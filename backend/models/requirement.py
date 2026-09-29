"""Business Requirement (§5.3, area 2): the BR (one per live process node, D-2) and its data
and RACI links. All frozen into baselines."""
from sqlalchemy import (
    CHAR, BigInteger, Boolean, CheckConstraint, Computed, ForeignKey, ForeignKeyConstraint,
    Identity, Index, String, Text, UniqueConstraint, text,
)
from sqlalchemy.orm import Mapped, mapped_column

from models.base import AuditMixin, Base


class BusinessRequirement(AuditMixin, Base):
    """Created empty with its process node (S1-7): br_statement is NULL until written, status
    set to BR_STATUS/DRAFT by the service. bfc_node_id never changes (service-enforced)."""

    __tablename__ = "business_requirement"

    br_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("project.project_id"), nullable=False)
    bfc_node_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    node_is_process: Mapped[bool | None] = mapped_column(
        Boolean, Computed("CASE WHEN is_active THEN TRUE END", persisted=True))
    br_number: Mapped[str] = mapped_column(String(20), nullable=False)
    br_statement: Mapped[str | None] = mapped_column(Text)
    business_logic: Mapped[str | None] = mapped_column(Text)
    output_expectation: Mapped[str | None] = mapped_column(Text)
    status_code_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status_category: Mapped[str] = mapped_column(String(40), Computed("'BR_STATUS'", persisted=True))

    __table_args__ = (
        UniqueConstraint("project_id", "br_number", name="uq_br_number"),
        UniqueConstraint("br_id", "project_id", name="uq_br_project"),
        UniqueConstraint("br_id", "project_id", "bfc_node_id", name="uq_br_node_carrier"),
        ForeignKeyConstraint(["bfc_node_id", "project_id"],
                             ["bfc_node.bfc_node_id", "bfc_node.project_id"], name="fk_br_node"),
        ForeignKeyConstraint(["bfc_node_id", "project_id", "node_is_process"],
                             ["bfc_node.bfc_node_id", "bfc_node.project_id", "bfc_node.is_process"],
                             name="fk_br_node_process", onupdate="NO ACTION"),
        ForeignKeyConstraint(["status_code_id", "status_category"],
                             ["code_master.code_id", "code_master.category"],
                             name="fk_br_status_code", onupdate="NO ACTION"),
        # D-2: one live BR per node.
        Index("uq_br_one_per_node", "bfc_node_id", unique=True, postgresql_where=text("is_active")),
        Index("ix_br_node", "bfc_node_id", "project_id"),
        Index("ix_br_status", "status_code_id"),
    )

    def owning_project_id(self) -> int:
        return self.project_id
