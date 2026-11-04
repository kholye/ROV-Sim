class_name LightModel
extends RefCounted
## Модель подводного света на процессоре: те же формулы, что shaders/underwater.gdshaderinc и
## physics_ref/rov/light.py (разд. 17-21 physics-sources.md). Нужна для замера экспозиции камеры
## (автоэкспозиция по нескольким точкам кадра) и для яркости частиц взвеси. Без узлов.

const STEPS := 10
const SILT_BLUR_ALBEDO := 0.15     # рисунок за облаком ила размыт: в рассеянной вперёд части — среднее альбедо

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
var silt: Array = []               # клубы ила, как Underwater.set_silt: [{c, m, sh, sv, bed}]
var silt_a := Vector3.ZERO
var silt_b := Vector3.ZERO
var silt_k := Vector3.ONE


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
	var ss := uw.silt_star()
	silt_a = ss[0]
	silt_b = ss[1]
	silt_k = ss[2]


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
	var delta := (lamp_pos - cam).dot(dir)         # точки равномерно по углу из лампы, как uw_backscatter в шейдере
	var h := maxf((cam + dir * delta - lamp_pos).length(), 0.02)
	var th_a := atan(-delta / h)
	var dth := (atan((D - delta) / h) - th_a) / STEPS
	for i in STEPS:
		var t := delta + h * tan(th_a + (i + 0.5) * dth)
		var X := cam + dir * t
		var v := X - lamp_pos
		var r := maxf(v.length(), 0.02)
		var l := v / r
		acc += b * phase(-l.dot(dir)) * lamp_intensity(l) * _exp3(-c * (r + t)) * dth / h
	return acc


func linf(cam: Vector3) -> Vector3:
	var Ed := esurf * _exp3(-kd * maxf(surface_y - cam.y, 0.0))
	return b * Ed / mu_d / (4.0 * PI) / c


static func _erf(x: float) -> float:
	var t := 1.0 / (1.0 + 0.3275911 * absf(x))
	var y := 1.0 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) 			* t * exp(-x * x)
	return signf(x) * y


## Облако ила на луче: [пропускание чёткого изображения Tc, яркости Tk, добавка яркости S]
## (как uw_silt шейдера и silt_terms эталона;
## рассеяние — квазиоднократное приближение Gordon 1973).
func silt_terms(cam: Vector3, dir: Vector3, D: float) -> Array:
	var mm := 0.0
	var sat := Vector3.ZERO
	var tm := 0.0
	var tm2 := 0.0
	for f: Dictionary in silt:
		var C: Vector3 = f.c
		var sh: float = f.sh
		var sv: float = f.sv
		var inv := Vector3(1.0 / (sh * sh), 1.0 / (sv * sv), 1.0 / (sh * sh))
		var a2 := (dir * dir).dot(inv)
		var a := sqrt(a2)
		var norm: float = float(f.m) / (pow(2.0 * PI, 1.5) * sh * sh * sv)
		var M := 0.0
		var tstar := 0.0
		for k in 2:
			var Ck := C if k == 0 else Vector3(C.x, 2.0 * float(f.bed) - C.y, C.z)
			var q0 := cam - Ck
			var qw := (dir * q0).dot(inv)
			var t0 := -qw / a2
			if k == 0:
				tstar = clampf(t0, 0.0, D)
			var d2 := maxf((q0 * q0).dot(inv) - qw * qw / a2, 0.0)
			if d2 < 40.0:
				M += norm * exp(-0.5 * d2) * sqrt(PI / 2.0) / a * (_erf(a * (D - t0) / sqrt(2.0)) + _erf(a * t0 / sqrt(2.0)))
		if M <= 0.0:
			continue
		mm += M
		sat += silt_b / (2.0 * silt_k) * (Vector3.ONE - _exp3(-2.0 * silt_k * M))
		tm += M * tstar
		tm2 += M * (tstar * tstar + 1.0 / a2)
	var S := Vector3.ZERO
	if mm > 0.0:
		var t := tm / mm
		var s2 := maxf(tm2 / mm - t * t, 0.0)
		var P := cam + dir * t
		var lv := P - lamp_pos
		var r := maxf(lv.length(), 0.02)
		var l := lv / r
		var re2 := r * r + s2
		var Ein := lamp_intensity(l) * (phase(minf(-l.dot(dir), r / sqrt(re2))) / re2) * _exp3(-c * (r + t))
		Ein += esurf * _exp3(-kd * maxf(surface_y - P.y, 0.0)) / (4.0 * PI * mu_d) * _exp3(-c * t)
		S = sat * Ein
	return [_exp3(-(silt_a + silt_b) * mm), _exp3(-silt_k * mm), S]


## Яркость точки P (альбедо albedo) для камеры cam.
func radiance(cam: Vector3, P: Vector3, N: Vector3, albedo: Vector3) -> Vector3:
	var V := P - cam
	var D := maxf(V.length(), 1e-4)
	var dir := V / D
	var e_lamp_amb := irradiance(P, N)
	var T := _exp3(-c * D)
	var path := backscatter(cam, dir, D) + linf(cam) * (Vector3.ONE - T)
	if not silt.is_empty():
		var st := silt_terms(cam, dir, D)
		var Tc: Vector3 = st[0]
		var Tk: Vector3 = st[1]
		# размытая часть: освещённость гладкой поверхности, обращённой к камере (без рельефа и рисунка)
		var lb := (P - lamp_pos).normalized()
		var rb := maxf((P - lamp_pos).length(), 0.02)
		var e_blur := lamp_intensity(lb) * (maxf(lb.dot(dir), 0.0) / (rb * rb)) * _exp3(-c * rb) \
				+ esurf * _exp3(-kd * maxf(surface_y - P.y, 0.0)) * 0.525      # свет сверху на вертикальную грань
		return (albedo * Tc * e_lamp_amb + SILT_BLUR_ALBEDO * (Tk - Tc) * e_blur) / PI * T + path * Tk + (st[2] as Vector3)
	return albedo / PI * e_lamp_amb * T + path
