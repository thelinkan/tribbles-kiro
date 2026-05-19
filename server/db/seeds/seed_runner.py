"""
Shared seed runner utility for Tribbles expansion seed scripts.

Provides common database connection logic and insert operations used by
each individual expansion seed script.

Usage from an individual seed script:
    from seed_runner import run_seed

    run_seed(
        expansion_name="Base Set",
        pack_art_filename="base_set_pack.jpg",
        expansion_description="The original Tribbles card set.",
        data_file="base_set.json"
    )
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

import aiomysql


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for database connection."""
    parser = argparse.ArgumentParser(
        description="Seed an expansion into the Tribbles database."
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


async def insert_expansion(
    conn: aiomysql.Connection,
    expansion_name: str,
    pack_art_filename: str,
    expansion_description: str,
) -> int:
    """Insert an expansion record and return its expansion_id.

    If the expansion already exists, returns the existing expansion_id.
    """
    async with conn.cursor() as cur:
        # Check if expansion already exists
        await cur.execute(
            "SELECT expansion_id FROM expansions WHERE expansion_name = %s",
            (expansion_name,),
        )
        row = await cur.fetchone()
        if row:
            print(f"[seed] Expansion '{expansion_name}' already exists (id={row[0]}).")
            return row[0]

        # Insert new expansion
        await cur.execute(
            "INSERT INTO expansions (expansion_name, pack_art_filename, expansion_description) "
            "VALUES (%s, %s, %s)",
            (expansion_name, pack_art_filename, expansion_description),
        )
        expansion_id = cur.lastrowid
        print(f"[seed] Inserted expansion '{expansion_name}' (id={expansion_id}).")
        return expansion_id


async def insert_cards(
    conn: aiomysql.Connection,
    expansion_id: int,
    cards: list[dict],
) -> int:
    """Insert card records for an expansion. Returns the number of cards inserted."""
    inserted = 0
    async with conn.cursor() as cur:
        for card in cards:
            await cur.execute(
                "INSERT INTO cards (card_name, denomination, power_text, card_number, expansion_id, image_filename) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (
                    card["card_name"],
                    card["denomination"],
                    card["power_text"],
                    card["card_number"],
                    expansion_id,
                    card["image_filename"],
                ),
            )
            inserted += 1
    return inserted


async def _run_seed_async(
    expansion_name: str,
    pack_art_filename: str,
    expansion_description: str,
    data_file: str,
    args: argparse.Namespace,
) -> None:
    """Core async logic for seeding an expansion."""
    # Resolve data file path relative to the seeds directory
    data_path = Path(__file__).parent / "data" / data_file
    if not data_path.exists():
        print(f"[seed] ERROR: Data file not found: {data_path}")
        sys.exit(1)

    print(f"[seed] Loading card data from {data_path}...")
    with open(data_path, "r", encoding="utf-8") as f:
        cards = json.load(f)

    print(f"[seed] Found {len(cards)} cards for '{expansion_name}'.")

    # Connect to database
    print(f"[seed] Connecting to MariaDB at {args.host}:{args.port}...")
    try:
        conn = await aiomysql.connect(
            host=args.host,
            port=args.port,
            user=args.user,
            password=args.password,
            db=args.database,
        )
    except Exception as e:
        print(f"[seed] ERROR: Could not connect to database: {e}")
        sys.exit(1)

    try:
        # Insert expansion record
        expansion_id = await insert_expansion(
            conn, expansion_name, pack_art_filename, expansion_description
        )

        # Insert card records
        inserted = await insert_cards(conn, expansion_id, cards)
        await conn.commit()

        print(f"[seed] Successfully inserted {inserted} cards for '{expansion_name}'.")
    finally:
        conn.close()


def run_seed(
    expansion_name: str,
    pack_art_filename: str,
    expansion_description: str,
    data_file: str,
) -> None:
    """Entry point for individual seed scripts.

    Parses CLI args, loads the JSON data file, and inserts the expansion
    and its cards into the database.
    """
    args = parse_args()
    asyncio.run(
        _run_seed_async(
            expansion_name=expansion_name,
            pack_art_filename=pack_art_filename,
            expansion_description=expansion_description,
            data_file=data_file,
            args=args,
        )
    )
