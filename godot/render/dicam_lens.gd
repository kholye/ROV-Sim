class_name DicamLens
extends RefCounted
## Объектив камеры аппарата Digma DiCam 300 в аквабоксе (docs/physics-sources.md, разд. 21): угол обзора на воздухе
## 140° по горизонтали (Холопов, табл. 7); проекция — равноудалённая «рыбий глаз» (r ∝ угол луча на воздухе, оценка:
## тип проекции в паспорте не указан, у экшн-камер с углом 140° — близкая к ней); плоское окно бокса в воде —
## закон Снелла на каждом луче: sin θ_воздух = n·sin θ_вода. Кадр 16:9; координаты кадра нормированы на полуширину.
## Камера Godot рисует прямолинейно с углом 2·θ_вода(70°) по горизонтали; проход стиля (shaders/style.gdshader)
## переводит её кадр в проекцию объектива теми же формулами.

var half_air := deg_to_rad(70.0)   # половина угла на воздухе, рад
var n := 1.333                     # показатель преломления воды


func _init(p: Dictionary) -> void:
	half_air = deg_to_rad(float(p["dicam_hfov_air_deg"]) * 0.5)
	n = float(p["water_n"])


## Половина угла по горизонтали в воде (для прямолинейной камеры Godot), рад.
func half_water() -> float:
	return asin(sin(half_air) / n)


## Направление в осях камеры (x вправо, y вверх, смотрит в −z) -> координаты кадра (x на полуширину, y вверх).
## Луч вне поля плоского окна (полное отражение не наступает: sin θ_воздух ≤ 1) — за краем кадра.
func project(dir: Vector3) -> Vector2:
	var rho := Vector2(dir.x, dir.y).length()
	var th_w := atan2(rho, -dir.z)
	var s := minf(n * sin(th_w), 1.0)
	var r := asin(s) / half_air
	if rho < 1e-9:
		return Vector2.ZERO
	return Vector2(dir.x, dir.y) / rho * r
