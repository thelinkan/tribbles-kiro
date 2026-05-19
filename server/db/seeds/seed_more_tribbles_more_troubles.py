"""
Seed script for the More Tribbles More Troubles expansion.

Independently runnable — inserts the More Tribbles More Troubles expansion
record and all its cards into the database.

Usage:
    python seed_more_tribbles_more_troubles.py --host localhost --port 3306 --user root --password secret --database tribbles
"""

import sys
from pathlib import Path

# Ensure the seeds package is importable when run directly
sys.path.insert(0, str(Path(__file__).parent))

from seed_runner import run_seed


def main() -> None:
    run_seed(
        expansion_name="More Tribbles More Troubles",
        pack_art_filename="more_tribbles_more_troubles_pack.jpg",
        expansion_description="The third expansion adding more complex card interactions.",
        data_file="more_tribbles_more_troubles.json",
    )


if __name__ == "__main__":
    main()
