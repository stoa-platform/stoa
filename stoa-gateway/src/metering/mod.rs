//! Metering Module
//!
//! Kafka-based metering for tool calls and HTTP requests.
//! Implements ADR-023 zero-blind-spot observability.
//!
//! ## Features
//!
//! - **Tool Call Events**: Every MCP tool invocation is metered
//! - **HTTP Request Events**: Every proxy request is metered
//! - **Error Snapshots**: Rich error context on 4xx/5xx responses
//! - **Timing Breakdown**: T_gateway + T_backend = T_total (ADR-023)
//!
//! ## Configuration
//!
//! Enable metering with environment variables:
//!
//! ```bash
//! STOA_METERING_ENABLED=true
//! STOA_KAFKA_BROKERS=localhost:9092
//! STOA_METERING_TOPIC=stoa.metering
//! STOA_ERRORS_TOPIC=stoa.errors
//! ```
//!
//! ## Feature Flag
//!
//! The `metering` feature enables the Kafka producer:
//!
//! ```toml
//! [features]
//! metering = ["rdkafka"]
//! ```
//!
//! Without the feature, metering events are logged but not sent to Kafka.

pub mod events;
pub mod middleware;
pub mod producer;
pub mod snapshots;

// Re-export commonly used types
// Allow unused imports as these are public API for consumers
#[allow(unused_imports)]
pub use events::{EventStatus, HttpRequestEvent, TokenUsage, ToolCallEvent};
#[allow(unused_imports)]
pub use middleware::{metering_middleware, record_tool_call, MeteringContext, MeteringExt};
pub use producer::{
    create_shared_producer, MeteringProducerConfig, SharedMeteringProducer,
};
#[allow(unused_imports)]
pub use producer::MeteringProducer;
#[allow(unused_imports)]
pub use snapshots::{
    ErrorSnapshot, ErrorType, GatewayState, RequestContext, TimingBreakdown,
};
