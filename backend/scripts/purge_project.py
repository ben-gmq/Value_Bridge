"""Carry out an approved DELETE removal of one project (slice16 spec §7; services/purge_run). Run from backend/, as the
owner, by an FTC operator:
    ./venv/bin/python -m scripts.purge_project <request number> --actor-email <your platform-admin email>
It connects with MIGRATION_DATABASE_URL (vb_owner). It prints the client, the project, its latest baseline and how many
rows of each table will go, then asks you to type <client code>/<project code>. Everything happens in one
transaction: on any refusal or error nothing is deleted and the request stays open.

Not yet: ARCHIVE requests, and destroying the project's keys after the removal (both wait for Ben's approval). The
key names are recorded on the request as outstanding."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine  # noqa: E402

from config import get_settings  # noqa: E402
from services import purge_run  # noqa: E402


def _plain(s: str | None) -> str:
    """sara L-f: names and the reason are typed by people — no control characters reach the operator's terminal."""
    return "".join(ch if ch.isprintable() else "?" for ch in (s or ""))


def _show(plan: purge_run.Plan) -> str:
    print(f"\nRemoval request {plan.purge_id} — DELETE")
    print(f"  Client:   {_plain(plan.client_code)}  {_plain(plan.client_name)}")
    print(f"  Project:  {_plain(plan.project_code)}  {_plain(plan.project_name)}  (id {plan.project_id})")
    print(f"  Latest baseline: {plan.latest_baseline or 'none'}")
    print(f"  Reason:   {_plain(plan.reason)}")
    print("  Rows that will be deleted:")
    for t, n in sorted(plan.counts.items()):
        if n:
            print(f"    {t:<40} {n:>8}")
    print(f"    {'total':<40} {sum(plan.counts.values()):>8}")
    return input(f"\nThis cannot be undone. Type {_plain(plan.expected)} to delete it: ")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("purge_id", type=int)
    p.add_argument("--actor-email", required=True)
    a = p.parse_args()
    eng = create_engine(get_settings().migration_database_url)
    try:
        with eng.begin() as c:
            plan = purge_run.execute(c, a.purge_id, a.actor_email, _show)
    except purge_run.Refused as exc:
        raise SystemExit(f"Refused: {exc}") from None
    finally:
        eng.dispose()
    print(f"\nDone: {plan.expected} removed; {sum(plan.counts.values())} rows deleted. "
          "Its keys are recorded as outstanding until key destruction is approved and run.")


if __name__ == "__main__":
    main()
