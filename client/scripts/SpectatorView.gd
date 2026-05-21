## SpectatorView — read-only game table for spectators.
## Displays all public game information (play piles, discard piles, draw deck
## counts, scores, sequence, direction, active player) without hand contents.
## No action buttons are available. Provides a Leave button to exit spectating.
## Listens for spectator_state_update messages from NetworkClient.
extends Control

# ─── Constants ──────────────────────────────────────────────────────────────────
## Positions around the table for up to 8 players (normalised 0–1 coordinates).
const TABLE_POSITIONS: Array[Vector2] = [
	Vector2(0.5, 0.85),   # 0: bottom centre
	Vector2(0.15, 0.70),  # 1: bottom-left
	Vector2(0.05, 0.40),  # 2: left
	Vector2(0.15, 0.15),  # 3: top-left
	Vector2(0.40, 0.05),  # 4: top-centre-left
	Vector2(0.60, 0.05),  # 5: top-centre-right
	Vector2(0.85, 0.15),  # 6: top-right
	Vector2(0.95, 0.40),  # 7: right
]

## Card denomination display names.
const DENOMINATION_NAMES: Dictionary = {
	1: "1",
	10: "10",
	100: "100",
	1000: "1,000",
	10000: "10,000",
	100000: "100,000",
}

# ─── Node References ────────────────────────────────────────────────────────────
@onready var game_info_panel: VBoxContainer = %GameInfoPanel
@onready var spectating_label: Label = %SpectatingLabel
@onready var sequence_label: Label = %SequenceLabel
@onready var direction_label: Label = %DirectionLabel
@onready var round_label: Label = %RoundLabel
@onready var spectator_count_label: Label = %SpectatorCountLabel
@onready var player_positions: Control = %PlayerPositions
@onready var leave_button: Button = %LeaveButton
@onready var enlarged_card_panel: PanelContainer = %EnlargedCardPanel
@onready var enlarged_card_label: Label = %EnlargedCardLabel

# ─── State ──────────────────────────────────────────────────────────────────────
## The spectator game state received from the server.
var _game_state: Dictionary = {}
## List of player position UI nodes (created dynamically).
var _player_nodes: Array[Control] = []
## Current spectator count.
var _spectator_count: int = 0
## The session ID being spectated.
var _session_id: String = ""


# ─── Lifecycle ──────────────────────────────────────────────────────────────────

func _ready() -> void:
	# Set localised text.
	spectating_label.text = tr("UI_LOBBY_WATCH_GAME")
	leave_button.text = tr("UI_LOGOUT")  # Reuse "Leave" concept.

	# Connect UI signals.
	leave_button.pressed.connect(_on_leave_pressed)

	# Connect network signals.
	NetworkClient.spectator_state_update.connect(_on_spectator_state_update)
	NetworkClient.spectator_count_update.connect(_on_spectator_count_update)
	NetworkClient.game_end.connect(_on_game_end)

	# Initial UI state.
	enlarged_card_panel.visible = false
	spectator_count_label.text = ""


# ─── Network Handlers ───────────────────────────────────────────────────────────

## Handle spectator_state_update messages from the server.
func _on_spectator_state_update(payload: Dictionary) -> void:
	_game_state = payload
	_session_id = payload.get("session_id", _session_id)
	_update_game_info()
	_update_player_positions()


## Handle spectator_count_update messages.
func _on_spectator_count_update(payload: Dictionary) -> void:
	_spectator_count = int(payload.get("spectator_count", 0))
	_update_spectator_count_display()


## Handle game_end: navigate to end-of-game screen.
func _on_game_end(_payload: Dictionary) -> void:
	get_tree().change_scene_to_file("res://scenes/EndOfGameScreen.tscn")


# ─── UI Updates ─────────────────────────────────────────────────────────────────

## Update the central game info panel.
func _update_game_info() -> void:
	var seq: int = _game_state.get("current_sequence", 1)
	var direction: int = _game_state.get("direction", 1)
	var round_num: int = _game_state.get("round_number", 1)

	sequence_label.text = "%s: %s" % [tr("UI_GAME_SEQUENCE"), DENOMINATION_NAMES.get(seq, str(seq))]

	if direction == 1:
		direction_label.text = "%s: %s" % [tr("UI_GAME_DIRECTION_CW"), "→"]
	else:
		direction_label.text = "%s: %s" % [tr("UI_GAME_DIRECTION_CCW"), "←"]

	round_label.text = "%s: %d" % [tr("UI_GAME_ROUND"), round_num]
	_update_spectator_count_display()


## Update the spectator count display.
func _update_spectator_count_display() -> void:
	if _spectator_count > 0:
		spectator_count_label.text = "%s: %d" % [tr("UI_GAME_SPECTATORS"), _spectator_count]
		spectator_count_label.visible = true
	else:
		spectator_count_label.visible = false


## Rebuild all player position nodes around the table.
func _update_player_positions() -> void:
	# Clear existing player nodes.
	for node in _player_nodes:
		if is_instance_valid(node):
			node.queue_free()
	_player_nodes.clear()

	var players: Array = _game_state.get("players", [])
	if players.is_empty():
		return

	var active_player_id: int = int(_game_state.get("active_player_id", -1))
	var viewport_size := get_viewport_rect().size

	for i in range(players.size()):
		var player_data: Dictionary = players[i]
		var pos_index: int = i % TABLE_POSITIONS.size()
		var table_pos: Vector2 = TABLE_POSITIONS[pos_index]

		var player_node := _create_player_position_node(player_data, active_player_id)
		player_node.position = Vector2(
			table_pos.x * viewport_size.x - 80.0,
			table_pos.y * viewport_size.y - 50.0
		)
		player_positions.add_child(player_node)
		_player_nodes.append(player_node)


## Create a single player position UI node for spectator view.
func _create_player_position_node(player_data: Dictionary, active_player_id: int) -> Control:
	var player_id: int = int(player_data.get("player_id", 0))
	var username: String = player_data.get("username", "Player")
	var score: int = int(player_data.get("cumulative_score", 0))
	var draw_count: int = int(player_data.get("draw_deck_count", 0))
	var is_active: bool = (player_id == active_player_id)
	var is_disconnected: bool = player_data.get("is_disconnected", false)
	var is_ai_sub: bool = player_data.get("ai_substitute_active", false)

	var container := VBoxContainer.new()
	container.custom_minimum_size = Vector2(160, 100)

	# Username label with active indicator.
	var name_label := Label.new()
	var display_name := username
	if is_active:
		display_name = "▶ " + display_name
	if is_disconnected:
		display_name += " [%s]" % tr("UI_PLAYER_DISCONNECTED")
	elif is_ai_sub:
		display_name += " [%s]" % tr("UI_AI_SUBSTITUTE")
	name_label.text = display_name
	name_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	container.add_child(name_label)

	# Score label.
	var score_label := Label.new()
	score_label.text = "%s: %d" % [tr("UI_GAME_SCORE"), score]
	score_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	container.add_child(score_label)

	# Piles row.
	var piles_row := HBoxContainer.new()
	piles_row.alignment = BoxContainer.ALIGNMENT_CENTER

	# Draw deck (face-down with count).
	var draw_btn := Button.new()
	draw_btn.text = "%s\n(%d)" % [tr("UI_GAME_DRAW_DECK"), draw_count]
	draw_btn.custom_minimum_size = Vector2(50, 40)
	draw_btn.mouse_entered.connect(_on_pile_hover_entered.bind("draw", player_data))
	draw_btn.mouse_exited.connect(_on_pile_hover_exited)
	piles_row.add_child(draw_btn)

	# Play pile (top card visible).
	var play_pile_top: Array = player_data.get("play_pile_top", [])
	var play_btn := Button.new()
	if not play_pile_top.is_empty():
		var top_card: Dictionary = play_pile_top[0] if play_pile_top[0] is Dictionary else {}
		play_btn.text = _format_card_short(top_card)
	else:
		play_btn.text = tr("UI_GAME_PLAY_PILE")
	play_btn.custom_minimum_size = Vector2(50, 40)
	play_btn.mouse_entered.connect(_on_pile_hover_entered.bind("play", player_data))
	play_btn.mouse_exited.connect(_on_pile_hover_exited)
	piles_row.add_child(play_btn)

	# Discard pile (top card visible).
	var discard_pile_top: Array = player_data.get("discard_pile_top", [])
	var discard_btn := Button.new()
	if not discard_pile_top.is_empty():
		var top_card: Dictionary = discard_pile_top[0] if discard_pile_top[0] is Dictionary else {}
		discard_btn.text = _format_card_short(top_card)
	else:
		discard_btn.text = tr("UI_GAME_DISCARD_PILE")
	discard_btn.custom_minimum_size = Vector2(50, 40)
	discard_btn.mouse_entered.connect(_on_pile_hover_entered.bind("discard", player_data))
	discard_btn.mouse_exited.connect(_on_pile_hover_exited)
	piles_row.add_child(discard_btn)

	container.add_child(piles_row)
	return container


# ─── Pile Hover ─────────────────────────────────────────────────────────────────

## Show enlarged card when hovering over a pile.
func _on_pile_hover_entered(pile_type: String, player_data: Dictionary) -> void:
	var top_card: Dictionary = {}

	match pile_type:
		"play":
			var pile: Array = player_data.get("play_pile_top", [])
			if not pile.is_empty():
				top_card = pile[0] if pile[0] is Dictionary else {}
		"discard":
			var pile: Array = player_data.get("discard_pile_top", [])
			if not pile.is_empty():
				top_card = pile[0] if pile[0] is Dictionary else {}
		"draw":
			var count: int = int(player_data.get("draw_deck_count", 0))
			enlarged_card_label.text = "%s\n%s: %d" % [
				tr("UI_GAME_DRAW_DECK"),
				"Cards",
				count,
			]
			enlarged_card_panel.visible = true
			return

	if top_card.is_empty():
		enlarged_card_panel.visible = false
		return

	enlarged_card_label.text = _format_card_full(top_card)
	enlarged_card_panel.visible = true


## Hide enlarged card when mouse leaves a pile.
func _on_pile_hover_exited() -> void:
	enlarged_card_panel.visible = false


# ─── Leave Button ───────────────────────────────────────────────────────────────

## Called when the Leave button is pressed — exit spectating.
func _on_leave_pressed() -> void:
	NetworkClient.send_message("leave_spectate", {
		"session_id": _session_id,
	})
	get_tree().change_scene_to_file("res://scenes/LobbyScreen.tscn")


# ─── Card Formatting Helpers ────────────────────────────────────────────────────

## Format a card for short display (denomination + power abbreviation).
func _format_card_short(card: Dictionary) -> String:
	if card.is_empty():
		return "—"
	var denom: int = int(card.get("denomination", 0))
	var power: String = card.get("power_text", "")
	var denom_str: String = DENOMINATION_NAMES.get(denom, str(denom))
	if power == "":
		return denom_str
	return "%s\n%s" % [denom_str, power]


## Format a card for full display (name, denomination, power).
func _format_card_full(card: Dictionary) -> String:
	if card.is_empty():
		return "—"
	var name_str: String = card.get("card_name", "Unknown")
	var denom: int = int(card.get("denomination", 0))
	var power: String = card.get("power_text", "")
	var denom_str: String = DENOMINATION_NAMES.get(denom, str(denom))
	return "%s\n%s: %s\n%s" % [name_str, tr("UI_CARD_FILTER_DENOMINATION"), denom_str, power]
