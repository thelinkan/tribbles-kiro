## Settings autoload singleton.
## Persists user preferences (language, server address, etc.) to a local
## configuration file. Loads settings on startup and saves on change.
extends Node

# ─── Signals ────────────────────────────────────────────────────────────────────
## Emitted when the language setting changes.
signal language_changed(locale: String)

# ─── Constants ──────────────────────────────────────────────────────────────────
## Path to the user settings file.
const SETTINGS_PATH: String = "user://settings.cfg"
## Default locale if no preference is saved.
const DEFAULT_LOCALE: String = "en"
## Supported locales.
const SUPPORTED_LOCALES: PackedStringArray = PackedStringArray(["en", "sv"])

# ─── State ──────────────────────────────────────────────────────────────────────
## The currently active locale code.
var current_locale: String = DEFAULT_LOCALE
## The last used server address.
var server_address: String = ""

## Internal config file reference.
var _config: ConfigFile = null


# ─── Lifecycle ──────────────────────────────────────────────────────────────────

func _ready() -> void:
	_config = ConfigFile.new()
	_load_settings()
	_apply_locale(current_locale)


# ─── Public API ─────────────────────────────────────────────────────────────────

## Set the interface language. Persists the choice and triggers re-render.
## locale: A locale code from SUPPORTED_LOCALES (e.g., "en" or "sv").
func set_language(locale: String) -> void:
	if locale not in SUPPORTED_LOCALES:
		push_warning("Settings: Unsupported locale '%s'. Supported: %s" % [locale, str(SUPPORTED_LOCALES)])
		return

	if locale == current_locale:
		return

	current_locale = locale
	_apply_locale(locale)
	_save_settings()
	language_changed.emit(locale)


## Set the server address and persist it.
## address: The server WebSocket URL (e.g., "ws://192.168.1.100:8080").
func set_server_address(address: String) -> void:
	server_address = address
	_save_settings()


## Get the list of supported locale codes.
func get_supported_locales() -> PackedStringArray:
	return SUPPORTED_LOCALES


# ─── Private Methods ────────────────────────────────────────────────────────────

## Load settings from the config file on disk.
func _load_settings() -> void:
	var err := _config.load(SETTINGS_PATH)
	if err != OK:
		# No settings file yet; use defaults.
		return

	current_locale = _config.get_value("general", "locale", DEFAULT_LOCALE)
	server_address = _config.get_value("general", "server_address", "")

	# Validate loaded locale.
	if current_locale not in SUPPORTED_LOCALES:
		current_locale = DEFAULT_LOCALE


## Save current settings to the config file on disk.
func _save_settings() -> void:
	_config.set_value("general", "locale", current_locale)
	_config.set_value("general", "server_address", server_address)
	var err := _config.save(SETTINGS_PATH)
	if err != OK:
		push_error("Settings: Failed to save settings (error %d)" % err)


## Apply the given locale to Godot's TranslationServer.
func _apply_locale(locale: String) -> void:
	TranslationServer.set_locale(locale)
