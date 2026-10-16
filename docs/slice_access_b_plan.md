# Access slice B — program members: build plan (night batch, 2026-10-16)

Builds D-71 (2)–(5), (8) and D-72/D-73 for programs, per `docs/access_v2_decision.md` (approved), the model
`docs/access_v2_model.md` and the design-auditor fixes in the paper's §8. Stacked on slice A and 1g on branch
`ren/2026-10-16_value-bridge-remaining-and-spec-list`; not merged.

## What a person can do when it lands
- On a program's page, an FTC admin or a program admin adds people as **Admin / Editor / Viewer**, changes and removes
  them. Each of them opens every live project in the program at that level, restricted ones included.
- A program admin is admin of every project in it: manages its members and code lists (not FTC-only settings).
- A project's Access list shows each person's level and source — direct, **via program X**, or as all staff. Removing a
  direct role from someone who also holds a program role says so in the confirm.
- Moving a project between programs (FTC admin) previews who gains and who loses access; restricting a project counts
  program members among those who keep it; changing a user's type lists their program roles that come back.
- A program admin of an empty program can still open it and manage its members.

## Grade
**Grade 1** — a silent failure shows a restricted client project to someone outside it. Heavy proof, as slice A:
- every program route and every project route as a member of a *different* program (404 on restricted projects);
- the level table extended with the program source (literal expectations, through the API);
- the leak sweep (`test_no_get_route_leaks_a_restricted_project`) with a program-B member persona;
- restriction / move confirms refused when a program member is added between preview and confirm (409);
- a user-type change revives program roles only through its preview (sara 1g L9);
- program retire refused by the database while live members exist (law 1).
Left uncovered on purpose: a true two-connection race on the program lock (the lock order carries it, as slice A).

## Steps (one commit each)
1. **Migration 0060 `program_member`** (model §6): live-unique (program, user), generated `program_is_active` with a
   composite FK to `program(program_id, is_active)` so a live member blocks a program retire; downgrade refuses while
   rows exist.
2. **Access core** — `access.py` only: the PROGRAM source in `level_for` / `access_to` / `who_can_open` /
   `visible_project_ids`; `visible_program_ids` adds programs you are a member of; `require_program` takes its level only
   from the platform flag or a membership (H2); lock order program(s) FOR UPDATE by id, then project (M2) in the
   restriction confirm and the move; `user_admin._comes_back` reads program roles.
3. **Program members** — service + routes: list (inactive users shown, removable — L1), add / change / remove at program
   ADMIN, a program-scoped object guard for `/program-members/{id}`; VIEWER above VIEW refused; platform admin refused;
   audited `PROGRAM_MEMBER_*` with the program in the detail.
4. **Move and create** — `move_project_program` preview names gains / losses / level changes inside its hash; creating a
   restricted project in a program names the program members it admits (audit detail).
5. **Screens** — Program page: Members card; Access page: "via program X" and the remove-confirm note.
6. **Checks** — Sara, full suite once, browser check, `rules-check-drift`.

## Size
About 3.5 working days of work; roughly 1,500 lines with tests.

## For the morning list
- Migration 0060 round-trip (down/up) — a downgrade asks Ben.
- Merge, stacked after 1g.
