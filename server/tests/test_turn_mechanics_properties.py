"""Property-based tests for the Game_Engine turn mechanics.

Uses Hypothesis to verify turn mechanics properties across
randomly generated game states and actions.

Properties 16-21: Turn mechanics
- Property 16: Turn validity — play or draw
- Property 17: Playing a card advances sequence correctly
- Property 18: Drawing a card moves top of draw deck to hand
- Property 19: Drawn matching card offers play-or-keep choice
- Property 20: Empty draw deck causes decked state
- Property 21: Last played denomination tracked independently

**Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9**
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


SEQUENCE_CYCLE = [1, 10, 100, 1000, 10000, 100000]
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
def hand_strategy(draw, min_size=1, max_size=10):
    """Generate a hand of cards with unique card_ids."""
    size = draw(st.integers(min_value=min_size, max_value=max_size))
    cards = []
    for i in range(size):
        card = draw(card_strategy(card_id=i + 1))
        cards.append(card)
    return cards


@st.composite
def draw_deck_strategy(draw, min_size=1, max_size=20, id_offset=1000):
    """Generate a draw deck of cards with unique card_ids."""
    size = draw(st.integers(min_value=min_size, max_value=max_size))
    cards = []
    for i in range(size):
        card = draw(card_strategy(card_id=id_offset + i))
        cards.append(card)
    return cards


@st.composite
def game_state_strategy(draw, num_players=None, current_sequence=None, sequence_broken=None):
    """Generate a valid game state for turn mechanics testing."""
    n_players = num_players if num_players is not None else draw(st.integers(min_value=4, max_value=8))
    seq = current_sequence if current_sequence is not None else draw(st.sampled_from(DENOMINATIONS))
    broken = sequence_broken if sequence_broken is not None else draw(st.booleans())
    current_player_index = draw(st.integers(min_value=0, max_value=n_players - 1))
    direction = draw(st.sampled_from([1, -1]))

    players = []
    for i in range(n_players):
        hand = draw(hand_strategy(min_size=1, max_size=7))
        # Offset card_ids to avoid collisions between players
        for j, card in enumerate(hand):
            hand[j] = CardInstance(
                card_id=i * 1000 + j + 1,
                card_name=card.card_name,
                denomination=card.denomination,
                power_text=card.power_text,
                expansion_id=card.expansion_id,
            )
        deck = draw(draw_deck_strategy(min_size=1, max_size=15, id_offset=i * 1000 + 500))
        player = PlayerState(
            player_id=i + 1,
            username=f"Player_{i + 1}",
            is_computer=False,
            hand=hand,
            draw_deck=deck,
            play_pile=[],
            discard_pile=[],
            cumulative_score=0,
            is_decked=False,
            has_gone_out=False,
            seat_position=i + 1,
        )
        players.append(player)

    last_played = draw(st.one_of(st.none(), st.sampled_from(DENOMINATIONS)))

    state = GameState(
        game_id="prop-test-game",
        players=players,
        spectators=[],
        current_player_index=current_player_index,
        direction=direction,
        current_sequence=seq,
        last_played_denomination=last_played,
        sequence_broken=broken,
        round_number=1,
        frozen_powers={},
        game_status="active",
        reconnection_timeout=30,
        pending_draw=None,
    )
    return state


def register_game(engine: GameEngine, state: GameState) -> None:
    """Register a game state in the engine's internal store."""
    engine._games[state.game_id] = state


def next_in_sequence(denomination: int) -> int:
    """Get the next denomination in the sequence cycle."""
    idx = SEQUENCE_CYCLE.index(denomination)
    return SEQUENCE_CYCLE[(idx + 1) % len(SEQUENCE_CYCLE)]


# --- Property 16: Turn validity — play or draw ---


class TestProperty16TurnValidity:
    """Property 16: Turn validity — play or draw.

    For any game state where it is a player's turn, the Game_Engine should accept
    only: (a) playing a card whose denomination matches the current sequence,
    (b) playing a 1-denomination card if the sequence was broken, (c) playing a
    Clone card matching the last played denomination, or (d) drawing a card.
    All other actions should be rejected.

    **Validates: Requirements 6.1, 6.7, 9.8**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_valid_sequence_match_play_accepted(self, data):
        """Playing a card whose denomination matches the current sequence is accepted."""
        seq = data.draw(st.sampled_from(DENOMINATIONS))
        state = data.draw(game_state_strategy(current_sequence=seq, sequence_broken=False))
        engine = GameEngine()
        register_game(engine, state)

        player = state.players[state.current_player_index]
        # Add a card matching the current sequence to the player's hand
        matching_card = CardInstance(
            card_id=99999,
            card_name="MatchingCard",
            denomination=seq,
            power_text="Go",
            expansion_id=1,
        )
        player.hand.append(matching_card)

        result = engine.process_action(
            state.game_id, player.player_id, {"type": "play_card", "card_id": 99999}
        )
        assert isinstance(result, list), f"Expected success but got error: {result}"

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_sequence_broken_allows_1_denomination_play(self, data):
        """Playing a 1-denomination card when sequence is broken is accepted."""
        # Use a non-1 sequence so the 1-card wouldn't normally be valid
        seq = data.draw(st.sampled_from([10, 100, 1000, 10000, 100000]))
        state = data.draw(game_state_strategy(current_sequence=seq, sequence_broken=True))
        engine = GameEngine()
        register_game(engine, state)

        player = state.players[state.current_player_index]
        one_card = CardInstance(
            card_id=99998,
            card_name="OneCard",
            denomination=1,
            power_text="Go",
            expansion_id=1,
        )
        player.hand.append(one_card)

        result = engine.process_action(
            state.game_id, player.player_id, {"type": "play_card", "card_id": 99998}
        )
        assert isinstance(result, list), f"Expected success but got error: {result}"

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_clone_card_matching_last_played_accepted(self, data):
        """Playing a Clone card whose denomination matches last_played_denomination is accepted."""
        seq = data.draw(st.sampled_from(DENOMINATIONS))
        last_played = data.draw(st.sampled_from(DENOMINATIONS))
        # Ensure clone denomination doesn't match current sequence (to isolate clone logic)
        assume(last_played != seq)

        state = data.draw(game_state_strategy(current_sequence=seq, sequence_broken=False))
        state.last_played_denomination = last_played
        engine = GameEngine()
        register_game(engine, state)

        player = state.players[state.current_player_index]
        clone_card = CardInstance(
            card_id=99997,
            card_name="CloneCard",
            denomination=last_played,
            power_text="Clone",
            expansion_id=1,
        )
        player.hand.append(clone_card)

        result = engine.process_action(
            state.game_id, player.player_id, {"type": "play_card", "card_id": 99997}
        )
        assert isinstance(result, list), f"Expected success but got error: {result}"

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_draw_card_always_accepted(self, data):
        """Drawing a card is always a valid action on a player's turn."""
        state = data.draw(game_state_strategy())
        engine = GameEngine()
        register_game(engine, state)

        player = state.players[state.current_player_index]

        result = engine.process_action(
            state.game_id, player.player_id, {"type": "draw_card"}
        )
        assert isinstance(result, list), f"Expected success but got error: {result}"

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_invalid_denomination_play_rejected(self, data):
        """Playing a card with wrong denomination (not matching sequence, not 1 on break,
        not clone matching last_played) is rejected."""
        seq = data.draw(st.sampled_from(DENOMINATIONS))
        state = data.draw(game_state_strategy(current_sequence=seq, sequence_broken=False))
        state.last_played_denomination = None  # No last played, so clone won't work
        engine = GameEngine()
        register_game(engine, state)

        player = state.players[state.current_player_index]
        # Pick a denomination that doesn't match the sequence
        invalid_denoms = [d for d in DENOMINATIONS if d != seq]
        invalid_denom = data.draw(st.sampled_from(invalid_denoms))

        bad_card = CardInstance(
            card_id=99996,
            card_name="BadCard",
            denomination=invalid_denom,
            power_text="Go",  # Not a Clone card
            expansion_id=1,
        )
        player.hand.append(bad_card)

        result = engine.process_action(
            state.game_id, player.player_id, {"type": "play_card", "card_id": 99996}
        )
        assert isinstance(result, tuple), f"Expected rejection but got success: {result}"
        assert result[0] == "invalid_play"


# --- Property 17: Playing a card advances sequence correctly ---


class TestProperty17PlayingCardAdvancesSequence:
    """Property 17: Playing a card advances sequence correctly.

    For any valid card play, the card should move from the player's hand to their
    play pile, and the sequence should advance to the next denomination in the
    cycle (1→10→100→1000→10000→100000→1).

    **Validates: Requirements 6.2, 6.3**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_card_moves_from_hand_to_play_pile(self, data):
        """For any valid card play, the card moves from hand to play pile."""
        seq = data.draw(st.sampled_from(DENOMINATIONS))
        state = data.draw(game_state_strategy(current_sequence=seq, sequence_broken=False))
        engine = GameEngine()
        register_game(engine, state)

        player = state.players[state.current_player_index]
        card = CardInstance(
            card_id=88888,
            card_name="TestCard",
            denomination=seq,
            power_text="Go",
            expansion_id=1,
        )
        player.hand.append(card)
        hand_size_before = len(player.hand)

        result = engine.process_action(
            state.game_id, player.player_id, {"type": "play_card", "card_id": 88888}
        )

        assert isinstance(result, list)
        assert card in player.play_pile
        assert card not in player.hand
        assert len(player.hand) == hand_size_before - 1

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_sequence_advances_to_next_denomination(self, data):
        """For any valid card play, the sequence advances to the next denomination."""
        seq = data.draw(st.sampled_from(DENOMINATIONS))
        state = data.draw(game_state_strategy(current_sequence=seq, sequence_broken=False))
        engine = GameEngine()
        register_game(engine, state)

        player = state.players[state.current_player_index]
        card = CardInstance(
            card_id=88887,
            card_name="TestCard",
            denomination=seq,
            power_text="Go",
            expansion_id=1,
        )
        player.hand.append(card)

        expected_next = next_in_sequence(seq)

        result = engine.process_action(
            state.game_id, player.player_id, {"type": "play_card", "card_id": 88887}
        )

        assert isinstance(result, list)
        assert state.current_sequence == expected_next

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_100000_wraps_to_1(self, data):
        """Playing a 100000 card wraps the sequence back to 1."""
        state = data.draw(game_state_strategy(current_sequence=100000, sequence_broken=False))
        engine = GameEngine()
        register_game(engine, state)

        player = state.players[state.current_player_index]
        card = CardInstance(
            card_id=88886,
            card_name="BigCard",
            denomination=100000,
            power_text="Go",
            expansion_id=1,
        )
        player.hand.append(card)

        result = engine.process_action(
            state.game_id, player.player_id, {"type": "play_card", "card_id": 88886}
        )

        assert isinstance(result, list)
        assert state.current_sequence == 1


# --- Property 18: Drawing a card moves top of draw deck to hand ---


class TestProperty18DrawingCardMovesToHand:
    """Property 18: Drawing a card moves top of draw deck to hand.

    For any draw action, the top card of the player's draw deck should move to
    the player's hand, and if it does not match the current sequence denomination,
    a pass should be recorded.

    **Validates: Requirements 6.4, 6.6**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_top_card_moves_from_deck_to_hand(self, data):
        """For any draw action, the top card of the draw deck moves to hand."""
        state = data.draw(game_state_strategy())
        engine = GameEngine()
        register_game(engine, state)

        player = state.players[state.current_player_index]
        assume(len(player.draw_deck) > 0)

        top_card = player.draw_deck[0]
        hand_size_before = len(player.hand)
        deck_size_before = len(player.draw_deck)

        result = engine.process_action(
            state.game_id, player.player_id, {"type": "draw_card"}
        )

        assert isinstance(result, list)
        assert top_card in player.hand
        assert len(player.hand) == hand_size_before + 1
        assert len(player.draw_deck) == deck_size_before - 1

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_non_matching_draw_creates_pending_accept(self, data):
        """For any draw of a non-matching card, a pending accept state is created."""
        seq = data.draw(st.sampled_from(DENOMINATIONS))
        state = data.draw(game_state_strategy(current_sequence=seq))
        engine = GameEngine()
        register_game(engine, state)

        player = state.players[state.current_player_index]
        assume(len(player.draw_deck) > 0)

        # Ensure the top card does NOT match the current sequence
        non_matching_denoms = [d for d in DENOMINATIONS if d != seq]
        non_matching_denom = data.draw(st.sampled_from(non_matching_denoms))
        player.draw_deck[0] = CardInstance(
            card_id=77777,
            card_name="NonMatchDraw",
            denomination=non_matching_denom,
            power_text="Go",
            expansion_id=1,
        )

        result = engine.process_action(
            state.game_id, player.player_id, {"type": "draw_card"}
        )

        assert isinstance(result, list)
        assert state.pending_draw is not None
        assert state.pending_draw.matches_sequence is False

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_non_matching_draw_accept_records_pass(self, data):
        """For any non-matching draw followed by accept, a pass is recorded (sequence_broken=True)."""
        seq = data.draw(st.sampled_from(DENOMINATIONS))
        state = data.draw(game_state_strategy(current_sequence=seq))
        engine = GameEngine()
        register_game(engine, state)

        player = state.players[state.current_player_index]
        assume(len(player.draw_deck) > 0)

        # Ensure the top card does NOT match the current sequence
        non_matching_denoms = [d for d in DENOMINATIONS if d != seq]
        non_matching_denom = data.draw(st.sampled_from(non_matching_denoms))
        player.draw_deck[0] = CardInstance(
            card_id=77776,
            card_name="NonMatchDraw",
            denomination=non_matching_denom,
            power_text="Go",
            expansion_id=1,
        )

        engine.process_action(
            state.game_id, player.player_id, {"type": "draw_card"}
        )

        # Accept the draw
        result = engine.process_action(
            state.game_id, player.player_id, {"type": "accept_draw"}
        )

        assert isinstance(result, list)
        assert state.sequence_broken is True


# --- Property 19: Drawn matching card offers play-or-keep choice ---


class TestProperty19DrawnMatchingCardOffersChoice:
    """Property 19: Drawn matching card offers play-or-keep choice.

    For any drawn card whose denomination matches the current sequence, the player
    should be offered the choice to play it immediately or keep it in hand; both
    choices should be valid.

    **Validates: Requirements 6.5**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_matching_draw_creates_pending_choice(self, data):
        """For any matching draw, a pending draw choice is created."""
        seq = data.draw(st.sampled_from(DENOMINATIONS))
        state = data.draw(game_state_strategy(current_sequence=seq))
        engine = GameEngine()
        register_game(engine, state)

        player = state.players[state.current_player_index]
        assume(len(player.draw_deck) > 0)

        # Set top card to match the current sequence
        player.draw_deck[0] = CardInstance(
            card_id=66666,
            card_name="MatchDraw",
            denomination=seq,
            power_text="Go",
            expansion_id=1,
        )

        result = engine.process_action(
            state.game_id, player.player_id, {"type": "draw_card"}
        )

        assert isinstance(result, list)
        assert state.pending_draw is not None
        assert state.pending_draw.matches_sequence is True
        assert state.pending_draw.player_id == player.player_id

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_player_can_play_matching_drawn_card(self, data):
        """For any matching draw, the player can play the drawn card immediately."""
        seq = data.draw(st.sampled_from(DENOMINATIONS))
        state = data.draw(game_state_strategy(current_sequence=seq))
        engine = GameEngine()
        register_game(engine, state)

        player = state.players[state.current_player_index]
        assume(len(player.draw_deck) > 0)

        # Set top card to match the current sequence
        player.draw_deck[0] = CardInstance(
            card_id=66665,
            card_name="MatchDraw",
            denomination=seq,
            power_text="Go",
            expansion_id=1,
        )

        # Draw the card
        engine.process_action(
            state.game_id, player.player_id, {"type": "draw_card"}
        )

        # Play the drawn card
        result = engine.process_action(
            state.game_id, player.player_id, {"type": "play_card", "card_id": 66665}
        )

        assert isinstance(result, list), f"Expected success but got error: {result}"
        assert state.pending_draw is None
        assert state.current_sequence == next_in_sequence(seq)

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_player_can_keep_matching_drawn_card(self, data):
        """For any matching draw, the player can keep the card (accept_draw = pass)."""
        seq = data.draw(st.sampled_from(DENOMINATIONS))
        state = data.draw(game_state_strategy(current_sequence=seq))
        engine = GameEngine()
        register_game(engine, state)

        player = state.players[state.current_player_index]
        assume(len(player.draw_deck) > 0)

        # Set top card to match the current sequence
        player.draw_deck[0] = CardInstance(
            card_id=66664,
            card_name="MatchDraw",
            denomination=seq,
            power_text="Go",
            expansion_id=1,
        )

        # Draw the card
        engine.process_action(
            state.game_id, player.player_id, {"type": "draw_card"}
        )

        # Keep the card (accept)
        result = engine.process_action(
            state.game_id, player.player_id, {"type": "accept_draw"}
        )

        assert isinstance(result, list), f"Expected success but got error: {result}"
        assert state.pending_draw is None
        assert state.sequence_broken is True
        # Card should still be in hand
        card_ids = [c.card_id for c in player.hand]
        assert 66664 in card_ids


# --- Property 20: Empty draw deck causes decked state ---


class TestProperty20EmptyDrawDeckCausesDecked:
    """Property 20: Empty draw deck causes decked state.

    For any player who must draw a card and whose draw deck is empty, that player
    should be marked as decked.

    **Validates: Requirements 6.8**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_empty_deck_draw_marks_player_decked(self, data):
        """For any player with an empty draw deck who draws, they are marked decked."""
        state = data.draw(game_state_strategy())
        engine = GameEngine()
        register_game(engine, state)

        player = state.players[state.current_player_index]
        # Empty the draw deck
        player.draw_deck = []

        result = engine.process_action(
            state.game_id, player.player_id, {"type": "draw_card"}
        )

        assert isinstance(result, list)
        assert player.is_decked is True

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_decked_player_hand_moved_to_discard(self, data):
        """For any player who becomes decked, their hand is moved to discard pile."""
        state = data.draw(game_state_strategy())
        engine = GameEngine()
        register_game(engine, state)

        player = state.players[state.current_player_index]
        # Empty the draw deck
        player.draw_deck = []
        hand_cards_before = list(player.hand)
        assume(len(hand_cards_before) > 0)

        result = engine.process_action(
            state.game_id, player.player_id, {"type": "draw_card"}
        )

        assert isinstance(result, list)
        assert player.hand == []
        for card in hand_cards_before:
            assert card in player.discard_pile

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_decked_event_emitted(self, data):
        """For any player who becomes decked, a player_decked event is emitted."""
        state = data.draw(game_state_strategy())
        engine = GameEngine()
        register_game(engine, state)

        player = state.players[state.current_player_index]
        player.draw_deck = []

        result = engine.process_action(
            state.game_id, player.player_id, {"type": "draw_card"}
        )

        assert isinstance(result, list)
        decked_events = [e for e in result if e["type"] == "player_decked"]
        assert len(decked_events) == 1
        assert decked_events[0]["player_id"] == player.player_id


# --- Property 21: Last played denomination tracked independently ---


class TestProperty21LastPlayedDenominationTracked:
    """Property 21: Last played denomination tracked independently.

    For any card play, the last_played_denomination should equal that card's
    denomination, independent of the current sequence state.

    **Validates: Requirements 6.9**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_last_played_equals_card_denomination(self, data):
        """For any valid card play, last_played_denomination equals the played card's denomination."""
        seq = data.draw(st.sampled_from(DENOMINATIONS))
        state = data.draw(game_state_strategy(current_sequence=seq, sequence_broken=False))
        engine = GameEngine()
        register_game(engine, state)

        player = state.players[state.current_player_index]
        card = CardInstance(
            card_id=55555,
            card_name="TrackCard",
            denomination=seq,
            power_text="Go",
            expansion_id=1,
        )
        player.hand.append(card)

        result = engine.process_action(
            state.game_id, player.player_id, {"type": "play_card", "card_id": 55555}
        )

        assert isinstance(result, list)
        assert state.last_played_denomination == seq

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_last_played_independent_of_current_sequence(self, data):
        """For any valid card play, last_played_denomination differs from current_sequence
        (since sequence advances after play)."""
        seq = data.draw(st.sampled_from(DENOMINATIONS))
        state = data.draw(game_state_strategy(current_sequence=seq, sequence_broken=False))
        engine = GameEngine()
        register_game(engine, state)

        player = state.players[state.current_player_index]
        card = CardInstance(
            card_id=55554,
            card_name="TrackCard",
            denomination=seq,
            power_text="Go",
            expansion_id=1,
        )
        player.hand.append(card)

        result = engine.process_action(
            state.game_id, player.player_id, {"type": "play_card", "card_id": 55554}
        )

        assert isinstance(result, list)
        # last_played_denomination is the card's denomination
        assert state.last_played_denomination == seq
        # current_sequence has advanced to the next value
        assert state.current_sequence == next_in_sequence(seq)
        # They are different (since the sequence advanced)
        assert state.last_played_denomination != state.current_sequence

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_last_played_set_for_clone_card_play(self, data):
        """For any Clone card play, last_played_denomination equals the Clone card's denomination."""
        seq = data.draw(st.sampled_from(DENOMINATIONS))
        last_played = data.draw(st.sampled_from(DENOMINATIONS))
        assume(last_played != seq)

        state = data.draw(game_state_strategy(current_sequence=seq, sequence_broken=False))
        state.last_played_denomination = last_played
        engine = GameEngine()
        register_game(engine, state)

        player = state.players[state.current_player_index]
        clone_card = CardInstance(
            card_id=55553,
            card_name="CloneTrack",
            denomination=last_played,
            power_text="Clone",
            expansion_id=1,
        )
        player.hand.append(clone_card)

        result = engine.process_action(
            state.game_id, player.player_id, {"type": "play_card", "card_id": 55553}
        )

        assert isinstance(result, list)
        assert state.last_played_denomination == last_played
