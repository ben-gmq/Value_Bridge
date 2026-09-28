# Value_Bridge — starting brief

**For:** Lilly, to design and build · **From:** Ben, via Janet · **Date:** 2026-09-16/17

Nothing here is designed. This is Ben's own description of what the tool must hold, plus
the decisions already taken and the questions that have to be answered before a data model
is drawn. Janet wrote the container only — she does not author project design, so nothing
below has been reviewed, normalized or extended.

## What it is

An internal Fortience Consulting tool for running **business and process assessments** —
the front half of an engagement, before any system is chosen or built. First use is the
project being proposed from 2027.

## What it must hold — Ben's words

- Store **business requirements** (a small number of data items per requirement).
- A **business process hierarchy, 5 levels deep**.
- The **process description used to produce the DFD**.
- A **list of data entities**.
- **Data entities linked to each business requirement's inputs and outputs** — both sides
  carry data.
- A **list of issues**, and a **categorization** of those issues.
- A **solution list**, each solution **linked to a business requirement**.
- Where there is a fixed package and vendor, this last layer would be the *system* or
  *functional* requirement. Here it is deliberately a **solution requirement**, because
  Fortience is the business consultant, not the system vendor. It links to the business
  requirement.

## Already decided

- **Multi-engagement from day one** — every assessment is a separate engagement inside one
  tool. Chosen over single-engagement because the engagement key touches nearly every
  table and is close to impossible to retrofit.
- **Full FTC scaffold**, not frontend-only — React + MUI + Vite, FastAPI + PostgreSQL, JWT
  auth, via `fortience-app-scaffold`. The point of this app is its data model, and a model
  never tested against a database is not tested.
- **No agent owns the assessment method.** Designing this app is Lilly's, as always.
  *Running* an assessment on a client stays with Ben for now; revisit after the first real
  engagement, when what repeats is known rather than guessed.

## Worth knowing before the model is drawn

This is Ben's own method turned into software. `design-spec` §4 already defines a Business
Requirement as *how a logical data entity is used by a function, and what business logic
produces the output data* — an entity × function × logic grid. This app stores as **data**
what that skill produces as a **design-time artifact**. Whether the app should eventually
emit that grid is a real design question, not a given.

## Open — settle these first

1. **Grain of every table**, starting with the keystone. "One row per what?" for business
   requirement, process node, data entity, issue, solution, solution requirement.
2. **The 5-level hierarchy**: one self-referencing process table with a level attribute, or
   five typed levels? Affects every query and every screen.
3. **BR ↔ data entity**: the link carries a *direction* (input vs output). One associative
   table with a direction column, or two relationships?
4. **Issue categorization**: a fixed `code_master` category, a free taxonomy, or multi-axis
   (severity × type × process area)?
5. **Solution → BR**: one-to-many or many-to-many? A solution usually answers several
   requirements, which makes this a join table — Ben to confirm.
6. **Engagement scoping**: which tables carry the engagement key, and what is shared library
   across engagements (issue categories? a reference process hierarchy?) versus per-client.
7. Does the DFD get **stored** as structured data and rendered, or **written** as a
   narrative field per process? Very different builds.
8. Is `Value_Bridge` the final name? It was chosen before this design conversation.

## Next step

`design-spec` → `apple` → `design-review`, signed off in Plan Mode, **then**
`fortience-app-scaffold`. The scaffold is an afternoon; the model is the product.
