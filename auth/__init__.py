"""Authentication + user-store surface for Macro Oil Terminal (P1.1)."""

from auth.session import (
    clear_cached_user,
    current_user,
    get_user_store,
    set_user_store,
)
from auth.user import (
    InMemoryUserStore,
    TableStorageUserStore,
    User,
    UserStore,
    UserStoreError,
)

__all__ = [
    "InMemoryUserStore",
    "TableStorageUserStore",
    "User",
    "UserStore",
    "UserStoreError",
    "clear_cached_user",
    "current_user",
    "get_user_store",
    "set_user_store",
]
