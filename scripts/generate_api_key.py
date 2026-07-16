# ~/src/scripts/generate_api_key.py

import argparse
import asyncio
import sys

from src.api.keys import create_api_key
from src.services.logging import log_message

PRINT_PREFIX = "GENERATE API KEY SCRIPT"

# USAGE (on project root): python3 -m scripts.generate_api_key <permission_level> <rate_limit>

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python3 -m scripts.generate_api_key",
        description="Create and store a new API key.",
    )
    parser.add_argument("level", type=int, help="Permission level (1-4; use 4 for SUPER_ADMIN bootstrap keys)")
    parser.add_argument("rate_limit", type=int, help="Rate limit value (must be > 0)")
    return parser.parse_args()


async def _run() -> None:
    args = _parse_args()

    if args.level <= 0:
        raise ValueError("permission level must be a positive integer")
    if args.rate_limit <= 0:
        raise ValueError("rate_limit must be a positive integer")

    token = await create_api_key(permission_level=args.level, rate_limit=args.rate_limit)

    log_message(f"[INFO] [{PRINT_PREFIX}] API key created successfully.")
    sys.stdout.write(f"{token}\n")


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()

