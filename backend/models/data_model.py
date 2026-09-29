"""Data entities (§5.3, area 3): DATA_ENTITY and DATA_FIELD — frozen into baselines (D-3)."""
from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Computed, ForeignKey, ForeignKeyConstraint, Identity,
    Index, Integer, SmallInteger, String, Text, UniqueConstraint, func, text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import AuditMixin, Base


class DataEntity(AuditMixin, Base):
    """de_number is minted by numbering.next_number(…, 'DE') and never reused (§5.4.6)."""

    __tablename__ = "data_entity"

    data_entity_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("project.project_id"), nullable=False)
    de_number: Mapped[str] = mapped_column(String(20), nullable=False)
    de_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    business_owner_note: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("project_id", "de_number", name="uq_de_number"),
        UniqueConstraint("data_entity_id", "project_id", name="uq_data_entity_project"),
        Index("uq_de_name_live", "project_id", func.lower(func.btrim(de_name)), unique=True,
              postgresql_where=text("is_active")),
    )

    def owning_project_id(self) -> int:
        return self.project_id


class DataField(AuditMixin, Base):
    """A logical field (D-26). fk_group_no is assigned by the service from the relationship the
    request names (S1-7) — never stored as sent."""

    __tablename__ = "data_field"

    data_field_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("project.project_id"), nullable=False)
    data_entity_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    seq_no: Mapped[int] = mapped_column(Integer, nullable=False)
    field_name: Mapped[str] = mapped_column(String(200), nullable=False)
    data_type_code_id: Mapped[int | None] = mapped_column(BigInteger)
    data_type_category: Mapped[str] = mapped_column(String(40), Computed("'FIELD_DATA_TYPE'", persisted=True))
    length_val: Mapped[int | None] = mapped_column(Integer)
    precision_val: Mapped[int | None] = mapped_column(Integer)
    scale_val: Mapped[int | None] = mapped_column(Integer)
    is_mandatory: Mapped[bool | None] = mapped_column(Boolean)       # NULL = unknown (A-53)
    is_primary_key: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    pk_ordinal: Mapped[int | None] = mapped_column(SmallInteger)
    is_foreign_key: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    ref_data_entity_id: Mapped[int | None] = mapped_column(BigInteger)
    ref_data_field_id: Mapped[int | None] = mapped_column(BigInteger)
    fk_group_no: Mapped[int | None] = mapped_column(SmallInteger)
    description: Mapped[str | None] = mapped_column(Text)

    data_type_code_row = relationship("CodeMaster", viewonly=True, lazy="joined",
                            primaryjoin="foreign(DataField.data_type_code_id) == CodeMaster.code_id")

    @property
    def data_type_code(self) -> str | None:
        return self.data_type_code_row.code if self.data_type_code_row is not None else None

    __table_args__ = (
        UniqueConstraint("data_field_id", "data_entity_id", name="uq_data_field_entity"),
        ForeignKeyConstraint(["data_entity_id", "project_id"],
                             ["data_entity.data_entity_id", "data_entity.project_id"], name="fk_df_entity"),
        # With fk_df_ref_field: the ref field is in the ref entity, and that entity is in this project.
        ForeignKeyConstraint(["ref_data_entity_id", "project_id"],
                             ["data_entity.data_entity_id", "data_entity.project_id"],
                             name="fk_df_ref_entity"),
        ForeignKeyConstraint(["ref_data_field_id", "ref_data_entity_id"],
                             ["data_field.data_field_id", "data_field.data_entity_id"],
                             name="fk_df_ref_field"),
        ForeignKeyConstraint(["data_type_code_id", "data_type_category"],
                             ["code_master.code_id", "code_master.category"],
                             name="fk_df_data_type_code", onupdate="NO ACTION"),
        CheckConstraint("seq_no <> 0 AND seq_no BETWEEN -999 AND 999", name="ck_df_seq"),
        CheckConstraint("is_primary_key = (pk_ordinal IS NOT NULL)", name="ck_df_pk_ordinal"),
        CheckConstraint("pk_ordinal IS NULL OR pk_ordinal >= 1", name="ck_df_pk_ordinal_pos"),
        CheckConstraint("is_foreign_key = (ref_data_entity_id IS NOT NULL)", name="ck_df_fk_target"),
        CheckConstraint("ref_data_field_id IS NULL OR is_foreign_key", name="ck_df_ref_field"),
        CheckConstraint("(fk_group_no IS NOT NULL) = is_foreign_key", name="ck_df_fk_group"),
        CheckConstraint("fk_group_no IS NULL OR fk_group_no >= 1", name="ck_df_fk_group_pos"),
        CheckConstraint("NOT is_primary_key OR is_mandatory IS DISTINCT FROM FALSE",
                        name="ck_df_pk_not_optional"),
        CheckConstraint("data_type_code_id IS NOT NULL OR "
                        "num_nulls(length_val, precision_val, scale_val) = 3", name="ck_df_size_needs_type"),
        CheckConstraint("coalesce(length_val, 1) > 0 AND coalesce(precision_val, 1) > 0 "
                        "AND coalesce(scale_val, 0) >= 0 "
                        "AND (scale_val IS NULL OR precision_val IS NULL OR scale_val <= precision_val)",
                        name="ck_df_sizes"),
        Index("uq_df_name_live", "data_entity_id", func.lower(func.btrim(field_name)), unique=True,
              postgresql_where=text("is_active")),
        Index("uq_df_pk_ordinal", "data_entity_id", "pk_ordinal", unique=True,
              postgresql_where=text("is_primary_key AND is_active")),
        Index("uq_df_fk_group_field", "data_entity_id", "ref_data_entity_id", "fk_group_no",
              "ref_data_field_id", unique=True,
              postgresql_where=text("is_active AND ref_data_field_id IS NOT NULL")),
        Index("uq_df_seq_live", "data_entity_id", "seq_no", unique=True, postgresql_where=text("is_active")),
        Index("ix_df_project", "project_id"),
        Index("ix_df_entity", "data_entity_id", "project_id"),
        Index("ix_df_ref_entity", "ref_data_entity_id", "project_id"),
        Index("ix_df_ref_field", "ref_data_field_id"),
        Index("ix_df_type", "data_type_code_id"),
        Index("ix_df_fk_group", "data_entity_id", "ref_data_entity_id", "fk_group_no",
              postgresql_where=text("is_foreign_key")),
    )

    def owning_project_id(self) -> int:
        return self.project_id
