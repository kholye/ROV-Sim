extends Node3D
## Сцена просмотра модели аппарата (этап 3). Модель медленно вращается.
## С аргументом `-- --shot <файл.png>` сохраняет кадр и закрывается (снимок для docs/model/).

var shot_path := ""
var frames := 0


func _ready() -> void:
	var args := OS.get_cmdline_user_args()
	var i := args.find("--shot")
	if i >= 0 and i + 1 < args.size():
		shot_path = args[i + 1]


func _process(delta: float) -> void:
	if shot_path.is_empty():
		$Rov.rotate_y(0.3 * delta)
		return
	frames += 1
	if frames == 5:
		get_viewport().get_texture().get_image().save_png(shot_path)
		get_tree().quit()
