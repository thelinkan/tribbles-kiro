"""Card catalogue repository for read-only access to cards and expansions.

Provides search, single-card lookup, and expansion listing using aiomysql
for async database access.
"""

from dataclasses import dataclass
from typing import List, Optional

import aiomysql


@dataclass
class Card:
    """Represents a card record from the database.

    Attributes:
        card_id: Unique identifier for the card.
        card_name: Display name of the card.
        denomination: Numeric value (1, 10, 100, 1000, 10000, or 100000).
        power_text: The power or ability text on the card.
        card_number: The card's catalogue number within its expansion.
        expansion_id: ID of the expansion this card belongs to.
        image_filename: Filename for the card's image asset.
    """

    card_id: int
    card_name: str
    denomination: int
    power_text: str
    card_number: str
    expansion_id: int
    image_filename: str


@dataclass
class Expansion:
    """Represents an expansion record from the database.

    Attributes:
        expansion_id: Unique identifier for the expansion.
        expansion_name: Display name of the expansion.
        pack_art_filename: Filename for the expansion's pack art image.
        expansion_description: Optional description text for the expansion.
    """

    expansion_id: int
    expansion_name: str
    pack_art_filename: str
    expansion_description: Optional[str]


@dataclass
class CardFilter:
    """Filter parameters for card search queries.

    All fields are optional. When multiple fields are set, all filters
    are applied together (AND logic).

    Attributes:
        denomination: Filter by exact denomination value.
        power_name: Filter by exact power_text match (compound powers are distinct).
        expansion: Filter by expansion_id.
        card_name_substring: Filter by substring match on card_name (case-insensitive).
    """

    denomination: Optional[int] = None
    power_name: Optional[str] = None
    expansion: Optional[int] = None
    card_name_substring: Optional[str] = None


class CardRepository:
    """Read-only repository for the card catalogue.

    Provides search with dynamic filtering, single-card lookup, and
    expansion listing. Uses exact match on power_text to ensure compound
    powers (e.g., "Clone & Reverse") are treated as distinct identities
    from their component powers.
    """

    def __init__(self, pool: aiomysql.Pool):
        """Initialise the card repository with a database connection pool.

        Args:
            pool: An aiomysql connection pool for database access.
        """
        self._pool = pool

    async def search_cards(self, filters: CardFilter) -> List[Card]:
        """Search the card catalogue with optional filters.

        Builds a dynamic SQL query from the supplied filter parameters.
        All filters are combined with AND logic. When no filters are
        supplied, returns all cards.

        Compound powers are treated as distinct identities — searching
        for "Clone" will not return "Clone & Reverse", and vice versa.

        Args:
            filters: A CardFilter with optional search criteria.

        Returns:
            A list of Card objects matching all supplied criteria.
        """
        query = "SELECT card_id, card_name, denomination, power_text, card_number, expansion_id, image_filename FROM cards"
        conditions: List[str] = []
        params: List[object] = []

        if filters.denomination is not None:
            conditions.append("denomination = %s")
            params.append(filters.denomination)

        if filters.power_name is not None:
            # Exact match ensures compound powers are distinct from components
            conditions.append("power_text = %s")
            params.append(filters.power_name)

        if filters.expansion is not None:
            conditions.append("expansion_id = %s")
            params.append(filters.expansion)

        if filters.card_name_substring is not None:
            conditions.append("card_name LIKE %s")
            params.append(f"%{filters.card_name_substring}%")

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY card_id"

        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, params)
                rows = await cur.fetchall()
                return [
                    Card(
                        card_id=row[0],
                        card_name=row[1],
                        denomination=row[2],
                        power_text=row[3],
                        card_number=row[4],
                        expansion_id=row[5],
                        image_filename=row[6],
                    )
                    for row in rows
                ]

    async def get_card(self, card_id: int) -> Optional[Card]:
        """Look up a single card by its ID.

        Args:
            card_id: The unique identifier of the card to retrieve.

        Returns:
            A Card object if found, or None if no card exists with that ID.
        """
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT card_id, card_name, denomination, power_text, "
                    "card_number, expansion_id, image_filename "
                    "FROM cards WHERE card_id = %s",
                    (card_id,),
                )
                row = await cur.fetchone()
                if row is None:
                    return None
                return Card(
                    card_id=row[0],
                    card_name=row[1],
                    denomination=row[2],
                    power_text=row[3],
                    card_number=row[4],
                    expansion_id=row[5],
                    image_filename=row[6],
                )

    async def get_all_expansions(self) -> List[Expansion]:
        """Return all expansion records from the database.

        Expansion names are derived from the database, not hard-coded,
        ensuring new expansions can be added without code changes.

        Returns:
            A list of all Expansion objects in the database.
        """
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT expansion_id, expansion_name, pack_art_filename, "
                    "expansion_description FROM expansions ORDER BY expansion_id"
                )
                rows = await cur.fetchall()
                return [
                    Expansion(
                        expansion_id=row[0],
                        expansion_name=row[1],
                        pack_art_filename=row[2],
                        expansion_description=row[3],
                    )
                    for row in rows
                ]
