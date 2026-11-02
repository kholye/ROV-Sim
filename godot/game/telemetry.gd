class_name Telemetry
extends RefCounted
## Запись телеметрии заплыва в CSV (клавиша F9, значок ЗАП на экране): 10 строк в секунду,
## user://telemetry/<дата>.csv. Истинное состояние модели (NED, СИ) и то, что видит оператор
## (глубина с шумом датчика, цель, команды).

const PERIOD := 0.1
const HEADER := "t_s;north_m;east_m;depth_m;roll_deg;pitch_deg;heading_deg;u_ms;v_ms;w_ms;p_degs;q_degs;r_degs;" + \
		"tank1_ml;tank2_ml;thr_left;thr_right;tank1_cmd;tank2_cmd;depth_meas_m;depth_target_m;depth_hold;" + \
		"lamp;battery_v;battery_wh;dropped;emergency"

var path := ""
var started_at := 0.0
var _f: FileAccess
var _acc := 0.0


func active() -> bool:
	return _f != null


func start(now: float) -> void:
	DirAccess.make_dir_recursive_absolute("user://telemetry")
	path = "user://telemetry/" + Time.get_datetime_string_from_system().replace(":", "-") + ".csv"
	_f = FileAccess.open(path, FileAccess.WRITE)
	_f.store_line(HEADER)
	started_at = now
	_acc = PERIOD


func stop() -> void:
	if _f:
		_f.close()
	_f = null


func step(dt: float, r: Rov) -> void:
	if _f == null:
		return
	_acc += dt
	if _acc < PERIOD:
		return
	_acc -= PERIOD
	var x := r.x
	var row := PackedStringArray([
		"%.2f" % (r.time - started_at), "%.4f" % x[0], "%.4f" % x[1], "%.4f" % x[2],
		"%.3f" % rad_to_deg(x[3]), "%.3f" % rad_to_deg(x[4]), "%.3f" % r.heading_deg(),
		"%.4f" % x[6], "%.4f" % x[7], "%.4f" % x[8],
		"%.3f" % rad_to_deg(x[9]), "%.3f" % rad_to_deg(x[10]), "%.3f" % rad_to_deg(x[11]),
		"%.2f" % (x[12] * 1e6), "%.2f" % (x[13] * 1e6), "%.2f" % r.thr[0], "%.2f" % r.thr[1],
		str(r.tank_cmd[0]), str(r.tank_cmd[1]), "%.4f" % r.depth_meas, "%.3f" % r.depth_target, str(int(r.depth_hold)),
		"%.1f" % r.lamp_level, "%.2f" % r.battery_voltage(), "%.3f" % (r.battery.E / 3600.0),
		str(int(r.dropped)), str(int(r.emergency))])
	_f.store_line(";".join(row))
