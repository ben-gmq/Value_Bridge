# Access slice A — project admin: build plan (for Ren / Ben, 2026-10-16)

Status: **plan only, nothing built.** Implements D-71 (1), (4)–(7) and D-73 for projects; program members are
slice B. Design: `docs/access_v2_decision.md`, `docs/access_v2_model.md`; history D-71…D-73.

## What a person can do when it lands
- An FTC admin creates a project and adds someone as **Admin** on its Access screen.
- That person opens the project's Access screen. They add, change and remove Editors, Viewers and other Admins.
  They cannot touch restriction, components, data-model depth, FTE basis or the DFD rule. Those stay greyed out, and
  the server refuses them.
- A viewer-type user cannot be added above Viewer. The screen offers only Viewer, and the server refuses anything else.
- Changing a user's type, or taking away FTC admin, first shows which project roles come back into force, and asks to
  confirm.

## Grade and depth
**Grade 1.** If it fails silently, someone gets admin or edit rights on client data they should not have, or a
project admin reaches FTC-only settings. Heavy proof is the default. Every check below is a test that runs as a real
user against the real guards:
1. **Every FTC-only route** (6 endpoints) refuses a project admin and a plain editor with 403. The list is taken from
   the route table, so a new FTC-only route cannot be missed.
2. **Every project-admin route** (access list, members list, add, change, remove) refuses a plain editor with 403, a
   project admin of *another* project with 403 or 404, and an outsider on a restricted project with 404.
3. **Level table:** user type × open/restricted × Viewer/Editor/Admin role → the expected level, for every combination.
4. A viewer-type user given Editor or Admin → 422. A platform admin → 422 (as today).
5. A project admin can appoint and remove another Admin, including one an FTC admin appointed (D-73).
6. The restriction preview and the Access list show project admins with their level. The hash covers them.
7. The user-type change preview lists the roles that come back. A stale confirm returns 409.
8. Migration: up, then down. Down refuses once an Admin row exists.
9. The existing leak test (`test_no_get_route_leaks_a_restricted_project`) adds a project-admin-of-another-project
   persona.

**Deliberately left uncovered:** two FTC admins changing the same user's type at the same moment. The row version
already gives the second one a 409; I won't write a dedicated race test for it.

## Build steps (one commit each, small)
1. **Migration 0058:** `project_member.access_level` widened to `varchar(5)` and allowed to hold ADMIN. Its undo refuses
   once an Admin row exists. Taken on `main`'s order: this branch is on `main` (7087ad4), with no other migration since
   0057. The request schemas still accept only Editor or Viewer at this point, so nothing opens yet.
2. **Access core, all in one commit, so no Admin row can exist before the guards are split:**
   - A new `PLATFORM` level above ADMIN, held only by FTC admins.
   - Components, data-model depth, FTE basis, the DFD rule (preview and set) and restriction move to it.
   - The kind cap splits in two: what open staff get (`KIND_BASE`), and the most a role can lift someone to
     (`KIND_CAP`).
   - The level is the higher of the staff default and the project role, capped by kind. Program levels stay
     FTC-admin-only until slice B.
   - One function in `access.py` lists everyone who can open the project, with their level and source. The
     restriction preview, the Access list and member rows read it.
   - Members accept Admin. A viewer-type user above Viewer is refused; this replaces today's "capped" warning.
3. **User-type and FTC-admin changes:** a preview listing the roles that come back into force, then a confirm tied to
   the preview by hash, recomputed under a lock on the user row.
4. **Screens:**
   - The edit check compares levels by rank (FTC admins included).
   - The Access screen opens for project admins, with Admin in the level picker. The restriction toggle stays FTC-only.
   - The Admin page gets the confirm step for user-type changes.
   - Text goes through `t()`.
5. **Tests** as listed above, written alongside steps 2–4.
6. **Checks:** Sara review (it touches access and the migration chain); the full suite (`pytest -m "" -n 4`) on the
   final commit; a browser check of the steps under "What a person can do"; `rules-check-drift`, because CLAUDE.md
   says "only platform admins reach ADMIN"; the BUGLOG backlog line updated.
7. **Merge** to `main` only with Ben's click. No push.

## Size and cost
About **2 working days** and roughly 900–1,200 changed lines, about half of them tests. That is half a day more than
the paper's 1.5 days: the user-type confirm (auditor M1) moves into this slice, because Admin rows can come back into
force as soon as they exist.

## Databases (local, this worktree only, never main's)
New and named clearly:
- `vb_acc_db` (dev)
- `vb_acc_test_db` plus `vb_acc_test_db_gw0`…`gw3` (the test runs)
- `vb_acc_demo_db` (the browser check)

The `vb_s12_*` databases stay, as Ben asked. Dev server ports: API 8112, web 5192. Stopped by PID after each step.

## The "access tests can fail" check
Not in this slice (not approved). I still think it is worth having **once, after slice B**. It would cover the level
calculation, the visibility list and the guard split for project and program access together, at about 1.5 days, since
one pass then covers both slices. It goes back to Ben with slice B's plan.
