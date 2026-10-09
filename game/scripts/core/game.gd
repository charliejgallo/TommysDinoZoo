extends Node
## Game-wide state: settings, the day clock, coins and save slots.
## The world (scripts/world/world.gd) owns the things in it and hands
## Game a dictionary to save via `world_state` callbacks.

signal coins_changed(coins: int)
signal hour_changed(hour: float)
signal dusk()          # three quarters of the day: "it's getting dark"
signal day_ended()     # time's up: Tommy goes to sleep
signal day_started(day: int)

const SAVE_VERSION := 1
const DAY_START := 6.0
const DAY_END := 22.0
const DUSK_HOUR := 18.0
const DAY_CHOICES := [15, 20, 30, 45, 60, 90]

var settings := {
	"day_minutes": 20,
	"locale": "",
	"music": 0.7,
	"sfx": 0.9,
	"guide_arrow": true,
	"fullscreen": false,
	"text_scale": 1.0,
	"camera": 1,          # index into CAMERA_ZOOMS
	"cheap": false,       # "everything costs a tenth": little kids get almost everything
	# parents
	"pin": "",            # 4 digits; "" = no PIN (a grown-up question guards instead)
	"lock_all": false,    # true: the whole Settings menu asks for the PIN
	"session_days": 0,    # game days per session before "time to rest" (0 = no limit)
	# accessibility
	"text_size": 0,       # index into TEXT_SCALES
	"tts": false,         # read prompts, messages and dialogs aloud
	"blur": true,         # the miniature tilt-shift blur
	"autorun": true,      # holding a direction runs after a moment
	"flash": true,        # the camera's white flash
	"rumble": true,       # joypad vibration on happy moments
	# real play time, across all farms (parents' panel)
	"play_date": "",
	"play_today_s": 0.0,
	"play_total_s": 0.0,
}

const TEXT_SCALES := [1.0, 1.15, 1.3]
var session_days := 0      # days finished since the game was opened
var _settings_save_t := 0.0

## Camera distance presets (Settings > Camera): very close .. far
const CAMERA_ZOOMS := [0.58, 0.75, 1.0, 1.3]

var slot := 0
var day := 1
var hour := DAY_START
var coins := 50
var running := false     # the clock runs only while playing
var played_today_s := 0.0  # real seconds played today (parents' panel)
var stats := {}          # counters for the day summary and trophies
var today := {}          # counters for this day only
var flags := {}          # one-off story/unlock flags
var _dusk_sent := false

var world_save: Callable    # () -> Dictionary
var world_load: Callable    # (Dictionary) -> void

func _ready() -> void:
	process_mode = Node.PROCESS_MODE_PAUSABLE
	load_settings()
	ThemeDB.fallback_font = UiTheme._font()
	get_tree().root.theme = UiTheme.get_theme()

func _process(dt: float) -> void:
	if not running:
		return
	played_today_s += dt
	_count_real_time(dt)
	var rate := (DAY_END - DAY_START) / (float(settings.day_minutes) * 60.0)
	if Dev.arg("fast") != "":
		rate *= float(Dev.arg("fast"))
	var prev := hour
	hour = min(hour + rate * dt, DAY_END)
	if int(prev * 4) != int(hour * 4):
		hour_changed.emit(hour)
	if not _dusk_sent and hour >= DUSK_HOUR:
		_dusk_sent = true
		dusk.emit()
	if hour >= DAY_END:
		running = false
		day_ended.emit()

## 0 at sunrise .. 1 at bedtime
func day_fraction() -> float:
	return (hour - DAY_START) / (DAY_END - DAY_START)

func clock_text() -> String:
	var h := int(hour)
	var m := int((hour - h) * 60.0) / 10 * 10
	return "%d:%02d" % [h, m]

func add_coins(n: int, why := "") -> void:
	coins = max(coins + n, 0)
	if n > 0:
		count("coins_earned", n)
	coins_changed.emit(coins)

## What something listed at `base` coins costs now (Settings: cheap mode
## divides every price by ten, never below one coin).
func price(base: int) -> int:
	if base <= 0:
		return base
	return maxi(1, int(ceil(base / 10.0))) if settings.get("cheap", false) else base

func can_pay(n: int) -> bool:
	return coins >= n

func count(key: String, n := 1) -> void:
	stats[key] = stats.get(key, 0) + n
	today[key] = today.get(key, 0) + n

func start_new_day() -> void:
	session_days += 1
	day += 1
	hour = DAY_START
	today = {}
	played_today_s = 0.0
	_dusk_sent = false
	running = true
	day_started.emit(day)

# ---------------------------------------------------------------- settings

## Real minutes played per calendar day and in total (all farms), for the
## parents' panel. Saved every half minute.
func _count_real_time(dt: float) -> void:
	var today_s := Time.get_date_string_from_system()
	if settings.play_date != today_s:
		settings.play_date = today_s
		settings.play_today_s = 0.0
	settings.play_today_s = float(settings.play_today_s) + dt
	settings.play_total_s = float(settings.play_total_s) + dt
	_settings_save_t += dt
	if _settings_save_t > 30.0:
		_settings_save_t = 0.0
		save_settings()

func minutes_today() -> int:
	if settings.play_date != Time.get_date_string_from_system():
		return 0
	return int(float(settings.play_today_s) / 60.0)

## Say something with the system's voice (Settings: read aloud).
func speak(text: String, interrupt := true) -> void:
	if not settings.get("tts", false) or text.strip_edges() == "":
		return
	var lang := TranslationServer.get_locale().substr(0, 2)
	var voices := DisplayServer.tts_get_voices_for_language(lang)
	if voices.is_empty():
		return
	DisplayServer.tts_speak(text, voices[0], 70, 1.0, 1.0, 0, interrupt)

## A short joypad buzz for happy moments.
func rumble(strength := 0.4, seconds := 0.15) -> void:
	if settings.get("rumble", true):
		for j in Input.get_connected_joypads():
			Input.start_joy_vibration(j, strength * 0.6, strength, seconds)

func load_settings() -> void:
	var f := FileAccess.open(data_dir().path_join("settings.json"), FileAccess.READ)
	if f:
		var d = JSON.parse_string(f.get_as_text())
		if typeof(d) == TYPE_DICTIONARY:
			settings.merge(d, true)
	if Dev.arg("day") != "":
		settings.day_minutes = int(Dev.arg("day"))

func save_settings() -> void:
	DirAccess.make_dir_recursive_absolute(data_dir())
	var f := FileAccess.open(data_dir().path_join("settings.json"), FileAccess.WRITE)
	f.store_string(JSON.stringify(settings, "  "))

func apply_settings() -> void:
	var loc: String = settings.locale
	if Dev.arg("lang") != "":
		loc = Dev.arg("lang")
	if loc == "":
		loc = Lang.best_default()
	Lang.set_language(loc)
	DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_FULLSCREEN if settings.fullscreen else DisplayServer.WINDOW_MODE_WINDOWED)
	get_tree().root.content_scale_factor = TEXT_SCALES[clampi(int(settings.get("text_size", 0)), 0, TEXT_SCALES.size() - 1)]
	var bus := AudioServer.get_bus_index("Music")
	if bus >= 0:
		AudioServer.set_bus_volume_db(bus, linear_to_db(settings.music))
	bus = AudioServer.get_bus_index("SFX")
	if bus >= 0:
		AudioServer.set_bus_volume_db(bus, linear_to_db(settings.sfx))

# ---------------------------------------------------------------- saves

func data_dir() -> String:
	return "user://dev" if Dev.is_dev() else "user://"

func slot_path(n: int) -> String:
	return data_dir().path_join("saves/slot_%d.json" % n)

func slot_info(n: int) -> Dictionary:
	var f := FileAccess.open(slot_path(n), FileAccess.READ)
	if f == null:
		return {}
	var d = JSON.parse_string(f.get_as_text())
	if typeof(d) != TYPE_DICTIONARY:
		return {}
	return {"day": d.get("day", 1), "coins": d.get("coins", 0), "name": d.get("farm_name", ""),
		"dinos": d.get("world", {}).get("dinos", []).size()}

func save_game() -> void:
	DirAccess.make_dir_recursive_absolute(data_dir().path_join("saves"))
	var d := {
		"version": SAVE_VERSION, "day": day, "hour": hour, "coins": coins,
		"stats": stats, "flags": flags, "farm_name": flags.get("farm_name", ""),
		"world": world_save.call() if world_save.is_valid() else {},
		"missions": Missions.save(),
	}
	var tmp := slot_path(slot) + ".tmp"
	var f := FileAccess.open(tmp, FileAccess.WRITE)
	f.store_string(JSON.stringify(d))
	f.close()
	DirAccess.rename_absolute(tmp, slot_path(slot))

func load_game(n: int) -> bool:
	slot = n
	var f := FileAccess.open(slot_path(n), FileAccess.READ)
	if f == null:
		new_game(n)
		return false
	var d = JSON.parse_string(f.get_as_text())
	if typeof(d) != TYPE_DICTIONARY:
		new_game(n)
		return false
	day = int(d.get("day", 1))
	hour = DAY_START   # every session starts in the morning
	coins = int(d.get("coins", 0))
	stats = d.get("stats", {})
	flags = d.get("flags", {})
	today = {}
	_dusk_sent = false
	Missions.load_from(d.get("missions", {}))
	if world_load.is_valid():
		world_load.call(d.get("world", {}))
	return true

func new_game(n: int) -> void:
	slot = n
	day = 1
	hour = DAY_START
	coins = 50
	stats = {}
	flags = {}
	today = {}
	_dusk_sent = false
	Missions.load_from({})
	if world_load.is_valid():
		world_load.call({})
