"""Unit tests for Expansion 6 (Nothing But Tribble) powers.

Tests cover:
- Advance: playable in place of 1-denomination card after sequence break
- Assimilate: move top of target's draw deck to active player's play pile as borrowed
- Convert: place Convert card under draw deck, move top of draw deck to play pile
- IDIC scoring: 10000 points per unique power in play pile for each IDIC card of distinct denomination
- Masaka: all players place hands under draw decks, deal 3 cards to each
- Scan: reveal top 3 of own draw deck, reorder and place on top or bottom
- Utilize: opponent randomly places one hand card on their play pile; active player scores

Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 14.7
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
from game.engine import GameEngine, GameSession, PlayerSetup
from game.round_manager import RoundManager
from scoring.service import ScoreService


# --- Test Helpers ---


def make_card(
    card_id: int = 1,
    card_name: str = "Test Card",
    denomination: int = 100,
    power_text: str = "Go",
    expansion_id: int = 6,
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
    sequence_broken: bool = False,
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
        sequence_broken=sequence_broken,
    )


# --- Tests for Advance Power ---


class TestAdvancePower:
    """Tests for the Advance power (Requirement 14.1)."""

    def test_advance_in_passive_powers(self):
        """Advance is registered as a passive power (play-validity rule, not activatable)."""
        assert "advance" in PASSIVE_POWERS

    def test_advance_not_in_activatable_powers(self):
        """Advance is NOT an activatable power."""
        assert "advance" not in ACTIVATABLE_POWERS

    def test_advance_playable_after_sequence_break(self):
        """Advance card can be played after a sequence break regardless of denomination."""
        engine = GameEngine()
        # Create a card with Advance power at denomination 100 (not 1)
        advance_card = make_card(card_id=1, denomination=100, power_text="Advance")
        # Sequence is broken, current sequence is 1000
        state = make_game_state(current_sequence=1000, sequence_broken=True)

        result = engine._is_valid_play(advance_card, state)
        assert result is True

    def test_advance_not_playable_without_sequence_break(self):
        """Advance card cannot be played if sequence is not broken (unless denomination matches)."""
        engine = GameEngine()
        advance_card = make_card(card_id=1, denomination=100, power_text="Advance")
        # Sequence is NOT broken, current sequence is 1000
        state = make_game_state(current_sequence=1000, sequence_broken=False)

        result = engine._is_valid_play(advance_card, state)
        assert result is False

    def test_advance_playable_when_denomination_matches(self):
        """Advance card can be played normally when denomination matches sequence."""
        engine = GameEngine()
        advance_card = make_card(card_id=1, denomination=100, power_text="Advance")
        state = make_game_state(current_sequence=100, sequence_broken=False)

        result = engine._is_valid_play(advance_card, state)
        assert result is True

    def test_advance_resets_sequence_to_10_after_break(self):
        """When Advance is played after a sequence break, sequence resets to 10."""
        engine = GameEngine()
        advance_card = make_card(card_id=1, denomination=1000, power_text="Advance")
        hand = [advance_card]
        players = [
            make_player(player_id=1, hand=hand, seat_position=1),
            make_player(player_id=2, seat_position=2),
        ]
        state = make_game_state(
            players=players, current_sequence=10000, sequence_broken=True
        )
        # Store the game state in the engine
        engine._games["test-game"] = state

        events = engine.process_action("test-game", 1, {"type": "play_card", "card_id": 1})

        assert isinstance(events, list)
        assert state.current_sequence == 10


# --- Tests for Assimilate Power ---


class TestAssimilatePower:
    """Tests for the Assimilate power (Requirement 14.2)."""

    def setup_method(self):
        self.resolver = PowerResolver()

    def test_assimilate_in_activatable_powers(self):
        """Assimilate is registered as an activatable power."""
        assert "assimilate" in ACTIVATABLE_POWERS

    def test_assimilate_in_powers_needing_target(self):
        """Assimilate requires a target player."""
        assert "assimilate" in POWERS_NEEDING_TARGET

    def test_assimilate_moves_top_of_target_deck_to_play_pile(self):
        """Assimilate moves top of target's draw deck to active player's play pile."""
        target_top_card = make_card(card_id=50, denomination=1000, power_text="Go")
        target_deck = [target_top_card, make_card(card_id=51, denomination=100)]
        players = [
            make_player(player_id=1, seat_position=1),
            make_player(player_id=2, draw_deck=target_deck, seat_position=2),
        ]
        state = make_game_state(players=players)
        card = make_card(card_id=99, power_text="Assimilate")
        self.resolver.create_power_prompt(state, 0, card)

        # Activate
        self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        # Choose target
        events = self.resolver.handle_power_choice(
            state, 0, {"target_player_index": 1}
        )

        assert isinstance(events, list)
        assert events[0]["type"] == "power_activated"
        assert events[0]["power_name"] == "assimilate"
        # Card moved to active player's play pile
        assert len(state.players[0].play_pile) == 1
        assert state.players[0].play_pile[0].card_id == 50
        # Target's draw deck reduced
        assert len(state.players[1].draw_deck) == 1

    def test_assimilate_records_borrowed_card(self):
        """Assimilate records the card as borrowed with original owner."""
        target_top_card = make_card(card_id=50, denomination=1000, power_text="Go")
        players = [
            make_player(player_id=1, seat_position=1),
            make_player(player_id=2, draw_deck=[target_top_card], seat_position=2),
        ]
        state = make_game_state(players=players)
        card = make_card(card_id=99, power_text="Assimilate")
        self.resolver.create_power_prompt(state, 0, card)
        self.resolver.handle_power_choice(state, 0, {"choice": "activate"})
        self.resolver.handle_power_choice(state, 0, {"target_player_index": 1})

        # Check borrowed_cards
        assert len(state.players[0].borrowed_cards) == 1
        borrowed_card, owner_id = state.players[0].borrowed_cards[0]
        assert borrowed_card.card_id == 50
        assert owner_id == 2

    def test_assimilate_cannot_target_self(self):
        """Assimilate cannot target yourself."""
        players = [
            make_player(player_id=1, draw_deck=[make_card()], seat_position=1),
            make_player(player_id=2, seat_position=2),
        ]
        state = make_game_state(players=players)
        card = make_card(card_id=99, power_text="Assimilate")
        self.resolver.create_power_prompt(state, 0, card)
        self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        result = self.resolver.handle_power_choice(
            state, 0, {"target_player_index": 0}
        )

        assert isinstance(result, tuple)
        assert result[0] == "invalid_target"

    def test_assimilate_target_must_have_draw_deck(self):
        """Assimilate target must have cards in draw deck."""
        players = [
            make_player(player_id=1, seat_position=1),
            make_player(player_id=2, draw_deck=[], seat_position=2),
        ]
        state = make_game_state(players=players)
        card = make_card(card_id=99, power_text="Assimilate")
        self.resolver.create_power_prompt(state, 0, card)
        self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        result = self.resolver.handle_power_choice(
            state, 0, {"target_player_index": 1}
        )

        assert isinstance(result, tuple)
        assert result[0] == "invalid_target"

    def test_assimilate_borrowed_cards_returned_at_round_end(self):
        """Borrowed cards are returned to original owner at round end."""
        borrowed_card = make_card(card_id=50, denomination=1000, power_text="Go")
        draw_deck_p1 = [make_card(card_id=i, denomination=10) for i in range(60, 80)]
        draw_deck_p2 = [make_card(card_id=i, denomination=10) for i in range(80, 100)]
        players = [
            make_player(
                player_id=1,
                play_pile=[borrowed_card],
                draw_deck=draw_deck_p1,
                has_gone_out=True,
                seat_position=1,
            ),
            make_player(
                player_id=2,
                draw_deck=draw_deck_p2,
                has_gone_out=False,
                seat_position=2,
            ),
        ]
        # Set up borrowed_cards
        players[0].borrowed_cards = [(borrowed_card, 2)]
        state = make_game_state(players=players)

        round_manager = RoundManager()
        events = round_manager.process_end_of_round(state)

        # Check that borrowed card was returned
        returned_events = [e for e in events if e.get("type") == "borrowed_card_returned"]
        assert len(returned_events) == 1
        assert returned_events[0]["owner_player_id"] == 2
        assert returned_events[0]["card_id"] == 50


# --- Tests for Convert Power ---


class TestConvertPower:
    """Tests for the Convert power (Requirement 14.3)."""

    def setup_method(self):
        self.resolver = PowerResolver()

    def test_convert_in_activatable_powers(self):
        """Convert is registered as an activatable power."""
        assert "convert" in ACTIVATABLE_POWERS

    def test_convert_in_immediate_powers(self):
        """Convert is registered as an immediate power."""
        assert "convert" in IMMEDIATE_POWERS

    def test_convert_moves_card_under_deck_and_draws(self):
        """Convert places itself under draw deck and moves top of deck to play pile."""
        convert_card = make_card(card_id=99, denomination=100, power_text="Convert")
        deck_top = make_card(card_id=50, denomination=1000, power_text="Go")
        deck_bottom = make_card(card_id=51, denomination=10, power_text="Skip")
        players = [
            make_player(
                player_id=1,
                play_pile=[convert_card],
                draw_deck=[deck_top, deck_bottom],
                seat_position=1,
            ),
            make_player(player_id=2, seat_position=2),
        ]
        state = make_game_state(players=players)
        self.resolver.create_power_prompt(state, 0, convert_card)

        events = self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        assert isinstance(events, list)
        assert events[0]["type"] == "power_activated"
        assert events[0]["power_name"] == "convert"
        # Convert card should be at the bottom of draw deck
        assert state.players[0].draw_deck[-1].card_id == 99
        # Top of deck (card 50) should now be in play pile
        assert state.players[0].play_pile[-1].card_id == 50
        # Original convert card should NOT be in play pile
        assert all(c.card_id != 99 for c in state.players[0].play_pile)

    def test_convert_empty_deck_after_placing_card(self):
        """Convert handles case where deck is empty after placing card under it."""
        convert_card = make_card(card_id=99, denomination=100, power_text="Convert")
        players = [
            make_player(
                player_id=1,
                play_pile=[convert_card],
                draw_deck=[],
                seat_position=1,
            ),
            make_player(player_id=2, seat_position=2),
        ]
        state = make_game_state(players=players)
        self.resolver.create_power_prompt(state, 0, convert_card)

        events = self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        assert isinstance(events, list)
        assert events[0]["type"] == "power_activated"
        # Convert card placed under deck, then drawn back as top card
        # Since deck was empty, convert goes under, then it's the only card, so it gets drawn
        assert state.players[0].play_pile[-1].card_id == 99

    def test_convert_decline(self):
        """Player can decline the Convert power."""
        convert_card = make_card(card_id=99, denomination=100, power_text="Convert")
        players = [
            make_player(
                player_id=1,
                play_pile=[convert_card],
                draw_deck=[make_card(card_id=50)],
                seat_position=1,
            ),
            make_player(player_id=2, seat_position=2),
        ]
        state = make_game_state(players=players)
        self.resolver.create_power_prompt(state, 0, convert_card)

        events = self.resolver.handle_power_choice(state, 0, {"choice": "decline"})

        assert isinstance(events, list)
        assert events[0]["type"] == "power_declined"
        # Play pile unchanged
        assert len(state.players[0].play_pile) == 1
        assert state.players[0].play_pile[0].card_id == 99


# --- Tests for IDIC Scoring ---


class TestIDICScoring:
    """Tests for the IDIC scoring power (Requirement 14.4)."""

    def test_idic_in_passive_powers(self):
        """IDIC is registered as a passive power."""
        assert "idic" in PASSIVE_POWERS

    def test_idic_basic_scoring(self):
        """IDIC awards 10000 per unique power for each distinct IDIC denomination."""
        # Player has 1 IDIC card and 3 unique powers in play pile
        idic_card = make_card(card_id=1, denomination=100, power_text="IDIC")
        go_card = make_card(card_id=2, denomination=10, power_text="Go")
        skip_card = make_card(card_id=3, denomination=1000, power_text="Skip")
        players = [
            make_player(
                player_id=1,
                play_pile=[idic_card, go_card, skip_card],
                has_gone_out=True,
                seat_position=1,
            ),
        ]
        state = make_game_state(players=players)

        score_service = ScoreService()
        idic_scores = score_service.calculate_idic_scores(state)

        # 1 IDIC card × 10000 × 3 unique powers (idic, go, skip)
        assert idic_scores[1] == 1 * 10000 * 3

    def test_idic_multiple_distinct_denominations(self):
        """Multiple IDIC cards of distinct denominations multiply the bonus."""
        idic1 = make_card(card_id=1, denomination=100, power_text="IDIC")
        idic2 = make_card(card_id=2, denomination=1000, power_text="IDIC")
        go_card = make_card(card_id=3, denomination=10, power_text="Go")
        players = [
            make_player(
                player_id=1,
                play_pile=[idic1, idic2, go_card],
                has_gone_out=True,
                seat_position=1,
            ),
        ]
        state = make_game_state(players=players)

        score_service = ScoreService()
        idic_scores = score_service.calculate_idic_scores(state)

        # 2 distinct IDIC denominations × 10000 × 2 unique powers (idic, go)
        assert idic_scores[1] == 2 * 10000 * 2

    def test_idic_same_denomination_does_not_stack(self):
        """Same denomination IDIC cards do NOT stack."""
        idic1 = make_card(card_id=1, denomination=100, power_text="IDIC")
        idic2 = make_card(card_id=2, denomination=100, power_text="IDIC")
        go_card = make_card(card_id=3, denomination=10, power_text="Go")
        players = [
            make_player(
                player_id=1,
                play_pile=[idic1, idic2, go_card],
                has_gone_out=True,
                seat_position=1,
            ),
        ]
        state = make_game_state(players=players)

        score_service = ScoreService()
        idic_scores = score_service.calculate_idic_scores(state)

        # Only 1 distinct denomination (100) × 10000 × 2 unique powers (idic, go)
        assert idic_scores[1] == 1 * 10000 * 2

    def test_idic_no_score_if_not_gone_out(self):
        """IDIC does not score for players who did not go out."""
        idic_card = make_card(card_id=1, denomination=100, power_text="IDIC")
        go_card = make_card(card_id=2, denomination=10, power_text="Go")
        players = [
            make_player(
                player_id=1,
                play_pile=[idic_card, go_card],
                has_gone_out=False,
                seat_position=1,
            ),
        ]
        state = make_game_state(players=players)

        score_service = ScoreService()
        idic_scores = score_service.calculate_idic_scores(state)

        assert idic_scores[1] == 0

    def test_idic_no_score_without_idic_cards(self):
        """No IDIC score if player has no IDIC cards."""
        go_card = make_card(card_id=1, denomination=10, power_text="Go")
        skip_card = make_card(card_id=2, denomination=100, power_text="Skip")
        players = [
            make_player(
                player_id=1,
                play_pile=[go_card, skip_card],
                has_gone_out=True,
                seat_position=1,
            ),
        ]
        state = make_game_state(players=players)

        score_service = ScoreService()
        idic_scores = score_service.calculate_idic_scores(state)

        assert idic_scores[1] == 0

    def test_idic_compound_powers_count_as_distinct(self):
        """Compound powers count as distinct powers for IDIC scoring."""
        idic_card = make_card(card_id=1, denomination=100, power_text="IDIC")
        compound_card = make_card(card_id=2, denomination=10, power_text="Clone & Reverse")
        go_card = make_card(card_id=3, denomination=1000, power_text="Go")
        players = [
            make_player(
                player_id=1,
                play_pile=[idic_card, compound_card, go_card],
                has_gone_out=True,
                seat_position=1,
            ),
        ]
        state = make_game_state(players=players)

        score_service = ScoreService()
        idic_scores = score_service.calculate_idic_scores(state)

        # 3 unique powers: "idic", "clone & reverse", "go"
        # 1 IDIC denomination × 10000 × 3
        assert idic_scores[1] == 1 * 10000 * 3


# --- Tests for Masaka Power ---


class TestMasakaPower:
    """Tests for the Masaka power (Requirement 14.5)."""

    def setup_method(self):
        self.resolver = PowerResolver()

    def test_masaka_in_activatable_powers(self):
        """Masaka is registered as an activatable power."""
        assert "masaka" in ACTIVATABLE_POWERS

    def test_masaka_in_immediate_powers(self):
        """Masaka is registered as an immediate power."""
        assert "masaka" in IMMEDIATE_POWERS

    def test_masaka_places_hands_under_decks_and_deals_3(self):
        """Masaka places all hands under draw decks and deals 3 to each player."""
        p1_hand = [make_card(card_id=i, denomination=10) for i in range(1, 4)]
        p1_deck = [make_card(card_id=i, denomination=100) for i in range(10, 20)]
        p2_hand = [make_card(card_id=i, denomination=10) for i in range(4, 7)]
        p2_deck = [make_card(card_id=i, denomination=100) for i in range(20, 30)]
        players = [
            make_player(player_id=1, hand=p1_hand, draw_deck=p1_deck, seat_position=1),
            make_player(player_id=2, hand=p2_hand, draw_deck=p2_deck, seat_position=2),
        ]
        state = make_game_state(players=players)
        card = make_card(card_id=99, power_text="Masaka")
        self.resolver.create_power_prompt(state, 0, card)

        events = self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        assert isinstance(events, list)
        # Each player should have exactly 3 cards in hand
        assert len(state.players[0].hand) == 3
        assert len(state.players[1].hand) == 3
        # Original hand cards should be in the draw deck (at the bottom)
        # Draw deck should be: original deck cards (minus 3 dealt) + original hand cards at bottom
        # Total deck before deal: 10 (original) + 3 (hand placed under) = 13
        # After dealing 3: 13 - 3 = 10 remaining in deck
        assert len(state.players[0].draw_deck) == 10

    def test_masaka_skips_decked_players(self):
        """Masaka skips decked players."""
        p1_hand = [make_card(card_id=i, denomination=10) for i in range(1, 4)]
        p1_deck = [make_card(card_id=i, denomination=100) for i in range(10, 20)]
        players = [
            make_player(player_id=1, hand=p1_hand, draw_deck=p1_deck, seat_position=1),
            make_player(player_id=2, is_decked=True, seat_position=2),
        ]
        state = make_game_state(players=players)
        card = make_card(card_id=99, power_text="Masaka")
        self.resolver.create_power_prompt(state, 0, card)

        events = self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        assert isinstance(events, list)
        # Player 1 should have 3 cards
        assert len(state.players[0].hand) == 3
        # Decked player 2 should be unchanged
        assert len(state.players[1].hand) == 0

    def test_masaka_decline(self):
        """Player can decline the Masaka power."""
        p1_hand = [make_card(card_id=i, denomination=10) for i in range(1, 4)]
        p1_deck = [make_card(card_id=i, denomination=100) for i in range(10, 20)]
        players = [
            make_player(player_id=1, hand=p1_hand, draw_deck=p1_deck, seat_position=1),
            make_player(player_id=2, seat_position=2),
        ]
        state = make_game_state(players=players)
        card = make_card(card_id=99, power_text="Masaka")
        self.resolver.create_power_prompt(state, 0, card)

        events = self.resolver.handle_power_choice(state, 0, {"choice": "decline"})

        assert isinstance(events, list)
        assert events[0]["type"] == "power_declined"
        # Hands unchanged
        assert len(state.players[0].hand) == 3


# --- Tests for Scan Power ---


class TestScanPower:
    """Tests for the Scan power (Requirement 14.6)."""

    def setup_method(self):
        self.resolver = PowerResolver()

    def test_scan_in_activatable_powers(self):
        """Scan is registered as an activatable power."""
        assert "scan" in ACTIVATABLE_POWERS

    def test_scan_in_powers_needing_target(self):
        """Scan requires a choice (reorder and placement)."""
        assert "scan" in POWERS_NEEDING_TARGET

    def test_scan_reveals_top_3_cards(self):
        """Scan reveals top 3 cards of own draw deck in the prompt."""
        deck = [
            make_card(card_id=10, denomination=1, power_text="Go"),
            make_card(card_id=11, denomination=10, power_text="Skip"),
            make_card(card_id=12, denomination=100, power_text="Reverse"),
            make_card(card_id=13, denomination=1000, power_text="Poison"),
        ]
        players = [
            make_player(player_id=1, draw_deck=deck, seat_position=1),
            make_player(player_id=2, seat_position=2),
        ]
        state = make_game_state(players=players)
        card = make_card(card_id=99, power_text="Scan")
        self.resolver.create_power_prompt(state, 0, card)

        events = self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        assert isinstance(events, list)
        assert events[0]["prompt_type"] == "scan_reorder"
        assert len(events[0]["revealed_cards"]) == 3
        assert events[0]["revealed_cards"][0]["card_id"] == 10
        assert events[0]["revealed_cards"][1]["card_id"] == 11
        assert events[0]["revealed_cards"][2]["card_id"] == 12

    def test_scan_reorder_place_on_top(self):
        """Scan allows reordering and placing on top of draw deck."""
        deck = [
            make_card(card_id=10, denomination=1, power_text="Go"),
            make_card(card_id=11, denomination=10, power_text="Skip"),
            make_card(card_id=12, denomination=100, power_text="Reverse"),
            make_card(card_id=13, denomination=1000, power_text="Poison"),
        ]
        players = [
            make_player(player_id=1, draw_deck=deck, seat_position=1),
            make_player(player_id=2, seat_position=2),
        ]
        state = make_game_state(players=players)
        card = make_card(card_id=99, power_text="Scan")
        self.resolver.create_power_prompt(state, 0, card)
        self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        # Reorder: 12, 10, 11 and place on top
        events = self.resolver.handle_power_choice(
            state, 0, {"card_ids": [12, 10, 11], "placement": "top"}
        )

        assert isinstance(events, list)
        assert events[0]["type"] == "power_activated"
        assert events[0]["placement"] == "top"
        # Deck should now be: 12, 10, 11, 13
        assert state.players[0].draw_deck[0].card_id == 12
        assert state.players[0].draw_deck[1].card_id == 10
        assert state.players[0].draw_deck[2].card_id == 11
        assert state.players[0].draw_deck[3].card_id == 13

    def test_scan_reorder_place_on_bottom(self):
        """Scan allows reordering and placing on bottom of draw deck."""
        deck = [
            make_card(card_id=10, denomination=1, power_text="Go"),
            make_card(card_id=11, denomination=10, power_text="Skip"),
            make_card(card_id=12, denomination=100, power_text="Reverse"),
            make_card(card_id=13, denomination=1000, power_text="Poison"),
        ]
        players = [
            make_player(player_id=1, draw_deck=deck, seat_position=1),
            make_player(player_id=2, seat_position=2),
        ]
        state = make_game_state(players=players)
        card = make_card(card_id=99, power_text="Scan")
        self.resolver.create_power_prompt(state, 0, card)
        self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        # Reorder: 11, 12, 10 and place on bottom
        events = self.resolver.handle_power_choice(
            state, 0, {"card_ids": [11, 12, 10], "placement": "bottom"}
        )

        assert isinstance(events, list)
        assert events[0]["type"] == "power_activated"
        assert events[0]["placement"] == "bottom"
        # Deck should now be: 13, 11, 12, 10
        assert state.players[0].draw_deck[0].card_id == 13
        assert state.players[0].draw_deck[1].card_id == 11
        assert state.players[0].draw_deck[2].card_id == 12
        assert state.players[0].draw_deck[3].card_id == 10

    def test_scan_fewer_than_3_cards_in_deck(self):
        """Scan works with fewer than 3 cards in draw deck."""
        deck = [
            make_card(card_id=10, denomination=1, power_text="Go"),
            make_card(card_id=11, denomination=10, power_text="Skip"),
        ]
        players = [
            make_player(player_id=1, draw_deck=deck, seat_position=1),
            make_player(player_id=2, seat_position=2),
        ]
        state = make_game_state(players=players)
        card = make_card(card_id=99, power_text="Scan")
        self.resolver.create_power_prompt(state, 0, card)

        events = self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        assert isinstance(events, list)
        assert len(events[0]["revealed_cards"]) == 2

    def test_scan_invalid_card_ids(self):
        """Scan rejects invalid card IDs."""
        deck = [
            make_card(card_id=10, denomination=1, power_text="Go"),
            make_card(card_id=11, denomination=10, power_text="Skip"),
            make_card(card_id=12, denomination=100, power_text="Reverse"),
        ]
        players = [
            make_player(player_id=1, draw_deck=deck, seat_position=1),
            make_player(player_id=2, seat_position=2),
        ]
        state = make_game_state(players=players)
        card = make_card(card_id=99, power_text="Scan")
        self.resolver.create_power_prompt(state, 0, card)
        self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        # Try with wrong card IDs
        result = self.resolver.handle_power_choice(
            state, 0, {"card_ids": [10, 11, 99], "placement": "top"}
        )

        assert isinstance(result, tuple)
        assert result[0] == "invalid_card_ids"


# --- Tests for Utilize Power ---


class TestUtilizePower:
    """Tests for the Utilize power (Requirement 14.7)."""

    def setup_method(self):
        self.resolver = PowerResolver()

    def test_utilize_in_activatable_powers(self):
        """Utilize is registered as an activatable power."""
        assert "utilize" in ACTIVATABLE_POWERS

    def test_utilize_in_powers_needing_target(self):
        """Utilize requires a target player."""
        assert "utilize" in POWERS_NEEDING_TARGET

    def test_utilize_moves_random_card_to_target_play_pile(self):
        """Utilize moves a random card from target's hand to their play pile."""
        target_hand = [
            make_card(card_id=50, denomination=100, power_text="Go"),
            make_card(card_id=51, denomination=1000, power_text="Skip"),
            make_card(card_id=52, denomination=10, power_text="Reverse"),
        ]
        players = [
            make_player(player_id=1, seat_position=1),
            make_player(player_id=2, hand=target_hand, seat_position=2),
        ]
        state = make_game_state(players=players)
        card = make_card(card_id=99, power_text="Utilize")
        self.resolver.create_power_prompt(state, 0, card)
        self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        events = self.resolver.handle_power_choice(
            state, 0, {"target_player_index": 1}
        )

        assert isinstance(events, list)
        assert events[0]["type"] == "power_activated"
        assert events[0]["power_name"] == "utilize"
        # Target should have lost one card from hand
        assert len(state.players[1].hand) == 2
        # Target should have gained one card in play pile
        assert len(state.players[1].play_pile) == 1
        # Active player should have scored
        utilized_denom = events[0]["utilized_card_denomination"]
        assert state.players[0].cumulative_score == utilized_denom

    def test_utilize_target_must_have_at_least_2_cards(self):
        """Utilize target must have at least 2 cards in hand."""
        target_hand = [make_card(card_id=50, denomination=100)]
        players = [
            make_player(player_id=1, seat_position=1),
            make_player(player_id=2, hand=target_hand, seat_position=2),
        ]
        state = make_game_state(players=players)
        card = make_card(card_id=99, power_text="Utilize")
        self.resolver.create_power_prompt(state, 0, card)
        self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        result = self.resolver.handle_power_choice(
            state, 0, {"target_player_index": 1}
        )

        assert isinstance(result, tuple)
        assert result[0] == "invalid_target"

    def test_utilize_cannot_target_self(self):
        """Utilize cannot target yourself."""
        players = [
            make_player(
                player_id=1,
                hand=[make_card(card_id=i) for i in range(1, 5)],
                seat_position=1,
            ),
            make_player(player_id=2, seat_position=2),
        ]
        state = make_game_state(players=players)
        card = make_card(card_id=99, power_text="Utilize")
        self.resolver.create_power_prompt(state, 0, card)
        self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        result = self.resolver.handle_power_choice(
            state, 0, {"target_player_index": 0}
        )

        assert isinstance(result, tuple)
        assert result[0] == "invalid_target"

    def test_utilize_scores_denomination_for_active_player(self):
        """Utilize scores the utilized card's denomination for the active player."""
        # Use a fixed seed to make the random selection predictable
        import random
        random.seed(42)

        target_hand = [
            make_card(card_id=50, denomination=100, power_text="Go"),
            make_card(card_id=51, denomination=1000, power_text="Skip"),
        ]
        players = [
            make_player(player_id=1, cumulative_score=0, seat_position=1),
            make_player(player_id=2, hand=target_hand, seat_position=2),
        ]
        state = make_game_state(players=players)
        card = make_card(card_id=99, power_text="Utilize")
        self.resolver.create_power_prompt(state, 0, card)
        self.resolver.handle_power_choice(state, 0, {"choice": "activate"})

        events = self.resolver.handle_power_choice(
            state, 0, {"target_player_index": 1}
        )

        assert isinstance(events, list)
        # Active player's score should equal the utilized card's denomination
        utilized_denom = events[0]["utilized_card_denomination"]
        assert state.players[0].cumulative_score == utilized_denom

    def test_utilize_decline(self):
        """Player can decline the Utilize power."""
        target_hand = [
            make_card(card_id=50, denomination=100),
            make_card(card_id=51, denomination=1000),
        ]
        players = [
            make_player(player_id=1, seat_position=1),
            make_player(player_id=2, hand=target_hand, seat_position=2),
        ]
        state = make_game_state(players=players)
        card = make_card(card_id=99, power_text="Utilize")
        self.resolver.create_power_prompt(state, 0, card)

        events = self.resolver.handle_power_choice(state, 0, {"choice": "decline"})

        assert isinstance(events, list)
        assert events[0]["type"] == "power_declined"
        # Target's hand unchanged
        assert len(state.players[1].hand) == 2
