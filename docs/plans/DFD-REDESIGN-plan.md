# DFD redesign — plan for Ren / Ben (2026-10-23)

**Status: plan only. Nothing is built until Ren answers.** Ben, after trying the busy demo: *"I am kind of okay with the
screen but DFD I think need to improve more… Swim lane need to be adjustable, flow need to look more clean… connectors
should be straight and need to be round only on the edge, not s curve."*

## What is wrong today (seen on the busy demo, OPS28 "Production execution": 9 steps, 5 lanes, 12 stores, 32 flows)
Evidence: `Evidence/2026-10-23/dfd-current/` (ui-verifier, 4 screenshots).
- **Every connector is a curve** (`canvas/edges.jsx`, `CurvedEdge` = React Flow's Bezier). It always leaves a box on
  its right and enters the next on its left, so a line going backwards draws a hook or an S across the diagram.
- **No routing at all.** The DFD does not use the layout engine already in the app (ELK, used for the ERD); it places
  boxes on its own grid (`DfdPage.jsx` `buildLayout`) and lets React Flow draw a curve between two points. Lines pass
  behind boxes, sit on top of each other where they share a box side, and labels collide: ~15–25 crossings on that one
  diagram, about 8 long diagonals cutting two or three lanes.
- **Data stores are drawn once**, beside the first step that writes them. A store used by steps in four lanes pulls
  four long lines across the diagram — this, more than the curves, is what makes the middle a knot.
- **Lanes are fixed**: height from the number of rows a lane needs, order as the server sends it; nothing to drag.
  Empty space is not reclaimed (a ~170 px empty band above the diagram; half-empty lanes).

## Options for the drawing engine

| Option | What it is | Effort | Memory / speed | Risk |
|---|---|---|---|---|
| **A. Keep React Flow, own layout + own line router** | Keep the lane × step-order grid (it carries meaning: lane = who, column = derived order). Add a small router that runs every line along the gaps between columns and lanes, gives each line its own track in a gap, and draws straight segments with rounded corners at the bends. | **5–7 days**, in 4 slices | No new library. Routing 30–60 lines is pure arithmetic in the browser, well under 50 ms | Low — every slice is visible and reversible |
| B. React Flow + ELK for the whole DFD | Let ELK place and route everything, lanes as ELK groups, and draw ELK's bend points | 4–6 days, outcome uncertain | ELK is already loaded (in a worker); 50–100 ms per layout | Medium–high: ELK cannot keep a step's column aligned across separate lane groups, so derived order (D-38) stops reading left to right |
| C. React Flow + libavoid-js router | A port of a well-known orthogonal router, with line-separation built in | 3–5 days | ~0.8 MB WebAssembly download; fast | Medium: the package is a **beta** (0.5.0-beta.5) under **LGPL** — a licence question for Ben before any install |
| D. Commercial diagram engine (yFiles for HTML, GoJS) | Swim lanes and orthogonal routing out of the box | 2–3 weeks: the DFD screen and its drawing feature rewritten | Heavier bundle | A paid licence (thousands of US dollars), and two diagram engines in one app (ERD and flow stay on React Flow) |
| E. Purpose-built SVG renderer, no React Flow | Draw everything ourselves | 2–3 weeks | Smallest | High: zoom, pan, drag, selection and the "draw a connection" feature (D-65) all rebuilt |

**Recommendation: A.** React Flow is not the problem — it is a good canvas (zoom, pan, drag, select, draw a connection
are built and tested). What is missing is a layout and a router, and our diagram is regular enough (lanes × columns)
that a router written for it is small, fast and predictable, with no new dependency and no licence. ELK stays for the ERD.

## The layout rules (option A)
1. **Lines:** straight horizontal and vertical segments only; a small rounded corner (radius ~8 px) at each bend; never
   a curve. Arrowheads where the data goes.
2. **Sides:** a line leaves and enters the box side facing its other end — right→left going forward, top/bottom between
   lanes in the same column, around the outside when going backward (a loop runs in its own track above the lane, not
   through the boxes).
3. **Tracks:** lines run only in the gaps between columns and between lanes; each line gets its own lane of the gap
   ("track"), so two lines never sit on top of each other; tracks are ordered to minimise crossings. Several lines on one
   box side are spread along that side, not stacked on one point.
4. **Stores where they are used:** a store sits in the lane that uses it most, in the gap just after its first writer.
   *Decision 2 below:* a store used in several lanes can be drawn **once per lane** (classic DFD notation: a repeated
   store carries a small mark), which removes most of the long diagonal lines.
5. **Balance:** each lane's height follows what it holds (steps and stores); columns shrink to the widest box they hold;
   empty bands are removed; the diagram opens fitted with no empty band above it.
6. **Labels** sit on the longest straight segment of their line, nudged clear of boxes and other labels; at low zoom they
   hide, as today.
7. **Adjustable lanes:** drag a lane's header up or down to reorder; drag its bottom edge to make it taller; "Reset
   layout" (already on the screen) puts both back. Saved per diagram for everyone, like box positions today (D-30).

## Slices (each one something Ben can open and judge)
| # | Slice | Ben sees | Days |
|---|---|---|---|
| 1 | Clean lines | Straight lines with rounded bends, right sides chosen, lines spread along box sides; no new layout yet | 1½ |
| 2 | Balanced layout | Stores beside their users (and, if Decision 2 is yes, once per lane), lane heights by content, no empty bands | 1½ |
| 3 | Line tracks | Lines in their own tracks between columns and lanes — no lines on top of each other, far fewer crossings | 1½–2 |
| 4 | Adjustable lanes | Reorder and resize lanes, saved; Reset puts them back | 1½–2 (includes a schema change) |

Slice 4 needs **a new saved row kind** (a lane's order and height per diagram): `diagram_layout` holds box positions
only. That is a data-design change — data model by `apple`, one reversible migration on `main`, Ben's OK — so it is the
last slice, and slices 1–3 stand without it.

**Grade 3** — presentation only: a broken layout is visible the moment the screen opens, and no business record changes
(slice 4 stores only lane order and height). Proof per slice: the router's rules as a few unit tests on a pure function
(lines only horizontal/vertical, no two segments on one track, every line ends on a box side), and one ui-verifier pass
on OPS28 "Production execution" and "Order management" compared with today's screenshots. The full suite runs before
each push, as always.

## Decisions for Ben
1. **Which engine?** I recommend A (keep React Flow, own layout and router; 5–7 days in four slices; no new library).
2. **May a data store be drawn once per lane that uses it** (marked as a repeat), instead of once per diagram? It is
   standard DFD notation and the single biggest cut in crossing lines; the store is still one record (same `DE-` number).
   I recommend yes.
3. **Lane order and height saved for everyone on that diagram** (like box positions today), not per person. I recommend
   for everyone.
