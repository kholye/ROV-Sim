extends LevelBase
## Тестовая сцена «лабораторный бассейн» кафедры: 3,5 × 3,5 × 3 м (сторона ≈3,5 м — по данным автора 2026-11-05).
## Для проверок (V3, V4, V5), в игровые сценарии не входит. Вода «чистая» бассейна кафедры
## (подогнано по кадрам Холопова, V5). Модель из Blender: blender/build_lab_pool.py -> assets/lab/lab_pool.glb
## (бетон, чёрное резиновое дно в иле — по данным автора; планшет мишени на северной стене).
## Сверху — пол зала из щитов на раме, открыт один щит (по данным автора, через него опускали аппарат). Зал построен
## по скану LIDAR (blender/build_lab_room.py, свет запечён — bake_lab_room.py) и из-под воды виден через окно Снелла
## (shaders/hall_refract.gdshader); за окном поверхность отражает (water_surface_lab.gdshader). Свет в воду —
## lab_e_surface (light_params.json: 300 лк зала × доля люка). Кабель-трос (game/tether.gd) идёт из люка к аппарату.
## Клавиша 1 / 2 / 3: поставить аппарат в 1,0 / 2,0 / 2,7 м от планшета на стене.

const S := 3.5                                  # сторона, м
const D := 3.0                                  # глубина, м
const LAB_GLB := preload("res://assets/lab/lab_pool.glb")
const ROOM_GLB := preload("res://assets/lab/lab_room.glb")
const ROOM_BAKE := "res://assets/lab/lab_room_bake.json"
const HALL_SHADER := preload("res://shaders/hall_refract.gdshader")
const SURF_SHADER := preload("res://shaders/water_surface_lab.gdshader")
const OPEN := Rect2(-1.09, -1.03, 1.10, 1.05)  # открытый щит в плане Godot (x восток, z юг), м — как в build_lab_room.py
const WALL_T := 0.5                             # толщина стенок-подложек для столкновений, м

var tether: Tether
const HALL_L := 40.0                            # кд/м²: средняя яркость зала в проёме люка для замера экспозиции (оценка по запеканию)
const UNDER_L := 0.5                            # кд/м²: низ щитов и балки (оценка)


func _ready() -> void:
	place = "lab"
	setup_level("pool", "lab_e_surface")
	var lab := LAB_GLB.instantiate()
	add_child(lab)
	uw.convert_tree(lab)
	for mi in lab.find_children("*", "MeshInstance3D", true, false):
		if not String(mi.name).begins_with("Plate"):
			(mi as MeshInstance3D).create_trimesh_collision()
	_backstop()
	_hall()
	spawn_rov(1.5, S / 2 - 2.0 - 0.4, 0.0, 0.0)     # камера (0,4 м впереди центра) в 2,0 м от планшета
	rov.above_water = func(S: Vector3) -> float: return HALL_L if OPEN.has_point(Vector2(S.x, S.z)) else UNDER_L
	if not args.has("no-silt"):              # ил на дне (по данным автора) поднимают движители
		var silt := SiltCloud.new()
		add_child(silt)
		silt.setup(rov, PackedFloat64Array([0, 0, D]), 5.0)
		silt.plume.box = PackedFloat64Array([-S / 2, S / 2, -S / 2, S / 2])   # ил остаётся в бассейне
		if silt.flocs:
			silt.flocs.set_box(Vector4(-S / 2, S / 2, -S / 2, S / 2))         # те же стенки в осях Godot (x, z)
	tether = Tether.new()
	tether.edge_turbid = false
	add_child(tether)
	tether.setup(self, Vector3(OPEN.get_center().x, 0.0, OPEN.get_center().y), Vector3.ZERO, D,
			AABB(Vector3(-S / 2, -D, -S / 2), Vector3(S, D + 0.3, S)), not args.has("no-tether"))


## Толстые невидимые стенки за стенами и под дном: тонкая сетка бассейна не держит то, что прошло её насквозь.
func _backstop() -> void:
	var sb := StaticBody3D.new()
	sb.name = "Backstop"
	add_child(sb)
	var h := S / 2 + WALL_T / 2
	for b in [[Vector3(0, -D - WALL_T / 2, 0), Vector3(S + 2 * WALL_T, WALL_T, S + 2 * WALL_T)],
			[Vector3(h, -D / 2, 0), Vector3(WALL_T, D + 1.0, S + 2 * WALL_T)], [Vector3(-h, -D / 2, 0), Vector3(WALL_T, D + 1.0, S + 2 * WALL_T)],
			[Vector3(0, -D / 2, h), Vector3(S, D + 1.0, WALL_T)], [Vector3(0, -D / 2, -h), Vector3(S, D + 1.0, WALL_T)]]:
		var cs := CollisionShape3D.new()
		var box := BoxShape3D.new()
		box.size = b[1]
		cs.shape = box
		cs.position = b[0]
		sb.add_child(cs)


## Зал над бассейном: запечённая яркость (кд/м²) со смещением вершин по закону преломления, поверхность воды
## с полным внутренним отражением за окном Снелла.
func _hall() -> void:
	var room := ROOM_GLB.instantiate()
	add_child(room)
	var bake: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(ROOM_BAKE))
	for mi in room.find_children("*", "MeshInstance3D", true, false):
		var m := mi as MeshInstance3D
		var src := m.mesh.surface_get_material(0) as BaseMaterial3D
		var hm := ShaderMaterial.new()
		hm.shader = HALL_SHADER
		hm.set_shader_parameter("light_tex", src.albedo_texture if src else null)
		hm.set_shader_parameter("l_ref", float(bake["L_ref_cd_m2"]))
		m.material_override = Underwater.register(hm)
		m.extra_cull_margin = 4.0                   # вершины смещаются в шейдере
		m.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	var sm := ShaderMaterial.new()
	sm.shader = SURF_SHADER
	LevelKit.quad(self, Vector2(S, S), Transform3D(Basis(Vector3.RIGHT, PI / 2), Vector3.ZERO), Underwater.register(sm))


func _unhandled_input(ev: InputEvent) -> void:
	super(ev)
	if ev is InputEventKey and ev.pressed and not ev.echo:
		var d: float = {KEY_1: 1.0, KEY_2: 2.0, KEY_3: 2.7}.get(ev.keycode, 0.0)
		if d > 0.0:
			rov.x = RovDynamics.initial_state(1.5, 0.0)
			rov.x[0] = S / 2 - d - 0.4                 # стена на севере (NED x = +1,5 м), камера на 0,4 м впереди центра
			rov.x[1] = 0.0
			rov.reset_control()


func hud_mission() -> String:
	var dist := rov.cam_front.global_position.z + S / 2
	var t := "ЛАБОРАТОРНЫЙ БАССЕЙН 3,5×3,5×3 м\nдо планшета %s м\n1 / 2 / 3 — 1,0 / 2,0 / 2,7 м" % Hud.num(dist, 2)
	if tether and tether.cable:
		t += "\nкабель %s м, %s Н" % [Hud.num(tether.length(), 1), Hud.num(tether.tension(), 1)]
	return t
