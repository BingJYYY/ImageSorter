"""Per-project CSV operation log.

Each row: time, source_path, action (copy/move/delete/undo_copy/undo_move),
destination_path, category_key, result (ok/fail), error_message.
"""

from __future__ import annotations
import csv, time, os
from pathlib import Path
from typing import Optional


class CsvLogger:
    FIELDNAMES = ("time", "source_path", "action", "destination_path",
                  "category_key", "result", "error")

    def __init__(self, log_path: Path):
        self.path = Path(log_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = None
        self._writer = None
        self._open()

    def _open(self) -> None:
        # newline="" is recommended by the csv module on Windows
        self._file = open(self.path, "a", newline="", encoding="utf-8-sig")
        self._writer = csv.DictWriter(self._file, fieldnames=self.FIELDNAMES)
        if self.path.stat().st_size == 0:
            self._writer.writeheader()
            self._file.flush()

    def write(self, *, source: str, action: str, destination: str = "",
              category: str = "", result: str = "ok", error: str = "") -> None:
        if self._writer is None:
            return
        try:
            self._writer.writerow({
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "source_path": source,
                "action": action,
                "destination_path": destination,
                "category_key": category,
                "result": result,
                "error": error,
            })
            self._file.flush()
        except Exception:
            pass

    def close(self) -> None:
        try:
            if self._file:
                self._file.close()
        except Exception:
            pass
        self._file = None
        self._writer = None
