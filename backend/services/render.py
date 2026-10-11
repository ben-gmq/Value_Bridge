"""THE ONE MERMAID LABEL PATH (design §7.12b, R2-S7; slice 3 spec §7 3c).

Every label in every Mermaid export — step, lane, condition, store, external party, entity,
field, relationship — goes through `escape_mermaid()`. There is no second label path.
Node ids are generated from database ids (s12, d7, x2, e40, E7, l1, a_3), never from user
text. `_guard()` is the last step of every exporter: an output line that begins with a
directive Mermaid would act on is a renderer bug, so it is logged and refused with a 500
rather than handed to a consultant to paste into a client's deck.

The exporters render exactly the dicts `generate_process_flow`, `generate_dfd` and
`generate_erd` return; they read nothing else."""
import logging
import re
import unicodedata

from fastapi import HTTPException

log = logging.getLogger("vb")

# Design §7.12b, copied exactly — '#' first by construction, since the map runs in one pass.
MERMAID_ENTITY = {'#': '#35;', '"': '#quot;', '<': '#lt;', '>': '#gt;', '`': '#96;',
                  '[': '#91;', ']': '#93;', '(': '#40;', ')': '#41;', '{': '#123;',
                  '}': '#125;', '|': '#124;', ';': '#59;'}

LABEL_CAP = 200
_BREAKING = {"Cc", "Zl", "Zp"}      # CR, LF, tab, \v, \f, U+0085, U+2028, U+2029 … → a space
_INVISIBLE = "Cf"                    # U+202E right-to-left override, U+200B, U+FEFF … → removed (Ben, sara L3)
BANNED_FIRST_TOKENS = ("click", "call", "href", "%%{init", "style", "classDef", "linkStyle", "class")
_TYPE_CODE = re.compile(r"[A-Z_]+")

UNASSIGNED_LANE = "Unassigned"
OUTSIDE_LANE = "Outside this diagram"


def check_format(fmt: str) -> None:
    """The export routes speak Mermaid only. The flow JSON file (D-25) belongs to the import slice."""
    if fmt == "json":
        raise HTTPException(422, "format=json (the flow JSON file) comes with the flow import slice; "
                                 "use format=mermaid")
    if fmt != "mermaid":
        raise HTTPException(422, "format must be mermaid")


def escape_mermaid(text) -> str:
    """Spec §7 3c, in this order: cap the RAW text (never cut an entity), break-like characters
    to a space and invisible format characters dropped, drop `%%`, the entity map in ONE pass,
    then wrap in quotes."""
    s = str(text or "")
    s = s[:LABEL_CAP]
    s = "".join(" " if unicodedata.category(c) in _BREAKING else c for c in s
                if unicodedata.category(c) != _INVISIBLE)
    s = s.replace("%%", "")
    s = "".join(MERMAID_ENTITY.get(c, c) for c in s)
    return '"' + s + '"'


def _banned(token: str) -> bool:
    """A directive word in any case, or anything that opens a comment, directive or YAML block."""
    low = token.lower()
    return low.startswith(("%%", "---")) or any(low.startswith(w.lower()) for w in BANNED_FIRST_TOKENS)


def _guard(text: str) -> str:
    """The last step of every exporter (§7.12b): any line whose first token is a directive → 500.
    Case-insensitive, and any `%%` / `---` opener too (sara L1) — defence in depth behind the
    escape, which already makes all of these unreachable from user text."""
    for n, line in enumerate(text.splitlines(), 1):
        token = (line.split() or [""])[0]
        if _banned(token):
            log.error("mermaid guard: line %d begins with a banned directive (%r)", n, token[:20])
            raise HTTPException(500, "The diagram export produced an unsafe line and was stopped")
    return text


def _join(lines: list[str]) -> str:
    return _guard("\n".join(lines) + "\n")


def _ref(n: dict) -> str:
    return f"{n['hier_code']} {n['node_name']}"


# ---- the DFD (§9.8: the one process diagram — lanes are performers, D-38/D-46/D-49) -----------

def _lane_label(lane: dict) -> str:
    if lane["kind"] == "UNASSIGNED":
        return UNASSIGNED_LANE
    name = lane["name"] or lane["code"] or ""
    return f"{name} · {lane['unit_name']}" if lane.get("unit_name") else name


def export_dfd(g: dict, with_order: bool = False) -> str:
    """flowchart LR; one subgraph per performer lane (unassigned last) holding its processes as
    stadiums; stores as cylinders, parties as squares and triggers as circles at the top level; one
    edge per flow in its direction (I = into the step), labelled; boundary stubs as dotted links to
    an `outside` box. The derived order is drawn only when asked, dashed (§9.8)."""
    lines = ["flowchart LR"]
    for i, lane in enumerate(g["lanes"], 1):
        lines.append(f"    subgraph l{i}[{escape_mermaid(_lane_label(lane))}]")
        lines += [f"        s{p['bfc_node_id']}([{escape_mermaid(_ref(p))}])"
                  for p in g["processes"] if p["lane_key"] == lane["lane_key"]]
        lines.append("    end")
    lines += [f"    d{s['data_entity_id']}[({escape_mermaid(s['de_number'] + ' ' + s['de_name'])})]"
              for s in g["stores"]]
    lines += [f"    x{x['external_entity_id']}[{escape_mermaid(x['ext_number'] + ' ' + x['ext_name'])}]"
              for x in g["externals"]]
    lines += [f"    t{t['process_trigger_id']}(({escape_mermaid(t['trigger_name'])}))" for t in g["triggers"]]
    for f in g["flows"]:
        step = f"s{f['bfc_node_id']}"
        other = {"STORE": f"d{f['data_entity_id']}", "EXTERNAL": f"x{f['external_entity_id']}",
                 "TRIGGER": f"t{f['process_trigger_id']}"}[f["kind"]]
        src, dst = (other, step) if f["direction"] == "I" else (step, other)
        label = f"|{escape_mermaid(f['label'])}|" if f["label"] and f["kind"] != "TRIGGER" else ""
        lines.append(f"    {src} -->{label} {dst}")
    stubs = sorted({(d, r["data_entity_id"]) for d in ("in", "out") for r in g["boundary"][d]})
    if stubs:
        lines.append(f"    outside[{escape_mermaid(OUTSIDE_LANE)}]")
        lines += [f"    outside -.-> d{de}" if d == "in" else f"    d{de} -.-> outside" for d, de in stubs]
    if with_order:
        lines += [f"    s{o['from_bfc_node_id']} -.-> s{o['to_bfc_node_id']}" for o in g["order"]]
    return _join(lines)


# ---- the ERD (§7.4 generate_erd, D-29; glyph table spec §7 3b) -------------------------------

PARENT_GLYPH = {"1": "||", "0..1": "|o"}
CHILD_GLYPH = {"1": "o|", "many": "o{"}          # the child end never claims a minimum (A-S3-8)


def _type(code: str | None) -> str:
    # A project may code a type CLASS or STYLE: plain upper case, but a directive word — refused
    # here so the guard (case-insensitive, sara L1/L2) never has to stop a legitimate export.
    if not code or not _TYPE_CODE.fullmatch(code) or _banned(code):
        return "unknown"
    return code


def _keys(f: dict) -> str:
    keys = [k for k, on in (("PK", f["is_primary_key"]), ("FK", f["is_foreign_key"])) if on]
    return (" " + ", ".join(keys)) if keys else ""      # R2-NEW-3: both → `PK, FK`


def _rel(r: dict) -> str:
    glyph = PARENT_GLYPH[r["parent_cardinality"]] + ("--" if r["identifying"] else "..") \
        + CHILD_GLYPH[r["child_cardinality"]]
    return f"    E{r['parent_data_entity_id']} {glyph} E{r['child_data_entity_id']} : {escape_mermaid(r['label'])}"


def export_erd(g: dict) -> str:
    """erDiagram; each entity E{id} with the alias "DE-0007 name"; its fields as
    `<type> a_<n> [PK|FK|PK, FK] "<real name>"` (erDiagram takes no quoted attribute names, so a
    Japanese or spaced name lives in the comment and never collides); one line per relationship,
    parent first; each out-of-area parent a declared stub entity with its relationships."""
    lines = ["erDiagram"]
    for e in g["entities"]:
        alias = f"    E{e['data_entity_id']}[{escape_mermaid(e['de_number'] + ' ' + e['de_name'])}]"
        if not e["fields"]:
            lines.append(alias)
            continue
        lines.append(alias + " {")
        lines += [f"        {_type(f['data_type_code'])} a_{n}{_keys(f)} {escape_mermaid(f['field_name'])}"
                  for n, f in enumerate(e["fields"], 1)]
        lines.append("    }")
    drawn = {e["data_entity_id"] for e in g["entities"]}
    stubs: dict[int, str] = {}
    for r in g["outside_refs"]:
        if r["parent_data_entity_id"] not in drawn:
            stubs.setdefault(r["parent_data_entity_id"], r["parent_de_number"] + " " + r["parent_de_name"])
    lines += [f"    E{pid}[{escape_mermaid(label)}]" for pid, label in stubs.items()]
    lines += [_rel(r) for r in g["relationships"]]
    lines += [_rel(r) for r in g["outside_refs"]]
    return _join(lines)
