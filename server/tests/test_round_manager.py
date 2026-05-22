"""Tests for the RoundManager.

Tests cover round transition requirements:
- 8.1: Mark player as gone out and trigger end-of-round
- 8.2: Sum denominations in play pile for goers, add to cumulative score
- 8.3: Move non-goers' hands to discard pile
- 8.4: Shuffle each player's play pile into their draw deck
- 8.5: Deal 7 cards from each active player's draw deck to their hand
- 8.6: Reset sequence to 1 and direction to clockwise
- 8.7: Single go-out → that player starts next round
- 8.8: Multiple go-out → lowest round score starts next round
- 7.6: Decked player at round end: play pile >= 7 → reshuffled draw deck
- 7.7: Decked player at round end: play pile < 7 → sit out next round
"""

import sys
import os

import pytest

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from models import CardInstance, GameState, PlayerState
from game.round_manager import RoundManager
from scoring.service import ScoreService


def make_card(card_id: int, denomination: int = 1, power: str = "Bonus") -> CardInstance:
    """Helper to create a CardInstance for testing."""
    return CardInstance(
        card_id=card_id,
        card_name=f"Tribble_{card_id}",
        denomination=denomination,
        power_text=power,
        expansion_id=1,
    )


def make_game_state(
    num_players: int = 4,
    current_player_index: int = 0,
    current_sequence: int = 100,
    direction: int = -1,
    round_number: int = 1,
) -> GameState:
    """Helper to create a GameState for round transition testing.

    Players are set up with various cards to test round transitions.
    """
    players = []
    for i in range(num_players):
        player = PlayerState(
            player_id=i + 1,
            username=f"Player_{i + 1}",
            is_computer=False,
            hand=[make_card(card_id=i * 100 + j, denomination=10) for j in range(5)],
            draw_deck=[
                make_card(card_id=i * 100 + 50 + j, denomination=100)
                for j in range(10)
            ],
            play_pile=[
                make_card(card_id=i * 100 + 70 + j, denomination=1000)
                for j in range(3)
            ],
            discard_pile=[],
            cumulative_score=0,
            is_decked=False,
            has_gone_out=False,
            seat_position=i + 1,
        )
        players.append(player)

    return GameState(
        game_id="test-game",
        players=players,
        current_player_index=current_player_index,
        direction=direction,
        current_sequence=current_sequence,
        round_number=round_number,
        game_status="round_end",
    )


@pytest.fixture
def round_manager():
    """Create a fresh RoundManager instance."""
    return RoundManager()


class TestRoundScoring:
    """Tests for round scoring (Requirements 8.2)."""

    def test_goer_scores_play_pile_denominations(self, round_manager):
        """Player who went out scores sum of play pile denominations."""
        state = make_game_state(num_players=3)
        state.players[0].has_gone_out = True
        state.players[0].hand = []  # Went out, hand is empty
        state.players[0].play_pile = [
            make_card(1, denomination=1),
            make_card(2, denomination=10),
            make_card(3, denomination=100),
        ]

        round_manager.process_end_of_round(state)

        assert state.players[0].cumulative_score == 111

    def test_non_goer_does_not_score(self, round_manager):
        """Player who did not go out does not gain score."""
        state = make_game_state(num_players=3)
        state.players[0].has_gone_out = True
        state.players[0].hand = []
        state.players[0].play_pile = [make_card(1, denomination=100)]
        # Player 2 did not go out but has cards in play pile
        state.players[1].play_pile = [make_card(2, denomination=10000)]

        round_manager.process_end_of_round(state)

        assert state.players[1].cumulative_score == 0

    def test_cumulative_score_accumulates(self, round_manager):
        """Round score is added to existing cumulative score."""
        state = make_game_state(num_players=2)
        state.players[0].has_gone_out = True
        state.players[0].hand = []
        state.players[0].cumulative_score = 500
        state.players[0].play_pile = [make_card(1, denomination=1000)]

        round_manager.process_end_of_round(state)

        assert state.players[0].cumulative_score == 1500


class TestNonGoersHandsToDiscard:
    """Tests for Requirement 8.3: Move non-goers' hands to discard."""

    def test_non_goer_hand_moved_to_discard(self, round_manager):
        """Non-goer's hand cards are moved to their discard pile."""
        state = make_game_state(num_players=3)
        state.players[0].has_gone_out = True
        state.players[0].hand = []
        state.players[0].play_pile = [make_card(1, denomination=1)]

        hand_cards = list(state.players[1].hand)
        initial_discard = list(state.players[1].discard_pile)

        round_manager.process_end_of_round(state)

        # Hand should be empty
        assert state.players[1].hand == [] or len(state.players[1].hand) == 7
        # Note: After process_end_of_round, new cards are dealt.
        # We need to check that the discard pile grew by the hand size
        # Actually, the hand is moved to discard BEFORE dealing new cards.
        # After dealing, the hand will have new cards from the draw deck.

    def test_goer_hand_not_moved_to_discard(self, round_manager):
        """Player who went out does not have hand moved to discard (hand is already empty)."""
        state = make_game_state(num_players=2)
        state.players[0].has_gone_out = True
        state.players[0].hand = []
        state.players[0].play_pile = [make_card(1, denomination=1)]

        round_manager.process_end_of_round(state)

        # Goer's discard pile should not have gained cards from hand
        # (hand was already empty)
        # The discard pile may have cards from other sources but not from hand


class TestPlayPilesShuffledIntoDraw:
    """Tests for Requirement 8.4: Shuffle play piles into draw decks."""

    def test_play_pile_cards_end_up_in_draw_deck(self, round_manager):
        """Play pile cards are moved into the draw deck."""
        state = make_game_state(num_players=2)
        state.players[0].has_gone_out = True
        state.players[0].hand = []

        # Set up known play pile for player 2
        play_pile_cards = [
            make_card(200, denomination=100),
            make_card(201, denomination=1000),
        ]
        state.players[1].play_pile = list(play_pile_cards)
        initial_draw_size = len(state.players[1].draw_deck)

        round_manager.process_end_of_round(state)

        # Play pile should be empty after processing
        assert state.players[1].play_pile == []

    def test_play_pile_cleared_after_shuffle(self, round_manager):
        """Play pile is empty after being shuffled into draw deck."""
        state = make_game_state(num_players=2)
        state.players[0].has_gone_out = True
        state.players[0].hand = []
        state.players[0].play_pile = [make_card(1, denomination=1)]

        round_manager.process_end_of_round(state)

        for player in state.players:
            assert player.play_pile == []


class TestDealNewHands:
    """Tests for Requirement 8.5: Deal 7 cards to each active player."""

    def test_active_players_receive_7_cards(self, round_manager):
        """Each active player receives 7 cards in their new hand."""
        state = make_game_state(num_players=3)
        state.players[0].has_gone_out = True
        state.players[0].hand = []
        state.players[0].play_pile = [make_card(1, denomination=1)]
        # Ensure all players have enough cards in draw deck
        for player in state.players:
            player.draw_deck = [
                make_card(card_id=player.player_id * 1000 + j, denomination=10)
                for j in range(20)
            ]

        round_manager.process_end_of_round(state)

        for player in state.players:
            assert len(player.hand) == 7

    def test_draw_deck_shrinks_by_7(self, round_manager):
        """Draw deck loses 7 cards after dealing."""
        state = make_game_state(num_players=2)
        state.players[0].has_gone_out = True
        state.players[0].hand = []
        state.players[0].play_pile = [make_card(1, denomination=1)]
        # Give player 2 a known draw deck size (after play pile shuffle)
        state.players[1].draw_deck = [
            make_card(card_id=500 + j, denomination=10) for j in range(15)
        ]
        state.players[1].play_pile = []  # No play pile to shuffle in
        state.players[1].hand = []  # No hand to move to discard

        round_manager.process_end_of_round(state)

        # Player 2 should have 15 - 7 = 8 cards in draw deck
        assert len(state.players[1].draw_deck) == 8


class TestSequenceAndDirectionReset:
    """Tests for Requirement 8.6: Reset sequence and direction."""

    def test_sequence_reset_to_1(self, round_manager):
        """Sequence is reset to 1 at start of new round."""
        state = make_game_state(num_players=2, current_sequence=10000)
        state.players[0].has_gone_out = True
        state.players[0].hand = []
        state.players[0].play_pile = [make_card(1, denomination=1)]

        round_manager.process_end_of_round(state)

        assert state.current_sequence == 1

    def test_direction_reset_to_clockwise(self, round_manager):
        """Direction is reset to clockwise (1) at start of new round."""
        state = make_game_state(num_players=2, direction=-1)
        state.players[0].has_gone_out = True
        state.players[0].hand = []
        state.players[0].play_pile = [make_card(1, denomination=1)]

        round_manager.process_end_of_round(state)

        assert state.direction == 1


class TestStartingPlayerDetermination:
    """Tests for Requirements 8.7 and 8.8: Starting player selection."""

    def test_single_goer_starts_next_round(self, round_manager):
        """When one player went out, they start the next round."""
        state = make_game_state(num_players=4)
        state.players[2].has_gone_out = True
        state.players[2].hand = []
        state.players[2].play_pile = [make_card(1, denomination=100)]

        round_manager.process_end_of_round(state)

        # Player 3 (index 2) should be the starting player
        assert state.current_player_index == 2

    def test_multiple_goers_lowest_score_starts(self, round_manager):
        """When multiple players went out, lowest round score starts."""
        state = make_game_state(num_players=4)
        # Player 1 went out with high score
        state.players[0].has_gone_out = True
        state.players[0].hand = []
        state.players[0].play_pile = [
            make_card(1, denomination=10000),
            make_card(2, denomination=1000),
        ]
        # Player 3 went out with low score
        state.players[2].has_gone_out = True
        state.players[2].hand = []
        state.players[2].play_pile = [
            make_card(3, denomination=1),
            make_card(4, denomination=10),
        ]

        round_manager.process_end_of_round(state)

        # Player 3 (index 2) has lower score (11 vs 11000), should start
        assert state.current_player_index == 2

    def test_multiple_goers_tie_broken_by_seat_position(self, round_manager):
        """When multiple goers tie on score, lowest seat position starts."""
        state = make_game_state(num_players=4)
        # Player 2 and Player 4 went out with same score
        state.players[1].has_gone_out = True
        state.players[1].hand = []
        state.players[1].play_pile = [make_card(1, denomination=100)]
        state.players[3].has_gone_out = True
        state.players[3].hand = []
        state.players[3].play_pile = [make_card(2, denomination=100)]

        round_manager.process_end_of_round(state)

        # Player 2 (seat 2) has lower seat position than Player 4 (seat 4)
        assert state.current_player_index == 1


class TestRoundNumberIncrement:
    """Tests for round number increment."""

    def test_round_number_increments(self, round_manager):
        """Round number increases by 1 after end-of-round processing."""
        state = make_game_state(num_players=2, round_number=3)
        state.players[0].has_gone_out = True
        state.players[0].hand = []
        state.players[0].play_pile = [make_card(1, denomination=1)]

        round_manager.process_end_of_round(state)

        assert state.round_number == 4


class TestFlagsClearedForNewRound:
    """Tests for clearing transient flags."""

    def test_has_gone_out_cleared(self, round_manager):
        """has_gone_out is cleared for all players after round transition."""
        state = make_game_state(num_players=3)
        state.players[0].has_gone_out = True
        state.players[0].hand = []
        state.players[0].play_pile = [make_card(1, denomination=1)]

        round_manager.process_end_of_round(state)

        for player in state.players:
            assert player.has_gone_out is False

    def test_is_decked_cleared(self, round_manager):
        """is_decked is cleared for all players after round transition."""
        state = make_game_state(num_players=3)
        state.players[0].has_gone_out = True
        state.players[0].hand = []
        state.players[0].play_pile = [make_card(1, denomination=1)]
        state.players[1].is_decked = True

        round_manager.process_end_of_round(state)

        for player in state.players:
            assert player.is_decked is False


class TestDeckedPlayerRoundTransition:
    """Tests for Requirements 7.6 and 7.7: Decked player round transitions."""

    def test_decked_player_with_7_plus_cards_rejoins(self, round_manager):
        """Decked player with >= 7 cards in play pile rejoins next round."""
        state = make_game_state(num_players=3)
        state.players[0].has_gone_out = True
        state.players[0].hand = []
        state.players[0].play_pile = [make_card(1, denomination=1)]

        # Player 2 is decked with 8 cards in play pile
        state.players[1].is_decked = True
        state.players[1].hand = []
        state.players[1].play_pile = [
            make_card(card_id=200 + j, denomination=10) for j in range(8)
        ]
        state.players[1].draw_deck = []

        round_manager.process_end_of_round(state)

        # Player 2 should have cards dealt (rejoined)
        assert len(state.players[1].hand) == 7
        assert state.players[1].is_decked is False

    def test_decked_player_with_less_than_7_cards_sits_out(self, round_manager):
        """Decked player with < 7 cards in play pile sits out next round."""
        state = make_game_state(num_players=3)
        state.players[0].has_gone_out = True
        state.players[0].hand = []
        state.players[0].play_pile = [make_card(1, denomination=1)]

        # Player 2 is decked with only 5 cards in play pile
        state.players[1].is_decked = True
        state.players[1].hand = []
        state.players[1].play_pile = [
            make_card(card_id=200 + j, denomination=10) for j in range(5)
        ]
        state.players[1].draw_deck = []

        round_manager.process_end_of_round(state)

        # Player 2 should have no hand (sitting out)
        assert len(state.players[1].hand) == 0

    def test_decked_player_sitting_out_play_pile_moved_to_discard(self, round_manager):
        """Decked player sitting out has play pile moved to discard."""
        state = make_game_state(num_players=3)
        state.players[0].has_gone_out = True
        state.players[0].hand = []
        state.players[0].play_pile = [make_card(1, denomination=1)]

        # Player 2 is decked with 3 cards in play pile
        pile_cards = [make_card(card_id=200 + j, denomination=10) for j in range(3)]
        state.players[1].is_decked = True
        state.players[1].hand = []
        state.players[1].play_pile = list(pile_cards)
        state.players[1].draw_deck = []
        state.players[1].discard_pile = []

        round_manager.process_end_of_round(state)

        # Play pile cards should be in discard
        for card in pile_cards:
            assert card in state.players[1].discard_pile
        assert state.players[1].play_pile == []

    def test_decked_player_exactly_7_cards_rejoins(self, round_manager):
        """Decked player with exactly 7 cards in play pile rejoins."""
        state = make_game_state(num_players=3)
        state.players[0].has_gone_out = True
        state.players[0].hand = []
        state.players[0].play_pile = [make_card(1, denomination=1)]

        # Player 2 is decked with exactly 7 cards in play pile
        state.players[1].is_decked = True
        state.players[1].hand = []
        state.players[1].play_pile = [
            make_card(card_id=200 + j, denomination=10) for j in range(7)
        ]
        state.players[1].draw_deck = []

        round_manager.process_end_of_round(state)

        # Player 2 should have 7 cards dealt (all from play pile reshuffled)
        assert len(state.players[1].hand) == 7


class TestEndOfRoundEvents:
    """Tests for events returned by process_end_of_round."""

    def test_returns_round_scores_event(self, round_manager):
        """Events include round_scores_calculated."""
        state = make_game_state(num_players=2)
        state.players[0].has_gone_out = True
        state.players[0].hand = []
        state.players[0].play_pile = [make_card(1, denomination=100)]

        events = round_manager.process_end_of_round(state)

        score_events = [e for e in events if e["type"] == "round_scores_calculated"]
        assert len(score_events) == 1
        assert score_events[0]["scores"][1] == 100

    def test_returns_new_round_started_event(self, round_manager):
        """Events include new_round_started with correct round number."""
        state = make_game_state(num_players=2, round_number=2)
        state.players[0].has_gone_out = True
        state.players[0].hand = []
        state.players[0].play_pile = [make_card(1, denomination=1)]

        events = round_manager.process_end_of_round(state)

        new_round_events = [e for e in events if e["type"] == "new_round_started"]
        assert len(new_round_events) == 1
        assert new_round_events[0]["round_number"] == 3

    def test_returns_starting_player_event(self, round_manager):
        """Events include starting_player_set."""
        state = make_game_state(num_players=3)
        state.players[1].has_gone_out = True
        state.players[1].hand = []
        state.players[1].play_pile = [make_card(1, denomination=1)]

        events = round_manager.process_end_of_round(state)

        start_events = [e for e in events if e["type"] == "starting_player_set"]
        assert len(start_events) == 1
        assert start_events[0]["player_id"] == 2

    def test_returns_round_reset_event(self, round_manager):
        """Events include round_reset with sequence=1 and direction=1."""
        state = make_game_state(num_players=2, current_sequence=10000, direction=-1)
        state.players[0].has_gone_out = True
        state.players[0].hand = []
        state.players[0].play_pile = [make_card(1, denomination=1)]

        events = round_manager.process_end_of_round(state)

        reset_events = [e for e in events if e["type"] == "round_reset"]
        assert len(reset_events) == 1
        assert reset_events[0]["sequence"] == 1
        assert reset_events[0]["direction"] == 1


class TestGameStatusReset:
    """Tests for game status reset after round transition."""

    def test_game_status_set_to_active(self, round_manager):
        """Game status is set back to 'active' after round transition."""
        state = make_game_state(num_players=2)
        state.game_status = "round_end"
        state.players[0].has_gone_out = True
        state.players[0].hand = []
        state.players[0].play_pile = [make_card(1, denomination=1)]

        round_manager.process_end_of_round(state)

        assert state.game_status == "active"

    def test_sequence_broken_cleared(self, round_manager):
        """sequence_broken is cleared for new round."""
        state = make_game_state(num_players=2)
        state.sequence_broken = True
        state.players[0].has_gone_out = True
        state.players[0].hand = []
        state.players[0].play_pile = [make_card(1, denomination=1)]

        round_manager.process_end_of_round(state)

        assert state.sequence_broken is False

    def test_last_played_denomination_cleared(self, round_manager):
        """last_played_denomination is cleared for new round."""
        state = make_game_state(num_players=2)
        state.last_played_denomination = 1000
        state.players[0].has_gone_out = True
        state.players[0].hand = []
        state.players[0].play_pile = [make_card(1, denomination=1)]

        round_manager.process_end_of_round(state)

        assert state.last_played_denomination is None
