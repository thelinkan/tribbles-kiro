## DeckBuilder — card search, deck editing, save/load/copy functionality.
## Left panel provides card search with filters (denomination, power, expansion,
## name substring). Right panel shows the current deck with card quantities,
## total count, minimum warning, and save/load/copy buttons.
extends Control

# ─── Constants ──────────────────────────────────────────────────────────────────
## Minimum number of cards required for a deck to be legal for game use.
const MINIMUM_DECK_SIZE: int = 35
## Denomination values used in the game.
const DENOMINATIONS: Array[int] = [1, 10, 100, 1000, 10000, 100000]

# ─── Node References ────────────────────────────────────────────────────────────
@onready var title_label: Label = %TitleLabel
@onready var denomination_filter: OptionButton = %DenominationFilter
@onready var power_filter: LineEdit = %PowerFilter
@onready var expansion_filter: OptionButton = %ExpansionFilter
@onready var name_filter: LineEdit = %NameFilter
@onready var search_button: Button = %SearchButton
@onready var search_results_list: VBoxContainer = %SearchResultsList
@onready var deck_name_field: LineEdit = %DeckNameField
@onready var public_toggle: CheckButton = %PublicToggle
@onready var comment_field: TextEdit = %CommentField
@onready var card_count_label: Label = %CardCountLabel
@onready var minimum_warning: Label = %MinimumWarning
@onready var deck_cards_list: VBoxContainer = %DeckCardsList
@onready var save_button: Button = %SaveButton
@onready var load_button: Button = %LoadButton
@onready var copy_button: Button = %CopyButton
@onready var back_button: Button = %BackButton

# ─── State ──────────────────────────────────────────────────────────────────────
## The current deck's card entries: card_id → {card_id, card_name, denomination, quantity}
var _deck_cards: Dictionary = {}
## The currently loaded deck ID (empty string if new/unsaved deck).
var _current_deck_id: String = ""
## Cached search results from the server.
var _search_results: Array = []


# ─── Lifecycle ──────────────────────────────────────────────────────────────────

func _ready() -> void:
	title_label.text = tr("UI_DECK_BUILDER")

	# Set up denomination filter options.
	denomination_filter.add_item(tr("UI_CARD_FILTER_DENOMINATION") + " (All)", 0)
	for denom in DENOMINATIONS:
		denomination_filter.add_item(str(denom), denom)

	# Set up expansion filter with a default "All" option.
	expansion_filter.add_item(tr("UI_CARD_FILTER_EXPANSION") + " (All)", 0)

	# Connect UI signals.
	search_button.pressed.connect(_on_search_pressed)
	save_button.pressed.connect(_on_save_pressed)
	load_button.pressed.connect(_on_load_pressed)
	copy_button.pressed.connect(_on_copy_pressed)
	back_button.pressed.connect(_on_back_pressed)

	# Connect network signals.
	NetworkClient.card_response.connect(_on_card_response)
	NetworkClient.deck_response.connect(_on_deck_response)

	# Initial UI state.
	_update_card_count_display()


# ─── Card Count & Warning ───────────────────────────────────────────────────────

## Calculate the total number of cards in the deck (sum of all quantities).
func _get_total_card_count() -> int:
	var total: int = 0
	for entry in _deck_cards.values():
		total += entry["quantity"]
	return total


## Update the card count label and minimum warning visibility.
func _update_card_count_display() -> void:
	var total := _get_total_card_count()
	card_count_label.text = tr("UI_DECK_CARD_COUNT") + ": " + str(total)

	# Show warning when deck has fewer than 35 cards.
	minimum_warning.visible = total < MINIMUM_DECK_SIZE


# ─── Deck Card Management ──────────────────────────────────────────────────────

## Add a card to the deck or increment its quantity if already present.
func _add_card_to_deck(card_id: int, card_name: String, denomination: int) -> void:
	if _deck_cards.has(card_id):
		_deck_cards[card_id]["quantity"] += 1
	else:
		_deck_cards[card_id] = {
			"card_id": card_id,
			"card_name": card_name,
			"denomination": denomination,
			"quantity": 1,
		}
	_rebuild_deck_list_ui()
	_update_card_count_display()


## Remove one copy of a card from the deck. Remove entry if quantity reaches zero.
func _remove_card_from_deck(card_id: int) -> void:
	if not _deck_cards.has(card_id):
		return
	_deck_cards[card_id]["quantity"] -= 1
	if _deck_cards[card_id]["quantity"] <= 0:
		_deck_cards.erase(card_id)
	_rebuild_deck_list_ui()
	_update_card_count_display()


## Rebuild the deck cards list UI from current state.
func _rebuild_deck_list_ui() -> void:
	# Clear existing entries.
	for child in deck_cards_list.get_children():
		child.queue_free()

	# Sort entries by denomination first, then card name.
	var sorted_entries: Array = _deck_cards.values()
	sorted_entries.sort_custom(_compare_deck_entries)

	# Create an entry for each card in the deck.
	for entry in sorted_entries:
		var row := HBoxContainer.new()

		var label := Label.new()
		label.text = "%s [%d] (x%d)" % [entry["card_name"], entry["denomination"], entry["quantity"]]
		label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		row.add_child(label)

		var add_btn := Button.new()
		add_btn.text = "+"
		add_btn.custom_minimum_size = Vector2(30, 0)
		var card_id: int = entry["card_id"]
		var card_name: String = entry["card_name"]
		var denomination: int = entry["denomination"]
		add_btn.pressed.connect(_add_card_to_deck.bind(card_id, card_name, denomination))
		row.add_child(add_btn)

		var remove_btn := Button.new()
		remove_btn.text = "-"
		remove_btn.custom_minimum_size = Vector2(30, 0)
		remove_btn.pressed.connect(_remove_card_from_deck.bind(card_id))
		row.add_child(remove_btn)

		deck_cards_list.add_child(row)


# ─── Search ─────────────────────────────────────────────────────────────────────

## Send a card search request to the server with current filter values.
func _on_search_pressed() -> void:
	var filters: Dictionary = {}

	# Denomination filter.
	var denom_index := denomination_filter.selected
	if denom_index > 0:
		filters["denomination"] = DENOMINATIONS[denom_index - 1]

	# Power filter.
	var power_text := power_filter.text.strip_edges()
	if power_text != "":
		filters["power"] = power_text

	# Expansion filter.
	var expansion_index := expansion_filter.selected
	if expansion_index > 0:
		filters["expansion_id"] = expansion_filter.get_item_id(expansion_index)

	# Name substring filter.
	var name_text := name_filter.text.strip_edges()
	if name_text != "":
		filters["name"] = name_text

	NetworkClient.send_message("search_cards", filters)


## Sort comparator: sort by denomination ascending, then card name ascending.
func _compare_deck_entries(a: Dictionary, b: Dictionary) -> bool:
	if a["denomination"] != b["denomination"]:
		return a["denomination"] < b["denomination"]
	return a["card_name"] < b["card_name"]


## Rebuild the search results list UI.
func _rebuild_search_results_ui() -> void:
	# Clear existing results.
	for child in search_results_list.get_children():
		child.queue_free()

	for card in _search_results:
		var row := HBoxContainer.new()

		var label := Label.new()
		label.text = "%s (%d)" % [card.get("card_name", ""), card.get("denomination", 0)]
		label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		row.add_child(label)

		var add_btn := Button.new()
		add_btn.text = "+"
		add_btn.custom_minimum_size = Vector2(30, 0)
		var card_id: int = card.get("card_id", 0)
		var card_name: String = card.get("card_name", "")
		var denomination: int = card.get("denomination", 0)
		add_btn.pressed.connect(_add_card_to_deck.bind(card_id, card_name, denomination))
		row.add_child(add_btn)

		search_results_list.add_child(row)


# ─── Save / Load / Copy ────────────────────────────────────────────────────────

## Save the current deck to the server.
func _on_save_pressed() -> void:
	var deck_data: Dictionary = {
		"deck_name": deck_name_field.text.strip_edges(),
		"is_public": public_toggle.button_pressed,
		"comment": comment_field.text,
		"cards": _build_cards_payload(),
	}
	if _current_deck_id != "":
		deck_data["deck_id"] = _current_deck_id
	NetworkClient.send_message("save_deck", deck_data)


## Request the list of decks from the server for loading.
func _on_load_pressed() -> void:
	NetworkClient.send_message("list_decks", {})


## Copy the current deck on the server.
func _on_copy_pressed() -> void:
	if _current_deck_id == "":
		return
	NetworkClient.send_message("copy_deck", {"deck_id": _current_deck_id})


## Navigate back to the main menu.
func _on_back_pressed() -> void:
	get_tree().change_scene_to_file("res://scenes/MainMenu.tscn")


## Build the cards payload array for save requests.
func _build_cards_payload() -> Array:
	var cards: Array = []
	for entry in _deck_cards.values():
		cards.append({
			"card_id": entry["card_id"],
			"quantity": entry["quantity"],
		})
	return cards


# ─── Network Response Handlers ──────────────────────────────────────────────────

## Handle card search responses from the server.
func _on_card_response(payload: Dictionary) -> void:
	var action: String = payload.get("action", "")
	match action:
		"search_results":
			_search_results = payload.get("cards", [])
			_rebuild_search_results_ui()


## Handle deck-related responses from the server.
func _on_deck_response(payload: Dictionary) -> void:
	var action: String = payload.get("action", "")
	match action:
		"deck_saved":
			_current_deck_id = str(payload.get("deck_id", ""))
		"deck_loaded":
			_load_deck_from_payload(payload)
		"deck_list":
			_show_deck_list(payload.get("decks", []))
		"deck_copied":
			_current_deck_id = str(payload.get("deck_id", ""))


## Load a deck from server payload into the editor.
func _load_deck_from_payload(payload: Dictionary) -> void:
	_current_deck_id = str(payload.get("deck_id", ""))
	deck_name_field.text = payload.get("deck_name", "")
	public_toggle.button_pressed = payload.get("is_public", false)
	comment_field.text = payload.get("comment", "")

	# Rebuild deck cards from payload.
	_deck_cards.clear()
	var cards: Array = payload.get("cards", [])
	for card in cards:
		var card_id: int = card.get("card_id", 0)
		_deck_cards[card_id] = {
			"card_id": card_id,
			"card_name": card.get("card_name", ""),
			"denomination": card.get("denomination", 0),
			"quantity": card.get("quantity", 1),
		}

	_rebuild_deck_list_ui()
	_update_card_count_display()


## Display a list of available decks for loading.
## Each deck entry is shown as a button that loads the selected deck.
func _show_deck_list(decks: Array) -> void:
	# Reuse the search results area to show deck list temporarily.
	for child in search_results_list.get_children():
		child.queue_free()

	for deck in decks:
		var btn := Button.new()
		btn.text = deck.get("deck_name", "Unnamed")
		btn.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		var deck_id: String = str(deck.get("deck_id", ""))
		btn.pressed.connect(_on_deck_selected.bind(deck_id))
		search_results_list.add_child(btn)


## Request loading a specific deck from the server.
func _on_deck_selected(deck_id: String) -> void:
	NetworkClient.send_message("load_deck", {"deck_id": deck_id})
