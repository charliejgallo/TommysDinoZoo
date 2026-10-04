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
	_button(vb, tr("menu.settings"), show_settings)
	_button(vb, tr("menu.save_quit"), func():
		Game.save_game()
		close_all()
		get_tree().paused = false
		get_tree().change_scene_to_file("res://scenes/title.tscn"))
	_focus_first(vb)

# ---------------------------------------------------------------- settings

func show_settings() -> void:
	var vb := _page(tr("menu.settings"))
	_stepper(vb, "set.day_length", Game.DAY_CHOICES.map(func(m): return tr("set.minutes") % m),
		Game.DAY_CHOICES.find(int(Game.settings.day_minutes)),
		func(i): Game.settings.day_minutes = Game.DAY_CHOICES[i])
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
	var parents := Label.new()
	parents.text = tr("set.parents") % int(Game.played_today_s / 60.0)
	parents.add_theme_font_size_override("font_size", 24)
	parents.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	vb.add_child(parents)
	_button(vb, tr("menu.back"), func():
		Game.save_settings()
		back())
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
				if d.get("kind", "") == kind and int(d.get("price", 0)) > 0:
					out.append({"id": id, "price": int(d.price), "name": Content.item_name(id), "icon": "item:" + id})
		"eggs":
			for sp in Content.dinos:
				var d: Dictionary = Content.dinos[sp]
				if int(d.get("price", 0)) > 0 and world.is_zone_open(d.get("habitat", "")):
					out.append({"id": "egg_" + sp, "price": int(d.price), "name": tr("shop.egg") % Content.dino_name(sp), "icon": "item:egg_" + sp})
		"furniture":
			for id in Content.props:
				var d: Dictionary = Content.props[id]
				if int(d.get("price", 0)) > 0 and not d.get("fixed", false):
					out.append({"id": "box_" + id, "price": int(d.price), "name": tr("prop." + id), "icon": "item:box_" + id})
	out.sort_custom(func(a, b): return a.price < b.price)
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
