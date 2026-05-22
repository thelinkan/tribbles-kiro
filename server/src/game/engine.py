"""Game engine — core game logic, rule enforcement, turn management, power resolution.

This module implements the Game_Engine class which is responsible for initialising
games, processing player actions, and providing visible state to players and spectators.
"""

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Union

from models import CardInstance, GameState, PendingDraw, PlayerState
from game.powers.resolver import PowerResolver


@dataclass
class PlayerSetup:
    """Input data for a single player joining a game.

    Attributes:
        player_id: Unique identifier for the player.
        username: Display name of the player.
        is_computer: True if this is a computer-controlled player.
        deck_cards: The full list of CardInstance objects forming the player's deck.
    """

    player_id: int
    username: str
    is_computer: bool
    deck_cards: List[CardInstance] = field(default_factory=list)


@dataclass
class GameSession:
    """Input data for initialising a new game.

    Attributes:
        game_id: Unique identifier for this game session.
        players: List of player setup data including their decks.
        spectators: List of player IDs who are spectating.
        reconnection_timeout: Seconds to wait before activating AI substitute.
    """

    game_id: str
    players: List[PlayerSetup] = field(default_factory=list)
    spectators: List[int] = field(default_factory=list)
    reconnection_timeout: int = 30


class GameEngine:
    """Core game logic engine.

    Responsible for initialising games, processing player actions,
    enforcing rules, and providing visible state.
    """

    CARDS_TO_DEAL = 7
    SEQUENCE_CYCLE = [1, 10, 100, 1000, 10000, 100000]

    def __init__(self):
        """Initialise the game engine."""
        self._games: Dict[str, GameState] = {}
        self._power_resolver = PowerResolver()

    def _advance_sequence(self, current: int) -> int:
        """Advance the sequence to the next denomination in the cycle.

        The cycle is: 1 → 10 → 100 → 1000 → 10000 → 100000 → 1.

        Args:
            current: The current sequence denomination.

        Returns:
            The next denomination in the cycle.
        """
        idx = self.SEQUENCE_CYCLE.index(current)
        return self.SEQUENCE_CYCLE[(idx + 1) % len(self.SEQUENCE_CYCLE)]

    def _advance_turn(self, state: GameState) -> None:
        """Advance the turn to the next player in the current direction.

        Skips over decked players. If all players are decked (shouldn't happen
        in normal play due to last-player-standing logic), wraps around without
        infinite loop by limiting iterations to player count.

        Args:
            state: The current game state (modified in place).
        """
        player_count = len(state.players)
        for _ in range(player_count):
            state.current_player_index = (
                state.current_player_index + state.direction
            ) % player_count
            if not state.players[state.current_player_index].is_decked:
                break

    def can_score_from(self, player: PlayerState) -> bool:
        """Check if points can be scored from a player.

        A decked player cannot have points scored from them, except via
        the Antidote power (handled separately in power resolution).

        Args:
            player: The player to check.

        Returns:
            True if points can be scored from this player.

        Requirements: 7.2
        """
        return not player.is_decked

    def can_score_to(self, player: PlayerState) -> bool:
        """Check if a player can receive/gain score points.

        A decked player cannot score points, except via the Antidote power
        (handled separately in power resolution).

        Args:
            player: The player to check.

        Returns:
            True if this player can score points.

        Requirements: 7.2
        """
        return not player.is_decked

    def _check_last_player_standing(self, state: GameState) -> List[dict]:
        """Check if only one non-decked player remains and trigger go-out.

        When all players except one are decked, the last remaining non-decked
        player automatically goes out by moving their entire hand to their
        play pile.

        Args:
            state: The current game state.

        Returns:
            List of game events if the last player goes out, empty list otherwise.

        Requirements: 7.5
        """
        non_decked_players = [
            p for p in state.players if not p.is_decked
        ]

        if len(non_decked_players) == 1:
            last_player = non_decked_players[0]
            # Only trigger if the player hasn't already gone out and has cards in hand
            if not last_player.has_gone_out and len(last_player.hand) > 0:
                # Move entire hand to play pile
                last_player.play_pile.extend(last_player.hand)
                last_player.hand.clear()
                last_player.has_gone_out = True

                return [
                    {
                        "type": "player_went_out",
                        "player_id": last_player.player_id,
                        "reason": "last_player_standing",
                    }
                ]

        return []

    def _is_clone_card(self, card: CardInstance) -> bool:
        """Check if a card has the Clone power (including compound powers with Clone).

        Checks both the card_name (e.g., "Tribble - Clone") and the power_text.

        Args:
            card: The card to check.

        Returns:
            True if the card has Clone as its power or as part of a compound power.
        """
        card_name = (card.card_name or "").lower()
        if "clone" in card_name:
            return True
        power = (card.power_text or "").lower()
        return "clone" in power

    def _is_valid_play(self, card: CardInstance, state: GameState) -> bool:
        """Check if a card is a valid play given the current game state.

        A card is valid if:
        - Its denomination matches the current sequence, OR
        - The sequence is broken and it's a 1-denomination card, OR
        - The sequence is broken and it has the Advance power (plays in place of 1), OR
        - It's a Clone card and its denomination matches the last_played_denomination.

        Args:
            card: The card to validate.
            state: The current game state.

        Returns:
            True if the card can be legally played.
        """
        # Normal play: denomination matches current sequence
        if card.denomination == state.current_sequence:
            return True

        # Sequence break: allow 1-denomination card
        if state.sequence_broken and card.denomination == 1:
            return True

        # Sequence break: allow Advance power card (plays in place of 1-denomination)
        if state.sequence_broken and self._is_advance_card(card):
            return True

        # Clone: denomination matches last_played_denomination
        if (
            self._is_clone_card(card)
            and state.last_played_denomination is not None
            and card.denomination == state.last_played_denomination
        ):
            return True

        return False

    def _is_advance_card(self, card: CardInstance) -> bool:
        """Check if a card has the Advance power.

        Checks both the card_name (e.g., "Tribble - Advance") and the power_text.

        Args:
            card: The card to check.

        Returns:
            True if the card has Advance as its power or as part of a compound power.

        Requirements: 14.1
        """
        card_name = (card.card_name or "").lower()
        if "advance" in card_name:
            return True
        power = (card.power_text or "").lower()
        return "advance" in power

    def process_action(
        self, game_id: str, player_id: int, action: dict
    ) -> Union[List[dict], Tuple[str, str]]:
        """Process a player action within a game.

        Handles play_card, draw_card, and accept_draw actions.
        Rejects any actions from spectator player IDs.

        Args:
            game_id: The game session ID.
            player_id: The player performing the action.
            action: A dict with 'type' and optional additional fields.
                - {"type": "play_card", "card_id": int, "activate_power": bool}
                - {"type": "draw_card"}
                - {"type": "accept_draw"}

        Returns:
            On success: A list of game event dicts describing what happened.
            On error: A tuple of (error_code, error_message).

        Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9, 22.7
        """
        # Validate game exists
        state = self._games.get(game_id)
        if state is None:
            return ("game_not_found", f"Game '{game_id}' not found.")

        # Reject actions from spectators (Requirement 22.7)
        if player_id in state.spectators:
            return ("spectator_cannot_act", "Spectators cannot perform game actions.")

        # Validate game is active
        if state.game_status != "active":
            return ("game_not_active", "Game is not in active state.")

        # Find the player
        player_index = None
        for i, p in enumerate(state.players):
            if p.player_id == player_id:
                player_index = i
                break

        if player_index is None:
            return ("player_not_found", f"Player {player_id} not in this game.")

        action_type = action.get("type")

        # Handle power_choice action (response to a power prompt)
        if action_type == "power_choice":
            return self._handle_power_choice(state, player_index, action)

        # If there's a pending power for this player, they must resolve it first
        if state.pending_power is not None and state.pending_power.player_index == player_index:
            if action_type != "power_choice":
                return (
                    "pending_power",
                    "You must resolve the pending power prompt before taking another action.",
                )

        # Handle accept_draw action (can come from the player with a pending draw)
        if action_type == "accept_draw":
            return self._handle_accept_draw(state, player_index)

        # For play_card during a pending draw, the player can play the drawn card
        if state.pending_draw is not None and state.pending_draw.player_id == player_id:
            if action_type == "play_card":
                return self._handle_play_drawn_card(state, player_index, action)
            else:
                return (
                    "pending_draw",
                    "You must play the drawn card or accept it (accept_draw).",
                )

        # Validate it's this player's turn
        if player_index != state.current_player_index:
            return ("not_your_turn", "It is not your turn.")

        if action_type == "play_card":
            return self._handle_play_card(state, player_index, action)
        elif action_type == "draw_card":
            return self._handle_draw_card(state, player_index)
        else:
            return ("invalid_action", f"Unknown action type: {action_type}")

    def _handle_play_card(
        self, state: GameState, player_index: int, action: dict
    ) -> Union[List[dict], Tuple[str, str]]:
        """Handle a play_card action.

        Validates the card is in hand and is a valid play, then moves it to the
        play pile, advances the sequence, tracks last_played_denomination, and
        advances the turn.

        Args:
            state: The current game state.
            player_index: Index of the player in state.players.
            action: The action dict with card_id.

        Returns:
            List of game events on success, or error tuple on failure.
        """
        player = state.players[player_index]
        card_id = action.get("card_id")

        if card_id is None:
            return ("missing_card_id", "play_card action requires a card_id.")

        # Find the card in the player's hand
        card = None
        card_index = None
        for i, c in enumerate(player.hand):
            if c.card_id == card_id:
                card = c
                card_index = i
                break

        if card is None:
            return ("card_not_in_hand", f"Card {card_id} is not in your hand.")

        # Validate the play
        if not self._is_valid_play(card, state):
            return (
                "invalid_play",
                f"Card with denomination {card.denomination} cannot be played. "
                f"Current sequence is {state.current_sequence}.",
            )

        # Move card from hand to play pile
        player.hand.pop(card_index)
        player.play_pile.append(card)

        # Track last_played_denomination (Requirement 6.9)
        state.last_played_denomination = card.denomination

        # Determine new sequence
        # If a 1-denomination card or Advance card was played after a sequence break, reset sequence to 10
        if state.sequence_broken and (card.denomination == 1 or self._is_advance_card(card)):
            state.current_sequence = 10
        else:
            state.current_sequence = self._advance_sequence(card.denomination)

        # Clear sequence_broken flag after a successful play
        state.sequence_broken = False

        # Build events
        events = [
            {
                "type": "card_played",
                "player_id": player.player_id,
                "card_id": card.card_id,
                "card_name": card.card_name,
                "denomination": card.denomination,
                "power": card.power_text,
                "new_sequence": state.current_sequence,
            }
        ]

        # Check if the card has an activatable power (Requirement 9.1)
        activate_power = action.get("activate_power", True)
        if activate_power:
            power_prompt_events = self._power_resolver.create_power_prompt(
                state, player_index, card
            )
            if power_prompt_events is not None:
                # Power prompt created — do NOT advance turn yet.
                # The turn will advance after the power is resolved or declined.
                events.extend(power_prompt_events)
                return events

        # No power to activate — advance turn to next player
        self._advance_turn(state)
        events.append(
            {
                "type": "turn_advanced",
                "next_player_id": state.players[state.current_player_index].player_id,
            }
        )

        return events

    def _handle_draw_card(
        self, state: GameState, player_index: int
    ) -> Union[List[dict], Tuple[str, str]]:
        """Handle a draw_card action.

        Draws the top card from the player's draw deck. If the deck is empty,
        marks the player as decked. If the drawn card matches the current sequence,
        creates a pending draw choice. Otherwise, records a pass.

        Args:
            state: The current game state.
            player_index: Index of the player in state.players.

        Returns:
            List of game events on success, or error tuple on failure.
        """
        player = state.players[player_index]

        # Check if draw deck is empty (Requirement 6.8)
        if len(player.draw_deck) == 0:
            player.is_decked = True
            # Move all hand cards to discard pile
            player.discard_pile.extend(player.hand)
            player.hand.clear()

            events = [
                {
                    "type": "player_decked",
                    "player_id": player.player_id,
                }
            ]

            # Check if last player standing should go out (Requirement 7.5)
            last_standing_events = self._check_last_player_standing(state)
            events.extend(last_standing_events)

            # Advance turn (skips decked players)
            self._advance_turn(state)
            events.append(
                {
                    "type": "turn_advanced",
                    "next_player_id": state.players[
                        state.current_player_index
                    ].player_id,
                }
            )

            return events

        # Draw the top card (index 0 is top of deck)
        drawn_card = player.draw_deck.pop(0)
        player.hand.append(drawn_card)

        events = [
            {
                "type": "card_drawn",
                "player_id": player.player_id,
                "card_id": drawn_card.card_id,
                "card_name": drawn_card.card_name,
                "denomination": drawn_card.denomination,
            }
        ]

        # Check if drawn card matches current sequence (Requirement 6.5)
        if drawn_card.denomination == state.current_sequence:
            # Create pending draw choice — player can play or keep
            state.pending_draw = PendingDraw(
                player_id=player.player_id,
                card=drawn_card,
                matches_sequence=True,
            )
            events.append(
                {
                    "type": "draw_choice_pending",
                    "player_id": player.player_id,
                    "card_id": drawn_card.card_id,
                    "denomination": drawn_card.denomination,
                    "message": "You drew a matching card. Play it or keep it?",
                }
            )
        else:
            # Non-matching draw: create pending accept (Requirement 6.6)
            state.pending_draw = PendingDraw(
                player_id=player.player_id,
                card=drawn_card,
                matches_sequence=False,
            )
            events.append(
                {
                    "type": "draw_accept_pending",
                    "player_id": player.player_id,
                    "card_id": drawn_card.card_id,
                    "denomination": drawn_card.denomination,
                    "message": "Drawn card does not match. Press Accept to continue.",
                }
            )

        return events

    def _handle_accept_draw(
        self, state: GameState, player_index: int
    ) -> Union[List[dict], Tuple[str, str]]:
        """Handle an accept_draw action (player confirms drawn card).

        For a matching draw, this means the player chose to keep the card (pass).
        For a non-matching draw, this confirms the player has seen the card.
        In both cases, a pass is recorded and the turn advances.

        Args:
            state: The current game state.
            player_index: Index of the player in state.players.

        Returns:
            List of game events on success, or error tuple on failure.
        """
        if state.pending_draw is None:
            return ("no_pending_draw", "No pending draw to accept.")

        if state.pending_draw.player_id != state.players[player_index].player_id:
            return ("not_your_draw", "This pending draw is not yours.")

        player = state.players[player_index]

        # Clear pending draw
        state.pending_draw = None

        # Record pass — set sequence_broken for next player (Requirement 6.7)
        state.sequence_broken = True

        events = [
            {
                "type": "pass_recorded",
                "player_id": player.player_id,
            }
        ]

        # Advance turn
        self._advance_turn(state)
        events.append(
            {
                "type": "turn_advanced",
                "next_player_id": state.players[state.current_player_index].player_id,
            }
        )

        return events

    def _handle_play_drawn_card(
        self, state: GameState, player_index: int, action: dict
    ) -> Union[List[dict], Tuple[str, str]]:
        """Handle playing the drawn card during a pending draw choice.

        This is only valid when the drawn card matches the current sequence
        and the player chooses to play it immediately.

        Args:
            state: The current game state.
            player_index: Index of the player in state.players.
            action: The action dict with card_id.

        Returns:
            List of game events on success, or error tuple on failure.
        """
        if state.pending_draw is None:
            return ("no_pending_draw", "No pending draw to play from.")

        if not state.pending_draw.matches_sequence:
            return (
                "cannot_play_non_matching",
                "Drawn card does not match sequence. You must accept it.",
            )

        if state.pending_draw.player_id != state.players[player_index].player_id:
            return ("not_your_draw", "This pending draw is not yours.")

        card_id = action.get("card_id")
        pending_card = state.pending_draw.card

        if card_id != pending_card.card_id:
            return (
                "wrong_card",
                "You can only play the drawn card during a pending draw choice.",
            )

        player = state.players[player_index]

        # Remove the card from hand (it was added during draw)
        card_index = None
        for i, c in enumerate(player.hand):
            if c.card_id == pending_card.card_id:
                card_index = i
                break

        if card_index is None:
            return ("card_not_in_hand", "Drawn card not found in hand.")

        player.hand.pop(card_index)
        player.play_pile.append(pending_card)

        # Track last_played_denomination (Requirement 6.9)
        state.last_played_denomination = pending_card.denomination

        # Advance sequence
        state.current_sequence = self._advance_sequence(pending_card.denomination)

        # Clear pending draw and sequence_broken
        state.pending_draw = None
        state.sequence_broken = False

        events = [
            {
                "type": "card_played",
                "player_id": player.player_id,
                "card_id": pending_card.card_id,
                "card_name": pending_card.card_name,
                "denomination": pending_card.denomination,
                "power": pending_card.power_text,
                "new_sequence": state.current_sequence,
            }
        ]

        # Advance turn
        self._advance_turn(state)
        events.append(
            {
                "type": "turn_advanced",
                "next_player_id": state.players[state.current_player_index].player_id,
            }
        )

        return events

    def _handle_power_choice(
        self, state: GameState, player_index: int, action: dict
    ) -> Union[List[dict], Tuple[str, str]]:
        """Handle a power_choice action — player responding to a power prompt.

        Delegates to the PowerResolver to process the choice. After the power
        is fully resolved (no more pending prompts), advances the turn.

        Args:
            state: The current game state.
            player_index: Index of the player making the choice.
            action: The action dict containing choice details (choice, card_id,
                target_player_index, value, etc.).

        Returns:
            List of game events on success, or error tuple on failure.

        Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7
        """
        if state.pending_power is None:
            return ("no_pending_power", "No pending power to resolve.")

        if state.pending_power.player_index != player_index:
            return ("not_your_power", "This pending power is not yours to resolve.")

        # Build the choice dict from the action payload
        choice = {}
        # Map from the protocol format to what PowerResolver expects
        if "choice" in action:
            choice["choice"] = action["choice"]
        elif "value" in action:
            # Client sends {choice_type: "option", value: "activate"/"decline"}
            value = action["value"]
            if value in ("activate", "decline"):
                choice["choice"] = value
            else:
                # For target selection, try to interpret the value
                choice["choice"] = "activate"
                # Try to parse as integer (player index or card id)
                try:
                    int_value = int(value)
                    # Determine what kind of target based on the pending power phase
                    if state.pending_power.phase == "choose_target":
                        power_name = state.pending_power.power_name
                        from game.powers.resolver import POWERS_NEEDING_TARGET
                        # Powers that need a player target
                        player_target_powers = {
                            "poison", "copy", "draw", "kill", "recycle",
                            "score", "battle", "assimilate", "utilize",
                        }
                        card_choice_powers = {
                            "discard", "rescue", "cycle", "exchange",
                            "replay", "process", "avalanche",
                        }
                        if power_name in player_target_powers:
                            choice["target_player_index"] = int_value
                        elif power_name in card_choice_powers:
                            choice["card_id"] = int_value
                        elif power_name == "freeze":
                            choice["power_to_freeze"] = value
                        elif power_name == "scan":
                            choice["order"] = action.get("order", [])
                            choice["placement"] = value
                        elif power_name == "toxin":
                            choice["card_id"] = int_value
                        else:
                            choice["value"] = value
                except (ValueError, TypeError):
                    # Non-integer value — could be a power name for Freeze
                    if state.pending_power.power_name == "freeze":
                        choice["choice"] = "activate"
                        choice["power_to_freeze"] = value
                    else:
                        choice["value"] = value

        # Copy additional fields that might be needed
        for key in ("card_id", "target_player_index", "play_immediately",
                    "power_to_freeze", "order", "placement", "card_ids"):
            if key in action and key not in choice:
                choice[key] = action[key]

        # Delegate to PowerResolver
        result = self._power_resolver.handle_power_choice(state, player_index, choice)

        if isinstance(result, tuple):
            return result

        events = result

        # Check if the power is fully resolved (no more pending power)
        if state.pending_power is None:
            # Power fully resolved — advance the turn
            # But check if Go power was activated (player keeps their turn)
            go_activated = any(
                e.get("type") == "power_activated" and e.get("power_name") == "go"
                for e in events
            )
            skip_activated = any(
                e.get("type") == "power_activated" and e.get("power_name") == "skip"
                for e in events
            )

            if not go_activated and not skip_activated:
                # Normal turn advance
                self._advance_turn(state)
                events.append(
                    {
                        "type": "turn_advanced",
                        "next_player_id": state.players[
                            state.current_player_index
                        ].player_id,
                    }
                )
            # For Go: current_player_index was already set by the power
            # For Skip: current_player_index was already set by the power

        return events

    def initialise_game(self, session: GameSession) -> GameState:
        """Initialise a new game from a session.

        Performs the following steps:
        1. Creates PlayerState objects for each player.
        2. Assigns random unique seat positions (1 through player_count).
        3. Shuffles each player's deck_cards to form their draw_deck.
        4. Deals 7 cards from each player's draw_deck to their hand.
        5. Selects a random starting player (sets current_player_index).
        6. Sets direction=1, current_sequence=1, round_number=1, game_status="active".

        Args:
            session: A GameSession containing player setup data and configuration.

        Returns:
            A fully initialised GameState ready for play.

        Requirements: 5.1, 5.2, 5.3, 5.4, 5.5
        """
        player_count = len(session.players)

        # Step 1 & 2: Assign random unique seat positions
        seat_positions = list(range(1, player_count + 1))
        random.shuffle(seat_positions)

        # Step 3 & 4: Create PlayerState objects with shuffled decks and dealt hands
        player_states: List[PlayerState] = []
        for i, player_setup in enumerate(session.players):
            # Shuffle the player's deck cards independently
            draw_deck = list(player_setup.deck_cards)
            random.shuffle(draw_deck)

            # Deal 7 cards from the draw deck to the hand
            hand = draw_deck[:self.CARDS_TO_DEAL]
            draw_deck = draw_deck[self.CARDS_TO_DEAL:]

            player_state = PlayerState(
                player_id=player_setup.player_id,
                username=player_setup.username,
                is_computer=player_setup.is_computer,
                hand=hand,
                draw_deck=draw_deck,
                play_pile=[],
                discard_pile=[],
                cumulative_score=0,
                is_decked=False,
                has_gone_out=False,
                seat_position=seat_positions[i],
            )
            player_states.append(player_state)

        # Sort players by seat position for consistent ordering
        player_states.sort(key=lambda p: p.seat_position)

        # Step 5: Select a random starting player
        current_player_index = random.randint(0, player_count - 1)

        # Step 6: Create the GameState with initial values
        game_state = GameState(
            game_id=session.game_id,
            players=player_states,
            spectators=list(session.spectators),
            current_player_index=current_player_index,
            direction=1,
            current_sequence=1,
            last_played_denomination=None,
            sequence_broken=False,
            round_number=1,
            frozen_powers={},
            game_status="active",
            reconnection_timeout=session.reconnection_timeout,
        )

        # Store the game state for later access
        self._games[session.game_id] = game_state

        return game_state
