"""WebSocket message router that dispatches incoming messages to services.

The MessageHandler parses incoming JSON messages, identifies the message type,
and routes them to the appropriate service handler method.
"""

import logging
from typing import Any, Callable, Awaitable, Optional

from websockets.asyncio.server import ServerConnection

from protocol.messages import (
    ClientMessageType,
    decode_message,
    error_message,
)

logger = logging.getLogger(__name__)

# Type alias for service handler functions
HandlerFunc = Callable[
    [ServerConnection, dict[str, Any]],
    Awaitable[Optional[str]],
]


class MessageHandler:
    """Routes incoming WebSocket messages to registered service handlers."""

    def __init__(self) -> None:
        self._routes: dict[str, HandlerFunc] = {}
        self._register_default_routes()

    def _register_default_routes(self) -> None:
        """Register placeholder routes for all known client message types."""
        known_types = [
            ClientMessageType.REGISTER,
            ClientMessageType.LOGIN,
            ClientMessageType.PLAY_CARD,
            ClientMessageType.DRAW_CARD,
            ClientMessageType.POWER_CHOICE,
            ClientMessageType.ACCEPT_DRAW,
            ClientMessageType.CREATE_GAME,
            ClientMessageType.JOIN_GAME,
            ClientMessageType.START_GAME,
            ClientMessageType.WATCH_GAME,
            ClientMessageType.LEAVE_SPECTATE,
            ClientMessageType.RECONNECT,
        ]
        for msg_type in known_types:
            self._routes[msg_type] = self._not_implemented_handler

    def register_handler(self, msg_type: str, handler: HandlerFunc) -> None:
        """Register a handler function for a specific message type.

        Args:
            msg_type: The client message type to handle.
            handler: An async function that receives the websocket and payload,
                     and returns an optional response string.
        """
        self._routes[msg_type] = handler

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

        handler = self._routes.get(msg_type)
        if handler is None:
            logger.warning(
                "Unknown message type '%s' from %s", msg_type, websocket.remote_address
            )
            return error_message(
                "unknown_message_type",
                f"Unknown message type: {msg_type}",
            )

        logger.debug(
            "Routing '%s' from %s", msg_type, websocket.remote_address
        )

        try:
            return await handler(websocket, payload)
        except Exception:
            logger.exception(
                "Error handling '%s' from %s", msg_type, websocket.remote_address
            )
            return error_message(
                "internal_error",
                "An internal server error occurred.",
            )

    @staticmethod
    async def _not_implemented_handler(
        websocket: ServerConnection,
        payload: dict[str, Any],
    ) -> str:
        """Placeholder handler for message types not yet implemented."""
        return error_message(
            "not_implemented",
            "This feature is not yet implemented.",
        )
