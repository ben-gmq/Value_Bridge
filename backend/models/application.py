"""Application landscape (§5.3, area 4, D-8): the catalogue, its to-be allocation to Solutions,
and as-is support on process steps. Schema: docs/slice6b_schema.md §1–§3; spec
docs/slice6b1_spec.md. All frozen into baselines (shadows generated later)."""
from sqlalchemy import (
    BigInteger, CheckConstraint, Computed, ForeignKey, ForeignKeyConstraint, Identity, Index, String, Text,
    UniqueConstraint, func, text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import AuditMixin, Base
from models.bfc import _live, _process_node_fk


class Application(AuditMixin, Base):
    """application_code is typed, upper-case, never reused (full UK) and editable until a baseline
    freezes it (S6b-6). Lifecycle AS_IS / TO_BE / BOTH is a system category (§8)."""

    __tablename__ = "application"

    application_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("project.project_id"), nullable=False)
    application_code: Mapped[str] = mapped_column(String(30), nullable=False)
    application_name: Mapped[str] = mapped_column(String(200), nullable=False)
    vendor: Mapped[str | None] = mapped_column(String(200))
    version_label: Mapped[str | None] = mapped_column(String(50))
    app_kind_code_id: Mapped[int | None] = mapped_column(BigInteger)
    app_kind_category: Mapped[str] = mapped_column(String(40), Computed("'APP_KIND'", persisted=True))
    lifecycle_code_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    lifecycle_category: Mapped[str] = mapped_column(String(40), Computed("'APP_LIFECYCLE'", persisted=True))
    description: Mapped[str | None] = mapped_column(Text)

    app_kind_code_row = relationship("CodeMaster", viewonly=True, lazy="joined",
                                     primaryjoin="foreign(Application.app_kind_code_id) == CodeMaster.code_id")
    lifecycle_code_row = relationship("CodeMaster", viewonly=True, lazy="joined",
                                      primaryjoin="foreign(Application.lifecycle_code_id) == CodeMaster.code_id")

    @property
    def app_kind_code(self) -> str | None:
        return self.app_kind_code_row.code if self.app_kind_code_row is not None else None

    @property
    def lifecycle_code(self) -> str | None:
        return self.lifecycle_code_row.code if self.lifecycle_code_row is not None else None

    __table_args__ = (
        UniqueConstraint("project_id", "application_code", name="uq_application_code"),
        UniqueConstraint("application_id", "project_id", name="uq_application_project"),
        ForeignKeyConstraint(["app_kind_code_id", "app_kind_category"], ["code_master.code_id", "code_master.category"],
                             name="fk_app_kind_code", onupdate="NO ACTION"),
        ForeignKeyConstraint(["lifecycle_code_id", "lifecycle_category"], ["code_master.code_id", "code_master.category"],
                             name="fk_app_lifecycle_code", onupdate="NO ACTION"),
        CheckConstraint("application_code ~ '^[A-Z0-9._-]+$'", name="ck_app_code_chars"),
        CheckConstraint("btrim(application_name) <> ''", name="ck_app_name_not_blank"),
        Index("uq_application_name_live", "project_id", func.lower(func.btrim(application_name)), unique=True,
              postgresql_where=text("is_active")),
        Index("ix_app_kind", "app_kind_code_id"),
        Index("ix_app_lifecycle", "lifecycle_code_id"),
    )

    def owning_project_id(self) -> int:
        return self.project_id


class ApplicationSolution(AuditMixin, Base):
    """To-be allocation: this application delivers this Solution. Never for an AS_IS application
    (R2-D11, service-enforced; consistency line as_is_allocated proves it). S1-5 surrogate PK."""

    __tablename__ = "application_solution"

    application_solution_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("project.project_id"), nullable=False)
    application_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    solution_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    allocation_note: Mapped[str | None] = mapped_column(Text)

    application_row = relationship("Application", viewonly=True,
                                   primaryjoin="foreign(ApplicationSolution.application_id) == Application.application_id")
    solution_row = relationship("Solution", viewonly=True,
                                primaryjoin="foreign(ApplicationSolution.solution_id) == Solution.solution_id")

    __table_args__ = (
        UniqueConstraint("application_id", "solution_id", name="uq_appsol_grain"),
        ForeignKeyConstraint(["application_id", "project_id"],
                             ["application.application_id", "application.project_id"], name="fk_appsol_application"),
        ForeignKeyConstraint(["solution_id", "project_id"], ["solution.solution_id", "solution.project_id"],
                             name="fk_appsol_solution"),
        Index("ix_appsol_solution", "solution_id", "project_id"),
        Index("ix_appsol_project", "project_id"),
    )

    def owning_project_id(self) -> int:
        return self.project_id


class ApplicationBfcNode(AuditMixin, Base):
    """As-is support: this application supports this process step today (D-8, D-23 guard).
    Retires and restores with its step (S6b-1, step_retire.OWNED_BY_STEP)."""

    __tablename__ = "application_bfc_node"

    application_bfc_node_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("project.project_id"), nullable=False)
    application_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    bfc_node_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    node_is_process: Mapped[bool | None] = _live(True)
    support_note: Mapped[str | None] = mapped_column(Text)

    application_row = relationship("Application", viewonly=True,
                                   primaryjoin="foreign(ApplicationBfcNode.application_id) == Application.application_id")
    node_row = relationship("BfcNode", viewonly=True,
                            primaryjoin="foreign(ApplicationBfcNode.bfc_node_id) == BfcNode.bfc_node_id")

    __table_args__ = (
        UniqueConstraint("application_id", "bfc_node_id", name="uq_appnode_grain"),
        ForeignKeyConstraint(["application_id", "project_id"],
                             ["application.application_id", "application.project_id"], name="fk_appnode_application"),
        *_process_node_fk("appnode"),
        Index("ix_appnode_node", "bfc_node_id", "project_id"),
        Index("ix_appnode_project", "project_id"),
    )

    def owning_project_id(self) -> int:
        return self.project_id
