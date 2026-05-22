"""Tests for game end condition (Requirements 16.1, 16.2).

Tests cover:
- Game ends after 5 rounds
- Game does not end before 5 rounds
- Winner is player with highest cumulative score
- Game status transitions to "completed"
- No new hands are dealt when game ends
- Final scores event is emitted
- Tie-breaking by seat position
"""

import sys
import os

import pytest

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from models import CardInstance, GameState, PlayerState
from game.round_manager import RoundManager
from scoring.service import ScoreService


def make_card(card_id: int, denomination: int = 1, power: str = "Bonus") -> CardInstance:
    """Helper to create a CardInstance for testing."""
    return CardInstance(
        card_id=card_id,
        card_name=f"Tribble_{card_id}",
        denomination=denomination,
        power_text=power,
        expansion_id=1,
    )


def make_game_state(
    num_players: int = 4,
    round_number: int = 1,
    cumulative_scores: list = None,
) -> GameState:
    """Helper to create a GameState for game end testing.

    Args:
        num_players: Number of players in the game.
        round_number: Current round number.
        cumulative_scores: Optional list of cumulative scores per player.
    """
    players = []
    for i in range(num_players):
        score = 0
        if cumulative_scores and i < len(cumulative_scores):
            score = cumulative_scores[i]

        player = PlayerState(
            player_id=i + 1,
            username=f"Player_{i + 1}",
            is_computer=False,
            hand=[make_card(card_id=i * 100 + j, denomination=10) for j in range(5)],
            draw_deck=[
                make_card(card_id=i * 100 + 50 + j, denomination=100)
                for j in range(20)
            ],
            play_pile=[
                make_card(card_id=i * 100 + 70 + j, denomination=1000)
                for j in range(3)
            ],
            discard_pile=[],
            cumulative_score=score,
            is_decked=False,
            has_gone_out=False,
            seat_position=i + 1,
        )
        players.append(player)

    return GameState(
        game_id="test-game",
        players=players,
        current_player_index=0,
        direction=1,
        current_sequence=100,
        round_number=round_number,
        game_status="round_end",
    )


@pytest.fixture
def round_manager():
    """Create a fresh RoundManager instance."""
    return RoundManager()


class TestGameEndsAfterFiveRounds:
    """Tests that the game ends after 5 rounds are completed."""

    def test_game_ends_when_round_5_completes(self, round_manager):
        """Game should end after the 5th round is completed (round_number=5)."""
        state = make_game_state(num_players=4, round_number=5)
        state.players[0].has_gone_out = True
        state.players[0].hand = []
        state.players[0].play_pile = [make_card(1, denomination=1000)]

        events = round_manager.process_end_of_round(state)

        assert state.game_status == "completed"

    def test_game_does_not_end_before_round_5(self, round_manager):
        """Game should NOT end before 5 rounds are completed."""
        for round_num in [1, 2, 3, 4]:
            state = make_game_state(num_players=4, round_number=round_num)
            state.players[0].has_gone_out = True
            state.players[0].hand = []
            state.players[0].play_pile = [make_card(1, denomination=1)]

            round_manager.process_end_of_round(state)

            assert state.game_status == "active", (
                f"Game should not end after round {round_num}"
            )

    def test_round_4_continues_normally(self, round_manager):
        """After round 4, a new round should start (round 5)."""
        state = make_game_state(num_players=4, round_number=4)
        state.players[0].has_gone_out = True
        state.players[0].hand = []
        state.players[0].play_pile = [make_card(1, denomination=1)]

        events = round_manager.process_end_of_round(state)

        assert state.game_status == "active"
        assert state.round_number == 5
        new_round_events = [e for e in events if e["type"] == "new_round_started"]
        assert len(new_round_events) == 1
        assert new_round_events[0]["round_number"] == 5


class TestGameStatusTransition:
    """Tests that game status transitions to 'completed' correctly."""

    def test_game_status_set_to_completed(self, round_manager):
        """Game status should be 'completed' when game ends."""
        state = make_game_state(num_players=4, round_number=5)
        state.players[0].has_gone_out = True
        state.players[0].hand = []
        state.players[0].play_pile = [make_card(1, denomination=100)]

        round_manager.process_end_of_round(state)

        assert state.game_status == "completed"

    def test_game_status_not_reset_to_active_on_end(self, round_manager):
        """Game status should NOT be reset to 'active' when game ends."""
        state = make_game_state(num_players=4, round_number=5)
        state.game_status = "round_end"
        state.players[0].has_gone_out = True
        state.players[0].hand = []
        state.players[0].play_pile = [make_card(1, denomination=100)]

        round_manager.process_end_of_round(state)

        assert state.game_status == "completed"


class TestWinnerDetermination:
    """Tests for determining the winner (highest cumulative score)."""

    def test_winner_is_highest_cumulative_score(self, round_manager):
        """Winner should be the player with the highest cumulative score."""
        state = make_game_state(
            num_players=4,
            round_number=5,
            cumulative_scores=[500, 1200, 800, 300],
        )
        state.players[1].has_gone_out = True
        state.players[1].hand = []
        state.players[1].play_pile = [make_card(1, denomination=100)]

        events = round_manager.process_end_of_round(state)

        game_end_events = [e for e in events if e["type"] == "game_end"]
        assert len(game_end_events) == 1
        # Player 2 has highest score (1200 + 100 from this round = 1300)
        assert game_end_events[0]["winner_player_id"] == 2
        assert game_end_events[0]["winner_username"] == "Player_2"

    def test_winner_includes_final_round_score(self, round_manager):
        """Winner determination should include the score from the final round."""
        state = make_game_state(
            num_players=3,
            round_number=5,
            cumulative_scores=[900, 800, 100],
        )
        # Player 2 goes out with a big play pile this round
        state.players[1].has_gone_out = True
        state.players[1].hand = []
        state.players[1].play_pile = [
            make_card(1, denomination=10000),
            make_card(2, denomination=1000),
        ]

        events = round_manager.process_end_of_round(state)

        game_end_events = [e for e in events if e["type"] == "game_end"]
        # Player 2: 800 + 11000 = 11800, Player 1: 900
        assert game_end_events[0]["winner_player_id"] == 2
        assert game_end_events[0]["final_scores"][2] == 11800

    def test_tie_broken_by_seat_position(self, round_manager):
        """When players tie on score, lowest seat position wins."""
        state = make_game_state(
            num_players=4,
            round_number=5,
            cumulative_scores=[1000, 1000, 500, 500],
        )
        state.players[0].has_gone_out = True
        state.players[0].hand = []
        state.players[0].play_pile = []  # No additional score this round

        events = round_manager.process_end_of_round(state)

        game_end_events = [e for e in events if e["type"] == "game_end"]
        # Player 1 and Player 2 both have 1000, Player 1 has seat_position=1
        assert game_end_events[0]["winner_player_id"] == 1


class TestNoNewHandsDealtOnGameEnd:
    """Tests that no new hands are dealt when the game ends."""

    def test_no_cards_dealt_when_game_ends(self, round_manager):
        """No cards should be dealt to players when the game ends."""
        state = make_game_state(num_players=4, round_number=5)
        state.players[0].has_gone_out = True
        state.players[0].hand = []
        state.players[0].play_pile = [make_card(1, denomination=1)]

        # Clear all hands and track draw deck sizes
        for player in state.players:
            player.hand = [] if player.has_gone_out else player.hand

        events = round_manager.process_end_of_round(state)

        # No cards_dealt events should be emitted
        dealt_events = [e for e in events if e["type"] == "cards_dealt"]
        assert len(dealt_events) == 0

    def test_no_new_round_started_event_on_game_end(self, round_manager):
        """No new_round_started event should be emitted when game ends."""
        state = make_game_state(num_players=4, round_number=5)
        state.players[0].has_gone_out = True
        state.players[0].hand = []
        state.players[0].play_pile = [make_card(1, denomination=1)]

        events = round_manager.process_end_of_round(state)

        new_round_events = [e for e in events if e["type"] == "new_round_started"]
        assert len(new_round_events) == 0


class TestFinalScoresEvent:
    """Tests for the game_end event with final scores."""

    def test_game_end_event_emitted(self, round_manager):
        """A game_end event should be emitted when the game ends."""
        state = make_game_state(num_players=4, round_number=5)
        state.players[0].has_gone_out = True
        state.players[0].hand = []
        state.players[0].play_pile = [make_card(1, denomination=100)]

        events = round_manager.process_end_of_round(state)

        game_end_events = [e for e in events if e["type"] == "game_end"]
        assert len(game_end_events) == 1

    def test_game_end_event_contains_final_scores(self, round_manager):
        """game_end event should contain final_scores for all players."""
        state = make_game_state(
            num_players=4,
            round_number=5,
            cumulative_scores=[100, 200, 300, 400],
        )
        state.players[2].has_gone_out = True
        state.players[2].hand = []
        state.players[2].play_pile = [make_card(1, denomination=1000)]

        events = round_manager.process_end_of_round(state)

        game_end_events = [e for e in events if e["type"] == "game_end"]
        final_scores = game_end_events[0]["final_scores"]

        # All players should have entries
        assert len(final_scores) == 4
        # Player 3 went out: 300 + 1000 = 1300
        assert final_scores[3] == 1300
        # Other players keep their cumulative scores
        assert final_scores[1] == 100
        assert final_scores[2] == 200
        assert final_scores[4] == 400

    def test_game_end_event_contains_winner_info(self, round_manager):
        """game_end event should contain winner_player_id and winner_username."""
        state = make_game_state(
            num_players=3,
            round_number=5,
            cumulative_scores=[500, 2000, 100],
        )
        state.players[0].has_gone_out = True
        state.players[0].hand = []
        state.players[0].play_pile = [make_card(1, denomination=1)]

        events = round_manager.process_end_of_round(state)

        game_end_events = [e for e in events if e["type"] == "game_end"]
        assert game_end_events[0]["winner_player_id"] == 2
        assert game_end_events[0]["winner_username"] == "Player_2"

    def test_round_scores_still_calculated_on_game_end(self, round_manager):
        """Round scores should still be calculated even when game ends."""
        state = make_game_state(num_players=3, round_number=5)
        state.players[0].has_gone_out = True
        state.players[0].hand = []
        state.players[0].play_pile = [make_card(1, denomination=10000)]

        events = round_manager.process_end_of_round(state)

        score_events = [e for e in events if e["type"] == "round_scores_calculated"]
        assert len(score_events) == 1
        assert score_events[0]["scores"][1] == 10000


class TestMaxRoundsConstant:
    """Tests for the MAX_ROUNDS constant."""

    def test_max_rounds_is_5(self):
        """MAX_ROUNDS should be 5."""
        assert RoundManager.MAX_ROUNDS == 5
