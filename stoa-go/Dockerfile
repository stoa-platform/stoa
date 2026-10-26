FROM alpine:3.19

# Preserve the project distribution notices in the runtime image.
COPY LICENSE NOTICE /usr/share/licenses/stoa/

RUN apk add --no-cache ca-certificates

COPY stoactl /usr/local/bin/stoactl

ENTRYPOINT ["/usr/local/bin/stoactl"]
