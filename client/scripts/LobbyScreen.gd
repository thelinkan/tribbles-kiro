## LobbyScreen — game lobby with two-category game list and actions.
## Displays waiting sessions (joinable) and active sessions (watchable).
## Provides Create Game, Join Game, and Watch Game functionality.
## Validates deck selection (minimum 35 cards) before creating or joining.
extends Control

# ─── Constants ──────────────────────────────────────────────────────────────────
## Minimum number of cards required for a deck to be used in a game.
const MINIMUM_DECK_SIZE: int = 35
## Minimum player count for a game session.
const MIN_PLAYER_COUNT: int = 4
## Maximum player count for a game session.
const MAX_PLAYER_COUNT: int = 8

# ─── Node References ────────────────────────────────────────────────────────────
@onready var title_label: Label = %TitleLabel
@onready var waiting_games_list: VBoxContainer = %WaitingGamesList
@onready var active_games_list: VBoxContainer = %ActiveGamesList
@onready var deck_selector: OptionButton = %DeckSelector
@onready var player_count_spin: SpinBox = %PlayerCountSpin
@onready var create_button: Button = %CreateButton
@onready var join_button: Button = %JoinButton
@onready var watch_button: Button = %WatchButton
@onready var back_button: Button = %BackButton
@onready var error_label: Label = %ErrorLabel
@onready var session_details_label: Label = %SessionDetailsLabel

# ─── State ──────────────────────────────────────────────────────────────────────
## Cached list of waiting game sessions from the server.
var _waiting_sessions: Array = []
## Cached list of active game sessions from the server.
var _active_sessions: Array = []
## Cached list of player decks: [{deck_id, deck_name, card_count}, ...]
var _player_decks: Array = []
## Currently selected waiting session ID (for join).
var _selected_waiting_session_id: String = ""
## Currently selected active session ID (for watch).
var _selected_active_session_id: String = ""


# ─── Lifecycle ──────────────────────────────────────────────────────────────────

func _ready() -> void:
	title_label.text = tr("UI_LOBBY")

	# Configure player count spinner.
	player_count_spin.min_value = MIN_PLAYER_COUNT
	player_count_spin.max_value = MAX_PLAYER_COUNT
	player_count_spin.value = MIN_PLAYER_COUNT
	player_count_spin.step = 1

	# Set localised button text.
	create_button.text = tr("UI_LOBBY_CREATE_GAME")
	join_button.text = tr("UI_LOBBY_JOIN_GAME")
	watch_button.text = tr("UI_LOBBY_WATCH_GAME")

	# Connect UI signals.
	create_button.pressed.connect(_on_create_pressed)
	join_button.pressed.connect(_on_join_pressed)
	watch_button.pressed.connect(_on_watch_pressed)
	back_button.pressed.connect(_on_back_pressed)
	deck_selector.item_selected.connect(_on_deck_selected)

	# Connect network signals.
	NetworkClient.lobby_response.connect(_on_lobby_response)
	NetworkClient.deck_response.connect(_on_deck_response)
	NetworkClient.error_received.connect(_on_error_received)

	# Initial UI state.
	error_label.visible = false
	session_details_label.text = ""
	join_button.disabled = true
	watch_button.disabled = true

	# Request game lists and player decks from server.
	_request_game_lists()
	_request_player_decks()


# ─── Server Requests ────────────────────────────────────────────────────────────

## Request the current game lists from the server.
func _request_game_lists() -> void:
	NetworkClient.send_message("list_games", {})


## Request the player's deck list from the server.
func _request_player_decks() -> void:
	NetworkClient.send_message("list_decks", {})


# ─── Deck Validation ───────────────────────────────────────────────────────────

## Returns the currently selected deck's card count, or -1 if no deck selected.
func _get_selected_deck_card_count() -> int:
	var idx := deck_selector.selected
	if idx < 0 or idx >= _player_decks.size():
		return -1
	return _player_decks[idx].get("card_count", _player_decks[idx].get("total_card_count", 0))


## Returns the currently selected deck ID, or empty string if none selected.
func _get_selected_deck_id() -> String:
	var idx := deck_selector.selected
	if idx < 0 or idx >= _player_decks.size():
		return ""
	return str(_player_decks[idx].get("deck_id", ""))


## Check if the selected deck meets the minimum card count requirement.
func _is_deck_valid_for_game() -> bool:
	var count := _get_selected_deck_card_count()
	return count >= MINIMUM_DECK_SIZE


# ─── UI Builders ────────────────────────────────────────────────────────────────

## Rebuild the waiting games list UI.
func _rebuild_waiting_games_ui() -> void:
	for child in waiting_games_list.get_children():
		child.queue_free()

	if _waiting_sessions.is_empty():
		var empty_label := Label.new()
		empty_label.text = "—"
		waiting_games_list.add_child(empty_label)
		return

	for session in _waiting_sessions:
		var session_id: String = str(session.get("session_id", ""))
		var player_count: int = session.get("player_count", 0)
		var players_joined: int = session.get("players_joined", 0)

		var btn := Button.new()
		btn.text = "%s — %d/%d players" % [session_id, players_joined, player_count]
		btn.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		btn.pressed.connect(_on_waiting_session_selected.bind(session_id, session))
		waiting_games_list.add_child(btn)


## Rebuild the active games list UI.
func _rebuild_active_games_ui() -> void:
	for child in active_games_list.get_children():
		child.queue_free()

	if _active_sessions.is_empty():
		var empty_label := Label.new()
		empty_label.text = "—"
		active_games_list.add_child(empty_label)
		return

	for session in _active_sessions:
		var session_id: String = str(session.get("session_id", ""))
		var player_count: int = session.get("player_count", 0)
		var players_joined: int = session.get("players_joined", 0)

		var btn := Button.new()
		btn.text = "%s — %d/%d players" % [session_id, players_joined, player_count]
		btn.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		btn.pressed.connect(_on_active_session_selected.bind(session_id, session))
		active_games_list.add_child(btn)


## Rebuild the deck selector dropdown.
func _rebuild_deck_selector() -> void:
	deck_selector.clear()
	for deck in _player_decks:
		var deck_name: String = deck.get("deck_name", "Unnamed")
		var card_count: int = deck.get("card_count", deck.get("total_card_count", 0))
		var suffix := " (%d cards)" % card_count
		if card_count < MINIMUM_DECK_SIZE:
			suffix += " ⚠"
		deck_selector.add_item(deck_name + suffix)
	# Auto-select the first deck if available.
	if deck_selector.item_count > 0:
		deck_selector.selected = 0


## Display session details for the selected session.
func _show_session_details(session: Dictionary) -> void:
	var session_id: String = str(session.get("session_id", ""))
	var player_count: int = session.get("player_count", 0)
	var players_joined: int = session.get("players_joined", 0)
	session_details_label.text = "Session: %s | Players: %d/%d" % [
		session_id, players_joined, player_count
	]


# ─── Session Selection ──────────────────────────────────────────────────────────

## Called when a waiting session is selected from the list.
func _on_waiting_session_selected(session_id: String, session: Dictionary) -> void:
	_selected_waiting_session_id = session_id
	_selected_active_session_id = ""
	join_button.disabled = false
	watch_button.disabled = true
	_show_session_details(session)


## Called when an active session is selected from the list.
func _on_active_session_selected(session_id: String, session: Dictionary) -> void:
	_selected_active_session_id = session_id
	_selected_waiting_session_id = ""
	join_button.disabled = true
	watch_button.disabled = false
	_show_session_details(session)


## Called when a deck is selected from the dropdown.
func _on_deck_selected(_index: int) -> void:
	# Clear any previous error when deck selection changes.
	error_label.visible = false


# ─── Action Handlers ────────────────────────────────────────────────────────────

## Create Game: validate deck, send create_game message.
func _on_create_pressed() -> void:
	error_label.visible = false

	var deck_id := _get_selected_deck_id()
	if deck_id == "":
		_show_error("Select a deck first.")
		return

	if not _is_deck_valid_for_game():
		_show_error(tr("UI_ERROR_DECK_TOO_SMALL"))
		return

	var player_count := int(player_count_spin.value)
	NetworkClient.send_message("create_game", {
		"deck_id": deck_id,
		"player_count": player_count,
	})


## Join Game: validate deck and session selection, send join_game message.
func _on_join_pressed() -> void:
	error_label.visible = false

	if _selected_waiting_session_id == "":
		_show_error("Select a waiting game to join.")
		return

	var deck_id := _get_selected_deck_id()
	if deck_id == "":
		_show_error("Select a deck first.")
		return

	if not _is_deck_valid_for_game():
		_show_error(tr("UI_ERROR_DECK_TOO_SMALL"))
		return

	NetworkClient.send_message("join_game", {
		"session_id": _selected_waiting_session_id,
		"deck_id": deck_id,
	})


## Watch Game: send watch_game message for selected active session.
func _on_watch_pressed() -> void:
	error_label.visible = false

	if _selected_active_session_id == "":
		_show_error("Select an active game to watch.")
		return

	NetworkClient.send_message("watch_game", {
		"session_id": _selected_active_session_id,
	})


## Navigate back to the main menu.
func _on_back_pressed() -> void:
	get_tree().change_scene_to_file("res://scenes/MainMenu.tscn")


# ─── Error Display ──────────────────────────────────────────────────────────────

## Show an error message to the player.
func _show_error(message: String) -> void:
	error_label.text = message
	error_label.visible = true


# ─── Network Response Handlers ──────────────────────────────────────────────────

## Handle lobby-related responses from the server.
func _on_lobby_response(payload: Dictionary) -> void:
	var action: String = payload.get("action", "")
	match action:
		"game_list":
			_waiting_sessions = payload.get("waiting", [])
			_active_sessions = payload.get("active", [])
			_rebuild_waiting_games_ui()
			_rebuild_active_games_ui()
		"game_created":
			# Refresh game lists after creating a game.
			_request_game_lists()
		"game_joined":
			# Navigate to game table when successfully joined.
			get_tree().change_scene_to_file("res://scenes/GameTable.tscn")
		"game_started":
			# Navigate to game table when game starts.
			get_tree().change_scene_to_file("res://scenes/GameTable.tscn")
		"watch_started":
			# Navigate to spectator view when watching.
			get_tree().change_scene_to_file("res://scenes/SpectatorView.tscn")


## Handle deck-related responses from the server.
func _on_deck_response(payload: Dictionary) -> void:
	var action: String = payload.get("action", "")
	match action:
		"deck_list":
			_player_decks = payload.get("decks", [])
			_rebuild_deck_selector()


## Handle error responses from the server.
func _on_error_received(payload: Dictionary) -> void:
	var error_code: String = payload.get("code", "")
	var error_message: String = ""

	match error_code:
		"session_full":
			error_message = tr("UI_ERROR_SESSION_FULL")
		"game_started":
			error_message = tr("UI_ERROR_GAME_STARTED")
		"invalid_player_count":
			error_message = tr("UI_ERROR_INVALID_PLAYER_COUNT")
		"deck_too_small":
			error_message = tr("UI_ERROR_DECK_TOO_SMALL")
		_:
			error_message = payload.get("message", "An error occurred.")

	_show_error(error_message)
