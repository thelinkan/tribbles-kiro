"""Tests for the Lobby_Service (create, join, start, list, watch operations).

Uses an in-memory mock of the aiomysql pool to test lobby logic without
requiring a live database connection.
"""

import sys
import os

import pytest

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lobby.service import LobbyService, LobbyError
from models import GameSessionSummary


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


@pytest.fixture
def valid_pool():
    """Create a FakePool with a valid deck (35+ cards)."""
    return FakePool(deck_cards={1: 40, 2: 50, 3: 10})


@pytest.fixture
def lobby_service(valid_pool):
    """Create a LobbyService with a fake pool containing valid decks."""
    return LobbyService(valid_pool)


class TestCreateGame:
    """Tests for LobbyService.create_game."""

    @pytest.mark.asyncio
    async def test_create_game_success(self, lobby_service):
        """Requirement 4.1: Create game with valid player count returns session ID in waiting state."""
        session_id, error = await lobby_service.create_game(
            player_id=1, deck_id=1, player_count=4
        )
        assert error is None
        assert session_id is not None
        assert isinstance(session_id, str)
        assert len(session_id) > 0

    @pytest.mark.asyncio
    async def test_create_game_session_in_waiting_state(self, lobby_service):
        """Requirement 4.1: Created session is in waiting state."""
        session_id, _ = await lobby_service.create_game(
            player_id=1, deck_id=1, player_count=6
        )
        waiting = await lobby_service.list_waiting_games()
        assert len(waiting) == 1
        assert waiting[0].session_id == session_id
        assert waiting[0].status == "waiting"

    @pytest.mark.asyncio
    async def test_create_game_player_count_too_low(self, lobby_service):
        """Requirement 4.9: Player count < 4 returns error."""
        session_id, error = await lobby_service.create_game(
            player_id=1, deck_id=1, player_count=3
        )
        assert session_id is None
        assert error is not None
        assert error.code == "invalid_player_count"

    @pytest.mark.asyncio
    async def test_create_game_player_count_too_high(self, lobby_service):
        """Requirement 4.9: Player count > 8 returns error."""
        session_id, error = await lobby_service.create_game(
            player_id=1, deck_id=1, player_count=9
        )
        assert session_id is None
        assert error is not None
        assert error.code == "invalid_player_count"

    @pytest.mark.asyncio
    async def test_create_game_player_count_boundary_4(self, lobby_service):
        """Requirement 4.1: Player count of 4 is valid."""
        session_id, error = await lobby_service.create_game(
            player_id=1, deck_id=1, player_count=4
        )
        assert error is None
        assert session_id is not None

    @pytest.mark.asyncio
    async def test_create_game_player_count_boundary_8(self, lobby_service):
        """Requirement 4.1: Player count of 8 is valid."""
        session_id, error = await lobby_service.create_game(
            player_id=1, deck_id=1, player_count=8
        )
        assert error is None
        assert session_id is not None

    @pytest.mark.asyncio
    async def test_create_game_deck_too_small(self):
        """Requirement 4.10: Create game with deck < 35 cards returns error."""
        pool = FakePool(deck_cards={1: 34})
        service = LobbyService(pool)
        session_id, error = await service.create_game(
            player_id=1, deck_id=1, player_count=4
        )
        assert session_id is None
        assert error is not None
        assert error.code == "deck_too_small"

    @pytest.mark.asyncio
    async def test_create_game_deck_exactly_35_cards(self):
        """Requirement 4.10: Deck with exactly 35 cards is valid."""
        pool = FakePool(deck_cards={1: 35})
        service = LobbyService(pool)
        session_id, error = await service.create_game(
            player_id=1, deck_id=1, player_count=4
        )
        assert error is None
        assert session_id is not None

    @pytest.mark.asyncio
    async def test_create_game_nonexistent_deck(self):
        """Create game with a deck that doesn't exist returns error."""
        pool = FakePool(deck_cards={})
        service = LobbyService(pool)
        session_id, error = await service.create_game(
            player_id=1, deck_id=99, player_count=4
        )
        assert session_id is None
        assert error is not None
        assert error.code == "deck_too_small"

    @pytest.mark.asyncio
    async def test_create_game_creator_is_first_player(self, lobby_service):
        """Creator is automatically added as the first player in the session."""
        session_id, _ = await lobby_service.create_game(
            player_id=1, deck_id=1, player_count=4
        )
        waiting = await lobby_service.list_waiting_games()
        assert waiting[0].current_player_count == 1
        assert "1" in waiting[0].players_joined


class TestJoinGame:
    """Tests for LobbyService.join_game."""

    @pytest.mark.asyncio
    async def test_join_game_success(self, lobby_service):
        """Requirement 4.2: Join game adds player if session is waiting and not full."""
        session_id, _ = await lobby_service.create_game(
            player_id=1, deck_id=1, player_count=4
        )
        result, error = await lobby_service.join_game(
            player_id=2, deck_id=2, session_id=session_id
        )
        assert error is None

    @pytest.mark.asyncio
    async def test_join_game_increments_player_count(self, lobby_service):
        """Requirement 4.2: Joining increments the human player count."""
        session_id, _ = await lobby_service.create_game(
            player_id=1, deck_id=1, player_count=4
        )
        await lobby_service.join_game(player_id=2, deck_id=2, session_id=session_id)
        waiting = await lobby_service.list_waiting_games()
        assert waiting[0].current_player_count == 2

    @pytest.mark.asyncio
    async def test_join_game_session_full(self, lobby_service):
        """Requirement 4.3: Join rejected if session is full."""
        session_id, _ = await lobby_service.create_game(
            player_id=1, deck_id=1, player_count=4
        )
        await lobby_service.join_game(player_id=2, deck_id=2, session_id=session_id)
        await lobby_service.join_game(player_id=3, deck_id=1, session_id=session_id)
        await lobby_service.join_game(player_id=4, deck_id=2, session_id=session_id)

        # Session is now full (4 players)
        result, error = await lobby_service.join_game(
            player_id=5, deck_id=1, session_id=session_id
        )
        assert error is not None
        assert error.code == "session_full"

    @pytest.mark.asyncio
    async def test_join_game_not_waiting(self, lobby_service):
        """Requirement 4.4: Join rejected if session is not in waiting state."""
        session_id, _ = await lobby_service.create_game(
            player_id=1, deck_id=1, player_count=4
        )
        # Start the game to transition to active
        await lobby_service.start_game(player_id=1, session_id=session_id)

        result, error = await lobby_service.join_game(
            player_id=2, deck_id=2, session_id=session_id
        )
        assert error is not None
        assert error.code == "game_already_started"

    @pytest.mark.asyncio
    async def test_join_game_deck_too_small(self):
        """Requirement 4.11: Join game with deck < 35 cards returns error."""
        # Deck 1 is valid (40 cards), deck 2 is too small (20 cards)
        pool = FakePool(deck_cards={1: 40, 2: 20})
        service = LobbyService(pool)
        session_id, _ = await service.create_game(
            player_id=1, deck_id=1, player_count=4
        )
        result, error = await service.join_game(
            player_id=2, deck_id=2, session_id=session_id
        )
        assert error is not None
        assert error.code == "deck_too_small"

    @pytest.mark.asyncio
    async def test_join_game_session_not_found(self, lobby_service):
        """Join game with nonexistent session returns not_found error."""
        result, error = await lobby_service.join_game(
            player_id=1, deck_id=1, session_id="nonexistent"
        )
        assert error is not None
        assert error.code == "not_found"


class TestStartGame:
    """Tests for LobbyService.start_game."""

    @pytest.mark.asyncio
    async def test_start_game_fills_ai_seats(self, lobby_service):
        """Start game fills remaining seats with AI players."""
        session_id, _ = await lobby_service.create_game(
            player_id=1, deck_id=1, player_count=6
        )
        await lobby_service.join_game(player_id=2, deck_id=2, session_id=session_id)

        result, error = await lobby_service.start_game(
            player_id=1, session_id=session_id
        )
        assert error is None

        # Session should now be active with 6 total players (2 human + 4 AI)
        active = await lobby_service.list_active_games()
        assert len(active) == 1
        assert active[0].status == "active"

    @pytest.mark.asyncio
    async def test_start_game_transitions_to_active(self, lobby_service):
        """Start game transitions session from waiting to active."""
        session_id, _ = await lobby_service.create_game(
            player_id=1, deck_id=1, player_count=4
        )
        await lobby_service.start_game(player_id=1, session_id=session_id)

        waiting = await lobby_service.list_waiting_games()
        active = await lobby_service.list_active_games()
        assert len(waiting) == 0
        assert len(active) == 1

    @pytest.mark.asyncio
    async def test_start_game_only_creator_can_start(self, lobby_service):
        """Only the session creator can start the game."""
        session_id, _ = await lobby_service.create_game(
            player_id=1, deck_id=1, player_count=4
        )
        await lobby_service.join_game(player_id=2, deck_id=2, session_id=session_id)

        result, error = await lobby_service.start_game(
            player_id=2, session_id=session_id
        )
        assert error is not None
        assert error.code == "not_creator"

    @pytest.mark.asyncio
    async def test_start_game_session_not_found(self, lobby_service):
        """Start game with nonexistent session returns not_found error."""
        result, error = await lobby_service.start_game(
            player_id=1, session_id="nonexistent"
        )
        assert error is not None
        assert error.code == "not_found"

    @pytest.mark.asyncio
    async def test_start_game_already_active(self, lobby_service):
        """Start game on already active session returns error."""
        session_id, _ = await lobby_service.create_game(
            player_id=1, deck_id=1, player_count=4
        )
        await lobby_service.start_game(player_id=1, session_id=session_id)

        result, error = await lobby_service.start_game(
            player_id=1, session_id=session_id
        )
        assert error is not None
        assert error.code == "game_already_started"

    @pytest.mark.asyncio
    async def test_start_game_all_seats_filled_no_ai(self, lobby_service):
        """When all seats are filled by humans, no AI players are added."""
        session_id, _ = await lobby_service.create_game(
            player_id=1, deck_id=1, player_count=4
        )
        await lobby_service.join_game(player_id=2, deck_id=2, session_id=session_id)
        await lobby_service.join_game(player_id=3, deck_id=1, session_id=session_id)
        await lobby_service.join_game(player_id=4, deck_id=2, session_id=session_id)

        result, error = await lobby_service.start_game(
            player_id=1, session_id=session_id
        )
        assert error is None

        # Verify the session has exactly 4 players (all human)
        session = lobby_service._sessions[session_id]
        assert len(session.players) == 4
        # No negative (AI) player IDs
        assert all(pid > 0 for pid in session.players.keys())


class TestListGames:
    """Tests for LobbyService.list_waiting_games and list_active_games."""

    @pytest.mark.asyncio
    async def test_list_waiting_games_empty(self, lobby_service):
        """No sessions returns empty list."""
        waiting = await lobby_service.list_waiting_games()
        assert waiting == []

    @pytest.mark.asyncio
    async def test_list_waiting_games_returns_summaries(self, lobby_service):
        """list_waiting_games returns GameSessionSummary objects."""
        await lobby_service.create_game(player_id=1, deck_id=1, player_count=4)
        waiting = await lobby_service.list_waiting_games()
        assert len(waiting) == 1
        summary = waiting[0]
        assert isinstance(summary, GameSessionSummary)
        assert summary.creator_player_id == 1
        assert summary.player_count == 4
        assert summary.current_player_count == 1
        assert summary.status == "waiting"

    @pytest.mark.asyncio
    async def test_list_active_games_empty(self, lobby_service):
        """No active sessions returns empty list."""
        active = await lobby_service.list_active_games()
        assert active == []

    @pytest.mark.asyncio
    async def test_list_active_games_after_start(self, lobby_service):
        """list_active_games returns sessions that have been started."""
        session_id, _ = await lobby_service.create_game(
            player_id=1, deck_id=1, player_count=4
        )
        await lobby_service.start_game(player_id=1, session_id=session_id)

        active = await lobby_service.list_active_games()
        assert len(active) == 1
        assert active[0].session_id == session_id
        assert active[0].status == "active"

    @pytest.mark.asyncio
    async def test_list_games_separates_waiting_and_active(self, lobby_service):
        """Waiting and active games are listed separately."""
        session1, _ = await lobby_service.create_game(
            player_id=1, deck_id=1, player_count=4
        )
        session2, _ = await lobby_service.create_game(
            player_id=2, deck_id=2, player_count=6
        )
        await lobby_service.start_game(player_id=1, session_id=session1)

        waiting = await lobby_service.list_waiting_games()
        active = await lobby_service.list_active_games()
        assert len(waiting) == 1
        assert waiting[0].session_id == session2
        assert len(active) == 1
        assert active[0].session_id == session1


class TestWatchGame:
    """Tests for LobbyService.watch_game."""

    @pytest.mark.asyncio
    async def test_watch_active_game_success(self, lobby_service):
        """Requirement 4.6, 22.1: Spectator can watch active game."""
        session_id, _ = await lobby_service.create_game(
            player_id=1, deck_id=1, player_count=4
        )
        await lobby_service.start_game(player_id=1, session_id=session_id)

        result, error = await lobby_service.watch_game(
            player_id=10, session_id=session_id
        )
        assert error is None

    @pytest.mark.asyncio
    async def test_watch_game_adds_spectator(self, lobby_service):
        """watch_game adds the player to the spectators list."""
        session_id, _ = await lobby_service.create_game(
            player_id=1, deck_id=1, player_count=4
        )
        await lobby_service.start_game(player_id=1, session_id=session_id)
        await lobby_service.watch_game(player_id=10, session_id=session_id)

        session = lobby_service._sessions[session_id]
        assert 10 in session.spectators

    @pytest.mark.asyncio
    async def test_watch_game_not_active(self, lobby_service):
        """Cannot watch a game that is still in waiting state."""
        session_id, _ = await lobby_service.create_game(
            player_id=1, deck_id=1, player_count=4
        )
        result, error = await lobby_service.watch_game(
            player_id=10, session_id=session_id
        )
        assert error is not None
        assert error.code == "game_not_active"

    @pytest.mark.asyncio
    async def test_watch_game_session_not_found(self, lobby_service):
        """Watch game with nonexistent session returns not_found error."""
        result, error = await lobby_service.watch_game(
            player_id=10, session_id="nonexistent"
        )
        assert error is not None
        assert error.code == "not_found"
