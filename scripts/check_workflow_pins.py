"""Reject mutable third-party GitHub Action references."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
USES_PATTERN = re.compile(r"^\s*(?:-\s+)?uses:\s+([^\s#]+)(?:\s+#\s*(.+))?\s*$")
PINNED_ACTION = re.compile(r"^[^/@\s]+/[^/@\s]+(?:/[^@\s]+)?@[0-9a-f]{40}$")
VERSION_COMMENT = re.compile(r"\bv\d+(?:\.\d+){0,2}\b")


def main() -> None:
    failures: list[str] = []
    checked = 0

    for workflow in sorted((*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml"))):
        for line_number, line in enumerate(workflow.read_text().splitlines(), start=1):
            match = USES_PATTERN.match(line)
            if match is None:
                continue
            reference, comment = match.groups()
            if reference.startswith("./"):
                continue
            checked += 1
            location = f"{workflow.relative_to(ROOT)}:{line_number}"
            if not PINNED_ACTION.fullmatch(reference):
                failures.append(f"{location}: mutable or invalid Action reference {reference!r}")
            if comment is None or VERSION_COMMENT.search(comment) is None:
                failures.append(f"{location}: pin must include a '# vX.Y.Z' version comment")

    if checked == 0:
        failures.append("no third-party Action references were found")
    if failures:
        raise SystemExit("\n".join(failures))
    print(f"Verified {checked} immutable third-party Action references.")


if __name__ == "__main__":
    main()
