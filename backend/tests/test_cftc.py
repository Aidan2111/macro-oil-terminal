"""CFTC endpoint tests.

Mocks ``providers._cftc.fetch_wti_positioning`` so the test doesn't
download the CFTC yearly zip.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.routers import cftc as cftc_router


def _synthetic_cot(n: int = 160) -> pd.DataFrame:
    idx = pd.date_range("2023-01-03", periods=n, freq="W-TUE")
    rng = np.random.default_rng(42)
    mm_net = rng.integers(-100_000, 250_000, n)
    producer_net = rng.integers(-300_000, -50_000, n)
    swap_net = rng.integers(-200_000, 100_000, n)
    df = pd.DataFrame(
        {
            "mm_net": mm_net.astype(int),
            "producer_net": producer_net.astype(int),
            "swap_net": swap_net.astype(int),
            "open_interest": rng.integers(1_500_000, 2_500_000, n).astype(int),
            "market": "WTI-PHYSICAL - NEW YORK MERCANTILE EXCHANGE",
        },
        index=idx,
    )
    df.index.name = "date"
    return df


def _patch_cftc(monkeypatch: pytest.MonkeyPatch, frame: pd.DataFrame) -> None:
    import providers._cftc as cftc_mod  # type: ignore[import-not-found]

    def _fake(years=None) -> object:
        return SimpleNamespace(
            frame=frame, source_url="test://cftc",
            fetched_at=pd.Timestamp.now("UTC"),
            market_name="WTI-PHYSICAL - NEW YORK MERCANTILE EXCHANGE",
            weeks=len(frame),
        )

    monkeypatch.setattr(cftc_mod, "fetch_wti_positioning", _fake)


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    cftc_router._invalidate_cache()


def test_cftc_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_cftc(monkeypatch, _synthetic_cot())
    client = TestClient(create_app())
    r = client.get("/api/cftc")
    assert r.status_code == 200
    payload = r.json()
    assert {"mm_net", "commercial_net", "mm_zscore_3y", "history"}.issubset(payload)
    assert isinstance(payload["mm_net"], int)
    assert len(payload["history"]) == 160


def test_cftc_500_on_empty_upstream(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_cftc(monkeypatch, pd.DataFrame())
    client = TestClient(create_app(), raise_server_exceptions=False)
    r = client.get("/api/cftc")
    assert r.status_code == 500


def test_cftc_cache_reuses_within_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}
    import providers._cftc as cftc_mod  # type: ignore[import-not-found]
    frame = _synthetic_cot()

    def _fake(years=None) -> object:
        calls["n"] += 1
        return SimpleNamespace(
            frame=frame, source_url="t://", fetched_at=pd.Timestamp.now("UTC"),
            market_name="WTI-PHYSICAL", weeks=len(frame),
        )

    monkeypatch.setattr(cftc_mod, "fetch_wti_positioning", _fake)
    client = TestClient(create_app())
    assert client.get("/api/cftc").status_code == 200
    assert client.get("/api/cftc").status_code == 200
    assert calls["n"] == 1
