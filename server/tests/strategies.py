"""Shared Hypothesis strategies for the Tribbles test suite.

Provides reusable composite strategies for generating valid game objects
across all property-based test files.

**Validates: Requirements 18.3**
"""

import sys
import os

from hypothesis import strategies as st

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from models import CardInstance, GameState, PlayerState


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DENOMINATIONS = [1, 10, 100, 1000, 10000, 100000]

BASIC_POWERS = [
    "Go", "Skip", "Poison", "Rescue", "Reverse", "Clone", "Discard",
]

EXPANSION_POWERS = [
    "Go", "Skip", "Poison", "Rescue", "Reverse", "Clone", "Discard",
    "Copy", "Cycle", "Draw", "Exchange", "Kill", "Recycle", "Replay", "Score",
    "Battle", "Evolve", "Freeze", "Mutate", "Process", "Quadruple", "Safety",
    "Tally", "Toxin",
    "Advance", "Avalanche", "Convert", "Famine", "Masaka", "Stampede",
    "Antidote", "Assimilate", "Bonus", "IDIC", "Scan", "Utilize",
]

COMPOUND_POWERS = [
    "Clone & Reverse", "Clone & Go", "Clone & Skip", "Clone & Discard",
    "Go & Reverse", "Skip & Reverse", "Poison & Go",
]


# ---------------------------------------------------------------------------
# Card strategies
# ---------------------------------------------------------------------------


@st.composite
def valid_card_instance(draw, card_id=None, denomination=None, power_text=None):
    """Generate a random CardInstance.

    Args:
        card_id: Fixed card_id, or None to generate randomly.
        denomination: Fixed denomination, or None to pick from valid values.
        power_text: Fixed power text, or None to pick from known powers.

    Returns:
        A valid CardInstance.
    """
    cid = card_id if card_id is not None else draw(
        st.integers(min_value=1, max_value=100000)
    )
    denom = denomination if denomination is not None else draw(
        st.sampled_from(DENOMINATIONS)
    )
    name = draw(
        st.text(
            min_size=1,
            max_size=20,
            alphabet=st.characters(whitelist_categories=("L", "N")),
        )
    )
    power = power_text if power_text is not None else draw(
        st.sampled_from(EXPANSION_POWERS)
    )
    expansion_id = draw(st.integers(min_value=1, max_value=6))

    return CardInstance(
        card_id=cid,
        card_name=name,
        denomination=denom,
        power_text=power,
        expansion_id=expansion_id,
    )


@st.composite
def valid_hand(draw, min_cards=0, max_cards=7):
    """Generate a random hand of CardInstance objects with unique card_ids.

    Args:
        min_cards: Minimum number of cards in hand.
        max_cards: Maximum number of cards in hand.

    Returns:
        A list of CardInstance objects.
    """
    size = draw(st.integers(min_value=min_cards, max_value=max_cards))
    cards = []
    for i in range(size):
        card = draw(valid_card_instance(card_id=i + 1))
        cards.append(card)
    return cards


@st.composite
def valid_play_pile(draw, min_cards=0, max_cards=10):
    """Generate a random play pile of CardInstance objects with unique card_ids.

    Args:
        min_cards: Minimum number of cards in pile.
        max_cards: Maximum number of cards in pile.

    Returns:
        A list of CardInstance objects.
    """
    size = draw(st.integers(min_value=min_cards, max_value=max_cards))
    cards = []
    for i in range(size):
        card = draw(valid_card_instance(card_id=1000 + i + 1))
        cards.append(card)
    return cards


@st.composite
def valid_draw_deck(draw, min_cards=0, max_cards=20):
    """Generate a random draw deck of CardInstance objects with unique card_ids.

    Args:
        min_cards: Minimum number of cards in deck.
        max_cards: Maximum number of cards in deck.

    Returns:
        A list of CardInstance objects.
    """
    size = draw(st.integers(min_value=min_cards, max_value=max_cards))
    cards = []
    for i in range(size):
        card = draw(valid_card_instance(card_id=2000 + i + 1))
        cards.append(card)
    return cards


# ---------------------------------------------------------------------------
# Game state strategies
# ---------------------------------------------------------------------------


@st.composite
def valid_game_state(draw, num_players=None, current_sequence=None, sequence_broken=None):
    """Generate a full, internally consistent GameState.

    Args:
        num_players: Fixed player count (4-8), or None to generate randomly.
        current_sequence: Fixed sequence denomination, or None to pick randomly.
        sequence_broken: Fixed sequence_broken flag, or None to pick randomly.

    Returns:
        A valid GameState with consistent player states.
    """
    n_players = num_players if num_players is not None else draw(
        st.integers(min_value=4, max_value=8)
    )
    seq = current_sequence if current_sequence is not None else draw(
        st.sampled_from(DENOMINATIONS)
    )
    broken = sequence_broken if sequence_broken is not None else draw(st.booleans())

    players = []
    for i in range(n_players):
        pid = i + 1
        id_base = pid * 1000

        hand = draw(st.lists(
            valid_card_instance(card_id=None),
            min_size=1,
            max_size=7,
        ).map(lambda cards: [
            CardInstance(
                card_id=id_base + j,
                card_name=c.card_name,
                denomination=c.denomination,
                power_text=c.power_text,
                expansion_id=c.expansion_id,
            )
            for j, c in enumerate(cards)
        ]))

        draw_deck_cards = draw(st.lists(
            valid_card_instance(card_id=None),
            min_size=1,
            max_size=15,
        ).map(lambda cards: [
            CardInstance(
                card_id=id_base + 100 + j,
                card_name=c.card_name,
                denomination=c.denomination,
                power_text=c.power_text,
                expansion_id=c.expansion_id,
            )
            for j, c in enumerate(cards)
        ]))

        play_pile_cards = draw(st.lists(
            valid_card_instance(card_id=None),
            min_size=0,
            max_size=8,
        ).map(lambda cards: [
            CardInstance(
                card_id=id_base + 200 + j,
                card_name=c.card_name,
                denomination=c.denomination,
                power_text=c.power_text,
                expansion_id=c.expansion_id,
            )
            for j, c in enumerate(cards)
        ]))

        discard_pile_cards = draw(st.lists(
            valid_card_instance(card_id=None),
            min_size=0,
            max_size=5,
        ).map(lambda cards: [
            CardInstance(
                card_id=id_base + 300 + j,
                card_name=c.card_name,
                denomination=c.denomination,
                power_text=c.power_text,
                expansion_id=c.expansion_id,
            )
            for j, c in enumerate(cards)
        ]))

        score = draw(st.integers(min_value=0, max_value=500000))

        player = PlayerState(
            player_id=pid,
            username=f"Player_{pid}",
            is_computer=draw(st.booleans()),
            hand=hand,
            draw_deck=draw_deck_cards,
            play_pile=play_pile_cards,
            discard_pile=discard_pile_cards,
            cumulative_score=score,
            is_decked=False,
            has_gone_out=False,
            seat_position=i + 1,
        )
        players.append(player)

    current_player_index = draw(st.integers(min_value=0, max_value=n_players - 1))
    direction = draw(st.sampled_from([1, -1]))
    round_number = draw(st.integers(min_value=1, max_value=5))
    timeout = draw(st.integers(min_value=5, max_value=120))

    return GameState(
        game_id="test-game",
        players=players,
        spectators=[],
        current_player_index=current_player_index,
        direction=direction,
        current_sequence=seq,
        last_played_denomination=draw(st.one_of(st.none(), st.sampled_from(DENOMINATIONS))),
        sequence_broken=broken,
        round_number=round_number,
        frozen_powers={},
        game_status="active",
        reconnection_timeout=timeout,
    )


# ---------------------------------------------------------------------------
# Deck data strategy
# ---------------------------------------------------------------------------


@st.composite
def valid_deck_data(draw):
    """Generate random deck save data matching the Deck_Service save format.

    Returns:
        A dict with deck_name, is_public, comment_text, and cards list.
        Each card entry has card_id and quantity.
    """
    deck_name = draw(st.text(
        min_size=1,
        max_size=50,
        alphabet=st.characters(whitelist_categories=("L", "N", "Zs")),
    ))
    is_public = draw(st.booleans())
    comment_text = draw(st.text(
        min_size=0,
        max_size=200,
        alphabet=st.characters(whitelist_categories=("L", "N", "Zs", "P")),
    ))

    # Generate card entries with unique card_ids
    num_entries = draw(st.integers(min_value=1, max_value=20))
    cards = []
    for i in range(num_entries):
        cards.append({
            "card_id": i + 1,
            "quantity": draw(st.integers(min_value=1, max_value=4)),
        })

    return {
        "deck_name": deck_name,
        "is_public": is_public,
        "comment_text": comment_text,
        "cards": cards,
    }


# ---------------------------------------------------------------------------
# Credentials strategy
# ---------------------------------------------------------------------------


@st.composite
def valid_credentials(draw):
    """Generate a random valid (username, password, email) tuple.

    Returns:
        A tuple of (username, password, email) with valid formats.
    """
    username = draw(st.text(
        alphabet=st.characters(min_codepoint=33, max_codepoint=126),
        min_size=1,
        max_size=30,
    ))
    password = draw(st.text(
        alphabet=st.characters(min_codepoint=32, max_codepoint=126),
        min_size=1,
        max_size=50,
    ))
    email = draw(st.from_regex(
        r"[a-z][a-z0-9]{0,10}@[a-z]{2,8}\.[a-z]{2,4}",
        fullmatch=True,
    ))

    return (username, password, email)


# ---------------------------------------------------------------------------
# Power-specific card strategies
# ---------------------------------------------------------------------------


@st.composite
def card_with_power(draw, power_name):
    """Generate a CardInstance with a specific power.

    Args:
        power_name: The power text to assign to the card.

    Returns:
        A CardInstance with the specified power.
    """
    return draw(valid_card_instance(power_text=power_name))


@st.composite
def compound_power_card(draw):
    """Generate a CardInstance with a compound power (e.g., "Clone & Reverse").

    Returns:
        A CardInstance with a compound power from the known compound powers list.
    """
    power = draw(st.sampled_from(COMPOUND_POWERS))
    return draw(valid_card_instance(power_text=power))


# ---------------------------------------------------------------------------
# Disconnected game state strategy
# ---------------------------------------------------------------------------


@st.composite
def disconnected_game_state(draw):
    """Generate a GameState with some players marked as disconnected.

    At least one player will be non-disconnected (to be the active player),
    and at least one player will be disconnected.

    Returns:
        A GameState where some players have is_disconnected-like state.
        Note: Actual DisconnectionState tracking is managed by DisconnectionManager,
        but this strategy creates a game state suitable for testing disconnection
        scenarios by marking some players as computer-controlled (simulating
        AI_Substitute activation).
    """
    state = draw(valid_game_state(num_players=draw(st.integers(min_value=4, max_value=8))))

    # Ensure the active player is human (not computer)
    state.players[state.current_player_index].is_computer = False

    # Mark at least one (but not all) players as "disconnected" by setting
    # is_computer=True to simulate AI_Substitute taking over
    eligible_indices = [
        i for i in range(len(state.players))
        if i != state.current_player_index
    ]

    num_to_disconnect = draw(st.integers(min_value=1, max_value=len(eligible_indices)))
    disconnect_indices = draw(
        st.permutations(eligible_indices).map(lambda p: p[:num_to_disconnect])
    )

    for idx in disconnect_indices:
        state.players[idx].is_computer = True

    # Ensure non-disconnected players (other than active) remain human
    # (only the explicitly disconnected ones become computer)
    for i in range(len(state.players)):
        if i != state.current_player_index and i not in disconnect_indices:
            state.players[i].is_computer = False

    return state
