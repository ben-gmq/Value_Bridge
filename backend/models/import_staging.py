"""Import staging (§5.3, D-5, D-25, Q14; docs/slice4_schema.md): the two tables of the one import
pipeline (VB law 8). Every target — DE, DF, Issue, BR, FR, WBS, flow JSON — fits them with no
schema change. Deviation 7c: neither table carries the full audit set. Written only by bulk.py."""
from datetime import datetime

from sqlalchemy import (
    BigInteger, CheckConstraint, Computed, DateTime, ForeignKey, ForeignKeyConstraint, Identity,
    Index, Integer, String, UniqueConstraint, func, text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base

TARGET_ENTITIES = ("ISSUE", "DATA_ENTITY", "DATA_FIELD", "BUSINESS_REQUIREMENT",
                   "FUNCTION_REQUIREMENT", "PROCESS_FLOW", "WBS_ITEM")
COUNT_COLUMNS = ("row_count", "error_count", "warning_count", "insert_count", "update_count",
                 "retire_count")


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


class ImportBatch(Base):
    """One uploaded file — the import trail (who, when, what, counts, outcome). Never deleted by
    the app, never retired: its status is its lifecycle. Not AuditMixin (no soft delete);
    uploaded_at / uploaded_by_user_id are its created pair. updated_at is set by
    trg_import_batch_updated_at; row_version is the version_id_col (the AppUser shape). vb_app
    may UPDATE only the lifecycle columns plus file_name, which the purge blanks to '(purged)'
    (column grant, Q-17b amended by S4-11/Q6)."""

    __tablename__ = "import_batch"

    import_batch_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("project.project_id"), nullable=False)
    target_entity: Mapped[str] = mapped_column(String(30), nullable=False)
    source_format: Mapped[str] = mapped_column(String(40), nullable=False, server_default="xlsx")
    import_mode: Mapped[str | None] = mapped_column(String(10))
    anchor_bfc_node_id: Mapped[int | None] = mapped_column(BigInteger)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    uploaded_by_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                  server_default=func.now())
    status_code_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status_category: Mapped[str] = mapped_column(String(40), Computed("'IMPORT_STATUS'", persisted=True))
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    warning_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    insert_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    update_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    retire_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    file_warning_detail: Mapped[list] = mapped_column(JSONB, nullable=False,
                                                      server_default=text("'[]'::jsonb"))
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    committed_by_user_id: Mapped[int | None] = mapped_column(BigInteger)
    rows_purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                 server_default=func.now())
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")

    status_code_row = relationship("CodeMaster", viewonly=True, lazy="joined",
                                   primaryjoin="foreign(ImportBatch.status_code_id) == CodeMaster.code_id")

    @property
    def status_code(self) -> str | None:
        return self.status_code_row.code if self.status_code_row is not None else None

    __mapper_args__ = {"version_id_col": row_version}
    __table_args__ = (
        # Q-19: the composite target for wbs_item.last_import_batch_id.
        UniqueConstraint("import_batch_id", "project_id", name="uq_import_batch_project"),
        # Q-2: the carrier target for import_row.
        UniqueConstraint("import_batch_id", "target_entity", name="uq_import_batch_target"),
        # Q-18: existence + tenancy only; live and non-process are service-checked.
        ForeignKeyConstraint(["anchor_bfc_node_id", "project_id"],
                             ["bfc_node.bfc_node_id", "bfc_node.project_id"], name="fk_ib_anchor"),
        ForeignKeyConstraint(["uploaded_by_user_id"], ["app_user.app_user_id"], name="fk_ib_uploaded_by"),
        ForeignKeyConstraint(["committed_by_user_id"], ["app_user.app_user_id"], name="fk_ib_committed_by"),
        ForeignKeyConstraint(["status_code_id", "status_category"],
                             ["code_master.code_id", "code_master.category"],
                             name="fk_ib_status_code", onupdate="NO ACTION"),
        CheckConstraint(f"target_entity IN ({_in(TARGET_ENTITIES)})", name="ck_ib_target_entity"),
        CheckConstraint("(target_entity = 'PROCESS_FLOW') = (source_format LIKE 'vb-process-flow/%')",
                        name="ck_ib_flow_format"),
        CheckConstraint("import_mode IN ('MERGE', 'REPLACE')", name="ck_ib_import_mode"),
        CheckConstraint("(target_entity IN ('PROCESS_FLOW', 'WBS_ITEM')) = (import_mode IS NOT NULL)",
                        name="ck_ib_mode_targets"),
        CheckConstraint("(target_entity = 'PROCESS_FLOW') = (anchor_bfc_node_id IS NOT NULL)",
                        name="ck_ib_flow_anchor"),
        CheckConstraint(f"least({', '.join(COUNT_COLUMNS)}) >= 0", name="ck_ib_counts_nonneg"),
        CheckConstraint("error_count <= row_count AND warning_count <= row_count "
                        "AND insert_count + update_count + retire_count <= row_count",
                        name="ck_ib_counts_bounded"),
        # "Merge never retires" (§7.2b rule 7, §7.11a).
        CheckConstraint("retire_count = 0 OR import_mode IS NOT DISTINCT FROM 'REPLACE'", name="ck_ib_retire_needs_replace"),
        CheckConstraint("(committed_at IS NULL) = (committed_by_user_id IS NULL)",
                        name="ck_ib_committed_pair"),
        CheckConstraint("committed_at IS NULL OR committed_at >= uploaded_at",
                        name="ck_ib_commit_after_upload"),
        CheckConstraint("rows_purged_at IS NULL OR rows_purged_at >= uploaded_at",
                        name="ck_ib_purge_after_upload"),
        CheckConstraint("btrim(file_name) <> ''", name="ck_ib_file_name"),
        CheckConstraint("btrim(source_format) <> ''", name="ck_ib_source_format"),
        CheckConstraint("jsonb_typeof(file_warning_detail) = 'array'", name="ck_ib_file_warning_array"),
        Index("ix_ib_purge_due", "uploaded_at", postgresql_where=text("rows_purged_at IS NULL")),
        Index("ix_ib_project", "project_id", uploaded_at.desc()),
        Index("ix_ib_anchor", "anchor_bfc_node_id", "project_id",
              postgresql_where=text("anchor_bfc_node_id IS NOT NULL")),
        Index("ix_ib_status", "status_code_id"),
    )

    def owning_project_id(self) -> int:
        return self.project_id
