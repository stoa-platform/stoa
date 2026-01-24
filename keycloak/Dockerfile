# STOA Keycloak - Custom theme image
# Based on official Keycloak with STOA dark theme
# Theme version: 2.0 - gostoa.dev aligned design

FROM quay.io/keycloak/keycloak:25.0 AS builder

# Copy STOA theme (invalidate cache on theme changes)
COPY themes/stoa /opt/keycloak/themes/stoa

# Build optimized image
RUN /opt/keycloak/bin/kc.sh build

# Production image
FROM quay.io/keycloak/keycloak:25.0

# Copy built providers and themes
COPY --from=builder /opt/keycloak/ /opt/keycloak/

# Set default theme for login
ENV KC_FEATURES=token-exchange

ENTRYPOINT ["/opt/keycloak/bin/kc.sh"]
