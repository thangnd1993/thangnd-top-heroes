# BXH and Tiệm fixed reward acceptance

Current Shop scope: daily offer, custom weekly, permanent privilege and
monthly privilege. Each has a distinct reward ID. `shop-acceptance` runs only
these four routes; GUI Tiệm uses the same traversal. Historical BXH logic is
preserved but is not authorized to rerun in this task. No VIP/Idle/Phase 7.

A tab-strip swipe is navigation only. Up to four swipes use current Shop/Back
geometry, entirely to the right of Back, with fresh screenshots and repeated
viewport detection. Search direction follows visible allowed tabs. An offscreen
or clipped tab is never unavailable: exhausted search reports TAB_NOT_FOUND.
A new tab is tapped only from a fresh bbox, then its distinct content title and
selected tile must be verified. The previous weekly gift cannot satisfy either
privilege route. Clean survey crops provide exact upper-gift/attention identities;
no highlighted paid tile, VND button or purchase entitlement is an action target.
Positive received evidence must match on the correct page; missing attention
alone stays UNKNOWN. Unknown dialogs and unsupported ad transitions block input.

An unresolved POSSIBLE action remains locked even across daily reset. In
particular journal 41 must not be retried. That lock does not suppress independent
privilege rewards; they proceed only if navigation state remains known.

## Evidence and runtime

Clean 2026-09-23 evidence supplies avatar frame edges (not the account avatar),
profile title/BXH tab, BXH title/chest/attention, shop title/daily title/gift,
back and allowed tab icons. The first Soup acceptance supplies the clean weekly
title and both positive “Đã nhận” variants. The Home frame matcher masks out all
portrait, level and badge pixels. All new assets are
UI-only crops; full profile screenshots, UID, guild and chat are not uploaded.
`tools/qualify_fixed_reward_assets.py` records extraction provenance; it never
runs during gameplay and its crop coordinates are not action coordinates.

The runtime requires paired screen anchors, a unique current gift core and a
badge associated geometrically with that core. Threshold .96 is unchanged;
BXH inactive classification additionally needs a .985 intact core and clear badge
area. Shop inactive classification needs a .98 positive open-gift/“Đã nhận”
anchor on its exact daily/weekly page. Missing shop attention alone is UNKNOWN.
Weak, duplicate, occluded or conflicting observations stay UNKNOWN.
Index-11 evidence additionally qualifies the unobstructed, chest-free BXH header
slot (.98), with both page anchors and no conflicting chest/attention. An absent
template on a blank or occluded frame alone does not prove unavailability.
At most two observation-only extra captures accommodate rocking gift artwork.
Navigation edges are explicitly enumerated; a bottom-tab swipe never authorizes
a tap on Gói Mỗi Ngày, Gói Mỗi Tuần or any other paid/unlisted section.

All target bboxes come from current frames through ScreenshotService's device
mapping. The whole lower product/ranking region is forbidden. Save geometry
before dispatch. Popup dismissal reuses the existing qualified paired-anchor
classifier and normalized bottom-left helper; UNKNOWN is never dismissed.

Reserve -> durable POSSIBLE -> one tap -> immediate capture -> qualified popup
dismissal -> fresh underlying same-page NOT_AVAILABLE -> VERIFIED. Any uncertain
dispatch stays reserved; navigation/cleanup cannot downgrade or reopen it.

## Identity, selection and lifecycle

The exact snapshot index/name is bound to verified explicit ADB and boot identity.
Additionally, a read-only backing-disk file identity/creation timestamp detects
recreated or replaced instances; LDPlayer's index-derived UUID alone is not used.
Persistent identity does not use the display name. A continuity mismatch blocks
action and cleanup. Protected is checked before each input, capture and cleanup.
Selection restoration never overrides newly added protection. Externally running
targets are left running, and Protected accounts receive no action.

`bxh-shop-acceptance --random-test` uses `secrets.choice` over recorded live
eligible candidates. `--confirm-non-protected` creates a new immutable fleet
snapshot and runs every member sequentially. Use only a fresh passing CI artifact.
Later random development checks exclude accounts already recorded as random
tests in this flow, so a failed test does not establish a preferred account.
Normal GUI BXH/Tiệm buttons act only on their explicitly selected target;
they do not temporarily select or expand to other accounts. Run Selected is unchanged.

## Reward periods and remaining qualification

The daily-offer screenshot `06-shop-entry.png`, written 2026-09-23 01:05:26 UTC,
shows 00:54:33 to reset, i.e. 01:59:59 UTC within capture rounding. Its qualified
daily policy is 02:00 UTC. Old daily-offer rows remain audit records and cannot
lock a subsequent observed daily period forever.

BXH/custom-weekly gift reset semantics have not yet been proven by saved evidence.
Their first observed opportunity can be attempted once; subsequent attempts stay
locked until the actual reset policy is qualified. The custom card's multi-day
offer timer is not assumed to be the free gift's reset. This limitation must be
reported, and real acceptance should preserve any visible cooldown evidence for
a targeted period-policy update. Do not infer these periods from VIP or local midnight.

Full PASS requires every snapshot member handled, all available gifts verified,
no hidden unknown/error, paid/Protected safety, cleanup and selection restoration,
and actual verified coverage of every required claim path. Otherwise report PARTIAL.

## Resume after the first fleet

The first complete fleet (20260924-171957-687304Z) processed all eight targets.
Four BXH actions produced rank-specific receipts, kept RESERVED/POSSIBLE because
the old generic receipt title did not match. The repaired receipt uses three
unique anchors (rank title excluding digits, gem core excluding amount, continue
text), plus their relative arrangement. It grants bottom-left dismissal only.
The floral avatar frame is a masked UI-style variant excluding all portrait,
level and attention pixels; no account name or fixed tap is involved.

`bxh-shop-acceptance --resume-report PATH` preserves the original target snapshot
and continues only unfinished rewards, after current protection/disk checks.
Previously successful/unavailable routes are copied with their evidence; the
source report is immutable and each subsequent attempt is retained in history.
Newly discovered accounts are not added. Existing journal locks still apply.

A recent BXH POSSIBLE record can be reconciled without input only when its saved
AVAILABLE frame and rank receipt are independently reclassified, their original
task/ADB/boot identities agree, and the freshly reverified same persistent target
shows positive NOT_AVAILABLE evidence. The current capture must be under 30 seconds
old; the original receipt must follow its claimable frame within 60 seconds.
Time spent awaiting repairs/CI does not invalidate an otherwise complete chain or
grant another claim opportunity. Existing period/journal locks still apply. Receipt alone,
missing files, stale evidence, identity changes or still-active/unknown UI keep
the original lock. This path cannot send or repeat a claim.

The standard congratulations receipt also supports its observed dim continue-text
phase, paired with the unchanged independent title. An ambiguous/duplicate bright
text cannot be rescued by the dim variant. The same evidence-only reconciliation
can resolve each separate shop journal after fresh positive “Đã nhận” evidence;
it never dispatches a locked gift again.

The observed custom-weekly gift style has an additional clean orange-box core and
adjacent attention crop, on the verified weekly page only. Duplicate/conflicting
variants remain UNKNOWN; no account-specific route or lower threshold is used.
A recognized announcement speaker in the shop header means the gift may be
covered: at most four observation-only waits, then UNKNOWN if still covered.

The observed Blood Night event overlay uses title, started text and close symbol
at .98, excluding timer and animated art. It permits only the already authorized
bottom-left dismissal, with existing budgets and fresh capture. The detected X
is classification evidence, not an extra navigation/claim action.
