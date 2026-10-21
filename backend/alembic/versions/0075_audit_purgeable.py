"""The audit log under a purge (slice16 schema §4, §5, §12.8; spec §18 S8; Q-69 b, AR-3). Paused for Ben: it touches the
audit log's immutability — approved by Ben 2026-10-22 ("yeah, purge migration").

fn_reject_modification_audit_purgeable(), for trg_audit_event_immutable alone: UPDATE always raises; DELETE passes only
when fn_purge_allows (0074) says so for the row's project AND the event is not one of the kept removal events, named
one by one (S8: by name, not by pattern). So the purge removes a project's own audit rows — they carry client text — and
the record of the removal itself survives even a wrong predicate. The removal events are written with no project_id
(services/purge), so a mis-written one blocks the project's own DELETE by FK and the purge rolls back.
FK audit_event → project is kept. fn_reject_modification is untouched.

Downgrade: re-points the trigger to fn_reject_modification — always safe (it only re-arms the guard).

Revision ID: 0075
Revises: 0074
"""
from alembic import op

revision = "0075"
down_revision = "0074"
branch_labels = None
depends_on = None

KEPT = ("PURGE_REQUESTED", "PURGE_APPROVED", "PURGE_CANCELLED", "PURGE_ARCHIVE_WRITTEN", "PROJECT_PURGED",
        "PURGE_KEYS_DESTROYED", "PURGE_ARCHIVE_DELETED")


def _trigger(fn: str) -> None:
    op.execute("DROP TRIGGER trg_audit_event_immutable ON audit_event")
    op.execute(f"CREATE TRIGGER trg_audit_event_immutable BEFORE UPDATE OR DELETE ON audit_event "
               f"FOR EACH ROW EXECUTE FUNCTION {fn}()")


def upgrade() -> None:
    kept = ", ".join(f"'{k}'" for k in KEPT)
    op.execute(f"""
        CREATE FUNCTION public.fn_reject_modification_audit_purgeable() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog, public, pg_temp AS $$
        BEGIN
          IF TG_OP = 'DELETE' AND OLD.event_type NOT IN ({kept})
             AND public.fn_purge_allows(OLD.project_id) THEN
            RETURN OLD;
          END IF;
          RAISE EXCEPTION '% on % is not allowed: the row is immutable', TG_OP, TG_TABLE_NAME
            USING ERRCODE = 'restrict_violation';
        END $$
    """)
    _trigger("fn_reject_modification_audit_purgeable")


def downgrade() -> None:
    _trigger("fn_reject_modification")
    op.execute("DROP FUNCTION fn_reject_modification_audit_purgeable()")
