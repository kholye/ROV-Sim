class_name RovSensors
extends RefCounted
## Датчики: давление, сырые гироскопы и акселерометры с шумом по Аллану (Дунаев т. 5-6),
## курс модуля AHRS (гироскоп + магнитометр, комплементарный фильтр). Порт physics_ref/rov/sensors.py.
## RandomNumberGenerator это не узел, а объект данных: физика от сцены не зависит.

var p: Dictionary
var rng := RandomNumberGenerator.new()
var fs: float
var _rrw := PackedFloat64Array([0, 0, 0, 0, 0, 0])   # гиро xyz, аксел xyz
var _gm := PackedFloat64Array([0, 0, 0, 0, 0, 0])
var _N := PackedFloat64Array()
var _K := PackedFloat64Array()
var _B := PackedFloat64Array()
var heading := 0.0
var _heading_init := false


func _init(params: Dictionary, seed_ := 1) -> void:
	p = params
	rng.seed = seed_
	fs = p["imu_rate"]
	for key in ["gyro", "accel"]:
		for i in 3:
			_N.append(float(p[key + "_N"][i]))
			_K.append(float(p[key + "_K"][i]))
			_B.append(float(p[key + "_B"][i]))
	for i in 6:
		_gm[i] = _B[i] / 0.62 * rng.randfn()


func depth_from_pressure(p_pa: float) -> float:
	return (p_pa - float(p["p_atm"])) / (float(p["rho"]) * float(p["g"]))


func pressure_at(depth: float) -> float:
	return float(p["p_atm"]) + float(p["rho"]) * float(p["g"]) * depth


## Одна выборка ИНС на частоте fs: истинные omega (3) и удельная сила f (3) -> измеренные (6).
func imu_sample(omega: PackedFloat64Array, f: PackedFloat64Array) -> PackedFloat64Array:
	var dt := 1.0 / fs
	var a_gyro := exp(-dt / float(p["gyro_bias_tau"]))
	var a_acc := exp(-dt / float(p["accel_bias_tau"]))
	var out := PackedFloat64Array()
	out.resize(6)
	for i in 6:
		var a := a_gyro if i < 3 else a_acc
		_rrw[i] += _K[i] * sqrt(dt) * rng.randfn()
		_gm[i] = a * _gm[i] + _B[i] / 0.62 * sqrt(1.0 - a * a) * rng.randfn()
		var truth: float = omega[i] if i < 3 else f[i - 3]
		out[i] = truth + _N[i] * sqrt(fs) * rng.randfn() + _rrw[i] + _gm[i]
	return out


## Курс модуля: интеграл скорости курса + поправка к магнитному курсу (tau_f = ahrs_tau).
func ahrs_heading_step(psi_true: float, psi_rate_meas: float) -> float:
	if not _heading_init:
		heading = psi_true
		_heading_init = true
	var dt := 1.0 / fs
	heading += psi_rate_meas * dt
	var mag := psi_true + deg_to_rad(float(p["mag_heading_sigma_deg"])) * rng.randfn()
	var e := atan2(sin(mag - heading), cos(mag - heading))
	heading += dt / float(p["ahrs_tau"]) * e
	return heading
