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

The claimable chest has separate closed and open/glowing animation anchors. Both keep the strict
`0.9` threshold so animation coverage does not weaken the not-available guard.

The Adventure portal action anchor uses only its stable blue core and excludes the animated flame.
