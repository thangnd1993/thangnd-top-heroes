# Idle Reward real visual evidence

These templates were cropped from fresh screenshots of `4 / 3-Chíp` using the verified explicit
ADB target `emulator-5562`. Full screenshots remain outside Git.

The availability gate is the glowing Adventure chest with a red dot. The blue `Nhận` button alone
is deliberately insufficient because it remains enabled seconds after a claim. The adjacent `6/6`
hourglass is excluded from every action anchor because it can spend stamina.

The reward panel is claimable only after that entry gate and then requires the verified title,
claim button, and minimum green accumulation segment. A gray remainder is not a not-available
signal because partially accumulated rewards contain both green and gray segments. The panel is
classified not claimable only when its title and unique no-reward message both match; the entry
screen remains the authoritative availability gate before opening it.

The immediate post-claim variant instead matches the gray *start* of the accumulation bar in a
tightly bounded region. This is mutually exclusive with the green minimum-fill anchor and cannot
slide down to the gray remainder of a partially filled bar.

The claimable chest has separate closed and open/glowing animation anchors. They use compact chest-core
crops and a unique current-frame search over the full viewport. The crop excludes the account-dependent
`Cấp` level label and map background. Fleet evidence scored 0.972–0.981 on those cores while the former
larger template scored 0.871–0.888. The strict 0.95 threshold remains above the observed fleet range's
lower bound and below every saved positive frame. Duplicate, weak, or conflicting matches fail closed.

The saved Pooh5 Adventure frame also contains a side panel outside the chest's live bounding box. It is
not treated as a blocking popup: the chest must still be uniquely detected in the current frame before
it can be tapped.

The Adventure portal action anchor uses only its stable blue core and excludes the animated flame.
