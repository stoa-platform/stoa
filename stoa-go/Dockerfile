FROM alpine:3.19@sha256:6baf43584bcb78f2e5847d1de515f23499913ac9f12bdf834811a3145eb11ca1

# Preserve the project distribution notices in the runtime image.
COPY LICENSE NOTICE /usr/share/licenses/stoa/

RUN apk add --no-cache ca-certificates

COPY stoactl /usr/local/bin/stoactl

ENTRYPOINT ["/usr/local/bin/stoactl"]
