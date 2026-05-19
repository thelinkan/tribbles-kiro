"""Tests for the WebSocket protocol messages and handler modules."""

import json
import pytest

import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from protocol.messages import (
    ClientMessageType,
    ServerMessageType,
    encode_message,
    decode_message,
    error_message,
)


class TestEncodeMessage:
    """Tests for encode_message helper."""

    def test_encode_produces_valid_json(self):
        result = encode_message("login", {"username": "alice", "password": "secret"})
        data = json.loads(result)
        assert data["type"] == "login"
        assert data["payload"]["username"] == "alice"
        assert data["payload"]["password"] == "secret"

    def test_encode_empty_payload(self):
        result = encode_message("draw_card", {})
        data = json.loads(result)
        assert data["type"] == "draw_card"
        assert data["payload"] == {}


class TestDecodeMessage:
    """Tests for decode_message helper."""

    def test_decode_valid_message(self):
        raw = json.dumps({"type": "login", "payload": {"username": "bob"}})
        msg_type, payload = decode_message(raw)
        assert msg_type == "login"
        assert payload == {"username": "bob"}

    def test_decode_missing_payload_defaults_to_empty(self):
        raw = json.dumps({"type": "draw_card"})
        msg_type, payload = decode_message(raw)
        assert msg_type == "draw_card"
        assert payload == {}

    def test_decode_invalid_json_raises(self):
        with pytest.raises(ValueError, match="Invalid JSON"):
            decode_message("not json at all")

    def test_decode_non_object_raises(self):
        with pytest.raises(ValueError, match="must be a JSON object"):
            decode_message(json.dumps([1, 2, 3]))

    def test_decode_missing_type_raises(self):
        with pytest.raises(ValueError, match="missing 'type' field"):
            decode_message(json.dumps({"payload": {}}))

    def test_decode_invalid_payload_type_raises(self):
        with pytest.raises(ValueError, match="'payload' must be a JSON object"):
            decode_message(json.dumps({"type": "login", "payload": "not a dict"}))


class TestErrorMessage:
    """Tests for error_message helper."""

    def test_error_message_format(self):
        result = error_message("auth_failed", "Invalid credentials")
        data = json.loads(result)
        assert data["type"] == ServerMessageType.ERROR
        assert data["payload"]["code"] == "auth_failed"
        assert data["payload"]["message"] == "Invalid credentials"


class TestMessageTypeConstants:
    """Tests that message type constants are defined correctly."""

    def test_client_message_types_are_strings(self):
        assert ClientMessageType.REGISTER == "register"
        assert ClientMessageType.LOGIN == "login"
        assert ClientMessageType.PLAY_CARD == "play_card"
        assert ClientMessageType.DRAW_CARD == "draw_card"
        assert ClientMessageType.POWER_CHOICE == "power_choice"
        assert ClientMessageType.ACCEPT_DRAW == "accept_draw"
        assert ClientMessageType.CREATE_GAME == "create_game"
        assert ClientMessageType.JOIN_GAME == "join_game"
        assert ClientMessageType.START_GAME == "start_game"
        assert ClientMessageType.WATCH_GAME == "watch_game"
        assert ClientMessageType.LEAVE_SPECTATE == "leave_spectate"
        assert ClientMessageType.RECONNECT == "reconnect"

    def test_server_message_types_are_strings(self):
        assert ServerMessageType.GAME_STATE_UPDATE == "game_state_update"
        assert ServerMessageType.PROMPT == "prompt"
        assert ServerMessageType.ROUND_END == "round_end"
        assert ServerMessageType.GAME_END == "game_end"
        assert ServerMessageType.ERROR == "error"
        assert ServerMessageType.DISCONNECT_NOTIFY == "disconnect_notify"
        assert ServerMessageType.RECONNECT_NOTIFY == "reconnect_notify"
        assert ServerMessageType.RECONNECT_STATE_SYNC == "reconnect_state_sync"
        assert ServerMessageType.SPECTATOR_STATE_UPDATE == "spectator_state_update"
        assert ServerMessageType.SPECTATOR_COUNT_UPDATE == "spectator_count_update"
