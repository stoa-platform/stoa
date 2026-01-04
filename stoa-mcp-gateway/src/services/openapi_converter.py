"""OpenAPI to MCP Tool Converter.

Transforms OpenAPI specifications into MCP Tool definitions.
Enables automatic discovery and registration of API endpoints as MCP tools.
"""

import json
import re
from typing import Any

import structlog

from ..models import Tool, ToolInputSchema

logger = structlog.get_logger(__name__)


class OpenAPIConverter:
    """Converts OpenAPI specifications to MCP Tools.

    Supports OpenAPI 3.0.x and 3.1.x specifications.
    Each operation (GET/POST/PUT/DELETE) becomes an MCP tool.
    """

    def __init__(
        self,
        api_id: str | None = None,
        tenant_id: str | None = None,
        base_url: str | None = None,
    ) -> None:
        """Initialize the converter.

        Args:
            api_id: STOA API identifier to associate with tools
            tenant_id: Tenant ID to associate with tools
            base_url: Base URL override for the API
        """
        self.api_id = api_id
        self.tenant_id = tenant_id
        self.base_url = base_url

    def convert(self, spec: dict[str, Any]) -> list[Tool]:
        """Convert an OpenAPI spec to MCP tools.

        Args:
            spec: OpenAPI specification as a dictionary

        Returns:
            List of MCP Tool definitions
        """
        tools: list[Tool] = []

        # Get base URL from spec or use override
        base_url = self._get_base_url(spec)

        # Get API info
        info = spec.get("info", {})
        api_title = info.get("title", "Unknown API")
        api_version = info.get("version", "1.0.0")

        # Process paths
        paths = spec.get("paths", {})
        for path, path_item in paths.items():
            if not isinstance(path_item, dict):
                continue

            # Skip path-level parameters and other non-operation fields
            for method in ["get", "post", "put", "delete", "patch"]:
                if method not in path_item:
                    continue

                operation = path_item[method]
                tool = self._operation_to_tool(
                    path=path,
                    method=method,
                    operation=operation,
                    base_url=base_url,
                    api_title=api_title,
                    api_version=api_version,
                    path_params=path_item.get("parameters", []),
                )
                if tool:
                    tools.append(tool)

        logger.info(
            "Converted OpenAPI spec to tools",
            api_title=api_title,
            tools_count=len(tools),
        )

        return tools

    def _get_base_url(self, spec: dict[str, Any]) -> str:
        """Extract base URL from OpenAPI spec."""
        if self.base_url:
            return self.base_url

        # OpenAPI 3.x
        servers = spec.get("servers", [])
        if servers and isinstance(servers[0], dict):
            return servers[0].get("url", "")

        # Swagger 2.0
        host = spec.get("host", "")
        base_path = spec.get("basePath", "")
        schemes = spec.get("schemes", ["https"])
        if host:
            scheme = schemes[0] if schemes else "https"
            return f"{scheme}://{host}{base_path}"

        return ""

    def _operation_to_tool(
        self,
        path: str,
        method: str,
        operation: dict[str, Any],
        base_url: str,
        api_title: str,
        api_version: str,
        path_params: list[dict[str, Any]] | None = None,
    ) -> Tool | None:
        """Convert an OpenAPI operation to an MCP tool.

        Args:
            path: API path (e.g., /users/{id})
            method: HTTP method
            operation: OpenAPI operation object
            base_url: Base URL for the API
            api_title: API title for naming
            api_version: API version
            path_params: Path-level parameters

        Returns:
            MCP Tool or None if conversion fails
        """
        try:
            # Generate tool name
            operation_id = operation.get("operationId")
            if operation_id:
                tool_name = self._sanitize_name(operation_id)
            else:
                tool_name = self._generate_name(path, method)

            # Build description
            summary = operation.get("summary", "")
            description = operation.get("description", summary)
            if not description:
                description = f"{method.upper()} {path}"

            # Combine path and operation parameters
            all_params = list(path_params or []) + operation.get("parameters", [])

            # Build input schema
            input_schema = self._build_input_schema(
                parameters=all_params,
                request_body=operation.get("requestBody"),
            )

            # Build endpoint URL
            endpoint = f"{base_url.rstrip('/')}{path}"

            # Extract tags
            tags = operation.get("tags", [])
            tags.append("api")  # Always add 'api' tag

            return Tool(
                name=tool_name,
                description=description,
                input_schema=input_schema,
                api_id=self.api_id,
                tenant_id=self.tenant_id,
                endpoint=endpoint,
                method=method.upper(),
                tags=tags,
                version=api_version,
            )

        except Exception as e:
            logger.warning(
                "Failed to convert operation to tool",
                path=path,
                method=method,
                error=str(e),
            )
            return None

    def _sanitize_name(self, name: str) -> str:
        """Sanitize operation ID to valid tool name."""
        # Replace non-alphanumeric with underscore
        sanitized = re.sub(r"[^a-zA-Z0-9]", "_", name)
        # Remove consecutive underscores
        sanitized = re.sub(r"_+", "_", sanitized)
        # Remove leading/trailing underscores
        sanitized = sanitized.strip("_")
        # Lowercase
        return sanitized.lower()

    def _generate_name(self, path: str, method: str) -> str:
        """Generate a tool name from path and method."""
        # Remove path parameters
        clean_path = re.sub(r"\{[^}]+\}", "", path)
        # Replace slashes and other chars
        clean_path = re.sub(r"[^a-zA-Z0-9]", "_", clean_path)
        # Remove consecutive underscores
        clean_path = re.sub(r"_+", "_", clean_path)
        # Remove leading/trailing underscores
        clean_path = clean_path.strip("_")

        return f"{method}_{clean_path}".lower()

    def _build_input_schema(
        self,
        parameters: list[dict[str, Any]],
        request_body: dict[str, Any] | None = None,
    ) -> ToolInputSchema:
        """Build MCP input schema from OpenAPI parameters.

        Args:
            parameters: OpenAPI parameter objects
            request_body: OpenAPI request body object

        Returns:
            MCP ToolInputSchema
        """
        properties: dict[str, Any] = {}
        required: list[str] = []

        # Process parameters (path, query, header)
        for param in parameters:
            if not isinstance(param, dict):
                continue

            # Handle $ref (simplified - just skip for now)
            if "$ref" in param:
                continue

            name = param.get("name")
            if not name:
                continue

            param_in = param.get("in", "query")
            schema = param.get("schema", {})

            # Build property definition
            prop_def: dict[str, Any] = {
                "type": schema.get("type", "string"),
                "description": param.get("description", ""),
            }

            # Add format if present
            if "format" in schema:
                prop_def["format"] = schema["format"]

            # Add enum if present
            if "enum" in schema:
                prop_def["enum"] = schema["enum"]

            # Add default if present
            if "default" in schema:
                prop_def["default"] = schema["default"]

            # Note the parameter location
            prop_def["x-in"] = param_in

            properties[name] = prop_def

            # Check if required
            if param.get("required", False):
                required.append(name)

        # Process request body
        if request_body and isinstance(request_body, dict):
            content = request_body.get("content", {})
            json_content = content.get("application/json", {})
            body_schema = json_content.get("schema", {})

            # If body schema has properties, add them
            if "properties" in body_schema:
                for name, prop in body_schema["properties"].items():
                    prop_copy = dict(prop)
                    prop_copy["x-in"] = "body"
                    properties[name] = prop_copy

                # Add required from body schema
                if "required" in body_schema:
                    required.extend(body_schema["required"])

            # If body schema is a reference, just add a 'body' parameter
            elif "$ref" in body_schema or body_schema.get("type") == "object":
                properties["body"] = {
                    "type": "object",
                    "description": request_body.get("description", "Request body"),
                    "x-in": "body",
                }
                if request_body.get("required", False):
                    required.append("body")

        return ToolInputSchema(
            properties=properties,
            required=list(set(required)),  # Deduplicate
        )


def convert_openapi_to_tools(
    spec: dict[str, Any] | str,
    api_id: str | None = None,
    tenant_id: str | None = None,
    base_url: str | None = None,
) -> list[Tool]:
    """Convert an OpenAPI specification to MCP tools.

    Convenience function for one-off conversions.

    Args:
        spec: OpenAPI spec as dict or JSON string
        api_id: STOA API identifier
        tenant_id: Tenant ID
        base_url: Base URL override

    Returns:
        List of MCP Tool definitions
    """
    if isinstance(spec, str):
        spec = json.loads(spec)

    converter = OpenAPIConverter(
        api_id=api_id,
        tenant_id=tenant_id,
        base_url=base_url,
    )
    return converter.convert(spec)
