# Single-agent Codex workflow

Use one Codex agent for repository work. Do not route work to custom Developer
or Reviewer agents, or spawn/delegate work to child agents.

For each substantial task, the single agent follows this sequence:

1. Read the current Git state and latest applicable checkpoint.
2. Inspect unfinished work and preserve completed work and uncommitted changes.
3. Implement only the authorized scope.
4. Run targeted local tests; run the full project gate only when requested or
   required by the current task instructions.
5. Self-review the diff for correctness, safety, and scope.
6. Commit and push only when authorized.
7. Let GitHub Actions run the full lint, test, Windows build, and smoke gate.
8. Perform real Windows/LDPlayer acceptance only when explicitly authorized.

## Real account selection and acceptance

- Discover live inventory and current protection. Randomly select from the
  authorized non-Protected candidates; record candidates, method and result.
- Bind the entire test to that verified identity. Randomize between runs, never
  between actions. There is no default test account or preferred index/name.
- For additional cross-account coverage choose a different eligible account.
  Successful test claims count toward acceptance and must never be repeated.
- After implementation and passing CI, use the fresh artifact and a new explicit
  snapshot of all authorized non-Protected accounts for full phase acceptance.
  Process sequentially, max_concurrency = 1, and finish unaffected accounts.
- Record original selection/running state and excluded Protected accounts.
  Re-check protection before each action, including cleanup; never override it.
- Restore each target's selection and only stop instances owned by this run.
  Do not add newly discovered accounts mid-run. Run Selected remains unchanged.
- Report unresolved paths honestly as PARTIAL/BLOCKED, never as unavailable or
  PASS. Do not stop at survey-only or CI-only evidence when real acceptance is
  authorized. Real scope still requires explicit user authorization.

## Safety boundaries (all runs)

- Read `docs/PROGRESS.md`, `docs/SAFETY.md`, and the current phase checkpoint
  before any real mutation.
- Queen remains Protected. Never mutate it without explicit current-task
  authorization.
- Use explicit indexed ADB only. Never use a default/first-device/index-0
  fallback, `quitall`, broadcast, or other global LDPlayer operation.
- `UNKNOWN` means no gameplay input. Never use blind coordinate-only gameplay.
- Claim only independently proven free rewards. Never spend money, diamonds,
  premium currency, tickets, speedups, items, or other resources.
- Never rename LDPlayer instances or repeat completed claims or surveys.
- Preserve unrelated running instances and verify exact target identity before
  any authorized mutation.
- Never start the next product phase as a side effect of workflow setup.

## Permanent Windows app delivery

Every new testable Windows version must come from a fresh CI-passing portable
artifact. Deliver it to `C:\Users\ADMIN\Desktop\app`. Verify the artifact run,
commit and copied files. Remove only previous Top Heroes app builds and copied
build ZIPs inside that exact folder, then leave only the newest app version.
Never delete unrelated Desktop files, source, journals, diagnostics or evidence.
Inspect and resolve the destination before recursive removal; an ambiguous file
must be preserved. Record old-build removal and latest-build verification.
