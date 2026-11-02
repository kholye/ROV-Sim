class_name LevelKit
extends RefCounted
## Общие кирпичики уровней: сетки с подводным материалом, статические препятствия, текстуры.
## Размеры в метрах, координаты Godot (Y вверх). Альбедо линейное.


## Ящик (видимый) с коллизией; parent получает StaticBody3D. Возвращает тело.
static func box(parent: Node, size: Vector3, pos: Vector3, mat: Material, collide := true, rot := Basis()) -> Node3D:
	var root: Node3D = StaticBody3D.new() if collide else Node3D.new()
	root.transform = Transform3D(rot, pos)
	var mi := MeshInstance3D.new()
	var bm := BoxMesh.new()
	bm.size = size
	mi.mesh = bm
	mi.material_override = mat
	root.add_child(mi)
	if collide:
		var cs := CollisionShape3D.new()
		var sh := BoxShape3D.new()
		sh.size = size
		cs.shape = sh
		root.add_child(cs)
	parent.add_child(root)
	return root


## Прямоугольник (одна сторона видна): нормаль = basis.z. Для стен изнутри бассейна.
static func quad(parent: Node, size: Vector2, xf: Transform3D, mat: Material) -> MeshInstance3D:
	var mi := MeshInstance3D.new()
	var q := QuadMesh.new()
	q.size = size
	mi.mesh = q
	mi.transform = xf
	mi.material_override = mat
	parent.add_child(mi)
	return mi


static func cylinder(parent: Node, radius: float, height: float, xf: Transform3D, mat: Material, collide := true) -> Node3D:
	var root: Node3D = StaticBody3D.new() if collide else Node3D.new()
	root.transform = xf
	var mi := MeshInstance3D.new()
	var cm := CylinderMesh.new()
	cm.top_radius = radius
	cm.bottom_radius = radius
	cm.height = height
	cm.radial_segments = 10
	cm.rings = 1
	mi.mesh = cm
	mi.material_override = mat
	root.add_child(mi)
	if collide:
		var cs := CollisionShape3D.new()
		var sh := CylinderShape3D.new()
		sh.radius = radius
		sh.height = height
		cs.shape = sh
		root.add_child(cs)
	parent.add_child(root)
	return root


## Статическое тело с формой из сетки (кольца, судно, дно).
static func trimesh_body(parent: Node, mi: MeshInstance3D) -> StaticBody3D:
	var sb := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	cs.shape = mi.mesh.create_trimesh_shape()
	sb.add_child(cs)
	sb.transform = mi.transform
	parent.add_child(sb)
	return sb


## Текстура плитки: квадрат 64 px = одна плитка, шов шириной 3 px (множитель альбедо).
static func tile_texture(grout := 0.45, noise := 0.06, seed_ := 1) -> ImageTexture:
	var img := Image.create(64, 64, false, Image.FORMAT_RGB8)
	var rng := RandomNumberGenerator.new()
	rng.seed = seed_
	for y in 64:
		for x in 64:
			var v := 1.0 - noise * rng.randf()
			if x < 3 or y < 3:
				v = grout
			img.set_pixel(x, y, Color(v, v, v).linear_to_srgb())
	img.generate_mipmaps()
	return ImageTexture.create_from_image(img)


## Текстура «ил и бетон»: пятна, без швов.
static func grime_texture(seed_ := 3, size := 128, amount := 0.35) -> ImageTexture:
	var n := FastNoiseLite.new()
	n.seed = seed_
	n.frequency = 0.05
	var img := Image.create(size, size, false, Image.FORMAT_RGB8)
	for y in size:
		for x in size:
			var v := clampf(1.0 - amount * (0.5 + 0.5 * n.get_noise_2d(x, y)), 0.0, 1.0)
			img.set_pixel(x, y, Color(v, v, v).linear_to_srgb())
	img.generate_mipmaps()
	return ImageTexture.create_from_image(img)
