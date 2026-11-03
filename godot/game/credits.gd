class_name Credits
extends RefCounted
## Авторы ROV-Sim и аппарата «Петрович». Текст хранится в двух местах: здесь (TEXT) и в
## assets/ui/authors.txt; у обоих проверяется отпечаток SHA-256. Если одну копию изменили или удалили,
## игра берёт другую; если испорчены обе — встроенную строку FALLBACK. Показывается на заставке,
## на экране «Авторы», в окне «как это работает» и на снимках фото-режима (короткая строка).
## Строка авторских прав — в LICENSE (MIT требует сохранять её во всех копиях).

const FILE := "res://assets/ui/authors.txt"
const SHA := "27ede7c4a1a01b19abbb3d9e96e82ff14ef124e2941a9144f087aeea78bf7c62"
const TEXT := """ROV-Sim — Холопов Егор Геннадьевич, 2026
Аппарат «Петрович» — макет для отработки инженерных решений, кафедра морских информационных систем и технологий (МИСиТ, 2350) СПбГМТУ
Коротицкий Евгений Викторович, к. т. н., доцент
Кузьменко Александр Владимирович, старший преподаватель
Холопов Егор Геннадьевич, магистр
Дунаев Артем Михайлович, магистр
Павлов Даниил Александрович, магистр
Первая версия симулятора — Семенов Николай Николаевич, заведующий кафедрой МИСиТ"""
const FALLBACK := "ROV-Sim — Холопов Е. Г., 2026. Аппарат «Петрович»: кафедра МИСиТ СПбГМТУ — Коротицкий Е. В., " + \
		"Кузьменко А. В., Холопов Е. Г., Дунаев А. М., Павлов Д. А. Первая версия симулятора — Семенов Н. Н."
const SHORT := "ROV-Sim, Холопов Е. Г. · аппарат «Петрович», кафедра МИСиТ СПбГМТУ"

static var _text := ""


static func _norm(t: String) -> String:
	return t.replace("\r", "").strip_edges()


## Проверенный текст авторов (строки через \n).
static func text() -> String:
	if _text != "":
		return _text
	if _norm(TEXT).sha256_text() == SHA:
		_text = _norm(TEXT)
	else:
		var f := FileAccess.open(FILE, FileAccess.READ)
		var t := _norm(f.get_as_text()) if f else ""
		_text = t if t.sha256_text() == SHA else FALLBACK
	return _text


## Обе копии на месте и не изменены (проверка в tests/game_tests.gd).
static func intact() -> bool:
	var f := FileAccess.open(FILE, FileAccess.READ)
	return _norm(TEXT).sha256_text() == SHA and f != null and _norm(f.get_as_text()).sha256_text() == SHA
