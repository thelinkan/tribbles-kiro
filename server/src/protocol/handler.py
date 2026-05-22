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
        logger.info("Message received: type='%s' from %s", msg_type, websocket.remote_address)

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
            try:
                deck_id_int = int(float(str(existing_deck_id)))
            except (ValueError, TypeError):
                deck_id_int = None
            if deck_id_int:
                updated = await self._deck_service.update_deck(player_id, deck_id_int, deck_data)
                if updated:
                    return encode_message("deck_response", {"action": "deck_saved", "deck_id": deck_id_int})
            # If update failed (not owned or invalid), fall through to create new

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

        logger.info("Player %d creating game: deck_id=%s, player_count=%s", player_id, deck_id, player_count)

        session_id, lobby_error = await self._lobby_service.create_game(
            player_id, int(float(str(deck_id))), int(float(str(player_count)))
        )
        if lobby_error is not None:
            logger.warning("Create game failed for player %d: %s", player_id, lobby_error.message)
            return error_message(lobby_error.code, lobby_error.message)

        logger.info("Game created: session_id=%s by player %d", session_id, player_id)
        return encode_message("lobby_response", {"action": "game_created", "session_id": session_id})

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

        return encode_message("lobby_response", {"action": "game_joined", "session_id": session_id})

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

        # Initialise the game in the GameEngine
        if self._game_engine is not None:
            from game.engine import GameSession, PlayerSetup
            from models import CardInstance

            lobby_session = self._lobby_service._sessions.get(session_id)
            if lobby_session:
                player_setups = []
                for pid, deck_id in lobby_session.players.items():
                    # For AI players (negative IDs), create a minimal deck
                    if pid < 0:
                        # AI player with a simple deck of 40 cards
                        deck_cards = [
                            CardInstance(
                                card_id=abs(pid) * 1000 + i,
                                card_name=f"AI_Card_{i}",
                                denomination=[1, 10, 100, 1000, 10000, 100000][i % 6],
                                power_text=["Go", "Skip", "Reverse", "Discard", "Poison", "Rescue"][i % 6],
                                expansion_id=1,
                            )
                            for i in range(40)
                        ]
                        player_setups.append(PlayerSetup(
                            player_id=pid,
                            username=f"Computer_{abs(pid)}",
                            is_computer=True,
                            deck_cards=deck_cards,
                        ))
                    else:
                        # Human player — load their deck from the database
                        deck_cards = []
                        if self._deck_service and self._card_repository:
                            deck, _ = await self._deck_service.load_deck(pid, int(float(str(deck_id))))
                            if deck:
                                for card_id, quantity in deck.cards.items():
                                    card = await self._card_repository.get_card(int(card_id))
                                    if card:
                                        for _ in range(quantity):
                                            deck_cards.append(CardInstance(
                                                card_id=card.card_id,
                                                card_name=card.card_name,
                                                denomination=card.denomination,
                                                power_text=card.power_text,
                                                expansion_id=card.expansion_id,
                                                image_filename=card.image_filename,
                                            ))
                        player_setups.append(PlayerSetup(
                            player_id=pid,
                            username=f"Player_{pid}",
                            is_computer=False,
                            deck_cards=deck_cards,
                        ))

                game_session = GameSession(
                    game_id=session_id,
                    players=player_setups,
                    spectators=[],
                )
                self._game_engine.initialise_game(game_session)
                logger.info("Game initialised: session_id=%s with %d players", session_id, len(player_setups))

                # Process initial AI turns if the first player is AI
                self._process_ai_turns(session_id)

        return encode_message("lobby_response", {"action": "game_started", "session_id": session_id})

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

        return encode_message("lobby_response", {
            "action": "game_list",
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

        return encode_message("lobby_response", {"action": "watch_started", "session_id": session_id})

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

        return encode_message("lobby_response", {"action": "leave_spectate", "session_id": session_id})

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

        # Check if there's a power_prompt in the events (pending power for this player)
        has_power_prompt = any(e.get("type") == "power_prompt" for e in result)

        if not has_power_prompt:
            # No power prompt — process AI turns if it's now an AI player's turn
            ai_events = self._process_ai_turns(game_id)
            result.extend(ai_events)

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

        # Only process AI turns if there's no pending draw (turn already advanced)
        has_pending_draw = any(
            e.get("type") in ("draw_choice_pending", "draw_accept_pending")
            for e in result
        )
        if not has_pending_draw:
            ai_events = self._process_ai_turns(game_id)
            result.extend(ai_events)

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

        # Process AI turns if it's now an AI player's turn
        ai_events = self._process_ai_turns(game_id)
        result.extend(ai_events)

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

        # Check if there's still a pending power prompt (multi-step powers)
        has_power_prompt = any(e.get("type") == "power_prompt" for e in result)

        if not has_power_prompt:
            # Power fully resolved — process AI turns if it's now an AI player's turn
            ai_events = self._process_ai_turns(game_id)
            result.extend(ai_events)

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

        Includes the player's hand, all players' public info (names, scores,
        pile counts, seat positions), and game state info.

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

        # Local player's hand (full card details)
        hand = [
            {
                "card_id": c.card_id,
                "card_name": c.card_name,
                "denomination": c.denomination,
                "power_text": c.power_text,
                "expansion_id": c.expansion_id,
                "image_filename": c.image_filename,
            }
            for c in player.hand
        ]

        # Determine which cards in hand are valid to play
        valid_card_ids = []
        if game_state.players[game_state.current_player_index].player_id == player_id:
            for c in player.hand:
                if self._game_engine._is_valid_play(c, game_state):
                    valid_card_ids.append(c.card_id)

        active_player_id = game_state.players[game_state.current_player_index].player_id

        # All players' public info (in seat order)
        players_info = []
        for p in game_state.players:
            # Top card of play pile (visible to all)
            play_pile_top = []
            if p.play_pile:
                top = p.play_pile[-1]
                play_pile_top = [{
                    "card_id": top.card_id,
                    "card_name": top.card_name,
                    "denomination": top.denomination,
                    "power_text": top.power_text,
                    "image_filename": top.image_filename,
                }]

            # Top card of discard pile (visible to all)
            discard_pile_top = []
            if p.discard_pile:
                top = p.discard_pile[-1]
                discard_pile_top = [{
                    "card_id": top.card_id,
                    "card_name": top.card_name,
                    "denomination": top.denomination,
                    "power_text": top.power_text,
                    "image_filename": top.image_filename,
                }]

            players_info.append({
                "player_id": p.player_id,
                "username": p.username,
                "is_computer": p.is_computer,
                "cumulative_score": p.cumulative_score,
                "draw_deck_count": len(p.draw_deck),
                "play_pile_top": play_pile_top,
                "discard_pile_top": discard_pile_top,
                "is_decked": p.is_decked,
                "has_gone_out": p.has_gone_out,
                "seat_position": p.seat_position,
            })

        return {
            "local_player_id": player_id,
            "hand": hand,
            "valid_card_ids": valid_card_ids,
            "players": players_info,
            "current_sequence": game_state.current_sequence,
            "direction": game_state.direction,
            "active_player_id": active_player_id,
            "round_number": game_state.round_number,
            "game_status": game_state.game_status,
            "is_your_turn": active_player_id == player_id,
        }

    # --- AI turn processing ---

    def _process_ai_turns(self, game_id: str, max_turns: int = 50) -> list:
        """Process AI player turns until it's a human player's turn.

        Runs the AIController for each consecutive AI player turn. Stops when
        it's a human player's turn, the game ends, or max_turns is reached
        (safety limit to prevent infinite loops).

        Also handles AI power choices: when an AI plays a card with a power,
        it automatically resolves the power prompt.

        Args:
            game_id: The game session ID.
            max_turns: Maximum AI turns to process (safety limit).

        Returns:
            A list of game events generated by AI turns, with internal AI
            power_prompt events filtered out (they are already resolved).
        """
        from ai.controller import AIController

        game_state = self._game_engine._games.get(game_id)
        if game_state is None or game_state.game_status != "active":
            return []

        ai = AIController()
        all_events = []

        for _ in range(max_turns):
            current_player = game_state.players[game_state.current_player_index]

            # Stop if it's a human player's turn
            if not current_player.is_computer:
                break

            # Check if there's a pending power for this AI player
            if game_state.pending_power is not None:
                if game_state.pending_power.player_index == game_state.current_player_index:
                    # AI resolves the power
                    power_events = self._resolve_ai_power(game_id, game_state, ai)
                    all_events.extend(power_events)
                    # After resolving, check if game ended or it's now a human's turn
                    if game_state.game_status != "active":
                        break
                    continue
                else:
                    # Pending power for a different player — shouldn't happen, break
                    break

            # AI chooses an action
            action = ai.choose_action(game_state, current_player.player_id)

            # Process the action
            result = self._game_engine.process_action(game_id, current_player.player_id, action)
            if isinstance(result, list):
                all_events.extend(result)
            else:
                # AI action failed — shouldn't happen, but break to avoid loop
                logger.warning("AI action failed for player %d: %s", current_player.player_id, result)
                break

            # Check if game ended
            if game_state.game_status != "active":
                break

            # Check if a power prompt was created for this AI player
            if game_state.pending_power is not None and game_state.pending_power.player_index == game_state.players.index(current_player):
                # AI resolves the power immediately
                power_events = self._resolve_ai_power(game_id, game_state, ai)
                all_events.extend(power_events)
                if game_state.game_status != "active":
                    break
                continue

            # Handle pending draw for AI (accept or play)
            if game_state.pending_draw and game_state.pending_draw.player_id == current_player.player_id:
                follow_up = ai.choose_action(game_state, current_player.player_id)
                result2 = self._game_engine.process_action(game_id, current_player.player_id, follow_up)
                if isinstance(result2, list):
                    all_events.extend(result2)

        # Filter out AI-internal events that would confuse the human client.
        # power_prompt: already resolved by AI
        # draw_choice_pending / draw_accept_pending: already resolved by AI
        AI_INTERNAL_EVENT_TYPES = {"power_prompt", "draw_choice_pending", "draw_accept_pending"}
        filtered_events = [
            e for e in all_events
            if e.get("type") not in AI_INTERNAL_EVENT_TYPES
        ]

        return filtered_events

    def _resolve_ai_power(self, game_id: str, game_state, ai) -> list:
        """Resolve a pending power prompt for an AI player.

        The AI will always activate powers and make reasonable target choices.

        Args:
            game_id: The game session ID.
            game_state: The current game state.
            ai: The AIController instance.

        Returns:
            A list of game events from power resolution.
        """
        all_events = []
        max_steps = 10  # Safety limit for multi-step powers

        for _ in range(max_steps):
            if game_state.pending_power is None:
                break

            pending = game_state.pending_power
            player_index = pending.player_index
            player = game_state.players[player_index]

            # Build the AI's power choice
            choice_action = {"type": "power_choice"}

            if pending.phase == "activate_or_decline":
                # AI activates powers only if they can be used effectively
                power_name = pending.power_name
                should_activate = True

                # Check if the power has valid targets before activating
                if power_name == "rescue" and not player.discard_pile:
                    should_activate = False
                elif power_name == "discard" and not player.hand:
                    should_activate = False
                elif power_name == "cycle" and not player.hand:
                    should_activate = False
                elif power_name == "exchange" and (not player.hand or not player.discard_pile):
                    should_activate = False
                elif power_name == "replay" and not player.play_pile:
                    should_activate = False
                elif power_name == "poison":
                    has_target = any(
                        len(p.draw_deck) > 0
                        for i, p in enumerate(game_state.players)
                        if i != player_index
                    )
                    if not has_target:
                        should_activate = False
                elif power_name == "kill":
                    has_target = any(
                        len(p.play_pile) > 0
                        for i, p in enumerate(game_state.players)
                        if i != player_index
                    )
                    if not has_target:
                        should_activate = False
                elif power_name == "avalanche" and len(player.hand) < 4:
                    should_activate = False

                choice_action["choice"] = "activate" if should_activate else "decline"
            elif pending.phase == "choose_target":
                choice_action["choice"] = "activate"
                power_name = pending.power_name

                # Make a reasonable target choice based on the power type
                player_target_powers = {
                    "poison", "copy", "draw", "kill", "recycle",
                    "score", "battle", "assimilate", "utilize",
                }
                card_from_hand_powers = {"discard", "cycle", "exchange", "avalanche"}
                card_from_discard_powers = {"rescue"}
                card_from_play_pile_powers = {"replay"}

                if power_name in player_target_powers:
                    # Choose a valid target player (first available opponent)
                    for i, p in enumerate(game_state.players):
                        if i != player_index:
                            # Basic validity check based on power
                            if power_name == "poison" and len(p.draw_deck) > 0:
                                choice_action["target_player_index"] = i
                                break
                            elif power_name == "copy" and len(p.play_pile) > 0:
                                choice_action["target_player_index"] = i
                                break
                            elif power_name == "draw" and len(p.draw_deck) > 0:
                                choice_action["target_player_index"] = i
                                break
                            elif power_name == "kill" and len(p.play_pile) > 0:
                                choice_action["target_player_index"] = i
                                break
                            elif power_name == "recycle" and len(p.discard_pile) > 0:
                                choice_action["target_player_index"] = i
                                break
                            elif power_name == "score":
                                choice_action["target_player_index"] = i
                                break
                            elif power_name == "battle" and len(p.draw_deck) >= 3:
                                choice_action["target_player_index"] = i
                                break
                            elif power_name == "assimilate" and len(p.draw_deck) > 0:
                                choice_action["target_player_index"] = i
                                break
                            elif power_name == "utilize" and len(p.hand) >= 2:
                                choice_action["target_player_index"] = i
                                break
                    # If no valid target found, decline
                    if "target_player_index" not in choice_action:
                        choice_action["choice"] = "decline"

                elif power_name in card_from_hand_powers:
                    # Choose the first card from hand
                    if player.hand:
                        choice_action["card_id"] = player.hand[0].card_id
                    else:
                        choice_action["choice"] = "decline"

                elif power_name in card_from_discard_powers:
                    # Choose the first card from discard pile
                    if player.discard_pile:
                        choice_action["card_id"] = player.discard_pile[0].card_id
                    else:
                        choice_action["choice"] = "decline"

                elif power_name in card_from_play_pile_powers:
                    # Choose the first card from play pile
                    if player.play_pile:
                        choice_action["card_id"] = player.play_pile[0].card_id
                    else:
                        choice_action["choice"] = "decline"

                elif power_name == "freeze":
                    # Freeze a common power
                    choice_action["power_to_freeze"] = "go"

                elif power_name == "process":
                    # Choose first 2 cards from hand to place under draw deck
                    if len(player.hand) >= 2:
                        choice_action["card_ids"] = [player.hand[0].card_id, player.hand[1].card_id]
                    elif player.hand:
                        choice_action["card_ids"] = [player.hand[0].card_id]
                    else:
                        choice_action["choice"] = "decline"

                elif power_name == "scan":
                    # Place cards on top in current order
                    choice_action["placement"] = "top"
                    choice_action["order"] = []

                elif power_name == "toxin":
                    # Choose the first revealed card
                    if hasattr(pending, 'toxin_revealed') and pending.toxin_revealed:
                        choice_action["card_id"] = pending.toxin_revealed[0][1].card_id
                    else:
                        choice_action["choice"] = "decline"

                else:
                    # Unknown power — decline
                    choice_action["choice"] = "decline"

            # Process the power choice through the engine
            result = self._game_engine.process_action(
                game_id, player.player_id, choice_action
            )
            if isinstance(result, list):
                all_events.extend(result)
            else:
                # Power choice failed — log and break
                logger.warning(
                    "AI power choice failed for player %d: %s",
                    player.player_id, result
                )
                # Force clear the pending power to avoid infinite loop
                game_state.pending_power = None
                break

        return all_events

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
