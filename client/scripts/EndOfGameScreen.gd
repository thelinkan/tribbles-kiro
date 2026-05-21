## EndOfGameScreen — displays final rankings (highest to lowest) and clearly
## indicates the winner. Reads payload data from NetworkClient.game_end_data.
## Shows a "Return to Lobby" button.
extends Control

# ─── Node References ────────────────────────────────────────────────────────────
@onready var title_label: Label = %TitleLabel
@onready var winner_label: Label = %WinnerLabel
@onready var rankings_container: VBoxContainer = %RankingsContainer
@onready var lobby_button: Button = %LobbyButton


# ─── Lifecycle ──────────────────────────────────────────────────────────────────

func _ready() -> void:
	title_label.text = tr("UI_END_GAME_TITLE")
	lobby_button.text = tr("UI_RETURN_TO_LOBBY")
	lobby_button.pressed.connect(_on_lobby_pressed)

	_populate_results()


# ─── Results Display ────────────────────────────────────────────────────────────

## Populate the winner display and rankings from NetworkClient.game_end_data.
func _populate_results() -> void:
	var data: Dictionary = NetworkClient.game_end_data
	var final_scores: Dictionary = data.get("final_scores", {})
	var winner: String = data.get("winner", "")

	# Display winner prominently.
	if winner != "":
		winner_label.text = "%s: %s" % [tr("UI_END_GAME_WINNER"), winner]
		winner_label.visible = true
	else:
		winner_label.visible = false

	if final_scores.is_empty():
		var empty_label := Label.new()
		empty_label.text = "No score data available."
		empty_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		rankings_container.add_child(empty_label)
		return

	# Sort players by score (highest to lowest).
	var sorted_players: Array = []
	for player_key in final_scores:
		var score: int = int(final_scores[player_key])
		sorted_players.append({"name": str(player_key), "score": score})

	sorted_players.sort_custom(_compare_scores_descending)

	# Add header row.
	var header := _create_ranking_row(tr("UI_RANK"), tr("UI_PLAYER"), tr("UI_END_GAME_FINAL_SCORES"), true, false)
	rankings_container.add_child(header)

	# Add separator.
	var separator := HSeparator.new()
	rankings_container.add_child(separator)

	# Add each player's ranking.
	for i in range(sorted_players.size()):
		var entry: Dictionary = sorted_players[i]
		var rank_str := str(i + 1)
		var player_name: String = entry["name"]
		var score_str := _format_score(entry["score"])
		var is_winner: bool = (player_name == winner)

		var row := _create_ranking_row(rank_str, player_name, score_str, false, is_winner)
		rankings_container.add_child(row)


## Custom sort comparator: highest score first.
func _compare_scores_descending(a: Dictionary, b: Dictionary) -> bool:
	return a["score"] > b["score"]


## Create a ranking row with rank, player name, and score columns.
func _create_ranking_row(rank: String, player_name: String, score: String, is_header: bool, is_winner: bool) -> HBoxContainer:
	var row := HBoxContainer.new()
	row.alignment = BoxContainer.ALIGNMENT_CENTER
	row.add_theme_constant_override("separation", 30)

	var rank_label := Label.new()
	rank_label.text = rank
	rank_label.custom_minimum_size = Vector2(40, 0)
	rank_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	if is_header:
		rank_label.add_theme_font_size_override("font_size", 18)
	if is_winner:
		rank_label.add_theme_font_size_override("font_size", 22)
		rank_label.add_theme_color_override("font_color", Color(1.0, 0.84, 0.0))
	row.add_child(rank_label)

	var name_label := Label.new()
	name_label.text = player_name
	name_label.custom_minimum_size = Vector2(200, 0)
	name_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_LEFT
	if is_header:
		name_label.add_theme_font_size_override("font_size", 18)
	if is_winner:
		name_label.add_theme_font_size_override("font_size", 22)
		name_label.add_theme_color_override("font_color", Color(1.0, 0.84, 0.0))
	row.add_child(name_label)

	var score_label := Label.new()
	score_label.text = score
	score_label.custom_minimum_size = Vector2(150, 0)
	score_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	if is_header:
		score_label.add_theme_font_size_override("font_size", 18)
	if is_winner:
		score_label.add_theme_font_size_override("font_size", 22)
		score_label.add_theme_color_override("font_color", Color(1.0, 0.84, 0.0))
	row.add_child(score_label)

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

## Return to the lobby screen.
func _on_lobby_pressed() -> void:
	get_tree().change_scene_to_file("res://scenes/LobbyScreen.tscn")
