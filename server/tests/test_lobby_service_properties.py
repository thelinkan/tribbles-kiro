"""Property-based tests for the Lobby_Service.

Uses Hypothesis to verify correctness properties across many random inputs.
Tests use the same FakeCursor/FakeConnection/FakePool pattern as the unit tests
for in-memory testing without a live database.

**Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.6, 4.9, 4.10**
"""

import asyncio
import sys
import os

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lobby.service import LobbyService, LobbyError


# ---------------------------------------------------------------------------
# Fake DB infrastructure (same pattern as test_lobby_service.py)
# ---------------------------------------------------------------------------


class FakeCursor:
    """A fake async cursor that stores deck card data in memory."""

    def __init__(self, storage: dict):
        self._storage = storage
        self._last_result = None

    async def execute(self, query: str, args=None):
        query_lower = query.strip().lower()

        if "sum(quantity)" in query_lower and "deck_cards" in query_lower:
            deck_id = args[0]
            deck_cards = self._storage.get("deck_cards", {})
            total = deck_cards.get(deck_id, 0)
            self._last_result = (total,)

    async def fetchone(self):
        return self._last_result

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

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class FakePool:
    """A fake aiomysql pool that returns FakeConnections."""

    def __init__(self, deck_cards: dict = None):
        """
        Args:
            deck_cards: Mapping of deck_id -> total card count.
        """
        self._storage: dict = {"deck_cards": deck_cards or {}}

    def acquire(self):
        return FakeConnection(self._storage)


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Valid player counts for game creation (4-8 inclusive)
valid_player_counts = st.integers(min_value=4, max_value=8)

# Player IDs: positive integers
valid_player_ids = st.integers(min_value=1, max_value=10000)

# Deck IDs: positive integers
valid_deck_ids = st.integers(min_value=1, max_value=100)

# Valid deck card counts (>= 35)
valid_deck_card_counts = st.integers(min_value=35, max_value=200)

# Invalid deck card counts (< 35)
invalid_deck_card_counts = st.integers(min_value=0, max_value=34)


# ---------------------------------------------------------------------------
# Property 10: Game session creation with valid player count
# ---------------------------------------------------------------------------


class TestGameSessionCreation:
    """**Validates: Requirements 4.1**

    For any player count between 4 and 8 inclusive and a valid deck ID,
    creating a game session should succeed and produce a session in the
    waiting state with the specified player count.
    """

    @given(
        player_id=valid_player_ids,
        deck_id=valid_deck_ids,
        player_count=valid_player_counts,
        card_count=valid_deck_card_counts,
    )
    @settings(max_examples=100, deadline=None)
    def test_create_game_succeeds_with_valid_inputs(
        self, player_id, deck_id, player_count, card_count
    ):
        """Creating a game with valid player count and valid deck should succeed
        and produce a session in the waiting state."""

        async def _run():
            pool = FakePool(deck_cards={deck_id: card_count})
            service = LobbyService(pool)

            session_id, error = await service.create_game(
                player_id=player_id, deck_id=deck_id, player_count=player_count
            )

            # Should succeed
            assert error is None, f"create_game failed unexpectedly: {error}"
            assert session_id is not None
            assert isinstance(session_id, str)
            assert len(session_id) > 0

            # Session should be in waiting state with specified player count
            waiting = await service.list_waiting_games()
            assert len(waiting) == 1
            assert waiting[0].session_id == session_id
            assert waiting[0].status == "waiting"
            assert waiting[0].player_count == player_count
            assert waiting[0].current_player_count == 1  # creator is first player

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# Property 11: Join game adds player when session is waiting and not full
# ---------------------------------------------------------------------------


class TestJoinGameAddsPlayer:
    """**Validates: Requirements 4.2**

    For any game session in the waiting state with fewer human players than
    the total player count, a join request from a new player with a valid
    deck should succeed and increment the human player count by one.
    """

    @given(
        creator_id=valid_player_ids,
        joiner_id=valid_player_ids,
        creator_deck_id=valid_deck_ids,
        joiner_deck_id=valid_deck_ids,
        player_count=valid_player_counts,
        creator_card_count=valid_deck_card_counts,
        joiner_card_count=valid_deck_card_counts,
    )
    @settings(max_examples=100, deadline=None)
    def test_join_game_increments_player_count(
        self,
        creator_id,
        joiner_id,
        creator_deck_id,
        joiner_deck_id,
        player_count,
        creator_card_count,
        joiner_card_count,
    ):
        """Joining a waiting, non-full session should succeed and increment
        the human player count by one."""
        # Ensure joiner is a different player than creator
        assume(creator_id != joiner_id)

        async def _run():
            pool = FakePool(
                deck_cards={
                    creator_deck_id: creator_card_count,
                    joiner_deck_id: joiner_card_count,
                }
            )
            service = LobbyService(pool)

            # Create a game
            session_id, _ = await service.create_game(
                player_id=creator_id,
                deck_id=creator_deck_id,
                player_count=player_count,
            )
            assert session_id is not None

            # Get initial player count
            waiting_before = await service.list_waiting_games()
            count_before = waiting_before[0].current_player_count

            # Join the game
            _, error = await service.join_game(
                player_id=joiner_id,
                deck_id=joiner_deck_id,
                session_id=session_id,
            )

            # Should succeed
            assert error is None, f"join_game failed unexpectedly: {error}"

            # Player count should have incremented by 1
            waiting_after = await service.list_waiting_games()
            assert len(waiting_after) == 1
            assert waiting_after[0].current_player_count == count_before + 1

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# Property 12: Join game rejected for non-waiting or full session
# ---------------------------------------------------------------------------


class TestJoinGameRejected:
    """**Validates: Requirements 4.3, 4.4**

    For any game session that is either not in the waiting state or already
    at full human capacity, a join request should return an appropriate error.
    """

    @given(
        creator_id=valid_player_ids,
        player_count=valid_player_counts,
        card_count=valid_deck_card_counts,
    )
    @settings(max_examples=100, deadline=None)
    def test_join_rejected_when_session_not_waiting(
        self, creator_id, player_count, card_count
    ):
        """Joining a session that is not in the waiting state should return an error."""

        async def _run():
            deck_id = 1
            pool = FakePool(deck_cards={deck_id: card_count})
            service = LobbyService(pool)

            # Create and start a game (transitions to active)
            session_id, _ = await service.create_game(
                player_id=creator_id, deck_id=deck_id, player_count=player_count
            )
            await service.start_game(player_id=creator_id, session_id=session_id)

            # Attempt to join the now-active session
            new_player_id = creator_id + 1
            _, error = await service.join_game(
                player_id=new_player_id, deck_id=deck_id, session_id=session_id
            )

            assert error is not None
            assert error.code == "game_already_started"

        asyncio.run(_run())

    @given(
        creator_id=valid_player_ids,
        card_count=valid_deck_card_counts,
    )
    @settings(max_examples=100, deadline=None)
    def test_join_rejected_when_session_full(self, creator_id, card_count):
        """Joining a session that is already at full human capacity should return an error."""

        async def _run():
            deck_id = 1
            player_count = 4  # Use minimum to make filling easier
            pool = FakePool(deck_cards={deck_id: card_count})
            service = LobbyService(pool)

            # Create a game with player_count=4
            session_id, _ = await service.create_game(
                player_id=creator_id, deck_id=deck_id, player_count=player_count
            )

            # Fill remaining seats with human players
            for i in range(1, player_count):
                joiner_id = creator_id + i
                _, join_error = await service.join_game(
                    player_id=joiner_id, deck_id=deck_id, session_id=session_id
                )
                assert join_error is None

            # Session is now full — attempt to join with one more player
            overflow_player_id = creator_id + player_count
            _, error = await service.join_game(
                player_id=overflow_player_id, deck_id=deck_id, session_id=session_id
            )

            assert error is not None
            assert error.code == "session_full"

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# Property 13: Start game fills remaining seats with AI
# ---------------------------------------------------------------------------


class TestStartGameFillsAI:
    """**Validates: Requirements 4.6**

    For any game session with N human players joined (where N ≤ total player
    count), starting the game should add exactly (total - N) computer-controlled
    players and transition the session to active state.
    """

    @given(
        creator_id=valid_player_ids,
        player_count=valid_player_counts,
        num_joiners=st.integers(min_value=0, max_value=7),
        card_count=valid_deck_card_counts,
    )
    @settings(max_examples=100, deadline=None)
    def test_start_game_fills_ai_and_transitions_to_active(
        self, creator_id, player_count, num_joiners, card_count
    ):
        """Starting a game should fill remaining seats with AI players (negative IDs)
        and transition the session to active state."""
        # Ensure num_joiners doesn't exceed available seats (player_count - 1 for creator)
        assume(num_joiners < player_count)

        async def _run():
            deck_id = 1
            pool = FakePool(deck_cards={deck_id: card_count})
            service = LobbyService(pool)

            # Create a game
            session_id, _ = await service.create_game(
                player_id=creator_id, deck_id=deck_id, player_count=player_count
            )

            # Add joiners
            for i in range(num_joiners):
                joiner_id = creator_id + i + 1
                await service.join_game(
                    player_id=joiner_id, deck_id=deck_id, session_id=session_id
                )

            # Count human players before start
            human_count = 1 + num_joiners  # creator + joiners

            # Start the game
            _, error = await service.start_game(
                player_id=creator_id, session_id=session_id
            )
            assert error is None, f"start_game failed unexpectedly: {error}"

            # Session should now be active
            active = await service.list_active_games()
            assert len(active) == 1
            assert active[0].status == "active"

            # Verify total players in session
            session = service._sessions[session_id]
            assert len(session.players) == player_count

            # Verify AI players have negative IDs
            expected_ai_count = player_count - human_count
            ai_players = [pid for pid in session.players.keys() if pid < 0]
            human_players = [pid for pid in session.players.keys() if pid > 0]
            assert len(ai_players) == expected_ai_count
            assert len(human_players) == human_count

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# Property 71: Deck size enforcement at game creation and joining
# ---------------------------------------------------------------------------


class TestDeckSizeEnforcement:
    """**Validates: Requirements 4.9, 4.10**

    For any deck with fewer than 35 cards, both create_game and join_game
    should reject the request with a deck_too_small error.
    """

    @given(
        player_id=valid_player_ids,
        deck_id=valid_deck_ids,
        player_count=valid_player_counts,
        card_count=invalid_deck_card_counts,
    )
    @settings(max_examples=100, deadline=None)
    def test_create_game_rejects_small_deck(
        self, player_id, deck_id, player_count, card_count
    ):
        """Creating a game with a deck that has fewer than 35 cards should
        return a deck_too_small error."""

        async def _run():
            pool = FakePool(deck_cards={deck_id: card_count})
            service = LobbyService(pool)

            session_id, error = await service.create_game(
                player_id=player_id, deck_id=deck_id, player_count=player_count
            )

            assert session_id is None
            assert error is not None
            assert error.code == "deck_too_small"

        asyncio.run(_run())

    @given(
        creator_id=valid_player_ids,
        joiner_id=valid_player_ids,
        creator_deck_id=valid_deck_ids,
        joiner_deck_id=valid_deck_ids,
        player_count=valid_player_counts,
        creator_card_count=valid_deck_card_counts,
        joiner_card_count=invalid_deck_card_counts,
    )
    @settings(max_examples=100, deadline=None)
    def test_join_game_rejects_small_deck(
        self,
        creator_id,
        joiner_id,
        creator_deck_id,
        joiner_deck_id,
        player_count,
        creator_card_count,
        joiner_card_count,
    ):
        """Joining a game with a deck that has fewer than 35 cards should
        return a deck_too_small error."""
        # Ensure different players and different deck IDs
        assume(creator_id != joiner_id)
        assume(creator_deck_id != joiner_deck_id)

        async def _run():
            pool = FakePool(
                deck_cards={
                    creator_deck_id: creator_card_count,
                    joiner_deck_id: joiner_card_count,
                }
            )
            service = LobbyService(pool)

            # Create a game with a valid deck
            session_id, create_error = await service.create_game(
                player_id=creator_id,
                deck_id=creator_deck_id,
                player_count=player_count,
            )
            assert create_error is None

            # Attempt to join with an invalid (too small) deck
            _, error = await service.join_game(
                player_id=joiner_id,
                deck_id=joiner_deck_id,
                session_id=session_id,
            )

            assert error is not None
            assert error.code == "deck_too_small"

        asyncio.run(_run())
