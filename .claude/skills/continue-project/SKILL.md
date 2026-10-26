---
name: continue-project
description: Start or resume substantial work on Top Heroes Auto Manager safely - inspect Git state, stashes, uncommitted changes and the latest checkpoint before editing. Use at the beginning of any new development task or after a session/mode change.
---

# Continue the project safely

1. `git status -sb`, `git rev-parse HEAD`, `git stash list`, `git branch -a`, `git log -5 --oneline`; `git fetch origin --prune` is allowed (read-only).
2. Compare any other branch with `git log HEAD..<ref>` and `git diff --stat HEAD...<ref>`; use `git merge-tree --write-tree HEAD <ref>` to test conflicts.
   **Never** merge, rebase, switch branch, reset, clean or stash without the user's decision. Uncommitted user files are theirs: edit around them.
3. Read the newest `docs/OCT*_*.md` checkpoint, `docs/SAFETY.md`, the tail of `docs/PROGRESS.md`, and `AGENTS.md`/`CLAUDE.md`.
4. Identify unfinished work (uncommitted files, stashes, TODOs in the latest checkpoint) and state it before starting new work.
5. Implement only the authorised scope, run targeted tests, self-review `git diff`, commit/push only when asked.
6. Never start the next product phase as workflow setup. Line endings: tracked files are LF; some working files are CRLF - do not normalise them.
