"""Tenancy (§5.3): CLIENT, PROGRAM (D-32), PROJECT — the data wall."""
from datetime import date, datetime

from sqlalchemy import (
    ARRAY, CHAR, BigInteger, Boolean, CheckConstraint, Computed, Date, DateTime, ForeignKey, ForeignKeyConstraint,
    Identity, Index, Integer, Numeric, SmallInteger, String, Text, UniqueConstraint, func, text,
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
    status_code_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # slice 16 (Q-89 b, 0071): the status's open / closed meaning, carried by fk_project_status, so the database holds
    # closed_on to it without naming a code (law 5). Both set by services.project only.
    status_category: Mapped[str] = mapped_column(String(40), Computed("'PROJECT_STATUS'", persisted=True))
    status_behaviour: Mapped[str] = mapped_column(String(20), nullable=False)
    # AR-8 (Q-87): the day (ICT) the status became a closed one — the start of the two-year archive clock.
    closed_on: Mapped[date | None] = mapped_column(Date)
    # D-39: KEYS_ONLY or FULL. Read only through services.components.depth().
    data_model_depth: Mapped[str] = mapped_column(String(10), nullable=False, server_default="FULL")
    # OR-6: visible only to admins and live project_member rows. Read per request.
    is_restricted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    # D-67 (slice 13c): the FTE basis — hours in one FTE = working days × hours per day (240 × 8 = 1,920).
    working_days_per_year: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="240")
    hours_per_working_day = mapped_column(Numeric(4, 2), nullable=False, server_default="8.00")

    client = relationship("Client")
    program = relationship("Program", viewonly=True,
                           primaryjoin="foreign(Project.program_id) == Program.program_id")

    __table_args__ = (
        UniqueConstraint("client_id", "project_code", name="uq_project_code"),
        CheckConstraint("working_days_per_year BETWEEN 1 AND 366", name="ck_project_fte_days"),
        CheckConstraint("hours_per_working_day BETWEEN 0.25 AND 24", name="ck_project_fte_hours"),
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
        ForeignKeyConstraint(["status_code_id", "status_category", "status_behaviour"],
                             ["code_master.code_id", "code_master.category", "code_master.behaviour_code"],
                             name="fk_project_status", onupdate="NO ACTION", use_alter=True),
        CheckConstraint("(status_behaviour = 'CLOSED') = (closed_on IS NOT NULL)", name="ck_project_closed_on"),
        Index("ix_project_closed_on", "closed_on", postgresql_where=text("closed_on IS NOT NULL")),
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


class ProjectDfdRule(AuditMixin, Base):
    """One DFD element a chart of a project requires before its scope can be frozen (D-70; slice13_schema
    §2.2, S13-1). Live row = required, retired row = not required; re-adding restores the same row (S1-7).
    The element vocabulary is closed and code-defined (each code is a predicate in services/process_flow), so it
    is CHECK-listed, not a code_master FK [Q-17]. Changed only through services.dfd_rule.set (audited). Not
    shadowed: the rule a baseline passed is copied onto its header (baseline.dfd_rule_to_be / _as_is)."""

    __tablename__ = "project_dfd_rule"

    project_dfd_rule_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("project.project_id"), nullable=False)
    bfc_set_code: Mapped[str] = mapped_column(String(10), nullable=False)
    element_code: Mapped[str] = mapped_column(String(12), nullable=False)

    __table_args__ = (
        UniqueConstraint("project_id", "bfc_set_code", "element_code", name="uq_project_dfd_rule"),
        CheckConstraint("bfc_set_code IN ('TO_BE', 'AS_IS')", name="ck_pdr_set"),
        CheckConstraint("element_code IN ('STARTED', 'DATA_IN', 'DATA_OUT', 'EXTERNAL', 'ORDER')",
                        name="ck_pdr_element"),
        CheckConstraint("element_code <> 'STARTED' OR is_active", name="ck_pdr_started_locked"),
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


class ProjectPurge(Base):
    """One request to take one project out of VB (ARCHIVE, DELETE) or to delete its archive (DELETE_ARCHIVE)
    (slice16 schema §3.2, §12.5; 0072). No FK to project: the record outlives it, and it is kept forever. State is
    derived from the dates (Q-67); trg_project_purge_guard enforces four eyes, the 24 hours and the order of steps,
    for every role. The app requests, approves, cancels and records the weekly check; only the owner-run job records
    the project file, key destruction and execution."""
    __tablename__ = "project_purge"
    KINDS = ("ARCHIVE", "DELETE", "DELETE_ARCHIVE")

    project_purge_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    purge_kind: Mapped[str] = mapped_column(String(15), nullable=False)
    project_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    client_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("client.client_id"), nullable=False)
    project_code: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    archive_purge_id: Mapped[int | None] = mapped_column(BigInteger)
    archive_purge_kind: Mapped[str | None] = mapped_column(
        String(15), Computed("CASE WHEN archive_purge_id IS NOT NULL THEN 'ARCHIVE' END", persisted=True))
    repurge_of_purge_id: Mapped[int | None] = mapped_column(BigInteger)
    archive_object_name: Mapped[str | None] = mapped_column(String(400))
    archive_sha256: Mapped[str | None] = mapped_column(CHAR(64))
    archive_byte_size: Mapped[int | None] = mapped_column(BigInteger)
    archive_key_ref: Mapped[str | None] = mapped_column(String(400))
    archive_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archive_check_error: Mapped[str | None] = mapped_column(String(2000))
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    requested_by_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("app_user.app_user_id"), nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by_user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("app_user.app_user_id"))
    # 0079: approved while the installation's setting was one approver; set by the guard alone
    approved_single_owner: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by_user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("app_user.app_user_id"))
    destroy_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    executed_by_user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("app_user.app_user_id"))
    backups_age_out_on: Mapped[date | None] = mapped_column(Date)
    files_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    files_deleted_count: Mapped[int | None] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("app_user.app_user_id"))
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")

    __table_args__ = (
        CheckConstraint("purge_kind IN ('ARCHIVE', 'DELETE', 'DELETE_ARCHIVE')", name="ck_pp_kind"),
        CheckConstraint("btrim(reason) <> ''", name="ck_pp_reason"),
        CheckConstraint("num_nonnulls(approved_at, approved_by_user_id) IN (0, 2)", name="ck_pp_approved"),
        CheckConstraint("approved_by_user_id <> requested_by_user_id OR approved_single_owner",
                        name="ck_pp_four_eyes"),                                                 # 0079
        CheckConstraint("NOT approved_single_owner OR approved_at IS NOT NULL", name="ck_pp_single_owner"),
        CheckConstraint("num_nonnulls(cancelled_at, cancelled_by_user_id) IN (0, 2)", name="ck_pp_cancelled"),
        CheckConstraint("num_nonnulls(executed_at, executed_by_user_id) IN (0, 2)", name="ck_pp_executed"),
        CheckConstraint("num_nonnulls(cancelled_at, executed_at) <= 1", name="ck_pp_one_end"),
        CheckConstraint("executed_at IS NULL OR approved_at IS NOT NULL", name="ck_pp_exec_approved"),
        CheckConstraint("(purge_kind = 'DELETE_ARCHIVE') = (archive_purge_id IS NOT NULL)", name="ck_pp_archive_ref"),
        CheckConstraint("purge_kind <> 'DELETE_ARCHIVE' OR repurge_of_purge_id IS NULL", name="ck_pp_repurge_kind"),
        CheckConstraint("num_nonnulls(archive_object_name, archive_sha256, archive_byte_size, archive_key_ref) "
                        "IN (0, 4)", name="ck_pp_archive_set"),
        CheckConstraint("purge_kind = 'ARCHIVE' OR archive_object_name IS NULL", name="ck_pp_archive_kind"),
        CheckConstraint("purge_kind <> 'ARCHIVE' OR executed_at IS NULL OR archive_object_name IS NOT NULL",
                        name="ck_pp_archive_exec"),
        CheckConstraint("archive_sha256 ~ '^[0-9a-f]{64}$'", name="ck_pp_archive_sha256"),
        CheckConstraint("archive_byte_size > 0", name="ck_pp_archive_size"),
        CheckConstraint("archive_checked_at IS NULL OR (purge_kind = 'ARCHIVE' AND executed_at IS NOT NULL)",
                        name="ck_pp_check_kind"),
        CheckConstraint("archive_check_error IS NULL OR archive_checked_at IS NOT NULL", name="ck_pp_check_pair"),
        CheckConstraint("destroy_started_at IS NULL OR (purge_kind = 'DELETE_ARCHIVE' AND approved_at IS NOT NULL)",
                        name="ck_pp_destroy_kind"),
        CheckConstraint("num_nonnulls(files_deleted_at, files_deleted_count) IN (0, 2) AND (files_deleted_at IS NULL "
                        "OR (purge_kind = 'DELETE_ARCHIVE' AND executed_at IS NOT NULL))", name="ck_pp_files_deleted"),
        CheckConstraint("files_deleted_count >= 0", name="ck_pp_files_count"),
        CheckConstraint("(executed_at IS NOT NULL AND purge_kind <> 'DELETE_ARCHIVE') = (backups_age_out_on IS NOT NULL)",
                        name="ck_pp_backups"),
        UniqueConstraint("archive_object_name", name="uq_pp_archive_object"),
        UniqueConstraint("project_purge_id", "project_id", "purge_kind", name="uq_pp_id_project_kind"),
        ForeignKeyConstraint(["archive_purge_id", "project_id", "archive_purge_kind"],
                             ["project_purge.project_purge_id", "project_purge.project_id", "project_purge.purge_kind"],
                             name="fk_pp_archive"),
        Index("uq_pp_open", "project_id", unique=True,
              postgresql_where=text("executed_at IS NULL AND cancelled_at IS NULL")),
        Index("uq_pp_removed", "project_id", unique=True,
              postgresql_where=text("executed_at IS NOT NULL AND purge_kind IN ('ARCHIVE', 'DELETE')")),
        Index("uq_pp_archive_deleted", "archive_purge_id", unique=True,
              postgresql_where=text("executed_at IS NOT NULL")),
    )


class ProjectPurgeKey(Base):
    """One project key name recorded by a removal, and its destruction (slice16 schema §3.3, §12.6; 0073). Names and
    versions only — never key material. A DELETE destroys its own keys; an ARCHIVE's are destroyed only by a later
    DELETE_ARCHIVE. Written by the owner-run purge job alone; the app reads it."""
    __tablename__ = "project_purge_key"

    project_purge_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("project_purge.project_purge_id"),
                                                  primary_key=True)
    key_name: Mapped[str] = mapped_column(String(200), primary_key=True)
    key_refs: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default="{}")
    destroyed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    was_present: Mapped[bool | None] = mapped_column(Boolean)
    destroyed_by_purge_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("project_purge.project_purge_id"))
    proof_object_name: Mapped[str | None] = mapped_column(String(400))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")

    __table_args__ = (
        CheckConstraint("num_nonnulls(destroyed_at, was_present, destroyed_by_purge_id) IN (0, 3)",
                        name="ck_ppk_destroyed"),
        CheckConstraint("proof_object_name IS NULL OR destroyed_at IS NOT NULL", name="ck_ppk_proof"),
        CheckConstraint("key_name ~ '^vb-[a-z0-9][a-z0-9-]{2,39}-proj-[0-9]+$'", name="ck_ppk_key_name"),
    )
