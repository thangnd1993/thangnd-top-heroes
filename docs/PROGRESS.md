# Tiến độ

## 2026-09-23 recovery loading recognition (offline; no gameplay)

The saved `3 / Queen con` startup frame at 14% is now recognized as
`GAME_LOADING` by a unique live-frame Stranger Things title anchor at the
existing 0.96 threshold. It no longer depends on the changing loading caption
or percentage. The Google Play service notice remains non-actionable; recovery
waits without tapping. The later Stranger Things event frame remains UNKNOWN,
and weak/conflicting evidence stays fail-closed. Focused recovery tests and
Ruff pass. No LDPlayer was launched and the Idle detector was not changed.
After CI, only the already authorized screenshot/recovery acceptance on
`3 / Queen con` may be performed; no claim or fleet run is authorized.

## 2026-09-23 Idle result-semantics repair (offline; no claim replay)

The accepted Idle claim on `2 / 5-Emmmmm` remains verified and is never to be
repeated. Existing evidence records one dispatch, fresh
`IDLE_REWARD_CLAIMED` at confidence `0.994715`, and a `VERIFIED` journal. The
offline runner now reports claim, postcondition, journal, navigation recovery,
and owned-instance cleanup independently. A verified receipt remains success
if later Home recovery or inventory reporting fails. Recovery is navigation
only and cannot redispatch the claim. Empty inventory discovery is bounded to
three reads; persistent emptiness and ambiguous exact-target identity fail
closed. No LDPlayer or real gameplay action was run for this repair.

The project workflow now uses one Codex agent with targeted tests, diff
self-review, authorized commit/push, GitHub Actions validation, and real
Windows acceptance only when explicitly authorized. Custom Developer/Reviewer
agent definitions and routing were removed. Phase 7 was not started.

## 2026-09-23 post-fleet repair (not another fleet run)

See [repair checkpoint](FLEET_REPAIR_20260923.md): three proven undispatched
outer trial locks released with backup/audit; durable pre-input uncertainty;
qualified one-time promo recovery; stable unique portal core at unchanged 0.9;
bounded recovery diagnostics. Index-2-only observation, zero claims, owned
cleanup and unchanged unrelated inventory. Guild-fire popup on historical 4/5
remains unsupported. Await explicit authorization before another fleet trial.
Phase 6 stays PARTIAL; no Phase 7.

## Phase 6 — VIP / Free Pack / Free Recruit — PARTIAL

- 2026-09-23 correction: run-16's `LDPlayer-2` identity mismatch is historical.
  Index 2 again resolves exactly as `5-Emmmmm`, but its explicit indexed ADB
  transport `emulator-5558` was unavailable at the latest check. Real gameplay
  remains frozen; do not substitute another transport or mutate persistent
  name/config. The three annotated fixed flows now have a versioned reference
  manifest, bounded injectable runtime and SQLite RESERVED/VERIFIED adapter;
  packaged claims remain
  `NOT_IMPLEMENTED` pending clean anchors and independent free/postcondition
  proof. See the task ledger for per-flow state. No Phase 7.

- 2026-09-22 audit: [PHASE6_TASK_CHECKPOINT.md](PHASE6_TASK_CHECKPOINT.md)
  records VIP, Free Pack, Free Recruit, Free Reward Explorer and Shop Traversal
  independently. Existing index-2 VIP screenshots make another discovery
  survey unnecessary; `41b747d` survey code passed CI `35678890820` but its
  first live launch (task run 16) stopped on index-2 name mismatch before any
  screenshot/game action. At that historical checkpoint index 2 appeared as
  `LDPlayer-2` with an incomplete config; the current blocker is unavailable
  explicit index-2 ADB, not the restored name. Do not repeat accepted shop navigation, historical claims,
  or start Phase 7.
- 2026-09-22: offline run-16 lifecycle/reporting fix `1c20bdf` records
  uncertain indexed launch separately from confirmed ownership and prevents
  identity errors from triggering index-only cleanup. 199 focused tests,
  independent safety review and full Windows CI `35706476751` passed. No
  device test or claim was performed; index-2 identity/config remains a
  separate blocker for real acceptance.

- 2026-09-22: task run 15 on `2 / 5-Emmmmm` narrowly accepted the packaged
  daily-pack observation route: Home → daily → help → daily → daily-pack →
  daily → Home. Fresh artifact `10673317114` from green Windows CI
  `35676774563` was used. Report result remains `PARTIAL` because dynamic
  Tiệm coverage is unknown; zero claim/journal, owned cleanup and unchanged
  before/after LDPlayer inventory passed. VIP/Free Pack/Recruit production
  acceptance and full submenu/scroll traversal remain unfinished.

- 2026-09-22: `shop-survey` observation-only task run 13 passed its narrow
  real route on `2 / 5-Emmmmm` with result `PARTIAL`: one known-promo Back,
  fresh Home, four guarded taps Home → daily → help → daily → Home. Commit
  `32142ea` passed full Windows CI run `35671625455`; fresh artifact
  `10671690862` was used. Explicit ADB/boot stayed fixed, no claim or
  journal row, owned cleanup and instance isolation passed. Other Tiệm tabs,
  nested/scroll coverage and VIP/Free Pack/Recruit claims remain unfinished;
  do not mark Phase 6 complete or start Phase 7.

- 2026-09-22: hạ tầng khảo sát Tiệm một phần `ca14c96` qua CI Windows đầy đủ
  (run `35662061780`, artifact `10666928804`), nhưng nghiệm thu thật task
  run 10 **dừng an toàn**: popup Stranger Things xuất hiện muộn sau đúng một
  tap Home→Tiệm; trang đích bị từ chối, không claim/mua/vé/journal, owned
  index 2 đã dừng, Queen/index 4 không đổi. Cần xử lý interstitial có bằng
  chứng sau hành động và artifact mới trước khi chạy lại. Chưa nghiệm thu
  traversal tab/cuộn rộng hoặc reward tasks; xem `PHASE6_RESUME.md`.
- 2026-09-22: artifact CI `10665326562` của commit `476e1a8` qua full
  lint/test/build/smoke (run `35656740331`). Nghiệm thu task run 9 trên đúng
  `2 / 5-Emmmmm` thành công **chỉ ở tuyến điều hướng**: popup sự kiện được
  nhận diện từ ảnh mới, đúng serial/boot, một Back rồi xác minh Home; bốn
  tap có bằng chứng đi Tiệm daily → thông tin → đóng → Home. Không claim,
  mua, dùng vé hoặc tạo journal. Owned cleanup thành công, Queen và index 4
  không đổi. Hướng dẫn Tiệm nói rõ mua gói/vé; gift red dot vẫn chưa chứng
  minh miễn phí nên không chạm. VIP/Recruit vẫn thiếu receipt độc lập và
  nested traversal production chưa hoàn tất; Phase 6 tiếp tục PARTIAL.
- Trước nghiệm thu task run 9, đã thêm tuyến `shop-navigation-survey` tách khỏi Free Pack:
  chỉ Home → Tiệm daily → popup thông tin → đóng → Home, tối đa bốn tap có
  bằng chứng ảnh mới; không claim/journal/mua/vé/scroll. UI/CLI và report có
  guard đúng index 2, ownership cleanup tường minh. 105 test liên quan và
  Ruff pass ở checkpoint đó; CI/artifact và nghiệm thu điều hướng đã hoàn tất
  ở task run 9 nêu trên. Đây không là
  nghiệm thu Free Pack hay toàn bộ Tiệm; Phase 6 vẫn PARTIAL.
- Các commit `53c2462`, `6a4f9b8`, `4a08d22`, `ddbd959` đã qua CI Windows
  đầy đủ; artifact của `4a08d22` đã tải và kiểm SHA-256. Không có claim thật
  nào được lặp trên index 2; VIP/Recruit vẫn thiếu receipt, gift daily chưa
  chứng minh zero-cost.
- Tiếp tục 2026-09-22: UI đã có nút VIP, Free Pack, Recruit, chuỗi Phase 6 và
  Hủy có guard đúng index 2; trạng thái cuối không mất sau refresh.
  Outcome `CLAIMED` mới xác minh journal; cooldown chỉ ghi nhận và giữ
  RESERVED. Bộ duyệt Tiệm mới giới hạn route/scroll và trả PARTIAL khi
  thiếu bằng chứng tab. Mặc định chưa claim thật khi thiếu receipt/zero-cost.
- Khảo sát mới trên index 2: VIP có chữ miễn phí rõ, Tiệm daily help nói tới
  mua gói/vé kích hoạt; quà vẫn mơ hồ. Không claim/recruit/mua; hai nhận diện
  Tavern không đạt ngưỡng nên không tap. Owned index 2 đã dừng.
- Parent chạy 109 test tập trung kể cả UI offscreen, Ruff sạch; CI mới và
  nghiệm thu production của phần code này vẫn chờ. Phase 7 chưa bắt đầu.
- Resumed branch: `codex/phase6-vip-pack-recruit`, based on accepted `33cb313`.
- Previous session already observed one free VIP claim, the daily shop gift (20
  diamonds), and one free recruit. Those claims were not repeated on resume.
- Added and tested the shared free-only guard, bounded explorer, current-frame
  unique target search, content fingerprints and red-dot discovery primitives.
- Đã thêm adapter ảnh theo frame hiện tại, điều hướng Home → VIP/Tavern có kiểm chứng,
  CLI Phase 6, journal/report cho task và chuỗi tác vụ. Các lệnh hiện cố ý trả
  `NOT_IMPLEMENTED`/`SAFETY_BLOCKED` trước claim khi thiếu hậu điều kiện;
  Free Pack chưa có chứng cứ zero-cost nên không chạm quà có red dot.
- Khảo sát bổ sung trên đúng `2 / 5-Emmmmm` xác nhận mép trái tab Tiệm,
  mép trên Quỹ Xây Thành và mép dưới Tiệm Kim Cương. Chỉ điều hướng/scroll,
  không nhận thưởng, chiêu mộ hay mua; owned start đã dừng đúng index 2.
  `0 / Queen` và `4 / 3-Chíp` không bị tác động.
- Hồi quy tập trung mới nhất do parent chạy: 93 passed; Ruff sạch. Checkpoint
  `b8be92a` có Windows CI `35629610052` xanh: full lint/pytest, PyInstaller,
  smoke và artifact mới `10654057686`. UI, traversal production và nghiệm
  thu task thật vẫn thiếu; CI xanh không đồng nghĩa Phase 6 hoàn thành.
- Detailed completed/remaining work and original evidence: [PHASE6_RESUME.md](PHASE6_RESUME.md).
- Phase 5 acceptance below is historical and remains unchanged.

## Phase 5 — Idle Reward — COMPLETE

- Trạng thái: **COMPLETE**. Real Windows acceptance pass ngày 2026-09-20 trên duy nhất
  `4 / 3-Chíp`, explicit ADB `emulator-5562`; `0 / Queen` vẫn Protected/unselected và không nhận
  mutation. Không dùng `5 / 4-Em Pé` và không bắt đầu Phase 6.
- Final portable: CI run `35469961859`, commit `43e3458`, artifact `10592886746`, SHA-256
  `67f648a2d0b41f466cde9049ee6177c29d9092396b755c4b347a1590cb695936`; lint, full pytest,
  PyInstaller build, executable smoke và artifact upload đều pass.
- Real claim evidence (task Run ID `5`, fresh CI artifact của `ee83c23`): verified `GAME_HOME` →
  Adventure entry → `Thưởng Treo Máy`; Claim được dispatch đúng một lần, popup `Chúc Mừng Nhận`
  và `Nhấn để tiếp tục` đều được verify. Không có claim retry.
- Lỗi cleanup thực tế sau Claim đã được sửa: popup có thể trở lại panel thay vì Home. Detector mới
  nhận riêng thông điệp không có thưởng và gray start của accumulation bar; cleanup chỉ dùng Back
  sau evidence mới, qua Adventure rồi verify `GAME_HOME`.
- Final no-double-claim/cleanup evidence (task Run ID `7`, final artifact): `NOT_AVAILABLE`,
  `claim_dispatched=false`, `cleanup_succeeded=true`, final state `GAME_HOME`, ADB
  `emulator-5562`, `isolation_changed_indices=[]`. Run history và report path đọc lại được từ SQLite
  sau process exit.
- Claimability gate là chest Adventure có glow xanh + red dot. Nút `Nhận` một mình không đủ vì vẫn
  xuất hiện sau Claim; hourglass `6/6` không có action anchor vì có thể dùng stamina. Partial bar có cả
  xanh và xám, nên gray-start detector bị giới hạn vùng và loại trừ với minimum green-fill detector.
- Đã sửa các integration bug thật: alternate open chest frame, portal flame animation, bar-state
  conflict, task-specific recovery từ panel/Adventure và hai biến thể post-claim. Threshold action
  anchors vẫn `0.9`; không nới safety guard hay cho phép click UNKNOWN.
- Task engine giữ exact snapshot, bounded observation, cancellation, một action/một screenshot mới,
  no-double-claim, `ACTION_RESULT_UNCERTAIN`, verified cleanup và machine-readable report. CLI:
  `TopHeroesAutoManager.exe task idle-reward --index 4 --name "3-Chíp"`; UI có **Thưởng treo máy** /
  **Chạy thử tác vụ**; SQLite persist `task_runs`.
- Portrait mapping đã được verify bằng action thật; stable portal core `(465,470)`, entry `(87,957)`,
  Claim `(362,915)`, popup continue `(360,1015)` theo device coordinates.
- Local targeted final: 66 Phase 5/vision/recovery tests pass; Ruff và diff check pass. Final state giữ
  `3-Chíp` running vì `started_by_run=false`; Queen stopped/Protected, các instance khác giữ nguyên
  baseline, kể cả index 1 và 7 đang chạy từ trước.
- Branch: `codex/phase5-idle-reward`. Phase 6 chưa bắt đầu.

## Phase 4 — Popup Handling + Safe Home Recovery — COMPLETE

- Trạng thái: **COMPLETE**. Real Windows acceptance: **PASSED** ngày 2026-09-19 trên duy nhất
  `4 / 3-Chíp`; `0 / Queen` vẫn Protected, unselected và không nhận mutation.
- Fresh portable: CI run `35444434273`, commit `097e155`, artifact `10584592524`, SHA-256
  `794a460ca253c40e2dee35d16bcf99d193806871486afec2b15faba39b091b9a`.
- Recovery engine giữ snapshot exact index/name, verified explicit ADB target, một screenshot mỗi step,
  action có precondition, postcondition bằng ảnh mới, cancellation và giới hạn 30 steps/120 giây.
  Loading/launch transition giới hạn 90 giây, poll 5 giây; không click trong loading.
- Scenario A (stopped): `ANDROID_HOME → launch_game → GAME_LOADING/UNKNOWN transition → GAME_HOME`,
  `SUCCESS`, ADB `emulator-5562`, `started_by_run=true`, cleanup đúng index 4.
- Scenario B (đã ở game home): `ALREADY_HOME`, actions rỗng, confidence `0.998662`, không cleanup
  instance không do run sở hữu. Scenario C (Android Home): launch package đã verify rồi `SUCCESS`,
  GAME_HOME confidence `0.979019`, không gameplay click.
- Scenario D synthetic: `UNKNOWN` được chụp xác nhận hai lần rồi fail-closed; không input/mutation.
  Blank/cropped frames chỉ được wait trong launch/loading window đã xác nhận và vẫn chịu timeout.
- Safe input abstraction chỉ tap khi có đúng một detected anchor với bounding box đã map về device;
  UNKNOWN hoặc thiếu evidence trả `DO NOT TAP`. Popup framework đã sẵn sàng nhưng chưa đăng ký handler
  vì không có real popup xuất hiện tự nhiên: **No real popup fixture available**.
- Diagnostic: `TopHeroesAutoManager.exe recovery home --index 4 --name "3-Chíp"`; report/screenshots
  nằm dưới `%LOCALAPPDATA%\TopHeroesAutoManager\diagnostics\recovery\` và không commit vào Git.
- Targeted local: 74 recovery/vision/lifecycle tests pass; Ruff pass. CI run `35444434273` lint,
  full pytest, Windows portable build và executable smoke đều pass.
- Isolation pass: Queen và các instance ngoài index 4 giữ nguyên; không default ADB, first-device/index-0
  fallback, `quitall`, global operation, blind click hoặc gameplay/daily-task automation.
- Branch: `codex/phase4-home-recovery`. Không bắt đầu Phase 5.

## Phase 3 — Screenshot Pipeline + Screen Recognition — COMPLETE

- Trạng thái: **COMPLETE**. Real Windows acceptance: **PASSED** ngày 2026-09-19 trên duy nhất
  `4 / 3-Chíp`; `0 / Queen` vẫn Protected, unselected và không nhận mutation.
- Fresh portable: CI run `35441526597`, commit `2fbaa46`, artifact `10583942593`, artifact SHA-256
  `62afeb1d0ca5ce6240ba1e6c35abb0e24457c9aed48b2be927675f9f90717c84`.
- Exact ADB target: `emulator-5562`; ảnh thật 1280x720, normalized 1280x720, scale 1.0/1.0.
- `ANDROID_HOME`: confidence `1.0`, 26.886 ms. `GAME_LOADING`: confidence `1.0`, 34.595 ms.
  `GAME_HOME`: confidence `0.998736`, 30.023 ms với required world-button và optional bottom-nav.
- `UNKNOWN` fail-closed, negative matching, threshold boundary và state conflict được regression-test
  bằng fixture synthetic; không tạo điều kiện game nguy hiểm chỉ để lấy ảnh.
- Template crop thật được version trong `assets/templates/{android,loading,home}`; full screenshots và
  debug overlays ở `%LOCALAPPDATA%\TopHeroesAutoManager\diagnostics\vision`, không commit vào Git.
- Screenshot service validate PNG/dimensions/nonblank, normalize orientation/resolution, giữ original/
  normalized coordinates và chỉ dispatch tới verified explicit target. Một detection cycle dùng một ảnh.
- Detector tổng hợp required/optional anchors theo weight; thiếu required hoặc conflict trong margin 0.03
  trả `UNKNOWN`. Detection JSON giữ Unicode UTF-8 và overlay là tùy chọn.
- Cleanup/isolation pass: stop đúng package và index 4; cuối run cả 12 instance stopped như baseline.
  Không default ADB, first-device/index-0 fallback, global LDPlayer op hoặc gameplay clicks.
- Local: Ruff pass; 16 vision tests pass; 158 non-GUI tests pass. CI Windows lint, full pytest,
  PyInstaller portable và executable smoke: pass.
- Branch: `codex/phase3-screen-recognition`. Không merge main và không bắt đầu Phase 4.

## Phase 2 — Run Selected Queue + Concurrency — COMPLETE

- Trạng thái: **COMPLETE**. Real Windows concurrency acceptance: **PASSED** ngày 2026-09-19,
  dùng portable artifact đã được CI run `35430067613` xác minh (commit `e1db0ad`).
- Remediation môi trường duy nhất: `5 / 4-Em Pé` có `basicSettings.adbDebug=0`, trong khi
  `4 / 3-Chíp` là `1`. Đã sao lưu `leidian5.config.phase2-adb-backup` và chỉ đổi đúng field
  `basicSettings.adbDebug` thành `1`; sau đó single-account Run ID `3` PASS.
- Multi-instance Run ID `4`: immutable snapshot `[[4, "3-Chíp"], [5, "4-Em Pé"]]`,
  max concurrency `2`. Cả hai worker active đồng thời với target độc lập: `emulator-5562` và
  `emulator-5564`; harmless health check pass, retry=0, `started_by_run=true`, cleanup dừng đúng
  hai target.
- Persistence pass sau process exit: Run `4` = SUCCESS, completed=2, failed=0, cancelled=0;
  hai RunAccount đều SUCCESS và persisted trong SQLite.
- Isolation pass: Queen không mutation; instance ngoài 4/5 không có lifecycle mutation. Chicken đã
  running từ trước và được giữ nguyên running. Không gameplay automation và không dùng default ADB,
  first-device fallback, index-0 fallback hoặc global LDPlayer operation.

## Phase 1 — Windows Foundation + LDPlayer Multi — COMPLETE

- Trạng thái: **COMPLETE**. Real Windows LDPlayer integration: **PASSED** ngày 2026-09-18.
- LDPlayer version: `9.5.31.0`; path: `D:\LDPlayer\LDPlayer9`.
- Protected main: `0 / Queen` (`protected=true`, `selected=false`); không có lifecycle/ADB/game mutation.
- Test clone duy nhất: `4 / 3-Chíp`; discovery đủ 12 instance và giữ đúng tên Unicode.
- ADB mapping đã xác minh: LDPlayer-scoped serial `emulator-5562`; explicit endpoint
  `127.0.0.1:5563` có cùng Android boot ID trong phép kiểm tra recovery.
- Diagnostic thật pass: start, Android-ready (bao gồm transitional state 2), harmless shell,
  screenshot, package discovery, game launch/stop, restart, ADB re-verification, exact stop và isolation.
- App label `Thời Đại Anh Hùng` được đối chiếu bằng APK metadata; package xác định duy nhất:
  `com.greenmushroom.boomblitz.gp.vn`; launcher: `com.rivergame.gp.AppActivity`.
- Resolver giữ fail-closed: không first-device/index-0 fallback; ưu tiên serial đã đăng ký, sau đó
  indexed identity và explicit loopback connection có boot-ID verification. Shared ADB restart chỉ được
  phép khi không có device khác và không có LDPlayer instance khác chạy.
- CI branch run: [35347373605](https://github.com/thangnd1993/thangnd-top-heroes/actions/runs/35347373605) —
  lint pass, pytest pass, PyInstaller/portable build pass, executable smoke pass.
- Artifact: `TopHeroesAutoManager-Windows-x64` (`10547612861`); EXE SHA-256
  `7853e1f4ab5979b813238b811e2ac0f51205fa9600c607d6b9ea481b45a5c62f`.
- Diagnostic report: `%LOCALAPPDATA%\TopHeroesAutoManager\diagnostics\reports\phase1-windows-acceptance.json`.
- Không chuyển sang Phase 2.

## Lịch sử sửa blocker lifecycle Start/Restart

- Trạng thái lịch sử: lifecycle fix đã được CI xác minh trước vòng nghiệm thu Windows thật.
- Root cause: execute gọi resolver ADB vô điều kiện trước khi phân loại lifecycle/ADB-dependent;
  cold start bị chặn và CLI reboot không bảo đảm đã chờ stop/start rồi verify transport mới.
- Fix: lifecycle index-first, selected/protected/snapshot guard giữ nguyên. Start → wait Android →
  resolve/verify. Restart → quit đúng index → wait stopped → launch cùng index → wait Android →
  resolve/verify mới. Stop/Query không phụ thuộc ADB. UI refresh read-only sau lifecycle.
- Startup timeout 120 giây, stop timeout 60 giây; polling kiểm tra lại quyền và identity.
  Resolver failure chỉ hủy thao tác của instance đó, không global cleanup hoặc chuyển target.
- Tests mới: 29 cases trong `tests/test_lifecycle.py`; thay test cold start bị chặn đã lỗi thời.
  Phủ đủ 9 yêu cầu: cold start không có ADB, thứ tự resolve, protected/unchecked, restart đổi serial/boot,
  failure isolation, exact index, không fallback 0, không quitall; thêm wait/timeout/revocation/identity changes.
- Local: `pytest -q` **103 passed**; `ruff check .` pass. LDPlayer thật: chưa test trên macOS.
- Windows CI: **103 passed in 16.39s** (Python 3.12, Windows x64), lint pass,
  PyInstaller build pass, `.exe --smoke-test` mở GUI và thoát sạch code 0.
- [GitHub Actions — success](https://github.com/thangnd1993/thangnd-top-heroes/actions/runs/35204186113).
- [Tải portable Windows đã sửa lifecycle](https://github.com/thangnd1993/thangnd-top-heroes/actions/runs/35204186113/artifacts/10489670505).
  Đăng nhập GitHub, tải ZIP, giải nén toàn bộ và chạy `TopHeroesAutoManager.exe` cạnh `_internal/`.
- Commit code/build: `637b3534c1720d4fb744bbe91582e9110367ba37`, đã push `origin/main`.
  Commit báo cáo kết quả build được push tiếp theo, chỉ thay tài liệu.
- Output CI: `dist/TopHeroesAutoManager/TopHeroesAutoManager.exe`.
  Bản tải local tách khỏi build cũ: `dist/phase1-lifecycle/TopHeroesAutoManager/`.
- Tài liệu: README, SAFETY, WINDOWS_TEST cập nhật theo lifecycle mới.
- Next: bàn giao lại Phase 1 để người dùng kiểm thử Windows thật, không làm Phase 2.

## Lịch sử bản bàn giao trước sửa lifecycle (đã thay thế)

## Phase 1 — Windows Foundation + LDPlayer Multi

- Trạng thái: đã bàn giao code foundation + portable Windows để thử nghiệm; **chưa nghiệm thu đầy đủ Phase 1**.
  Còn kiểm tra LDPlayer thật trên máy người dùng và quyết định ngoại lệ cold start.
- Phạm vi hoàn thành: GUI PySide6 tiếng Việt, discovery, list2 typed parser, tìm kiếm/lọc,
  selected/protected SQLite, snapshot thao tác, guard execution, indexed CLI + ADB boot ID verification,
  screenshot PNG, packages/game control, logs, docs và portable build workflow.
- Kiểm thử: **75 passed** trên macOS / Python 3.12.14; `ruff check .` pass.
  Có GUI offscreen; subprocess/LDPlayer/ADB được mock. Không diễn giải mock thành kết quả thiết bị thật.
- Windows CI (Windows Server 2025 x64, Python 3.12.10): **75 passed in 12.98s**; lint pass.
- Manual verification: chưa chạy LDPlayer; máy làm việc macOS không cài giả lập. Người dùng sẽ test Windows sau.
- UI preview: `docs/phase1-ui.png` là ảnh widget của GUI, không phải ảnh Android hoặc bằng chứng test ADB.
- LDPlayer path / CLI / ADB / instances: chưa phát hiện trong môi trường macOS.
- Screenshot thật và ADB verification thật: chưa thực hiện; unit tests pass.
- Windows portable: **build thành công**, smoke test executable mở GUI và thoát sạch với code 0.
  [CI run đã xác minh](https://github.com/thangnd1993/thangnd-top-heroes/actions/runs/35202851053).
  [Tải artifact portable](https://github.com/thangnd1993/thangnd-top-heroes/actions/runs/35202851053/artifacts/10489185027).
  Output: `dist/TopHeroesAutoManager/TopHeroesAutoManager.exe` và `_internal/`.
  Portable ZIP bàn giao local: `dist/TopHeroesAutoManager-Windows-x64.zip`.
  ZIP 48.0 MiB đã kiểm tra CRC; có Python DLL, Qt DLL và Windows platform plugin đi kèm.
  EXE SHA256: `4d9aabe6e49edba57ed5e3ee735d2524964bfa0e9d04fed27e135c648e5f0415`.
  ZIP SHA256: `def37ea4c700bfc116fe9082d9c6ee12bf4845cdc4a27af9ef58dc5720fa6523`.
- Known limitations: cold start bị chặn vì chính sách cần ADB đã verify; chưa chấp thuận ngoại lệ.
  Không đoán resolution/package/serial; các biến thể CLI cần test trên LDPlayer thật.
  Không nhận biết delete/recreate cùng index+tên giữa hai refresh; xem SAFETY.md.
- Commit khởi tạo: `d755209` — đã push `origin/main`.
- Commit implementation: `dbb1953340b0e8b5e54415365d73573fd3c03b27` — đã push `origin/main`.
- Cập nhật kiểm thử: phủ toàn bộ protected actions, input abstraction, cold-start policy và
  transport đổi trước dispatch. Đóng SQLite connection rõ ràng sau mỗi transaction (quan trọng trên Windows).
- Commit bổ sung guard tests/SQLite: `38d3964485b967f03f12a5f09378bb522bf65a95`.
- Commit code/build cuối: `0191fd941d2ddac4dfe298f0ff72db08c8c1be85` — đã push `origin/main` và CI pass.
- Commit báo cáo này chỉ thay đổi docs; hash xem `git log -1 --format=%H` sau checkout bản bàn giao.
- Push status: các commit code đã có trên `origin/main`; bản ghi bàn giao cũng được commit/push riêng.
- Bước tiếp: người dùng kiểm tra [WINDOWS_TEST.md](WINDOWS_TEST.md); dừng Phase 1.
- Phase kế tiếp (chưa làm): Phase 2 — queue/concurrency/account lifecycle, chỉ khi người dùng yêu cầu.
