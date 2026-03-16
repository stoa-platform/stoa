//! STOA XDP Rate Limiter — eBPF kernel program (CAB-1841)
//!
//! Attaches to a network interface via XDP. For each IPv4 packet:
//! 1. Extracts source IP from the IP header
//! 2. Increments per-IP packet/byte counters in a BPF HashMap
//! 3. If packets-per-second exceeds the limit → XDP_DROP
//! 4. Otherwise → XDP_PASS
//!
//! The userspace loader reads the map for Prometheus metrics and can
//! update the rate limit threshold at runtime.

#![no_std]
#![no_main]

use aya_ebpf::{
    bindings::xdp_action,
    macros::{map, xdp},
    maps::HashMap,
    programs::XdpContext,
};
use aya_log_ebpf::info;
use core::mem;
use network_types::{
    eth::{EthHdr, EtherType},
    ip::Ipv4Hdr,
};
use stoa_xdp_common::{IpKey, IpStats, MAX_ENTRIES, DEFAULT_PPS_LIMIT, WINDOW_NS};

/// Per-IP packet/byte counters + rate limit state.
#[map]
static IP_STATS: HashMap<IpKey, IpStats> = HashMap::with_max_entries(MAX_ENTRIES, 0);

/// Rate limit threshold (packets per second). Updated by userspace.
#[map]
static RATE_LIMIT: HashMap<u32, u64> = HashMap::with_max_entries(1, 0);

#[xdp]
pub fn stoa_xdp_ratelimit(ctx: XdpContext) -> u32 {
    match try_ratelimit(ctx) {
        Ok(action) => action,
        Err(_) => xdp_action::XDP_ABORTED,
    }
}

#[inline(always)]
fn try_ratelimit(ctx: XdpContext) -> Result<u32, ()> {
    // Parse Ethernet header
    let ethhdr: *const EthHdr = ptr_at(&ctx, 0)?;
    if unsafe { (*ethhdr).ether_type } != EtherType::Ipv4 {
        return Ok(xdp_action::XDP_PASS);
    }

    // Parse IPv4 header
    let ipv4hdr: *const Ipv4Hdr = ptr_at(&ctx, EthHdr::LEN)?;
    let src_ip = u32::from_be(unsafe { (*ipv4hdr).src_addr });
    let pkt_len = (ctx.data_end() - ctx.data()) as u64;

    let key = IpKey { src_ip };
    let now_ns = unsafe { aya_ebpf::helpers::bpf_ktime_get_ns() };

    // Read current rate limit (userspace-configurable, default 1000 pps)
    let limit = unsafe {
        RATE_LIMIT.get(&0).copied().unwrap_or(DEFAULT_PPS_LIMIT)
    };

    // Update or create per-IP stats
    let action = if let Some(stats) = unsafe { IP_STATS.get_ptr_mut(&key) } {
        let stats = unsafe { &mut *stats };
        // Reset window if expired
        if now_ns - stats.last_reset_ns >= WINDOW_NS {
            stats.packets = 1;
            stats.bytes = pkt_len;
            stats.last_reset_ns = now_ns;
            xdp_action::XDP_PASS
        } else {
            stats.packets += 1;
            stats.bytes += pkt_len;
            if stats.packets > limit {
                xdp_action::XDP_DROP
            } else {
                xdp_action::XDP_PASS
            }
        }
    } else {
        let new_stats = IpStats {
            packets: 1,
            bytes: pkt_len,
            last_reset_ns: now_ns,
        };
        let _ = IP_STATS.insert(&key, &new_stats, 0);
        xdp_action::XDP_PASS
    };

    if action == xdp_action::XDP_DROP {
        info!(&ctx, "RATE LIMITED: src={:i} pkts>{}", src_ip, limit);
    }

    Ok(action)
}

#[inline(always)]
fn ptr_at<T>(ctx: &XdpContext, offset: usize) -> Result<*const T, ()> {
    let start = ctx.data();
    let end = ctx.data_end();
    let len = mem::size_of::<T>();
    if start + offset + len > end {
        return Err(());
    }
    Ok((start + offset) as *const T)
}

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}
