"""Power resolution framework for the Tribbles card game.

This module implements the PowerResolver class which dispatches and executes
card power effects. It handles the two-phase activation flow:
  Phase 1: Prompt player to activate or decline the power.
  Phase 2: Execute the power effect (possibly with additional target selection).

Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8
"""

from typing import List, Optional, Tuple, Union

from models import CardInstance, GameState, PendingPower, PlayerState
from scoring.service import ScoreService


# Powers that can be activated (have an effect beyond just being played)
ACTIVATABLE_POWERS = {"discard", "go", "skip", "poison", "rescue", "reverse"}

# Powers that require a target or choice after activation
POWERS_NEEDING_TARGET = {"discard", "poison", "rescue"}

# Powers that execute immediately on activation (no target needed)
IMMEDIATE_POWERS = {"go", "skip", "reverse"}


class PowerResolver:
    """Dispatches and executes card power effects.

    The PowerResolver handles the multi-phase power activation flow:
    1. When a card with an activatable power is played, it creates a pending
       power prompt (activate or decline).
    2. When the player responds, it either executes the power immediately
       (for Go, Skip, Reverse) or prompts for a target/choice (for Discard,
       Poison, Rescue).
    3. When the target/choice is provided, it executes the power effect.

    The Clone power has no activation effect — it's handled by _is_valid_play
    in the GameEngine. When a Clone card is played, it goes to the play pile
    normally without triggering any power prompt.

    Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8
    """

    def __init__(self, score_service: Optional[ScoreService] = None):
        """Initialise the PowerResolver.

        Args:
            score_service: Optional ScoreService for applying immediate scores.
                If not provided, a new one will be created.
        """
        if score_service is None:
            score_service = ScoreService()
        self._score_service = score_service

    def get_activatable_power(self, card: CardInstance) -> Optional[str]:
        """Extract the activatable power name from a card, if any.

        For compound powers (e.g., "Clone & Reverse"), returns the non-Clone
        component if one exists. Clone itself has no activation effect.

        Args:
            card: The card to check.

        Returns:
            The power name (lowercase) if the card has an activatable power,
            or None if it has no activatable power.
        """
        power_text = card.power_text.lower().strip()

        # Handle compound powers (e.g., "clone & reverse")
        if "&" in power_text:
            parts = [p.strip() for p in power_text.split("&")]
            # Filter out "clone" — it has no activation effect
            activatable_parts = [p for p in parts if p in ACTIVATABLE_POWERS]
            if activatable_parts:
                return activatable_parts[0]
            return None

        # Simple power
        if power_text in ACTIVATABLE_POWERS:
            return power_text

        return None

    def create_power_prompt(
        self, game_state: GameState, player_index: int, card: CardInstance
    ) -> Optional[List[dict]]:
        """Create a pending power prompt after a card with an activatable power is played.

        Sets game_state.pending_power and returns prompt events.

        Args:
            game_state: The current game state (modified in place).
            player_index: Index of the player who played the card.
            card: The card that was played.

        Returns:
            A list of prompt events if the card has an activatable power,
            or None if no power prompt is needed.

        Requirements: 9.1
        """
        power_name = self.get_activatable_power(card)
        if power_name is None:
            return None

        game_state.pending_power = PendingPower(
            player_index=player_index,
            card=card,
            power_name=power_name,
            phase="activate_or_decline",
        )

        return [
            {
                "type": "power_prompt",
                "prompt_type": "activate_or_decline",
                "player_id": game_state.players[player_index].player_id,
                "card_id": card.card_id,
                "power_name": power_name,
                "message": f"Activate {power_name} power or decline?",
            }
        ]

    def handle_power_choice(
        self, game_state: GameState, player_index: int, choice: dict
    ) -> Union[List[dict], Tuple[str, str]]:
        """Handle a player's power choice response.

        Processes the player's response to a power prompt. This can be:
        - An activate/decline choice (phase 1)
        - A target/card selection (phase 2)

        Args:
            game_state: The current game state (modified in place).
            player_index: Index of the player making the choice.
            choice: A dict with choice details:
                - {"choice": "decline"} — decline the power
                - {"choice": "activate"} — activate (for immediate powers)
                - {"choice": "activate", "card_id": int} — for Discard
                - {"choice": "activate", "target_player_index": int} — for Poison
                - {"choice": "activate", "card_id": int, "play_immediately": bool} — for Rescue

        Returns:
            On success: A list of game event dicts.
            On error: A tuple of (error_code, error_message).
        """
        pending = game_state.pending_power
        if pending is None:
            return ("no_pending_power", "No pending power to resolve.")

        if pending.player_index != player_index:
            return ("not_your_power", "This pending power is not yours to resolve.")

        # Phase 1: Activate or decline
        if pending.phase == "activate_or_decline":
            return self._handle_activate_or_decline(game_state, player_index, choice)

        # Phase 2: Target/choice selection
        if pending.phase == "choose_target":
            return self._handle_target_choice(game_state, player_index, choice)

        return ("invalid_phase", f"Unknown power phase: {pending.phase}")

    def _handle_activate_or_decline(
        self, game_state: GameState, player_index: int, choice: dict
    ) -> Union[List[dict], Tuple[str, str]]:
        """Handle the activate/decline choice for a power.

        Args:
            game_state: The current game state (modified in place).
            player_index: Index of the player making the choice.
            choice: Dict with "choice" key ("activate" or "decline").

        Returns:
            List of events on success, or error tuple on failure.

        Requirements: 9.1
        """
        pending = game_state.pending_power
        player_choice = choice.get("choice")

        if player_choice == "decline":
            # Clear pending power — card was already placed on play pile
            game_state.pending_power = None
            return [
                {
                    "type": "power_declined",
                    "player_id": game_state.players[player_index].player_id,
                    "power_name": pending.power_name,
                }
            ]

        if player_choice != "activate":
            return ("invalid_choice", "Choice must be 'activate' or 'decline'.")

        # Activate the power
        power_name = pending.power_name

        # Immediate powers: execute right away
        if power_name in IMMEDIATE_POWERS:
            game_state.pending_power = None
            return self._execute_immediate_power(game_state, player_index, power_name)

        # Powers needing a target: transition to choose_target phase
        if power_name in POWERS_NEEDING_TARGET:
            pending.phase = "choose_target"
            return self._create_target_prompt(game_state, player_index, power_name)

        # Unknown power — shouldn't happen
        game_state.pending_power = None
        return ("unknown_power", f"Unknown power: {power_name}")

    def _execute_immediate_power(
        self, game_state: GameState, player_index: int, power_name: str
    ) -> List[dict]:
        """Execute a power that needs no target selection.

        Args:
            game_state: The current game state (modified in place).
            player_index: Index of the player activating the power.
            power_name: The power to execute.

        Returns:
            List of game events describing the power effect.
        """
        if power_name == "go":
            return self._execute_go(game_state, player_index)
        elif power_name == "skip":
            return self._execute_skip(game_state, player_index)
        elif power_name == "reverse":
            return self._execute_reverse(game_state, player_index)
        return []

    def _execute_go(self, game_state: GameState, player_index: int) -> List[dict]:
        """Execute the Go power: grant an additional turn.

        The active player remains the active player. The sequence has already
        been advanced when the card was played.

        Args:
            game_state: The current game state (modified in place).
            player_index: Index of the player activating Go.

        Returns:
            List of game events.

        Requirements: 9.3
        """
        # Keep the current player as active (undo the turn advance that happened)
        game_state.current_player_index = player_index

        return [
            {
                "type": "power_activated",
                "power_name": "go",
                "player_id": game_state.players[player_index].player_id,
                "effect": "additional_turn",
            }
        ]

    def _execute_skip(self, game_state: GameState, player_index: int) -> List[dict]:
        """Execute the Skip power: skip the next player in current direction.

        Advances the turn one extra time past the next player.

        Args:
            game_state: The current game state (modified in place).
            player_index: Index of the player activating Skip.

        Returns:
            List of game events.

        Requirements: 9.4
        """
        player_count = len(game_state.players)

        # Find the next non-decked player (the one being skipped)
        skipped_index = game_state.current_player_index
        for _ in range(player_count):
            skipped_index = (skipped_index + game_state.direction) % player_count
            if not game_state.players[skipped_index].is_decked:
                break

        # Now advance past the skipped player to the one after
        next_index = skipped_index
        for _ in range(player_count):
            next_index = (next_index + game_state.direction) % player_count
            if not game_state.players[next_index].is_decked:
                break

        game_state.current_player_index = next_index

        return [
            {
                "type": "power_activated",
                "power_name": "skip",
                "player_id": game_state.players[player_index].player_id,
                "skipped_player_id": game_state.players[skipped_index].player_id,
                "next_player_id": game_state.players[next_index].player_id,
            }
        ]

    def _execute_reverse(
        self, game_state: GameState, player_index: int
    ) -> List[dict]:
        """Execute the Reverse power: toggle play direction.

        Toggles direction between 1 (clockwise) and -1 (counterclockwise).

        Args:
            game_state: The current game state (modified in place).
            player_index: Index of the player activating Reverse.

        Returns:
            List of game events.

        Requirements: 9.7
        """
        game_state.direction *= -1

        return [
            {
                "type": "power_activated",
                "power_name": "reverse",
                "player_id": game_state.players[player_index].player_id,
                "new_direction": game_state.direction,
            }
        ]

    def _create_target_prompt(
        self, game_state: GameState, player_index: int, power_name: str
    ) -> List[dict]:
        """Create a target selection prompt for powers that need one.

        Args:
            game_state: The current game state.
            player_index: Index of the player who needs to choose.
            power_name: The power being activated.

        Returns:
            List of prompt events.
        """
        player = game_state.players[player_index]

        if power_name == "discard":
            # Prompt to choose a card from hand
            card_ids = [c.card_id for c in player.hand]
            return [
                {
                    "type": "power_prompt",
                    "prompt_type": "choose_card_from_hand",
                    "player_id": player.player_id,
                    "power_name": "discard",
                    "options": card_ids,
                    "message": "Choose a card from your hand to discard.",
                }
            ]

        elif power_name == "poison":
            # Prompt to choose an opponent with at least 1 card in draw deck
            valid_targets = []
            for i, p in enumerate(game_state.players):
                if i != player_index and len(p.draw_deck) > 0:
                    valid_targets.append(i)
            return [
                {
                    "type": "power_prompt",
                    "prompt_type": "choose_target_player",
                    "player_id": player.player_id,
                    "power_name": "poison",
                    "options": valid_targets,
                    "message": "Choose an opponent with cards in their draw deck.",
                }
            ]

        elif power_name == "rescue":
            # Prompt to choose a card from discard pile
            card_ids = [c.card_id for c in player.discard_pile]
            return [
                {
                    "type": "power_prompt",
                    "prompt_type": "choose_card_from_discard",
                    "player_id": player.player_id,
                    "power_name": "rescue",
                    "options": card_ids,
                    "message": "Choose a card from your discard pile to rescue.",
                }
            ]

        return []

    def _handle_target_choice(
        self, game_state: GameState, player_index: int, choice: dict
    ) -> Union[List[dict], Tuple[str, str]]:
        """Handle the target/card selection for a power that needs one.

        Args:
            game_state: The current game state (modified in place).
            player_index: Index of the player making the choice.
            choice: Dict with target details specific to the power.

        Returns:
            List of events on success, or error tuple on failure.
        """
        pending = game_state.pending_power
        power_name = pending.power_name

        # Clear pending power before executing
        game_state.pending_power = None

        if power_name == "discard":
            return self._execute_discard(game_state, player_index, choice)
        elif power_name == "poison":
            return self._execute_poison(game_state, player_index, choice)
        elif power_name == "rescue":
            return self._execute_rescue(game_state, player_index, choice)

        return ("unknown_power", f"Unknown power for target choice: {power_name}")

    def _execute_discard(
        self, game_state: GameState, player_index: int, choice: dict
    ) -> Union[List[dict], Tuple[str, str]]:
        """Execute the Discard power: move a chosen card from hand to discard pile.

        Args:
            game_state: The current game state (modified in place).
            player_index: Index of the player activating Discard.
            choice: Dict with "card_id" specifying which card to discard.

        Returns:
            List of events on success, or error tuple on failure.

        Requirements: 9.2
        """
        player = game_state.players[player_index]
        card_id = choice.get("card_id")

        if card_id is None:
            return ("missing_card_id", "Discard power requires a card_id choice.")

        # Find the card in hand
        card_index = None
        card = None
        for i, c in enumerate(player.hand):
            if c.card_id == card_id:
                card_index = i
                card = c
                break

        if card_index is None:
            return ("card_not_in_hand", f"Card {card_id} is not in your hand.")

        # Move card from hand to discard pile
        player.hand.pop(card_index)
        player.discard_pile.append(card)

        return [
            {
                "type": "power_activated",
                "power_name": "discard",
                "player_id": player.player_id,
                "discarded_card_id": card.card_id,
                "discarded_card_name": card.card_name,
            }
        ]

    def _execute_poison(
        self, game_state: GameState, player_index: int, choice: dict
    ) -> Union[List[dict], Tuple[str, str]]:
        """Execute the Poison power: discard top of target's draw deck, score denomination.

        Args:
            game_state: The current game state (modified in place).
            player_index: Index of the player activating Poison.
            choice: Dict with "target_player_index" specifying the target.

        Returns:
            List of events on success, or error tuple on failure.

        Requirements: 9.5
        """
        target_index = choice.get("target_player_index")

        if target_index is None:
            return (
                "missing_target",
                "Poison power requires a target_player_index choice.",
            )

        # Validate target
        if target_index == player_index:
            return ("invalid_target", "Cannot target yourself with Poison.")

        if target_index < 0 or target_index >= len(game_state.players):
            return ("invalid_target", "Target player index out of range.")

        target = game_state.players[target_index]

        if len(target.draw_deck) == 0:
            return (
                "invalid_target",
                "Target player has no cards in their draw deck.",
            )

        # Discard top card of target's draw deck
        top_card = target.draw_deck.pop(0)
        target.discard_pile.append(top_card)

        # Score the denomination for the active player
        player = game_state.players[player_index]
        self._score_service.apply_immediate_score(
            game_state, player.player_id, top_card.denomination
        )

        return [
            {
                "type": "power_activated",
                "power_name": "poison",
                "player_id": player.player_id,
                "target_player_id": target.player_id,
                "discarded_card_id": top_card.card_id,
                "discarded_card_denomination": top_card.denomination,
                "points_scored": top_card.denomination,
            }
        ]

    def _execute_rescue(
        self, game_state: GameState, player_index: int, choice: dict
    ) -> Union[List[dict], Tuple[str, str]]:
        """Execute the Rescue power: recover a card from discard pile.

        The chosen card is either placed face-down on top of the draw deck,
        or if its denomination matches the current sequence, played immediately.

        Args:
            game_state: The current game state (modified in place).
            player_index: Index of the player activating Rescue.
            choice: Dict with "card_id" and optionally "play_immediately" (bool).

        Returns:
            List of events on success, or error tuple on failure.

        Requirements: 9.6
        """
        player = game_state.players[player_index]
        card_id = choice.get("card_id")
        play_immediately = choice.get("play_immediately", False)

        if card_id is None:
            return ("missing_card_id", "Rescue power requires a card_id choice.")

        # Find the card in discard pile
        card_index = None
        card = None
        for i, c in enumerate(player.discard_pile):
            if c.card_id == card_id:
                card_index = i
                card = c
                break

        if card_index is None:
            return (
                "card_not_in_discard",
                f"Card {card_id} is not in your discard pile.",
            )

        # Remove from discard pile
        player.discard_pile.pop(card_index)

        if play_immediately and card.denomination == game_state.current_sequence:
            # Play immediately — place on play pile
            player.play_pile.append(card)

            # Update sequence and last_played_denomination
            game_state.last_played_denomination = card.denomination
            # Advance sequence
            sequence_cycle = [1, 10, 100, 1000, 10000, 100000]
            idx = sequence_cycle.index(card.denomination)
            game_state.current_sequence = sequence_cycle[(idx + 1) % len(sequence_cycle)]

            return [
                {
                    "type": "power_activated",
                    "power_name": "rescue",
                    "player_id": player.player_id,
                    "rescued_card_id": card.card_id,
                    "rescued_card_name": card.card_name,
                    "action": "played_immediately",
                    "new_sequence": game_state.current_sequence,
                }
            ]
        else:
            # Place face-down on top of draw deck
            player.draw_deck.insert(0, card)

            return [
                {
                    "type": "power_activated",
                    "power_name": "rescue",
                    "player_id": player.player_id,
                    "rescued_card_id": card.card_id,
                    "rescued_card_name": card.card_name,
                    "action": "placed_on_draw_deck",
                }
            ]
