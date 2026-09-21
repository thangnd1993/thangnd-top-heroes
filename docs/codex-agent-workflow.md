# auto-top-heroes Codex workflow

Open a new trusted Codex session in this repository and say: **“Continue the next phase using the auto-top-heroes workflow.”** The parent reads `AGENTS.md`, current Git state, and the latest phase checkpoint, then routes work and passes agent results directly. A new session is required to load changed project instructions and agent files. The repository remains the source of truth for the active phase and authorized account.

| Scope | Route | Review budget |
| --- | --- | --- |
| Small: typo, copy, lint, docs, obvious isolated fix | Luna developer → focused checks → authorized commit/push | No Astra |
| Medium: contained automation, UI, ADB helper, or test improvement | Luna developer first; Astra final review only for concrete risk | Zero or one Astra |
| Major/high risk: new phase, lifecycle/selection, vision architecture, resource protection, real gameplay mutation, multi-account, queue/scheduler, destructive change | Astra plan → Luna implementation/self-review/validation → Astra final review | Normally at most two Astra calls |

The reviewer is `auto-top-heroes-reviewer` (`gpt-6-astra`, reasoning `low`, read-only). Planning covers current state, affected files, steps, safety risks, focused tests, and acceptance criteria. Final review checks the actual diff and relevant results, returning `APPROVED` or `CHANGES_REQUIRED` with concrete findings. The developer is `auto-top-heroes-developer` (`gpt-5.6-luna`, reasoning `max`). Luna owns implementation, focused tests, normal fixes, documentation, and authorized Git completion. Normal developer budget is one implementation session plus an optional fix continuation. Repeat Astra review after fixes only for serious account, purchase/resource, destructive, wrong-instance, correctness, or architecture risks.

The custom agent files live under `.codex/agents/`; `.codex/config.toml` caps concurrent child agents at one because the normal route is sequential. `AGENTS.md` supplies routing to each new project session. These instructions guide orchestration; they do not schedule tasks or expand permission to mutate devices, spend resources, or push to an unapproved destination. If a client lacks named custom agent selection, the parent uses the model/effort and role instructions from those files with its available spawn controls and reports the actual route used.

For real Windows/LDPlayer tests, first read the current checkpoint and resolve the exact allowlisted index/name. As of Phase 6 it is `2 / 5-Emmmmm`; `4 / 3-Chíp` is revoked for Phase 6. `0 / Queen` remains Protected. Verify current selection, protection, indexed ADB serial and Android boot identity, and the intended game before any mutation. Do not broadcast to all instances. Use current-account screenshots for dynamic target discovery, a verified screen/action/postcondition cycle, bounded nested menu/scroll exploration, and fail-closed free-only guards. Red dots reveal candidates, not permission to claim. Never spend money, diamonds, premium currency, tickets, speedups, items, or other resources by default. Use mocks and recorded screenshots before the minimum necessary real device acceptance; clean up the owned test instance and preserve unrelated processes.

Routing dry run (classification only; none of these product tasks should execute):

| Request | Expected route |
| --- | --- |
| Fix a typo in the Auto Top Heroes UI. | Luna only |
| Improve one isolated screenshot helper. | Luna; Astra final review only if actual risk warrants it |
| Continue the next Top Heroes automation phase. | Astra plan → Luna implementation → Astra final review |
| Change which LDPlayer account receives real mutation tests. | Astra plan → Luna implementation → Astra final safety review; resolve authorization from current repository state |

Use focused local tests while editing. Run the required phase gate once at completion, normally through GitHub Actions for full Windows lint/test/build/smoke. For a completed authorized task, inspect the diff, update progress docs, commit and push the tracked branch without rewriting history, then verify local/remote HEAD and a clean tree. The current Phase 6 checkpoint remains incomplete; creating this workflow does not advance the product phase.

Configuration follows the [official OpenAI custom agent schema](https://learn.chatgpt.com/docs/agent-configuration/subagents) and [project instruction discovery](https://learn.chatgpt.com/docs/agent-configuration/agents-md).

Validation on this Windows installation (Codex CLI 0.155.0-alpha.9.2): strict project configuration loaded; a fresh trusted session loaded `AGENTS.md`; TOML parsing and the bundled model catalog accepted both requested model/effort pairs. A bounded read-only session spawned each named custom role in sequence. Its saved child turn metadata showed `gpt-6-astra/low` for the reviewer and `gpt-5.6-luna/max` for the developer. A separate read-only classification returned the four routes above. No sample task was implemented and no LDPlayer action occurred.
