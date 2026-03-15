//! WebSocket Proxy Module (CAB-1758)
//!
//! Generic bidirectional WebSocket proxy with governance:
//! - Auth on handshake (JWT/API key validation before upgrade)
//! - Per-message rate limiting (token bucket per connection)
//! - Prometheus metrics (active connections, messages, duration)
//! - Audit logging (opt-in frame tracing)

pub mod proxy;
pub mod rate_limit;
