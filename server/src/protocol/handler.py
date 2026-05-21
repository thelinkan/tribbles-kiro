"""WebSocket message router that dispatches incoming messages to services.

The MessageHandler parses incoming JSON messages, identifies the message type,
and routes them to the appropriate service handler method. It validates session
tokens for authenticated endpoints and returns JSON responses.
"""

import json
import logging
from typing import Any, Dict, Optional

from websockets.asyncio.server import ServerConnection

from protocol.messages import (
    ClientMessageType,
    ServerMessageType,
    decode_message,
    encode_message,
    error_message,
)

logger = logging.getLogger(__name__)

# Message types that do not require authentication
UNAUTHENTICATED_TYPES = frozenset({
    ClientMessageType.REGISTER,
    ClientMessageType.LOGIN,
})


class MessageHandler:
    """Routes incoming WebSocket messages to registered service handlers.

    Accepts service instances in the constructor and routes messages by type
    to the appropriate service method. Validates session tokens for all
    authenticated endpoints.
    """

    def __init__(
        self,
        auth_service=None,
        card_repository=None,
        deck_service=None,
        lobby_service=None,
        game_engine=None,
        disconnection_manager=None,
        spectator_manager=None,
    ) -> None:
        self._auth_service = auth_service
        self._card_repository = card_repository
        self._deck_service = deck_service
        self._lobby_service = lobby_service
        self._game_engine = game_engine
        self._disconnection_manager = disconnection_manager
        self._spectator_manager = spectator_manager

        # Map of websocket -> player_id for authenticated connections
        self._authenticated_connections: Dict[ServerConnection, int] = {}

    async def handle_message(
        self,
        websocket: ServerConnection,
        raw_message: str | bytes,
    ) -> Optional[str]:
        """Parse and route an incoming WebSocket message.

        Args:
            websocket: The client's WebSocket connection.
            raw_message: The raw message string or bytes from the client.

        Returns:
            An optional response string to send back to the client.
        """
        if isinstance(raw_message, bytes):
            raw_message = raw_message.decode("utf-8")

        try:
            msg_type, payload = decode_message(raw_message)
        except ValueError as e:
            logger.warning("Invalid message from %s: %s", websocket.remote_address, e)
            return error_message("invalid_message", str(e))

        # Extract token from top-level message if not in payload
        # (client sends token at top level: {"type": ..., "payload": ..., "token": ...})
        import json as _json
        try:
            full_msg = _json.loads(raw_message)
            top_level_token = full_msg.get("token")
            if top_level_token and "token" not in payload:
                payload["token"] = top_level_token
        except (ValueError, TypeError):
            pass

        logger.debug("Routing '%s' from %s", msg_type, websocket.remote_address)

        try:
            # For unauthenticated endpoints, route directly
            if msg_type in UNAUTHENTICATED_TYPES:
                return await self._route_unauthenticated(msg_type, payload, websocket)

            # For all other endpoints, validate the session token first
            player_id = await self._validate_session(payload, websocket)
            if player_id is None:
                return error_message(
                    "unauthorised",
                    "Invalid or missing session token.",
                )

            return await self._route_authenticated(msg_type, payload, player_id, websocket)

        except Exception:
            logger.exception(
                "Error handling '%s' from %s", msg_type, websocket.remote_address
            )
            return error_message(
                "internal_error",
                "An internal server error occurred.",
            )

    async def _validate_session(
        self, payload: dict, websocket: ServerConnection
    ) -> Optional[int]:
        """Validate the session token from the payload.

        Args:
            payload: The message payload containing a 'token' field.
            websocket: The client's WebSocket connection.

        Returns:
            The player_id if valid, None otherwise.
        """
        token = payload.get("token")
        if not token:
            return None

        if self._auth_service is None:
            return None

        player_id, auth_error = await self._auth_service.validate_token(token)
        if auth_error is not None:
            return None

        # Track the authenticated connection
        self._authenticated_connections[websocket] = player_id
        return player_id

    async def _route_unauthenticated(
        self, msg_type: str, payload: dict, websocket: ServerConnection
    ) -> str:
        """Route unauthenticated message types (register, login).

        Args:
            msg_type: The message type.
            payload: The message payload.
            websocket: The client's WebSocket connection.

        Returns:
            A JSON response string.
        """
        if msg_type == ClientMessageType.REGISTER:
            return await self._handle_register(payload)
        elif msg_type == ClientMessageType.LOGIN:
            return await self._handle_login(payload, websocket)
        else:
            return error_message("unknown_message_type", f"Unknown message type: {msg_type}")

    async def _route_authenticated(
        self, msg_type: str, payload: dict, player_id: int, websocket: ServerConnection
    ) -> str:
        """Route authenticated message types to the appropriate service.

        Args:
            msg_type: The message type.
            payload: The message payload.
            player_id: The authenticated player's ID.
            websocket: The client's WebSocket connection.

        Returns:
            A JSON response string.
        """
        # Card repository
        if msg_type == ClientMessageType.SEARCH_CARDS:
            return await self._handle_search_cards(payload)

        # Deck service
        elif msg_type == ClientMessageType.SAVE_DECK:
            return await self._handle_save_deck(payload, player_id)
        elif msg_type == ClientMessageType.LOAD_DECK:
            return await self._handle_load_deck(payload, player_id)
        elif msg_type == ClientMessageType.LIST_DECKS:
            return await self._handle_list_decks(player_id)
        elif msg_type == ClientMessageType.COPY_DECK:
            return await self._handle_copy_deck(payload, player_id)

        # Lobby service
        elif msg_type == ClientMessageType.CREATE_GAME:
            return await self._handle_create_game(payload, player_id)
        elif msg_type == ClientMessageType.JOIN_GAME:
            return await self._handle_join_game(payload, player_id)
        elif msg_type == ClientMessageType.START_GAME:
            return await self._handle_start_game(payload, player_id)
        elif msg_type == ClientMessageType.LIST_GAMES:
            return await self._handle_list_games()
        elif msg_type == ClientMessageType.WATCH_GAME:
            return await self._handle_watch_game(payload, player_id)
        elif msg_type == ClientMessageType.LEAVE_SPECTATE:
            return await self._handle_leave_spectate(payload, player_id)

        # Game engine
        elif msg_type == ClientMessageType.PLAY_CARD:
            return await self._handle_play_card(payload, player_id)
        elif msg_type == ClientMessageType.DRAW_CARD:
            return await self._handle_draw_card(payload, player_id)
        elif msg_type == ClientMessageType.ACCEPT_DRAW:
            return await self._handle_accept_draw(payload, player_id)
        elif msg_type == ClientMessageType.POWER_CHOICE:
            return await self._handle_power_choice(payload, player_id)
        elif msg_type == ClientMessageType.GET_GAME_STATE:
            return await self._handle_get_game_state(payload, player_id)

        # Disconnection manager
        elif msg_type == ClientMessageType.RECONNECT:
            return await self._handle_reconnect(payload, player_id, websocket)

        else:
            return error_message("unknown_message_type", f"Unknown message type: {msg_type}")

    # --- Auth handlers ---

    async def _handle_register(self, payload: dict) -> str:
        """Handle a register message."""
        if self._auth_service is None:
            return error_message("not_implemented", "Auth service not available.")

        username = payload.get("username")
        password = payload.get("password")
        email = payload.get("email")

        if not username or not password or not email:
            return error_message("invalid_payload", "Missing username, password, or email.")

        player_id, auth_error = await self._auth_service.register(username, password, email)
        if auth_error is not None:
            return error_message(auth_error.code, auth_error.message)

        return encode_message("register_response", {"player_id": player_id})

    async def _handle_login(self, payload: dict, websocket: ServerConnection) -> str:
        """Handle a login message."""
        if self._auth_service is None:
            return error_message("not_implemented", "Auth service not available.")

        username = payload.get("username")
        password = payload.get("password")

        if not username or not password:
            return error_message("invalid_payload", "Missing username or password.")

        token, auth_error = await self._auth_service.login(username, password)
        if auth_error is not None:
            return error_message(auth_error.code, auth_error.message)

        # Validate the token to get the player_id and track the connection
        player_id, _ = await self._auth_service.validate_token(token)
        if player_id is not None:
            self._authenticated_connections[websocket] = player_id

        return encode_message("login_response", {"token": token, "player_id": player_id})

    # --- Card repository handlers ---

    async def _handle_search_cards(self, payload: dict) -> str:
        """Handle a search_cards message."""
        if self._card_repository is None:
            return error_message("not_implemented", "Card repository not available.")

        from cards.repository import CardFilter

        filters = CardFilter(
            denomination=payload.get("denomination"),
            power_name=payload.get("power_name") or payload.get("power"),
            expansion=payload.get("expansion") or payload.get("expansion_id"),
            card_name_substring=payload.get("card_name_substring") or payload.get("name"),
        )

        cards = await self._card_repository.search_cards(filters)
        cards_data = [
            {
                "card_id": c.card_id,
                "card_name": c.card_name,
                "denomination": c.denomination,
                "power_text": c.power_text,
                "card_number": c.card_number,
                "expansion_id": c.expansion_id,
                "image_filename": c.image_filename,
            }
            for c in cards
        ]

        return encode_message("card_response", {"action": "search_results", "cards": cards_data})

    # --- Deck service handlers ---

    async def _handle_save_deck(self, payload: dict, player_id: int) -> str:
        """Handle a save_deck message."""
        if self._deck_service is None:
            return error_message("not_implemented", "Deck service not available.")

        # The client sends deck fields directly in the payload
        deck_data = payload.get("deck_data", payload)

        # Convert cards from array format [{card_id, quantity}] to dict {card_id: quantity}
        cards_raw = deck_data.get("cards", {})
        if isinstance(cards_raw, list):
            cards_dict = {}
            for entry in cards_raw:
                cid = entry.get("card_id")
                qty = entry.get("quantity", 1)
                if cid is not None:
                    cards_dict[cid] = qty
            deck_data = dict(deck_data)
            deck_data["cards"] = cards_dict

        # Map "comment" to "comment_text" if needed
        if "comment" in deck_data and "comment_text" not in deck_data:
            deck_data["comment_text"] = deck_data["comment"]

        # If deck_id is present, update the existing deck instead of creating new
        existing_deck_id = deck_data.get("deck_id") or payload.get("deck_id")
        if existing_deck_id:
            updated = await self._deck_service.update_deck(player_id, int(float(existing_deck_id)), deck_data)
            if updated:
                return encode_message("deck_response", {"action": "deck_saved", "deck_id": int(existing_deck_id)})
            # If update failed (not owned), fall through to create new

        deck_id = await self._deck_service.save_deck(player_id, deck_data)
        return encode_message("deck_response", {"action": "deck_saved", "deck_id": deck_id})

    async def _handle_load_deck(self, payload: dict, player_id: int) -> str:
        """Handle a load_deck message."""
        if self._deck_service is None:
            return error_message("not_implemented", "Deck service not available.")

        deck_id = payload.get("deck_id")
        if deck_id is None:
            return error_message("invalid_payload", "Missing deck_id.")

        deck, deck_error = await self._deck_service.load_deck(player_id, deck_id)
        if deck_error is not None:
            return error_message(deck_error.code, deck_error.message)

        # Enrich card entries with card details from the repository
        cards_list = []
        for card_id, quantity in deck.cards.items():
            card_detail = None
            if self._card_repository:
                card_detail = await self._card_repository.get_card(int(card_id))
            if card_detail:
                cards_list.append({
                    "card_id": card_detail.card_id,
                    "card_name": card_detail.card_name,
                    "denomination": card_detail.denomination,
                    "power_text": card_detail.power_text,
                    "quantity": quantity,
                })
            else:
                cards_list.append({
                    "card_id": int(card_id),
                    "card_name": f"Card {card_id}",
                    "denomination": 0,
                    "power_text": "",
                    "quantity": quantity,
                })

        return encode_message("deck_response", {
            "action": "deck_loaded",
            "deck_id": deck.deck_id,
            "deck_name": deck.deck_name,
            "is_public": deck.is_public,
            "comment": deck.comment_text or "",
            "cards": cards_list,
        })

    async def _handle_list_decks(self, player_id: int) -> str:
        """Handle a list_decks message."""
        if self._deck_service is None:
            return error_message("not_implemented", "Deck service not available.")

        decks = await self._deck_service.list_decks(player_id)
        decks_data = [
            {
                "deck_id": d.deck_id,
                "deck_name": d.deck_name,
                "owner_player_id": d.owner_player_id,
                "is_public": d.is_public,
                "total_card_count": d.total_card_count,
            }
            for d in decks
        ]
        return encode_message("deck_response", {"action": "deck_list", "decks": decks_data})

    async def _handle_copy_deck(self, payload: dict, player_id: int) -> str:
        """Handle a copy_deck message."""
        if self._deck_service is None:
            return error_message("not_implemented", "Deck service not available.")

        source_deck_id = payload.get("source_deck_id")
        if source_deck_id is None:
            return error_message("invalid_payload", "Missing source_deck_id.")

        new_deck_id, deck_error = await self._deck_service.copy_deck(player_id, source_deck_id)
        if deck_error is not None:
            return error_message(deck_error.code, deck_error.message)

        return encode_message("deck_response", {"action": "deck_copied", "deck_id": new_deck_id})

    # --- Lobby service handlers ---

    async def _handle_create_game(self, payload: dict, player_id: int) -> str:
        """Handle a create_game message."""
        if self._lobby_service is None:
            return error_message("not_implemented", "Lobby service not available.")

        deck_id = payload.get("deck_id")
        player_count = payload.get("player_count")

        if deck_id is None or player_count is None:
            return error_message("invalid_payload", "Missing deck_id or player_count.")

        session_id, lobby_error = await self._lobby_service.create_game(
            player_id, deck_id, player_count
        )
        if lobby_error is not None:
            return error_message(lobby_error.code, lobby_error.message)

        return encode_message("create_game_success", {"session_id": session_id})

    async def _handle_join_game(self, payload: dict, player_id: int) -> str:
        """Handle a join_game message."""
        if self._lobby_service is None:
            return error_message("not_implemented", "Lobby service not available.")

        session_id = payload.get("session_id")
        deck_id = payload.get("deck_id")

        if not session_id or deck_id is None:
            return error_message("invalid_payload", "Missing session_id or deck_id.")

        _, lobby_error = await self._lobby_service.join_game(player_id, deck_id, session_id)
        if lobby_error is not None:
            return error_message(lobby_error.code, lobby_error.message)

        return encode_message("join_game_success", {"session_id": session_id})

    async def _handle_start_game(self, payload: dict, player_id: int) -> str:
        """Handle a start_game message."""
        if self._lobby_service is None:
            return error_message("not_implemented", "Lobby service not available.")

        session_id = payload.get("session_id")
        if not session_id:
            return error_message("invalid_payload", "Missing session_id.")

        _, lobby_error = await self._lobby_service.start_game(player_id, session_id)
        if lobby_error is not None:
            return error_message(lobby_error.code, lobby_error.message)

        return encode_message("start_game_success", {"session_id": session_id})

    async def _handle_list_games(self) -> str:
        """Handle a list_games message."""
        if self._lobby_service is None:
            return error_message("not_implemented", "Lobby service not available.")

        waiting = await self._lobby_service.list_waiting_games()
        active = await self._lobby_service.list_active_games()

        waiting_data = [
            {
                "session_id": s.session_id,
                "creator_player_id": s.creator_player_id,
                "player_count": s.player_count,
                "current_player_count": s.current_player_count,
                "status": s.status,
                "players_joined": s.players_joined,
            }
            for s in waiting
        ]
        active_data = [
            {
                "session_id": s.session_id,
                "creator_player_id": s.creator_player_id,
                "player_count": s.player_count,
                "current_player_count": s.current_player_count,
                "status": s.status,
                "players_joined": s.players_joined,
            }
            for s in active
        ]

        return encode_message("list_games_result", {
            "waiting": waiting_data,
            "active": active_data,
        })

    async def _handle_watch_game(self, payload: dict, player_id: int) -> str:
        """Handle a watch_game message."""
        if self._lobby_service is None:
            return error_message("not_implemented", "Lobby service not available.")

        session_id = payload.get("session_id")
        if not session_id:
            return error_message("invalid_payload", "Missing session_id.")

        _, lobby_error = await self._lobby_service.watch_game(player_id, session_id)
        if lobby_error is not None:
            return error_message(lobby_error.code, lobby_error.message)

        return encode_message("watch_game_success", {"session_id": session_id})

    async def _handle_leave_spectate(self, payload: dict, player_id: int) -> str:
        """Handle a leave_spectate message."""
        if self._spectator_manager is None or self._game_engine is None:
            return error_message("not_implemented", "Spectator service not available.")

        session_id = payload.get("session_id")
        if not session_id:
            return error_message("invalid_payload", "Missing session_id.")

        # Get the game state from the engine
        game_state = self._game_engine._games.get(session_id)
        if game_state is None:
            return error_message("game_not_found", f"Game '{session_id}' not found.")

        removed = self._spectator_manager.leave_spectate(game_state, player_id)
        if not removed:
            return error_message("not_spectating", "You are not spectating this game.")

        return encode_message("leave_spectate_success", {"session_id": session_id})

    # --- Game engine handlers ---

    async def _handle_play_card(self, payload: dict, player_id: int) -> str:
        """Handle a play_card message."""
        if self._game_engine is None:
            return error_message("not_implemented", "Game engine not available.")

        game_id = payload.get("game_id")
        card_id = payload.get("card_id")
        activate_power = payload.get("activate_power", False)

        if not game_id or card_id is None:
            return error_message("invalid_payload", "Missing game_id or card_id.")

        action = {
            "type": "play_card",
            "card_id": card_id,
            "activate_power": activate_power,
        }

        result = self._game_engine.process_action(game_id, player_id, action)
        if isinstance(result, tuple):
            return error_message(result[0], result[1])

        return encode_message("action_result", {"events": result})

    async def _handle_draw_card(self, payload: dict, player_id: int) -> str:
        """Handle a draw_card message."""
        if self._game_engine is None:
            return error_message("not_implemented", "Game engine not available.")

        game_id = payload.get("game_id")
        if not game_id:
            return error_message("invalid_payload", "Missing game_id.")

        action = {"type": "draw_card"}

        result = self._game_engine.process_action(game_id, player_id, action)
        if isinstance(result, tuple):
            return error_message(result[0], result[1])

        return encode_message("action_result", {"events": result})

    async def _handle_accept_draw(self, payload: dict, player_id: int) -> str:
        """Handle an accept_draw message."""
        if self._game_engine is None:
            return error_message("not_implemented", "Game engine not available.")

        game_id = payload.get("game_id")
        if not game_id:
            return error_message("invalid_payload", "Missing game_id.")

        action = {"type": "accept_draw"}

        result = self._game_engine.process_action(game_id, player_id, action)
        if isinstance(result, tuple):
            return error_message(result[0], result[1])

        return encode_message("action_result", {"events": result})

    async def _handle_power_choice(self, payload: dict, player_id: int) -> str:
        """Handle a power_choice message."""
        if self._game_engine is None:
            return error_message("not_implemented", "Game engine not available.")

        game_id = payload.get("game_id")
        if not game_id:
            return error_message("invalid_payload", "Missing game_id.")

        # Pass the entire payload as the action (contains choice_type, value, etc.)
        action = {"type": "power_choice"}
        action.update({k: v for k, v in payload.items() if k not in ("token", "game_id")})

        result = self._game_engine.process_action(game_id, player_id, action)
        if isinstance(result, tuple):
            return error_message(result[0], result[1])

        return encode_message("action_result", {"events": result})

    async def _handle_get_game_state(self, payload: dict, player_id: int) -> str:
        """Handle a get_game_state message."""
        if self._game_engine is None:
            return error_message("not_implemented", "Game engine not available.")

        game_id = payload.get("game_id")
        if not game_id:
            return error_message("invalid_payload", "Missing game_id.")

        game_state = self._game_engine._games.get(game_id)
        if game_state is None:
            return error_message("game_not_found", f"Game '{game_id}' not found.")

        # Check if the player is a spectator
        if self._spectator_manager and self._spectator_manager.is_spectator(game_state, player_id):
            spectator_state = self._spectator_manager.get_spectator_visible_state(game_state)
            return encode_message(ServerMessageType.SPECTATOR_STATE_UPDATE, spectator_state)

        # Build player-visible state
        player_state = self._build_player_visible_state(game_state, player_id)
        if player_state is None:
            return error_message("player_not_found", "You are not in this game.")

        return encode_message(ServerMessageType.GAME_STATE_UPDATE, {"visible_state": player_state})

    def _build_player_visible_state(self, game_state, player_id: int) -> Optional[dict]:
        """Build the visible state for a specific player.

        Args:
            game_state: The current game state.
            player_id: The player requesting their visible state.

        Returns:
            A dict with the player's visible state, or None if player not found.
        """
        player = None
        for p in game_state.players:
            if p.player_id == player_id:
                player = p
                break

        if player is None:
            return None

        hand = [
            {
                "card_id": c.card_id,
                "card_name": c.card_name,
                "denomination": c.denomination,
                "power_text": c.power_text,
                "expansion_id": c.expansion_id,
            }
            for c in player.hand
        ]

        active_player_id = game_state.players[game_state.current_player_index].player_id

        return {
            "hand": hand,
            "play_pile_count": len(player.play_pile),
            "draw_deck_count": len(player.draw_deck),
            "discard_pile_count": len(player.discard_pile),
            "cumulative_score": player.cumulative_score,
            "current_sequence": game_state.current_sequence,
            "direction": game_state.direction,
            "active_player_id": active_player_id,
            "round_number": game_state.round_number,
            "game_status": game_state.game_status,
            "is_your_turn": active_player_id == player_id,
        }

    # --- Disconnection/reconnection handler ---

    async def _handle_reconnect(
        self, payload: dict, player_id: int, websocket: ServerConnection
    ) -> str:
        """Handle a reconnect message."""
        if self._disconnection_manager is None or self._game_engine is None:
            return error_message("not_implemented", "Disconnection service not available.")

        session_id = payload.get("session_id")
        if not session_id:
            return error_message("invalid_payload", "Missing session_id.")

        game_state = self._game_engine._games.get(session_id)
        if game_state is None:
            return error_message("game_not_found", f"Game '{session_id}' not found.")

        # Check if game ended while disconnected
        end_result = self._disconnection_manager.handle_game_ended_while_disconnected(
            game_state, player_id
        )
        if end_result is not None:
            return json.dumps(end_result)

        # Mark the player as reconnected
        self._disconnection_manager.mark_reconnected(game_state, player_id)

        # Build and return the reconnection state sync
        reconnect_state = self._disconnection_manager.get_reconnect_state(
            game_state, player_id
        )

        return encode_message(
            ServerMessageType.RECONNECT_STATE_SYNC,
            reconnect_state,
        )

    def handle_disconnect(self, websocket: ServerConnection) -> Optional[int]:
        """Handle a WebSocket disconnection.

        Removes the connection from the authenticated connections map and
        returns the player_id that was associated with it.

        Args:
            websocket: The disconnected WebSocket connection.

        Returns:
            The player_id that was disconnected, or None if not authenticated.
        """
        return self._authenticated_connections.pop(websocket, None)
