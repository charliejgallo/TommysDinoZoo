extends Node
## Developer hooks driven by command-line user args (after `--`):
##   --shot=<png>       save a screenshot and quit
##   --shot-after=<s>   seconds to wait before the shot (default 1.5)
##   --scene=<res path> change to that scene at start
##   --keys=<steps>     scripted input for player 1, steps separated by
##                      commas: "up:1.2" holds up 1.2 s, "a" taps A,
##                      "bhold" holds B 0.6 s, "wait:0.5" waits
##   --trace            print player 1's position and target every 0.5 s

var _shot := ""
var _after := 1.5
var _t := 0.0
var _steps := []
var _step_t := 0.0
var _held := ""
var _trace_t := 0.0

func _ready() -> void:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--shot="):
			_shot = a.substr(7)
		elif a.begins_with("--shot-after="):
			_after = float(a.substr(13))
		elif a.begins_with("--shot-after-keys="):
			_after = 99999.0
		elif a.begins_with("--scene="):
			get_tree().change_scene_to_file.call_deferred(a.substr(8))
		elif a.begins_with("--keys="):
			_steps = Array(a.substr(7).split(","))
			_step_t = 1.0   # let the world settle first
	process_mode = Node.PROCESS_MODE_ALWAYS

func arg(name: String, def := "") -> String:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--" + name + "="):
			return a.substr(name.length() + 3)
		if a == "--" + name:
			return "1"
	return def

func _physics_process(dt: float) -> void:
	_run_keys(dt)
	if arg("trace") != "":
		_trace_t += dt
		if _trace_t >= 0.5:
			_trace_t = 0.0
			var p = get_tree().get_first_node_in_group("players")
			if p:
				print("[trace] t=%.1f pos=(%.1f,%.1f) slots=%s target=%s h=%.2f" % [Time.get_ticks_msec() / 1000.0,
					p.global_position.x, p.global_position.z, p.slots, p.target_info.get("verb", "-"), Game.hour])

func _run_keys(dt: float) -> void:
	if _held != "" and _step_t <= 0.0:
		_send(_held, false)
		_held = ""
	if _step_t > 0.0:
		_step_t -= dt
		return
	if _steps.is_empty():
		if _shot != "" and arg("shot-after-keys") != "" and _after > 1000.0:
			_after = _t + float(arg("shot-after-keys"))
		return
	var st: String = _steps.pop_front()
	var parts := st.split(":")
	var act := parts[0]
	var dur := float(parts[1]) if parts.size() > 1 else 0.0
	if act == "wait":
		_step_t = dur
		return
	if act == "bhold":
		act = "b"
		dur = 0.6
	# "ui_*" steps drive menus; anything else is player 1's action
	_held = act if act.begins_with("ui_") else "p1_" + act
	_send(_held, true)
	_step_t = max(dur, 0.05)

func _send(action: String, pressed: bool) -> void:
	var e := InputEventAction.new()
	e.action = action
	e.pressed = pressed
	e.strength = 1.0 if pressed else 0.0
	Input.parse_input_event(e)

func _process(dt: float) -> void:
	if _shot == "":
		return
	_t += dt
	if _t >= _after:
		var img := get_viewport().get_texture().get_image()
		img.save_png(_shot)
		print("[dev] shot ", _shot)
		_shot = ""
		get_tree().quit()
