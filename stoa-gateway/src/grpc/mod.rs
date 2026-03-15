//! gRPC Protocol Support Module (CAB-1755)
//!
//! Provides gRPC protocol support for the STOA Gateway:
//! - Proto parser: extract service/method/message definitions from `.proto` files
//! - gRPC proxy: HTTP/2 passthrough with auth + rate limiting + metrics
//! - gRPC→MCP bridge: expose gRPC services as MCP tools (JSON↔gRPC-web)

pub mod bridge;
pub mod proto_parser;
pub mod proxy;
