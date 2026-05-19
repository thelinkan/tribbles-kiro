"""Tribbles multiplayer card game server entry point.

Starts an asyncio WebSocket server that accepts client connections
and routes JSON messages to the appropriate service handlers.
"""

import asyncio
import logging
import signal
import sys

from websockets.asyncio.server import serve, ServerConnection
from websockets.exceptions import ConnectionClosed

from protocol.handler import MessageHandler

logger = logging.getLogger(__name__)

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8765


class TribbleServer:
    """Main WebSocket server for the Tribbles card game."""

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
        self.host = host
        self.port = port
        self.handler = MessageHandler()
        self._connected_clients: set[ServerConnection] = set()

    async def handle_connection(self, websocket: ServerConnection) -> None:
        """Handle a new WebSocket client connection."""
        self._connected_clients.add(websocket)
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
            self._connected_clients.discard(websocket)

    async def start(self) -> None:
        """Start the WebSocket server."""
        logger.info("Starting Tribbles server on %s:%d", self.host, self.port)

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
