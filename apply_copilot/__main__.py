"""Entry point: `python -m apply_copilot` → starts the dashboard server."""
from __future__ import annotations
import argparse
import sys

from .config import SERVER_HOST, SERVER_PORT, ensure_dirs, OPENAI_API_KEY
from .storage import init_db


def main():
    parser = argparse.ArgumentParser(prog="apply_copilot",
                                       description="Auto-apply assistant. Dashboard at http://localhost:8787")
    parser.add_argument("--host", default=SERVER_HOST)
    parser.add_argument("--port", type=int, default=SERVER_PORT)
    parser.add_argument("--init-only", action="store_true",
                        help="Initialize storage and exit (for first-time setup checks)")
    args = parser.parse_args()

    ensure_dirs()
    init_db()

    if args.init_only:
        print(f"Storage initialized at {ensure_dirs.__module__.split('.')[0]}/.")
        sys.exit(0)

    if not OPENAI_API_KEY:
        print("⚠ Warning: OPENAI_API_KEY is not set.")
        print("  Set it before running an autopilot:")
        print("    macOS/Linux:  export OPENAI_API_KEY='sk-...'")
        print("    Windows (PS): $env:OPENAI_API_KEY='sk-...'")
        print()

    import uvicorn
    uvicorn.run("apply_copilot.server.main:app", host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
