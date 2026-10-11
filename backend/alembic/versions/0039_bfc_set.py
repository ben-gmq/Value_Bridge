"""bfc_node.bfc_set_code — the to-be and the optional as-is function chart (D-47, slice7_schema §9.1).

Every existing node becomes TO_BE. A child is always in its parent's set (composite FK). The live code,
sibling-position and process indexes become per set, so each set has its own 01 and its own L1 row.
The column is immutable (service; the FKs refuse a change while children or a BR exist).

Revision ID: 0039
Revises: 0038
"""
from alembic import op
import sqlalchemy as sa

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("bfc_node", sa.Column("bfc_set_code", sa.String(10), nullable=False, server_default="TO_BE"))
    op.alter_column("bfc_node", "bfc_set_code", server_default=None)
    op.create_check_constraint("ck_bfc_set", "bfc_node", "bfc_set_code IN ('TO_BE', 'AS_IS')")
    op.create_unique_constraint("uq_bfc_node_set", "bfc_node", ["bfc_node_id", "project_id", "bfc_set_code"])
    op.create_foreign_key("fk_bfc_node_parent_set", "bfc_node", "bfc_node",
                          ["parent_bfc_node_id", "project_id", "bfc_set_code"],
                          ["bfc_node_id", "project_id", "bfc_set_code"], onupdate="NO ACTION")
    for name in ("uq_bfc_hier_code_live", "uq_bfc_sibling_seq", "ix_bfc_hier_pattern", "ix_bfc_process_live"):
        op.execute(f"DROP INDEX {name}")
    op.execute("CREATE UNIQUE INDEX uq_bfc_hier_code_live ON bfc_node (project_id, bfc_set_code, hier_code) WHERE is_active")
    op.execute("CREATE UNIQUE INDEX uq_bfc_sibling_seq ON bfc_node "
               "(project_id, bfc_set_code, parent_bfc_node_id, seq_no) NULLS NOT DISTINCT WHERE is_active")
    op.execute("CREATE INDEX ix_bfc_hier_pattern ON bfc_node "
               "(project_id, bfc_set_code, hier_code varchar_pattern_ops) WHERE is_active")
    op.execute("CREATE INDEX ix_bfc_process_live ON bfc_node (project_id, bfc_set_code) WHERE is_process AND is_active")


def downgrade() -> None:
    """Fails while any AS_IS row exists (the per-project indexes would collide): pauses for Ben."""
    for name in ("uq_bfc_hier_code_live", "uq_bfc_sibling_seq", "ix_bfc_hier_pattern", "ix_bfc_process_live"):
        op.execute(f"DROP INDEX {name}")
    op.execute("CREATE UNIQUE INDEX uq_bfc_hier_code_live ON bfc_node (project_id, hier_code) WHERE is_active")
    op.execute("CREATE UNIQUE INDEX uq_bfc_sibling_seq ON bfc_node "
               "(project_id, parent_bfc_node_id, seq_no) NULLS NOT DISTINCT WHERE is_active")
    op.execute("CREATE INDEX ix_bfc_hier_pattern ON bfc_node (project_id, hier_code varchar_pattern_ops) WHERE is_active")
    op.execute("CREATE INDEX ix_bfc_process_live ON bfc_node (project_id) WHERE is_process AND is_active")
    op.drop_constraint("fk_bfc_node_parent_set", "bfc_node", type_="foreignkey")
    op.drop_constraint("uq_bfc_node_set", "bfc_node", type_="unique")
    op.drop_constraint("ck_bfc_set", "bfc_node", type_="check")
    op.drop_column("bfc_node", "bfc_set_code")
