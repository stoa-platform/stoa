//! WASM Plugin Loader — discovers and loads `.wasm` files (CAB-1644)
//!
//! Scans `STOA_PLUGIN_DIR` for `.wasm` files with optional `.toml` sidecar config.
//!
//! # Directory Layout
//!
//! ```text
//! plugins/
//! ├── request-logger.wasm       # compiled WASM module
//! ├── request-logger.toml       # optional config sidecar
//! ├── rate-limiter.wasm
//! └── rate-limiter.toml
//! ```
//!
//! # TOML Sidecar Format
//!
//! ```toml
//! name = "request-logger"
//! version = "1.0.0"
//! description = "Logs all incoming requests"
//! phases = ["pre_auth", "post_upstream"]
//!
//! [config]
//! log_headers = true
//! ```

use std::path::{Path, PathBuf};
use std::sync::Arc;
use tracing::{info, warn};

use super::registry::PluginRegistry;
use super::sdk::Phase;
use super::wasm_runtime::WasmPlugin;

/// TOML sidecar schema for a WASM plugin.
#[derive(serde::Deserialize)]
struct PluginManifest {
    name: String,
    #[serde(default = "default_version")]
    version: String,
    #[serde(default)]
    description: String,
    #[serde(default = "default_phases")]
    phases: Vec<String>,
    #[serde(default)]
    config: serde_json::Value,
}

fn default_version() -> String {
    "0.1.0".to_string()
}

fn default_phases() -> Vec<String> {
    vec![
        "pre_auth".to_string(),
        "post_auth".to_string(),
        "pre_upstream".to_string(),
        "post_upstream".to_string(),
        "on_error".to_string(),
    ]
}

fn parse_phase(s: &str) -> Option<Phase> {
    match s {
        "pre_auth" => Some(Phase::PreAuth),
        "post_auth" => Some(Phase::PostAuth),
        "pre_upstream" => Some(Phase::PreUpstream),
        "post_upstream" => Some(Phase::PostUpstream),
        "on_error" => Some(Phase::OnError),
        _ => None,
    }
}

/// Load all WASM plugins from a directory and register them in the given registry.
///
/// Returns the number of plugins successfully loaded.
pub async fn load_plugins_from_dir(dir: &Path, registry: &PluginRegistry) -> Result<usize, String> {
    if !dir.is_dir() {
        return Err(format!("plugin dir does not exist: {}", dir.display()));
    }

    let entries = std::fs::read_dir(dir).map_err(|e| format!("read dir: {e}"))?;

    let mut loaded = 0;
    for entry in entries.flatten() {
        let path = entry.path();
        if path.extension().and_then(|e| e.to_str()) != Some("wasm") {
            continue;
        }

        match load_single_plugin(&path, registry).await {
            Ok(name) => {
                info!(plugin = %name, path = %path.display(), "WASM plugin loaded");
                loaded += 1;
            }
            Err(e) => {
                warn!(path = %path.display(), error = %e, "failed to load WASM plugin");
            }
        }
    }

    Ok(loaded)
}

/// Load a single WASM plugin from a `.wasm` file.
async fn load_single_plugin(wasm_path: &Path, registry: &PluginRegistry) -> Result<String, String> {
    let wasm_bytes = std::fs::read(wasm_path).map_err(|e| format!("read wasm: {e}"))?;

    let manifest = load_manifest(wasm_path)?;
    let phases: Vec<Phase> = manifest
        .phases
        .iter()
        .filter_map(|s| parse_phase(s))
        .collect();

    let plugin = WasmPlugin::from_bytes(
        &manifest.name,
        &manifest.version,
        &manifest.description,
        &wasm_bytes,
        phases,
        &manifest.config,
    )?;

    registry
        .register(Arc::new(plugin), &manifest.config)
        .await
        .map_err(|e| format!("register: {e}"))?;

    Ok(manifest.name)
}

/// Load the TOML sidecar manifest. If no `.toml` file exists, derive defaults
/// from the `.wasm` filename.
fn load_manifest(wasm_path: &Path) -> Result<PluginManifest, String> {
    let toml_path = wasm_path.with_extension("toml");

    if toml_path.exists() {
        let content = std::fs::read_to_string(&toml_path).map_err(|e| format!("read toml: {e}"))?;
        let manifest: PluginManifest =
            toml::from_str(&content).map_err(|e| format!("parse toml: {e}"))?;
        return Ok(manifest);
    }

    // Derive name from filename (e.g., "request-logger.wasm" → "request-logger")
    let name = wasm_path
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("unknown")
        .to_string();

    Ok(PluginManifest {
        name,
        version: default_version(),
        description: String::new(),
        phases: default_phases(),
        config: serde_json::Value::Null,
    })
}

/// Get the plugin directory from `STOA_PLUGIN_DIR` env var.
pub fn plugin_dir() -> Option<PathBuf> {
    std::env::var("STOA_PLUGIN_DIR").ok().map(PathBuf::from)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use tempfile::TempDir;

    fn write_test_wasm(dir: &Path, name: &str, wat: &str) {
        let wasm_path = dir.join(format!("{name}.wasm"));
        // wasmtime can compile WAT directly, but .wasm files are binary.
        // For testing, we write WAT as bytes — WasmPlugin::from_bytes handles WAT too.
        std::fs::write(&wasm_path, wat.as_bytes()).expect("write wasm");
    }

    fn write_toml(dir: &Path, name: &str, content: &str) {
        let toml_path = dir.join(format!("{name}.toml"));
        let mut f = std::fs::File::create(&toml_path).expect("create toml");
        f.write_all(content.as_bytes()).expect("write toml");
    }

    #[tokio::test]
    async fn test_load_plugins_from_dir() {
        let tmp = TempDir::new().expect("tmpdir");
        let dir = tmp.path();

        write_test_wasm(dir, "logger", super::super::wasm_runtime::TEST_LOGGER_WAT);
        write_toml(
            dir,
            "logger",
            r#"
name = "logger"
version = "1.0.0"
description = "Test logger"
phases = ["pre_auth"]

[config]
verbose = true
"#,
        );

        let registry = PluginRegistry::new();
        let count = load_plugins_from_dir(dir, &registry).await.expect("load");

        assert_eq!(count, 1);
        assert_eq!(registry.count().await, 1);

        let meta = registry.get("logger").await;
        assert!(meta.is_some());
        assert_eq!(meta.as_ref().expect("meta").version, "1.0.0");
    }

    #[tokio::test]
    async fn test_load_without_toml_sidecar() {
        let tmp = TempDir::new().expect("tmpdir");
        let dir = tmp.path();

        write_test_wasm(dir, "no-toml", super::super::wasm_runtime::TEST_LOGGER_WAT);

        let registry = PluginRegistry::new();
        let count = load_plugins_from_dir(dir, &registry).await.expect("load");

        assert_eq!(count, 1);
        let meta = registry.get("no-toml").await;
        assert!(meta.is_some());
        // Default: all 5 phases
        assert_eq!(meta.expect("meta").phases.len(), 5);
    }

    #[tokio::test]
    async fn test_load_nonexistent_dir() {
        let registry = PluginRegistry::new();
        let result = load_plugins_from_dir(Path::new("/nonexistent"), &registry).await;
        assert!(result.is_err());
    }

    #[tokio::test]
    async fn test_load_skips_non_wasm_files() {
        let tmp = TempDir::new().expect("tmpdir");
        let dir = tmp.path();

        std::fs::write(dir.join("readme.md"), "not a plugin").expect("write");
        std::fs::write(dir.join("config.toml"), "not a plugin").expect("write");

        let registry = PluginRegistry::new();
        let count = load_plugins_from_dir(dir, &registry).await.expect("load");
        assert_eq!(count, 0);
    }

    #[test]
    fn test_parse_phase() {
        assert_eq!(parse_phase("pre_auth"), Some(Phase::PreAuth));
        assert_eq!(parse_phase("post_upstream"), Some(Phase::PostUpstream));
        assert_eq!(parse_phase("on_error"), Some(Phase::OnError));
        assert_eq!(parse_phase("invalid"), None);
    }

    #[test]
    fn test_plugin_dir_env() {
        // When env var is not set
        std::env::remove_var("STOA_PLUGIN_DIR");
        assert!(plugin_dir().is_none());

        std::env::set_var("STOA_PLUGIN_DIR", "/tmp/plugins");
        assert_eq!(plugin_dir(), Some(PathBuf::from("/tmp/plugins")));
        std::env::remove_var("STOA_PLUGIN_DIR");
    }
}
