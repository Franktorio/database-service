# ~/tools/scripts/migrate_db.py

import asyncio
from datetime import datetime

PRINT_PREFIX = "MIGRATION SCRIPT"

# USAGE (on project root): python3 -m tools.scripts.migrate_db

import psycopg2
from psycopg2 import sql
from psycopg2.extras import execute_batch
from sqlalchemy.ext.asyncio import create_async_engine

from config.loader import (
	POSTGRESQL_DATABASE_NAME,
	POSTGRESQL_HOST,
	POSTGRESQL_PASSWORD,
	POSTGRESQL_PORT,
	POSTGRESQL_USERNAME
)
from src.models.base import Base
import src.models.tables # Unused but here to register the tables to the base class
from src.services.system.logging import log_message

CHUNK_SIZE = 1000


def _connect(dbname: str, *, autocommit: bool = False):
	conn = psycopg2.connect(
		dbname=dbname,
		user=POSTGRESQL_USERNAME,
		password=POSTGRESQL_PASSWORD,
		host=POSTGRESQL_HOST,
		port=POSTGRESQL_PORT,
	)
	conn.autocommit = autocommit
	return conn


def _list_public_tables(conn) -> list[str]:
	with conn.cursor() as cursor:
		cursor.execute(
			"""
			SELECT table_name
			FROM information_schema.tables
			WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
			ORDER BY table_name
			"""
		)
		return [row[0] for row in cursor.fetchall()]


def _table_columns(conn, table_name: str) -> dict[str, tuple[str, str]]:
	with conn.cursor() as cursor:
		cursor.execute(
			"""
			SELECT column_name, data_type, udt_name
			FROM information_schema.columns
			WHERE table_schema = 'public' AND table_name = %s
			ORDER BY ordinal_position
			""",
			(table_name,),
		)
		return {row[0]: (row[1], row[2]) for row in cursor.fetchall()}


async def _create_schema_for_database(db_name: str) -> None:
	temp_url = (
		"postgresql+asyncpg://"
		f"{POSTGRESQL_USERNAME}:{POSTGRESQL_PASSWORD}"
		f"@{POSTGRESQL_HOST}:{POSTGRESQL_PORT}/{db_name}"
	)
	engine = create_async_engine(temp_url, echo=False)
	try:
		async with engine.begin() as conn:
			await conn.run_sync(Base.metadata.create_all)
	finally:
		await engine.dispose()


def _copy_table_rows(source_conn, target_conn, table_name: str) -> tuple[int, list[str]]:
	source_cols = _table_columns(source_conn, table_name)
	target_cols = _table_columns(target_conn, table_name)

	compatible_columns: list[str] = []
	for col_name, target_type in target_cols.items():
		source_type = source_cols.get(col_name)
		if source_type is not None and source_type == target_type:
			compatible_columns.append(col_name)

	if not compatible_columns:
		return 0, []

	total_rows = 0
	select_query = sql.SQL("SELECT {} FROM {}.{}").format(
		sql.SQL(", ").join(sql.Identifier(col) for col in compatible_columns),
		sql.Identifier("public"),
		sql.Identifier(table_name),
	)
	insert_query = sql.SQL("INSERT INTO {}.{} ({}) VALUES ({})").format(
		sql.Identifier("public"),
		sql.Identifier(table_name),
		sql.SQL(", ").join(sql.Identifier(col) for col in compatible_columns),
		sql.SQL(", ").join(sql.Placeholder() for _ in compatible_columns),
	)

	with source_conn.cursor(name=f"migration_{table_name}") as source_cursor:
		source_cursor.itersize = CHUNK_SIZE
		source_cursor.execute(select_query)

		with target_conn.cursor() as target_cursor:
			while True:
				rows = source_cursor.fetchmany(CHUNK_SIZE)
				if not rows:
					break
				execute_batch(target_cursor, insert_query.as_string(target_conn), rows, page_size=CHUNK_SIZE)
				total_rows += len(rows)

	return total_rows, compatible_columns


def _terminate_connections(admin_conn, db_name: str) -> None:
	with admin_conn.cursor() as cursor:
		cursor.execute(
			"""
			SELECT pg_terminate_backend(pid)
			FROM pg_stat_activity
			WHERE datname = %s
			  AND pid <> pg_backend_pid()
			""",
			(db_name,),
		)


def main() -> None:
	timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
	source_db = POSTGRESQL_DATABASE_NAME
	temp_db = f"{source_db}_tmp_migration_{timestamp}"
	backup_db = f"{source_db}_pre_migration_{timestamp}"

	log_message(f"[INFO] [{PRINT_PREFIX}] Starting migration for database '{source_db}'.")
	log_message(f"[DEBUG] [{PRINT_PREFIX}] Temporary database will be '{temp_db}'.")

	admin_conn = _connect("postgres", autocommit=True)
	source_conn = None
	target_conn = None

	try:
		with admin_conn.cursor() as cursor:
			cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(temp_db)))
		log_message(f"[INFO] [{PRINT_PREFIX}] Created temporary database '{temp_db}'.")

		asyncio.run(_create_schema_for_database(temp_db))
		log_message(f"[INFO] [{PRINT_PREFIX}] Created latest schema in temporary database.")

		source_conn = _connect(source_db)
		target_conn = _connect(temp_db)

		with target_conn.cursor() as target_cursor:
			target_cursor.execute("SET session_replication_role = replica")

		source_tables = set(_list_public_tables(source_conn))
		target_tables = set(_list_public_tables(target_conn))
		common_tables = sorted(source_tables & target_tables)
		log_message(f"[INFO] [{PRINT_PREFIX}] Found {len(common_tables)} table(s) to evaluate for migration.")

		migrated_tables = 0
		total_rows = 0
		for table_name in common_tables:
			row_count, cols = _copy_table_rows(source_conn, target_conn, table_name)
			if cols:
				migrated_tables += 1
				total_rows += row_count
				log_message(
					f"[INFO] [{PRINT_PREFIX}] Migrated {row_count} row(s) from table '{table_name}' "
					f"using {len(cols)} compatible column(s)."
				)
			else:
				log_message(
					f"[WARNING] [{PRINT_PREFIX}] Skipped data copy for table '{table_name}'; "
					"no compatible columns found."
				)

		with target_conn.cursor() as target_cursor:
			target_cursor.execute("SET session_replication_role = DEFAULT")

		target_conn.commit()
		source_conn.close()
		target_conn.close()
		source_conn = None
		target_conn = None

		_terminate_connections(admin_conn, source_db)
		_terminate_connections(admin_conn, temp_db)

		with admin_conn.cursor() as cursor:
			cursor.execute(
				sql.SQL("ALTER DATABASE {} RENAME TO {}").format(
					sql.Identifier(source_db), sql.Identifier(backup_db)
				)
			)
			cursor.execute(
				sql.SQL("ALTER DATABASE {} RENAME TO {}").format(
					sql.Identifier(temp_db), sql.Identifier(source_db)
				)
			)

		log_message(f"[INFO] [{PRINT_PREFIX}] Migration swap complete.")
		log_message(f"[INFO] [{PRINT_PREFIX}] Previous database kept as '{backup_db}'.")
		log_message(
			f"[INFO] [{PRINT_PREFIX}] Migration summary: {migrated_tables} table(s), "
			f"{total_rows} total row(s) copied."
		)

	except Exception as exc:
		log_message(f"[ERROR] [{PRINT_PREFIX}] Migration failed: {exc}")

		if target_conn is not None:
			target_conn.rollback()
			target_conn.close()
		if source_conn is not None:
			source_conn.close()

		try:
			_terminate_connections(admin_conn, temp_db)
			with admin_conn.cursor() as cursor:
				cursor.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(temp_db)))
			log_message(f"[INFO] [{PRINT_PREFIX}] Removed temporary database '{temp_db}'.")
		except Exception as cleanup_exc:
			log_message(f"[WARNING] [{PRINT_PREFIX}] Cleanup failed for temporary DB '{temp_db}': {cleanup_exc}")

		raise
	finally:
		admin_conn.close()


if __name__ == "__main__":
	main()

