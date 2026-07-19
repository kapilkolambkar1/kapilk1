"""
Launcher — entry point for the compiled executable.
Opens the Streamlit GUI in the user's default browser.

When built with PyInstaller this becomes:
  - Windows: ScriptToImage.exe
  - Linux/macOS: ScriptToImage
"""

import os
import sys
import socket
import threading
import time
import webbrowser
from pathlib import Path


def _find_free_port(start: int = 8501) -> int:
    for port in range(start, start + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return start


def _wait_and_open(port: int, delay: float = 2.5) -> None:
    """Wait for Streamlit to start, then open the browser."""
    time.sleep(delay)
    webbrowser.open(f"http://127.0.0.1:{port}")


def _resource_path(relative: str) -> str:
    """Return absolute path — works both normally and inside a PyInstaller bundle."""
    base = getattr(sys, "_MEIPASS", Path(__file__).parent)
    return str(Path(base) / relative)


def main() -> None:
    # Ensure the output directory exists next to the exe
    exe_dir = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
    output_dir = exe_dir / "output"
    output_dir.mkdir(exist_ok=True)

    # Load any .env file next to the executable
    env_file = exe_dir / ".env"
    if env_file.exists():
        from dotenv import load_dotenv
        load_dotenv(env_file)

    port = _find_free_port()

    # Open browser after a short delay
    threading.Thread(target=_wait_and_open, args=(port,), daemon=True).start()

    # Launch Streamlit
    app_path = _resource_path("gui_app.py")

    import streamlit.web.cli as stcli
    sys.argv = [
        "streamlit",
        "run",
        app_path,
        "--server.port", str(port),
        "--server.headless", "true",
        "--browser.gatherUsageStats", "false",
        "--server.fileWatcherType", "none",
    ]
    stcli.main()


if __name__ == "__main__":
    main()
