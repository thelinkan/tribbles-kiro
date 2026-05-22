"""Power resolution framework for the Tribbles card game.

This module implements the PowerResolver class which dispatches and executes
card power effects. It handles the two-phase activation flow:
  Phase 1: Prompt player to activate or decline the power.
  Phase 2: Execute the power effect (possibly with additional target selection).

Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 11.1, 11.2, 11.3,
              11.4, 11.5, 11.6, 11.7, 11.8, 11.9
"""

import random
from typing import List, Optional, Tuple, Union

from models import CardInstance, GameState, PendingPower, PlayerState
from scoring.service import ScoreService


# Powers that can be activated (have an effect beyond just being played)
ACTIVATABLE_POWERS = {
    "discard", "go", "skip", "poison", "rescue", "reverse",
    # Expansion 3: More Tribbles More Troubles
    "copy", "cycle", "draw", "exchange", "kill", "recycle", "replay", "score",
    # Expansion 4: No Tribble at All
    "battle", "evolve", "freeze", "mutate", "process", "toxin",
    # Expansion 5: Trials and Tribble-ations
    "avalanche", "famine", "stampede",
    # Expansion 6: Nothing But Tribble
    "assimilate", "convert", "masaka", "scan", "utilize",
}

# Powers that require a target or choice after activation
POWERS_NEEDING_TARGET = {
    "discard", "poison", "rescue",
    # Expansion 3
    "copy", "cycle", "draw", "exchange", "kill", "recycle", "replay", "score",
    # Expansion 4
    "battle", "freeze", "process", "toxin",
    # Expansion 5
    "avalanche",
    # Expansion 6
    "assimilate", "scan", "utilize",
}

# Powers that execute immediately on activation (no target needed)
IMMEDIATE_POWERS = {"go", "skip", "reverse", "evolve", "mutate", "famine", "stampede", "convert", "masaka"}

# Antidote is a passive power — it triggers during Poison resolution, not actively played
PASSIVE_POWERS = {"antidote", "quadruple", "safety", "tally", "time_warp", "advance", "idic"}


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

        Extracts the power name from the card_name field (pattern: "Tribble - PowerName")
        or falls back to checking if the power_text starts with a known power name.

        For compound powers (e.g., "Clone & Reverse"), returns the non-Clone
        component if one exists. Clone itself has no activation effect.

        For compound powers where neither component is Clone, returns both
        power names joined by "&" to indicate both must activate together.

        Args:
            card: The card to check.

        Returns:
            The power name (lowercase) if the card has an activatable power,
            or a compound string "power1&power2" if both must activate,
            or None if it has no activatable power.
        """
        # Extract power name from card_name (e.g., "Tribble - Skip" → "skip")
        # Also handles compound names like "Tribble - Clone & Reverse"
        power_name = self._extract_power_name(card)
        if power_name is None:
            return None

        # Handle compound powers (e.g., "clone & reverse")
        if "&" in power_name:
            parts = [p.strip() for p in power_name.split("&")]
            has_clone = "clone" in parts
            activatable_parts = [p for p in parts if p in ACTIVATABLE_POWERS]

            if has_clone:
                # If one is Clone: only the non-Clone power activates independently
                non_clone_parts = [p for p in activatable_parts if p != "clone"]
                if non_clone_parts:
                    return non_clone_parts[0]
                return None
            else:
                # Neither is Clone: both powers must activate together
                if len(activatable_parts) >= 2:
                    return "&".join(activatable_parts)
                elif len(activatable_parts) == 1:
                    return activatable_parts[0]
                return None

        # Simple power
        if power_name in ACTIVATABLE_POWERS:
            return power_name

        return None

    def _extract_power_name(self, card: CardInstance) -> Optional[str]:
        """Extract the power name from a card's card_name or power_text.

        Tries the card_name first (pattern: "Tribble - PowerName" or
        "Tribble - Power1 & Power2"), then falls back to checking if the
        first word of power_text matches a known power.

        Args:
            card: The card to extract the power name from.

        Returns:
            The power name in lowercase, or None if not found.
        """
        # Try extracting from card_name (e.g., "Tribble - Skip" → "skip")
        card_name = card.card_name or ""
        if " - " in card_name:
            power_part = card_name.split(" - ", 1)[1].strip().lower()
            # Check if it's a known power or compound
            if "&" in power_part:
                # Compound: "clone & reverse" → check parts
                parts = [p.strip() for p in power_part.split("&")]
                if any(p in ACTIVATABLE_POWERS or p in PASSIVE_POWERS for p in parts):
                    return power_part
            elif power_part in ACTIVATABLE_POWERS or power_part in PASSIVE_POWERS:
                return power_part

        # Fallback: check if power_text starts with or contains a known power name
        power_text = (card.power_text or "").lower().strip()
        if not power_text:
            return None

        # Check first word
        first_word = power_text.split()[0].rstrip(".:,;") if power_text else ""
        if first_word in ACTIVATABLE_POWERS:
            return first_word

        # Check if any known power name appears at the start of power_text
        for power in ACTIVATABLE_POWERS:
            if power_text.startswith(power):
                return power

        return None

    def get_compound_powers(self, card: CardInstance) -> Optional[List[str]]:
        """Get the list of individual activatable powers from a compound card.

        Args:
            card: The card to check.

        Returns:
            A list of power names if compound, or None if not compound.
        """
        power_name = self._extract_power_name(card)
        if power_name is None or "&" not in power_name:
            return None
        parts = [p.strip() for p in power_name.split("&")]
        return [p for p in parts if p in ACTIVATABLE_POWERS]

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

        # Skip activation prompt if the power cannot be used
        player = game_state.players[player_index]
        if power_name == "rescue" and not player.discard_pile:
            return None
        if power_name == "discard" and not player.hand:
            return None
        if power_name == "poison":
            has_target = any(
                len(p.draw_deck) > 0
                for i, p in enumerate(game_state.players)
                if i != player_index
            )
            if not has_target:
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

        # Handle compound powers (both must activate together)
        if "&" in power_name:
            # Both powers activate together — execute them sequentially
            parts = [p.strip() for p in power_name.split("&")]
            game_state.pending_power = None
            all_events = []
            for part in parts:
                if part in IMMEDIATE_POWERS:
                    events = self._execute_immediate_power(game_state, player_index, part)
                    all_events.extend(events)
                elif part in POWERS_NEEDING_TARGET:
                    # For compound powers with target-needing components,
                    # set up the first target-needing power as pending
                    pending.power_name = part
                    pending.phase = "choose_target"
                    game_state.pending_power = pending
                    prompt_events = self._create_target_prompt(game_state, player_index, part)
                    all_events.extend(prompt_events)
                    return all_events
            return all_events

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
        elif power_name == "evolve":
            return self._execute_evolve(game_state, player_index)
        elif power_name == "mutate":
            return self._execute_mutate(game_state, player_index)
        elif power_name == "famine":
            return self._execute_famine(game_state, player_index)
        elif power_name == "stampede":
            return self._execute_stampede(game_state, player_index)
        elif power_name == "convert":
            return self._execute_convert(game_state, player_index)
        elif power_name == "masaka":
            return self._execute_masaka(game_state, player_index)
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
            # Prompt to choose a card from discard pile (include full card info)
            card_options = [
                {"card_id": c.card_id, "card_name": c.card_name, "denomination": c.denomination, "power_text": c.power_text}
                for c in player.discard_pile
            ]
            return [
                {
                    "type": "power_prompt",
                    "prompt_type": "choose_card_from_discard",
                    "player_id": player.player_id,
                    "power_name": "rescue",
                    "options": card_options,
                    "message": "Choose a card from your discard pile to rescue.",
                }
            ]

        elif power_name == "copy":
            # Prompt to choose another player's play pile to copy from
            valid_targets = []
            for i, p in enumerate(game_state.players):
                if i != player_index and len(p.play_pile) > 0:
                    valid_targets.append(i)
            return [
                {
                    "type": "power_prompt",
                    "prompt_type": "choose_target_player",
                    "player_id": player.player_id,
                    "power_name": "copy",
                    "options": valid_targets,
                    "message": "Choose a player whose top play pile card to copy.",
                }
            ]

        elif power_name == "cycle":
            # Prompt to choose a card from hand to place under draw deck
            card_ids = [c.card_id for c in player.hand]
            return [
                {
                    "type": "power_prompt",
                    "prompt_type": "choose_card_from_hand",
                    "player_id": player.player_id,
                    "power_name": "cycle",
                    "options": card_ids,
                    "message": "Choose a card from your hand to place under your draw deck.",
                }
            ]

        elif power_name == "draw":
            # Prompt to choose any player to draw a card
            valid_targets = []
            for i, p in enumerate(game_state.players):
                if len(p.draw_deck) > 0:
                    valid_targets.append(i)
            return [
                {
                    "type": "power_prompt",
                    "prompt_type": "choose_target_player",
                    "player_id": player.player_id,
                    "power_name": "draw",
                    "options": valid_targets,
                    "message": "Choose any player to draw one card from their draw deck.",
                }
            ]

        elif power_name == "exchange":
            # Prompt to choose a card from hand to discard
            card_ids = [c.card_id for c in player.hand]
            return [
                {
                    "type": "power_prompt",
                    "prompt_type": "choose_card_from_hand",
                    "player_id": player.player_id,
                    "power_name": "exchange",
                    "options": card_ids,
                    "message": "Choose a card from your hand to discard for Exchange.",
                }
            ]

        elif power_name == "kill":
            # Prompt to choose any player with cards in their play pile
            valid_targets = []
            for i, p in enumerate(game_state.players):
                if len(p.play_pile) > 0:
                    valid_targets.append(i)
            return [
                {
                    "type": "power_prompt",
                    "prompt_type": "choose_target_player",
                    "player_id": player.player_id,
                    "power_name": "kill",
                    "options": valid_targets,
                    "message": "Choose a player to discard the top of their play pile.",
                }
            ]

        elif power_name == "recycle":
            # Prompt to choose any player with cards in their discard pile
            valid_targets = []
            for i, p in enumerate(game_state.players):
                if len(p.discard_pile) > 0:
                    valid_targets.append(i)
            return [
                {
                    "type": "power_prompt",
                    "prompt_type": "choose_target_player",
                    "player_id": player.player_id,
                    "power_name": "recycle",
                    "options": valid_targets,
                    "message": "Choose a player to shuffle their discard pile into their draw deck.",
                }
            ]

        elif power_name == "replay":
            # Replay can only target cards whose denomination matches the current sequence.
            # Exclude the Replay card itself from options.
            pending_card = game_state.pending_power.card if game_state.pending_power else None
            all_pile_cards = [
                {"card_id": c.card_id, "card_name": c.card_name, "denomination": c.denomination, "power_text": c.power_text}
                for c in player.play_pile
                if pending_card is None or c.card_id != pending_card.card_id
            ]
            # Filter to only cards that match the current sequence (legal to play)
            playable_options = [
                c for c in all_pile_cards
                if c["denomination"] == game_state.current_sequence
            ]

            if not playable_options:
                # No legal targets — show all pile cards for info, with Continue button
                game_state.pending_power = None
                return [
                    {
                        "type": "power_prompt",
                        "prompt_type": "activate_or_decline",
                        "player_id": player.player_id,
                        "power_name": "replay",
                        "options": [{"value": "decline", "label": "Continue"}],
                        "pile_cards": all_pile_cards,
                        "message": "No legal target — no card in your play pile matches the current sequence.",
                    }
                ]
            return [
                {
                    "type": "power_prompt",
                    "prompt_type": "choose_card_from_play_pile",
                    "player_id": player.player_id,
                    "power_name": "replay",
                    "options": playable_options,
                    "message": "Choose a card from your play pile to play again.",
                }
            ]

        elif power_name == "score":
            # Prompt to choose any other player to mark as Score target
            valid_targets = []
            for i, p in enumerate(game_state.players):
                if i != player_index:
                    valid_targets.append(i)
            return [
                {
                    "type": "power_prompt",
                    "prompt_type": "choose_target_player",
                    "player_id": player.player_id,
                    "power_name": "score",
                    "options": valid_targets,
                    "message": "Choose a player to mark as Score target.",
                }
            ]

        elif power_name == "battle":
            # Prompt to choose an opponent with at least 3 cards in draw deck
            valid_targets = []
            for i, p in enumerate(game_state.players):
                if i != player_index and len(p.draw_deck) >= 3:
                    valid_targets.append(i)
            return [
                {
                    "type": "power_prompt",
                    "prompt_type": "choose_target_player",
                    "player_id": player.player_id,
                    "power_name": "battle",
                    "options": valid_targets,
                    "message": "Choose an opponent to battle (both reveal top 3 of draw deck).",
                }
            ]

        elif power_name == "freeze":
            # Prompt to name a power to freeze
            # All activatable powers except freeze itself are valid choices
            freezable_powers = sorted(ACTIVATABLE_POWERS - {"freeze"})
            return [
                {
                    "type": "power_prompt",
                    "prompt_type": "choose_power_to_freeze",
                    "player_id": player.player_id,
                    "power_name": "freeze",
                    "options": freezable_powers,
                    "message": "Name a power to freeze until the end of your next turn.",
                }
            ]

        elif power_name == "process":
            # Process: draw 3 from deck, then prompt to place 2 under draw deck
            # First, draw 3 cards
            cards_drawn = []
            for _ in range(3):
                if len(player.draw_deck) > 0:
                    drawn = player.draw_deck.pop(0)
                    player.hand.append(drawn)
                    cards_drawn.append(drawn)

            # Now prompt to choose 2 cards from hand to place under draw deck
            card_ids = [c.card_id for c in player.hand]
            return [
                {
                    "type": "power_prompt",
                    "prompt_type": "choose_cards_from_hand",
                    "player_id": player.player_id,
                    "power_name": "process",
                    "options": card_ids,
                    "cards_drawn": [c.card_id for c in cards_drawn],
                    "count": 2,
                    "message": "Choose 2 cards from your hand to place under your draw deck.",
                }
            ]

        elif power_name == "toxin":
            # Toxin: for each Discard card in opponents' play piles, reveal top of their draw deck
            # Execute the reveal immediately and prompt for choice
            revealed_cards = []  # list of (player_index, card)
            for i, p in enumerate(game_state.players):
                if i == player_index:
                    continue
                # Count Discard cards in this opponent's play pile
                discard_count = sum(
                    1 for c in p.play_pile if c.power_text.lower().strip() == "discard"
                )
                # Reveal that many cards from top of their draw deck
                for _ in range(discard_count):
                    if len(p.draw_deck) > 0:
                        revealed = p.draw_deck.pop(0)
                        revealed_cards.append((i, revealed))

            if not revealed_cards:
                # No cards revealed — Toxin has no effect
                return [
                    {
                        "type": "power_activated",
                        "power_name": "toxin",
                        "player_id": player.player_id,
                        "effect": "no_discard_cards_found",
                        "revealed_cards": [],
                    }
                ]

            # Store revealed cards in pending power options for later resolution
            game_state.pending_power.phase = "choose_target"
            # Store revealed cards as extra state on pending power
            game_state.pending_power.toxin_revealed = revealed_cards

            revealed_info = [
                {"owner_index": idx, "card_id": card.card_id, "denomination": card.denomination}
                for idx, card in revealed_cards
            ]
            return [
                {
                    "type": "power_prompt",
                    "prompt_type": "choose_revealed_card",
                    "player_id": player.player_id,
                    "power_name": "toxin",
                    "revealed_cards": revealed_info,
                    "message": "Choose one revealed card to score its denomination.",
                }
            ]

        elif power_name == "avalanche":
            # Avalanche: check if active player has >= 4 other cards in hand
            # If condition met, all players discard one card, then active player
            # discards one additional card. Prompt active player for additional discard.
            if len(player.hand) < 4:
                # Condition not met — power has no effect
                return [
                    {
                        "type": "power_activated",
                        "power_name": "avalanche",
                        "player_id": player.player_id,
                        "effect": "condition_not_met",
                        "hand_size": len(player.hand),
                    }
                ]

            # All players discard one card (auto-discard last card from hand)
            for p in game_state.players:
                if len(p.hand) > 0:
                    discarded = p.hand.pop()
                    p.discard_pile.append(discarded)

            # Prompt active player to discard one additional card
            card_ids = [c.card_id for c in player.hand]
            if not card_ids:
                # Active player has no more cards to discard
                return [
                    {
                        "type": "power_activated",
                        "power_name": "avalanche",
                        "player_id": player.player_id,
                        "effect": "all_discarded_no_additional",
                    }
                ]

            return [
                {
                    "type": "power_prompt",
                    "prompt_type": "choose_card_from_hand",
                    "player_id": player.player_id,
                    "power_name": "avalanche",
                    "options": card_ids,
                    "message": "Avalanche: choose one additional card from your hand to discard.",
                }
            ]

        elif power_name == "assimilate":
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
                    "power_name": "assimilate",
                    "options": valid_targets,
                    "message": "Choose an opponent to assimilate the top card of their draw deck.",
                }
            ]

        elif power_name == "scan":
            # Reveal top 3 of own draw deck to self only
            revealed = []
            for i in range(min(3, len(player.draw_deck))):
                revealed.append(player.draw_deck[i])

            if not revealed:
                return [
                    {
                        "type": "power_activated",
                        "power_name": "scan",
                        "player_id": player.player_id,
                        "effect": "no_cards_to_scan",
                    }
                ]

            revealed_info = [
                {"card_id": c.card_id, "card_name": c.card_name, "denomination": c.denomination, "power_text": c.power_text}
                for c in revealed
            ]
            return [
                {
                    "type": "power_prompt",
                    "prompt_type": "scan_reorder",
                    "player_id": player.player_id,
                    "power_name": "scan",
                    "revealed_cards": revealed_info,
                    "message": "Reorder these cards and choose to place them on top or bottom of your draw deck.",
                }
            ]

        elif power_name == "utilize":
            # Prompt to choose an opponent with at least 2 cards in hand
            valid_targets = []
            for i, p in enumerate(game_state.players):
                if i != player_index and len(p.hand) >= 2:
                    valid_targets.append(i)
            return [
                {
                    "type": "power_prompt",
                    "prompt_type": "choose_target_player",
                    "player_id": player.player_id,
                    "power_name": "utilize",
                    "options": valid_targets,
                    "message": "Choose an opponent with at least 2 cards in hand.",
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

        # Allow declining during target selection (e.g., no valid targets available)
        if choice.get("choice") == "decline":
            game_state.pending_power = None
            return [
                {
                    "type": "power_declined",
                    "player_id": game_state.players[player_index].player_id,
                    "power_name": power_name,
                    "reason": "no_valid_target",
                }
            ]

        # For toxin, we need to access pending power data during execution
        # so don't clear it yet — let the execute method handle it
        if power_name == "toxin":
            return self._execute_toxin(game_state, player_index, choice)

        # For rescue placement follow-up (play now vs place on deck)
        if power_name == "rescue" and hasattr(pending, "rescue_card_id") and pending.rescue_card_id:
            rescue_card_id = pending.rescue_card_id
            value = choice.get("value", "")
            game_state.pending_power = None
            if value == "play_now":
                return self._execute_rescue(game_state, player_index, {"card_id": rescue_card_id, "play_immediately": True})
            else:
                return self._execute_rescue(game_state, player_index, {"card_id": rescue_card_id, "choice": "place_on_deck"})

        # Clear pending power before executing
        game_state.pending_power = None

        if power_name == "discard":
            return self._execute_discard(game_state, player_index, choice)
        elif power_name == "poison":
            return self._execute_poison(game_state, player_index, choice)
        elif power_name == "rescue":
            return self._execute_rescue(game_state, player_index, choice)
        elif power_name == "copy":
            return self._execute_copy(game_state, player_index, choice)
        elif power_name == "cycle":
            return self._execute_cycle(game_state, player_index, choice)
        elif power_name == "draw":
            return self._execute_draw(game_state, player_index, choice)
        elif power_name == "exchange":
            return self._execute_exchange(game_state, player_index, choice)
        elif power_name == "kill":
            return self._execute_kill(game_state, player_index, choice)
        elif power_name == "recycle":
            return self._execute_recycle(game_state, player_index, choice)
        elif power_name == "replay":
            return self._execute_replay(game_state, player_index, choice)
        elif power_name == "score":
            return self._execute_score(game_state, player_index, choice)
        elif power_name == "battle":
            return self._execute_battle(game_state, player_index, choice)
        elif power_name == "freeze":
            return self._execute_freeze(game_state, player_index, choice)
        elif power_name == "process":
            return self._execute_process(game_state, player_index, choice)
        elif power_name == "toxin":
            return self._execute_toxin(game_state, player_index, choice)
        elif power_name == "avalanche":
            return self._execute_avalanche(game_state, player_index, choice)
        elif power_name == "assimilate":
            return self._execute_assimilate(game_state, player_index, choice)
        elif power_name == "scan":
            return self._execute_scan(game_state, player_index, choice)
        elif power_name == "utilize":
            return self._execute_utilize(game_state, player_index, choice)

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

        If the top card of the target's draw deck has the Antidote power, the
        targeted player scores instead and may place their hand beneath their draw deck.

        Args:
            game_state: The current game state (modified in place).
            player_index: Index of the player activating Poison.
            choice: Dict with "target_player_index" specifying the target.

        Returns:
            List of events on success, or error tuple on failure.

        Requirements: 9.5, 11.1
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

        # Check for Antidote on the top card of target's draw deck (Requirement 11.1)
        top_card = target.draw_deck[0]
        top_card_name = (top_card.card_name or "").lower()
        top_card_power = (top_card.power_text or "").lower().strip()
        is_antidote = "antidote" in top_card_name or top_card_power == "antidote"
        if is_antidote:
            # Antidote triggers: targeted player scores instead
            target.draw_deck.pop(0)
            target.discard_pile.append(top_card)

            # Target scores the denomination (instead of Poison player)
            self._score_service.apply_immediate_score(
                game_state, target.player_id, top_card.denomination
            )

            # Allow target to place hand beneath draw deck
            target.draw_deck.extend(target.hand)
            target.hand.clear()

            return [
                {
                    "type": "power_activated",
                    "power_name": "poison",
                    "player_id": game_state.players[player_index].player_id,
                    "target_player_id": target.player_id,
                    "antidote_triggered": True,
                    "discarded_card_id": top_card.card_id,
                    "discarded_card_denomination": top_card.denomination,
                    "points_scored_by_target": top_card.denomination,
                }
            ]

        # Normal Poison: discard top card of target's draw deck
        target.draw_deck.pop(0)
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

        Look through your discard pile and recover a card. Place it face-down
        on top of your draw deck - or, if it has the proper number of tribbles
        (matches current sequence), you may play it now.

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

        # Check if the card matches the current sequence
        matches_sequence = (card.denomination == game_state.current_sequence)

        # If it matches and player hasn't yet chosen what to do, prompt them
        if matches_sequence and not play_immediately and choice.get("choice") != "place_on_deck":
            # Set up a second prompt: play now or place on draw deck
            game_state.pending_power = PendingPower(
                player_index=player_index,
                card=game_state.pending_power.card if game_state.pending_power else card,
                power_name="rescue",
                phase="choose_target",
            )
            # Store the rescued card id for the follow-up choice
            game_state.pending_power.rescue_card_id = card_id
            return [
                {
                    "type": "power_prompt",
                    "prompt_type": "choose_card_from_discard",
                    "player_id": player.player_id,
                    "power_name": "rescue_placement",
                    "options": [
                        {"value": "play_now", "label": "Play it now (matches sequence)"},
                        {"value": "place_on_deck", "label": "Place on top of draw deck"},
                    ],
                    "message": "This card matches the current sequence. Play it now or place on draw deck?",
                }
            ]

        # Remove from discard pile
        player.discard_pile.pop(card_index)

        if play_immediately or choice.get("value") == "play_now":
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

    def _execute_copy(
        self, game_state: GameState, player_index: int, choice: dict
    ) -> Union[List[dict], Tuple[str, str]]:
        """Execute the Copy power: apply game text of top card of another player's play pile.

        Cannot copy the Quadruple power.

        Args:
            game_state: The current game state (modified in place).
            player_index: Index of the player activating Copy.
            choice: Dict with "target_player_index" specifying whose play pile to copy from.

        Returns:
            List of events on success, or error tuple on failure.

        Requirements: 11.2, 12.10
        """
        target_index = choice.get("target_player_index")

        if target_index is None:
            return (
                "missing_target",
                "Copy power requires a target_player_index choice.",
            )

        if target_index == player_index:
            return ("invalid_target", "Cannot copy from your own play pile.")

        if target_index < 0 or target_index >= len(game_state.players):
            return ("invalid_target", "Target player index out of range.")

        target = game_state.players[target_index]

        if len(target.play_pile) == 0:
            return (
                "invalid_target",
                "Target player has no cards in their play pile.",
            )

        # Get the top card of the target's play pile
        top_card = target.play_pile[-1]
        copied_power = top_card.power_text.lower().strip()

        # Cannot copy Quadruple (Requirement 12.10)
        if copied_power == "quadruple":
            return (
                "cannot_copy_quadruple",
                "The Copy power cannot copy Quadruple.",
            )

        return [
            {
                "type": "power_activated",
                "power_name": "copy",
                "player_id": game_state.players[player_index].player_id,
                "target_player_id": target.player_id,
                "copied_card_id": top_card.card_id,
                "copied_power": copied_power,
            }
        ]

    def _execute_cycle(
        self, game_state: GameState, player_index: int, choice: dict
    ) -> Union[List[dict], Tuple[str, str]]:
        """Execute the Cycle power: place one hand card under draw deck, draw one from top.

        Args:
            game_state: The current game state (modified in place).
            player_index: Index of the player activating Cycle.
            choice: Dict with "card_id" specifying which card to place under draw deck.

        Returns:
            List of events on success, or error tuple on failure.

        Requirements: 11.3
        """
        player = game_state.players[player_index]
        card_id = choice.get("card_id")

        if card_id is None:
            return ("missing_card_id", "Cycle power requires a card_id choice.")

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

        # Place the chosen card under the draw deck
        player.hand.pop(card_index)
        player.draw_deck.append(card)

        # Draw one card from the top of the draw deck
        if len(player.draw_deck) > 0:
            drawn_card = player.draw_deck.pop(0)
            player.hand.append(drawn_card)
        else:
            drawn_card = None

        return [
            {
                "type": "power_activated",
                "power_name": "cycle",
                "player_id": player.player_id,
                "placed_card_id": card.card_id,
                "drawn_card_id": drawn_card.card_id if drawn_card else None,
            }
        ]

    def _execute_draw(
        self, game_state: GameState, player_index: int, choice: dict
    ) -> Union[List[dict], Tuple[str, str]]:
        """Execute the Draw power: chosen player draws one card from their draw deck.

        Args:
            game_state: The current game state (modified in place).
            player_index: Index of the player activating Draw.
            choice: Dict with "target_player_index" specifying who draws.

        Returns:
            List of events on success, or error tuple on failure.

        Requirements: 11.4
        """
        target_index = choice.get("target_player_index")

        if target_index is None:
            return (
                "missing_target",
                "Draw power requires a target_player_index choice.",
            )

        if target_index < 0 or target_index >= len(game_state.players):
            return ("invalid_target", "Target player index out of range.")

        target = game_state.players[target_index]

        if len(target.draw_deck) == 0:
            return (
                "invalid_target",
                "Target player has no cards in their draw deck.",
            )

        # Target draws one card from the top of their draw deck
        drawn_card = target.draw_deck.pop(0)
        target.hand.append(drawn_card)

        return [
            {
                "type": "power_activated",
                "power_name": "draw",
                "player_id": game_state.players[player_index].player_id,
                "target_player_id": target.player_id,
                "drawn_card_id": drawn_card.card_id,
            }
        ]

    def _execute_exchange(
        self, game_state: GameState, player_index: int, choice: dict
    ) -> Union[List[dict], Tuple[str, str]]:
        """Execute the Exchange power: discard one hand card, take one from discard pile.

        Args:
            game_state: The current game state (modified in place).
            player_index: Index of the player activating Exchange.
            choice: Dict with "card_id" (card to discard from hand) and
                "take_card_id" (card to take from discard pile).

        Returns:
            List of events on success, or error tuple on failure.

        Requirements: 11.5
        """
        player = game_state.players[player_index]
        card_id = choice.get("card_id")
        take_card_id = choice.get("take_card_id")

        if card_id is None:
            return ("missing_card_id", "Exchange power requires a card_id choice.")

        if take_card_id is None:
            return (
                "missing_take_card_id",
                "Exchange power requires a take_card_id choice.",
            )

        # Find the card to discard from hand
        discard_index = None
        discard_card = None
        for i, c in enumerate(player.hand):
            if c.card_id == card_id:
                discard_index = i
                discard_card = c
                break

        if discard_index is None:
            return ("card_not_in_hand", f"Card {card_id} is not in your hand.")

        # Find the card to take from discard pile
        take_index = None
        take_card = None
        for i, c in enumerate(player.discard_pile):
            if c.card_id == take_card_id:
                take_index = i
                take_card = c
                break

        if take_index is None:
            return (
                "card_not_in_discard",
                f"Card {take_card_id} is not in your discard pile.",
            )

        # Discard the hand card
        player.hand.pop(discard_index)
        player.discard_pile.append(discard_card)

        # Take the card from discard pile into hand
        player.discard_pile.pop(take_index)
        player.hand.append(take_card)

        return [
            {
                "type": "power_activated",
                "power_name": "exchange",
                "player_id": player.player_id,
                "discarded_card_id": discard_card.card_id,
                "taken_card_id": take_card.card_id,
            }
        ]

    def _execute_kill(
        self, game_state: GameState, player_index: int, choice: dict
    ) -> Union[List[dict], Tuple[str, str]]:
        """Execute the Kill power: discard top card of target's play pile.

        Args:
            game_state: The current game state (modified in place).
            player_index: Index of the player activating Kill.
            choice: Dict with "target_player_index" specifying the target.

        Returns:
            List of events on success, or error tuple on failure.

        Requirements: 11.6
        """
        target_index = choice.get("target_player_index")

        if target_index is None:
            return (
                "missing_target",
                "Kill power requires a target_player_index choice.",
            )

        if target_index < 0 or target_index >= len(game_state.players):
            return ("invalid_target", "Target player index out of range.")

        target = game_state.players[target_index]

        if len(target.play_pile) == 0:
            return (
                "invalid_target",
                "Target player has no cards in their play pile.",
            )

        # Discard the top card of the target's play pile
        top_card = target.play_pile.pop()
        target.discard_pile.append(top_card)

        return [
            {
                "type": "power_activated",
                "power_name": "kill",
                "player_id": game_state.players[player_index].player_id,
                "target_player_id": target.player_id,
                "killed_card_id": top_card.card_id,
                "killed_card_denomination": top_card.denomination,
            }
        ]

    def _execute_recycle(
        self, game_state: GameState, player_index: int, choice: dict
    ) -> Union[List[dict], Tuple[str, str]]:
        """Execute the Recycle power: shuffle target's discard pile into their draw deck.

        Args:
            game_state: The current game state (modified in place).
            player_index: Index of the player activating Recycle.
            choice: Dict with "target_player_index" specifying the target.

        Returns:
            List of events on success, or error tuple on failure.

        Requirements: 11.7
        """
        target_index = choice.get("target_player_index")

        if target_index is None:
            return (
                "missing_target",
                "Recycle power requires a target_player_index choice.",
            )

        if target_index < 0 or target_index >= len(game_state.players):
            return ("invalid_target", "Target player index out of range.")

        target = game_state.players[target_index]

        if len(target.discard_pile) == 0:
            return (
                "invalid_target",
                "Target player has no cards in their discard pile.",
            )

        # Move all discard pile cards into draw deck and shuffle
        target.draw_deck.extend(target.discard_pile)
        target.discard_pile.clear()
        random.shuffle(target.draw_deck)

        return [
            {
                "type": "power_activated",
                "power_name": "recycle",
                "player_id": game_state.players[player_index].player_id,
                "target_player_id": target.player_id,
            }
        ]

    def _execute_replay(
        self, game_state: GameState, player_index: int, choice: dict
    ) -> Union[List[dict], Tuple[str, str]]:
        """Execute the Replay power: search own play pile, play one card again.

        The chosen card is removed from the play pile and placed back on top
        of the play pile as if played from hand.

        Args:
            game_state: The current game state (modified in place).
            player_index: Index of the player activating Replay.
            choice: Dict with "card_id" specifying which card to replay.

        Returns:
            List of events on success, or error tuple on failure.

        Requirements: 11.8
        """
        player = game_state.players[player_index]
        card_id = choice.get("card_id")

        if card_id is None:
            return ("missing_card_id", "Replay power requires a card_id choice.")

        # Find the card in play pile
        card_index = None
        card = None
        for i, c in enumerate(player.play_pile):
            if c.card_id == card_id:
                card_index = i
                card = c
                break

        if card_index is None:
            return (
                "card_not_in_play_pile",
                f"Card {card_id} is not in your play pile.",
            )

        # Remove from play pile and place back on top (as if played from hand)
        player.play_pile.pop(card_index)
        player.play_pile.append(card)

        return [
            {
                "type": "power_activated",
                "power_name": "replay",
                "player_id": player.player_id,
                "replayed_card_id": card.card_id,
                "replayed_card_name": card.card_name,
                "replayed_card_denomination": card.denomination,
            }
        ]

    def _execute_score(
        self, game_state: GameState, player_index: int, choice: dict
    ) -> Union[List[dict], Tuple[str, str]]:
        """Execute the Score power: mark target player as Score target.

        If the target plays a card on their next turn, the Score activator
        gains points equal to that card's denomination.

        Args:
            game_state: The current game state (modified in place).
            player_index: Index of the player activating Score.
            choice: Dict with "target_player_index" specifying the target.

        Returns:
            List of events on success, or error tuple on failure.

        Requirements: 11.9
        """
        target_index = choice.get("target_player_index")

        if target_index is None:
            return (
                "missing_target",
                "Score power requires a target_player_index choice.",
            )

        if target_index == player_index:
            return ("invalid_target", "Cannot target yourself with Score.")

        if target_index < 0 or target_index >= len(game_state.players):
            return ("invalid_target", "Target player index out of range.")

        target = game_state.players[target_index]
        player = game_state.players[player_index]

        # Mark the target with the Score power activator's player_id
        target.score_target_by = player.player_id

        return [
            {
                "type": "power_activated",
                "power_name": "score",
                "player_id": player.player_id,
                "target_player_id": target.player_id,
            }
        ]

    # --- Expansion 4: No Tribble at All powers ---

    def _execute_battle(
        self, game_state: GameState, player_index: int, choice: dict
    ) -> Union[List[dict], Tuple[str, str]]:
        """Execute the Battle power: reveal top 3 of both players' draw decks.

        Higher total denomination wins all 6 cards under their play pile.
        Loser discards their 3 revealed cards.

        Args:
            game_state: The current game state (modified in place).
            player_index: Index of the player activating Battle.
            choice: Dict with "target_player_index" specifying the opponent.

        Returns:
            List of events on success, or error tuple on failure.

        Requirements: 12.4
        """
        target_index = choice.get("target_player_index")

        if target_index is None:
            return (
                "missing_target",
                "Battle power requires a target_player_index choice.",
            )

        if target_index == player_index:
            return ("invalid_target", "Cannot battle yourself.")

        if target_index < 0 or target_index >= len(game_state.players):
            return ("invalid_target", "Target player index out of range.")

        player = game_state.players[player_index]
        target = game_state.players[target_index]

        if len(player.draw_deck) < 3:
            return (
                "insufficient_cards",
                "You need at least 3 cards in your draw deck to battle.",
            )

        if len(target.draw_deck) < 3:
            return (
                "invalid_target",
                "Target needs at least 3 cards in their draw deck to battle.",
            )

        # Reveal top 3 of each player's draw deck
        player_revealed = [player.draw_deck.pop(0) for _ in range(3)]
        target_revealed = [target.draw_deck.pop(0) for _ in range(3)]

        player_total = sum(c.denomination for c in player_revealed)
        target_total = sum(c.denomination for c in target_revealed)

        all_six = player_revealed + target_revealed

        if player_total >= target_total:
            # Active player wins (ties go to active player)
            # Winner places all 6 under their play pile
            player.play_pile = all_six + player.play_pile
            # Loser discards their 3
            target.discard_pile.extend(target_revealed)
            winner_id = player.player_id
            loser_id = target.player_id
        else:
            # Target wins
            target.play_pile = all_six + target.play_pile
            # Loser (active player) discards their 3
            player.discard_pile.extend(player_revealed)
            winner_id = target.player_id
            loser_id = player.player_id

        return [
            {
                "type": "power_activated",
                "power_name": "battle",
                "player_id": player.player_id,
                "target_player_id": target.player_id,
                "player_revealed": [c.card_id for c in player_revealed],
                "target_revealed": [c.card_id for c in target_revealed],
                "player_total": player_total,
                "target_total": target_total,
                "winner_player_id": winner_id,
                "loser_player_id": loser_id,
            }
        ]

    def _execute_evolve(
        self, game_state: GameState, player_index: int
    ) -> List[dict]:
        """Execute the Evolve power: count hand, move hand to discard, draw same count.

        Args:
            game_state: The current game state (modified in place).
            player_index: Index of the player activating Evolve.

        Returns:
            List of game events.

        Requirements: 12.5
        """
        player = game_state.players[player_index]

        hand_count = len(player.hand)

        # Move all hand cards to discard pile
        player.discard_pile.extend(player.hand)
        player.hand.clear()

        # Draw same count from deck
        cards_drawn = []
        for _ in range(hand_count):
            if len(player.draw_deck) > 0:
                drawn = player.draw_deck.pop(0)
                player.hand.append(drawn)
                cards_drawn.append(drawn)

        return [
            {
                "type": "power_activated",
                "power_name": "evolve",
                "player_id": player.player_id,
                "cards_discarded": hand_count,
                "cards_drawn": len(cards_drawn),
            }
        ]

    def _execute_freeze(
        self, game_state: GameState, player_index: int, choice: dict
    ) -> Union[List[dict], Tuple[str, str]]:
        """Execute the Freeze power: record named power as frozen.

        The named power is frozen until the end of the active player's next turn.
        Any attempt to play a card with that power during the freeze period is rejected.

        Args:
            game_state: The current game state (modified in place).
            player_index: Index of the player activating Freeze.
            choice: Dict with "power_name" specifying which power to freeze.

        Returns:
            List of events on success, or error tuple on failure.

        Requirements: 12.6
        """
        frozen_power = choice.get("power_name")

        if frozen_power is None:
            return (
                "missing_power_name",
                "Freeze power requires a power_name choice.",
            )

        frozen_power = frozen_power.lower().strip()

        if frozen_power not in ACTIVATABLE_POWERS or frozen_power == "freeze":
            return (
                "invalid_power_name",
                f"Cannot freeze power: {frozen_power}.",
            )

        # Record the frozen power — expires at end of active player's next turn
        # We track this as the player_index who froze it (to know when their next turn ends)
        game_state.frozen_powers[frozen_power] = player_index

        return [
            {
                "type": "power_activated",
                "power_name": "freeze",
                "player_id": game_state.players[player_index].player_id,
                "frozen_power": frozen_power,
            }
        ]

    def is_power_frozen(self, game_state: GameState, power_name: str) -> bool:
        """Check if a power is currently frozen.

        Args:
            game_state: The current game state.
            power_name: The power to check.

        Returns:
            True if the power is frozen and cannot be played.

        Requirements: 12.6
        """
        return power_name.lower().strip() in game_state.frozen_powers

    def clear_expired_freezes(self, game_state: GameState, player_index: int) -> List[dict]:
        """Clear frozen powers that have expired (end of freezing player's next turn).

        Should be called at the end of each player's turn.

        Args:
            game_state: The current game state (modified in place).
            player_index: Index of the player whose turn just ended.

        Returns:
            List of events for any cleared freezes.

        Requirements: 12.6
        """
        events = []
        expired = []
        for power_name, freezer_index in game_state.frozen_powers.items():
            if freezer_index == player_index:
                expired.append(power_name)

        for power_name in expired:
            del game_state.frozen_powers[power_name]
            events.append({
                "type": "freeze_expired",
                "power_name": power_name,
            })

        return events

    def _execute_mutate(
        self, game_state: GameState, player_index: int
    ) -> List[dict]:
        """Execute the Mutate power: count play pile, shuffle into deck, move same count back.

        Args:
            game_state: The current game state (modified in place).
            player_index: Index of the player activating Mutate.

        Returns:
            List of game events.

        Requirements: 12.7
        """
        player = game_state.players[player_index]

        pile_count = len(player.play_pile)

        # Shuffle play pile into draw deck
        player.draw_deck.extend(player.play_pile)
        player.play_pile.clear()
        random.shuffle(player.draw_deck)

        # Move same count from top of deck to play pile
        cards_moved = []
        for _ in range(pile_count):
            if len(player.draw_deck) > 0:
                card = player.draw_deck.pop(0)
                player.play_pile.append(card)
                cards_moved.append(card)

        return [
            {
                "type": "power_activated",
                "power_name": "mutate",
                "player_id": player.player_id,
                "pile_count": pile_count,
                "cards_moved": len(cards_moved),
            }
        ]

    def _execute_process(
        self, game_state: GameState, player_index: int, choice: dict
    ) -> Union[List[dict], Tuple[str, str]]:
        """Execute the Process power phase 2: place 2 chosen cards under draw deck.

        The 3 cards were already drawn during the prompt phase.
        Now the player chooses 2 cards from hand to place under draw deck.

        Args:
            game_state: The current game state (modified in place).
            player_index: Index of the player activating Process.
            choice: Dict with "card_ids" (list of 2 card IDs to place under deck).

        Returns:
            List of events on success, or error tuple on failure.

        Requirements: 12.8
        """
        player = game_state.players[player_index]
        card_ids = choice.get("card_ids")

        if card_ids is None or len(card_ids) != 2:
            return (
                "invalid_choice",
                "Process power requires exactly 2 card_ids to place under draw deck.",
            )

        # Find and remove the 2 cards from hand
        cards_to_place = []
        for cid in card_ids:
            found = False
            for i, c in enumerate(player.hand):
                if c.card_id == cid:
                    cards_to_place.append(player.hand.pop(i))
                    found = True
                    break
            if not found:
                return (
                    "card_not_in_hand",
                    f"Card {cid} is not in your hand.",
                )

        # Place the 2 cards under the draw deck
        player.draw_deck.extend(cards_to_place)

        return [
            {
                "type": "power_activated",
                "power_name": "process",
                "player_id": player.player_id,
                "cards_placed_under_deck": [c.card_id for c in cards_to_place],
            }
        ]

    def _execute_toxin(
        self, game_state: GameState, player_index: int, choice: dict
    ) -> Union[List[dict], Tuple[str, str]]:
        """Execute the Toxin power phase 2: choose one revealed card to score.

        All revealed cards go to their owners' hands.

        Args:
            game_state: The current game state (modified in place).
            player_index: Index of the player activating Toxin.
            choice: Dict with "card_id" specifying which revealed card to score.

        Returns:
            List of events on success, or error tuple on failure.

        Requirements: 12.13
        """
        player = game_state.players[player_index]
        chosen_card_id = choice.get("card_id")

        if chosen_card_id is None:
            return (
                "missing_card_id",
                "Toxin power requires a card_id choice.",
            )

        # Get the revealed cards from pending power state
        pending = game_state.pending_power
        if pending is None:
            # If pending was already cleared, check for toxin_revealed attribute
            return ("no_pending_power", "No pending Toxin resolution.")

        revealed_cards = getattr(pending, "toxin_revealed", None)
        if revealed_cards is None:
            return ("no_revealed_cards", "No revealed cards for Toxin resolution.")

        # Clear pending power
        game_state.pending_power = None

        # Find the chosen card among revealed
        chosen_card = None
        chosen_owner_index = None
        for owner_idx, card in revealed_cards:
            if card.card_id == chosen_card_id:
                chosen_card = card
                chosen_owner_index = owner_idx
                break

        if chosen_card is None:
            return (
                "invalid_card_id",
                f"Card {chosen_card_id} is not among the revealed cards.",
            )

        # Score the chosen card's denomination for the active player
        self._score_service.apply_immediate_score(
            game_state, player.player_id, chosen_card.denomination
        )

        # All revealed cards go to their owners' hands
        for owner_idx, card in revealed_cards:
            game_state.players[owner_idx].hand.append(card)

        return [
            {
                "type": "power_activated",
                "power_name": "toxin",
                "player_id": player.player_id,
                "scored_card_id": chosen_card.card_id,
                "scored_denomination": chosen_card.denomination,
                "revealed_count": len(revealed_cards),
            }
        ]

    # --- Expansion 5: Trials and Tribble-ations powers ---

    def _execute_avalanche(
        self, game_state: GameState, player_index: int, choice: dict
    ) -> Union[List[dict], Tuple[str, str]]:
        """Execute the Avalanche power phase 2: active player discards one additional card.

        The all-players discard already happened during the prompt phase.
        Now the active player chooses one additional card to discard.

        Args:
            game_state: The current game state (modified in place).
            player_index: Index of the player activating Avalanche.
            choice: Dict with "card_id" specifying which additional card to discard.

        Returns:
            List of events on success, or error tuple on failure.

        Requirements: 13.1
        """
        player = game_state.players[player_index]
        card_id = choice.get("card_id")

        if card_id is None:
            return ("missing_card_id", "Avalanche power requires a card_id choice.")

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

        # Discard the additional card
        player.hand.pop(card_index)
        player.discard_pile.append(card)

        return [
            {
                "type": "power_activated",
                "power_name": "avalanche",
                "player_id": player.player_id,
                "effect": "all_discarded_plus_additional",
                "additional_discarded_card_id": card.card_id,
            }
        ]

    def _execute_famine(
        self, game_state: GameState, player_index: int
    ) -> List[dict]:
        """Execute the Famine power: set next sequence denomination to 1.

        Args:
            game_state: The current game state (modified in place).
            player_index: Index of the player activating Famine.

        Returns:
            List of game events.

        Requirements: 13.2
        """
        game_state.current_sequence = 1

        return [
            {
                "type": "power_activated",
                "power_name": "famine",
                "player_id": game_state.players[player_index].player_id,
                "effect": "sequence_reset_to_1",
                "new_sequence": 1,
            }
        ]

    def _execute_stampede(
        self, game_state: GameState, player_index: int
    ) -> List[dict]:
        """Execute the Stampede power: all players may play one card of current sequence denomination.

        Each player in turn order (starting from the player after the active player)
        may play one card matching the current sequence denomination. Only the active
        player's card power may activate.

        For simplicity, this auto-plays the first matching card found in each player's
        hand. The active player's card is the one whose power could activate.

        Args:
            game_state: The current game state (modified in place).
            player_index: Index of the player activating Stampede.

        Returns:
            List of game events.

        Requirements: 13.3
        """
        current_denom = game_state.current_sequence
        player_count = len(game_state.players)
        events = []
        active_player_card_power = None

        # Process all players in turn order starting from the player after active
        order = []
        idx = player_index
        for _ in range(player_count):
            idx = (idx + game_state.direction) % player_count
            if idx == player_index:
                break
            order.append(idx)
        # Active player goes last
        order.append(player_index)

        for pidx in order:
            p = game_state.players[pidx]
            if p.is_decked:
                continue

            # Find first card matching current sequence denomination
            matching_card = None
            matching_index = None
            for i, c in enumerate(p.hand):
                if c.denomination == current_denom:
                    matching_card = c
                    matching_index = i
                    break

            if matching_card is not None:
                # Play the card: move from hand to play pile
                p.hand.pop(matching_index)
                p.play_pile.append(matching_card)

                card_event = {
                    "type": "stampede_card_played",
                    "player_id": p.player_id,
                    "card_id": matching_card.card_id,
                    "card_name": matching_card.card_name,
                    "denomination": matching_card.denomination,
                    "power": matching_card.power_text,
                }
                events.append(card_event)

                # Only the active player's card power may activate
                if pidx == player_index:
                    active_player_card_power = matching_card.power_text.lower().strip()

        # Advance the sequence past the current denomination
        sequence_cycle = [1, 10, 100, 1000, 10000, 100000]
        if current_denom in sequence_cycle:
            idx = sequence_cycle.index(current_denom)
            game_state.current_sequence = sequence_cycle[(idx + 1) % len(sequence_cycle)]

        # Update last_played_denomination
        game_state.last_played_denomination = current_denom

        events.insert(0, {
            "type": "power_activated",
            "power_name": "stampede",
            "player_id": game_state.players[player_index].player_id,
            "effect": "stampede_resolved",
            "cards_played": len([e for e in events if e.get("type") == "stampede_card_played"]),
            "active_player_card_power": active_player_card_power,
            "new_sequence": game_state.current_sequence,
        })

        return events

    # --- Expansion 6: Nothing But Tribble powers ---

    def _execute_convert(
        self, game_state: GameState, player_index: int
    ) -> List[dict]:
        """Execute the Convert power: place Convert card under draw deck, move top of deck to play pile.

        The Convert card (which was just played to the play pile) is moved from
        the play pile to under the draw deck, then the top of the draw deck is
        moved to the play pile.

        Args:
            game_state: The current game state (modified in place).
            player_index: Index of the player activating Convert.

        Returns:
            List of game events.

        Requirements: 14.3
        """
        player = game_state.players[player_index]

        # Find the Convert card in the play pile (it's the most recently played card, i.e. last)
        convert_card = None
        convert_index = None
        for i in range(len(player.play_pile) - 1, -1, -1):
            if player.play_pile[i].power_text.lower().strip() == "convert":
                convert_card = player.play_pile[i]
                convert_index = i
                break

        if convert_card is None:
            # Shouldn't happen, but handle gracefully
            return [
                {
                    "type": "power_activated",
                    "power_name": "convert",
                    "player_id": player.player_id,
                    "effect": "no_convert_card_found",
                }
            ]

        # Move Convert card from play pile to under the draw deck
        player.play_pile.pop(convert_index)
        player.draw_deck.append(convert_card)

        # Move top of draw deck to play pile
        if len(player.draw_deck) > 0:
            top_card = player.draw_deck.pop(0)
            player.play_pile.append(top_card)
            return [
                {
                    "type": "power_activated",
                    "power_name": "convert",
                    "player_id": player.player_id,
                    "convert_card_id": convert_card.card_id,
                    "new_play_pile_card_id": top_card.card_id,
                    "new_play_pile_card_denomination": top_card.denomination,
                }
            ]
        else:
            return [
                {
                    "type": "power_activated",
                    "power_name": "convert",
                    "player_id": player.player_id,
                    "convert_card_id": convert_card.card_id,
                    "effect": "no_card_to_draw",
                }
            ]

    def _execute_masaka(
        self, game_state: GameState, player_index: int
    ) -> List[dict]:
        """Execute the Masaka power: all players place hands under draw decks, deal 3 to each.

        Args:
            game_state: The current game state (modified in place).
            player_index: Index of the player activating Masaka.

        Returns:
            List of game events.

        Requirements: 14.5
        """
        events = []

        # All players place their hands under their draw decks
        for player in game_state.players:
            if player.is_decked:
                continue
            if len(player.hand) > 0:
                player.draw_deck.extend(player.hand)
                player.hand.clear()

        # Deal 3 cards to each non-decked player
        for player in game_state.players:
            if player.is_decked:
                continue
            cards_dealt = 0
            for _ in range(3):
                if len(player.draw_deck) > 0:
                    card = player.draw_deck.pop(0)
                    player.hand.append(card)
                    cards_dealt += 1
            events.append({
                "type": "masaka_cards_dealt",
                "player_id": player.player_id,
                "cards_dealt": cards_dealt,
            })

        events.insert(0, {
            "type": "power_activated",
            "power_name": "masaka",
            "player_id": game_state.players[player_index].player_id,
            "effect": "hands_reset_and_dealt",
        })

        return events

    def _execute_assimilate(
        self, game_state: GameState, player_index: int, choice: dict
    ) -> Union[List[dict], Tuple[str, str]]:
        """Execute the Assimilate power: move top of target's draw deck to active player's play pile.

        The card is recorded as borrowed and will be returned at round end.

        Args:
            game_state: The current game state (modified in place).
            player_index: Index of the player activating Assimilate.
            choice: Dict with "target_player_index" specifying the target.

        Returns:
            List of events on success, or error tuple on failure.

        Requirements: 14.2
        """
        target_index = choice.get("target_player_index")

        if target_index is None:
            return (
                "missing_target",
                "Assimilate power requires a target_player_index choice.",
            )

        if target_index == player_index:
            return ("invalid_target", "Cannot target yourself with Assimilate.")

        if target_index < 0 or target_index >= len(game_state.players):
            return ("invalid_target", "Target player index out of range.")

        target = game_state.players[target_index]

        if len(target.draw_deck) == 0:
            return (
                "invalid_target",
                "Target player has no cards in their draw deck.",
            )

        player = game_state.players[player_index]

        # Move top of target's draw deck to active player's play pile
        borrowed_card = target.draw_deck.pop(0)
        player.play_pile.append(borrowed_card)

        # Record as borrowed (card, original_owner_id)
        player.borrowed_cards.append((borrowed_card, target.player_id))

        return [
            {
                "type": "power_activated",
                "power_name": "assimilate",
                "player_id": player.player_id,
                "target_player_id": target.player_id,
                "borrowed_card_id": borrowed_card.card_id,
                "borrowed_card_denomination": borrowed_card.denomination,
            }
        ]

    def _execute_scan(
        self, game_state: GameState, player_index: int, choice: dict
    ) -> Union[List[dict], Tuple[str, str]]:
        """Execute the Scan power phase 2: reorder revealed cards and place on top or bottom.

        Args:
            game_state: The current game state (modified in place).
            player_index: Index of the player activating Scan.
            choice: Dict with "card_ids" (ordered list of card IDs) and
                "placement" ("top" or "bottom").

        Returns:
            List of events on success, or error tuple on failure.

        Requirements: 14.6
        """
        player = game_state.players[player_index]
        card_ids = choice.get("card_ids")
        placement = choice.get("placement", "top")

        if card_ids is None:
            return ("missing_card_ids", "Scan power requires card_ids in the chosen order.")

        # Validate the card_ids match the top cards of the draw deck
        # The cards were revealed but not removed, so they should still be at the top
        num_revealed = min(3, len(player.draw_deck))
        top_cards = player.draw_deck[:num_revealed]
        top_card_ids = {c.card_id for c in top_cards}

        if set(card_ids) != top_card_ids:
            return (
                "invalid_card_ids",
                "Card IDs do not match the revealed cards.",
            )

        if len(card_ids) != num_revealed:
            return (
                "invalid_card_ids",
                f"Expected {num_revealed} card IDs, got {len(card_ids)}.",
            )

        # Remove the top cards from the draw deck
        removed_cards = player.draw_deck[:num_revealed]
        player.draw_deck = player.draw_deck[num_revealed:]

        # Reorder according to the provided card_ids order
        card_map = {c.card_id: c for c in removed_cards}
        reordered = [card_map[cid] for cid in card_ids]

        # Place on top or bottom
        if placement == "bottom":
            player.draw_deck.extend(reordered)
        else:
            # Place on top (in order, so first in list is top of deck)
            player.draw_deck = reordered + player.draw_deck

        return [
            {
                "type": "power_activated",
                "power_name": "scan",
                "player_id": player.player_id,
                "placement": placement,
                "card_count": len(reordered),
            }
        ]

    def _execute_utilize(
        self, game_state: GameState, player_index: int, choice: dict
    ) -> Union[List[dict], Tuple[str, str]]:
        """Execute the Utilize power: opponent randomly places one hand card on their play pile.

        Active player scores that card's denomination.

        Args:
            game_state: The current game state (modified in place).
            player_index: Index of the player activating Utilize.
            choice: Dict with "target_player_index" specifying the target.

        Returns:
            List of events on success, or error tuple on failure.

        Requirements: 14.7
        """
        target_index = choice.get("target_player_index")

        if target_index is None:
            return (
                "missing_target",
                "Utilize power requires a target_player_index choice.",
            )

        if target_index == player_index:
            return ("invalid_target", "Cannot target yourself with Utilize.")

        if target_index < 0 or target_index >= len(game_state.players):
            return ("invalid_target", "Target player index out of range.")

        target = game_state.players[target_index]

        if len(target.hand) < 2:
            return (
                "invalid_target",
                "Target player must have at least 2 cards in hand.",
            )

        player = game_state.players[player_index]

        # Randomly select one card from target's hand
        random_index = random.randint(0, len(target.hand) - 1)
        utilized_card = target.hand.pop(random_index)

        # Place it on target's play pile
        target.play_pile.append(utilized_card)

        # Active player scores that card's denomination
        self._score_service.apply_immediate_score(
            game_state, player.player_id, utilized_card.denomination
        )

        return [
            {
                "type": "power_activated",
                "power_name": "utilize",
                "player_id": player.player_id,
                "target_player_id": target.player_id,
                "utilized_card_id": utilized_card.card_id,
                "utilized_card_denomination": utilized_card.denomination,
                "points_scored": utilized_card.denomination,
            }
        ]
