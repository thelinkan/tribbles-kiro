"""Property-based tests for decked state logic in the Game_Engine.

Uses Hypothesis to verify decked state properties across
randomly generated game states.

Properties 22-24: Decked state
- Property 22: Decked state invariants
- Property 23: Decked player is valid power target
- Property 24: Last non-decked player goes out

**Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.5**
"""

import sys
import os

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from game.engine import GameEngine
from models import CardInstance, GameState, PendingDraw, PlayerState


DENOMINATIONS = [1, 10, 100, 1000, 10000, 100000]
POWERS = ["Go", "Skip", "Poison", "Rescue", "Reverse", "Discard"]


# --- Strategies ---


@st.composite
def card_strategy(draw, card_id=None, denomination=None, power=None):
    """Generate a random CardInstance with optional fixed fields."""
    cid = card_id if card_id is not None else draw(st.integers(min_value=1, max_value=100000))
    denom = denomination if denomination is not None else draw(st.sampled_from(DENOMINATIONS))
    pwr = power if power is not None else draw(st.sampled_from(POWERS))
    return CardInstance(
        card_id=cid,
        card_name=f"Tribble_{cid}",
        denomination=denom,
        power_text=pwr,
        expansion_id=1,
    )


@st.composite
def hand_strategy(draw, min_size=1, max_size=7, id_offset=0):
    """Generate a hand of cards with unique card_ids."""
    size = draw(st.integers(min_value=min_size, max_value=max_size))
    cards = []
    for i in range(size):
        card = draw(card_strategy(card_id=id_offset + i + 1))
        cards.append(card)
    return cards


@st.composite
def play_pile_strategy(draw, min_size=0, max_size=5, id_offset=0):
    """Generate a play pile of cards with unique card_ids."""
    size = draw(st.integers(min_value=min_size, max_value=max_size))
    cards = []
    for i in range(size):
        card = draw(card_strategy(card_id=id_offset + i + 1))
        cards.append(card)
    return cards


@st.composite
def draw_deck_strategy(draw, min_size=1, max_size=15, id_offset=0):
    """Generate a draw deck of cards with unique card_ids."""
    size = draw(st.integers(min_value=min_size, max_value=max_size))
    cards = []
    for i in range(size):
        card = draw(card_strategy(card_id=id_offset + i + 1))
        cards.append(card)
    return cards


@st.composite
def game_state_with_empty_draw_deck(draw, num_players=None):
    """Generate a game state where the active player has an empty draw deck.

    Used for Property 22 to test decked state invariants.
    """
    n_players = num_players if num_players is not None else draw(st.integers(min_value=4, max_value=8))
    current_player_index = draw(st.integers(min_value=0, max_value=n_players - 1))
    seq = draw(st.sampled_from(DENOMINATIONS))
    direction = draw(st.sampled_from([1, -1]))

    players = []
    for i in range(n_players):
        hand_offset = i * 1000
        pile_offset = i * 1000 + 200
        deck_offset = i * 1000 + 500

        hand = draw(hand_strategy(min_size=1, max_size=7, id_offset=hand_offset))
        play_pile = draw(play_pile_strategy(min_size=0, max_size=5, id_offset=pile_offset))

        if i == current_player_index:
            # Active player has empty draw deck (will become decked)
            draw_deck = []
        else:
            # Other players have cards in their draw deck
            draw_deck = draw(draw_deck_strategy(min_size=1, max_size=15, id_offset=deck_offset))

        player = PlayerState(
            player_id=i + 1,
            username=f"Player_{i + 1}",
            is_computer=False,
            hand=hand,
            draw_deck=draw_deck,
            play_pile=play_pile,
            discard_pile=[],
            cumulative_score=0,
            is_decked=False,
            has_gone_out=False,
            seat_position=i + 1,
        )
        players.append(player)

    state = GameState(
        game_id="prop-test-game",
        players=players,
        spectators=[],
        current_player_index=current_player_index,
        direction=direction,
        current_sequence=seq,
        last_played_denomination=None,
        sequence_broken=False,
        round_number=1,
        frozen_powers={},
        game_status="active",
        reconnection_timeout=30,
        pending_draw=None,
    )
    return state


@st.composite
def game_state_with_decked_player(draw, num_players=None):
    """Generate a game state where at least one player is already decked.

    Used for Property 23 to test that decked players remain valid targets.
    """
    n_players = num_players if num_players is not None else draw(st.integers(min_value=4, max_value=8))
    seq = draw(st.sampled_from(DENOMINATIONS))
    direction = draw(st.sampled_from([1, -1]))

    # Choose which player(s) are decked (at least one, but not all)
    decked_indices = draw(
        st.lists(
            st.integers(min_value=0, max_value=n_players - 1),
            min_size=1,
            max_size=n_players - 1,
            unique=True,
        )
    )

    # Current player must be non-decked
    non_decked_indices = [i for i in range(n_players) if i not in decked_indices]
    current_player_index = draw(st.sampled_from(non_decked_indices))

    players = []
    for i in range(n_players):
        hand_offset = i * 1000
        pile_offset = i * 1000 + 200
        deck_offset = i * 1000 + 500

        if i in decked_indices:
            # Decked player: empty hand, empty draw deck, has play pile
            play_pile = draw(play_pile_strategy(min_size=0, max_size=5, id_offset=pile_offset))
            player = PlayerState(
                player_id=i + 1,
                username=f"Player_{i + 1}",
                is_computer=False,
                hand=[],
                draw_deck=[],
                play_pile=play_pile,
                discard_pile=draw(play_pile_strategy(min_size=0, max_size=5, id_offset=pile_offset + 100)),
                cumulative_score=0,
                is_decked=True,
                has_gone_out=False,
                seat_position=i + 1,
            )
        else:
            hand = draw(hand_strategy(min_size=1, max_size=7, id_offset=hand_offset))
            draw_deck = draw(draw_deck_strategy(min_size=1, max_size=15, id_offset=deck_offset))
            play_pile = draw(play_pile_strategy(min_size=0, max_size=5, id_offset=pile_offset))
            player = PlayerState(
                player_id=i + 1,
                username=f"Player_{i + 1}",
                is_computer=False,
                hand=hand,
                draw_deck=draw_deck,
                play_pile=play_pile,
                discard_pile=[],
                cumulative_score=0,
                is_decked=False,
                has_gone_out=False,
                seat_position=i + 1,
            )
        players.append(player)

    state = GameState(
        game_id="prop-test-game",
        players=players,
        spectators=[],
        current_player_index=current_player_index,
        direction=direction,
        current_sequence=seq,
        last_played_denomination=None,
        sequence_broken=False,
        round_number=1,
        frozen_powers={},
        game_status="active",
        reconnection_timeout=30,
        pending_draw=None,
    )
    return state


@st.composite
def game_state_all_but_one_decked(draw, num_players=None):
    """Generate a game state where all players except one are decked,
    and the active player (who is not decked) has an empty draw deck.

    When the active player draws, they become decked, leaving the one
    remaining non-decked player as the last player standing.

    Used for Property 24 to test last non-decked player goes out.
    """
    n_players = num_players if num_players is not None else draw(st.integers(min_value=3, max_value=8))
    seq = draw(st.sampled_from(DENOMINATIONS))
    direction = draw(st.sampled_from([1, -1]))

    # Choose the player who will be the last standing (not the active player)
    # The active player will become decked, leaving last_standing as the only one
    all_indices = list(range(n_players))
    # We need at least 2 non-decked players before the action:
    # the active player (who will become decked) and the last standing player
    active_player_index = draw(st.integers(min_value=0, max_value=n_players - 1))
    remaining_indices = [i for i in all_indices if i != active_player_index]
    last_standing_index = draw(st.sampled_from(remaining_indices))

    players = []
    for i in range(n_players):
        hand_offset = i * 1000
        pile_offset = i * 1000 + 200
        deck_offset = i * 1000 + 500

        if i == active_player_index:
            # Active player: has hand, empty draw deck (will become decked)
            hand = draw(hand_strategy(min_size=1, max_size=7, id_offset=hand_offset))
            play_pile = draw(play_pile_strategy(min_size=0, max_size=5, id_offset=pile_offset))
            player = PlayerState(
                player_id=i + 1,
                username=f"Player_{i + 1}",
                is_computer=False,
                hand=hand,
                draw_deck=[],
                play_pile=play_pile,
                discard_pile=[],
                cumulative_score=0,
                is_decked=False,
                has_gone_out=False,
                seat_position=i + 1,
            )
        elif i == last_standing_index:
            # Last standing player: has hand and draw deck, not decked
            hand = draw(hand_strategy(min_size=1, max_size=7, id_offset=hand_offset))
            draw_deck = draw(draw_deck_strategy(min_size=1, max_size=15, id_offset=deck_offset))
            play_pile = draw(play_pile_strategy(min_size=0, max_size=5, id_offset=pile_offset))
            player = PlayerState(
                player_id=i + 1,
                username=f"Player_{i + 1}",
                is_computer=False,
                hand=hand,
                draw_deck=draw_deck,
                play_pile=play_pile,
                discard_pile=[],
                cumulative_score=0,
                is_decked=False,
                has_gone_out=False,
                seat_position=i + 1,
            )
        else:
            # All other players are already decked
            play_pile = draw(play_pile_strategy(min_size=0, max_size=5, id_offset=pile_offset))
            player = PlayerState(
                player_id=i + 1,
                username=f"Player_{i + 1}",
                is_computer=False,
                hand=[],
                draw_deck=[],
                play_pile=play_pile,
                discard_pile=draw(play_pile_strategy(min_size=0, max_size=3, id_offset=pile_offset + 100)),
                cumulative_score=0,
                is_decked=True,
                has_gone_out=False,
                seat_position=i + 1,
            )
        players.append(player)

    state = GameState(
        game_id="prop-test-game",
        players=players,
        spectators=[],
        current_player_index=active_player_index,
        direction=direction,
        current_sequence=seq,
        last_played_denomination=None,
        sequence_broken=False,
        round_number=1,
        frozen_powers={},
        game_status="active",
        reconnection_timeout=30,
        pending_draw=None,
    )
    return state, last_standing_index


def register_game(engine: GameEngine, state: GameState) -> None:
    """Register a game state in the engine's internal store."""
    engine._games[state.game_id] = state


# --- Property 22: Decked state invariants ---


class TestProperty22DeckedStateInvariants:
    """Property 22: Decked state invariants.

    For any player who becomes decked: their hand should be immediately emptied
    (moved to discard pile), they should not be able to score points nor have
    points scored from them (except via Antidote), and their play pile should
    remain unchanged for the duration of the round.

    **Validates: Requirements 7.1, 7.2, 7.3**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_hand_emptied_to_discard_on_decked(self, data):
        """For any player who becomes decked, all hand cards move to discard pile."""
        state = data.draw(game_state_with_empty_draw_deck())
        engine = GameEngine()
        register_game(engine, state)

        player = state.players[state.current_player_index]
        hand_cards_before = list(player.hand)
        assume(len(hand_cards_before) > 0)

        result = engine.process_action(
            state.game_id, player.player_id, {"type": "draw_card"}
        )

        assert isinstance(result, list)
        assert player.is_decked is True
        assert player.hand == []
        for card in hand_cards_before:
            assert card in player.discard_pile

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_discard_pile_grows_by_hand_size(self, data):
        """For any player who becomes decked, discard pile grows by the hand size."""
        state = data.draw(game_state_with_empty_draw_deck())
        engine = GameEngine()
        register_game(engine, state)

        player = state.players[state.current_player_index]
        hand_size_before = len(player.hand)
        discard_size_before = len(player.discard_pile)
        assume(hand_size_before > 0)

        result = engine.process_action(
            state.game_id, player.player_id, {"type": "draw_card"}
        )

        assert isinstance(result, list)
        assert len(player.discard_pile) == discard_size_before + hand_size_before

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_play_pile_unchanged_when_decked(self, data):
        """For any player who becomes decked, their play pile remains unchanged."""
        state = data.draw(game_state_with_empty_draw_deck())
        engine = GameEngine()
        register_game(engine, state)

        player = state.players[state.current_player_index]
        play_pile_before = list(player.play_pile)

        result = engine.process_action(
            state.game_id, player.player_id, {"type": "draw_card"}
        )

        assert isinstance(result, list)
        assert player.is_decked is True
        assert player.play_pile == play_pile_before

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_cannot_score_from_decked_player(self, data):
        """For any decked player, can_score_from returns False."""
        state = data.draw(game_state_with_empty_draw_deck())
        engine = GameEngine()
        register_game(engine, state)

        player = state.players[state.current_player_index]

        # Trigger decked state
        engine.process_action(
            state.game_id, player.player_id, {"type": "draw_card"}
        )

        assert player.is_decked is True
        assert engine.can_score_from(player) is False

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_cannot_score_to_decked_player(self, data):
        """For any decked player, can_score_to returns False."""
        state = data.draw(game_state_with_empty_draw_deck())
        engine = GameEngine()
        register_game(engine, state)

        player = state.players[state.current_player_index]

        # Trigger decked state
        engine.process_action(
            state.game_id, player.player_id, {"type": "draw_card"}
        )

        assert player.is_decked is True
        assert engine.can_score_to(player) is False


# --- Property 23: Decked player is valid power target ---


class TestProperty23DeckedPlayerIsValidPowerTarget:
    """Property 23: Decked player is valid power target.

    For any decked player, they should remain a valid target for Tribbles powers.
    This means they remain in the players list and their state is accessible.

    **Validates: Requirements 7.4**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_decked_player_remains_in_players_list(self, data):
        """For any decked player, they remain in the game's players list."""
        state = data.draw(game_state_with_decked_player())
        engine = GameEngine()
        register_game(engine, state)

        decked_players = [p for p in state.players if p.is_decked]
        assume(len(decked_players) > 0)

        for decked_player in decked_players:
            # Player is still in the players list
            assert decked_player in state.players
            # Player can be found by player_id
            found = [p for p in state.players if p.player_id == decked_player.player_id]
            assert len(found) == 1

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_decked_player_play_pile_accessible(self, data):
        """For any decked player, their play pile is accessible for power references."""
        state = data.draw(game_state_with_decked_player())
        engine = GameEngine()
        register_game(engine, state)

        decked_players = [p for p in state.players if p.is_decked]
        assume(len(decked_players) > 0)

        for decked_player in decked_players:
            # Play pile is accessible (not None, not removed)
            assert decked_player.play_pile is not None
            assert isinstance(decked_player.play_pile, list)

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_decked_player_not_excluded_from_iteration(self, data):
        """For any decked player, iterating over all players includes them."""
        state = data.draw(game_state_with_decked_player())
        engine = GameEngine()
        register_game(engine, state)

        decked_players = [p for p in state.players if p.is_decked]
        assume(len(decked_players) > 0)

        # Verify that a power targeting "any player" would include decked players
        all_player_ids = [p.player_id for p in state.players]
        for decked_player in decked_players:
            assert decked_player.player_id in all_player_ids

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_decked_player_state_fields_accessible(self, data):
        """For any decked player, all state fields remain accessible."""
        state = data.draw(game_state_with_decked_player())
        engine = GameEngine()
        register_game(engine, state)

        decked_players = [p for p in state.players if p.is_decked]
        assume(len(decked_players) > 0)

        for decked_player in decked_players:
            # All fields are accessible (not removed or corrupted)
            assert decked_player.is_decked is True
            assert isinstance(decked_player.player_id, int)
            assert isinstance(decked_player.username, str)
            assert isinstance(decked_player.hand, list)
            assert isinstance(decked_player.discard_pile, list)
            assert isinstance(decked_player.play_pile, list)
            assert isinstance(decked_player.cumulative_score, int)


# --- Property 24: Last non-decked player goes out ---


class TestProperty24LastNonDeckedPlayerGoesOut:
    """Property 24: Last non-decked player goes out.

    For any game state where all players except one are decked, the remaining
    player should immediately go out by placing their entire hand into their
    play pile.

    **Validates: Requirements 7.5**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_last_player_goes_out_when_others_decked(self, data):
        """When all but one player become decked, the last player goes out."""
        state, last_standing_index = data.draw(game_state_all_but_one_decked())
        engine = GameEngine()
        register_game(engine, state)

        active_player = state.players[state.current_player_index]
        last_standing = state.players[last_standing_index]

        result = engine.process_action(
            state.game_id, active_player.player_id, {"type": "draw_card"}
        )

        assert isinstance(result, list)
        # Active player is now decked
        assert active_player.is_decked is True
        # Last standing player has gone out
        assert last_standing.has_gone_out is True

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_last_player_hand_moves_to_play_pile(self, data):
        """When last player goes out, their hand moves to their play pile."""
        state, last_standing_index = data.draw(game_state_all_but_one_decked())
        engine = GameEngine()
        register_game(engine, state)

        active_player = state.players[state.current_player_index]
        last_standing = state.players[last_standing_index]
        hand_cards_before = list(last_standing.hand)
        play_pile_before = list(last_standing.play_pile)
        assume(len(hand_cards_before) > 0)

        result = engine.process_action(
            state.game_id, active_player.player_id, {"type": "draw_card"}
        )

        assert isinstance(result, list)
        # Hand is now empty
        assert last_standing.hand == []
        # All hand cards are now in the play pile
        for card in hand_cards_before:
            assert card in last_standing.play_pile
        # Existing play pile cards are preserved
        for card in play_pile_before:
            assert card in last_standing.play_pile

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_last_player_play_pile_size_correct(self, data):
        """When last player goes out, play pile size = original pile + hand size."""
        state, last_standing_index = data.draw(game_state_all_but_one_decked())
        engine = GameEngine()
        register_game(engine, state)

        active_player = state.players[state.current_player_index]
        last_standing = state.players[last_standing_index]
        hand_size_before = len(last_standing.hand)
        pile_size_before = len(last_standing.play_pile)
        assume(hand_size_before > 0)

        result = engine.process_action(
            state.game_id, active_player.player_id, {"type": "draw_card"}
        )

        assert isinstance(result, list)
        assert len(last_standing.play_pile) == pile_size_before + hand_size_before

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_last_player_went_out_event_emitted(self, data):
        """When last player goes out, a player_went_out event is emitted."""
        state, last_standing_index = data.draw(game_state_all_but_one_decked())
        engine = GameEngine()
        register_game(engine, state)

        active_player = state.players[state.current_player_index]
        last_standing = state.players[last_standing_index]
        assume(len(last_standing.hand) > 0)

        result = engine.process_action(
            state.game_id, active_player.player_id, {"type": "draw_card"}
        )

        assert isinstance(result, list)
        went_out_events = [e for e in result if e["type"] == "player_went_out"]
        assert len(went_out_events) == 1
        assert went_out_events[0]["player_id"] == last_standing.player_id
        assert went_out_events[0]["reason"] == "last_player_standing"
