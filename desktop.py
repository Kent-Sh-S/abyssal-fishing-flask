"""xppb desktop entry point: local server, persistent data and a browser window."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import signal
import sys
import threading
import webbrowser

from crash_reporting import install_hooks, write_report


def data_directory():
    override = os.environ.get("ABYSS_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "AbyssalFishing"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "AbyssalFishing"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "abyssal-fishing"


def serve(args, folder):
    # Keep startup/import failures inside main's crash-report boundary.
    from flask import got_request_exception, jsonify
    from werkzeug.serving import make_server
    from app import create_app

    folder.mkdir(parents=True, exist_ok=True)
    application = create_app({"INSTANCE_PATH": str(folder),
                              "DATABASE": str(folder / "abyss.sqlite3"),
                              "DESKTOP_MODE": True})
    reports = folder / "crash-reports"

    def request_failed(sender, exception, **extra):
        write_report(type(exception), exception, exception.__traceback__, reports)

    got_request_exception.connect(request_failed, application, weak=False)
    server = make_server("127.0.0.1", args.port, application, threaded=True)
    server.daemon_threads = True

    @application.post("/desktop/quit")
    def quit_desktop():
        # The existing app.before_request enforces the session CSRF token.
        threading.Thread(target=server.shutdown, daemon=True).start()
        return jsonify(ok=True)

    if args.smoke_test:
        with application.test_client() as client:
            for path in ("/login", "/static/game.js", "/static/desktop.js"):
                response = client.get(path)
                status = response.status_code
                response.close()
                if status != 200:
                    raise RuntimeError(f"Desktop asset failed: {path} ({status})")
            if client.post("/desktop/quit").status_code != 403:
                raise RuntimeError("Desktop exit must require CSRF")
        server.server_close()
        return 0

    def stopped(signum, frame):
        raise KeyboardInterrupt

    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGTERM, stopped)
    if not args.no_browser:
        timer = threading.Timer(0.35, webbrowser.open, args=(f"http://localhost:{server.server_port}/",))
        timer.daemon = True
        timer.start()
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return 0


def main(argv=None):
    folder = data_directory()
    reports = folder / "crash-reports"
    install_hooks(reports)
    try:
        # pythonw.exe deliberately has no console and sets these to None.
        # WSGI logging and browser discovery still need valid file objects.
        for name in ("stdout", "stderr"):
            if getattr(sys, name) is None:
                setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))
        parser = argparse.ArgumentParser(description="ABYSSAL Flask desktop")
        parser.add_argument("--port", type=int, default=0)
        parser.add_argument("--no-browser", action="store_true")
        parser.add_argument("--smoke-test", action="store_true")
        args = parser.parse_args(argv)
        return serve(args, folder)
    except KeyboardInterrupt:
        return 0
    except SystemExit as error:
        if error.code not in (None, 0):
            write_report(type(error), error, error.__traceback__, reports)
        return error.code or 0
    except BaseException as error:
        write_report(type(error), error, error.__traceback__, reports)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
