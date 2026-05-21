"""Spectator state broadcasting and management.

This module implements the SpectatorManager class which handles:
- Building spectator-visible game state (all public info, no hand contents)
- Building spectator_state_update messages
- Building spectator_count_update messages
- Spectator leave logic
- Checking if a player is a spectator

Requirements: 22.1, 22.2, 22.3, 22.5, 22.6, 22.7
"""

from typing import Dict, List, Optional

from models import GameState


class SpectatorManager:
    """Manages spectator state broadcasting and spectator lifecycle.

    Provides methods to build spectator-visible state payloads, generate
    WebSocket messages for spectators, handle spectator leaving, and
    check whether a player is a spectator.

    Requirements: 22.1, 22.2, 22.3, 22.5, 22.6, 22.7
    """

    def get_spectator_visible_state(self, game_state: GameState) -> dict:
        """Build the spectator-visible state payload.

        Returns all public game information without any player's hand contents.
        Includes play piles, discard piles, draw deck card counts, scores,
        current sequence, direction, active player, round number, and game status.

        Args:
            game_state: The current game state.

        Returns:
            A dict containing all public state visible to spectators:
            {
                "play_piles": {player_id: [card_dicts], ...},
                "discard_piles": {player_id: [card_dicts], ...},
                "draw_deck_counts": {player_id: count, ...},
                "scores": {player_id: score, ...},
                "current_sequence": int,
                "direction": int,
                "active_player_id": int,
                "round_number": int,
                "game_status": str,
            }

        Requirements: 22.2, 22.3
        """
        play_piles: Dict[int, List[dict]] = {}
        discard_piles: Dict[int, List[dict]] = {}
        draw_deck_counts: Dict[int, int] = {}
        scores: Dict[int, int] = {}

        for player in game_state.players:
            pid = player.player_id

            play_piles[pid] = [
                {
                    "card_id": c.card_id,
                    "card_name": c.card_name,
                    "denomination": c.denomination,
                    "power_text": c.power_text,
                    "expansion_id": c.expansion_id,
                }
                for c in player.play_pile
            ]

            discard_piles[pid] = [
                {
                    "card_id": c.card_id,
                    "card_name": c.card_name,
                    "denomination": c.denomination,
                    "power_text": c.power_text,
                    "expansion_id": c.expansion_id,
                }
                for c in player.discard_pile
            ]

            draw_deck_counts[pid] = len(player.draw_deck)
            scores[pid] = player.cumulative_score

        active_player_id = game_state.players[game_state.current_player_index].player_id

        return {
            "play_piles": play_piles,
            "discard_piles": discard_piles,
            "draw_deck_counts": draw_deck_counts,
            "scores": scores,
            "current_sequence": game_state.current_sequence,
            "direction": game_state.direction,
            "active_player_id": active_player_id,
            "round_number": game_state.round_number,
            "game_status": game_state.game_status,
        }

    def build_spectator_state_update(self, game_state: GameState) -> dict:
        """Build the spectator_state_update WebSocket message.

        Wraps the spectator-visible state in the standard message format.

        Args:
            game_state: The current game state.

        Returns:
            A dict matching the spectator_state_update message format:
            {"type": "spectator_state_update", "payload": {...}}

        Requirements: 22.2
        """
        return {
            "type": "spectator_state_update",
            "payload": self.get_spectator_visible_state(game_state),
        }

    def build_spectator_count_update(self, game_state: GameState) -> dict:
        """Build the spectator_count_update WebSocket message.

        Sent to all players and spectators when the spectator count changes.

        Args:
            game_state: The current game state.

        Returns:
            A dict matching the spectator_count_update message format:
            {"type": "spectator_count_update", "payload": {"session_id": str, "spectator_count": int}}

        Requirements: 22.6
        """
        return {
            "type": "spectator_count_update",
            "payload": {
                "session_id": game_state.game_id,
                "spectator_count": len(game_state.spectators),
            },
        }

    def leave_spectate(self, game_state: GameState, player_id: int) -> bool:
        """Remove a spectator from the game session.

        Removes the player from the spectators list without affecting
        the game state or active players.

        Args:
            game_state: The current game state (modified in place).
            player_id: The ID of the spectator to remove.

        Returns:
            True if the spectator was removed, False if they were not spectating.

        Requirements: 22.5
        """
        if player_id in game_state.spectators:
            game_state.spectators.remove(player_id)
            return True
        return False

    def is_spectator(self, game_state: GameState, player_id: int) -> bool:
        """Check if a player is a spectator in the given game.

        Args:
            game_state: The current game state.
            player_id: The ID of the player to check.

        Returns:
            True if the player is in the spectators list, False otherwise.

        Requirements: 22.7
        """
        return player_id in game_state.spectators
