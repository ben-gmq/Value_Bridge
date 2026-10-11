"""Rate card (§5.3 EFFORT_RATE, D-13, R2-D7): one cell per (project × FR type × complexity) →
standard man-days, with the reason for its current value. Schema: docs/slice6c_schema.md; spec
docs/slice6c_spec.md. Read only through services/effort.rate_for. Frozen into baselines later."""
from sqlalchemy import (
    BigInteger, CheckConstraint, Computed, ForeignKey, ForeignKeyConstraint, Identity, Index, Numeric, String, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import AuditMixin, Base


class EffortRate(AuditMixin, Base):
    """Surrogate PK, the design's natural key a full UNIQUE (apple Q-1). A change to standard_days must
    bump row_version and carry a reason — a CHECK for the seeded state, a trigger for every UPDATE
    (DR6c-D1). Never retired in 6c."""

    __tablename__ = "effort_rate"

    effort_rate_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("project.project_id"), nullable=False)
    fr_type_code_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    fr_type_category: Mapped[str] = mapped_column(String(40), Computed("'FR_TYPE'", persisted=True))
    complexity_code_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    complexity_category: Mapped[str] = mapped_column(String(40), Computed("'FR_COMPLEXITY'", persisted=True))
    standard_days = mapped_column(Numeric(7, 2), nullable=False)
    change_rationale: Mapped[str | None] = mapped_column(Text)

    fr_type_code_row = relationship("CodeMaster", viewonly=True, lazy="joined",
                                    primaryjoin="foreign(EffortRate.fr_type_code_id) == CodeMaster.code_id")
    complexity_code_row = relationship("CodeMaster", viewonly=True, lazy="joined",
                                       primaryjoin="foreign(EffortRate.complexity_code_id) == CodeMaster.code_id")

    __table_args__ = (
        UniqueConstraint("project_id", "fr_type_code_id", "complexity_code_id", name="uq_effort_rate_cell"),
        ForeignKeyConstraint(["fr_type_code_id", "fr_type_category"], ["code_master.code_id", "code_master.category"],
                             name="fk_effort_rate_type", onupdate="NO ACTION"),
        ForeignKeyConstraint(["complexity_code_id", "complexity_category"], ["code_master.code_id", "code_master.category"],
                             name="fk_effort_rate_complexity", onupdate="NO ACTION"),
        CheckConstraint("standard_days > 0 AND standard_days <> 'NaN'", name="ck_effort_rate_days_positive"),
        CheckConstraint("row_version = 1 OR change_rationale IS NOT NULL", name="ck_effort_rate_rationale"),
        CheckConstraint("change_rationale IS NULL OR btrim(change_rationale) <> ''",
                        name="ck_effort_rate_rationale_not_blank"),
        Index("ix_effort_rate_type", "fr_type_code_id"),
        Index("ix_effort_rate_complexity", "complexity_code_id"),
    )

    def owning_project_id(self) -> int:
        return self.project_id
