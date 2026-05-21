"""Score calculation service for the Tribbles multiplayer game.

This module implements the Score_Service class responsible for calculating
round scores and applying immediate score changes during gameplay.
"""

from typing import Dict

from models import GameState, PlayerState


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

        Args:
            game_state: The current game state at end of round.

        Returns:
            A dictionary mapping player_id to their round score.
            Only players who went out will have non-zero scores.

        Requirements: 8.2
        """
        scores: Dict[int, int] = {}
        for player in game_state.players:
            if player.has_gone_out:
                round_score = sum(card.denomination for card in player.play_pile)
                scores[player.player_id] = round_score
            else:
                scores[player.player_id] = 0
        return scores

    def apply_immediate_score(
        self, game_state: GameState, player_id: int, points: int
    ) -> None:
        """Apply immediate score points to a player's cumulative score.

        Used by powers like Poison and Score that grant points during gameplay
        rather than at end of round.

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
