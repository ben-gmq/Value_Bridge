"""Declare this installation's kind and set how many admins approve (0079; docs/approvers_setting_spec.md; Ben
2026-10-24). Run from backend/, as the owner (MIGRATION_DATABASE_URL), by Fortience IS or the installation's owner:
    ./venv/bin/python -m scripts.instance_settings --show
    ./venv/bin/python -m scripts.instance_settings --declare-kind LOCAL_SINGLE_OWNER --operator "<name>"
    ./venv/bin/python -m scripts.instance_settings --approvers 1 --operator "<name>"
    ./venv/bin/python -m scripts.instance_settings --approvers 2 --operator "<name>"
The database decides: 1 only on a LOCAL_SINGLE_OWNER installation; a SHARED installation stays shared for good; every
change is a row in vb_instance_setting_log naming the operator. A LOCAL_SINGLE_OWNER database also needs
VB_INSTALLATION_KIND=LOCAL_SINGLE_OWNER in the server's .env, or the server refuses to start."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.exc import DBAPIError  # noqa: E402

from config import get_settings  # noqa: E402
from services import instance  # noqa: E402

KINDS = ("SHARED", "LOCAL_SINGLE_OWNER")


def show(c) -> str:
    row = c.execute(text("SELECT instance_id, installation_kind, approvers_required, public.fn_approvers_required() "
                         "FROM vb_instance")).first()
    if row is None:
        return "This database is not stamped: run scripts.stamp_instance first."
    return (f"{row[0]}: kind {row[1] or 'undeclared (read as SHARED)'}, setting {row[2]}, "
            f"approvers required now {row[3]}")


def change(owner_url: str, kind: str | None, approvers: int | None, operator: str) -> str:
    eng = create_engine(owner_url)
    try:
        with eng.begin() as c:
            if c.scalar(text("SELECT count(*) FROM vb_instance")) == 0:
                raise SystemExit("This database is not stamped: run scripts.stamp_instance first.")
            c.execute(text("SELECT set_config('vb.operator', :o, true)"), {"o": operator})
            if kind is not None:
                c.execute(text("UPDATE vb_instance SET installation_kind = :k"), {"k": kind})
            if approvers is not None:
                c.execute(text("UPDATE vb_instance SET approvers_required = :n"), {"n": approvers})
            return show(c)
    except DBAPIError as exc:                                  # the guard's or a CHECK's refusal, said plainly
        raise SystemExit(f"Refused by the database: {exc.orig}") from exc
    finally:
        eng.dispose()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--show", action="store_true")
    p.add_argument("--declare-kind", choices=KINDS)
    p.add_argument("--approvers", type=int, choices=(1, 2))
    p.add_argument("--operator", help="who is making the change (recorded in the setting log)")
    a = p.parse_args()
    url = get_settings().migration_database_url
    if a.show or (a.declare_kind is None and a.approvers is None):
        eng = create_engine(url)
        with eng.connect() as c:
            print(show(c))
        eng.dispose()
        return
    if not (a.operator or "").strip():
        raise SystemExit("--operator is required: every change names who made it")
    if a.declare_kind == "LOCAL_SINGLE_OWNER" or a.approvers == 1:            # Ben 2026-10-28: this computer only
        why = instance.not_this_computer()
        if why:
            raise SystemExit(why)
    print(change(url, a.declare_kind, a.approvers, a.operator.strip()))
    if a.declare_kind == "LOCAL_SINGLE_OWNER":
        print("Set VB_INSTALLATION_KIND=LOCAL_SINGLE_OWNER in this host's .env, or the server will not start.")


if __name__ == "__main__":
    main()
