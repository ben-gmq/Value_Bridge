"""Identity (§5.3 area 7): APP_USER, USER_ACCESS_GRANT, AUDIT_EVENT."""
from datetime import datetime

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Computed, DateTime, ForeignKey,
    ForeignKeyConstraint, Identity, Index, Integer, String, func, text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import AuditMixin, Base, TimestampMixin


class AppUser(TimestampMixin, Base):
    """One row per FTC staff member who can log in (D-11). No per-user role column:
    the global tier is `is_platform_admin`, the project tier is the one active grant (D-9)."""

    __tablename__ = "app_user"

    app_user_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Nullable only because the first-run admin is created by nobody (scaffold §1).
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("app_user.app_user_id"))
    updated_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("app_user.app_user_id"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("app_user.app_user_id"))
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")

    __mapper_args__ = {"version_id_col": row_version}
    __table_args__ = (Index("uq_app_user_email", func.lower(email), unique=True),)


class UserAccessGrant(AuditMixin, Base):
    """One grant of one project role over ONE scope — a project or a program (D-32).
    At most one live grant per user; program-derived access is computed, never stored."""

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
