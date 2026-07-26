from __future__ import annotations

from runbuoy.models import Progress
from runbuoy.progress.adapters import LineProgressAdapter, RegexProgressAdapter


def test_line_adapter_handles_chunks_ansi_and_carriage_deduplication() -> None:
    values: list[Progress] = []
    adapter = LineProgressAdapter(values.append, total=3, match=r"^DONE$")
    adapter.feed(b"\x1b[32mDO")
    adapter.feed(b"NE\x1b[0m\rDONE\r")
    adapter.feed(b"DONE\n")
    adapter.close()
    assert [value.current for value in values] == [1, 2]
    assert values[-1].fraction == 2 / 3


def test_line_adapter_counts_identical_newline_records() -> None:
    values: list[Progress] = []
    adapter = LineProgressAdapter(values.append, total=100, match=r"^Hello World$")
    adapter.feed(("Hello World\n" * 100).encode())
    assert len(values) == 100
    assert values[-1].fraction == 1


def test_regex_adapter_handles_utf8_and_record_chunk_boundaries() -> None:
    values: list[Progress] = []
    adapter = RegexProgressAdapter(values.append, pattern=r"^PROGRESS: ([0-9]+)/([0-9]+)$")
    adapter.feed("阶段\nPROG".encode())
    adapter.feed(b"RESS: 37/")
    adapter.feed(b"100\r")
    assert values[0].current == 37
    assert values[0].total == 100


def test_regex_adapter_clamps_and_ignores_stale_or_duplicate_progress() -> None:
    values: list[Progress] = []
    adapter = RegexProgressAdapter(values.append, pattern=r"(\d+)/(\d+)")
    adapter.feed(b"9/10\r9/10\r8/10\r12/10\r")
    assert [value.current for value in values] == [9, 10]
