"""Disconnection and reconnection management for player sessions.

This module implements the DisconnectionManager class which handles:
- Detecting and tracking player disconnections
- Grace period management (skip turns without decking)
- AI_Substitute activation after timeout
- Player reconnection and state synchronisation

Requirements: 21.1, 21.2, 21.3, 21.4, 21.5, 21.6, 21.7, 21.8
"""

import time
from typing import Dict, List, Optional, Tuple

from models import DisconnectionState, GameState


class DisconnectionManager:
    """Manages player disconnection, reconnection, and AI_Substitute lifecycle.

    Tracks disconnection state per player per game session. Provides methods
    to mark players as disconnected/reconnected, check timeouts, determine
    whether to skip turns, and build reconnection state payloads.

    The manager stores DisconnectionState objects keyed by (game_id, player_id).

    Requirements: 21.1, 21.2, 21.3, 21.4, 21.5, 21.6, 21.7, 21.8
    """

    def __init__(self) -> None:
        """Initialise the disconnection manager with an empty state store."""
        self._states: Dict[Tuple[str, int], DisconnectionState] = {}

    def mark_disconnected(
        self, game_state: GameState, player_id: int, current_time: Optional[float] = None
    ) -> DisconnectionState:
        """Mark a player as disconnected and record the timestamp.

        Sets is_disconnected=True and records the server timestamp when
        disconnection was detected. Begins the reconnection grace period.

        Args:
            game_state: The current game state.
            player_id: The ID of the disconnected player.
            current_time: Optional override for the current time (for testing).
                Defaults to time.time() if not provided.

        Returns:
            The updated DisconnectionState for the player.

        Requirements: 21.1
        """
        if current_time is None:
            current_time = time.time()

        key = (game_state.game_id, player_id)
        state = DisconnectionState(
            player_id=player_id,
            is_disconnected=True,
            disconnected_at=current_time,
            ai_substitute_active=False,
        )
        self._states[key] = state
        return state

    def mark_reconnected(
        self, game_state: GameState, player_id: int
    ) -> DisconnectionState:
        """Mark a player as reconnected, removing AI_Substitute if active.

        Clears the disconnection state: sets is_disconnected=False,
        clears disconnected_at, and deactivates AI_Substitute.

        Args:
            game_state: The current game state.
            player_id: The ID of the reconnecting player.

        Returns:
            The updated DisconnectionState for the player.

        Requirements: 21.6
        """
        key = (game_state.game_id, player_id)
        state = self._states.get(key)
        if state is None:
            state = DisconnectionState(player_id=player_id)
            self._states[key] = state

        state.is_disconnected = False
        state.disconnected_at = None
        state.ai_substitute_active = False
        return state

    def check_timeout(
        self, game_state: GameState, player_id: int, current_time: Optional[float] = None
    ) -> bool:
        """Check if the grace period has expired and activate AI_Substitute if so.

        If the player is disconnected and the elapsed time since disconnection
        exceeds the game's reconnection_timeout, activates AI_Substitute.

        Args:
            game_state: The current game state (provides reconnection_timeout).
            player_id: The ID of the player to check.
            current_time: Optional override for the current time (for testing).
                Defaults to time.time() if not provided.

        Returns:
            True if AI_Substitute was activated (timeout elapsed), False otherwise.

        Requirements: 21.4
        """
        if current_time is None:
            current_time = time.time()

        key = (game_state.game_id, player_id)
        state = self._states.get(key)

        if state is None or not state.is_disconnected:
            return False

        if state.ai_substitute_active:
            # Already activated
            return True

        if state.disconnected_at is None:
            return False

        elapsed = current_time - state.disconnected_at
        if elapsed >= game_state.reconnection_timeout:
            state.ai_substitute_active = True
            return True

        return False

    def is_in_grace_period(
        self, game_state: GameState, player_id: int, current_time: Optional[float] = None
    ) -> bool:
        """Check if a player is disconnected and still within the grace period.

        A player is in the grace period if they are disconnected, the timeout
        has not elapsed, and AI_Substitute is not yet active.

        Args:
            game_state: The current game state (provides reconnection_timeout).
            player_id: The ID of the player to check.
            current_time: Optional override for the current time (for testing).
                Defaults to time.time() if not provided.

        Returns:
            True if the player is in the grace period, False otherwise.

        Requirements: 21.3
        """
        if current_time is None:
            current_time = time.time()

        key = (game_state.game_id, player_id)
        state = self._states.get(key)

        if state is None or not state.is_disconnected:
            return False

        if state.ai_substitute_active:
            return False

        if state.disconnected_at is None:
            return False

        elapsed = current_time - state.disconnected_at
        return elapsed < game_state.reconnection_timeout

    def should_skip_turn(
        self, game_state: GameState, player_id: int, current_time: Optional[float] = None
    ) -> bool:
        """Determine if a disconnected player's turn should be skipped.

        Returns True if the player is disconnected and still within the grace
        period (AI_Substitute not yet active). During the grace period, the
        player's turn is skipped without marking them as decked.

        Args:
            game_state: The current game state.
            player_id: The ID of the player whose turn it is.
            current_time: Optional override for the current time (for testing).
                Defaults to time.time() if not provided.

        Returns:
            True if the turn should be skipped (grace period), False otherwise.

        Requirements: 21.3
        """
        return self.is_in_grace_period(game_state, player_id, current_time)

    def is_ai_substitute_active(self, game_state: GameState, player_id: int) -> bool:
        """Check if AI_Substitute is currently controlling a player's seat.

        Args:
            game_state: The current game state.
            player_id: The ID of the player to check.

        Returns:
            True if AI_Substitute is active for this player, False otherwise.

        Requirements: 21.5
        """
        key = (game_state.game_id, player_id)
        state = self._states.get(key)
        if state is None:
            return False
        return state.ai_substitute_active

    def is_disconnected(self, game_state: GameState, player_id: int) -> bool:
        """Check if a player is currently marked as disconnected.

        Args:
            game_state: The current game state.
            player_id: The ID of the player to check.

        Returns:
            True if the player is disconnected, False otherwise.
        """
        key = (game_state.game_id, player_id)
        state = self._states.get(key)
        if state is None:
            return False
        return state.is_disconnected

    def get_disconnection_state(
        self, game_state: GameState, player_id: int
    ) -> Optional[DisconnectionState]:
        """Get the disconnection state for a player in a game.

        Args:
            game_state: The current game state.
            player_id: The ID of the player.

        Returns:
            The DisconnectionState if one exists, None otherwise.
        """
        key = (game_state.game_id, player_id)
        return self._states.get(key)

    def get_reconnect_state(self, game_state: GameState, player_id: int) -> dict:
        """Build the reconnect_state_sync payload for a reconnecting player.

        Constructs the full game state payload that should be sent to a
        reconnecting player, including their hand, visible piles, scores,
        sequence, direction, and active player.

        Args:
            game_state: The current game state.
            player_id: The ID of the reconnecting player.

        Returns:
            A dict matching the reconnect_state_sync message payload format:
            {
                "hand": [...],
                "play_pile": [...],
                "draw_deck_count": int,
                "discard_pile": [...],
                "scores": {player_id: score, ...},
                "current_sequence": int,
                "direction": int,
                "active_player_id": int,
                "round_number": int,
                "game_status": str,
            }

        Requirements: 21.7
        """
        # Find the player's state
        player_state = None
        for p in game_state.players:
            if p.player_id == player_id:
                player_state = p
                break

        if player_state is None:
            return {}

        # Build hand as list of card dicts
        hand = [
            {
                "card_id": c.card_id,
                "card_name": c.card_name,
                "denomination": c.denomination,
                "power_text": c.power_text,
                "expansion_id": c.expansion_id,
            }
            for c in player_state.hand
        ]

        # Build play pile as list of card dicts
        play_pile = [
            {
                "card_id": c.card_id,
                "card_name": c.card_name,
                "denomination": c.denomination,
                "power_text": c.power_text,
                "expansion_id": c.expansion_id,
            }
            for c in player_state.play_pile
        ]

        # Build discard pile as list of card dicts
        discard_pile = [
            {
                "card_id": c.card_id,
                "card_name": c.card_name,
                "denomination": c.denomination,
                "power_text": c.power_text,
                "expansion_id": c.expansion_id,
            }
            for c in player_state.discard_pile
        ]

        # Build scores dict for all players
        scores = {
            p.player_id: p.cumulative_score for p in game_state.players
        }

        # Get active player ID
        active_player_id = game_state.players[game_state.current_player_index].player_id

        return {
            "hand": hand,
            "play_pile": play_pile,
            "draw_deck_count": len(player_state.draw_deck),
            "discard_pile": discard_pile,
            "scores": scores,
            "current_sequence": game_state.current_sequence,
            "direction": game_state.direction,
            "active_player_id": active_player_id,
            "round_number": game_state.round_number,
            "game_status": game_state.game_status,
        }

    def build_disconnect_notify(
        self, game_state: GameState, player_id: int
    ) -> dict:
        """Build the disconnect_notify message payload.

        Args:
            game_state: The current game state.
            player_id: The ID of the disconnected player.

        Returns:
            A dict matching the disconnect_notify message format.
        """
        username = ""
        for p in game_state.players:
            if p.player_id == player_id:
                username = p.username
                break

        return {
            "type": "disconnect_notify",
            "payload": {
                "player_id": player_id,
                "username": username,
                "grace_period_seconds": game_state.reconnection_timeout,
            },
        }

    def build_reconnect_notify(
        self, game_state: GameState, player_id: int
    ) -> dict:
        """Build the reconnect_notify message payload.

        Args:
            game_state: The current game state.
            player_id: The ID of the reconnecting player.

        Returns:
            A dict matching the reconnect_notify message format.
        """
        username = ""
        for p in game_state.players:
            if p.player_id == player_id:
                username = p.username
                break

        return {
            "type": "reconnect_notify",
            "payload": {
                "player_id": player_id,
                "username": username,
            },
        }

    def handle_game_ended_while_disconnected(
        self, game_state: GameState, player_id: int
    ) -> Optional[dict]:
        """Handle the case where a game ended while a player was disconnected.

        If the game is completed and the player was disconnected, returns
        the final game results so the player can view them on reconnect.

        Args:
            game_state: The current game state.
            player_id: The ID of the reconnecting player.

        Returns:
            A dict with final game results if the game ended while disconnected,
            None if the game is still active.

        Requirements: 21.8
        """
        if game_state.game_status != "completed":
            return None

        # Build final scores
        scores = {
            p.player_id: p.cumulative_score for p in game_state.players
        }

        # Determine winner (highest score)
        winner_id = max(scores, key=lambda pid: scores[pid])
        winner_username = ""
        for p in game_state.players:
            if p.player_id == winner_id:
                winner_username = p.username
                break

        # Find the reconnecting player's score
        player_score = scores.get(player_id, 0)

        return {
            "type": "game_end",
            "payload": {
                "final_scores": scores,
                "winner": winner_username,
                "player_score": player_score,
                "game_status": "completed",
            },
        }
