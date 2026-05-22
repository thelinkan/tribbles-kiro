"""Tests for the DisconnectionManager — player disconnection and reconnection.

Tests cover disconnection and reconnection requirements:
- 21.1: Detect disconnection, mark with timestamp
- 21.2: Configurable timeout (default 30s)
- 21.3: During grace period, skip disconnected player's turn without decking
- 21.4: After timeout, activate AI_Substitute using AIController
- 21.5: AI_Substitute operates on player's existing state
- 21.6: On reconnect, remove AI_Substitute, restore player control
- 21.7: Send reconnect_state_sync with full game state
- 21.8: Handle game ending while disconnected
"""

import sys
import os

import pytest

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from game.disconnection import DisconnectionManager
from models import CardInstance, GameState, PlayerState


def make_card(card_id: int, denomination: int = 1, power: str = "Bonus") -> CardInstance:
    """Helper to create a CardInstance for testing."""
    return CardInstance(
        card_id=card_id,
        card_name=f"Tribble_{card_id}",
        denomination=denomination,
        power_text=power,
        expansion_id=1,
    )


def make_player(player_id: int, username: str = "", hand_size: int = 7) -> PlayerState:
    """Helper to create a PlayerState for testing."""
    if not username:
        username = f"Player_{player_id}"
    hand = [make_card(i + player_id * 100, denomination=(i % 6 + 1) * 10) for i in range(hand_size)]
    draw_deck = [make_card(i + player_id * 100 + 50) for i in range(10)]
    play_pile = [make_card(i + player_id * 100 + 70, denomination=100) for i in range(3)]
    discard_pile = [make_card(i + player_id * 100 + 80, denomination=1000) for i in range(2)]
    return PlayerState(
        player_id=player_id,
        username=username,
        is_computer=False,
        hand=hand,
        draw_deck=draw_deck,
        play_pile=play_pile,
        discard_pile=discard_pile,
        cumulative_score=5000,
        is_decked=False,
        has_gone_out=False,
        seat_position=player_id,
    )


def make_game_state(
    player_count: int = 4,
    game_id: str = "test-game-1",
    reconnection_timeout: int = 30,
) -> GameState:
    """Helper to create a GameState for testing."""
    players = [make_player(i + 1) for i in range(player_count)]
    return GameState(
        game_id=game_id,
        players=players,
        current_player_index=0,
        direction=1,
        current_sequence=100,
        round_number=2,
        game_status="active",
        reconnection_timeout=reconnection_timeout,
    )


class TestMarkDisconnected:
    """Tests for DisconnectionManager.mark_disconnected."""

    def test_marks_player_as_disconnected(self):
        """Marking a player as disconnected sets is_disconnected=True."""
        manager = DisconnectionManager()
        game_state = make_game_state()

        result = manager.mark_disconnected(game_state, player_id=2, current_time=1000.0)

        assert result.is_disconnected is True
        assert result.player_id == 2

    def test_records_disconnection_timestamp(self):
        """Marking disconnected records the server timestamp. (Req 21.1)"""
        manager = DisconnectionManager()
        game_state = make_game_state()

        result = manager.mark_disconnected(game_state, player_id=3, current_time=1500.5)

        assert result.disconnected_at == 1500.5

    def test_ai_substitute_not_active_initially(self):
        """AI_Substitute should not be active immediately on disconnect."""
        manager = DisconnectionManager()
        game_state = make_game_state()

        result = manager.mark_disconnected(game_state, player_id=1, current_time=1000.0)

        assert result.ai_substitute_active is False

    def test_is_disconnected_returns_true_after_marking(self):
        """is_disconnected helper returns True after marking."""
        manager = DisconnectionManager()
        game_state = make_game_state()

        manager.mark_disconnected(game_state, player_id=2, current_time=1000.0)

        assert manager.is_disconnected(game_state, player_id=2) is True

    def test_is_disconnected_returns_false_for_connected_player(self):
        """is_disconnected returns False for a player not marked disconnected."""
        manager = DisconnectionManager()
        game_state = make_game_state()

        assert manager.is_disconnected(game_state, player_id=1) is False


class TestGracePeriod:
    """Tests for grace period logic (Req 21.3)."""

    def test_in_grace_period_immediately_after_disconnect(self):
        """Player is in grace period right after disconnection."""
        manager = DisconnectionManager()
        game_state = make_game_state(reconnection_timeout=30)

        manager.mark_disconnected(game_state, player_id=2, current_time=1000.0)

        assert manager.is_in_grace_period(game_state, player_id=2, current_time=1000.0) is True

    def test_in_grace_period_before_timeout(self):
        """Player is in grace period when elapsed time < timeout."""
        manager = DisconnectionManager()
        game_state = make_game_state(reconnection_timeout=30)

        manager.mark_disconnected(game_state, player_id=2, current_time=1000.0)

        assert manager.is_in_grace_period(game_state, player_id=2, current_time=1029.0) is True

    def test_not_in_grace_period_after_timeout(self):
        """Player is NOT in grace period after timeout elapses."""
        manager = DisconnectionManager()
        game_state = make_game_state(reconnection_timeout=30)

        manager.mark_disconnected(game_state, player_id=2, current_time=1000.0)
        # Check timeout first to activate AI
        manager.check_timeout(game_state, player_id=2, current_time=1030.0)

        assert manager.is_in_grace_period(game_state, player_id=2, current_time=1030.0) is False

    def test_not_in_grace_period_for_connected_player(self):
        """Connected player is not in grace period."""
        manager = DisconnectionManager()
        game_state = make_game_state()

        assert manager.is_in_grace_period(game_state, player_id=1, current_time=1000.0) is False

    def test_should_skip_turn_during_grace_period(self):
        """Turn should be skipped during grace period (Req 21.3)."""
        manager = DisconnectionManager()
        game_state = make_game_state(reconnection_timeout=30)

        manager.mark_disconnected(game_state, player_id=2, current_time=1000.0)

        assert manager.should_skip_turn(game_state, player_id=2, current_time=1015.0) is True

    def test_should_not_skip_turn_after_timeout(self):
        """Turn should NOT be skipped after timeout (AI takes over)."""
        manager = DisconnectionManager()
        game_state = make_game_state(reconnection_timeout=30)

        manager.mark_disconnected(game_state, player_id=2, current_time=1000.0)
        manager.check_timeout(game_state, player_id=2, current_time=1030.0)

        assert manager.should_skip_turn(game_state, player_id=2, current_time=1030.0) is False

    def test_should_not_skip_turn_for_connected_player(self):
        """Connected player's turn should not be skipped."""
        manager = DisconnectionManager()
        game_state = make_game_state()

        assert manager.should_skip_turn(game_state, player_id=1, current_time=1000.0) is False


class TestCheckTimeout:
    """Tests for timeout checking and AI_Substitute activation (Req 21.4)."""

    def test_timeout_not_reached(self):
        """check_timeout returns False when timeout not reached."""
        manager = DisconnectionManager()
        game_state = make_game_state(reconnection_timeout=30)

        manager.mark_disconnected(game_state, player_id=2, current_time=1000.0)

        assert manager.check_timeout(game_state, player_id=2, current_time=1020.0) is False

    def test_timeout_reached_activates_ai(self):
        """check_timeout returns True and activates AI when timeout reached."""
        manager = DisconnectionManager()
        game_state = make_game_state(reconnection_timeout=30)

        manager.mark_disconnected(game_state, player_id=2, current_time=1000.0)

        result = manager.check_timeout(game_state, player_id=2, current_time=1030.0)

        assert result is True
        assert manager.is_ai_substitute_active(game_state, player_id=2) is True

    def test_timeout_exact_boundary(self):
        """check_timeout activates AI at exactly the timeout boundary."""
        manager = DisconnectionManager()
        game_state = make_game_state(reconnection_timeout=30)

        manager.mark_disconnected(game_state, player_id=2, current_time=1000.0)

        result = manager.check_timeout(game_state, player_id=2, current_time=1030.0)

        assert result is True

    def test_timeout_already_activated(self):
        """check_timeout returns True if AI already activated."""
        manager = DisconnectionManager()
        game_state = make_game_state(reconnection_timeout=30)

        manager.mark_disconnected(game_state, player_id=2, current_time=1000.0)
        manager.check_timeout(game_state, player_id=2, current_time=1030.0)

        # Call again — should still return True
        assert manager.check_timeout(game_state, player_id=2, current_time=1050.0) is True

    def test_timeout_for_connected_player(self):
        """check_timeout returns False for a connected player."""
        manager = DisconnectionManager()
        game_state = make_game_state()

        assert manager.check_timeout(game_state, player_id=1, current_time=9999.0) is False

    def test_configurable_timeout_per_session(self):
        """Timeout is configurable per session (Req 21.2)."""
        manager = DisconnectionManager()
        game_state = make_game_state(reconnection_timeout=10)

        manager.mark_disconnected(game_state, player_id=2, current_time=1000.0)

        # At 9 seconds — not yet timed out
        assert manager.check_timeout(game_state, player_id=2, current_time=1009.0) is False
        # At 10 seconds — timed out
        assert manager.check_timeout(game_state, player_id=2, current_time=1010.0) is True

    def test_default_timeout_is_30_seconds(self):
        """Default reconnection_timeout is 30 seconds (Req 21.2)."""
        game_state = make_game_state()
        assert game_state.reconnection_timeout == 30


class TestMarkReconnected:
    """Tests for DisconnectionManager.mark_reconnected (Req 21.6)."""

    def test_clears_disconnection_state(self):
        """Reconnecting clears is_disconnected flag."""
        manager = DisconnectionManager()
        game_state = make_game_state()

        manager.mark_disconnected(game_state, player_id=2, current_time=1000.0)
        result = manager.mark_reconnected(game_state, player_id=2)

        assert result.is_disconnected is False

    def test_clears_timestamp(self):
        """Reconnecting clears the disconnected_at timestamp."""
        manager = DisconnectionManager()
        game_state = make_game_state()

        manager.mark_disconnected(game_state, player_id=2, current_time=1000.0)
        result = manager.mark_reconnected(game_state, player_id=2)

        assert result.disconnected_at is None

    def test_deactivates_ai_substitute(self):
        """Reconnecting deactivates AI_Substitute (Req 21.6)."""
        manager = DisconnectionManager()
        game_state = make_game_state(reconnection_timeout=30)

        manager.mark_disconnected(game_state, player_id=2, current_time=1000.0)
        manager.check_timeout(game_state, player_id=2, current_time=1030.0)

        # AI should be active
        assert manager.is_ai_substitute_active(game_state, player_id=2) is True

        # Reconnect
        result = manager.mark_reconnected(game_state, player_id=2)

        assert result.ai_substitute_active is False
        assert manager.is_ai_substitute_active(game_state, player_id=2) is False

    def test_reconnect_without_prior_disconnect(self):
        """Reconnecting a player that was never disconnected creates clean state."""
        manager = DisconnectionManager()
        game_state = make_game_state()

        result = manager.mark_reconnected(game_state, player_id=3)

        assert result.is_disconnected is False
        assert result.ai_substitute_active is False

    def test_is_disconnected_false_after_reconnect(self):
        """is_disconnected returns False after reconnection."""
        manager = DisconnectionManager()
        game_state = make_game_state()

        manager.mark_disconnected(game_state, player_id=2, current_time=1000.0)
        manager.mark_reconnected(game_state, player_id=2)

        assert manager.is_disconnected(game_state, player_id=2) is False


class TestGetReconnectState:
    """Tests for reconnect_state_sync payload building (Req 21.7)."""

    def test_contains_hand(self):
        """Reconnect state includes the player's hand."""
        manager = DisconnectionManager()
        game_state = make_game_state()

        payload = manager.get_reconnect_state(game_state, player_id=1)

        assert "hand" in payload
        assert len(payload["hand"]) == len(game_state.players[0].hand)

    def test_contains_play_pile(self):
        """Reconnect state includes the player's play pile."""
        manager = DisconnectionManager()
        game_state = make_game_state()

        payload = manager.get_reconnect_state(game_state, player_id=1)

        assert "play_pile" in payload
        assert len(payload["play_pile"]) == len(game_state.players[0].play_pile)

    def test_contains_draw_deck_count(self):
        """Reconnect state includes draw deck count (not contents)."""
        manager = DisconnectionManager()
        game_state = make_game_state()

        payload = manager.get_reconnect_state(game_state, player_id=1)

        assert "draw_deck_count" in payload
        assert payload["draw_deck_count"] == len(game_state.players[0].draw_deck)

    def test_contains_discard_pile(self):
        """Reconnect state includes the player's discard pile."""
        manager = DisconnectionManager()
        game_state = make_game_state()

        payload = manager.get_reconnect_state(game_state, player_id=1)

        assert "discard_pile" in payload
        assert len(payload["discard_pile"]) == len(game_state.players[0].discard_pile)

    def test_contains_scores_for_all_players(self):
        """Reconnect state includes scores for all players."""
        manager = DisconnectionManager()
        game_state = make_game_state(player_count=4)

        payload = manager.get_reconnect_state(game_state, player_id=1)

        assert "scores" in payload
        assert len(payload["scores"]) == 4

    def test_contains_current_sequence(self):
        """Reconnect state includes current sequence denomination."""
        manager = DisconnectionManager()
        game_state = make_game_state()

        payload = manager.get_reconnect_state(game_state, player_id=1)

        assert payload["current_sequence"] == 100

    def test_contains_direction(self):
        """Reconnect state includes play direction."""
        manager = DisconnectionManager()
        game_state = make_game_state()

        payload = manager.get_reconnect_state(game_state, player_id=1)

        assert payload["direction"] == 1

    def test_contains_active_player_id(self):
        """Reconnect state includes the active player's ID."""
        manager = DisconnectionManager()
        game_state = make_game_state()

        payload = manager.get_reconnect_state(game_state, player_id=2)

        assert payload["active_player_id"] == game_state.players[0].player_id

    def test_contains_round_number(self):
        """Reconnect state includes the current round number."""
        manager = DisconnectionManager()
        game_state = make_game_state()

        payload = manager.get_reconnect_state(game_state, player_id=1)

        assert payload["round_number"] == 2

    def test_contains_game_status(self):
        """Reconnect state includes the game status."""
        manager = DisconnectionManager()
        game_state = make_game_state()

        payload = manager.get_reconnect_state(game_state, player_id=1)

        assert payload["game_status"] == "active"

    def test_card_dict_format(self):
        """Cards in the payload are dicts with expected fields."""
        manager = DisconnectionManager()
        game_state = make_game_state()

        payload = manager.get_reconnect_state(game_state, player_id=1)

        card = payload["hand"][0]
        assert "card_id" in card
        assert "card_name" in card
        assert "denomination" in card
        assert "power_text" in card
        assert "expansion_id" in card

    def test_returns_empty_dict_for_unknown_player(self):
        """Returns empty dict if player_id not found in game state."""
        manager = DisconnectionManager()
        game_state = make_game_state()

        payload = manager.get_reconnect_state(game_state, player_id=999)

        assert payload == {}


class TestBuildNotifyMessages:
    """Tests for disconnect_notify and reconnect_notify message building."""

    def test_disconnect_notify_format(self):
        """disconnect_notify has correct type and payload fields."""
        manager = DisconnectionManager()
        game_state = make_game_state()

        msg = manager.build_disconnect_notify(game_state, player_id=2)

        assert msg["type"] == "disconnect_notify"
        assert msg["payload"]["player_id"] == 2
        assert msg["payload"]["username"] == "Player_2"
        assert msg["payload"]["grace_period_seconds"] == 30

    def test_reconnect_notify_format(self):
        """reconnect_notify has correct type and payload fields."""
        manager = DisconnectionManager()
        game_state = make_game_state()

        msg = manager.build_reconnect_notify(game_state, player_id=3)

        assert msg["type"] == "reconnect_notify"
        assert msg["payload"]["player_id"] == 3
        assert msg["payload"]["username"] == "Player_3"


class TestGameEndedWhileDisconnected:
    """Tests for handling game end during disconnection (Req 21.8)."""

    def test_returns_none_for_active_game(self):
        """Returns None if game is still active."""
        manager = DisconnectionManager()
        game_state = make_game_state()

        result = manager.handle_game_ended_while_disconnected(game_state, player_id=2)

        assert result is None

    def test_returns_game_end_for_completed_game(self):
        """Returns game_end payload if game is completed."""
        manager = DisconnectionManager()
        game_state = make_game_state()
        game_state.game_status = "completed"
        # Give player 1 the highest score
        game_state.players[0].cumulative_score = 50000

        result = manager.handle_game_ended_while_disconnected(game_state, player_id=2)

        assert result is not None
        assert result["type"] == "game_end"
        assert result["payload"]["game_status"] == "completed"
        assert result["payload"]["winner"] == "Player_1"

    def test_game_end_includes_final_scores(self):
        """Game end payload includes final scores for all players."""
        manager = DisconnectionManager()
        game_state = make_game_state(player_count=4)
        game_state.game_status = "completed"

        result = manager.handle_game_ended_while_disconnected(game_state, player_id=2)

        assert len(result["payload"]["final_scores"]) == 4

    def test_game_end_includes_player_score(self):
        """Game end payload includes the reconnecting player's score."""
        manager = DisconnectionManager()
        game_state = make_game_state()
        game_state.game_status = "completed"
        game_state.players[1].cumulative_score = 12345

        result = manager.handle_game_ended_while_disconnected(game_state, player_id=2)

        assert result["payload"]["player_score"] == 12345


class TestAISubstituteState:
    """Tests for AI_Substitute operating on player's existing state (Req 21.5)."""

    def test_ai_substitute_not_active_for_connected_player(self):
        """AI_Substitute is not active for a connected player."""
        manager = DisconnectionManager()
        game_state = make_game_state()

        assert manager.is_ai_substitute_active(game_state, player_id=1) is False

    def test_ai_substitute_active_after_timeout(self):
        """AI_Substitute becomes active after timeout."""
        manager = DisconnectionManager()
        game_state = make_game_state(reconnection_timeout=30)

        manager.mark_disconnected(game_state, player_id=2, current_time=1000.0)
        manager.check_timeout(game_state, player_id=2, current_time=1030.0)

        assert manager.is_ai_substitute_active(game_state, player_id=2) is True

    def test_ai_substitute_not_active_during_grace_period(self):
        """AI_Substitute is NOT active during grace period."""
        manager = DisconnectionManager()
        game_state = make_game_state(reconnection_timeout=30)

        manager.mark_disconnected(game_state, player_id=2, current_time=1000.0)

        assert manager.is_ai_substitute_active(game_state, player_id=2) is False

    def test_player_state_unchanged_when_ai_activates(self):
        """Player's hand/deck/piles are unchanged when AI_Substitute activates (Req 21.5)."""
        manager = DisconnectionManager()
        game_state = make_game_state(reconnection_timeout=30)

        # Record state before
        player = game_state.players[1]  # player_id=2
        hand_before = list(player.hand)
        deck_before = list(player.draw_deck)
        play_pile_before = list(player.play_pile)
        discard_before = list(player.discard_pile)

        manager.mark_disconnected(game_state, player_id=2, current_time=1000.0)
        manager.check_timeout(game_state, player_id=2, current_time=1030.0)

        # State should be unchanged
        assert player.hand == hand_before
        assert player.draw_deck == deck_before
        assert player.play_pile == play_pile_before
        assert player.discard_pile == discard_before
