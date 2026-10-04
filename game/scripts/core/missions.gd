extends Node
## Daily missions: three short, clear tasks a day picked from templates that
## fit what the farm has. Progress is counted from Game.stats since the
## mission was given, so any action anywhere counts. Claimed at the board.

const TEMPLATES := [
	# key counted in Game.stats, amount range, reward, needs
	{"id": "pet",     "key": "pets",      "n": [3, 6], "coins": 15},
	{"id": "feed",    "key": "fed",       "n": [2, 4], "coins": 20},
	{"id": "scoop",   "key": "poops",     "n": [1, 3], "coins": 20, "needs_item": "shovel"},
	{"id": "brush",   "key": "brushed",   "n": [1, 2], "coins": 20, "needs_item": "brush"},
	{"id": "harvest", "key": "harvested", "n": [2, 4], "coins": 15},
	{"id": "plant",   "key": "planted",   "n": [1, 2], "coins": 20},
	{"id": "fill",    "key": "filled",    "n": [1, 2], "coins": 15},
	{"id": "play",    "key": "played",    "n": [1, 3], "coins": 20, "needs_item": "ball"},
	{"id": "feed_dino", "key": "fed_%s",  "n": [1, 3], "coins": 25, "per_dino": true},
	{"id": "pet_dino",  "key": "pet_%s",  "n": [2, 4], "coins": 20, "per_dino": true},
]

var today := []      # [{id, key, n, start, coins, done, claimed, dino}]
var day := -1

func ensure_day(species_present: Array, owned_items: Array) -> void:
	if day == Game.day and not today.is_empty():
		return
	day = Game.day
	today = []
	var pool := TEMPLATES.duplicate()
	pool.shuffle()
	var rng := RandomNumberGenerator.new()
	rng.seed = hash([Game.slot, Game.day])
	for t in pool:
		if today.size() >= 3:
			break
		if t.has("needs_item") and not (t.needs_item in owned_items):
			continue
		var key: String = t.key
		var dino := ""
		if t.get("per_dino", false):
			if species_present.is_empty():
				continue
			dino = species_present[rng.randi() % species_present.size()]
			key = key % dino
		var n := rng.randi_range(t.n[0], t.n[1])
		today.append({"id": t.id, "key": key, "n": n, "start": int(Game.stats.get(key, 0)),
			"coins": t.coins + (n - t.n[0]) * 5, "claimed": false, "dino": dino})

func progress(m: Dictionary) -> int:
	return min(int(Game.stats.get(m.key, 0)) - int(m.start), int(m.n))

func is_done(m: Dictionary) -> bool:
	return progress(m) >= int(m.n)

func text(m: Dictionary) -> String:
	var t := tr("mission." + m.id)
	if m.dino != "":
		return t % [m.n, Content.dino_name(m.dino)]
	return t % m.n

func claim(i: int) -> int:
	var m: Dictionary = today[i]
	if m.claimed or not is_done(m):
		return 0
	m.claimed = true
	Game.add_coins(int(m.coins))
	Game.count("missions_done")
	return int(m.coins)

func pending_claims() -> int:
	var n := 0
	for m in today:
		if not m.claimed and is_done(m):
			n += 1
	return n

func save() -> Dictionary:
	return {"day": day, "today": today}

func load_from(d: Dictionary) -> void:
	day = int(d.get("day", -1))
	today = d.get("today", [])
