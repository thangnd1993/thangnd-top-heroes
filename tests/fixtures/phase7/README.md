# Phase 7 offline reference fixtures

Ten user-authorized annotated game screenshots, re-encoded as PNG to omit
ancillary metadata. Game UI only. These qualify structure and unmarked cores;
real acceptance still requires fresh screenshots from the passing CI artifact.

Tests use mock transport/journals and synthetic negative variants; no real
emulator or account input. Runtime templates exclude annotation strokes.


`home-live.png` is the clean Home capture from the authorized random index11
acceptance on 2026-09-27 (`20260927-111159-869224Z-guild-mail.png`). It qualifies
reference/live entry resampling, unrelated-icon rejection and duplicate rejection.
It contains game UI only. The fixture is not a source of runtime coordinates.

`guild-live.png` is the clean Guild screen reached through the qualified Home
entry in the bound random acceptance (20260927-120802-242844Z). It qualifies
outlined-text resampling, positive page pairs and dimmed/partial negatives.

The remaining `*-live*.png` images come from the bound random acceptance
`20260927-144934-534222Z`, index11. They cover territory tab settling, the196
loot count, member12→received-check rows while Quick Claim remains green,
connected technology graph lines, and Mail4/10/60 badges plus selected tab
variants. No stored coordinates are used at runtime. The member before/after/
confirmation frames belong to ONE dispatch (journal122); never replay it.
