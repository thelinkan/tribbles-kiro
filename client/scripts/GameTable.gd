## GameTable — main game scene displaying the virtual table with all players,
## their piles, the local player's hand, action buttons, and game state info.
## Arranges players around the table with the local player at the bottom.
## Handles turn interactions: card selection, draw, accept, and power prompts.
## Listens for game_state_update, prompt, disconnect/reconnect notifications.
extends Control

# ─── Constants ──────────────────────────────────────────────────────────────────
## Positions around the table for up to 8 players (normalised 0–1 coordinates).
## Index 0 is always the local player (bottom centre).
const TABLE_POSITIONS: Array[Vector2] = [
	Vector2(0.5, 0.88),   # 0: bottom centre (local player)
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
@onready var sequence_label: Label = %SequenceLabel
@onready var direction_label: Label = %DirectionLabel
@onready var round_label: Label = %RoundLabel
@onready var spectator_label: Label = %SpectatorLabel
@onready var player_positions: Control = %PlayerPositions
@onready var hand_container: HBoxContainer = %HandContainer
@onready var action_panel: VBoxContainer = %ActionPanel
@onready var draw_button: Button = %DrawButton
@onready var accept_button: Button = %AcceptButton
@onready var drawn_card_label: Label = %DrawnCardLabel
@onready var prompt_overlay: PanelContainer = %PromptOverlay
@onready var prompt_title: Label = %PromptTitle
@onready var prompt_options: VBoxContainer = %PromptOptions
@onready var enlarged_card_panel: PanelContainer = %EnlargedCardPanel
@onready var enlarged_card_label: Label = %EnlargedCardLabel
@onready var turn_indicator: Label = %TurnIndicator

# ─── State ──────────────────────────────────────────────────────────────────────
## The full visible game state received from the server.
var _game_state: Dictionary = {}
## The local player's ID (set from NetworkClient or game state).
var _local_player_id: int = -1
## Whether it is currently the local player's turn.
var _is_local_turn: bool = false
## List of player position UI nodes (created dynamically).
var _player_nodes: Array[Control] = []
## Current spectator count.
var _spectator_count: int = 0
## Set of disconnected player IDs.
var _disconnected_players: Dictionary = {}
## Set of AI-substitute player IDs.
var _ai_substitute_players: Dictionary = {}
## Cards in the local player's hand that are valid to play.
var _valid_card_ids: Array[int] = []
## The drawn card awaiting acceptance (null if none).
var _drawn_card: Dictionary = {}


# ─── Lifecycle ──────────────────────────────────────────────────────────────────

func _ready() -> void:
	# Set localised button text.
	draw_button.text = tr("UI_GAME_DRAW_CARD")
	accept_button.text = tr("UI_GAME_ACCEPT_DRAW")

	# Connect UI signals.
	draw_button.pressed.connect(_on_draw_pressed)
	accept_button.pressed.connect(_on_accept_pressed)

	# Connect network signals.
	NetworkClient.game_state_update.connect(_on_game_state_update)
	NetworkClient.prompt_received.connect(_on_prompt_received)
	NetworkClient.disconnect_notify.connect(_on_disconnect_notify)
	NetworkClient.reconnect_notify.connect(_on_reconnect_notify)
	NetworkClient.spectator_count_update.connect(_on_spectator_count_update)
	NetworkClient.round_end.connect(_on_round_end)
	NetworkClient.game_end.connect(_on_game_end)

	# Initial UI state.
	turn_indicator.text = ""
	spectator_label.text = ""
	prompt_overlay.visible = false
	enlarged_card_panel.visible = false
	accept_button.visible = false
	drawn_card_label.visible = false

	# Request initial game state.
	NetworkClient.send_message("get_game_state", {"game_id": NetworkClient.current_game_id})


# ─── Game State Update (Task 25.3) ─────────────────────────────────────────────

## Handle game_state_update messages from the server.
func _on_game_state_update(payload: Dictionary) -> void:
	_game_state = payload.get("visible_state", payload)
	_local_player_id = _game_state.get("local_player_id", _local_player_id)
	_check_ai_substitutes()
	_update_game_info()
	_update_player_positions()
	_update_hand_display()
	_update_turn_state()


## Update the central game info panel (sequence, direction, round, spectators).
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

	if _spectator_count > 0:
		spectator_label.text = "%s: %d" % [tr("UI_GAME_SPECTATORS"), _spectator_count]
		spectator_label.visible = true
	else:
		spectator_label.visible = false


## Update the turn state and highlight controls.
func _update_turn_state() -> void:
	var active_player_id: int = _game_state.get("active_player_id", -1)
	_is_local_turn = (active_player_id == _local_player_id)

	if _is_local_turn:
		turn_indicator.text = tr("UI_GAME_YOUR_TURN")
		draw_button.disabled = false
	else:
		turn_indicator.text = ""
		draw_button.disabled = true

	# Determine valid playable cards.
	_valid_card_ids.clear()
	if _is_local_turn:
		var valid_cards: Array = _game_state.get("valid_card_ids", [])
		for card_id in valid_cards:
			_valid_card_ids.append(int(card_id))

	# Re-highlight hand cards.
	_highlight_hand_cards()


# ─── Player Position Display (Task 25.1) ───────────────────────────────────────

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

	# Find local player index to reorder positions.
	var local_index: int = -1
	for i in range(players.size()):
		if int(players[i].get("player_id", -1)) == _local_player_id:
			local_index = i
			break

	if local_index == -1:
		local_index = 0

	# Reorder so local player is at position 0.
	var ordered_players: Array = []
	for i in range(players.size()):
		var idx := (local_index + i) % players.size()
		ordered_players.append(players[idx])

	var active_player_id: int = _game_state.get("active_player_id", -1)
	var viewport_size := get_viewport_rect().size

	for i in range(ordered_players.size()):
		var player_data: Dictionary = ordered_players[i]
		var pos_index: int = i % TABLE_POSITIONS.size()
		var table_pos: Vector2 = TABLE_POSITIONS[pos_index]

		var player_node := _create_player_position_node(player_data, active_player_id)
		player_node.position = Vector2(
			table_pos.x * viewport_size.x - 80.0,
			table_pos.y * viewport_size.y - 50.0
		)
		player_positions.add_child(player_node)
		_player_nodes.append(player_node)


## Create a single player position UI node showing username, score, piles.
func _create_player_position_node(player_data: Dictionary, active_player_id: int) -> Control:
	var player_id: int = int(player_data.get("player_id", 0))
	var username: String = player_data.get("username", "Player")
	var score: int = int(player_data.get("cumulative_score", 0))
	var draw_count: int = int(player_data.get("draw_deck_count", 0))
	var is_active: bool = (player_id == active_player_id)
	var is_disconnected: bool = _disconnected_players.has(player_id)
	var is_ai_sub: bool = _ai_substitute_players.has(player_id)

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
	var play_pile: Array = player_data.get("play_pile_top", [])
	var play_btn := Button.new()
	if not play_pile.is_empty():
		var top_card: Dictionary = play_pile[0] if play_pile[0] is Dictionary else {}
		play_btn.text = _format_card_short(top_card)
	else:
		play_btn.text = tr("UI_GAME_PLAY_PILE")
	play_btn.custom_minimum_size = Vector2(50, 40)
	play_btn.mouse_entered.connect(_on_pile_hover_entered.bind("play", player_data))
	play_btn.mouse_exited.connect(_on_pile_hover_exited)
	piles_row.add_child(play_btn)

	# Discard pile (top card visible).
	var discard_pile: Array = player_data.get("discard_pile_top", [])
	var discard_btn := Button.new()
	if not discard_pile.is_empty():
		var top_card: Dictionary = discard_pile[0] if discard_pile[0] is Dictionary else {}
		discard_btn.text = _format_card_short(top_card)
	else:
		discard_btn.text = tr("UI_GAME_DISCARD_PILE")
	discard_btn.custom_minimum_size = Vector2(50, 40)
	discard_btn.mouse_entered.connect(_on_pile_hover_entered.bind("discard", player_data))
	discard_btn.mouse_exited.connect(_on_pile_hover_exited)
	piles_row.add_child(discard_btn)

	container.add_child(piles_row)
	return container


# ─── Pile Hover (Task 25.1) ─────────────────────────────────────────────────────

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
			# Draw deck is face-down; show count only.
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


# ─── Hand Display (Task 25.2) ──────────────────────────────────────────────────

## Rebuild the local player's hand display.
func _update_hand_display() -> void:
	# Clear existing hand cards.
	for child in hand_container.get_children():
		child.queue_free()

	var hand: Array = _game_state.get("hand", [])
	for card_data in hand:
		if not card_data is Dictionary:
			continue
		var card: Dictionary = card_data
		var card_id: int = int(card.get("card_id", 0))

		var card_btn := Button.new()
		card_btn.text = _format_card_short(card)
		card_btn.custom_minimum_size = Vector2(80, 120)
		card_btn.tooltip_text = _format_card_full(card)
		card_btn.pressed.connect(_on_hand_card_pressed.bind(card_id, card))
		card_btn.set_meta("card_id", card_id)
		hand_container.add_child(card_btn)

	_highlight_hand_cards()


## Highlight valid playable cards in the hand.
func _highlight_hand_cards() -> void:
	for child in hand_container.get_children():
		if child is Button:
			var card_id: int = int(child.get_meta("card_id", 0))
			if _is_local_turn and card_id in _valid_card_ids:
				child.modulate = Color(1.0, 1.0, 0.6, 1.0)  # Yellow highlight.
				child.disabled = false
			elif _is_local_turn:
				child.modulate = Color(0.6, 0.6, 0.6, 1.0)  # Dimmed.
				child.disabled = true
			else:
				child.modulate = Color(1.0, 1.0, 1.0, 1.0)  # Normal.
				child.disabled = true


# ─── Turn Interaction (Task 25.2) ──────────────────────────────────────────────

## Called when a hand card is pressed — send play_card action.
func _on_hand_card_pressed(card_id: int, _card_data: Dictionary) -> void:
	if not _is_local_turn:
		return
	if card_id not in _valid_card_ids:
		return

	NetworkClient.send_message("play_card", {
		"game_id": NetworkClient.current_game_id,
		"card_id": card_id,
		"activate_power": true,
	})


## Called when the Draw button is pressed — send draw_card action.
func _on_draw_pressed() -> void:
	if not _is_local_turn:
		return

	NetworkClient.send_message("draw_card", {"game_id": NetworkClient.current_game_id})


## Called when the Accept button is pressed — send accept_draw action.
func _on_accept_pressed() -> void:
	NetworkClient.send_message("accept_draw", {"game_id": NetworkClient.current_game_id})
	accept_button.visible = false
	drawn_card_label.visible = false
	_drawn_card = {}


# ─── Prompt Handling (Task 25.2 / 25.3) ────────────────────────────────────────

## Handle prompt messages from the server (power activation choices).
func _on_prompt_received(payload: Dictionary) -> void:
	var prompt_type: String = payload.get("prompt_type", "")

	match prompt_type:
		"activate_power":
			_show_power_activation_prompt(payload)
		"drawn_card":
			_show_drawn_card_prompt(payload)
		_:
			_show_generic_prompt(payload)


## Show power activation prompt with Activate/Decline options.
func _show_power_activation_prompt(payload: Dictionary) -> void:
	var card: Dictionary = payload.get("card", {})
	var options: Array = payload.get("options", [])

	prompt_title.text = "%s: %s" % [tr("UI_GAME_ACTIVATE_POWER"), _format_card_full(card)]

	# Clear existing options.
	for child in prompt_options.get_children():
		child.queue_free()

	if options.is_empty():
		# Default: Activate / Decline.
		var activate_btn := Button.new()
		activate_btn.text = tr("UI_GAME_ACTIVATE_POWER")
		activate_btn.pressed.connect(_on_prompt_option_selected.bind("activate"))
		prompt_options.add_child(activate_btn)

		var decline_btn := Button.new()
		decline_btn.text = tr("UI_GAME_DECLINE_POWER")
		decline_btn.pressed.connect(_on_prompt_option_selected.bind("decline"))
		prompt_options.add_child(decline_btn)
	else:
		for option in options:
			var option_btn := Button.new()
			if option is Dictionary:
				option_btn.text = str(option.get("label", option.get("value", "Option")))
				option_btn.pressed.connect(
					_on_prompt_option_selected.bind(str(option.get("value", "")))
				)
			else:
				option_btn.text = str(option)
				option_btn.pressed.connect(_on_prompt_option_selected.bind(str(option)))
			prompt_options.add_child(option_btn)

	prompt_overlay.visible = true


## Show drawn card display with Accept button (for non-matching draws).
func _show_drawn_card_prompt(payload: Dictionary) -> void:
	var card: Dictionary = payload.get("card", {})
	_drawn_card = card

	drawn_card_label.text = _format_card_full(card)
	drawn_card_label.visible = true
	accept_button.visible = true

	# If the drawn card matches the sequence, also show a Play option.
	var can_play: bool = payload.get("can_play", false)
	if can_play:
		prompt_title.text = tr("UI_GAME_PLAY_CARD") + "?"

		for child in prompt_options.get_children():
			child.queue_free()

		var play_btn := Button.new()
		play_btn.text = tr("UI_GAME_PLAY_CARD")
		play_btn.pressed.connect(_on_drawn_card_play)
		prompt_options.add_child(play_btn)

		var keep_btn := Button.new()
		keep_btn.text = tr("UI_GAME_ACCEPT_DRAW")
		keep_btn.pressed.connect(_on_drawn_card_keep)
		prompt_options.add_child(keep_btn)

		prompt_overlay.visible = true


## Show a generic prompt with provided options.
func _show_generic_prompt(payload: Dictionary) -> void:
	var title: String = payload.get("title", "Choose")
	var options: Array = payload.get("options", [])

	prompt_title.text = title

	for child in prompt_options.get_children():
		child.queue_free()

	for option in options:
		var option_btn := Button.new()
		if option is Dictionary:
			option_btn.text = str(option.get("label", option.get("value", "Option")))
			option_btn.pressed.connect(
				_on_prompt_option_selected.bind(str(option.get("value", "")))
			)
		else:
			option_btn.text = str(option)
			option_btn.pressed.connect(_on_prompt_option_selected.bind(str(option)))
		prompt_options.add_child(option_btn)

	prompt_overlay.visible = true


## Called when a prompt option is selected — send power_choice.
func _on_prompt_option_selected(value: String) -> void:
	NetworkClient.send_message("power_choice", {
		"game_id": NetworkClient.current_game_id,
		"choice_type": "option",
		"value": value,
	})
	prompt_overlay.visible = false


## Called when the player chooses to play the drawn card.
func _on_drawn_card_play() -> void:
	NetworkClient.send_message("power_choice", {
		"game_id": NetworkClient.current_game_id,
		"choice_type": "play_drawn",
		"value": "play",
	})
	prompt_overlay.visible = false
	accept_button.visible = false
	drawn_card_label.visible = false
	_drawn_card = {}


## Called when the player chooses to keep the drawn card in hand.
func _on_drawn_card_keep() -> void:
	NetworkClient.send_message("accept_draw", {"game_id": NetworkClient.current_game_id})
	prompt_overlay.visible = false
	accept_button.visible = false
	drawn_card_label.visible = false
	_drawn_card = {}


# ─── Disconnect / Reconnect Handling (Task 25.3) ───────────────────────────────

## Handle disconnect_notify: show disconnected indicator at player position.
func _on_disconnect_notify(payload: Dictionary) -> void:
	var player_id: int = int(payload.get("player_id", 0))
	_disconnected_players[player_id] = true
	# Remove from AI substitute if previously set.
	_ai_substitute_players.erase(player_id)
	# Refresh display.
	_update_player_positions()


## Handle reconnect_notify: remove indicator, show brief notification.
func _on_reconnect_notify(payload: Dictionary) -> void:
	var player_id: int = int(payload.get("player_id", 0))
	var username: String = payload.get("username", "Player")
	_disconnected_players.erase(player_id)
	_ai_substitute_players.erase(player_id)
	# Refresh display.
	_update_player_positions()
	# Show brief reconnection notification via turn indicator.
	turn_indicator.text = "%s: %s" % [tr("UI_PLAYER_RECONNECTED"), username]
	# Clear notification after a short delay.
	get_tree().create_timer(3.0).timeout.connect(_clear_reconnect_notification)


## Clear the reconnection notification text.
func _clear_reconnect_notification() -> void:
	if _is_local_turn:
		turn_indicator.text = tr("UI_GAME_YOUR_TURN")
	else:
		turn_indicator.text = ""


## Handle spectator_count_update: display spectator count.
func _on_spectator_count_update(payload: Dictionary) -> void:
	_spectator_count = int(payload.get("spectator_count", 0))
	_update_game_info()


## Handle AI_Substitute indicator — called when game state includes AI info.
func _check_ai_substitutes() -> void:
	var players: Array = _game_state.get("players", [])
	for player_data in players:
		if not player_data is Dictionary:
			continue
		var player_id: int = int(player_data.get("player_id", 0))
		var is_ai_sub: bool = player_data.get("ai_substitute_active", false)
		if is_ai_sub:
			_ai_substitute_players[player_id] = true
			_disconnected_players.erase(player_id)
		elif _ai_substitute_players.has(player_id) and not is_ai_sub:
			_ai_substitute_players.erase(player_id)


# ─── Round End / Game End (Task 25.3) ──────────────────────────────────────────

## Handle round_end: store payload and navigate to end-of-round screen.
func _on_round_end(payload: Dictionary) -> void:
	NetworkClient.round_end_data = payload
	get_tree().change_scene_to_file("res://scenes/EndOfRoundScreen.tscn")


## Handle game_end: store payload and navigate to end-of-game screen.
func _on_game_end(payload: Dictionary) -> void:
	NetworkClient.game_end_data = payload
	get_tree().change_scene_to_file("res://scenes/EndOfGameScreen.tscn")


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
