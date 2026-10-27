"""Identity (§5.3 area 7): APP_USER, USER_ACCESS_GRANT, AUDIT_EVENT."""
from datetime import datetime

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Computed, DateTime, ForeignKey,
    ForeignKeyConstraint, Identity, Index, Integer, String, Text, func, text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import UserDefinedType

from models.base import AuditMixin, Base, TimestampMixin


class AppUser(TimestampMixin, Base):
    """One row per FTC staff member who can log in (D-11). Admin is `is_platform_admin`; every
    other user is a USER (edit) or VIEWER (read only) on every visible project (D-40)."""

    __tablename__ = "app_user"

    app_user_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    user_kind: Mapped[str] = mapped_column(String(20), nullable=False, server_default="VIEWER")   # D-40
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Nullable only because the first-run admin is created by nobody (scaffold §1).
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("app_user.app_user_id"))
    updated_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("app_user.app_user_id"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("app_user.app_user_id"))
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")

    __mapper_args__ = {"version_id_col": row_version}
    __table_args__ = (Index("uq_app_user_email", func.lower(email), unique=True),
                      CheckConstraint("user_kind IN ('USER', 'VIEWER')", name="ck_app_user_kind"))


class Xid8(UserDefinedType):
    """PostgreSQL's 64-bit transaction id (pg_current_xact_id()), for platform_admin_grant.approved_xact."""
    cache_ok = True

    def get_col_spec(self, **kw):
        return "xid8"


class PlatformAdminGrant(Base):
    """One row per way one user was made, or asked to be made, a platform admin (slice17 schema rev 3, migration 0076):
    a REQUEST one admin makes and a different, independent one decides; the BOOTSTRAP of the first two admins; or an
    owner-run LEGACY grant. Kept forever. The database guard sets every time and refuses every out-of-order step; the
    named actor pairs replace AuditMixin, as on project_purge. `approved_xact` (xid8) is set by the guard alone; the app
    never writes it (no grant), it is mapped only so the model describes the whole table."""

    __tablename__ = "platform_admin_grant"
    ORIGINS = ("REQUEST", "BOOTSTRAP", "LEGACY")
    __table_args__ = (
        Index("uq_pag_open", "target_user_id", unique=True,
              postgresql_where=text("approved_at IS NULL AND rejected_at IS NULL AND cancelled_at IS NULL")),
        Index("ix_pag_target_granted", "target_user_id", text("approved_at DESC"),
              postgresql_where=text("approved_at IS NOT NULL")),
    )

    platform_admin_grant_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    grant_origin: Mapped[str] = mapped_column(String(10), nullable=False)
    target_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("app_user.app_user_id"), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    operator_name: Mapped[str | None] = mapped_column(String(200))
    source_audit_event_id: Mapped[int | None] = mapped_column(BigInteger)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    requested_by_user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("app_user.app_user_id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by_user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("app_user.app_user_id"))
    approved_xact = mapped_column(Xid8)
    # 0079: approved while the installation's setting was one approver; set by the guard alone, never by the app
    approved_single_owner: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_by_user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("app_user.app_user_id"))
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by_user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("app_user.app_user_id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("app_user.app_user_id"))
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")


class UserAccessGrant(AuditMixin, Base):
    """RETIRED by D-40 (migration 0038): history only, SELECT-only for the app role. It held one
    grant of one project role over one project or program (D-32); access is now user_kind plus
    project_member on restricted projects."""

    __tablename__ = "user_access_grant"

    user_access_grant_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    app_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("app_user.app_user_id"), nullable=False
    )
    project_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("project.project_id"))
    program_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("program.program_id"))
    project_role_code_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("code_master.code_id"), nullable=False
    )
    # Generated guard: TRUE while live, NULL when revoked — so a revoked grant never blocks
    # retiring its project or program (MATCH SIMPLE skips NULLs).
    scope_is_active: Mapped[bool | None] = mapped_column(
        Boolean, Computed("CASE WHEN is_active THEN TRUE END", persisted=True)
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    granted_by_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("app_user.app_user_id"), nullable=False
    )

    user = relationship("AppUser", foreign_keys=[app_user_id])
    role_code = relationship("CodeMaster", foreign_keys=[project_role_code_id])

    __table_args__ = (
        CheckConstraint("num_nonnulls(project_id, program_id) = 1", name="ck_grant_one_scope"),
        Index("uq_grant_one_live_per_user", "app_user_id", unique=True,
              postgresql_where=text("is_active")),
        ForeignKeyConstraint(["project_id", "scope_is_active"],
                             ["project.project_id", "project.is_active"],
                             name="fk_grant_live_project", onupdate="NO ACTION"),
        ForeignKeyConstraint(["program_id", "scope_is_active"],
                             ["program.program_id", "program.is_active"],
                             name="fk_grant_live_program", onupdate="NO ACTION"),
        Index("ix_grant_program_live", "program_id", postgresql_where=text("is_active")),
        Index("ix_grant_project_live", "project_id", postgresql_where=text("is_active")),
    )

    def owning_project_id(self) -> int | None:
        """object_guard contract (§7.8). A program grant resolves to no project → admin only."""
        return self.project_id


class ProjectMember(AuditMixin, Base):
    """A named member of a project, with a level (OR-6). Only matters while the project is
    restricted. Each membership period is its own row; re-adding inserts, never restores."""

    __tablename__ = "project_member"

    project_member_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("project.project_id"), nullable=False)
    project_is_active: Mapped[bool | None] = mapped_column(
        Boolean, Computed("CASE WHEN is_active THEN TRUE END", persisted=True))
    app_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("app_user.app_user_id"), nullable=False)
    access_level: Mapped[str] = mapped_column(String(5), nullable=False)
    member_note: Mapped[str | None] = mapped_column(Text)

    user = relationship("AppUser", foreign_keys=[app_user_id])

    __table_args__ = (
        ForeignKeyConstraint(["project_id", "project_is_active"], ["project.project_id", "project.is_active"],
                             name="fk_pm_live_project", onupdate="NO ACTION"),
        CheckConstraint("access_level IN ('ADMIN', 'EDIT', 'VIEW')", name="ck_pm_level"),
        CheckConstraint("member_note IS NULL OR btrim(member_note) <> ''", name="ck_pm_note_not_blank"),
        Index("uq_pm_live", "project_id", "app_user_id", unique=True, postgresql_where=text("is_active")),
        Index("ix_pm_user_live", "app_user_id", postgresql_where=text("is_active")),
    )

    def owning_project_id(self) -> int:
        return self.project_id


class ProgramMember(AuditMixin, Base):
    """A named member of a program, with a level (D-71): that level on every live project of the program, restricted
    ones included — derived per request by services/access, never copied. One row per membership period; re-adding
    inserts, never restores. A live member blocks retiring the program (fk_prgm_live_program; law 1)."""

    __tablename__ = "program_member"

    program_member_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    program_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("program.program_id"), nullable=False)
    program_is_active: Mapped[bool | None] = mapped_column(
        Boolean, Computed("CASE WHEN is_active THEN TRUE END", persisted=True))
    app_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("app_user.app_user_id"), nullable=False)
    access_level: Mapped[str] = mapped_column(String(5), nullable=False)
    member_note: Mapped[str | None] = mapped_column(Text)

    user = relationship("AppUser", foreign_keys=[app_user_id])

    __table_args__ = (
        ForeignKeyConstraint(["program_id", "program_is_active"], ["program.program_id", "program.is_active"],
                             name="fk_prgm_live_program", onupdate="NO ACTION"),
        CheckConstraint("access_level IN ('ADMIN', 'EDIT', 'VIEW')", name="ck_prgm_level"),
        CheckConstraint("member_note IS NULL OR btrim(member_note) <> ''", name="ck_prgm_note_not_blank"),
        Index("uq_prgm_live", "program_id", "app_user_id", unique=True, postgresql_where=text("is_active")),
        Index("ix_prgm_user_live", "app_user_id", postgresql_where=text("is_active")),
    )

    def owning_project_id(self) -> None:
        return None                      # program-scoped: routers use the program member guard, never object_guard

    def owning_program_id(self) -> int:
        return self.program_id


class AuditEvent(Base):
    """Append-only forensic log. `event_type` is a plain varchar on purpose (§5.3)."""

    __tablename__ = "audit_event"

    audit_event_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    app_user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("app_user.app_user_id"))
    project_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("project.project_id"))
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    target_table: Mapped[str | None] = mapped_column(String(60))
    target_id: Mapped[int | None] = mapped_column(BigInteger)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    source_ip: Mapped[str | None] = mapped_column(INET)
    detail: Mapped[dict | None] = mapped_column(JSONB)

    __table_args__ = (Index("ix_audit_event_project", "project_id", "occurred_at"),)
