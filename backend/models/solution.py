"""Solution (§5.3, area 4, D-7): the project's transformation answers and the BRs each one
answers. Schema: docs/slice5_schema.md. Both frozen into baselines (shadows generated later)."""
from sqlalchemy import (
    BigInteger, CheckConstraint, Computed, ForeignKey, ForeignKeyConstraint, Identity, Index, String,
    Text, UniqueConstraint, func, text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import AuditMixin, Base


class Solution(AuditMixin, Base):
    """One transformation answer in one project. Status is set to PROPOSED by the service (Q-4)."""

    __tablename__ = "solution"

    solution_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("project.project_id"), nullable=False)
    solution_number: Mapped[str] = mapped_column(String(20), nullable=False)
    solution_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    category_code_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    category_category: Mapped[str] = mapped_column(String(40), Computed("'SOLUTION_CATEGORY'", persisted=True))
    status_code_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status_category: Mapped[str] = mapped_column(String(40), Computed("'SOLUTION_STATUS'", persisted=True))
    benefit_note: Mapped[str | None] = mapped_column(Text)
    effort_note: Mapped[str | None] = mapped_column(Text)

    category_code_row = relationship("CodeMaster", viewonly=True, lazy="joined",
                                     primaryjoin="foreign(Solution.category_code_id) == CodeMaster.code_id")
    status_code_row = relationship("CodeMaster", viewonly=True, lazy="joined",
                                   primaryjoin="foreign(Solution.status_code_id) == CodeMaster.code_id")

    @property
    def category_code(self) -> str | None:
        return self.category_code_row.code if self.category_code_row is not None else None

    @property
    def status_code(self) -> str | None:
        return self.status_code_row.code if self.status_code_row is not None else None

    __table_args__ = (
        UniqueConstraint("project_id", "solution_number", name="uq_solution_number"),
        UniqueConstraint("solution_id", "project_id", name="uq_solution_project"),
        ForeignKeyConstraint(["category_code_id", "category_category"],
                             ["code_master.code_id", "code_master.category"],
                             name="fk_sol_category_code", onupdate="NO ACTION"),
        ForeignKeyConstraint(["status_code_id", "status_category"],
                             ["code_master.code_id", "code_master.category"],
                             name="fk_sol_status_code", onupdate="NO ACTION"),
        CheckConstraint("btrim(solution_name) <> ''", name="ck_sol_name_not_blank"),
        Index("uq_solution_name_live", "project_id", func.lower(func.btrim(solution_name)), unique=True,
              postgresql_where=text("is_active")),
        Index("ix_sol_category", "category_code_id"),
        Index("ix_sol_status", "status_code_id"),
    )

    def owning_project_id(self) -> int:
        return self.project_id


class BrSolution(AuditMixin, Base):
    """BR × solution, with the coverage note. S1-5: surrogate PK; the design's key is a full UNIQUE,
    so a re-link restores the old row. Retires and restores with its BR's step (S5-1)."""

    __tablename__ = "br_solution"

    br_solution_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("project.project_id"), nullable=False)
    br_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    solution_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    coverage_note: Mapped[str | None] = mapped_column(Text)

    # Read-only: the two-ended label "BR-0042 ↔ SOL-0003" a 409 or a retire preview shows (DR1-P1).
    br_row = relationship("BusinessRequirement", viewonly=True,
                          primaryjoin="foreign(BrSolution.br_id) == BusinessRequirement.br_id")
    solution_row = relationship("Solution", viewonly=True,
                                primaryjoin="foreign(BrSolution.solution_id) == Solution.solution_id")

    __table_args__ = (
        UniqueConstraint("br_id", "solution_id", name="uq_brsol_grain"),
        ForeignKeyConstraint(["br_id", "project_id"],
                             ["business_requirement.br_id", "business_requirement.project_id"],
                             name="fk_brsol_br"),
        ForeignKeyConstraint(["solution_id", "project_id"],
                             ["solution.solution_id", "solution.project_id"], name="fk_brsol_solution"),
        Index("ix_brsol_solution", "solution_id", "project_id"),
        Index("ix_brsol_project", "project_id"),
    )

    def owning_project_id(self) -> int:
        return self.project_id
