# STOA Keycloak - Custom theme image
# Based on official Keycloak with STOA dark theme
# Theme version: 2.1 - KC 26.5.3 upgrade
# Login theme: parent=keycloak (v1, deprecated in KC 26 — migrate to v2 when v1 removed)
# Account theme: parent=keycloak.v2 (current)
# Mode: production (start) with external PostgreSQL (CAB-1955)

FROM quay.io/keycloak/keycloak:26.5.3 AS builder

# Copy STOA theme (invalidate cache on theme changes)
COPY themes/stoa /opt/keycloak/themes/stoa

# Configure for production mode with PostgreSQL (CAB-1955)
ENV KC_DB=postgres
ENV KC_HEALTH_ENABLED=true

# KC 26 features: token-exchange, DPoP binding (CAB-438), PAR (CAB-1733 FAPI 2.0)
ENV KC_FEATURES=token-exchange,dpop,par

# Build optimized image
RUN /opt/keycloak/bin/kc.sh build

# Production image
FROM quay.io/keycloak/keycloak:26.5.3

# Copy built providers and themes
COPY --from=builder /opt/keycloak/ /opt/keycloak/

ENTRYPOINT ["/opt/keycloak/bin/kc.sh"]
