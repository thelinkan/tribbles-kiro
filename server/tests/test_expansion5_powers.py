"""Unit tests for Expansion 5 (Trials and Tribble-ations) powers.

Tests cover:
- Avalanche: if active player has >= 4 other cards in hand, all players discard
  one card, active player discards one additional
- Famine: set next sequence denomination to 1 regardless of current position
- Stampede: all players may play one card of current sequence denomination in
  turn order; only active player's card power may activate
- Time Warp: at round end, reduce next-round hand size by number of unique
  Time Warp denominations in play pile (min 1 card dealt), does not stack
  same denomination

Requirements: 13.1, 13.2, 13.3, 13.4
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest

from models import CardInstance, GameState, PendingPower, PlayerState
from game.powers.resolver import (
    ACTIVATABLE_POWERS,
    IMMEDIATE_POWERS,
    PASSIVE_POWERS,
    POWERS_NEEDING_TARGET,
    PowerResolver,
)
from game.round_manager import RoundManager


# --- Test Helpers ---


def make_card(
    card_id: int = 1,
    card_name: str = "Test Card",
    denomination: int = 100,
    power_text: str = "Go",
    expansion_id: int = 5,
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


# --- Tests for Avalanche Power ---


class TestAvalanchePower:
    """Tests for the Avalanche power (Requirement 13.1)."""

    def setup_method(self):
        self.resolver = PowerResolver()

    def test_avalanche_in_activatable_powers(self):
        """Avalanche is registered as an activatable power."""
        assert "avalanche" in ACTIVATABLE_POWERS

    def test_avalanche_in_powers_needing_target(self):
        """Avalanche is registered as needing a target (additional discard choice)."""
        assert "avalanche" in POWERS_NEEDING_TARGET

    def test_avalanche_condition_met_all_discard_and_prompt(self):
        """When active player has >= 4 cards in hand, all players discard one
        and active player is prompted for additional discard."""
        # Active player has 5 cards in hand (>= 4 condition met)
        p1_hand = [make_card(card_id=i, denomination=10) for i in range(1, 6)]
        p2_hand = [make_card(card_id=10, denomination=100)]
        p3_hand = [make_card(card_id=20, denomination=1000)]
        players = [
            make_player(player_id=1, hand=p1_hand, seat_position=1),
            make_player(player_id=2, hand=p2_hand, seat_position=2),
            make_player(player_id=3, hand=p3_hand, seat_position=3),
        ]
        state = make_game_state(players=players)
        card = make_card(card_id=99, power_text="Avalanche")
        self.resolver.create_power_prompt(state, 0, card)

        # Activate
        events = self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        assert isinstance(events, list)
        # Should be a prompt for additional discard
        assert events[0]["prompt_type"] == "choose_card_from_hand"
        assert events[0]["power_name"] == "avalanche"
        # All players should have lost one card from hand
        # P1: 5 - 1 = 4, P2: 1 - 1 = 0, P3: 1 - 1 = 0
        assert len(state.players[0].hand) == 4
        assert len(state.players[1].hand) == 0
        assert len(state.players[2].hand) == 0
        # Discarded cards should be in discard piles
        assert len(state.players[0].discard_pile) == 1
        assert len(state.players[1].discard_pile) == 1
        assert len(state.players[2].discard_pile) == 1

    def test_avalanche_additional_discard_executes(self):
        """Active player can choose additional card to discard after avalanche."""
        p1_hand = [make_card(card_id=i, denomination=10) for i in range(1, 6)]
        p2_hand = [make_card(card_id=10, denomination=100)]
        p3_hand = [make_card(card_id=20, denomination=1000)]
        players = [
            make_player(player_id=1, hand=p1_hand, seat_position=1),
            make_player(player_id=2, hand=p2_hand, seat_position=2),
            make_player(player_id=3, hand=p3_hand, seat_position=3),
        ]
        state = make_game_state(players=players)
        card = make_card(card_id=99, power_text="Avalanche")
        self.resolver.create_power_prompt(state, 0, card)

        # Activate (triggers all-discard and prompt)
        self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        # Now choose additional card to discard (card_id=1 should still be in hand)
        events = self.resolver.handle_power_choice(state, 0, {"card_id": 1})

        assert isinstance(events, list)
        assert events[0]["type"] == "power_activated"
        assert events[0]["power_name"] == "avalanche"
        assert events[0]["effect"] == "all_discarded_plus_additional"
        # P1 should now have 3 cards (5 - 1 auto - 1 additional)
        assert len(state.players[0].hand) == 3

    def test_avalanche_condition_not_met(self):
        """When active player has < 4 cards in hand, avalanche has no effect."""
        # Active player has 3 cards (< 4 condition NOT met)
        p1_hand = [make_card(card_id=i, denomination=10) for i in range(1, 4)]
        players = [
            make_player(player_id=1, hand=p1_hand, seat_position=1),
            make_player(player_id=2, seat_position=2),
            make_player(player_id=3, seat_position=3),
        ]
        state = make_game_state(players=players)
        card = make_card(card_id=99, power_text="Avalanche")
        self.resolver.create_power_prompt(state, 0, card)

        # Activate
        events = self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        assert isinstance(events, list)
        assert events[0]["type"] == "power_activated"
        assert events[0]["effect"] == "condition_not_met"
        # No cards should have been discarded
        assert len(state.players[0].hand) == 3

    def test_avalanche_decline(self):
        """Player can decline the Avalanche power."""
        p1_hand = [make_card(card_id=i, denomination=10) for i in range(1, 6)]
        players = [
            make_player(player_id=1, hand=p1_hand, seat_position=1),
            make_player(player_id=2, seat_position=2),
            make_player(player_id=3, seat_position=3),
        ]
        state = make_game_state(players=players)
        card = make_card(card_id=99, power_text="Avalanche")
        self.resolver.create_power_prompt(state, 0, card)

        events = self.resolver.handle_power_choice(state, 0, {"choice": "decline"})

        assert isinstance(events, list)
        assert events[0]["type"] == "power_declined"
        # No cards discarded
        assert len(state.players[0].hand) == 5



# --- Tests for Famine Power ---


class TestFaminePower:
    """Tests for the Famine power (Requirement 13.2)."""

    def setup_method(self):
        self.resolver = PowerResolver()

    def test_famine_in_activatable_powers(self):
        """Famine is registered as an activatable power."""
        assert "famine" in ACTIVATABLE_POWERS

    def test_famine_in_immediate_powers(self):
        """Famine is registered as an immediate power."""
        assert "famine" in IMMEDIATE_POWERS

    def test_famine_resets_sequence_to_1(self):
        """Famine sets the next sequence denomination to 1."""
        players = [
            make_player(player_id=1, seat_position=1),
            make_player(player_id=2, seat_position=2),
            make_player(player_id=3, seat_position=3),
        ]
        state = make_game_state(players=players, current_sequence=1000)
        card = make_card(power_text="Famine")
        self.resolver.create_power_prompt(state, 0, card)

        events = self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        assert isinstance(events, list)
        assert events[0]["type"] == "power_activated"
        assert events[0]["power_name"] == "famine"
        assert events[0]["new_sequence"] == 1
        assert state.current_sequence == 1

    def test_famine_resets_from_any_sequence(self):
        """Famine resets to 1 regardless of current sequence position."""
        for seq in [1, 10, 100, 1000, 10000, 100000]:
            players = [
                make_player(player_id=1, seat_position=1),
                make_player(player_id=2, seat_position=2),
                make_player(player_id=3, seat_position=3),
            ]
            state = make_game_state(players=players, current_sequence=seq)
            card = make_card(power_text="Famine")
            self.resolver.create_power_prompt(state, 0, card)

            events = self.resolver.handle_power_choice(
                state, 0, {"choice": "activate"}
            )

            assert state.current_sequence == 1

    def test_famine_decline(self):
        """Player can decline the Famine power."""
        players = [
            make_player(player_id=1, seat_position=1),
            make_player(player_id=2, seat_position=2),
            make_player(player_id=3, seat_position=3),
        ]
        state = make_game_state(players=players, current_sequence=1000)
        card = make_card(power_text="Famine")
        self.resolver.create_power_prompt(state, 0, card)

        events = self.resolver.handle_power_choice(state, 0, {"choice": "decline"})

        assert isinstance(events, list)
        assert events[0]["type"] == "power_declined"
        # Sequence unchanged
        assert state.current_sequence == 1000


# --- Tests for Stampede Power ---


class TestStampedePower:
    """Tests for the Stampede power (Requirement 13.3)."""

    def setup_method(self):
        self.resolver = PowerResolver()

    def test_stampede_in_activatable_powers(self):
        """Stampede is registered as an activatable power."""
        assert "stampede" in ACTIVATABLE_POWERS

    def test_stampede_in_immediate_powers(self):
        """Stampede is registered as an immediate power."""
        assert "stampede" in IMMEDIATE_POWERS

    def test_stampede_all_players_play_matching_card(self):
        """All players with a matching card play it to their play pile."""
        # Current sequence is 100
        p1_hand = [make_card(card_id=1, denomination=100, power_text="Go")]
        p2_hand = [make_card(card_id=2, denomination=100, power_text="Skip")]
        p3_hand = [make_card(card_id=3, denomination=100, power_text="Reverse")]
        players = [
            make_player(player_id=1, hand=p1_hand, seat_position=1),
            make_player(player_id=2, hand=p2_hand, seat_position=2),
            make_player(player_id=3, hand=p3_hand, seat_position=3),
        ]
        state = make_game_state(
            players=players, current_player_index=0, current_sequence=100
        )
        card = make_card(power_text="Stampede")
        self.resolver.create_power_prompt(state, 0, card)

        events = self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        assert isinstance(events, list)
        # All 3 players should have played their card
        assert len(state.players[0].hand) == 0
        assert len(state.players[1].hand) == 0
        assert len(state.players[2].hand) == 0
        assert len(state.players[0].play_pile) == 1
        assert len(state.players[1].play_pile) == 1
        assert len(state.players[2].play_pile) == 1

    def test_stampede_only_active_player_power_noted(self):
        """Only the active player's card power is noted for activation."""
        p1_hand = [make_card(card_id=1, denomination=100, power_text="Go")]
        p2_hand = [make_card(card_id=2, denomination=100, power_text="Skip")]
        players = [
            make_player(player_id=1, hand=p1_hand, seat_position=1),
            make_player(player_id=2, hand=p2_hand, seat_position=2),
            make_player(player_id=3, seat_position=3),
        ]
        state = make_game_state(
            players=players, current_player_index=0, current_sequence=100
        )
        card = make_card(power_text="Stampede")
        self.resolver.create_power_prompt(state, 0, card)

        events = self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        assert isinstance(events, list)
        # Find the main power_activated event
        activated = [e for e in events if e.get("type") == "power_activated"]
        assert len(activated) == 1
        assert activated[0]["active_player_card_power"] == "go"

    def test_stampede_no_matching_cards(self):
        """If no player has a matching card, stampede still resolves."""
        p1_hand = [make_card(card_id=1, denomination=10, power_text="Go")]
        p2_hand = [make_card(card_id=2, denomination=1000, power_text="Skip")]
        players = [
            make_player(player_id=1, hand=p1_hand, seat_position=1),
            make_player(player_id=2, hand=p2_hand, seat_position=2),
            make_player(player_id=3, seat_position=3),
        ]
        state = make_game_state(
            players=players, current_player_index=0, current_sequence=100
        )
        card = make_card(power_text="Stampede")
        self.resolver.create_power_prompt(state, 0, card)

        events = self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        assert isinstance(events, list)
        activated = [e for e in events if e.get("type") == "power_activated"]
        assert activated[0]["cards_played"] == 0
        # Hands unchanged
        assert len(state.players[0].hand) == 1
        assert len(state.players[1].hand) == 1

    def test_stampede_advances_sequence(self):
        """Stampede advances the sequence after resolution."""
        p1_hand = [make_card(card_id=1, denomination=100, power_text="Go")]
        players = [
            make_player(player_id=1, hand=p1_hand, seat_position=1),
            make_player(player_id=2, seat_position=2),
            make_player(player_id=3, seat_position=3),
        ]
        state = make_game_state(
            players=players, current_player_index=0, current_sequence=100
        )
        card = make_card(power_text="Stampede")
        self.resolver.create_power_prompt(state, 0, card)

        events = self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        # Sequence should advance from 100 to 1000
        assert state.current_sequence == 1000

    def test_stampede_skips_decked_players(self):
        """Decked players are skipped during stampede."""
        p1_hand = [make_card(card_id=1, denomination=100, power_text="Go")]
        p2_hand = [make_card(card_id=2, denomination=100, power_text="Skip")]
        players = [
            make_player(player_id=1, hand=p1_hand, seat_position=1),
            make_player(player_id=2, hand=p2_hand, seat_position=2, is_decked=True),
            make_player(player_id=3, seat_position=3),
        ]
        state = make_game_state(
            players=players, current_player_index=0, current_sequence=100
        )
        card = make_card(power_text="Stampede")
        self.resolver.create_power_prompt(state, 0, card)

        events = self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        # Decked player 2 should not have played
        assert len(state.players[1].hand) == 1
        assert len(state.players[1].play_pile) == 0
        # Active player 1 should have played
        assert len(state.players[0].hand) == 0
        assert len(state.players[0].play_pile) == 1



# --- Tests for Time Warp Power ---


class TestTimeWarpPower:
    """Tests for the Time Warp power (Requirement 13.4)."""

    def test_time_warp_in_passive_powers(self):
        """Time Warp is registered as a passive power."""
        assert "time_warp" in PASSIVE_POWERS

    def test_time_warp_reduces_cards_dealt(self):
        """Time Warp reduces cards dealt next round by unique denomination count."""
        # Player did NOT go out, has 1 Time Warp card in play pile
        time_warp_card = make_card(
            card_id=50, denomination=100, power_text="Time Warp"
        )
        draw_deck = [make_card(card_id=i, denomination=10) for i in range(60, 80)]
        players = [
            make_player(
                player_id=1,
                play_pile=[time_warp_card],
                draw_deck=draw_deck,
                has_gone_out=False,
                seat_position=1,
            ),
            make_player(
                player_id=2,
                draw_deck=[make_card(card_id=i, denomination=10) for i in range(80, 100)],
                has_gone_out=True,
                seat_position=2,
            ),
        ]
        state = make_game_state(players=players)

        round_manager = RoundManager()
        events = []

        # Track time warp reductions
        round_manager._track_time_warp_reductions(state, events)

        # Player 1 should have 1 unique Time Warp denomination
        assert len(state.players[0].time_warp_reductions) == 1
        assert 100 in state.players[0].time_warp_reductions

        # Now deal new hands — player 1 should get 6 cards (7 - 1)
        deal_events = []
        round_manager._deal_new_hands(state, [], deal_events)

        assert len(state.players[0].hand) == 6

    def test_time_warp_multiple_unique_denominations(self):
        """Multiple unique Time Warp denominations reduce by that count."""
        tw1 = make_card(card_id=50, denomination=100, power_text="Time Warp")
        tw2 = make_card(card_id=51, denomination=1000, power_text="Time Warp")
        tw3 = make_card(card_id=52, denomination=10000, power_text="Time Warp")
        draw_deck = [make_card(card_id=i, denomination=10) for i in range(60, 80)]
        players = [
            make_player(
                player_id=1,
                play_pile=[tw1, tw2, tw3],
                draw_deck=draw_deck,
                has_gone_out=False,
                seat_position=1,
            ),
            make_player(player_id=2, has_gone_out=True, seat_position=2),
        ]
        state = make_game_state(players=players)

        round_manager = RoundManager()
        events = []
        round_manager._track_time_warp_reductions(state, events)

        assert len(state.players[0].time_warp_reductions) == 3

        deal_events = []
        round_manager._deal_new_hands(state, [], deal_events)

        # 7 - 3 = 4 cards dealt
        assert len(state.players[0].hand) == 4

    def test_time_warp_same_denomination_does_not_stack(self):
        """Same denomination Time Warp cards do NOT stack."""
        tw1 = make_card(card_id=50, denomination=100, power_text="Time Warp")
        tw2 = make_card(card_id=51, denomination=100, power_text="Time Warp")
        draw_deck = [make_card(card_id=i, denomination=10) for i in range(60, 80)]
        players = [
            make_player(
                player_id=1,
                play_pile=[tw1, tw2],
                draw_deck=draw_deck,
                has_gone_out=False,
                seat_position=1,
            ),
            make_player(player_id=2, has_gone_out=True, seat_position=2),
        ]
        state = make_game_state(players=players)

        round_manager = RoundManager()
        events = []
        round_manager._track_time_warp_reductions(state, events)

        # Only 1 unique denomination (100), even though 2 cards
        assert len(state.players[0].time_warp_reductions) == 1

        deal_events = []
        round_manager._deal_new_hands(state, [], deal_events)

        # 7 - 1 = 6 cards dealt
        assert len(state.players[0].hand) == 6

    def test_time_warp_minimum_one_card_dealt(self):
        """Time Warp reduction cannot reduce below 1 card dealt."""
        # 6 unique Time Warp denominations would reduce by 6 (7-6=1)
        tw_cards = [
            make_card(card_id=50+i, denomination=d, power_text="Time Warp")
            for i, d in enumerate([1, 10, 100, 1000, 10000, 100000])
        ]
        draw_deck = [make_card(card_id=i, denomination=10) for i in range(60, 80)]
        players = [
            make_player(
                player_id=1,
                play_pile=tw_cards,
                draw_deck=draw_deck,
                has_gone_out=False,
                seat_position=1,
            ),
            make_player(player_id=2, has_gone_out=True, seat_position=2),
        ]
        state = make_game_state(players=players)

        round_manager = RoundManager()
        events = []
        round_manager._track_time_warp_reductions(state, events)

        assert len(state.players[0].time_warp_reductions) == 6

        deal_events = []
        round_manager._deal_new_hands(state, [], deal_events)

        # 7 - 6 = 1 card dealt (minimum)
        assert len(state.players[0].hand) == 1

    def test_time_warp_not_applied_to_player_who_went_out(self):
        """Time Warp does NOT apply to players who went out."""
        tw = make_card(card_id=50, denomination=100, power_text="Time Warp")
        draw_deck = [make_card(card_id=i, denomination=10) for i in range(60, 80)]
        players = [
            make_player(
                player_id=1,
                play_pile=[tw],
                draw_deck=draw_deck,
                has_gone_out=True,  # Went out — no reduction
                seat_position=1,
            ),
            make_player(player_id=2, seat_position=2),
        ]
        state = make_game_state(players=players)

        round_manager = RoundManager()
        events = []
        round_manager._track_time_warp_reductions(state, events)

        # Player who went out should have no reductions
        assert len(state.players[0].time_warp_reductions) == 0

        deal_events = []
        round_manager._deal_new_hands(state, [], deal_events)

        # Normal 7 cards dealt
        assert len(state.players[0].hand) == 7

    def test_time_warp_no_effect_without_time_warp_cards(self):
        """Players without Time Warp cards get normal hand size."""
        normal_card = make_card(card_id=50, denomination=100, power_text="Go")
        draw_deck = [make_card(card_id=i, denomination=10) for i in range(60, 80)]
        players = [
            make_player(
                player_id=1,
                play_pile=[normal_card],
                draw_deck=draw_deck,
                has_gone_out=False,
                seat_position=1,
            ),
            make_player(player_id=2, has_gone_out=True, seat_position=2),
        ]
        state = make_game_state(players=players)

        round_manager = RoundManager()
        events = []
        round_manager._track_time_warp_reductions(state, events)

        assert len(state.players[0].time_warp_reductions) == 0

        deal_events = []
        round_manager._deal_new_hands(state, [], deal_events)

        # Normal 7 cards dealt
        assert len(state.players[0].hand) == 7
