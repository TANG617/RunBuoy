from __future__ import annotations

from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]


def text(relative: str) -> str:
    return (SKILL_ROOT / relative).read_text(encoding="utf-8")


def test_installation_routes_global_and_project_environments_independently() -> None:
    skill = text("SKILL.md")
    installation = text("references/installation.md")

    for expected in (
        "command -v runbuoy",
        "uv tool install --python 3.12 runbuoy",
        "runbuoy --version",
        "runbuoy doctor --json",
        "runbuoy capabilities --json",
        "uv add --optional runbuoy runbuoy",
        "requirements-runbuoy.txt",
        "actual interpreter",
        "sudo",
        "curl",
    ):
        assert expected in installation
    assert "Global CLI and project API environments are intentionally separate" in installation
    assert "Ordinary requests" in skill


def test_forward_routes_keep_local_execution_independent_from_delivery() -> None:
    skill = text("SKILL.md")

    for expected in (
        "Existing Run ID",
        "Existing PID/process",
        "cannot be adopted or attached",
        "paired == false",
        "paired == true && reachable == false",
        "continue the local Run",
        "ok == true",
        "detached == true",
        "worker_ready == true",
        "do not poll",
        "Use `--wait` only",
    ):
        assert expected in skill


def test_python_fallback_and_progress_guidance_are_fail_open() -> None:
    python_api = text("references/python-api.md")
    progress = text("references/progress.md")

    for expected in (
        'error.name != "runbuoy"',
        "raise",
        "class NoopReporter",
        "enabled = False",
        "return False",
        "required=False",
        "on_error",
    ):
        assert expected in python_api
    assert "unknown" in progress
    assert "single coordinator" in progress


def test_privacy_and_read_only_boundaries_cover_all_remote_message_sources() -> None:
    privacy = text("references/privacy.md")

    for expected in (
        "--progress lines",
        "--progress regex",
        "structured",
        "log tail",
        "Machine → Server → iPhone",
        "cannot start",
        "cancel",
        "attach",
    ):
        assert expected in privacy
