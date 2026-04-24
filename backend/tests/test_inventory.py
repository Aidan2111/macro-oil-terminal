"""Inventory endpoint tests.

Mocks ``providers.inventory.fetch_inventory`` so no EIA / FRED calls
happen during the test run.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.routers import inventory as inventory_router


def _synthetic_inventory(n: int = 120) -> pd.DataFrame:
    idx = pd.date_range("2023-01-06", periods=n, freq="W-FRI")
    commercial = np.linspace(450_000_000, 410_000_000, n)
    spr = np.linspace(350_000_000, 365_000_000, n)
    cushing = np.linspace(30_000_000, 28_000_000, n)
    df = pd.DataFrame(
        {
            "Commercial_bbls": commercial,
            "SPR_bbls": spr,
            "Cushing_bbls": cushing,
        },
        index=idx,
    )
    df["Total_Inventory_bbls"] = df["Commercial_bbls"] + df["SPR_bbls"]
    df.index.name = "Date"
    return df


def _patch_inventory(monkeypatch: pytest.MonkeyPatch, frame: pd.DataFrame) -> None:
    import providers.inventory as inv_mod  # type: ignore[import-not-found]

    def _fake() -> object:
        return SimpleNamespace(
            frame=frame, source="EIA-test",
            source_url="test://eia", fetched_at=pd.Timestamp.now("UTC"),
        )

    monkeypatch.setattr(inv_mod, "fetch_inventory", _fake)


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    inventory_router._invalidate_cache()


def test_inventory_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_inventory(monkeypatch, _synthetic_inventory())
    client = TestClient(create_app())
    r = client.get("/api/inventory")
    assert r.status_code == 200
    payload = r.json()
    assert {"commercial_bbls", "spr_bbls", "cushing_bbls", "forecast", "history"}.issubset(payload)
    assert payload["forecast"]["daily_depletion_bbls"] < 0  # synthetic draws down
    assert len(payload["history"]) >= 1


def test_inventory_500_on_empty_upstream(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_inventory(monkeypatch, pd.DataFrame())
    client = TestClient(create_app(), raise_server_exceptions=False)
    r = client.get("/api/inventory")
    assert r.status_code == 500


def test_inventory_cache_reuses_within_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}
    import providers.inventory as inv_mod  # type: ignore[import-not-found]
    frame = _synthetic_inventory()

    def _fake() -> object:
        calls["n"] += 1
        return SimpleNamespace(
            frame=frame, source="EIA", source_url="t://",
            fetched_at=pd.Timestamp.now("UTC"),
        )

    monkeypatch.setattr(inv_mod, "fetch_inventory", _fake)
    client = TestClient(create_app())
    assert client.get("/api/inventory").status_code == 200
    assert client.get("/api/inventory").status_code == 200
    assert calls["n"] == 1
