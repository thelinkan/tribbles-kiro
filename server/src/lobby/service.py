"""Game lobby service for session creation, joining, spectating, and lifecycle.

Manages in-memory game sessions. Validates deck sizes and player counts.
Follows the Result-style tuple return pattern: (value, None) on success,
(None, LobbyError) on failure.
"""

import uuid
from typing import Dict, List, Optional, Tuple

import aiomysql

from models import GameSessionSummary


class LobbyError:
    """Represents a lobby operation error with a code and message."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message

    def __repr__(self) -> str:
        return f"LobbyError(code={self.code!r}, message={self.message!r})"


class _GameSession:
    """Internal representation of a game session held in memory."""

    def __init__(
        self,
        session_id: str,
        creator_player_id: int,
        player_count: int,
    ):
        self.session_id = session_id
        self.creator_player_id = creator_player_id
        self.player_count = player_count
        self.status = "waiting"
        # Maps player_id -> deck_id for human players
        self.players: Dict[int, int] = {}
        # List of player_ids who are spectating
        self.spectators: List[int] = []

    @property
    def current_player_count(self) -> int:
        return len(self.players)

    def to_summary(self) -> GameSessionSummary:
        return GameSessionSummary(
            session_id=self.session_id,
            creator_player_id=self.creator_player_id,
            player_count=self.player_count,
            current_player_count=self.current_player_count,
            status=self.status,
            players_joined=[str(pid) for pid in self.players.keys()],
        )


class LobbyService:
    """Handles game session creation, joining, spectating, and lifecycle.

    Uses an aiomysql connection pool to validate deck card counts.
    Game sessions are stored in memory (not persisted to DB during gameplay).
    All methods are async. Operations that can fail return a Result-style tuple:
    (value, None) on success, or (None, LobbyError) on failure.
    """

    MIN_PLAYER_COUNT = 4
    MAX_PLAYER_COUNT = 8
    MIN_DECK_CARD_COUNT = 35

    def __init__(self, pool: aiomysql.Pool):
        """Initialise the lobby service with a database connection pool.

        Args:
            pool: An aiomysql connection pool for database access (deck validation).
        """
        self._pool = pool
        self._sessions: Dict[str, _GameSession] = {}

    async def _get_deck_card_count(self, deck_id: int) -> Optional[int]:
        """Query the total card count for a deck from the database.

        Returns the sum of all card quantities, or None if the deck doesn't exist.
        """
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT COALESCE(SUM(quantity), 0) FROM deck_cards WHERE deck_id = %s",
                    (deck_id,),
                )
                row = await cur.fetchone()
                if row is None:
                    return None
                return int(row[0])

    async def create_game(
        self, player_id: int, deck_id: int, player_count: int
    ) -> Tuple[Optional[str], Optional[LobbyError]]:
        """Create a new game session in the waiting state.

        Validates that player_count is between 4 and 8 inclusive, and that
        the referenced deck has at least 35 cards total.

        Args:
            player_id: The ID of the player creating the game.
            deck_id: The ID of the deck the creator will use.
            player_count: Total number of player slots (4-8).

        Returns:
            A tuple of (session_id, None) on success, or (None, LobbyError) on failure.
        """
        # Validate player count
        if player_count < self.MIN_PLAYER_COUNT or player_count > self.MAX_PLAYER_COUNT:
            return (
                None,
                LobbyError(
                    "invalid_player_count",
                    f"Player count must be between {self.MIN_PLAYER_COUNT} and "
                    f"{self.MAX_PLAYER_COUNT} inclusive.",
                ),
            )

        # Validate deck size
        card_count = await self._get_deck_card_count(deck_id)
        if card_count is None or card_count < self.MIN_DECK_CARD_COUNT:
            return (
                None,
                LobbyError(
                    "deck_too_small",
                    "Deck does not meet the minimum card count for game use.",
                ),
            )

        # Create session
        session_id = str(uuid.uuid4())
        session = _GameSession(
            session_id=session_id,
            creator_player_id=player_id,
            player_count=player_count,
        )
        session.players[player_id] = deck_id
        self._sessions[session_id] = session

        return (session_id, None)

    async def join_game(
        self, player_id: int, deck_id: int, session_id: str
    ) -> Tuple[Optional[None], Optional[LobbyError]]:
        """Join an existing game session.

        Validates that the session is in the waiting state, is not full,
        and that the referenced deck has at least 35 cards total.

        Args:
            player_id: The ID of the player joining.
            deck_id: The ID of the deck the player will use.
            session_id: The ID of the session to join.

        Returns:
            A tuple of (None, None) on success, or (None, LobbyError) on failure.
        """
        session = self._sessions.get(session_id)
        if session is None:
            return (
                None,
                LobbyError("not_found", "Game session not found."),
            )

        # Check session state
        if session.status != "waiting":
            return (
                None,
                LobbyError(
                    "game_already_started",
                    "The game has already started.",
                ),
            )

        # Check if session is full
        if session.current_player_count >= session.player_count:
            return (
                None,
                LobbyError("session_full", "The session is full."),
            )

        # Validate deck size
        card_count = await self._get_deck_card_count(deck_id)
        if card_count is None or card_count < self.MIN_DECK_CARD_COUNT:
            return (
                None,
                LobbyError(
                    "deck_too_small",
                    "Deck does not meet the minimum card count for game use.",
                ),
            )

        # Add player
        session.players[player_id] = deck_id
        return (None, None)

    async def start_game(
        self, player_id: int, session_id: str
    ) -> Tuple[Optional[None], Optional[LobbyError]]:
        """Start a game session, filling remaining seats with AI players.

        Only the session creator can start the game. Fills remaining seats
        with computer-controlled players (assigned placeholder deck IDs)
        and transitions the session to active state.

        Args:
            player_id: The ID of the player requesting the start.
            session_id: The ID of the session to start.

        Returns:
            A tuple of (None, None) on success, or (None, LobbyError) on failure.
        """
        session = self._sessions.get(session_id)
        if session is None:
            return (
                None,
                LobbyError("not_found", "Game session not found."),
            )

        if session.creator_player_id != player_id:
            return (
                None,
                LobbyError(
                    "not_creator",
                    "Only the session creator can start the game.",
                ),
            )

        if session.status != "waiting":
            return (
                None,
                LobbyError(
                    "game_already_started",
                    "The game has already started.",
                ),
            )

        # Fill remaining seats with AI players using placeholder deck IDs
        remaining_seats = session.player_count - session.current_player_count
        for i in range(remaining_seats):
            # AI player IDs are negative to distinguish from human players
            ai_player_id = -(i + 1)
            # Placeholder deck_id — will be refined when AI_Controller is implemented
            ai_deck_id = -1
            session.players[ai_player_id] = ai_deck_id

        # Transition to active state
        session.status = "active"
        return (None, None)

    async def list_waiting_games(self) -> List[GameSessionSummary]:
        """List all game sessions in the waiting state.

        Returns:
            A list of GameSessionSummary objects for sessions available to join.
        """
        return [
            session.to_summary()
            for session in self._sessions.values()
            if session.status == "waiting"
        ]

    async def list_active_games(self) -> List[GameSessionSummary]:
        """List all game sessions in the active state.

        Returns:
            A list of GameSessionSummary objects for sessions available to watch.
        """
        return [
            session.to_summary()
            for session in self._sessions.values()
            if session.status == "active"
        ]

    async def watch_game(
        self, player_id: int, session_id: str
    ) -> Tuple[Optional[None], Optional[LobbyError]]:
        """Add a player as a spectator to an active game session.

        Args:
            player_id: The ID of the player who wants to spectate.
            session_id: The ID of the session to watch.

        Returns:
            A tuple of (None, None) on success, or (None, LobbyError) on failure.
        """
        session = self._sessions.get(session_id)
        if session is None:
            return (
                None,
                LobbyError("not_found", "Game session not found."),
            )

        if session.status != "active":
            return (
                None,
                LobbyError(
                    "game_not_active",
                    "Can only watch games that are currently active.",
                ),
            )

        session.spectators.append(player_id)
        return (None, None)
