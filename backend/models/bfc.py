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


class BfcNode(AuditMixin, Base):
    """is_process is the only process test (VB law 4, D-23). level_no, seq_no and hier_code are
    derived by services/bfc.py; hier_code is re-coded in two phases on reorder (S1-2)."""

    __tablename__ = "bfc_node"

    bfc_node_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("project.project_id"), nullable=False)
    parent_bfc_node_id: Mapped[int | None] = mapped_column(BigInteger)
    parent_is_process: Mapped[bool | None] = _live(False)
    level_no: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    is_process: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    seq_no: Mapped[int] = mapped_column(Integer, nullable=False)
    hier_code: Mapped[str] = mapped_column(String(40), nullable=False)
    node_name: Mapped[str] = mapped_column(String(200), nullable=False)
    purpose_desc: Mapped[str | None] = mapped_column(Text)
    data_processing_desc: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("bfc_node_id", "project_id", name="uq_bfc_node_project"),
        UniqueConstraint("bfc_node_id", "project_id", "is_process", name="uq_bfc_node_process_target"),
        ForeignKeyConstraint(["parent_bfc_node_id", "project_id"],
                             ["bfc_node.bfc_node_id", "bfc_node.project_id"], name="fk_bfc_node_parent"),
        # D-23: a live node's parent is never a process. Never CASCADE (§5.4.7(2)).
        ForeignKeyConstraint(["parent_bfc_node_id", "project_id", "parent_is_process"],
                             ["bfc_node.bfc_node_id", "bfc_node.project_id", "bfc_node.is_process"],
                             name="fk_bfc_node_parent_not_process", onupdate="NO ACTION"),
        CheckConstraint("level_no BETWEEN 1 AND 5", name="ck_bfc_level"),
        CheckConstraint("(level_no = 1) = (parent_bfc_node_id IS NULL)", name="ck_bfc_root"),
        CheckConstraint("NOT is_process OR level_no >= 3", name="ck_bfc_process_level"),
        CheckConstraint("level_no < 5 OR is_process", name="ck_bfc_l5_is_process"),
        CheckConstraint("is_process OR data_processing_desc IS NULL", name="ck_bfc_desc_process_only"),
        CheckConstraint("seq_no <> 0 AND seq_no BETWEEN -99 AND 99", name="ck_bfc_seq"),
        Index("uq_bfc_hier_code_live", "project_id", "hier_code", unique=True,
              postgresql_where=text("is_active")),
        # S1-1: L1 nodes share the NULL parent, so they cannot share a position.
        Index("uq_bfc_sibling_seq", "project_id", "parent_bfc_node_id", "seq_no", unique=True,
              postgresql_nulls_not_distinct=True, postgresql_where=text("is_active")),
        Index("uq_bfc_process_name", "parent_bfc_node_id", func.lower(func.btrim(node_name)),
              unique=True, postgresql_where=text("is_active AND is_process")),
        Index("ix_bfc_parent_guard", "parent_bfc_node_id", "project_id", "parent_is_process"),
        Index("ix_bfc_hier_pattern", "project_id", "hier_code", postgresql_where=text("is_active"),
              postgresql_ops={"hier_code": "varchar_pattern_ops"}),
        Index("ix_bfc_process_live", "project_id", postgresql_where=text("is_process AND is_active")),
        Index("ix_bfc_project", "project_id"),
    )

    def owning_project_id(self) -> int:
        return self.project_id


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


class BfcNodeDataEntity(AuditMixin, Base):
    """Step I/O — the one record of it (D-24). Written only by bfc.ensure_step_io (R2-D13).
    S1-5: surrogate PK so the baseline shadow keeps the link; the design's key is a UNIQUE."""

    __tablename__ = "bfc_node_data_entity"

    bfc_node_data_entity_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("project.project_id"), nullable=False)
    bfc_node_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    node_is_process: Mapped[bool | None] = _live(True)
    data_entity_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    direction: Mapped[str] = mapped_column(CHAR(1), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("bfc_node_id", "data_entity_id", "direction", name="uq_bnde_grain"),
        UniqueConstraint("bfc_node_id", "data_entity_id", "direction", "is_active",
                         name="uq_bnde_live_target"),
        *_process_node_fk("bnde"),
        ForeignKeyConstraint(["data_entity_id", "project_id"],
                             ["data_entity.data_entity_id", "data_entity.project_id"], name="fk_bnde_de"),
        CheckConstraint("direction IN ('I', 'O')", name="ck_bnde_direction"),
        Index("ix_bnde_node", "bfc_node_id", "project_id"),
        Index("ix_bnde_de", "data_entity_id", "project_id"),
        Index("ix_bnde_project", "project_id"),
    )

    def owning_project_id(self) -> int:
        return self.project_id
