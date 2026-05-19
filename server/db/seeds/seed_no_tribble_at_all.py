"""
Seed script for the No Tribble at All expansion.

Independently runnable — inserts the No Tribble at All expansion record
and all its cards into the database.

Usage:
    python seed_no_tribble_at_all.py --host localhost --port 3306 --user root --password secret --database tribbles
"""

import sys
from pathlib import Path

# Ensure the seeds package is importable when run directly
sys.path.insert(0, str(Path(__file__).parent))

from seed_runner import run_seed


def main() -> None:
    run_seed(
        expansion_name="No Tribble at All",
        pack_art_filename="no_tribble_at_all_pack.jpg",
        expansion_description="The fourth expansion with advanced power combinations.",
        data_file="no_tribble_at_all.json",
    )


if __name__ == "__main__":
    main()
