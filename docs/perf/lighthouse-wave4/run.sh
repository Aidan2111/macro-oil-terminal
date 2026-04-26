#!/usr/bin/env bash
# Wave 4 Lighthouse runner.
#
# Hits the live SWA URL for every public route at desktop + mobile
# viewports and saves the JSON reports under
# docs/perf/lighthouse-wave4/{route}-{viewport}.json.
#
# Usage (from repo root or anywhere):
#     bash docs/perf/lighthouse-wave4/run.sh
#
# Pre-reqs:
#   - Node 20+ on PATH (npx will pull lighthouse if not installed).
#   - A Chrome / Chromium binary lighthouse can drive headlessly.
#
# The agent's sandboxed network is locked to a small allowlist that
# does not include Azure Static Web Apps, so this script must run
# from the user's host.
set -euo pipefail

BASE=https://delightful-pebble-00d8eb30f.7.azurestaticapps.net
OUT_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$OUT_DIR"

ROUTES=(
  "home:/"
  "macro:/macro/"
  "fleet:/fleet/"
  "positions:/positions/"
  "track-record:/track-record/"
)

run_one() {
  local name="$1" path="$2" viewport="$3"
  local out="$OUT_DIR/${name}-${viewport}.json"
  echo ">>> ${viewport} ${name} (${BASE}${path})"
  local preset_flag=""
  if [ "$viewport" = "desktop" ]; then
    preset_flag="--preset=desktop"
  fi
  npx -y lighthouse "${BASE}${path}" \
    --output=json \
    --output-path="${out}" \
    --quiet \
    --only-categories=performance,accessibility,best-practices,seo \
    ${preset_flag} \
    --chrome-flags="--headless=new --no-sandbox"
}

for entry in "${ROUTES[@]}"; do
  IFS=":" read -r name path <<< "$entry"
  for viewport in desktop mobile; do
    run_one "$name" "$path" "$viewport" || echo "  (failed — continuing)"
  done
done

echo
echo "Generating summary table…"
node "$OUT_DIR/summarise.mjs"
