"""Production entry point for packaged FastAPI (PyInstaller / desktop sidecar).

Listens on 127.0.0.1 only. Paths come from environment variables set by Electron.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="Treningsanalyse backend (desktop)")
    parser.add_argument("--host", default=os.environ.get("BACKEND_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("BACKEND_PORT", "8000")))
    parser.add_argument("--log-level", default=os.environ.get("LOG_LEVEL", "info"))
    args = parser.parse_args()

    # Force loopback in desktop mode — never bind all interfaces.
    host = args.host
    if host in {"0.0.0.0", "::", "[::]"}:
        host = "127.0.0.1"

    os.environ.setdefault("DESKTOP_MODE", "true")
    os.environ.setdefault("SKIP_GARMIN_INIT", "true")

    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    log = logging.getLogger("treningsanalyse.desktop_backend")
    log.info("Starting desktop backend on %s:%s", host, args.port)

    # Ensure Settings are built after env vars (TRAININGSANALYSE_DATA_DIR, etc.) are set.
    import app.config as config_mod

    config_mod.reset_settings_cache()
    config_mod.settings = config_mod.get_settings()

    import uvicorn
    from app.main import app

    uvicorn.run(
        app,
        host=host,
        port=args.port,
        log_level=str(args.log_level).lower(),
        access_log=False,
    )


if __name__ == "__main__":
    # Ensure backend package root is on sys.path when frozen or run as script
    if getattr(sys, "frozen", False):
        # PyInstaller
        pass
    else:
        backend_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if backend_root not in sys.path:
            sys.path.insert(0, backend_root)
    main()
