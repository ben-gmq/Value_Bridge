"""Function requirement (§5.3, area 4, D-7/D-27/D-28): one FTC-specified system function in one
project, optionally under a Solution. Schema: docs/slice6a_schema.md, as amended by S6a-1
(suggested_br_id waits for the FR import). Frozen into baselines (shadow generated later)."""
from sqlalchemy import (
    BigInteger, CheckConstraint, Computed, ForeignKey, ForeignKeyConstraint, Identity, Index, Numeric,
    String, Text, UniqueConstraint, text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import AuditMixin, Base


class FunctionRequirement(AuditMixin, Base):
    """fr_type_behaviour is a verified copy of the type's behaviour (D-27). complexity_code_id and
    effort_days are always NULL until the rate card (S6a-3); the CHECK ties them together (D-13)."""

    __tablename__ = "function_requirement"

    fr_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("project.project_id"), nullable=False)
    fr_number: Mapped[str] = mapped_column(String(20), nullable=False)
    fr_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    solution_id: Mapped[int | None] = mapped_column(BigInteger)
    fr_type_code_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    fr_type_category: Mapped[str] = mapped_column(String(40), Computed("'FR_TYPE'", persisted=True))
    fr_type_behaviour: Mapped[str] = mapped_column(String(20), nullable=False)
    complexity_code_id: Mapped[int | None] = mapped_column(BigInteger)
    complexity_category: Mapped[str] = mapped_column(String(40), Computed("'FR_COMPLEXITY'", persisted=True))
    effort_days = mapped_column(Numeric(7, 2))
    fulfilment_status_code_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    fulfilment_status_category: Mapped[str] = mapped_column(
        String(40), Computed("'FR_FULFILMENT_STATUS'", persisted=True))
    acceptance_note: Mapped[str | None] = mapped_column(Text)

    fr_type_code_row = relationship("CodeMaster", viewonly=True, lazy="joined",
                                    primaryjoin="foreign(FunctionRequirement.fr_type_code_id) == CodeMaster.code_id")
    complexity_code_row = relationship("CodeMaster", viewonly=True, lazy="joined",
                                       primaryjoin="foreign(FunctionRequirement.complexity_code_id) == CodeMaster.code_id")
    fulfilment_code_row = relationship("CodeMaster", viewonly=True, lazy="joined",
                                       primaryjoin="foreign(FunctionRequirement.fulfilment_status_code_id) == CodeMaster.code_id")
    solution_row = relationship("Solution", viewonly=True,
                                primaryjoin="foreign(FunctionRequirement.solution_id) == Solution.solution_id")

    @property
    def fr_type_code(self) -> str | None:
        return self.fr_type_code_row.code if self.fr_type_code_row is not None else None

    @property
    def complexity_code(self) -> str | None:
        return self.complexity_code_row.code if self.complexity_code_row is not None else None

    @property
    def fulfilment_status_code(self) -> str | None:
        return self.fulfilment_code_row.code if self.fulfilment_code_row is not None else None

    __table_args__ = (
        UniqueConstraint("project_id", "fr_number", name="uq_fr_number"),
        UniqueConstraint("fr_id", "project_id", name="uq_fr_project"),
        UniqueConstraint("fr_id", "project_id", "fr_type_behaviour", name="uq_fr_behaviour_target"),
        ForeignKeyConstraint(["solution_id", "project_id"], ["solution.solution_id", "solution.project_id"],
                             name="fk_fr_solution"),
        ForeignKeyConstraint(["fr_type_code_id", "fr_type_category", "fr_type_behaviour"],
                             ["code_master.code_id", "code_master.category", "code_master.behaviour_code"],
                             name="fk_fr_type_code", onupdate="NO ACTION"),
        ForeignKeyConstraint(["complexity_code_id", "complexity_category"],
                             ["code_master.code_id", "code_master.category"],
                             name="fk_fr_complexity_code", onupdate="NO ACTION"),
        ForeignKeyConstraint(["fulfilment_status_code_id", "fulfilment_status_category"],
                             ["code_master.code_id", "code_master.category"],
                             name="fk_fr_fulfilment_code", onupdate="NO ACTION"),
        CheckConstraint("btrim(fr_name) <> ''", name="ck_fr_name_not_blank"),
        CheckConstraint("(complexity_code_id IS NULL) = (effort_days IS NULL)", name="ck_fr_effort_with_complexity"),
        CheckConstraint("effort_days IS NULL OR effort_days >= 0", name="ck_fr_effort_nonneg"),
        Index("ix_fr_solution", "solution_id", "project_id"),
        Index("ix_fr_unlinked", "project_id", postgresql_where=text("solution_id IS NULL AND is_active")),
        Index("ix_fr_behaviour", "project_id", "fr_type_behaviour", postgresql_where=text("is_active")),
        Index("ix_fr_type", "fr_type_code_id"),
        Index("ix_fr_complexity", "complexity_code_id"),
        Index("ix_fr_fulfilment", "fulfilment_status_code_id"),
    )

    def owning_project_id(self) -> int:
        return self.project_id
