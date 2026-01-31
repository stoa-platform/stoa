"""
Client Model for mTLS Certificate Provisioning (CAB-865)
"""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Enum as SQLEnum, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID

from src.database import Base


class ClientStatus(str, enum.Enum):
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"


class Client(Base):
    __tablename__ = "clients"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(255), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    certificate_cn = Column(String(255), nullable=False)
    certificate_serial = Column(String(255), nullable=True)
    certificate_fingerprint = Column(String(255), nullable=True)
    certificate_pem = Column(Text, nullable=True)
    certificate_not_before = Column(DateTime(timezone=True), nullable=True)
    certificate_not_after = Column(DateTime(timezone=True), nullable=True)
    status = Column(SQLEnum(ClientStatus), default=ClientStatus.ACTIVE, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_clients_tenant_cn", "tenant_id", "certificate_cn", unique=True),
    )

    def __repr__(self):
        return f"<Client {self.id} cn={self.certificate_cn}>"
