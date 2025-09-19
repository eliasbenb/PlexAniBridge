"""API endpoints for accessing historical log files."""

import logging
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from src import config

__all__ = ["router"]


class LogFileModel(BaseModel):
    name: str
    size: int
    mtime: int  # epoch ms
    current: bool


class LogEntryModel(BaseModel):
    timestamp: str | None = None
    level: str
    message: str


router = APIRouter()

LOG_DIR: Path = (config.data_path / "logs").resolve()

LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) - "
    r"(?P<logger>[^ ]+?) - (?P<level>[A-Z]+)\t(?P<message>.*)$"
)


def _list_log_files() -> list[Path]:
    if not LOG_DIR.exists():
        return []
    # Include the active log file and rotated backups.
    return sorted(
        [p for p in LOG_DIR.glob("PlexAniBridge.*.log*") if p.is_file()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


@router.get(
    "/files",
    summary="List available log files",
    response_model=list[LogFileModel],
)
async def list_log_files() -> list[LogFileModel]:
    """Return metadata about available log files.

    Returns:
        JSONResponse: List of log file metadata sorted by most recent first.
    """
    files = _list_log_files()
    res: list[LogFileModel] = []

    # Determine current effective log level to identify active file.
    root_logger = logging.getLogger("PlexAniBridge")
    current_level_name = logging.getLevelName(root_logger.getEffectiveLevel())
    active_filename = f"PlexAniBridge.{current_level_name}.log"

    for f in files:
        st = f.stat()
        res.append(
            LogFileModel(
                name=f.name,
                size=st.st_size,
                mtime=int(st.st_mtime * 1000),
                # Active file is the one matching the current log level base file
                current=f.name == active_filename,
            )
        )

    return res


def _safe_resolve(name: str) -> Path:
    """Resolve a user-supplied file name safely within LOG_DIR.

    Args:
        name (str): The file name to resolve.

    Raises:
        HTTPException: If the file name is invalid or not found.
    """
    if "/" in name or ".." in name:
        raise HTTPException(status_code=400, detail="Invalid log file name")

    target = (LOG_DIR / name).resolve()

    if not str(target).startswith(str(LOG_DIR)):
        raise HTTPException(status_code=400, detail="Invalid log file name")

    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Log file not found")

    return target


def _tail_lines(path: Path, max_lines: int) -> list[str]:
    """Return up to the last max_lines of the file efficiently.

    Args:
        path (Path): The path to the log file.
        max_lines (int): The maximum number of lines to return. If 0, return all lines.

    Returns:
        list[str]: The last max_lines lines of the file (oldest first). If
                   max_lines == 0, return all lines.
    """
    if max_lines < 0:
        return []

    if max_lines == 0:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            return [ln.rstrip("\n\r") for ln in fh.readlines()]

    # Read in binary for efficiency, then decode assuming UTF-8.
    chunk_size = 8192
    lines: list[str] = []

    with path.open("rb") as fh:
        fh.seek(0, 2)
        file_size = fh.tell()
        buffer = b""
        pos = file_size

        while pos > 0 and len(lines) < max_lines:
            read_size = min(chunk_size, pos)
            pos -= read_size
            fh.seek(pos)
            buffer = fh.read(read_size) + buffer
            parts = buffer.split(b"\n")
            buffer = parts[0]
            for line in parts[1:]:
                try:
                    lines.append(line.decode("utf-8", errors="replace"))
                except Exception:
                    lines.append("")
                if len(lines) >= max_lines:
                    break

        if len(lines) < max_lines and buffer:
            try:
                lines.append(buffer.decode("utf-8", errors="replace"))
            except Exception:
                lines.append("")

    return list(reversed(lines[:max_lines]))


@router.get(
    "/file/{name}",
    summary="Fetch parsed tail of a log file",
    response_model=list[LogEntryModel],
)
async def get_log_file(
    name: str, lines: int = Query(500, ge=0, le=2000)
) -> list[LogEntryModel]:
    """Return the last N lines of a log file parsed into JSON entries.

    Args:
        name (str): File name (basename) of the log file.
        lines (int): Maximum number of lines to return (tail). Default 500.

    Returns:
        JSONResponse: Ordered list (oldest first) of parsed log entries.
    """
    path = _safe_resolve(name)
    raw_lines = _tail_lines(path, lines)
    res: list[LogEntryModel] = []

    for ln in raw_lines:
        ln = ln.rstrip("\n\r")
        m = LINE_RE.match(ln)
        if m:
            gd = m.groupdict()
            res.append(
                LogEntryModel(
                    timestamp=gd["timestamp"],
                    level=gd["level"],
                    message=gd["message"],
                )
            )
        else:
            res.append(LogEntryModel(timestamp=None, level="INFO", message=ln))

    return res
