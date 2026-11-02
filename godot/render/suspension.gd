class_name Suspension
extends MultiMeshInstance3D
## Видимая взвесь вокруг камеры (shaders/underwater_particles.gdshader). Частицы равномерно в кубе
## box × box × box, радиусы 0,25-3 мм («морской снег», агрегаты 0,5-5 мм) по степенному закону (мелких больше: n(r) ∝ r^−2, оценка по
## распределению Юнге для взвеси, Mobley 1994). Плотность видимых частиц пропорциональна рассеянию
## взвесью: n = particles_per_m3_per_bp · b_p550 (оценка, не измерено). Куб следует за камерой в шейдере.

const SHADER := preload("res://shaders/underwater_particles.gdshader")


func setup(uw: Underwater, bp550: float, box := 6.0, seed_ := 11) -> void:
	var dens: float = float(uw.p["particles_per_m3_per_bp"]) * bp550
	var n := int(dens * box * box * box)
	var mm := MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	mm.use_custom_data = true
	var q := QuadMesh.new()
	q.size = Vector2.ONE
	mm.mesh = q
	mm.instance_count = n
	var rng := RandomNumberGenerator.new()
	rng.seed = seed_
	var rmin := 0.25e-3
	var rmax := 3.0e-3
	for i in n:
		mm.set_instance_transform(i, Transform3D())
		# r^−2: обратная функция распределения 1/r = 1/rmin − u(1/rmin − 1/rmax)
		var r := 1.0 / (1.0 / rmin - rng.randf() * (1.0 / rmin - 1.0 / rmax))
		mm.set_instance_custom_data(i, Color(rng.randf(), rng.randf(), rng.randf(), r))
	multimesh = mm
	var m := ShaderMaterial.new()
	m.shader = SHADER
	m.set_shader_parameter("box", box)
	m.set_shader_parameter("albedo_p", float(uw.p["particle_albedo"]))
	material_override = Underwater.register(m)
	custom_aabb = AABB(Vector3(-1e4, -1e4, -1e4), Vector3(2e4, 2e4, 2e4))   # позиция считается в шейдере
	cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	name = "Suspension"


func _process(_dt: float) -> void:
	var m := material_override as ShaderMaterial
	if m:
		m.set_shader_parameter("viewport_h", get_viewport().get_visible_rect().size.y)
