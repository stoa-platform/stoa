//! Defense-in-depth path warnings for filesystem-backed Config fields.
//!
//! `policy_path`, `ip_blocklist_file`, and `prompt_cache_watch_dir` each accept
//! arbitrary filesystem paths today (CAB-2165 Bundle 2 / P2-11 GW-2). The
//! operator who configures the pod already has access to the container FS, so
//! path traversal is not an external attack vector — but a configuration typo
//! pointing at `/tmp/blocklist.txt` or a secret mount outside
//! `/etc/stoa/` / `/var/stoa/` / `/opt/stoa/` can silently degrade security
//! posture.
//!
//! This module emits a `tracing::warn!` at startup when any of those fields
//! resolves outside the canonical STOA prefixes. It never rejects — the
//! operator keeps full control. Relative paths are trusted as explicit intent
//! within the process working directory and produce no warning.
//!
//! The predicate [`is_path_outside_safe_prefixes`] is exposed as a
//! `pub(crate)` pure function so regression guards assert on the boolean
//! directly, without relying on `tracing` log capture.

use std::path::Path;
use tracing::warn;

/// Absolute-path prefixes considered "safe" (no warning emitted).
///
/// Uses component-aware [`Path::starts_with`] so `/etc/stoa-malicious` does
/// NOT match `/etc/stoa` (unlike a naive `str::starts_with`).
const SAFE_PREFIXES: &[&str] = &["/etc/stoa", "/var/stoa", "/opt/stoa"];

/// Returns `true` if `path` is an absolute path that does not begin with any
/// [`SAFE_PREFIXES`] component.
///
/// Relative paths always return `false` (no warning) — they are treated as
/// explicit operator intent within the process working directory.
pub(crate) fn is_path_outside_safe_prefixes(path: &str) -> bool {
    let p = Path::new(path);
    if !p.is_absolute() {
        return false;
    }
    !SAFE_PREFIXES
        .iter()
        .any(|prefix| p.starts_with(Path::new(prefix)))
}

/// Emit a defense-in-depth warning when `path` is outside canonical STOA
/// prefixes. No-op for paths inside the safe set, relative paths, or when the
/// operator has opted into a non-standard mount knowingly.
pub(crate) fn warn_if_unsafe(field: &'static str, path: &str) {
    if is_path_outside_safe_prefixes(path) {
        warn!(
            field = field,
            path = path,
            "config path outside canonical /etc/stoa/ — defense-in-depth warning (CAB-2165)"
        );
    }
}

#[cfg(test)]
mod tests {
    use super::is_path_outside_safe_prefixes;

    #[test]
    fn safe_prefix_is_not_flagged() {
        assert!(!is_path_outside_safe_prefixes(
            "/etc/stoa/policies/default.rego"
        ));
        assert!(!is_path_outside_safe_prefixes("/var/stoa/blocklist.txt"));
        assert!(!is_path_outside_safe_prefixes("/opt/stoa/watch"));
        // Exact-match at the prefix itself.
        assert!(!is_path_outside_safe_prefixes("/etc/stoa"));
    }

    #[test]
    fn unsafe_absolute_prefix_is_flagged() {
        assert!(is_path_outside_safe_prefixes("/tmp/custom.rego"));
        assert!(is_path_outside_safe_prefixes("/etc/passwd"));
        // Sibling-prefix trap: /etc/stoa-malicious must NOT be treated as safe.
        assert!(is_path_outside_safe_prefixes(
            "/etc/stoa-malicious/foo.yaml"
        ));
    }

    #[test]
    fn relative_path_is_not_flagged() {
        assert!(!is_path_outside_safe_prefixes("policies/default.rego"));
        assert!(!is_path_outside_safe_prefixes("./data/watch"));
        assert!(!is_path_outside_safe_prefixes("../custom.yaml"));
    }
}
