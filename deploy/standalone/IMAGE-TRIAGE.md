# Image triage

## Identity

Scanned image: `stoa-gateway:standalone`
Label `org.opencontainers.image.revision`: `fe1e5a3271d47f9788482c972f1a692e2350927c`
That value is `git rev-parse HEAD` at build time (`deploy/standalone/build-image.sh`, `STOA_REVISION` unset). It is the commit that refuses `POST /admin/policies` in standalone.
Tar: `deploy/standalone/stoa-gateway-standalone.tar` (not committed)
Tar sha256: `71cb54076b9e7336031b9ab3363eb10ee41e01217f94fbf63a8099a86bcfcd95`
Tar.gz sha256: `7a1e79418235a1eb2290ac67b6de453f8a86d98884a21bc0fd4e8fa158df4f00` (`/cursor/stores/self/stoa-gateway-standalone/stoa-gateway-standalone.tar.gz`)
Base: `debian:bookworm-slim` (Trivy detected Debian 12.15), builder `rust:1.93-bookworm`
Build: `cargo chef cook --release --locked` and `cargo auditable build --release --locked` (cargo-auditable 0.7.5). The binary is not stripped; `readelf` finds `.dep-v0`.

The triage commit does not touch the docker context (`stoa-gateway/`, including `Dockerfile` and `Cargo.lock`). Proof, empty at this commit and after it:

```text
git diff fe1e5a3271d47f9788482c972f1a692e2350927c HEAD -- stoa-gateway/
```

## Disposition

`trivy image --ignore-unfixed=false stoa-gateway:standalone` (Trivy 0.58.1, exit 0) reports Debian 12.15: 364 findings (1 CRITICAL, 70 HIGH, 131 MEDIUM, 161 LOW, 1 UNKNOWN) and the Rust binary: 1 MEDIUM. `quick-xml` 0.39.4 is not in that Rust report. RustSec still lists two HIGH advisories on it. >= 0.41.0 avant tout câblage SOAP.

| Vulnerability | Packages | Disposition |
| --- | --- | --- |
| RUSTSEC-2026-0194, RUSTSEC-2026-0195 HIGH (not emitted by Trivy 0.58.1) | quick-xml 0.39.4 | DoS in XML attribute checks and `NsReader`. Linked for the SOAP module. `STOA_SOAP_PROXY_ENABLED` and `STOA_SOAP_BRIDGE_ENABLED` stay false, and no SOAP contract is published. Accept only while that stays true. >= 0.41.0 avant tout câblage SOAP. |
| CVE-2023-45853 CRITICAL, will_not_fix | zlib1g | MiniZip `zipOpenNewFileInZip4_64` integer overflow. Not reachable: the gateway does not open zip archives and does not call that MiniZip entry point. zlib is a Debian base-image library. Accept on this image. |
| CVE-2026-48504 MEDIUM, fixed in 0.32.1 | opentelemetry_sdk 0.27.1 | Unbounded allocation in W3C baggage propagation. The binary enables the `trace` feature only; baggage is not used. Accept on this image. The bump crosses five minors and is a separate tracing change. |
| CVE-2026-84782 HIGH, affected | libssl3, openssl | DTLS handshake retransmission disclosure. The process uses TLS, not DTLS. No bookworm fix. Accept for this image. |
| CVE-2026-12064, CVE-2026-6276, CVE-2026-8286, CVE-2026-8458, CVE-2026-8927 HIGH | curl, libcurl4 | Only the image `HEALTHCHECK` runs curl, against `http://localhost:8080/health`. No fixed version. Accept. |
| CVE-2026-53613, CVE-2026-53615, CVE-2026-76642, CVE-2026-78408, CVE-2026-78409, CVE-2026-78410 HIGH, affected | util-linux and its libraries | mount, nsenter, and libmount bugs. The container is uid 1000, drops all capabilities, and has a read-only root. It does not mount. No fixed version. Accept. |
| CVE-2026-16742 HIGH, fix_deferred | libsystemd0, libudev1 | systemd-homed signature check. systemd is not running in the container. Accept. |
| CVE-2023-2953 HIGH, affected | libldap-2.5-0 | OpenLDAP null deref. Pulled in by curl. The gateway does not speak LDAP. Accept. |
| CVE-2026-54369 HIGH, fix_deferred | libacl1 | libacl symlink traversal. The process does not call libacl. Accept. |
| CVE-2026-41992 HIGH, fix_deferred | gzip | LZH decompression overflow. The process does not invoke gzip. Accept. |
| CVE-2025-69720 HIGH, affected | ncurses, libtinfo6 | Terminal library overflow. The process does not link ncurses for request handling. Accept. |
| CVE-2026-9538 HIGH, fix_deferred | perl-base | `Archive::Tar` denial of service. perl is a base-image essential and is not executed. Accept. |

Commitment: the runtime base moves from `debian:bookworm-slim` (tag, not digest) to `gcr.io/distroless/cc` pinned by digest. That removes the zlib/MiniZip package and the other Debian rows above. This image is not that base.

## cargo audit

cargo-audit 0.22.2 has no `--locked` flag. The scan reads `stoa-gateway/Cargo.lock`. The image build is `cargo auditable build --release --locked`.

Command: `cargo audit --no-fetch` in `stoa-gateway/` (exit 0). Zero advisories outside the 12 exceptions. `informational_warnings = []` in `stoa-gateway/.cargo/audit.toml`, so unmaintained and unsound notices are not emitted.

```text
      Loaded 1348 security advisories (from /usr/local/cargo/advisory-db)
    Scanning Cargo.lock for vulnerabilities (617 crate dependencies)
```

The 12 exceptions in `stoa-gateway/.cargo/audit.toml`:

1. `RUSTSEC-2026-0194` quick-xml 0.39.4, linked, SOAP only. >= 0.41.0 avant tout câblage SOAP.
2. `RUSTSEC-2026-0195` quick-xml 0.39.4, same acceptance.
3. `RUSTSEC-2023-0071` rsa 0.9.10, linked by jsonwebtoken. No fixed upgrade. JWT verify, no decrypt.
4. `RUSTSEC-2024-0437` protobuf 2.28.0. prometheus is built with `default-features = false`, so protobuf is not linked.
5. `RUSTSEC-2026-0327` wasmtime 43.0.2. Optional `--features wasm`, not in this image.
6. `RUSTSEC-2026-0316` wasmtime 43.0.2. Same.
7. `RUSTSEC-2026-0363` wasmtime 43.0.2. Same.
8. `RUSTSEC-2026-0269` wasmtime 43.0.2. Same.
9. `RUSTSEC-2026-0379` wasmtime 43.0.2. Same.
10. `RUSTSEC-2026-0359` wasmtime 43.0.2. Same.
11. `RUSTSEC-2026-0222` wasmtime 43.0.2. Same.
12. `RUSTSEC-2026-0362` wasmtime 43.0.2. Same.

## trivy image --ignore-unfixed=false

Command: `trivy image --ignore-unfixed=false stoa-gateway:standalone` (Trivy 0.58.1, exit 0).

```text
2026-10-21T17:54:01Z	INFO	[vuln] Vulnerability scanning is enabled
2026-10-21T17:54:01Z	INFO	[secret] Secret scanning is enabled
2026-10-21T17:54:01Z	INFO	[secret] If your scanning is slow, please try '--scanners vuln' to disable secret scanning
2026-10-21T17:54:01Z	INFO	[secret] Please see also https://aquasecurity.github.io/trivy/v0.58/docs/scanner/secret#recommendation for faster secret detection
2026-10-21T17:54:01Z	INFO	Detected OS	family="debian" version="12.15"
2026-10-21T17:54:01Z	INFO	[debian] Detecting vulnerabilities...	os_version="12" pkg_num=110
2026-10-21T17:54:01Z	INFO	Number of language-specific files	num=1
2026-10-21T17:54:01Z	INFO	[rustbinary] Detecting vulnerabilities...
2026-10-21T17:54:01Z	WARN	Using severities from other vendors for some vulnerabilities. Read https://aquasecurity.github.io/trivy/v0.58/docs/scanner/vulnerability#severity-selection for details.

stoa-gateway:standalone (debian 12.15)
======================================
Total: 364 (UNKNOWN: 1, LOW: 161, MEDIUM: 131, HIGH: 70, CRITICAL: 1)

┌─────────────────────┬─────────────────────┬──────────┬──────────────┬────────────────────────┬───────────────┬──────────────────────────────────────────────────────────────┐
│       Library       │    Vulnerability    │ Severity │    Status    │   Installed Version    │ Fixed Version │                            Title                             │
├─────────────────────┼─────────────────────┼──────────┼──────────────┼────────────────────────┼───────────────┼──────────────────────────────────────────────────────────────┤
│ apt                 │ CVE-2011-3374       │ LOW      │ affected     │ 2.6.1                  │               │ It was found that apt-key in apt, all versions, do not       │
│                     │                     │          │              │                        │               │ correctly...                                                 │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2011-3374                    │
├─────────────────────┼─────────────────────┤          │              ├────────────────────────┼───────────────┼──────────────────────────────────────────────────────────────┤
│ bash                │ TEMP-0841856-B18BAF │          │              │ 5.2.15-2+b13           │               │ [Privilege escalation possible to other user than root]      │
│                     │                     │          │              │                        │               │ https://security-tracker.debian.org/tracker/TEMP-0841856-B1- │
│                     │                     │          │              │                        │               │ 8BAF                                                         │
├─────────────────────┼─────────────────────┼──────────┤              ├────────────────────────┼───────────────┼──────────────────────────────────────────────────────────────┤
│ bsdutils            │ CVE-2026-53613      │ HIGH     │              │ 1:2.38.1-5+deb12u3     │               │ util-linux: util-linux: TOCTOU in the mount program via      │
│                     │                     │          │              │                        │               │ ancestor directory swap on...                                │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-53613                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-53615      │          │              │                        │               │ util-linux: util-linux: Partition metadata compromise via    │
│                     │                     │          │              │                        │               │ integer overflow in DOS partition parser...                  │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-53615                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-76642      │          │              │                        │               │ util-linux: util-linux: failed external mount helper still   │
│                     │                     │          │              │                        │               │ runs privileged X-mount post-hooks                           │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-76642                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-78408      │          │              │                        │               │ util-linux: util-linux: nsenter --join-cgroup leaks root     │
│                     │                     │          │              │                        │               │ cgroup migration authority                                   │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-78408                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-78409      │          │              │                        │               │ util-linux: util-linux: X-mount.subdir detached-tree         │
│                     │                     │          │              │                        │               │ resolution can escape via intermediate symlinks              │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-78409                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-78410      │          │              │                        │               │ util-linux: util-linux: restricted bind mounts do not pin    │
│                     │                     │          │              │                        │               │ the source, allowing X-mount.owner/group/mode...             │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-78410                   │
│                     ├─────────────────────┼──────────┤              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-13595      │ MEDIUM   │              │                        │               │ util-linux: util-linux: heap use-after-free in libblkid      │
│                     │                     │          │              │                        │               │ nested partition probing                                     │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-13595                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-27456      │          │              │                        │               │ util-linux: TOCTOU in the mount program when setting up loop │
│                     │                     │          │              │                        │               │ devices                                                      │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-27456                   │
│                     ├─────────────────────┤          ├──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-3184       │          │ will_not_fix │                        │               │ util-linux: util-linux: Access control bypass due to         │
│                     │                     │          │              │                        │               │ improper hostname canonicalization                           │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-3184                    │
│                     ├─────────────────────┼──────────┼──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2022-0563       │ LOW      │ affected     │                        │               │ util-linux: partial disclosure of arbitrary files in chfn    │
│                     │                     │          │              │                        │               │ and chsh when compiled...                                    │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2022-0563                    │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2025-14104      │          │              │                        │               │ util-linux: util-linux: Heap buffer overread in setpwnam()   │
│                     │                     │          │              │                        │               │ when processing 256-byte usernames                           │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2025-14104                   │
├─────────────────────┼─────────────────────┤          ├──────────────┼────────────────────────┼───────────────┼──────────────────────────────────────────────────────────────┤
│ coreutils           │ CVE-2016-2781       │          │ will_not_fix │ 9.1-1                  │               │ coreutils: Non-privileged session can escape to the parent   │
│                     │                     │          │              │                        │               │ session in chroot                                            │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2016-2781                    │
│                     ├─────────────────────┤          ├──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2017-18018      │          │ affected     │                        │               │ coreutils: race condition vulnerability in chown and chgrp   │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2017-18018                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2025-5278       │          │              │                        │               │ coreutils: Heap Buffer Under-Read in GNU Coreutils sort via  │
│                     │                     │          │              │                        │               │ Key Specification                                            │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2025-5278                    │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-56391      │          │              │                        │               │ coreutils: GNU coreutils uniq: Denial of Service and         │
│                     │                     │          │              │                        │               │ information disclosure via out-of-bounds...                  │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-56391                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-56392      │          │              │                        │               │ coreutils: GNU coreutils unexpand: Denial of Service via     │
│                     │                     │          │              │                        │               │ crafted tab stop values...                                   │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-56392                   │
├─────────────────────┼─────────────────────┼──────────┼──────────────┼────────────────────────┼───────────────┼──────────────────────────────────────────────────────────────┤
│ curl                │ CVE-2026-12064      │ HIGH     │ fix_deferred │ 7.88.1-10+deb12u15     │               │ curl: curl: SSH host verification bypass when using          │
│                     │                     │          │              │                        │               │ schemeless URLs with SFTP/SCP...                             │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-12064                   │
│                     ├─────────────────────┤          ├──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-6276       │          │ affected     │                        │               │ curl: libcurl: Information disclosure due to cookie leak     │
│                     │                     │          │              │                        │               │ when reusing connections with...                             │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-6276                    │
│                     ├─────────────────────┤          ├──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-8286       │          │ fix_deferred │                        │               │ curl: curl: Insecure connection establishment due to TLS     │
│                     │                     │          │              │                        │               │ configuration mismatch                                       │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-8286                    │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-8458       │          │              │                        │               │ curl: libcurl: Unauthorized connection reuse due to a        │
│                     │                     │          │              │                        │               │ logical error                                                │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-8458                    │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-8927       │          │              │                        │               │ curl: Information disclosure due to uncleared proxy          │
│                     │                     │          │              │                        │               │ authentication state                                         │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-8927                    │
│                     ├─────────────────────┼──────────┤              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-10536      │ MEDIUM   │              │                        │               │ libcurl: libcurl: Use-after-free vulnerability leading to    │
│                     │                     │          │              │                        │               │ Denial of Service                                            │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-10536                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-11856      │          │              │                        │               │ curl: curl: Information disclosure via incorrect Digest      │
│                     │                     │          │              │                        │               │ authentication header reuse                                  │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-11856                   │
│                     ├─────────────────────┤          ├──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-1965       │          │ affected     │                        │               │ curl: curl: Authentication bypass due to incorrect           │
│                     │                     │          │              │                        │               │ connection reuse with Negotiate authentication...            │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-1965                    │
│                     ├─────────────────────┤          ├──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-19931      │          │ fix_deferred │                        │               │ curl: libcurl: Information disclosure via incorrect          │
│                     │                     │          │              │                        │               │ connection reuse with Negotiate authentication               │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-19931                   │
│                     ├─────────────────────┤          ├──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-4873       │          │ affected     │                        │               │ curl: curl: Information disclosure due to incorrect TLS      │
│                     │                     │          │              │                        │               │ connection reuse                                             │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-4873                    │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-5545       │          │              │                        │               │ curl: libcurl: Authentication bypass due to incorrect HTTP   │
│                     │                     │          │              │                        │               │ Negotiate connection reuse                                   │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-5545                    │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-6253       │          │              │                        │               │ curl: curl: Proxy credential disclosure via redirects to     │
│                     │                     │          │              │                        │               │ unauthenticated proxies                                      │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-6253                    │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-6429       │          │              │                        │               │ curl: libcurl: Credential leak via reused proxy connection   │
│                     │                     │          │              │                        │               │ during HTTP redirects                                        │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-6429                    │
│                     ├─────────────────────┤          ├──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-8924       │          │ fix_deferred │                        │               │ curl: curl: Cookie injection via malicious HTTP server using │
│                     │                     │          │              │                        │               │ super cookies                                                │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-8924                    │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-8932       │          │              │                        │               │ libcurl: libcurl: Security feature bypass due to improper    │
│                     │                     │          │              │                        │               │ mTLS connection reuse                                        │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-8932                    │
│                     ├─────────────────────┤          ├──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-92388      │          │ affected     │                        │               │ curl: curl: FTP wildcard write callback mixup                │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-92388                   │
│                     ├─────────────────────┼──────────┤              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2024-2379       │ LOW      │              │                        │               │ curl: QUIC certificate check bypass with wolfSSL             │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2024-2379                    │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2025-0725       │          │              │                        │               │ libcurl: Buffer Overflow in libcurl via zlib Integer         │
│                     │                     │          │              │                        │               │ Overflow                                                     │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2025-0725                    │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2025-10966      │          │              │                        │               │ curl: Curl missing SFTP host verification with wolfSSH       │
│                     │                     │          │              │                        │               │ backend                                                      │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2025-10966                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2025-14017      │          │              │                        │               │ curl: curl: Security bypass due to global TLS option changes │
│                     │                     │          │              │                        │               │ in multi-threaded...                                         │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2025-14017                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2025-15079      │          │              │                        │               │ curl: Host verification bypass during SSH transfers          │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2025-15079                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2025-15224      │          │              │                        │               │ curl: libssh key passphrase bypass without agent set         │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2025-15224                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-107928     │          │              │                        │               │ curl: curl: info leak uploading over WebSockets with GnuTLS  │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-107928                  │
│                     ├─────────────────────┤          ├──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-13608      │          │ fix_deferred │                        │               │ curl: curl: Authentication bypass in OpenLDAP SASL           │
│                     │                     │          │              │                        │               │ negotiation via Man-in-the-Middle (MITM) attack...           │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-13608                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-18924      │          │              │                        │               │ curl: libcurl: Use-after-free in HTTP/2 Server Push with     │
│                     │                     │          │              │                        │               │ shared connections                                           │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-18924                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-80230      │          │              │                        │               │ curl: curl: Public key pinning bypass allows unauthenticated │
│                     │                     │          │              │                        │               │ connections                                                  │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-80230                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-82209      │          │              │                        │               │ curl: libcurl: Information disclosure via improper Public    │
│                     │                     │          │              │                        │               │ Suffix List boundary check                                   │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-82209                   │
│                     ├─────────────────────┤          ├──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-86409      │          │ affected     │                        │               │ curl: curl: stale SigV4 headers sent unintended              │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-86409                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-86410      │          │              │                        │               │ curl: curl: redirect to SFTP or SCP bypasses host            │
│                     │                     │          │              │                        │               │ verification                                                 │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-86410                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-86414      │          │              │                        │               │ curl: curl: leaking host credentials to HTTP proxy           │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-86414                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-87864      │          │              │                        │               │ curl: IMAP APPEND plus CRLF conversion command injection     │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-87864                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-87865      │          │              │                        │               │ curl: curl: knownhost callback mismatches key as missing     │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-87865                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-87866      │          │              │                        │               │ curl: curl: wolfSSL public-key pinning bypass                │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-87866                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-92389      │          │              │                        │               │ curl: curl: TFTP direction confusion                         │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-92389                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-92390      │          │              │                        │               │ curl: curl: -J no-clobber guarantee bypassed with 103 early  │
│                     │                     │          │              │                        │               │ hints                                                        │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-92390                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-92391      │          │              │                        │               │ curl: curl: curl_mime_free stack overflow by recursion       │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-92391                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-94266      │          │              │                        │               │ curl: curl: password leak in CURLINFO_EFFECTIVE_URL          │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-94266                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-9547       │          │              │                        │               │ curl: curl: Man-in-the-middle attack via SSH host key bypass │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-9547                    │
├─────────────────────┼─────────────────────┤          │              ├────────────────────────┼───────────────┼──────────────────────────────────────────────────────────────┤
│ dash                │ CVE-2026-102473     │          │              │ 0.5.12-2               │               │ dash: dash: Super-polynomial backtracking in pmatch when     │
│                     │                     │          │              │                        │               │ libc fnmatch is disabled                                     │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-102473                  │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-102474     │          │              │                        │               │ dash: dash: Heap out-of-bounds write in conv_escape via      │
│                     │                     │          │              │                        │               │ undersized Unicode escape reservation...                     │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-102474                  │
├─────────────────────┼─────────────────────┤          │              ├────────────────────────┼───────────────┼──────────────────────────────────────────────────────────────┤
│ diffutils           │ CVE-2026-53910      │          │              │ 1:3.8-4                │               │ diffutils: heap‑based buffer overflow due to multiple signed │
│                     │                     │          │              │                        │               │ integer overflows in line‑mapping...                         │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-53910                   │
├─────────────────────┼─────────────────────┼──────────┼──────────────┼────────────────────────┼───────────────┼──────────────────────────────────────────────────────────────┤
│ gcc-12-base         │ CVE-2026-102010     │ MEDIUM   │ will_not_fix │ 12.2.0-14+deb12u1      │               │ gcc-toolset-15-gcc: gcc: gcc-toolset-16: gcc: Denial of      │
│                     │                     │          │              │                        │               │ Service via use-after-free in binary heap...                 │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-102010                  │
│                     ├─────────────────────┤          ├──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-95619      │          │ fix_deferred │                        │               │ gcc: libstdc++ integer overflow in `new` operator            │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-95619                   │
│                     ├─────────────────────┼──────────┼──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2022-27943      │ LOW      │ affected     │                        │               │ binutils: libiberty/rust-demangle.c in GNU GCC 11.2 allows   │
│                     │                     │          │              │                        │               │ stack exhaustion in demangle_const                           │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2022-27943                   │
├─────────────────────┼─────────────────────┼──────────┤              ├────────────────────────┼───────────────┼──────────────────────────────────────────────────────────────┤
│ gpgv                │ CVE-2025-30258      │ MEDIUM   │              │ 2.2.40-1.1+deb12u2     │               │ gnupg: verification DoS due to a malicious subkey in the     │
│                     │                     │          │              │                        │               │ keyring                                                      │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2025-30258                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2025-68972      │          │              │                        │               │ gnupg: GnuPG: Signature bypass via form feed character in    │
│                     │                     │          │              │                        │               │ signed messages                                              │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2025-68972                   │
│                     ├─────────────────────┼──────────┤              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2022-3219       │ LOW      │              │                        │               │ gnupg: denial of service issue (resource consumption) using  │
│                     │                     │          │              │                        │               │ compressed packets                                           │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2022-3219                    │
│                     ├─────────────────────┤          ├──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-105712     │          │ fix_deferred │                        │               │ gnupg2: gnupg: Arbitrary file overwrite via symlink          │
│                     │                     │          │              │                        │               │ traversal in gpgtar                                          │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-105712                  │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-57062      │          │              │                        │               │ GnuPG: Incorrect cryptographic message parsing               │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-57062                   │
├─────────────────────┼─────────────────────┼──────────┤              ├────────────────────────┼───────────────┼──────────────────────────────────────────────────────────────┤
│ gzip                │ CVE-2026-41992      │ HIGH     │              │ 1.12-1                 │               │ gzip: gzip: Information disclosure via global buffer         │
│                     │                     │          │              │                        │               │ overflow in LZH decompression                                │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-41992                   │
│                     ├─────────────────────┼──────────┤              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-41991      │ MEDIUM   │              │                        │               │ gzip: gzip: Arbitrary file overwrite via insecure temporary  │
│                     │                     │          │              │                        │               │ file handling in gzexe...                                    │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-41991                   │
├─────────────────────┼─────────────────────┤          │              ├────────────────────────┼───────────────┼──────────────────────────────────────────────────────────────┤
│ krb5-locales        │ CVE-2026-107708     │          │              │ 1.20.1-2+deb12u5       │               │ krb5: krb5: Denial of Service via malformed PAC in S4U2Proxy │
│                     │                     │          │              │                        │               │ requests                                                     │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-107708                  │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-107778     │          │              │                        │               │ krb5: krb5: Denial of Service via crafted forwarded          │
│                     │                     │          │              │                        │               │ credentials                                                  │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-107778                  │
│                     ├─────────────────────┼──────────┼──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2018-5709       │ LOW      │ affected     │                        │               │ krb5: integer overflow in dbentry->n_key_data in             │
│                     │                     │          │              │                        │               │ kadmin/dbutil/dump.c                                         │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2018-5709                    │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2024-26458      │          │              │                        │               │ krb5: Memory leak at /krb5/src/lib/rpc/pmap_rmt.c            │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2024-26458                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2024-26461      │          │              │                        │               │ krb5: Memory leak at /krb5/src/lib/gssapi/krb5/k5sealv3.c    │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2024-26461                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-11850      │          │              │                        │               │ krb5: krb5: integer underflow in berval2tl_data() leads to   │
│                     │                     │          │              │                        │               │ heap out-of-bounds read                                      │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-11850                   │
├─────────────────────┼─────────────────────┼──────────┼──────────────┼────────────────────────┼───────────────┼──────────────────────────────────────────────────────────────┤
│ libacl1             │ CVE-2026-54369      │ HIGH     │ fix_deferred │ 2.3.1-3                │               │ acl: Symlink traversal privilege escalation via libacl       │
│                     │                     │          │              │                        │               │ functions                                                    │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-54369                   │
│                     ├─────────────────────┼──────────┤              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-54370      │ MEDIUM   │              │                        │               │ acl: TOCTOU Symlink Traversal via getfacl/setfacl            │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-54370                   │
├─────────────────────┼─────────────────────┼──────────┼──────────────┼────────────────────────┼───────────────┼──────────────────────────────────────────────────────────────┤
│ libapt-pkg6.0       │ CVE-2011-3374       │ LOW      │ affected     │ 2.6.1                  │               │ It was found that apt-key in apt, all versions, do not       │
│                     │                     │          │              │                        │               │ correctly...                                                 │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2011-3374                    │
├─────────────────────┼─────────────────────┼──────────┼──────────────┼────────────────────────┼───────────────┼──────────────────────────────────────────────────────────────┤
│ libattr1            │ CVE-2026-54371      │ MEDIUM   │ fix_deferred │ 1:2.5.1-4              │               │ attr: attr: Symlink Traversal Privilege Escalation via       │
│                     │                     │          │              │                        │               │ getfattr and setfattr                                        │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-54371                   │
├─────────────────────┼─────────────────────┼──────────┼──────────────┼────────────────────────┼───────────────┼──────────────────────────────────────────────────────────────┤
│ libblkid1           │ CVE-2026-53613      │ HIGH     │ affected     │ 2.38.1-5+deb12u3       │               │ util-linux: util-linux: TOCTOU in the mount program via      │
│                     │                     │          │              │                        │               │ ancestor directory swap on...                                │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-53613                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-53615      │          │              │                        │               │ util-linux: util-linux: Partition metadata compromise via    │
│                     │                     │          │              │                        │               │ integer overflow in DOS partition parser...                  │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-53615                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-76642      │          │              │                        │               │ util-linux: util-linux: failed external mount helper still   │
│                     │                     │          │              │                        │               │ runs privileged X-mount post-hooks                           │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-76642                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-78408      │          │              │                        │               │ util-linux: util-linux: nsenter --join-cgroup leaks root     │
│                     │                     │          │              │                        │               │ cgroup migration authority                                   │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-78408                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-78409      │          │              │                        │               │ util-linux: util-linux: X-mount.subdir detached-tree         │
│                     │                     │          │              │                        │               │ resolution can escape via intermediate symlinks              │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-78409                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-78410      │          │              │                        │               │ util-linux: util-linux: restricted bind mounts do not pin    │
│                     │                     │          │              │                        │               │ the source, allowing X-mount.owner/group/mode...             │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-78410                   │
│                     ├─────────────────────┼──────────┤              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-13595      │ MEDIUM   │              │                        │               │ util-linux: util-linux: heap use-after-free in libblkid      │
│                     │                     │          │              │                        │               │ nested partition probing                                     │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-13595                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-27456      │          │              │                        │               │ util-linux: TOCTOU in the mount program when setting up loop │
│                     │                     │          │              │                        │               │ devices                                                      │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-27456                   │
│                     ├─────────────────────┤          ├──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-3184       │          │ will_not_fix │                        │               │ util-linux: util-linux: Access control bypass due to         │
│                     │                     │          │              │                        │               │ improper hostname canonicalization                           │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-3184                    │
│                     ├─────────────────────┼──────────┼──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2022-0563       │ LOW      │ affected     │                        │               │ util-linux: partial disclosure of arbitrary files in chfn    │
│                     │                     │          │              │                        │               │ and chsh when compiled...                                    │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2022-0563                    │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2025-14104      │          │              │                        │               │ util-linux: util-linux: Heap buffer overread in setpwnam()   │
│                     │                     │          │              │                        │               │ when processing 256-byte usernames                           │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2025-14104                   │
├─────────────────────┼─────────────────────┼──────────┤              ├────────────────────────┼───────────────┼──────────────────────────────────────────────────────────────┤
│ libbz2-1.0          │ CVE-2026-42250      │ MEDIUM   │              │ 1.0.8-5+b1             │               │ bzip2: bzip2: Denial of Service in bzip2recover via a        │
│                     │                     │          │              │                        │               │ specially crafted file...                                    │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-42250                   │
├─────────────────────┼─────────────────────┤          ├──────────────┼────────────────────────┼───────────────┼──────────────────────────────────────────────────────────────┤
│ libc-bin            │ CVE-2026-18374      │          │ fix_deferred │ 2.36-9+deb12u14        │               │ glibc: glibc: Heap buffer overflow via attacker-controlled   │
│                     │                     │          │              │                        │               │ fopen mode string                                            │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-18374                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-19499      │          │              │                        │               │ glibc: Buffer Overflow in strfmon right-justification        │
│                     │                     │          │              │                        │               │ padding                                                      │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-19499                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-19542      │          │              │                        │               │ glibc: Fix out-of-bounds array write in tdelete              │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-19542                   │
│                     ├─────────────────────┤          ├──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-5435       │          │ affected     │                        │               │ glibc: glibc: Out-of-bounds write via TSIG record processing │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-5435                    │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-5450       │          │              │                        │               │ glibc: glibc: Heap Buffer Overflow in `scanf` with `%mc`     │
│                     │                     │          │              │                        │               │ format specifier and...                                      │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-5450                    │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-5928       │          │              │                        │               │ glibc: glibc: Information disclosure or denial of service    │
│                     │                     │          │              │                        │               │ via ungetwc function with...                                 │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-5928                    │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-6238       │          │              │                        │               │ glibc: glibc: Application crash or uninitialized memory read │
│                     │                     │          │              │                        │               │ via crafted DNS response...                                  │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-6238                    │
│                     ├─────────────────────┤          ├──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-6368       │          │ fix_deferred │                        │               │ glibc: glibc: Process abort due to invalid memory in wordexp │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-6368                    │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-6791       │          │              │                        │               │ glibc: Glibc: Denial of Service via stack exhaustion during  │
│                     │                     │          │              │                        │               │ tilde expansion                                              │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-6791                    │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-77117      │          │              │                        │               │ glibc: Non-progress DoS in SHIFT_JISX0213 -&gt               │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-77117                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-80489      │          │              │                        │               │ glibc: Non-progress DoS in EUC_JISX0213 -> UCS-4 conversion  │
│                     │                     │          │              │                        │               │ state                                                        │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-80489                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-8674       │          │              │                        │               │ glibc: glibc DNS stub resolver: Denial of Service via long   │
│                     │                     │          │              │                        │               │ search domain...                                             │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-8674                    │
│                     ├─────────────────────┤          ├──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-86805      │          │ affected     │                        │               │ glibc: glibc: Privilege escalation and arbitrary code        │
│                     │                     │          │              │                        │               │ execution via TOCTOU race condition...                       │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-86805                   │
│                     ├─────────────────────┤          ├──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-89092      │          │ fix_deferred │                        │               │ glibc: nscd stack overflow leads to degraded DNS resolution  │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-89092                   │
│                     ├─────────────────────┤          ├──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-95818      │          │ affected     │                        │               │ glibc: glibc: Local attacker can cause denial of service and │
│                     │                     │          │              │                        │               │ information disclosure...                                    │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-95818                   │
│                     ├─────────────────────┼──────────┤              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2010-4756       │ LOW      │              │                        │               │ glibc: glob implementation can cause excessive CPU and       │
│                     │                     │          │              │                        │               │ memory consumption due to...                                 │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2010-4756                    │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2018-20796      │          │              │                        │               │ glibc: uncontrolled recursion in function                    │
│                     │                     │          │              │                        │               │ check_dst_limits_calc_pos_1 in posix/regexec.c               │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2018-20796                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2019-1010022    │          │              │                        │               │ glibc: stack guard protection bypass                         │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2019-1010022                 │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2019-1010023    │          │              │                        │               │ glibc: running ldd on malicious ELF leads to code execution  │
│                     │                     │          │              │                        │               │ because of...                                                │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2019-1010023                 │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2019-1010024    │          │              │                        │               │ glibc: ASLR bypass using cache of thread stack and heap      │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2019-1010024                 │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2019-1010025    │          │              │                        │               │ glibc: information disclosure of heap addresses of           │
│                     │                     │          │              │                        │               │ pthread_created thread                                       │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2019-1010025                 │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2019-9192       │          │              │                        │               │ glibc: uncontrolled recursion in function                    │
│                     │                     │          │              │                        │               │ check_dst_limits_calc_pos_1 in posix/regexec.c               │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2019-9192                    │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-97399      │          │              │                        │               │ glibc: glibc: Denial of Service via out-of-bounds read in    │
│                     │                     │          │              │                        │               │ strncasecmp                                                  │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-97399                   │
├─────────────────────┼─────────────────────┼──────────┼──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│ libc6               │ CVE-2026-18374      │ MEDIUM   │ fix_deferred │                        │               │ glibc: glibc: Heap buffer overflow via attacker-controlled   │
│                     │                     │          │              │                        │               │ fopen mode string                                            │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-18374                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-19499      │          │              │                        │               │ glibc: Buffer Overflow in strfmon right-justification        │
│                     │                     │          │              │                        │               │ padding                                                      │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-19499                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-19542      │          │              │                        │               │ glibc: Fix out-of-bounds array write in tdelete              │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-19542                   │
│                     ├─────────────────────┤          ├──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-5435       │          │ affected     │                        │               │ glibc: glibc: Out-of-bounds write via TSIG record processing │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-5435                    │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-5450       │          │              │                        │               │ glibc: glibc: Heap Buffer Overflow in `scanf` with `%mc`     │
│                     │                     │          │              │                        │               │ format specifier and...                                      │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-5450                    │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-5928       │          │              │                        │               │ glibc: glibc: Information disclosure or denial of service    │
│                     │                     │          │              │                        │               │ via ungetwc function with...                                 │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-5928                    │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-6238       │          │              │                        │               │ glibc: glibc: Application crash or uninitialized memory read │
│                     │                     │          │              │                        │               │ via crafted DNS response...                                  │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-6238                    │
│                     ├─────────────────────┤          ├──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-6368       │          │ fix_deferred │                        │               │ glibc: glibc: Process abort due to invalid memory in wordexp │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-6368                    │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-6791       │          │              │                        │               │ glibc: Glibc: Denial of Service via stack exhaustion during  │
│                     │                     │          │              │                        │               │ tilde expansion                                              │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-6791                    │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-77117      │          │              │                        │               │ glibc: Non-progress DoS in SHIFT_JISX0213 -&gt               │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-77117                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-80489      │          │              │                        │               │ glibc: Non-progress DoS in EUC_JISX0213 -> UCS-4 conversion  │
│                     │                     │          │              │                        │               │ state                                                        │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-80489                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-8674       │          │              │                        │               │ glibc: glibc DNS stub resolver: Denial of Service via long   │
│                     │                     │          │              │                        │               │ search domain...                                             │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-8674                    │
│                     ├─────────────────────┤          ├──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-86805      │          │ affected     │                        │               │ glibc: glibc: Privilege escalation and arbitrary code        │
│                     │                     │          │              │                        │               │ execution via TOCTOU race condition...                       │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-86805                   │
│                     ├─────────────────────┤          ├──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-89092      │          │ fix_deferred │                        │               │ glibc: nscd stack overflow leads to degraded DNS resolution  │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-89092                   │
│                     ├─────────────────────┤          ├──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-95818      │          │ affected     │                        │               │ glibc: glibc: Local attacker can cause denial of service and │
│                     │                     │          │              │                        │               │ information disclosure...                                    │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-95818                   │
│                     ├─────────────────────┼──────────┤              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2010-4756       │ LOW      │              │                        │               │ glibc: glob implementation can cause excessive CPU and       │
│                     │                     │          │              │                        │               │ memory consumption due to...                                 │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2010-4756                    │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2018-20796      │          │              │                        │               │ glibc: uncontrolled recursion in function                    │
│                     │                     │          │              │                        │               │ check_dst_limits_calc_pos_1 in posix/regexec.c               │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2018-20796                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2019-1010022    │          │              │                        │               │ glibc: stack guard protection bypass                         │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2019-1010022                 │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2019-1010023    │          │              │                        │               │ glibc: running ldd on malicious ELF leads to code execution  │
│                     │                     │          │              │                        │               │ because of...                                                │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2019-1010023                 │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2019-1010024    │          │              │                        │               │ glibc: ASLR bypass using cache of thread stack and heap      │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2019-1010024                 │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2019-1010025    │          │              │                        │               │ glibc: information disclosure of heap addresses of           │
│                     │                     │          │              │                        │               │ pthread_created thread                                       │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2019-1010025                 │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2019-9192       │          │              │                        │               │ glibc: uncontrolled recursion in function                    │
│                     │                     │          │              │                        │               │ check_dst_limits_calc_pos_1 in posix/regexec.c               │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2019-9192                    │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-97399      │          │              │                        │               │ glibc: glibc: Denial of Service via out-of-bounds read in    │
│                     │                     │          │              │                        │               │ strncasecmp                                                  │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-97399                   │
├─────────────────────┼─────────────────────┼──────────┼──────────────┼────────────────────────┼───────────────┼──────────────────────────────────────────────────────────────┤
│ libcurl4            │ CVE-2026-12064      │ HIGH     │ fix_deferred │ 7.88.1-10+deb12u15     │               │ curl: curl: SSH host verification bypass when using          │
│                     │                     │          │              │                        │               │ schemeless URLs with SFTP/SCP...                             │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-12064                   │
│                     ├─────────────────────┤          ├──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-6276       │          │ affected     │                        │               │ curl: libcurl: Information disclosure due to cookie leak     │
│                     │                     │          │              │                        │               │ when reusing connections with...                             │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-6276                    │
│                     ├─────────────────────┤          ├──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-8286       │          │ fix_deferred │                        │               │ curl: curl: Insecure connection establishment due to TLS     │
│                     │                     │          │              │                        │               │ configuration mismatch                                       │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-8286                    │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-8458       │          │              │                        │               │ curl: libcurl: Unauthorized connection reuse due to a        │
│                     │                     │          │              │                        │               │ logical error                                                │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-8458                    │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-8927       │          │              │                        │               │ curl: Information disclosure due to uncleared proxy          │
│                     │                     │          │              │                        │               │ authentication state                                         │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-8927                    │
│                     ├─────────────────────┼──────────┤              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-10536      │ MEDIUM   │              │                        │               │ libcurl: libcurl: Use-after-free vulnerability leading to    │
│                     │                     │          │              │                        │               │ Denial of Service                                            │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-10536                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-11856      │          │              │                        │               │ curl: curl: Information disclosure via incorrect Digest      │
│                     │                     │          │              │                        │               │ authentication header reuse                                  │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-11856                   │
│                     ├─────────────────────┤          ├──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-1965       │          │ affected     │                        │               │ curl: curl: Authentication bypass due to incorrect           │
│                     │                     │          │              │                        │               │ connection reuse with Negotiate authentication...            │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-1965                    │
│                     ├─────────────────────┤          ├──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-19931      │          │ fix_deferred │                        │               │ curl: libcurl: Information disclosure via incorrect          │
│                     │                     │          │              │                        │               │ connection reuse with Negotiate authentication               │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-19931                   │
│                     ├─────────────────────┤          ├──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-4873       │          │ affected     │                        │               │ curl: curl: Information disclosure due to incorrect TLS      │
│                     │                     │          │              │                        │               │ connection reuse                                             │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-4873                    │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-5545       │          │              │                        │               │ curl: libcurl: Authentication bypass due to incorrect HTTP   │
│                     │                     │          │              │                        │               │ Negotiate connection reuse                                   │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-5545                    │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-6253       │          │              │                        │               │ curl: curl: Proxy credential disclosure via redirects to     │
│                     │                     │          │              │                        │               │ unauthenticated proxies                                      │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-6253                    │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-6429       │          │              │                        │               │ curl: libcurl: Credential leak via reused proxy connection   │
│                     │                     │          │              │                        │               │ during HTTP redirects                                        │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-6429                    │
│                     ├─────────────────────┤          ├──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-8924       │          │ fix_deferred │                        │               │ curl: curl: Cookie injection via malicious HTTP server using │
│                     │                     │          │              │                        │               │ super cookies                                                │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-8924                    │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-8932       │          │              │                        │               │ libcurl: libcurl: Security feature bypass due to improper    │
│                     │                     │          │              │                        │               │ mTLS connection reuse                                        │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-8932                    │
│                     ├─────────────────────┤          ├──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-92388      │          │ affected     │                        │               │ curl: curl: FTP wildcard write callback mixup                │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-92388                   │
│                     ├─────────────────────┼──────────┤              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2024-2379       │ LOW      │              │                        │               │ curl: QUIC certificate check bypass with wolfSSL             │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2024-2379                    │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2025-0725       │          │              │                        │               │ libcurl: Buffer Overflow in libcurl via zlib Integer         │
│                     │                     │          │              │                        │               │ Overflow                                                     │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2025-0725                    │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2025-10966      │          │              │                        │               │ curl: Curl missing SFTP host verification with wolfSSH       │
│                     │                     │          │              │                        │               │ backend                                                      │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2025-10966                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2025-14017      │          │              │                        │               │ curl: curl: Security bypass due to global TLS option changes │
│                     │                     │          │              │                        │               │ in multi-threaded...                                         │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2025-14017                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2025-15079      │          │              │                        │               │ curl: Host verification bypass during SSH transfers          │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2025-15079                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2025-15224      │          │              │                        │               │ curl: libssh key passphrase bypass without agent set         │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2025-15224                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-107928     │          │              │                        │               │ curl: curl: info leak uploading over WebSockets with GnuTLS  │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-107928                  │
│                     ├─────────────────────┤          ├──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-13608      │          │ fix_deferred │                        │               │ curl: curl: Authentication bypass in OpenLDAP SASL           │
│                     │                     │          │              │                        │               │ negotiation via Man-in-the-Middle (MITM) attack...           │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-13608                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-18924      │          │              │                        │               │ curl: libcurl: Use-after-free in HTTP/2 Server Push with     │
│                     │                     │          │              │                        │               │ shared connections                                           │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-18924                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-80230      │          │              │                        │               │ curl: curl: Public key pinning bypass allows unauthenticated │
│                     │                     │          │              │                        │               │ connections                                                  │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-80230                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-82209      │          │              │                        │               │ curl: libcurl: Information disclosure via improper Public    │
│                     │                     │          │              │                        │               │ Suffix List boundary check                                   │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-82209                   │
│                     ├─────────────────────┤          ├──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-86409      │          │ affected     │                        │               │ curl: curl: stale SigV4 headers sent unintended              │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-86409                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-86410      │          │              │                        │               │ curl: curl: redirect to SFTP or SCP bypasses host            │
│                     │                     │          │              │                        │               │ verification                                                 │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-86410                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-86414      │          │              │                        │               │ curl: curl: leaking host credentials to HTTP proxy           │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-86414                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-87864      │          │              │                        │               │ curl: IMAP APPEND plus CRLF conversion command injection     │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-87864                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-87865      │          │              │                        │               │ curl: curl: knownhost callback mismatches key as missing     │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-87865                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-87866      │          │              │                        │               │ curl: curl: wolfSSL public-key pinning bypass                │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-87866                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-92389      │          │              │                        │               │ curl: curl: TFTP direction confusion                         │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-92389                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-92390      │          │              │                        │               │ curl: curl: -J no-clobber guarantee bypassed with 103 early  │
│                     │                     │          │              │                        │               │ hints                                                        │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-92390                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-92391      │          │              │                        │               │ curl: curl: curl_mime_free stack overflow by recursion       │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-92391                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-94266      │          │              │                        │               │ curl: curl: password leak in CURLINFO_EFFECTIVE_URL          │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-94266                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-9547       │          │              │                        │               │ curl: curl: Man-in-the-middle attack via SSH host key bypass │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-9547                    │
├─────────────────────┼─────────────────────┼──────────┼──────────────┼────────────────────────┼───────────────┼──────────────────────────────────────────────────────────────┤
│ libgcc-s1           │ CVE-2026-102010     │ MEDIUM   │ will_not_fix │ 12.2.0-14+deb12u1      │               │ gcc-toolset-15-gcc: gcc: gcc-toolset-16: gcc: Denial of      │
│                     │                     │          │              │                        │               │ Service via use-after-free in binary heap...                 │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-102010                  │
│                     ├─────────────────────┤          ├──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-95619      │          │ fix_deferred │                        │               │ gcc: libstdc++ integer overflow in `new` operator            │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-95619                   │
│                     ├─────────────────────┼──────────┼──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2022-27943      │ LOW      │ affected     │                        │               │ binutils: libiberty/rust-demangle.c in GNU GCC 11.2 allows   │
│                     │                     │          │              │                        │               │ stack exhaustion in demangle_const                           │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2022-27943                   │
├─────────────────────┼─────────────────────┤          │              ├────────────────────────┼───────────────┼──────────────────────────────────────────────────────────────┤
│ libgcrypt20         │ CVE-2018-6829       │          │              │ 1.10.1-3+deb12u1       │               │ libgcrypt: ElGamal implementation doesn't have semantic      │
│                     │                     │          │              │                        │               │ security due to incorrectly encoded plaintexts...            │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2018-6829                    │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2024-2236       │          │              │                        │               │ libgcrypt: vulnerable to Marvin Attack                       │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2024-2236                    │
├─────────────────────┼─────────────────────┤          │              ├────────────────────────┼───────────────┼──────────────────────────────────────────────────────────────┤
│ libgnutls30         │ CVE-2011-3389       │          │              │ 3.7.9-2+deb12u7        │               │ HTTPS: block-wise chosen-plaintext attack against SSL/TLS    │
│                     │                     │          │              │                        │               │ (BEAST)                                                      │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2011-3389                    │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-67693      │          │              │                        │               │ gnutls: gnutls: Information disclosure via contradictory Key │
│                     │                     │          │              │                        │               │ Usage and Extended Key Usage...                              │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-67693                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-88647      │          │              │                        │               │ gnutls: gnutls: Information disclosure via hostname          │
│                     │                     │          │              │                        │               │ verification bypass                                          │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-88647                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-88648      │          │              │                        │               │ gnutls: gnutls: Cross-domain certificate restriction bypass  │
│                     │                     │          │              │                        │               │ via incomplete X.509 validation                              │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-88648                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-95184      │          │              │                        │               │ gnutls: gnutls: legitimate user certificates incorrectly     │
│                     │                     │          │              │                        │               │ rejected causing denial of service                           │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-95184                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-95209      │          │              │                        │               │ gnutls: gnutls: legitimate CA certificates incorrectly       │
│                     │                     │          │              │                        │               │ rejected causing denial of service                           │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-95209                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-95210      │          │              │                        │               │ gnutls: gnutls: certificates with invalid extensions         │
│                     │                     │          │              │                        │               │ incorrectly accepted                                         │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-95210                   │
├─────────────────────┼─────────────────────┼──────────┼──────────────┼────────────────────────┼───────────────┼──────────────────────────────────────────────────────────────┤
│ libgssapi-krb5-2    │ CVE-2026-107708     │ MEDIUM   │ fix_deferred │ 1.20.1-2+deb12u5       │               │ krb5: krb5: Denial of Service via malformed PAC in S4U2Proxy │
│                     │                     │          │              │                        │               │ requests                                                     │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-107708                  │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-107778     │          │              │                        │               │ krb5: krb5: Denial of Service via crafted forwarded          │
│                     │                     │          │              │                        │               │ credentials                                                  │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-107778                  │
│                     ├─────────────────────┼──────────┼──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2018-5709       │ LOW      │ affected     │                        │               │ krb5: integer overflow in dbentry->n_key_data in             │
│                     │                     │          │              │                        │               │ kadmin/dbutil/dump.c                                         │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2018-5709                    │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2024-26458      │          │              │                        │               │ krb5: Memory leak at /krb5/src/lib/rpc/pmap_rmt.c            │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2024-26458                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2024-26461      │          │              │                        │               │ krb5: Memory leak at /krb5/src/lib/gssapi/krb5/k5sealv3.c    │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2024-26461                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-11850      │          │              │                        │               │ krb5: krb5: integer underflow in berval2tl_data() leads to   │
│                     │                     │          │              │                        │               │ heap out-of-bounds read                                      │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-11850                   │
├─────────────────────┼─────────────────────┼──────────┼──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│ libk5crypto3        │ CVE-2026-107708     │ MEDIUM   │ fix_deferred │                        │               │ krb5: krb5: Denial of Service via malformed PAC in S4U2Proxy │
│                     │                     │          │              │                        │               │ requests                                                     │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-107708                  │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-107778     │          │              │                        │               │ krb5: krb5: Denial of Service via crafted forwarded          │
│                     │                     │          │              │                        │               │ credentials                                                  │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-107778                  │
│                     ├─────────────────────┼──────────┼──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2018-5709       │ LOW      │ affected     │                        │               │ krb5: integer overflow in dbentry->n_key_data in             │
│                     │                     │          │              │                        │               │ kadmin/dbutil/dump.c                                         │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2018-5709                    │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2024-26458      │          │              │                        │               │ krb5: Memory leak at /krb5/src/lib/rpc/pmap_rmt.c            │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2024-26458                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2024-26461      │          │              │                        │               │ krb5: Memory leak at /krb5/src/lib/gssapi/krb5/k5sealv3.c    │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2024-26461                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-11850      │          │              │                        │               │ krb5: krb5: integer underflow in berval2tl_data() leads to   │
│                     │                     │          │              │                        │               │ heap out-of-bounds read                                      │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-11850                   │
├─────────────────────┼─────────────────────┼──────────┼──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│ libkrb5-3           │ CVE-2026-107708     │ MEDIUM   │ fix_deferred │                        │               │ krb5: krb5: Denial of Service via malformed PAC in S4U2Proxy │
│                     │                     │          │              │                        │               │ requests                                                     │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-107708                  │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-107778     │          │              │                        │               │ krb5: krb5: Denial of Service via crafted forwarded          │
│                     │                     │          │              │                        │               │ credentials                                                  │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-107778                  │
│                     ├─────────────────────┼──────────┼──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2018-5709       │ LOW      │ affected     │                        │               │ krb5: integer overflow in dbentry->n_key_data in             │
│                     │                     │          │              │                        │               │ kadmin/dbutil/dump.c                                         │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2018-5709                    │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2024-26458      │          │              │                        │               │ krb5: Memory leak at /krb5/src/lib/rpc/pmap_rmt.c            │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2024-26458                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2024-26461      │          │              │                        │               │ krb5: Memory leak at /krb5/src/lib/gssapi/krb5/k5sealv3.c    │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2024-26461                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-11850      │          │              │                        │               │ krb5: krb5: integer underflow in berval2tl_data() leads to   │
│                     │                     │          │              │                        │               │ heap out-of-bounds read                                      │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-11850                   │
├─────────────────────┼─────────────────────┼──────────┼──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│ libkrb5support0     │ CVE-2026-107708     │ MEDIUM   │ fix_deferred │                        │               │ krb5: krb5: Denial of Service via malformed PAC in S4U2Proxy │
│                     │                     │          │              │                        │               │ requests                                                     │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-107708                  │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-107778     │          │              │                        │               │ krb5: krb5: Denial of Service via crafted forwarded          │
│                     │                     │          │              │                        │               │ credentials                                                  │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-107778                  │
│                     ├─────────────────────┼──────────┼──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2018-5709       │ LOW      │ affected     │                        │               │ krb5: integer overflow in dbentry->n_key_data in             │
│                     │                     │          │              │                        │               │ kadmin/dbutil/dump.c                                         │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2018-5709                    │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2024-26458      │          │              │                        │               │ krb5: Memory leak at /krb5/src/lib/rpc/pmap_rmt.c            │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2024-26458                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2024-26461      │          │              │                        │               │ krb5: Memory leak at /krb5/src/lib/gssapi/krb5/k5sealv3.c    │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2024-26461                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-11850      │          │              │                        │               │ krb5: krb5: integer underflow in berval2tl_data() leads to   │
│                     │                     │          │              │                        │               │ heap out-of-bounds read                                      │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-11850                   │
├─────────────────────┼─────────────────────┼──────────┤              ├────────────────────────┼───────────────┼──────────────────────────────────────────────────────────────┤
│ libldap-2.5-0       │ CVE-2023-2953       │ HIGH     │              │ 2.5.13+dfsg-5          │               │ openldap: null pointer dereference in ber_memalloc_x         │
│                     │                     │          │              │                        │               │ function                                                     │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2023-2953                    │
│                     ├─────────────────────┼──────────┤              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2015-3276       │ LOW      │              │                        │               │ openldap: incorrect multi-keyword mode cipherstring parsing  │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2015-3276                    │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2017-14159      │          │              │                        │               │ openldap: Privilege escalation via PID file manipulation     │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2017-14159                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2017-17740      │          │              │                        │               │ openldap: contrib/slapd-modules/nops/nops.c attempts to free │
│                     │                     │          │              │                        │               │ stack buffer allowing remote attackers to cause...           │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2017-17740                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2020-15719      │          │              │                        │               │ openldap: Certificate validation incorrectly matches name    │
│                     │                     │          │              │                        │               │ against CN-ID                                                │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2020-15719                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-22185      │          │              │                        │               │ OpenLDAP: OpenLDAP LMDB: Denial of Service and Information   │
│                     │                     │          │              │                        │               │ Disclosure via Heap Buffer...                                │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-22185                   │
├─────────────────────┼─────────────────────┼──────────┤              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│ libldap-common      │ CVE-2023-2953       │ HIGH     │              │                        │               │ openldap: null pointer dereference in ber_memalloc_x         │
│                     │                     │          │              │                        │               │ function                                                     │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2023-2953                    │
│                     ├─────────────────────┼──────────┤              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2015-3276       │ LOW      │              │                        │               │ openldap: incorrect multi-keyword mode cipherstring parsing  │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2015-3276                    │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2017-14159      │          │              │                        │               │ openldap: Privilege escalation via PID file manipulation     │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2017-14159                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2017-17740      │          │              │                        │               │ openldap: contrib/slapd-modules/nops/nops.c attempts to free │
│                     │                     │          │              │                        │               │ stack buffer allowing remote attackers to cause...           │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2017-17740                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2020-15719      │          │              │                        │               │ openldap: Certificate validation incorrectly matches name    │
│                     │                     │          │              │                        │               │ against CN-ID                                                │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2020-15719                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-22185      │          │              │                        │               │ OpenLDAP: OpenLDAP LMDB: Denial of Service and Information   │
│                     │                     │          │              │                        │               │ Disclosure via Heap Buffer...                                │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-22185                   │
├─────────────────────┼─────────────────────┼──────────┤              ├────────────────────────┼───────────────┼──────────────────────────────────────────────────────────────┤
│ libmount1           │ CVE-2026-53613      │ HIGH     │              │ 2.38.1-5+deb12u3       │               │ util-linux: util-linux: TOCTOU in the mount program via      │
│                     │                     │          │              │                        │               │ ancestor directory swap on...                                │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-53613                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-53615      │          │              │                        │               │ util-linux: util-linux: Partition metadata compromise via    │
│                     │                     │          │              │                        │               │ integer overflow in DOS partition parser...                  │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-53615                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-76642      │          │              │                        │               │ util-linux: util-linux: failed external mount helper still   │
│                     │                     │          │              │                        │               │ runs privileged X-mount post-hooks                           │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-76642                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-78408      │          │              │                        │               │ util-linux: util-linux: nsenter --join-cgroup leaks root     │
│                     │                     │          │              │                        │               │ cgroup migration authority                                   │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-78408                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-78409      │          │              │                        │               │ util-linux: util-linux: X-mount.subdir detached-tree         │
│                     │                     │          │              │                        │               │ resolution can escape via intermediate symlinks              │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-78409                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-78410      │          │              │                        │               │ util-linux: util-linux: restricted bind mounts do not pin    │
│                     │                     │          │              │                        │               │ the source, allowing X-mount.owner/group/mode...             │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-78410                   │
│                     ├─────────────────────┼──────────┤              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-13595      │ MEDIUM   │              │                        │               │ util-linux: util-linux: heap use-after-free in libblkid      │
│                     │                     │          │              │                        │               │ nested partition probing                                     │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-13595                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-27456      │          │              │                        │               │ util-linux: TOCTOU in the mount program when setting up loop │
│                     │                     │          │              │                        │               │ devices                                                      │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-27456                   │
│                     ├─────────────────────┤          ├──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-3184       │          │ will_not_fix │                        │               │ util-linux: util-linux: Access control bypass due to         │
│                     │                     │          │              │                        │               │ improper hostname canonicalization                           │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-3184                    │
│                     ├─────────────────────┼──────────┼──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2022-0563       │ LOW      │ affected     │                        │               │ util-linux: partial disclosure of arbitrary files in chfn    │
│                     │                     │          │              │                        │               │ and chsh when compiled...                                    │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2022-0563                    │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2025-14104      │          │              │                        │               │ util-linux: util-linux: Heap buffer overread in setpwnam()   │
│                     │                     │          │              │                        │               │ when processing 256-byte usernames                           │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2025-14104                   │
├─────────────────────┼─────────────────────┼──────────┼──────────────┼────────────────────────┼───────────────┼──────────────────────────────────────────────────────────────┤
│ libnghttp2-14       │ CVE-2026-58055      │ MEDIUM   │ fix_deferred │ 1.52.0-1+deb12u3       │               │ nghttp2: nghttp2: HTTP Request/Response Smuggling and        │
│                     │                     │          │              │                        │               │ Response-Queue Poisoning via ambiguous HTTP/1.1 Upgrade...   │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-58055                   │
├─────────────────────┼─────────────────────┤          │              ├────────────────────────┼───────────────┼──────────────────────────────────────────────────────────────┤
│ libp11-kit0         │ CVE-2026-13757      │          │              │ 0.24.1-2               │               │ p11-kit: Stack exhaustion via unbounded recursion in RPC     │
│                     │                     │          │              │                        │               │ attribute parsing                                            │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-13757                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-18938      │          │              │                        │               │ p11-kit: Integer overflow in RPC attribute-array length      │
│                     │                     │          │              │                        │               │ calculation can under-allocate nested attribute...           │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-18938                   │
├─────────────────────┼─────────────────────┤          ├──────────────┼────────────────────────┼───────────────┼──────────────────────────────────────────────────────────────┤
│ libpam-modules      │ CVE-2024-10041      │          │ will_not_fix │ 1.5.2-6+deb12u2        │               │ pam: libpam: Libpam vulnerable to read hashed password       │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2024-10041                   │
│                     ├─────────────────────┤          ├──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-54411      │          │ fix_deferred │                        │               │ linux-pam: Plaintext password recovery via timing            │
│                     │                     │          │              │                        │               │ discrepancy in pam_userdb module                             │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-54411                   │
├─────────────────────┼─────────────────────┤          ├──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│ libpam-modules-bin  │ CVE-2024-10041      │          │ will_not_fix │                        │               │ pam: libpam: Libpam vulnerable to read hashed password       │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2024-10041                   │
│                     ├─────────────────────┤          ├──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-54411      │          │ fix_deferred │                        │               │ linux-pam: Plaintext password recovery via timing            │
│                     │                     │          │              │                        │               │ discrepancy in pam_userdb module                             │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-54411                   │
├─────────────────────┼─────────────────────┤          ├──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│ libpam-runtime      │ CVE-2024-10041      │          │ will_not_fix │                        │               │ pam: libpam: Libpam vulnerable to read hashed password       │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2024-10041                   │
│                     ├─────────────────────┤          ├──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-54411      │          │ fix_deferred │                        │               │ linux-pam: Plaintext password recovery via timing            │
│                     │                     │          │              │                        │               │ discrepancy in pam_userdb module                             │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-54411                   │
├─────────────────────┼─────────────────────┤          ├──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│ libpam0g            │ CVE-2024-10041      │          │ will_not_fix │                        │               │ pam: libpam: Libpam vulnerable to read hashed password       │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2024-10041                   │
│                     ├─────────────────────┤          ├──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-54411      │          │ fix_deferred │                        │               │ linux-pam: Plaintext password recovery via timing            │
│                     │                     │          │              │                        │               │ discrepancy in pam_userdb module                             │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-54411                   │
├─────────────────────┼─────────────────────┤          ├──────────────┼────────────────────────┼───────────────┼──────────────────────────────────────────────────────────────┤
│ libsasl2-2          │ CVE-2026-107161     │          │ affected     │ 2.1.28+dfsg-10         │               │ cyrus-sasl: Heap buffer overflow in cyrus-sasl               │
│                     │                     │          │              │                        │               │ add_to_challenge() allows malicious server to crash...       │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-107161                  │
├─────────────────────┤                     │          │              │                        ├───────────────┤                                                              │
│ libsasl2-modules    │                     │          │              │                        │               │                                                              │
│                     │                     │          │              │                        │               │                                                              │
│                     │                     │          │              │                        │               │                                                              │
├─────────────────────┤                     │          │              │                        ├───────────────┤                                                              │
│ libsasl2-modules-db │                     │          │              │                        │               │                                                              │
│                     │                     │          │              │                        │               │                                                              │
│                     │                     │          │              │                        │               │                                                              │
├─────────────────────┼─────────────────────┼──────────┤              ├────────────────────────┼───────────────┼──────────────────────────────────────────────────────────────┤
│ libsmartcols1       │ CVE-2026-53613      │ HIGH     │              │ 2.38.1-5+deb12u3       │               │ util-linux: util-linux: TOCTOU in the mount program via      │
│                     │                     │          │              │                        │               │ ancestor directory swap on...                                │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-53613                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-53615      │          │              │                        │               │ util-linux: util-linux: Partition metadata compromise via    │
│                     │                     │          │              │                        │               │ integer overflow in DOS partition parser...                  │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-53615                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-76642      │          │              │                        │               │ util-linux: util-linux: failed external mount helper still   │
│                     │                     │          │              │                        │               │ runs privileged X-mount post-hooks                           │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-76642                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-78408      │          │              │                        │               │ util-linux: util-linux: nsenter --join-cgroup leaks root     │
│                     │                     │          │              │                        │               │ cgroup migration authority                                   │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-78408                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-78409      │          │              │                        │               │ util-linux: util-linux: X-mount.subdir detached-tree         │
│                     │                     │          │              │                        │               │ resolution can escape via intermediate symlinks              │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-78409                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-78410      │          │              │                        │               │ util-linux: util-linux: restricted bind mounts do not pin    │
│                     │                     │          │              │                        │               │ the source, allowing X-mount.owner/group/mode...             │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-78410                   │
│                     ├─────────────────────┼──────────┤              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-13595      │ MEDIUM   │              │                        │               │ util-linux: util-linux: heap use-after-free in libblkid      │
│                     │                     │          │              │                        │               │ nested partition probing                                     │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-13595                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-27456      │          │              │                        │               │ util-linux: TOCTOU in the mount program when setting up loop │
│                     │                     │          │              │                        │               │ devices                                                      │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-27456                   │
│                     ├─────────────────────┤          ├──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-3184       │          │ will_not_fix │                        │               │ util-linux: util-linux: Access control bypass due to         │
│                     │                     │          │              │                        │               │ improper hostname canonicalization                           │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-3184                    │
│                     ├─────────────────────┼──────────┼──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2022-0563       │ LOW      │ affected     │                        │               │ util-linux: partial disclosure of arbitrary files in chfn    │
│                     │                     │          │              │                        │               │ and chsh when compiled...                                    │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2022-0563                    │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2025-14104      │          │              │                        │               │ util-linux: util-linux: Heap buffer overread in setpwnam()   │
│                     │                     │          │              │                        │               │ when processing 256-byte usernames                           │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2025-14104                   │
├─────────────────────┼─────────────────────┼──────────┤              ├────────────────────────┼───────────────┼──────────────────────────────────────────────────────────────┤
│ libssl3             │ CVE-2026-84782      │ HIGH     │              │ 3.0.22-1~deb12u1       │               │ openssl: compat-openssl: openssl: Information disclosure via │
│                     │                     │          │              │                        │               │ DTLS handshake retransmission                                │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-84782                   │
│                     ├─────────────────────┼──────────┤              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-54872      │ MEDIUM   │              │                        │               │ openssl: OpenSSL: Private key recovery via timing            │
│                     │                     │          │              │                        │               │ side-channel in generic elliptic curve...                    │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-54872                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-75805      │          │              │                        │               │ openssl: openssl: Denial of Service via crafted CMP          │
│                     │                     │          │              │                        │               │ certificate revocation response                              │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-75805                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-75806      │          │              │                        │               │ openssl: OpenSSL: Denial of Service via undersized DTLS      │
│                     │                     │          │              │                        │               │ record                                                       │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-75806                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-77696      │          │              │                        │               │ openssl: OpenSSL: Private key recovery via SM2 timing        │
│                     │                     │          │              │                        │               │ side-channel                                                 │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-77696                   │
│                     ├─────────────────────┼──────────┤              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2025-27587      │ LOW      │              │                        │               │ OpenSSL 3.0.0 through 3.3.2 on the PowerPC architecture is   │
│                     │                     │          │              │                        │               │ vulnerable ......                                            │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2025-27587                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-35189      │          │              │                        │               │ openssl: openssl: Denial of Service via excessive memory     │
│                     │                     │          │              │                        │               │ allocation in CRL distribution...                            │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-35189                   │
├─────────────────────┼─────────────────────┼──────────┼──────────────┼────────────────────────┼───────────────┼──────────────────────────────────────────────────────────────┤
│ libstdc++6          │ CVE-2026-102010     │ MEDIUM   │ will_not_fix │ 12.2.0-14+deb12u1      │               │ gcc-toolset-15-gcc: gcc: gcc-toolset-16: gcc: Denial of      │
│                     │                     │          │              │                        │               │ Service via use-after-free in binary heap...                 │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-102010                  │
│                     ├─────────────────────┤          ├──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-95619      │          │ fix_deferred │                        │               │ gcc: libstdc++ integer overflow in `new` operator            │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-95619                   │
│                     ├─────────────────────┼──────────┼──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2022-27943      │ LOW      │ affected     │                        │               │ binutils: libiberty/rust-demangle.c in GNU GCC 11.2 allows   │
│                     │                     │          │              │                        │               │ stack exhaustion in demangle_const                           │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2022-27943                   │
├─────────────────────┼─────────────────────┼──────────┼──────────────┼────────────────────────┼───────────────┼──────────────────────────────────────────────────────────────┤
│ libsystemd0         │ CVE-2026-16742      │ HIGH     │ fix_deferred │ 252.39-1~deb12u2       │               │ systemd: systemd-homed: Local privilege escalation via       │
│                     │                     │          │              │                        │               │ missing home-record signature verification                   │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-16742                   │
│                     ├─────────────────────┼──────────┤              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-15059      │ MEDIUM   │              │                        │               │ systemd: systemd-oomd: Unprivileged users can terminate      │
│                     │                     │          │              │                        │               │ arbitrary processes via IPC API                              │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-15059                   │
│                     ├─────────────────────┼──────────┼──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2013-4392       │ LOW      │ affected     │                        │               │ systemd: TOCTOU race condition when updating file            │
│                     │                     │          │              │                        │               │ permissions and SELinux security contexts...                 │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2013-4392                    │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2023-31437      │          │              │                        │               │ An issue was discovered in systemd 253. An attacker can      │
│                     │                     │          │              │                        │               │ modify a...                                                  │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2023-31437                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2023-31438      │          │              │                        │               │ An issue was discovered in systemd 253. An attacker can      │
│                     │                     │          │              │                        │               │ truncate a...                                                │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2023-31438                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2023-31439      │          │              │                        │               │ An issue was discovered in systemd 253. An attacker can      │
│                     │                     │          │              │                        │               │ modify the...                                                │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2023-31439                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-40228      │          │              │                        │               │ systemd: systemd-journald: Unintended output to user         │
│                     │                     │          │              │                        │               │ terminals via logger command                                 │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-40228                   │
├─────────────────────┼─────────────────────┤          │              ├────────────────────────┼───────────────┼──────────────────────────────────────────────────────────────┤
│ libtasn1-6          │ CVE-2025-13151      │          │              │ 4.19.0-2+deb12u1       │               │ libtasn1: libtasn1: Denial of Service via stack-based buffer │
│                     │                     │          │              │                        │               │ overflow in asn1_expend_octet_string                         │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2025-13151                   │
├─────────────────────┼─────────────────────┼──────────┤              ├────────────────────────┼───────────────┼──────────────────────────────────────────────────────────────┤
│ libtinfo6           │ CVE-2025-69720      │ HIGH     │              │ 6.4-4                  │               │ ncurses: ncurses: Buffer overflow vulnerability may lead to  │
│                     │                     │          │              │                        │               │ arbitrary code execution.                                    │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2025-69720                   │
│                     ├─────────────────────┼──────────┤              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2023-50495      │ MEDIUM   │              │                        │               │ ncurses: segmentation fault via _nc_wrap_entry()             │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2023-50495                   │
│                     ├─────────────────────┼──────────┤              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2025-6141       │ LOW      │              │                        │               │ gnu-ncurses: ncurses Stack Buffer Overflow                   │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2025-6141                    │
├─────────────────────┼─────────────────────┼──────────┼──────────────┼────────────────────────┼───────────────┼──────────────────────────────────────────────────────────────┤
│ libudev1            │ CVE-2026-16742      │ HIGH     │ fix_deferred │ 252.39-1~deb12u2       │               │ systemd: systemd-homed: Local privilege escalation via       │
│                     │                     │          │              │                        │               │ missing home-record signature verification                   │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-16742                   │
│                     ├─────────────────────┼──────────┤              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-15059      │ MEDIUM   │              │                        │               │ systemd: systemd-oomd: Unprivileged users can terminate      │
│                     │                     │          │              │                        │               │ arbitrary processes via IPC API                              │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-15059                   │
│                     ├─────────────────────┼──────────┼──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2013-4392       │ LOW      │ affected     │                        │               │ systemd: TOCTOU race condition when updating file            │
│                     │                     │          │              │                        │               │ permissions and SELinux security contexts...                 │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2013-4392                    │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2023-31437      │          │              │                        │               │ An issue was discovered in systemd 253. An attacker can      │
│                     │                     │          │              │                        │               │ modify a...                                                  │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2023-31437                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2023-31438      │          │              │                        │               │ An issue was discovered in systemd 253. An attacker can      │
│                     │                     │          │              │                        │               │ truncate a...                                                │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2023-31438                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2023-31439      │          │              │                        │               │ An issue was discovered in systemd 253. An attacker can      │
│                     │                     │          │              │                        │               │ modify the...                                                │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2023-31439                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-40228      │          │              │                        │               │ systemd: systemd-journald: Unintended output to user         │
│                     │                     │          │              │                        │               │ terminals via logger command                                 │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-40228                   │
├─────────────────────┼─────────────────────┼──────────┤              ├────────────────────────┼───────────────┼──────────────────────────────────────────────────────────────┤
│ libuuid1            │ CVE-2026-53613      │ HIGH     │              │ 2.38.1-5+deb12u3       │               │ util-linux: util-linux: TOCTOU in the mount program via      │
│                     │                     │          │              │                        │               │ ancestor directory swap on...                                │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-53613                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-53615      │          │              │                        │               │ util-linux: util-linux: Partition metadata compromise via    │
│                     │                     │          │              │                        │               │ integer overflow in DOS partition parser...                  │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-53615                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-76642      │          │              │                        │               │ util-linux: util-linux: failed external mount helper still   │
│                     │                     │          │              │                        │               │ runs privileged X-mount post-hooks                           │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-76642                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-78408      │          │              │                        │               │ util-linux: util-linux: nsenter --join-cgroup leaks root     │
│                     │                     │          │              │                        │               │ cgroup migration authority                                   │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-78408                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-78409      │          │              │                        │               │ util-linux: util-linux: X-mount.subdir detached-tree         │
│                     │                     │          │              │                        │               │ resolution can escape via intermediate symlinks              │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-78409                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-78410      │          │              │                        │               │ util-linux: util-linux: restricted bind mounts do not pin    │
│                     │                     │          │              │                        │               │ the source, allowing X-mount.owner/group/mode...             │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-78410                   │
│                     ├─────────────────────┼──────────┤              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-13595      │ MEDIUM   │              │                        │               │ util-linux: util-linux: heap use-after-free in libblkid      │
│                     │                     │          │              │                        │               │ nested partition probing                                     │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-13595                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-27456      │          │              │                        │               │ util-linux: TOCTOU in the mount program when setting up loop │
│                     │                     │          │              │                        │               │ devices                                                      │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-27456                   │
│                     ├─────────────────────┤          ├──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-3184       │          │ will_not_fix │                        │               │ util-linux: util-linux: Access control bypass due to         │
│                     │                     │          │              │                        │               │ improper hostname canonicalization                           │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-3184                    │
│                     ├─────────────────────┼──────────┼──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2022-0563       │ LOW      │ affected     │                        │               │ util-linux: partial disclosure of arbitrary files in chfn    │
│                     │                     │          │              │                        │               │ and chsh when compiled...                                    │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2022-0563                    │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2025-14104      │          │              │                        │               │ util-linux: util-linux: Heap buffer overread in setpwnam()   │
│                     │                     │          │              │                        │               │ when processing 256-byte usernames                           │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2025-14104                   │
├─────────────────────┼─────────────────────┤          │              ├────────────────────────┼───────────────┼──────────────────────────────────────────────────────────────┤
│ login               │ CVE-2007-5686       │          │              │ 1:4.13+dfsg1-1+deb12u2 │               │ initscripts in rPath Linux 1 sets insecure permissions for   │
│                     │                     │          │              │                        │               │ the /var/lo ......                                           │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2007-5686                    │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2024-56433      │          │              │                        │               │ shadow-utils: Default subordinate ID configuration in        │
│                     │                     │          │              │                        │               │ /etc/login.defs could lead to compromise                     │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2024-56433                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ TEMP-0628843-DBAD28 │          │              │                        │               │ [more related to CVE-2005-4890]                              │
│                     │                     │          │              │                        │               │ https://security-tracker.debian.org/tracker/TEMP-0628843-DB- │
│                     │                     │          │              │                        │               │ AD28                                                         │
├─────────────────────┼─────────────────────┼──────────┤              ├────────────────────────┼───────────────┼──────────────────────────────────────────────────────────────┤
│ mount               │ CVE-2026-53613      │ HIGH     │              │ 2.38.1-5+deb12u3       │               │ util-linux: util-linux: TOCTOU in the mount program via      │
│                     │                     │          │              │                        │               │ ancestor directory swap on...                                │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-53613                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-53615      │          │              │                        │               │ util-linux: util-linux: Partition metadata compromise via    │
│                     │                     │          │              │                        │               │ integer overflow in DOS partition parser...                  │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-53615                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-76642      │          │              │                        │               │ util-linux: util-linux: failed external mount helper still   │
│                     │                     │          │              │                        │               │ runs privileged X-mount post-hooks                           │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-76642                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-78408      │          │              │                        │               │ util-linux: util-linux: nsenter --join-cgroup leaks root     │
│                     │                     │          │              │                        │               │ cgroup migration authority                                   │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-78408                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-78409      │          │              │                        │               │ util-linux: util-linux: X-mount.subdir detached-tree         │
│                     │                     │          │              │                        │               │ resolution can escape via intermediate symlinks              │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-78409                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-78410      │          │              │                        │               │ util-linux: util-linux: restricted bind mounts do not pin    │
│                     │                     │          │              │                        │               │ the source, allowing X-mount.owner/group/mode...             │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-78410                   │
│                     ├─────────────────────┼──────────┤              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-13595      │ MEDIUM   │              │                        │               │ util-linux: util-linux: heap use-after-free in libblkid      │
│                     │                     │          │              │                        │               │ nested partition probing                                     │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-13595                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-27456      │          │              │                        │               │ util-linux: TOCTOU in the mount program when setting up loop │
│                     │                     │          │              │                        │               │ devices                                                      │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-27456                   │
│                     ├─────────────────────┤          ├──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-3184       │          │ will_not_fix │                        │               │ util-linux: util-linux: Access control bypass due to         │
│                     │                     │          │              │                        │               │ improper hostname canonicalization                           │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-3184                    │
│                     ├─────────────────────┼──────────┼──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2022-0563       │ LOW      │ affected     │                        │               │ util-linux: partial disclosure of arbitrary files in chfn    │
│                     │                     │          │              │                        │               │ and chsh when compiled...                                    │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2022-0563                    │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2025-14104      │          │              │                        │               │ util-linux: util-linux: Heap buffer overread in setpwnam()   │
│                     │                     │          │              │                        │               │ when processing 256-byte usernames                           │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2025-14104                   │
├─────────────────────┼─────────────────────┼──────────┤              ├────────────────────────┼───────────────┼──────────────────────────────────────────────────────────────┤
│ ncurses-base        │ CVE-2025-69720      │ HIGH     │              │ 6.4-4                  │               │ ncurses: ncurses: Buffer overflow vulnerability may lead to  │
│                     │                     │          │              │                        │               │ arbitrary code execution.                                    │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2025-69720                   │
│                     ├─────────────────────┼──────────┤              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2023-50495      │ MEDIUM   │              │                        │               │ ncurses: segmentation fault via _nc_wrap_entry()             │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2023-50495                   │
│                     ├─────────────────────┼──────────┤              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2025-6141       │ LOW      │              │                        │               │ gnu-ncurses: ncurses Stack Buffer Overflow                   │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2025-6141                    │
├─────────────────────┼─────────────────────┼──────────┤              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│ ncurses-bin         │ CVE-2025-69720      │ HIGH     │              │                        │               │ ncurses: ncurses: Buffer overflow vulnerability may lead to  │
│                     │                     │          │              │                        │               │ arbitrary code execution.                                    │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2025-69720                   │
│                     ├─────────────────────┼──────────┤              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2023-50495      │ MEDIUM   │              │                        │               │ ncurses: segmentation fault via _nc_wrap_entry()             │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2023-50495                   │
│                     ├─────────────────────┼──────────┤              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2025-6141       │ LOW      │              │                        │               │ gnu-ncurses: ncurses Stack Buffer Overflow                   │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2025-6141                    │
├─────────────────────┼─────────────────────┼──────────┤              ├────────────────────────┼───────────────┼──────────────────────────────────────────────────────────────┤
│ openssl             │ CVE-2026-84782      │ HIGH     │              │ 3.0.22-1~deb12u1       │               │ openssl: compat-openssl: openssl: Information disclosure via │
│                     │                     │          │              │                        │               │ DTLS handshake retransmission                                │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-84782                   │
│                     ├─────────────────────┼──────────┤              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-54872      │ MEDIUM   │              │                        │               │ openssl: OpenSSL: Private key recovery via timing            │
│                     │                     │          │              │                        │               │ side-channel in generic elliptic curve...                    │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-54872                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-75805      │          │              │                        │               │ openssl: openssl: Denial of Service via crafted CMP          │
│                     │                     │          │              │                        │               │ certificate revocation response                              │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-75805                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-75806      │          │              │                        │               │ openssl: OpenSSL: Denial of Service via undersized DTLS      │
│                     │                     │          │              │                        │               │ record                                                       │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-75806                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-77696      │          │              │                        │               │ openssl: OpenSSL: Private key recovery via SM2 timing        │
│                     │                     │          │              │                        │               │ side-channel                                                 │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-77696                   │
│                     ├─────────────────────┼──────────┤              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2025-27587      │ LOW      │              │                        │               │ OpenSSL 3.0.0 through 3.3.2 on the PowerPC architecture is   │
│                     │                     │          │              │                        │               │ vulnerable ......                                            │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2025-27587                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-35189      │          │              │                        │               │ openssl: openssl: Denial of Service via excessive memory     │
│                     │                     │          │              │                        │               │ allocation in CRL distribution...                            │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-35189                   │
├─────────────────────┼─────────────────────┤          │              ├────────────────────────┼───────────────┼──────────────────────────────────────────────────────────────┤
│ passwd              │ CVE-2007-5686       │          │              │ 1:4.13+dfsg1-1+deb12u2 │               │ initscripts in rPath Linux 1 sets insecure permissions for   │
│                     │                     │          │              │                        │               │ the /var/lo ......                                           │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2007-5686                    │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2024-56433      │          │              │                        │               │ shadow-utils: Default subordinate ID configuration in        │
│                     │                     │          │              │                        │               │ /etc/login.defs could lead to compromise                     │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2024-56433                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ TEMP-0628843-DBAD28 │          │              │                        │               │ [more related to CVE-2005-4890]                              │
│                     │                     │          │              │                        │               │ https://security-tracker.debian.org/tracker/TEMP-0628843-DB- │
│                     │                     │          │              │                        │               │ AD28                                                         │
├─────────────────────┼─────────────────────┼──────────┼──────────────┼────────────────────────┼───────────────┼──────────────────────────────────────────────────────────────┤
│ perl-base           │ CVE-2026-9538       │ HIGH     │ fix_deferred │ 5.36.0-7+deb12u4       │               │ perl-Archive-Tar: perl-Archive-Tar: Denial of Service via    │
│                     │                     │          │              │                        │               │ crafted tar header with large entry...                       │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-9538                    │
│                     ├─────────────────────┼──────────┼──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-15534      │ MEDIUM   │ affected     │                        │               │ perl: Perl: Arbitrary code execution via out-of-bounds       │
│                     │                     │          │              │                        │               │ memory access in regular expression...                       │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-15534                   │
│                     ├─────────────────────┼──────────┤              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2011-4116       │ LOW      │              │                        │               │ perl: File:: Temp insecure temporary file handling           │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2011-4116                    │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2023-31486      │          │              │                        │               │ http-tiny: perl: insecure TLS cert default                   │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2023-31486                   │
│                     ├─────────────────────┼──────────┤              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-82560      │ UNKNOWN  │              │                        │               │ Pod::Text versions before 6.1.1 for Perl allow CPU and       │
│                     │                     │          │              │                        │               │ memory exhausti ......                                       │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-82560                   │
├─────────────────────┼─────────────────────┼──────────┤              ├────────────────────────┼───────────────┼──────────────────────────────────────────────────────────────┤
│ sysvinit-utils      │ TEMP-0517018-A83CE6 │ LOW      │              │ 3.06-4                 │               │ [sysvinit: no-root option in expert installer exposes        │
│                     │                     │          │              │                        │               │ locally exploitable security flaw]                           │
│                     │                     │          │              │                        │               │ https://security-tracker.debian.org/tracker/TEMP-0517018-A8- │
│                     │                     │          │              │                        │               │ 3CE6                                                         │
├─────────────────────┼─────────────────────┼──────────┼──────────────┼────────────────────────┼───────────────┼──────────────────────────────────────────────────────────────┤
│ tar                 │ CVE-2026-18477      │ MEDIUM   │ fix_deferred │ 1.34+dfsg-1.2+deb12u1  │               │ tar: tar: TOCTOU in incremental dumpdir 'X' rename handling  │
│                     │                     │          │              │                        │               │ allows restore path...                                       │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-18477                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-18508      │          │              │                        │               │ tar: tar: --one-top-level hardlink targets not confined to   │
│                     │                     │          │              │                        │               │ top-level directory enabling arbitrary...                    │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-18508                   │
│                     ├─────────────────────┤          ├──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-5704       │          │ affected     │                        │               │ tar: tar: Hidden file injection via crafted archives         │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-5704                    │
│                     ├─────────────────────┼──────────┤              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2005-2541       │ LOW      │              │                        │               │ tar: does not properly warn the user when extracting setuid  │
│                     │                     │          │              │                        │               │ or setgid...                                                 │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2005-2541                    │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ TEMP-0290435-0B57B5 │          │              │                        │               │ [tar's rmt command may have undesired side effects]          │
│                     │                     │          │              │                        │               │ https://security-tracker.debian.org/tracker/TEMP-0290435-0B- │
│                     │                     │          │              │                        │               │ 57B5                                                         │
├─────────────────────┼─────────────────────┼──────────┤              ├────────────────────────┼───────────────┼──────────────────────────────────────────────────────────────┤
│ util-linux          │ CVE-2026-53613      │ HIGH     │              │ 2.38.1-5+deb12u3       │               │ util-linux: util-linux: TOCTOU in the mount program via      │
│                     │                     │          │              │                        │               │ ancestor directory swap on...                                │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-53613                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-53615      │          │              │                        │               │ util-linux: util-linux: Partition metadata compromise via    │
│                     │                     │          │              │                        │               │ integer overflow in DOS partition parser...                  │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-53615                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-76642      │          │              │                        │               │ util-linux: util-linux: failed external mount helper still   │
│                     │                     │          │              │                        │               │ runs privileged X-mount post-hooks                           │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-76642                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-78408      │          │              │                        │               │ util-linux: util-linux: nsenter --join-cgroup leaks root     │
│                     │                     │          │              │                        │               │ cgroup migration authority                                   │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-78408                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-78409      │          │              │                        │               │ util-linux: util-linux: X-mount.subdir detached-tree         │
│                     │                     │          │              │                        │               │ resolution can escape via intermediate symlinks              │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-78409                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-78410      │          │              │                        │               │ util-linux: util-linux: restricted bind mounts do not pin    │
│                     │                     │          │              │                        │               │ the source, allowing X-mount.owner/group/mode...             │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-78410                   │
│                     ├─────────────────────┼──────────┤              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-13595      │ MEDIUM   │              │                        │               │ util-linux: util-linux: heap use-after-free in libblkid      │
│                     │                     │          │              │                        │               │ nested partition probing                                     │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-13595                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-27456      │          │              │                        │               │ util-linux: TOCTOU in the mount program when setting up loop │
│                     │                     │          │              │                        │               │ devices                                                      │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-27456                   │
│                     ├─────────────────────┤          ├──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-3184       │          │ will_not_fix │                        │               │ util-linux: util-linux: Access control bypass due to         │
│                     │                     │          │              │                        │               │ improper hostname canonicalization                           │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-3184                    │
│                     ├─────────────────────┼──────────┼──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2022-0563       │ LOW      │ affected     │                        │               │ util-linux: partial disclosure of arbitrary files in chfn    │
│                     │                     │          │              │                        │               │ and chsh when compiled...                                    │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2022-0563                    │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2025-14104      │          │              │                        │               │ util-linux: util-linux: Heap buffer overread in setpwnam()   │
│                     │                     │          │              │                        │               │ when processing 256-byte usernames                           │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2025-14104                   │
├─────────────────────┼─────────────────────┼──────────┤              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│ util-linux-extra    │ CVE-2026-53613      │ HIGH     │              │                        │               │ util-linux: util-linux: TOCTOU in the mount program via      │
│                     │                     │          │              │                        │               │ ancestor directory swap on...                                │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-53613                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-53615      │          │              │                        │               │ util-linux: util-linux: Partition metadata compromise via    │
│                     │                     │          │              │                        │               │ integer overflow in DOS partition parser...                  │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-53615                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-76642      │          │              │                        │               │ util-linux: util-linux: failed external mount helper still   │
│                     │                     │          │              │                        │               │ runs privileged X-mount post-hooks                           │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-76642                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-78408      │          │              │                        │               │ util-linux: util-linux: nsenter --join-cgroup leaks root     │
│                     │                     │          │              │                        │               │ cgroup migration authority                                   │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-78408                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-78409      │          │              │                        │               │ util-linux: util-linux: X-mount.subdir detached-tree         │
│                     │                     │          │              │                        │               │ resolution can escape via intermediate symlinks              │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-78409                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-78410      │          │              │                        │               │ util-linux: util-linux: restricted bind mounts do not pin    │
│                     │                     │          │              │                        │               │ the source, allowing X-mount.owner/group/mode...             │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-78410                   │
│                     ├─────────────────────┼──────────┤              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-13595      │ MEDIUM   │              │                        │               │ util-linux: util-linux: heap use-after-free in libblkid      │
│                     │                     │          │              │                        │               │ nested partition probing                                     │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-13595                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-27456      │          │              │                        │               │ util-linux: TOCTOU in the mount program when setting up loop │
│                     │                     │          │              │                        │               │ devices                                                      │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-27456                   │
│                     ├─────────────────────┤          ├──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-3184       │          │ will_not_fix │                        │               │ util-linux: util-linux: Access control bypass due to         │
│                     │                     │          │              │                        │               │ improper hostname canonicalization                           │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-3184                    │
│                     ├─────────────────────┼──────────┼──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2022-0563       │ LOW      │ affected     │                        │               │ util-linux: partial disclosure of arbitrary files in chfn    │
│                     │                     │          │              │                        │               │ and chsh when compiled...                                    │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2022-0563                    │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2025-14104      │          │              │                        │               │ util-linux: util-linux: Heap buffer overread in setpwnam()   │
│                     │                     │          │              │                        │               │ when processing 256-byte usernames                           │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2025-14104                   │
├─────────────────────┼─────────────────────┼──────────┼──────────────┼────────────────────────┼───────────────┼──────────────────────────────────────────────────────────────┤
│ zlib1g              │ CVE-2023-45853      │ CRITICAL │ will_not_fix │ 1:1.2.13.dfsg-1        │               │ zlib: integer overflow and resultant heap-based buffer       │
│                     │                     │          │              │                        │               │ overflow in zipOpenNewFileInZip4_6                           │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2023-45853                   │
│                     ├─────────────────────┼──────────┼──────────────┤                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-27171      │ MEDIUM   │ affected     │                        │               │ zlib: zlib: Denial of Service via infinite loop in CRC32     │
│                     │                     │          │              │                        │               │ combine functions...                                         │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-27171                   │
│                     ├─────────────────────┤          │              │                        ├───────────────┼──────────────────────────────────────────────────────────────┤
│                     │ CVE-2026-85091      │          │              │                        │               │ zlib versions 1.3.1.2 through 1.3.2 contain a heap buffer    │
│                     │                     │          │              │                        │               │ overflow vul ......                                          │
│                     │                     │          │              │                        │               │ https://avd.aquasec.com/nvd/cve-2026-85091                   │
└─────────────────────┴─────────────────────┴──────────┴──────────────┴────────────────────────┴───────────────┴──────────────────────────────────────────────────────────────┘

app/stoa-gateway (rustbinary)
=============================
Total: 1 (UNKNOWN: 0, LOW: 0, MEDIUM: 1, HIGH: 0, CRITICAL: 0)

┌───────────────────┬────────────────┬──────────┬────────┬───────────────────┬───────────────┬──────────────────────────────────────────────────────────┐
│      Library      │ Vulnerability  │ Severity │ Status │ Installed Version │ Fixed Version │                          Title                           │
├───────────────────┼────────────────┼──────────┼────────┼───────────────────┼───────────────┼──────────────────────────────────────────────────────────┤
│ opentelemetry_sdk │ CVE-2026-48504 │ MEDIUM   │ fixed  │ 0.27.1            │ 0.32.1        │ opentelemetry_sdk has unbounded memory allocation in W3C │
│                   │                │          │        │                   │               │ Baggage propagation                                      │
│                   │                │          │        │                   │               │ https://avd.aquasec.com/nvd/cve-2026-48504               │
└───────────────────┴────────────────┴──────────┴────────┴───────────────────┴───────────────┴──────────────────────────────────────────────────────────┘
```

## SBOM

CycloneDX from `trivy image --input deploy/standalone/stoa-gateway-standalone.tar --format cyclonedx`. 414 components, including `pkg:cargo/quick-xml@0.39.4`. Same bytes as `deploy/standalone/stoa-gateway-standalone.cdx.json` (gitignored) and the agent-store copy.

```json
{
  "$schema": "http://cyclonedx.org/schema/bom-1.6.schema.json",
  "bomFormat": "CycloneDX",
  "specVersion": "1.6",
  "serialNumber": "urn:uuid:73d19584-892a-4591-b1d0-1b39a2a13514",
  "version": 1,
  "metadata": {
    "timestamp": "2026-10-21T17:53:16+00:00",
    "tools": {
      "components": [
        {
          "type": "application",
          "group": "aquasecurity",
          "name": "trivy",
          "version": "0.58.1"
        }
      ]
    },
    "component": {
      "bom-ref": "e83fff54-c213-4eb4-bff9-ecae09e3e054",
      "type": "container",
      "name": "/workspace/deploy/standalone/stoa-gateway-standalone.tar",
      "properties": [
        {
          "name": "aquasecurity:trivy:DiffID",
          "value": "sha256:041fa36e7b553df7512e26cdd7928c7b0d6bd791c9548f15bb7cd65e1bf263dc"
        },
        {
          "name": "aquasecurity:trivy:DiffID",
          "value": "sha256:2d38fbc95e2fae0ba3d9f337dd0a5cb13f43d4a46122f49ea6310c5d2a9676f3"
        },
        {
          "name": "aquasecurity:trivy:DiffID",
          "value": "sha256:60992be8344f4aa87e8d369bfb6fa4e963c774eacb2f0480b307d1f07f7b8656"
        },
        {
          "name": "aquasecurity:trivy:DiffID",
          "value": "sha256:7382b2d6f195cd4e5db720b0914e21cbc5530ac4ed578ddd8d5f0b083615cc50"
        },
        {
          "name": "aquasecurity:trivy:DiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:DiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:ImageID",
          "value": "sha256:bc751600ea87162db85c69805911f1caf23c75784c4edcf0252ff6d4534476fe"
        },
        {
          "name": "aquasecurity:trivy:Labels:org.opencontainers.image.revision",
          "value": "fe1e5a3271d47f9788482c972f1a692e2350927c"
        },
        {
          "name": "aquasecurity:trivy:Labels:org.opencontainers.image.source",
          "value": "https://github.com/stoa-platform/stoa"
        },
        {
          "name": "aquasecurity:trivy:Labels:org.opencontainers.image.title",
          "value": "stoa-gateway"
        },
        {
          "name": "aquasecurity:trivy:SchemaVersion",
          "value": "2"
        }
      ]
    }
  },
  "components": [
    {
      "bom-ref": "157d1c05-2b49-4cd7-b32d-47b79ca3b8a1",
      "type": "application",
      "name": "app/stoa-gateway",
      "properties": [
        {
          "name": "aquasecurity:trivy:Class",
          "value": "lang-pkgs"
        },
        {
          "name": "aquasecurity:trivy:Type",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "f62f0ba9-863c-4578-8673-8faa46f5ae12",
      "type": "operating-system",
      "name": "debian",
      "version": "12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:Class",
          "value": "os-pkgs"
        },
        {
          "name": "aquasecurity:trivy:Type",
          "value": "debian"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/ahash@0.8.12",
      "type": "library",
      "name": "ahash",
      "version": "0.8.12",
      "purl": "pkg:cargo/ahash@0.8.12",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "ahash@0.8.12"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/aho-corasick@1.1.5",
      "type": "library",
      "name": "aho-corasick",
      "version": "1.1.5",
      "purl": "pkg:cargo/aho-corasick@1.1.5",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "aho-corasick@1.1.5"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/anyhow@1.0.104",
      "type": "library",
      "name": "anyhow",
      "version": "1.0.104",
      "purl": "pkg:cargo/anyhow@1.0.104",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "anyhow@1.0.104"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/arc-swap@1.9.3",
      "type": "library",
      "name": "arc-swap",
      "version": "1.9.3",
      "purl": "pkg:cargo/arc-swap@1.9.3",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "arc-swap@1.9.3"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/async-lock@3.4.2",
      "type": "library",
      "name": "async-lock",
      "version": "3.4.2",
      "purl": "pkg:cargo/async-lock@3.4.2",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "async-lock@3.4.2"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/async-stream@0.3.6",
      "type": "library",
      "name": "async-stream",
      "version": "0.3.6",
      "purl": "pkg:cargo/async-stream@0.3.6",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "async-stream@0.3.6"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/async-trait@0.1.92",
      "type": "library",
      "name": "async-trait",
      "version": "0.1.92",
      "purl": "pkg:cargo/async-trait@0.1.92",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "async-trait@0.1.92"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/atomic-waker@1.1.2",
      "type": "library",
      "name": "atomic-waker",
      "version": "1.1.2",
      "purl": "pkg:cargo/atomic-waker@1.1.2",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "atomic-waker@1.1.2"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/axum-core@0.4.5",
      "type": "library",
      "name": "axum-core",
      "version": "0.4.5",
      "purl": "pkg:cargo/axum-core@0.4.5",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "axum-core@0.4.5"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/axum@0.7.9",
      "type": "library",
      "name": "axum",
      "version": "0.7.9",
      "purl": "pkg:cargo/axum@0.7.9",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "axum@0.7.9"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/base16ct@0.2.0",
      "type": "library",
      "name": "base16ct",
      "version": "0.2.0",
      "purl": "pkg:cargo/base16ct@0.2.0",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "base16ct@0.2.0"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/base64@0.22.1",
      "type": "library",
      "name": "base64",
      "version": "0.22.1",
      "purl": "pkg:cargo/base64@0.22.1",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "base64@0.22.1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/base64@0.23.1",
      "type": "library",
      "name": "base64",
      "version": "0.23.1",
      "purl": "pkg:cargo/base64@0.23.1",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "base64@0.23.1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/base64ct@1.8.3",
      "type": "library",
      "name": "base64ct",
      "version": "1.8.3",
      "purl": "pkg:cargo/base64ct@1.8.3",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "base64ct@1.8.3"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/bincode@2.0.1",
      "type": "library",
      "name": "bincode",
      "version": "2.0.1",
      "purl": "pkg:cargo/bincode@2.0.1",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "bincode@2.0.1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/bit-set@0.8.0",
      "type": "library",
      "name": "bit-set",
      "version": "0.8.0",
      "purl": "pkg:cargo/bit-set@0.8.0",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "bit-set@0.8.0"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/bit-vec@0.8.0",
      "type": "library",
      "name": "bit-vec",
      "version": "0.8.0",
      "purl": "pkg:cargo/bit-vec@0.8.0",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "bit-vec@0.8.0"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/bitflags@2.13.2",
      "type": "library",
      "name": "bitflags",
      "version": "2.13.2",
      "purl": "pkg:cargo/bitflags@2.13.2",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "bitflags@2.13.2"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/block-buffer@0.10.4",
      "type": "library",
      "name": "block-buffer",
      "version": "0.10.4",
      "purl": "pkg:cargo/block-buffer@0.10.4",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "block-buffer@0.10.4"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/block-buffer@0.12.1",
      "type": "library",
      "name": "block-buffer",
      "version": "0.12.1",
      "purl": "pkg:cargo/block-buffer@0.12.1",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "block-buffer@0.12.1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/borrow-or-share@0.2.4",
      "type": "library",
      "name": "borrow-or-share",
      "version": "0.2.4",
      "purl": "pkg:cargo/borrow-or-share@0.2.4",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "borrow-or-share@0.2.4"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/bstr@1.13.1",
      "type": "library",
      "name": "bstr",
      "version": "1.13.1",
      "purl": "pkg:cargo/bstr@1.13.1",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "bstr@1.13.1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/bytecount@0.6.9",
      "type": "library",
      "name": "bytecount",
      "version": "0.6.9",
      "purl": "pkg:cargo/bytecount@0.6.9",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "bytecount@0.6.9"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/byteorder@1.5.0",
      "type": "library",
      "name": "byteorder",
      "version": "1.5.0",
      "purl": "pkg:cargo/byteorder@1.5.0",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "byteorder@1.5.0"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/bytes@1.12.1",
      "type": "library",
      "name": "bytes",
      "version": "1.12.1",
      "purl": "pkg:cargo/bytes@1.12.1",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "bytes@1.12.1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/cfg-if@1.0.5",
      "type": "library",
      "name": "cfg-if",
      "version": "1.0.5",
      "purl": "pkg:cargo/cfg-if@1.0.5",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "cfg-if@1.0.5"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/chacha20@0.10.2",
      "type": "library",
      "name": "chacha20",
      "version": "0.10.2",
      "purl": "pkg:cargo/chacha20@0.10.2",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "chacha20@0.10.2"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/chrono-tz@0.10.4",
      "type": "library",
      "name": "chrono-tz",
      "version": "0.10.4",
      "purl": "pkg:cargo/chrono-tz@0.10.4",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "chrono-tz@0.10.4"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/chrono@0.4.45",
      "type": "library",
      "name": "chrono",
      "version": "0.4.45",
      "purl": "pkg:cargo/chrono@0.4.45",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "chrono@0.4.45"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/const-oid@0.10.2",
      "type": "library",
      "name": "const-oid",
      "version": "0.10.2",
      "purl": "pkg:cargo/const-oid@0.10.2",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "const-oid@0.10.2"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/const-oid@0.9.6",
      "type": "library",
      "name": "const-oid",
      "version": "0.9.6",
      "purl": "pkg:cargo/const-oid@0.9.6",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "const-oid@0.9.6"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/cpufeatures@0.2.17",
      "type": "library",
      "name": "cpufeatures",
      "version": "0.2.17",
      "purl": "pkg:cargo/cpufeatures@0.2.17",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "cpufeatures@0.2.17"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/cpufeatures@0.3.1",
      "type": "library",
      "name": "cpufeatures",
      "version": "0.3.1",
      "purl": "pkg:cargo/cpufeatures@0.3.1",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "cpufeatures@0.3.1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/crossbeam-channel@0.5.17",
      "type": "library",
      "name": "crossbeam-channel",
      "version": "0.5.17",
      "purl": "pkg:cargo/crossbeam-channel@0.5.17",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "crossbeam-channel@0.5.17"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/crossbeam-epoch@0.9.21",
      "type": "library",
      "name": "crossbeam-epoch",
      "version": "0.9.21",
      "purl": "pkg:cargo/crossbeam-epoch@0.9.21",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "crossbeam-epoch@0.9.21"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/crossbeam-utils@0.8.23",
      "type": "library",
      "name": "crossbeam-utils",
      "version": "0.8.23",
      "purl": "pkg:cargo/crossbeam-utils@0.8.23",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "crossbeam-utils@0.8.23"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/crypto-bigint@0.5.5",
      "type": "library",
      "name": "crypto-bigint",
      "version": "0.5.5",
      "purl": "pkg:cargo/crypto-bigint@0.5.5",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "crypto-bigint@0.5.5"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/crypto-common@0.1.6",
      "type": "library",
      "name": "crypto-common",
      "version": "0.1.6",
      "purl": "pkg:cargo/crypto-common@0.1.6",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "crypto-common@0.1.6"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/crypto-common@0.2.2",
      "type": "library",
      "name": "crypto-common",
      "version": "0.2.2",
      "purl": "pkg:cargo/crypto-common@0.2.2",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "crypto-common@0.2.2"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/curve25519-dalek-derive@0.1.1",
      "type": "library",
      "name": "curve25519-dalek-derive",
      "version": "0.1.1",
      "purl": "pkg:cargo/curve25519-dalek-derive@0.1.1",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "curve25519-dalek-derive@0.1.1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/curve25519-dalek@4.1.3",
      "type": "library",
      "name": "curve25519-dalek",
      "version": "4.1.3",
      "purl": "pkg:cargo/curve25519-dalek@4.1.3",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "curve25519-dalek@4.1.3"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/data-encoding@2.11.1",
      "type": "library",
      "name": "data-encoding",
      "version": "2.11.1",
      "purl": "pkg:cargo/data-encoding@2.11.1",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "data-encoding@2.11.1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/der@0.7.10",
      "type": "library",
      "name": "der",
      "version": "0.7.10",
      "purl": "pkg:cargo/der@0.7.10",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "der@0.7.10"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/deranged@0.5.9",
      "type": "library",
      "name": "deranged",
      "version": "0.5.9",
      "purl": "pkg:cargo/deranged@0.5.9",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "deranged@0.5.9"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/digest@0.10.7",
      "type": "library",
      "name": "digest",
      "version": "0.10.7",
      "purl": "pkg:cargo/digest@0.10.7",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "digest@0.10.7"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/digest@0.11.3",
      "type": "library",
      "name": "digest",
      "version": "0.11.3",
      "purl": "pkg:cargo/digest@0.11.3",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "digest@0.11.3"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/displaydoc@0.2.7",
      "type": "library",
      "name": "displaydoc",
      "version": "0.2.7",
      "purl": "pkg:cargo/displaydoc@0.2.7",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "displaydoc@0.2.7"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/ecdsa@0.16.9",
      "type": "library",
      "name": "ecdsa",
      "version": "0.16.9",
      "purl": "pkg:cargo/ecdsa@0.16.9",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "ecdsa@0.16.9"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/ed25519-dalek@2.2.0",
      "type": "library",
      "name": "ed25519-dalek",
      "version": "2.2.0",
      "purl": "pkg:cargo/ed25519-dalek@2.2.0",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "ed25519-dalek@2.2.0"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/ed25519@2.2.3",
      "type": "library",
      "name": "ed25519",
      "version": "2.2.3",
      "purl": "pkg:cargo/ed25519@2.2.3",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "ed25519@2.2.3"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/elliptic-curve@0.13.8",
      "type": "library",
      "name": "elliptic-curve",
      "version": "0.13.8",
      "purl": "pkg:cargo/elliptic-curve@0.13.8",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "elliptic-curve@0.13.8"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/email_address@0.2.9",
      "type": "library",
      "name": "email_address",
      "version": "0.2.9",
      "purl": "pkg:cargo/email_address@0.2.9",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "email_address@0.2.9"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/equivalent@1.0.3",
      "type": "library",
      "name": "equivalent",
      "version": "1.0.3",
      "purl": "pkg:cargo/equivalent@1.0.3",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "equivalent@1.0.3"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/errno@0.3.14",
      "type": "library",
      "name": "errno",
      "version": "0.3.14",
      "purl": "pkg:cargo/errno@0.3.14",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "errno@0.3.14"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/event-listener-strategy@0.5.4",
      "type": "library",
      "name": "event-listener-strategy",
      "version": "0.5.4",
      "purl": "pkg:cargo/event-listener-strategy@0.5.4",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "event-listener-strategy@0.5.4"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/event-listener@5.4.2",
      "type": "library",
      "name": "event-listener",
      "version": "5.4.2",
      "purl": "pkg:cargo/event-listener@5.4.2",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "event-listener@5.4.2"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/fancy-regex@0.14.0",
      "type": "library",
      "name": "fancy-regex",
      "version": "0.14.0",
      "purl": "pkg:cargo/fancy-regex@0.14.0",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "fancy-regex@0.14.0"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/fastrand@2.5.0",
      "type": "library",
      "name": "fastrand",
      "version": "2.5.0",
      "purl": "pkg:cargo/fastrand@2.5.0",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "fastrand@2.5.0"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/ff@0.13.1",
      "type": "library",
      "name": "ff",
      "version": "0.13.1",
      "purl": "pkg:cargo/ff@0.13.1",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "ff@0.13.1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/figment@0.10.19",
      "type": "library",
      "name": "figment",
      "version": "0.10.19",
      "purl": "pkg:cargo/figment@0.10.19",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "figment@0.10.19"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/fluent-uri@0.3.2",
      "type": "library",
      "name": "fluent-uri",
      "version": "0.3.2",
      "purl": "pkg:cargo/fluent-uri@0.3.2",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "fluent-uri@0.3.2"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/fnv@1.0.7",
      "type": "library",
      "name": "fnv",
      "version": "1.0.7",
      "purl": "pkg:cargo/fnv@1.0.7",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "fnv@1.0.7"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/form_urlencoded@1.2.2",
      "type": "library",
      "name": "form_urlencoded",
      "version": "1.2.2",
      "purl": "pkg:cargo/form_urlencoded@1.2.2",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "form_urlencoded@1.2.2"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/fraction@0.15.4",
      "type": "library",
      "name": "fraction",
      "version": "0.15.4",
      "purl": "pkg:cargo/fraction@0.15.4",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "fraction@0.15.4"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/futures-channel@0.3.34",
      "type": "library",
      "name": "futures-channel",
      "version": "0.3.34",
      "purl": "pkg:cargo/futures-channel@0.3.34",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "futures-channel@0.3.34"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/futures-core@0.3.34",
      "type": "library",
      "name": "futures-core",
      "version": "0.3.34",
      "purl": "pkg:cargo/futures-core@0.3.34",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "futures-core@0.3.34"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/futures-executor@0.3.34",
      "type": "library",
      "name": "futures-executor",
      "version": "0.3.34",
      "purl": "pkg:cargo/futures-executor@0.3.34",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "futures-executor@0.3.34"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/futures-io@0.3.34",
      "type": "library",
      "name": "futures-io",
      "version": "0.3.34",
      "purl": "pkg:cargo/futures-io@0.3.34",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "futures-io@0.3.34"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/futures-sink@0.3.34",
      "type": "library",
      "name": "futures-sink",
      "version": "0.3.34",
      "purl": "pkg:cargo/futures-sink@0.3.34",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "futures-sink@0.3.34"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/futures-task@0.3.34",
      "type": "library",
      "name": "futures-task",
      "version": "0.3.34",
      "purl": "pkg:cargo/futures-task@0.3.34",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "futures-task@0.3.34"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/futures-util@0.3.34",
      "type": "library",
      "name": "futures-util",
      "version": "0.3.34",
      "purl": "pkg:cargo/futures-util@0.3.34",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "futures-util@0.3.34"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/futures@0.3.34",
      "type": "library",
      "name": "futures",
      "version": "0.3.34",
      "purl": "pkg:cargo/futures@0.3.34",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "futures@0.3.34"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/generic-array@0.14.9",
      "type": "library",
      "name": "generic-array",
      "version": "0.14.9",
      "purl": "pkg:cargo/generic-array@0.14.9",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "generic-array@0.14.9"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/getrandom@0.2.17",
      "type": "library",
      "name": "getrandom",
      "version": "0.2.17",
      "purl": "pkg:cargo/getrandom@0.2.17",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "getrandom@0.2.17"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/getrandom@0.3.4",
      "type": "library",
      "name": "getrandom",
      "version": "0.3.4",
      "purl": "pkg:cargo/getrandom@0.3.4",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "getrandom@0.3.4"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/getrandom@0.4.3",
      "type": "library",
      "name": "getrandom",
      "version": "0.4.3",
      "purl": "pkg:cargo/getrandom@0.4.3",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "getrandom@0.4.3"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/glob@0.3.4",
      "type": "library",
      "name": "glob",
      "version": "0.3.4",
      "purl": "pkg:cargo/glob@0.3.4",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "glob@0.3.4"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/globset@0.4.20",
      "type": "library",
      "name": "globset",
      "version": "0.4.20",
      "purl": "pkg:cargo/globset@0.4.20",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "globset@0.4.20"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/group@0.13.0",
      "type": "library",
      "name": "group",
      "version": "0.13.0",
      "purl": "pkg:cargo/group@0.13.0",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "group@0.13.0"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/h2@0.4.20",
      "type": "library",
      "name": "h2",
      "version": "0.4.20",
      "purl": "pkg:cargo/h2@0.4.20",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "h2@0.4.20"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/hashbrown@0.12.3",
      "type": "library",
      "name": "hashbrown",
      "version": "0.12.3",
      "purl": "pkg:cargo/hashbrown@0.12.3",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "hashbrown@0.12.3"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/hashbrown@0.17.1",
      "type": "library",
      "name": "hashbrown",
      "version": "0.17.1",
      "purl": "pkg:cargo/hashbrown@0.17.1",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "hashbrown@0.17.1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/hkdf@0.12.4",
      "type": "library",
      "name": "hkdf",
      "version": "0.12.4",
      "purl": "pkg:cargo/hkdf@0.12.4",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "hkdf@0.12.4"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/hmac@0.12.1",
      "type": "library",
      "name": "hmac",
      "version": "0.12.1",
      "purl": "pkg:cargo/hmac@0.12.1",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "hmac@0.12.1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/hostname@0.4.2",
      "type": "library",
      "name": "hostname",
      "version": "0.4.2",
      "purl": "pkg:cargo/hostname@0.4.2",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "hostname@0.4.2"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/http-body-util@0.1.5",
      "type": "library",
      "name": "http-body-util",
      "version": "0.1.5",
      "purl": "pkg:cargo/http-body-util@0.1.5",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "http-body-util@0.1.5"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/http-body@1.1.0",
      "type": "library",
      "name": "http-body",
      "version": "1.1.0",
      "purl": "pkg:cargo/http-body@1.1.0",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "http-body@1.1.0"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/http@1.5.0",
      "type": "library",
      "name": "http",
      "version": "1.5.0",
      "purl": "pkg:cargo/http@1.5.0",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "http@1.5.0"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/httparse@1.10.1",
      "type": "library",
      "name": "httparse",
      "version": "1.10.1",
      "purl": "pkg:cargo/httparse@1.10.1",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "httparse@1.10.1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/httpdate@1.0.3",
      "type": "library",
      "name": "httpdate",
      "version": "1.0.3",
      "purl": "pkg:cargo/httpdate@1.0.3",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "httpdate@1.0.3"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/hybrid-array@0.4.15",
      "type": "library",
      "name": "hybrid-array",
      "version": "0.4.15",
      "purl": "pkg:cargo/hybrid-array@0.4.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "hybrid-array@0.4.15"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/hyper-rustls@0.27.10",
      "type": "library",
      "name": "hyper-rustls",
      "version": "0.27.10",
      "purl": "pkg:cargo/hyper-rustls@0.27.10",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "hyper-rustls@0.27.10"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/hyper-timeout@0.5.2",
      "type": "library",
      "name": "hyper-timeout",
      "version": "0.5.2",
      "purl": "pkg:cargo/hyper-timeout@0.5.2",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "hyper-timeout@0.5.2"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/hyper-util@0.1.21",
      "type": "library",
      "name": "hyper-util",
      "version": "0.1.21",
      "purl": "pkg:cargo/hyper-util@0.1.21",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "hyper-util@0.1.21"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/hyper@1.12.0",
      "type": "library",
      "name": "hyper",
      "version": "1.12.0",
      "purl": "pkg:cargo/hyper@1.12.0",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "hyper@1.12.0"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/iana-time-zone@0.1.65",
      "type": "library",
      "name": "iana-time-zone",
      "version": "0.1.65",
      "purl": "pkg:cargo/iana-time-zone@0.1.65",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "iana-time-zone@0.1.65"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/icu_collections@2.3.0",
      "type": "library",
      "name": "icu_collections",
      "version": "2.3.0",
      "purl": "pkg:cargo/icu_collections@2.3.0",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "icu_collections@2.3.0"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/icu_locale_core@2.3.0",
      "type": "library",
      "name": "icu_locale_core",
      "version": "2.3.0",
      "purl": "pkg:cargo/icu_locale_core@2.3.0",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "icu_locale_core@2.3.0"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/icu_normalizer@2.3.0",
      "type": "library",
      "name": "icu_normalizer",
      "version": "2.3.0",
      "purl": "pkg:cargo/icu_normalizer@2.3.0",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "icu_normalizer@2.3.0"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/icu_normalizer_data@2.3.0",
      "type": "library",
      "name": "icu_normalizer_data",
      "version": "2.3.0",
      "purl": "pkg:cargo/icu_normalizer_data@2.3.0",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "icu_normalizer_data@2.3.0"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/icu_properties@2.3.0",
      "type": "library",
      "name": "icu_properties",
      "version": "2.3.0",
      "purl": "pkg:cargo/icu_properties@2.3.0",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "icu_properties@2.3.0"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/icu_properties_data@2.3.0",
      "type": "library",
      "name": "icu_properties_data",
      "version": "2.3.0",
      "purl": "pkg:cargo/icu_properties_data@2.3.0",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "icu_properties_data@2.3.0"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/icu_provider@2.3.1",
      "type": "library",
      "name": "icu_provider",
      "version": "2.3.1",
      "purl": "pkg:cargo/icu_provider@2.3.1",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "icu_provider@2.3.1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/idna@1.1.0",
      "type": "library",
      "name": "idna",
      "version": "1.1.0",
      "purl": "pkg:cargo/idna@1.1.0",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "idna@1.1.0"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/idna_adapter@1.2.2",
      "type": "library",
      "name": "idna_adapter",
      "version": "1.2.2",
      "purl": "pkg:cargo/idna_adapter@1.2.2",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "idna_adapter@1.2.2"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/indexmap@1.9.3",
      "type": "library",
      "name": "indexmap",
      "version": "1.9.3",
      "purl": "pkg:cargo/indexmap@1.9.3",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "indexmap@1.9.3"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/indexmap@2.14.2",
      "type": "library",
      "name": "indexmap",
      "version": "2.14.2",
      "purl": "pkg:cargo/indexmap@2.14.2",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "indexmap@2.14.2"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/inlinable_string@0.1.15",
      "type": "library",
      "name": "inlinable_string",
      "version": "0.1.15",
      "purl": "pkg:cargo/inlinable_string@0.1.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "inlinable_string@0.1.15"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/inotify-sys@0.1.8",
      "type": "library",
      "name": "inotify-sys",
      "version": "0.1.8",
      "purl": "pkg:cargo/inotify-sys@0.1.8",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "inotify-sys@0.1.8"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/inotify@0.11.5",
      "type": "library",
      "name": "inotify",
      "version": "0.11.5",
      "purl": "pkg:cargo/inotify@0.11.5",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "inotify@0.11.5"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/ipnet@2.12.2",
      "type": "library",
      "name": "ipnet",
      "version": "2.12.2",
      "purl": "pkg:cargo/ipnet@2.12.2",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "ipnet@2.12.2"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/itoa@1.0.18",
      "type": "library",
      "name": "itoa",
      "version": "1.0.18",
      "purl": "pkg:cargo/itoa@1.0.18",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "itoa@1.0.18"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/jsonschema@0.30.0",
      "type": "library",
      "name": "jsonschema",
      "version": "0.30.0",
      "purl": "pkg:cargo/jsonschema@0.30.0",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "jsonschema@0.30.0"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/jsonwebtoken@10.4.0",
      "type": "library",
      "name": "jsonwebtoken",
      "version": "10.4.0",
      "purl": "pkg:cargo/jsonwebtoken@10.4.0",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "jsonwebtoken@10.4.0"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/lazy_static@1.5.1",
      "type": "library",
      "name": "lazy_static",
      "version": "1.5.1",
      "purl": "pkg:cargo/lazy_static@1.5.1",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "lazy_static@1.5.1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/libc@0.2.191",
      "type": "library",
      "name": "libc",
      "version": "0.2.191",
      "purl": "pkg:cargo/libc@0.2.191",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libc@0.2.191"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/libm@0.2.16",
      "type": "library",
      "name": "libm",
      "version": "0.2.16",
      "purl": "pkg:cargo/libm@0.2.16",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libm@0.2.16"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/linux-raw-sys@0.12.1",
      "type": "library",
      "name": "linux-raw-sys",
      "version": "0.12.1",
      "purl": "pkg:cargo/linux-raw-sys@0.12.1",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "linux-raw-sys@0.12.1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/litemap@0.8.3",
      "type": "library",
      "name": "litemap",
      "version": "0.8.3",
      "purl": "pkg:cargo/litemap@0.8.3",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "litemap@0.8.3"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/lock_api@0.4.14",
      "type": "library",
      "name": "lock_api",
      "version": "0.4.14",
      "purl": "pkg:cargo/lock_api@0.4.14",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "lock_api@0.4.14"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/log@0.4.34",
      "type": "library",
      "name": "log",
      "version": "0.4.34",
      "purl": "pkg:cargo/log@0.4.34",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "log@0.4.34"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/lru-slab@0.1.3",
      "type": "library",
      "name": "lru-slab",
      "version": "0.1.3",
      "purl": "pkg:cargo/lru-slab@0.1.3",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "lru-slab@0.1.3"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/matchers@0.2.0",
      "type": "library",
      "name": "matchers",
      "version": "0.2.0",
      "purl": "pkg:cargo/matchers@0.2.0",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "matchers@0.2.0"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/matchit@0.7.3",
      "type": "library",
      "name": "matchit",
      "version": "0.7.3",
      "purl": "pkg:cargo/matchit@0.7.3",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "matchit@0.7.3"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/memchr@2.8.3",
      "type": "library",
      "name": "memchr",
      "version": "2.8.3",
      "purl": "pkg:cargo/memchr@2.8.3",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "memchr@2.8.3"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/mime@0.3.17",
      "type": "library",
      "name": "mime",
      "version": "0.3.17",
      "purl": "pkg:cargo/mime@0.3.17",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "mime@0.3.17"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/mio@1.2.4",
      "type": "library",
      "name": "mio",
      "version": "1.2.4",
      "purl": "pkg:cargo/mio@1.2.4",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "mio@1.2.4"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/moka@0.12.16",
      "type": "library",
      "name": "moka",
      "version": "0.12.16",
      "purl": "pkg:cargo/moka@0.12.16",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "moka@0.12.16"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/msvc_spectre_libs@0.1.3",
      "type": "library",
      "name": "msvc_spectre_libs",
      "version": "0.1.3",
      "purl": "pkg:cargo/msvc_spectre_libs@0.1.3",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "msvc_spectre_libs@0.1.3"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/notify-types@2.1.0",
      "type": "library",
      "name": "notify-types",
      "version": "2.1.0",
      "purl": "pkg:cargo/notify-types@2.1.0",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "notify-types@2.1.0"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/notify@8.2.0",
      "type": "library",
      "name": "notify",
      "version": "8.2.0",
      "purl": "pkg:cargo/notify@8.2.0",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "notify@8.2.0"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/nu-ansi-term@0.50.3",
      "type": "library",
      "name": "nu-ansi-term",
      "version": "0.50.3",
      "purl": "pkg:cargo/nu-ansi-term@0.50.3",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "nu-ansi-term@0.50.3"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/num-bigint-dig@0.8.6",
      "type": "library",
      "name": "num-bigint-dig",
      "version": "0.8.6",
      "purl": "pkg:cargo/num-bigint-dig@0.8.6",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "num-bigint-dig@0.8.6"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/num-bigint@0.4.8",
      "type": "library",
      "name": "num-bigint",
      "version": "0.4.8",
      "purl": "pkg:cargo/num-bigint@0.4.8",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "num-bigint@0.4.8"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/num-cmp@0.1.0",
      "type": "library",
      "name": "num-cmp",
      "version": "0.1.0",
      "purl": "pkg:cargo/num-cmp@0.1.0",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "num-cmp@0.1.0"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/num-complex@0.4.6",
      "type": "library",
      "name": "num-complex",
      "version": "0.4.6",
      "purl": "pkg:cargo/num-complex@0.4.6",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "num-complex@0.4.6"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/num-conv@0.2.2",
      "type": "library",
      "name": "num-conv",
      "version": "0.2.2",
      "purl": "pkg:cargo/num-conv@0.2.2",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "num-conv@0.2.2"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/num-integer@0.1.47",
      "type": "library",
      "name": "num-integer",
      "version": "0.1.47",
      "purl": "pkg:cargo/num-integer@0.1.47",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "num-integer@0.1.47"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/num-iter@0.1.46",
      "type": "library",
      "name": "num-iter",
      "version": "0.1.46",
      "purl": "pkg:cargo/num-iter@0.1.46",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "num-iter@0.1.46"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/num-rational@0.4.2",
      "type": "library",
      "name": "num-rational",
      "version": "0.4.2",
      "purl": "pkg:cargo/num-rational@0.4.2",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "num-rational@0.4.2"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/num-traits@0.2.19",
      "type": "library",
      "name": "num-traits",
      "version": "0.2.19",
      "purl": "pkg:cargo/num-traits@0.2.19",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "num-traits@0.2.19"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/num@0.4.3",
      "type": "library",
      "name": "num",
      "version": "0.4.3",
      "purl": "pkg:cargo/num@0.4.3",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "num@0.4.3"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/once_cell@1.21.4",
      "type": "library",
      "name": "once_cell",
      "version": "1.21.4",
      "purl": "pkg:cargo/once_cell@1.21.4",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "once_cell@1.21.4"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/opentelemetry-otlp@0.27.0",
      "type": "library",
      "name": "opentelemetry-otlp",
      "version": "0.27.0",
      "purl": "pkg:cargo/opentelemetry-otlp@0.27.0",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "opentelemetry-otlp@0.27.0"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/opentelemetry-proto@0.27.0",
      "type": "library",
      "name": "opentelemetry-proto",
      "version": "0.27.0",
      "purl": "pkg:cargo/opentelemetry-proto@0.27.0",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "opentelemetry-proto@0.27.0"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/opentelemetry@0.27.1",
      "type": "library",
      "name": "opentelemetry",
      "version": "0.27.1",
      "purl": "pkg:cargo/opentelemetry@0.27.1",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "opentelemetry@0.27.1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/opentelemetry_sdk@0.27.1",
      "type": "library",
      "name": "opentelemetry_sdk",
      "version": "0.27.1",
      "purl": "pkg:cargo/opentelemetry_sdk@0.27.1",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "opentelemetry_sdk@0.27.1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/outref@0.5.2",
      "type": "library",
      "name": "outref",
      "version": "0.5.2",
      "purl": "pkg:cargo/outref@0.5.2",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "outref@0.5.2"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/p256@0.13.2",
      "type": "library",
      "name": "p256",
      "version": "0.13.2",
      "purl": "pkg:cargo/p256@0.13.2",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "p256@0.13.2"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/p384@0.13.1",
      "type": "library",
      "name": "p384",
      "version": "0.13.1",
      "purl": "pkg:cargo/p384@0.13.1",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "p384@0.13.1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/parking@2.2.1",
      "type": "library",
      "name": "parking",
      "version": "2.2.1",
      "purl": "pkg:cargo/parking@2.2.1",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "parking@2.2.1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/parking_lot@0.12.5",
      "type": "library",
      "name": "parking_lot",
      "version": "0.12.5",
      "purl": "pkg:cargo/parking_lot@0.12.5",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "parking_lot@0.12.5"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/parking_lot_core@0.9.12",
      "type": "library",
      "name": "parking_lot_core",
      "version": "0.9.12",
      "purl": "pkg:cargo/parking_lot_core@0.9.12",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "parking_lot_core@0.9.12"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/pear@0.2.9",
      "type": "library",
      "name": "pear",
      "version": "0.2.9",
      "purl": "pkg:cargo/pear@0.2.9",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "pear@0.2.9"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/pem-rfc7468@0.7.0",
      "type": "library",
      "name": "pem-rfc7468",
      "version": "0.7.0",
      "purl": "pkg:cargo/pem-rfc7468@0.7.0",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "pem-rfc7468@0.7.0"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/pem@3.0.6",
      "type": "library",
      "name": "pem",
      "version": "3.0.6",
      "purl": "pkg:cargo/pem@3.0.6",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "pem@3.0.6"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/percent-encoding@2.3.2",
      "type": "library",
      "name": "percent-encoding",
      "version": "2.3.2",
      "purl": "pkg:cargo/percent-encoding@2.3.2",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "percent-encoding@2.3.2"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/phf@0.12.1",
      "type": "library",
      "name": "phf",
      "version": "0.12.1",
      "purl": "pkg:cargo/phf@0.12.1",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "phf@0.12.1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/phf_shared@0.12.1",
      "type": "library",
      "name": "phf_shared",
      "version": "0.12.1",
      "purl": "pkg:cargo/phf_shared@0.12.1",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "phf_shared@0.12.1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/pin-project-lite@0.2.17",
      "type": "library",
      "name": "pin-project-lite",
      "version": "0.2.17",
      "purl": "pkg:cargo/pin-project-lite@0.2.17",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "pin-project-lite@0.2.17"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/pin-project@1.1.13",
      "type": "library",
      "name": "pin-project",
      "version": "1.1.13",
      "purl": "pkg:cargo/pin-project@1.1.13",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "pin-project@1.1.13"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/pkcs1@0.7.5",
      "type": "library",
      "name": "pkcs1",
      "version": "0.7.5",
      "purl": "pkg:cargo/pkcs1@0.7.5",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "pkcs1@0.7.5"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/pkcs8@0.10.2",
      "type": "library",
      "name": "pkcs8",
      "version": "0.10.2",
      "purl": "pkg:cargo/pkcs8@0.10.2",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "pkcs8@0.10.2"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/portable-atomic@1.15.0",
      "type": "library",
      "name": "portable-atomic",
      "version": "1.15.0",
      "purl": "pkg:cargo/portable-atomic@1.15.0",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "portable-atomic@1.15.0"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/potential_utf@0.1.6",
      "type": "library",
      "name": "potential_utf",
      "version": "0.1.6",
      "purl": "pkg:cargo/potential_utf@0.1.6",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "potential_utf@0.1.6"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/powerfmt@0.2.1",
      "type": "library",
      "name": "powerfmt",
      "version": "0.2.1",
      "purl": "pkg:cargo/powerfmt@0.2.1",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "powerfmt@0.2.1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/ppv-lite86@0.2.21",
      "type": "library",
      "name": "ppv-lite86",
      "version": "0.2.21",
      "purl": "pkg:cargo/ppv-lite86@0.2.21",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "ppv-lite86@0.2.21"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/primeorder@0.13.6",
      "type": "library",
      "name": "primeorder",
      "version": "0.13.6",
      "purl": "pkg:cargo/primeorder@0.13.6",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "primeorder@0.13.6"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/proc-macro2@1.0.107",
      "type": "library",
      "name": "proc-macro2",
      "version": "1.0.107",
      "purl": "pkg:cargo/proc-macro2@1.0.107",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "proc-macro2@1.0.107"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/prometheus@0.13.4",
      "type": "library",
      "name": "prometheus",
      "version": "0.13.4",
      "purl": "pkg:cargo/prometheus@0.13.4",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "prometheus@0.13.4"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/prost@0.13.5",
      "type": "library",
      "name": "prost",
      "version": "0.13.5",
      "purl": "pkg:cargo/prost@0.13.5",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "prost@0.13.5"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/quick-xml@0.39.4",
      "type": "library",
      "name": "quick-xml",
      "version": "0.39.4",
      "purl": "pkg:cargo/quick-xml@0.39.4",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "quick-xml@0.39.4"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/quinn-proto@0.11.19",
      "type": "library",
      "name": "quinn-proto",
      "version": "0.11.19",
      "purl": "pkg:cargo/quinn-proto@0.11.19",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "quinn-proto@0.11.19"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/quinn-udp@0.5.16",
      "type": "library",
      "name": "quinn-udp",
      "version": "0.5.16",
      "purl": "pkg:cargo/quinn-udp@0.5.16",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "quinn-udp@0.5.16"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/quinn@0.11.12",
      "type": "library",
      "name": "quinn",
      "version": "0.11.12",
      "purl": "pkg:cargo/quinn@0.11.12",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "quinn@0.11.12"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/quote@1.0.47",
      "type": "library",
      "name": "quote",
      "version": "1.0.47",
      "purl": "pkg:cargo/quote@1.0.47",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "quote@1.0.47"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/rand@0.10.3",
      "type": "library",
      "name": "rand",
      "version": "0.10.3",
      "purl": "pkg:cargo/rand@0.10.3",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "rand@0.10.3"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/rand@0.8.8",
      "type": "library",
      "name": "rand",
      "version": "0.8.8",
      "purl": "pkg:cargo/rand@0.8.8",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "rand@0.8.8"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/rand@0.9.5",
      "type": "library",
      "name": "rand",
      "version": "0.9.5",
      "purl": "pkg:cargo/rand@0.9.5",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "rand@0.9.5"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/rand_chacha@0.3.1",
      "type": "library",
      "name": "rand_chacha",
      "version": "0.3.1",
      "purl": "pkg:cargo/rand_chacha@0.3.1",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "rand_chacha@0.3.1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/rand_chacha@0.9.0",
      "type": "library",
      "name": "rand_chacha",
      "version": "0.9.0",
      "purl": "pkg:cargo/rand_chacha@0.9.0",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "rand_chacha@0.9.0"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/rand_core@0.10.1",
      "type": "library",
      "name": "rand_core",
      "version": "0.10.1",
      "purl": "pkg:cargo/rand_core@0.10.1",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "rand_core@0.10.1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/rand_core@0.6.4",
      "type": "library",
      "name": "rand_core",
      "version": "0.6.4",
      "purl": "pkg:cargo/rand_core@0.6.4",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "rand_core@0.6.4"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/rand_core@0.9.5",
      "type": "library",
      "name": "rand_core",
      "version": "0.9.5",
      "purl": "pkg:cargo/rand_core@0.9.5",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "rand_core@0.9.5"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/rand_pcg@0.10.2",
      "type": "library",
      "name": "rand_pcg",
      "version": "0.10.2",
      "purl": "pkg:cargo/rand_pcg@0.10.2",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "rand_pcg@0.10.2"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/ref-cast@1.0.27",
      "type": "library",
      "name": "ref-cast",
      "version": "1.0.27",
      "purl": "pkg:cargo/ref-cast@1.0.27",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "ref-cast@1.0.27"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/referencing@0.30.0",
      "type": "library",
      "name": "referencing",
      "version": "0.30.0",
      "purl": "pkg:cargo/referencing@0.30.0",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "referencing@0.30.0"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/regex-automata@0.4.18",
      "type": "library",
      "name": "regex-automata",
      "version": "0.4.18",
      "purl": "pkg:cargo/regex-automata@0.4.18",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "regex-automata@0.4.18"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/regex-syntax@0.8.11",
      "type": "library",
      "name": "regex-syntax",
      "version": "0.8.11",
      "purl": "pkg:cargo/regex-syntax@0.8.11",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "regex-syntax@0.8.11"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/regex@1.13.1",
      "type": "library",
      "name": "regex",
      "version": "1.13.1",
      "purl": "pkg:cargo/regex@1.13.1",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "regex@1.13.1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/regorus-mimalloc-sys@2.2.6",
      "type": "library",
      "name": "regorus-mimalloc-sys",
      "version": "2.2.6",
      "purl": "pkg:cargo/regorus-mimalloc-sys@2.2.6",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "regorus-mimalloc-sys@2.2.6"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/regorus-mimalloc@2.2.8",
      "type": "library",
      "name": "regorus-mimalloc",
      "version": "2.2.8",
      "purl": "pkg:cargo/regorus-mimalloc@2.2.8",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "regorus-mimalloc@2.2.8"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/regorus@0.9.1",
      "type": "library",
      "name": "regorus",
      "version": "0.9.1",
      "purl": "pkg:cargo/regorus@0.9.1",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "regorus@0.9.1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/reqwest@0.12.28",
      "type": "library",
      "name": "reqwest",
      "version": "0.12.28",
      "purl": "pkg:cargo/reqwest@0.12.28",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "reqwest@0.12.28"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/rfc6979@0.4.0",
      "type": "library",
      "name": "rfc6979",
      "version": "0.4.0",
      "purl": "pkg:cargo/rfc6979@0.4.0",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "rfc6979@0.4.0"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/ring@0.17.14",
      "type": "library",
      "name": "ring",
      "version": "0.17.14",
      "purl": "pkg:cargo/ring@0.17.14",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "ring@0.17.14"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/rsa@0.9.10",
      "type": "library",
      "name": "rsa",
      "version": "0.9.10",
      "purl": "pkg:cargo/rsa@0.9.10",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "rsa@0.9.10"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/rustc-hash@2.1.3",
      "type": "library",
      "name": "rustc-hash",
      "version": "2.1.3",
      "purl": "pkg:cargo/rustc-hash@2.1.3",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "rustc-hash@2.1.3"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/rustix@1.1.5",
      "type": "library",
      "name": "rustix",
      "version": "1.1.5",
      "purl": "pkg:cargo/rustix@1.1.5",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "rustix@1.1.5"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/rustls-pki-types@1.15.1",
      "type": "library",
      "name": "rustls-pki-types",
      "version": "1.15.1",
      "purl": "pkg:cargo/rustls-pki-types@1.15.1",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "rustls-pki-types@1.15.1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/rustls-webpki@0.103.16",
      "type": "library",
      "name": "rustls-webpki",
      "version": "0.103.16",
      "purl": "pkg:cargo/rustls-webpki@0.103.16",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "rustls-webpki@0.103.16"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/rustls@0.23.46",
      "type": "library",
      "name": "rustls",
      "version": "0.23.46",
      "purl": "pkg:cargo/rustls@0.23.46",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "rustls@0.23.46"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/rustversion@1.0.23",
      "type": "library",
      "name": "rustversion",
      "version": "1.0.23",
      "purl": "pkg:cargo/rustversion@1.0.23",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "rustversion@1.0.23"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/ryu@1.0.23",
      "type": "library",
      "name": "ryu",
      "version": "1.0.23",
      "purl": "pkg:cargo/ryu@1.0.23",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "ryu@1.0.23"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/same-file@1.0.6",
      "type": "library",
      "name": "same-file",
      "version": "1.0.6",
      "purl": "pkg:cargo/same-file@1.0.6",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "same-file@1.0.6"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/scopeguard@1.2.0",
      "type": "library",
      "name": "scopeguard",
      "version": "1.2.0",
      "purl": "pkg:cargo/scopeguard@1.2.0",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "scopeguard@1.2.0"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/sec1@0.7.3",
      "type": "library",
      "name": "sec1",
      "version": "0.7.3",
      "purl": "pkg:cargo/sec1@0.7.3",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "sec1@0.7.3"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/semver@1.0.28",
      "type": "library",
      "name": "semver",
      "version": "1.0.28",
      "purl": "pkg:cargo/semver@1.0.28",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "semver@1.0.28"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/serde@1.0.229",
      "type": "library",
      "name": "serde",
      "version": "1.0.229",
      "purl": "pkg:cargo/serde@1.0.229",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "serde@1.0.229"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/serde_core@1.0.229",
      "type": "library",
      "name": "serde_core",
      "version": "1.0.229",
      "purl": "pkg:cargo/serde_core@1.0.229",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "serde_core@1.0.229"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/serde_json@1.0.154",
      "type": "library",
      "name": "serde_json",
      "version": "1.0.154",
      "purl": "pkg:cargo/serde_json@1.0.154",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "serde_json@1.0.154"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/serde_path_to_error@0.1.20",
      "type": "library",
      "name": "serde_path_to_error",
      "version": "0.1.20",
      "purl": "pkg:cargo/serde_path_to_error@0.1.20",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "serde_path_to_error@0.1.20"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/serde_spanned@1.1.2",
      "type": "library",
      "name": "serde_spanned",
      "version": "1.1.2",
      "purl": "pkg:cargo/serde_spanned@1.1.2",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "serde_spanned@1.1.2"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/serde_urlencoded@0.7.1",
      "type": "library",
      "name": "serde_urlencoded",
      "version": "0.7.1",
      "purl": "pkg:cargo/serde_urlencoded@0.7.1",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "serde_urlencoded@0.7.1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/serde_yaml@0.9.34%2Bdeprecated",
      "type": "library",
      "name": "serde_yaml",
      "version": "0.9.34+deprecated",
      "purl": "pkg:cargo/serde_yaml@0.9.34%2Bdeprecated",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "serde_yaml@0.9.34+deprecated"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/sha1@0.10.7",
      "type": "library",
      "name": "sha1",
      "version": "0.10.7",
      "purl": "pkg:cargo/sha1@0.10.7",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "sha1@0.10.7"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/sha2@0.10.9",
      "type": "library",
      "name": "sha2",
      "version": "0.10.9",
      "purl": "pkg:cargo/sha2@0.10.9",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "sha2@0.10.9"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/sha2@0.11.1",
      "type": "library",
      "name": "sha2",
      "version": "0.11.1",
      "purl": "pkg:cargo/sha2@0.11.1",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "sha2@0.11.1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/sharded-slab@0.1.7",
      "type": "library",
      "name": "sharded-slab",
      "version": "0.1.7",
      "purl": "pkg:cargo/sharded-slab@0.1.7",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "sharded-slab@0.1.7"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/signal-hook-registry@1.4.8",
      "type": "library",
      "name": "signal-hook-registry",
      "version": "1.4.8",
      "purl": "pkg:cargo/signal-hook-registry@1.4.8",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "signal-hook-registry@1.4.8"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/signature@2.2.0",
      "type": "library",
      "name": "signature",
      "version": "2.2.0",
      "purl": "pkg:cargo/signature@2.2.0",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "signature@2.2.0"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/simple_asn1@0.6.4",
      "type": "library",
      "name": "simple_asn1",
      "version": "0.6.4",
      "purl": "pkg:cargo/simple_asn1@0.6.4",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "simple_asn1@0.6.4"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/siphasher@1.0.4",
      "type": "library",
      "name": "siphasher",
      "version": "1.0.4",
      "purl": "pkg:cargo/siphasher@1.0.4",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "siphasher@1.0.4"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/slab@0.4.12",
      "type": "library",
      "name": "slab",
      "version": "0.4.12",
      "purl": "pkg:cargo/slab@0.4.12",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "slab@0.4.12"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/smallvec@1.16.3",
      "type": "library",
      "name": "smallvec",
      "version": "1.16.3",
      "purl": "pkg:cargo/smallvec@1.16.3",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "smallvec@1.16.3"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/socket2@0.5.10",
      "type": "library",
      "name": "socket2",
      "version": "0.5.10",
      "purl": "pkg:cargo/socket2@0.5.10",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "socket2@0.5.10"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/socket2@0.6.5",
      "type": "library",
      "name": "socket2",
      "version": "0.6.5",
      "purl": "pkg:cargo/socket2@0.6.5",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "socket2@0.6.5"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/spin@0.9.9",
      "type": "library",
      "name": "spin",
      "version": "0.9.9",
      "purl": "pkg:cargo/spin@0.9.9",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "spin@0.9.9"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/spki@0.7.3",
      "type": "library",
      "name": "spki",
      "version": "0.7.3",
      "purl": "pkg:cargo/spki@0.7.3",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "spki@0.7.3"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/stable_deref_trait@1.2.1",
      "type": "library",
      "name": "stable_deref_trait",
      "version": "1.2.1",
      "purl": "pkg:cargo/stable_deref_trait@1.2.1",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "stable_deref_trait@1.2.1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/stoa-gateway@0.9.25",
      "type": "library",
      "name": "stoa-gateway",
      "version": "0.9.25",
      "purl": "pkg:cargo/stoa-gateway@0.9.25",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "stoa-gateway@0.9.25"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/subtle@2.6.1",
      "type": "library",
      "name": "subtle",
      "version": "2.6.1",
      "purl": "pkg:cargo/subtle@2.6.1",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "subtle@2.6.1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/syn@2.0.119",
      "type": "library",
      "name": "syn",
      "version": "2.0.119",
      "purl": "pkg:cargo/syn@2.0.119",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "syn@2.0.119"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/syn@3.0.9",
      "type": "library",
      "name": "syn",
      "version": "3.0.9",
      "purl": "pkg:cargo/syn@3.0.9",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "syn@3.0.9"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/sync_wrapper@1.0.2",
      "type": "library",
      "name": "sync_wrapper",
      "version": "1.0.2",
      "purl": "pkg:cargo/sync_wrapper@1.0.2",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "sync_wrapper@1.0.2"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/synstructure@0.14.0",
      "type": "library",
      "name": "synstructure",
      "version": "0.14.0",
      "purl": "pkg:cargo/synstructure@0.14.0",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "synstructure@0.14.0"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/tagptr@0.2.0",
      "type": "library",
      "name": "tagptr",
      "version": "0.2.0",
      "purl": "pkg:cargo/tagptr@0.2.0",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "tagptr@0.2.0"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/tempfile@3.27.0",
      "type": "library",
      "name": "tempfile",
      "version": "3.27.0",
      "purl": "pkg:cargo/tempfile@3.27.0",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "tempfile@3.27.0"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/thiserror@1.0.69",
      "type": "library",
      "name": "thiserror",
      "version": "1.0.69",
      "purl": "pkg:cargo/thiserror@1.0.69",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "thiserror@1.0.69"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/thiserror@2.0.21",
      "type": "library",
      "name": "thiserror",
      "version": "2.0.21",
      "purl": "pkg:cargo/thiserror@2.0.21",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "thiserror@2.0.21"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/thread_local@1.1.10",
      "type": "library",
      "name": "thread_local",
      "version": "1.1.10",
      "purl": "pkg:cargo/thread_local@1.1.10",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "thread_local@1.1.10"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/time-core@0.1.9",
      "type": "library",
      "name": "time-core",
      "version": "0.1.9",
      "purl": "pkg:cargo/time-core@0.1.9",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "time-core@0.1.9"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/time@0.3.55",
      "type": "library",
      "name": "time",
      "version": "0.3.55",
      "purl": "pkg:cargo/time@0.3.55",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "time@0.3.55"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/tinystr@0.8.4",
      "type": "library",
      "name": "tinystr",
      "version": "0.8.4",
      "purl": "pkg:cargo/tinystr@0.8.4",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "tinystr@0.8.4"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/tinyvec@1.13.3",
      "type": "library",
      "name": "tinyvec",
      "version": "1.13.3",
      "purl": "pkg:cargo/tinyvec@1.13.3",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "tinyvec@1.13.3"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/tokio-rustls@0.26.6",
      "type": "library",
      "name": "tokio-rustls",
      "version": "0.26.6",
      "purl": "pkg:cargo/tokio-rustls@0.26.6",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "tokio-rustls@0.26.6"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/tokio-stream@0.1.19",
      "type": "library",
      "name": "tokio-stream",
      "version": "0.1.19",
      "purl": "pkg:cargo/tokio-stream@0.1.19",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "tokio-stream@0.1.19"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/tokio-tungstenite@0.24.0",
      "type": "library",
      "name": "tokio-tungstenite",
      "version": "0.24.0",
      "purl": "pkg:cargo/tokio-tungstenite@0.24.0",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "tokio-tungstenite@0.24.0"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/tokio-tungstenite@0.29.0",
      "type": "library",
      "name": "tokio-tungstenite",
      "version": "0.29.0",
      "purl": "pkg:cargo/tokio-tungstenite@0.29.0",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "tokio-tungstenite@0.29.0"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/tokio-util@0.7.20",
      "type": "library",
      "name": "tokio-util",
      "version": "0.7.20",
      "purl": "pkg:cargo/tokio-util@0.7.20",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "tokio-util@0.7.20"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/tokio@1.54.0",
      "type": "library",
      "name": "tokio",
      "version": "1.54.0",
      "purl": "pkg:cargo/tokio@1.54.0",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "tokio@1.54.0"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/toml@1.1.8%2Bspec-1.1.0",
      "type": "library",
      "name": "toml",
      "version": "1.1.8+spec-1.1.0",
      "purl": "pkg:cargo/toml@1.1.8%2Bspec-1.1.0",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "toml@1.1.8+spec-1.1.0"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/toml_datetime@1.1.2%2Bspec-1.1.0",
      "type": "library",
      "name": "toml_datetime",
      "version": "1.1.2+spec-1.1.0",
      "purl": "pkg:cargo/toml_datetime@1.1.2%2Bspec-1.1.0",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "toml_datetime@1.1.2+spec-1.1.0"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/toml_parser@1.1.5%2Bspec-1.1.0",
      "type": "library",
      "name": "toml_parser",
      "version": "1.1.5+spec-1.1.0",
      "purl": "pkg:cargo/toml_parser@1.1.5%2Bspec-1.1.0",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "toml_parser@1.1.5+spec-1.1.0"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/toml_writer@1.1.3%2Bspec-1.1.0",
      "type": "library",
      "name": "toml_writer",
      "version": "1.1.3+spec-1.1.0",
      "purl": "pkg:cargo/toml_writer@1.1.3%2Bspec-1.1.0",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "toml_writer@1.1.3+spec-1.1.0"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/tonic@0.12.3",
      "type": "library",
      "name": "tonic",
      "version": "0.12.3",
      "purl": "pkg:cargo/tonic@0.12.3",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "tonic@0.12.3"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/tower-http@0.6.11",
      "type": "library",
      "name": "tower-http",
      "version": "0.6.11",
      "purl": "pkg:cargo/tower-http@0.6.11",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "tower-http@0.6.11"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/tower-layer@0.3.3",
      "type": "library",
      "name": "tower-layer",
      "version": "0.3.3",
      "purl": "pkg:cargo/tower-layer@0.3.3",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "tower-layer@0.3.3"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/tower-service@0.3.3",
      "type": "library",
      "name": "tower-service",
      "version": "0.3.3",
      "purl": "pkg:cargo/tower-service@0.3.3",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "tower-service@0.3.3"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/tower@0.4.13",
      "type": "library",
      "name": "tower",
      "version": "0.4.13",
      "purl": "pkg:cargo/tower@0.4.13",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "tower@0.4.13"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/tower@0.5.3",
      "type": "library",
      "name": "tower",
      "version": "0.5.3",
      "purl": "pkg:cargo/tower@0.5.3",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "tower@0.5.3"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/tracing-attributes@0.1.31",
      "type": "library",
      "name": "tracing-attributes",
      "version": "0.1.31",
      "purl": "pkg:cargo/tracing-attributes@0.1.31",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "tracing-attributes@0.1.31"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/tracing-core@0.1.36",
      "type": "library",
      "name": "tracing-core",
      "version": "0.1.36",
      "purl": "pkg:cargo/tracing-core@0.1.36",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "tracing-core@0.1.36"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/tracing-log@0.2.0",
      "type": "library",
      "name": "tracing-log",
      "version": "0.2.0",
      "purl": "pkg:cargo/tracing-log@0.2.0",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "tracing-log@0.2.0"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/tracing-opentelemetry@0.28.0",
      "type": "library",
      "name": "tracing-opentelemetry",
      "version": "0.28.0",
      "purl": "pkg:cargo/tracing-opentelemetry@0.28.0",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "tracing-opentelemetry@0.28.0"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/tracing-serde@0.2.0",
      "type": "library",
      "name": "tracing-serde",
      "version": "0.2.0",
      "purl": "pkg:cargo/tracing-serde@0.2.0",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "tracing-serde@0.2.0"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/tracing-subscriber@0.3.23",
      "type": "library",
      "name": "tracing-subscriber",
      "version": "0.3.23",
      "purl": "pkg:cargo/tracing-subscriber@0.3.23",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "tracing-subscriber@0.3.23"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/tracing@0.1.44",
      "type": "library",
      "name": "tracing",
      "version": "0.1.44",
      "purl": "pkg:cargo/tracing@0.1.44",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "tracing@0.1.44"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/try-lock@0.2.5",
      "type": "library",
      "name": "try-lock",
      "version": "0.2.5",
      "purl": "pkg:cargo/try-lock@0.2.5",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "try-lock@0.2.5"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/tungstenite@0.24.0",
      "type": "library",
      "name": "tungstenite",
      "version": "0.24.0",
      "purl": "pkg:cargo/tungstenite@0.24.0",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "tungstenite@0.24.0"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/tungstenite@0.29.0",
      "type": "library",
      "name": "tungstenite",
      "version": "0.29.0",
      "purl": "pkg:cargo/tungstenite@0.29.0",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "tungstenite@0.29.0"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/typenum@1.20.1",
      "type": "library",
      "name": "typenum",
      "version": "1.20.1",
      "purl": "pkg:cargo/typenum@1.20.1",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "typenum@1.20.1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/uncased@0.9.10",
      "type": "library",
      "name": "uncased",
      "version": "0.9.10",
      "purl": "pkg:cargo/uncased@0.9.10",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "uncased@0.9.10"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/unicode-ident@1.0.27",
      "type": "library",
      "name": "unicode-ident",
      "version": "1.0.27",
      "purl": "pkg:cargo/unicode-ident@1.0.27",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "unicode-ident@1.0.27"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/unsafe-libyaml@0.2.11",
      "type": "library",
      "name": "unsafe-libyaml",
      "version": "0.2.11",
      "purl": "pkg:cargo/unsafe-libyaml@0.2.11",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "unsafe-libyaml@0.2.11"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/untrusted@0.9.0",
      "type": "library",
      "name": "untrusted",
      "version": "0.9.0",
      "purl": "pkg:cargo/untrusted@0.9.0",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "untrusted@0.9.0"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/unty@0.0.4",
      "type": "library",
      "name": "unty",
      "version": "0.0.4",
      "purl": "pkg:cargo/unty@0.0.4",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "unty@0.0.4"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/url@2.5.8",
      "type": "library",
      "name": "url",
      "version": "2.5.8",
      "purl": "pkg:cargo/url@2.5.8",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "url@2.5.8"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/urlencoding@2.1.3",
      "type": "library",
      "name": "urlencoding",
      "version": "2.1.3",
      "purl": "pkg:cargo/urlencoding@2.1.3",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "urlencoding@2.1.3"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/utf-8@0.7.6",
      "type": "library",
      "name": "utf-8",
      "version": "0.7.6",
      "purl": "pkg:cargo/utf-8@0.7.6",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "utf-8@0.7.6"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/utf8_iter@1.0.4",
      "type": "library",
      "name": "utf8_iter",
      "version": "1.0.4",
      "purl": "pkg:cargo/utf8_iter@1.0.4",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "utf8_iter@1.0.4"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/uuid-simd@0.8.0",
      "type": "library",
      "name": "uuid-simd",
      "version": "0.8.0",
      "purl": "pkg:cargo/uuid-simd@0.8.0",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "uuid-simd@0.8.0"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/uuid@1.28.0",
      "type": "library",
      "name": "uuid",
      "version": "1.28.0",
      "purl": "pkg:cargo/uuid@1.28.0",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "uuid@1.28.0"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/vsimd@0.8.0",
      "type": "library",
      "name": "vsimd",
      "version": "0.8.0",
      "purl": "pkg:cargo/vsimd@0.8.0",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "vsimd@0.8.0"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/walkdir@2.5.0",
      "type": "library",
      "name": "walkdir",
      "version": "2.5.0",
      "purl": "pkg:cargo/walkdir@2.5.0",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "walkdir@2.5.0"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/want@0.3.2",
      "type": "library",
      "name": "want",
      "version": "0.3.2",
      "purl": "pkg:cargo/want@0.3.2",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "want@0.3.2"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/webpki-roots@0.26.11",
      "type": "library",
      "name": "webpki-roots",
      "version": "0.26.11",
      "purl": "pkg:cargo/webpki-roots@0.26.11",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "webpki-roots@0.26.11"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/webpki-roots@1.0.10",
      "type": "library",
      "name": "webpki-roots",
      "version": "1.0.10",
      "purl": "pkg:cargo/webpki-roots@1.0.10",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "webpki-roots@1.0.10"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/winnow@1.0.4",
      "type": "library",
      "name": "winnow",
      "version": "1.0.4",
      "purl": "pkg:cargo/winnow@1.0.4",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "winnow@1.0.4"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/writeable@0.6.4",
      "type": "library",
      "name": "writeable",
      "version": "0.6.4",
      "purl": "pkg:cargo/writeable@0.6.4",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "writeable@0.6.4"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/yansi@1.0.1",
      "type": "library",
      "name": "yansi",
      "version": "1.0.1",
      "purl": "pkg:cargo/yansi@1.0.1",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "yansi@1.0.1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/yoke-derive@0.8.4",
      "type": "library",
      "name": "yoke-derive",
      "version": "0.8.4",
      "purl": "pkg:cargo/yoke-derive@0.8.4",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "yoke-derive@0.8.4"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/yoke@0.8.3",
      "type": "library",
      "name": "yoke",
      "version": "0.8.3",
      "purl": "pkg:cargo/yoke@0.8.3",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "yoke@0.8.3"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/zerocopy-derive@0.8.63",
      "type": "library",
      "name": "zerocopy-derive",
      "version": "0.8.63",
      "purl": "pkg:cargo/zerocopy-derive@0.8.63",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "zerocopy-derive@0.8.63"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/zerocopy@0.8.63",
      "type": "library",
      "name": "zerocopy",
      "version": "0.8.63",
      "purl": "pkg:cargo/zerocopy@0.8.63",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "zerocopy@0.8.63"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/zerofrom-derive@0.1.8",
      "type": "library",
      "name": "zerofrom-derive",
      "version": "0.1.8",
      "purl": "pkg:cargo/zerofrom-derive@0.1.8",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "zerofrom-derive@0.1.8"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/zerofrom@0.1.8",
      "type": "library",
      "name": "zerofrom",
      "version": "0.1.8",
      "purl": "pkg:cargo/zerofrom@0.1.8",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "zerofrom@0.1.8"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/zeroize@1.9.1",
      "type": "library",
      "name": "zeroize",
      "version": "1.9.1",
      "purl": "pkg:cargo/zeroize@1.9.1",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "zeroize@1.9.1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/zerotrie@0.2.5",
      "type": "library",
      "name": "zerotrie",
      "version": "0.2.5",
      "purl": "pkg:cargo/zerotrie@0.2.5",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "zerotrie@0.2.5"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/zerovec-derive@0.11.6",
      "type": "library",
      "name": "zerovec-derive",
      "version": "0.11.6",
      "purl": "pkg:cargo/zerovec-derive@0.11.6",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "zerovec-derive@0.11.6"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/zerovec@0.11.8",
      "type": "library",
      "name": "zerovec",
      "version": "0.11.8",
      "purl": "pkg:cargo/zerovec@0.11.8",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "zerovec@0.11.8"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:cargo/zmij@1.0.23",
      "type": "library",
      "name": "zmij",
      "version": "1.0.23",
      "purl": "pkg:cargo/zmij@1.0.23",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:f11a4257786d76ad270246b9364e00f68fb05bc543b14e095dac350165e7c09b"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:893fa4389f6aff885192feef2a152b5190d0eb8e9b70858b68cfd48023743088"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "zmij@1.0.23"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "rustbinary"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/adduser@3.134?arch=all&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Debian Adduser Developers <adduser@packages.debian.org>"
      },
      "name": "adduser",
      "version": "3.134",
      "licenses": [
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/adduser@3.134?arch=all&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "adduser@3.134"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "adduser"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "3.134"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/apt@2.6.1?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "APT Development Team <deity@lists.debian.org>"
      },
      "name": "apt",
      "version": "2.6.1",
      "licenses": [
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "BSD-3-Clause"
          }
        },
        {
          "license": {
            "name": "MIT"
          }
        }
      ],
      "purl": "pkg:deb/debian/apt@2.6.1?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "apt@2.6.1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "apt"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "2.6.1"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/base-files@12.4%2Bdeb12u15?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Santiago Vila <sanvila@debian.org>"
      },
      "name": "base-files",
      "version": "12.4+deb12u15",
      "licenses": [
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        }
      ],
      "purl": "pkg:deb/debian/base-files@12.4%2Bdeb12u15?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "base-files@12.4+deb12u15"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "base-files"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "12.4+deb12u15"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/base-passwd@3.6.1?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Colin Watson <cjwatson@debian.org>"
      },
      "name": "base-passwd",
      "version": "3.6.1",
      "licenses": [
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "public-domain"
          }
        }
      ],
      "purl": "pkg:deb/debian/base-passwd@3.6.1?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "base-passwd@3.6.1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "base-passwd"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "3.6.1"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/bash@5.2.15-2%2Bb13?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Matthias Klose <doko@debian.org>"
      },
      "name": "bash",
      "version": "5.2.15-2+b13",
      "licenses": [
        {
          "license": {
            "name": "GPL-3.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-only"
          }
        },
        {
          "license": {
            "name": "GPL-3+ with Bison exception"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "GFDL-1.3-no-invariants-only"
          }
        },
        {
          "license": {
            "name": "GFDL-1.3-only"
          }
        },
        {
          "license": {
            "name": "Latex2e"
          }
        },
        {
          "license": {
            "name": "BSD-4-Clause-UC"
          }
        },
        {
          "license": {
            "name": "MIT"
          }
        },
        {
          "license": {
            "name": "permissive"
          }
        }
      ],
      "purl": "pkg:deb/debian/bash@5.2.15-2%2Bb13?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "bash@5.2.15-2+b13"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "bash"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "2"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "5.2.15"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/bsdutils@2.38.1-5%2Bdeb12u3?arch=amd64&distro=debian-12.15&epoch=1",
      "type": "library",
      "supplier": {
        "name": "util-linux packagers <util-linux@packages.debian.org>"
      },
      "name": "bsdutils",
      "version": "1:2.38.1-5+deb12u3",
      "licenses": [
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-or-later"
          }
        },
        {
          "license": {
            "name": "public-domain"
          }
        },
        {
          "license": {
            "name": "BSD-4-Clause"
          }
        },
        {
          "license": {
            "name": "MIT"
          }
        },
        {
          "license": {
            "name": "BSD-3-Clause"
          }
        },
        {
          "license": {
            "name": "BSLA"
          }
        },
        {
          "license": {
            "name": "LGPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "LGPL-2.1-or-later"
          }
        },
        {
          "license": {
            "name": "LGPL-3.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-only"
          }
        },
        {
          "license": {
            "name": "LGPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "LGPL-2.1-only"
          }
        },
        {
          "license": {
            "name": "LGPL-3.0-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/bsdutils@2.38.1-5%2Bdeb12u3?arch=amd64&distro=debian-12.15&epoch=1",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "bsdutils@1:2.38.1-5+deb12u3"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "util-linux"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "5+deb12u3"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "2.38.1"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/ca-certificates@20250419~deb12u2?arch=all&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Julien Cristau <jcristau@debian.org>"
      },
      "name": "ca-certificates",
      "version": "20250419~deb12u2",
      "licenses": [
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "MPL-2.0"
          }
        }
      ],
      "purl": "pkg:deb/debian/ca-certificates@20250419~deb12u2?arch=all&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:041fa36e7b553df7512e26cdd7928c7b0d6bd791c9548f15bb7cd65e1bf263dc"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:5681027ac9bb5e47b5b9e1164dbd199959488b99838037e2ebc3ade3250ff736"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "ca-certificates@20250419~deb12u2"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "ca-certificates"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "20250419~deb12u2"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/coreutils@9.1-1?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Michael Stone <mstone@debian.org>"
      },
      "name": "coreutils",
      "version": "9.1-1",
      "licenses": [
        {
          "license": {
            "name": "GPL-3.0-or-later"
          }
        },
        {
          "license": {
            "name": "BSD-4-Clause-UC"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-only"
          }
        },
        {
          "license": {
            "name": "ISC"
          }
        },
        {
          "license": {
            "name": "FSFULLR"
          }
        },
        {
          "license": {
            "name": "GFDL-1.3-no-invariants-only"
          }
        },
        {
          "license": {
            "name": "GFDL-1.3-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/coreutils@9.1-1?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "coreutils@9.1-1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "coreutils"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "1"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "9.1"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/curl@7.88.1-10%2Bdeb12u15?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Alessandro Ghedini <ghedo@debian.org>"
      },
      "name": "curl",
      "version": "7.88.1-10+deb12u15",
      "licenses": [
        {
          "license": {
            "name": "curl"
          }
        },
        {
          "license": {
            "name": "OLDAP-2.8"
          }
        },
        {
          "license": {
            "name": "ISC"
          }
        },
        {
          "license": {
            "name": "GPL-2+ with Autoconf-data exception"
          }
        },
        {
          "license": {
            "name": "GPL-3+ with Autoconf-data exception"
          }
        },
        {
          "license": {
            "name": "GPL-2+ with Libtool exception"
          }
        },
        {
          "license": {
            "name": "BSD-3-Clause"
          }
        },
        {
          "license": {
            "name": "BSD-4-Clause-UC"
          }
        },
        {
          "license": {
            "name": "FSFULLR"
          }
        },
        {
          "license": {
            "name": "X11"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/curl@7.88.1-10%2Bdeb12u15?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:041fa36e7b553df7512e26cdd7928c7b0d6bd791c9548f15bb7cd65e1bf263dc"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:5681027ac9bb5e47b5b9e1164dbd199959488b99838037e2ebc3ade3250ff736"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "curl@7.88.1-10+deb12u15"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "curl"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "10+deb12u15"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "7.88.1"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/dash@0.5.12-2?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Andrej Shadura <andrewsh@debian.org>"
      },
      "name": "dash",
      "version": "0.5.12-2",
      "licenses": [
        {
          "license": {
            "name": "BSD-3-Clause"
          }
        },
        {
          "license": {
            "name": "public-domain"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/dash@0.5.12-2?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "dash@0.5.12-2"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "dash"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "2"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "0.5.12"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/debconf@1.5.82?arch=all&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Debconf Developers <debconf-devel@lists.alioth.debian.org>"
      },
      "name": "debconf",
      "version": "1.5.82",
      "licenses": [
        {
          "license": {
            "name": "BSD-2-Clause"
          }
        }
      ],
      "purl": "pkg:deb/debian/debconf@1.5.82?arch=all&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "debconf@1.5.82"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "debconf"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "1.5.82"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/debian-archive-keyring@2023.3%2Bdeb12u2?arch=all&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Debian Release Team <packages@release.debian.org>"
      },
      "name": "debian-archive-keyring",
      "version": "2023.3+deb12u2",
      "licenses": [
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        }
      ],
      "purl": "pkg:deb/debian/debian-archive-keyring@2023.3%2Bdeb12u2?arch=all&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "debian-archive-keyring@2023.3+deb12u2"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "debian-archive-keyring"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "2023.3+deb12u2"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/debianutils@5.7-0.5~deb12u1?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Clint Adams <clint@debian.org>"
      },
      "name": "debianutils",
      "version": "5.7-0.5~deb12u1",
      "licenses": [
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "public-domain"
          }
        },
        {
          "license": {
            "name": "SMAIL-GPL"
          }
        }
      ],
      "purl": "pkg:deb/debian/debianutils@5.7-0.5~deb12u1?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "debianutils@5.7-0.5~deb12u1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "debianutils"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "0.5~deb12u1"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "5.7"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/diffutils@3.8-4?arch=amd64&distro=debian-12.15&epoch=1",
      "type": "library",
      "supplier": {
        "name": "Santiago Vila <sanvila@debian.org>"
      },
      "name": "diffutils",
      "version": "1:3.8-4",
      "licenses": [
        {
          "license": {
            "name": "GPL-3.0-or-later"
          }
        },
        {
          "license": {
            "name": "FSFULLR"
          }
        },
        {
          "license": {
            "name": "LGPL-2.1-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-with-autoconf-exception+"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-only"
          }
        },
        {
          "license": {
            "name": "GPL-3+ with texinfo exception"
          }
        },
        {
          "license": {
            "name": "LGPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "X11"
          }
        },
        {
          "license": {
            "name": "FSFAP"
          }
        },
        {
          "license": {
            "name": "GFDL-1.3-no-invariants-only"
          }
        },
        {
          "license": {
            "name": "LGPL-3.0-or-later"
          }
        },
        {
          "license": {
            "name": "LGPL-3.0-only"
          }
        },
        {
          "license": {
            "name": "public-domain"
          }
        },
        {
          "license": {
            "name": "LGPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "LGPL-2.1-only"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "GFDL-1.3-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/diffutils@3.8-4?arch=amd64&distro=debian-12.15&epoch=1",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "diffutils@1:3.8-4"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcEpoch",
          "value": "1"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "diffutils"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "4"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "3.8"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/dpkg@1.21.23?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Dpkg Developers <debian-dpkg@lists.debian.org>"
      },
      "name": "dpkg",
      "version": "1.21.23",
      "licenses": [
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "BSD-2-Clause"
          }
        },
        {
          "license": {
            "name": "public-domain-s-s-d"
          }
        }
      ],
      "purl": "pkg:deb/debian/dpkg@1.21.23?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "dpkg@1.21.23"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "dpkg"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "1.21.23"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/e2fsprogs@1.47.0-2%2Bb2?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Theodore Y. Ts'o <tytso@mit.edu>"
      },
      "name": "e2fsprogs",
      "version": "1.47.0-2+b2",
      "licenses": [
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "LGPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "BSD-3-Clause"
          }
        },
        {
          "license": {
            "name": "Apache-2.0"
          }
        },
        {
          "license": {
            "name": "ISC"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "MIT-US-export"
          }
        },
        {
          "license": {
            "name": "Kazlib"
          }
        },
        {
          "license": {
            "name": "Latex2e"
          }
        },
        {
          "license": {
            "name": "GPL-2+ with Texinfo exception"
          }
        }
      ],
      "purl": "pkg:deb/debian/e2fsprogs@1.47.0-2%2Bb2?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "e2fsprogs@1.47.0-2+b2"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "e2fsprogs"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "2"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "1.47.0"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/findutils@4.9.0-4?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Andreas Metzler <ametzler@debian.org>"
      },
      "name": "findutils",
      "version": "4.9.0-4",
      "licenses": [
        {
          "license": {
            "name": "GFDL-1.3-no-invariants-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-or-later"
          }
        },
        {
          "license": {
            "name": "FSFAP"
          }
        },
        {
          "license": {
            "name": "GPL-3+ with Autoconf-data exception"
          }
        },
        {
          "license": {
            "name": "FSFULLR"
          }
        },
        {
          "license": {
            "name": "GPL-2+ with Autoconf-data exception"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "X11"
          }
        },
        {
          "license": {
            "name": "public-domain"
          }
        },
        {
          "license": {
            "name": "GPL with automake exception"
          }
        },
        {
          "license": {
            "name": "LGPL-2.1-or-later"
          }
        },
        {
          "license": {
            "name": "LGPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "LGPL-3.0-or-later"
          }
        },
        {
          "license": {
            "name": "BSD-3-clause and/or GPL-3+"
          }
        },
        {
          "license": {
            "name": "GPL-3+ with Bison-2.2 exception"
          }
        },
        {
          "license": {
            "name": "LGPL-3.0-only"
          }
        },
        {
          "license": {
            "name": "ISC and/or LGPL-2.1+"
          }
        },
        {
          "license": {
            "name": "BSD-3-Clause"
          }
        },
        {
          "license": {
            "name": "GFDL-1.3-only"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-only"
          }
        },
        {
          "license": {
            "name": "ISC"
          }
        },
        {
          "license": {
            "name": "LGPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "LGPL-2.1-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/findutils@4.9.0-4?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "findutils@4.9.0-4"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "findutils"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "4"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "4.9.0"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/gcc-12-base@12.2.0-14%2Bdeb12u1?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Debian GCC Maintainers <debian-gcc@lists.debian.org>"
      },
      "name": "gcc-12-base",
      "version": "12.2.0-14+deb12u1",
      "licenses": [
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-only"
          }
        },
        {
          "license": {
            "name": "GFDL-1.2-only"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "Artistic-2.0"
          }
        },
        {
          "license": {
            "name": "LGPL-2.0-or-later"
          }
        }
      ],
      "purl": "pkg:deb/debian/gcc-12-base@12.2.0-14%2Bdeb12u1?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "gcc-12-base@12.2.0-14+deb12u1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "gcc-12"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "14+deb12u1"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "12.2.0"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/gpgv@2.2.40-1.1%2Bdeb12u2?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Debian GnuPG Maintainers <pkg-gnupg-maint@lists.alioth.debian.org>"
      },
      "name": "gpgv",
      "version": "2.2.40-1.1+deb12u2",
      "licenses": [
        {
          "license": {
            "name": "GPL-3.0-or-later"
          }
        },
        {
          "license": {
            "name": "permissive"
          }
        },
        {
          "license": {
            "name": "LGPL-2.1-or-later"
          }
        },
        {
          "license": {
            "name": "MIT"
          }
        },
        {
          "license": {
            "name": "BSD-3-Clause"
          }
        },
        {
          "license": {
            "name": "LGPL-3.0-or-later"
          }
        },
        {
          "license": {
            "name": "RFC-Reference"
          }
        },
        {
          "license": {
            "name": "TinySCHEME"
          }
        },
        {
          "license": {
            "name": "CC0-1.0"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-only"
          }
        },
        {
          "license": {
            "name": "LGPL-3.0-only"
          }
        },
        {
          "license": {
            "name": "LGPL-2.1-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/gpgv@2.2.40-1.1%2Bdeb12u2?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "gpgv@2.2.40-1.1+deb12u2"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "gnupg2"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "1.1+deb12u2"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "2.2.40"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/grep@3.8-5?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Anibal Monsalve Salazar <anibal@debian.org>"
      },
      "name": "grep",
      "version": "3.8-5",
      "licenses": [
        {
          "license": {
            "name": "GPL-3.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/grep@3.8-5?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "grep@3.8-5"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "grep"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "5"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "3.8"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/gzip@1.12-1?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Milan Kupcevic <milan@debian.org>"
      },
      "name": "gzip",
      "version": "1.12-1",
      "licenses": [
        {
          "license": {
            "name": "GPL-3.0-or-later"
          }
        },
        {
          "license": {
            "name": "GFDL-1.3+-no-invariant"
          }
        },
        {
          "license": {
            "name": "FSF-manpages"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-only"
          }
        },
        {
          "license": {
            "name": "GFDL-3"
          }
        }
      ],
      "purl": "pkg:deb/debian/gzip@1.12-1?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "gzip@1.12-1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "gzip"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "1"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "1.12"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/hostname@3.23%2Bnmu1?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Michael Meskes <meskes@debian.org>"
      },
      "name": "hostname",
      "version": "3.23+nmu1",
      "licenses": [
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/hostname@3.23%2Bnmu1?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "hostname@3.23+nmu1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "hostname"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "3.23+nmu1"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/init-system-helpers@1.65.2%2Bdeb12u1?arch=all&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Debian systemd Maintainers <pkg-systemd-maintainers@lists.alioth.debian.org>"
      },
      "name": "init-system-helpers",
      "version": "1.65.2+deb12u1",
      "licenses": [
        {
          "license": {
            "name": "BSD-3-Clause"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/init-system-helpers@1.65.2%2Bdeb12u1?arch=all&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "init-system-helpers@1.65.2+deb12u1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "init-system-helpers"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "1.65.2+deb12u1"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/krb5-locales@1.20.1-2%2Bdeb12u5?arch=all&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Sam Hartman <hartmans@debian.org>"
      },
      "name": "krb5-locales",
      "version": "1.20.1-2+deb12u5",
      "licenses": [
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/krb5-locales@1.20.1-2%2Bdeb12u5?arch=all&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:041fa36e7b553df7512e26cdd7928c7b0d6bd791c9548f15bb7cd65e1bf263dc"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:5681027ac9bb5e47b5b9e1164dbd199959488b99838037e2ebc3ade3250ff736"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "krb5-locales@1.20.1-2+deb12u5"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "krb5"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "2+deb12u5"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "1.20.1"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libacl1@2.3.1-3?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Guillem Jover <guillem@debian.org>"
      },
      "name": "libacl1",
      "version": "2.3.1-3",
      "licenses": [
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "LGPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "LGPL-2.1-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/libacl1@2.3.1-3?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libacl1@2.3.1-3"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "acl"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "3"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "2.3.1"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libapt-pkg6.0@2.6.1?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "APT Development Team <deity@lists.debian.org>"
      },
      "name": "libapt-pkg6.0",
      "version": "2.6.1",
      "licenses": [
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "BSD-3-Clause"
          }
        },
        {
          "license": {
            "name": "MIT"
          }
        }
      ],
      "purl": "pkg:deb/debian/libapt-pkg6.0@2.6.1?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libapt-pkg6.0@2.6.1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "apt"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "2.6.1"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libattr1@2.5.1-4?arch=amd64&distro=debian-12.15&epoch=1",
      "type": "library",
      "supplier": {
        "name": "Guillem Jover <guillem@debian.org>"
      },
      "name": "libattr1",
      "version": "1:2.5.1-4",
      "licenses": [
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "LGPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "LGPL-2.1-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/libattr1@2.5.1-4?arch=amd64&distro=debian-12.15&epoch=1",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libattr1@1:2.5.1-4"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcEpoch",
          "value": "1"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "attr"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "4"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "2.5.1"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libaudit-common@3.0.9-1?arch=all&distro=debian-12.15&epoch=1",
      "type": "library",
      "supplier": {
        "name": "Laurent Bigonville <bigon@debian.org>"
      },
      "name": "libaudit-common",
      "version": "1:3.0.9-1",
      "licenses": [
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "LGPL-2.1-only"
          }
        },
        {
          "license": {
            "name": "GPL-1.0-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/libaudit-common@3.0.9-1?arch=all&distro=debian-12.15&epoch=1",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libaudit-common@1:3.0.9-1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcEpoch",
          "value": "1"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "audit"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "1"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "3.0.9"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libaudit1@3.0.9-1?arch=amd64&distro=debian-12.15&epoch=1",
      "type": "library",
      "supplier": {
        "name": "Laurent Bigonville <bigon@debian.org>"
      },
      "name": "libaudit1",
      "version": "1:3.0.9-1",
      "licenses": [
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "LGPL-2.1-only"
          }
        },
        {
          "license": {
            "name": "GPL-1.0-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/libaudit1@3.0.9-1?arch=amd64&distro=debian-12.15&epoch=1",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libaudit1@1:3.0.9-1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcEpoch",
          "value": "1"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "audit"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "1"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "3.0.9"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libblkid1@2.38.1-5%2Bdeb12u3?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "util-linux packagers <util-linux@packages.debian.org>"
      },
      "name": "libblkid1",
      "version": "2.38.1-5+deb12u3",
      "licenses": [
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-or-later"
          }
        },
        {
          "license": {
            "name": "public-domain"
          }
        },
        {
          "license": {
            "name": "BSD-4-Clause"
          }
        },
        {
          "license": {
            "name": "MIT"
          }
        },
        {
          "license": {
            "name": "BSD-3-Clause"
          }
        },
        {
          "license": {
            "name": "BSLA"
          }
        },
        {
          "license": {
            "name": "LGPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "LGPL-2.1-or-later"
          }
        },
        {
          "license": {
            "name": "LGPL-3.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-only"
          }
        },
        {
          "license": {
            "name": "LGPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "LGPL-2.1-only"
          }
        },
        {
          "license": {
            "name": "LGPL-3.0-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/libblkid1@2.38.1-5%2Bdeb12u3?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libblkid1@2.38.1-5+deb12u3"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "util-linux"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "5+deb12u3"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "2.38.1"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libbrotli1@1.0.9-2%2Bb6?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Tomasz Buchert <tomasz@debian.org>"
      },
      "name": "libbrotli1",
      "version": "1.0.9-2+b6",
      "licenses": [
        {
          "license": {
            "name": "MIT"
          }
        }
      ],
      "purl": "pkg:deb/debian/libbrotli1@1.0.9-2%2Bb6?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:041fa36e7b553df7512e26cdd7928c7b0d6bd791c9548f15bb7cd65e1bf263dc"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:5681027ac9bb5e47b5b9e1164dbd199959488b99838037e2ebc3ade3250ff736"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libbrotli1@1.0.9-2+b6"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "brotli"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "2"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "1.0.9"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libbz2-1.0@1.0.8-5%2Bb1?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Anibal Monsalve Salazar <anibal@debian.org>"
      },
      "name": "libbz2-1.0",
      "version": "1.0.8-5+b1",
      "licenses": [
        {
          "license": {
            "name": "BSD-3-Clause"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/libbz2-1.0@1.0.8-5%2Bb1?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libbz2-1.0@1.0.8-5+b1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "bzip2"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "5"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "1.0.8"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libc-bin@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "GNU Libc Maintainers <debian-glibc@lists.debian.org>"
      },
      "name": "libc-bin",
      "version": "2.36-9+deb12u14",
      "licenses": [
        {
          "license": {
            "name": "LGPL-2.1-only"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/libc-bin@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libc-bin@2.36-9+deb12u14"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "glibc"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "9+deb12u14"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "2.36"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "GNU Libc Maintainers <debian-glibc@lists.debian.org>"
      },
      "name": "libc6",
      "version": "2.36-9+deb12u14",
      "licenses": [
        {
          "license": {
            "name": "LGPL-2.1-only"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libc6@2.36-9+deb12u14"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "glibc"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "9+deb12u14"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "2.36"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libcap-ng0@0.8.3-1%2Bb3?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Håvard F. Aasen <havard.f.aasen@pfft.no>"
      },
      "name": "libcap-ng0",
      "version": "0.8.3-1+b3",
      "licenses": [
        {
          "license": {
            "name": "LGPL-2.1-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-only"
          }
        },
        {
          "license": {
            "name": "LGPL-2.1-only"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/libcap-ng0@0.8.3-1%2Bb3?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libcap-ng0@0.8.3-1+b3"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "libcap-ng"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "1"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "0.8.3"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libcap2@2.66-4%2Bdeb12u3%2Bb1?arch=amd64&distro=debian-12.15&epoch=1",
      "type": "library",
      "supplier": {
        "name": "Christian Kastner <ckk@debian.org>"
      },
      "name": "libcap2",
      "version": "1:2.66-4+deb12u3+b1",
      "licenses": [
        {
          "license": {
            "name": "BSD-3-Clause"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        }
      ],
      "purl": "pkg:deb/debian/libcap2@2.66-4%2Bdeb12u3%2Bb1?arch=amd64&distro=debian-12.15&epoch=1",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libcap2@1:2.66-4+deb12u3+b1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcEpoch",
          "value": "1"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "libcap2"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "4+deb12u3"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "2.66"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libcom-err2@1.47.0-2%2Bb2?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Theodore Y. Ts'o <tytso@mit.edu>"
      },
      "name": "libcom-err2",
      "version": "1.47.0-2+b2",
      "licenses": [
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "LGPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "BSD-3-Clause"
          }
        },
        {
          "license": {
            "name": "Apache-2.0"
          }
        },
        {
          "license": {
            "name": "ISC"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "MIT-US-export"
          }
        },
        {
          "license": {
            "name": "Kazlib"
          }
        },
        {
          "license": {
            "name": "Latex2e"
          }
        },
        {
          "license": {
            "name": "GPL-2+ with Texinfo exception"
          }
        }
      ],
      "purl": "pkg:deb/debian/libcom-err2@1.47.0-2%2Bb2?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libcom-err2@1.47.0-2+b2"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "e2fsprogs"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "2"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "1.47.0"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libcrypt1@4.4.33-2?arch=amd64&distro=debian-12.15&epoch=1",
      "type": "library",
      "supplier": {
        "name": "Marco d'Itri <md@linux.it>"
      },
      "name": "libcrypt1",
      "version": "1:4.4.33-2",
      "purl": "pkg:deb/debian/libcrypt1@4.4.33-2?arch=amd64&distro=debian-12.15&epoch=1",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libcrypt1@1:4.4.33-2"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcEpoch",
          "value": "1"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "libxcrypt"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "2"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "4.4.33"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libcurl4@7.88.1-10%2Bdeb12u15?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Alessandro Ghedini <ghedo@debian.org>"
      },
      "name": "libcurl4",
      "version": "7.88.1-10+deb12u15",
      "licenses": [
        {
          "license": {
            "name": "curl"
          }
        },
        {
          "license": {
            "name": "OLDAP-2.8"
          }
        },
        {
          "license": {
            "name": "ISC"
          }
        },
        {
          "license": {
            "name": "GPL-2+ with Autoconf-data exception"
          }
        },
        {
          "license": {
            "name": "GPL-3+ with Autoconf-data exception"
          }
        },
        {
          "license": {
            "name": "GPL-2+ with Libtool exception"
          }
        },
        {
          "license": {
            "name": "BSD-3-Clause"
          }
        },
        {
          "license": {
            "name": "BSD-4-Clause-UC"
          }
        },
        {
          "license": {
            "name": "FSFULLR"
          }
        },
        {
          "license": {
            "name": "X11"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/libcurl4@7.88.1-10%2Bdeb12u15?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:041fa36e7b553df7512e26cdd7928c7b0d6bd791c9548f15bb7cd65e1bf263dc"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:5681027ac9bb5e47b5b9e1164dbd199959488b99838037e2ebc3ade3250ff736"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libcurl4@7.88.1-10+deb12u15"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "curl"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "10+deb12u15"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "7.88.1"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libdb5.3@5.3.28%2Bdfsg2-1?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Bastian Germann <bage@debian.org>"
      },
      "name": "libdb5.3",
      "version": "5.3.28+dfsg2-1",
      "licenses": [
        {
          "license": {
            "name": "Sleepycat"
          }
        },
        {
          "license": {
            "name": "BSD-3-Clause"
          }
        },
        {
          "license": {
            "name": "MS-PL"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "Artistic-2.0"
          }
        },
        {
          "license": {
            "name": "X11"
          }
        },
        {
          "license": {
            "name": "MIT-old"
          }
        },
        {
          "license": {
            "name": "TCL-like"
          }
        },
        {
          "license": {
            "name": "BSD-3-clause-fjord"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-only"
          }
        },
        {
          "license": {
            "name": "Zlib"
          }
        }
      ],
      "purl": "pkg:deb/debian/libdb5.3@5.3.28%2Bdfsg2-1?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libdb5.3@5.3.28+dfsg2-1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "db5.3"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "1"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "5.3.28+dfsg2"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libdebconfclient0@0.270?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Debian Install System Team <debian-boot@lists.debian.org>"
      },
      "name": "libdebconfclient0",
      "version": "0.270",
      "licenses": [
        {
          "license": {
            "name": "BSD-2-Clause"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/libdebconfclient0@0.270?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libdebconfclient0@0.270"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "cdebconf"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "0.270"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libext2fs2@1.47.0-2%2Bb2?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Theodore Y. Ts'o <tytso@mit.edu>"
      },
      "name": "libext2fs2",
      "version": "1.47.0-2+b2",
      "licenses": [
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "LGPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "BSD-3-Clause"
          }
        },
        {
          "license": {
            "name": "Apache-2.0"
          }
        },
        {
          "license": {
            "name": "ISC"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "MIT-US-export"
          }
        },
        {
          "license": {
            "name": "Kazlib"
          }
        },
        {
          "license": {
            "name": "Latex2e"
          }
        },
        {
          "license": {
            "name": "GPL-2+ with Texinfo exception"
          }
        }
      ],
      "purl": "pkg:deb/debian/libext2fs2@1.47.0-2%2Bb2?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libext2fs2@1.47.0-2+b2"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "e2fsprogs"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "2"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "1.47.0"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libffi8@3.4.4-1?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Debian GCC Maintainers <debian-gcc@lists.debian.org>"
      },
      "name": "libffi8",
      "version": "3.4.4-1",
      "licenses": [
        {
          "license": {
            "name": "MIT"
          }
        },
        {
          "license": {
            "name": "X11"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-or-later"
          }
        },
        {
          "license": {
            "name": "MPL-1.1"
          }
        },
        {
          "license": {
            "name": "LGPL-2.1-or-later"
          }
        },
        {
          "license": {
            "name": "public-domain"
          }
        }
      ],
      "purl": "pkg:deb/debian/libffi8@3.4.4-1?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libffi8@3.4.4-1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "libffi"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "1"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "3.4.4"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libgcc-s1@12.2.0-14%2Bdeb12u1?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Debian GCC Maintainers <debian-gcc@lists.debian.org>"
      },
      "name": "libgcc-s1",
      "version": "12.2.0-14+deb12u1",
      "purl": "pkg:deb/debian/libgcc-s1@12.2.0-14%2Bdeb12u1?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libgcc-s1@12.2.0-14+deb12u1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "gcc-12"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "14+deb12u1"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "12.2.0"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libgcrypt20@1.10.1-3%2Bdeb12u1?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Debian GnuTLS Maintainers <pkg-gnutls-maint@lists.alioth.debian.org>"
      },
      "name": "libgcrypt20",
      "version": "1.10.1-3+deb12u1",
      "licenses": [
        {
          "license": {
            "name": "LGPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/libgcrypt20@1.10.1-3%2Bdeb12u1?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libgcrypt20@1.10.1-3+deb12u1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "libgcrypt20"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "3+deb12u1"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "1.10.1"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libgmp10@6.2.1%2Bdfsg1-1.1?arch=amd64&distro=debian-12.15&epoch=2",
      "type": "library",
      "supplier": {
        "name": "Debian Science Team <debian-science-maintainers@lists.alioth.debian.org>"
      },
      "name": "libgmp10",
      "version": "2:6.2.1+dfsg1-1.1",
      "licenses": [
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "LGPL-3.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-3+ with Bison exception"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-only"
          }
        },
        {
          "license": {
            "name": "LGPL-3.0-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/libgmp10@6.2.1%2Bdfsg1-1.1?arch=amd64&distro=debian-12.15&epoch=2",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libgmp10@2:6.2.1+dfsg1-1.1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcEpoch",
          "value": "2"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "gmp"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "1.1"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "6.2.1+dfsg1"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libgnutls30@3.7.9-2%2Bdeb12u7?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Debian GnuTLS Maintainers <pkg-gnutls-maint@lists.alioth.debian.org>"
      },
      "name": "libgnutls30",
      "version": "3.7.9-2+deb12u7",
      "licenses": [
        {
          "license": {
            "name": "LGPL-2.1-only"
          }
        },
        {
          "license": {
            "name": "LGPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "LGPL-3.0-only"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-only"
          }
        },
        {
          "license": {
            "name": "GFDL-1.3-only"
          }
        },
        {
          "license": {
            "name": "CC0-1.0"
          }
        },
        {
          "license": {
            "name": "MIT"
          }
        },
        {
          "license": {
            "name": "Apache-2.0"
          }
        },
        {
          "license": {
            "name": "LGPL-3.0-or-later"
          }
        },
        {
          "license": {
            "name": "LGPL-2.1-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-or-later"
          }
        },
        {
          "license": {
            "name": "BSD-3-Clause"
          }
        }
      ],
      "purl": "pkg:deb/debian/libgnutls30@3.7.9-2%2Bdeb12u7?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libgnutls30@3.7.9-2+deb12u7"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "gnutls28"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "2+deb12u7"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "3.7.9"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libgpg-error0@1.46-1?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Debian GnuPG Maintainers <pkg-gnupg-maint@lists.alioth.debian.org>"
      },
      "name": "libgpg-error0",
      "version": "1.46-1",
      "licenses": [
        {
          "license": {
            "name": "LGPL-2.1-or-later"
          }
        },
        {
          "license": {
            "name": "BSD-3-Clause"
          }
        },
        {
          "license": {
            "name": "g10-permissive"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-or-later"
          }
        },
        {
          "license": {
            "name": "LGPL-2.1-only"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/libgpg-error0@1.46-1?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libgpg-error0@1.46-1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "libgpg-error"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "1"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "1.46"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libgssapi-krb5-2@1.20.1-2%2Bdeb12u5?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Sam Hartman <hartmans@debian.org>"
      },
      "name": "libgssapi-krb5-2",
      "version": "1.20.1-2+deb12u5",
      "licenses": [
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/libgssapi-krb5-2@1.20.1-2%2Bdeb12u5?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:041fa36e7b553df7512e26cdd7928c7b0d6bd791c9548f15bb7cd65e1bf263dc"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:5681027ac9bb5e47b5b9e1164dbd199959488b99838037e2ebc3ade3250ff736"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libgssapi-krb5-2@1.20.1-2+deb12u5"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "krb5"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "2+deb12u5"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "1.20.1"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libhogweed6@3.8.1-2?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Magnus Holmgren <holmgren@debian.org>"
      },
      "name": "libhogweed6",
      "version": "3.8.1-2",
      "licenses": [
        {
          "license": {
            "name": "LGPL-3.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "LGPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "LGPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "MIT"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-with-autoconf-exception+"
          }
        },
        {
          "license": {
            "name": "public-domain"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "GAP"
          }
        }
      ],
      "purl": "pkg:deb/debian/libhogweed6@3.8.1-2?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libhogweed6@3.8.1-2"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "nettle"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "2"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "3.8.1"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libidn2-0@2.3.3-1%2Bb1?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Debian Libidn team <help-libidn@gnu.org>"
      },
      "name": "libidn2-0",
      "version": "2.3.3-1+b1",
      "licenses": [
        {
          "license": {
            "name": "GPL-3.0-or-later"
          }
        },
        {
          "license": {
            "name": "LGPL-3.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "Unicode"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-only"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "LGPL-3.0-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/libidn2-0@2.3.3-1%2Bb1?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libidn2-0@2.3.3-1+b1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "libidn2"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "1"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "2.3.3"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libk5crypto3@1.20.1-2%2Bdeb12u5?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Sam Hartman <hartmans@debian.org>"
      },
      "name": "libk5crypto3",
      "version": "1.20.1-2+deb12u5",
      "licenses": [
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/libk5crypto3@1.20.1-2%2Bdeb12u5?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:041fa36e7b553df7512e26cdd7928c7b0d6bd791c9548f15bb7cd65e1bf263dc"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:5681027ac9bb5e47b5b9e1164dbd199959488b99838037e2ebc3ade3250ff736"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libk5crypto3@1.20.1-2+deb12u5"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "krb5"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "2+deb12u5"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "1.20.1"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libkeyutils1@1.6.3-2?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Christian Kastner <ckk@debian.org>"
      },
      "name": "libkeyutils1",
      "version": "1.6.3-2",
      "licenses": [
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "LGPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "LGPL-2.0-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/libkeyutils1@1.6.3-2?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:041fa36e7b553df7512e26cdd7928c7b0d6bd791c9548f15bb7cd65e1bf263dc"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:5681027ac9bb5e47b5b9e1164dbd199959488b99838037e2ebc3ade3250ff736"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libkeyutils1@1.6.3-2"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "keyutils"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "2"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "1.6.3"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libkrb5-3@1.20.1-2%2Bdeb12u5?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Sam Hartman <hartmans@debian.org>"
      },
      "name": "libkrb5-3",
      "version": "1.20.1-2+deb12u5",
      "licenses": [
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/libkrb5-3@1.20.1-2%2Bdeb12u5?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:041fa36e7b553df7512e26cdd7928c7b0d6bd791c9548f15bb7cd65e1bf263dc"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:5681027ac9bb5e47b5b9e1164dbd199959488b99838037e2ebc3ade3250ff736"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libkrb5-3@1.20.1-2+deb12u5"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "krb5"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "2+deb12u5"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "1.20.1"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libkrb5support0@1.20.1-2%2Bdeb12u5?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Sam Hartman <hartmans@debian.org>"
      },
      "name": "libkrb5support0",
      "version": "1.20.1-2+deb12u5",
      "licenses": [
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/libkrb5support0@1.20.1-2%2Bdeb12u5?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:041fa36e7b553df7512e26cdd7928c7b0d6bd791c9548f15bb7cd65e1bf263dc"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:5681027ac9bb5e47b5b9e1164dbd199959488b99838037e2ebc3ade3250ff736"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libkrb5support0@1.20.1-2+deb12u5"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "krb5"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "2+deb12u5"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "1.20.1"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libldap-2.5-0@2.5.13%2Bdfsg-5?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Debian OpenLDAP Maintainers <pkg-openldap-devel@lists.alioth.debian.org>"
      },
      "name": "libldap-2.5-0",
      "version": "2.5.13+dfsg-5",
      "licenses": [
        {
          "license": {
            "name": "OpenLDAP-2.8"
          }
        },
        {
          "license": {
            "name": "FSF-unlimited"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-with-autoconf-exception+"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-with-autoconf-exception+"
          }
        },
        {
          "license": {
            "name": "GPL-2+ with Libtool exception"
          }
        },
        {
          "license": {
            "name": "GPL-3+ with Libtool exception"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "UMich"
          }
        },
        {
          "license": {
            "name": "F5"
          }
        },
        {
          "license": {
            "name": "JCG"
          }
        },
        {
          "license": {
            "name": "MIT-XC"
          }
        },
        {
          "license": {
            "name": "NeoSoft-permissive"
          }
        },
        {
          "license": {
            "name": "BSD-3-Clause"
          }
        },
        {
          "license": {
            "name": "Beerware"
          }
        },
        {
          "license": {
            "name": "public-domain"
          }
        },
        {
          "license": {
            "name": "BSD-4-clause-California"
          }
        },
        {
          "license": {
            "name": "BSD-3-clause-variant"
          }
        },
        {
          "license": {
            "name": "Expat-ISC"
          }
        },
        {
          "license": {
            "name": "Expat-UNM"
          }
        },
        {
          "license": {
            "name": "MIT"
          }
        },
        {
          "license": {
            "name": "BSD-3-clause-California"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/libldap-2.5-0@2.5.13%2Bdfsg-5?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:041fa36e7b553df7512e26cdd7928c7b0d6bd791c9548f15bb7cd65e1bf263dc"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:5681027ac9bb5e47b5b9e1164dbd199959488b99838037e2ebc3ade3250ff736"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libldap-2.5-0@2.5.13+dfsg-5"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "openldap"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "5"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "2.5.13+dfsg"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libldap-common@2.5.13%2Bdfsg-5?arch=all&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Debian OpenLDAP Maintainers <pkg-openldap-devel@lists.alioth.debian.org>"
      },
      "name": "libldap-common",
      "version": "2.5.13+dfsg-5",
      "licenses": [
        {
          "license": {
            "name": "OpenLDAP-2.8"
          }
        },
        {
          "license": {
            "name": "FSF-unlimited"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-with-autoconf-exception+"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-with-autoconf-exception+"
          }
        },
        {
          "license": {
            "name": "GPL-2+ with Libtool exception"
          }
        },
        {
          "license": {
            "name": "GPL-3+ with Libtool exception"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "UMich"
          }
        },
        {
          "license": {
            "name": "F5"
          }
        },
        {
          "license": {
            "name": "JCG"
          }
        },
        {
          "license": {
            "name": "MIT-XC"
          }
        },
        {
          "license": {
            "name": "NeoSoft-permissive"
          }
        },
        {
          "license": {
            "name": "BSD-3-Clause"
          }
        },
        {
          "license": {
            "name": "Beerware"
          }
        },
        {
          "license": {
            "name": "public-domain"
          }
        },
        {
          "license": {
            "name": "BSD-4-clause-California"
          }
        },
        {
          "license": {
            "name": "BSD-3-clause-variant"
          }
        },
        {
          "license": {
            "name": "Expat-ISC"
          }
        },
        {
          "license": {
            "name": "Expat-UNM"
          }
        },
        {
          "license": {
            "name": "MIT"
          }
        },
        {
          "license": {
            "name": "BSD-3-clause-California"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/libldap-common@2.5.13%2Bdfsg-5?arch=all&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:041fa36e7b553df7512e26cdd7928c7b0d6bd791c9548f15bb7cd65e1bf263dc"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:5681027ac9bb5e47b5b9e1164dbd199959488b99838037e2ebc3ade3250ff736"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libldap-common@2.5.13+dfsg-5"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "openldap"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "5"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "2.5.13+dfsg"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/liblz4-1@1.9.4-1?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Nobuhiro Iwamatsu <iwamatsu@debian.org>"
      },
      "name": "liblz4-1",
      "version": "1.9.4-1",
      "licenses": [
        {
          "license": {
            "name": "BSD-2-Clause"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/liblz4-1@1.9.4-1?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "liblz4-1@1.9.4-1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "lz4"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "1"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "1.9.4"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/liblzma5@5.4.1-1%2Bdeb12u2?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Sebastian Andrzej Siewior <sebastian@breakpoint.cc>"
      },
      "name": "liblzma5",
      "version": "5.4.1-1+deb12u2",
      "licenses": [
        {
          "license": {
            "name": "PD"
          }
        },
        {
          "license": {
            "name": "probably-PD"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "LGPL-2.1-or-later"
          }
        },
        {
          "license": {
            "name": "permissive-fsf"
          }
        },
        {
          "license": {
            "name": "Autoconf"
          }
        },
        {
          "license": {
            "name": "permissive-nowarranty"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "none"
          }
        },
        {
          "license": {
            "name": "config-h"
          }
        },
        {
          "license": {
            "name": "LGPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "LGPL-2.1-only"
          }
        },
        {
          "license": {
            "name": "noderivs"
          }
        },
        {
          "license": {
            "name": "PD-debian"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/liblzma5@5.4.1-1%2Bdeb12u2?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "liblzma5@5.4.1-1+deb12u2"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "xz-utils"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "1+deb12u2"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "5.4.1"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libmd0@1.0.4-2?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Guillem Jover <guillem@debian.org>"
      },
      "name": "libmd0",
      "version": "1.0.4-2",
      "licenses": [
        {
          "license": {
            "name": "BSD-3-Clause"
          }
        },
        {
          "license": {
            "name": "BSD-3-clause-Aaron-D-Gifford"
          }
        },
        {
          "license": {
            "name": "BSD-2-Clause"
          }
        },
        {
          "license": {
            "name": "BSD-2-Clause-NetBSD"
          }
        },
        {
          "license": {
            "name": "ISC"
          }
        },
        {
          "license": {
            "name": "Beerware"
          }
        },
        {
          "license": {
            "name": "public-domain-md4"
          }
        },
        {
          "license": {
            "name": "public-domain-md5"
          }
        },
        {
          "license": {
            "name": "public-domain-sha1"
          }
        }
      ],
      "purl": "pkg:deb/debian/libmd0@1.0.4-2?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libmd0@1.0.4-2"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "libmd"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "2"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "1.0.4"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libmount1@2.38.1-5%2Bdeb12u3?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "util-linux packagers <util-linux@packages.debian.org>"
      },
      "name": "libmount1",
      "version": "2.38.1-5+deb12u3",
      "licenses": [
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-or-later"
          }
        },
        {
          "license": {
            "name": "public-domain"
          }
        },
        {
          "license": {
            "name": "BSD-4-Clause"
          }
        },
        {
          "license": {
            "name": "MIT"
          }
        },
        {
          "license": {
            "name": "BSD-3-Clause"
          }
        },
        {
          "license": {
            "name": "BSLA"
          }
        },
        {
          "license": {
            "name": "LGPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "LGPL-2.1-or-later"
          }
        },
        {
          "license": {
            "name": "LGPL-3.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-only"
          }
        },
        {
          "license": {
            "name": "LGPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "LGPL-2.1-only"
          }
        },
        {
          "license": {
            "name": "LGPL-3.0-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/libmount1@2.38.1-5%2Bdeb12u3?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libmount1@2.38.1-5+deb12u3"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "util-linux"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "5+deb12u3"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "2.38.1"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libnettle8@3.8.1-2?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Magnus Holmgren <holmgren@debian.org>"
      },
      "name": "libnettle8",
      "version": "3.8.1-2",
      "licenses": [
        {
          "license": {
            "name": "LGPL-3.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "LGPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "LGPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "MIT"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-with-autoconf-exception+"
          }
        },
        {
          "license": {
            "name": "public-domain"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "GAP"
          }
        }
      ],
      "purl": "pkg:deb/debian/libnettle8@3.8.1-2?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libnettle8@3.8.1-2"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "nettle"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "2"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "3.8.1"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libnghttp2-14@1.52.0-1%2Bdeb12u3?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Tomasz Buchert <tomasz@debian.org>"
      },
      "name": "libnghttp2-14",
      "version": "1.52.0-1+deb12u3",
      "licenses": [
        {
          "license": {
            "name": "MIT"
          }
        },
        {
          "license": {
            "name": "all-permissive"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-with-autoconf-exception+"
          }
        },
        {
          "license": {
            "name": "BSD-2-Clause"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/libnghttp2-14@1.52.0-1%2Bdeb12u3?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:041fa36e7b553df7512e26cdd7928c7b0d6bd791c9548f15bb7cd65e1bf263dc"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:5681027ac9bb5e47b5b9e1164dbd199959488b99838037e2ebc3ade3250ff736"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libnghttp2-14@1.52.0-1+deb12u3"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "nghttp2"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "1+deb12u3"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "1.52.0"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libp11-kit0@0.24.1-2?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Debian GnuTLS Maintainers <pkg-gnutls-maint@lists.alioth.debian.org>"
      },
      "name": "libp11-kit0",
      "version": "0.24.1-2",
      "licenses": [
        {
          "license": {
            "name": "BSD-3-Clause"
          }
        },
        {
          "license": {
            "name": "permissive-like-automake-output"
          }
        },
        {
          "license": {
            "name": "ISC"
          }
        },
        {
          "license": {
            "name": "ISC+IBM"
          }
        },
        {
          "license": {
            "name": "LGPL-2.1-or-later"
          }
        },
        {
          "license": {
            "name": "Apache-2.0"
          }
        },
        {
          "license": {
            "name": "same-as-rest-of-p11kit"
          }
        },
        {
          "license": {
            "name": "LGPL-2.1-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/libp11-kit0@0.24.1-2?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libp11-kit0@0.24.1-2"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "p11-kit"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "2"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "0.24.1"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libpam-modules-bin@1.5.2-6%2Bdeb12u2?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Sam Hartman <hartmans@debian.org>"
      },
      "name": "libpam-modules-bin",
      "version": "1.5.2-6+deb12u2",
      "licenses": [
        {
          "license": {
            "name": "BSD-3-Clause"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-only"
          }
        },
        {
          "license": {
            "name": "GPL-3+ with Bison exception"
          }
        },
        {
          "license": {
            "name": "BSD-tcp_wrappers"
          }
        },
        {
          "license": {
            "name": "LGPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "LGPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "public-domain"
          }
        },
        {
          "license": {
            "name": "Beerware"
          }
        }
      ],
      "purl": "pkg:deb/debian/libpam-modules-bin@1.5.2-6%2Bdeb12u2?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libpam-modules-bin@1.5.2-6+deb12u2"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "pam"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "6+deb12u2"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "1.5.2"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libpam-modules@1.5.2-6%2Bdeb12u2?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Sam Hartman <hartmans@debian.org>"
      },
      "name": "libpam-modules",
      "version": "1.5.2-6+deb12u2",
      "licenses": [
        {
          "license": {
            "name": "BSD-3-Clause"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-only"
          }
        },
        {
          "license": {
            "name": "GPL-3+ with Bison exception"
          }
        },
        {
          "license": {
            "name": "BSD-tcp_wrappers"
          }
        },
        {
          "license": {
            "name": "LGPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "LGPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "public-domain"
          }
        },
        {
          "license": {
            "name": "Beerware"
          }
        }
      ],
      "purl": "pkg:deb/debian/libpam-modules@1.5.2-6%2Bdeb12u2?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libpam-modules@1.5.2-6+deb12u2"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "pam"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "6+deb12u2"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "1.5.2"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libpam-runtime@1.5.2-6%2Bdeb12u2?arch=all&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Sam Hartman <hartmans@debian.org>"
      },
      "name": "libpam-runtime",
      "version": "1.5.2-6+deb12u2",
      "licenses": [
        {
          "license": {
            "name": "BSD-3-Clause"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-only"
          }
        },
        {
          "license": {
            "name": "GPL-3+ with Bison exception"
          }
        },
        {
          "license": {
            "name": "BSD-tcp_wrappers"
          }
        },
        {
          "license": {
            "name": "LGPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "LGPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "public-domain"
          }
        },
        {
          "license": {
            "name": "Beerware"
          }
        }
      ],
      "purl": "pkg:deb/debian/libpam-runtime@1.5.2-6%2Bdeb12u2?arch=all&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libpam-runtime@1.5.2-6+deb12u2"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "pam"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "6+deb12u2"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "1.5.2"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libpam0g@1.5.2-6%2Bdeb12u2?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Sam Hartman <hartmans@debian.org>"
      },
      "name": "libpam0g",
      "version": "1.5.2-6+deb12u2",
      "licenses": [
        {
          "license": {
            "name": "BSD-3-Clause"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-only"
          }
        },
        {
          "license": {
            "name": "GPL-3+ with Bison exception"
          }
        },
        {
          "license": {
            "name": "BSD-tcp_wrappers"
          }
        },
        {
          "license": {
            "name": "LGPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "LGPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "public-domain"
          }
        },
        {
          "license": {
            "name": "Beerware"
          }
        }
      ],
      "purl": "pkg:deb/debian/libpam0g@1.5.2-6%2Bdeb12u2?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libpam0g@1.5.2-6+deb12u2"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "pam"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "6+deb12u2"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "1.5.2"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libpcre2-8-0@10.42-1%2Bdeb12u2?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Matthew Vernon <matthew@debian.org>"
      },
      "name": "libpcre2-8-0",
      "version": "10.42-1+deb12u2",
      "licenses": [
        {
          "license": {
            "name": "BSD-3-clause-Cambridge with BINARY LIBRARY-LIKE PACKAGES exception"
          }
        },
        {
          "license": {
            "name": "BSD-3-Clause"
          }
        },
        {
          "license": {
            "name": "X11"
          }
        },
        {
          "license": {
            "name": "BSD-2-Clause"
          }
        },
        {
          "license": {
            "name": "public-domain"
          }
        }
      ],
      "purl": "pkg:deb/debian/libpcre2-8-0@10.42-1%2Bdeb12u2?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libpcre2-8-0@10.42-1+deb12u2"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "pcre2"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "1+deb12u2"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "10.42"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libpsl5@0.21.2-1?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Tim Rühsen <tim.ruehsen@gmx.de>"
      },
      "name": "libpsl5",
      "version": "0.21.2-1",
      "licenses": [
        {
          "license": {
            "name": "MIT"
          }
        },
        {
          "license": {
            "name": "gnulib"
          }
        },
        {
          "license": {
            "name": "Chromium"
          }
        }
      ],
      "purl": "pkg:deb/debian/libpsl5@0.21.2-1?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:041fa36e7b553df7512e26cdd7928c7b0d6bd791c9548f15bb7cd65e1bf263dc"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:5681027ac9bb5e47b5b9e1164dbd199959488b99838037e2ebc3ade3250ff736"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libpsl5@0.21.2-1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "libpsl"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "1"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "0.21.2"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/librtmp1@2.4%2B20151223.gitfa8646d.1-2%2Bb2?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Debian Multimedia Maintainers <debian-multimedia@lists.debian.org>"
      },
      "name": "librtmp1",
      "version": "2.4+20151223.gitfa8646d.1-2+b2",
      "licenses": [
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "LGPL-2.1-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/librtmp1@2.4%2B20151223.gitfa8646d.1-2%2Bb2?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:041fa36e7b553df7512e26cdd7928c7b0d6bd791c9548f15bb7cd65e1bf263dc"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:5681027ac9bb5e47b5b9e1164dbd199959488b99838037e2ebc3ade3250ff736"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "librtmp1@2.4+20151223.gitfa8646d.1-2+b2"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "rtmpdump"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "2"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "2.4+20151223.gitfa8646d.1"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libsasl2-2@2.1.28%2Bdfsg-10?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Debian Cyrus Team <team+cyrus@tracker.debian.org>"
      },
      "name": "libsasl2-2",
      "version": "2.1.28+dfsg-10",
      "licenses": [
        {
          "license": {
            "name": "BSD-4-Clause"
          }
        },
        {
          "license": {
            "name": "OpenSSL"
          }
        },
        {
          "license": {
            "name": "SSLeay"
          }
        },
        {
          "license": {
            "name": "BSD-3-Clause"
          }
        },
        {
          "license": {
            "name": "BSD-2-Clause"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-only"
          }
        },
        {
          "license": {
            "name": "BSD-4-Clause-UC"
          }
        },
        {
          "license": {
            "name": "RSA-MD"
          }
        },
        {
          "license": {
            "name": "BSD-4-clause-KTH"
          }
        },
        {
          "license": {
            "name": "text://BSD-4-clause and IBM-as-is"
          }
        },
        {
          "license": {
            "name": "BSD-3-clause-JANET"
          }
        },
        {
          "license": {
            "name": "BSD-3-clause-PADL"
          }
        },
        {
          "license": {
            "name": "MIT-OpenVision"
          }
        },
        {
          "license": {
            "name": "OpenLDAP"
          }
        },
        {
          "license": {
            "name": "FSFULLR"
          }
        },
        {
          "license": {
            "name": "MIT-CMU"
          }
        },
        {
          "license": {
            "name": "MIT-Export"
          }
        },
        {
          "license": {
            "name": "BSD-2.2-clause"
          }
        },
        {
          "license": {
            "name": "text://IBM-as-is"
          }
        }
      ],
      "purl": "pkg:deb/debian/libsasl2-2@2.1.28%2Bdfsg-10?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:041fa36e7b553df7512e26cdd7928c7b0d6bd791c9548f15bb7cd65e1bf263dc"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:5681027ac9bb5e47b5b9e1164dbd199959488b99838037e2ebc3ade3250ff736"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libsasl2-2@2.1.28+dfsg-10"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "cyrus-sasl2"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "10"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "2.1.28+dfsg"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libsasl2-modules-db@2.1.28%2Bdfsg-10?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Debian Cyrus Team <team+cyrus@tracker.debian.org>"
      },
      "name": "libsasl2-modules-db",
      "version": "2.1.28+dfsg-10",
      "licenses": [
        {
          "license": {
            "name": "BSD-4-Clause"
          }
        },
        {
          "license": {
            "name": "OpenSSL"
          }
        },
        {
          "license": {
            "name": "SSLeay"
          }
        },
        {
          "license": {
            "name": "BSD-3-Clause"
          }
        },
        {
          "license": {
            "name": "BSD-2-Clause"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-only"
          }
        },
        {
          "license": {
            "name": "BSD-4-Clause-UC"
          }
        },
        {
          "license": {
            "name": "RSA-MD"
          }
        },
        {
          "license": {
            "name": "BSD-4-clause-KTH"
          }
        },
        {
          "license": {
            "name": "text://BSD-4-clause and IBM-as-is"
          }
        },
        {
          "license": {
            "name": "BSD-3-clause-JANET"
          }
        },
        {
          "license": {
            "name": "BSD-3-clause-PADL"
          }
        },
        {
          "license": {
            "name": "MIT-OpenVision"
          }
        },
        {
          "license": {
            "name": "OpenLDAP"
          }
        },
        {
          "license": {
            "name": "FSFULLR"
          }
        },
        {
          "license": {
            "name": "MIT-CMU"
          }
        },
        {
          "license": {
            "name": "MIT-Export"
          }
        },
        {
          "license": {
            "name": "BSD-2.2-clause"
          }
        },
        {
          "license": {
            "name": "text://IBM-as-is"
          }
        }
      ],
      "purl": "pkg:deb/debian/libsasl2-modules-db@2.1.28%2Bdfsg-10?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:041fa36e7b553df7512e26cdd7928c7b0d6bd791c9548f15bb7cd65e1bf263dc"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:5681027ac9bb5e47b5b9e1164dbd199959488b99838037e2ebc3ade3250ff736"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libsasl2-modules-db@2.1.28+dfsg-10"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "cyrus-sasl2"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "10"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "2.1.28+dfsg"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libsasl2-modules@2.1.28%2Bdfsg-10?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Debian Cyrus Team <team+cyrus@tracker.debian.org>"
      },
      "name": "libsasl2-modules",
      "version": "2.1.28+dfsg-10",
      "licenses": [
        {
          "license": {
            "name": "BSD-4-Clause"
          }
        },
        {
          "license": {
            "name": "OpenSSL"
          }
        },
        {
          "license": {
            "name": "SSLeay"
          }
        },
        {
          "license": {
            "name": "BSD-3-Clause"
          }
        },
        {
          "license": {
            "name": "BSD-2-Clause"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-only"
          }
        },
        {
          "license": {
            "name": "BSD-4-Clause-UC"
          }
        },
        {
          "license": {
            "name": "RSA-MD"
          }
        },
        {
          "license": {
            "name": "BSD-4-clause-KTH"
          }
        },
        {
          "license": {
            "name": "text://BSD-4-clause and IBM-as-is"
          }
        },
        {
          "license": {
            "name": "BSD-3-clause-JANET"
          }
        },
        {
          "license": {
            "name": "BSD-3-clause-PADL"
          }
        },
        {
          "license": {
            "name": "MIT-OpenVision"
          }
        },
        {
          "license": {
            "name": "OpenLDAP"
          }
        },
        {
          "license": {
            "name": "FSFULLR"
          }
        },
        {
          "license": {
            "name": "MIT-CMU"
          }
        },
        {
          "license": {
            "name": "MIT-Export"
          }
        },
        {
          "license": {
            "name": "BSD-2.2-clause"
          }
        },
        {
          "license": {
            "name": "text://IBM-as-is"
          }
        }
      ],
      "purl": "pkg:deb/debian/libsasl2-modules@2.1.28%2Bdfsg-10?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:041fa36e7b553df7512e26cdd7928c7b0d6bd791c9548f15bb7cd65e1bf263dc"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:5681027ac9bb5e47b5b9e1164dbd199959488b99838037e2ebc3ade3250ff736"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libsasl2-modules@2.1.28+dfsg-10"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "cyrus-sasl2"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "10"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "2.1.28+dfsg"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libseccomp2@2.5.4-1%2Bdeb12u1?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Kees Cook <kees@debian.org>"
      },
      "name": "libseccomp2",
      "version": "2.5.4-1+deb12u1",
      "licenses": [
        {
          "license": {
            "name": "LGPL-2.1-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/libseccomp2@2.5.4-1%2Bdeb12u1?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libseccomp2@2.5.4-1+deb12u1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "libseccomp"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "1+deb12u1"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "2.5.4"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libselinux1@3.4-1%2Bb6?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Debian SELinux maintainers <selinux-devel@lists.alioth.debian.org>"
      },
      "name": "libselinux1",
      "version": "3.4-1+b6",
      "licenses": [
        {
          "license": {
            "name": "LGPL-2.1-only"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/libselinux1@3.4-1%2Bb6?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libselinux1@3.4-1+b6"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "libselinux"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "1"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "3.4"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libsemanage-common@3.4-1?arch=all&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Debian SELinux maintainers <selinux-devel@lists.alioth.debian.org>"
      },
      "name": "libsemanage-common",
      "version": "3.4-1",
      "licenses": [
        {
          "license": {
            "name": "LGPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        }
      ],
      "purl": "pkg:deb/debian/libsemanage-common@3.4-1?arch=all&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libsemanage-common@3.4-1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "libsemanage"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "1"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "3.4"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libsemanage2@3.4-1%2Bb5?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Debian SELinux maintainers <selinux-devel@lists.alioth.debian.org>"
      },
      "name": "libsemanage2",
      "version": "3.4-1+b5",
      "licenses": [
        {
          "license": {
            "name": "LGPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        }
      ],
      "purl": "pkg:deb/debian/libsemanage2@3.4-1%2Bb5?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libsemanage2@3.4-1+b5"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "libsemanage"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "1"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "3.4"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libsepol2@3.4-2.1?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Debian SELinux maintainers <selinux-devel@lists.alioth.debian.org>"
      },
      "name": "libsepol2",
      "version": "3.4-2.1",
      "licenses": [
        {
          "license": {
            "name": "LGPL-2.1-or-later"
          }
        },
        {
          "license": {
            "name": "LGPL-2.1-only"
          }
        },
        {
          "license": {
            "name": "Zlib"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        }
      ],
      "purl": "pkg:deb/debian/libsepol2@3.4-2.1?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libsepol2@3.4-2.1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "libsepol"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "2.1"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "3.4"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libsmartcols1@2.38.1-5%2Bdeb12u3?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "util-linux packagers <util-linux@packages.debian.org>"
      },
      "name": "libsmartcols1",
      "version": "2.38.1-5+deb12u3",
      "licenses": [
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-or-later"
          }
        },
        {
          "license": {
            "name": "public-domain"
          }
        },
        {
          "license": {
            "name": "BSD-4-Clause"
          }
        },
        {
          "license": {
            "name": "MIT"
          }
        },
        {
          "license": {
            "name": "BSD-3-Clause"
          }
        },
        {
          "license": {
            "name": "BSLA"
          }
        },
        {
          "license": {
            "name": "LGPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "LGPL-2.1-or-later"
          }
        },
        {
          "license": {
            "name": "LGPL-3.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-only"
          }
        },
        {
          "license": {
            "name": "LGPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "LGPL-2.1-only"
          }
        },
        {
          "license": {
            "name": "LGPL-3.0-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/libsmartcols1@2.38.1-5%2Bdeb12u3?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libsmartcols1@2.38.1-5+deb12u3"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "util-linux"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "5+deb12u3"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "2.38.1"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libss2@1.47.0-2%2Bb2?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Theodore Y. Ts'o <tytso@mit.edu>"
      },
      "name": "libss2",
      "version": "1.47.0-2+b2",
      "licenses": [
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "LGPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "BSD-3-Clause"
          }
        },
        {
          "license": {
            "name": "Apache-2.0"
          }
        },
        {
          "license": {
            "name": "ISC"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "MIT-US-export"
          }
        },
        {
          "license": {
            "name": "Kazlib"
          }
        },
        {
          "license": {
            "name": "Latex2e"
          }
        },
        {
          "license": {
            "name": "GPL-2+ with Texinfo exception"
          }
        }
      ],
      "purl": "pkg:deb/debian/libss2@1.47.0-2%2Bb2?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libss2@1.47.0-2+b2"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "e2fsprogs"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "2"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "1.47.0"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libssh2-1@1.10.0-3%2Bdeb12u1?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Nicolas Mora <babelouest@debian.org>"
      },
      "name": "libssh2-1",
      "version": "1.10.0-3+deb12u1",
      "licenses": [
        {
          "license": {
            "name": "BSD-3-Clause"
          }
        }
      ],
      "purl": "pkg:deb/debian/libssh2-1@1.10.0-3%2Bdeb12u1?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:041fa36e7b553df7512e26cdd7928c7b0d6bd791c9548f15bb7cd65e1bf263dc"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:5681027ac9bb5e47b5b9e1164dbd199959488b99838037e2ebc3ade3250ff736"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libssh2-1@1.10.0-3+deb12u1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "libssh2"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "3+deb12u1"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "1.10.0"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libssl3@3.0.22-1~deb12u1?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Debian OpenSSL Team <pkg-openssl-devel@alioth-lists.debian.net>"
      },
      "name": "libssl3",
      "version": "3.0.22-1~deb12u1",
      "licenses": [
        {
          "license": {
            "name": "Apache-2.0"
          }
        },
        {
          "license": {
            "name": "Artistic-2.0"
          }
        },
        {
          "license": {
            "name": "GPL-1.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-1.0-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/libssl3@3.0.22-1~deb12u1?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:041fa36e7b553df7512e26cdd7928c7b0d6bd791c9548f15bb7cd65e1bf263dc"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:5681027ac9bb5e47b5b9e1164dbd199959488b99838037e2ebc3ade3250ff736"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libssl3@3.0.22-1~deb12u1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "openssl"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "1~deb12u1"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "3.0.22"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libstdc%2B%2B6@12.2.0-14%2Bdeb12u1?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Debian GCC Maintainers <debian-gcc@lists.debian.org>"
      },
      "name": "libstdc++6",
      "version": "12.2.0-14+deb12u1",
      "purl": "pkg:deb/debian/libstdc%2B%2B6@12.2.0-14%2Bdeb12u1?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libstdc++6@12.2.0-14+deb12u1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "gcc-12"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "14+deb12u1"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "12.2.0"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libsystemd0@252.39-1~deb12u2?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Debian systemd Maintainers <pkg-systemd-maintainers@lists.alioth.debian.org>"
      },
      "name": "libsystemd0",
      "version": "252.39-1~deb12u2",
      "licenses": [
        {
          "license": {
            "name": "LGPL-2.1-or-later"
          }
        },
        {
          "license": {
            "name": "CC0-1.0"
          }
        },
        {
          "license": {
            "name": "GPL-2 with Linux-syscall-note exception"
          }
        },
        {
          "license": {
            "name": "MIT"
          }
        },
        {
          "license": {
            "name": "public-domain"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "LGPL-2.1-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/libsystemd0@252.39-1~deb12u2?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libsystemd0@252.39-1~deb12u2"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "systemd"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "1~deb12u2"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "252.39"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libtasn1-6@4.19.0-2%2Bdeb12u1?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Debian GnuTLS Maintainers <pkg-gnutls-maint@lists.alioth.debian.org>"
      },
      "name": "libtasn1-6",
      "version": "4.19.0-2+deb12u1",
      "licenses": [
        {
          "license": {
            "name": "LGPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "LGPL-2.1-only"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-only"
          }
        },
        {
          "license": {
            "name": "GFDL-1.3-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/libtasn1-6@4.19.0-2%2Bdeb12u1?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libtasn1-6@4.19.0-2+deb12u1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "libtasn1-6"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "2+deb12u1"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "4.19.0"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libtinfo6@6.4-4?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Craig Small <csmall@debian.org>"
      },
      "name": "libtinfo6",
      "version": "6.4-4",
      "licenses": [
        {
          "license": {
            "name": "MIT/X11"
          }
        },
        {
          "license": {
            "name": "X11"
          }
        },
        {
          "license": {
            "name": "BSD-3-Clause"
          }
        }
      ],
      "purl": "pkg:deb/debian/libtinfo6@6.4-4?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libtinfo6@6.4-4"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "ncurses"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "4"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "6.4"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libudev1@252.39-1~deb12u2?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Debian systemd Maintainers <pkg-systemd-maintainers@lists.alioth.debian.org>"
      },
      "name": "libudev1",
      "version": "252.39-1~deb12u2",
      "licenses": [
        {
          "license": {
            "name": "LGPL-2.1-or-later"
          }
        },
        {
          "license": {
            "name": "CC0-1.0"
          }
        },
        {
          "license": {
            "name": "GPL-2 with Linux-syscall-note exception"
          }
        },
        {
          "license": {
            "name": "MIT"
          }
        },
        {
          "license": {
            "name": "public-domain"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "LGPL-2.1-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/libudev1@252.39-1~deb12u2?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libudev1@252.39-1~deb12u2"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "systemd"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "1~deb12u2"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "252.39"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libunistring2@1.0-2?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Jörg Frings-Fürst <debian@jff.email>"
      },
      "name": "libunistring2",
      "version": "1.0-2",
      "licenses": [
        {
          "license": {
            "name": "LGPL-3.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "FreeSoftware"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-or-later"
          }
        },
        {
          "license": {
            "name": "GFDL-1.2-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-2+ with distribution exception"
          }
        },
        {
          "license": {
            "name": "MIT"
          }
        },
        {
          "license": {
            "name": "LGPL-3.0-only"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-only"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "GFDL-1.2-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/libunistring2@1.0-2?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libunistring2@1.0-2"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "libunistring"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "2"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "1.0"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libuuid1@2.38.1-5%2Bdeb12u3?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "util-linux packagers <util-linux@packages.debian.org>"
      },
      "name": "libuuid1",
      "version": "2.38.1-5+deb12u3",
      "licenses": [
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-or-later"
          }
        },
        {
          "license": {
            "name": "public-domain"
          }
        },
        {
          "license": {
            "name": "BSD-4-Clause"
          }
        },
        {
          "license": {
            "name": "MIT"
          }
        },
        {
          "license": {
            "name": "BSD-3-Clause"
          }
        },
        {
          "license": {
            "name": "BSLA"
          }
        },
        {
          "license": {
            "name": "LGPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "LGPL-2.1-or-later"
          }
        },
        {
          "license": {
            "name": "LGPL-3.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-only"
          }
        },
        {
          "license": {
            "name": "LGPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "LGPL-2.1-only"
          }
        },
        {
          "license": {
            "name": "LGPL-3.0-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/libuuid1@2.38.1-5%2Bdeb12u3?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libuuid1@2.38.1-5+deb12u3"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "util-linux"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "5+deb12u3"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "2.38.1"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libxxhash0@0.8.1-1?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Josue Ortega <josue@debian.org>"
      },
      "name": "libxxhash0",
      "version": "0.8.1-1",
      "licenses": [
        {
          "license": {
            "name": "BSD-2-Clause"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/libxxhash0@0.8.1-1?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libxxhash0@0.8.1-1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "xxhash"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "1"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "0.8.1"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libzstd1@1.5.4%2Bdfsg2-5?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "RPM packaging team <team+pkg-rpm@tracker.debian.org>"
      },
      "name": "libzstd1",
      "version": "1.5.4+dfsg2-5",
      "licenses": [
        {
          "license": {
            "name": "BSD-3-Clause"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "Zlib"
          }
        },
        {
          "license": {
            "name": "MIT"
          }
        }
      ],
      "purl": "pkg:deb/debian/libzstd1@1.5.4%2Bdfsg2-5?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libzstd1@1.5.4+dfsg2-5"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "libzstd"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "5"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "1.5.4+dfsg2"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/login@4.13%2Bdfsg1-1%2Bdeb12u2?arch=amd64&distro=debian-12.15&epoch=1",
      "type": "library",
      "supplier": {
        "name": "Shadow package maintainers <pkg-shadow-devel@lists.alioth.debian.org>"
      },
      "name": "login",
      "version": "1:4.13+dfsg1-1+deb12u2",
      "licenses": [
        {
          "license": {
            "name": "BSD-3-Clause"
          }
        },
        {
          "license": {
            "name": "GPL-1.0-only"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "public-domain"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/login@4.13%2Bdfsg1-1%2Bdeb12u2?arch=amd64&distro=debian-12.15&epoch=1",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "login@1:4.13+dfsg1-1+deb12u2"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcEpoch",
          "value": "1"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "shadow"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "1+deb12u2"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "4.13+dfsg1"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/logsave@1.47.0-2%2Bb2?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Theodore Y. Ts'o <tytso@mit.edu>"
      },
      "name": "logsave",
      "version": "1.47.0-2+b2",
      "licenses": [
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "LGPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "BSD-3-Clause"
          }
        },
        {
          "license": {
            "name": "Apache-2.0"
          }
        },
        {
          "license": {
            "name": "ISC"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "MIT-US-export"
          }
        },
        {
          "license": {
            "name": "Kazlib"
          }
        },
        {
          "license": {
            "name": "Latex2e"
          }
        },
        {
          "license": {
            "name": "GPL-2+ with Texinfo exception"
          }
        }
      ],
      "purl": "pkg:deb/debian/logsave@1.47.0-2%2Bb2?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "logsave@1.47.0-2+b2"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "e2fsprogs"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "2"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "1.47.0"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/mawk@1.3.4.20200120-3.1?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Boyuan Yang <byang@debian.org>"
      },
      "name": "mawk",
      "version": "1.3.4.20200120-3.1",
      "licenses": [
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "X11"
          }
        },
        {
          "license": {
            "name": "CC-BY-3.0"
          }
        }
      ],
      "purl": "pkg:deb/debian/mawk@1.3.4.20200120-3.1?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "mawk@1.3.4.20200120-3.1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "mawk"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "3.1"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "1.3.4.20200120"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/mount@2.38.1-5%2Bdeb12u3?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "util-linux packagers <util-linux@packages.debian.org>"
      },
      "name": "mount",
      "version": "2.38.1-5+deb12u3",
      "licenses": [
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-or-later"
          }
        },
        {
          "license": {
            "name": "public-domain"
          }
        },
        {
          "license": {
            "name": "BSD-4-Clause"
          }
        },
        {
          "license": {
            "name": "MIT"
          }
        },
        {
          "license": {
            "name": "BSD-3-Clause"
          }
        },
        {
          "license": {
            "name": "BSLA"
          }
        },
        {
          "license": {
            "name": "LGPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "LGPL-2.1-or-later"
          }
        },
        {
          "license": {
            "name": "LGPL-3.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-only"
          }
        },
        {
          "license": {
            "name": "LGPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "LGPL-2.1-only"
          }
        },
        {
          "license": {
            "name": "LGPL-3.0-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/mount@2.38.1-5%2Bdeb12u3?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "mount@2.38.1-5+deb12u3"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "util-linux"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "5+deb12u3"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "2.38.1"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/ncurses-base@6.4-4?arch=all&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Craig Small <csmall@debian.org>"
      },
      "name": "ncurses-base",
      "version": "6.4-4",
      "licenses": [
        {
          "license": {
            "name": "MIT/X11"
          }
        },
        {
          "license": {
            "name": "X11"
          }
        },
        {
          "license": {
            "name": "BSD-3-Clause"
          }
        }
      ],
      "purl": "pkg:deb/debian/ncurses-base@6.4-4?arch=all&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "ncurses-base@6.4-4"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "ncurses"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "4"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "6.4"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/ncurses-bin@6.4-4?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Craig Small <csmall@debian.org>"
      },
      "name": "ncurses-bin",
      "version": "6.4-4",
      "licenses": [
        {
          "license": {
            "name": "MIT/X11"
          }
        },
        {
          "license": {
            "name": "X11"
          }
        },
        {
          "license": {
            "name": "BSD-3-Clause"
          }
        }
      ],
      "purl": "pkg:deb/debian/ncurses-bin@6.4-4?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "ncurses-bin@6.4-4"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "ncurses"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "4"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "6.4"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/openssl@3.0.22-1~deb12u1?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Debian OpenSSL Team <pkg-openssl-devel@alioth-lists.debian.net>"
      },
      "name": "openssl",
      "version": "3.0.22-1~deb12u1",
      "licenses": [
        {
          "license": {
            "name": "Apache-2.0"
          }
        },
        {
          "license": {
            "name": "Artistic-2.0"
          }
        },
        {
          "license": {
            "name": "GPL-1.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-1.0-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/openssl@3.0.22-1~deb12u1?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:041fa36e7b553df7512e26cdd7928c7b0d6bd791c9548f15bb7cd65e1bf263dc"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:5681027ac9bb5e47b5b9e1164dbd199959488b99838037e2ebc3ade3250ff736"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "openssl@3.0.22-1~deb12u1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "openssl"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "1~deb12u1"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "3.0.22"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/passwd@4.13%2Bdfsg1-1%2Bdeb12u2?arch=amd64&distro=debian-12.15&epoch=1",
      "type": "library",
      "supplier": {
        "name": "Shadow package maintainers <pkg-shadow-devel@lists.alioth.debian.org>"
      },
      "name": "passwd",
      "version": "1:4.13+dfsg1-1+deb12u2",
      "licenses": [
        {
          "license": {
            "name": "BSD-3-Clause"
          }
        },
        {
          "license": {
            "name": "GPL-1.0-only"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "public-domain"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/passwd@4.13%2Bdfsg1-1%2Bdeb12u2?arch=amd64&distro=debian-12.15&epoch=1",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "passwd@1:4.13+dfsg1-1+deb12u2"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcEpoch",
          "value": "1"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "shadow"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "1+deb12u2"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "4.13+dfsg1"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/perl-base@5.36.0-7%2Bdeb12u4?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Niko Tyni <ntyni@debian.org>"
      },
      "name": "perl-base",
      "version": "5.36.0-7+deb12u4",
      "licenses": [
        {
          "license": {
            "name": "GPL-1.0-or-later"
          }
        },
        {
          "license": {
            "name": "Artistic-2.0"
          }
        },
        {
          "license": {
            "name": "MIT"
          }
        },
        {
          "license": {
            "name": "REGCOMP"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-with-bison-exception+"
          }
        },
        {
          "license": {
            "name": "Unicode"
          }
        },
        {
          "license": {
            "name": "BZIP"
          }
        },
        {
          "license": {
            "name": "Zlib"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "RRA-KEEP-THIS-NOTICE"
          }
        },
        {
          "license": {
            "name": "BSD-3-clause-with-weird-numbering"
          }
        },
        {
          "license": {
            "name": "CC0-1.0"
          }
        },
        {
          "license": {
            "name": "TEXT-TABS"
          }
        },
        {
          "license": {
            "name": "BSD-4-clause-POWERDOG"
          }
        },
        {
          "license": {
            "name": "BSD-3-clause-GENERIC"
          }
        },
        {
          "license": {
            "name": "BSD-3-Clause"
          }
        },
        {
          "license": {
            "name": "SDBM-PUBLIC-DOMAIN"
          }
        },
        {
          "license": {
            "name": "DONT-CHANGE-THE-GPL"
          }
        },
        {
          "license": {
            "name": "Artistic-dist"
          }
        },
        {
          "license": {
            "name": "LGPL-2.1-only"
          }
        },
        {
          "license": {
            "name": "GPL-1.0-only"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "Artistic-2"
          }
        },
        {
          "license": {
            "name": "HSIEH-DERIVATIVE"
          }
        },
        {
          "license": {
            "name": "HSIEH-BSD"
          }
        }
      ],
      "purl": "pkg:deb/debian/perl-base@5.36.0-7%2Bdeb12u4?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "perl-base@5.36.0-7+deb12u4"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "perl"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "7+deb12u4"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "5.36.0"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/publicsuffix@20230209.2326-1?arch=all&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Daniel Kahn Gillmor <dkg@fifthhorseman.net>"
      },
      "name": "publicsuffix",
      "version": "20230209.2326-1",
      "licenses": [
        {
          "license": {
            "name": "MPL-2.0"
          }
        },
        {
          "license": {
            "name": "CC0-1.0"
          }
        }
      ],
      "purl": "pkg:deb/debian/publicsuffix@20230209.2326-1?arch=all&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:041fa36e7b553df7512e26cdd7928c7b0d6bd791c9548f15bb7cd65e1bf263dc"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:5681027ac9bb5e47b5b9e1164dbd199959488b99838037e2ebc3ade3250ff736"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "publicsuffix@20230209.2326-1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "publicsuffix"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "1"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "20230209.2326"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/sed@4.9-1%2Bdeb12u1?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Clint Adams <clint@debian.org>"
      },
      "name": "sed",
      "version": "4.9-1+deb12u1",
      "licenses": [
        {
          "license": {
            "name": "GPL-3.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-only"
          }
        },
        {
          "license": {
            "name": "X11"
          }
        },
        {
          "license": {
            "name": "GFDL-1.3-no-invariants-or-later"
          }
        },
        {
          "license": {
            "name": "GFDL-1.3-only"
          }
        },
        {
          "license": {
            "name": "ISC"
          }
        },
        {
          "license": {
            "name": "BSD-4-Clause-UC"
          }
        },
        {
          "license": {
            "name": "BSL-1"
          }
        },
        {
          "license": {
            "name": "pcre"
          }
        }
      ],
      "purl": "pkg:deb/debian/sed@4.9-1%2Bdeb12u1?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "sed@4.9-1+deb12u1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "sed"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "1+deb12u1"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "4.9"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/sysvinit-utils@3.06-4?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Debian sysvinit maintainers <debian-init-diversity@chiark.greenend.org.uk>"
      },
      "name": "sysvinit-utils",
      "version": "3.06-4",
      "licenses": [
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-only"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/sysvinit-utils@3.06-4?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "sysvinit-utils@3.06-4"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "sysvinit"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "4"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "3.06"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/tar@1.34%2Bdfsg-1.2%2Bdeb12u1?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Janos Lenart <ocsi@debian.org>"
      },
      "name": "tar",
      "version": "1.34+dfsg-1.2+deb12u1",
      "licenses": [
        {
          "license": {
            "name": "GPL-3.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-only"
          }
        },
        {
          "license": {
            "name": "GPL-3+ with Bison exception"
          }
        },
        {
          "license": {
            "name": "LGPL-3.0-or-later"
          }
        },
        {
          "license": {
            "name": "LGPL-3.0-only"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/tar@1.34%2Bdfsg-1.2%2Bdeb12u1?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "tar@1.34+dfsg-1.2+deb12u1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "tar"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "1.2+deb12u1"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "1.34+dfsg"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/tzdata@2026c-0%2Bdeb12u1?arch=all&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "GNU Libc Maintainers <debian-glibc@lists.debian.org>"
      },
      "name": "tzdata",
      "version": "2026c-0+deb12u1",
      "licenses": [
        {
          "license": {
            "name": "public-domain"
          }
        }
      ],
      "purl": "pkg:deb/debian/tzdata@2026c-0%2Bdeb12u1?arch=all&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "tzdata@2026c-0+deb12u1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "tzdata"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "0+deb12u1"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "2026c"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/usr-is-merged@37~deb12u1?arch=all&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "Marco d'Itri <md@linux.it>"
      },
      "name": "usr-is-merged",
      "version": "37~deb12u1",
      "licenses": [
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/usr-is-merged@37~deb12u1?arch=all&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "usr-is-merged@37~deb12u1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "usrmerge"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "37~deb12u1"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/util-linux-extra@2.38.1-5%2Bdeb12u3?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "util-linux packagers <util-linux@packages.debian.org>"
      },
      "name": "util-linux-extra",
      "version": "2.38.1-5+deb12u3",
      "licenses": [
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-or-later"
          }
        },
        {
          "license": {
            "name": "public-domain"
          }
        },
        {
          "license": {
            "name": "BSD-4-Clause"
          }
        },
        {
          "license": {
            "name": "MIT"
          }
        },
        {
          "license": {
            "name": "BSD-3-Clause"
          }
        },
        {
          "license": {
            "name": "BSLA"
          }
        },
        {
          "license": {
            "name": "LGPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "LGPL-2.1-or-later"
          }
        },
        {
          "license": {
            "name": "LGPL-3.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-only"
          }
        },
        {
          "license": {
            "name": "LGPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "LGPL-2.1-only"
          }
        },
        {
          "license": {
            "name": "LGPL-3.0-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/util-linux-extra@2.38.1-5%2Bdeb12u3?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "util-linux-extra@2.38.1-5+deb12u3"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "util-linux"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "5+deb12u3"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "2.38.1"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/util-linux@2.38.1-5%2Bdeb12u3?arch=amd64&distro=debian-12.15",
      "type": "library",
      "supplier": {
        "name": "util-linux packagers <util-linux@packages.debian.org>"
      },
      "name": "util-linux",
      "version": "2.38.1-5+deb12u3",
      "licenses": [
        {
          "license": {
            "name": "GPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-or-later"
          }
        },
        {
          "license": {
            "name": "public-domain"
          }
        },
        {
          "license": {
            "name": "BSD-4-Clause"
          }
        },
        {
          "license": {
            "name": "MIT"
          }
        },
        {
          "license": {
            "name": "BSD-3-Clause"
          }
        },
        {
          "license": {
            "name": "BSLA"
          }
        },
        {
          "license": {
            "name": "LGPL-2.0-or-later"
          }
        },
        {
          "license": {
            "name": "LGPL-2.1-or-later"
          }
        },
        {
          "license": {
            "name": "LGPL-3.0-or-later"
          }
        },
        {
          "license": {
            "name": "GPL-3.0-only"
          }
        },
        {
          "license": {
            "name": "LGPL-2.0-only"
          }
        },
        {
          "license": {
            "name": "LGPL-2.1-only"
          }
        },
        {
          "license": {
            "name": "LGPL-3.0-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/util-linux@2.38.1-5%2Bdeb12u3?arch=amd64&distro=debian-12.15",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "util-linux@2.38.1-5+deb12u3"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "util-linux"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "5+deb12u3"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "2.38.1"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/zlib1g@1.2.13.dfsg-1?arch=amd64&distro=debian-12.15&epoch=1",
      "type": "library",
      "supplier": {
        "name": "Mark Brown <broonie@debian.org>"
      },
      "name": "zlib1g",
      "version": "1:1.2.13.dfsg-1",
      "licenses": [
        {
          "license": {
            "name": "Zlib"
          }
        }
      ],
      "purl": "pkg:deb/debian/zlib1g@1.2.13.dfsg-1?arch=amd64&distro=debian-12.15&epoch=1",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9b35de7893378218e365c34c2c735fb0032a859112fb7345ca8ea73f9aa1db70"
        },
        {
          "name": "aquasecurity:trivy:LayerDigest",
          "value": "sha256:11422d7ca1a44390a32bd8d8d9dc5946b4d053b3bbd9507d682e35584ba84a26"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "zlib1g@1:1.2.13.dfsg-1"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcEpoch",
          "value": "1"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "zlib"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "1"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "1.2.13.dfsg"
        }
      ]
    }
  ],
  "dependencies": [
    {
      "ref": "157d1c05-2b49-4cd7-b32d-47b79ca3b8a1",
      "dependsOn": [
        "pkg:cargo/stoa-gateway@0.9.25"
      ]
    },
    {
      "ref": "e83fff54-c213-4eb4-bff9-ecae09e3e054",
      "dependsOn": [
        "157d1c05-2b49-4cd7-b32d-47b79ca3b8a1",
        "f62f0ba9-863c-4578-8673-8faa46f5ae12"
      ]
    },
    {
      "ref": "f62f0ba9-863c-4578-8673-8faa46f5ae12",
      "dependsOn": [
        "pkg:deb/debian/apt@2.6.1?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/base-passwd@3.6.1?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/bash@5.2.15-2%2Bb13?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/bsdutils@2.38.1-5%2Bdeb12u3?arch=amd64&distro=debian-12.15&epoch=1",
        "pkg:deb/debian/ca-certificates@20250419~deb12u2?arch=all&distro=debian-12.15",
        "pkg:deb/debian/coreutils@9.1-1?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/curl@7.88.1-10%2Bdeb12u15?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/dash@0.5.12-2?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/diffutils@3.8-4?arch=amd64&distro=debian-12.15&epoch=1",
        "pkg:deb/debian/e2fsprogs@1.47.0-2%2Bb2?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/findutils@4.9.0-4?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/grep@3.8-5?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/gzip@1.12-1?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/hostname@3.23%2Bnmu1?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/init-system-helpers@1.65.2%2Bdeb12u1?arch=all&distro=debian-12.15",
        "pkg:deb/debian/krb5-locales@1.20.1-2%2Bdeb12u5?arch=all&distro=debian-12.15",
        "pkg:deb/debian/libacl1@2.3.1-3?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libattr1@2.5.1-4?arch=amd64&distro=debian-12.15&epoch=1",
        "pkg:deb/debian/libc-bin@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libext2fs2@1.47.0-2%2Bb2?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libldap-common@2.5.13%2Bdfsg-5?arch=all&distro=debian-12.15",
        "pkg:deb/debian/libmd0@1.0.4-2?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libmount1@2.38.1-5%2Bdeb12u3?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libpam-modules-bin@1.5.2-6%2Bdeb12u2?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libpam-runtime@1.5.2-6%2Bdeb12u2?arch=all&distro=debian-12.15",
        "pkg:deb/debian/libsasl2-modules@2.1.28%2Bdfsg-10?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libss2@1.47.0-2%2Bb2?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libtinfo6@6.4-4?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libuuid1@2.38.1-5%2Bdeb12u3?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/login@4.13%2Bdfsg1-1%2Bdeb12u2?arch=amd64&distro=debian-12.15&epoch=1",
        "pkg:deb/debian/mawk@1.3.4.20200120-3.1?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/mount@2.38.1-5%2Bdeb12u3?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/ncurses-base@6.4-4?arch=all&distro=debian-12.15",
        "pkg:deb/debian/ncurses-bin@6.4-4?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/perl-base@5.36.0-7%2Bdeb12u4?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/publicsuffix@20230209.2326-1?arch=all&distro=debian-12.15",
        "pkg:deb/debian/sed@4.9-1%2Bdeb12u1?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/sysvinit-utils@3.06-4?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/tzdata@2026c-0%2Bdeb12u1?arch=all&distro=debian-12.15",
        "pkg:deb/debian/util-linux@2.38.1-5%2Bdeb12u3?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:cargo/ahash@0.8.12",
      "dependsOn": [
        "pkg:cargo/cfg-if@1.0.5",
        "pkg:cargo/getrandom@0.3.4",
        "pkg:cargo/once_cell@1.21.4",
        "pkg:cargo/serde@1.0.229",
        "pkg:cargo/zerocopy@0.8.63"
      ]
    },
    {
      "ref": "pkg:cargo/aho-corasick@1.1.5",
      "dependsOn": [
        "pkg:cargo/memchr@2.8.3"
      ]
    },
    {
      "ref": "pkg:cargo/anyhow@1.0.104",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/arc-swap@1.9.3",
      "dependsOn": [
        "pkg:cargo/rustversion@1.0.23"
      ]
    },
    {
      "ref": "pkg:cargo/async-lock@3.4.2",
      "dependsOn": [
        "pkg:cargo/event-listener-strategy@0.5.4",
        "pkg:cargo/event-listener@5.4.2",
        "pkg:cargo/pin-project-lite@0.2.17"
      ]
    },
    {
      "ref": "pkg:cargo/async-stream@0.3.6",
      "dependsOn": [
        "pkg:cargo/futures-core@0.3.34",
        "pkg:cargo/pin-project-lite@0.2.17"
      ]
    },
    {
      "ref": "pkg:cargo/async-trait@0.1.92",
      "dependsOn": [
        "pkg:cargo/proc-macro2@1.0.107",
        "pkg:cargo/quote@1.0.47",
        "pkg:cargo/syn@3.0.9"
      ]
    },
    {
      "ref": "pkg:cargo/atomic-waker@1.1.2",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/axum-core@0.4.5",
      "dependsOn": [
        "pkg:cargo/async-trait@0.1.92",
        "pkg:cargo/bytes@1.12.1",
        "pkg:cargo/futures-util@0.3.34",
        "pkg:cargo/http-body-util@0.1.5",
        "pkg:cargo/http-body@1.1.0",
        "pkg:cargo/http@1.5.0",
        "pkg:cargo/mime@0.3.17",
        "pkg:cargo/pin-project-lite@0.2.17",
        "pkg:cargo/rustversion@1.0.23",
        "pkg:cargo/sync_wrapper@1.0.2",
        "pkg:cargo/tower-layer@0.3.3",
        "pkg:cargo/tower-service@0.3.3",
        "pkg:cargo/tracing@0.1.44"
      ]
    },
    {
      "ref": "pkg:cargo/axum@0.7.9",
      "dependsOn": [
        "pkg:cargo/async-trait@0.1.92",
        "pkg:cargo/axum-core@0.4.5",
        "pkg:cargo/base64@0.22.1",
        "pkg:cargo/bytes@1.12.1",
        "pkg:cargo/futures-util@0.3.34",
        "pkg:cargo/http-body-util@0.1.5",
        "pkg:cargo/http-body@1.1.0",
        "pkg:cargo/http@1.5.0",
        "pkg:cargo/hyper-util@0.1.21",
        "pkg:cargo/hyper@1.12.0",
        "pkg:cargo/itoa@1.0.18",
        "pkg:cargo/matchit@0.7.3",
        "pkg:cargo/memchr@2.8.3",
        "pkg:cargo/mime@0.3.17",
        "pkg:cargo/percent-encoding@2.3.2",
        "pkg:cargo/pin-project-lite@0.2.17",
        "pkg:cargo/rustversion@1.0.23",
        "pkg:cargo/serde@1.0.229",
        "pkg:cargo/serde_json@1.0.154",
        "pkg:cargo/serde_path_to_error@0.1.20",
        "pkg:cargo/serde_urlencoded@0.7.1",
        "pkg:cargo/sha1@0.10.7",
        "pkg:cargo/sync_wrapper@1.0.2",
        "pkg:cargo/tokio-tungstenite@0.24.0",
        "pkg:cargo/tokio@1.54.0",
        "pkg:cargo/tower-layer@0.3.3",
        "pkg:cargo/tower-service@0.3.3",
        "pkg:cargo/tower@0.5.3",
        "pkg:cargo/tracing@0.1.44"
      ]
    },
    {
      "ref": "pkg:cargo/base16ct@0.2.0",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/base64@0.22.1",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/base64@0.23.1",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/base64ct@1.8.3",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/bincode@2.0.1",
      "dependsOn": [
        "pkg:cargo/serde@1.0.229",
        "pkg:cargo/unty@0.0.4"
      ]
    },
    {
      "ref": "pkg:cargo/bit-set@0.8.0",
      "dependsOn": [
        "pkg:cargo/bit-vec@0.8.0"
      ]
    },
    {
      "ref": "pkg:cargo/bit-vec@0.8.0",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/bitflags@2.13.2",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/block-buffer@0.10.4",
      "dependsOn": [
        "pkg:cargo/generic-array@0.14.9"
      ]
    },
    {
      "ref": "pkg:cargo/block-buffer@0.12.1",
      "dependsOn": [
        "pkg:cargo/hybrid-array@0.4.15"
      ]
    },
    {
      "ref": "pkg:cargo/borrow-or-share@0.2.4",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/bstr@1.13.1",
      "dependsOn": [
        "pkg:cargo/memchr@2.8.3",
        "pkg:cargo/serde_core@1.0.229"
      ]
    },
    {
      "ref": "pkg:cargo/bytecount@0.6.9",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/byteorder@1.5.0",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/bytes@1.12.1",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/cfg-if@1.0.5",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/chacha20@0.10.2",
      "dependsOn": [
        "pkg:cargo/cfg-if@1.0.5",
        "pkg:cargo/cpufeatures@0.3.1",
        "pkg:cargo/rand_core@0.10.1"
      ]
    },
    {
      "ref": "pkg:cargo/chrono-tz@0.10.4",
      "dependsOn": [
        "pkg:cargo/chrono@0.4.45",
        "pkg:cargo/phf@0.12.1"
      ]
    },
    {
      "ref": "pkg:cargo/chrono@0.4.45",
      "dependsOn": [
        "pkg:cargo/iana-time-zone@0.1.65",
        "pkg:cargo/num-traits@0.2.19",
        "pkg:cargo/serde@1.0.229"
      ]
    },
    {
      "ref": "pkg:cargo/const-oid@0.10.2",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/const-oid@0.9.6",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/cpufeatures@0.2.17",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/cpufeatures@0.3.1",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/crossbeam-channel@0.5.17",
      "dependsOn": [
        "pkg:cargo/crossbeam-utils@0.8.23"
      ]
    },
    {
      "ref": "pkg:cargo/crossbeam-epoch@0.9.21",
      "dependsOn": [
        "pkg:cargo/crossbeam-utils@0.8.23"
      ]
    },
    {
      "ref": "pkg:cargo/crossbeam-utils@0.8.23",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/crypto-bigint@0.5.5",
      "dependsOn": [
        "pkg:cargo/generic-array@0.14.9",
        "pkg:cargo/rand_core@0.6.4",
        "pkg:cargo/subtle@2.6.1",
        "pkg:cargo/zeroize@1.9.1"
      ]
    },
    {
      "ref": "pkg:cargo/crypto-common@0.1.6",
      "dependsOn": [
        "pkg:cargo/generic-array@0.14.9",
        "pkg:cargo/typenum@1.20.1"
      ]
    },
    {
      "ref": "pkg:cargo/crypto-common@0.2.2",
      "dependsOn": [
        "pkg:cargo/hybrid-array@0.4.15"
      ]
    },
    {
      "ref": "pkg:cargo/curve25519-dalek-derive@0.1.1",
      "dependsOn": [
        "pkg:cargo/proc-macro2@1.0.107",
        "pkg:cargo/quote@1.0.47",
        "pkg:cargo/syn@2.0.119"
      ]
    },
    {
      "ref": "pkg:cargo/curve25519-dalek@4.1.3",
      "dependsOn": [
        "pkg:cargo/cfg-if@1.0.5",
        "pkg:cargo/cpufeatures@0.2.17",
        "pkg:cargo/curve25519-dalek-derive@0.1.1",
        "pkg:cargo/digest@0.10.7",
        "pkg:cargo/subtle@2.6.1",
        "pkg:cargo/zeroize@1.9.1"
      ]
    },
    {
      "ref": "pkg:cargo/data-encoding@2.11.1",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/der@0.7.10",
      "dependsOn": [
        "pkg:cargo/const-oid@0.9.6",
        "pkg:cargo/pem-rfc7468@0.7.0",
        "pkg:cargo/zeroize@1.9.1"
      ]
    },
    {
      "ref": "pkg:cargo/deranged@0.5.9",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/digest@0.10.7",
      "dependsOn": [
        "pkg:cargo/block-buffer@0.10.4",
        "pkg:cargo/const-oid@0.9.6",
        "pkg:cargo/crypto-common@0.1.6",
        "pkg:cargo/subtle@2.6.1"
      ]
    },
    {
      "ref": "pkg:cargo/digest@0.11.3",
      "dependsOn": [
        "pkg:cargo/block-buffer@0.12.1",
        "pkg:cargo/const-oid@0.10.2",
        "pkg:cargo/crypto-common@0.2.2"
      ]
    },
    {
      "ref": "pkg:cargo/displaydoc@0.2.7",
      "dependsOn": [
        "pkg:cargo/proc-macro2@1.0.107",
        "pkg:cargo/quote@1.0.47",
        "pkg:cargo/syn@3.0.9"
      ]
    },
    {
      "ref": "pkg:cargo/ecdsa@0.16.9",
      "dependsOn": [
        "pkg:cargo/der@0.7.10",
        "pkg:cargo/digest@0.10.7",
        "pkg:cargo/elliptic-curve@0.13.8",
        "pkg:cargo/rfc6979@0.4.0",
        "pkg:cargo/signature@2.2.0",
        "pkg:cargo/spki@0.7.3"
      ]
    },
    {
      "ref": "pkg:cargo/ed25519-dalek@2.2.0",
      "dependsOn": [
        "pkg:cargo/curve25519-dalek@4.1.3",
        "pkg:cargo/ed25519@2.2.3",
        "pkg:cargo/serde@1.0.229",
        "pkg:cargo/sha2@0.10.9",
        "pkg:cargo/subtle@2.6.1",
        "pkg:cargo/zeroize@1.9.1"
      ]
    },
    {
      "ref": "pkg:cargo/ed25519@2.2.3",
      "dependsOn": [
        "pkg:cargo/pkcs8@0.10.2",
        "pkg:cargo/signature@2.2.0"
      ]
    },
    {
      "ref": "pkg:cargo/elliptic-curve@0.13.8",
      "dependsOn": [
        "pkg:cargo/base16ct@0.2.0",
        "pkg:cargo/crypto-bigint@0.5.5",
        "pkg:cargo/digest@0.10.7",
        "pkg:cargo/ff@0.13.1",
        "pkg:cargo/generic-array@0.14.9",
        "pkg:cargo/group@0.13.0",
        "pkg:cargo/hkdf@0.12.4",
        "pkg:cargo/pem-rfc7468@0.7.0",
        "pkg:cargo/pkcs8@0.10.2",
        "pkg:cargo/rand_core@0.6.4",
        "pkg:cargo/sec1@0.7.3",
        "pkg:cargo/subtle@2.6.1",
        "pkg:cargo/zeroize@1.9.1"
      ]
    },
    {
      "ref": "pkg:cargo/email_address@0.2.9",
      "dependsOn": [
        "pkg:cargo/serde@1.0.229"
      ]
    },
    {
      "ref": "pkg:cargo/equivalent@1.0.3",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/errno@0.3.14",
      "dependsOn": [
        "pkg:cargo/libc@0.2.191"
      ]
    },
    {
      "ref": "pkg:cargo/event-listener-strategy@0.5.4",
      "dependsOn": [
        "pkg:cargo/event-listener@5.4.2",
        "pkg:cargo/pin-project-lite@0.2.17"
      ]
    },
    {
      "ref": "pkg:cargo/event-listener@5.4.2",
      "dependsOn": [
        "pkg:cargo/parking@2.2.1",
        "pkg:cargo/pin-project-lite@0.2.17"
      ]
    },
    {
      "ref": "pkg:cargo/fancy-regex@0.14.0",
      "dependsOn": [
        "pkg:cargo/bit-set@0.8.0",
        "pkg:cargo/regex-automata@0.4.18",
        "pkg:cargo/regex-syntax@0.8.11"
      ]
    },
    {
      "ref": "pkg:cargo/fastrand@2.5.0",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/ff@0.13.1",
      "dependsOn": [
        "pkg:cargo/rand_core@0.6.4",
        "pkg:cargo/subtle@2.6.1"
      ]
    },
    {
      "ref": "pkg:cargo/figment@0.10.19",
      "dependsOn": [
        "pkg:cargo/parking_lot@0.12.5",
        "pkg:cargo/pear@0.2.9",
        "pkg:cargo/serde@1.0.229",
        "pkg:cargo/serde_yaml@0.9.34%2Bdeprecated",
        "pkg:cargo/tempfile@3.27.0",
        "pkg:cargo/uncased@0.9.10"
      ]
    },
    {
      "ref": "pkg:cargo/fluent-uri@0.3.2",
      "dependsOn": [
        "pkg:cargo/borrow-or-share@0.2.4",
        "pkg:cargo/ref-cast@1.0.27",
        "pkg:cargo/serde@1.0.229"
      ]
    },
    {
      "ref": "pkg:cargo/fnv@1.0.7",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/form_urlencoded@1.2.2",
      "dependsOn": [
        "pkg:cargo/percent-encoding@2.3.2"
      ]
    },
    {
      "ref": "pkg:cargo/fraction@0.15.4",
      "dependsOn": [
        "pkg:cargo/lazy_static@1.5.1",
        "pkg:cargo/num@0.4.3"
      ]
    },
    {
      "ref": "pkg:cargo/futures-channel@0.3.34",
      "dependsOn": [
        "pkg:cargo/futures-core@0.3.34",
        "pkg:cargo/futures-sink@0.3.34"
      ]
    },
    {
      "ref": "pkg:cargo/futures-core@0.3.34",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/futures-executor@0.3.34",
      "dependsOn": [
        "pkg:cargo/futures-core@0.3.34",
        "pkg:cargo/futures-task@0.3.34",
        "pkg:cargo/futures-util@0.3.34"
      ]
    },
    {
      "ref": "pkg:cargo/futures-io@0.3.34",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/futures-sink@0.3.34",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/futures-task@0.3.34",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/futures-util@0.3.34",
      "dependsOn": [
        "pkg:cargo/futures-channel@0.3.34",
        "pkg:cargo/futures-core@0.3.34",
        "pkg:cargo/futures-io@0.3.34",
        "pkg:cargo/futures-sink@0.3.34",
        "pkg:cargo/futures-task@0.3.34",
        "pkg:cargo/memchr@2.8.3",
        "pkg:cargo/pin-project-lite@0.2.17",
        "pkg:cargo/slab@0.4.12"
      ]
    },
    {
      "ref": "pkg:cargo/futures@0.3.34",
      "dependsOn": [
        "pkg:cargo/futures-channel@0.3.34",
        "pkg:cargo/futures-core@0.3.34",
        "pkg:cargo/futures-executor@0.3.34",
        "pkg:cargo/futures-io@0.3.34",
        "pkg:cargo/futures-sink@0.3.34",
        "pkg:cargo/futures-task@0.3.34",
        "pkg:cargo/futures-util@0.3.34"
      ]
    },
    {
      "ref": "pkg:cargo/generic-array@0.14.9",
      "dependsOn": [
        "pkg:cargo/typenum@1.20.1",
        "pkg:cargo/zeroize@1.9.1"
      ]
    },
    {
      "ref": "pkg:cargo/getrandom@0.2.17",
      "dependsOn": [
        "pkg:cargo/cfg-if@1.0.5",
        "pkg:cargo/libc@0.2.191"
      ]
    },
    {
      "ref": "pkg:cargo/getrandom@0.3.4",
      "dependsOn": [
        "pkg:cargo/cfg-if@1.0.5",
        "pkg:cargo/libc@0.2.191"
      ]
    },
    {
      "ref": "pkg:cargo/getrandom@0.4.3",
      "dependsOn": [
        "pkg:cargo/cfg-if@1.0.5",
        "pkg:cargo/libc@0.2.191",
        "pkg:cargo/rand_core@0.10.1"
      ]
    },
    {
      "ref": "pkg:cargo/glob@0.3.4",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/globset@0.4.20",
      "dependsOn": [
        "pkg:cargo/aho-corasick@1.1.5",
        "pkg:cargo/bstr@1.13.1",
        "pkg:cargo/regex-automata@0.4.18",
        "pkg:cargo/regex-syntax@0.8.11"
      ]
    },
    {
      "ref": "pkg:cargo/group@0.13.0",
      "dependsOn": [
        "pkg:cargo/ff@0.13.1",
        "pkg:cargo/rand_core@0.6.4",
        "pkg:cargo/subtle@2.6.1"
      ]
    },
    {
      "ref": "pkg:cargo/h2@0.4.20",
      "dependsOn": [
        "pkg:cargo/atomic-waker@1.1.2",
        "pkg:cargo/bytes@1.12.1",
        "pkg:cargo/fnv@1.0.7",
        "pkg:cargo/futures-core@0.3.34",
        "pkg:cargo/futures-sink@0.3.34",
        "pkg:cargo/http@1.5.0",
        "pkg:cargo/indexmap@2.14.2",
        "pkg:cargo/slab@0.4.12",
        "pkg:cargo/tokio-util@0.7.20",
        "pkg:cargo/tokio@1.54.0",
        "pkg:cargo/tracing@0.1.44"
      ]
    },
    {
      "ref": "pkg:cargo/hashbrown@0.12.3",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/hashbrown@0.17.1",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/hkdf@0.12.4",
      "dependsOn": [
        "pkg:cargo/hmac@0.12.1"
      ]
    },
    {
      "ref": "pkg:cargo/hmac@0.12.1",
      "dependsOn": [
        "pkg:cargo/digest@0.10.7"
      ]
    },
    {
      "ref": "pkg:cargo/hostname@0.4.2",
      "dependsOn": [
        "pkg:cargo/cfg-if@1.0.5",
        "pkg:cargo/libc@0.2.191"
      ]
    },
    {
      "ref": "pkg:cargo/http-body-util@0.1.5",
      "dependsOn": [
        "pkg:cargo/bytes@1.12.1",
        "pkg:cargo/futures-core@0.3.34",
        "pkg:cargo/http-body@1.1.0",
        "pkg:cargo/http@1.5.0",
        "pkg:cargo/pin-project-lite@0.2.17"
      ]
    },
    {
      "ref": "pkg:cargo/http-body@1.1.0",
      "dependsOn": [
        "pkg:cargo/bytes@1.12.1",
        "pkg:cargo/http@1.5.0"
      ]
    },
    {
      "ref": "pkg:cargo/http@1.5.0",
      "dependsOn": [
        "pkg:cargo/bytes@1.12.1",
        "pkg:cargo/itoa@1.0.18"
      ]
    },
    {
      "ref": "pkg:cargo/httparse@1.10.1",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/httpdate@1.0.3",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/hybrid-array@0.4.15",
      "dependsOn": [
        "pkg:cargo/typenum@1.20.1"
      ]
    },
    {
      "ref": "pkg:cargo/hyper-rustls@0.27.10",
      "dependsOn": [
        "pkg:cargo/http@1.5.0",
        "pkg:cargo/hyper-util@0.1.21",
        "pkg:cargo/hyper@1.12.0",
        "pkg:cargo/rustls@0.23.46",
        "pkg:cargo/tokio-rustls@0.26.6",
        "pkg:cargo/tokio@1.54.0",
        "pkg:cargo/tower-service@0.3.3",
        "pkg:cargo/webpki-roots@1.0.10"
      ]
    },
    {
      "ref": "pkg:cargo/hyper-timeout@0.5.2",
      "dependsOn": [
        "pkg:cargo/hyper-util@0.1.21",
        "pkg:cargo/hyper@1.12.0",
        "pkg:cargo/pin-project-lite@0.2.17",
        "pkg:cargo/tokio@1.54.0",
        "pkg:cargo/tower-service@0.3.3"
      ]
    },
    {
      "ref": "pkg:cargo/hyper-util@0.1.21",
      "dependsOn": [
        "pkg:cargo/base64@0.23.1",
        "pkg:cargo/bytes@1.12.1",
        "pkg:cargo/futures-channel@0.3.34",
        "pkg:cargo/futures-util@0.3.34",
        "pkg:cargo/http-body@1.1.0",
        "pkg:cargo/http@1.5.0",
        "pkg:cargo/httparse@1.10.1",
        "pkg:cargo/hyper@1.12.0",
        "pkg:cargo/ipnet@2.12.2",
        "pkg:cargo/libc@0.2.191",
        "pkg:cargo/percent-encoding@2.3.2",
        "pkg:cargo/pin-project-lite@0.2.17",
        "pkg:cargo/socket2@0.6.5",
        "pkg:cargo/tokio@1.54.0",
        "pkg:cargo/tower-service@0.3.3",
        "pkg:cargo/tracing@0.1.44"
      ]
    },
    {
      "ref": "pkg:cargo/hyper@1.12.0",
      "dependsOn": [
        "pkg:cargo/atomic-waker@1.1.2",
        "pkg:cargo/bytes@1.12.1",
        "pkg:cargo/futures-channel@0.3.34",
        "pkg:cargo/futures-core@0.3.34",
        "pkg:cargo/h2@0.4.20",
        "pkg:cargo/http-body@1.1.0",
        "pkg:cargo/http@1.5.0",
        "pkg:cargo/httparse@1.10.1",
        "pkg:cargo/httpdate@1.0.3",
        "pkg:cargo/itoa@1.0.18",
        "pkg:cargo/pin-project-lite@0.2.17",
        "pkg:cargo/smallvec@1.16.3",
        "pkg:cargo/tokio@1.54.0",
        "pkg:cargo/want@0.3.2"
      ]
    },
    {
      "ref": "pkg:cargo/iana-time-zone@0.1.65",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/icu_collections@2.3.0",
      "dependsOn": [
        "pkg:cargo/displaydoc@0.2.7",
        "pkg:cargo/potential_utf@0.1.6",
        "pkg:cargo/utf8_iter@1.0.4",
        "pkg:cargo/yoke@0.8.3",
        "pkg:cargo/zerofrom@0.1.8",
        "pkg:cargo/zerovec@0.11.8"
      ]
    },
    {
      "ref": "pkg:cargo/icu_locale_core@2.3.0",
      "dependsOn": [
        "pkg:cargo/displaydoc@0.2.7",
        "pkg:cargo/litemap@0.8.3",
        "pkg:cargo/tinystr@0.8.4",
        "pkg:cargo/writeable@0.6.4",
        "pkg:cargo/zerovec@0.11.8"
      ]
    },
    {
      "ref": "pkg:cargo/icu_normalizer@2.3.0",
      "dependsOn": [
        "pkg:cargo/icu_collections@2.3.0",
        "pkg:cargo/icu_normalizer_data@2.3.0",
        "pkg:cargo/icu_properties@2.3.0",
        "pkg:cargo/icu_provider@2.3.1",
        "pkg:cargo/smallvec@1.16.3",
        "pkg:cargo/zerovec@0.11.8"
      ]
    },
    {
      "ref": "pkg:cargo/icu_normalizer_data@2.3.0",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/icu_properties@2.3.0",
      "dependsOn": [
        "pkg:cargo/displaydoc@0.2.7",
        "pkg:cargo/icu_collections@2.3.0",
        "pkg:cargo/icu_locale_core@2.3.0",
        "pkg:cargo/icu_properties_data@2.3.0",
        "pkg:cargo/icu_provider@2.3.1",
        "pkg:cargo/zerotrie@0.2.5",
        "pkg:cargo/zerovec@0.11.8"
      ]
    },
    {
      "ref": "pkg:cargo/icu_properties_data@2.3.0",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/icu_provider@2.3.1",
      "dependsOn": [
        "pkg:cargo/displaydoc@0.2.7",
        "pkg:cargo/icu_locale_core@2.3.0",
        "pkg:cargo/writeable@0.6.4",
        "pkg:cargo/yoke@0.8.3",
        "pkg:cargo/zerofrom@0.1.8",
        "pkg:cargo/zerotrie@0.2.5",
        "pkg:cargo/zerovec@0.11.8"
      ]
    },
    {
      "ref": "pkg:cargo/idna@1.1.0",
      "dependsOn": [
        "pkg:cargo/idna_adapter@1.2.2",
        "pkg:cargo/smallvec@1.16.3",
        "pkg:cargo/utf8_iter@1.0.4"
      ]
    },
    {
      "ref": "pkg:cargo/idna_adapter@1.2.2",
      "dependsOn": [
        "pkg:cargo/icu_normalizer@2.3.0",
        "pkg:cargo/icu_properties@2.3.0"
      ]
    },
    {
      "ref": "pkg:cargo/indexmap@1.9.3",
      "dependsOn": [
        "pkg:cargo/hashbrown@0.12.3"
      ]
    },
    {
      "ref": "pkg:cargo/indexmap@2.14.2",
      "dependsOn": [
        "pkg:cargo/equivalent@1.0.3",
        "pkg:cargo/hashbrown@0.17.1",
        "pkg:cargo/serde_core@1.0.229"
      ]
    },
    {
      "ref": "pkg:cargo/inlinable_string@0.1.15",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/inotify-sys@0.1.8",
      "dependsOn": [
        "pkg:cargo/libc@0.2.191"
      ]
    },
    {
      "ref": "pkg:cargo/inotify@0.11.5",
      "dependsOn": [
        "pkg:cargo/bitflags@2.13.2",
        "pkg:cargo/inotify-sys@0.1.8",
        "pkg:cargo/libc@0.2.191"
      ]
    },
    {
      "ref": "pkg:cargo/ipnet@2.12.2",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/itoa@1.0.18",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/jsonschema@0.30.0",
      "dependsOn": [
        "pkg:cargo/ahash@0.8.12",
        "pkg:cargo/base64@0.22.1",
        "pkg:cargo/bytecount@0.6.9",
        "pkg:cargo/email_address@0.2.9",
        "pkg:cargo/fancy-regex@0.14.0",
        "pkg:cargo/fraction@0.15.4",
        "pkg:cargo/idna@1.1.0",
        "pkg:cargo/itoa@1.0.18",
        "pkg:cargo/num-cmp@0.1.0",
        "pkg:cargo/num-traits@0.2.19",
        "pkg:cargo/once_cell@1.21.4",
        "pkg:cargo/percent-encoding@2.3.2",
        "pkg:cargo/referencing@0.30.0",
        "pkg:cargo/regex-syntax@0.8.11",
        "pkg:cargo/regex@1.13.1",
        "pkg:cargo/serde@1.0.229",
        "pkg:cargo/serde_json@1.0.154",
        "pkg:cargo/uuid-simd@0.8.0"
      ]
    },
    {
      "ref": "pkg:cargo/jsonwebtoken@10.4.0",
      "dependsOn": [
        "pkg:cargo/base64@0.22.1",
        "pkg:cargo/ed25519-dalek@2.2.0",
        "pkg:cargo/hmac@0.12.1",
        "pkg:cargo/p256@0.13.2",
        "pkg:cargo/p384@0.13.1",
        "pkg:cargo/pem@3.0.6",
        "pkg:cargo/rand@0.8.8",
        "pkg:cargo/rsa@0.9.10",
        "pkg:cargo/serde@1.0.229",
        "pkg:cargo/serde_json@1.0.154",
        "pkg:cargo/sha2@0.10.9",
        "pkg:cargo/signature@2.2.0",
        "pkg:cargo/simple_asn1@0.6.4",
        "pkg:cargo/zeroize@1.9.1"
      ]
    },
    {
      "ref": "pkg:cargo/lazy_static@1.5.1",
      "dependsOn": [
        "pkg:cargo/spin@0.9.9"
      ]
    },
    {
      "ref": "pkg:cargo/libc@0.2.191",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/libm@0.2.16",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/linux-raw-sys@0.12.1",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/litemap@0.8.3",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/lock_api@0.4.14",
      "dependsOn": [
        "pkg:cargo/scopeguard@1.2.0"
      ]
    },
    {
      "ref": "pkg:cargo/log@0.4.34",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/lru-slab@0.1.3",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/matchers@0.2.0",
      "dependsOn": [
        "pkg:cargo/regex-automata@0.4.18"
      ]
    },
    {
      "ref": "pkg:cargo/matchit@0.7.3",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/memchr@2.8.3",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/mime@0.3.17",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/mio@1.2.4",
      "dependsOn": [
        "pkg:cargo/libc@0.2.191",
        "pkg:cargo/log@0.4.34"
      ]
    },
    {
      "ref": "pkg:cargo/moka@0.12.16",
      "dependsOn": [
        "pkg:cargo/async-lock@3.4.2",
        "pkg:cargo/crossbeam-channel@0.5.17",
        "pkg:cargo/crossbeam-epoch@0.9.21",
        "pkg:cargo/crossbeam-utils@0.8.23",
        "pkg:cargo/equivalent@1.0.3",
        "pkg:cargo/event-listener@5.4.2",
        "pkg:cargo/futures-util@0.3.34",
        "pkg:cargo/parking_lot@0.12.5",
        "pkg:cargo/portable-atomic@1.15.0",
        "pkg:cargo/smallvec@1.16.3",
        "pkg:cargo/tagptr@0.2.0",
        "pkg:cargo/uuid@1.28.0"
      ]
    },
    {
      "ref": "pkg:cargo/msvc_spectre_libs@0.1.3",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/notify-types@2.1.0",
      "dependsOn": [
        "pkg:cargo/bitflags@2.13.2"
      ]
    },
    {
      "ref": "pkg:cargo/notify@8.2.0",
      "dependsOn": [
        "pkg:cargo/inotify@0.11.5",
        "pkg:cargo/libc@0.2.191",
        "pkg:cargo/log@0.4.34",
        "pkg:cargo/mio@1.2.4",
        "pkg:cargo/notify-types@2.1.0",
        "pkg:cargo/walkdir@2.5.0"
      ]
    },
    {
      "ref": "pkg:cargo/nu-ansi-term@0.50.3",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/num-bigint-dig@0.8.6",
      "dependsOn": [
        "pkg:cargo/lazy_static@1.5.1",
        "pkg:cargo/libm@0.2.16",
        "pkg:cargo/num-integer@0.1.47",
        "pkg:cargo/num-iter@0.1.46",
        "pkg:cargo/num-traits@0.2.19",
        "pkg:cargo/rand@0.8.8",
        "pkg:cargo/smallvec@1.16.3",
        "pkg:cargo/zeroize@1.9.1"
      ]
    },
    {
      "ref": "pkg:cargo/num-bigint@0.4.8",
      "dependsOn": [
        "pkg:cargo/num-integer@0.1.47",
        "pkg:cargo/num-traits@0.2.19"
      ]
    },
    {
      "ref": "pkg:cargo/num-cmp@0.1.0",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/num-complex@0.4.6",
      "dependsOn": [
        "pkg:cargo/num-traits@0.2.19"
      ]
    },
    {
      "ref": "pkg:cargo/num-conv@0.2.2",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/num-integer@0.1.47",
      "dependsOn": [
        "pkg:cargo/num-traits@0.2.19"
      ]
    },
    {
      "ref": "pkg:cargo/num-iter@0.1.46",
      "dependsOn": [
        "pkg:cargo/num-integer@0.1.47",
        "pkg:cargo/num-traits@0.2.19"
      ]
    },
    {
      "ref": "pkg:cargo/num-rational@0.4.2",
      "dependsOn": [
        "pkg:cargo/num-bigint@0.4.8",
        "pkg:cargo/num-integer@0.1.47",
        "pkg:cargo/num-traits@0.2.19"
      ]
    },
    {
      "ref": "pkg:cargo/num-traits@0.2.19",
      "dependsOn": [
        "pkg:cargo/libm@0.2.16"
      ]
    },
    {
      "ref": "pkg:cargo/num@0.4.3",
      "dependsOn": [
        "pkg:cargo/num-bigint@0.4.8",
        "pkg:cargo/num-complex@0.4.6",
        "pkg:cargo/num-integer@0.1.47",
        "pkg:cargo/num-iter@0.1.46",
        "pkg:cargo/num-rational@0.4.2",
        "pkg:cargo/num-traits@0.2.19"
      ]
    },
    {
      "ref": "pkg:cargo/once_cell@1.21.4",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/opentelemetry-otlp@0.27.0",
      "dependsOn": [
        "pkg:cargo/async-trait@0.1.92",
        "pkg:cargo/futures-core@0.3.34",
        "pkg:cargo/http@1.5.0",
        "pkg:cargo/opentelemetry-proto@0.27.0",
        "pkg:cargo/opentelemetry@0.27.1",
        "pkg:cargo/opentelemetry_sdk@0.27.1",
        "pkg:cargo/prost@0.13.5",
        "pkg:cargo/thiserror@1.0.69",
        "pkg:cargo/tokio@1.54.0",
        "pkg:cargo/tonic@0.12.3"
      ]
    },
    {
      "ref": "pkg:cargo/opentelemetry-proto@0.27.0",
      "dependsOn": [
        "pkg:cargo/opentelemetry@0.27.1",
        "pkg:cargo/opentelemetry_sdk@0.27.1",
        "pkg:cargo/prost@0.13.5",
        "pkg:cargo/tonic@0.12.3"
      ]
    },
    {
      "ref": "pkg:cargo/opentelemetry@0.27.1",
      "dependsOn": [
        "pkg:cargo/futures-core@0.3.34",
        "pkg:cargo/futures-sink@0.3.34",
        "pkg:cargo/pin-project-lite@0.2.17",
        "pkg:cargo/thiserror@1.0.69",
        "pkg:cargo/tracing@0.1.44"
      ]
    },
    {
      "ref": "pkg:cargo/opentelemetry_sdk@0.27.1",
      "dependsOn": [
        "pkg:cargo/async-trait@0.1.92",
        "pkg:cargo/futures-channel@0.3.34",
        "pkg:cargo/futures-executor@0.3.34",
        "pkg:cargo/futures-util@0.3.34",
        "pkg:cargo/glob@0.3.4",
        "pkg:cargo/opentelemetry@0.27.1",
        "pkg:cargo/percent-encoding@2.3.2",
        "pkg:cargo/rand@0.8.8",
        "pkg:cargo/serde_json@1.0.154",
        "pkg:cargo/thiserror@1.0.69",
        "pkg:cargo/tokio-stream@0.1.19",
        "pkg:cargo/tokio@1.54.0",
        "pkg:cargo/tracing@0.1.44"
      ]
    },
    {
      "ref": "pkg:cargo/outref@0.5.2",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/p256@0.13.2",
      "dependsOn": [
        "pkg:cargo/ecdsa@0.16.9",
        "pkg:cargo/elliptic-curve@0.13.8",
        "pkg:cargo/primeorder@0.13.6",
        "pkg:cargo/sha2@0.10.9"
      ]
    },
    {
      "ref": "pkg:cargo/p384@0.13.1",
      "dependsOn": [
        "pkg:cargo/ecdsa@0.16.9",
        "pkg:cargo/elliptic-curve@0.13.8",
        "pkg:cargo/primeorder@0.13.6",
        "pkg:cargo/sha2@0.10.9"
      ]
    },
    {
      "ref": "pkg:cargo/parking@2.2.1",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/parking_lot@0.12.5",
      "dependsOn": [
        "pkg:cargo/lock_api@0.4.14",
        "pkg:cargo/parking_lot_core@0.9.12"
      ]
    },
    {
      "ref": "pkg:cargo/parking_lot_core@0.9.12",
      "dependsOn": [
        "pkg:cargo/cfg-if@1.0.5",
        "pkg:cargo/libc@0.2.191",
        "pkg:cargo/smallvec@1.16.3"
      ]
    },
    {
      "ref": "pkg:cargo/pear@0.2.9",
      "dependsOn": [
        "pkg:cargo/inlinable_string@0.1.15",
        "pkg:cargo/yansi@1.0.1"
      ]
    },
    {
      "ref": "pkg:cargo/pem-rfc7468@0.7.0",
      "dependsOn": [
        "pkg:cargo/base64ct@1.8.3"
      ]
    },
    {
      "ref": "pkg:cargo/pem@3.0.6",
      "dependsOn": [
        "pkg:cargo/base64@0.22.1",
        "pkg:cargo/serde_core@1.0.229"
      ]
    },
    {
      "ref": "pkg:cargo/percent-encoding@2.3.2",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/phf@0.12.1",
      "dependsOn": [
        "pkg:cargo/phf_shared@0.12.1"
      ]
    },
    {
      "ref": "pkg:cargo/phf_shared@0.12.1",
      "dependsOn": [
        "pkg:cargo/siphasher@1.0.4"
      ]
    },
    {
      "ref": "pkg:cargo/pin-project-lite@0.2.17",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/pin-project@1.1.13",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/pkcs1@0.7.5",
      "dependsOn": [
        "pkg:cargo/der@0.7.10",
        "pkg:cargo/pkcs8@0.10.2",
        "pkg:cargo/spki@0.7.3"
      ]
    },
    {
      "ref": "pkg:cargo/pkcs8@0.10.2",
      "dependsOn": [
        "pkg:cargo/der@0.7.10",
        "pkg:cargo/spki@0.7.3"
      ]
    },
    {
      "ref": "pkg:cargo/portable-atomic@1.15.0",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/potential_utf@0.1.6",
      "dependsOn": [
        "pkg:cargo/zerovec@0.11.8"
      ]
    },
    {
      "ref": "pkg:cargo/powerfmt@0.2.1",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/ppv-lite86@0.2.21",
      "dependsOn": [
        "pkg:cargo/zerocopy@0.8.63"
      ]
    },
    {
      "ref": "pkg:cargo/primeorder@0.13.6",
      "dependsOn": [
        "pkg:cargo/elliptic-curve@0.13.8"
      ]
    },
    {
      "ref": "pkg:cargo/proc-macro2@1.0.107",
      "dependsOn": [
        "pkg:cargo/unicode-ident@1.0.27"
      ]
    },
    {
      "ref": "pkg:cargo/prometheus@0.13.4",
      "dependsOn": [
        "pkg:cargo/cfg-if@1.0.5",
        "pkg:cargo/fnv@1.0.7",
        "pkg:cargo/lazy_static@1.5.1",
        "pkg:cargo/memchr@2.8.3",
        "pkg:cargo/parking_lot@0.12.5",
        "pkg:cargo/thiserror@1.0.69"
      ]
    },
    {
      "ref": "pkg:cargo/prost@0.13.5",
      "dependsOn": [
        "pkg:cargo/bytes@1.12.1"
      ]
    },
    {
      "ref": "pkg:cargo/quick-xml@0.39.4",
      "dependsOn": [
        "pkg:cargo/memchr@2.8.3",
        "pkg:cargo/serde@1.0.229"
      ]
    },
    {
      "ref": "pkg:cargo/quinn-proto@0.11.19",
      "dependsOn": [
        "pkg:cargo/bytes@1.12.1",
        "pkg:cargo/lru-slab@0.1.3",
        "pkg:cargo/rand@0.10.3",
        "pkg:cargo/rand_pcg@0.10.2",
        "pkg:cargo/ring@0.17.14",
        "pkg:cargo/rustc-hash@2.1.3",
        "pkg:cargo/rustls@0.23.46",
        "pkg:cargo/slab@0.4.12",
        "pkg:cargo/thiserror@2.0.21",
        "pkg:cargo/tinyvec@1.13.3",
        "pkg:cargo/tracing@0.1.44"
      ]
    },
    {
      "ref": "pkg:cargo/quinn-udp@0.5.16",
      "dependsOn": [
        "pkg:cargo/libc@0.2.191",
        "pkg:cargo/socket2@0.6.5",
        "pkg:cargo/tracing@0.1.44"
      ]
    },
    {
      "ref": "pkg:cargo/quinn@0.11.12",
      "dependsOn": [
        "pkg:cargo/bytes@1.12.1",
        "pkg:cargo/pin-project-lite@0.2.17",
        "pkg:cargo/quinn-proto@0.11.19",
        "pkg:cargo/quinn-udp@0.5.16",
        "pkg:cargo/rustc-hash@2.1.3",
        "pkg:cargo/rustls@0.23.46",
        "pkg:cargo/socket2@0.6.5",
        "pkg:cargo/thiserror@2.0.21",
        "pkg:cargo/tokio@1.54.0",
        "pkg:cargo/tracing@0.1.44"
      ]
    },
    {
      "ref": "pkg:cargo/quote@1.0.47",
      "dependsOn": [
        "pkg:cargo/proc-macro2@1.0.107"
      ]
    },
    {
      "ref": "pkg:cargo/rand@0.10.3",
      "dependsOn": [
        "pkg:cargo/chacha20@0.10.2",
        "pkg:cargo/getrandom@0.4.3",
        "pkg:cargo/rand_core@0.10.1"
      ]
    },
    {
      "ref": "pkg:cargo/rand@0.8.8",
      "dependsOn": [
        "pkg:cargo/libc@0.2.191",
        "pkg:cargo/rand_chacha@0.3.1",
        "pkg:cargo/rand_core@0.6.4"
      ]
    },
    {
      "ref": "pkg:cargo/rand@0.9.5",
      "dependsOn": [
        "pkg:cargo/rand_chacha@0.9.0",
        "pkg:cargo/rand_core@0.9.5"
      ]
    },
    {
      "ref": "pkg:cargo/rand_chacha@0.3.1",
      "dependsOn": [
        "pkg:cargo/ppv-lite86@0.2.21",
        "pkg:cargo/rand_core@0.6.4"
      ]
    },
    {
      "ref": "pkg:cargo/rand_chacha@0.9.0",
      "dependsOn": [
        "pkg:cargo/ppv-lite86@0.2.21",
        "pkg:cargo/rand_core@0.9.5"
      ]
    },
    {
      "ref": "pkg:cargo/rand_core@0.10.1",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/rand_core@0.6.4",
      "dependsOn": [
        "pkg:cargo/getrandom@0.2.17"
      ]
    },
    {
      "ref": "pkg:cargo/rand_core@0.9.5",
      "dependsOn": [
        "pkg:cargo/getrandom@0.3.4"
      ]
    },
    {
      "ref": "pkg:cargo/rand_pcg@0.10.2",
      "dependsOn": [
        "pkg:cargo/rand_core@0.10.1"
      ]
    },
    {
      "ref": "pkg:cargo/ref-cast@1.0.27",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/referencing@0.30.0",
      "dependsOn": [
        "pkg:cargo/ahash@0.8.12",
        "pkg:cargo/fluent-uri@0.3.2",
        "pkg:cargo/once_cell@1.21.4",
        "pkg:cargo/parking_lot@0.12.5",
        "pkg:cargo/percent-encoding@2.3.2",
        "pkg:cargo/serde_json@1.0.154"
      ]
    },
    {
      "ref": "pkg:cargo/regex-automata@0.4.18",
      "dependsOn": [
        "pkg:cargo/aho-corasick@1.1.5",
        "pkg:cargo/memchr@2.8.3",
        "pkg:cargo/regex-syntax@0.8.11"
      ]
    },
    {
      "ref": "pkg:cargo/regex-syntax@0.8.11",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/regex@1.13.1",
      "dependsOn": [
        "pkg:cargo/aho-corasick@1.1.5",
        "pkg:cargo/memchr@2.8.3",
        "pkg:cargo/regex-automata@0.4.18",
        "pkg:cargo/regex-syntax@0.8.11"
      ]
    },
    {
      "ref": "pkg:cargo/regorus-mimalloc-sys@2.2.6",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/regorus-mimalloc@2.2.8",
      "dependsOn": [
        "pkg:cargo/regorus-mimalloc-sys@2.2.6"
      ]
    },
    {
      "ref": "pkg:cargo/regorus@0.9.1",
      "dependsOn": [
        "pkg:cargo/anyhow@1.0.104",
        "pkg:cargo/bincode@2.0.1",
        "pkg:cargo/chrono-tz@0.10.4",
        "pkg:cargo/chrono@0.4.45",
        "pkg:cargo/data-encoding@2.11.1",
        "pkg:cargo/globset@0.4.20",
        "pkg:cargo/indexmap@2.14.2",
        "pkg:cargo/ipnet@2.12.2",
        "pkg:cargo/jsonschema@0.30.0",
        "pkg:cargo/lazy_static@1.5.1",
        "pkg:cargo/msvc_spectre_libs@0.1.3",
        "pkg:cargo/num-bigint@0.4.8",
        "pkg:cargo/num-traits@0.2.19",
        "pkg:cargo/rand@0.9.5",
        "pkg:cargo/regex@1.13.1",
        "pkg:cargo/regorus-mimalloc@2.2.8",
        "pkg:cargo/semver@1.0.28",
        "pkg:cargo/serde@1.0.229",
        "pkg:cargo/serde_json@1.0.154",
        "pkg:cargo/serde_yaml@0.9.34%2Bdeprecated",
        "pkg:cargo/spin@0.9.9",
        "pkg:cargo/thiserror@2.0.21",
        "pkg:cargo/url@2.5.8",
        "pkg:cargo/uuid@1.28.0"
      ]
    },
    {
      "ref": "pkg:cargo/reqwest@0.12.28",
      "dependsOn": [
        "pkg:cargo/base64@0.22.1",
        "pkg:cargo/bytes@1.12.1",
        "pkg:cargo/futures-core@0.3.34",
        "pkg:cargo/futures-util@0.3.34",
        "pkg:cargo/h2@0.4.20",
        "pkg:cargo/http-body-util@0.1.5",
        "pkg:cargo/http-body@1.1.0",
        "pkg:cargo/http@1.5.0",
        "pkg:cargo/hyper-rustls@0.27.10",
        "pkg:cargo/hyper-util@0.1.21",
        "pkg:cargo/hyper@1.12.0",
        "pkg:cargo/log@0.4.34",
        "pkg:cargo/percent-encoding@2.3.2",
        "pkg:cargo/pin-project-lite@0.2.17",
        "pkg:cargo/quinn@0.11.12",
        "pkg:cargo/rustls-pki-types@1.15.1",
        "pkg:cargo/rustls@0.23.46",
        "pkg:cargo/serde@1.0.229",
        "pkg:cargo/serde_json@1.0.154",
        "pkg:cargo/serde_urlencoded@0.7.1",
        "pkg:cargo/sync_wrapper@1.0.2",
        "pkg:cargo/tokio-rustls@0.26.6",
        "pkg:cargo/tokio-util@0.7.20",
        "pkg:cargo/tokio@1.54.0",
        "pkg:cargo/tower-http@0.6.11",
        "pkg:cargo/tower-service@0.3.3",
        "pkg:cargo/tower@0.5.3",
        "pkg:cargo/url@2.5.8",
        "pkg:cargo/webpki-roots@1.0.10"
      ]
    },
    {
      "ref": "pkg:cargo/rfc6979@0.4.0",
      "dependsOn": [
        "pkg:cargo/hmac@0.12.1",
        "pkg:cargo/subtle@2.6.1"
      ]
    },
    {
      "ref": "pkg:cargo/ring@0.17.14",
      "dependsOn": [
        "pkg:cargo/cfg-if@1.0.5",
        "pkg:cargo/getrandom@0.2.17",
        "pkg:cargo/untrusted@0.9.0"
      ]
    },
    {
      "ref": "pkg:cargo/rsa@0.9.10",
      "dependsOn": [
        "pkg:cargo/const-oid@0.9.6",
        "pkg:cargo/digest@0.10.7",
        "pkg:cargo/num-bigint-dig@0.8.6",
        "pkg:cargo/num-integer@0.1.47",
        "pkg:cargo/num-traits@0.2.19",
        "pkg:cargo/pkcs1@0.7.5",
        "pkg:cargo/pkcs8@0.10.2",
        "pkg:cargo/rand_core@0.6.4",
        "pkg:cargo/signature@2.2.0",
        "pkg:cargo/spki@0.7.3",
        "pkg:cargo/subtle@2.6.1",
        "pkg:cargo/zeroize@1.9.1"
      ]
    },
    {
      "ref": "pkg:cargo/rustc-hash@2.1.3",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/rustix@1.1.5",
      "dependsOn": [
        "pkg:cargo/bitflags@2.13.2",
        "pkg:cargo/errno@0.3.14",
        "pkg:cargo/libc@0.2.191",
        "pkg:cargo/linux-raw-sys@0.12.1"
      ]
    },
    {
      "ref": "pkg:cargo/rustls-pki-types@1.15.1",
      "dependsOn": [
        "pkg:cargo/zeroize@1.9.1"
      ]
    },
    {
      "ref": "pkg:cargo/rustls-webpki@0.103.16",
      "dependsOn": [
        "pkg:cargo/ring@0.17.14",
        "pkg:cargo/rustls-pki-types@1.15.1",
        "pkg:cargo/untrusted@0.9.0"
      ]
    },
    {
      "ref": "pkg:cargo/rustls@0.23.46",
      "dependsOn": [
        "pkg:cargo/once_cell@1.21.4",
        "pkg:cargo/ring@0.17.14",
        "pkg:cargo/rustls-pki-types@1.15.1",
        "pkg:cargo/rustls-webpki@0.103.16",
        "pkg:cargo/subtle@2.6.1",
        "pkg:cargo/zeroize@1.9.1"
      ]
    },
    {
      "ref": "pkg:cargo/rustversion@1.0.23",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/ryu@1.0.23",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/same-file@1.0.6",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/scopeguard@1.2.0",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/sec1@0.7.3",
      "dependsOn": [
        "pkg:cargo/base16ct@0.2.0",
        "pkg:cargo/der@0.7.10",
        "pkg:cargo/generic-array@0.14.9",
        "pkg:cargo/pkcs8@0.10.2",
        "pkg:cargo/subtle@2.6.1",
        "pkg:cargo/zeroize@1.9.1"
      ]
    },
    {
      "ref": "pkg:cargo/semver@1.0.28",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/serde@1.0.229",
      "dependsOn": [
        "pkg:cargo/serde_core@1.0.229"
      ]
    },
    {
      "ref": "pkg:cargo/serde_core@1.0.229",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/serde_json@1.0.154",
      "dependsOn": [
        "pkg:cargo/itoa@1.0.18",
        "pkg:cargo/memchr@2.8.3",
        "pkg:cargo/serde_core@1.0.229",
        "pkg:cargo/zmij@1.0.23"
      ]
    },
    {
      "ref": "pkg:cargo/serde_path_to_error@0.1.20",
      "dependsOn": [
        "pkg:cargo/itoa@1.0.18",
        "pkg:cargo/serde_core@1.0.229"
      ]
    },
    {
      "ref": "pkg:cargo/serde_spanned@1.1.2",
      "dependsOn": [
        "pkg:cargo/serde_core@1.0.229"
      ]
    },
    {
      "ref": "pkg:cargo/serde_urlencoded@0.7.1",
      "dependsOn": [
        "pkg:cargo/form_urlencoded@1.2.2",
        "pkg:cargo/itoa@1.0.18",
        "pkg:cargo/ryu@1.0.23",
        "pkg:cargo/serde@1.0.229"
      ]
    },
    {
      "ref": "pkg:cargo/serde_yaml@0.9.34%2Bdeprecated",
      "dependsOn": [
        "pkg:cargo/indexmap@2.14.2",
        "pkg:cargo/itoa@1.0.18",
        "pkg:cargo/ryu@1.0.23",
        "pkg:cargo/serde@1.0.229",
        "pkg:cargo/unsafe-libyaml@0.2.11"
      ]
    },
    {
      "ref": "pkg:cargo/sha1@0.10.7",
      "dependsOn": [
        "pkg:cargo/cfg-if@1.0.5",
        "pkg:cargo/cpufeatures@0.2.17",
        "pkg:cargo/digest@0.10.7"
      ]
    },
    {
      "ref": "pkg:cargo/sha2@0.10.9",
      "dependsOn": [
        "pkg:cargo/cfg-if@1.0.5",
        "pkg:cargo/cpufeatures@0.2.17",
        "pkg:cargo/digest@0.10.7"
      ]
    },
    {
      "ref": "pkg:cargo/sha2@0.11.1",
      "dependsOn": [
        "pkg:cargo/cfg-if@1.0.5",
        "pkg:cargo/cpufeatures@0.3.1",
        "pkg:cargo/digest@0.11.3"
      ]
    },
    {
      "ref": "pkg:cargo/sharded-slab@0.1.7",
      "dependsOn": [
        "pkg:cargo/lazy_static@1.5.1"
      ]
    },
    {
      "ref": "pkg:cargo/signal-hook-registry@1.4.8",
      "dependsOn": [
        "pkg:cargo/errno@0.3.14",
        "pkg:cargo/libc@0.2.191"
      ]
    },
    {
      "ref": "pkg:cargo/signature@2.2.0",
      "dependsOn": [
        "pkg:cargo/digest@0.10.7",
        "pkg:cargo/rand_core@0.6.4"
      ]
    },
    {
      "ref": "pkg:cargo/simple_asn1@0.6.4",
      "dependsOn": [
        "pkg:cargo/num-bigint@0.4.8",
        "pkg:cargo/num-traits@0.2.19",
        "pkg:cargo/thiserror@2.0.21",
        "pkg:cargo/time@0.3.55"
      ]
    },
    {
      "ref": "pkg:cargo/siphasher@1.0.4",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/slab@0.4.12",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/smallvec@1.16.3",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/socket2@0.5.10",
      "dependsOn": [
        "pkg:cargo/libc@0.2.191"
      ]
    },
    {
      "ref": "pkg:cargo/socket2@0.6.5",
      "dependsOn": [
        "pkg:cargo/libc@0.2.191"
      ]
    },
    {
      "ref": "pkg:cargo/spin@0.9.9",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/spki@0.7.3",
      "dependsOn": [
        "pkg:cargo/base64ct@1.8.3",
        "pkg:cargo/der@0.7.10"
      ]
    },
    {
      "ref": "pkg:cargo/stable_deref_trait@1.2.1",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/stoa-gateway@0.9.25",
      "dependsOn": [
        "pkg:cargo/arc-swap@1.9.3",
        "pkg:cargo/async-trait@0.1.92",
        "pkg:cargo/axum@0.7.9",
        "pkg:cargo/base64@0.22.1",
        "pkg:cargo/chrono@0.4.45",
        "pkg:cargo/figment@0.10.19",
        "pkg:cargo/form_urlencoded@1.2.2",
        "pkg:cargo/futures@0.3.34",
        "pkg:cargo/hostname@0.4.2",
        "pkg:cargo/ipnet@2.12.2",
        "pkg:cargo/jsonwebtoken@10.4.0",
        "pkg:cargo/libc@0.2.191",
        "pkg:cargo/moka@0.12.16",
        "pkg:cargo/notify@8.2.0",
        "pkg:cargo/once_cell@1.21.4",
        "pkg:cargo/opentelemetry-otlp@0.27.0",
        "pkg:cargo/opentelemetry@0.27.1",
        "pkg:cargo/opentelemetry_sdk@0.27.1",
        "pkg:cargo/parking_lot@0.12.5",
        "pkg:cargo/prometheus@0.13.4",
        "pkg:cargo/quick-xml@0.39.4",
        "pkg:cargo/rand@0.10.3",
        "pkg:cargo/regex@1.13.1",
        "pkg:cargo/regorus@0.9.1",
        "pkg:cargo/reqwest@0.12.28",
        "pkg:cargo/serde@1.0.229",
        "pkg:cargo/serde_json@1.0.154",
        "pkg:cargo/serde_yaml@0.9.34%2Bdeprecated",
        "pkg:cargo/sha2@0.11.1",
        "pkg:cargo/socket2@0.6.5",
        "pkg:cargo/subtle@2.6.1",
        "pkg:cargo/thiserror@2.0.21",
        "pkg:cargo/tokio-stream@0.1.19",
        "pkg:cargo/tokio-tungstenite@0.29.0",
        "pkg:cargo/tokio@1.54.0",
        "pkg:cargo/toml@1.1.8%2Bspec-1.1.0",
        "pkg:cargo/tracing-opentelemetry@0.28.0",
        "pkg:cargo/tracing-subscriber@0.3.23",
        "pkg:cargo/tracing@0.1.44",
        "pkg:cargo/url@2.5.8",
        "pkg:cargo/urlencoding@2.1.3",
        "pkg:cargo/uuid@1.28.0"
      ]
    },
    {
      "ref": "pkg:cargo/subtle@2.6.1",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/syn@2.0.119",
      "dependsOn": [
        "pkg:cargo/proc-macro2@1.0.107",
        "pkg:cargo/quote@1.0.47",
        "pkg:cargo/unicode-ident@1.0.27"
      ]
    },
    {
      "ref": "pkg:cargo/syn@3.0.9",
      "dependsOn": [
        "pkg:cargo/proc-macro2@1.0.107",
        "pkg:cargo/quote@1.0.47",
        "pkg:cargo/unicode-ident@1.0.27"
      ]
    },
    {
      "ref": "pkg:cargo/sync_wrapper@1.0.2",
      "dependsOn": [
        "pkg:cargo/futures-core@0.3.34"
      ]
    },
    {
      "ref": "pkg:cargo/synstructure@0.14.0",
      "dependsOn": [
        "pkg:cargo/proc-macro2@1.0.107",
        "pkg:cargo/quote@1.0.47",
        "pkg:cargo/syn@3.0.9"
      ]
    },
    {
      "ref": "pkg:cargo/tagptr@0.2.0",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/tempfile@3.27.0",
      "dependsOn": [
        "pkg:cargo/fastrand@2.5.0",
        "pkg:cargo/getrandom@0.4.3",
        "pkg:cargo/once_cell@1.21.4",
        "pkg:cargo/rustix@1.1.5"
      ]
    },
    {
      "ref": "pkg:cargo/thiserror@1.0.69",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/thiserror@2.0.21",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/thread_local@1.1.10",
      "dependsOn": [
        "pkg:cargo/cfg-if@1.0.5"
      ]
    },
    {
      "ref": "pkg:cargo/time-core@0.1.9",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/time@0.3.55",
      "dependsOn": [
        "pkg:cargo/deranged@0.5.9",
        "pkg:cargo/num-conv@0.2.2",
        "pkg:cargo/powerfmt@0.2.1",
        "pkg:cargo/serde_core@1.0.229",
        "pkg:cargo/time-core@0.1.9"
      ]
    },
    {
      "ref": "pkg:cargo/tinystr@0.8.4",
      "dependsOn": [
        "pkg:cargo/displaydoc@0.2.7",
        "pkg:cargo/zerovec@0.11.8"
      ]
    },
    {
      "ref": "pkg:cargo/tinyvec@1.13.3",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/tokio-rustls@0.26.6",
      "dependsOn": [
        "pkg:cargo/rustls@0.23.46",
        "pkg:cargo/tokio@1.54.0"
      ]
    },
    {
      "ref": "pkg:cargo/tokio-stream@0.1.19",
      "dependsOn": [
        "pkg:cargo/futures-core@0.3.34",
        "pkg:cargo/pin-project-lite@0.2.17",
        "pkg:cargo/tokio@1.54.0"
      ]
    },
    {
      "ref": "pkg:cargo/tokio-tungstenite@0.24.0",
      "dependsOn": [
        "pkg:cargo/futures-util@0.3.34",
        "pkg:cargo/log@0.4.34",
        "pkg:cargo/tokio@1.54.0",
        "pkg:cargo/tungstenite@0.24.0"
      ]
    },
    {
      "ref": "pkg:cargo/tokio-tungstenite@0.29.0",
      "dependsOn": [
        "pkg:cargo/futures-util@0.3.34",
        "pkg:cargo/log@0.4.34",
        "pkg:cargo/rustls-pki-types@1.15.1",
        "pkg:cargo/rustls@0.23.46",
        "pkg:cargo/tokio-rustls@0.26.6",
        "pkg:cargo/tokio@1.54.0",
        "pkg:cargo/tungstenite@0.29.0",
        "pkg:cargo/webpki-roots@0.26.11"
      ]
    },
    {
      "ref": "pkg:cargo/tokio-util@0.7.20",
      "dependsOn": [
        "pkg:cargo/bytes@1.12.1",
        "pkg:cargo/futures-core@0.3.34",
        "pkg:cargo/futures-sink@0.3.34",
        "pkg:cargo/libc@0.2.191",
        "pkg:cargo/pin-project-lite@0.2.17",
        "pkg:cargo/tokio@1.54.0"
      ]
    },
    {
      "ref": "pkg:cargo/tokio@1.54.0",
      "dependsOn": [
        "pkg:cargo/bytes@1.12.1",
        "pkg:cargo/libc@0.2.191",
        "pkg:cargo/mio@1.2.4",
        "pkg:cargo/parking_lot@0.12.5",
        "pkg:cargo/pin-project-lite@0.2.17",
        "pkg:cargo/signal-hook-registry@1.4.8",
        "pkg:cargo/socket2@0.6.5"
      ]
    },
    {
      "ref": "pkg:cargo/toml@1.1.8%2Bspec-1.1.0",
      "dependsOn": [
        "pkg:cargo/indexmap@2.14.2",
        "pkg:cargo/serde_core@1.0.229",
        "pkg:cargo/serde_spanned@1.1.2",
        "pkg:cargo/toml_datetime@1.1.2%2Bspec-1.1.0",
        "pkg:cargo/toml_parser@1.1.5%2Bspec-1.1.0",
        "pkg:cargo/toml_writer@1.1.3%2Bspec-1.1.0",
        "pkg:cargo/winnow@1.0.4"
      ]
    },
    {
      "ref": "pkg:cargo/toml_datetime@1.1.2%2Bspec-1.1.0",
      "dependsOn": [
        "pkg:cargo/serde_core@1.0.229"
      ]
    },
    {
      "ref": "pkg:cargo/toml_parser@1.1.5%2Bspec-1.1.0",
      "dependsOn": [
        "pkg:cargo/winnow@1.0.4"
      ]
    },
    {
      "ref": "pkg:cargo/toml_writer@1.1.3%2Bspec-1.1.0",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/tonic@0.12.3",
      "dependsOn": [
        "pkg:cargo/async-stream@0.3.6",
        "pkg:cargo/async-trait@0.1.92",
        "pkg:cargo/axum@0.7.9",
        "pkg:cargo/base64@0.22.1",
        "pkg:cargo/bytes@1.12.1",
        "pkg:cargo/h2@0.4.20",
        "pkg:cargo/http-body-util@0.1.5",
        "pkg:cargo/http-body@1.1.0",
        "pkg:cargo/http@1.5.0",
        "pkg:cargo/hyper-timeout@0.5.2",
        "pkg:cargo/hyper-util@0.1.21",
        "pkg:cargo/hyper@1.12.0",
        "pkg:cargo/percent-encoding@2.3.2",
        "pkg:cargo/pin-project@1.1.13",
        "pkg:cargo/prost@0.13.5",
        "pkg:cargo/socket2@0.5.10",
        "pkg:cargo/tokio-stream@0.1.19",
        "pkg:cargo/tokio@1.54.0",
        "pkg:cargo/tower-layer@0.3.3",
        "pkg:cargo/tower-service@0.3.3",
        "pkg:cargo/tower@0.4.13",
        "pkg:cargo/tracing@0.1.44"
      ]
    },
    {
      "ref": "pkg:cargo/tower-http@0.6.11",
      "dependsOn": [
        "pkg:cargo/bitflags@2.13.2",
        "pkg:cargo/bytes@1.12.1",
        "pkg:cargo/futures-util@0.3.34",
        "pkg:cargo/http-body@1.1.0",
        "pkg:cargo/http@1.5.0",
        "pkg:cargo/pin-project-lite@0.2.17",
        "pkg:cargo/tower-layer@0.3.3",
        "pkg:cargo/tower-service@0.3.3",
        "pkg:cargo/tower@0.5.3",
        "pkg:cargo/url@2.5.8"
      ]
    },
    {
      "ref": "pkg:cargo/tower-layer@0.3.3",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/tower-service@0.3.3",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/tower@0.4.13",
      "dependsOn": [
        "pkg:cargo/futures-core@0.3.34",
        "pkg:cargo/futures-util@0.3.34",
        "pkg:cargo/indexmap@1.9.3",
        "pkg:cargo/pin-project-lite@0.2.17",
        "pkg:cargo/pin-project@1.1.13",
        "pkg:cargo/rand@0.8.8",
        "pkg:cargo/slab@0.4.12",
        "pkg:cargo/tokio-util@0.7.20",
        "pkg:cargo/tokio@1.54.0",
        "pkg:cargo/tower-layer@0.3.3",
        "pkg:cargo/tower-service@0.3.3",
        "pkg:cargo/tracing@0.1.44"
      ]
    },
    {
      "ref": "pkg:cargo/tower@0.5.3",
      "dependsOn": [
        "pkg:cargo/futures-core@0.3.34",
        "pkg:cargo/futures-util@0.3.34",
        "pkg:cargo/pin-project-lite@0.2.17",
        "pkg:cargo/sync_wrapper@1.0.2",
        "pkg:cargo/tokio@1.54.0",
        "pkg:cargo/tower-layer@0.3.3",
        "pkg:cargo/tower-service@0.3.3",
        "pkg:cargo/tracing@0.1.44"
      ]
    },
    {
      "ref": "pkg:cargo/tracing-attributes@0.1.31",
      "dependsOn": [
        "pkg:cargo/proc-macro2@1.0.107",
        "pkg:cargo/quote@1.0.47",
        "pkg:cargo/syn@2.0.119"
      ]
    },
    {
      "ref": "pkg:cargo/tracing-core@0.1.36",
      "dependsOn": [
        "pkg:cargo/once_cell@1.21.4"
      ]
    },
    {
      "ref": "pkg:cargo/tracing-log@0.2.0",
      "dependsOn": [
        "pkg:cargo/log@0.4.34",
        "pkg:cargo/once_cell@1.21.4",
        "pkg:cargo/tracing-core@0.1.36"
      ]
    },
    {
      "ref": "pkg:cargo/tracing-opentelemetry@0.28.0",
      "dependsOn": [
        "pkg:cargo/once_cell@1.21.4",
        "pkg:cargo/opentelemetry@0.27.1",
        "pkg:cargo/opentelemetry_sdk@0.27.1",
        "pkg:cargo/smallvec@1.16.3",
        "pkg:cargo/tracing-core@0.1.36",
        "pkg:cargo/tracing-log@0.2.0",
        "pkg:cargo/tracing-subscriber@0.3.23",
        "pkg:cargo/tracing@0.1.44"
      ]
    },
    {
      "ref": "pkg:cargo/tracing-serde@0.2.0",
      "dependsOn": [
        "pkg:cargo/serde@1.0.229",
        "pkg:cargo/tracing-core@0.1.36"
      ]
    },
    {
      "ref": "pkg:cargo/tracing-subscriber@0.3.23",
      "dependsOn": [
        "pkg:cargo/matchers@0.2.0",
        "pkg:cargo/nu-ansi-term@0.50.3",
        "pkg:cargo/once_cell@1.21.4",
        "pkg:cargo/regex-automata@0.4.18",
        "pkg:cargo/serde@1.0.229",
        "pkg:cargo/serde_json@1.0.154",
        "pkg:cargo/sharded-slab@0.1.7",
        "pkg:cargo/smallvec@1.16.3",
        "pkg:cargo/thread_local@1.1.10",
        "pkg:cargo/tracing-core@0.1.36",
        "pkg:cargo/tracing-log@0.2.0",
        "pkg:cargo/tracing-serde@0.2.0",
        "pkg:cargo/tracing@0.1.44"
      ]
    },
    {
      "ref": "pkg:cargo/tracing@0.1.44",
      "dependsOn": [
        "pkg:cargo/log@0.4.34",
        "pkg:cargo/pin-project-lite@0.2.17",
        "pkg:cargo/tracing-attributes@0.1.31",
        "pkg:cargo/tracing-core@0.1.36"
      ]
    },
    {
      "ref": "pkg:cargo/try-lock@0.2.5",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/tungstenite@0.24.0",
      "dependsOn": [
        "pkg:cargo/byteorder@1.5.0",
        "pkg:cargo/bytes@1.12.1",
        "pkg:cargo/data-encoding@2.11.1",
        "pkg:cargo/http@1.5.0",
        "pkg:cargo/httparse@1.10.1",
        "pkg:cargo/log@0.4.34",
        "pkg:cargo/rand@0.8.8",
        "pkg:cargo/sha1@0.10.7",
        "pkg:cargo/thiserror@1.0.69",
        "pkg:cargo/utf-8@0.7.6"
      ]
    },
    {
      "ref": "pkg:cargo/tungstenite@0.29.0",
      "dependsOn": [
        "pkg:cargo/bytes@1.12.1",
        "pkg:cargo/data-encoding@2.11.1",
        "pkg:cargo/http@1.5.0",
        "pkg:cargo/httparse@1.10.1",
        "pkg:cargo/log@0.4.34",
        "pkg:cargo/rand@0.9.5",
        "pkg:cargo/rustls-pki-types@1.15.1",
        "pkg:cargo/rustls@0.23.46",
        "pkg:cargo/sha1@0.10.7",
        "pkg:cargo/thiserror@2.0.21"
      ]
    },
    {
      "ref": "pkg:cargo/typenum@1.20.1",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/uncased@0.9.10",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/unicode-ident@1.0.27",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/unsafe-libyaml@0.2.11",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/untrusted@0.9.0",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/unty@0.0.4",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/url@2.5.8",
      "dependsOn": [
        "pkg:cargo/form_urlencoded@1.2.2",
        "pkg:cargo/idna@1.1.0",
        "pkg:cargo/percent-encoding@2.3.2",
        "pkg:cargo/serde@1.0.229"
      ]
    },
    {
      "ref": "pkg:cargo/urlencoding@2.1.3",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/utf-8@0.7.6",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/utf8_iter@1.0.4",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/uuid-simd@0.8.0",
      "dependsOn": [
        "pkg:cargo/outref@0.5.2",
        "pkg:cargo/uuid@1.28.0",
        "pkg:cargo/vsimd@0.8.0"
      ]
    },
    {
      "ref": "pkg:cargo/uuid@1.28.0",
      "dependsOn": [
        "pkg:cargo/getrandom@0.4.3",
        "pkg:cargo/rand@0.10.3",
        "pkg:cargo/serde_core@1.0.229"
      ]
    },
    {
      "ref": "pkg:cargo/vsimd@0.8.0",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/walkdir@2.5.0",
      "dependsOn": [
        "pkg:cargo/same-file@1.0.6"
      ]
    },
    {
      "ref": "pkg:cargo/want@0.3.2",
      "dependsOn": [
        "pkg:cargo/try-lock@0.2.5"
      ]
    },
    {
      "ref": "pkg:cargo/webpki-roots@0.26.11",
      "dependsOn": [
        "pkg:cargo/webpki-roots@1.0.10"
      ]
    },
    {
      "ref": "pkg:cargo/webpki-roots@1.0.10",
      "dependsOn": [
        "pkg:cargo/rustls-pki-types@1.15.1"
      ]
    },
    {
      "ref": "pkg:cargo/winnow@1.0.4",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/writeable@0.6.4",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/yansi@1.0.1",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/yoke-derive@0.8.4",
      "dependsOn": [
        "pkg:cargo/proc-macro2@1.0.107",
        "pkg:cargo/quote@1.0.47",
        "pkg:cargo/syn@3.0.9",
        "pkg:cargo/synstructure@0.14.0"
      ]
    },
    {
      "ref": "pkg:cargo/yoke@0.8.3",
      "dependsOn": [
        "pkg:cargo/stable_deref_trait@1.2.1",
        "pkg:cargo/yoke-derive@0.8.4",
        "pkg:cargo/zerofrom@0.1.8"
      ]
    },
    {
      "ref": "pkg:cargo/zerocopy-derive@0.8.63",
      "dependsOn": [
        "pkg:cargo/proc-macro2@1.0.107",
        "pkg:cargo/quote@1.0.47",
        "pkg:cargo/syn@2.0.119"
      ]
    },
    {
      "ref": "pkg:cargo/zerocopy@0.8.63",
      "dependsOn": [
        "pkg:cargo/zerocopy-derive@0.8.63"
      ]
    },
    {
      "ref": "pkg:cargo/zerofrom-derive@0.1.8",
      "dependsOn": [
        "pkg:cargo/proc-macro2@1.0.107",
        "pkg:cargo/quote@1.0.47",
        "pkg:cargo/syn@3.0.9",
        "pkg:cargo/synstructure@0.14.0"
      ]
    },
    {
      "ref": "pkg:cargo/zerofrom@0.1.8",
      "dependsOn": [
        "pkg:cargo/zerofrom-derive@0.1.8"
      ]
    },
    {
      "ref": "pkg:cargo/zeroize@1.9.1",
      "dependsOn": []
    },
    {
      "ref": "pkg:cargo/zerotrie@0.2.5",
      "dependsOn": [
        "pkg:cargo/displaydoc@0.2.7",
        "pkg:cargo/yoke@0.8.3",
        "pkg:cargo/zerofrom@0.1.8"
      ]
    },
    {
      "ref": "pkg:cargo/zerovec-derive@0.11.6",
      "dependsOn": [
        "pkg:cargo/proc-macro2@1.0.107",
        "pkg:cargo/quote@1.0.47",
        "pkg:cargo/syn@3.0.9"
      ]
    },
    {
      "ref": "pkg:cargo/zerovec@0.11.8",
      "dependsOn": [
        "pkg:cargo/yoke@0.8.3",
        "pkg:cargo/zerofrom@0.1.8",
        "pkg:cargo/zerovec-derive@0.11.6"
      ]
    },
    {
      "ref": "pkg:cargo/zmij@1.0.23",
      "dependsOn": []
    },
    {
      "ref": "pkg:deb/debian/adduser@3.134?arch=all&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/passwd@4.13%2Bdfsg1-1%2Bdeb12u2?arch=amd64&distro=debian-12.15&epoch=1"
      ]
    },
    {
      "ref": "pkg:deb/debian/apt@2.6.1?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/adduser@3.134?arch=all&distro=debian-12.15",
        "pkg:deb/debian/debian-archive-keyring@2023.3%2Bdeb12u2?arch=all&distro=debian-12.15",
        "pkg:deb/debian/gpgv@2.2.40-1.1%2Bdeb12u2?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libapt-pkg6.0@2.6.1?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libgcc-s1@12.2.0-14%2Bdeb12u1?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libgnutls30@3.7.9-2%2Bdeb12u7?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libseccomp2@2.5.4-1%2Bdeb12u1?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libstdc%2B%2B6@12.2.0-14%2Bdeb12u1?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libsystemd0@252.39-1~deb12u2?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/base-files@12.4%2Bdeb12u15?arch=amd64&distro=debian-12.15",
      "dependsOn": []
    },
    {
      "ref": "pkg:deb/debian/base-passwd@3.6.1?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libdebconfclient0@0.270?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libselinux1@3.4-1%2Bb6?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/bash@5.2.15-2%2Bb13?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/base-files@12.4%2Bdeb12u15?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/debianutils@5.7-0.5~deb12u1?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/bsdutils@2.38.1-5%2Bdeb12u3?arch=amd64&distro=debian-12.15&epoch=1",
      "dependsOn": []
    },
    {
      "ref": "pkg:deb/debian/ca-certificates@20250419~deb12u2?arch=all&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/debconf@1.5.82?arch=all&distro=debian-12.15",
        "pkg:deb/debian/openssl@3.0.22-1~deb12u1?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/coreutils@9.1-1?arch=amd64&distro=debian-12.15",
      "dependsOn": []
    },
    {
      "ref": "pkg:deb/debian/curl@7.88.1-10%2Bdeb12u15?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libcurl4@7.88.1-10%2Bdeb12u15?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/zlib1g@1.2.13.dfsg-1?arch=amd64&distro=debian-12.15&epoch=1"
      ]
    },
    {
      "ref": "pkg:deb/debian/dash@0.5.12-2?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/debianutils@5.7-0.5~deb12u1?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/dpkg@1.21.23?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/debconf@1.5.82?arch=all&distro=debian-12.15",
      "dependsOn": []
    },
    {
      "ref": "pkg:deb/debian/debian-archive-keyring@2023.3%2Bdeb12u2?arch=all&distro=debian-12.15",
      "dependsOn": []
    },
    {
      "ref": "pkg:deb/debian/debianutils@5.7-0.5~deb12u1?arch=amd64&distro=debian-12.15",
      "dependsOn": []
    },
    {
      "ref": "pkg:deb/debian/diffutils@3.8-4?arch=amd64&distro=debian-12.15&epoch=1",
      "dependsOn": []
    },
    {
      "ref": "pkg:deb/debian/dpkg@1.21.23?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/tar@1.34%2Bdfsg-1.2%2Bdeb12u1?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/e2fsprogs@1.47.0-2%2Bb2?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/logsave@1.47.0-2%2Bb2?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/findutils@4.9.0-4?arch=amd64&distro=debian-12.15",
      "dependsOn": []
    },
    {
      "ref": "pkg:deb/debian/gcc-12-base@12.2.0-14%2Bdeb12u1?arch=amd64&distro=debian-12.15",
      "dependsOn": []
    },
    {
      "ref": "pkg:deb/debian/gpgv@2.2.40-1.1%2Bdeb12u2?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libbz2-1.0@1.0.8-5%2Bb1?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libgcrypt20@1.10.1-3%2Bdeb12u1?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libgpg-error0@1.46-1?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/zlib1g@1.2.13.dfsg-1?arch=amd64&distro=debian-12.15&epoch=1"
      ]
    },
    {
      "ref": "pkg:deb/debian/grep@3.8-5?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/dpkg@1.21.23?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/gzip@1.12-1?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/dpkg@1.21.23?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/hostname@3.23%2Bnmu1?arch=amd64&distro=debian-12.15",
      "dependsOn": []
    },
    {
      "ref": "pkg:deb/debian/init-system-helpers@1.65.2%2Bdeb12u1?arch=all&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/usr-is-merged@37~deb12u1?arch=all&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/krb5-locales@1.20.1-2%2Bdeb12u5?arch=all&distro=debian-12.15",
      "dependsOn": []
    },
    {
      "ref": "pkg:deb/debian/libacl1@2.3.1-3?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/libapt-pkg6.0@2.6.1?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libbz2-1.0@1.0.8-5%2Bb1?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libgcc-s1@12.2.0-14%2Bdeb12u1?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libgcrypt20@1.10.1-3%2Bdeb12u1?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/liblz4-1@1.9.4-1?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/liblzma5@5.4.1-1%2Bdeb12u2?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libstdc%2B%2B6@12.2.0-14%2Bdeb12u1?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libsystemd0@252.39-1~deb12u2?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libudev1@252.39-1~deb12u2?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libxxhash0@0.8.1-1?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libzstd1@1.5.4%2Bdfsg2-5?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/zlib1g@1.2.13.dfsg-1?arch=amd64&distro=debian-12.15&epoch=1"
      ]
    },
    {
      "ref": "pkg:deb/debian/libattr1@2.5.1-4?arch=amd64&distro=debian-12.15&epoch=1",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/libaudit-common@3.0.9-1?arch=all&distro=debian-12.15&epoch=1",
      "dependsOn": []
    },
    {
      "ref": "pkg:deb/debian/libaudit1@3.0.9-1?arch=amd64&distro=debian-12.15&epoch=1",
      "dependsOn": [
        "pkg:deb/debian/libaudit-common@3.0.9-1?arch=all&distro=debian-12.15&epoch=1",
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libcap-ng0@0.8.3-1%2Bb3?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/libblkid1@2.38.1-5%2Bdeb12u3?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/libbrotli1@1.0.9-2%2Bb6?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/libbz2-1.0@1.0.8-5%2Bb1?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/libc-bin@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libgcc-s1@12.2.0-14%2Bdeb12u1?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/libcap-ng0@0.8.3-1%2Bb3?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/libcap2@2.66-4%2Bdeb12u3%2Bb1?arch=amd64&distro=debian-12.15&epoch=1",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/libcom-err2@1.47.0-2%2Bb2?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/libcrypt1@4.4.33-2?arch=amd64&distro=debian-12.15&epoch=1",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/libcurl4@7.88.1-10%2Bdeb12u15?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libbrotli1@1.0.9-2%2Bb6?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libgssapi-krb5-2@1.20.1-2%2Bdeb12u5?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libidn2-0@2.3.3-1%2Bb1?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libldap-2.5-0@2.5.13%2Bdfsg-5?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libnghttp2-14@1.52.0-1%2Bdeb12u3?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libpsl5@0.21.2-1?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/librtmp1@2.4%2B20151223.gitfa8646d.1-2%2Bb2?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libssh2-1@1.10.0-3%2Bdeb12u1?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libssl3@3.0.22-1~deb12u1?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libzstd1@1.5.4%2Bdfsg2-5?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/zlib1g@1.2.13.dfsg-1?arch=amd64&distro=debian-12.15&epoch=1"
      ]
    },
    {
      "ref": "pkg:deb/debian/libdb5.3@5.3.28%2Bdfsg2-1?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/libdebconfclient0@0.270?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/libext2fs2@1.47.0-2%2Bb2?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/libffi8@3.4.4-1?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/libgcc-s1@12.2.0-14%2Bdeb12u1?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/gcc-12-base@12.2.0-14%2Bdeb12u1?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/libgcrypt20@1.10.1-3%2Bdeb12u1?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libgpg-error0@1.46-1?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/libgmp10@6.2.1%2Bdfsg1-1.1?arch=amd64&distro=debian-12.15&epoch=2",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/libgnutls30@3.7.9-2%2Bdeb12u7?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libgmp10@6.2.1%2Bdfsg1-1.1?arch=amd64&distro=debian-12.15&epoch=2",
        "pkg:deb/debian/libhogweed6@3.8.1-2?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libidn2-0@2.3.3-1%2Bb1?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libnettle8@3.8.1-2?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libp11-kit0@0.24.1-2?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libtasn1-6@4.19.0-2%2Bdeb12u1?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libunistring2@1.0-2?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/libgpg-error0@1.46-1?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/libgssapi-krb5-2@1.20.1-2%2Bdeb12u5?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libcom-err2@1.47.0-2%2Bb2?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libk5crypto3@1.20.1-2%2Bdeb12u5?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libkrb5-3@1.20.1-2%2Bdeb12u5?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libkrb5support0@1.20.1-2%2Bdeb12u5?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/libhogweed6@3.8.1-2?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libgmp10@6.2.1%2Bdfsg1-1.1?arch=amd64&distro=debian-12.15&epoch=2",
        "pkg:deb/debian/libnettle8@3.8.1-2?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/libidn2-0@2.3.3-1%2Bb1?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libunistring2@1.0-2?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/libk5crypto3@1.20.1-2%2Bdeb12u5?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libkrb5support0@1.20.1-2%2Bdeb12u5?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/libkeyutils1@1.6.3-2?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/libkrb5-3@1.20.1-2%2Bdeb12u5?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libcom-err2@1.47.0-2%2Bb2?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libk5crypto3@1.20.1-2%2Bdeb12u5?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libkeyutils1@1.6.3-2?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libkrb5support0@1.20.1-2%2Bdeb12u5?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libssl3@3.0.22-1~deb12u1?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/libkrb5support0@1.20.1-2%2Bdeb12u5?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/libldap-2.5-0@2.5.13%2Bdfsg-5?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libgnutls30@3.7.9-2%2Bdeb12u7?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libsasl2-2@2.1.28%2Bdfsg-10?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/libldap-common@2.5.13%2Bdfsg-5?arch=all&distro=debian-12.15",
      "dependsOn": []
    },
    {
      "ref": "pkg:deb/debian/liblz4-1@1.9.4-1?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/liblzma5@5.4.1-1%2Bdeb12u2?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/libmd0@1.0.4-2?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/libmount1@2.38.1-5%2Bdeb12u3?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libblkid1@2.38.1-5%2Bdeb12u3?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libselinux1@3.4-1%2Bb6?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/libnettle8@3.8.1-2?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/libnghttp2-14@1.52.0-1%2Bdeb12u3?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/libp11-kit0@0.24.1-2?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libffi8@3.4.4-1?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/libpam-modules-bin@1.5.2-6%2Bdeb12u2?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libaudit1@3.0.9-1?arch=amd64&distro=debian-12.15&epoch=1",
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libcrypt1@4.4.33-2?arch=amd64&distro=debian-12.15&epoch=1",
        "pkg:deb/debian/libpam0g@1.5.2-6%2Bdeb12u2?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libselinux1@3.4-1%2Bb6?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/libpam-modules@1.5.2-6%2Bdeb12u2?arch=amd64&distro=debian-12.15",
      "dependsOn": []
    },
    {
      "ref": "pkg:deb/debian/libpam-runtime@1.5.2-6%2Bdeb12u2?arch=all&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/debconf@1.5.82?arch=all&distro=debian-12.15",
        "pkg:deb/debian/libpam-modules@1.5.2-6%2Bdeb12u2?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/libpam0g@1.5.2-6%2Bdeb12u2?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/debconf@1.5.82?arch=all&distro=debian-12.15",
        "pkg:deb/debian/libaudit1@3.0.9-1?arch=amd64&distro=debian-12.15&epoch=1",
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/libpcre2-8-0@10.42-1%2Bdeb12u2?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/libpsl5@0.21.2-1?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libidn2-0@2.3.3-1%2Bb1?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libunistring2@1.0-2?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/librtmp1@2.4%2B20151223.gitfa8646d.1-2%2Bb2?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libgmp10@6.2.1%2Bdfsg1-1.1?arch=amd64&distro=debian-12.15&epoch=2",
        "pkg:deb/debian/libgnutls30@3.7.9-2%2Bdeb12u7?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libhogweed6@3.8.1-2?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libnettle8@3.8.1-2?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/zlib1g@1.2.13.dfsg-1?arch=amd64&distro=debian-12.15&epoch=1"
      ]
    },
    {
      "ref": "pkg:deb/debian/libsasl2-2@2.1.28%2Bdfsg-10?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libsasl2-modules-db@2.1.28%2Bdfsg-10?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/libsasl2-modules-db@2.1.28%2Bdfsg-10?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libdb5.3@5.3.28%2Bdfsg2-1?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/libsasl2-modules@2.1.28%2Bdfsg-10?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libssl3@3.0.22-1~deb12u1?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/libseccomp2@2.5.4-1%2Bdeb12u1?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/libselinux1@3.4-1%2Bb6?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libpcre2-8-0@10.42-1%2Bdeb12u2?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/libsemanage-common@3.4-1?arch=all&distro=debian-12.15",
      "dependsOn": []
    },
    {
      "ref": "pkg:deb/debian/libsemanage2@3.4-1%2Bb5?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libaudit1@3.0.9-1?arch=amd64&distro=debian-12.15&epoch=1",
        "pkg:deb/debian/libbz2-1.0@1.0.8-5%2Bb1?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libselinux1@3.4-1%2Bb6?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libsemanage-common@3.4-1?arch=all&distro=debian-12.15",
        "pkg:deb/debian/libsepol2@3.4-2.1?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/libsepol2@3.4-2.1?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/libsmartcols1@2.38.1-5%2Bdeb12u3?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/libss2@1.47.0-2%2Bb2?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libcom-err2@1.47.0-2%2Bb2?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/libssh2-1@1.10.0-3%2Bdeb12u1?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libssl3@3.0.22-1~deb12u1?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/zlib1g@1.2.13.dfsg-1?arch=amd64&distro=debian-12.15&epoch=1"
      ]
    },
    {
      "ref": "pkg:deb/debian/libssl3@3.0.22-1~deb12u1?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/libstdc%2B%2B6@12.2.0-14%2Bdeb12u1?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/gcc-12-base@12.2.0-14%2Bdeb12u1?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libgcc-s1@12.2.0-14%2Bdeb12u1?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/libsystemd0@252.39-1~deb12u2?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libcap2@2.66-4%2Bdeb12u3%2Bb1?arch=amd64&distro=debian-12.15&epoch=1",
        "pkg:deb/debian/libgcrypt20@1.10.1-3%2Bdeb12u1?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/liblz4-1@1.9.4-1?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/liblzma5@5.4.1-1%2Bdeb12u2?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libzstd1@1.5.4%2Bdfsg2-5?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/libtasn1-6@4.19.0-2%2Bdeb12u1?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/libtinfo6@6.4-4?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/libudev1@252.39-1~deb12u2?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/libunistring2@1.0-2?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/libuuid1@2.38.1-5%2Bdeb12u3?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/libxxhash0@0.8.1-1?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/libzstd1@1.5.4%2Bdfsg2-5?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/login@4.13%2Bdfsg1-1%2Bdeb12u2?arch=amd64&distro=debian-12.15&epoch=1",
      "dependsOn": []
    },
    {
      "ref": "pkg:deb/debian/logsave@1.47.0-2%2Bb2?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/mawk@1.3.4.20200120-3.1?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/mount@2.38.1-5%2Bdeb12u3?arch=amd64&distro=debian-12.15",
      "dependsOn": []
    },
    {
      "ref": "pkg:deb/debian/ncurses-base@6.4-4?arch=all&distro=debian-12.15",
      "dependsOn": []
    },
    {
      "ref": "pkg:deb/debian/ncurses-bin@6.4-4?arch=amd64&distro=debian-12.15",
      "dependsOn": []
    },
    {
      "ref": "pkg:deb/debian/openssl@3.0.22-1~deb12u1?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libssl3@3.0.22-1~deb12u1?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/passwd@4.13%2Bdfsg1-1%2Bdeb12u2?arch=amd64&distro=debian-12.15&epoch=1",
      "dependsOn": [
        "pkg:deb/debian/libaudit1@3.0.9-1?arch=amd64&distro=debian-12.15&epoch=1",
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libcrypt1@4.4.33-2?arch=amd64&distro=debian-12.15&epoch=1",
        "pkg:deb/debian/libpam-modules@1.5.2-6%2Bdeb12u2?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libpam0g@1.5.2-6%2Bdeb12u2?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libselinux1@3.4-1%2Bb6?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libsemanage2@3.4-1%2Bb5?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/perl-base@5.36.0-7%2Bdeb12u4?arch=amd64&distro=debian-12.15",
      "dependsOn": []
    },
    {
      "ref": "pkg:deb/debian/publicsuffix@20230209.2326-1?arch=all&distro=debian-12.15",
      "dependsOn": []
    },
    {
      "ref": "pkg:deb/debian/sed@4.9-1%2Bdeb12u1?arch=amd64&distro=debian-12.15",
      "dependsOn": []
    },
    {
      "ref": "pkg:deb/debian/sysvinit-utils@3.06-4?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/tar@1.34%2Bdfsg-1.2%2Bdeb12u1?arch=amd64&distro=debian-12.15",
      "dependsOn": []
    },
    {
      "ref": "pkg:deb/debian/tzdata@2026c-0%2Bdeb12u1?arch=all&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/debconf@1.5.82?arch=all&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/usr-is-merged@37~deb12u1?arch=all&distro=debian-12.15",
      "dependsOn": []
    },
    {
      "ref": "pkg:deb/debian/util-linux-extra@2.38.1-5%2Bdeb12u3?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/libaudit1@3.0.9-1?arch=amd64&distro=debian-12.15&epoch=1",
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15",
        "pkg:deb/debian/libsmartcols1@2.38.1-5%2Bdeb12u3?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/util-linux@2.38.1-5%2Bdeb12u3?arch=amd64&distro=debian-12.15",
      "dependsOn": [
        "pkg:deb/debian/util-linux-extra@2.38.1-5%2Bdeb12u3?arch=amd64&distro=debian-12.15"
      ]
    },
    {
      "ref": "pkg:deb/debian/zlib1g@1.2.13.dfsg-1?arch=amd64&distro=debian-12.15&epoch=1",
      "dependsOn": [
        "pkg:deb/debian/libc6@2.36-9%2Bdeb12u14?arch=amd64&distro=debian-12.15"
      ]
    }
  ],
  "vulnerabilities": []
}
```
