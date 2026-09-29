"""Business Requirement (§5.3, area 2): the BR (one per live process node, D-2) and its data
and RACI links. All frozen into baselines."""
from sqlalchemy import (
    CHAR, BigInteger, Boolean, CheckConstraint, Computed, ForeignKey, ForeignKeyConstraint,
    Identity, Index, String, Text, UniqueConstraint, text,
)
from sqlalchemy.orm import Mapped, mapped_column

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
        # D-2: one live BR per node.
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
