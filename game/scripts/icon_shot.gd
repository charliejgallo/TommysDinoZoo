extends Node3D
## Dev: the app icon picture (Tommy hugging-distance from a baby trike on a
## soft sky). godot --path game --resolution 1024x1024 -- --scene=res://scenes/icon_shot.tscn --shot=x.png

func _ready() -> void:
	var st := Stage.make_env(self)
	st.world_env.camera_attributes = null
	var g := MeshInstance3D.new()
	var pm := PlaneMesh.new()
	pm.size = Vector2(40, 40)
	g.mesh = pm
	var gm := ShaderMaterial.new()
	gm.shader = Look.TOON
	gm.set_shader_parameter("albedo", Color("#8fd46a"))
	gm.set_shader_parameter("rim_dark", 0.0)
	g.material_override = gm
	add_child(g)
	var t := Content.instance_model("tommy")
	t.position = Vector3(-0.38, 0, 0)
	t.rotation_degrees.y = 20
	add_child(t)
	var head := AnimRig.attach(t, "head")
	if head:
		head.add_child(Content.instance_model("cap_basic"))
	var d := Content.instance_model("trike_baby")
	d.position = Vector3(0.42, 0, 0.1)
	d.rotation_degrees.y = -40
	add_child(d)
	for n in [t, d]:
		var ap: AnimationPlayer = n.find_child("AnimationPlayer", true, false)
		if ap:
			ap.play("idle" if n == d else "wave")
			ap.seek(0.3 if n == d else 0.45, true)
			ap.pause()
	var cam := Camera3D.new()
	cam.fov = 30
	add_child(cam)
	cam.position = Vector3(0.0, 1.9, 2.5)
	cam.look_at(Vector3(0.02, 0.42, 0), Vector3.UP)
	cam.make_current()
