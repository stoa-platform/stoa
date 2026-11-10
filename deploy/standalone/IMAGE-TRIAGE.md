# Image triage

## Identity

Scanned image: `stoa-gateway:standalone`
Label `org.opencontainers.image.revision`: `254a3f8d01ec48b431c595f3e3ccbf3217d4009e`
That value is `git rev-parse HEAD` at build time (`deploy/standalone/build-image.sh`, `STOA_REVISION` unset). It is the commit that routes contract paths with parameters and derives MCP tools from published contracts. The runtime stage and the dependency set are those of the previous image (`ae6d3b868b399c21a05680268b7a6fdea48b50b7`): `git diff ae6d3b868b399c21a05680268b7a6fdea48b50b7 254a3f8d01ec48b431c595f3e3ccbf3217d4009e -- stoa-gateway/Dockerfile stoa-gateway/Cargo.toml stoa-gateway/Cargo.lock` is empty.
Tar: `deploy/standalone/stoa-gateway-standalone.tar` (not committed)
Tar sha256: `ecd4c89786a2a9c0b13ee5c8a1a28dc31277dfe698d92fcfe953d782bac85a44`
Base: `gcr.io/distroless/cc-debian13@sha256:e1f5543d45a2cd7c02a5b43dda5f0ff30729b4832113759d01ed39b0b152cddb` (Trivy detected Debian 13.7), builder `rust:1.93-bookworm`. No shell, no package manager, no curl, no `HEALTHCHECK`; user `1000:1000`. `build-image.sh` checks this on every build.
OS packages (14): base-files 13.8+deb13u7, ca-certificates 20250419+deb13u1, gcc-14-base 14.2.0-19, libc6 2.41-12+deb13u4, libgcc-s1 14.2.0-19, libgomp1 14.2.0-19, libssl3t64 3.5.7-1~deb13u3, libstdc++6 14.2.0-19, libzstd1 1.5.7+dfsg-1, media-types 13.0.0, netbase 6.5, tzdata 2026f-0+deb13u1, tzdata-legacy 2026f-0+deb13u1, zlib1g 1:1.3.dfsg+really1.3.1-1+deb13u1.
Size: 63 MB (160 MB on the Debian runtime).
Build: `cargo chef cook --release --locked` and `cargo auditable build --release --locked` (cargo-auditable 0.7.5). The binary is not stripped; `readelf` finds `.dep-v0`.
Build host: macOS arm64, Docker Desktop 29.6.1, `DOCKER_DEFAULT_PLATFORM=linux/amd64`. The image is `linux/amd64`. Trivy 0.58.1 ran from the `aquasec/trivy:0.58.1` container: the script's fallback downloads a Linux binary.
Built and scanned on the build host, then imported on worker-3, on 2026-11-10. In service since 23:30 UTC. Config digest on the node: `sha256:fac4932faa7fa4baf1874043966f480b5b16a66ebbaf5dde4a12316c0f07cc8f`.

Previous images, kept on worker-3 for rollback:

| Tag on worker-3 | Revision | In service |
| --- | --- | --- |
| `stoa-gateway:standalone-prev-ae6d3b86` | `ae6d3b868b399c21a05680268b7a6fdea48b50b7` | 2026-11-10, 20:23 to 23:30 UTC, the first image on the distroless runtime, tar sha256 `76ca7d83d57d93831d35387535782c9daebffa158ad54a54cc4fe7621ebd5fcf`, config digest `sha256:8cff54bde6d618a26e3476ee2e0ee53d7674910d1d651720efaf42d3cac0f798` |
| `stoa-gateway:standalone-prev-36c4c3f9` | `36c4c3f934dd709c53e9f270845458b077741743` | 2026-11-10, 18:35 to 20:23 UTC, the last image on the Debian runtime (`debian:bookworm-slim`), tar sha256 `180d061d540d7c1a3c012d9c1e2d27ddd198485c2ec7eb4ab5e38a6a624b3bfe`, config digest `sha256:02d1a1738252e47703469159ac33f754a43939b0723289bf9be15df5ed473abe` |
| `stoa-gateway:standalone-prev-4e84fae7` | `4e84fae718a14dd6d1e75504cfe6f031cb76ea9d` | 2026-11-10, 17:11 to 18:35 UTC, tar sha256 `f1108188dd87822ad5850ec20954c61f3126f387f3d6beb3644c5871223d0635`, config digest `sha256:ca6a3c050cfb5026344efdb3d80b93a98c5ec935cd08fff9fd59f03a1cb59547` |
| `stoa-gateway:standalone-prev-c2e40501` | `c2e40501a5a0ab696f06b308dbb40fab81447b01` | 2026-11-10, about 15 minutes (tokio 1.54.0) |
| `stoa-gateway:standalone-prev-6d23399e` | `6d23399e4d1a1f4c54a03122640c0469c8b4829c` | 2026-10-21 to 2026-11-10, tar sha256 `c714dbf06d0f7e592d47ae3ee706ffec7dfa52603bbf024beec28162c3a52031` |

This triage commit does not touch the docker context (`stoa-gateway/`, including `Dockerfile` and `Cargo.lock`). Proof, empty at this commit and after it:

```text
git diff 254a3f8d01ec48b431c595f3e3ccbf3217d4009e HEAD -- stoa-gateway/
```

## Disposition

`trivy image --ignore-unfixed=false` on the tar (Trivy 0.58.1, exit 0, database of 2026-11-10) reports Debian 13.7: 46 findings (34 MEDIUM, 12 LOW), no CRITICAL, no HIGH, none with a fixed package, and the Rust binary: 1 MEDIUM. With `--ignore-unfixed`, the build gate, CRITICAL and HIGH are 0. The same gateway on the Debian runtime (revision `36c4c3f9`) reported 421 OS findings (1 CRITICAL, 96 HIGH, 133 MEDIUM, 161 LOW, 30 UNKNOWN). Every OS row accepted for that image named a package this image does not carry (curl, krb5, util-linux, systemd, OpenLDAP, libacl, gzip, ncurses, perl) or a finding Trivy no longer reports on this base (zlib1g, libssl3). `quick-xml` 0.39.4 is not in the Rust report. RustSec still lists two HIGH advisories on it. >= 0.41.0 avant tout câblage SOAP.

| Vulnerability | Packages | Disposition |
| --- | --- | --- |
| RUSTSEC-2026-0194, RUSTSEC-2026-0195 HIGH (not emitted by Trivy 0.58.1) | quick-xml 0.39.4 | DoS in XML attribute checks and `NsReader`. Linked for the SOAP module. `STOA_SOAP_PROXY_ENABLED` and `STOA_SOAP_BRIDGE_ENABLED` stay false, and no SOAP contract is published. Accept only while that stays true. >= 0.41.0 avant tout câblage SOAP. |
| CVE-2026-48504 MEDIUM, fixed in 0.32.1 | opentelemetry_sdk 0.27.1 | Unbounded allocation in W3C baggage propagation. The binary enables the `trace` feature only; baggage is not used. Accept on this image. The bump crosses five minors and is a separate tracing change. |
| 22 identifiers, MEDIUM and LOW, affected, no fixed package in trixie | libc6 | glibc. Below the CRITICAL and HIGH line this triage and the build gate work on: listed in the table below, not triaged one by one. Read again when the base digest moves. |
| 6 identifiers, MEDIUM and LOW, affected, no fixed package in trixie, each reported on four packages | gcc-14-base, libgcc-s1, libgomp1, libstdc++6 | The GCC runtime libraries of the base. The binary links `libgcc_s` only. Same line as glibc. |

Commitment met on 2026-11-10: the runtime base is `gcr.io/distroless/cc-debian13` pinned by digest, which is what `gcr.io/distroless/cc:latest` resolved to that day. The date given was 06/11/2026. `cc-debian12` was scanned the same day and set aside: 65 findings, one of them HIGH with a fixed package (libssl3).

Moving the base digest is a rebuild, a scan and a new triage here.

### Record: the Debian runtime (images until 2026-11-10, 20:23 UTC)

The text below is the triage of the images built on `debian:bookworm-slim`, kept as written but for one heading level. It does not describe the image in service: where it says "this image", "still" or "the commitment below", it speaks of revision `36c4c3f9` and of the state before this build.

`trivy image --ignore-unfixed=false` on the tar (Trivy 0.58.1, exit 0, database of 2026-11-10) reports Debian 12.15: 421 findings (1 CRITICAL, 96 HIGH, 133 MEDIUM, 161 LOW, 30 UNKNOWN) and the Rust binary: 1 MEDIUM. With `--ignore-unfixed`, the build gate, both CRITICAL and HIGH are 0: no finding has a fixed package in bookworm. The scan of 2026-10-21 on revision `6d23399e` reported 364 findings (1 CRITICAL, 70 HIGH, 131 MEDIUM, 161 LOW, 1 UNKNOWN). The rows below are that triage; the changes since are listed under "Rebuild of 2026-11-10". Those counts were first taken on revision `4e84fae7`, built the same day; the scan of this image is the same finding for finding (same base image digest, same `Cargo.lock`). `quick-xml` 0.39.4 is not in that Rust report. RustSec still lists two HIGH advisories on it. >= 0.41.0 avant tout câblage SOAP.

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

#### Rebuild of 2026-11-10, Debian runtime

The CRITICAL is unchanged (`CVE-2023-45853`, zlib1g, will_not_fix, accepted above).

No longer reported at HIGH on this image: `CVE-2026-76642`, `CVE-2026-78408`, `CVE-2026-78409` (util-linux) and `CVE-2026-84782` (libssl3, openssl). Their rows above are kept as the record of the earlier acceptance.

Reported at HIGH and absent from the triage above. The dispositions were written during the rebuild and accepted by Christophe on 2026-11-10.

| Vulnerability | Packages | Disposition |
| --- | --- | --- |
| CVE-2026-112315 to CVE-2026-112323, CVE-2026-119079 HIGH, affected | krb5-locales, libgssapi-krb5-2, libk5crypto3, libkrb5-3, libkrb5support0 | Memory leaks, CPU exhaustion and a null dereference in the MIT krb5 daemons (`kadmind`, KDC). The image runs neither. The libraries are pulled in by curl, which only runs the `HEALTHCHECK` against localhost. Accepted on 2026-11-10. |
| CVE-2026-76844 HIGH, affected | zlib1g | Heap overflow in `gz_write` after a failed `write()` (the `gz*` file API). The gateway binary does not link the system zlib (no `libz-sys` in the SBOM) and nothing in the container writes gzip files. In the table below Trivy prints another advisory's title for this identifier ("webpack-dev-middleware ... Path Traversal"); the description it carries for it, and the package, are the zlib ones. Accepted on 2026-11-10. |

Rust binary: the first rebuild of the day (revision `c2e40501`) carried `CVE-2026-115567`, a race in tokio 1.54.0 timer handling, fixed in 1.54.1. It was in the image of 2026-10-21 as well; Trivy's database did not list it then. This image links tokio 1.54.1 and the finding is gone. `CVE-2026-48504` (opentelemetry_sdk 0.27.1, MEDIUM) is unchanged and accepted above.

The commitment below gives 06/11/2026 for the move to `gcr.io/distroless/cc` pinned by digest. On 2026-11-10 the runtime base is still `debian:bookworm-slim`: that date has passed.

Commitment: migration to `gcr.io/distroless/cc` pinned by digest by 06/11/2026 at the latest. The runtime base is still `debian:bookworm-slim` (a tag, not a digest). That move removes the zlib/MiniZip package and the other Debian rows above. This image is not that base.

## cargo audit

### Run of 2026-11-10

`cargo audit` (cargo-audit 0.22.1, 1446 advisories, database fetched on 2026-11-10) on the lock of revision `4e84fae7`, which this image keeps unchanged, exited 1: seven advisories published since 2026-10-21 were outside the 12 exceptions. Christophe accepted the seven on 2026-11-10. They are now exceptions in `stoa-gateway/.cargo/audit.toml` (19 in all) and `cargo audit` exits 0 on the same lock and the same database.

| Advisory | Crate | In the standalone binary (SBOM) | Disposition |
| --- | --- | --- | --- |
| `RUSTSEC-2026-0387` | crypto-bigint 0.5.5 | yes, through p256 and p384 of jsonwebtoken | Timing variability in operations meant to be constant-time. The gateway verifies JWT signatures with public keys and holds no secret scalar. Accepted on 2026-11-10, on the same ground as `RUSTSEC-2023-0071`. |
| `RUSTSEC-2026-0391` | zstd 0.13.3 | no | Not linked. Exception since 2026-11-10: not in the image. |
| `RUSTSEC-2026-0403`, `RUSTSEC-2026-0398` | zstd-safe 7.3.0 | no | Not linked. Exception since 2026-11-10: not in the image. |
| `RUSTSEC-2026-0418` | libz-sys 1.1.30 | no | Build script issue, crate not linked. Exception since 2026-11-10: not in the image. |
| `RUSTSEC-2026-0388` | pingora-core 0.8.1 | no | Optional `pingora` feature, `FEATURES` is empty. Exception since 2026-11-10: not in the image. |
| `RUSTSEC-2026-0424` | wasmtime 43.0.2 | no | Optional `wasm` feature, like the eight wasmtime exceptions. Exception since 2026-11-10: not in the image. |

The text below is the run of 2026-10-21.

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

Command: `trivy image --input deploy/standalone/stoa-gateway-standalone.tar --ignore-unfixed=false` (Trivy 0.58.1 from `aquasec/trivy:0.58.1`, exit 0), on the image of revision `254a3f8d`.

```text
2026-11-10T23:29:02Z	INFO	[vuln] Vulnerability scanning is enabled
2026-11-10T23:29:02Z	INFO	[secret] Secret scanning is enabled
2026-11-10T23:29:02Z	INFO	[secret] If your scanning is slow, please try '--scanners vuln' to disable secret scanning
2026-11-10T23:29:02Z	INFO	[secret] Please see also https://aquasecurity.github.io/trivy/v0.58/docs/scanner/secret#recommendation for faster secret detection
2026-11-10T23:29:02Z	INFO	Detected OS	family="debian" version="13.7"
2026-11-10T23:29:02Z	INFO	[debian] Detecting vulnerabilities...	os_version="13" pkg_num=14
2026-11-10T23:29:02Z	INFO	Number of language-specific files	num=1
2026-11-10T23:29:02Z	INFO	[rustbinary] Detecting vulnerabilities...
2026-11-10T23:29:02Z	WARN	Using severities from other vendors for some vulnerabilities. Read https://aquasecurity.github.io/trivy/v0.58/docs/scanner/vulnerability#severity-selection for details.

/tmp/claude-stoa/wt-build/deploy/standalone/stoa-gateway-standalone.tar (debian 13.7)
=====================================================================================
Total: 46 (UNKNOWN: 0, LOW: 12, MEDIUM: 34, HIGH: 0, CRITICAL: 0)

┌─────────────┬──────────────────┬──────────┬──────────┬───────────────────┬───────────────┬──────────────────────────────────────────────────────────────┐
│   Library   │  Vulnerability   │ Severity │  Status  │ Installed Version │ Fixed Version │                            Title                             │
├─────────────┼──────────────────┼──────────┼──────────┼───────────────────┼───────────────┼──────────────────────────────────────────────────────────────┤
│ gcc-14-base │ CVE-2026-102010  │ MEDIUM   │ affected │ 14.2.0-19         │               │ gcc-toolset-15-gcc: gcc: gcc-toolset-16: gcc: Denial of      │
│             │                  │          │          │                   │               │ Service via use-after-free in binary heap...                 │
│             │                  │          │          │                   │               │ https://avd.aquasec.com/nvd/cve-2026-102010                  │
│             ├──────────────────┤          │          │                   ├───────────────┼──────────────────────────────────────────────────────────────┤
│             │ CVE-2026-114690  │          │          │                   │               │ gcc: Confirmed out-of-bounds read/write in libstdc++         │
│             │                  │          │          │                   │               │ parallel `std                                                │
│             │                  │          │          │                   │               │ https://avd.aquasec.com/nvd/cve-2026-114690                  │
│             ├──────────────────┤          │          │                   ├───────────────┼──────────────────────────────────────────────────────────────┤
│             │ CVE-2026-114691  │          │          │                   │               │ gcc: Integer wrap in `std                                    │
│             │                  │          │          │                   │               │ https://avd.aquasec.com/nvd/cve-2026-114691                  │
│             ├──────────────────┤          │          │                   ├───────────────┼──────────────────────────────────────────────────────────────┤
│             │ CVE-2026-115455  │          │          │                   │               │ gcc: Stack overflow in std::bitset on libstdc++              │
│             │                  │          │          │                   │               │ https://avd.aquasec.com/nvd/cve-2026-115455                  │
│             ├──────────────────┤          │          │                   ├───────────────┼──────────────────────────────────────────────────────────────┤
│             │ CVE-2026-95619   │          │          │                   │               │ gcc: libstdc++ integer overflow in `new` operator            │
│             │                  │          │          │                   │               │ https://avd.aquasec.com/nvd/cve-2026-95619                   │
│             ├──────────────────┼──────────┤          │                   ├───────────────┼──────────────────────────────────────────────────────────────┤
│             │ CVE-2026-115456  │ LOW      │          │                   │               │ gcc: Out-of-bounds read in std::from_chars                   │
│             │                  │          │          │                   │               │ https://avd.aquasec.com/nvd/cve-2026-115456                  │
├─────────────┼──────────────────┼──────────┤          ├───────────────────┼───────────────┼──────────────────────────────────────────────────────────────┤
│ libc6       │ CVE-2026-18374   │ MEDIUM   │          │ 2.41-12+deb13u4   │               │ glibc: glibc: Heap buffer overflow via attacker-controlled   │
│             │                  │          │          │                   │               │ fopen mode string                                            │
│             │                  │          │          │                   │               │ https://avd.aquasec.com/nvd/cve-2026-18374                   │
│             ├──────────────────┤          │          │                   ├───────────────┼──────────────────────────────────────────────────────────────┤
│             │ CVE-2026-19499   │          │          │                   │               │ glibc: Buffer Overflow in strfmon right-justification        │
│             │                  │          │          │                   │               │ padding                                                      │
│             │                  │          │          │                   │               │ https://avd.aquasec.com/nvd/cve-2026-19499                   │
│             ├──────────────────┤          │          │                   ├───────────────┼──────────────────────────────────────────────────────────────┤
│             │ CVE-2026-19542   │          │          │                   │               │ glibc: Fix out-of-bounds array write in tdelete              │
│             │                  │          │          │                   │               │ https://avd.aquasec.com/nvd/cve-2026-19542                   │
│             ├──────────────────┤          │          │                   ├───────────────┼──────────────────────────────────────────────────────────────┤
│             │ CVE-2026-5435    │          │          │                   │               │ glibc: glibc: Out-of-bounds write via TSIG record processing │
│             │                  │          │          │                   │               │ https://avd.aquasec.com/nvd/cve-2026-5435                    │
│             ├──────────────────┤          │          │                   ├───────────────┼──────────────────────────────────────────────────────────────┤
│             │ CVE-2026-6238    │          │          │                   │               │ glibc: glibc: Application crash or uninitialized memory read │
│             │                  │          │          │                   │               │ via crafted DNS response...                                  │
│             │                  │          │          │                   │               │ https://avd.aquasec.com/nvd/cve-2026-6238                    │
│             ├──────────────────┤          │          │                   ├───────────────┼──────────────────────────────────────────────────────────────┤
│             │ CVE-2026-6368    │          │          │                   │               │ glibc: glibc: Process abort due to invalid memory in wordexp │
│             │                  │          │          │                   │               │ https://avd.aquasec.com/nvd/cve-2026-6368                    │
│             ├──────────────────┤          │          │                   ├───────────────┼──────────────────────────────────────────────────────────────┤
│             │ CVE-2026-6791    │          │          │                   │               │ glibc: Glibc: Denial of Service via stack exhaustion during  │
│             │                  │          │          │                   │               │ tilde expansion                                              │
│             │                  │          │          │                   │               │ https://avd.aquasec.com/nvd/cve-2026-6791                    │
│             ├──────────────────┤          │          │                   ├───────────────┼──────────────────────────────────────────────────────────────┤
│             │ CVE-2026-77117   │          │          │                   │               │ glibc: Non-progress DoS in SHIFT_JISX0213 -&gt               │
│             │                  │          │          │                   │               │ https://avd.aquasec.com/nvd/cve-2026-77117                   │
│             ├──────────────────┤          │          │                   ├───────────────┼──────────────────────────────────────────────────────────────┤
│             │ CVE-2026-80489   │          │          │                   │               │ glibc: Non-progress DoS in EUC_JISX0213 -> UCS-4 conversion  │
│             │                  │          │          │                   │               │ state                                                        │
│             │                  │          │          │                   │               │ https://avd.aquasec.com/nvd/cve-2026-80489                   │
│             ├──────────────────┤          │          │                   ├───────────────┼──────────────────────────────────────────────────────────────┤
│             │ CVE-2026-84243   │          │          │                   │               │ glibc: glibc: Arbitrary code execution via directory         │
│             │                  │          │          │                   │               │ traversal in LANGUAGE environment variable...                │
│             │                  │          │          │                   │               │ https://avd.aquasec.com/nvd/cve-2026-84243                   │
│             ├──────────────────┤          │          │                   ├───────────────┼──────────────────────────────────────────────────────────────┤
│             │ CVE-2026-8674    │          │          │                   │               │ glibc: glibc DNS stub resolver: Denial of Service via long   │
│             │                  │          │          │                   │               │ search domain...                                             │
│             │                  │          │          │                   │               │ https://avd.aquasec.com/nvd/cve-2026-8674                    │
│             ├──────────────────┤          │          │                   ├───────────────┼──────────────────────────────────────────────────────────────┤
│             │ CVE-2026-86805   │          │          │                   │               │ glibc: glibc: Privilege escalation and arbitrary code        │
│             │                  │          │          │                   │               │ execution via TOCTOU race condition...                       │
│             │                  │          │          │                   │               │ https://avd.aquasec.com/nvd/cve-2026-86805                   │
│             ├──────────────────┤          │          │                   ├───────────────┼──────────────────────────────────────────────────────────────┤
│             │ CVE-2026-89092   │          │          │                   │               │ glibc: nscd stack overflow leads to degraded DNS resolution  │
│             │                  │          │          │                   │               │ https://avd.aquasec.com/nvd/cve-2026-89092                   │
│             ├──────────────────┤          │          │                   ├───────────────┼──────────────────────────────────────────────────────────────┤
│             │ CVE-2026-95818   │          │          │                   │               │ glibc: glibc: Local attacker can cause denial of service and │
│             │                  │          │          │                   │               │ information disclosure...                                    │
│             │                  │          │          │                   │               │ https://avd.aquasec.com/nvd/cve-2026-95818                   │
│             ├──────────────────┼──────────┤          │                   ├───────────────┼──────────────────────────────────────────────────────────────┤
│             │ CVE-2010-4756    │ LOW      │          │                   │               │ glibc: glob implementation can cause excessive CPU and       │
│             │                  │          │          │                   │               │ memory consumption due to...                                 │
│             │                  │          │          │                   │               │ https://avd.aquasec.com/nvd/cve-2010-4756                    │
│             ├──────────────────┤          │          │                   ├───────────────┼──────────────────────────────────────────────────────────────┤
│             │ CVE-2018-20796   │          │          │                   │               │ glibc: uncontrolled recursion in function                    │
│             │                  │          │          │                   │               │ check_dst_limits_calc_pos_1 in posix/regexec.c               │
│             │                  │          │          │                   │               │ https://avd.aquasec.com/nvd/cve-2018-20796                   │
│             ├──────────────────┤          │          │                   ├───────────────┼──────────────────────────────────────────────────────────────┤
│             │ CVE-2019-1010022 │          │          │                   │               │ glibc: stack guard protection bypass                         │
│             │                  │          │          │                   │               │ https://avd.aquasec.com/nvd/cve-2019-1010022                 │
│             ├──────────────────┤          │          │                   ├───────────────┼──────────────────────────────────────────────────────────────┤
│             │ CVE-2019-1010023 │          │          │                   │               │ glibc: running ldd on malicious ELF leads to code execution  │
│             │                  │          │          │                   │               │ because of...                                                │
│             │                  │          │          │                   │               │ https://avd.aquasec.com/nvd/cve-2019-1010023                 │
│             ├──────────────────┤          │          │                   ├───────────────┼──────────────────────────────────────────────────────────────┤
│             │ CVE-2019-1010024 │          │          │                   │               │ glibc: ASLR bypass using cache of thread stack and heap      │
│             │                  │          │          │                   │               │ https://avd.aquasec.com/nvd/cve-2019-1010024                 │
│             ├──────────────────┤          │          │                   ├───────────────┼──────────────────────────────────────────────────────────────┤
│             │ CVE-2019-1010025 │          │          │                   │               │ glibc: information disclosure of heap addresses of           │
│             │                  │          │          │                   │               │ pthread_created thread                                       │
│             │                  │          │          │                   │               │ https://avd.aquasec.com/nvd/cve-2019-1010025                 │
│             ├──────────────────┤          │          │                   ├───────────────┼──────────────────────────────────────────────────────────────┤
│             │ CVE-2019-9192    │          │          │                   │               │ glibc: uncontrolled recursion in function                    │
│             │                  │          │          │                   │               │ check_dst_limits_calc_pos_1 in posix/regexec.c               │
│             │                  │          │          │                   │               │ https://avd.aquasec.com/nvd/cve-2019-9192                    │
│             ├──────────────────┤          │          │                   ├───────────────┼──────────────────────────────────────────────────────────────┤
│             │ CVE-2026-97399   │          │          │                   │               │ glibc: glibc: Denial of Service via out-of-bounds read in    │
│             │                  │          │          │                   │               │ strncasecmp                                                  │
│             │                  │          │          │                   │               │ https://avd.aquasec.com/nvd/cve-2026-97399                   │
├─────────────┼──────────────────┼──────────┤          ├───────────────────┼───────────────┼──────────────────────────────────────────────────────────────┤
│ libgcc-s1   │ CVE-2026-102010  │ MEDIUM   │          │ 14.2.0-19         │               │ gcc-toolset-15-gcc: gcc: gcc-toolset-16: gcc: Denial of      │
│             │                  │          │          │                   │               │ Service via use-after-free in binary heap...                 │
│             │                  │          │          │                   │               │ https://avd.aquasec.com/nvd/cve-2026-102010                  │
│             ├──────────────────┤          │          │                   ├───────────────┼──────────────────────────────────────────────────────────────┤
│             │ CVE-2026-114690  │          │          │                   │               │ gcc: Confirmed out-of-bounds read/write in libstdc++         │
│             │                  │          │          │                   │               │ parallel `std                                                │
│             │                  │          │          │                   │               │ https://avd.aquasec.com/nvd/cve-2026-114690                  │
│             ├──────────────────┤          │          │                   ├───────────────┼──────────────────────────────────────────────────────────────┤
│             │ CVE-2026-114691  │          │          │                   │               │ gcc: Integer wrap in `std                                    │
│             │                  │          │          │                   │               │ https://avd.aquasec.com/nvd/cve-2026-114691                  │
│             ├──────────────────┤          │          │                   ├───────────────┼──────────────────────────────────────────────────────────────┤
│             │ CVE-2026-115455  │          │          │                   │               │ gcc: Stack overflow in std::bitset on libstdc++              │
│             │                  │          │          │                   │               │ https://avd.aquasec.com/nvd/cve-2026-115455                  │
│             ├──────────────────┤          │          │                   ├───────────────┼──────────────────────────────────────────────────────────────┤
│             │ CVE-2026-95619   │          │          │                   │               │ gcc: libstdc++ integer overflow in `new` operator            │
│             │                  │          │          │                   │               │ https://avd.aquasec.com/nvd/cve-2026-95619                   │
│             ├──────────────────┼──────────┤          │                   ├───────────────┼──────────────────────────────────────────────────────────────┤
│             │ CVE-2026-115456  │ LOW      │          │                   │               │ gcc: Out-of-bounds read in std::from_chars                   │
│             │                  │          │          │                   │               │ https://avd.aquasec.com/nvd/cve-2026-115456                  │
├─────────────┼──────────────────┼──────────┤          │                   ├───────────────┼──────────────────────────────────────────────────────────────┤
│ libgomp1    │ CVE-2026-102010  │ MEDIUM   │          │                   │               │ gcc-toolset-15-gcc: gcc: gcc-toolset-16: gcc: Denial of      │
│             │                  │          │          │                   │               │ Service via use-after-free in binary heap...                 │
│             │                  │          │          │                   │               │ https://avd.aquasec.com/nvd/cve-2026-102010                  │
│             ├──────────────────┤          │          │                   ├───────────────┼──────────────────────────────────────────────────────────────┤
│             │ CVE-2026-114690  │          │          │                   │               │ gcc: Confirmed out-of-bounds read/write in libstdc++         │
│             │                  │          │          │                   │               │ parallel `std                                                │
│             │                  │          │          │                   │               │ https://avd.aquasec.com/nvd/cve-2026-114690                  │
│             ├──────────────────┤          │          │                   ├───────────────┼──────────────────────────────────────────────────────────────┤
│             │ CVE-2026-114691  │          │          │                   │               │ gcc: Integer wrap in `std                                    │
│             │                  │          │          │                   │               │ https://avd.aquasec.com/nvd/cve-2026-114691                  │
│             ├──────────────────┤          │          │                   ├───────────────┼──────────────────────────────────────────────────────────────┤
│             │ CVE-2026-115455  │          │          │                   │               │ gcc: Stack overflow in std::bitset on libstdc++              │
│             │                  │          │          │                   │               │ https://avd.aquasec.com/nvd/cve-2026-115455                  │
│             ├──────────────────┤          │          │                   ├───────────────┼──────────────────────────────────────────────────────────────┤
│             │ CVE-2026-95619   │          │          │                   │               │ gcc: libstdc++ integer overflow in `new` operator            │
│             │                  │          │          │                   │               │ https://avd.aquasec.com/nvd/cve-2026-95619                   │
│             ├──────────────────┼──────────┤          │                   ├───────────────┼──────────────────────────────────────────────────────────────┤
│             │ CVE-2026-115456  │ LOW      │          │                   │               │ gcc: Out-of-bounds read in std::from_chars                   │
│             │                  │          │          │                   │               │ https://avd.aquasec.com/nvd/cve-2026-115456                  │
├─────────────┼──────────────────┼──────────┤          │                   ├───────────────┼──────────────────────────────────────────────────────────────┤
│ libstdc++6  │ CVE-2026-102010  │ MEDIUM   │          │                   │               │ gcc-toolset-15-gcc: gcc: gcc-toolset-16: gcc: Denial of      │
│             │                  │          │          │                   │               │ Service via use-after-free in binary heap...                 │
│             │                  │          │          │                   │               │ https://avd.aquasec.com/nvd/cve-2026-102010                  │
│             ├──────────────────┤          │          │                   ├───────────────┼──────────────────────────────────────────────────────────────┤
│             │ CVE-2026-114690  │          │          │                   │               │ gcc: Confirmed out-of-bounds read/write in libstdc++         │
│             │                  │          │          │                   │               │ parallel `std                                                │
│             │                  │          │          │                   │               │ https://avd.aquasec.com/nvd/cve-2026-114690                  │
│             ├──────────────────┤          │          │                   ├───────────────┼──────────────────────────────────────────────────────────────┤
│             │ CVE-2026-114691  │          │          │                   │               │ gcc: Integer wrap in `std                                    │
│             │                  │          │          │                   │               │ https://avd.aquasec.com/nvd/cve-2026-114691                  │
│             ├──────────────────┤          │          │                   ├───────────────┼──────────────────────────────────────────────────────────────┤
│             │ CVE-2026-115455  │          │          │                   │               │ gcc: Stack overflow in std::bitset on libstdc++              │
│             │                  │          │          │                   │               │ https://avd.aquasec.com/nvd/cve-2026-115455                  │
│             ├──────────────────┤          │          │                   ├───────────────┼──────────────────────────────────────────────────────────────┤
│             │ CVE-2026-95619   │          │          │                   │               │ gcc: libstdc++ integer overflow in `new` operator            │
│             │                  │          │          │                   │               │ https://avd.aquasec.com/nvd/cve-2026-95619                   │
│             ├──────────────────┼──────────┤          │                   ├───────────────┼──────────────────────────────────────────────────────────────┤
│             │ CVE-2026-115456  │ LOW      │          │                   │               │ gcc: Out-of-bounds read in std::from_chars                   │
│             │                  │          │          │                   │               │ https://avd.aquasec.com/nvd/cve-2026-115456                  │
└─────────────┴──────────────────┴──────────┴──────────┴───────────────────┴───────────────┴──────────────────────────────────────────────────────────────┘

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

CycloneDX from `trivy image --input deploy/standalone/stoa-gateway-standalone.tar --format cyclonedx`, on the image of revision `254a3f8d`. 318 components (302 crates, 14 OS packages), including `pkg:cargo/quick-xml@0.39.4` and `pkg:cargo/tokio@1.54.1`. Same bytes as `deploy/standalone/stoa-gateway-standalone.cdx.json` (not committed).

```json
{
  "$schema": "http://cyclonedx.org/schema/bom-1.6.schema.json",
  "bomFormat": "CycloneDX",
  "specVersion": "1.6",
  "serialNumber": "urn:uuid:5393c4a4-a4e5-4e35-9224-4e5f36d4f91a",
  "version": 1,
  "metadata": {
    "timestamp": "2026-11-10T23:28:38+00:00",
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
      "bom-ref": "e5e87692-5a76-49c1-aab7-d6257537524d",
      "type": "container",
      "name": "/tmp/claude-stoa/wt-build/deploy/standalone/stoa-gateway-standalone.tar",
      "properties": [
        {
          "name": "aquasecurity:trivy:DiffID",
          "value": "sha256:0762a1f6557d1e88a761ab05aa7f65a10dc0e559913ea13befb873d907e1a396"
        },
        {
          "name": "aquasecurity:trivy:DiffID",
          "value": "sha256:187cfc6d1e3e8a40a5e64653bcd3239c140807dcf1c09e48021178705a5a6139"
        },
        {
          "name": "aquasecurity:trivy:DiffID",
          "value": "sha256:1f5d28bd51650f429293f7730ede274b81dc0744aa918bc887133c4ad610258c"
        },
        {
          "name": "aquasecurity:trivy:DiffID",
          "value": "sha256:275a30dd8ce958b21daa9ad962c6fbc09f98306ee2f486b65c9075dc257b1412"
        },
        {
          "name": "aquasecurity:trivy:DiffID",
          "value": "sha256:2cef49adb7d7902c61ecdd385036e3c7fb7c9f0ada96a41901797c77b7daedd7"
        },
        {
          "name": "aquasecurity:trivy:DiffID",
          "value": "sha256:2e7e048c8b43ab2a1f69ee041025502f890b3faaee2053015a3c3e7256d9ec25"
        },
        {
          "name": "aquasecurity:trivy:DiffID",
          "value": "sha256:4cde6b0bb6f50a5f255eef7b2a42162c661cf776b803225dcac9a659e396bb6b"
        },
        {
          "name": "aquasecurity:trivy:DiffID",
          "value": "sha256:4d049f83d9cf21d1f5cc0e11deaf36df02790d0e60c1a3829538fb4b61685368"
        },
        {
          "name": "aquasecurity:trivy:DiffID",
          "value": "sha256:621c35e751a51a9a9dc3e80aa0b7fe8be2a93402ea6ccd307d30852cd7776cda"
        },
        {
          "name": "aquasecurity:trivy:DiffID",
          "value": "sha256:6e18ad80f3d64a8cbbcd1ff2e8a0d5ce7282cf664e816b86183a59d30a618e8a"
        },
        {
          "name": "aquasecurity:trivy:DiffID",
          "value": "sha256:6f1cdceb6a3146f0ccb986521156bef8a422cdbb0863396f7f751f575ba308f4"
        },
        {
          "name": "aquasecurity:trivy:DiffID",
          "value": "sha256:7db505d90756626f425c6c5468eca565c82f589b144ecaa4f411ad9bbf79e614"
        },
        {
          "name": "aquasecurity:trivy:DiffID",
          "value": "sha256:8a3b315d45080ecb38e39d42d28e951303c67c2ce7482bcdbbc3b5424be19013"
        },
        {
          "name": "aquasecurity:trivy:DiffID",
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
        },
        {
          "name": "aquasecurity:trivy:DiffID",
          "value": "sha256:9486261b5a13f63ca6904b36721527ac8f19df53d300560138d69ae9b4c203de"
        },
        {
          "name": "aquasecurity:trivy:DiffID",
          "value": "sha256:ad51d0769d16ba578106a177987dfe3d2e02c1668c852b795b2f6b024068242a"
        },
        {
          "name": "aquasecurity:trivy:DiffID",
          "value": "sha256:af5aa97ebe6ce1604747ec1e21af7136ded391bcabe4acef882e718a87c86bcc"
        },
        {
          "name": "aquasecurity:trivy:DiffID",
          "value": "sha256:b5764396d8d3f88c6c91b8e97022f147ec721afcf85710d96775922e0df881af"
        },
        {
          "name": "aquasecurity:trivy:DiffID",
          "value": "sha256:b64fe4bb89ff075efc03878811052cbaf4f9dd891aed968e9ed6993fedf1f4a7"
        },
        {
          "name": "aquasecurity:trivy:DiffID",
          "value": "sha256:bc5152368100eebfc56f31fbca003ccb57f905125668216777be5663724db7be"
        },
        {
          "name": "aquasecurity:trivy:DiffID",
          "value": "sha256:bd3cdfae1d3fdd83a2231d608969b38b82349777c2fff9a7c12d54f8ac5c9b38"
        },
        {
          "name": "aquasecurity:trivy:DiffID",
          "value": "sha256:c0e409312adc366898967307565f692bb33d43a439d3de48e27d14b742389725"
        },
        {
          "name": "aquasecurity:trivy:DiffID",
          "value": "sha256:c16b2ec4b1493bad1b1de23d659c899e60abb166bda756d02792f0a03ba54a43"
        },
        {
          "name": "aquasecurity:trivy:ImageID",
          "value": "sha256:fac4932faa7fa4baf1874043966f480b5b16a66ebbaf5dde4a12316c0f07cc8f"
        },
        {
          "name": "aquasecurity:trivy:Labels:org.opencontainers.image.revision",
          "value": "254a3f8d01ec48b431c595f3e3ccbf3217d4009e"
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
      "bom-ref": "33a4f387-90c4-40ed-b93e-9cd298c9e9ad",
      "type": "operating-system",
      "name": "debian",
      "version": "13.7",
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
      "bom-ref": "3b1f0d5a-395d-45ec-a48e-db0d561b2dcf",
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
      "bom-ref": "pkg:cargo/ahash@0.8.12",
      "type": "library",
      "name": "ahash",
      "version": "0.8.12",
      "purl": "pkg:cargo/ahash@0.8.12",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
      "bom-ref": "pkg:cargo/tokio@1.54.1",
      "type": "library",
      "name": "tokio",
      "version": "1.54.1",
      "purl": "pkg:cargo/tokio@1.54.1",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "tokio@1.54.1"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
          "value": "sha256:8cbb58306426d2089b8b7a925356b490eb49cc1f2a9ba022ed459a5658d4e2a6"
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
      "bom-ref": "pkg:deb/debian/base-files@13.8%2Bdeb13u7?arch=amd64&distro=debian-13.7",
      "type": "library",
      "supplier": {
        "name": "Santiago Vila <sanvila@debian.org>"
      },
      "name": "base-files",
      "version": "13.8+deb13u7",
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
            "name": "verbatim"
          }
        }
      ],
      "purl": "pkg:deb/debian/base-files@13.8%2Bdeb13u7?arch=amd64&distro=debian-13.7",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:9486261b5a13f63ca6904b36721527ac8f19df53d300560138d69ae9b4c203de"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "base-files@13.8+deb13u7"
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
          "value": "13.8+deb13u7"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/ca-certificates@20250419%2Bdeb13u1?arch=all&distro=debian-13.7",
      "type": "library",
      "supplier": {
        "name": "Julien Cristau <jcristau@debian.org>"
      },
      "name": "ca-certificates",
      "version": "20250419+deb13u1",
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
      "purl": "pkg:deb/debian/ca-certificates@20250419%2Bdeb13u1?arch=all&distro=debian-13.7",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:0762a1f6557d1e88a761ab05aa7f65a10dc0e559913ea13befb873d907e1a396"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "ca-certificates@20250419+deb13u1"
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
          "value": "20250419+deb13u1"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/gcc-14-base@14.2.0-19?arch=amd64&distro=debian-13.7",
      "type": "library",
      "supplier": {
        "name": "Debian GCC Maintainers <debian-gcc@lists.debian.org>"
      },
      "name": "gcc-14-base",
      "version": "14.2.0-19",
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
            "name": "Artistic-2.0"
          }
        },
        {
          "license": {
            "name": "LGPL-2.0-or-later"
          }
        }
      ],
      "purl": "pkg:deb/debian/gcc-14-base@14.2.0-19?arch=amd64&distro=debian-13.7",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:7db505d90756626f425c6c5468eca565c82f589b144ecaa4f411ad9bbf79e614"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "gcc-14-base@14.2.0-19"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "gcc-14"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "19"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "14.2.0"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libc6@2.41-12%2Bdeb13u4?arch=amd64&distro=debian-13.7",
      "type": "library",
      "supplier": {
        "name": "GNU Libc Maintainers <debian-glibc@lists.debian.org>"
      },
      "name": "libc6",
      "version": "2.41-12+deb13u4",
      "licenses": [
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
            "name": "LGPL-2.1+-with-link-exception"
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
            "name": "GPL-2+-with-link-exception"
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
            "name": "FSFAP"
          }
        },
        {
          "license": {
            "name": "Carnegie"
          }
        },
        {
          "license": {
            "name": "Inner-Net"
          }
        },
        {
          "license": {
            "name": "MIT-like-Lord"
          }
        },
        {
          "license": {
            "name": "BSD-like-Spencer"
          }
        },
        {
          "license": {
            "name": "PCRE"
          }
        },
        {
          "license": {
            "name": "BSD-3-clause-Carnegie"
          }
        },
        {
          "license": {
            "name": "Unicode-DFS-2016"
          }
        },
        {
          "license": {
            "name": "BSL-1.0"
          }
        },
        {
          "license": {
            "name": "SunPro"
          }
        },
        {
          "license": {
            "name": "CORE-MATH"
          }
        },
        {
          "license": {
            "name": "BSD-3-clause-Berkeley"
          }
        },
        {
          "license": {
            "name": "BSD-3-clause-WIDE"
          }
        },
        {
          "license": {
            "name": "BSD-2-Clause"
          }
        },
        {
          "license": {
            "name": "BSD-3-clause-Oracle"
          }
        },
        {
          "license": {
            "name": "DEC"
          }
        },
        {
          "license": {
            "name": "IBM"
          }
        },
        {
          "license": {
            "name": "ISC"
          }
        },
        {
          "license": {
            "name": "Univ-Coimbra"
          }
        },
        {
          "license": {
            "name": "public-domain"
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
      "purl": "pkg:deb/debian/libc6@2.41-12%2Bdeb13u4?arch=amd64&distro=debian-13.7",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:8a3b315d45080ecb38e39d42d28e951303c67c2ce7482bcdbbc3b5424be19013"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libc6@2.41-12+deb13u4"
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
          "value": "12+deb13u4"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "2.41"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libgcc-s1@14.2.0-19?arch=amd64&distro=debian-13.7",
      "type": "library",
      "supplier": {
        "name": "Debian GCC Maintainers <debian-gcc@lists.debian.org>"
      },
      "name": "libgcc-s1",
      "version": "14.2.0-19",
      "purl": "pkg:deb/debian/libgcc-s1@14.2.0-19?arch=amd64&distro=debian-13.7",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:c16b2ec4b1493bad1b1de23d659c899e60abb166bda756d02792f0a03ba54a43"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libgcc-s1@14.2.0-19"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "gcc-14"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "19"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "14.2.0"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libgomp1@14.2.0-19?arch=amd64&distro=debian-13.7",
      "type": "library",
      "supplier": {
        "name": "Debian GCC Maintainers <debian-gcc@lists.debian.org>"
      },
      "name": "libgomp1",
      "version": "14.2.0-19",
      "purl": "pkg:deb/debian/libgomp1@14.2.0-19?arch=amd64&distro=debian-13.7",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:1f5d28bd51650f429293f7730ede274b81dc0744aa918bc887133c4ad610258c"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libgomp1@14.2.0-19"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "gcc-14"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "19"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "14.2.0"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libssl3t64@3.5.7-1~deb13u3?arch=amd64&distro=debian-13.7",
      "type": "library",
      "supplier": {
        "name": "Debian OpenSSL Team <pkg-openssl-devel@alioth-lists.debian.net>"
      },
      "name": "libssl3t64",
      "version": "3.5.7-1~deb13u3",
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
      "purl": "pkg:deb/debian/libssl3t64@3.5.7-1~deb13u3?arch=amd64&distro=debian-13.7",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:2cef49adb7d7902c61ecdd385036e3c7fb7c9f0ada96a41901797c77b7daedd7"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libssl3t64@3.5.7-1~deb13u3"
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
          "value": "1~deb13u3"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "3.5.7"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libstdc%2B%2B6@14.2.0-19?arch=amd64&distro=debian-13.7",
      "type": "library",
      "supplier": {
        "name": "Debian GCC Maintainers <debian-gcc@lists.debian.org>"
      },
      "name": "libstdc++6",
      "version": "14.2.0-19",
      "purl": "pkg:deb/debian/libstdc%2B%2B6@14.2.0-19?arch=amd64&distro=debian-13.7",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:6e18ad80f3d64a8cbbcd1ff2e8a0d5ce7282cf664e816b86183a59d30a618e8a"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libstdc++6@14.2.0-19"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "gcc-14"
        },
        {
          "name": "aquasecurity:trivy:SrcRelease",
          "value": "19"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "14.2.0"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/libzstd1@1.5.7%2Bdfsg-1?arch=amd64&distro=debian-13.7",
      "type": "library",
      "supplier": {
        "name": "RPM packaging team <team+pkg-rpm@tracker.debian.org>"
      },
      "name": "libzstd1",
      "version": "1.5.7+dfsg-1",
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
      "purl": "pkg:deb/debian/libzstd1@1.5.7%2Bdfsg-1?arch=amd64&distro=debian-13.7",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:c0e409312adc366898967307565f692bb33d43a439d3de48e27d14b742389725"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "libzstd1@1.5.7+dfsg-1"
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
          "value": "1"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "1.5.7+dfsg"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/media-types@13.0.0?arch=all&distro=debian-13.7",
      "type": "library",
      "supplier": {
        "name": "Mime-Support Packagers <team+debian-mimesupport-packagers@tracker.debian.org>"
      },
      "name": "media-types",
      "version": "13.0.0",
      "licenses": [
        {
          "license": {
            "name": "ad-hoc"
          }
        }
      ],
      "purl": "pkg:deb/debian/media-types@13.0.0?arch=all&distro=debian-13.7",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:275a30dd8ce958b21daa9ad962c6fbc09f98306ee2f486b65c9075dc257b1412"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "media-types@13.0.0"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "media-types"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "13.0.0"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/netbase@6.5?arch=all&distro=debian-13.7",
      "type": "library",
      "supplier": {
        "name": "Marco d'Itri <md@linux.it>"
      },
      "name": "netbase",
      "version": "6.5",
      "licenses": [
        {
          "license": {
            "name": "GPL-2.0-only"
          }
        }
      ],
      "purl": "pkg:deb/debian/netbase@6.5?arch=all&distro=debian-13.7",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:621c35e751a51a9a9dc3e80aa0b7fe8be2a93402ea6ccd307d30852cd7776cda"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "netbase@6.5"
        },
        {
          "name": "aquasecurity:trivy:PkgType",
          "value": "debian"
        },
        {
          "name": "aquasecurity:trivy:SrcName",
          "value": "netbase"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "6.5"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/tzdata-legacy@2026f-0%2Bdeb13u1?arch=all&distro=debian-13.7",
      "type": "library",
      "supplier": {
        "name": "GNU Libc Maintainers <debian-glibc@lists.debian.org>"
      },
      "name": "tzdata-legacy",
      "version": "2026f-0+deb13u1",
      "licenses": [
        {
          "license": {
            "name": "public-domain"
          }
        }
      ],
      "purl": "pkg:deb/debian/tzdata-legacy@2026f-0%2Bdeb13u1?arch=all&distro=debian-13.7",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:b5764396d8d3f88c6c91b8e97022f147ec721afcf85710d96775922e0df881af"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "tzdata-legacy@2026f-0+deb13u1"
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
          "value": "0+deb13u1"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "2026f"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/tzdata@2026f-0%2Bdeb13u1?arch=all&distro=debian-13.7",
      "type": "library",
      "supplier": {
        "name": "GNU Libc Maintainers <debian-glibc@lists.debian.org>"
      },
      "name": "tzdata",
      "version": "2026f-0+deb13u1",
      "licenses": [
        {
          "license": {
            "name": "public-domain"
          }
        }
      ],
      "purl": "pkg:deb/debian/tzdata@2026f-0%2Bdeb13u1?arch=all&distro=debian-13.7",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:b64fe4bb89ff075efc03878811052cbaf4f9dd891aed968e9ed6993fedf1f4a7"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "tzdata@2026f-0+deb13u1"
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
          "value": "0+deb13u1"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "2026f"
        }
      ]
    },
    {
      "bom-ref": "pkg:deb/debian/zlib1g@1.3.dfsg%2Breally1.3.1-1%2Bdeb13u1?arch=amd64&distro=debian-13.7&epoch=1",
      "type": "library",
      "supplier": {
        "name": "Mark Brown <broonie@debian.org>"
      },
      "name": "zlib1g",
      "version": "1:1.3.dfsg+really1.3.1-1+deb13u1",
      "licenses": [
        {
          "license": {
            "name": "Zlib"
          }
        }
      ],
      "purl": "pkg:deb/debian/zlib1g@1.3.dfsg%2Breally1.3.1-1%2Bdeb13u1?arch=amd64&distro=debian-13.7&epoch=1",
      "properties": [
        {
          "name": "aquasecurity:trivy:LayerDiffID",
          "value": "sha256:2e7e048c8b43ab2a1f69ee041025502f890b3faaee2053015a3c3e7256d9ec25"
        },
        {
          "name": "aquasecurity:trivy:PkgID",
          "value": "zlib1g@1:1.3.dfsg+really1.3.1-1+deb13u1"
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
          "value": "1+deb13u1"
        },
        {
          "name": "aquasecurity:trivy:SrcVersion",
          "value": "1.3.dfsg+really1.3.1"
        }
      ]
    }
  ],
  "dependencies": [
    {
      "ref": "33a4f387-90c4-40ed-b93e-9cd298c9e9ad",
      "dependsOn": [
        "pkg:deb/debian/base-files@13.8%2Bdeb13u7?arch=amd64&distro=debian-13.7",
        "pkg:deb/debian/ca-certificates@20250419%2Bdeb13u1?arch=all&distro=debian-13.7",
        "pkg:deb/debian/gcc-14-base@14.2.0-19?arch=amd64&distro=debian-13.7",
        "pkg:deb/debian/libc6@2.41-12%2Bdeb13u4?arch=amd64&distro=debian-13.7",
        "pkg:deb/debian/libgcc-s1@14.2.0-19?arch=amd64&distro=debian-13.7",
        "pkg:deb/debian/libgomp1@14.2.0-19?arch=amd64&distro=debian-13.7",
        "pkg:deb/debian/libssl3t64@3.5.7-1~deb13u3?arch=amd64&distro=debian-13.7",
        "pkg:deb/debian/libstdc%2B%2B6@14.2.0-19?arch=amd64&distro=debian-13.7",
        "pkg:deb/debian/libzstd1@1.5.7%2Bdfsg-1?arch=amd64&distro=debian-13.7",
        "pkg:deb/debian/media-types@13.0.0?arch=all&distro=debian-13.7",
        "pkg:deb/debian/netbase@6.5?arch=all&distro=debian-13.7",
        "pkg:deb/debian/tzdata-legacy@2026f-0%2Bdeb13u1?arch=all&distro=debian-13.7",
        "pkg:deb/debian/tzdata@2026f-0%2Bdeb13u1?arch=all&distro=debian-13.7",
        "pkg:deb/debian/zlib1g@1.3.dfsg%2Breally1.3.1-1%2Bdeb13u1?arch=amd64&distro=debian-13.7&epoch=1"
      ]
    },
    {
      "ref": "3b1f0d5a-395d-45ec-a48e-db0d561b2dcf",
      "dependsOn": [
        "pkg:cargo/stoa-gateway@0.9.25"
      ]
    },
    {
      "ref": "e5e87692-5a76-49c1-aab7-d6257537524d",
      "dependsOn": [
        "33a4f387-90c4-40ed-b93e-9cd298c9e9ad",
        "3b1f0d5a-395d-45ec-a48e-db0d561b2dcf"
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
        "pkg:cargo/tokio@1.54.1",
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
        "pkg:cargo/tokio@1.54.1",
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
        "pkg:cargo/tokio@1.54.1",
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
        "pkg:cargo/tokio@1.54.1",
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
        "pkg:cargo/tokio@1.54.1",
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
        "pkg:cargo/tokio@1.54.1",
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
        "pkg:cargo/tokio@1.54.1",
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
        "pkg:cargo/tokio@1.54.1",
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
        "pkg:cargo/tokio@1.54.1",
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
        "pkg:cargo/tokio@1.54.1",
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
        "pkg:cargo/tokio@1.54.1",
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
        "pkg:cargo/tokio@1.54.1"
      ]
    },
    {
      "ref": "pkg:cargo/tokio-stream@0.1.19",
      "dependsOn": [
        "pkg:cargo/futures-core@0.3.34",
        "pkg:cargo/pin-project-lite@0.2.17",
        "pkg:cargo/tokio@1.54.1"
      ]
    },
    {
      "ref": "pkg:cargo/tokio-tungstenite@0.24.0",
      "dependsOn": [
        "pkg:cargo/futures-util@0.3.34",
        "pkg:cargo/log@0.4.34",
        "pkg:cargo/tokio@1.54.1",
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
        "pkg:cargo/tokio@1.54.1",
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
        "pkg:cargo/tokio@1.54.1"
      ]
    },
    {
      "ref": "pkg:cargo/tokio@1.54.1",
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
        "pkg:cargo/tokio@1.54.1",
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
        "pkg:cargo/tokio@1.54.1",
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
        "pkg:cargo/tokio@1.54.1",
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
      "ref": "pkg:deb/debian/base-files@13.8%2Bdeb13u7?arch=amd64&distro=debian-13.7",
      "dependsOn": []
    },
    {
      "ref": "pkg:deb/debian/ca-certificates@20250419%2Bdeb13u1?arch=all&distro=debian-13.7",
      "dependsOn": []
    },
    {
      "ref": "pkg:deb/debian/gcc-14-base@14.2.0-19?arch=amd64&distro=debian-13.7",
      "dependsOn": []
    },
    {
      "ref": "pkg:deb/debian/libc6@2.41-12%2Bdeb13u4?arch=amd64&distro=debian-13.7",
      "dependsOn": []
    },
    {
      "ref": "pkg:deb/debian/libgcc-s1@14.2.0-19?arch=amd64&distro=debian-13.7",
      "dependsOn": []
    },
    {
      "ref": "pkg:deb/debian/libgomp1@14.2.0-19?arch=amd64&distro=debian-13.7",
      "dependsOn": []
    },
    {
      "ref": "pkg:deb/debian/libssl3t64@3.5.7-1~deb13u3?arch=amd64&distro=debian-13.7",
      "dependsOn": []
    },
    {
      "ref": "pkg:deb/debian/libstdc%2B%2B6@14.2.0-19?arch=amd64&distro=debian-13.7",
      "dependsOn": []
    },
    {
      "ref": "pkg:deb/debian/libzstd1@1.5.7%2Bdfsg-1?arch=amd64&distro=debian-13.7",
      "dependsOn": []
    },
    {
      "ref": "pkg:deb/debian/media-types@13.0.0?arch=all&distro=debian-13.7",
      "dependsOn": []
    },
    {
      "ref": "pkg:deb/debian/netbase@6.5?arch=all&distro=debian-13.7",
      "dependsOn": []
    },
    {
      "ref": "pkg:deb/debian/tzdata-legacy@2026f-0%2Bdeb13u1?arch=all&distro=debian-13.7",
      "dependsOn": []
    },
    {
      "ref": "pkg:deb/debian/tzdata@2026f-0%2Bdeb13u1?arch=all&distro=debian-13.7",
      "dependsOn": []
    },
    {
      "ref": "pkg:deb/debian/zlib1g@1.3.dfsg%2Breally1.3.1-1%2Bdeb13u1?arch=amd64&distro=debian-13.7&epoch=1",
      "dependsOn": []
    }
  ],
  "vulnerabilities": []
}
```
