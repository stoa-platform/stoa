//! RAG Injector — Context enrichment for AI agent prompts (CAB-1761)
//!
//! Enriches prompts with contextual information from external sources
//! (vector databases, REST APIs) before forwarding to the LLM backend.
//!
//! Pipeline position (request path):
//!
//! ```text
//! Request → Auth → Rate Limit → Guardrails → [RAG INJECTOR] → Tool Execute / LLM
//! ```

pub mod injector;

pub use injector::{RagContext, RagInjector, RagInjectorConfig, RagSource, RagSourceType};
