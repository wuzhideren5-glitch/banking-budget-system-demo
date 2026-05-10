#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Banking Budget backend with a Python version check.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8003)
    parser.add_argument("--reload", action="store_true")
    return parser.parse_args()


def main() -> int:
    if sys.version_info < (3, 10):
        version = ".".join(str(part) for part in sys.version_info[:3])
        print(
            f"Python {version} is not supported. Please use Python 3.10+ to run the backend.",
            file=sys.stderr,
        )
        return 1

    args = parse_args()

    import uvicorn

    uvicorn.run("app.main:app", host=args.host, port=args.port, reload=args.reload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
