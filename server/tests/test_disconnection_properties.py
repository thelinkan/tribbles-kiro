"""Property-based tests for disconnection and reconnection management.

Uses Hypothesis to verify that disconnection detection, grace period handling,
AI_Substitute activation, reconnection state sync, and game-end-while-disconnected
all behave correctly across a wide range of inputs.

**Validates: Requirements 21.1, 21.3, 21.4, 21.5, 21.6, 21.7, 21.8**
"""

import sys
import os

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from game.disconnection import DisconnectionManager
from models import CardInstance, GameState, PlayerState


DENOMINATIONS = [1, 10, 100, 1000, 10000, 100000]
POWERS = ["Go", "Skip", "Poison", "Rescue", "Reverse", "Discard"]


# --- Strategies ---


@st.composite
def card_strategy(draw, card_id=None):
    """Generate a random CardInstance."""
    cid = card_id if card_id is not None else draw(st.integers(min_value=1, max_value=100000))
    denom = draw(st.sampled_from(DENOMINATIONS))
    pwr = draw(st.sampled_from(POWERS))
    return CardInstance(
        card_id=cid,
        card_name=f"Tribble_{cid}",
        denomination=denom,
        power_text=pwr,
        expansion_id=1,
    )


@st.composite
def card_list_strategy(draw, min_size=1, max_size=10, id_offset=0):
    """Generate a list of cards with unique card_ids."""
    size = draw(st.integers(min_value=min_size, max_value=max_size))
    cards = []
    for i in range(size):
        card = draw(card_strategy(card_id=id_offset + i + 1))
        cards.append(card)
    return cards


@st.composite
def player_state_strategy(draw, player_id=None, seat_position=None):
    """Generate a random PlayerState with hand, draw deck, play pile, and discard pile."""
    pid = player_id if player_id is not None else draw(st.integers(min_value=1, max_value=100))
    seat = seat_position if seat_position is not None else pid
    id_base = pid * 1000

    hand = draw(card_list_strategy(min_size=1, max_size=7, id_offset=id_base))
    draw_deck = draw(card_list_strategy(min_size=1, max_size=15, id_offset=id_base + 100))
    play_pile = draw(card_list_strategy(min_size=0, max_size=8, id_offset=id_base + 200))
    discard_pile = draw(card_list_strategy(min_size=0, max_size=5, id_offset=id_base + 300))
    score = draw(st.integers(min_value=0, max_value=100000))

    return PlayerState(
        player_id=pid,
        username=f"Player_{pid}",
        is_computer=False,
        hand=hand,
        draw_deck=draw_deck,
        play_pile=play_pile,
        discard_pile=discard_pile,
        cumulative_score=score,
        is_decked=False,
        has_gone_out=False,
        seat_position=seat,
    )


@st.composite
def game_state_strategy(draw, player_count=None, game_status="active"):
    """Generate a random GameState with the given number of players."""
    n_players = player_count if player_count is not None else draw(
        st.integers(min_value=4, max_value=8)
    )
    players = [draw(player_state_strategy(player_id=i + 1, seat_position=i + 1)) for i in range(n_players)]
    timeout = draw(st.integers(min_value=5, max_value=120))
    direction = draw(st.sampled_from([1, -1]))
    sequence = draw(st.sampled_from(DENOMINATIONS))
    current_idx = draw(st.integers(min_value=0, max_value=n_players - 1))

    return GameState(
        game_id="prop-test-game",
        players=players,
        spectators=[],
        current_player_index=current_idx,
        direction=direction,
        current_sequence=sequence,
        round_number=draw(st.integers(min_value=1, max_value=5)),
        game_status=game_status,
        reconnection_timeout=timeout,
    )


@st.composite
def disconnection_time_strategy(draw):
    """Generate a disconnection timestamp and a current time within grace period."""
    disconnect_time = draw(st.floats(min_value=1000.0, max_value=100000.0))
    return disconnect_time


# --- Property 66: Disconnection marks player and starts grace period ---


class TestProperty66DisconnectionMarksPlayerAndStartsGracePeriod:
    """Property 66: Disconnection marks player and starts grace period.

    For any player who disconnects, they should be marked as disconnected with
    a timestamp, and the grace period should begin.

    **Validates: Requirements 21.1**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_player_marked_disconnected_with_timestamp(self, data):
        """For any player who disconnects, is_disconnected=True and disconnected_at is set."""
        state = data.draw(game_state_strategy())
        player_idx = data.draw(st.integers(min_value=0, max_value=len(state.players) - 1))
        player_id = state.players[player_idx].player_id
        disconnect_time = data.draw(st.floats(min_value=1000.0, max_value=100000.0))

        manager = DisconnectionManager()
        result = manager.mark_disconnected(state, player_id=player_id, current_time=disconnect_time)

        assert result.is_disconnected is True
        assert result.disconnected_at == disconnect_time
        assert result.player_id == player_id

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_grace_period_begins_on_disconnect(self, data):
        """For any player who disconnects, they should be in the grace period immediately."""
        state = data.draw(game_state_strategy())
        player_idx = data.draw(st.integers(min_value=0, max_value=len(state.players) - 1))
        player_id = state.players[player_idx].player_id
        disconnect_time = data.draw(st.floats(min_value=1000.0, max_value=100000.0))

        manager = DisconnectionManager()
        manager.mark_disconnected(state, player_id=player_id, current_time=disconnect_time)

        assert manager.is_in_grace_period(state, player_id=player_id, current_time=disconnect_time) is True

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_ai_substitute_not_active_on_disconnect(self, data):
        """For any player who disconnects, AI_Substitute should not be active immediately."""
        state = data.draw(game_state_strategy())
        player_idx = data.draw(st.integers(min_value=0, max_value=len(state.players) - 1))
        player_id = state.players[player_idx].player_id
        disconnect_time = data.draw(st.floats(min_value=1000.0, max_value=100000.0))

        manager = DisconnectionManager()
        result = manager.mark_disconnected(state, player_id=player_id, current_time=disconnect_time)

        assert result.ai_substitute_active is False
        assert manager.is_ai_substitute_active(state, player_id=player_id) is False


# --- Property 67: Disconnected player's turn is skipped without decking ---


class TestProperty67DisconnectedPlayerTurnSkippedWithoutDecking:
    """Property 67: Disconnected player's turn is skipped without decking.

    For any disconnected player in the grace period whose turn comes up,
    their turn should be skipped without marking them as decked.

    **Validates: Requirements 21.3**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_should_skip_turn_during_grace_period(self, data):
        """For any disconnected player in grace period, should_skip_turn returns True."""
        state = data.draw(game_state_strategy())
        player_idx = data.draw(st.integers(min_value=0, max_value=len(state.players) - 1))
        player_id = state.players[player_idx].player_id
        disconnect_time = data.draw(st.floats(min_value=1000.0, max_value=50000.0))
        # Elapsed time within grace period
        elapsed = data.draw(st.floats(
            min_value=0.0,
            max_value=float(state.reconnection_timeout) - 0.01,
        ))
        current_time = disconnect_time + elapsed

        manager = DisconnectionManager()
        manager.mark_disconnected(state, player_id=player_id, current_time=disconnect_time)

        assert manager.should_skip_turn(state, player_id=player_id, current_time=current_time) is True

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_player_not_decked_when_turn_skipped(self, data):
        """For any disconnected player whose turn is skipped, is_decked remains False."""
        state = data.draw(game_state_strategy())
        player_idx = data.draw(st.integers(min_value=0, max_value=len(state.players) - 1))
        player_id = state.players[player_idx].player_id
        disconnect_time = data.draw(st.floats(min_value=1000.0, max_value=50000.0))
        elapsed = data.draw(st.floats(
            min_value=0.0,
            max_value=float(state.reconnection_timeout) - 0.01,
        ))
        current_time = disconnect_time + elapsed

        manager = DisconnectionManager()
        manager.mark_disconnected(state, player_id=player_id, current_time=disconnect_time)

        # Verify turn should be skipped
        assert manager.should_skip_turn(state, player_id=player_id, current_time=current_time) is True
        # Verify player is NOT decked
        assert state.players[player_idx].is_decked is False

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_connected_player_turn_not_skipped(self, data):
        """For any connected player, should_skip_turn returns False."""
        state = data.draw(game_state_strategy())
        player_idx = data.draw(st.integers(min_value=0, max_value=len(state.players) - 1))
        player_id = state.players[player_idx].player_id
        current_time = data.draw(st.floats(min_value=1000.0, max_value=100000.0))

        manager = DisconnectionManager()
        # Player is NOT disconnected

        assert manager.should_skip_turn(state, player_id=player_id, current_time=current_time) is False


# --- Property 68: AI_Substitute activation preserves player state ---


class TestProperty68AISubstituteActivationPreservesPlayerState:
    """Property 68: AI_Substitute activation preserves player state.

    For any disconnected player after timeout, AI_Substitute should be activated
    without modifying the player's hand, draw deck, play pile, or discard pile.

    **Validates: Requirements 21.4, 21.5**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_ai_activated_after_timeout(self, data):
        """For any disconnected player after timeout, AI_Substitute becomes active."""
        state = data.draw(game_state_strategy())
        player_idx = data.draw(st.integers(min_value=0, max_value=len(state.players) - 1))
        player_id = state.players[player_idx].player_id
        disconnect_time = data.draw(st.floats(min_value=1000.0, max_value=50000.0))
        # Time after timeout
        extra = data.draw(st.floats(min_value=0.0, max_value=100.0))
        current_time = disconnect_time + float(state.reconnection_timeout) + extra

        manager = DisconnectionManager()
        manager.mark_disconnected(state, player_id=player_id, current_time=disconnect_time)
        result = manager.check_timeout(state, player_id=player_id, current_time=current_time)

        assert result is True
        assert manager.is_ai_substitute_active(state, player_id=player_id) is True

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_player_hand_unchanged_after_ai_activation(self, data):
        """For any disconnected player, hand is unchanged when AI_Substitute activates."""
        state = data.draw(game_state_strategy())
        player_idx = data.draw(st.integers(min_value=0, max_value=len(state.players) - 1))
        player_id = state.players[player_idx].player_id
        disconnect_time = data.draw(st.floats(min_value=1000.0, max_value=50000.0))
        current_time = disconnect_time + float(state.reconnection_timeout)

        # Record state before
        player = state.players[player_idx]
        hand_before = list(player.hand)
        draw_deck_before = list(player.draw_deck)
        play_pile_before = list(player.play_pile)
        discard_pile_before = list(player.discard_pile)

        manager = DisconnectionManager()
        manager.mark_disconnected(state, player_id=player_id, current_time=disconnect_time)
        manager.check_timeout(state, player_id=player_id, current_time=current_time)

        # Verify AI is active
        assert manager.is_ai_substitute_active(state, player_id=player_id) is True
        # Verify player state is unchanged
        assert player.hand == hand_before
        assert player.draw_deck == draw_deck_before
        assert player.play_pile == play_pile_before
        assert player.discard_pile == discard_pile_before

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_ai_not_activated_before_timeout(self, data):
        """For any disconnected player before timeout, AI_Substitute is not active."""
        state = data.draw(game_state_strategy())
        player_idx = data.draw(st.integers(min_value=0, max_value=len(state.players) - 1))
        player_id = state.players[player_idx].player_id
        disconnect_time = data.draw(st.floats(min_value=1000.0, max_value=50000.0))
        # Time before timeout
        elapsed = data.draw(st.floats(
            min_value=0.0,
            max_value=float(state.reconnection_timeout) - 0.01,
        ))
        current_time = disconnect_time + elapsed

        manager = DisconnectionManager()
        manager.mark_disconnected(state, player_id=player_id, current_time=disconnect_time)
        result = manager.check_timeout(state, player_id=player_id, current_time=current_time)

        assert result is False
        assert manager.is_ai_substitute_active(state, player_id=player_id) is False


# --- Property 69: Reconnection restores player control with full state sync ---


class TestProperty69ReconnectionRestoresPlayerControl:
    """Property 69: Reconnection restores player control with full state sync.

    For any reconnecting player, AI_Substitute should be deactivated, and the
    reconnect state should contain all required fields.

    **Validates: Requirements 21.6, 21.7**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_ai_substitute_deactivated_on_reconnect(self, data):
        """For any reconnecting player, AI_Substitute should be deactivated."""
        state = data.draw(game_state_strategy())
        player_idx = data.draw(st.integers(min_value=0, max_value=len(state.players) - 1))
        player_id = state.players[player_idx].player_id
        disconnect_time = data.draw(st.floats(min_value=1000.0, max_value=50000.0))
        current_time = disconnect_time + float(state.reconnection_timeout)

        manager = DisconnectionManager()
        manager.mark_disconnected(state, player_id=player_id, current_time=disconnect_time)
        manager.check_timeout(state, player_id=player_id, current_time=current_time)

        # Verify AI was active
        assert manager.is_ai_substitute_active(state, player_id=player_id) is True

        # Reconnect
        result = manager.mark_reconnected(state, player_id=player_id)

        assert result.ai_substitute_active is False
        assert result.is_disconnected is False
        assert manager.is_ai_substitute_active(state, player_id=player_id) is False

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_reconnect_state_contains_all_required_fields(self, data):
        """For any reconnecting player, reconnect state contains all required fields."""
        state = data.draw(game_state_strategy())
        player_idx = data.draw(st.integers(min_value=0, max_value=len(state.players) - 1))
        player_id = state.players[player_idx].player_id

        manager = DisconnectionManager()
        payload = manager.get_reconnect_state(state, player_id=player_id)

        # Verify all required fields are present
        assert "hand" in payload
        assert "play_pile" in payload
        assert "draw_deck_count" in payload
        assert "discard_pile" in payload
        assert "scores" in payload
        assert "current_sequence" in payload
        assert "direction" in payload
        assert "active_player_id" in payload
        assert "round_number" in payload
        assert "game_status" in payload

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_reconnect_state_hand_matches_player_hand(self, data):
        """For any reconnecting player, reconnect state hand matches actual hand."""
        state = data.draw(game_state_strategy())
        player_idx = data.draw(st.integers(min_value=0, max_value=len(state.players) - 1))
        player_id = state.players[player_idx].player_id

        manager = DisconnectionManager()
        payload = manager.get_reconnect_state(state, player_id=player_id)

        assert len(payload["hand"]) == len(state.players[player_idx].hand)

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_reconnect_state_scores_for_all_players(self, data):
        """For any reconnecting player, reconnect state includes scores for all players."""
        state = data.draw(game_state_strategy())
        player_idx = data.draw(st.integers(min_value=0, max_value=len(state.players) - 1))
        player_id = state.players[player_idx].player_id

        manager = DisconnectionManager()
        payload = manager.get_reconnect_state(state, player_id=player_id)

        assert len(payload["scores"]) == len(state.players)


# --- Property 70: Game ending with disconnected player records score in results ---


class TestProperty70GameEndingWithDisconnectedPlayerRecordsScore:
    """Property 70: Game ending with disconnected player records score in results.

    For any game that ends while a player is disconnected, the final results
    should include that player's score.

    **Validates: Requirements 21.8**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_completed_game_includes_disconnected_player_score(self, data):
        """For any completed game with a disconnected player, results include their score."""
        state = data.draw(game_state_strategy(game_status="completed"))
        player_idx = data.draw(st.integers(min_value=0, max_value=len(state.players) - 1))
        player_id = state.players[player_idx].player_id
        expected_score = state.players[player_idx].cumulative_score

        manager = DisconnectionManager()
        manager.mark_disconnected(state, player_id=player_id, current_time=1000.0)

        result = manager.handle_game_ended_while_disconnected(state, player_id=player_id)

        assert result is not None
        assert result["type"] == "game_end"
        assert result["payload"]["player_score"] == expected_score

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_completed_game_includes_all_player_scores(self, data):
        """For any completed game, final_scores includes entries for all players."""
        state = data.draw(game_state_strategy(game_status="completed"))
        player_idx = data.draw(st.integers(min_value=0, max_value=len(state.players) - 1))
        player_id = state.players[player_idx].player_id

        manager = DisconnectionManager()
        result = manager.handle_game_ended_while_disconnected(state, player_id=player_id)

        assert result is not None
        assert len(result["payload"]["final_scores"]) == len(state.players)

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_active_game_returns_none(self, data):
        """For any active game, handle_game_ended_while_disconnected returns None."""
        state = data.draw(game_state_strategy(game_status="active"))
        player_idx = data.draw(st.integers(min_value=0, max_value=len(state.players) - 1))
        player_id = state.players[player_idx].player_id

        manager = DisconnectionManager()
        result = manager.handle_game_ended_while_disconnected(state, player_id=player_id)

        assert result is None

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_completed_game_has_winner(self, data):
        """For any completed game, the result includes a winner field."""
        state = data.draw(game_state_strategy(game_status="completed"))
        player_idx = data.draw(st.integers(min_value=0, max_value=len(state.players) - 1))
        player_id = state.players[player_idx].player_id

        manager = DisconnectionManager()
        result = manager.handle_game_ended_while_disconnected(state, player_id=player_id)

        assert result is not None
        assert "winner" in result["payload"]
        assert result["payload"]["game_status"] == "completed"
