//! Envoy gRPC adapter for the shared authorization engine.
pub mod ext_authz_grpc;
// Generated upstream messages include documentation examples that are not Rust.
#[allow(clippy::all, rustdoc::broken_intra_doc_links)]
pub mod proto {
    include!(concat!(env!("OUT_DIR"), "/envoy.rs"));
}
