//! File Watcher for Prompt Cache Invalidation (CAB-1123 Phase 2)
//!
//! Watches a directory for file changes and invalidates the prompt cache
//! when knowledge base files are modified. Uses `notify` crate (blocking I/O)
//! wrapped in `tokio::task::spawn_blocking`.

use std::path::Path;
use std::sync::Arc;

use notify::{Event, EventKind, RecursiveMode, Watcher};
use tracing::{info, warn};

use super::PromptCache;

/// Spawn a background file watcher that clears the prompt cache on file changes.
///
/// Tolerates missing directories (logs a warning, doesn't panic).
/// Runs in a blocking thread since `notify` is synchronous.
pub fn spawn_cache_file_watcher(watch_dir: String, cache: Arc<PromptCache>) {
    let path = Path::new(&watch_dir);
    if !path.exists() {
        warn!(
            dir = %watch_dir,
            "Prompt cache watch directory does not exist — watcher disabled"
        );
        return;
    }

    info!(dir = %watch_dir, "Starting prompt cache file watcher");

    tokio::task::spawn_blocking(move || {
        let cache = cache;
        let (tx, rx) = std::sync::mpsc::channel::<notify::Result<Event>>();

        let mut watcher = match notify::recommended_watcher(tx) {
            Ok(w) => w,
            Err(e) => {
                warn!(error = %e, "Failed to create file watcher");
                return;
            }
        };

        if let Err(e) = watcher.watch(Path::new(&watch_dir), RecursiveMode::Recursive) {
            warn!(error = %e, dir = %watch_dir, "Failed to watch directory");
            return;
        }

        for event in rx {
            match event {
                Ok(event) => {
                    if matches!(
                        event.kind,
                        EventKind::Modify(_) | EventKind::Remove(_) | EventKind::Create(_)
                    ) {
                        info!(
                            paths = ?event.paths,
                            "File change detected — invalidating prompt cache"
                        );
                        cache.clear();
                    }
                }
                Err(e) => {
                    warn!(error = %e, "File watcher error");
                }
            }
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::cache::PromptCacheConfig;

    #[test]
    fn watcher_tolerates_missing_directory() {
        let cache = Arc::new(PromptCache::new(PromptCacheConfig::default()));
        // Should not panic — just logs a warning
        spawn_cache_file_watcher("/nonexistent/path/abc123".into(), cache);
    }
}
