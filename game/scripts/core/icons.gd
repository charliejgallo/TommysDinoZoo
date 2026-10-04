extends Node
## Icons for the HUD, prompts and thought bubbles. Every icon is rendered
## from a 3D model (res://assets/models/icon_<name>.glb, or the item's own
## model for item icons) in an off-screen viewport under the game's light,
## so icons always match the art. A PNG at res://assets/icons/<name>.png
## wins if present. Until a render is ready a soft placeholder is returned;
## `icon_ready(name)` fires when the real one exists.

signal icon_ready(name: String)

const SIZE := 128
var _cache := {}
var _queue := []
var _vp: SubViewport
var _holder: Node3D
var _busy := false

func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	_vp = SubViewport.new()
	_vp.size = Vector2i(SIZE, SIZE)
	_vp.transparent_bg = true
	_vp.own_world_3d = true
	_vp.render_target_update_mode = SubViewport.UPDATE_DISABLED
	add_child(_vp)
	var cam := Camera3D.new()
	cam.projection = Camera3D.PROJECTION_ORTHOGONAL
	cam.size = 1.0
	cam.position = Vector3(0, 0, 3.0)
	_vp.add_child(cam)
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-40, -30, 0)
	sun.light_energy = 1.2
	_vp.add_child(sun)
	var env := Environment.new()
	env.background_mode = Environment.BG_CLEAR_COLOR
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color(0.85, 0.88, 1.0)
	env.ambient_light_energy = 0.55
	var we := WorldEnvironment.new()
	we.environment = env
	_vp.add_child(we)
	_holder = Node3D.new()
	_vp.add_child(_holder)

## Icon for a name: "need_food", "verb_pet", "item_fern", "coin"...
func get_icon(name: String) -> Texture2D:
	if _cache.has(name):
		return _cache[name]
	var png := "res://assets/icons/%s.png" % name
	if ResourceLoader.exists(png):
		_cache[name] = load(png)
		return _cache[name]
	var model := _model_for(name)
	if model != "" and ResourceLoader.exists(Content.model_path(model)):
		_cache[name] = _placeholder(name)
		_queue.append([name, model])
		_pump()
		return _cache[name]
	_cache[name] = _placeholder(name)
	return _cache[name]

func item_icon(id: String) -> Texture2D:
	return get_icon("item:" + id)

func _model_for(name: String) -> String:
	if name.begins_with("item:"):
		var id := name.substr(5)
		if id.begins_with("egg_"):
			return id
		if id.begins_with("box_"):
			return "item_box"
		return Content.items.get(id, {}).get("model", "item_" + id)
	if name.begins_with("dino:"):
		return name.substr(5) + "_adult"
	if name.begins_with("dinobaby:"):
		return name.substr(9) + "_baby"
	if name.begins_with("verb_"):
		name = name.substr(5)
	return "icon_" + ALIASES.get(name, name)

const ALIASES := {"ball": "need_fun", "verb_ball": "need_fun"}

func _placeholder(name: String) -> Texture2D:
	var img := Image.create(SIZE, SIZE, false, Image.FORMAT_RGBA8)
	var c := Color.from_hsv(float(hash(name) % 360) / 360.0, 0.5, 0.95)
	var r := SIZE * 0.36
	for y in SIZE:
		for x in SIZE:
			var d := Vector2(x - SIZE / 2.0, y - SIZE / 2.0).length()
			if d < r:
				img.set_pixel(x, y, c.lightened(0.25 * (1.0 - d / r)))
			elif d < r + 4:
				img.set_pixel(x, y, c.darkened(0.35))
	return ImageTexture.create_from_image(img)

func _pump() -> void:
	if _busy or _queue.is_empty():
		return
	_busy = true
	var job: Array = _queue.pop_front()
	var name: String = job[0]
	for c in _holder.get_children():
		c.queue_free()
	var inst: Node3D = load(Content.model_path(job[1])).instantiate()
	Look.apply(inst)
	_holder.add_child(inst)
	# turn it a little so it reads as 3D, then fit its box in the 1 m view
	var flat: bool = name.trim_prefix("verb_") in FLAT or name.begins_with("dino")
	var pivot := Node3D.new()
	_holder.add_child(pivot)
	inst.reparent(pivot, false)
	pivot.rotation_degrees = Vector3(0, 0, 0) if flat else Vector3(18, -28, 0)
	if name.begins_with("dino"):
		pivot.rotation_degrees = Vector3(12, -35, 0)
		var ap: AnimationPlayer = inst.find_child("AnimationPlayer", true, false)
		if ap and ap.has_animation("idle"):
			ap.play("idle")
			ap.seek(0.4, true)
			ap.pause()
	var aabb := _aabb_in(pivot, _holder)
	var s: float = 0.86 / maxf(maxf(aabb.size.x, aabb.size.y), 0.01)
	pivot.scale = Vector3.ONE * s
	var c := (aabb.position + aabb.size / 2.0) * s
	pivot.position = Vector3(-c.x, -c.y, -c.z)
	_vp.render_target_update_mode = SubViewport.UPDATE_ONCE
	await RenderingServer.frame_post_draw
	await RenderingServer.frame_post_draw
	var img := _vp.get_texture().get_image()
	var tex: ImageTexture = _cache.get(name)
	if tex is ImageTexture:
		tex.set_image(img)
	else:
		_cache[name] = ImageTexture.create_from_image(img)
	icon_ready.emit(name)
	_busy = false
	_pump()

const FLAT := ["heart", "need_love", "star", "sparkle", "nope", "sleep", "sun", "moon", "need_clean", "water"]

func _aabb_in(n: Node3D, space: Node3D) -> AABB:
	var out := AABB()
	var first := true
	var inv := space.global_transform.affine_inverse()
	for mi in n.find_children("*", "MeshInstance3D", true, false):
		var b: AABB = (inv * mi.global_transform) * mi.get_aabb()
		out = b if first else out.merge(b)
		first = false
	return out

func _aabb(n: Node3D) -> AABB:
	var out := AABB()
	var first := true
	for mi in n.find_children("*", "MeshInstance3D", true, false):
		var b: AABB = (n.global_transform.affine_inverse() * mi.global_transform) * mi.get_aabb() if n.is_inside_tree() else mi.get_aabb()
		out = b if first else out.merge(b)
		first = false
	return out
