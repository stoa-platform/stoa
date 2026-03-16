//! STOA TC Classifier — HTTP path extraction + policy enforcement + audit (CAB-1843)
//!
//! TC (Traffic Control) eBPF program that inspects HTTP traffic post-TLS:
//! 1. Parses HTTP method + path from first 256 bytes of TCP payload
//! 2. Hashes path → looks up per-API metrics + policy in BPF HashMaps
//! 3. Enforces rate limit / block rules from policy map
//! 4. Pushes audit events via PerfEventArray
//!
//! Attach: `tc qdisc add dev eth0 clsact && tc filter add dev eth0 ingress bpf ...`

#![no_std]
#![no_main]

use aya_ebpf::{
    bindings::TC_ACT_OK,
    bindings::TC_ACT_PIPE,
    bindings::TC_ACT_SHOT,
    macros::{classifier, map},
    maps::{HashMap, PerfEventArray},
    programs::TcContext,
};
use aya_log_ebpf::info;
use core::mem;
use network_types::{eth::EthHdr, ip::Ipv4Hdr, tcp::TcpHdr};
use stoa_xdp_common::{ApiKey, ApiPolicy, ApiStats, AuditEvent, MAX_API_ENTRIES, WINDOW_NS};

// --- BPF Maps ---

/// Per-API metrics: key = path hash, value = {packets, bytes, last_reset_ns}
#[map]
static API_STATS: HashMap<ApiKey, ApiStats> = HashMap::with_max_entries(MAX_API_ENTRIES, 0);

/// Per-API policy: key = path hash, value = {max_pps, blocked}
/// Populated by userspace from policies.json
#[map]
static API_POLICY: HashMap<ApiKey, ApiPolicy> = HashMap::with_max_entries(MAX_API_ENTRIES, 0);

/// Audit event stream to userspace
#[map]
static AUDIT_EVENTS: PerfEventArray<AuditEvent> = PerfEventArray::new(0);

// --- Constants ---

const ETH_P_IP: u16 = 0x0800;
const IPPROTO_TCP: u8 = 6;
const MAX_HTTP_SCAN: usize = 256;

// --- Entry Point ---

#[classifier]
pub fn stoa_tc_classify(ctx: TcContext) -> i32 {
    match try_classify(ctx) {
        Ok(action) => action,
        Err(_) => TC_ACT_PIPE,
    }
}

fn try_classify(ctx: TcContext) -> Result<i32, ()> {
    // Parse Ethernet
    let ethhdr: EthHdr = ctx.load(0).map_err(|_| ())?;
    if u16::from_be(ethhdr.h_proto) != ETH_P_IP {
        return Ok(TC_ACT_PIPE);
    }

    // Parse IPv4
    let ipv4hdr: Ipv4Hdr = ctx.load(EthHdr::LEN).map_err(|_| ())?;
    if ipv4hdr.proto != IPPROTO_TCP {
        return Ok(TC_ACT_PIPE);
    }
    let src_ip = u32::from_be(ipv4hdr.src_addr);
    let ip_hdr_len = ((ipv4hdr.version_ihl & 0x0F) as usize) * 4;

    // Parse TCP
    let tcp_offset = EthHdr::LEN + ip_hdr_len;
    let tcphdr: TcpHdr = ctx.load(tcp_offset).map_err(|_| ())?;
    let tcp_hdr_len = ((tcphdr.doff() as usize) & 0x0F) * 4;

    // HTTP payload offset
    let payload_offset = tcp_offset + tcp_hdr_len;
    let pkt_len = (ctx.len() as usize).saturating_sub(payload_offset);

    // Skip non-HTTP (SYN/ACK/FIN or empty payload)
    if pkt_len < 8 {
        return Ok(TC_ACT_PIPE);
    }

    // Read first bytes to check for HTTP method
    let scan_len = if pkt_len < MAX_HTTP_SCAN {
        pkt_len
    } else {
        MAX_HTTP_SCAN
    };

    // Read HTTP method (bounded: max 8 chars before space)
    let mut method_hash: u32 = 0x811c_9dc5; // FNV-1a offset basis
    let mut i = 0usize;
    while i < 8 && i < scan_len {
        let byte: u8 = ctx.load(payload_offset + i).map_err(|_| ())?;
        if byte == b' ' {
            break;
        }
        method_hash ^= byte as u32;
        method_hash = method_hash.wrapping_mul(0x0100_0193); // FNV-1a prime
        i += 1;
    }

    // Skip space after method
    if i >= scan_len {
        return Ok(TC_ACT_PIPE);
    }
    i += 1; // skip space

    // Read path (bounded: max 247 chars before space or \r)
    let mut path_hash: u32 = 0x811c_9dc5;
    let path_start = i;
    while i < scan_len && (i - path_start) < 247 {
        let byte: u8 = ctx.load(payload_offset + i).map_err(|_| ())?;
        if byte == b' ' || byte == b'\r' || byte == b'?' {
            break;
        }
        path_hash ^= byte as u32;
        path_hash = path_hash.wrapping_mul(0x0100_0193);
        i += 1;
    }

    let api_key = ApiKey { path_hash };
    let now_ns = unsafe { aya_ebpf::helpers::bpf_ktime_get_ns() };
    let pkt_bytes = ctx.len() as u64;

    // --- Metrics ---
    if let Some(stats) = API_STATS.get_ptr_mut(&api_key) {
        let stats = unsafe { &mut *stats };
        if now_ns - stats.last_reset_ns >= WINDOW_NS {
            stats.packets = 1;
            stats.bytes = pkt_bytes;
            stats.last_reset_ns = now_ns;
        } else {
            stats.packets += 1;
            stats.bytes += pkt_bytes;
        }
    } else {
        let new_stats = ApiStats {
            packets: 1,
            bytes: pkt_bytes,
            last_reset_ns: now_ns,
        };
        let _ = API_STATS.insert(&api_key, &new_stats, 0);
    }

    // --- Policy Enforcement ---
    let mut action = TC_ACT_PIPE;
    let mut action_code: u8 = 0; // 0=pass, 1=blocked, 2=rate-limited

    if let Some(policy) = unsafe { API_POLICY.get(&api_key) } {
        if policy.blocked != 0 {
            action = TC_ACT_SHOT;
            action_code = 1;
        } else if policy.max_pps > 0 {
            if let Some(stats) = unsafe { API_STATS.get(&api_key) } {
                if stats.packets > policy.max_pps {
                    action = TC_ACT_SHOT;
                    action_code = 2;
                }
            }
        }
    }

    // --- Audit Event ---
    let event = AuditEvent {
        timestamp_ns: now_ns,
        src_ip,
        method_hash,
        path_hash,
        action: action_code,
        bytes: pkt_bytes,
    };
    AUDIT_EVENTS.output(&ctx, &event, 0);

    Ok(action)
}

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}
