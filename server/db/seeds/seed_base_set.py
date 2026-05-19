"""
Seed script for the Base Set expansion.

Independently runnable — inserts the Base Set expansion record and all
its cards into the database.

Usage:
    python seed_base_set.py --host localhost --port 3306 --user root --password secret --database tribbles
"""

import sys
from pathlib import Path

# Ensure the seeds package is importable when run directly
sys.path.insert(0, str(Path(__file__).parent))

from seed_runner import run_seed


def main() -> None:
    run_seed(
        expansion_name="Base Set",
        pack_art_filename="base_set_pack.jpg",
        expansion_description="The original Tribbles card set featuring core game mechanics.",
        data_file="base_set.json",
    )


if __name__ == "__main__":
    main()
