"""Property-based tests for spectator management.

Uses Hypothesis to verify that spectators receive only public state,
cannot perform game actions, and that spectator leaving does not affect
game state.

**Validates: Requirements 22.2, 22.3, 22.5, 22.7**
"""

import sys
import os

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from game.spectator import SpectatorManager
from game.engine import GameEngine, GameSession, PlayerSetup
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
def game_state_with_spectators_strategy(draw, player_count=None):
    """Generate a random GameState with spectators."""
    n_players = player_count if player_count is not None else draw(
        st.integers(min_value=4, max_value=8)
    )
    players = [draw(player_state_strategy(player_id=i + 1, seat_position=i + 1)) for i in range(n_players)]
    # Spectator IDs are distinct from player IDs (start at 100)
    n_spectators = draw(st.integers(min_value=1, max_value=5))
    spectators = list(range(100, 100 + n_spectators))
    direction = draw(st.sampled_from([1, -1]))
    sequence = draw(st.sampled_from(DENOMINATIONS))
    current_idx = draw(st.integers(min_value=0, max_value=n_players - 1))

    return GameState(
        game_id="prop-test-game",
        players=players,
        spectators=spectators,
        current_player_index=current_idx,
        direction=direction,
        current_sequence=sequence,
        round_number=draw(st.integers(min_value=1, max_value=5)),
        game_status="active",
        reconnection_timeout=30,
    )


# --- Property 72: Spectator receives only public state ---


class TestProperty72SpectatorReceivesOnlyPublicState:
    """Property 72: Spectator receives only public state.

    For any game state, the spectator visible state should contain play piles,
    discard piles, draw deck counts, and scores, but NOT hand contents.

    **Validates: Requirements 22.2, 22.3**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_spectator_state_contains_public_fields(self, data):
        """For any game state, spectator visible state contains all public fields."""
        state = data.draw(game_state_with_spectators_strategy())
        manager = SpectatorManager()

        result = manager.get_spectator_visible_state(state)

        assert "play_piles" in result
        assert "discard_piles" in result
        assert "draw_deck_counts" in result
        assert "scores" in result
        assert "current_sequence" in result
        assert "direction" in result
        assert "active_player_id" in result
        assert "round_number" in result
        assert "game_status" in result

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_spectator_state_does_not_contain_hands(self, data):
        """For any game state, spectator visible state does NOT contain hand contents."""
        state = data.draw(game_state_with_spectators_strategy())
        manager = SpectatorManager()

        result = manager.get_spectator_visible_state(state)

        assert "hand" not in result
        assert "hands" not in result

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_spectator_state_draw_deck_counts_match(self, data):
        """For any game state, draw deck counts match actual deck sizes."""
        state = data.draw(game_state_with_spectators_strategy())
        manager = SpectatorManager()

        result = manager.get_spectator_visible_state(state)

        for player in state.players:
            assert result["draw_deck_counts"][player.player_id] == len(player.draw_deck)

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_spectator_state_scores_match(self, data):
        """For any game state, spectator scores match actual player scores."""
        state = data.draw(game_state_with_spectators_strategy())
        manager = SpectatorManager()

        result = manager.get_spectator_visible_state(state)

        for player in state.players:
            assert result["scores"][player.player_id] == player.cumulative_score

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_spectator_state_play_piles_match(self, data):
        """For any game state, spectator play piles match actual play pile sizes."""
        state = data.draw(game_state_with_spectators_strategy())
        manager = SpectatorManager()

        result = manager.get_spectator_visible_state(state)

        for player in state.players:
            assert len(result["play_piles"][player.player_id]) == len(player.play_pile)


# --- Property 73: Spectator cannot perform game actions ---


class TestProperty73SpectatorCannotPerformGameActions:
    """Property 73: Spectator cannot perform game actions.

    For any spectator player ID, attempting to perform a game action should
    be rejected.

    **Validates: Requirements 22.7**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_spectator_play_card_rejected(self, data):
        """For any spectator, attempting to play a card is rejected."""
        spectator_id = data.draw(st.integers(min_value=100, max_value=200))
        card_id = data.draw(st.integers(min_value=1, max_value=1000))

        engine = GameEngine()
        deck_cards = [
            CardInstance(
                card_id=i,
                card_name=f"Tribble_{i}",
                denomination=1,
                power_text="Go",
                expansion_id=1,
            )
            for i in range(1, 36)
        ]
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
            game_id="spectator-prop-test",
            players=players,
            spectators=[spectator_id],
        )
        engine.initialise_game(session)

        result = engine.process_action(
            "spectator-prop-test",
            player_id=spectator_id,
            action={"type": "play_card", "card_id": card_id},
        )

        assert isinstance(result, tuple)
        assert result[0] == "spectator_cannot_act"

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_spectator_draw_card_rejected(self, data):
        """For any spectator, attempting to draw a card is rejected."""
        spectator_id = data.draw(st.integers(min_value=100, max_value=200))

        engine = GameEngine()
        deck_cards = [
            CardInstance(
                card_id=i,
                card_name=f"Tribble_{i}",
                denomination=1,
                power_text="Go",
                expansion_id=1,
            )
            for i in range(1, 36)
        ]
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
            game_id="spectator-prop-test",
            players=players,
            spectators=[spectator_id],
        )
        engine.initialise_game(session)

        result = engine.process_action(
            "spectator-prop-test",
            player_id=spectator_id,
            action={"type": "draw_card"},
        )

        assert isinstance(result, tuple)
        assert result[0] == "spectator_cannot_act"

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_spectator_accept_draw_rejected(self, data):
        """For any spectator, attempting to accept a draw is rejected."""
        spectator_id = data.draw(st.integers(min_value=100, max_value=200))

        engine = GameEngine()
        deck_cards = [
            CardInstance(
                card_id=i,
                card_name=f"Tribble_{i}",
                denomination=1,
                power_text="Go",
                expansion_id=1,
            )
            for i in range(1, 36)
        ]
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
            game_id="spectator-prop-test",
            players=players,
            spectators=[spectator_id],
        )
        engine.initialise_game(session)

        result = engine.process_action(
            "spectator-prop-test",
            player_id=spectator_id,
            action={"type": "accept_draw"},
        )

        assert isinstance(result, tuple)
        assert result[0] == "spectator_cannot_act"


# --- Property 74: Spectator leaving does not affect game state ---


class TestProperty74SpectatorLeavingDoesNotAffectGameState:
    """Property 74: Spectator leaving does not affect game state.

    For any spectator who leaves, the game state (players, scores, sequence,
    direction) should remain unchanged.

    **Validates: Requirements 22.5**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_players_unchanged_after_spectator_leaves(self, data):
        """For any spectator who leaves, the players list remains unchanged."""
        state = data.draw(game_state_with_spectators_strategy())
        spectator_id = data.draw(st.sampled_from(state.spectators))

        # Record state before
        player_ids_before = [p.player_id for p in state.players]
        n_players_before = len(state.players)

        manager = SpectatorManager()
        manager.leave_spectate(state, player_id=spectator_id)

        # Verify players unchanged
        player_ids_after = [p.player_id for p in state.players]
        assert player_ids_after == player_ids_before
        assert len(state.players) == n_players_before

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_scores_unchanged_after_spectator_leaves(self, data):
        """For any spectator who leaves, all player scores remain unchanged."""
        state = data.draw(game_state_with_spectators_strategy())
        spectator_id = data.draw(st.sampled_from(state.spectators))

        # Record scores before
        scores_before = {p.player_id: p.cumulative_score for p in state.players}

        manager = SpectatorManager()
        manager.leave_spectate(state, player_id=spectator_id)

        # Verify scores unchanged
        for player in state.players:
            assert player.cumulative_score == scores_before[player.player_id]

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_sequence_unchanged_after_spectator_leaves(self, data):
        """For any spectator who leaves, current_sequence remains unchanged."""
        state = data.draw(game_state_with_spectators_strategy())
        spectator_id = data.draw(st.sampled_from(state.spectators))

        sequence_before = state.current_sequence

        manager = SpectatorManager()
        manager.leave_spectate(state, player_id=spectator_id)

        assert state.current_sequence == sequence_before

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_direction_unchanged_after_spectator_leaves(self, data):
        """For any spectator who leaves, direction remains unchanged."""
        state = data.draw(game_state_with_spectators_strategy())
        spectator_id = data.draw(st.sampled_from(state.spectators))

        direction_before = state.direction

        manager = SpectatorManager()
        manager.leave_spectate(state, player_id=spectator_id)

        assert state.direction == direction_before

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_spectator_removed_from_list(self, data):
        """For any spectator who leaves, they are removed from the spectators list."""
        state = data.draw(game_state_with_spectators_strategy())
        spectator_id = data.draw(st.sampled_from(state.spectators))

        manager = SpectatorManager()
        result = manager.leave_spectate(state, player_id=spectator_id)

        assert result is True
        assert spectator_id not in state.spectators
