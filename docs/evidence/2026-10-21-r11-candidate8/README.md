# r11 candidate8: the member-restart fix, packaged (predeclared, then checked)

Build `lf1-20261021-r11-candidate8`, the bytes meant for release. Source: candidate7 plus fix `98dd705` (ADR-009 item 8).
Resources commit `ea5c5b9`; CPU gate on the source: `../2026-10-21-r11-candidate8-checks/` (23/23 ALL PASS).
Steps as in `../2026-10-21-r11-candidate7/README.md`: build into a fresh Archive directory (UUID 10443D1F443D094C
checked), prepare-only, compare every runtime source byte, source-copy + packaged Linux Worker and Server checks.
