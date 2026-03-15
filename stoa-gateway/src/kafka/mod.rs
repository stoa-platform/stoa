//! Kafka Event Bridge Module (CAB-1757)
//!
//! Bridges Kafka topics to MCP tools, enabling AI agents to:
//! - **Publish** messages to Kafka topics via MCP tool calls
//! - **Subscribe** to Kafka topics and read recent messages via MCP tool calls
//!
//! Feature-gated via `kafka_bridge_enabled` config flag.
//! Kafka connectivity requires the `kafka` cargo feature.

pub mod bridge;
