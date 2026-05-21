"""Tests for the SpectatorManager — spectator state broadcasting and management.

Tests cover spectator requirements:
- 22.1: Spectator can watch active game (already in Lobby_Service)
- 22.2: Spectator receives only public state (no hand contents)
- 22.3: Spectator cannot perform game actions
- 22.5: Spectator leaving does not affect game state
- 22.6: Spectator count update sent to all players and spectators
- 22.7: Reject game actions from spectator player IDs
"""

import sys
import os

import pytest

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from game.spectator import SpectatorManager
from game.engine import GameEngine, GameSession, PlayerSetup
from models import CardInstance, GameState, PlayerState


def make_card(card_id: int, denomination: int = 1, power: str = "Go") -> CardInstance:
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
    spectators: list = None,
) -> GameState:
    """Helper to create a GameState for testing."""
    players = [make_player(i + 1) for i in range(player_count)]
    return GameState(
        game_id=game_id,
        players=players,
        spectators=spectators if spectators is not None else [],
        current_player_index=0,
        direction=1,
        current_sequence=100,
        round_number=2,
        game_status="active",
    )


class TestGetSpectatorVisibleState:
    """Tests for SpectatorManager.get_spectator_visible_state (Req 22.2, 22.3)."""

    def test_contains_play_piles_for_all_players(self):
        """Spectator state includes play piles for all players."""
        manager = SpectatorManager()
        game_state = make_game_state(player_count=4)

        result = manager.get_spectator_visible_state(game_state)

        assert "play_piles" in result
        assert len(result["play_piles"]) == 4

    def test_contains_discard_piles_for_all_players(self):
        """Spectator state includes discard piles for all players."""
        manager = SpectatorManager()
        game_state = make_game_state(player_count=4)

        result = manager.get_spectator_visible_state(game_state)

        assert "discard_piles" in result
        assert len(result["discard_piles"]) == 4

    def test_contains_draw_deck_counts_for_all_players(self):
        """Spectator state includes draw deck counts (not contents)."""
        manager = SpectatorManager()
        game_state = make_game_state(player_count=4)

        result = manager.get_spectator_visible_state(game_state)

        assert "draw_deck_counts" in result
        assert len(result["draw_deck_counts"]) == 4
        # Verify counts match actual deck sizes
        for player in game_state.players:
            assert result["draw_deck_counts"][player.player_id] == len(player.draw_deck)

    def test_contains_scores_for_all_players(self):
        """Spectator state includes scores for all players."""
        manager = SpectatorManager()
        game_state = make_game_state(player_count=4)

        result = manager.get_spectator_visible_state(game_state)

        assert "scores" in result
        assert len(result["scores"]) == 4

    def test_contains_current_sequence(self):
        """Spectator state includes current sequence denomination."""
        manager = SpectatorManager()
        game_state = make_game_state()

        result = manager.get_spectator_visible_state(game_state)

        assert result["current_sequence"] == 100

    def test_contains_direction(self):
        """Spectator state includes play direction."""
        manager = SpectatorManager()
        game_state = make_game_state()

        result = manager.get_spectator_visible_state(game_state)

        assert result["direction"] == 1

    def test_contains_active_player_id(self):
        """Spectator state includes the active player's ID."""
        manager = SpectatorManager()
        game_state = make_game_state()

        result = manager.get_spectator_visible_state(game_state)

        assert result["active_player_id"] == game_state.players[0].player_id

    def test_contains_round_number(self):
        """Spectator state includes the current round number."""
        manager = SpectatorManager()
        game_state = make_game_state()

        result = manager.get_spectator_visible_state(game_state)

        assert result["round_number"] == 2

    def test_contains_game_status(self):
        """Spectator state includes the game status."""
        manager = SpectatorManager()
        game_state = make_game_state()

        result = manager.get_spectator_visible_state(game_state)

        assert result["game_status"] == "active"

    def test_does_not_contain_hand_contents(self):
        """Spectator state does NOT include any player's hand contents (Req 22.3)."""
        manager = SpectatorManager()
        game_state = make_game_state(player_count=4)

        result = manager.get_spectator_visible_state(game_state)

        # The result should not have a "hands" key
        assert "hands" not in result
        assert "hand" not in result

    def test_play_pile_card_format(self):
        """Play pile cards are dicts with expected fields."""
        manager = SpectatorManager()
        game_state = make_game_state()

        result = manager.get_spectator_visible_state(game_state)

        pid = game_state.players[0].player_id
        card = result["play_piles"][pid][0]
        assert "card_id" in card
        assert "card_name" in card
        assert "denomination" in card
        assert "power_text" in card
        assert "expansion_id" in card

    def test_discard_pile_card_format(self):
        """Discard pile cards are dicts with expected fields."""
        manager = SpectatorManager()
        game_state = make_game_state()

        result = manager.get_spectator_visible_state(game_state)

        pid = game_state.players[0].player_id
        card = result["discard_piles"][pid][0]
        assert "card_id" in card
        assert "card_name" in card
        assert "denomination" in card
        assert "power_text" in card
        assert "expansion_id" in card

    def test_active_player_changes_with_index(self):
        """Active player ID reflects the current_player_index."""
        manager = SpectatorManager()
        game_state = make_game_state()
        game_state.current_player_index = 2

        result = manager.get_spectator_visible_state(game_state)

        assert result["active_player_id"] == game_state.players[2].player_id


class TestBuildSpectatorStateUpdate:
    """Tests for SpectatorManager.build_spectator_state_update (Req 22.2)."""

    def test_message_type(self):
        """Message has type 'spectator_state_update'."""
        manager = SpectatorManager()
        game_state = make_game_state()

        msg = manager.build_spectator_state_update(game_state)

        assert msg["type"] == "spectator_state_update"

    def test_payload_contains_public_state(self):
        """Payload contains all public state fields."""
        manager = SpectatorManager()
        game_state = make_game_state()

        msg = manager.build_spectator_state_update(game_state)

        payload = msg["payload"]
        assert "play_piles" in payload
        assert "discard_piles" in payload
        assert "draw_deck_counts" in payload
        assert "scores" in payload
        assert "current_sequence" in payload
        assert "direction" in payload
        assert "active_player_id" in payload
        assert "round_number" in payload
        assert "game_status" in payload

    def test_payload_does_not_contain_hands(self):
        """Payload does NOT contain hand contents."""
        manager = SpectatorManager()
        game_state = make_game_state()

        msg = manager.build_spectator_state_update(game_state)

        assert "hands" not in msg["payload"]
        assert "hand" not in msg["payload"]


class TestBuildSpectatorCountUpdate:
    """Tests for SpectatorManager.build_spectator_count_update (Req 22.6)."""

    def test_message_type(self):
        """Message has type 'spectator_count_update'."""
        manager = SpectatorManager()
        game_state = make_game_state(spectators=[10, 11, 12])

        msg = manager.build_spectator_count_update(game_state)

        assert msg["type"] == "spectator_count_update"

    def test_payload_contains_session_id(self):
        """Payload contains the session/game ID."""
        manager = SpectatorManager()
        game_state = make_game_state(game_id="my-game-42", spectators=[10])

        msg = manager.build_spectator_count_update(game_state)

        assert msg["payload"]["session_id"] == "my-game-42"

    def test_payload_contains_spectator_count(self):
        """Payload contains the correct spectator count."""
        manager = SpectatorManager()
        game_state = make_game_state(spectators=[10, 11, 12])

        msg = manager.build_spectator_count_update(game_state)

        assert msg["payload"]["spectator_count"] == 3

    def test_zero_spectators(self):
        """Spectator count is 0 when no spectators."""
        manager = SpectatorManager()
        game_state = make_game_state(spectators=[])

        msg = manager.build_spectator_count_update(game_state)

        assert msg["payload"]["spectator_count"] == 0


class TestLeaveSpectate:
    """Tests for SpectatorManager.leave_spectate (Req 22.5)."""

    def test_removes_spectator_from_list(self):
        """Leaving removes the spectator from the spectators list."""
        manager = SpectatorManager()
        game_state = make_game_state(spectators=[10, 11, 12])

        result = manager.leave_spectate(game_state, player_id=11)

        assert result is True
        assert 11 not in game_state.spectators

    def test_returns_false_if_not_spectating(self):
        """Returns False if the player is not in the spectators list."""
        manager = SpectatorManager()
        game_state = make_game_state(spectators=[10, 12])

        result = manager.leave_spectate(game_state, player_id=99)

        assert result is False

    def test_does_not_affect_players(self):
        """Leaving spectate does not affect the players list."""
        manager = SpectatorManager()
        game_state = make_game_state(player_count=4, spectators=[10])
        players_before = [p.player_id for p in game_state.players]

        manager.leave_spectate(game_state, player_id=10)

        players_after = [p.player_id for p in game_state.players]
        assert players_after == players_before

    def test_does_not_affect_game_status(self):
        """Leaving spectate does not change game status."""
        manager = SpectatorManager()
        game_state = make_game_state(spectators=[10])

        manager.leave_spectate(game_state, player_id=10)

        assert game_state.game_status == "active"

    def test_does_not_affect_current_player(self):
        """Leaving spectate does not change the current player index."""
        manager = SpectatorManager()
        game_state = make_game_state(spectators=[10])
        game_state.current_player_index = 2

        manager.leave_spectate(game_state, player_id=10)

        assert game_state.current_player_index == 2

    def test_does_not_affect_scores(self):
        """Leaving spectate does not change any player's score."""
        manager = SpectatorManager()
        game_state = make_game_state(spectators=[10])
        scores_before = [p.cumulative_score for p in game_state.players]

        manager.leave_spectate(game_state, player_id=10)

        scores_after = [p.cumulative_score for p in game_state.players]
        assert scores_after == scores_before

    def test_other_spectators_remain(self):
        """Leaving only removes the specified spectator, others remain."""
        manager = SpectatorManager()
        game_state = make_game_state(spectators=[10, 11, 12])

        manager.leave_spectate(game_state, player_id=11)

        assert game_state.spectators == [10, 12]


class TestIsSpectator:
    """Tests for SpectatorManager.is_spectator (Req 22.7)."""

    def test_returns_true_for_spectator(self):
        """Returns True for a player in the spectators list."""
        manager = SpectatorManager()
        game_state = make_game_state(spectators=[10, 11])

        assert manager.is_spectator(game_state, player_id=10) is True

    def test_returns_false_for_non_spectator(self):
        """Returns False for a player not in the spectators list."""
        manager = SpectatorManager()
        game_state = make_game_state(spectators=[10, 11])

        assert manager.is_spectator(game_state, player_id=99) is False

    def test_returns_false_for_active_player(self):
        """Returns False for an active player (not spectating)."""
        manager = SpectatorManager()
        game_state = make_game_state(player_count=4, spectators=[10])

        # Player 1 is an active player, not a spectator
        assert manager.is_spectator(game_state, player_id=1) is False


class TestRejectSpectatorActions:
    """Tests for rejecting game actions from spectator player IDs (Req 22.7)."""

    def _setup_game_with_spectator(self):
        """Helper to set up a game with a spectator via GameEngine."""
        engine = GameEngine()
        deck_cards = [make_card(i, denomination=1) for i in range(1, 36)]
        players = [
            PlayerSetup(
                player_id=pid,
                username=f"Player_{pid}",
                is_computer=False,
                deck_cards=list(deck_cards),
            )
            for pid in range(1, 5)
        ]
        session = GameSession(
            game_id="spectator-test",
            players=players,
            spectators=[100],  # Player 100 is a spectator
        )
        game_state = engine.initialise_game(session)
        return engine, game_state

    def test_spectator_play_card_rejected(self):
        """Spectator cannot play a card."""
        engine, game_state = self._setup_game_with_spectator()

        result = engine.process_action(
            "spectator-test", player_id=100, action={"type": "play_card", "card_id": 1}
        )

        assert isinstance(result, tuple)
        assert result[0] == "spectator_cannot_act"

    def test_spectator_draw_card_rejected(self):
        """Spectator cannot draw a card."""
        engine, game_state = self._setup_game_with_spectator()

        result = engine.process_action(
            "spectator-test", player_id=100, action={"type": "draw_card"}
        )

        assert isinstance(result, tuple)
        assert result[0] == "spectator_cannot_act"

    def test_spectator_accept_draw_rejected(self):
        """Spectator cannot accept a draw."""
        engine, game_state = self._setup_game_with_spectator()

        result = engine.process_action(
            "spectator-test", player_id=100, action={"type": "accept_draw"}
        )

        assert isinstance(result, tuple)
        assert result[0] == "spectator_cannot_act"

    def test_active_player_can_still_act(self):
        """Active players can still perform actions normally."""
        engine, game_state = self._setup_game_with_spectator()

        # The active player should be able to draw
        active_player_id = game_state.players[game_state.current_player_index].player_id
        result = engine.process_action(
            "spectator-test", player_id=active_player_id, action={"type": "draw_card"}
        )

        # Should succeed (list of events, not an error tuple)
        assert isinstance(result, list)
