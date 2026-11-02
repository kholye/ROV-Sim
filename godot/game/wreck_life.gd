class_name WreckLife
extends RefCounted
## Обрастание судна и живность на дне экземплярами (blender/build_wreck_site.py): образцы Proto_<вид>
## лежат в wreck_site.glb (скрываются), экземпляры — в wreck_life.json (положение, базис с масштабом, тон;
## оси Godot относительно корня сцены места). Вид рисуется пачками MultiMesh по ячейкам CELL × CELL м:
## ячейка дальше RANGE от камеры не рисуется — в мутной воде (видимость ≈ 7 м) мелочь там уже неразличима,
## а видеокарте не приходится считать свет для тысяч невидимых организмов. Ячейки ближе LOD_D рисуются
## подробным образцом, дальше — упрощённым Proto_<вид>_lod (в 3-4 раза меньше треугольников: мелкие
## треугольники стоят видеокарте дорого, свет считается на каждый).

const LIFE := "res://assets/wreck/wreck_life.json"
const RANGE := 8.0                                        # м до центра ячейки (+ 0,7 ячейки): дальше 8 м при видимости 7 м мелочь не различить
const RANGE_BIG := {"kelp_dig": 12.0, "kelp_sac": 12.0}   # длинные листья заметны дальше
const LOD_D := 5.0                                        # м до центра ячейки: ближе — подробный образец


## Строит пачки под site (узел сцены места); возвращает число экземпляров.
static func build(site: Node3D) -> int:
	var data: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(LIFE))
	var cell := float(data["cell"])
	var total := 0
	for sp in data["species"]:
		var proto := site.find_child("Proto_" + sp, true, false) as MeshInstance3D
		var lod := site.find_child("Proto_" + sp + "_lod", true, false) as MeshInstance3D
		proto.visible = false
		if lod:
			lod.visible = false
		var mat := (proto.get_surface_override_material(0) as ShaderMaterial).duplicate() as ShaderMaterial
		mat.set_shader_parameter("instanced", true)
		Underwater.register(mat)
		var cells := {}
		for row in data["species"][sp]:
			var key := Vector2i(floori(row[0] / cell), floori(row[2] / cell))
			if not cells.has(key):
				cells[key] = []
			cells[key].append(row)
		for key: Vector2i in cells:
			var rows: Array = cells[key]
			var center := Vector3((key.x + 0.5) * cell, 0.0, (key.y + 0.5) * cell)
			var far := float(RANGE_BIG.get(sp, RANGE)) + cell * 0.7
			if lod:
				_cell(site, "Life_%s_%d_%d" % [sp, key.x, key.y], proto.mesh, mat, rows, center, 0.0, LOD_D)
				_cell(site, "Life_%s_lod_%d_%d" % [sp, key.x, key.y], lod.mesh, mat, rows, center, LOD_D, far)
			else:
				_cell(site, "Life_%s_%d_%d" % [sp, key.x, key.y], proto.mesh, mat, rows, center, 0.0, far)
			total += rows.size()
	return total


static func _cell(site: Node3D, nm: String, mesh: Mesh, mat: Material, rows: Array, center: Vector3,
		r0: float, r1: float) -> void:
	var mm := MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	mm.use_custom_data = true
	mm.mesh = mesh
	mm.instance_count = rows.size()
	for i in rows.size():
		var r: Array = rows[i]
		var b := Basis(Vector3(r[3], r[4], r[5]), Vector3(r[6], r[7], r[8]), Vector3(r[9], r[10], r[11]))
		mm.set_instance_transform(i, Transform3D(b, Vector3(r[0], r[1], r[2]) - center))
		mm.set_instance_custom_data(i, Color(r[12], r[13], r[14], 0.0))
	var mi := MultiMeshInstance3D.new()
	mi.name = nm
	mi.multimesh = mm
	mi.material_override = mat
	mi.position = center
	mi.visibility_range_begin = r0
	mi.visibility_range_end = r1
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	site.add_child(mi)
