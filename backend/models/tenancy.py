"""Tenancy (§5.3): CLIENT, PROGRAM (D-32), PROJECT — the data wall."""
from datetime import date

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Computed, Date, ForeignKey, ForeignKeyConstraint,
    Identity, Index, String, Text, UniqueConstraint, func, text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import AuditMixin, Base


class Client(AuditMixin, Base):
    __tablename__ = "client"

    client_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    client_code: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    client_name: Mapped[str] = mapped_column(String(200), nullable=False)
    industry: Mapped[str | None] = mapped_column(String(100))


class Program(AuditMixin, Base):
    """A roll-up and access scope, never a data layer (D-32)."""

    __tablename__ = "program"

    program_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    client_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("client.client_id"), nullable=False)
    program_code: Mapped[str] = mapped_column(String(30), nullable=False)
    program_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    client = relationship("Client")

    __table_args__ = (
        UniqueConstraint("client_id", "program_code", name="uq_program_code"),
        Index("uq_program_name_live", "client_id", func.lower(program_name), unique=True,
              postgresql_where=text("is_active")),
        # Composite-FK targets: prove "same client" and "live program" declaratively.
        UniqueConstraint("program_id", "client_id", name="uq_program_client"),
        UniqueConstraint("program_id", "client_id", "is_active", name="uq_program_client_live"),
        UniqueConstraint("program_id", "is_active", name="uq_program_live"),
    )


class Project(AuditMixin, Base):
    __tablename__ = "project"

    project_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    client_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("client.client_id"), nullable=False)
    program_id: Mapped[int | None] = mapped_column(BigInteger)
    program_is_active: Mapped[bool | None] = mapped_column(
        Boolean, Computed("CASE WHEN is_active THEN TRUE END", persisted=True)
    )
    project_code: Mapped[str] = mapped_column(String(30), nullable=False)
    project_name: Mapped[str] = mapped_column(String(200), nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    status_code_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("code_master.code_id", use_alter=True, name="fk_project_status"),
        nullable=False,
    )
    # D-39: KEYS_ONLY or FULL. Read only through services.components.depth().
    data_model_depth: Mapped[str] = mapped_column(String(10), nullable=False, server_default="FULL")
    # OR-6: visible only to admins and live project_member rows. Read per request.
    is_restricted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    client = relationship("Client")
    program = relationship("Program", viewonly=True,
                           primaryjoin="foreign(Project.program_id) == Program.program_id")

    __table_args__ = (
        UniqueConstraint("client_id", "project_code", name="uq_project_code"),
        UniqueConstraint("project_id", "is_active", name="uq_project_live"),
        # A project joins only a program of its own client ...
        ForeignKeyConstraint(["program_id", "client_id"],
                             ["program.program_id", "program.client_id"],
                             name="fk_project_program_client"),
        # ... and, while active, only a live one (Q4, by construction).
        ForeignKeyConstraint(["program_id", "client_id", "program_is_active"],
                             ["program.program_id", "program.client_id", "program.is_active"],
                             name="fk_project_program_live", onupdate="NO ACTION"),
        CheckConstraint("end_date IS NULL OR start_date IS NULL OR end_date >= start_date",
                        name="ck_project_dates"),
        CheckConstraint("data_model_depth IN ('KEYS_ONLY', 'FULL')", name="ck_project_depth"),
    )

    def owning_project_id(self) -> int:
        return self.project_id


class ProjectComponent(AuditMixin, Base):
    """A component this project uses (D-37). Live row = on, retired row = off; switching back on
    restores the same row. Changed only through services.components.set_components (audited)."""

    __tablename__ = "project_component"

    project_component_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("project.project_id"), nullable=False)
    component_code_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    component_category: Mapped[str] = mapped_column(
        String(40), Computed("'PROJECT_COMPONENT'", persisted=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("project_id", "component_code_id", name="uq_project_component"),
        ForeignKeyConstraint(["component_code_id", "component_category"],
                             ["code_master.code_id", "code_master.category"],
                             name="fk_pc_component", onupdate="NO ACTION"),
        Index("ix_pc_component", "component_code_id"),
    )

    def owning_project_id(self) -> int:
        return self.project_id


class ProjectTemplateComponent(AuditMixin, Base):
    """One component of one project template (OR-3). Global and seeded; copied once at
    create_project, never linked afterwards."""

    __tablename__ = "project_template_component"

    project_template_component_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    template_code_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    template_category: Mapped[str] = mapped_column(
        String(40), Computed("'PROJECT_TEMPLATE'", persisted=True), nullable=False)
    component_code_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    component_category: Mapped[str] = mapped_column(
        String(40), Computed("'PROJECT_COMPONENT'", persisted=True), nullable=False)
    # Seeded rows have no author, as on code_master (PLAYBOOK_DEVIATIONS 7d).
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("app_user.app_user_id"))

    __table_args__ = (
        UniqueConstraint("template_code_id", "component_code_id", name="uq_ptc_grain"),
        ForeignKeyConstraint(["template_code_id", "template_category"],
                             ["code_master.code_id", "code_master.category"],
                             name="fk_ptc_template", onupdate="NO ACTION"),
        ForeignKeyConstraint(["component_code_id", "component_category"],
                             ["code_master.code_id", "code_master.category"],
                             name="fk_ptc_component", onupdate="NO ACTION"),
        Index("ix_ptc_component", "component_code_id"),
    )
