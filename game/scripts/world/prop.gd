class_name Prop
extends StaticBody3D
## Anything placed on the 1 m grid. What it does comes from its content
## entry: feeder (trough), bed (nest), incubator, plot (garden), missions
## (board), home (house), harvest (bush gives items once a day), shake
## (tree drops fruit once a day), light (lamp turns on at night).

var id := ""
var def := {}
var rot := 0              # quarter turns
var state := {}           # saved per-prop state (food left, plant, egg...)
var model: Node3D
var _light: OmniLight3D
var fade := 0.0
var _fade_mats := []

func set_fade(v: float) -> void:
	if is_equal_approx(v, fade):
		return
	fade = v
	if _fade_mats.is_empty():
		# own copies so only this prop fades
		for mi in model.find_children("*", "MeshInstance3D", true, false):
			for i in mi.mesh.get_surface_count():
				var m = mi.get_active_material(i)
				if m is ShaderMaterial:
					var c: ShaderMaterial = m.duplicate()
					mi.set_surface_override_material(i, c)
					_fade_mats.append(c)
	for m in _fade_mats:
		m.set_shader_parameter("fade", fade)

func setup(pid: String, pos: Vector3, r := 0, st := {}) -> void:
	id = pid
	def = Content.props.get(id, {})
	rot = r
	state = st.duplicate(true)
	position = pos
	rotation.y = r * PI / 2.0

func save() -> Array:
	return [id, snappedf(position.x, 0.01), snappedf(position.z, 0.01), rot, state]

func footprint() -> Vector2:
	var s: Array = def.get("size", [1, 1])
	return Vector2(s[0], s[1])

func _ready() -> void:
	add_to_group("props")
	if _interactive():
		add_to_group("interact")
	collision_layer = 1
	model = Content.instance_model(def.get("model", "prop_" + id), Vector3(footprint().x * 0.8, 0.6, footprint().y * 0.8), Color(0.8, 0.7, 0.55))
	add_child(model)
	if not def.get("walk", false) and not def.has("plant_on"):
		var col := CollisionShape3D.new()
		var box := BoxShape3D.new()
		var fp := footprint()
		if def.has("shake") or id.begins_with("tree") or id == "palm" or id == "lamp":
			box.size = Vector3(0.45, 2.0, 0.45)
		elif id in ["flowers", "fern_clump", "garden_plot", "nest"]:
			box.size = Vector3.ZERO
		else:
			box.size = Vector3(fp.x * 0.85, 1.2, fp.y * 0.85)
		if box.size != Vector3.ZERO:
			col.shape = box
			col.position.y = box.size.y / 2.0
			add_child(col)
	if def.get("light", false):
		_light = OmniLight3D.new()
		_light.position.y = 1.9
		_light.omni_range = 7.0
		_light.light_color = Color(1.0, 0.85, 0.55)
		_light.light_energy = 0.0
		add_child(_light)
	if def.get("feeder", "") != "":
		_update_feeder_look()
	if def.has("incubator"):
		update_incubator_look()

func update_incubator_look() -> void:
	var old := get_node_or_null("Egg")
	if old:
		old.free()
	var egg: String = state.get("egg", "")
	if egg == "":
		return
	var m := Content.instance_model(egg if ResourceLoader.exists(Content.model_path(egg)) else "egg_trike", Vector3(0.2, 0.26, 0.2), Color(1, 0.95, 0.85))
	m.name = "Egg"
	m.position = Vector3(0, 0.42, 0)
	add_child(m)
	var ap: AnimationPlayer = m.find_child("AnimationPlayer", true, false)
	if ap and ap.has_animation("wobble"):
		ap.get_animation("wobble").loop_mode = Animation.LOOP_LINEAR
		ap.play("wobble")

func _interactive() -> bool:
	if not def.get("fixed", false):
		return true
	for k in ["feeder", "incubator", "plot", "missions", "home", "harvest", "shake", "shop"]:
		if def.has(k):
			return true
	return false

func set_night(amount: float) -> void:
	if _light:
		_light.light_energy = amount * 2.6

func interact_point() -> Vector3:
	return global_position + Vector3(0, 0.5, 0)

func interact_radius() -> float:
	return max(footprint().x, footprint().y) * 0.45

func is_bed() -> bool:
	return def.get("bed", false)

func world() -> Node:
	return get_tree().get_first_node_in_group("world")

# ---------------------------------------------------------------- feeders

func food_left() -> int:
	return int(state.get("food", 0))

func feeder_food() -> String:
	return state.get("tag", "")

## A dino arriving to eat: true if it ate.
func feed_dino(d: Dino) -> bool:
	if def.get("feeder", "") == "water":
		d.needs.food = clamp(d.needs.food + 0.05, 0.0, 1.0)
		return true
	if food_left() <= 0 or not (feeder_food() in d.def.get("diet", [])):
		return false
	state.food = food_left() - 1
	_update_feeder_look()
	return true

func _update_feeder_look() -> void:
	# the trough shows little copies of the food it holds (one per 2 portions)
	var bed := model.find_child("food", true, false) as Node3D
	if bed:
		bed.visible = food_left() > 0
	var pile := get_node_or_null("FoodPile")
	if pile:
		pile.free()
	if food_left() <= 0 or def.get("feeder", "") != "food":
		return
	pile = Node3D.new()
	pile.name = "FoodPile"
	add_child(pile)
	var item: Dictionary = {}
	for id in Content.items:
		if Content.items[id].get("food", "") == feeder_food():
			item = Content.items[id]
			break
	var n := int(ceil(food_left() / 2.0))
	for i in n:
		var m := Content.instance_model(item.get("model", "item_fern"), Vector3(0.15, 0.15, 0.15), Color(0.4, 0.8, 0.3))
		var x := (float(i) - (n - 1) / 2.0) * 0.32
		m.position = Vector3(x, 0.42, randf_range(-0.06, 0.06))
		m.rotation.y = randf() * TAU
		m.scale = Vector3.ONE * 1.6
		m.rotation.z = deg_to_rad(80) if randf() < 0.5 else 0.0
		pile.add_child(m)

# ---------------------------------------------------------------- player

func interact_info(p: Player) -> Dictionary:
	var held := p.held_def()
	if def.has("feeder") and def.feeder == "food":
		if held.get("kind", "") == "food":
			return {"verb": "fill", "icon": "fill", "priority": 2}
		return _pack_info(p)
	if def.has("incubator"):
		if state.get("egg", "") == "" and p.held().begins_with("egg_"):
			return {"verb": "incubate", "icon": "egg", "priority": 3}
		if state.get("egg", "") != "":
			return {"verb": "look_egg", "icon": "egg", "priority": 1}
		return _pack_info(p)
	if def.has("harvest"):
		if int(state.get("day", 0)) != Game.day:
			return {"verb": "harvest", "icon": "harvest", "priority": 1}
		return {}
	if def.has("shake"):
		if int(state.get("day", 0)) != Game.day:
			return {"verb": "shake", "icon": "shake", "priority": 1}
		return {}
	if def.has("plot"):
		return world().plot_info(self, p)
	if def.has("missions"):
		return {"verb": "missions", "icon": "missions", "priority": 2}
	if def.has("home"):
		return {"verb": "sleep", "icon": "sleep", "priority": 1}
	if def.has("shop"):
		return {"verb": "shop", "icon": "shop", "priority": 2}
	return _pack_info(p)

## Any movable thing can be packed back into its box with an empty hand.
func _pack_info(p: Player) -> Dictionary:
	if def.get("fixed", false) or p.held() != "" or not p.has_free_slot():
		return {}
	if def.has("incubator") and state.get("egg", "") != "":
		return {}
	return {"verb": "pack", "icon": "place", "priority": 0}

func interact(p: Player, info: Dictionary) -> void:
	match info.verb:
		"fill":
			var tag: String = p.held_def().get("food", "")
			if feeder_food() != tag and food_left() > 0:
				# a different food: the old one is swapped out, no loss
				state.food = 0
			state.tag = tag
			state.food = min(food_left() + 3, 9)
			p.take_held()
			p.anim_once("give")
			_update_feeder_look()
			Sfx.play("fill")
			Game.count("filled")
		"incubate":
			state.egg = p.take_held()
			state.since = Game.day
			update_incubator_look()
			p.anim_once("give")
			Sfx.play("egg")
			world().toast(tr("toast.egg_in"), "egg")
		"look_egg":
			world().toast(tr("toast.egg_wait"), "egg")
		"harvest":
			var item: String = def.harvest
			if p.give_item(item):
				state.day = Game.day
				p.anim_once("pickup")
				Sfx.play("pickup")
				Game.count("harvested")
			else:
				world().toast(tr("toast.hands_full"), "hands")
		"shake":
			state.day = Game.day
			p.anim_once("use")
			Sfx.play("shake")
			var n := 2
			for i in n:
				var off := Vector3(randf_range(-1.0, 1.0), 0, randf_range(0.6, 1.3))
				world().spawn_item(def.shake, global_position + off)
		"missions":
			world().open_missions(p)
		"sleep":
			world().ask_sleep(p)
		"shop":
			world().open_shop(p)
		"pack":
			if p.give_item("box_" + id):
				p.anim_once("pickup")
				Sfx.play("pickup")
				queue_free()
		_:
			if def.has("plot"):
				world().plot_do(self, p, info)
