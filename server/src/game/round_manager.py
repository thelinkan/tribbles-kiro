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

        # Step 1c: Calculate and apply IDIC scores (Requirement 14.4)
        idic_scores = self._score_service.calculate_idic_scores(game_state)
        for player in game_state.players:
            idic = idic_scores.get(player.player_id, 0)
            if idic > 0:
                player.cumulative_score += idic
                events.append({
                    "type": "idic_scored",
                    "player_id": player.player_id,
                    "idic_points": idic,
                })

        # Step 1d: Return borrowed cards to original owners (Requirement 14.2)
        self._return_borrowed_cards(game_state, events)

        # Step 2: Move non-goers' hands to discard piles
        self._move_non_goers_hands_to_discard(game_state, events)

        # Step 3: Handle decked player transitions
        sitting_out_players = self._handle_decked_player_transitions(
            game_state, events
        )

        # Step 3b: Track Time Warp reductions for next round (Requirement 13.4)
        # For players who did NOT go out, count unique Time Warp denominations
        # in their play pile. This must happen before play piles are cleared.
        self._track_time_warp_reductions(game_state, events)

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

        If a player has the Safety card in their play pile, their hand is
        shuffled into their draw deck instead of being placed in the discard pile.

        Args:
            game_state: The current game state (modified in place).
            events: Events list to append to.

        Requirements: 8.3, 12.11
        """
        for player in game_state.players:
            if not player.has_gone_out and len(player.hand) > 0:
                cards_moved = len(player.hand)

                # Check for Safety power in play pile (Requirement 12.11)
                has_safety = any(
                    c.power_text.lower().strip() == "safety"
                    for c in player.play_pile
                )

                if has_safety:
                    # Shuffle hand into draw deck instead of discard
                    player.draw_deck.extend(player.hand)
                    player.hand.clear()
                    random.shuffle(player.draw_deck)
                    events.append({
                        "type": "hand_shuffled_into_draw_deck",
                        "player_id": player.player_id,
                        "cards_moved": cards_moved,
                        "reason": "safety_power",
                    })
                else:
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

    def _return_borrowed_cards(
        self, game_state: GameState, events: List[dict]
    ) -> None:
        """Return borrowed cards (from Assimilate) to their original owners.

        For each player, any cards in their borrowed_cards list are removed from
        their play pile and returned to the original owner's discard pile.

        Args:
            game_state: The current game state (modified in place).
            events: Events list to append to.

        Requirements: 14.2
        """
        for player in game_state.players:
            if not player.borrowed_cards:
                continue

            for borrowed_card, original_owner_id in player.borrowed_cards:
                # Remove from play pile if still there
                card_found = False
                for i, c in enumerate(player.play_pile):
                    if c.card_id == borrowed_card.card_id:
                        player.play_pile.pop(i)
                        card_found = True
                        break

                # Return to original owner's discard pile
                if card_found:
                    for owner in game_state.players:
                        if owner.player_id == original_owner_id:
                            owner.discard_pile.append(borrowed_card)
                            events.append({
                                "type": "borrowed_card_returned",
                                "borrower_player_id": player.player_id,
                                "owner_player_id": original_owner_id,
                                "card_id": borrowed_card.card_id,
                            })
                            break

            # Clear borrowed cards list
            player.borrowed_cards.clear()

    def _track_time_warp_reductions(
        self, game_state: GameState, events: List[dict]
    ) -> None:
        """Track Time Warp reductions for the next round.

        For each player who did NOT go out, count unique Time Warp denominations
        in their play pile. Store these in the player's time_warp_reductions set.
        Same denomination does NOT stack (only unique denominations count).

        Args:
            game_state: The current game state (modified in place).
            events: Events list to append to.

        Requirements: 13.4
        """
        for player in game_state.players:
            # Clear previous reductions
            player.time_warp_reductions = set()

            # Only applies to players who did NOT go out
            if player.has_gone_out:
                continue

            # Find unique Time Warp denominations in play pile
            for card in player.play_pile:
                if card.power_text.lower().strip() == "time warp":
                    player.time_warp_reductions.add(card.denomination)

            if player.time_warp_reductions:
                events.append({
                    "type": "time_warp_reduction",
                    "player_id": player.player_id,
                    "unique_denominations": sorted(player.time_warp_reductions),
                    "reduction": len(player.time_warp_reductions),
                })

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
        """Deal cards from each active player's draw deck to their hand.

        Players who are sitting out do not receive cards.
        Time Warp reduces the number of cards dealt for players who did not go out
        and have Time Warp cards in their play pile (checked before play piles are
        cleared). The reduction is 1 per unique Time Warp denomination (min 1 card dealt).

        Args:
            game_state: The current game state (modified in place).
            sitting_out_players: List of player_ids who are sitting out.
            events: Events list to append to.

        Requirements: 8.5, 13.4
        """
        for player in game_state.players:
            if player.player_id in sitting_out_players:
                continue

            # Calculate Time Warp reduction
            time_warp_reduction = len(player.time_warp_reductions)
            cards_to_deal_count = max(1, self.CARDS_TO_DEAL - time_warp_reduction)

            cards_to_deal = min(cards_to_deal_count, len(player.draw_deck))
            player.hand = player.draw_deck[:cards_to_deal]
            player.draw_deck = player.draw_deck[cards_to_deal:]

            event = {
                "type": "cards_dealt",
                "player_id": player.player_id,
                "cards_dealt": cards_to_deal,
            }
            if time_warp_reduction > 0:
                event["time_warp_reduction"] = time_warp_reduction
            events.append(event)

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
