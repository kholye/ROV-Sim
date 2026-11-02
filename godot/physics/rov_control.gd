class_name RovControl
extends RefCounted
## Бортовое управление как на пульте: микширование стика, ПИД глубины с сеткой 0,0-9,9,
## поршни «вкл/выкл» по порогу (Дунаев 2.4, прил. А). Порт physics_ref/rov/control.py.

var kp: float
var ki: float
var kd: float
var threshold: float
var integral_limit: float
var dt: float
var predict_T: float
var integral := 0.0
var _prev_e := 0.0
var _has_prev := false
var _prev_h := 0.0
var _has_prev_h := false
var _prev_v := 0.0


## Правый стик (-32768..32767) -> [левый, правый] в -100..100 (протокол пульта).
static func joystick_to_motors(x: int, y: int, dead := 15000) -> PackedInt32Array:
	var xn := _norm(x, dead)
	var yn := _norm(y, dead)
	var L := yn + xn
	var R := yn - xn
	var mx := maxf(absf(L), absf(R))
	if mx > 1.0:
		L /= mx
		R /= mx
	return PackedInt32Array([roundi(100.0 * L), roundi(100.0 * R)])


static func _norm(a: int, dead: int) -> float:
	if absi(a) < dead:
		return 0.0
	return clampf((a - dead * signi(a)) / float(32768 - dead), -1.0, 1.0)


## Коэффициент на сетке пульта: целое 0..99 = k·10.
static func quantize_gain(k: float) -> float:
	return clampi(int(floor(k * 10.0 + 0.5)), 0, 99) / 10.0


func _init(p: Dictionary, kp_: float, ki_: float, kd_: float, predict_T_ := 0.0) -> void:
	kp = quantize_gain(kp_)
	ki = quantize_gain(ki_)
	kd = quantize_gain(kd_)
	threshold = p["pid_threshold"]
	integral_limit = p["pid_integral_limit"]
	dt = p["control_period"]
	predict_T = predict_T_


## Вызывать раз в control_period. Возвращает команду обеим цистернам: 1 набрать, -1 вытеснить, 0 стоп.
func update(target: float, h: float) -> int:
	var v := (h - _prev_h) / dt if _has_prev_h else 0.0
	var a := (v - _prev_v) / dt
	_prev_h = h
	_has_prev_h = true
	_prev_v = v
	var h_eff := h + v * predict_T + a * predict_T * predict_T / 2.0 if predict_T > 0.0 else h
	var e := target - h_eff
	integral = clampf(integral + e * dt, -integral_limit, integral_limit)
	var de := (e - _prev_e) / dt if _has_prev else 0.0
	_prev_e = e
	_has_prev = true
	var u := kp * e + ki * integral + kd * de
	if u > threshold:
		return 1
	if u < -threshold:
		return -1
	return 0
