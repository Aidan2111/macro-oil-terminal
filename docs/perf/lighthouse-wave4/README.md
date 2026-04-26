# Wave 4 Lighthouse summary

Run via `bash docs/perf/lighthouse-wave4/run.sh` from the user's host
(the agent's sandboxed network is locked to a small allowlist that
does not include Azure Static Web Apps, so live-URL Lighthouse runs
must happen on the host).

The runner saves a JSON report per `{route}-{viewport}` pair in this
directory; `summarise.mjs` walks them and rewrites this README with
a real table once results land.

| Route | Viewport | Perf | A11y | BP | SEO |
|-------|----------|-----:|-----:|---:|----:|
| home  | desktop  | _pending_ | _pending_ | _pending_ | _pending_ |
| home  | mobile   | _pending_ | _pending_ | _pending_ | _pending_ |
| macro | desktop  | _pending_ | _pending_ | _pending_ | _pending_ |
| macro | mobile   | _pending_ | _pending_ | _pending_ | _pending_ |
| fleet | desktop  | _pending_ | _pending_ | _pending_ | _pending_ |
| fleet | mobile   | _pending_ | _pending_ | _pending_ | _pending_ |
| positions | desktop | _pending_ | _pending_ | _pending_ | _pending_ |
| positions | mobile  | _pending_ | _pending_ | _pending_ | _pending_ |
| track-record | desktop | _pending_ | _pending_ | _pending_ | _pending_ |
| track-record | mobile  | _pending_ | _pending_ | _pending_ | _pending_ |

Targets: ≥90 perf / 100 a11y / 100 BP / 100 SEO.
