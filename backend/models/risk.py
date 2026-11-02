"""Risk (§4.10, §5 RISK, D-15; docs/slice_risks_spec.md, RK-1…RK-6).

One row per risk in one project — something that MIGHT happen and needs mitigation. Live, never frozen (design §5
table 32). Probability and impact carry their weight (W1…W5) and the status its behaviour through composite FKs into
code_master, as `issue.status_behaviour` does (I-1), so `exposure_score` is a generated column the request can never
set (law 6, criterion 61) and "materialised exactly when linked to its issue" is a CHECK (law 5). Never merged with
ISSUE: `promote_risk_to_issue` sets `materialised_issue_id` and the risk row stays as the record it was foreseen."""
from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Computed, Date, ForeignKey, ForeignKeyConstraint, Identity, Index, SmallInteger,
    String, Text, UniqueConstraint, text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import AuditMixin, Base

EXPOSURE_SQL = "CAST(substr(probability_weight, 2) AS smallint) * CAST(substr(impact_weight, 2) AS smallint)"


class Risk(AuditMixin, Base):
    __tablename__ = "risk"

    risk_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("project.project_id"), nullable=False)
    risk_number: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    probability_code_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    probability_category: Mapped[str] = mapped_column(String(40), Computed("'RISK_PROBABILITY'", persisted=True))
    probability_weight: Mapped[str] = mapped_column(String(20), nullable=False)
    impact_code_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    impact_category: Mapped[str] = mapped_column(String(40), Computed("'RISK_IMPACT'", persisted=True))
    impact_weight: Mapped[str] = mapped_column(String(20), nullable=False)
    exposure_score: Mapped[int] = mapped_column(SmallInteger, Computed(EXPOSURE_SQL, persisted=True))
    mitigation: Mapped[str | None] = mapped_column(Text)
    owner_org_role_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status_code_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status_category: Mapped[str] = mapped_column(String(40), Computed("'RISK_STATUS'", persisted=True))
    status_behaviour: Mapped[str] = mapped_column(String(20), nullable=False)
    raised_date = mapped_column(Date, nullable=False)                         # review r1 (apple): ageing reads it
    target_date = mapped_column(Date)
    bfc_node_id: Mapped[int | None] = mapped_column(BigInteger)
    solution_id: Mapped[int | None] = mapped_column(BigInteger)
    phase_id: Mapped[int | None] = mapped_column(BigInteger)                 # RK-3: the wave
    materialised_issue_id: Mapped[int | None] = mapped_column(BigInteger)
    # §5.4.7(1) guard (as issue_br): TRUE while live, so a live risk can only point at a live issue
    risk_live: Mapped[bool | None] = mapped_column(Boolean, Computed("CASE WHEN is_active THEN TRUE END", persisted=True))

    probability_code_row = relationship("CodeMaster", viewonly=True, lazy="joined",
                                        primaryjoin="foreign(Risk.probability_code_id) == CodeMaster.code_id")
    impact_code_row = relationship("CodeMaster", viewonly=True, lazy="joined",
                                   primaryjoin="foreign(Risk.impact_code_id) == CodeMaster.code_id")
    status_code_row = relationship("CodeMaster", viewonly=True, lazy="joined",
                                   primaryjoin="foreign(Risk.status_code_id) == CodeMaster.code_id")

    @property
    def probability_code(self) -> str | None:
        return self.probability_code_row.code if self.probability_code_row is not None else None

    @property
    def impact_code(self) -> str | None:
        return self.impact_code_row.code if self.impact_code_row is not None else None

    @property
    def status_code(self) -> str | None:
        return self.status_code_row.code if self.status_code_row is not None else None

    __table_args__ = (
        UniqueConstraint("project_id", "risk_number", name="uq_risk_number"),
        UniqueConstraint("risk_id", "project_id", name="uq_risk_project"),
        ForeignKeyConstraint(["probability_code_id", "probability_category", "probability_weight"],
                             ["code_master.code_id", "code_master.category", "code_master.behaviour_code"],
                             name="fk_risk_probability", onupdate="NO ACTION"),
        ForeignKeyConstraint(["impact_code_id", "impact_category", "impact_weight"],
                             ["code_master.code_id", "code_master.category", "code_master.behaviour_code"],
                             name="fk_risk_impact", onupdate="NO ACTION"),
        ForeignKeyConstraint(["status_code_id", "status_category", "status_behaviour"],
                             ["code_master.code_id", "code_master.category", "code_master.behaviour_code"],
                             name="fk_risk_status", onupdate="NO ACTION"),
        ForeignKeyConstraint(["owner_org_role_id", "project_id"], ["org_role.org_role_id", "org_role.project_id"],
                             name="fk_risk_owner"),
        ForeignKeyConstraint(["bfc_node_id", "project_id"], ["bfc_node.bfc_node_id", "bfc_node.project_id"],
                             name="fk_risk_node"),
        ForeignKeyConstraint(["solution_id", "project_id"], ["solution.solution_id", "solution.project_id"],
                             name="fk_risk_solution"),
        ForeignKeyConstraint(["phase_id", "project_id"], ["phase.phase_id", "phase.project_id"], name="fk_risk_phase"),
        ForeignKeyConstraint(["materialised_issue_id", "project_id"], ["issue.issue_id", "issue.project_id"],
                             name="fk_risk_issue"),
        ForeignKeyConstraint(["materialised_issue_id", "project_id", "risk_live"],
                             ["issue.issue_id", "issue.project_id", "issue.is_active"], name="fk_risk_issue_live"),
        CheckConstraint("probability_weight IN ('W1','W2','W3','W4','W5')", name="ck_risk_probability_weight"),
        CheckConstraint("impact_weight IN ('W1','W2','W3','W4','W5')", name="ck_risk_impact_weight"),
        CheckConstraint("target_date IS NULL OR target_date >= raised_date", name="ck_risk_target_after_raised"),
        CheckConstraint("btrim(title) <> ''", name="ck_risk_title_not_blank"),
        CheckConstraint("(status_behaviour = 'MATERIALISED') = (materialised_issue_id IS NOT NULL)",
                        name="ck_risk_materialised_iff_linked"),
        Index("uq_risk_issue", "materialised_issue_id", unique=True,
              postgresql_where=text("materialised_issue_id IS NOT NULL")),
        Index("ix_risk_open", "project_id", "exposure_score",
              postgresql_where=text("is_active AND status_behaviour = 'OPEN'")),
        Index("ix_risk_probability", "probability_code_id"),
        Index("ix_risk_impact", "impact_code_id"),
        Index("ix_risk_status", "status_code_id"),
        Index("ix_risk_owner", "owner_org_role_id"),
        Index("ix_risk_node", "bfc_node_id"),
        Index("ix_risk_solution", "solution_id"),
        Index("ix_risk_phase", "phase_id"),
    )

    def owning_project_id(self) -> int:
        return self.project_id
