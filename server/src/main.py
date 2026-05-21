"""Tribbles multiplayer card game server entry point.

Starts an asyncio WebSocket server that accepts client connections
and routes JSON messages to the appropriate service handlers.
Creates a database pool and instantiates all services on startup.
"""

import asyncio
import logging
import os
import signal
import sys
from typing import Dict, Optional

import aiomysql
from websockets.asyncio.server import serve, ServerConnection
from websockets.exceptions import ConnectionClosed

from auth.service import AuthService
from cards.repository import CardRepository
from decks.service import DeckService
from game.disconnection import DisconnectionManager
from game.engine import GameEngine
from game.spectator import SpectatorManager
from lobby.service import LobbyService
from protocol.handler import MessageHandler

logger = logging.getLogger(__name__)

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8765

# Database configuration defaults
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", "3306"))
DB_USER = os.environ.get("DB_USER", "tribbles")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "tribbles")
DB_NAME = os.environ.get("DB_NAME", "tribbles")


class TribbleServer:
    """Main WebSocket server for the Tribbles card game."""

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
        self.host = host
        self.port = port
        self.handler: Optional[MessageHandler] = None
        self._connected_clients: Dict[int, ServerConnection] = {}  # player_id -> websocket
        self._pool: Optional[aiomysql.Pool] = None

    async def _create_db_pool(self) -> aiomysql.Pool:
        """Create the aiomysql database connection pool."""
        pool = await aiomysql.create_pool(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            db=DB_NAME,
            autocommit=False,
            minsize=2,
            maxsize=10,
        )
        logger.info("Database connection pool created (%s@%s:%d/%s)", DB_USER, DB_HOST, DB_PORT, DB_NAME)
        return pool

    def _create_services(self, pool: aiomysql.Pool) -> MessageHandler:
        """Instantiate all services and create the message handler.

        Args:
            pool: The aiomysql connection pool.

        Returns:
            A fully wired MessageHandler instance.
        """
        auth_service = AuthService(pool)
        card_repository = CardRepository(pool)
        deck_service = DeckService(pool)
        lobby_service = LobbyService(pool)
        game_engine = GameEngine()
        disconnection_manager = DisconnectionManager()
        spectator_manager = SpectatorManager()

        handler = MessageHandler(
            auth_service=auth_service,
            card_repository=card_repository,
            deck_service=deck_service,
            lobby_service=lobby_service,
            game_engine=game_engine,
            disconnection_manager=disconnection_manager,
            spectator_manager=spectator_manager,
        )

        return handler

    async def handle_connection(self, websocket: ServerConnection) -> None:
        """Handle a new WebSocket client connection."""
        remote = websocket.remote_address
        logger.info("Client connected: %s", remote)

        try:
            async for raw_message in websocket:
                response = await self.handler.handle_message(websocket, raw_message)
                if response is not None:
                    await websocket.send(response)
        except ConnectionClosed:
            logger.info("Client disconnected: %s", remote)
        finally:
            # Handle disconnection tracking
            player_id = self.handler.handle_disconnect(websocket)
            if player_id is not None:
                self._connected_clients.pop(player_id, None)
                logger.info("Player %d disconnected", player_id)

    async def start(self) -> None:
        """Start the WebSocket server."""
        logger.info("Starting Tribbles server on %s:%d", self.host, self.port)

        # Create database pool and services
        self._pool = await self._create_db_pool()
        self.handler = self._create_services(self._pool)

        stop = asyncio.get_event_loop().create_future()

        # Handle graceful shutdown on SIGTERM/SIGINT
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, stop.set_result, None)
            except NotImplementedError:
                # Windows doesn't support add_signal_handler
                pass

        async with serve(self.handle_connection, self.host, self.port):
            logger.info("Server listening on ws://%s:%d", self.host, self.port)
            try:
                await stop
            except asyncio.CancelledError:
                pass

        # Cleanup
        if self._pool is not None:
            self._pool.close()
            await self._pool.wait_closed()
            logger.info("Database pool closed.")

        logger.info("Server shut down.")


def main() -> None:
    """Entry point for the Tribbles server."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    host = DEFAULT_HOST
    port = DEFAULT_PORT

    # Allow overriding host/port via command-line args
    if len(sys.argv) >= 2:
        host = sys.argv[1]
    if len(sys.argv) >= 3:
        port = int(sys.argv[2])

    server = TribbleServer(host=host, port=port)

    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        logger.info("Server interrupted by user.")


if __name__ == "__main__":
    main()
