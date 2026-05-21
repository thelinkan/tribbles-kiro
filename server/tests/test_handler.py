"""Tests for the WebSocket message handler/router."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from protocol.handler import MessageHandler
from protocol.messages import ClientMessageType, ServerMessageType, encode_message


@pytest.fixture
def handler():
    """Create a handler with no services (tests basic routing/error handling)."""
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
        raw = json.dumps({"type": "unknown_type", "payload": {"token": "abc"}})
        result = await handler.handle_message(mock_websocket, raw)
        data = json.loads(result)
        assert data["type"] == ServerMessageType.ERROR
        # Without a valid token, it returns unauthorised for authenticated routes
        # But unknown_type is not in any route, so it returns unauthorised
        assert data["payload"]["code"] == "unauthorised"

    @pytest.mark.asyncio
    async def test_login_without_service_returns_not_implemented(
        self, handler, mock_websocket
    ):
        raw = json.dumps({"type": ClientMessageType.LOGIN, "payload": {"username": "a", "password": "b"}})
        result = await handler.handle_message(mock_websocket, raw)
        data = json.loads(result)
        assert data["type"] == ServerMessageType.ERROR
        assert data["payload"]["code"] == "not_implemented"

    @pytest.mark.asyncio
    async def test_register_without_service_returns_not_implemented(
        self, handler, mock_websocket
    ):
        raw = json.dumps({"type": ClientMessageType.REGISTER, "payload": {"username": "a", "password": "b", "email": "a@b.c"}})
        result = await handler.handle_message(mock_websocket, raw)
        data = json.loads(result)
        assert data["type"] == ServerMessageType.ERROR
        assert data["payload"]["code"] == "not_implemented"

    @pytest.mark.asyncio
    async def test_register_missing_fields_returns_invalid_payload(self, mock_websocket):
        """Register with missing fields returns invalid_payload error."""
        mock_auth = AsyncMock()
        handler = MessageHandler(auth_service=mock_auth)

        raw = json.dumps({"type": ClientMessageType.REGISTER, "payload": {"username": "a"}})
        result = await handler.handle_message(mock_websocket, raw)
        data = json.loads(result)
        assert data["type"] == ServerMessageType.ERROR
        assert data["payload"]["code"] == "invalid_payload"

    @pytest.mark.asyncio
    async def test_login_missing_fields_returns_invalid_payload(self, mock_websocket):
        """Login with missing fields returns invalid_payload error."""
        mock_auth = AsyncMock()
        handler = MessageHandler(auth_service=mock_auth)

        raw = json.dumps({"type": ClientMessageType.LOGIN, "payload": {"username": "a"}})
        result = await handler.handle_message(mock_websocket, raw)
        data = json.loads(result)
        assert data["type"] == ServerMessageType.ERROR
        assert data["payload"]["code"] == "invalid_payload"

    @pytest.mark.asyncio
    async def test_authenticated_route_without_token_returns_unauthorised(
        self, handler, mock_websocket
    ):
        """Authenticated routes without a token return unauthorised."""
        raw = json.dumps({"type": ClientMessageType.LIST_DECKS, "payload": {}})
        result = await handler.handle_message(mock_websocket, raw)
        data = json.loads(result)
        assert data["type"] == ServerMessageType.ERROR
        assert data["payload"]["code"] == "unauthorised"

    @pytest.mark.asyncio
    async def test_bytes_message_is_decoded(self, handler, mock_websocket):
        raw = json.dumps({"type": ClientMessageType.LOGIN, "payload": {"username": "a", "password": "b"}}).encode("utf-8")
        result = await handler.handle_message(mock_websocket, raw)
        # Should still route correctly (to not_implemented since no auth service)
        data = json.loads(result)
        assert data["type"] == ServerMessageType.ERROR
        assert data["payload"]["code"] == "not_implemented"

    @pytest.mark.asyncio
    async def test_successful_register(self, mock_websocket):
        """Successful registration returns register_success."""
        mock_auth = AsyncMock()
        mock_auth.register = AsyncMock(return_value=(42, None))
        handler = MessageHandler(auth_service=mock_auth)

        raw = json.dumps({
            "type": ClientMessageType.REGISTER,
            "payload": {"username": "alice", "password": "pass123", "email": "alice@test.com"},
        })
        result = await handler.handle_message(mock_websocket, raw)
        data = json.loads(result)
        assert data["type"] == "register_success"
        assert data["payload"]["player_id"] == 42

    @pytest.mark.asyncio
    async def test_successful_login(self, mock_websocket):
        """Successful login returns login_success with token."""
        mock_auth = AsyncMock()
        mock_auth.login = AsyncMock(return_value=("token123", None))
        mock_auth.validate_token = AsyncMock(return_value=(1, None))
        handler = MessageHandler(auth_service=mock_auth)

        raw = json.dumps({
            "type": ClientMessageType.LOGIN,
            "payload": {"username": "alice", "password": "pass123"},
        })
        result = await handler.handle_message(mock_websocket, raw)
        data = json.loads(result)
        assert data["type"] == "login_success"
        assert data["payload"]["token"] == "token123"
        assert data["payload"]["player_id"] == 1

    @pytest.mark.asyncio
    async def test_handler_exception_returns_internal_error(self, mock_websocket):
        """An exception in a handler returns internal_error."""
        mock_auth = AsyncMock()
        mock_auth.register = AsyncMock(side_effect=RuntimeError("Something broke"))
        handler = MessageHandler(auth_service=mock_auth)

        raw = json.dumps({
            "type": ClientMessageType.REGISTER,
            "payload": {"username": "a", "password": "b", "email": "c@d.e"},
        })
        result = await handler.handle_message(mock_websocket, raw)
        data = json.loads(result)
        assert data["type"] == ServerMessageType.ERROR
        assert data["payload"]["code"] == "internal_error"

    @pytest.mark.asyncio
    async def test_handle_disconnect_returns_player_id(self, mock_websocket):
        """handle_disconnect returns the player_id for an authenticated connection."""
        mock_auth = AsyncMock()
        mock_auth.login = AsyncMock(return_value=("token123", None))
        mock_auth.validate_token = AsyncMock(return_value=(7, None))
        handler = MessageHandler(auth_service=mock_auth)

        # Login to establish the connection mapping
        raw = json.dumps({
            "type": ClientMessageType.LOGIN,
            "payload": {"username": "bob", "password": "pass"},
        })
        await handler.handle_message(mock_websocket, raw)

        # Now disconnect
        player_id = handler.handle_disconnect(mock_websocket)
        assert player_id == 7

    @pytest.mark.asyncio
    async def test_handle_disconnect_unknown_websocket_returns_none(self, handler, mock_websocket):
        """handle_disconnect returns None for an unknown websocket."""
        player_id = handler.handle_disconnect(mock_websocket)
        assert player_id is None
