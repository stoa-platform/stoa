"""
Contract and Protocol Binding models for UAC Protocol Switcher

Contracts represent Universal API Contracts that can be exposed via multiple protocols.
ProtocolBindings track which protocols are enabled for each contract.
"""
import uuid
import enum
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, Integer, ForeignKey, Enum as SQLEnum, Index, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.database import Base


class ProtocolType(str, enum.Enum):
    """Supported protocol types for UAC bindings."""
    REST = "rest"
    GRAPHQL = "graphql"
    GRPC = "grpc"
    MCP = "mcp"
    KAFKA = "kafka"


class Contract(Base):
    """
    Universal API Contract model.

    A contract defines an API once and can expose it via multiple protocols (REST, GraphQL, gRPC, MCP, Kafka).
    """
    __tablename__ = "contracts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(255), nullable=False, index=True)

    # Contract identification
    name = Column(String(255), nullable=False)
    display_name = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    version = Column(String(50), nullable=False, default="1.0.0")

    # Contract status
    status = Column(String(50), nullable=False, default="draft")  # draft, published, deprecated

    # OpenAPI/Schema reference (the source of truth)
    openapi_spec_url = Column(String(512), nullable=True)
    schema_hash = Column(String(64), nullable=True)  # For detecting schema changes

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(String(255), nullable=True)

    # Relationships
    bindings = relationship("ProtocolBinding", back_populates="contract", cascade="all, delete-orphan")

    __table_args__ = (
        Index('ix_contracts_tenant_name', 'tenant_id', 'name'),
        Index('ix_contracts_tenant_status', 'tenant_id', 'status'),
    )

    def __repr__(self):
        return f"<Contract {self.tenant_id}/{self.name}:{self.version}>"


class ProtocolBinding(Base):
    """
    Protocol binding for a contract.

    Each binding represents an enabled protocol (REST, GraphQL, etc.) for a contract.
    """
    __tablename__ = "protocol_bindings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contract_id = Column(UUID(as_uuid=True), ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False)
    protocol = Column(SQLEnum(ProtocolType), nullable=False)
    enabled = Column(Boolean, default=False, nullable=False)

    # Protocol-specific endpoint info
    endpoint = Column(String(512), nullable=True)
    playground_url = Column(String(512), nullable=True)

    # MCP-specific fields
    tool_name = Column(String(255), nullable=True)

    # GraphQL-specific fields (comma-separated operations)
    operations = Column(Text, nullable=True)

    # gRPC-specific fields
    proto_file_url = Column(String(512), nullable=True)

    # Kafka-specific fields
    topic_name = Column(String(255), nullable=True)

    # Generation metadata
    generated_at = Column(DateTime, nullable=True)
    generation_error = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship
    contract = relationship("Contract", back_populates="bindings")

    __table_args__ = (
        Index('ix_bindings_contract_protocol', 'contract_id', 'protocol', unique=True),
    )

    def __repr__(self):
        return f"<ProtocolBinding {self.contract_id}:{self.protocol}>"
