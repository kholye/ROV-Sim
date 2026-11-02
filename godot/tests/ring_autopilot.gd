extends RefCounted
## Автопилот проверки «кольца проходятся» (не игровой режим АНПА, тот на этапе 7):
## глубина держится ПИД пульта на цистернах (цель = глубина кольца), курс и ход через стик пульта.
## Путь: точка 2 м перед кольцом по его оси, затем 1,2 м за кольцом. Проход только при ошибке глубины
## меньше просвет/2 − 0,22 м (полувысота корпуса 0,12 + запас); при касании отход и новый заход.

var rov: Rov
var ring := 0
var phase := 0          # 0 подход к точке перед кольцом, 1 проход
var _touches := 0


func attach(r: Rov) -> void:
	rov = r
	rov.depth_hold = true
	rov.depth_target = RingCourse.LAYOUT[0][2]


static func _raw(u: float) -> int:
	if absf(u) < 1e-3:
		return 0
	return int(signf(u) * (15001.0 + clampf(absf(u), 0.0, 1.0) * (32767.0 - 15001.0)))


func stick(r: Rov) -> Array:
	if ring >= RingCourse.LAYOUT.size():
		return [0, 0]
	var c := RingCourse.center(ring)
	var a := RingCourse.axis(ring)
	if r.touches != _touches:
		_touches = r.touches
		phase = 0
	var off := -2.0 if phase == 0 else 1.2
	var tx := c[0] + a[0] * off
	var ty := c[1] + a[1] * off
	var dx := tx - r.x[0]
	var dy := ty - r.x[1]
	var dist := sqrt(dx * dx + dy * dy)
	r.depth_target = c[2]
	var tol := maxf(float(RingCourse.LAYOUT[ring][4]) / 2.0 - 0.22, 0.05)
	if phase == 0 and dist < 0.2:
		phase = 1
	if phase == 1 and RingCourse.side(ring, r.position_ned()) > 0.6:
		ring += 1
		phase = 0
		return [0, 0]
	var want := atan2(dy, dx)
	var e := wrapf(want - r.x[5], -PI, PI)
	var turn := clampf(1.6 * e - 1.2 * r.x[11], -1.0, 1.0)
	var depth_err := absf(r.depth() - c[2])
	var fwd := clampf(dist * 0.8, 0.0, 0.7) * clampf(1.0 - absf(e) / 0.6, 0.0, 1.0)
	if phase == 1 and depth_err > tol:
		fwd = 0.0                      # ждём глубину перед проходом
	elif depth_err > 0.6:
		fwd *= 0.3
	if fwd < 0.05 and absf(r.x[6]) > 0.05:
		fwd = -0.3 * signf(r.x[6])     # гасим ход
	return [_raw(turn * 0.8), _raw(fwd)]
