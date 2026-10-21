# Image triage

Scanned image: `stoa-gateway:standalone`
Git revision in `org.opencontainers.image.revision`: `29955d56cdee022caf3d57442027902d3ae39fad`
Tar: `deploy/standalone/stoa-gateway-standalone.tar` (not committed)
Tar sha256: `08184dcb57c2951adb42dafe16a7cb21ac06dc14fee111514794571ba7bb4a33`
Base: `debian:bookworm-slim` (Trivy detected Debian 12.15), builder `rust:1.93-bookworm`
Scanner: Trivy 0.58.1 (`aquasec/trivy:0.58.1`), `--scanners vuln --ignore-unfixed`
SBOM: `stoa-gateway-standalone.cdx.json`, CycloneDX, 111 components (OS packages). The runtime image has no `Cargo.lock`, so this SBOM does not list Rust crates.

`deploy/standalone/build-image.sh` exits if that scan reports any CRITICAL finding.
On this image the gate is empty: 0 CRITICAL, 0 HIGH.

The same tar with unfixed vulnerabilities included has 1 CRITICAL and 70 HIGH rows (19 unique CVEs). Every one has an empty fixed version (`will_not_fix`, `affected`, or `fix_deferred`). They are accepted below. A Debian fix would fail the script's `--ignore-unfixed` gate and has to be rebuilt, not re-accepted from this table.

| Vulnerability | Packages | Disposition |
| --- | --- | --- |
| CVE-2023-45853 CRITICAL, will_not_fix | zlib1g | MiniZip `zipOpenNewFileInZip4_64` overflow. The gateway does not open zip archives. Accept. |
| CVE-2026-84782 HIGH, affected | libssl3, openssl | DTLS handshake retransmission disclosure. The process uses TLS, not DTLS. No bookworm fix. Accept for Friday and rebuild when Debian ships a fix. |
| CVE-2026-12064, CVE-2026-6276, CVE-2026-8286, CVE-2026-8458, CVE-2026-8927 HIGH | curl, libcurl4 | Only the image `HEALTHCHECK` runs curl, against `http://localhost:8080/health`. No SFTP, cookies, or proxy auth. No fixed version. Accept. |
| CVE-2026-53613, CVE-2026-53615, CVE-2026-76642, CVE-2026-78408, CVE-2026-78409, CVE-2026-78410 HIGH, affected | util-linux and its libraries | mount, nsenter, and libmount bugs. The container is uid 1000, drops all capabilities, and has a read-only root. It does not mount. No fixed version. Accept. |
| CVE-2026-16742 HIGH, fix_deferred | libsystemd0, libudev1 | systemd-homed signature check. systemd is not running in the container. Accept. |
| CVE-2023-2953 HIGH, affected | libldap-2.5-0 | OpenLDAP null deref. Pulled in by curl. The gateway does not speak LDAP. Accept. |
| CVE-2026-54369 HIGH, fix_deferred | libacl1 | libacl symlink traversal. The process does not call libacl. Accept. |
| CVE-2026-41992 HIGH, fix_deferred | gzip | LZH decompression overflow. The process does not invoke gzip. Accept. |
| CVE-2025-69720 HIGH, affected | ncurses, libtinfo6 | Terminal library overflow. The process does not link ncurses for request handling. Accept. |
| CVE-2026-9538 HIGH, fix_deferred | perl-base | `Archive::Tar` denial of service. perl is a base-image essential and is not executed. Accept. |
