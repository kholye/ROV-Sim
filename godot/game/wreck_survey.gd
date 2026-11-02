class_name WreckSurvey
extends RefCounted
## Правила осмотра судна (версия 1.1; в первой версии симулятора — 3 м, 35° от оси, 1,5 с): точка осмотрена,
## если она ближе RANGE к камере аппарата, в центральной части кадра (FRAME_FILL ширины и высоты: frame_tan —
## тангенсы половин углов кадра), ничем не заслонена и различима — проверку заслонения и света делает
## вызывающий (visible: в мутной воде нужна доля света от самой поверхности в яркости пикселя не меньше
## порога, см. game/wreck.gd), и так HOLD с подряд. Время идёт после смещения на 0,5 м от старта; финиш,
## когда осмотрены все. Касания считаются без штрафа. Без узлов: проверяется в tests/game_tests.gd.

const RANGE := 2.0
const FRAME_FILL := 0.8
const HOLD := 2.0
const START_MOVE := 0.5

var points: Array = []          # Vector3, мир Godot
var names: Array = []
var done: Array[bool] = []
var done_time: Array[float] = []
var seen_for: Array[float] = []
var start_pos := Vector3.ZERO
var started := false
var start_time := -1.0
var finish_time := -1.0
var touches := 0
var last_touch := -10.0
var just_done := -1             # номер точки, осмотренной на этом шаге (для снимка), иначе −1
var frame_tan := Vector2(tan(deg_to_rad(35.0)), tan(deg_to_rad(35.0)) * 9.0 / 16.0)   # tg половин углов кадра (гор., верт.)
var _last_t := 0.0


func start(pos: Vector3, now: float) -> void:
	start_pos = pos
	started = false
	start_time = -1.0
	finish_time = -1.0
	done.clear()
	done_time.clear()
	seen_for.clear()
	for i in points.size():
		done.append(false)
		done_time.append(-1.0)
		seen_for.append(0.0)
	_last_t = now


## visible: func(cam_pos: Vector3, point: Vector3) -> bool (луч не заслонён).
func tick(cam: Transform3D, now: float, visible: Callable) -> void:
	just_done = -1
	var dt := now - _last_t
	_last_t = now
	if not started:
		if cam.origin.distance_to(start_pos) >= START_MOVE:
			started = true
			start_time = now
		else:
			return
	if finished():
		return
	for i in points.size():
		if done[i]:
			continue
		var v: Vector3 = points[i] - cam.origin
		var ok: bool = v.length() < RANGE and in_frame(cam, points[i]) and visible.call(cam.origin, points[i])
		seen_for[i] = seen_for[i] + dt if ok else 0.0
		if seen_for[i] >= HOLD:
			done[i] = true
			done_time[i] = now - start_time
			just_done = i
	if done.count(false) == 0 and finish_time < 0.0:
		finish_time = now


## Точка в центральной части кадра (FRAME_FILL ширины и высоты) перед камерой.
func in_frame(cam: Transform3D, p: Vector3) -> bool:
	var lc := cam.affine_inverse() * p           # оси камеры: x вправо, y вверх, смотрит в −z
	if lc.z >= -0.05:
		return false
	return absf(lc.x / -lc.z) <= frame_tan.x * FRAME_FILL and absf(lc.y / -lc.z) <= frame_tan.y * FRAME_FILL


func contact(now: float) -> void:
	if started and not finished() and now - last_touch >= 0.4:
		last_touch = now
		touches += 1


func finished() -> bool:
	return finish_time >= 0.0


func count() -> int:
	return done.count(true)


func elapsed(now: float) -> float:
	if start_time < 0.0:
		return 0.0
	return (finish_time if finished() else now) - start_time
