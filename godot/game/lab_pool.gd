extends LevelBase
## Тестовая сцена «лабораторный бассейн» кафедры: 3 × 3 × 3 м (размер по данным автора).
## Для проверок (V3, V4, V5), в игровые сценарии не входит. Вода «чистая» бассейна кафедры
## (подогнано по кадрам Холопова, V5). Модель из Blender: blender/build_lab_pool.py -> assets/lab/lab_pool.glb
## (бетон с налётом и илом, чёрное резиновое дно в иле — по данным автора; планшет мишени на дне, как в
## опытах, и на северной стене: камера аппарата смотрит вперёд и вниз не наклоняется).
## Клавиша 1 / 2 / 3: поставить аппарат в 1,0 / 2,0 / 2,7 м от планшета на стене.

const S := 3.0
const LAB_GLB := preload("res://assets/lab/lab_pool.glb")


func _ready() -> void:
	setup_level("pool", "pool_e_surface")
	var lab := LAB_GLB.instantiate()
	add_child(lab)
	uw.convert_tree(lab)
	for mi in lab.find_children("*", "MeshInstance3D", true, false):
		if not String(mi.name).begins_with("Plate"):
			(mi as MeshInstance3D).create_trimesh_collision()
	LevelKit.quad(self, Vector2(S, S), Transform3D(Basis(Vector3.RIGHT, PI / 2), Vector3.ZERO),
			Underwater.material(Vector3.ZERO, uw.esurf / PI))
	spawn_rov(1.5, S / 2 - 2.0 - 0.4, 0.0, 0.0)     # камера (0,4 м впереди центра) в 2,0 м от планшета
	if not args.has("no-silt"):              # ил на дне (по данным автора) поднимают движители
		var silt := SiltCloud.new()
		add_child(silt)
		silt.setup(rov, PackedFloat64Array([0, 0, S]), 5.0)
		silt.plume.box = PackedFloat64Array([-S / 2, S / 2, -S / 2, S / 2])   # ил остаётся в бассейне
		if silt.flocs:
			silt.flocs.set_box(Vector4(-S / 2, S / 2, -S / 2, S / 2))         # те же стенки в осях Godot (x, z)


func _unhandled_input(ev: InputEvent) -> void:
	super(ev)
	if ev is InputEventKey and ev.pressed and not ev.echo:
		var d: float = {KEY_1: 1.0, KEY_2: 2.0, KEY_3: 2.7}.get(ev.keycode, 0.0)
		if d > 0.0:
			rov.x = RovDynamics.initial_state(1.5, 0.0)
			rov.x[0] = S / 2 - d - 0.4                 # стена на севере (NED x = +1,5 м), камера на 0,4 м впереди центра
			rov.x[1] = 0.0


func hud_mission() -> String:
	var dist := rov.cam_front.global_position.z + S / 2
	return "ЛАБОРАТОРНЫЙ БАССЕЙН 3×3×3 м\nдо планшета %s м\n1 / 2 / 3 — 1,0 / 2,0 / 2,7 м" % Hud.num(dist, 2)
