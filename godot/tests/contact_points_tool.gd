extends SceneTree
## Точки касания корпуса для модели касания (physics/rov_contact.gd, docs/physics-sources.md, разд. 31):
## вершины выпуклой оболочки модели аппарата (assets/rov/rov.glb, оси модели = NED тела через NedGodot),
## прорежённые выбором самой дальней точки (сначала крайние по шести осям). Печатает JSON для rov_params.json.
##   Godot --headless --path godot --script res://tests/contact_points_tool.gd -- [N]

func _init() -> void:
	var a := OS.get_cmdline_user_args()
	var N := int(a[0]) if a.size() > 0 else 32
	var m: Node3D = load("res://assets/rov/rov.glb").instantiate()
	var pts := PackedVector3Array()
	for mi: MeshInstance3D in m.find_children("*", "MeshInstance3D", true, false):
		var t := Transform3D.IDENTITY          # дерево ещё не в сцене: глобальная матрица — произведением вверх до корня
		var nd: Node = mi
		while nd != m and nd is Node3D:
			t = (nd as Node3D).transform * t
			nd = nd.get_parent()
		t = m.transform * t
		for s in mi.mesh.get_surface_count():
			for v: Vector3 in mi.mesh.surface_get_arrays(s)[Mesh.ARRAY_VERTEX]:
				pts.append(t * v)
	while pts.size() % 3 != 0:
		pts.append(pts[0])
	var am := ArrayMesh.new()
	var arr := []
	arr.resize(Mesh.ARRAY_MAX)
	arr[Mesh.ARRAY_VERTEX] = pts
	am.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arr)
	var hull: PackedVector3Array = (am.create_convex_shape(true, false) as ConvexPolygonShape3D).points
	var chosen: Array[Vector3] = []
	for axis in [Vector3.RIGHT, Vector3.LEFT, Vector3.UP, Vector3.DOWN, Vector3.FORWARD, Vector3.BACK]:
		var best := hull[0]
		for h in hull:
			if h.dot(axis) > best.dot(axis):
				best = h
		if not chosen.has(best):
			chosen.append(best)
	while chosen.size() < N:
		var far := hull[0]
		var fd := -1.0
		for h in hull:
			var d := 1e9
			for c in chosen:
				d = minf(d, h.distance_to(c))
			if d > fd:
				fd = d
				far = h
		chosen.append(far)
	var out := []
	for c in chosen:
		var n := NedGodot.vec_to_ned(c)
		out.append([snappedf(n[0], 0.001), snappedf(n[1], 0.001), snappedf(n[2], 0.001)])
	print("HULL ", hull.size(), " вершин оболочки, выбрано ", out.size())
	print("POINTS ", JSON.stringify(out))
	quit()
