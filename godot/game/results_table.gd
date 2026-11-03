class_name ResultsTable
extends PanelContainer
## Таблица результатов в игре: кольца (Paths: leaders_rings.json, 10 лучших, поля как в первой
## версии симулятора) и осмотр судна (wreck_results.csv). Тот же вид в главном меню и на финише.
## Результаты отдельно по режиму управления (Settings.MODES); у осмотра судна — только по правилам версии 1.1
## (строки с режимом), старые строки (правила 3 м / 35° / 1,5 с) в таблицу не попадают.

const RING_COLS := [["№", 3], ["имя", 14], ["итог", 7], ["время", 7], ["штраф", 6], ["пропущ.", 8], ["не по пор.", 10],
		["касан.", 8], ["дата", 16]]
const WRECK_COLS := [["№", 3], ["имя", 14], ["время, с", 9], ["точек", 6], ["касаний", 8], ["дата", 16]]

var title: Label
var grid: GridContainer
var foot: Label
var plain := false              # вид страницы главного меню (без рамки, IBM Plex Mono, цвета MenuKit)


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


static func load_rings(dir := "", mode := "science") -> Array:
	var path := (dir if dir != "" else Paths.root()).path_join("leaders_rings.json")
	if not FileAccess.file_exists(path):
		return []
	var parsed = JSON.parse_string(FileAccess.get_file_as_string(path))
	if not parsed is Array:
		return []
	return (parsed as Array).filter(func(r): return r.get("mode", "science") == mode).slice(0, 10)


## Осмотр судна: строки CSV, лучшие по времени (только завершённые осмотры).
static func load_wreck(dir := "", mode := "science") -> Array:
	var path := (dir if dir != "" else Paths.root()).path_join("wreck_results.csv")
	var out := []
	if not FileAccess.file_exists(path):
		return out
	var f := FileAccess.open(path, FileAccess.READ)
	f.get_csv_line(";")
	while not f.eof_reached():
		var r := f.get_csv_line(";")
		if r.size() >= 6 and r[5] == mode:
			out.append({"name": r[0], "time": float(r[1]), "points": int(r[2]), "touches": int(r[3]), "date": r[4]})
	out.sort_custom(func(a, b): return a["time"] < b["time"])
	return out.slice(0, 10)


## Строка в CSV осмотра судна (как rings_results.csv колец).
static func save_wreck(res: Dictionary, dir := "") -> void:
	var csv := (dir if dir != "" else Paths.root()).path_join("wreck_results.csv")
	var new_file := not FileAccess.file_exists(csv)
	var c := FileAccess.open(csv, FileAccess.READ_WRITE if not new_file else FileAccess.WRITE)
	c.seek_end()
	if new_file:
		c.store_line("name;time;points;touches;date;mode")
	c.store_line("%s;%.1f;%d;%d;%s;%s" % [res["name"], res["time"], res["points"], res["touches"], res["date"],
			res.get("mode", "science")])
	c.close()


## Вид главного меню: без рамки и фона, моноширинный IBM Plex Mono, цвета MenuKit.
func set_plain() -> void:
	plain = true
	add_theme_stylebox_override("panel", StyleBoxEmpty.new())
	title.add_theme_color_override("font_color", MenuKit.MUTED)
	title.add_theme_font_override("font", MenuKit.vf(MenuKit.F_MONO))
	title.add_theme_font_size_override("font_size", 13)
	foot.add_theme_color_override("font_color", MenuKit.MUTED)
	foot.add_theme_font_override("font", MenuKit.vf(MenuKit.F_MONO))
	foot.add_theme_font_size_override("font_size", 12)
	grid.add_theme_constant_override("h_separation", 22)
	grid.add_theme_constant_override("v_separation", 8)


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
		_cell(String(c[0]), MenuKit.MUTED if plain else Color(Hud.WHITE, 0.6))
	if cells.is_empty():
		_cell("—", Hud.WHITE)
		_cell("пока нет результатов", Hud.WHITE)
		for i in cols.size() - 2:
			_cell("", Hud.WHITE)
	for i in cells.size():
		var mine: bool = not highlight.is_empty() and rows[i].get("date") == highlight.get("date") \
				and rows[i].get("name") == highlight.get("name")
		var col := (MenuKit.AMBER if mine else MenuKit.TEXT) if plain else (Hud.AMBER if mine else Hud.WHITE)
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
	if plain:
		l.add_theme_font_override("font", MenuKit.vf(MenuKit.F_MONO))
	grid.add_child(l)
