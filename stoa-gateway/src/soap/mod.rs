//! SOAP/XML Bridge Module (CAB-1762)
//!
//! Provides SOAP protocol support for the STOA Gateway:
//! - WSDL parsing: extract operations from WSDL documents
//! - SOAP proxy: passthrough HTTP POST with text/xml content-type
//! - SOAP→REST bridge: expose SOAP operations as JSON REST endpoints
//! - SOAP→MCP bridge: expose SOAP operations as MCP tools

pub mod bridge;
pub mod proxy;
pub mod wsdl;
