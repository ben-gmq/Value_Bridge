"""The weekly archive check (services/weekly_check; slice16 spec §1a, §19 U1/U5). Run from backend/ once a week by
Fortience IS, as the application role (DATABASE_URL), on the host that holds the archive folders:
    ./venv/bin/python -m scripts.weekly_check --actor-email <the platform admin who owns the check> --operator "<name>"
It checks every current baseline file (size, sha256) and every held project archive (size, sha256, key), owes a
replacement for each failed file, and prints the report — projects due for archiving, reopened since the last run,
owed and failing files, unfinished removals, the platform-admin lines. Keep its output in the operator's run log. Every
run records one line, so the Removals tab shows when it last ran and warns after 8 days. Exits 1 when anything failed."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select  # noqa: E402

from config import get_settings  # noqa: E402
from database import SessionLocal  # noqa: E402
from models import AppUser  # noqa: E402
from services import instance, weekly_check  # noqa: E402
from services.archive_store import from_settings  # noqa: E402


def _lines(rep: dict) -> list[str]:
    s = rep["summary"]
    out = [f"Weekly archive check — {s['due']} due for archiving, {s['reopened']} reopened since the last run, "
           f"{s['owed_files']} file(s) owed, {s['failed_files']} failed this run, {s['held_archives']} held archive(s) "
           f"checked ({s['held_failing']} failing), {s['unfinished_removals']} unfinished removal(s)."]
    out += [f"  DUE      {d['client_code']}/{d['project_code']} closed {d['closed_on']} due {d['due_on']}"
            for d in rep["due_for_archiving"]]
    out += [f"  REOPENED {r['project_code']} on {r['reopened_at']:%Y-%m-%d} (was closed {r['was_closed_on']})"
            for r in rep["reopened_since_last_run"]]
    out += [f"  FAILED   baseline {f['baseline_id']} {f['archive_part']} file {f['file_seq']}: {f['error']} — "
            f"file {f['replacement_file_seq']} owed" for f in rep["failed_files"]]
    out += [f"  OWED     project {o['project_code'] or o['project_id']}: {o['owed_files']} file(s)"
            + (f" — last error: {o['last_error']}" if o["last_error"] else "") for o in rep["owed_files"]]
    out += [f"  HELD     {h['project_code']} (request {h['project_purge_id']}): "
            + ("OK" if h["ok"] else f"FAILING — {h['error']}") for h in rep["held_archives"]]
    out += [f"  REMOVAL  {u['purge_kind']} {u['project_code']} (request {u['project_purge_id']}): {u['state']}"
            + (f", {u['keys_outstanding']} key(s) outstanding" if u["keys_outstanding"] else "")
            for u in rep["unfinished_removals"]]
    a = rep["admin"]
    if rep["live_platform_admins"] < rep["approvers_required"]:                    # 0079: the setting, not 2
        out.append("  ADMINS   fewer than two live platform admins: no removal can be approved")
    out += [f"  ADMINS   live admin {u} has no grant on record — needs an IS grant" for u in a["admins_without_a_grant"]]
    out += [f"  ADMINS   request {g} for admin rights has waited over 7 days" for g in a["open_over_7_days"]]
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--actor-email", required=True)
    p.add_argument("--operator", required=True)
    p.add_argument("--json", action="store_true", help="print the full report as JSON as well")
    a = p.parse_args()
    target = from_settings(get_settings())
    if target is None:
        raise SystemExit("VB_ARCHIVE_DIR and VB_ARCHIVE_KEY_DIR must be set: the check reads the stored files.")
    with SessionLocal() as db:
        s = get_settings()
        instance.check_startup(db, s.vb_instance_id, s.vb_installation_kind)     # never under another's names
        actor = db.scalar(select(AppUser).where(func.lower(AppUser.email) == a.actor_email.lower(),
                                                AppUser.is_active, AppUser.is_platform_admin))
        if actor is None:
            raise SystemExit("--actor-email must name a live platform admin (the check's owner, Q-84).")
        try:
            weekly_check.check_reachable(db, *target, get_settings().vb_instance_id)
        except weekly_check.Unreachable as exc:
            raise SystemExit(f"Nothing checked: {exc}. Run it on the host that holds the archive folders.") from exc
        rep = weekly_check.run(db, *target, actor.app_user_id, a.operator)
    print("\n".join(_lines(rep)))
    if a.json:
        print(json.dumps(rep, default=str, indent=2))
    s = rep["summary"]
    sys.exit(1 if s["failed_files"] or s["held_failing"] else 0)


if __name__ == "__main__":
    main()
