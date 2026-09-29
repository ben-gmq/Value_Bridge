"""Client organisation (§5.3, area 8): ORG_UNIT and ORG_ROLE — frozen into baselines (D-12)."""
from sqlalchemy import (
    BigInteger, CheckConstraint, Computed, ForeignKey, ForeignKeyConstraint, Identity, Index,
    Integer, SmallInteger, String, Text, UniqueConstraint, func, text,
)
from sqlalchemy.orm import Mapped, mapped_column

from models.base import AuditMixin, Base


class OrgUnit(AuditMixin, Base):
    """L1–L3. level_no, seq_no and parent are set by the service, never the request (VB law 6)."""

    __tablename__ = "org_unit"

    org_unit_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("project.project_id"), nullable=False)
    parent_org_unit_id: Mapped[int | None] = mapped_column(BigInteger)
    level_no: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    level_code_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    level_category: Mapped[str] = mapped_column(String(40), Computed("'ORG_UNIT_LEVEL'", persisted=True))
    org_unit_code: Mapped[str] = mapped_column(String(30), nullable=False)
    org_unit_name: Mapped[str] = mapped_column(String(200), nullable=False)
    seq_no: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("org_unit_id", "project_id", name="uq_org_unit_project"),
        ForeignKeyConstraint(["parent_org_unit_id", "project_id"],
                             ["org_unit.org_unit_id", "org_unit.project_id"], name="fk_org_unit_parent"),
        # S1-4: the level code must be an ORG_UNIT_LEVEL code, proven by the database.
        ForeignKeyConstraint(["level_code_id", "level_category"],
                             ["code_master.code_id", "code_master.category"],
                             name="fk_org_unit_level_code", onupdate="NO ACTION"),
        CheckConstraint("level_no BETWEEN 1 AND 3", name="ck_org_unit_level"),
        CheckConstraint("(level_no = 1) = (parent_org_unit_id IS NULL)", name="ck_org_unit_root"),
        # S1-3: negatives exist only mid-reorder (two-phase); at most 99 siblings.
        CheckConstraint("seq_no <> 0 AND seq_no BETWEEN -99 AND 99", name="ck_org_unit_seq"),
        # S1-1: a NULL parent is one shared parent, so L1 units cannot share a position.
        Index("uq_org_unit_sibling_seq", "project_id", "parent_org_unit_id", "seq_no", unique=True,
              postgresql_nulls_not_distinct=True, postgresql_where=text("is_active")),
        # S1-6: a retired unit's code may be reused.
        Index("uq_org_unit_code_live", "project_id", func.lower(func.btrim(org_unit_code)),
              unique=True, postgresql_where=text("is_active")),
        Index("ix_org_unit_project", "project_id"),
        Index("ix_org_unit_parent", "parent_org_unit_id", "project_id"),
        Index("ix_org_unit_level_code", "level_code_id"),
    )

    def owning_project_id(self) -> int:
        return self.project_id


class OrgRole(AuditMixin, Base):
    """A role within one org unit of the same project (S1-7). Never bare `role` (VB law 7)."""

    __tablename__ = "org_role"

    org_role_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("project.project_id"), nullable=False)
    org_unit_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    org_role_code: Mapped[str] = mapped_column(String(30), nullable=False)
    org_role_name: Mapped[str] = mapped_column(String(200), nullable=False)
    responsibility_desc: Mapped[str | None] = mapped_column(Text)
    headcount: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (
        UniqueConstraint("org_role_id", "project_id", name="uq_org_role_project"),
        ForeignKeyConstraint(["org_unit_id", "project_id"],
                             ["org_unit.org_unit_id", "org_unit.project_id"], name="fk_org_role_unit"),
        CheckConstraint("headcount IS NULL OR headcount >= 0", name="ck_org_role_headcount"),
        Index("uq_org_role_code_live", "project_id", func.lower(func.btrim(org_role_code)),
              unique=True, postgresql_where=text("is_active")),
        Index("ix_org_role_project", "project_id"),
        Index("ix_org_role_unit", "org_unit_id", "project_id"),
    )

    def owning_project_id(self) -> int:
        return self.project_id
