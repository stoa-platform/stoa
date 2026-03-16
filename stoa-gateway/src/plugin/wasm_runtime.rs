//! WASM Plugin Runtime — wasmtime integration (CAB-1644)
//!
//! Loads compiled `.wasm` modules and bridges them to the existing `Plugin` trait.
//! WASM plugins participate in the same 5-phase lifecycle as native Rust plugins.
//!
//! # WASM Module Contract
//!
//! Exports (all optional — missing = no-op for that phase):
//! - `on_pre_auth() -> i32`
//! - `on_post_auth() -> i32`
//! - `on_pre_upstream() -> i32`
//! - `on_post_upstream() -> i32`
//! - `on_error() -> i32`
//! - `memory` (required for host function string passing)
//!
//! Return: 0 = Continue, >0 = Reject with that HTTP status code.
//!
//! Host imports (module "stoa"):
//! - `log(ptr: i32, len: i32)` — log a message via tracing
//! - `get_header(name_ptr: i32, name_len: i32, buf_ptr: i32, buf_cap: i32) -> i32`
//! - `set_header(name_ptr: i32, name_len: i32, val_ptr: i32, val_len: i32)`
//! - `get_config(buf_ptr: i32, buf_cap: i32) -> i32`

use async_trait::async_trait;
use axum::http::StatusCode;
use serde_json::Value;
use wasmtime::*;

use super::sdk::{Phase, Plugin, PluginContext, PluginMetadata, PluginResult};

/// Per-execution host state passed into WASM Store.
struct HostState {
    request_headers: Vec<(String, String)>,
    headers_to_set: Vec<(String, String)>,
    config_json: String,
}

/// A WASM plugin backed by wasmtime.
///
/// `Engine` and `Module` are `Send + Sync` — a fresh `Store` + `Instance`
/// is created for each `execute()` call (cheap, avoids lifetime issues).
pub struct WasmPlugin {
    engine: Engine,
    module: Module,
    meta: PluginMetadata,
    config_json: String,
}

impl WasmPlugin {
    /// Load a WASM plugin from bytes.
    pub fn from_bytes(
        name: &str,
        version: &str,
        description: &str,
        wasm_bytes: &[u8],
        phases: Vec<Phase>,
        config: &Value,
    ) -> Result<Self, String> {
        let mut wasm_config = Config::new();
        wasm_config.wasm_memory64(false);
        let engine = Engine::new(&wasm_config).map_err(|e| format!("engine init: {e}"))?;
        let module =
            Module::new(&engine, wasm_bytes).map_err(|e| format!("module compile: {e}"))?;

        Ok(Self {
            engine,
            module,
            meta: PluginMetadata {
                name: name.to_string(),
                version: version.to_string(),
                description: description.to_string(),
                phases,
            },
            config_json: config.to_string(),
        })
    }

    /// Build a linker with host functions.
    fn build_linker(engine: &Engine) -> Result<Linker<HostState>, String> {
        let mut linker = Linker::new(engine);

        // stoa.log(ptr, len) — read string from WASM memory, log via tracing
        linker
            .func_wrap(
                "stoa",
                "log",
                |mut caller: Caller<'_, HostState>, ptr: i32, len: i32| {
                    if let Some(msg) = read_wasm_string(&mut caller, ptr, len) {
                        tracing::info!(source = "wasm-plugin", "{msg}");
                    }
                },
            )
            .map_err(|e| format!("link stoa.log: {e}"))?;

        // stoa.get_header(name_ptr, name_len, buf_ptr, buf_cap) -> i32 (bytes written, -1 if not found)
        linker
            .func_wrap(
                "stoa",
                "get_header",
                |mut caller: Caller<'_, HostState>,
                 name_ptr: i32,
                 name_len: i32,
                 buf_ptr: i32,
                 buf_cap: i32| {
                    let name = match read_wasm_string(&mut caller, name_ptr, name_len) {
                        Some(s) => s,
                        None => return -1i32,
                    };
                    let value = caller
                        .data()
                        .request_headers
                        .iter()
                        .find(|(k, _)| k.eq_ignore_ascii_case(&name))
                        .map(|(_, v)| v.clone());
                    match value {
                        Some(val) => {
                            write_wasm_bytes(&mut caller, buf_ptr, buf_cap, val.as_bytes())
                        }
                        None => -1,
                    }
                },
            )
            .map_err(|e| format!("link stoa.get_header: {e}"))?;

        // stoa.set_header(name_ptr, name_len, val_ptr, val_len)
        linker
            .func_wrap(
                "stoa",
                "set_header",
                |mut caller: Caller<'_, HostState>,
                 name_ptr: i32,
                 name_len: i32,
                 val_ptr: i32,
                 val_len: i32| {
                    let name = read_wasm_string(&mut caller, name_ptr, name_len);
                    let val = read_wasm_string(&mut caller, val_ptr, val_len);
                    if let (Some(n), Some(v)) = (name, val) {
                        caller.data_mut().headers_to_set.push((n, v));
                    }
                },
            )
            .map_err(|e| format!("link stoa.set_header: {e}"))?;

        // stoa.get_config(buf_ptr, buf_cap) -> i32 (bytes written)
        linker
            .func_wrap(
                "stoa",
                "get_config",
                |mut caller: Caller<'_, HostState>, buf_ptr: i32, buf_cap: i32| {
                    let json = caller.data().config_json.clone();
                    write_wasm_bytes(&mut caller, buf_ptr, buf_cap, json.as_bytes())
                },
            )
            .map_err(|e| format!("link stoa.get_config: {e}"))?;

        Ok(linker)
    }

    /// Execute a phase by calling the corresponding WASM export.
    fn run_phase(&self, phase: Phase, ctx: &mut PluginContext) -> PluginResult {
        let export_name = match phase {
            Phase::PreAuth => "on_pre_auth",
            Phase::PostAuth => "on_post_auth",
            Phase::PreUpstream => "on_pre_upstream",
            Phase::PostUpstream => "on_post_upstream",
            Phase::OnError => "on_error",
        };

        let linker = match Self::build_linker(&self.engine) {
            Ok(l) => l,
            Err(e) => {
                tracing::error!(plugin = %self.meta.name, error = %e, "failed to build linker");
                return PluginResult::Continue;
            }
        };

        let headers: Vec<(String, String)> = ctx
            .request_headers
            .iter()
            .map(|(k, v)| (k.as_str().to_string(), v.to_str().unwrap_or("").to_string()))
            .collect();

        let host_state = HostState {
            request_headers: headers,
            headers_to_set: Vec::new(),
            config_json: self.config_json.clone(),
        };

        let mut store = Store::new(&self.engine, host_state);

        let instance = match linker.instantiate(&mut store, &self.module) {
            Ok(i) => i,
            Err(e) => {
                tracing::error!(plugin = %self.meta.name, error = %e, "wasm instantiation failed");
                return PluginResult::Continue;
            }
        };

        // Look for the phase export — if missing, this phase is a no-op
        let func = match instance.get_typed_func::<(), i32>(&mut store, export_name) {
            Ok(f) => f,
            Err(_) => return PluginResult::Continue,
        };

        let result_code = match func.call(&mut store, ()) {
            Ok(code) => code,
            Err(e) => {
                tracing::error!(
                    plugin = %self.meta.name,
                    phase = %phase,
                    error = %e,
                    "wasm execution failed"
                );
                return PluginResult::Continue;
            }
        };

        // Apply headers set by the plugin
        for (name, value) in &store.data().headers_to_set {
            ctx.set_request_header(name, value);
        }

        if result_code == 0 {
            PluginResult::Continue
        } else {
            let status = StatusCode::from_u16(result_code as u16)
                .unwrap_or(StatusCode::INTERNAL_SERVER_ERROR);
            PluginResult::Terminate {
                status,
                body: format!("Rejected by plugin {}", self.meta.name),
            }
        }
    }
}

// Safety: Engine and Module are Send+Sync. WasmPlugin holds no Store.
unsafe impl Send for WasmPlugin {}
unsafe impl Sync for WasmPlugin {}

#[async_trait]
impl Plugin for WasmPlugin {
    fn metadata(&self) -> PluginMetadata {
        self.meta.clone()
    }

    async fn execute(&self, phase: Phase, ctx: &mut PluginContext) -> PluginResult {
        self.run_phase(phase, ctx)
    }
}

/// Read a UTF-8 string from WASM linear memory.
fn read_wasm_string(caller: &mut Caller<'_, HostState>, ptr: i32, len: i32) -> Option<String> {
    let memory = caller.get_export("memory")?.into_memory()?;
    let data = memory.data(&caller);
    let start = ptr as usize;
    let end = start + len as usize;
    if end > data.len() {
        return None;
    }
    String::from_utf8(data[start..end].to_vec()).ok()
}

/// Write bytes into WASM linear memory. Returns bytes written (capped by buf_cap).
fn write_wasm_bytes(
    caller: &mut Caller<'_, HostState>,
    buf_ptr: i32,
    buf_cap: i32,
    bytes: &[u8],
) -> i32 {
    let memory = match caller.get_export("memory") {
        Some(ext) => match ext.into_memory() {
            Some(m) => m,
            None => return -1,
        },
        None => return -1,
    };
    let start = buf_ptr as usize;
    let write_len = bytes.len().min(buf_cap as usize);
    let end = start + write_len;
    let data = memory.data_mut(caller);
    if end > data.len() {
        return -1;
    }
    data[start..end].copy_from_slice(&bytes[..write_len]);
    write_len as i32
}

/// Precompiled test WAT module for unit tests — logs and continues.
#[cfg(test)]
pub(crate) const TEST_LOGGER_WAT: &str = r#"(module
    (import "stoa" "log" (func $log (param i32 i32)))
    (import "stoa" "set_header" (func $set_header (param i32 i32 i32 i32)))

    (memory (export "memory") 1)

    ;; "hello from wasm" at offset 0
    (data (i32.const 0) "hello from wasm")

    ;; header name "x-wasm" at offset 32
    (data (i32.const 32) "x-wasm")

    ;; header value "active" at offset 48
    (data (i32.const 48) "active")

    (func (export "on_pre_auth") (result i32)
        ;; log("hello from wasm")
        i32.const 0   ;; ptr
        i32.const 15  ;; len
        call $log

        ;; set_header("x-wasm", "active")
        i32.const 32  ;; name ptr
        i32.const 6   ;; name len
        i32.const 48  ;; val ptr
        i32.const 6   ;; val len
        call $set_header

        ;; return 0 = Continue
        i32.const 0
    )
)"#;

/// WAT module that rejects with 403.
#[cfg(test)]
pub(crate) const TEST_REJECT_WAT: &str = r#"(module
    (memory (export "memory") 1)

    (func (export "on_pre_auth") (result i32)
        i32.const 403
    )
)"#;

#[cfg(test)]
mod tests {
    use super::*;
    use axum::http::HeaderMap;

    fn make_plugin(wat: &str, phases: Vec<Phase>) -> WasmPlugin {
        WasmPlugin::from_bytes(
            "test-wasm",
            "1.0.0",
            "Test WASM plugin",
            wat.as_bytes(),
            phases,
            &serde_json::json!({"key": "value"}),
        )
        .expect("compile WAT")
    }

    #[tokio::test]
    async fn test_wasm_plugin_continue() {
        let plugin = make_plugin(TEST_LOGGER_WAT, vec![Phase::PreAuth]);
        let mut ctx = PluginContext::new(
            Phase::PreAuth,
            "acme".to_string(),
            "/test".to_string(),
            "GET".to_string(),
            HeaderMap::new(),
        );

        let result = plugin.execute(Phase::PreAuth, &mut ctx).await;
        assert!(matches!(result, PluginResult::Continue));
        assert_eq!(ctx.get_request_header("x-wasm"), Some("active"));
    }

    #[tokio::test]
    async fn test_wasm_plugin_reject() {
        let plugin = make_plugin(TEST_REJECT_WAT, vec![Phase::PreAuth]);
        let mut ctx = PluginContext::new(
            Phase::PreAuth,
            "acme".to_string(),
            "/test".to_string(),
            "GET".to_string(),
            HeaderMap::new(),
        );

        let result = plugin.execute(Phase::PreAuth, &mut ctx).await;
        match result {
            PluginResult::Terminate { status, .. } => {
                assert_eq!(status, StatusCode::FORBIDDEN);
            }
            _ => panic!("expected Terminate"),
        }
    }

    #[tokio::test]
    async fn test_wasm_missing_phase_is_noop() {
        let plugin = make_plugin(TEST_LOGGER_WAT, vec![Phase::PreAuth, Phase::PostUpstream]);
        let mut ctx = PluginContext::new(
            Phase::PostUpstream,
            "acme".to_string(),
            "/test".to_string(),
            "GET".to_string(),
            HeaderMap::new(),
        );

        // on_post_upstream not exported → Continue
        let result = plugin.execute(Phase::PostUpstream, &mut ctx).await;
        assert!(matches!(result, PluginResult::Continue));
    }

    #[tokio::test]
    async fn test_wasm_metadata() {
        let plugin = make_plugin(TEST_LOGGER_WAT, vec![Phase::PreAuth]);
        let meta = plugin.metadata();
        assert_eq!(meta.name, "test-wasm");
        assert_eq!(meta.version, "1.0.0");
        assert_eq!(meta.phases, vec![Phase::PreAuth]);
    }

    #[tokio::test]
    async fn test_wasm_invalid_bytes_fails() {
        let result = WasmPlugin::from_bytes(
            "bad",
            "1.0.0",
            "bad plugin",
            b"not wasm",
            vec![],
            &serde_json::json!(null),
        );
        assert!(result.is_err());
    }

    #[tokio::test]
    async fn test_wasm_registers_in_plugin_registry() {
        use super::super::registry::PluginRegistry;
        use std::sync::Arc;

        let plugin = make_plugin(TEST_LOGGER_WAT, vec![Phase::PreAuth]);
        let registry = PluginRegistry::new();
        let meta = registry
            .register(Arc::new(plugin), &serde_json::json!(null))
            .await
            .expect("register");

        assert_eq!(meta.name, "test-wasm");
        assert_eq!(registry.count().await, 1);

        let plugins = registry.plugins_for_phase(Phase::PreAuth).await;
        assert_eq!(plugins, vec!["test-wasm"]);
    }
}
