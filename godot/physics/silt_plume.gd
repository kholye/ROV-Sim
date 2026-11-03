class_name SiltPlume
extends RefCounted
## Ил, поднятый струями движителей у дна: облако из гауссовых клубов. NED, СИ, без узлов.
## Порт physics_ref/rov/silt.py (там же описание цепочки; источники — docs/physics-sources.md, разд. 29):
## струя (теория импульса + круглая струя Albertson 1950) -> касательное напряжение на дне -> размыв
## Партениадеса -> клубы, которые несут течение и струи, растят вовлечение и вихревая диффузия, оседание в дно.

const EMIT_PERIOD := 0.3
const MAX_PUFFS := 8
const B_MIN := 1e-3
const KAPPA := 0.4
const N_X := 24
const N_Y := 13


class Puff:
	extends RefCounted
	var pos: PackedFloat64Array      # центр, NED
	var m := 0.0                     # кг
	var sh := 0.0                    # σ по горизонтали, м
	var sz := 0.0                    # σ по вертикали, м
	var bed := 0.0                   # глубина дна под клубом (отражение), м
	var age := 0.0

	func _init(pos_: PackedFloat64Array, m_: float, sh_: float, sz_: float, bed_: float, age_ := 0.0) -> void:
		pos = pos_.duplicate()
		m = m_
		sh = sh_
		sz = sz_
		bed = bed_
		age = age_

	func peak_c() -> float:
		return m / (pow(2.0 * PI, 1.5) * sh * sh * sz)


var p: Dictionary
var b_star := 500.0
var puffs: Array[Puff] = []
var pending := PackedFloat64Array([0, 0])
var pend_pos: Array[PackedFloat64Array] = [PackedFloat64Array([0, 0, 0]), PackedFloat64Array([0, 0, 0])]
var pend_s2 := PackedFloat64Array([0, 0])
var pend_sg := PackedFloat64Array([0, 0])
var pend_t := PackedFloat64Array([0, 0])
var eroded := 0.0
var deposited := 0.0
var removed := 0.0
var _A := 0.0
var box := PackedFloat64Array()        # стенки (бассейн): север мин, север макс, восток мин, восток макс; пусто — нет
var last: Array = [[0.0, PackedFloat64Array([0, 0, 0]), 0.0, 0.0], [0.0, PackedFloat64Array([0, 0, 0]), 0.0, 0.0]]
## ↑ последний размыв по струям (для частиц-хлопьев): [кг/с, центр NED, дисперсия по площади, толщина струи]


func _init(params: Dictionary, b_star_ := 500.0) -> void:
	p = params
	b_star = b_star_
	var D: float = p["thruster_duct_d"]
	_A = PI * D * D / 4.0


static func _mv(R: PackedFloat64Array, v: PackedFloat64Array) -> PackedFloat64Array:
	return PackedFloat64Array([R[0] * v[0] + R[1] * v[1] + R[2] * v[2],
			R[3] * v[0] + R[4] * v[1] + R[5] * v[2], R[6] * v[0] + R[7] * v[1] + R[8] * v[2]])


static func _dot(a: PackedFloat64Array, b: PackedFloat64Array) -> float:
	return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


static func _phi(s: float) -> float:
	return exp(-0.5 * s * s) / sqrt(2.0 * PI)


## Струи: [срез NED, направление NED, U0, D] или null для движителя без тяги (0 — левый, 1 — правый).
func jets(x: PackedFloat64Array, thr: PackedFloat64Array) -> Array:
	var R := RovDynamics.rot_nb(x[3], x[4], x[5])
	var tp: Array = p["thruster_pos"]
	var out := []
	for k in 2:
		var sgn := -1.0 if k == 0 else 1.0
		var s := clampf(thr[k], -1.0, 1.0)
		var T: float = float(p["thrust_max"]) * s * absf(s)
		if T < 0.0:
			T *= float(p["thrust_reverse_ratio"])
		if T == 0.0:
			out.append(null)
			continue
		var db := PackedFloat64Array([-signf(T), 0.0, 0.0])
		var half: float = float(p["thruster_duct_length"]) / 2.0
		var ob := PackedFloat64Array([float(tp[0]) + db[0] * half, sgn * float(tp[1]), float(tp[2])])
		var o := _mv(R, ob)
		for i in 3:
			o[i] += x[i]
		var U0 := sqrt(2.0 * absf(T) / (float(p["rho"]) * _A))
		out.append([o, _mv(R, db), U0, float(p["thruster_duct_d"])])
	return out


## Скорость на оси и σ на расстоянии xa от среза: [U_m, σ].
func axis_speed(xa: float, U0: float, D: float) -> Vector2:
	var core: float = float(p["jet_core"]) * D
	var Um := U0 if xa <= core else U0 * core / xa
	return Vector2(Um, maxf(float(p["jet_spread"]) * xa, D / 4.0))


## Скорость, наведённая струями в точке X (NED).
func jet_velocity(X: PackedFloat64Array, js: Array) -> PackedFloat64Array:
	var v := PackedFloat64Array([0, 0, 0])
	for j in js:
		if j == null:
			continue
		var o: PackedFloat64Array = j[0]
		var d: PackedFloat64Array = j[1]
		var rel := PackedFloat64Array([X[0] - o[0], X[1] - o[1], X[2] - o[2]])
		var xa := _dot(rel, d)
		if xa <= 0.0:
			continue
		var r2 := _dot(rel, rel) - xa * xa
		var us := axis_speed(xa, j[2], j[3])
		var u := us.x * exp(-r2 / (2.0 * us.y * us.y))
		for i in 3:
			v[i] += d[i] * u
	return v


## Размыв дна (глубина bed) одной струёй: [кг/с, центр размыва NED, дисперсия по площади м², толщина струи σ над
## размывом, м — сорванный ил сразу уходит в турбулентную струю и занимает её толщину].
func erosion(jet: Array, bed: float) -> Array:
	var o: PackedFloat64Array = jet[0]
	var d: PackedFloat64Array = jet[1]
	var nh := sqrt(d[0] * d[0] + d[1] * d[1])
	if nh < 1e-6:
		return [0.0, o, 0.0, 0.0]
	var e := Vector2(d[0] / nh, d[1] / nh)
	var n := Vector2(-e.y, e.x)
	var xs := PackedFloat64Array()
	for i in N_X:
		xs.append(0.05 * pow(100.0, float(i) / (N_X - 1)))      # geomspace(0,05; 5)
	var edges := PackedFloat64Array([0.0])
	for i in N_X - 1:
		edges.append(0.5 * (xs[i] + xs[i + 1]))
	edges.append(xs[N_X - 1] * 1.05)
	var rho: float = p["rho"]
	var cd: float = p["silt_cd_bed"]
	var tce: float = p["silt_tau_ce"]
	var M: float = p["silt_M"]
	var tot := 0.0
	var acc_sig := 0.0
	var acc := PackedFloat64Array([0, 0, 0])
	var pts := []
	for i in N_X:
		var xa := xs[i]
		var A := PackedFloat64Array([o[0] + d[0] * xa, o[1] + d[1] * xa, o[2] + d[2] * xa])
		var h := bed - A[2]
		if h < 0.0:
			break
		var us := axis_speed(xa, jet[2], jet[3])
		var sig := us.y
		var dy := 6.0 * sig / (N_Y - 1)
		for jy in N_Y:
			var y := -3.0 * sig + jy * dy
			var u := us.x * exp(-(h * h + y * y) / (2.0 * sig * sig))
			var tau := rho * cd * u * u
			var E := M * maxf(tau / tce - 1.0, 0.0)
			var dm := E * dy * (edges[i + 1] - edges[i]) * nh
			if dm > 0.0:
				var P := PackedFloat64Array([A[0] + n.x * y, A[1] + n.y * y, bed])
				pts.append([P, dm])
				tot += dm
				acc_sig += dm * sig
				for k in 3:
					acc[k] += dm * P[k]
	if tot <= 0.0:
		return [0.0, o, 0.0, 0.0]
	var c := PackedFloat64Array([acc[0] / tot, acc[1] / tot, acc[2] / tot])
	var acc2 := 0.0
	for q in pts:
		var P: PackedFloat64Array = q[0]
		acc2 += float(q[1]) * ((P[0] - c[0]) ** 2 + (P[1] - c[1]) ** 2 + (P[2] - c[2]) ** 2)
	return [tot, c, acc2 / tot, acc_sig / tot]


## Шаг dt: x — состояние аппарата (14), thr — команды движителей, beds — глубина дна под каждым движителем
## (NAN — дна нет), current — течение или null, h_site — глубина места для профиля течения.
func step(dt: float, x: PackedFloat64Array, thr: PackedFloat64Array, beds: PackedFloat64Array,
		current: RovEnvironment.Current = null, h_site := 0.0) -> void:
	var js := jets(x, thr)
	for k in 2:
		last[k] = [0.0, PackedFloat64Array([0, 0, 0]), 0.0, 0.0]
		if js[k] != null and not is_nan(beds[k]):
			var er := erosion(js[k], beds[k])
			last[k] = er
			var mdot: float = er[0]
			if mdot > 0.0:
				var dm := mdot * dt
				var w0 := pending[k]
				var c: PackedFloat64Array = er[1]
				var pp := pend_pos[k]
				for i in 3:
					pp[i] = (w0 * pp[i] + dm * c[i]) / (w0 + dm)
				pend_pos[k] = pp
				pend_s2[k] = (w0 * pend_s2[k] + dm * float(er[2])) / (w0 + dm)
				pend_sg[k] = (w0 * pend_sg[k] + dm * float(er[3])) / (w0 + dm)
				pending[k] += dm
				eroded += dm
		pend_t[k] += dt
		if pend_t[k] >= EMIT_PERIOD:
			pend_t[k] = 0.0
			if pending[k] > 0.0:
				var s0: float = p["silt_sigma0"]
				var sh := maxf(sqrt(pend_s2[k] / 2.0), s0)
				puffs.append(Puff.new(pend_pos[k], pending[k], sh, maxf(pend_sg[k], s0), pend_pos[k][2]))
				pending[k] = 0.0
				pend_s2[k] = 0.0
	var U := 0.0
	if current:
		var cv := current.velocity()
		U = sqrt(cv[0] * cv[0] + cv[1] * cv[1] + cv[2] * cv[2])
	var ustar := sqrt(float(p["silt_cd_current"])) * U
	var ws: float = p["silt_ws"]
	var spread: float = p["jet_spread"]
	var keep: Array[Puff] = []
	for f in puffs:
		var hgt := maxf(f.bed - f.pos[2], 0.0)
		var vc := current.velocity_at(hgt, h_site) if current else PackedFloat64Array([0, 0, 0])
		var vj := jet_velocity(f.pos, js)
		for i in 3:
			f.pos[i] += (vc[i] + vj[i]) * dt
		f.pos[2] = minf(f.pos[2] + ws * dt, f.bed)
		# турбулентность у дна: течение и струи над клубом (то же u у дна, что размывает ил)
		var vb := jet_velocity(PackedFloat64Array([f.pos[0], f.pos[1], f.bed]), js)
		var us := sqrt(ustar * ustar + float(p["silt_cd_bed"]) * _dot(vb, vb))
		var K := KAPPA * us * maxf(hgt + f.sz, 0.05)
		var grow := spread * sqrt(_dot(vj, vj)) * dt
		f.sh = sqrt((f.sh + grow) ** 2 + 2.0 * K * dt)
		f.sz = sqrt((f.sz + grow) ** 2 + 2.0 * K * dt)
		if box.size() == 4:
			_confine(f)
		hgt = maxf(f.bed - f.pos[2], 0.0)
		var lost := f.m * (1.0 - exp(-ws * 2.0 * _phi(hgt / f.sz) / f.sz * dt))
		f.m -= lost
		deposited += lost
		f.age += dt
		if f.peak_c() * 2.0 * b_star < B_MIN:
			removed += f.m
		else:
			keep.append(f)
	puffs = keep
	while puffs.size() > MAX_PUFFS:
		_merge_closest()


## Убрать клубы дальше radius (м, по горизонтали) от точки center (NED): ушли за пределы сцены.
func cull(center: PackedFloat64Array, radius: float) -> void:
	var keep: Array[Puff] = []
	for f in puffs:
		if Vector2(f.pos[0] - center[0], f.pos[1] - center[1]).length() > radius:
			removed += f.m
		else:
			keep.append(f)
	puffs = keep


## Концентрация ила в точке X (NED), кг/м³ (с отражением от дна).
func concentration(X: PackedFloat64Array) -> float:
	var c := 0.0
	for f in puffs:
		var norm := f.m / (pow(2.0 * PI, 1.5) * f.sh * f.sh * f.sz)
		var dh2 := (X[0] - f.pos[0]) ** 2 + (X[1] - f.pos[1]) ** 2
		for zc in [f.pos[2], 2.0 * f.bed - f.pos[2]]:
			c += norm * exp(-0.5 * (dh2 / (f.sh * f.sh) + (X[2] - zc) ** 2 / (f.sz * f.sz)))
	return c


func suspended() -> float:
	var s := pending[0] + pending[1]
	for f in puffs:
		s += f.m
	return s


## Бассейн: центр клуба не выходит за стенки, σ по горизонтали не больше половины ширины, по вертикали —
## половины глубины (грубо: ил остаётся в бассейне, отражения от стенок не считаются).
func _confine(f: Puff) -> void:
	f.pos[0] = clampf(f.pos[0], box[0], box[1])
	f.pos[1] = clampf(f.pos[1], box[2], box[3])
	f.sh = minf(f.sh, 0.5 * minf(box[1] - box[0], box[3] - box[2]))
	f.sz = minf(f.sz, 0.5 * f.bed)


func _merge_closest() -> void:
	var best := INF
	var bi := 0
	var bj := 1
	for i in puffs.size():
		for j in range(i + 1, puffs.size()):
			var a := puffs[i]
			var b := puffs[j]
			var d2 := ((a.pos[0] - b.pos[0]) ** 2 + (a.pos[1] - b.pos[1]) ** 2 + (a.pos[2] - b.pos[2]) ** 2) \
					/ (a.sh * a.sh + b.sh * b.sh + a.sz * a.sz + b.sz * b.sz)
			if d2 < best:
				best = d2
				bi = i
				bj = j
	puffs[bi] = merge(puffs[bi], puffs[bj])
	puffs.remove_at(bj)


## Один клуб с той же массой, центром масс и вторыми моментами (по горизонтали — среднее двух осей).
static func merge(a: Puff, b: Puff) -> Puff:
	var m := a.m + b.m
	var c := PackedFloat64Array()
	for i in 3:
		c.append((a.m * a.pos[i] + b.m * b.pos[i]) / m)
	var mh := 0.0
	var mz := 0.0
	for f in [a, b]:
		var dx: float = f.pos[0] - c[0]
		var dy: float = f.pos[1] - c[1]
		mh += f.m * (f.sh * f.sh + (dx * dx + dy * dy) / 2.0)
		mz += f.m * (f.sz * f.sz + (f.pos[2] - c[2]) ** 2)
	return Puff.new(c, m, sqrt(mh / m), sqrt(mz / m), (a.m * a.bed + b.m * b.bed) / m, (a.m * a.age + b.m * b.age) / m)
