//! Typed enums for Config fields that were previously `String` with
//! documented-but-unenforced value sets (CAB-2165 Bundle 1 / P2-9 GW-2).
//!
//! Each enum uses `#[serde(rename_all = "snake_case")]` (or `kebab-case`
//! where the documented value contains a hyphen) so the serialized form is
//! identical to the strings previously accepted in YAML / env vars. No
//! implicit aliases — strict parsing rejects unknown values with a clear
//! "unknown variant" error at `Config::load()` time, instead of silently
//! falling through to a default.
//!
//! One explicit alias is kept: `co-pilot → Copilot` on
//! [`SupervisionDefaultTier`] for parity with
//! `supervision::SupervisionTier::from_header`.

use serde::{Deserialize, Serialize};
use std::fmt;

/// Git provider selector for UAC sync.
///
/// Env: `STOA_GIT_PROVIDER` (canonical values: `gitlab` | `github`).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
#[serde(rename_all = "snake_case")]
pub enum GitProvider {
    #[default]
    Gitlab,
    Github,
}

impl GitProvider {
    /// Canonical lowercase string form (matches the serde `rename_all` output).
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Gitlab => "gitlab",
            Self::Github => "github",
        }
    }
}

impl fmt::Display for GitProvider {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

/// Tracing verbosity level.
///
/// Informational only: `tracing` itself is driven by `RUST_LOG`
/// (`EnvFilter::try_from_default_env`) in `main.rs`. This field documents the
/// operator-intended level and appears in the health / debug snapshots.
/// Env: `STOA_LOG_LEVEL`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
#[serde(rename_all = "snake_case")]
pub enum LogLevel {
    Trace,
    Debug,
    #[default]
    Info,
    Warn,
    Error,
}

/// Log output format.
///
/// Informational only: the formatter is selected in `main.rs` based on
/// `RUST_LOG` / build flags. Env: `STOA_LOG_FORMAT`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
#[serde(rename_all = "snake_case")]
pub enum LogFormat {
    #[default]
    Json,
    Pretty,
    Compact,
}

/// Deployment environment label for registration + observability.
///
/// Env: `STOA_ENVIRONMENT` (canonical values: `dev` | `staging` | `prod`).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
#[serde(rename_all = "snake_case")]
pub enum Environment {
    #[default]
    Dev,
    Staging,
    Prod,
}

impl Environment {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Dev => "dev",
            Self::Staging => "staging",
            Self::Prod => "prod",
        }
    }
}

impl fmt::Display for Environment {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

/// Shadow-mode traffic capture source (ADR-024 §5).
///
/// Env: `STOA_SHADOW_CAPTURE_SOURCE` (kebab-case values: `inline` |
/// `envoy-tap` | `port-mirror` | `kafka`).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum ShadowCaptureSource {
    Inline,
    EnvoyTap,
    PortMirror,
    Kafka,
}

/// Default supervision tier when the `X-Hegemon-Supervision` header is absent
/// (CAB-1636).
///
/// Env: `STOA_SUPERVISION_DEFAULT_TIER` (canonical: `autopilot` | `copilot` |
/// `command`). Accepts `co-pilot` as a deprecated alias for parity with
/// `supervision::SupervisionTier::from_header`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
#[serde(rename_all = "snake_case")]
pub enum SupervisionDefaultTier {
    #[default]
    Autopilot,
    #[serde(alias = "co-pilot")]
    Copilot,
    Command,
}

impl SupervisionDefaultTier {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Autopilot => "autopilot",
            Self::Copilot => "copilot",
            Self::Command => "command",
        }
    }
}

impl fmt::Display for SupervisionDefaultTier {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

/// LLM proxy upstream provider format (CAB-1568).
///
/// Env: `STOA_LLM_PROXY_PROVIDER` (canonical: `anthropic` | `mistral` |
/// `openai`).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum LlmProxyProvider {
    Anthropic,
    Mistral,
    Openai,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn git_provider_parses_canonical_values() {
        assert_eq!(
            serde_json::from_str::<GitProvider>("\"gitlab\"").unwrap(),
            GitProvider::Gitlab
        );
        assert_eq!(
            serde_json::from_str::<GitProvider>("\"github\"").unwrap(),
            GitProvider::Github
        );
    }

    #[test]
    fn regression_cab_2165_git_provider_rejects_unknown_value() {
        // Regression for CAB-2165 Bundle 1 / P2-9 GW-2.
        // Replaces the legacy test_git_provider_unknown_value_treated_as_gitlab
        // anti-pattern: strict parsing now surfaces typos instead of silently
        // falling through to the default.
        let err = serde_json::from_str::<GitProvider>("\"bitbucket\"")
            .expect_err("unknown variant should not deserialize");
        let msg = err.to_string();
        assert!(
            msg.contains("unknown variant") && msg.contains("bitbucket"),
            "error message should name the rejected variant; got: {msg}"
        );
    }

    #[test]
    fn git_provider_rejects_typo_with_case_mismatch() {
        // "GitHub" (mixed case) is not canonical and must be rejected —
        // deployed YAML/env is all lowercase (verified pre-migration grep).
        assert!(serde_json::from_str::<GitProvider>("\"GitHub\"").is_err());
        assert!(serde_json::from_str::<GitProvider>("\"GITLAB\"").is_err());
    }

    #[test]
    fn git_provider_default_is_gitlab() {
        assert_eq!(GitProvider::default(), GitProvider::Gitlab);
    }

    #[test]
    fn log_level_parses_all_standard_values() {
        for (s, expected) in [
            ("trace", LogLevel::Trace),
            ("debug", LogLevel::Debug),
            ("info", LogLevel::Info),
            ("warn", LogLevel::Warn),
            ("error", LogLevel::Error),
        ] {
            let parsed: LogLevel = serde_json::from_str(&format!("\"{s}\"")).unwrap();
            assert_eq!(parsed, expected, "failed to parse {s}");
        }
    }

    #[test]
    fn log_level_rejects_uppercase() {
        // No implicit case-folding alias (D.1 strict).
        assert!(serde_json::from_str::<LogLevel>("\"WARN\"").is_err());
    }

    #[test]
    fn log_format_rejects_unknown() {
        assert!(serde_json::from_str::<LogFormat>("\"xml\"").is_err());
    }

    #[test]
    fn environment_accepts_dev_staging_prod() {
        assert_eq!(
            serde_json::from_str::<Environment>("\"dev\"").unwrap(),
            Environment::Dev
        );
        assert_eq!(
            serde_json::from_str::<Environment>("\"staging\"").unwrap(),
            Environment::Staging
        );
        assert_eq!(
            serde_json::from_str::<Environment>("\"prod\"").unwrap(),
            Environment::Prod
        );
    }

    #[test]
    fn environment_rejects_unknown() {
        assert!(serde_json::from_str::<Environment>("\"mordor\"").is_err());
        assert!(serde_json::from_str::<Environment>("\"production\"").is_err());
    }

    #[test]
    fn shadow_capture_source_is_kebab_case() {
        assert_eq!(
            serde_json::from_str::<ShadowCaptureSource>("\"envoy-tap\"").unwrap(),
            ShadowCaptureSource::EnvoyTap
        );
        assert_eq!(
            serde_json::from_str::<ShadowCaptureSource>("\"port-mirror\"").unwrap(),
            ShadowCaptureSource::PortMirror
        );
        // Snake-case form is NOT accepted (no implicit alias).
        assert!(serde_json::from_str::<ShadowCaptureSource>("\"envoy_tap\"").is_err());
    }

    #[test]
    fn supervision_tier_copilot_alias() {
        // Canonical snake_case form.
        assert_eq!(
            serde_json::from_str::<SupervisionDefaultTier>("\"copilot\"").unwrap(),
            SupervisionDefaultTier::Copilot
        );
        // Explicit alias from D.1 — parity with SupervisionTier::from_header.
        assert_eq!(
            serde_json::from_str::<SupervisionDefaultTier>("\"co-pilot\"").unwrap(),
            SupervisionDefaultTier::Copilot
        );
    }

    #[test]
    fn supervision_tier_all_canonical_variants() {
        assert_eq!(
            serde_json::from_str::<SupervisionDefaultTier>("\"autopilot\"").unwrap(),
            SupervisionDefaultTier::Autopilot
        );
        assert_eq!(
            serde_json::from_str::<SupervisionDefaultTier>("\"command\"").unwrap(),
            SupervisionDefaultTier::Command
        );
    }

    #[test]
    fn llm_proxy_provider_all_variants() {
        for (s, expected) in [
            ("anthropic", LlmProxyProvider::Anthropic),
            ("mistral", LlmProxyProvider::Mistral),
            ("openai", LlmProxyProvider::Openai),
        ] {
            let parsed: LlmProxyProvider = serde_json::from_str(&format!("\"{s}\"")).unwrap();
            assert_eq!(parsed, expected, "failed to parse {s}");
        }
    }

    #[test]
    fn llm_proxy_provider_rejects_unknown() {
        assert!(serde_json::from_str::<LlmProxyProvider>("\"google\"").is_err());
    }

    #[test]
    fn git_provider_display_matches_serde() {
        assert_eq!(GitProvider::Gitlab.to_string(), "gitlab");
        assert_eq!(GitProvider::Github.to_string(), "github");
    }

    #[test]
    fn environment_display_matches_serde() {
        assert_eq!(Environment::Dev.to_string(), "dev");
        assert_eq!(Environment::Staging.to_string(), "staging");
        assert_eq!(Environment::Prod.to_string(), "prod");
    }

    #[test]
    fn supervision_tier_display_matches_serde() {
        assert_eq!(SupervisionDefaultTier::Autopilot.to_string(), "autopilot");
        assert_eq!(SupervisionDefaultTier::Copilot.to_string(), "copilot");
        assert_eq!(SupervisionDefaultTier::Command.to_string(), "command");
    }
}
