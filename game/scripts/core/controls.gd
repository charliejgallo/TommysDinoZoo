extends Node
## Input actions, made in code so each player can get its own devices.
## Player 1 (index 0): arrows + WASD, A = Z/Space/Enter, B = X, menu = Esc,
## and every joypad while single player. A second player would get
## `p2_*` actions bound to one joypad (see bind_player).
##
## Game code asks `Controls.move(p)`, `Controls.pressed(p, "a")`, etc.

const DEADZONE := 0.25

func _ready() -> void:
	bind_player(0, -1, true)

func bind_player(p: int, joy_device: int, keyboard: bool) -> void:
	var pre := "p%d_" % (p + 1)
	var keys := {
		"up": [KEY_UP, KEY_W], "down": [KEY_DOWN, KEY_S],
		"left": [KEY_LEFT, KEY_A], "right": [KEY_RIGHT, KEY_D],
		"a": [KEY_Z, KEY_SPACE, KEY_ENTER, KEY_KP_ENTER], "b": [KEY_X],
		"menu": [KEY_ESCAPE],
	}
	var buttons := {
		"up": [JOY_BUTTON_DPAD_UP], "down": [JOY_BUTTON_DPAD_DOWN],
		"left": [JOY_BUTTON_DPAD_LEFT], "right": [JOY_BUTTON_DPAD_RIGHT],
		"a": [JOY_BUTTON_A], "b": [JOY_BUTTON_B], "menu": [JOY_BUTTON_START],
	}
	var axes := {
		"up": [JOY_AXIS_LEFT_Y, -1.0], "down": [JOY_AXIS_LEFT_Y, 1.0],
		"left": [JOY_AXIS_LEFT_X, -1.0], "right": [JOY_AXIS_LEFT_X, 1.0],
	}
	for act in keys:
		var name: String = pre + act
		if InputMap.has_action(name):
			InputMap.erase_action(name)
		InputMap.add_action(name, DEADZONE)
		if keyboard:
			for k in keys[act]:
				var e := InputEventKey.new()
				e.physical_keycode = k
				InputMap.action_add_event(name, e)
		for b in buttons.get(act, []):
			var e := InputEventJoypadButton.new()
			e.button_index = b
			e.device = joy_device
			InputMap.action_add_event(name, e)
		if axes.has(act):
			var e := InputEventJoypadMotion.new()
			e.axis = axes[act][0]
			e.axis_value = axes[act][1]
			e.device = joy_device
			InputMap.action_add_event(name, e)
	# menu navigation for UI uses the built-in ui_* actions; add joypad A/B
	# and our keys to them once
	if p == 0:
		_extend("ui_accept", [KEY_Z, KEY_SPACE, KEY_ENTER], [JOY_BUTTON_A])
		_extend("ui_cancel", [KEY_X, KEY_ESCAPE], [JOY_BUTTON_B])
		_extend("ui_up", [KEY_W], [])
		_extend("ui_down", [KEY_S], [])
		_extend("ui_left", [KEY_A], [])
		_extend("ui_right", [KEY_D], [])

func _extend(action: String, ks: Array, bs: Array) -> void:
	for k in ks:
		var e := InputEventKey.new()
		e.physical_keycode = k
		if not InputMap.action_has_event(action, e):
			InputMap.action_add_event(action, e)
	for b in bs:
		var e := InputEventJoypadButton.new()
		e.button_index = b
		e.device = -1
		if not InputMap.action_has_event(action, e):
			InputMap.action_add_event(action, e)

func move(p: int) -> Vector2:
	var pre := "p%d_" % (p + 1)
	return Input.get_vector(pre + "left", pre + "right", pre + "up", pre + "down", DEADZONE)

func pressed(p: int, act: String) -> bool:
	return Input.is_action_just_pressed("p%d_%s" % [p + 1, act])

func held(p: int, act: String) -> bool:
	return Input.is_action_pressed("p%d_%s" % [p + 1, act])

func released(p: int, act: String) -> bool:
	return Input.is_action_just_released("p%d_%s" % [p + 1, act])

## Last device used, for showing keyboard or joypad glyphs.
var using_joypad := false

func _input(e: InputEvent) -> void:
	if e is InputEventJoypadButton or (e is InputEventJoypadMotion and abs(e.axis_value) > 0.5):
		using_joypad = true
	elif e is InputEventKey:
		using_joypad = false
