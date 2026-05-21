"""Property-based tests for Expansion 5 (Trials and Tribble-ations) powers.

Uses Hypothesis to verify power activation and effect properties across
randomly generated game states and card configurations.

Properties 54-57: Expansion 5 power effects
- Property 54: Avalanche conditional discard
- Property 55: Famine resets sequence to 1
- Property 56: Stampede allows all to play, only active power triggers
- Property 57: Time Warp reduces next round hand size

**Validates: Requirements 13.1, 13.2, 13.3, 13.4**
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from models import CardInstance, GameState, PendingPower, PlayerState
from game.powers.resolver import PowerResolver
from game.round_manager import RoundManager


DENOMINATIONS = [1, 10, 100, 1000, 10000, 100000]
SIMPLE_POWERS = ["go", "skip", "reverse", "discard", "poison", "rescue",
                 "copy", "cycle", "draw", "exchange", "kill", "recycle",
                 "replay", "score", "battle", "evolve", "freeze", "mutate",
                 "process", "toxin", "avalanche", "famine", "stampede"]


# --- Strategies ---


@st.composite
def card_strategy(draw, card_id=None, denomination=None, power_text=None):
    """Generate a random CardInstance."""
    cid = card_id if card_id is not None else draw(st.integers(min_value=1, max_value=100000))
    denom = denomination if denomination is not None else draw(st.sampled_from(DENOMINATIONS))
    pwr = power_text if power_text is not None else draw(st.sampled_from(SIMPLE_POWERS))
    return CardInstance(
        card_id=cid,
        card_name=f"Tribble_{cid}",
        denomination=denom,
        power_text=pwr.capitalize(),
        expansion_id=5,
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
def game_state_with_players(draw, num_players=None, current_sequence=None):
    """Generate a game state with multiple players for power testing."""
    n_players = num_players if num_players is not None else draw(st.integers(min_value=3, max_value=6))
    seq = current_sequence if current_sequence is not None else draw(st.sampled_from(DENOMINATIONS))
    direction = draw(st.sampled_from([1, -1]))

    players = []
    for i in range(n_players):
        hand = draw(hand_strategy(min_size=1, max_size=7, id_offset=i * 1000))
        deck = draw(draw_deck_strategy(min_size=1, max_size=10, id_offset=i * 1000 + 500))
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

    state = GameState(
        game_id="prop-test-exp5",
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


# --- Property 54: Avalanche conditional discard ---


class TestProperty54AvalancheConditionalDiscard:
    """Property 54: Avalanche conditional discard.

    For any Avalanche power activation where the active player has at least 4
    other cards in hand after playing, all players' hands should decrease by 1
    card (to discard), and the active player should discard one additional card.

    **Validates: Requirements 13.1**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_avalanche_all_players_lose_one_card_when_condition_met(self, data):
        """When active player has >= 4 cards, all players discard one card."""
        state = data.draw(game_state_with_players())
        resolver = PowerResolver()
        player_index = 0
        player = state.players[player_index]

        # Ensure active player has at least 4 cards in hand (condition for avalanche)
        while len(player.hand) < 4:
            player.hand.append(data.draw(card_strategy(
                card_id=data.draw(st.integers(min_value=90000, max_value=99999))
            )))

        # Ensure all other players have at least 1 card in hand
        for i, p in enumerate(state.players):
            if i != player_index and len(p.hand) == 0:
                p.hand.append(data.draw(card_strategy(
                    card_id=data.draw(st.integers(min_value=80000, max_value=89999))
                )))

        # Record hand sizes before
        hand_sizes_before = [len(p.hand) for p in state.players]

        # Activate Avalanche
        power_card = CardInstance(
            card_id=99900, card_name="Avalanche_Power", denomination=100,
            power_text="Avalanche", expansion_id=5,
        )
        resolver.create_power_prompt(state, player_index, power_card)
        events = resolver.handle_power_choice(state, player_index, {"choice": "activate"})

        assert isinstance(events, list)

        # All players should have lost exactly 1 card from hand (auto-discard)
        for i, p in enumerate(state.players):
            if hand_sizes_before[i] > 0:
                assert len(p.hand) == hand_sizes_before[i] - 1
                assert len(p.discard_pile) == 1

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_avalanche_active_player_discards_additional(self, data):
        """Active player discards one additional card after all-player discard."""
        state = data.draw(game_state_with_players())
        resolver = PowerResolver()
        player_index = 0
        player = state.players[player_index]

        # Ensure active player has at least 5 cards (4 for condition + 1 for additional)
        while len(player.hand) < 5:
            player.hand.append(data.draw(card_strategy(
                card_id=data.draw(st.integers(min_value=90000, max_value=99999))
            )))

        hand_size_before = len(player.hand)

        # Activate Avalanche
        power_card = CardInstance(
            card_id=99900, card_name="Avalanche_Power", denomination=100,
            power_text="Avalanche", expansion_id=5,
        )
        resolver.create_power_prompt(state, player_index, power_card)
        events = resolver.handle_power_choice(state, player_index, {"choice": "activate"})

        assert isinstance(events, list)
        # After auto-discard, player has hand_size_before - 1 cards
        # Now choose additional card to discard
        assume(len(player.hand) >= 1)
        additional_card_id = player.hand[0].card_id

        events = resolver.handle_power_choice(
            state, player_index, {"card_id": additional_card_id}
        )

        assert isinstance(events, list)
        assert events[0]["type"] == "power_activated"
        assert events[0]["power_name"] == "avalanche"
        assert events[0]["effect"] == "all_discarded_plus_additional"
        # Active player lost 2 total (1 auto + 1 additional)
        assert len(player.hand) == hand_size_before - 2



# --- Property 55: Famine resets sequence to 1 ---


class TestProperty55FamineResetsSequenceTo1:
    """Property 55: Famine resets sequence to 1.

    For any Famine power activation, the next expected sequence denomination
    should be 1 regardless of the current sequence position.

    **Validates: Requirements 13.2**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_famine_always_resets_sequence_to_1(self, data):
        """For any current sequence value, Famine sets it to 1."""
        current_seq = data.draw(st.sampled_from(DENOMINATIONS))
        state = data.draw(game_state_with_players(current_sequence=current_seq))
        resolver = PowerResolver()

        # Activate Famine
        power_card = CardInstance(
            card_id=99910, card_name="Famine_Power", denomination=current_seq,
            power_text="Famine", expansion_id=5,
        )
        resolver.create_power_prompt(state, 0, power_card)
        events = resolver.handle_power_choice(state, 0, {"choice": "activate"})

        assert isinstance(events, list)
        assert events[0]["type"] == "power_activated"
        assert events[0]["power_name"] == "famine"
        assert events[0]["new_sequence"] == 1
        assert state.current_sequence == 1


# --- Property 56: Stampede allows all to play, only active power triggers ---


class TestProperty56StampedeAllPlayOnlyActivePowerTriggers:
    """Property 56: Stampede allows all to play, only active power triggers.

    For any Stampede power activation, all players who play a card of the current
    sequence denomination should have it placed on their play pile, but only the
    active player's card power should be noted for activation.

    **Validates: Requirements 13.3**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_stampede_matching_cards_move_to_play_pile(self, data):
        """All players with matching denomination cards have them placed on play pile."""
        current_seq = data.draw(st.sampled_from(DENOMINATIONS))
        num_players = data.draw(st.integers(min_value=3, max_value=6))
        state = data.draw(game_state_with_players(
            num_players=num_players, current_sequence=current_seq
        ))
        resolver = PowerResolver()
        player_index = 0

        # Give some players matching cards
        players_with_match = data.draw(st.lists(
            st.integers(min_value=0, max_value=num_players - 1),
            min_size=1, max_size=num_players,
            unique=True,
        ))

        for pidx in players_with_match:
            matching_card = CardInstance(
                card_id=70000 + pidx,
                card_name=f"Match_{pidx}",
                denomination=current_seq,
                power_text="Go",
                expansion_id=5,
            )
            state.players[pidx].hand.insert(0, matching_card)

        # Record play pile sizes before
        play_pile_before = [len(p.play_pile) for p in state.players]

        # Activate Stampede
        power_card = CardInstance(
            card_id=99920, card_name="Stampede_Power", denomination=100,
            power_text="Stampede", expansion_id=5,
        )
        resolver.create_power_prompt(state, player_index, power_card)
        events = resolver.handle_power_choice(state, player_index, {"choice": "activate"})

        assert isinstance(events, list)

        # All non-decked players with matching cards should have them in play pile
        for pidx in players_with_match:
            if not state.players[pidx].is_decked:
                assert len(state.players[pidx].play_pile) == play_pile_before[pidx] + 1
                # The matching card should be in the play pile
                pile_ids = [c.card_id for c in state.players[pidx].play_pile]
                assert 70000 + pidx in pile_ids

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_stampede_only_active_player_power_noted(self, data):
        """Only the active player's card power is noted for activation."""
        current_seq = data.draw(st.sampled_from(DENOMINATIONS))
        state = data.draw(game_state_with_players(
            num_players=data.draw(st.integers(min_value=3, max_value=5)),
            current_sequence=current_seq,
        ))
        resolver = PowerResolver()
        player_index = 0

        # Give active player a matching card with a specific power
        active_power = data.draw(st.sampled_from(["go", "skip", "reverse", "discard"]))
        active_card = CardInstance(
            card_id=70000,
            card_name="Active_Match",
            denomination=current_seq,
            power_text=active_power.capitalize(),
            expansion_id=5,
        )
        state.players[player_index].hand.insert(0, active_card)

        # Give another player a matching card with a different power
        other_index = 1
        other_card = CardInstance(
            card_id=70001,
            card_name="Other_Match",
            denomination=current_seq,
            power_text="Poison",
            expansion_id=5,
        )
        state.players[other_index].hand.insert(0, other_card)

        # Activate Stampede
        power_card = CardInstance(
            card_id=99920, card_name="Stampede_Power", denomination=100,
            power_text="Stampede", expansion_id=5,
        )
        resolver.create_power_prompt(state, player_index, power_card)
        events = resolver.handle_power_choice(state, player_index, {"choice": "activate"})

        assert isinstance(events, list)
        # Find the main power_activated event
        activated = [e for e in events if e.get("type") == "power_activated"]
        assert len(activated) == 1
        # Only the active player's card power should be noted
        assert activated[0]["active_player_card_power"] == active_power



# --- Property 57: Time Warp reduces next round hand size ---


class TestProperty57TimeWarpReducesNextRoundHandSize:
    """Property 57: Time Warp reduces next round hand size.

    For any player who did not go out and has Time Warp cards in their play pile
    at round end, the number of cards dealt next round should be reduced by the
    number of unique Time Warp denominations (min 1 card dealt).

    **Validates: Requirements 13.4**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_time_warp_reduces_by_unique_denomination_count(self, data):
        """Cards dealt is reduced by the number of unique Time Warp denominations."""
        # Generate 1-5 unique Time Warp denominations
        num_unique = data.draw(st.integers(min_value=1, max_value=5))
        tw_denoms = data.draw(st.lists(
            st.sampled_from(DENOMINATIONS),
            min_size=num_unique, max_size=num_unique,
            unique=True,
        ))

        # Create Time Warp cards for those denominations
        tw_cards = []
        for i, denom in enumerate(tw_denoms):
            tw_cards.append(CardInstance(
                card_id=50000 + i,
                card_name=f"TimeWarp_{denom}",
                denomination=denom,
                power_text="Time Warp",
                expansion_id=5,
            ))

        # Create a large draw deck so dealing is not limited by deck size
        draw_deck = [
            CardInstance(
                card_id=60000 + i, card_name=f"Deck_{i}",
                denomination=10, power_text="Go", expansion_id=5,
            )
            for i in range(20)
        ]

        players = [
            PlayerState(
                player_id=1, username="TWPlayer", is_computer=False,
                hand=[], draw_deck=draw_deck, play_pile=tw_cards,
                discard_pile=[], cumulative_score=0, is_decked=False,
                has_gone_out=False, seat_position=1,
            ),
            PlayerState(
                player_id=2, username="Winner", is_computer=False,
                hand=[], draw_deck=[], play_pile=[], discard_pile=[],
                cumulative_score=0, is_decked=False, has_gone_out=True,
                seat_position=2,
            ),
        ]
        state = GameState(
            game_id="prop-test-tw", players=players,
            current_player_index=0, direction=1, current_sequence=1,
        )

        round_manager = RoundManager()
        events = []

        # Track time warp reductions
        round_manager._track_time_warp_reductions(state, events)

        assert len(state.players[0].time_warp_reductions) == num_unique

        # Deal new hands
        deal_events = []
        round_manager._deal_new_hands(state, [], deal_events)

        # Expected: max(1, 7 - num_unique)
        expected_cards = max(1, 7 - num_unique)
        assert len(state.players[0].hand) == expected_cards

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_time_warp_same_denomination_does_not_stack(self, data):
        """Multiple Time Warp cards of the same denomination count as 1 reduction."""
        denom = data.draw(st.sampled_from(DENOMINATIONS))
        num_copies = data.draw(st.integers(min_value=2, max_value=4))

        # Create multiple Time Warp cards with the same denomination
        tw_cards = []
        for i in range(num_copies):
            tw_cards.append(CardInstance(
                card_id=50000 + i,
                card_name=f"TimeWarp_{i}",
                denomination=denom,
                power_text="Time Warp",
                expansion_id=5,
            ))

        draw_deck = [
            CardInstance(
                card_id=60000 + i, card_name=f"Deck_{i}",
                denomination=10, power_text="Go", expansion_id=5,
            )
            for i in range(20)
        ]

        players = [
            PlayerState(
                player_id=1, username="TWPlayer", is_computer=False,
                hand=[], draw_deck=draw_deck, play_pile=tw_cards,
                discard_pile=[], cumulative_score=0, is_decked=False,
                has_gone_out=False, seat_position=1,
            ),
            PlayerState(
                player_id=2, username="Winner", is_computer=False,
                hand=[], draw_deck=[], play_pile=[], discard_pile=[],
                cumulative_score=0, is_decked=False, has_gone_out=True,
                seat_position=2,
            ),
        ]
        state = GameState(
            game_id="prop-test-tw-stack", players=players,
            current_player_index=0, direction=1, current_sequence=1,
        )

        round_manager = RoundManager()
        events = []

        round_manager._track_time_warp_reductions(state, events)

        # Only 1 unique denomination regardless of copies
        assert len(state.players[0].time_warp_reductions) == 1

        deal_events = []
        round_manager._deal_new_hands(state, [], deal_events)

        # 7 - 1 = 6 cards dealt
        assert len(state.players[0].hand) == 6

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_time_warp_minimum_one_card_dealt(self, data):
        """Time Warp reduction cannot reduce below 1 card dealt."""
        # Use all 6 denominations to get maximum reduction
        tw_cards = [
            CardInstance(
                card_id=50000 + i, card_name=f"TimeWarp_{d}",
                denomination=d, power_text="Time Warp", expansion_id=5,
            )
            for i, d in enumerate(DENOMINATIONS)
        ]

        draw_deck = [
            CardInstance(
                card_id=60000 + i, card_name=f"Deck_{i}",
                denomination=10, power_text="Go", expansion_id=5,
            )
            for i in range(20)
        ]

        players = [
            PlayerState(
                player_id=1, username="TWPlayer", is_computer=False,
                hand=[], draw_deck=draw_deck, play_pile=tw_cards,
                discard_pile=[], cumulative_score=0, is_decked=False,
                has_gone_out=False, seat_position=1,
            ),
            PlayerState(
                player_id=2, username="Winner", is_computer=False,
                hand=[], draw_deck=[], play_pile=[], discard_pile=[],
                cumulative_score=0, is_decked=False, has_gone_out=True,
                seat_position=2,
            ),
        ]
        state = GameState(
            game_id="prop-test-tw-min", players=players,
            current_player_index=0, direction=1, current_sequence=1,
        )

        round_manager = RoundManager()
        events = []

        round_manager._track_time_warp_reductions(state, events)

        assert len(state.players[0].time_warp_reductions) == 6

        deal_events = []
        round_manager._deal_new_hands(state, [], deal_events)

        # max(1, 7 - 6) = 1
        assert len(state.players[0].hand) == 1

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_time_warp_not_applied_to_player_who_went_out(self, data):
        """Time Warp does NOT apply to players who went out."""
        denom = data.draw(st.sampled_from(DENOMINATIONS))
        tw_card = CardInstance(
            card_id=50000, card_name="TimeWarp",
            denomination=denom, power_text="Time Warp", expansion_id=5,
        )

        draw_deck = [
            CardInstance(
                card_id=60000 + i, card_name=f"Deck_{i}",
                denomination=10, power_text="Go", expansion_id=5,
            )
            for i in range(20)
        ]

        players = [
            PlayerState(
                player_id=1, username="TWPlayer", is_computer=False,
                hand=[], draw_deck=draw_deck, play_pile=[tw_card],
                discard_pile=[], cumulative_score=0, is_decked=False,
                has_gone_out=True,  # Went out — no reduction
                seat_position=1,
            ),
            PlayerState(
                player_id=2, username="Other", is_computer=False,
                hand=[], draw_deck=[], play_pile=[], discard_pile=[],
                cumulative_score=0, is_decked=False, has_gone_out=False,
                seat_position=2,
            ),
        ]
        state = GameState(
            game_id="prop-test-tw-out", players=players,
            current_player_index=0, direction=1, current_sequence=1,
        )

        round_manager = RoundManager()
        events = []

        round_manager._track_time_warp_reductions(state, events)

        # Player who went out should have no reductions
        assert len(state.players[0].time_warp_reductions) == 0

        deal_events = []
        round_manager._deal_new_hands(state, [], deal_events)

        # Normal 7 cards dealt
        assert len(state.players[0].hand) == 7
