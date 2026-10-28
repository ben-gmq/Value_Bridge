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
from sqlalchemy import bindparam, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, aliased
from sqlalchemy.types import Text

from config import get_settings
from models import (AppUser, AuditEvent, BfcNode, BrFunctionRequirement, BrSolution, BusinessRequirement, CodeMaster,
                    DataEntity, DataField, FrInterface, FunctionRequirement, ImportBatch, ImportRow, Issue, IssueBr,
                    OrgUnit, Solution, Stakeholder)
from services import audit, code_master, components, effort, errors, interface, xlsx
from services import business_requirement as br_service
from services import function_requirement as fr_service
from services import issue as issue_service
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
    choices: tuple[str, ...] | None = None      # a fixed list for the template (e.g. Y / N)


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
    values: dict | None = None                  # the row's parsed values as `compare` sees them, when
                                                # they differ from the cells (a target named by name)
    pins: dict = field(default_factory=dict)    # what the row resolved to at staging (4a-R13): a
                                                # different resolution at commit is an error
    info: dict | None = None                    # display only: resolved parents, the relationship
    plan: dict = field(default_factory=dict)    # the target's working notes from validate to apply
    token_key: str | None = None                # the key column a token message points at (slice 1e)


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
    component: str | None = None                # D-37: checked at validate and commit (§5.2)
    max_rows: int | None = None                 # a lower cap than xlsx.MAX_ROWS (slice 1e, P7)
    reupload_warning: bool = False              # warn when this file was committed before (slice 1e, P1)

    @property
    def codes(self) -> tuple[str, ...]:
        return tuple(c.code for c in self.columns)

    @property
    def token_column(self) -> str | None:
        return "row_token" if "row_token" in self.codes else None     # an FR / issue sheet locks a second column


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

# ---- DATA_FIELD (4a-2) -----------------------------------------------------------------------

def as_int(lo: int, hi: int) -> Callable:
    """A whole number from lo to hi; 10 and 10.0 are the same number, 10.5 is not."""
    def parse(value):
        if value is None:
            return None
        if isinstance(value, bool):
            raise ValueError(f"A whole number from {lo} to {hi}.")
        if isinstance(value, float):
            if not value.is_integer():
                raise ValueError(f"A whole number from {lo} to {hi}.")
            value = int(value)
        if isinstance(value, str):
            m = re.fullmatch(r"\+?(\d{1,10})(?:\.0*)?", value)
            if not m:
                raise ValueError(f"A whole number from {lo} to {hi}.")
            value = int(m.group(1))
        if not isinstance(value, int) or not lo <= value <= hi:
            raise ValueError(f"A whole number from {lo} to {hi}.")
        return value
    return parse


_YES, _NO = frozenset({"Y", "YES", "TRUE", "1"}), frozenset({"N", "NO", "FALSE", "0"})


def as_yes_no(value):
    """Y / N / blank → True / False / None: blank means "unknown" (§4 each row)."""
    if value is None or isinstance(value, bool):
        return value
    text_ = as_text(value).upper()
    if text_ in _YES:
        return True
    if text_ in _NO:
        return False
    raise ValueError("Y, N or blank.")


DF_COLUMNS = (
    Column("de_number", "DE number", max_len=20, width=12),
    Column("de_name", "Entity name (when no DE number)", max_len=200, width=26),
    Column("field_name", "Field name", max_len=200, width=28),
    Column("data_type", "Data type", max_len=40, category="FIELD_DATA_TYPE", width=14),
    Column("length", "Length", parse=as_int(1, 2_147_483_647), width=9),
    Column("precision", "Precision", parse=as_int(1, 2_147_483_647), width=10),
    Column("scale", "Scale", parse=as_int(0, 2_147_483_647), width=8),
    Column("mandatory", "Mandatory (Y/N)", parse=as_yes_no, choices=("Y", "N"), width=11),
    Column("pk_position", "PK position", parse=as_int(1, 32), width=10),
    Column("ref_de_number", "FK: DE number", max_len=20, width=13),
    Column("ref_de_name", "FK: entity name (when no DE number)", max_len=200, width=26),
    Column("ref_field_name", "FK: field name", max_len=200, width=22),
    Column("fk_group", "FK group", max_len=40, width=10),
    Column("description", "Description", max_len=4000, width=40),
    Column("row_token", "Row token (do not edit)", max_len=200, protected=True, width=14),
)
DF_COMPARE = ("field_name", "data_type", "length", "precision", "scale", "mandatory", "pk_position",
              "ref_de_number", "ref_field_name", "fk_group", "description")
_REF_COLUMNS = ("ref_de_number", "ref_field_name", "fk_group")
_FK_GROUP_NUMBER = re.compile(r"\d{1,5}")             # 4a-R1: numeric = a stored relationship number
_FK_GROUP_MAX = 32_767                                # fk_group_no is a smallint


@dataclass(frozen=True)
class _Ent:
    data_entity_id: int
    de_number: str
    de_name: str


def _fields_with_refs(db: Session, project_id: int):
    ref_de, ref_f = aliased(DataEntity), aliased(DataField)
    return (select(DataField, ref_de.de_number, ref_de.de_name, ref_f.field_name)
            .outerjoin(ref_de, ref_de.data_entity_id == DataField.ref_data_entity_id)
            .outerjoin(ref_f, ref_f.data_field_id == DataField.ref_data_field_id)
            .where(DataField.project_id == project_id))


def _df_values(f: DataField, ref_number: str | None, ref_field: str | None) -> dict:
    """A live field as `compare` sees it: the cells' parsed shape."""
    return {"field_name": f.field_name, "data_type": f.data_type_code, "length": f.length_val,
            "precision": f.precision_val, "scale": f.scale_val, "mandatory": f.is_mandatory,
            "pk_position": f.pk_ordinal, "ref_de_number": ref_number if f.is_foreign_key else None,
            "ref_field_name": ref_field, "fk_group": f.fk_group_no, "description": f.description}


def _df_current(db: Session, project_id: int, ids: list[int]) -> dict[int, dict]:
    if not ids:
        return {}
    rows = db.execute(_fields_with_refs(db, project_id).where(DataField.data_field_id.in_(ids))).all()
    return {f.data_field_id: _df_values(f, num, rf) for f, num, _name, rf in rows}


def _df_export_rows(db: Session, project_id: int) -> list[dict]:
    owner = aliased(DataEntity)
    rows = db.execute(_fields_with_refs(db, project_id).add_columns(owner.de_number, owner.de_name)
                      .join(owner, owner.data_entity_id == DataField.data_entity_id)
                      .where(DataField.is_active, owner.is_active)
                      .order_by(owner.de_number, DataField.seq_no)).all()
    out = []
    for f, ref_num, ref_name, ref_field, de_number, de_name in rows:
        v = _df_values(f, ref_num, ref_field)
        out.append({**v, "de_number": de_number, "de_name": de_name,
                    "mandatory": None if f.is_mandatory is None else ("Y" if f.is_mandatory else "N"),
                    "ref_de_name": ref_name if f.is_foreign_key else None,
                    "row_token": row_token(project_id, DataField.__tablename__, f.data_field_id,
                                           f.row_version)})
    return out


def sql_keys(db: Session, names) -> dict[str, str]:
    """{name: lower(btrim(name))}, normalised IN SQL as the live-name indexes do (Q8, S4-11)."""
    names = sorted({n for n in names if n is not None})
    if not names:
        return {}
    arr = bindparam("names", names, type_=ARRAY(Text))
    return dict(db.execute(select(text("n"), func.lower(func.btrim(text("n"))))
                           .select_from(func.unnest(arr).alias("n"))).all())


def resolve_entities(db: Session, project_id: int, numbers, names, lock: bool = False):
    """Every entity a field sheet names, by number or by lower(btrim(name)), in ONE SQL pass bound
    to the batch's project (4a-R12, 4a-R14); at commit, held FOR NO KEY UPDATE so none is renamed
    or retired under the apply, and two imports into one entity take turns (seq_no, groups).
    Returns ({name: key}, {number: _Ent}, {key: _Ent})."""
    keys = sql_keys(db, names)
    numbers = sorted({n for n in numbers if n})
    if not numbers and not keys:
        return keys, {}, {}
    name_key = func.lower(func.btrim(DataEntity.de_name))
    q = (select(DataEntity.data_entity_id, DataEntity.de_number, DataEntity.de_name, name_key)
         .where(DataEntity.project_id == project_id, DataEntity.is_active,
                or_(DataEntity.de_number.in_(numbers), name_key.in_(sorted(set(keys.values())))))
         .order_by(DataEntity.data_entity_id))             # a fixed lock order (sara L-1)
    if lock:
        q = q.with_for_update(key_share=True, of=DataEntity)
    by_number, by_key = {}, {}
    for i, number, name, key in db.execute(q).all():
        e = _Ent(i, number, name)
        by_number[number] = e
        by_key[key] = e
    return keys, by_number, by_key


_ANY_SPACE = "[\\s   -‍    ⁠　﻿]"


def near_names(db: Session, project_id: int, names) -> dict[str, str]:
    """4a-R15: for a name that found no live entity, the live entity in THIS project whose name
    matches once all whitespace is ignored: {name: "DE-nnnn name"}."""
    squeeze = {n: re.sub(_ANY_SPACE, "", n).lower() for n in names if n}
    if not squeeze:
        return {}
    pattern = bindparam("pattern", _ANY_SPACE)
    squeezed = func.lower(func.regexp_replace(DataEntity.de_name, pattern, "", "g"))
    rows = db.execute(select(squeezed, DataEntity.de_number, DataEntity.de_name)
                      .where(DataEntity.project_id == project_id, DataEntity.is_active,
                             squeezed.in_(sorted(set(squeeze.values()))))).all()
    found = {k: f"{num} {name}" for k, num, name in rows}
    return {n: found[k] for n, k in squeeze.items() if k in found}


_MISSING = object()          # named, but did not resolve (the row has its error)


def _entity_of(r: Staged, num_col: str, name_col: str, keys: dict, by_number: dict, by_key: dict,
               near: dict):
    """The entity a row names by number, or when that is blank by name; both given must agree
    (S4-12, 4a-R19). None when neither is given; _MISSING when the row got an error."""
    number, name = r.cells[num_col], r.cells[name_col]
    if any(e["column"] in (num_col, name_col) for e in r.errors):
        return _MISSING
    if number is None and name is None:
        return None
    by_num = by_number.get(number) if number else None
    by_nm = by_key.get(keys.get(name)) if name else None
    if number and by_num is None:
        r.errors.append(msg("ENTITY_NOT_FOUND", f"No live data entity in this project is {number}.",
                            num_col, key=number))
        return _MISSING
    if not number and by_nm is None:
        hint = near.get(name)
        r.errors.append(msg("ENTITY_NOT_FOUND", f"No live data entity in this project is named {_q(name)}."
                            + (f" Did you mean {hint}? (the spaces differ)" if hint else ""), name_col,
                            name=name, near=hint))
        return _MISSING
    if number and name and (by_nm is None or by_nm.data_entity_id != by_num.data_entity_id):
        r.errors.append(msg("ENTITY_MISMATCH", f"{number} is named {_q(by_num.de_name)}, not {_q(name)}: "
                            "the number and the name must name the same entity.", name_col,
                            key=number, name=name, current=by_num.de_name))
        return _MISSING
    return by_num or by_nm


def _pin(e: _Ent | None, by_name: bool) -> dict | None:
    return None if e is None else {"de_number": e.de_number, "de_name": e.de_name, "by_name": by_name}


def _df_validate(ctx: Ctx, rows: list[Staged]) -> None:
    db, project_id = ctx.db, ctx.project_id
    for r in rows:
        for c in ("de_number", "ref_de_number"):
            if r.cells[c] is not None:
                r.cells[c] = r.cells[c].upper()

    # 4a-R12: every parent AND every referenced entity, resolved first, in one SQL pass.
    names = [r.cells[c] for r in rows for c in ("de_name", "ref_de_name")]
    keys, by_number, by_key = resolve_entities(
        db, project_id, [r.cells[c] for r in rows for c in ("de_number", "ref_de_number")], names,
        lock=ctx.for_commit)
    near = near_names(db, project_id, [n for n in set(names) if n and keys.get(n) not in by_key])
    field_keys = sql_keys(db, [r.cells[c] for r in rows for c in ("field_name", "ref_field_name")])

    for r in rows:
        parent = _entity_of(r, "de_number", "de_name", keys, by_number, by_key, near)
        ref = _entity_of(r, "ref_de_number", "ref_de_name", keys, by_number, by_key, near)
        if parent is None:
            r.errors.append(msg("REQUIRED", "A field needs its data entity: a DE number, or the "
                                "entity's name.", "de_number"))
        if r.cells["field_name"] is None:
            r.errors.append(msg("REQUIRED", "A data field needs a name.", "field_name"))
        r.plan = {"parent": parent if isinstance(parent, _Ent) else None,
                  "ref": ref if isinstance(ref, _Ent) else None, "ref_missing": ref is _MISSING,
                  "key": field_keys.get(r.cells["field_name"])}
        r.verdict = "UPDATE" if r.cells["row_token"] is not None else "INSERT"
        if r.plan["parent"] is not None:
            r.pins["de_number"] = parent.de_number
        if r.plan["ref"] is not None:
            r.pins["ref_de_number"] = ref.de_number
        r.info = {"parent": _pin(r.plan["parent"], r.cells["de_number"] is None),
                  "ref": _pin(r.plan["ref"], r.cells["ref_de_number"] is None)}

    # The field rows the tokens name (locked at commit), then every live field of every entity
    # the sheet touches, keyed by (entity id, lower(btrim(name))) — the resolved id, never a cell.
    tok_ids = sorted({r.token.row_id for r in rows if r.token})
    found: dict[int, tuple[DataField, str]] = {}
    if tok_ids:
        q = (select(DataField, DataEntity.de_number)
             .join(DataEntity, DataEntity.data_entity_id == DataField.data_entity_id)
             .where(DataField.project_id == project_id, DataField.data_field_id.in_(tok_ids))
             .order_by(DataField.data_field_id))
        if ctx.for_commit:
            q = q.with_for_update(of=DataField)
        found = {f.data_field_id: (f, n) for f, n in db.execute(q.execution_options(populate_existing=True))}
    de_ids = sorted({e.data_entity_id for r in rows for e in (r.plan["parent"], r.plan["ref"]) if e}
                    | {f.data_entity_id for f, _n in found.values()})
    live_by_key: dict[tuple[int, str], DataField] = {}
    live_of: dict[int, list[DataField]] = {}
    if de_ids:
        q = (select(DataField, func.lower(func.btrim(DataField.field_name)))
             .where(DataField.project_id == project_id, DataField.data_entity_id.in_(de_ids),
                    DataField.is_active).order_by(DataField.data_field_id))
        if ctx.for_commit:
            q = q.with_for_update(read=True, of=DataField)
        for f, key in db.execute(q.execution_options(populate_existing=True)):
            live_by_key[(f.data_entity_id, key)] = f
            live_of.setdefault(f.data_entity_id, []).append(f)
    current = _df_current(db, project_id, [i for i, (f, _n) in found.items() if f.is_active])
    types = {c.code: c.code for c in code_master.resolve(db, project_id, "FIELD_DATA_TYPE")}
    types_ci: dict[str, list[str]] = {}
    for code in types:
        types_ci.setdefault(code.upper(), []).append(code)

    # Keys, tokens and verdicts.
    first_key: dict[str, int] = {}
    file_rows: dict[tuple[int, str], Staged] = {}            # (entity id, key) → the row
    for r in rows:
        parent, key = r.plan["parent"], r.plan["key"]
        if parent is None or key is None:
            continue
        bkey = f"{parent.de_number}/{key}"
        if (parent.data_entity_id, key) in file_rows:
            r.errors.append(msg("DUPLICATE_KEY", f"{bkey} also appears on row {first_key[bkey]}.",
                                "field_name", key=bkey, first_row=first_key[bkey]))
            continue
        first_key[bkey] = r.sheet_row_no
        file_rows[(parent.data_entity_id, key)] = r
        r.business_key = bkey
        holder = live_by_key.get((parent.data_entity_id, key))
        if r.cells["row_token"] is not None and r.token is None:
            continue                                         # the token's own error is recorded
        if r.token is None:
            if holder is not None:
                r.errors.append(msg("EXPORT_FIRST", f"{parent.de_number} already has the field "
                                    f"{_q(holder.field_name)}: export first to update. A row for an "
                                    "existing field needs the row token from an export.", "field_name",
                                    key=bkey))
            continue
        f, owner_number = found.get(r.token.row_id, (None, None))
        if f is None or not f.is_active:
            r.errors.append(msg("ROW_RETIRED", f"{bkey} was retired or changed since export: re-export.",
                                "field_name", key=bkey))
            continue
        token_key = f"{owner_number}/{f.field_name}"
        if f.data_entity_id != parent.data_entity_id or holder is None or \
                holder.data_field_id != f.data_field_id:
            # Moved to another entity, renamed, or the rows were shifted against their tokens.
            # A field is renamed or moved on screen, never through an import (safer reading).
            r.errors.append(msg("FIELD_MISMATCH", f"This row's token belongs to {token_key}, not "
                                f"{bkey}: the rows were sorted or shifted, or the field was renamed or "
                                "moved. Rename or move fields on screen, then re-export.", "field_name",
                                key=bkey, token_key=token_key))
            continue
        r.target_id, r.target_row_version = f.data_field_id, f.row_version
        r.plan["field"] = f

    # Values, as `compare` sees them.
    for r in rows:
        c, plan = r.cells, r.plan
        f, ref = plan.get("field"), plan["ref"]
        v = {k: c[k] for k in DF_COMPARE if k in c}
        if c["data_type"] is not None and c["data_type"] not in types:
            match = types_ci.get(c["data_type"].upper(), [])
            if len(match) == 1:
                v["data_type"] = match[0]
            else:
                r.errors.append(msg("CODE_UNKNOWN", f"{_q(c['data_type'])} is not a data type of this "
                                    "project.", "data_type", value=c["data_type"]))
        sized = next((k for k in ("length", "precision", "scale") if c[k] is not None), None)
        if sized and c["data_type"] is None:
            r.errors.append(msg("SIZE_NEEDS_TYPE", "A size needs a data type.", sized))
        if c["scale"] is not None and c["precision"] is not None and c["scale"] > c["precision"]:
            r.errors.append(msg("SCALE_OVER_PRECISION", "The scale cannot be larger than the precision.",
                                "scale"))
        if c["pk_position"] is not None and c["mandatory"] is False:
            r.errors.append(msg("PK_OPTIONAL", "A primary-key field cannot be optional (N).", "mandatory"))
        v["ref_de_number"] = ref.de_number if ref else None
        if ref is None and not plan["ref_missing"]:
            for col in ("ref_field_name", "fk_group"):
                if c[col] is not None:
                    r.errors.append(msg("REF_NEEDS_ENTITY", "A foreign key names its entity first: "
                                        "FK DE number, or FK entity name.", col))
            v["ref_field_name"] = v["fk_group"] = None
        if ref is not None:
            # The referenced field: live in the referenced entity, or a new row in this file (Q7).
            plan["ref_field"] = None
            if c["ref_field_name"] is not None:
                rkey = field_keys.get(c["ref_field_name"])
                live_rf = live_by_key.get((ref.data_entity_id, rkey))
                file_rf = file_rows.get((ref.data_entity_id, rkey))
                if live_rf is not None:
                    plan["ref_field"] = ("live", live_rf.data_field_id)
                    v["ref_field_name"] = live_rf.field_name
                elif file_rf is not None:
                    plan["ref_field"] = ("file", file_rf.sheet_row_no)
                    v["ref_field_name"] = file_rf.cells["field_name"]
                else:
                    r.errors.append(msg("REF_FIELD_NOT_FOUND", f"{ref.de_number} has no live field named "
                                        f"{_q(c['ref_field_name'])}, and no row in this file adds one.",
                                        "ref_field_name", key=ref.de_number, name=c["ref_field_name"]))
            # The relationship (Q3, 4a-R1): numeric = a stored number; any other text = a label.
            own = f.fk_group_no if f is not None and f.is_foreign_key and \
                f.ref_data_entity_id == ref.data_entity_id else None
            g = c["fk_group"]
            if g is None:
                plan["group"] = ("own", own) if own is not None else ("new", None)
                v["fk_group"] = own
            elif _FK_GROUP_NUMBER.fullmatch(g):
                n = int(g)
                if not 1 <= n <= _FK_GROUP_MAX:
                    r.errors.append(msg("FK_GROUP_NOT_FOUND", f"There is no stored relationship {g} to "
                                        f"{ref.de_number}.", "fk_group", key=ref.de_number, group=g))
                plan["group"] = ("num", n)
                v["fk_group"] = n
            else:
                plan["group"] = ("label", g.casefold())
                v["fk_group"] = g
        r.values = v

    # Verdicts for exported rows, and a colleague's edit since export (D2).
    for r in rows:
        f = r.plan.get("field")
        if f is None:
            continue
        cur = current[f.data_field_id]
        if f.row_version != r.token.row_version:
            stale = [k for k in DF_COMPARE if not _same(cur[k], r.values.get(k))]
            for k in stale:
                r.errors.append(msg("ROW_STALE", f"{r.business_key} changed since export. Current value: "
                                    f"{_q(cur[k])}", k, key=r.business_key, current=cur[k]))
            if not stale:
                r.errors.append(msg("ROW_STALE", f"{r.business_key} changed since export. Re-export.",
                                    None, key=r.business_key))
            continue
        r.verdict = "MATCH" if all(_same(cur[k], r.values.get(k)) for k in DF_COMPARE) else "UPDATE"
        r.plan["ref_pass"] = r.verdict == "UPDATE" and \
            any(not _same(cur[k], r.values.get(k)) for k in _REF_COLUMNS)
    for r in rows:
        if r.verdict == "INSERT":
            r.plan["ref_pass"] = r.plan["ref"] is not None

    _df_check_sets(rows, live_of)


def _df_check_sets(rows: list[Staged], live_of: dict[int, list[DataField]]) -> None:
    """Each entity's final key and relationship sets, live plus file, must stay unique, so a swap
    or a collision is a validation error and never a unique index failing mid-commit (crit. 10)."""
    in_file = {r.plan["field"].data_field_id: r for r in rows if r.plan.get("field") is not None}
    # A row whose token found no field (its error is recorded) claims nothing.
    rows = [r for r in rows if r.verdict == "INSERT" or r.plan.get("field") is not None]

    # 4a-R2: a pk_position another live field holds is an error, as entity names are; within
    # the file, two rows may not claim one position. PK swaps go through the screen.
    live_pk = {(f.data_entity_id, f.pk_ordinal): f for fs in live_of.values() for f in fs if f.is_primary_key}
    first_pk: dict[tuple[int, int], int] = {}
    for r in rows:
        parent, pk = r.plan["parent"], (r.values or {}).get("pk_position")
        if parent is None or pk is None or r.verdict == "MATCH":
            continue
        f = r.plan.get("field")
        if f is not None and f.pk_ordinal == pk:
            continue                                         # unchanged: it already holds it
        holder = live_pk.get((parent.data_entity_id, pk))
        if holder is not None and (f is None or holder.data_field_id != f.data_field_id):
            r.errors.append(msg("PK_TAKEN", f"{holder.field_name} already holds primary-key position {pk}. "
                                "Change key positions on screen.", "pk_position",
                                name=holder.field_name, position=pk))
        elif (parent.data_entity_id, pk) in first_pk:
            r.errors.append(msg("DUPLICATE_PK", f"Row {first_pk[(parent.data_entity_id, pk)]} also claims "
                                f"primary-key position {pk}.", "pk_position",
                                first_row=first_pk[(parent.data_entity_id, pk)], position=pk))
        else:
            first_pk[(parent.data_entity_id, pk)] = r.sheet_row_no

    # An entity holds at most MAX_FIELDS live fields.
    adds: dict[int, int] = {}
    for r in rows:
        if r.verdict == "INSERT" and r.plan["parent"] is not None:
            de_id = r.plan["parent"].data_entity_id
            adds[de_id] = adds.get(de_id, 0) + 1
            if len(live_of.get(de_id, [])) + adds[de_id] > de_service.MAX_FIELDS:
                r.errors.append(msg("FIELD_LIMIT", f"An entity holds at most {de_service.MAX_FIELDS} fields.",
                                    "field_name", max=de_service.MAX_FIELDS))

    # Relationships: a numeric group must exist (4a-R1) — held by a live field that keeps it —
    # and one relationship may not point at the same referenced field twice.
    def keeps(f: DataField) -> bool:
        r = in_file.get(f.data_field_id)
        if r is None or r.verdict == "MATCH":
            return True
        ref, g = r.plan["ref"], r.plan.get("group")
        return ref is not None and ref.data_entity_id == f.ref_data_entity_id and \
            g in (("num", f.fk_group_no), ("own", f.fk_group_no))

    members: dict[tuple, list[tuple[Staged | None, object]]] = {}
    for fs in live_of.values():
        for f in fs:
            if f.is_foreign_key and keeps(f) and (f.data_field_id not in in_file or
                                                  in_file[f.data_field_id].verdict == "MATCH"):
                gid = (f.data_entity_id, f.ref_data_entity_id, "n", f.fk_group_no)
                members.setdefault(gid, []).append((None, ("live", f.ref_data_field_id)
                                                    if f.ref_data_field_id else None))
    for r in rows:
        parent, ref, g = r.plan["parent"], r.plan["ref"], r.plan.get("group")
        if parent is None or ref is None or g is None or r.verdict == "MATCH":
            continue
        base = (parent.data_entity_id, ref.data_entity_id)
        if g[0] == "num":
            holders = [f for f in live_of.get(parent.data_entity_id, [])
                       if f.is_foreign_key and f.ref_data_entity_id == ref.data_entity_id
                       and f.fk_group_no == g[1] and keeps(f)]
            if not holders and not any(e["column"] == "fk_group" for e in r.errors):
                r.errors.append(msg("FK_GROUP_NOT_FOUND", f"{parent.de_number} has no stored relationship "
                                    f"{g[1]} to {ref.de_number}. A number names a stored relationship; use "
                                    "a label such as a or b to start a new one.", "fk_group",
                                    key=ref.de_number, group=str(g[1])))
                continue
            gid = (*base, "n", g[1])
            r.info["relationship"] = {"kind": "existing", "group": g[1], "to": ref.de_number,
                                      "with": [f.field_name for f in holders
                                               if f.data_field_id != (r.target_id or 0)]}
        elif g[0] == "own":
            gid = (*base, "n", g[1])
            r.info["relationship"] = {"kind": "existing", "group": g[1], "to": ref.de_number, "with": []}
        elif g[0] == "label":
            gid = (*base, "l", g[1])
            r.info["relationship"] = {"kind": "new", "label": r.cells["fk_group"], "to": ref.de_number}
        else:
            gid = (*base, "row", r.sheet_row_no)
            r.info["relationship"] = {"kind": "new", "label": None, "to": ref.de_number}
        members.setdefault(gid, []).append((r, r.plan.get("ref_field")))
    # sara M-1: a referenced field another member of the same stored relationship holds, and that
    # member's row in this file changes its reference, is a swap: the apply would hit
    # uq_df_fk_group_field mid-commit. Swaps go through the screen, as key positions do (4a-R2).
    for r in rows:
        parent, ref, g, rf = r.plan["parent"], r.plan["ref"], r.plan.get("group"), r.plan.get("ref_field")
        if r.verdict == "MATCH" or not r.plan.get("ref_pass") or parent is None or ref is None \
                or g is None or g[0] not in ("num", "own") or rf is None or rf[0] != "live":
            continue
        own_id = r.target_id or 0
        for h in live_of.get(parent.data_entity_id, []):
            hr = in_file.get(h.data_field_id)
            if h.data_field_id != own_id and h.is_foreign_key and h.ref_data_entity_id == ref.data_entity_id \
                    and h.fk_group_no == g[1] and h.ref_data_field_id == rf[1] and hr is not None \
                    and hr.verdict != "MATCH" and hr.plan.get("ref_pass"):
                r.errors.append(msg("FK_SWAP", f"{h.field_name} (row {hr.sheet_row_no}) holds that field in "
                                    "this relationship and this file changes it too. Swap relationship "
                                    "columns on screen.", "ref_field_name", name=h.field_name,
                                    first_row=hr.sheet_row_no))
                break
    for gid, ms in members.items():
        seen: dict = {}
        for r, rf in ms:
            if rf is None:
                continue
            if rf in seen and r is not None:
                r.errors.append(msg("FK_FIELD_TWICE", "This relationship already points at that field "
                                    + (f"(row {seen[rf]})." if seen[rf] else "(a live field)."),
                                    "ref_field_name", first_row=seen[rf]))
            else:
                seen.setdefault(rf, r.sheet_row_no if r is not None else None)
    # Label groups name their members, so the preview shows what each new relationship joins.
    for r in rows:
        rel = (r.info or {}).get("relationship")
        if rel and rel["kind"] == "new" and rel["label"] is not None:
            same = [o.cells["field_name"] for o in rows if o is not r and o.plan.get("group") == r.plan["group"]
                    and o.plan["parent"] == r.plan["parent"] and o.plan["ref"] == r.plan["ref"]]
            rel["with"] = same


def _df_spec(v: dict) -> dict:
    return {"data_type_code": v["data_type"], "length_val": v["length"], "precision_val": v["precision"],
            "scale_val": v["scale"], "is_mandatory": v["mandatory"],
            "is_primary_key": v["pk_position"] is not None, "pk_ordinal": v["pk_position"],
            "description": v["description"]}


def _df_apply(ctx: Ctx, rows: list[Staged]) -> None:
    """Two passes (Q7): every field without its reference, then the references, so a reference
    to a field added by this same file resolves. Numbers and ids exist only from here on."""
    db = ctx.db
    by_row = {r.sheet_row_no: r for r in rows}
    for r in rows:
        ctx.current_row = r
        v = r.values
        if r.verdict == "INSERT":
            de = db.get(DataEntity, r.plan["parent"].data_entity_id)        # held FOR NO KEY UPDATE
            r.target_id = de_service.add_field(db, ctx.actor_id, de, r.cells["field_name"],
                                               _df_spec(v)).data_field_id
        elif r.verdict == "UPDATE":
            f = db.get(DataField, r.target_id)                               # locked by re-validation
            r.before = {**_df_current(db, ctx.project_id, [f.data_field_id])[f.data_field_id],
                        "row_version": f.row_version}
            de_service.change_field(db, ctx.actor_id, f, r.target_row_version,
                                    v["field_name"] if v["field_name"] != f.field_name else None, _df_spec(v))
    label_no: dict[tuple, int] = {}
    for r in rows:
        if not r.plan.get("ref_pass"):
            continue
        ctx.current_row = r
        f = db.get(DataField, r.target_id)
        ref = r.plan["ref"]
        if ref is None:
            spec = {"ref_data_entity_id": None}
        else:
            rf = r.plan.get("ref_field")
            rf_id = None if rf is None else rf[1] if rf[0] == "live" else by_row[rf[1]].target_id
            kind, g = r.plan["group"]
            lkey = (f.data_entity_id, ref.data_entity_id, g)
            group = g if kind in ("num", "own") else label_no.get(lkey, "new") if kind == "label" else "new"
            spec = {"ref_data_entity_id": ref.data_entity_id, "ref_data_field_id": rf_id, "fk_group": group}
        de_service.change_field(db, ctx.actor_id, f, f.row_version, None, spec)
        if ref is not None and r.plan["group"][0] == "label":
            label_no.setdefault((f.data_entity_id, ref.data_entity_id, r.plan["group"][1]), f.fk_group_no)
    ctx.current_row = None


DATA_FIELD = Target("DATA_FIELD", "data-fields", "Data fields", DataField.__tablename__,
                    DF_COLUMNS, DF_COMPARE, _df_export_rows, _df_current, _df_validate, _df_apply)

# ---- shared by the slice 1e targets (spec §7.0) ----------------------------------------------

def picker_codes(db: Session, project_id: int, category: str) -> set[str]:
    """The codes a new or changed value may take: the project's picker list, hidden codes left out (D4, R5)."""
    return {r.code for r in code_master.resolve(db, project_id, category, for_picker=True)}


def changed(current, value) -> bool:
    return not _same(current, value)


ROW_CAP_1E = 2_000                                          # P7: one file, one transaction, bounded


def _links_mac(claims: str, numbers: list[str]) -> str:
    key = get_settings().row_token_key.encode()
    digest = hmac.new(key, b"vb-links|" + claims.encode() + b"|" + ",".join(numbers).encode(),
                      hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def links_cell(project_id: int, table: str, row_id: int, row_version: int, numbers) -> str:
    """The signed links-at-export cell (§7.4, N2): the BR numbers linked when the row was exported, and a MAC over
    the row token's claims plus that list — so a cell copied to another row, or edited, does not verify."""
    nums = sorted(set(numbers))
    claims = f"{TOKEN_VERSION}.{project_id}.{table}.{row_id}.{row_version}"
    return f"{', '.join(nums)} | {_links_mac(claims, nums)}"


def read_links_cell(cell: str | None, tok: Claims) -> list[str] | None:
    """The BR numbers a genuine links-at-export cell carries for this token's row, or None."""
    if cell is None:
        return None
    listed, sep, mac = cell.rpartition("|")
    if not sep:
        return None
    nums = sorted({n.strip().upper() for n in listed.split(",") if n.strip()})
    claims = f"{TOKEN_VERSION}.{tok.project_id}.{tok.table}.{tok.row_id}.{tok.row_version}"
    return nums if hmac.compare_digest(_links_mac(claims, nums), mac.strip()) else None


def br_list(value: str | None) -> list[str]:
    """A br_numbers cell: comma, semicolon or line separated, upper-cased; duplicates dropped, first order kept."""
    out: list[str] = []
    for part in re.split(r"[,;\n]", value or ""):
        n = part.strip().upper()
        if n and n not in out:
            out.append(n)
    return out


def live_brs(db: Session, project_id: int, numbers, lock: bool = False) -> dict[str, BusinessRequirement]:
    """This project's live BRs by number; FOR SHARE at commit, so a retire waits."""
    if not numbers:
        return {}
    q = select(BusinessRequirement).where(BusinessRequirement.project_id == project_id, BusinessRequirement.is_active,
                                          BusinessRequirement.br_number.in_(sorted(set(numbers))))
    if lock:
        q = q.with_for_update(read=True, of=BusinessRequirement)
    return {br.br_number: br for br in db.scalars(q.order_by(BusinessRequirement.br_number))}


def check_links(r: Staged, live_numbers: set[str], at_export: list[str] | None, cell: list[str],
                found: dict[str, BusinessRequirement]) -> list[str]:
    """§7.0 "BRs to add" (P5, D1, N6) for an existing row: returns the additions; errors and warnings go on the row.
    `live_numbers` are the BRs linked now; `at_export` the signed cell's list."""
    key = r.business_key
    if at_export is None:
        r.errors.append(msg("LINKS_TOKEN_INVALID", "The links-at-export cell is not one VB issued, or it was edited. "
                            "Re-export.", "br_links_at_export", key=key))
        return []
    removed = [n for n in cell if n in at_export and n not in live_numbers]
    for n in removed:                                       # N6: only when the file still lists it
        r.errors.append(msg("ROW_STALE", f"{n} was unlinked on screen since your export. Re-export.", "br_numbers",
                            key=key, br=n))
    omitted = [n for n in at_export if n not in cell and n in live_numbers]
    if omitted:
        r.warnings.append(msg("LINKS_ADD_ONLY", f"Links are only added by file: {', '.join(omitted)} stays linked. "
                              "Remove a link on screen.", "br_numbers", brs=", ".join(omitted)))
    adds = [n for n in cell if n not in at_export and n not in live_numbers]
    for n in adds:
        if n not in found:
            r.errors.append(msg("NOT_FOUND", f"{n} is not a live BR of this project.", "br_numbers", key=n))
    return [n for n in adds if n in found] if not removed else []


def reupload_warning(db: Session, project_id: int, target: "Target", sha: str) -> dict | None:
    """P1: the same file committed before to this project and target — named by date and committer."""
    hit = db.execute(select(AuditEvent.occurred_at, AppUser.display_name)
                     .outerjoin(AppUser, AppUser.app_user_id == AuditEvent.app_user_id)
                     .where(AuditEvent.event_type == "IMPORT_COMMITTED", AuditEvent.project_id == project_id,
                            AuditEvent.detail["file_sha256"].astext == sha,
                            AuditEvent.detail["entity"].astext == target.code)
                     .order_by(AuditEvent.occurred_at.desc()).limit(1)).first()
    if hit is None:
        return None
    when, who = hit
    return msg("FILE_COMMITTED_BEFORE", f"This exact file was committed on {when:%Y-%m-%d} by {who or 'someone'}. "
               "Re-export before editing again.", None, date=f"{when:%Y-%m-%d}", by=who)


# ---- BUSINESS_REQUIREMENT (slice 1e-a, spec §7.1) -----------------------------------------------

BR_COLUMNS = (
    Column("br_number", "BR number", max_len=20, width=12),
    Column("hier_code", "Chart code (check only)", max_len=40, width=12),
    Column("step_name", "Process step (read only)", max_len=200, width=32),
    Column("br_statement", "Statement", max_len=8000, width=60),
    Column("status_code", "Status", max_len=40, category="BR_STATUS", width=16),
    Column("row_token", "Row token (do not edit)", max_len=200, protected=True, width=14),
)
BR_COMPARE = ("br_statement", "status_code")


def _brs_with_steps(db: Session, project_id: int, numbers: list[str] | None = None, lock: bool = False):
    """(BR, its step) for this project's live BRs — every one, or those numbered; locked for a commit."""
    q = (select(BusinessRequirement, BfcNode)
         .join(BfcNode, (BfcNode.bfc_node_id == BusinessRequirement.bfc_node_id)
               & (BfcNode.project_id == BusinessRequirement.project_id))
         .where(BusinessRequirement.project_id == project_id, BusinessRequirement.is_active)
         .order_by(BusinessRequirement.br_number))
    if numbers is not None:
        q = q.where(BusinessRequirement.br_number.in_(numbers))
    if lock:
        q = q.with_for_update(of=BusinessRequirement)
    return db.execute(q.execution_options(populate_existing=True)).all()


def _br_values(br) -> dict:
    return {"br_statement": br.br_statement, "status_code": br.status_code}


def _br_export_rows(db: Session, project_id: int) -> list[dict]:
    return [{"br_number": br.br_number, "hier_code": node.hier_code, "step_name": node.node_name, **_br_values(br),
             "row_token": row_token(project_id, BusinessRequirement.__tablename__, br.br_id, br.row_version)}
            for br, node in _brs_with_steps(db, project_id)]


def _br_current(db: Session, project_id: int, ids: list[int]) -> dict[int, dict]:
    if not ids:
        return {}
    rows = db.scalars(select(BusinessRequirement).where(BusinessRequirement.project_id == project_id,
                                                       BusinessRequirement.br_id.in_(ids)))
    return {br.br_id: _br_values(br) for br in rows}


def _br_validate(ctx: Ctx, rows: list[Staged]) -> None:
    first: dict[str, int] = {}
    for r in rows:
        number = r.cells["br_number"]
        if number is None:
            if not any(e["column"] == "br_number" for e in r.errors):
                r.errors.append(msg("BR_NUMBER_REQUIRED", "BRs are created with their step — use the flow import "
                                    "to add steps.", "br_number"))
            continue
        number = r.cells["br_number"] = number.strip().upper()
        if number in first:
            r.errors.append(msg("DUPLICATE_KEY", f"{number} also appears on row {first[number]}.", "br_number",
                                key=number, first_row=first[number]))
            continue
        first[number] = r.sheet_row_no
        r.business_key = number
    found = {br.br_number: (br, node) for br, node in
             _brs_with_steps(ctx.db, ctx.project_id, sorted(first), lock=ctx.for_commit)} if first else {}
    statuses = picker_codes(ctx.db, ctx.project_id, "BR_STATUS")
    for r in rows:
        number = r.business_key
        if number is None or r.errors:
            continue
        hit = found.get(number)
        if hit is None:
            r.errors.append(msg("NOT_FOUND", f"{number} is not a live BR of this project.", "br_number", key=number))
            continue
        br, node = hit
        tok = r.token
        if tok is None:
            if r.cells["row_token"] is None:
                r.errors.append(msg("EXPORT_FIRST", f"{number}: export first to update. A BR row needs the row "
                                    "token from an export.", "br_number", key=number))
            continue
        if tok.row_id != br.br_id:
            r.errors.append(msg("TOKEN_ROW_MISMATCH", f"This row's token belongs to another BR, not {number}: the "
                                "rows were sorted or shifted. Re-export.", "br_number", key=number))
            continue
        current = _br_values(br)
        if br.row_version != tok.row_version:
            stale = [k for k in BR_COMPARE if changed(current[k], r.cells[k])]
            if stale == ["status_code"] and current["status_code"] in br_service.SYSTEM_SET_STATUSES:     # D6
                r.errors.append(msg("FROZEN_SINCE_EXPORT", f"{number}: a baseline was frozen since your export. "
                                    "Re-export.", "status_code", key=number))
            elif stale:
                for k in stale:
                    r.errors.append(msg("ROW_STALE", f"{number} changed since export. Current value: "
                                        f"{_q(current[k])}", k, key=number, current=current[k]))
            else:
                r.errors.append(msg("ROW_STALE", f"{number} changed since export. Re-export.", None, key=number))
            continue
        if r.cells["hier_code"] is not None and r.cells["hier_code"] != node.hier_code:
            r.errors.append(msg("MOVED_SINCE_EXPORT", f"{number} moved since export: now {node.hier_code}, file "
                                f"says {r.cells['hier_code']}. Re-export.", "hier_code", key=number,
                                current=node.hier_code))                              # R2-D1, criterion 117
            continue
        if r.cells["step_name"] is not None and changed(node.node_name, r.cells["step_name"]):
            r.warnings.append(msg("STEP_NAME_IGNORED", "Step names change on the chart; this one was ignored.",
                                  "step_name"))
        r.target_id, r.target_row_version = br.br_id, br.row_version
        diff = [k for k in BR_COMPARE if changed(current[k], r.cells[k])]
        if "br_statement" in diff and r.cells["br_statement"] is None:
            r.errors.append(msg("REQUIRED", "A BR's statement cannot be cleared.", "br_statement"))
        if "status_code" in diff:
            new = r.cells["status_code"]
            if new is None:
                r.errors.append(msg("REQUIRED", "A BR needs a status.", "status_code"))
            elif new in br_service.SYSTEM_SET_STATUSES:
                r.errors.append(msg("SYSTEM_SET", f"{new} is set by the baseline freeze, not by hand.",
                                    "status_code", value=new))
            elif new not in statuses:
                r.errors.append(msg("CODE_UNKNOWN", f"{_q(new)} is not a status this project offers.",
                                    "status_code", value=new))
        r.verdict = "UPDATE" if diff else "MATCH"


def _br_apply(ctx: Ctx, rows: list[Staged]) -> None:
    for r in rows:
        if r.verdict != "UPDATE":
            continue
        ctx.current_row = r
        br = ctx.db.get(BusinessRequirement, r.target_id)                # locked by the re-validation
        current = _br_values(br)
        r.before = {**current, "row_version": br.row_version}
        fields = {"br_statement": r.cells["br_statement"]} if changed(current["br_statement"],
                                                                       r.cells["br_statement"]) else {}
        status = r.cells["status_code"] if changed(current["status_code"], r.cells["status_code"]) else None
        br_service.update_br(ctx.db, ctx.actor_id, br, r.target_row_version, fields, status, commit=False)
    ctx.current_row = None


BUSINESS_REQUIREMENT = Target("BUSINESS_REQUIREMENT", "business-requirements", "Business requirements",
                              "business_requirement", BR_COLUMNS, BR_COMPARE, _br_export_rows, _br_current,
                              _br_validate, _br_apply, max_rows=ROW_CAP_1E, reupload_warning=True)


# ---- FUNCTION_REQUIREMENT (slice 1e-a, spec §7.2, round-2 N1/N3/N5/N6) ---------------------------------------------

FR_COLUMNS = (
    Column("fr_number", "FR number (blank = new)", max_len=20, width=12),
    Column("fr_name", "Name", max_len=200, width=36),
    Column("fr_type_code", "Type", max_len=40, category="FR_TYPE", width=16),
    Column("complexity_code", "Complexity", max_len=40, category="FR_COMPLEXITY", width=14),
    Column("solution_number", "Solution number", max_len=20, width=14),
    Column("br_numbers", "BRs (add only)", max_len=4000, width=24),
    Column("br_links_at_export", "BRs at export (do not edit)", max_len=4000, protected=True, width=14),
    Column("description", "Description", max_len=4000, width=48),
    Column("acceptance_note", "Acceptance note", max_len=4000, width=36),
    Column("status_code", "Status", max_len=40, category="FR_FULFILMENT_STATUS", width=16),
    Column("effort_days", "Effort days (read only)", max_len=40, width=12),
    Column("interface_source_app", "Interface source (read only)", max_len=40, width=14),
    Column("interface_target_app", "Interface target (read only)", max_len=40, width=14),
    Column("row_token", "Row token (do not edit)", max_len=200, protected=True, width=14),
)
FR_VALUES = ("fr_name", "fr_type_code", "complexity_code", "solution_number", "description", "acceptance_note",
             "status_code")
FR_COMPARE = (*FR_VALUES, "links_added")                  # the preview's "links added: BR-0007" (P5)
FR_DEFAULT_STATUS = "SPECIFIED"                           # what create_fr sets


def _fr_values(fr: FunctionRequirement) -> dict:
    return {"fr_name": fr.fr_name, "fr_type_code": fr.fr_type_code, "complexity_code": fr.complexity_code,
            "solution_number": fr.solution_row.solution_number if fr.solution_row else None,
            "description": fr.description, "acceptance_note": fr.acceptance_note,
            "status_code": fr.fulfilment_status_code, "links_added": None}


def _fr_links(db: Session, fr_ids: list[int]) -> dict[int, list[str]]:
    """Each FR's live BR links, by BR number."""
    out: dict[int, list[str]] = {i: [] for i in fr_ids}
    if fr_ids:
        for fr_id, number in db.execute(
                select(BrFunctionRequirement.fr_id, BusinessRequirement.br_number)
                .join(BusinessRequirement, BusinessRequirement.br_id == BrFunctionRequirement.br_id)
                .where(BrFunctionRequirement.fr_id.in_(fr_ids), BrFunctionRequirement.is_active,
                       BusinessRequirement.is_active).order_by(BusinessRequirement.br_number)):
            out[fr_id].append(number)
    return out


def _frs(db: Session, project_id: int, numbers: list[str] | None = None, lock: bool = False):
    q = (select(FunctionRequirement).where(FunctionRequirement.project_id == project_id, FunctionRequirement.is_active)
         .order_by(FunctionRequirement.fr_number))
    if numbers is not None:
        q = q.where(FunctionRequirement.fr_number.in_(numbers))
    if lock:
        q = q.with_for_update(of=FunctionRequirement)
    return list(db.scalars(q.execution_options(populate_existing=True)))


def _fr_export_rows(db: Session, project_id: int) -> list[dict]:
    frs = _frs(db, project_id)
    links = _fr_links(db, [f.fr_id for f in frs])
    ifaces = {fi.fr_id: fi for fi in db.scalars(select(FrInterface).where(FrInterface.project_id == project_id,
                                                                         FrInterface.is_active))}
    table = FunctionRequirement.__tablename__
    out = []
    for fr in frs:
        fi = ifaces.get(fr.fr_id)
        v = {k: x for k, x in _fr_values(fr).items() if k != "links_added"}
        out.append({"fr_number": fr.fr_number, **v, "br_numbers": ", ".join(links[fr.fr_id]),
                    "br_links_at_export": links_cell(project_id, table, fr.fr_id, fr.row_version, links[fr.fr_id]),
                    "effort_days": str(fr.effort_days) if fr.effort_days is not None else None,
                    "interface_source_app": fi.source_row.application_code if fi else None,     # Q-2: read only
                    "interface_target_app": fi.target_row.application_code if fi else None,
                    "row_token": row_token(project_id, table, fr.fr_id, fr.row_version)})
    return out


def _fr_current(db: Session, project_id: int, ids: list[int]) -> dict[int, dict]:
    if not ids:
        return {}
    rows = db.scalars(select(FunctionRequirement).where(FunctionRequirement.project_id == project_id,
                                                       FunctionRequirement.fr_id.in_(ids)))
    return {fr.fr_id: _fr_values(fr) for fr in rows}


def _codes_by(db: Session, project_id: int, category: str) -> dict[str, CodeMaster]:
    return {c.code: c for c in code_master.resolve(db, project_id, category)}


def _token_checks(r: Staged, row, row_id: int, number: str, what: str) -> bool:
    """The DATA_ENTITY token rules for a numbered row: True when the row may go on."""
    tok = r.token
    if tok is None:
        if r.cells["row_token"] is None:
            r.errors.append(msg("EXPORT_FIRST", f"{number}: export first to update. {what} row needs the row token "
                                "from an export.", r.token_key, key=number))
        return False
    if tok.row_id != row_id:
        r.errors.append(msg("TOKEN_ROW_MISMATCH", f"This row's token belongs to another record, not {number}: the "
                            "rows were sorted or shifted. Re-export.", r.token_key, key=number))
        return False
    if row.row_version != tok.row_version:
        r.errors.append(msg("ROW_STALE", f"{number} changed since export. Re-export.", None, key=number))
        return False
    return True


def _numbered(rows: list[Staged], key: str, noun: str) -> list[str]:
    """Upper-case the key, mark UPDATE / INSERT, refuse a key twice; the keys found, in order."""
    first: dict[str, int] = {}
    for r in rows:
        r.token_key = key
        number = r.cells[key]
        if number is not None:
            number = r.cells[key] = number.strip().upper()
        r.verdict = "UPDATE" if number else "INSERT"
        if not number:
            if r.token is not None:
                r.errors.append(msg("TOKEN_ROW_MISMATCH", f"This row has a row token but no {noun} number: the rows "
                                    "were shifted. Re-export.", key))
            continue
        if number in first:
            r.errors.append(msg("DUPLICATE_KEY", f"{number} also appears on row {first[number]}.", key,
                                key=number, first_row=first[number]))
            continue
        first[number] = r.sheet_row_no
        r.business_key = number
    return sorted(first)


def _fr_validate(ctx: Ctx, rows: list[Staged]) -> None:
    db, pid = ctx.db, ctx.project_id
    numbers = _numbered(rows, "fr_number", "FR")
    for r in rows:
        if r.cells["fr_name"] is None:
            r.errors.append(msg("REQUIRED", "An FR needs a name.", "fr_name"))
    found = {fr.fr_number: fr for fr in _frs(db, pid, numbers, lock=ctx.for_commit)} if numbers else {}
    links_now = _fr_links(db, [fr.fr_id for fr in found.values()])
    on = components.enabled(db, pid)
    types, cxs = _codes_by(db, pid, "FR_TYPE"), _codes_by(db, pid, "FR_COMPLEXITY")
    pick = {c: picker_codes(db, pid, c) for c in ("FR_TYPE", "FR_COMPLEXITY", "FR_FULFILMENT_STATUS")}
    brs = live_brs(db, pid, {n for r in rows for n in br_list(r.cells["br_numbers"])}, lock=ctx.for_commit)
    sol_numbers = sorted({r.cells["solution_number"].strip().upper() for r in rows if r.cells["solution_number"]})
    sols = {s.solution_number: s for s in db.scalars(select(Solution).where(
        Solution.project_id == pid, Solution.is_active, Solution.solution_number.in_(sol_numbers)))} \
        if sol_numbers else {}

    def code_ok(r: Staged, col: str, category: str, value: str) -> None:
        if value not in pick[category]:
            r.errors.append(msg("CODE_UNKNOWN", f"{_q(value)} is not a value this project offers here.", col,
                                value=value))

    for r in rows:
        c = r.cells
        if any(e["column"] in ("row_token", "fr_number") for e in r.errors):
            continue
        fr = None
        if r.verdict == "UPDATE":
            fr = found.get(r.business_key)
            if fr is None:
                r.errors.append(msg("NOT_FOUND", f"{r.business_key} is not a live FR of this project.", "fr_number",
                                    key=r.business_key))
                continue
            if not _token_checks(r, fr, fr.fr_id, r.business_key, "An FR"):
                continue
            r.target_id, r.target_row_version = fr.fr_id, fr.row_version

        cur = _fr_values(fr) if fr else dict.fromkeys(FR_COMPARE)
        v = {k: c[k] for k in FR_VALUES}
        if v["solution_number"] is not None:
            v["solution_number"] = v["solution_number"].strip().upper()
        if fr is not None:                               # Q-5, N3, N5: a blank is "unchanged", never "cleared"
            for k in ("solution_number", "complexity_code"):
                if v[k] is None:
                    v[k] = cur[k]
        elif v["status_code"] is None:
            v["status_code"] = FR_DEFAULT_STATUS
        diff = {k for k in FR_VALUES if changed(cur[k], v[k])}

        # codes: only a new or changed value is checked against the picker list (§7.0, D4, R5)
        if "fr_type_code" in diff or fr is None:
            if v["fr_type_code"] is None:
                r.errors.append(msg("REQUIRED", "An FR needs a type.", "fr_type_code"))          # N1
            else:
                code_ok(r, "fr_type_code", "FR_TYPE", v["fr_type_code"])
        if "status_code" in diff:
            if v["status_code"] is None:
                r.errors.append(msg("REQUIRED", "An FR needs a status.", "status_code"))
            else:
                code_ok(r, "status_code", "FR_FULFILMENT_STATUS", v["status_code"])          # Q-7: honoured
        rating = "complexity_code" in diff and v["complexity_code"] is not None
        if rating:
            code_ok(r, "complexity_code", "FR_COMPLEXITY", v["complexity_code"])
            if "EFFORT" not in on:
                r.errors.append(msg("COMPONENT_OFF", "Rating complexity needs the Effort component, which is off "
                                    "in this project.", "complexity_code", component="EFFORT"))      # S1

        # links: "BRs to add" (§7.0, P5, D1, N6)
        cell = br_list(c["br_numbers"])
        if fr is None:
            for n in cell:
                if n not in brs:
                    r.errors.append(msg("NOT_FOUND", f"{n} is not a live BR of this project.", "br_numbers", key=n))
            adds = [n for n in cell if n in brs]
            final_ids = [brs[n].br_id for n in adds]
        else:
            live_now = set(links_now[fr.fr_id])
            adds = check_links(r, live_now, read_links_cell(c["br_links_at_export"], r.token), cell, brs)
            final_ids = _br_ids_of(db, fr.fr_id) + [brs[n].br_id for n in adds]
            if adds:
                diff.add("links_added")
        v["links_added"] = ", ".join(adds) or None
        if adds:
            r.pins["br_numbers"] = ",".join(str(brs[n].br_id) for n in adds)
        if not final_ids:
            r.warnings.append(msg("NO_BR", "No BR: this FR will not trace.", "br_numbers"))   # D-28; none for SOL

        # solution: a live SOL- of this project (never created, D-34), answering one of the final BRs (Q-3)
        if v["solution_number"] is not None and ("solution_number" in diff):
            sol = sols.get(v["solution_number"])
            if sol is None:
                r.errors.append(msg("NOT_FOUND", f"{v['solution_number']} is not a live solution of this project.",
                                    "solution_number", key=v["solution_number"]))
            elif "SOLUTION" not in on:
                r.errors.append(msg("COMPONENT_OFF", "Tagging a solution needs the Solution component, which is "
                                    "off in this project.", "solution_number", component="SOLUTION"))   # S1
            else:
                r.pins["solution_number"] = sol.solution_id
                if final_ids and not db.scalar(select(func.count()).select_from(BrSolution).where(
                        BrSolution.solution_id == sol.solution_id, BrSolution.is_active,
                        BrSolution.br_id.in_(final_ids))):
                    r.errors.append(msg("SOLUTION_ANSWERS_NO_BR", f"{sol.solution_number} answers none of this "
                                        "row's BRs. Add it to one of them first.", "solution_number",
                                        key=sol.solution_number))

        # type and complexity: the rate cells update_fr and rate_fr will need (P3c, N1, criterion 124)
        final_type = fr.fr_type_code_row if fr is not None and "fr_type_code" not in diff else \
            types.get(v["fr_type_code"])
        if fr is not None and "fr_type_code" in diff and final_type is not None:
            if (fr.fr_type_behaviour == "INTERFACE" and final_type.behaviour_code != "INTERFACE"   # behaviour
                    and interface.live_detail_exists(db, fr.fr_id)):
                r.errors.append(msg("INTERFACE_DETAIL", f"{fr.fr_number} has interface detail. Remove it on screen "
                                    "first, or keep an interface type.", "fr_type_code"))
            if fr.complexity_code_id is not None and \
                    effort.rate_for(db, pid, final_type.code_id, fr.complexity_code_id, lock=False) is None:
                r.errors.append(msg("NO_RATE_CELL", f"No rate card entry for {final_type.label} × "
                                    f"{fr.complexity_code_row.label}.", "fr_type_code"))
        if rating and final_type is not None and v["complexity_code"] in cxs:
            if not final_type.is_active:
                r.errors.append(msg("TYPE_RETIRED", "This FR's type is retired: change the type first.",
                                    "complexity_code"))                                          # N1
            elif effort.rate_for(db, pid, final_type.code_id, cxs[v["complexity_code"]].code_id, lock=False) is None:
                r.errors.append(msg("NO_RATE_CELL", f"No rate card entry for {final_type.label} × "
                                    f"{cxs[v['complexity_code']].label}.", "complexity_code"))
        stored_days = str(fr.effort_days) if fr is not None and fr.effort_days is not None else None
        if "EFFORT" in on and c["effort_days"] is not None and changed(stored_days, c["effort_days"]):
            r.warnings.append(msg("EFFORT_DERIVED", "Effort days are derived from the rate card; your value was "
                                  "ignored.", "effort_days"))

        r.values = v
        if fr is not None:
            r.verdict = "UPDATE" if diff else "MATCH"

    # P1: a new row whose name and type match a live FR's — a warning, not a block (Q-6)
    new = [r for r in rows if r.verdict == "INSERT" and r.cells["fr_name"] is not None]
    if new:
        live = db.execute(select(func.lower(func.btrim(FunctionRequirement.fr_name)), CodeMaster.code,
                                 FunctionRequirement.fr_number)
                          .join(CodeMaster, CodeMaster.code_id == FunctionRequirement.fr_type_code_id)
                          .where(FunctionRequirement.project_id == pid, FunctionRequirement.is_active)).all()
        by_key = {(n, t): num for n, t, num in live}
        for r in new:
            hit = by_key.get((r.cells["fr_name"].strip().lower(), r.cells["fr_type_code"]))
            if hit:
                r.warnings.append(msg("POSSIBLE_DUPLICATE", f"{hit} already has this name and type.", "fr_name",
                                      key=hit))


def _br_ids_of(db: Session, fr_id: int) -> list[int]:
    return list(db.scalars(select(BrFunctionRequirement.br_id)
                           .join(BusinessRequirement, BusinessRequirement.br_id == BrFunctionRequirement.br_id)
                           .where(BrFunctionRequirement.fr_id == fr_id, BrFunctionRequirement.is_active,
                                  BusinessRequirement.is_active)))


def _fr_apply(ctx: Ctx, rows: list[Staged]) -> None:
    """P3a/b: create (with the first link) → the other links → update_fr (solution, status, type, text) → rate_fr.
    Each call takes the FR's current row_version (P3d)."""
    db, pid = ctx.db, ctx.project_id
    for r in rows:
        if r.verdict not in ("INSERT", "UPDATE"):
            continue
        ctx.current_row = r
        v = r.values
        add_ids = [int(i) for i in r.pins["br_numbers"].split(",")] if r.pins.get("br_numbers") else []
        if r.verdict == "INSERT":
            fields = {"description": v["description"], "acceptance_note": v["acceptance_note"]}
            fr, _ = fr_service.create_fr(db, ctx.actor_id, pid, v["fr_name"], v["fr_type_code"], None, fields,
                                         br_id=add_ids[0] if add_ids else None, commit=False)
            r.target_id, add_ids = fr.fr_id, add_ids[1:]
            cur = {**dict.fromkeys(FR_VALUES), "fr_type_code": v["fr_type_code"], "status_code": FR_DEFAULT_STATUS,
                   "fr_name": v["fr_name"], "description": v["description"], "acceptance_note": v["acceptance_note"]}
        else:
            fr = db.get(FunctionRequirement, r.target_id)                   # locked by the re-validation
            cur = _fr_values(fr)
            r.before = {**cur, "row_version": fr.row_version}
        added = [fr_service.link_fr(db, ctx.actor_id, db.get(BusinessRequirement, br_id), fr.fr_id, None,
                                    commit=False, drift=False)[0].br_function_requirement_id for br_id in add_ids]
        if added and r.before is not None:
            r.before["links_added_ids"] = added                             # P6: kept for a manual reversal
        texts = {k: v[k] for k in fr_service.EDITABLE if changed(cur[k], v[k])}
        extra = {"solution_id": r.pins["solution_number"]} if "solution_number" in r.pins else {}
        new_type = v["fr_type_code"] if changed(cur["fr_type_code"], v["fr_type_code"]) else None
        status = v["status_code"] if changed(cur["status_code"], v["status_code"]) else None
        if texts or extra or new_type or status:
            fr, _ = fr_service.update_fr(db, ctx.actor_id, fr, fr.row_version, texts, new_type, status,
                                         commit=False, **extra)
        if v["complexity_code"] is not None and changed(cur["complexity_code"], v["complexity_code"]):
            effort.rate_fr(db, ctx.actor_id, fr, fr.row_version, v["complexity_code"], commit=False)
    ctx.current_row = None


FUNCTION_REQUIREMENT = Target("FUNCTION_REQUIREMENT", "function-requirements", "Function requirements",
                              FunctionRequirement.__tablename__, FR_COLUMNS, FR_COMPARE, _fr_export_rows,
                              _fr_current, _fr_validate, _fr_apply, component="FUNCTION_REQUIREMENT",
                              max_rows=ROW_CAP_1E, reupload_warning=True)


# ---- ISSUE (slice 1e-a, spec §7.3, round-2 N1/N4/N8) --------------------------------------------------------------

def as_iso_date(value):
    """A date cell, or YYYY-MM-DD typed as text (D10) → ISO text; anything else is refused."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.time() != time(0):
            raise ValueError("A date as YYYY-MM-DD.")
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value.strip()):
        try:
            return date.fromisoformat(value.strip()).isoformat()
        except ValueError:
            pass
    raise ValueError("A date as YYYY-MM-DD.")


ISSUE_COLUMNS = (
    Column("issue_number", "Issue number (blank = new)", max_len=20, width=12),
    Column("title", "Title", max_len=200, width=36),
    Column("description", "Description", max_len=20000, width=48),
    Column("issue_type_code", "Type", max_len=40, category="ISSUE_TYPE", width=14),
    Column("severity_code", "Severity", max_len=40, category="ISSUE_SEVERITY", width=12),
    Column("status_code", "Status (open statuses only)", max_len=40, category="ISSUE_STATUS", width=16),
    Column("raised_by", "Raised by (stakeholder name)", max_len=200, width=24),
    Column("raised_by_org_unit", "Raiser's org unit code (blank = none)", max_len=30, width=16),
    Column("raised_date", "Raised date (YYYY-MM-DD)", parse=as_iso_date, width=14),
    Column("target_date", "Target date (YYYY-MM-DD)", parse=as_iso_date, width=14),
    Column("br_numbers", "BRs (add only)", max_len=4000, width=24),
    Column("br_links_at_export", "BRs at export (do not edit)", max_len=4000, protected=True, width=14),
    Column("row_token", "Row token (do not edit)", max_len=200, protected=True, width=14),
)
ISSUE_VALUES = ("title", "description", "issue_type_code", "severity_code", "status_code", "raised_by",
                "raised_by_org_unit", "raised_date", "target_date")
ISSUE_COMPARE = (*ISSUE_VALUES, "links_added")
ISSUE_DEFAULT_STATUS = "OPEN"                             # what raise_issue sets (pinned, I-1)
OPEN_ISSUE = issue_service.OPEN                           # branch on behaviour, never a code (law 5)


def _stakeholders(db: Session, project_id: int, ids=None, lock: bool = False) -> dict[int, tuple]:
    """Stakeholder id → (name, org unit code or None, is_active); every one of the project's when `ids` is None."""
    q = (select(Stakeholder.stakeholder_id, Stakeholder.stakeholder_name, OrgUnit.org_unit_code, Stakeholder.is_active)
         .outerjoin(OrgUnit, OrgUnit.org_unit_id == Stakeholder.org_unit_id)
         .where(Stakeholder.project_id == project_id))
    if ids is not None:
        q = q.where(Stakeholder.stakeholder_id.in_(sorted(set(ids)) or [-1]))
    if lock:
        q = q.with_for_update(read=True, of=Stakeholder)
    return {sid: (name, unit, live) for sid, name, unit, live in db.execute(q)}


def _fold(value: str | None) -> str | None:
    """How a raiser cell is compared: trimmed, case-folded — the unique index's own rule (I-16)."""
    return value.strip().lower() if value and value.strip() else None


def _issue_values(issue: Issue, stk: dict[int, tuple]) -> dict:
    name, unit, _ = stk.get(issue.raised_by_stakeholder_id, (None, None, None))
    return {"title": issue.title, "description": issue.description, "issue_type_code": issue.issue_type_code,
            "severity_code": issue.severity_code, "status_code": issue.status_code, "raised_by": name,
            "raised_by_org_unit": unit,
            "raised_date": issue.raised_date.isoformat() if issue.raised_date else None,
            "target_date": issue.target_date.isoformat() if issue.target_date else None, "links_added": None}


def _issue_links(db: Session, issue_ids: list[int]) -> dict[int, list[str]]:
    """Each issue's live BR links, by BR number."""
    out: dict[int, list[str]] = {i: [] for i in issue_ids}
    if issue_ids:
        for issue_id, number in db.execute(
                select(IssueBr.issue_id, BusinessRequirement.br_number)
                .join(BusinessRequirement, BusinessRequirement.br_id == IssueBr.br_id)
                .where(IssueBr.issue_id.in_(issue_ids), IssueBr.is_active, BusinessRequirement.is_active)
                .order_by(BusinessRequirement.br_number)):
            out[issue_id].append(number)
    return out


def _issues(db: Session, project_id: int, numbers: list[str] | None = None, lock: bool = False) -> list[Issue]:
    q = select(Issue).where(Issue.project_id == project_id, Issue.is_active).order_by(Issue.issue_number)
    if numbers is not None:
        q = q.where(Issue.issue_number.in_(numbers))
    if lock:
        q = q.with_for_update(of=Issue)
    return list(db.scalars(q.execution_options(populate_existing=True)).unique())


def _issue_export_rows(db: Session, project_id: int) -> list[dict]:
    issues = _issues(db, project_id)
    links = _issue_links(db, [i.issue_id for i in issues])
    stk = _stakeholders(db, project_id, [i.raised_by_stakeholder_id for i in issues])
    table = Issue.__tablename__
    out = []
    for i in issues:
        v = {k: x for k, x in _issue_values(i, stk).items() if k != "links_added"}
        out.append({"issue_number": i.issue_number, **v, "br_numbers": ", ".join(links[i.issue_id]),
                    "br_links_at_export": links_cell(project_id, table, i.issue_id, i.row_version, links[i.issue_id]),
                    "row_token": row_token(project_id, table, i.issue_id, i.row_version)})
    return out


def _issue_current(db: Session, project_id: int, ids: list[int]) -> dict[int, dict]:
    if not ids:
        return {}
    issues = list(db.scalars(select(Issue).where(Issue.project_id == project_id, Issue.issue_id.in_(ids))).unique())
    stk = _stakeholders(db, project_id, [i.raised_by_stakeholder_id for i in issues])
    return {i.issue_id: _issue_values(i, stk) for i in issues}


def _issue_validate(ctx: Ctx, rows: list[Staged]) -> None:
    db, pid = ctx.db, ctx.project_id
    numbers = _numbered(rows, "issue_number", "issue")
    for r in rows:
        if r.cells["title"] is None:
            r.errors.append(msg("REQUIRED", "An issue needs a title.", "title"))
        if r.cells["raised_date"] is None and not any(e["column"] == "raised_date" for e in r.errors):
            r.errors.append(msg("REQUIRED", "An issue needs a raised date (YYYY-MM-DD).", "raised_date"))  # D10
    found = {i.issue_number: i for i in _issues(db, pid, numbers, lock=ctx.for_commit)} if numbers else {}
    links_now = _issue_links(db, [i.issue_id for i in found.values()])
    statuses = _codes_by(db, pid, "ISSUE_STATUS")
    pick = {c: picker_codes(db, pid, c) for c in ("ISSUE_TYPE", "ISSUE_SEVERITY", "ISSUE_STATUS")}
    brs = live_brs(db, pid, {n for r in rows for n in br_list(r.cells["br_numbers"])}, lock=ctx.for_commit)
    stk = _stakeholders(db, pid, lock=ctx.for_commit)
    live_by: dict[tuple, list[int]] = {}                   # (name, unit) folded → live stakeholder ids
    for sid, (name, unit, is_live) in stk.items():
        if is_live:
            live_by.setdefault((_fold(name), _fold(unit)), []).append(sid)

    def named(ids) -> str:
        return ", ".join(f"{stk[s][0]} ({stk[s][1] or 'no unit'})" for s in sorted(ids))

    def code_ok(r: Staged, col: str, category: str, value: str) -> None:
        if value not in pick[category]:
            r.errors.append(msg("CODE_UNKNOWN", f"{_q(value)} is not a value this project offers here.", col,
                                value=value))

    for r in rows:
        c = r.cells
        if any(e["column"] in ("row_token", "issue_number") for e in r.errors):
            continue
        issue = None
        if r.verdict == "UPDATE":
            issue = found.get(r.business_key)
            if issue is None:
                r.errors.append(msg("NOT_FOUND", f"{r.business_key} is not a live issue of this project.",
                                    "issue_number", key=r.business_key))
                continue
            if not _token_checks(r, issue, issue.issue_id, r.business_key, "An issue"):
                continue
            r.target_id, r.target_row_version = issue.issue_id, issue.row_version

        cur = _issue_values(issue, stk) if issue else dict.fromkeys(ISSUE_COMPARE)
        v = {k: c[k] for k in ISSUE_VALUES}
        if issue is None and v["status_code"] is None:
            v["status_code"] = ISSUE_DEFAULT_STATUS

        # raiser (D3, N8): an unchanged raiser keeps its id; otherwise name + unit match exactly one live stakeholder
        key = (_fold(v["raised_by"]), _fold(v["raised_by_org_unit"]))
        if issue is not None and key == (_fold(cur["raised_by"]), _fold(cur["raised_by_org_unit"])):
            v["raised_by"], v["raised_by_org_unit"] = cur["raised_by"], cur["raised_by_org_unit"]
        elif key[0] is None:
            r.errors.append(msg("REQUIRED", "An issue needs a raiser: a stakeholder's name.", "raised_by"))
        else:
            hits = live_by.get(key, [])
            if len(hits) == 1:
                r.pins["raised_by"] = hits[0]
                v["raised_by"], v["raised_by_org_unit"] = stk[hits[0]][0], stk[hits[0]][1]
            elif hits:
                r.errors.append(msg("RAISER_AMBIGUOUS", f"{v['raised_by']} matches {len(hits)} stakeholders: "
                                    f"{named(hits)}. Choose the raiser on the issue screen.", "raised_by"))
            else:
                near = [s for (n, _), ids in live_by.items() if n == key[0] for s in ids]
                hint = f" Stakeholders with this name: {named(near)}." if near else ""
                r.errors.append(msg("RAISER_NOT_FOUND", f"No live stakeholder {v['raised_by']} in "
                                    f"{v['raised_by_org_unit'] or 'no org unit'}.{hint} Add the person on the "
                                    "Stakeholders screen first; an import never creates one.", "raised_by"))
        diff = {k for k in ISSUE_VALUES if changed(cur[k], v[k])}

        # codes: only a new or changed value is checked against the picker list (§7.0, N1)
        for col, cat, noun in (("issue_type_code", "ISSUE_TYPE", "a type"),
                               ("severity_code", "ISSUE_SEVERITY", "a severity")):
            if col in diff or issue is None:
                if v[col] is None:
                    r.errors.append(msg("REQUIRED", f"An issue needs {noun}.", col))
                else:
                    code_ok(r, col, cat, v[col])
        if "status_code" in diff:                          # R2 / N1: open statuses only; closing is on screen
            row = statuses.get(v["status_code"])
            if issue is not None and issue.status_behaviour != OPEN_ISSUE:
                r.errors.append(msg("ISSUE_CLOSED", f"{issue.issue_number} is closed: reopen it on the issue "
                                    "screen before changing its status.", "status_code"))
            elif v["status_code"] is None:
                r.errors.append(msg("REQUIRED", "An issue needs a status.", "status_code"))
            elif v["status_code"] not in pick["ISSUE_STATUS"] or row is None:
                code_ok(r, "status_code", "ISSUE_STATUS", v["status_code"])
            elif row.behaviour_code != OPEN_ISSUE:
                r.errors.append(msg("STATUS_CLOSES", f"{v['status_code']} closes the issue: resolve it on the issue "
                                    "screen, where a resolution is required.", "status_code"))
        if v["raised_date"] and v["target_date"] and v["target_date"] < v["raised_date"]:
            r.errors.append(msg("DATE_ORDER", "The target date cannot be before the raised date.", "target_date"))

        # links: "BRs to add" (§7.0, P5, D1, N6)
        cell = br_list(c["br_numbers"])
        if issue is None:
            for n in cell:
                if n not in brs:
                    r.errors.append(msg("NOT_FOUND", f"{n} is not a live BR of this project.", "br_numbers", key=n))
            adds = [n for n in cell if n in brs]
        else:
            adds = check_links(r, set(links_now[issue.issue_id]),
                               read_links_cell(c["br_links_at_export"], r.token), cell, brs)
            if adds:
                diff.add("links_added")
        v["links_added"] = ", ".join(adds) or None
        if adds:
            r.pins["br_numbers"] = ",".join(str(brs[n].br_id) for n in adds)

        r.values = v
        if issue is not None:
            r.verdict = "UPDATE" if diff else "MATCH"

    # P1: a new row whose title and raised date match a live issue's — a warning, not a block (Q-6)
    new = [r for r in rows if r.verdict == "INSERT" and r.cells["title"] is not None and r.cells["raised_date"]]
    if new:
        by_key = {(t, d.isoformat()): n for t, d, n in db.execute(
            select(func.lower(func.btrim(Issue.title)), Issue.raised_date, Issue.issue_number)
            .where(Issue.project_id == pid, Issue.is_active))}
        for r in new:
            hit = by_key.get((r.cells["title"].strip().lower(), r.cells["raised_date"]))
            if hit:
                r.warnings.append(msg("POSSIBLE_DUPLICATE", f"{hit} already has this title and raised date.", "title",
                                      key=hit))


def _issue_fields(v: dict, keys) -> dict:
    out = {k: v[k] for k in keys}
    for k in ("raised_date", "target_date"):
        if k in out:
            out[k] = date.fromisoformat(out[k]) if out[k] else None
    return out


def _issue_apply(ctx: Ctx, rows: list[Staged]) -> None:
    """raise_issue (then update_issue for a non-OPEN open status, N4) or update_issue with the changed fields only →
    link_br for each addition, the ids kept for a manual reversal (P6)."""
    db, pid = ctx.db, ctx.project_id
    for r in rows:
        if r.verdict not in ("INSERT", "UPDATE"):
            continue
        ctx.current_row = r
        v = r.values
        add_ids = [int(i) for i in r.pins["br_numbers"].split(",")] if r.pins.get("br_numbers") else []
        raiser = {"raised_by_stakeholder_id": r.pins["raised_by"]} if "raised_by" in r.pins else {}
        if r.verdict == "INSERT":
            fields = _issue_fields(v, ("title", "description", "issue_type_code", "severity_code", "raised_date",
                                       "target_date"))
            issue = issue_service.raise_issue(db, ctx.actor_id, pid, {**fields, **raiser}, commit=False)
            r.target_id = issue.issue_id
            if v["status_code"] != ISSUE_DEFAULT_STATUS:
                issue_service.update_issue(db, ctx.actor_id, issue, issue.row_version,
                                           {"status_code": v["status_code"]}, commit=False)
        else:
            issue = db.get(Issue, r.target_id)                              # locked by the re-validation
            stk = _stakeholders(db, pid, [issue.raised_by_stakeholder_id])
            cur = _issue_values(issue, stk)
            r.before = {**cur, "raised_by_stakeholder_id": issue.raised_by_stakeholder_id,
                        "row_version": issue.row_version}
            keys = [k for k in ISSUE_VALUES if k not in ("raised_by", "raised_by_org_unit") and changed(cur[k], v[k])]
            fields = {**_issue_fields(v, keys), **raiser}
            if fields:
                issue_service.update_issue(db, ctx.actor_id, issue, issue.row_version, fields, commit=False)
        added = [issue_service.link_br(db, ctx.actor_id, issue, br_id, commit=False).issue_br_id for br_id in add_ids]
        if added and r.before is not None:
            r.before["links_added_ids"] = added                             # P6
    ctx.current_row = None


ISSUE = Target("ISSUE", "issues", "Issues", Issue.__tablename__, ISSUE_COLUMNS, ISSUE_COMPARE, _issue_export_rows,
               _issue_current, _issue_validate, _issue_apply, component="ISSUE", max_rows=ROW_CAP_1E,
               reupload_warning=True)

# A workbook of several targets' sheets, one batch per sheet (S4-12): template and export only.
BOOKS: dict[str, tuple[Target, ...]] = {"data-model": (DATA_ENTITY, DATA_FIELD)}

TARGETS: dict[str, Target] = {t.slug: t for t in (DATA_ENTITY, DATA_FIELD, BUSINESS_REQUIREMENT,
                                                  FUNCTION_REQUIREMENT, ISSUE)}
BY_CODE: dict[str, Target] = {t.code: t for t in TARGETS.values()}


def target_for(slug: str) -> Target:
    t = TARGETS.get(slug)
    if t is None:
        raise HTTPException(404, "Not found")
    return t


def book_for(slug: str) -> tuple[Target, ...]:
    """What a template or export of `slug` carries: one target's sheet, or a book's sheets."""
    return BOOKS[slug] if slug in BOOKS else (target_for(slug),)


# ---- template and export -------------------------------------------------------------------

def out_columns(db: Session, project_id: int, target: Target) -> tuple[xlsx.OutColumn, ...]:
    """Data-validation lists come from THIS project's resolved codes (criterion 47)."""
    return tuple(xlsx.OutColumn(c.code, c.header, c.width, c.protected,
                                tuple(r.code for r in code_master.resolve(db, project_id, c.category, for_picker=True))
                                if c.category else c.choices)
                 for c in target.columns)


def template_book(db: Session, project_id: int, targets: tuple[Target, ...]) -> bytes:
    """One workbook, one tagged sheet per target and at most one hidden lookup sheet (S4-12)."""
    for t in targets:
        components.require_on(db, project_id, t.component)            # slice 1e, S1
    return xlsx.write_book([xlsx.OutSheet(t.sheet_title, t.code, out_columns(db, project_id, t))
                            for t in targets])


def export_book(db: Session, project_id: int, targets: tuple[Target, ...]) -> bytes:
    for t in targets:
        components.require_on(db, project_id, t.component)            # slice 1e, S1
    return xlsx.write_book([xlsx.OutSheet(t.sheet_title, t.code, out_columns(db, project_id, t),
                                          [[r.get(c) for c in t.codes] for r in t.export_rows(db, project_id)])
                            for t in targets])


def template(db: Session, project_id: int, target: Target) -> bytes:
    return template_book(db, project_id, (target,))


def export(db: Session, project_id: int, target: Target) -> bytes:
    return export_book(db, project_id, (target,))


def download_name(target: Target | str, kind: str, project_id: int) -> str:
    """Server-generated, never from user text (§7.11)."""
    slug = target if isinstance(target, str) else target.slug
    return f"vb-{slug}-{kind}-p{project_id}-{date.today():%Y%m%d}.xlsx"


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
    _parse_rows(ctx, target, rows)
    target.validate(ctx, rows)


def _parse_rows(ctx: Ctx, target: Target, rows: list[Staged]) -> None:
    """Every cell parsed and length-checked, every token read: the checks that need no target
    logic. A token from another project is the file-level 422."""
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


def _payload(r: Staged, file_info: dict) -> dict:
    p = {"v": 1, "cells": r.cells, "file": file_info}
    if r.target_id is not None:
        p["resolved"] = {"target_id": r.target_id, "target_row_version": r.target_row_version}
    if r.values is not None:
        p["values"] = r.values
    if r.pins:
        p["pins"] = r.pins
    if r.info:
        p["info"] = r.info
    return p


def _file_warnings(sheet: xlsx.SheetRead) -> list[dict]:
    """Columns this target does not read, and another target's sheet in the same workbook
    (4a-R17: a data-model workbook runs one step per sheet, each reading only its own)."""
    out = [msg("COLUMN_IGNORED", f"Column {c} is not part of this import and was ignored.", c)
           for c in sheet.ignored_columns]
    for title, code in sheet.other_sheets:
        other = BY_CODE.get(code)
        if other is not None:
            out.append(msg("SHEET_NOT_READ", f"The {other.sheet_title.lower()} sheet "
                           f"{xlsx.sheet_label(title)} was not read in this step.", None,
                           sheet=title[:xlsx.SHEET_NAME_CAP], target=other.slug))
    return out


def _read(body: bytes, target: Target) -> xlsx.SheetRead:
    with xlsx.parse_slot():
        sheet = xlsx.read_rows(body, target.code, target.codes)
    if not sheet.rows:
        raise HTTPException(422, "The sheet has no data rows.")
    if target.max_rows is not None and len(sheet.rows) > target.max_rows:
        raise HTTPException(422, f"At most {target.max_rows:,} rows per file ({len(sheet.rows):,} given). "
                                 "Split the file.")
    return sheet


def check_file(db: Session, project_id: int, target: Target, body: bytes) -> dict:
    """The file-level checks alone, nothing staged: the one tagged sheet, every mapped column,
    the caps, another project's token. The data-model wizard runs this on the fields sheet
    before the entities step commits (S4-12), so a fields sheet that cannot even be read is
    found before any entity is written. A failure is the same 422 validate gives."""
    sheet = _read(body, target)
    rows = [Staged(no, dict(cells)) for no, cells in sheet.rows]
    _parse_rows(Ctx(db, project_id, 0), target, rows)
    return {"target": target.slug, "sheet_name": sheet.sheet_name[:xlsx.SHEET_NAME_CAP],
            "row_count": len(rows), "file_warnings": _file_warnings(sheet),
            "other_sheets": [{"sheet": title[:xlsx.SHEET_NAME_CAP], "target": BY_CODE[code].slug}
                             for title, code in sheet.other_sheets if code in BY_CODE]}


def validate(db: Session, actor_id: int, project_id: int, target: Target, body: bytes,
             file_name: str) -> ImportBatch:
    components.require_on(db, project_id, target.component)          # D-37 (§5.2, sara L3)
    sha = hashlib.sha256(body).hexdigest()
    sheet = _read(body, target)
    ctx = Ctx(db, project_id, actor_id)
    rows = [Staged(no, dict(cells)) for no, cells in sheet.rows]
    _check(ctx, target, rows)

    status = _statuses(db)
    warnings = _file_warnings(sheet)
    if target.reupload_warning and (seen := reupload_warning(db, project_id, target, sha)) is not None:
        warnings.append(seen)
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
                           .order_by(ImportRow.sheet_row_no, ImportRow.import_row_id)))   # a flow row has no sheet row


FLOW = "PROCESS_FLOW"                         # slice 1e-b: its own validate and apply (services/flow_import.py)


def batch_out(db: Session, batch: ImportBatch, rows: list[ImportRow] | None = None) -> dict:
    rows = _rows_of(db, batch) if rows is None else rows
    file_info = rows[0].payload.get("file", {}) if rows else {}
    target = BY_CODE.get(batch.target_entity)
    slug = target.slug if target else "process-flow" if batch.target_entity == FLOW else None
    return {"import_batch_id": batch.import_batch_id, "project_id": batch.project_id,
            "target": slug, "target_entity": batch.target_entity,
            "import_mode": batch.import_mode, "anchor_bfc_node_id": batch.anchor_bfc_node_id,
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
    cells = row.payload.get("values") or row.payload.get("cells", {})
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
    rows = _rows_of(db, batch)
    if batch.target_entity == FLOW:
        from services import flow_import
        return {"batch": batch_out(db, batch, rows), "purged": batch.rows_purged_at is not None,
                "rows": flow_import.preview_rows(db, batch, rows)}
    target = BY_CODE.get(batch.target_entity)
    if target is None:
        raise HTTPException(404, "Not found")
    ids = [r.payload.get("resolved", {}).get("target_id") for r in rows if r.verdict == "UPDATE"]
    current = target.current(db, batch.project_id, [i for i in ids if i is not None])
    out = []
    for r in rows:
        tid = r.payload.get("resolved", {}).get("target_id")
        out.append({"import_row_id": r.import_row_id, "sheet_row_no": r.sheet_row_no, "verdict": r.verdict,
                    "business_key": r.business_key,
                    "is_valid": r.is_valid, "errors": r.error_detail, "warnings": r.warning_detail,
                    "changes": _changes(target, r, current.get(tid)),
                    "resolved": r.payload.get("info"),
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
    for import_row_id, errs in row_errors.items():          # by row id: a flow row has no sheet row (D5)
        db.execute(update(ImportRow)
                   .where(ImportRow.import_batch_id == batch_id, ImportRow.import_row_id == import_row_id)
                   .values(error_detail=errs, is_valid=False)
                   .execution_options(synchronize_session=False))
    if row_errors:
        invalid = db.scalar(select(func.count()).select_from(ImportRow).where(
            ImportRow.import_batch_id == batch_id, ImportRow.is_valid.is_(False)))
        db.execute(update(ImportBatch).where(ImportBatch.import_batch_id == batch_id)
                   .values(error_count=invalid).execution_options(synchronize_session=False))
    return True


def commit(db: Session, actor_id: int, batch_id: int, row_version: int,
           acknowledged_inserts: int | None, source_ip: str | None = None,
           acknowledged_updates: int | None = None) -> ImportBatch:
    """The one commit: lock, status, version, errors, the component, then the target's own apply, and every
    failure audited. A flow batch takes `acknowledged_updates` too (FI-7) and its component from its anchor (P3)."""
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
        if batch.target_entity == FLOW:
            from services import flow_import                       # its anchor's DFD component, checked there (P3)
            result = flow_import.commit_rows(db, actor_id, batch, status, acknowledged_inserts,
                                             acknowledged_updates, source_ip)
        else:
            target = BY_CODE.get(batch.target_entity)
            if target is None:
                raise HTTPException(404, "Not found")
            components.require_on(db, project_id, target.component)  # D-37 (§5.2, sara L3)
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
        pinned = staged[r.sheet_row_no].payload.get("pins") or {}
        for col in sorted(set(pinned) | set(r.pins)):
            if not errs and pinned.get(col) != r.pins.get(col):    # 4a-R13: resolved, then pinned
                errs.append(msg("RESOLVED_CHANGED", f"This row's {col} now resolves to "
                                f"{_q(r.pins.get(col))}, not {_q(pinned.get(col))}: the data changed since "
                                "the upload. Upload the file again.", col,
                                was=pinned.get(col), now=r.pins.get(col)))
        if errs:
            fresh_errors[staged[r.sheet_row_no].import_row_id] = errs
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
                           {staged[r.sheet_row_no].import_row_id: [msg("APPLY_FAILED", str(detail), None)]}
                           if r else {})

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


# ---- purge (Q14, §7.12b) -------------------------------------------------------------------
# The 90-day row purge lives in services/import_purge.py; it is named here because the design's
# function map calls it bulk.purge_import_rows.
from services.import_purge import purge_import_rows  # noqa: E402,F401
