//! STOA XDP Rate Limiter — Userspace Loader + Prometheus Metrics (CAB-1841)
//!
//! Loads the eBPF XDP program, attaches it to a network interface, and
//! exposes per-IP packet counters as Prometheus metrics on :9191/metrics.
//!
//! Usage:
//!   sudo RUST_LOG=info ./stoa-xdp --iface eth0 --pps-limit 500

use anyhow::Context;
use aya::maps::lru_hash_map::LruHashMap;
use aya::programs::{Xdp, XdpFlags};
use axum::{routing::get, Router};
use clap::Parser;
use log::{info, warn};
use prometheus::{Encoder, IntGauge, IntGaugeVec, Opts, Registry, TextEncoder};
use std::net::Ipv4Addr;
use std::sync::Arc;
use stoa_xdp_common::{IpKey, IpStats};
use tokio::sync::RwLock;

#[derive(Debug, Parser)]
#[command(name = "stoa-xdp", about = "STOA eBPF XDP rate limiter")]
struct Opt {
    /// Network interface to attach XDP program to
    #[clap(short, long, default_value = "eth0")]
    iface: String,

    /// Packets-per-second limit per source IP
    #[clap(long, default_value = "1000")]
    pps_limit: u64,

    /// Prometheus metrics listen address (localhost-only by default for security)
    #[clap(long, default_value = "127.0.0.1:9191")]
    metrics_addr: String,

    /// Path to compiled eBPF object file
    #[clap(long, default_value = "target/bpfel-unknown-none/release/stoa-xdp")]
    ebpf_obj: String,
}

/// Prometheus metrics for eBPF XDP rate limiter.
///
/// Uses IntGaugeVec (not IntCounterVec) because BPF map values are absolute
/// snapshots read every second — calling reset() + inc_by() on counters violates
/// the Prometheus monotonic counter contract and breaks rate() queries in Grafana.
///
/// NOTE: src_ip labels contain PII (source IP addresses) under GDPR.
/// In production, consider hashing or aggregating IPs.
struct Metrics {
    packets: IntGaugeVec,
    bytes: IntGaugeVec,
    dropped: IntGaugeVec,
    active_ips: IntGauge,
    registry: Registry,
}

impl Metrics {
    fn new() -> anyhow::Result<Self> {
        let registry = Registry::new();

        let packets = IntGaugeVec::new(
            Opts::new("stoa_ebpf_packets_current", "Current window packets per source IP"),
            &["src_ip"],
        )?;
        let bytes = IntGaugeVec::new(
            Opts::new("stoa_ebpf_bytes_current", "Current window bytes per source IP"),
            &["src_ip"],
        )?;
        let dropped = IntGaugeVec::new(
            Opts::new("stoa_ebpf_dropped_current", "Current window dropped packets (rate limited)"),
            &["src_ip"],
        )?;
        let active_ips = IntGauge::new("stoa_ebpf_active_ips", "Number of active source IPs")?;

        registry.register(Box::new(packets.clone()))?;
        registry.register(Box::new(bytes.clone()))?;
        registry.register(Box::new(dropped.clone()))?;
        registry.register(Box::new(active_ips.clone()))?;

        Ok(Self {
            packets,
            bytes,
            dropped,
            active_ips,
            registry,
        })
    }

    fn encode(&self) -> String {
        let encoder = TextEncoder::new();
        let families = self.registry.gather();
        let mut buf = Vec::new();
        encoder.encode(&families, &mut buf).unwrap_or_default();
        String::from_utf8(buf).unwrap_or_default()
    }
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let opt = Opt::parse();
    env_logger::init();

    info!(
        "STOA XDP rate limiter: iface={}, limit={} pps, metrics={}",
        opt.iface, opt.pps_limit, opt.metrics_addr
    );

    // Load eBPF program
    let bpf_bytes = std::fs::read(&opt.ebpf_obj)
        .with_context(|| format!("failed to read eBPF object: {}", opt.ebpf_obj))?;
    let mut ebpf = aya::Ebpf::load(&bpf_bytes).context("failed to load eBPF program")?;

    // Initialize eBPF logger
    if let Err(e) = aya_log::EbpfLogger::init(&mut ebpf) {
        warn!("eBPF logger init failed (non-fatal): {e}");
    }

    // Attach XDP program
    let program: &mut Xdp = ebpf
        .program_mut("stoa_xdp_ratelimit")
        .context("XDP program not found")?
        .try_into()?;
    program.load()?;
    program
        .attach(&opt.iface, XdpFlags::default())
        .with_context(|| format!("failed to attach XDP to {}", opt.iface))?;

    info!("XDP program attached to {}", opt.iface);

    // Set rate limit in BPF map
    let mut rate_limit: LruHashMap<_, u32, u64> =
        LruHashMap::try_from(ebpf.map_mut("RATE_LIMIT").context("RATE_LIMIT map not found")?)?;
    rate_limit.insert(0, opt.pps_limit, 0)?;
    info!("Rate limit set to {} pps", opt.pps_limit);

    // Set up Prometheus metrics
    let metrics = Arc::new(Metrics::new()?);
    let metrics_clone = metrics.clone();

    // Background task: read BPF maps every second, update Prometheus
    let ebpf = Arc::new(RwLock::new(ebpf));
    let ebpf_reader = ebpf.clone();
    let pps_limit = opt.pps_limit;

    tokio::spawn(async move {
        let mut interval = tokio::time::interval(std::time::Duration::from_secs(1));
        loop {
            interval.tick().await;
            let ebpf = ebpf_reader.read().await;
            let map = match ebpf.map("IP_STATS") {
                Some(m) => m,
                None => {
                    warn!("IP_STATS map not found — eBPF program may have been unloaded");
                    continue;
                }
            };
            let ip_stats: LruHashMap<_, IpKey, IpStats> = match LruHashMap::try_from(map) {
                Ok(m) => m,
                Err(e) => {
                    warn!("failed to read IP_STATS map: {e}");
                    continue;
                }
            };

            let mut count = 0i64;
            for item in ip_stats.iter() {
                if let Ok((key, stats)) = item {
                    let ip = Ipv4Addr::from(key.src_ip);
                    let label = ip.to_string();
                    // Use set() on gauges — absolute values from BPF map snapshots.
                    // Never use reset()+inc_by() on counters (violates monotonic contract).
                    metrics_clone
                        .packets
                        .with_label_values(&[&label])
                        .set(stats.packets as i64);
                    metrics_clone
                        .bytes
                        .with_label_values(&[&label])
                        .set(stats.bytes as i64);
                    if stats.packets > pps_limit {
                        metrics_clone
                            .dropped
                            .with_label_values(&[&label])
                            .set((stats.packets - pps_limit) as i64);
                    } else {
                        metrics_clone
                            .dropped
                            .with_label_values(&[&label])
                            .set(0);
                    }
                    count += 1;
                }
            }
            metrics_clone.active_ips.set(count);
        }
    });

    // Prometheus metrics HTTP server
    let metrics_handler = metrics.clone();
    let app = Router::new().route(
        "/metrics",
        get(move || {
            let m = metrics_handler.clone();
            async move { m.encode() }
        }),
    );

    let listener = tokio::net::TcpListener::bind(&opt.metrics_addr).await?;
    info!("Prometheus metrics on http://{}/metrics", opt.metrics_addr);

    axum::serve(listener, app)
        .with_graceful_shutdown(async {
            tokio::signal::ctrl_c().await.ok();
            info!("Shutting down...");
        })
        .await?;

    Ok(())
}
