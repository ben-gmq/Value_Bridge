"""Slice 16's purge approval reads the grant record (slice17 schema rev 3 §6, §8; spec §10 criterion 5; AR-13, AR-18,
AR-20, AR-24). Paused for Ben: it changes slice 16's four-eyes check — built and tested on throwaway databases only
until he clicks.

fn_project_purge_guard's AR-13 block — which read the approver's latest grant from audit_event, a table whose time and
detail the app role can write — becomes one call of fn_admin_purge_independent (0076): the approver independent of
the requester both ways (creator included, AR-24), and their latest grant at least 30 days old (AR-20). Nothing else in
0072's body changes.

The body is frozen by its SHA-256, not pasted: the migration reads the live function, refuses unless it is exactly
0072's body (0073–0076 never touch it), replaces the one AR-13 block and the two variables it used, and the downgrade
does the reverse under the same check. After 0077 no guard reads audit_event.

Revision ID: 0077
Revises: 0076
"""
import hashlib

from alembic import op
from sqlalchemy import text

revision = "0077"
down_revision = "0076"
branch_labels = None
depends_on = None

SHA_0072 = "9c16d705e49a7856fb638f44fa6388f68b8f537a22a5c41387b40fde7e54db7e"   # sha256 of 0072's prosrc (utf-8)
SHA_0077 = "4c6354f00d11e1876d29770ad4056b4e426725e825ead55fdaf3751dd91aea6d"   # ... and of this migration's

OLD_DECLARE = "DECLARE src project_purge; grant_by bigint; grant_at timestamptz;"
NEW_DECLARE = "DECLARE src project_purge;"
OLD_BLOCK = """            -- AR-13 (Q-93 a, U9): the approver's latest platform-admin grant must be at least 30 days old and not made
            -- by the requester; no grant on record counts as too recent. The setup and CLI admins' creation is their grant.
            SELECT e.app_user_id, e.occurred_at INTO grant_by, grant_at FROM audit_event e
             WHERE e.target_table = 'app_user' AND e.target_id = NEW.approved_by_user_id
               AND e.event_type IN ('PLATFORM_ADMIN_GRANTED', 'FIRST_ADMIN_CREATED', 'ADMIN_CREATED_BY_CLI')
             ORDER BY e.occurred_at DESC, e.audit_event_id DESC LIMIT 1;
            IF grant_at IS NULL OR grant_at > statement_timestamp() - interval '30 days'
               OR grant_by IS NOT DISTINCT FROM OLD.requested_by_user_id THEN
              RAISE EXCEPTION 'the approver''s admin rights must be at least 30 days old and not granted by the '
                'requester (AR-13)' USING ERRCODE = 'restrict_violation';
            END IF;
"""
NEW_BLOCK = """            -- AR-13, AR-18, AR-20, AR-24 (0077): independence and the 30 days, from the grant record alone
            IF NOT public.fn_admin_purge_independent(NEW.approved_by_user_id, OLD.requested_by_user_id) THEN
              RAISE EXCEPTION 'the approver must be independent of the requester and hold admin rights at least 30 '
                'days (AR-13, AR-18, AR-20)' USING ERRCODE = 'restrict_violation';
            END IF;
"""


def _swap(body: str, old_decl: str, new_decl: str, old_block: str, new_block: str) -> str:
    if body.count(old_decl) != 1 or body.count(old_block) != 1:
        raise RuntimeError("0077: the purge guard's AR-13 block is not where 0072 left it")
    return body.replace(old_decl, new_decl).replace(old_block, new_block)


def _sha(body: str) -> str:
    return hashlib.sha256(body.encode()).hexdigest()


def _replace(expect_sha: str, make) -> None:
    conn = op.get_bind()
    body = conn.execute(text("SELECT prosrc FROM pg_proc WHERE proname = 'fn_project_purge_guard'")).scalar_one()
    if _sha(body) != expect_sha:
        raise RuntimeError(f"0077: fn_project_purge_guard is not the body this migration was written against "
                           f"(sha256 {_sha(body)}, expected {expect_sha}) — refusing to replace it")
    new = make(body)
    tag = "$guard$"
    assert tag not in new
    # 0072's header, unchanged: SET search_path pinned as 0072 had it
    op.execute(f"CREATE OR REPLACE FUNCTION fn_project_purge_guard() RETURNS trigger "
               f"LANGUAGE plpgsql SET search_path = pg_catalog, public AS {tag}{new}{tag}")


def upgrade() -> None:
    _replace(SHA_0072, lambda b: _swap(b, OLD_DECLARE, NEW_DECLARE, OLD_BLOCK, NEW_BLOCK))


def downgrade() -> None:
    _replace(SHA_0077, lambda b: _swap(b, NEW_DECLARE, OLD_DECLARE, NEW_BLOCK, OLD_BLOCK))
