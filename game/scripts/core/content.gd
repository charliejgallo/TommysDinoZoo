extends Node
## Content registry. Every pack lives in `res://content/<pack>/pack.json`
## (and optionally `user://content/<pack>/`). Packs merge in alphabetical
## order with "base" first; a later pack may add entries or override fields
## of existing ones. Everything is addressed by string id, so saves survive
## new packs.

var packs := []
var dinos := {}
var items := {}
var plants := {}
var props := {}
var habitats := {}
var wardrobe := {}   # role -> [[name, colour, price], ...]; index 0 is the default

func _ready() -> void:
	var dirs := []
	for root in ["res://content", "user://content"]:
		var da := DirAccess.open(root)
		if da == null:
			continue
		var names := Array(da.get_directories())
		names.sort()
		names.erase("base")
		if root == "res://content":
			names.push_front("base")
		for n in names:
			dirs.append(root.path_join(n))
	var lang_dirs := []
	for d in dirs:
		var f := FileAccess.open(d.path_join("pack.json"), FileAccess.READ)
		if f == null:
			continue
		var data = JSON.parse_string(f.get_as_text())
		if typeof(data) != TYPE_DICTIONARY:
			push_error("content: bad pack.json in " + d)
			continue
		packs.append(data.get("id", d.get_file()))
		for key in ["dinos", "items", "plants", "props", "habitats"]:
			var dst: Dictionary = get(key)
			for id in data.get(key, {}):
				var entry: Dictionary = data[key][id]
				entry["id"] = id
				entry["pack"] = d
				if dst.has(id):
					dst[id].merge(entry, true)
				else:
					dst[id] = entry
		for role in data.get("wardrobe", {}):
			wardrobe[role] = wardrobe.get(role, []) + data.wardrobe[role]
		lang_dirs.append(d.path_join("lang"))
	lang_dirs.append("user://lang")
	Lang.load_dirs(lang_dirs)

func model_path(model: String) -> String:
	return "res://assets/models/%s.glb" % model

## Instantiate a model by name; a coloured placeholder when it's missing so
## the game keeps running while art is being made.
func instance_model(model: String, fallback_size := Vector3(0.4, 0.4, 0.4), color := Color(1, 0.5, 0.8)) -> Node3D:
	var p := model_path(model)
	if ResourceLoader.exists(p):
		var n: Node3D = load(p).instantiate()
		Look.apply(n)
		return n
	var mi := MeshInstance3D.new()
	var bm := BoxMesh.new()
	bm.size = fallback_size
	mi.mesh = bm
	mi.position.y = fallback_size.y / 2.0
	var m := ShaderMaterial.new()
	m.shader = Look.TOON
	m.set_shader_parameter("albedo", color)
	mi.material_override = m
	var root := Node3D.new()
	root.add_child(mi)
	root.name = model
	return root

func item_name(id: String) -> String:
	return tr("item." + id)

func dino_name(id: String) -> String:
	return tr("dino." + id)
