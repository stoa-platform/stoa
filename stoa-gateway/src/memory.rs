//! Memory budget & backpressure (CAB-1829)
//!
//! Monitors process RSS and applies backpressure (503 + Retry-After) when
//! memory usage exceeds a configurable threshold (default: 80% of limit).
//!
//! Memory sampling uses `/proc/self/statm` on Linux and `mach_task_info`
//! on macOS, polled every 5 seconds by a background Tokio task.

use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::Arc;

use axum::http::StatusCode;
use axum::response::{IntoResponse, Response};
use once_cell::sync::Lazy;
use prometheus::{register_gauge, Gauge};
use tracing::{info, warn};

/// Prometheus gauge: current process RSS in bytes.
pub static MEMORY_USAGE_BYTES: Lazy<Gauge> = Lazy::new(|| {
    register_gauge!(
        "gateway_memory_usage_bytes",
        "Current process resident set size in bytes"
    )
    .expect("Failed to create gateway_memory_usage_bytes metric")
});

/// Backpressure threshold as a fraction of the memory limit (80%).
const BACKPRESSURE_RATIO: f64 = 0.80;

/// Polling interval for memory sampling.
const POLL_INTERVAL_SECS: u64 = 5;

/// Monitors process memory and signals backpressure.
#[derive(Clone)]
pub struct MemoryMonitor {
    inner: Arc<Inner>,
}

struct Inner {
    /// Memory limit in bytes.
    limit_bytes: u64,
    /// Backpressure threshold in bytes (limit * 0.80).
    threshold_bytes: u64,
    /// True when RSS exceeds the threshold.
    under_pressure: AtomicBool,
    /// Latest RSS reading in bytes.
    current_rss: AtomicU64,
}

impl MemoryMonitor {
    /// Create a new monitor with the given limit in megabytes.
    pub fn new(limit_mb: u64) -> Self {
        let limit_bytes = limit_mb * 1024 * 1024;
        let threshold_bytes = (limit_bytes as f64 * BACKPRESSURE_RATIO) as u64;
        Self {
            inner: Arc::new(Inner {
                limit_bytes,
                threshold_bytes,
                under_pressure: AtomicBool::new(false),
                current_rss: AtomicU64::new(0),
            }),
        }
    }

    /// Returns true when the process is under memory pressure.
    pub fn under_pressure(&self) -> bool {
        self.inner.under_pressure.load(Ordering::Relaxed)
    }

    /// Current RSS in bytes.
    pub fn current_rss(&self) -> u64 {
        self.inner.current_rss.load(Ordering::Relaxed)
    }

    /// Memory limit in bytes.
    pub fn limit_bytes(&self) -> u64 {
        self.inner.limit_bytes
    }

    /// Threshold in bytes.
    pub fn threshold_bytes(&self) -> u64 {
        self.inner.threshold_bytes
    }

    /// Spawn the background polling task.
    pub fn start_polling(&self) {
        let inner = self.inner.clone();
        tokio::spawn(async move {
            let mut interval =
                tokio::time::interval(tokio::time::Duration::from_secs(POLL_INTERVAL_SECS));
            loop {
                interval.tick().await;
                let rss = read_rss_bytes();
                inner.current_rss.store(rss, Ordering::Relaxed);
                MEMORY_USAGE_BYTES.set(rss as f64);

                let was_pressured = inner.under_pressure.load(Ordering::Relaxed);
                let now_pressured = rss >= inner.threshold_bytes;
                inner.under_pressure.store(now_pressured, Ordering::Relaxed);

                if now_pressured && !was_pressured {
                    warn!(
                        rss_mb = rss / (1024 * 1024),
                        threshold_mb = inner.threshold_bytes / (1024 * 1024),
                        limit_mb = inner.limit_bytes / (1024 * 1024),
                        "Memory backpressure ACTIVE — rejecting new requests with 503"
                    );
                } else if !now_pressured && was_pressured {
                    info!(
                        rss_mb = rss / (1024 * 1024),
                        threshold_mb = inner.threshold_bytes / (1024 * 1024),
                        "Memory backpressure RELEASED — accepting requests again"
                    );
                }
            }
        });
    }
}

/// Build a 503 Service Unavailable response with Retry-After header.
pub fn backpressure_response() -> Response {
    let body = serde_json::json!({
        "error": "SERVICE_UNAVAILABLE",
        "message": "Memory limit exceeded — backpressure active",
        "retry_after": POLL_INTERVAL_SECS,
    });
    let mut resp = (StatusCode::SERVICE_UNAVAILABLE, axum::Json(body)).into_response();
    resp.headers_mut().insert(
        "Retry-After",
        POLL_INTERVAL_SECS
            .to_string()
            .parse()
            .expect("valid header"),
    );
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
    let page_size = unsafe { libc::sysconf(libc::_SC_PAGESIZE) } as u64;
    resident_pages * page_size
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
    fn backpressure_flag() {
        let m = MemoryMonitor::new(512);
        // Manually set pressure
        m.inner.under_pressure.store(true, Ordering::Relaxed);
        assert!(m.under_pressure());
        m.inner.under_pressure.store(false, Ordering::Relaxed);
        assert!(!m.under_pressure());
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
        // Force-initialize the metric and verify it exists
        Lazy::force(&MEMORY_USAGE_BYTES);
        MEMORY_USAGE_BYTES.set(42.0);
        assert_eq!(MEMORY_USAGE_BYTES.get() as u64, 42);
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
