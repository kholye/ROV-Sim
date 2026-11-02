class_name NedGodot
extends RefCounted
## Единственный модуль перевода из системы физики (Fossen, NED: x север/вперёд, y восток/вправо,
## z вниз) в систему Godot (X вправо, Y вверх, -Z вперёд). Больше нигде системы не смешиваются.
##
## Godot = P · NED,  P = [[0, 1, 0], [0, 0, -1], [-1, 0, 0]]  (det P = +1, чистый поворот).
## Оси тела переводятся той же P: вперёд -> -Z, вправо -> +X, вниз -> -Y.
## Ориентация: B_godot = P · R_nb · Pᵀ.


static func vec(ned: PackedFloat64Array) -> Vector3:
	return Vector3(ned[1], -ned[2], -ned[0])


static func vec_to_ned(v: Vector3) -> PackedFloat64Array:
	return PackedFloat64Array([-v.z, v.x, -v.y])


## Положение из состояния (eta = x[0..5]).
static func position(x: PackedFloat64Array) -> Vector3:
	return Vector3(x[1], -x[2], -x[0])


static func basis(x: PackedFloat64Array) -> Basis:
	var R := RovDynamics.rot_nb(x[3], x[4], x[5])
	# P R Pᵀ: элемент (i, j) = R[pi(i), pi(j)] со знаками s(i)·s(j),
	# где строка i матрицы P имеет единицу в столбце pi(i) со знаком s(i).
	var pi := [1, 2, 0]
	var s := [1.0, -1.0, -1.0]
	var m := []
	for i in 3:
		var row := []
		for j in 3:
			row.append(s[i] * s[j] * R[pi[i] * 3 + pi[j]])
		m.append(row)
	# Basis хранит столбцы: x_axis = столбец 0 и т.д.
	return Basis(Vector3(m[0][0], m[1][0], m[2][0]),
			Vector3(m[0][1], m[1][1], m[2][1]),
			Vector3(m[0][2], m[1][2], m[2][2]))


static func transform(x: PackedFloat64Array) -> Transform3D:
	return Transform3D(basis(x), position(x))


## Линейная скорость тела (u, v, w) -> скорость в мире Godot.
static func world_velocity(x: PackedFloat64Array) -> Vector3:
	var R := RovDynamics.rot_nb(x[3], x[4], x[5])
	var v := PackedFloat64Array([0, 0, 0])
	for i in 3:
		v[i] = R[i * 3] * x[6] + R[i * 3 + 1] * x[7] + R[i * 3 + 2] * x[8]
	return vec(v)
