"""Score calculation service for the Tribbles multiplayer game.

This module implements the Score_Service class responsible for calculating
round scores and applying immediate score changes during gameplay.
"""

from typing import Dict

from models import CardInstance, GameState, PlayerState


class ScoreService:
    """Handles score calculation and application for the Tribbles game.

    Responsible for:
    - Calculating round scores based on play pile denominations for players who went out
    - Applying immediate score changes (e.g., from Poison, Score powers)

    Requirements: 8.2
    """

    def calculate_round_scores(self, game_state: GameState) -> Dict[int, int]:
        """Calculate round scores for all players who went out.

        For each player with has_gone_out=True, sums the denominations of all
        cards in their play pile. Players who did not go out receive a score of 0.

        The Quadruple card (denomination 10000) is worth 40000 instead of 10000
        for the round winner.

        Args:
            game_state: The current game state at end of round.

        Returns:
            A dictionary mapping player_id to their round score.
            Only players who went out will have non-zero scores.

        Requirements: 8.2, 12.9
        """
        scores: Dict[int, int] = {}
        for player in game_state.players:
            if player.has_gone_out:
                round_score = 0
                for card in player.play_pile:
                    if card.power_text.lower().strip() == "quadruple":
                        # Quadruple card worth 40000 instead of 10000
                        round_score += 40000
                    else:
                        round_score += card.denomination
                scores[player.player_id] = round_score
            else:
                scores[player.player_id] = 0
        return scores

    BONUS_DENOMINATIONS = {1, 10, 100, 1000}
    BONUS_POINTS = 100000

    def calculate_bonus_scores(self, game_state: GameState) -> Dict[int, int]:
        """Calculate bonus scores for players with all four Bonus denomination cards.

        For each non-decked player, checks if their play pile contains Bonus cards
        at denominations 1, 10, 100, and 1000. If all four are present, awards
        100000 bonus points.

        Args:
            game_state: The current game state at end of round.

        Returns:
            A dictionary mapping player_id to their bonus score (100000 or 0).

        Requirements: 10.1
        """
        bonus_scores: Dict[int, int] = {}
        for player in game_state.players:
            if player.is_decked:
                bonus_scores[player.player_id] = 0
                continue

            # Find Bonus cards in the play pile and collect their denominations
            bonus_denominations_found: set = set()
            for card in player.play_pile:
                if card.power_text.lower() == "bonus" and card.denomination in self.BONUS_DENOMINATIONS:
                    bonus_denominations_found.add(card.denomination)

            if bonus_denominations_found >= self.BONUS_DENOMINATIONS:
                bonus_scores[player.player_id] = self.BONUS_POINTS
            else:
                bonus_scores[player.player_id] = 0

        return bonus_scores

    def apply_immediate_score(
        self, game_state: GameState, player_id: int, points: int
    ) -> None:
        """Apply immediate score points to a player's cumulative score.

        Used by powers like Poison and Score that grant points during gameplay
        rather than at end of round.

        Checks for Tally power: if the card being scored has the Tally power,
        the scorer receives half and the Tally card's owner receives the other half.

        Args:
            game_state: The current game state.
            player_id: The player to receive the points.
            points: The number of points to add (can be negative for penalties).

        Raises:
            ValueError: If the player_id is not found in the game state.
        """
        for player in game_state.players:
            if player.player_id == player_id:
                player.cumulative_score += points
                return
        raise ValueError(f"Player {player_id} not found in game state.")

    def apply_tally_score(
        self, game_state: GameState, scorer_player_id: int, card: "CardInstance", points: int
    ) -> Dict[int, int]:
        """Apply scoring with Tally power check.

        If the card being scored has the Tally power, the scorer receives half
        the denomination and the Tally card's owner receives the other half.

        Args:
            game_state: The current game state.
            scorer_player_id: The player who is scoring.
            card: The card being scored from.
            points: The base points to award.

        Returns:
            Dict mapping player_id to points actually awarded.

        Requirements: 12.12
        """
        # Check if the card has Tally power
        if card.power_text.lower().strip() == "tally":
            # Find the Tally card's owner (the player whose play pile contains it)
            tally_owner_id = None
            for player in game_state.players:
                for pile_card in player.play_pile:
                    if pile_card.card_id == card.card_id:
                        tally_owner_id = player.player_id
                        break
                if tally_owner_id is not None:
                    break

            if tally_owner_id is not None and tally_owner_id != scorer_player_id:
                # Split: half to scorer, half to Tally owner
                half = points // 2
                scorer_points = half
                owner_points = half

                self.apply_immediate_score(game_state, scorer_player_id, scorer_points)
                self.apply_immediate_score(game_state, tally_owner_id, owner_points)

                return {scorer_player_id: scorer_points, tally_owner_id: owner_points}

        # Normal scoring (no Tally or scorer owns the Tally card)
        self.apply_immediate_score(game_state, scorer_player_id, points)
        return {scorer_player_id: points}
