"""
utils/logger.py
Sets up a clean, coloured console logger + rotating file logger.
"""

import logging
import logging.handlers
import os
from pathlib import Path


def setup_logger() -> None:
    """Configure root logger once at startup.

    ``LOG_LEVEL`` controls the console. ``LOG_FILE_LEVEL`` can retain
    diagnostic records in the rotating log without making normal console use
    noisy.
    """
    console_level = _configured_level("LOG_LEVEL", logging.INFO)
    file_level = _configured_level("LOG_FILE_LEVEL", logging.DEBUG)

    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    root = logging.getLogger()
    root.setLevel(min(console_level, file_level))

    # ── Console handler ───────────────────────────────────
    console = logging.StreamHandler()
    console.setLevel(console_level)
    console.setFormatter(_ColourFormatter())
    root.addHandler(console)

    # ── Rotating file handler ─────────────────────────────
    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "roselinne.log",
        maxBytes=5 * 1024 * 1024,   # 5 MB
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(file_level)
    file_handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s  %(levelname)-8s  %(name)-20s  %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root.addHandler(file_handler)

    # Quiet down noisy libraries
    for noisy in ("discord", "discord.gateway", "discord.http", "aiohttp", "openai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def _configured_level(name: str, default: int) -> int:
    value = os.getenv(name, "").strip().upper()
    if not value:
        return default
    level = getattr(logging, value, None)
    if isinstance(level, int):
        return level
    logging.getLogger("roselinne.logger").warning(
        "Invalid %s=%r; using %s", name, value, logging.getLevelName(default)
    )
    return default


# ──────────────────────────────────────────────────────────
# ANSI colour formatter (Windows-safe via colorama if present)
# ──────────────────────────────────────────────────────────
_GREY    = "\x1b[38;5;240m"
_CYAN    = "\x1b[38;5;117m"
_YELLOW  = "\x1b[38;5;220m"
_RED     = "\x1b[38;5;203m"
_MAGENTA = "\x1b[38;5;176m"
_RESET   = "\x1b[0m"

_LEVEL_COLOURS = {
    logging.DEBUG:    _GREY,
    logging.INFO:     _CYAN,
    logging.WARNING:  _YELLOW,
    logging.ERROR:    _RED,
    logging.CRITICAL: _MAGENTA,
}


class _ColourFormatter(logging.Formatter):
    FMT = "%(asctime)s  {colour}%(levelname)-8s{reset}  %(name)-20s  %(message)s"
    DATE = "%H:%M:%S"

    def format(self, record: logging.LogRecord) -> str:
        colour = _LEVEL_COLOURS.get(record.levelno, _RESET)
        formatter = logging.Formatter(
            self.FMT.format(colour=colour, reset=_RESET),
            datefmt=self.DATE,
        )
        return formatter.format(record)
