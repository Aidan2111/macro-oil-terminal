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

from data_ingestion import fetch_pricing_data, simulate_inventory, generate_ais_mock
from quantitative_models import (
    compute_spread_zscore,
    forecast_depletion,
    categorize_flag_states,
    backtest_zscore_meanreversion,
)
from webgpu_components import render_hero_banner, render_fleet_globe
from ai_insights import InsightContext, generate_commentary


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
    <style>
    .block-container { padding-top: 1.2rem; padding-bottom: 2rem; }
    .stTabs [data-baseweb="tab-list"] { gap: 2rem; }
    .big-metric { font-size: 1.1rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.sidebar.header("Controls")
z_threshold = st.sidebar.slider(
    "Z-Score Alert Threshold", min_value=0.5, max_value=5.0, value=3.0, step=0.1
)
floor_mbbl = st.sidebar.slider(
    "Inventory Floor (Million bbls)",
    min_value=100,
    max_value=700,
    value=300,
    step=25,
)
floor_bbls = float(floor_mbbl) * 1_000_000.0

depletion_weeks = st.sidebar.slider(
    "Depletion Rolling Window (Weeks)", min_value=2, max_value=26, value=4, step=1
)

st.sidebar.markdown("---")
st.sidebar.caption(
    "Pricing: yfinance (5y daily, BZ=F / CL=F). Inventory: simulated 2y. "
    "AIS: mock 500-vessel fleet."
)


# ---------------------------------------------------------------------------
# Data loading (cached)
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False, ttl=60 * 60)
def _load_pricing() -> pd.DataFrame:
    return fetch_pricing_data(years=5)


@st.cache_data(show_spinner=False, ttl=60 * 60)
def _load_inventory() -> pd.DataFrame:
    return simulate_inventory(years=2)


@st.cache_data(show_spinner=False, ttl=60 * 60)
def _load_ais() -> pd.DataFrame:
    return generate_ais_mock(n_vessels=500)


with st.spinner("Loading market data..."):
    prices = _load_pricing()
    inventory = _load_inventory()
    ais_df = _load_ais()

spread_df = compute_spread_zscore(prices, window=90)
depletion = forecast_depletion(
    inventory, floor_bbls=floor_bbls, lookback_weeks=depletion_weeks
)
ais_with_cat, ais_agg = categorize_flag_states(ais_df)


# ---------------------------------------------------------------------------
# Header + WebGPU hero
# ---------------------------------------------------------------------------
st.title("Inventory-Adjusted Spread Arbitrage & AIS Fleet Analytics")
st.caption(
    "Macro oil desk terminal — Brent/WTI dislocations, inventory drawdown velocity, "
    "and tanker fleet composition by regulatory regime."
)

render_hero_banner(height=220)


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab_arb, tab_depl, tab_fleet, tab_ai = st.tabs(
    ["Macro Arbitrage", "Depletion Forecast", "Fleet Analytics", "AI Insights"]
)


# ---- Tab 1 --------------------------------------------------------------
with tab_arb:
    st.subheader("Brent vs WTI — Price + Spread Z-Score")

    latest_spread = float(spread_df["Spread"].dropna().iloc[-1]) if not spread_df["Spread"].dropna().empty else 0.0
    latest_z = float(spread_df["Z_Score"].dropna().iloc[-1]) if not spread_df["Z_Score"].dropna().empty else 0.0
    z_flag = abs(latest_z) >= z_threshold

    col1, col2, col3 = st.columns(3)
    col1.metric("Latest Brent", f"${float(prices['Brent'].iloc[-1]):,.2f}")
    col2.metric("Latest WTI", f"${float(prices['WTI'].iloc[-1]):,.2f}")
    col3.metric(
        f"Spread Z (90d)",
        f"{latest_z:+.2f}",
        delta=f"{'ALERT' if z_flag else 'calm'}  |  spread ${latest_spread:,.2f}",
        delta_color="inverse" if z_flag else "normal",
    )

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        row_heights=[0.62, 0.38],
        subplot_titles=("Brent & WTI (USD / bbl)", "Brent-WTI Spread Z-Score (90d rolling)"),
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

    st.markdown("#### Historical Z-score mean-reversion backtest")
    st.caption(
        f"Enters at \u00b1{z_threshold:.1f}\u03c3, exits when |Z| < 0.2. "
        "10,000 bbl notional per trade. Toy strategy — excludes carry, "
        "slippage, and financing, so treat the PnL as a signal-quality "
        "indicator rather than a P&L forecast."
    )
    bt = backtest_zscore_meanreversion(
        spread_df, entry_z=z_threshold, exit_z=0.2, notional_bbls=10_000.0
    )
    bt_c1, bt_c2, bt_c3, bt_c4 = st.columns(4)
    bt_c1.metric("Trades", f"{bt['n_trades']:,}")
    bt_c2.metric(
        "Total PnL",
        f"${bt['total_pnl_usd']:,.0f}",
        delta=f"{bt['avg_pnl_per_bbl']:+.2f}/bbl avg",
    )
    bt_c3.metric("Win rate", f"{bt['win_rate']*100:.1f}%")
    bt_c4.metric("Avg hold", f"{bt['avg_days_held']:.1f} days")

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

        with st.expander("Trade blotter"):
            st.dataframe(bt["trades"], use_container_width=True)
            st.download_button(
                label="Download trade blotter (CSV)",
                data=bt["trades"].to_csv(index=False).encode(),
                file_name="zscore_backtest_trades.csv",
                mime="text/csv",
                key="download_blotter",
            )
    else:
        st.info(
            f"No trades triggered at \u00b1{z_threshold:.1f}\u03c3 on the "
            "historical window. Drop the threshold in the sidebar to see activity."
        )


# ---- Tab 2 --------------------------------------------------------------
with tab_depl:
    st.subheader("Inventory Depletion Forecaster")

    daily_rate = depletion["daily_depletion_bbls"]
    weekly_rate = depletion["weekly_depletion_bbls"]
    current_inv = depletion["current_inventory"]
    proj_date = depletion["projected_floor_date"]
    r2 = depletion["r_squared"]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Current Inventory", f"{current_inv/1e6:,.1f} Mbbl")
    c2.metric(
        "Daily Depletion",
        f"{daily_rate/1e3:+,.1f} kbbl/d",
        delta=f"{weekly_rate/1e6:+.2f} Mbbl/wk",
    )
    c3.metric(
        "Projected Floor Breach",
        proj_date.strftime("%Y-%m-%d") if proj_date is not None else "N/A",
    )
    c4.metric("Regression R\u00b2", f"{r2:.3f}")

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
    st.subheader("Global Tanker Fleet — Flag-State Exposure")

    category_colors = {
        "Jones Act / Domestic": "#2ca02c",
        "Shadow Risk": "#ff9f1c",
        "Sanctioned": "#d62728",
        "Other": "#8c8c8c",
    }

    headline = ais_agg[ais_agg["Category"].isin(category_colors.keys())].copy()
    headline = headline.set_index("Category").reindex(
        ["Jones Act / Domestic", "Shadow Risk", "Sanctioned", "Other"]
    ).fillna(0).reset_index()

    colors = [category_colors[c] for c in headline["Category"]]

    bar = go.Figure()
    bar.add_trace(
        go.Bar(
            x=headline["Category"],
            y=headline["Total_Cargo_Mbbl"],
            marker_color=colors,
            text=[f"{v:,.1f} Mbbl<br>{int(n)} vessels" for v, n in zip(headline["Total_Cargo_Mbbl"], headline["Vessel_Count"])],
            textposition="outside",
            hovertemplate="%{x}<br>%{y:,.1f} Mbbl<extra></extra>",
            name="Cargo Mbbl",
        )
    )
    bar.update_layout(
        height=440,
        template="plotly_dark",
        yaxis_title="Mbbl on Water",
        xaxis_title="",
        showlegend=False,
        margin=dict(l=40, r=20, t=30, b=40),
    )

    total_mbbl = float(ais_with_cat["Cargo_Volume_bbls"].sum() / 1e6)
    total_vessels = int(len(ais_with_cat))

    m1, m2, m3 = st.columns(3)
    m1.metric("Tankers Tracked", f"{total_vessels:,}")
    m2.metric("Total Cargo on Water", f"{total_mbbl:,.1f} Mbbl")
    jones = float(headline.loc[headline["Category"] == "Jones Act / Domestic", "Total_Cargo_Mbbl"].sum())
    m3.metric("Jones Act Share", f"{(jones / total_mbbl * 100.0) if total_mbbl else 0:.1f}%")

    st.plotly_chart(bar, use_container_width=True)

    st.markdown("#### 3D Globe — WebGPU Tanker Positions")
    st.caption(
        "Green = Jones Act/Domestic, Amber = Shadow Risk, Red = Sanctioned, Grey = Other. "
        "WebGPU is used when available (`navigator.gpu`); the scene falls back to WebGL otherwise."
    )
    render_fleet_globe(ais_with_cat, height=560)

    with st.expander("Vessel sample (first 25 rows)"):
        st.dataframe(
            ais_with_cat.head(25)[
                [
                    "Vessel_Name",
                    "MMSI",
                    "Flag_State",
                    "Destination",
                    "Cargo_Volume_bbls",
                    "Category",
                ]
            ],
            use_container_width=True,
        )
        st.download_button(
            label="Download full fleet roster (CSV)",
            data=ais_with_cat.to_csv(index=False).encode(),
            file_name="ais_fleet_roster.csv",
            mime="text/csv",
            key="download_fleet",
        )


# ---- Tab 4 — AI Insights -------------------------------------------------
with tab_ai:
    st.subheader("AI-Generated Market Commentary")

    endpoint_set = bool(os.environ.get("AZURE_OPENAI_ENDPOINT"))
    key_set = bool(os.environ.get("AZURE_OPENAI_KEY"))
    deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")

    status_cols = st.columns([1, 1, 1, 2])
    status_cols[0].metric("Endpoint", "set" if endpoint_set else "missing")
    status_cols[1].metric("API key", "set" if key_set else "missing")
    status_cols[2].metric("Deployment", deployment)
    status_cols[3].metric(
        "Mode",
        "Azure OpenAI" if (endpoint_set and key_set) else "Canned fallback",
    )

    jones_mbbl = float(
        headline.loc[headline["Category"] == "Jones Act / Domestic", "Total_Cargo_Mbbl"].sum()
    )
    shadow_mbbl = float(
        headline.loc[headline["Category"] == "Shadow Risk", "Total_Cargo_Mbbl"].sum()
    )
    sanctioned_mbbl = float(
        headline.loc[headline["Category"] == "Sanctioned", "Total_Cargo_Mbbl"].sum()
    )

    ctx = InsightContext(
        latest_brent=float(prices["Brent"].iloc[-1]),
        latest_wti=float(prices["WTI"].iloc[-1]),
        latest_spread=latest_spread,
        latest_z=latest_z,
        z_threshold=z_threshold,
        current_inventory_bbls=current_inv,
        floor_bbls=floor_bbls,
        daily_depletion_bbls=daily_rate,
        projected_floor_date=proj_date,
        r_squared=r2,
        jones_mbbl=jones_mbbl,
        shadow_mbbl=shadow_mbbl,
        sanctioned_mbbl=sanctioned_mbbl,
        total_fleet_mbbl=total_mbbl,
        total_vessels=total_vessels,
    )

    regenerate = st.button("Regenerate commentary", type="primary")
    cache_key = (
        round(latest_z, 2),
        round(current_inv / 1e6, 1),
        round(daily_rate / 1e3, 1),
        proj_date.strftime("%Y-%m-%d") if proj_date is not None else "",
        round(jones_mbbl, 1),
        round(shadow_mbbl, 1),
        round(sanctioned_mbbl, 1),
        round(z_threshold, 2),
        regenerate,
    )

    # Use session_state as a simple memo keyed by the tuple above to avoid
    # hashing the dataclass itself.
    if (
        "_ai_key" not in st.session_state
        or st.session_state["_ai_key"] != cache_key
    ):
        with st.spinner("Asking Azure OpenAI..."):
            st.session_state["_ai_commentary"] = generate_commentary(ctx)
            st.session_state["_ai_key"] = cache_key
    commentary = st.session_state["_ai_commentary"]

    st.markdown(commentary)

    with st.expander("Snapshot sent to the model"):
        st.code(ctx.prompt_snapshot(), language="text")


st.markdown("---")
st.caption(
    "Streamlit + Plotly + Three.js/WebGPU + Azure OpenAI. Pricing via yfinance, "
    "inventory simulated, AIS mocked. Not investment advice."
)
