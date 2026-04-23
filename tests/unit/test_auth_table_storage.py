"""Unit tests for the TableStorageUserStore (P1.1.2)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from azure.core.exceptions import HttpResponseError, ResourceNotFoundError

from auth import User, UserStore
from auth.user import TableStorageUserStore, UserStoreError


def _claims() -> dict:
    return {
        "sub": "g-123",
        "email": "a@b.c",
        "name": "A",
        "picture": "https://example.com/pic.png",
    }


def test_table_storage_upsert_translates_to_entity() -> None:
    mock_client = MagicMock()
    # First write: no existing row.
    mock_client.get_entity.side_effect = ResourceNotFoundError("not found")
    store = TableStorageUserStore(table_client=mock_client)
    assert isinstance(store, UserStore)

    user = store.upsert_from_oidc_claims(_claims())

    assert mock_client.upsert_entity.call_count == 1
    args, kwargs = mock_client.upsert_entity.call_args
    entity = kwargs.get("entity", args[0] if args else None)
    assert entity["PartitionKey"] == "users"
    assert entity["RowKey"] == "g-123"
    assert entity["email"] == "a@b.c"
    assert entity["name"] == "A"
    assert entity["picture_url"] == "https://example.com/pic.png"
    assert isinstance(entity["created_at"], str)
    assert isinstance(entity["updated_at"], str)
    # created_at and updated_at match on first write.
    assert entity["created_at"] == entity["updated_at"]
    assert user.sub == "g-123"
    assert user.email == "a@b.c"


def test_table_storage_get_round_trip() -> None:
    canned = {
        "PartitionKey": "users",
        "RowKey": "g-123",
        "email": "a@b.c",
        "name": "Alice",
        "picture_url": "https://example.com/a.png",
        "created_at": "2026-04-22T12:00:00+00:00",
        "updated_at": "2026-04-22T12:30:00+00:00",
        "alpaca_refresh_token_ref": None,
        "alpaca_mode": None,
        "notification_prefs_json": "{}",
        "onboarding_completed_at": None,
    }
    mock_client = MagicMock()
    mock_client.get_entity.return_value = canned

    store = TableStorageUserStore(table_client=mock_client)
    got = store.get("g-123")

    assert isinstance(got, User)
    assert got.sub == "g-123"
    assert got.email == "a@b.c"
    assert got.name == "Alice"
    assert got.picture_url == "https://example.com/a.png"
    assert got.created_at == datetime(2026, 4, 22, 12, 0, 0, tzinfo=timezone.utc)
    assert got.updated_at == datetime(2026, 4, 22, 12, 30, 0, tzinfo=timezone.utc)
    mock_client.get_entity.assert_called_once_with(
        partition_key="users", row_key="g-123"
    )


def test_table_storage_get_returns_none_on_resource_not_found() -> None:
    mock_client = MagicMock()
    mock_client.get_entity.side_effect = ResourceNotFoundError("missing")
    store = TableStorageUserStore(table_client=mock_client)

    assert store.get("missing") is None


def test_table_storage_500_wraps_in_user_store_error() -> None:
    mock_client = MagicMock()
    boom = HttpResponseError("500 backend error")
    # get_entity is called first inside upsert to preserve created_at;
    # make that call blow up with a 500 so we exercise the wrap path.
    mock_client.get_entity.side_effect = boom
    store = TableStorageUserStore(table_client=mock_client)

    with pytest.raises(UserStoreError) as excinfo:
        store.upsert_from_oidc_claims(_claims())

    assert excinfo.value.__cause__ is boom
