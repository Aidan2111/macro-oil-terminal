"""Authentication + user-store surface for Macro Oil Terminal (P1.1)."""

from auth.config import (
    AuthNotConfigured,
    boot_check,
    is_configured,
)
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
    "AuthNotConfigured",
    "InMemoryUserStore",
    "TableStorageUserStore",
    "User",
    "UserStore",
    "UserStoreError",
    "boot_check",
    "clear_cached_user",
    "current_user",
    "get_user_store",
    "is_configured",
    "render_login_gate",
    "require_auth",
    "requires_auth",
    "set_user_store",
]
