"""Shared CLI progress events and terminal rendering helpers."""

from __future__ import annotations

import sys
import threading
from dataclasses import dataclass
from typing import Callable, Literal, TextIO

ProgressStage = Literal["start", "update", "finish"]


@dataclass(frozen=True)
class ProgressEvent:
    """Normalized progress update emitted by long-running CLI workflows."""

    phase: str
    message: str
    stage: ProgressStage
    current: int | None = None
    total: int | None = None


ProgressCallback = Callable[[ProgressEvent], None]


def emit_progress(
    callback: ProgressCallback | None,
    *,
    phase: str,
    message: str,
    stage: ProgressStage,
    current: int | None = None,
    total: int | None = None,
) -> None:
    """Emit one progress event only when a callback is present."""
    if callback is None:
        return
    callback(
        ProgressEvent(
            phase=phase,
            message=message,
            stage=stage,
            current=current,
            total=total,
        )
    )


class TerminalProgressRenderer:
    """Render progress updates for the CLI without pulling in heavy UI deps."""

    def __init__(self, *, stream: TextIO | None = None) -> None:
        self.stream = stream or sys.stderr
        self._lock = threading.Lock()
        self._spinner_stop = threading.Event()
        self._spinner_thread: threading.Thread | None = None
        self._spinner_message = ""
        self._spinner_phase = ""

    def __call__(self, event: ProgressEvent) -> None:
        if event.current is not None and event.total is not None:
            self._stop_spinner()
            self._write_line(
                f"[progress] {event.message} {event.current}/{event.total}"
            )
            return
        if event.stage == "start":
            self._start_spinner(event.phase, event.message)
            return
        if event.stage == "finish":
            self._stop_spinner(final_message=f"[done] {event.message}")
            return
        self._stop_spinner()
        self._write_line(f"[progress] {event.message}")

    def close(self) -> None:
        """Stop any active spinner before process exit."""
        self._stop_spinner()

    def _start_spinner(self, phase: str, message: str) -> None:
        self._stop_spinner()
        if not self._is_tty():
            self._write_line(f"[start] {message}")
            return
        self._spinner_phase = phase
        self._spinner_message = message
        self._spinner_stop = threading.Event()
        self._spinner_thread = threading.Thread(
            target=self._run_spinner,
            daemon=True,
        )
        self._spinner_thread.start()

    def _stop_spinner(self, *, final_message: str | None = None) -> None:
        thread = self._spinner_thread
        if thread is not None:
            self._spinner_stop.set()
            thread.join(timeout=1.0)
            self._spinner_thread = None
            with self._lock:
                self.stream.write("\r")
                self.stream.write(" " * (len(self._spinner_message) + 16))
                self.stream.write("\r")
                self.stream.flush()
        if final_message is not None:
            self._write_line(final_message)

    def _run_spinner(self) -> None:
        frames = "|/-\\"
        index = 0
        while not self._spinner_stop.wait(0.1):
            frame = frames[index % len(frames)]
            with self._lock:
                self.stream.write(f"\r[{frame}] {self._spinner_message}")
                self.stream.flush()
            index += 1

    def _write_line(self, message: str) -> None:
        with self._lock:
            self.stream.write(message + "\n")
            self.stream.flush()

    def _is_tty(self) -> bool:
        isatty = getattr(self.stream, "isatty", None)
        return bool(callable(isatty) and isatty())
