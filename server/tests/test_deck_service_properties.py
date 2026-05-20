"""Property-based tests for the Deck_Service.

Uses Hypothesis to verify correctness properties across many random inputs.
Tests use the same FakeCursor/FakeConnection/FakePool pattern as the unit tests
for in-memory testing without a live database.

**Validates: Requirements 3.2, 3.3, 3.4, 3.5, 3.6, 3.7**
"""

import asyncio
import sys
import os

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from decks.service import DeckService, DeckError, Deck


# ---------------------------------------------------------------------------
# Fake DB infrastructure (same pattern as test_deck_service.py)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Hypothesis strategies for generating valid deck inputs
# ---------------------------------------------------------------------------

# Deck names: printable text, 1-50 chars
valid_deck_names = st.text(
    alphabet=st.characters(min_codepoint=32, max_codepoint=126),
    min_size=1,
    max_size=50,
)

# Comment text: either None or printable text up to 200 chars
valid_comments = st.one_of(
    st.none(),
    st.text(
        alphabet=st.characters(min_codepoint=32, max_codepoint=126),
        min_size=0,
        max_size=200,
    ),
)

# Card entries: dict of card_id (positive int) -> quantity (positive int)
valid_cards = st.dictionaries(
    keys=st.integers(min_value=1, max_value=500),
    values=st.integers(min_value=1, max_value=10),
    min_size=0,
    max_size=20,
)

# Player IDs: positive integers
valid_player_ids = st.integers(min_value=1, max_value=10000)

# Full deck data strategy
valid_deck_data = st.fixed_dictionaries({
    "deck_name": valid_deck_names,
    "is_public": st.booleans(),
    "comment_text": valid_comments,
    "cards": valid_cards,
})


# ---------------------------------------------------------------------------
# Property 6: Deck save/load round-trip
# ---------------------------------------------------------------------------

class TestDeckSaveLoadRoundTrip:
    """**Validates: Requirements 3.2, 3.3**

    For any valid deck data (name, public flag, comment, card entries with
    quantities), saving the deck and then loading it should return deck data
    equivalent to the original.
    """

    @given(player_id=valid_player_ids, deck_data=valid_deck_data)
    @settings(max_examples=100, deadline=None)
    def test_save_then_load_returns_equivalent_data(self, player_id, deck_data):
        """Saving a deck and loading it back should return equivalent data."""

        async def _run():
            service = DeckService(FakePool())

            # Save the deck
            deck_id = await service.save_deck(player_id=player_id, deck_data=deck_data)
            assert deck_id is not None

            # Load the deck back
            loaded_deck, error = await service.load_deck(player_id=player_id, deck_id=deck_id)
            assert error is None, f"Load failed unexpectedly: {error}"
            assert loaded_deck is not None

            # Verify all fields match the original data
            assert loaded_deck.deck_id == deck_id
            assert loaded_deck.owner_player_id == player_id
            assert loaded_deck.deck_name == deck_data["deck_name"]
            assert loaded_deck.is_public == deck_data["is_public"]
            assert loaded_deck.comment_text == deck_data["comment_text"]
            assert loaded_deck.cards == deck_data["cards"]

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# Property 7: Public deck access
# ---------------------------------------------------------------------------

class TestPublicDeckAccess:
    """**Validates: Requirements 3.4**

    For any deck marked as public and any authenticated player, loading that
    deck should succeed and return the full deck data.
    """

    @given(
        owner_id=valid_player_ids,
        requester_id=valid_player_ids,
        deck_data=valid_deck_data,
    )
    @settings(max_examples=100, deadline=None)
    def test_public_deck_accessible_by_any_player(self, owner_id, requester_id, deck_data):
        """Any authenticated player should be able to load a public deck."""
        # Force the deck to be public
        deck_data = {**deck_data, "is_public": True}

        async def _run():
            service = DeckService(FakePool())

            # Save a public deck as the owner
            deck_id = await service.save_deck(player_id=owner_id, deck_data=deck_data)

            # Load the deck as a different player (or same player)
            loaded_deck, error = await service.load_deck(player_id=requester_id, deck_id=deck_id)
            assert error is None, f"Public deck load failed: {error}"
            assert loaded_deck is not None

            # Verify full deck data is returned
            assert loaded_deck.deck_id == deck_id
            assert loaded_deck.deck_name == deck_data["deck_name"]
            assert loaded_deck.is_public is True
            assert loaded_deck.comment_text == deck_data["comment_text"]
            assert loaded_deck.cards == deck_data["cards"]

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# Property 8: Deck copy produces identical card entries
# ---------------------------------------------------------------------------

class TestDeckCopyIdenticalCards:
    """**Validates: Requirements 3.5, 3.6**

    For any deck that is either owned by the requesting player or marked public,
    copying it should produce a new deck with a different ID but identical card
    entries and quantities.
    """

    @given(
        owner_id=valid_player_ids,
        requester_id=valid_player_ids,
        deck_data=valid_deck_data,
    )
    @settings(max_examples=100, deadline=None)
    def test_copy_produces_different_id_same_cards(self, owner_id, requester_id, deck_data):
        """Copying an accessible deck produces a new deck with identical cards."""
        # Ensure the requester can access the deck: either they own it or it's public
        if owner_id != requester_id:
            deck_data = {**deck_data, "is_public": True}

        async def _run():
            service = DeckService(FakePool())

            # Save the source deck
            source_id = await service.save_deck(player_id=owner_id, deck_data=deck_data)

            # Copy the deck
            new_id, error = await service.copy_deck(player_id=requester_id, source_deck_id=source_id)
            assert error is None, f"Copy failed unexpectedly: {error}"
            assert new_id is not None
            assert new_id != source_id

            # Load the copy and verify card entries are identical
            copy, load_error = await service.load_deck(player_id=requester_id, deck_id=new_id)
            assert load_error is None
            assert copy is not None
            assert copy.cards == deck_data["cards"]
            assert copy.owner_player_id == requester_id

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# Property 9: Private deck copy denied for non-owner
# ---------------------------------------------------------------------------

class TestPrivateDeckCopyDenied:
    """**Validates: Requirements 3.7**

    For any deck marked as private and any player who is not the owner,
    attempting to copy that deck should return an authorisation error.
    """

    @given(
        owner_id=valid_player_ids,
        requester_id=valid_player_ids,
        deck_data=valid_deck_data,
    )
    @settings(max_examples=100, deadline=None)
    def test_private_deck_copy_by_non_owner_returns_auth_error(self, owner_id, requester_id, deck_data):
        """Copying a private deck as a non-owner should return an authorisation error."""
        # Ensure the requester is NOT the owner
        assume(owner_id != requester_id)
        # Force the deck to be private
        deck_data = {**deck_data, "is_public": False}

        async def _run():
            service = DeckService(FakePool())

            # Save a private deck as the owner
            source_id = await service.save_deck(player_id=owner_id, deck_data=deck_data)

            # Attempt to copy as a non-owner
            new_id, error = await service.copy_deck(player_id=requester_id, source_deck_id=source_id)
            assert new_id is None
            assert error is not None
            assert error.code == "unauthorised"

        asyncio.run(_run())
