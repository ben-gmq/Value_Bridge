"""program_member — a named member of a program, with a level (D-71; docs/access_v2_model.md §6 B).

One row per membership period of one user on one program (partial unique while live); re-adding inserts, never restores
(R2-S5, as project_member). Through project.program_id it gives that user its level on every live project of the
program, restricted ones included — effective access is still computed per request (services/access). A live member
blocks retiring its program through the generated live guard and the composite FK to program(program_id, is_active)
(law 1: nothing cascades). Not shadowed or frozen. vb_app gets SELECT/INSERT/UPDATE from 0001's default privileges and
no DELETE.

Downgrade: refuses while the table holds any row — dropping it would erase membership history.

Revision ID: 0060
Revises: 0059
"""
from alembic import op
import sqlalchemy as sa

from vb_ops import audit_columns, drop_updated_at_trigger, live_guard, updated_at_trigger

revision = "0060"
down_revision = "0059"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "program_member",
        sa.Column("program_member_id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("program_id", sa.BigInteger, sa.ForeignKey("program.program_id"), nullable=False),
        live_guard("program_is_active", True),
        sa.Column("app_user_id", sa.BigInteger, sa.ForeignKey("app_user.app_user_id"), nullable=False),
        sa.Column("access_level", sa.String(5), nullable=False),
        sa.Column("member_note", sa.Text),
        *audit_columns(),
        sa.ForeignKeyConstraint(["program_id", "program_is_active"], ["program.program_id", "program.is_active"],
                                name="fk_prgm_live_program", onupdate="NO ACTION"),
        sa.CheckConstraint("access_level IN ('ADMIN', 'EDIT', 'VIEW')", name="ck_prgm_level"),
        sa.CheckConstraint("member_note IS NULL OR btrim(member_note) <> ''", name="ck_prgm_note_not_blank"),
    )
    op.execute("CREATE UNIQUE INDEX uq_prgm_live ON program_member (program_id, app_user_id) WHERE is_active")
    op.execute("CREATE INDEX ix_prgm_user_live ON program_member (app_user_id) WHERE is_active")
    updated_at_trigger("program_member")


def downgrade() -> None:
    op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM program_member) THEN "
               "RAISE EXCEPTION 'program memberships exist: downgrade refused'; END IF; END $$")
    drop_updated_at_trigger("program_member")
    op.drop_table("program_member")
