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
    fetch_cftc_positioning,
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
from cointegration import engle_granger
from crack_spread import compute_crack
from auth import clear_cached_user, current_user

# UIP-T0: language pass — every UI string that names a finance concept
# pulls from ``language.TERMS`` so the rename stays in one place.
from language import (
    TERMS as _T,
    describe_stretch as _describe_stretch,
    describe_confidence as _describe_confidence,
    describe_correlation as _describe_correlation,
    describe_stance as _describe_stance,
)

# UIP-T1: theme palette + CSS injection (idempotent per session).
# UIP-T5: apply_theme + axis-label + money-hover helpers routed through
# the same module so every Plotly call site has one import surface.
from theme import (
    SYMBOL_DISPLAY_NAMES,
    _resolve_build_version,
    apply_theme,
    format_money_hover,  # noqa: F401 — available for future hover refinements
    inject_css,
    pretty_axis_label,
    render_catalyst_countdown,
    render_checklist,
    render_conviction_bar,
    render_empty,
    render_error,
    render_footer,
    render_loading_status,
    render_onboarding,
    render_stance_pill,
    render_ticker_strip,
    render_tier_card,
)

_AI_ACTIVE = _obs_configure()


# ---------------------------------------------------------------------------
# Page config + sidebar
# ---------------------------------------------------------------------------
# UIP-T9: page_icon tries the favicon.ico path first. Streamlit 1.42
# accepts a path-like string; if the version in use doesn't, fall back
# to a PIL Image so the icon still renders. The emoji default is a last
# resort so boot never breaks in a stripped-down environment.
_PAGE_ICON = "static/favicon.ico"
try:  # best-effort: some Streamlit versions only accept PIL.Image for files.
    from PIL import Image as _PILImage
    _PAGE_ICON = _PILImage.open("static/favicon.ico")
except Exception:
    pass

st.set_page_config(
    page_title="Macro Oil Terminal",
    page_icon=_PAGE_ICON,
    layout="wide",
    menu_items={
        "Get help": "https://github.com/Aidan2111/macro-oil-terminal",
        "Report a bug": "https://github.com/Aidan2111/macro-oil-terminal/issues",
    },
)
inject_css()
# UIP-T8: first-visit onboarding toasts — self-guarded on localStorage,
# no-op on repeat visits. Lives here so the component mounts before any
# downstream render writes to the DOM.
render_onboarding()

# P1.1 auth boot check — surface a banner if misconfigured, but never crash
# in dev. UIP-T9: gate the banner behind non-prod (or an explicit opt-in)
# so production deploys stay quiet when the expected auth env is wired up.
_is_prod = os.environ.get("STREAMLIT_ENV") == "prod"
_auth_banner_in_prod = os.environ.get("AUTH_BANNER_IN_PROD") == "true"
if not _is_prod or _auth_banner_in_prod:
    try:
        from auth import boot_check
        boot_check()
    except Exception as _auth_boot_err:  # AuthNotConfigured or import-time issue
        st.warning(
            f"Auth not fully configured: {_auth_boot_err}. "
            "Public research remains available; execute actions are disabled."
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
    _T["stretch_alert"] + (" (σ, Z-score)" if show_advanced else ""),
    min_value=0.5,
    max_value=5.0,
    value=_q_default("z", 0.5, 5.0, 3.0),
    step=0.1,
    help=(
        "How far the Brent-WTI spread has to drift from its normal range "
        "before we flag it. Measured in standard deviations (Z-score). "
        "3.0σ ≈ extreme stretch, triggers once every few years on average."
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


@st.cache_data(show_spinner=False, ttl=60 * 3)
def _health_cached():
    from providers.health import providers_health
    return providers_health()


with st.sidebar.expander("Data sources (health)"):
    try:
        rows = _health_cached()
    except Exception as exc:
        rows = []
        st.caption(f":red[health check failed: {exc!r}]")
    for r in rows:
        ok = r.get("ok")
        if ok is True:
            icon = "🟢"
        elif ok is False:
            icon = "🔴"
        else:
            icon = "⚪"
        lat = r.get("latency_ms", 0)
        note = r.get("note") or ""
        st.caption(f"{icon} **{r['label']}** — {lat} ms · {note}")

alert_on = st.sidebar.toggle(
    "Email me when the spread gets stretched",
    value=False,
    help="Requires ALERT_SMTP_* env vars. Without them, the UI will show the "
    "exact message that would have been sent. (Technically a Z-score breach.)",
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


@st.cache_data(show_spinner=False, ttl=60 * 60 * 12)  # CFTC publishes weekly (Friday 3:30 ET)
def _load_cftc_cached():
    try:
        return fetch_cftc_positioning()
    except Exception:
        return None


# --- Defensive fetch: surface clear error states instead of fake data ---
# UIP-T7: every top-level data fetch is wrapped + routed through
# ``render_error`` so users never see a raw traceback. Each branch that
# fails hard calls ``st.stop()`` after rendering the styled error card
# so downstream rendering doesn't blow up on a missing frame.
pricing_res: PricingResult | None = None
inventory_res: InventoryResult | None = None
ais_res: AISResult | None = None

with render_loading_status("Loading live market data\u2026"):
    try:
        pricing_res = _load_pricing_cached()
    except PricingUnavailable as exc:
        render_error(
            "Pricing feed unavailable — yfinance returned no data. "
            f"{type(exc).__name__}: {exc}",
            retry_fn=lambda: _load_pricing_cached.clear(),
        )
        st.stop()
    except Exception as exc:
        render_error(
            f"Couldn't reach the pricing feed right now. {type(exc).__name__}",
            retry_fn=lambda: _load_pricing_cached.clear(),
        )
        st.stop()

    try:
        inventory_res = _load_inventory_cached()
    except InventoryUnavailable as exc:
        render_error(
            "Inventory feed unavailable — EIA dnav and FRED both failed. "
            f"{type(exc).__name__}: {exc}",
            retry_fn=lambda: _load_inventory_cached.clear(),
        )
        st.stop()
    except Exception as exc:
        render_error(
            f"Couldn't reach the inventory feed right now. {type(exc).__name__}",
            retry_fn=lambda: _load_inventory_cached.clear(),
        )
        st.stop()

    try:
        ais_res = _load_ais_cached()
    except Exception as exc:
        render_error(
            f"Couldn't reach the AIS fleet feed right now. {type(exc).__name__}",
            retry_fn=lambda: _load_ais_cached.clear(),
        )
        st.stop()

    # CFTC positioning — soft failure: show a warning but keep the dashboard usable
    cftc_res = _load_cftc_cached()

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


@st.cache_data(show_spinner=False, ttl=60 * 60)
def _cointegration_cached(price_fingerprint: str) -> dict:
    """Engle-Granger on the full 5y Brent/WTI frame (cached hourly)."""
    try:
        res = engle_granger(prices["Brent"], prices["WTI"])
        return res.to_dict()
    except Exception as exc:
        return {
            "verdict": "inconclusive",
            "p_value": float("nan"),
            "adf_stat": float("nan"),
            "hedge_ratio": float("nan"),
            "alpha": float("nan"),
            "half_life_days": None,
            "is_cointegrated": False,
            "is_weak": False,
            "n_obs": 0,
            "window": "full",
            "error": repr(exc)[:160],
        }


@st.cache_data(show_spinner=False, ttl=60 * 60)
def _crack_cached(price_fingerprint: str) -> dict:
    """3-2-1 crack spread + 30d correlation vs Brent-WTI (cached hourly)."""
    out = compute_crack(brent_wti_daily=prices)
    return {
        "ok": bool(out.ok),
        "latest_crack_usd": float(out.latest_crack_usd),
        "latest_rbob": float(out.latest_rbob_usd_per_gal),
        "latest_ho": float(out.latest_ho_usd_per_gal),
        "latest_wti": float(out.latest_wti_usd),
        "corr_30d_vs_brent_wti": float(out.corr_30d_vs_brent_wti),
        "note": out.note,
    }


def _fp(df: pd.DataFrame) -> str:
    return f"{len(df)}-{df.index[-1] if len(df) else 'empty'}"


spread_df = _spread_cached(_fp(prices), 90)
depletion = _depletion_cached(_fp(inventory), floor_bbls, depletion_weeks)
ais_with_cat, ais_agg = categorize_flag_states(ais_df)
coint_info = _cointegration_cached(_fp(prices))
crack_info = _crack_cached(_fp(prices))

# Backtest summary — promoted above the tabs so the hero band can use it
# to build the ThesisContext before the first tab renders. Tab 1 still
# displays the full backtest detail panel below; this is the same call.
bt = _backtest_cached(
    _fp(spread_df), float(z_threshold), 0.2,
    float(slippage_per_bbl), float(commission_per_trade),
)


# ---------------------------------------------------------------------------
# Header + WebGPU hero
# ---------------------------------------------------------------------------
st.title("Inventory-Adjusted Spread Arbitrage & AIS Fleet Analytics")
st.caption(
    f"Macro oil desk terminal — Brent/WTI {_T['stretch'].lower()}, inventory "
    "drawdown velocity, and tanker fleet composition by regulatory regime."
)


@st.cache_data(show_spinner=False, ttl=45)
def _load_intraday_cached(refresh_token: int):
    """Cached intraday pull — token gives us a per-minute bucket."""
    try:
        return fetch_pricing_intraday_data(interval="1m", period="2d")
    except Exception:
        return None


def _spark_series_tail(series, n: int = 50) -> list[float]:
    """Convert a pandas Series tail to a plain list of floats for the
    inline-SVG sparkline. Drops NaNs so a partial feed doesn't torpedo
    the min-max scaling inside ``theme._build_sparkline_polyline``.
    """
    try:
        clean = series.dropna().tail(n)
        return [float(v) for v in clean.tolist()]
    except Exception:
        return []


@st.fragment(run_every=60 if live_mode else None)
def _ticker_strip() -> None:
    """Bloomberg-tape ticker strip — autorefreshes every 60s in live
    mode. Body delegates to ``theme.render_ticker_strip`` so the HTML
    + inline SVG rendering stays single-source (UIP-T4). No Plotly —
    the strip is pure markdown + SVG so the per-render cost is
    sub-millisecond and the fragment can tick without a chart re-mount.
    """
    import time as _t
    bucket = int(_t.time() // 60)
    intraday = _load_intraday_cached(bucket) if live_mode else None

    if intraday is not None and not intraday.frame.empty:
        brent_tail = intraday.frame["Brent"].dropna()
        wti_tail = intraday.frame["WTI"].dropna()
    else:
        brent_tail = prices["Brent"].dropna()
        wti_tail = prices["WTI"].dropna()

    def _delta(tail) -> tuple[float, float, float]:
        """Return (latest_price, delta_abs, delta_pct) vs the window's
        first observation. Falls back to zeros on empty tails."""
        if tail is None or tail.empty:
            return 0.0, 0.0, 0.0
        latest = float(tail.iloc[-1])
        first = float(tail.iloc[0])
        d_abs = latest - first
        d_pct = (d_abs / first * 100.0) if first else 0.0
        return latest, d_abs, d_pct

    brent_latest, brent_d_abs, brent_d_pct = _delta(brent_tail.tail(120))
    wti_latest, wti_d_abs, wti_d_pct = _delta(wti_tail.tail(120))

    spread_tail = (brent_tail - wti_tail).dropna().tail(120)
    spread_latest, spread_d_abs, spread_d_pct = _delta(spread_tail)

    inv_series = (inventory["Total_Inventory_bbls"] / 1e6).dropna()
    inv_latest, inv_d_abs, inv_d_pct = _delta(inv_series.tail(52))

    quotes = [
        {
            "symbol": "BZ=F",
            "display_name": SYMBOL_DISPLAY_NAMES.get("BZ=F", "Brent"),
            "price": brent_latest,
            "delta_abs": brent_d_abs,
            "delta_pct": brent_d_pct,
            "sparkline_values": _spark_series_tail(brent_tail),
        },
        {
            "symbol": "CL=F",
            "display_name": SYMBOL_DISPLAY_NAMES.get("CL=F", "WTI"),
            "price": wti_latest,
            "delta_abs": wti_d_abs,
            "delta_pct": wti_d_pct,
            "sparkline_values": _spark_series_tail(wti_tail),
        },
        {
            "symbol": "SPREAD",
            "display_name": "Spread",
            "price": spread_latest,
            "delta_abs": spread_d_abs,
            "delta_pct": spread_d_pct,
            "sparkline_values": _spark_series_tail(spread_tail),
        },
        {
            "symbol": "INV",
            "display_name": "Inventory Mbbl",
            "price": inv_latest,
            "delta_abs": inv_d_abs,
            "delta_pct": inv_d_pct,
            "sparkline_values": _spark_series_tail(inv_series),
        },
    ]

    render_ticker_strip(quotes)

# --- Desk-style risk summary pinned above the tabs -----------------------
try:
    _latest_brent = float(prices["Brent"].iloc[-1])
    _latest_wti = float(prices["WTI"].iloc[-1])
    _latest_spread = _latest_brent - _latest_wti
    _z = float(spread_df["Z_Score"].dropna().iloc[-1]) if spread_df["Z_Score"].notna().any() else 0.0
    _alert = abs(_z) >= z_threshold
    _last_thesis = st.session_state.get("_thesis_obj")
    _stance = (_last_thesis.raw.get("stance") if _last_thesis else "—")
    _stance_display = {
        "long_spread": "BUY SPREAD",
        "short_spread": "SELL SPREAD",
        "flat": "WAIT",
        "—": "trade idea not yet generated",
    }.get(_stance, str(_stance))
    _conf = float(_last_thesis.raw.get("conviction_0_to_10", 0.0)) if _last_thesis else 0.0

    # Countdown to the next EIA Wednesday 10:30 ET (14:30 UTC).
    _now = pd.Timestamp.utcnow().tz_localize(None)
    _days_ahead = (2 - _now.weekday()) % 7
    if _days_ahead == 0 and _now.hour >= 15:
        _days_ahead = 7
    _next_eia = (_now + pd.Timedelta(days=_days_ahead)).replace(hour=14, minute=30, second=0, microsecond=0)
    _delta = _next_eia - _now
    _h_left = int(_delta.total_seconds() // 3600)
    _m_left = int((_delta.total_seconds() % 3600) // 60)

    _pill_bg = "#e74c3c" if _alert else "#1b2838"
    _stance_bg = {
        "BUY SPREAD": "#2ecc71",
        "SELL SPREAD": "#e74c3c",
        "WAIT": "#95a5a6",
    }.get(_stance_display, "#444a54")
    st.markdown(
        f"""
        <div style="display:flex; gap:14px; align-items:center;
                    padding:8px 14px; margin-bottom:10px;
                    border-radius:8px; background:#111821;
                    border-left:4px solid {_pill_bg};
                    font-family: ui-monospace, Menlo, monospace;
                    font-size:0.92rem; color:#e7ecf3;">
          <span style="background:{_stance_bg}; color:#0b0f14;
                       padding:2px 10px; border-radius:4px; font-weight:700;">
            {_stance_display}
          </span>
          <span>confidence <b>{_conf:.1f}/10</b></span>
          <span>·  Brent <b>${_latest_brent:,.2f}</b></span>
          <span>WTI <b>${_latest_wti:,.2f}</b></span>
          <span>spread <b>{_latest_spread:+.2f}</b></span>
          <span>stretch <b>{_z:+.2f}</b>{' ⚠' if _alert else ''}</span>
          <span style="margin-left:auto; opacity:0.85;">
            next EIA in <b>{_h_left}h {_m_left}m</b>
          </span>
        </div>
        """,
        unsafe_allow_html=True,
    )
except Exception:
    pass


# --- Global keyboard shortcuts (1/2/3/4 tabs, R regen, / filter, ? help) --
st.markdown(
    """
    <script>
    (function () {
      if (window.__oilTermHotkeysBound) return;
      window.__oilTermHotkeysBound = true;
      const root = () => window.parent.document;
      function clickTab(i) {
        const tabs = root().querySelectorAll('button[role="tab"]');
        if (tabs && tabs.length > i) tabs[i].click();
      }
      function clickByText(text) {
        const btns = root().querySelectorAll('button');
        for (const b of btns) { if (b.innerText.trim() === text) { b.click(); return true; } }
        return false;
      }
      function toggleCheatsheet() {
        const d = root().getElementById('oil-cheatsheet');
        if (!d) return;
        d.style.display = d.style.display === 'none' ? 'block' : 'none';
      }
      const handler = (ev) => {
        if (ev.target && ['INPUT','TEXTAREA','SELECT'].includes(ev.target.tagName)) return;
        if (ev.metaKey || ev.ctrlKey || ev.altKey) return;
        switch (ev.key) {
          case '1': case '2': case '3':
            clickTab(parseInt(ev.key, 10) - 1); ev.preventDefault(); break;
          case 'r': case 'R':
            clickByText('Regenerate'); break;
          case '?':
            toggleCheatsheet(); ev.preventDefault(); break;
        }
      };
      root().addEventListener('keydown', handler, true);
    })();
    </script>
    <div id="oil-cheatsheet" style="display:none; position:fixed; top:80px; right:24px;
         z-index: 9999; background:#111821; color:#e7ecf3; padding:14px 18px;
         border:1px solid #2a3442; border-radius:8px;
         font-family: ui-monospace, Menlo, monospace; font-size:0.88rem; line-height:1.55;
         box-shadow: 0 8px 24px rgba(0,0,0,0.45);">
      <b>Keyboard shortcuts</b><br/>
      <b>1 2 3</b> — switch tabs<br/>
      <b>R</b> — regenerate trade idea<br/>
      <b>?</b> — toggle this cheat sheet
    </div>
    """,
    unsafe_allow_html=True,
)


render_hero_banner(height=220)


# ---------------------------------------------------------------------------
# Hero thesis band (Task 6a/b) — rendered above the tabs on every page.
# Uses trade_thesis.decorate_thesis_for_execution(thesis, ctx) to build
# the three instrument tiers + the pre-trade checklist. The audit log for
# checklist ticks is appended to data/trade_executions.jsonl (gitignored).
# ---------------------------------------------------------------------------
_HERO_BROKER_LINKS = {
    "IBKR": "https://www.ibkr.com/research/stocks",
    "Schwab": "https://www.schwab.com/research",
    "Fidelity": "https://www.fidelity.com/research",
    "TastyTrade": "https://tastytrade.com/",
}
_HERO_DISCLAIMER = (
    "Research & education only. Not personalized financial advice. "
    "Futures and options can lose more than the initial investment. "
    "Past performance does not predict future results. Consult a licensed "
    "advisor before executing. Data may be 15-min delayed."
)


class _TierPlaceholder:
    """Lightweight stand-in for an ``Instrument`` used when the hero has
    no tradeable stance but still wants three tier-card sentinels on
    the DOM. Carries only the fields ``theme.render_tier_card`` reads.
    """

    def __init__(self, tier: int, name: str, symbol: str | None) -> None:
        self.tier = tier
        self.name = name
        self.symbol = symbol
        self.legs = (
            [s.strip() for s in symbol.split("/") if s.strip()]
            if symbol and "/" in symbol
            else ([symbol] if symbol else [])
        )
        self.size_usd = None


class _ChecklistView:
    """Lightweight shim passed into ``theme.render_checklist`` so the
    styled list reflects the live session_state tick without mutating
    the original ``trade_thesis.ChecklistItem`` objects (UIP-T3).
    """

    def __init__(self, key: str, prompt: str, auto_check) -> None:
        self.key = key
        self.prompt = prompt
        self.auto_check = auto_check


def _hero_audit_log(thesis_fingerprint: str, checklist_key: str, checked_by_user: bool, auto_check_value) -> None:
    """Append one checklist-tick row to data/trade_executions.jsonl.

    Failures are swallowed — the UI must never raise from a checkbox click.
    """
    try:
        import json as _json
        import pathlib as _pl
        from datetime import datetime as _dt, timezone as _tz
        path = _pl.Path("data/trade_executions.jsonl")
        path.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "ts_utc": _dt.now(_tz.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "thesis_fingerprint": thesis_fingerprint,
            "checklist_key": checklist_key,
            "checked_by_user": bool(checked_by_user),
            "auto_check_value": auto_check_value,
        }
        with path.open("a") as fh:
            fh.write(_json.dumps(row, default=str) + "\n")
    except Exception:
        pass  # log-but-continue; never raise


def _hero_stance_label(stance: str) -> tuple[str, str]:
    """Return (display_label, bg_color) for a stance string.

    Display labels come from ``language.TERMS`` so the language pass stays
    in one place. The pill uses an uppercased display form.
    """
    mapping = {
        "long_spread":  (_T["long_spread"].upper(),  "#2ecc71"),
        "short_spread": (_T["short_spread"].upper(), "#e74c3c"),
        "flat":         (_T["flat"].upper(),         "#95a5a6"),
    }
    return mapping.get(stance, (_T["flat"].upper(), "#95a5a6"))


def _render_thesis_mini(decorated) -> None:
    """Render the stance pill / conviction bar / horizon / 2-line summary.

    UIP-T2 replaced the inline stance pill + confidence text with
    ``theme.render_stance_pill`` + ``theme.render_conviction_bar`` so
    both widgets pick up the frozen palette + classes declared in
    ``theme._CSS``. The horizon byline and summary caption are still
    rendered inline — they're low-churn and T3 will rewire them
    alongside the countdown + checklist pass.
    """
    raw = decorated.raw or {}
    stance = raw.get("stance", "flat")
    conv_int = int(round(float(raw.get("conviction_0_to_10", 0.0))))
    horizon = int(raw.get("time_horizon_days", 0))
    summary = raw.get("thesis_summary", "")

    # Stance stored lowercase in the JSON schema; the new helper accepts
    # either case but we normalize here for clarity.
    render_stance_pill(stance.upper() if isinstance(stance, str) else "FLAT")
    render_conviction_bar(conv_int, stance.upper() if isinstance(stance, str) else "FLAT")

    st.markdown(
        f'<div class="caption" style="color: var(--text-secondary); '
        f'margin-top: 4px;">horizon <b>{horizon} days</b></div>',
        unsafe_allow_html=True,
    )
    if summary:
        # Two-line summary — cap at ~280 chars to keep the band compact.
        short = summary if len(summary) <= 280 else summary[:277] + "..."
        st.caption(short)


def _render_portfolio_input() -> float:
    """Render the portfolio-sizing number_input and return its current value."""
    return float(st.number_input(
        "Portfolio (USD)",
        min_value=0, value=100_000, step=1_000,
        key="hero_portfolio_usd",
        help="Dollar sizing in the tiles below is percent × this portfolio value.",
    ))


def _render_tier_tile(col, inst, portfolio_usd: float, stance: str = "flat") -> None:
    """Render a single instrument tile into the given column.

    UIP-T2 replaced the inline bespoke ``col.markdown(...)`` block with
    ``theme.render_tier_card``. To keep the dollar-sizing + broker links
    visible (they were live under the old tile) we emit them as compact
    captions below the new card; the P1.1.5 auth-gated execute stub
    still renders below the card, unchanged. The stub's "below the card"
    placement is a pragmatic compromise — moving it inside the card
    would require refactoring ``render_tier_card`` to accept a callable
    slot, which is out of scope for T2.
    """
    pct = float(getattr(inst, "suggested_size_pct", 0.0) or 0.0)
    dollars = portfolio_usd * pct / 100.0
    # Attach size_usd on the instrument so render_tier_card's P&L preview
    # stub can render a dollar number instead of "TBD". This is a live
    # attribute set per-render — cheap, and P1.2 will replace it with a
    # real broker-side computation.
    try:
        inst.size_usd = float(dollars)
    except Exception:
        pass
    # Same for legs — derive from symbol if the Instrument doesn't carry
    # an explicit list. "USO/BNO" / "CL=F/BZ=F" split cleanly on "/".
    if not getattr(inst, "legs", None):
        sym = getattr(inst, "symbol", None) or ""
        if "/" in sym:
            inst.legs = [s.strip() for s in sym.split("/") if s.strip()]
        elif sym:
            inst.legs = [sym]

    with col:
        render_tier_card(inst, f"tier{getattr(inst, 'tier', 0)}", stance)
        # Preserve the sizing byline + broker links — this context lived
        # under the old tile and users rely on it. The execute stub from
        # P1.1.5 renders immediately after so the auth gate still feels
        # attached to this column.
        broker_bits = " · ".join(
            f'<a href="{url}" target="_blank" rel="noopener noreferrer" '
            f'style="color:var(--primary); text-decoration:none;">{name}</a>'
            for name, url in _HERO_BROKER_LINKS.items()
        )
        st.markdown(
            f'<div class="caption" style="color: var(--text-secondary); '
            f'margin-top: 6px;">size <b>{pct:.1f}%</b> &middot; '
            f'<b>${dollars:,.0f}</b></div>'
            f'<div class="caption" style="margin-top: 2px;">{broker_bits}</div>',
            unsafe_allow_html=True,
        )
        if getattr(inst, "tier", None) == 2:
            st.caption(
                "Defined-risk alt: ATM \u00b1 2 strikes on BNO/USO, 30\u201360 DTE, OI > 100."
            )
        # P1.1.5 — auth-gated execute stub. P1.3 swaps the caption for a real
        # order-placement button wired to the Alpaca broker via user.sub.
        _render_execute_button_stub(f"tier{getattr(inst, 'tier', 0)}")


def _render_checklist(checklist, thesis_fingerprint: str) -> None:
    """Render the 5-item pre-trade checklist.

    UIP-T3 swaps the plain-Streamlit checkboxes for the styled
    ``theme.render_checklist`` list (Lucide SVG icons + data-testid
    hook). The interactive toggles still need to live somewhere so the
    user can tick ``stop_in_place`` / ``half_life_ack`` /
    ``no_conflicting_recent_thesis`` — we stash them inside a collapsed
    ``st.expander`` below the styled list so the visible hero stays
    clean. Current ``auto_check`` state is reflected through the
    session_state mirror that the expander checkboxes write to.
    """
    with st.container(border=True):
        st.markdown("**Pre-trade checklist**")

        # Mirror any user-toggle state from session_state back onto the
        # ChecklistItem objects so the styled row reflects the current
        # tick. ``auto_check`` stays authoritative when the context
        # already resolved it (True/False); ``None`` items defer to the
        # user toggle.
        mirrored = []
        for item in checklist:
            session_key = f"hero_check_{item.key}"
            user_ticked = bool(st.session_state.get(session_key, False))
            effective_auto = item.auto_check
            if effective_auto is None:
                effective_auto = user_ticked
            # Build a lightweight shim so we don't mutate the original.
            mirrored.append(_ChecklistView(
                key=item.key, prompt=item.prompt, auto_check=effective_auto,
            ))

        render_checklist(mirrored)

        with st.expander("Toggle checklist items", expanded=False):
            for item in checklist:
                auto_val = item.auto_check
                default = bool(auto_val) if auto_val is not None else False
                st.checkbox(
                    item.prompt,
                    value=default,
                    key=f"hero_check_{item.key}",
                    on_change=_hero_audit_log,
                    args=(thesis_fingerprint, item.key, True, auto_val),
                    help=("Auto-checked from today's data." if auto_val is not None
                          else "User must tick before executing."),
                )


def _render_header_signin() -> None:
    """Render a compact sign-in / sign-out row at the top of the hero band.

    Emits an empty sentinel ``<div data-testid="...">`` immediately before
    the Streamlit button/caption so Playwright can locate the control
    (Streamlit widgets don't accept arbitrary ``data-testid`` attributes).

    The real ``st.login("google")`` / ``st.logout()`` wiring lands in
    Task 6 — here we use ``getattr(...)`` fallbacks so the app keeps
    rendering on older Streamlit versions and the button press never
    crashes the page (per the design spec's "Sign-in is temporarily
    unavailable" fallback).
    """
    user = current_user()
    # Right-align the header row so it doesn't crowd the stance pill below.
    _spacer, col = st.columns([6, 2])
    if user is not None:
        col.markdown(
            f'<div data-testid="signed-in-as" '
            f'style="text-align:right; color:#c7cdd4; font-size:0.82rem;">'
            f"Signed in as {user.email}</div>",
            unsafe_allow_html=True,
        )
        if col.button("Sign out", key="auth-signout-btn"):
            try:
                clear_cached_user()
                getattr(st, "logout", lambda: None)()
                st.rerun()
            except Exception as exc:  # pragma: no cover - defensive
                st.warning(f"Sign-out failed: {exc}")
        return

    col.markdown(
        '<div data-testid="signin-button" style="text-align:right;"></div>',
        unsafe_allow_html=True,
    )
    if col.button(
        "Sign in with Google",
        key="auth-signin-btn",
        type="primary",
    ):
        try:
            getattr(st, "login", lambda *_: None)("google")
        except Exception:  # pragma: no cover - real login wired in Task 6/7
            st.info(
                "Sign-in is temporarily unavailable. "
                "Public research remains available below."
            )


def _render_execute_button_stub(tier_key) -> None:
    """Placeholder for the P1.3 broker-wired execute button.

    Inline auth gating (vs. ``@requires_auth``) avoids stacking three
    login prompts when the hero band renders three tier tiles on an
    unauthed view. The decorator is still the right tool for
    route-level gates like the P1.6 onboarding wizard — just not here.
    """
    if current_user() is None:
        st.caption("Sign in to execute this tier.")
        return
    st.caption(f"\u25b8 Execute {tier_key} (auth ready \u2014 P1.3 wires broker)")


def _render_hero_band(thesis, ctx, decorated) -> None:
    """Render the hero thesis band above the tabs (every page, every tab).

    The outermost element is a ``<div data-testid="hero-band">`` emitted
    via ``st.markdown(unsafe_allow_html=True)``. DOMPurify preserves the
    ``data-testid`` attribute so the Playwright role-based locator in
    ``tests/e2e/test_hero_band.py`` resolves it. The same markdown block
    includes a visible header stripe so the element has non-zero bounding
    box dimensions (a requirement for Playwright ``to_be_visible``).
    """
    # The visible wrapper stripe — emitted as a single self-contained HTML
    # block so Streamlit doesn't close the div prematurely.
    stance_for_header = "flat"
    if decorated is not None:
        stance_for_header = (decorated.raw or {}).get("stance", "flat")
    header_label, header_color = _hero_stance_label(stance_for_header)
    st.markdown(
        f'<div data-testid="hero-band" '
        f'style="border-left:4px solid {header_color}; '
        f'background:#111821; padding:10px 14px; margin:6px 0 10px 0; '
        f'border-radius:6px; color:#e7ecf3;">'
        f'<span style="background:{header_color}; color:#0b0f14; '
        f'padding:4px 10px; border-radius:4px; font-weight:700; '
        f'letter-spacing:1px; font-size:0.85rem;">HERO &middot; {header_label}</span>'
        f'<span style="margin-left:10px; color:#c7cdd4; font-size:0.85rem;">'
        f"Today's {_T['trade_idea'].lower()}, sizing, and pre-trade checklist.</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # Body — rendered inside a regular container immediately below the
    # wrapper div. The wrapper div above is what the e2e test asserts on;
    # the container below holds the interactive widgets.
    with st.container(key="hero-band-body"):
        # Task 5 (P1.1.5): sign-in / sign-out header row sits at the top
        # of the hero body so the auth surface is always first-paint.
        _render_header_signin()
        if thesis is None or decorated is None:
            # Initial load before the LLM call fires. Show a placeholder flat
            # hero so the Playwright test's hero-band selector still resolves.
            _placeholder_label = _T["flat"].upper()
            st.markdown(
                f'<span style="background:#95a5a6; color:#0b0f14; padding:6px 14px; '
                f'border-radius:6px; font-weight:700;">{_placeholder_label}</span>'
                f'<span style="margin-left:10px; color:#c7cdd4;">'
                f'{_T["trade_idea"]} pending\u2026</span>',
                unsafe_allow_html=True,
            )
            # UIP-T3: emit the countdown sentinel even on the pending
            # placeholder so the e2e selector resolves during first paint.
            _placeholder_hrs = getattr(ctx, "hours_to_next_eia", None) if ctx is not None else None
            render_catalyst_countdown(_placeholder_hrs)
            _render_portfolio_input()
            st.caption(_HERO_DISCLAIMER)
            return

        raw = decorated.raw or {}
        _render_thesis_mini(decorated)

        # UIP-T3: EIA catalyst countdown sits immediately under the stance
        # pill + conviction bar so the "when does this thesis expire"
        # signal lives next to the stance itself.
        _hrs_to_eia = getattr(ctx, "hours_to_next_eia", None) if ctx is not None else None
        render_catalyst_countdown(_hrs_to_eia)

        portfolio_usd = _render_portfolio_input()

        materiality_flat = (
            raw.get("stance") == "flat" and not (decorated.instruments or [])
        )
        _stance_for_card = str(raw.get("stance", "flat")).upper()
        if materiality_flat:
            # UIP-T7: surface a styled empty-state card so the "no trade
            # today" branch feels intentional rather than empty. The three
            # placeholder tier cards still render below so the skeleton
            # + sentinel selectors stay consistent.
            render_empty(
                "inbox",
                "No actionable trade idea today. Monitor the Spread "
                "Stretch gauge above.",
            )
            # UIP-T2: render three placeholder tier cards even on the
            # flat path so the hero keeps a consistent skeleton and the
            # sentinel selectors always resolve. Cards surface the
            # "waiting for a tradeable stretch" story rather than
            # actual sizing numbers.
            _placeholder_instruments = [
                _TierPlaceholder(tier=1, name="Paper", symbol=None),
                _TierPlaceholder(tier=2, name="USO/BNO ETF pair", symbol="USO/BNO"),
                _TierPlaceholder(tier=3, name="CL=F / BZ=F futures", symbol="CL=F/BZ=F"),
            ]
            cols = st.columns(3)
            for col, inst in zip(cols, _placeholder_instruments):
                with col:
                    render_tier_card(inst, f"tier{inst.tier}", _stance_for_card)
        else:
            cols = st.columns(3)
            for col, inst in zip(cols, decorated.instruments):
                _render_tier_tile(col, inst, portfolio_usd, _stance_for_card)
            _render_checklist(
                decorated.checklist or [],
                decorated.context_fingerprint or "",
            )

        st.caption(_HERO_DISCLAIMER)


# UIP-T4: Bloomberg-tape ticker strip renders at the very top of the page,
# above the hero band. The fragment body assembles a list of quote dicts
# from the same intraday / daily sources the old Plotly-tile strip used,
# then delegates to ``theme.render_ticker_strip`` for the inline-SVG render.
_ticker_strip()


# Build a pre-tabs thesis + decoration so the hero band can render above
# the tabs on first load. We re-use the cached thesis in session state if
# present (e.g. after the Tab-1 internals expander regenerates it), so we
# don't double-call the LLM.
try:
    from trade_thesis import decorate_thesis_for_execution as _decorate
    from thesis_context import build_context as _build_ctx
    from trade_thesis import generate_thesis as _gen_thesis

    _hero_ctx = _build_ctx(
        pricing_res=pricing_res,
        inventory_res=inventory_res,
        spread_df=spread_df,
        backtest=bt,
        depletion=depletion,
        ais_agg=ais_agg,
        ais_with_cat=ais_with_cat,
        z_threshold=z_threshold,
        floor_bbls=floor_bbls,
        coint_info=coint_info,
        crack_info=crack_info,
    )
    _hero_ctx.fleet_source = ais_res.source

    _hero_thesis = st.session_state.get("_thesis_obj")
    if _hero_thesis is None:
        _hero_thesis = _gen_thesis(_hero_ctx, mode="fast")
        st.session_state["_thesis_obj"] = _hero_thesis
        st.session_state["_thesis_last_generated_at"] = (
            pd.Timestamp.utcnow().strftime("%Y-%m-%d %H:%M:%SZ")
        )
    _hero_decorated = _decorate(_hero_thesis, _hero_ctx)
    _render_hero_band(_hero_thesis, _hero_ctx, _hero_decorated)
except Exception as _hero_exc:
    # Never let the hero band break the rest of the app. Emit a compact
    # but still-visible hero wrapper so the e2e selector still resolves.
    st.markdown(
        '<div data-testid="hero-band" '
        'style="border-left:4px solid #95a5a6; background:#111821; '
        'padding:10px 14px; margin:6px 0 10px 0; border-radius:6px; '
        'color:#e7ecf3;">'
        '<span style="background:#95a5a6; color:#0b0f14; padding:4px 10px; '
        'border-radius:4px; font-weight:700; letter-spacing:1px; '
        'font-size:0.85rem;">HERO &middot; UNAVAILABLE</span>'
        f'<span style="margin-left:10px; color:#c7cdd4; font-size:0.85rem;">'
        f"{_hero_exc!r}</span>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.caption(_HERO_DISCLAIMER)


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab_arb, tab_depl, tab_fleet = st.tabs(
    [
        _T["stretch"],
        "Inventory drawdown",
        "Tanker fleet",
    ]
)


# ---- Tab 1 --------------------------------------------------------------
with tab_arb:
    st.subheader(
        f"Brent vs WTI — price and {_T['stretch'].lower()}"
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
        f"90-day {_T['stretch'].lower()}" + (" (Z-score)" if show_advanced else ""),
        f"{latest_z:+.2f}",
        delta=f"{'ALERT' if z_flag else 'calm'}  |  spread ${latest_spread:,.2f}",
        delta_color="inverse" if z_flag else "normal",
        help=(
            "How far the Brent-WTI spread is from its 90-day normal, in "
            "standard deviations. |Stretch| > 2 = statistically unusual; "
            "> 3 = extreme. Technically a Z-score."
        ),
    )

    # --- Cointegration + crack spread tiles (desk-quant foundation) ----
    ct_col, hl_col, hr_col, crack_col = st.columns(4)
    coint_verdict = coint_info.get("verdict", "inconclusive")
    coint_p = coint_info.get("p_value", float("nan"))
    verdict_badge = {
        "cointegrated": ("STRONG", "normal"),
        "weak": ("WEAK", "off"),
        "not_cointegrated": ("BROKEN", "inverse"),
        "inconclusive": ("—", "off"),
    }.get(coint_verdict, ("—", "off"))
    ct_col.metric(
        "Cointegration strength",
        verdict_badge[0],
        delta=f"p={coint_p:.3f}" if coint_p == coint_p else "n/a",
        delta_color=verdict_badge[1],
        help=(
            "Engle-Granger test on Brent vs WTI. STRONG (p<0.05) means "
            "the pair is statistically well-behaved for mean-reversion "
            "trading. BROKEN means the signal isn't valid right now."
        ),
    )
    hl = coint_info.get("half_life_days")
    hl_col.metric(
        "Half-life to mean",
        f"{hl:.1f} days" if hl else "—",
        help=(
            "How long it takes the Brent-WTI spread to decay half-way "
            "back to its mean. Short half-life (<30d) = fast reverting; "
            "long (>90d) = slow grind — size accordingly."
        ),
    )
    hr = coint_info.get("hedge_ratio", float("nan"))
    hr_col.metric(
        "Dynamic hedge ratio",
        f"{hr:.2f}" if hr == hr else "—",
        help=(
            "β from OLS Brent = α + β·WTI. A 1:1 hedge is naïve; the "
            "current β tells you how many barrels of WTI you'd short per "
            "barrel of Brent you're long to isolate the residual."
        ),
    )
    crack_ok = crack_info.get("ok", False)
    crack_val = crack_info.get("latest_crack_usd", float("nan"))
    crack_corr = crack_info.get("corr_30d_vs_brent_wti", float("nan"))
    crack_col.metric(
        "3-2-1 crack spread",
        f"${crack_val:,.2f}/bbl" if crack_ok and crack_val == crack_val else "n/a",
        delta=f"corr30d {crack_corr:+.2f}" if crack_corr == crack_corr else "",
        help=(
            "(2·RBOB + HO)/3 − WTI, in USD/barrel — a proxy for refinery "
            "margin. When crack is high, refiners lift WTI hard and the "
            "Brent-WTI spread tends to compress. The correlation number "
            "shows how tightly those moves track over the last 30 days."
        ),
    )

    if not crack_ok:
        st.caption(
            f":grey[crack spread unavailable — {crack_info.get('note', 'upstream fetch failed')}]"
        )
    if coint_verdict == "not_cointegrated":
        st.warning(
            "⚠️  Brent & WTI fail the cointegration test right now "
            f"(p={coint_p:.3f}). The spread-stretch signal below should be "
            "treated as trend-follow rather than snap-back to normal."
        )
    elif coint_verdict == "weak":
        st.info(
            f"Cointegration weak (p={coint_p:.3f}) — {_T['trade_idea'].lower()} card "
            "will size more conservatively than normal."
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
            f"How stretched is the spread? — 90-day {_T['stretch'].lower()}"
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
    fig.update_yaxes(title_text=pretty_axis_label("stretch"), row=2, col=1)
    fig.update_xaxes(title_text="Date", row=2, col=1)

    st.plotly_chart(apply_theme(fig), use_container_width=True)

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
        f"#### {_T['mean_reversion']} — {_T['backtest_label'].lower()}"
        + (" (Z-score mean reversion)" if show_advanced else "")
    )
    st.caption(
        f"Enters when the stretch reaches \u00b1{z_threshold:.1f}, exits when "
        "the spread is back near normal. 10,000 barrels per trade, with the "
        "slippage and commission drag you set in the sidebar. "
        "Think of the PnL as a signal-quality indicator, not a P&L forecast."
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

    # --- Extended risk suite (desk-grade) -------------------------------
    rx_c1, rx_c2, rx_c3, rx_c4, rx_c5 = st.columns(5)
    sortino = bt.get("sortino", 0.0)
    rx_c1.metric(
        "Downside-adj return" + (" (Sortino)" if show_advanced else ""),
        f"{sortino:.2f}" if sortino != float("inf") else "∞",
        help=(
            "Like Sharpe, but only penalises downside volatility — ignores "
            "good swings. If Sortino >> Sharpe, the strategy's noise is "
            "mostly upside. Technically the Sortino ratio."
        ),
    )
    calmar = bt.get("calmar", 0.0)
    rx_c2.metric(
        "Return vs drawdown" + (" (Calmar)" if show_advanced else ""),
        f"{calmar:.2f}" if calmar != float("inf") else "∞",
        help=(
            "Annualised return ÷ biggest losing streak. A PM's single "
            "favourite sizing metric: > 1 means you make more in a year "
            "than you bled at the worst drawdown. Technically Calmar."
        ),
    )
    rx_c3.metric(
        "Worst-5% trade" + (" (VaR-95)" if show_advanced else ""),
        f"${bt.get('var_95', 0.0):,.0f}",
        help=(
            "95% of historical trades did at least this well; the other "
            "5% did worse. Per-trade value-at-risk on the PnL distribution."
        ),
    )
    rx_c4.metric(
        "Tail-5% avg" + (" (ES-95)" if show_advanced else ""),
        f"${bt.get('es_95', 0.0):,.0f}",
        help=(
            "Average PnL across the worst 5% of historical trades — "
            "expected shortfall. What to brace for on a bad day."
        ),
    )
    roll = bt.get("rolling_12m_sharpe", float("nan"))
    rx_c5.metric(
        "12m rolling risk-adjusted return" + (" (Sharpe)" if show_advanced else ""),
        f"{roll:.2f}" if roll == roll else "—",
        help=(
            "Trailing-year Sharpe ratio on the trade PnL series. A sharp "
            "drop versus the full-sample number means the strategy's edge "
            "has decayed recently — re-examine before sizing up."
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
        st.plotly_chart(apply_theme(eq_fig), use_container_width=True)

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
        st.plotly_chart(apply_theme(pnl_fig), use_container_width=True)

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
                st.plotly_chart(apply_theme(wf_fig), use_container_width=True)
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
                        xaxis_title=(
                            "Price-jumpiness regime (30d realised, median-split)"
                        ),
                        showlegend=False,
                        margin=dict(l=40, r=20, t=30, b=40),
                    )
                    st.markdown("**Regime breakdown (high-vol vs low-vol at entry)**")
                    st.plotly_chart(apply_theme(rb_fig), use_container_width=True)
    else:
        st.info(
            f"No trades triggered at \u00b1{z_threshold:.1f}\u03c3 on the "
            "historical window. Drop the threshold in the sidebar to see activity."
        )

    # --- Model internals (relocated from the retired "AI trade thesis" tab) --
    # The hero band at the top already shows the stance, confidence, summary,
    # and pre-trade checklist. What's left from the old AI tab is the model
    # mode toggle, the reasoning summary ("how I'm thinking about this"),
    # and the history of past theses — kept here for traders who want to
    # inspect the engine that produced the hero band.
    with st.expander("Model internals (thesis engine)"):
        from trade_thesis import (
            read_recent_theses as _mi_read_recent,
            history_stats as _mi_history_stats,
            diff_theses as _mi_diff,
        )

        _mi_thesis = st.session_state.get("_thesis_obj")

        # Mode toggle + regenerate ---------------------------------------
        _mi_mode_display = st.radio(
            "Model",
            options=[
                "Quick read (gpt-4o, ~2s)",
                "Deep analysis (o4-mini reasoning, 10\u201320s)",
            ],
            index=0,
            horizontal=True,
            key="_mi_mode_radio",
            help=(
                "Quick read uses gpt-4o \u2014 fast synthesis for normal use. "
                "Deep analysis invokes o4-mini, a reasoning model that thinks "
                "longer about the data and exposes its step-by-step thinking."
            ),
        )
        _mi_selected_mode = "fast" if _mi_mode_display.startswith("Quick") else "deep"

        _mi_regen = st.button(
            "Regenerate",
            type="primary",
            key="_mi_regen_btn",
            help=f"Regenerates the {_T['trade_idea'].lower()} now; the hero band will refresh on rerun.",
        )
        if _mi_regen:
            try:
                from trade_thesis import generate_thesis as _mi_gen
                with st.spinner(
                    "Thinking through the data\u2026" if _mi_selected_mode == "deep"
                    else "Generating\u2026"
                ):
                    _mi_thesis = _mi_gen(_hero_ctx, mode=_mi_selected_mode)
                st.session_state["_thesis_obj"] = _mi_thesis
                st.session_state["_thesis_last_generated_at"] = (
                    pd.Timestamp.utcnow().strftime("%Y-%m-%d %H:%M:%SZ")
                )
                st.success(f"{_T['trade_idea']} regenerated. Scroll up to see the refreshed hero band.")
            except Exception as _exc:
                st.error(f"Regenerate failed: `{_exc!r}`")

        # Reasoning summary ---------------------------------------------
        if _mi_thesis is not None:
            _reasoning = (_mi_thesis.raw or {}).get("reasoning_summary")
            if _reasoning:
                st.markdown("**How I'm thinking about this**")
                st.markdown(_reasoning)

            # Run metadata
            _bits = [
                f"mode **{_mi_thesis.mode}**",
                f"latency **{_mi_thesis.latency_s:.2f}s**",
                f"streamed **{'yes' if _mi_thesis.streamed else 'no'}**",
            ]
            if _mi_thesis.retried:
                _bits.append("retried once")
            if _mi_thesis.guardrails_applied:
                _bits.append(f"{len(_mi_thesis.guardrails_applied)} guardrails")
            st.caption("Run: " + "  \u00b7  ".join(_bits))

        # Recent trade-idea history --------------------------------------
        # UIP-T7: wrap the thesis-history load so a corrupt jsonl never
        # propagates a traceback into the expander.
        try:
            _mi_history = _mi_read_recent(n=10)
        except Exception as _hist_exc:
            render_error(
                f"Couldn't load trade-idea history. {type(_hist_exc).__name__}",
                retry_fn=lambda: None,
            )
            _mi_history = []
        _mi_stats = _mi_history_stats(_mi_history)
        if _mi_stats["n"]:
            st.caption(
                f"**Last {_mi_stats['n']} trade ideas:** "
                f"{_mi_stats['long']} buy \u00b7 {_mi_stats['short']} sell \u00b7 "
                f"{_mi_stats['flat']} wait \u00b7 "
                f"average confidence {_mi_stats['avg_conf']:.1f}/10."
            )
        with st.expander(f"Recent trade ideas ({_mi_stats.get('n', 0)})"):
            if not _mi_history:
                st.caption("No trade ideas logged yet.")
            else:
                _mi_rows = []
                for r in _mi_history:
                    _th = r.get("thesis", {}) or {}
                    _mi_rows.append({
                        "when": r.get("timestamp", "\u2014"),
                        "mode": _th.get("mode") or r.get("mode") or "\u2014",
                        "stance": _th.get("stance", "\u2014"),
                        "confidence": round(float(_th.get("conviction_0_to_10", 0) or 0), 1),
                        "summary": (_th.get("thesis_summary") or "")[:160],
                    })
                st.dataframe(pd.DataFrame(_mi_rows), use_container_width=True)

    # ---- CFTC Positioning expander (Macro Arbitrage) --------------------
    with st.expander(":material/query_stats: Positioning — CFTC COT (WTI)", expanded=False):
        if cftc_res is None or cftc_res.frame is None or cftc_res.frame.empty:
            st.warning(
                "CFTC feed unavailable — weekly positioning data could not be "
                "retrieved. Check network connectivity; updates next Friday 3:30pm ET."
            )
        else:
            st.caption(
                f":blue-badge[:material/public: CFTC COT (keyless, weekly)] "
                f"Source: **{cftc_res.source}** · "
                f"fetched {cftc_res.fetched_at.strftime('%Y-%m-%d %H:%M:%SZ')} · "
                f"as of **{cftc_res.frame.index[-1].strftime('%Y-%m-%d')}** · "
                f"{cftc_res.weeks} weeks"
            )
            cot_latest = cftc_res.frame.iloc[-1]
            pcols = st.columns(4)
            pcols[0].metric(
                "Managed Money net",
                f"{int(cot_latest['mm_net']):+,}",
                delta=f"Z {cftc_res.mm_zscore_3y:+.2f}" if cftc_res.mm_zscore_3y is not None else None,
                help=(
                    "Hedge-fund / CTA net futures position (contracts, 1000 bbl each). "
                    "Z-score is vs trailing ~3y. Extreme positive = crowded long "
                    "(often precedes reversal); extreme negative = crowded short."
                ),
            )
            pcols[1].metric(
                "Producer / Merchant net",
                f"{int(cot_latest['producer_net']):+,}",
                help="Physical crude producers, refiners, merchants — the hedging flow.",
            )
            pcols[2].metric(
                "Swap Dealer net",
                f"{int(cot_latest['swap_net']):+,}",
                help="Bank desks laying off producer hedges. Usually negative when producers are net long.",
            )
            pcols[3].metric(
                "Open interest",
                f"{int(cot_latest['open_interest']):,}",
                help="Total contracts outstanding across all categories.",
            )

            # Chart: MM net + Z-score overlay
            try:
                mm_frame = cftc_res.frame[["mm_net"]].copy()
                mm_frame = mm_frame.dropna()
                rolling_mean = mm_frame["mm_net"].rolling(156, min_periods=20).mean()
                rolling_std = mm_frame["mm_net"].rolling(156, min_periods=20).std(ddof=0)
                mm_frame["z"] = (mm_frame["mm_net"] - rolling_mean) / rolling_std

                fig = go.Figure()
                fig.add_trace(
                    go.Scattergl(
                        x=mm_frame.index,
                        y=mm_frame["mm_net"],
                        mode="lines",
                        name="MM Net (contracts)",
                        line=dict(color="#1f77b4", width=1.8),
                    )
                )
                fig.add_trace(
                    go.Scattergl(
                        x=mm_frame.index,
                        y=mm_frame["z"] * (mm_frame["mm_net"].abs().mean()),
                        mode="lines",
                        name="Z-score (scaled)",
                        line=dict(color="#ff7f0e", width=1.2, dash="dot"),
                        yaxis="y2",
                        opacity=0.75,
                    )
                )
                fig.update_layout(
                    height=320,
                    template="plotly_dark",
                    margin=dict(l=40, r=40, t=30, b=40),
                    xaxis_title="Report date",
                    yaxis=dict(title="Managed-money net (contracts)"),
                    yaxis2=dict(title="Z-score (~3y)", overlaying="y", side="right", showgrid=False),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0.0),
                )
                st.plotly_chart(apply_theme(fig), use_container_width=True)
                st.caption(
                    ":grey[Z-score thresholds: ±1.5σ historically mark extended positioning; "
                    "±2.0σ flags crowded regimes that often mean-revert within 4-8 weeks.]"
                )
            except Exception as exc:
                st.caption(f":red[positioning chart failed to render: {exc!r}]")


# ---- Tab 2 --------------------------------------------------------------
with tab_depl:
    st.subheader("How fast is US crude inventory drawing down?")
    # Badge reflects whether we're on the v2 API key path or keyless dnav fallback.
    _eia_live = bool(os.environ.get("EIA_API_KEY"))
    _badge = (
        ":green-badge[:material/verified: EIA v2 API (keyed)]"
        if _eia_live
        else ":orange-badge[:material/public: EIA dnav (keyless)]"
    )
    st.caption(
        f"{_badge}  Source: **{inventory_res.source}** · "
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

    # --- Cushing delivery hub (the Brent-WTI spread driver) -------------
    cushing_series = inventory.get("Cushing_bbls")
    if cushing_series is not None and cushing_series.notna().any():
        cu = cushing_series.dropna()
        cu_current = float(cu.iloc[-1])
        cu_tail = cu.tail(4)
        if len(cu_tail) >= 2:
            days = (cu_tail.index[-1] - cu_tail.index[0]).days or 1
            cu_slope = (cu_tail.iloc[-1] - cu_tail.iloc[0]) / days
        else:
            cu_slope = 0.0

        d1, d2, d3 = st.columns([2, 2, 3])
        d1.metric(
            "Cushing, OK stocks",
            f"{cu_current/1e6:,.1f} million barrels",
            help=(
                "Weekly EIA series for Cushing, Oklahoma — the physical "
                "delivery hub for the WTI contract. Dominant driver of "
                "the WTI leg of the Brent-WTI spread."
            ),
        )
        d2.metric(
            "Cushing 4-week drawdown",
            f"{cu_slope/1e3:+,.1f} thousand bbl/day",
            help=(
                "Linear slope of the last 4 weekly Cushing observations. "
                "Falling Cushing → WTI firms → Brent-WTI spread compresses."
            ),
        )
        # 5y percentile for quick context
        if len(cu) > 50:
            pct_rank = float((cu < cu_current).mean() * 100.0)
            d3.metric(
                "Cushing 5y percentile",
                f"{pct_rank:.0f}th",
                help=(
                    "Where today's Cushing stock level sits in its own "
                    "5-year distribution. Above 80th = pipeline-out-stressed; "
                    "below 20th = WTI well-bid."
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

    st.plotly_chart(apply_theme(fig2), use_container_width=True)

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
    # Badge: LIVE when aisstream.io websocket returned a real snapshot, else clearly-labeled sample.
    if getattr(ais_res, "is_live", False):
        _fleet_badge = f":green-badge[:material/sensors: LIVE AIS — {len(ais_res.frame):,} vessels · last 5 min]"
    else:
        _fleet_badge = ":orange-badge[:material/inventory_2: Labeled historical snapshot (Q3 2024)]"
    st.caption(
        f"{_fleet_badge}  Source: **{ais_res.source}** · "
        f"fetched {ais_res.fetched_at.strftime('%Y-%m-%d %H:%M:%SZ')}"
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

    st.plotly_chart(apply_theme(bar), use_container_width=True)

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
    st.plotly_chart(apply_theme(drill_fig), use_container_width=True)

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



st.markdown("---")
st.caption(
    "Streamlit + Plotly + Three.js/WebGPU + Azure OpenAI. Pricing via Yahoo Finance "
    "(15-min delayed futures). Inventory via EIA dnav (keyless). AIS placeholder with "
    "aisstream.io upgrade path. Not investment advice."
)

# UIP-T9: app footer — single-line disclaimer + build version + region.
# Zero personalization; copy is fixed by ``theme.render_footer``.
render_footer(_resolve_build_version())
