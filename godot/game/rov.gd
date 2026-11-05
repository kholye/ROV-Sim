class_name Rov
extends Node3D
## Аппарат в игровой сцене: физика этапа 2 (RovDynamics, NED) + управление как на пульте
## (протокол пульта, docs/ui.md) + лампа для подводного света + камеры + столкновения.
## Это мост «движок <-> физика»: состояние живёт в NED, в Godot переводит только NedGodot.
##
## Управление как у пульта (game/pult_input.gd, docs/ui.md): правый стик / стрелки — ход и поворот,
## цистерны E/Q (обе), R/F (носовая), T/G (кормовая), H удержание глубины, PgUp/PgDn цель на шаг,
## [ ] шаг 10/50/100/500 мм, L лампа, X сброс груза и пробел аварийное всплытие (с подтверждением,
## как в пульте v7), C камера аппарата / вид сзади, F9 запись телеметрии.

signal touched(collider: Object)

const DT := 0.005                  # шаг физики, с (RK4, этап 2)
const TOUCH_PAUSE := 0.4           # пауза между касаниями, с (как в первой версии симулятора, Семенов Н. Н.)
const ROV_GLB := preload("res://assets/rov/rov.glb")

var p: Dictionary
var dyn: RovDynamics
var ctl: RovControl
var battery: RovEnvironment.Battery
var current: RovEnvironment.Current          # течение сцены (null — стоячая вода, бассейны)
var seabed_depth := 0.0                      # глубина места для профиля течения у дна, м
var ext_force := PackedFloat64Array()        # кабель-трос: [сила NED, Н; точка в осях тела, м] (game/tether.gd), пусто — нет
var x: PackedFloat64Array
var dropped := false
var thr := PackedFloat64Array([0.0, 0.0])
var ramp: ThrusterRamp                       # нарастание команды движителя, 100 % за 3 с (научный режим)
var thr_ramp := true                         # false — мгновенная команда (проверки, сравнение)
var tank_cmd := PackedInt32Array([0, 0])
var depth_hold := false
var depth_target := 0.0
var lamp_level := 0.5              # 0 / 0,5 / 1
var emergency := false
var depth_meas := 0.0              # глубина с шумом датчика давления: её видит оператор и ПИД
var step_i := 2                    # шаг цели глубины: PultInput.DEPTH_STEPS[step_i]
var confirm := ""                  # ждёт подтверждения: "drop" / "emergency" (повторное нажатие за 3 с)
var _confirm_t := 0.0
var notice := ""                   # короткое сообщение для экрана
var notice_t := -10.0
var power := 0.0                   # потребляемая мощность, Вт
var power_avg := 0.0               # сглаженная (10 с) для оценки оставшегося времени
var telemetry := Telemetry.new()
var time := 0.0
var touches := 0
var uw: Underwater
var light: LightModel              # та же модель света на процессоре: замер экспозиции, яркость взвеси
## Автоэкспозиция камеры: у DiCam 300 она есть (руководство пользователя, с. 9: поправка «Экспозиция» −3…+3 —
## поверх автоматики; процессор Allwinner V3 / HawkView). --fixed_exposure — постоянная camera_exposure (сравнение).
var auto_exposure := true
var exposure := 0.004
const AE_TARGET := 0.10            # средняя линейная яркость замера (≈ sRGB 89): тёмный стиль, оценка
const AE_TAU := 0.6                # постоянная подстройки, с
const AE_RANGE := Vector2(0.0005, 0.5)
var _ae_dt := 0.0
var _ae_frame := 0
var input_enabled := true
var autopilot: Callable            # для проверок: func(rov) -> [x, y] стика, -32768..32767
var kinematic := false             # только для автопроверки осмотра судна: положение задаётся извне, физики нет
## Режим управления (Settings «control», при создании аппарата): "science" — команды пульта как есть;
## "assist" — та же физика, помогает пульт: ход разгоняется плавно (SLEW); поворот задаёт скорость рыскания
## (до TURN_RATE), после отпускания пульт гасит вращение и держит курс, где аппарат остановился
## (неустойчивость корпуса по курсу, docs/verification-report.md, V1); глубина всегда на удержании
## (ПИД пульта), E / Q плавно ведут цель глубже / мельче (DEPTH_RATE), дифферент выравнивают цистерны по
## отдельности; "boost" — как assist, и насос цистерн ×BOOST_TANK, тяга ×BOOST_THRUST (не настоящий аппарат).
var control_mode := "science"
const SLEW := 1.6                  # доля полного хода в секунду (разгон вперёд от нуля до полного ≈ 0,6 с)
const HEADING_KP := 2.0            # удержание курса: доля тяги на радиан ошибки
const HEADING_KD := 1.5            # и на рад/с скорости рыскания
const TURN_RATE := 0.6             # рад/с (≈ 35°/с) при полном повороте
const RATE_K := 1.2                # доля тяги на рад/с ошибки скорости рыскания
const SETTLED := 0.08              # рад/с: вращение погашено — курс запоминается
const DEPTH_RATE := 0.25           # м/с: скорость цели глубины при E / Q
const TRIM_DEG := 2.0              # дифферент, при котором цистерны начинают выравнивать
const BOOST_TANK := 3.0
const BOOST_THRUST := 1.5
var _stick_f := Vector2.ZERO       # сглаженный стик, доли −1..1
var _psi_hold := 0.0
var _yaw_free := false             # поворот или ещё гасим вращение: курс не держим

var _ctl_acc := 0.0
var _touch_t := -10.0
var _rng := RandomNumberGenerator.new()
var _model: Node3D
var _body: CharacterBody3D             # не сталкивается: только мишень лучей (слой 2)
var cam_front: Camera3D
var lens: DicamLens            # объектив DiCam 300 в аквабоксе (табл. 7 Холопова, render/dicam_lens.gd)
var cam_chase: Camera3D
var _lamp_pos_body := PackedFloat64Array([0.33, 0.0, 0.0955])   # светодиоды лампы, NED тела (модель этапа 3)
var _cam_pos_body := PackedFloat64Array([0.40, 0.0, 0.0])       # перед объективом камеры
## Наклон камеры вниз (версия 1.4): у Дунаева (ВКР, описание аппарата, п. 2) угол наклона камеры можно менять;
## сам угол и пределы в данных не указаны — оценка: 0-30° шагом 5°, по умолчанию 20° (Settings «cam_tilt»).
## В пульте команды наклона нет; в игре — I / K (R3 геймпада по кругу).
const CAM_TILT_MAX := 30.0
const CAM_TILT_STEP := 5.0
var cam_tilt := 20.0


func setup(water: Underwater, depth: float, north: float, east: float, psi_deg: float) -> void:
	uw = water
	light = LightModel.new(uw)
	exposure = float(uw.p["camera_exposure"])
	Underwater.set_exposure(exposure)
	p = RovDynamics.load_params()
	control_mode = String(Settings.get_value("control"))
	if control_mode == "boost":
		p["tank_rate"] = float(p["tank_rate"]) * BOOST_TANK
		p["thrust_max"] = float(p["thrust_max"]) * BOOST_THRUST
	dyn = RovDynamics.new(p)
	PultInput.ensure_actions()
	var g: Array = Settings.get_value("pid")
	set_pid(g[0], g[1], g[2])
	battery = RovEnvironment.Battery.new(p)
	ramp = ThrusterRamp.new(p)
	x = RovDynamics.initial_state(depth, deg_to_rad(psi_deg))
	x[0] = north
	x[1] = east
	depth_meas = depth
	reset_control()
	_rng.seed = 7
	_model = ROV_GLB.instantiate()
	add_child(_model)
	uw.convert_tree(_model)
	cam_front = Camera3D.new()
	cam_front.position = NedGodot.vec(_cam_pos_body)
	cam_front.keep_aspect = Camera3D.KEEP_WIDTH
	lens = DicamLens.new(uw.p)
	cam_front.fov = rad_to_deg(2.0 * lens.half_water())   # прямолинейный кадр; проекцию объектива даёт LensPass
	cam_front.near = 0.02
	cam_front.far = 60.0
	add_child(cam_front)
	set_cam_tilt(float(Settings.get_value("cam_tilt")))
	cam_chase = Camera3D.new()
	cam_chase.position = Vector3(0, 0.35, 1.3)
	cam_chase.rotation = Vector3(deg_to_rad(-12), 0, 0)
	cam_chase.fov = 70.0
	cam_chase.near = 0.05
	cam_chase.far = 60.0
	add_child(cam_chase)
	cam_front.current = true
	# «бесконечная» вода вокруг аппарата
	var vol := MeshInstance3D.new()
	var sm := SphereMesh.new()
	sm.radius = 50.0
	sm.height = 100.0
	sm.radial_segments = 16
	sm.rings = 8
	vol.mesh = sm
	vol.material_override = Underwater.volume_material()
	vol.top_level = true
	vol.name = "WaterVolume"
	add_child(vol)
	for c in p["contact_points"]:
		_contact_pts.append(PackedFloat64Array(c))
	# корпус-коробка для лучей других систем (слой 2): габарит модели 765 × 282 × 240 мм, середина габарита
	# (17,5; 0; 49) мм в осях тела (по точкам касания) — столкновения считает модель касания
	_body = CharacterBody3D.new()
	_body.top_level = true
	_body.collision_layer = 2
	_body.collision_mask = 1
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(0.282, 0.24, 0.765)
	cs.shape = box
	cs.position = NedGodot.vec(PackedFloat64Array([0.0175, 0.0, 0.049]))
	_body.add_child(cs)
	add_child(_body)
	_sync()


## После постановки аппарата (старт, «на старт», --at): цель глубины = текущая глубина, курс держится текущий;
## в режимах автопилота удержание глубины сразу включено.
func reset_control() -> void:
	depth_target = x[2]
	depth_hold = control_mode != "science"
	_psi_hold = x[5]
	_yaw_free = false
	_stick_f = Vector2.ZERO


func depth() -> float:
	return x[2]


func heading_deg() -> float:
	return fposmod(rad_to_deg(x[5]), 360.0)


## Скорость течения (NED) на глубине depth_m: профиль у дна (RovEnvironment.bed_profile).
func water_velocity(depth_m: float) -> PackedFloat64Array:
	if current == null:
		return PackedFloat64Array([0, 0, 0])
	return current.velocity_at(seabed_depth - depth_m, seabed_depth)


func position_ned() -> PackedFloat64Array:
	return x.slice(0, 3)


func camera() -> Camera3D:
	return cam_front if cam_front.current else cam_chase


## Команда n пульта: Kp, Kd, Ki в шкале 0,0-9,9 (RovControl квантует с шагом 0,1).
func set_pid(kp: float, kd: float, ki: float) -> void:
	ctl = RovControl.new(p, kp, ki, kd)


## Наклон камеры аппарата вниз, ° (0..CAM_TILT_MAX): поворот камеры вокруг поперечной оси тела.
func set_cam_tilt(deg: float) -> void:
	cam_tilt = clampf(deg, 0.0, CAM_TILT_MAX)
	cam_front.rotation = Vector3(-deg_to_rad(cam_tilt), 0.0, 0.0)


func say(t: String) -> void:
	notice = t
	notice_t = time


func battery_voltage() -> float:
	return battery.voltage(power)


## Оставшееся время работы, с, при средней мощности последних секунд.
func battery_time_left() -> float:
	return battery.E / maxf(power_avg, 1.0)


func _unhandled_input(ev: InputEvent) -> void:
	if not input_enabled or not ev.is_pressed() or ev.is_echo():
		return
	if ev.is_action("depth_hold"):
		depth_hold = not depth_hold
		depth_target = snappedf(depth_meas, 0.001)    # цель в мм, как в пульте
		say("удержание глубины %s" % ("ВКЛ, цель %.3f м" % depth_target if depth_hold else "ВЫКЛ"))
	elif ev.is_action("target_up") or ev.is_action("target_down"):
		var st: float = PultInput.DEPTH_STEPS[step_i]
		depth_target = maxf(depth_target + (st if ev.is_action("target_down") else -st), 0.0)
		say("цель глубины %.3f м" % depth_target)
	elif ev.is_action("step_prev") or ev.is_action("step_next"):
		step_i = clampi(step_i + (1 if ev.is_action("step_next") else -1), 0, PultInput.DEPTH_STEPS.size() - 1)
		say("шаг цели %d мм" % roundi(PultInput.DEPTH_STEPS[step_i] * 1000))
	elif ev.is_action("lamp"):
		lamp_level = {0.0: 0.5, 0.5: 1.0, 1.0: 0.0}[lamp_level]
		say("лампа %d %%" % roundi(lamp_level * 100))
	elif ev.is_action("drop"):
		if dropped:
			say("груз уже сброшен")
		elif _ask("drop", "СБРОСИТЬ ГРУЗ 1 кг? X ещё раз"):
			dropped = true
			say("груз сброшен")
	elif ev.is_action("emergency"):
		if emergency:
			emergency = false
			say("аварийное всплытие отменено")
		elif _ask("emergency", "АВАРИЙНОЕ ВСПЛЫТИЕ? пробел ещё раз"):
			emergency = true
			depth_hold = false
			say("АВАРИЙНОЕ ВСПЛЫТИЕ: цистерны осушаются")
	elif ev.is_action("cam_up") or ev.is_action("cam_down"):
		var d := -CAM_TILT_STEP if ev.is_action("cam_up") else CAM_TILT_STEP
		if ev is InputEventJoypadButton and cam_tilt >= CAM_TILT_MAX:   # R3 — по кругу 0..30°
			d = -cam_tilt
		set_cam_tilt(cam_tilt + d)
		Settings.set_value("cam_tilt", cam_tilt)
		say("наклон камеры %d° вниз" % roundi(cam_tilt))
	elif ev.is_action("cam_swap"):
		cam_chase.current = cam_front.current
		cam_front.current = not cam_chase.current
	elif ev.is_action("record"):
		if telemetry.active():
			telemetry.stop()
			say("запись остановлена: " + ProjectSettings.globalize_path(telemetry.path))
		else:
			telemetry.start(time)
			say("запись телеметрии")


## Подтверждение опасной команды, как диалоги пульта v7: второе нажатие за 3 с.
func _ask(what: String, question: String) -> bool:
	if confirm == what and time - _confirm_t < 3.0:
		confirm = ""
		return true
	confirm = what
	_confirm_t = time
	say(question)
	return false


func _stick() -> Vector2i:
	if autopilot.is_valid():
		var s: Array = autopilot.call(self)
		return Vector2i(s[0], s[1])
	if not input_enabled:
		return Vector2i.ZERO
	return PultInput.poll_stick()


func _tank_command() -> PackedInt32Array:
	if emergency:
		return PackedInt32Array([-1, -1])
	if control_mode != "science" and input_enabled:
		var manual := PultInput.poll_tanks()
		if (manual[0] != 0 or manual[1] != 0) and not (Input.is_action_pressed("tank_both_fill")
				or Input.is_action_pressed("tank_both_empty")):
			return manual                          # отдельная цистерна вручную (R/F, T/G) — как в научном режиме
	if depth_hold:
		var c := ctl.update(depth_target, depth_meas)
		if control_mode != "science":
			return _trim(c)
		return PackedInt32Array([c, c])
	if not input_enabled:
		return PackedInt32Array([0, 0])
	return PultInput.poll_tanks()


func _physics_process(delta: float) -> void:
	if dyn == null:
		return
	if kinematic:
		time += delta
		_sync()
		meter_exposure(delta if time > 0.1 else 10.0)
		return
	var st := _stick()
	if control_mode != "science" and not autopilot.is_valid():
		st = _assist(st, delta)
	var m := RovControl.joystick_to_motors(st.x, st.y)
	thr = PackedFloat64Array([m[0] / 100.0, m[1] / 100.0])
	if control_mode == "science" and not autopilot.is_valid() and thr_ramp:
		thr = ramp.step(delta, thr)          # как прошивка: 100 % за 3 с (Павлов, прил. А)
	else:
		ramp.s = thr.duplicate()             # режимы с помощью и автопилот сами сглаживают команды
	if battery.E <= 0.0:
		thr = PackedFloat64Array([0.0, 0.0])
		ramp.reset()
	_find_contacts()
	var n := maxi(1, roundi(delta / DT))
	var h := delta / n
	for i in n:
		_ctl_acc += h
		if _ctl_acc >= float(p["control_period"]):     # команды пульта 10 Гц (такт этапа 2)
			_ctl_acc -= float(p["control_period"])
			depth_meas = depth() + float(p["depth_noise_sigma"]) * _rng.randfn()
			tank_cmd = _tank_command()
		if current:
			current.step(h)
		x = dyn.rk4_step(x, h, thr, tank_cmd, water_velocity(x[2]), dropped, ext_force, contacts)
		power = battery.step(h, thr, tank_cmd, lamp_level / 0.5)   # 7,2 Вт при 50 % (Холопов 3.1.2), ∝ уровню
	power_avg += (power - power_avg) * (1.0 - exp(-delta / 10.0)) if time > 0.0 else power - power_avg
	time += delta
	telemetry.step(delta, self)
	if confirm != "" and time - _confirm_t > 3.0:
		confirm = ""
	_touch_check()
	_sync()
	meter_exposure(delta if time > 0.1 else 10.0)


## Помощь пульта (режимы assist / boost): цель глубины по E / Q, удержание курса без команды поворота,
## плавный разгон. Возвращает стик в единицах пульта.
func _assist(st: Vector2i, delta: float) -> Vector2i:
	if input_enabled:
		var dz := 0.0
		if Input.is_action_pressed("tank_both_fill"):
			dz += DEPTH_RATE * delta
		if Input.is_action_pressed("tank_both_empty"):
			dz -= DEPTH_RATE * delta
		if dz != 0.0:
			depth_hold = true
			depth_target = maxf(depth_target + dz, 0.0)
	var want := Vector2(_unzone(st.x), _unzone(st.y))      # доля хода за мёртвой зоной пульта, −1..1
	var u := 0.0                                    # нужная доля тяги на поворот
	if absf(want.x) > 0.05:                         # поворот: держим скорость рыскания
		_yaw_free = true
		u = RATE_K * (want.x * TURN_RATE - x[11])
	elif _yaw_free:                                 # отпустили: гасим вращение, курс запомним, когда встанет
		u = -RATE_K * x[11]
		if absf(x[11]) < SETTLED:
			_yaw_free = false
			_psi_hold = x[5]
	else:                                           # держим курс
		u = HEADING_KP * wrapf(_psi_hold - x[5], -PI, PI) - HEADING_KD * x[11]
	u = clampf(u, -1.0, 1.0)
	want.x = signf(u) * sqrt(absf(u))               # тяга движителя ∝ стик·|стик| (RovDynamics): обратное
	_stick_f.x = want.x                             # поворот сглаживает сам регулятор скорости рыскания
	_stick_f.y = move_toward(_stick_f.y, want.y, SLEW * delta)
	return Vector2i(_zone(_stick_f.x), _zone(_stick_f.y))


## Стик пульта ↔ доля хода: мёртвая зона ±15000 (RovControl), за ней линейно до ±32767.
const ZONE := 15000


static func _unzone(a: int) -> float:
	return 0.0 if absi(a) < ZONE else clampf((a - ZONE * signi(a)) / float(32768 - ZONE), -1.0, 1.0)


static func _zone(n: float) -> int:
	return 0 if absf(n) < 0.004 else clampi(roundi(signf(n) * (ZONE + absf(n) * (32768 - ZONE))), -32768, 32767)


## Удержание глубины с выравниванием дифферента: команда ПИД c обеим цистернам, при дифференте больше
## TRIM_DEG носовая и кормовая получают разные команды (нос вверх — носовую наполнить, кормовую осушить).
func _trim(c: int) -> PackedInt32Array:
	var th := rad_to_deg(x[4])
	if absf(th) < TRIM_DEG:
		return PackedInt32Array([c, c])
	var d := 1 if th > 0.0 else -1
	return PackedInt32Array([clampi(c + d, -1, 1), clampi(c - d, -1, 1)])


## Касание (physics/rov_contact.gd, docs/physics-sources.md, разд. 31): раз в кадр от середины аппарата к каждой
## точке корпуса (contact_points) идёт луч с запасом CONTACT_MARGIN за точку; попадание даёт местную плоскость
## препятствия (точка, нормаль), её сила считается внутри шагов RK4. Луч из середины не проскакивает тонкую
## стену или дно, даже если точка уже за ними.
const CONTACT_MARGIN := 0.1        # м: за кадр (1/60 с) аппарат проходит меньше 3 см
var contacts := PackedFloat64Array()   # плоскости касания этого кадра (RovContact, по 9 чисел на точку)
var _contact_pts: Array = []
var _contact_hit: Array = []        # препятствие у каждой плоскости (для touched)
var _touching := {}                 # препятствия, которых корпус касался в прошлом кадре


func _find_contacts() -> void:
	contacts = PackedFloat64Array()
	_contact_hit.clear()
	if not is_inside_tree():
		return
	var space := get_world_3d().direct_space_state
	var R := RovDynamics.rot_nb(x[3], x[4], x[5])
	var c := NedGodot.position(x)
	for r: PackedFloat64Array in _contact_pts:
		var pw := NedGodot.vec(RovContact.point_ned(x, R, r))
		var d := pw - c
		var q := PhysicsRayQueryParameters3D.create(c, pw + d.normalized() * CONTACT_MARGIN, 1)
		q.hit_back_faces = false
		var hit := space.intersect_ray(q)
		if hit.is_empty():
			continue
		var S := NedGodot.vec_to_ned(hit["position"])
		var n := NedGodot.vec_to_ned(hit["normal"])
		contacts.append_array(r)
		contacts.append_array(S)
		contacts.append_array(n)
		_contact_hit.append(hit["collider"])


## После шага: какие препятствия корпус касается сейчас; новое касание — сигнал touched (как вход в
## столкновение в первой версии симулятора) с паузой TOUCH_PAUSE.
func _touch_check() -> void:
	var now := {}
	var R := RovDynamics.rot_nb(x[3], x[4], x[5])
	for i in _contact_hit.size():
		var b := i * 9
		var P := RovContact.point_ned(x, R, contacts.slice(b, b + 3))
		var d := (contacts[b + 3] - P[0]) * contacts[b + 6] + (contacts[b + 4] - P[1]) * contacts[b + 7] 				+ (contacts[b + 5] - P[2]) * contacts[b + 8]
		if d > 0.0:
			now[_contact_hit[i]] = true
	for col in now:
		if not _touching.has(col) and time - _touch_t > TOUCH_PAUSE:
			_touch_t = time
			touches += 1
			touched.emit(col)
	_touching = now


func _sync() -> void:
	transform = NedGodot.transform(x)
	_body.global_transform = Transform3D(NedGodot.basis(x), NedGodot.position(x))
	if uw:
		var lp := to_global(NedGodot.vec(_lamp_pos_body))
		var fwd := -global_transform.basis.z
		var I: Vector3 = uw.lamp_intensity("own", lamp_level) if lamp_level > 0.0 and battery.E > 0.0 else Vector3.ZERO
		Underwater.set_lamp(lp, fwd, I)
		if light:
			light.lamp_pos = lp
			light.lamp_dir = fwd
			light.lamp_i = I
	var vol := get_node_or_null("WaterVolume") as Node3D
	if vol:
		vol.global_position = global_position


## Автоэкспозиция: 9 лучей по сетке 3 × 3 кадра (центр с весом 2), яркость точки попадания по модели
## света (альбедо серое 0,15), промах = вода до 30 м. Экспозиция подстраивается в логарифме с AE_TAU.
func meter_exposure(dt: float) -> void:
	if not auto_exposure or light == null or not is_inside_tree():
		return
	_ae_dt += dt
	_ae_frame += 1
	if _ae_frame % 3 != 1 and dt < 1.0:       # замер раз в 3 кадра физики (экономия процессора)
		return
	dt = _ae_dt
	_ae_dt = 0.0
	var cam := get_viewport().get_camera_3d()      # активная камера (аппарата, сзади или обзорная)
	var lum := metered_luminance(cam, get_viewport().get_visible_rect().size)
	var target := clampf(AE_TARGET / maxf(lum, 1e-6), AE_RANGE.x, AE_RANGE.y)
	exposure *= pow(target / exposure, 1.0 - exp(-dt / AE_TAU))
	Underwater.set_exposure(exposure)


## Средняя яркость кадра камеры по модели света: 9 лучей по сетке 3 × 3 (центр с весом 2), альбедо
## серое 0,15, промах = вода до 30 м. mask: слои столкновений (1 сцена, 2 корпус аппарата).
func metered_luminance(cam: Camera3D, vp: Vector2, mask := 1) -> float:
	var space := get_world_3d().direct_space_state
	var sum := 0.0
	var wsum := 0.0
	for j in 3:
		for i in 3:
			var sp := Vector2((i + 0.5) / 3.0, (j + 0.5) / 3.0) * vp
			var o := cam.project_ray_origin(sp)
			var d := cam.project_ray_normal(sp)
			var q := PhysicsRayQueryParameters3D.create(o, o + d * 30.0, mask)
			var hit := space.intersect_ray(q)
			var L: Vector3
			if hit.is_empty():
				L = light.radiance(o, o + d * 30.0, Vector3.UP, Vector3.ZERO)
			else:
				L = light.radiance(o, hit["position"], hit["normal"], Vector3(0.15, 0.15, 0.15))
			var w := 2.0 if i == 1 and j == 1 else 1.0
			sum += w * (0.299 * L.x + 0.587 * L.y + 0.114 * L.z)
			wsum += w
	return sum / wsum
