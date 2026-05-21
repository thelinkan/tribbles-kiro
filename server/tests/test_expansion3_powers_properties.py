"""Property-based tests for Expansion 3 (More Tribbles More Troubles) powers.

Uses Hypothesis to verify power activation and effect properties across
randomly generated game states and card configurations.

Properties 36-43: Expansion 3 power effects
- Property 36: Antidote reverses Poison scoring
- Property 37: Copy power applies target's top play pile card effect
- Property 38: Cycle preserves hand size
- Property 39: Draw power increases target's hand
- Property 40: Exchange swaps hand card with discard card
- Property 41: Kill removes top of target's play pile
- Property 42: Recycle merges discard into draw deck
- Property 43: Score power delayed scoring

**Validates: Requirements 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.9**
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from models import CardInstance, GameState, PendingPower, PlayerState
from game.powers.resolver import PowerResolver
from scoring.service import ScoreService


DENOMINATIONS = [1, 10, 100, 1000, 10000, 100000]
NON_QUADRUPLE_POWERS = ["go", "skip", "reverse", "discard", "poison", "rescue",
                        "copy", "cycle", "draw", "exchange", "kill", "recycle",
                        "replay", "score"]


# --- Strategies ---


@st.composite
def card_strategy(draw, card_id=None, denomination=None, power_text=None):
    """Generate a random CardInstance."""
    cid = card_id if card_id is not None else draw(st.integers(min_value=1, max_value=100000))
    denom = denomination if denomination is not None else draw(st.sampled_from(DENOMINATIONS))
    pwr = power_text if power_text is not None else draw(st.sampled_from(NON_QUADRUPLE_POWERS))
    return CardInstance(
        card_id=cid,
        card_name=f"Tribble_{cid}",
        denomination=denom,
        power_text=pwr.capitalize(),
        expansion_id=3,
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
def play_pile_strategy(draw, min_size=1, max_size=5, id_offset=300):
    """Generate a play pile of cards with unique card_ids."""
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
        game_id="prop-test-exp3",
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


# --- Property 36: Antidote reverses Poison scoring ---


class TestProperty36AntidoteReversesPoisonScoring:
    """Property 36: Antidote reverses Poison scoring.

    For any Poison targeting a player whose top draw deck card has the Antidote
    power, the targeted player should score points equal to that card's denomination
    (instead of the Poison player), and should be allowed to place their hand
    beneath their draw deck.

    **Validates: Requirements 11.1**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_antidote_target_scores_instead_of_poison_player(self, data):
        """When target's top draw card has Antidote, target scores instead of Poison player."""
        state = data.draw(game_state_with_players(num_players=data.draw(st.integers(min_value=3, max_value=6))))
        resolver = PowerResolver()
        player_index = 0
        player = state.players[player_index]

        # Pick a valid target (not self)
        valid_targets = [i for i in range(len(state.players)) if i != player_index]
        target_index = data.draw(st.sampled_from(valid_targets))
        target = state.players[target_index]

        # Set up target's top draw deck card as Antidote
        antidote_denom = data.draw(st.sampled_from(DENOMINATIONS))
        antidote_card = CardInstance(
            card_id=99000,
            card_name="Antidote_Card",
            denomination=antidote_denom,
            power_text="Antidote",
            expansion_id=3,
        )
        target.draw_deck.insert(0, antidote_card)

        player_score_before = player.cumulative_score
        target_score_before = target.cumulative_score

        # Activate Poison
        power_card = CardInstance(
            card_id=99001,
            card_name="Poison_Power",
            denomination=100,
            power_text="Poison",
            expansion_id=1,
        )
        resolver.create_power_prompt(state, player_index, power_card)
        resolver.handle_power_choice(state, player_index, {"choice": "activate"})
        events = resolver.handle_power_choice(
            state, player_index, {"target_player_index": target_index}
        )

        assert isinstance(events, list)
        assert events[0]["antidote_triggered"] is True
        # Target scored the antidote card's denomination
        assert target.cumulative_score == target_score_before + antidote_denom
        # Poison player did NOT score
        assert player.cumulative_score == player_score_before

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_antidote_places_hand_beneath_draw_deck(self, data):
        """When Antidote triggers, target's hand is placed beneath their draw deck."""
        state = data.draw(game_state_with_players(num_players=data.draw(st.integers(min_value=3, max_value=6))))
        resolver = PowerResolver()
        player_index = 0

        # Pick a valid target (not self)
        valid_targets = [i for i in range(len(state.players)) if i != player_index]
        target_index = data.draw(st.sampled_from(valid_targets))
        target = state.players[target_index]

        # Set up target's top draw deck card as Antidote
        antidote_card = CardInstance(
            card_id=99100,
            card_name="Antidote_Card",
            denomination=data.draw(st.sampled_from(DENOMINATIONS)),
            power_text="Antidote",
            expansion_id=3,
        )
        target.draw_deck.insert(0, antidote_card)

        hand_cards_before = list(target.hand)
        hand_size_before = len(target.hand)

        # Activate Poison
        power_card = CardInstance(
            card_id=99101,
            card_name="Poison_Power",
            denomination=100,
            power_text="Poison",
            expansion_id=1,
        )
        resolver.create_power_prompt(state, player_index, power_card)
        resolver.handle_power_choice(state, player_index, {"choice": "activate"})
        events = resolver.handle_power_choice(
            state, player_index, {"target_player_index": target_index}
        )

        assert isinstance(events, list)
        assert events[0]["antidote_triggered"] is True
        # Target's hand should be empty (placed beneath draw deck)
        assert len(target.hand) == 0
        # All former hand cards should be in the draw deck
        draw_deck_ids = {c.card_id for c in target.draw_deck}
        for card in hand_cards_before:
            assert card.card_id in draw_deck_ids


# --- Property 37: Copy power applies target's top play pile card effect ---


class TestProperty37CopyPowerAppliesTargetEffect:
    """Property 37: Copy power applies target's top play pile card effect.

    For any Copy power activation targeting another player's play pile, the effect
    should be identical to activating the power of the top card of that pile
    (subject to that power's rules), except Quadruple cannot be copied.

    **Validates: Requirements 11.2**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_copy_returns_correct_copied_power(self, data):
        """Copy returns the correct power name from the target's top play pile card."""
        state = data.draw(game_state_with_players(num_players=data.draw(st.integers(min_value=3, max_value=6))))
        resolver = PowerResolver()
        player_index = 0

        # Pick a valid target (not self)
        valid_targets = [i for i in range(len(state.players)) if i != player_index]
        target_index = data.draw(st.sampled_from(valid_targets))
        target = state.players[target_index]

        # Give target a play pile with a non-Quadruple power on top
        power_name = data.draw(st.sampled_from(NON_QUADRUPLE_POWERS))
        top_card = CardInstance(
            card_id=99200,
            card_name=f"Target_Top_{power_name}",
            denomination=data.draw(st.sampled_from(DENOMINATIONS)),
            power_text=power_name.capitalize(),
            expansion_id=3,
        )
        target.play_pile = [top_card]

        # Activate Copy
        power_card = CardInstance(
            card_id=99201,
            card_name="Copy_Power",
            denomination=100,
            power_text="Copy",
            expansion_id=3,
        )
        resolver.create_power_prompt(state, player_index, power_card)
        resolver.handle_power_choice(state, player_index, {"choice": "activate"})
        events = resolver.handle_power_choice(
            state, player_index, {"target_player_index": target_index}
        )

        assert isinstance(events, list)
        assert events[0]["type"] == "power_activated"
        assert events[0]["power_name"] == "copy"
        assert events[0]["copied_power"] == power_name
        assert events[0]["copied_card_id"] == 99200

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_copy_rejects_quadruple(self, data):
        """Copy power cannot copy the Quadruple power."""
        state = data.draw(game_state_with_players(num_players=data.draw(st.integers(min_value=3, max_value=6))))
        resolver = PowerResolver()
        player_index = 0

        # Pick a valid target (not self)
        valid_targets = [i for i in range(len(state.players)) if i != player_index]
        target_index = data.draw(st.sampled_from(valid_targets))
        target = state.players[target_index]

        # Give target a play pile with Quadruple on top
        quadruple_card = CardInstance(
            card_id=99210,
            card_name="Quadruple_Card",
            denomination=10000,
            power_text="Quadruple",
            expansion_id=4,
        )
        target.play_pile = [quadruple_card]

        # Activate Copy
        power_card = CardInstance(
            card_id=99211,
            card_name="Copy_Power",
            denomination=100,
            power_text="Copy",
            expansion_id=3,
        )
        resolver.create_power_prompt(state, player_index, power_card)
        resolver.handle_power_choice(state, player_index, {"choice": "activate"})
        result = resolver.handle_power_choice(
            state, player_index, {"target_player_index": target_index}
        )

        assert isinstance(result, tuple)
        assert result[0] == "cannot_copy_quadruple"


# --- Property 38: Cycle preserves hand size ---


class TestProperty38CyclePreservesHandSize:
    """Property 38: Cycle preserves hand size.

    For any Cycle power activation, the player's hand size should remain unchanged
    (one card placed under draw deck, one card drawn from top).

    **Validates: Requirements 11.3**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_cycle_hand_size_unchanged(self, data):
        """For any Cycle activation, hand size remains the same."""
        state = data.draw(game_state_with_players())
        resolver = PowerResolver()
        player = state.players[0]

        # Ensure player has at least 1 card in hand and 1 in draw deck
        assume(len(player.hand) >= 1)
        assume(len(player.draw_deck) >= 1)

        hand_size_before = len(player.hand)

        # Pick a random card from hand
        card_index = data.draw(st.integers(min_value=0, max_value=len(player.hand) - 1))
        chosen_card_id = player.hand[card_index].card_id

        # Activate Cycle
        power_card = CardInstance(
            card_id=99300,
            card_name="Cycle_Power",
            denomination=100,
            power_text="Cycle",
            expansion_id=3,
        )
        resolver.create_power_prompt(state, 0, power_card)
        resolver.handle_power_choice(state, 0, {"choice": "activate"})
        events = resolver.handle_power_choice(state, 0, {"card_id": chosen_card_id})

        assert isinstance(events, list)
        assert events[0]["type"] == "power_activated"
        assert events[0]["power_name"] == "cycle"
        # Hand size should be unchanged
        assert len(player.hand) == hand_size_before


# --- Property 39: Draw power increases target's hand ---


class TestProperty39DrawPowerIncreasesTargetHand:
    """Property 39: Draw power increases target's hand.

    For any Draw power activation targeting a player with cards in their draw deck,
    that player's hand should grow by 1 and their draw deck should shrink by 1.

    **Validates: Requirements 11.4**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_draw_increases_hand_decreases_deck(self, data):
        """For any Draw activation, target's hand grows by 1 and draw deck shrinks by 1."""
        state = data.draw(game_state_with_players())
        resolver = PowerResolver()
        player_index = 0

        # Pick a valid target (any player with cards in draw deck)
        valid_targets = [
            i for i in range(len(state.players))
            if len(state.players[i].draw_deck) > 0
        ]
        assume(len(valid_targets) > 0)
        target_index = data.draw(st.sampled_from(valid_targets))
        target = state.players[target_index]

        hand_size_before = len(target.hand)
        deck_size_before = len(target.draw_deck)
        top_card = target.draw_deck[0]

        # Activate Draw
        power_card = CardInstance(
            card_id=99400,
            card_name="Draw_Power",
            denomination=100,
            power_text="Draw",
            expansion_id=3,
        )
        resolver.create_power_prompt(state, player_index, power_card)
        resolver.handle_power_choice(state, player_index, {"choice": "activate"})
        events = resolver.handle_power_choice(
            state, player_index, {"target_player_index": target_index}
        )

        assert isinstance(events, list)
        assert events[0]["type"] == "power_activated"
        assert events[0]["power_name"] == "draw"
        # Target's hand grew by 1
        assert len(target.hand) == hand_size_before + 1
        # Target's draw deck shrunk by 1
        assert len(target.draw_deck) == deck_size_before - 1
        # The drawn card is the former top card
        assert top_card in target.hand


# --- Property 40: Exchange swaps hand card with discard card ---


class TestProperty40ExchangeSwapsCards:
    """Property 40: Exchange swaps hand card with discard card.

    For any Exchange power activation, the player's hand size should remain unchanged,
    the discarded card should appear in the discard pile, and the taken card should
    appear in hand.

    **Validates: Requirements 11.5**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_exchange_preserves_hand_size_and_swaps(self, data):
        """For any Exchange activation, hand size is unchanged and cards are swapped."""
        state = data.draw(game_state_with_players())
        resolver = PowerResolver()
        player = state.players[0]

        # Ensure player has at least 1 card in hand and 1 in discard pile
        assume(len(player.hand) >= 1)
        assume(len(player.discard_pile) >= 1)

        hand_size_before = len(player.hand)

        # Pick a random card from hand to discard
        hand_idx = data.draw(st.integers(min_value=0, max_value=len(player.hand) - 1))
        discard_card = player.hand[hand_idx]
        discard_card_id = discard_card.card_id

        # Pick a random card from discard pile to take
        discard_idx = data.draw(st.integers(min_value=0, max_value=len(player.discard_pile) - 1))
        take_card = player.discard_pile[discard_idx]
        take_card_id = take_card.card_id

        # Activate Exchange
        power_card = CardInstance(
            card_id=99500,
            card_name="Exchange_Power",
            denomination=100,
            power_text="Exchange",
            expansion_id=3,
        )
        resolver.create_power_prompt(state, 0, power_card)
        resolver.handle_power_choice(state, 0, {"choice": "activate"})
        events = resolver.handle_power_choice(
            state, 0, {"card_id": discard_card_id, "take_card_id": take_card_id}
        )

        assert isinstance(events, list)
        assert events[0]["type"] == "power_activated"
        assert events[0]["power_name"] == "exchange"
        # Hand size unchanged
        assert len(player.hand) == hand_size_before
        # The discarded card is now in discard pile
        discard_ids = [c.card_id for c in player.discard_pile]
        assert discard_card_id in discard_ids
        # The taken card is now in hand
        hand_ids = [c.card_id for c in player.hand]
        assert take_card_id in hand_ids
        # The discarded card is NOT in hand
        assert discard_card_id not in hand_ids


# --- Property 41: Kill removes top of target's play pile ---


class TestProperty41KillRemovesTopOfPlayPile:
    """Property 41: Kill removes top of target's play pile.

    For any Kill power activation targeting a player with cards in their play pile,
    the top card should move from their play pile to their discard pile.

    **Validates: Requirements 11.6**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_kill_moves_top_card_to_discard(self, data):
        """For any Kill activation, top card of target's play pile moves to discard."""
        state = data.draw(game_state_with_players())
        resolver = PowerResolver()
        player_index = 0

        # Give at least one player a non-empty play pile
        target_index = data.draw(st.integers(min_value=0, max_value=len(state.players) - 1))
        target = state.players[target_index]

        # Add cards to target's play pile
        play_pile_cards = data.draw(play_pile_strategy(min_size=1, max_size=5, id_offset=99600))
        target.play_pile = play_pile_cards

        top_card = target.play_pile[-1]
        play_pile_size_before = len(target.play_pile)
        discard_size_before = len(target.discard_pile)

        # Activate Kill
        power_card = CardInstance(
            card_id=99601,
            card_name="Kill_Power",
            denomination=100,
            power_text="Kill",
            expansion_id=3,
        )
        resolver.create_power_prompt(state, player_index, power_card)
        resolver.handle_power_choice(state, player_index, {"choice": "activate"})
        events = resolver.handle_power_choice(
            state, player_index, {"target_player_index": target_index}
        )

        assert isinstance(events, list)
        assert events[0]["type"] == "power_activated"
        assert events[0]["power_name"] == "kill"
        assert events[0]["killed_card_id"] == top_card.card_id
        # Play pile lost one card
        assert len(target.play_pile) == play_pile_size_before - 1
        # Discard pile gained one card
        assert len(target.discard_pile) == discard_size_before + 1
        # The top card is now in discard pile
        assert target.discard_pile[-1].card_id == top_card.card_id


# --- Property 42: Recycle merges discard into draw deck ---


class TestProperty42RecycleMergesDiscardIntoDeck:
    """Property 42: Recycle merges discard into draw deck.

    For any Recycle power activation targeting a player, that player's discard pile
    should become empty and all former discard cards should be in their draw deck.

    **Validates: Requirements 11.7**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_recycle_empties_discard_into_draw_deck(self, data):
        """For any Recycle activation, discard pile empties and cards move to draw deck."""
        state = data.draw(game_state_with_players())
        resolver = PowerResolver()
        player_index = 0

        # Pick a target with cards in discard pile
        valid_targets = [
            i for i in range(len(state.players))
            if len(state.players[i].discard_pile) > 0
        ]
        assume(len(valid_targets) > 0)
        target_index = data.draw(st.sampled_from(valid_targets))
        target = state.players[target_index]

        discard_card_ids = {c.card_id for c in target.discard_pile}
        draw_deck_size_before = len(target.draw_deck)
        discard_size_before = len(target.discard_pile)

        # Activate Recycle
        power_card = CardInstance(
            card_id=99700,
            card_name="Recycle_Power",
            denomination=100,
            power_text="Recycle",
            expansion_id=3,
        )
        resolver.create_power_prompt(state, player_index, power_card)
        resolver.handle_power_choice(state, player_index, {"choice": "activate"})
        events = resolver.handle_power_choice(
            state, player_index, {"target_player_index": target_index}
        )

        assert isinstance(events, list)
        assert events[0]["type"] == "power_activated"
        assert events[0]["power_name"] == "recycle"
        # Discard pile should be empty
        assert len(target.discard_pile) == 0
        # Draw deck should contain all former discard cards plus original draw cards
        assert len(target.draw_deck) == draw_deck_size_before + discard_size_before
        draw_deck_ids = {c.card_id for c in target.draw_deck}
        for card_id in discard_card_ids:
            assert card_id in draw_deck_ids


# --- Property 43: Score power delayed scoring ---


class TestProperty43ScorePowerDelayedScoring:
    """Property 43: Score power delayed scoring.

    For any Score power activation targeting a player, if that player plays a card
    on their next turn, the Score activator should gain points equal to that card's
    denomination. For this property test, we verify that score_target_by is set
    correctly on the target player.

    **Validates: Requirements 11.9**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_score_sets_target_by_on_target(self, data):
        """For any Score activation, target's score_target_by is set to activator's player_id."""
        state = data.draw(game_state_with_players(num_players=data.draw(st.integers(min_value=3, max_value=6))))
        resolver = PowerResolver()
        player_index = 0
        player = state.players[player_index]

        # Pick a valid target (not self)
        valid_targets = [i for i in range(len(state.players)) if i != player_index]
        target_index = data.draw(st.sampled_from(valid_targets))
        target = state.players[target_index]

        # Ensure score_target_by is initially None
        assert target.score_target_by is None

        # Activate Score
        power_card = CardInstance(
            card_id=99800,
            card_name="Score_Power",
            denomination=100,
            power_text="Score",
            expansion_id=3,
        )
        resolver.create_power_prompt(state, player_index, power_card)
        resolver.handle_power_choice(state, player_index, {"choice": "activate"})
        events = resolver.handle_power_choice(
            state, player_index, {"target_player_index": target_index}
        )

        assert isinstance(events, list)
        assert events[0]["type"] == "power_activated"
        assert events[0]["power_name"] == "score"
        # score_target_by should be set to the activator's player_id
        assert target.score_target_by == player.player_id
