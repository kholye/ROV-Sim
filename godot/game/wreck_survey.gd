class_name WreckSurvey
extends RefCounted
## Правила осмотра судна как в первой версии симулятора (сборка преподавателя):
## точка осмотрена, если она ближе 3 м к камере, в пределах 35° от оси камеры, ничем не заслонена,
## и так 1,5 с подряд. Время идёт после смещения на 0,5 м от старта; финиш, когда осмотрены все.
## Касания считаются без штрафа. Без узлов: проверяется в tests/game_tests.gd.

const RANGE := 3.0
const ANGLE_DEG := 35.0
const HOLD := 1.5
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
	var fwd := -cam.basis.z.normalized()
	for i in points.size():
		if done[i]:
			continue
		var v: Vector3 = points[i] - cam.origin
		var d := v.length()
		var ok: bool = d < RANGE and rad_to_deg(fwd.angle_to(v)) < ANGLE_DEG and visible.call(cam.origin, points[i])
		seen_for[i] = seen_for[i] + dt if ok else 0.0
		if seen_for[i] >= HOLD:
			done[i] = true
			done_time[i] = now - start_time
			just_done = i
	if done.count(false) == 0 and finish_time < 0.0:
		finish_time = now


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
