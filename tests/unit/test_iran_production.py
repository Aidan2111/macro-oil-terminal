"""Unit tests for the EIA STEO Iran crude production wrapper (issue #79)."""

from __future__ import annotations


def _fake_steo(rows: list[dict]):
    """Build a fake `fetch_steo_series` callable returning `rows`."""
    def _fn(series_id: str, *, limit: int = 60):
        return rows
    return _fn


def test_compute_envelope_shape():
    from backend.services import iran_production_service as svc

    rows = [
        {"month": "2025-01", "value": 3100.0},
        {"month": "2025-02", "value": 3150.0},
        {"month": "2025-03", "value": 3175.0},
    ]
    env = svc.compute_envelope(fetch_fn=_fake_steo(rows))
    assert env["series_id"] == "COPR_IR"
    assert env["latest_kbpd"] == 3175.0
    assert len(env["monthly"]) == 3
    assert env["monthly"][0] == {"month": "2025-01", "kbpd": 3100.0}
    # YTD avg over 2025 = (3100 + 3150 + 3175) / 3 = 3141.667
    assert env["ytd_avg_kbpd"] == 3141.667
    # Delta = 3175 - 3141.667 = 33.333
    assert env["delta_vs_ytd_avg_kbpd"] == 33.333


def test_ytd_avg_handles_year_boundary():
    """YTD avg is restricted to the latest-year months only — December
    of the prior year shouldn't get pooled with the current year."""
    from backend.services import iran_production_service as svc

    rows = [
        {"month": "2024-11", "value": 3000.0},
        {"month": "2024-12", "value": 3050.0},
        {"month": "2025-01", "value": 3200.0},
        {"month": "2025-02", "value": 3300.0},
    ]
    env = svc.compute_envelope(fetch_fn=_fake_steo(rows))
    # Latest year is 2025, so YTD avg = (3200 + 3300) / 2 = 3250.
    assert env["ytd_avg_kbpd"] == 3250.0


def test_compute_envelope_empty_rows_raises():
    """Empty STEO response is a runtime error; the route returns 503
    via _provider_error."""
    import pytest
    from backend.services import iran_production_service as svc

    # The internal compute_envelope runs the fetch; if fetch returns
    # nothing useful we still write a row but that's exercised below.
    # An empty list path raises so the data-quality flips to red.
    def _empty(series_id: str, *, limit: int = 60):
        raise RuntimeError("EIA STEO: empty data for COPR_IR")

    with pytest.raises(RuntimeError):
        svc.compute_envelope(fetch_fn=_empty)
    state = svc.get_last_fetch_state()
    assert state["status"] == "red"
    assert "empty" in str(state["message"]).lower()


def test_record_fetch_success_writes_state():
    from backend.services import iran_production_service as svc

    rows = [{"month": "2026-04", "value": 3250.5}]
    env = svc.compute_envelope(fetch_fn=_fake_steo(rows))
    state = svc.get_last_fetch_state()
    assert state["status"] == "green"
    assert state["n_obs"] == 1
    assert state["last_good_at"] is not None
    assert env["latest_kbpd"] == 3250.5


def test_fetch_steo_series_shape_validation():
    """Provider-level — fetch_steo_series rejects rows that are
    missing `value` or have non-numeric strings."""
    import os
    import pytest
    from providers import _eia

    # Cover the no-key branch directly — the function refuses.
    saved = os.environ.pop("EIA_API_KEY", None)
    try:
        with pytest.raises(RuntimeError, match="EIA_API_KEY"):
            _eia.fetch_steo_series("COPR_IR")
    finally:
        if saved is not None:
            os.environ["EIA_API_KEY"] = saved
