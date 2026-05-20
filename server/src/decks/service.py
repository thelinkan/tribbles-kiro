"""Deck management service for CRUD operations on player decks.

Provides save, load, copy, and listing operations for decks,
using aiomysql for database access. Follows the Result-style tuple
return pattern: (value, None) on success, (None, DeckError) on failure.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import aiomysql

from models import DeckSummary


class DeckError:
    """Represents a deck operation error with a code and message."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message

    def __repr__(self) -> str:
        return f"DeckError(code={self.code!r}, message={self.message!r})"


@dataclass
class Deck:
    """Full deck data returned by load operations.

    Attributes:
        deck_id: Unique identifier for the deck.
        deck_name: Display name of the deck.
        owner_player_id: Player ID of the deck owner.
        is_public: True if the deck is publicly visible.
        comment_text: Optional comment/description for the deck.
        cards: Dictionary mapping card_id to quantity.
    """

    deck_id: int
    deck_name: str
    owner_player_id: int
    is_public: bool
    comment_text: Optional[str]
    cards: Dict[int, int]  # card_id -> quantity


# Type alias for deck ID
DeckID = int


class DeckService:
    """Handles CRUD operations on player decks.

    Uses aiomysql connection pool for database access. All methods are async.
    Operations that can fail return a Result-style tuple: (value, None) on
    success, or (None, DeckError) on failure.
    """

    def __init__(self, pool: aiomysql.Pool):
        """Initialise the deck service with a database connection pool.

        Args:
            pool: An aiomysql connection pool for database access.
        """
        self._pool = pool

    async def save_deck(self, player_id: int, deck_data: dict) -> DeckID:
        """Save a new deck for the given player.

        Persists the deck record and all card entries. Allows any card count
        (no minimum enforcement at save time).

        Args:
            player_id: The ID of the player who owns this deck.
            deck_data: Dictionary containing:
                - deck_name (str): Name of the deck.
                - is_public (bool): Whether the deck is publicly visible.
                - comment_text (str|None): Optional comment.
                - cards (dict): Mapping of card_id (int) to quantity (int).

        Returns:
            The ID of the newly created deck.
        """
        deck_name = deck_data["deck_name"]
        is_public = deck_data.get("is_public", False)
        comment_text = deck_data.get("comment_text", None)
        cards = deck_data.get("cards", {})

        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                # Insert the deck record
                await cur.execute(
                    "INSERT INTO decks (owner_player_id, deck_name, is_public, comment_text) "
                    "VALUES (%s, %s, %s, %s)",
                    (player_id, deck_name, is_public, comment_text),
                )
                deck_id = cur.lastrowid

                # Insert card entries
                for card_id, quantity in cards.items():
                    await cur.execute(
                        "INSERT INTO deck_cards (deck_id, card_id, quantity) "
                        "VALUES (%s, %s, %s)",
                        (deck_id, int(card_id), quantity),
                    )

                await conn.commit()
                return deck_id

    async def load_deck(
        self, player_id: int, deck_id: int
    ) -> Tuple[Optional[Deck], Optional[DeckError]]:
        """Load a deck by ID if the requesting player has access.

        A player can load a deck if they own it or if the deck is public.

        Args:
            player_id: The ID of the requesting player.
            deck_id: The ID of the deck to load.

        Returns:
            A tuple of (Deck, None) on success, or (None, DeckError) on failure.
        """
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                # Fetch the deck record
                await cur.execute(
                    "SELECT deck_id, owner_player_id, deck_name, is_public, comment_text "
                    "FROM decks WHERE deck_id = %s",
                    (deck_id,),
                )
                row = await cur.fetchone()

                if row is None:
                    return (
                        None,
                        DeckError("not_found", "Deck not found."),
                    )

                d_id, owner_id, deck_name, is_public, comment_text = row

                # Check access: must be owner or deck must be public
                if owner_id != player_id and not is_public:
                    return (
                        None,
                        DeckError(
                            "unauthorised",
                            "You do not have permission to access this deck.",
                        ),
                    )

                # Fetch card entries
                await cur.execute(
                    "SELECT card_id, quantity FROM deck_cards WHERE deck_id = %s",
                    (deck_id,),
                )
                cards_rows = await cur.fetchall()
                cards = {card_id: quantity for card_id, quantity in cards_rows}

                deck = Deck(
                    deck_id=d_id,
                    deck_name=deck_name,
                    owner_player_id=owner_id,
                    is_public=bool(is_public),
                    comment_text=comment_text,
                    cards=cards,
                )
                return (deck, None)

    async def copy_deck(
        self, player_id: int, source_deck_id: int
    ) -> Tuple[Optional[DeckID], Optional[DeckError]]:
        """Copy an existing deck for the requesting player.

        The source deck must be owned by the requesting player or be public.
        Private decks not owned by the requester are rejected.

        Args:
            player_id: The ID of the player requesting the copy.
            source_deck_id: The ID of the deck to copy.

        Returns:
            A tuple of (new_deck_id, None) on success, or (None, DeckError) on failure.
        """
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                # Fetch the source deck record
                await cur.execute(
                    "SELECT deck_id, owner_player_id, deck_name, is_public, comment_text "
                    "FROM decks WHERE deck_id = %s",
                    (source_deck_id,),
                )
                row = await cur.fetchone()

                if row is None:
                    return (
                        None,
                        DeckError("not_found", "Source deck not found."),
                    )

                _, owner_id, deck_name, is_public, comment_text = row

                # Check access: must be owner or deck must be public
                if owner_id != player_id and not is_public:
                    return (
                        None,
                        DeckError(
                            "unauthorised",
                            "You do not have permission to copy this deck.",
                        ),
                    )

                # Create the new deck record for the requesting player
                new_deck_name = f"Copy of {deck_name}"
                await cur.execute(
                    "INSERT INTO decks (owner_player_id, deck_name, is_public, comment_text) "
                    "VALUES (%s, %s, %s, %s)",
                    (player_id, new_deck_name, False, comment_text),
                )
                new_deck_id = cur.lastrowid

                # Copy card entries from source deck
                await cur.execute(
                    "SELECT card_id, quantity FROM deck_cards WHERE deck_id = %s",
                    (source_deck_id,),
                )
                cards_rows = await cur.fetchall()

                for card_id, quantity in cards_rows:
                    await cur.execute(
                        "INSERT INTO deck_cards (deck_id, card_id, quantity) "
                        "VALUES (%s, %s, %s)",
                        (new_deck_id, card_id, quantity),
                    )

                await conn.commit()
                return (new_deck_id, None)

    async def list_decks(self, player_id: int) -> List[DeckSummary]:
        """List all decks owned by the given player.

        Args:
            player_id: The ID of the player whose decks to list.

        Returns:
            A list of DeckSummary objects for the player's decks.
        """
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT d.deck_id, d.deck_name, d.owner_player_id, d.is_public, "
                    "COALESCE(SUM(dc.quantity), 0) as total_card_count "
                    "FROM decks d "
                    "LEFT JOIN deck_cards dc ON d.deck_id = dc.deck_id "
                    "WHERE d.owner_player_id = %s "
                    "GROUP BY d.deck_id, d.deck_name, d.owner_player_id, d.is_public",
                    (player_id,),
                )
                rows = await cur.fetchall()

                return [
                    DeckSummary(
                        deck_id=row[0],
                        deck_name=row[1],
                        owner_player_id=row[2],
                        is_public=bool(row[3]),
                        total_card_count=int(row[4]),
                    )
                    for row in rows
                ]

    async def list_public_decks(self) -> List[DeckSummary]:
        """List all public decks.

        Returns:
            A list of DeckSummary objects for all public decks.
        """
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT d.deck_id, d.deck_name, d.owner_player_id, d.is_public, "
                    "COALESCE(SUM(dc.quantity), 0) as total_card_count "
                    "FROM decks d "
                    "LEFT JOIN deck_cards dc ON d.deck_id = dc.deck_id "
                    "WHERE d.is_public = TRUE "
                    "GROUP BY d.deck_id, d.deck_name, d.owner_player_id, d.is_public",
                )
                rows = await cur.fetchall()

                return [
                    DeckSummary(
                        deck_id=row[0],
                        deck_name=row[1],
                        owner_player_id=row[2],
                        is_public=bool(row[3]),
                        total_card_count=int(row[4]),
                    )
                    for row in rows
                ]
