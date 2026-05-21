"""Tests for Bonus power scoring (Requirement 10.1).

Tests cover:
- All four Bonus denominations present → 100000 points awarded
- Missing one denomination → no bonus
- Player is decked → no bonus even if cards present
- Multiple players can each earn bonus independently
- Bonus cards must have "Bonus" power text (not just any card at those denominations)
- Player who went out can earn bonus
- Player who didn't go out can earn bonus (if they have the cards in play pile)
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


def make_bonus_card(card_id: int, denomination: int) -> CardInstance:
    """Helper to create a Bonus CardInstance."""
    return CardInstance(
        card_id=card_id,
        card_name=f"Bonus_Tribble_{denomination}",
        denomination=denomination,
        power_text="Bonus",
        expansion_id=2,
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


class TestBonusScoring:
    """Tests for calculate_bonus_scores method."""

    def test_all_four_bonus_denominations_awards_100000(self, score_service):
        """Player with all four Bonus denominations (1, 10, 100, 1000) gets 100000 points."""
        state = make_game_state(num_players=2)
        state.players[0].play_pile = [
            make_bonus_card(1, 1),
            make_bonus_card(2, 10),
            make_bonus_card(3, 100),
            make_bonus_card(4, 1000),
        ]

        bonus_scores = score_service.calculate_bonus_scores(state)

        assert bonus_scores[1] == 100000

    def test_missing_one_denomination_no_bonus(self, score_service):
        """Player missing one Bonus denomination gets no bonus."""
        state = make_game_state(num_players=2)
        # Missing denomination 1000
        state.players[0].play_pile = [
            make_bonus_card(1, 1),
            make_bonus_card(2, 10),
            make_bonus_card(3, 100),
        ]

        bonus_scores = score_service.calculate_bonus_scores(state)

        assert bonus_scores[1] == 0

    def test_decked_player_no_bonus_even_with_all_cards(self, score_service):
        """Decked player gets no bonus even if play pile has all four Bonus cards."""
        state = make_game_state(num_players=2)
        state.players[0].is_decked = True
        state.players[0].play_pile = [
            make_bonus_card(1, 1),
            make_bonus_card(2, 10),
            make_bonus_card(3, 100),
            make_bonus_card(4, 1000),
        ]

        bonus_scores = score_service.calculate_bonus_scores(state)

        assert bonus_scores[1] == 0

    def test_multiple_players_earn_bonus_independently(self, score_service):
        """Multiple players can each earn the bonus independently."""
        state = make_game_state(num_players=3)
        # Player 1 has all four
        state.players[0].play_pile = [
            make_bonus_card(1, 1),
            make_bonus_card(2, 10),
            make_bonus_card(3, 100),
            make_bonus_card(4, 1000),
        ]
        # Player 2 has all four
        state.players[1].play_pile = [
            make_bonus_card(5, 1),
            make_bonus_card(6, 10),
            make_bonus_card(7, 100),
            make_bonus_card(8, 1000),
        ]
        # Player 3 does not
        state.players[2].play_pile = [
            make_bonus_card(9, 1),
            make_bonus_card(10, 10),
        ]

        bonus_scores = score_service.calculate_bonus_scores(state)

        assert bonus_scores[1] == 100000
        assert bonus_scores[2] == 100000
        assert bonus_scores[3] == 0

    def test_non_bonus_power_cards_at_required_denominations_no_bonus(self, score_service):
        """Cards at required denominations but without 'Bonus' power text don't count."""
        state = make_game_state(num_players=2)
        state.players[0].play_pile = [
            make_card(1, denomination=1, power="Go"),
            make_card(2, denomination=10, power="Skip"),
            make_card(3, denomination=100, power="Poison"),
            make_card(4, denomination=1000, power="Reverse"),
        ]

        bonus_scores = score_service.calculate_bonus_scores(state)

        assert bonus_scores[1] == 0

    def test_player_who_went_out_can_earn_bonus(self, score_service):
        """Player who went out can earn the bonus if they have all four Bonus cards."""
        state = make_game_state(num_players=2)
        state.players[0].has_gone_out = True
        state.players[0].play_pile = [
            make_bonus_card(1, 1),
            make_bonus_card(2, 10),
            make_bonus_card(3, 100),
            make_bonus_card(4, 1000),
        ]

        bonus_scores = score_service.calculate_bonus_scores(state)

        assert bonus_scores[1] == 100000

    def test_player_who_did_not_go_out_can_earn_bonus(self, score_service):
        """Player who didn't go out can earn bonus if they have all four Bonus cards in play pile."""
        state = make_game_state(num_players=2)
        state.players[0].has_gone_out = False
        state.players[0].play_pile = [
            make_bonus_card(1, 1),
            make_bonus_card(2, 10),
            make_bonus_card(3, 100),
            make_bonus_card(4, 1000),
        ]

        bonus_scores = score_service.calculate_bonus_scores(state)

        assert bonus_scores[1] == 100000

    def test_bonus_power_text_case_insensitive(self, score_service):
        """Bonus power text check is case-insensitive."""
        state = make_game_state(num_players=2)
        state.players[0].play_pile = [
            CardInstance(card_id=1, card_name="B1", denomination=1, power_text="BONUS", expansion_id=2),
            CardInstance(card_id=2, card_name="B2", denomination=10, power_text="bonus", expansion_id=2),
            CardInstance(card_id=3, card_name="B3", denomination=100, power_text="Bonus", expansion_id=2),
            CardInstance(card_id=4, card_name="B4", denomination=1000, power_text="bOnUs", expansion_id=2),
        ]

        bonus_scores = score_service.calculate_bonus_scores(state)

        assert bonus_scores[1] == 100000

    def test_extra_bonus_cards_still_awards_bonus(self, score_service):
        """Having extra Bonus cards (duplicates) still awards the bonus."""
        state = make_game_state(num_players=2)
        state.players[0].play_pile = [
            make_bonus_card(1, 1),
            make_bonus_card(2, 1),  # duplicate denomination 1
            make_bonus_card(3, 10),
            make_bonus_card(4, 100),
            make_bonus_card(5, 1000),
        ]

        bonus_scores = score_service.calculate_bonus_scores(state)

        assert bonus_scores[1] == 100000

    def test_bonus_card_at_10000_does_not_count(self, score_service):
        """Bonus card at denomination 10000 does not contribute to the bonus requirement."""
        state = make_game_state(num_players=2)
        # Has 10000 instead of 1000
        state.players[0].play_pile = [
            make_bonus_card(1, 1),
            make_bonus_card(2, 10),
            make_bonus_card(3, 100),
            make_bonus_card(4, 10000),
        ]

        bonus_scores = score_service.calculate_bonus_scores(state)

        assert bonus_scores[1] == 0
