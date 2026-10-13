"""Backfill br_function_requirement from today's derived paths, then re-base v_br_function_requirement on the
direct link (D-52; docs/slice10b_schema.md §3.1, §3.2, §3.4, §6.1, §9). Runs as vb_owner.

1. Live paths [Q-7]: one link per live BR_SOLUTION → SOLUTION → FR path — exactly the rows the 0024 view
   returns. created_by = the BR_SOLUTION's author, coverage_note NULL. Asserted: after the insert, every pair the
   old view returned has a link row (live, or unlinked on purpose after an earlier run). OLD_PAIRS adds
   br.is_active to the 0024 view's joins; the two are equal because brsol_under_inactive forbids a live pairing
   under a retired BR.
2. Step-retired paths [Q-8]: a br_solution row retired by a step retire (stamped with the deleted_at of a
   STEP_RETIRED_WITH_DEPENDENTS event that lists it) gives a RETIRED link for each live FR tagged with its
   solution, stamped with the same deleted_at / deleted_by, so undoing that step retire brings the links back.
3. One BR_FR_BACKFILLED audit event per project that received rows, listing them (app_user_id NULL).
4. The view now reads the direct link only, with three appended columns (CREATE OR REPLACE keeps
   v_interface_list valid).

Re-runnable: the tables are locked in SHARE mode first, and only pairs with no link yet are inserted, so a
re-upgrade after a downgrade neither duplicates rows nor writes a second event for the same rows.

Downgrade: restores the 0024 body (with the three appended columns kept as NULLs — a replaced view cannot drop
columns while v_interface_list depends on it). The backfilled rows stay; 0049's downgrade removes them, so this
revision never hard-deletes on its own.

Revision ID: 0051
Revises: 0050
"""
from alembic import op

revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None

OLD_PAIRS = """
        SELECT bs.project_id, bs.br_id, fr.fr_id
        FROM   br_solution bs
        JOIN   solution s              ON s.solution_id = bs.solution_id
        JOIN   function_requirement fr ON fr.solution_id = bs.solution_id
        JOIN   business_requirement br ON br.br_id = bs.br_id
        WHERE  bs.is_active AND s.is_active AND fr.is_active AND br.is_active"""


def upgrade() -> None:
    op.execute("LOCK TABLE br_solution, solution, function_requirement, business_requirement IN SHARE MODE")
    op.execute("CREATE TEMP TABLE _brfr_backfill (link_id bigint, project_id bigint, live boolean) ON COMMIT DROP")
    # 1. live paths (the old view's row set; read before the view is replaced)
    op.execute(f"""
        WITH old AS ({OLD_PAIRS}),
        ins AS (
            INSERT INTO br_function_requirement (project_id, br_id, fr_id, coverage_note, created_by)
            SELECT bs.project_id, bs.br_id, fr.fr_id, NULL, bs.created_by
            FROM   br_solution bs
            JOIN   solution s              ON s.solution_id = bs.solution_id
            JOIN   function_requirement fr ON fr.solution_id = bs.solution_id
            JOIN   business_requirement br ON br.br_id = bs.br_id
            WHERE  bs.is_active AND s.is_active AND fr.is_active AND br.is_active
              AND  NOT EXISTS (SELECT 1 FROM br_function_requirement l
                               WHERE l.br_id = bs.br_id AND l.fr_id = fr.fr_id)
            RETURNING br_function_requirement_id, project_id)
        INSERT INTO _brfr_backfill SELECT br_function_requirement_id, project_id, true FROM ins""")
    op.execute(f"""
        DO $$ DECLARE expected bigint; covered bigint; BEGIN
          SELECT count(*) INTO expected FROM ({OLD_PAIRS}) o;
          SELECT count(*) INTO covered FROM ({OLD_PAIRS}) o
          WHERE EXISTS (SELECT 1 FROM br_function_requirement l
                        WHERE l.br_id = o.br_id AND l.fr_id = o.fr_id);   -- a dead row is a decision, not a loss
          IF covered <> expected THEN
            RAISE EXCEPTION 'backfill covers % of % derived BR-FR paths', covered, expected;
          END IF;
        END $$""")
    # 2. paths a step retire took with it: retired links with the same stamp
    op.execute("""
        WITH ins AS (
            INSERT INTO br_function_requirement (project_id, br_id, fr_id, coverage_note, created_by,
                                                 is_active, deleted_at, deleted_by)
            SELECT DISTINCT ON (bs.br_id, fr.fr_id)
                   bs.project_id, bs.br_id, fr.fr_id, NULL, bs.created_by, false, bs.deleted_at, bs.deleted_by
            FROM   br_solution bs
            JOIN   function_requirement fr ON fr.solution_id = bs.solution_id AND fr.is_active
            WHERE  NOT bs.is_active
              AND  EXISTS (SELECT 1 FROM audit_event e
                           WHERE e.event_type = 'STEP_RETIRED_WITH_DEPENDENTS'
                             AND e.project_id = bs.project_id
                             AND (e.detail ->> 'deleted_at')::timestamptz = bs.deleted_at
                             AND e.detail -> 'rows' @> jsonb_build_array(
                                     jsonb_build_array('br_solution', bs.br_solution_id)))
              AND  NOT EXISTS (SELECT 1 FROM br_function_requirement l
                               WHERE l.br_id = bs.br_id AND l.fr_id = fr.fr_id)
            ORDER  BY bs.br_id, fr.fr_id, bs.deleted_at DESC
            RETURNING br_function_requirement_id, project_id)
        INSERT INTO _brfr_backfill SELECT br_function_requirement_id, project_id, false FROM ins""")
    # 3. provenance: one event per project that received rows
    op.execute("""
        INSERT INTO audit_event (event_type, project_id, target_table, detail)
        SELECT 'BR_FR_BACKFILLED', project_id, 'br_function_requirement',
               jsonb_build_object('count', count(*), 'live', count(*) FILTER (WHERE live),
                                  'retired_with_step', count(*) FILTER (WHERE NOT live),
                                  'link_ids', jsonb_agg(link_id ORDER BY link_id),
                                  'decision', 'D-52', 'migration', '0051')
        FROM _brfr_backfill GROUP BY project_id""")
    # 4. the view reads the direct link only [Q-16]
    op.execute("""
        CREATE OR REPLACE VIEW v_br_function_requirement WITH (security_invoker = true) AS
        SELECT l.project_id,
               l.br_id,
               fr.fr_id,
               fr.fr_number,
               fr.fr_type_code_id,
               fr.fr_type_behaviour,
               s.solution_id,
               s.category_code_id AS solution_category_code_id,
               l.br_function_requirement_id,
               l.coverage_note,
               EXISTS (SELECT 1 FROM br_solution bs
                       WHERE bs.br_id = l.br_id AND bs.solution_id = s.solution_id AND bs.is_active) AS tag_answers_br
        FROM   br_function_requirement l
        JOIN   function_requirement fr ON fr.fr_id = l.fr_id
        JOIN   business_requirement br ON br.br_id = l.br_id
        LEFT JOIN solution s           ON s.solution_id = fr.solution_id AND s.is_active
        WHERE  l.is_active AND fr.is_active AND br.is_active
    """)
    op.execute("REVOKE INSERT, UPDATE ON v_br_function_requirement FROM vb_app")


def downgrade() -> None:
    op.execute("""
        CREATE OR REPLACE VIEW v_br_function_requirement WITH (security_invoker = true) AS
        SELECT bs.project_id,
               bs.br_id,
               fr.fr_id,
               fr.fr_number,
               fr.fr_type_code_id,
               fr.fr_type_behaviour,
               s.solution_id,
               s.category_code_id AS solution_category_code_id,
               NULL::bigint  AS br_function_requirement_id,
               NULL::text    AS coverage_note,
               NULL::boolean AS tag_answers_br
        FROM   br_solution bs
        JOIN   solution s              ON s.solution_id = bs.solution_id
        JOIN   function_requirement fr ON fr.solution_id = s.solution_id
        WHERE  bs.is_active AND s.is_active AND fr.is_active
    """)
    op.execute("REVOKE INSERT, UPDATE ON v_br_function_requirement FROM vb_app")
