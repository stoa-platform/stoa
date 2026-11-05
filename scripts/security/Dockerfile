# CAB-2071 phase 3: bake openssl + curl + coreutils into the image so the
# CronJob no longer has to `apk add` at runtime — that path was failing with
# "Permission denied" once the container ran with `capabilities.drop: [ALL]`.
#
# The actual probe script (`tls-cert-check.sh`) is mounted from the
# `security-scripts` ConfigMap in `stoa-system`, so the image only ships the
# tools — keeps script iteration cheap (kubectl apply on the ConfigMap, no
# image rebuild).
FROM alpine:3.21@sha256:ee16d92f96db08d9d2d07da48555a27f3a69d8f0759021dbc601195ed0d2b5bd

# Preserve the project distribution notices in the runtime image.
COPY LICENSE NOTICE /usr/share/licenses/stoa/

RUN apk add --no-cache openssl curl coreutils

USER 65532

ENTRYPOINT []
CMD ["sh", "-c", "echo 'tls-cert-monitor: ready (override CMD with /scripts/tls-cert-check.sh)'"]
