"""Property-based tests for Expansion 4 (No Tribble at All) powers.

Uses Hypothesis to verify power activation and effect properties across
randomly generated game states and card configurations.

Properties 44-53: Expansion 4 power effects
- Property 44: Compound power activation rules
- Property 45: Battle resolution
- Property 46: Evolve preserves hand count
- Property 47: Freeze prevents playing named power
- Property 48: Mutate preserves play pile count
- Property 49: Process net hand gain
- Property 50: Quadruple scoring modifier
- Property 51: Safety end-of-round modifier
- Property 52: Tally scoring split
- Property 53: Toxin reveals cards per Discard count

**Validates: Requirements 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7, 12.8, 12.9, 12.10, 12.11, 12.12, 12.13**
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from models import CardInstance, GameState, PendingPower, PlayerState
from game.powers.resolver import ACTIVATABLE_POWERS, PowerResolver
from scoring.service import ScoreService
from game.round_manager import RoundManager


DENOMINATIONS = [1, 10, 100, 1000, 10000, 100000]
SIMPLE_POWERS = ["go", "skip", "reverse", "discard", "poison", "rescue",
                 "copy", "cycle", "draw", "exchange", "kill", "recycle",
                 "replay", "score", "battle", "evolve", "freeze", "mutate",
                 "process", "toxin"]


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
        expansion_id=4,
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
        game_id="prop-test-exp4",
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


# --- Property 44: Compound power activation rules ---


class TestProperty44CompoundPowerActivationRules:
    """Property 44: Compound power activation rules.

    For any compound power card: if neither component is Clone, both powers must
    activate together; if one component is Clone and Clone is not used, only the
    non-Clone power activates; if Clone is used, both powers must activate.

    **Validates: Requirements 12.1, 12.2, 12.3**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_compound_neither_clone_returns_both_joined(self, data):
        """For any compound power with neither component being Clone, get_activatable_power returns both joined by &."""
        resolver = PowerResolver()
        # Pick two distinct activatable powers that are not Clone
        activatable_list = sorted(ACTIVATABLE_POWERS - {"clone"})
        power1 = data.draw(st.sampled_from(activatable_list))
        power2 = data.draw(st.sampled_from(activatable_list))
        assume(power1 != power2)

        power_text = f"{power1.capitalize()} & {power2.capitalize()}"
        card = CardInstance(
            card_id=data.draw(st.integers(min_value=1, max_value=100000)),
            card_name="Compound_Card",
            denomination=data.draw(st.sampled_from(DENOMINATIONS)),
            power_text=power_text,
            expansion_id=4,
        )

        result = resolver.get_activatable_power(card)
        # Both powers must be returned joined by &
        assert result is not None
        assert "&" in result
        parts = [p.strip() for p in result.split("&")]
        assert power1 in parts
        assert power2 in parts

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_compound_with_clone_returns_non_clone_only(self, data):
        """For any compound power with Clone, get_activatable_power returns only the non-Clone component."""
        resolver = PowerResolver()
        # Pick an activatable power that is not Clone
        activatable_list = sorted(ACTIVATABLE_POWERS - {"clone"})
        other_power = data.draw(st.sampled_from(activatable_list))

        # Randomly order Clone and the other power
        if data.draw(st.booleans()):
            power_text = f"Clone & {other_power.capitalize()}"
        else:
            power_text = f"{other_power.capitalize()} & Clone"

        card = CardInstance(
            card_id=data.draw(st.integers(min_value=1, max_value=100000)),
            card_name="Clone_Compound_Card",
            denomination=data.draw(st.sampled_from(DENOMINATIONS)),
            power_text=power_text,
            expansion_id=4,
        )

        result = resolver.get_activatable_power(card)
        # Only the non-Clone power should be returned
        assert result == other_power

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_compound_clone_with_passive_returns_none(self, data):
        """For a compound power with Clone and a passive power, get_activatable_power returns None."""
        resolver = PowerResolver()
        passive_powers = ["antidote", "quadruple", "safety", "tally"]
        passive = data.draw(st.sampled_from(passive_powers))

        power_text = f"Clone & {passive.capitalize()}"
        card = CardInstance(
            card_id=data.draw(st.integers(min_value=1, max_value=100000)),
            card_name="Clone_Passive_Card",
            denomination=data.draw(st.sampled_from(DENOMINATIONS)),
            power_text=power_text,
            expansion_id=4,
        )

        result = resolver.get_activatable_power(card)
        # Clone + passive = no activatable power
        assert result is None


# --- Property 45: Battle resolution ---


class TestProperty45BattleResolution:
    """Property 45: Battle resolution.

    For any Battle power activation, both players reveal top 3 cards of their draw
    decks; the player with the higher total denomination places those 6 cards under
    their play pile, the other discards their 3 revealed cards.

    **Validates: Requirements 12.4**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_battle_winner_gets_six_cards_loser_discards_three(self, data):
        """For any Battle, winner gets 6 cards under play pile, loser discards their 3."""
        state = data.draw(game_state_with_players(num_players=data.draw(st.integers(min_value=3, max_value=6))))
        resolver = PowerResolver()
        player_index = 0
        player = state.players[player_index]

        # Pick a valid target (not self)
        valid_targets = [i for i in range(len(state.players)) if i != player_index]
        target_index = data.draw(st.sampled_from(valid_targets))
        target = state.players[target_index]

        # Ensure both have at least 3 cards in draw deck
        while len(player.draw_deck) < 3:
            player.draw_deck.append(data.draw(card_strategy(card_id=data.draw(st.integers(min_value=90000, max_value=99999)))))
        while len(target.draw_deck) < 3:
            target.draw_deck.append(data.draw(card_strategy(card_id=data.draw(st.integers(min_value=80000, max_value=89999)))))

        player_play_pile_before = len(player.play_pile)
        target_play_pile_before = len(target.play_pile)
        player_discard_before = len(player.discard_pile)
        target_discard_before = len(target.discard_pile)

        # Get top 3 denominations to determine expected winner
        player_top3_total = sum(c.denomination for c in player.draw_deck[:3])
        target_top3_total = sum(c.denomination for c in target.draw_deck[:3])

        # Activate Battle
        power_card = CardInstance(
            card_id=99900, card_name="Battle_Power", denomination=100,
            power_text="Battle", expansion_id=4,
        )
        resolver.create_power_prompt(state, player_index, power_card)
        resolver.handle_power_choice(state, player_index, {"choice": "activate"})
        events = resolver.handle_power_choice(
            state, player_index, {"target_player_index": target_index}
        )

        assert isinstance(events, list)
        assert events[0]["type"] == "power_activated"
        assert events[0]["power_name"] == "battle"

        if player_top3_total >= target_top3_total:
            # Active player wins
            assert events[0]["winner_player_id"] == player.player_id
            # Winner gets 6 cards under play pile
            assert len(player.play_pile) == player_play_pile_before + 6
            # Loser discards their 3
            assert len(target.discard_pile) == target_discard_before + 3
        else:
            # Target wins
            assert events[0]["winner_player_id"] == target.player_id
            # Winner gets 6 cards under play pile
            assert len(target.play_pile) == target_play_pile_before + 6
            # Loser discards their 3
            assert len(player.discard_pile) == player_discard_before + 3


# --- Property 46: Evolve preserves hand count ---


class TestProperty46EvolvePreservesHandCount:
    """Property 46: Evolve preserves hand count.

    For any Evolve power activation, the player's hand size should remain the same
    (old hand moved to discard, same count drawn from deck), provided the draw deck
    has enough cards.

    **Validates: Requirements 12.5**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_evolve_hand_size_preserved_when_deck_sufficient(self, data):
        """For any Evolve with sufficient draw deck, hand size is preserved."""
        state = data.draw(game_state_with_players())
        resolver = PowerResolver()
        player = state.players[0]

        assume(len(player.hand) >= 1)
        # Ensure draw deck has at least as many cards as hand
        while len(player.draw_deck) < len(player.hand):
            player.draw_deck.append(data.draw(card_strategy(
                card_id=data.draw(st.integers(min_value=70000, max_value=79999))
            )))

        hand_size_before = len(player.hand)
        old_hand_ids = {c.card_id for c in player.hand}

        # Activate Evolve
        power_card = CardInstance(
            card_id=99910, card_name="Evolve_Power", denomination=1000,
            power_text="Evolve", expansion_id=4,
        )
        resolver.create_power_prompt(state, 0, power_card)
        events = resolver.handle_power_choice(state, 0, {"choice": "activate"})

        assert isinstance(events, list)
        assert events[0]["type"] == "power_activated"
        assert events[0]["power_name"] == "evolve"
        # Hand size preserved
        assert len(player.hand) == hand_size_before
        # Old hand cards are in discard pile
        discard_ids = {c.card_id for c in player.discard_pile}
        for card_id in old_hand_ids:
            assert card_id in discard_ids


# --- Property 47: Freeze prevents playing named power ---


class TestProperty47FreezePreventsPower:
    """Property 47: Freeze prevents playing named power.

    For any Freeze power activation naming a specific power, is_power_frozen returns
    True after freeze and False after clear.

    **Validates: Requirements 12.6**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_freeze_makes_power_frozen(self, data):
        """After Freeze activation, is_power_frozen returns True for the named power."""
        resolver = PowerResolver()
        # Pick a freezable power (any activatable except freeze itself)
        freezable = sorted(ACTIVATABLE_POWERS - {"freeze"})
        power_to_freeze = data.draw(st.sampled_from(freezable))

        state = data.draw(game_state_with_players())

        # Verify power is not frozen initially
        assert resolver.is_power_frozen(state, power_to_freeze) is False

        # Freeze the power
        state.frozen_powers[power_to_freeze] = 0

        # Verify power is now frozen
        assert resolver.is_power_frozen(state, power_to_freeze) is True

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_freeze_cleared_after_clear_expired(self, data):
        """After clear_expired_freezes for the freezing player, is_power_frozen returns False."""
        resolver = PowerResolver()
        freezable = sorted(ACTIVATABLE_POWERS - {"freeze"})
        power_to_freeze = data.draw(st.sampled_from(freezable))

        state = data.draw(game_state_with_players())
        freezer_index = 0

        # Freeze the power
        state.frozen_powers[power_to_freeze] = freezer_index

        # Verify frozen
        assert resolver.is_power_frozen(state, power_to_freeze) is True

        # Clear expired freezes for the freezer
        events = resolver.clear_expired_freezes(state, freezer_index)

        # Verify no longer frozen
        assert resolver.is_power_frozen(state, power_to_freeze) is False
        assert len(events) >= 1
        assert events[0]["type"] == "freeze_expired"


# --- Property 48: Mutate preserves play pile count ---


class TestProperty48MutatePreservesPlayPileCount:
    """Property 48: Mutate preserves play pile count.

    For any Mutate power activation, the player's play pile size should remain the
    same (old pile shuffled into deck, same count moved from deck to pile).

    **Validates: Requirements 12.7**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_mutate_play_pile_count_preserved(self, data):
        """For any Mutate activation, play pile count is preserved."""
        state = data.draw(game_state_with_players())
        resolver = PowerResolver()
        player = state.players[0]

        # Give the player a non-empty play pile
        pile_size = data.draw(st.integers(min_value=1, max_value=5))
        play_pile_cards = []
        for i in range(pile_size):
            play_pile_cards.append(data.draw(card_strategy(
                card_id=60000 + i
            )))
        player.play_pile = play_pile_cards

        # Ensure draw deck is large enough (after pile is shuffled in, we need pile_size cards)
        # The pile cards get shuffled into the deck, so total deck = current deck + pile
        # We need at least pile_size from the combined deck
        # Since pile cards go into deck, combined will be >= pile_size as long as pile_size >= 1
        # which is guaranteed

        pile_count_before = len(player.play_pile)

        # Activate Mutate
        power_card = CardInstance(
            card_id=99920, card_name="Mutate_Power", denomination=100,
            power_text="Mutate", expansion_id=4,
        )
        resolver.create_power_prompt(state, 0, power_card)
        events = resolver.handle_power_choice(state, 0, {"choice": "activate"})

        assert isinstance(events, list)
        assert events[0]["type"] == "power_activated"
        assert events[0]["power_name"] == "mutate"
        # Play pile count preserved
        assert len(player.play_pile) == pile_count_before


# --- Property 49: Process net hand gain ---


class TestProperty49ProcessNetHandGain:
    """Property 49: Process net hand gain.

    For any Process power activation, the player's hand should grow by 1 net card
    (draw 3, place 2 under draw deck).

    **Validates: Requirements 12.8**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_process_net_hand_gain_is_one(self, data):
        """After full Process resolution (draw 3, place 2), net hand gain is +1."""
        state = data.draw(game_state_with_players())
        resolver = PowerResolver()
        player = state.players[0]

        # Ensure draw deck has at least 3 cards
        while len(player.draw_deck) < 3:
            player.draw_deck.append(data.draw(card_strategy(
                card_id=data.draw(st.integers(min_value=50000, max_value=59999))
            )))

        hand_size_before = len(player.hand)

        # Activate Process — draws 3 cards and prompts for 2 to place under deck
        power_card = CardInstance(
            card_id=99930, card_name="Process_Power", denomination=100,
            power_text="Process", expansion_id=4,
        )
        resolver.create_power_prompt(state, 0, power_card)
        events = resolver.handle_power_choice(state, 0, {"choice": "activate"})

        assert isinstance(events, list)
        assert events[0]["prompt_type"] == "choose_cards_from_hand"
        # After drawing 3, hand should have grown by 3
        assert len(player.hand) == hand_size_before + 3

        # Choose 2 cards from hand to place under draw deck
        # Pick any 2 cards from hand
        assume(len(player.hand) >= 2)
        card_ids_to_place = [player.hand[0].card_id, player.hand[1].card_id]

        events = resolver.handle_power_choice(
            state, 0, {"card_ids": card_ids_to_place}
        )

        assert isinstance(events, list)
        assert events[0]["type"] == "power_activated"
        assert events[0]["power_name"] == "process"
        # Net hand gain should be +1 (drew 3, placed 2 back)
        assert len(player.hand) == hand_size_before + 1


# --- Property 50: Quadruple scoring modifier ---


class TestProperty50QuadrupleScoringModifier:
    """Property 50: Quadruple scoring modifier.

    For any round winner whose play pile contains the Quadruple card, that card
    should contribute 40000 points to their score instead of 10000.

    **Validates: Requirements 12.9**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_quadruple_card_scores_40000(self, data):
        """For any player who went out with Quadruple in play pile, it scores 40000."""
        score_service = ScoreService()

        # Generate a play pile with a Quadruple card and some normal cards
        num_normal = data.draw(st.integers(min_value=0, max_value=5))
        play_pile = []
        normal_total = 0
        for i in range(num_normal):
            denom = data.draw(st.sampled_from(DENOMINATIONS))
            normal_total += denom
            play_pile.append(CardInstance(
                card_id=40000 + i,
                card_name=f"Normal_{i}",
                denomination=denom,
                power_text="Go",
                expansion_id=4,
            ))

        # Add the Quadruple card
        quadruple_card = CardInstance(
            card_id=49999,
            card_name="Quadruple_Card",
            denomination=10000,
            power_text="Quadruple",
            expansion_id=4,
        )
        play_pile.append(quadruple_card)

        players = [
            PlayerState(
                player_id=1, username="Winner", is_computer=False,
                hand=[], draw_deck=[], play_pile=play_pile, discard_pile=[],
                cumulative_score=0, is_decked=False, has_gone_out=True, seat_position=1,
            ),
            PlayerState(
                player_id=2, username="Other", is_computer=False,
                hand=[], draw_deck=[], play_pile=[], discard_pile=[],
                cumulative_score=0, is_decked=False, has_gone_out=False, seat_position=2,
            ),
        ]
        state = GameState(
            game_id="prop-test-quadruple", players=players,
            current_player_index=0, direction=1, current_sequence=1,
        )

        scores = score_service.calculate_round_scores(state)

        # Quadruple contributes 40000 instead of 10000
        expected = normal_total + 40000
        assert scores[1] == expected


# --- Property 51: Safety end-of-round modifier ---


class TestProperty51SafetyEndOfRoundModifier:
    """Property 51: Safety end-of-round modifier.

    For any player with Safety in their play pile at round end who did not go out,
    their hand should be shuffled into their draw deck instead of being placed in
    their discard pile.

    **Validates: Requirements 12.11**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_safety_hand_goes_to_draw_deck_not_discard(self, data):
        """For any player with Safety who didn't go out, hand goes to draw deck."""
        round_manager = RoundManager()

        # Generate a hand
        hand_size = data.draw(st.integers(min_value=1, max_value=7))
        hand_cards = []
        for i in range(hand_size):
            hand_cards.append(CardInstance(
                card_id=30000 + i,
                card_name=f"Hand_{i}",
                denomination=data.draw(st.sampled_from(DENOMINATIONS)),
                power_text="Go",
                expansion_id=4,
            ))

        # Safety card in play pile
        safety_card = CardInstance(
            card_id=39999, card_name="Safety_Card",
            denomination=data.draw(st.sampled_from(DENOMINATIONS)),
            power_text="Safety", expansion_id=4,
        )

        # Some other cards in play pile
        num_other_pile = data.draw(st.integers(min_value=0, max_value=3))
        play_pile = [safety_card]
        for i in range(num_other_pile):
            play_pile.append(CardInstance(
                card_id=35000 + i, card_name=f"Pile_{i}",
                denomination=data.draw(st.sampled_from(DENOMINATIONS)),
                power_text="Go", expansion_id=4,
            ))

        players = [
            PlayerState(
                player_id=1, username="SafetyPlayer", is_computer=False,
                hand=list(hand_cards), draw_deck=[], play_pile=play_pile,
                discard_pile=[], cumulative_score=0, is_decked=False,
                has_gone_out=False, seat_position=1,
            ),
            PlayerState(
                player_id=2, username="Winner", is_computer=False,
                hand=[], draw_deck=[], play_pile=[], discard_pile=[],
                cumulative_score=0, is_decked=False, has_gone_out=True, seat_position=2,
            ),
        ]
        state = GameState(
            game_id="prop-test-safety", players=players,
            current_player_index=0, direction=1, current_sequence=1,
        )

        events = []
        round_manager._move_non_goers_hands_to_discard(state, events)

        # Hand should be empty
        assert len(state.players[0].hand) == 0
        # Cards should be in draw deck, NOT discard
        assert len(state.players[0].discard_pile) == 0
        draw_deck_ids = {c.card_id for c in state.players[0].draw_deck}
        for card in hand_cards:
            assert card.card_id in draw_deck_ids
        # Event should indicate safety
        assert any(e.get("type") == "hand_shuffled_into_draw_deck" for e in events)


# --- Property 52: Tally scoring split ---


class TestProperty52TallyScoringSpilt:
    """Property 52: Tally scoring split.

    For any scoring event involving a card with the Tally power, the scorer should
    receive half the card's denomination value and the Tally card's owner should
    receive an equal number of points.

    **Validates: Requirements 12.12**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_tally_splits_points_evenly(self, data):
        """For any Tally scoring, scorer gets half and Tally owner gets half."""
        score_service = ScoreService()

        # Generate a denomination for the Tally card
        denom = data.draw(st.sampled_from(DENOMINATIONS))

        tally_card = CardInstance(
            card_id=20000, card_name="Tally_Card",
            denomination=denom, power_text="Tally", expansion_id=4,
        )

        # Tally owner is player 2, scorer is player 1
        players = [
            PlayerState(
                player_id=1, username="Scorer", is_computer=False,
                hand=[], draw_deck=[], play_pile=[], discard_pile=[],
                cumulative_score=0, is_decked=False, has_gone_out=False, seat_position=1,
            ),
            PlayerState(
                player_id=2, username="TallyOwner", is_computer=False,
                hand=[], draw_deck=[], play_pile=[tally_card], discard_pile=[],
                cumulative_score=0, is_decked=False, has_gone_out=False, seat_position=2,
            ),
        ]
        state = GameState(
            game_id="prop-test-tally", players=players,
            current_player_index=0, direction=1, current_sequence=1,
        )

        result = score_service.apply_tally_score(state, 1, tally_card, denom)

        # Points should be split evenly
        expected_half = denom // 2
        assert result[1] == expected_half  # Scorer gets half
        assert result[2] == expected_half  # Tally owner gets half
        assert state.players[0].cumulative_score == expected_half
        assert state.players[1].cumulative_score == expected_half

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_tally_no_split_when_scorer_is_owner(self, data):
        """When scorer owns the Tally card, no split occurs — full points to scorer."""
        score_service = ScoreService()

        denom = data.draw(st.sampled_from(DENOMINATIONS))

        tally_card = CardInstance(
            card_id=20001, card_name="Tally_Card",
            denomination=denom, power_text="Tally", expansion_id=4,
        )

        # Scorer (player 1) also owns the Tally card
        players = [
            PlayerState(
                player_id=1, username="ScorerOwner", is_computer=False,
                hand=[], draw_deck=[], play_pile=[tally_card], discard_pile=[],
                cumulative_score=0, is_decked=False, has_gone_out=False, seat_position=1,
            ),
            PlayerState(
                player_id=2, username="Other", is_computer=False,
                hand=[], draw_deck=[], play_pile=[], discard_pile=[],
                cumulative_score=0, is_decked=False, has_gone_out=False, seat_position=2,
            ),
        ]
        state = GameState(
            game_id="prop-test-tally-owner", players=players,
            current_player_index=0, direction=1, current_sequence=1,
        )

        result = score_service.apply_tally_score(state, 1, tally_card, denom)

        # No split — full points to scorer
        assert result[1] == denom
        assert state.players[0].cumulative_score == denom
        assert state.players[1].cumulative_score == 0


# --- Property 53: Toxin reveals cards per Discard count ---


class TestProperty53ToxinRevealsPerDiscardCount:
    """Property 53: Toxin reveals cards per Discard count.

    For any Toxin power activation, each opponent should reveal a number of cards
    from their draw deck equal to the number of Discard cards in their play pile;
    the active player scores points equal to one chosen revealed card's denomination;
    all revealed cards go to their respective owners' hands.

    **Validates: Requirements 12.13**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_toxin_reveals_correct_count_and_scores(self, data):
        """For any Toxin activation, revealed count matches Discard count in opponents' piles."""
        resolver = PowerResolver()

        # Set up: opponent has some Discard cards in play pile
        num_discard_cards = data.draw(st.integers(min_value=1, max_value=3))
        opponent_play_pile = []
        for i in range(num_discard_cards):
            opponent_play_pile.append(CardInstance(
                card_id=10000 + i, card_name=f"Discard_{i}",
                denomination=data.draw(st.sampled_from(DENOMINATIONS)),
                power_text="Discard", expansion_id=4,
            ))
        # Add some non-Discard cards too
        num_other = data.draw(st.integers(min_value=0, max_value=2))
        for i in range(num_other):
            opponent_play_pile.append(CardInstance(
                card_id=11000 + i, card_name=f"Other_{i}",
                denomination=data.draw(st.sampled_from(DENOMINATIONS)),
                power_text="Go", expansion_id=4,
            ))

        # Opponent needs enough cards in draw deck to reveal
        opponent_draw_deck = []
        for i in range(num_discard_cards + 2):
            opponent_draw_deck.append(CardInstance(
                card_id=12000 + i, card_name=f"Draw_{i}",
                denomination=data.draw(st.sampled_from(DENOMINATIONS)),
                power_text="Go", expansion_id=4,
            ))

        players = [
            PlayerState(
                player_id=1, username="ToxinPlayer", is_computer=False,
                hand=[], draw_deck=[], play_pile=[], discard_pile=[],
                cumulative_score=0, is_decked=False, has_gone_out=False, seat_position=1,
            ),
            PlayerState(
                player_id=2, username="Opponent", is_computer=False,
                hand=[], draw_deck=opponent_draw_deck, play_pile=opponent_play_pile,
                discard_pile=[], cumulative_score=0, is_decked=False,
                has_gone_out=False, seat_position=2,
            ),
            PlayerState(
                player_id=3, username="Bystander", is_computer=False,
                hand=[], draw_deck=[], play_pile=[], discard_pile=[],
                cumulative_score=0, is_decked=False, has_gone_out=False, seat_position=3,
            ),
        ]
        state = GameState(
            game_id="prop-test-toxin", players=players,
            current_player_index=0, direction=1, current_sequence=1,
        )

        # Activate Toxin
        power_card = CardInstance(
            card_id=99940, card_name="Toxin_Power", denomination=100,
            power_text="Toxin", expansion_id=4,
        )
        resolver.create_power_prompt(state, 0, power_card)
        events = resolver.handle_power_choice(state, 0, {"choice": "activate"})

        assert isinstance(events, list)
        assert events[0]["prompt_type"] == "choose_revealed_card"
        # Number of revealed cards should equal number of Discard cards in opponent's pile
        assert len(events[0]["revealed_cards"]) == num_discard_cards

        # Choose the first revealed card to score
        chosen_card_id = events[0]["revealed_cards"][0]["card_id"]
        chosen_denom = events[0]["revealed_cards"][0]["denomination"]

        score_before = state.players[0].cumulative_score

        events = resolver.handle_power_choice(state, 0, {"card_id": chosen_card_id})

        assert isinstance(events, list)
        assert events[0]["type"] == "power_activated"
        assert events[0]["power_name"] == "toxin"
        # Active player scored the chosen card's denomination
        assert state.players[0].cumulative_score == score_before + chosen_denom
        # All revealed cards go to their owners' hands
        assert len(state.players[1].hand) == num_discard_cards
