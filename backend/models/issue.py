"""Issue management (§5.3 area 5, §4.5; docs/slice14_issue_spec.md, slice14_issue_schema.md; I-1…I-16).

STAKEHOLDER: one named client-side person in one project, no login (D-4). Not frozen — a person is not scope; a
baseline shows the raiser's current name (I-15)."""
from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, ForeignKey, ForeignKeyConstraint, Identity, Index, String, UniqueConstraint,
    func, text,
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
