class_name PultInput
extends RefCounted
## Управление как у пульта на MATLAB в режиме «Джойстик» (протокол пульта, docs/ui.md): геймпад Xbox
## (XInput) и клавиатура переводятся в те же команды, что уходят в аппарат.
##   правый стик            -> ход и поворот: микширование L = y + x, R = y − x, зона 15000 (RovControl)
##   крестовина ↑/↓ + LT/RT -> команды цистерн u/d, LT = цистерна 1 (носовая, оценка), RT = цистерна 2
##   B                      -> удержание глубины (h), Y / A -> цель мельче / глубже на шаг,
##   крестовина ←/→         -> шаг цели 10 / 50 / 100 / 500 мм (как в пульте)
##   LB                     -> свет (L)
## Клавиатура повторяет геймпад (ход и поворот: WASD или стрелки); клавиши интерфейса (окошко, фильтры,
## графики) к пульту не относятся.
## Смысл u/d пульта по исходникам не определён: принято u = набрать воду (аппарат тяжелеет), оценка.

const STICK_MAX := 32767
const DEPTH_STEPS := [0.010, 0.050, 0.100, 0.500]     # м, шаги цели глубины пульта (мм в кадре)

## Действия и клавиши по умолчанию. Геймпад добавляется в ensure_actions().
const KEYS := {
	"rov_fwd": [KEY_W, KEY_UP], "rov_back": [KEY_S, KEY_DOWN], "rov_left": [KEY_A, KEY_LEFT], "rov_right": [KEY_D, KEY_RIGHT],
	"tank_both_fill": [KEY_E], "tank_both_empty": [KEY_Q],
	"tank1_fill": [KEY_R], "tank1_empty": [KEY_F],
	"tank2_fill": [KEY_T], "tank2_empty": [KEY_G],
	"depth_hold": [KEY_H], "target_up": [KEY_PAGEUP], "target_down": [KEY_PAGEDOWN],
	"step_prev": [KEY_BRACKETLEFT], "step_next": [KEY_BRACKETRIGHT],
	"lamp": [KEY_L], "drop": [KEY_X], "emergency": [KEY_SPACE],
	"cam_swap": [KEY_C], "pip": [KEY_V], "cam_up": [KEY_I], "cam_down": [KEY_K],
	"help": [KEY_F1], "graph": [KEY_F2], "forces": [KEY_F3], "light_curve": [KEY_F4], "record": [KEY_F9], "photo": [KEY_F12],
	"pause": [KEY_ESCAPE], "start_run": [KEY_ENTER, KEY_KP_ENTER], "reset_run": [KEY_BACKSPACE],
}
const PADS := {
	"depth_hold": JOY_BUTTON_B, "target_up": JOY_BUTTON_Y, "target_down": JOY_BUTTON_A,
	"step_prev": JOY_BUTTON_DPAD_LEFT, "step_next": JOY_BUTTON_DPAD_RIGHT, "lamp": JOY_BUTTON_LEFT_SHOULDER,
	"pip": JOY_BUTTON_BACK, "pause": JOY_BUTTON_START, "cam_down": JOY_BUTTON_RIGHT_STICK,
}


## Создать действия в InputMap (один раз за запуск). Shift+V (камера окошка) отдельно: «pip_cam».
static func ensure_actions() -> void:
	if InputMap.has_action("rov_fwd"):
		return
	for a in KEYS:
		InputMap.add_action(a)
		for k in KEYS[a]:
			var e := InputEventKey.new()
			e.physical_keycode = k
			InputMap.action_add_event(a, e)
		if PADS.has(a):
			var j := InputEventJoypadButton.new()
			j.button_index = PADS[a]
			InputMap.action_add_event(a, j)
	InputMap.add_action("pip_cam")
	var sv := InputEventKey.new()
	sv.physical_keycode = KEY_V
	sv.shift_pressed = true
	InputMap.action_add_event("pip_cam", sv)


## Клавиши хода (WASD / стрелки) = стик до упора (±32767), как полное отклонение правого стика.
static func keyboard_stick(fwd: bool, back: bool, left: bool, right: bool) -> Vector2i:
	return Vector2i((STICK_MAX if right else 0) - (STICK_MAX if left else 0),
			(STICK_MAX if fwd else 0) - (STICK_MAX if back else 0))


## Ось геймпада Godot (−1..1, Y вниз) -> значение XInput (−32768..32767, Y вверх), как читает пульт.
static func pad_stick(ax: float, ay: float) -> Vector2i:
	return Vector2i(clampi(roundi(ax * STICK_MAX), -32768, STICK_MAX), clampi(roundi(-ay * STICK_MAX), -32768, STICK_MAX))


## Команда цистерн как в кадре пульта: u (+1) / d (−1) / стоп (0) для [цистерна 1, цистерна 2].
## sel1 / sel2 — LT / RT (на клавиатуре выбор задаёт сама клавиша). up = u, down = d.
static func tank_command(up: bool, down: bool, sel1: bool, sel2: bool) -> PackedInt32Array:
	var c := 0
	if up != down:
		c = 1 if up else -1
	return PackedInt32Array([c if sel1 else 0, c if sel2 else 0])


## Стик за этот кадр: геймпад, если отклонён за зону пульта, иначе клавиатура.
static func poll_stick() -> Vector2i:
	var k := keyboard_stick(Input.is_action_pressed("rov_fwd"), Input.is_action_pressed("rov_back"),
			Input.is_action_pressed("rov_left"), Input.is_action_pressed("rov_right"))
	for dev in Input.get_connected_joypads():
		var s := pad_stick(Input.get_joy_axis(dev, JOY_AXIS_RIGHT_X), Input.get_joy_axis(dev, JOY_AXIS_RIGHT_Y))
		if absi(s.x) >= 15000 or absi(s.y) >= 15000:
			return s
	return k


## Команда цистерн за этот такт: клавиатура (E/Q обе, R/F носовая, T/G кормовая) или геймпад
## (крестовина ↑/↓ с LT и/или RT: без курков пульт цистернам ничего не шлёт).
static func poll_tanks() -> PackedInt32Array:
	if Input.is_action_pressed("tank_both_fill"): return tank_command(true, false, true, true)
	if Input.is_action_pressed("tank_both_empty"): return tank_command(false, true, true, true)
	if Input.is_action_pressed("tank1_fill"): return tank_command(true, false, true, false)
	if Input.is_action_pressed("tank1_empty"): return tank_command(false, true, true, false)
	if Input.is_action_pressed("tank2_fill"): return tank_command(true, false, false, true)
	if Input.is_action_pressed("tank2_empty"): return tank_command(false, true, false, true)
	for dev in Input.get_connected_joypads():
		var up := Input.is_joy_button_pressed(dev, JOY_BUTTON_DPAD_UP)
		var down := Input.is_joy_button_pressed(dev, JOY_BUTTON_DPAD_DOWN)
		if up or down:
			return tank_command(up, down, Input.get_joy_axis(dev, JOY_AXIS_TRIGGER_LEFT) > 0.5,
					Input.get_joy_axis(dev, JOY_AXIS_TRIGGER_RIGHT) > 0.5)
	return PackedInt32Array([0, 0])
