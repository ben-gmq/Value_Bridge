"""THE ONE IMPORT PIPELINE (VB law 8; design §7.11, slice 4a spec §4–§7): template · export ·
validate · preview · commit, for every target.

A target is a column map plus two small functions — `validate(ctx, rows)` sets each row's verdict
and errors, `apply(ctx, rows)` writes them through the services' no-commit forms — so a later
target (Data Fields in 4a-2, then Issues, BRs, FRs, WBS, the flow JSON) adds a map and two
functions here and never a second pipeline. Everything else is shared:

- **Validate** is one transaction: the batch is inserted VALIDATING, every row is staged with
  its intended verdict and its errors, and the batch ends VALIDATED even with errors. File-level
  problems (the sheet, a missing column, a token from another project) are a 422 with nothing
  staged. Numbers are never minted here (§7.11 property 3).
- **Preview** computes before/after against the live rows when it is asked (S4-8), never stored.
- **Commit** locks the batch, re-checks it, re-validates every row inside the transaction (D1)
  and applies the lot with `Session.commit` made to raise, then commits once. A rule failure
  marks the batch REJECTED in a follow-up `UPDATE … WHERE status = VALIDATED`; an operational
  one (4a-R7's four SQLSTATEs) leaves it VALIDATED for a retry. Every failed attempt is audited.

Each exported row carries a signed row token (4a-R3): readable claims — project, table, id,
row_version — and an HMAC-SHA256 over them with ROW_TOKEN_KEY (never the JWT secret). The MAC
is checked first, then each claim, so stale, moved and other-project rows each get their own
error. Messages are `{code, column, message, params}` (schema §3.2); the screen renders
`t('import.msg.<code>', params)` and every string in them is untrusted text."""
import base64
import hashlib
import hmac
import re
import unicodedata
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from urllib.parse import unquote

from fastapi import HTTPException
from sqlalchemy import bindparam, func, select, text, update
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from sqlalchemy.types import Text

from config import get_settings
from models import DataEntity, ImportBatch, ImportRow
from services import audit, code_master, errors, xlsx
from services import data_entity as de_service

OPERATIONAL_SQLSTATES = frozenset({"40001", "40P01", "55P03", "57014"})    # 4a-R7
TOKEN_VERSION = "v1"
_TOKEN = re.compile(r"v1\.(\d{1,18})\.([a-z_]{1,40})\.(\d{1,18})\.(\d{1,9})\.([A-Za-z0-9_-]{43})")


# ---- messages ------------------------------------------------------------------------------

def msg(code: str, message: str, column: str | None = None, **params) -> dict:
    return {"code": code, "column": column, "message": message,
            "params": {k: v for k, v in params.items() if v is None or isinstance(v, (str, int, float, bool))}}


def _q(value) -> str:
    """A value quoted for an English fallback message."""
    return "“" + ("" if value is None else str(value)) + "”"


# ---- the row token (4a-R3) -----------------------------------------------------------------

@dataclass(frozen=True)
class Claims:
    project_id: int
    table: str
    row_id: int
    row_version: int


def _mac(claims: str) -> str:
    key = get_settings().row_token_key.encode()
    digest = hmac.new(key, b"vb-row-token|" + claims.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def row_token(project_id: int, table: str, row_id: int, row_version: int) -> str:
    claims = f"{TOKEN_VERSION}.{project_id}.{table}.{row_id}.{row_version}"
    return f"{claims}.{_mac(claims)}"


def read_token(token: str) -> Claims | None:
    """The claims of a genuine token, or None — the MAC is verified (in constant time) before
    any claim is believed."""
    m = _TOKEN.fullmatch(token or "")
    if not m:
        return None
    claims = token.rsplit(".", 1)[0]
    if not hmac.compare_digest(_mac(claims), m.group(5)):
        return None
    return Claims(int(m.group(1)), m.group(2), int(m.group(3)), int(m.group(4)))


# ---- column maps and targets ---------------------------------------------------------------

def as_text(value):
    """A cell read as text: numbers without a spurious .0, dates as ISO, booleans as TRUE/FALSE."""
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, datetime):
        return value.date().isoformat() if value.time() == time(0) else value.isoformat()
    if isinstance(value, (date, time, timedelta)):
        return value.isoformat() if not isinstance(value, timedelta) else str(value)
    return str(value)


@dataclass(frozen=True)
class Column:
    code: str
    header: str                                 # row 2; English, display only
    max_len: int | None = None
    category: str | None = None                 # a code_master category → the template's list
    protected: bool = False                     # the row token: locked, signed
    width: int = 24
    parse: Callable = as_text                   # cell → JSON scalar, or ValueError


@dataclass
class Staged:
    """One sheet row on its way through validate or commit."""
    sheet_row_no: int
    cells: dict
    verdict: str = "INSERT"
    business_key: str | None = None
    errors: list[dict] = field(default_factory=list)
    warnings: list[dict] = field(default_factory=list)
    token: Claims | None = None
    target_id: int | None = None
    target_row_version: int | None = None
    before: dict | None = None                  # set by apply on an UPDATE row (Q5)


@dataclass
class Ctx:
    db: Session
    project_id: int
    actor_id: int
    for_commit: bool = False                    # re-validation inside the commit: lock what is read
    current_row: Staged | None = None           # the row being applied, for a failure's locator


@dataclass(frozen=True)
class Target:
    code: str                                   # import_batch.target_entity / import_row.row_kind
    slug: str                                   # the route segment
    sheet_title: str
    table: str                                  # the token's table claim
    columns: tuple[Column, ...]
    compare: tuple[str, ...]                    # the columns an UPDATE may change (preview, MATCH)
    export_rows: Callable[[Session, int], list[dict]]
    current: Callable[[Session, int, list[int]], dict[int, dict]]
    validate: Callable[[Ctx, list[Staged]], None]
    apply: Callable[[Ctx, list[Staged]], None]

    @property
    def codes(self) -> tuple[str, ...]:
        return tuple(c.code for c in self.columns)

    @property
    def token_column(self) -> str | None:
        return next((c.code for c in self.columns if c.protected), None)


def _same(current, value) -> bool:
    """MATCH compares parsed values: a blank cell equals an empty or NULL column."""
    return xlsx.clean_cell(current) == value


# ---- DATA_ENTITY ---------------------------------------------------------------------------

DE_COLUMNS = (
    Column("de_number", "DE number", max_len=20, width=12),
    Column("de_name", "Name", max_len=200, width=32),
    Column("description", "Description", max_len=4000, width=48),
    Column("business_owner_note", "Business owner note", max_len=4000, width=36),
    Column("row_token", "Row token (do not edit)", max_len=200, protected=True, width=14),
)


def _de_export_rows(db: Session, project_id: int) -> list[dict]:
    return [{"de_number": de.de_number, "de_name": de.de_name, "description": de.description,
             "business_owner_note": de.business_owner_note,
             "row_token": row_token(project_id, DataEntity.__tablename__, de.data_entity_id, de.row_version)}
            for de in de_service.list_entities(db, project_id)]


def _de_current(db: Session, project_id: int, ids: list[int]) -> dict[int, dict]:
    if not ids:
        return {}
    rows = db.scalars(select(DataEntity).where(DataEntity.project_id == project_id,
                                               DataEntity.data_entity_id.in_(ids)))
    return {de.data_entity_id: {k: getattr(de, k) for k in de_service.ENTITY_COLUMNS} for de in rows}


def live_names(db: Session, project_id: int, names: list[str]) -> tuple[dict[str, str], dict[str, tuple]]:
    """Names normalised as the live-name index does, lower(btrim(name)), IN SQL and bound to
    this project (Q8, 4a-R14): ({file name: key}, {key: (data_entity_id, de_number)})."""
    if not names:
        return {}, {}
    arr = bindparam("names", names, type_=ARRAY(Text))
    keys = dict(db.execute(select(text("n"), func.lower(func.btrim(text("n"))))
                           .select_from(func.unnest(arr).alias("n"))).all())
    live = db.execute(select(func.lower(func.btrim(DataEntity.de_name)), DataEntity.data_entity_id,
                             DataEntity.de_number)
                      .where(DataEntity.project_id == project_id, DataEntity.is_active,
                             func.lower(func.btrim(DataEntity.de_name)).in_(list(set(keys.values()))))).all()
    return keys, {k: (i, n) for k, i, n in live}


def _de_validate(ctx: Ctx, rows: list[Staged]) -> None:
    db, first_key = ctx.db, {}
    for r in rows:
        number = r.cells["de_number"]
        if number is not None:
            number = r.cells["de_number"] = number.upper()
        r.verdict = "UPDATE" if number else "INSERT"
        if number and not any(e["column"] == "de_number" for e in r.errors):
            if number in first_key:
                r.errors.append(msg("DUPLICATE_KEY", f"{number} also appears on row {first_key[number]}.",
                                    "de_number", key=number, first_row=first_key[number]))
            else:
                first_key[number] = r.sheet_row_no
                r.business_key = number
        if r.cells["de_name"] is None:
            r.errors.append(msg("REQUIRED", "A data entity needs a name.", "de_name"))

    # Resolve every token's entity in one read, bound to this project; at commit, under lock.
    ids = sorted({r.token.row_id for r in rows if r.token})
    q = select(DataEntity).where(DataEntity.project_id == ctx.project_id,
                                 DataEntity.data_entity_id.in_(ids)).order_by(DataEntity.data_entity_id)
    if ctx.for_commit:
        q = q.with_for_update(of=DataEntity)
    found = {de.data_entity_id: de for de in
             db.scalars(q.execution_options(populate_existing=True))} if ids else {}

    renames: dict[int, str] = {}
    for r in rows:
        number, tok = r.cells["de_number"], r.token
        tok_cell = r.cells["row_token"]
        if tok_cell is not None and tok is None:
            continue                                     # the token's own error is recorded
        if number is None:
            if tok is not None:
                r.errors.append(msg("TOKEN_ROW_MISMATCH", "This row has a row token but no DE number: "
                                    "the rows were shifted. Re-export.", "de_number"))
            continue
        if tok is None:
            r.errors.append(msg("EXPORT_FIRST", f"{number}: export first to update. A row with a DE "
                                "number needs the row token from an export.", "de_number", key=number))
            continue
        de = found.get(tok.row_id)
        if de is None:
            r.errors.append(msg("ROW_RETIRED", f"{number} was retired or changed since export: re-export.",
                                "de_number", key=number))
            continue
        if de.de_number != number:
            r.errors.append(msg("TOKEN_ROW_MISMATCH", f"This row's token belongs to {de.de_number}, not "
                                f"{number}: the rows were sorted or shifted. Re-export.", "de_number",
                                key=number, token_key=de.de_number))
            continue
        if not de.is_active:
            r.errors.append(msg("ROW_RETIRED", f"{number} was retired or changed since export: re-export.",
                                "de_number", key=number))
            continue
        if de.row_version != tok.row_version:
            stale = [k for k in de_service.ENTITY_COLUMNS if not _same(getattr(de, k), r.cells[k])]
            for k in stale:
                r.errors.append(msg("ROW_STALE", f"{number} changed since export. Current value: "
                                    f"{_q(getattr(de, k))}", k, key=number, current=getattr(de, k)))
            if not stale:
                r.errors.append(msg("ROW_STALE", f"{number} changed since export. Re-export.", None,
                                    key=number))
            continue
        r.target_id, r.target_row_version = de.data_entity_id, de.row_version
        if all(_same(getattr(de, k), r.cells[k]) for k in de_service.ENTITY_COLUMNS):
            r.verdict = "MATCH"
        elif r.cells["de_name"] is not None and not _same(de.de_name, r.cells["de_name"]):
            renames[r.sheet_row_no] = r.cells["de_name"]

    # Names: a new name, or a rename, must not be another live entity's (swaps included), nor
    # another row's in this file.
    named = [r for r in rows if r.cells["de_name"] is not None and
             (r.verdict == "INSERT" or r.sheet_row_no in renames)]
    keys, live = live_names(db, ctx.project_id, [r.cells["de_name"] for r in named])
    first_name: dict[str, int] = {}
    for r in named:
        key = keys[r.cells["de_name"]]
        holder = live.get(key)
        if holder is not None and holder[0] != r.target_id:
            code, what = ("NAME_EXISTS", "A live data entity") if r.verdict == "INSERT" else \
                ("NAME_TAKEN", "Another live data entity")
            r.errors.append(msg(code, f"{what} already has this name: {holder[1]}.", "de_name",
                                key=holder[1]))
        elif key in first_name:
            r.errors.append(msg("DUPLICATE_NAME", f"Row {first_name[key]} has the same name.", "de_name",
                                first_row=first_name[key]))
        else:
            first_name[key] = r.sheet_row_no


def _de_apply(ctx: Ctx, rows: list[Staged]) -> None:
    db = ctx.db
    for r in rows:
        ctx.current_row = r
        c = r.cells
        if r.verdict == "INSERT":
            de = de_service.add_entity(db, ctx.actor_id, ctx.project_id, c["de_name"], c["description"],
                                       c["business_owner_note"])
            r.target_id = de.data_entity_id
        elif r.verdict == "UPDATE":
            de = db.get(DataEntity, r.target_id)            # locked by the re-validation
            r.before = {**{k: getattr(de, k) for k in de_service.ENTITY_COLUMNS},
                        "row_version": de.row_version}
            changes = {k: c[k] for k in de_service.ENTITY_COLUMNS if not _same(getattr(de, k), c[k])}
            de_service.change_entity(db, ctx.actor_id, de, r.target_row_version, changes)
    ctx.current_row = None


DATA_ENTITY = Target("DATA_ENTITY", "data-entities", "Data entities", DataEntity.__tablename__,
                     DE_COLUMNS, de_service.ENTITY_COLUMNS, _de_export_rows, _de_current, _de_validate, _de_apply)

TARGETS: dict[str, Target] = {t.slug: t for t in (DATA_ENTITY,)}    # data-fields joins in 4a-2
BY_CODE: dict[str, Target] = {t.code: t for t in TARGETS.values()}


def target_for(slug: str) -> Target:
    t = TARGETS.get(slug)
    if t is None:
        raise HTTPException(404, "Not found")
    return t


# ---- template and export -------------------------------------------------------------------

def out_columns(db: Session, project_id: int, target: Target) -> tuple[xlsx.OutColumn, ...]:
    """Data-validation lists come from THIS project's resolved codes (criterion 47)."""
    return tuple(xlsx.OutColumn(c.code, c.header, c.width, c.protected,
                                tuple(r.code for r in code_master.resolve(db, project_id, c.category))
                                if c.category else None)
                 for c in target.columns)


def template(db: Session, project_id: int, target: Target) -> bytes:
    return xlsx.write_book([xlsx.OutSheet(target.sheet_title, target.code,
                                          out_columns(db, project_id, target))])


def export(db: Session, project_id: int, target: Target) -> bytes:
    rows = [[r.get(c) for c in target.codes] for r in target.export_rows(db, project_id)]
    return xlsx.write_book([xlsx.OutSheet(target.sheet_title, target.code,
                                          out_columns(db, project_id, target), rows)])


def download_name(target: Target, kind: str, project_id: int) -> str:
    """Server-generated, never from user text (§7.11)."""
    return f"vb-{target.slug}-{kind}-p{project_id}-{date.today():%Y%m%d}.xlsx"


def clean_file_name(raw: str | None) -> str:
    """X-VB-File-Name, for display only (4a-R8, Q-15): percent-decoded, then the basename with
    control and format characters removed, at most 255 characters."""
    name = unquote(raw or "", errors="replace")
    name = re.split(r"[\\/]", name)[-1]
    name = "".join(ch for ch in name if unicodedata.category(ch)[0] != "C").strip()
    return name[:255].strip() or "upload.xlsx"


# ---- validate ------------------------------------------------------------------------------

def _statuses(db: Session) -> dict[str, int]:
    """IMPORT_STATUS from the global tier only (Q-12)."""
    return {r.code: r.code_id for r in code_master.resolve(db, None, "IMPORT_STATUS")}


def _check(ctx: Ctx, target: Target, rows: list[Staged]) -> None:
    """The shared checks, then the target's. Raises the file-level 422 for another project's token."""
    by_code = {c.code: c for c in target.columns}
    foreign = False
    for r in rows:
        for code, value in list(r.cells.items()):
            col = by_code[code]
            if value is xlsx.NO_CACHED_VALUE:
                r.errors.append(msg("FORMULA_NO_VALUE", "This cell holds a formula with no calculated "
                                    "value. Open the file in Excel, save it, and upload it again.", code))
                r.cells[code] = None
                continue
            if value is xlsx.CELL_ERROR:
                r.errors.append(msg("CELL_ERROR", "This cell holds an Excel error value.", code))
                r.cells[code] = None
                continue
            try:
                value = r.cells[code] = col.parse(value)
            except ValueError as e:
                r.errors.append(msg("INVALID", str(e) or "This value is not valid here.", code))
                r.cells[code] = None
                continue
            if col.max_len and isinstance(value, str) and len(value) > col.max_len:
                r.errors.append(msg("TOO_LONG", f"At most {col.max_len} characters ({len(value)} given).",
                                    code, max=col.max_len, length=len(value)))
        tok = target.token_column
        if tok and r.cells.get(tok) is not None and not any(e["column"] == tok for e in r.errors):
            claims = read_token(r.cells[tok])
            if claims is None:
                r.errors.append(msg("TOKEN_INVALID", "This row's token is not one VB issued, or it was "
                                    "edited. Re-export.", tok))
            elif claims.project_id != ctx.project_id:
                foreign = True
            elif claims.table != target.table:
                r.errors.append(msg("TOKEN_OTHER_TABLE", "This row's token belongs to another kind of "
                                    "record. Re-export.", tok))
            else:
                r.token = claims
    if foreign:
        raise HTTPException(422, "This file was exported from another project.")
    target.validate(ctx, rows)


def _payload(r: Staged, file_info: dict) -> dict:
    p = {"v": 1, "cells": r.cells, "file": file_info}
    if r.target_id is not None:
        p["resolved"] = {"target_id": r.target_id, "target_row_version": r.target_row_version}
    return p


def validate(db: Session, actor_id: int, project_id: int, target: Target, body: bytes,
             file_name: str) -> ImportBatch:
    sha = hashlib.sha256(body).hexdigest()
    with xlsx.parse_slot():
        sheet = xlsx.read_rows(body, target.code, target.codes)
    if not sheet.rows:
        raise HTTPException(422, "The sheet has no data rows.")
    ctx = Ctx(db, project_id, actor_id)
    rows = [Staged(no, dict(cells)) for no, cells in sheet.rows]
    _check(ctx, target, rows)

    status = _statuses(db)
    warnings = [msg("COLUMN_IGNORED", f"Column {c} is not part of this import and was ignored.", c)
                for c in sheet.ignored_columns]
    batch = ImportBatch(project_id=project_id, target_entity=target.code, file_name=file_name,
                        uploaded_by_user_id=actor_id, status_code_id=status["VALIDATING"],
                        file_warning_detail=warnings)
    db.add(batch)
    db.flush()
    file_info = {"sha256": sha, "sheet": sheet.sheet_name[:xlsx.SHEET_NAME_CAP]}
    for r in rows:
        db.add(ImportRow(import_batch_id=batch.import_batch_id, target_entity=target.code,
                         row_kind=target.code, sheet_row_no=r.sheet_row_no, business_key=r.business_key,
                         payload=_payload(r, file_info), verdict=r.verdict, is_valid=not r.errors,
                         error_detail=r.errors, warning_detail=r.warnings))
    batch.row_count = len(rows)
    batch.error_count = sum(1 for r in rows if r.errors)
    batch.warning_count = sum(1 for r in rows if r.warnings)
    # A row with errors counts only as an error, never also as an add or change (UAT 2026-10-08).
    batch.insert_count = sum(1 for r in rows if r.verdict == "INSERT" and not r.errors)
    batch.update_count = sum(1 for r in rows if r.verdict == "UPDATE" and not r.errors)
    batch.status_code_id = status["VALIDATED"]
    db.commit()
    db.refresh(batch)
    return batch


# ---- reading a batch -----------------------------------------------------------------------

def _rows_of(db: Session, batch: ImportBatch) -> list[ImportRow]:
    return list(db.scalars(select(ImportRow).where(ImportRow.import_batch_id == batch.import_batch_id)
                           .order_by(ImportRow.sheet_row_no)))


def batch_out(db: Session, batch: ImportBatch, rows: list[ImportRow] | None = None) -> dict:
    rows = _rows_of(db, batch) if rows is None else rows
    file_info = rows[0].payload.get("file", {}) if rows else {}
    target = BY_CODE.get(batch.target_entity)
    return {"import_batch_id": batch.import_batch_id, "project_id": batch.project_id,
            "target": target.slug if target else None, "target_entity": batch.target_entity,
            "status": batch.status_code, "file_name": batch.file_name,
            "sheet_name": file_info.get("sheet"),
            "uploaded_by_user_id": batch.uploaded_by_user_id, "uploaded_at": batch.uploaded_at,
            "row_count": batch.row_count, "error_count": batch.error_count,
            "warning_count": batch.warning_count, "insert_count": batch.insert_count,
            "update_count": batch.update_count,
            "match_count": sum(1 for r in rows if r.verdict == "MATCH" and r.is_valid),
            "file_warnings": batch.file_warning_detail, "committed_at": batch.committed_at,
            "committed_by_user_id": batch.committed_by_user_id,
            "rows_purged_at": batch.rows_purged_at, "row_version": batch.row_version}


def _changes(target: Target, row: ImportRow, current: dict | None) -> list[dict]:
    cells = row.payload.get("cells", {})
    before = row.payload.get("before") or current or {}
    if row.verdict == "INSERT":
        return [{"column": c, "before": None, "after": cells.get(c), "cleared": False}
                for c in target.compare if cells.get(c) is not None]
    if row.verdict != "UPDATE" or (current is None and "before" not in row.payload):
        return []
    return [{"column": c, "before": before.get(c), "after": cells.get(c),
             "cleared": cells.get(c) is None and xlsx.clean_cell(before.get(c)) is not None}
            for c in target.compare if not _same(before.get(c), cells.get(c))]


def preview(db: Session, batch: ImportBatch) -> dict:
    """Per row: verdict, errors and warnings by sheet row, and before/after computed NOW
    against the live rows (S4-8); a committed row shows the before-values it stored."""
    target = BY_CODE.get(batch.target_entity)
    if target is None:
        raise HTTPException(404, "Not found")
    rows = _rows_of(db, batch)
    ids = [r.payload.get("resolved", {}).get("target_id") for r in rows if r.verdict == "UPDATE"]
    current = target.current(db, batch.project_id, [i for i in ids if i is not None])
    out = []
    for r in rows:
        tid = r.payload.get("resolved", {}).get("target_id")
        out.append({"sheet_row_no": r.sheet_row_no, "verdict": r.verdict, "business_key": r.business_key,
                    "is_valid": r.is_valid, "errors": r.error_detail, "warnings": r.warning_detail,
                    "changes": _changes(target, r, current.get(tid)),
                    "committed_target_id": r.committed_target_id})
    return {"batch": batch_out(db, batch, rows), "purged": batch.rows_purged_at is not None, "rows": out}


# ---- commit --------------------------------------------------------------------------------

class _RuleFailure(Exception):
    """The batch cannot commit as staged: it becomes REJECTED, with these rows' fresh errors."""

    def __init__(self, message: str, row_errors: dict[int, list[dict]]) -> None:
        super().__init__(message)
        self.message, self.row_errors = message, row_errors


@contextmanager
def no_commit(db: Session):
    """During the apply nothing may commit partway: a helper that tries raises."""
    def _forbidden(*_a, **_k):
        raise RuntimeError("Session.commit called during an import's apply")
    db.commit = _forbidden
    try:
        yield
    finally:
        del db.commit


def _audit_failure(db: Session, actor_id: int, batch_id: int, project_id: int | None, kind: str,
                   reason: str, source_ip: str | None) -> None:
    audit.record(db, "IMPORT_COMMIT_FAILED", actor_id=actor_id, project_id=project_id,
                 target_table="import_batch", target_id=batch_id,
                 detail={"kind": kind, "reason": reason[:500]}, source_ip=source_ip)


def _reject(db: Session, batch_id: int, status: dict[str, int], row_errors: dict[int, list[dict]],
            file_msg: dict | None = None) -> bool:
    """Follow-up transaction: REJECTED only if still VALIDATED, so a racing successful commit is
    never overwritten. The fresh errors go onto their rows, so the preview explains why; a
    failure no row owns (a database error) leaves one file-level message instead (sara L-2)."""
    values = {"status_code_id": status["REJECTED"], "row_version": ImportBatch.row_version + 1}
    if file_msg is not None:
        values["file_warning_detail"] = ImportBatch.file_warning_detail.op("||")(
            bindparam("file_msg", [file_msg], type_=JSONB))
    res = db.execute(update(ImportBatch)
                     .where(ImportBatch.import_batch_id == batch_id,
                            ImportBatch.status_code_id == status["VALIDATED"])
                     .values(**values)
                     .execution_options(synchronize_session=False))
    if res.rowcount != 1:
        return False
    for sheet_row_no, errs in row_errors.items():
        db.execute(update(ImportRow)
                   .where(ImportRow.import_batch_id == batch_id, ImportRow.sheet_row_no == sheet_row_no)
                   .values(error_detail=errs, is_valid=False)
                   .execution_options(synchronize_session=False))
    if row_errors:
        invalid = db.scalar(select(func.count()).select_from(ImportRow).where(
            ImportRow.import_batch_id == batch_id, ImportRow.is_valid.is_(False)))
        db.execute(update(ImportBatch).where(ImportBatch.import_batch_id == batch_id)
                   .values(error_count=invalid).execution_options(synchronize_session=False))
    return True


def commit(db: Session, actor_id: int, batch_id: int, row_version: int,
           acknowledged_inserts: int | None, source_ip: str | None = None) -> ImportBatch:
    status = _statuses(db)
    project_id = None
    try:
        batch = db.scalars(select(ImportBatch).where(ImportBatch.import_batch_id == batch_id)
                           .with_for_update(of=ImportBatch)
                           .execution_options(populate_existing=True)).one()
        project_id = batch.project_id
        if batch.status_code_id != status["VALIDATED"]:
            # Named from the id: under FOR UPDATE the eager-joined code row is not re-read.
            now = next((k for k, v in status.items() if v == batch.status_code_id), "not validated")
            raise HTTPException(409, f"This batch is {now.lower()}; it cannot be committed.")
        if batch.row_version != row_version:
            raise HTTPException(409, errors.CONFLICT, headers=errors.STALE_HEADERS)
        if batch.error_count > 0:
            raise HTTPException(422, f"Fix {batch.error_count} rows and upload the file again.")
        target = BY_CODE.get(batch.target_entity)
        if target is None:
            raise HTTPException(404, "Not found")
        result = _commit(db, actor_id, batch, target, status, acknowledged_inserts, source_ip)
        db.commit()                            # the one commit; a failure here is audited too
    except HTTPException as e:                 # refused before anything was applied: unchanged
        db.rollback()
        _audit_failure(db, actor_id, batch_id, project_id, "REFUSED", str(e.detail), source_ip)
        db.commit()
        raise
    except DBAPIError as e:
        db.rollback()
        sqlstate = getattr(e.orig, "sqlstate", None)
        operational = sqlstate in OPERATIONAL_SQLSTATES
        if not operational:
            _reject(db, batch_id, status, {}, msg("APPLY_FAILED", f"The database refused the change "
                                                  f"(SQLSTATE {sqlstate}).", None, reason=f"SQLSTATE {sqlstate}"))
        _audit_failure(db, actor_id, batch_id, project_id, "OPERATIONAL" if operational else "RULE",
                       f"SQLSTATE {sqlstate}", source_ip)
        db.commit()
        if operational:
            raise HTTPException(503, "The database was busy, so nothing was applied. Commit again.")
        raise HTTPException(422, "The batch could not be applied, so nothing was applied and it was "
                                 "rejected. Upload the file again.")
    except _RuleFailure as e:
        db.rollback()
        _reject(db, batch_id, status, e.row_errors)
        _audit_failure(db, actor_id, batch_id, project_id, "RULE", e.message, source_ip)
        db.commit()
        raise HTTPException(422, e.message)
    except Exception as e:
        db.rollback()
        _reject(db, batch_id, status, {}, msg("APPLY_FAILED", "An unexpected error stopped the commit.",
                                              None, reason=type(e).__name__))
        _audit_failure(db, actor_id, batch_id, project_id, "RULE", type(e).__name__, source_ip)
        db.commit()
        raise
    db.refresh(result)
    return result


def _commit(db: Session, actor_id: int, batch: ImportBatch, target: Target, status: dict[str, int],
            acknowledged_inserts: int | None, source_ip: str | None = None) -> ImportBatch:
    stored = _rows_of(db, batch)
    staged = {r.sheet_row_no: r for r in stored}
    rows = [Staged(r.sheet_row_no, dict(r.payload.get("cells", {}))) for r in stored]
    ctx = Ctx(db, batch.project_id, actor_id, for_commit=True)

    # D1: every verdict is computed again, here, under lock. Any change is an error.
    try:
        _check(ctx, target, rows)
    except HTTPException as e:
        raise _RuleFailure(str(e.detail), {})
    fresh_errors: dict[int, list[dict]] = {}
    for r in rows:
        was = staged[r.sheet_row_no].verdict
        errs = list(r.errors)
        if not errs and r.verdict != was:
            errs.append(msg("VERDICT_CHANGED", f"This row would now be {r.verdict}, not {was}: the data "
                            "changed since the upload. Upload the file again.", None,
                            was=was, now=r.verdict))
        if errs:
            fresh_errors[r.sheet_row_no] = errs
    if fresh_errors:
        raise _RuleFailure(f"{len(fresh_errors)} rows changed since the upload, so nothing was applied "
                           "and the batch was rejected. Export again, re-apply your edits and upload.",
                           fresh_errors)
    inserts = sum(1 for r in rows if r.verdict == "INSERT")
    if inserts and acknowledged_inserts != inserts:
        raise HTTPException(422, f"This will CREATE {inserts} new rows. Confirm the count.")

    try:
        with no_commit(db):
            target.apply(ctx, rows)
            db.flush()
    except (HTTPException, ValueError) as e:
        r = ctx.current_row
        detail = e.detail if isinstance(e, HTTPException) else str(e)
        raise _RuleFailure(f"Row {r.sheet_row_no if r else '?'} could not be applied: {detail}. Nothing "
                           "was applied and the batch was rejected.",
                           {r.sheet_row_no: [msg("APPLY_FAILED", str(detail), None)]} if r else {})

    with no_commit(db):
        for r in rows:
            row = staged[r.sheet_row_no]
            row.committed_target_id = r.target_id
            if r.verdict == "UPDATE":
                row.payload = {**row.payload, "before": r.before}
        file_info = stored[0].payload.get("file", {}) if stored else {}
        batch.status_code_id = status["COMMITTED"]
        batch.committed_at = func.now()
        batch.committed_by_user_id = actor_id
        audit.record(db, "IMPORT_COMMITTED", actor_id=actor_id, project_id=batch.project_id,
                     target_table="import_batch", target_id=batch.import_batch_id,
                     detail={"entity": target.code, "insert_count": inserts,
                             "update_count": sum(1 for r in rows if r.verdict == "UPDATE"),
                             "match_count": sum(1 for r in rows if r.verdict == "MATCH"),
                             "retire_count": 0, "file_sha256": file_info.get("sha256"),
                             "sheet": file_info.get("sheet")}, source_ip=source_ip)
        db.flush()
    return batch
