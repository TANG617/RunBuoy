"""Check repository-relative links in Markdown sources."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
LINK_PATTERN = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
EXCLUDED_PARTS = {".git", ".venv", "doc_build", "node_modules"}


def markdown_files() -> list[Path]:
    return sorted(
        path
        for path in ROOT.rglob("*")
        if path.suffix in {".md", ".mdx"} and EXCLUDED_PARTS.isdisjoint(path.parts)
    )


def main() -> None:
    failures: list[str] = []
    checked = 0
    for source in markdown_files():
        for match in LINK_PATTERN.finditer(source.read_text(errors="replace")):
            raw_target = match.group(1).strip()
            if raw_target.startswith("<") and raw_target.endswith(">"):
                raw_target = raw_target[1:-1]
            raw_target = raw_target.split(maxsplit=1)[0]
            parsed = urlsplit(raw_target)
            if parsed.scheme or parsed.netloc or raw_target.startswith("#"):
                continue
            if parsed.path.startswith("/") and "website" in source.parts:
                continue
            target_path = unquote(parsed.path)
            if not target_path:
                continue
            checked += 1
            target = ROOT / target_path.removeprefix("/")
            if not parsed.path.startswith("/"):
                target = source.parent / target_path
            if not target.resolve().exists():
                line = source.read_text(errors="replace")[: match.start()].count("\n") + 1
                failures.append(
                    f"{source.relative_to(ROOT)}:{line}: missing local target {raw_target!r}"
                )

    if failures:
        raise SystemExit("\n".join(failures))
    print(f"Verified {checked} repository-relative Markdown links.")


if __name__ == "__main__":
    main()
