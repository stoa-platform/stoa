FROM alpine:3.24@sha256:be2656061b536c1883c4034790e21d0a09c5aaaf51968b89368a3c0371ea2c9a

# Preserve the project distribution notices in the runtime image.
COPY LICENSE NOTICE /usr/share/licenses/stoa/

RUN apk add --no-cache ca-certificates

COPY stoactl /usr/local/bin/stoactl

ENTRYPOINT ["/usr/local/bin/stoactl"]
