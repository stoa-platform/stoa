use super::types::{ContentBlock, ToolResult};

/// Builder for constructing MCP-compliant responses
#[derive(Debug, Default)]
pub struct ResponseBuilder {
    content_blocks: Vec<ContentBlock>,
    is_error: bool,
}

impl ResponseBuilder {
    /// Create a new response builder
    pub fn new() -> Self {
        Self::default()
    }

    /// Mark this response as an error
    pub fn error(mut self) -> Self {
        self.is_error = true;
        self
    }

    /// Add a text content block
    pub fn text(mut self, text: impl Into<String>) -> Self {
        self.content_blocks
            .push(ContentBlock::Text { text: text.into() });
        self
    }

    /// Build the final ToolResult
    pub fn build(self) -> ToolResult {
        ToolResult {
            content: self.content_blocks,
            is_error: self.is_error,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_response_builder_error() {
        let result = ResponseBuilder::new()
            .error()
            .text("Policy violation occurred")
            .build();

        assert!(result.is_error);
        assert_eq!(result.content.len(), 1);
    }

    #[test]
    fn test_response_builder_success() {
        let result = ResponseBuilder::new().text("Operation successful").build();

        assert!(!result.is_error);
    }

    #[test]
    fn test_response_builder_multiple_blocks() {
        let result = ResponseBuilder::new()
            .text("First message")
            .text("Second message")
            .build();

        assert_eq!(result.content.len(), 2);
    }
}
