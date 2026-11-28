//! Memory budget & backpressure (CAB-1829)
//!
//! Monitors process RSS and applies backpressure (503 + Retry-After +
//! `Connection: close`) when memory usage crosses a high watermark (default:
//! 80% of the limit). Backpressure is released only once usage falls below a
//! lower watermark (default: 70%), so usage hovering around a single threshold
//! does not flip the gateway on and off at every sample.
//!
//! Memory sampling uses `/proc/self/statm` on Linux and `mach_task_info`
//! on macOS, polled every 5 seconds by a background Tokio task.

use std::path::Path;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use std::time::Duration;

use axum::http::{header, HeaderValue, StatusCode};
use axum::response::{IntoResponse, Response};
use once_cell::sync::Lazy;
use parking_lot::RwLock;
use prometheus::{register_gauge, register_int_counter, Gauge, IntCounter};
use tokio::time::Instant;
use tracing::{info, warn};

use crate::config::Config;

/// Prometheus gauge: current process RSS in bytes.
pub static MEMORY_USAGE_BYTES: Lazy<Gauge> = Lazy::new(|| {
    register_gauge!(
        "gateway_memory_usage_bytes",
        "Current process resident set size in bytes"
    )
    .expect("Failed to create gateway_memory_usage_bytes metric")
});

/// Prometheus gauge: effective process memory limit in bytes.
pub static MEMORY_LIMIT_BYTES: Lazy<Gauge> = Lazy::new(|| {
    register_gauge!(
        "gateway_memory_limit_bytes",
        "Effective process memory limit in bytes (backpressure reference)"
    )
    .expect("Failed to create gateway_memory_limit_bytes metric")
});

/// Prometheus gauge: 1 while memory backpressure is active, else 0.
pub static BACKPRESSURE_ACTIVE: Lazy<Gauge> = Lazy::new(|| {
    register_gauge!(
        "gateway_backpressure_active",
        "1 while memory backpressure is active, 0 otherwise"
    )
    .expect("Failed to create gateway_backpressure_active metric")
});

/// Prometheus counter: requests rejected with 503 by memory backpressure.
///
/// The backpressure middleware runs outside the HTTP metrics middleware, so
/// these rejections are not visible in the generic request counters.
pub static BACKPRESSURE_REJECTIONS_TOTAL: Lazy<IntCounter> = Lazy::new(|| {
    register_int_counter!(
        "gateway_backpressure_rejections_total",
        "Requests rejected with 503 because memory backpressure was active"
    )
    .expect("Failed to create gateway_backpressure_rejections_total metric")
});

/// Prometheus gauge: open file descriptors (sockets included) of the process.
pub static OPEN_FDS: Lazy<Gauge> = Lazy::new(|| {
    register_gauge!(
        "gateway_process_open_fds",
        "Open file descriptors of the gateway process (sockets included)"
    )
    .expect("Failed to create gateway_process_open_fds metric")
});

/// Default ratio of the limit at which backpressure activates.
pub const DEFAULT_HIGH_WATERMARK_RATIO: f64 = 0.80;

/// Default ratio of the limit below which backpressure is released.
pub const DEFAULT_LOW_WATERMARK_RATIO: f64 = 0.70;

/// Polling interval for memory sampling.
const POLL_INTERVAL_SECS: u64 = 5;
const MIB: u64 = 1024 * 1024;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum LimitSource {
    Config,
    CgroupV2,
    CgroupV1,
    Default,
}

impl LimitSource {
    fn as_str(self) -> &'static str {
        match self {
            Self::Config => "config",
            Self::CgroupV2 => "cgroup_v2",
            Self::CgroupV1 => "cgroup_v1",
            Self::Default => "default",
        }
    }
}

fn read_cgroup_limit(path: &Path, source: LimitSource) -> Option<u64> {
    let contents = std::fs::read_to_string(path).ok()?;
    let bytes = contents.trim().parse::<u64>().ok()?;
    // v1 reports LONG_MAX rounded down to a page boundary for an unlimited
    // cgroup on 64-bit Linux (up to 64 KiB pages). v2 uses the string "max".
    if source == LimitSource::CgroupV1 && bytes >= i64::MAX as u64 - 65_535 {
        return None;
    }
    Some(bytes)
}

fn effective_limit(
    limit_mb: u64,
    explicit: bool,
    v2_path: &Path,
    v1_path: &Path,
) -> (u64, LimitSource) {
    let configured_bytes = limit_mb.saturating_mul(MIB);
    let cgroup = [
        (v2_path, LimitSource::CgroupV2),
        (v1_path, LimitSource::CgroupV1),
    ]
    .into_iter()
    .filter_map(|(path, source)| read_cgroup_limit(path, source).map(|bytes| (bytes, source)))
    .min_by_key(|&(bytes, _)| bytes);

    match cgroup {
        Some((bytes, source)) if !explicit || bytes <= configured_bytes => {
            if explicit && bytes < configured_bytes {
                warn!(
                    configured_bytes,
                    cgroup_bytes = bytes,
                    source = source.as_str(),
                    "Configured memory budget exceeds the cgroup limit; using the cgroup limit"
                );
            }
            (bytes, source)
        }
        _ if explicit => (configured_bytes, LimitSource::Config),
        _ => (configured_bytes, LimitSource::Default),
    }
}

/// Monitors process memory and signals backpressure.
#[derive(Clone)]
pub struct MemoryMonitor {
    inner: Arc<Inner>,
}

struct Inner {
    /// Memory limit in bytes.
    limit_bytes: u64,
    /// Backpressure activates when RSS reaches this value (high watermark).
    threshold_bytes: u64,
    /// Backpressure is released only when RSS falls below this value (low watermark).
    release_bytes: u64,
    /// Start of the current uninterrupted backpressure interval, if any.
    pressure_since: RwLock<Option<Instant>>,
    /// Latest RSS reading in bytes.
    current_rss: AtomicU64,
}

/// Hysteresis decision: next backpressure state for an RSS sample.
///
/// - not pressured: activate when `rss >= threshold_bytes`
/// - pressured: stay active until `rss < release_bytes`
pub fn next_pressure_state(
    was_pressured: bool,
    rss: u64,
    threshold_bytes: u64,
    release_bytes: u64,
) -> bool {
    if was_pressured {
        rss >= release_bytes
    } else {
        rss >= threshold_bytes
    }
}

impl MemoryMonitor {
    /// Resolve the runtime memory budget from configuration and container cgroups.
    pub fn for_runtime(config: &Config) -> Self {
        let (limit_bytes, source) = effective_limit(
            config.memory_limit_mb,
            config.memory_limit_explicit,
            Path::new("/sys/fs/cgroup/memory.max"),
            Path::new("/sys/fs/cgroup/memory/memory.limit_in_bytes"),
        );
        let monitor = Self::with_byte_limit(
            limit_bytes,
            config.memory_backpressure_high_ratio,
            config.memory_backpressure_low_ratio,
        );
        info!(
            source = source.as_str(),
            limit_bytes,
            threshold_bytes = monitor.threshold_bytes(),
            release_bytes = monitor.release_bytes(),
            liveness_fail_after_secs = config.backpressure_liveness_fail_after_secs,
            "Memory budget monitor initialized"
        );
        monitor
    }

    /// Create a new monitor with the given limit in megabytes and default
    /// watermarks (activate at 80%, release below 70%).
    pub fn new(limit_mb: u64) -> Self {
        Self::with_watermarks(
            limit_mb,
            DEFAULT_HIGH_WATERMARK_RATIO,
            DEFAULT_LOW_WATERMARK_RATIO,
        )
    }

    /// Create a monitor with explicit watermarks (ratios of the limit).
    ///
    /// Ratios are expected to satisfy `0 < low <= high <= 1` (enforced by
    /// config validation); `low` is clamped to `high` defensively.
    pub fn with_watermarks(limit_mb: u64, high_ratio: f64, low_ratio: f64) -> Self {
        Self::with_byte_limit(limit_mb.saturating_mul(MIB), high_ratio, low_ratio)
    }

    fn with_byte_limit(limit_bytes: u64, high_ratio: f64, low_ratio: f64) -> Self {
        let threshold_bytes = (limit_bytes as f64 * high_ratio) as u64;
        let release_bytes = ((limit_bytes as f64 * low_ratio) as u64).min(threshold_bytes);
        MEMORY_LIMIT_BYTES.set(limit_bytes as f64);
        Self {
            inner: Arc::new(Inner {
                limit_bytes,
                threshold_bytes,
                release_bytes,
                pressure_since: RwLock::new(None),
                current_rss: AtomicU64::new(0),
            }),
        }
    }

    /// Returns true when the process is under memory pressure.
    pub fn under_pressure(&self) -> bool {
        self.inner.pressure_since.read().is_some()
    }

    /// Whether backpressure has lasted at least the liveness grace period.
    pub fn liveness_failed(&self, fail_after_secs: u64) -> bool {
        fail_after_secs != 0
            && self
                .inner
                .pressure_since
                .read()
                .is_some_and(|since| since.elapsed() >= Duration::from_secs(fail_after_secs))
    }

    /// Current RSS in bytes.
    pub fn current_rss(&self) -> u64 {
        self.inner.current_rss.load(Ordering::Relaxed)
    }

    /// Memory limit in bytes.
    pub fn limit_bytes(&self) -> u64 {
        self.inner.limit_bytes
    }

    /// Activation threshold (high watermark) in bytes.
    pub fn threshold_bytes(&self) -> u64 {
        self.inner.threshold_bytes
    }

    /// Release threshold (low watermark) in bytes.
    pub fn release_bytes(&self) -> u64 {
        self.inner.release_bytes
    }

    /// Apply one RSS sample and return the resulting backpressure state.
    pub fn observe(&self, rss: u64) -> bool {
        let inner = &self.inner;
        inner.current_rss.store(rss, Ordering::Relaxed);
        MEMORY_USAGE_BYTES.set(rss as f64);

        let mut pressure_since = inner.pressure_since.write();
        let was_pressured = pressure_since.is_some();
        let now_pressured = next_pressure_state(
            was_pressured,
            rss,
            inner.threshold_bytes,
            inner.release_bytes,
        );
        if now_pressured && !was_pressured {
            *pressure_since = Some(Instant::now());
        } else if !now_pressured {
            *pressure_since = None;
        }
        BACKPRESSURE_ACTIVE.set(if now_pressured { 1.0 } else { 0.0 });
        drop(pressure_since);

        if now_pressured && !was_pressured {
            warn!(
                rss_mb = rss / (1024 * 1024),
                threshold_mb = inner.threshold_bytes / (1024 * 1024),
                release_mb = inner.release_bytes / (1024 * 1024),
                limit_mb = inner.limit_bytes / (1024 * 1024),
                "Memory backpressure ACTIVE — rejecting new requests with 503"
            );
        } else if !now_pressured && was_pressured {
            info!(
                rss_mb = rss / (1024 * 1024),
                release_mb = inner.release_bytes / (1024 * 1024),
                "Memory backpressure RELEASED — accepting requests again"
            );
        }
        now_pressured
    }

    /// Spawn the background polling task.
    pub fn start_polling(&self) {
        let monitor = self.clone();
        tokio::spawn(async move {
            let mut interval =
                tokio::time::interval(tokio::time::Duration::from_secs(POLL_INTERVAL_SECS));
            loop {
                interval.tick().await;
                let rss = read_rss_bytes();
                // A failed sample must not reset active backpressure.
                if rss > 0 {
                    monitor.observe(rss);
                }
                OPEN_FDS.set(read_fd_count() as f64);
            }
        });
    }
}

/// Build a 503 Service Unavailable response with `Retry-After` and
/// `Connection: close`, so rejected clients release their connection instead
/// of keeping it open while the gateway sheds load.
pub fn backpressure_response() -> Response {
    let body = serde_json::json!({
        "error": "SERVICE_UNAVAILABLE",
        "message": "Memory limit exceeded — backpressure active",
        "retry_after": POLL_INTERVAL_SECS,
    });
    let mut resp = (StatusCode::SERVICE_UNAVAILABLE, axum::Json(body)).into_response();
    let headers = resp.headers_mut();
    headers.insert(header::RETRY_AFTER, HeaderValue::from(POLL_INTERVAL_SECS));
    headers.insert(header::CONNECTION, HeaderValue::from_static("close"));
    resp
}

/// Read the current process RSS in bytes.
///
/// - Linux: reads `/proc/self/statm` (field 1 = resident pages).
/// - macOS: uses `mach_task_basic_info` via libc.
/// - Other: returns 0 (backpressure never triggers).
pub fn read_rss_bytes() -> u64 {
    #[cfg(target_os = "linux")]
    {
        read_rss_linux()
    }
    #[cfg(target_os = "macos")]
    {
        read_rss_macos()
    }
    #[cfg(not(any(target_os = "linux", target_os = "macos")))]
    {
        0
    }
}

#[cfg(target_os = "linux")]
fn read_rss_linux() -> u64 {
    // /proc/self/statm: size resident shared text lib data dt (in pages)
    let Ok(data) = std::fs::read_to_string("/proc/self/statm") else {
        return 0;
    };
    let resident_pages: u64 = data
        .split_whitespace()
        .nth(1)
        .and_then(|s| s.parse().ok())
        .unwrap_or(0);
    let page_size = unsafe { libc::sysconf(libc::_SC_PAGESIZE) };
    resident_pages * u64::try_from(page_size).unwrap_or(0)
}

#[cfg(target_os = "macos")]
fn read_rss_macos() -> u64 {
    use std::mem;

    // MACH_TASK_BASIC_INFO = 20
    const MACH_TASK_BASIC_INFO: u32 = 20;

    #[repr(C)]
    #[derive(Default)]
    struct MachTaskBasicInfo {
        virtual_size: u64,
        resident_size: u64,
        resident_size_max: u64,
        user_time: [u32; 2],   // time_value_t
        system_time: [u32; 2], // time_value_t
        policy: i32,
        suspend_count: i32,
    }

    unsafe {
        let mut info: MachTaskBasicInfo = MachTaskBasicInfo::default();
        let mut count = (mem::size_of::<MachTaskBasicInfo>() / mem::size_of::<u32>()) as u32;
        #[allow(deprecated)]
        // libc::mach_task_self deprecated in favor of mach2, but adding mach2 just for this is overkill
        let task = libc::mach_task_self();
        let kr = libc::task_info(
            task,
            MACH_TASK_BASIC_INFO,
            &mut info as *mut _ as *mut i32,
            &mut count,
        );
        if kr == 0 {
            info.resident_size
        } else {
            0
        }
    }
}

/// Read the number of open file descriptors for the current process.
pub fn read_fd_count() -> u64 {
    #[cfg(target_os = "linux")]
    {
        match std::fs::read_dir("/proc/self/fd") {
            Ok(entries) => entries.count() as u64,
            Err(_) => 0,
        }
    }
    #[cfg(not(target_os = "linux"))]
    {
        0
    }
}

/// Read the number of threads in the current process.
pub fn read_thread_count() -> u64 {
    #[cfg(target_os = "linux")]
    {
        let Ok(status) = std::fs::read_to_string("/proc/self/status") else {
            return 0;
        };
        for line in status.lines() {
            if let Some(val) = line.strip_prefix("Threads:") {
                return val.trim().parse().unwrap_or(0);
            }
        }
        0
    }
    #[cfg(not(target_os = "linux"))]
    {
        0
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn monitor_defaults() {
        let m = MemoryMonitor::new(512);
        assert_eq!(m.limit_bytes(), 512 * 1024 * 1024);
        assert_eq!(m.threshold_bytes(), (512.0 * 1024.0 * 1024.0 * 0.80) as u64);
        assert!(!m.under_pressure());
        assert_eq!(m.current_rss(), 0);
    }

    #[test]
    fn monitor_custom_limit() {
        let m = MemoryMonitor::new(1024);
        assert_eq!(m.limit_bytes(), 1024 * 1024 * 1024);
        assert_eq!(
            m.threshold_bytes(),
            (1024.0 * 1024.0 * 1024.0 * 0.80) as u64
        );
    }

    #[test]
    fn effective_memory_limit_uses_config_cgroup_or_default() {
        let dir = tempfile::tempdir().unwrap();
        let v2 = dir.path().join("memory.max");
        let v1 = dir.path().join("memory.limit_in_bytes");
        let limit = |mb, explicit| effective_limit(mb, explicit, &v2, &v1);

        assert_eq!(limit(512, false), (512 * MIB, LimitSource::Default));
        assert_eq!(limit(768, true), (768 * MIB, LimitSource::Config));

        // Preserve the cgroup budget to the byte, including sub-MiB limits.
        let v2_bytes = 1024 * MIB + 4096;
        std::fs::write(&v2, format!("{v2_bytes}\n")).unwrap();
        assert_eq!(limit(512, false), (v2_bytes, LimitSource::CgroupV2));
        assert_eq!(limit(512, true), (512 * MIB, LimitSource::Config));
        assert_eq!(limit(2048, true), (v2_bytes, LimitSource::CgroupV2));

        std::fs::write(&v1, "268435456\n").unwrap();
        assert_eq!(limit(512, false), (256 * MIB, LimitSource::CgroupV1));

        std::fs::write(&v2, "max\n").unwrap();
        assert_eq!(limit(512, false), (256 * MIB, LimitSource::CgroupV1));

        std::fs::write(&v1, "9223372036854771712\n").unwrap();
        assert_eq!(limit(512, false), (512 * MIB, LimitSource::Default));

        std::fs::write(&v2, "malformed\n").unwrap();
        assert_eq!(limit(512, false), (512 * MIB, LimitSource::Default));
    }

    #[test]
    fn backpressure_response_has_503_and_retry_after() {
        let resp = backpressure_response();
        assert_eq!(resp.status(), StatusCode::SERVICE_UNAVAILABLE);
        assert_eq!(
            resp.headers().get("Retry-After").unwrap().to_str().unwrap(),
            "5"
        );
    }

    #[test]
    fn regression_backpressure_response_closes_connection() {
        let resp = backpressure_response();
        assert_eq!(resp.status(), StatusCode::SERVICE_UNAVAILABLE);
        assert_eq!(
            resp.headers()
                .get(header::CONNECTION)
                .unwrap()
                .to_str()
                .unwrap(),
            "close"
        );
    }

    #[test]
    fn regression_backpressure_hysteresis_no_flapping() {
        const MB: u64 = 1024 * 1024;
        // 100 MB limit: activate at 80 MB, release below 70 MB.
        let m = MemoryMonitor::new(100);
        assert_eq!(m.threshold_bytes(), 80 * MB);
        assert_eq!(m.release_bytes(), 70 * MB);

        assert!(!m.observe(79 * MB), "below high watermark: inactive");
        assert!(m.observe(80 * MB), "high watermark reached: active");
        // Usage oscillating inside the 70-80% band must not toggle the state.
        for rss in [
            79 * MB,
            75 * MB,
            71 * MB,
            70 * MB,
            79 * MB + MB / 2,
            72 * MB,
        ] {
            assert!(m.observe(rss), "stays active at {} MB", rss / MB);
        }
        assert!(!m.observe(70 * MB - 1), "below low watermark: released");
        for rss in [70 * MB, 75 * MB, 79 * MB, 80 * MB - 1] {
            assert!(!m.observe(rss), "stays inactive at {} MB", rss / MB);
        }
        assert!(m.observe(80 * MB), "reactivates at high watermark");
    }

    #[test]
    fn hysteresis_custom_watermarks_and_clamp() {
        const MB: u64 = 1024 * 1024;
        let m = MemoryMonitor::with_watermarks(100, 0.9, 0.5);
        assert_eq!(m.threshold_bytes(), 90 * MB);
        assert_eq!(m.release_bytes(), 50 * MB);
        // low > high is clamped to high (no hysteresis, never inverted).
        let m = MemoryMonitor::with_watermarks(100, 0.8, 0.95);
        assert_eq!(m.release_bytes(), m.threshold_bytes());
        assert!(m.observe(80 * MB));
        assert!(!m.observe(80 * MB - 1));
    }

    #[test]
    fn read_rss_returns_nonzero_on_supported_os() {
        let rss = read_rss_bytes();
        // On Linux/macOS this should return the actual RSS; on other platforms 0.
        #[cfg(any(target_os = "linux", target_os = "macos"))]
        assert!(rss > 0, "RSS should be nonzero on supported OS");
        #[cfg(not(any(target_os = "linux", target_os = "macos")))]
        assert_eq!(rss, 0);
    }

    #[test]
    fn metric_is_registered() {
        Lazy::force(&MEMORY_USAGE_BYTES);
        assert!(prometheus::gather()
            .iter()
            .any(|metric| metric.get_name() == "gateway_memory_usage_bytes"));
    }

    #[tokio::test]
    async fn polling_updates_rss() {
        let m = MemoryMonitor::new(512);
        m.start_polling();
        // Wait for at least one poll cycle
        tokio::time::sleep(tokio::time::Duration::from_millis(100)).await;
        // On a real OS, the interval is 5s so the first tick fires immediately
        tokio::time::sleep(tokio::time::Duration::from_secs(1)).await;
        // RSS should have been updated (>0 on supported OS)
        #[cfg(any(target_os = "linux", target_os = "macos"))]
        assert!(m.current_rss() > 0, "Polling should have read RSS");
    }
}
