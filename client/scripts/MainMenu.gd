## MainMenu — navigation hub after login.
## Provides buttons to navigate to Deck Builder, Lobby, Settings, and Log Out.
extends Control

@onready var title_label: Label = %TitleLabel
@onready var deck_builder_button: Button = %DeckBuilderButton
@onready var lobby_button: Button = %LobbyButton
@onready var settings_button: Button = %SettingsButton
@onready var logout_button: Button = %LogoutButton


func _ready() -> void:
	title_label.text = tr("UI_MAIN_MENU_TITLE")
	deck_builder_button.text = tr("UI_DECK_BUILDER")
	lobby_button.text = tr("UI_LOBBY")
	settings_button.text = tr("UI_SETTINGS")
	logout_button.text = tr("UI_LOGOUT")

	deck_builder_button.pressed.connect(_on_deck_builder)
	lobby_button.pressed.connect(_on_lobby)
	settings_button.pressed.connect(_on_settings)
	logout_button.pressed.connect(_on_logout)


func _on_deck_builder() -> void:
	get_tree().change_scene_to_file("res://scenes/DeckBuilder.tscn")


func _on_lobby() -> void:
	get_tree().change_scene_to_file("res://scenes/LobbyScreen.tscn")


func _on_settings() -> void:
	get_tree().change_scene_to_file("res://scenes/SettingsScreen.tscn")


func _on_logout() -> void:
	NetworkClient.disconnect_from_server()
	get_tree().change_scene_to_file("res://scenes/LoginScreen.tscn")
