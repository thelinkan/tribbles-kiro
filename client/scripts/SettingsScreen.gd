## SettingsScreen — language selection and user preferences.
## Provides a language dropdown (English, Swedish) that persists the choice
## via the Settings autoload and updates TranslationServer in real time.
extends Control

# ─── Node References ────────────────────────────────────────────────────────────
@onready var title_label: Label = %TitleLabel
@onready var language_label: Label = %LanguageLabel
@onready var language_dropdown: OptionButton = %LanguageDropdown
@onready var back_button: Button = %BackButton

# ─── Constants ──────────────────────────────────────────────────────────────────
## Locale codes matching the dropdown item indices.
var _locale_codes: Array[String] = ["en", "sv"]


# ─── Lifecycle ──────────────────────────────────────────────────────────────────

func _ready() -> void:
	# Set localised text.
	title_label.text = tr("UI_SETTINGS")
	language_label.text = tr("UI_SETTINGS_LANGUAGE")

	# Populate language dropdown.
	language_dropdown.clear()
	language_dropdown.add_item(tr("UI_SETTINGS_LANGUAGE_EN"), 0)
	language_dropdown.add_item(tr("UI_SETTINGS_LANGUAGE_SV"), 1)

	# Set dropdown to current locale.
	var current_index := _locale_codes.find(Settings.current_locale)
	if current_index >= 0:
		language_dropdown.selected = current_index

	# Connect signals.
	language_dropdown.item_selected.connect(_on_language_selected)
	back_button.pressed.connect(_on_back_pressed)

	# Listen for language changes to update UI text dynamically.
	Settings.language_changed.connect(_on_language_changed)


# ─── Signal Handlers ────────────────────────────────────────────────────────────

## Called when the player selects a language from the dropdown.
func _on_language_selected(index: int) -> void:
	if index < 0 or index >= _locale_codes.size():
		return
	var locale := _locale_codes[index]
	Settings.set_language(locale)


## Called when the language changes — refresh all localised text.
func _on_language_changed(_locale: String) -> void:
	title_label.text = tr("UI_SETTINGS")
	language_label.text = tr("UI_SETTINGS_LANGUAGE")

	# Update dropdown item text without changing selection.
	language_dropdown.set_item_text(0, tr("UI_SETTINGS_LANGUAGE_EN"))
	language_dropdown.set_item_text(1, tr("UI_SETTINGS_LANGUAGE_SV"))


## Navigate back to the main menu.
func _on_back_pressed() -> void:
	get_tree().change_scene_to_file("res://scenes/MainMenu.tscn")
