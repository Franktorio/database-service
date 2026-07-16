# ~/src/scripts/setup_postgres.py

import pathlib
import json
import re
import shutil
import subprocess
import sys

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
	sys.path.insert(0, str(PROJECT_ROOT))

from config.loader import (
	POSTGRESQL_DATABASE_NAME,
	POSTGRESQL_PASSWORD,
	POSTGRESQL_PORT,
	POSTGRESQL_USERNAME,
)
from src.services.logging import log_message

PRINT_PREFIX = "SETUP POSTGRES SCRIPT"

_SERVICE_CONFIG = json.loads(
	(pathlib.Path(__file__).resolve().parents[1] / "config" / "service_config.json").read_text()
)
_SETUP_CONFIG = _SERVICE_CONFIG.get("setup_postgres", {})
COMMAND_SUBPROCESS_TIMEOUT_SECONDS = _SETUP_CONFIG.get("command_subprocess_timeout_seconds", 60)
PROBE_SUBPROCESS_TIMEOUT_SECONDS = _SETUP_CONFIG.get("probe_subprocess_timeout_seconds", 60)

# USAGE (on project root): python3 -m scripts.setup_postgres

DB_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_]+$") # only alphanumeric and underscores for safe CREATE DATABASE execution
ROLE_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


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
			f"Command timed out after {COMMAND_SUBPROCESS_TIMEOUT_SECONDS}s: {' '.join(command)}"
		) from exc


def _require_command(command_name: str) -> None:
	if shutil.which(command_name) is None:
		raise RuntimeError(
			f"Required command '{command_name}' is not available. "
			"This script expects a Debian/Ubuntu environment with apt and systemd."
		)


def _install_postgres_packages() -> None:
	log_message(f"[INFO] [{PRINT_PREFIX}] Installing PostgreSQL packages with sudo.")
	_run(["sudo", "apt-get", "update"])
	_run(["sudo", "apt-get", "install", "-y", "postgresql", "postgresql-contrib"])


def _start_postgres_service() -> None:
	log_message(f"[INFO] [{PRINT_PREFIX}] Enabling and starting PostgreSQL service.")
	_run(["sudo", "systemctl", "enable", "postgresql"])
	_run(["sudo", "systemctl", "start", "postgresql"])


def _restart_postgres_service() -> None:
	log_message(f"[INFO] [{PRINT_PREFIX}] Restarting PostgreSQL service to apply configuration changes.")
	_run(["sudo", "systemctl", "restart", "postgresql"])


def _validate_database_name(db_name: str) -> None:
	if not db_name:
		raise ValueError("POSTGRESQL_DATABASE_NAME is empty in config/.env")
	if DB_NAME_PATTERN.match(db_name) is None:
		raise ValueError(
			"POSTGRESQL_DATABASE_NAME must match [A-Za-z0-9_]+ for safe CREATE DATABASE execution"
		)


def _validate_role_name(role_name: str) -> None:
	if not role_name:
		raise ValueError("POSTGRESQL_USERNAME is empty in config/.env")
	if ROLE_NAME_PATTERN.match(role_name) is None:
		raise ValueError("POSTGRESQL_USERNAME must match [A-Za-z_][A-Za-z0-9_]*")


def _validate_role_password(role_password: str) -> None:
	if role_password == "":
		raise ValueError("POSTGRESQL_PASSWORD is empty in config/.env")


def _sql_literal(value: str) -> str:
	return "'" + value.replace("'", "''") + "'"


def _quoted_ident(value: str) -> str:
	return f'"{value}"'


def _validate_port(port_value: str) -> int:
	try:
		port = int(port_value)
	except ValueError as exc:
		raise ValueError("POSTGRESQL_PORT in config/.env must be an integer") from exc

	if port < 1 or port > 65535:
		raise ValueError("POSTGRESQL_PORT in config/.env must be between 1 and 65535")

	return port


def _get_postgresql_conf_path() -> str:
	result = _run(["sudo", "-u", "postgres", "psql", "-tAc", "SHOW config_file"])
	conf_path = result.stdout.strip()
	if not conf_path:
		raise RuntimeError("Could not determine postgresql.conf path via psql")
	return conf_path


def _set_postgresql_port(port: int) -> None:
	conf_path = _get_postgresql_conf_path()
	log_message(f"[INFO] [{PRINT_PREFIX}] Setting PostgreSQL port to {port} in '{conf_path}'.")

	port_line_pattern = r"^[[:space:]]*#?[[:space:]]*port[[:space:]]*="
	try:
		has_port_line = subprocess.run(
			["sudo", "grep", "-Eq", port_line_pattern, conf_path],
			check=False,
			timeout=PROBE_SUBPROCESS_TIMEOUT_SECONDS,
		).returncode == 0
	except subprocess.TimeoutExpired as exc:
		raise RuntimeError(
			f"Command timed out after {PROBE_SUBPROCESS_TIMEOUT_SECONDS}s: sudo grep -Eq ... {conf_path}"
		) from exc

	if has_port_line:
		_run(
			[
				"sudo",
				"sed",
				"-ri",
				rf"s|{port_line_pattern}.*$|port = {port}|",
				conf_path,
			]
		)
	else:
		_run(["sudo", "sh", "-c", f"printf '\nport = {port}\n' >> '{conf_path}'"])


def _database_exists(db_name: str) -> bool:
	result = _run(
		[
			"sudo",
			"-u",
			"postgres",
			"psql",
			"-tAc",
			f"SELECT 1 FROM pg_database WHERE datname = '{db_name}'",
		]
	)
	return result.stdout.strip() == "1"


def _role_exists(role_name: str) -> bool:
	result = _run(
		[
			"sudo",
			"-u",
			"postgres",
			"psql",
			"-tAc",
			f"SELECT 1 FROM pg_roles WHERE rolname = {_sql_literal(role_name)}",
		]
	)
	return result.stdout.strip() == "1"


def _create_or_update_role(role_name: str, role_password: str) -> None:
	role_ident = _quoted_ident(role_name)
	password_literal = _sql_literal(role_password)

	if _role_exists(role_name):
		log_message(f"[INFO] [{PRINT_PREFIX}] Role '{role_name}' already exists. Updating password.")
		_run(
			[
				"sudo",
				"-u",
				"postgres",
				"psql",
				"-v",
				"ON_ERROR_STOP=1",
				"-c",
				f"ALTER ROLE {role_ident} WITH LOGIN PASSWORD {password_literal}",
			]
		)
		return

	log_message(f"[INFO] [{PRINT_PREFIX}] Creating role '{role_name}'.")
	_run(
		[
			"sudo",
			"-u",
			"postgres",
			"psql",
			"-v",
			"ON_ERROR_STOP=1",
			"-c",
			f"CREATE ROLE {role_ident} WITH LOGIN PASSWORD {password_literal}",
		]
	)
	log_message(f"[INFO] [{PRINT_PREFIX}] Created role '{role_name}'.")


def _create_database_if_needed(db_name: str, owner_name: str) -> None:
	db_ident = _quoted_ident(db_name)
	owner_ident = _quoted_ident(owner_name)

	if _database_exists(db_name):
		log_message(f"[INFO] [{PRINT_PREFIX}] Database '{db_name}' already exists.")
		_run(
			[
				"sudo",
				"-u",
				"postgres",
				"psql",
				"-v",
				"ON_ERROR_STOP=1",
				"-c",
				f"ALTER DATABASE {db_ident} OWNER TO {owner_ident}",
			]
		)
		_run(
			[
				"sudo",
				"-u",
				"postgres",
				"psql",
				"-v",
				"ON_ERROR_STOP=1",
				"-c",
				f"GRANT ALL PRIVILEGES ON DATABASE {db_ident} TO {owner_ident}",
			]
		)
		log_message(f"[INFO] [{PRINT_PREFIX}] Ensured '{owner_name}' owns database '{db_name}'.")
		return

	log_message(f"[INFO] [{PRINT_PREFIX}] Creating database '{db_name}'.")
	_run(
		[
			"sudo",
			"-u",
			"postgres",
			"psql",
			"-v",
			"ON_ERROR_STOP=1",
			"-c",
			f"CREATE DATABASE {db_ident} OWNER {owner_ident}",
		]
	)
	log_message(f"[INFO] [{PRINT_PREFIX}] Created database '{db_name}'.")


def main() -> None:
	log_message(f"[INFO] [{PRINT_PREFIX}] Starting PostgreSQL installation/setup.")

	for command in ("sudo", "apt-get", "systemctl", "psql"):
		_require_command(command)

	validated_port = _validate_port(POSTGRESQL_PORT)
	_validate_database_name(POSTGRESQL_DATABASE_NAME)
	_validate_role_name(POSTGRESQL_USERNAME)
	_validate_role_password(POSTGRESQL_PASSWORD)
	_install_postgres_packages()
	_start_postgres_service()
	_set_postgresql_port(validated_port)
	_restart_postgres_service()
	_create_or_update_role(POSTGRESQL_USERNAME, POSTGRESQL_PASSWORD)
	_create_database_if_needed(POSTGRESQL_DATABASE_NAME, POSTGRESQL_USERNAME)

	log_message(f"[INFO] [{PRINT_PREFIX}] Setup completed successfully.")


if __name__ == "__main__":
	main()

