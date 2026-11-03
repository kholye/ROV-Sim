class_name TetherCable
extends RefCounted
## Кабель-трос ТНПА: цепочка сосредоточенных масс, NED, СИ, без узлов. Порт physics_ref/rov/tether.py
## (там описание модели; источники — docs/physics-sources.md, разд. 30): вес в воде, сопротивление поперёк и
## вдоль по Морисону, нерастяжимые (упругость меди) звенья только на растяжение — XPBD с прогонкой трёхдиагональной системы,
## касания через contact (мост движка), трение Кулона, подача у судна. Узлы подряд: X[3i..3i+2].

const NEWTON := 3

var p: Dictionary
var seg := 0.3
var w_net := 0.0                  # вес в воде, Н/м (+z — вниз)
var mu_m := 0.0                   # масса с присоединённой, кг/м
var kn := 0.0
var kt := 0.0
var anchor := PackedFloat64Array([0, 0, 0])
var length := 0.0
var X := PackedFloat64Array()
var V := PackedFloat64Array()
var rest := PackedFloat64Array()
var tension_end := PackedFloat64Array([0, 0, 0])   # сила кабеля на аппарат, NED, Н
var tension_top := 0.0
var taut := false
var contacts := PackedInt32Array()


func _init(params: Dictionary, anchor_: PackedFloat64Array, end: PackedFloat64Array, length_: float) -> void:
	p = params
	seg = p["tether_seg"]
	var rho: float = p["rho"]
	w_net = (float(p["tether_mass_per_m"]) - rho * float(p["tether_area"])) * float(p["g"])
	mu_m = float(p["tether_mass_per_m"]) + rho * float(p["tether_area"]) * float(p["tether_ca"])
	kn = 0.5 * rho * float(p["tether_cn"]) * float(p["tether_d_drag"])
	kt = 0.5 * rho * float(p["tether_ct"]) * PI * float(p["tether_d_drag"])
	anchor = anchor_.duplicate()
	length = length_
	_init_shape(end)


func count() -> int:
	return X.size() / 3


func node(i: int) -> PackedFloat64Array:
	return PackedFloat64Array([X[3 * i], X[3 * i + 1], X[3 * i + 2]])


func _init_shape(end: PackedFloat64Array) -> void:
	var n_full := maxi(floori(length / seg), 1)
	var l0 := length - (n_full - 1) * seg
	if l0 < 0.3 * seg and n_full > 1:
		n_full -= 1
		l0 += seg
	rest = PackedFloat64Array([l0])
	for i in n_full - 1:
		rest.append(seg)
	var N := rest.size() + 1
	var d := sqrt((end[0] - anchor[0]) ** 2 + (end[1] - anchor[1]) ** 2 + (end[2] - anchor[2]) ** 2)
	const K := 401
	var curve := PackedFloat64Array()
	curve.resize(3 * K)
	var arc := PackedFloat64Array()
	arc.resize(K)
	var sag := 0.0
	for it in 60:                         # провис h: длина дуги a + h·4u(1−u) вниз = length
		arc[0] = 0.0
		for q in K:
			var u := float(q) / (K - 1)
			for k in 3:
				curve[3 * q + k] = anchor[k] + (end[k] - anchor[k]) * u
			curve[3 * q + 2] += sag * 4.0 * u * (1.0 - u)
			if q > 0:
				arc[q] = arc[q - 1] + sqrt((curve[3 * q] - curve[3 * q - 3]) ** 2 + (curve[3 * q + 1] - curve[3 * q - 2]) ** 2
						+ (curve[3 * q + 2] - curve[3 * q - 1]) ** 2)
		if arc[K - 1] >= length or d >= length:
			break
		sag += maxf(0.5 * (length - arc[K - 1]), 0.01)
	# узлы по длине дуги (звенья сразу почти нужной длины; если дуга короче — сжаты, это изгиб)
	var pts := PackedFloat64Array()
	pts.resize(3 * N)
	var sn := 0.0
	var q := 0
	for i in N:
		if i > 0:
			sn += rest[i - 1]
		var s := sn * arc[K - 1] / length
		while q < K - 2 and arc[q + 1] < s:
			q += 1
		var f := clampf((s - arc[q]) / maxf(arc[q + 1] - arc[q], 1e-12), 0.0, 1.0)
		for k in 3:
			pts[3 * i + k] = curve[3 * q + k] + (curve[3 * q + 3 + k] - curve[3 * q + k]) * f
	X = pts
	V = PackedFloat64Array()
	V.resize(3 * N)
	V.fill(0.0)


func total_length() -> float:
	var s := 0.0
	for r in rest:
		s += r
	return s


## Помощник на судне: держит стравленным slack[0]·d + slack[1]; стравливает при натяжении у судна > taut; выбирает только
## слабину — тем медленнее, чем ближе натяжение у блока к весу висящего кабеля + запас (аппарат не тянет).
func payout(dt: float, end: PackedFloat64Array) -> void:
	var d := sqrt((end[0] - anchor[0]) ** 2 + (end[1] - anchor[1]) ** 2 + (end[2] - anchor[2]) ** 2)
	var sl: Array = p["tether_slack"]
	var lmax: float = p["tether_length_max"]
	var target := minf(lmax, maxf(float(sl[0]) * d + float(sl[1]), d + seg))
	var v: float = p["tether_payout_speed"]
	var rate := v * clampf((target - length) / 1.0, -1.0, 1.0)
	if rate < 0.0:                         # выбирает только слабину: натяжение у блока не больше веса висящего кабеля + запас
		var slack_T := w_net * maxf(end[2] - anchor[2], 0.0) + float(p["tether_haul_margin"])
		rate *= clampf(1.0 - tension_top / slack_T, 0.0, 1.0)
	if tension_top > float(p["tether_taut"]):
		rate = v
	var new_len := minf(maxf(length + rate * dt, 2.0 * seg), lmax)
	rest[0] += new_len - length
	length = new_len
	while rest[0] > 1.5 * seg:
		var f := (rest[0] - seg) / rest[0]
		var xn := PackedFloat64Array()
		var vn := PackedFloat64Array()
		for k in 3:
			xn.append(anchor[k] + (X[3 + k] - anchor[k]) * f)
			vn.append(V[3 + k] * f)
		for k in [2, 1, 0]:                      # вставка по одному в позицию узла 1: сначала z, потом y, x
			X.insert(3, xn[k])
			V.insert(3, vn[k])
		rest.insert(1, seg)
		rest[0] -= seg
	while rest[0] < 0.3 * seg and rest.size() > 2:
		for k in 3:
			X.remove_at(3)
			V.remove_at(3)
		rest[0] += rest[1]
		rest.remove_at(1)


func node_mass() -> PackedFloat64Array:
	var N := rest.size() + 1
	var L := PackedFloat64Array()
	L.resize(N)
	L.fill(0.0)
	for j in rest.size():
		L[j] += 0.5 * rest[j]
		L[j + 1] += 0.5 * rest[j]
	return L


## dt, с; end — гермоввод аппарата (NED); water: Callable(X) -> скорость воды NED (или пустой);
## contact: Callable(x_old, x_new) -> [x, нормаль, глубина] или [] (или пустой Callable).
func step(dt: float, end: PackedFloat64Array, water: Callable = Callable(), contact: Callable = Callable()) -> void:
	var N := count()
	var Lm := node_mass()
	var m := PackedFloat64Array()
	m.resize(N)
	for i in N:
		m[i] = mu_m * Lm[i]
	var P := X.duplicate()
	for i in range(1, N - 1):
		var t := PackedFloat64Array([X[3 * i + 3] - X[3 * i - 3], X[3 * i + 4] - X[3 * i - 2], X[3 * i + 5] - X[3 * i - 1]])
		var tl := maxf(sqrt(t[0] * t[0] + t[1] * t[1] + t[2] * t[2]), 1e-9)
		for k in 3:
			t[k] /= tl
		var u: PackedFloat64Array = water.call(node(i)) if water.is_valid() else PackedFloat64Array([0, 0, 0])
		var vr := PackedFloat64Array([V[3 * i] - u[0], V[3 * i + 1] - u[1], V[3 * i + 2] - u[2]])
		var vdt := vr[0] * t[0] + vr[1] * t[1] + vr[2] * t[2]
		var vt := PackedFloat64Array([vdt * t[0], vdt * t[1], vdt * t[2]])
		var vn := PackedFloat64Array([vr[0] - vt[0], vr[1] - vt[1], vr[2] - vt[2]])
		var an := minf(dt * kn * Lm[i] * sqrt(vn[0] * vn[0] + vn[1] * vn[1] + vn[2] * vn[2]) / m[i], 1.0)
		var at := minf(dt * kt * Lm[i] * absf(vdt) / m[i], 1.0)
		for k in 3:
			V[3 * i + k] -= vn[k] * an + vt[k] * at
		V[3 * i + 2] += dt * w_net * Lm[i] / m[i]
		for k in 3:
			P[3 * i + k] = X[3 * i + k] + dt * V[3 * i + k]
	for k in 3:
		P[k] = anchor[k]
		P[3 * (N - 1) + k] = end[k]
	var w := PackedFloat64Array()
	w.resize(N)
	for i in N:
		w[i] = 1.0 / m[i]
	w[0] = 0.0
	w[N - 1] = 0.0
	var M := rest.size()
	var alpha := PackedFloat64Array()
	alpha.resize(M)
	for j in M:
		alpha[j] = rest[j] / (float(p["tether_EA"]) * dt * dt)
	var lam := PackedFloat64Array()
	lam.resize(M)
	lam.fill(0.0)
	var cn := {}                       # узел -> [нормаль, глубина]
	for it in NEWTON + 1:
		_solve(P, w, alpha, lam)
		if contact.is_valid():
			for i in range(1, N - 1):
				var r: Array = contact.call(node(i), PackedFloat64Array([P[3 * i], P[3 * i + 1], P[3 * i + 2]]))
				if not r.is_empty():
					var q: PackedFloat64Array = r[0]
					for k in 3:
						P[3 * i + k] = q[k]
					var prev: float = cn[i][1] if cn.has(i) else 0.0
					cn[i] = [r[1], prev + float(r[2])]
	var mu: float = p["tether_mu"]
	var keys := cn.keys()
	keys.sort()
	for i: int in keys:
		var nrm: PackedFloat64Array = cn[i][0]
		var depth: float = cn[i][1]
		var dl := PackedFloat64Array([P[3 * i] - X[3 * i], P[3 * i + 1] - X[3 * i + 1], P[3 * i + 2] - X[3 * i + 2]])
		var dn := dl[0] * nrm[0] + dl[1] * nrm[1] + dl[2] * nrm[2]
		var tg := PackedFloat64Array([dl[0] - dn * nrm[0], dl[1] - dn * nrm[1], dl[2] - dn * nrm[2]])
		var tgl := sqrt(tg[0] * tg[0] + tg[1] * tg[1] + tg[2] * tg[2])
		var f := 1.0 if tgl <= mu * depth else (mu * depth / tgl if tgl > 0.0 else 0.0)
		for k in 3:
			P[3 * i + k] -= tg[k] * f
	for i in range(1, N - 1):
		for k in 3:
			V[3 * i + k] = (P[3 * i + k] - X[3 * i + k]) / dt
	X = P
	var nl := PackedFloat64Array([P[3 * N - 3] - P[3 * N - 6], P[3 * N - 2] - P[3 * N - 5], P[3 * N - 1] - P[3 * N - 4]])
	var nll := maxf(sqrt(nl[0] * nl[0] + nl[1] * nl[1] + nl[2] * nl[2]), 1e-12)
	# на аппарат: натяжение последнего звена + вес в воде половины звена у гермоввода
	for k in 3:
		tension_end[k] = lam[M - 1] * nl[k] / nll / (dt * dt)
	tension_end[2] += w_net * Lm[N - 1]
	tension_top = -lam[0] / (dt * dt)
	var te := sqrt(tension_end[0] ** 2 + tension_end[1] ** 2 + tension_end[2] ** 2)
	taut = length >= float(p["tether_length_max"]) - 1e-9 and te > float(p["tether_taut"])
	contacts = PackedInt32Array(keys)


## Итерация Ньютона XPBD: J W Jᵀ Δλ = −C − α̃λ (трёхдиагональная система, прогонка), затем смещения.
func _solve(P: PackedFloat64Array, w: PackedFloat64Array, alpha: PackedFloat64Array, lam: PackedFloat64Array) -> void:
	var M := rest.size()
	var n := PackedFloat64Array()
	n.resize(3 * M)
	var b := PackedFloat64Array()
	b.resize(M)
	var diag := PackedFloat64Array()
	diag.resize(M)
	var act: Array[bool] = []
	act.resize(M)
	for j in M:
		var dx := P[3 * j + 3] - P[3 * j]
		var dy := P[3 * j + 4] - P[3 * j + 1]
		var dz := P[3 * j + 5] - P[3 * j + 2]
		var L := sqrt(dx * dx + dy * dy + dz * dz)
		var Ls := maxf(L, 1e-12)
		n[3 * j] = dx / Ls
		n[3 * j + 1] = dy / Ls
		n[3 * j + 2] = dz / Ls
		# звено только тянет: сжатое звено без натяжения не участвует (кабель изгибается между узлами)
		act[j] = L - rest[j] > 0.0 or lam[j] < 0.0
		b[j] = -(L - rest[j]) - alpha[j] * lam[j] if act[j] else 0.0
		diag[j] = w[j] + w[j + 1] + alpha[j] if act[j] else 1.0
	var off := PackedFloat64Array()
	off.resize(maxi(M - 1, 0))
	for j in M - 1:
		if act[j] and act[j + 1]:
			off[j] = -w[j + 1] * (n[3 * j] * n[3 * j + 3] + n[3 * j + 1] * n[3 * j + 4] + n[3 * j + 2] * n[3 * j + 5])
		else:
			off[j] = 0.0
	var cp := PackedFloat64Array()
	cp.resize(M)
	var dp := PackedFloat64Array()
	dp.resize(M)
	cp[0] = off[0] / diag[0] if M > 1 else 0.0
	dp[0] = b[0] / diag[0]
	for j in range(1, M):
		var den := diag[j] - off[j - 1] * cp[j - 1]
		cp[j] = off[j] / den if j < M - 1 else 0.0
		dp[j] = (b[j] - off[j - 1] * dp[j - 1]) / den
	var dl := PackedFloat64Array()
	dl.resize(M)
	dl[M - 1] = dp[M - 1]
	for j in range(M - 2, -1, -1):
		dl[j] = dp[j] - cp[j] * dl[j + 1]
	for j in M:
		dl[j] = minf(dl[j], -lam[j])          # λ + Δλ ≤ 0: звено только тянет
		lam[j] += dl[j]
	# смещения: сначала все «минус» (как P[:-1] −= …), потом все «плюс» — тот же порядок, что в эталоне
	for j in M:
		for k in 3:
			P[3 * j + k] -= w[j] * dl[j] * n[3 * j + k]
	for j in M:
		for k in 3:
			P[3 * j + 3 + k] += w[j + 1] * dl[j] * n[3 * j + k]
