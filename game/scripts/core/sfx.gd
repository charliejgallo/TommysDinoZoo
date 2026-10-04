extends Node
## Sound effects by name: res://assets/sfx/<name>.ogg|.wav. Missing sounds
## are silently skipped so the game runs before audio exists. A small pool
## of players lets effects overlap.

var _cache := {}
var _pool: Array[AudioStreamPlayer] = []
var _next := 0

func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	for i in 8:
		var p := AudioStreamPlayer.new()
		p.bus = "SFX" if AudioServer.get_bus_index("SFX") >= 0 else "Master"
		add_child(p)
		_pool.append(p)

func _stream(name: String) -> AudioStream:
	if _cache.has(name):
		return _cache[name]
	var s: AudioStream = null
	for ext in ["ogg", "wav"]:
		var p := "res://assets/sfx/%s.%s" % [name, ext]
		if ResourceLoader.exists(p):
			s = load(p)
			break
	_cache[name] = s
	return s

func play(name: String, pitch_jitter := 0.08, volume_db := 0.0) -> void:
	var s := _stream(name)
	if s == null:
		return
	var p := _pool[_next]
	_next = (_next + 1) % _pool.size()
	p.stream = s
	p.pitch_scale = 1.0 + randf_range(-pitch_jitter, pitch_jitter)
	p.volume_db = volume_db
	p.play()
