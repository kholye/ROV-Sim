shader_type spatial;
// Зал над лабораторным бассейном (запечённый свет, blender/bake_lab_room.py): яркость из текстуры, кд/м².
// Камера под водой: каждая вершина сдвигается в видимое место по закону преломления на плоской поверхности
// (n = 1,333): всё, что над водой, сжимается в окно Снелла (конус 48,6° от вертикали). Яркость в воде —
// n² · T · L (сохранение L/n², Френель T для неполяризованного света), дальше ослабление и пелена на пути
// в воде — как у всего подводного (uw_radiance). Камера над водой — просто запечённая яркость.
// Упрощение: смещение линейно внутри грани (рёбра ≤ 0,35 м), волн нет.
render_mode unshaded, cull_back, world_vertex_coords;

#include "res://shaders/underwater.gdshaderinc"

uniform sampler2D light_tex : source_color, filter_linear_mipmap;
uniform float l_ref = 120.0;          // кд/м² при 1,0 текстуры
const float N_W = 1.333;

varying vec3 v_true;

void vertex() {
	vec3 cam = CAMERA_POSITION_WORLD;
	vec3 P = VERTEX;
	v_true = P;
	float d = uw_surface_y - cam.y;
	float h = P.y - uw_surface_y;
	if (d > 0.0 && h > 0.0) {
		vec2 r = P.xz - cam.xz;
		float R = length(r);
		// точка выхода на поверхности: d·tg θw + h·tg θa = R, sin θa = n sin θw (деление пополам по sin θw)
		float lo = 0.0;
		float hi = 0.99999 / N_W;
		for (int i = 0; i < 24; i++) {
			float s = 0.5 * (lo + hi);
			float sa = N_W * s;
			float f = d * s / sqrt(1.0 - s * s) + h * sa / sqrt(1.0 - sa * sa) - R;
			if (f > 0.0) { hi = s; } else { lo = s; }
		}
		float s = 0.5 * (lo + hi);
		float x = d * s / sqrt(1.0 - s * s);
		vec2 u = R > 1e-6 ? r / R : vec2(0.0);
		vec3 S = vec3(cam.x + u.x * x, uw_surface_y, cam.z + u.y * x);
		VERTEX = cam + normalize(S - cam) * (length(S - cam) + length(P - S));
	}
}

void fragment() {
	vec3 cam = CAMERA_POSITION_WORLD;
	vec3 L = texture(light_tex, UV).rgb * l_ref;
	vec3 Pa = (INV_VIEW_MATRIX * vec4(VERTEX, 1.0)).xyz;
	if (cam.y < uw_surface_y) {
		vec3 dir = normalize(Pa - cam);
		float t = (uw_surface_y - cam.y) / max(dir.y, 1e-4);
		vec3 S = cam + dir * t;
		float ci = clamp(dir.y, 0.0, 1.0);                  // cos угла в воде
		float st = N_W * sqrt(1.0 - ci * ci);
		float ct = sqrt(max(1.0 - st * st, 0.0));            // cos угла в воздухе
		float rs = (N_W * ci - ct) / (N_W * ci + ct);
		float rp = (ci - N_W * ct) / (ci + N_W * ct);
		float T = 1.0 - 0.5 * (rs * rs + rp * rp);
		ALBEDO = uw_camera(uw_radiance(cam, S, vec3(0.0, -1.0, 0.0), vec3(0.0), L * N_W * N_W * T), FRAGCOORD.xy);
	} else {
		ALBEDO = uw_camera(L, FRAGCOORD.xy);
	}
}
