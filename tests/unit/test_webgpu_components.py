"""Unit tests for WebGPU HTML template scaffolding."""

from __future__ import annotations

import pandas as pd


def test_hero_template_placeholders():
    from webgpu_components import _HERO_HTML
    for tok in ("__HEIGHT__", "__THREE_WEBGPU_URL__", "__THREE_CORE_URL__"):
        assert tok in _HERO_HTML
    assert "setAnimationLoop" in _HERO_HTML


def test_globe_template_placeholders():
    from webgpu_components import _GLOBE_HTML
    for tok in ("__POINTS_JSON__", "__THREE_TSL_URL__", "__EARTH_TEX_URL__"):
        assert tok in _GLOBE_HTML
    assert "InstancedMesh" in _GLOBE_HTML


def test_points_payload_basic():
    from webgpu_components import _points_payload
    from data_ingestion import fetch_ais_data
    from quantitative_models import categorize_flag_states
    det, _ = categorize_flag_states(fetch_ais_data(20).frame)
    pts = _points_payload(det)
    assert len(pts) == 20
    for p in pts:
        assert -90 <= p["lat"] <= 90
        assert -180 <= p["lon"] <= 180
        assert set(p.keys()) >= {"lat", "lon", "color", "cargo", "name", "flag", "category"}


def test_points_payload_empty():
    from webgpu_components import _points_payload
    assert _points_payload(pd.DataFrame()) == []
