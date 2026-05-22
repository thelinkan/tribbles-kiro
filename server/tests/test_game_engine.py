"""Tests for the Game_Engine initialise_game method.

Tests cover game initialisation requirements:
- 5.1: Randomly assign seating positions to all players
- 5.2: Randomly select one player as the starting player
- 5.3: Shuffle each player's draw deck independently
- 5.4: Deal 7 cards from each player's draw deck to that player's hand
- 5.5: Set initial play direction to clockwise and initial sequence denomination to 1
"""

import sys
import os

import pytest

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from game.engine import GameEngine, GameSession, PlayerSetup
from models import CardInstance, GameState, PlayerState


def make_card(card_id: int, denomination: int = 1, power: str = "Bonus") -> CardInstance:
    """Helper to create a CardInstance for testing."""
    return CardInstance(
        card_id=card_id,
        card_name=f"Tribble_{card_id}",
        denomination=denomination,
        power_text=power,
        expansion_id=1,
    )


def make_deck(size: int = 40, start_id: int = 1) -> list:
    """Helper to create a list of CardInstance objects for a deck."""
    denominations = [1, 10, 100, 1000, 10000, 100000]
    return [
        make_card(
            card_id=start_id + i,
            denomination=denominations[i % len(denominations)],
        )
        for i in range(size)
    ]


def make_session(
    player_count: int = 4, deck_size: int = 40, game_id: str = "test-game-1"
) -> GameSession:
    """Helper to create a GameSession with the specified number of players."""
    players = []
    for i in range(player_count):
        players.append(
            PlayerSetup(
                player_id=i + 1,
                username=f"Player_{i + 1}",
                is_computer=(i >= 2),  # First 2 human, rest AI
                deck_cards=make_deck(size=deck_size, start_id=i * 100 + 1),
            )
        )
    return GameSession(
        game_id=game_id,
        players=players,
        spectators=[100, 101],
        reconnection_timeout=30,
    )


@pytest.fixture
def engine():
    """Create a fresh GameEngine instance."""
    return GameEngine()


@pytest.fixture
def session_4_players():
    """Create a session with 4 players."""
    return make_session(player_count=4)


@pytest.fixture
def session_8_players():
    """Create a session with 8 players."""
    return make_session(player_count=8)


class TestInitialiseGameSeatPositions:
    """Tests for Requirement 5.1: Randomly assign seating positions."""

    def test_all_players_have_unique_seat_positions(self, engine, session_4_players):
        """Each player gets a unique seat position."""
        state = engine.initialise_game(session_4_players)
        positions = [p.seat_position for p in state.players]
        assert len(set(positions)) == len(positions)

    def test_seat_positions_cover_1_through_player_count(
        self, engine, session_4_players
    ):
        """Seat positions are exactly 1 through player_count."""
        state = engine.initialise_game(session_4_players)
        positions = sorted(p.seat_position for p in state.players)
        assert positions == [1, 2, 3, 4]

    def test_seat_positions_8_players(self, engine, session_8_players):
        """Seat positions cover 1 through 8 for 8 players."""
        state = engine.initialise_game(session_8_players)
        positions = sorted(p.seat_position for p in state.players)
        assert positions == [1, 2, 3, 4, 5, 6, 7, 8]

    def test_players_sorted_by_seat_position(self, engine, session_4_players):
        """Players list is ordered by seat position."""
        state = engine.initialise_game(session_4_players)
        for i in range(len(state.players) - 1):
            assert state.players[i].seat_position < state.players[i + 1].seat_position


class TestInitialiseGameStartingPlayer:
    """Tests for Requirement 5.2: Randomly select starting player."""

    def test_starting_player_index_is_valid(self, engine, session_4_players):
        """current_player_index is within bounds of the players list."""
        state = engine.initialise_game(session_4_players)
        assert 0 <= state.current_player_index < len(state.players)

    def test_starting_player_is_a_member(self, engine, session_4_players):
        """The starting player is one of the players in the game."""
        state = engine.initialise_game(session_4_players)
        starting_player = state.players[state.current_player_index]
        player_ids = [p.player_id for p in state.players]
        assert starting_player.player_id in player_ids


class TestInitialiseGameDeckShuffle:
    """Tests for Requirement 5.3: Shuffle each player's draw deck independently."""

    def test_draw_deck_contains_remaining_cards(self, engine, session_4_players):
        """After dealing 7, the draw deck has deck_size - 7 cards."""
        state = engine.initialise_game(session_4_players)
        for player in state.players:
            # Original deck was 40 cards, 7 dealt to hand
            assert len(player.draw_deck) == 40 - 7

    def test_all_original_cards_accounted_for(self, engine):
        """All cards from the original deck are in either hand or draw_deck."""
        session = make_session(player_count=4, deck_size=40)
        state = engine.initialise_game(session)

        for i, player in enumerate(state.players):
            original_ids = {c.card_id for c in session.players[i].deck_cards}
            current_ids = {c.card_id for c in player.hand} | {
                c.card_id for c in player.draw_deck
            }
            # After sorting by seat, player order may differ from session order
            # Find the matching session player by player_id
            session_player = next(
                sp for sp in session.players if sp.player_id == player.player_id
            )
            original_ids = {c.card_id for c in session_player.deck_cards}
            current_ids = {c.card_id for c in player.hand} | {
                c.card_id for c in player.draw_deck
            }
            assert original_ids == current_ids


class TestInitialiseGameDealCards:
    """Tests for Requirement 5.4: Deal 7 cards from draw deck to hand."""

    def test_each_player_has_7_cards_in_hand(self, engine, session_4_players):
        """Every player starts with exactly 7 cards in hand."""
        state = engine.initialise_game(session_4_players)
        for player in state.players:
            assert len(player.hand) == 7

    def test_hand_cards_come_from_deck(self, engine):
        """Hand cards are a subset of the original deck cards."""
        session = make_session(player_count=4, deck_size=40)
        state = engine.initialise_game(session)

        for player in state.players:
            session_player = next(
                sp for sp in session.players if sp.player_id == player.player_id
            )
            original_ids = {c.card_id for c in session_player.deck_cards}
            hand_ids = {c.card_id for c in player.hand}
            assert hand_ids.issubset(original_ids)

    def test_small_deck_deals_all_available(self, engine):
        """If deck has fewer than 7 cards, all cards go to hand."""
        session = GameSession(
            game_id="small-deck-game",
            players=[
                PlayerSetup(
                    player_id=1,
                    username="Player_1",
                    is_computer=False,
                    deck_cards=make_deck(size=5, start_id=1),
                ),
                PlayerSetup(
                    player_id=2,
                    username="Player_2",
                    is_computer=False,
                    deck_cards=make_deck(size=5, start_id=100),
                ),
            ],
            spectators=[],
        )
        state = engine.initialise_game(session)
        for player in state.players:
            assert len(player.hand) == 5
            assert len(player.draw_deck) == 0


class TestInitialiseGameDirection:
    """Tests for Requirement 5.5: Set direction clockwise and sequence to 1."""

    def test_direction_is_clockwise(self, engine, session_4_players):
        """Initial direction is clockwise (1)."""
        state = engine.initialise_game(session_4_players)
        assert state.direction == 1

    def test_sequence_starts_at_1(self, engine, session_4_players):
        """Initial sequence denomination is 1."""
        state = engine.initialise_game(session_4_players)
        assert state.current_sequence == 1

    def test_round_number_is_1(self, engine, session_4_players):
        """Initial round number is 1."""
        state = engine.initialise_game(session_4_players)
        assert state.round_number == 1

    def test_game_status_is_active(self, engine, session_4_players):
        """Game status is set to active."""
        state = engine.initialise_game(session_4_players)
        assert state.game_status == "active"

    def test_last_played_denomination_is_none(self, engine, session_4_players):
        """No card has been played yet."""
        state = engine.initialise_game(session_4_players)
        assert state.last_played_denomination is None

    def test_sequence_broken_is_false(self, engine, session_4_players):
        """No sequence break at start."""
        state = engine.initialise_game(session_4_players)
        assert state.sequence_broken is False

    def test_frozen_powers_is_empty(self, engine, session_4_players):
        """No powers are frozen at start."""
        state = engine.initialise_game(session_4_players)
        assert state.frozen_powers == {}


class TestInitialiseGamePlayerState:
    """Tests for initial player state correctness."""

    def test_play_pile_is_empty(self, engine, session_4_players):
        """All players start with empty play piles."""
        state = engine.initialise_game(session_4_players)
        for player in state.players:
            assert player.play_pile == []

    def test_discard_pile_is_empty(self, engine, session_4_players):
        """All players start with empty discard piles."""
        state = engine.initialise_game(session_4_players)
        for player in state.players:
            assert player.discard_pile == []

    def test_cumulative_score_is_zero(self, engine, session_4_players):
        """All players start with zero score."""
        state = engine.initialise_game(session_4_players)
        for player in state.players:
            assert player.cumulative_score == 0

    def test_no_player_is_decked(self, engine, session_4_players):
        """No player starts as decked."""
        state = engine.initialise_game(session_4_players)
        for player in state.players:
            assert player.is_decked is False

    def test_no_player_has_gone_out(self, engine, session_4_players):
        """No player starts as having gone out."""
        state = engine.initialise_game(session_4_players)
        for player in state.players:
            assert player.has_gone_out is False

    def test_player_ids_preserved(self, engine, session_4_players):
        """All original player IDs are present in the game state."""
        state = engine.initialise_game(session_4_players)
        state_ids = {p.player_id for p in state.players}
        session_ids = {p.player_id for p in session_4_players.players}
        assert state_ids == session_ids

    def test_usernames_preserved(self, engine, session_4_players):
        """All original usernames are present in the game state."""
        state = engine.initialise_game(session_4_players)
        state_usernames = {p.username for p in state.players}
        session_usernames = {p.username for p in session_4_players.players}
        assert state_usernames == session_usernames

    def test_is_computer_preserved(self, engine, session_4_players):
        """Computer player flags are preserved correctly."""
        state = engine.initialise_game(session_4_players)
        for player in state.players:
            session_player = next(
                sp
                for sp in session_4_players.players
                if sp.player_id == player.player_id
            )
            assert player.is_computer == session_player.is_computer


class TestInitialiseGameMetadata:
    """Tests for game metadata (game_id, spectators, timeout)."""

    def test_game_id_preserved(self, engine, session_4_players):
        """Game ID matches the session's game_id."""
        state = engine.initialise_game(session_4_players)
        assert state.game_id == "test-game-1"

    def test_spectators_preserved(self, engine, session_4_players):
        """Spectator list is preserved from the session."""
        state = engine.initialise_game(session_4_players)
        assert state.spectators == [100, 101]

    def test_reconnection_timeout_preserved(self, engine, session_4_players):
        """Reconnection timeout is preserved from the session."""
        state = engine.initialise_game(session_4_players)
        assert state.reconnection_timeout == 30

    def test_custom_reconnection_timeout(self, engine):
        """Custom reconnection timeout is respected."""
        session = GameSession(
            game_id="custom-timeout",
            players=[
                PlayerSetup(
                    player_id=1,
                    username="P1",
                    is_computer=False,
                    deck_cards=make_deck(size=40),
                ),
                PlayerSetup(
                    player_id=2,
                    username="P2",
                    is_computer=True,
                    deck_cards=make_deck(size=40, start_id=100),
                ),
            ],
            spectators=[],
            reconnection_timeout=60,
        )
        state = engine.initialise_game(session)
        assert state.reconnection_timeout == 60

    def test_game_stored_in_engine(self, engine, session_4_players):
        """The game state is stored internally for later access."""
        state = engine.initialise_game(session_4_players)
        assert session_4_players.game_id in engine._games
        assert engine._games[session_4_players.game_id] is state
