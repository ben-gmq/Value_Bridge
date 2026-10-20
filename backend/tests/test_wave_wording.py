"""Slice 15 criterion 11 (W-1, T5; sara L2): no screen, label, report or comparison area shows the word "phase". Every
visible word says "wave"; only code names (tables, routes, the component code) keep `phase`.

Read from the sources a person can see: the waves strings file, the shell's rail label, the comparison labels for the
three frozen tables and their columns, the seeded component label, and every refusal the phasing service raises."""
import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
I18N = ROOT / "frontend" / "src" / "i18n"
PHASE = re.compile(r"phase", re.IGNORECASE)


def _strings(name):
    return json.loads((I18N / name).read_text())


def test_the_wave_screens_and_labels_never_say_phase():
    waves = _strings("en.waves.json")
    assert waves and all(k.startswith("waves.") for k in waves)
    shell = _strings("en.json")
    base = _strings("en.baselines.json")
    shown = {**waves, "nav.waves": shell["nav.waves"], "baselines.area.PHASE": base["baselines.area.PHASE"],
             **{k: v for k, v in base.items() if k.startswith(("baselines.entity.", "baselines.field."))
                and PHASE.search(k)}}
    assert {"baselines.entity.phase", "baselines.entity.solution_phase", "baselines.field.phase_code",
            "baselines.field.phase_id"} <= set(shown)                        # the frozen columns are labelled
    assert [f"{k}: {v}" for k, v in shown.items() if PHASE.search(v)] == []


def test_the_component_label_and_every_refusal_say_wave():
    from seeds.seed_code_master import LIBRARY
    comps = dict(next(rows for cat, _, rows in LIBRARY if cat == "PROJECT_COMPONENT"))
    assert comps["PHASING"] == "Waves"                                      # T5: COMPONENT_OFF names it
    tree = ast.parse((ROOT / "backend" / "services" / "phasing.py").read_text())
    details = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "HTTPException" and len(node.args) > 1:
            msg = node.args[1]
            parts = [v.value for v in ast.walk(msg) if isinstance(v, ast.Constant) and isinstance(v.value, str)]
            details.append(" ".join(parts))
    assert len(details) >= 15
    assert [d for d in details if PHASE.search(d)] == []
