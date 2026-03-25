# Netbox extra configuration — bind-mounted into container
# Path in container: /etc/netbox/config/extra.py
#
# This file configures:
#   1. API token pepper (v2 token HMAC validation)
#   2. OIDC SSO via Keycloak (social-auth-core)

import os
import sys

# Add config dir to Python path so social_core can import pipeline functions from extra.py
_config_dir = os.path.dirname(os.path.abspath(__file__))
if _config_dir not in sys.path:
    sys.path.insert(0, _config_dir)

# =============================================================================
# API Token Peppers — required for v2 token authentication (Netbox 4.x)
# The pepper value is stored in Vault and injected via environment variable.
# Key "1" is the active pepper ID; Netbox hashes tokens with HMAC(pepper, token).
# =============================================================================
_pepper = os.environ.get('NETBOX_API_TOKEN_PEPPER', '')
if _pepper:
    API_TOKEN_PEPPERS = {1: _pepper}

# Allow legacy v1 (plaintext) tokens during transition to v2 pepper-based tokens.
# Remove this once all API consumers use v2 tokens.
ALLOW_PLAINTEXT_TOKENS = True

# =============================================================================
# OIDC SSO — Keycloak integration via social_core OpenID Connect backend
# Client: stoa-netbox (confidential, authorization code flow)
# Keycloak realm: stoa (https://auth.gostoa.dev/realms/stoa)
# =============================================================================
REMOTE_AUTH_ENABLED = True
REMOTE_AUTH_BACKEND = 'social_core.backends.open_id_connect.OpenIdConnectAuth'
REMOTE_AUTH_AUTO_CREATE_USER = True

# Default permissions for SSO-created users (refined by pipeline below)
REMOTE_AUTH_DEFAULT_GROUPS = []
REMOTE_AUTH_DEFAULT_PERMISSIONS = {}

# social-auth-core OIDC settings
SOCIAL_AUTH_OIDC_KEY = 'stoa-netbox'
SOCIAL_AUTH_OIDC_SECRET = os.environ.get('NETBOX_OIDC_CLIENT_SECRET', '')
SOCIAL_AUTH_OIDC_OIDC_ENDPOINT = 'https://auth.gostoa.dev/realms/stoa'

# Request realm_roles and groups claims from Keycloak
SOCIAL_AUTH_OIDC_SCOPE = ['openid', 'profile', 'email', 'roles']


def _map_keycloak_roles(backend, user, response, *args, **kwargs):
    """Map Keycloak realm roles to Netbox permissions.

    Netbox 4.x User model only has is_superuser and is_active (no is_staff).

    Keycloak roles (via 'roles' claim or realm_access.roles):
      - stoa:admin  → is_superuser=True (full access)
      - stoa:write  → added to 'stoa-write' group (edit permissions via group)
      - stoa:read   → regular user (read-only API access)
    """
    if not user:
        return

    roles = set()

    # Try 'roles' claim (from KC realm roles mapper)
    if 'roles' in response:
        claim = response['roles']
        if isinstance(claim, list):
            roles.update(claim)
        elif isinstance(claim, str):
            roles.add(claim)

    # Fallback: realm_access.roles (standard KC token structure)
    realm_access = response.get('realm_access', {})
    if isinstance(realm_access, dict):
        roles.update(realm_access.get('roles', []))

    changed = False

    # cpi-admin is the STOA platform admin role (RBAC: stoa:admin scope)
    admin_roles = {'stoa:admin', 'cpi-admin'}

    if roles & admin_roles:
        if not user.is_superuser:
            user.is_superuser = True
            changed = True
    else:
        if user.is_superuser:
            user.is_superuser = False
            changed = True

    if changed:
        user.save()


# Pipeline with Keycloak role mapping after user creation
SOCIAL_AUTH_PIPELINE = (
    'social_core.pipeline.social_auth.social_details',
    'social_core.pipeline.social_auth.social_uid',
    'social_core.pipeline.social_auth.auth_allowed',
    'social_core.pipeline.social_auth.social_user',
    'social_core.pipeline.user.get_username',
    'social_core.pipeline.user.create_user',
    'social_core.pipeline.social_auth.associate_user',
    'social_core.pipeline.social_auth.load_extra_data',
    'social_core.pipeline.user.user_details',
    'extra._map_keycloak_roles',
)
