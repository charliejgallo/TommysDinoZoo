class_name SaleSign
extends Node3D
## The "for sale" sign at the gate of a closed habitat: A shows its price
## and opens it when there are enough coins.

var zone := ""
var price := 0

func setup(z: String, pos: Vector3) -> void:
	zone = z
	price = int(Content.habitats.get(z, {}).get("price", 0))
	position = pos

func _ready() -> void:
	add_to_group("interact")
	var m := Content.instance_model("prop_sign", Vector3(0.6, 0.9, 0.1), Color(0.9, 0.75, 0.5))
	add_child(m)
	var l := Label3D.new()
	l.text = "%s\n%d" % [tr("habitat." + zone), price]
	l.font = UiTheme.get_theme().default_font
	l.font_size = 44
	l.outline_size = 10
	l.pixel_size = 0.005
	l.position = Vector3(0, 1.55, 0)
	l.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	l.modulate = Color("#7a5236")
	l.outline_modulate = Color("#fff7e6")
	add_child(l)

func interact_point() -> Vector3:
	return global_position + Vector3(0, 0.5, 0)

func interact_info(_p: Player) -> Dictionary:
	return {"verb": "buy_land", "icon": "shop", "priority": 2}

func interact(_p: Player, _info: Dictionary) -> void:
	var w := get_tree().get_first_node_in_group("world")
	w.menus.show_confirm(tr("land.ask") % [tr("habitat." + zone), price], func():
		if not Game.can_pay(price):
			Sfx.play("nope")
			w.toast(tr("toast.no_coins"), "coin")
			return
		Game.add_coins(-price)
		w.open_zone(zone))
