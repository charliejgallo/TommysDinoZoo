class_name Menus
extends CanvasLayer
## Title, save slots, pause and settings pages. Everything is navigable
## with arrows/joypad + A/B (B goes back); the mouse also works.
## Settings include the day length (15-90 min) for parents.

signal closed()

var in_game := false
var shop_open := false
var _root: Control
var _stack: Array[Control] = []

func _ready() -> void:
	layer = 20
	process_mode = Node.PROCESS_MODE_ALWAYS
	_root = Control.new()
	_root.set_anchors_preset(Control.PRESET_FULL_RECT)
	_root.theme = UiTheme.get_theme()
	_root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_root)

func is_open() -> bool:
	return not _stack.is_empty()

func _unhandled_input(e: InputEvent) -> void:
	if _stack.is_empty():
		return
	if e.is_action_pressed("ui_cancel"):
		get_viewport().set_input_as_handled()
		back()

# ---------------------------------------------------------------- pages

func _page(title: String, dim := true) -> VBoxContainer:
	var holder := Control.new()
	holder.set_anchors_preset(Control.PRESET_FULL_RECT)
	if dim:
		var bg := ColorRect.new()
		bg.color = Color(0.1, 0.12, 0.25, 0.55)
		bg.set_anchors_preset(Control.PRESET_FULL_RECT)
		holder.add_child(bg)
	var panel := PanelContainer.new()
	panel.set_anchors_and_offsets_preset(Control.PRESET_CENTER)
	panel.grow_horizontal = Control.GROW_DIRECTION_BOTH
	panel.grow_vertical = Control.GROW_DIRECTION_BOTH
	holder.add_child(panel)
	var vb := VBoxContainer.new()
	vb.add_theme_constant_override("separation", 14)
	vb.custom_minimum_size = Vector2(560, 0)
	panel.add_child(vb)
	if title != "":
		var l := Label.new()
		l.text = title
		l.add_theme_font_size_override("font_size", 44)
		l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		vb.add_child(l)
	for p in _stack:
		p.visible = false
	_root.add_child(holder)
	_stack.append(holder)
	return vb

func _button(vb: Control, text: String, cb: Callable) -> Button:
	var b := Button.new()
	b.text = text
	b.custom_minimum_size = Vector2(0, 68)
	b.pressed.connect(func():
		Sfx.play("ui")
		cb.call())
	b.focus_entered.connect(func(): Sfx.play("ui_move", 0.0, -8.0))
	vb.add_child(b)
	return b

func _focus_first(vb: Control) -> void:
	for c in vb.get_children():
		if c is Button:
			c.grab_focus.call_deferred()
			return
		if c is HBoxContainer:
			for cc in c.get_children():
				if cc is Button:
					cc.grab_focus.call_deferred()
					return

func back() -> void:
	if _stack.is_empty():
		return
	var top: Control = _stack.pop_back()
	top.queue_free()
	if _stack.is_empty():
		shop_open = false
		closed.emit()
	else:
		_stack[-1].visible = true
		_focus_first(_stack[-1].find_children("*", "VBoxContainer", true, false)[0])

func close_all() -> void:
	shop_open = false
	while not _stack.is_empty():
		_stack.pop_back().queue_free()
	closed.emit()

# ---------------------------------------------------------------- title

func show_title() -> void:
	var vb := _page("", false)
	# title: the panel sits on the left so the farm shows on the right
	var panel: Control = vb.get_parent()
	panel.set_anchors_and_offsets_preset(Control.PRESET_CENTER_LEFT)
	panel.offset_left = 70
	panel.grow_horizontal = Control.GROW_DIRECTION_END
	vb.custom_minimum_size = Vector2(440, 0)
	var logo := Label.new()
	logo.text = "Tommy's\nDino Zoo"
	logo.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	logo.add_theme_font_size_override("font_size", 76)
	logo.add_theme_color_override("font_color", UiTheme.ORANGE)
	logo.add_theme_color_override("font_outline_color", Color.WHITE)
	logo.add_theme_constant_override("outline_size", 18)
	vb.add_child(logo)
	_button(vb, tr("menu.play"), show_slots)
	_button(vb, tr("menu.settings"), show_settings)
	_button(vb, tr("menu.quit"), func(): get_tree().quit())
	_focus_first(vb)

func show_slots() -> void:
	var vb := _page(tr("menu.choose_farm"))
	for i in 3:
		var info := Game.slot_info(i)
		var text := tr("menu.new_farm")
		if not info.is_empty():
			text = tr("menu.slot_info") % [info.day, info.dinos, info.coins]
		var n := i
		_button(vb, "%d · %s" % [i + 1, text], func(): _start(n, info.is_empty()))
	_focus_first(vb)

func _start(slot: int, fresh: bool) -> void:
	Game.slot = slot
	Game.flags["_fresh"] = fresh
	close_all()
	get_tree().change_scene_to_file("res://scenes/main.tscn")

# ---------------------------------------------------------------- pause

func show_pause() -> void:
	get_tree().paused = true
	var vb := _page(tr("menu.pause"))
	_button(vb, tr("menu.resume"), close_all)
	_button(vb, tr("menu.album"), show_album)
	_button(vb, tr("menu.settings"), show_settings)
	_button(vb, tr("menu.save_quit"), func():
		Game.save_game()
		close_all()
		get_tree().paused = false
		get_tree().change_scene_to_file("res://scenes/title.tscn"))
	_focus_first(vb)

# ---------------------------------------------------------------- settings

func show_settings() -> void:
	if Game.settings.get("lock_all", false):
		parent_gate(_show_settings_page)
	else:
		_show_settings_page()

func _show_settings_page() -> void:
	var vb := _page(tr("menu.settings"))
	_button(vb, tr("set.page_game"), show_settings_game)
	_button(vb, tr("set.page_access"), show_settings_access)
	_button(vb, tr("set.page_parents"), func(): parent_gate(show_parents))
	_button(vb, tr("menu.back"), func():
		Game.save_settings()
		back())
	_focus_first(vb)

func show_settings_game() -> void:
	var vb := _page(tr("set.page_game"))
	_stepper(vb, "set.camera", ["set.cam_0", "set.cam_1", "set.cam_2", "set.cam_3"].map(func(k): return tr(k)),
		int(Game.settings.camera), func(i): Game.settings.camera = i)
	var locs := Lang.languages.keys()
	locs.sort()
	var cur: String = Game.settings.locale if Game.settings.locale != "" else TranslationServer.get_locale().substr(0, 2)
	_stepper(vb, "set.language", locs.map(func(l): return Lang.languages[l]), max(locs.find(cur), 0),
		func(i):
			Game.settings.locale = locs[i]
			Game.apply_settings())
	var vols := [0.0, 0.25, 0.5, 0.75, 1.0]
	_stepper(vb, "set.music", vols.map(func(v): return "%d%%" % int(v * 100)), _nearest(vols, Game.settings.music),
		func(i):
			Game.settings.music = vols[i]
			Game.apply_settings())
	_stepper(vb, "set.sfx", vols.map(func(v): return "%d%%" % int(v * 100)), _nearest(vols, Game.settings.sfx),
		func(i):
			Game.settings.sfx = vols[i]
			Game.apply_settings())
	var onoff := [tr("set.off"), tr("set.on")]
	_stepper(vb, "set.guide", onoff, 1 if Game.settings.guide_arrow else 0, func(i): Game.settings.guide_arrow = i == 1)
	_stepper(vb, "set.fullscreen", onoff, 1 if Game.settings.fullscreen else 0,
		func(i):
			Game.settings.fullscreen = i == 1
			Game.apply_settings())
	_button(vb, tr("menu.back"), func():
		Game.save_settings()
		back())
	_focus_first(vb)

func show_settings_access() -> void:
	var vb := _page(tr("set.page_access"))
	var onoff := [tr("set.off"), tr("set.on")]
	_stepper(vb, "set.text_size", [tr("set.size_0"), tr("set.size_1"), tr("set.size_2")], int(Game.settings.get("text_size", 0)),
		func(i):
			Game.settings.text_size = i
			Game.apply_settings())
	_stepper(vb, "set.tts", onoff, 1 if Game.settings.get("tts", false) else 0, func(i):
		Game.settings.tts = i == 1
		Game.speak(tr("set.tts_hello")))
	_stepper(vb, "set.autorun", onoff, 1 if Game.settings.get("autorun", true) else 0, func(i): Game.settings.autorun = i == 1)
	_stepper(vb, "set.blur", onoff, 1 if Game.settings.get("blur", true) else 0, func(i): Game.settings.blur = i == 1)
	_stepper(vb, "set.flash", onoff, 1 if Game.settings.get("flash", true) else 0, func(i): Game.settings.flash = i == 1)
	_stepper(vb, "set.rumble", onoff, 1 if Game.settings.get("rumble", true) else 0, func(i):
		Game.settings.rumble = i == 1
		Game.rumble())
	_button(vb, tr("menu.back"), func():
		Game.save_settings()
		back())
	_focus_first(vb)

## For grown-ups: day length, cheap mode, session limit, PIN, play time.
func show_parents() -> void:
	var vb := _page(tr("set.page_parents"))
	var onoff := [tr("set.off"), tr("set.on")]
	_stepper(vb, "set.day_length", Game.DAY_CHOICES.map(func(m): return tr("set.minutes") % m),
		max(Game.DAY_CHOICES.find(int(Game.settings.day_minutes)), 0),
		func(i): Game.settings.day_minutes = Game.DAY_CHOICES[i])
	var limits := [0, 1, 2, 3, 5]
	_stepper(vb, "set.session_days", limits.map(func(n): return tr("set.no_limit") if n == 0 else (tr("set.days") % n)),
		max(limits.find(int(Game.settings.get("session_days", 0))), 0),
		func(i): Game.settings.session_days = limits[i])
	_stepper(vb, "set.cheap", onoff, 1 if Game.settings.get("cheap", false) else 0, func(i): Game.settings.cheap = i == 1)
	_stepper(vb, "set.lock_all", onoff, 1 if Game.settings.get("lock_all", false) else 0, func(i): Game.settings.lock_all = i == 1)
	var pin_b := _button(vb, tr("set.pin_set") if Game.settings.get("pin", "") == "" else tr("set.pin_change"), func():
		show_pin_pad(tr("set.pin_new"), func(p):
			Game.settings.pin = p
			Game.save_settings()
			back()))
	if Game.settings.get("pin", "") != "":
		_button(vb, tr("set.pin_remove"), func():
			Game.settings.pin = ""
			Game.save_settings()
			back()
			show_parents())
	var info := Label.new()
	var d := Game.day if is_instance_valid(get_tree().get_first_node_in_group("world")) else 0
	info.text = tr("set.stats") % [Game.minutes_today(), int(float(Game.settings.play_total_s) / 3600.0),
		int(fmod(float(Game.settings.play_total_s) / 60.0, 60.0)), d]
	info.add_theme_font_size_override("font_size", 24)
	info.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	vb.add_child(info)
	_button(vb, tr("menu.back"), func():
		Game.save_settings()
		back())
	_focus_first(vb)

# ---------------------------------------------------------------- parents' gate

## Run `on_ok` once a grown-up proves it: the PIN if there is one, else a
## multiplication only a grown-up (or a big kid) knows.
func parent_gate(on_ok: Callable) -> void:
	if Game.settings.get("pin", "") != "":
		var check := func(p: String):
			if p == Game.settings.pin:
				back()
				on_ok.call()
			else:
				Sfx.play("nope")
		show_pin_pad(tr("gate.pin"), check, true)
	else:
		_math_gate(on_ok)

func _math_gate(on_ok: Callable) -> void:
	var a := randi_range(6, 9)
	var b := randi_range(6, 9)
	var vb := _page(tr("gate.title"))
	var q := Label.new()
	q.text = tr("gate.question") % [a, b]
	q.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	q.add_theme_font_size_override("font_size", 40)
	vb.add_child(q)
	var answers := [a * b, a * b + randi_range(1, 4) * (1 if randf() < 0.5 else -1), a * (b + 1)]
	answers.shuffle()
	var hb := HBoxContainer.new()
	hb.alignment = BoxContainer.ALIGNMENT_CENTER
	hb.add_theme_constant_override("separation", 14)
	vb.add_child(hb)
	for n in answers:
		var v: int = n
		var bt := Button.new()
		bt.text = str(v)
		bt.custom_minimum_size = Vector2(140, 70)
		bt.pressed.connect(func():
			if v == a * b:
				back()
				on_ok.call()
			else:
				Sfx.play("nope")
				back())
		hb.add_child(bt)
	_button(vb, tr("menu.back"), back)
	hb.get_child(0).grab_focus.call_deferred()

## A 4-digit pad that works with arrows/joypad, the number keys or the mouse.
## `keep_open` leaves the pad up after a wrong code.
func show_pin_pad(title: String, on_done: Callable, keep_open := false) -> void:
	var vb := _page(title)
	var shown := Label.new()
	shown.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	shown.add_theme_font_size_override("font_size", 52)
	vb.add_child(shown)
	var st := {"code": ""}
	var refresh := func():
		shown.text = " ".join(range(4).map(func(i): return "●" if i < st.code.length() else "○"))
	refresh.call()
	var press := func(k: String):
		if k == "⌫":
			st.code = st.code.substr(0, max(st.code.length() - 1, 0))
		elif st.code.length() < 4:
			st.code += k
		refresh.call()
		Sfx.play("ui_move")
		if st.code.length() == 4:
			var c: String = st.code
			st.code = ""
			refresh.call()
			on_done.call(c)
	var grid := GridContainer.new()
	grid.columns = 3
	grid.add_theme_constant_override("h_separation", 10)
	grid.add_theme_constant_override("v_separation", 10)
	var center := CenterContainer.new()
	center.add_child(grid)
	vb.add_child(center)
	for k in ["1", "2", "3", "4", "5", "6", "7", "8", "9", "⌫", "0", ""]:
		var bt := Button.new()
		bt.text = k
		bt.custom_minimum_size = Vector2(96, 72)
		if k == "":
			bt.disabled = true
			bt.modulate.a = 0.0
		else:
			var kk: String = k
			bt.pressed.connect(func(): press.call(kk))
		grid.add_child(bt)
	# number keys on the keyboard
	var catcher := Control.new()
	catcher.set_anchors_preset(Control.PRESET_FULL_RECT)
	catcher.mouse_filter = Control.MOUSE_FILTER_IGNORE
	vb.add_child(catcher)
	vb.set_meta("pin_press", press)
	if title == tr("gate.pin"):
		_button(vb, tr("gate.forgot"), func():
			back()
			_math_gate(func():
				Game.settings.pin = ""
				Game.save_settings()
				show_pin_pad(tr("set.pin_new"), func(p):
					Game.settings.pin = p
					Game.save_settings()
					back())))
	_button(vb, tr("menu.back"), back)
	grid.get_child(0).grab_focus.call_deferred()

func _input(e: InputEvent) -> void:
	# digits typed while a PIN pad is open
	if _stack.is_empty() or not (e is InputEventKey) or not e.pressed:
		return
	var vb := _stack[-1].find_children("*", "VBoxContainer", true, false)
	if vb.is_empty() or not vb[0].has_meta("pin_press"):
		return
	var k: int = e.physical_keycode
	var press: Callable = vb[0].get_meta("pin_press")
	if k >= KEY_0 and k <= KEY_9:
		press.call(str(k - KEY_0))
		get_viewport().set_input_as_handled()
	elif k >= KEY_KP_0 and k <= KEY_KP_9:
		press.call(str(k - KEY_KP_0))
		get_viewport().set_input_as_handled()
	elif k == KEY_BACKSPACE:
		press.call("⌫")
		get_viewport().set_input_as_handled()

# ---------------------------------------------------------------- rest time

## The session's days are used up: a calm "time to rest" card. Going on
## needs a grown-up.
func show_rest(on_continue: Callable) -> void:
	get_tree().paused = true
	var vb := _page(tr("rest.title"))
	var l := Label.new()
	l.text = tr("rest.text")
	l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	l.custom_minimum_size = Vector2(600, 0)
	vb.add_child(l)
	Game.speak(tr("rest.title") + ". " + tr("rest.text"))
	_button(vb, tr("rest.quit"), func():
		close_all()
		get_tree().paused = false
		get_tree().change_scene_to_file("res://scenes/title.tscn"))
	_button(vb, tr("rest.parents"), func():
		parent_gate(func():
			close_all()
			get_tree().paused = false
			on_continue.call()))
	_focus_first(vb)

func _nearest(arr: Array, v: float) -> int:
	var best := 0
	for i in arr.size():
		if abs(arr[i] - v) < abs(arr[best] - v):
			best = i
	return best

## A row "Label   < value >": left/right (or A) changes the value.
func _stepper(vb: Control, key: String, values: Array, index: int, on_change: Callable) -> void:
	var hb := HBoxContainer.new()
	hb.add_theme_constant_override("separation", 12)
	var l := Label.new()
	l.text = tr(key)
	l.custom_minimum_size = Vector2(300, 0)
	l.add_theme_font_size_override("font_size", 28)
	hb.add_child(l)
	var b := Button.new()
	b.custom_minimum_size = Vector2(300, 60)
	var state := {"i": index}
	b.text = "‹  %s  ›" % values[index]
	var step := func(d: int):
		state.i = (state.i + d + values.size()) % values.size()
		b.text = "‹  %s  ›" % values[state.i]
		on_change.call(state.i)
		Sfx.play("ui_move")
	b.pressed.connect(func(): step.call(1))
	b.gui_input.connect(func(e: InputEvent):
		if e.is_action_pressed("ui_left"):
			step.call(-1)
			b.accept_event()
		elif e.is_action_pressed("ui_right"):
			step.call(1)
			b.accept_event())
	hb.add_child(b)
	vb.add_child(hb)

# ---------------------------------------------------------------- board

func show_missions(world: Node) -> void:
	get_tree().paused = true
	var vb := _page(tr("menu.missions"))
	for i in Missions.today.size():
		var m: Dictionary = Missions.today[i]
		var done := Missions.is_done(m)
		var label := "%s   (%d/%d)" % [Missions.text(m), Missions.progress(m), m.n]
		if m.claimed:
			label = "✓ " + Missions.text(m)
		var b := _icon_button(vb, label, "star" if done else "missions",
			("+%d" % m.coins) if not m.claimed else "", func():
				var got := Missions.claim(i)
				if got > 0:
					Sfx.play("mission")
					world.toast(tr("toast.mission_done") % got, "coin")
					back()
					show_missions(world))
		b.disabled = m.claimed or not done
	_button(vb, tr("menu.back"), back)
	_focus_first(vb)

func _icon_button(vb: Control, text: String, icon: String, right: String, cb: Callable) -> Button:
	var b := _button(vb, "", cb)
	b.custom_minimum_size = Vector2(760, 76)
	var hb := HBoxContainer.new()
	hb.set_anchors_preset(Control.PRESET_FULL_RECT)
	hb.offset_left = 16
	hb.offset_right = -20
	hb.add_theme_constant_override("separation", 12)
	hb.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var ti := TextureRect.new()
	ti.texture = Icons.get_icon(icon) if not icon.begins_with("item:") else Icons.item_icon(icon.substr(5))
	ti.custom_minimum_size = Vector2(56, 56)
	ti.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	ti.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	ti.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	hb.add_child(ti)
	var l := Label.new()
	l.text = text
	l.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	l.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	l.add_theme_font_size_override("font_size", 26)
	hb.add_child(l)
	if right != "":
		var r := Label.new()
		r.text = right
		r.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		r.add_theme_color_override("font_color", UiTheme.ORANGE)
		hb.add_child(r)
	b.add_child(hb)
	return b

# ---------------------------------------------------------------- shop

const SHOP_TABS := ["food", "seeds", "tools", "eggs", "furniture"]

func shop_catalog(tab: String, world: Node) -> Array:
	var out := []
	match tab:
		"food", "seeds", "tools":
			var kind: String = {"food": "food", "seeds": "seed", "tools": "tool"}[tab]
			for id in Content.items:
				var d: Dictionary = Content.items[id]
				if tab == "tools" and d.get("kind", "") == "upgrade" and not Game.flags.get(d.get("flag", id), false):
					out.append({"id": id, "price": Game.price(int(d.price)), "name": Content.item_name(id), "icon": "item:" + id, "upgrade": true})
				if d.get("kind", "") == kind and int(d.get("price", 0)) > 0:
					out.append({"id": id, "price": Game.price(int(d.price)), "name": Content.item_name(id), "icon": "item:" + id})
		"eggs":
			for sp in Content.dinos:
				var d: Dictionary = Content.dinos[sp]
				if int(d.get("price", 0)) > 0 and world.is_zone_open(d.get("habitat", "")):
					out.append({"id": "egg_" + sp, "price": Game.price(int(d.price)), "name": tr("shop.egg") % Content.dino_name(sp), "icon": "item:egg_" + sp})
		"furniture":
			for id in Content.props:
				var d: Dictionary = Content.props[id]
				if int(d.get("price", 0)) > 0 and not d.get("fixed", false):
					out.append({"id": "box_" + id, "price": Game.price(int(d.price)), "name": tr("prop." + id), "icon": "item:box_" + id})
	out.sort_custom(func(a, b): return [not a.get("upgrade", false), a.price] < [not b.get("upgrade", false), b.price])
	return out

func show_shop(world: Node, player: Node, tab := 0) -> void:
	get_tree().paused = true
	shop_open = true
	var vb := _page(tr("menu.shop"))
	var tabs := HBoxContainer.new()
	tabs.add_theme_constant_override("separation", 8)
	tabs.alignment = BoxContainer.ALIGNMENT_CENTER
	vb.add_child(tabs)
	var first: Button = null
	for i in SHOP_TABS.size():
		var tb := Button.new()
		tb.text = tr("shop." + SHOP_TABS[i])
		tb.add_theme_font_size_override("font_size", 24)
		tb.toggle_mode = true
		tb.button_pressed = i == tab
		var n := i
		tb.pressed.connect(func():
			back()
			show_shop(world, player, n))
		tabs.add_child(tb)
		if i == tab:
			first = tb
	var coins := Label.new()
	coins.text = tr("shop.coins") % Game.coins
	coins.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	vb.add_child(coins)
	var sc := ScrollContainer.new()
	sc.custom_minimum_size = Vector2(800, 430)
	sc.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	vb.add_child(sc)
	var list := VBoxContainer.new()
	list.add_theme_constant_override("separation", 8)
	sc.add_child(list)
	var items := shop_catalog(SHOP_TABS[tab], world)
	if items.is_empty():
		var l := Label.new()
		l.text = tr("shop.empty")
		list.add_child(l)
	for it in items:
		var b := _icon_button(list, it.name, it.icon, "%d" % it.price, func():
			if not Game.can_pay(it.price):
				Sfx.play("nope")
				world.toast(tr("toast.no_coins"), "coin")
				return
			Game.add_coins(-it.price)
			if it.get("upgrade", false):
				Game.flags[Content.items[it.id].get("flag", it.id)] = true
				player.fit_pockets()
				Sfx.play("mission")
				world.toast(tr("toast.backpack"), "place")
				back()
				show_shop(world, player, 2)
				return
			if not player.give_item(it.id):
				world.spawn_item(it.id, player.front_point(0.9))
				world.toast(tr("toast.on_ground"), "place")
			Sfx.play("buy")
			coins.text = tr("shop.coins") % Game.coins)
		b.disabled = not Game.can_pay(it.price)
		b.focus_entered.connect(func(): sc.ensure_control_visible(b))
	_button(vb, tr("menu.back"), back)
	if first:
		first.grab_focus.call_deferred()

# ---------------------------------------------------------------- naming

## Name a newborn: three suggestions as big buttons (for kids who don't
## write yet) and a text box. Calls on_done(name).
func show_naming(species: String, suggestions: Array, on_done: Callable) -> void:
	get_tree().paused = true
	var vb := _page(tr("name.title") % Content.dino_name(species))
	var pic := TextureRect.new()
	pic.texture = Icons.get_icon("egg")
	pic.custom_minimum_size = Vector2(110, 110)
	pic.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	pic.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	vb.add_child(pic)
	var ask := Label.new()
	ask.text = tr("name.ask")
	ask.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	vb.add_child(ask)
	for n in suggestions:
		var nm: String = n
		_button(vb, nm, func():
			close_all()
			on_done.call(nm))
	var hb := HBoxContainer.new()
	hb.add_theme_constant_override("separation", 10)
	var le := LineEdit.new()
	le.placeholder_text = tr("name.write")
	le.max_length = 14
	le.custom_minimum_size = Vector2(380, 64)
	le.add_theme_font_size_override("font_size", 28)
	hb.add_child(le)
	var ok := Button.new()
	ok.text = tr("name.ok")
	ok.custom_minimum_size = Vector2(160, 64)
	var submit := func(_t := ""):
		var t := le.text.strip_edges()
		if t != "":
			close_all()
			on_done.call(t)
	ok.pressed.connect(submit)
	le.text_submitted.connect(submit)
	hb.add_child(ok)
	vb.add_child(hb)
	_focus_first(vb)

# ---------------------------------------------------------------- confirm

func show_confirm(question: String, on_yes: Callable) -> void:
	get_tree().paused = true
	var vb := _page("")
	var l := Label.new()
	l.text = question
	l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	l.custom_minimum_size = Vector2(560, 0)
	vb.add_child(l)
	_button(vb, tr("menu.yes"), func():
		close_all()
		on_yes.call())
	_button(vb, tr("menu.no"), back)
	_focus_first(vb)

# ---------------------------------------------------------------- dialog

## A speech box at the bottom: the speaker's name, the text typing out, A to
## go on; after the last line, optional choices ([label, callable]) and Bye.
func show_dialog(speaker: String, lines: Array, choices: Array, on_close: Callable) -> void:
	get_tree().paused = true
	while not _stack.is_empty():
		_stack.pop_back().queue_free()
	var holder := Control.new()
	holder.set_anchors_preset(Control.PRESET_FULL_RECT)
	_root.add_child(holder)
	_stack.append(holder)
	var panel := PanelContainer.new()
	panel.set_anchors_and_offsets_preset(Control.PRESET_CENTER_BOTTOM)
	panel.offset_left = -560
	panel.offset_right = 560
	panel.offset_top = -330
	panel.offset_bottom = -170
	holder.add_child(panel)
	var vb := VBoxContainer.new()
	vb.add_theme_constant_override("separation", 10)
	panel.add_child(vb)
	var name_l := Label.new()
	name_l.text = speaker
	name_l.add_theme_color_override("font_color", UiTheme.ORANGE)
	name_l.add_theme_font_size_override("font_size", 30)
	vb.add_child(name_l)
	var text := Label.new()
	text.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	text.custom_minimum_size = Vector2(1060, 70)
	text.add_theme_font_size_override("font_size", 30)
	vb.add_child(text)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 12)
	row.alignment = BoxContainer.ALIGNMENT_END
	vb.add_child(row)
	var state := {"i": 0}
	var finish := func():
		if _stack.has(holder):
			_stack.erase(holder)
		holder.queue_free()
		get_tree().paused = false
		on_close.call()
	var show_line := func(self_ref: Callable):
		for c in row.get_children():
			c.queue_free()
		text.text = lines[state.i]
		Game.speak(speaker + ". " + text.text)
		text.visible_ratio = 0.0
		var tw := create_tween()
		tw.tween_property(text, "visible_ratio", 1.0, clampf(text.text.length() * 0.02, 0.3, 1.6))
		Sfx.play("ui_move", 0.1, -10.0)
		var last: bool = state.i >= lines.size() - 1
		if not last:
			var nb := Button.new()
			nb.text = "▶"
			nb.custom_minimum_size = Vector2(110, 56)
			nb.pressed.connect(func():
				state.i += 1
				self_ref.call(self_ref))
			row.add_child(nb)
			nb.grab_focus.call_deferred()
			return
		var first: Button = null
		for ch in choices:
			var b := Button.new()
			b.text = ch[0]
			b.custom_minimum_size = Vector2(0, 56)
			var cb: Callable = ch[1]
			b.pressed.connect(func():
				Sfx.play("ui")
				if _stack.has(holder):
					_stack.erase(holder)
				holder.queue_free()
				get_tree().paused = false
				cb.call())
			row.add_child(b)
			if first == null:
				first = b
		var bye := Button.new()
		bye.text = tr("dlg.bye")
		bye.custom_minimum_size = Vector2(140, 56)
		bye.pressed.connect(finish)
		row.add_child(bye)
		(first if first else bye).grab_focus.call_deferred()
	show_line.call(show_line)

# ---------------------------------------------------------------- album

## One card per species: known ones (ever owned or photographed) show their
## picture, real fact, food and habitat; unknown ones are a "?".
func known_species() -> Array:
	var out := []
	for d in get_tree().get_nodes_in_group("dinos"):
		if not (d.species in out):
			out.append(d.species)
	for k in Game.flags:
		if str(k).begins_with("seen_") or str(k).begins_with("photo_"):
			var sp := str(k).split("_", true, 1)[1]
			if not (sp in out):
				out.append(sp)
	return out

func show_album(focus := 0) -> void:
	var vb := _page(tr("menu.album"))
	var known := known_species()
	for sp in known:
		Game.flags["seen_" + sp] = true
	var lbl := Label.new()
	lbl.text = tr("album.count") % [known.size(), Content.dinos.size()]
	lbl.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	vb.add_child(lbl)
	var grid := GridContainer.new()
	grid.columns = 5
	grid.add_theme_constant_override("h_separation", 10)
	grid.add_theme_constant_override("v_separation", 10)
	vb.add_child(grid)
	var ids := Content.dinos.keys()
	var first: Button = null
	for i in ids.size():
		var sp: String = ids[i]
		var b := Button.new()
		b.custom_minimum_size = Vector2(150, 140)
		var has := sp in known
		var inner := VBoxContainer.new()
		inner.set_anchors_preset(Control.PRESET_FULL_RECT)
		inner.mouse_filter = Control.MOUSE_FILTER_IGNORE
		inner.add_theme_constant_override("separation", 0)
		var pic := TextureRect.new()
		pic.texture = Icons.get_icon("dino:" + sp) if has else Icons.get_icon("egg")
		pic.modulate = Color.WHITE if has else Color(0.45, 0.4, 0.35, 0.35)
		pic.custom_minimum_size = Vector2(0, 100)
		pic.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		pic.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		pic.mouse_filter = Control.MOUSE_FILTER_IGNORE
		inner.add_child(pic)
		var nl := Label.new()
		nl.text = Content.dino_name(sp) if has else "?"
		nl.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		nl.add_theme_font_size_override("font_size", 16)
		nl.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
		nl.mouse_filter = Control.MOUSE_FILTER_IGNORE
		inner.add_child(nl)
		b.add_child(inner)
		if has:
			b.pressed.connect(func(): show_album_card(sp))
		else:
			b.disabled = true
		grid.add_child(b)
		if first == null and has:
			first = b
	_button(vb, tr("menu.back"), back)
	if first:
		first.grab_focus.call_deferred()
	else:
		_focus_first(vb)

func show_album_card(sp: String) -> void:
	var vb := _page(Content.dino_name(sp))
	var d: Dictionary = Content.dinos[sp]
	var hb := HBoxContainer.new()
	hb.add_theme_constant_override("separation", 20)
	vb.add_child(hb)
	var pic := TextureRect.new()
	pic.texture = Icons.get_icon("dino:" + sp)
	pic.custom_minimum_size = Vector2(260, 260)
	pic.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	pic.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	hb.add_child(pic)
	var info := VBoxContainer.new()
	info.add_theme_constant_override("separation", 10)
	hb.add_child(info)
	var fact := Label.new()
	fact.text = tr("fact." + sp)
	fact.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	fact.custom_minimum_size = Vector2(520, 0)
	fact.add_theme_font_size_override("font_size", 26)
	info.add_child(fact)
	var foods := []
	for f in d.get("diet", []):
		for id in Content.items:
			if Content.items[id].get("food", "") == f:
				foods.append(Content.item_name(id))
				break
	var eats := Label.new()
	eats.text = tr("album.eats") % ", ".join(foods)
	eats.add_theme_font_size_override("font_size", 24)
	info.add_child(eats)
	var fav := Label.new()
	for id in Content.items:
		if Content.items[id].get("food", "") == d.get("fav", ""):
			fav.text = tr("album.fav") % Content.item_name(id)
			break
	fav.add_theme_font_size_override("font_size", 24)
	info.add_child(fav)
	var hab := Label.new()
	hab.text = tr("album.home") % tr("habitat." + d.get("habitat", "meadow"))
	hab.add_theme_font_size_override("font_size", 24)
	info.add_child(hab)
	var best := 0
	for n in get_tree().get_nodes_in_group("dinos"):
		if n.species == sp:
			best = max(best, n.hearts())
	var h := Label.new()
	h.text = tr("album.hearts") + " " + "♥".repeat(best) + "♡".repeat(5 - best)
	h.add_theme_color_override("font_color", Color("#ff5d8f"))
	h.add_theme_font_size_override("font_size", 28)
	info.add_child(h)
	_button(vb, tr("menu.back"), back)
	_focus_first(vb)

# ---------------------------------------------------------------- wardrobe

const WARDROBE_ROLES := ["cap", "shirt", "pants", "shoes", "skin", "hair"]

## Left/right tries a colour on Tommy (the camera comes close); A buys it if
## it isn't his yet. Leaving puts back whatever he didn't buy.
func show_wardrobe(player: Node) -> void:
	get_tree().paused = true
	var world := get_tree().get_first_node_in_group("world")
	world.cam_override = 0.42
	player.face_towards(player.global_position + Vector3(0, 0, 5))
	var vb := _page(tr("home.wardrobe"))
	var panel: Control = vb.get_parent()
	panel.set_anchors_and_offsets_preset(Control.PRESET_CENTER_LEFT)
	panel.offset_left = 50
	panel.grow_horizontal = Control.GROW_DIRECTION_END
	var holder: Control = panel.get_parent()
	holder.get_child(0).color = Color(0, 0, 0, 0)
	var saved: Dictionary = Game.flags.get("outfit", {}).duplicate()
	var coins := Label.new()
	coins.text = tr("shop.coins") % Game.coins
	coins.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	vb.add_child(coins)
	var hint := Label.new()
	hint.text = tr("wear.hint")
	hint.add_theme_font_size_override("font_size", 22)
	hint.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	vb.add_child(hint)
	var owned := func(role: String, o: Array) -> bool:
		return Game.price(int(o[2])) == 0 or Game.flags.get("owned_%s_%s" % [role, o[0]], false)
	for role in WARDROBE_ROLES:
		var opts: Array = Content.wardrobe.get(role, [])
		if opts.is_empty():
			continue
		var r: String = role
		var hb := HBoxContainer.new()
		hb.add_theme_constant_override("separation", 12)
		var l := Label.new()
		l.text = tr("wear." + r)
		l.custom_minimum_size = Vector2(190, 0)
		l.add_theme_font_size_override("font_size", 28)
		hb.add_child(l)
		var b := Button.new()
		b.custom_minimum_size = Vector2(330, 58)
		var st := {"i": int(saved.get(r, 0))}
		var refresh := func():
			var o: Array = opts[st.i]
			var mine: bool = owned.call(r, o)
			b.text = "‹  %s%s  ›" % [tr("color." + o[0]), "" if mine else "  · %d" % Game.price(int(o[2]))]
			var of: Dictionary = Game.flags.get("outfit", {})
			of[r] = st.i
			Game.flags["outfit"] = of
			player.apply_outfit()
		refresh.call()
		b.gui_input.connect(func(e: InputEvent):
			if e.is_action_pressed("ui_left") or e.is_action_pressed("ui_right"):
				st.i = (st.i + (1 if e.is_action_pressed("ui_right") else -1) + opts.size()) % opts.size()
				refresh.call()
				Sfx.play("ui_move")
				b.accept_event())
		b.pressed.connect(func():
			var o: Array = opts[st.i]
			if owned.call(r, o):
				saved[r] = st.i
				Sfx.play("ui")
				return
			if not Game.can_pay(Game.price(int(o[2]))):
				Sfx.play("nope")
				return
			Game.add_coins(-Game.price(int(o[2])))
			Game.flags["owned_%s_%s" % [r, o[0]]] = true
			saved[r] = st.i
			Sfx.play("buy")
			coins.text = tr("shop.coins") % Game.coins
			refresh.call())
		hb.add_child(b)
		vb.add_child(hb)
	_button(vb, tr("menu.back"), func():
		# keep only what he owns
		var of: Dictionary = Game.flags.get("outfit", {})
		for rr in of.keys():
			var o: Array = Content.wardrobe[rr][int(of[rr])]
			if not owned.call(rr, o):
				of[rr] = saved.get(rr, 0)
		Game.flags["outfit"] = of
		player.apply_outfit()
		world.cam_override = 0.0
		back())
	_focus_first(vb)

## dev: --open=dev_shop_tools
func dev_shop_tools() -> void:
	var w := get_tree().get_first_node_in_group("world")
	show_shop(w, w.players[0], 2)
