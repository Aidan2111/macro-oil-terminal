"""User dataclass + UserStore Protocol + store implementations (P1.1.1, P1.1.2).

Optional fields on :class:`User` are populated by later P1.x tasks
(P1.2 Alpaca, P1.6 onboarding, P1.7 notifications); they stay as stubs
here so the storage shape is stable from day one.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from azure.core.exceptions import HttpResponseError, ResourceNotFoundError
from azure.data.tables import TableClient, UpdateMode


_PARTITION_KEY = "users"


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


class UserStoreError(Exception):
    """Raised when the backing :class:`UserStore` fails unexpectedly.

    Callers upstream use this to decide whether to retry or surface a
    user-visible error. The original SDK exception is attached as
    ``__cause__`` (via ``raise ... from err``) for observability.
    """


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


# --- Table Storage translation helpers (P1.1.2) ----------------------------


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _parse_iso(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    dt = datetime.fromisoformat(str(value))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _entity_from_user(user: User) -> dict:
    """Flatten a :class:`User` to a Table Storage entity dict."""
    return {
        "PartitionKey": _PARTITION_KEY,
        "RowKey": user.sub,
        "email": user.email,
        "name": user.name,
        "picture_url": user.picture_url,
        "created_at": _iso(user.created_at),
        "updated_at": _iso(user.updated_at),
        "alpaca_refresh_token_ref": user.alpaca_refresh_token_ref,
        "alpaca_mode": user.alpaca_mode,
        "notification_prefs_json": user.notification_prefs_json,
        "onboarding_completed_at": _iso(user.onboarding_completed_at),
    }


def _user_from_entity(entity: dict) -> User:
    """Inverse of :func:`_entity_from_user`."""
    created_at = _parse_iso(entity.get("created_at"))
    updated_at = _parse_iso(entity.get("updated_at"))
    # created_at/updated_at are required on User; fall back to now_utc if
    # the row is somehow missing them (shouldn't happen for rows we wrote).
    now = _now_utc()
    return User(
        sub=entity["RowKey"],
        email=entity["email"],
        name=entity.get("name", "") or "",
        picture_url=entity.get("picture_url"),
        created_at=created_at or now,
        updated_at=updated_at or now,
        alpaca_refresh_token_ref=entity.get("alpaca_refresh_token_ref"),
        alpaca_mode=entity.get("alpaca_mode"),
        notification_prefs_json=entity.get("notification_prefs_json") or "{}",
        onboarding_completed_at=_parse_iso(entity.get("onboarding_completed_at")),
    )


class TableStorageUserStore:
    """Production :class:`UserStore` backed by Azure Table Storage.

    The constructor takes an already-configured
    :class:`azure.data.tables.TableClient` so tests can inject a mock.
    Call sites in production should use
    :meth:`TableStorageUserStore.from_connection_string`.
    """

    def __init__(self, table_client: TableClient) -> None:
        self._client = table_client

    @classmethod
    def from_connection_string(
        cls, conn_str: str, table_name: str = "users"
    ) -> "TableStorageUserStore":
        client = TableClient.from_connection_string(conn_str, table_name=table_name)
        return cls(table_client=client)

    # --- read ---------------------------------------------------------------

    def get(self, sub: str) -> User | None:
        try:
            entity = self._client.get_entity(
                partition_key=_PARTITION_KEY, row_key=sub
            )
        except ResourceNotFoundError:
            return None
        except HttpResponseError as err:
            raise UserStoreError(f"get({sub!r}) failed") from err
        return _user_from_entity(dict(entity))

    # --- write --------------------------------------------------------------

    def upsert_from_oidc_claims(self, claims: dict) -> User:
        sub = claims["sub"]
        now = _now_utc()
        try:
            existing_entity: dict | None
            try:
                existing_entity = dict(
                    self._client.get_entity(
                        partition_key=_PARTITION_KEY, row_key=sub
                    )
                )
            except ResourceNotFoundError:
                existing_entity = None

            if existing_entity is None:
                user = User(
                    sub=sub,
                    email=claims["email"],
                    name=claims.get("name", ""),
                    picture_url=claims.get("picture"),
                    created_at=now,
                    updated_at=now,
                )
            else:
                existing = _user_from_entity(existing_entity)
                user = replace(
                    existing,
                    email=claims["email"],
                    name=claims.get("name", existing.name),
                    picture_url=claims.get("picture", existing.picture_url),
                    updated_at=now,
                )
            self._client.upsert_entity(
                entity=_entity_from_user(user), mode=UpdateMode.MERGE
            )
        except HttpResponseError as err:
            raise UserStoreError(
                f"upsert_from_oidc_claims({sub!r}) failed"
            ) from err
        return user

    def update_preferences(self, sub: str, **fields: object) -> User:
        try:
            existing_entity = dict(
                self._client.get_entity(
                    partition_key=_PARTITION_KEY, row_key=sub
                )
            )
        except ResourceNotFoundError as err:
            raise KeyError(sub) from err
        except HttpResponseError as err:
            raise UserStoreError(f"update_preferences({sub!r}) failed") from err
        existing = _user_from_entity(existing_entity)
        user = replace(existing, **fields, updated_at=_now_utc())
        try:
            self._client.upsert_entity(
                entity=_entity_from_user(user), mode=UpdateMode.MERGE
            )
        except HttpResponseError as err:
            raise UserStoreError(f"update_preferences({sub!r}) failed") from err
        return user
