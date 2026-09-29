"""Data entities (§5.3, area 3): DATA_ENTITY and DATA_FIELD — frozen into baselines (D-3)."""
from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Computed, ForeignKey, ForeignKeyConstraint, Identity,
    Index, Integer, SmallInteger, String, Text, UniqueConstraint, func, text,
)
from sqlalchemy.orm import Mapped, mapped_column

from models.base import AuditMixin, Base


class DataEntity(AuditMixin, Base):
    """de_number is minted by numbering.next_number(…, 'DE') and never reused (§5.4.6)."""

    __tablename__ = "data_entity"

    data_entity_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("project.project_id"), nullable=False)
    de_number: Mapped[str] = mapped_column(String(20), nullable=False)
    de_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    business_owner_note: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("project_id", "de_number", name="uq_de_number"),
        UniqueConstraint("data_entity_id", "project_id", name="uq_data_entity_project"),
        Index("uq_de_name_live", "project_id", func.lower(func.btrim(de_name)), unique=True,
              postgresql_where=text("is_active")),
    )

    def owning_project_id(self) -> int:
        return self.project_id
