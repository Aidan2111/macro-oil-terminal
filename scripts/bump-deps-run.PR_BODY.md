# Coordinated Python dep major-bump

Brings the analytical Python stack onto the 2026 floor:

| package        | from        | to              | risk   | why bumped now |
| -------------- | ----------- | --------------- | ------ | -------------- |
| `numpy`        | `>=1.24.0`  | `>=2.4.4`       | LOW    | NumPy 2.x ABI is now the install default; sklearn 1.8 / pandas 3 require it. |
| `pandas`       | `>=2.0.0`   | `>=3.0.2`       | MEDIUM | 3.0 removes `Timestamp.utcnow()` and `Timestamp.utcfromtimestamp()`; we migrate every call site (see commit). |
| `scikit-learn` | `>=1.3.0`   | `>=1.8.0`       | LOW    | Only one usage (`LinearRegression` in `quantitative_models.py`) — public API unchanged. |
| `arch`         | `>=7.0.0`   | `>=8.0.0`       | LOW    | `arch_model(...).fit(disp="off", show_warning=False)` is unchanged in 8.x. |
| `statsmodels`  | `>=0.14.0`  | `>=0.14.6`      | LOW    | Patch-stream bump; `adfuller` / `OLS` / `add_constant` are unchanged. |

## Migration patches in this PR

Pandas 3 removed `Timestamp.utcnow()` and `Timestamp.utcfromtimestamp()`. Every
call site is rewritten by `scripts/bump-deps-migrations/01_apply_python_migrations.py`:

- `pd.Timestamp.utcnow()` → `pd.Timestamp.now(tz="UTC").tz_convert(None)`
  (preserves naive-UTC semantics — `fetched_at` consumers stringify it via
  `.strftime("%Y-%m-%d %H:%M:%SZ")`, so the trailing `Z` keeps reading as UTC.)
- `pd.Timestamp.utcfromtimestamp(x)` → `pd.Timestamp.fromtimestamp(x, tz="UTC").tz_convert(None)`
- `datetime.utcnow()` → `datetime.now(timezone.utc).replace(tzinfo=None)`
  (Python 3.13 deprecation hygiene; required imports are added.)

Touched files (24 utcnow + 1 utcfromtimestamp + 3 datetime.utcnow):

- `providers/inventory.py`, `providers/_cftc.py`, `providers/pricing.py`,
  `providers/_polygon.py`, `providers/_yfinance.py`
- `thesis_context.py`, `data_ingestion.py`, `crack_spread.py`, `app.py`
- `tests/unit/test_coverage_gaps.py`, `tests/unit/test_thesis_context_full.py`,
  `tests/unit/test_cftc_integration.py`

## Explicitly out of scope

- **`openai`** stays on `>=1.50.0`. The Foundry path
  (`backend/services/trade_thesis_foundry.py`) drives `client.beta.assistants.*`
  and `client.beta.threads.*` heavily; openai 2.x removed that surface in favour
  of the Responses API. That migration is a separate PR.
- **`yfinance`** stays on `>=0.2.40`. The 0.2 → 1.3 jump pulls in `curl_cffi`,
  `peewee`, `protobuf` and reshapes the public API. The existing call sites
  already pass `auto_adjust=False` explicitly, so the headline 1.0 default flip
  is a no-op for us — but the broader transitive-dep churn deserves its own PR.
- **`azure-ai-projects`** / **`azure-identity`** untouched (recently bumped).
- **Frontend deps** untouched.
- **`Dockerfile`** untouched (separate Python 3.14 dependabot PR is in flight).

## Local verification

Built against Homebrew Python 3.13 in a new `.venv313/` (the existing `.venv/`
is Xcode's 3.9.6 and is left alone). Both `tests/unit/` and `backend/tests/`
must pass before this PR is pushed; the playbook script
(`scripts/bump-deps-run.sh`) won't push unless they're green.

## Follow-ups

- [ ] `feat(deps): openai 2.x + Foundry Assistants→Responses migration`
- [ ] `feat(deps): yfinance 1.3 + transitive dep audit (curl_cffi / peewee / protobuf)`
- [ ] `chore(ci): bump CI runner Python from 3.10 → 3.13 once the matrix accepts it`
