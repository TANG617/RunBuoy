#!/usr/bin/env python3
"""Fail CI when RunBuoy's one-way, read-only boundary regresses."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_PATH_FRAGMENTS = (
    "/cancel",
    "/retry",
    "/input",
    "/commands",
    "/execute",
    "/signal",
    "/approve",
    "/keys",
)
FORBIDDEN_IOS_DEPENDENCIES = (
    "react-native",
    "expo",
    "swiftterm",
    "wkwebview",
    "webkit",
    "nmssh",
    "citadel",
    "terminal emulator",
)
FORBIDDEN_IOS_UI = (
    "cancel run",
    "retry run",
    "send input",
    "approve command",
    "open terminal",
    "attach terminal",
    "terminal keyboard",
)
SENSITIVE_REMOTE_KEYS = {
    "argv",
    "cwd",
    "env",
    "environment",
    "stdout",
    "stderr",
    "stdin",
    "token",
    "secret",
    "command",
}


def tracked_files(prefix: str) -> Iterable[Path]:
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("git is required for the boundary checker")
    result = subprocess.run(  # noqa: S603 - absolute trusted executable and fixed arguments
        [git, "ls-files", "-z", "--", prefix],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    for raw in result.stdout.split(b"\0"):
        if raw:
            yield ROOT / raw.decode()


def text_files(prefix: str, suffixes: set[str]) -> Iterable[tuple[Path, str]]:
    for path in tracked_files(prefix):
        if path.suffix.lower() in suffixes and path.is_file():
            yield path, path.read_text(encoding="utf-8", errors="ignore")


def recursive_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        own = {str(key).lower() for key in value}
        nested = set().union(*(recursive_keys(child) for child in value.values()), set())
        return own | nested
    if isinstance(value, list):
        return set().union(*(recursive_keys(child) for child in value), set())
    return set()


def contains_dependency_name(source: str, dependency: str) -> bool:
    """Match dependency tokens without flagging words such as exposing/EmptyBody."""
    tokens = [re.escape(token) for token in re.split(r"[\s_-]+", dependency)]
    pattern = r"(?<![a-z0-9])" + r"[\s_-]+".join(tokens) + r"(?![a-z0-9])"
    return re.search(pattern, source, re.I) is not None


def main() -> int:
    failures: list[str] = []

    openapi_path = ROOT / "packages/protocol/openapi.yaml"
    openapi = openapi_path.read_text(encoding="utf-8").lower()
    for fragment in FORBIDDEN_PATH_FRAGMENTS:
        route_pattern = re.compile(rf"^\s{{2}}[^\n]*{re.escape(fragment)}[^\n]*:\s*$", re.M)
        if route_pattern.search(openapi):
            failures.append(f"OpenAPI exposes forbidden route fragment: {fragment}")

    for path, source in text_files("server", {".py"}):
        lowered = source.lower()
        if re.search(r"@\w+\.websocket\s*\(", source, re.I) or "websocketroute" in lowered:
            failures.append(f"Server WebSocket route found: {path.relative_to(ROOT)}")
        for fragment in FORBIDDEN_PATH_FRAGMENTS:
            route_pattern = re.compile(
                rf"@\w+\.(?:post|put|patch|get|delete)\s*\(\s*[\"'][^\"']*"
                rf"{re.escape(fragment)}",
                re.I,
            )
            if route_pattern.search(source):
                failures.append(
                    f"Server exposes forbidden route {fragment}: {path.relative_to(ROOT)}"
                )
        if re.search(r"(poll|fetch|get).{0,24}(remote[_ -]?command|machine[_ -]?inbox)", lowered):
            failures.append(f"Machine remote-command polling found: {path.relative_to(ROOT)}")

    ios_suffixes = {".swift", ".pbxproj", ".plist", ".entitlements", ".resolved"}
    for path, source in text_files("apps/ios", ios_suffixes):
        lowered = source.lower()
        for dependency in FORBIDDEN_IOS_DEPENDENCIES:
            if contains_dependency_name(lowered, dependency):
                failures.append(
                    f"Forbidden iOS dependency/API '{dependency}': {path.relative_to(ROOT)}"
                )
        if path.suffix.lower() == ".swift":
            for label in FORBIDDEN_IOS_UI:
                if label in lowered:
                    failures.append(f"Forbidden mutation UI '{label}': {path.relative_to(ROOT)}")
            if re.search(
                r"\b(?:import|class|struct)\s+\w*(?:Terminal|SSH|PTY)\w*",
                source,
            ):
                failures.append(f"Terminal/SSH type found: {path.relative_to(ROOT)}")

    fixture_path = ROOT / "packages/protocol/fixtures/default-upload.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    unsafe = sorted(recursive_keys(fixture) & SENSITIVE_REMOTE_KEYS)
    if unsafe:
        failures.append(f"Default remote fixture includes sensitive keys: {', '.join(unsafe)}")

    if failures:
        print("RunBuoy read-only boundary FAILED", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print("RunBuoy read-only boundary: PASS")
    print("- no remote-control OpenAPI or server routes")
    print("- no server WebSocket or machine command polling")
    print("- no forbidden iOS runtime, terminal dependency, or mutation UI")
    print("- default remote payload excludes sensitive execution data")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
