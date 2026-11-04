shader_type spatial;
// Видимая взвесь (крупные частицы, «морской снег»): каждая частица — шарик радиуса r (данные экземпляра),
// освещённый лампой и светом сверху по той же модели (underwater.gdshaderinc). Яркость частицы
// L = ρ_p·E/π: частицы 0,3-3 мм много больше длины волны и отражают как матовые тела (геометрическая
// оптика), а не как мелкая взвесь с фазовой функцией Фурнье-Форанд (та даёт назад в ~40 раз меньше;
// мелкая взвесь уже учтена как вуаль). Ослабление до камеры e^(−c·D). Частицы мельче пикселя рисуются не меньше MIN_PX пикселей, яркость делится на отношение
// площадей (тот же световой поток: так выглядит размытие объектива). Смешение аддитивное в линейном буфере.
// Частицы живут в кубе BOX вокруг камеры и переносятся при выходе (бесконечная вода).
render_mode unshaded, blend_add, depth_draw_never, cull_disabled, shadows_disabled;

#include "res://shaders/underwater.gdshaderinc"

uniform float box = 6.0;             // сторона куба вокруг камеры, м
uniform float albedo_p = 0.5;        // альбедо частиц (оценка)
uniform vec3 offset = vec3(0.0);   // накопленный снос течением и оседание, м (считает render/suspension.gd)
uniform float min_px = 1.6;
uniform float viewport_h = 720.0;

varying vec3 v_center;
varying float v_cover;

void vertex() {
	vec3 seed = INSTANCE_CUSTOM.xyz;                  // 0..1
	float r = INSTANCE_CUSTOM.w;                      // радиус, м
	// броуновское блуждание: медленные синусы со случайной фазой
	vec3 wob = 0.03 * vec3(sin(uw_time * 0.31 + seed.x * 40.0), sin(uw_time * 0.23 + seed.y * 40.0), sin(uw_time * 0.27 + seed.z * 40.0));
	vec3 p = seed * box + offset + wob;
	vec3 cam = CAMERA_POSITION_WORLD;
	p = cam + mod(p - cam, vec3(box)) - vec3(box * 0.5);
	v_center = p;
	float d = max(length(p - cam), 0.05);
	// размер на экране: не меньше min_px (фокусное расстояние в пикселях по высоте: PROJECTION_MATRIX[1][1]·h/2)
	float f_px = PROJECTION_MATRIX[1][1] * viewport_h * 0.5;
	float r_px = r * f_px / d;
	float r_draw = max(r, min_px * 0.5 * d / f_px);
	v_cover = (r_px * r_px) / max(pow(r_draw * f_px / d, 2.0), 1e-9);
	// billboard к камере
	vec3 right = normalize(INV_VIEW_MATRIX[0].xyz);
	vec3 up = normalize(INV_VIEW_MATRIX[1].xyz);
	vec3 wpos = p + (right * VERTEX.x + up * VERTEX.y) * 2.0 * r_draw;
	POSITION = PROJECTION_MATRIX * VIEW_MATRIX * vec4(wpos, 1.0);
}

void fragment() {
	vec2 q = UV * 2.0 - 1.0;
	float disk = 1.0 - smoothstep(0.6, 1.0, length(q));
	if (disk <= 0.0) {
		discard;
	}
	vec3 cam = CAMERA_POSITION_WORLD;
	vec3 to_cam = cam - v_center;
	float D = length(to_cam);
	vec3 lv = v_center - uw_lamp_pos;
	float r = max(length(lv), 0.02);
	vec3 l = lv / r;
	float cos_psi = dot(l, to_cam / D);               // угол между светом лампы и направлением на камеру
	vec3 E_lamp = uw_lamp_intensity(l) / (r * r) * exp(-uw_c * r);
	vec3 Ed = uw_esurf * exp(-uw_kd * max(uw_surface_y - v_center.y, 0.0));
	// освещённая половина шарика видна камере на долю (1 + cos ψ')/2, ψ' — угол лампа-частица-камера
	float lit = 0.5 * (1.0 - cos_psi);
	vec3 L = albedo_p / PI * (E_lamp * lit + Ed + 0.5 * uw_static_e(v_center, vec3(0.0))) * exp(-uw_c * D);
	vec3 x = clamp(L * uw_exposure * v_cover * disk, 0.0, 1.0);
	// буфер отбрасывает дробь: дизеринг [0, 1) шага сохраняет среднее даже у очень слабых частиц
	int bi = int(mod(FRAGCOORD.x, 4.0)) + 4 * int(mod(FRAGCOORD.y, 4.0));
	x = min(x + (UW_BAYER[bi] + 0.5) / 16.0 / 255.0, vec3(1.0));
	// аддитивно в линейный буфер: вывод понимается как sRGB, поэтому кодируем
	ALBEDO = mix(12.92 * x, 1.055 * pow(x, vec3(1.0 / 2.4)) - 0.055, step(vec3(0.0031308), x));
}
