# Hero Trade Thesis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use
> `superpowers:subagent-driven-development` — fresh subagent per task, two-
> stage review (spec compliance, then code quality).

**Goal:** Promote the Trade Thesis to hero placement with 3 instrument tiers
and a 5-item pre-trade checklist; gate on materiality; add `hours_to_next_eia`
to the context.

**Architecture:** Decoration is a pure function over `Thesis + ThesisContext`
that produces `instruments: list[Instrument]` and `checklist: list[ChecklistItem]`.
The LLM path is untouched. UI consumes the decorated thesis. Streamlit hero
band renders above tabs on every tab.

**Tech stack:** Python 3.11, pandas, Streamlit, pytest, Playwright for e2e.

---

> **Status:** DRAFT. Do NOT begin execution until `docs/designs/hero-thesis.md`
> is approved by Aidan. This plan assumes the design's open items resolve to
> the proposed defaults. If they don't, tasks 2 and 5 change.

---

## Task 1 — Add `hours_to_next_eia` to `ThesisContext`

**Files:**
- Modify: `thesis_context.py` (add field to dataclass, compute in builder)
- Create: `tests/unit/test_thesis_context_eia_hours.py`

- [ ] **Step 1 — Write failing test**

```python
# tests/unit/test_thesis_context_eia_hours.py
from datetime import datetime, timezone
from thesis_context import _hours_to_next_eia_release

def test_hours_to_next_eia_tuesday_before_release():
    now = datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc)  # Tue noon UTC
    # Next release: Wed 2026-04-22 14:30 UTC
    assert abs(_hours_to_next_eia_release(now) - 26.5) < 0.1

def test_hours_to_next_eia_wednesday_after_release():
    now = datetime(2026, 4, 22, 15, 0, tzinfo=timezone.utc)  # Wed 15:00 UTC
    # Next release: Wed 2026-04-29 14:30 UTC = 7d * 24h - 0.5h
    assert abs(_hours_to_next_eia_release(now) - 167.5) < 0.1

def test_hours_to_next_eia_is_none_when_now_is_none():
    assert _hours_to_next_eia_release(None) is None
```

- [ ] **Step 2 — Run the test to verify it fails**

```bash
cd ~/Documents/macro_oil_terminal-hero
source ../macro_oil_terminal/.venv/bin/activate
python -m pytest tests/unit/test_thesis_context_eia_hours.py -v
```

Expected: `ImportError: cannot import name '_hours_to_next_eia_release'`.

- [ ] **Step 3 — Write the minimal implementation**

In `thesis_context.py`, add:

```python
from datetime import datetime, timezone, timedelta
from typing import Optional

def _hours_to_next_eia_release(now: Optional[datetime]) -> Optional[float]:
    """Hours until next EIA weekly petroleum status release (Wed 14:30 UTC)."""
    if now is None:
        return None
    # Days until next Wednesday (weekday 2); 0 if today AND before 14:30
    days_ahead = (2 - now.weekday()) % 7
    candidate = now.replace(hour=14, minute=30, second=0, microsecond=0) \
                   + timedelta(days=days_ahead)
    if candidate <= now:
        candidate += timedelta(days=7)
    return (candidate - now).total_seconds() / 3600.0
```

And add to `ThesisContext`:

```python
hours_to_next_eia: Optional[float] = None
```

- [ ] **Step 4 — Run the test to verify it passes**

```bash
python -m pytest tests/unit/test_thesis_context_eia_hours.py -v
```

Expected: `3 passed`.

- [ ] **Step 5 — Commit**

```bash
git add thesis_context.py tests/unit/test_thesis_context_eia_hours.py
git commit -m "feat(thesis): add hours_to_next_eia helper + field (task 1/6)"
```

---

## Task 2 — Add `Instrument` and `ChecklistItem` dataclasses

**Files:**
- Modify: `trade_thesis.py`
- Create: `tests/unit/test_hero_thesis_decoration.py` (shell only — no decorate fn yet)

- [ ] **Step 1 — Write failing test**

```python
# tests/unit/test_hero_thesis_decoration.py
from trade_thesis import Instrument, ChecklistItem

def test_instrument_dataclass_has_expected_fields():
    inst = Instrument(tier=1, name="Paper", symbol=None,
                      rationale="track only", suggested_size_pct=0.0,
                      worst_case_per_unit="N/A")
    assert inst.tier == 1
    assert inst.symbol is None

def test_checklist_item_dataclass_has_expected_fields():
    item = ChecklistItem(key="stop_in_place", prompt="I have a stop",
                         auto_check=None)
    assert item.key == "stop_in_place"
    assert item.auto_check is None
```

- [ ] **Step 2 — Verify it fails**

```bash
python -m pytest tests/unit/test_hero_thesis_decoration.py -v
```

Expected: `ImportError: cannot import name 'Instrument'`.

- [ ] **Step 3 — Add the dataclasses**

In `trade_thesis.py`, add above the existing `@dataclass class Thesis`:

```python
@dataclass
class Instrument:
    tier: int
    name: str
    symbol: Optional[str]
    rationale: str
    suggested_size_pct: float
    worst_case_per_unit: str

@dataclass
class ChecklistItem:
    key: str
    prompt: str
    auto_check: Optional[bool]
```

- [ ] **Step 4 — Verify passes**

```bash
python -m pytest tests/unit/test_hero_thesis_decoration.py -v
```

Expected: `2 passed`.

- [ ] **Step 5 — Commit**

```bash
git add trade_thesis.py tests/unit/test_hero_thesis_decoration.py
git commit -m "feat(thesis): Instrument + ChecklistItem dataclasses (task 2/6)"
```

---

## Task 3 — `decorate_thesis_for_execution` — flat stance returns empty

**Files:**
- Modify: `trade_thesis.py`
- Modify: `tests/unit/test_hero_thesis_decoration.py`

- [ ] **Step 1 — Failing test**

```python
def test_decorate_flat_thesis_returns_empty_instruments_and_checklist(
        flat_thesis, minimal_context):
    out = decorate_thesis_for_execution(flat_thesis, minimal_context)
    assert out.instruments == []
    assert out.checklist == []
    # original unchanged (no mutation)
    assert flat_thesis.instruments == []
```

(Include `flat_thesis` and `minimal_context` fixtures at top of file — complete
code below.)

```python
import pytest
from trade_thesis import Thesis, decorate_thesis_for_execution
from thesis_context import ThesisContext

@pytest.fixture
def flat_thesis():
    return Thesis(raw={"stance": "flat", "conviction_0_to_10": 0.0,
                       "time_horizon_days": 0, "suggested_pct_of_capital": 0.0},
                  mode="model", validated=True)

@pytest.fixture
def minimal_context():
    return ThesisContext(
        latest_brent=80.0, latest_wti=76.0, latest_spread=4.0,
        rolling_mean_90d=3.5, rolling_std_90d=0.5, current_z=1.0,
        z_percentile_5y=60.0, days_since_last_abs_z_over_2=5,
        bt_hit_rate=0.6, bt_avg_hold_days=3.0, bt_avg_pnl_per_bbl=0.1,
        bt_max_drawdown_usd=-1000.0, bt_sharpe=0.8,
        inventory_source="EIA", inventory_current_bbls=400_000_000.0,
        inventory_4w_slope_bbls_per_day=-100_000.0,
        inventory_52w_slope_bbls_per_day=-50_000.0,
        inventory_floor_bbls=300_000_000.0,
        inventory_projected_floor_date="2027-04-22",
        days_of_supply=20.0,
        fleet_total_mbbl=500.0, fleet_jones_mbbl=100.0,
        fleet_shadow_mbbl=200.0, fleet_sanctioned_mbbl=50.0,
        fleet_source="Historical snapshot",
        fleet_delta_vs_30d_mbbl=5.0,
        vol_brent_30d_pct=25.0, vol_brent_30d_p85=40.0,
        hours_to_next_eia=48.0)
```

- [ ] **Step 2 — Verify fails**

Expected: `ImportError: cannot import name 'decorate_thesis_for_execution'`.

- [ ] **Step 3 — Implement minimal version**

```python
def decorate_thesis_for_execution(thesis: Thesis,
                                  ctx: ThesisContext) -> Thesis:
    """Return a copy of `thesis` with instruments + checklist populated."""
    from copy import deepcopy
    out = deepcopy(thesis)
    if out.raw.get("stance") == "flat":
        out.instruments = []
        out.checklist = []
    return out
```

And add the fields to `Thesis` (if not added by Task 2 coupling — they aren't):

```python
@dataclass
class Thesis:
    # ... existing fields ...
    instruments: list = field(default_factory=list)
    checklist: list = field(default_factory=list)
```

- [ ] **Step 4 — Verify passes**
- [ ] **Step 5 — Commit**

```bash
git commit -am "feat(thesis): decorate stub — flat returns empty (task 3/6)"
```

---

## Task 4 — Decorate: three tiers for long_spread

**Files:**
- Modify: `trade_thesis.py`, `tests/unit/test_hero_thesis_decoration.py`

- [ ] **Step 1 — Failing tests**

```python
def test_decorate_long_spread_produces_three_tiers(minimal_context):
    thesis = Thesis(raw={"stance": "long_spread", "conviction_0_to_10": 7.0,
                         "time_horizon_days": 4, "suggested_pct_of_capital": 4.0},
                    mode="model", validated=True)
    out = decorate_thesis_for_execution(thesis, minimal_context)
    assert [i.tier for i in out.instruments] == [1, 2, 3]
    assert out.instruments[0].suggested_size_pct == 0.0              # paper
    assert out.instruments[1].suggested_size_pct == pytest.approx(2.0)  # ETF half
    assert out.instruments[2].suggested_size_pct == pytest.approx(4.0)  # futures full

def test_decorate_short_spread_inverts_etf_pair(minimal_context):
    thesis = Thesis(raw={"stance": "short_spread", "conviction_0_to_10": 7.0,
                         "time_horizon_days": 4, "suggested_pct_of_capital": 4.0},
                    mode="model", validated=True)
    out = decorate_thesis_for_execution(thesis, minimal_context)
    assert "short USO / long BNO" in out.instruments[1].rationale.lower()
```

- [ ] **Step 2 — Verify fails** (existing impl returns empty)

- [ ] **Step 3 — Extend `decorate_thesis_for_execution`**

```python
def decorate_thesis_for_execution(thesis, ctx):
    from copy import deepcopy
    out = deepcopy(thesis)
    stance = out.raw.get("stance")
    if stance == "flat":
        out.instruments = []
        out.checklist = []
        return out
    size = float(out.raw.get("suggested_pct_of_capital", 0.0))
    if stance == "long_spread":
        etf_note = "long USO / short BNO (WTI vs Brent ETF pair)"
        fut_note = "long CL=F / short BZ=F (futures calendar pair)"
    else:  # short_spread
        etf_note = "short USO / long BNO (WTI vs Brent ETF pair, inverted)"
        fut_note = "short CL=F / long BZ=F (futures calendar pair, inverted)"
    out.instruments = [
        Instrument(tier=1, name="Paper", symbol=None,
                   rationale="Track the thesis without capital at risk.",
                   suggested_size_pct=0.0, worst_case_per_unit="N/A"),
        Instrument(tier=2, name="USO/BNO ETF pair",
                   symbol="USO/BNO", rationale=etf_note,
                   suggested_size_pct=round(size * 0.5, 2),
                   worst_case_per_unit="~$X per $1k notional"),
        Instrument(tier=3, name="CL=F / BZ=F futures",
                   symbol="CL=F/BZ=F", rationale=fut_note,
                   suggested_size_pct=round(size * 1.0, 2),
                   worst_case_per_unit="$1000 per contract per $1 move"),
    ]
    out.checklist = []  # filled in task 5
    return out
```

- [ ] **Step 4 — Verify passes**
- [ ] **Step 5 — Commit**

---

## Task 5 — Decorate: checklist with two auto-check rules

**Files:**
- Modify: `trade_thesis.py`, `tests/unit/test_hero_thesis_decoration.py`

- [ ] **Step 1 — Failing tests**

```python
def test_decorate_checklist_auto_checks_vol_clamp_when_vol_below_p85(
        minimal_context):
    # minimal_context has vol_brent_30d_pct=25 < vol_brent_30d_p85=40
    thesis = Thesis(raw={"stance": "long_spread", "conviction_0_to_10": 7,
                         "time_horizon_days": 4, "suggested_pct_of_capital": 4},
                    mode="model", validated=True)
    out = decorate_thesis_for_execution(thesis, minimal_context)
    vol_item = next(c for c in out.checklist if c.key == "vol_clamp_ok")
    assert vol_item.auto_check is True

def test_decorate_checklist_catalyst_clear_over_24h(minimal_context):
    # minimal_context has hours_to_next_eia=48
    thesis = Thesis(raw={"stance": "long_spread", "conviction_0_to_10": 7,
                         "time_horizon_days": 4, "suggested_pct_of_capital": 4},
                    mode="model", validated=True)
    out = decorate_thesis_for_execution(thesis, minimal_context)
    cat_item = next(c for c in out.checklist if c.key == "catalyst_clear")
    assert cat_item.auto_check is True
```

- [ ] **Step 2 — Verify fails** (checklist currently empty)

- [ ] **Step 3 — Implement checklist**

```python
def _build_checklist(ctx):
    vol_ok = ctx.vol_brent_30d_pct < ctx.vol_brent_30d_p85
    cat_ok = (ctx.hours_to_next_eia is not None
              and ctx.hours_to_next_eia >= 24.0)
    return [
        ChecklistItem("stop_in_place",
                      "I have a stop at ±2σ spread move from entry.", None),
        ChecklistItem("vol_clamp_ok",
                      "Realized vol is below its 1y 85th percentile.", vol_ok),
        ChecklistItem("half_life_ack",
                      "I understand the implied half-life is ~N days.", None),
        ChecklistItem("catalyst_clear",
                      "No EIA release within 24 hours.", cat_ok),
        ChecklistItem("no_conflicting_recent_thesis",
                      "No stance flip in the last 5 thesis entries.", None),
    ]

# in decorate_thesis_for_execution, replace `out.checklist = []` with:
out.checklist = _build_checklist(ctx)
```

- [ ] **Step 4 — Verify passes**
- [ ] **Step 5 — Commit**

---

## Task 6 — Hero band in `app.py` + e2e

**Files:**
- Modify: `app.py`
- Create: `tests/e2e/test_hero_band.py`

- [ ] **Step 1 — Failing Playwright test**

```python
# tests/e2e/test_hero_band.py
import re
from playwright.sync_api import expect

def test_hero_band_renders_above_tabs(page, live_server):
    page.goto(live_server.url)
    hero = page.locator("[data-testid=hero-band]")
    expect(hero).to_be_visible()
    tabs = page.locator("[data-baseweb=tab-list]")
    hero_box = hero.bounding_box()
    tabs_box = tabs.bounding_box()
    assert hero_box["y"] + hero_box["height"] <= tabs_box["y"]
```

- [ ] **Step 2 — Verify fails** (no data-testid=hero-band yet)

- [ ] **Step 3 — Implement hero band**

Add to `app.py`, before the `st.tabs(...)` call, a new function:

```python
def _render_hero_band(thesis, ctx):
    from trade_thesis import decorate_thesis_for_execution
    decorated = decorate_thesis_for_execution(thesis, ctx)
    with st.container():
        st.markdown('<div data-testid="hero-band">', unsafe_allow_html=True)
        _render_liveness(ctx)
        _render_thesis_card(decorated)
        if decorated.instruments:
            cols = st.columns(3)
            for col, inst in zip(cols, decorated.instruments):
                _render_instrument_tile(col, inst)
            _render_checklist(decorated.checklist)
        st.markdown('</div>', unsafe_allow_html=True)
```

Wire it into the main render path; delete the "AI Insights" tab.

- [ ] **Step 4 — Verify e2e passes**

```bash
python -m pytest tests/e2e/test_hero_band.py -v
```

- [ ] **Step 5 — Commit + run full test gate**

```bash
git commit -am "feat(ui): hero thesis band + 3 tiers + checklist (task 6/6)"
python test_runner.py  # authoritative gate
```

Expected: all checks green.

---

## After all 6 tasks

Invoke `superpowers:finishing-a-development-branch`:

1. Run full test suite → expect green.
2. Present Aidan with 4 options (merge / PR / keep / discard).
3. If merge chosen: `git checkout main && git merge hero-thesis && git push`.
4. Cleanup worktree: `git worktree remove ../macro_oil_terminal-hero`.
5. Watch CI + CD. Don't close out until `/_stcore/health` is green on Azure.

## Execution note

Per `superpowers:subagent-driven-development`, dispatch a fresh subagent per
task (1 through 6) with two-stage review after each. Do not let any task
merge into the next; spec reviewer must ✅ before code-quality reviewer
begins; both must ✅ before advancing.
