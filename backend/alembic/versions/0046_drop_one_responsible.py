"""Drop uq_bnor_one_responsible (D-46, Q-26): the lane is the performer now, so normal RACI allows
several Responsible roles on a step. One Accountable stays (uq_bnor_one_accountable).

Revision ID: 0046
Revises: 0045
"""
from alembic import op

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX uq_bnor_one_responsible")


def downgrade() -> None:
    """Fails if two live RESPONSIBLE roles now share a step: pauses for Ben."""
    op.execute("CREATE UNIQUE INDEX uq_bnor_one_responsible ON bfc_node_org_role (bfc_node_id) "
               "WHERE is_active AND raci_behaviour = 'RESPONSIBLE'")
