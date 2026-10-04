class_name World
extends Node3D
## The farm: builds the ground, fences and zones from content/base/map.json,
## spawns props, dinos and loose items (from the save or the map), runs
## day/night, the camera, small effects, and the end-of-day flow.

const GROUND_COLORS := {
	"yard": Color("#9ad66e"), "grass": Color("#86c95f"), "path": Color("#e6cf9a"),
	"locked": Color("#6f9f55"), "border": Color("#79b75a"),
}

var map := {}
var bounds := Rect2()
var zones := {}            # id -> {rect: Rect2, open: bool, gate: Vector2}
var open_zones := ["meadow"]
var players: Array[Player] = []
var hud: Node
var cam: Camera3D
var sun: DirectionalLight3D
var env: Environment
var sky_mat: ProceduralSkyMaterial
var _uid := 1
var _props_root: Node3D
var _dinos_root: Node3D
var _items_root: Node3D
var _fences_root: Node3D
var _npcs_root: Node3D
var _noise_tex: NoiseTexture2D
var _sleeping := false
var _habitat_rev := 0
var menus: Menus
var _ground_img: Image
var _ground_tex: ImageTexture
var _ground_origin := Vector2.ZERO

func _repaint_ground() -> void:
	for iy in _ground_img.get_height():
		for ix in _ground_img.get_width():
			var p := _ground_origin + Vector2((ix + 0.5) / PX_PER_M, (iy + 0.5) / PX_PER_M)
			_ground_img.set_pixel(ix, iy, _ground_color(p))
	_ground_tex.update(_ground_img)

func _check_menu() -> void:
	if Controls.pressed(0, "menu") and not menus.is_open() and not _sleeping:
		menus.show_pause()

func _ready() -> void:
	add_to_group("world")
	var f := FileAccess.open("res://content/base/map.json", FileAccess.READ)
	map = JSON.parse_string(f.get_as_text())
	var b: Array = map.bounds
	bounds = Rect2(b[0], b[1], b[2] - b[0], b[3] - b[1])
	for zid in map.zones:
		var z: Dictionary = map.zones[zid]
		var r: Array = z.rect
		zones[zid] = {"rect": Rect2(r[0], r[1], r[2] - r[0], r[3] - r[1]),
			"gate": Vector2(z.gate[0], z.gate[1]), "open": z.get("open", false)}
	var st := Stage.make_env(self)
	_cam_attr = st.world_env.camera_attributes
	env = st.env
	sun = st.sun
	sky_mat = env.sky.sky_material
	_noise_tex = NoiseTexture2D.new()
	_noise_tex.seamless = true
	_noise_tex.width = 256
	_noise_tex.height = 256
	var fn := FastNoiseLite.new()
	fn.frequency = 0.02
	_noise_tex.noise = fn
	_props_root = _child("Props")
	_dinos_root = _child("Dinos")
	_items_root = _child("Items")
	_fences_root = _child("Fences")
	_npcs_root = _child("Npcs")
	_pond_setup()
	_build_ground()
	_build_water()
	cam = Camera3D.new()
	add_child(cam)
	cam.make_current()
	var p := Player.new()
	p.name = "Tommy"
	add_child(p)
	players.append(p)
	var hud_scene := preload("res://scripts/ui/hud.gd")
	hud = CanvasLayer.new()
	hud.set_script(hud_scene)
	add_child(hud)
	hud.bind(p)
	get_tree().process_frame.connect(_paused_frame)
	Game.world_save = save_state
	Game.world_load = load_state
	Game.day_ended.connect(_on_day_ended)
	Game.dusk.connect(func(): toast(tr("toast.dusk"), "moon"))
	Game.apply_settings()
	var slot := int(Dev.arg("slot", str(Game.slot)))
	if Dev.arg("state") != "":
		# dev: start from a hand-made world state (screenshots, tests)
		Game.new_game(slot)
		var sf := FileAccess.open(Dev.arg("state"), FileAccess.READ)
		load_state(JSON.parse_string(sf.get_as_text()))
	elif Dev.arg("new") != "" or Game.flags.get("_fresh", false):
		Game.new_game(slot)
	else:
		Game.load_game(slot)
	menus = Menus.new()
	menus.in_game = true
	menus.closed.connect(func(): get_tree().paused = false)
	add_child(menus)
	var sp: Array = map.spawn
	p.global_position = Vector3(sp[0], 0, sp[1])
	if Dev.arg("at") != "":
		var a := Dev.arg("at").split(",")
		p.global_position = Vector3(float(a[0]), 0, float(a[1]))
	if Dev.arg("hour") != "":
		Game.hour = float(Dev.arg("hour"))
	_snap_camera()
	Game.running = true
	_update_daylight()

func _child(n: String) -> Node3D:
	var c := Node3D.new()
	c.name = n
	add_child(c)
	return c

# ---------------------------------------------------------------- building

func zone_at(p: Vector2) -> String:
	for zid in zones:
		if zones[zid].rect.has_point(p):
			return zid
	var y: Array = map.yard
	if Rect2(y[0], y[1], y[2] - y[0], y[3] - y[1]).has_point(p):
		return "yard"
	return ""

func _path_dist(p: Vector2) -> float:
	var best := INF
	for path in map.paths:
		for i in path.size() - 1:
			var a := Vector2(path[i][0], path[i][1])
			var b := Vector2(path[i + 1][0], path[i + 1][1])
			best = min(best, Geometry2D.get_closest_point_to_segment(p, a, b).distance_to(p))
	return best

func _ground_color(p: Vector2) -> Color:
	var z := zone_at(p)
	var c: Color = GROUND_COLORS.grass
	if z == "yard":
		c = GROUND_COLORS.yard
	elif z != "":
		var hc := Color(Content.habitats.get(z, {}).get("color", "#86c95f"))
		c = hc if is_zone_open(z) else hc.lerp(GROUND_COLORS.locked, 0.55)
	elif not bounds.has_point(p):
		c = GROUND_COLORS.border
	var wd := pond_dist(p)
	if wd < 1.2:
		c = c.lerp(Color("#ecd9a6"), 1.0 - smoothstep(0.4, 1.2, wd))
	var pd := _path_dist(p)
	if pd < 1.3:
		c = c.lerp(GROUND_COLORS.path, 1.0 - smoothstep(0.85, 1.25, pd))
	return c

func _height(p: Vector2) -> float:
	# flat farm, gentle hills rising outside the bounds to frame the world
	var dx: float = max(bounds.position.x - p.x, p.x - bounds.end.x, 0.0)
	var dz: float = max(bounds.position.y - p.y, p.y - bounds.end.y, 0.0)
	var d := Vector2(dx, dz).length()
	var h := pow(d, 1.35) * 0.35
	var wd := pond_dist(p)
	if wd < 0.5:
		h -= 0.7 * smoothstep(0.5, -2.0, wd)
	return h

const PX_PER_M := 3

func _build_ground() -> void:
	var pad := 30.0
	var x0 := bounds.position.x - pad
	var z0 := bounds.position.y - pad
	var nx := int(bounds.size.x + pad * 2)
	var nz := int(bounds.size.y + pad * 2)
	# colours: painted into a texture (3 px per metre, filtered) so zone and
	# path edges are soft and smooth instead of following the mesh grid
	var img := Image.create(nx * PX_PER_M, nz * PX_PER_M, false, Image.FORMAT_RGB8)
	for iy in img.get_height():
		for ix in img.get_width():
			var p := Vector2(x0 + (ix + 0.5) / PX_PER_M, z0 + (iy + 0.5) / PX_PER_M)
			img.set_pixel(ix, iy, _ground_color(p))
	_ground_img = img
	_ground_origin = Vector2(x0, z0)
	var tex := ImageTexture.create_from_image(img)
	_ground_tex = tex
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	for iz in nz + 1:
		for ix in nx + 1:
			var p := Vector2(x0 + ix, z0 + iz)
			st.set_uv(Vector2(float(ix) / nx, float(iz) / nz))
			st.add_vertex(Vector3(p.x, _height(p), p.y))
	for iz in nz:
		for ix in nx:
			var i := iz * (nx + 1) + ix
			st.add_index(i)
			st.add_index(i + 1)
			st.add_index(i + nx + 1)
			st.add_index(i + 1)
			st.add_index(i + nx + 2)
			st.add_index(i + nx + 1)
	st.generate_normals()
	var mi := MeshInstance3D.new()
	mi.name = "Ground"
	mi.mesh = st.commit()
	var m := ShaderMaterial.new()
	m.shader = preload("res://shaders/ground.gdshader")
	m.set_shader_parameter("noise_tex", _noise_tex)
	m.set_shader_parameter("color_tex", tex)
	mi.material_override = m
	add_child(mi)
	var body := StaticBody3D.new()
	var col := CollisionShape3D.new()
	col.shape = WorldBoundaryShape3D.new()
	body.add_child(col)
	add_child(body)
	# invisible walls at the bounds
	for side in 4:
		var w := StaticBody3D.new()
		var c := CollisionShape3D.new()
		var bs := BoxShape3D.new()
		var horiz := side < 2
		bs.size = Vector3(bounds.size.x + 2, 4, 1) if horiz else Vector3(1, 4, bounds.size.y + 2)
		c.shape = bs
		w.add_child(c)
		var cx := bounds.position.x + bounds.size.x / 2.0
		var cz := bounds.position.y + bounds.size.y / 2.0
		match side:
			0: w.position = Vector3(cx, 2, bounds.position.y - 0.5)
			1: w.position = Vector3(cx, 2, bounds.end.y + 0.5)
			2: w.position = Vector3(bounds.position.x - 0.5, 2, cz)
			3: w.position = Vector3(bounds.end.x + 0.5, 2, cz)
		add_child(w)

var pond_center := Vector2.ZERO
var pond_radii := Vector2.ONE

func _pond_setup() -> void:
	var lag: Rect2 = zones.lagoon.rect
	pond_center = lag.get_center() + Vector2(3, -3)
	pond_radii = Vector2(lag.size.x * 0.24, lag.size.y * 0.19)

## 0 at the pond's edge, < 0 inside, > 0 outside (in metres, roughly)
func pond_dist(p: Vector2) -> float:
	var q := (p - pond_center) / pond_radii
	return (q.length() - 1.0) * min(pond_radii.x, pond_radii.y)

func _build_water() -> void:
	# the lagoon's pond (shown even before it opens: it's pretty)
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var n := 48
	var pts := PackedVector3Array()
	for i in n:
		var a := TAU * i / n
		var wob := 1.0 + sin(a * 3.0) * 0.05 + sin(a * 5.0 + 1.0) * 0.03
		pts.append(Vector3(cos(a) * pond_radii.x * wob, 0, sin(a) * pond_radii.y * wob))
	for i in n:
		st.set_normal(Vector3.UP)
		st.add_vertex(Vector3.ZERO)
		st.add_vertex(pts[i])
		st.add_vertex(pts[(i + 1) % n])
	var pond := MeshInstance3D.new()
	pond.mesh = st.commit()
	pond.position = Vector3(pond_center.x, -0.08, pond_center.y)
	var wm := ShaderMaterial.new()
	wm.shader = preload("res://shaders/water.gdshader")
	wm.set_shader_parameter("noise_tex", _noise_tex)
	pond.material_override = wm
	add_child(pond)
	# Tommy can't walk on water (layer 8; swimmers ignore it)
	var sb := StaticBody3D.new()
	sb.collision_layer = 8
	var cs := CollisionShape3D.new()
	var shape := ConvexPolygonShape3D.new()
	var hull := PackedVector3Array()
	for p in pts:
		hull.append(p * 0.92)
		hull.append(p * 0.92 + Vector3(0, 2, 0))
	shape.points = hull
	cs.shape = shape
	sb.add_child(cs)
	pond.add_child(sb)

func is_zone_open(z: String) -> bool:
	return z in open_zones

func open_zone(z: String) -> void:
	if z in open_zones:
		return
	open_zones.append(z)
	_build_fences()
	_repaint_ground()
	Sfx.play("mission")
	toast(tr("land.opened") % tr("habitat." + z), "star")
	Game.count("lands")

func _build_fences() -> void:
	for c in _fences_root.get_children():
		c.queue_free()
	for zid in zones:
		var r: Rect2 = zones[zid].rect
		var gate: Vector2 = zones[zid].gate
		var pts := []
		# walk the perimeter in 1 m steps; each section is centred between posts
		for x in range(int(r.position.x), int(r.end.x)):
			pts.append([Vector2(x + 0.5, r.position.y), 0])
			pts.append([Vector2(x + 0.5, r.end.y), 0])
		for z in range(int(r.position.y), int(r.end.y)):
			pts.append([Vector2(r.position.x, z + 0.5), 1])
			pts.append([Vector2(r.end.x, z + 0.5), 1])
		for e in pts:
			var p: Vector2 = e[0]
			var is_gate := p.distance_to(gate) < 0.6
			if is_gate and is_zone_open(zid):
				continue   # open gate: a gap
			var model := "prop_gate" if is_gate else "prop_fence"
			var n := Content.instance_model(model, Vector3(1.0, 0.6, 0.12), Color(0.95, 0.9, 0.8))
			n.position = Vector3(p.x, 0, p.y)
			n.rotation.y = PI / 2.0 if e[1] == 1 else 0.0
			_fences_root.add_child(n)
			var sb := StaticBody3D.new()
			var cs := CollisionShape3D.new()
			var bs := BoxShape3D.new()
			bs.size = Vector3(1.0, 1.0, 0.2)
			cs.shape = bs
			cs.position.y = 0.5
			sb.add_child(cs)
			n.add_child(sb)
		if not is_zone_open(zid):
			var sign := SaleSign.new()
			sign.setup(zid, Vector3(gate.x, 0, gate.y) + _outward(zid) * 1.2)
			_fences_root.add_child(sign)

func _outward(zid: String) -> Vector3:
	var r: Rect2 = zones[zid].rect
	var g: Vector2 = zones[zid].gate
	var c := r.get_center()
	var d := (g - c)
	if abs(d.x) / r.size.x > abs(d.y) / r.size.y:
		return Vector3(sign(d.x), 0, 0.6)
	return Vector3(0.6, 0, sign(d.y))

# ---------------------------------------------------------------- spawning

func spawn_prop(id: String, pos: Vector3, rot := 0, st := {}) -> Prop:
	var p := Prop.new()
	p.setup(id, pos, rot, st)
	_props_root.add_child(p)
	return p

func spawn_dino(d: Dictionary) -> Dino:
	var n := Dino.new()
	if not d.has("uid"):
		d.uid = _uid
	_uid = max(_uid, int(d.uid) + 1)
	n.setup(d)
	_dinos_root.add_child(n)
	return n

func spawn_item(id: String, pos: Vector3) -> WorldItem:
	var it := WorldItem.new()
	pos.y = 0
	it.setup(id, pos)
	_items_root.add_child(it)
	return it

func throw_item(id: String, from: Vector3, dir: Vector3) -> void:
	var it := spawn_item(id, from)
	it.position = from
	it.vel = dir * 5.0 + Vector3(0, 3.5, 0)
	it.flying = true
	Sfx.play("throw")

func on_ball_landed(ball: WorldItem) -> void:
	var best: Dino = null
	for d in _dinos_root.get_children():
		if d.state == "sleep" or d.is_swimmer():
			continue
		var dist: float = d.global_position.distance_to(ball.global_position)
		if dist < 10.0 and (best == null or dist < best.global_position.distance_to(ball.global_position)):
			best = d
	if best:
		best.chase(ball)

func place_prop_from(p: Player) -> bool:
	var id := p.held().substr(4)
	var at := p.front_point(1.2)
	var cell := Vector3(round(at.x), 0, round(at.z))
	for q in _props_root.get_children():
		if q.global_position.distance_to(cell) < 0.9:
			toast(tr("toast.no_room"), "place")
			return false
	p.take_held()
	spawn_prop(id, cell, 0, {"mine": true})
	Sfx.play("place")
	return true

# ---------------------------------------------------------------- queries

func poops_in(habitat: String) -> int:
	var n := 0
	var r: Rect2 = zones.get(habitat, {}).get("rect", Rect2())
	for it in _items_root.get_children():
		if it.id == "poop" and r.has_point(Vector2(it.position.x, it.position.z)):
			n += 1
	return n

func _in_zone(node: Node3D, habitat: String) -> bool:
	var r: Rect2 = zones.get(habitat, {}).get("rect", Rect2())
	return r.has_point(Vector2(node.global_position.x, node.global_position.z))

func find_feeder(habitat: String, diet: Array, from: Vector3) -> Prop:
	var best: Prop = null
	for p in _props_root.get_children():
		if p.def.get("feeder", "") == "food" and p.food_left() > 0 and p.feeder_food() in diet and _in_zone(p, habitat):
			if best == null or p.global_position.distance_to(from) < best.global_position.distance_to(from):
				best = p
	return best

## The nearest prop in the habitat whose entry passes `test` (a Callable
## taking the entry dictionary).
func find_prop(habitat: String, from: Vector3, test: Callable) -> Prop:
	var best: Prop = null
	for p in _props_root.get_children():
		if test.call(p.def) and _in_zone(p, habitat):
			if best == null or p.global_position.distance_to(from) < best.global_position.distance_to(from):
				best = p
	return best

func find_feature(habitat: String, feature: String, from: Vector3) -> Prop:
	var best: Prop = null
	for p in _props_root.get_children():
		if p.def.get(feature, false) and _in_zone(p, habitat):
			if best == null or p.global_position.distance_to(from) < best.global_position.distance_to(from):
				best = p
	return best

func random_point_in_pond(scale := 0.75) -> Vector3:
	var a := randf() * TAU
	var r := sqrt(randf()) * scale
	return Vector3(pond_center.x + cos(a) * pond_radii.x * r, 0, pond_center.y + sin(a) * pond_radii.y * r)

## Where a newborn of this species goes: inside its habitat, near the gate.
func habitat_spawn(habitat: String) -> Vector3:
	var z: Dictionary = zones.get(habitat, zones.meadow)
	var r: Rect2 = z.rect
	var g: Vector2 = z.gate
	var inward := (r.get_center() - g).normalized()
	var p := g + inward * 2.5
	return Vector3(p.x, 0, p.y)

func random_point_in(habitat: String, near: Vector3, radius: float) -> Vector3:
	var r: Rect2 = zones.get(habitat, {}).get("rect", bounds)
	r = r.grow(-1.2)
	for i in 8:
		var p := Vector2(near.x, near.z) + Vector2(randf_range(-radius, radius), randf_range(-radius, radius))
		if r.has_point(p):
			return Vector3(p.x, 0, p.y)
	return Vector3(r.get_center().x, 0, r.get_center().y)

# ---------------------------------------------------------------- garden

func plot_info(plot: Prop, p: Player) -> Dictionary:
	var crop: String = plot.state.get("crop", "")
	var held := p.held_def()
	if crop == "":
		if held.get("kind", "") == "seed":
			return {"verb": "plant", "icon": "plant", "priority": 2}
		return {}
	var pdef: Dictionary = Content.plants.get(crop, {})
	if int(plot.state.get("grown", 0)) >= int(pdef.get("days", 1)):
		return {"verb": "harvest", "icon": "harvest", "priority": 2}
	if held.get("tool", "") == "water" and int(plot.state.get("watered", 0)) != Game.day:
		return {"verb": "water", "icon": "water", "priority": 2}
	return {}

func plot_do(plot: Prop, p: Player, info: Dictionary) -> void:
	match info.verb:
		"plant":
			plot.state.crop = p.held_def().plant
			plot.state.grown = 0
			plot.state.watered = 0
			p.take_held()
			p.anim_once("dig")
			Sfx.play("plant")
			Game.count("planted")
		"water":
			plot.state.watered = Game.day
			p.anim_once("use")
			fx_sparkles(plot.global_position)
			Sfx.play("water")
		"harvest":
			var pdef: Dictionary = Content.plants.get(plot.state.crop, {})
			for i in int(pdef.get("count", 1)):
				spawn_item(pdef.yield, plot.global_position + Vector3(randf_range(-0.8, 0.8), 0, randf_range(0.8, 1.4)))
			plot.state = {}
			p.anim_once("pickup")
			Sfx.play("harvest")
			Game.count("harvested")
	_refresh_plot(plot)

func _refresh_plot(plot: Prop) -> void:
	var old := plot.get_node_or_null("Crop")
	if old:
		old.queue_free()
	var crop: String = plot.state.get("crop", "")
	if crop == "":
		return
	var pdef: Dictionary = Content.plants.get(crop, {})
	var n := Content.instance_model(pdef.get("model", "prop_fern"), Vector3(0.5, 0.5, 0.5), Color(0.4, 0.8, 0.3))
	n.name = "Crop"
	var g: float = float(plot.state.get("grown", 0)) / maxf(float(pdef.get("days", 1)), 1.0)
	n.scale = Vector3.ONE * lerp(0.35, 0.9, g)
	plot.add_child(n)

# ---------------------------------------------------------------- frame

var _music_mode := ""

func _music_for_hour() -> String:
	var h := Game.hour
	if h < 10.0: return "morning"
	if h < 16.5: return "day"
	if h < 19.5: return "evening"
	return "night"

func _update_music() -> void:
	var want := _music_for_hour()
	if menus and menus.is_open() and menus.shop_open:
		want = "shop"
	if _sleeping:
		return
	if want != _music_mode:
		_music_mode = want
		Music.play(want, 3.0)

func _paused_frame() -> void:
	# menus pause the world but the camera may still glide (wardrobe)
	if get_tree().paused and is_inside_tree():
		_update_camera(get_process_delta_time() if get_process_delta_time() > 0 else 1.0 / 60.0)

func _process(dt: float) -> void:
	_check_menu()
	_update_music()
	_update_camera(dt)
	_update_daylight()
	_update_occluders(dt)
	_update_guide(dt)
	_update_visitors(dt)

var _guide: Node3D
var _guide_t := 0.0

## A soft golden arrow at Tommy's feet pointing to the dino that most needs
## care, when it's far away (Settings: guide arrow).
func _update_guide(dt: float) -> void:
	if _guide == null:
		_guide = Node3D.new()
		var mi := MeshInstance3D.new()
		# a flat rounded arrow lying on the grass, pointing -Z
		var st := SurfaceTool.new()
		st.begin(Mesh.PRIMITIVE_TRIANGLES)
		var pts := [Vector3(0, 0, -0.32), Vector3(0.26, 0, 0.0), Vector3(0.1, 0, 0.0),
			Vector3(0.1, 0, 0.22), Vector3(-0.1, 0, 0.22), Vector3(-0.1, 0, 0.0), Vector3(-0.26, 0, 0.0)]
		for t in [[0, 1, 6], [2, 3, 4], [2, 4, 5]]:
			for i in t:
				st.set_normal(Vector3.UP)
				st.add_vertex(pts[i])
		mi.mesh = st.commit()
		var m := StandardMaterial3D.new()
		m.albedo_color = Color(1.0, 0.82, 0.3)
		m.emission_enabled = true
		m.emission = Color(1.0, 0.75, 0.2)
		m.emission_energy_multiplier = 0.6
		m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		m.cull_mode = BaseMaterial3D.CULL_DISABLED
		mi.material_override = m
		mi.position = Vector3(0, 0, -0.95)
		_guide.add_child(mi)
		add_child(_guide)
	_guide_t += dt
	var target: Node3D = null
	if Game.settings.guide_arrow and not players.is_empty():
		var worst := 0.35
		for d in _dinos_root.get_children():
			var lo: float = d.needs[d.lowest_need()]
			if lo < worst and d.state != "sleep":
				worst = lo
				target = d
	var show := target != null and target.global_position.distance_to(players[0].global_position) > 5.0
	_guide.visible = show
	if show:
		var p := players[0].global_position
		_guide.global_position = p + Vector3(0, 0.06, 0)
		_guide.scale = Vector3.ONE * (1.0 + sin(_guide_t * 5.0) * 0.08)
		var d := target.global_position - p
		_guide.rotation.y = atan2(-d.x, -d.z)

## Tall things between the camera and Tommy fade out (dithered) so he is
## never lost behind the house or a tree.
func _update_occluders(dt: float) -> void:
	if players.is_empty():
		return
	var eye := cam.global_position
	var tgt := players[0].global_position + Vector3(0, 0.6, 0)
	for p in _props_root.get_children():
		var h: float = p.def.get("height", 0.0)
		if h <= 0.0:
			continue
		var c: Vector3 = p.global_position + Vector3(0, h * 0.5, 0)
		var seg := Geometry3D.get_closest_point_to_segment(c, eye, tgt)
		var fp: Vector2 = p.footprint()
		var r: float = maxf(fp.x, fp.y) * 0.5 + 0.6
		var behind: bool = seg.distance_to(c) < r + h * 0.25 and p.global_position.z > tgt.z - 0.5
		p.set_fade(move_toward(p.fade, 0.7 if behind else 0.0, dt * 3.0))

var cam_zoom := 1.0
var _cam_attr: CameraAttributesPractical
var cam_override := 0.0   # > 0: menus bring the camera close (wardrobe)

func _zoom_setting() -> float:
	if cam_override > 0.0:
		return cam_override
	if Dev.arg("zoom") != "":
		return float(Dev.arg("zoom"))
	return Game.CAMERA_ZOOMS[clampi(int(Game.settings.camera), 0, Game.CAMERA_ZOOMS.size() - 1)]

func _snap_camera() -> void:
	cam_zoom = _zoom_setting()
	Stage.place_camera(cam, _cam_target())
	cam.global_position = _cam_target() + Stage.cam_offset() * cam_zoom

func _cam_target() -> Vector3:
	var c := Vector3.ZERO
	for p in players:
		c += p.global_position
	c /= max(players.size(), 1)
	c.y = 0.5
	c.x = clamp(c.x, bounds.position.x + 6, bounds.end.x - 6)
	c.z = clamp(c.z, bounds.position.y + 2, bounds.end.y - 4)
	return c

func _update_camera(dt: float) -> void:
	cam_zoom = move_toward(cam_zoom, _zoom_setting(), dt * 1.5)
	var want := _cam_target() + Stage.cam_offset() * cam_zoom
	if _cam_attr:
		# keep the miniature blur around Tommy whatever the distance
		var dist := Stage.CAM_DIST * cam_zoom
		_cam_attr.dof_blur_near_distance = dist * 0.62
		_cam_attr.dof_blur_near_transition = dist * 0.22
		_cam_attr.dof_blur_far_distance = dist * 1.45
		_cam_attr.dof_blur_far_transition = dist * 0.7
	cam.global_position = cam.global_position.lerp(want, 1.0 - exp(-4.0 * dt))

func _update_daylight() -> void:
	var h := Game.hour
	# sun travels east to west from 6 to 20; at night a high cool "moon"
	# takes over so shadows stay short and soft
	var t: float = clamp((h - 6.0) / 14.0, 0.0, 1.0)
	var elev: float = sin(t * PI) * 58.0 + 14.0
	var yaw: float = lerp(-70.0, 70.0, t) + 145.0
	var night_amt: float = smoothstep(19.3, 20.8, h)
	var sun_rot := Vector3(-elev, yaw, 0)
	var moon_rot := Vector3(-55.0, 160.0, 0)
	sun.rotation_degrees = sun_rot.lerp(moon_rot, night_amt)
	var day := Color(1.0, 0.96, 0.88)
	var gold := Color(1.0, 0.72, 0.48)
	var moon := Color(0.55, 0.65, 1.0)
	var warm: float = max(1.0 - smoothstep(6.0, 8.0, h), smoothstep(16.5, 19.0, h) * (1.0 - night_amt))
	sun.light_color = day.lerp(gold, warm).lerp(moon, night_amt)
	sun.light_energy = lerp(1.0, 0.28, night_amt)
	env.ambient_light_energy = lerp(0.3, 0.42, night_amt)
	sky_mat.sky_top_color = Color(0.42, 0.66, 0.95).lerp(Color(0.95, 0.55, 0.45), warm * 0.5).lerp(Color(0.08, 0.1, 0.26), night_amt)
	sky_mat.sky_horizon_color = Color(0.82, 0.9, 0.97).lerp(Color(1.0, 0.75, 0.55), warm * 0.7).lerp(Color(0.2, 0.2, 0.4), night_amt)
	env.ambient_light_color = Color(0.8, 0.85, 1.0).lerp(Color(0.3, 0.36, 0.7), night_amt)
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR if night_amt > 0.0 else Environment.AMBIENT_SOURCE_SKY
	var lamps: float = smoothstep(18.5, 19.5, h)
	for p in _props_root.get_children():
		p.set_night(lamps)

# ---------------------------------------------------------------- effects

func fx_hearts(at: Vector3, n := 3) -> void:
	for i in n:
		var s := Sprite3D.new()
		s.texture = Icons.get_icon("heart")
		s.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		s.pixel_size = 0.0028
		s.no_depth_test = true
		s.position = at + Vector3(randf_range(-0.3, 0.3), 0, randf_range(-0.2, 0.2))
		add_child(s)
		var tw := create_tween()
		tw.set_parallel(true)
		tw.tween_property(s, "position:y", s.position.y + 1.0, 1.1).set_delay(i * 0.12)
		tw.tween_property(s, "modulate:a", 0.0, 0.5).set_delay(0.6 + i * 0.12)
		tw.chain().tween_callback(s.queue_free)

func fx_sparkles(at: Vector3) -> void:
	var p := CPUParticles3D.new()
	p.one_shot = true
	p.emitting = true
	p.amount = 18
	p.lifetime = 0.8
	p.explosiveness = 0.9
	p.direction = Vector3.UP
	p.spread = 70.0
	p.initial_velocity_min = 1.0
	p.initial_velocity_max = 2.2
	p.gravity = Vector3(0, -2, 0)
	var qm := QuadMesh.new()
	qm.size = Vector2(0.08, 0.08)
	var m := StandardMaterial3D.new()
	m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	m.billboard_mode = BaseMaterial3D.BILLBOARD_ENABLED
	m.albedo_color = Color(1, 0.95, 0.6)
	qm.material = m
	p.mesh = qm
	p.position = at + Vector3(0, 0.3, 0)
	add_child(p)
	get_tree().create_timer(1.5).timeout.connect(p.queue_free)

func fx_text(at: Vector3, key: String) -> void:
	var l := Label3D.new()
	l.text = tr("fx." + key)
	l.font = UiTheme.get_theme().default_font
	l.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	l.no_depth_test = true
	l.font_size = 48
	l.outline_size = 12
	l.pixel_size = 0.006
	l.position = at
	add_child(l)
	var tw := create_tween()
	tw.tween_property(l, "position:y", at.y + 0.6, 1.0)
	tw.tween_property(l, "modulate:a", 0.0, 0.4)
	tw.tween_callback(l.queue_free)

func fx_flash() -> void:
	if hud:
		hud.flash()

func toast(text: String, icon := "") -> void:
	if hud:
		hud.toast(text, icon)

func open_missions(_p: Player) -> void:
	_ensure_missions()
	menus.show_missions(self)

func open_shop(p: Player) -> void:
	menus.show_shop(self, p)

func _ensure_missions() -> void:
	var sp := []
	for d in _dinos_root.get_children():
		if not (d.species in sp):
			sp.append(d.species)
	var owned := []
	for it in _items_root.get_children():
		owned.append(it.id)
	for p in players:
		owned.append_array(p.slots)
	Missions.ensure_day(sp, owned)

func ask_sleep(p: Player) -> void:
	if Game.hour < 17.0:
		toast(tr("toast.too_early"), "sleep")
		return
	Game.running = false
	_on_day_ended()

# ---------------------------------------------------------------- day end

func _on_day_ended() -> void:
	if _sleeping:
		return
	_sleeping = true
	for p in players:
		p.frozen = true
		p.rig.once("yawn", "idle")
	await get_tree().create_timer(1.6).timeout
	var summary := _close_day()
	Game.save_game()
	Music.play("summary", 1.5)
	_music_mode = "summary"
	hud.show_day_summary(summary)
	await hud.summary_closed
	_sleeping = false
	Game.start_new_day()
	_morning()
	for p in players:
		p.frozen = false
		var sp: Array = map.spawn
		p.global_position = Vector3(sp[0], 0, sp[1])
	_snap_camera()

func _close_day() -> Dictionary:
	var s := {"day": Game.day, "coins": Game.today.get("coins_earned", 0), "happy": 0,
		"dinos": 0, "grew": [], "hatched": [], "today": Game.today.duplicate()}
	for d in _dinos_root.get_children():
		s.dinos += 1
		if d.happy_today or d.mood() > 0.6:
			s.happy += 1
		var g: String = d.end_of_day()
		if g != "":
			s.grew.append([d.dino_name, d.species, g])
	for p in _props_root.get_children():
		if p.def.get("incubator", false) and p.state.get("egg", "") != "":
			var sp: String = p.state.egg.substr(4)
			p.state = {}
			p.update_incubator_look()
			var hab: String = Content.dinos.get(sp, {}).get("habitat", "meadow")
			if not is_zone_open(hab):
				hab = "meadow"
			var at := habitat_spawn(hab)
			if Content.dinos.get(sp, {}).get("kind", "") == "swimmer":
				at = random_point_in_pond(0.3)
			# compys come in a little gang
			var nd: Dino = null
			for k in int(Content.dinos.get(sp, {}).get("group", 1)):
				nd = spawn_dino({"species": sp, "age": "baby", "name": _suggest_name(sp),
					"pos": [at.x + k * 0.5, at.z + (k % 2) * 0.4], "habitat": hab})
				nd.set_meta("unnamed", true)
			Sfx.play("hatch")
			s.hatched.append([nd.dino_name, sp])
		if p.def.get("plot", false) and p.state.get("crop", "") != "":
			if int(p.state.get("watered", 0)) == Game.day:
				p.state.grown = int(p.state.get("grown", 0)) + 1
			_refresh_plot(p)
	return s

## Neighbours come every morning; kids visit when the farm has happy dinos.
func spawn_npcs() -> void:
	for c in _npcs_root.get_children():
		c.free()
	var entry := Vector3(0, 0, 13.5)
	var shop := _prop_pos("shop", Vector3(-5, 0, 11.5))
	var inc := _prop_pos("incubator", Vector3(3, 0, 8))
	var board := _prop_pos("board", Vector3(-2.6, 0, 6))
	var juan := Npc.new()
	juan.setup("juan", "npc_juan", shop + Vector3(0, 0, -0.55), [shop + Vector3(0, 0, -0.55)])
	_npcs_root.add_child(juan)
	var nat := Npc.new()
	nat.setup("nat", "npc_nat", inc + Vector3(1.4, 0, 1.0), [inc + Vector3(1.4, 0, 1.0), Vector3(1.5, 0, -2.5), Vector3(4, 0, 4)])
	_npcs_root.add_child(nat)
	var juampi := Npc.new()
	juampi.setup("juampi", "npc_juampi", board + Vector3(1.2, 0, 1.0), [board + Vector3(1.2, 0, 1.0), Vector3(-6, 0, 6.5), Vector3(-1.5, 0, -2.5)])
	_npcs_root.add_child(juampi)
	_kids_today = 0
	for i in int(Dev.arg("kids", "0")):   # dev: visitors right away
		var k := Npc.new()
		k.setup("kid", KID_MODELS[i % KID_MODELS.size()], Vector3(-3.0 + i * 1.6, 0, 3.2 + (i % 2) * 0.8), [Vector3(0, 0, 3)])
		k.want = KID_WANTS[i % KID_WANTS.size()]
		_npcs_root.add_child(k)

var _kids_today := 0
var _kid_t := 30.0

func _prop_pos(id: String, def: Vector3) -> Vector3:
	for p in _props_root.get_children():
		if p.id == id:
			return p.global_position
	return def

const KID_WANTS := ["berries", "apple", "fern", "roots", "fish", "leaves"]
const KID_MODELS := ["npc_kid_a", "npc_kid_b", "npc_kid_c"]

func _update_visitors(dt: float) -> void:
	_kid_t -= dt
	if _kid_t > 0.0 or Game.hour > 16.0 or Game.hour < 8.0 or not Game.running:
		return
	_kid_t = randf_range(60.0, 140.0)
	var happy := 0
	for d in _dinos_root.get_children():
		if d.mood() > 0.55:
			happy += 1
	if happy == 0 or _kids_today >= mini(1 + happy / 2, 4):
		return
	_kids_today += 1
	var k := Npc.new()
	var places := [Vector3(randf_range(-3, 3), 0, randf_range(-3, 2)), Vector3(randf_range(-6, 6), 0, randf_range(1, 9))]
	k.setup("kid", KID_MODELS[randi() % KID_MODELS.size()], Vector3(randf_range(-1, 1), 0, 13.5), places)
	k.want = KID_WANTS[randi() % KID_WANTS.size()] if randf() < 0.7 else ""
	_npcs_root.add_child(k)
	toast(tr("toast.visitor"), "heart")
	# they leave after a while, dropping coins in the piggy bank by the gate
	get_tree().create_timer(randf_range(150.0, 260.0), false).timeout.connect(func():
		if is_instance_valid(k):
			var tip := 5 + happy * 3
			Game.add_coins(tip)
			toast(tr("toast.visitor_tip") % tip, "coin")
			k.leave(Vector3(0, 0, 14.5)))

func _morning() -> void:
	spawn_npcs()
	_ensure_missions()
	for d in _dinos_root.get_children():
		if d.has_meta("unnamed"):
			d.remove_meta("unnamed")
			var picks := []
			while picks.size() < 3:
				var n := _suggest_name(d.species)
				if not (n in picks):
					picks.append(n)
			_snap_camera()
			await get_tree().create_timer(0.6).timeout
			var done := [false]
			menus.show_naming(d.species, picks, func(nm):
				d.dino_name = nm
				done[0] = true
				toast(tr("toast.welcome") % nm, "heart"))
			while not done[0]:
				await get_tree().process_frame
			get_tree().paused = false

func _suggest_name(sp: String) -> String:
	var names := tr("names.suggest").split(",")
	if names.size() <= 1:
		names = ["Trici", "Coco", "Pipo", "Luna", "Rocco", "Mimi", "Bongo", "Kiwi"]
	return names[randi() % names.size()].strip_edges()

# ---------------------------------------------------------------- save / load

func save_state() -> Dictionary:
	var d := {"dinos": [], "props": [], "items": [], "open": open_zones, "uid": _uid, "habitat_rev": _habitat_rev}
	for n in _dinos_root.get_children():
		d.dinos.append(n.save())
	for n in _props_root.get_children():
		d.props.append(n.save())
	for n in _items_root.get_children():
		d.items.append([n.id, snappedf(n.position.x, 0.01), snappedf(n.position.z, 0.01)])
	d.players = []
	for p in players:
		d.players.append({"slots": p.slots, "active": p.active})
	return d

func load_state(d: Dictionary) -> void:
	for root in [_props_root, _dinos_root, _items_root]:
		for c in root.get_children():
			c.free()
	if d.is_empty():
		d = {"props": map.props, "dinos": map.dinos, "items": map.items, "open": ["meadow"], "habitat_rev": 0}
	# habitats furnished by the map (and newer layouts for older saves)
	if int(d.get("habitat_rev", 0)) < int(map.get("habitat_rev", 0)):
		d.props = d.props + map.get("habitat_props", [])
		d.habitat_rev = map.get("habitat_rev", 0)
	_habitat_rev = int(d.get("habitat_rev", 0))
	open_zones.assign(d.get("open", ["meadow"]))
	if _ground_img:
		_repaint_ground()
	_uid = int(d.get("uid", 1))
	for e in d.props:
		var st: Dictionary = e[4] if e.size() > 4 else {}
		var pr := spawn_prop(e[0], Vector3(e[1], 0, e[2]), int(e[3]) if e.size() > 3 else 0, st)
		if pr.def.get("plot", false):
			_refresh_plot(pr)
	for e in d.dinos:
		var dd: Dictionary = e.duplicate()
		if dd.get("name", "") == "":
			dd.name = _suggest_name(dd.species)
		spawn_dino(dd)
	for e in d.items:
		spawn_item(e[0], Vector3(e[1], 0, e[2]))
	spawn_npcs()
	var ps: Array = d.get("players", [])
	_ensure_missions.call_deferred()
	for i in min(ps.size(), players.size()):
		players[i].slots.assign(ps[i].slots)
		players[i].active = int(ps[i].active)
		players[i]._refresh_held()
		players[i].slots_changed.emit()
	_build_fences()
