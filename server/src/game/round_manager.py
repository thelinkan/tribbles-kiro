"""Round management for the Tribbles multiplayer game.

This module implements the RoundManager class responsible for handling
end-of-round processing and new round setup including scoring, card
redistribution, and starting player determination.
"""

import random
from typing import Dict, List

from models import GameState, PlayerState
from scoring.service import ScoreService


class RoundManager:
    """Manages round transitions in the Tribbles card game.

    Handles end-of-round processing including:
    - Score calculation and application for players who went out
    - Moving non-goers' hands to discard piles
    - Handling decked player round transitions
    - Shuffling play piles into draw decks
    - Dealing new hands
    - Determining starting player for the new round
    - Resetting sequence and direction
    - Ending the game after MAX_ROUNDS rounds

    Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 7.6, 7.7, 16.1, 16.2
    """

    CARDS_TO_DEAL = 7
    MAX_ROUNDS = 5

    def __init__(self, score_service: ScoreService = None):
        """Initialise the RoundManager.

        Args:
            score_service: Optional ScoreService instance. If not provided,
                a new one will be created.
        """
        if score_service is None:
            score_service = ScoreService()
        self._score_service = score_service

    def process_end_of_round(self, game_state: GameState) -> List[dict]:
        """Orchestrate end-of-round processing.

        Performs the following steps in order:
        1. Calculate and apply round scores for players who went out
        2. Move non-goers' hands to their discard piles (respecting Safety power)
        3. Handle decked player transitions (pile >= 7 -> reshuffle; < 7 -> sit out)
        4. Shuffle all players' play piles into their draw decks
        5. Deal 7 cards to each active player
        6. Determine starting player for the new round
        7. Reset sequence to 1, direction to clockwise (1)
        8. Increment round_number
        9. Check if game should end (after MAX_ROUNDS rounds)
        10. Clear has_gone_out and is_decked flags for the new round
        11. Return events list

        Args:
            game_state: The current game state (modified in place).

        Returns:
            A list of game event dicts describing what happened during the transition.

        Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 7.6, 7.7, 16.1, 16.2
        """
        events: List[dict] = []

        # Step 1: Calculate and apply round scores
        round_scores = self._score_service.calculate_round_scores(game_state)
        for player in game_state.players:
            score = round_scores.get(player.player_id, 0)
            if score > 0:
                player.cumulative_score += score

        events.append({
            "type": "round_scores_calculated",
            "scores": round_scores,
        })

        # Step 1b: Calculate and apply bonus scores (Requirement 10.1)
        bonus_scores = self._score_service.calculate_bonus_scores(game_state)
        for player in game_state.players:
            bonus = bonus_scores.get(player.player_id, 0)
            if bonus > 0:
                player.cumulative_score += bonus
                events.append({
                    "type": "bonus_scored",
                    "player_id": player.player_id,
                    "bonus_points": bonus,
                })

        # Step 2: Move non-goers' hands to discard piles
        self._move_non_goers_hands_to_discard(game_state, events)

        # Step 3: Handle decked player transitions
        sitting_out_players = self._handle_decked_player_transitions(
            game_state, events
        )

        # Step 4: Shuffle all players' play piles into their draw decks
        self._shuffle_play_piles_into_draw_decks(game_state, events)

        # Step 8: Increment round number
        game_state.round_number += 1

        # Step 9: Check if game should end after MAX_ROUNDS rounds
        if game_state.round_number > self.MAX_ROUNDS:
            return self._end_game(game_state, events)

        # Step 5: Deal 7 cards to each active player
        self._deal_new_hands(game_state, sitting_out_players, events)

        # Step 6: Determine starting player
        starting_player_index = self._determine_starting_player(
            game_state, round_scores
        )
        game_state.current_player_index = starting_player_index

        events.append({
            "type": "starting_player_set",
            "player_id": game_state.players[starting_player_index].player_id,
        })

        # Step 7: Reset sequence and direction
        game_state.current_sequence = 1
        game_state.direction = 1

        events.append({
            "type": "round_reset",
            "sequence": 1,
            "direction": 1,
        })

        # Step 10: Clear has_gone_out and is_decked flags
        for player in game_state.players:
            player.has_gone_out = False
            player.is_decked = False

        # Reset other transient state
        game_state.last_played_denomination = None
        game_state.sequence_broken = False
        game_state.pending_draw = None
        game_state.game_status = "active"

        events.append({
            "type": "new_round_started",
            "round_number": game_state.round_number,
        })

        return events

    def _move_non_goers_hands_to_discard(
        self, game_state: GameState, events: List[dict]
    ) -> None:
        """Move hands of players who did not go out to their discard piles.

        Args:
            game_state: The current game state (modified in place).
            events: Events list to append to.

        Requirements: 8.3
        """
        for player in game_state.players:
            if not player.has_gone_out and len(player.hand) > 0:
                cards_moved = len(player.hand)
                player.discard_pile.extend(player.hand)
                player.hand.clear()
                events.append({
                    "type": "hand_moved_to_discard",
                    "player_id": player.player_id,
                    "cards_moved": cards_moved,
                })

    def _handle_decked_player_transitions(
        self, game_state: GameState, events: List[dict]
    ) -> List[int]:
        """Handle decked player round transitions.

        For decked players:
        - If play pile >= 7 cards: reshuffle as draw deck for next round
        - If play pile < 7 cards: sit out next round (mark as sitting out)

        Note: The actual reshuffling into draw deck happens in step 4 for all
        players. Here we only handle the "sit out" case by marking players
        and clearing their play pile for those who can't rejoin.

        Args:
            game_state: The current game state (modified in place).
            events: Events list to append to.

        Returns:
            List of player_ids who are sitting out the next round.

        Requirements: 7.6, 7.7
        """
        sitting_out: List[int] = []

        for player in game_state.players:
            if player.is_decked:
                pile_size = len(player.play_pile)
                if pile_size >= self.CARDS_TO_DEAL:
                    # Player can rejoin: play pile will be reshuffled as draw deck
                    # (handled in step 4 along with all other players)
                    events.append({
                        "type": "decked_player_rejoins",
                        "player_id": player.player_id,
                        "play_pile_size": pile_size,
                    })
                else:
                    # Player sits out: play pile too small
                    # Move any remaining cards to discard
                    player.discard_pile.extend(player.play_pile)
                    player.play_pile.clear()
                    sitting_out.append(player.player_id)
                    events.append({
                        "type": "decked_player_sits_out",
                        "player_id": player.player_id,
                        "play_pile_size": pile_size,
                    })

        return sitting_out

    def _shuffle_play_piles_into_draw_decks(
        self, game_state: GameState, events: List[dict]
    ) -> None:
        """Shuffle each player's play pile into their draw deck.

        All cards from the play pile are added to the draw deck and then
        the draw deck is shuffled.

        Args:
            game_state: The current game state (modified in place).
            events: Events list to append to.

        Requirements: 8.4
        """
        for player in game_state.players:
            if len(player.play_pile) > 0:
                player.draw_deck.extend(player.play_pile)
                player.play_pile.clear()
                random.shuffle(player.draw_deck)

    def _deal_new_hands(
        self,
        game_state: GameState,
        sitting_out_players: List[int],
        events: List[dict],
    ) -> None:
        """Deal 7 cards from each active player's draw deck to their hand.

        Players who are sitting out do not receive cards.

        Args:
            game_state: The current game state (modified in place).
            sitting_out_players: List of player_ids who are sitting out.
            events: Events list to append to.

        Requirements: 8.5
        """
        for player in game_state.players:
            if player.player_id in sitting_out_players:
                continue

            cards_to_deal = min(self.CARDS_TO_DEAL, len(player.draw_deck))
            player.hand = player.draw_deck[:cards_to_deal]
            player.draw_deck = player.draw_deck[cards_to_deal:]

            events.append({
                "type": "cards_dealt",
                "player_id": player.player_id,
                "cards_dealt": cards_to_deal,
            })

    def _determine_starting_player(
        self, game_state: GameState, round_scores: Dict[int, int]
    ) -> int:
        """Determine which player starts the new round.

        Rules:
        - If exactly one player went out, that player starts.
        - If multiple players went out, the one with the lowest round score starts.
        - Ties are broken by seat position (lowest seat position wins).

        Args:
            game_state: The current game state.
            round_scores: Dictionary of player_id to round score.

        Returns:
            The index into game_state.players for the starting player.

        Requirements: 8.7, 8.8
        """
        # Find players who went out
        goers = [p for p in game_state.players if p.has_gone_out]

        if len(goers) == 1:
            # Single go-out: that player starts
            starting_player = goers[0]
        elif len(goers) > 1:
            # Multiple go-out: lowest round score starts
            # Tie-break by seat position (lowest)
            goers.sort(
                key=lambda p: (round_scores.get(p.player_id, 0), p.seat_position)
            )
            starting_player = goers[0]
        else:
            # No one went out (shouldn't happen in normal play, but handle gracefully)
            # Keep current player
            return game_state.current_player_index

        # Find the index of the starting player
        for i, player in enumerate(game_state.players):
            if player.player_id == starting_player.player_id:
                return i

        # Fallback (shouldn't reach here)
        return game_state.current_player_index

    def _end_game(self, game_state: GameState, events: List[dict]) -> List[dict]:
        """End the game after MAX_ROUNDS rounds have been completed.

        Sets game_status to "completed", determines the winner, and returns
        a game_end event with final scores and winner info.

        Args:
            game_state: The current game state (modified in place).
            events: Events list to append to.

        Returns:
            The complete events list including the game_end event.

        Requirements: 16.1, 16.2
        """
        game_state.game_status = "completed"

        winner = self._determine_winner(game_state)

        final_scores = {
            player.player_id: player.cumulative_score
            for player in game_state.players
        }

        events.append({
            "type": "game_end",
            "final_scores": final_scores,
            "winner_player_id": winner.player_id,
            "winner_username": winner.username,
        })

        return events

    def _determine_winner(self, game_state: GameState) -> PlayerState:
        """Determine the winner of the game.

        The winner is the player with the highest cumulative score.
        Ties are broken by seat position (lowest seat position wins).

        Args:
            game_state: The current game state.

        Returns:
            The PlayerState of the winning player.

        Requirements: 16.1
        """
        players_sorted = sorted(
            game_state.players,
            key=lambda p: (-p.cumulative_score, p.seat_position),
        )
        return players_sorted[0]
