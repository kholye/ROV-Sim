extends SceneTree
## Тексты лицензий движка Godot и его сторонних библиотек для папки сборки (их требует MIT).
##   Godot_console --headless --path godot --script <этот файл> -- <папка>

func _init() -> void:
	var out: String = OS.get_cmdline_user_args()[0]
	DirAccess.make_dir_recursive_absolute(out)
	_write(out.path_join("Godot-LICENSE.txt"), Engine.get_license_text())
	var s := "Godot Engine: сторонние компоненты и их лицензии\n\n"
	for c in Engine.get_copyright_info():
		s += "== %s\n" % c["name"]
		for p in c["parts"]:
			s += "   файлы: %s\n   авторы: %s\n   лицензия: %s\n" % [", ".join(p["files"]), ", ".join(p["copyright"]), p["license"]]
		s += "\n"
	s += "\n\nТексты лицензий\n\n"
	var info := Engine.get_license_info()
	for k in info:
		s += "== %s\n%s\n\n" % [k, info[k]]
	_write(out.path_join("Godot-third-party.txt"), s)
	print("licenses -> ", out)
	quit()


func _write(path: String, text: String) -> void:
	var f := FileAccess.open(path, FileAccess.WRITE)
	f.store_string(text)
