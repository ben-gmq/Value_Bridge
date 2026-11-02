"""decision — the append-only decision log (design §4.11, §5 DECISION, D-17, A-41, criterion 78;
docs/slice_decisions_spec.md §5; DC-1…DC-5, Ben 2026-11-02; review round 1 D1-1…D1-6).

  1. Refuses while any project-tier PM_DIMENSION row or project hide of one exists, naming it as project:code:
     PM_DIMENSION becomes company-only, because a decision is never re-pointed to a project's copy of a code.
  2. decision: one row per recorded decision; no soft delete, no updated_* columns, no row_version (nothing ever changes
     it). Dimension through (code_id, category); the decision it supersedes through (id, project_id), so a correction
     stays in its project; uq_decision_superseded_once lets each decision be corrected once (DC-2). analysis_code is
     checked for format only (D1-2); decided_by_user_id equals created_by (D1-1); decided_on is never past the
     creation day (+1 for the time-zone edge; the service refuses tomorrow in ICT). The id is GENERATED ALWAYS.
  3. fn_decision_reject + trg_decision_immutable: UPDATE always raises; DELETE passes only when fn_purge_allows (0074)
     says so for the row's own project — the scoped purge of an approved request, run as vb_owner. No TRUNCATE trigger
     (as the shadows, S8-2). purge_run.DELETE_GUARDS names the function.
  4. fn_decision_stamp + trg_decision_stamp: created_at is the database's clock, never the request's (D1-3).
  5. vb_app: UPDATE and TRUNCATE revoked (0001's default privileges granted UPDATE); it never had DELETE.

Not a shadow (law 2 n/a), not frozen (design §6 table 35); purge_run finds it by its project_id.

Downgrade: refuses while any decision row exists (evidential — nothing could recreate it); then drops the table and
the functions.

Revision ID: 0084
Revises: 0083
"""
from alembic import op
import sqlalchemy as sa

from vb_ops import category_column

revision = "0084"
down_revision = "0083"
branch_labels = None
depends_on = None

REJECT = """
    CREATE FUNCTION public.fn_decision_reject() RETURNS trigger
    LANGUAGE plpgsql SET search_path = pg_catalog, public, pg_temp AS $$
    BEGIN
      IF TG_OP = 'DELETE' AND public.fn_purge_allows(OLD.project_id) THEN
        RETURN OLD;
      END IF;
      RAISE EXCEPTION '% on decision is not allowed: a decision is never changed; record a new one that supersedes it',
        TG_OP USING ERRCODE = 'restrict_violation';
    END $$
"""

STAMP = """
    CREATE FUNCTION public.fn_decision_stamp() RETURNS trigger
    LANGUAGE plpgsql SET search_path = pg_catalog, public, pg_temp AS $$
    BEGIN
      NEW.created_at := now();
      RETURN NEW;
    END $$
"""


def upgrade() -> None:
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM code_master WHERE category = 'PM_DIMENSION' AND project_id IS NOT NULL) THEN
        RAISE EXCEPTION 'project-tier PM_DIMENSION rows exist (%): decision dimensions are company-only; resolve them '
          'by hand first', (SELECT string_agg(project_id || ':' || code, ', ') FROM code_master
                             WHERE category = 'PM_DIMENSION' AND project_id IS NOT NULL);
      END IF;
      IF EXISTS (SELECT 1 FROM project_code_visibility v JOIN code_master c ON c.code_id = v.code_id
                  WHERE c.category = 'PM_DIMENSION' AND v.is_active) THEN
        RAISE EXCEPTION 'a project hides a PM_DIMENSION (%): decision dimensions are company-only; unhide first',
          (SELECT string_agg(v.project_id || ':' || c.code, ', ') FROM project_code_visibility v
             JOIN code_master c ON c.code_id = v.code_id WHERE c.category = 'PM_DIMENSION' AND v.is_active);
      END IF;
    END $$""")
    op.create_table(
        "decision",
        sa.Column("decision_id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column("project_id", sa.BigInteger, sa.ForeignKey("project.project_id"), nullable=False),
        sa.Column("decision_number", sa.String(20), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("decision_text", sa.Text, nullable=False),
        sa.Column("alternative_rejected", sa.Text, nullable=False),
        sa.Column("analysis_code", sa.String(40)),
        sa.Column("dimension_code_id", sa.BigInteger, nullable=False),
        category_column("dimension_category", "PM_DIMENSION"),
        sa.Column("decided_on", sa.Date, nullable=False),
        sa.Column("decided_by_user_id", sa.BigInteger, sa.ForeignKey("app_user.app_user_id"), nullable=False),
        sa.Column("supersedes_decision_id", sa.BigInteger),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", sa.BigInteger, sa.ForeignKey("app_user.app_user_id"), nullable=False),
        sa.UniqueConstraint("project_id", "decision_number", name="uq_decision_number"),
        sa.UniqueConstraint("decision_id", "project_id", name="uq_decision_project"),
        sa.ForeignKeyConstraint(["dimension_code_id", "dimension_category"],
                                ["code_master.code_id", "code_master.category"], name="fk_decision_dimension"),
        sa.ForeignKeyConstraint(["supersedes_decision_id", "project_id"],
                                ["decision.decision_id", "decision.project_id"], name="fk_decision_supersedes"),
        sa.CheckConstraint("btrim(title) <> ''", name="ck_decision_title_not_blank"),
        sa.CheckConstraint("btrim(decision_text) <> ''", name="ck_decision_text_not_blank"),
        sa.CheckConstraint("btrim(alternative_rejected) <> ''", name="ck_decision_alternative_not_blank"),
        sa.CheckConstraint("analysis_code IS NULL OR analysis_code ~ '^[a-z_]{1,40}$'", name="ck_decision_analysis"),
        sa.CheckConstraint("decided_by_user_id = created_by", name="ck_decision_decided_by_recorder"),
        sa.CheckConstraint("decided_on <= (created_at AT TIME ZONE 'UTC')::date + 1", name="ck_decision_not_future"),
        sa.CheckConstraint("supersedes_decision_id IS NULL OR supersedes_decision_id <> decision_id",
                           name="ck_decision_not_self"),
    )
    op.execute("CREATE UNIQUE INDEX uq_decision_superseded_once ON decision (supersedes_decision_id) "
               "WHERE supersedes_decision_id IS NOT NULL")
    op.create_index("ix_decision_log", "decision", ["project_id", "decided_on", "decision_id"])
    for name, col in (("ix_decision_dimension", "dimension_code_id"), ("ix_decision_decided_by", "decided_by_user_id"),
                      ("ix_decision_created_by", "created_by")):
        op.create_index(name, "decision", [col])
    op.execute(REJECT)
    op.execute("CREATE TRIGGER trg_decision_immutable BEFORE UPDATE OR DELETE ON decision "
               "FOR EACH ROW EXECUTE FUNCTION fn_decision_reject()")
    op.execute(STAMP)
    op.execute("CREATE TRIGGER trg_decision_stamp BEFORE INSERT ON decision "
               "FOR EACH ROW EXECUTE FUNCTION fn_decision_stamp()")
    op.execute("REVOKE UPDATE, TRUNCATE ON decision FROM vb_app")


def downgrade() -> None:
    op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM decision) THEN "
               "RAISE EXCEPTION 'decisions exist: downgrade refused; nothing changed'; END IF; END $$")
    op.execute("DROP TRIGGER trg_decision_immutable ON decision")
    op.execute("DROP TRIGGER trg_decision_stamp ON decision")
    op.drop_table("decision")
    op.execute("DROP FUNCTION public.fn_decision_reject()")
    op.execute("DROP FUNCTION public.fn_decision_stamp()")
