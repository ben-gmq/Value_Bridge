"""Declarative base and the §5.1 conventions every business table carries.

`updated_at` is maintained by the fn_set_updated_at() DB trigger (§13) — never `onupdate=`.
`row_version` is SQLAlchemy's version_id_col, so every ORM UPDATE carries
`WHERE row_version = :v` and a lost race raises StaleDataError → 409 (D-6).
"""
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, func
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AuditMixin(TimestampMixin):
    """§5.1: audit columns, soft delete and optimistic concurrency, born with the table."""

    @declared_attr
    def created_by(cls) -> Mapped[int]:
        return mapped_column(BigInteger, ForeignKey("app_user.app_user_id"), nullable=False)

    @declared_attr
    def updated_by(cls) -> Mapped[int | None]:
        return mapped_column(BigInteger, ForeignKey("app_user.app_user_id"), nullable=True)

    @declared_attr
    def deleted_by(cls) -> Mapped[int | None]:
        return mapped_column(BigInteger, ForeignKey("app_user.app_user_id"), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")

    @declared_attr.directive
    def __mapper_args__(cls):
        return {"version_id_col": cls.row_version}
