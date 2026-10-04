extends Node
## Background music by name: res://assets/music/<name>.ogg. play() crossfades
## (~2 s) between two players on the "Music" bus (Master if it is missing).
## Missing files are silently skipped so the game runs without them.
## Every track loops seamlessly except the ones in NO_LOOP.

const DIR := "res://assets/music/"
const FADE := 2.0
const NO_LOOP := ["summary"]

var current := ""
var _players: Array[AudioStreamPlayer] = []
var _gain: Array[float] = [0.0, 0.0]
var _tweens: Array[Tween] = [null, null]
var _active := 0
var _cache := {}

func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	var bus := "Music" if AudioServer.get_bus_index("Music") >= 0 else "Master"
	for i in 2:
		var p := AudioStreamPlayer.new()
		p.bus = bus
		p.volume_db = -80.0
		add_child(p)
		_players.append(p)

func _stream(name: String) -> AudioStream:
	if _cache.has(name):
		return _cache[name]
	var s: AudioStream = null
	var path := DIR + name + ".ogg"
	if ResourceLoader.exists(path):
		s = load(path)
		if s is AudioStreamOggVorbis:
			(s as AudioStreamOggVorbis).loop = not NO_LOOP.has(name)
	_cache[name] = s
	return s

## Crossfade to the named track. Same track again = nothing; missing = nothing.
func play(name: String, fade := FADE) -> void:
	if name == current and _players[_active].playing:
		return
	var s := _stream(name)
	if s == null:
		return
	current = name
	var old := _active
	_active = 1 - _active
	var p := _players[_active]
	p.stream = s
	_set_gain(0.0, _active)
	p.play()
	_fade(_active, 1.0, fade)
	_fade(old, 0.0, fade)

## Fade everything out and stop.
func stop(fade := FADE) -> void:
	current = ""
	for i in 2:
		_fade(i, 0.0, fade)

func _fade(i: int, to: float, time: float) -> void:
	if _tweens[i]:
		_tweens[i].kill()
	var p := _players[i]
	if not p.playing:
		_set_gain(to, i)
		return
	if time <= 0.0:
		_set_gain(to, i)
		if to <= 0.0:
			p.stop()
		return
	var t := create_tween()
	t.tween_method(_set_gain.bind(i), _gain[i], to, time * absf(to - _gain[i]) + 0.01)
	if to <= 0.0:
		t.tween_callback(p.stop)
	_tweens[i] = t

func _set_gain(g: float, i: int) -> void:
	_gain[i] = g
	# equal-power curve: the two players sum to a steady level mid-fade
	_players[i].volume_db = linear_to_db(maxf(sin(g * PI * 0.5), 0.0001))
