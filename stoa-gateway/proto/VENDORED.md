# Envoy Authorization v3

Unmodified upstream import closure of `envoy/service/auth/v3/external_auth.proto`.
`UPSTREAM.lock.json` records repository, immutable commit, path, byte length and
SHA256 for every vendored proto and license. Envoy v1.39.0 is pinned at
8eea3285d6bdb89f8ea34632cfe7ce1608a8f374. UDPA annotations come from cncf/xds.
Licenses are copied in `licenses/` (Envoy/xDS/PGV/googleapis: Apache-2.0;
protobuf: BSD-3-Clause).

Google well-known types use protobuf v25.3, commit
4a2aef570deb2bfb8927426558701e8bfc26f2a4. protobuf v31.1's descriptor extension
range syntax is unsupported by protox 0.10.0; no upstream file was edited to
work around this. These well-known types keep their official wire definitions.

`build.rs` compiles with Cargo.lock-pinned protox **0.10.0** (pure Rust), then
passes its encoded descriptor set to tonic-build 0.12.3 with `skip_protoc_run`.
The descriptor wire format bridges protox's prost 0.14 and tonic's prost 0.13.
Generated Rust lives only in OUT_DIR. Neither network nor protoc is used by the
build. Provision locked Cargo dependencies once, then build/test with
`cargo test -p stoa-gateway --offline --locked`.
