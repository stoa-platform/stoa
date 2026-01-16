"""MCP SSE Transport Handler.

Implements the Streamable HTTP Transport for the Model Context Protocol.
This enables direct integration with Claude.ai, Claude Desktop and other MCP clients.

Supports both:
- GET /mcp/sse: Legacy SSE connection (Claude Desktop)
- POST /mcp/sse: Streamable HTTP Transport (Claude.ai) - MCP spec 2025-03-26
"""

import asyncio
import json
import uuid
from typing import Any, AsyncGenerator

import structlog
from fastapi import APIRouter, Depends, Request, Response, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse

from ..middleware.auth import TokenClaims, get_current_user, get_optional_user
from ..services import get_tool_registry
from ..config import get_settings
from ..models.mcp import ToolInvocation

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/mcp", tags=["MCP SSE"])


class MCPSession:
    """Manages an MCP session over SSE."""

    def __init__(self, session_id: str, user: TokenClaims | None = None):
        self.session_id = session_id
        self.user = user
        self.initialized = False
        self.message_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

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
            elif method == "notifications/cancelled":
                # Handle cancellation notification
                logger.info("Request cancelled", params=params)
                return None
            else:
                return self._make_error(msg_id, -32601, f"Method not found: {method}")
        except Exception as e:
            logger.error("MCP message handling error", error=str(e), method=method)
            return self._make_error(msg_id, -32603, str(e))

    async def _handle_initialize(self, msg_id: Any, params: dict) -> dict:
        """Handle initialize request."""
        settings = get_settings()
        client_info = params.get("clientInfo", {})
        protocol_version = params.get("protocolVersion", "2024-11-05")

        print(f"[MCP] _handle_initialize: client={client_info}, protocol={protocol_version}", flush=True)

        # Use the client's requested protocol version for compatibility
        response = self._make_response(msg_id, {
            "protocolVersion": protocol_version,
            "capabilities": {
                "tools": {"listChanged": True},
                "resources": {},
                "prompts": {},
            },
            "serverInfo": {
                "name": "STOA MCP Gateway",
                "version": settings.app_version,
                "icons": [
                    {
                        "url": f"https://portal.{settings.base_domain}/favicon.svg",
                        "mimeType": "image/svg+xml",
                    },
                ],
            },
        })
        print(f"[MCP] Initialize response: {json.dumps(response)[:300]}", flush=True)
        return response

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
        print(f"[MCP] _handle_call_tool: {tool_name} with args {arguments}", flush=True)
        try:
            # Create ToolInvocation object for the registry
            invocation = ToolInvocation(
                name=tool_name,
                arguments=arguments,
                request_id=str(msg_id) if msg_id else None,
            )

            # Get user token if available
            user_token = None
            if self.user and hasattr(self.user, 'raw_token'):
                user_token = self.user.raw_token

            print(f"[MCP] Invoking registry.invoke() for {tool_name}", flush=True)
            result = await registry.invoke(invocation, user_token=user_token)
            print(f"[MCP] Tool result: is_error={result.is_error}, content_len={len(result.content)}", flush=True)

            # Format content from ToolResult
            content = []
            for item in result.content:
                if hasattr(item, 'text'):
                    content.append({"type": "text", "text": item.text})
                else:
                    content.append({"type": "text", "text": str(item)})

            response = self._make_response(msg_id, {
                "content": content,
                "isError": result.is_error,
            })
            print(f"[MCP] Response: {json.dumps(response)[:500]}", flush=True)
            return response
        except Exception as e:
            import traceback
            print(f"[MCP] ERROR: {type(e).__name__}: {e}", flush=True)
            print(f"[MCP] Traceback: {traceback.format_exc()}", flush=True)
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


# Active sessions by session ID
_sessions: dict[str, MCPSession] = {}


def _get_session_id_from_request(request: Request) -> str | None:
    """Extract session ID from request headers."""
    return request.headers.get("Mcp-Session-Id") or request.headers.get("X-MCP-Session-Id")


async def get_user_or_session(
    request: Request,
    user: TokenClaims | None = Depends(get_optional_user),
) -> TokenClaims:
    """Authenticate via Bearer token OR via existing MCP session.

    Claude.ai sends the Bearer token only on the first request (initialize),
    then uses Mcp-Session-Id for subsequent requests. This function allows
    both authentication methods.

    Priority:
    1. Bearer token (if provided and valid)
    2. Existing MCP session (if session_id is valid and already authenticated)
    3. Raise 401 if neither works
    """
    # If we have a valid Bearer token, use it
    if user is not None:
        logger.debug("Authenticated via Bearer token", sub=user.subject)
        return user

    # Try session-based authentication
    session_id = _get_session_id_from_request(request)
    if session_id and session_id in _sessions:
        session = _sessions[session_id]
        if session.user is not None:
            logger.debug("Authenticated via MCP session", session_id=session_id, sub=session.user.subject)
            return session.user

    # Log all headers for debugging
    all_headers = dict(request.headers)
    if "authorization" in all_headers:
        all_headers["authorization"] = all_headers["authorization"][:50] + "..."

    logger.warning(
        "MCP authentication failed - no Bearer token and no valid session",
        session_id=session_id,
        session_exists=session_id in _sessions if session_id else False,
        path=str(request.url.path),
        method=request.method,
    )
    print(f"[MCP AUTH] 401 for {request.method} {request.url.path} - session_id={session_id}, headers={all_headers}", flush=True)

    raise HTTPException(
        status_code=401,
        detail="Not authenticated - provide Bearer token or valid Mcp-Session-Id",
        headers={"WWW-Authenticate": 'Bearer, Basic realm="STOA MCP Gateway"'},
    )


@router.post("/sse")
async def mcp_sse_post_endpoint(
    request: Request,
    user: TokenClaims = Depends(get_user_or_session),
) -> Response:
    """
    MCP Streamable HTTP Transport endpoint (POST).

    This implements the MCP 2025-03-26 Streamable HTTP Transport spec.
    Claude.ai uses this to send JSON-RPC messages and receive SSE responses.

    Flow:
    1. Client POSTs JSON-RPC message (e.g., initialize)
    2. Server responds with SSE stream containing the response
    3. Session ID is returned in Mcp-Session-Id header
    """
    # Get or create session
    session_id = _get_session_id_from_request(request)

    if session_id and session_id in _sessions:
        session = _sessions[session_id]
        logger.info("Resuming MCP session", session_id=session_id)
    else:
        session_id = str(uuid.uuid4())
        session = MCPSession(session_id, user)
        _sessions[session_id] = session
        logger.info("Created new MCP session", session_id=session_id, user=user.subject)

    # Parse the JSON-RPC message
    try:
        body = await request.json()
    except json.JSONDecodeError as e:
        logger.error("Invalid JSON in request", error=str(e))
        return JSONResponse(
            content={"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}},
            status_code=400,
        )

    method = body.get("method")
    msg_id = body.get("id")

    # Debug logging to stdout
    accept_header = request.headers.get("Accept", "")
    content_type = request.headers.get("Content-Type", "")
    print(f"[MCP] Received: method={method}, id={msg_id}, Accept={accept_header}, CT={content_type}", flush=True)
    if method == "tools/call":
        print(f"[MCP] Tool call params: {body.get('params')}", flush=True)

    logger.info(
        "MCP POST request",
        method=method,
        msg_id=msg_id,
        session_id=session_id,
    )

    # Handle the message
    try:
        response = await session.handle_message(body)
        logger.info(
            "MCP message handled",
            method=method,
            msg_id=msg_id,
            has_response=response is not None,
            is_error=response.get("error") if response else None,
        )
    except Exception as e:
        logger.error(
            "MCP message handling failed",
            method=method,
            msg_id=msg_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        response = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32603, "message": str(e)},
        }

    # Check if client wants SSE response
    accept_header = request.headers.get("Accept", "")
    wants_sse = "text/event-stream" in accept_header

    if wants_sse and response is not None:
        # Return SSE stream with the response
        # Per MCP Streamable HTTP spec, just use data: without event:
        async def sse_response_stream() -> AsyncGenerator[str, None]:
            """Generate SSE events for the response."""
            # Send the JSON-RPC response as SSE data
            yield f"data: {json.dumps(response)}\n\n"

        return StreamingResponse(
            sse_response_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                "Mcp-Session-Id": session_id,
            },
        )
    else:
        # Return plain JSON response
        if response is None:
            # For notifications (no response expected), return 202 Accepted
            return Response(
                status_code=202,
                headers={"Mcp-Session-Id": session_id},
            )

        return JSONResponse(
            content=response,
            headers={"Mcp-Session-Id": session_id},
        )


@router.get("/sse")
async def mcp_sse_get_endpoint(
    request: Request,
    user: TokenClaims = Depends(get_user_or_session),
) -> StreamingResponse:
    """
    MCP Server-Sent Events endpoint (GET).

    This is the legacy SSE endpoint for Claude Desktop and similar clients.
    Establishes a persistent SSE connection for bidirectional communication.

    The client sends messages via POST to /mcp/message with the session ID.
    """
    # Check for existing session
    session_id = _get_session_id_from_request(request)

    if session_id and session_id in _sessions:
        session = _sessions[session_id]
        logger.info("Resuming MCP SSE session", session_id=session_id)
    else:
        session_id = str(uuid.uuid4())
        session = MCPSession(session_id, user)
        _sessions[session_id] = session
        logger.info("MCP SSE session started", session_id=session_id, user=user.subject)

    async def event_stream() -> AsyncGenerator[str, None]:
        """Generate SSE events."""
        # Send endpoint event first (per MCP spec)
        # This tells the client where to POST messages
        settings = get_settings()
        endpoint_url = f"https://mcp.{settings.base_domain}/mcp/sse"
        yield f"event: endpoint\ndata: {endpoint_url}\n\n"

        # Keep connection alive
        try:
            while True:
                # Check if client disconnected
                if await request.is_disconnected():
                    break

                # Check for queued messages to send
                try:
                    message = session.message_queue.get_nowait()
                    yield f"event: message\ndata: {json.dumps(message)}\n\n"
                except asyncio.QueueEmpty:
                    pass

                # Send keepalive ping every 30 seconds
                yield ": keepalive\n\n"

                # Wait before next iteration
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
            "Mcp-Session-Id": session_id,
        },
    )


@router.delete("/sse")
async def mcp_sse_delete_endpoint(
    request: Request,
    user: TokenClaims = Depends(get_user_or_session),
) -> Response:
    """
    Close MCP session endpoint (DELETE).

    Per MCP spec, clients can explicitly close sessions via DELETE.
    """
    session_id = _get_session_id_from_request(request)

    if session_id and session_id in _sessions:
        _sessions.pop(session_id, None)
        logger.info("MCP session closed via DELETE", session_id=session_id)
        return Response(status_code=204)
    else:
        return Response(status_code=404)


@router.post("/message")
async def mcp_message_endpoint(
    request: Request,
    user: TokenClaims = Depends(get_user_or_session),
) -> Response:
    """
    Handle MCP JSON-RPC messages (legacy endpoint).

    Clients send messages here and receive responses.
    For SSE mode, include session_id in the Mcp-Session-Id header.
    """
    body = await request.json()

    # Get or create session
    session_id = _get_session_id_from_request(request) or body.pop("_session_id", None)

    if not session_id:
        session_id = str(uuid.uuid4())

    if session_id in _sessions:
        session = _sessions[session_id]
    else:
        session = MCPSession(session_id, user)
        _sessions[session_id] = session

    # Handle message
    response = await session.handle_message(body)

    if response is None:
        return Response(
            status_code=202,
            headers={"Mcp-Session-Id": session_id},
        )

    return JSONResponse(
        content=response,
        headers={"Mcp-Session-Id": session_id},
    )


@router.post("/")
async def mcp_jsonrpc_endpoint(
    request: Request,
    user: TokenClaims = Depends(get_user_or_session),
) -> Response:
    """
    Direct JSON-RPC endpoint for MCP.

    Simpler alternative to SSE for clients that support it.
    Each request is independent (no session state).
    """
    body = await request.json()
    session_id = _get_session_id_from_request(request) or str(uuid.uuid4())
    session = MCPSession(session_id, user)

    response = await session.handle_message(body)

    if response is None:
        return Response(status_code=202)

    return JSONResponse(content=response)
