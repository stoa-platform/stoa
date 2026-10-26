"""Expected role and permission cases; no new permission policy."""

from src.auth.dependencies import User

PERMISSIONS = (
    "tenants:create",
    "tenants:read",
    "tenants:update",
    "tenants:delete",
    "apis:create",
    "apis:read",
    "apis:update",
    "apis:delete",
    "apis:deploy",
    "apis:promote",
    "apps:create",
    "apps:read",
    "apps:update",
    "apps:delete",
    "users:manage",
    "audit:read",
    "workflows:read",
    "workflows:manage",
)
READ = {"tenants:read", "apis:read", "apps:read", "audit:read", "workflows:read"}
EXPECTED = {
    "cpi-admin": set(PERMISSIONS),
    "tenant-admin": set(PERMISSIONS) - {"tenants:create", "tenants:update", "tenants:delete"},
    "devops": READ
    | {
        "apis:create",
        "apis:update",
        "apis:deploy",
        "apis:promote",
        "apps:create",
        "apps:update",
    },
    "viewer": READ,
    "stoa.security": READ,
    "stoa.agent": {"apis:read", "apps:read"},
}
ROLE_CASES = (
    (),
    ("fixture-unknown",),
    ("cpi-admin",),
    ("tenant-admin",),
    ("devops",),
    ("viewer",),
    ("stoa.security",),
    ("stoa.agent",),
    ("fixture-unknown", "devops"),
    ("fixture-unknown", "viewer"),
    ("viewer", "devops"),
)
ALLOWED_CASES = ((), ("cpi-admin", "devops"), ("viewer",))


def make_user(roles: tuple[str, ...]) -> User:
    return User(id="fixture-user", email="fixture@example.invalid", username="fixture", roles=list(roles))


def expected_permission(roles: tuple[str, ...], permission: str) -> bool:
    return any(permission in EXPECTED.get(role, set()) for role in roles)
