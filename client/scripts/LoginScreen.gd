## LoginScreen — handles login and registration flow.
## Provides server address, username, password fields with a toggle between
## login and registration modes. On success, stores the session token in
## NetworkClient and navigates to MainMenu.
extends Control

# ─── Node References ────────────────────────────────────────────────────────────
@onready var title_label: Label = %TitleLabel
@onready var server_address_field: LineEdit = %ServerAddressField
@onready var username_field: LineEdit = %UsernameField
@onready var password_field: LineEdit = %PasswordField
@onready var email_field: LineEdit = %EmailField
@onready var action_button: Button = %ActionButton
@onready var toggle_button: Button = %ToggleButton
@onready var error_label: Label = %ErrorLabel

# ─── State ──────────────────────────────────────────────────────────────────────
## Whether the screen is currently in registration mode.
var _is_register_mode: bool = false


# ─── Lifecycle ──────────────────────────────────────────────────────────────────

func _ready() -> void:
	# Load persisted server address from Settings.
	server_address_field.text = Settings.server_address

	# Connect UI signals.
	action_button.pressed.connect(_on_action_button_pressed)
	toggle_button.pressed.connect(_on_toggle_button_pressed)

	# Connect network signals.
	NetworkClient.login_response.connect(_on_login_response)
	NetworkClient.register_response.connect(_on_register_response)
	NetworkClient.error_received.connect(_on_error_received)

	# Start in login mode.
	_set_login_mode()


# ─── Mode Switching ─────────────────────────────────────────────────────────────

## Switch to login mode UI.
func _set_login_mode() -> void:
	_is_register_mode = false
	title_label.text = tr("UI_LOGIN_TITLE")
	email_field.visible = false
	action_button.text = tr("UI_LOGIN_BUTTON")
	toggle_button.text = tr("UI_SWITCH_TO_REGISTER")
	error_label.visible = false


## Switch to registration mode UI.
func _set_register_mode() -> void:
	_is_register_mode = true
	title_label.text = tr("UI_REGISTER_TITLE")
	email_field.visible = true
	action_button.text = tr("UI_REGISTER_BUTTON")
	toggle_button.text = tr("UI_SWITCH_TO_LOGIN")
	error_label.visible = false


# ─── Signal Handlers ────────────────────────────────────────────────────────────

## Called when the action button (Login / Register) is pressed.
func _on_action_button_pressed() -> void:
	error_label.visible = false

	var server_url := server_address_field.text.strip_edges()
	var username := username_field.text.strip_edges()
	var password := password_field.text

	# Persist server address.
	Settings.set_server_address(server_url)

	# Connect to server if not already connected.
	if not NetworkClient.is_server_connected():
		NetworkClient.connect_to_server(server_url)

	if _is_register_mode:
		var email := email_field.text.strip_edges()
		NetworkClient.send_message("register", {
			"username": username,
			"password": password,
			"email": email,
		})
	else:
		NetworkClient.send_message("login", {
			"username": username,
			"password": password,
		})


## Called when the toggle button is pressed to switch modes.
func _on_toggle_button_pressed() -> void:
	if _is_register_mode:
		_set_login_mode()
	else:
		_set_register_mode()


## Called when the server responds to a login request.
func _on_login_response(_payload: Dictionary) -> void:
	# Token is already stored by NetworkClient._handle_message.
	get_tree().change_scene_to_file("res://scenes/MainMenu.tscn")


## Called when the server responds to a registration request.
func _on_register_response(_payload: Dictionary) -> void:
	# After successful registration, switch to login mode so the user can log in.
	_set_login_mode()
	# Optionally auto-login: send login with same credentials.
	var username := username_field.text.strip_edges()
	var password := password_field.text
	NetworkClient.send_message("login", {
		"username": username,
		"password": password,
	})


## Called when the server sends an error.
func _on_error_received(payload: Dictionary) -> void:
	var error_code: String = payload.get("code", "")
	var error_message: String = ""

	# Map known error codes to translation keys.
	match error_code:
		"auth_failed":
			error_message = tr("UI_ERROR_AUTH_FAILED")
		"username_taken":
			error_message = tr("UI_ERROR_USERNAME_TAKEN")
		_:
			# Fallback: use the message from the server or a generic error.
			error_message = payload.get("message", tr("UI_ERROR_AUTH_FAILED"))

	error_label.text = error_message
	error_label.visible = true

	# Clear password but NOT username (per requirement 1.10).
	password_field.text = ""
