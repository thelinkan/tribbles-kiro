"""Unit tests for Expansion 3 (More Tribbles More Troubles) powers.

Tests cover:
- Antidote: passive power that reverses Poison scoring when on top of target's draw deck
- Copy: apply game text of top card of another player's play pile (cannot copy Quadruple)
- Cycle: place one hand card under draw deck, draw one from top
- Draw: choose any player, that player draws one card from their draw deck
- Exchange: discard one hand card, take one card from discard pile
- Kill: choose any player, discard top of their play pile
- Recycle: choose any player, shuffle their discard pile into their draw deck
- Replay: search own play pile, play one card again as if from hand
- Score: mark target, if target plays next turn → activator gains that card's denomination

Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8, 11.9
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest

from models import CardInstance, GameState, PendingPower, PlayerState
from game.powers.resolver import (
    ACTIVATABLE_POWERS,
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
    cumulative_score: int = 0,
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
        cumulative_score=cumulative_score,
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


# --- Tests for Antidote (passive power during Poison resolution) ---


class TestAntidotePower:
    """Tests for the Antidote power (Requirement 11.1).

    Antidote is passive: when Poison targets a player whose top draw card
    has Antidote, the targeted player scores instead and can place hand
    beneath draw deck.
    """

    def setup_method(self):
        self.resolver = PowerResolver()

    def test_antidote_reverses_poison_scoring(self):
        """When target's top draw card has Antidote, target scores instead of Poison player."""
        antidote_card = make_card(card_id=50, denomination=1000, power_text="Antidote")
        other_card = make_card(card_id=51, denomination=10)
        hand_card = make_card(card_id=52, denomination=100)
        players = [
            make_player(player_id=1, seat_position=1),
            make_player(
                player_id=2,
                draw_deck=[antidote_card, other_card],
                hand=[hand_card],
                seat_position=2,
            ),
            make_player(player_id=3, seat_position=3),
        ]
        state = make_game_state(players=players)
        card = make_card(power_text="Poison")
        self.resolver.create_power_prompt(state, 0, card)

        # Activate Poison
        self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        # Choose target (player index 1 who has Antidote on top)
        events = self.resolver.handle_power_choice(
            state, 0, {"target_player_index": 1}
        )

        assert isinstance(events, list)
        assert events[0]["type"] == "power_activated"
        assert events[0]["antidote_triggered"] is True
        # Target scored, not the Poison player
        assert state.players[1].cumulative_score == 1000
        assert state.players[0].cumulative_score == 0
        # Antidote card moved to target's discard pile
        assert antidote_card in state.players[1].discard_pile

    def test_antidote_places_hand_beneath_draw_deck(self):
        """When Antidote triggers, target's hand is placed beneath their draw deck."""
        antidote_card = make_card(card_id=50, denomination=1000, power_text="Antidote")
        other_card = make_card(card_id=51, denomination=10)
        hand_card1 = make_card(card_id=52, denomination=100)
        hand_card2 = make_card(card_id=53, denomination=1)
        players = [
            make_player(player_id=1, seat_position=1),
            make_player(
                player_id=2,
                draw_deck=[antidote_card, other_card],
                hand=[hand_card1, hand_card2],
                seat_position=2,
            ),
            make_player(player_id=3, seat_position=3),
        ]
        state = make_game_state(players=players)
        card = make_card(power_text="Poison")
        self.resolver.create_power_prompt(state, 0, card)
        self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        events = self.resolver.handle_power_choice(
            state, 0, {"target_player_index": 1}
        )

        assert isinstance(events, list)
        # Target's hand should be empty (placed beneath draw deck)
        assert len(state.players[1].hand) == 0
        # Draw deck should contain: other_card (remaining after antidote removed) + hand cards
        assert other_card in state.players[1].draw_deck
        assert hand_card1 in state.players[1].draw_deck
        assert hand_card2 in state.players[1].draw_deck

    def test_no_antidote_normal_poison(self):
        """When target's top draw card does NOT have Antidote, normal Poison applies."""
        normal_card = make_card(card_id=50, denomination=1000, power_text="Go")
        players = [
            make_player(player_id=1, seat_position=1),
            make_player(
                player_id=2,
                draw_deck=[normal_card],
                seat_position=2,
            ),
            make_player(player_id=3, seat_position=3),
        ]
        state = make_game_state(players=players)
        card = make_card(power_text="Poison")
        self.resolver.create_power_prompt(state, 0, card)
        self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        events = self.resolver.handle_power_choice(
            state, 0, {"target_player_index": 1}
        )

        assert isinstance(events, list)
        assert "antidote_triggered" not in events[0]
        # Poison player scored
        assert state.players[0].cumulative_score == 1000
        assert state.players[1].cumulative_score == 0


# --- Tests for Copy power ---


class TestCopyPower:
    """Tests for the Copy power (Requirement 11.2)."""

    def setup_method(self):
        self.resolver = PowerResolver()

    def test_copy_returns_copied_power_info(self):
        """Copy power returns info about the copied card's power."""
        target_play_card = make_card(card_id=60, denomination=100, power_text="Go")
        players = [
            make_player(player_id=1, seat_position=1),
            make_player(
                player_id=2,
                play_pile=[target_play_card],
                seat_position=2,
            ),
            make_player(player_id=3, seat_position=3),
        ]
        state = make_game_state(players=players)
        card = make_card(power_text="Copy")
        self.resolver.create_power_prompt(state, 0, card)

        # Activate
        events = self.resolver.handle_power_choice(state, 0, {"choice": "activate"})
        assert isinstance(events, list)
        assert events[0]["prompt_type"] == "choose_target_player"

        # Choose target
        events = self.resolver.handle_power_choice(
            state, 0, {"target_player_index": 1}
        )

        assert isinstance(events, list)
        assert events[0]["type"] == "power_activated"
        assert events[0]["power_name"] == "copy"
        assert events[0]["copied_power"] == "go"
        assert events[0]["copied_card_id"] == 60

    def test_copy_cannot_copy_quadruple(self):
        """Copy power cannot copy the Quadruple power (Requirement 12.10)."""
        quadruple_card = make_card(card_id=60, denomination=10000, power_text="Quadruple")
        players = [
            make_player(player_id=1, seat_position=1),
            make_player(
                player_id=2,
                play_pile=[quadruple_card],
                seat_position=2,
            ),
            make_player(player_id=3, seat_position=3),
        ]
        state = make_game_state(players=players)
        card = make_card(power_text="Copy")
        self.resolver.create_power_prompt(state, 0, card)
        self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        result = self.resolver.handle_power_choice(
            state, 0, {"target_player_index": 1}
        )

        assert isinstance(result, tuple)
        assert result[0] == "cannot_copy_quadruple"

    def test_copy_cannot_target_self(self):
        """Copy power cannot target own play pile."""
        play_card = make_card(card_id=60, denomination=100, power_text="Go")
        players = [
            make_player(player_id=1, play_pile=[play_card], seat_position=1),
            make_player(player_id=2, seat_position=2),
            make_player(player_id=3, seat_position=3),
        ]
        state = make_game_state(players=players)
        card = make_card(power_text="Copy")
        self.resolver.create_power_prompt(state, 0, card)
        self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        result = self.resolver.handle_power_choice(
            state, 0, {"target_player_index": 0}
        )

        assert isinstance(result, tuple)
        assert result[0] == "invalid_target"

    def test_copy_target_empty_play_pile(self):
        """Copy power rejects target with empty play pile."""
        players = [
            make_player(player_id=1, seat_position=1),
            make_player(player_id=2, play_pile=[], seat_position=2),
            make_player(player_id=3, seat_position=3),
        ]
        state = make_game_state(players=players)
        card = make_card(power_text="Copy")
        self.resolver.create_power_prompt(state, 0, card)
        self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        result = self.resolver.handle_power_choice(
            state, 0, {"target_player_index": 1}
        )

        assert isinstance(result, tuple)
        assert result[0] == "invalid_target"


# --- Tests for Cycle power ---


class TestCyclePower:
    """Tests for the Cycle power (Requirement 11.3)."""

    def setup_method(self):
        self.resolver = PowerResolver()

    def test_cycle_preserves_hand_size(self):
        """Cycle power preserves hand size (one out, one in)."""
        hand_card1 = make_card(card_id=70, denomination=10)
        hand_card2 = make_card(card_id=71, denomination=100)
        draw_card = make_card(card_id=72, denomination=1000)
        players = [
            make_player(
                player_id=1,
                hand=[hand_card1, hand_card2],
                draw_deck=[draw_card],
                seat_position=1,
            ),
            make_player(player_id=2, seat_position=2),
            make_player(player_id=3, seat_position=3),
        ]
        state = make_game_state(players=players)
        card = make_card(power_text="Cycle")
        self.resolver.create_power_prompt(state, 0, card)

        # Activate
        events = self.resolver.handle_power_choice(state, 0, {"choice": "activate"})
        assert isinstance(events, list)
        assert events[0]["prompt_type"] == "choose_card_from_hand"

        # Choose card to place under draw deck
        events = self.resolver.handle_power_choice(state, 0, {"card_id": 70})

        assert isinstance(events, list)
        assert events[0]["type"] == "power_activated"
        assert events[0]["power_name"] == "cycle"
        # Hand size should still be 2 (removed one, drew one)
        assert len(state.players[0].hand) == 2
        # The drawn card should be in hand
        assert draw_card in state.players[0].hand
        # The placed card should be at the bottom of draw deck
        assert hand_card1 in state.players[0].draw_deck

    def test_cycle_places_card_under_draw_deck(self):
        """Cycle places the chosen card at the bottom of the draw deck."""
        hand_card = make_card(card_id=70, denomination=10)
        draw_card1 = make_card(card_id=72, denomination=1000)
        draw_card2 = make_card(card_id=73, denomination=100)
        players = [
            make_player(
                player_id=1,
                hand=[hand_card],
                draw_deck=[draw_card1, draw_card2],
                seat_position=1,
            ),
            make_player(player_id=2, seat_position=2),
            make_player(player_id=3, seat_position=3),
        ]
        state = make_game_state(players=players)
        card = make_card(power_text="Cycle")
        self.resolver.create_power_prompt(state, 0, card)
        self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        events = self.resolver.handle_power_choice(state, 0, {"card_id": 70})

        assert isinstance(events, list)
        # hand_card should be at the end of draw deck
        assert state.players[0].draw_deck[-1].card_id == 70
        # draw_card1 was drawn (it was on top)
        assert draw_card1 in state.players[0].hand

    def test_cycle_invalid_card(self):
        """Cycle rejects card not in hand."""
        hand_card = make_card(card_id=70, denomination=10)
        players = [
            make_player(
                player_id=1,
                hand=[hand_card],
                draw_deck=[make_card(card_id=72)],
                seat_position=1,
            ),
            make_player(player_id=2, seat_position=2),
            make_player(player_id=3, seat_position=3),
        ]
        state = make_game_state(players=players)
        card = make_card(power_text="Cycle")
        self.resolver.create_power_prompt(state, 0, card)
        self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        result = self.resolver.handle_power_choice(state, 0, {"card_id": 999})

        assert isinstance(result, tuple)
        assert result[0] == "card_not_in_hand"


# --- Tests for Draw power ---


class TestDrawPower:
    """Tests for the Draw power (Requirement 11.4)."""

    def setup_method(self):
        self.resolver = PowerResolver()

    def test_draw_target_draws_one_card(self):
        """Draw power causes target to draw one card from their draw deck."""
        target_draw_card = make_card(card_id=80, denomination=100)
        players = [
            make_player(player_id=1, seat_position=1),
            make_player(
                player_id=2,
                draw_deck=[target_draw_card],
                hand=[],
                seat_position=2,
            ),
            make_player(player_id=3, seat_position=3),
        ]
        state = make_game_state(players=players)
        card = make_card(power_text="Draw")
        self.resolver.create_power_prompt(state, 0, card)

        # Activate
        events = self.resolver.handle_power_choice(state, 0, {"choice": "activate"})
        assert isinstance(events, list)
        assert events[0]["prompt_type"] == "choose_target_player"

        # Choose target
        events = self.resolver.handle_power_choice(
            state, 0, {"target_player_index": 1}
        )

        assert isinstance(events, list)
        assert events[0]["type"] == "power_activated"
        assert events[0]["power_name"] == "draw"
        # Target's hand grew by 1
        assert len(state.players[1].hand) == 1
        assert target_draw_card in state.players[1].hand
        # Target's draw deck shrunk by 1
        assert len(state.players[1].draw_deck) == 0

    def test_draw_can_target_self(self):
        """Draw power can target the activating player."""
        draw_card = make_card(card_id=80, denomination=100)
        players = [
            make_player(
                player_id=1,
                draw_deck=[draw_card],
                hand=[],
                seat_position=1,
            ),
            make_player(player_id=2, seat_position=2),
            make_player(player_id=3, seat_position=3),
        ]
        state = make_game_state(players=players)
        card = make_card(power_text="Draw")
        self.resolver.create_power_prompt(state, 0, card)
        self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        events = self.resolver.handle_power_choice(
            state, 0, {"target_player_index": 0}
        )

        assert isinstance(events, list)
        assert events[0]["power_name"] == "draw"
        assert len(state.players[0].hand) == 1
        assert draw_card in state.players[0].hand

    def test_draw_target_empty_draw_deck(self):
        """Draw power rejects target with empty draw deck."""
        players = [
            make_player(player_id=1, seat_position=1),
            make_player(player_id=2, draw_deck=[], seat_position=2),
            make_player(player_id=3, seat_position=3),
        ]
        state = make_game_state(players=players)
        card = make_card(power_text="Draw")
        self.resolver.create_power_prompt(state, 0, card)
        self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        result = self.resolver.handle_power_choice(
            state, 0, {"target_player_index": 1}
        )

        assert isinstance(result, tuple)
        assert result[0] == "invalid_target"


# --- Tests for Exchange power ---


class TestExchangePower:
    """Tests for the Exchange power (Requirement 11.5)."""

    def setup_method(self):
        self.resolver = PowerResolver()

    def test_exchange_swaps_hand_card_with_discard_card(self):
        """Exchange discards one hand card and takes one from discard pile."""
        hand_card = make_card(card_id=90, denomination=10, card_name="Hand Card")
        discard_card = make_card(card_id=91, denomination=1000, card_name="Discard Card")
        players = [
            make_player(
                player_id=1,
                hand=[hand_card],
                discard_pile=[discard_card],
                seat_position=1,
            ),
            make_player(player_id=2, seat_position=2),
            make_player(player_id=3, seat_position=3),
        ]
        state = make_game_state(players=players)
        card = make_card(power_text="Exchange")
        self.resolver.create_power_prompt(state, 0, card)

        # Activate
        events = self.resolver.handle_power_choice(state, 0, {"choice": "activate"})
        assert isinstance(events, list)
        assert events[0]["prompt_type"] == "choose_card_from_hand"

        # Choose card to discard and card to take
        events = self.resolver.handle_power_choice(
            state, 0, {"card_id": 90, "take_card_id": 91}
        )

        assert isinstance(events, list)
        assert events[0]["type"] == "power_activated"
        assert events[0]["power_name"] == "exchange"
        # Hand size unchanged
        assert len(state.players[0].hand) == 1
        # Discard card is now in hand
        assert discard_card in state.players[0].hand
        # Hand card is now in discard pile
        assert hand_card in state.players[0].discard_pile

    def test_exchange_preserves_hand_size(self):
        """Exchange preserves hand size (one out, one in)."""
        hand_card1 = make_card(card_id=90, denomination=10)
        hand_card2 = make_card(card_id=92, denomination=100)
        discard_card = make_card(card_id=91, denomination=1000)
        players = [
            make_player(
                player_id=1,
                hand=[hand_card1, hand_card2],
                discard_pile=[discard_card],
                seat_position=1,
            ),
            make_player(player_id=2, seat_position=2),
            make_player(player_id=3, seat_position=3),
        ]
        state = make_game_state(players=players)
        card = make_card(power_text="Exchange")
        self.resolver.create_power_prompt(state, 0, card)
        self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        events = self.resolver.handle_power_choice(
            state, 0, {"card_id": 90, "take_card_id": 91}
        )

        assert isinstance(events, list)
        assert len(state.players[0].hand) == 2

    def test_exchange_card_not_in_hand(self):
        """Exchange rejects card not in hand."""
        discard_card = make_card(card_id=91, denomination=1000)
        players = [
            make_player(
                player_id=1,
                hand=[],
                discard_pile=[discard_card],
                seat_position=1,
            ),
            make_player(player_id=2, seat_position=2),
            make_player(player_id=3, seat_position=3),
        ]
        state = make_game_state(players=players)
        card = make_card(power_text="Exchange")
        self.resolver.create_power_prompt(state, 0, card)
        self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        result = self.resolver.handle_power_choice(
            state, 0, {"card_id": 999, "take_card_id": 91}
        )

        assert isinstance(result, tuple)
        assert result[0] == "card_not_in_hand"

    def test_exchange_card_not_in_discard(self):
        """Exchange rejects take_card_id not in discard pile."""
        hand_card = make_card(card_id=90, denomination=10)
        players = [
            make_player(
                player_id=1,
                hand=[hand_card],
                discard_pile=[],
                seat_position=1,
            ),
            make_player(player_id=2, seat_position=2),
            make_player(player_id=3, seat_position=3),
        ]
        state = make_game_state(players=players)
        card = make_card(power_text="Exchange")
        self.resolver.create_power_prompt(state, 0, card)
        self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        result = self.resolver.handle_power_choice(
            state, 0, {"card_id": 90, "take_card_id": 999}
        )

        assert isinstance(result, tuple)
        assert result[0] == "card_not_in_discard"



# --- Tests for Kill power ---


class TestKillPower:
    """Tests for the Kill power (Requirement 11.6)."""

    def setup_method(self):
        self.resolver = PowerResolver()

    def test_kill_discards_top_of_target_play_pile(self):
        """Kill power discards the top card of target's play pile."""
        play_card1 = make_card(card_id=100, denomination=10)
        play_card2 = make_card(card_id=101, denomination=1000)
        players = [
            make_player(player_id=1, seat_position=1),
            make_player(
                player_id=2,
                play_pile=[play_card1, play_card2],
                seat_position=2,
            ),
            make_player(player_id=3, seat_position=3),
        ]
        state = make_game_state(players=players)
        card = make_card(power_text="Kill")
        self.resolver.create_power_prompt(state, 0, card)

        # Activate
        events = self.resolver.handle_power_choice(state, 0, {"choice": "activate"})
        assert isinstance(events, list)
        assert events[0]["prompt_type"] == "choose_target_player"

        # Choose target
        events = self.resolver.handle_power_choice(
            state, 0, {"target_player_index": 1}
        )

        assert isinstance(events, list)
        assert events[0]["type"] == "power_activated"
        assert events[0]["power_name"] == "kill"
        assert events[0]["killed_card_id"] == 101  # Top card (last in list)
        # Play pile lost top card
        assert len(state.players[1].play_pile) == 1
        assert state.players[1].play_pile[0].card_id == 100
        # Top card moved to discard pile
        assert play_card2 in state.players[1].discard_pile

    def test_kill_can_target_self(self):
        """Kill power can target the activating player's own play pile."""
        play_card = make_card(card_id=100, denomination=10)
        players = [
            make_player(player_id=1, play_pile=[play_card], seat_position=1),
            make_player(player_id=2, seat_position=2),
            make_player(player_id=3, seat_position=3),
        ]
        state = make_game_state(players=players)
        card = make_card(power_text="Kill")
        self.resolver.create_power_prompt(state, 0, card)
        self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        events = self.resolver.handle_power_choice(
            state, 0, {"target_player_index": 0}
        )

        assert isinstance(events, list)
        assert events[0]["power_name"] == "kill"
        assert len(state.players[0].play_pile) == 0
        assert play_card in state.players[0].discard_pile

    def test_kill_target_empty_play_pile(self):
        """Kill power rejects target with empty play pile."""
        players = [
            make_player(player_id=1, seat_position=1),
            make_player(player_id=2, play_pile=[], seat_position=2),
            make_player(player_id=3, seat_position=3),
        ]
        state = make_game_state(players=players)
        card = make_card(power_text="Kill")
        self.resolver.create_power_prompt(state, 0, card)
        self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        result = self.resolver.handle_power_choice(
            state, 0, {"target_player_index": 1}
        )

        assert isinstance(result, tuple)
        assert result[0] == "invalid_target"


# --- Tests for Recycle power ---


class TestRecyclePower:
    """Tests for the Recycle power (Requirement 11.7)."""

    def setup_method(self):
        self.resolver = PowerResolver()

    def test_recycle_shuffles_discard_into_draw_deck(self):
        """Recycle shuffles target's discard pile into their draw deck."""
        discard_card1 = make_card(card_id=110, denomination=10)
        discard_card2 = make_card(card_id=111, denomination=100)
        draw_card = make_card(card_id=112, denomination=1000)
        players = [
            make_player(player_id=1, seat_position=1),
            make_player(
                player_id=2,
                discard_pile=[discard_card1, discard_card2],
                draw_deck=[draw_card],
                seat_position=2,
            ),
            make_player(player_id=3, seat_position=3),
        ]
        state = make_game_state(players=players)
        card = make_card(power_text="Recycle")
        self.resolver.create_power_prompt(state, 0, card)

        # Activate
        events = self.resolver.handle_power_choice(state, 0, {"choice": "activate"})
        assert isinstance(events, list)
        assert events[0]["prompt_type"] == "choose_target_player"

        # Choose target
        events = self.resolver.handle_power_choice(
            state, 0, {"target_player_index": 1}
        )

        assert isinstance(events, list)
        assert events[0]["type"] == "power_activated"
        assert events[0]["power_name"] == "recycle"
        # Discard pile should be empty
        assert len(state.players[1].discard_pile) == 0
        # Draw deck should contain all former discard cards + original draw card
        assert len(state.players[1].draw_deck) == 3
        draw_deck_ids = {c.card_id for c in state.players[1].draw_deck}
        assert draw_deck_ids == {110, 111, 112}

    def test_recycle_target_empty_discard(self):
        """Recycle rejects target with empty discard pile."""
        players = [
            make_player(player_id=1, seat_position=1),
            make_player(player_id=2, discard_pile=[], seat_position=2),
            make_player(player_id=3, seat_position=3),
        ]
        state = make_game_state(players=players)
        card = make_card(power_text="Recycle")
        self.resolver.create_power_prompt(state, 0, card)
        self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        result = self.resolver.handle_power_choice(
            state, 0, {"target_player_index": 1}
        )

        assert isinstance(result, tuple)
        assert result[0] == "invalid_target"

    def test_recycle_can_target_self(self):
        """Recycle can target the activating player."""
        discard_card = make_card(card_id=110, denomination=10)
        players = [
            make_player(
                player_id=1,
                discard_pile=[discard_card],
                draw_deck=[],
                seat_position=1,
            ),
            make_player(player_id=2, seat_position=2),
            make_player(player_id=3, seat_position=3),
        ]
        state = make_game_state(players=players)
        card = make_card(power_text="Recycle")
        self.resolver.create_power_prompt(state, 0, card)
        self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        events = self.resolver.handle_power_choice(
            state, 0, {"target_player_index": 0}
        )

        assert isinstance(events, list)
        assert len(state.players[0].discard_pile) == 0
        assert discard_card in state.players[0].draw_deck


# --- Tests for Replay power ---


class TestReplayPower:
    """Tests for the Replay power (Requirement 11.8)."""

    def setup_method(self):
        self.resolver = PowerResolver()

    def test_replay_moves_card_to_top_of_play_pile(self):
        """Replay removes card from play pile and places it back on top."""
        play_card1 = make_card(card_id=120, denomination=10)
        play_card2 = make_card(card_id=121, denomination=100)
        play_card3 = make_card(card_id=122, denomination=1000)
        players = [
            make_player(
                player_id=1,
                play_pile=[play_card1, play_card2, play_card3],
                seat_position=1,
            ),
            make_player(player_id=2, seat_position=2),
            make_player(player_id=3, seat_position=3),
        ]
        state = make_game_state(players=players)
        card = make_card(power_text="Replay")
        self.resolver.create_power_prompt(state, 0, card)

        # Activate
        events = self.resolver.handle_power_choice(state, 0, {"choice": "activate"})
        assert isinstance(events, list)
        assert events[0]["prompt_type"] == "choose_card_from_play_pile"

        # Choose card from play pile to replay
        events = self.resolver.handle_power_choice(state, 0, {"card_id": 120})

        assert isinstance(events, list)
        assert events[0]["type"] == "power_activated"
        assert events[0]["power_name"] == "replay"
        assert events[0]["replayed_card_id"] == 120
        # Card should be on top of play pile (last element)
        assert state.players[0].play_pile[-1].card_id == 120
        # Play pile size unchanged (removed and re-added)
        assert len(state.players[0].play_pile) == 3

    def test_replay_card_not_in_play_pile(self):
        """Replay rejects card not in play pile."""
        play_card = make_card(card_id=120, denomination=10)
        players = [
            make_player(
                player_id=1,
                play_pile=[play_card],
                seat_position=1,
            ),
            make_player(player_id=2, seat_position=2),
            make_player(player_id=3, seat_position=3),
        ]
        state = make_game_state(players=players)
        card = make_card(power_text="Replay")
        self.resolver.create_power_prompt(state, 0, card)
        self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        result = self.resolver.handle_power_choice(state, 0, {"card_id": 999})

        assert isinstance(result, tuple)
        assert result[0] == "card_not_in_play_pile"


# --- Tests for Score power ---


class TestScorePower:
    """Tests for the Score power (Requirement 11.9)."""

    def setup_method(self):
        self.resolver = PowerResolver()

    def test_score_marks_target_player(self):
        """Score power marks the target player with the activator's player_id."""
        players = [
            make_player(player_id=1, seat_position=1),
            make_player(player_id=2, seat_position=2),
            make_player(player_id=3, seat_position=3),
        ]
        state = make_game_state(players=players)
        card = make_card(power_text="Score")
        self.resolver.create_power_prompt(state, 0, card)

        # Activate
        events = self.resolver.handle_power_choice(state, 0, {"choice": "activate"})
        assert isinstance(events, list)
        assert events[0]["prompt_type"] == "choose_target_player"

        # Choose target
        events = self.resolver.handle_power_choice(
            state, 0, {"target_player_index": 1}
        )

        assert isinstance(events, list)
        assert events[0]["type"] == "power_activated"
        assert events[0]["power_name"] == "score"
        assert events[0]["target_player_id"] == 2
        # Target should be marked with activator's player_id
        assert state.players[1].score_target_by == 1

    def test_score_cannot_target_self(self):
        """Score power cannot target the activating player."""
        players = [
            make_player(player_id=1, seat_position=1),
            make_player(player_id=2, seat_position=2),
            make_player(player_id=3, seat_position=3),
        ]
        state = make_game_state(players=players)
        card = make_card(power_text="Score")
        self.resolver.create_power_prompt(state, 0, card)
        self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        result = self.resolver.handle_power_choice(
            state, 0, {"target_player_index": 0}
        )

        assert isinstance(result, tuple)
        assert result[0] == "invalid_target"

    def test_score_target_initially_none(self):
        """Before Score is used, score_target_by is None."""
        players = [
            make_player(player_id=1, seat_position=1),
            make_player(player_id=2, seat_position=2),
            make_player(player_id=3, seat_position=3),
        ]
        state = make_game_state(players=players)
        assert state.players[1].score_target_by is None


# --- Tests for new powers in ACTIVATABLE_POWERS ---


class TestExpansion3PowerRegistration:
    """Tests that expansion 3 powers are properly registered."""

    def test_expansion3_powers_in_activatable(self):
        """All expansion 3 powers are in ACTIVATABLE_POWERS."""
        expansion3_powers = {"copy", "cycle", "draw", "exchange", "kill", "recycle", "replay", "score"}
        assert expansion3_powers.issubset(ACTIVATABLE_POWERS)

    def test_antidote_not_activatable(self):
        """Antidote is a passive power and should not be in ACTIVATABLE_POWERS."""
        assert "antidote" not in ACTIVATABLE_POWERS

    def test_get_activatable_power_expansion3(self):
        """get_activatable_power detects expansion 3 powers."""
        resolver = PowerResolver()
        for power in ["copy", "cycle", "draw", "exchange", "kill", "recycle", "replay", "score"]:
            card = make_card(power_text=power.capitalize())
            assert resolver.get_activatable_power(card) == power
