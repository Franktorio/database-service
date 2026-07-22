# ~/src/scripts/setup_redis.py
# This script is intended to be run in a Debian/Ubuntu environment with apt and systemd.
# It sets up a Redis server with the specified configuration.

import pathlib
import json
import subprocess
import sys

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
	sys.path.insert(0, str(PROJECT_ROOT))

from config.loader import (
    REDIS_HOST,
    REDIS_PORT,
    REDIS_PASSWORD,
)
from src.services.logging import log_message

PRINT_PREFIX = "SETUP REDIS SCRIPT"

_SERVICE_CONFIG = json.loads(
    (
        pathlib.Path(__file__).resolve().parents[1]
        / "config"
        / "service_config.json"
    ).read_text()
)

_SETUP_CONFIG = _SERVICE_CONFIG.get("setup_redis", {})

COMMAND_SUBPROCESS_TIMEOUT_SECONDS = _SETUP_CONFIG.get(
    "command_subprocess_timeout_seconds",
    60,
)

PROBE_SUBPROCESS_TIMEOUT_SECONDS = _SETUP_CONFIG.get(
    "probe_subprocess_timeout_seconds",
    30,
)

REDIS_CONF_PATH = "/etc/redis/redis.conf"
PORT_LINE_PATTERN = r"^[[:space:]]*#?[[:space:]]*port[[:space:]]*="


def _run(command: list[str]) -> subprocess.CompletedProcess:
    log_message(f"[DEBUG] [{PRINT_PREFIX}] Running command: {' '.join(command)}")

    try:
        return subprocess.run(
            command,
            check=True,
            text=True,
            capture_output=True,
            timeout=COMMAND_SUBPROCESS_TIMEOUT_SECONDS,
        )

    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"Command timed out after "
            f"{COMMAND_SUBPROCESS_TIMEOUT_SECONDS}s: "
            f"{' '.join(command)}"
        ) from exc


def _install_redis_packages() -> None:
    log_message(f"[INFO] [{PRINT_PREFIX}] Installing Redis packages.")

    _run(["sudo", "apt-get", "update"])

    _run(
        [
            "sudo",
            "apt-get",
            "install",
            "-y",
            "redis-server",
        ]
    )


def _start_redis_service() -> None:
    log_message(f"[INFO] [{PRINT_PREFIX}] Enabling and starting Redis service.")

    _run(["sudo", "systemctl", "enable", "redis-server"])
    _run(["sudo", "systemctl", "start", "redis-server"])
    

def _configure_redis() -> None:
    log_message(f"[INFO] [{PRINT_PREFIX}] Configuring Redis server.")

    _run([
        "sudo",
        "sed",
        "-ri",
        f"s|^#?\\s*port\\s+.*$|port {REDIS_PORT}|",
        REDIS_CONF_PATH,
    ])
    
    if not REDIS_PASSWORD:
        raise RuntimeError("REDIS_PASSWORD is not set. Please set it in config/.env.")

    _run([
        "sudo",
        "sed",
        "-ri",
        f"s|^#?\\s*requirepass\\s+.*$|requirepass {REDIS_PASSWORD}|",
        REDIS_CONF_PATH,
    ])
        

def _restart_redis_service() -> None:
    log_message(f"[INFO] [{PRINT_PREFIX}] Restarting Redis service to apply configuration changes.")

    _run(["sudo", "systemctl", "restart", "redis-server"])
    

def _verify_redis_service() -> None:
    log_message(f"[INFO] [{PRINT_PREFIX}] Verifying Redis service status.")

    command = ["redis-cli", "-h", REDIS_HOST, "-p", str(REDIS_PORT), "-a", REDIS_PASSWORD, "PING"]
    result = _run(command)
    if result.stdout.strip() != "PONG":
        raise RuntimeError("Failed to verify Redis service.")
    

def main() -> None:
    log_message(f"[INFO] [{PRINT_PREFIX}] Starting Redis setup script.")

    _install_redis_packages()
    _start_redis_service()
    _configure_redis()
    _restart_redis_service()
    _verify_redis_service()

    log_message(f"[INFO] [{PRINT_PREFIX}] Redis setup script completed successfully.")
    
if __name__ == "__main__":
    main()