from __future__ import annotations

import codecs
import re
from abc import ABC, abstractmethod
from collections.abc import Callable

from runbuoy.models import Progress, ProgressMode, RunManifest
from runbuoy.security.redaction import safe_message, strip_ansi

ProgressCallback = Callable[[Progress], None]


class RecordFramer:
    """Frame terminal text on LF or CR while preserving UTF-8 chunk boundaries."""

    def __init__(self) -> None:
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._buffer = ""

    def feed(self, chunk: bytes) -> list[tuple[str, str]]:
        self._buffer += self._decoder.decode(chunk)
        records: list[tuple[str, str]] = []
        start = 0
        index = 0
        while index < len(self._buffer):
            character = self._buffer[index]
            if character not in "\r\n":
                index += 1
                continue
            is_crlf = (
                character == "\r"
                and index + 1 < len(self._buffer)
                and self._buffer[index + 1] == "\n"
            )
            records.append((self._buffer[start:index], "\n" if is_crlf else character))
            if is_crlf:
                index += 1
            index += 1
            start = index
        self._buffer = self._buffer[start:]
        return records

    def flush(self) -> list[tuple[str, str]]:
        self._buffer += self._decoder.decode(b"", final=True)
        if not self._buffer:
            return []
        result = [(self._buffer, "")]
        self._buffer = ""
        return result


class ProgressAdapter(ABC):
    def __init__(self, callback: ProgressCallback) -> None:
        self.callback = callback

    @abstractmethod
    def feed(self, chunk: bytes) -> None:
        """Consume raw PTY output."""

    def close(self) -> None:
        return


class IndeterminateAdapter(ProgressAdapter):
    def feed(self, chunk: bytes) -> None:
        return


class RecordProgressAdapter(ProgressAdapter):
    def __init__(self, callback: ProgressCallback) -> None:
        super().__init__(callback)
        self.framer = RecordFramer()
        self._last_carriage_record: str | None = None

    def feed(self, chunk: bytes) -> None:
        for record, separator in self.framer.feed(chunk):
            self._handle_record(strip_ansi(record).strip(), separator)

    def close(self) -> None:
        for record, separator in self.framer.flush():
            self._handle_record(strip_ansi(record).strip(), separator)

    def _handle_record(self, record: str, separator: str) -> None:
        if not record:
            return
        if separator == "\r" and record == self._last_carriage_record:
            return
        self._last_carriage_record = record if separator == "\r" else None
        self.on_record(record)

    @abstractmethod
    def on_record(self, record: str) -> None:
        """Parse one ANSI-free terminal record."""


class LineProgressAdapter(RecordProgressAdapter):
    def __init__(
        self,
        callback: ProgressCallback,
        *,
        total: float,
        match: str | None = None,
        unit: str | None = "lines",
    ) -> None:
        if total <= 0:
            raise ValueError("total must be greater than zero")
        super().__init__(callback)
        self.total = total
        self.pattern = re.compile(match) if match else None
        self.unit = unit
        self.current = 0.0

    def on_record(self, record: str) -> None:
        if self.pattern is not None and self.pattern.search(record) is None:
            return
        self.current = min(self.current + 1, self.total)
        self.callback(
            Progress.determinate(
                self.current,
                self.total,
                source="lines",
                unit=self.unit,
                message=safe_message(record),
            )
        )


class RegexProgressAdapter(RecordProgressAdapter):
    def __init__(
        self,
        callback: ProgressCallback,
        *,
        pattern: str,
        unit: str | None = None,
    ) -> None:
        super().__init__(callback)
        self.pattern = re.compile(pattern)
        if self.pattern.groups < 2:
            raise ValueError("regex progress pattern requires current and total capture groups")
        self.unit = unit
        self._last_current = -1.0

    def on_record(self, record: str) -> None:
        match = self.pattern.search(record)
        if match is None:
            return
        try:
            current = float(match.group(1))
            total = float(match.group(2))
        except (ValueError, IndexError) as error:
            raise ValueError("regex progress captures must be numeric") from error
        if total <= 0 or current < self._last_current:
            return
        progress = Progress.determinate(
            current,
            total,
            source="regex",
            unit=self.unit,
            message=safe_message(record),
        )
        if progress.current == self._last_current:
            return
        self._last_current = progress.current or 0
        self.callback(progress)


class StructuredProgressAdapter(ProgressAdapter):
    """Structured updates arrive over the authenticated Unix socket."""

    def feed(self, chunk: bytes) -> None:
        return

    def accept(
        self,
        *,
        current: float,
        total: float,
        unit: str | None = None,
        phase: str | None = None,
        message: str | None = None,
    ) -> None:
        self.callback(
            Progress.determinate(
                current,
                total,
                source="explicit",
                unit=unit,
                phase=phase,
                message=safe_message(message),
            )
        )


def make_adapter(manifest: RunManifest, callback: ProgressCallback) -> ProgressAdapter:
    if manifest.progress_mode == ProgressMode.LINES:
        if manifest.total is None:
            raise ValueError("--total is required for lines progress")
        return LineProgressAdapter(
            callback, total=manifest.total, match=manifest.match, unit=manifest.unit or "lines"
        )
    if manifest.progress_mode == ProgressMode.REGEX:
        if not manifest.pattern:
            raise ValueError("--pattern is required for regex progress")
        return RegexProgressAdapter(callback, pattern=manifest.pattern, unit=manifest.unit)
    if manifest.progress_mode == ProgressMode.STRUCTURED:
        return StructuredProgressAdapter(callback)
    return IndeterminateAdapter(callback)
