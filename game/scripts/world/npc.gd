class_name Npc
extends CharacterBody3D
## A neighbour: Doctora Nat (eggs and dino facts), Tío Juampi (tips on the
## day's missions and a hand with things), Abuelo Juan (the shop stand) and
## visiting kids (small requests; they leave coins when the dinos are happy).
## They stroll between a few spots of their own during the day and go home
## at dusk. Everything they say comes from the language files.

const WALK := 1.3

var id := ""              # nat, juampi, juan, kid
var model_name := ""
var spots: Array = []     # Vector3 places they like
var home := Vector3.ZERO
var model: Node3D
var rig: AnimRig
var _goal := Vector3.ZERO
var _moving := false
var _wait := 0.0
var _facing := 0.0
var _talking := false
var _leaving := false
var want := ""            # kids: the item they asked for
var asked := false

func setup(nid: String, mname: String, at: Vector3, places: Array) -> void:
	id = nid
	model_name = mname
	position = at
	home = at
	spots = places

func _ready() -> void:
	add_to_group("npcs")
	add_to_group("interact")
	collision_layer = 4
	collision_mask = 1 | 8
	var col := CollisionShape3D.new()
	var cap := CapsuleShape3D.new()
	cap.radius = 0.3
	cap.height = 1.2
	col.shape = cap
	col.position.y = 0.6
	add_child(col)
	model = Content.instance_model(model_name, Vector3(0.5, 1.4, 0.4), Color(0.9, 0.6, 0.4))
	add_child(model)
	rig = AnimRig.new(model)
	_wait = randf_range(0.5, 3.0)

func display_name() -> String:
	return tr("npc." + id)

func _physics_process(dt: float) -> void:
	rig.tick()
	if _talking:
		rig.loop("talk")
		return
	if Game.hour >= 19.0 and not _leaving and id != "kid":
		_leaving = true
		_go(home)
	if _moving:
		var d := _goal - global_position
		d.y = 0
		if d.length() < 0.3:
			_moving = false
			_wait = randf_range(3.0, 8.0)
			if _leaving and id == "kid":
				queue_free()
		else:
			var want_yaw := atan2(d.x, d.z)
			_facing = lerp_angle(_facing, want_yaw, 1.0 - exp(-8.0 * dt))
			model.rotation.y = _facing
			velocity = Vector3(sin(_facing), 0, cos(_facing)) * WALK
			move_and_slide()
			global_position.y = 0
			rig.loop("walk", WALK / 1.6)
			return
	rig.loop("idle")
	_wait -= dt
	if _wait <= 0.0 and not _leaving and not spots.is_empty() and Dev.arg("still") == "":
		var p: Vector3 = spots[randi() % spots.size()]
		_go(p + Vector3(randf_range(-1.2, 1.2), 0, randf_range(-1.2, 1.2)))

func _go(p: Vector3) -> void:
	_goal = p
	_moving = true

func leave(exit: Vector3) -> void:
	_leaving = true
	_go(exit)

func face(p: Vector3) -> void:
	var d := p - global_position
	if Vector2(d.x, d.z).length() > 0.05:
		_facing = atan2(d.x, d.z)
		model.rotation.y = _facing

# ---------------------------------------------------------------- talking

func interact_point() -> Vector3:
	return global_position + Vector3(0, 0.8, 0)

func interact_info(p: Player) -> Dictionary:
	if id == "kid" and want != "" and p.held() == want:
		return {"verb": "give_kid", "icon": "feed", "priority": 3}
	return {"verb": "talk", "icon": "talk", "priority": 2}

func interact(p: Player, info: Dictionary) -> void:
	face(p.global_position)
	_moving = false
	var w := get_tree().get_first_node_in_group("world")
	if info.verb == "give_kid":
		p.take_held()
		p.anim_once("give")
		rig.once("happy")
		var coins := 15 + randi_range(0, 3) * 5
		Game.add_coins(coins)
		Game.count("kid_gifts")
		Sfx.play("coins")
		w.toast(tr("kid.thanks") % coins, "coin")
		want = ""
		return
	_talking = true
	p.anim_once("wave")
	var done := func():
		_talking = false
		_wait = 2.0
	match id:
		"juampi":
			w.menus.show_dialog(display_name(), [_juampi_tip()], [
				[tr("dlg.another_tip"), func(): w.menus.show_dialog(display_name(), [_general_tip()], [], done)],
			], done)
		"nat":
			w.menus.show_dialog(display_name(), [tr("nat.hello")], [
				[tr("dlg.buy_eggs"), func():
					done.call()
					w.menus.show_shop(w, p, 3)],
				[tr("dlg.dino_fact"), func(): w.menus.show_dialog(display_name(), [_fact()], [], done)],
			], done)
		"juan":
			w.menus.show_dialog(display_name(), [tr("juan.hello")], [
				[tr("dlg.shop"), func():
					done.call()
					w.menus.show_shop(w, p, 0)],
			], done)
		"kid":
			if want == "":
				w.menus.show_dialog(display_name(), [tr("kid.happy")], [], done)
			else:
				asked = true
				w.menus.show_dialog(display_name(), [tr("kid.want") % Content.item_name(want)], [], done)

func _juampi_tip() -> String:
	# a tip for the first unfinished mission of the day, else a general one
	for m in Missions.today:
		if not m.claimed and not Missions.is_done(m):
			var key := "tip." + str(m.id)
			if tr(key) != key:
				return tr("juampi.about") % Missions.text(m) + "\n" + tr(key)
	return _general_tip()

func _general_tip() -> String:
	var n := 1
	while tr("tip.general_%d" % (n + 1)) != "tip.general_%d" % (n + 1):
		n += 1
	return tr("tip.general_%d" % randi_range(1, n))

func _fact() -> String:
	var w := get_tree().get_first_node_in_group("world")
	var have := []
	for d in w.get_tree().get_nodes_in_group("dinos"):
		if not (d.species in have):
			have.append(d.species)
	if have.is_empty():
		have = Content.dinos.keys()
	var sp: String = have[randi() % have.size()]
	return "%s: %s" % [Content.dino_name(sp), tr("fact." + sp)]
