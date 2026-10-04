extends Control
## Dev: every icon (and given items) in a grid, for checking the renders.
##   godot --path game -- --scene=res://scenes/icon_sheet.tscn [--items=a,b] --shot=x.png --shot-after=4

func _ready() -> void:
	var bg := ColorRect.new()
	bg.color = Color("#fff7e6")
	bg.set_anchors_preset(Control.PRESET_FULL_RECT)
	add_child(bg)
	var grid := GridContainer.new()
	grid.columns = 10
	grid.position = Vector2(20, 20)
	add_child(grid)
	var names := []
	var da := DirAccess.open("res://assets/models")
	for f in da.get_files():
		if f.begins_with("icon_") and f.ends_with(".glb"):
			names.append(f.substr(5, f.length() - 9))
	for it in Dev.arg("items", "").split(",", false):
		names.append("item:" + it)
	for n in names:
		var vb := VBoxContainer.new()
		var tr_ := TextureRect.new()
		tr_.texture = Icons.get_icon(n)
		tr_.custom_minimum_size = Vector2(128, 128)
		tr_.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		vb.add_child(tr_)
		var l := Label.new()
		l.text = n
		l.add_theme_color_override("font_color", Color("#7a5236"))
		l.add_theme_font_size_override("font_size", 14)
		vb.add_child(l)
		grid.add_child(vb)
