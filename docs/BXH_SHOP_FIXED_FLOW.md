# BXH and Tiệm fixed reward acceptance

Scope: BXH top-left chest, Tiệm Ưu Đãi Mỗi Ngày upper-right gift and
Thẻ Tuần Tự Chọn upper-right gift. These have three independent reward IDs.
No other shop tab, VIP, Idle or Phase 7 is included.

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
