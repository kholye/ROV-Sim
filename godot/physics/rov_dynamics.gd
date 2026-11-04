class_name RovDynamics
extends RefCounted
## Динамика аппарата, 6 степеней свободы по Fossen (2011), система NED.
## Порт physics_ref/rov/dynamics.py: те же формулы и тот же RK4. Без узлов Godot и без
## Vector3/Basis (они 32-битные): только float (64 бита) и PackedFloat64Array.
##
## Состояние x (14): x y z phi theta psi | u v w p q r | V1 V2.
## Перевод в систему Godot делает только ned_godot.gd.

var p: Dictionary
var r_hull: float                   # только для выхода на поверхность
var ma := PackedFloat64Array()      # присоединённые массы, полная матрица 6×6 (36, по строкам)
var d_quad := PackedFloat64Array()  # равносильная диагональ сопротивления (6), для проверок
var d_lin := PackedFloat64Array()   # линейное сопротивление (6)
var k_front: float                  # 1/2 rho Cd_ax A_front
var front_c := PackedFloat64Array() # центр лобовой площади (y, z)
var k_cr: float                     # 1/2 rho Cd_cross
var side := PackedFloat64Array()    # клетки силуэта сбоку: x, z, A подряд
var top := PackedFloat64Array()     # клетки силуэта сверху, правая половина: x, y > 0, A подряд
var thr_pos := [PackedFloat64Array(), PackedFloat64Array()]
var tank_x := PackedFloat64Array()
var fins: Array = []


static func load_params(path: String = "res://physics/rov_params.json") -> Dictionary:
	var raw: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(path))
	var out := {}
	for k in raw:
		if not String(k).begins_with("_"):
			out[k] = raw[k]["value"]
	return out


func _init(params: Dictionary) -> void:
	p = params
	var rho: float = p["rho"]
	r_hull = float(p["hull_diameter"]) / 2.0
	ma = added_mass_matrix(p)
	k_front = 0.5 * rho * float(p["cd_axial"]) * float(p["drag_area_front"])
	front_c = PackedFloat64Array(p["drag_front_center"])
	k_cr = 0.5 * rho * float(p["cd_cross"])
	for c in p["drag_cells_side"]:
		side.append_array(PackedFloat64Array(c))
	for c in p["drag_cells_top"]:
		top.append_array(PackedFloat64Array(c))
	# равносильная диагональ: сила при движении по одной оси (как d_quad в dynamics.py)
	d_quad = PackedFloat64Array([k_front, 0, 0, 0, 0, 0])
	for i in range(0, side.size(), 3):
		var x := side[i]; var z := side[i + 1]; var A := side[i + 2]
		d_quad[1] += k_cr * A
		d_quad[3] += k_cr * A * pow(absf(z), 3)
		d_quad[5] += k_cr * A * pow(absf(x), 3)
	for i in range(0, top.size(), 3):
		var x := top[i]; var y := top[i + 1]; var A := 2.0 * top[i + 2]   # с зеркальной половиной
		d_quad[2] += k_cr * A
		d_quad[3] += k_cr * A * pow(absf(y), 3)
		d_quad[4] += k_cr * A * pow(absf(x), 3)
	# линейное: по вертикали трос и трение (подогнано по рис. 48 Дунаева), крен (оценка)
	d_lin = PackedFloat64Array([0.0, 0.0, float(p["heave_damping_lin"]), float(p["roll_damping_lin"]), 0.0, 0.0])
	var tp: Array = p["thruster_pos"]
	thr_pos = [PackedFloat64Array([tp[0], -float(tp[1]), tp[2]]), PackedFloat64Array([tp[0], tp[1], tp[2]])]
	tank_x = PackedFloat64Array(p["tank_x"])
	fins = p["fins"]


## Присоединённые массы 6×6 по полосам (как added_mass_matrix в dynamics.py):
## M_A = ∫ rho (s22 J2ᵀJ2 + s33 J3ᵀJ3) dx + rho s44 в (3, 3), J2 = [0,1,0,-z,0,x], J3 = [0,0,1,y,-x,0].
static func added_mass_matrix(pp: Dictionary) -> PackedFloat64Array:
	var rho: float = pp["rho"]
	var M := PackedFloat64Array()
	M.resize(36)
	M.fill(0.0)
	M[0] = float(pp["added_mass_surge"])
	for s in pp["added_mass_strips"]:
		var x0: float = s["x0"]; var x1: float = s["x1"]
		var y: float = s["y"]; var z: float = s["z"]
		var L := x1 - x0
		var X1 := (x1 * x1 - x0 * x0) / 2.0
		var X2 := (x1 * x1 * x1 - x0 * x0 * x0) / 3.0
		var a: float = rho * float(s["s22"])
		var b: float = rho * float(s["s33"])
		M[1 * 6 + 1] += a * L
		M[1 * 6 + 3] += -a * z * L
		M[1 * 6 + 5] += a * X1
		M[3 * 6 + 3] += a * z * z * L
		M[3 * 6 + 5] += -a * z * X1
		M[5 * 6 + 5] += a * X2
		M[2 * 6 + 2] += b * L
		M[2 * 6 + 3] += b * y * L
		M[2 * 6 + 4] += -b * X1
		M[3 * 6 + 3] += b * y * y * L
		M[3 * 6 + 4] += -b * y * X1
		M[4 * 6 + 4] += b * X2
		M[3 * 6 + 3] += rho * float(s["s44"]) * L
	for i in 6:
		for j in range(i + 1, 6):
			M[j * 6 + i] = M[i * 6 + j]
	return M


static func submerged_fraction(z_axis: float, r: float) -> float:
	var h := clampf(z_axis + r, 0.0, 2.0 * r)
	if h <= 0.0:
		return 0.0
	if h >= 2.0 * r:
		return 1.0
	var seg := r * r * acos((r - h) / r) - (r - h) * sqrt(2.0 * r * h - h * h)
	return seg / (PI * r * r)


static func cross(a: PackedFloat64Array, b: PackedFloat64Array) -> PackedFloat64Array:
	return PackedFloat64Array([a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]])


## Матрица тело -> NED (Fossen 2011, ф. 2.18), строки подряд (9 чисел).
static func rot_nb(phi: float, theta: float, psi: float) -> PackedFloat64Array:
	var cf := cos(phi); var sf := sin(phi)
	var ct := cos(theta); var st := sin(theta)
	var cp := cos(psi); var sp := sin(psi)
	return PackedFloat64Array([
		cp * ct, -sp * cf + cp * st * sf, sp * sf + cp * cf * st,
		sp * ct, cp * cf + sf * st * sp, -cp * sf + st * sp * cf,
		-st, ct * sf, ct * cf])


## Матрица масс M_RB + M_A (36 чисел), центр масс и масса.
## При сбросе груза его масса и момент инерции вычитаются в точке ballast_drop_pos.
func mass_matrix(V1: float, V2: float, dropped: bool) -> Dictionary:
	var rho: float = p["rho"]
	var m0: float = p["mass_dry"]
	var cg0 := PackedFloat64Array(p["cg_dry"])
	# инерция сухого аппарата относительно начала координат тела
	var Id: Array = p["inertia_dry_cg"]
	var I := PackedFloat64Array([0, 0, 0, 0, 0, 0, 0, 0, 0])
	for i in 3:
		I[i * 4] = float(Id[i])
	_add_point_inertia(I, m0, cg0)
	var m_body := m0
	var cgb := cg0.duplicate()
	if dropped:
		var md: float = p["ballast_drop_mass"]
		var rd := PackedFloat64Array(p["ballast_drop_pos"])
		m_body = m0 - md
		for i in 3:
			cgb[i] = (m0 * cg0[i] - md * rd[i]) / m_body
		_add_point_inertia(I, -md, rd)
	var mw := [rho * V1, rho * V2]
	var m: float = m_body + mw[0] + mw[1]
	var rg := PackedFloat64Array()
	for i in 3:
		var s: float = m_body * cgb[i]
		if i == 0:
			s += mw[0] * tank_x[0] + mw[1] * tank_x[1]
		rg.append(s / m)
	for k in 2:
		_add_point_inertia(I, mw[k], PackedFloat64Array([tank_x[k], 0.0, 0.0]))
	var M := PackedFloat64Array()
	M.resize(36)
	M.fill(0.0)
	for i in 3:
		M[i * 6 + i] = m
		for j in 3:
			M[(3 + i) * 6 + 3 + j] = I[i * 3 + j]
	# -m S(rg) вверху справа, m S(rg) внизу слева
	var S := [[0.0, -rg[2], rg[1]], [rg[2], 0.0, -rg[0]], [-rg[1], rg[0], 0.0]]
	for i in 3:
		for j in 3:
			M[i * 6 + 3 + j] = -m * S[i][j]
			M[(3 + i) * 6 + j] = m * S[i][j]
	var Mrb := M.duplicate()
	for i in 36:
		M[i] += ma[i]
	return {"m": m, "rg": rg, "M": M, "Mrb": Mrb}


## Точечная масса mm в точке rr: прибавить mm (|r|² E − r rᵀ) к тензору I (9 чисел).
static func _add_point_inertia(I: PackedFloat64Array, mm: float, rr: PackedFloat64Array) -> void:
	var r2 := rr[0] * rr[0] + rr[1] * rr[1] + rr[2] * rr[2]
	for i in 3:
		for j in 3:
			I[i * 3 + j] += mm * ((r2 if i == j else 0.0) - rr[i] * rr[j])


func displaced_volume(dropped: bool) -> float:
	return float(p["mass_dry"]) / float(p["rho"]) + float(p["neutral_tank_volume"]) \
			- (float(p["ballast_drop_volume"]) if dropped else 0.0)


## Центр плавучести; после сброса груза без объёма груза.
func buoyancy_center(dropped: bool) -> PackedFloat64Array:
	var cb := PackedFloat64Array(p["cb"])
	if not dropped:
		return cb
	var V := displaced_volume(false)
	var Vd: float = p["ballast_drop_volume"]
	var rd := PackedFloat64Array(p["ballast_drop_pos"])
	for i in 3:
		cb[i] = (V * cb[i] - Vd * rd[i]) / (V - Vd)
	return cb


## C(nu)·nu по матрице масс (Fossen 2011, ф. 6.43): [n2 x a; n1 x a + n2 x b].
static func coriolis_times(M: PackedFloat64Array, nu: PackedFloat64Array) -> PackedFloat64Array:
	var a := PackedFloat64Array([0, 0, 0])
	var b := PackedFloat64Array([0, 0, 0])
	for i in 3:
		for j in 6:
			a[i] += M[i * 6 + j] * nu[j]
			b[i] += M[(3 + i) * 6 + j] * nu[j]
	var n1 := PackedFloat64Array([nu[0], nu[1], nu[2]])
	var n2 := PackedFloat64Array([nu[3], nu[4], nu[5]])
	var top := cross(n2, a)
	var bot1 := cross(n1, a)
	var bot2 := cross(n2, b)
	return PackedFloat64Array([top[0], top[1], top[2], bot1[0] + bot2[0], bot1[1] + bot2[1], bot1[2] + bot2[2]])


func restoring(eta: PackedFloat64Array, W: float, B: float, rg: PackedFloat64Array, rb) -> PackedFloat64Array:
	var cf := cos(eta[3]); var sf := sin(eta[3])
	var ct := cos(eta[4]); var st := sin(eta[4])
	var xg := rg[0]; var yg := rg[1]; var zg := rg[2]
	var xb: float = rb[0]; var yb: float = rb[1]; var zb: float = rb[2]
	return PackedFloat64Array([
		(W - B) * st,
		-(W - B) * ct * sf,
		-(W - B) * ct * cf,
		-(yg * W - yb * B) * ct * cf + (zg * W - zb * B) * ct * sf,
		(zg * W - zb * B) * st + (xg * W - xb * B) * ct * cf,
		-(xg * W - xb * B) * ct * sf - (yg * W - yb * B) * st])


## Тяга движителей: s = [левый, правый] в [-1, 1]; T = Tmax·s·|s| (оценка).
func thrust(s: PackedFloat64Array) -> PackedFloat64Array:
	var tau := PackedFloat64Array([0, 0, 0, 0, 0, 0])
	for k in 2:
		var sk := clampf(s[k], -1.0, 1.0)
		var T: float = float(p["thrust_max"]) * sk * absf(sk)
		if T < 0.0:
			T *= float(p["thrust_reverse_ratio"])
		var F := PackedFloat64Array([T, 0.0, 0.0])
		var mom := cross(thr_pos[k], F)
		tau[0] += T
		for i in 3:
			tau[3 + i] += mom[i]
	return tau


## Плоскости и насадки: сила вдоль нормали (ось y или z тела) от местной скорости,
## подъёмная сила с ограничением угла срыва + сопротивление пластины. Как fin_forces в dynamics.py.
func fin_forces(nu_r: PackedFloat64Array) -> PackedFloat64Array:
	var rho: float = p["rho"]
	var tau := PackedFloat64Array([0, 0, 0, 0, 0, 0])
	var w := PackedFloat64Array([nu_r[3], nu_r[4], nu_r[5]])
	for f in fins:
		var r := PackedFloat64Array(f["pos"])
		var n: int = int(f["normal"])
		var wr := cross(w, r)
		var u: float = nu_r[0] + wr[0]
		var c: float = nu_r[n] + wr[n]
		var k: float = tan(deg_to_rad(float(f["alpha_stall_deg"]))) * absf(u)
		var c_lift := clampf(c, -k, k)
		var F: float = -0.5 * rho * float(f["area"]) * (float(f["cla"]) * absf(u) * c_lift + float(f["cd_plate"]) * absf(c) * c)
		var Fv := PackedFloat64Array([0, 0, 0])
		Fv[n] = F
		var mom := cross(r, Fv)
		for i in 3:
			tau[i] += Fv[i]
			tau[3 + i] += mom[i]
	return tau


## Квадратичное сопротивление по силуэтам (как drag в dynamics.py): продольное в центре лобовой
## площади, поперечное по клеткам силуэтов от местной скорости (cross-flow drag).
func drag(nu_r: PackedFloat64Array) -> PackedFloat64Array:
	var u := nu_r[0]; var v := nu_r[1]; var w := nu_r[2]
	var pr := nu_r[3]; var q := nu_r[4]; var r := nu_r[5]
	var tau := PackedFloat64Array([0, 0, 0, 0, 0, 0])
	var yc := front_c[0]; var zc := front_c[1]
	var ul := u + q * zc - r * yc
	var Fx := -k_front * absf(ul) * ul
	tau[0] += Fx
	tau[4] += zc * Fx
	tau[5] += -yc * Fx
	for i in range(0, side.size(), 3):
		var x := side[i]; var z := side[i + 1]
		var vl := v + r * x - pr * z
		var Fy := -k_cr * side[i + 2] * absf(vl) * vl
		tau[1] += Fy
		tau[3] += -z * Fy
		tau[5] += x * Fy
	# сверху: клетка (x, y) и её зеркальная (x, -y) попарно, симметрия точная
	for i in range(0, top.size(), 3):
		var x := top[i]; var y := top[i + 1]
		var wp := w + pr * y - q * x
		var wm := w - pr * y - q * x
		var Fp := -k_cr * top[i + 2] * absf(wp) * wp
		var Fm := -k_cr * top[i + 2] * absf(wm) * wm
		tau[2] += Fp + Fm
		tau[3] += y * (Fp - Fm)
		tau[4] += -x * (Fp + Fm)
	return tau


## Решение M x = b (6x6) методом Гаусса с выбором главного элемента.
static func solve6(M: PackedFloat64Array, b: PackedFloat64Array) -> PackedFloat64Array:
	var A := M.duplicate()
	var x := b.duplicate()
	for c in 6:
		var piv := c
		for r in range(c + 1, 6):
			if absf(A[r * 6 + c]) > absf(A[piv * 6 + c]):
				piv = r
		if piv != c:
			for j in 6:
				var t := A[c * 6 + j]; A[c * 6 + j] = A[piv * 6 + j]; A[piv * 6 + j] = t
			var tb := x[c]; x[c] = x[piv]; x[piv] = tb
		for r in range(c + 1, 6):
			var f := A[r * 6 + c] / A[c * 6 + c]
			for j in range(c, 6):
				A[r * 6 + j] -= f * A[c * 6 + j]
			x[r] -= f * x[c]
	for c in range(5, -1, -1):
		var s := x[c]
		for j in range(c + 1, 6):
			s -= A[c * 6 + j] * x[j]
		x[c] = s / A[c * 6 + c]
	return x


## Производная состояния (14) и nu' (6) подряд: 20 чисел.
## ext — внешняя сила (кабель-трос): 6 чисел [сила в NED, Н; точка приложения в осях тела, м] или пусто.
## contacts — плоскости касания у точек корпуса (RovContact, по 9 чисел на точку) или пусто.
func deriv(x: PackedFloat64Array, thr: PackedFloat64Array, tank_cmd: PackedInt32Array,
		vc_n: PackedFloat64Array, dropped: bool, ext := PackedFloat64Array(),
		contacts := PackedFloat64Array()) -> PackedFloat64Array:
	var eta := x.slice(0, 6)
	var nu := x.slice(6, 12)
	var R := rot_nb(eta[3], eta[4], eta[5])
	var mm := mass_matrix(x[12], x[13], dropped)
	var m: float = mm["m"]
	var W: float = m * float(p["g"])
	var B: float = float(p["rho"]) * float(p["g"]) * displaced_volume(dropped) * submerged_fraction(eta[2], r_hull)
	# течение в осях тела: R^T v_c
	var vcb := PackedFloat64Array([0, 0, 0])
	for i in 3:
		for j in 3:
			vcb[i] += R[j * 3 + i] * vc_n[j]
	var nu_r := nu.duplicate()
	for i in 3:
		nu_r[i] -= vcb[i]
	var w_body := PackedFloat64Array([nu[3], nu[4], nu[5]])
	var nudot_c := cross(w_body, vcb)   # -S(w) v_c = -(w x v_c); знак ниже
	var tau := thrust(thr)
	if ext.size() == 6:
		var Fb := PackedFloat64Array([0, 0, 0])
		for i in 3:
			for j in 3:
				Fb[i] += R[j * 3 + i] * ext[j]
		var rr := PackedFloat64Array([ext[3], ext[4], ext[5]])
		var mo := cross(rr, Fb)
		for i in 3:
			tau[i] += Fb[i]
			tau[3 + i] += mo[i]
	if contacts.size() > 0:
		var tc := RovContact.wrench(x, R, contacts, float(p["contact_k"]), float(p["contact_c"]),
				float(p["contact_mu"]), float(p["contact_v_eps"]))
		for i in 6:
			tau[i] += tc[i]
	var tf := fin_forces(nu_r)
	var td := drag(nu_r)
	for i in 6:
		tau[i] += tf[i] + td[i]
	var crb := coriolis_times(mm["Mrb"], nu)
	var ca := coriolis_times(ma, nu_r)
	var g := restoring(eta, W, B, mm["rg"], buoyancy_center(dropped))
	var rhs := PackedFloat64Array([0, 0, 0, 0, 0, 0])
	for i in 6:
		var dv := d_lin[i] * nu_r[i]
		var mc := 0.0                      # M_A · nu_c', nu_c' = (-(w × v_c), 0)
		for j in 3:
			mc -= ma[i * 6 + j] * nudot_c[j]
		rhs[i] = tau[i] - crb[i] - ca[i] - dv - g[i] + mc
	var nudot := solve6(mm["M"], rhs)
	var out := PackedFloat64Array()
	out.resize(20)
	# eta' = J(eta) nu
	for i in 3:
		out[i] = R[i * 3] * nu[0] + R[i * 3 + 1] * nu[1] + R[i * 3 + 2] * nu[2]
	var cf := cos(eta[3]); var sf := sin(eta[3])
	var ct := cos(eta[4]); var tt := tan(eta[4])
	out[3] = nu[3] + sf * tt * nu[4] + cf * tt * nu[5]
	out[4] = cf * nu[4] - sf * nu[5]
	out[5] = sf / ct * nu[4] + cf / ct * nu[5]
	for i in 6:
		out[6 + i] = nudot[i]
		out[14 + i] = nudot[i]
	var cap: float = p["tank_capacity"]
	for k in 2:
		var c := tank_cmd[k]
		var V := x[12 + k]
		out[12 + k] = 0.0
		if (c > 0 and V < cap) or (c < 0 and V > 0.0):
			out[12 + k] = float(p["tank_rate"]) * signf(c)
	return out


## Силы для показа (окошко «вид сбоку», клавиша F3), те же формулы, что в deriv; на движение не влияет.
## Вес и Архимед — модули (Н) и точки приложения (ЦМ, ЦВ) в осях тела; тяга каждого движителя (Н)
## и его положение; сопротивление вместе с плоскостями — сила (Н) в осях тела, приложена условно в начале.
func forces(x: PackedFloat64Array, thr: PackedFloat64Array, dropped: bool) -> Dictionary:
	var mm := mass_matrix(x[12], x[13], dropped)
	var W: float = float(mm["m"]) * float(p["g"])
	var B: float = float(p["rho"]) * float(p["g"]) * displaced_volume(dropped) * submerged_fraction(x[2], r_hull)
	var T := PackedFloat64Array([0, 0])
	for k in 2:
		var sk := clampf(thr[k], -1.0, 1.0)
		T[k] = float(p["thrust_max"]) * sk * absf(sk)
		if T[k] < 0.0:
			T[k] *= float(p["thrust_reverse_ratio"])
	var nu := x.slice(6, 12)
	var td := drag(nu)
	var tf := fin_forces(nu)
	return {"W": W, "B": B, "rg": mm["rg"], "rb": buoyancy_center(dropped), "T": T, "thr_pos": thr_pos,
			"drag": PackedFloat64Array([td[0] + tf[0], td[1] + tf[1], td[2] + tf[2]])}


## Один шаг RK4, входы (и внешняя сила ext, см. deriv) постоянны на шаге. Возвращает новое состояние (14).
func rk4_step(x: PackedFloat64Array, dt: float, thr: PackedFloat64Array, tank_cmd: PackedInt32Array,
		vc_n := PackedFloat64Array([0, 0, 0]), dropped := false, ext := PackedFloat64Array(),
		contacts := PackedFloat64Array()) -> PackedFloat64Array:
	var k1 := deriv(x, thr, tank_cmd, vc_n, dropped, ext, contacts)
	var k2 := deriv(_axpy(x, k1, 0.5 * dt), thr, tank_cmd, vc_n, dropped, ext, contacts)
	var k3 := deriv(_axpy(x, k2, 0.5 * dt), thr, tank_cmd, vc_n, dropped, ext, contacts)
	var k4 := deriv(_axpy(x, k3, dt), thr, tank_cmd, vc_n, dropped, ext, contacts)
	var xn := PackedFloat64Array()
	xn.resize(14)
	for i in 14:
		xn[i] = x[i] + dt / 6.0 * (k1[i] + 2.0 * k2[i] + 2.0 * k3[i] + k4[i])
	var cap: float = p["tank_capacity"]
	xn[12] = clampf(xn[12], 0.0, cap)
	xn[13] = clampf(xn[13], 0.0, cap)
	return xn


static func _axpy(x: PackedFloat64Array, k: PackedFloat64Array, h: float) -> PackedFloat64Array:
	var y := PackedFloat64Array()
	y.resize(14)
	for i in 14:
		y[i] = x[i] + h * k[i]
	return y


static func initial_state(depth := 0.0, psi := 0.0, V1 := 35e-6, V2 := 35e-6) -> PackedFloat64Array:
	var x := PackedFloat64Array()
	x.resize(14)
	x.fill(0.0)
	x[2] = depth
	x[5] = psi
	x[12] = V1
	x[13] = V2
	return x
