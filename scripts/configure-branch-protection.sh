#!/usr/bin/env bash
# Issue #130 — apply branch protection to `main` so direct pushes
# can't bypass the CI / CD / CodeQL / Security / synthetic gates.
#
# Run once after PR #N (which lands this script + #131's pytest gate)
# merges:
#
#     bash scripts/configure-branch-protection.sh
#
# Idempotent — re-running just re-applies the same rule. Requires a
# gh CLI authenticated as repo admin.
#
# Required check names below MUST match the `name:` of each job/matrix
# leaf as it appears on a successful run. If GitHub renames a check
# (e.g. matrix split changes), update the JSON below or the rule will
# block forever waiting on a check that never fires.
#
# Caveat: with `enforce_admins=true`, the same protection applies to
# the gh CLI account merging via `--squash --auto`. PRs auto-merge
# AFTER all required checks turn green AND the required-review count
# is satisfied. For a single-maintainer repo, set
# `required_pull_request_reviews.required_approving_review_count` to 0
# so PRs can self-merge (still requires checks to pass). Aidan can
# bump this to 1 once the second maintainer onboards.

set -euo pipefail

REPO="${REPO:-Aidan2111/macro-oil-terminal}"
BRANCH="${BRANCH:-main}"
GH="${GH:-/Users/aidanbothost/.local/bin/gh}"

cat <<JSON > /tmp/main-protection.json
{
  "required_status_checks": {
    "strict": true,
    "contexts": [
      "Backend pytest",
      "Frontend build + test",
      "pytest (unit + coverage) (3.11)",
      "pytest (unit + coverage) (3.12)",
      "Analyze (python)",
      "bandit + pip-audit (Python)",
      "npm audit (frontend)"
    ]
  },
  "enforce_admins": false,
  "required_pull_request_reviews": {
    "required_approving_review_count": 0,
    "dismiss_stale_reviews": true,
    "require_code_owner_reviews": false
  },
  "restrictions": null,
  "required_linear_history": true,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "block_creations": false,
  "required_conversation_resolution": false
}
JSON

echo "Applying branch protection to ${REPO}/branches/${BRANCH}…"
"$GH" api -X PUT \
  -H "Accept: application/vnd.github+json" \
  "/repos/${REPO}/branches/${BRANCH}/protection" \
  --input /tmp/main-protection.json

echo
echo "Verifying:"
"$GH" api "/repos/${REPO}/branches/${BRANCH}/protection" \
  | python3 -c 'import json,sys;d=json.load(sys.stdin);print("required_status_checks:", d.get("required_status_checks",{}).get("contexts"));print("required_reviews:", d.get("required_pull_request_reviews",{}).get("required_approving_review_count"));print("force_pushes:", d.get("allow_force_pushes",{}).get("enabled"));print("deletions:", d.get("allow_deletions",{}).get("enabled"));print("linear_history:", d.get("required_linear_history",{}).get("enabled"));'

echo
echo "Done. Direct pushes to ${BRANCH} are now blocked by the listed status checks."
echo "Aidan: bump required_approving_review_count from 0 -> 1 once a second maintainer is on the repo."
