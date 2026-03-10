"""Threat category configuration table."""

from datetime import datetime
from sqlalchemy import String, DateTime, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class CategoryConfig(Base):
    """Global threat category definitions and severity levels."""
    __tablename__ = "category_configs"

    category: Mapped[str] = mapped_column(String(50), primary_key=True)
    domain: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="high")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
