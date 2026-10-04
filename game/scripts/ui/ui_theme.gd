class_name UiTheme
## The game's Godot Theme, built in code: cream rounded panels with a
## brown outline, big friendly buttons that light up gold when focused
## (keyboard/joypad navigation is the main way to use menus).

const CREAM := Color("#fff7e6")
const CREAM_DARK := Color("#f3e3c3")
const BROWN := Color("#7a5236")
const GOLD := Color("#ffcf4a")
const ORANGE := Color("#e0703c")

static var _theme: Theme

static func get_theme() -> Theme:
	if _theme:
		return _theme
	var t := Theme.new()
	t.default_font_size = 30
	var f := _font()
	if f:
		t.default_font = f
	t.set_color("font_color", "Label", BROWN)
	for state in ["normal", "hover", "pressed", "focus", "disabled"]:
		var s := _box(CREAM_DARK if state == "normal" else CREAM,
			GOLD.darkened(0.15) if state in ["focus", "hover", "pressed"] else BROWN.lightened(0.25),
			6 if state in ["focus", "hover"] else 3)
		if state == "disabled":
			s.bg_color = CREAM_DARK.darkened(0.08)
		t.set_stylebox(state, "Button", s)
	t.set_color("font_color", "Button", BROWN)
	t.set_color("font_focus_color", "Button", BROWN)
	t.set_color("font_hover_color", "Button", BROWN)
	t.set_color("font_pressed_color", "Button", ORANGE)
	t.set_color("font_disabled_color", "Button", BROWN.lightened(0.45))
	t.set_font_size("font_size", "Button", 32)
	t.set_stylebox("normal", "LineEdit", _box(Color.WHITE, BROWN.lightened(0.25), 3, 18))
	t.set_stylebox("focus", "LineEdit", _box(Color.WHITE, GOLD.darkened(0.15), 6, 18))
	t.set_color("font_color", "LineEdit", BROWN)
	t.set_color("font_placeholder_color", "LineEdit", BROWN.lightened(0.45))
	t.set_color("caret_color", "LineEdit", ORANGE)
	t.set_stylebox("panel", "PanelContainer", _box(CREAM, BROWN, 5, 36))
	t.set_stylebox("panel", "Panel", _box(CREAM, BROWN, 5, 36))
	_theme = t
	return t

static var font: Font

static func _font() -> Font:
	if font:
		return font
	# Fredoka (SIL OFL, assets/fonts/OFL.txt), a variable font: semibold
	if ResourceLoader.exists("res://assets/fonts/Fredoka.ttf"):
		var fv := FontVariation.new()
		fv.base_font = load("res://assets/fonts/Fredoka.ttf")
		fv.variation_opentype = {TextServerManager.get_primary_interface().name_to_tag("wght"): 560}
		font = fv
		return font
	var sf := SystemFont.new()
	sf.font_names = PackedStringArray(["Arial Rounded MT Bold", "Nunito", "Varela Round", "Segoe UI", "Helvetica Neue"])
	sf.font_weight = 700
	return sf

static func _box(bg: Color, border: Color, bw := 3, radius := 24) -> StyleBoxFlat:
	var s := StyleBoxFlat.new()
	s.bg_color = bg
	s.border_color = border
	s.set_border_width_all(bw)
	s.set_corner_radius_all(radius)
	s.shadow_color = Color(0, 0, 0, 0.18)
	s.shadow_size = 6
	s.shadow_offset = Vector2(0, 3)
	s.content_margin_left = 22
	s.content_margin_right = 22
	s.content_margin_top = 12
	s.content_margin_bottom = 12
	return s
