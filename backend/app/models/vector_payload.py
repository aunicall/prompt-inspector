"""Semantic vector payload table for prompt injection detection."""

import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Boolean, Text, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import HALFVEC
from app.database import Base
from app.config import settings


class VectorPayload(Base):
    """Attack payload vector store."""
    __tablename__ = "vector_payloads"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    categories = mapped_column(JSONB, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding = mapped_column(HALFVEC(settings.EMBEDDING_DIM), nullable=False)
    source: Mapped[str] = mapped_column(
        String(50), default="manual", nullable=False, server_default="manual"
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
