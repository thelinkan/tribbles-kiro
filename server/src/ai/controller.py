"""AI Controller — decision-making for computer-controlled players and AI substitutes.

This module implements the AIController class which provides automated
decision-making for both permanent computer players and AI_Substitute seats
(disconnected players after timeout).

The same strategy is used for both cases. The AI operates on the player's
existing hand, draw deck, play pile, and discard pile without modification.

Requirements: 4.7, 4.8, 21.4, 21.5
"""

from typing import List, Optional

from models import CardInstance, GameState, PendingDraw, PendingPower, PlayerState


# Powers considered beneficial to the activating player
BENEFICIAL_POWERS = {
    "go", "reverse", "discard", "rescue", "cycle", "recycle",
    "replay", "process", "evolve", "mutate", "draw", "exchange",
    "advance", "convert", "masaka", "scan", "utilize",
}

# Powers that target opponents (offensive)
OFFENSIVE_POWERS = {
    "skip", "poison", "kill", "score", "battle", "freeze",
    "toxin", "avalanche", "stampede", "assimilate", "copy",
}


class AIController:
    """Decision-making for computer-controlled players and AI substitutes.

    Provides a single entry point `choose_action` that examines the current
    game state and returns a valid action dict for the specified player.

    Strategy:
    - Prefer playing cards that advance the sequence
    - Activate beneficial powers (Go, Reverse, Discard, etc.)
    - Target the player with the highest cumulative score for offensive powers
    - Draw when no valid play is available

    Requirements: 4.7, 4.8, 21.4, 21.5
    """

    def choose_action(self, game_state: GameState, player_id: int) -> dict:
        """Select a valid action for the given player.

        Examines the game state and returns the best action the AI can take.
        Handles pending draws, pending powers, and normal turn play.

        Args:
            game_state: The current game state.
            player_id: The ID of the player to act for.

        Returns:
            A dict representing the action, matching the format expected by
            GameEngine.process_action:
            - {"type": "play_card", "card_id": int, "activate_power": bool}
            - {"type": "draw_card"}
            - {"type": "accept_draw"}
            - {"type": "power_choice", "choice": str, ...}
        """
        # Find the player
        player = self._find_player(game_state, player_id)
        if player is None:
            return {"type": "draw_card"}

        player_index = self._find_player_index(game_state, player_id)

        # Handle pending draw first
        if game_state.pending_draw is not None:
            if game_state.pending_draw.player_id == player_id:
                return self._handle_pending_draw(game_state)

        # Handle pending power
        if game_state.pending_power is not None:
            if game_state.pending_power.player_index == player_index:
                return self._handle_pending_power(game_state, player_index)

        # Normal turn: find valid plays from hand
        valid_plays = self._get_valid_plays(player.hand, game_state)

        if valid_plays:
            best_card = self._choose_best_card(valid_plays, game_state)
            activate = self._should_activate_power(best_card, game_state, player_index)
            return {
                "type": "play_card",
                "card_id": best_card.card_id,
                "activate_power": activate,
            }

        # No valid plays — draw a card
        return {"type": "draw_card"}

    def _find_player(self, game_state: GameState, player_id: int) -> Optional[PlayerState]:
        """Find a player by ID in the game state."""
        for p in game_state.players:
            if p.player_id == player_id:
                return p
        return None

    def _find_player_index(self, game_state: GameState, player_id: int) -> int:
        """Find a player's index by ID in the game state."""
        for i, p in enumerate(game_state.players):
            if p.player_id == player_id:
                return i
        return -1

    def _handle_pending_draw(self, game_state: GameState) -> dict:
        """Handle a pending draw decision.

        If the drawn card matches the sequence, play it immediately.
        If it doesn't match, accept it.

        Args:
            game_state: The current game state.

        Returns:
            Action dict for the pending draw.
        """
        pending = game_state.pending_draw
        if pending.matches_sequence:
            # Play the matching drawn card immediately
            return {
                "type": "play_card",
                "card_id": pending.card.card_id,
                "activate_power": self._should_activate_power_for_card(
                    pending.card, game_state,
                    self._find_player_index(game_state, pending.player_id)
                ),
            }
        else:
            # Non-matching draw — accept it
            return {"type": "accept_draw"}

    def _handle_pending_power(self, game_state: GameState, player_index: int) -> dict:
        """Handle a pending power choice.

        Args:
            game_state: The current game state.
            player_index: Index of the player making the choice.

        Returns:
            Action dict for the power choice.
        """
        pending = game_state.pending_power

        if pending.phase == "activate_or_decline":
            return self._decide_activate_or_decline(game_state, player_index, pending)

        if pending.phase == "choose_target":
            return self._decide_target_choice(game_state, player_index, pending)

        # Default: decline unknown phases
        return {"type": "power_choice", "choice": "decline"}

    def _decide_activate_or_decline(
        self, game_state: GameState, player_index: int, pending: PendingPower
    ) -> dict:
        """Decide whether to activate or decline a power.

        Strategy: Always activate beneficial powers and offensive powers.
        Only decline if the power would be harmful to self.

        Args:
            game_state: The current game state.
            player_index: Index of the player.
            pending: The pending power information.

        Returns:
            Action dict with activate or decline choice.
        """
        power_name = pending.power_name.lower()

        # For compound powers, check the components
        if "&" in power_name:
            parts = [p.strip() for p in power_name.split("&")]
            # Activate if any component is beneficial or offensive
            should_activate = any(
                p in BENEFICIAL_POWERS or p in OFFENSIVE_POWERS for p in parts
            )
        else:
            should_activate = (
                power_name in BENEFICIAL_POWERS or power_name in OFFENSIVE_POWERS
            )

        # Special case: Avalanche — only activate if we have >= 4 cards in hand
        if "avalanche" in power_name:
            player = game_state.players[player_index]
            if len(player.hand) < 4:
                should_activate = False

        if should_activate:
            return {"type": "power_choice", "choice": "activate"}
        else:
            return {"type": "power_choice", "choice": "decline"}

    def _decide_target_choice(
        self, game_state: GameState, player_index: int, pending: PendingPower
    ) -> dict:
        """Decide on a target or card choice for a power.

        Strategy:
        - For target selection: pick the opponent with the highest score
        - For card choices from hand (Discard): pick the lowest denomination card
        - For Toxin revealed cards: pick the highest denomination card

        Args:
            game_state: The current game state.
            player_index: Index of the player.
            pending: The pending power information.

        Returns:
            Action dict with the target/card choice.
        """
        power_name = pending.power_name.lower()
        player = game_state.players[player_index]

        # Powers that need a target player
        if power_name in ("poison", "kill", "score", "battle", "copy",
                          "draw", "recycle", "assimilate", "scan"):
            target = self._choose_target_opponent(game_state, player_index, pending)
            return {
                "type": "power_choice",
                "choice": "activate",
                "target_player_index": target,
            }

        # Discard: choose lowest denomination card from hand
        if power_name == "discard":
            card_id = self._choose_lowest_denomination_card(player.hand)
            return {
                "type": "power_choice",
                "choice": "activate",
                "card_id": card_id,
            }

        # Rescue: choose highest denomination card from discard pile
        if power_name == "rescue":
            if player.discard_pile:
                best = max(player.discard_pile, key=lambda c: c.denomination)
                play_immediately = (best.denomination == game_state.current_sequence)
                return {
                    "type": "power_choice",
                    "choice": "activate",
                    "card_id": best.card_id,
                    "play_immediately": play_immediately,
                }
            return {"type": "power_choice", "choice": "decline"}

        # Cycle: choose lowest denomination card from hand to place under deck
        if power_name == "cycle":
            card_id = self._choose_lowest_denomination_card(player.hand)
            return {
                "type": "power_choice",
                "choice": "activate",
                "card_id": card_id,
            }

        # Exchange: choose lowest denomination card from hand to discard
        if power_name == "exchange":
            card_id = self._choose_lowest_denomination_card(player.hand)
            # Choose highest denomination from discard pile to take
            if player.discard_pile:
                take_card = max(player.discard_pile, key=lambda c: c.denomination)
                return {
                    "type": "power_choice",
                    "choice": "activate",
                    "card_id": card_id,
                    "take_card_id": take_card.card_id,
                }
            return {"type": "power_choice", "choice": "activate", "card_id": card_id}

        # Replay: choose highest denomination card from play pile
        if power_name == "replay":
            if player.play_pile:
                best = max(player.play_pile, key=lambda c: c.denomination)
                return {
                    "type": "power_choice",
                    "choice": "activate",
                    "card_id": best.card_id,
                }
            return {"type": "power_choice", "choice": "decline"}

        # Process: choose 2 lowest denomination cards from hand to place under deck
        if power_name == "process":
            if len(player.hand) >= 2:
                sorted_hand = sorted(player.hand, key=lambda c: c.denomination)
                card_ids = [sorted_hand[0].card_id, sorted_hand[1].card_id]
                return {
                    "type": "power_choice",
                    "choice": "activate",
                    "card_ids": card_ids,
                }
            elif len(player.hand) == 1:
                return {
                    "type": "power_choice",
                    "choice": "activate",
                    "card_ids": [player.hand[0].card_id],
                }
            return {"type": "power_choice", "choice": "activate", "card_ids": []}

        # Freeze: choose a common offensive power to freeze
        if power_name == "freeze":
            return {
                "type": "power_choice",
                "choice": "activate",
                "power_to_freeze": "go",
            }

        # Toxin: choose the highest denomination revealed card
        if power_name == "toxin" and pending.toxin_revealed:
            best_revealed = max(pending.toxin_revealed, key=lambda t: t[1].denomination)
            return {
                "type": "power_choice",
                "choice": "activate",
                "card_id": best_revealed[1].card_id,
            }

        # Avalanche: choose lowest denomination card for additional discard
        if power_name == "avalanche":
            if player.hand:
                card_id = self._choose_lowest_denomination_card(player.hand)
                return {
                    "type": "power_choice",
                    "choice": "activate",
                    "card_id": card_id,
                }
            return {"type": "power_choice", "choice": "activate"}

        # Utilize: choose a card from discard pile
        if power_name == "utilize":
            if player.discard_pile:
                best = max(player.discard_pile, key=lambda c: c.denomination)
                return {
                    "type": "power_choice",
                    "choice": "activate",
                    "card_id": best.card_id,
                }
            return {"type": "power_choice", "choice": "decline"}

        # Default: just activate with no extra params
        return {"type": "power_choice", "choice": "activate"}

    def _choose_target_opponent(
        self, game_state: GameState, player_index: int, pending: PendingPower
    ) -> int:
        """Choose the best opponent to target.

        Strategy: target the player with the highest cumulative score
        (most threatening opponent). Falls back to valid options if available.

        Args:
            game_state: The current game state.
            player_index: Index of the AI player.
            pending: The pending power with valid options.

        Returns:
            Index of the chosen target player.
        """
        # Use options from pending power if available
        valid_targets = pending.options if pending.options else []

        if not valid_targets:
            # Fallback: all other non-decked players
            valid_targets = [
                i for i, p in enumerate(game_state.players)
                if i != player_index and not p.is_decked
            ]

        if not valid_targets:
            # Last resort: any other player
            valid_targets = [
                i for i in range(len(game_state.players))
                if i != player_index
            ]

        # Choose the player with the highest score (most threatening)
        best_target = max(
            valid_targets,
            key=lambda i: game_state.players[i].cumulative_score,
        )
        return best_target

    def _get_valid_plays(
        self, hand: List[CardInstance], game_state: GameState
    ) -> List[CardInstance]:
        """Get all valid cards that can be played from hand.

        A card is valid if:
        - Its denomination matches the current sequence, OR
        - The sequence is broken and it's a 1-denomination card, OR
        - The sequence is broken and it has the Advance power, OR
        - It's a Clone card and its denomination matches last_played_denomination.

        Args:
            hand: The player's hand.
            game_state: The current game state.

        Returns:
            List of cards that can be legally played.
        """
        valid = []
        for card in hand:
            if self._is_valid_play(card, game_state):
                valid.append(card)
        return valid

    def _is_valid_play(self, card: CardInstance, game_state: GameState) -> bool:
        """Check if a card is a valid play given the current game state.

        Args:
            card: The card to validate.
            game_state: The current game state.

        Returns:
            True if the card can be legally played.
        """
        # Normal play: denomination matches current sequence
        if card.denomination == game_state.current_sequence:
            return True

        # Sequence break: allow 1-denomination card
        if game_state.sequence_broken and card.denomination == 1:
            return True

        # Sequence break: allow Advance power card
        if game_state.sequence_broken and self._is_advance_card(card):
            return True

        # Clone: denomination matches last_played_denomination
        if (
            self._is_clone_card(card)
            and game_state.last_played_denomination is not None
            and card.denomination == game_state.last_played_denomination
        ):
            return True

        return False

    def _is_clone_card(self, card: CardInstance) -> bool:
        """Check if a card has the Clone power."""
        return "clone" in card.power_text.lower()

    def _is_advance_card(self, card: CardInstance) -> bool:
        """Check if a card has the Advance power."""
        return "advance" in card.power_text.lower()

    def _choose_best_card(
        self, valid_plays: List[CardInstance], game_state: GameState
    ) -> CardInstance:
        """Choose the best card to play from valid options.

        Strategy:
        - Prefer cards that advance the sequence (matching current_sequence)
        - Among those, prefer cards with beneficial powers (Go is best)
        - Prefer higher denomination cards (they score more in play pile)
        - Clone cards are lower priority unless they have a good compound power

        Args:
            valid_plays: List of valid cards to choose from.
            game_state: The current game state.

        Returns:
            The best card to play.
        """
        def card_score(card: CardInstance) -> tuple:
            """Score a card for priority. Higher tuple = better choice."""
            power = card.power_text.lower().strip()

            # Prefer cards matching current sequence (advance the game)
            matches_sequence = 1 if card.denomination == game_state.current_sequence else 0

            # Power priority: Go is best (extra turn), then other beneficial powers
            power_priority = 0
            if "go" in power:
                power_priority = 10
            elif any(p in power for p in ("reverse", "skip", "poison", "score")):
                power_priority = 5
            elif any(p in power for p in BENEFICIAL_POWERS):
                power_priority = 3
            elif "clone" in power:
                power_priority = 1

            # Higher denomination = more points in play pile
            denomination_score = card.denomination

            return (matches_sequence, power_priority, denomination_score)

        return max(valid_plays, key=card_score)

    def _should_activate_power(
        self, card: CardInstance, game_state: GameState, player_index: int
    ) -> bool:
        """Decide whether to activate a card's power.

        Strategy: activate beneficial and offensive powers, decline harmful ones.

        Args:
            card: The card being played.
            game_state: The current game state.
            player_index: Index of the AI player.

        Returns:
            True if the power should be activated.
        """
        return self._should_activate_power_for_card(card, game_state, player_index)

    def _should_activate_power_for_card(
        self, card: CardInstance, game_state: GameState, player_index: int
    ) -> bool:
        """Decide whether to activate a card's power.

        Args:
            card: The card being played.
            game_state: The current game state.
            player_index: Index of the AI player.

        Returns:
            True if the power should be activated.
        """
        power = card.power_text.lower().strip()

        # No power or passive power — nothing to activate
        if not power or power in ("clone", "antidote", "quadruple", "safety",
                                   "tally", "time_warp", "advance", "bonus", "idic"):
            return False

        # Handle compound powers
        if "&" in power:
            parts = [p.strip() for p in power.split("&")]
            # Activate if any non-clone component is beneficial or offensive
            non_clone = [p for p in parts if p != "clone"]
            return any(p in BENEFICIAL_POWERS or p in OFFENSIVE_POWERS for p in non_clone)

        # Avalanche: only activate if we have enough cards
        if power == "avalanche":
            player = game_state.players[player_index]
            return len(player.hand) >= 4

        # Activate beneficial and offensive powers
        return power in BENEFICIAL_POWERS or power in OFFENSIVE_POWERS

    def _choose_lowest_denomination_card(self, cards: List[CardInstance]) -> int:
        """Choose the card with the lowest denomination from a list.

        Args:
            cards: List of cards to choose from.

        Returns:
            The card_id of the lowest denomination card.
        """
        if not cards:
            return -1
        lowest = min(cards, key=lambda c: c.denomination)
        return lowest.card_id
