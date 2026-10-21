"""Shared (§5.3): CODE_MASTER (two-tier, with behaviour), PROJECT_SEQUENCE and VB_INSTANCE (slice 16)."""
from datetime import datetime

from sqlalchemy import (
    ARRAY, BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Identity, Index, Integer, String, Text,
    UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from models.base import AuditMixin, Base

FR_BEHAVIOURS = ("FORM", "INTERFACE", "REPORT", "BATCH", "OTHER")
RACI_BEHAVIOURS = ("RESPONSIBLE", "ACCOUNTABLE", "CONSULTED", "INFORMED", "SUPPORT", "OTHER")
ISSUE_STATUS_BEHAVIOURS = ("OPEN", "CLOSED")          # slice14 §15 N1–N2, I-1 (migration 0061)SEQUENCE_CODES = ("DE", "BR", "FR", "ISSUE", "SOL", "BEN", "RSK", "CR", "DEC", "EXT")


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


class CodeMaster(AuditMixin, Base):
    """project_id NULL = the FTC-wide library; non-null = a project override (A-16).
    Resolution has one owner: services/code_master.resolve (finding D12)."""

    __tablename__ = "code_master"

    code_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    project_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("project.project_id", use_alter=True, name="fk_code_master_project")
    )
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    behaviour_code: Mapped[str | None] = mapped_column(String(20))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    # Seeded FTC library rows have no author — the one nullable created_by (deviation 7).
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("app_user.app_user_id"))

    __table_args__ = (
        Index("uq_code_master_scope", "project_id", "category", "code", unique=True,
              postgresql_nulls_not_distinct=True),
        CheckConstraint(
            "(category IN ('FR_TYPE','RACI_TYPE','ISSUE_STATUS')) = (behaviour_code IS NOT NULL)",
            name="ck_code_behaviour_present"),
        CheckConstraint(f"category <> 'FR_TYPE' OR behaviour_code IN ({_in(FR_BEHAVIOURS)})",
                        name="ck_code_fr_behaviour"),
        CheckConstraint(f"category <> 'RACI_TYPE' OR behaviour_code IN ({_in(RACI_BEHAVIOURS)})",
                        name="ck_code_raci_behaviour"),
        CheckConstraint(f"category <> 'ISSUE_STATUS' OR behaviour_code IN ({_in(ISSUE_STATUS_BEHAVIOURS)})",
                        name="ck_code_issue_status_behaviour"),        # Composite-FK target: category is in it because both vocabularies share OTHER (§5.3).
        UniqueConstraint("code_id", "category", "behaviour_code", name="uq_code_behaviour_target"),
        UniqueConstraint("code_id", "category", name="uq_code_category_target"),
    )

    def owning_project_id(self) -> int | None:
        """None for a company row, so object_guard keeps it platform-admin only (404 to anyone else, slice1g R9)."""
        return self.project_id


class ProjectCodeVisibility(AuditMixin, Base):
    """A company code one project has hidden from its pickers (wave 1g, G-1): one row per (project, company code) for
    life — live = hidden now; unhide retires it, hide again restores it (S1-7). Only services/code_lists writes it.
    Not shadowed: hiding never changes what a row holds or a baseline froze."""

    __tablename__ = "project_code_visibility"

    project_code_visibility_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("project.project_id"), nullable=False)
    code_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("code_master.code_id"), nullable=False)

    __table_args__ = (UniqueConstraint("project_id", "code_id", name="uq_pcv_project_code"),)

    def owning_project_id(self) -> int:
        return self.project_id


class ProjectSequence(Base):
    """One counter per (project, series). All ten are seeded by create_project (R2-D14);
    next_number raises on a missing row and never inserts one lazily."""

    __tablename__ = "project_sequence"

    project_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("project.project_id"), primary_key=True
    )
    sequence_code: Mapped[str] = mapped_column(String(10), primary_key=True)
    prefix: Mapped[str] = mapped_column(String(10), nullable=False)
    pad_width: Mapped[int] = mapped_column(Integer, nullable=False, server_default="4")
    last_value: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")

    __table_args__ = (
        CheckConstraint(f"sequence_code IN ({_in(SEQUENCE_CODES)})", name="ck_sequence_code"),
    )


class VbInstance(Base):
    """This database's archive identity (slice16 schema §3.4, §12.7; 0069): one row, stamped by the owner-run
    scripts.stamp_instance, read by the app. Every archive file and key name starts with `instance_id`; a re-stamp
    keeps the old ids in `prior_instance_ids`, whose tombstones still count (§18 S6). Not a business table."""

    __tablename__ = "vb_instance"

    one_row: Mapped[bool] = mapped_column(Boolean, primary_key=True, server_default="true")
    instance_id: Mapped[str] = mapped_column(String(40), nullable=False)
    prior_instance_ids: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default="{}")
    stamped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint("one_row", name="ck_vi_one_row"),
        CheckConstraint("instance_id ~ '^[a-z0-9][a-z0-9-]{2,39}$'", name="ck_vi_instance_id"),
    )
