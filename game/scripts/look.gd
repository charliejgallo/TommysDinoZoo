class_name Look
## Gives imported models the game's look: every glTF material becomes the
## shared toon shader with the same base colour. Materials are cached per
## (name, colour) so a scene full of dinos shares a handful of them.

const TOON := preload("res://shaders/toon.gdshader")
const GLASS := preload("res://shaders/glass.gdshader")  # alpha materials (role `glass`)
static var _cache := {}

static func apply(root: Node) -> void:
	for n in root.find_children("*", "MeshInstance3D", true, false):
		_apply_mesh(n)
	if root is MeshInstance3D:
		_apply_mesh(root)

static func _apply_mesh(mi: MeshInstance3D) -> void:
	if mi.mesh == null:
		return
	for i in mi.mesh.get_surface_count():
		var src := mi.get_active_material(i)
		if src is StandardMaterial3D:
			mi.set_surface_override_material(i, toon_for(src))

static func toon_for(src: StandardMaterial3D) -> ShaderMaterial:
	var key := "%s|%s|%s" % [src.resource_name, src.albedo_color.to_html(), src.emission_enabled]
	if _cache.has(key):
		return _cache[key]
	var m := ShaderMaterial.new()
	m.shader = GLASS if src.transparency != BaseMaterial3D.TRANSPARENCY_DISABLED else TOON
	m.resource_name = src.resource_name
	m.set_shader_parameter("albedo", src.albedo_color)
	if src.emission_enabled:
		m.set_shader_parameter("emit", src.emission_energy_multiplier * 0.6)
	_cache[key] = m
	return m
