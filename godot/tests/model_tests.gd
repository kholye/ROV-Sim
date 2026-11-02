extends SceneTree
## Проверки модели аппарата (этап 3) в Godot без окна:
##   Godot_console --headless --path godot --script res://tests/model_tests.gd
## 1) все названные части на месте; 2) габарит корпуса 650 × 140 мм (допуск 1 мм);
## 3) метки ЦМ/ЦВ, движители, плоскости, цистерны стоят там, где их ждёт физика
##    (rov_params.json через NedGodot.vec, допуск 1 мм);
## 4) вытесненный объём сетки = объём, который считает физика (mass_dry/rho + V_n), допуск 1 %.

const GLB := "res://assets/rov/rov.glb"
const PARAMS := "res://physics/rov_params.json"
const TOL := 0.001

var failures := 0


func check(name: String, ok: bool) -> void:
	print(("OK   " if ok else "FAIL ") + name)
	if not ok:
		failures += 1


func near(a: Vector3, b: Vector3) -> bool:
	return a.distance_to(b) <= TOL


## Объём замкнутой сетки в мировых координатах: сумма тетраэдров с вершиной в начале координат.
func mesh_volume(m: MeshInstance3D) -> float:
	var v := 0.0
	var xf := m.global_transform
	for s in m.mesh.get_surface_count():
		var arr := m.mesh.surface_get_arrays(s)
		var pts: PackedVector3Array = arr[Mesh.ARRAY_VERTEX]
		var idx: PackedInt32Array = arr[Mesh.ARRAY_INDEX]
		for i in range(0, idx.size(), 3):
			var a := xf * pts[idx[i]]
			var b := xf * pts[idx[i + 1]]
			var c := xf * pts[idx[i + 2]]
			v += a.dot(b.cross(c)) / 6.0
	return absf(v)


func ned(arr: Array) -> Vector3:
	return NedGodot.vec(PackedFloat64Array(arr))


var model: Node3D


func _initialize() -> void:
	model = (load(GLB) as PackedScene).instantiate()
	root.add_child(model)


## Глобальные координаты доступны, когда модель уже в дереве: проверяем на первом кадре.
func _process(_delta: float) -> bool:
	run()
	return true


func run() -> void:
	var p: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(PARAMS))

	var names := ["ROV", "thruster_L", "thruster_R", "thruster_L_prop", "thruster_R_prop",
			"tank_bow", "tank_stern", "lamp", "lamp_emitter", "camera", "camera_eye",
			"fin_L", "fin_R", "CG", "CB", "ballast_drop", "hull_main_tube", "lower_tube"]
	var nodes := {}
	for n in names:
		nodes[n] = model.find_child(n, true, false)
		check("часть есть: " + n, nodes[n] != null)
	if failures > 0:
		quit(1)
		return

	# Габарит корпуса: объединение AABB деталей hull_*
	var box := AABB()
	var first := true
	var tris := 0
	for mi in model.find_children("*", "MeshInstance3D", true, false):
		var m := mi as MeshInstance3D
		for s in m.mesh.get_surface_count():
			tris += m.mesh.surface_get_arrays(s)[Mesh.ARRAY_INDEX].size() / 3
		if not m.name.begins_with("hull_"):
			continue
		var b := m.global_transform * m.get_aabb()
		box = b if first else box.merge(b)
		first = false
	print("габарит корпуса, мм: X %.2f  Y %.2f  Z %.2f; треугольников %d"
			% [box.size.x * 1e3, box.size.y * 1e3, box.size.z * 1e3, tris])
	check("длина корпуса 650 ± 1 мм (вдоль Z)", absf(box.size.z - 0.65) <= TOL)
	check("диаметр корпуса 140 ± 1 мм (X)", absf(box.size.x - 0.14) <= TOL)
	check("диаметр корпуса 140 ± 1 мм (Y)", absf(box.size.y - 0.14) <= TOL)
	check("нос смотрит в -Z (камера впереди)",
			(nodes["camera_eye"] as Node3D).global_position.z < box.position.z + 0.001)
	check("треугольников 10000-16000 (цель 10-15 тыс.)", tris >= 10000 and tris <= 16000)

	# Совпадение с конфигом физики
	var v = func(n: String) -> Vector3: return (nodes[n] as Node3D).global_position
	check("ЦМ = cg_dry", near(v.call("CG"), ned(p["cg_dry"]["value"])))
	check("ЦВ = cb", near(v.call("CB"), ned(p["cb"]["value"])))
	var tp: Array = p["thruster_pos"]["value"]
	check("правый движитель = thruster_pos", near(v.call("thruster_R"), ned(tp)))
	check("левый движитель = thruster_pos (зеркально)",
			near(v.call("thruster_L"), ned([tp[0], -tp[1], tp[2]])))
	var tx: Array = p["tank_x"]["value"]
	check("носовая цистерна = tank_x[0]", near(v.call("tank_bow"), ned([tx[0], 0, 0])))
	check("кормовая цистерна = tank_x[1]", near(v.call("tank_stern"), ned([tx[1], 0, 0])))

	# Плоскости: центр площади трапеции и площадь пары против носовых плоскостей в fins
	var fin_area := 0.0
	var fin0: Dictionary = {}
	for f in p["fins"]["value"]:
		if String(f["name"]).begins_with("носовая"):
			fin_area += float(f["area"])
			fin0 = f
	var fb := (nodes["fin_R"] as MeshInstance3D)
	var fa := fb.global_transform * fb.get_aabb()
	var cx := -(fa.position.z + fa.size.z / 2)        # центр по x тела (по габариту)
	print("плоскость: габарит вдоль x %.1f мм, вылет %.1f мм, центр x %.1f мм"
			% [fa.size.z * 1e3, fa.size.x * 1e3, cx * 1e3])
	check("плоскость: центр по x = fins.pos (±1 мм)", absf(cx - float(fin0["pos"][0])) <= TOL)
	var area := 2 * (0.200 + 0.143) / 2 * fa.size.x
	check("плоскости: площадь пары = сумма fins (±2 %)", absf(area - fin_area) <= 0.02 * fin_area)

	# Вытесненный объём: замкнутые сетки без внутренних частей (цистерны, корпус камеры в боксе)
	# и без кабелей, как в blender/build_rov.py
	var vol := 0.0
	for mi in model.find_children("*", "MeshInstance3D", true, false):
		var m := mi as MeshInstance3D
		var nm := String(m.name)
		if nm.begins_with("tank_") or nm == "camera_body" or nm.begins_with("cable_"):
			continue
		vol += mesh_volume(m)
	var v_phys: float = float(p["mass_dry"]["value"]) / float(p["rho"]["value"]) \
			+ float(p["neutral_tank_volume"]["value"])
	print("объём сетки %.4f л, физика %.4f л" % [vol * 1e3, v_phys * 1e3])
	check("объём сетки = объём в физике (±1 %)", absf(vol - v_phys) <= 0.01 * v_phys)

	print("ИТОГ: %s" % ("все проверки пройдены" if failures == 0 else "%d не пройдено" % failures))
	quit(1 if failures > 0 else 0)
