"""Local crash reports. Never include environment variables, requests or cookies."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import platform
import sys
import tempfile
import threading
import traceback


def write_report(exc_type, exc_value, exc_tb, directory):
    if issubclass(exc_type, KeyboardInterrupt):
        return None
    if issubclass(exc_type, SystemExit) and exc_value.code in (None, 0):
        return None
    now = datetime.now(timezone.utc)
    name = f"crash-report-{now:%Y-%m-%d-%H-%M-%S.%fZ}.txt"
    text = (f"ABYSSAL Flask desktop crash report\nUTC: {now.isoformat()}\n"
            f"Platform: {platform.platform()}\nPython: {sys.version}\n\n"
            + "".join(traceback.format_exception(exc_type, exc_value, exc_tb)))
    for folder in (Path(directory), Path(tempfile.gettempdir()) / "AbyssalFishing" / "crash-reports"):
        try:
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / name
            with path.open("x", encoding="utf-8") as handle:
                handle.write(text)
            return path
        except OSError:
            continue
    return None


def install_hooks(directory):
    previous = (sys.excepthook, threading.excepthook)

    def main_hook(kind, value, tb):
        write_report(kind, value, tb, directory)

    def thread_hook(args):
        write_report(args.exc_type, args.exc_value, args.exc_traceback, directory)

    sys.excepthook = main_hook
    threading.excepthook = thread_hook
    return previous
