class_name Dino
extends CharacterBody3D
## A dinosaur: needs (panza/limpieza/juego/cariño), friendship, growth stage
## and a small state machine. Nothing bad ever happens: a neglected dino
## just sits and looks a bit sad until someone cares for it.

const NEED_KEYS := ["food", "clean", "fun", "love"]
const DECAY := {"food": 0.045, "clean": 0.022, "fun": 0.04, "love": 0.035}  # per game hour
const AGES := ["baby", "juv", "adult"]
const AGE_SCALE := {"baby": 0.45, "juv": 0.7, "adult": 1.0}
const AGE_DAYS := {"baby": 2, "juv": 3}    # happy days needed to grow

var species := "trike"
var dino_name := ""
var age := "baby"
var grow_days := 0
var needs := {"food": 0.8, "clean": 0.9, "fun": 0.7, "love": 0.6}
var friendship := 0          # points; 20 per heart, 5 hearts
var habitat := "meadow"
var uid := 0
var happy_today := false

var def := {}
var model: Node3D
var rig: AnimRig
var bubble: Sprite3D
var state := "idle"
var _state_t := 0.0
var _goal := Vector3.ZERO
var _goal_node: Node = null
var _facing := 0.0
var _stuck_t := 0.0
var _last_pos := Vector3.ZERO
var _pet_cool := 0.0
var _poop_t := -1.0

func setup(d: Dictionary) -> void:
	species = d.get("species", species)
	dino_name = d.get("name", "")
	age = d.get("age", "baby")
	grow_days = int(d.get("grow", 0))
	friendship = int(d.get("friend", 0))
	uid = int(d.get("uid", 0))
	if d.has("needs"):
		for k in NEED_KEYS:
			needs[k] = float(d.needs.get(k, needs[k]))
	def = Content.dinos.get(species, {})
	habitat = d.get("habitat", def.get("habitat", "meadow"))
	if d.has("pos"):
		position = Vector3(d.pos[0], 0, d.pos[1])

func save() -> Dictionary:
	return {"species": species, "name": dino_name, "age": age, "grow": grow_days,
		"friend": friendship, "uid": uid, "habitat": habitat,
		"needs": needs.duplicate(), "pos": [snappedf(position.x, 0.01), snappedf(position.z, 0.01)]}

func size() -> float:
	return float(def.get("size", 1.0)) * AGE_SCALE[age]

func _ready() -> void:
	add_to_group("dinos")
	add_to_group("interact")
	collision_layer = 4
	collision_mask = 1 | 4
	var col := CollisionShape3D.new()
	var cap := CapsuleShape3D.new()
	var s := size()
	cap.radius = clamp(s * 0.28, 0.12, 1.0)
	cap.height = max(s * 0.7, cap.radius * 2.0)
	col.shape = cap
	col.position.y = cap.height / 2.0
	add_child(col)
	_build_model()
	bubble = Sprite3D.new()
	bubble.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	bubble.pixel_size = 0.004
	bubble.position.y = s * 1.15 + 0.35
	bubble.no_depth_test = true
	bubble.render_priority = 10
	bubble.visible = false
	add_child(bubble)
	_facing = randf() * TAU
	if Dev.arg("still") != "":
		_facing = PI * 0.15
	model.rotation.y = _facing
	if Dev.arg("still") == "":
		_pick_wander()

func _build_model() -> void:
	if model:
		model.queue_free()
	var name := "%s_%s" % [species, age]
	var scale_fix := 1.0
	if not ResourceLoader.exists(Content.model_path(name)):
		if ResourceLoader.exists(Content.model_path(species + "_adult")):
			name = species + "_adult"
			scale_fix = AGE_SCALE[age]
	var s := size()
	model = Content.instance_model(name, Vector3(s * 0.6, s, s * 1.1), Color.from_hsv(hash(species) % 360 / 360.0, 0.45, 0.9))
	model.scale = Vector3.ONE * scale_fix
	add_child(model)
	rig = AnimRig.new(model)

func walk_speed() -> float:
	var w := float(def.get("walk", 1.0))
	return w * (0.67 if age == "baby" else (0.83 if age == "juv" else 1.0))

func mood() -> float:
	var t := 0.0
	for k in NEED_KEYS:
		t += needs[k]
	return t / NEED_KEYS.size()

func hearts() -> int:
	return min(friendship / 20, 5)

func lowest_need() -> String:
	var lo := "food"
	for k in NEED_KEYS:
		if needs[k] < needs[lo]:
			lo = k
	return lo

# ---------------------------------------------------------------- update

func _physics_process(dt: float) -> void:
	rig.tick()
	var hours := dt * _hours_per_second()
	for k in NEED_KEYS:
		var rate: float = DECAY[k]
		if k == "clean":
			rate += 0.01 * _world().poops_in(habitat)
		if state == "sleep":
			rate *= 0.3
		needs[k] = clamp(needs[k] - rate * hours, 0.0, 1.0)
	if mood() > 0.6:
		happy_today = true
	_pet_cool = max(_pet_cool - dt, 0.0)
	if _poop_t > 0.0:
		_poop_t -= dt
		if _poop_t <= 0.0:
			_world().spawn_item("poop", global_position - _fwd() * size() * 0.5)
	_state_t -= dt
	match state:
		"idle":
			rig.loop("sad" if mood() < 0.3 else "idle")
			if _state_t <= 0.0:
				_think()
		"wander", "goto":
			_walk_to(_goal, dt)
		"react", "eat":
			if _state_t <= 0.0:
				_set_state("idle", randf_range(1.0, 3.0))
		"sleep":
			rig.loop("sleep")
			if Game.hour < 20.0 and Game.running:
				_set_state("idle", 1.0)
	_update_bubble()

func _hours_per_second() -> float:
	if not Game.running:
		return 0.0
	var r := (Game.DAY_END - Game.DAY_START) / (float(Game.settings.day_minutes) * 60.0)
	if Dev.arg("fast") != "":
		r *= float(Dev.arg("fast"))
	return r

func _world() -> Node:
	return get_tree().get_first_node_in_group("world")

func _fwd() -> Vector3:
	return Vector3(sin(_facing), 0, cos(_facing))

func _set_state(s: String, t: float) -> void:
	state = s
	_state_t = t

func _think() -> void:
	if Dev.arg("still") != "":
		_set_state("idle", 2.0)
		return
	if Game.hour >= 20.0:
		var nest = _world().find_feature(habitat, "bed", global_position)
		if nest and global_position.distance_to(nest.global_position) > 1.2:
			_go(nest.global_position + Vector3(randf_range(-0.4, 0.4), 0, randf_range(-0.4, 0.4)), nest)
		else:
			_set_state("sleep", 999.0)
		return
	if needs.food < 0.55:
		var trough = _world().find_feeder(habitat, def.get("diet", []), global_position)
		if trough:
			_go(trough.interact_point(), trough)
			return
	if mood() < 0.3 and randf() < 0.6:
		_set_state("idle", randf_range(3.0, 6.0))
		return
	if randf() < 0.65:
		_pick_wander()
	else:
		if randf() < 0.3 and rig.has("call"):
			rig.once("call")
			if _world().players[0].global_position.distance_to(global_position) < 9.0:
				voice()
		_set_state("idle", randf_range(2.0, 5.0))

func _pick_wander() -> void:
	var p: Vector3 = _world().random_point_in(habitat, global_position, 6.0)
	_go(p, null)
	state = "wander"

func _go(p: Vector3, node: Node) -> void:
	_goal = p
	_goal_node = node
	_stuck_t = 0.0
	_set_state("goto", 20.0)

func _walk_to(p: Vector3, dt: float) -> void:
	var d := p - global_position
	d.y = 0
	var arrive := 0.35 + (0.4 if _goal_node else 0.0) + size() * 0.25
	if d.length() < arrive or _state_t <= 0.0 or _stuck_t > 1.5:
		velocity = Vector3.ZERO
		if _goal_node and is_instance_valid(_goal_node) and d.length() < arrive + 0.6:
			_arrived(_goal_node)
		else:
			_set_state("idle", randf_range(1.5, 4.0))
		return
	var want := atan2(d.x, d.z)
	_facing = lerp_angle(_facing, want, 1.0 - exp(-6.0 * dt))
	model.rotation.y = _facing
	var sp := walk_speed() * (0.6 if mood() < 0.3 else 1.0)
	velocity = _fwd() * sp
	velocity.y = 0
	move_and_slide()
	global_position.y = 0.0
	rig.loop("walk", sp / walk_speed())
	if global_position.distance_to(_last_pos) < sp * dt * 0.3:
		_stuck_t += dt
	else:
		_stuck_t = max(_stuck_t - dt, 0.0)
	_last_pos = global_position

func _arrived(node: Node) -> void:
	if node.has_method("feed_dino") and node.feed_dino(self):
		face(node.global_position)
		var t := rig.once("eat")
		_eat_effects(0.45, false)
		_set_state("eat", t)
		return
	if node.has_method("is_bed"):
		_set_state("sleep", 999.0)
		return
	_set_state("idle", 2.0)

func face(p: Vector3) -> void:
	var d := p - global_position
	if Vector2(d.x, d.z).length() > 0.05:
		_facing = atan2(d.x, d.z)
		model.rotation.y = _facing

func _eat_effects(amount: float, from_hand: bool) -> void:
	needs.food = clamp(needs.food + amount, 0.0, 1.0)
	if _poop_t <= 0.0 and randf() < 0.5:
		_poop_t = randf_range(20.0, 50.0)
	if from_hand:
		needs.love = clamp(needs.love + 0.08, 0.0, 1.0)

# ---------------------------------------------------------------- player

func interact_point() -> Vector3:
	return global_position + Vector3(0, size() * 0.5, 0)

func interact_radius() -> float:
	return size() * 0.35

func interact_info(p: Player) -> Dictionary:
	var item := p.held()
	var d := p.held_def()
	if state == "sleep":
		return {"verb": "pet", "icon": "pet", "priority": 2}
	if d.get("kind", "") == "food":
		if d.get("food", "") in def.get("diet", []):
			return {"verb": "feed", "icon": "feed", "priority": 3}
		return {"verb": "offer", "icon": "feed", "priority": 3}
	match d.get("tool", ""):
		"brush":
			return {"verb": "brush", "icon": "brush", "priority": 3}
		"ball":
			return {"verb": "play", "icon": "ball", "priority": 3}
		"photo":
			return {"verb": "photo", "icon": "photo", "priority": 3}
	return {"verb": "pet", "icon": "pet", "priority": 2}

func interact(p: Player, info: Dictionary) -> void:
	face(p.global_position)
	velocity = Vector3.ZERO
	match info.verb:
		"pet":
			p.anim_once("pet_low" if size() < 0.75 else "pet")
			if state != "sleep":
				_set_state("react", rig.once("pet"))
			var gain := 0.25 if _pet_cool <= 0.0 else 0.06
			needs.love = clamp(needs.love + gain, 0.0, 1.0)
			needs.fun = clamp(needs.fun + 0.05, 0.0, 1.0)
			if _pet_cool <= 0.0:
				_befriend(2)
			_pet_cool = 20.0
			_world().fx_hearts(interact_point() + Vector3(0, size() * 0.4, 0), 3)
			Sfx.play("pet")
			voice()
			Game.count("pets")
			Game.count("pet_" + species)
		"feed":
			var food: String = p.held_def().get("food", "")
			p.take_held()
			p.anim_once("give")
			_set_state("eat", rig.once("eat"))
			_eat_effects(0.4, true)
			if food == def.get("fav", ""):
				needs.love = clamp(needs.love + 0.15, 0.0, 1.0)
				_befriend(3)
				_world().fx_hearts(interact_point() + Vector3(0, size() * 0.4, 0), 5)
			else:
				_befriend(1)
			Sfx.play("eat")
			Game.count("fed")
			Game.count("fed_" + species)
		"offer":
			p.anim_once("give")
			_set_state("react", rig.once("sad") if rig.has("sad") else 1.0)
			_world().fx_text(interact_point() + Vector3(0, size() * 0.5, 0), "nope")
			Sfx.play("nope")
		"brush":
			p.anim_once("use")
			_set_state("react", rig.once("happy"))
			needs.clean = clamp(needs.clean + 0.5, 0.0, 1.0)
			_befriend(1)
			_world().fx_sparkles(interact_point())
			Sfx.play("brush")
			Game.count("brushed")
		"play":
			p.anim_once("give")
			_set_state("react", rig.once("play") if rig.has("play") else rig.once("happy"))
			needs.fun = clamp(needs.fun + 0.4, 0.0, 1.0)
			_befriend(1)
			Sfx.play("ball")
			voice()
			Game.count("played")
		"photo":
			p.anim_once("use")
			_set_state("react", rig.once("happy"))
			Game.count("photo_" + species)
			Game.flags["photo_" + species] = true
			_world().fx_flash()
			Sfx.play("photo")

func voice() -> void:
	var s := size()
	var v := "baby" if age == "baby" else ("tiny" if s < 0.5 else ("small" if s < 1.0 else ("mid" if s < 2.0 else "big")))
	Sfx.play("voice_%s_%d" % [v, randi_range(1, 2)], 0.06, -4.0)

func _befriend(n: int) -> void:
	var before := hearts()
	friendship = min(friendship + n, 100)
	if hearts() > before:
		Sfx.play("heart")
		_world().toast(tr("toast.heart_up") % [dino_name if dino_name != "" else Content.dino_name(species)], "heart")

func _update_bubble() -> void:
	var lo := lowest_need()
	var show: bool = state != "sleep" and needs[lo] < 0.35
	if show:
		var tex := Icons.get_icon("need_" + lo)
		if bubble.texture != tex:
			bubble.texture = tex
	bubble.visible = show and bubble.texture != null

## Called by the world at the end of each day.
func end_of_day() -> String:
	var grew := ""
	if happy_today and age != "adult":
		grow_days += 1
		if grow_days >= AGE_DAYS[age]:
			age = AGES[AGES.find(age) + 1]
			grow_days = 0
			grew = age
			_build_model()
	happy_today = false
	# a night's sleep tops a little of everything up
	for k in NEED_KEYS:
		needs[k] = clamp(needs[k] + 0.15, 0.0, 1.0)
	return grew
