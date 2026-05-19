"""
Seed script for the Trials and Tribble-ations expansion.

Independently runnable — inserts the Trials and Tribble-ations expansion
record and all its cards into the database.

Usage:
    python seed_trials_and_tribbleations.py --host localhost --port 3306 --user root --password secret --database tribbles
"""

import sys
from pathlib import Path

# Ensure the seeds package is importable when run directly
sys.path.insert(0, str(Path(__file__).parent))

from seed_runner import run_seed


def main() -> None:
    run_seed(
        expansion_name="Trials and Tribble-ations",
        pack_art_filename="trials_and_tribbleations_pack.jpg",
        expansion_description="The fifth expansion featuring time-themed mechanics.",
        data_file="trials_and_tribbleations.json",
    )


if __name__ == "__main__":
    main()
