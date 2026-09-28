# Value_Bridge

Internal Fortience Consulting tool for running business and process assessments —
business requirements, the process hierarchy, data entities, issues, and the solutions
and solution requirements derived from them. Multi-engagement: every assessment is a
separate engagement inside one tool.

First use: the project being proposed from 2027.

## Status

**Design signed off by Ben on 2026-09-28** (`docs/VB_design.md`, both design-review rounds
closed). Build in progress, starting with the foundation (auth, projects and programs,
access control, code master). Build plan: https://claude.ai/artifact/KReFrU3AkML4cZBzM2C9L9

| Document | What it is |
|---|---|
| `docs/VB_design.md` | The signed-off design spec — the source of truth |
| `docs/VB_機能一覧.md` | Function list in Japanese, for project members and the client |
| `docs/ASSESSMENT_BRIEF.md` | Ben's original brief |
| `BUGLOG.md` | Defects and the standing review backlog |

Stack (FTC standard): React + MUI + Vite frontend, FastAPI + PostgreSQL backend, JWT auth,
hosted on Azure (Japan East).
