"""Change requests (§4.11, §5 CHANGE_REQUEST / CR_IMPACT, D-16; docs/slice_change_requests_spec.md, CR-1…CR-3).

CHANGE_REQUEST — one row per proposed change to one agreed baseline of one project. The target is fixed once raised
(point-in-time). The status carries its behaviour (OPEN / PRICED / DEFERRED / APPROVED / REJECTED) through a composite
FK into code_master, so code branches on the behaviour (law 5). The four price columns are the figures the decider
saw: all set or all empty, written only by services/change_request.py (law 6). Who decided and when are read from the
DECISION it points at (the latest), never copied. A cut (`displaces_cr_id`) is used once; a budget record is
all-or-none; both only on an approved increase (CR-3).

CR_IMPACT — one row per (change request × impacted object), ever: a seed (BR / FR marked ADD / MODIFY / REMOVE) or an
object the trace reached, never both. Exactly one of the seven references is set. Neither table is frozen."""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Computed, DateTime, ForeignKey, ForeignKeyConstraint, Identity, Index,
    Integer, Numeric, String, Text, UniqueConstraint, text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import AuditMixin, Base

CR_STATES = ("OPEN", "PRICED", "DEFERRED", "APPROVED", "REJECTED")
_STATES = "('OPEN', 'PRICED', 'DEFERRED', 'APPROVED', 'REJECTED')"
# (column, table, key): the seven things a change can reach (spec §1 analyse)
IMPACT_TARGETS = (("impacted_br_id", "business_requirement", "br_id"),
                  ("impacted_fr_id", "function_requirement", "fr_id"),
                  ("impacted_solution_id", "solution", "solution_id"),
                  ("impacted_application_id", "application", "application_id"),
                  ("impacted_data_entity_id", "data_entity", "data_entity_id"),
                  ("impacted_phase_id", "phase", "phase_id"),
                  ("impacted_benefit_id", "benefit", "benefit_id"))
IMPACT_COLUMNS = tuple(c for c, _, _ in IMPACT_TARGETS)
ROUTES = ("SEED", "BR_FR", "BR_SOLUTION", "FR_SOLUTION", "SOLUTION_APP", "BR_ENTITY", "SOLUTION_WAVE",
          "SOLUTION_BENEFIT")


class ChangeRequest(AuditMixin, Base):
    __tablename__ = "change_request"

    change_request_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("project.project_id"), nullable=False)
    cr_number: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    against_baseline_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    origin_code_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    origin_category: Mapped[str] = mapped_column(String(40), Computed("'CR_ORIGIN'", persisted=True))
    status_code_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status_category: Mapped[str] = mapped_column(String(40), Computed("'CR_STATUS'", persisted=True))
    status_behaviour: Mapped[str] = mapped_column(String(20), nullable=False)
    raised_by_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("app_user.app_user_id"), nullable=False)
    effort_delta_days: Mapped[Decimal | None] = mapped_column(Numeric(9, 2))
    effort_exposed_days: Mapped[Decimal | None] = mapped_column(Numeric(9, 2))
    unrated_fr_count: Mapped[int | None] = mapped_column(Integer)
    priced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_id: Mapped[int | None] = mapped_column(BigInteger)
    displaces_cr_id: Mapped[int | None] = mapped_column(BigInteger)
    budget_increase_days: Mapped[Decimal | None] = mapped_column(Numeric(9, 2))
    budget_reference: Mapped[str | None] = mapped_column(String(200))
    budget_approved_by: Mapped[str | None] = mapped_column(String(200))

    origin_code_row = relationship("CodeMaster", viewonly=True, lazy="joined",
                                   primaryjoin="foreign(ChangeRequest.origin_code_id) == CodeMaster.code_id")
    status_code_row = relationship("CodeMaster", viewonly=True, lazy="joined",
                                   primaryjoin="foreign(ChangeRequest.status_code_id) == CodeMaster.code_id")

    @property
    def origin_code(self) -> str | None:
        return self.origin_code_row.code if self.origin_code_row is not None else None

    @property
    def status_code(self) -> str | None:
        return self.status_code_row.code if self.status_code_row is not None else None

    __table_args__ = (
        UniqueConstraint("project_id", "cr_number", name="uq_cr_number"),
        UniqueConstraint("change_request_id", "project_id", name="uq_cr_project"),
        ForeignKeyConstraint(["against_baseline_id", "project_id"], ["baseline.baseline_id", "baseline.project_id"],
                             name="fk_cr_baseline"),
        ForeignKeyConstraint(["origin_code_id", "origin_category"], ["code_master.code_id", "code_master.category"],
                             name="fk_cr_origin", onupdate="NO ACTION"),
        ForeignKeyConstraint(["status_code_id", "status_category", "status_behaviour"],
                             ["code_master.code_id", "code_master.category", "code_master.behaviour_code"],
                             name="fk_cr_status", onupdate="NO ACTION"),
        ForeignKeyConstraint(["decision_id", "project_id"], ["decision.decision_id", "decision.project_id"],
                             name="fk_cr_decision"),
        ForeignKeyConstraint(["displaces_cr_id", "project_id"],
                             ["change_request.change_request_id", "change_request.project_id"],
                             name="fk_cr_displaces"),
        CheckConstraint("btrim(title) <> ''", name="ck_cr_title_not_blank"),
        CheckConstraint("btrim(rationale) <> ''", name="ck_cr_rationale_not_blank"),
        CheckConstraint(f"status_behaviour IN {_STATES}", name="ck_cr_status_behaviour"),
        CheckConstraint("raised_by_user_id = created_by", name="ck_cr_raised_by_creator"),
        CheckConstraint("num_nulls(effort_delta_days, effort_exposed_days, unrated_fr_count, priced_at) IN (0, 4)",
                        name="ck_cr_price_all_or_none"),
        CheckConstraint("unrated_fr_count IS NULL OR unrated_fr_count >= 0", name="ck_cr_unrated"),
        CheckConstraint("status_behaviour NOT IN ('PRICED', 'APPROVED') OR (priced_at IS NOT NULL "
                        "AND unrated_fr_count = 0)", name="ck_cr_priced_is_rated"),
        CheckConstraint("status_behaviour NOT IN ('APPROVED', 'REJECTED', 'DEFERRED') OR decision_id IS NOT NULL",
                        name="ck_cr_decided_has_decision"),
        CheckConstraint("displaces_cr_id IS NULL OR displaces_cr_id <> change_request_id",
                        name="ck_cr_displaces_not_self"),
        CheckConstraint("displaces_cr_id IS NULL OR (status_behaviour = 'APPROVED' AND effort_delta_days > 0)",
                        name="ck_cr_displaces_on_increase"),
        CheckConstraint("num_nulls(budget_increase_days, budget_reference, budget_approved_by) IN (0, 3)",
                        name="ck_cr_budget_all_or_none"),
        CheckConstraint("budget_increase_days IS NULL OR (budget_increase_days > 0 AND btrim(budget_reference) <> '' "
                        "AND btrim(budget_approved_by) <> '' AND status_behaviour = 'APPROVED' "
                        "AND effort_delta_days > 0)", name="ck_cr_budget_on_increase"),
        Index("ix_cr_status", "project_id", "status_code_id"),
        Index("ix_cr_baseline", "against_baseline_id"),
        Index("ix_cr_decision", "decision_id"),
        Index("ix_cr_origin", "origin_code_id"),
        Index("ix_cr_raised_by", "raised_by_user_id"),
        Index("uq_cr_displaces_once", "displaces_cr_id", unique=True, postgresql_where=text("displaces_cr_id IS NOT NULL")),
    )

    def owning_project_id(self) -> int:
        return self.project_id


class CrImpact(AuditMixin, Base):
    __tablename__ = "cr_impact"

    cr_impact_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("project.project_id"), nullable=False)
    change_request_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    impacted_br_id: Mapped[int | None] = mapped_column(BigInteger)
    impacted_fr_id: Mapped[int | None] = mapped_column(BigInteger)
    impacted_solution_id: Mapped[int | None] = mapped_column(BigInteger)
    impacted_application_id: Mapped[int | None] = mapped_column(BigInteger)
    impacted_data_entity_id: Mapped[int | None] = mapped_column(BigInteger)
    impacted_phase_id: Mapped[int | None] = mapped_column(BigInteger)
    impacted_benefit_id: Mapped[int | None] = mapped_column(BigInteger)
    is_seed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    impact_type_code_id: Mapped[int | None] = mapped_column(BigInteger)
    impact_type_category: Mapped[str] = mapped_column(String(40), Computed("'CR_IMPACT_TYPE'", persisted=True))
    reached_via: Mapped[str] = mapped_column(String(20), nullable=False)
    effort_delta_days: Mapped[Decimal | None] = mapped_column(Numeric(9, 2))
    agreed_effort_days: Mapped[Decimal | None] = mapped_column(Numeric(9, 2))
    value_unit: Mapped[str | None] = mapped_column(String(40))
    value_at_stake: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    value_change: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))

    impact_type_code_row = relationship("CodeMaster", viewonly=True, lazy="joined",
                                        primaryjoin="foreign(CrImpact.impact_type_code_id) == CodeMaster.code_id")

    @property
    def impact_type_code(self) -> str | None:
        return self.impact_type_code_row.code if self.impact_type_code_row is not None else None

    __table_args__ = (
        ForeignKeyConstraint(["change_request_id", "project_id"],
                             ["change_request.change_request_id", "change_request.project_id"],
                             name="fk_cri_change_request"),
        *[ForeignKeyConstraint([c, "project_id"], [f"{t}.{k}", f"{t}.project_id"], name=f"fk_cri_{c[9:-3]}")
          for c, t, k in IMPACT_TARGETS],
        ForeignKeyConstraint(["impact_type_code_id", "impact_type_category"],
                             ["code_master.code_id", "code_master.category"], name="fk_cri_impact_type",
                             onupdate="NO ACTION"),
        UniqueConstraint("change_request_id", *IMPACT_COLUMNS, name="uq_cri_grain", postgresql_nulls_not_distinct=True),
        CheckConstraint(f"num_nonnulls({', '.join(IMPACT_COLUMNS)}) = 1", name="ck_cri_one_object"),
        CheckConstraint("is_seed = (impact_type_code_id IS NOT NULL)", name="ck_cri_seed_has_type"),
        CheckConstraint("NOT is_seed OR num_nonnulls(impacted_br_id, impacted_fr_id) = 1",
                        name="ck_cri_seed_is_br_or_fr"),
        CheckConstraint("is_seed = (reached_via = 'SEED')", name="ck_cri_seed_route"),
        CheckConstraint(f"reached_via IN ({', '.join(repr(r) for r in ROUTES)})", name="ck_cri_route"),
        CheckConstraint("effort_delta_days IS NULL OR (is_seed AND impacted_fr_id IS NOT NULL)",
                        name="ck_cri_delta_on_fr_seed"),
        CheckConstraint("agreed_effort_days IS NULL OR impacted_fr_id IS NOT NULL", name="ck_cri_agreed_on_fr"),
        CheckConstraint("(value_unit IS NULL AND value_at_stake IS NULL AND value_change IS NULL) "
                        "OR impacted_benefit_id IS NOT NULL", name="ck_cri_value_on_benefit"),
        *[Index(f"ix_cri_{c[9:-3]}", c) for c in IMPACT_COLUMNS],
        Index("ix_cri_impact_type", "impact_type_code_id"),
    )

    def owning_project_id(self) -> int:
        return self.project_id
