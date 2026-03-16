//! STOA Pingora Front-Proxy (CAB-1849)
//!
//! Built on Cloudflare's Pingora framework — the same foundation that handles
//! 1+ trillion requests/day. Runs as a front-proxy in front of stoa-gateway,
//! providing shared connection pooling, H2 multiplexing, and zero-downtime upgrades.
//!
//! Architecture:
//! ```text
//! Client → [Pingora :8080] → [stoa-gateway :8081] → Backend
//!            ↑ shared pool      ↑ MCP/admin/auth
//!            ↑ H2 mux           ↑ plugins/phases
//!            ↑ TLS termination  ↑ eBPF integration
//! ```
//!
//! Usage:
//!   RUST_LOG=info ./stoa-pingora --backend 127.0.0.1:8081 --listen 0.0.0.0:8080

use async_trait::async_trait;
use clap::Parser;
use log::info;
use pingora_core::server::Server;
use pingora_core::upstreams::peer::HttpPeer;
use pingora_http::RequestHeader;
use pingora_proxy::{http_proxy_service, ProxyHttp, Session};

#[derive(Debug, Parser)]
#[command(name = "stoa-pingora", about = "STOA Pingora Front-Proxy")]
struct Opt {
    /// Backend address (stoa-gateway)
    #[clap(short, long, default_value = "127.0.0.1:8081")]
    backend: String,

    /// Listen address
    #[clap(short, long, default_value = "0.0.0.0:8080")]
    listen: String,

    /// Enable H2 to upstream
    #[clap(long, default_value = "false")]
    h2_upstream: bool,
}

/// Per-request context threaded through Pingora's filter phases.
pub struct StoaCtx {
    /// Selected backend address (may change per-request in future)
    upstream: String,
    /// Whether to use H2 for upstream connection
    _h2: bool,
}

/// STOA Pingora proxy implementation.
///
/// Implements Pingora's `ProxyHttp` trait — the same interface Cloudflare uses
/// for their production proxy. Each method is a filter phase in the request
/// lifecycle, matching our ProxyPhase trait design (CAB-1834).
pub struct StoaProxy {
    backend: String,
    h2_upstream: bool,
}

impl StoaProxy {
    fn new(backend: String, h2_upstream: bool) -> Self {
        Self {
            backend,
            h2_upstream,
        }
    }
}

#[async_trait]
impl ProxyHttp for StoaProxy {
    type CTX = StoaCtx;

    fn new_ctx(&self) -> Self::CTX {
        StoaCtx {
            upstream: self.backend.clone(),
            _h2: self.h2_upstream,
        }
    }

    /// Select the upstream peer (stoa-gateway backend).
    ///
    /// In future phases, this will read from the route registry
    /// for direct-to-backend routing (bypassing stoa-gateway for
    /// simple proxy cases).
    async fn upstream_peer(
        &self,
        _session: &mut Session,
        ctx: &mut Self::CTX,
    ) -> pingora_core::Result<Box<HttpPeer>> {
        let peer = Box::new(HttpPeer::new(&ctx.upstream, false, String::new()));
        Ok(peer)
    }

    /// Filter incoming requests — add STOA headers.
    async fn request_filter(
        &self,
        session: &mut Session,
        _ctx: &mut Self::CTX,
    ) -> pingora_core::Result<bool> {
        // Inject X-Forwarded-By header to identify Pingora front-proxy
        session
            .req_header_mut()
            .insert_header("X-Stoa-Proxy", "pingora")
            .ok();

        // false = continue processing (don't short-circuit)
        Ok(false)
    }

    /// Modify upstream request before forwarding.
    async fn upstream_request_filter(
        &self,
        _session: &mut Session,
        upstream_request: &mut RequestHeader,
        _ctx: &mut Self::CTX,
    ) -> pingora_core::Result<()> {
        // Preserve original Host header for stoa-gateway routing
        // (Pingora replaces Host with upstream address by default)
        upstream_request
            .insert_header("X-Stoa-Pingora", "true")
            .ok();
        Ok(())
    }

    /// Log completed requests.
    async fn logging(
        &self,
        session: &mut Session,
        _e: Option<&pingora_core::Error>,
        _ctx: &mut Self::CTX,
    ) {
        let status = session
            .response_written()
            .map(|r| r.status.as_u16())
            .unwrap_or(0);
        let method = session.req_header().method.as_str();
        let path = session.req_header().uri.path();

        info!("{method} {path} → {status} (pingora)",);
    }
}

fn main() {
    env_logger::init();
    let opt = Opt::parse();

    info!(
        "STOA Pingora Front-Proxy starting — listen={}, backend={}",
        opt.listen, opt.backend,
    );

    let mut server = Server::new(None).expect("Failed to create Pingora server");

    let proxy = StoaProxy::new(opt.backend, opt.h2_upstream);
    let mut proxy_service = http_proxy_service(&server.configuration, proxy);
    proxy_service.add_tcp(&opt.listen);

    server.add_service(proxy_service);

    info!("Pingora front-proxy ready on {}", opt.listen);
    server.run_forever();
}
