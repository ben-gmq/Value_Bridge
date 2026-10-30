"""Control rules (D-19; design §5.3 CONTROL_RULE, §7.13; docs/slice_control_a_spec.md; CT-1…CT-4).

One row per (project × analysis), or one FTC house default per analysis when project_id is NULL. A project's rules are
COPIED from the house tier, never referenced: what FTC and the client agreed at mobilisation does not move when the house
standard does. Not frozen (§5.10 row 40)."""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Identity, Index, Numeric, String,
    Text, func, text,
)
from sqlalchemy.orm import Mapped, mapped_column

from models.base import AuditMixin, Base

# §7.13 ANALYSIS_REGISTRY — a rule naming any other analysis is refused (also ck_ctl_analysis, 0081).
REGISTRY = ("priced_diff", "requirement_volatility", "coverage", "solution_matrix", "application_gap",
            "interface_load", "org_impact_heatmap", "stakeholder_engagement", "value_ranking", "benefit_gap",
            "risk_register", "issue_dashboard", "data_migration_map", "master_data_candidates",
            "process_change_intensity", "phase_plan", "consistency_check")
COMPARISONS = ("GT", "LT", "PCT_GT")


class ControlRule(AuditMixin, Base):
    __tablename__ = "control_rule"

    control_rule_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    project_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("project.project_id"))
    analysis_code: Mapped[str] = mapped_column(String(40), nullable=False)
    comparison: Mapped[str] = mapped_column(String(10), nullable=False)
    threshold_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    escalate_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    owner_org_role_id: Mapped[int | None] = mapped_column(BigInteger)
    prescribed_action: Mapped[str | None] = mapped_column(Text)
    escalation_path: Mapped[str | None] = mapped_column(Text)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    is_house_default: Mapped[bool] = mapped_column(Boolean, nullable=False)
    change_rationale: Mapped[str | None] = mapped_column(Text)
    agreed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    # A house row is seeded by the CLI and has no author (deviation 7j, as code_master's library rows).
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("app_user.app_user_id"))

    __table_args__ = (
        ForeignKeyConstraint(["owner_org_role_id", "project_id"], ["org_role.org_role_id", "org_role.project_id"],
                             name="fk_ctl_owner_role"),
        CheckConstraint("analysis_code IN (" + ", ".join(f"'{c}'" for c in REGISTRY) + ")", name="ck_ctl_analysis"),
        CheckConstraint("comparison IN ('GT', 'LT', 'PCT_GT')", name="ck_ctl_comparison"),
        CheckConstraint("is_house_default = (project_id IS NULL)", name="ck_ctl_house_tier"),
        CheckConstraint("project_id IS NOT NULL OR owner_org_role_id IS NULL", name="ck_ctl_house_no_owner"),
        CheckConstraint("project_id IS NULL OR created_by IS NOT NULL", name="ck_ctl_project_author"),
        CheckConstraint("row_version = 1 OR change_rationale IS NOT NULL", name="ck_ctl_rationale"),
        Index("uq_ctl_house", "analysis_code", unique=True, postgresql_where=text("project_id IS NULL")),
        Index("uq_ctl_project", "project_id", "analysis_code", unique=True,
              postgresql_where=text("project_id IS NOT NULL")),
        Index("ix_ctl_owner", "owner_org_role_id", "project_id"),
    )
