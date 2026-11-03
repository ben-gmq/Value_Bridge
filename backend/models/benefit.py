"""Benefit (§4.9, §5 BENEFIT / BENEFIT_SOLUTION, D-14; docs/slice_benefits_spec.md, BN-1…BN-6).

BENEFIT — one row per quantified benefit in one project. A benefit with no accountable org role is not a benefit, it
is a hope: the role is NOT NULL (criterion 59). The status carries its behaviour (LIVE / ABANDONED, BN-3) through a
composite FK into code_master, as `risk.status_behaviour` does, so code branches on the behaviour (law 5). Target ≠
baseline (BN-1): a benefit that changes nothing is refused by the database too.

BENEFIT_SOLUTION — one row per (benefit × solution), ever: unlinking retires it, linking again restores it and its
frozen source_id (solution_phase's S1-7). `link_live` is TRUE while live, so the two live-guard FKs refuse a live link
under a retired benefit or solution whatever the timing (R1-M1, issue_br's pattern). The ≤ 100 % total across a
benefit's live links is services/benefit.py's, under a lock on the benefit (a CHECK sees one row).

Both are frozen with each baseline while BENEFIT is on (hash spec 7, services/freeze_set.py)."""
from decimal import Decimal

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Computed, Date, ForeignKey, ForeignKeyConstraint, Identity, Index, Numeric,
    String, Text, UniqueConstraint, func, text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import AuditMixin, Base


class Benefit(AuditMixin, Base):
    __tablename__ = "benefit"

    benefit_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("project.project_id"), nullable=False)
    benefit_number: Mapped[str] = mapped_column(String(20), nullable=False)
    benefit_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    benefit_type_code_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    benefit_type_category: Mapped[str] = mapped_column(String(40), Computed("'BENEFIT_TYPE'", persisted=True))
    measure_name: Mapped[str] = mapped_column(String(200), nullable=False)
    measure_unit: Mapped[str] = mapped_column(String(40), nullable=False)
    baseline_value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    target_value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    realisation_date = mapped_column(Date)
    accountable_org_role_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status_code_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status_category: Mapped[str] = mapped_column(String(40), Computed("'BENEFIT_STATUS'", persisted=True))
    status_behaviour: Mapped[str] = mapped_column(String(20), nullable=False)

    benefit_type_code_row = relationship("CodeMaster", viewonly=True, lazy="joined",
                                         primaryjoin="foreign(Benefit.benefit_type_code_id) == CodeMaster.code_id")
    status_code_row = relationship("CodeMaster", viewonly=True, lazy="joined",
                                   primaryjoin="foreign(Benefit.status_code_id) == CodeMaster.code_id")

    @property
    def benefit_type_code(self) -> str | None:
        return self.benefit_type_code_row.code if self.benefit_type_code_row is not None else None

    @property
    def status_code(self) -> str | None:
        return self.status_code_row.code if self.status_code_row is not None else None

    __table_args__ = (
        UniqueConstraint("project_id", "benefit_number", name="uq_benefit_number"),
        UniqueConstraint("benefit_id", "project_id", name="uq_benefit_project"),
        UniqueConstraint("benefit_id", "project_id", "is_active", name="uq_benefit_live_target"),
        ForeignKeyConstraint(["benefit_type_code_id", "benefit_type_category"],
                             ["code_master.code_id", "code_master.category"],
                             name="fk_benefit_type", onupdate="NO ACTION"),
        ForeignKeyConstraint(["status_code_id", "status_category", "status_behaviour"],
                             ["code_master.code_id", "code_master.category", "code_master.behaviour_code"],
                             name="fk_benefit_status", onupdate="NO ACTION"),
        ForeignKeyConstraint(["accountable_org_role_id", "project_id"], ["org_role.org_role_id", "org_role.project_id"],
                             name="fk_benefit_accountable"),
        CheckConstraint("btrim(benefit_name) <> ''", name="ck_benefit_name_not_blank"),
        CheckConstraint("btrim(measure_name) <> ''", name="ck_benefit_measure_not_blank"),
        CheckConstraint("btrim(measure_unit) <> ''", name="ck_benefit_unit_not_blank"),
        CheckConstraint("target_value <> baseline_value", name="ck_benefit_changes_something"),     # BN-1
        CheckConstraint("status_behaviour IN ('LIVE', 'ABANDONED')", name="ck_benefit_status_behaviour"),
        Index("ix_benefit_type", "benefit_type_code_id"),
        Index("ix_benefit_status", "status_code_id"),
        Index("ix_benefit_accountable", "accountable_org_role_id"),
        Index("ix_benefit_unit", "project_id", func.lower(func.btrim(measure_unit)), postgresql_where=text("is_active")),
    )

    def owning_project_id(self) -> int:
        return self.project_id


class BenefitSolution(AuditMixin, Base):
    __tablename__ = "benefit_solution"

    benefit_solution_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("project.project_id"), nullable=False)
    benefit_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    solution_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    contribution_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    link_live: Mapped[bool | None] = mapped_column(Boolean, Computed("CASE WHEN is_active THEN TRUE END", persisted=True))

    benefit_row = relationship("Benefit", viewonly=True, lazy="joined",
                               primaryjoin="foreign(BenefitSolution.benefit_id) == Benefit.benefit_id")
    solution_row = relationship("Solution", viewonly=True, lazy="joined",
                                primaryjoin="foreign(BenefitSolution.solution_id) == Solution.solution_id")

    __table_args__ = (
        UniqueConstraint("benefit_id", "solution_id", name="uq_bensol_grain"),
        ForeignKeyConstraint(["benefit_id", "project_id"], ["benefit.benefit_id", "benefit.project_id"],
                             name="fk_bensol_benefit"),
        ForeignKeyConstraint(["solution_id", "project_id"], ["solution.solution_id", "solution.project_id"],
                             name="fk_bensol_solution"),
        ForeignKeyConstraint(["benefit_id", "project_id", "link_live"],
                             ["benefit.benefit_id", "benefit.project_id", "benefit.is_active"],
                             name="fk_bensol_benefit_live"),
        ForeignKeyConstraint(["solution_id", "project_id", "link_live"],
                             ["solution.solution_id", "solution.project_id", "solution.is_active"],
                             name="fk_bensol_solution_live"),
        CheckConstraint("contribution_pct > 0 AND contribution_pct <= 100", name="ck_bensol_pct"),
        Index("ix_bensol_solution", "solution_id"),
    )

    def owning_project_id(self) -> int:
        return self.project_id
