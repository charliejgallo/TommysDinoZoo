extends Node3D
## Model viewer for art checks under the game's light and camera.
##   godot --path game -- --scene=res://scenes/viewer.tscn \
##       --models=tommy,trike_adult --anim=walk --t=0.4 --yaw=0 \
##       [--cam=game|close|wide] [--grid] [--attach=cap_basic@head,...] --shot=out.png
##       [--pos=x:z[:yaw[:y]]/...] [--step=S --cols=N] [--dist=F] [--tx= --ty= --tz=] [--nodof]
## Model names resolve to res://assets/models/<name>.glb. Models stand in a
## row along X, spaced by their size. --anim falls back to the first
## animation when a model lacks it; --t freezes the animation at that time
## (seconds), omit it to let it play. --attach=<model>@<bone> parents
## res://assets/models/<model>.glb to that bone (identity offset) on every
## model that has the bone (caps on `head`, back items on `chest`...).

func _ready() -> void:
	var env := Stage.make_env(self)
	if Dev.arg("nodof") != "":   # --nodof: no tilt-shift blur (sharp close-ups)
		env.world_env.camera_attributes = null
	var ground := MeshInstance3D.new()
	var pm := PlaneMesh.new()
	pm.size = Vector2(60, 60)
	ground.mesh = pm
	var gm := ShaderMaterial.new()
	gm.shader = Look.TOON
	gm.set_shader_parameter("albedo", Color(0.49, 0.78, 0.38))
	gm.set_shader_parameter("rim_dark", 0.0)
	ground.material_override = gm
	add_child(ground)
	if Dev.arg("grid") != "":
		for i in range(-10, 11):
			for axis in 2:
				var b := MeshInstance3D.new()
				var bm := BoxMesh.new()
				bm.size = Vector3(0.02, 0.005, 20) if axis == 0 else Vector3(20, 0.005, 0.02)
				b.mesh = bm
				b.position = Vector3(i, 0.003, 0) if axis == 0 else Vector3(0, 0.003, i)
				add_child(b)
	var names := Dev.arg("models", "test_blob").split(",")
	var anim := Dev.arg("anim", "idle")
	var t := Dev.arg("t", "")
	var yaw := float(Dev.arg("yaw", "0"))
	var x := 0.0
	var spans := []
	var nodes := []
	for nm in names:
		var path := nm if nm.begins_with("res://") else "res://assets/models/%s.glb" % nm
		var ps: PackedScene = load(path)
		if ps == null:
			push_error("viewer: cannot load " + path)
			continue
		var inst := ps.instantiate() as Node3D
		add_child(inst)
		_attach(inst, Dev.arg("attach"))
		Look.apply(inst)
		inst.rotation_degrees.y = yaw
		var ap: AnimationPlayer = inst.find_child("AnimationPlayer", true, false)
		if ap and ap.get_animation_list().size() > 0:
			var a := anim if ap.has_animation(anim) else ap.get_animation_list()[0]
			ap.get_animation(a).loop_mode = Animation.LOOP_LINEAR
			ap.play(a)
			if t != "":
				ap.seek(float(t), true)
				ap.pause()
		var w := _width(inst)
		spans.append(w)
		nodes.append(inst)
	var gap := 0.4
	var total := 0.0
	for w in spans:
		total += w
	total += gap * max(spans.size() - 1, 0)
	x = -total / 2.0
	for i in nodes.size():
		nodes[i].position.x = x + spans[i] / 2.0
		x += spans[i] + gap
	# Optional fixed placement, to check props on the 1 m grid:
	#   --pos=x:z[:yaw[:y]]/...        one entry per model (metres, degrees)
	#   --step=S [--cols=N]            fixed pitch S, N per row (rows go back)
	var pos := Dev.arg("pos", "")
	var step := float(Dev.arg("step", "0"))
	if pos != "":
		var ps := pos.split("/")
		for i in min(ps.size(), nodes.size()):
			var f := ps[i].split(":")
			nodes[i].position = Vector3(float(f[0]), 0, float(f[1]))
			if f.size() > 2:
				nodes[i].rotation_degrees.y = float(f[2])
			if f.size() > 3:   # optional height (held items hang from their grip)
				nodes[i].position.y = float(f[3])
	elif step > 0.0:
		var cols := int(Dev.arg("cols", str(nodes.size())))
		var rows := int(ceil(nodes.size() / float(cols)))
		for i in nodes.size():
			nodes[i].position = Vector3((i % cols - floor((cols - 1) / 2.0)) * step, 0,
				(i / cols - floor((rows - 1) / 2.0)) * step)
		total = cols * step
	var cam := Camera3D.new()
	add_child(cam)
	var mode := Dev.arg("cam", "game")
	# --tx/--ty/--tz move the look-at target (default 0, 0.5, 0)
	var target := Vector3(float(Dev.arg("tx", "0")), float(Dev.arg("ty", "0.5")), float(Dev.arg("tz", "0")))
	Stage.place_camera(cam, target)
	if mode == "close":
		cam.global_position = target + Stage.cam_offset() * 0.45
	elif mode == "wide":
		cam.global_position = target + Stage.cam_offset() * max(1.0, total / 6.0)
	elif mode == "front":
		cam.global_position = target + Vector3(0, 0.6, 1).normalized() * max(4.0, total * 1.4)
	# --dist=F scales the camera distance (e.g. 0.15 for held items)
	cam.global_position = target + (cam.global_position - target) * float(Dev.arg("dist", "1"))
	cam.look_at(target, Vector3.UP)
	cam.make_current()

func _width(n: Node3D) -> float:
	var aabb := AABB()
	var first := true
	for mi in n.find_children("*", "MeshInstance3D", true, false):
		var b: AABB = mi.global_transform * mi.get_aabb()
		aabb = b if first else aabb.merge(b)
		first = false
	return max(aabb.size.x, 0.5)

func _attach(inst: Node, spec: String) -> void:
	if spec == "":
		return
	var sk: Skeleton3D = null
	for n in inst.find_children("*", "Skeleton3D", true, false):
		sk = n
		break
	if sk == null:
		return
	for item in spec.split(","):
		var parts := item.split("@")
		if parts.size() != 2 or sk.find_bone(parts[1]) < 0:
			continue
		var ps: PackedScene = load("res://assets/models/%s.glb" % parts[0])
		if ps == null:
			push_error("viewer: cannot load attach " + parts[0])
			continue
		var ba := BoneAttachment3D.new()
		ba.bone_name = parts[1]
		sk.add_child(ba)
		ba.add_child(ps.instantiate())
