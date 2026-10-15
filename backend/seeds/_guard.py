"""The one throwaway-database check for the demo seeds (sara M3): the name of the database actually connected to
(`current_database()`, not the URL — a URL query can redirect the connection, sara H1) must hold one of the markers
as a WHOLE word — `vb_demo_night` and `vb_test_ui` pass, `vb_latest` or `contest` do not."""
import re

from sqlalchemy import text


def assert_throwaway_db(db, markers: tuple[str, ...]) -> str:
    name = db.scalar(text("select current_database()"))
    words = set(re.split(r"[^a-z0-9]+", name.lower()))
    if not words & set(markers):
        raise SystemExit(f"Refusing: connected database '{name}' is not a {'/'.join(markers)} database")
    return name
