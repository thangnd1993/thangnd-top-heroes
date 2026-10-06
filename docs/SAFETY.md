# Permanent no-rename invariant — all phases

## Qualified World view navigation and purchase-modal closure — 2026-10-06

World return permits only the current Về Thành castle control, with four unique
HUD anchors and two consecutive fresh same-transport/boot frames. One input only,
fresh reclassification afterward; no troop recall, attack, relocation, spending,
restart or claim. An attack-confirmation popup remains fail-closed/no input.
Known VND purchase modal permits only a paired, current, unique red close after
fresh confirmation. Its content/upper gift remains unqualified/BLOCKED; closing
never proves paid-only or exhausted coverage. No paid control/gift is authorized.
All old VERIFIED/POSSIBLE locks, external lifecycle ownership and exact identity
checks remain in force; no global timeout or coordinate fallback changes.

## Qualified Treo Thuong recovery — 2026-09-30

User explicitly authorized navigation out of the known bounty board. Require
unique current title, task label and Back control at>=.98, with qualified layout.
Tap only the current Back bbox, consume the frame and capture afresh. Maximum two
attempts while that same qualified state persists; never retry uncertain transport.
A state change ends this Back sequence. Continue normal qualified Home/overlay
recovery; unrelated UNKNOWN still receives no input. No bounty claim is authorized.
Historical Sep30 scope was attach-only. On Oct03 the user explicitly authorized
starting stopped index9 once and owned stop after continuation. Preserve unrelated
running instances (currently Protected Chicken). Continue only Guild/Mail via
explicit resume-flow scope; no historical Phase6 pending flows.

## Phase 7 explicit action scope — 2026-09-27

Guild and Mail are now authorized under the same instance-first ownership.
The ONLY resource-spending exception is the user-approved GREEN wood Cống Hiến
control on the uniquely like-marked technology. Require the current wood icon,
green control, independent remaining count and disjoint orange diamond control.
One input followed by a proven count decrement; ambiguous results stay POSSIBLE.
No diamond donations, purchases, other resources, Trial Hall or mail deletion.
Relics reset at 09:00 Vietnam as explicitly confirmed by the user.

Confirmed again on 2026-09-28: WOOD ONLY. Stone, food, diamonds, tickets,
premium/rare resources and unqualified icons are forbidden even on a green button.
Reacquire the enabled green control and its unique wood icon from every current
frame. Require a positive independent counter and disjoint paid diamond control.
After one input, independently verify exactly one count decrement before continuing.
A changed/unknown cost returns RESOURCE_NOT_AUTHORIZED for the remaining portion;
never send another input. This safe exclusion does not stop independent Guild/Mail
work or erase an already verified wood donation. UNKNOWN page/control/counter still
fails closed. Previous VERIFIED journals 122-129 are immutable.


## Permanent Home-overlay and continuous Shop rules — 2026-09-25

User authorized one agent, offline repair then fresh-CI random development and
all-current-non-Protected sequential Shop acceptance. No VIP/BXH/Idle or Phase7.
A known overlay covering Home is dismissed with the approved normalized game
bottom-left action, followed by a fresh classification. Bounded retries only;
actual unrelated UNKNOWN and true loading receive no blind Back. Generic Home
coverage uses paired opposite-corner dimmed Home HUD, plus a sharp foreground;
no new seasonal artwork templates. True promotional splash loading is reported
as LOADING_TIMEOUT, not a Home popup waiting forever as PROMO_BLOCKING.

Shop is one continuous account session: enter once, process all four allowed
tabs from the current screen, dismiss receipts back into Shop, then exit once.
Keep traversal state, current tab/viewport/fingerprints, max12 total swipes and
max4 per search; reacquire each tab after scrolling. Never click forbidden tabs.
Blocked independent rewards do not reset traversal. Unexpected exit fails closed
with an explicit re-entry reason; no silent reopening. Record entry/swipe/route
metrics and reward journals before owned cleanup and selection restoration.

Prior fleet claims46,48,49,50,51,52,53,54,55,56 are VERIFIED. Journal41 and legacy
upper-entry47 remain RESERVED/POSSIBLE. Never replay them. Prior final audit is
artifacts/shop-resumed-final-audit.json; all24 unrelated journals unchanged.
Current random target must come from LIVE non-Protected candidates, including
accounts already tested when only navigation is possible. No hardcoded account.


LDPlayer instance names are user-owned, DISPLAY-ONLY and READ-ONLY. Automation
has no rename/config replacement/rollback surface. Names never participate in
technical identity, opt-in, Protection, journal, runtime ownership or resume.
Unicode labels are preserved exactly for display, with no normalization.

Bind installation namespace + live Multi index + non-name backing-file identity.
Read-only evidence uses data.vmdk resolved path, filesystem volume/file ID and
creation timestamp, preserving the project's existing fingerprint. Actual
LDPlayer Machine UUIDs encode the index and cannot independently prove against
index reuse. Never write an identifier into LDPlayer configuration.

Selection and Protection survive user renames. A durable identity mismatch is
IDENTITY_CHANGED and remains blocked, even if an old disk/name later reappears;
never transfer flags, authorization or journal ownership to a replacement.
App-side identity sidecars preserve original historical journal rows/evidence.
Rows without sufficient durable evidence are AMBIGUOUS and stay locked, never
implicitly verified, released or retried. Current snapshots pin stable IDs before
mutation. Name-only historical snapshots cannot authorize execution. Exact
indexed serial + boot and process continuity are separate session proof.

Every run audits name-write attempts, starting/ending labels and stable ID/index.
A changed label preserves technical ownership but its cause remains
NAME_CHANGE_CAUSE_UNPROVEN without independent process/file evidence. An internal
zero-write counter cannot identify the writer. Never restore its old label. No default/first-device/index-0 ADB fallback.

Freeze the per-instance execution plan before lifecycle mutation. Missing discovery
or omitted work remains BLOCKED/ABORTED, never COMPLETE or NOT_AVAILABLE. Record
scan, candidate/nested traversal, reward outcomes and genuine blockers. Failure
or incomplete coverage does not prohibit safe cleanup of a run-owned instance.
Before cleanup, verify live Protection/selection, durable identity, process and
boot ownership. Never stop an external, replaced or uncertain owner. Cleanup
cannot turn an incomplete task into success, unlock a claim or restart a session.
Navigation-only recovery continues independent candidates only with fresh safe
evidence; UNKNOWN itself never authorizes input.

LDPlayer transport accepts only list2/launch/quit/indexed adb. The obsolete
whole-config ADB remediation writer is disabled, including backup restoration:
its old rollback could overwrite concurrent user-owned metadata. No automated
rename path or generic config replacement is available. Manual LDPlayer settings
remain user-owned. This rule does not authorize real emulator actions in tests.

# Thiết kế an toàn Phase 1

## Luồng thực thi

Lifecycle và ADB-dependent operations là hai nhóm riêng, không có ADB prerequisite cho launch.

Start: UI → Manager.execute → refresh list2 → snapshot một instance → kiểm tra quyền/index →
`launch --index N` nếu đang tắt → poll list2 chờ Android → resolve/verify ADB → trả kết quả.
Nếu đang chạy/đang khởi động, chờ Android của chính instance đó, không gửi launch trùng lặp.

Restart: kiểm tra quyền/index → `quit --index N` → poll tới trạng thái đã dừng → kiểm tra lại quyền/index →
`launch --index N` → poll tới Android sẵn sàng → resolve/verify ADB mới. Không dùng CLI reboot,
không cache Target/serial từ trước restart. Stop cũng chỉ cần index và guard, không cần ADB.

Query trạng thái (`refresh`/`query(index)`) chỉ đọc list2, có thể đọc instance protected hoặc unchecked,
không gửi lệnh ADB hay lifecycle mutation. Index chỉ định phải hợp lệ và tồn tại duy nhất.

ADB-dependent: UI → Manager.execute → refresh list2 → snapshot một instance → kiểm tra quyền/index →
CLI indexed ADB get-serialno → CLI indexed Android boot ID → adb devices → adb -s SERIAL đọc boot ID →
đối chiếu boot ID lần nữa → kiểm tra quyền → gửi đúng một lệnh có target rõ ràng → xóa snapshot.
Screenshot, input, packages và game control không tự launch instance đang tắt.

Chỉ các probe nhận dạng read-only được phép thực hiện trong quá trình xác minh trước khi có
ADB đã xác minh. Probe CLI có index rõ ràng và chỉ chạy sau whitelist/queue guard;
probe adb chỉ dùng serial chính CLI trả về. Không quét các thiết bị khác để tìm boot ID.
`adb devices` và `list2` chỉ liệt kê. Không chụp screenshot để dò target.

Mọi lệnh tác động thiết bị, bao gồm screenshot, đều đi qua Manager. Các phương thức có `_`
trong transport là chi tiết nội bộ, UI không gọi trực tiếp. Python không phải sandbox chống plugin
độc hại; Phase 1 không hỗ trợ plugin/script tùy ý. `ADB.connect` chỉ hỗ trợ endpoint loopback rõ ràng;
UI dùng resolver CLI của LDPlayer, không tự tính port hoặc fallback connect ngầm.

## Guard theo loại thao tác

1. Index tồn tại duy nhất trong list2 hiện tại.
2. Cặp index/tên trong snapshot của thao tác đang thực thi.
3. SQLite vẫn selected.
4. SQLite không protected.
5. Index + stable ID trùng khớp, cùng namespace; tên chỉ để hiển thị.
6. **Riêng thao tác phụ thuộc ADB:** explicit serial online, boot ID trùng CLI index, không thay đổi khi verify lại.

Lifecycle mutation áp dụng điều kiện 1–5; ADB-dependent áp dụng cả 1–6. UI không có đường bypass
selected/protected cho Start/Stop/Restart. Query read-only không phải automation mutation.

Sai bất kỳ điều kiện nào: hủy instance và log lỗi, không thử index/serial khác.
Mỗi thao tác xác minh mới; không cache quyền ADB qua reboot. Timeout process là 20 giây mỗi lệnh.
Nếu lệnh điều khiển timeout, kết quả có thể chưa rõ: không retry tự động; refresh để kiểm tra.

## Chờ lifecycle và lỗi khởi động

Poll list2 mỗi giây, kiểm tra snapshot và quyền hiện hành trong mỗi lần poll.
Deadline monotonic: 120 giây chờ Android, 60 giây chờ dừng; process đang chạy có timeout riêng 20 giây.
Nếu bị thu hồi selection/protection, đổi tên hoặc biến mất thì hủy ngay tại lần kiểm tra tiếp theo.
Không start sau stop timeout. Không resolve ADB trước Android-ready. Không gameplay operation sau
resolver failure. Snapshot được giải phóng trong finally; không queue continuation sang instance khác.
Không rollback bằng quit/quitall khi ADB lỗi: instance vừa khởi động có thể vẫn đang chạy; UI refresh
read-only để người dùng thấy trạng thái. Chỉ retry khi người dùng yêu cầu một thao tác mới.

## Trạng thái thay đổi

Snapshot bất biến: thay đổi checkbox không tự thêm thành viên. Thu hồi selection/protection được
kiểm tra lại trước dispatch. Trong một process, UI khóa các điều khiển khi worker đang chạy và Manager
dùng RLock. SQLite constraint không cho selected và protected đồng thời.

Đổi tên hoặc reappearance sau refresh hủy selection; protection vẫn giữ. Không phân biệt được trường hợp
xóa rồi tạo lại một instance với cùng index và tên giữa hai lần đọc vì list2 không cung cấp UUID bền vững.
Không xóa/tạo/đổi tên instance trong LDPlayer Multi khi thao tác đang chạy. CLI bên ngoài và OS có thể
thay đổi target ngay sau lần verify; không thể khóa giao dịch nguyên tử xuyên LDPlayer/ADB bằng list2.
Phiên bản LDPlayer không hỗ trợ `adb --index N --command get-serialno` hoặc không cho đọc boot ID
sẽ bị chặn. Cần dữ liệu thực tế trước khi bổ sung adapter cho biến thể đó; không suy đoán.

## Không thuộc Phase 1

Không task gameplay, không scheduler, không tự tắt sau tác vụ, không chạy đồng thời nhiều giả lập.
Các guard tiêu kim cương/vật phẩm sẽ được thiết kế cùng state recognition trong phase tương lai.

## Permanent instance-first automation

The outer loop is the instance snapshot. Start/attach once, execute the frozen
plan from the extensible enabled/supported flow registry, then cleanup once.
Finish every flow's authorized sub-rewards in one feature visit before leaving.
No feature-wide fleet passes or lifecycle restart between features/rewards.
Future features register with the same pipeline; the scheduler has no phase list.
Record disabled, not-applicable and blocked flows explicitly. A blocked reward
locks only itself; continue independent work only with fresh safe evidence.
Preserve live Protection, exact identity, original selection and external running
ownership. A stopped/replaced instance during a session fails closed, never restarts.
