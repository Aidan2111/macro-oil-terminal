"""Issue #103 — LLM calibration burn-in via shadow theses.

Identifies ~100 historical signal-trigger dates from the spread series
(where |Z| crossed an entry threshold), replays each through the
thesis pipeline with **historical context only** (no future data),
records the predicted (stance, conviction) and the realized 30-day-
forward outcome (did the spread mean-revert toward 0?), and writes
everything to ``data/shadow_theses.jsonl``.

Two modes:

  * ``--mode=stub`` (default): use a deterministic local rule that
    emulates what the LLM would do — stance from sign(Z), conviction
    scaled with |Z|. Lets us seed the calibration pipeline without
    burning $5-20 of API tokens. Mark every row with
    ``mode="stub"`` so the audit trail is unambiguous.
  * ``--mode=foundry``: real LLM call per trigger date. One-time
    burn-in. Cost: 100 calls × ~$0.05–0.20 = $5-20.

Usage
-----
    python scripts/run_shadow_calibration.py --mode stub --max-rows 100
    python scripts/run_shadow_calibration.py --mode foundry --max-rows 100
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

REPO = pathlib.Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _load_spread_history() -> pd.DataFrame:
    """Return a long Brent-WTI spread history with Z-score column.

    Falls back to a synthetic series if the live providers are
    unavailable (offline run / no API keys). The synthetic path is
    deterministic so the stub burn-in is reproducible.
    """
    try:
        from backend.services.backtest_service import _load_spread_df

        df = _load_spread_df(lookback_days=365 * 8)
        if df is not None and not df.empty:
            return df
    except Exception as exc:
        print(f"[shadow-calibration] live providers unavailable: {exc}", file=sys.stderr)

    print("[shadow-calibration] falling back to synthetic 8y spread series", file=sys.stderr)
    rng = np.random.default_rng(2026)
    n = 365 * 8
    # AR(1) mean-reverting spread + occasional regime breaks (random
    # walk segments) so a chunk of triggers don't mean-revert. This
    # produces a non-degenerate calibration verdict — pure mean
    # reversion would give 100% hits at every conviction bucket.
    spread = np.zeros(n)
    spread[0] = 4.0
    regime_breaks = sorted(rng.integers(low=200, high=n - 50, size=12).tolist())
    in_break_until = -1
    for i in range(1, n):
        if regime_breaks and i == regime_breaks[0]:
            regime_breaks.pop(0)
            in_break_until = i + int(rng.integers(20, 80))
        if i <= in_break_until:
            # Random-walk segment (no mean reversion) — these triggers
            # tend NOT to revert within 30 days.
            spread[i] = spread[i - 1] + rng.normal(0, 1.4)
        else:
            bias = 0.5 * np.sin(2 * np.pi * i / 250.0)
            spread[i] = 0.85 * spread[i - 1] + 0.15 * (4.0 + bias) + rng.normal(0, 1.0)
    idx = pd.date_range(end=datetime(2026, 4, 28), periods=n, freq="D")
    s = pd.Series(spread, index=idx, name="Spread")
    rmean = s.shift(1).rolling(90).mean()
    rstd = s.shift(1).rolling(90).std(ddof=0).replace(0, np.nan)
    z = (s - rmean) / rstd
    return pd.DataFrame({"Spread": s, "Z_Score": z}).dropna()


def _trigger_dates(df: pd.DataFrame, *, threshold: float = 1.5, min_gap_days: int = 14) -> list[pd.Timestamp]:
    """Pick historical signal-trigger dates: bars where |Z| crosses
    ``threshold`` from below, with at least ``min_gap_days`` gap to
    the previous trigger so consecutive bars don't all qualify.
    """
    z = df["Z_Score"].abs()
    # First-crossing: today >= threshold AND yesterday < threshold.
    crossings = (z >= threshold) & (z.shift(1) < threshold)
    candidates = list(df.index[crossings])
    selected: list[pd.Timestamp] = []
    last = None
    for d in candidates:
        if last is None or (d - last).days >= min_gap_days:
            selected.append(d)
            last = d
    return selected


def _stub_thesis(z: float) -> tuple[str, int]:
    """Deterministic stand-in for the LLM call.

    stance: long_spread when Z<0, short_spread when Z>0, flat at small |Z|.
    conviction: clip(round(1 + abs(Z) * 2), 1, 10) — wider spread than
    a 1.5x scaling so the calibration histogram populates 3+ buckets.
    """
    if abs(z) < 1.0:
        return "flat", 1
    stance = "short_spread" if z > 0 else "long_spread"
    conv = int(round(min(10, max(1, 1.0 + abs(z) * 2.0))))
    return stance, conv


def _foundry_thesis(date: pd.Timestamp, ctx_payload: dict) -> tuple[str, int]:
    """Real LLM call against historical context. Best-effort; on any
    failure raises so the caller can decide whether to skip."""
    from foundry_agent import build_thesis_via_foundry  # type: ignore

    out = build_thesis_via_foundry(ctx_payload)  # legacy entry point
    raw = out.raw if hasattr(out, "raw") else (out or {})
    stance = str(raw.get("stance") or "flat")
    conv = int(raw.get("conviction_0_to_10") or 0)
    return stance, conv


def _realized_outcome(df: pd.DataFrame, trigger: pd.Timestamp, *, horizon_days: int = 30) -> bool | None:
    """Did the spread mean-revert toward 0 by ``horizon_days`` after
    the trigger? Returns None if not enough forward data exists."""
    end = trigger + pd.Timedelta(days=horizon_days)
    if end > df.index.max():
        return None
    z_at_trigger = float(df.loc[trigger, "Z_Score"])
    forward = df.loc[trigger:end]
    if forward.empty:
        return None
    # "Reverted toward 0" = at some point in the next N days, |Z| <= 0.2
    # (matches the live exit_z of 0.2). Tighter than a slack-allowed
    # threshold so regime-shift triggers (where mean reversion fails)
    # actually score as miss and the calibration verdict ends up
    # non-trivial.
    return bool((forward["Z_Score"].abs() <= 0.2).any())


def _build_row(
    *, trigger: pd.Timestamp, df: pd.DataFrame, mode: str,
) -> dict | None:
    z = float(df.loc[trigger, "Z_Score"])
    spread = float(df.loc[trigger, "Spread"])
    hit = _realized_outcome(df, trigger)
    if hit is None:
        # Trigger too close to "now" to score; skip.
        return None

    if mode == "foundry":
        try:
            stance, conv = _foundry_thesis(trigger, {"current_z": z, "latest_spread": spread})
        except Exception as exc:
            print(f"[shadow-calibration] foundry failed at {trigger.date()}: {exc}", file=sys.stderr)
            return None
    else:
        stance, conv = _stub_thesis(z)

    return {
        "trigger_date": trigger.isoformat(),
        "z_at_trigger": z,
        "spread_at_trigger": spread,
        "mode": mode,
        "thesis": {
            "stance": stance,
            "conviction_0_to_10": conv,
            "outcome": {"hit_target": hit},
        },
        "scored_at": datetime.now(timezone.utc).isoformat(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Shadow-thesis calibration burn-in (issue #103)")
    parser.add_argument("--mode", choices=("stub", "foundry"), default="stub")
    parser.add_argument("--max-rows", type=int, default=100)
    parser.add_argument("--threshold", type=float, default=1.5)
    parser.add_argument("--min-gap-days", type=int, default=14)
    parser.add_argument("--horizon-days", type=int, default=30)
    parser.add_argument(
        "--output",
        type=pathlib.Path,
        default=REPO / "data" / "shadow_theses.jsonl",
    )
    args = parser.parse_args(argv)

    df = _load_spread_history()
    triggers = _trigger_dates(df, threshold=args.threshold, min_gap_days=args.min_gap_days)
    if not triggers:
        print("[shadow-calibration] no trigger dates — adjust threshold", file=sys.stderr)
        return 1

    rows: list[dict] = []
    for t in triggers:
        if len(rows) >= args.max_rows:
            break
        row = _build_row(trigger=t, df=df, mode=args.mode)
        if row is not None:
            rows.append(row)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, default=str) + "\n")

    # Summary.
    if rows:
        per_bucket: dict[str, list[bool]] = {"low": [], "mid": [], "high": []}
        for r in rows:
            conv = r["thesis"]["conviction_0_to_10"]
            hit = r["thesis"]["outcome"]["hit_target"]
            if conv <= 3:
                per_bucket["low"].append(hit)
            elif conv <= 6:
                per_bucket["mid"].append(hit)
            else:
                per_bucket["high"].append(hit)
        print(f"[shadow-calibration] wrote {len(rows)} rows to {args.output}")
        for k, v in per_bucket.items():
            if v:
                rate = sum(v) / len(v)
                print(f"  conviction {k:>5}: n={len(v)} hit_rate={rate:.2%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
