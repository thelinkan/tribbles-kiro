"""WebSocket message protocol definitions and JSON serialisation helpers.

All messages are JSON objects with a `type` field and a `payload` field.
This module defines the message type constants and provides helpers for
encoding/decoding messages.
"""

import json
from typing import Any


# --- Client → Server message types ---

class ClientMessageType:
    """Constants for messages sent from client to server."""

    REGISTER = "register"
    LOGIN = "login"
    PLAY_CARD = "play_card"
    DRAW_CARD = "draw_card"
    POWER_CHOICE = "power_choice"
    ACCEPT_DRAW = "accept_draw"
    CREATE_GAME = "create_game"
    JOIN_GAME = "join_game"
    START_GAME = "start_game"
    WATCH_GAME = "watch_game"
    LEAVE_SPECTATE = "leave_spectate"
    RECONNECT = "reconnect"


# --- Server → Client message types ---

class ServerMessageType:
    """Constants for messages sent from server to client."""

    GAME_STATE_UPDATE = "game_state_update"
    PROMPT = "prompt"
    ROUND_END = "round_end"
    GAME_END = "game_end"
    ERROR = "error"
    DISCONNECT_NOTIFY = "disconnect_notify"
    RECONNECT_NOTIFY = "reconnect_notify"
    RECONNECT_STATE_SYNC = "reconnect_state_sync"
    SPECTATOR_STATE_UPDATE = "spectator_state_update"
    SPECTATOR_COUNT_UPDATE = "spectator_count_update"


# --- Serialisation helpers ---

def encode_message(msg_type: str, payload: dict[str, Any]) -> str:
    """Encode a message type and payload into a JSON string.

    Args:
        msg_type: The message type constant.
        payload: The message payload dictionary.

    Returns:
        A JSON-encoded string with `type` and `payload` fields.
    """
    return json.dumps({"type": msg_type, "payload": payload})


def decode_message(raw: str) -> tuple[str, dict[str, Any]]:
    """Decode a raw JSON string into a message type and payload.

    Args:
        raw: The raw JSON string received from a WebSocket.

    Returns:
        A tuple of (message_type, payload_dict).

    Raises:
        ValueError: If the message is not valid JSON or missing required fields.
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e}") from e

    if not isinstance(data, dict):
        raise ValueError("Message must be a JSON object")

    msg_type = data.get("type")
    if msg_type is None:
        raise ValueError("Message missing 'type' field")

    payload = data.get("payload", {})
    if not isinstance(payload, dict):
        raise ValueError("Message 'payload' must be a JSON object")

    return msg_type, payload


def error_message(code: str, message: str) -> str:
    """Create an error response message.

    Args:
        code: A machine-readable error code.
        message: A human-readable error description.

    Returns:
        A JSON-encoded error message string.
    """
    return encode_message(
        ServerMessageType.ERROR,
        {"code": code, "message": message},
    )
