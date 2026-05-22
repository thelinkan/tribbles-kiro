## GameTable — main game scene displaying the virtual table with all players,
## their piles, the local player's hand, action buttons, and game state info.
## Arranges players around the table with the local player at the bottom.
## Handles turn interactions: card selection, draw, accept, and power prompts.
## Listens for game_state_update, prompt, disconnect/reconnect notifications.
extends Control

# ─── Constants ──────────────────────────────────────────────────────────────────
## Positions around the table for up to 8 players (normalised 0–1 coordinates).
## Index 0 is always the local player (bottom centre).
## Adjusted with padding so all players are fully within the visible screen area.
const TABLE_POSITIONS: Array[Vector2] = [
	Vector2(0.50, 0.82),  # 0: bottom centre (local player)
	Vector2(0.18, 0.65),  # 1: bottom-left
	Vector2(0.10, 0.40),  # 2: left
	Vector2(0.18, 0.18),  # 3: top-left
	Vector2(0.40, 0.10),  # 4: top-centre-left
	Vector2(0.60, 0.10),  # 5: top-centre-right
	Vector2(0.82, 0.18),  # 6: top-right
	Vector2(0.90, 0.40),  # 7: right
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

## Hand card dimensions.
const HAND_CARD_WIDTH: float = 80.0
const HAND_CARD_HEIGHT: float = 120.0
## Minimum overlap spacing between cards in the fan.
const HAND_CARD_MIN_SPACING: float = 25.0
## How much a hovered card rises above others (pixels).
const HAND_CARD_HOVER_RISE: float = 20.0

# ─── Node References ────────────────────────────────────────────────────────────
@onready var game_info_panel: VBoxContainer = %GameInfoPanel
@onready var sequence_label: Label = %SequenceLabel
@onready var direction_label: Label = %DirectionLabel
@onready var round_label: Label = %RoundLabel
@onready var spectator_label: Label = %SpectatorLabel
@onready var player_positions: Control = %PlayerPositions
@onready var local_player_piles: HBoxContainer = %LocalPlayerPiles
@onready var hand_container: Control = %HandContainer
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
## Currently hovered hand card node (for z-order management).
var _hovered_hand_card: Control = null


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
	NetworkClient.action_result_received.connect(_on_action_result_received)
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


## Handle action_result messages — check for power_prompt events and show prompts.
## Also requests a fresh game state update after processing events.
func _on_action_result_received(payload: Dictionary) -> void:
	var events: Array = payload.get("events", [])

	for event in events:
		if not event is Dictionary:
			continue
		var event_type: String = event.get("type", "")

		if event_type == "power_prompt":
			_handle_power_prompt_event(event)
			return  # Don't request state update yet — waiting for player choice

		if event_type == "draw_choice_pending":
			_handle_draw_choice_event(event)
			return

		if event_type == "draw_accept_pending":
			_handle_draw_accept_event(event)
			return

	# No prompt pending — request updated game state
	NetworkClient.send_message("get_game_state", {"game_id": NetworkClient.current_game_id})


## Handle a power_prompt event from action_result — show appropriate prompt overlay.
func _handle_power_prompt_event(event: Dictionary) -> void:
	var prompt_type: String = event.get("prompt_type", "")
	var power_name: String = event.get("power_name", "")
	var message: String = event.get("message", "")
	var options: Array = event.get("options", [])

	match prompt_type:
		"activate_or_decline":
			_show_activate_decline_prompt(power_name, message)
		"choose_target_player":
			_show_target_player_prompt(power_name, message, options)
		"choose_card_from_hand":
			_show_card_from_hand_prompt(power_name, message, options)
		"choose_card_from_discard":
			_show_card_from_discard_prompt(power_name, message, options)
		"choose_card_from_play_pile":
			_show_card_from_play_pile_prompt(power_name, message, options)
		"choose_cards_from_hand":
			_show_multi_card_prompt(power_name, message, options, event.get("count", 2))
		"choose_power_to_freeze":
			_show_freeze_power_prompt(power_name, message, options)
		"choose_revealed_card":
			_show_revealed_card_prompt(power_name, message, event.get("revealed_cards", []))
		"scan_reorder":
			_show_scan_prompt(power_name, message, event.get("revealed_cards", []))
		_:
			_show_generic_power_prompt(power_name, message, options)


## Show activate/decline prompt for a power.
func _show_activate_decline_prompt(power_name: String, message: String) -> void:
	prompt_title.text = message

	for child in prompt_options.get_children():
		child.queue_free()

	var activate_btn := Button.new()
	activate_btn.text = "%s %s" % [tr("UI_GAME_ACTIVATE_POWER"), power_name.capitalize()]
	activate_btn.pressed.connect(_on_power_choice_selected.bind("activate"))
	prompt_options.add_child(activate_btn)

	var decline_btn := Button.new()
	decline_btn.text = tr("UI_GAME_DECLINE_POWER")
	decline_btn.pressed.connect(_on_power_choice_selected.bind("decline"))
	prompt_options.add_child(decline_btn)

	prompt_overlay.visible = true


## Show target player selection prompt.
func _show_target_player_prompt(power_name: String, message: String, target_indices: Array) -> void:
	prompt_title.text = message

	for child in prompt_options.get_children():
		child.queue_free()

	var players: Array = _game_state.get("players", [])
	for target_index in target_indices:
		var idx: int = int(target_index)
		if idx >= 0 and idx < players.size():
			var player_data: Dictionary = players[idx]
			var username: String = player_data.get("username", "Player %d" % idx)
			var btn := Button.new()
			btn.text = username
			btn.pressed.connect(_on_power_target_selected.bind(str(idx)))
			prompt_options.add_child(btn)

	prompt_overlay.visible = true


## Show card selection from hand prompt.
func _show_card_from_hand_prompt(power_name: String, message: String, card_ids: Array) -> void:
	prompt_title.text = message

	for child in prompt_options.get_children():
		child.queue_free()

	var hand: Array = _game_state.get("hand", [])
	for card_id in card_ids:
		var cid: int = int(card_id)
		# Find card data in hand
		var card_text: String = "Card %d" % cid
		for card_data in hand:
			if card_data is Dictionary and int(card_data.get("card_id", 0)) == cid:
				card_text = _format_card_short(card_data)
				break
		var btn := Button.new()
		btn.text = card_text
		btn.pressed.connect(_on_power_card_selected.bind(str(cid)))
		prompt_options.add_child(btn)

	prompt_overlay.visible = true


## Show card selection from discard pile prompt.
func _show_card_from_discard_prompt(power_name: String, message: String, card_options: Array) -> void:
	prompt_title.text = message

	for child in prompt_options.get_children():
		child.queue_free()

	for card_option in card_options:
		var btn := Button.new()
		if card_option is Dictionary:
			var cid: int = int(card_option.get("card_id", 0))
			var card_name: String = card_option.get("card_name", "")
			var denom: int = int(card_option.get("denomination", 0))
			var denom_str: String = DENOMINATION_NAMES.get(denom, str(denom))
			btn.text = "%s [%s]" % [card_name, denom_str]
			btn.pressed.connect(_on_power_card_selected.bind(str(cid)))
		else:
			var cid: int = int(card_option)
			btn.text = "Card %d" % cid
			btn.pressed.connect(_on_power_card_selected.bind(str(cid)))
		prompt_options.add_child(btn)

	prompt_overlay.visible = true


## Show card selection from play pile prompt.
func _show_card_from_play_pile_prompt(power_name: String, message: String, card_options: Array) -> void:
	prompt_title.text = message

	for child in prompt_options.get_children():
		child.queue_free()

	for card_option in card_options:
		var btn := Button.new()
		if card_option is Dictionary:
			var cid: int = int(card_option.get("card_id", 0))
			var card_name: String = card_option.get("card_name", "")
			var denom: int = int(card_option.get("denomination", 0))
			var denom_str: String = DENOMINATION_NAMES.get(denom, str(denom))
			btn.text = "%s [%s]" % [card_name, denom_str]
			btn.pressed.connect(_on_power_card_selected.bind(str(cid)))
		else:
			var cid: int = int(card_option)
			btn.text = "Card %d" % cid
			btn.pressed.connect(_on_power_card_selected.bind(str(cid)))
		prompt_options.add_child(btn)

	prompt_overlay.visible = true


## Show multi-card selection prompt (e.g., Process power — choose 2 cards).
func _show_multi_card_prompt(power_name: String, message: String, card_ids: Array, count: int) -> void:
	prompt_title.text = "%s (choose %d)" % [message, count]

	for child in prompt_options.get_children():
		child.queue_free()

	# For simplicity, show cards as individual buttons; player picks one at a time.
	# A more advanced UI would allow multi-select, but for now we handle sequentially.
	var hand: Array = _game_state.get("hand", [])
	for card_id in card_ids:
		var cid: int = int(card_id)
		var card_text: String = "Card %d" % cid
		for card_data in hand:
			if card_data is Dictionary and int(card_data.get("card_id", 0)) == cid:
				card_text = _format_card_short(card_data)
				break
		var btn := Button.new()
		btn.text = card_text
		btn.pressed.connect(_on_power_card_selected.bind(str(cid)))
		prompt_options.add_child(btn)

	prompt_overlay.visible = true


## Show freeze power selection prompt.
func _show_freeze_power_prompt(power_name: String, message: String, power_options: Array) -> void:
	prompt_title.text = message

	for child in prompt_options.get_children():
		child.queue_free()

	for power_opt in power_options:
		var btn := Button.new()
		btn.text = str(power_opt).capitalize()
		btn.pressed.connect(_on_power_choice_selected.bind(str(power_opt)))
		prompt_options.add_child(btn)

	prompt_overlay.visible = true


## Show revealed card selection prompt (Toxin power).
func _show_revealed_card_prompt(power_name: String, message: String, revealed_cards: Array) -> void:
	prompt_title.text = message

	for child in prompt_options.get_children():
		child.queue_free()

	for card_info in revealed_cards:
		if not card_info is Dictionary:
			continue
		var card_id: int = int(card_info.get("card_id", 0))
		var denom: int = int(card_info.get("denomination", 0))
		var btn := Button.new()
		btn.text = "%s (%d pts)" % [DENOMINATION_NAMES.get(denom, str(denom)), denom]
		btn.pressed.connect(_on_power_card_selected.bind(str(card_id)))
		prompt_options.add_child(btn)

	prompt_overlay.visible = true


## Show scan reorder prompt.
func _show_scan_prompt(power_name: String, message: String, revealed_cards: Array) -> void:
	prompt_title.text = message

	for child in prompt_options.get_children():
		child.queue_free()

	# Simplified: show Top/Bottom placement options
	var top_btn := Button.new()
	top_btn.text = tr("UI_GAME_PLACE_TOP") if TranslationServer.get_locale() != "" else "Place on Top"
	top_btn.pressed.connect(_on_power_choice_selected.bind("top"))
	prompt_options.add_child(top_btn)

	var bottom_btn := Button.new()
	bottom_btn.text = tr("UI_GAME_PLACE_BOTTOM") if TranslationServer.get_locale() != "" else "Place on Bottom"
	bottom_btn.pressed.connect(_on_power_choice_selected.bind("bottom"))
	prompt_options.add_child(bottom_btn)

	prompt_overlay.visible = true


## Show a generic power prompt with options.
func _show_generic_power_prompt(power_name: String, message: String, options: Array) -> void:
	prompt_title.text = message

	for child in prompt_options.get_children():
		child.queue_free()

	for option in options:
		var btn := Button.new()
		btn.text = str(option)
		btn.pressed.connect(_on_power_choice_selected.bind(str(option)))
		prompt_options.add_child(btn)

	prompt_overlay.visible = true


## Called when a power activate/decline or simple choice is selected.
func _on_power_choice_selected(value: String) -> void:
	NetworkClient.send_message("power_choice", {
		"game_id": NetworkClient.current_game_id,
		"choice_type": "option",
		"value": value,
	})
	prompt_overlay.visible = false


## Called when a target player is selected for a power.
func _on_power_target_selected(target_index: String) -> void:
	NetworkClient.send_message("power_choice", {
		"game_id": NetworkClient.current_game_id,
		"choice_type": "target_player",
		"value": target_index,
	})
	prompt_overlay.visible = false


## Called when a card is selected for a power (from hand, discard, play pile, or revealed).
func _on_power_card_selected(card_id: String) -> void:
	NetworkClient.send_message("power_choice", {
		"game_id": NetworkClient.current_game_id,
		"choice_type": "card_selection",
		"value": card_id,
	})
	prompt_overlay.visible = false


## Handle draw_choice_pending event — show play/keep choice for matching draw.
## Handle draw_choice_pending event — show drawn card and play/keep choice.
## The drawn card matches the current sequence so the player can play it or keep it.
func _handle_draw_choice_event(event: Dictionary) -> void:
	var card_id: int = int(event.get("card_id", 0))
	var denomination: int = int(event.get("denomination", 0))
	var card_name: String = event.get("card_name", "")
	var power_text: String = event.get("power_text", "")
	var denom_str: String = DENOMINATION_NAMES.get(denomination, str(denomination))

	# Show drawn card info prominently
	var card_display: String = "%s [%s]" % [card_name, denom_str]
	if power_text != "":
		card_display += "\n%s" % power_text

	prompt_title.text = "%s:\n%s\n\n%s" % [tr("UI_GAME_DRAWN_CARD"), card_display, "This card matches! Play it or keep in hand?"]

	for child in prompt_options.get_children():
		child.queue_free()

	var play_btn := Button.new()
	play_btn.text = tr("UI_GAME_PLAY_CARD")
	play_btn.pressed.connect(_on_draw_play_choice.bind(card_id))
	prompt_options.add_child(play_btn)

	var keep_btn := Button.new()
	keep_btn.text = "Keep in hand (Pass)"
	keep_btn.pressed.connect(_on_draw_keep_choice)
	prompt_options.add_child(keep_btn)

	prompt_overlay.visible = true


## Handle draw_accept_pending event — show drawn card with Pass button.
## The drawn card does not match the sequence so it goes into hand automatically.
func _handle_draw_accept_event(event: Dictionary) -> void:
	var card_id: int = int(event.get("card_id", 0))
	var denomination: int = int(event.get("denomination", 0))
	var card_name: String = event.get("card_name", "")
	var power_text: String = event.get("power_text", "")
	var denom_str: String = DENOMINATION_NAMES.get(denomination, str(denomination))

	# Show drawn card info prominently with a Pass button
	var card_display: String = "%s [%s]" % [card_name, denom_str]
	if power_text != "":
		card_display += "\n%s" % power_text

	prompt_title.text = "%s:\n%s\n\n%s" % [tr("UI_GAME_DRAWN_CARD"), card_display, "Does not match. Card goes to hand."]

	for child in prompt_options.get_children():
		child.queue_free()

	var pass_btn := Button.new()
	pass_btn.text = "Pass"
	pass_btn.pressed.connect(_on_draw_keep_choice)
	prompt_options.add_child(pass_btn)

	prompt_overlay.visible = true


## Called when player chooses to play the drawn matching card.
func _on_draw_play_choice(card_id: int) -> void:
	NetworkClient.send_message("play_card", {
		"game_id": NetworkClient.current_game_id,
		"card_id": card_id,
		"activate_power": true,
	})
	prompt_overlay.visible = false


## Called when player chooses to keep the drawn card (pass).
func _on_draw_keep_choice() -> void:
	NetworkClient.send_message("accept_draw", {"game_id": NetworkClient.current_game_id})
	prompt_overlay.visible = false


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

	# Clear local player piles.
	for child in local_player_piles.get_children():
		child.queue_free()

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

	# Render local player's piles in the dedicated panel above the hand.
	if not ordered_players.is_empty():
		var local_data: Dictionary = ordered_players[0]
		_create_local_player_piles(local_data, active_player_id)

	# Render other players around the table (skip index 0 = local player).
	for i in range(1, ordered_players.size()):
		var player_data: Dictionary = ordered_players[i]
		var pos_index: int = i % TABLE_POSITIONS.size()
		var table_pos: Vector2 = TABLE_POSITIONS[pos_index]

		var player_node := _create_player_position_node(player_data, active_player_id)
		# Centre the node on the table position with padding clamping.
		var node_x: float = table_pos.x * viewport_size.x - 80.0
		var node_y: float = table_pos.y * viewport_size.y - 50.0
		# Clamp to ensure fully visible with 10px padding.
		node_x = clampf(node_x, 10.0, viewport_size.x - 170.0)
		node_y = clampf(node_y, 10.0, viewport_size.y - 110.0)
		player_node.position = Vector2(node_x, node_y)
		player_positions.add_child(player_node)
		_player_nodes.append(player_node)


## Create the local player's piles display in the dedicated panel above the hand.
## Shows draw deck count, play pile top card, and discard pile top card.
func _create_local_player_piles(player_data: Dictionary, active_player_id: int) -> void:
	var player_id: int = int(player_data.get("player_id", 0))
	var username: String = player_data.get("username", "Player")
	var score: int = int(player_data.get("cumulative_score", 0))
	var draw_count: int = int(player_data.get("draw_deck_count", 0))

	# Username + score label on the left.
	var info_label := Label.new()
	info_label.text = "%s  %s: %d" % [username, tr("UI_GAME_SCORE"), score]
	info_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	local_player_piles.add_child(info_label)

	# Spacer.
	var spacer := Control.new()
	spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	local_player_piles.add_child(spacer)

	# Draw deck (face-down with count).
	var draw_btn := Button.new()
	draw_btn.text = "%s (%d)" % [tr("UI_GAME_DRAW_DECK"), draw_count]
	draw_btn.custom_minimum_size = Vector2(70, 35)
	draw_btn.mouse_entered.connect(_on_pile_hover_entered.bind("draw", player_data))
	draw_btn.mouse_exited.connect(_on_pile_hover_exited)
	local_player_piles.add_child(draw_btn)

	# Play pile (top card visible).
	var play_pile: Array = player_data.get("play_pile_top", [])
	var play_btn := Button.new()
	if not play_pile.is_empty():
		var top_card: Dictionary = play_pile[0] if play_pile[0] is Dictionary else {}
		play_btn.text = _format_card_short(top_card)
		play_btn.tooltip_text = _format_card_full(top_card)
	else:
		play_btn.text = tr("UI_GAME_PLAY_PILE")
	play_btn.custom_minimum_size = Vector2(70, 35)
	play_btn.mouse_entered.connect(_on_pile_hover_entered.bind("play", player_data))
	play_btn.mouse_exited.connect(_on_pile_hover_exited)
	local_player_piles.add_child(play_btn)

	# Discard pile (top card visible).
	var discard_pile: Array = player_data.get("discard_pile_top", [])
	var discard_btn := Button.new()
	if not discard_pile.is_empty():
		var top_card: Dictionary = discard_pile[0] if discard_pile[0] is Dictionary else {}
		discard_btn.text = _format_card_short(top_card)
		discard_btn.tooltip_text = _format_card_full(top_card)
	else:
		discard_btn.text = tr("UI_GAME_DISCARD_PILE")
	discard_btn.custom_minimum_size = Vector2(70, 35)
	discard_btn.mouse_entered.connect(_on_pile_hover_entered.bind("discard", player_data))
	discard_btn.mouse_exited.connect(_on_pile_hover_exited)
	local_player_piles.add_child(discard_btn)


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


# ─── Hand Display (Task 25.2 / 29.4.1) ────────────────────────────────────────

## Rebuild the local player's hand display using an overlapping fan layout.
## Cards overlap horizontally with the rightmost card fully visible.
## Fan spacing adjusts dynamically so up to 15 cards fit within available width.
func _update_hand_display() -> void:
	# Clear existing hand cards.
	for child in hand_container.get_children():
		child.queue_free()
	_hovered_hand_card = null

	var hand: Array = _game_state.get("hand", [])
	if hand.is_empty():
		return

	var card_count: int = hand.size()
	var container_width: float = hand_container.size.x
	if container_width <= 0:
		container_width = 800.0  # Fallback width.

	# Calculate spacing: fit all cards within available width.
	# The last card is fully visible, so total width = spacing * (n-1) + card_width.
	var spacing: float = HAND_CARD_WIDTH  # Default: no overlap.
	if card_count > 1:
		var available_for_spacing: float = container_width - HAND_CARD_WIDTH
		spacing = available_for_spacing / float(card_count - 1)
		# Clamp spacing: at least HAND_CARD_MIN_SPACING, at most full card width.
		spacing = clampf(spacing, HAND_CARD_MIN_SPACING, HAND_CARD_WIDTH)

	# Calculate starting x to centre the fan within the container.
	var total_fan_width: float = spacing * float(card_count - 1) + HAND_CARD_WIDTH
	var start_x: float = (container_width - total_fan_width) / 2.0

	for i in range(card_count):
		var card_data = hand[i]
		if not card_data is Dictionary:
			continue
		var card: Dictionary = card_data
		var card_id: int = int(card.get("card_id", 0))

		# Try to load a card image; fall back to styled text button.
		var card_node: Control = _create_hand_card_node(card, card_id)
		card_node.custom_minimum_size = Vector2(HAND_CARD_WIDTH, HAND_CARD_HEIGHT)
		card_node.size = Vector2(HAND_CARD_WIDTH, HAND_CARD_HEIGHT)
		card_node.tooltip_text = _format_card_full(card)
		card_node.gui_input.connect(_on_hand_card_gui_input.bind(card_id, card))
		card_node.mouse_entered.connect(_on_hand_card_hover_entered.bind(card_node, i))
		card_node.mouse_exited.connect(_on_hand_card_hover_exited.bind(card_node, i))
		card_node.set_meta("card_id", card_id)
		card_node.set_meta("base_y", 0.0)

		# Position the card in the fan layout.
		card_node.position = Vector2(start_x + spacing * float(i), 0.0)

		hand_container.add_child(card_node)

	_highlight_hand_cards()


## Called when mouse enters a hand card — raise it above others.
func _on_hand_card_hover_entered(card_node: Control, _index: int) -> void:
	_hovered_hand_card = card_node
	# Raise the card visually by moving it up.
	card_node.position.y = -HAND_CARD_HOVER_RISE
	# Move to front so it renders above overlapping neighbours.
	hand_container.move_child(card_node, hand_container.get_child_count() - 1)


## Called when mouse exits a hand card — restore its position.
func _on_hand_card_hover_exited(card_node: Control, _index: int) -> void:
	if _hovered_hand_card == card_node:
		_hovered_hand_card = null
	# Restore vertical position.
	card_node.position.y = 0.0
	# Restore z-order by re-laying out (move back to original index).
	# We re-sort all children by their x position to restore proper overlap order.
	_restore_hand_z_order()


## Restore the z-order of hand cards based on their x position (left to right).
func _restore_hand_z_order() -> void:
	var children: Array[Node] = []
	for child in hand_container.get_children():
		children.append(child)
	# Sort by x position (leftmost first = lowest z-order).
	children.sort_custom(func(a: Node, b: Node) -> bool:
		return a.position.x < b.position.x
	)
	for i in range(children.size()):
		hand_container.move_child(children[i], i)


## Highlight valid playable cards in the hand.
func _highlight_hand_cards() -> void:
	for child in hand_container.get_children():
		if not child.has_meta("card_id"):
			continue
		var card_id: int = int(child.get_meta("card_id", 0))
		if _is_local_turn and card_id in _valid_card_ids:
			child.modulate = Color(1.0, 1.0, 0.6, 1.0)  # Yellow highlight.
			child.mouse_filter = Control.MOUSE_FILTER_STOP
		elif _is_local_turn:
			child.modulate = Color(0.6, 0.6, 0.6, 1.0)  # Dimmed.
			child.mouse_filter = Control.MOUSE_FILTER_STOP
		else:
			child.modulate = Color(1.0, 1.0, 1.0, 1.0)  # Normal.
			child.mouse_filter = Control.MOUSE_FILTER_STOP


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


## Called when a hand card node receives gui_input (click) — delegates to _on_hand_card_pressed.
func _on_hand_card_gui_input(event: InputEvent, card_id: int, card_data: Dictionary) -> void:
	if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
		_on_hand_card_pressed(card_id, card_data)


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

## Create a hand card node — uses card image if available, otherwise a styled button.
## Card images are looked up at res://assets/cards/{image_filename}.
func _create_hand_card_node(card: Dictionary, card_id: int) -> Control:
	var image_filename: String = card.get("image_filename", "")

	# Try to load card image
	if image_filename != "":
		var image_path: String = "res://assets/cards/%s" % image_filename
		if ResourceLoader.exists(image_path):
			var texture: Texture2D = load(image_path)
			if texture != null:
				var tex_btn := TextureButton.new()
				tex_btn.texture_normal = texture
				tex_btn.ignore_texture_size = true
				tex_btn.stretch_mode = TextureButton.STRETCH_KEEP_ASPECT_COVERED
				tex_btn.custom_minimum_size = Vector2(HAND_CARD_WIDTH, HAND_CARD_HEIGHT)
				tex_btn.size = Vector2(HAND_CARD_WIDTH, HAND_CARD_HEIGHT)
				return tex_btn

	# Fallback: styled text button
	var card_btn := Button.new()
	card_btn.text = _format_card_short(card)
	card_btn.clip_text = true
	card_btn.add_theme_stylebox_override("normal", _create_card_stylebox())
	card_btn.add_theme_stylebox_override("hover", _create_card_stylebox(Color(0.9, 0.9, 0.95, 1.0)))
	card_btn.add_theme_stylebox_override("pressed", _create_card_stylebox(Color(0.75, 0.75, 0.8, 1.0)))
	card_btn.add_theme_stylebox_override("disabled", _create_card_stylebox(Color(0.7, 0.7, 0.7, 1.0)))
	card_btn.add_theme_color_override("font_color", Color(0.0, 0.0, 0.0, 1.0))
	card_btn.add_theme_color_override("font_hover_color", Color(0.0, 0.0, 0.0, 1.0))
	card_btn.add_theme_color_override("font_pressed_color", Color(0.0, 0.0, 0.0, 1.0))
	card_btn.add_theme_color_override("font_disabled_color", Color(0.3, 0.3, 0.3, 1.0))
	return card_btn


## Create a StyleBoxFlat for card buttons: opaque background with black border.
## bg_color defaults to light gray; pass a different color for hover/pressed states.
func _create_card_stylebox(bg_color: Color = Color(0.85, 0.85, 0.85, 1.0)) -> StyleBoxFlat:
	var style := StyleBoxFlat.new()
	style.bg_color = bg_color
	style.border_color = Color(0.0, 0.0, 0.0, 1.0)
	style.set_border_width_all(2)
	style.set_corner_radius_all(4)
	style.set_content_margin_all(4)
	return style


## Format a card for short display (denomination + power name only).
func _format_card_short(card: Dictionary) -> String:
	if card.is_empty():
		return "—"
	var denom: int = int(card.get("denomination", 0))
	var power: String = card.get("power_text", "")
	var denom_str: String = DENOMINATION_NAMES.get(denom, str(denom))
	if power == "":
		return denom_str
	# Show only the power name, not full rules text.
	# Power names are typically short (e.g., "Go", "Skip", "Poison").
	var power_name: String = power.split(":")[0].strip_edges() if ":" in power else power
	return "%s\n%s" % [denom_str, power_name]


## Format a card for full display (name, denomination, power with full text).
func _format_card_full(card: Dictionary) -> String:
	if card.is_empty():
		return "—"
	var name_str: String = card.get("card_name", "Unknown")
	var denom: int = int(card.get("denomination", 0))
	var power: String = card.get("power_text", "")
	var denom_str: String = DENOMINATION_NAMES.get(denom, str(denom))
	return "%s\n%s: %s\n%s" % [name_str, tr("UI_CARD_FILTER_DENOMINATION"), denom_str, power]
