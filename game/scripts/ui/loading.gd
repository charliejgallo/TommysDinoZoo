extends Control
## Between the title and the farm: the game's logo, a little egg that
## wobbles and a bar that fills while the farm loads in the background.

const TARGET := "res://scenes/main.tscn"
var bar: ProgressBar
var egg: TextureRect
var _t := 0.0
var _shown := 0.0
var _done := false

func _ready() -> void:
	theme = UiTheme.get_theme()
	var bg := ColorRect.new()
	bg.color = Color("#fff7e6")
	bg.set_anchors_preset(Control.PRESET_FULL_RECT)
	add_child(bg)
	var vb := VBoxContainer.new()
	vb.set_anchors_and_offsets_preset(Control.PRESET_CENTER)
	vb.grow_horizontal = Control.GROW_DIRECTION_BOTH
	vb.grow_vertical = Control.GROW_DIRECTION_BOTH
	vb.alignment = BoxContainer.ALIGNMENT_CENTER
	vb.add_theme_constant_override("separation", 18)
	add_child(vb)
	var logo := TextureRect.new()
	logo.texture = load("res://icon.png")
	logo.custom_minimum_size = Vector2(300, 300)
	logo.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	logo.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	vb.add_child(logo)
	var title := Label.new()
	title.text = "Tommy's Dino Zoo"
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.add_theme_font_size_override("font_size", 60)
	title.add_theme_color_override("font_color", UiTheme.ORANGE)
	title.add_theme_color_override("font_outline_color", Color.WHITE)
	title.add_theme_constant_override("outline_size", 14)
	vb.add_child(title)
	var hb := HBoxContainer.new()
	hb.alignment = BoxContainer.ALIGNMENT_CENTER
	hb.add_theme_constant_override("separation", 14)
	vb.add_child(hb)
	egg = TextureRect.new()
	egg.texture = Icons.get_icon("egg")
	egg.custom_minimum_size = Vector2(56, 56)
	egg.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	egg.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	egg.pivot_offset = Vector2(28, 40)
	hb.add_child(egg)
	bar = ProgressBar.new()
	bar.custom_minimum_size = Vector2(420, 30)
	bar.show_percentage = false
	var bg_s := StyleBoxFlat.new()
	bg_s.bg_color = Color("#f3e3c3")
	bg_s.border_color = UiTheme.BROWN.lightened(0.2)
	bg_s.set_border_width_all(3)
	bg_s.set_corner_radius_all(15)
	var fg_s := StyleBoxFlat.new()
	fg_s.bg_color = Color("#8fd46a")
	fg_s.set_corner_radius_all(15)
	bar.add_theme_stylebox_override("background", bg_s)
	bar.add_theme_stylebox_override("fill", fg_s)
	bar.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	hb.add_child(bar)
	var hint := Label.new()
	hint.text = tr("loading.hint")
	hint.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	hint.add_theme_font_size_override("font_size", 26)
	vb.add_child(hint)
	Game.speak(hint.text)
	ResourceLoader.load_threaded_request(TARGET)

func _process(dt: float) -> void:
	_t += dt
	egg.rotation = sin(_t * 9.0) * 0.18
	if _done:
		return
	var prog := []
	var st := ResourceLoader.load_threaded_get_status(TARGET, prog)
	var want: float = (prog[0] if not prog.is_empty() else 0.0) * 0.8
	if st == ResourceLoader.THREAD_LOAD_LOADED:
		want = 0.9
	_shown = move_toward(_shown, want, dt * 1.6)
	bar.value = _shown * 100.0
	# show the screen at least a moment so it doesn't just flicker
	if st == ResourceLoader.THREAD_LOAD_LOADED and _shown >= 0.88 and _t > 0.8:
		_done = true
		bar.value = 95.0
		await get_tree().process_frame
		await get_tree().process_frame
		get_tree().change_scene_to_packed(ResourceLoader.load_threaded_get(TARGET))
	elif st == ResourceLoader.THREAD_LOAD_FAILED:
		_done = true
		get_tree().change_scene_to_file(TARGET)
