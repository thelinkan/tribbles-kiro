## ReconnectionOverlay script.
## Displays a modal overlay when the network connection is lost and hides
## itself when the connection is restored. Listens to NetworkClient signals.
extends Node

@onready var _panel: Panel = $"../Panel"
@onready var _status_label: Label = $"../Panel/VBox/StatusLabel"
@onready var _attempt_label: Label = $"../Panel/VBox/AttemptLabel"


func _ready() -> void:
	_panel.visible = false
	NetworkClient.disconnected.connect(_on_disconnected)
	NetworkClient.reconnecting.connect(_on_reconnecting)
	NetworkClient.connected.connect(_on_connected)
	NetworkClient.reconnection_failed.connect(_on_reconnection_failed)


func _on_disconnected() -> void:
	_status_label.text = tr("UI_CONNECTION_LOST")
	_attempt_label.text = tr("UI_RECONNECTING")
	_panel.visible = true


func _on_reconnecting(attempt: int) -> void:
	_attempt_label.text = tr("UI_RECONNECTING") + " (%d/%d)" % [attempt, NetworkClient.MAX_RECONNECT_ATTEMPTS]


func _on_connected() -> void:
	_panel.visible = false


func _on_reconnection_failed() -> void:
	_status_label.text = tr("UI_RECONNECTION_FAILED")
	_attempt_label.text = ""
