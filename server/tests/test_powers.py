"""Unit tests for the PowerResolver framework and base powers.

Tests cover:
- Power activation prompt logic (activate or decline)
- Discard power: choose card from hand → move to discard pile
- Go power: grant additional turn
- Skip power: skip next player in current direction
- Poison power: target selection, discard top of target's draw deck, score denomination
- Rescue power: browse discard pile, select card → top of draw deck or play immediately
- Reverse power: toggle direction
- Clone power: no activation effect (handled by _is_valid_play)

Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest

from models import CardInstance, GameState, PendingPower, PlayerState
from game.powers.resolver import (
    ACTIVATABLE_POWERS,
    IMMEDIATE_POWERS,
    POWERS_NEEDING_TARGET,
    PowerResolver,
)
from scoring.service import ScoreService


# --- Test Helpers ---


def make_card(
    card_id: int = 1,
    card_name: str = "Test Card",
    denomination: int = 100,
    power_text: str = "Go",
    expansion_id: int = 1,
) -> CardInstance:
    """Create a CardInstance for testing."""
    return CardInstance(
        card_id=card_id,
        card_name=card_name,
        denomination=denomination,
        power_text=power_text,
        expansion_id=expansion_id,
    )


def make_player(
    player_id: int = 1,
    username: str = "Player1",
    hand: list = None,
    draw_deck: list = None,
    discard_pile: list = None,
    play_pile: list = None,
    seat_position: int = 1,
) -> PlayerState:
    """Create a PlayerState for testing."""
    return PlayerState(
        player_id=player_id,
        username=username,
        is_computer=False,
        hand=hand if hand is not None else [],
        draw_deck=draw_deck if draw_deck is not None else [],
        discard_pile=discard_pile if discard_pile is not None else [],
        play_pile=play_pile if play_pile is not None else [],
        cumulative_score=0,
        is_decked=False,
        has_gone_out=False,
        seat_position=seat_position,
    )


def make_game_state(
    players: list = None,
    current_player_index: int = 0,
    direction: int = 1,
    current_sequence: int = 100,
) -> GameState:
    """Create a GameState for testing."""
    if players is None:
        players = [
            make_player(player_id=1, username="Alice", seat_position=1),
            make_player(player_id=2, username="Bob", seat_position=2),
            make_player(player_id=3, username="Charlie", seat_position=3),
        ]
    return GameState(
        game_id="test-game",
        players=players,
        current_player_index=current_player_index,
        direction=direction,
        current_sequence=current_sequence,
    )


# --- Tests for get_activatable_power ---


class TestGetActivatablePower:
    """Tests for PowerResolver.get_activatable_power."""

    def setup_method(self):
        self.resolver = PowerResolver()

    def test_simple_activatable_power(self):
        """Simple activatable powers are detected."""
        for power in ACTIVATABLE_POWERS:
            card = make_card(power_text=power.capitalize())
            assert self.resolver.get_activatable_power(card) == power

    def test_clone_not_activatable(self):
        """Clone has no activation effect."""
        card = make_card(power_text="Clone")
        assert self.resolver.get_activatable_power(card) is None

    def test_compound_power_with_clone(self):
        """Compound power with Clone returns the non-Clone component."""
        card = make_card(power_text="Clone & Reverse")
        assert self.resolver.get_activatable_power(card) == "reverse"

    def test_compound_power_without_clone(self):
        """Compound power without Clone returns both powers joined by &."""
        card = make_card(power_text="Go & Skip")
        result = self.resolver.get_activatable_power(card)
        assert result == "go&skip"

    def test_non_activatable_power(self):
        """Non-activatable powers return None."""
        card = make_card(power_text="Bonus")
        assert self.resolver.get_activatable_power(card) is None

    def test_empty_power_text(self):
        """Empty power text returns None."""
        card = make_card(power_text="")
        assert self.resolver.get_activatable_power(card) is None


# --- Tests for create_power_prompt ---


class TestCreatePowerPrompt:
    """Tests for PowerResolver.create_power_prompt (Requirement 9.1)."""

    def setup_method(self):
        self.resolver = PowerResolver()

    def test_activatable_power_creates_prompt(self):
        """Playing a card with an activatable power creates a pending power prompt."""
        state = make_game_state()
        card = make_card(power_text="Go")

        events = self.resolver.create_power_prompt(state, 0, card)

        assert events is not None
        assert len(events) == 1
        assert events[0]["type"] == "power_prompt"
        assert events[0]["prompt_type"] == "activate_or_decline"
        assert events[0]["power_name"] == "go"
        assert state.pending_power is not None
        assert state.pending_power.power_name == "go"
        assert state.pending_power.phase == "activate_or_decline"

    def test_non_activatable_power_no_prompt(self):
        """Playing a card without an activatable power returns None."""
        state = make_game_state()
        card = make_card(power_text="Clone")

        events = self.resolver.create_power_prompt(state, 0, card)

        assert events is None
        assert state.pending_power is None

    def test_bonus_power_no_prompt(self):
        """Bonus power has no activation prompt."""
        state = make_game_state()
        card = make_card(power_text="Bonus")

        events = self.resolver.create_power_prompt(state, 0, card)

        assert events is None


# --- Tests for declining a power ---


class TestDeclinePower:
    """Tests for declining a power activation (Requirement 9.1)."""

    def setup_method(self):
        self.resolver = PowerResolver()

    def test_decline_clears_pending_power(self):
        """Declining a power clears the pending power state."""
        state = make_game_state()
        card = make_card(power_text="Go")
        self.resolver.create_power_prompt(state, 0, card)

        events = self.resolver.handle_power_choice(state, 0, {"choice": "decline"})

        assert isinstance(events, list)
        assert events[0]["type"] == "power_declined"
        assert events[0]["power_name"] == "go"
        assert state.pending_power is None

    def test_decline_does_not_trigger_effect(self):
        """Declining a power does not change game state beyond clearing pending."""
        state = make_game_state(direction=1)
        card = make_card(power_text="Reverse")
        self.resolver.create_power_prompt(state, 0, card)

        self.resolver.handle_power_choice(state, 0, {"choice": "decline"})

        # Direction should not have changed
        assert state.direction == 1


# --- Tests for Go power ---


class TestGoPower:
    """Tests for the Go power (Requirement 9.3)."""

    def setup_method(self):
        self.resolver = PowerResolver()

    def test_go_keeps_active_player(self):
        """Go power keeps the active player for the next turn."""
        state = make_game_state(current_player_index=0)
        card = make_card(power_text="Go")
        self.resolver.create_power_prompt(state, 0, card)

        # Simulate that turn was already advanced (as engine does)
        state.current_player_index = 1

        events = self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        assert isinstance(events, list)
        assert events[0]["type"] == "power_activated"
        assert events[0]["power_name"] == "go"
        assert events[0]["effect"] == "additional_turn"
        # Player 0 should be active again
        assert state.current_player_index == 0


# --- Tests for Skip power ---


class TestSkipPower:
    """Tests for the Skip power (Requirement 9.4)."""

    def setup_method(self):
        self.resolver = PowerResolver()

    def test_skip_advances_past_next_player(self):
        """Skip power skips the next player in current direction."""
        state = make_game_state(current_player_index=1, direction=1)
        card = make_card(power_text="Skip")
        self.resolver.create_power_prompt(state, 0, card)

        events = self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        assert isinstance(events, list)
        assert events[0]["type"] == "power_activated"
        assert events[0]["power_name"] == "skip"
        # From current_player_index=1, direction=1:
        # Next player is index 2 (Charlie, player_id=3) — gets skipped
        # After skip, lands on index 0 (Alice, player_id=1)
        assert events[0]["skipped_player_id"] == 3  # Charlie (index 2) is skipped
        assert state.current_player_index == 0  # Alice (index 0) is next

    def test_skip_respects_direction(self):
        """Skip power respects counterclockwise direction."""
        state = make_game_state(current_player_index=1, direction=-1)
        card = make_card(power_text="Skip")
        self.resolver.create_power_prompt(state, 0, card)

        events = self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        assert isinstance(events, list)
        # In counterclockwise from index 1: next is index 0 (Alice, player_id=1), then index 2 (Charlie, player_id=3)
        assert events[0]["skipped_player_id"] == 1  # Alice (index 0) is skipped
        assert state.current_player_index == 2  # Charlie (index 2) is next


# --- Tests for Reverse power ---


class TestReversePower:
    """Tests for the Reverse power (Requirement 9.7)."""

    def setup_method(self):
        self.resolver = PowerResolver()

    def test_reverse_toggles_clockwise_to_counterclockwise(self):
        """Reverse toggles direction from clockwise to counterclockwise."""
        state = make_game_state(direction=1)
        card = make_card(power_text="Reverse")
        self.resolver.create_power_prompt(state, 0, card)

        events = self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        assert isinstance(events, list)
        assert events[0]["type"] == "power_activated"
        assert events[0]["power_name"] == "reverse"
        assert state.direction == -1

    def test_reverse_toggles_counterclockwise_to_clockwise(self):
        """Reverse toggles direction from counterclockwise to clockwise."""
        state = make_game_state(direction=-1)
        card = make_card(power_text="Reverse")
        self.resolver.create_power_prompt(state, 0, card)

        events = self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        assert state.direction == 1

    def test_reverse_twice_restores_original(self):
        """Activating Reverse twice restores the original direction."""
        state = make_game_state(direction=1)

        # First reverse
        card1 = make_card(card_id=1, power_text="Reverse")
        self.resolver.create_power_prompt(state, 0, card1)
        self.resolver.handle_power_choice(state, 0, {"choice": "activate"})
        assert state.direction == -1

        # Second reverse
        card2 = make_card(card_id=2, power_text="Reverse")
        self.resolver.create_power_prompt(state, 0, card2)
        self.resolver.handle_power_choice(state, 0, {"choice": "activate"})
        assert state.direction == 1


# --- Tests for Discard power ---


class TestDiscardPower:
    """Tests for the Discard power (Requirement 9.2)."""

    def setup_method(self):
        self.resolver = PowerResolver()

    def test_discard_moves_card_from_hand_to_discard_pile(self):
        """Discard power moves chosen card from hand to discard pile."""
        hand_card = make_card(card_id=10, card_name="Tribble 10", denomination=10)
        players = [
            make_player(player_id=1, hand=[hand_card], seat_position=1),
            make_player(player_id=2, seat_position=2),
            make_player(player_id=3, seat_position=3),
        ]
        state = make_game_state(players=players)
        card = make_card(power_text="Discard")
        self.resolver.create_power_prompt(state, 0, card)

        # Activate
        events = self.resolver.handle_power_choice(state, 0, {"choice": "activate"})
        assert isinstance(events, list)
        assert events[0]["type"] == "power_prompt"
        assert events[0]["prompt_type"] == "choose_card_from_hand"

        # Choose card
        events = self.resolver.handle_power_choice(state, 0, {"card_id": 10})

        assert isinstance(events, list)
        assert events[0]["type"] == "power_activated"
        assert events[0]["power_name"] == "discard"
        assert events[0]["discarded_card_id"] == 10
        # Card moved from hand to discard pile
        assert len(state.players[0].hand) == 0
        assert len(state.players[0].discard_pile) == 1
        assert state.players[0].discard_pile[0].card_id == 10

    def test_discard_invalid_card_id(self):
        """Discard power rejects card not in hand."""
        hand_card = make_card(card_id=10)
        players = [
            make_player(player_id=1, hand=[hand_card], seat_position=1),
            make_player(player_id=2, seat_position=2),
            make_player(player_id=3, seat_position=3),
        ]
        state = make_game_state(players=players)
        card = make_card(power_text="Discard")
        self.resolver.create_power_prompt(state, 0, card)
        self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        result = self.resolver.handle_power_choice(state, 0, {"card_id": 999})

        assert isinstance(result, tuple)
        assert result[0] == "card_not_in_hand"


# --- Tests for Poison power ---


class TestPoisonPower:
    """Tests for the Poison power (Requirement 9.5)."""

    def setup_method(self):
        self.resolver = PowerResolver()

    def test_poison_discards_top_of_target_draw_deck_and_scores(self):
        """Poison discards top of target's draw deck and scores denomination."""
        target_top_card = make_card(card_id=20, denomination=1000)
        players = [
            make_player(player_id=1, seat_position=1),
            make_player(
                player_id=2,
                draw_deck=[target_top_card, make_card(card_id=21)],
                seat_position=2,
            ),
            make_player(player_id=3, seat_position=3),
        ]
        state = make_game_state(players=players)
        card = make_card(power_text="Poison")
        self.resolver.create_power_prompt(state, 0, card)

        # Activate
        events = self.resolver.handle_power_choice(state, 0, {"choice": "activate"})
        assert isinstance(events, list)
        assert events[0]["type"] == "power_prompt"
        assert events[0]["prompt_type"] == "choose_target_player"

        # Choose target (player index 1)
        events = self.resolver.handle_power_choice(
            state, 0, {"target_player_index": 1}
        )

        assert isinstance(events, list)
        assert events[0]["type"] == "power_activated"
        assert events[0]["power_name"] == "poison"
        assert events[0]["points_scored"] == 1000
        # Target's draw deck lost top card
        assert len(state.players[1].draw_deck) == 1
        # Top card moved to target's discard pile
        assert state.players[1].discard_pile[0].card_id == 20
        # Active player scored
        assert state.players[0].cumulative_score == 1000

    def test_poison_cannot_target_self(self):
        """Poison cannot target the active player."""
        players = [
            make_player(player_id=1, draw_deck=[make_card()], seat_position=1),
            make_player(player_id=2, draw_deck=[make_card()], seat_position=2),
            make_player(player_id=3, seat_position=3),
        ]
        state = make_game_state(players=players)
        card = make_card(power_text="Poison")
        self.resolver.create_power_prompt(state, 0, card)
        self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        result = self.resolver.handle_power_choice(
            state, 0, {"target_player_index": 0}
        )

        assert isinstance(result, tuple)
        assert result[0] == "invalid_target"

    def test_poison_cannot_target_empty_draw_deck(self):
        """Poison cannot target a player with empty draw deck."""
        players = [
            make_player(player_id=1, seat_position=1),
            make_player(player_id=2, draw_deck=[], seat_position=2),
            make_player(player_id=3, seat_position=3),
        ]
        state = make_game_state(players=players)
        card = make_card(power_text="Poison")
        self.resolver.create_power_prompt(state, 0, card)
        self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        result = self.resolver.handle_power_choice(
            state, 0, {"target_player_index": 1}
        )

        assert isinstance(result, tuple)
        assert result[0] == "invalid_target"


# --- Tests for Rescue power ---


class TestRescuePower:
    """Tests for the Rescue power (Requirement 9.6)."""

    def setup_method(self):
        self.resolver = PowerResolver()

    def test_rescue_places_card_on_top_of_draw_deck(self):
        """Rescue places chosen card face-down on top of draw deck."""
        discard_card = make_card(card_id=30, card_name="Rescued Card", denomination=10)
        existing_draw = make_card(card_id=31)
        players = [
            make_player(
                player_id=1,
                discard_pile=[discard_card],
                draw_deck=[existing_draw],
                seat_position=1,
            ),
            make_player(player_id=2, seat_position=2),
            make_player(player_id=3, seat_position=3),
        ]
        state = make_game_state(players=players)
        card = make_card(power_text="Rescue")
        self.resolver.create_power_prompt(state, 0, card)

        # Activate
        events = self.resolver.handle_power_choice(state, 0, {"choice": "activate"})
        assert isinstance(events, list)
        assert events[0]["prompt_type"] == "choose_card_from_discard"

        # Choose card (place on draw deck)
        events = self.resolver.handle_power_choice(
            state, 0, {"card_id": 30, "play_immediately": False}
        )

        assert isinstance(events, list)
        assert events[0]["type"] == "power_activated"
        assert events[0]["power_name"] == "rescue"
        assert events[0]["action"] == "placed_on_draw_deck"
        # Card is now on top of draw deck
        assert state.players[0].draw_deck[0].card_id == 30
        assert len(state.players[0].discard_pile) == 0

    def test_rescue_plays_immediately_if_matches_sequence(self):
        """Rescue plays card immediately if denomination matches current sequence."""
        discard_card = make_card(card_id=30, denomination=100)
        players = [
            make_player(
                player_id=1,
                discard_pile=[discard_card],
                seat_position=1,
            ),
            make_player(player_id=2, seat_position=2),
            make_player(player_id=3, seat_position=3),
        ]
        state = make_game_state(players=players, current_sequence=100)
        card = make_card(power_text="Rescue")
        self.resolver.create_power_prompt(state, 0, card)

        # Activate
        self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        # Choose card and play immediately
        events = self.resolver.handle_power_choice(
            state, 0, {"card_id": 30, "play_immediately": True}
        )

        assert isinstance(events, list)
        assert events[0]["action"] == "played_immediately"
        # Card is on play pile
        assert state.players[0].play_pile[-1].card_id == 30
        assert len(state.players[0].discard_pile) == 0
        # Sequence advanced
        assert state.current_sequence == 1000

    def test_rescue_card_not_in_discard(self):
        """Rescue rejects card not in discard pile."""
        players = [
            make_player(player_id=1, discard_pile=[], seat_position=1),
            make_player(player_id=2, seat_position=2),
            make_player(player_id=3, seat_position=3),
        ]
        state = make_game_state(players=players)
        card = make_card(power_text="Rescue")
        self.resolver.create_power_prompt(state, 0, card)
        self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        result = self.resolver.handle_power_choice(
            state, 0, {"card_id": 999, "play_immediately": False}
        )

        assert isinstance(result, tuple)
        assert result[0] == "card_not_in_discard"


# --- Tests for error handling ---


class TestPowerResolverErrors:
    """Tests for error handling in PowerResolver."""

    def setup_method(self):
        self.resolver = PowerResolver()

    def test_no_pending_power(self):
        """Handling a choice with no pending power returns error."""
        state = make_game_state()

        result = self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        assert isinstance(result, tuple)
        assert result[0] == "no_pending_power"

    def test_wrong_player_resolving_power(self):
        """Only the player who played the card can resolve the power."""
        state = make_game_state()
        card = make_card(power_text="Go")
        self.resolver.create_power_prompt(state, 0, card)

        result = self.resolver.handle_power_choice(state, 1, {"choice": "activate"})

        assert isinstance(result, tuple)
        assert result[0] == "not_your_power"

    def test_invalid_choice_value(self):
        """Invalid choice value returns error."""
        state = make_game_state()
        card = make_card(power_text="Go")
        self.resolver.create_power_prompt(state, 0, card)

        result = self.resolver.handle_power_choice(state, 0, {"choice": "invalid"})

        assert isinstance(result, tuple)
        assert result[0] == "invalid_choice"
