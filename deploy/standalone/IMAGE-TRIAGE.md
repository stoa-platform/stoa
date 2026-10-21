# Image triage

Scanned image: `stoa-gateway:standalone`
Git revision in `org.opencontainers.image.revision`: `5b648ef4f7adb761ba4f8f5c4cc2fbba2595e2ae`
Tar: `deploy/standalone/stoa-gateway-standalone.tar` (not committed)
Tar sha256: `3b3c92fc3cf5307fe23657b858691e501b260c440bf62a7554e1dcb166a732d2`
Base: `debian:bookworm-slim` (Trivy detected Debian 12.15), builder `rust:1.93-bookworm`
Build: `cargo chef cook --release --locked` and `cargo auditable build --release --locked` (cargo-auditable 0.7.5). The binary is not stripped; `readelf` finds `.dep-v0`.
Scanner: Trivy 0.58.1, `--ignore-unfixed` on the tar. It reports the Rust binary (`lang-pkgs rustbinary app/stoa-gateway`).
SBOM: `stoa-gateway-standalone.cdx.json`, CycloneDX, 414 components, including `pkg:cargo/quick-xml@0.39.4`.

`deploy/standalone/build-image.sh` exits if that scan reports any CRITICAL finding with a fix. On this image the gate is empty: 0 CRITICAL, 0 HIGH.

The same tar with unfixed vulnerabilities included has 1 CRITICAL and 70 HIGH rows, all Debian packages with an empty fixed version. Trivy 0.58.1 reports 0 vulnerabilities on the Rust binary. RustSec still lists two HIGH advisories on `quick-xml` 0.39.4 (fixed in 0.41.0) that this database did not emit. They are accepted below only because this switch publishes no SOAP contract.

| Vulnerability | Packages | Disposition |
| --- | --- | --- |
| RUSTSEC-2026-0194, RUSTSEC-2026-0195 HIGH (fixed in quick-xml 0.41.0; not emitted by Trivy 0.58.1) | quick-xml 0.39.4 | DoS in XML attribute checks and `NsReader`. The crate is linked for the SOAP module. `STOA_SOAP_PROXY_ENABLED` and `STOA_SOAP_BRIDGE_ENABLED` stay false, and no SOAP contract is published on this switch. Accept only while that stays true. Publishing a SOAP contract voids this row; bump to `quick-xml` >= 0.41.0 first. |
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
