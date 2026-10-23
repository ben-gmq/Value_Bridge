# Value Bridge — why the full test run takes 12 minutes, and what to do (proposal, 2026-10-23)

Measure-and-propose only (Ben 2026-10-23, "1 yes"). Nothing in the test setup has changed. Each option below is its own
task for Ren / Ben to approve.

## Where the 12 minutes go
Full run on `0afa86d`: **1021 tests, 4 workers, 705 s** (11 min 45 s). Across the four workers that is 2631 s of test time:

| Part | Time | Share |
|---|---|---|
| Building each test's data (setup) | 1114 s | 42% |
| Wiping it afterwards (teardown) | 878 s | 33% |
| The tests themselves | 639 s | 24% |

So three quarters of the time is preparing and clearing data, not testing.

**One file is almost a quarter of it.** `test_purge_run.py` (the project-removal tests) takes **609 s**: 31 tests, each
rebuilding the full showcase project, freezing it twice and stamping the database (~12 s under load), then wiping it all
(~7 s). Its test bodies take 12 s in total. Next largest: `test_baseline.py` 174 s, `test_purge_bypass.py` 90 s, the
migration tests ~140 s together. The slowest single test is the "no GET route leaks a restricted project" sweep, 33 s.

**What it is not** (measured, so nobody spends time there):
- Password hashing: 288 hashes took 0.3 s in total. Making them cheaper saved nothing (122 s vs 124 s).
- The harness's own bookkeeping (which tables a test touched): about 1 s per 62 tests.
- The per-worker migration walk at start: ~9–11 s, once per worker.

**What it is:** every commit waits for the disk to confirm the write (PostgreSQL's `synchronous_commit`). Tests commit
constantly — every API call, every wipe — and four workers queue on the same disk under WSL. The wipe is mostly this.

## Measured: the same tests with commits not waiting for the disk
Only this run's own connections were changed (an environment variable); the server and every other database were not.

| Files (one worker) | As now | Commits not waiting | Saving |
|---|---|---|---|
| test_access + test_baseline + test_code_lists (62 tests) | 138 s | 89 s | −35% (teardown −59%) |
| test_purge_run (31 tests) | 266 s | 200 s | −25% |
| Full suite, 4 workers | 705 s | reached 77% in 394 s → **~510 s projected** | ~−27% |

The full-suite run with the setting was cut off at 77% when the session ended, so its total is a projection, not a
measurement; option A's own full run gives the real figure.

## Result of option A (approved and built 2026-10-23, `0a0f6df`)
Ben: "Yes go with A". Measured on a quiet machine: **full run 705 s → 690 s (−2%)**, 1021 passed. The ~27% projected
above was wrong — the cut-off run had not yet reached the slowest files, which run last — so A does little for the
four-worker full run. It does save 25–35% on a single-process run (the everyday `pytest`, one file at a time), and it
changes no test, so it stays. What limits the four-worker run is therefore not the commit wait; finding that out is the
first step of B (below), before any build.

## What limits the four-worker run (measured 2026-10-23, Ben: "1. Yes")
One instrumented full run (585 s; the same suite measured 585–705 s across today's runs, so ±15% is noise):
- **Not uneven workers:** all four were busy ~570 s and finished within 12 s of each other.
- **Not the processor or the disk's capacity:** the machine sat 71% idle; waiting on the disk only 5%.
- **It is waiting for one kind of disk sync, one at a time.** Time splits: preparing data 40%, the tests 25%, **clearing
  data 35% (808 s)**. When the cleanup login is working, 73% of that time it is waiting on `DataFileImmediateSync` —
  PostgreSQL forcing each freshly emptied table and index file to disk, which is what `TRUNCATE` does and option A
  cannot touch.
- **Where:** 182 tests (those that freeze a baseline or change a code list) take the harness's "empty the whole group"
  path and spend 1–5 s each clearing up — **674 s of the 808 s**. Emptying the baseline group alone (39 tables, 123
  indexes) costs **645 ms**; deleting the same rows costs **~1 ms** (measured on this worktree's test database).

## Option C — clear test data by deleting rows, not emptying tables (proposed)
- What: the harness's cleanup (`tests/conftest.py` `clean()`) deletes rows children-first — as it already does for most
  tables — also for the append-only group (their guard triggers switched off inside that one cleanup transaction, as the
  owner, on test databases only — the harness already does exactly this for `vb_instance`), and for the library path
  (delete and re-copy only the library rows a test changed). `TRUNCATE` stays only as the fallback for a cycle of
  references that has no column to clear first.
- Proof that every test still starts from the same fresh state: after each cleanup the harness re-checks that every table
  is empty and every id counter restarted, and fails the run if not; then the full suite twice.
- Saves: most of the 674 s → **about 2–2½ minutes off the full run** (≈ 10–11½ → 8–9 min), and the same share of every
  everyday run.
- Effort: **about half a day.** Risk: low–medium — test plumbing only; the guards stay on everywhere except inside the
  test cleanup transaction, and production code does not change. Sara reviews it (it switches a guard off, even in a test).
- After C: re-measure. Then B (the removal tests build their sample once) and a fifth/sixth worker (the machine is mostly
  idle) are each a short measurement before any build.

## Options

**(A) Test connections don't wait for the disk on commit** — recommended now.
- What: the test harness sets `synchronous_commit=off` for its own connections only (test databases; the app's real
  setting and Ben's databases untouched).
- Saves: ~3 minutes per full run (≈ 12 → 8½ min).
- Effort: about 1 hour, including one full run to confirm the number.
- Risk: very low. If the machine crashes mid-run, the last fraction of a second of *test* data can be lost; the database
  is never corrupted, and the next run wipes it anyway. No test or assertion changes.

**(B) Build the removal tests' showcase once per worker and copy it for each test** — a separate task, after A.
- What: `test_purge_run`'s `rich` world is built once, saved, and restored before each of its 31 tests instead of rebuilt.
- Saves: most of that file's ~150 s share of the run → another ~1½–2 minutes (with A: ≈ 6½ min).
- Effort: half a day to a day.
- Risk: medium. These tests prove that a removal deletes exactly the right rows (Grade 1), so the restored copy must be
  proven identical to a fresh build — a test that compares every row of both — and Sara reviews it before it lands.

**(C) A fifth worker** — a 15-minute measurement after A, not before: the run is waiting on the disk, so more workers
only help once A has removed that wait.

**Not proposed:**
- Removing, merging or loosening tests.
- Switching off disk safety for the whole database server: Ben's real databases share it.
- A second, memory-only database server for tests: a bigger change, with another server to keep running.

## Recommendation
Approve **A** now (about 1 hour, ~3 minutes saved on every full run). Then decide on **B** once A's real number is in.
