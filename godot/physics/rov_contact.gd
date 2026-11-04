class_name RovContact
extends RefCounted
## Касание корпуса с дном, стенами и предметами (версия 1.4, docs/physics-sources.md, разд. 31).
## Чистые функции без узлов Godot: точки касания корпуса (contact_points в rov_params.json — вершины выпуклой
## оболочки модели) и местные плоскости препятствий в NED. Плоскости находит мост (game/rov.gd) лучами раз в кадр;
## внутри шага RK4 сила считается от текущего состояния, поэтому жёсткая пружина не раскачивается.
##
## Модель — штрафная пружина с демпфером по нормали и сглаженное кулоново трение (Hunt, Crossley 1975 —
## линейный вариант Kelvin-Voigt; трение — регуляризация Coulomb по скорости, как в MuJoCo / Drake):
##   δ = (S − P)·n > 0 — заглубление точки P за плоскость (S, n), n — нормаль препятствия к аппарату;
##   F_n = max(0, k·δ − c·v_n),  F_t = −μ·F_n·v_t / √(|v_t|² + v_ε²).
## k, c, μ, v_ε — оценка (подбор для устойчивого шага и малого заглубления, не замер).

## contacts: по 9 чисел на точку — [r в осях тела (3); S — точка плоскости, NED (3); n — нормаль, NED (3)].
## Возвращает силу и момент в осях тела (6), как тяга в RovDynamics.deriv.
static func wrench(x: PackedFloat64Array, R: PackedFloat64Array, contacts: PackedFloat64Array,
		k: float, c: float, mu: float, v_eps: float) -> PackedFloat64Array:
	var tau := PackedFloat64Array([0, 0, 0, 0, 0, 0])
	for b in range(0, contacts.size(), 9):
		var r := PackedFloat64Array([contacts[b], contacts[b + 1], contacts[b + 2]])
		var P := point_ned(x, R, r)
		var n := PackedFloat64Array([contacts[b + 6], contacts[b + 7], contacts[b + 8]])
		var d := (contacts[b + 3] - P[0]) * n[0] + (contacts[b + 4] - P[1]) * n[1] + (contacts[b + 5] - P[2]) * n[2]
		if d <= 0.0:
			continue
		var v := point_velocity_ned(x, R, r)
		var vn := v[0] * n[0] + v[1] * n[1] + v[2] * n[2]
		var Fn := maxf(0.0, k * d - c * vn)
		if Fn == 0.0:
			continue
		var F := PackedFloat64Array([0, 0, 0])
		var vt := PackedFloat64Array([v[0] - vn * n[0], v[1] - vn * n[1], v[2] - vn * n[2]])
		var s := mu * Fn / sqrt(vt[0] * vt[0] + vt[1] * vt[1] + vt[2] * vt[2] + v_eps * v_eps)
		for i in 3:
			F[i] = Fn * n[i] - s * vt[i]
		var Fb := PackedFloat64Array([0, 0, 0])          # Rᵀ F
		for i in 3:
			Fb[i] = R[i] * F[0] + R[3 + i] * F[1] + R[6 + i] * F[2]
		var M := RovDynamics.cross(r, Fb)
		for i in 3:
			tau[i] += Fb[i]
			tau[3 + i] += M[i]
	return tau


## Точка тела r (оси тела) в NED: η + R r.
static func point_ned(x: PackedFloat64Array, R: PackedFloat64Array, r: PackedFloat64Array) -> PackedFloat64Array:
	var out := PackedFloat64Array([x[0], x[1], x[2]])
	for i in 3:
		out[i] += R[i * 3] * r[0] + R[i * 3 + 1] * r[1] + R[i * 3 + 2] * r[2]
	return out


## Скорость точки тела r в NED: R (v + ω × r).
static func point_velocity_ned(x: PackedFloat64Array, R: PackedFloat64Array, r: PackedFloat64Array) -> PackedFloat64Array:
	var w := RovDynamics.cross(PackedFloat64Array([x[9], x[10], x[11]]), r)
	var vb := PackedFloat64Array([x[6] + w[0], x[7] + w[1], x[8] + w[2]])
	var out := PackedFloat64Array([0, 0, 0])
	for i in 3:
		out[i] = R[i * 3] * vb[0] + R[i * 3 + 1] * vb[1] + R[i * 3 + 2] * vb[2]
	return out


## Наибольшее заглубление среди точек, м (0 — касания нет): для проверок и экрана.
static func max_depth(x: PackedFloat64Array, contacts: PackedFloat64Array) -> float:
	var R := RovDynamics.rot_nb(x[3], x[4], x[5])
	var best := 0.0
	for b in range(0, contacts.size(), 9):
		var P := point_ned(x, R, PackedFloat64Array([contacts[b], contacts[b + 1], contacts[b + 2]]))
		var d := (contacts[b + 3] - P[0]) * contacts[b + 6] + (contacts[b + 4] - P[1]) * contacts[b + 7] \
				+ (contacts[b + 5] - P[2]) * contacts[b + 8]
		best = maxf(best, d)
	return best
