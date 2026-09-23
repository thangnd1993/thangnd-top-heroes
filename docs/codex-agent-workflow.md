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

## Safety boundaries

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
