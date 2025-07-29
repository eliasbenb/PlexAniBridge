"""Logs routes."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.config.settings import PlexAnibridgeConfig
from src.web.dependencies import get_config, get_templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def logs_viewer(
    request: Request,
    templates: Jinja2Templates = Depends(get_templates),
    config: PlexAnibridgeConfig = Depends(get_config),
):
    """Live logs viewer page."""
    log_dir = config.data_path / "logs"
    log_files = []

    if log_dir.exists():
        for log_file in log_dir.glob("*.log"):
            stat = log_file.stat()
            log_files.append(
                {
                    "name": log_file.name,
                    "size": stat.st_size,
                    "modified": stat.st_mtime,
                }
            )

        # Sort by modification time, newest first
        log_files.sort(key=lambda x: x["modified"], reverse=True)

    context = {
        "request": request,
        "title": "Logs",
        "log_files": log_files,
        "log_dir": str(log_dir),
    }

    return templates.TemplateResponse("logs.html.jinja", context)


@router.get("/tail/{log_file}")
async def tail_log(
    log_file: str,
    config: PlexAnibridgeConfig = Depends(get_config),
    lines: int = 100,
):
    """Get the last N lines of a log file."""
    log_path = config.data_path / "logs" / log_file

    if not log_path.exists() or not log_path.is_file():
        return {"error": "Log file not found"}

    try:
        # Read the last N lines efficiently
        with open(log_path, "rb") as f:
            # Go to end of file
            f.seek(0, 2)
            file_size = f.tell()

            # Read file in chunks from the end
            lines_found = []
            buffer = ""
            chunk_size = 1024

            position = file_size
            while position > 0 and len(lines_found) < lines:
                # Calculate chunk size (don't go below 0)
                chunk_size = min(chunk_size, position)
                position -= chunk_size

                # Read chunk
                f.seek(position)
                chunk = f.read(chunk_size).decode("utf-8", errors="ignore")
                buffer = chunk + buffer

                # Split into lines
                lines_in_buffer = buffer.split("\n")
                if position == 0:
                    # If we're at the beginning, use all lines
                    lines_found = lines_in_buffer + lines_found
                else:
                    # Keep the last line for next iteration (might be incomplete)
                    lines_found = lines_in_buffer[1:] + lines_found
                    buffer = lines_in_buffer[0]

            # Take only the requested number of lines
            result_lines = (
                lines_found[-lines:] if len(lines_found) > lines else lines_found
            )

            return {"lines": [line for line in result_lines if line.strip()]}

    except Exception as e:
        return {"error": f"Failed to read log file: {str(e)}"}
