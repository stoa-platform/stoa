//! Kernel/process metrics self-collection (CAB-1976).
//!
//! Extends the memory polling loop to collect process-level metrics from
//! `/proc/self/` on Linux. Stores a `ProcessSnapshot` in `ArcSwap` for
//! lock-free reads on the hot path (admin endpoint).
//!
//! On macOS, only RSS is available; other fields return `None`.

#[cfg(target_os = "linux")]
use std::sync::atomic::Ordering;
use std::sync::atomic::AtomicU64;
use std::sync::Arc;
use std::time::SystemTime;

use arc_swap::ArcSwap;
use once_cell::sync::Lazy;
use prometheus::{register_gauge, Gauge};
use tracing::debug;

// ─── Prometheus Gauges ───────────────────────────────────────────────

pub static PROCESS_CPU_USER_MS: Lazy<Gauge> = Lazy::new(|| {
    register_gauge!(
        "gateway_process_cpu_user_ms",
        "Process CPU user time delta per poll interval (ms)"
    )
    .expect("metric")
});

pub static PROCESS_CPU_SYS_MS: Lazy<Gauge> = Lazy::new(|| {
    register_gauge!(
        "gateway_process_cpu_sys_ms",
        "Process CPU system time delta per poll interval (ms)"
    )
    .expect("metric")
});

pub static PROCESS_FD_COUNT: Lazy<Gauge> = Lazy::new(|| {
    register_gauge!(
        "gateway_process_fd_count",
        "Number of open file descriptors"
    )
    .expect("metric")
});

pub static PROCESS_THREAD_COUNT: Lazy<Gauge> = Lazy::new(|| {
    register_gauge!(
        "gateway_process_thread_count",
        "Number of threads in the process"
    )
    .expect("metric")
});

pub static PROCESS_CTX_SWITCHES_VOL: Lazy<Gauge> = Lazy::new(|| {
    register_gauge!(
        "gateway_process_ctx_switches_voluntary",
        "Cumulative voluntary context switches"
    )
    .expect("metric")
});

// ─── Snapshot ────────────────────────────────────────────────────────

/// Point-in-time snapshot of process metrics, updated every 5 seconds.
#[derive(Clone, Debug)]
pub struct ProcessSnapshot {
    pub rss_bytes: u64,
    pub virt_bytes: u64,
    pub cpu_user_ms: Option<f64>,
    pub cpu_sys_ms: Option<f64>,
    pub ctx_switches_vol: Option<u64>,
    pub ctx_switches_invol: Option<u64>,
    pub fd_count: Option<u32>,
    pub thread_count: Option<u32>,
    pub sampled_at: SystemTime,
}

impl Default for ProcessSnapshot {
    fn default() -> Self {
        Self {
            rss_bytes: 0,
            virt_bytes: 0,
            cpu_user_ms: None,
            cpu_sys_ms: None,
            ctx_switches_vol: None,
            ctx_switches_invol: None,
            fd_count: None,
            thread_count: None,
            sampled_at: SystemTime::now(),
        }
    }
}

// ─── Collector ───────────────────────────────────────────────────────

/// Background collector that polls `/proc/self/` every 5 seconds.
#[derive(Clone)]
pub struct KernelMetricsCollector {
    snapshot: Arc<ArcSwap<ProcessSnapshot>>,
    prev_utime: Arc<AtomicU64>,
    prev_stime: Arc<AtomicU64>,
}

impl KernelMetricsCollector {
    pub fn new() -> Self {
        Self {
            snapshot: Arc::new(ArcSwap::from_pointee(ProcessSnapshot::default())),
            prev_utime: Arc::new(AtomicU64::new(0)),
            prev_stime: Arc::new(AtomicU64::new(0)),
        }
    }

    /// Get the latest snapshot (lock-free read).
    pub fn snapshot(&self) -> Arc<ProcessSnapshot> {
        self.snapshot.load_full()
    }

    /// Start the background polling task.
    pub fn start_polling(&self) {
        let snapshot = self.snapshot.clone();
        let prev_utime = self.prev_utime.clone();
        let prev_stime = self.prev_stime.clone();

        tokio::spawn(async move {
            let mut interval =
                tokio::time::interval(tokio::time::Duration::from_secs(5));

            // Get ticks-per-second for jiffies → ms conversion
            let ticks_per_sec = get_clock_ticks();

            loop {
                interval.tick().await;

                let (rss, virt) = read_memory();
                let (cpu_user_ms, cpu_sys_ms) =
                    read_cpu_delta(&prev_utime, &prev_stime, ticks_per_sec);
                let (ctx_vol, ctx_invol) = read_context_switches();
                let fd_count = read_fd_count();
                let thread_count = read_thread_count();

                // Update Prometheus gauges
                if let Some(u) = cpu_user_ms {
                    PROCESS_CPU_USER_MS.set(u);
                }
                if let Some(s) = cpu_sys_ms {
                    PROCESS_CPU_SYS_MS.set(s);
                }
                if let Some(fd) = fd_count {
                    PROCESS_FD_COUNT.set(fd as f64);
                }
                if let Some(t) = thread_count {
                    PROCESS_THREAD_COUNT.set(t as f64);
                }
                if let Some(v) = ctx_vol {
                    PROCESS_CTX_SWITCHES_VOL.set(v as f64);
                }

                let snap = ProcessSnapshot {
                    rss_bytes: rss,
                    virt_bytes: virt,
                    cpu_user_ms,
                    cpu_sys_ms,
                    ctx_switches_vol: ctx_vol,
                    ctx_switches_invol: ctx_invol,
                    fd_count,
                    thread_count,
                    sampled_at: SystemTime::now(),
                };

                debug!(
                    rss_mb = rss / (1024 * 1024),
                    fd = fd_count.unwrap_or(0),
                    threads = thread_count.unwrap_or(0),
                    "kernel_metrics poll"
                );

                snapshot.store(Arc::new(snap));
            }
        });
    }
}

// ─── Platform-specific readers ───────────────────────────────────────

fn get_clock_ticks() -> u64 {
    #[cfg(target_os = "linux")]
    {
        let ticks = unsafe { libc::sysconf(libc::_SC_CLK_TCK) };
        if ticks > 0 { ticks as u64 } else { 100 }
    }
    #[cfg(not(target_os = "linux"))]
    {
        100
    }
}

/// Read RSS and VmSize.
fn read_memory() -> (u64, u64) {
    #[cfg(target_os = "linux")]
    {
        let Ok(data) = std::fs::read_to_string("/proc/self/statm") else {
            return (0, 0);
        };
        let mut parts = data.split_whitespace();
        let virt_pages: u64 = parts.next().and_then(|s| s.parse().ok()).unwrap_or(0);
        let rss_pages: u64 = parts.next().and_then(|s| s.parse().ok()).unwrap_or(0);
        let page_size = unsafe { libc::sysconf(libc::_SC_PAGESIZE) } as u64;
        (rss_pages * page_size, virt_pages * page_size)
    }
    #[cfg(target_os = "macos")]
    {
        // Reuse the same mach_task_basic_info approach from memory.rs
        (read_rss_macos(), 0)
    }
    #[cfg(not(any(target_os = "linux", target_os = "macos")))]
    {
        (0, 0)
    }
}

/// Read CPU user/sys delta in ms since last poll.
fn read_cpu_delta(
    prev_utime: &AtomicU64,
    prev_stime: &AtomicU64,
    ticks_per_sec: u64,
) -> (Option<f64>, Option<f64>) {
    #[cfg(target_os = "linux")]
    {
        let Ok(data) = std::fs::read_to_string("/proc/self/stat") else {
            return (None, None);
        };
        // Fields: pid comm state ppid ... (field 14=utime, 15=stime, 1-indexed)
        // The comm field may contain spaces in parens, so find closing ')' first
        let after_comm = match data.find(')') {
            Some(pos) => &data[pos + 2..], // skip ") "
            None => return (None, None),
        };
        let fields: Vec<&str> = after_comm.split_whitespace().collect();
        // After comm: state(0) ppid(1) ... utime(11) stime(12)
        if fields.len() < 13 {
            return (None, None);
        }
        let utime: u64 = fields[11].parse().unwrap_or(0);
        let stime: u64 = fields[12].parse().unwrap_or(0);

        let prev_u = prev_utime.swap(utime, Ordering::Relaxed);
        let prev_s = prev_stime.swap(stime, Ordering::Relaxed);

        // First poll: no delta yet
        if prev_u == 0 && prev_s == 0 {
            return (Some(0.0), Some(0.0));
        }

        let delta_u = utime.saturating_sub(prev_u);
        let delta_s = stime.saturating_sub(prev_s);
        let ms_per_tick = 1000.0 / ticks_per_sec as f64;

        (
            Some(delta_u as f64 * ms_per_tick),
            Some(delta_s as f64 * ms_per_tick),
        )
    }
    #[cfg(not(target_os = "linux"))]
    {
        let _ = (prev_utime, prev_stime, ticks_per_sec);
        (None, None)
    }
}

/// Read voluntary/involuntary context switches from /proc/self/status.
fn read_context_switches() -> (Option<u64>, Option<u64>) {
    #[cfg(target_os = "linux")]
    {
        let Ok(data) = std::fs::read_to_string("/proc/self/status") else {
            return (None, None);
        };
        let mut vol = None;
        let mut invol = None;
        for line in data.lines() {
            if let Some(v) = line.strip_prefix("voluntary_ctxt_switches:\t") {
                vol = v.trim().parse().ok();
            } else if let Some(v) = line.strip_prefix("nonvoluntary_ctxt_switches:\t") {
                invol = v.trim().parse().ok();
            }
        }
        (vol, invol)
    }
    #[cfg(not(target_os = "linux"))]
    {
        (None, None)
    }
}

/// Count open file descriptors via /proc/self/fd/.
fn read_fd_count() -> Option<u32> {
    #[cfg(target_os = "linux")]
    {
        std::fs::read_dir("/proc/self/fd")
            .ok()
            .map(|d| d.count() as u32)
    }
    #[cfg(not(target_os = "linux"))]
    {
        None
    }
}

/// Read thread count from /proc/self/status.
fn read_thread_count() -> Option<u32> {
    #[cfg(target_os = "linux")]
    {
        let Ok(data) = std::fs::read_to_string("/proc/self/status") else {
            return None;
        };
        for line in data.lines() {
            if let Some(v) = line.strip_prefix("Threads:\t") {
                return v.trim().parse().ok();
            }
        }
        None
    }
    #[cfg(not(target_os = "linux"))]
    {
        None
    }
}

#[cfg(target_os = "macos")]
fn read_rss_macos() -> u64 {
    use std::mem;
    const MACH_TASK_BASIC_INFO: u32 = 20;

    #[repr(C)]
    #[derive(Default)]
    struct MachTaskBasicInfo {
        virtual_size: u64,
        resident_size: u64,
        resident_size_max: u64,
        user_time: [u32; 2],
        system_time: [u32; 2],
        policy: i32,
        suspend_count: i32,
    }

    unsafe {
        let mut info = MachTaskBasicInfo::default();
        let mut count = (mem::size_of::<MachTaskBasicInfo>() / mem::size_of::<u32>()) as u32;
        #[allow(deprecated)]
        let task = libc::mach_task_self();
        let kr = libc::task_info(
            task,
            MACH_TASK_BASIC_INFO,
            &mut info as *mut _ as *mut i32,
            &mut count,
        );
        if kr == 0 { info.resident_size } else { 0 }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn default_snapshot() {
        let snap = ProcessSnapshot::default();
        assert_eq!(snap.rss_bytes, 0);
        assert!(snap.cpu_user_ms.is_none());
    }

    #[test]
    fn collector_starts() {
        let c = KernelMetricsCollector::new();
        let snap = c.snapshot();
        assert_eq!(snap.rss_bytes, 0); // no poll yet
    }

    #[test]
    fn read_memory_returns_values() {
        let (rss, _virt) = read_memory();
        #[cfg(any(target_os = "linux", target_os = "macos"))]
        assert!(rss > 0);
        #[cfg(not(any(target_os = "linux", target_os = "macos")))]
        assert_eq!(rss, 0);
    }

    #[test]
    fn clock_ticks_positive() {
        assert!(get_clock_ticks() > 0);
    }
}
