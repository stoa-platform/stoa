"""MCP SSE Transport Handler.

Implements Server-Sent Events transport for the Model Context Protocol.
This enables direct integration with Claude Desktop and other MCP clients.
"""

import json
import uuid
from typing import Any, AsyncGenerator

import structlog
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import StreamingResponse

from ..middleware.auth import TokenClaims, get_current_user
from ..services import get_tool_registry
from ..config import get_settings

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/mcp", tags=["MCP SSE"])


class MCPSession:
    """Manages an MCP session over SSE."""

    def __init__(self, session_id: str, user: TokenClaims | None = None):
        self.session_id = session_id
        self.user = user
        self.initialized = False

    async def handle_message(self, message: dict[str, Any]) -> dict[str, Any] | None:
        """Handle incoming JSON-RPC message and return response."""
        method = message.get("method")
        msg_id = message.get("id")
        params = message.get("params", {})

        logger.info("MCP message received", method=method, session=self.session_id)

        try:
            if method == "initialize":
                return await self._handle_initialize(msg_id, params)
            elif method == "initialized":
                self.initialized = True
                return None  # No response for notification
            elif method == "tools/list":
                return await self._handle_list_tools(msg_id, params)
            elif method == "tools/call":
                return await self._handle_call_tool(msg_id, params)
            elif method == "ping":
                return self._make_response(msg_id, {})
            else:
                return self._make_error(msg_id, -32601, f"Method not found: {method}")
        except Exception as e:
            logger.error("MCP message handling error", error=str(e), method=method)
            return self._make_error(msg_id, -32603, str(e))

    async def _handle_initialize(self, msg_id: Any, params: dict) -> dict:
        """Handle initialize request."""
        settings = get_settings()
        return self._make_response(msg_id, {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {"listChanged": True},
                "resources": {},
                "prompts": {},
            },
            "serverInfo": {
                "name": "stoa-mcp-gateway",
                "version": settings.app_version,
                "icons": [
                    {
                        "src": "https://raw.githubusercontent.com/stoa-platform/stoa/main/docs/assets/logo.svg",
                        "mimeType": "image/svg+xml",
                        "sizes": ["any"],
                    },
                ],
            },
        })

    async def _handle_list_tools(self, msg_id: Any, params: dict) -> dict:
        """Handle tools/list request."""
        registry = await get_tool_registry()
        result = registry.list_tools(limit=1000)

        tools = []
        for tool in result.tools:
            # Use input_schema (snake_case) - the Python attribute name
            # MCP protocol expects inputSchema (camelCase) in the response
            schema = tool.input_schema
            if schema:
                input_schema = schema.model_dump() if hasattr(schema, 'model_dump') else dict(schema)
            else:
                input_schema = {"type": "object", "properties": {}}

            tools.append({
                "name": tool.name,
                "description": tool.description or "",
                "inputSchema": input_schema,
            })

        return self._make_response(msg_id, {"tools": tools})

    async def _handle_call_tool(self, msg_id: Any, params: dict) -> dict:
        """Handle tools/call request."""
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        if not tool_name:
            return self._make_error(msg_id, -32602, "Missing tool name")

        registry = await get_tool_registry()
        tool = registry.get_tool(tool_name)

        if not tool:
            return self._make_error(msg_id, -32602, f"Tool not found: {tool_name}")

        # Execute tool
        try:
            result = await registry.invoke_tool(tool_name, arguments, user=self.user)
            return self._make_response(msg_id, {
                "content": [
                    {"type": "text", "text": json.dumps(result.result, indent=2)}
                ],
                "isError": not result.success,
            })
        except Exception as e:
            logger.error("Tool invocation failed", tool=tool_name, error=str(e))
            return self._make_response(msg_id, {
                "content": [{"type": "text", "text": f"Error: {str(e)}"}],
                "isError": True,
            })

    def _make_response(self, msg_id: Any, result: Any) -> dict:
        """Create JSON-RPC response."""
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": result,
        }

    def _make_error(self, msg_id: Any, code: int, message: str) -> dict:
        """Create JSON-RPC error response."""
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": code, "message": message},
        }


# Active sessions
_sessions: dict[str, MCPSession] = {}


@router.get("/sse")
async def mcp_sse_endpoint(
    request: Request,
    user: TokenClaims = Depends(get_current_user),
) -> StreamingResponse:
    """
    MCP Server-Sent Events endpoint.

    This endpoint establishes an SSE connection for the MCP protocol.
    Claude Desktop and other MCP clients connect here.

    The client sends messages via POST to /mcp/message with the session ID.
    """
    session_id = str(uuid.uuid4())
    session = MCPSession(session_id, user)
    _sessions[session_id] = session

    logger.info("MCP SSE session started", session_id=session_id, user=user.subject)

    async def event_stream() -> AsyncGenerator[str, None]:
        """Generate SSE events."""
        # Send session ID as first event
        yield f"event: session\ndata: {json.dumps({'session_id': session_id})}\n\n"

        # Keep connection alive
        try:
            while True:
                # Check if client disconnected
                if await request.is_disconnected():
                    break

                # Send keepalive ping every 30 seconds
                yield f"event: ping\ndata: {json.dumps({'type': 'ping'})}\n\n"

                # Wait before next ping
                import asyncio
                await asyncio.sleep(30)
        finally:
            # Cleanup session
            _sessions.pop(session_id, None)
            logger.info("MCP SSE session ended", session_id=session_id)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/message")
async def mcp_message_endpoint(
    request: Request,
    user: TokenClaims = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Handle MCP JSON-RPC messages.

    Clients send messages here and receive responses.
    For SSE mode, include session_id in the request.
    """
    body = await request.json()

    # Get or create session
    session_id = body.pop("_session_id", None) or str(uuid.uuid4())

    if session_id in _sessions:
        session = _sessions[session_id]
    else:
        session = MCPSession(session_id, user)
        _sessions[session_id] = session

    # Handle message
    response = await session.handle_message(body)

    if response is None:
        return {"jsonrpc": "2.0", "result": "ok"}

    return response


@router.post("/")
async def mcp_jsonrpc_endpoint(
    request: Request,
    user: TokenClaims = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Direct JSON-RPC endpoint for MCP.

    Simpler alternative to SSE for clients that support it.
    Each request is independent (no session state).
    """
    body = await request.json()
    session = MCPSession(str(uuid.uuid4()), user)

    response = await session.handle_message(body)

    if response is None:
        return {"jsonrpc": "2.0", "result": "ok"}

    return response
