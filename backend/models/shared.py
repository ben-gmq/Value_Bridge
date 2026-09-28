"""Shared (§5.3): CODE_MASTER (two-tier, with behaviour) and PROJECT_SEQUENCE."""
from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, ForeignKey, Identity, Index, Integer, String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from models.base import AuditMixin, Base

FR_BEHAVIOURS = ("FORM", "INTERFACE", "REPORT", "BATCH", "OTHER")
RACI_BEHAVIOURS = ("RESPONSIBLE", "ACCOUNTABLE", "CONSULTED", "INFORMED", "SUPPORT", "OTHER")
SEQUENCE_CODES = ("DE", "BR", "FR", "ISSUE", "SOL", "BEN", "RSK", "CR", "DEC", "EXT")


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

    __table_args__ = (
        Index("uq_code_master_scope", "project_id", "category", "code", unique=True,
              postgresql_nulls_not_distinct=True),
        CheckConstraint(
            "(category IN ('FR_TYPE','RACI_TYPE')) = (behaviour_code IS NOT NULL)",
            name="ck_code_behaviour_present"),
        CheckConstraint(f"category <> 'FR_TYPE' OR behaviour_code IN ({_in(FR_BEHAVIOURS)})",
                        name="ck_code_fr_behaviour"),
        CheckConstraint(f"category <> 'RACI_TYPE' OR behaviour_code IN ({_in(RACI_BEHAVIOURS)})",
                        name="ck_code_raci_behaviour"),
        # Composite-FK target: category is in it because both vocabularies share OTHER (§5.3).
        UniqueConstraint("code_id", "category", "behaviour_code", name="uq_code_behaviour_target"),
        UniqueConstraint("code_id", "category", name="uq_code_category_target"),
    )


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
