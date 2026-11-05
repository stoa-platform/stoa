# POC gateway image memory

Run `python3 scripts/bench/gateway_image_memory.py` from the repository root.
Requires local Docker, Go and cached Go modules. No downloads, login or push;
missing prerequisites fail with `results pending`. Total command budget is
14 minutes plus at most 20 seconds for cleanup. Only its named container is removed.
The printed directory retains `run.json`, `results.json`, `test.log`, the test
binary and six Envoy configurations. Ordinary Go tests skip the measurement.

The POC data plane uses the image pinned in `o1-offline-envoy.md`:
`envoyproxy/envoy@sha256:29d778ba078e0404d18fa45ffb834c062071b0f81dc0a6a41501ce8e23a0059f`.
This differs from the Rust distribution: `stoa-gateway/Dockerfile` and
`stoa-gateway-ci.yml` publish `ghcr.io/stoa-platform/stoa-gateway:dev-<full SHA>`
on linux/amd64 with `FEATURES=kafka,pingora`. The Go release ships the agent/CLI,
not the Envoy data-plane binary. These measurements do not describe Rust RSS.

Each case starts a fresh Envoy process in that unmodified image, one worker,
network disabled, loopback upstream and real gRPC allow witness. `BuildSnapshot`
produces the filters; only ADS delivery becomes inline and route timeout becomes
120 seconds. No optional policies are configured. Upload/download use bounded
zero-filled buffers, verified byte counts and HTTP 200. `/proc/<pid>/status`
provides idle `VmRSS` and post-transfer lifetime peak `VmHWM` (KiB, includes
startup). This excludes the Go harness, client, upstream and Docker VM memory.

Measured 2026-11-05 02:03:35 UTC, macOS 26.6.2 arm64, Docker 29.6.1,
linux/arm64, Go 1.26.0; repository base `aecb84f1e59d393a76616d2c2d1243e85b0b1ab4`.
Image ID: `sha256:c469e21da1e279b02519b69ca897ee5615287bb56960c4b7e05481e178125c44`.
Sizes from the parent acceptance criteria use decimal MB/GB (not MiB/GiB).

| Bytes | Upload idle / peak KiB | Download idle / peak KiB |
|---:|---:|---:|
| 50,000,000 | 53,848 / 57,800 | 55,028 / 58,728 |
| 1,000,000,000 | 55,040 / 58,920 | 56,920 / 60,644 |
| 5,000,000,000 | 55,052 / 59,600 | 56,712 / 60,412 |

All six transfers passed. The script prints the evidence directory for each run.
This single sequential run supports bounded RSS for this fixture only; it is not
a concurrency, TLS, slow-consumer, policy, production-deployment or CI result.
The sibling streaming regression proves first-fragment relay separately; these
measurements impose no statistical flatness threshold. Repeat on the deployment
architecture and with its actual policies before claiming production equivalence.
