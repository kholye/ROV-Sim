class_name Paths
extends RefCounted
## Где игра хранит свои файлы (настройки, результаты, телеметрия, снимки F12, отчёты осмотра).
## Собранная игра (.exe) портативная: всё в папке userdata рядом с ROV-Sim.exe, в системные папки
## (%APPDATA%) ничего не пишется; журнал и кэш шейдеров движка выключены (project.godot). Если папка игры
## только для чтения (например, Program Files), — запасной путь user://. Из редактора — user://, как раньше.

const DIR := "userdata"

static var _root := ""


## Корень данных игры, всегда с «/» на конце.
static func root() -> String:
	if _root != "":
		return _root
	_root = "user://"
	if OS.has_feature("template"):
		var d := OS.get_executable_path().get_base_dir().path_join(DIR)
		DirAccess.make_dir_recursive_absolute(d)
		var f := FileAccess.open(d.path_join(".write_test"), FileAccess.WRITE)
		if f:
			f.close()
			DirAccess.remove_absolute(d.path_join(".write_test"))
			_root = d + "/"
	return _root


static func file(name: String) -> String:
	return root() + name


## Папка внутри корня (создаётся), с «/» на конце.
static func dir(name: String) -> String:
	var d := root() + name
	DirAccess.make_dir_recursive_absolute(d)
	return d + "/"


## При выходе собранной игры: убрать пустые папки, которые движок всё равно создаёт в %APPDATA%
## (Godot/app_userdata/ROV-Sim/shader_cache и родители). Удаляются только пустые папки, файлы — никогда.
static func clean_system_dirs() -> void:
	if not OS.has_feature("template") or root() == "user://":
		return
	var u := OS.get_user_data_dir()
	var d := DirAccess.open(u)
	if d:
		for sub in d.get_directories():
			DirAccess.remove_absolute(u.path_join(sub))
	for p in [u, u.get_base_dir(), u.get_base_dir().get_base_dir()]:   # ROV-Sim, app_userdata, Godot — если пусты
		DirAccess.remove_absolute(p)


## Путь для показа игроку (полный путь на диске).
static func shown(path: String) -> String:
	return ProjectSettings.globalize_path(path) if path.begins_with("user://") else path
