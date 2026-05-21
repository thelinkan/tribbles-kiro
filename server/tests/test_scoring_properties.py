"""Property-based tests for scoring and round transitions.

Uses Hypothesis to verify scoring and round transition properties across
randomly generated game states.

Properties 25-27: Scoring and round transitions
- Property 25: Decked player round transition
- Property 26: End-of-round scoring and cleanup
- Property 27: New round starting player selection

**Validates: Requirements 7.6, 7.7, 8.1, 8.2, 8.3, 8.4, 8.7, 8.8**
"""

import sys
import os

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from game.round_manager import RoundManager
from models import CardInstance, GameState, PlayerState
from scoring.service import ScoreService


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
def card_list_strategy(draw, min_size=0, max_size=10, id_offset=0):
    """Generate a list of cards with unique card_ids."""
    size = draw(st.integers(min_value=min_size, max_value=max_size))
    cards = []
    for i in range(size):
        card = draw(card_strategy(card_id=id_offset + i + 1))
        cards.append(card)
    return cards


@st.composite
def game_state_with_decked_players_at_round_end(draw):
    """Generate a game state at round end with at least one decked player.

    Some decked players have play piles >= 7 cards, some < 7 cards.
    At least one non-decked player has gone out (to trigger end-of-round).

    Used for Property 25 to test decked player round transitions.
    """
    n_players = draw(st.integers(min_value=3, max_value=6))
    direction = draw(st.sampled_from([1, -1]))
    seq = draw(st.sampled_from(DENOMINATIONS))

    # At least one player must have gone out, and at least one must be decked
    # Choose indices for decked players (at least 1, at most n_players - 1)
    num_decked = draw(st.integers(min_value=1, max_value=n_players - 1))
    all_indices = list(range(n_players))
    decked_indices = draw(
        st.lists(
            st.sampled_from(all_indices),
            min_size=num_decked,
            max_size=num_decked,
            unique=True,
        )
    )

    # The goer must be a non-decked player
    non_decked_indices = [i for i in all_indices if i not in decked_indices]
    goer_index = draw(st.sampled_from(non_decked_indices))

    players = []
    for i in range(n_players):
        hand_offset = i * 1000
        pile_offset = i * 1000 + 200
        deck_offset = i * 1000 + 500

        if i in decked_indices:
            # Decked player: choose play pile size (some >= 7, some < 7)
            has_enough = draw(st.booleans())
            if has_enough:
                pile_size = draw(st.integers(min_value=7, max_value=15))
            else:
                pile_size = draw(st.integers(min_value=0, max_value=6))

            play_pile = []
            for j in range(pile_size):
                card = draw(card_strategy(card_id=pile_offset + j + 1))
                play_pile.append(card)

            player = PlayerState(
                player_id=i + 1,
                username=f"Player_{i + 1}",
                is_computer=False,
                hand=[],
                draw_deck=[],
                play_pile=play_pile,
                discard_pile=[],
                cumulative_score=draw(st.integers(min_value=0, max_value=10000)),
                is_decked=True,
                has_gone_out=False,
                seat_position=i + 1,
            )
        elif i == goer_index:
            # Player who went out: empty hand, has play pile for scoring
            play_pile = draw(card_list_strategy(min_size=1, max_size=10, id_offset=pile_offset))
            draw_deck = draw(card_list_strategy(min_size=5, max_size=15, id_offset=deck_offset))
            player = PlayerState(
                player_id=i + 1,
                username=f"Player_{i + 1}",
                is_computer=False,
                hand=[],
                draw_deck=draw_deck,
                play_pile=play_pile,
                discard_pile=[],
                cumulative_score=draw(st.integers(min_value=0, max_value=10000)),
                is_decked=False,
                has_gone_out=True,
                seat_position=i + 1,
            )
        else:
            # Non-decked, non-goer player: has hand and draw deck
            hand = draw(card_list_strategy(min_size=1, max_size=7, id_offset=hand_offset))
            draw_deck = draw(card_list_strategy(min_size=5, max_size=15, id_offset=deck_offset))
            play_pile = draw(card_list_strategy(min_size=0, max_size=5, id_offset=pile_offset))
            player = PlayerState(
                player_id=i + 1,
                username=f"Player_{i + 1}",
                is_computer=False,
                hand=hand,
                draw_deck=draw_deck,
                play_pile=play_pile,
                discard_pile=[],
                cumulative_score=draw(st.integers(min_value=0, max_value=10000)),
                is_decked=False,
                has_gone_out=False,
                seat_position=i + 1,
            )
        players.append(player)

    state = GameState(
        game_id="prop-test-game",
        players=players,
        spectators=[],
        current_player_index=0,
        direction=direction,
        current_sequence=seq,
        last_played_denomination=None,
        sequence_broken=False,
        round_number=draw(st.integers(min_value=1, max_value=4)),
        frozen_powers={},
        game_status="round_end",
        reconnection_timeout=30,
        pending_draw=None,
    )
    return state


@st.composite
def game_state_for_scoring_and_cleanup(draw):
    """Generate a game state at round end with some players having gone out.

    Used for Property 26 to test end-of-round scoring and cleanup.
    """
    n_players = draw(st.integers(min_value=3, max_value=6))
    direction = draw(st.sampled_from([1, -1]))
    seq = draw(st.sampled_from(DENOMINATIONS))

    # At least one player must have gone out
    num_goers = draw(st.integers(min_value=1, max_value=max(1, n_players - 1)))
    all_indices = list(range(n_players))
    goer_indices = draw(
        st.lists(
            st.sampled_from(all_indices),
            min_size=num_goers,
            max_size=num_goers,
            unique=True,
        )
    )

    players = []
    for i in range(n_players):
        hand_offset = i * 1000
        pile_offset = i * 1000 + 200
        deck_offset = i * 1000 + 500

        if i in goer_indices:
            # Player who went out: empty hand, has play pile for scoring
            play_pile = draw(card_list_strategy(min_size=1, max_size=10, id_offset=pile_offset))
            draw_deck = draw(card_list_strategy(min_size=5, max_size=15, id_offset=deck_offset))
            player = PlayerState(
                player_id=i + 1,
                username=f"Player_{i + 1}",
                is_computer=False,
                hand=[],
                draw_deck=draw_deck,
                play_pile=play_pile,
                discard_pile=[],
                cumulative_score=draw(st.integers(min_value=0, max_value=10000)),
                is_decked=False,
                has_gone_out=True,
                seat_position=i + 1,
            )
        else:
            # Non-goer: has hand and draw deck
            hand = draw(card_list_strategy(min_size=1, max_size=7, id_offset=hand_offset))
            draw_deck = draw(card_list_strategy(min_size=7, max_size=20, id_offset=deck_offset))
            play_pile = draw(card_list_strategy(min_size=0, max_size=5, id_offset=pile_offset))
            player = PlayerState(
                player_id=i + 1,
                username=f"Player_{i + 1}",
                is_computer=False,
                hand=hand,
                draw_deck=draw_deck,
                play_pile=play_pile,
                discard_pile=[],
                cumulative_score=draw(st.integers(min_value=0, max_value=10000)),
                is_decked=False,
                has_gone_out=False,
                seat_position=i + 1,
            )
        players.append(player)

    state = GameState(
        game_id="prop-test-game",
        players=players,
        spectators=[],
        current_player_index=0,
        direction=direction,
        current_sequence=seq,
        last_played_denomination=None,
        sequence_broken=False,
        round_number=draw(st.integers(min_value=1, max_value=4)),
        frozen_powers={},
        game_status="round_end",
        reconnection_timeout=30,
        pending_draw=None,
    )
    return state


@st.composite
def game_state_for_starting_player_single_goer(draw):
    """Generate a game state at round end with exactly one player who went out.

    Used for Property 27 to test starting player selection (single goer case).
    """
    n_players = draw(st.integers(min_value=3, max_value=6))
    direction = draw(st.sampled_from([1, -1]))
    seq = draw(st.sampled_from(DENOMINATIONS))

    # Exactly one player went out
    goer_index = draw(st.integers(min_value=0, max_value=n_players - 1))

    players = []
    for i in range(n_players):
        hand_offset = i * 1000
        pile_offset = i * 1000 + 200
        deck_offset = i * 1000 + 500

        if i == goer_index:
            play_pile = draw(card_list_strategy(min_size=1, max_size=10, id_offset=pile_offset))
            draw_deck = draw(card_list_strategy(min_size=5, max_size=15, id_offset=deck_offset))
            player = PlayerState(
                player_id=i + 1,
                username=f"Player_{i + 1}",
                is_computer=False,
                hand=[],
                draw_deck=draw_deck,
                play_pile=play_pile,
                discard_pile=[],
                cumulative_score=draw(st.integers(min_value=0, max_value=10000)),
                is_decked=False,
                has_gone_out=True,
                seat_position=i + 1,
            )
        else:
            hand = draw(card_list_strategy(min_size=1, max_size=7, id_offset=hand_offset))
            draw_deck = draw(card_list_strategy(min_size=7, max_size=20, id_offset=deck_offset))
            play_pile = draw(card_list_strategy(min_size=0, max_size=5, id_offset=pile_offset))
            player = PlayerState(
                player_id=i + 1,
                username=f"Player_{i + 1}",
                is_computer=False,
                hand=hand,
                draw_deck=draw_deck,
                play_pile=play_pile,
                discard_pile=[],
                cumulative_score=draw(st.integers(min_value=0, max_value=10000)),
                is_decked=False,
                has_gone_out=False,
                seat_position=i + 1,
            )
        players.append(player)

    state = GameState(
        game_id="prop-test-game",
        players=players,
        spectators=[],
        current_player_index=0,
        direction=direction,
        current_sequence=seq,
        last_played_denomination=None,
        sequence_broken=False,
        round_number=draw(st.integers(min_value=1, max_value=4)),
        frozen_powers={},
        game_status="round_end",
        reconnection_timeout=30,
        pending_draw=None,
    )
    return state, goer_index


@st.composite
def game_state_for_starting_player_multiple_goers(draw):
    """Generate a game state at round end with multiple players who went out.

    Each goer has a distinct play pile with different total denominations to
    test lowest-score-starts logic.

    Used for Property 27 to test starting player selection (multiple goers case).
    """
    n_players = draw(st.integers(min_value=3, max_value=6))
    direction = draw(st.sampled_from([1, -1]))
    seq = draw(st.sampled_from(DENOMINATIONS))

    # Multiple players went out (at least 2)
    num_goers = draw(st.integers(min_value=2, max_value=min(n_players, 4)))
    all_indices = list(range(n_players))
    goer_indices = draw(
        st.lists(
            st.sampled_from(all_indices),
            min_size=num_goers,
            max_size=num_goers,
            unique=True,
        )
    )

    players = []
    for i in range(n_players):
        hand_offset = i * 1000
        pile_offset = i * 1000 + 200
        deck_offset = i * 1000 + 500

        if i in goer_indices:
            play_pile = draw(card_list_strategy(min_size=1, max_size=10, id_offset=pile_offset))
            draw_deck = draw(card_list_strategy(min_size=5, max_size=15, id_offset=deck_offset))
            player = PlayerState(
                player_id=i + 1,
                username=f"Player_{i + 1}",
                is_computer=False,
                hand=[],
                draw_deck=draw_deck,
                play_pile=play_pile,
                discard_pile=[],
                cumulative_score=draw(st.integers(min_value=0, max_value=10000)),
                is_decked=False,
                has_gone_out=True,
                seat_position=i + 1,
            )
        else:
            hand = draw(card_list_strategy(min_size=1, max_size=7, id_offset=hand_offset))
            draw_deck = draw(card_list_strategy(min_size=7, max_size=20, id_offset=deck_offset))
            play_pile = draw(card_list_strategy(min_size=0, max_size=5, id_offset=pile_offset))
            player = PlayerState(
                player_id=i + 1,
                username=f"Player_{i + 1}",
                is_computer=False,
                hand=hand,
                draw_deck=draw_deck,
                play_pile=play_pile,
                discard_pile=[],
                cumulative_score=draw(st.integers(min_value=0, max_value=10000)),
                is_decked=False,
                has_gone_out=False,
                seat_position=i + 1,
            )
        players.append(player)

    state = GameState(
        game_id="prop-test-game",
        players=players,
        spectators=[],
        current_player_index=0,
        direction=direction,
        current_sequence=seq,
        last_played_denomination=None,
        sequence_broken=False,
        round_number=draw(st.integers(min_value=1, max_value=4)),
        frozen_powers={},
        game_status="round_end",
        reconnection_timeout=30,
        pending_draw=None,
    )
    return state, goer_indices


# --- Property 25: Decked player round transition ---


class TestProperty25DeckedPlayerRoundTransition:
    """Property 25: Decked player round transition.

    For any decked player at round end: if their play pile has 7 or more cards,
    it should become their shuffled draw deck for the next round; if fewer than
    7 cards, they should sit out the next round.

    **Validates: Requirements 7.6, 7.7**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_decked_player_with_7_plus_cards_gets_draw_deck(self, data):
        """For any decked player with >= 7 cards in play pile, play pile becomes draw deck."""
        state = data.draw(game_state_with_decked_players_at_round_end())
        round_manager = RoundManager()

        # Find decked players with >= 7 cards in play pile
        decked_with_enough = [
            p for p in state.players if p.is_decked and len(p.play_pile) >= 7
        ]
        assume(len(decked_with_enough) > 0)

        # Record play pile card ids before processing
        pile_card_ids_before = {
            p.player_id: set(c.card_id for c in p.play_pile)
            for p in decked_with_enough
        }

        round_manager.process_end_of_round(state)

        for player in state.players:
            if player.player_id in pile_card_ids_before:
                # After processing, the play pile cards should be in the draw deck
                # (some may have been dealt to hand)
                draw_deck_ids = set(c.card_id for c in player.draw_deck)
                hand_ids = set(c.card_id for c in player.hand)
                combined_ids = draw_deck_ids | hand_ids
                original_ids = pile_card_ids_before[player.player_id]
                assert original_ids == combined_ids

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_decked_player_with_7_plus_cards_receives_hand(self, data):
        """For any decked player with >= 7 cards in play pile, they receive 7 cards in hand."""
        state = data.draw(game_state_with_decked_players_at_round_end())
        round_manager = RoundManager()

        decked_with_enough = [
            p for p in state.players if p.is_decked and len(p.play_pile) >= 7
        ]
        assume(len(decked_with_enough) > 0)

        round_manager.process_end_of_round(state)

        for player in state.players:
            if player.player_id in [p.player_id for p in decked_with_enough]:
                assert len(player.hand) == 7

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_decked_player_with_less_than_7_cards_sits_out(self, data):
        """For any decked player with < 7 cards in play pile, they sit out (no hand dealt)."""
        state = data.draw(game_state_with_decked_players_at_round_end())
        round_manager = RoundManager()

        decked_without_enough = [
            p for p in state.players if p.is_decked and len(p.play_pile) < 7
        ]
        assume(len(decked_without_enough) > 0)

        sitting_out_ids = [p.player_id for p in decked_without_enough]

        round_manager.process_end_of_round(state)

        for player in state.players:
            if player.player_id in sitting_out_ids:
                # Player sitting out should have no hand
                assert len(player.hand) == 0

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_decked_player_sitting_out_play_pile_to_discard(self, data):
        """For any decked player sitting out, their play pile cards move to discard."""
        state = data.draw(game_state_with_decked_players_at_round_end())
        round_manager = RoundManager()

        decked_without_enough = [
            p for p in state.players if p.is_decked and len(p.play_pile) < 7
        ]
        assume(len(decked_without_enough) > 0)

        # Record play pile card ids before processing
        pile_card_ids_before = {
            p.player_id: set(c.card_id for c in p.play_pile)
            for p in decked_without_enough
        }

        round_manager.process_end_of_round(state)

        for player in state.players:
            if player.player_id in pile_card_ids_before:
                original_ids = pile_card_ids_before[player.player_id]
                discard_ids = set(c.card_id for c in player.discard_pile)
                # All original play pile cards should be in discard
                assert original_ids.issubset(discard_ids)
                # Play pile should be empty
                assert player.play_pile == []


# --- Property 26: End-of-round scoring and cleanup ---


class TestProperty26EndOfRoundScoringAndCleanup:
    """Property 26: End-of-round scoring and cleanup.

    For any round end: each player who went out should score points equal to
    the sum of denominations in their play pile; each player who did not go out
    should have their hand moved to their discard pile; and all players' play
    piles should be shuffled into their draw decks.

    **Validates: Requirements 8.1, 8.2, 8.3, 8.4**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_goers_score_sum_of_play_pile_denominations(self, data):
        """For any player who went out, cumulative score increases by play pile sum."""
        state = data.draw(game_state_for_scoring_and_cleanup())
        round_manager = RoundManager()

        goers = [p for p in state.players if p.has_gone_out]
        assume(len(goers) > 0)

        # Record expected scores before processing
        expected_scores = {}
        for player in goers:
            pile_sum = sum(c.denomination for c in player.play_pile)
            expected_scores[player.player_id] = player.cumulative_score + pile_sum

        round_manager.process_end_of_round(state)

        for player in state.players:
            if player.player_id in expected_scores:
                assert player.cumulative_score == expected_scores[player.player_id]

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_non_goers_do_not_score(self, data):
        """For any player who did not go out, cumulative score does not increase."""
        state = data.draw(game_state_for_scoring_and_cleanup())
        round_manager = RoundManager()

        non_goers = [p for p in state.players if not p.has_gone_out]
        assume(len(non_goers) > 0)

        # Record scores before processing
        scores_before = {p.player_id: p.cumulative_score for p in non_goers}

        round_manager.process_end_of_round(state)

        for player in state.players:
            if player.player_id in scores_before:
                assert player.cumulative_score == scores_before[player.player_id]

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_non_goers_hand_moved_to_discard(self, data):
        """For any player who did not go out, their hand cards move to discard pile."""
        state = data.draw(game_state_for_scoring_and_cleanup())
        round_manager = RoundManager()

        non_goers = [p for p in state.players if not p.has_gone_out]
        assume(len(non_goers) > 0)

        # Record hand card ids before processing
        hand_card_ids_before = {
            p.player_id: set(c.card_id for c in p.hand)
            for p in non_goers
            if len(p.hand) > 0
        }
        assume(len(hand_card_ids_before) > 0)

        round_manager.process_end_of_round(state)

        for player in state.players:
            if player.player_id in hand_card_ids_before:
                discard_ids = set(c.card_id for c in player.discard_pile)
                original_hand_ids = hand_card_ids_before[player.player_id]
                # All original hand cards should be in discard
                assert original_hand_ids.issubset(discard_ids)

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_all_play_piles_cleared(self, data):
        """For any round end, all players' play piles should be empty after processing."""
        state = data.draw(game_state_for_scoring_and_cleanup())
        round_manager = RoundManager()

        round_manager.process_end_of_round(state)

        for player in state.players:
            assert player.play_pile == []

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_play_pile_cards_end_up_in_draw_deck_or_hand(self, data):
        """For any round end, play pile cards are shuffled into draw deck (or dealt to hand)."""
        state = data.draw(game_state_for_scoring_and_cleanup())
        round_manager = RoundManager()

        # Record play pile card ids for non-decked players before processing
        pile_card_ids_before = {}
        for player in state.players:
            if len(player.play_pile) > 0 and not player.is_decked:
                pile_card_ids_before[player.player_id] = set(
                    c.card_id for c in player.play_pile
                )

        assume(len(pile_card_ids_before) > 0)

        round_manager.process_end_of_round(state)

        for player in state.players:
            if player.player_id in pile_card_ids_before:
                # Play pile cards should now be in draw deck or hand
                draw_deck_ids = set(c.card_id for c in player.draw_deck)
                hand_ids = set(c.card_id for c in player.hand)
                combined = draw_deck_ids | hand_ids
                original_pile_ids = pile_card_ids_before[player.player_id]
                assert original_pile_ids.issubset(combined)


# --- Property 27: New round starting player selection ---


class TestProperty27NewRoundStartingPlayerSelection:
    """Property 27: New round starting player selection.

    For any round end where exactly one player went out, that player should be
    the starting player for the next round. When multiple players went out
    simultaneously, the one with the lowest round score should start.

    **Validates: Requirements 8.7, 8.8**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_single_goer_becomes_starting_player(self, data):
        """For any round end with exactly one goer, that player starts next round."""
        state, goer_index = data.draw(game_state_for_starting_player_single_goer())
        round_manager = RoundManager()

        goer_player_id = state.players[goer_index].player_id

        round_manager.process_end_of_round(state)

        # The starting player should be the goer
        starting_player = state.players[state.current_player_index]
        assert starting_player.player_id == goer_player_id

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_multiple_goers_lowest_score_starts(self, data):
        """For any round end with multiple goers, lowest round score starts."""
        state, goer_indices = data.draw(game_state_for_starting_player_multiple_goers())
        round_manager = RoundManager()

        # Calculate expected round scores for goers
        goer_scores = []
        for idx in goer_indices:
            player = state.players[idx]
            round_score = sum(c.denomination for c in player.play_pile)
            goer_scores.append((round_score, player.seat_position, player.player_id, idx))

        # Sort by round score, then seat position (tie-breaker)
        goer_scores.sort(key=lambda x: (x[0], x[1]))
        expected_starting_player_id = goer_scores[0][2]

        round_manager.process_end_of_round(state)

        starting_player = state.players[state.current_player_index]
        assert starting_player.player_id == expected_starting_player_id

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_starting_player_is_always_a_goer(self, data):
        """For any round end, the starting player for next round was a goer."""
        state = data.draw(game_state_for_scoring_and_cleanup())
        round_manager = RoundManager()

        goer_ids = [p.player_id for p in state.players if p.has_gone_out]
        assume(len(goer_ids) > 0)

        round_manager.process_end_of_round(state)

        starting_player = state.players[state.current_player_index]
        assert starting_player.player_id in goer_ids
