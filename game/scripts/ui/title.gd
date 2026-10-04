extends Node3D
## Title screen: a little diorama of the farm with a slowly drifting
## camera behind the menu.

var cam: Camera3D
var _t := 0.0
var menus: Menus

func _ready() -> void:
	Game.apply_settings()
	Stage.make_env(self)
	var g := MeshInstance3D.new()
	var pm := PlaneMesh.new()
	pm.size = Vector2(80, 80)
	g.mesh = pm
	var gm := ShaderMaterial.new()
	gm.shader = Look.TOON
	gm.set_shader_parameter("albedo", Color("#8fd46a"))
	gm.set_shader_parameter("rim_dark", 0.0)
	g.material_override = gm
	add_child(g)
	var scene := [
		["prop_house", Vector3(-4, 0, -5), 20.0], ["prop_tree_round", Vector3(5, 0, -6), 0.0],
		["prop_tree_fruit", Vector3(-9, 0, -2), 0.0], ["prop_fence", Vector3(2, 0, 1), 0.0],
		["prop_fence", Vector3(3, 0, 1), 0.0], ["prop_fence", Vector3(4, 0, 1), 0.0],
		["prop_flowers", Vector3(-1.5, 0, -1.5), 0.0], ["prop_incubator", Vector3(0.5, 0, -3), 0.0],
		["brachio_adult", Vector3(8, 0, -9), -40.0], ["trike_adult", Vector3(3, 0, -1.5), -30.0],
		["trike_baby", Vector3(1.6, 0, -0.6), -10.0], ["raptor_adult", Vector3(-3.5, 0, 0.5), 30.0],
		["tommy", Vector3(0, 0, 0), 10.0],
	]
	for e in scene:
		var n := Content.instance_model(e[0], Vector3(0.6, 0.8, 0.6), Color(0.9, 0.7, 0.5))
		n.position = e[1]
		n.rotation_degrees.y = e[2]
		add_child(n)
		var ap: AnimationPlayer = n.find_child("AnimationPlayer", true, false)
		if ap:
			var rig := AnimRig.new(n)
			rig.loop("wave" if e[0] == "tommy" and ap.has_animation("wave") else "idle")
	cam = Camera3D.new()
	cam.fov = 32
	add_child(cam)
	menus = Menus.new()
	add_child(menus)
	menus.show_title()

func _process(dt: float) -> void:
	_t += dt
	var a := sin(_t * 0.08) * 0.35
	cam.position = Vector3(sin(a) * 13.0 - 2.0, 6.5, cos(a) * 13.0 + 1.0)
	cam.look_at(Vector3(-2.5, 1.2, -2), Vector3.UP)
