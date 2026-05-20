"""Tests for the Game_Engine process_action method — core turn mechanics.

Tests cover turn mechanics requirements:
- 6.1: Player must play current sequence denomination or draw
- 6.2: Playing a valid card moves it to play pile and advances sequence
- 6.3: 100000 → 1 sequence wrap
- 6.4: Drawing moves top of draw deck to hand
- 6.5: Drawing matching card creates pending choice
- 6.6: Drawing non-matching card records pass after accept
- 6.7: Sequence break allows 1-denomination play
- 6.8: Empty draw deck causes decked state
- 6.9: last_played_denomination tracked independently
- Clone card playable when denomination matches last_played
"""

import sys
import os

import pytest

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from game.engine import GameEngine, GameSession, PlayerSetup
from models import CardInstance, GameState, PendingDraw, PlayerState


def make_card(card_id: int, denomination: int = 1, power: str = "Go") -> CardInstance:
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
    """Create a fresh GameEngine instance with a test game."""
    eng = GameEngine()
    return eng


def register_game(engine: GameEngine, state: GameState) -> None:
    """Register a game state in the engine's internal store."""
    engine._games[state.game_id] = state


class TestOnlyActivePlayerCanAct:
    """Tests that only the active player can perform actions."""

    def test_wrong_player_play_card_rejected(self, engine):
        """A non-active player cannot play a card."""
        state = make_game_state(current_player_index=0)
        register_game(engine, state)

        result = engine.process_action(
            "test-game", 2, {"type": "play_card", "card_id": 100}
        )
        assert isinstance(result, tuple)
        assert result[0] == "not_your_turn"

    def test_wrong_player_draw_card_rejected(self, engine):
        """A non-active player cannot draw a card."""
        state = make_game_state(current_player_index=0)
        register_game(engine, state)

        result = engine.process_action("test-game", 3, {"type": "draw_card"})
        assert isinstance(result, tuple)
        assert result[0] == "not_your_turn"

    def test_active_player_can_act(self, engine):
        """The active player can perform a valid action."""
        state = make_game_state(current_player_index=0, current_sequence=1)
        register_game(engine, state)

        # Player 1 has denomination-1 cards in hand
        result = engine.process_action(
            "test-game", 1, {"type": "play_card", "card_id": 0}
        )
        assert isinstance(result, list)


class TestPlayCardMovesToPileAndAdvancesSequence:
    """Tests for Requirement 6.2: Playing a valid card."""

    def test_card_moves_from_hand_to_play_pile(self, engine):
        """Playing a card removes it from hand and adds to play pile."""
        state = make_game_state(current_sequence=1)
        register_game(engine, state)

        player = state.players[0]
        card = player.hand[0]  # denomination 1
        hand_size_before = len(player.hand)

        result = engine.process_action(
            "test-game", 1, {"type": "play_card", "card_id": card.card_id}
        )

        assert isinstance(result, list)
        assert len(player.hand) == hand_size_before - 1
        assert card in player.play_pile
        assert card not in player.hand

    def test_sequence_advances_after_play(self, engine):
        """Sequence advances to next denomination after a valid play."""
        state = make_game_state(current_sequence=1)
        register_game(engine, state)

        card = state.players[0].hand[0]  # denomination 1
        engine.process_action(
            "test-game", 1, {"type": "play_card", "card_id": card.card_id}
        )

        assert state.current_sequence == 10

    def test_sequence_10_advances_to_100(self, engine):
        """Sequence 10 advances to 100."""
        state = make_game_state(current_sequence=10)
        # Give player a denomination-10 card
        state.players[0].hand.append(make_card(card_id=999, denomination=10))
        register_game(engine, state)

        engine.process_action(
            "test-game", 1, {"type": "play_card", "card_id": 999}
        )

        assert state.current_sequence == 100

    def test_card_played_event_emitted(self, engine):
        """A card_played event is returned."""
        state = make_game_state(current_sequence=1)
        register_game(engine, state)

        card = state.players[0].hand[0]
        result = engine.process_action(
            "test-game", 1, {"type": "play_card", "card_id": card.card_id}
        )

        assert isinstance(result, list)
        card_played_events = [e for e in result if e["type"] == "card_played"]
        assert len(card_played_events) == 1
        assert card_played_events[0]["card_id"] == card.card_id
        assert card_played_events[0]["denomination"] == 1


class TestSequenceWrap100000To1:
    """Tests for Requirement 6.3: 100000 → 1 wrap."""

    def test_playing_100000_resets_sequence_to_1(self, engine):
        """After playing a 100000 card, sequence resets to 1."""
        state = make_game_state(current_sequence=100000)
        state.players[0].hand.append(make_card(card_id=888, denomination=100000))
        register_game(engine, state)

        engine.process_action(
            "test-game", 1, {"type": "play_card", "card_id": 888}
        )

        assert state.current_sequence == 1

    def test_full_sequence_cycle(self, engine):
        """Verify the full cycle: 1→10→100→1000→10000→100000→1."""
        state = make_game_state(current_sequence=1)
        register_game(engine, state)

        denominations = [1, 10, 100, 1000, 10000, 100000]
        expected_next = [10, 100, 1000, 10000, 100000, 1]

        for denom, expected in zip(denominations, expected_next):
            state.current_sequence = denom
            state.current_player_index = 0
            card = make_card(card_id=700 + denom, denomination=denom)
            state.players[0].hand.append(card)

            engine.process_action(
                "test-game", 1, {"type": "play_card", "card_id": card.card_id}
            )

            assert state.current_sequence == expected


class TestDrawCard:
    """Tests for Requirement 6.4: Drawing moves top of deck to hand."""

    def test_draw_moves_top_card_to_hand(self, engine):
        """Drawing takes the top card from draw deck and adds to hand."""
        state = make_game_state(current_sequence=100)  # No 100-denom cards in hand
        register_game(engine, state)

        player = state.players[0]
        top_card = player.draw_deck[0]
        hand_size_before = len(player.hand)
        deck_size_before = len(player.draw_deck)

        result = engine.process_action("test-game", 1, {"type": "draw_card"})

        assert isinstance(result, list)
        assert top_card in player.hand
        assert len(player.hand) == hand_size_before + 1
        assert len(player.draw_deck) == deck_size_before - 1

    def test_draw_card_event_emitted(self, engine):
        """A card_drawn event is returned."""
        state = make_game_state(current_sequence=100)
        register_game(engine, state)

        top_card = state.players[0].draw_deck[0]
        result = engine.process_action("test-game", 1, {"type": "draw_card"})

        assert isinstance(result, list)
        drawn_events = [e for e in result if e["type"] == "card_drawn"]
        assert len(drawn_events) == 1
        assert drawn_events[0]["card_id"] == top_card.card_id


class TestDrawMatchingCardPendingChoice:
    """Tests for Requirement 6.5: Drawing matching card creates pending choice."""

    def test_matching_draw_creates_pending_choice(self, engine):
        """Drawing a card that matches the sequence creates a pending draw choice."""
        state = make_game_state(current_sequence=10)
        # Top of draw deck is denomination 10 (matches sequence)
        state.players[0].draw_deck[0] = make_card(card_id=555, denomination=10)
        register_game(engine, state)

        result = engine.process_action("test-game", 1, {"type": "draw_card"})

        assert isinstance(result, list)
        assert state.pending_draw is not None
        assert state.pending_draw.player_id == 1
        assert state.pending_draw.matches_sequence is True

        # Check for draw_choice_pending event
        choice_events = [e for e in result if e["type"] == "draw_choice_pending"]
        assert len(choice_events) == 1

    def test_player_can_play_matching_drawn_card(self, engine):
        """Player can play the matching drawn card immediately."""
        state = make_game_state(current_sequence=10)
        state.players[0].draw_deck[0] = make_card(card_id=555, denomination=10)
        register_game(engine, state)

        # Draw the card
        engine.process_action("test-game", 1, {"type": "draw_card"})

        # Play the drawn card
        result = engine.process_action(
            "test-game", 1, {"type": "play_card", "card_id": 555}
        )

        assert isinstance(result, list)
        assert state.pending_draw is None
        assert state.current_sequence == 100  # 10 → 100

    def test_player_can_keep_matching_drawn_card(self, engine):
        """Player can keep the matching drawn card (accept_draw = pass)."""
        state = make_game_state(current_sequence=10)
        state.players[0].draw_deck[0] = make_card(card_id=555, denomination=10)
        register_game(engine, state)

        # Draw the card
        engine.process_action("test-game", 1, {"type": "draw_card"})

        # Accept (keep in hand)
        result = engine.process_action("test-game", 1, {"type": "accept_draw"})

        assert isinstance(result, list)
        assert state.pending_draw is None
        assert state.sequence_broken is True
        # Card should still be in hand
        card_ids = [c.card_id for c in state.players[0].hand]
        assert 555 in card_ids


class TestDrawNonMatchingCardRecordsPass:
    """Tests for Requirement 6.6: Non-matching draw records pass after accept."""

    def test_non_matching_draw_creates_accept_pending(self, engine):
        """Drawing a non-matching card creates a pending accept state."""
        state = make_game_state(current_sequence=100)
        # Top of draw deck is denomination 10 (doesn't match 100)
        state.players[0].draw_deck[0] = make_card(card_id=444, denomination=10)
        register_game(engine, state)

        result = engine.process_action("test-game", 1, {"type": "draw_card"})

        assert isinstance(result, list)
        assert state.pending_draw is not None
        assert state.pending_draw.matches_sequence is False

        accept_events = [e for e in result if e["type"] == "draw_accept_pending"]
        assert len(accept_events) == 1

    def test_accept_non_matching_draw_records_pass(self, engine):
        """Accepting a non-matching draw records a pass and advances turn."""
        state = make_game_state(current_sequence=100)
        state.players[0].draw_deck[0] = make_card(card_id=444, denomination=10)
        register_game(engine, state)

        engine.process_action("test-game", 1, {"type": "draw_card"})
        result = engine.process_action("test-game", 1, {"type": "accept_draw"})

        assert isinstance(result, list)
        assert state.sequence_broken is True
        assert state.current_player_index == 1  # Turn advanced

    def test_cannot_play_non_matching_drawn_card(self, engine):
        """Player cannot play a non-matching drawn card."""
        state = make_game_state(current_sequence=100)
        state.players[0].draw_deck[0] = make_card(card_id=444, denomination=10)
        register_game(engine, state)

        engine.process_action("test-game", 1, {"type": "draw_card"})
        result = engine.process_action(
            "test-game", 1, {"type": "play_card", "card_id": 444}
        )

        assert isinstance(result, tuple)
        assert result[0] == "cannot_play_non_matching"


class TestSequenceBreakAllows1DenominationPlay:
    """Tests for Requirement 6.7: After a pass, next player can play 1-denom card."""

    def test_after_pass_next_player_can_play_1(self, engine):
        """After a pass, the next player can play a 1-denomination card."""
        state = make_game_state(current_sequence=100)
        state.sequence_broken = True
        state.current_player_index = 1  # Player 2's turn
        # Give player 2 a 1-denomination card
        state.players[1].hand.append(make_card(card_id=777, denomination=1))
        register_game(engine, state)

        result = engine.process_action(
            "test-game", 2, {"type": "play_card", "card_id": 777}
        )

        assert isinstance(result, list)
        # After playing a 1 during sequence break, sequence resets to 10
        assert state.current_sequence == 10

    def test_after_pass_next_player_can_still_play_sequence(self, engine):
        """After a pass, the next player can still play the current sequence."""
        state = make_game_state(current_sequence=100)
        state.sequence_broken = True
        state.current_player_index = 1
        state.players[1].hand.append(make_card(card_id=778, denomination=100))
        register_game(engine, state)

        result = engine.process_action(
            "test-game", 2, {"type": "play_card", "card_id": 778}
        )

        assert isinstance(result, list)
        assert state.current_sequence == 1000

    def test_sequence_broken_cleared_after_play(self, engine):
        """sequence_broken is cleared after a successful play."""
        state = make_game_state(current_sequence=100)
        state.sequence_broken = True
        state.current_player_index = 1
        state.players[1].hand.append(make_card(card_id=777, denomination=1))
        register_game(engine, state)

        engine.process_action(
            "test-game", 2, {"type": "play_card", "card_id": 777}
        )

        assert state.sequence_broken is False


class TestEmptyDrawDeckCausesDeckedState:
    """Tests for Requirement 6.8: Empty draw deck causes decked state."""

    def test_empty_deck_marks_player_decked(self, engine):
        """Drawing with empty deck marks the player as decked."""
        state = make_game_state(current_sequence=100)
        state.players[0].draw_deck = []  # Empty draw deck
        register_game(engine, state)

        result = engine.process_action("test-game", 1, {"type": "draw_card"})

        assert isinstance(result, list)
        assert state.players[0].is_decked is True

    def test_decked_player_hand_moved_to_discard(self, engine):
        """When decked, all hand cards move to discard pile."""
        state = make_game_state(current_sequence=100)
        state.players[0].draw_deck = []
        hand_cards = list(state.players[0].hand)
        register_game(engine, state)

        engine.process_action("test-game", 1, {"type": "draw_card"})

        assert state.players[0].hand == []
        for card in hand_cards:
            assert card in state.players[0].discard_pile

    def test_decked_event_emitted(self, engine):
        """A player_decked event is emitted."""
        state = make_game_state(current_sequence=100)
        state.players[0].draw_deck = []
        register_game(engine, state)

        result = engine.process_action("test-game", 1, {"type": "draw_card"})

        decked_events = [e for e in result if e["type"] == "player_decked"]
        assert len(decked_events) == 1
        assert decked_events[0]["player_id"] == 1

    def test_turn_advances_after_decked(self, engine):
        """Turn advances to next player after being decked."""
        state = make_game_state(current_sequence=100)
        state.players[0].draw_deck = []
        register_game(engine, state)

        engine.process_action("test-game", 1, {"type": "draw_card"})

        assert state.current_player_index == 1


class TestLastPlayedDenominationTrackedIndependently:
    """Tests for Requirement 6.9: last_played_denomination tracked separately."""

    def test_last_played_set_on_play(self, engine):
        """last_played_denomination is set to the played card's denomination."""
        state = make_game_state(current_sequence=1)
        register_game(engine, state)

        card = state.players[0].hand[0]  # denomination 1
        engine.process_action(
            "test-game", 1, {"type": "play_card", "card_id": card.card_id}
        )

        assert state.last_played_denomination == 1

    def test_last_played_independent_of_sequence(self, engine):
        """last_played_denomination differs from current_sequence after play."""
        state = make_game_state(current_sequence=1)
        register_game(engine, state)

        card = state.players[0].hand[0]  # denomination 1
        engine.process_action(
            "test-game", 1, {"type": "play_card", "card_id": card.card_id}
        )

        # Sequence advanced to 10, but last_played is still 1
        assert state.current_sequence == 10
        assert state.last_played_denomination == 1

    def test_last_played_updates_each_play(self, engine):
        """last_played_denomination updates with each card played."""
        state = make_game_state(current_sequence=1)
        register_game(engine, state)

        # Player 1 plays denomination 1
        card1 = state.players[0].hand[0]
        engine.process_action(
            "test-game", 1, {"type": "play_card", "card_id": card1.card_id}
        )
        assert state.last_played_denomination == 1

        # Player 2 plays denomination 10
        state.players[1].hand.append(make_card(card_id=900, denomination=10))
        engine.process_action(
            "test-game", 2, {"type": "play_card", "card_id": 900}
        )
        assert state.last_played_denomination == 10


class TestCloneCardPlayable:
    """Tests that Clone card is playable when denomination matches last_played."""

    def test_clone_playable_matching_last_played(self, engine):
        """Clone card can be played when its denomination matches last_played."""
        state = make_game_state(current_sequence=10)
        state.last_played_denomination = 1  # Last played was denomination 1
        # Give player a Clone card with denomination 1
        clone_card = make_card(card_id=600, denomination=1, power="Clone")
        state.players[0].hand.append(clone_card)
        register_game(engine, state)

        result = engine.process_action(
            "test-game", 1, {"type": "play_card", "card_id": 600}
        )

        assert isinstance(result, list)
        assert clone_card in state.players[0].play_pile

    def test_clone_not_playable_wrong_denomination(self, engine):
        """Clone card cannot be played when denomination doesn't match last_played."""
        state = make_game_state(current_sequence=100)
        state.last_played_denomination = 10  # Last played was denomination 10
        # Clone card with denomination 1 (doesn't match last_played=10 or sequence=100)
        clone_card = make_card(card_id=601, denomination=1, power="Clone")
        state.players[0].hand.append(clone_card)
        register_game(engine, state)

        result = engine.process_action(
            "test-game", 1, {"type": "play_card", "card_id": 601}
        )

        assert isinstance(result, tuple)
        assert result[0] == "invalid_play"

    def test_clone_not_playable_when_no_last_played(self, engine):
        """Clone card cannot be played when no card has been played yet."""
        state = make_game_state(current_sequence=10)
        state.last_played_denomination = None
        clone_card = make_card(card_id=602, denomination=10, power="Clone")
        state.players[0].hand.append(clone_card)
        register_game(engine, state)

        # The clone card has denomination 10 which matches sequence, so it's valid
        # as a normal play. Let's test with a non-matching denomination.
        clone_card2 = make_card(card_id=603, denomination=1, power="Clone")
        state.players[0].hand.append(clone_card2)

        result = engine.process_action(
            "test-game", 1, {"type": "play_card", "card_id": 603}
        )

        assert isinstance(result, tuple)
        assert result[0] == "invalid_play"

    def test_compound_clone_power_playable(self, engine):
        """A compound power card with Clone is playable matching last_played."""
        state = make_game_state(current_sequence=100)
        state.last_played_denomination = 1000
        # Clone & Reverse compound power card with denomination 1000
        compound_card = make_card(
            card_id=604, denomination=1000, power="Clone & Reverse"
        )
        state.players[0].hand.append(compound_card)
        register_game(engine, state)

        result = engine.process_action(
            "test-game", 1, {"type": "play_card", "card_id": 604}
        )

        assert isinstance(result, list)
        assert compound_card in state.players[0].play_pile


class TestTurnAdvancement:
    """Tests for turn advancement after actions."""

    def test_turn_advances_clockwise(self, engine):
        """Turn advances to next player in clockwise direction."""
        state = make_game_state(current_sequence=1, direction=1)
        register_game(engine, state)

        card = state.players[0].hand[0]
        engine.process_action(
            "test-game", 1, {"type": "play_card", "card_id": card.card_id}
        )

        assert state.current_player_index == 1

    def test_turn_advances_counterclockwise(self, engine):
        """Turn advances in counterclockwise direction."""
        state = make_game_state(current_sequence=1, direction=-1)
        state.current_player_index = 1
        register_game(engine, state)

        card = state.players[1].hand[0]
        engine.process_action(
            "test-game", 2, {"type": "play_card", "card_id": card.card_id}
        )

        # Player index 1 - 1 = 0
        assert state.current_player_index == 0

    def test_turn_wraps_around(self, engine):
        """Turn wraps from last player to first player."""
        state = make_game_state(current_sequence=1, num_players=4)
        state.current_player_index = 3  # Last player
        register_game(engine, state)

        card = state.players[3].hand[0]
        engine.process_action(
            "test-game", 4, {"type": "play_card", "card_id": card.card_id}
        )

        assert state.current_player_index == 0


class TestErrorCases:
    """Tests for error handling in process_action."""

    def test_game_not_found(self, engine):
        """Error when game doesn't exist."""
        result = engine.process_action(
            "nonexistent", 1, {"type": "play_card", "card_id": 1}
        )
        assert isinstance(result, tuple)
        assert result[0] == "game_not_found"

    def test_player_not_in_game(self, engine):
        """Error when player is not in the game."""
        state = make_game_state()
        register_game(engine, state)

        result = engine.process_action(
            "test-game", 99, {"type": "play_card", "card_id": 1}
        )
        assert isinstance(result, tuple)
        assert result[0] == "player_not_found"

    def test_card_not_in_hand(self, engine):
        """Error when card is not in player's hand."""
        state = make_game_state(current_sequence=1)
        register_game(engine, state)

        result = engine.process_action(
            "test-game", 1, {"type": "play_card", "card_id": 9999}
        )
        assert isinstance(result, tuple)
        assert result[0] == "card_not_in_hand"

    def test_invalid_denomination_rejected(self, engine):
        """Playing a card with wrong denomination is rejected."""
        state = make_game_state(current_sequence=100)
        # Player has denomination-1 cards, sequence expects 100
        register_game(engine, state)

        card = state.players[0].hand[0]  # denomination 1
        result = engine.process_action(
            "test-game", 1, {"type": "play_card", "card_id": card.card_id}
        )
        assert isinstance(result, tuple)
        assert result[0] == "invalid_play"

    def test_invalid_action_type(self, engine):
        """Unknown action type returns error."""
        state = make_game_state()
        register_game(engine, state)

        result = engine.process_action("test-game", 1, {"type": "unknown_action"})
        assert isinstance(result, tuple)
        assert result[0] == "invalid_action"

    def test_game_not_active(self, engine):
        """Error when game is not in active state."""
        state = make_game_state()
        state.game_status = "completed"
        register_game(engine, state)

        result = engine.process_action(
            "test-game", 1, {"type": "play_card", "card_id": 0}
        )
        assert isinstance(result, tuple)
        assert result[0] == "game_not_active"
