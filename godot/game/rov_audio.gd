class_name RovAudio
extends AudioStreamPlayer
## Звук, синтезируемый на лету (без чужих записей): вой бесщёточных движителей — частота растёт
## с оборотами (обороты ∝ |команда|, раз тяга ∝ s·|s|), шум винта; жужжание поршневых приводов
## цистерн, пока они работают; низкий гул воды; глухой удар при касании; короткий сигнал при
## сообщении (как писк пульта). Частоты и громкости — художественная оценка, не замер.

const RATE := 22050.0

var rov: Rov
var _gen: AudioStreamGeneratorPlayback
var _rng := RandomNumberGenerator.new()
var _ph := PackedFloat64Array([0, 0, 0, 0, 0])   # фазы: движитель Л, П, привод цистерн, его редуктор, сигнал
var _amp := PackedFloat64Array([0, 0, 0])         # сглаженные громкости: Л, П, цистерны
var _f := PackedFloat64Array([0, 0])
var _brown := 0.0
var _lp := PackedFloat64Array([0, 0])
var _thud := 0.0
var _beep := 0.0
var _last_notice := -10.0


func setup(r: Rov) -> void:
	rov = r
	_rng.seed = 3
	var s := AudioStreamGenerator.new()
	s.mix_rate = RATE
	s.buffer_length = 0.15
	stream = s
	volume_db = -6.0
	process_mode = Node.PROCESS_MODE_PAUSABLE
	rov.touched.connect(func(_c): _thud = 1.0)
	play()
	_gen = get_stream_playback()


func beep() -> void:
	_beep = 1.0


func _process(_dt: float) -> void:
	if _gen == null or rov == null:
		return
	if rov.notice_t != _last_notice:
		_last_notice = rov.notice_t
		_beep = 1.0
	var n := _gen.get_frames_available()
	if n <= 0:
		return
	var tgt := PackedFloat64Array([0, 0, 0])
	for k in 2:
		var s := absf(rov.thr[k])
		tgt[k] = 0.16 * pow(s, 1.2)
		_f[k] = 70.0 + 650.0 * s
	tgt[2] = 0.05 if (rov.tank_cmd[0] != 0 or rov.tank_cmd[1] != 0) else 0.0
	var buf := PackedVector2Array()
	buf.resize(n)
	var a := 1.0 - exp(-1.0 / (RATE * 0.05))
	for i in n:
		for k in 3:
			_amp[k] += (tgt[k] - _amp[k]) * a
		var out := 0.0
		for k in 2:
			_ph[k] = fmod(_ph[k] + _f[k] / RATE, 1.0)
			var w := sin(TAU * _ph[k]) * 0.6 + sin(TAU * 2.0 * _ph[k]) * 0.25 + sin(TAU * 7.0 * _ph[k]) * 0.08
			var wn := _rng.randf() * 2.0 - 1.0
			_lp[k] += (wn - _lp[k]) * (0.05 + 0.4 * _amp[k])
			out += _amp[k] * (w + 0.8 * _lp[k])
		if _amp[2] > 1e-4:
			_ph[2] = fmod(_ph[2] + 118.0 / RATE, 1.0)
			_ph[3] = fmod(_ph[3] + 940.0 / RATE, 1.0)
			out += _amp[2] * ((1.0 if _ph[2] < 0.5 else -1.0) * 0.6 + sin(TAU * _ph[3]) * 0.4)
		_brown = _brown * 0.995 + (_rng.randf() * 2.0 - 1.0) * 0.005
		out += _brown * 0.9
		if _thud > 1e-3:
			out += _thud * (_rng.randf() * 2.0 - 1.0) * 0.5 * (0.6 + 0.4 * sin(TAU * 55.0 * _thud))
			_thud *= exp(-1.0 / (RATE * 0.09))
		if _beep > 1e-3:
			_ph[4] = fmod(_ph[4] + 1320.0 / RATE, 1.0)
			out += 0.08 * sin(TAU * _ph[4]) * (1.0 if _beep > 0.35 else _beep / 0.35)
			_beep -= 1.0 / (RATE * 0.09)
		var v := tanh(out * 1.4)
		buf[i] = Vector2(v, v)
	_gen.push_buffer(buf)
