"""Inventory-Adjusted Spread Arbitrage & AIS Fleet Analytics Model.

Streamlit entry point. Run with:
    streamlit run app.py
"""

from __future__ import annotations

import os

# Load .env (no-op if python-dotenv absent or no file) so local dev picks
# up AZURE_OPENAI_* keys without App Service's app settings.
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from data_ingestion import (
    fetch_pricing_data,
    fetch_pricing_intraday_data,
    fetch_inventory_data,
    fetch_ais_data,
    PricingResult,
    InventoryResult,
    AISResult,
    PricingUnavailable,
    InventoryUnavailable,
    active_pricing_provider,
    active_inventory_provider,
)
from quantitative_models import (
    compute_spread_zscore,
    forecast_depletion,
    categorize_flag_states,
    backtest_zscore_meanreversion,
    walk_forward_backtest,
    monte_carlo_entry_noise,
    regime_breakdown,
)
from webgpu_components import render_hero_banner, render_fleet_globe
from alerts import maybe_send_zscore_alert
from observability import configure as _obs_configure, span as _obs_span, trace_event

_AI_ACTIVE = _obs_configure()


# ---------------------------------------------------------------------------
# Page config + sidebar
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Oil Terminal | Spread Arbitrage & AIS Fleet",
    page_icon="\U0001f6e2\ufe0f",
    layout="wide",
)

st.markdown(
    """
    <link rel="preconnect" href="https://cdn.jsdelivr.net" crossorigin>
    <link rel="dns-prefetch" href="https://cdn.jsdelivr.net">
    <link rel="preconnect" href="https://threejs.org" crossorigin>
    <style>
    .block-container { padding-top: 1.2rem; padding-bottom: 2rem; }
    .stTabs [data-baseweb="tab-list"] { gap: 2rem; }
    .big-metric { font-size: 1.1rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.sidebar.header("Controls")


def _clamp(value, lo, hi, default):
    try:
        v = float(value)
        if v != v or v == float("inf") or v == float("-inf"):
            return default
        return max(lo, min(hi, v))
    except (TypeError, ValueError):
        return default


def _q_default(key: str, lo: float, hi: float, default: float) -> float:
    """Read a sidebar default from ?key=... query params with strict clamping."""
    qv = st.query_params.get(key)
    if qv is None:
        return default
    return _clamp(qv, lo, hi, default)


show_advanced = st.sidebar.checkbox(
    "Show advanced metrics",
    value=False,
    help=(
        "When on, the UI also shows the raw statistical labels "
        "(Z-score, percentile, Kelly sizing math) alongside the plain-language ones."
    ),
)

z_threshold = st.sidebar.slider(
    "Dislocation alert level" + (" (σ, Z-score)" if show_advanced else ""),
    min_value=0.5,
    max_value=5.0,
    value=_q_default("z", 0.5, 5.0, 3.0),
    step=0.1,
    help=(
        "How far the Brent-WTI spread has to drift from its normal range "
        "before we flag it. Measured in standard deviations (Z-score). "
        "3.0σ ≈ extreme dislocation, triggers once every few years on average."
    ),
)
floor_mbbl_default = int(_q_default("floor", 100, 700, 300))
floor_mbbl = st.sidebar.slider(
    "Inventory floor (million barrels)",
    min_value=100,
    max_value=700,
    value=floor_mbbl_default,
    step=25,
    help=(
        "The inventory level we want to stay above. The depletion tab "
        "projects when we'd hit this floor if the current drawdown pace held."
    ),
)
floor_bbls = float(floor_mbbl) * 1_000_000.0

depletion_weeks = st.sidebar.slider(
    "Drawdown lookback (weeks)",
    min_value=2,
    max_value=26,
    value=int(_q_default("window", 2, 26, 4)),
    step=1,
    help=(
        "How many trailing weeks of inventory history to fit the "
        "drawdown-rate regression to. Shorter = more reactive but noisier."
    ),
)

# Keep the URL query params in sync so links capture the current slider state.
st.query_params["z"] = f"{z_threshold:.1f}"
st.query_params["floor"] = str(int(floor_mbbl))
st.query_params["window"] = str(int(depletion_weeks))

st.sidebar.markdown("---")
st.sidebar.caption(
    f"Pricing: {active_pricing_provider('daily')}  \n"
    f"Inventory: {active_inventory_provider()}  \n"
    f"AIS: aisstream.io if `AISSTREAM_API_KEY` set, else labeled Q3 2024 snapshot."
)

alert_on = st.sidebar.toggle(
    "Email me on Z-score breach",
    value=False,
    help="Requires ALERT_SMTP_* env vars. Without them, the UI will show the "
    "exact message that would have been sent.",
)

live_mode = st.sidebar.toggle(
    "Live mode (1-min bars, 60s refresh)",
    value=True,
    help="When on, the top ticker strip pulls 1-min intraday bars from yfinance "
    "every 60s via an st.fragment. When off, a 60-day static snapshot is used.",
)

st.sidebar.markdown("---")
st.sidebar.caption("Backtest frictions")
slippage_per_bbl = st.sidebar.number_input(
    "Slippage (USD/bbl per leg)",
    min_value=0.0, max_value=2.0, value=0.05, step=0.01, format="%.2f",
    help="Bid-ask drag applied at both entry and exit. 0.05/bbl ≈ tight institutional fill.",
)
commission_per_trade = st.sidebar.number_input(
    "Commission (USD/round-trip)",
    min_value=0.0, max_value=250.0, value=20.0, step=5.0, format="%.0f",
    help="Fixed fee deducted per completed trade. Zero = frictionless toy.",
)


# ---------------------------------------------------------------------------
# Data loading (cached)
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False, ttl=60 * 60)
def _load_pricing_cached() -> PricingResult:
    return fetch_pricing_data(years=5)


@st.cache_data(show_spinner=False, ttl=60 * 60 * 4)  # EIA publishes weekly
def _load_inventory_cached() -> InventoryResult:
    return fetch_inventory_data()


@st.cache_data(show_spinner=False, ttl=60 * 30)
def _load_ais_cached() -> AISResult:
    return fetch_ais_data(n_vessels=500)


# --- Defensive fetch: surface clear error states instead of fake data ---
pricing_res: PricingResult | None = None
inventory_res: InventoryResult | None = None
ais_res: AISResult | None = None

with st.spinner("Loading live market data..."):
    try:
        pricing_res = _load_pricing_cached()
    except PricingUnavailable as exc:
        st.error(
            "Pricing feed unavailable — yfinance returned no data. "
            f"`{exc}`  Click below to retry."
        )
        if st.button("Retry pricing fetch", key="retry_pricing"):
            _load_pricing_cached.clear()
            st.rerun()
        st.stop()

    try:
        inventory_res = _load_inventory_cached()
    except InventoryUnavailable as exc:
        st.error(
            "Inventory feed unavailable — EIA dnav and FRED both failed. "
            f"`{exc}`  Click below to retry."
        )
        if st.button("Retry inventory fetch", key="retry_inventory"):
            _load_inventory_cached.clear()
            st.rerun()
        st.stop()

    try:
        ais_res = _load_ais_cached()
    except Exception as exc:
        st.error(f"AIS fetch raised unexpectedly: `{exc!r}`")
        st.stop()

prices = pricing_res.frame
inventory = inventory_res.frame
ais_df = ais_res.frame


# --- Compute-heavy models cached by their inputs (5y spread, backtest,
# depletion regression) so slider moves don't re-run them. Each helper
# takes only hashable primitives + the fingerprint of its input frame.
@st.cache_data(show_spinner=False, ttl=60 * 60)
def _spread_cached(price_fingerprint: str, window: int) -> pd.DataFrame:
    return compute_spread_zscore(prices, window=window)


@st.cache_data(show_spinner=False, ttl=60 * 60)
def _depletion_cached(inv_fingerprint: str, floor: float, weeks: int) -> dict:
    return forecast_depletion(inventory, floor_bbls=floor, lookback_weeks=weeks)


@st.cache_data(show_spinner=False, ttl=60 * 60)
def _backtest_cached(
    spread_fingerprint: str, entry_z: float, exit_z: float,
    slippage: float, commission: float,
) -> dict:
    return backtest_zscore_meanreversion(
        spread_df, entry_z=entry_z, exit_z=exit_z,
        notional_bbls=10_000.0,
        slippage_per_bbl=slippage, commission_per_trade=commission,
    )


def _fp(df: pd.DataFrame) -> str:
    return f"{len(df)}-{df.index[-1] if len(df) else 'empty'}"


spread_df = _spread_cached(_fp(prices), 90)
depletion = _depletion_cached(_fp(inventory), floor_bbls, depletion_weeks)
ais_with_cat, ais_agg = categorize_flag_states(ais_df)


# ---------------------------------------------------------------------------
# Header + WebGPU hero
# ---------------------------------------------------------------------------
st.title("Inventory-Adjusted Spread Arbitrage & AIS Fleet Analytics")
st.caption(
    "Macro oil desk terminal — Brent/WTI dislocations, inventory drawdown velocity, "
    "and tanker fleet composition by regulatory regime."
)


def _sparkline(series, color: str, height: int = 60) -> go.Figure:
    fig = go.Figure(
        data=[
            go.Scattergl(
                x=list(range(len(series))),
                y=list(series),
                mode="lines",
                line=dict(color=color, width=1.6),
                hoverinfo="skip",
            )
        ]
    )
    fig.update_layout(
        height=height,
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        showlegend=False,
    )
    return fig


@st.cache_data(show_spinner=False, ttl=45)
def _load_intraday_cached(refresh_token: int):
    """Cached intraday pull — token gives us a per-minute bucket."""
    try:
        return fetch_pricing_intraday_data(interval="1m", period="2d")
    except Exception:
        return None


@st.fragment(run_every=60 if live_mode else None)
def _ticker_strip() -> None:
    """Real-time ticker strip — autorefreshes every 60s in live mode."""
    import time as _t
    bucket = int(_t.time() // 60)
    intraday = _load_intraday_cached(bucket) if live_mode else None

    brent_tail: pd.Series
    wti_tail: pd.Series
    mode_badge: str
    last_updated: str

    if intraday is not None and not intraday.frame.empty:
        brent_tail = intraday.frame["Brent"].tail(120)
        wti_tail = intraday.frame["WTI"].tail(120)
        last_updated = intraday.frame.index[-1].strftime("%H:%M:%S UTC")
        mode_badge = f"LIVE 1-min  ·  last bar {last_updated}  ·  ~15-min publisher delay"
    else:
        brent_tail = prices["Brent"].tail(60)
        wti_tail = prices["WTI"].tail(60)
        mode_badge = "DAILY snapshot (market closed or live feed unavailable)"
        last_updated = prices.index[-1].strftime("%Y-%m-%d")

    spread_tail = brent_tail.reindex_like(wti_tail).dropna() - wti_tail.dropna().reindex_like(brent_tail.reindex_like(wti_tail).dropna())
    latest_brent_v = float(brent_tail.iloc[-1])
    latest_wti_v = float(wti_tail.iloc[-1])
    latest_spread_v = latest_brent_v - latest_wti_v

    st.caption(f"Source: **Yahoo Finance (Brent / WTI)** · {mode_badge}")
    cols = st.columns(4)
    cols[0].metric(
        "Brent",
        f"${latest_brent_v:,.2f}",
        delta=f"{(latest_brent_v - float(brent_tail.iloc[0])):+.2f}",
    )
    cols[0].plotly_chart(_sparkline(brent_tail, "#1f77b4"),
                        use_container_width=True,
                        config={"displayModeBar": False},
                        key="sp_brent")

    cols[1].metric(
        "WTI",
        f"${latest_wti_v:,.2f}",
        delta=f"{(latest_wti_v - float(wti_tail.iloc[0])):+.2f}",
    )
    cols[1].plotly_chart(_sparkline(wti_tail, "#d62728"),
                        use_container_width=True,
                        config={"displayModeBar": False},
                        key="sp_wti")

    z_tail = spread_df["Z_Score"].dropna().tail(120)
    z_val = z_tail.iloc[-1] if not z_tail.empty else 0.0
    dislocation_label = (
        f"Dislocation {z_val:+.2f}\u03c3" if show_advanced
        else f"Dislocation {z_val:+.2f}"
    )
    cols[2].metric(
        f"Spread ${latest_spread_v:+.2f}",
        dislocation_label,
        delta=("ALERT" if abs(z_val) >= z_threshold else "calm"),
        delta_color=("inverse" if abs(z_val) >= z_threshold else "normal"),
        help=(
            "Dislocation measures how far today's Brent-WTI spread is from "
            "its normal range. +2 = spread is about 2× its usual daily wobble "
            "above average; statistically extreme. Technically a Z-score."
        ),
    )
    cols[2].plotly_chart(_sparkline(z_tail, "#2ca02c"),
                        use_container_width=True,
                        config={"displayModeBar": False},
                        key="sp_z")

    inv_tail = inventory["Total_Inventory_bbls"].tail(52) / 1e6
    cols[3].metric(
        "Inventory",
        f"{inv_tail.iloc[-1]:,.0f} Mbbl",
        delta=f"{(inv_tail.iloc[-1]-inv_tail.iloc[0]):+.1f}",
    )
    cols[3].plotly_chart(_sparkline(inv_tail, "#ff9f1c"),
                        use_container_width=True,
                        config={"displayModeBar": False},
                        key="sp_inv")


_ticker_strip()

render_hero_banner(height=220)


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab_arb, tab_depl, tab_fleet, tab_ai = st.tabs(
    [
        "Spread dislocation",
        "Inventory drawdown",
        "Tanker fleet",
        "AI trade thesis",
    ]
)


# ---- Tab 1 --------------------------------------------------------------
with tab_arb:
    st.subheader(
        "Brent vs WTI — price and spread dislocation"
        + (" (Z-score)" if show_advanced else "")
    )
    st.caption(
        f"Source: **{pricing_res.source}** (daily, ~15-min delayed futures) · "
        f"fetched {pricing_res.fetched_at.strftime('%Y-%m-%d %H:%M:%SZ')}"
    )

    latest_spread = float(spread_df["Spread"].dropna().iloc[-1]) if not spread_df["Spread"].dropna().empty else 0.0
    latest_z = float(spread_df["Z_Score"].dropna().iloc[-1]) if not spread_df["Z_Score"].dropna().empty else 0.0
    z_flag = abs(latest_z) >= z_threshold

    col1, col2, col3 = st.columns(3)
    col1.metric("Latest Brent", f"${float(prices['Brent'].iloc[-1]):,.2f}")
    col2.metric("Latest WTI", f"${float(prices['WTI'].iloc[-1]):,.2f}")
    col3.metric(
        "90-day dislocation" + (" (Z-score)" if show_advanced else ""),
        f"{latest_z:+.2f}",
        delta=f"{'ALERT' if z_flag else 'calm'}  |  spread ${latest_spread:,.2f}",
        delta_color="inverse" if z_flag else "normal",
        help=(
            "How far the Brent-WTI spread is from its 90-day normal, in "
            "standard deviations. |Dislocation| > 2 = statistically unusual; "
            "> 3 = extreme."
        ),
    )

    if alert_on:
        alert_status = maybe_send_zscore_alert(latest_z, z_threshold, latest_spread)
        if alert_status is None:
            st.success(f"Spread within band — no alert sent (|Z|={abs(latest_z):.2f} < {z_threshold:.1f}).")
        elif alert_status.startswith("[sent]"):
            st.error(alert_status)
        elif alert_status.startswith("[error]"):
            st.warning(alert_status)
        else:
            with st.expander("Alert would be sent (SMTP not configured)", expanded=False):
                st.code(alert_status)

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        row_heights=[0.62, 0.38],
        subplot_titles=(
            "Brent & WTI (USD / barrel)",
            "How stretched is the spread? — 90-day dislocation"
            + (" (Z-score)" if show_advanced else ""),
        ),
    )

    fig.add_trace(
        go.Scattergl(
            x=prices.index,
            y=prices["Brent"],
            name="Brent",
            line=dict(color="#1f77b4", width=1.4),
            hovertemplate="%{x|%Y-%m-%d}<br>Brent $%{y:.2f}<extra></extra>",
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scattergl(
            x=prices.index,
            y=prices["WTI"],
            name="WTI",
            line=dict(color="#d62728", width=1.4),
            hovertemplate="%{x|%Y-%m-%d}<br>WTI $%{y:.2f}<extra></extra>",
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Scattergl(
            x=spread_df.index,
            y=spread_df["Z_Score"],
            name="Spread Z",
            line=dict(color="#2ca02c", width=1.2),
            hovertemplate="%{x|%Y-%m-%d}<br>Z %{y:.2f}<extra></extra>",
        ),
        row=2,
        col=1,
    )
    # Horizontal red alert lines at +/- threshold
    fig.add_hline(
        y=z_threshold,
        line=dict(color="red", width=1.2, dash="dash"),
        row=2,
        col=1,
        annotation_text=f"+{z_threshold:.1f}\u03c3",
        annotation_position="top right",
    )
    fig.add_hline(
        y=-z_threshold,
        line=dict(color="red", width=1.2, dash="dash"),
        row=2,
        col=1,
        annotation_text=f"-{z_threshold:.1f}\u03c3",
        annotation_position="bottom right",
    )
    fig.add_hline(y=0, line=dict(color="rgba(150,150,150,0.5)", width=1), row=2, col=1)

    fig.update_layout(
        height=640,
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=40, r=20, t=60, b=40),
        template="plotly_dark",
    )
    fig.update_yaxes(title_text="USD / bbl", row=1, col=1)
    fig.update_yaxes(title_text="Z-Score", row=2, col=1)
    fig.update_xaxes(title_text="Date", row=2, col=1)

    st.plotly_chart(fig, use_container_width=True)

    with st.expander("Recent observations"):
        st.dataframe(
            spread_df.tail(20)[["Brent", "WTI", "Spread", "Z_Score"]].round(3),
            use_container_width=True,
        )
        st.download_button(
            label="Download full series (CSV)",
            data=spread_df[["Brent", "WTI", "Spread", "Z_Score"]].to_csv().encode(),
            file_name="brent_wti_spread.csv",
            mime="text/csv",
            key="download_spread",
        )

    st.markdown(
        "#### Snap-back to normal — historical backtest"
        + (" (Z-score mean reversion)" if show_advanced else "")
    )
    st.caption(
        f"Enters when dislocation reaches \u00b1{z_threshold:.1f}, exits when "
        "the spread is back near normal. 10,000 barrels per trade, with the "
        "slippage and commission drag you set in the sidebar. "
        "Think of the PnL as a signal-quality indicator, not a P&L forecast."
    )
    bt = _backtest_cached(
        _fp(spread_df), float(z_threshold), 0.2,
        float(slippage_per_bbl), float(commission_per_trade),
    )
    bt_c1, bt_c2, bt_c3, bt_c4, bt_c5, bt_c6 = st.columns(6)
    bt_c1.metric("Trades", f"{bt['n_trades']:,}")
    bt_c2.metric(
        "Total PnL",
        f"${bt['total_pnl_usd']:,.0f}",
        delta=f"{bt['avg_pnl_per_bbl']:+.2f}/bbl avg",
    )
    bt_c3.metric(
        "Win rate",
        f"{bt['win_rate']*100:.1f}%",
        help="Share of historical trades that closed profitably.",
    )
    bt_c4.metric(
        "Avg hold",
        f"{bt['avg_days_held']:.1f} days",
        help="Average number of days a trade was open.",
    )
    bt_c5.metric(
        "Biggest losing streak",
        f"${bt.get('max_drawdown_usd', 0.0):,.0f}",
        help=(
            "The deepest peak-to-trough drop the cumulative PnL experienced "
            "during the backtest. Technically the max drawdown."
        ),
    )
    bt_c6.metric(
        "Risk-adjusted return",
        f"{bt.get('sharpe', 0.0):.2f}",
        help=(
            "Average trade return divided by its volatility, annualised. "
            "Rule of thumb: > 1 is good, > 2 is excellent, < 0.5 is noise. "
            "Technically the Sharpe ratio."
        ),
    )

    if not bt["equity_curve"].empty:
        eq_fig = go.Figure()
        eq_fig.add_trace(
            go.Scattergl(
                x=bt["equity_curve"]["Date"],
                y=bt["equity_curve"]["cum_pnl_usd"],
                name="Cumulative PnL",
                line=dict(color="#ff9f1c", width=1.8),
                hovertemplate="%{x|%Y-%m-%d}<br>$%{y:,.0f}<extra></extra>",
            )
        )
        eq_fig.update_layout(
            height=320,
            template="plotly_dark",
            margin=dict(l=40, r=20, t=20, b=40),
            yaxis_title="Cumulative PnL (USD)",
            xaxis_title="Trade exit date",
            showlegend=False,
        )
        st.plotly_chart(eq_fig, use_container_width=True)

        # PnL distribution histogram
        pnl_fig = go.Figure()
        pnl_fig.add_trace(
            go.Histogram(
                x=bt["trades"]["pnl_usd"],
                nbinsx=24,
                marker_color="#ff9f1c",
                opacity=0.85,
                hovertemplate="bucket %{x:,.0f} USD<br>count=%{y}<extra></extra>",
            )
        )
        pnl_fig.add_vline(
            x=0, line=dict(color="#e7ecf3", width=1, dash="dot"),
            annotation_text="breakeven", annotation_position="top right",
        )
        pnl_fig.update_layout(
            height=260,
            template="plotly_dark",
            margin=dict(l=40, r=20, t=20, b=40),
            yaxis_title="Trades",
            xaxis_title="Trade PnL (USD)",
            showlegend=False,
            bargap=0.03,
        )
        st.plotly_chart(pnl_fig, use_container_width=True)

        with st.expander("Trade blotter"):
            st.dataframe(bt["trades"], use_container_width=True)
            st.download_button(
                label="Download trade blotter (CSV)",
                data=bt["trades"].to_csv(index=False).encode(),
                file_name="zscore_backtest_trades.csv",
                mime="text/csv",
                key="download_blotter",
            )

        with st.expander("Walk-forward, Monte Carlo, regime breakdown (robustness)"):
            st.caption(
                "These extras stress the strategy. Walk-forward slides a "
                "12-month window in 3-month steps to spot regime breaks. "
                "Monte Carlo adds ±0.15σ i.i.d. noise to the entry "
                "threshold across 200 runs. Regime split bins trades by "
                "the 30-day realised vol at entry."
            )

            # Walk-forward
            wf = walk_forward_backtest(
                spread_df, entry_z=float(z_threshold), exit_z=0.2,
                notional_bbls=10_000.0,
                slippage_per_bbl=float(slippage_per_bbl),
                window_months=12, step_months=3,
            )
            if not wf.empty:
                wf_fig = go.Figure()
                wf_fig.add_trace(
                    go.Bar(
                        x=wf["window_end"],
                        y=wf["total_pnl_usd"],
                        marker_color=[
                            "#2ecc71" if p >= 0 else "#e74c3c" for p in wf["total_pnl_usd"]
                        ],
                        hovertemplate=(
                            "window end %{x|%Y-%m-%d}<br>PnL $%{y:,.0f}<br>"
                            "trades %{customdata[0]}<br>win rate %{customdata[1]:.0%}"
                            "<extra></extra>"
                        ),
                        customdata=wf[["n_trades", "win_rate"]].values,
                    )
                )
                wf_fig.update_layout(
                    height=280,
                    template="plotly_dark",
                    margin=dict(l=40, r=20, t=20, b=40),
                    yaxis_title="Window PnL (USD)",
                    xaxis_title="Window end",
                    showlegend=False,
                )
                st.markdown("**Walk-forward (12m window, 3m step)**")
                st.plotly_chart(wf_fig, use_container_width=True)
            else:
                st.info("Not enough history for a 12-month walk-forward window.")

            # Monte Carlo
            mc = monte_carlo_entry_noise(
                spread_df,
                entry_z=float(z_threshold), exit_z=0.2,
                notional_bbls=10_000.0,
                slippage_per_bbl=float(slippage_per_bbl),
                n_runs=200, noise_sigma=0.15, seed=7,
            )
            if mc["n_runs"] > 0:
                mc_cols = st.columns(4)
                mc_cols[0].metric("MC runs", f"{mc['n_runs']}")
                mc_cols[1].metric("Mean PnL", f"${mc['pnl_mean']:,.0f}")
                mc_cols[2].metric("P05 PnL", f"${mc['pnl_p05']:,.0f}")
                mc_cols[3].metric("P95 PnL", f"${mc['pnl_p95']:,.0f}")
                st.caption(
                    "If P05 is deeply negative while P95 is positive the "
                    "strategy is threshold-sensitive — a small shift in "
                    f"entry_z wipes out results."
                )
            else:
                st.info("Monte Carlo skipped (no trades on this slice).")

            # Regime breakdown
            if not bt["trades"].empty:
                rb = regime_breakdown(spread_df, bt["trades"], vol_window=30)
                if not rb.empty:
                    rb_fig = go.Figure(
                        data=[
                            go.Bar(
                                x=rb["regime"],
                                y=rb["total_pnl_usd"],
                                marker_color=["#1f77b4" if r == "low_vol" else "#ff7f0e" for r in rb["regime"]],
                                text=[
                                    f"{int(n)} trades<br>{w*100:.0f}% win"
                                    for n, w in zip(rb["n_trades"], rb["win_rate"])
                                ],
                                textposition="outside",
                            )
                        ]
                    )
                    rb_fig.update_layout(
                        height=280,
                        template="plotly_dark",
                        yaxis_title="Total PnL (USD)",
                        xaxis_title="Volatility regime (30d realised, median-split)",
                        showlegend=False,
                        margin=dict(l=40, r=20, t=30, b=40),
                    )
                    st.markdown("**Regime breakdown (high-vol vs low-vol at entry)**")
                    st.plotly_chart(rb_fig, use_container_width=True)
    else:
        st.info(
            f"No trades triggered at \u00b1{z_threshold:.1f}\u03c3 on the "
            "historical window. Drop the threshold in the sidebar to see activity."
        )


# ---- Tab 2 --------------------------------------------------------------
with tab_depl:
    st.subheader("How fast is US crude inventory drawing down?")
    st.caption(
        f"Source: **EIA (dnav, keyless)** via {inventory_res.source} · "
        f"fetched {inventory_res.fetched_at.strftime('%Y-%m-%d %H:%M:%SZ')} · "
        f"[{inventory_res.source_url}]({inventory_res.source_url})"
    )

    daily_rate = depletion["daily_depletion_bbls"]
    weekly_rate = depletion["weekly_depletion_bbls"]
    current_inv = depletion["current_inventory"]
    proj_date = depletion["projected_floor_date"]
    r2 = depletion["r_squared"]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "Current inventory",
        f"{current_inv/1e6:,.1f} million barrels",
        help="US commercial crude (ex-SPR) + SPR, as of the latest EIA weekly release.",
    )
    c2.metric(
        "Daily drawdown",
        f"{daily_rate/1e3:+,.1f} thousand bbl/day",
        delta=f"{weekly_rate/1e6:+.2f} million bbl/week",
        help=(
            "How much inventory is disappearing per day on average, "
            "estimated from a linear fit to the trailing lookback window. "
            "Negative = inventories shrinking."
        ),
    )
    c3.metric(
        "Date inventory hits the floor",
        proj_date.strftime("%Y-%m-%d") if proj_date is not None else "—",
        help=(
            "If the current daily drawdown continues unchanged, this is the "
            "approximate date the total inventory would fall to the floor you "
            "set in the sidebar."
        ),
    )
    c4.metric(
        "Trend fit quality" + (" (R²)" if show_advanced else ""),
        f"{r2:.3f}",
        help=(
            "How well the linear trend explains the recent inventory path. "
            "1.0 = perfect line, 0 = noise. Technically R² of the regression."
        ),
    )

    fig2 = go.Figure()

    fig2.add_trace(
        go.Scattergl(
            x=inventory.index,
            y=inventory["Total_Inventory_bbls"] / 1e6,
            name="Total Inventory (Mbbl)",
            line=dict(color="#1f77b4", width=1.6),
            hovertemplate="%{x|%Y-%m-%d}<br>%{y:,.1f} Mbbl<extra></extra>",
        )
    )

    reg_line = depletion["regression_line"]
    if not reg_line.empty:
        fig2.add_trace(
            go.Scattergl(
                x=reg_line["Date"],
                y=reg_line["Projected_Inventory_bbls"] / 1e6,
                name=f"Regression Projection ({depletion_weeks}w window)",
                line=dict(color="#ff7f0e", width=2, dash="dash"),
                hovertemplate="%{x|%Y-%m-%d}<br>proj %{y:,.1f} Mbbl<extra></extra>",
            )
        )

    fig2.add_hline(
        y=floor_bbls / 1e6,
        line=dict(color="red", width=1.4, dash="dot"),
        annotation_text=f"Floor {floor_mbbl} Mbbl",
        annotation_position="bottom right",
    )

    if proj_date is not None:
        fig2.add_vline(
            x=proj_date,
            line=dict(color="red", width=1, dash="dot"),
            annotation_text=proj_date.strftime("%Y-%m-%d"),
            annotation_position="top right",
        )

    fig2.update_layout(
        height=560,
        template="plotly_dark",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=40, r=20, t=40, b=40),
        yaxis_title="Inventory (Million bbls)",
        xaxis_title="Date",
    )

    st.plotly_chart(fig2, use_container_width=True)

    st.caption(
        f"Linear regression on trailing {depletion_weeks}-week inventory window. "
        "Dashed orange line is the forward projection; red dotted line is the user-set floor."
    )

    st.download_button(
        label="Download inventory + projection (CSV)",
        data=(
            pd.concat(
                [
                    inventory.reset_index().rename(columns={"Date": "Date"}),
                    depletion["regression_line"].assign(Date=depletion["regression_line"]["Date"]),
                ],
                axis=0,
                ignore_index=True,
            ).to_csv(index=False).encode()
        ),
        file_name="inventory_depletion.csv",
        mime="text/csv",
        key="download_depletion",
    )


# ---- Tab 3 --------------------------------------------------------------
with tab_fleet:
    st.subheader("Where are the crude tankers flagged?")
    st.caption(
        "Tanker registrations split into three policy-relevant buckets: "
        "US-flagged vessels (Jones Act), flags of convenience used by "
        "sanctions-sensitive cargoes, and sanctioned-country flags."
    )
    st.caption(
        f"Source: **{ais_res.source}** · fetched {ais_res.fetched_at.strftime('%Y-%m-%d %H:%M:%SZ')}"
    )
    if ais_res.snapshot_notice:
        st.info(ais_res.snapshot_notice)

    category_colors = {
        "Jones Act / Domestic": "#2ca02c",
        "Shadow Risk": "#ff9f1c",
        "Sanctioned": "#d62728",
        "Other": "#8c8c8c",
    }
    # UI-only labels — the underlying category names stay stable for downstream
    # math (backtest / thesis / tests). See quantitative_models.categorize_flag_states.
    category_display = {
        "Jones Act / Domestic": "US-flagged / US-destined",
        "Shadow Risk": "Flags of convenience",
        "Sanctioned": "Sanctioned-country flags",
        "Other": "Other",
    }
    category_display_full = {
        "Jones Act / Domestic": (
            "US-flagged / US-destined (Jones Act)"
        ),
        "Shadow Risk": "Flags of convenience (Panama, Liberia, Marshall Is., Malta)",
        "Sanctioned": "Sanctioned-country flags (Russia, Iran, Venezuela)",
        "Other": "Other",
    }

    headline = ais_agg[ais_agg["Category"].isin(category_colors.keys())].copy()
    headline = headline.set_index("Category").reindex(
        ["Jones Act / Domestic", "Shadow Risk", "Sanctioned", "Other"]
    ).fillna(0).reset_index()

    colors = [category_colors[c] for c in headline["Category"]]

    display_labels = [category_display.get(c, c) for c in headline["Category"]]

    bar = go.Figure()
    bar.add_trace(
        go.Bar(
            x=display_labels,
            y=headline["Total_Cargo_Mbbl"],
            marker_color=colors,
            text=[
                f"{v:,.1f} million barrels<br>{int(n)} vessels"
                for v, n in zip(headline["Total_Cargo_Mbbl"], headline["Vessel_Count"])
            ],
            textposition="outside",
            hovertemplate="%{x}<br>%{y:,.1f} million barrels<extra></extra>",
            name="Cargo",
        )
    )
    bar.update_layout(
        height=440,
        template="plotly_dark",
        yaxis_title="Million barrels on water",
        xaxis_title="",
        showlegend=False,
        margin=dict(l=40, r=20, t=30, b=40),
    )

    total_mbbl = float(ais_with_cat["Cargo_Volume_bbls"].sum() / 1e6)
    total_vessels = int(len(ais_with_cat))

    m1, m2, m3 = st.columns(3)
    m1.metric(
        "Tankers tracked",
        f"{total_vessels:,}",
        help="Number of crude tankers in the current snapshot.",
    )
    m2.metric(
        "Total cargo on water",
        f"{total_mbbl:,.1f} million barrels",
        help="Sum of estimated cargo volumes across all tracked tankers.",
    )
    jones = float(headline.loc[headline["Category"] == "Jones Act / Domestic", "Total_Cargo_Mbbl"].sum())
    m3.metric(
        "US-flagged / US-destined share",
        f"{(jones / total_mbbl * 100.0) if total_mbbl else 0:.1f}%",
        help=(
            "Share of cargo on US-flagged vessels OR destined for a US port. "
            "Technically the 'Jones Act / Domestic' bucket."
        ),
    )

    st.plotly_chart(bar, use_container_width=True)

    # Per-country drill-down (Mbbl by flag state, colored by category)
    drill = (
        ais_with_cat.groupby(["Flag_State", "Category"], as_index=False)
        .agg(
            Total_Cargo_bbls=("Cargo_Volume_bbls", "sum"),
            Vessel_Count=("Cargo_Volume_bbls", "count"),
        )
        .sort_values("Total_Cargo_bbls", ascending=False)
    )
    drill["Total_Cargo_Mbbl"] = drill["Total_Cargo_bbls"] / 1_000_000.0
    drill_fig = go.Figure()
    for cat, cat_color in category_colors.items():
        subset = drill[drill["Category"] == cat]
        if subset.empty:
            continue
        display_cat = category_display.get(cat, cat)
        drill_fig.add_trace(
            go.Bar(
                x=subset["Flag_State"],
                y=subset["Total_Cargo_Mbbl"],
                name=display_cat,
                marker_color=cat_color,
                hovertemplate=(
                    "%{x}<br>%{y:,.1f} million barrels"
                    "<br>%{customdata} vessels"
                    "<extra>"
                    + display_cat
                    + "</extra>"
                ),
                customdata=subset["Vessel_Count"],
            )
        )
    drill_fig.update_layout(
        height=380,
        template="plotly_dark",
        margin=dict(l=40, r=20, t=30, b=60),
        yaxis_title="Million barrels on water",
        xaxis_title="Vessel registration country",
        barmode="stack",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    st.markdown("#### Per-country breakdown")
    st.plotly_chart(drill_fig, use_container_width=True)

    st.markdown("#### Live globe")
    st.caption(
        "Green = US-flagged / US-destined · Amber = flags of convenience · "
        "Red = sanctioned-country flags · Grey = other. "
        "Uses WebGPU when your browser supports it; falls back to WebGL."
    )
    render_fleet_globe(ais_with_cat, height=560)

    with st.expander("Vessel sample (first 25 rows)"):
        sample = ais_with_cat.head(25)[
            [
                "Vessel_Name",
                "MMSI",
                "Flag_State",
                "Destination",
                "Cargo_Volume_bbls",
                "Category",
            ]
        ].rename(
            columns={
                "Vessel_Name": "Vessel name",
                "MMSI": "Vessel ID",
                "Flag_State": "Registered in",
                "Destination": "Destination",
                "Cargo_Volume_bbls": "Cargo (barrels)",
                "Category": "Bucket",
            }
        )
        sample["Bucket"] = sample["Bucket"].map(
            lambda c: category_display.get(c, c)
        )
        st.dataframe(
            sample,
            use_container_width=True,
            column_config={
                "Vessel ID": st.column_config.TextColumn(
                    "Vessel ID",
                    help="MMSI — Maritime Mobile Service Identity, the 9-digit AIS radio callsign.",
                ),
            } if hasattr(st, "column_config") else None,
        )
        st.download_button(
            label="Download full fleet roster (CSV)",
            data=ais_with_cat.to_csv(index=False).encode(),
            file_name="ais_fleet_roster.csv",
            mime="text/csv",
            key="download_fleet",
        )


# ---- Tab 4 — AI Trade Thesis ---------------------------------------------
with tab_ai:
    from trade_thesis import generate_thesis
    from thesis_context import build_context

    st.subheader("AI trade thesis")
    st.caption(
        "Plain-language trade guidance grounded in today's real state — "
        "spread dislocation, snap-back hit rate from the backtest, EIA "
        "inventory trend, tanker fleet composition, volatility regime. "
        "Educational research only."
    )

    endpoint_set = bool(os.environ.get("AZURE_OPENAI_ENDPOINT"))
    key_set = bool(os.environ.get("AZURE_OPENAI_KEY"))
    deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")

    status_cols = st.columns([1, 1, 1, 2])
    status_cols[0].metric("Endpoint", "set" if endpoint_set else "missing")
    status_cols[1].metric("API key", "set" if key_set else "missing")
    status_cols[2].metric("Deployment", deployment)
    status_cols[3].metric(
        "Mode",
        "Azure OpenAI (JSON schema)" if (endpoint_set and key_set) else "Rule-based fallback",
    )

    ctx_obj = build_context(
        pricing_res=pricing_res,
        inventory_res=inventory_res,
        spread_df=spread_df,
        backtest=bt,
        depletion=depletion,
        ais_agg=ais_agg,
        ais_with_cat=ais_with_cat,
        z_threshold=z_threshold,
        floor_bbls=floor_bbls,
    )
    ctx_obj.fleet_source = ais_res.source

    regenerate = st.button("Regenerate thesis", type="primary", key="regen_thesis")
    # Cache key: params hash + date-hour so sliders don't re-burn tokens but
    # the thesis refreshes at least once per hour.
    cache_key = (
        ctx_obj.fingerprint(),
        pd.Timestamp.utcnow().strftime("%Y-%m-%d-%H"),
        regenerate,
    )
    if "_thesis_key" not in st.session_state or st.session_state["_thesis_key"] != cache_key:
        with st.spinner("Generating trade thesis..."):
            try:
                thesis = generate_thesis(ctx_obj)
            except Exception as exc:
                st.error(f"Thesis generation failed: `{exc!r}`")
                st.stop()
        st.session_state["_thesis_obj"] = thesis
        st.session_state["_thesis_key"] = cache_key
    thesis = st.session_state["_thesis_obj"]
    raw = thesis.raw

    # Stance pill — plain-language mapping
    stance = raw.get("stance", "flat")
    stance_color = {"long_spread": "#2ecc71", "short_spread": "#e74c3c", "flat": "#95a5a6"}[stance]
    stance_label = {
        "long_spread": "BUY THE SPREAD",
        "short_spread": "SELL THE SPREAD",
        "flat": "STAND ASIDE",
    }[stance]
    # Technical suffix only when advanced view is on
    stance_suffix = (
        {"long_spread": "  (long spread)", "short_spread": "  (short spread)", "flat": "  (flat)"}[stance]
        if show_advanced
        else ""
    )
    conviction = float(raw.get("conviction_0_to_10", 0.0))
    horizon = int(raw.get("time_horizon_days", 0))

    st.markdown(
        f"""
        <div style="display:flex; gap:18px; align-items:center; margin-top:6px; margin-bottom:10px;">
          <span style="background:{stance_color}; color:#0b0f14; padding:10px 18px; border-radius:8px;
                       font-weight:700; letter-spacing:1.2px; font-size:1.15rem;">
            {stance_label}{stance_suffix}
          </span>
          <span style="color:#e7ecf3; font-family:ui-monospace,Menlo,monospace;">
            confidence <b>{conviction:.1f}/10</b>
            &nbsp;·&nbsp; horizon <b>{horizon} days</b>
            &nbsp;·&nbsp; source <b>{thesis.source}</b>
          </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    entry = raw.get("entry", {}) or {}
    exit_ = raw.get("exit", {}) or {}
    sizing = raw.get("position_sizing", {}) or {}

    def _z_display(v):
        return f"{v}σ (Z)" if show_advanced else f"{v}"

    tri_cols = st.columns(3)
    tri_cols[0].markdown(
        f"**Enter when**\n\n"
        f"- {entry.get('trigger_condition','—')}\n"
        f"- Dislocation reaches **{_z_display(entry.get('suggested_z_level','—'))}**\n"
        f"- Spread near **${entry.get('suggested_spread_usd','—')}**"
    )
    tri_cols[1].markdown(
        f"**Take profit when**\n\n"
        f"- {exit_.get('target_condition','—')}\n"
        f"- Dislocation reaches **{_z_display(exit_.get('target_z_level','—'))}**"
    )
    tri_cols[2].markdown(
        f"**Cut the trade if**\n\n"
        f"- {exit_.get('stop_loss_condition','—')}\n"
        f"- Dislocation reaches **{_z_display(exit_.get('stop_z_level','—'))}**"
    )

    st.markdown("#### Why — the thesis")
    st.markdown(f"> {raw.get('thesis_summary','(no summary)')}")

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("#### What's driving this")
        for d in (raw.get("key_drivers") or []):
            st.markdown(f"- {d}")
        sizing_method_display = {
            "fixed_fractional": "fixed fraction of capital",
            "volatility_scaled": "scaled by volatility",
            "kelly": "Kelly-style sizing",
        }.get(sizing.get("method", ""), sizing.get("method", "?"))
        method_suffix = f" ({sizing.get('method','?')})" if show_advanced else ""
        st.markdown(
            f"**How much to risk** — {sizing_method_display}{method_suffix} · "
            f"suggest **{sizing.get('suggested_pct_of_capital',0):.1f}% of capital**"
        )
        st.caption(sizing.get("rationale", ""))
    with col_b:
        st.markdown("#### What would make us wrong")
        with st.container(border=True):
            for r in (raw.get("invalidation_risks") or []):
                st.warning(r)

    if raw.get("catalyst_watchlist"):
        st.markdown("#### Upcoming events to watch")
        for c in raw["catalyst_watchlist"]:
            st.info(f"**{c.get('event','?')}** — {c.get('date','?')} · {c.get('expected_impact','')}")

    with st.expander("Things to keep in mind (caveats & guardrails)"):
        if thesis.guardrails_applied:
            st.markdown("**Automatic adjustments this run:**")
            for g in thesis.guardrails_applied:
                st.markdown(f"- {g}")
        if raw.get("data_caveats"):
            st.markdown("**Model-reported caveats:**")
            for c in raw["data_caveats"]:
                st.markdown(f"- {c}")

    # Copy-as-markdown report — same plain language
    md_report_lines = [
        f"# Trade Thesis — {thesis.generated_at}",
        f"**Stance:** {stance_label}  \n**Confidence:** {conviction:.1f}/10  \n"
        f"**Horizon:** {horizon} days  \n**Source:** {thesis.source}",
        "",
        f"## Why\n\n{raw.get('thesis_summary','')}",
        "",
        f"### Enter when\n- {entry.get('trigger_condition','')}\n- Dislocation: {entry.get('suggested_z_level','')}\n- Spread: ${entry.get('suggested_spread_usd','')}",
        f"\n### Take profit when\n- {exit_.get('target_condition','')}\n- Dislocation: {exit_.get('target_z_level','')}",
        f"\n### Cut the trade if\n- {exit_.get('stop_loss_condition','')}\n- Dislocation: {exit_.get('stop_z_level','')}",
        "",
        f"### How much to risk\n{sizing_method_display} — {sizing.get('suggested_pct_of_capital',0):.1f}% of capital\n\n{sizing.get('rationale','')}",
        "",
        "### What's driving this\n" + "\n".join(f"- {d}" for d in (raw.get("key_drivers") or [])),
        "\n### What would make us wrong\n" + "\n".join(f"- {r}" for r in (raw.get("invalidation_risks") or [])),
    ]
    if raw.get("data_caveats"):
        md_report_lines.append("\n### Things to keep in mind\n" + "\n".join(f"- {c}" for c in raw["data_caveats"]))
    md_report = "\n".join(md_report_lines)

    st.download_button(
        "Copy as markdown report",
        data=md_report.encode(),
        file_name=f"trade_thesis_{thesis.context_fingerprint}.md",
        mime="text/markdown",
        key="dl_thesis_md",
    )

    st.caption(
        "**Research / education only. Not personalised financial advice. "
        "Executing trades carries risk of material loss.**"
    )

    with st.expander("Context sent to the model"):
        st.json(ctx_obj.to_dict())


st.markdown("---")
st.caption(
    "Streamlit + Plotly + Three.js/WebGPU + Azure OpenAI. Pricing via Yahoo Finance "
    "(15-min delayed futures). Inventory via EIA dnav (keyless). AIS placeholder with "
    "aisstream.io upgrade path. Not investment advice."
)
