# Suggest a flow's arrows from the chart order — preview, then keep

**Date:** 2026-10-01 · **Author:** Lilly · **Status:** rev 3.1 (after its round 1), a **new, smaller design**. Ben chose
option (a) on 2026-10-01, after round 2 of the stored-draft design (rev 2) found a structural
gap in how drafted rows were identified.
**Builds on:** design D-20/D-21 (process flow edges), §7.2a `link_process_flow`, Slice 2 (S2-1…S2-6).

## 1. Purpose
On a flow with no arrows, a consultant presses **Suggest arrows**. The canvas shows a proposed
chain as faint, unsaved ghost lines. **Nothing is stored.** If the consultant presses **Keep
these arrows**, the arrows are saved as ordinary arrows, chosen by that person. **Discard**
removes the ghosts.

## 2. Doctrine
Playbook audit on every write; one owner per rule; VB law 6 (the server derives the arrows; the
body only confirms). Design S2-2 (ends are create-only) and S2-5 (re-link restores a retired
twin).

## 3. Grain
There is no new table, no draft state and no marker. Keeping the suggestion writes ordinary
`bfc_node_flow` rows: one per consecutive pair of steps in chart order, plus one start event and
one end event per frame. Once kept, they are indistinguishable from hand-drawn arrows, because
a person chose them.

## 4. Business Requirement grid

| Function | Entity | Use | Logic → output |
|---|---|---|---|
| `suggest_arrows` | `bfc_node` | R | **Offered only on a function whose active children are all process steps** (A-SG-4). The frame is those children in `seq_no` / `hier_code` order, the chart order the consultant set. That means at most 99 steps (`MAX_SIBLINGS`). A node with any summary child → 422 "Suggest works on a function whose children are all steps". No active steps → 422 "no process steps under this node" |
| `suggest_arrows` | `bfc_node_flow` | R | **Offered only when no live arrow joins two frame steps and no live start/end event sits on one.** Otherwise → 409. An incoming or outgoing hand-off from outside the frame does not block |
| `suggest_arrows` | — | — | → `{arrows: [{from, to}], confirm_hash}`. Every arrow is **SEQUENCE**, with `seq_no` NULL; nothing is guessed. `confirm_hash` = SHA-256 over the frame node id, the sorted (step id, `row_version`) pairs, and the (id, `row_version`) of any retired arrow on a proposed pair |
| `keep_arrows` | `bfc_node_flow` | C | 1. Lock the frame's steps `FOR NO KEY UPDATE`, in id order.<br>2. **Re-run the whole `suggest_arrows` rule under the lock**, including the 409 when frame steps already have arrows, so a colleague's arrow drawn since the GET is never merged in.<br>3. Compare the hash; changed → 409 "the chart changed; suggest again".<br>4. In ONE transaction, create each arrow through the shared no-commit `_link_row`. A retired twin on a pair is restored as a plain SEQUENCE (S2-5). `relink` gains `detail=`, so its audit event records the twin's previous type, label, `seq_no` and note.<br>5. **Flush, then write** one `FLOW_ARROWS_KEPT` event `{frame_id, confirm_hash, created_ids, restored_ids}` with real ids |
| `flow_completeness_report` | — | R | Unchanged. Kept arrows are a person's arrows. The frame is one direct-parent group, so a kept chain reports **no** `no_start`, `no_end` or `orphan_steps` |
| flow graph | — | R | The graph response gains `can_suggest`, computed by the same rule, so the button never disagrees with the server |
| review the suggestion *(manual)* | — | — | The consultant sees the ghost chain on the canvas, in place, and presses Keep or Discard. Afterwards they correct arrows as today |

## 5–6. Logical / physical
**No schema change, no migration.** The suggestion lives only in the browser until it is kept.

## 7. Function (in `services/process_flow.py`)
```
suggest_arrows(db, node) -> {arrows, confirm_hash}    # guards as generate_process_flow; read only
keep_arrows(db, actor, node, confirm_hash) -> {created, restored}
    FOR NO KEY UPDATE every frame step (id order); RE-RUN the suggest rule; hash; _link_row each;
    flush; audit with real ids; one commit
_link_row(...)       # link_process_flow's body without its commit — the one per-arrow rule;
                     # link_process_flow = _link_row + commit, behaviour unchanged.
                     # _link_row is the ONLY writer of bfc_node_flow rows; the future flow
                     # JSON import writes through it too
```

## 8. code_master
None.

## 9. API (`object_guard(BfcNode, "EDITOR")`, one guard each)

| Method · path | Body | Response |
|---|---|---|
| `GET /bfc-nodes/{id}/process-flow/suggest` | — | `{arrows, confirm_hash}`; 409 when the frame already has arrows |
| `POST /bfc-nodes/{id}/process-flow/suggest/keep` | `{confirm_hash}` | `{created, restored}` |

## 10. Acceptance criteria (Grade 3 on screen; the one write path is tested directly)
1. An L2 node with 3 steps suggests start → 01 → 02 → 03 → end. Nothing is written by the GET.
   Keep creates 4 SEQUENCE arrows with `seq_no` NULL. `FLOW_ARROWS_KEPT.created_ids` equals the
   new rows' ids. Afterwards the completeness report shows no `no_start`, `no_end` or
   `orphan_steps` for the node.
2. A node with a summary child, or with no steps → 422, and `can_suggest` is false.
2a. A colleague hand-draws an arrow between two frame steps after the GET → Keep returns 409,
    and nothing is created.
3. A live arrow between two frame steps → 409. An inbound hand-off from outside does not block.
4. A hash taken before a step was added, or before a twin on a pair was retired → Keep returns 409
   and nothing is created.
5. A retired twin on a pair is restored, not duplicated. Its earlier type and note are in the
   audit event.
6. A forced failure on the last arrow creates nothing.
7. A REVIEWER sees no button and gets 403. A project the user can't see → 404.
8. On screen: Suggest draws ghost arrows (dashed, faded), and Discard removes them with no
   request sent. Keep saves them, and they redraw as normal arrows.

## 11. Assumptions
- **A-SG-1** Every suggested arrow is SEQUENCE. Hand-offs, conditions and parallels are a
  person's call, made after Keep.
- **A-SG-2** Only offered on a frame with no arrows between its steps, so it never merges into
  a flow a person has started.
- **A-SG-3** A start and an end event per frame, even when the first or last step also has a
  hand-off from or to outside.
- **A-SG-4** Suggest works only on a function whose children are all steps: one chain per
  direct parent, matching the completeness report. A larger node is drafted one function at a
  time, so every suggestion stays reviewable (at most 99 steps). Linking between functions is a
  person's hand-off.
- **A-SG-5** A restored twin comes back as a plain SEQUENCE with its note cleared. Its earlier
  values are kept in its audit event.

## 12. Out of scope
A stored draft state, undo-as-a-unit, merging with existing arrows, guessing arrow types.

## 13. Build checklist
- Tests in `tests/test_process_flow_api.py`, one per criterion.
- FlowPage: on a flow with steps and no arrows, a **Suggest arrows** button (`useCanEdit`).
  Ghost edges are drawn with the shared labelled-edge type, styled dashed and faded from theme
  tokens. Keep and Discard sit in a banner over the canvas.
- Strings in `en.processes.json`.
- sara before commit (a new write path).
- No migration.

**Design review:** rev 2 (stored drafts) went through 2 rounds on 2026-10-01. Round 2 found the
draft-identity gap, which made it a new design (Ben chose this option).

Rev 3, round 1 (2026-10-01): 8 findings (1 HIGH, 3 MEDIUM, 4 LOW), all fixed in this rev 3.1:
- **the HIGH:** Keep now re-runs the rule under the lock;
- **the sub-process, size and lock findings:** closed by A-SG-4;
- the flush-before-audit and relink history fixes;
- `can_suggest`;
- the 422 for an empty frame.

The questions became A-SG-3, A-SG-4 and A-SG-5, Lilly's recommendations, which Ben follows.

One interaction is out of this slice and tracked in VB-005: restoring a retired step after a
Keep brings its old arrows back beside the new chain.

**Round 2 of 2** (2026-10-01): all 8 closed; 1 new LOW, **tracked, not redrafted**. The builder
applies two rules:
- **SG-1:** §7's "_link_row is the ONLY writer" reads, in code comments and in review, as
  *"`_link_row` is the only path that creates or re-links an arrow. Every path that makes an
  arrow live (`_link_row`, `step_retire.restore`) locks a step at one of its ends."* sara checks
  that `step_retire.restore` still takes that lock.
- The button keys on `can_suggest` only (§13 wording).
