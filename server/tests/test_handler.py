"""Tests for the WebSocket message handler/router."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from protocol.handler import MessageHandler
from protocol.messages import ClientMessageType, ServerMessageType, encode_message


@pytest.fixture
def handler():
    return MessageHandler()


@pytest.fixture
def mock_websocket():
    ws = AsyncMock()
    ws.remote_address = ("127.0.0.1", 12345)
    return ws


class TestMessageHandler:
    """Tests for the MessageHandler routing logic."""

    @pytest.mark.asyncio
    async def test_invalid_json_returns_error(self, handler, mock_websocket):
        result = await handler.handle_message(mock_websocket, "not json")
        data = json.loads(result)
        assert data["type"] == ServerMessageType.ERROR
        assert data["payload"]["code"] == "invalid_message"

    @pytest.mark.asyncio
    async def test_unknown_message_type_returns_error(self, handler, mock_websocket):
        raw = json.dumps({"type": "unknown_type", "payload": {}})
        result = await handler.handle_message(mock_websocket, raw)
        data = json.loads(result)
        assert data["type"] == ServerMessageType.ERROR
        assert data["payload"]["code"] == "unknown_message_type"

    @pytest.mark.asyncio
    async def test_unimplemented_handler_returns_not_implemented(
        self, handler, mock_websocket
    ):
        raw = json.dumps({"type": ClientMessageType.LOGIN, "payload": {}})
        result = await handler.handle_message(mock_websocket, raw)
        data = json.loads(result)
        assert data["type"] == ServerMessageType.ERROR
        assert data["payload"]["code"] == "not_implemented"

    @pytest.mark.asyncio
    async def test_registered_handler_is_called(self, handler, mock_websocket):
        custom_handler = AsyncMock(
            return_value=encode_message("game_state_update", {"state": "ok"})
        )
        handler.register_handler(ClientMessageType.LOGIN, custom_handler)

        raw = json.dumps({"type": "login", "payload": {"username": "alice"}})
        result = await handler.handle_message(mock_websocket, raw)

        custom_handler.assert_called_once_with(
            mock_websocket, {"username": "alice"}
        )
        data = json.loads(result)
        assert data["type"] == "game_state_update"

    @pytest.mark.asyncio
    async def test_handler_exception_returns_internal_error(
        self, handler, mock_websocket
    ):
        async def failing_handler(ws, payload):
            raise RuntimeError("Something broke")

        handler.register_handler(ClientMessageType.LOGIN, failing_handler)

        raw = json.dumps({"type": "login", "payload": {}})
        result = await handler.handle_message(mock_websocket, raw)
        data = json.loads(result)
        assert data["type"] == ServerMessageType.ERROR
        assert data["payload"]["code"] == "internal_error"

    @pytest.mark.asyncio
    async def test_bytes_message_is_decoded(self, handler, mock_websocket):
        raw = json.dumps({"type": "login", "payload": {}}).encode("utf-8")
        result = await handler.handle_message(mock_websocket, raw)
        # Should still route correctly (to not_implemented placeholder)
        data = json.loads(result)
        assert data["type"] == ServerMessageType.ERROR
        assert data["payload"]["code"] == "not_implemented"

    @pytest.mark.asyncio
    async def test_handler_returning_none_returns_none(
        self, handler, mock_websocket
    ):
        async def silent_handler(ws, payload):
            return None

        handler.register_handler(ClientMessageType.DRAW_CARD, silent_handler)

        raw = json.dumps({"type": "draw_card", "payload": {}})
        result = await handler.handle_message(mock_websocket, raw)
        assert result is None
