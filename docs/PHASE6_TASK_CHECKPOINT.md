# Phase 6 task ledger — audited 2026-09-22

Branch: `codex/phase6-vip-pack-recruit`, pre-audit HEAD `41b747d`; local and
remote HEAD matched and the worktree was clean before this checkpoint edit.
Phase 6 is **not complete**. Only
`2 / 5-Emmmmm` is authorized for future Phase 6 real work; `0 / Queen` is
Protected and `4 / 3-Chíp` is revoked. Historical evidence from index 4 is
preserved, never authority to mutate it or reuse its coordinates on index 2.

State refers to the **named milestone only**, not completion of its parent
reward task. `CI_PASS` does not imply a real claim. `REAL_ACCEPTANCE_PASS` below
is explicitly limited to the stated navigation route.

| Item | Audited state | Completed evidence and real mutations | Exact remaining work |
| --- | --- | --- | --- |
| VIP | `CI_PASS` — observation-only command; reward claim **not done** | Index-2 VIP Home→page→Home screenshots from 2026-09-20 and 2026-09-21 already show daily-free wording, green `Nhận`, and a separate paid offer. Five index-2 VIP templates exist. `41b747d` added a claim-free survey command, 44 focused tests passed, full Windows CI `35678890820` passed. Run 16 attempted an index-2 launch but stopped at identity mismatch before ADB/game screenshots/taps/claim. Historical index-4 manual VIP claim occurred once; do not repeat it. | Do **not** repeat VIP UI survey merely to rediscover the free label. Independent index-2 postclaim receipt and cycle proof are missing, so production reward task remains `NOT_IMPLEMENTED`; no claim or live retry. Resolve the index-2 identity/config incident before any future authorized real work. |
| Free Pack | `SURVEY_DONE` — inspected shop surfaces only; claim **not done** | Index-2 daily offer, help, daily-pack, weekly/monthly and adjacent shop evidence exists. Help mentions purchases/activation tickets; a red dot on the gift is not proof of zero cost. Historical index-4 manual gift yielded 20 diamonds; do not replay. Fail-closed task scaffolding in `108ea2b` passed CI `35676774563`. | Obtain independent current-account zero-cost, availability and postclaim evidence or retain `NOT_IMPLEMENTED`. Do not tap red-dot gift, paid pack or ticket control to test a hypothesis. No repeat of accepted daily-pack navigation for this item. |
| Free Recruit | `SURVEY_DONE` — page evidence only; claim **not done** | Index-2 Tavern-selected, Recruit-open and exit screenshots exist; free `3/3`, tickets 277 and diamonds 4114 were observed without recruit input. Five index-2 Recruit templates and fail-closed task scaffolding exist; `108ea2b` CI passed. Historical index-4 manual free recruit happened once; do not replay. Newer same-account selected-name/menu matches failed conservative gates, so no live Recruit survey was packaged. | Qualify a reliable current-account Tavern→Recruit route without lowering the `.97` Tavern threshold, then independent free-result/receipt, paid-alternative and cycle evidence. No free/x10 recruit tap while these are absent. |
| Free Reward Explorer | `CI_PASS` — safety foundation only; production integration **not done** | `63dfc86` introduced free-only guard and bounded explorer; `9db7a1c` CI `35525124909` passed. `b8be92a`, `53c2462` and `4a08d22` added/tested current-frame matching, paid/UNKNOWN diagnostics, bounded nested traversal, red-dot discovery, durable RESERVED/VERIFIED journal and fail-closed task scaffolding; their Windows CI runs passed. No explorer-driven real claim was accepted. | Bind only independently qualified account-specific screen adapters/receipts; prove recurrence/cycle instead of guessing reset. Integrate with reward tasks and test no premium/resource spending. Foundation tests/CI need not be repeated without a relevant code change or regression. |
| Shop Traversal | `REAL_ACCEPTANCE_PASS` — **bounded daily/help/daily-pack route only**; full Tiệm traversal **not done** | Manual index-2 survey already photographed multiple shop tabs and vertical/horizontal boundaries. Production run 9 accepted Home→daily→help→daily→Home; run 13 accepted the same bounded route; run 15 accepted Home→daily→help→daily→daily-pack→daily→Home with `claims=[]`, `journal_rows=0`, owned cleanup and identical before/after inventory. Run 15 report: `%LOCALAPPDATA%\TopHeroesAutoManager\diagnostics\tasks\shop-survey\5-Emmmmm\20260922-014852-111006Z\report.json`. `108ea2b` CI `35676774563` passed. Run 14's identical route failed overall isolation and is **not** acceptance. | Qualify and integrate the remaining named tabs/nested menus and vertical/horizontal scroll boundaries with visited fingerprints and bounded stop conditions. Report PARTIAL until coverage is proven; do not rerun the already accepted daily-pack route just because another tab is unfinished. No reward claim authority follows from navigation acceptance. |

Saved current-account evidence is under
`%LOCALAPPDATA%\TopHeroesAutoManager\diagnostics\vision\5-Emmmmm\`.
Notable VIP frames: `20260920-180241-073168Z-phase6-vip-open-after.png` and
`20260921-174132-284341Z-phase6-20260922-vip-current-after.png` (with
before/exit frames). Recruit frames: `20260920-180742-342934Z-phase6-recruit-open-before.png`,
`20260920-180746-889930Z-phase6-recruit-open-after.png`, and the
`20260920-181311-372913Z` / `181316-988122Z` exit pair. Versioned crops
are in `assets/tasks/phase6/{home,vip,recruit,shop}`. Existing tests include
`test_phase6_vip_survey*`, `test_phase6_visual.py`, `test_phase6_tasks.py`,
`test_phase6_shop*`, `test_free_rewards.py`, and `test_exploration_vision.py`.

## Run 16 identity/config incident — live work paused

Fresh CI artifact `10673824670` from `41b747d` was used once for `vip-survey`
on index 2. Its task report is
`%LOCALAPPDATA%\TopHeroesAutoManager\diagnostics\tasks\vip-survey\5-Emmmmm\20260922-022543-065287Z\report.json`;
recovery report is
`%LOCALAPPDATA%\TopHeroesAutoManager\diagnostics\recovery\5-Emmmmm\20260922-022543-245559Z\report.json`.
The launch command was attempted, then the immutable-name guard saw index 2
as running `LDPlayer-2` instead of `5-Emmmmm` and stopped before explicit ADB
resolution, screenshot, gameplay input or reward action. Task result `ADB_ERROR`,
`survey=null`, `claims=[]`, `journal_rows=0`. The report's
`started_by_run=false` is **not proof no launch was dispatched**: current
recovery code sets it only after the entire launch/verification call returns.
No cleanup was attempted because ownership was unproven. A concurrent read-only
check found `leidian2.config` had only seven `propertySettings.*` keys rather
than the 84-key pre-ADB backup, with name/ADB settings missing. Later read-only
checks saw 13 keys and index 2 stopped, still named `LDPlayer-2`; external
state continued changing after the task and no agent cleanup was sent. The
reports establish the timing, **not the cause** of that rewrite. An old
pre-ADB backup exists but must not be blindly copied over current state.
At the latest audit check index 2 was stopped under the wrong name. No further real
Phase 6 mutation, index-only cleanup, automatic rename, config restoration,
ADB enabling or live acceptance is permitted until exact identity and repair
authority are resolved. Queen and index 4 received no task mutation.

## No-repeat rule and next checkpoint

Mark a completed step reusable. Repeat only when its relevant production code
changed afterward, a regression failed, CI invalidated it, or the evidence is
genuinely insufficient for that **same** step. Record that reason and the
specific old/new evidence before a repeat. A new Codex session or an unfinished
different Phase 6 item is never a repeat reason. Never repeat an uncertain or
completed real claim to manufacture fixtures. Every account rediscovers a
target from its own current screenshot; no index-4 coordinate authority.

Next exact action under the present pause: keep real device work frozen,
preserve run-16 evidence and independently review the launch-ownership/reporting
gap offline. Do not restart VIP survey or the accepted shop route. After any
separate repair authorization, verify the original index-2 identity,
selection/protection, ADB debug, explicit ADB/boot mapping and stable unrelated
inventory before considering only a genuinely unfinished real acceptance.
