"""Tests for the Card_Repository (card search, lookup, expansion listing).

Uses an in-memory mock of the aiomysql pool to test repository logic without
requiring a live database connection.
"""

import sys
import os

import pytest

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from cards.repository import Card, CardFilter, CardRepository, Expansion


# --- Fake database layer ---

SAMPLE_CARDS = [
    (1, "Tribble - Go", 1, "Go", "1V", 1, "1V_1_go.jpg"),
    (2, "Tribble - Skip", 10, "Skip", "2V", 1, "2V_10_skip.jpg"),
    (3, "Tribble - Clone", 100, "Clone", "3V", 1, "3V_100_clone.jpg"),
    (4, "Tribble - Reverse", 1000, "Reverse", "4V", 1, "4V_1000_reverse.jpg"),
    (5, "Tribble - Clone & Reverse", 10000, "Clone & Reverse", "5V", 2, "5V_10000_clone&reverse.jpg"),
    (6, "Tribble - Poison", 100, "Poison", "6V", 2, "6V_100_poison.jpg"),
    (7, "Tribble - Go", 10, "Go", "7V", 2, "7V_10_go.jpg"),
    (8, "Tribble - Bonus", 1, "Bonus", "8V", 3, "8V_1_bonus.jpg"),
]

SAMPLE_EXPANSIONS = [
    (1, "Base Set", "base_set.jpg", "The original Tribbles expansion."),
    (2, "The Trouble with Tribbles", "trouble.jpg", "Second expansion."),
    (3, "More Tribbles More Troubles", "more.jpg", None),
]


class FakeCursor:
    """A fake async cursor that queries in-memory card/expansion data."""

    def __init__(self, cards, expansions):
        self._cards = cards
        self._expansions = expansions
        self._results = []

    async def execute(self, query: str, args=None):
        query_lower = query.strip().lower()

        if "from cards" in query_lower and "where card_id" in query_lower:
            # get_card query
            card_id = args[0]
            self._results = [c for c in self._cards if c[0] == card_id]

        elif "from cards" in query_lower:
            # search_cards query - apply filters in-memory
            results = list(self._cards)

            if args:
                # Parse conditions from query to apply filters
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
            # get_all_expansions query
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


@pytest.fixture
def repo():
    """Create a CardRepository with a fake in-memory pool."""
    pool = FakePool()
    return CardRepository(pool)


@pytest.fixture
def empty_repo():
    """Create a CardRepository with no data."""
    pool = FakePool(cards=[], expansions=[])
    return CardRepository(pool)


# --- Tests ---


class TestSearchCards:
    """Tests for CardRepository.search_cards."""

    @pytest.mark.asyncio
    async def test_no_filters_returns_all_cards(self, repo):
        """Requirement 2.4: No filters returns all cards."""
        results = await repo.search_cards(CardFilter())
        assert len(results) == len(SAMPLE_CARDS)

    @pytest.mark.asyncio
    async def test_filter_by_denomination(self, repo):
        """Requirement 2.3: Filter by denomination returns matching cards."""
        results = await repo.search_cards(CardFilter(denomination=100))
        assert len(results) == 2
        assert all(c.denomination == 100 for c in results)

    @pytest.mark.asyncio
    async def test_filter_by_power_name_exact_match(self, repo):
        """Requirement 2.3: Filter by power_name uses exact match."""
        results = await repo.search_cards(CardFilter(power_name="Go"))
        assert len(results) == 2
        assert all(c.power_text == "Go" for c in results)

    @pytest.mark.asyncio
    async def test_filter_by_expansion(self, repo):
        """Requirement 2.3: Filter by expansion returns matching cards."""
        results = await repo.search_cards(CardFilter(expansion=1))
        assert len(results) == 4
        assert all(c.expansion_id == 1 for c in results)

    @pytest.mark.asyncio
    async def test_filter_by_card_name_substring(self, repo):
        """Requirement 2.3: Filter by card name substring (case-insensitive)."""
        results = await repo.search_cards(CardFilter(card_name_substring="Poison"))
        assert len(results) == 1
        assert results[0].card_name == "Tribble - Poison"

    @pytest.mark.asyncio
    async def test_multiple_filters_combined(self, repo):
        """Requirement 2.3: All filters applied together (AND logic)."""
        results = await repo.search_cards(CardFilter(denomination=10, power_name="Go"))
        assert len(results) == 1
        assert results[0].card_name == "Tribble - Go"
        assert results[0].denomination == 10

    @pytest.mark.asyncio
    async def test_compound_power_not_returned_for_component_search(self, repo):
        """Requirement 2.5: Searching for 'Clone' does NOT return 'Clone & Reverse'."""
        results = await repo.search_cards(CardFilter(power_name="Clone"))
        assert all(c.power_text == "Clone" for c in results)
        assert not any(c.power_text == "Clone & Reverse" for c in results)

    @pytest.mark.asyncio
    async def test_component_power_not_returned_for_compound_search(self, repo):
        """Requirement 2.5: Searching for 'Clone & Reverse' does NOT return 'Clone' or 'Reverse'."""
        results = await repo.search_cards(CardFilter(power_name="Clone & Reverse"))
        assert len(results) == 1
        assert results[0].power_text == "Clone & Reverse"

    @pytest.mark.asyncio
    async def test_no_matching_results(self, repo):
        """Filter that matches nothing returns empty list."""
        results = await repo.search_cards(CardFilter(denomination=999999))
        assert results == []

    @pytest.mark.asyncio
    async def test_returns_card_objects(self, repo):
        """Results are Card dataclass instances with correct fields."""
        results = await repo.search_cards(CardFilter(power_name="Poison"))
        assert len(results) == 1
        card = results[0]
        assert isinstance(card, Card)
        assert card.card_id == 6
        assert card.card_name == "Tribble - Poison"
        assert card.denomination == 100
        assert card.power_text == "Poison"
        assert card.card_number == "6V"
        assert card.expansion_id == 2
        assert card.image_filename == "6V_100_poison.jpg"


class TestGetCard:
    """Tests for CardRepository.get_card."""

    @pytest.mark.asyncio
    async def test_get_existing_card(self, repo):
        """Returns the correct card for a valid ID."""
        card = await repo.get_card(1)
        assert card is not None
        assert card.card_id == 1
        assert card.card_name == "Tribble - Go"
        assert card.denomination == 1
        assert card.power_text == "Go"

    @pytest.mark.asyncio
    async def test_get_nonexistent_card(self, repo):
        """Returns None for an ID that doesn't exist."""
        card = await repo.get_card(9999)
        assert card is None

    @pytest.mark.asyncio
    async def test_get_card_all_fields(self, repo):
        """All card fields are populated correctly."""
        card = await repo.get_card(5)
        assert card is not None
        assert card.card_id == 5
        assert card.card_name == "Tribble - Clone & Reverse"
        assert card.denomination == 10000
        assert card.power_text == "Clone & Reverse"
        assert card.card_number == "5V"
        assert card.expansion_id == 2
        assert card.image_filename == "5V_10000_clone&reverse.jpg"


class TestGetAllExpansions:
    """Tests for CardRepository.get_all_expansions."""

    @pytest.mark.asyncio
    async def test_returns_all_expansions(self, repo):
        """Requirement 2.8: Returns all expansions from the database."""
        expansions = await repo.get_all_expansions()
        assert len(expansions) == 3

    @pytest.mark.asyncio
    async def test_expansion_fields(self, repo):
        """Expansion objects have correct fields."""
        expansions = await repo.get_all_expansions()
        exp = expansions[0]
        assert isinstance(exp, Expansion)
        assert exp.expansion_id == 1
        assert exp.expansion_name == "Base Set"
        assert exp.pack_art_filename == "base_set.jpg"
        assert exp.expansion_description == "The original Tribbles expansion."

    @pytest.mark.asyncio
    async def test_expansion_nullable_description(self, repo):
        """Expansion description can be None."""
        expansions = await repo.get_all_expansions()
        exp = expansions[2]
        assert exp.expansion_name == "More Tribbles More Troubles"
        assert exp.expansion_description is None

    @pytest.mark.asyncio
    async def test_empty_expansions(self, empty_repo):
        """Returns empty list when no expansions exist."""
        expansions = await empty_repo.get_all_expansions()
        assert expansions == []
