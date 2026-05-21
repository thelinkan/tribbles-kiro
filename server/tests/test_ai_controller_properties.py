"""Property-based tests for the AI_Controller decision-making.

Uses Hypothesis to verify that AI actions are always valid according to
the game rules enforced by GameEngine.process_action.

Property 14: AI actions are always valid
- For any game state where it is a computer player's turn, the action
  chosen by the AI_Controller should be a valid action according to the
  current game rules.

**Validates: Requirements 4.7, 4.8**
"""

import sys
import os

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ai.controller import AIController
from game.engine import GameEngine
from models import CardInstance, GameState, PendingDraw, PlayerState


# --- Strategies ---

VALID_DENOMINATIONS = [1, 10, 100, 1000, 10000, 100000]

VALID_POWERS = [
    "Go", "Skip", "Poison", "Rescue", "Reverse", "Clone", "Discard",
    "Cycle", "Recycle", "Replay", "Process", "Evolve", "Mutate",
    "Draw", "Exchange", "Advance", "Convert", "Masaka", "Scan",
    "Utilize", "Freeze", "Kill", "Score", "Battle", "Toxin",
    "Avalanche", "Stampede", "Assimilate", "Copy", "Bonus",
    "Quadruple", "Safety", "Tally", "Antidote", "IDIC",
    "Clone & Reverse", "Clone & Go", "Clone & Skip",
]


@st.composite
def card_instance_strategy(draw, card_id=None):
    """Generate a random CardInstance with a valid denomination and power."""
    cid = card_id if card_id is not None else draw(
        st.integers(min_value=1, max_value=10000)
    )
    denomination = draw(st.sampled_from(VALID_DENOMINATIONS))
    power_text = draw(st.sampled_from(VALID_POWERS))
    expansion_id = draw(st.integers(min_value=1, max_value=6))
    return CardInstance(
        card_id=cid,
        card_name=f"Tribble_{cid}",
        denomination=denomination,
        power_text=power_text,
        expansion_id=expansion_id,
    )


@st.composite
def hand_strategy(draw, min_size=0, max_size=10, start_card_id=1):
    """Generate a hand of cards with unique card_ids."""
    size = draw(st.integers(min_value=min_size, max_value=max_size))
    cards = []
    for i in range(size):
        card = draw(card_instance_strategy(card_id=start_card_id + i))
        cards.append(card)
    return cards


@st.composite
def draw_deck_strategy(draw, min_size=0, max_size=20, start_card_id=100):
    """Generate a draw deck of cards with unique card_ids."""
    size = draw(st.integers(min_value=min_size, max_value=max_size))
    cards = []
    for i in range(size):
        card = draw(card_instance_strategy(card_id=start_card_id + i))
        cards.append(card)
    return cards


@st.composite
def player_state_strategy(draw, player_id, seat_position, is_current=False):
    """Generate a random PlayerState.

    If is_current=True, ensures the player has at least a draw deck
    (so draw_card is always possible unless decked).
    """
    hand_start = player_id * 1000
    deck_start = player_id * 1000 + 100

    hand = draw(hand_strategy(
        min_size=0 if not is_current else 0,
        max_size=10,
        start_card_id=hand_start,
    ))
    draw_deck = draw(draw_deck_strategy(
        min_size=1,  # At least 1 card so draw is possible
        max_size=20,
        start_card_id=deck_start,
    ))
    cumulative_score = draw(st.integers(min_value=0, max_value=500000))

    return PlayerState(
        player_id=player_id,
        username=f"Player_{player_id}",
        is_computer=True,
        hand=hand,
        draw_deck=draw_deck,
        play_pile=[],
        discard_pile=[],
        cumulative_score=cumulative_score,
        is_decked=False,
        has_gone_out=False,
        seat_position=seat_position,
    )


@st.composite
def game_state_normal_turn_strategy(draw):
    """Generate a game state for a normal turn (no pending draw/power).

    The current player is a computer player whose turn it is.
    """
    num_players = draw(st.integers(min_value=4, max_value=8))
    current_player_index = draw(st.integers(min_value=0, max_value=num_players - 1))

    players = []
    for i in range(num_players):
        player = draw(player_state_strategy(
            player_id=i + 1,
            seat_position=i + 1,
            is_current=(i == current_player_index),
        ))
        players.append(player)

    current_sequence = draw(st.sampled_from(VALID_DENOMINATIONS))
    sequence_broken = draw(st.booleans())
    last_played_denomination = draw(
        st.one_of(st.none(), st.sampled_from(VALID_DENOMINATIONS))
    )

    return GameState(
        game_id="test-ai-prop",
        players=players,
        current_player_index=current_player_index,
        current_sequence=current_sequence,
        last_played_denomination=last_played_denomination,
        sequence_broken=sequence_broken,
        round_number=1,
        game_status="active",
        pending_draw=None,
        pending_power=None,
    )


@st.composite
def game_state_pending_draw_strategy(draw):
    """Generate a game state with a pending draw for the current player.

    The pending draw can be either matching or non-matching.
    """
    num_players = draw(st.integers(min_value=4, max_value=8))
    current_player_index = draw(st.integers(min_value=0, max_value=num_players - 1))

    players = []
    for i in range(num_players):
        player = draw(player_state_strategy(
            player_id=i + 1,
            seat_position=i + 1,
            is_current=(i == current_player_index),
        ))
        players.append(player)

    current_sequence = draw(st.sampled_from(VALID_DENOMINATIONS))
    matches_sequence = draw(st.booleans())

    # The drawn card
    if matches_sequence:
        drawn_denomination = current_sequence
    else:
        non_matching = [d for d in VALID_DENOMINATIONS if d != current_sequence]
        drawn_denomination = draw(st.sampled_from(non_matching))

    drawn_card_id = 9999
    drawn_card = CardInstance(
        card_id=drawn_card_id,
        card_name="DrawnTribble",
        denomination=drawn_denomination,
        power_text=draw(st.sampled_from(VALID_POWERS)),
        expansion_id=1,
    )

    # The drawn card must be in the player's hand (engine checks this)
    current_player = players[current_player_index]
    current_player.hand.append(drawn_card)

    pending_draw = PendingDraw(
        player_id=current_player.player_id,
        card=drawn_card,
        matches_sequence=matches_sequence,
    )

    return GameState(
        game_id="test-ai-prop",
        players=players,
        current_player_index=current_player_index,
        current_sequence=current_sequence,
        last_played_denomination=draw(
            st.one_of(st.none(), st.sampled_from(VALID_DENOMINATIONS))
        ),
        sequence_broken=draw(st.booleans()),
        round_number=1,
        game_status="active",
        pending_draw=pending_draw,
        pending_power=None,
    )


# --- Property Tests ---

class TestProperty14AIActionsAreAlwaysValid:
    """Property 14: AI actions are always valid.

    For any game state where it is a computer player's turn, the action
    chosen by the AI_Controller should be a valid action according to the
    current game rules.

    **Validates: Requirements 4.7, 4.8**
    """

    @given(state=game_state_normal_turn_strategy())
    @settings(max_examples=100, deadline=None)
    def test_ai_normal_turn_action_is_valid(self, state):
        """For any game state on a normal turn (no pending draw), the AI
        chooses an action that is accepted by GameEngine.process_action.

        **Validates: Requirements 4.7, 4.8**
        """
        ai = AIController()
        engine = GameEngine()

        # Register the game state with the engine
        engine._games[state.game_id] = state

        current_player = state.players[state.current_player_index]
        player_id = current_player.player_id

        # AI chooses an action
        action = ai.choose_action(state, player_id)

        # The action must be one of the valid types
        assert action["type"] in ("play_card", "draw_card", "accept_draw", "power_choice")

        # Process the action through the engine
        result = engine.process_action(state.game_id, player_id, action)

        # A valid action returns a list of events, not an error tuple
        assert isinstance(result, list), (
            f"AI action {action} was rejected by engine: {result}"
        )

    @given(state=game_state_pending_draw_strategy())
    @settings(max_examples=100, deadline=None)
    def test_ai_pending_draw_action_is_valid(self, state):
        """For any game state with a pending draw for the current player,
        the AI chooses an action that is accepted by GameEngine.process_action.

        **Validates: Requirements 4.7, 4.8**
        """
        ai = AIController()
        engine = GameEngine()

        # Register the game state with the engine
        engine._games[state.game_id] = state

        current_player = state.players[state.current_player_index]
        player_id = current_player.player_id

        # AI chooses an action
        action = ai.choose_action(state, player_id)

        # For pending draws, valid actions are play_card (matching) or accept_draw
        assert action["type"] in ("play_card", "accept_draw")

        # Process the action through the engine
        result = engine.process_action(state.game_id, player_id, action)

        # A valid action returns a list of events, not an error tuple
        assert isinstance(result, list), (
            f"AI action {action} was rejected by engine: {result}"
        )
