"""Tests for the AI Controller decision-making.

Tests cover AI requirements:
- 4.7: Computer players use automated decision-making that follows all game rules
- 4.8: Computer players select valid plays from hand or draw when no valid play available
- 21.4: AI_Substitute uses same strategy as permanent computer players
- 21.5: AI_Substitute operates on disconnected player's existing state
"""

import sys
import os

import pytest

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ai.controller import AIController, BENEFICIAL_POWERS, OFFENSIVE_POWERS
from models import CardInstance, GameState, PendingDraw, PendingPower, PlayerState


def make_card(
    card_id: int = 1,
    denomination: int = 1,
    power: str = "Go",
    expansion_id: int = 1,
) -> CardInstance:
    """Helper to create a CardInstance for testing."""
    return CardInstance(
        card_id=card_id,
        card_name=f"Tribble_{card_id}",
        denomination=denomination,
        power_text=power,
        expansion_id=expansion_id,
    )


def make_player(
    player_id: int = 1,
    username: str = "Player_1",
    is_computer: bool = True,
    hand: list = None,
    draw_deck: list = None,
    play_pile: list = None,
    discard_pile: list = None,
    cumulative_score: int = 0,
    seat_position: int = 1,
) -> PlayerState:
    """Helper to create a PlayerState for testing."""
    return PlayerState(
        player_id=player_id,
        username=username,
        is_computer=is_computer,
        hand=hand if hand is not None else [],
        draw_deck=draw_deck if draw_deck is not None else [],
        play_pile=play_pile if play_pile is not None else [],
        discard_pile=discard_pile if discard_pile is not None else [],
        cumulative_score=cumulative_score,
        seat_position=seat_position,
    )


def make_game_state(
    players: list = None,
    current_player_index: int = 0,
    current_sequence: int = 1,
    last_played_denomination: int = None,
    sequence_broken: bool = False,
    pending_draw: PendingDraw = None,
    pending_power: PendingPower = None,
) -> GameState:
    """Helper to create a GameState for testing."""
    if players is None:
        players = [
            make_player(player_id=1, seat_position=1),
            make_player(player_id=2, seat_position=2, cumulative_score=50),
            make_player(player_id=3, seat_position=3, cumulative_score=100),
            make_player(player_id=4, seat_position=4, cumulative_score=25),
        ]
    return GameState(
        game_id="test-game",
        players=players,
        current_player_index=current_player_index,
        current_sequence=current_sequence,
        last_played_denomination=last_played_denomination,
        sequence_broken=sequence_broken,
        pending_draw=pending_draw,
        pending_power=pending_power,
    )


@pytest.fixture
def ai():
    """Create a fresh AIController instance."""
    return AIController()


class TestAIReturnsValidAction:
    """Test that AI always returns a valid action type."""

    def test_returns_draw_when_hand_empty(self, ai):
        """AI draws when hand is empty."""
        state = make_game_state()
        state.players[0].hand = []
        action = ai.choose_action(state, player_id=1)
        assert action["type"] == "draw_card"

    def test_returns_play_card_when_matching_card_available(self, ai):
        """AI plays a card when a matching card is in hand."""
        card = make_card(card_id=10, denomination=1, power="Go")
        state = make_game_state(current_sequence=1)
        state.players[0].hand = [card]
        action = ai.choose_action(state, player_id=1)
        assert action["type"] == "play_card"
        assert action["card_id"] == 10

    def test_returns_draw_when_no_matching_card(self, ai):
        """AI draws when no card in hand matches the current sequence."""
        card = make_card(card_id=10, denomination=100, power="Go")
        state = make_game_state(current_sequence=1)
        state.players[0].hand = [card]
        action = ai.choose_action(state, player_id=1)
        assert action["type"] == "draw_card"

    def test_returns_valid_action_for_unknown_player(self, ai):
        """AI returns draw_card for a player not in the game."""
        state = make_game_state()
        action = ai.choose_action(state, player_id=999)
        assert action["type"] == "draw_card"


class TestAIPlaysMatchingCard:
    """Test that AI correctly identifies and plays matching cards."""

    def test_plays_card_matching_current_sequence(self, ai):
        """AI plays a card whose denomination matches current_sequence."""
        card_10 = make_card(card_id=1, denomination=10, power="Discard")
        card_100 = make_card(card_id=2, denomination=100, power="Go")
        state = make_game_state(current_sequence=10)
        state.players[0].hand = [card_10, card_100]
        action = ai.choose_action(state, player_id=1)
        assert action["type"] == "play_card"
        assert action["card_id"] == 1

    def test_plays_one_denomination_after_sequence_break(self, ai):
        """AI plays a 1-denomination card when sequence is broken."""
        card_1 = make_card(card_id=5, denomination=1, power="Go")
        card_100 = make_card(card_id=6, denomination=100, power="Skip")
        state = make_game_state(current_sequence=100, sequence_broken=True)
        state.players[0].hand = [card_1, card_100]
        action = ai.choose_action(state, player_id=1)
        assert action["type"] == "play_card"
        # Should play either the 1-denomination card or the 100 (both valid)
        assert action["card_id"] in (5, 6)

    def test_plays_advance_card_after_sequence_break(self, ai):
        """AI plays an Advance card when sequence is broken."""
        card_advance = make_card(card_id=7, denomination=10000, power="Advance")
        state = make_game_state(current_sequence=100, sequence_broken=True)
        state.players[0].hand = [card_advance]
        action = ai.choose_action(state, player_id=1)
        assert action["type"] == "play_card"
        assert action["card_id"] == 7

    def test_plays_clone_matching_last_played(self, ai):
        """AI plays a Clone card when its denomination matches last_played_denomination."""
        card_clone = make_card(card_id=8, denomination=100, power="Clone")
        state = make_game_state(
            current_sequence=1000,
            last_played_denomination=100,
        )
        state.players[0].hand = [card_clone]
        action = ai.choose_action(state, player_id=1)
        assert action["type"] == "play_card"
        assert action["card_id"] == 8

    def test_does_not_play_clone_when_denomination_mismatch(self, ai):
        """AI does not play Clone when denomination doesn't match last_played."""
        card_clone = make_card(card_id=8, denomination=100, power="Clone")
        state = make_game_state(
            current_sequence=1000,
            last_played_denomination=10,
        )
        state.players[0].hand = [card_clone]
        action = ai.choose_action(state, player_id=1)
        assert action["type"] == "draw_card"


class TestAIDrawsWhenNoValidPlay:
    """Test that AI draws when no valid play is available."""

    def test_draws_when_no_matching_denomination(self, ai):
        """AI draws when hand has no cards matching current sequence."""
        cards = [
            make_card(card_id=1, denomination=10, power="Go"),
            make_card(card_id=2, denomination=100, power="Skip"),
            make_card(card_id=3, denomination=1000, power="Reverse"),
        ]
        state = make_game_state(current_sequence=100000)
        state.players[0].hand = cards
        action = ai.choose_action(state, player_id=1)
        assert action["type"] == "draw_card"

    def test_draws_when_hand_empty(self, ai):
        """AI draws when hand is completely empty."""
        state = make_game_state(current_sequence=1)
        state.players[0].hand = []
        action = ai.choose_action(state, player_id=1)
        assert action["type"] == "draw_card"


class TestAIHandlesPendingDraw:
    """Test that AI handles pending draw correctly."""

    def test_plays_matching_drawn_card(self, ai):
        """AI plays a drawn card that matches the sequence."""
        drawn_card = make_card(card_id=20, denomination=10, power="Go")
        pending = PendingDraw(
            player_id=1,
            card=drawn_card,
            matches_sequence=True,
        )
        state = make_game_state(current_sequence=10, pending_draw=pending)
        state.players[0].hand = [drawn_card]
        action = ai.choose_action(state, player_id=1)
        assert action["type"] == "play_card"
        assert action["card_id"] == 20

    def test_accepts_non_matching_drawn_card(self, ai):
        """AI accepts a drawn card that doesn't match the sequence."""
        drawn_card = make_card(card_id=21, denomination=100, power="Skip")
        pending = PendingDraw(
            player_id=1,
            card=drawn_card,
            matches_sequence=False,
        )
        state = make_game_state(current_sequence=10, pending_draw=pending)
        state.players[0].hand = [drawn_card]
        action = ai.choose_action(state, player_id=1)
        assert action["type"] == "accept_draw"

    def test_ignores_other_players_pending_draw(self, ai):
        """AI ignores pending draw for a different player."""
        drawn_card = make_card(card_id=22, denomination=10, power="Go")
        pending = PendingDraw(
            player_id=2,  # Different player
            card=drawn_card,
            matches_sequence=True,
        )
        card_in_hand = make_card(card_id=30, denomination=1, power="Discard")
        state = make_game_state(current_sequence=1, pending_draw=pending)
        state.players[0].hand = [card_in_hand]
        action = ai.choose_action(state, player_id=1)
        # Should proceed with normal turn logic
        assert action["type"] == "play_card"
        assert action["card_id"] == 30


class TestAIActivatesBeneficialPowers:
    """Test that AI activates beneficial powers."""

    def test_activates_go_power(self, ai):
        """AI activates Go power (extra turn)."""
        card = make_card(card_id=10, denomination=1, power="Go")
        state = make_game_state(current_sequence=1)
        state.players[0].hand = [card]
        action = ai.choose_action(state, player_id=1)
        assert action["type"] == "play_card"
        assert action["activate_power"] is True

    def test_activates_reverse_power(self, ai):
        """AI activates Reverse power."""
        card = make_card(card_id=11, denomination=1, power="Reverse")
        state = make_game_state(current_sequence=1)
        state.players[0].hand = [card]
        action = ai.choose_action(state, player_id=1)
        assert action["type"] == "play_card"
        assert action["activate_power"] is True

    def test_activates_discard_power(self, ai):
        """AI activates Discard power."""
        card = make_card(card_id=12, denomination=1, power="Discard")
        state = make_game_state(current_sequence=1)
        state.players[0].hand = [card, make_card(card_id=99, denomination=100)]
        action = ai.choose_action(state, player_id=1)
        assert action["type"] == "play_card"
        assert action["activate_power"] is True

    def test_does_not_activate_passive_power(self, ai):
        """AI does not try to activate passive powers like Bonus."""
        card = make_card(card_id=13, denomination=1, power="Bonus")
        state = make_game_state(current_sequence=1)
        state.players[0].hand = [card]
        action = ai.choose_action(state, player_id=1)
        assert action["type"] == "play_card"
        assert action["activate_power"] is False

    def test_does_not_activate_clone_power(self, ai):
        """AI does not try to activate Clone power (it's passive)."""
        card = make_card(card_id=14, denomination=10, power="Clone")
        state = make_game_state(
            current_sequence=1000,
            last_played_denomination=10,
        )
        state.players[0].hand = [card]
        action = ai.choose_action(state, player_id=1)
        assert action["type"] == "play_card"
        assert action["activate_power"] is False


class TestAITargetsOpponents:
    """Test that AI targets opponents correctly for offensive powers."""

    def test_targets_highest_score_opponent(self, ai):
        """AI targets the opponent with the highest cumulative score."""
        # Player 3 has score 100 (highest)
        pending = PendingPower(
            player_index=0,
            card=make_card(card_id=50, denomination=1000, power="Poison"),
            power_name="poison",
            phase="choose_target",
            options=[1, 2, 3],  # Valid target indices
        )
        state = make_game_state(pending_power=pending)
        # Ensure player 3 (index 2) has highest score
        state.players[0].cumulative_score = 0
        state.players[1].cumulative_score = 50
        state.players[2].cumulative_score = 100
        state.players[3].cumulative_score = 25

        action = ai.choose_action(state, player_id=1)
        assert action["type"] == "power_choice"
        assert action["target_player_index"] == 2  # Player at index 2 has score 100

    def test_targets_from_valid_options_only(self, ai):
        """AI only targets from the valid options list."""
        pending = PendingPower(
            player_index=0,
            card=make_card(card_id=50, denomination=1000, power="Poison"),
            power_name="poison",
            phase="choose_target",
            options=[1, 3],  # Only indices 1 and 3 are valid
        )
        state = make_game_state(pending_power=pending)
        state.players[0].cumulative_score = 0
        state.players[1].cumulative_score = 50
        state.players[2].cumulative_score = 200  # Highest but not in options
        state.players[3].cumulative_score = 75

        action = ai.choose_action(state, player_id=1)
        assert action["type"] == "power_choice"
        assert action["target_player_index"] == 3  # Index 3 has score 75 (highest in options)


class TestAIPendingPowerDecisions:
    """Test AI decisions for pending power activate/decline."""

    def test_activates_beneficial_power_prompt(self, ai):
        """AI activates when prompted for a beneficial power."""
        pending = PendingPower(
            player_index=0,
            card=make_card(card_id=50, denomination=1, power="Go"),
            power_name="go",
            phase="activate_or_decline",
        )
        state = make_game_state(pending_power=pending)
        action = ai.choose_action(state, player_id=1)
        assert action["type"] == "power_choice"
        assert action["choice"] == "activate"

    def test_activates_offensive_power_prompt(self, ai):
        """AI activates when prompted for an offensive power."""
        pending = PendingPower(
            player_index=0,
            card=make_card(card_id=51, denomination=1000, power="Poison"),
            power_name="poison",
            phase="activate_or_decline",
        )
        state = make_game_state(pending_power=pending)
        action = ai.choose_action(state, player_id=1)
        assert action["type"] == "power_choice"
        assert action["choice"] == "activate"

    def test_declines_avalanche_with_few_cards(self, ai):
        """AI declines Avalanche when hand has fewer than 4 cards."""
        pending = PendingPower(
            player_index=0,
            card=make_card(card_id=52, denomination=100000, power="Avalanche"),
            power_name="avalanche",
            phase="activate_or_decline",
        )
        state = make_game_state(pending_power=pending)
        state.players[0].hand = [make_card(card_id=i) for i in range(3)]
        action = ai.choose_action(state, player_id=1)
        assert action["type"] == "power_choice"
        assert action["choice"] == "decline"

    def test_activates_avalanche_with_enough_cards(self, ai):
        """AI activates Avalanche when hand has 4+ cards."""
        pending = PendingPower(
            player_index=0,
            card=make_card(card_id=52, denomination=100000, power="Avalanche"),
            power_name="avalanche",
            phase="activate_or_decline",
        )
        state = make_game_state(pending_power=pending)
        state.players[0].hand = [make_card(card_id=i) for i in range(5)]
        action = ai.choose_action(state, player_id=1)
        assert action["type"] == "power_choice"
        assert action["choice"] == "activate"


class TestAICardChoiceStrategy:
    """Test AI card selection strategy."""

    def test_prefers_go_power_card(self, ai):
        """AI prefers a card with Go power over other matching cards."""
        card_go = make_card(card_id=1, denomination=1, power="Go")
        card_plain = make_card(card_id=2, denomination=1, power="Bonus")
        state = make_game_state(current_sequence=1)
        state.players[0].hand = [card_plain, card_go]
        action = ai.choose_action(state, player_id=1)
        assert action["card_id"] == 1  # Go card preferred

    def test_prefers_higher_denomination_among_equal_powers(self, ai):
        """AI prefers higher denomination when powers are equal."""
        # Both match sequence (sequence_broken allows 1-denom cards)
        # But if current_sequence is 1, both are valid
        card_low = make_card(card_id=1, denomination=1, power="Bonus")
        card_high = make_card(card_id=2, denomination=1, power="Bonus")
        # Make a scenario where both are valid but have different denominations
        # Use sequence_broken where both 1-denom and current_sequence match
        state = make_game_state(current_sequence=100, sequence_broken=True)
        card_1 = make_card(card_id=1, denomination=1, power="Bonus")
        card_100 = make_card(card_id=2, denomination=100, power="Bonus")
        state.players[0].hand = [card_1, card_100]
        action = ai.choose_action(state, player_id=1)
        # card_100 matches current_sequence (higher priority) and has higher denomination
        assert action["card_id"] == 2

    def test_discard_power_chooses_lowest_denomination(self, ai):
        """AI discards the lowest denomination card when using Discard power."""
        pending = PendingPower(
            player_index=0,
            card=make_card(card_id=50, denomination=1, power="Discard"),
            power_name="discard",
            phase="choose_target",
        )
        state = make_game_state(pending_power=pending)
        state.players[0].hand = [
            make_card(card_id=10, denomination=100),
            make_card(card_id=11, denomination=1),
            make_card(card_id=12, denomination=1000),
        ]
        action = ai.choose_action(state, player_id=1)
        assert action["type"] == "power_choice"
        assert action["card_id"] == 11  # Lowest denomination


class TestAISubstituteBehavior:
    """Test that AI works correctly for AI_Substitute (disconnected player) seats."""

    def test_operates_on_existing_player_state(self, ai):
        """AI_Substitute uses the disconnected player's existing hand."""
        # Simulate a human player who disconnected
        player = make_player(
            player_id=5,
            username="DisconnectedPlayer",
            is_computer=False,  # Originally human
            hand=[make_card(card_id=100, denomination=10, power="Go")],
            draw_deck=[make_card(card_id=101, denomination=1)],
            cumulative_score=75,
        )
        state = make_game_state(
            players=[
                player,
                make_player(player_id=2, seat_position=2),
                make_player(player_id=3, seat_position=3),
                make_player(player_id=4, seat_position=4),
            ],
            current_sequence=10,
        )
        # AI acts for the disconnected player
        action = ai.choose_action(state, player_id=5)
        assert action["type"] == "play_card"
        assert action["card_id"] == 100

    def test_same_strategy_for_computer_and_substitute(self, ai):
        """AI uses the same strategy regardless of is_computer flag."""
        hand = [make_card(card_id=100, denomination=10, power="Go")]

        # Computer player
        computer_player = make_player(
            player_id=1, is_computer=True, hand=list(hand)
        )
        state_computer = make_game_state(
            players=[
                computer_player,
                make_player(player_id=2, seat_position=2),
                make_player(player_id=3, seat_position=3),
                make_player(player_id=4, seat_position=4),
            ],
            current_sequence=10,
        )

        # Human player (AI substitute)
        human_player = make_player(
            player_id=1, is_computer=False, hand=list(hand)
        )
        state_substitute = make_game_state(
            players=[
                human_player,
                make_player(player_id=2, seat_position=2),
                make_player(player_id=3, seat_position=3),
                make_player(player_id=4, seat_position=4),
            ],
            current_sequence=10,
        )

        action_computer = ai.choose_action(state_computer, player_id=1)
        action_substitute = ai.choose_action(state_substitute, player_id=1)

        # Both should make the same decision
        assert action_computer == action_substitute
