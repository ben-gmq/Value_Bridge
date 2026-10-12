"""br_function_requirement — BR × FR, the direct mapping (D-52; docs/slice10b_schema.md §1, §9).

S1-5 surrogate PK + a FULL unique grain (br_id, fr_id) [Q-2], so a re-link restores the same row. Both
composites keep a pairing inside one project. vb_app gets SELECT/INSERT/UPDATE from 0001's default privileges
and no DELETE (law 1).

Downgrade [Q-21]: refuses while any row exists that 0051's backfill did not insert (its BR_FR_BACKFILLED events
list every id it wrote), or any row was changed since (row_version > 1). A downgrade never destroys a link a
person made.

Revision ID: 0049
Revises: 0048
"""
from alembic import op
import sqlalchemy as sa

from vb_ops import audit_columns, drop_updated_at_trigger, updated_at_trigger

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "br_function_requirement",
        sa.Column("br_function_requirement_id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("project_id", sa.BigInteger, sa.ForeignKey("project.project_id"), nullable=False),
        sa.Column("br_id", sa.BigInteger, nullable=False),
        sa.Column("fr_id", sa.BigInteger, nullable=False),
        sa.Column("coverage_note", sa.Text),
        *audit_columns(),
        sa.UniqueConstraint("br_id", "fr_id", name="uq_brfr_grain"),
        sa.ForeignKeyConstraint(["br_id", "project_id"],
                                ["business_requirement.br_id", "business_requirement.project_id"],
                                name="fk_brfr_br"),
        sa.ForeignKeyConstraint(["fr_id", "project_id"],
                                ["function_requirement.fr_id", "function_requirement.project_id"],
                                name="fk_brfr_fr"),
    )
    op.create_index("ix_brfr_fr", "br_function_requirement", ["fr_id", "project_id"])
    op.create_index("ix_brfr_project", "br_function_requirement", ["project_id"])
    updated_at_trigger("br_function_requirement")


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM br_function_requirement l
                     WHERE l.row_version > 1
                        OR NOT EXISTS (SELECT 1 FROM audit_event e,
                                              jsonb_array_elements(e.detail -> 'link_ids') AS x(id)
                                       WHERE e.event_type = 'BR_FR_BACKFILLED'
                                         AND x.id::text::bigint = l.br_function_requirement_id)) THEN
            RAISE EXCEPTION 'br_function_requirement holds links made or changed after 0051: downgrade refused';
          END IF;
        END $$""")
    drop_updated_at_trigger("br_function_requirement")
    op.drop_table("br_function_requirement")
