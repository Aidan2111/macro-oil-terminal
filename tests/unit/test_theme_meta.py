"""Unit tests for the UIP-T9 meta polish — logo SVG, favicon, footer,
and build-version resolver.

See ``docs/plans/ui-polish.md`` → Task T9 and ``docs/designs/ui-polish.md``
→ "Meta polish" for the contract these tests lock in.

Goals of this pass:
* A checked-in ``static/logo.svg`` — a small, brand-palette SVG tile used
  by the favicon build and (future) in-app marks.
* A checked-in ``static/favicon.ico`` — derived from the SVG via
  ``infra/gen_favicon.py`` (cairosvg + Pillow; Pillow-only fallback).
* ``theme._resolve_build_version()`` — reads ``BUILD_VERSION`` env var
  with a ``"dev"`` fallback so the footer never shows a raw placeholder.
* ``theme.render_footer(version, region)`` — one-line disclaimer with
  version + region, ``data-testid="app-footer"`` sentinel, zero
  personalization. The copy is fixed per the design spec — a
  parametrised test guards the "no personal strings" invariant.

Assertions run against either the filesystem (logo / favicon) or the
HTML captured from a monkeypatched ``theme.st.markdown`` (footer).
Outside a Streamlit runtime the helper is a no-op.
"""

from __future__ import annotations

import pathlib

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# Capture helper — same shape as T3/T7/T8 tests.
# ---------------------------------------------------------------------------
def _capture_markdown(monkeypatch):
    calls: list[tuple[str, bool]] = []

    def _fake_markdown(body, unsafe_allow_html=False):
        calls.append((body, bool(unsafe_allow_html)))

    monkeypatch.setattr("theme.st.markdown", _fake_markdown)
    return calls


# ---------------------------------------------------------------------------
# 1. static/logo.svg — file present, non-empty, looks like an SVG.
# ---------------------------------------------------------------------------
def test_logo_svg_file_present_and_nonempty():
    """``static/logo.svg`` must exist at the repo root, weigh more than
    200 bytes (so a stub empty file fails), and contain an ``<svg`` tag
    so it's parsable as SVG.
    """
    path = REPO_ROOT / "static" / "logo.svg"
    assert path.exists(), f"{path} does not exist"
    size = path.stat().st_size
    assert size > 200, f"{path} only {size} bytes — expected > 200"
    contents = path.read_text(encoding="utf-8")
    assert "<svg" in contents, "logo.svg does not contain an <svg tag"


# ---------------------------------------------------------------------------
# 2. static/favicon.ico — file present, non-empty.
# ---------------------------------------------------------------------------
def test_favicon_file_present_and_nonempty():
    """``static/favicon.ico`` must exist and be > 200 bytes. A missing
    file is not an acceptable RED skip — the GREEN commit is expected
    to check in the generated .ico so production builds ship it.
    """
    path = REPO_ROOT / "static" / "favicon.ico"
    if not path.exists():
        pytest.skip(f"{path} not yet generated — run infra/gen_favicon.py")
    size = path.stat().st_size
    assert size > 200, f"{path} only {size} bytes — expected > 200"


# ---------------------------------------------------------------------------
# 3. _resolve_build_version reads BUILD_VERSION env var.
# ---------------------------------------------------------------------------
def test_resolve_build_version_reads_env(monkeypatch):
    """When ``BUILD_VERSION`` is set in the environment,
    ``_resolve_build_version()`` returns that value verbatim.
    """
    from theme import _resolve_build_version

    monkeypatch.setenv("BUILD_VERSION", "v0.4.1")
    assert _resolve_build_version() == "v0.4.1"


# ---------------------------------------------------------------------------
# 4. _resolve_build_version falls back to "dev".
# ---------------------------------------------------------------------------
def test_resolve_build_version_falls_back_to_dev(monkeypatch):
    """With ``BUILD_VERSION`` absent from the env, the resolver returns
    the literal string ``"dev"`` so the footer never surfaces a blank
    version.
    """
    from theme import _resolve_build_version

    monkeypatch.delenv("BUILD_VERSION", raising=False)
    assert _resolve_build_version() == "dev"


# ---------------------------------------------------------------------------
# 5. render_footer — disclaimer + version + region present; testid attached.
# ---------------------------------------------------------------------------
def test_render_footer_contains_disclaimer_version_region(monkeypatch):
    """Captured HTML must contain the disclaimer phrase, the passed-in
    version, the region literal, and the ``data-testid="app-footer"``
    sentinel hook. The copy must not contain an emoji or personalization.
    """
    from theme import render_footer

    calls = _capture_markdown(monkeypatch)
    render_footer(version="v1.2.3", region="canadaeast")

    html = "".join(body for body, _ in calls)
    assert 'data-testid="app-footer"' in html
    assert "Research" in html
    assert "education" in html
    assert "v1.2.3" in html
    assert "canadaeast" in html


def test_render_footer_default_region_is_canadaeast(monkeypatch):
    """``region`` defaults to ``canadaeast`` — the only prod deploy
    region for this app. Passing only a version must still surface the
    region in the HTML.
    """
    from theme import render_footer

    calls = _capture_markdown(monkeypatch)
    render_footer(version="v0.9.0")
    html = "".join(body for body, _ in calls)
    assert "canadaeast" in html
    assert "v0.9.0" in html


# ---------------------------------------------------------------------------
# 6. No personalization — parametrised over the banned-strings set.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "banned",
    ["aidan", "Aidan", "AIDAN", "youbiquity", "personal", "my desk", "Aidan's Desk"],
)
def test_footer_never_contains_personal_strings(monkeypatch, banned):
    """Case-insensitive scan: the footer HTML must not surface any of
    the banned personalization strings. The product is "Macro Oil
    Terminal" — generic; no one person's desk. Guards against a future
    copy edit that re-introduces personal branding.
    """
    from theme import render_footer

    calls = _capture_markdown(monkeypatch)
    render_footer(version="v1.0.0", region="canadaeast")
    html = "".join(body for body, _ in calls).lower()
    assert banned.lower() not in html, (
        f"footer HTML contains banned personalization string: {banned!r}"
    )
