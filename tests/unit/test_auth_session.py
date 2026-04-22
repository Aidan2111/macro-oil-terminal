"""Unit tests for current_user() + MOCK_AUTH_USER seam (P1.1.3)."""

from __future__ import annotations

import hashlib

import pytest

from auth import InMemoryUserStore, User
from auth import session as auth_session
from auth.session import (
    clear_cached_user,
    current_user,
    get_user_store,
    set_user_store,
)


class _FakeUser:
    """Stands in for Streamlit's runtime ``st.user`` object."""

    def __init__(
        self,
        *,
        is_logged_in: bool,
        sub: str | None = None,
        email: str | None = None,
        name: str | None = None,
        picture: str | None = None,
    ) -> None:
        self.is_logged_in = is_logged_in
        self.sub = sub
        self.email = email
        self.name = name
        self.picture = picture

    def to_dict(self) -> dict:
        return {
            "sub": self.sub,
            "email": self.email,
            "name": self.name,
            "picture": self.picture,
        }


class _FakeStreamlit:
    """Minimal ``st`` stand-in: ``user`` + ``session_state`` dict."""

    def __init__(self, user: _FakeUser) -> None:
        self.user = user
        self.session_state: dict = {}


@pytest.fixture(autouse=True)
def _reset_session_state(monkeypatch):
    """Each test starts with a fresh store + no cached user + no st stub."""
    # Start every test with a known empty in-memory store so state never
    # leaks across tests (the module-level singleton is sticky otherwise).
    set_user_store(InMemoryUserStore())
    # Default: no streamlit runtime.
    monkeypatch.setattr(auth_session, "st", None)
    monkeypatch.setattr(auth_session, "_st_runtime_exists", lambda: False)
    yield
    clear_cached_user()


def test_current_user_returns_none_when_no_env_and_no_streamlit_user(
    monkeypatch,
) -> None:
    monkeypatch.delenv("MOCK_AUTH_USER", raising=False)
    monkeypatch.delenv("STREAMLIT_ENV", raising=False)

    assert current_user() is None


def test_current_user_returns_mock_when_env_set_and_not_prod(monkeypatch) -> None:
    email = "aidan@youbiquity.com"
    monkeypatch.setenv("MOCK_AUTH_USER", email)
    monkeypatch.setenv("STREAMLIT_ENV", "dev")

    user = current_user()

    assert isinstance(user, User)
    assert user.email == email
    expected_sub = f"mock:{hashlib.sha256(email.encode()).hexdigest()[:16]}"
    assert user.sub == expected_sub
    assert user.name == "Aidan"  # email.split("@")[0].title()
    assert user.picture_url is None


def test_current_user_ignores_mock_when_streamlit_env_is_prod(monkeypatch) -> None:
    monkeypatch.setenv("MOCK_AUTH_USER", "aidan@youbiquity.com")
    monkeypatch.setenv("STREAMLIT_ENV", "prod")

    assert current_user() is None


def test_current_user_upserts_store_from_streamlit_user_logged_in(
    monkeypatch,
) -> None:
    monkeypatch.delenv("MOCK_AUTH_USER", raising=False)
    monkeypatch.delenv("STREAMLIT_ENV", raising=False)

    fake_user = _FakeUser(
        is_logged_in=True,
        sub="g-abc123",
        email="real@example.com",
        name="Real Person",
        picture="https://example.com/pic.png",
    )
    fake_st = _FakeStreamlit(fake_user)
    monkeypatch.setattr(auth_session, "st", fake_st)
    monkeypatch.setattr(auth_session, "_st_runtime_exists", lambda: True)

    store = InMemoryUserStore()
    set_user_store(store)

    user = current_user()

    assert isinstance(user, User)
    assert user.sub == "g-abc123"
    assert user.email == "real@example.com"
    assert user.name == "Real Person"
    assert user.picture_url == "https://example.com/pic.png"

    persisted = store.get("g-abc123")
    assert persisted == user
    assert fake_st.session_state.get("_auth_user") == user


def test_current_user_cached_across_calls_within_session(monkeypatch) -> None:
    monkeypatch.delenv("MOCK_AUTH_USER", raising=False)
    monkeypatch.delenv("STREAMLIT_ENV", raising=False)

    fake_user = _FakeUser(
        is_logged_in=True,
        sub="g-abc123",
        email="real@example.com",
        name="Real Person",
        picture="https://example.com/pic.png",
    )
    fake_st = _FakeStreamlit(fake_user)
    monkeypatch.setattr(auth_session, "st", fake_st)
    monkeypatch.setattr(auth_session, "_st_runtime_exists", lambda: True)

    class _CountingStore(InMemoryUserStore):
        def __init__(self) -> None:
            super().__init__()
            self.upsert_calls = 0

        def upsert_from_oidc_claims(self, claims: dict) -> User:
            self.upsert_calls += 1
            return super().upsert_from_oidc_claims(claims)

    store = _CountingStore()
    set_user_store(store)

    first = current_user()
    second = current_user()
    third = current_user()

    assert first is second is third
    assert store.upsert_calls == 1
