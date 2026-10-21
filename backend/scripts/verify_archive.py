"""Verify one written baseline archive file end to end (slice16 spec §7, criterion 155; the restore drill's first
step). Run from backend/:
    ./venv/bin/python -m scripts.verify_archive <baseline_id> [--part SCOPE|SIGNOFF]
Reads the part's current written file, checks its size and sha256 against the record, decrypts it and recomputes
every row hash and the digest. Prints OK or the first mismatch; exits 1 on a mismatch. Reads only."""
import argparse
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from config import get_settings  # noqa: E402
from database import SessionLocal  # noqa: E402
from models import BaselineArchive  # noqa: E402
from services import archive  # noqa: E402
from services.archive_store import from_settings  # noqa: E402


def check(row: BaselineArchive, store, keys) -> str | None:
    blob = store.get(row.object_name)
    if len(blob) != row.byte_size or hashlib.sha256(blob).hexdigest() != row.file_sha256:
        return "stored bytes: size or sha256 differ from the record"
    expect = {"project_id": row.project_id, "baseline_id": row.baseline_id, "archive_part": row.archive_part,
              "file_seq": row.file_seq, "instance_id": row.object_name.split("/", 1)[0]}
    return archive.verify_file(blob, keys, expect)["first_mismatch"]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("baseline_id", type=int)
    p.add_argument("--part", choices=("SCOPE", "SIGNOFF"), default="SCOPE")
    a = p.parse_args()
    target = from_settings(get_settings())
    if target is None:
        raise SystemExit("VB_ARCHIVE_DIR and VB_ARCHIVE_KEY_DIR must be set.")
    with SessionLocal() as db:
        row = db.scalar(select(BaselineArchive).where(
            BaselineArchive.baseline_id == a.baseline_id, BaselineArchive.archive_part == a.part,
            BaselineArchive.written_at.is_not(None)).order_by(BaselineArchive.file_seq.desc()).limit(1))
    if row is None:
        raise SystemExit(f"No written {a.part} file for baseline {a.baseline_id}.")
    why = check(row, *target)
    print("OK" if why is None else f"MISMATCH: {why}")
    sys.exit(0 if why is None else 1)


if __name__ == "__main__":
    main()
