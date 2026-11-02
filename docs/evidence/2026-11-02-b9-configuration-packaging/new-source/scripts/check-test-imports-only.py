#!/usr/bin/env python3
"""Prove existing backend tests changed imports only, including imports in child Python command strings."""

import argparse
import ast
from difflib import SequenceMatcher
import hashlib
import json
from pathlib import Path
import subprocess


def assert_imports_only(before, after):
    try:
        old, new = ast.parse(before), ast.parse(after)
    except SyntaxError:
        raise ValueError("Changed source is not a valid Python program") from None
    allowed = []
    for tree in (old, new):
        allowed.append(
            {
                line
                for node in ast.walk(tree)
                if isinstance(node, (ast.Import, ast.ImportFrom))
                for line in range(node.lineno, node.end_lineno + 1)
            }
        )

    class RemoveImports(ast.NodeTransformer):
        def visit_Import(self, node):
            return None

        def visit_ImportFrom(self, node):
            return None

    old, new = RemoveImports().visit(old), RemoveImports().visit(new)
    embedded = 0

    def compare(left, right):
        nonlocal embedded
        if type(left) is not type(right):
            raise ValueError("A non-import syntax node changed")
        if (
            isinstance(left, ast.Constant)
            and isinstance(left.value, str)
            and isinstance(right.value, str)
            and left.value != right.value
        ):
            result = assert_imports_only(left.value, right.value)
            embedded += 1 + result["embeddedPrograms"]
            for index, node in enumerate((left, right)):
                allowed[index].update(range(node.lineno, node.end_lineno + 1))
            return
        if isinstance(left, ast.AST):
            for name in left._fields:
                compare(getattr(left, name), getattr(right, name))
        elif isinstance(left, list):
            if len(left) != len(right):
                raise ValueError("A non-import statement or argument changed")
            for first, second in zip(left, right, strict=True):
                compare(first, second)
        elif left != right:
            raise ValueError("A non-import value changed")

    compare(old, new)
    changed = 0
    for operation, first, last, new_first, new_last in SequenceMatcher(
        a=before.splitlines(), b=after.splitlines(), autojunk=False
    ).get_opcodes():
        if operation == "equal":
            continue
        for index, begin, end in ((0, first, last), (1, new_first, new_last)):
            lines = set(range(begin + 1, end + 1))
            if not lines <= allowed[index]:
                raise ValueError("A changed line is outside an import or a verified child-program import")
            changed += len(lines)
    return {"changedLines": changed, "embeddedPrograms": embedded}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]

    def git(*arguments):
        return subprocess.check_output(["git", *arguments], cwd=root, text=True)

    base = git("rev-parse", "--verify", args.base + "^{commit}").strip()
    existing = [
        name
        for name in git("ls-tree", "-r", "--name-only", base, "--", "backend/tests").splitlines()
        if name.endswith(".py")
    ]
    changes = {}
    for name in existing:
        old = git("show", base + ":" + name)
        source = root / name
        if not source.is_file():
            raise ValueError("An existing test/helper was removed: " + name)
        new = source.read_text()
        if old != new:
            changes[name] = {
                **assert_imports_only(old, new),
                "beforeSha256": hashlib.sha256(old.encode()).hexdigest(),
                "afterSha256": hashlib.sha256(new.encode()).hexdigest(),
            }
    current = set(git("ls-files", "--cached", "--others", "--exclude-standard", "--", "backend/tests").splitlines())
    report = {
        "baseline": base,
        "checkedExistingFiles": len(existing),
        "changedFiles": changes,
        "addedTestsAndHelpers": sorted(name for name in current - set(existing) if name.endswith(".py")),
        "nonImportAstUnchanged": True,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"PASS import-only changes in {len(changes)} existing test/helper files; {len(existing)} checked")


if __name__ == "__main__":
    main()
