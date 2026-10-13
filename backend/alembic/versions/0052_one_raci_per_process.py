"""One RACI per process (D-64; docs/slice10d_raci_schema.md §3, §5, Q-1…Q-6; design review 10d round 1).
Runs as vb_owner.

DEPLOY NOTE: stop the API before `alembic upgrade`, start the new code after. 0052 takes bfc_node_org_role in
ACCESS EXCLUSIVE mode, and old code would 500 on a to-be step role once the guard exists. Run
`./venv/bin/python -m scripts.precheck_0052` first: it lists what would stop step 1, read-only.

A to-be process's roles are its requirement's (br_org_role); an as-is process's roles stay on the step
(bfc_node_org_role). In one transaction:

1. Pre-check [Q-5]: a live to-be step role whose step has no live BR stops the migration, listing every such
   step. A BR is never invented.
2. Merge each live to-be step role into its step's live BR. Codes are matched by RESOLVED code and behaviour,
   never the raw raci_code_id: a step row's code resolves to the project's override of that code if one is
   live (services/code_master.resolve), and two codes of the same behaviour count as the same role (DR10d-2).
   Decided in this order:
   - the BR already holds that org role with that behaviour live → `already`;
   - an ACCOUNTABLE when the BR already has a live ACCOUNTABLE for another org role → `conflicts` [Q-2]: the
     BR's wins, nothing copied (decided BEFORE restore/insert, so uq_bror_one_accountable never trips);
   - the BR holds the resolved grain retired → that row is restored → `restored`;
   - otherwise inserted with the resolved code, created_by = the step row's author → `copied`
     (a second step row of the same org role and behaviour joins the first → `already`).
3. Every live to-be step role is retired with one stamp → `retired`. No actor exists in a migration, so
   deleted_by stays NULL, updated_by is untouched, and the audit event carries the provenance (0045 / 0051
   precedent).
4. History [Q-3]: a to-be step role retired by a step retire that still holds (its stamp is a
   STEP_RETIRED_WITH_DEPENDENTS event's, which lists it, and the step is still retired with that stamp) gets a
   RETIRED copy on the event's BR — the BR the event lists whose deleted_at is
   the event's stamp — with the same deleted_at / deleted_by, so undoing that step retire brings the role back
   on the BR (step_retire._same_stamp_links). No such BR → `unplaced`. Same org role and behaviour already on
   that BR with the stamp → `history_already`, not reported (nothing written). Any other row on the full grain (retired rows included, the
   0051 precedent) → `not_carried`. An ACCOUNTABLE when the BR's same-stamp (or live) rows hold one for another
   org role → `conflicts` (kind RETIRED_WITH_STEP): the BR's wins, so the restore brings back exactly one.
5. One RACI_MERGED_TO_BR audit event per project that changed (app_user_id NULL, decision D-64), listing every
   id above. A run that changes nothing writes no event: history rows an earlier 0052 event already reported
   are not reported again. Conflicts are also printed to the migration output.
6. The guard: generated node_live_set ('AS_IS' while live, NULL once retired) + composite FK to
   bfc_node (bfc_node_id, project_id, bfc_set_code), so a live or restored step role exists only on an as-is
   step. Retired rows are not checked (MATCH SIMPLE): history stays as it is. The column is GENERATED, so
   baseline_shadow.snapshot_column_names skips it: no shadow DDL, no hash-spec change (§4).

Re-runnable: after a downgrade no live to-be step role remains and every history copy is already there, so a
second upgrade changes nothing and writes no event.

Downgrade: drops the FK and the column only; it cannot fail. The data merge is NOT undone: no row was deleted,
the step rows are retired and intact, and the audit event holds the full id map. Undoing it automatically could
re-create Accountable conflicts, so that pauses for Ben.

Revision ID: 0052
Revises: 0051
"""
from alembic import op
from sqlalchemy import text

revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None

# A step row's code as code_master.resolve gives it for the row's project: the live project override of the
# same code, else the row's own code.
RESOLVED = """
        JOIN      code_master c ON c.code_id = r.raci_code_id
        LEFT JOIN code_master o ON o.project_id = r.project_id AND o.category = 'RACI_TYPE' AND o.code = c.code
                               AND o.is_active AND o.behaviour_code IS NOT NULL AND o.code_id <> c.code_id"""
RESOLVED_COLS = "coalesce(o.code_id, c.code_id) AS raci_code_id, coalesce(o.behaviour_code, c.behaviour_code) " \
                "AS raci_behaviour"


def upgrade() -> None:
    # DR10d-3: the exclusive lock first, so no writer upgrades a lock half way (and the API is stopped anyway).
    op.execute("LOCK TABLE bfc_node_org_role IN ACCESS EXCLUSIVE MODE")
    op.execute("LOCK TABLE br_org_role, bfc_node IN SHARE ROW EXCLUSIVE MODE")   # no lock upgrade later (sara L1)
    op.execute("LOCK TABLE business_requirement IN SHARE MODE")
    # 1. pre-check [Q-5] (scripts/precheck_0052.py runs the same query read-only)
    op.execute("""
        DO $$ DECLARE bad text; BEGIN
          SELECT string_agg(format('project %s: %s %s (bfc_node_id %s, step roles %s)', project_id, hier_code,
                                   node_name, bfc_node_id, ids), '; ' ORDER BY project_id, hier_code)
          INTO bad
          FROM (SELECT n.project_id, n.hier_code, n.node_name, n.bfc_node_id,
                       string_agg(r.bfc_node_org_role_id::text, ',' ORDER BY r.bfc_node_org_role_id) AS ids
                FROM   bfc_node_org_role r
                JOIN   bfc_node n ON n.bfc_node_id = r.bfc_node_id
                WHERE  r.is_active AND n.bfc_set_code = 'TO_BE'
                  AND  NOT EXISTS (SELECT 1 FROM business_requirement b
                                   WHERE b.bfc_node_id = r.bfc_node_id AND b.is_active)
                GROUP  BY n.project_id, n.hier_code, n.node_name, n.bfc_node_id) s;
          IF bad IS NOT NULL THEN
            RAISE EXCEPTION '0052 stopped (D-64, Q-5): live roles on to-be process steps with no live business '
                            'requirement. Fix these first, a requirement is never invented: %', bad;
          END IF;
        END $$""")
    # 2. merge
    op.execute(f"""
        CREATE TEMP TABLE _raci_merge ON COMMIT DROP AS
        SELECT r.bfc_node_org_role_id AS step_role_id, r.project_id, b.br_id, r.org_role_id, {RESOLVED_COLS},
               r.created_by, NULL::text AS outcome, NULL::bigint AS br_org_role_id
        FROM   bfc_node_org_role r
        JOIN   bfc_node n             ON n.bfc_node_id = r.bfc_node_id
        JOIN   business_requirement b ON b.bfc_node_id = r.bfc_node_id AND b.is_active
        {RESOLVED}
        WHERE  r.is_active AND n.bfc_set_code = 'TO_BE'""")
    op.execute("""
        UPDATE _raci_merge m SET outcome = 'already', br_org_role_id = x.br_org_role_id
        FROM   br_org_role x
        WHERE  x.br_id = m.br_id AND x.org_role_id = m.org_role_id AND x.raci_behaviour = m.raci_behaviour
          AND  x.is_active""")
    op.execute("""
        UPDATE _raci_merge m SET outcome = 'conflict', br_org_role_id = x.br_org_role_id
        FROM   br_org_role x
        WHERE  m.outcome IS NULL AND m.raci_behaviour = 'ACCOUNTABLE'
          AND  x.br_id = m.br_id AND x.is_active AND x.raci_behaviour = 'ACCOUNTABLE'""")
    # the same org role and behaviour twice on one step (two codes of one behaviour): the first one is carried
    op.execute("""
        WITH ranked AS (SELECT step_role_id, row_number() OVER (PARTITION BY br_id, org_role_id, raci_behaviour
                                                                ORDER BY step_role_id) AS n
                        FROM _raci_merge WHERE outcome IS NULL)
        UPDATE _raci_merge m SET outcome = 'duplicate' FROM ranked WHERE ranked.step_role_id = m.step_role_id
          AND ranked.n > 1""")
    op.execute("""
        UPDATE _raci_merge m SET outcome = 'restored', br_org_role_id = x.br_org_role_id
        FROM   br_org_role x
        WHERE  m.outcome IS NULL
          AND  x.br_id = m.br_id AND x.org_role_id = m.org_role_id AND x.raci_code_id = m.raci_code_id
          AND  NOT x.is_active""")
    op.execute("""
        UPDATE br_org_role x SET is_active = true, deleted_at = NULL, deleted_by = NULL, updated_by = NULL,
                                 raci_behaviour = m.raci_behaviour, row_version = x.row_version + 1
        FROM   _raci_merge m
        WHERE  m.outcome = 'restored' AND x.br_org_role_id = m.br_org_role_id""")
    op.execute("""
        WITH ins AS (
            INSERT INTO br_org_role (project_id, br_id, org_role_id, raci_code_id, raci_behaviour, created_by)
            SELECT project_id, br_id, org_role_id, raci_code_id, raci_behaviour, created_by
            FROM   _raci_merge WHERE outcome IS NULL
            ORDER  BY step_role_id
            RETURNING br_org_role_id, br_id, org_role_id, raci_code_id)
        UPDATE _raci_merge m SET outcome = 'copied', br_org_role_id = ins.br_org_role_id
        FROM   ins
        WHERE  m.outcome IS NULL AND ins.br_id = m.br_id AND ins.org_role_id = m.org_role_id
          AND  ins.raci_code_id = m.raci_code_id""")
    op.execute("""
        UPDATE _raci_merge m SET outcome = 'already', br_org_role_id = x.br_org_role_id
        FROM   br_org_role x
        WHERE  m.outcome = 'duplicate' AND x.br_id = m.br_id AND x.org_role_id = m.org_role_id
          AND  x.raci_behaviour = m.raci_behaviour AND x.is_active""")
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM _raci_merge WHERE outcome NOT IN ('already', 'conflict', 'restored', 'copied')
                                                  OR outcome IS NULL OR br_org_role_id IS NULL) THEN
            RAISE EXCEPTION '0052: a to-be step role was neither merged nor named as a conflict';
          END IF;
        END $$""")
    # 3. retire every merged step role, one stamp
    op.execute("""
        UPDATE bfc_node_org_role r SET is_active = false, deleted_at = now(), row_version = r.row_version + 1
        FROM   _raci_merge m
        WHERE  r.bfc_node_org_role_id = m.step_role_id""")
    # 4. history: roles retired with their step become retired rows of the event's BR, same stamp [Q-3]
    op.execute(f"""
        CREATE TEMP TABLE _raci_history ON COMMIT DROP AS
        SELECT DISTINCT ON (r.bfc_node_org_role_id)
               r.bfc_node_org_role_id AS step_role_id, r.project_id, b.br_id, r.org_role_id, {RESOLVED_COLS},
               r.created_by, r.deleted_at, r.deleted_by, NULL::text AS outcome, NULL::bigint AS br_org_role_id
        FROM   bfc_node_org_role r
        JOIN   bfc_node n    ON n.bfc_node_id = r.bfc_node_id AND n.bfc_set_code = 'TO_BE'
                            AND NOT n.is_active AND n.deleted_at = r.deleted_at      -- still retired by it
        JOIN   audit_event e ON e.event_type = 'STEP_RETIRED_WITH_DEPENDENTS'
                            AND e.project_id = r.project_id
                            AND e.target_table = 'bfc_node' AND e.target_id = r.bfc_node_id
                            AND (e.detail ->> 'deleted_at')::timestamptz = r.deleted_at
                            AND e.detail -> 'rows' @> jsonb_build_array(
                                    jsonb_build_array('bfc_node_org_role', r.bfc_node_org_role_id))
        LEFT JOIN business_requirement b
                             ON b.bfc_node_id = r.bfc_node_id AND NOT b.is_active
                            AND b.deleted_at = (e.detail ->> 'deleted_at')::timestamptz
                            AND e.detail -> 'rows' @> jsonb_build_array(
                                    jsonb_build_array('business_requirement', b.br_id))
        {RESOLVED}
        WHERE  NOT r.is_active
        ORDER  BY r.bfc_node_org_role_id, b.br_id NULLS LAST""")
    op.execute("UPDATE _raci_history SET outcome = 'unplaced' WHERE br_id IS NULL")
    op.execute("""
        UPDATE _raci_history h SET outcome = 'already', br_org_role_id = x.br_org_role_id
        FROM   br_org_role x
        WHERE  h.outcome IS NULL AND x.br_id = h.br_id AND x.org_role_id = h.org_role_id
          AND  x.raci_behaviour = h.raci_behaviour AND NOT x.is_active AND x.deleted_at = h.deleted_at""")
    op.execute("""
        UPDATE _raci_history h SET outcome = 'conflict', br_org_role_id = x.br_org_role_id
        FROM   br_org_role x
        WHERE  h.outcome IS NULL AND h.raci_behaviour = 'ACCOUNTABLE'
          AND  x.br_id = h.br_id AND x.raci_behaviour = 'ACCOUNTABLE'
          AND  (x.is_active OR x.deleted_at = h.deleted_at)""")
    op.execute("""
        UPDATE _raci_history h SET outcome = 'not_carried', br_org_role_id = x.br_org_role_id
        FROM   br_org_role x
        WHERE  h.outcome IS NULL AND x.br_id = h.br_id AND x.org_role_id = h.org_role_id
          AND  x.raci_code_id = h.raci_code_id""")
    op.execute("""
        WITH ranked AS (SELECT step_role_id, row_number() OVER (PARTITION BY br_id, org_role_id, raci_behaviour
                                                                ORDER BY step_role_id) AS n
                        FROM _raci_history WHERE outcome IS NULL)
        UPDATE _raci_history h SET outcome = 'already' FROM ranked WHERE ranked.step_role_id = h.step_role_id
          AND ranked.n > 1""")
    op.execute("""
        WITH ins AS (
            INSERT INTO br_org_role (project_id, br_id, org_role_id, raci_code_id, raci_behaviour, created_by,
                                     is_active, deleted_at, deleted_by)
            SELECT h.project_id, h.br_id, h.org_role_id, h.raci_code_id, h.raci_behaviour, h.created_by,
                   false, h.deleted_at, h.deleted_by
            FROM   _raci_history h
            WHERE  h.outcome IS NULL
              AND  NOT EXISTS (SELECT 1 FROM br_org_role x WHERE x.br_id = h.br_id AND x.org_role_id = h.org_role_id
                               AND x.raci_code_id = h.raci_code_id)
            ORDER  BY h.step_role_id
            RETURNING br_org_role_id, br_id, org_role_id, raci_code_id)
        UPDATE _raci_history h SET outcome = 'copied', br_org_role_id = ins.br_org_role_id
        FROM   ins
        WHERE  h.outcome IS NULL AND ins.br_id = h.br_id AND ins.org_role_id = h.org_role_id
          AND  ins.raci_code_id = h.raci_code_id""")
    # an exception row reported by an earlier 0052 run is not news: a re-run must write nothing
    op.execute("""
        DELETE FROM _raci_history h
        WHERE  h.outcome IN ('already', 'unplaced', 'not_carried', 'conflict')
          AND  EXISTS (SELECT 1 FROM audit_event e
                       WHERE e.event_type = 'RACI_MERGED_TO_BR' AND e.project_id = h.project_id
                         AND e.detail -> 'history_reported' @> to_jsonb(h.step_role_id))""")
    op.execute("DELETE FROM _raci_history WHERE outcome = 'already'")     # nothing written, nothing to report
    _print_conflicts()
    # 5. provenance: one event per project that changed
    op.execute("""
        WITH m AS (SELECT project_id,
                          jsonb_agg(jsonb_build_array(step_role_id, br_org_role_id) ORDER BY step_role_id)
                              FILTER (WHERE outcome = 'copied')   AS copied,
                          jsonb_agg(jsonb_build_array(step_role_id, br_org_role_id) ORDER BY step_role_id)
                              FILTER (WHERE outcome = 'restored') AS restored,
                          jsonb_agg(jsonb_build_array(step_role_id, br_org_role_id) ORDER BY step_role_id)
                              FILTER (WHERE outcome = 'already')  AS already,
                          jsonb_agg(jsonb_build_object('kind', 'LIVE', 'step_role_id', step_role_id,
                                                       'br_id', br_id, 'dropped_org_role_id', org_role_id,
                                                       'kept_br_org_role_id', br_org_role_id)
                                    ORDER BY step_role_id) FILTER (WHERE outcome = 'conflict') AS conflicts,
                          jsonb_agg(step_role_id ORDER BY step_role_id) AS retired
                   FROM _raci_merge GROUP BY project_id),
             h AS (SELECT project_id,
                          jsonb_agg(jsonb_build_array(step_role_id, br_org_role_id) ORDER BY step_role_id)
                              FILTER (WHERE outcome = 'copied')      AS history_copied,
                          jsonb_agg(jsonb_build_array(step_role_id, br_org_role_id) ORDER BY step_role_id)
                              FILTER (WHERE outcome = 'not_carried') AS not_carried,
                          jsonb_agg(step_role_id ORDER BY step_role_id)
                              FILTER (WHERE outcome = 'unplaced')    AS unplaced,
                          jsonb_agg(jsonb_build_object('kind', 'RETIRED_WITH_STEP', 'step_role_id', step_role_id,
                                                       'br_id', br_id, 'dropped_org_role_id', org_role_id,
                                                       'kept_br_org_role_id', br_org_role_id)
                                    ORDER BY step_role_id) FILTER (WHERE outcome = 'conflict') AS conflicts,
                          jsonb_agg(step_role_id ORDER BY step_role_id) AS history_reported
                   FROM _raci_history GROUP BY project_id)
        INSERT INTO audit_event (event_type, project_id, target_table, detail)
        SELECT 'RACI_MERGED_TO_BR', p.project_id, 'bfc_node_org_role',
               jsonb_build_object(
                   'decision', 'D-64', 'migration', '0052', 'deleted_at', now(),
                   'copied',    coalesce(m.copied, '[]'),    'restored',  coalesce(m.restored, '[]'),
                   'already',   coalesce(m.already, '[]'),
                   'conflicts', coalesce(m.conflicts, '[]') || coalesce(h.conflicts, '[]'),
                   'retired',   coalesce(m.retired, '[]'),
                   'history_copied',   coalesce(h.history_copied, '[]'),
                   'not_carried',      coalesce(h.not_carried, '[]'),
                   'unplaced',         coalesce(h.unplaced, '[]'),
                   'history_reported', coalesce(h.history_reported, '[]'))
        FROM   (SELECT project_id FROM m UNION SELECT project_id FROM h) p
        LEFT JOIN m ON m.project_id = p.project_id
        LEFT JOIN h ON h.project_id = p.project_id
        ORDER  BY p.project_id""")
    # 6. the guard: a live step role sits on an as-is step only
    op.execute("ALTER TABLE bfc_node_org_role ADD COLUMN node_live_set varchar(10) "
               "GENERATED ALWAYS AS (CASE WHEN is_active THEN 'AS_IS' END) STORED")
    op.execute("ALTER TABLE bfc_node_org_role ADD CONSTRAINT fk_bnor_node_as_is "
               "FOREIGN KEY (bfc_node_id, project_id, node_live_set) "
               "REFERENCES bfc_node (bfc_node_id, project_id, bfc_set_code) ON UPDATE NO ACTION")


def _print_conflicts() -> None:
    """DR10d-7: the Accountables the BR's won over, named for the person running the migration."""
    rows = op.get_bind().execute(text("""
        SELECT x.project_id, b.br_number, kept.org_role_code, dropped.org_role_code, x.kind
        FROM   (SELECT project_id, br_id, org_role_id, br_org_role_id, 'live' AS kind
                FROM _raci_merge WHERE outcome = 'conflict'
                UNION ALL
                SELECT project_id, br_id, org_role_id, br_org_role_id, 'retired with its step'
                FROM _raci_history WHERE outcome = 'conflict') x
        JOIN   business_requirement b ON b.br_id = x.br_id
        JOIN   br_org_role k          ON k.br_org_role_id = x.br_org_role_id
        JOIN   org_role kept          ON kept.org_role_id = k.org_role_id
        JOIN   org_role dropped       ON dropped.org_role_id = x.org_role_id
        ORDER  BY x.project_id, b.br_number""")).all()
    for project_id, br_number, kept, dropped, kind in rows:
        print(f"0052 Accountable conflict (project {project_id}, {kind}): {br_number} keeps {kept}; "
              f"the step's {dropped} was not copied (see audit event RACI_MERGED_TO_BR)")


def downgrade() -> None:
    # The guard only. The merge stays: rows were moved and retired, never deleted (see the module docstring).
    op.execute("ALTER TABLE bfc_node_org_role DROP CONSTRAINT IF EXISTS fk_bnor_node_as_is")
    op.execute("ALTER TABLE bfc_node_org_role DROP COLUMN IF EXISTS node_live_set")
