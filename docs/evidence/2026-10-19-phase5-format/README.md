# Phase 5 — repository-wide formatting, with strict Python AST equality

The format-only changes follow `ffb04a0` (shared command constants) and structural cleanup `e335ea8`. Ruff uses 120 columns;
Prettier formats active TS/JS/CSS/JSON. Archived documents, prior evidence, raw scientific artifacts, notebooks, generated
files, dependency locks, resource profiles and fixtures are excluded. No numeric function or data value is rewritten.

`ast-final.json` compares all 287 active Python source/tool/test/report files with the exact baseline commit recorded in
that file: zero changed ASTs. This includes every Recipe v1 noise/ES/ledger/generation-record module. The initial formatter
trimmed docstring whitespace in six files; 13 local `fmt: off/on` guards preserve those literal values exactly. They are
comments and leave the AST unchanged. The initial mismatch is retained in `ast.json`; the final proof is `ast-final.json`.
An import-order lint issue was resolved by moving the duplicated command capability sets into their shared definition
before the final formatting baseline. A frontend JSON fixture was restored unchanged and all fixture directories excluded.

`ruff-check-final.log`, `ruff-format-check.log` and `prettier-check.log` record passing lint/style checks.
`runtime.log`: 2,110 passed, 100 skipped. `check-all.log` and `checks/` record the full CPU product check (backend 283 cases).
`source-packages.log` confirms isolated Worker/Server source archive imports without torch. Published resource tarballs,
profiles and the deployed lab remain untouched. The formatting commit is recorded in `.git-blame-ignore-revs` by the
following documentation commit, because a commit cannot contain its own id.

## What this does NOT show

No GPU run, native Windows test, installer publication or live deployment. AST equality proves Python syntax-tree
preservation; browser, type, unit and build checks provide the separate TS/JS verification. Raw evidence is not reformatted.
