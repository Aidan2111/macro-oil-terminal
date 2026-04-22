"""User dataclass + UserStore Protocol + in-memory implementation (P1.1.1).

Optional fields on :class:`User` are populated by later P1.x tasks
(P1.2 Alpaca, P1.6 onboarding, P1.7 notifications); they stay as stubs
here so the storage shape is stable from day one.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class User:
    """Authenticated user row keyed by the OIDC ``sub`` claim."""

    sub: str
    email: str
    name: str
    picture_url: str | None
    created_at: datetime
    updated_at: datetime
    alpaca_refresh_token_ref: str | None = None
    alpaca_mode: str | None = None
    notification_prefs_json: str = "{}"
    onboarding_completed_at: datetime | None = None


@runtime_checkable
class UserStore(Protocol):
    """Persistence contract for :class:`User` rows."""

    def get(self, sub: str) -> User | None: ...

    def upsert_from_oidc_claims(self, claims: dict) -> User: ...

    def update_preferences(self, sub: str, **fields: object) -> User: ...


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class InMemoryUserStore:
    """Dict-backed :class:`UserStore` for tests and local dev."""

    def __init__(self) -> None:
        self._rows: dict[str, User] = {}

    def get(self, sub: str) -> User | None:
        return self._rows.get(sub)

    def upsert_from_oidc_claims(self, claims: dict) -> User:
        sub = claims["sub"]
        now = _now_utc()
        existing = self._rows.get(sub)
        if existing is None:
            user = User(
                sub=sub,
                email=claims["email"],
                name=claims.get("name", ""),
                picture_url=claims.get("picture"),
                created_at=now,
                updated_at=now,
            )
        else:
            user = replace(
                existing,
                email=claims["email"],
                name=claims.get("name", existing.name),
                picture_url=claims.get("picture", existing.picture_url),
                updated_at=now,
            )
        self._rows[sub] = user
        return user

    def update_preferences(self, sub: str, **fields: object) -> User:
        existing = self._rows.get(sub)
        if existing is None:
            raise KeyError(sub)
        user = replace(existing, **fields, updated_at=_now_utc())
        self._rows[sub] = user
        return user
