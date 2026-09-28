"""Identity and tenancy: app_user, client, code_master, program, project (§5.3, D-32).

code_master ↔ project reference each other (project.status_code_id, code_master.project_id),
so code_master's project FK is added after both tables exist.

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa

from vb_ops import audit_columns, drop_updated_at_trigger, updated_at_trigger

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

TABLES = ("app_user", "client", "code_master", "program", "project")


def upgrade() -> None:
    op.create_table(
        "app_user",
        sa.Column("app_user_id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("is_platform_admin", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", sa.BigInteger, sa.ForeignKey("app_user.app_user_id")),
        sa.Column("row_version", sa.Integer, nullable=False, server_default="1"),
    )
    op.execute("CREATE UNIQUE INDEX uq_app_user_email ON app_user (lower(email))")

    op.create_table(
        "client",
        sa.Column("client_id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("client_code", sa.String(30), nullable=False, unique=True),
        sa.Column("client_name", sa.String(200), nullable=False),
        sa.Column("industry", sa.String(100)),
        *audit_columns(),
    )

    op.create_table(
        "code_master",
        sa.Column("code_id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("project_id", sa.BigInteger),            # FK added below
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("behaviour_code", sa.String(20)),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_system", sa.Boolean, nullable=False, server_default=sa.false()),
        *audit_columns(),
        sa.CheckConstraint("(category IN ('FR_TYPE','RACI_TYPE')) = (behaviour_code IS NOT NULL)",
                           name="ck_code_behaviour_present"),
        sa.CheckConstraint("category <> 'FR_TYPE' OR behaviour_code IN "
                           "('FORM','INTERFACE','REPORT','BATCH','OTHER')",
                           name="ck_code_fr_behaviour"),
        sa.CheckConstraint("category <> 'RACI_TYPE' OR behaviour_code IN "
                           "('RESPONSIBLE','ACCOUNTABLE','CONSULTED','INFORMED','SUPPORT','OTHER')",
                           name="ck_code_raci_behaviour"),
        sa.UniqueConstraint("code_id", "category", "behaviour_code", name="uq_code_behaviour_target"),
        sa.UniqueConstraint("code_id", "category", name="uq_code_category_target"),
    )
    # Seeded library rows are created by nobody: the one place created_by may be NULL.
    op.alter_column("code_master", "created_by", nullable=True)
    op.execute("CREATE UNIQUE INDEX uq_code_master_scope ON code_master "
               "(project_id, category, code) NULLS NOT DISTINCT")

    op.create_table(
        "program",
        sa.Column("program_id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("client_id", sa.BigInteger, sa.ForeignKey("client.client_id"), nullable=False),
        sa.Column("program_code", sa.String(30), nullable=False),
        sa.Column("program_name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text),
        *audit_columns(),
        sa.UniqueConstraint("client_id", "program_code", name="uq_program_code"),
        sa.UniqueConstraint("program_id", "client_id", name="uq_program_client"),
        sa.UniqueConstraint("program_id", "client_id", "is_active", name="uq_program_client_live"),
        sa.UniqueConstraint("program_id", "is_active", name="uq_program_live"),
    )
    op.execute("CREATE UNIQUE INDEX uq_program_name_live ON program "
               "(client_id, lower(program_name)) WHERE is_active")

    op.create_table(
        "project",
        sa.Column("project_id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("client_id", sa.BigInteger, sa.ForeignKey("client.client_id"), nullable=False),
        sa.Column("program_id", sa.BigInteger),
        sa.Column("program_is_active", sa.Boolean,
                  sa.Computed("CASE WHEN is_active THEN TRUE END", persisted=True)),
        sa.Column("project_code", sa.String(30), nullable=False),
        sa.Column("project_name", sa.String(200), nullable=False),
        sa.Column("start_date", sa.Date),
        sa.Column("end_date", sa.Date),
        sa.Column("status_code_id", sa.BigInteger,
                  sa.ForeignKey("code_master.code_id", name="fk_project_status"), nullable=False),
        *audit_columns(),
        sa.UniqueConstraint("client_id", "project_code", name="uq_project_code"),
        sa.UniqueConstraint("project_id", "is_active", name="uq_project_live"),
        sa.ForeignKeyConstraint(["program_id", "client_id"],
                                ["program.program_id", "program.client_id"],
                                name="fk_project_program_client"),
        sa.ForeignKeyConstraint(["program_id", "client_id", "program_is_active"],
                                ["program.program_id", "program.client_id", "program.is_active"],
                                name="fk_project_program_live", onupdate="NO ACTION"),
        sa.CheckConstraint("end_date IS NULL OR start_date IS NULL OR end_date >= start_date",
                           name="ck_project_dates"),
    )
    op.create_foreign_key("fk_code_master_project", "code_master", "project",
                          ["project_id"], ["project_id"])

    for t in TABLES:
        updated_at_trigger(t)


def downgrade() -> None:
    for t in reversed(TABLES):
        drop_updated_at_trigger(t)
    op.drop_constraint("fk_code_master_project", "code_master", type_="foreignkey")
    op.drop_table("project")
    op.drop_table("program")
    op.drop_table("code_master")
    op.drop_table("client")
    op.drop_table("app_user")
