"""Cross-platform process lock for the bot entry point."""

from __future__ import annotations

import os
from pathlib import Path

if os.name == "nt":
    import msvcrt
else:
    import fcntl


class SingleInstanceLock:
    """Keep one bot process active while allowing stale lock files to recover."""

    def __init__(self, path: Path):
        self.path = path
        self._file = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("a+", encoding="ascii")
        self._file.seek(0)
        if self._file.tell() == 0:
            self._file.write("0")
            self._file.flush()
        self._file.seek(0)
        try:
            if os.name == "nt":
                msvcrt.locking(self._file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(self._file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, OSError):
            self._file.close()
            self._file = None
            return False

        self._file.seek(0)
        self._file.truncate()
        self._file.write(str(os.getpid()))
        self._file.flush()
        return True

    def release(self) -> None:
        if self._file is None:
            return
        try:
            if os.name == "nt":
                self._file.seek(0)
                msvcrt.locking(self._file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
        finally:
            self._file.close()
            self._file = None

    def __enter__(self) -> SingleInstanceLock:
        if not self.acquire():
            raise RuntimeError("Another Roselinne process is already running.")
        return self

    def __exit__(self, _exc_type, _exc_value, _traceback) -> None:
        self.release()
