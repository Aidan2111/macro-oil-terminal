"""TDD test for _hours_to_next_eia_release helper (Task 1/6)."""

from datetime import datetime, timezone

from thesis_context import _hours_to_next_eia_release


def test_hours_to_next_eia_tuesday_before_release():
    now = datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc)  # Tue noon UTC
    # Next release: Wed 2026-04-22 14:30 UTC = 26.5 hours away
    assert abs(_hours_to_next_eia_release(now) - 26.5) < 0.1


def test_hours_to_next_eia_wednesday_after_release():
    now = datetime(2026, 4, 22, 15, 0, tzinfo=timezone.utc)  # Wed 15:00 UTC
    # Next release: Wed 2026-04-29 14:30 UTC = 167.5 hours away
    assert abs(_hours_to_next_eia_release(now) - 167.5) < 0.1


def test_hours_to_next_eia_is_none_when_now_is_none():
    assert _hours_to_next_eia_release(None) is None
