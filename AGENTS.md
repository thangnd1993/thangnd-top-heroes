# auto-top-heroes workflow

This repository uses the project-local `auto-top-heroes` Codex workflow. On a new substantial task, first inspect `git status`, the current branch and recent commits, then read the latest applicable progress/safety checkpoint. Do not restart completed phase work or discard uncommitted changes. See [docs/codex-agent-workflow.md](docs/codex-agent-workflow.md) for routing and use.

The parent Codex session orchestrates agents and passes their results directly. Route by actual scope and risk:

- Small, isolated work: `auto-top-heroes-developer` only. Focused validation, then authorized commit/push. No reviewer.
- Medium, contained work: developer first. Add one `auto-top-heroes-reviewer` final review only when the actual diff or runtime risk warrants it; no planning call by default.
- New phase or high-risk automation/architecture, LDPlayer lifecycle/selection/ADB, computer vision architecture, account safety, resource spending, real gameplay mutation, queue/scheduler, or destructive work: reviewer plan → developer implementation and self-review → reviewer final review. Normally at most two reviewer calls and one developer session plus one fix continuation. Re-review after fixes only for account safety, destructive actions, purchases/resources, wrong-instance targeting, serious correctness, or an architecture blocker. The parent resolves ordinary review findings without a review loop.

Use the named project agents when this Codex client exposes custom agent selection. If it exposes only generic spawn controls, select the exact model and effort from the agent files and include their role instructions in the assignment. If subagents are unavailable, perform the work in the parent and report that routing could not be validated; do not silently claim the configured agents ran.

For real LDPlayer work, read [docs/PROGRESS.md](docs/PROGRESS.md), [docs/SAFETY.md](docs/SAFETY.md), and the current phase checkpoint (currently [docs/PHASE6_RESUME.md](docs/PHASE6_RESUME.md)), then resolve the explicit allowlist. The current Phase 6 checkpoint authorizes only `2 / 5-Emmmmm`; `4 / 3-Chíp` is revoked for Phase 6. `0 / Queen` remains Protected and must never receive lifecycle, ADB, or gameplay mutation without explicit current-task authorization. Do not select any different real clone or broadcast to all instances. Preserve unrelated running instances.

Use existing indexed LDPlayer and verified explicit ADB boundaries. Verify exact index/name, selection/protection, boot identity, and intended game before mutation. Discover targets from each account's current screenshot, verify the expected state, take one evidence-guarded action, and verify the fresh result. Bound nested tab, submenu, vertical/horizontal scroll, and red-dot exploration. Red dots are discovery signals only. Claim only independently proven free rewards; ambiguous cost or state fails closed. No automatic money, diamonds, premium currency, tickets, speedups, items, or other resource spending.

Use focused local tests during development and the repository's required final gate once. Minimize real device runs; preserve screenshot evidence, avoid repeating claims with uncertain outcomes, and report cleanup/isolation accurately. Never start the next product phase as a side effect of workflow setup.
