# Phase 6 interruption checkpoint — 2026-09-20

## 2026-09-22 bounded partial shop-survey acceptance (real run 13)

- Commit `32142ea` passed full Windows CI run `35671625455`. Fresh artifact
  `10671690862` archive is 105,306,520 bytes, SHA-256
  `0E6DD4E2842CD1EDC1B5082367AE5E88D45874E193E400AB4F37FA1EEB5DA5F8`.
- One real `shop-survey` run on only `2 / 5-Emmmmm` completed its packaged
  navigation route with result **PARTIAL**, as designed: a single known-promo
  Back reached fresh Home, then four screenshot-guarded taps traversed
  Home → daily offer → information popup → daily offer → Home. Explicit ADB
  `emulator-5558`, boot `4eccccff-f330-4a56-9a1b-59247568d004` stayed
  constant. Report:
  `diagnostics/tasks/shop-survey/5-Emmmmm/20260922-002655-011534Z/report.json`
  in local app data (task run 13). `claims=[]`, `journal_rows=0`, owned
  cleanup succeeded, `isolation_changed_indices=[]`. Queen and revoked
  index 4 remained stopped; externally running 1, 6 and 7 were preserved.
- This accepts only the packaged Home/daily/help observation route. The
  survey honestly reports `coverage_unknown_or_dynamic`; other shop tabs,
  nested sections, vertical/horizontal scrolls and all reward claims still
  need independent evidence and production integration. No final merge or
  Phase 7. Next: qualify adjacent index-2 tabs offline, then extend bounded
  production traversal without adding claim authority.

## 2026-09-22 initial-promo live success, survey time-bound checkpoint (run 12)

- Commit `a688f88` passed full Windows CI run `35670480460`. Fresh artifact
  `10669934367` archive is 105,307,628 bytes, SHA-256
  `AB73BEE2FC13AC337B582D6A714D0676BFBEF84B3195C8DDD1C2F8609C9C1886`.
- One real `shop-survey` run on only `2 / 5-Emmmmm` verified explicit ADB
  `emulator-5558`, boot `fd627bd7-c58f-488d-8376-88f7cd6f5ac3`. The known
  full-screen Stranger Things promo appeared on the first survey frame after
  Home recovery. Exactly one observed-target Back closed it; a fresh same-boot
  frame independently verified unobstructed Home. The survey then used
  screenshot-guarded Home → daily offer → information popup → daily offer.
- The result is **TIMEOUT**, not survey acceptance: the 30-second survey bound
  expired before the final daily-offer → Home step. Report:
  `diagnostics/tasks/shop-survey/5-Emmmmm/20260922-001328-382093Z/report.json`
  in local app data. `claims=[]`, `journal_rows=0`; owned index-2 cleanup
  succeeded. Queen and revoked index 4 remained stopped; externally running
  indices 1, 6 and 7 were preserved. Do **not** rerun this artifact blindly.
- Next: review the measured capture/action times, adjust only the bounded
  observation-only survey limit with regression tests (and qualify any added
  adjacent tab offline), then fresh CI artifact and one scoped live run.
  Reward tasks, comprehensive shop traversal, final merge and Phase 7 remain
  incomplete/out of scope.

## 2026-09-22 initial-frame promo checkpoint (real run 11 blocked safely)

- Commit `711e708` passed Windows CI run `35667419060` (full lint, tests,
  package and executable smoke). Fresh artifact `10670015360` was downloaded;
  its archive is 105,302,907 bytes, SHA-256
  `8D87B86D0673FB239DF2D179F5B41E7C7606FA0C6697AEC83B84C87A0DD997F4`.
- One `shop-survey` run on only `2 / 5-Emmmmm` safely stopped before any
  survey action. Recovery verified `GAME_HOME` on explicit ADB `emulator-5558`,
  boot `18939681-40ca-4b0e-9b99-53f939bec0ae`; the first survey capture
  two seconds later showed the known Stranger Things popup. The post-navigation
  popup handler was correctly not armed because no navigation had occurred.
  `actions=[]`, `claims=[]`, `journal_rows=0`; owned cleanup succeeded and all
  instances returned to their prior stopped state. Report:
  `diagnostics/tasks/shop-survey/5-Emmmmm/20260921-233200-702519Z/report.json`
  in local app data. Do **not** rerun this artifact blindly.
- Next: a separately reviewed, one-time initial-frame promo guard bound to the
  successful recovery serial/boot, sharing the single-Back budget and requiring
  a fresh unobstructed Home before any shop tap. Then targeted tests, fresh CI
  artifact and one bounded real acceptance. Phase 6 remains PARTIAL; no reward
  acceptance, final merge or Phase 7 is authorized by this checkpoint.

## 2026-09-22 partial shop-survey checkpoint (real run 10 blocked safely)

- Observation-only partial-survey infrastructure commit `ca14c96` passed
  Windows CI run `35662061780`: full Ruff, pytest, PyInstaller, executable
  smoke and fresh artifact `10666928804`. The downloaded archive is
  105,296,688 bytes, SHA-256
  `633A96C5BDE64DF04D16B420B774200AB356EA8D4AE0E4176E24EEC3D2C697F6`.
- Fresh artifact task run 10 on only `2 / 5-Emmmmm` was **SAFETY_BLOCKED**, not
  accepted. Standard recovery reached `GAME_HOME` on explicit ADB
  `emulator-5558`, boot ID `538776d2-082b-441c-a4f7-4b603a65fad3`.
  After one current-frame-guarded Home→shop tap, a delayed Stranger Things
  popup appeared in the next capture. The strict page registry refused it;
  there was no further navigation, Back, claim, purchase, ticket use or journal
  row. The known title matches at 0.999936 in that fresh frame. Owned cleanup
  succeeded, all instances returned to their prior stopped state, and Queen
  and revoked index 4 remained untouched. Durable report:
  `diagnostics/tasks/shop-survey/5-Emmmmm/20260921-222627-200207Z/report.json`
  in local app data. Do **not** rerun this artifact blindly. Next is a
  reviewed, one-action known-promo interstitial handler after navigation,
  with same-boot destination proof and no retry of the preceding shop tap.
- The packaged survey currently knows only Home/daily/help; directional
  traversal is tested infrastructure, not real multi-tab/scroll coverage.
  Phase 6 remains PARTIAL; reward claims and final merge remain blocked.

## 2026-09-22 fresh-artifact shop navigation acceptance (Phase 6 still PARTIAL)

- Commit `476e1a8` passed Windows CI run `35656740331`: full Ruff, pytest,
  PyInstaller build, executable smoke and artifact upload `10665326562`.
  The downloaded archive is 105,261,941 bytes, SHA-256
  `CD79AEC2E8BAD6910D740504F3BAB9F8043D52C1DB3E18B838CE2CB288BF2F9D`.
- Earlier artifact `92a85fc` produced task run 8: standard Home recovery
  started only index 2, but timed out on a Stranger Things popup. No shop tap,
  claim or purchase occurred; owned cleanup succeeded. A Phase-6-shop-only
  known-promo handler now matches its title uniquely on a fresh frame, binds
  account/serial/boot, sends at most one observed-target Back, and verifies
  fresh Home. Default Phase 4/5 recovery remains unchanged. Astra final safety
  review approved; parent reran 98 focused regressions, Ruff and diff checks.
- Fresh artifact task run 9 succeeded on only `2 / 5-Emmmmm`: after bounded
  `LOADING_TIMEOUT`, one recognized promo Back produced same-boot `GAME_HOME`
  (confidence 0.989572); then four current-frame-guarded taps completed
  Home → Tiệm daily → information popup → daily → Home. Report:
  `diagnostics/tasks/shop-navigation-survey/5-Emmmmm/20260921-212914-623760Z/report.json`
  in local app data. Explicit ADB was `emulator-5558`, boot ID
  `5636e549-fdab-44d0-b9a5-6b106402b8bc`. `claims=[]`, `journal_rows=0`,
  owned cleanup succeeded and before/after inventories were identical. Queen
  and revoked index 4 stayed stopped and untouched.
- The live daily-offer information text describes purchases and an activation
  ticket. The red-marked gift is **not proven zero-cost** and was not tapped.
  This is navigation-only acceptance, **not** Free Pack, VIP, Free Recruit,
  complete nested shop traversal, or Phase 6 completion. Do not merge main or
  start Phase 7. Next work is production bounded submenu/scroll coverage and
  independent free-cost/postclaim receipts for guarded reward acceptance.

## 2026-09-22 continued implementation (still not acceptance)

- Authorized index `2 / 5-Emmmmm` was started only through guarded Home
  recovery. Explicit ADB `emulator-5558` and fresh boot ID
  `a475da84-8ba9-4e3f-947f-e0282791a39d` were verified. Current daily
  shop help described purchases and an activation ticket; it did not prove
  the red-marked gift free. Current VIP again showed explicit free daily
  wording/green `Nhận`, but no claim was made. Two Tavern image matches failed
  before dispatch; no Recruit action was sent. Owned index 2 was stopped;
  Queen and revoked index 4 remained untouched. See `PHASE6_SURVEY.md`.
- Added current-frame postclaim outcome classification and bounded shop
  discovery primitives. A cooldown is **not** a verified claim: its durable
  journal reservation remains and retry stays blocked. Missing declared
  shop tab/scroll evidence makes coverage partial, never complete. The
  current Free Pack gift is still cost-ambiguous and cannot be claimed.
- Added individual/sequence Phase 6 UI controls for exact authorized index
  2, cooperative cancellation through Home recovery and each entry step,
  and persistent display of the last result. Packaged VIP/Recruit still
  lack independent same-account postclaim receipt anchors; Free Pack has
  no proven zero-cost action. Default task claims remain fail-closed.
- The Astra safety review approved the targeted journal, coverage,
  cancellation and UI-result fixes. Parent reran 109 focused tests including
  offscreen UI, plus changed-module Ruff and diff checks successfully.
  Commit `53c2462` passed Windows CI run `35638066955`: full Ruff, pytest,
  PyInstaller build, executable smoke, and fresh artifact upload
  (`10656758476`). This verifies the build, not a real reward claim.
  Real production acceptance remains open. Do not merge main or start Phase 7.
- An offline follow-up aligned the packaged Tavern match threshold with the
  guarded survey threshold (`0.97`, rejecting observed `0.9449`/`0.8363`)
  and added at most three fresh destination observations without repeating an
  input. Cancellation and boot/serial identity are checked during the wait.
  Focused navigation/assets tests passed (22); parent independently reran
  102 related tests and Ruff. Astra's final safety review approved the diff.
  These synthetic/offline checks do not prove live Tavern recognition or
  authorize a VIP/Recruit claim; receipt anchors remain absent.
- Commit `6a4f9b8` passed Windows CI run `35639781713`: full lint/test,
  PyInstaller build, executable smoke and artifact upload (`10657698681`).
  The unauthenticated artifact-download API returned HTTP 401 locally, so
  no real acceptance from that artifact is claimed.
- Added an injectable, observation-only shop survey engine. It has no claim
  or journal port, retains unvisited sibling obligations, validates the
  actual parent destination before backtracking, and records reward/cost
  candidates only as diagnostics. Missing routes and scroll-direction
  boundaries force PARTIAL. Astra approved the blocking safety fixes;
  developer ran 138 related tests and parent independently ran 116, with
  Ruff/diff checks clean. No packaged index-2 shop route/scroll evidence is
  yet sufficient to wire this to CLI/UI or conduct a live shop survey.
  Free Pack remains NOT_IMPLEMENTED and no reward was claimed.
- Commit `4a08d22` passed Windows CI run `35642294934`: full lint/test,
  PyInstaller build, executable smoke and fresh artifact upload
  (`10658713326`). The exact archive was downloaded through the existing
  authorized GitHub credential, 105,099,995 bytes, SHA-256
  `7671753165409F3F21993D412C7DC041D867E5EE29BB310DFFABA6761F350DD0`.
  It has not been used for live reward acceptance.
- Qualified four same-account navigation-only crops for the daily-offer page,
  information popup, close X, and back arrow. The first crop revision was
  rejected by visual review because its supposed exit anchor was an offer
  item; it was replaced, visually inspected, and retested against neighboring
  shop tabs/popup plus Home/VIP/promo negatives. The back arrow is generic
  and must be gated by separate daily-page identity. Astra approved the
  corrected offline assets; parent reran 32 focused shop tests and Ruff.
  These assets are not wired to a live task and do not prove a free gift.
- Commit `ddbd959` passed Windows CI run `35646815434`: full lint/test,
  PyInstaller build, executable smoke and artifact `10659844555`. The later
  navigation runner changes require their own fresh CI and artifact.
- Added a dedicated `shop-navigation-survey` CLI/UI route for only
  Home → daily offers → information popup → daily offers → Home, capped at
  four current-frame guarded taps. It is separate from Free Pack and the
  reward journal and cannot claim, purchase, use tickets or scroll. The new
  info-button crop was checked against same-account negatives. Recovery
  failures now carry explicit ownership/cleanup state; the task never infers
  ownership from stopped→running or repeats an uncertain quit. Astra's final
  review approved the lifecycle and CLI/UI integration; parent independently
  reran 105 related tests, Ruff and diff checks. CI/fresh-artifact navigation
  acceptance remain open. This route is not full Tiệm traversal or reward
  acceptance. Phase 6 remains PARTIAL; do not merge main or start Phase 7.

## Reviewed safe checkpoint — 2026-09-22 (Phase 6 still PARTIAL)

- The current work adds current-frame VIP/Recruit visual adapters, guarded
  Home entry navigation, CLI task/sequence scaffolding, durable reward-intent
  integration, and task/sequence reports. Phase 6 real claims are deliberately
  blocked: index-2 VIP/Recruit lack independently verified post-claim evidence,
  and the daily shop gift lacks independent zero-cost proof. Free Pack and
  production nested shop traversal remain unsupported; no UI control or real
  production acceptance is claimed.
- Sequence Home/cleanup/persistence paths now preserve failure status, task
  identity, ownership, and cleanup outcome. A lost report/DB write cannot be
  represented as a successful claim or trigger an automatic retry of an
  uncertain quit. The configured Astra safety review approved the targeted
  fix; parent reran 93 focused reward/Phase-6/recovery tests, Ruff, and
  `git diff --check` successfully. Implementation checkpoint `b8be92a`
  passed Windows CI run `35629610052`: full lint, pytest, PyInstaller build,
  executable smoke, and fresh artifact upload (`10654057686`). This is a
  verified build, not real Phase 6 task acceptance.
- The latest guarded real survey used only `2 / 5-Emmmmm`, verified serial
  `emulator-5558` and boot ID
  `38300bf4-de4e-4f50-99e4-bee8c4d0b1ee`, performed navigation and scroll
  only, then stopped its owned start. Queen and revoked index 4 received no
  mutation. See `PHASE6_SURVEY.md` for observed boundaries/evidence tags.
- Do not merge to main or start Phase 7. Next work is independent post-claim
  evidence, free-pack zero-cost proof or explicit unsupported reporting,
  production bounded nested traversal and UI integration, then full CI,
  fresh artifact, scoped real acceptance, and only then final completion.

## In-progress continuation — 2026-09-21 (not acceptance)

- The continuation began from committed branch checkpoint `11b8019`; its
  Phase 6 code and visual-fixture edits were preserved in place. Do not
  discard them or repeat any real claim to recreate fixtures.
- The 2026-09-21 continuation started only `2 / 5-Emmmmm` through guarded
  Home recovery, verified explicit ADB `emulator-5558` and boot ID
  `38300bf4-de4e-4f50-99e4-bee8c4d0b1ee`, then captured fresh same-account
  screenshots for navigation-only shop survey. An attempted Home-to-shop action
  first failed its visual context check and dispatched no input. A promo popup
  was dismissed with one observed Back action; the earlier tap on its decorative
  collaboration symbol had no effect. No reward, recruit, purchase, or resource
  action was performed. The owned index-2 start was stopped after survey;
  `0 / Queen` and revoked `4 / 3-Chíp` remained stopped and untouched.
- The explorer now records paid/ambiguous candidates and continues bounded
  safe discovery without claiming them. New current-frame VIP/Recruit adapter
  primitives and index-2-derived precondition/Home-navigation crops are under
  development. The generated crops matched saved same-account survey frames;
  this is offline evidence only, not live acceptance or cross-account authority.
- The local crops have **no independently verified post-claim anchor** for
  index 2. The daily shop gift still lacks proof of zero cost. Live claims must
  remain fail-closed. Task/CLI wiring remains fail-closed scaffolding. The shop
  left-tab boundary, growth-fund upper boundary, and diamond-shop lower boundary
  were verified in the new survey; production nested traversal, UI, CI/fresh
  artifact, real acceptance, and final review remain open.

## Current authorization — 2026-09-21 (supersedes historical target below)

- Remaining Phase 6 real survey and acceptance target is **only `2 / 5-Emmmmm`**.
- `4 / 3-Chíp` is no longer authorized for any Phase 6 device operation, including
  lifecycle, ADB, screenshot collection, survey or acceptance. Its evidence below
  is historical and its coordinates are not authoritative for the new account.
- Queen remains Protected and must receive no mutation. Other running instances
  are external state and must be preserved.
- User confirmed **Yes, enable ADB for index 2**. Backed up
  `D:\LDPlayer\LDPlayer9\vms\config\leidian2.config` to the same directory as
  `leidian2.config.phase6-adb-backup-20260921`; changed only
  `basicSettings.adbDebug` from 0 to 1 and verified the parsed configuration diff.
  Do not repeat this completed configuration change or overwrite its backup.
- Index 2 was selected after exact identity/not-Protected verification. Its scoped
  ADB was verified as `emulator-5558` with boot ID
  `70b1cc0e-24e0-465f-9e54-4025067f47aa` during this survey. These are historical
  evidence only; resolve and verify again on the next start.
- At this checkpoint index 2 is **stopped** after verified Home and owned-start
  cleanup. Indices 1 (`anh Ry`) and 7 (`Happy`) were already running externally and
  remain running. Queen and index 4 remain stopped and untouched.
- User explicitly authorized normal pushes of this branch to
  `thangnd1993/thangnd-top-heroes`, subsequent Phase 6 commits, and safe merge/push
  to main only after all Phase 6 criteria pass. No force push/history rewrite.
- Phase 7 remains out of scope (future target also index 2 unless changed).

Branch `codex/phase6-vip-pack-recruit` was created from accepted Phase 5 merge
`33cb313576e4c6ca7770988cdac1c5996337ca51`. At the resumption inventory the tracked
working tree was clean, no Phase 6 implementation commits existed, and all 12
LDPlayer instances were stopped. No Python, ADB, LDPlayer or task worker was running.

## Preserve completed real actions

The interrupted task was `Run Phase 1 LDPlayer acceptance`, task ID
`01a0af6f-f17a-7e00-bfa4-4aeb41210253`; its latest turn contains Phase 6 and the later
Free Reward Explorer product requirements. Do not repeat its claims to collect fixtures.

- VIP: `VIP6 mỗi ngày có thể nhận miễn phí` / `Nhận` was tapped once; reward popup
  was verified and the claim button changed to a countdown.
- Free Pack: the gift on `Ưu Đãi Mỗi Ngày` yielded 20 diamonds. The later screenshot
  shows `Đã nhận`. `Gói Mỗi Ngày` displayed paid offers, not the free gift.
- Free Recruit: `Miễn Phí 3/3` was tapped once. Result/continue was observed;
  subsequent screen shows `2/3`, progress 146 → 147, tickets unchanged at 265 and
  diamonds unchanged at 4142. A cooldown remains; the `Miễn Phí` label alone does
  not prove another attempt is currently available.
- Home was verified after recruit. These were manual evidence collection actions,
  not acceptance of a Phase 6 production implementation. SQLite contains only
  Phase 5 `idle-reward` task runs (latest ID 7).

Original screenshots and metadata remain in
`%LOCALAPPDATA%/TopHeroesAutoManager/diagnostics/vision/3-Chíp/`.
Portrait inspection copies remain in ignored `artifacts/phase6-*.png`.

## Current unfinished point — index 2 survey checkpoint

- See [PHASE6_SURVEY.md](PHASE6_SURVEY.md) for actual per-tab coverage and evidence.
  No reward, recruit, purchase or resource-consuming action was performed on index 2.
- VIP currently showed an explicit free daily reward and green Nhận; recruit showed
  `Miễn Phí 3/3`, 277 tickets and 4114 diamonds. Availability was preserved for a
  fresh production artifact. Do not assume it will remain available next session.
- Surveyed daily offers/packs, weekly packs/card, permanent/monthly cards, growth
  and prestige funds, diamond shop, vertical lists and the horizontal right boundary.
  Some gift icons lack independent free-cost evidence: **do not claim them**.
- Native capture failed twice with `SetIsBorderRequired failed: No such interface
  supported (0x80004002)`. Authorized survey used the accepted Manager/verified ADB
  pipeline, not unverified device selection. `scripts/phase6_survey.py` is a manual
  one-action evidence tool, not a production task or acceptance runner.
- A transient empty LDPlayer inventory marked all 12 persisted rows absent and
  cleared selection. The guard stopped post-navigation capture; no tap was blindly
  retried. Raw SQLite still retained Queen protection. Added empty-inventory
  rejection before metadata mutation, verified current inventory/protection, and
  restored only authorized index 2 selection. No other selection/protection changed.
- Added screenshot-bound optional `observed_target` input dispatch: exact account,
  serial and boot must match at dispatch; live selection revocation is respected.
- Added durable claim-intent storage and a journalled explorer adapter. RESERVED
  commits before dispatch and blocks retries across restarts, rename and cycle
  changes until a verified receipt exists. A real adapter must prove a cycle;
  screenshot hashes, boot IDs and guessed midnight resets are not cycle evidence.
- Targeted results: inventory/foundation 90 passed; reward/journal/vision 41 passed;
  observed-target/lifecycle 44 passed. These are mock regressions, not production
  acceptance. Do not repeat the full suite locally.
- Push authorization is resolved. Foundation commit `9db7a1c` full Windows CI passed:
  [35525124909](https://github.com/thangnd1993/thangnd-top-heroes/actions/runs/35525124909).
- Next: complete production visual adapters and task/CLI/UI integration, prove free
  shop gift semantics or report UNKNOWN without tapping, finish bounded coverage,
  targeted tests, new passing CI artifact and real acceptance. **Phase 6 is NOT
  COMPLETE. Do not merge main or start Phase 7.**

## Historical unfinished point — former target (not authorization)

The last original capture is `20260920-125155-889857Z-phase6-shop-explore-tab1-scroll1`;
portrait copy `artifacts/phase6-shop-tab1-scroll1-portrait.png`. It shows the shop's
`Ưu Đãi Mỗi Ngày` tab with the already claimed gift and paid offers after a vertical
scroll. Remaining shop tabs, nested pages and horizontal/vertical content have not
been exhaustively surveyed. Do not represent this first viewport as a complete scan.

## Remaining implementation

- Reuse accepted target guards, screenshot/vision pipeline, safe input, recovery,
  task reporting, persistence, cancellation and lifecycle ownership.
- Add `vip_reward`, `free_pack`, `free_recruit`, individual CLI/UI and sequence with
  verified Home between tasks; no Phase 7 or unrelated gameplay.
- Central free-only guard: reject money, diamonds, premium currency, tickets,
  rare items, speedups, any resource cost, and ambiguous identity. Red dots are
  discovery signals only. Require fresh precondition and postcondition; never retry
  a dispatched claim with an uncertain result.
- Reusable Free Reward Explorer: known safe menus, nested tabs, vertical/horizontal
  traversal, fingerprints/visited states, bounded depth/steps/scrolls, diagnostic
  UNKNOWN for unsupported UI. Prioritize genuinely free diamond rewards.
- Detect targets independently on each account's current screenshot. Building
  positions from 3-Chíp are not authoritative on another account. Cached positions
  may only be hints followed by current visual verification.
- Targeted tests, then commit/push and GitHub Actions full pytest/lint/portable/smoke.
  Use fresh passing artifacts for production acceptance. Preserve all earlier tests.
- Update README, PROGRESS and WINDOWS_TEST with honest per-task acceptance status.

The historical target `4 / 3-Chíp` is now revoked. Only the current authorization
section above applies. Queen remains Protected and must never receive mutation.

## Resumed work

- Added `automation/free_rewards.py`: free-only guard and adapter-driven bounded
  explorer; fresh account/transport evidence, independent free/availability anchors,
  diamond priority, no retry after claim dispatch, separate claim/recovery outcomes,
  nested navigation postconditions, scroll bounds and repeated-content detection.
- Added `vision/exploration.py`: current-frame unique target matching across account
  layouts, explicit content fingerprints, and red-dot candidates without claim authority.
- These are foundation components only. They are deliberately not wired to live CLI/UI
  tasks: real screen adapters, durable claim-attempt persistence, safe scroll/return-home
  adapters and the remaining shop survey are still required before production use.
- Accepted Phase 4 recovery resumed only index 4, successfully reaching GAME_HOME.
  Report: `diagnostics/recovery/3-Chíp/20260920-155436-608211Z/report.json` in AppData.
  This run owns that start (`started_by_run=true`). No Phase 6 claim was repeated.
- Native window inventory found `3-Chíp`, but inspection returned
  `Computer Use app approval timed out`. Shop navigation has not proceeded past this
  access boundary. No alternate input mechanism was used to bypass it.
- Sandboxed `ldconsole list2` incorrectly reported all instances stopped while the
  actual window existed. An elevated read-only `list2` confirmed index 4 running and
  all other instances stopped. Use the real process view for lifecycle decisions.
- Ownership cleanup completed through the accepted Manager: only index 4 was
  stopped, then all 12 instances were verified stopped. Queen remained untouched.
- Targeted foundation tests: **32 passed**. No completed real reward action was
  replayed and no Phase 6 production acceptance is claimed.
- Foundation committed locally as `63dfc86`. Ruff and `git diff --check` passed.
- Added the Phase 6 branch to the existing Windows CI push filter. Publishing was
  rejected by automatic approval review: destination considered unverified and
  source-upload authorization insufficient. No push occurred and no Phase 6 CI or
  portable result is claimed. The recovered original request specifies commit →
  push → CI; repository origin is `https://github.com/thangnd1993/thangnd-top-heroes.git`.
- Next live step after LDPlayer app access is available: scoped recovery if stopped,
  current screenshot verification, reopen Tiệm, resume beyond the already examined
  daily-offer viewport. Never repeat the preserved VIP/gift/recruit claims blindly.
