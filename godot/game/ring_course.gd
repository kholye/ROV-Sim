class_name RingCourse
extends RefCounted
## Правила колец как в первой версии симулятора (сборка преподавателя). Только данные и логика, без узлов: проверяется без окна (tests/game_tests.gd).
## Координаты NED (x север = вдоль бассейна, y восток, z глубина), начало в центре бассейна на поверхности.
##
## Проход: центр аппарата сменил сторону плоскости кольца, ближе просвет/2 от оси и в сторону оси кольца.
## Не по порядку: засчитано, +15. Финиш: взятие кольца 6. Каждое не взятое к финишу: +30.
## Касания считаются (пауза 0,4 с), штрафа нет. Итог = секунды + штраф, меньше лучше.

const ORDER_PENALTY := 15
const MISS_PENALTY := 30
# север (z Unity), восток (x Unity), глубина, курс оси (°, + по часовой сверху), просвет — RingCourse.Layout
const LAYOUT := [
	[-8.0, 0.0, 1.2, 0.0, 1.2],
	[-4.0, 1.8, 2.0, 20.0, 1.1],
	[0.0, 0.5, 3.2, -15.0, 1.0],
	[4.0, -2.2, 2.4, -25.0, 0.9],
	[7.5, -0.5, 3.6, 15.0, 0.8],
	[10.5, 1.5, 1.6, 25.0, 0.7],
]
const START := [-11.0, 0.0, 1.0, 0.0]     # север, восток, глубина, курс

enum Phase { WAITING, RUNNING, FINISHED }

var phase := Phase.WAITING
var passed: Array[bool] = []
var ring_touches: Array[int] = []
var last_side: Array[float] = []
var out_of_order := 0
var touches := 0
var start_time := -1.0
var finish_time := -1.0
var last_touch := -10.0
var event := ""
var events: Array[String] = []


static func center(i: int) -> PackedFloat64Array:
	return PackedFloat64Array([LAYOUT[i][0], LAYOUT[i][1], LAYOUT[i][2]])


static func axis(i: int) -> PackedFloat64Array:
	var psi := deg_to_rad(float(LAYOUT[i][3]))
	return PackedFloat64Array([cos(psi), sin(psi), 0.0])


static func side(i: int, pt: PackedFloat64Array) -> float:
	var c := center(i)
	var a := axis(i)
	return (pt[0] - c[0]) * a[0] + (pt[1] - c[1]) * a[1] + (pt[2] - c[2]) * a[2]


func restart(pt: PackedFloat64Array) -> void:
	phase = Phase.WAITING
	passed.clear()
	ring_touches.clear()
	last_side.clear()
	for i in LAYOUT.size():
		passed.append(false)
		ring_touches.append(0)
		last_side.append(side(i, pt))
	out_of_order = 0
	touches = 0
	start_time = -1.0
	finish_time = -1.0
	event = ""
	events.clear()


func begin(pt: PackedFloat64Array, now: float) -> void:
	restart(pt)
	phase = Phase.RUNNING
	start_time = now
	_log("старт")


func next_number() -> int:
	for i in passed.size():
		if not passed[i]:
			return i + 1
	return 0


func tick(pt: PackedFloat64Array, now: float) -> void:
	for i in LAYOUT.size():
		var s := side(i, pt)
		if phase == Phase.RUNNING and signf(s) != signf(last_side[i]) and last_side[i] != 0.0:
			var c := center(i)
			var a := axis(i)
			var r := 0.0
			for k in 3:
				var d := pt[k] - c[k] - a[k] * s
				r += d * d
			r = sqrt(r)
			var clear: float = LAYOUT[i][4]
			if r < clear * 0.5 and s > 0.0:
				_take(i, now)
			elif r < clear * 0.5:
				_log("кольцо %d пройдено в обратную сторону, не засчитано" % (i + 1))
			elif not passed[i] and r < clear * 2.0:
				_log("кольцо %d обойдено, не взято" % (i + 1))
		last_side[i] = s


func _take(i: int, now: float) -> void:
	if passed[i]:
		_log("кольцо %d уже взято" % (i + 1))
		return
	var expected := next_number()
	passed[i] = true
	if i + 1 != expected:
		out_of_order += 1
		_log("кольцо %d взято не по порядку (ждали %d): +%d очков" % [i + 1, expected, ORDER_PENALTY])
	else:
		_log("кольцо %d взято %s" % [i + 1, "с касанием" if ring_touches[i] > 0 else "чисто"])
	if i + 1 == LAYOUT.size():
		finish_time = now
		phase = Phase.FINISHED
		_log("финиш" + (": не взято колец %d, +%d очков" % [missed(), missed() * MISS_PENALTY] if missed() > 0 else ""))


## Касание: ring — номер кольца (1..6) или 0, если касание не кольца.
func contact(ring: int, now: float) -> void:
	if phase != Phase.RUNNING or now - last_touch < 0.4:
		return
	last_touch = now
	touches += 1
	if ring > 0:
		ring_touches[ring - 1] += 1
		_log("касание: кольцо %d" % ring)


func missed() -> int:
	return passed.count(false)


func penalty() -> int:
	return missed() * MISS_PENALTY + out_of_order * ORDER_PENALTY


func elapsed(now: float) -> float:
	if start_time < 0.0:
		return 0.0
	return (finish_time if finish_time >= 0.0 else now) - start_time


func total() -> float:
	return elapsed(finish_time) + penalty()


func result(name: String) -> Dictionary:
	return {"name": name, "total": snappedf(total(), 0.1), "time": snappedf(elapsed(finish_time), 0.1),
			"penalty": penalty(), "missed": missed(), "out_of_order": out_of_order, "touches": touches,
			"date": Time.get_datetime_string_from_system().replace("T", " ").substr(0, 16)}


func _log(s: String) -> void:
	event = s
	events.append(s)


## Таблица лидеров: JSON (поля как leaders_rings.json сборки) + строка в CSV. Возвращает 10 лучших.
static func save_result(res: Dictionary, dir := "user://") -> Array:
	var path := dir.path_join("leaders_rings.json")
	var all: Array = []
	if FileAccess.file_exists(path):
		var parsed = JSON.parse_string(FileAccess.get_file_as_string(path))
		if parsed is Array:
			all = parsed
	all.append(res)
	all.sort_custom(func(a, b): return float(a["total"]) < float(b["total"]))
	var f := FileAccess.open(path, FileAccess.WRITE)
	f.store_string(JSON.stringify(all, "  "))
	f.close()
	var csv := dir.path_join("rings_results.csv")
	var new_file := not FileAccess.file_exists(csv)
	var c := FileAccess.open(csv, FileAccess.READ_WRITE if not new_file else FileAccess.WRITE)
	c.seek_end()
	if new_file:
		c.store_line("name;total;time;penalty;missed;out_of_order;touches;date")
	c.store_line("%s;%.1f;%.1f;%d;%d;%d;%d;%s" % [res["name"], res["total"], res["time"], res["penalty"],
			res["missed"], res["out_of_order"], res["touches"], res["date"]])
	c.close()
	return all.slice(0, 10)
