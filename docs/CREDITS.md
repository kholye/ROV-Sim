# Авторство, источники и лицензии

## Автор ROV-Sim

**Холопов Егор Геннадьевич**, 2026: симулятор целиком — физика и её проверки, свет, модели и сцены, интерфейс, код.

## Аппарат «Петрович»

Телеуправляемый подводный аппарат «Петрович» — макет для отработки инженерных решений. Собран и разработан коллективом кафедры морских информационных систем и технологий (МИСиТ, 2350) СПбГМТУ в рамках трёх магистерских работ:

- **Коротицкий Евгений Викторович**, к. т. н., доцент;
- **Кузьменко Александр Владимирович**, старший преподаватель;
- **Холопов Егор Геннадьевич**, магистр;
- **Дунаев Артем Михайлович**, магистр;
- **Павлов Даниил Александрович**, магистр.

## Первая версия симулятора

**Семенов Николай Николаевич**, заведующий кафедрой МИСиТ: первая версия симулятора (сборка Unity), на которой основан ROV-Sim. Из неё взяты правила колец и осмотра судна, штрафы, раскладка бассейна 12 × 25 × 5 м и колец, формат таблицы лидеров.

## Работы, на которых основан проект

Работы Холопова, Дунаева и Павлова используются с разрешения авторов; статья Игнатьевой и Кузьменко цитируется как публикация. Ссылки на разделы — в [`physics-sources.md`](physics-sources.md).

- **Холопов Е. Г.**, магистерская диссертация, СПбГМТУ, 2026: аппарат (корпус, цистерны, датчики, батарея, лампа, камера), система технического зрения, кадры мишени и программы обработки (`data/Kholopov-progs`: контраст, ΔE CIEDE2000), данные для проверки света V5.
- **Дунаев А. М.**, магистерская диссертация, СПбГМТУ, 2026: математическая модель аппарата (ф. 8-32, код прил. А), ПИД глубины (разд. 2.4), опыты в бассейне (рис. 48-49, т. 9: калибровка и проверка V3), шум датчиков по Аллану (т. 5-8: V4), паспорт модуля SSAH-RS220 (прил. Б).
- **Павлов Д. А.** «Исследование информационно-управляющей системы МПР», выпускная квалификационная работа (магистр), СПбГМТУ, 2026: информационно-управляющая система аппарата — канал RS-485, протокол текстовых пакетов и листинг прошивки контроллера (прил. А: смысл команд, порядок телеметрии, значения по умолчанию), инерциальная навигация (МЭМС, затем AHRS SSAH-RS220), программный комплекс оператора в MATLAB App Designer (`data/ROV-pult`: 26-символьный кадр, микширование джойстика, шкала ПИД 0,0-9,9; по нему сделано управление игры), общий вид и характеристики аппарата (рис. 1, т. 2).
- **Игнатьева Н. В., Кузьменко А. В.** «Влияние дальности наблюдения на контрастность изображений подводных объектов», *Морские интеллектуальные технологии*, 2024: метод оценки контраста, осветитель СДВС5 и камера ПВК2HD (т. 1), кривые рис. 10-13 (оцифрованы для V5).

## Источники физики и света

Полные ссылки на формулы и таблицы — в [`physics-sources.md`](physics-sources.md) (раздел указан в скобках).

**Движение аппарата**
- Fossen T. I. *Handbook of Marine Craft Hydrodynamics and Motion Control.* Wiley, 2011 — уравнения 6 ст. св., кинематика, присоединённые массы, течение, движители, рули (1, 6-9).
- Newman J. N. *Marine Hydrodynamics.* MIT Press, 1977, гл. 4 — полосовая теория присоединённых масс (6).
- Lamb H. *Hydrodynamics*, § 373 — продольная присоединённая масса эллипсоида (6, V1(д)).
- DNV-RP-H103 *Modelling and Analysis of Marine Operations*, табл. A-1, A-2 — присоединённые массы круга и пластины (6, 7а).
- Hoerner S. F. *Fluid-Dynamic Drag.* 1965, гл. 3 — коэффициенты сопротивления, поперечное обтекание (7, 7а).
- Jones R. T. NACA Report 835, 1946 — подъёмная сила крыла малого удлинения (7а).
- IEEE Std 952 — дисперсия Аллана для гироскопов (11).

**Свет в воде**
- Pope R. M., Fry E. S. Absorption spectrum (380-700 nm) of pure water. *Appl. Opt.* 36, 8710 (1997); таблица с https://omlc.org/spectra/water/ (17).
- Morel A. Optical properties of pure water and pure sea water, 1974 — рассеяние чистой воды (17).
- Babin M. et al., 2003 — спектральный наклон рассеяния взвесью (17).
- Jaffe J. S., 1990; McGlamery B. L., 1980 — модель однократного рассеяния для подводной съёмки (18).
- Akkaynak D., Treibitz T. A revised underwater image formation model. CVPR 2018 — раздельные прямой сигнал и вуаль, проверка линейности кадра (18, V5).
- Mobley C. D. et al. Phase function effects on oceanic light fields. *Appl. Opt.* 41, 1035 (2002) — фазовая функция Фурнье-Форанд (18).
- Mobley C. D. *Light and Water.* Academic Press, 1994; Kirk J. T. O. *Light and Photosynthesis in Aquatic Ecosystems*, 1984/2011 — свет сверху, видимость, мутность (20, 23, 24, 26).
- Alldredge A. L., Silver M. W. Characteristics, dynamics and significance of marine snow, 1988 — видимая взвесь (24).

## 3D-модели
- **«Malpas Metal Boat Wreck»** — artfletch, https://sketchfab.com/3d-models/malpas-metal-boat-wreck-7a2c49c1be2c48a3a4d80a3f27dae205, лицензия **CC BY 4.0** (http://creativecommons.org/licenses/by/4.0/). Изменено: срезана грунтовая подложка, упрощено с 664 до 80 тыс. треугольников, текстура уменьшена до 4096², судно поставлено на дно с креном и наносами ила (`blender/build_wreck_scan.py`, `build_wreck_site.py`). Используется в сцене «корабль» (`godot/assets/wreck/wreck_site.glb`).
- Аппарат, бассейны, кольца, бочки, якорь, камни — свои, собраны скриптами Blender (`blender/*.py`).
- Зал лаборатории над лабораторным бассейном — свой, по размерам скана LIDAR помещения кафедры (снят Холоповым Е. Г., 2026; скан в сборку не входит): `blender/scan_measure.py`, `build_lab_room.py`, `lab_devices.py`, `bake_lab_room.py`.

## Текстуры
- **Poly Haven** (https://polyhaven.com), лицензия **CC0**: brown_mud_02, brown_mud_03, brown_mud_rocks_01, dense_sand, rock_boulder_dry, rust_coarse_01, green_metal_rust, concrete_wall_006, concrete_wall_008, painted_plaster_wall, distressed_painted_planks, floor_tiles_08, herringbone_parquet, concrete_floor_worn_001, rubber_tiles, anti_skid_tiles (`godot/assets/textures/`, скачивает `work/tools/get_polyhaven.py`).
- Плитка бассейна `pool_tiles` — своя (`work/tools/make_pool_tiles.py`).
- Стенды, плакаты, доска, знак и картон в зале лаборатории — свои (`blender/make_room_textures.py`).

## Шрифты и звук
- **PT Mono** и **PT Sans** — ParaType, лицензия **SIL Open Font License 1.1** (`godot/assets/fonts/PTMono-Regular.ttf`, `PTSans-Regular.ttf`, `PTSans-Bold.ttf`; тексты лицензии рядом: `PTMono-OFL.txt`, `PTSans-OFL.txt`), взяты из https://github.com/google/fonts/tree/main/ofl/ptmono и `.../ofl/ptsans`. PT Mono — интерфейс и панели, PT Sans — главное меню, заставка, подпись фото-режима.
- **Unbounded** — The Unbounded Project Authors, и **IBM Plex Sans / IBM Plex Mono** — IBM Corp., лицензия **SIL Open Font License 1.1** (`godot/assets/fonts/Unbounded-Variable.ttf`, `IBMPlexSans-Variable.ttf`, `IBMPlexMono-Regular.ttf`, тексты лицензий рядом: `Unbounded-OFL.txt`, `IBMPlexSans-OFL.txt`, `IBMPlexMono-OFL.txt`), взяты из https://github.com/google/fonts (`ofl/unbounded`, `ofl/ibmplexsans`, `ofl/ibmplexmono`). Главное меню, страницы меню и пауза.
- **Kenney «Interface Sounds»** — Kenney (www.kenney.nl), лицензия **CC0** (https://creativecommons.org/publicdomain/zero/1.0/), взяты с https://opengameart.org/content/interface-sounds; `godot/assets/audio/ui_*.ogg` (select_002, confirmation_002, back_002, switch_002, toggle_002, question_001), лицензия рядом: `kenney_interface_sounds_license.txt`. Звуки меню.
- **«Aquaria»** — cynicmusic, лицензия **CC0**, https://opengameart.org/content/aquaria; `godot/assets/audio/menu_aquaria.ogg` (переведено из WAV в OGG). Музыка главного меню.
- Остальной звук (движители, цистерны, касания, гул насосов, шорох кабеля, звон металла) синтезируется в игре (`godot/game/rov_audio.gd`).

## Программы и инструменты
- **Godot Engine** 4.7.2 — лицензия MIT, © Juan Linietsky, Ariel Manzur и участники Godot Engine (https://godotengine.org/license). Движок входит в сборку `.exe`; тексты лицензий движка и его сторонних библиотек лежат в сборке, в папке `licenses/`.
- **Blender** 4.5 LTS (GPL) — построение моделей и сцен; в сборку не входит, `.glb` — наши данные.
- **Python** 3.12, **NumPy**, **SciPy**, **matplotlib** (BSD-подобные лицензии) — эталон физики и проверки.
- Разработано с помощью ИИ-помощника Claude (Anthropic).
