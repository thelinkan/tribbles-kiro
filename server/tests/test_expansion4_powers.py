"""Unit tests for Expansion 4 (No Tribble at All) powers.

Tests cover:
- Compound power activation rules (both activate unless one is Clone)
- Battle: reveal top 3 of both players' draw decks, higher total wins
- Evolve: count hand, move to discard, draw same count
- Freeze: record named power as frozen, reject frozen power plays
- Mutate: count play pile, shuffle into deck, move same count back
- Process: draw 3, place 2 under draw deck
- Quadruple: card worth 40000 instead of 10000
- Safety: hand shuffled into draw deck instead of discard
- Tally: scoring split half to scorer, half to owner
- Toxin: reveal cards per Discard count in opponents' piles

Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7, 12.8, 12.9, 12.10, 12.11, 12.12, 12.13
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
from game.round_manager import RoundManager


# --- Test Helpers ---


def make_card(
    card_id: int = 1,
    card_name: str = "Test Card",
    denomination: int = 100,
    power_text: str = "Go",
    expansion_id: int = 4,
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
    has_gone_out: bool = False,
    is_decked: bool = False,
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
        is_decked=is_decked,
        has_gone_out=has_gone_out,
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


# --- Tests for Compound Power Rules ---


class TestCompoundPowerRules:
    """Tests for compound power activation rules (Requirements 12.1, 12.2, 12.3)."""

    def setup_method(self):
        self.resolver = PowerResolver()

    def test_compound_neither_clone_returns_both_powers(self):
        """Compound power with neither Clone returns both powers joined by &."""
        card = make_card(power_text="Go & Reverse")
        power = self.resolver.get_activatable_power(card)
        assert power == "go&reverse"

    def test_compound_with_clone_returns_non_clone_only(self):
        """Compound power with Clone returns only the non-Clone power."""
        card = make_card(power_text="Clone & Reverse")
        power = self.resolver.get_activatable_power(card)
        assert power == "reverse"

    def test_compound_clone_and_skip(self):
        """Compound Clone & Skip returns skip."""
        card = make_card(power_text="Clone & Skip")
        power = self.resolver.get_activatable_power(card)
        assert power == "skip"

    def test_compound_both_immediate_powers_activate_together(self):
        """When both compound powers are immediate, both execute on activation."""
        players = [
            make_player(player_id=1, seat_position=1),
            make_player(player_id=2, seat_position=2),
            make_player(player_id=3, seat_position=3),
        ]
        state = make_game_state(players=players, current_player_index=0)
        card = make_card(power_text="Go & Reverse")
        self.resolver.create_power_prompt(state, 0, card)

        events = self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        assert isinstance(events, list)
        # Both powers should have activated
        power_names = [e.get("power_name") for e in events if e.get("type") == "power_activated"]
        assert "go" in power_names
        assert "reverse" in power_names

    def test_compound_non_clone_no_activatable(self):
        """Compound power with no activatable components returns None."""
        card = make_card(power_text="Bonus & Safety")
        power = self.resolver.get_activatable_power(card)
        assert power is None


# --- Tests for Battle Power ---


class TestBattlePower:
    """Tests for the Battle power (Requirement 12.4)."""

    def setup_method(self):
        self.resolver = PowerResolver()

    def test_battle_higher_total_wins_all_six(self):
        """Player with higher total denomination wins all 6 cards under play pile."""
        # Player 1 has high cards, Player 2 has low cards
        p1_draw = [
            make_card(card_id=10, denomination=10000),
            make_card(card_id=11, denomination=10000),
            make_card(card_id=12, denomination=10000),
            make_card(card_id=13, denomination=1),
        ]
        p2_draw = [
            make_card(card_id=20, denomination=1),
            make_card(card_id=21, denomination=1),
            make_card(card_id=22, denomination=1),
            make_card(card_id=23, denomination=100),
        ]
        players = [
            make_player(player_id=1, draw_deck=p1_draw, seat_position=1),
            make_player(player_id=2, draw_deck=p2_draw, seat_position=2),
            make_player(player_id=3, seat_position=3),
        ]
        state = make_game_state(players=players)
        card = make_card(power_text="Battle")
        self.resolver.create_power_prompt(state, 0, card)

        # Activate
        self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        # Choose target
        events = self.resolver.handle_power_choice(
            state, 0, {"target_player_index": 1}
        )

        assert isinstance(events, list)
        assert events[0]["type"] == "power_activated"
        assert events[0]["power_name"] == "battle"
        assert events[0]["winner_player_id"] == 1
        # Winner (player 1) has all 6 cards under play pile
        assert len(state.players[0].play_pile) == 6
        # Loser (player 2) discards their 3
        assert len(state.players[1].discard_pile) == 3

    def test_battle_loser_discards_their_revealed(self):
        """Loser discards their 3 revealed cards."""
        p1_draw = [
            make_card(card_id=10, denomination=1),
            make_card(card_id=11, denomination=1),
            make_card(card_id=12, denomination=1),
        ]
        p2_draw = [
            make_card(card_id=20, denomination=10000),
            make_card(card_id=21, denomination=10000),
            make_card(card_id=22, denomination=10000),
        ]
        players = [
            make_player(player_id=1, draw_deck=p1_draw, seat_position=1),
            make_player(player_id=2, draw_deck=p2_draw, seat_position=2),
            make_player(player_id=3, seat_position=3),
        ]
        state = make_game_state(players=players)
        card = make_card(power_text="Battle")
        self.resolver.create_power_prompt(state, 0, card)
        self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        events = self.resolver.handle_power_choice(
            state, 0, {"target_player_index": 1}
        )

        assert isinstance(events, list)
        assert events[0]["winner_player_id"] == 2
        # Loser (player 1) discards their 3
        assert len(state.players[0].discard_pile) == 3
        # Winner (player 2) has all 6 under play pile
        assert len(state.players[1].play_pile) == 6

    def test_battle_tie_goes_to_active_player(self):
        """On tie, active player wins."""
        p1_draw = [
            make_card(card_id=10, denomination=100),
            make_card(card_id=11, denomination=100),
            make_card(card_id=12, denomination=100),
        ]
        p2_draw = [
            make_card(card_id=20, denomination=100),
            make_card(card_id=21, denomination=100),
            make_card(card_id=22, denomination=100),
        ]
        players = [
            make_player(player_id=1, draw_deck=p1_draw, seat_position=1),
            make_player(player_id=2, draw_deck=p2_draw, seat_position=2),
            make_player(player_id=3, seat_position=3),
        ]
        state = make_game_state(players=players)
        card = make_card(power_text="Battle")
        self.resolver.create_power_prompt(state, 0, card)
        self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        events = self.resolver.handle_power_choice(
            state, 0, {"target_player_index": 1}
        )

        assert isinstance(events, list)
        assert events[0]["winner_player_id"] == 1

    def test_battle_insufficient_cards_rejected(self):
        """Battle rejected if active player has fewer than 3 cards in draw deck."""
        p1_draw = [make_card(card_id=10, denomination=100)]
        p2_draw = [
            make_card(card_id=20, denomination=100),
            make_card(card_id=21, denomination=100),
            make_card(card_id=22, denomination=100),
        ]
        players = [
            make_player(player_id=1, draw_deck=p1_draw, seat_position=1),
            make_player(player_id=2, draw_deck=p2_draw, seat_position=2),
            make_player(player_id=3, seat_position=3),
        ]
        state = make_game_state(players=players)
        card = make_card(power_text="Battle")
        self.resolver.create_power_prompt(state, 0, card)
        self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        result = self.resolver.handle_power_choice(
            state, 0, {"target_player_index": 1}
        )

        assert isinstance(result, tuple)
        assert result[0] == "insufficient_cards"


# --- Tests for Evolve Power ---


class TestEvolvePower:
    """Tests for the Evolve power (Requirement 12.5)."""

    def setup_method(self):
        self.resolver = PowerResolver()

    def test_evolve_preserves_hand_count(self):
        """Evolve preserves hand size (old hand to discard, same count drawn)."""
        hand_cards = [
            make_card(card_id=30, denomination=10),
            make_card(card_id=31, denomination=100),
            make_card(card_id=32, denomination=1000),
        ]
        draw_cards = [
            make_card(card_id=40, denomination=10000),
            make_card(card_id=41, denomination=100000),
            make_card(card_id=42, denomination=1),
            make_card(card_id=43, denomination=10),
        ]
        players = [
            make_player(
                player_id=1,
                hand=list(hand_cards),
                draw_deck=list(draw_cards),
                seat_position=1,
            ),
            make_player(player_id=2, seat_position=2),
            make_player(player_id=3, seat_position=3),
        ]
        state = make_game_state(players=players)
        card = make_card(power_text="Evolve")
        self.resolver.create_power_prompt(state, 0, card)

        events = self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        assert isinstance(events, list)
        assert events[0]["type"] == "power_activated"
        assert events[0]["power_name"] == "evolve"
        # Hand size preserved
        assert len(state.players[0].hand) == 3
        # Old hand cards in discard
        for c in hand_cards:
            assert c in state.players[0].discard_pile
        # New hand cards are from draw deck
        assert state.players[0].hand[0].card_id == 40
        assert state.players[0].hand[1].card_id == 41
        assert state.players[0].hand[2].card_id == 42

    def test_evolve_with_insufficient_draw_deck(self):
        """Evolve draws as many as available if draw deck has fewer cards than hand."""
        hand_cards = [
            make_card(card_id=30, denomination=10),
            make_card(card_id=31, denomination=100),
            make_card(card_id=32, denomination=1000),
        ]
        draw_cards = [make_card(card_id=40, denomination=10000)]
        players = [
            make_player(
                player_id=1,
                hand=list(hand_cards),
                draw_deck=list(draw_cards),
                seat_position=1,
            ),
            make_player(player_id=2, seat_position=2),
            make_player(player_id=3, seat_position=3),
        ]
        state = make_game_state(players=players)
        card = make_card(power_text="Evolve")
        self.resolver.create_power_prompt(state, 0, card)

        events = self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        assert isinstance(events, list)
        # Only 1 card drawn (draw deck had only 1)
        assert len(state.players[0].hand) == 1
        # All 3 old hand cards in discard
        assert len(state.players[0].discard_pile) == 3


# --- Tests for Freeze Power ---


class TestFreezePower:
    """Tests for the Freeze power (Requirement 12.6)."""

    def setup_method(self):
        self.resolver = PowerResolver()

    def test_freeze_records_frozen_power(self):
        """Freeze records the named power as frozen."""
        players = [
            make_player(player_id=1, seat_position=1),
            make_player(player_id=2, seat_position=2),
            make_player(player_id=3, seat_position=3),
        ]
        state = make_game_state(players=players)
        card = make_card(power_text="Freeze")
        self.resolver.create_power_prompt(state, 0, card)

        # Activate
        self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        # Choose power to freeze
        events = self.resolver.handle_power_choice(
            state, 0, {"power_name": "go"}
        )

        assert isinstance(events, list)
        assert events[0]["type"] == "power_activated"
        assert events[0]["power_name"] == "freeze"
        assert events[0]["frozen_power"] == "go"
        assert "go" in state.frozen_powers

    def test_freeze_is_power_frozen_check(self):
        """is_power_frozen returns True for frozen powers."""
        state = make_game_state()
        state.frozen_powers["go"] = 0

        assert self.resolver.is_power_frozen(state, "go") is True
        assert self.resolver.is_power_frozen(state, "skip") is False

    def test_freeze_cannot_freeze_freeze(self):
        """Cannot freeze the Freeze power itself."""
        players = [
            make_player(player_id=1, seat_position=1),
            make_player(player_id=2, seat_position=2),
            make_player(player_id=3, seat_position=3),
        ]
        state = make_game_state(players=players)
        card = make_card(power_text="Freeze")
        self.resolver.create_power_prompt(state, 0, card)
        self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        result = self.resolver.handle_power_choice(
            state, 0, {"power_name": "freeze"}
        )

        assert isinstance(result, tuple)
        assert result[0] == "invalid_power_name"

    def test_freeze_expires_at_end_of_freezers_next_turn(self):
        """Frozen power expires at end of freezing player's next turn."""
        state = make_game_state()
        state.frozen_powers["go"] = 0  # Frozen by player at index 0

        # Clear expired freezes when player 0's turn ends
        events = self.resolver.clear_expired_freezes(state, 0)

        assert len(events) == 1
        assert events[0]["type"] == "freeze_expired"
        assert "go" not in state.frozen_powers

    def test_freeze_does_not_expire_for_other_players_turn(self):
        """Frozen power does not expire when another player's turn ends."""
        state = make_game_state()
        state.frozen_powers["go"] = 0  # Frozen by player at index 0

        # Player 1's turn ends — should not clear
        events = self.resolver.clear_expired_freezes(state, 1)

        assert len(events) == 0
        assert "go" in state.frozen_powers


# --- Tests for Mutate Power ---


class TestMutatePower:
    """Tests for the Mutate power (Requirement 12.7)."""

    def setup_method(self):
        self.resolver = PowerResolver()

    def test_mutate_preserves_play_pile_count(self):
        """Mutate preserves play pile size (old pile to deck, same count back)."""
        play_cards = [
            make_card(card_id=50, denomination=10),
            make_card(card_id=51, denomination=100),
            make_card(card_id=52, denomination=1000),
        ]
        draw_cards = [
            make_card(card_id=60, denomination=10000),
            make_card(card_id=61, denomination=100000),
        ]
        players = [
            make_player(
                player_id=1,
                play_pile=list(play_cards),
                draw_deck=list(draw_cards),
                seat_position=1,
            ),
            make_player(player_id=2, seat_position=2),
            make_player(player_id=3, seat_position=3),
        ]
        state = make_game_state(players=players)
        card = make_card(power_text="Mutate")
        self.resolver.create_power_prompt(state, 0, card)

        events = self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        assert isinstance(events, list)
        assert events[0]["type"] == "power_activated"
        assert events[0]["power_name"] == "mutate"
        # Play pile count preserved (3 cards moved back)
        assert len(state.players[0].play_pile) == 3
        # Original play pile cards are now in the draw deck (shuffled)
        # The new play pile cards came from the combined deck

    def test_mutate_shuffles_pile_into_deck(self):
        """Mutate shuffles play pile into draw deck before drawing back."""
        play_cards = [make_card(card_id=50, denomination=10)]
        # Empty draw deck — after shuffle, deck will have the play pile card
        players = [
            make_player(
                player_id=1,
                play_pile=list(play_cards),
                draw_deck=[],
                seat_position=1,
            ),
            make_player(player_id=2, seat_position=2),
            make_player(player_id=3, seat_position=3),
        ]
        state = make_game_state(players=players)
        card = make_card(power_text="Mutate")
        self.resolver.create_power_prompt(state, 0, card)

        events = self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        assert isinstance(events, list)
        # 1 card was in pile, shuffled into deck, then 1 drawn back to pile
        assert len(state.players[0].play_pile) == 1
        assert len(state.players[0].draw_deck) == 0


# --- Tests for Process Power ---


class TestProcessPower:
    """Tests for the Process power (Requirement 12.8)."""

    def setup_method(self):
        self.resolver = PowerResolver()

    def test_process_net_hand_gain_of_one(self):
        """Process results in net +1 hand card (draw 3, place 2 under deck)."""
        hand_cards = [make_card(card_id=70, denomination=10)]
        draw_cards = [
            make_card(card_id=80, denomination=100),
            make_card(card_id=81, denomination=1000),
            make_card(card_id=82, denomination=10000),
            make_card(card_id=83, denomination=100000),
        ]
        players = [
            make_player(
                player_id=1,
                hand=list(hand_cards),
                draw_deck=list(draw_cards),
                seat_position=1,
            ),
            make_player(player_id=2, seat_position=2),
            make_player(player_id=3, seat_position=3),
        ]
        state = make_game_state(players=players)
        card = make_card(power_text="Process")
        self.resolver.create_power_prompt(state, 0, card)

        # Activate — this draws 3 cards and prompts for 2 to place under deck
        events = self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        assert isinstance(events, list)
        assert events[0]["prompt_type"] == "choose_cards_from_hand"
        # Hand should now have 4 cards (1 original + 3 drawn)
        assert len(state.players[0].hand) == 4

        # Choose 2 cards to place under draw deck
        events = self.resolver.handle_power_choice(
            state, 0, {"card_ids": [70, 80]}
        )

        assert isinstance(events, list)
        assert events[0]["type"] == "power_activated"
        assert events[0]["power_name"] == "process"
        # Hand should now have 2 cards (4 - 2 placed under deck)
        assert len(state.players[0].hand) == 2
        # Draw deck should have the 2 placed cards at the end
        assert state.players[0].draw_deck[-2].card_id == 70
        assert state.players[0].draw_deck[-1].card_id == 80

    def test_process_rejects_wrong_count(self):
        """Process rejects if not exactly 2 cards chosen."""
        hand_cards = [make_card(card_id=70, denomination=10)]
        draw_cards = [
            make_card(card_id=80, denomination=100),
            make_card(card_id=81, denomination=1000),
            make_card(card_id=82, denomination=10000),
        ]
        players = [
            make_player(
                player_id=1,
                hand=list(hand_cards),
                draw_deck=list(draw_cards),
                seat_position=1,
            ),
            make_player(player_id=2, seat_position=2),
            make_player(player_id=3, seat_position=3),
        ]
        state = make_game_state(players=players)
        card = make_card(power_text="Process")
        self.resolver.create_power_prompt(state, 0, card)
        self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        result = self.resolver.handle_power_choice(
            state, 0, {"card_ids": [70]}
        )

        assert isinstance(result, tuple)
        assert result[0] == "invalid_choice"


# --- Tests for Quadruple Scoring ---


class TestQuadrupleScoring:
    """Tests for the Quadruple scoring modifier (Requirement 12.9)."""

    def test_quadruple_card_worth_40000(self):
        """Quadruple card counts as 40000 instead of 10000 for round winner."""
        quadruple_card = make_card(card_id=90, denomination=10000, power_text="Quadruple")
        normal_card = make_card(card_id=91, denomination=1000, power_text="Go")
        players = [
            make_player(
                player_id=1,
                play_pile=[quadruple_card, normal_card],
                has_gone_out=True,
                seat_position=1,
            ),
            make_player(player_id=2, seat_position=2),
        ]
        state = make_game_state(players=players)

        score_service = ScoreService()
        scores = score_service.calculate_round_scores(state)

        # Quadruple = 40000, normal = 1000
        assert scores[1] == 41000

    def test_normal_10000_card_scores_normally(self):
        """A normal 10000 card without Quadruple power scores 10000."""
        normal_card = make_card(card_id=90, denomination=10000, power_text="Go")
        players = [
            make_player(
                player_id=1,
                play_pile=[normal_card],
                has_gone_out=True,
                seat_position=1,
            ),
            make_player(player_id=2, seat_position=2),
        ]
        state = make_game_state(players=players)

        score_service = ScoreService()
        scores = score_service.calculate_round_scores(state)

        assert scores[1] == 10000

    def test_quadruple_only_for_players_who_went_out(self):
        """Quadruple only applies to players who went out."""
        quadruple_card = make_card(card_id=90, denomination=10000, power_text="Quadruple")
        players = [
            make_player(
                player_id=1,
                play_pile=[quadruple_card],
                has_gone_out=False,
                seat_position=1,
            ),
            make_player(player_id=2, seat_position=2, has_gone_out=True, play_pile=[]),
        ]
        state = make_game_state(players=players)

        score_service = ScoreService()
        scores = score_service.calculate_round_scores(state)

        assert scores[1] == 0


# --- Tests for Safety Power ---


class TestSafetyPower:
    """Tests for the Safety end-of-round modifier (Requirement 12.11)."""

    def test_safety_shuffles_hand_into_draw_deck(self):
        """Player with Safety has hand shuffled into draw deck instead of discard."""
        safety_card = make_card(card_id=100, denomination=1000, power_text="Safety")
        hand_card1 = make_card(card_id=101, denomination=10)
        hand_card2 = make_card(card_id=102, denomination=100)
        players = [
            make_player(
                player_id=1,
                hand=[hand_card1, hand_card2],
                play_pile=[safety_card],
                draw_deck=[],
                has_gone_out=False,
                seat_position=1,
            ),
            make_player(player_id=2, seat_position=2, has_gone_out=True),
        ]
        state = make_game_state(players=players)

        round_manager = RoundManager()
        events = []
        round_manager._move_non_goers_hands_to_discard(state, events)

        # Hand should be empty
        assert len(state.players[0].hand) == 0
        # Cards should be in draw deck, not discard
        assert len(state.players[0].discard_pile) == 0
        assert len(state.players[0].draw_deck) == 2
        draw_ids = {c.card_id for c in state.players[0].draw_deck}
        assert draw_ids == {101, 102}
        # Event should indicate safety
        assert events[0]["type"] == "hand_shuffled_into_draw_deck"
        assert events[0]["reason"] == "safety_power"

    def test_no_safety_moves_to_discard(self):
        """Player without Safety has hand moved to discard normally."""
        hand_card = make_card(card_id=101, denomination=10)
        players = [
            make_player(
                player_id=1,
                hand=[hand_card],
                play_pile=[make_card(card_id=100, denomination=1000, power_text="Go")],
                has_gone_out=False,
                seat_position=1,
            ),
            make_player(player_id=2, seat_position=2, has_gone_out=True),
        ]
        state = make_game_state(players=players)

        round_manager = RoundManager()
        events = []
        round_manager._move_non_goers_hands_to_discard(state, events)

        assert len(state.players[0].hand) == 0
        assert len(state.players[0].discard_pile) == 1
        assert events[0]["type"] == "hand_moved_to_discard"


# --- Tests for Tally Scoring ---


class TestTallyScoring:
    """Tests for the Tally scoring split (Requirement 12.12)."""

    def test_tally_splits_score_half_and_half(self):
        """Tally splits scoring: half to scorer, half to Tally owner."""
        tally_card = make_card(card_id=110, denomination=1000, power_text="Tally")
        players = [
            make_player(player_id=1, seat_position=1, cumulative_score=0),
            make_player(
                player_id=2,
                play_pile=[tally_card],
                seat_position=2,
                cumulative_score=0,
            ),
        ]
        state = make_game_state(players=players)

        score_service = ScoreService()
        result = score_service.apply_tally_score(state, 1, tally_card, 1000)

        # Half to scorer (player 1), half to Tally owner (player 2)
        assert result[1] == 500
        assert result[2] == 500
        assert state.players[0].cumulative_score == 500
        assert state.players[1].cumulative_score == 500

    def test_tally_owner_is_scorer_no_split(self):
        """If Tally owner is the scorer, no split occurs (full points to scorer)."""
        tally_card = make_card(card_id=110, denomination=1000, power_text="Tally")
        players = [
            make_player(
                player_id=1,
                play_pile=[tally_card],
                seat_position=1,
                cumulative_score=0,
            ),
            make_player(player_id=2, seat_position=2, cumulative_score=0),
        ]
        state = make_game_state(players=players)

        score_service = ScoreService()
        result = score_service.apply_tally_score(state, 1, tally_card, 1000)

        # No split — scorer owns the Tally card
        assert result[1] == 1000
        assert state.players[0].cumulative_score == 1000

    def test_non_tally_card_scores_normally(self):
        """Non-Tally card scores full points to scorer."""
        normal_card = make_card(card_id=110, denomination=1000, power_text="Go")
        players = [
            make_player(player_id=1, seat_position=1, cumulative_score=0),
            make_player(
                player_id=2,
                play_pile=[normal_card],
                seat_position=2,
                cumulative_score=0,
            ),
        ]
        state = make_game_state(players=players)

        score_service = ScoreService()
        result = score_service.apply_tally_score(state, 1, normal_card, 1000)

        assert result[1] == 1000
        assert state.players[0].cumulative_score == 1000
        assert state.players[1].cumulative_score == 0


# --- Tests for Toxin Power ---


class TestToxinPower:
    """Tests for the Toxin power (Requirement 12.13)."""

    def setup_method(self):
        self.resolver = PowerResolver()

    def test_toxin_reveals_per_discard_count(self):
        """Toxin reveals cards equal to Discard count in opponent's play pile."""
        discard_card1 = make_card(card_id=120, denomination=10, power_text="Discard")
        discard_card2 = make_card(card_id=121, denomination=100, power_text="Discard")
        revealed1 = make_card(card_id=130, denomination=1000)
        revealed2 = make_card(card_id=131, denomination=10000)
        players = [
            make_player(player_id=1, seat_position=1),
            make_player(
                player_id=2,
                play_pile=[discard_card1, discard_card2],
                draw_deck=[revealed1, revealed2],
                seat_position=2,
            ),
            make_player(player_id=3, seat_position=3),
        ]
        state = make_game_state(players=players)
        card = make_card(power_text="Toxin")
        self.resolver.create_power_prompt(state, 0, card)

        # Activate
        events = self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        assert isinstance(events, list)
        assert events[0]["prompt_type"] == "choose_revealed_card"
        # 2 Discard cards in opponent's pile → 2 cards revealed
        assert len(events[0]["revealed_cards"]) == 2

    def test_toxin_no_discard_cards_no_effect(self):
        """Toxin has no effect if no opponents have Discard cards in play pile."""
        players = [
            make_player(player_id=1, seat_position=1),
            make_player(
                player_id=2,
                play_pile=[make_card(card_id=120, power_text="Go")],
                draw_deck=[make_card(card_id=130, denomination=1000)],
                seat_position=2,
            ),
            make_player(player_id=3, seat_position=3),
        ]
        state = make_game_state(players=players)
        card = make_card(power_text="Toxin")
        self.resolver.create_power_prompt(state, 0, card)

        events = self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        assert isinstance(events, list)
        assert events[0]["type"] == "power_activated"
        assert events[0]["effect"] == "no_discard_cards_found"

    def test_toxin_chosen_card_scores_and_all_go_to_hands(self):
        """Active player scores chosen card; all revealed go to owners' hands."""
        discard_card = make_card(card_id=120, denomination=10, power_text="Discard")
        revealed1 = make_card(card_id=130, denomination=1000)
        revealed2 = make_card(card_id=131, denomination=10000)
        # Player 2 has 1 Discard, Player 3 has 1 Discard
        players = [
            make_player(player_id=1, seat_position=1, cumulative_score=0),
            make_player(
                player_id=2,
                play_pile=[make_card(card_id=120, denomination=10, power_text="Discard")],
                draw_deck=[revealed1],
                seat_position=2,
            ),
            make_player(
                player_id=3,
                play_pile=[make_card(card_id=121, denomination=100, power_text="Discard")],
                draw_deck=[revealed2],
                seat_position=3,
            ),
        ]
        state = make_game_state(players=players)
        card = make_card(power_text="Toxin")
        self.resolver.create_power_prompt(state, 0, card)

        # Activate — reveals cards
        events = self.resolver.handle_power_choice(state, 0, {"choice": "activate"})
        assert events[0]["prompt_type"] == "choose_revealed_card"

        # Choose revealed card from player 3 (denomination 10000)
        events = self.resolver.handle_power_choice(
            state, 0, {"card_id": 131}
        )

        assert isinstance(events, list)
        assert events[0]["type"] == "power_activated"
        assert events[0]["power_name"] == "toxin"
        assert events[0]["scored_denomination"] == 10000
        # Active player scored 10000
        assert state.players[0].cumulative_score == 10000
        # All revealed cards go to their owners' hands
        assert revealed1 in state.players[1].hand
        assert revealed2 in state.players[2].hand


# --- Tests for new powers in ACTIVATABLE_POWERS ---


class TestExpansion4PowersRegistered:
    """Tests that expansion 4 powers are properly registered."""

    def test_battle_in_activatable_powers(self):
        assert "battle" in ACTIVATABLE_POWERS

    def test_evolve_in_activatable_powers(self):
        assert "evolve" in ACTIVATABLE_POWERS

    def test_freeze_in_activatable_powers(self):
        assert "freeze" in ACTIVATABLE_POWERS

    def test_mutate_in_activatable_powers(self):
        assert "mutate" in ACTIVATABLE_POWERS

    def test_process_in_activatable_powers(self):
        assert "process" in ACTIVATABLE_POWERS

    def test_toxin_in_activatable_powers(self):
        assert "toxin" in ACTIVATABLE_POWERS
