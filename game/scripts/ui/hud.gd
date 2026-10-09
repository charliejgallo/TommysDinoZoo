extends CanvasLayer
## In-game HUD: three inventory slots (bottom), coins (top left), day and
## clock (top right), the action prompt over the current target, toasts,
## the photo flash and the end-of-day summary.

signal summary_closed()

const CREAM := Color("#fff7e6")
const BROWN := Color("#7a5236")
const GOLD := Color("#ffcf4a")
const SLOT := 104

var player: Player
var slot_panels: Array[Panel] = []
var slot_icons: Array[TextureRect] = []
var coins_label: Label
var clock_label: Label
var clock_icon: TextureRect
var prompt: PanelContainer
var prompt_label: Label
var prompt_key: Label
var prompt_icon: TextureRect
var toast_box: PanelContainer
var toast_label: Label
var toast_icon: TextureRect
var flash_rect: ColorRect
var summary: Control
var _toast_tw: Tween
var _root: Control

static func box(bg: Color, border: Color, radius := 22, bw := 4) -> StyleBoxFlat:
	var s := StyleBoxFlat.new()
	s.bg_color = bg
	s.border_color = border
	s.set_border_width_all(bw)
	s.set_corner_radius_all(radius)
	s.shadow_color = Color(0, 0, 0, 0.18)
	s.shadow_size = 6
	s.shadow_offset = Vector2(0, 3)
	s.content_margin_left = 14
	s.content_margin_right = 14
	s.content_margin_top = 8
	s.content_margin_bottom = 8
	return s

static func label(text: String, size := 30, color := BROWN) -> Label:
	var l := Label.new()
	l.text = text
	l.add_theme_font_size_override("font_size", size)
	l.add_theme_color_override("font_color", color)
	return l

func _ready() -> void:
	_root = Control.new()
	_root.set_anchors_preset(Control.PRESET_FULL_RECT)
	_root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_root.theme = UiTheme.get_theme()
	add_child(_root)
	_build_slots()
	_build_top()
	_build_prompt()
	_build_toast()
	flash_rect = ColorRect.new()
	flash_rect.color = Color(1, 1, 1, 0)
	flash_rect.set_anchors_preset(Control.PRESET_FULL_RECT)
	flash_rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_root.add_child(flash_rect)
	Game.coins_changed.connect(func(c): coins_label.text = str(c))
	Icons.icon_ready.connect(_on_icon_ready)

func bind(p: Player) -> void:
	player = p
	p.slots_changed.connect(_refresh_slots)
	p.target_changed.connect(_on_target)
	_refresh_slots()

func _build_slots() -> void:
	var hb := HBoxContainer.new()
	hb.add_theme_constant_override("separation", 14)
	hb.set_anchors_and_offsets_preset(Control.PRESET_CENTER_BOTTOM)
	hb.offset_top = -SLOT - 28
	hb.offset_bottom = -28
	hb.offset_left = -(SLOT * 4 + 42) / 2.0
	hb.offset_right = (SLOT * 4 + 42) / 2.0
	hb.alignment = BoxContainer.ALIGNMENT_CENTER
	_root.add_child(hb)
	for i in 4:
		var p := Panel.new()
		p.custom_minimum_size = Vector2(SLOT, SLOT)
		p.pivot_offset = Vector2(SLOT, SLOT) / 2.0
		hb.add_child(p)
		var tr_ := TextureRect.new()
		tr_.set_anchors_preset(Control.PRESET_FULL_RECT)
		tr_.offset_left = 10
		tr_.offset_top = 10
		tr_.offset_right = -10
		tr_.offset_bottom = -10
		tr_.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		tr_.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		p.add_child(tr_)
		slot_panels.append(p)
		slot_icons.append(tr_)

func _build_top() -> void:
	var coins := PanelContainer.new()
	coins.add_theme_stylebox_override("panel", box(CREAM, BROWN))
	coins.position = Vector2(24, 20)
	_root.add_child(coins)
	var hb := HBoxContainer.new()
	hb.add_theme_constant_override("separation", 8)
	coins.add_child(hb)
	var ci := TextureRect.new()
	ci.texture = Icons.get_icon("coin")
	ci.custom_minimum_size = Vector2(44, 44)
	ci.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	ci.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	hb.add_child(ci)
	coins_label = label(str(Game.coins), 34)
	hb.add_child(coins_label)
	var clock := PanelContainer.new()
	clock.add_theme_stylebox_override("panel", box(CREAM, BROWN))
	clock.set_anchors_and_offsets_preset(Control.PRESET_TOP_RIGHT)
	clock.offset_left = -260
	clock.offset_right = -24
	clock.offset_top = 20
	_root.add_child(clock)
	var hb2 := HBoxContainer.new()
	hb2.add_theme_constant_override("separation", 8)
	clock.add_child(hb2)
	clock_icon = TextureRect.new()
	clock_icon.custom_minimum_size = Vector2(44, 44)
	clock_icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	clock_icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	hb2.add_child(clock_icon)
	clock_label = label("", 30)
	hb2.add_child(clock_label)

func _build_prompt() -> void:
	prompt = PanelContainer.new()
	prompt.add_theme_stylebox_override("panel", box(CREAM, BROWN, 26, 3))
	prompt.visible = false
	_root.add_child(prompt)
	var hb := HBoxContainer.new()
	hb.add_theme_constant_override("separation", 8)
	prompt.add_child(hb)
	var key := PanelContainer.new()
	key.add_theme_stylebox_override("panel", box(Color("#5cc46a"), Color("#2f7d3b"), 18, 3))
	prompt_key = label("A", 24, Color.WHITE)
	key.add_child(prompt_key)
	hb.add_child(key)
	prompt_icon = TextureRect.new()
	prompt_icon.custom_minimum_size = Vector2(38, 38)
	prompt_icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	prompt_icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	hb.add_child(prompt_icon)
	prompt_label = label("", 26)
	hb.add_child(prompt_label)

func _build_toast() -> void:
	toast_box = PanelContainer.new()
	toast_box.add_theme_stylebox_override("panel", box(CREAM, GOLD.darkened(0.2), 26, 4))
	toast_box.set_anchors_and_offsets_preset(Control.PRESET_CENTER_TOP)
	toast_box.offset_top = 96
	toast_box.grow_horizontal = Control.GROW_DIRECTION_BOTH
	toast_box.modulate.a = 0.0
	_root.add_child(toast_box)
	var hb := HBoxContainer.new()
	hb.add_theme_constant_override("separation", 10)
	toast_box.add_child(hb)
	toast_icon = TextureRect.new()
	toast_icon.custom_minimum_size = Vector2(44, 44)
	toast_icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	toast_icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	hb.add_child(toast_icon)
	toast_label = label("", 28)
	hb.add_child(toast_label)

# ---------------------------------------------------------------- updates

func _process(_dt: float) -> void:
	clock_label.text = "%s %d · %s" % [tr("hud.day"), Game.day, Game.clock_text()]
	clock_icon.texture = Icons.get_icon("moon" if Game.hour >= 19.5 else "sun")
	_place_prompt()
	if summary and summary.visible:
		if Input.is_action_just_pressed("ui_accept") or Controls.pressed(0, "a"):
			_close_summary()

func _refresh_slots() -> void:
	if player == null:
		return
	for i in slot_panels.size():
		slot_panels[i].visible = i < player.slots.size()
		if i >= player.slots.size():
			continue
		var active := i == player.active
		var s := box(CREAM if active else Color(1, 0.97, 0.9, 0.82), GOLD.darkened(0.15) if active else BROWN.lightened(0.3), 24, 6 if active else 3)
		slot_panels[i].add_theme_stylebox_override("panel", s)
		slot_panels[i].scale = Vector2.ONE * (1.12 if active else 0.94)
		var id: String = player.slots[i]
		slot_icons[i].texture = Icons.item_icon(id) if id != "" else null

func _on_icon_ready(_name: String) -> void:
	_refresh_slots()

func _on_target(info: Dictionary) -> void:
	if info.is_empty():
		prompt.visible = false
		return
	prompt.visible = true
	prompt_label.text = tr("verb." + info.verb)
	Game.speak(prompt_label.text)
	prompt_key.text = "A" if Controls.using_joypad else "Z"
	prompt_icon.texture = Icons.get_icon("verb_" + info.get("icon", info.verb))
	prompt.modulate = Color(1, 1, 1, 0.6) if info.get("disabled", false) else Color.WHITE

func _place_prompt() -> void:
	if not prompt.visible or player == null:
		return
	var cam := get_viewport().get_camera_3d()
	if cam == null:
		return
	var t = player.target
	var at: Vector3 = player.global_position + Vector3(0, 1.4, 0)
	if t and is_instance_valid(t):
		var ip: Vector3 = t.interact_point() if t.has_method("interact_point") else t.global_position
		at = ip + Vector3(0, 0.9, 0)
	var sp := cam.unproject_position(at)
	prompt.reset_size()
	prompt.position = sp - Vector2(prompt.size.x / 2.0, prompt.size.y)

func toast(text: String, icon := "") -> void:
	toast_label.text = text
	Game.speak(text, false)
	toast_icon.texture = Icons.get_icon(icon) if icon != "" else null
	toast_icon.visible = icon != ""
	toast_box.reset_size()
	toast_box.offset_left = -toast_box.size.x / 2.0
	toast_box.offset_right = toast_box.size.x / 2.0
	if _toast_tw:
		_toast_tw.kill()
	_toast_tw = create_tween()
	_toast_tw.tween_property(toast_box, "modulate:a", 1.0, 0.2)
	_toast_tw.tween_interval(2.6)
	_toast_tw.tween_property(toast_box, "modulate:a", 0.0, 0.5)

func flash() -> void:
	flash_rect.color.a = 0.85
	create_tween().tween_property(flash_rect, "color:a", 0.0, 0.35)

# ---------------------------------------------------------------- day summary

func show_day_summary(s: Dictionary) -> void:
	if summary:
		summary.queue_free()
	summary = ColorRect.new()
	summary.color = Color(0.12, 0.13, 0.28, 0.0)
	summary.set_anchors_preset(Control.PRESET_FULL_RECT)
	_root.add_child(summary)
	create_tween().tween_property(summary, "color:a", 0.92, 0.8)
	var panel := PanelContainer.new()
	panel.add_theme_stylebox_override("panel", box(CREAM, BROWN, 36, 5))
	panel.set_anchors_and_offsets_preset(Control.PRESET_CENTER)
	panel.grow_horizontal = Control.GROW_DIRECTION_BOTH
	panel.grow_vertical = Control.GROW_DIRECTION_BOTH
	summary.add_child(panel)
	var vb := VBoxContainer.new()
	vb.add_theme_constant_override("separation", 12)
	vb.custom_minimum_size = Vector2(620, 0)
	panel.add_child(vb)
	var title := label(tr("summary.title") % s.day, 44)
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	vb.add_child(title)
	vb.add_child(_line("heart", tr("summary.happy") % [s.happy, s.dinos]))
	vb.add_child(_line("coin", tr("summary.coins") % s.coins))
	for g in s.grew:
		vb.add_child(_line("star", tr("summary.grew") % [g[0], tr("age." + g[2])]))
	for h in s.hatched:
		vb.add_child(_line("egg", tr("summary.hatched") % Content.dino_name(h[1])))
	var best := _best_moment(s.today)
	if best != "":
		vb.add_child(_line("sparkle", best))
	Game.speak(tr("summary.title") % s.day + ". " + tr("summary.happy") % [s.happy, s.dinos] + ". " + tr("summary.bye"))
	var bye := label(tr("summary.bye"), 40, Color("#e0703c"))
	bye.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	vb.add_child(bye)
	var hint := label(tr("summary.continue") % ("A" if Controls.using_joypad else "Z"), 26, BROWN.lightened(0.2))
	hint.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	vb.add_child(hint)

func _line(icon: String, text: String) -> Control:
	var hb := HBoxContainer.new()
	hb.add_theme_constant_override("separation", 12)
	var ti := TextureRect.new()
	ti.texture = Icons.get_icon(icon)
	ti.custom_minimum_size = Vector2(48, 48)
	ti.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	ti.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	hb.add_child(ti)
	hb.add_child(label(text, 30))
	return hb

func _best_moment(today: Dictionary) -> String:
	var best := ""
	var n := 0
	for k in today:
		if k.begins_with("pet_") and today[k] > n:
			n = today[k]
			best = tr("summary.pets") % [Content.dino_name(k.substr(4)), n]
	return best

func _close_summary() -> void:
	var s := summary
	summary = null
	var tw := create_tween()
	tw.tween_property(s, "modulate:a", 0.0, 0.5)
	tw.tween_callback(s.queue_free)
	summary_closed.emit()
