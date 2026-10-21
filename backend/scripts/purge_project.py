"""Carry out an approved DELETE removal of one project (slice16 spec §7; services/purge_run). Run from backend/, as the
owner, by an FTC operator (Fortience IS):
    ./venv/bin/python -m scripts.purge_project <request number> --actor-email <your platform-admin email>
    ./venv/bin/python -m scripts.purge_project <request number> --actor-email <email> --keys-only   # retry the keys
It connects with MIGRATION_DATABASE_URL (vb_owner) and needs VB_ARCHIVE_DIR / VB_ARCHIVE_KEY_DIR. It prints the client,
the project, its latest baseline and how many rows of each table will go, then asks you to type
<client code>/<project code>. The removal is one transaction: on any refusal or error nothing is deleted, no key is
touched, and the request stays open. Only after it has committed are the tombstone written and the project's keys
destroyed; a key that could not be destroyed is listed and stays outstanding — run again with --keys-only.

Not yet: ARCHIVE requests and DELETE_ARCHIVE runs."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine  # noqa: E402

from config import get_settings  # noqa: E402
from services import purge_run  # noqa: E402
from services.archive_store import from_settings  # noqa: E402


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
    print("  Then the project's keys are destroyed: its archive files can never be read again.")
    return input(f"\nThis cannot be undone. Type {_plain(plan.expected)} to delete it: ")


def _report(results: list[purge_run.KeyResult]) -> None:
    for k in results:
        if k.destroyed:
            proof = f"proved on {k.proof_object_name}" if k.proof_object_name else "no stored file to prove on"
            print(f"  key {k.key_name}: destroyed ({'was present' if k.was_present else 'was already absent'}; {proof})")
        else:
            print(f"  key {k.key_name}: NOT destroyed — {k.note}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("purge_id", type=int)
    p.add_argument("--actor-email", required=True)
    p.add_argument("--keys-only", action="store_true")
    a = p.parse_args()
    target = from_settings(get_settings())
    store, keys = target if target else (None, None)
    eng = create_engine(get_settings().migration_database_url)
    removed = []                                              # sara L3: the removal has committed once this is set

    def on_removed(plan: purge_run.Plan) -> None:
        removed.append(plan)
        print(f"\nRemoved: {_plain(plan.expected)}; {sum(plan.counts.values())} rows deleted. Now its keys:")
    try:
        if a.keys_only:
            if store is None:
                raise purge_run.Refused("VB_ARCHIVE_DIR and VB_ARCHIVE_KEY_DIR must be set.")
            removed.append(None)
            results = purge_run.destroy_keys(eng, a.purge_id, a.actor_email, store, keys)
        else:                                                 # sara N1: the same remove() the tests prove
            _plan, results = purge_run.remove(eng, a.purge_id, a.actor_email, _show, store, keys, on_removed)
    except purge_run.Refused as exc:
        if removed:
            raise SystemExit(f"Keys refused: {exc} Any keys not yet destroyed stay outstanding.") from None
        raise SystemExit(f"Refused: {exc} Nothing was deleted.") from None
    except Exception as exc:  # noqa: BLE001 — after the commit, any failure leaves keys outstanding, never hidden
        if removed:
            raise SystemExit(f"The project is removed, but its keys are outstanding ({exc}). "
                             "Run again with --keys-only.") from None
        raise
    finally:
        eng.dispose()
    _report(results)
    if any(not k.destroyed for k in results):
        raise SystemExit("Some keys are outstanding: see above, then run again with --keys-only.")


if __name__ == "__main__":
    main()
