class_name ResultsTable
extends PanelContainer
## Таблица результатов в игре: кольца (user://leaders_rings.json, 10 лучших, поля как в сборке
## преподавателя) и осмотр судна (user://wreck_results.csv). Тот же вид в главном меню и на финише.

const RING_COLS := [["№", 3], ["имя", 14], ["итог", 7], ["время", 7], ["штраф", 6], ["пропущ.", 8], ["не по пор.", 10],
		["касан.", 8], ["дата", 16]]
const WRECK_COLS := [["№", 3], ["имя", 14], ["время, с", 9], ["точек", 6], ["касаний", 8], ["дата", 16]]

var title: Label
var grid: GridContainer
var foot: Label


func _init() -> void:
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.02, 0.03, 0.03, 0.86)
	sb.set_border_width_all(1)
	sb.border_color = Color(Hud.WHITE, 0.4)
	sb.set_content_margin_all(14)
	add_theme_stylebox_override("panel", sb)
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 10)
	add_child(box)
	title = Label.new()
	title.add_theme_color_override("font_color", Hud.AMBER)
	title.add_theme_font_size_override("font_size", 15)
	box.add_child(title)
	grid = GridContainer.new()
	grid.add_theme_constant_override("h_separation", 12)
	grid.add_theme_constant_override("v_separation", 4)
	box.add_child(grid)
	foot = Label.new()
	foot.autowrap_mode = TextServer.AUTOWRAP_ARBITRARY
	foot.custom_minimum_size = Vector2(300, 0)
	foot.add_theme_font_size_override("font_size", 13)
	foot.add_theme_color_override("font_color", Color(Hud.WHITE, 0.7))
	box.add_child(foot)


static func load_rings(dir := "user://") -> Array:
	var path := dir.path_join("leaders_rings.json")
	if not FileAccess.file_exists(path):
		return []
	var parsed = JSON.parse_string(FileAccess.get_file_as_string(path))
	return parsed.slice(0, 10) if parsed is Array else []


## Осмотр судна: строки CSV, лучшие по времени (только завершённые осмотры).
static func load_wreck(dir := "user://") -> Array:
	var path := dir.path_join("wreck_results.csv")
	var out := []
	if not FileAccess.file_exists(path):
		return out
	var f := FileAccess.open(path, FileAccess.READ)
	f.get_csv_line(";")
	while not f.eof_reached():
		var r := f.get_csv_line(";")
		if r.size() >= 5:
			out.append({"name": r[0], "time": float(r[1]), "points": int(r[2]), "touches": int(r[3]), "date": r[4]})
	out.sort_custom(func(a, b): return a["time"] < b["time"])
	return out.slice(0, 10)


## Строка в CSV осмотра судна (как rings_results.csv колец).
static func save_wreck(res: Dictionary, dir := "user://") -> void:
	var csv := dir.path_join("wreck_results.csv")
	var new_file := not FileAccess.file_exists(csv)
	var c := FileAccess.open(csv, FileAccess.READ_WRITE if not new_file else FileAccess.WRITE)
	c.seek_end()
	if new_file:
		c.store_line("name;time;points;touches;date")
	c.store_line("%s;%.1f;%d;%d;%s" % [res["name"], res["time"], res["points"], res["touches"], res["date"]])
	c.close()


func show_rings(rows: Array, highlight: Dictionary = {}, footer := "") -> void:
	title.text = "КОЛЬЦА · 10 лучших\nитог = время + штраф: +15 не по порядку, +30 за пропущенное"
	_fill(RING_COLS, rows.map(func(r): return [r["name"], Hud.num(r["total"], 1), Hud.num(r["time"], 1), str(int(r["penalty"])),
			str(int(r["missed"])), str(int(r["out_of_order"])), str(int(r["touches"])), r["date"]]), rows, highlight, footer)


func show_wreck(rows: Array, highlight: Dictionary = {}, footer := "") -> void:
	title.text = "СУДНО · 10 лучших осмотров\nвремя до последней из 6 точек осмотра"
	_fill(WRECK_COLS, rows.map(func(r): return [r["name"], Hud.num(r["time"], 1), str(r["points"]), str(r["touches"]), r["date"]]),
			rows, highlight, footer)


func _fill(cols: Array, cells: Array, rows: Array, highlight: Dictionary, footer: String) -> void:
	for c in grid.get_children():
		c.queue_free()
	grid.columns = cols.size()
	for c in cols:
		_cell(String(c[0]), Color(Hud.WHITE, 0.6))
	if cells.is_empty():
		_cell("—", Hud.WHITE)
		_cell("пока нет результатов", Hud.WHITE)
		for i in cols.size() - 2:
			_cell("", Hud.WHITE)
	for i in cells.size():
		var mine: bool = not highlight.is_empty() and rows[i].get("date") == highlight.get("date") \
				and rows[i].get("name") == highlight.get("name")
		var col := Hud.AMBER if mine else Hud.WHITE
		_cell(str(i + 1), col)
		for v in cells[i]:
			_cell(String(v), col)
	foot.text = footer
	foot.visible = footer != ""


func _cell(t: String, col: Color) -> void:
	var l := Label.new()
	l.text = t
	l.add_theme_font_size_override("font_size", 15)
	l.add_theme_color_override("font_color", col)
	grid.add_child(l)
