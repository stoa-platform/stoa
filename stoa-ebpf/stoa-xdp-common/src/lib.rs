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

// --- TC (Traffic Control) types (CAB-1843) ---

/// Maximum entries in per-API BPF maps.
pub const MAX_API_ENTRIES: u32 = 16384;

/// Key for per-API maps: FNV-1a hash of the URL path.
#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct ApiKey {
    pub path_hash: u32,
}

/// Per-API metrics.
#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct ApiStats {
    pub packets: u64,
    pub bytes: u64,
    pub last_reset_ns: u64,
}

/// Per-API policy (loaded from JSON config by userspace).
#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct ApiPolicy {
    /// Max packets per second (0 = unlimited).
    pub max_pps: u64,
    /// 1 = blocked, 0 = allowed.
    pub blocked: u64,
}

/// Audit event pushed from kernel to userspace via perf_event_array.
///
/// Field ordering matters: all u64 fields first, then u32, then u8 — this
/// eliminates internal padding that would leak uninitialized kernel memory
/// through perf_event_array.
#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct AuditEvent {
    pub timestamp_ns: u64,
    pub bytes: u64,
    pub src_ip: u32,
    pub method_hash: u32,
    pub path_hash: u32,
    /// 0 = pass, 1 = blocked, 2 = rate-limited.
    pub action: u8,
    // 3 bytes trailing padding — safe (end of struct, not leaked between fields)
}

// --- Userspace Pod impls ---

#[cfg(feature = "user")]
unsafe impl aya::Pod for IpKey {}

#[cfg(feature = "user")]
unsafe impl aya::Pod for IpStats {}

#[cfg(feature = "user")]
unsafe impl aya::Pod for ApiKey {}

#[cfg(feature = "user")]
unsafe impl aya::Pod for ApiStats {}

#[cfg(feature = "user")]
unsafe impl aya::Pod for ApiPolicy {}

#[cfg(feature = "user")]
unsafe impl aya::Pod for AuditEvent {}
