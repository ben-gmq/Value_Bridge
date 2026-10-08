# Evidence

Screenshots from UI test runs (ui-verifier, UAT passes), kept by the date of the test.

- **Never put a file directly in this folder.** Every file goes under a date folder, then a
  folder for the slice or check it proves: `Evidence/<YYYY-MM-DD>/<slice>/NN-<check>.png`,
  for example `Evidence/2026-10-09/slice-4a-1/03-preview-errors.png`.
- The date is the day the test ran, not the day the file was moved.
- Screenshots stay on this machine: `*.png` here is gitignored (the folder layout and this
  README are tracked). Folders from before 2026-10-08 were filed by file date:
  `root-screenshots/` came from the repo root, `playwright/` from `.playwright-mcp/`.
