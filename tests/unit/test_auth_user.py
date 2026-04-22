"""Unit tests for the User dataclass + InMemoryUserStore (P1.1.1)."""

from __future__ import annotations

import dataclasses
import time
from datetime import datetime, timezone

from auth import InMemoryUserStore, User, UserStore


def _sample_user() -> User:
    now = datetime(2026, 4, 22, 12, 0, 0, tzinfo=timezone.utc)
    return User(
        sub="g-abc123",
        email="a@b.c",
        name="Alice",
        picture_url="https://example.com/a.png",
        created_at=now,
        updated_at=now,
    )


def test_user_dataclass_round_trip() -> None:
    user = _sample_user()
    as_dict = dataclasses.asdict(user)
    rebuilt = User(**as_dict)
    assert rebuilt == user
    # Optional fields round-trip with their defaults.
    assert rebuilt.alpaca_refresh_token_ref is None
    assert rebuilt.alpaca_mode is None
    assert rebuilt.notification_prefs_json == "{}"
    assert rebuilt.onboarding_completed_at is None


def test_in_memory_user_store_upsert_creates_user_with_equal_timestamps_on_first_call() -> None:
    store = InMemoryUserStore()
    assert isinstance(store, UserStore)
    claims = {
        "sub": "g-123",
        "email": "a@b.c",
        "name": "A",
        "picture": "https://example.com/pic.png",
    }
    created = store.upsert_from_oidc_claims(claims)
    assert created.sub == "g-123"
    assert created.email == "a@b.c"
    assert created.name == "A"
    assert created.picture_url == "https://example.com/pic.png"
    assert created.created_at == created.updated_at
    assert store.get("g-123") == created


def test_in_memory_user_store_upsert_is_idempotent_and_bumps_updated_at() -> None:
    store = InMemoryUserStore()
    claims = {
        "sub": "g-123",
        "email": "a@b.c",
        "name": "A",
        "picture": "https://example.com/pic.png",
    }
    first = store.upsert_from_oidc_claims(claims)
    time.sleep(0.002)
    second = store.upsert_from_oidc_claims(claims)
    assert second.sub == first.sub
    assert second.created_at == first.created_at
    assert second.updated_at > first.created_at
    assert store.get("g-123") == second
