#!/usr/bin/env python3
"""
Launcher for the FTA Editor web UI.

    python3 fta_web/run.py                  # free port, opens a browser
    python3 fta_web/run.py --port 8765      # fixed port
    python3 fta_web/run.py --no-browser     # print the URL, open it yourself
    python3 fta_web/run.py --root ~/trees   # restrict the file sandbox

This is the only supported entry point. It mints the per-launch session token,
hands it to the browser in the bootstrap URL, and starts a single-process
server bound to loopback. See security.py for why each of those matters.

It is also the entry script of the frozen build (build/fta_editor.spec), where
the same flags are spelled ``./fta_editor --port 8765``.
"""
import argparse
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

# Make the bare-name imports below work regardless of how this file was
# invoked (``python3 fta_web/run.py``, an absolute path, or a symlink).
#
# Frozen, ``__file__`` points inside the PyInstaller archive rather than at a
# directory holding sibling modules, so the sys.path entry has to be
# ``sys._MEIPASS``. This one check is open-coded because it runs *before*
# runtime_paths is importable in a source checkout; every other frozen/source
# path decision in the app goes through runtime_paths.py.
if getattr(sys, "frozen", False):
    _FTA_WEB_DIR = str(Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)).resolve())
else:
    _FTA_WEB_DIR = str(Path(__file__).resolve().parent)
if _FTA_WEB_DIR not in sys.path:
    sys.path.insert(0, _FTA_WEB_DIR)

import config  # noqa: E402
import security  # noqa: E402
from app import create_app  # noqa: E402

#: How long the browser-opener waits for the server to accept connections
#: before giving up and opening the URL anyway.
_STARTUP_TIMEOUT_S = 10.0
_STARTUP_POLL_S = 0.05


def _free_port() -> int:
    """Ask the OS for an unused ephemeral port on the loopback interface.

    Bind-and-release: there is a small window in which another process could
    take the port before the server binds it. Acceptable for a desktop tool --
    the failure is a clear "address in use" at startup, not a silent
    misbinding -- and ``--port`` is there when a fixed port is needed.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((config.HOST, 0))
        return sock.getsockname()[1]


def _wait_until_serving(port: int, timeout: float = _STARTUP_TIMEOUT_S) -> bool:
    """Poll the port until the server accepts a connection."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((config.HOST, port), timeout=0.25):
                return True
        except OSError:
            time.sleep(_STARTUP_POLL_S)
    return False


def _open_browser_when_ready(url: str, port: int) -> None:
    """Open the bootstrap URL once the socket is live.

    Opening it before the server is listening gives the user a "connection
    refused" page and a confusing first impression, so wait for the port
    rather than sleeping a fixed interval.
    """

    def _worker():
        if not _wait_until_serving(port):
            print(
                "Server did not come up in time; open the URL above manually.",
                file=sys.stderr,
            )
            return
        try:
            webbrowser.open(url)
        except Exception as exc:  # pragma: no cover - platform dependent
            print("Could not open a browser (%s). Use the URL above." % exc,
                  file=sys.stderr)

    # Daemon thread: it must never keep the process alive after Ctrl-C.
    threading.Thread(target=_worker, name="open-browser", daemon=True).start()


def _resolve_root(raw: str) -> Path:
    root = Path(raw).expanduser().resolve()
    if not root.is_dir():
        raise SystemExit("--root is not a directory: %s" % root)
    return root


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        # Frozen, "python3 fta_web/run.py" is not a command the user can type;
        # --help has to name the executable they actually launched.
        prog=(
            Path(sys.executable).name
            if getattr(sys, "frozen", False)
            else "fta_web/run.py"
        ),
        description="Run the FTA Editor web UI on localhost.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="port to listen on (default: a free ephemeral port)",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="do not open a browser; just print the URL",
    )
    parser.add_argument(
        "--root",
        default=None,
        metavar="DIR",
        help="root directory for the file sandbox (default: your home directory)",
    )
    args = parser.parse_args(argv)
    if args.port is not None and not (0 < args.port < 65536):
        parser.error("--port must be between 1 and 65535")
    return args


def main(argv=None) -> int:
    args = parse_args(argv)

    port = args.port if args.port is not None else _free_port()
    fs_root = _resolve_root(args.root) if args.root else config.DEFAULT_FS_ROOT

    # One token per launch. It is never persisted, so quitting the server
    # invalidates every page that holds it.
    token = security.generate_token()
    app = create_app(token=token, port=port, fs_root=fs_root)

    url = "http://%s:%d/?t=%s" % (config.HOST, port, token)

    # Printed in full, including the token: this is the only copy the user can
    # get if the browser does not open (headless box, SSH, WSL, a locked-down
    # default browser). The terminal is already as trusted as this process.
    print("FTA Editor")
    print("  URL       : %s" % url)
    print("  Sandbox   : %s" % fs_root)
    print("  Bound to  : %s:%d (loopback only)" % (config.HOST, port))
    print("  Auth      : %s header, validated against this launch's token"
          % config.TOKEN_HEADER)
    print("Press Ctrl-C to stop.")
    sys.stdout.flush()

    if not args.no_browser:
        _open_browser_when_ready(url, port)

    try:
        app.run(
            host=config.HOST,  # never 0.0.0.0: the file endpoints are unguarded
                               # against the network, only against the browser.
            port=port,
            debug=False,       # the debugger is an RCE console on a port that
                               # any local page can reach.
            use_reloader=False,  # the reloader forks a child: two processes,
                                 # two copies of the editor state, edits lost
                                 # at random. Never enable it here.
            threaded=True,      # Flask's default. Requests are served
                                # concurrently, so shared editor state must be
                                # mutated under a lock (see state.py).
        )
    except KeyboardInterrupt:  # pragma: no cover - interactive
        print("\nStopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
