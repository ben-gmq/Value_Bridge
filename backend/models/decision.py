"""Decision (§4.11 record_decision / decision_log, §5 DECISION, D-17, A-41; docs/slice_decisions_spec.md, DC-1…DC-5).

One row per recorded decision in one project. Append-only and evidential: no soft delete, no updated_* columns, no
row_version — nothing ever changes it. The database refuses UPDATE and DELETE for every role (trg_decision_immutable →
fn_decision_reject, migration 0084) except the scoped purge of an approved project (fn_purge_allows, 0074), and
vb_app holds no UPDATE grant. A wrong decision is corrected by a NEW row whose supersedes_decision_id points at it;
the partial unique index lets each decision be superseded once, so only the latest in a chain is corrected (DC-2)."""
from datetime import date, datetime

from sqlalchemy import (
    BigInteger, CheckConstraint, Computed, Date, DateTime, ForeignKey, ForeignKeyConstraint, Identity, Index, String,
    Text, UniqueConstraint, func, text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base


class Decision(Base):
    __tablename__ = "decision"

    decision_id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("project.project_id"), nullable=False)
    decision_number: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    decision_text: Mapped[str] = mapped_column(Text, nullable=False)
    alternative_rejected: Mapped[str] = mapped_column(Text, nullable=False)
    analysis_code: Mapped[str | None] = mapped_column(String(40))          # DC-3: one of the project's rules
    dimension_code_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    dimension_category: Mapped[str] = mapped_column(String(40), Computed("'PM_DIMENSION'", persisted=True))
    decided_on: Mapped[date] = mapped_column(Date, nullable=False)            # DC-4: the meeting date
    decided_by_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("app_user.app_user_id"), nullable=False)
    supersedes_decision_id: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("app_user.app_user_id"), nullable=False)

    dimension_code_row = relationship("CodeMaster", viewonly=True, lazy="joined",
                                      primaryjoin="foreign(Decision.dimension_code_id) == CodeMaster.code_id")

    @property
    def dimension_code(self) -> str | None:
        return self.dimension_code_row.code if self.dimension_code_row is not None else None

    __table_args__ = (
        UniqueConstraint("project_id", "decision_number", name="uq_decision_number"),
        UniqueConstraint("decision_id", "project_id", name="uq_decision_project"),
        ForeignKeyConstraint(["dimension_code_id", "dimension_category"], ["code_master.code_id", "code_master.category"],
                             name="fk_decision_dimension"),
        ForeignKeyConstraint(["supersedes_decision_id", "project_id"], ["decision.decision_id", "decision.project_id"],
                             name="fk_decision_supersedes"),
        CheckConstraint("btrim(title) <> ''", name="ck_decision_title_not_blank"),
        CheckConstraint("btrim(decision_text) <> ''", name="ck_decision_text_not_blank"),
        CheckConstraint("btrim(alternative_rejected) <> ''", name="ck_decision_alternative_not_blank"),
        # D1-2: format only — the registry check is the service's (an immutable row could never be re-validated
        # against a narrowed list, and a widened one would need this CHECK widened in step)
        CheckConstraint("analysis_code IS NULL OR analysis_code ~ '^[a-z0-9_]{1,40}$'", name="ck_decision_analysis"),
        CheckConstraint("decided_by_user_id = created_by", name="ck_decision_decided_by_recorder"),   # D1-1
        CheckConstraint("decided_on <= (created_at AT TIME ZONE 'UTC')::date + 1", name="ck_decision_not_future"),
        CheckConstraint("supersedes_decision_id IS NULL OR supersedes_decision_id <> decision_id",
                        name="ck_decision_not_self"),
        Index("uq_decision_superseded_once", "supersedes_decision_id", unique=True,
              postgresql_where=text("supersedes_decision_id IS NOT NULL")),
        Index("ix_decision_log", "project_id", "decided_on", "decision_id"),
        Index("ix_decision_dimension", "dimension_code_id"),
        Index("ix_decision_decided_by", "decided_by_user_id"),
        Index("ix_decision_created_by", "created_by"),
    )

    def owning_project_id(self) -> int:
        return self.project_id
