"""The performer of a process (D-46, slice7_schema §9.4): one per process — a department (org unit), a
position (org role), an IT system (application) or AI — as an exclusive arc of typed columns on
bfc_node. Kinds are CHECK-listed (S2-1). FKs are composite with project_id.

Data step (Q-27, DR7-P3): every process — live, or retired together with its RESPONSIBLE link —
whose RESPONSIBLE RACI role gives today's lane gets performer ORG_ROLE = that role, so lanes survive.

Revision ID: 0041
Revises: 0040
"""
from alembic import op
import sqlalchemy as sa

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None

_FKS = (("unit", "performer_org_unit_id", "org_unit", "org_unit_id"),
        ("role", "performer_org_role_id", "org_role", "org_role_id"),
        ("app", "performer_application_id", "application", "application_id"))


def upgrade() -> None:
    op.add_column("bfc_node", sa.Column("performer_kind", sa.String(12)))
    for _s, col, _t, _p in _FKS:
        op.add_column("bfc_node", sa.Column(col, sa.BigInteger))
    op.add_column("bfc_node", sa.Column("performer_label", sa.String(200)))
    op.create_check_constraint("ck_bfc_performer_kind", "bfc_node",
                               "performer_kind IS NULL OR performer_kind IN ('ORG_UNIT','ORG_ROLE','APPLICATION','AI')")
    op.create_check_constraint("ck_bfc_performer_arc", "bfc_node", """
        num_nonnulls(performer_org_unit_id, performer_org_role_id, performer_application_id)
            = CASE WHEN performer_kind IN ('ORG_UNIT','ORG_ROLE','APPLICATION') THEN 1 ELSE 0 END
        AND (performer_kind IS DISTINCT FROM 'ORG_UNIT'    OR performer_org_unit_id   IS NOT NULL)
        AND (performer_kind IS DISTINCT FROM 'ORG_ROLE'    OR performer_org_role_id   IS NOT NULL)
        AND (performer_kind IS DISTINCT FROM 'APPLICATION' OR performer_application_id IS NOT NULL)""")
    op.create_check_constraint("ck_bfc_performer_label", "bfc_node",
                               "performer_label IS NULL OR (performer_kind IS NOT DISTINCT FROM 'AI' AND btrim(performer_label) <> '')")
    op.create_check_constraint("ck_bfc_performer_ai_label", "bfc_node",
                               "performer_kind IS DISTINCT FROM 'AI' OR performer_label IS NOT NULL")
    op.create_check_constraint("ck_bfc_performer_process", "bfc_node", "performer_kind IS NULL OR is_process")
    for short, col, table, pk in _FKS:
        op.create_foreign_key(f"fk_bfc_perf_{short}", "bfc_node", table, [col, "project_id"],
                              [pk, "project_id"], onupdate="NO ACTION")
        op.execute(f"CREATE INDEX ix_bfc_perf_{short} ON bfc_node ({col}, project_id) WHERE {col} IS NOT NULL")
    op.execute("""
        UPDATE bfc_node n SET performer_kind = 'ORG_ROLE', performer_org_role_id = r.org_role_id,
                              row_version = n.row_version + 1
        FROM bfc_node_org_role r
        WHERE r.bfc_node_id = n.bfc_node_id AND r.raci_behaviour = 'RESPONSIBLE' AND n.is_process
          AND ((n.is_active AND r.is_active)
               OR (NOT n.is_active AND NOT r.is_active AND r.deleted_at = n.deleted_at))""")


def downgrade() -> None:
    """Loses performers set since: pauses for Ben once any exist beyond the backfill."""
    for short, _col, _t, _p in _FKS:
        op.execute(f"DROP INDEX ix_bfc_perf_{short}")
        op.drop_constraint(f"fk_bfc_perf_{short}", "bfc_node", type_="foreignkey")
    for ck in ("ck_bfc_performer_process", "ck_bfc_performer_ai_label", "ck_bfc_performer_label",
               "ck_bfc_performer_arc", "ck_bfc_performer_kind"):
        op.drop_constraint(ck, "bfc_node", type_="check")
    for col in ("performer_label", "performer_application_id", "performer_org_role_id",
                "performer_org_unit_id", "performer_kind"):
        op.drop_column("bfc_node", col)
