"""Unit tests for the _clamp helper living inside app.py.

We pull the function via regex rather than importing app.py, because
importing app.py instantiates Streamlit and we want these tests to be
fast and Streamlit-free.
"""

from __future__ import annotations

import pathlib
import re


def _load_clamp():
    source = pathlib.Path("app.py").read_text()
    m = re.search(r"def _clamp\(.*?(?=\ndef |\nst\.sidebar)", source, re.S)
    assert m, "could not locate _clamp in app.py"
    ns: dict = {}
    exec(m.group(0), ns)
    return ns["_clamp"]


def test_clamp_valid_range():
    _clamp = _load_clamp()
    assert _clamp(2.5, 0, 10, 5) == 2.5
    assert _clamp(-1, 0, 10, 5) == 0
    assert _clamp(99, 0, 10, 5) == 10


def test_clamp_nan_falls_back():
    _clamp = _load_clamp()
    assert _clamp(float("nan"), 0, 10, 5) == 5


def test_clamp_non_numeric_falls_back():
    _clamp = _load_clamp()
    assert _clamp("banana", 0, 10, 5) == 5
    assert _clamp(None, 0, 10, 5) == 5


def test_clamp_inf_falls_back():
    _clamp = _load_clamp()
    assert _clamp(float("inf"), 0, 10, 5) == 5
    assert _clamp(float("-inf"), 0, 10, 5) == 5
