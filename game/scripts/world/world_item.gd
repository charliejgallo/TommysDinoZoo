class_name WorldItem
extends Node3D
## A loose item lying on the ground (dropped, dropped by a tree, a dino's
## poop). A picks it up; poop needs the shovel.

var id := ""
var def := {}
var model: Node3D
var _bob := randf() * TAU
var vel := Vector3.ZERO
var flying := false

func setup(iid: String, pos: Vector3) -> void:
	id = iid
	def = Content.items.get(id, {})
	position = pos

func _ready() -> void:
	add_to_group("interact")
	add_to_group("items")
	var mname: String = def.get("model", "item_" + id)
	if id.begins_with("egg_"):
		mname = id
	elif id.begins_with("box_"):
		mname = "item_box"
	model = Content.instance_model(mname, Vector3(0.2, 0.2, 0.2), Color(1, 0.75, 0.3))
	add_child(model)

func _process(dt: float) -> void:
	if flying:
		vel.y -= 12.0 * dt
		position += vel * dt
		if position.y <= 0.0:
			position.y = 0.0
			if vel.length() < 1.0:
				flying = false
			vel = Vector3(vel.x * 0.5, -vel.y * 0.35, vel.z * 0.5)
		return
	if id != "poop":
		_bob += dt * 2.0
		model.position.y = 0.04 + sin(_bob) * 0.03
		model.rotation.y += dt * 0.6

func interact_point() -> Vector3:
	return global_position

func interact_info(p: Player) -> Dictionary:
	if def.get("needs_tool", "") != "":
		if p.held_def().get("tool", "") == def.needs_tool:
			return {"verb": "scoop", "icon": "scoop", "priority": 2}
		return {"verb": "need_" + def.needs_tool, "icon": "scoop", "priority": 0, "disabled": true}
	if not p.has_free_slot():
		return {"verb": "hands_full", "icon": "hands", "priority": 0, "disabled": true}
	return {"verb": "pickup", "icon": "pickup", "priority": 1}

func interact(p: Player, info: Dictionary) -> void:
	match info.verb:
		"pickup":
			if p.give_item(id):
				p.anim_once("pickup")
				Sfx.play("pickup")
				queue_free()
		"scoop":
			p.anim_once("dig")
			Sfx.play("scoop")
			Game.count("poops")
			var w := get_tree().get_first_node_in_group("world")
			w.fx_sparkles(global_position)
			queue_free()
