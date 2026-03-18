FROM alpine:3.19

RUN apk add --no-cache ca-certificates

COPY stoactl /usr/local/bin/stoactl

ENTRYPOINT ["/usr/local/bin/stoactl"]
