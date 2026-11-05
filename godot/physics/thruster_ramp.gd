class_name ThrusterRamp
extends RefCounted
## Нарастание команды движителя, как в прошивке (Павлов, прил. А, speedControl): линейно,
## полный ход за thruster_ramp_time (3 с), в обе стороны. Порт physics_ref/rov/control.py.

var rate: float
var s := PackedFloat64Array([0.0, 0.0])


func _init(p: Dictionary) -> void:
	rate = 1.0 / float(p["thruster_ramp_time"])


## Шаг dt, target — команды [-1, 1] для левого и правого. Возвращает текущие значения.
func step(dt: float, target: PackedFloat64Array) -> PackedFloat64Array:
	var lim := rate * dt
	for k in 2:
		s[k] += clampf(target[k] - s[k], -lim, lim)
	return s.duplicate()


func reset() -> void:
	s = PackedFloat64Array([0.0, 0.0])
