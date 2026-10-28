"""Approvers required — a per-installation setting, 2 or 1 (docs/approvers_setting_spec.md; Ben 2026-10-24, his own
change to Q-67…Q-85 and AR-18…AR-24). Paused for Ben before any non-throwaway database: it changes the four-eyes checks
of removals (slice 16) and admin grants (slice 17).

- vb_instance gains installation_kind (NULL = undeclared, read as SHARED) and approvers_required (default 2). 1 is
  allowed only on a LOCAL_SINGLE_OWNER installation (a NULL-safe CHECK); the kind is one-way (SHARED stays SHARED); a
  re-stamp puts the setting back to 2; only the owner writes it, naming an operator; every change is a row in the
  append-only vb_instance_setting_log.
- fn_approvers_required() is the one reader: 1 only for a LOCAL_SINGLE_OWNER installation set to 1; anything else,
  including no row, is 2 (fails closed).
- project_purge and platform_admin_grant gain approved_single_owner, set only by their guards at approval. Their
  four-eyes CHECKs accept the same admin only on a row so flagged. Under 2 every check is exactly as before; under 1 the
  same live admin may request and approve (the 30-day rule on the approver stays, A-Q1), and an approval made alone
  can never run once the setting is back at 2 (A-Q5). The 24-hour wait, live-admin checks, a target never approving
  their own grant, LEGACY / BOOTSTRAP and the owner-only DELETE path are untouched.

Every changed function body is frozen by its SHA-256 and changed by exact swaps that must match once (0077's pattern);
the downgrade does the reverse under the new hashes, and refuses once anything was approved alone or the setting was 1.

Revision ID: 0079
Revises: 0078
"""
import hashlib

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision = "0079"
down_revision = "0078"
branch_labels = None
depends_on = None

PURGE_HDR = "LANGUAGE plpgsql SET search_path = pg_catalog, public"
GRANT_HDR = "LANGUAGE plpgsql SET search_path = pg_catalog, public, pg_temp"
SQL_HDR = "LANGUAGE sql STABLE SET search_path = pg_catalog, public, pg_temp"

# ---- fn_project_purge_guard (0077's body) ----------------------------------------------------------------------------
PURGE_SWAPS = [
    ("DECLARE src project_purge;",
     "DECLARE src project_purge; quorum smallint := public.fn_approvers_required();"),
    (">= 2 THEN\n              RAISE EXCEPTION 'a purge needs at least two live",
     ">= quorum THEN\n              RAISE EXCEPTION 'a purge needs at least two live"),
    ("            NEW.requested_at := statement_timestamp();\n            RETURN NEW;",
     "            NEW.requested_at := statement_timestamp();\n            NEW.approved_single_owner := false;\n"
     "            RETURN NEW;"),
    ("            IF NEW.approved_by_user_id = OLD.requested_by_user_id THEN",
     "            IF quorum = 2 AND NEW.approved_by_user_id = OLD.requested_by_user_id THEN"),
    (">= 2 THEN\n              RAISE EXCEPTION 'an open request is approved once",
     ">= quorum THEN\n              RAISE EXCEPTION 'an open request is approved once"),
    ("            IF NOT public.fn_admin_purge_independent(NEW.approved_by_user_id, OLD.requested_by_user_id) THEN",
     "            IF (quorum = 2 AND NOT public.fn_admin_purge_independent(NEW.approved_by_user_id, "
     "OLD.requested_by_user_id))\n"
     "               OR (quorum = 1 AND NOT public.fn_admin_rights_aged(NEW.approved_by_user_id)) THEN"),
    ("            NEW.approved_at := statement_timestamp();\n"
     "          ELSIF (NEW.approved_at IS DISTINCT FROM OLD.approved_at OR NEW.approved_by_user_id IS DISTINCT FROM "
     "OLD.approved_by_user_id) THEN",
     "            NEW.approved_at := statement_timestamp();\n"
     "            NEW.approved_single_owner := (quorum = 1);\n"
     "          ELSIF (NEW.approved_at IS DISTINCT FROM OLD.approved_at OR NEW.approved_by_user_id IS DISTINCT FROM "
     "OLD.approved_by_user_id OR NEW.approved_single_owner IS DISTINCT FROM OLD.approved_single_owner) THEN"),
    (">= 2 THEN                                              -- sara H1: before the vault",
     ">= quorum\n               OR (OLD.approved_single_owner AND quorum = 2) THEN       -- sara H1: before the vault"),
    (">= 2 THEN\n              RAISE EXCEPTION 'execution needs",
     ">= quorum\n               OR (OLD.approved_single_owner AND quorum = 2) THEN\n"
     "              RAISE EXCEPTION 'execution needs"),
]

# ---- fn_platform_admin_grant_guard (0076's body) ---------------------------------------------------------------------
GRANT_SWAPS = [
    ("DECLARE t public.app_user;",
     "DECLARE t public.app_user; quorum smallint := public.fn_approvers_required();"),
    ("      IF TG_OP = 'INSERT' THEN\n        NEW.recorded_at := statement_timestamp();",
     "      IF TG_OP = 'INSERT' THEN\n        NEW.recorded_at := statement_timestamp();\n"
     "        NEW.approved_single_owner := false;"),
    ("          IF t.created_by = NEW.requested_by_user_id THEN\n"
     "            RAISE EXCEPTION 'an admin cannot ask for admin rights for an account they created (AR-24)'\n"
     "              USING ERRCODE = 'restrict_violation';\n          END IF;\n"
     "          NEW.requested_at := statement_timestamp();\n        ELSIF NEW.grant_origin = 'BOOTSTRAP' THEN",
     "          IF quorum = 2 AND t.created_by = NEW.requested_by_user_id THEN\n"
     "            RAISE EXCEPTION 'an admin cannot ask for admin rights for an account they created (AR-24)'\n"
     "              USING ERRCODE = 'restrict_violation';\n          END IF;\n"
     "          NEW.requested_at := statement_timestamp();\n        ELSIF NEW.grant_origin = 'BOOTSTRAP' THEN"),
    ("        IF NEW.approved_by_user_id IN (OLD.requested_by_user_id, OLD.target_user_id) THEN",
     "        IF NEW.approved_by_user_id = OLD.target_user_id\n"
     "           OR (quorum = 2 AND NEW.approved_by_user_id = OLD.requested_by_user_id) THEN"),
    ("        IF t.created_by = NEW.approved_by_user_id THEN",
     "        IF quorum = 2 AND t.created_by = NEW.approved_by_user_id THEN"),
    ("        IF NOT public.fn_admin_grant_independent(NEW.approved_by_user_id, OLD.requested_by_user_id) THEN",
     "        IF quorum = 2 AND NOT public.fn_admin_grant_independent(NEW.approved_by_user_id, "
     "OLD.requested_by_user_id) THEN"),
    ("        NEW.approved_xact := pg_current_xact_id();\n      ELSIF NEW.rejected_by_user_id IS NOT NULL THEN",
     "        NEW.approved_xact := pg_current_xact_id();\n        NEW.approved_single_owner := (quorum = 1);\n"
     "      ELSIF NEW.rejected_by_user_id IS NOT NULL THEN"),
    ("OR NEW.approved_xact IS DISTINCT FROM OLD.approved_xact OR",
     "OR NEW.approved_xact IS DISTINCT FROM OLD.approved_xact OR NEW.approved_single_owner IS DISTINCT FROM "
     "OLD.approved_single_owner OR"),
]

# ---- fn_vb_instance_guard (0069's body) ------------------------------------------------------------------------------
INSTANCE_SWAPS = [
    ("          IF TG_OP = 'UPDATE' AND (NEW.instance_id = OLD.instance_id\n"
     "               OR NEW.prior_instance_ids IS DISTINCT FROM OLD.prior_instance_ids || OLD.instance_id::text) THEN\n"
     "            RAISE EXCEPTION 'a re-stamp changes the instance id and appends the old one to prior_instance_ids'\n"
     "              USING ERRCODE = 'restrict_violation';\n          END IF;",
     "          IF session_user <> 'vb_owner' OR current_user <> 'vb_owner' THEN                -- 0079\n"
     "            RAISE EXCEPTION 'only the owner writes this database''s identity and approval setting'\n"
     "              USING ERRCODE = 'restrict_violation';\n          END IF;\n"
     "          IF TG_OP = 'UPDATE' AND NEW.instance_id = OLD.instance_id THEN                  -- 0079: the setting\n"
     "            IF NEW.prior_instance_ids IS DISTINCT FROM OLD.prior_instance_ids THEN\n"
     "              RAISE EXCEPTION 'a re-stamp changes the instance id and appends the old one to prior_instance_ids'\n"
     "                USING ERRCODE = 'restrict_violation';\n"
     "            END IF;\n"
     "            IF NULLIF(btrim(current_setting('vb.operator', true)), '') IS NULL THEN\n"
     "              RAISE EXCEPTION 'a change of the approval setting names its operator'\n"
     "                USING ERRCODE = 'restrict_violation';\n            END IF;\n"
     "            IF (OLD.installation_kind = 'SHARED' AND NEW.installation_kind IS DISTINCT FROM 'SHARED')\n"
     "               OR (OLD.installation_kind IS NOT NULL AND NEW.installation_kind IS NULL) THEN\n"
     "              RAISE EXCEPTION 'a shared installation stays shared, and a declared kind is never undeclared'\n"
     "                USING ERRCODE = 'restrict_violation';\n            END IF;\n"
     "            IF OLD.installation_kind = 'LOCAL_SINGLE_OWNER' AND NEW.installation_kind = 'SHARED' THEN\n"
     "              NEW.approvers_required := 2;                                    -- going shared forces two\n"
     "            END IF;\n"
     "            NEW.stamped_at := OLD.stamped_at;\n            RETURN NEW;\n          END IF;\n"
     "          IF TG_OP = 'UPDATE' AND NEW.prior_instance_ids IS DISTINCT FROM OLD.prior_instance_ids "
     "|| OLD.instance_id::text THEN\n"
     "            RAISE EXCEPTION 'a re-stamp changes the instance id and appends the old one to prior_instance_ids'\n"
     "              USING ERRCODE = 'restrict_violation';\n          END IF;\n"
     "          IF TG_OP = 'UPDATE' AND NEW.installation_kind IS DISTINCT FROM OLD.installation_kind THEN\n"
     "            RAISE EXCEPTION 'a re-stamp keeps the installation kind' USING ERRCODE = 'restrict_violation';\n"
     "          END IF;\n"
     "          NEW.approvers_required := 2;                    -- 0079: a first stamp and a re-stamp start at two"),
]

# ---- fn_purge_allows (0074's body) and fn_admin_purge_independent (0076's body) ---------------------------------------
ALLOWS_SWAPS = [
    ("AND (pp.purge_kind = 'DELETE' OR pp.archive_object_name IS NOT NULL))",
     "AND (pp.purge_kind = 'DELETE' OR pp.archive_object_name IS NOT NULL)\n"
     "                      AND (NOT pp.approved_single_owner OR public.fn_approvers_required() = 1))"),
]
AGED = """COALESCE((SELECT g.approved_at <= statement_timestamp() - interval '30 days'
                         FROM public.platform_admin_grant g
                        WHERE g.target_user_id = p_approver AND g.approved_at IS NOT NULL
                        ORDER BY g.approved_at DESC, g.platform_admin_grant_id DESC
                        LIMIT 1), false)"""
INDEPENDENT_SWAPS = [("AND " + AGED, "AND public.fn_admin_rights_aged(p_approver)")]

FUNCTIONS = [  # name, signature, header, sha before, sha after, swaps
    ("fn_project_purge_guard", "()", "RETURNS trigger " + PURGE_HDR,
     "4c6354f00d11e1876d29770ad4056b4e426725e825ead55fdaf3751dd91aea6d", "SHA_PURGE_0079", PURGE_SWAPS),
    ("fn_platform_admin_grant_guard", "()", "RETURNS trigger " + GRANT_HDR,
     "2a44a350980b9ba98f33f340ce8d2d3f4906373eba7e4233ada3a492d2ffddfa", "SHA_GRANT_0079", GRANT_SWAPS),
    ("fn_vb_instance_guard", "()", "RETURNS trigger " + PURGE_HDR,
     "334a51cd5880d8ff36f070cda4d5b70df710fc5169bbdc986f4d294cc999269b", "SHA_INSTANCE_0079", INSTANCE_SWAPS),
    ("fn_purge_allows", "(p_project_id bigint)", "RETURNS boolean " + SQL_HDR,
     "2cf08a6be18fd8e7dcec8d34e3a960d1a7a65dc6c55bfa67837fac31f1a2a848", "SHA_ALLOWS_0079", ALLOWS_SWAPS),
    ("fn_admin_purge_independent", "(p_approver bigint, p_requester bigint)", "RETURNS boolean " + SQL_HDR,
     "3c24b4d5b0fb1dc0f3d74d08e0e06061ee71d33893c0721394a2638512fbd43c", "SHA_INDEPENDENT_0079", INDEPENDENT_SWAPS),
]
NEW_SHAS = {   # the bodies these swaps produce (tests/test_migration_0079.py re-derives them from the database)
    "SHA_PURGE_0079": "4213b1c931470c28816311bfda7505feca6bbd26f3701ff9259f0294b661b214",
    "SHA_GRANT_0079": "576e1ea4162600711152c1ad5a4cd077b808607cb49d20876468e8c739aeffa0",
    "SHA_INSTANCE_0079": "29f66b2a7f8fcdf7d5ad8e1f9630ed0410c67184bf7ae29d48986fa86eaa762f",
    "SHA_ALLOWS_0079": "fd4d7e69e447ddaa171ad50a0ccf56297472a90a7655b9bcf77fb19833bd8029",
    "SHA_INDEPENDENT_0079": "528e2ddd0f99ffc946f574248d0dd6e442736b1a71675121dbe0a3ba8d774309",
}


def sha(body: str) -> str:
    return hashlib.sha256(body.encode()).hexdigest()


def swap(name: str, body: str, swaps: list[tuple[str, str]], forward: bool = True) -> str:
    for old, new in swaps if forward else [(n, o) for o, n in reversed(swaps)]:
        if body.count(old) != 1:
            raise RuntimeError(f"0079: {name} does not hold this block exactly once — refusing to change it: {old[:60]!r}")
        body = body.replace(old, new)
    return body


def _rewrite(forward: bool) -> None:
    conn = op.get_bind()
    for name, sig, header, before, after_key, swaps in FUNCTIONS:
        body = conn.execute(text("SELECT prosrc FROM pg_proc WHERE proname = :n"), {"n": name}).scalar_one()
        expect = before if forward else NEW_SHAS[after_key]
        if sha(body) != expect:
            raise RuntimeError(f"0079: {name} is not the body this migration was written against "
                               f"(sha256 {sha(body)}, expected {expect}) — refusing to replace it")
        new = swap(name, body, swaps, forward)
        tag = "$vb0079$"
        assert tag not in new
        op.execute(f"CREATE OR REPLACE FUNCTION public.{name}{sig} {header} AS {tag}{new}{tag}")


def upgrade() -> None:
    op.add_column("vb_instance", sa.Column("installation_kind", sa.String(20)))
    op.add_column("vb_instance", sa.Column("approvers_required", sa.SmallInteger, nullable=False, server_default="2"))
    op.create_check_constraint("ck_vi_kind", "vb_instance",
                               "installation_kind IS NULL OR installation_kind IN ('SHARED', 'LOCAL_SINGLE_OWNER')")
    op.create_check_constraint("ck_vi_approvers", "vb_instance",
                               "approvers_required IN (1, 2) AND (approvers_required = 2 OR "
                               "installation_kind IS NOT DISTINCT FROM 'LOCAL_SINGLE_OWNER')")

    op.create_table(
        "vb_instance_setting_log",
        sa.Column("vb_instance_setting_log_id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("kind_from", sa.String(20)), sa.Column("kind_to", sa.String(20)),
        sa.Column("approvers_from", sa.SmallInteger), sa.Column("approvers_to", sa.SmallInteger, nullable=False),
        sa.Column("operator_name", sa.Text), sa.Column("db_session_user", sa.Text, nullable=False),
    )
    op.execute("""
    CREATE FUNCTION public.fn_vb_instance_setting_log_guard() RETURNS trigger
    LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
    BEGIN
      RAISE EXCEPTION 'vb_instance_setting_log is append-only' USING ERRCODE = 'restrict_violation';
    END $$""")
    op.execute("CREATE TRIGGER trg_vb_instance_setting_log_guard BEFORE UPDATE OR DELETE ON vb_instance_setting_log "
               "FOR EACH ROW EXECUTE FUNCTION fn_vb_instance_setting_log_guard()")
    op.execute("""
    CREATE FUNCTION public.fn_vb_instance_log_setting() RETURNS trigger
    LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
    BEGIN
      IF TG_OP = 'INSERT' OR NEW.installation_kind IS DISTINCT FROM OLD.installation_kind
         OR NEW.approvers_required IS DISTINCT FROM OLD.approvers_required THEN
        INSERT INTO public.vb_instance_setting_log (kind_from, kind_to, approvers_from, approvers_to, operator_name,
                                                    db_session_user)
        VALUES (CASE WHEN TG_OP = 'UPDATE' THEN OLD.installation_kind END, NEW.installation_kind,
                CASE WHEN TG_OP = 'UPDATE' THEN OLD.approvers_required END, NEW.approvers_required,
                NULLIF(btrim(current_setting('vb.operator', true)), ''), session_user);
      END IF;
      RETURN NULL;
    END $$""")
    op.execute("CREATE TRIGGER trg_vb_instance_log_setting AFTER INSERT OR UPDATE ON vb_instance "
               "FOR EACH ROW EXECUTE FUNCTION fn_vb_instance_log_setting()")
    # the default privileges would give the app INSERT / UPDATE on a new table: it may only read the log (0069's way)
    op.execute("REVOKE ALL ON vb_instance_setting_log FROM vb_app")
    op.execute("GRANT SELECT ON vb_instance_setting_log TO vb_app")

    op.execute(f"""
    CREATE FUNCTION public.fn_approvers_required() RETURNS smallint {SQL_HDR} AS $$
      SELECT COALESCE((SELECT CASE WHEN v.installation_kind = 'LOCAL_SINGLE_OWNER' AND v.approvers_required = 1
                                   THEN 1 ELSE 2 END
                         FROM public.vb_instance v WHERE v.one_row), 2)::smallint $$""")
    op.execute(f"""
    CREATE FUNCTION public.fn_admin_rights_aged(p_approver bigint) RETURNS boolean {SQL_HDR} AS $$
      -- AR-20: the approver's latest grant at least 30 days old; never NULL
      SELECT {AGED} $$""")

    for table, ck_old, ck_new, ck_flag in (
        ("project_purge", "ck_pp_four_eyes",
         "approved_by_user_id <> requested_by_user_id OR approved_single_owner",
         "NOT approved_single_owner OR approved_at IS NOT NULL"),
        ("platform_admin_grant", "ck_pag_four_eyes",
         "(approved_by_user_id <> requested_by_user_id OR approved_single_owner) AND approved_by_user_id <> "
         "target_user_id AND requested_by_user_id <> target_user_id",
         "NOT approved_single_owner OR (grant_origin = 'REQUEST' AND approved_at IS NOT NULL)")):
        op.add_column(table, sa.Column("approved_single_owner", sa.Boolean, nullable=False, server_default="false"))
        op.drop_constraint(ck_old, table, type_="check")
        op.create_check_constraint(ck_old, table, ck_new)
        op.create_check_constraint(ck_old.replace("four_eyes", "single_owner"), table, ck_flag)

    _rewrite(forward=True)


def downgrade() -> None:
    conn = op.get_bind()
    alone = conn.execute(text(
        "SELECT (SELECT count(*) FROM project_purge WHERE approved_single_owner) "
        "+ (SELECT count(*) FROM platform_admin_grant WHERE approved_single_owner) "
        "+ (SELECT count(*) FROM vb_instance WHERE approvers_required = 1) "
        "+ (SELECT count(*) FROM vb_instance_setting_log WHERE approvers_to = 1)")).scalar_one()
    if alone:
        raise RuntimeError("0079 downgrade refused: something was approved alone, or the setting was 1 — the "
                           "restored two-admin checks would not hold for those rows, and the record of it would go")
    _rewrite(forward=False)
    for table, ck in (("project_purge", "ck_pp"), ("platform_admin_grant", "ck_pag")):
        op.drop_constraint(f"{ck}_single_owner", table, type_="check")
        op.drop_constraint(f"{ck}_four_eyes", table, type_="check")
        op.drop_column(table, "approved_single_owner")
    op.create_check_constraint("ck_pp_four_eyes", "project_purge", "approved_by_user_id <> requested_by_user_id")
    op.create_check_constraint("ck_pag_four_eyes", "platform_admin_grant",
                               "approved_by_user_id <> requested_by_user_id AND approved_by_user_id <> target_user_id "
                               "AND requested_by_user_id <> target_user_id")
    op.execute("DROP FUNCTION fn_admin_rights_aged(bigint)")
    op.execute("DROP FUNCTION fn_approvers_required()")
    op.execute("DROP TRIGGER trg_vb_instance_log_setting ON vb_instance")
    op.execute("DROP FUNCTION fn_vb_instance_log_setting()")
    op.drop_table("vb_instance_setting_log")
    op.execute("DROP FUNCTION fn_vb_instance_setting_log_guard()")
    op.drop_constraint("ck_vi_approvers", "vb_instance", type_="check")
    op.drop_constraint("ck_vi_kind", "vb_instance", type_="check")
    op.drop_column("vb_instance", "approvers_required")
    op.drop_column("vb_instance", "installation_kind")
