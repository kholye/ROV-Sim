class_name UiSound
extends Node
## Автозагрузка UiSoundNode (класс UiSound): шины звука и звуки интерфейса. Шины: Music (музыка меню), UI (кнопки), World (звук
## аппарата и места, с эхом по сцене — set_room). Кнопки любого меню озвучиваются сами: при появлении кнопки
## в дереве к ней подключаются выбор (фокус) и нажатие; кнопка с meta «sfx» = "back" звучит как «назад».
## Вызывать через статические UiSound.sfx(), .menu_music(), .room(): без узла (проверки --script) — ничего.
## Звуки — Kenney «Interface Sounds» (CC0), музыка — «Aquaria», cynicmusic (CC0); docs/CREDITS.md.

const SFX := {
	"select": preload("res://assets/audio/ui_select.ogg"),
	"confirm": preload("res://assets/audio/ui_confirm.ogg"),
	"back": preload("res://assets/audio/ui_back.ogg"),
	"switch": preload("res://assets/audio/ui_switch.ogg"),
	"toggle": preload("res://assets/audio/ui_toggle.ogg"),
	"question": preload("res://assets/audio/ui_question.ogg"),
}
const MUSIC := preload("res://assets/audio/menu_aquaria.ogg")
const MUSIC_DB := -16.0          # тихо, фоном (просьба: «не навязчивая»)
const SFX_DB := -10.0
const QUIET_AFTER_SCENE := 0.25  # с: после смены сцены первый фокус (grab_focus) не озвучивается

var _players: Array[AudioStreamPlayer] = []
var _music: AudioStreamPlayer
var _quiet_until := 0.0
var _tw: Tween


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	for b in ["Music", "UI", "World"]:
		if AudioServer.get_bus_index(b) < 0:
			AudioServer.add_bus()
			var i := AudioServer.bus_count - 1
			AudioServer.set_bus_name(i, b)
			AudioServer.set_bus_send(i, "Master")
	var w := AudioServer.get_bus_index("World")
	if AudioServer.get_bus_effect_count(w) == 0:
		AudioServer.add_bus_effect(w, AudioEffectReverb.new())
	set_room(0.0, 0.0)
	for i in 4:
		var p := AudioStreamPlayer.new()
		p.bus = "UI"
		p.volume_db = SFX_DB
		add_child(p)
		_players.append(p)
	_music = AudioStreamPlayer.new()
	_music.bus = "Music"
	var m := MUSIC.duplicate() as AudioStreamOggVorbis
	m.loop = true
	_music.stream = m
	_music.volume_db = -80.0
	add_child(_music)
	get_tree().node_added.connect(_on_node)
	get_tree().scene_changed.connect(func(): _quiet_until = _now() + QUIET_AFTER_SCENE)


static func _node() -> UiSound:
	var t := Engine.get_main_loop() as SceneTree
	return t.root.get_node_or_null("UiSoundNode") as UiSound if t else null


static func sfx(name: String) -> void:
	var n := _node()
	if n:
		n.play(name)


static func menu_music(on: bool) -> void:
	var n := _node()
	if n:
		n.music(on)


static func room(size: float, wet: float) -> void:
	var n := _node()
	if n:
		n.set_room(size, wet)


func _now() -> float:
	return Time.get_ticks_msec() / 1000.0


func play(name: String) -> void:
	if not SFX.has(name) or DisplayServer.get_name() == "headless":
		return
	for p in _players:
		if not p.playing:
			p.stream = SFX[name]
			p.play()
			return
	_players[0].stream = SFX[name]
	_players[0].play()


## Музыка меню: плавно включить / выключить.
func music(on: bool) -> void:
	if DisplayServer.get_name() == "headless":
		return
	if _tw:
		_tw.kill()
	_tw = create_tween()
	if on:
		if not _music.playing:
			_music.volume_db = -40.0
			_music.play()
		_tw.tween_property(_music, "volume_db", MUSIC_DB, 1.5)
	else:
		_tw.tween_property(_music, "volume_db", -60.0, 0.6)
		_tw.tween_callback(_music.stop)


## Эхо на шине World: размер помещения и доля отражённого звука (0 — открытая вода).
func set_room(size: float, wet: float) -> void:
	var w := AudioServer.get_bus_index("World")
	var r := AudioServer.get_bus_effect(w, 0) as AudioEffectReverb
	r.room_size = size
	r.wet = wet
	r.dry = 1.0
	r.damping = 0.6
	AudioServer.set_bus_effect_enabled(w, 0, wet > 0.0)


func _on_node(n: Node) -> void:
	if n is BaseButton:
		var b := n as BaseButton
		b.focus_entered.connect(func(): if _now() > _quiet_until: play("select"))
		if b is CheckBox or b is CheckButton:
			b.toggled.connect(func(_on): play("toggle"))
		elif b is OptionButton:
			(b as OptionButton).item_selected.connect(func(_i): play("toggle"))
		else:
			b.pressed.connect(func(): play(String(b.get_meta("sfx", "confirm"))))
