extends Node
## Автозагрузка PortableNode: при выходе собранной игры убирает пустые папки движка в %APPDATA% (Paths).

func _exit_tree() -> void:
	Paths.clean_system_dirs()
