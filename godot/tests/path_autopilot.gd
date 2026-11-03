extends RefCounted
## Автопилот проверок «по точкам» (не игровой режим): глубина — ПИД пульта на цистернах, курс и ход — стик пульта,
## как ring_autopilot.gd. Точки — NED [север, восток, глубина]; следующая, когда ближе 0,6 м по горизонтали.
## В сцене судна: --path "n,e,d;n,e,d;…" (показ кабеля, зацепов, ила).

var rov: Rov
var points: Array = []
var i := 0


func attach(r: Rov, spec: String) -> void:
	rov = r
	for s in spec.split(";", false):
		points.append(s.split_floats(","))
	rov.depth_hold = true
	if not points.is_empty():
		rov.depth_target = points[0][2]


static func _raw(u: float) -> int:
	if absf(u) < 1e-3:
		return 0
	return int(signf(u) * (15001.0 + clampf(absf(u), 0.0, 1.0) * (32767.0 - 15001.0)))


func done() -> bool:
	return i >= points.size()


var _log := OS.get_cmdline_user_args().has("--path_log")   # --path_log: раз в секунду глубина, дифферент, скорость
var _t := 0.0


func stick(r: Rov) -> Array:
	if _log and r.time - _t >= 1.0:
		_t = r.time
		print("PATH t=%.0f точка %d глубина %.2f дифферент %.1f скорость %.2f м/с" % [r.time, i, r.x[2], rad_to_deg(r.x[4]), r.x[6]])
	if done():
		return [0, 0]
	var t: PackedFloat64Array = points[i]
	var dx := t[0] - r.x[0]
	var dy := t[1] - r.x[1]
	var dist := sqrt(dx * dx + dy * dy)
	r.depth_target = t[2]
	if dist < 0.6:
		i += 1
		return [0, 0]
	var e := wrapf(atan2(dy, dx) - r.x[5], -PI, PI)
	var turn := clampf(1.6 * e - 1.2 * r.x[11], -1.0, 1.0)
	var fwd := clampf(dist * 0.8, 0.0, 0.35) * clampf(1.0 - absf(e) / 0.6, 0.0, 1.0)   # ход до ≈ 0,5 м/с: быстрее корпус неустойчив по дифференту (V1)
	if fwd < 0.05 and absf(r.x[6]) > 0.05:
		fwd = -0.3 * signf(r.x[6])
	return [_raw(turn * 0.8), _raw(fwd)]
