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
from auth.widgets import (
    render_login_gate,
    require_auth,
    requires_auth,
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
    "render_login_gate",
    "require_auth",
    "requires_auth",
    "set_user_store",
]
