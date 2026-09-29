"""Business Function Chart (§5.3, area 1): BFC_NODE, its step I/O and RACI links, and the
external parties a step exchanges data with (D-24a). All frozen into baselines."""
from sqlalchemy import (
    CHAR, BigInteger, Boolean, CheckConstraint, Computed, ForeignKey, ForeignKeyConstraint,
    Identity, Index, Integer, SmallInteger, String, Text, UniqueConstraint, func, text,
)
from sqlalchemy.orm import Mapped, mapped_column

from models.base import AuditMixin, Base


def _live(value: bool):
    """§5.4.7(1) guard: `value` while the row is live, NULL once retired (mirrors vb_ops.live_guard)."""
    return mapped_column(Boolean, Computed(f"CASE WHEN is_active THEN {str(value).upper()} END",
                                           persisted=True))


def _process_node_fk(prefix: str) -> tuple:
    """Every step-level link proves its node is in the project and, while live, is a process."""
    return (
        ForeignKeyConstraint(["bfc_node_id", "project_id"],
                             ["bfc_node.bfc_node_id", "bfc_node.project_id"], name=f"fk_{prefix}_node"),
        ForeignKeyConstraint(["bfc_node_id", "project_id", "node_is_process"],
                             ["bfc_node.bfc_node_id", "bfc_node.project_id", "bfc_node.is_process"],
                             name=f"fk_{prefix}_node_process", onupdate="NO ACTION"),
    )


class ExternalEntity(AuditMixin, Base):
    """A party outside the client (D-24a). ext_number is minted ('EXT' series)."""

    __tablename__ = "external_entity"

    external_entity_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("project.project_id"), nullable=False)
    ext_number: Mapped[str] = mapped_column(String(20), nullable=False)
    ext_name: Mapped[str] = mapped_column(String(200), nullable=False)
    kind_code_id: Mapped[int | None] = mapped_column(BigInteger)
    kind_category: Mapped[str] = mapped_column(String(40), Computed("'EXTERNAL_ENTITY_KIND'", persisted=True))
    description: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("project_id", "ext_number", name="uq_ext_number"),
        UniqueConstraint("external_entity_id", "project_id", name="uq_external_entity_project"),
        ForeignKeyConstraint(["kind_code_id", "kind_category"],
                             ["code_master.code_id", "code_master.category"],
                             name="fk_ext_kind_code", onupdate="NO ACTION"),
        Index("uq_ext_name_live", "project_id", func.lower(func.btrim(ext_name)), unique=True,
              postgresql_where=text("is_active")),
        Index("ix_ext_kind", "kind_code_id"),
    )

    def owning_project_id(self) -> int:
        return self.project_id
