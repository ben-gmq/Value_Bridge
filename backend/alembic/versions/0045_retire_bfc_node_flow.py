"""Retire the process-flow arrows (D-38, slice7_schema §9.6): order is now derived from data.

Every live bfc_node_flow is soft-retired (never deleted), with one FLOW_EDGES_RETIRED audit event per
project, and the app role loses INSERT and UPDATE on the table — "no new arrows" is a database fact.
The rows stay readable as history.

Revision ID: 0045
Revises: 0044
"""
from alembic import op

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO audit_event (event_type, project_id, target_table, detail)
        SELECT 'FLOW_EDGES_RETIRED', project_id, 'bfc_node_flow',
               jsonb_build_object('count', count(*), 'ids', jsonb_agg(bfc_node_flow_id ORDER BY bfc_node_flow_id),
                                  'decision', 'D-38', 'migration', '0045')
        FROM bfc_node_flow WHERE is_active GROUP BY project_id""")
    op.execute("UPDATE bfc_node_flow SET is_active = false, deleted_at = now(), row_version = row_version + 1 "
               "WHERE is_active")
    op.execute("REVOKE INSERT, UPDATE ON bfc_node_flow FROM vb_app")


def downgrade() -> None:
    # The retirement is evidence and stays; only the privilege returns.
    op.execute("GRANT INSERT, UPDATE ON bfc_node_flow TO vb_app")
