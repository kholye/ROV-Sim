class_name RovEnvironment
extends RefCounted
## Течение (постоянное + Гаусс-Марков, Fossen 2011, разд. 8.3) и батарея.
## Порт physics_ref/rov/environment.py.


class Current:
	extends RefCounted
	var V0 := 0.0
	var dir := 0.0
	var T := 0.0
	var sigma_w := 0.0
	var dV := 0.0
	var rng := RandomNumberGenerator.new()

	func _init(speed := 0.0, direction_rad := 0.0, T_ := 0.0, sigma_w_ := 0.0, seed_ := 0) -> void:
		V0 = speed
		dir = direction_rad
		T = T_
		sigma_w = sigma_w_
		rng.seed = seed_

	func step(dt: float) -> PackedFloat64Array:
		if T > 0.0 and sigma_w > 0.0:
			var a := exp(-dt / T)
			dV = a * dV + sigma_w * sqrt(T / 2.0 * (1.0 - a * a)) * rng.randfn()
		return velocity()

	func velocity() -> PackedFloat64Array:
		var V := V0 + dV
		return PackedFloat64Array([V * cos(dir), V * sin(dir), 0.0])


class Battery:
	extends RefCounted
	var p: Dictionary
	var E0: float
	var E: float
	var used := 0.0

	func _init(params: Dictionary) -> void:
		p = params
		E0 = float(p["battery_energy"]) * 3600.0
		E = E0

	func power(thr: PackedFloat64Array, tank_cmd: PackedInt32Array, lamp: float) -> float:
		var P: float = float(p["power_hotel"]) + float(p["power_lamp"]) * lamp
		for s in thr:
			P += float(p["thruster_power_max"]) * pow(absf(clampf(s, -1.0, 1.0)), 3.0)
		for c in tank_cmd:
			if c != 0:
				P += float(p["power_tank_motor"])
		return P

	func step(dt: float, thr: PackedFloat64Array, tank_cmd: PackedInt32Array, lamp := 0.0) -> float:
		var P := power(thr, tank_cmd, lamp) if E > 0.0 else 0.0
		var dE := minf(P * dt, E)
		E -= dE
		used += dE
		return P

	func soc() -> float:
		return E / E0

	func voltage(P: float) -> float:
		if E <= 0.0:
			return 0.0
		var ocv: float = float(p["battery_v_empty"]) + (float(p["battery_v_full"]) - float(p["battery_v_empty"])) * soc()
		var R: float = p["battery_r_int"]
		var I := (ocv - sqrt(maxf(ocv * ocv - 4.0 * R * P, 0.0))) / (2.0 * R)
		return ocv - I * R
