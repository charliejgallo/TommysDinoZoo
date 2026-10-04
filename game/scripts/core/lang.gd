extends Node
## Language packs: every content pack has `lang/<locale>.po`; extra packs can
## be dropped in `user://lang/<locale>.po` (or `user://lang/<pack>/...`).
## A new language = new .po files; the settings menu lists whatever exists.
## The tiny PO reader handles msgid/msgstr with continuation lines and the
## header field "X-Language-Name" (shown in the menu).

var languages := {}   # locale -> display name
var _translations := {}  # locale -> Translation

func load_dirs(dirs: Array) -> void:
	for d in dirs:
		_scan(d)
	for loc in _translations:
		TranslationServer.add_translation(_translations[loc])

func _scan(dir: String) -> void:
	var da := DirAccess.open(dir)
	if da == null:
		return
	for f in da.get_files():
		if f.ends_with(".po"):
			_read_po(dir.path_join(f), f.get_basename())
	for sub in da.get_directories():
		_scan(dir.path_join(sub))

func _read_po(path: String, locale: String) -> void:
	var fa := FileAccess.open(path, FileAccess.READ)
	if fa == null:
		return
	var tr: Translation = _translations.get(locale)
	if tr == null:
		tr = Translation.new()
		tr.locale = locale
		_translations[locale] = tr
	var cur := ""
	var id := ""
	var str := ""
	var entries := []
	while not fa.eof_reached():
		var line := fa.get_line().strip_edges()
		if line.begins_with("msgid "):
			if cur == "str":
				entries.append([id, str])
			id = _unq(line.substr(6))
			str = ""
			cur = "id"
		elif line.begins_with("msgstr "):
			str = _unq(line.substr(7))
			cur = "str"
		elif line.begins_with("\""):
			if cur == "id":
				id += _unq(line)
			elif cur == "str":
				str += _unq(line)
	if cur == "str":
		entries.append([id, str])
	for e in entries:
		if e[0] == "":
			for h in e[1].split("\n"):
				if h.begins_with("X-Language-Name:"):
					languages[locale] = h.substr(16).strip_edges()
		elif e[1] != "":
			tr.add_message(e[0], e[1])
	if not languages.has(locale):
		languages[locale] = locale

func _unq(s: String) -> String:
	s = s.strip_edges()
	if s.begins_with("\"") and s.ends_with("\""):
		s = s.substr(1, s.length() - 2)
	return s.c_unescape()

func set_language(locale: String) -> void:
	TranslationServer.set_locale(locale)

func best_default() -> String:
	var sys := OS.get_locale_language()
	return sys if languages.has(sys) else ("en" if languages.has("en") else "es")
