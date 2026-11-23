# STOA Keycloak - Custom theme image
# Based on official Keycloak with STOA dark theme
# Theme version: 2.1 - KC 26.5.3 upgrade
# Login theme: parent=keycloak.v2 (migrated CAB-1960)
# Account theme: parent=keycloak.v2 (current)
# Mode: production (start --optimized) with PostgreSQL backend (CAB-1955)

FROM quay.io/keycloak/keycloak:26.5.3@sha256:5a236ae4dd8ece77490115bace15a11a4d15e9cbcf58a490b95a7da2cd71d32a AS builder

# Copy STOA theme (invalidate cache on theme changes)
COPY themes/stoa /opt/keycloak/themes/stoa

# Configure for PostgreSQL + production mode
ENV KC_DB=postgres
ENV KC_HEALTH_ENABLED=true
ENV KC_HTTP_ENABLED=true
ENV KC_FEATURES=token-exchange,dpop,par

# Build optimized image
RUN /opt/keycloak/bin/kc.sh build

# Application version baked at build time. docker-publish passes the release
# tag version; manual or local builds default to 0.0.0-dev.
ARG APP_VERSION=0.0.0-dev
RUN printf '%s\n' "${APP_VERSION}" | { read -r version || true; printf '%s\n' "${version:-0.0.0-dev}"; } > /opt/keycloak/stoa-version.txt

# Production image
FROM quay.io/keycloak/keycloak:26.5.3@sha256:5a236ae4dd8ece77490115bace15a11a4d15e9cbcf58a490b95a7da2cd71d32a

# Preserve the project distribution notices in the runtime image.
COPY LICENSE NOTICE /usr/share/licenses/stoa/

# Copy built providers and themes
COPY --from=builder /opt/keycloak/ /opt/keycloak/

ENTRYPOINT ["/opt/keycloak/bin/kc.sh"]
