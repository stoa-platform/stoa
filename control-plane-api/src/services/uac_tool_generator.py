"""UAC → MCP Tool Generator (CAB-605).

Converts UAC contract endpoints into individual MCP tool definitions
stored in the mcp_generated_tools table for gateway discovery.
"""

import json
import re
import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.contract import Contract, McpGeneratedTool
from src.schemas.uac import UacContractSpec, UacEndpointSpec


class UacToolGenerator:
    """Generates MCP tool definitions from UAC contract endpoints."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def generate_tools(
        self,
        contract: Contract,
        uac_spec: UacContractSpec,
    ) -> list[McpGeneratedTool]:
        """Generate MCP tools from a UAC spec (idempotent — replaces existing)."""
        await self.db.execute(delete(McpGeneratedTool).where(McpGeneratedTool.contract_id == contract.id))

        tools: list[McpGeneratedTool] = []
        for endpoint in uac_spec.endpoints:
            tool_name = self._build_tool_name(uac_spec.tenant_id, uac_spec.name, endpoint)
            description = self._build_description(endpoint, uac_spec.display_name or uac_spec.name)
            input_schema = self._build_input_schema(endpoint)

            tool = McpGeneratedTool(
                id=uuid.uuid4(),
                contract_id=contract.id,
                tenant_id=uac_spec.tenant_id,
                tool_name=tool_name,
                description=description,
                input_schema=json.dumps(input_schema) if input_schema else None,
                output_schema=(json.dumps(endpoint.output_schema) if endpoint.output_schema else None),
                backend_url=endpoint.backend_url,
                http_method=endpoint.methods[0] if endpoint.methods else "GET",
                path_pattern=endpoint.path,
                version=uac_spec.version,
                spec_hash=uac_spec.spec_hash,
                enabled=True,
            )
            self.db.add(tool)
            tools.append(tool)

        await self.db.flush()
        return tools

    async def get_tools_for_contract(self, contract_id: uuid.UUID) -> list[McpGeneratedTool]:
        """List all generated tools for a contract."""
        result = await self.db.execute(select(McpGeneratedTool).where(McpGeneratedTool.contract_id == contract_id))
        return list(result.scalars().all())

    async def get_tools_for_tenant(self, tenant_id: str) -> list[McpGeneratedTool]:
        """List all enabled tools for a tenant (gateway discovery)."""
        result = await self.db.execute(
            select(McpGeneratedTool).where(
                McpGeneratedTool.tenant_id == tenant_id,
                McpGeneratedTool.enabled.is_(True),
            )
        )
        return list(result.scalars().all())

    async def invalidate_tools(self, contract_id: uuid.UUID) -> int:
        """Disable all tools for a contract. Returns count of disabled tools."""
        result = await self.db.execute(
            select(McpGeneratedTool).where(
                McpGeneratedTool.contract_id == contract_id,
                McpGeneratedTool.enabled.is_(True),
            )
        )
        tools = result.scalars().all()
        count = 0
        for tool in tools:
            tool.enabled = False
            count += 1
        await self.db.flush()
        return count

    @staticmethod
    def _build_tool_name(
        tenant_id: str,
        contract_name: str,
        endpoint: UacEndpointSpec,
    ) -> str:
        """Build MCP tool name: {tenant}:{contract}:{operation}."""
        if endpoint.operation_id:
            op_id = re.sub(r"[^a-zA-Z0-9_]", "_", endpoint.operation_id).lower()
        else:
            path_slug = re.sub(r"[{}]", "", endpoint.path)
            path_slug = re.sub(r"[^a-zA-Z0-9/]", "_", path_slug).strip("/_")
            path_slug = path_slug.replace("/", "_")
            method = endpoint.methods[0].lower() if endpoint.methods else "get"
            op_id = f"{method}_{path_slug}"
        return f"{tenant_id}:{contract_name}:{op_id}"

    @staticmethod
    def _build_description(endpoint: UacEndpointSpec, contract_display: str) -> str:
        """Build human-readable description."""
        methods = ", ".join(endpoint.methods) if endpoint.methods else "GET"
        return f"{methods} {endpoint.path} — {contract_display}"

    @staticmethod
    def _build_input_schema(endpoint: UacEndpointSpec) -> dict | None:
        """Build input schema from explicit spec or path parameters."""
        if endpoint.input_schema:
            return endpoint.input_schema
        params = re.findall(r"\{(\w+)\}", endpoint.path)
        if not params:
            return None
        return {
            "type": "object",
            "properties": {p: {"type": "string", "description": f"Path parameter: {p}"} for p in params},
            "required": params,
        }
