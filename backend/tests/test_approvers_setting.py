"""Approvers required — a per-installation setting (migration 0079; docs/approvers_setting_spec.md; Ben 2026-10-24).
Grade 1: it relaxes a permission gate and a data-destroying path, so every rule is proven at the database with its
refusal seen — the setting fails closed to two, only the owner naming an operator moves it, a shared installation stays
shared, every change is logged, an approval made alone is flagged and cannot run once the setting is back at two — and
under two nothing changes (the slice 16 and 17 four-eyes suites run unchanged beside this file)."""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from database import engine as app_engine
from database import SessionLocal
from models import AppUser
from services import admin_grant, instance, purge_run
from tests.admin_team import seed_bootstrap
from tests.test_project_purge_record import INSERT, backdate, owner, promote, refused, request, run, two  # noqa: F401

APPROVE = "UPDATE project_purge SET approved_at = now(), approved_by_user_id = :u WHERE project_purge_id = :pp"


def stamp(owner):
    run(owner, "INSERT INTO vb_instance (instance_id) VALUES ('test-a')")


def settings(eng, kind=None, n=None, operator="IS test"):
    with eng.begin() as c:
        if operator:
            c.execute(text("SELECT set_config('vb.operator', :o, true)"), {"o": operator})
        if kind is not None:
            c.execute(text("UPDATE vb_instance SET installation_kind = :k"), {"k": kind})
        if n is not None:
            c.execute(text("UPDATE vb_instance SET approvers_required = :n"), {"n": n})


def settings_refused(eng, **kw) -> str:
    with pytest.raises(DBAPIError) as e:
        settings(eng, **kw)
    return str(e.value.orig)


def quorum(eng) -> int:
    return run(eng, "SELECT public.fn_approvers_required()")[0]


def single_owner(owner):
    stamp(owner)
    settings(owner, kind="LOCAL_SINGLE_OWNER")
    settings(owner, n=1)


def age_grant(owner, uid, days=31):
    """Test-only: the admin's grant approved `days` ago (the guard forces the time on every approval)."""
    run(owner, "ALTER TABLE platform_admin_grant DISABLE TRIGGER trg_platform_admin_grant_guard")
    try:
        run(owner, f"UPDATE platform_admin_grant SET approved_at = now() - interval '{days} days' "
                   "WHERE target_user_id = :u", u=uid)
    finally:
        run(owner, "ALTER TABLE platform_admin_grant ENABLE TRIGGER trg_platform_admin_grant_guard")


def test_the_setting_fails_closed_to_two_and_one_needs_a_declared_single_owner_installation(owner):
    """Acceptance 1 and 7 (spec): no row, an undeclared kind and SHARED all read 2; 1 is refused on each; SHARED never
    becomes LOCAL; only a LOCAL_SINGLE_OWNER installation set to 1 reads 1."""
    assert quorum(owner) == 2                                                            # not even stamped
    stamp(owner)
    assert quorum(owner) == 2
    assert "ck_vi_approvers" in settings_refused(owner, n=1)                             # undeclared: the NULL-safe CHECK
    settings(owner, kind="SHARED")
    assert "ck_vi_approvers" in settings_refused(owner, n=1)
    assert "stays shared" in settings_refused(owner, kind="LOCAL_SINGLE_OWNER")          # A-Q4: one-way
    assert quorum(owner) == 2


def test_a_local_installation_reads_one_only_once_set_and_going_shared_or_restamping_puts_it_back_to_two(owner):
    single_owner(owner)
    assert quorum(owner) == 1
    settings(owner, kind="SHARED")                                                       # LOCAL → SHARED forces two
    assert quorum(owner) == 2 and run(owner, "SELECT approvers_required FROM vb_instance")[0] == 2
    assert "stays shared" in settings_refused(owner, kind="LOCAL_SINGLE_OWNER")
    assert "never undeclared" in refused(owner, "SELECT set_config('vb.operator', 'IS test', true); "
                                                "UPDATE vb_instance SET installation_kind = NULL")


def test_a_restamp_keeps_the_kind_and_resets_the_setting_to_two(owner):
    single_owner(owner)
    run(owner, "UPDATE vb_instance SET instance_id = 'test-b', prior_instance_ids = prior_instance_ids || 'test-a'::text")
    assert run(owner, "SELECT installation_kind, approvers_required FROM vb_instance") == ("LOCAL_SINGLE_OWNER", 2)
    assert quorum(owner) == 2


def test_only_the_owner_naming_an_operator_changes_it_and_every_change_is_one_log_row(owner):
    """Acceptance 2: the app role cannot write it; the owner must name an operator; the log is append-only."""
    stamp(owner)
    assert "permission denied" in settings_refused(app_engine, kind="LOCAL_SINGLE_OWNER")
    assert "names its operator" in settings_refused(owner, kind="LOCAL_SINGLE_OWNER", operator=None)
    settings(owner, kind="LOCAL_SINGLE_OWNER", operator="Ben (owner)")
    settings(owner, n=1, operator="Ben (owner)")
    log = [tuple(r) for r in run_all(owner, "SELECT kind_from, kind_to, approvers_from, approvers_to, operator_name, "
                                            "db_session_user FROM vb_instance_setting_log ORDER BY 1 NULLS FIRST")]
    assert log[-2:] == [(None, "LOCAL_SINGLE_OWNER", 2, 2, "Ben (owner)", "vb_owner"),
                        ("LOCAL_SINGLE_OWNER", "LOCAL_SINGLE_OWNER", 2, 1, "Ben (owner)", "vb_owner")]
    assert "append-only" in refused(owner, "UPDATE vb_instance_setting_log SET operator_name = 'x'")
    assert "append-only" in refused(owner, "DELETE FROM vb_instance_setting_log")
    assert "permission denied" in refused(app_engine, "UPDATE vb_instance_setting_log SET operator_name = 'x'")


def run_all(eng, sql, **kw):
    with eng.begin() as c:
        return c.execute(text(sql), kw).all()


def test_under_two_the_requester_still_cannot_approve_even_on_a_local_installation(two, owner):
    """Acceptance 3: LOCAL_SINGLE_OWNER alone changes nothing — the setting must also be 1."""
    stamp(owner)
    settings(owner, kind="LOCAL_SINGLE_OWNER")
    seed_bootstrap(owner, two["a1"])
    assert "two live platform admins" in refused(app_engine, INSERT, k="DELETE", p=two["p"], c=two["c"],
                                                 r=two["a1"], a=None)


def test_under_one_a_sole_admin_requests_and_approves_a_removal_flagged_and_the_30_days_still_apply(two, owner):
    """Acceptance 4, A-Q1: one live admin asks and approves; the approval is flagged; rights under 30 days old are
    refused as before."""
    single_owner(owner)
    seed_bootstrap(owner, two["a1"])                                                     # approved just now
    pp = request(app_engine, two)
    assert "single-owner setting the approver" in refused(app_engine, APPROVE, u=two["a1"], pp=pp)   # A-Q1 kept
    age_grant(owner, two["a1"])
    run(app_engine, APPROVE, u=two["a1"], pp=pp)
    assert run(owner, "SELECT approved_by_user_id = requested_by_user_id, approved_single_owner FROM project_purge "
                      "WHERE project_purge_id = :pp", pp=pp) == (True, True)
    assert "never changes" in refused(owner, "UPDATE project_purge SET approved_single_owner = false "
                                             "WHERE project_purge_id = :pp", pp=pp)          # not even the owner


def test_the_flag_is_never_the_app_s_to_write(two, owner):
    single_owner(owner)
    seed_bootstrap(owner, two["a1"])
    pp = request(app_engine, two)
    assert "permission denied" in refused(app_engine, "UPDATE project_purge SET approved_single_owner = true "
                                                      "WHERE project_purge_id = :pp", pp=pp)
    assert "never changes" in refused(owner, "UPDATE project_purge SET approved_single_owner = true "
                                             "WHERE project_purge_id = :pp", pp=pp)          # not even the owner's to set
    assert run(owner, "SELECT approved_single_owner FROM project_purge WHERE project_purge_id = :pp", pp=pp)[0] is False


def test_an_approval_made_alone_runs_under_one_and_never_once_the_setting_is_back_at_two(two, owner):
    """Acceptance 6, A-Q2, A-Q5: under 1 the sole admin may also run it; back at 2 the database and the run refuse."""
    single_owner(owner)
    seed_bootstrap(owner, two["a1"])
    age_grant(owner, two["a1"])
    pp = request(app_engine, two)
    run(app_engine, APPROVE, u=two["a1"], pp=pp)
    backdate(owner, pp)
    with owner.begin() as c:                                                             # under 1: the run's own checks pass
        assert purge_run._check_request(c, pp, two["a1"]).project_purge_id == pp
    allows = "SELECT set_config('vb.purge_project_id', :p, true), public.fn_purge_allows(:pi)"
    assert run(owner, allows, p=str(two["p"]), pi=two["p"])[1] is True
    settings(owner, n=2)
    assert run(owner, allows, p=str(two["p"]), pi=two["p"])[1] is False
    with owner.begin() as c, pytest.raises(purge_run.Refused, match="approved alone"):
        purge_run._check_request(c, pp, two["a1"])
    assert "execution needs" in refused(owner, "UPDATE project_purge SET executed_at = now(), executed_by_user_id = :u "
                                               "WHERE project_purge_id = :pp", u=two["a1"], pp=pp)


def test_under_one_a_sole_admin_grants_admin_rights_to_an_account_they_created_flagged(client, world, owner):
    """Acceptance 5: AR-24 and the independence check give way under 1; a target never approves their own grant."""
    a1 = run(owner, "SELECT app_user_id FROM app_user WHERE email = 'admin@example.test'")[0]
    seed_bootstrap(owner, a1)
    target = world["users"]["editor"]                                                    # created by a1 (world)
    with SessionLocal() as db:
        actor = db.get(AppUser, a1)
        with pytest.raises(Exception, match="AR-24"):                                    # under 2: refused, as before
            admin_grant.request(db, actor, target, "Second admin")
    single_owner(owner)
    with SessionLocal() as db:
        actor = db.get(AppUser, a1)
        g = admin_grant.request(db, actor, target, "Second admin for the laptop")
        g = admin_grant.approve(db, actor, g.platform_admin_grant_id, g.row_version)
        assert g.approved_single_owner is True and db.get(AppUser, target).is_platform_admin
    assert run(owner, "SELECT detail->>'approved_alone' FROM audit_event WHERE event_type = 'PLATFORM_ADMIN_GRANTED' "
                      "ORDER BY audit_event_id DESC LIMIT 1")[0] == "true"


def test_the_server_refuses_to_start_when_the_host_does_not_agree_it_is_single_owner(owner):
    """A-Q3: a LOCAL_SINGLE_OWNER database needs VB_INSTALLATION_KIND=LOCAL_SINGLE_OWNER on the host."""
    stamp(owner)
    settings(owner, kind="LOCAL_SINGLE_OWNER")
    with SessionLocal() as db:
        with pytest.raises(instance.NotStamped, match="VB_INSTALLATION_KIND"):
            instance.check_startup(db, "test-a", None)
        assert instance.check_startup(db, "test-a", "LOCAL_SINGLE_OWNER") == "test-a"


def test_the_admin_overview_carries_the_setting_for_the_banner(client, world, owner):
    """Acceptance 8: the admin page's banner reads approvers_required from the overview."""
    h = world["admin"]
    assert client.get("/api/v1/admin/archive-overview", headers=h).json()["approvers_required"] == 2
    single_owner(owner)
    assert client.get("/api/v1/admin/archive-overview", headers=h).json()["approvers_required"] == 1


# ---- sara round 1 (2026-10-28): H1, M2, M5 ---------------------------------------------------------------------------

def test_under_two_on_a_local_installation_the_requester_still_cannot_approve(two, owner):
    """M5: a stamped LOCAL row at 2 behaves exactly as before — not only the no-row path the older suites run on."""
    stamp(owner)
    settings(owner, kind="LOCAL_SINGLE_OWNER")
    promote(owner, two["a2"])
    pp = request(app_engine, two)
    assert "four eyes" in refused(app_engine, APPROVE, u=two["a1"], pp=pp)


def test_the_app_cannot_insert_a_flagged_request_the_guard_forces_it_false(two, owner):
    """M5: vb_app holds INSERT on the table; a request born flagged is born unflagged."""
    single_owner(owner)
    seed_bootstrap(owner, two["a1"])
    pp = run(app_engine, INSERT.replace("archive_purge_id)", "archive_purge_id, approved_single_owner)")
             .replace(":a)", ":a, true)"), k="DELETE", p=two["p"], c=two["c"], r=two["a1"], a=None)[0]
    assert run(owner, "SELECT approved_single_owner FROM project_purge WHERE project_purge_id = :pp", pp=pp)[0] is False


def test_a_decided_grant_s_flag_never_changes(client, world, owner):
    """M5: on the grant table the flag is fixed once decided — even for the owner."""
    a1 = run(owner, "SELECT app_user_id FROM app_user WHERE email = 'admin@example.test'")[0]
    seed_bootstrap(owner, a1)
    single_owner(owner)
    with SessionLocal() as db:
        actor = db.get(AppUser, a1)
        g = admin_grant.request(db, actor, world["users"]["editor"], "Second admin")
        g = admin_grant.approve(db, actor, g.platform_admin_grant_id, g.row_version)
        gid = g.platform_admin_grant_id
    assert "never changes" in refused(owner, "UPDATE platform_admin_grant SET approved_single_owner = false "
                                             "WHERE platform_admin_grant_id = :g", g=gid)


def test_admins_made_alone_never_approve_for_each_other_once_back_at_two(client, world, owner):
    """H1: one person's admins B and C count as independent of nobody, so back at 2 they cannot pair."""
    a1 = run(owner, "SELECT app_user_id FROM app_user WHERE email = 'admin@example.test'")[0]
    seed_bootstrap(owner, a1)
    single_owner(owner)
    b, c, d = world["users"]["editor"], world["users"]["owner"], world["users"]["outsider"]
    with SessionLocal() as db:
        actor = db.get(AppUser, a1)
        for uid in (b, c):
            g = admin_grant.request(db, actor, uid, "Made alone")
            admin_grant.approve(db, actor, g.platform_admin_grant_id, g.row_version)
    settings(owner, n=2)
    assert run(owner, "SELECT public.fn_admin_grant_independent(:b, :c)", b=b, c=c)[0] is False
    with SessionLocal() as db:
        g = admin_grant.request(db, db.get(AppUser, b), d, "A third, back at two")
        with pytest.raises(Exception, match="independent"):
            admin_grant.approve(db, db.get(AppUser, c), g.platform_admin_grant_id, g.row_version)


def test_the_removal_run_refuses_a_single_owner_database_the_host_does_not_declare(owner, monkeypatch):
    """M2: the data-destroying script applies A-Q3 too, through the same rule as the server."""
    from config import get_settings
    stamp(owner)
    settings(owner, kind="LOCAL_SINGLE_OWNER")
    monkeypatch.setattr(get_settings(), "vb_instance_id", "test-a")
    monkeypatch.setattr(get_settings(), "vb_installation_kind", None)
    with owner.begin() as c, pytest.raises(purge_run.Refused, match="VB_INSTALLATION_KIND"):
        purge_run._instance(c)
    monkeypatch.setattr(get_settings(), "vb_installation_kind", "LOCAL_SINGLE_OWNER")
    with owner.begin() as c:
        assert purge_run._instance(c) == "test-a"


# ---- Ben 2026-10-28 (sara M3): single-owner only where the app is served to this computer ------------------------------

@pytest.mark.parametrize("url, ok", [("http://localhost:5180", True), ("http://127.0.0.1:5180", True),
                                     ("https://vb.fortience.com", False), ("http://10.0.0.5:5180", False)])
def test_single_owner_runs_only_where_the_app_is_served_to_this_computer(owner, monkeypatch, url, ok):
    """A server with a real address never runs single-owner, even with the database and its .env both declaring it."""
    from config import get_settings
    stamp(owner)
    settings(owner, kind="LOCAL_SINGLE_OWNER")
    monkeypatch.setattr(get_settings(), "frontend_url", url)
    with SessionLocal() as db:
        if ok:
            assert instance.check_startup(db, "test-a", "LOCAL_SINGLE_OWNER") == "test-a"
        else:
            with pytest.raises(instance.NotStamped, match="only on this computer"):
                instance.check_startup(db, "test-a", "LOCAL_SINGLE_OWNER")


def test_a_host_declaring_single_owner_on_a_server_address_is_refused_even_for_a_shared_database(owner, monkeypatch):
    from config import get_settings
    stamp(owner)
    settings(owner, kind="SHARED")
    monkeypatch.setattr(get_settings(), "frontend_url", "https://vb.fortience.com")
    with SessionLocal() as db:
        with pytest.raises(instance.NotStamped, match="only on this computer"):
            instance.check_startup(db, "test-a", "LOCAL_SINGLE_OWNER")
        assert instance.check_startup(db, "test-a", None) == "test-a"          # a shared server as before


def test_the_owner_command_will_not_declare_single_owner_from_a_server(owner, monkeypatch):
    from config import get_settings
    from scripts import instance_settings
    stamp(owner)
    monkeypatch.setattr(get_settings(), "frontend_url", "https://vb.fortience.com")
    for argv in (["--declare-kind", "LOCAL_SINGLE_OWNER"], ["--approvers", "1"]):
        monkeypatch.setattr("sys.argv", ["instance_settings", *argv, "--operator", "IS test"])
        with pytest.raises(SystemExit, match="only on this computer"):
            instance_settings.main()
    assert run(owner, "SELECT installation_kind FROM vb_instance")[0] is None                # nothing changed
