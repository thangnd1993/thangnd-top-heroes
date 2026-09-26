# auto-top-heroes workflow

**Permanent, all phases:** LDPlayer instance names are user-owned and read-only.
Automation must never rename an instance unless the user explicitly requests
that exact rename. Never repair identity by changing an LDPlayer name or restoring
an old config. Rediscover current names exactly, preserve Protection, verify
technical identity, and fail closed if ambiguous.

This repository uses one Codex agent. On a new substantial task, inspect Git
status, current branch and recent commits, then read the latest applicable
progress/safety checkpoint. Do not restart completed work or discard uncommitted
changes. See [docs/codex-agent-workflow.md](docs/codex-agent-workflow.md).

Single-agent sequence:

read checkpoint → inspect unfinished work → implement → targeted tests →
self-review diff → commit/push when authorized → GitHub Actions full
lint/test/Windows build/smoke → real Windows acceptance only when explicitly
authorized.

Real development checks must choose a test account randomly from live authorized
non-Protected inventory. Record the eligible set and selection method, then bind
the whole test to that exact verified instance. Never default to index 2 or any
preferred name. Use another eligible account for additional cross-account checks;
never repeat a successful claim for coverage.

When full phase acceptance is authorized, use the fresh passing CI artifact and
an explicit snapshot of ALL currently non-Protected targets, sequentially
(`max_concurrency = 1`). A successful random test or availability scan does not
finish acceptance. Preserve same-period claim locks, original selections and
external running instances. Normal application Run Selected scope is unchanged.

Preserve all project safety rules:

- Queen is Protected; never mutate without explicit current-task authorization.
- Use explicit indexed ADB only. No default, first-device, or index-0 fallback.
- No `quitall`, broadcast, or global LDPlayer operations.
- `UNKNOWN` means no gameplay input; no blind coordinate-only gameplay.
- Free-only claims. Never spend money, diamonds, premium currency, tickets,
  speedups, items, or other resources.
- Never rename LDPlayer instances or repeat completed claims/surveys.
- Read [docs/PROGRESS.md](docs/PROGRESS.md), [docs/SAFETY.md](docs/SAFETY.md),
  and the current phase checkpoint before real mutation.
- Verify exact target identity and preserve unrelated running instances.
- Never start the next product phase as workflow setup.

## Permanent Windows app delivery

Every new testable Windows version must come from a fresh CI-passing portable
artifact. Deliver it to `C:\Users\ADMIN\Desktop\app`. Verify the artifact run,
commit and copied files. Remove only previous Top Heroes app builds and copied
build ZIPs inside that exact folder, then leave only the newest app version.
Never delete unrelated Desktop files, source, journals, diagnostics or evidence.
Inspect and resolve the destination before recursive removal; an ambiguous file
must be preserved. Record old-build removal and latest-build verification.
