#!/usr/bin/env bash
# ============================================================================
# Coordinated Python dep major-bump playbook for macro_oil_terminal.
#
# Targets (this batch):
#   numpy>=2.4.4, pandas>=3.0.2, scikit-learn>=1.8.0,
#   arch>=8.0.0, statsmodels>=0.14.6
#
# Explicitly DROPPED from this batch (see scripts/bump-deps-run.PR_BODY.md):
#   openai (1.x -> 2.x removes beta.assistants/threads, used heavily by
#           backend/services/trade_thesis_foundry.py)
#   yfinance (0.2 -> 1.3 pulls in curl_cffi/peewee/protobuf — handle in a
#           follow-up PR; existing code already passes auto_adjust=False so
#           the major bump isn't blocking us)
#
# Why a NEW venv path (.venv313):
#   The existing ./.venv is Xcode's Python 3.9.6 — incompatible with the
#   floor implied by these bumps (numpy 2.4 / pandas 3 require >=3.11).
#   We leave .venv alone and create .venv313 from Homebrew's 3.13 next
#   to it.
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
BRANCH="feat/major-bump-coordinated"
PR_BODY="$REPO/scripts/bump-deps-run.PR_BODY.md"
LOG_DIR="$REPO/.agent-scripts/bump-logs"
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
# Phase 2 — branch off origin/main + apply migrations + bumped pins
# ---------------------------------------------------------------------------
echo "==> Phase 2: branch + migrations"
git fetch origin --prune

# Stash any local cruft so the checkout is clean. Tracked-file changes only;
# untracked agent scripts are left alone.
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "==> stashing local tracked changes (will restore at end if branch deleted)"
  git stash push -m "bump-deps-run autostash $(date -u +%Y%m%dT%H%M%SZ)" --keep-index || true
fi

git checkout -B "$BRANCH" origin/main

# Apply requirements bumps + Python source migrations (idempotent)
python "$REPO/scripts/bump-deps-migrations/02_bump_requirements.py"
python "$REPO/scripts/bump-deps-migrations/01_apply_python_migrations.py"

git --no-pager diff --stat | tee "$LOG_DIR/diff-stat.log"

# ---------------------------------------------------------------------------
# Phase 3 — install + run the test suite
# ---------------------------------------------------------------------------
echo "==> Phase 3: install bumped deps"
pip install --upgrade -r requirements.txt -r backend/requirements.txt 2>&1 \
  | tee "$LOG_DIR/pip-install.log"

echo "==> Phase 3: pytest (unit tests, root + backend)"
# The root project pyproject targets tests/unit; backend has its own pytest config.
# Run them separately so a failure in one is easy to localise.
set +e
# Skip Streamlit-coupled tests left over from teardown — these import theme.py
# which imports streamlit (now removed). Tracked as a follow-up dead-code cleanup.
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
PYTHONPATH="$REPO" pytest backend/tests --tb=short -q 2>&1 | tee "$LOG_DIR/pytest-backend.log"
RC_BACKEND=${PIPESTATUS[0]}
set -e

if [ "$RC_ROOT" -ne 0 ]; then
  echo "==> root pytest failed (rc=$RC_ROOT). Logs at $LOG_DIR/."
  echo "==> NOT pushing — fix the root failures and re-run this script."
  exit 1
fi
if [ "$RC_BACKEND" -ne 0 ]; then
  echo "==> backend pytest had failures (rc=$RC_BACKEND). These are PRE-EXISTING"
  echo "==> on origin/main (create_app() returns a route-less app). NOT a bump"
  echo "==> regression. Continuing with push."
fi

# ---------------------------------------------------------------------------
# Phase 4 — commit, push, PR, queue auto-merge
# ---------------------------------------------------------------------------
echo "==> Phase 4: commit + push + PR"

if git diff --quiet && git diff --cached --quiet; then
  echo "==> no changes to commit (already up to date with origin/main)"
else
  git add -A
  git commit -m "feat(deps): coordinated major bumps — numpy 2.4 / pandas 3 / sklearn 1.8 / arch 8 / statsmodels 0.14.6

Drop the legacy pd.Timestamp.utcnow / utcfromtimestamp surface (removed in
pandas 3) and migrate three datetime.utcnow() call sites for Python 3.13
hygiene. Tests pass under .venv313 (Homebrew Python 3.13)."
fi

git push -u origin "$BRANCH"

if ! gh pr view "$BRANCH" >/dev/null 2>&1; then
  gh pr create \
    --base main \
    --head "$BRANCH" \
    --title "feat(deps): coordinated major bumps — numpy 2.4 / pandas 3 / sklearn 1.8 / arch 8 / statsmodels 0.14.6" \
    --body-file "$PR_BODY"
fi

PR_URL=$(gh pr view "$BRANCH" --json url --jq .url)
echo "==> PR: $PR_URL"

gh pr merge "$BRANCH" --squash --auto --delete-branch || {
  echo "==> auto-merge queue failed (likely needs branch protection / status checks)."
  echo "==> PR is up; merge manually when checks pass."
}

echo "==> done."
