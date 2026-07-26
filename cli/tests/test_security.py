from __future__ import annotations

import pytest

from runbuoy.security.redaction import (
    assert_safe_remote_payload,
    redact,
    strip_ansi,
)
from runbuoy.security.titles import safe_title


def test_safe_title_drops_paths_and_arguments() -> None:
    command = ["/usr/bin/python3", "/private/project/experiment.py", "--token", "secret"]
    assert safe_title(command) == "python3 · experiment.py"
    assert safe_title(["cargo", "test", "--all"]) == "cargo · test"
    assert safe_title(["docker", "build", "--secret=abc"]) == "docker · build"


def test_explicit_title_is_single_line_and_redacted() -> None:
    assert safe_title(["x"], "Build\nAPI_KEY=hunter2") == "Build API_KEY=[REDACTED]"


def test_redaction_and_ansi_stripping() -> None:
    value = "\x1b[31mfailed\x1b[0m token=abcdef Authorization: Bearer xyz"
    cleaned = redact(value)
    assert "\x1b" not in cleaned
    assert "abcdef" not in cleaned
    assert "xyz" not in cleaned
    assert strip_ansi("\x1b[32mok\x1b[0m") == "ok"


@pytest.mark.parametrize("field", ["argv", "cwd", "env", "stdout", "stderr", "api_key"])
def test_remote_payload_rejects_sensitive_fields(field: str) -> None:
    with pytest.raises(ValueError, match="forbidden remote field"):
        assert_safe_remote_payload({"safe": {"nested": [{field: "secret"}]}})
