# Who can do what on a project — decision paper for Ben (2026-10-16)

Status: **for Ben's decision. Nothing here is built.** Data model by `apple` (2026-10-16); reviewed by `design-auditor`
(§8). Once Ben decides, the decisions move to `VB_design_history.md` §3 and `VB_design.md` is rewritten in the same
commit, as usual.

## 1. Where we are today
- **FTC admins** (platform admins) see and change everything.
- **Staff** see every open project: editors can edit, viewers can read. A **restricted** project is seen only by the
  people added to it, as editor or viewer.
- **Nobody but an FTC admin can be "admin" of a project.** Eight project settings sit behind that level: members,
  restriction, components, data-model depth, FTE basis and the DFD rule (preview and set).
- **Programs give no access at all** (decision D-40): putting someone "on a program" means nothing today.

## 2. What Ben asked for (his words)
- "If I assign the users to the project, then only the admin has to create the project and assign the users. If the
  user is assigned to a program, then the project is editable by the admin of the project."
- "Yes, the program admin will also add and remove program members, for sure. No, for the second part, I did mean about
  the program. Wow, even if it's risky work, I still have to do it."

This reverses D-40 ("programs grant nothing") and the rule that only FTC admins reach admin level.

## 3. The proposal in one picture
| Role | How you get it | What you can do |
|---|---|---|
| **FTC admin** | set on the user (as today) | everything, on every project and program |
| **Program admin** | added to a program as Admin | admin on **every project in that program**; adds and removes program members |
| **Program editor / viewer** | added to a program as Editor / Viewer | edit / read **every project in that program**, restricted ones included |
| **Project admin** | added to a project as Admin | adds and removes that project's members; maintains its code lists (wave 1g) |
| **Project editor / viewer** | added to a project (as today) | edit / read that project |
| **Staff, not added** | as today | edit / read open projects only |

Two rules sit on top of every row:
- **You get the higher of your project role and your program role** — never less than either.
- **A viewer-type user can never edit or administer**, whatever they are added as.

## 4. Decisions for Ben (recommendations marked)
1. **Add a "project admin" role?** Recommend **yes** — it is what lets an FTC admin create the project and hand it over.
2. **Add program members (Admin / Editor / Viewer)?** Recommend **yes**, as in §3. Ben has said yes in principle.
3. **Does a program role open a restricted project in that program?** Recommend **yes** — otherwise putting someone on
   a program does nothing for exactly the projects where it matters. The restricted setting still keeps out everyone
   who is on neither the project nor its program.
4. **Is a program admin automatically admin of each project in it?** Recommend **yes** (Ben's "admin of the project"
   through the program).
5. **Who adds and removes members?**
   - Program members: **FTC admin and that program's admins.**
   - Project members: **FTC admin, that project's admins, and the admins of its program.**
   - An admin may add others **up to and including Admin**, at their own level only (a project admin cannot touch the
     program list). Recommend yes.
6. **Which settings stay FTC-admin only?** Recommend: **restricted on/off, components, data-model depth, FTE basis,
   the DFD rule, creating projects and programs, and moving a project between programs.** The project admin gets
   members and code lists. Reason: these change what is priced, or who can see client data, for the whole project.
   Moving stays FTC-only because a program admin could otherwise move a restricted project into their own program
   and so give themselves access.
7. **A viewer-type user given Admin or Editor:** recommend **refuse it with a message** rather than quietly cap it.
8. **Retiring a program that still has members:** recommend **refuse until the members are removed** (nothing
   cascades — VB law 1). There is no program-retire screen yet; this is the rule for when there is.
9. **Project and program admins add people to restricted projects without FTC seeing it first.** Is that intended?
   Recommend **yes** — that is the hand-over Ben described. Every add is audited and appears in the access review
   taken at each freeze. *Alternative:* FTC admin is notified of each add (about half a day more).
10. **When a program admin is removed, do the project admins they appointed stay?** Recommend **yes** — the role belongs
    to the project, not to whoever granted it.
11. **May a project admin demote or remove another project admin, including one an FTC admin appointed?** Recommend
    **yes**, at the same level only; FTC admin can always put it back.

## 5. What people will see change
- The project's **Access** list shows each person's role and **where it comes from**: "direct" or "via program X".
  Removing someone's project role does not remove what they hold through the program — the screen says so before you
  confirm.
- **Moving a project to another program** now changes who can see it. The confirm screen lists who gains and who
  loses access, and FTC admin confirms.
- **Creating a restricted project inside a program** opens it at once to that program's members. The create screen
  names them.
- Program admins can open their program (even before it has projects) and manage its member list.
- **Changing a user's type** (viewer ↔ editor, or taking away FTC admin) now lists the project and program roles that
  come back into force, and asks FTC admin to confirm when anyone's level goes up.
- Members whose login has been switched off still show on the member lists, marked inactive, so they can be removed.

## 6. What it costs
- **Grade 1** — a mistake here shows client data to someone who should not see it, or lets them change it. Heavy proof
  is the default: every route checked as a non-member, a member of a *different* program, a demoted user, and a
  removed member; Sara before each commit; full suite before the merge.
- **Build: about 5 working days**, in two slices:
  - **A — project admin (about 1.5 days):** the Admin role on project members, the FTC-only settings moved behind
    their own guard in the same change, members screen for project admins.
  - **B — program members (about 3.5 days):** the program member list and screen, access through the program, one
    shared "who can open this project" list behind the Access screen, the restrict and move confirm screens and the
    freeze access review, and the user-type change confirm.
- **Optional, its own approval:** a break-the-code check that proves these access tests can fail (about 1–2 days).
- **Schedule:** the 40-day plan grows to about **45 days**. Slice A goes before wave 1g (the code-list screen needs
  the project admin role); slice B can run after 1g.
- **Database:** two additive migrations on `main`; nothing existing changes meaning. Both refuse to undo once an
  Admin or program-member row exists, because undoing would erase membership history.

## 7. Open points (below the line — I'll follow the recommendation unless Ben says otherwise)
- Audit entries for program changes are found by program through the event detail, not a column of their own.
  Fine for now.
- Platform admins are never added as members (as today).

## 8. Design review (`design-auditor`, round 1, 2026-10-16: 0 critical, 2 high, 2 medium, 3 low)
All seven are taken into the build; none needs Ben except the three questions now in §4 (9–11).
| # | Finding | What we do |
|---|---|---|
| H1 | Three screens that list "who can open this project" (restrict preview, Access list, freeze access review) read direct members only — program members would be missing, so FTC admin could restrict a project believing someone is out | one function in `access.py` returns every person, level and source; all of them read it; tests add a program-member persona |
| H2 | Reusing today's "kind cap" name with a new value would make every editor an admin of every open project, and let any editor make themselves program admin | keep the cap's meaning, add a separate "staff default"; a program level comes only from FTC admin or a program membership; tests: a plain editor gets refused on every admin route |
| M1 | Roles held while someone was FTC admin or a viewer quietly come back when their type changes | the user-type change lists them and asks to confirm (§5) |
| M2 | A program member added at the same moment as a restriction is confirmed can slip past the preview | one lock order everywhere — program(s), then project — and the preview is recomputed after locking |
| L1 | A switched-off user's program membership could block retire with nothing visible to remove | shown as inactive and removable (§5) |
| L2 | FTC admins would see read-only screens once their level is renamed | the browser compares levels by rank, in the same change |
| L3 | A program admin of an empty program could not open it | programs you are a member of are visible to you |

**Round 2 (final under the cap, 2026-10-16): the fixes hold; no new high findings; nothing structural.** The model's
tables, keys and undo guards check out. Three points are settled in the code, each with a test:
- The restrict and move confirms **lock the program rows for update** (a weaker lock lets the race back in). A test
  adds a program member during a restrict confirm and expects a refusal.
- The user-type confirm is tied to exactly what was shown: the preview is recomputed under a lock and must match.
- A program level comes only from FTC admin or a program membership (the model is corrected to say so). The test that
  a plain editor is refused on every admin route lands in the same commit.
- Program admins get their own guard to change and remove program members.

