"""Property-based tests for Bonus scoring (Requirement 10.1).

Uses Hypothesis to verify the Bonus scoring condition across randomly generated
game states with various play pile configurations.

Property 35: Bonus scoring condition
- For any player who was not decked and whose play pile contains Bonus cards
  at denominations 1, 10, 100, and 1000, the Score_Service should add 100000
  bonus points.
- For any play pile missing one or more of these, no bonus should be awarded.

**Validates: Requirements 10.1**
"""

import sys
import os

from hypothesis import given, settings, assume
from hypothesis import strategies as st

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from models import CardInstance, GameState, PlayerState
from scoring.service import ScoreService


DENOMINATIONS = [1, 10, 100, 1000, 10000, 100000]
BONUS_DENOMINATIONS = [1, 10, 100, 1000]
NON_BONUS_POWERS = ["Go", "Skip", "Poison", "Rescue", "Reverse", "Discard"]


# --- Strategies ---


@st.composite
def bonus_card_strategy(draw, denomination):
    """Generate a Bonus CardInstance at a specific denomination."""
    cid = draw(st.integers(min_value=1, max_value=100000))
    # Allow case variation in power text to test case-insensitivity
    power_text = draw(st.sampled_from(["Bonus", "bonus", "BONUS", "bOnUs"]))
    return CardInstance(
        card_id=cid,
        card_name=f"Bonus_Tribble_{denomination}",
        denomination=denomination,
        power_text=power_text,
        expansion_id=2,
    )


@st.composite
def non_bonus_card_strategy(draw):
    """Generate a non-Bonus CardInstance (any denomination, non-Bonus power)."""
    cid = draw(st.integers(min_value=1, max_value=100000))
    denom = draw(st.sampled_from(DENOMINATIONS))
    power = draw(st.sampled_from(NON_BONUS_POWERS))
    return CardInstance(
        card_id=cid,
        card_name=f"Tribble_{cid}",
        denomination=denom,
        power_text=power,
        expansion_id=1,
    )


@st.composite
def play_pile_with_all_bonus_denominations(draw):
    """Generate a play pile that contains Bonus cards at all four required denominations.

    May also include additional non-bonus cards and duplicate bonus cards.
    """
    # Generate one Bonus card for each required denomination
    bonus_cards = []
    for denom in BONUS_DENOMINATIONS:
        card = draw(bonus_card_strategy(denomination=denom))
        bonus_cards.append(card)

    # Optionally add extra non-bonus cards
    extra_count = draw(st.integers(min_value=0, max_value=5))
    extra_cards = draw(st.lists(non_bonus_card_strategy(), min_size=extra_count, max_size=extra_count))

    # Optionally add duplicate bonus cards
    dup_count = draw(st.integers(min_value=0, max_value=3))
    dup_cards = []
    for _ in range(dup_count):
        dup_denom = draw(st.sampled_from(BONUS_DENOMINATIONS))
        dup_cards.append(draw(bonus_card_strategy(denomination=dup_denom)))

    pile = bonus_cards + extra_cards + dup_cards
    draw(st.randoms()).shuffle(pile)
    return pile


@st.composite
def play_pile_missing_bonus_denominations(draw):
    """Generate a play pile that is missing at least one required Bonus denomination.

    May contain some Bonus cards but not all four required denominations.
    """
    # Choose which denominations to include (must be a strict subset)
    included_denoms = draw(
        st.lists(
            st.sampled_from(BONUS_DENOMINATIONS),
            min_size=0,
            max_size=3,
            unique=True,
        )
    )
    # Ensure we're missing at least one
    assume(set(included_denoms) != set(BONUS_DENOMINATIONS))

    bonus_cards = []
    for denom in included_denoms:
        card = draw(bonus_card_strategy(denomination=denom))
        bonus_cards.append(card)

    # Add some non-bonus cards (including at missing denominations to ensure
    # non-bonus cards don't satisfy the requirement)
    extra_count = draw(st.integers(min_value=0, max_value=5))
    extra_cards = draw(st.lists(non_bonus_card_strategy(), min_size=extra_count, max_size=extra_count))

    pile = bonus_cards + extra_cards
    draw(st.randoms()).shuffle(pile)
    return pile


@st.composite
def game_state_for_bonus_scoring(draw):
    """Generate a game state with a mix of players for bonus scoring testing.

    Creates players with various configurations:
    - Some non-decked with all four Bonus denominations (should get bonus)
    - Some non-decked missing Bonus denominations (should not get bonus)
    - Some decked with all four Bonus denominations (should not get bonus)
    """
    n_players = draw(st.integers(min_value=2, max_value=6))

    players = []
    for i in range(n_players):
        is_decked = draw(st.booleans())
        has_all_bonus = draw(st.booleans())

        if has_all_bonus:
            play_pile = draw(play_pile_with_all_bonus_denominations())
        else:
            play_pile = draw(play_pile_missing_bonus_denominations())

        player = PlayerState(
            player_id=i + 1,
            username=f"Player_{i + 1}",
            is_computer=False,
            hand=[],
            draw_deck=[],
            play_pile=play_pile,
            discard_pile=[],
            cumulative_score=draw(st.integers(min_value=0, max_value=500000)),
            is_decked=is_decked,
            has_gone_out=draw(st.booleans()),
            seat_position=i + 1,
        )
        players.append(player)

    state = GameState(
        game_id="prop-test-bonus",
        players=players,
        spectators=[],
        current_player_index=0,
        direction=1,
        current_sequence=1,
        last_played_denomination=None,
        sequence_broken=False,
        round_number=draw(st.integers(min_value=1, max_value=5)),
        frozen_powers={},
        game_status="round_end",
        reconnection_timeout=30,
        pending_draw=None,
    )
    return state


# --- Property 35: Bonus scoring condition ---


class TestProperty35BonusScoringCondition:
    """Property 35: Bonus scoring condition.

    For any player who was not decked and whose play pile contains Bonus cards
    at denominations 1, 10, 100, and 1000, the Score_Service should add 100000
    bonus points. For any play pile missing one or more of these, no bonus
    should be awarded.

    **Validates: Requirements 10.1**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_non_decked_player_with_all_bonus_denominations_gets_100000(self, data):
        """For any non-decked player with all four Bonus denominations, bonus is 100000."""
        state = data.draw(game_state_for_bonus_scoring())
        score_service = ScoreService()

        # Find non-decked players with all four Bonus denominations
        eligible_players = []
        for player in state.players:
            if not player.is_decked:
                bonus_denoms_found = set()
                for card in player.play_pile:
                    if card.power_text.lower() == "bonus" and card.denomination in {1, 10, 100, 1000}:
                        bonus_denoms_found.add(card.denomination)
                if bonus_denoms_found >= {1, 10, 100, 1000}:
                    eligible_players.append(player)

        assume(len(eligible_players) > 0)

        bonus_scores = score_service.calculate_bonus_scores(state)

        for player in eligible_players:
            assert bonus_scores[player.player_id] == 100000, (
                f"Player {player.player_id} has all Bonus denominations and is not decked, "
                f"but got bonus score {bonus_scores[player.player_id]} instead of 100000"
            )

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_non_decked_player_missing_bonus_denominations_gets_zero(self, data):
        """For any non-decked player missing one or more Bonus denominations, bonus is 0."""
        state = data.draw(game_state_for_bonus_scoring())
        score_service = ScoreService()

        # Find non-decked players missing at least one Bonus denomination
        ineligible_players = []
        for player in state.players:
            if not player.is_decked:
                bonus_denoms_found = set()
                for card in player.play_pile:
                    if card.power_text.lower() == "bonus" and card.denomination in {1, 10, 100, 1000}:
                        bonus_denoms_found.add(card.denomination)
                if bonus_denoms_found < {1, 10, 100, 1000}:
                    ineligible_players.append(player)

        assume(len(ineligible_players) > 0)

        bonus_scores = score_service.calculate_bonus_scores(state)

        for player in ineligible_players:
            assert bonus_scores[player.player_id] == 0, (
                f"Player {player.player_id} is missing Bonus denominations, "
                f"but got bonus score {bonus_scores[player.player_id]} instead of 0"
            )

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_decked_player_never_gets_bonus(self, data):
        """For any decked player, bonus is always 0 regardless of play pile contents."""
        state = data.draw(game_state_for_bonus_scoring())
        score_service = ScoreService()

        decked_players = [p for p in state.players if p.is_decked]
        assume(len(decked_players) > 0)

        bonus_scores = score_service.calculate_bonus_scores(state)

        for player in decked_players:
            assert bonus_scores[player.player_id] == 0, (
                f"Decked player {player.player_id} should get 0 bonus, "
                f"but got {bonus_scores[player.player_id]}"
            )

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_all_players_receive_a_bonus_score_entry(self, data):
        """For any game state, every player should have an entry in the bonus scores dict."""
        state = data.draw(game_state_for_bonus_scoring())
        score_service = ScoreService()

        bonus_scores = score_service.calculate_bonus_scores(state)

        for player in state.players:
            assert player.player_id in bonus_scores, (
                f"Player {player.player_id} missing from bonus scores dict"
            )

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_bonus_score_is_either_100000_or_zero(self, data):
        """For any player, the bonus score is exactly 100000 or 0 (no other values)."""
        state = data.draw(game_state_for_bonus_scoring())
        score_service = ScoreService()

        bonus_scores = score_service.calculate_bonus_scores(state)

        for player in state.players:
            assert bonus_scores[player.player_id] in (0, 100000), (
                f"Player {player.player_id} has unexpected bonus score: "
                f"{bonus_scores[player.player_id]}"
            )
