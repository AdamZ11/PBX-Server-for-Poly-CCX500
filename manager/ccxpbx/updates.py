"""Update watcher: talks to the root helper (install/ccxpbx-update.sh) through files only.

The helper writes status.json and update.log into UPDATE_DIR; the web app asks for a check or an
update by writing the word "check" or "apply" into UPDATE_DIR/request, which a systemd path unit
watches. The web app never runs git or the installer itself and never gets root.
"""
import json
import time
from pathlib import Path

from . import config

STALE_RUNNING = 90 * 60   # a "running" status older than this is treated as failed


def update_dir() -> Path:
    return config.DATA_DIR / "update"


def status() -> dict:
    """Current update status; {"installed": False} until the helper has run once."""
    path = update_dir() / "status.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"installed": False, "available": False, "pending": pending()}
    data["installed"] = True
    data["available"] = int(data.get("behind") or 0) > 0
    data["pending"] = pending()
    if data.get("state") == "running" and time.time() - path.stat().st_mtime > STALE_RUNNING:
        data["state"] = "failed"
        data["message"] = "A frissítés nem fejeződött be, részletek a naplóban."
    return data


def pending() -> str:
    try:
        return (update_dir() / "request").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def request(action: str) -> None:
    if action not in ("check", "apply"):
        raise ValueError(action)
    d = update_dir()
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / ".request.tmp"
    tmp.write_text(action, encoding="utf-8")
    tmp.replace(d / "request")   # atomic, so the path unit never sees a half written file


def log_tail(lines: int = 80) -> str:
    try:
        text = (update_dir() / "update.log").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return "\n".join(text.splitlines()[-lines:])
