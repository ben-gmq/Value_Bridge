"""Business Requirement (§5.3, area 2): the BR (one per live process node, D-2) and its data
and RACI links. All frozen into baselines."""
from sqlalchemy import (
    CHAR, BigInteger, Boolean, CheckConstraint, Computed, ForeignKey, ForeignKeyConstraint,
    Identity, Index, SmallInteger, String, Text, UniqueConstraint, text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import AuditMixin, Base


class BusinessRequirement(AuditMixin, Base):
    """Created empty with its process node (S1-7): br_statement is NULL until written, status
    set to BR_STATUS/DRAFT by the service. bfc_node_id never changes (service-enforced)."""

    __tablename__ = "business_requirement"

    br_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("project.project_id"), nullable=False)
    bfc_node_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    node_is_process: Mapped[bool | None] = mapped_column(
        Boolean, Computed("CASE WHEN is_active THEN TRUE END", persisted=True))
    br_number: Mapped[str] = mapped_column(String(20), nullable=False)
    br_statement: Mapped[str | None] = mapped_column(Text)
    business_logic: Mapped[str | None] = mapped_column(Text)
    output_expectation: Mapped[str | None] = mapped_column(Text)
    status_code_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status_category: Mapped[str] = mapped_column(String(40), Computed("'BR_STATUS'", persisted=True))
    # S7-2: a BR hangs off a to-be process only (fk_br_node_to_be).
    node_bfc_set: Mapped[str] = mapped_column(String(10), Computed("'TO_BE'", persisted=True))

    status_code_row = relationship("CodeMaster", viewonly=True, lazy="joined",
                            primaryjoin="foreign(BusinessRequirement.status_code_id) == CodeMaster.code_id")

    @property
    def status_code(self) -> str | None:
        return self.status_code_row.code if self.status_code_row is not None else None

    __table_args__ = (
        UniqueConstraint("project_id", "br_number", name="uq_br_number"),
        UniqueConstraint("br_id", "project_id", name="uq_br_project"),
        UniqueConstraint("br_id", "project_id", "bfc_node_id", name="uq_br_node_carrier"),
        ForeignKeyConstraint(["bfc_node_id", "project_id"],
                             ["bfc_node.bfc_node_id", "bfc_node.project_id"], name="fk_br_node"),
        ForeignKeyConstraint(["bfc_node_id", "project_id", "node_is_process"],
                             ["bfc_node.bfc_node_id", "bfc_node.project_id", "bfc_node.is_process"],
                             name="fk_br_node_process", onupdate="NO ACTION"),
        ForeignKeyConstraint(["status_code_id", "status_category"],
                             ["code_master.code_id", "code_master.category"],
                             name="fk_br_status_code", onupdate="NO ACTION"),
        ForeignKeyConstraint(["bfc_node_id", "project_id", "node_bfc_set"],
                             ["bfc_node.bfc_node_id", "bfc_node.project_id", "bfc_node.bfc_set_code"],
                             name="fk_br_node_to_be", onupdate="NO ACTION"),
        # D-2 / S7-2: one live BR per to-be process.
        Index("uq_br_one_per_node", "bfc_node_id", unique=True, postgresql_where=text("is_active")),
        Index("ix_br_node", "bfc_node_id", "project_id"),
        Index("ix_br_status", "status_code_id"),
    )

    def owning_project_id(self) -> int:
        return self.project_id


class BrDataEntity(AuditMixin, Base):
    """BR × DE × CRUD, licensed by live step I/O (D-24). direction is generated; bfc_node_id is
    copied from the BR by the service. S1-5: surrogate PK."""

    __tablename__ = "br_data_entity"

    br_data_entity_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("project.project_id"), nullable=False)
    br_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    bfc_node_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    data_entity_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    crud_code: Mapped[str] = mapped_column(CHAR(1), nullable=False)
    direction: Mapped[str] = mapped_column(
        CHAR(1), Computed("CASE WHEN crud_code = 'R' THEN 'I' ELSE 'O' END", persisted=True))
    io_is_active: Mapped[bool | None] = mapped_column(
        Boolean, Computed("CASE WHEN is_active THEN TRUE END", persisted=True))
    usage_note: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("br_id", "data_entity_id", "crud_code", name="uq_brde_grain"),
        # D-60(b): the target of br_data_field's licence FK — a live attribute tick needs this live row.
        UniqueConstraint("br_id", "data_entity_id", "crud_code", "io_is_active", name="uq_brde_live_licence"),
        ForeignKeyConstraint(["br_id", "project_id", "bfc_node_id"],
                             ["business_requirement.br_id", "business_requirement.project_id",
                              "business_requirement.bfc_node_id"], name="fk_brde_br"),
        ForeignKeyConstraint(["data_entity_id", "project_id"],
                             ["data_entity.data_entity_id", "data_entity.project_id"], name="fk_brde_de"),
        ForeignKeyConstraint(["bfc_node_id", "data_entity_id", "direction", "io_is_active"],
                             ["bfc_node_data_entity.bfc_node_id", "bfc_node_data_entity.data_entity_id",
                              "bfc_node_data_entity.direction", "bfc_node_data_entity.is_active"],
                             name="fk_brde_io_licence", onupdate="NO ACTION"),
        CheckConstraint("crud_code IN ('C', 'R', 'U', 'D')", name="ck_brde_crud"),
        Index("ix_brde_de", "data_entity_id"),
        Index("ix_brde_io", "bfc_node_id", "data_entity_id", "direction"),
        Index("ix_brde_project", "project_id"),
    )

    def owning_project_id(self) -> int:
        return self.project_id


class BrDataField(AuditMixin, Base):
    """D-60(b) (slice11_schema §2): BR × attribute × C / R / U — which fields a BR uses and how. Delete stays
    entity-level. Licensed by the BR's live entity-level row of the same CRUD (fk_brdf_licence → uq_brde_live_licence),
    so a tick can never outlive its entity tick; the field FK proves the attribute belongs to that entity."""

    __tablename__ = "br_data_field"

    br_data_field_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("project.project_id"), nullable=False)
    br_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    data_entity_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    crud_code: Mapped[str] = mapped_column(CHAR(1), nullable=False)
    brde_is_active: Mapped[bool | None] = mapped_column(
        Boolean, Computed("CASE WHEN is_active THEN TRUE END", persisted=True))
    data_field_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    usage_note: Mapped[str | None] = mapped_column(Text)

    br_row = relationship("BusinessRequirement", viewonly=True, lazy="joined",
                          primaryjoin="foreign(BrDataField.br_id) == BusinessRequirement.br_id")
    field_row = relationship("DataField", viewonly=True, lazy="joined",
                             primaryjoin="foreign(BrDataField.data_field_id) == DataField.data_field_id")

    __table_args__ = (
        UniqueConstraint("br_id", "data_field_id", "crud_code", name="uq_brdf_grain"),
        ForeignKeyConstraint(["br_id", "project_id"],
                             ["business_requirement.br_id", "business_requirement.project_id"], name="fk_brdf_br"),
        ForeignKeyConstraint(["br_id", "data_entity_id", "crud_code", "brde_is_active"],
                             ["br_data_entity.br_id", "br_data_entity.data_entity_id", "br_data_entity.crud_code",
                              "br_data_entity.io_is_active"], name="fk_brdf_licence", onupdate="NO ACTION"),
        ForeignKeyConstraint(["data_field_id", "data_entity_id"],
                             ["data_field.data_field_id", "data_field.data_entity_id"], name="fk_brdf_field"),
        CheckConstraint("crud_code IN ('C', 'R', 'U')", name="ck_brdf_crud"),
        Index("ix_brdf_field", "data_field_id"),
        Index("ix_brdf_project", "project_id"),
    )

    def owning_project_id(self) -> int:
        return self.project_id


class BrSystemFlow(AuditMixin, Base):
    """D-61 (slice11_schema §3): "what data entity we copy from which system to which system" on a to-be BR — one row
    per (BR × entity × from-application × to-application). Both ends come from the Applications master list (S11-3),
    never free text, and differ. No pointer to an FR: coverage by an interface FR is derived (§3.1); an interface FR
    and a Data migration FR (S11-5) cover a flow alike. Gated by APPLICATION."""

    __tablename__ = "br_system_flow"

    br_system_flow_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("project.project_id"), nullable=False)
    br_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    data_entity_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_application_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    target_application_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    flow_note: Mapped[str | None] = mapped_column(Text)

    br_row = relationship("BusinessRequirement", viewonly=True, lazy="joined",
                          primaryjoin="foreign(BrSystemFlow.br_id) == BusinessRequirement.br_id")
    entity_row = relationship("DataEntity", viewonly=True, lazy="joined",
                              primaryjoin="foreign(BrSystemFlow.data_entity_id) == DataEntity.data_entity_id")
    source_row = relationship("Application", viewonly=True, lazy="joined",
                              primaryjoin="foreign(BrSystemFlow.source_application_id) == Application.application_id")
    target_row = relationship("Application", viewonly=True, lazy="joined",
                              primaryjoin="foreign(BrSystemFlow.target_application_id) == Application.application_id")

    __table_args__ = (
        UniqueConstraint("br_id", "data_entity_id", "source_application_id", "target_application_id",
                         name="uq_brsf_grain"),
        ForeignKeyConstraint(["br_id", "project_id"],
                             ["business_requirement.br_id", "business_requirement.project_id"], name="fk_brsf_br"),
        ForeignKeyConstraint(["data_entity_id", "project_id"],
                             ["data_entity.data_entity_id", "data_entity.project_id"], name="fk_brsf_de"),
        ForeignKeyConstraint(["source_application_id", "project_id"],
                             ["application.application_id", "application.project_id"], name="fk_brsf_source"),
        ForeignKeyConstraint(["target_application_id", "project_id"],
                             ["application.application_id", "application.project_id"], name="fk_brsf_target"),
        CheckConstraint("source_application_id <> target_application_id", name="ck_brsf_endpoints_distinct"),
        Index("ix_brsf_de", "data_entity_id"),
        Index("ix_brsf_source", "source_application_id"),
        Index("ix_brsf_target", "target_application_id"),
        Index("ix_brsf_project", "project_id"),
    )

    def owning_project_id(self) -> int:
        return self.project_id


class BrRequirementLine(AuditMixin, Base):
    """D-59 (slice11_schema §1.1): one numbered requirement statement within one BR — "BR-0043.3". line_no is
    minted by the service (max + 1 over all the BR's lines, retired included), never reused, never sent; seq_no is
    the display order. Kind and priority are category-only FKs (no behaviour, §1.3); priority NULL = not yet set."""

    __tablename__ = "br_requirement_line"

    br_requirement_line_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("project.project_id"), nullable=False)
    br_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    line_no: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    seq_no: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    line_kind_code_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    line_kind_category: Mapped[str] = mapped_column(String(40), Computed("'BR_LINE_KIND'", persisted=True))
    priority_code_id: Mapped[int | None] = mapped_column(BigInteger)
    priority_category: Mapped[str] = mapped_column(String(40), Computed("'BR_PRIORITY'", persisted=True))
    line_text: Mapped[str] = mapped_column(Text, nullable=False)

    br_row = relationship("BusinessRequirement", viewonly=True, lazy="joined",
                          primaryjoin="foreign(BrRequirementLine.br_id) == BusinessRequirement.br_id")
    line_kind_row = relationship("CodeMaster", viewonly=True, lazy="joined",
                                 primaryjoin="foreign(BrRequirementLine.line_kind_code_id) == CodeMaster.code_id")
    priority_row = relationship("CodeMaster", viewonly=True, lazy="joined",
                                primaryjoin="foreign(BrRequirementLine.priority_code_id) == CodeMaster.code_id")

    @property
    def line_kind_code(self) -> str | None:
        return self.line_kind_row.code if self.line_kind_row is not None else None

    @property
    def priority_code(self) -> str | None:
        return self.priority_row.code if self.priority_row is not None else None

    @property
    def line_label(self) -> str:
        return f"{self.br_row.br_number}.{self.line_no}"

    __table_args__ = (
        UniqueConstraint("br_id", "line_no", name="uq_brl_line_no"),
        ForeignKeyConstraint(["br_id", "project_id"],
                             ["business_requirement.br_id", "business_requirement.project_id"], name="fk_brl_br"),
        ForeignKeyConstraint(["line_kind_code_id", "line_kind_category"],
                             ["code_master.code_id", "code_master.category"], name="fk_brl_kind",
                             onupdate="NO ACTION"),
        ForeignKeyConstraint(["priority_code_id", "priority_category"],
                             ["code_master.code_id", "code_master.category"], name="fk_brl_priority",
                             onupdate="NO ACTION"),
        CheckConstraint("line_no >= 1", name="ck_brl_line_no"),
        CheckConstraint("btrim(line_text) <> ''", name="ck_brl_text"),
        Index("uq_brl_seq_live", "br_id", "seq_no", unique=True, postgresql_where=text("is_active")),
        Index("ix_brl_project", "project_id"),
        Index("ix_brl_kind", "line_kind_code_id"),
        Index("ix_brl_priority", "priority_code_id"),
    )

    def owning_project_id(self) -> int:
        return self.project_id


class BrOrgRole(AuditMixin, Base):
    """BR × org role × RACI; one ACCOUNTABLE-behaviour role per BR. S1-5: surrogate PK."""

    __tablename__ = "br_org_role"

    br_org_role_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("project.project_id"), nullable=False)
    br_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    org_role_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    raci_code_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    raci_category: Mapped[str] = mapped_column(String(40), Computed("'RACI_TYPE'", persisted=True))
    raci_behaviour: Mapped[str] = mapped_column(String(20), nullable=False)

    raci_code_row = relationship("CodeMaster", viewonly=True, lazy="joined",
                            primaryjoin="foreign(BrOrgRole.raci_code_id) == CodeMaster.code_id")

    @property
    def raci_code(self) -> str | None:
        return self.raci_code_row.code if self.raci_code_row is not None else None

    __table_args__ = (
        UniqueConstraint("br_id", "org_role_id", "raci_code_id", name="uq_bror_grain"),
        ForeignKeyConstraint(["br_id", "project_id"],
                             ["business_requirement.br_id", "business_requirement.project_id"],
                             name="fk_bror_br"),
        ForeignKeyConstraint(["org_role_id", "project_id"],
                             ["org_role.org_role_id", "org_role.project_id"], name="fk_bror_role"),
        ForeignKeyConstraint(["raci_code_id", "raci_category", "raci_behaviour"],
                             ["code_master.code_id", "code_master.category", "code_master.behaviour_code"],
                             name="fk_bror_raci", onupdate="NO ACTION"),
        Index("uq_bror_one_accountable", "br_id", unique=True,
              postgresql_where=text("is_active AND raci_behaviour = 'ACCOUNTABLE'")),
        Index("ix_bror_role", "org_role_id", "project_id"),
        Index("ix_bror_raci", "raci_code_id"),
        Index("ix_bror_project", "project_id"),
    )

    def owning_project_id(self) -> int:
        return self.project_id
