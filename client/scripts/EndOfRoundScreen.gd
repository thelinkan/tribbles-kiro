## EndOfRoundScreen — displays each player's round score and cumulative score
## after a round ends. Reads payload data from NetworkClient.round_end_data.
## Shows a "Continue" button that returns to the GameTable scene.
extends Control

# ─── Node References ────────────────────────────────────────────────────────────
@onready var title_label: Label = %TitleLabel
@onready var scores_container: VBoxContainer = %ScoresContainer
@onready var continue_button: Button = %ContinueButton


# ─── Lifecycle ──────────────────────────────────────────────────────────────────

func _ready() -> void:
	title_label.text = tr("UI_END_ROUND_TITLE")
	continue_button.text = tr("UI_CONTINUE")
	continue_button.pressed.connect(_on_continue_pressed)

	_populate_scores()


# ─── Score Display ──────────────────────────────────────────────────────────────

## Populate the scores list from NetworkClient.round_end_data.
func _populate_scores() -> void:
	var data: Dictionary = NetworkClient.round_end_data
	var scores: Dictionary = data.get("scores", {})

	if scores.is_empty():
		var empty_label := Label.new()
		empty_label.text = "No score data available."
		empty_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		scores_container.add_child(empty_label)
		return

	# Add header row.
	var header := _create_score_row(tr("UI_PLAYER"), tr("UI_END_ROUND_SCORES"), tr("UI_END_ROUND_CUMULATIVE"), true)
	scores_container.add_child(header)

	# Add separator.
	var separator := HSeparator.new()
	scores_container.add_child(separator)

	# Each entry in scores is keyed by player username or ID.
	# Expected format: {"player_name": {"round_score": X, "cumulative_score": Y}}
	for player_key in scores:
		var player_scores: Dictionary = scores[player_key] if scores[player_key] is Dictionary else {}
		var round_score: int = int(player_scores.get("round_score", 0))
		var cumulative_score: int = int(player_scores.get("cumulative_score", 0))
		var display_name: String = str(player_key)

		var row := _create_score_row(display_name, _format_score(round_score), _format_score(cumulative_score), false)
		scores_container.add_child(row)


## Create a row with three columns: player name, round score, cumulative score.
func _create_score_row(col1: String, col2: String, col3: String, is_header: bool) -> HBoxContainer:
	var row := HBoxContainer.new()
	row.alignment = BoxContainer.ALIGNMENT_CENTER
	row.add_theme_constant_override("separation", 40)

	var label1 := Label.new()
	label1.text = col1
	label1.custom_minimum_size = Vector2(200, 0)
	label1.horizontal_alignment = HORIZONTAL_ALIGNMENT_LEFT
	if is_header:
		label1.add_theme_font_size_override("font_size", 18)
	row.add_child(label1)

	var label2 := Label.new()
	label2.text = col2
	label2.custom_minimum_size = Vector2(150, 0)
	label2.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	if is_header:
		label2.add_theme_font_size_override("font_size", 18)
	row.add_child(label2)

	var label3 := Label.new()
	label3.text = col3
	label3.custom_minimum_size = Vector2(150, 0)
	label3.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	if is_header:
		label3.add_theme_font_size_override("font_size", 18)
	row.add_child(label3)

	return row


## Format a score integer with comma separators for readability.
func _format_score(score: int) -> String:
	var score_str := str(score)
	if score < 1000:
		return score_str
	# Add comma separators.
	var result := ""
	var count := 0
	for i in range(score_str.length() - 1, -1, -1):
		if count > 0 and count % 3 == 0:
			result = "," + result
		result = score_str[i] + result
		count += 1
	return result


# ─── Navigation ─────────────────────────────────────────────────────────────────

## Return to the GameTable scene to continue playing.
func _on_continue_pressed() -> void:
	get_tree().change_scene_to_file("res://scenes/GameTable.tscn")
