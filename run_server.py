"""Launcher script starting uvicorn server on 127.0.0.1:8000."""
import os
import sys
import threading
import webbrowser
import uvicorn

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def main() -> None:
    """Start uvicorn server, announce URL, and open browser after short delay."""
    port = int(os.environ.get("PORT", 8000))
    host = "127.0.0.1"
    server_url = f"http://{host}:{port}/"
    print(f"Starting RootCause-QA server at {server_url}")

    def _open_browser() -> None:
        try:
            webbrowser.open(server_url)
        except Exception:
            pass

    threading.Timer(1.2, _open_browser).start()
    uvicorn.run("server.main:app", host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
