"""Baselines (§4.6, §5.3 area 6; slice8_schema §2–§3): the header, one row per frozen version of one
project's scope, and the 24 generated shadow tables that hold the frozen rows.

The header has no soft delete (A-36) and no created_* pair: frozen_at / frozen_by_user_id are that pair
under the design's names [Q-6]. Only the status, the approval set, updated_by and row_version may change,
by column grant and by trg_baseline_header_guard (0047). Shadows are Core Tables built by
services/baseline_shadow.py from the live models — never hand-written (law 2) — and are written only by
services/baseline.freeze with INSERT … SELECT."""
from datetime import date, datetime

from sqlalchemy import (ARRAY, CHAR, BigInteger, CheckConstraint, Computed, Date, DateTime, ForeignKey, ForeignKeyConstraint,
                        Identity, Index, Integer, SmallInteger, String, Text, UniqueConstraint, func, text)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base
# The shadowed live tables must be on Base.metadata before SHADOW_TABLES is built.
import models.application  # noqa: F401
import models.bfc  # noqa: F401
import models.client_org  # noqa: F401
import models.data_model  # noqa: F401
import models.effort  # noqa: F401
import models.function_requirement  # noqa: F401
import models.requirement  # noqa: F401
import models.solution  # noqa: F401
import models.tenancy  # noqa: F401
from services.baseline_shadow import shadow_table


_ELEMENTS = "ARRAY['STARTED','DATA_IN','DATA_OUT','EXTERNAL','ORDER']::varchar(12)[]"
DFD_RULE_VALS = (f"dfd_rule_to_be IS NULL OR (cardinality(dfd_rule_to_be) >= 1 AND cardinality(dfd_rule_as_is) >= 1 "
                 f"AND dfd_rule_to_be <@ {_ELEMENTS} AND dfd_rule_as_is <@ {_ELEMENTS})")


class Baseline(Base):
    __tablename__ = "baseline"

    baseline_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("project.project_id"), nullable=False)
    major_no: Mapped[int] = mapped_column(Integer, nullable=False)
    minor_no: Mapped[int] = mapped_column(Integer, nullable=False)
    version_label: Mapped[str] = mapped_column(
        String(24), Computed("'v' || major_no || '.' || minor_no", persisted=True))
    status_code_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status_category: Mapped[str] = mapped_column(String(40), Computed("'BASELINE_STATUS'", persisted=True))
    hash_spec_version: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    data_model_depth: Mapped[str] = mapped_column(String(10), nullable=False)
    # D-70 (slice13_schema §2.6, 0053): the DFD rule each chart passed at the freeze, sorted. Both NULL = frozen
    # before 13b, i.e. the D-38 rule. Header facts like data_model_depth: frozen by the guard, not in the digest.
    dfd_rule_to_be: Mapped[list[str] | None] = mapped_column(ARRAY(String(12)))
    dfd_rule_as_is: Mapped[list[str] | None] = mapped_column(ARRAY(String(12)))
    note: Mapped[str | None] = mapped_column(Text)
    prior_baseline_id: Mapped[int | None] = mapped_column(BigInteger)
    frozen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    frozen_by_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("app_user.app_user_id"), nullable=False)
    content_digest: Mapped[str] = mapped_column(CHAR(64), nullable=False)          # DR8-S1
    client_approver_name: Mapped[str | None] = mapped_column(String(200))
    client_approved_on: Mapped[date | None] = mapped_column(Date)
    approval_note: Mapped[str | None] = mapped_column(Text)
    approval_reference: Mapped[str | None] = mapped_column(String(200))           # DR8-Q3
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by_user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("app_user.app_user_id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("app_user.app_user_id"))
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")

    status_code_row = relationship("CodeMaster", viewonly=True, lazy="joined",
                                   primaryjoin="foreign(Baseline.status_code_id) == CodeMaster.code_id")

    @property
    def status_code(self) -> str | None:
        return self.status_code_row.code if self.status_code_row is not None else None

    __mapper_args__ = {"version_id_col": row_version}
    __table_args__ = (
        UniqueConstraint("baseline_id", "project_id", name="uq_baseline_project"),
        UniqueConstraint("project_id", "major_no", "minor_no", name="uq_baseline_version"),
        UniqueConstraint("project_id", "version_label", name="uq_baseline_label"),
        UniqueConstraint("prior_baseline_id", name="uq_baseline_prior"),
        Index("uq_baseline_first", "project_id", unique=True, postgresql_where=text("prior_baseline_id IS NULL")),
        Index("ix_baseline_status", "status_code_id"),
        CheckConstraint("major_no >= 1", name="ck_baseline_major"),
        CheckConstraint("minor_no >= 0", name="ck_baseline_minor"),
        CheckConstraint("hash_spec_version >= 1", name="ck_baseline_hash_spec"),
        CheckConstraint("data_model_depth IN ('KEYS_ONLY', 'FULL')", name="ck_baseline_depth"),
        CheckConstraint("note IS NULL OR btrim(note) <> ''", name="ck_baseline_note_not_blank"),
        CheckConstraint("num_nonnulls(dfd_rule_to_be, dfd_rule_as_is) IN (0, 2)", name="ck_baseline_dfd_rule_pair"),
        CheckConstraint(DFD_RULE_VALS, name="ck_baseline_dfd_rule_vals"),
        CheckConstraint("approval_note IS NULL OR btrim(approval_note) <> ''",
                        name="ck_baseline_approval_note_not_blank"),
        CheckConstraint("approval_reference IS NULL OR client_approver_name IS NOT NULL",
                        name="ck_baseline_approval_reference"),
        CheckConstraint("(prior_baseline_id IS NULL) = (major_no = 1 AND minor_no = 0)", name="ck_baseline_prior"),
        CheckConstraint("num_nonnulls(client_approver_name, client_approved_on, approved_at, "
                        "approved_by_user_id) IN (0, 4)", name="ck_baseline_approval_set"),
        ForeignKeyConstraint(["prior_baseline_id", "project_id"], ["baseline.baseline_id", "baseline.project_id"],
                             name="fk_baseline_prior"),
        ForeignKeyConstraint(["status_code_id", "status_category"], ["code_master.code_id", "code_master.category"],
                             name="fk_baseline_status", onupdate="NO ACTION"),
    )

    def owning_project_id(self) -> int:
        return self.project_id


# The live tables a baseline freezes, in freeze (FK) order (§6.1 less the unbuilt tables; slice8 §3.1).
# br_function_requirement joined at hash spec 2 (slice10b §5.2), right after function_requirement.
# services/freeze_set.FREEZE_SET carries the rest of each entry; a test asserts the two agree.
SHADOWED = ("org_unit", "org_role", "bfc_node", "data_entity", "data_field", "external_entity",
            "process_trigger", "bfc_node_data_entity", "bfc_node_org_role", "bfc_node_external_flow",
            "bfc_node_trigger", "business_requirement", "br_data_entity", "br_org_role", "application",
            "solution", "br_solution", "function_requirement", "br_function_requirement", "fr_interface", "fr_interface_data_entity",
            "application_solution", "application_bfc_node", "effort_rate", "project_component")

SHADOW_TABLES = {name: shadow_table(Base.metadata.tables[name], Base.metadata) for name in SHADOWED}
