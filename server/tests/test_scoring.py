"""Tests for the Score_Service.

Tests cover scoring requirements:
- 8.2: Sum denominations in play pile for players who went out, add to cumulative score
- apply_immediate_score: Add points to a player's cumulative score during gameplay
"""

import sys
import os

import pytest

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from models import CardInstance, GameState, PlayerState
from scoring.service import ScoreService


def make_card(card_id: int, denomination: int = 1, power: str = "Go") -> CardInstance:
    """Helper to create a CardInstance for testing."""
    return CardInstance(
        card_id=card_id,
        card_name=f"Tribble_{card_id}",
        denomination=denomination,
        power_text=power,
        expansion_id=1,
    )


def make_game_state(num_players: int = 4) -> GameState:
    """Helper to create a GameState with controllable parameters."""
    players = []
    for i in range(num_players):
        player = PlayerState(
            player_id=i + 1,
            username=f"Player_{i + 1}",
            is_computer=False,
            hand=[],
            draw_deck=[],
            play_pile=[],
            discard_pile=[],
            cumulative_score=0,
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
        current_sequence=1,
        round_number=1,
        game_status="active",
    )


@pytest.fixture
def score_service():
    """Create a fresh ScoreService instance."""
    return ScoreService()


class TestCalculateRoundScores:
    """Tests for calculate_round_scores method."""

    def test_single_player_went_out_scores_play_pile(self, score_service):
        """Player who went out scores sum of denominations in play pile."""
        state = make_game_state(num_players=3)
        state.players[0].has_gone_out = True
        state.players[0].play_pile = [
            make_card(1, denomination=1),
            make_card(2, denomination=10),
            make_card(3, denomination=100),
        ]

        scores = score_service.calculate_round_scores(state)

        assert scores[1] == 111  # 1 + 10 + 100

    def test_player_who_did_not_go_out_scores_zero(self, score_service):
        """Players who did not go out receive a score of 0."""
        state = make_game_state(num_players=3)
        state.players[0].has_gone_out = True
        state.players[0].play_pile = [make_card(1, denomination=100)]
        # Player 2 did not go out
        state.players[1].play_pile = [make_card(2, denomination=1000)]

        scores = score_service.calculate_round_scores(state)

        assert scores[2] == 0

    def test_multiple_players_went_out(self, score_service):
        """Multiple players who went out each score their own play pile."""
        state = make_game_state(num_players=4)
        state.players[0].has_gone_out = True
        state.players[0].play_pile = [
            make_card(1, denomination=1),
            make_card(2, denomination=10),
        ]
        state.players[2].has_gone_out = True
        state.players[2].play_pile = [
            make_card(3, denomination=1000),
            make_card(4, denomination=10000),
        ]

        scores = score_service.calculate_round_scores(state)

        assert scores[1] == 11  # 1 + 10
        assert scores[3] == 11000  # 1000 + 10000
        assert scores[2] == 0
        assert scores[4] == 0

    def test_empty_play_pile_scores_zero(self, score_service):
        """Player who went out with empty play pile scores 0."""
        state = make_game_state(num_players=2)
        state.players[0].has_gone_out = True
        state.players[0].play_pile = []

        scores = score_service.calculate_round_scores(state)

        assert scores[1] == 0

    def test_all_denominations_summed_correctly(self, score_service):
        """All denomination values are summed correctly."""
        state = make_game_state(num_players=2)
        state.players[0].has_gone_out = True
        state.players[0].play_pile = [
            make_card(1, denomination=1),
            make_card(2, denomination=10),
            make_card(3, denomination=100),
            make_card(4, denomination=1000),
            make_card(5, denomination=10000),
            make_card(6, denomination=100000),
        ]

        scores = score_service.calculate_round_scores(state)

        assert scores[1] == 111111

    def test_no_players_went_out(self, score_service):
        """When no players went out, all scores are 0."""
        state = make_game_state(num_players=3)

        scores = score_service.calculate_round_scores(state)

        assert all(score == 0 for score in scores.values())


class TestApplyImmediateScore:
    """Tests for apply_immediate_score method."""

    def test_adds_points_to_player(self, score_service):
        """Points are added to the specified player's cumulative score."""
        state = make_game_state(num_players=3)
        state.players[0].cumulative_score = 100

        score_service.apply_immediate_score(state, player_id=1, points=50)

        assert state.players[0].cumulative_score == 150

    def test_adds_points_to_correct_player(self, score_service):
        """Points are added only to the specified player, not others."""
        state = make_game_state(num_players=3)
        state.players[0].cumulative_score = 100
        state.players[1].cumulative_score = 200

        score_service.apply_immediate_score(state, player_id=2, points=75)

        assert state.players[0].cumulative_score == 100  # Unchanged
        assert state.players[1].cumulative_score == 275

    def test_negative_points(self, score_service):
        """Negative points reduce the cumulative score."""
        state = make_game_state(num_players=2)
        state.players[0].cumulative_score = 500

        score_service.apply_immediate_score(state, player_id=1, points=-100)

        assert state.players[0].cumulative_score == 400

    def test_invalid_player_raises_error(self, score_service):
        """Raises ValueError when player_id is not found."""
        state = make_game_state(num_players=2)

        with pytest.raises(ValueError, match="Player 99 not found"):
            score_service.apply_immediate_score(state, player_id=99, points=50)

    def test_zero_points(self, score_service):
        """Adding zero points leaves score unchanged."""
        state = make_game_state(num_players=2)
        state.players[0].cumulative_score = 300

        score_service.apply_immediate_score(state, player_id=1, points=0)

        assert state.players[0].cumulative_score == 300
