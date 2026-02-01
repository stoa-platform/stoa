"""Error classification for consumer-facing execution view.

CAB-432: Classifies HTTP errors into a simplified taxonomy.
Messages are consumer-friendly — never technical, never revealing internals.
"""

from .models import ErrorCategory, ErrorSource


def classify_error(
    status_code: int,
    duration_ms: int = 0,
    is_mcp_tool: bool = False,
    is_async: bool = False,
) -> dict:
    """Classify an HTTP error into a consumer-friendly category.

    Args:
        status_code: HTTP status code of the failed request.
        duration_ms: Request duration in milliseconds.
        is_mcp_tool: Whether the request targeted an MCP tool.
        is_async: Whether the request was an async/event-driven operation.

    Returns:
        Dict with error_source, error_category, summary, help_text,
        and suggested_action.
    """
    match status_code:
        case 401:
            return {
                "error_source": ErrorSource.GATEWAY,
                "error_category": ErrorCategory.AUTH_FAILED,
                "summary": "Authentication failed",
                "help_text": (
                    "Your API key or token was not accepted. It may be expired, revoked, or incorrectly formatted."
                ),
                "suggested_action": ("Check your API key in Application Settings and regenerate it if needed."),
            }

        case 403:
            return {
                "error_source": ErrorSource.GATEWAY,
                "error_category": ErrorCategory.FORBIDDEN,
                "summary": "Access denied",
                "help_text": (
                    "Your application does not have permission to access this resource. "
                    "This may be due to missing subscriptions or insufficient scopes."
                ),
                "suggested_action": ("Verify your API subscription is active and covers this endpoint."),
            }

        case 429:
            return {
                "error_source": ErrorSource.GATEWAY,
                "error_category": ErrorCategory.RATE_LIMIT,
                "summary": "Rate limit exceeded",
                "help_text": (
                    "Your application has sent too many requests in a short period. "
                    "The rate limit resets automatically."
                ),
                "suggested_action": ("Reduce request frequency or implement exponential backoff in your client."),
            }

        case 502:
            return {
                "error_source": ErrorSource.BACKEND,
                "error_category": ErrorCategory.BAD_GATEWAY,
                "summary": "Service temporarily unreachable",
                "help_text": (
                    "The API service could not process your request at this time. This is typically a temporary issue."
                ),
                "suggested_action": "Retry the request after a few seconds.",
            }

        case 503:
            return {
                "error_source": ErrorSource.BACKEND,
                "error_category": ErrorCategory.UNAVAILABLE,
                "summary": "Service unavailable",
                "help_text": (
                    "The API service is currently undergoing maintenance or is overloaded. It should be back shortly."
                ),
                "suggested_action": (
                    "Wait a moment and retry. If the issue persists, contact support with the trace ID."
                ),
            }

        case 504:
            return {
                "error_source": ErrorSource.BACKEND,
                "error_category": ErrorCategory.TIMEOUT,
                "summary": "Request timed out",
                "help_text": (
                    "The API service took too long to respond. This may happen with large or complex requests."
                ),
                "suggested_action": (
                    "Try again with a smaller request payload, or contact support if timeouts persist."
                ),
            }

        case 500:
            # MCP tool errors take priority over async/kafka errors
            if is_mcp_tool:
                return {
                    "error_source": ErrorSource.TOOL,
                    "error_category": ErrorCategory.TOOL_ERROR,
                    "summary": "Tool execution failed",
                    "help_text": (
                        "The MCP tool encountered an error while processing your request. "
                        "The tool provider has been notified."
                    ),
                    "suggested_action": (
                        "Retry the request. If the issue persists, contact support with the trace ID."
                    ),
                }

            if is_async:
                return {
                    "error_source": ErrorSource.KAFKA,
                    "error_category": ErrorCategory.KAFKA_ERROR,
                    "summary": "Async processing failed",
                    "help_text": (
                        "Your request was accepted but could not be fully processed. The operation may complete later."
                    ),
                    "suggested_action": (
                        "Check the status of your request later, or contact support with the trace ID."
                    ),
                }

            return {
                "error_source": ErrorSource.BACKEND,
                "error_category": ErrorCategory.UNAVAILABLE,
                "summary": "Unexpected error",
                "help_text": (
                    "An unexpected error occurred while processing your request. Our team has been notified."
                ),
                "suggested_action": ("Retry the request. If the issue persists, contact support with the trace ID."),
            }

        case 400:
            return {
                "error_source": ErrorSource.CLIENT,
                "error_category": ErrorCategory.BAD_REQUEST,
                "summary": "Invalid request",
                "help_text": ("The request could not be processed because it contains invalid or missing parameters."),
                "suggested_action": ("Review the API documentation and check your request parameters."),
            }

        case 404:
            return {
                "error_source": ErrorSource.CLIENT,
                "error_category": ErrorCategory.NOT_FOUND,
                "summary": "Resource not found",
                "help_text": ("The requested resource does not exist or has been removed."),
                "suggested_action": ("Verify the endpoint URL and resource identifiers in your request."),
            }

        case 422:
            return {
                "error_source": ErrorSource.CLIENT,
                "error_category": ErrorCategory.BAD_REQUEST,
                "summary": "Validation error",
                "help_text": ("The request data did not pass validation. One or more fields have invalid values."),
                "suggested_action": ("Check the field types and constraints in the API documentation."),
            }

        case _:
            return {
                "error_source": ErrorSource.CLIENT,
                "error_category": ErrorCategory.BAD_REQUEST,
                "summary": f"Request failed ({status_code})",
                "help_text": "The request could not be completed.",
                "suggested_action": ("Contact support with the trace ID for assistance."),
            }
