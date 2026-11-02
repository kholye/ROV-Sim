shader_type spatial;
// Рыбы и крабы у судна (game/fauna.gd): сетка длиной 1 (нос −Z, хвост +Z), размер — масштаб экземпляра.
// Изгиб тела: бегущая от головы к хвосту волна (длина 0,9 тела), амплитуда растёт к хвосту как s²
// (карангиформное плавание, Bainbridge 1958: размах хвоста ≈ 0,2 длины). Фаза, амплитуда и изгиб на
// повороте приходят данными экземпляра: x — фаза, y — амплитуда хвоста (доля длины), z — изгиб.
// Свет — та же модель (underwater.gdshaderinc); цвет — линейное альбедо вершин в UV.xy и UV2.x (COLOR в пачках
// экземпляров Compatibility подменяется данными экземпляра).
render_mode unshaded, cull_disabled;

#include "res://shaders/underwater.gdshaderinc"

uniform vec3 wave_axis = vec3(1.0, 0.0, 0.0);   // ось изгиба: вбок у рыб, вверх-вниз у камбалы
// Стая целиком на видеокарте (school = true, game/fauna.gd): центр стаи идёт по эллипсу s_center + a1·ra·cos θ +
// a2·rb·sin θ, θ = ω·t; данные экземпляра — место рыбы (x — сдвиг по дуге, м; y — высота над s_h0; z — поперёк)
// и длина рыбы (w). У аппарата (rov_pos) рыбы расступаются на s_flee м. Преобразование экземпляра — единичное.
uniform bool school = false;
uniform vec3 s_center = vec3(0.0);
uniform vec3 s_a1 = vec3(1.0, 0.0, 0.0);
uniform vec3 s_a2 = vec3(0.0, 0.0, 1.0);
uniform vec2 s_radii = vec2(5.0, 5.0);
uniform float s_omega = 0.02;      // рад/с, знак — направление обхода
uniform float s_h0 = 0.0;          // высота центра стаи (Godot y)
uniform float s_flee = 2.5;
uniform float s_min_y = -100.0;
uniform float s_freq = 2.0;        // частота хвоста, Гц (Bainbridge по скорости стаи)
uniform vec3 rov_pos = vec3(10000.0);

void vertex() {
	float s = clamp(VERTEX.z + 0.5, 0.0, 1.0);    // 0 — нос, 1 — конец хвоста
	float env = 0.12 + 0.88 * s * s;
	if (school) {
		vec3 slot = INSTANCE_CUSTOM.xyz;
		float h = fract(sin(float(INSTANCE_ID) * 12.9898) * 43758.5453);
		float R = 0.5 * (s_radii.x + s_radii.y);
		float th = TIME * s_omega + (slot.x + 0.3 * sin(TIME * 0.3 + h * 20.0)) / R;
		vec3 nrm = normalize(s_a1 * cos(th) / s_radii.x + s_a2 * sin(th) / s_radii.y);
		vec3 fw = normalize(s_a1 * (-sin(th) * s_radii.x) + s_a2 * (cos(th) * s_radii.y)) * sign(s_omega);
		vec3 p = s_center + s_a1 * cos(th) * s_radii.x + s_a2 * sin(th) * s_radii.y
				+ nrm * (slot.z + 0.25 * sin(TIME * 0.27 + h * 31.0));
		p.y = s_h0 + slot.y + 0.15 * sin(TIME * 0.23 + h * 17.0);
		vec3 d = p - rov_pos;
		float dl = max(length(d), 1e-3);
		float push = max(s_flee - dl, 0.0);
		p += d / dl * push * 1.3;
		p.y = max(p.y, s_min_y);
		fw = normalize(fw + d / dl * push * 0.6);               // отворачивают от аппарата
		fw.y = clamp(fw.y, -0.4, 0.4);
		fw = normalize(fw);
		vec3 rt = normalize(cross(fw, vec3(0.0, 1.0, 0.0)));
		vec3 up = cross(rt, fw);
		float amp = 0.12 + 0.08 * min(push, 1.0);
		vec3 v = VERTEX + wave_axis * (0.5 * amp * env * sin(TIME * 6.2832 * s_freq + h * 6.2832 - 6.2832 * s / 0.9));
		VERTEX = p + (rt * v.x + up * v.y - fw * v.z) * INSTANCE_CUSTOM.w;
		NORMAL = rt * NORMAL.x + up * NORMAL.y - fw * NORMAL.z;
	} else {
		float ph = INSTANCE_CUSTOM.x;
		float amp = INSTANCE_CUSTOM.y;
		float bend = INSTANCE_CUSTOM.z;
		VERTEX += wave_axis * (0.5 * amp * env * sin(ph - 6.2832 * s / 0.9) + bend * s * s);
	}
}

void fragment() {
	vec3 P = (INV_VIEW_MATRIX * vec4(VERTEX, 1.0)).xyz;
	vec3 n = FRONT_FACING ? NORMAL : -NORMAL;
	vec3 N = normalize((INV_VIEW_MATRIX * vec4(n, 0.0)).xyz);
	ALBEDO = uw_camera(uw_radiance(CAMERA_POSITION_WORLD, P, N, vec3(UV.x, UV.y, UV2.x), vec3(0.0)), FRAGCOORD.xy);
}
