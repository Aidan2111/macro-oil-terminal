# Wave 4 Lighthouse summary

Run via `bash docs/perf/lighthouse-wave4/run.sh` from the
user's host (the agent's sandbox cannot reach the live SWA).

| Route | Viewport | Perf | A11y | BP | SEO |
|-------|----------|-----:|-----:|---:|----:|
| fleet | desktop | 99 | 100 | 92 | 100 |
| fleet | mobile | 93 | 100 | 92 | 100 |
| home | desktop | 93 | 96 | 100 | 100 |
| home | mobile | 79 | 96 | 100 | 100 |
| macro | desktop | 96 | 96 | 100 | 100 |
| macro | mobile | 92 | 96 | 100 | 100 |
| positions | desktop | 98 | 100 | 100 | 100 |
| positions | mobile | 97 | 100 | 100 | 100 |
| track-record | desktop | 97 | 100 | 100 | 100 |
| track-record | mobile | 92 | 100 | 100 | 100 |

Targets: ≥90 perf / 100 a11y / 100 BP / 100 SEO.
