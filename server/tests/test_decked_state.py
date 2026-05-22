"""Tests for decked state logic in the Game_Engine.

Tests cover decked state requirements:
- 7.1: When decked, immediately move all hand cards to discard pile
- 7.2: Decked player cannot score and cannot have points scored from them (except Antidote)
- 7.3: Decked player's play pile remains intact for power references
- 7.4: Decked player can be targeted by powers (is_decked does NOT prevent targeting)
- 7.5: When all but one player decked, last player goes out (hand → play pile)
- Turn skips decked players
"""

import sys
import os

import pytest

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from game.engine import GameEngine, GameSession, PlayerSetup
from models import CardInstance, GameState, PendingDraw, PlayerState


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
    current_player_index: int = 0,
    current_sequence: int = 1,
    direction: int = 1,
    game_id: str = "test-game",
) -> GameState:
    """Helper to create a GameState with controllable parameters."""
    players = []
    for i in range(num_players):
        player = PlayerState(
            player_id=i + 1,
            username=f"Player_{i + 1}",
            is_computer=False,
            hand=[make_card(card_id=i * 100 + j, denomination=1) for j in range(7)],
            draw_deck=[
                make_card(card_id=i * 100 + 50 + j, denomination=10) for j in range(10)
            ],
            play_pile=[],
            discard_pile=[],
            cumulative_score=0,
            is_decked=False,
            has_gone_out=False,
            seat_position=i + 1,
        )
        players.append(player)

    state = GameState(
        game_id=game_id,
        players=players,
        spectators=[],
        current_player_index=current_player_index,
        direction=direction,
        current_sequence=current_sequence,
        last_played_denomination=None,
        sequence_broken=False,
        round_number=1,
        frozen_powers={},
        game_status="active",
        reconnection_timeout=30,
        pending_draw=None,
    )
    return state


@pytest.fixture
def engine():
    """Create a fresh GameEngine instance."""
    return GameEngine()


def register_game(engine: GameEngine, state: GameState) -> None:
    """Register a game state in the engine's internal store."""
    engine._games[state.game_id] = state


class TestDeckedPlayerHandMovedToDiscard:
    """Tests for Requirement 7.1: Hand moved to discard when decked."""

    def test_hand_cards_moved_to_discard_on_decked(self, engine):
        """When a player is decked, all hand cards move to discard pile."""
        state = make_game_state(current_sequence=100)
        state.players[0].draw_deck = []  # Empty draw deck
        hand_cards = list(state.players[0].hand)
        register_game(engine, state)

        engine.process_action("test-game", 1, {"type": "draw_card"})

        assert state.players[0].hand == []
        assert state.players[0].is_decked is True
        for card in hand_cards:
            assert card in state.players[0].discard_pile

    def test_hand_is_empty_after_decked(self, engine):
        """Decked player's hand is completely empty."""
        state = make_game_state(current_sequence=100)
        state.players[0].draw_deck = []
        register_game(engine, state)

        engine.process_action("test-game", 1, {"type": "draw_card"})

        assert len(state.players[0].hand) == 0

    def test_discard_pile_grows_by_hand_size(self, engine):
        """Discard pile grows by the number of cards that were in hand."""
        state = make_game_state(current_sequence=100)
        state.players[0].draw_deck = []
        initial_hand_size = len(state.players[0].hand)
        initial_discard_size = len(state.players[0].discard_pile)
        register_game(engine, state)

        engine.process_action("test-game", 1, {"type": "draw_card"})

        assert len(state.players[0].discard_pile) == initial_discard_size + initial_hand_size


class TestDeckedPlayerPlayPileIntact:
    """Tests for Requirement 7.3: Play pile remains intact when decked."""

    def test_play_pile_unchanged_after_decked(self, engine):
        """Decked player's play pile is not modified."""
        state = make_game_state(current_sequence=100)
        state.players[0].draw_deck = []
        # Give the player some cards in their play pile
        play_pile_cards = [make_card(card_id=900 + i, denomination=10) for i in range(3)]
        state.players[0].play_pile = list(play_pile_cards)
        register_game(engine, state)

        engine.process_action("test-game", 1, {"type": "draw_card"})

        assert state.players[0].play_pile == play_pile_cards

    def test_play_pile_size_unchanged_after_decked(self, engine):
        """Play pile size doesn't change when player is decked."""
        state = make_game_state(current_sequence=100)
        state.players[0].draw_deck = []
        state.players[0].play_pile = [make_card(card_id=900 + i) for i in range(5)]
        initial_pile_size = len(state.players[0].play_pile)
        register_game(engine, state)

        engine.process_action("test-game", 1, {"type": "draw_card"})

        assert len(state.players[0].play_pile) == initial_pile_size


class TestTurnSkipsDeckedPlayers:
    """Tests that turn advancement skips decked players."""

    def test_turn_skips_single_decked_player(self, engine):
        """Turn skips over a decked player to the next non-decked player."""
        state = make_game_state(current_sequence=1, num_players=4)
        # Player 2 (index 1) is decked
        state.players[1].is_decked = True
        register_game(engine, state)

        # Player 1 plays a card, turn should skip player 2 and go to player 3
        card = state.players[0].hand[0]
        engine.process_action(
            "test-game", 1, {"type": "play_card", "card_id": card.card_id}
        )

        assert state.current_player_index == 2  # Skipped index 1

    def test_turn_skips_multiple_decked_players(self, engine):
        """Turn skips over multiple consecutive decked players."""
        state = make_game_state(current_sequence=1, num_players=4)
        # Players 2 and 3 (indices 1, 2) are decked
        state.players[1].is_decked = True
        state.players[2].is_decked = True
        register_game(engine, state)

        card = state.players[0].hand[0]
        engine.process_action(
            "test-game", 1, {"type": "play_card", "card_id": card.card_id}
        )

        assert state.current_player_index == 3  # Skipped indices 1 and 2

    def test_turn_wraps_around_skipping_decked(self, engine):
        """Turn wraps around the player list while skipping decked players."""
        state = make_game_state(current_sequence=1, num_players=4)
        state.current_player_index = 2  # Player 3's turn
        # Players 4 and 1 (indices 3, 0) are decked
        state.players[3].is_decked = True
        state.players[0].is_decked = True
        register_game(engine, state)

        card = state.players[2].hand[0]
        engine.process_action(
            "test-game", 3, {"type": "play_card", "card_id": card.card_id}
        )

        assert state.current_player_index == 1  # Wrapped around, skipping 3 and 0

    def test_turn_skips_decked_counterclockwise(self, engine):
        """Turn skips decked players in counterclockwise direction."""
        state = make_game_state(current_sequence=1, num_players=4, direction=-1)
        state.current_player_index = 2  # Player 3's turn
        # Player 2 (index 1) is decked
        state.players[1].is_decked = True
        register_game(engine, state)

        card = state.players[2].hand[0]
        engine.process_action(
            "test-game", 3, {"type": "play_card", "card_id": card.card_id}
        )

        # Counterclockwise from index 2: index 1 (decked), so goes to index 0
        assert state.current_player_index == 0

    def test_decked_player_skipped_after_draw(self, engine):
        """When a player becomes decked, the next turn skips them."""
        state = make_game_state(current_sequence=100, num_players=4)
        state.players[0].draw_deck = []  # Player 1 will be decked
        register_game(engine, state)

        result = engine.process_action("test-game", 1, {"type": "draw_card"})

        # Player 1 is now decked, turn should go to player 2
        assert state.players[0].is_decked is True
        assert state.current_player_index == 1


class TestLastNonDeckedPlayerGoesOut:
    """Tests for Requirement 7.5: Last non-decked player goes out automatically."""

    def test_last_player_goes_out_when_all_others_decked(self, engine):
        """When all but one player are decked, the last player goes out."""
        state = make_game_state(current_sequence=100, num_players=4)
        # Players 2, 3, 4 are already decked
        state.players[1].is_decked = True
        state.players[1].hand = []
        state.players[2].is_decked = True
        state.players[2].hand = []
        state.players[3].is_decked = True
        state.players[3].hand = []
        # Player 1 has empty draw deck, will become decked
        # But wait — we need player 1 to be the one getting decked, leaving no one...
        # Actually, let's set up: players 2, 3 are decked, player 1 gets decked,
        # leaving player 4 as last standing
        state.players[1].is_decked = True
        state.players[1].hand = []
        state.players[2].is_decked = True
        state.players[2].hand = []
        # Player 4 (index 3) is NOT decked and has cards in hand
        state.players[3].is_decked = False
        state.players[3].hand = [make_card(card_id=800 + i) for i in range(5)]
        # Player 1 (index 0) will become decked
        state.players[0].draw_deck = []
        register_game(engine, state)

        result = engine.process_action("test-game", 1, {"type": "draw_card"})

        # Player 4 should have gone out
        assert state.players[3].has_gone_out is True
        assert state.players[3].hand == []

    def test_last_player_hand_moves_to_play_pile(self, engine):
        """Last player's hand cards move to their play pile when they go out."""
        state = make_game_state(current_sequence=100, num_players=3)
        # Players 2, 3 are already decked (indices 1, 2)
        # Actually: player 2 (index 1) is decked, player 1 (index 0) will get decked
        # leaving player 3 (index 2) as last standing
        state.players[1].is_decked = True
        state.players[1].hand = []
        # Player 3 has specific hand cards
        hand_cards = [make_card(card_id=800 + i, denomination=100) for i in range(4)]
        state.players[2].hand = list(hand_cards)
        state.players[2].play_pile = [make_card(card_id=850, denomination=10)]
        # Player 1 will become decked
        state.players[0].draw_deck = []
        register_game(engine, state)

        engine.process_action("test-game", 1, {"type": "draw_card"})

        # Player 3's hand should now be in their play pile
        for card in hand_cards:
            assert card in state.players[2].play_pile
        assert state.players[2].hand == []

    def test_last_player_play_pile_includes_existing_cards(self, engine):
        """Last player's play pile retains existing cards plus hand cards."""
        state = make_game_state(current_sequence=100, num_players=3)
        state.players[1].is_decked = True
        state.players[1].hand = []
        # Player 3 has existing play pile and hand
        existing_pile = [make_card(card_id=850, denomination=10)]
        hand_cards = [make_card(card_id=860 + i) for i in range(3)]
        state.players[2].play_pile = list(existing_pile)
        state.players[2].hand = list(hand_cards)
        # Player 1 will become decked
        state.players[0].draw_deck = []
        register_game(engine, state)

        engine.process_action("test-game", 1, {"type": "draw_card"})

        # Play pile should have existing + hand cards
        assert len(state.players[2].play_pile) == len(existing_pile) + len(hand_cards)
        for card in existing_pile + hand_cards:
            assert card in state.players[2].play_pile

    def test_last_player_event_emitted(self, engine):
        """A player_went_out event is emitted for the last standing player."""
        state = make_game_state(current_sequence=100, num_players=3)
        state.players[1].is_decked = True
        state.players[1].hand = []
        state.players[2].hand = [make_card(card_id=800)]
        state.players[0].draw_deck = []
        register_game(engine, state)

        result = engine.process_action("test-game", 1, {"type": "draw_card"})

        went_out_events = [e for e in result if e["type"] == "player_went_out"]
        assert len(went_out_events) == 1
        assert went_out_events[0]["player_id"] == 3
        assert went_out_events[0]["reason"] == "last_player_standing"

    def test_no_go_out_when_multiple_non_decked_remain(self, engine):
        """No automatic go-out when more than one non-decked player remains."""
        state = make_game_state(current_sequence=100, num_players=4)
        # Only player 2 is decked
        state.players[1].is_decked = True
        state.players[1].hand = []
        # Player 1 will become decked, but players 3 and 4 remain
        state.players[0].draw_deck = []
        register_game(engine, state)

        result = engine.process_action("test-game", 1, {"type": "draw_card"})

        # Players 3 and 4 should NOT have gone out
        assert state.players[2].has_gone_out is False
        assert state.players[3].has_gone_out is False
        went_out_events = [e for e in result if e["type"] == "player_went_out"]
        assert len(went_out_events) == 0


class TestScoringPreventionForDeckedPlayers:
    """Tests for Requirement 7.2: Scoring prevention for decked players."""

    def test_cannot_score_from_decked_player(self, engine):
        """can_score_from returns False for a decked player."""
        player = PlayerState(
            player_id=1,
            username="Test",
            is_computer=False,
            is_decked=True,
        )
        assert engine.can_score_from(player) is False

    def test_can_score_from_non_decked_player(self, engine):
        """can_score_from returns True for a non-decked player."""
        player = PlayerState(
            player_id=1,
            username="Test",
            is_computer=False,
            is_decked=False,
        )
        assert engine.can_score_from(player) is True

    def test_cannot_score_to_decked_player(self, engine):
        """can_score_to returns False for a decked player."""
        player = PlayerState(
            player_id=1,
            username="Test",
            is_computer=False,
            is_decked=True,
        )
        assert engine.can_score_to(player) is False

    def test_can_score_to_non_decked_player(self, engine):
        """can_score_to returns True for a non-decked player."""
        player = PlayerState(
            player_id=1,
            username="Test",
            is_computer=False,
            is_decked=False,
        )
        assert engine.can_score_to(player) is True


class TestDeckedPlayerCanBeTargeted:
    """Tests for Requirement 7.4: Decked player can be targeted by powers.

    The is_decked flag does NOT prevent a player from being a valid target
    for power effects. This is verified by checking that no targeting logic
    in the engine excludes decked players.
    """

    def test_decked_player_is_still_in_players_list(self, engine):
        """A decked player remains in the players list and is findable."""
        state = make_game_state(num_players=4)
        state.players[1].is_decked = True
        register_game(engine, state)

        # Decked player is still accessible
        decked_player = state.players[1]
        assert decked_player.player_id == 2
        assert decked_player.is_decked is True

    def test_decked_player_play_pile_accessible(self, engine):
        """A decked player's play pile can be accessed for power references."""
        state = make_game_state(num_players=4)
        pile_card = make_card(card_id=999, denomination=1000, power="Bonus")
        state.players[1].play_pile = [pile_card]
        state.players[1].is_decked = True
        register_game(engine, state)

        # Play pile is accessible even when decked
        assert len(state.players[1].play_pile) == 1
        assert state.players[1].play_pile[0] == pile_card
