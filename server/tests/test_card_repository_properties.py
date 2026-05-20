"""Property-based tests for the Card_Repository.

Uses Hypothesis to verify correctness properties of card search filtering
and compound power distinction.

**Validates: Requirements 2.3, 2.5**
"""

import sys
import os

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from cards.repository import Card, CardFilter, CardRepository


# --- Test data: a rich dataset with compound and component powers ---

VALID_DENOMINATIONS = [1, 10, 100, 1000, 10000, 100000]

COMPONENT_POWERS = ["Go", "Skip", "Clone", "Reverse", "Poison", "Rescue", "Bonus",
                    "Discard", "Draw", "Cycle", "Exchange", "Kill", "Recycle",
                    "Replay", "Score", "Copy", "Battle", "Evolve", "Freeze",
                    "Mutate", "Process", "Antidote", "Toxin", "Advance",
                    "Assimilate", "Convert", "Famine", "Stampede", "Avalanche"]

COMPOUND_POWERS = ["Clone & Reverse", "Clone & Poison", "Go & Skip",
                   "Rescue & Discard", "Clone & Go", "Reverse & Skip"]

ALL_POWERS = COMPONENT_POWERS + COMPOUND_POWERS

EXPANSION_IDS = [1, 2, 3, 4, 5, 6]

# Build a comprehensive sample dataset with cards covering all powers and expansions
SAMPLE_CARDS = []
_card_id = 1
for exp_id in EXPANSION_IDS:
    for denom in VALID_DENOMINATIONS:
        for power in ALL_POWERS[:7]:  # Use a subset per expansion/denom to keep dataset manageable
            SAMPLE_CARDS.append((
                _card_id,
                f"Tribble - {power}",
                denom,
                power,
                f"{_card_id}V",
                exp_id,
                f"{_card_id}V_{denom}_{power.lower().replace(' & ', '&')}.jpg",
            ))
            _card_id += 1

# Add specific compound power cards to ensure they exist in the dataset
for compound in COMPOUND_POWERS:
    for denom in [1000, 10000]:
        SAMPLE_CARDS.append((
            _card_id,
            f"Tribble - {compound}",
            denom,
            compound,
            f"{_card_id}V",
            4,  # expansion 4 (No Tribble at All)
            f"{_card_id}V_{denom}_{compound.lower().replace(' & ', '&')}.jpg",
        ))
        _card_id += 1

# Add cards with component powers that are also part of compounds
for component in ["Clone", "Reverse", "Poison", "Go", "Skip", "Rescue", "Discard"]:
    for denom in [100, 1000]:
        SAMPLE_CARDS.append((
            _card_id,
            f"Tribble - {component}",
            denom,
            component,
            f"{_card_id}V",
            1,
            f"{_card_id}V_{denom}_{component.lower()}.jpg",
        ))
        _card_id += 1


SAMPLE_EXPANSIONS = [
    (1, "Base Set", "base_set.jpg", "The original Tribbles expansion."),
    (2, "The Trouble with Tribbles", "trouble.jpg", "Second expansion."),
    (3, "More Tribbles More Troubles", "more.jpg", None),
    (4, "No Tribble at All", "no_tribble.jpg", "Fourth expansion."),
    (5, "Trials and Tribble-ations", "trials.jpg", "Fifth expansion."),
    (6, "Nothing But Tribble", "nothing.jpg", "Sixth expansion."),
]


# --- Fake database layer (reusing pattern from unit tests) ---


class FakeCursor:
    """A fake async cursor that queries in-memory card/expansion data."""

    def __init__(self, cards, expansions):
        self._cards = cards
        self._expansions = expansions
        self._results = []

    async def execute(self, query: str, args=None):
        query_lower = query.strip().lower()

        if "from cards" in query_lower and "where card_id" in query_lower:
            card_id = args[0]
            self._results = [c for c in self._cards if c[0] == card_id]

        elif "from cards" in query_lower:
            results = list(self._cards)

            if args:
                param_idx = 0
                if "denomination = %s" in query:
                    denom = args[param_idx]
                    results = [c for c in results if c[2] == denom]
                    param_idx += 1
                if "power_text = %s" in query:
                    power = args[param_idx]
                    results = [c for c in results if c[3] == power]
                    param_idx += 1
                if "expansion_id = %s" in query:
                    exp_id = args[param_idx]
                    results = [c for c in results if c[5] == exp_id]
                    param_idx += 1
                if "card_name like %s" in query_lower:
                    substring = args[param_idx].strip("%")
                    results = [c for c in results if substring.lower() in c[1].lower()]
                    param_idx += 1

            self._results = results

        elif "from expansions" in query_lower:
            self._results = list(self._expansions)

    async def fetchall(self):
        return self._results

    async def fetchone(self):
        if self._results:
            return self._results[0]
        return None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class FakeConnection:
    """A fake async connection wrapping a FakeCursor."""

    def __init__(self, cards, expansions):
        self._cards = cards
        self._expansions = expansions

    def cursor(self):
        return FakeCursor(self._cards, self._expansions)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class FakePool:
    """A fake aiomysql pool that returns FakeConnections."""

    def __init__(self, cards=None, expansions=None):
        self._cards = SAMPLE_CARDS if cards is None else cards
        self._expansions = SAMPLE_EXPANSIONS if expansions is None else expansions

    def acquire(self):
        return FakeConnection(self._cards, self._expansions)


# --- Hypothesis strategies ---


@st.composite
def card_filter_strategy(draw):
    """Generate random CardFilter combinations with values from the dataset."""
    denomination = draw(st.one_of(st.none(), st.sampled_from(VALID_DENOMINATIONS)))
    power_name = draw(st.one_of(st.none(), st.sampled_from(ALL_POWERS)))
    expansion = draw(st.one_of(st.none(), st.sampled_from(EXPANSION_IDS)))
    # For card_name_substring, use substrings that could appear in card names
    card_name_substring = draw(st.one_of(
        st.none(),
        st.sampled_from(["Tribble", "Clone", "Reverse", "Go", "Skip", "Poison",
                         "Rescue", "Bonus", "Discard", "Draw", "Cycle", "&",
                         "tribble", "CLONE", "ble"]),
    ))
    return CardFilter(
        denomination=denomination,
        power_name=power_name,
        expansion=expansion,
        card_name_substring=card_name_substring,
    )


@st.composite
def compound_power_strategy(draw):
    """Generate a compound power name (containing ' & ')."""
    return draw(st.sampled_from(COMPOUND_POWERS))


# --- Helper: compute expected results by applying filters in Python ---


def matches_filter(card_tuple, card_filter: CardFilter) -> bool:
    """Check if a card tuple matches all supplied filter criteria."""
    _, card_name, denomination, power_text, _, expansion_id, _ = card_tuple

    if card_filter.denomination is not None and denomination != card_filter.denomination:
        return False
    if card_filter.power_name is not None and power_text != card_filter.power_name:
        return False
    if card_filter.expansion is not None and expansion_id != card_filter.expansion:
        return False
    if card_filter.card_name_substring is not None:
        if card_filter.card_name_substring.lower() not in card_name.lower():
            return False
    return True


# --- Property Tests ---


class TestProperty4CardSearchFilterCorrectness:
    """Property 4: Card search filter correctness.

    For any combination of filter parameters (denomination, power name,
    expansion, card name substring), all cards returned by the Card_Repository
    should satisfy every supplied filter criterion, and no card satisfying all
    criteria should be omitted.

    **Validates: Requirements 2.3**
    """

    @pytest.mark.asyncio
    @settings(max_examples=100, deadline=None)
    @given(filters=card_filter_strategy())
    async def test_all_returned_cards_match_all_filters(self, filters: CardFilter):
        """Every card returned by search_cards must satisfy all supplied filter criteria."""
        repo = CardRepository(FakePool())
        results = await repo.search_cards(filters)

        for card in results:
            if filters.denomination is not None:
                assert card.denomination == filters.denomination, (
                    f"Card {card.card_id} has denomination {card.denomination}, "
                    f"expected {filters.denomination}"
                )
            if filters.power_name is not None:
                assert card.power_text == filters.power_name, (
                    f"Card {card.card_id} has power '{card.power_text}', "
                    f"expected '{filters.power_name}'"
                )
            if filters.expansion is not None:
                assert card.expansion_id == filters.expansion, (
                    f"Card {card.card_id} has expansion_id {card.expansion_id}, "
                    f"expected {filters.expansion}"
                )
            if filters.card_name_substring is not None:
                assert filters.card_name_substring.lower() in card.card_name.lower(), (
                    f"Card {card.card_id} name '{card.card_name}' does not contain "
                    f"substring '{filters.card_name_substring}'"
                )

    @pytest.mark.asyncio
    @settings(max_examples=100, deadline=None)
    @given(filters=card_filter_strategy())
    async def test_no_matching_card_is_omitted(self, filters: CardFilter):
        """No card satisfying all criteria should be omitted from results."""
        repo = CardRepository(FakePool())
        results = await repo.search_cards(filters)

        # Compute expected set of card_ids
        expected_ids = {
            card_tuple[0]
            for card_tuple in SAMPLE_CARDS
            if matches_filter(card_tuple, filters)
        }

        result_ids = {card.card_id for card in results}

        assert expected_ids == result_ids, (
            f"Mismatch: expected {len(expected_ids)} cards, got {len(result_ids)}. "
            f"Missing: {expected_ids - result_ids}, Extra: {result_ids - expected_ids}"
        )


class TestProperty5CompoundPowersDistinctFromComponents:
    """Property 5: Compound powers are distinct from component powers.

    For any compound power (e.g., "Clone & Reverse"), searching for that
    compound power should not return cards with only one of the component
    powers, and searching for a component power should not return cards
    whose power is the compound.

    **Validates: Requirements 2.5**
    """

    @pytest.mark.asyncio
    @settings(max_examples=100, deadline=None)
    @given(compound=compound_power_strategy())
    async def test_compound_search_excludes_component_only_cards(self, compound: str):
        """Searching for a compound power should not return cards with only a component power."""
        repo = CardRepository(FakePool())
        results = await repo.search_cards(CardFilter(power_name=compound))

        # Extract component powers from the compound
        components = [p.strip() for p in compound.split("&")]

        for card in results:
            # Every returned card must have the exact compound power
            assert card.power_text == compound, (
                f"Searching for compound '{compound}' returned card {card.card_id} "
                f"with power '{card.power_text}' (a component, not the compound)"
            )

    @pytest.mark.asyncio
    @settings(max_examples=100, deadline=None)
    @given(compound=compound_power_strategy())
    async def test_component_search_excludes_compound_cards(self, compound: str):
        """Searching for a component power should not return cards whose power is the compound."""
        repo = CardRepository(FakePool())

        # Extract component powers from the compound
        components = [p.strip() for p in compound.split("&")]

        for component in components:
            results = await repo.search_cards(CardFilter(power_name=component))

            for card in results:
                # No returned card should have the compound power
                assert card.power_text == component, (
                    f"Searching for component '{component}' returned card {card.card_id} "
                    f"with power '{card.power_text}' (the compound, not the component)"
                )
                assert card.power_text != compound, (
                    f"Searching for component '{component}' returned card {card.card_id} "
                    f"with compound power '{card.power_text}'"
                )
