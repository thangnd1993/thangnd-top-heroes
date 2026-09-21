# Daily-offer navigation evidence

These five anchors are a navigation-only profile for the verified index-2
daily-offer viewport. They were cropped from the same-account 2026-09-22
captures and are intentionally separate from reward/cost evidence:

- `phase6-daily-page` identifies the daily-offer page title.
- `phase6-daily-info-button` identifies the information button on that page.
  It is only an entry to the generic help popup; it does not prove a free gift.
- `phase6-daily-info-popup` identifies the information popup. Its text
  describes purchases and activation tickets; it does not prove a free gift.
- `phase6-daily-info-close` identifies the popup close control.
- `phase6-daily-exit` identifies the daily-page back/exit control. The arrow
  is generic and can also appear on neighboring shop tabs, so it is
  action-only evidence and must be gated by an independently verified fresh
  `phase6-daily-page` match before dispatch.

Every action still requires a unique match in a fresh current-account frame,
an exact target/boot identity, and a fresh destination check. These anchors do
not authorize a gift, purchase, ticket use, claim, scroll, or resource spend.
The fixed four-action navigation route is wired to the dedicated
`shop-navigation-survey` CLI/UI task. A separate claim-free `shop-survey`
task now packages only the qualified Home → daily-offer → information-popup
→ daily-offer → Home path. It deliberately reports `PARTIAL` because no
neighboring tab, scroll boundary, zero-cost gift, or reward postcondition has
been independently qualified. The daily gift remains
`UNKNOWN`/`NOT_IMPLEMENTED` until independent zero-cost and postcondition
evidence exists.
