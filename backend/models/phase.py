"""Waves (D-18; docs/slice15_phasing_spec.md, slice15_phasing_schema.md; W-1…W-9).

A PHASE is a delivery wave within one project, shown as "Wave" on every screen (W-1); inside the code the names stay
`phase`. Frozen from hash spec 6 (schema §7)."""
from sqlalchemy import (
    BigInteger, CheckConstraint, Computed, Date, ForeignKey, ForeignKeyConstraint, Identity, Index, Numeric,
    SmallInteger, String, Text, UniqueConstraint, func, text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import AuditMixin, Base


class Phase(AuditMixin, Base):
    """One wave of one project. The code is typed ("P1", "Wave 2"), no number series. `seq_no` is the order (dates are
    information and may overlap); negatives only mid-reorder (S1-2/S1-3). The status is company-only (W-4)."""

    __tablename__ = "phase"

    phase_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("project.project_id"), nullable=False)
    phase_code: Mapped[str] = mapped_column(String(20), nullable=False)
    phase_name: Mapped[str] = mapped_column(String(200), nullable=False)
    seq_no: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    start_date = mapped_column(Date)
    end_date = mapped_column(Date)
    status_code_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status_category: Mapped[str] = mapped_column(String(40), Computed("'PHASE_STATUS'", persisted=True))

    status_code_row = relationship("CodeMaster", viewonly=True, lazy="joined",
                                   primaryjoin="foreign(Phase.status_code_id) == CodeMaster.code_id")

    @property
    def status_code(self) -> str | None:
        return self.status_code_row.code if self.status_code_row is not None else None

    __table_args__ = (
        UniqueConstraint("phase_id", "project_id", name="uq_phase_project"),
        ForeignKeyConstraint(["status_code_id", "status_category"], ["code_master.code_id", "code_master.category"],
                             name="fk_phase_status", onupdate="NO ACTION"),
        CheckConstraint("btrim(phase_code) <> ''", name="ck_phase_code_not_blank"),
        CheckConstraint("btrim(phase_name) <> ''", name="ck_phase_name_not_blank"),
        CheckConstraint("seq_no <> 0 AND seq_no BETWEEN -99 AND 99", name="ck_phase_seq"),
        CheckConstraint("end_date IS NULL OR start_date IS NULL OR end_date >= start_date", name="ck_phase_dates"),
        Index("uq_phase_code_live", "project_id", func.lower(func.btrim(phase_code)), unique=True,
              postgresql_where=text("is_active")),
        Index("uq_phase_seq_live", "project_id", "seq_no", unique=True, postgresql_where=text("is_active")),
        Index("ix_phase_status", "status_code_id"),
    )

    def owning_project_id(self) -> int:
        return self.project_id


class SolutionPhase(AuditMixin, Base):
    """The share of one solution's current effort that lands in one wave (D-18, W-5). A solution's live rows total
    exactly 100 or there are none — a cross-row rule kept by the whole-split PUT under a lock (schema §5). The grain is
    unique in full, so re-assigning a wave restores its row and keeps its source_id (S1-7)."""

    __tablename__ = "solution_phase"

    solution_phase_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("project.project_id"), nullable=False)
    solution_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    phase_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    portion_pct = mapped_column(Numeric(5, 2), nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(["solution_id", "project_id"], ["solution.solution_id", "solution.project_id"],
                             name="fk_solph_solution"),
        ForeignKeyConstraint(["phase_id", "project_id"], ["phase.phase_id", "phase.project_id"],
                             name="fk_solph_phase"),
        UniqueConstraint("solution_id", "phase_id", name="uq_solph_grain"),
        CheckConstraint("portion_pct > 0 AND portion_pct <= 100", name="ck_solph_portion"),
        Index("ix_solph_phase", "phase_id", "project_id"),
        Index("ix_solph_project", "project_id"),
    )

    def owning_project_id(self) -> int:
        return self.project_id


class SolutionDependency(AuditMixin, Base):
    """One edge: solution_id needs depends_on_solution_id (D-18). Never self (the one cycle a CHECK sees); every
    other cycle is refused by services/phasing.link_solution_dependency under a per-project advisory lock (schema §4)
    — the only writer of live edges, restores included. Composite FKs keep the graph inside one project."""

    __tablename__ = "solution_dependency"

    solution_dependency_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("project.project_id"), nullable=False)
    solution_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    depends_on_solution_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        ForeignKeyConstraint(["solution_id", "project_id"], ["solution.solution_id", "solution.project_id"],
                             name="fk_soldep_solution"),
        ForeignKeyConstraint(["depends_on_solution_id", "project_id"], ["solution.solution_id", "solution.project_id"],
                             name="fk_soldep_prereq"),
        UniqueConstraint("solution_id", "depends_on_solution_id", name="uq_soldep_grain"),
        CheckConstraint("solution_id <> depends_on_solution_id", name="ck_soldep_not_self"),
        Index("ix_soldep_prereq", "depends_on_solution_id", "project_id"),
    )

    def owning_project_id(self) -> int:
        return self.project_id
