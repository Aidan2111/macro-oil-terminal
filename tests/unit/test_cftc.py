"""CFTC COT provider coverage — mocked network path + schema validation."""

from __future__ import annotations

import io
import zipfile

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_WTI_NAME = "WTI-PHYSICAL - NEW YORK MERCANTILE EXCHANGE"

_CSV_HEADER = ",".join([
    "Market_and_Exchange_Names",
    "Report_Date_as_YYYY-MM-DD",
    "Open_Interest_All",
    "Prod_Merc_Positions_Long_All", "Prod_Merc_Positions_Short_All",
    "Swap_Positions_Long_All", "Swap__Positions_Short_All",
    "M_Money_Positions_Long_All", "M_Money_Positions_Short_All",
    "Other_Rept_Positions_Long_All", "Other_Rept_Positions_Short_All",
    "NonRept_Positions_Long_All", "NonRept_Positions_Short_All",
])


def _build_zip(rows):
    """Rows: list of dicts (one per weekly report row)."""
    import csv
    buf = io.StringIO()
    fieldnames = _CSV_HEADER.split(",")
    writer = csv.DictWriter(buf, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
    writer.writeheader()
    for r in rows:
        writer.writerow({k: r.get(k, 0) for k in fieldnames})
    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w") as zf:
        zf.writestr("f_year.txt", buf.getvalue())
    zbuf.seek(0)
    return zbuf.getvalue()


def _synthetic_rows(n=30, seed=7):
    import random
    rng = random.Random(seed)
    start = pd.Timestamp("2024-01-02")
    rows = []
    for i in range(n):
        d = (start + pd.Timedelta(days=7 * i)).strftime("%Y-%m-%d")
        mm_long = 150_000 + rng.randint(-20_000, 20_000)
        mm_short = 50_000 + rng.randint(-10_000, 10_000)
        rows.append({
            "Market_and_Exchange_Names": _WTI_NAME,
            "Report_Date_as_YYYY-MM-DD": d,
            "Open_Interest_All": 2_000_000,
            "Prod_Merc_Positions_Long_All": 300_000,
            "Prod_Merc_Positions_Short_All": 20_000,
            "Swap_Positions_Long_All": 150_000,
            "Swap__Positions_Short_All": 700_000,
            "M_Money_Positions_Long_All": mm_long,
            "M_Money_Positions_Short_All": mm_short,
            "Other_Rept_Positions_Long_All": 110_000,
            "Other_Rept_Positions_Short_All": 60_000,
            "NonRept_Positions_Long_All": 50_000,
            "NonRept_Positions_Short_All": 45_000,
        })
    return rows


class _FakeResp:
    def __init__(self, content, status_code=200):
        self.content = content
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.fixture(autouse=True)
def _reset_cache():
    from providers import _cftc
    _cftc._CACHE.clear()
    yield
    _cftc._CACHE.clear()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def test_fetch_happy_path(monkeypatch):
    from providers import _cftc

    content = _build_zip(_synthetic_rows(n=10))
    monkeypatch.setattr("providers._cftc.requests.get", lambda *a, **kw: _FakeResp(content))
    result = _cftc.fetch_wti_positioning(years=[2024])
    assert result.weeks == 10
    assert result.market_name == _WTI_NAME
    # Schema
    for col in ("mm_net", "producer_net", "swap_net", "other_rept_net", "nonrept_net", "open_interest"):
        assert col in result.frame.columns, f"missing column {col}"
    # Net = Long - Short by construction
    row = result.frame.iloc[-1]
    assert row["producer_net"] == 300_000 - 20_000
    assert row["swap_net"] == 150_000 - 700_000


def test_fetch_cache_hit(monkeypatch):
    from providers import _cftc

    content = _build_zip(_synthetic_rows(n=6))
    calls = {"n": 0}

    def _counting_get(*a, **kw):
        calls["n"] += 1
        return _FakeResp(content)

    monkeypatch.setattr("providers._cftc.requests.get", _counting_get)
    _cftc.fetch_wti_positioning(years=[2024])
    _cftc.fetch_wti_positioning(years=[2024])  # cached
    assert calls["n"] == 1


def test_fetch_failure_when_no_years(monkeypatch):
    from providers import _cftc

    def _always_fail(*a, **kw):
        return _FakeResp(b"", status_code=500)

    monkeypatch.setattr("providers._cftc.requests.get", _always_fail)
    with pytest.raises(RuntimeError, match="no WTI data"):
        _cftc.fetch_wti_positioning(years=[2024])


def test_managed_money_zscore_returns_none_when_short():
    from providers import _cftc
    # Only 5 rows — below the min=20 guardrail
    df = pd.DataFrame({"mm_net": [100, 200, 300, 400, 500]}, index=pd.date_range("2024-01-01", periods=5, freq="W"))
    assert _cftc.managed_money_zscore(df) is None


def test_managed_money_zscore_happy_path():
    from providers import _cftc
    import numpy as np
    rng = np.random.default_rng(0)
    s = rng.normal(0, 10_000, 200).cumsum() + 100_000
    df = pd.DataFrame({"mm_net": s}, index=pd.date_range("2022-01-01", periods=200, freq="W"))
    z = _cftc.managed_money_zscore(df)
    assert z is not None
    assert -4.0 < z < 4.0


def test_filter_wti_prefers_canonical_market():
    from providers import _cftc
    import pandas as pd
    df = pd.DataFrame({
        "Market_and_Exchange_Names": [
            "CRUDE OIL, LIGHT SWEET-WTI - ICE FUTURES EUROPE",
            _WTI_NAME,
        ],
        "report_date": [pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-09")],
    })
    # Canonical NYMEX name wins when present
    wti = _cftc._filter_wti(df)
    assert wti["_matched_market"].iloc[0] == _WTI_NAME


def test_health_check_handles_failure(monkeypatch):
    from providers import _cftc

    def _boom(*a, **kw):
        raise RuntimeError("network down")

    monkeypatch.setattr("providers._cftc.requests.head", _boom)
    h = _cftc.health_check(timeout=1.0)
    assert h["ok"] is False
    assert "network down" in h["note"]
