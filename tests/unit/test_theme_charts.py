"""Unit tests for ``theme.apply_theme`` + chart polish helpers — UIP-T5.

See ``docs/plans/ui-polish.md`` → Task T5 and ``docs/designs/ui-polish.md``
→ ``theme.apply_theme(fig)`` for the contract locked in here.

Three helpers ship in T5:

* ``apply_theme(fig)`` — in-place mutation of a Plotly ``go.Figure``
  layout: paper/plot background, gridline tint, hoverlabel styling,
  fixed margins, cyan-first colorway. Returns the same figure.
* ``pretty_axis_label(raw)`` — snake-case → plain-English axis label
  via ``language.TERMS`` with a title-case-plus-suffix-rules fallback.
* ``format_money_hover(value)`` — ``$X,XXX.XX`` helper for hover
  templates.

Tests that touch ``go.Figure`` are guarded by ``pytest.importorskip`` so
a minimal venv without Plotly still collects cleanly; CI ships Plotly.
"""

from __future__ import annotations

import pytest

# Plotly guard — the theme helpers themselves do not import plotly at
# module load, so ``import theme`` stays cheap; only the figure-level
# tests need plotly.
go = pytest.importorskip("plotly.graph_objects")

import theme
from theme import PALETTE, apply_theme, format_money_hover, pretty_axis_label


# ---------------------------------------------------------------------------
# apply_theme — layout mutation
# ---------------------------------------------------------------------------
def _make_fig():
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=[1, 2, 3], y=[4, 5, 6], name="demo"))
    return fig


def test_apply_theme_sets_palette_colors():
    fig = _make_fig()
    apply_theme(fig)
    assert fig.layout.paper_bgcolor == PALETTE.bg_1
    assert fig.layout.plot_bgcolor == PALETTE.bg_1
    assert fig.layout.xaxis.gridcolor == PALETTE.gridline
    assert fig.layout.yaxis.gridcolor == PALETTE.gridline


def test_apply_theme_sets_colorway_primary_first():
    fig = _make_fig()
    apply_theme(fig)
    assert tuple(fig.layout.colorway)[0] == PALETTE.primary


def test_apply_theme_sets_margins_per_design_spec():
    fig = _make_fig()
    apply_theme(fig)
    assert fig.layout.margin.l == 40
    assert fig.layout.margin.r == 20
    assert fig.layout.margin.t == 40
    assert fig.layout.margin.b == 30


def test_apply_theme_preserves_existing_traces():
    fig = _make_fig()
    apply_theme(fig)
    assert len(fig.data) == 1


def test_apply_theme_returns_same_figure():
    fig = _make_fig()
    assert apply_theme(fig) is fig


# ---------------------------------------------------------------------------
# pretty_axis_label + format_money_hover
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("z_score", "Spread Stretch"),
        ("stretch", "Spread Stretch"),
        ("conviction", "Confidence"),
        ("spread_usd", "Spread ($)"),
        ("unknown_field", "Unknown Field"),
    ],
)
def test_pretty_axis_label_maps_known_keys(raw, expected):
    assert pretty_axis_label(raw) == expected


def test_format_money_hover_commas_and_two_decimals():
    assert format_money_hover(1234567.891) == "$1,234,567.89"
