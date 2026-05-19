"""
Seed script for the Nothing But Tribble expansion.

Independently runnable — inserts the Nothing But Tribble expansion record
and all its cards into the database.

Usage:
    python seed_nothing_but_tribble.py --host localhost --port 3306 --user root --password secret --database tribbles
"""

import sys
from pathlib import Path

# Ensure the seeds package is importable when run directly
sys.path.insert(0, str(Path(__file__).parent))

from seed_runner import run_seed


def main() -> None:
    run_seed(
        expansion_name="Nothing But Tribble",
        pack_art_filename="nothing_but_tribble_pack.jpg",
        expansion_description="The sixth expansion completing the Tribbles card game collection.",
        data_file="nothing_but_tribble.json",
    )


if __name__ == "__main__":
    main()
