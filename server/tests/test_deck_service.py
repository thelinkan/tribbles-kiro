"""Tests for the Deck_Service (save, load, copy, list operations).

Uses an in-memory mock of the aiomysql pool to test deck logic without
requiring a live database connection.
"""

import sys
import os

import pytest

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from decks.service import DeckService, DeckError, Deck
from models import DeckSummary


class FakeCursor:
    """A fake async cursor that stores data in memory for deck operations."""

    def __init__(self, storage: dict):
        self._storage = storage
        self._last_result = None
        self._all_results = []
        self._lastrowid = 0

    @property
    def lastrowid(self):
        return self._lastrowid

    async def execute(self, query: str, args=None):
        query_lower = query.strip().lower()

        if query_lower.startswith("insert into decks"):
            owner_player_id, deck_name, is_public, comment_text = args
            decks = self._storage.setdefault("decks", {})
            new_id = len(decks) + 1
            decks[new_id] = {
                "deck_id": new_id,
                "owner_player_id": owner_player_id,
                "deck_name": deck_name,
                "is_public": is_public,
                "comment_text": comment_text,
            }
            self._lastrowid = new_id

        elif query_lower.startswith("insert into deck_cards"):
            deck_id, card_id, quantity = args
            deck_cards = self._storage.setdefault("deck_cards", [])
            deck_cards.append({
                "deck_id": deck_id,
                "card_id": card_id,
                "quantity": quantity,
            })

        elif query_lower.startswith("select deck_id, owner_player_id, deck_name, is_public, comment_text"):
            deck_id = args[0]
            deck = self._storage.get("decks", {}).get(deck_id)
            if deck:
                self._last_result = (
                    deck["deck_id"],
                    deck["owner_player_id"],
                    deck["deck_name"],
                    deck["is_public"],
                    deck["comment_text"],
                )
            else:
                self._last_result = None

        elif query_lower.startswith("select card_id, quantity from deck_cards"):
            deck_id = args[0]
            deck_cards = self._storage.get("deck_cards", [])
            self._all_results = [
                (dc["card_id"], dc["quantity"])
                for dc in deck_cards
                if dc["deck_id"] == deck_id
            ]

        elif "from decks d" in query_lower and "where d.owner_player_id" in query_lower:
            # list_decks query
            player_id = args[0]
            decks = self._storage.get("decks", {})
            deck_cards = self._storage.get("deck_cards", [])
            results = []
            for d_id, deck in decks.items():
                if deck["owner_player_id"] == player_id:
                    total = sum(
                        dc["quantity"]
                        for dc in deck_cards
                        if dc["deck_id"] == d_id
                    )
                    results.append((
                        deck["deck_id"],
                        deck["deck_name"],
                        deck["owner_player_id"],
                        deck["is_public"],
                        total,
                    ))
            self._all_results = results

        elif "from decks d" in query_lower and "where d.is_public = true" in query_lower:
            # list_public_decks query
            decks = self._storage.get("decks", {})
            deck_cards = self._storage.get("deck_cards", [])
            results = []
            for d_id, deck in decks.items():
                if deck["is_public"]:
                    total = sum(
                        dc["quantity"]
                        for dc in deck_cards
                        if dc["deck_id"] == d_id
                    )
                    results.append((
                        deck["deck_id"],
                        deck["deck_name"],
                        deck["owner_player_id"],
                        deck["is_public"],
                        total,
                    ))
            self._all_results = results

    async def fetchone(self):
        return self._last_result

    async def fetchall(self):
        return self._all_results

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class FakeConnection:
    """A fake async connection wrapping a FakeCursor."""

    def __init__(self, storage: dict):
        self._storage = storage
        self._cursor = FakeCursor(storage)

    def cursor(self):
        return self._cursor

    async def commit(self):
        pass

    async def rollback(self):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class FakePool:
    """A fake aiomysql pool that returns FakeConnections."""

    def __init__(self):
        self._storage: dict = {}

    def acquire(self):
        return FakeConnection(self._storage)


@pytest.fixture
def deck_service():
    """Create a DeckService with a fake in-memory pool."""
    pool = FakePool()
    return DeckService(pool)


class TestSaveDeck:
    """Tests for DeckService.save_deck."""

    @pytest.mark.asyncio
    async def test_save_deck_returns_deck_id(self, deck_service):
        """Requirement 3.2: Save deck persists and associates with authenticated player."""
        deck_data = {
            "deck_name": "My First Deck",
            "is_public": False,
            "comment_text": "A test deck",
            "cards": {1: 4, 2: 3, 3: 2},
        }
        deck_id = await deck_service.save_deck(player_id=1, deck_data=deck_data)
        assert deck_id == 1

    @pytest.mark.asyncio
    async def test_save_deck_persists_deck_record(self, deck_service):
        """Requirement 3.1: Deck record has owner, name, public flag, comment."""
        deck_data = {
            "deck_name": "Test Deck",
            "is_public": True,
            "comment_text": "Some comment",
            "cards": {10: 2},
        }
        deck_id = await deck_service.save_deck(player_id=42, deck_data=deck_data)
        storage = deck_service._pool._storage
        deck = storage["decks"][deck_id]
        assert deck["owner_player_id"] == 42
        assert deck["deck_name"] == "Test Deck"
        assert deck["is_public"] is True
        assert deck["comment_text"] == "Some comment"

    @pytest.mark.asyncio
    async def test_save_deck_persists_card_entries(self, deck_service):
        """Requirement 3.1: Deck has card entries with card ID and quantity."""
        deck_data = {
            "deck_name": "Card Deck",
            "cards": {1: 4, 5: 2, 10: 1},
        }
        deck_id = await deck_service.save_deck(player_id=1, deck_data=deck_data)
        storage = deck_service._pool._storage
        deck_cards = [
            dc for dc in storage["deck_cards"] if dc["deck_id"] == deck_id
        ]
        assert len(deck_cards) == 3
        card_map = {dc["card_id"]: dc["quantity"] for dc in deck_cards}
        assert card_map == {1: 4, 5: 2, 10: 1}

    @pytest.mark.asyncio
    async def test_save_deck_allows_empty_cards(self, deck_service):
        """Requirement 3.10: Save deck allows any card count (including zero)."""
        deck_data = {
            "deck_name": "Empty Deck",
            "cards": {},
        }
        deck_id = await deck_service.save_deck(player_id=1, deck_data=deck_data)
        assert deck_id == 1
        storage = deck_service._pool._storage
        deck_cards = [
            dc for dc in storage.get("deck_cards", []) if dc["deck_id"] == deck_id
        ]
        assert len(deck_cards) == 0

    @pytest.mark.asyncio
    async def test_save_deck_allows_few_cards(self, deck_service):
        """Requirement 3.10: No minimum card count enforcement at save time."""
        deck_data = {
            "deck_name": "Small Deck",
            "cards": {1: 1},  # Only 1 card total
        }
        deck_id = await deck_service.save_deck(player_id=1, deck_data=deck_data)
        assert deck_id == 1

    @pytest.mark.asyncio
    async def test_save_multiple_decks_increments_id(self, deck_service):
        """Multiple saves produce distinct deck IDs."""
        deck_data = {"deck_name": "Deck A", "cards": {}}
        id1 = await deck_service.save_deck(player_id=1, deck_data=deck_data)
        id2 = await deck_service.save_deck(player_id=1, deck_data={"deck_name": "Deck B", "cards": {}})
        assert id1 == 1
        assert id2 == 2


class TestLoadDeck:
    """Tests for DeckService.load_deck."""

    @pytest.mark.asyncio
    async def test_load_own_deck_success(self, deck_service):
        """Requirement 3.3: Load deck returns full data if owned by requesting player."""
        deck_data = {
            "deck_name": "My Deck",
            "is_public": False,
            "comment_text": "Private deck",
            "cards": {1: 4, 2: 3},
        }
        deck_id = await deck_service.save_deck(player_id=1, deck_data=deck_data)
        deck, error = await deck_service.load_deck(player_id=1, deck_id=deck_id)
        assert error is None
        assert deck is not None
        assert deck.deck_id == deck_id
        assert deck.deck_name == "My Deck"
        assert deck.owner_player_id == 1
        assert deck.is_public is False
        assert deck.comment_text == "Private deck"
        assert deck.cards == {1: 4, 2: 3}

    @pytest.mark.asyncio
    async def test_load_public_deck_by_non_owner(self, deck_service):
        """Requirement 3.4: Load deck returns full data if deck is public."""
        deck_data = {
            "deck_name": "Public Deck",
            "is_public": True,
            "comment_text": "Shared",
            "cards": {5: 10},
        }
        deck_id = await deck_service.save_deck(player_id=1, deck_data=deck_data)
        deck, error = await deck_service.load_deck(player_id=99, deck_id=deck_id)
        assert error is None
        assert deck is not None
        assert deck.deck_name == "Public Deck"
        assert deck.cards == {5: 10}

    @pytest.mark.asyncio
    async def test_load_private_deck_by_non_owner_rejected(self, deck_service):
        """Private deck not owned by requester returns authorisation error."""
        deck_data = {
            "deck_name": "Secret Deck",
            "is_public": False,
            "cards": {1: 1},
        }
        deck_id = await deck_service.save_deck(player_id=1, deck_data=deck_data)
        deck, error = await deck_service.load_deck(player_id=99, deck_id=deck_id)
        assert deck is None
        assert error is not None
        assert error.code == "unauthorised"

    @pytest.mark.asyncio
    async def test_load_nonexistent_deck(self, deck_service):
        """Loading a deck that doesn't exist returns not_found error."""
        deck, error = await deck_service.load_deck(player_id=1, deck_id=999)
        assert deck is None
        assert error is not None
        assert error.code == "not_found"


class TestCopyDeck:
    """Tests for DeckService.copy_deck."""

    @pytest.mark.asyncio
    async def test_copy_own_deck_success(self, deck_service):
        """Requirement 3.5: Copy owned deck creates new deck with identical card entries."""
        deck_data = {
            "deck_name": "Original",
            "is_public": False,
            "comment_text": "My deck",
            "cards": {1: 4, 2: 3, 3: 2},
        }
        source_id = await deck_service.save_deck(player_id=1, deck_data=deck_data)
        new_id, error = await deck_service.copy_deck(player_id=1, source_deck_id=source_id)
        assert error is None
        assert new_id is not None
        assert new_id != source_id

        # Verify the copy has identical cards
        copy, _ = await deck_service.load_deck(player_id=1, deck_id=new_id)
        assert copy.cards == {1: 4, 2: 3, 3: 2}
        assert copy.owner_player_id == 1
        assert copy.deck_name == "Copy of Original"

    @pytest.mark.asyncio
    async def test_copy_public_deck_by_non_owner(self, deck_service):
        """Requirement 3.6: Copy public deck creates new deck for requesting player."""
        deck_data = {
            "deck_name": "Shared Deck",
            "is_public": True,
            "cards": {10: 5, 20: 3},
        }
        source_id = await deck_service.save_deck(player_id=1, deck_data=deck_data)
        new_id, error = await deck_service.copy_deck(player_id=2, source_deck_id=source_id)
        assert error is None
        assert new_id is not None

        # Verify the copy belongs to player 2
        copy, _ = await deck_service.load_deck(player_id=2, deck_id=new_id)
        assert copy.owner_player_id == 2
        assert copy.cards == {10: 5, 20: 3}

    @pytest.mark.asyncio
    async def test_copy_private_deck_by_non_owner_rejected(self, deck_service):
        """Requirement 3.7: Copy private deck not owned by requester returns auth error."""
        deck_data = {
            "deck_name": "Private Deck",
            "is_public": False,
            "cards": {1: 1},
        }
        source_id = await deck_service.save_deck(player_id=1, deck_data=deck_data)
        new_id, error = await deck_service.copy_deck(player_id=2, source_deck_id=source_id)
        assert new_id is None
        assert error is not None
        assert error.code == "unauthorised"

    @pytest.mark.asyncio
    async def test_copy_nonexistent_deck(self, deck_service):
        """Copying a deck that doesn't exist returns not_found error."""
        new_id, error = await deck_service.copy_deck(player_id=1, source_deck_id=999)
        assert new_id is None
        assert error is not None
        assert error.code == "not_found"

    @pytest.mark.asyncio
    async def test_copy_deck_is_private_by_default(self, deck_service):
        """Copied decks should be private regardless of source visibility."""
        deck_data = {
            "deck_name": "Public Source",
            "is_public": True,
            "cards": {1: 1},
        }
        source_id = await deck_service.save_deck(player_id=1, deck_data=deck_data)
        new_id, _ = await deck_service.copy_deck(player_id=2, source_deck_id=source_id)
        copy, _ = await deck_service.load_deck(player_id=2, deck_id=new_id)
        assert copy.is_public is False


class TestListDecks:
    """Tests for DeckService.list_decks."""

    @pytest.mark.asyncio
    async def test_list_decks_returns_own_decks(self, deck_service):
        """list_decks returns only decks owned by the specified player."""
        await deck_service.save_deck(player_id=1, deck_data={"deck_name": "Deck A", "cards": {1: 5}})
        await deck_service.save_deck(player_id=1, deck_data={"deck_name": "Deck B", "cards": {2: 3}})
        await deck_service.save_deck(player_id=2, deck_data={"deck_name": "Other", "cards": {3: 1}})

        decks = await deck_service.list_decks(player_id=1)
        assert len(decks) == 2
        names = {d.deck_name for d in decks}
        assert names == {"Deck A", "Deck B"}

    @pytest.mark.asyncio
    async def test_list_decks_returns_deck_summaries(self, deck_service):
        """list_decks returns DeckSummary objects with correct total_card_count."""
        await deck_service.save_deck(
            player_id=1,
            deck_data={"deck_name": "Big Deck", "is_public": True, "cards": {1: 10, 2: 5, 3: 20}},
        )
        decks = await deck_service.list_decks(player_id=1)
        assert len(decks) == 1
        summary = decks[0]
        assert isinstance(summary, DeckSummary)
        assert summary.deck_name == "Big Deck"
        assert summary.owner_player_id == 1
        assert summary.is_public is True
        assert summary.total_card_count == 35

    @pytest.mark.asyncio
    async def test_list_decks_empty_for_new_player(self, deck_service):
        """A player with no decks gets an empty list."""
        decks = await deck_service.list_decks(player_id=99)
        assert decks == []


class TestListPublicDecks:
    """Tests for DeckService.list_public_decks."""

    @pytest.mark.asyncio
    async def test_list_public_decks_returns_only_public(self, deck_service):
        """list_public_decks returns only decks marked as public."""
        await deck_service.save_deck(
            player_id=1,
            deck_data={"deck_name": "Public A", "is_public": True, "cards": {1: 5}},
        )
        await deck_service.save_deck(
            player_id=1,
            deck_data={"deck_name": "Private B", "is_public": False, "cards": {2: 3}},
        )
        await deck_service.save_deck(
            player_id=2,
            deck_data={"deck_name": "Public C", "is_public": True, "cards": {3: 10}},
        )

        decks = await deck_service.list_public_decks()
        assert len(decks) == 2
        names = {d.deck_name for d in decks}
        assert names == {"Public A", "Public C"}

    @pytest.mark.asyncio
    async def test_list_public_decks_includes_card_count(self, deck_service):
        """Public deck summaries include correct total_card_count."""
        await deck_service.save_deck(
            player_id=1,
            deck_data={"deck_name": "Counted", "is_public": True, "cards": {1: 7, 2: 8}},
        )
        decks = await deck_service.list_public_decks()
        assert len(decks) == 1
        assert decks[0].total_card_count == 15

    @pytest.mark.asyncio
    async def test_list_public_decks_empty_when_none_public(self, deck_service):
        """Returns empty list when no public decks exist."""
        await deck_service.save_deck(
            player_id=1,
            deck_data={"deck_name": "Private", "is_public": False, "cards": {1: 1}},
        )
        decks = await deck_service.list_public_decks()
        assert decks == []
