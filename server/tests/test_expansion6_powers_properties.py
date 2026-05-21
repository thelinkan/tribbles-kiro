"""Property-based tests for Expansion 6 (Nothing But Tribble) powers.

Uses Hypothesis to verify power activation and effect properties across
randomly generated game states and card configurations.

Properties 58-64: Expansion 6 power effects
- Property 58: Advance playable after sequence break
- Property 59: Assimilate borrows and returns
- Property 60: Convert transforms card placement
- Property 61: IDIC scoring calculation
- Property 62: Masaka replaces all hands with 3 cards
- Property 63: Scan preserves draw deck size
- Property 64: Utilize forces opponent card to play pile and scores

**Validates: Requirements 14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 14.7**
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from models import CardInstance, GameState, PendingPower, PlayerState
from game.powers.resolver import PowerResolver
from game.engine import GameEngine
from game.round_manager import RoundManager
from scoring.service import ScoreService


DENOMINATIONS = [1, 10, 100, 1000, 10000, 100000]
SIMPLE_POWERS = ["go", "skip", "reverse", "discard", "poison", "rescue",
                 "copy", "cycle", "draw", "exchange", "kill", "recycle",
                 "replay", "score", "battle", "evolve", "freeze", "mutate",
                 "process", "toxin", "avalanche", "famine", "stampede",
                 "assimilate", "convert", "masaka", "scan", "utilize"]


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
        expansion_id=6,
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
def game_state_with_players(draw, num_players=None, current_sequence=None,
                            sequence_broken=False):
    """Generate a game state with multiple players for power testing."""
    n_players = num_players if num_players is not None else draw(
        st.integers(min_value=3, max_value=6))
    seq = current_sequence if current_sequence is not None else draw(
        st.sampled_from(DENOMINATIONS))
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
        game_id="prop-test-exp6",
        players=players,
        spectators=[],
        current_player_index=0,
        direction=direction,
        current_sequence=seq,
        last_played_denomination=None,
        sequence_broken=sequence_broken,
        round_number=1,
        frozen_powers={},
        game_status="active",
        reconnection_timeout=30,
        pending_draw=None,
        pending_power=None,
    )
    return state


# --- Property 58: Advance playable after sequence break ---


class TestProperty58AdvancePlayableAfterSequenceBreak:
    """Property 58: Advance playable after sequence break.

    For any game state where the sequence is broken, an Advance card should be
    playable regardless of its denomination.

    **Validates: Requirements 14.1**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_advance_playable_any_denomination_after_break(self, data):
        """Advance card is playable after sequence break regardless of denomination."""
        current_seq = data.draw(st.sampled_from(DENOMINATIONS))
        advance_denom = data.draw(st.sampled_from(DENOMINATIONS))
        state = data.draw(game_state_with_players(
            current_sequence=current_seq, sequence_broken=True
        ))
        engine = GameEngine()

        advance_card = CardInstance(
            card_id=99999,
            card_name="Advance_Test",
            denomination=advance_denom,
            power_text="Advance",
            expansion_id=6,
        )

        result = engine._is_valid_play(advance_card, state)
        assert result is True

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_advance_not_playable_without_break_unless_matches(self, data):
        """Advance card is NOT playable without sequence break unless denomination matches."""
        current_seq = data.draw(st.sampled_from(DENOMINATIONS))
        advance_denom = data.draw(st.sampled_from(DENOMINATIONS))
        assume(advance_denom != current_seq)

        state = data.draw(game_state_with_players(
            current_sequence=current_seq, sequence_broken=False
        ))
        engine = GameEngine()

        advance_card = CardInstance(
            card_id=99999,
            card_name="Advance_Test",
            denomination=advance_denom,
            power_text="Advance",
            expansion_id=6,
        )

        result = engine._is_valid_play(advance_card, state)
        assert result is False



# --- Property 59: Assimilate borrows and returns ---


class TestProperty59AssimilateBorrowsAndReturns:
    """Property 59: Assimilate borrows and returns.

    For any Assimilate power activation, the top card of the target's draw deck
    should move to the active player's play pile as borrowed, and should be
    returned at round end.

    **Validates: Requirements 14.2**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_assimilate_borrows_top_card_from_target(self, data):
        """Assimilate moves top of target's draw deck to active player's play pile."""
        state = data.draw(game_state_with_players(num_players=data.draw(
            st.integers(min_value=3, max_value=5))))
        resolver = PowerResolver()
        player_index = 0

        # Pick a valid target (not self, has draw deck)
        valid_targets = [
            i for i, p in enumerate(state.players)
            if i != player_index and len(p.draw_deck) > 0
        ]
        assume(len(valid_targets) > 0)
        target_index = data.draw(st.sampled_from(valid_targets))

        target_deck_size_before = len(state.players[target_index].draw_deck)
        top_card_id = state.players[target_index].draw_deck[0].card_id
        play_pile_size_before = len(state.players[player_index].play_pile)

        # Activate Assimilate
        power_card = CardInstance(
            card_id=99800, card_name="Assimilate_Power", denomination=100,
            power_text="Assimilate", expansion_id=6,
        )
        resolver.create_power_prompt(state, player_index, power_card)
        resolver.handle_power_choice(state, player_index, {"choice": "activate"})
        events = resolver.handle_power_choice(
            state, player_index, {"target_player_index": target_index}
        )

        assert isinstance(events, list)
        assert events[0]["type"] == "power_activated"
        assert events[0]["power_name"] == "assimilate"

        # Card moved to active player's play pile
        assert len(state.players[player_index].play_pile) == play_pile_size_before + 1
        assert state.players[player_index].play_pile[-1].card_id == top_card_id

        # Target's draw deck reduced by 1
        assert len(state.players[target_index].draw_deck) == target_deck_size_before - 1

        # Card recorded as borrowed
        assert len(state.players[player_index].borrowed_cards) == 1
        borrowed_card, owner_id = state.players[player_index].borrowed_cards[0]
        assert borrowed_card.card_id == top_card_id
        assert owner_id == state.players[target_index].player_id

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_assimilate_borrowed_card_returned_at_round_end(self, data):
        """Borrowed card is returned to original owner at round end."""
        borrowed_card = data.draw(card_strategy(card_id=50000))
        # Create players with enough draw deck for round processing
        draw_deck_p1 = [data.draw(card_strategy(card_id=60000 + i))
                        for i in range(10)]
        draw_deck_p2 = [data.draw(card_strategy(card_id=70000 + i))
                        for i in range(10)]

        players = [
            PlayerState(
                player_id=1, username="Borrower", is_computer=False,
                hand=[], draw_deck=draw_deck_p1,
                play_pile=[borrowed_card],
                discard_pile=[], cumulative_score=0, is_decked=False,
                has_gone_out=True, seat_position=1,
            ),
            PlayerState(
                player_id=2, username="Owner", is_computer=False,
                hand=[], draw_deck=draw_deck_p2,
                play_pile=[], discard_pile=[], cumulative_score=0,
                is_decked=False, has_gone_out=False, seat_position=2,
            ),
        ]
        players[0].borrowed_cards = [(borrowed_card, 2)]

        state = GameState(
            game_id="prop-test-assimilate-return", players=players,
            current_player_index=0, direction=1, current_sequence=1,
        )

        round_manager = RoundManager()
        events = []
        round_manager._return_borrowed_cards(state, events)

        # Borrowed card removed from borrower's play pile
        assert all(c.card_id != borrowed_card.card_id
                   for c in state.players[0].play_pile)
        # Returned to owner's discard pile
        assert any(c.card_id == borrowed_card.card_id
                   for c in state.players[1].discard_pile)
        # Borrowed cards list cleared
        assert len(state.players[0].borrowed_cards) == 0



# --- Property 60: Convert transforms card placement ---


class TestProperty60ConvertTransformsCardPlacement:
    """Property 60: Convert transforms card placement.

    For any Convert power activation, the Convert card should move from the play
    pile to under the draw deck, and the top of the draw deck should move to the
    play pile.

    **Validates: Requirements 14.3**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_convert_moves_card_under_deck_and_draws_top(self, data):
        """Convert card moves under draw deck, top of deck moves to play pile."""
        convert_denom = data.draw(st.sampled_from(DENOMINATIONS))
        deck_size = data.draw(st.integers(min_value=1, max_value=10))

        convert_card = CardInstance(
            card_id=99700, card_name="Convert_Power",
            denomination=convert_denom, power_text="Convert", expansion_id=6,
        )
        draw_deck = [data.draw(card_strategy(card_id=40000 + i))
                     for i in range(deck_size)]
        top_card_id = draw_deck[0].card_id

        players = [
            PlayerState(
                player_id=1, username="Converter", is_computer=False,
                hand=[], draw_deck=draw_deck,
                play_pile=[convert_card],
                discard_pile=[], cumulative_score=0, is_decked=False,
                has_gone_out=False, seat_position=1,
            ),
            PlayerState(
                player_id=2, username="Other", is_computer=False,
                hand=[], draw_deck=[], play_pile=[], discard_pile=[],
                cumulative_score=0, is_decked=False, has_gone_out=False,
                seat_position=2,
            ),
        ]
        state = GameState(
            game_id="prop-test-convert", players=players,
            current_player_index=0, direction=1, current_sequence=100,
        )

        resolver = PowerResolver()
        resolver.create_power_prompt(state, 0, convert_card)
        events = resolver.handle_power_choice(state, 0, {"choice": "activate"})

        assert isinstance(events, list)
        assert events[0]["type"] == "power_activated"
        assert events[0]["power_name"] == "convert"

        # Convert card should be at the bottom of draw deck
        assert state.players[0].draw_deck[-1].card_id == 99700
        # Convert card should NOT be in play pile
        assert all(c.card_id != 99700 for c in state.players[0].play_pile)
        # Top of original deck should now be in play pile
        assert state.players[0].play_pile[-1].card_id == top_card_id

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_convert_deck_size_changes_correctly(self, data):
        """After Convert, draw deck size = original_size - 1 + 1 (net unchanged)."""
        deck_size = data.draw(st.integers(min_value=1, max_value=10))
        convert_card = CardInstance(
            card_id=99700, card_name="Convert_Power",
            denomination=100, power_text="Convert", expansion_id=6,
        )
        draw_deck = [data.draw(card_strategy(card_id=40000 + i))
                     for i in range(deck_size)]

        players = [
            PlayerState(
                player_id=1, username="Converter", is_computer=False,
                hand=[], draw_deck=draw_deck,
                play_pile=[convert_card],
                discard_pile=[], cumulative_score=0, is_decked=False,
                has_gone_out=False, seat_position=1,
            ),
            PlayerState(
                player_id=2, username="Other", is_computer=False,
                hand=[], draw_deck=[], play_pile=[], discard_pile=[],
                cumulative_score=0, is_decked=False, has_gone_out=False,
                seat_position=2,
            ),
        ]
        state = GameState(
            game_id="prop-test-convert-size", players=players,
            current_player_index=0, direction=1, current_sequence=100,
        )

        resolver = PowerResolver()
        resolver.create_power_prompt(state, 0, convert_card)
        resolver.handle_power_choice(state, 0, {"choice": "activate"})

        # Deck: original had deck_size cards. Convert card added to bottom (+1),
        # top card removed to play pile (-1). Net: deck_size unchanged.
        assert len(state.players[0].draw_deck) == deck_size



# --- Property 61: IDIC scoring calculation ---


class TestProperty61IDICScoringCalculation:
    """Property 61: IDIC scoring calculation.

    For any player who went out with IDIC cards in their play pile, the IDIC score
    should equal (number of distinct IDIC denominations) x 10000 x (number of
    unique powers in play pile).

    **Validates: Requirements 14.4**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_idic_score_formula(self, data):
        """IDIC score = distinct_idic_denoms * 10000 * unique_powers."""
        # Generate 1-4 distinct IDIC denominations
        num_idic_denoms = data.draw(st.integers(min_value=1, max_value=4))
        idic_denoms = data.draw(st.lists(
            st.sampled_from(DENOMINATIONS),
            min_size=num_idic_denoms, max_size=num_idic_denoms,
            unique=True,
        ))

        # Create IDIC cards
        idic_cards = [
            CardInstance(
                card_id=30000 + i, card_name=f"IDIC_{d}",
                denomination=d, power_text="IDIC", expansion_id=6,
            )
            for i, d in enumerate(idic_denoms)
        ]

        # Generate 1-5 other cards with distinct powers
        num_other = data.draw(st.integers(min_value=1, max_value=5))
        other_powers = data.draw(st.lists(
            st.sampled_from(["Go", "Skip", "Reverse", "Discard", "Poison",
                             "Rescue", "Copy", "Cycle"]),
            min_size=num_other, max_size=num_other,
            unique=True,
        ))
        other_cards = [
            CardInstance(
                card_id=31000 + i, card_name=f"Other_{p}",
                denomination=data.draw(st.sampled_from(DENOMINATIONS)),
                power_text=p, expansion_id=6,
            )
            for i, p in enumerate(other_powers)
        ]

        play_pile = idic_cards + other_cards

        # Count unique powers (including "idic")
        unique_powers = set()
        for c in play_pile:
            unique_powers.add(c.power_text.lower().strip())

        expected_score = num_idic_denoms * 10000 * len(unique_powers)

        players = [
            PlayerState(
                player_id=1, username="IDICPlayer", is_computer=False,
                hand=[], draw_deck=[], play_pile=play_pile,
                discard_pile=[], cumulative_score=0, is_decked=False,
                has_gone_out=True, seat_position=1,
            ),
        ]
        state = GameState(
            game_id="prop-test-idic", players=players,
            current_player_index=0, direction=1, current_sequence=1,
        )

        score_service = ScoreService()
        idic_scores = score_service.calculate_idic_scores(state)

        assert idic_scores[1] == expected_score

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_idic_same_denomination_does_not_multiply(self, data):
        """Multiple IDIC cards of the same denomination count as 1 distinct denomination."""
        denom = data.draw(st.sampled_from(DENOMINATIONS))
        num_copies = data.draw(st.integers(min_value=2, max_value=4))

        idic_cards = [
            CardInstance(
                card_id=30000 + i, card_name=f"IDIC_{i}",
                denomination=denom, power_text="IDIC", expansion_id=6,
            )
            for i in range(num_copies)
        ]

        # Add one other power card
        other_card = CardInstance(
            card_id=31000, card_name="Other_Go",
            denomination=10, power_text="Go", expansion_id=6,
        )
        play_pile = idic_cards + [other_card]

        # 1 distinct IDIC denom * 10000 * 2 unique powers (idic, go)
        expected_score = 1 * 10000 * 2

        players = [
            PlayerState(
                player_id=1, username="IDICPlayer", is_computer=False,
                hand=[], draw_deck=[], play_pile=play_pile,
                discard_pile=[], cumulative_score=0, is_decked=False,
                has_gone_out=True, seat_position=1,
            ),
        ]
        state = GameState(
            game_id="prop-test-idic-same", players=players,
            current_player_index=0, direction=1, current_sequence=1,
        )

        score_service = ScoreService()
        idic_scores = score_service.calculate_idic_scores(state)

        assert idic_scores[1] == expected_score

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_idic_no_score_if_not_gone_out(self, data):
        """IDIC does not score for players who did not go out."""
        idic_card = CardInstance(
            card_id=30000, card_name="IDIC_100",
            denomination=100, power_text="IDIC", expansion_id=6,
        )
        other_card = CardInstance(
            card_id=31000, card_name="Other_Go",
            denomination=10, power_text="Go", expansion_id=6,
        )

        players = [
            PlayerState(
                player_id=1, username="IDICPlayer", is_computer=False,
                hand=[], draw_deck=[], play_pile=[idic_card, other_card],
                discard_pile=[], cumulative_score=0, is_decked=False,
                has_gone_out=False, seat_position=1,
            ),
        ]
        state = GameState(
            game_id="prop-test-idic-no-out", players=players,
            current_player_index=0, direction=1, current_sequence=1,
        )

        score_service = ScoreService()
        idic_scores = score_service.calculate_idic_scores(state)

        assert idic_scores[1] == 0



# --- Property 62: Masaka replaces all hands with 3 cards ---


class TestProperty62MasakaReplacesAllHandsWith3Cards:
    """Property 62: Masaka replaces all hands with 3 cards.

    For any Masaka power activation, all non-decked players should end up with
    exactly 3 cards in hand (if their draw deck has enough).

    **Validates: Requirements 14.5**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_masaka_all_non_decked_players_get_3_cards(self, data):
        """All non-decked players end up with exactly 3 cards after Masaka."""
        num_players = data.draw(st.integers(min_value=2, max_value=5))

        players = []
        for i in range(num_players):
            hand_size = data.draw(st.integers(min_value=1, max_value=7))
            hand = [
                CardInstance(
                    card_id=i * 1000 + j, card_name=f"H_{i}_{j}",
                    denomination=data.draw(st.sampled_from(DENOMINATIONS)),
                    power_text="Go", expansion_id=6,
                )
                for j in range(hand_size)
            ]
            # Ensure enough cards in draw deck (hand goes under + need 3 to deal)
            deck_size = data.draw(st.integers(min_value=5, max_value=15))
            deck = [
                CardInstance(
                    card_id=i * 1000 + 500 + j, card_name=f"D_{i}_{j}",
                    denomination=data.draw(st.sampled_from(DENOMINATIONS)),
                    power_text="Skip", expansion_id=6,
                )
                for j in range(deck_size)
            ]
            players.append(PlayerState(
                player_id=i + 1, username=f"Player_{i + 1}", is_computer=False,
                hand=hand, draw_deck=deck, play_pile=[], discard_pile=[],
                cumulative_score=0, is_decked=False, has_gone_out=False,
                seat_position=i + 1,
            ))

        state = GameState(
            game_id="prop-test-masaka", players=players,
            current_player_index=0, direction=1, current_sequence=100,
        )

        resolver = PowerResolver()
        power_card = CardInstance(
            card_id=99600, card_name="Masaka_Power",
            denomination=100, power_text="Masaka", expansion_id=6,
        )
        resolver.create_power_prompt(state, 0, power_card)
        events = resolver.handle_power_choice(state, 0, {"choice": "activate"})

        assert isinstance(events, list)

        # All non-decked players should have exactly 3 cards
        for p in state.players:
            if not p.is_decked:
                assert len(p.hand) == 3

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_masaka_skips_decked_players(self, data):
        """Decked players are not affected by Masaka."""
        # Create 3 players, one decked
        hand1 = [CardInstance(card_id=j, card_name=f"H1_{j}", denomination=10,
                              power_text="Go", expansion_id=6) for j in range(1, 5)]
        deck1 = [CardInstance(card_id=500 + j, card_name=f"D1_{j}", denomination=100,
                              power_text="Skip", expansion_id=6) for j in range(10)]
        hand3 = [CardInstance(card_id=2000 + j, card_name=f"H3_{j}", denomination=10,
                              power_text="Go", expansion_id=6) for j in range(1, 4)]
        deck3 = [CardInstance(card_id=2500 + j, card_name=f"D3_{j}", denomination=100,
                              power_text="Skip", expansion_id=6) for j in range(10)]

        players = [
            PlayerState(player_id=1, username="Active", is_computer=False,
                        hand=hand1, draw_deck=deck1, play_pile=[], discard_pile=[],
                        cumulative_score=0, is_decked=False, has_gone_out=False,
                        seat_position=1),
            PlayerState(player_id=2, username="Decked", is_computer=False,
                        hand=[], draw_deck=[], play_pile=[], discard_pile=[],
                        cumulative_score=0, is_decked=True, has_gone_out=False,
                        seat_position=2),
            PlayerState(player_id=3, username="Normal", is_computer=False,
                        hand=hand3, draw_deck=deck3, play_pile=[], discard_pile=[],
                        cumulative_score=0, is_decked=False, has_gone_out=False,
                        seat_position=3),
        ]
        state = GameState(
            game_id="prop-test-masaka-decked", players=players,
            current_player_index=0, direction=1, current_sequence=100,
        )

        resolver = PowerResolver()
        power_card = CardInstance(
            card_id=99600, card_name="Masaka_Power",
            denomination=100, power_text="Masaka", expansion_id=6,
        )
        resolver.create_power_prompt(state, 0, power_card)
        events = resolver.handle_power_choice(state, 0, {"choice": "activate"})

        assert isinstance(events, list)
        # Non-decked players get 3 cards
        assert len(state.players[0].hand) == 3
        assert len(state.players[2].hand) == 3
        # Decked player unchanged
        assert len(state.players[1].hand) == 0



# --- Property 63: Scan preserves draw deck size ---


class TestProperty63ScanPreservesDrawDeckSize:
    """Property 63: Scan preserves draw deck size.

    For any Scan power activation, the draw deck size should remain unchanged
    after reordering.

    **Validates: Requirements 14.6**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_scan_preserves_deck_size_top_placement(self, data):
        """Draw deck size unchanged after Scan with top placement."""
        deck_size = data.draw(st.integers(min_value=3, max_value=12))
        draw_deck = [
            CardInstance(
                card_id=20000 + i, card_name=f"Deck_{i}",
                denomination=data.draw(st.sampled_from(DENOMINATIONS)),
                power_text="Go", expansion_id=6,
            )
            for i in range(deck_size)
        ]

        players = [
            PlayerState(
                player_id=1, username="Scanner", is_computer=False,
                hand=[], draw_deck=draw_deck, play_pile=[], discard_pile=[],
                cumulative_score=0, is_decked=False, has_gone_out=False,
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
            game_id="prop-test-scan-top", players=players,
            current_player_index=0, direction=1, current_sequence=100,
        )

        resolver = PowerResolver()
        power_card = CardInstance(
            card_id=99500, card_name="Scan_Power",
            denomination=100, power_text="Scan", expansion_id=6,
        )
        resolver.create_power_prompt(state, 0, power_card)
        # Activate to get the reveal prompt
        resolver.handle_power_choice(state, 0, {"choice": "activate"})

        # Get the top 3 card IDs and shuffle them for reorder
        num_revealed = min(3, deck_size)
        revealed_ids = [draw_deck[i].card_id for i in range(num_revealed)]
        # Reverse order as a simple reorder
        reordered_ids = list(reversed(revealed_ids))

        events = resolver.handle_power_choice(
            state, 0, {"card_ids": reordered_ids, "placement": "top"}
        )

        assert isinstance(events, list)
        assert events[0]["type"] == "power_activated"
        assert events[0]["power_name"] == "scan"
        # Deck size preserved
        assert len(state.players[0].draw_deck) == deck_size

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_scan_preserves_deck_size_bottom_placement(self, data):
        """Draw deck size unchanged after Scan with bottom placement."""
        deck_size = data.draw(st.integers(min_value=3, max_value=12))
        draw_deck = [
            CardInstance(
                card_id=20000 + i, card_name=f"Deck_{i}",
                denomination=data.draw(st.sampled_from(DENOMINATIONS)),
                power_text="Go", expansion_id=6,
            )
            for i in range(deck_size)
        ]

        players = [
            PlayerState(
                player_id=1, username="Scanner", is_computer=False,
                hand=[], draw_deck=draw_deck, play_pile=[], discard_pile=[],
                cumulative_score=0, is_decked=False, has_gone_out=False,
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
            game_id="prop-test-scan-bottom", players=players,
            current_player_index=0, direction=1, current_sequence=100,
        )

        resolver = PowerResolver()
        power_card = CardInstance(
            card_id=99500, card_name="Scan_Power",
            denomination=100, power_text="Scan", expansion_id=6,
        )
        resolver.create_power_prompt(state, 0, power_card)
        resolver.handle_power_choice(state, 0, {"choice": "activate"})

        # Get the top 3 card IDs
        num_revealed = min(3, deck_size)
        revealed_ids = [draw_deck[i].card_id for i in range(num_revealed)]
        reordered_ids = list(reversed(revealed_ids))

        events = resolver.handle_power_choice(
            state, 0, {"card_ids": reordered_ids, "placement": "bottom"}
        )

        assert isinstance(events, list)
        assert events[0]["type"] == "power_activated"
        # Deck size preserved
        assert len(state.players[0].draw_deck) == deck_size



# --- Property 64: Utilize forces opponent card to play pile and scores ---


class TestProperty64UtilizeForcesOpponentCardToPlayPileAndScores:
    """Property 64: Utilize forces opponent card to play pile and scores.

    For any Utilize power activation targeting an opponent with >=2 cards, one
    card should move from target's hand to their play pile, and the active player
    should score that card's denomination.

    **Validates: Requirements 14.7**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_utilize_moves_card_from_target_hand_to_play_pile(self, data):
        """Utilize moves one card from target's hand to their play pile."""
        state = data.draw(game_state_with_players(num_players=data.draw(
            st.integers(min_value=3, max_value=5))))
        resolver = PowerResolver()
        player_index = 0

        # Find valid targets (not self, has >= 2 cards in hand)
        valid_targets = [
            i for i, p in enumerate(state.players)
            if i != player_index and len(p.hand) >= 2
        ]
        assume(len(valid_targets) > 0)
        target_index = data.draw(st.sampled_from(valid_targets))

        target_hand_size_before = len(state.players[target_index].hand)
        target_pile_size_before = len(state.players[target_index].play_pile)
        active_score_before = state.players[player_index].cumulative_score

        # Activate Utilize
        power_card = CardInstance(
            card_id=99400, card_name="Utilize_Power",
            denomination=100, power_text="Utilize", expansion_id=6,
        )
        resolver.create_power_prompt(state, player_index, power_card)
        resolver.handle_power_choice(state, player_index, {"choice": "activate"})
        events = resolver.handle_power_choice(
            state, player_index, {"target_player_index": target_index}
        )

        assert isinstance(events, list)
        assert events[0]["type"] == "power_activated"
        assert events[0]["power_name"] == "utilize"

        # Target lost 1 card from hand
        assert len(state.players[target_index].hand) == target_hand_size_before - 1
        # Target gained 1 card in play pile
        assert len(state.players[target_index].play_pile) == target_pile_size_before + 1

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_utilize_active_player_scores_card_denomination(self, data):
        """Active player scores the denomination of the utilized card."""
        state = data.draw(game_state_with_players(num_players=data.draw(
            st.integers(min_value=3, max_value=5))))
        resolver = PowerResolver()
        player_index = 0

        # Find valid targets
        valid_targets = [
            i for i, p in enumerate(state.players)
            if i != player_index and len(p.hand) >= 2
        ]
        assume(len(valid_targets) > 0)
        target_index = data.draw(st.sampled_from(valid_targets))

        active_score_before = state.players[player_index].cumulative_score
        # Sum of all possible denominations in target's hand (to verify score increased)
        target_hand_denoms = [c.denomination for c in state.players[target_index].hand]

        # Activate Utilize
        power_card = CardInstance(
            card_id=99400, card_name="Utilize_Power",
            denomination=100, power_text="Utilize", expansion_id=6,
        )
        resolver.create_power_prompt(state, player_index, power_card)
        resolver.handle_power_choice(state, player_index, {"choice": "activate"})
        events = resolver.handle_power_choice(
            state, player_index, {"target_player_index": target_index}
        )

        assert isinstance(events, list)
        scored_denom = events[0]["utilized_card_denomination"]

        # The scored denomination should be one of the target's original hand denominations
        assert scored_denom in target_hand_denoms
        # Active player's score increased by that denomination
        assert state.players[player_index].cumulative_score == active_score_before + scored_denom
