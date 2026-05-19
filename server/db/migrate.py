"""
Database migration script for Tribbles Multiplayer Game.

Applies the schema.sql to a MariaDB instance. Accepts connection parameters
via command-line arguments or environment variables.

Usage:
    python migrate.py --host localhost --port 3306 --user root --password secret --database tribbles

Environment variables (used as fallbacks):
    DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME
"""

import argparse
import os
import sys
from pathlib import Path

import aiomysql
import asyncio


SCHEMA_FILE = Path(__file__).parent / "schema.sql"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply Tribbles database schema to a MariaDB instance."
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("DB_HOST", "localhost"),
        help="Database host (default: localhost or DB_HOST env var)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("DB_PORT", "3306")),
        help="Database port (default: 3306 or DB_PORT env var)",
    )
    parser.add_argument(
        "--user",
        default=os.environ.get("DB_USER", "root"),
        help="Database user (default: root or DB_USER env var)",
    )
    parser.add_argument(
        "--password",
        default=os.environ.get("DB_PASSWORD", ""),
        help="Database password (default: empty or DB_PASSWORD env var)",
    )
    parser.add_argument(
        "--database",
        default=os.environ.get("DB_NAME", "tribbles"),
        help="Database name (default: tribbles or DB_NAME env var)",
    )
    return parser.parse_args()


async def run_migration(
    host: str, port: int, user: str, password: str, database: str
) -> None:
    """Read schema.sql and execute each statement against the database."""
    print(f"[migrate] Connecting to MariaDB at {host}:{port} as '{user}'...")

    # First connect without a database to ensure the database exists
    try:
        conn = await aiomysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
        )
    except Exception as e:
        print(f"[migrate] ERROR: Could not connect to MariaDB: {e}")
        sys.exit(1)

    try:
        async with conn.cursor() as cur:
            print(f"[migrate] Ensuring database '{database}' exists...")
            await cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{database}` "
                f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        await conn.commit()
    finally:
        conn.close()

    # Now connect to the target database and apply schema
    try:
        conn = await aiomysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            db=database,
        )
    except Exception as e:
        print(f"[migrate] ERROR: Could not connect to database '{database}': {e}")
        sys.exit(1)

    try:
        print(f"[migrate] Reading schema from {SCHEMA_FILE}...")
        if not SCHEMA_FILE.exists():
            print(f"[migrate] ERROR: Schema file not found: {SCHEMA_FILE}")
            sys.exit(1)

        schema_sql = SCHEMA_FILE.read_text(encoding="utf-8")

        # Split on semicolons to get individual statements
        statements = [
            stmt.strip()
            for stmt in schema_sql.split(";")
            if stmt.strip() and not stmt.strip().startswith("--")
        ]

        print(f"[migrate] Applying {len(statements)} SQL statements...")

        async with conn.cursor() as cur:
            for i, statement in enumerate(statements, 1):
                # Skip pure comment blocks
                lines = [
                    line
                    for line in statement.split("\n")
                    if line.strip() and not line.strip().startswith("--")
                ]
                if not lines:
                    continue

                try:
                    await cur.execute(statement)
                    print(f"[migrate]   ({i}/{len(statements)}) OK")
                except Exception as e:
                    error_msg = str(e)
                    # Handle "already exists" gracefully
                    if "already exists" in error_msg.lower() or "1050" in error_msg:
                        print(
                            f"[migrate]   ({i}/{len(statements)}) "
                            f"SKIPPED (already exists)"
                        )
                    elif "duplicate" in error_msg.lower() or "1061" in error_msg:
                        print(
                            f"[migrate]   ({i}/{len(statements)}) "
                            f"SKIPPED (duplicate key/index)"
                        )
                    else:
                        print(
                            f"[migrate]   ({i}/{len(statements)}) "
                            f"ERROR: {e}"
                        )
                        raise

        await conn.commit()
        print("[migrate] Schema migration completed successfully.")

    finally:
        conn.close()


def main() -> None:
    args = parse_args()
    asyncio.run(
        run_migration(
            host=args.host,
            port=args.port,
            user=args.user,
            password=args.password,
            database=args.database,
        )
    )


if __name__ == "__main__":
    main()
