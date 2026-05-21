## NetworkClient autoload singleton.
## Manages WebSocket connection to the game server, message serialisation/
## deserialisation, reconnection with exponential backoff, and session token
## storage. Emits signals for each server message type so that UI scenes can
## react to incoming data without polling.
extends Node

# ─── Signals ────────────────────────────────────────────────────────────────────
## Emitted when the WebSocket connection is established.
signal connected
## Emitted when the WebSocket connection is closed.
signal disconnected
## Emitted when a reconnection attempt starts.
signal reconnecting(attempt: int)
## Emitted when reconnection fails after all retries.
signal reconnection_failed

# Server → Client message signals
## Emitted on successful login; payload contains session token.
signal login_response(payload: Dictionary)
## Emitted on successful registration.
signal register_response(payload: Dictionary)
## Emitted when the server sends a game state update.
signal game_state_update(payload: Dictionary)
## Emitted when the server prompts the player for a choice.
signal prompt_received(payload: Dictionary)
## Emitted at end of round with score data.
signal round_end(payload: Dictionary)
## Emitted at end of game with final scores.
signal game_end(payload: Dictionary)
## Emitted when the server reports an error.
signal error_received(payload: Dictionary)
## Emitted when another player disconnects.
signal disconnect_notify(payload: Dictionary)
## Emitted when a player reconnects.
signal reconnect_notify(payload: Dictionary)
## Emitted on reconnection with full state sync.
signal reconnect_state_sync(payload: Dictionary)
## Emitted with spectator state updates.
signal spectator_state_update(payload: Dictionary)
## Emitted when spectator count changes.
signal spectator_count_update(payload: Dictionary)
## Emitted for lobby-related responses (game list, create/join confirmations).
signal lobby_response(payload: Dictionary)
## Emitted for deck-related responses.
signal deck_response(payload: Dictionary)
## Emitted for card catalogue responses.
signal card_response(payload: Dictionary)

# ─── Configuration ──────────────────────────────────────────────────────────────
## Maximum number of reconnection attempts before giving up.
const MAX_RECONNECT_ATTEMPTS: int = 8
## Initial delay in seconds before the first reconnection attempt.
const INITIAL_RECONNECT_DELAY: float = 1.0
## Maximum delay cap in seconds for exponential backoff.
const MAX_RECONNECT_DELAY: float = 30.0
## Multiplier applied to the delay after each failed attempt.
const BACKOFF_MULTIPLIER: float = 2.0

# ─── State ──────────────────────────────────────────────────────────────────────
## The WebSocket peer used for communication.
var _socket: WebSocketPeer = null
## The server URL to connect to (e.g., "ws://192.168.1.100:8080").
var _server_url: String = ""
## Session token received after successful login.
var session_token: String = ""
## Whether we are currently connected.
var is_connected: bool = false
## Whether a reconnection sequence is in progress.
var _is_reconnecting: bool = false
## Current reconnection attempt counter.
var _reconnect_attempt: int = 0
## Current reconnection delay in seconds.
var _reconnect_delay: float = INITIAL_RECONNECT_DELAY
## Timer used for reconnection backoff.
var _reconnect_timer: Timer = null
## Whether the user intentionally disconnected (suppress reconnection).
var _intentional_disconnect: bool = false
## Temporary storage for round_end payload (read by EndOfRoundScreen on _ready).
var round_end_data: Dictionary = {}
## Temporary storage for game_end payload (read by EndOfGameScreen on _ready).
var game_end_data: Dictionary = {}


# ─── Lifecycle ──────────────────────────────────────────────────────────────────

func _ready() -> void:
	_reconnect_timer = Timer.new()
	_reconnect_timer.one_shot = true
	_reconnect_timer.timeout.connect(_attempt_reconnect)
	add_child(_reconnect_timer)


func _process(_delta: float) -> void:
	if _socket == null:
		return

	_socket.poll()

	var state := _socket.get_ready_state()

	match state:
		WebSocketPeer.STATE_OPEN:
			if not is_connected:
				_on_connected()
			while _socket.get_available_packet_count() > 0:
				var packet := _socket.get_packet()
				var text := packet.get_string_from_utf8()
				_handle_message(text)
		WebSocketPeer.STATE_CLOSING:
			pass  # Wait for close to complete.
		WebSocketPeer.STATE_CLOSED:
			if is_connected:
				_on_disconnected()


# ─── Public API ─────────────────────────────────────────────────────────────────

## Connect to the game server at the given WebSocket URL.
## url: The full WebSocket URL, e.g. "ws://192.168.1.100:8080"
func connect_to_server(url: String) -> void:
	_server_url = url
	_intentional_disconnect = false
	_create_socket_and_connect()


## Disconnect from the server. Suppresses automatic reconnection.
func disconnect_from_server() -> void:
	_intentional_disconnect = true
	_is_reconnecting = false
	_reconnect_timer.stop()
	if _socket != null:
		_socket.close()
	session_token = ""


## Send a message to the server.
## msg_type: The message type string (e.g., "login", "play_card").
## payload: The payload dictionary for the message.
func send_message(msg_type: String, payload: Dictionary = {}) -> void:
	if _socket == null or _socket.get_ready_state() != WebSocketPeer.STATE_OPEN:
		push_warning("NetworkClient: Cannot send message, not connected.")
		return

	var message := {
		"type": msg_type,
		"payload": payload,
	}

	# Include session token in all messages after login (except login/register).
	if session_token != "" and msg_type != "login" and msg_type != "register":
		message["token"] = session_token

	var json_string := JSON.stringify(message)
	_socket.send_text(json_string)


## Returns true if the client is currently connected to the server.
func is_server_connected() -> bool:
	return is_connected


## Returns true if a reconnection attempt is in progress.
func is_reconnection_in_progress() -> bool:
	return _is_reconnecting


# ─── Private Methods ────────────────────────────────────────────────────────────

## Create a new WebSocketPeer and initiate connection.
func _create_socket_and_connect() -> void:
	_socket = WebSocketPeer.new()
	var err := _socket.connect_to_url(_server_url)
	if err != OK:
		push_error("NetworkClient: Failed to initiate connection to %s (error %d)" % [_server_url, err])
		_start_reconnection()


## Called when the WebSocket connection is established.
func _on_connected() -> void:
	is_connected = true
	_is_reconnecting = false
	_reconnect_attempt = 0
	_reconnect_delay = INITIAL_RECONNECT_DELAY
	connected.emit()


## Called when the WebSocket connection is lost.
func _on_disconnected() -> void:
	is_connected = false
	_socket = null
	disconnected.emit()

	if not _intentional_disconnect:
		_start_reconnection()


## Begin the reconnection sequence with exponential backoff.
func _start_reconnection() -> void:
	if _is_reconnecting:
		return
	_is_reconnecting = true
	_reconnect_attempt = 0
	_reconnect_delay = INITIAL_RECONNECT_DELAY
	_attempt_reconnect()


## Perform a single reconnection attempt.
func _attempt_reconnect() -> void:
	_reconnect_attempt += 1

	if _reconnect_attempt > MAX_RECONNECT_ATTEMPTS:
		_is_reconnecting = false
		reconnection_failed.emit()
		return

	reconnecting.emit(_reconnect_attempt)
	_create_socket_and_connect()

	# Schedule next attempt with exponential backoff in case this one fails.
	_reconnect_delay = minf(_reconnect_delay * BACKOFF_MULTIPLIER, MAX_RECONNECT_DELAY)
	_reconnect_timer.start(_reconnect_delay)


## Parse and route an incoming JSON message from the server.
func _handle_message(text: String) -> void:
	var json := JSON.new()
	var parse_result := json.parse(text)
	if parse_result != OK:
		push_error("NetworkClient: Failed to parse server message: %s" % text)
		return

	var data: Dictionary = json.data
	if not data.has("type"):
		push_error("NetworkClient: Message missing 'type' field: %s" % text)
		return

	var msg_type: String = data.get("type", "")
	var payload: Dictionary = data.get("payload", {})

	match msg_type:
		"login_response":
			if payload.has("token"):
				session_token = payload["token"]
			login_response.emit(payload)
		"register_response":
			register_response.emit(payload)
		"game_state_update":
			game_state_update.emit(payload)
		"prompt":
			prompt_received.emit(payload)
		"round_end":
			round_end_data = payload
			round_end.emit(payload)
		"game_end":
			game_end_data = payload
			game_end.emit(payload)
		"error":
			error_received.emit(payload)
		"disconnect_notify":
			disconnect_notify.emit(payload)
		"reconnect_notify":
			reconnect_notify.emit(payload)
		"reconnect_state_sync":
			reconnect_state_sync.emit(payload)
		"spectator_state_update":
			spectator_state_update.emit(payload)
		"spectator_count_update":
			spectator_count_update.emit(payload)
		"lobby_response":
			lobby_response.emit(payload)
		"deck_response":
			deck_response.emit(payload)
		"card_response":
			card_response.emit(payload)
		_:
			push_warning("NetworkClient: Unknown message type '%s'" % msg_type)
