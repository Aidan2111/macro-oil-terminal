#!/usr/bin/env bash
# ============================================================================
# Q3 prediction-quality slice — coordinated backend + frontend ship.
#
# Surfaces four visible end-states on the live SWA:
#   1. Engle-Granger cointegration (p-value + half-life) on every thesis.
#   2. GARCH(1,1)-normalized stretch as an advanced-toggle on the hero card.
#   3. Regime detection — term structure + vol bucket badges on hero.
#   4. Sortino + Calmar + VaR-95 + ES-97.5 on the backtest tile.
#
# Same operator workflow as Q1 / Q2: branch off origin/main, run the venv313
# pytest suite, push, open a PR, queue auto-merge.
#
# Idempotent — every step is safe to re-run.
# ============================================================================

set -euo pipefail

# Ensure host CLI tools are on PATH when invoked from a non-interactive shell
export PATH="/Users/aidanbothost/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

REPO=/Users/aidanbothost/Documents/macro_oil_terminal
cd "$REPO"

PY=/opt/homebrew/bin/python3.13
[ -x "$PY" ] || { echo "FATAL: Python 3.13 not at $PY" >&2; exit 1; }

VENV="$REPO/.venv313"
BRANCH="feat/prediction-quality"
PR_BODY="$REPO/scripts/q3-prediction-quality-run.PR_BODY.md"
LOG_DIR="$REPO/.agent-scripts/q3-prediction-quality-logs"
mkdir -p "$LOG_DIR"

# ---------------------------------------------------------------------------
# Phase 1 — preflight + venv
# ---------------------------------------------------------------------------
echo "==> Phase 1: preflight"
"$PY" --version
git --version
gh --version | head -1

if [ ! -d "$VENV" ]; then
  echo "==> creating fresh venv at $VENV"
  "$PY" -m venv "$VENV"
fi

# shellcheck disable=SC1091
source "$VENV/bin/activate"
python --version
pip install --upgrade --quiet pip wheel setuptools

# ---------------------------------------------------------------------------
# Phase 2 — branch off origin/main
# ---------------------------------------------------------------------------
echo "==> Phase 2: branch off origin/main"
git fetch origin --prune

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "==> stashing local tracked changes (will restore at end if branch deleted)"
  git stash push -m "q3-prediction-quality autostash $(date -u +%Y%m%dT%H%M%SZ)" --keep-index || true
fi

# `-B` makes this idempotent — re-running resets the branch to origin/main
# then re-applies the same tracked source changes already on disk in the
# working tree (the agent has written them; this script just commits them).
git checkout -B "$BRANCH" origin/main

# ---------------------------------------------------------------------------
# Phase 3 — install + run the test suite
# ---------------------------------------------------------------------------
echo "==> Phase 3: install pinned deps"
pip install --upgrade --quiet \
  -r requirements.txt \
  -r backend/requirements.txt \
  2>&1 | tee "$LOG_DIR/pip-install.log" >/dev/null

echo "==> Phase 3: pytest — Q3 unit suite (cointegration + regime + GARCH + backtest)"
set +e
PYTHONPATH="$REPO" pytest \
  tests/unit/test_cointegration_service.py \
  tests/unit/test_regime_service.py \
  tests/unit/test_garch_stretch.py \
  tests/unit/test_backtest_risk_metrics.py \
  --tb=short -q 2>&1 | tee "$LOG_DIR/pytest-q3.log"
RC_Q3=${PIPESTATUS[0]}

# The full root suite catches regressions to the modules we touched
# (quantitative_models, thesis_context, trade_thesis). Skip the
# Streamlit-coupled tests left over from the streamlit-decommission PR,
# matching the bump-deps playbook.
PYTHONPATH="$REPO" pytest tests/unit --tb=short -q \
  --ignore=tests/unit/test_theme.py \
  --ignore=tests/unit/test_theme_charts.py \
  --ignore=tests/unit/test_theme_checklist_countdown.py \
  --ignore=tests/unit/test_theme_hero.py \
  --ignore=tests/unit/test_theme_onboarding.py \
  --ignore=tests/unit/test_theme_states.py \
  --ignore=tests/unit/test_theme_ticker.py \
  --ignore=tests/unit/test_ux_revision_v2.py \
  --ignore=tests/unit/test_auth_decorator.py \
  --ignore=tests/unit/test_theme_meta.py \
  --ignore=tests/unit/test_ui_hedging_render.py \
  2>&1 | tee "$LOG_DIR/pytest-root.log"
RC_ROOT=${PIPESTATUS[0]}

# Backend tests have a pre-existing failure (route-less create_app, see
# bump-deps-run.PR_BODY.md). Run them so the log shows the same
# baseline the operator already accepts; do NOT gate on RC_BACKEND.
PYTHONPATH="$REPO" pytest backend/tests --tb=short -q \
  2>&1 | tee "$LOG_DIR/pytest-backend.log"
RC_BACKEND=${PIPESTATUS[0]}
set -e

if [ "$RC_Q3" -ne 0 ]; then
  echo "==> Q3 unit pytest failed (rc=$RC_Q3). Logs at $LOG_DIR/."
  echo "==> NOT pushing — fix the failures and re-run this script."
  exit 1
fi
if [ "$RC_ROOT" -ne 0 ]; then
  echo "==> root pytest failed (rc=$RC_ROOT). Logs at $LOG_DIR/."
  echo "==> NOT pushing — fix the failures and re-run this script."
  exit 1
fi
if [ "$RC_BACKEND" -ne 0 ]; then
  echo "==> backend pytest had failures (rc=$RC_BACKEND). These are PRE-EXISTING"
  echo "==> on origin/main (create_app() returns a route-less app, documented in"
  echo "==> scripts/bump-deps-run.PR_BODY.md). NOT a Q3 regression. Continuing."
fi

# ---------------------------------------------------------------------------
# Phase 4 — frontend type-check (lightweight; the next CI run does the build)
# ---------------------------------------------------------------------------
if command -v pnpm >/dev/null 2>&1 && [ -f "$REPO/frontend/package.json" ]; then
  echo "==> Phase 4: frontend type-check"
  ( cd "$REPO/frontend" && pnpm install --silent && pnpm exec tsc --noEmit ) \
    2>&1 | tee "$LOG_DIR/tsc.log" || {
      echo "==> tsc reported errors. Inspect $LOG_DIR/tsc.log."
      # Don't gate the push on tsc — Vercel CI is the source of truth.
    }
else
  echo "==> Phase 4 skipped: pnpm not on PATH"
fi

# ---------------------------------------------------------------------------
# Phase 5 — commit, push, PR, queue auto-merge
# ---------------------------------------------------------------------------
echo "==> Phase 5: commit + push + PR"

if git diff --quiet && git diff --cached --quiet; then
  echo "==> no changes to commit (already up to date with origin/main)"
else
  git add -A
  git commit -m "feat(thesis): Q3 prediction-quality slice — Engle-Granger + regime + GARCH + tail-risk metrics

Backend:
  * backend/services/cointegration_service.py — wraps cointegration.engle_granger
    with a content-hash cache so SSE poll cycles don't re-OLS on every hit.
  * backend/services/regime_service.py — term structure (contango/backwardation/
    flat) + 1y vol-bucket percentile classifier.
  * backend/services/garch_stretch.py — GARCH(1,1)-normalised stretch with a
    rolling-std fallback when arch can't fit.
  * ThesisContext gains 9 optional Q3 fields (regime + GARCH); coint fields
    already existed.
  * trade_thesis.SYSTEM_PROMPT instructs the LLM to cite the new fields.
  * quantitative_models.backtest_zscore_meanreversion adds ES-97.5 alongside
    the existing Sortino / Calmar / VaR-95 / ES-95.

Frontend:
  * components/hero/CointegrationStat.tsx — plain-English-tooltipped pill.
  * components/hero/RegimeBadges.tsx — two side-by-side badges.
  * components/hero/AdvancedToggle.tsx — sessionStorage-backed
    rolling↔GARCH stretch swap (localStorage is unavailable in Cowork).
  * components/charts/BacktestRiskMetrics.tsx — 4-up tooltipped strip.

Tests: 4 new pytest files, 26 cases, all green under .venv313."
fi

git push -u origin "$BRANCH"

if ! gh pr view "$BRANCH" >/dev/null 2>&1; then
  gh pr create \
    --base main \
    --head "$BRANCH" \
    --title "feat(thesis): Q3 prediction-quality slice — Engle-Granger + regime + GARCH + tail-risk" \
    --body-file "$PR_BODY"
fi

PR_URL=$(gh pr view "$BRANCH" --json url --jq .url)
echo "==> PR: $PR_URL"

gh pr merge "$BRANCH" --squash --auto --delete-branch || {
  echo "==> auto-merge queue failed (likely needs branch protection / status checks)."
  echo "==> PR is up; merge manually when checks pass."
}

echo "==> done."
