"""Diagram presentation (D-29, D-30, S2-6): one saved position per project × diagram × scope ×
object. Hard-deleted, no soft delete, no row_version, never baselined — the documented
deviation A-52. Written only by services/diagram_layout.save (§13)."""
from decimal import Decimal

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, ForeignKey, ForeignKeyConstraint, Identity, Index,
    Numeric, String, UniqueConstraint, text,
)
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base, TimestampMixin

DIAGRAM_TYPES = ("ERD", "PROCESS_FLOW", "DFD")
OBJECT_COLUMNS = ("bfc_node_id", "data_entity_id", "external_entity_id", "bfc_node_flow_id")


def _object_fk(col: str, target: str, name: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint([col, "project_id"], [f"{target}.{col}", f"{target}.project_id"],
                                name=name)


class DiagramLayout(TimestampMixin, Base):
    __tablename__ = "diagram_layout"

    diagram_layout_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("project.project_id"), nullable=False)
    diagram_type: Mapped[str] = mapped_column(String(20), nullable=False)
    scope_bfc_node_id: Mapped[int | None] = mapped_column(BigInteger)
    bfc_node_id: Mapped[int | None] = mapped_column(BigInteger)
    data_entity_id: Mapped[int | None] = mapped_column(BigInteger)
    external_entity_id: Mapped[int | None] = mapped_column(BigInteger)
    bfc_node_flow_id: Mapped[int | None] = mapped_column(BigInteger)
    x: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    y: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    width: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    height: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    is_collapsed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("app_user.app_user_id"), nullable=False)
    updated_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("app_user.app_user_id"))

    __table_args__ = (
        ForeignKeyConstraint(["scope_bfc_node_id", "project_id"],
                             ["bfc_node.bfc_node_id", "bfc_node.project_id"], name="fk_dl_scope"),
        _object_fk("bfc_node_id", "bfc_node", "fk_dl_node"),
        _object_fk("data_entity_id", "data_entity", "fk_dl_de"),
        _object_fk("external_entity_id", "external_entity", "fk_dl_ext"),
        _object_fk("bfc_node_flow_id", "bfc_node_flow", "fk_dl_flow"),
        # A constraint, not an index, so save() can name it in ON CONFLICT (S2-6).
        UniqueConstraint("project_id", "diagram_type", "scope_bfc_node_id", *OBJECT_COLUMNS,
                         name="uq_dl_object", postgresql_nulls_not_distinct=True),
        CheckConstraint("diagram_type IN ('ERD', 'PROCESS_FLOW', 'DFD')", name="ck_dl_type"),
        CheckConstraint("num_nonnulls(bfc_node_id, data_entity_id, external_entity_id, "
                        "bfc_node_flow_id) = 1", name="ck_dl_one_object"),
        CheckConstraint("diagram_type <> 'ERD' OR data_entity_id IS NOT NULL", name="ck_dl_erd_entity"),
        CheckConstraint("diagram_type = 'PROCESS_FLOW' OR bfc_node_flow_id IS NULL",
                        name="ck_dl_event_flow_only"),
        CheckConstraint("diagram_type = 'ERD' OR scope_bfc_node_id IS NOT NULL", name="ck_dl_scope"),
        CheckConstraint("width IS NULL OR width > 0", name="ck_dl_width"),
        CheckConstraint("height IS NULL OR height > 0", name="ck_dl_height"),
        CheckConstraint("diagram_type = 'ERD' OR NOT is_collapsed", name="ck_dl_collapse_erd"),
        *(Index(f"ix_dl_{short}", col, "project_id", postgresql_where=text(f"{col} IS NOT NULL"))
          for short, col in (("scope", "scope_bfc_node_id"), ("node", "bfc_node_id"),
                             ("de", "data_entity_id"), ("ext", "external_entity_id"),
                             ("flow", "bfc_node_flow_id"))),
    )

    def owning_project_id(self) -> int:
        return self.project_id
