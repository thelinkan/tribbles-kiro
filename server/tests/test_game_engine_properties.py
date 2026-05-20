"""Property-based tests for the Game_Engine initialise_game method.

Uses Hypothesis to verify game initialisation invariants across
randomly generated player configurations.

Property 15: Game initialisation invariants
- All seat positions are unique and cover exactly 1 through player_count
- current_player_index is a valid index into the players list
- Every player has exactly 7 cards in hand (or all cards if deck < 7)

**Validates: Requirements 5.1, 5.2, 5.4**
"""

import sys
import os

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from game.engine import GameEngine, GameSession, PlayerSetup
from models import CardInstance


# --- Strategies ---

@st.composite
def card_instance_strategy(draw, card_id=None):
    """Generate a random CardInstance."""
    cid = card_id if card_id is not None else draw(st.integers(min_value=1, max_value=10000))
    denomination = draw(st.sampled_from([1, 10, 100, 1000, 10000, 100000]))
    card_name = draw(st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L", "N"))))
    power_text = draw(st.sampled_from(["Go", "Skip", "Poison", "Rescue", "Reverse", "Clone", "Discard"]))
    expansion_id = draw(st.integers(min_value=1, max_value=6))
    return CardInstance(
        card_id=cid,
        card_name=card_name,
        denomination=denomination,
        power_text=power_text,
        expansion_id=expansion_id,
    )


@st.composite
def deck_strategy(draw, min_size=7, max_size=60):
    """Generate a random deck of CardInstance objects with unique card_ids."""
    size = draw(st.integers(min_value=min_size, max_value=max_size))
    cards = []
    for i in range(size):
        card = draw(card_instance_strategy(card_id=i + 1))
        cards.append(card)
    return cards


@st.composite
def player_setup_strategy(draw, player_id, min_deck_size=7):
    """Generate a random PlayerSetup for a given player_id."""
    username = f"Player_{player_id}"
    is_computer = draw(st.booleans())
    deck_cards = draw(deck_strategy(min_size=min_deck_size, max_size=60))
    return PlayerSetup(
        player_id=player_id,
        username=username,
        is_computer=is_computer,
        deck_cards=deck_cards,
    )


@st.composite
def game_session_strategy(draw, min_deck_size=7):
    """Generate a random GameSession with 4-8 players, each with a deck of at least min_deck_size cards."""
    player_count = draw(st.integers(min_value=4, max_value=8))
    players = []
    for i in range(player_count):
        player = draw(player_setup_strategy(player_id=i + 1, min_deck_size=min_deck_size))
        players.append(player)
    spectators = draw(st.lists(st.integers(min_value=100, max_value=200), min_size=0, max_size=5))
    reconnection_timeout = draw(st.integers(min_value=10, max_value=120))
    game_id = draw(st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L", "N"))))
    return GameSession(
        game_id=game_id,
        players=players,
        spectators=spectators,
        reconnection_timeout=reconnection_timeout,
    )


@st.composite
def game_session_small_deck_strategy(draw):
    """Generate a GameSession where some players may have fewer than 7 cards."""
    player_count = draw(st.integers(min_value=4, max_value=8))
    players = []
    for i in range(player_count):
        player = draw(player_setup_strategy(player_id=i + 1, min_deck_size=1))
        players.append(player)
    game_id = draw(st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L", "N"))))
    return GameSession(
        game_id=game_id,
        players=players,
        spectators=[],
        reconnection_timeout=30,
    )


# --- Property Tests ---

class TestProperty15GameInitialisationInvariants:
    """Property 15: Game initialisation invariants.

    **Validates: Requirements 5.1, 5.2, 5.4**
    """

    @given(session=game_session_strategy(min_deck_size=7))
    @settings(max_examples=100, deadline=None)
    def test_seat_positions_unique_and_cover_1_through_player_count(self, session):
        """For any set of players, after initialisation all seat positions
        are unique and cover exactly 1 through player_count.

        **Validates: Requirements 5.1**
        """
        engine = GameEngine()
        state = engine.initialise_game(session)

        player_count = len(session.players)
        positions = [p.seat_position for p in state.players]

        # All positions are unique
        assert len(set(positions)) == player_count

        # Positions cover exactly 1 through player_count
        assert sorted(positions) == list(range(1, player_count + 1))

    @given(session=game_session_strategy(min_deck_size=7))
    @settings(max_examples=100, deadline=None)
    def test_current_player_index_is_valid(self, session):
        """For any set of players, after initialisation the starting player
        (current_player_index) is a valid index into the players list.

        **Validates: Requirements 5.2**
        """
        engine = GameEngine()
        state = engine.initialise_game(session)

        player_count = len(session.players)

        # current_player_index is a valid index
        assert 0 <= state.current_player_index < player_count

        # The player at that index is a member of the players list
        starting_player = state.players[state.current_player_index]
        player_ids = [p.player_id for p in state.players]
        assert starting_player.player_id in player_ids

    @given(session=game_session_strategy(min_deck_size=7))
    @settings(max_examples=100, deadline=None)
    def test_every_player_has_exactly_7_cards_in_hand(self, session):
        """For any set of players with decks of at least 7 cards, after
        initialisation every player has exactly 7 cards in hand.

        **Validates: Requirements 5.4**
        """
        engine = GameEngine()
        state = engine.initialise_game(session)

        for player in state.players:
            assert len(player.hand) == 7

    @given(session=game_session_small_deck_strategy())
    @settings(max_examples=100, deadline=None)
    def test_players_with_small_decks_get_all_available_cards(self, session):
        """For any set of players where some decks have fewer than 7 cards,
        after initialisation each player has min(7, deck_size) cards in hand.

        **Validates: Requirements 5.4**
        """
        engine = GameEngine()
        state = engine.initialise_game(session)

        for player in state.players:
            # Find the original deck size for this player
            session_player = next(
                sp for sp in session.players if sp.player_id == player.player_id
            )
            expected_hand_size = min(7, len(session_player.deck_cards))
            assert len(player.hand) == expected_hand_size
