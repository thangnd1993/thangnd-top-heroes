---
name: runtime-acceptance
description: Judge real runtime acceptance of Top Heroes Auto Manager from the installed app's logs and reports - separate VERIFIED, POSSIBLE, BLOCKED and NOT_AVAILABLE, and never call a phase passed from CI alone. Use after the user has run the installed app.
---

# Runtime acceptance analysis

1. Run `/analyze-run` first to identify the run and build; confirm the exe that ran equals the delivered build (`runtime.exe_sha256`).
2. Classify every frozen-plan reward per account: **VERIFIED** (journal VERIFIED + postcondition evidence), **POSSIBLE** (dispatched, unproven; locked), **BLOCKED**
   (needs evidence/decision; list the exact blocker), **NOT_AVAILABLE** (positively proven absent - never inferred from BLOCKED/UNKNOWN), **NOT_RUN_TARGET_BLOCKED** (account lost).
3. A phase passes only when every enabled route is terminal and verified on the real app for all authorised targets, cleanup is proven (selection/running state of
   run-owned instances only), names unchanged, Protected untouched. Otherwise the verdict is PARTIAL with the list.
4. State what CI/unit tests prove (code paths) versus what only a user run proves (gameplay). Do not start Phase 9 or declare Phase 8 complete without this evidence.
