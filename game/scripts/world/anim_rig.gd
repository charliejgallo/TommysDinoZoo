class_name AnimRig
extends RefCounted
## Wraps an imported model's AnimationPlayer: loops the looping clips,
## cross-fades, plays one-shots and falls back gracefully when a clip is
## missing (placeholders have none).

const LOOPS := ["idle", "walk", "run", "carry_idle", "carry_walk", "sleep", "sit", "talk", "sad"]

var ap: AnimationPlayer
var current := ""
var _one_shot_until := 0.0
var _after := ""

func _init(model: Node) -> void:
	ap = model.find_child("AnimationPlayer", true, false) if model else null
	if ap:
		for n in ap.get_animation_list():
			if n in LOOPS:
				ap.get_animation(n).loop_mode = Animation.LOOP_LINEAR

func has(name: String) -> bool:
	return ap != null and ap.has_animation(name)

## Loop `name` (no-op if already playing). Ignored while a one-shot runs.
func loop(name: String, speed := 1.0, blend := 0.18) -> void:
	if ap == null or busy():
		return
	if not ap.has_animation(name):
		name = "idle" if ap.has_animation("idle") else ""
		if name == "":
			return
	if current != name:
		ap.play(name, blend, speed)
		current = name
	else:
		ap.speed_scale = speed

## Play a one-shot; returns its length in seconds (0.6 when missing, so
## callers can still time their logic).
func once(name: String, then := "idle", speed := 1.0) -> float:
	if ap == null or not ap.has_animation(name):
		return 0.6
	ap.play(name, 0.12, speed)
	ap.speed_scale = speed
	current = name
	var length := ap.get_animation(name).length / speed
	_one_shot_until = Time.get_ticks_msec() / 1000.0 + length - 0.12
	_after = then
	return length

func busy() -> bool:
	return Time.get_ticks_msec() / 1000.0 < _one_shot_until

func tick() -> void:
	if ap and _after != "" and not busy():
		var a := _after
		_after = ""
		current = ""
		loop(a)

## Find a bone attachment point (BoneAttachment3D) on the model's skeleton.
static func attach(model: Node, bone: String) -> Node3D:
	if model == null:
		return null
	var sk: Skeleton3D = model.find_child("*", true, false) as Skeleton3D
	for n in model.find_children("*", "Skeleton3D", true, false):
		sk = n
		break
	if sk == null or sk.find_bone(bone) < 0:
		return null
	var ba := BoneAttachment3D.new()
	ba.bone_name = bone
	sk.add_child(ba)
	return ba
