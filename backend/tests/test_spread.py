"""Spread endpoint tests.

Mocks the underlying ``providers.pricing.fetch_pricing_daily`` call so
the test doesn't hit yfinance. Covers happy-path shape, Pydantic
validation on a malformed payload, and TTL cache reuse.
"""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.routers import spread as spread_router


def _synthetic_prices(n: int = 200) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    brent = 85.0 + (pd.Series(range(n)) % 7) * 0.25
    wti = 80.0 + (pd.Series(range(n)) % 5) * 0.20
    return pd.DataFrame({"Brent": brent.values, "WTI": wti.values}, index=idx)


def _patch_pricing(monkeypatch: pytest.MonkeyPatch, frame: pd.DataFrame) -> None:
    import providers.pricing as pricing_mod  # type: ignore[import-not-found]

    def _fake_fetch() -> object:
        return SimpleNamespace(
            frame=frame,
            source="yfinance-test",
            kind="daily",
            source_url="test://",
            fetched_at=pd.Timestamp.now("UTC"),
        )

    monkeypatch.setattr(pricing_mod, "fetch_pricing_daily", _fake_fetch)


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    spread_router._invalidate_cache()


def test_spread_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_pricing(monkeypatch, _synthetic_prices())
    client = TestClient(create_app())
    r = client.get("/api/spread")
    assert r.status_code == 200
    payload = r.json()
    assert {"brent", "wti", "spread", "stretch_band", "history", "as_of"}.issubset(payload)
    assert payload["stretch_band"] in {"Calm", "Normal", "Stretched", "Very Stretched", "Extreme"}
    assert len(payload["history"]) == 90
    assert payload["history"][0]["date"] < payload["history"][-1]["date"]


def test_spread_500_on_empty_upstream(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_pricing(monkeypatch, pd.DataFrame({"Brent": [], "WTI": []}))
    client = TestClient(create_app(), raise_server_exceptions=False)
    r = client.get("/api/spread")
    assert r.status_code == 500


def test_spread_cache_reuses_within_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}
    import providers.pricing as pricing_mod  # type: ignore[import-not-found]
    frame = _synthetic_prices()

    def _fake_fetch() -> object:
        calls["n"] += 1
        return SimpleNamespace(
            frame=frame, source="yf", kind="daily",
            source_url="t://", fetched_at=pd.Timestamp.now("UTC"),
        )

    monkeypatch.setattr(pricing_mod, "fetch_pricing_daily", _fake_fetch)
    client = TestClient(create_app())
    assert client.get("/api/spread").status_code == 200
    assert client.get("/api/spread").status_code == 200
    assert calls["n"] == 1
