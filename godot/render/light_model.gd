class_name LightModel
extends RefCounted
## Модель подводного света на процессоре: те же формулы, что shaders/underwater.gdshaderinc и
## physics_ref/rov/light.py (разд. 17-21 physics-sources.md). Нужна для замера экспозиции камеры
## (автоэкспозиция по нескольким точкам кадра) и для яркости частиц взвеси. Без узлов.

const STEPS := 10

var c := Vector3.ZERO
var b := Vector3.ZERO
var kd := Vector3.ZERO
var esurf := Vector3.ZERO
var mu_d := 0.8
var nu := 0.0
var k := 0.0
var c180 := 0.0
var surface_y := 0.0
var lamp_pos := Vector3.ZERO
var lamp_dir := Vector3.FORWARD
var lamp_i := Vector3.ZERO


func _init(uw: Underwater, surface := 0.0) -> void:
	c = uw.c
	b = uw.b
	kd = uw.kd
	esurf = uw.esurf
	mu_d = float(uw.p["mean_cosine_down"])
	var n: float = uw.p["phase_ff_n"]
	nu = (3.0 - float(uw.p["phase_ff_mu"])) / 2.0
	k = 4.0 / (3.0 * (n - 1.0) * (n - 1.0))
	var kn := pow(k, nu)
	c180 = (1.0 - kn) / (16.0 * PI * (k - 1.0) * kn)
	surface_y = surface


static func _exp3(v: Vector3) -> Vector3:
	return Vector3(exp(v.x), exp(v.y), exp(v.z))


func phase(cos_psi: float) -> float:
	var s2 := maxf((1.0 - cos_psi) * 0.5, 1e-6)
	var d := k * s2
	if absf(1.0 - d) < 1e-3:
		d = 1.0 - 1e-3
	var dn := pow(d, nu)
	var f := (nu * (1.0 - d) - (1.0 - dn) + (d * (1.0 - dn) - nu * (1.0 - d)) / s2) / (4.0 * PI * (1.0 - d) * (1.0 - d) * dn)
	return f + c180 * (3.0 * cos_psi * cos_psi - 1.0)


func lamp_intensity(l: Vector3) -> Vector3:
	return lamp_i * maxf(l.dot(lamp_dir), 0.0)


## Освещённость в точке P (нормаль N, Vector3.ZERO: шар — без косинуса) от лампы и света сверху.
func irradiance(P: Vector3, N: Vector3) -> Vector3:
	var lv := P - lamp_pos
	var r := maxf(lv.length(), 0.02)
	var l := lv / r
	var cos_i := 1.0 if N == Vector3.ZERO else maxf(-l.dot(N), 0.0)
	var e := lamp_intensity(l) * (cos_i / (r * r)) * _exp3(-c * r)
	var Ed := esurf * _exp3(-kd * maxf(surface_y - P.y, 0.0))
	var nu_up := 0.0 if N == Vector3.ZERO else N.y
	return e + Ed * ((1.0 + nu_up) * 0.5 + 0.05 * (1.0 - nu_up) * 0.5)


func backscatter(cam: Vector3, dir: Vector3, D: float) -> Vector3:
	var acc := Vector3.ZERO
	if lamp_i == Vector3.ZERO:
		return acc
	for i in STEPS:
		var s := (i + 0.5) / STEPS
		var t := D * s * s
		var dt := D * 2.0 * s / STEPS
		var X := cam + dir * t
		var v := X - lamp_pos
		var r := maxf(v.length(), 0.02)
		var l := v / r
		acc += b * phase(-l.dot(dir)) * lamp_intensity(l) / (r * r) * _exp3(-c * (r + t)) * dt
	return acc


func linf(cam: Vector3) -> Vector3:
	var Ed := esurf * _exp3(-kd * maxf(surface_y - cam.y, 0.0))
	return b * Ed / mu_d / (4.0 * PI) / c


## Яркость точки P (альбедо albedo) для камеры cam.
func radiance(cam: Vector3, P: Vector3, N: Vector3, albedo: Vector3) -> Vector3:
	var V := P - cam
	var D := maxf(V.length(), 1e-4)
	var dir := V / D
	var e_lamp_amb := irradiance(P, N)
	var T := _exp3(-c * D)
	return albedo / PI * e_lamp_amb * T + backscatter(cam, dir, D) + linf(cam) * (Vector3.ONE - T)
