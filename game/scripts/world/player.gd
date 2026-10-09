class_name Player
extends CharacterBody3D
## Tommy (or a second player later: every input goes through `index`).
## Three inventory slots; the active one is held in the hand. A = context
## action on the best target in front; B = next slot, hold B = drop.

signal slots_changed()
signal target_changed(info: Dictionary)

const WALK := 1.6
const RUN := 3.5
const RUN_AFTER := 0.9      # seconds of full input before running
const REACH := 1.7
const DROP_HOLD := 0.45

var index := 0
var slots := ["", "", ""]
var active := 0
var frozen := false          # menus, dialogs, cut-scenes

var model: Node3D
var rig: AnimRig
var hand: Node3D             # small items
var arms: Node3D             # big items (both hands, chest height)
var held_node: Node3D
var target: Node = null
var target_info := {}
var _push_t := 0.0
var _b_t := -1.0
var _lock_until := 0.0
var _facing := 0.0
var _step_t := 0.0

func _ready() -> void:
	add_to_group("players")
	var col := CollisionShape3D.new()
	var cap := CapsuleShape3D.new()
	cap.radius = 0.28
	cap.height = 1.0
	col.shape = cap
	col.position.y = 0.5
	add_child(col)
	collision_layer = 2
	collision_mask = 1 | 4 | 8
	model = Content.instance_model("tommy", Vector3(0.45, 1.0, 0.35), Color(0.2, 0.45, 0.9))
	add_child(model)
	rig = AnimRig.new(model)
	hand = AnimRig.attach(model, "hand.R")
	if hand == null:
		hand = Node3D.new()
		hand.position = Vector3(0.25, 0.45, 0.15)
		model.add_child(hand)
	arms = Node3D.new()
	arms.position = Vector3(0, 0.5, 0.32)
	model.add_child(arms)
	var cap_node := Content.instance_model("cap_basic", Vector3.ZERO)
	var head := AnimRig.attach(model, "head")
	if head and ResourceLoader.exists(Content.model_path("cap_basic")):
		head.add_child(cap_node)
	_refresh_held()
	apply_outfit()

## Recolour Tommy by material role from Game.flags.outfit (role -> index
## into the wardrobe table). Materials are duplicated so only he changes.
func apply_outfit() -> void:
	var outfit: Dictionary = Game.flags.get("outfit", {})
	var table: Dictionary = Content.wardrobe
	for mi in find_children("*", "MeshInstance3D", true, false):
		if mi.mesh == null:
			continue
		for i in mi.mesh.get_surface_count():
			var m = mi.get_active_material(i)
			if not (m is ShaderMaterial):
				continue
			var role: String = m.resource_name
			var shade := 1.0
			if role == "cap_brim":
				role = "cap"
				shade = 0.85
			if not table.has(role):
				continue
			var idx: int = int(outfit.get(role, 0))
			var own: ShaderMaterial = m if m.has_meta("own") else m.duplicate()
			own.set_meta("own", true)
			own.set_shader_parameter("tint", Color(table[role][idx][1]) * Color(shade, shade, shade))
			own.set_shader_parameter("tint_mix", 0.0 if idx == 0 else 1.0)
			mi.set_surface_override_material(i, own)

## Pockets: three, four with the backpack from the shop.
func pocket_count() -> int:
	return 4 if Game.flags.get("backpack", false) else 3

func fit_pockets() -> void:
	while slots.size() < pocket_count():
		slots.append("")
	slots_changed.emit()

func held() -> String:
	return slots[active]

func held_def() -> Dictionary:
	return Content.items.get(slots[active], {})

func is_big(id: String) -> bool:
	return Content.items.get(id, {}).get("carry", "") == "big" or id.begins_with("egg_") or id.begins_with("box_")

## Put an item in the active slot if free, else the first free one.
func give_item(id: String) -> bool:
	if slots[active] == "":
		slots[active] = id
	else:
		var free := slots.find("")
		if free < 0:
			return false
		slots[free] = id
		active = free
	_refresh_held()
	slots_changed.emit()
	return true

## Give an item even with full pockets: what's in the active pocket is put
## down at Tommy's feet to make room (never lost).
func give_or_swap(id: String) -> void:
	if give_item(id):
		return
	var old := take_held()
	give_item(id)
	var w := get_tree().get_first_node_in_group("world")
	if w and old != "":
		w.spawn_item(old, front_point(0.6))

func take_held() -> String:
	var id: String = slots[active]
	slots[active] = ""
	_refresh_held()
	slots_changed.emit()
	return id

func has_free_slot() -> bool:
	return slots.has("")

func lock(seconds: float) -> void:
	_lock_until = Time.get_ticks_msec() / 1000.0 + seconds

func locked() -> bool:
	return frozen or Time.get_ticks_msec() / 1000.0 < _lock_until

func anim_once(name: String) -> float:
	var t := rig.once(name, _idle_name())
	lock(t * 0.85)
	return t

func face_towards(p: Vector3) -> void:
	var d := p - global_position
	d.y = 0
	if d.length() > 0.05:
		_facing = atan2(d.x, d.z)
		model.rotation.y = _facing

func _idle_name() -> String:
	return "carry_idle" if is_big(held()) else "idle"

func _physics_process(dt: float) -> void:
	rig.tick()
	var inp := Vector2.ZERO if locked() else Controls.move(index)
	var mag := inp.length()
	if mag > 0.9:
		_push_t += dt
	else:
		_push_t = 0.0
	var speed := 0.0
	if mag > 0.05:
		speed = RUN if _push_t > RUN_AFTER and Game.settings.get("autorun", true) and not is_big(held()) else WALK * clamp(mag * 1.2, 0.5, 1.0)
		var want := atan2(inp.x, inp.y)
		_facing = lerp_angle(_facing, want, 1.0 - exp(-14.0 * dt))
		model.rotation.y = _facing
	var dir := Vector3(inp.x, 0, inp.y).normalized() if mag > 0.05 else Vector3.ZERO
	velocity.x = dir.x * speed
	velocity.z = dir.z * speed
	velocity.y = 0.0 if is_on_floor() else velocity.y - 20.0 * dt
	move_and_slide()
	global_position.y = max(global_position.y, 0.0)
	# animation
	var big := is_big(held())
	if speed > 0.05:
		_step_t -= dt * speed
		if _step_t <= 0.0:
			_step_t = 0.8
			Sfx.play("step_grass_%d" % randi_range(1, 3), 0.1, -6.0)
	if speed > WALK + 0.1:
		rig.loop("run", speed / RUN)
	elif speed > 0.05:
		rig.loop("carry_walk" if big else "walk", speed / WALK)
	else:
		rig.loop("carry_idle" if big else "idle")
	if not locked():
		_update_target()
		_handle_buttons(dt)

func _handle_buttons(dt: float) -> void:
	if Controls.pressed(index, "a"):
		_do_action()
	if Controls.pressed(index, "b"):
		_b_t = 0.0
	if _b_t >= 0.0:
		if Controls.held(index, "b"):
			_b_t += dt
			if _b_t >= DROP_HOLD:
				_b_t = -1.0
				drop_held()
		else:
			_b_t = -1.0
			next_slot()

func next_slot() -> void:
	active = (active + 1) % slots.size()
	_refresh_held()
	slots_changed.emit()
	Sfx.play("slot")

func drop_held() -> void:
	if held() == "":
		return
	var id := take_held()
	var w := get_tree().get_first_node_in_group("world")
	if w:
		w.spawn_item(id, front_point(0.8))
	Sfx.play("drop")

func front_point(dist := 0.8) -> Vector3:
	return global_position + Vector3(sin(_facing), 0, cos(_facing)) * dist

func forward() -> Vector3:
	return Vector3(sin(_facing), 0, cos(_facing))

func _update_target() -> void:
	var best: Node = null
	var best_score := INF
	var best_info := {}
	var fwd := forward()
	for n in get_tree().get_nodes_in_group("interact"):
		if not is_instance_valid(n) or n == self:
			continue
		var p: Vector3 = n.interact_point() if n.has_method("interact_point") else n.global_position
		var d := p - global_position
		d.y = 0
		var reach: float = REACH + (n.interact_radius() if n.has_method("interact_radius") else 0.0)
		var dist := d.length()
		if dist > reach:
			continue
		var ang := fwd.angle_to(d.normalized()) if dist > 0.05 else 0.0
		if ang > deg_to_rad(75):
			continue
		var info: Dictionary = n.interact_info(self)
		if info.is_empty():
			continue
		var score := dist + ang * 0.9 - float(info.get("priority", 0)) * 0.3
		if score < best_score:
			best_score = score
			best = n
			best_info = info
	if best == null:
		best_info = _self_action()
	if best != target or best_info.get("verb", "") != target_info.get("verb", ""):
		target = best
		target_info = best_info
		target_changed.emit(target_info)

## Actions that need no target: place a packed prop, throw the ball.
func _self_action() -> Dictionary:
	var d := held_def()
	if held().begins_with("box_"):
		return {"verb": "place", "icon": "place"}
	if d.get("throwable", false):
		return {"verb": "throw", "icon": "throw"}
	if d.get("tool", "") == "fish":
		var w := get_tree().get_first_node_in_group("world")
		var fp := front_point(1.4)
		if w and w.is_zone_open("lagoon") and w.pond_dist(Vector2(fp.x, fp.z)) < 0.3:
			return {"verb": "fish", "icon": "water"}
	return {}

func _do_action() -> void:
	if target and is_instance_valid(target):
		if target_info.get("disabled", false):
			Sfx.play("nope")
			return
		face_towards(target.interact_point() if target.has_method("interact_point") else target.global_position)
		target.interact(self, target_info)
		_clear_target()
		return
	match target_info.get("verb", ""):
		"place":
			var w := get_tree().get_first_node_in_group("world")
			if w and w.place_prop_from(self):
				anim_once("pickup")
		"fish":
			var w := get_tree().get_first_node_in_group("world")
			var wait := randf_range(1.5, 3.0)
			anim_once("use")
			lock(wait + 0.6)
			w.toast(tr("toast.fish_wait"), "water")
			await get_tree().create_timer(wait, false).timeout
			Sfx.play("splash")
			anim_once("happy")
			give_or_swap("fish")
			w.toast(tr("toast.fish_got"), "harvest")
			Game.count("fished")
		"throw":
			var w := get_tree().get_first_node_in_group("world")
			if w:
				var id := take_held()
				anim_once("give")
				w.throw_item(id, global_position + Vector3(0, 0.7, 0), forward())

func _clear_target() -> void:
	target = null
	target_info = {}
	target_changed.emit({})

func _refresh_held() -> void:
	if held_node:
		held_node.queue_free()
		held_node = null
	var id := held()
	if id == "":
		return
	var model_name: String = Content.items.get(id, {}).get("model", "item_" + id)
	if id.begins_with("egg_"):
		model_name = id
	elif id.begins_with("box_"):
		model_name = "item_box"
	held_node = Content.instance_model(model_name, Vector3(0.18, 0.18, 0.18), Color(1, 0.8, 0.3))
	if is_big(id):
		arms.add_child(held_node)
	else:
		hand.add_child(held_node)
