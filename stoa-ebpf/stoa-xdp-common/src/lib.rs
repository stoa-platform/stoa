//! Shared types between eBPF XDP program and userspace loader.
//!
//! Keep this crate `#![no_std]`-compatible so the eBPF program can use it.

#![no_std]

/// Maximum entries in the rate limit BPF map.
pub const MAX_ENTRIES: u32 = 65536;

/// Rate limit window in nanoseconds (1 second).
pub const WINDOW_NS: u64 = 1_000_000_000;

/// Default packets-per-second threshold per source IP.
pub const DEFAULT_PPS_LIMIT: u64 = 1000;

/// Key for the per-IP packet counter map.
#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct IpKey {
    pub src_ip: u32,
}

/// Value for the per-IP packet counter map.
#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct IpStats {
    pub packets: u64,
    pub bytes: u64,
    pub last_reset_ns: u64,
}

#[cfg(feature = "user")]
unsafe impl aya::Pod for IpKey {}

#[cfg(feature = "user")]
unsafe impl aya::Pod for IpStats {}
