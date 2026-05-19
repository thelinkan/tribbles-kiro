"""
Seed script for The Trouble with Tribbles expansion.

Independently runnable — inserts The Trouble with Tribbles expansion record
and all its cards into the database.

Usage:
    python seed_trouble_with_tribbles.py --host localhost --port 3306 --user root --password secret --database tribbles
"""

import sys
from pathlib import Path

# Ensure the seeds package is importable when run directly
sys.path.insert(0, str(Path(__file__).parent))

from seed_runner import run_seed


def main() -> None:
    run_seed(
        expansion_name="The Trouble with Tribbles",
        pack_art_filename="trouble_with_tribbles_pack.jpg",
        expansion_description="The second expansion introducing new powers and strategies.",
        data_file="trouble_with_tribbles.json",
    )


if __name__ == "__main__":
    main()
