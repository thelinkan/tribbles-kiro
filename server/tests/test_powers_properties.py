"""Property-based tests for the PowerResolver base powers.

Uses Hypothesis to verify power activation and effect properties across
randomly generated game states and card configurations.

Properties 28-34: Base power effects
- Property 28: Power activation choice
- Property 29: Discard power effect
- Property 30: Go power grants additional turn
- Property 31: Skip power skips next player
- Property 32: Poison power scores from opponent's draw deck
- Property 33: Rescue power recovers from discard pile
- Property 34: Reverse power toggles direction (idempotent pair)

**Validates: Requirements 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8**
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from models import CardInstance, GameState, PendingPower, PlayerState
from game.powers.resolver import (
    ACTIVATABLE_POWERS,
    IMMEDIATE_POWERS,
    POWERS_NEEDING_TARGET,
    PowerResolver,
)
from scoring.service import ScoreService


DENOMINATIONS = [1, 10, 100, 1000, 10000, 100000]
SEQUENCE_CYCLE = [1, 10, 100, 1000, 10000, 100000]
ACTIVATABLE_POWER_LIST = list(ACTIVATABLE_POWERS)


# --- Strategies ---


@st.composite
def card_strategy(draw, card_id=None, denomination=None, power_text=None):
    """Generate a random CardInstance."""
    cid = card_id if card_id is not None else draw(st.integers(min_value=1, max_value=100000))
    denom = denomination if denomination is not None else draw(st.sampled_from(DENOMINATIONS))
    pwr = power_text if power_text is not None else draw(st.sampled_from(ACTIVATABLE_POWER_LIST))
    return CardInstance(
        card_id=cid,
        card_name=f"Tribble_{cid}",
        denomination=denom,
        power_text=pwr.capitalize(),
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
def draw_deck_strategy(draw, min_size=1, max_size=15, id_offset=500):
    """Generate a draw deck of cards with unique card_ids."""
    size = draw(st.integers(min_value=min_size, max_value=max_size))
    cards = []
    for i in range(size):
        card = draw(card_strategy(card_id=id_offset + i))
        cards.append(card)
    return cards


@st.composite
def discard_pile_strategy(draw, min_size=1, max_size=5, id_offset=800):
    """Generate a discard pile of cards with unique card_ids."""
    size = draw(st.integers(min_value=min_size, max_value=max_size))
    cards = []
    for i in range(size):
        card = draw(card_strategy(card_id=id_offset + i))
        cards.append(card)
    return cards


@st.composite
def game_state_with_players(draw, num_players=None, current_sequence=None):
    """Generate a game state with multiple players for power testing."""
    n_players = num_players if num_players is not None else draw(st.integers(min_value=3, max_value=6))
    seq = current_sequence if current_sequence is not None else draw(st.sampled_from(DENOMINATIONS))
    direction = draw(st.sampled_from([1, -1]))

    players = []
    for i in range(n_players):
        hand = draw(hand_strategy(min_size=1, max_size=7, id_offset=i * 1000))
        deck = draw(draw_deck_strategy(min_size=1, max_size=10, id_offset=i * 1000 + 500))
        discard = draw(discard_pile_strategy(min_size=0, max_size=3, id_offset=i * 1000 + 800))
        player = PlayerState(
            player_id=i + 1,
            username=f"Player_{i + 1}",
            is_computer=False,
            hand=hand,
            draw_deck=deck,
            play_pile=[],
            discard_pile=discard,
            cumulative_score=0,
            is_decked=False,
            has_gone_out=False,
            seat_position=i + 1,
        )
        players.append(player)

    state = GameState(
        game_id="prop-test-powers",
        players=players,
        spectators=[],
        current_player_index=0,
        direction=direction,
        current_sequence=seq,
        last_played_denomination=None,
        sequence_broken=False,
        round_number=1,
        frozen_powers={},
        game_status="active",
        reconnection_timeout=30,
        pending_draw=None,
        pending_power=None,
    )
    return state


# --- Property 28: Power activation choice ---


class TestProperty28PowerActivationChoice:
    """Property 28: Power activation choice.

    For any card with an activatable power, when played the player should be
    prompted to activate or decline; declining should place the card without
    triggering its effect.

    **Validates: Requirements 9.1**
    """

    @given(power_name=st.sampled_from(ACTIVATABLE_POWER_LIST), data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_activatable_power_creates_prompt(self, power_name, data):
        """For any activatable power, playing the card creates a pending power prompt."""
        state = data.draw(game_state_with_players())
        resolver = PowerResolver()
        card = CardInstance(
            card_id=99999,
            card_name=f"Test_{power_name}",
            denomination=data.draw(st.sampled_from(DENOMINATIONS)),
            power_text=power_name.capitalize(),
            expansion_id=1,
        )

        events = resolver.create_power_prompt(state, 0, card)

        assert events is not None
        assert len(events) == 1
        assert events[0]["type"] == "power_prompt"
        assert events[0]["prompt_type"] == "activate_or_decline"
        assert events[0]["power_name"] == power_name
        assert state.pending_power is not None
        assert state.pending_power.power_name == power_name
        assert state.pending_power.phase == "activate_or_decline"

    @given(power_name=st.sampled_from(ACTIVATABLE_POWER_LIST), data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_declining_power_does_not_trigger_effect(self, power_name, data):
        """For any activatable power, declining clears pending power without effect."""
        state = data.draw(game_state_with_players())
        resolver = PowerResolver()
        card = CardInstance(
            card_id=99998,
            card_name=f"Test_{power_name}",
            denomination=data.draw(st.sampled_from(DENOMINATIONS)),
            power_text=power_name.capitalize(),
            expansion_id=1,
        )

        # Capture state before
        direction_before = state.direction
        current_player_before = state.current_player_index
        hand_before = list(state.players[0].hand)

        resolver.create_power_prompt(state, 0, card)
        events = resolver.handle_power_choice(state, 0, {"choice": "decline"})

        assert isinstance(events, list)
        assert events[0]["type"] == "power_declined"
        assert state.pending_power is None
        # State should be unchanged
        assert state.direction == direction_before
        assert state.players[0].hand == hand_before

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_non_activatable_power_no_prompt(self, data):
        """For any non-activatable power, no prompt is created."""
        state = data.draw(game_state_with_players())
        resolver = PowerResolver()
        non_activatable = data.draw(st.sampled_from(["Clone", "Bonus", "Antidote", ""]))
        card = CardInstance(
            card_id=99997,
            card_name="NonActivatable",
            denomination=data.draw(st.sampled_from(DENOMINATIONS)),
            power_text=non_activatable,
            expansion_id=1,
        )

        events = resolver.create_power_prompt(state, 0, card)

        assert events is None
        assert state.pending_power is None


# --- Property 29: Discard power effect ---


class TestProperty29DiscardPowerEffect:
    """Property 29: Discard power effect.

    For any Discard power activation and any card chosen from hand, that card
    should move from the player's hand to their discard pile, and hand size
    should decrease by one.

    **Validates: Requirements 9.2**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_discard_moves_chosen_card_to_discard_pile(self, data):
        """For any Discard activation, the chosen card moves from hand to discard pile."""
        state = data.draw(game_state_with_players())
        resolver = PowerResolver()
        player = state.players[0]
        assume(len(player.hand) >= 1)

        # Pick a random card from hand to discard
        card_index = data.draw(st.integers(min_value=0, max_value=len(player.hand) - 1))
        chosen_card = player.hand[card_index]
        chosen_card_id = chosen_card.card_id

        hand_size_before = len(player.hand)
        discard_size_before = len(player.discard_pile)

        # Create and activate discard power
        power_card = CardInstance(
            card_id=99990,
            card_name="Discard_Power",
            denomination=100,
            power_text="Discard",
            expansion_id=1,
        )
        resolver.create_power_prompt(state, 0, power_card)
        resolver.handle_power_choice(state, 0, {"choice": "activate"})

        # Choose the card to discard
        events = resolver.handle_power_choice(state, 0, {"card_id": chosen_card_id})

        assert isinstance(events, list)
        assert events[0]["type"] == "power_activated"
        assert events[0]["power_name"] == "discard"
        assert len(player.hand) == hand_size_before - 1
        assert len(player.discard_pile) == discard_size_before + 1
        # The chosen card is now in discard pile
        discard_ids = [c.card_id for c in player.discard_pile]
        assert chosen_card_id in discard_ids
        # The chosen card is no longer in hand
        hand_ids = [c.card_id for c in player.hand]
        assert chosen_card_id not in hand_ids


# --- Property 30: Go power grants additional turn ---


class TestProperty30GoPowerGrantsAdditionalTurn:
    """Property 30: Go power grants additional turn.

    For any Go power activation, the active player should remain the active
    player for the next action with the sequence advanced.

    **Validates: Requirements 9.3**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_go_keeps_active_player(self, data):
        """For any Go activation, the active player remains active."""
        state = data.draw(game_state_with_players())
        resolver = PowerResolver()
        player_index = 0

        power_card = CardInstance(
            card_id=99980,
            card_name="Go_Power",
            denomination=data.draw(st.sampled_from(DENOMINATIONS)),
            power_text="Go",
            expansion_id=1,
        )
        resolver.create_power_prompt(state, player_index, power_card)

        # Simulate that the turn was already advanced (as the engine does after playing)
        state.current_player_index = (player_index + state.direction) % len(state.players)

        events = resolver.handle_power_choice(state, player_index, {"choice": "activate"})

        assert isinstance(events, list)
        assert events[0]["type"] == "power_activated"
        assert events[0]["power_name"] == "go"
        assert events[0]["effect"] == "additional_turn"
        # The original player should be active again
        assert state.current_player_index == player_index


# --- Property 31: Skip power skips next player ---


class TestProperty31SkipPowerSkipsNextPlayer:
    """Property 31: Skip power skips next player.

    For any Skip power activation, the next player in the current direction
    should be skipped and the turn should pass to the player after them.

    **Validates: Requirements 9.4**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_skip_advances_past_next_player(self, data):
        """For any Skip activation, the next player is skipped."""
        num_players = data.draw(st.integers(min_value=3, max_value=6))
        state = data.draw(game_state_with_players(num_players=num_players))
        resolver = PowerResolver()
        player_index = 0

        # Set current_player_index to simulate post-play state
        state.current_player_index = player_index

        power_card = CardInstance(
            card_id=99970,
            card_name="Skip_Power",
            denomination=data.draw(st.sampled_from(DENOMINATIONS)),
            power_text="Skip",
            expansion_id=1,
        )
        resolver.create_power_prompt(state, player_index, power_card)

        direction = state.direction
        # The next player in direction (the one who should be skipped)
        expected_skipped = (state.current_player_index + direction) % num_players
        # The player after the skipped one
        expected_next = (expected_skipped + direction) % num_players

        events = resolver.handle_power_choice(state, player_index, {"choice": "activate"})

        assert isinstance(events, list)
        assert events[0]["type"] == "power_activated"
        assert events[0]["power_name"] == "skip"
        assert events[0]["skipped_player_id"] == state.players[expected_skipped].player_id
        assert state.current_player_index == expected_next


# --- Property 32: Poison power scores from opponent's draw deck ---


class TestProperty32PoisonPowerScoresFromOpponent:
    """Property 32: Poison power scores from opponent's draw deck.

    For any Poison power activation targeting a player with at least one card
    in their draw deck, the top card of that player's draw deck should be
    discarded and the active player should gain points equal to that card's
    denomination.

    **Validates: Requirements 9.5**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_poison_discards_top_card_and_scores(self, data):
        """For any Poison activation, top card of target's deck is discarded and points scored."""
        state = data.draw(game_state_with_players(num_players=data.draw(st.integers(min_value=3, max_value=6))))
        resolver = PowerResolver()
        player_index = 0
        player = state.players[player_index]

        # Pick a valid target (not self, with cards in draw deck)
        valid_targets = [
            i for i in range(len(state.players))
            if i != player_index and len(state.players[i].draw_deck) > 0
        ]
        assume(len(valid_targets) > 0)
        target_index = data.draw(st.sampled_from(valid_targets))
        target = state.players[target_index]

        top_card = target.draw_deck[0]
        expected_points = top_card.denomination
        score_before = player.cumulative_score
        target_deck_size_before = len(target.draw_deck)
        target_discard_size_before = len(target.discard_pile)

        power_card = CardInstance(
            card_id=99960,
            card_name="Poison_Power",
            denomination=100,
            power_text="Poison",
            expansion_id=1,
        )
        resolver.create_power_prompt(state, player_index, power_card)
        # Activate
        resolver.handle_power_choice(state, player_index, {"choice": "activate"})
        # Choose target
        events = resolver.handle_power_choice(
            state, player_index, {"target_player_index": target_index}
        )

        assert isinstance(events, list)
        assert events[0]["type"] == "power_activated"
        assert events[0]["power_name"] == "poison"
        assert events[0]["points_scored"] == expected_points
        # Target's draw deck lost one card
        assert len(target.draw_deck) == target_deck_size_before - 1
        # Top card moved to target's discard pile
        assert len(target.discard_pile) == target_discard_size_before + 1
        assert target.discard_pile[-1].card_id == top_card.card_id
        # Active player scored
        assert player.cumulative_score == score_before + expected_points


# --- Property 33: Rescue power recovers from discard pile ---


class TestProperty33RescuePowerRecoversFromDiscard:
    """Property 33: Rescue power recovers from discard pile.

    For any Rescue power activation and any card chosen from the player's discard
    pile, that card should either be placed face-down on top of the draw deck, or
    if its denomination matches the current sequence, be playable immediately.

    **Validates: Requirements 9.6**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_rescue_places_card_on_draw_deck(self, data):
        """For any Rescue activation declining immediate play, card goes to top of draw deck."""
        state = data.draw(game_state_with_players())
        resolver = PowerResolver()
        player = state.players[0]

        # Ensure player has at least one card in discard pile
        assume(len(player.discard_pile) >= 1)

        # Pick a card from discard pile
        card_index = data.draw(st.integers(min_value=0, max_value=len(player.discard_pile) - 1))
        chosen_card = player.discard_pile[card_index]
        chosen_card_id = chosen_card.card_id

        discard_size_before = len(player.discard_pile)
        draw_deck_size_before = len(player.draw_deck)

        power_card = CardInstance(
            card_id=99950,
            card_name="Rescue_Power",
            denomination=100,
            power_text="Rescue",
            expansion_id=1,
        )
        resolver.create_power_prompt(state, 0, power_card)
        resolver.handle_power_choice(state, 0, {"choice": "activate"})

        # Choose card, don't play immediately
        events = resolver.handle_power_choice(
            state, 0, {"card_id": chosen_card_id, "play_immediately": False}
        )

        assert isinstance(events, list)
        assert events[0]["type"] == "power_activated"
        assert events[0]["power_name"] == "rescue"
        assert events[0]["action"] == "placed_on_draw_deck"
        # Card removed from discard pile
        assert len(player.discard_pile) == discard_size_before - 1
        # Card placed on top of draw deck
        assert len(player.draw_deck) == draw_deck_size_before + 1
        assert player.draw_deck[0].card_id == chosen_card_id

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_rescue_plays_immediately_when_matching_sequence(self, data):
        """For any Rescue activation where card matches sequence, it can be played immediately."""
        seq = data.draw(st.sampled_from(DENOMINATIONS))
        state = data.draw(game_state_with_players(current_sequence=seq))
        resolver = PowerResolver()
        player = state.players[0]

        # Add a card matching the current sequence to the discard pile
        matching_card = CardInstance(
            card_id=99940,
            card_name="Matching_Rescue",
            denomination=seq,
            power_text="Go",
            expansion_id=1,
        )
        player.discard_pile.append(matching_card)

        discard_size_before = len(player.discard_pile)
        play_pile_size_before = len(player.play_pile)

        power_card = CardInstance(
            card_id=99941,
            card_name="Rescue_Power",
            denomination=100,
            power_text="Rescue",
            expansion_id=1,
        )
        resolver.create_power_prompt(state, 0, power_card)
        resolver.handle_power_choice(state, 0, {"choice": "activate"})

        # Choose card and play immediately
        events = resolver.handle_power_choice(
            state, 0, {"card_id": 99940, "play_immediately": True}
        )

        assert isinstance(events, list)
        assert events[0]["type"] == "power_activated"
        assert events[0]["power_name"] == "rescue"
        assert events[0]["action"] == "played_immediately"
        # Card removed from discard pile
        assert len(player.discard_pile) == discard_size_before - 1
        # Card placed on play pile
        assert len(player.play_pile) == play_pile_size_before + 1
        assert player.play_pile[-1].card_id == 99940
        # Sequence advanced
        seq_idx = SEQUENCE_CYCLE.index(seq)
        expected_next_seq = SEQUENCE_CYCLE[(seq_idx + 1) % len(SEQUENCE_CYCLE)]
        assert state.current_sequence == expected_next_seq


# --- Property 34: Reverse power toggles direction (idempotent pair) ---


class TestProperty34ReversePowerTogglesDirection:
    """Property 34: Reverse power toggles direction (idempotent pair).

    For any game state, activating Reverse should toggle the direction;
    activating Reverse twice should restore the original direction.

    **Validates: Requirements 9.7**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_reverse_toggles_direction(self, data):
        """For any game state, Reverse toggles the direction."""
        state = data.draw(game_state_with_players())
        resolver = PowerResolver()
        direction_before = state.direction

        power_card = CardInstance(
            card_id=99930,
            card_name="Reverse_Power",
            denomination=data.draw(st.sampled_from(DENOMINATIONS)),
            power_text="Reverse",
            expansion_id=1,
        )
        resolver.create_power_prompt(state, 0, power_card)
        events = resolver.handle_power_choice(state, 0, {"choice": "activate"})

        assert isinstance(events, list)
        assert events[0]["type"] == "power_activated"
        assert events[0]["power_name"] == "reverse"
        assert state.direction == -direction_before

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_reverse_twice_restores_original_direction(self, data):
        """For any game state, activating Reverse twice restores the original direction."""
        state = data.draw(game_state_with_players())
        resolver = PowerResolver()
        direction_before = state.direction

        # First reverse
        card1 = CardInstance(
            card_id=99920,
            card_name="Reverse_1",
            denomination=data.draw(st.sampled_from(DENOMINATIONS)),
            power_text="Reverse",
            expansion_id=1,
        )
        resolver.create_power_prompt(state, 0, card1)
        resolver.handle_power_choice(state, 0, {"choice": "activate"})
        assert state.direction == -direction_before

        # Second reverse
        card2 = CardInstance(
            card_id=99921,
            card_name="Reverse_2",
            denomination=data.draw(st.sampled_from(DENOMINATIONS)),
            power_text="Reverse",
            expansion_id=1,
        )
        resolver.create_power_prompt(state, 0, card2)
        resolver.handle_power_choice(state, 0, {"choice": "activate"})
        assert state.direction == direction_before
