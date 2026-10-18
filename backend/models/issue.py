"""Issue management (§5.3 area 5, §4.5; docs/slice14_issue_spec.md, slice14_issue_schema.md; I-1…I-16).

STAKEHOLDER: one named client-side person in one project, no login (D-4). Not frozen — a person is not scope; a
baseline shows the raiser's current name (I-15).
ISSUE: one raised issue, anchored to the project, not to a BR (§5.3). Frozen from hash spec 5 (I-5)."""
from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Computed, Date, DateTime, ForeignKey, ForeignKeyConstraint, Identity, Index,
    String, Text, UniqueConstraint, func, text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import AuditMixin, Base


class Stakeholder(AuditMixin, Base):
    """org_unit_id is optional (I-2): BPO staff are often outside the client's chart. Two people may share a name in
    different units (I-16), so the live key is (project, unit, name); a NULL unit is one shared unit."""

    __tablename__ = "stakeholder"

    stakeholder_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("project.project_id"), nullable=False)
    org_unit_id: Mapped[int | None] = mapped_column(BigInteger)
    stakeholder_name: Mapped[str] = mapped_column(String(200), nullable=False)
    job_title: Mapped[str | None] = mapped_column(String(200))
    is_bpo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    org_unit_row = relationship("OrgUnit", viewonly=True,
                                primaryjoin="foreign(Stakeholder.org_unit_id) == OrgUnit.org_unit_id")

    __table_args__ = (
        UniqueConstraint("stakeholder_id", "project_id", name="uq_stk_project"),
        ForeignKeyConstraint(["org_unit_id", "project_id"], ["org_unit.org_unit_id", "org_unit.project_id"],
                             name="fk_stk_org_unit"),
        CheckConstraint("btrim(stakeholder_name) <> ''", name="ck_stk_name_not_blank"),
        Index("uq_stk_name_live", "project_id", func.coalesce(org_unit_id, 0),
              func.lower(func.btrim(stakeholder_name)), unique=True, postgresql_where=text("is_active")),
        Index("ix_stk_org_unit", "org_unit_id", "project_id"),
    )

    def owning_project_id(self) -> int:
        return self.project_id


class Issue(AuditMixin, Base):
    """status_behaviour is a verified copy of the status's open / closed behaviour (I-1, §15 N1), carried through the
    composite FK as fr_type_behaviour is (D-27), so the database holds "resolved exactly when closed" without reading
    a code (law 5). The raiser is a stakeholder; the recorder is the consultant from the JWT (D-4, D8)."""

    __tablename__ = "issue"

    issue_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("project.project_id"), nullable=False)
    issue_number: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    severity_code_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    severity_category: Mapped[str] = mapped_column(String(40), Computed("'ISSUE_SEVERITY'", persisted=True))
    issue_type_code_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    issue_type_category: Mapped[str] = mapped_column(String(40), Computed("'ISSUE_TYPE'", persisted=True))
    status_code_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status_category: Mapped[str] = mapped_column(String(40), Computed("'ISSUE_STATUS'", persisted=True))
    status_behaviour: Mapped[str] = mapped_column(String(20), nullable=False)
    raised_by_stakeholder_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    recorded_by_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("app_user.app_user_id"), nullable=False)
    raised_date = mapped_column(Date, nullable=False)
    target_date = mapped_column(Date)
    resolution: Mapped[str | None] = mapped_column(Text)
    resolved_at = mapped_column(DateTime(timezone=True))
    resolved_by_user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("app_user.app_user_id"))

    severity_code_row = relationship("CodeMaster", viewonly=True, lazy="joined",
                                     primaryjoin="foreign(Issue.severity_code_id) == CodeMaster.code_id")
    issue_type_code_row = relationship("CodeMaster", viewonly=True, lazy="joined",
                                       primaryjoin="foreign(Issue.issue_type_code_id) == CodeMaster.code_id")
    status_code_row = relationship("CodeMaster", viewonly=True, lazy="joined",
                                   primaryjoin="foreign(Issue.status_code_id) == CodeMaster.code_id")

    @property
    def severity_code(self) -> str | None:
        return self.severity_code_row.code if self.severity_code_row is not None else None

    @property
    def issue_type_code(self) -> str | None:
        return self.issue_type_code_row.code if self.issue_type_code_row is not None else None

    @property
    def status_code(self) -> str | None:
        return self.status_code_row.code if self.status_code_row is not None else None

    __table_args__ = (
        UniqueConstraint("project_id", "issue_number", name="uq_issue_number"),
        UniqueConstraint("issue_id", "project_id", name="uq_issue_project"),
        UniqueConstraint("issue_id", "project_id", "is_active", name="uq_issue_live_target"),
        ForeignKeyConstraint(["severity_code_id", "severity_category"], ["code_master.code_id", "code_master.category"],
                             name="fk_issue_severity", onupdate="NO ACTION"),
        ForeignKeyConstraint(["issue_type_code_id", "issue_type_category"],
                             ["code_master.code_id", "code_master.category"], name="fk_issue_type",
                             onupdate="NO ACTION"),
        ForeignKeyConstraint(["status_code_id", "status_category", "status_behaviour"],
                             ["code_master.code_id", "code_master.category", "code_master.behaviour_code"],
                             name="fk_issue_status", onupdate="NO ACTION"),
        ForeignKeyConstraint(["raised_by_stakeholder_id", "project_id"],
                             ["stakeholder.stakeholder_id", "stakeholder.project_id"], name="fk_issue_raiser"),
        CheckConstraint("btrim(title) <> ''", name="ck_issue_title_not_blank"),
        CheckConstraint("target_date IS NULL OR target_date >= raised_date", name="ck_issue_target_after_raised"),
        CheckConstraint("(resolved_at IS NULL) = (resolved_by_user_id IS NULL)", name="ck_issue_resolved_pair"),
        # §15 N1: resolved exactly when the status is closed; a closed issue carries a resolution (§4.5, I-1)
        CheckConstraint("(status_behaviour = 'CLOSED') = (resolved_at IS NOT NULL)",
                        name="ck_issue_resolved_iff_closed"),
        CheckConstraint("resolved_at IS NULL OR btrim(coalesce(resolution, '')) <> ''",
                        name="ck_issue_resolution_text"),
        Index("ix_issue_raiser", "raised_by_stakeholder_id"),
        Index("ix_issue_open", "project_id", "status_behaviour", postgresql_where=text("is_active")),
        Index("ix_issue_severity", "severity_code_id"),
        Index("ix_issue_type", "issue_type_code_id"),
        Index("ix_issue_status", "status_code_id"),
    )

    def owning_project_id(self) -> int:
        return self.project_id


class IssueBr(AuditMixin, Base):
    """Issue × BR (§5.4 "ISSUE ↔ BR is many-to-many"). S1-5 / I-8: surrogate PK, full UK on the pair, so a re-link
    restores the same row (S1-7). The live guard makes "a live link under a retired issue" impossible in the database;
    BR liveness is the service's (as br_solution). Retires and restores with its BR's step (step_retire.OWNED_BY_BR,
    I-3)."""

    __tablename__ = "issue_br"

    issue_br_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("project.project_id"), nullable=False)
    issue_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    br_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    issue_is_active: Mapped[bool | None] = mapped_column(
        Boolean, Computed("CASE WHEN is_active THEN TRUE END", persisted=True))

    # Read-only: the two-ended label "ISS-0001 ↔ BR-0042" (DR1-P1).
    issue_row = relationship("Issue", viewonly=True, primaryjoin="foreign(IssueBr.issue_id) == Issue.issue_id")
    br_row = relationship("BusinessRequirement", viewonly=True,
                          primaryjoin="foreign(IssueBr.br_id) == BusinessRequirement.br_id")

    __table_args__ = (
        UniqueConstraint("issue_id", "br_id", name="uq_ibr_grain"),
        ForeignKeyConstraint(["issue_id", "project_id"], ["issue.issue_id", "issue.project_id"], name="fk_ibr_issue"),
        ForeignKeyConstraint(["br_id", "project_id"], ["business_requirement.br_id", "business_requirement.project_id"],
                             name="fk_ibr_br"),
        ForeignKeyConstraint(["issue_id", "project_id", "issue_is_active"],
                             ["issue.issue_id", "issue.project_id", "issue.is_active"], name="fk_ibr_issue_live",
                             onupdate="NO ACTION"),
        Index("ix_ibr_br", "br_id"),
        Index("ix_ibr_project", "project_id"),
    )

    def owning_project_id(self) -> int:
        return self.project_id
