shader_type spatial;
// Вид хлопьев ила (частицы shaders/silt_flocs.gdshader): матовый шарик радиуса r, освещённый лампой и светом сверху
// по той же модели, что «морской снег» (underwater_particles.gdshader, разд. 24): L = ρ_p/π·(E_лампы·(1 − cos ψ)/2
// + E_сверху)·e^(−c·D). Мельче min_px пикселей — рисуется min_px с уменьшенной яркостью (тот же световой поток).
// Вблизи камера не в фокусе: пятно размытия не меньше defocus_px / D пикселей (оценка по кадру turbid_1m), поток тот же.
// Появляется и гаснет по возрасту (без мигания при рождении и в конце жизни частицы пула).
render_mode unshaded, blend_add, depth_draw_never, cull_disabled, shadows_disabled;

#include "res://shaders/underwater.gdshaderinc"

uniform float albedo_p = 0.5;
uniform float min_px = 1.6;
uniform float defocus_px = 2.5;      // диаметр пятна размытия на 1 м, px·м (на высоте кадра 720)
uniform float viewport_h = 720.0;
uniform bool debug_show = false;     // --flocs_debug: все хлопья крупно и ярко (проверка рождения и движения)

varying vec3 v_center;
varying float v_cover;

void vertex() {
	vec3 p = MODEL_MATRIX[3].xyz;
	float r = INSTANCE_CUSTOM.z;
	float age = INSTANCE_CUSTOM.y;
	v_center = p;
	vec3 cam = CAMERA_POSITION_WORLD;
	float d = max(length(p - cam), 0.05);
	float f_px = PROJECTION_MATRIX[1][1] * viewport_h * 0.5;
	float r_px = r * f_px / d;
	float rd_px = max(max(r_px, min_px * 0.5), 0.5 * defocus_px * (viewport_h / 720.0) / d);
	if (debug_show) {
		rd_px = 3.0;
	}
	float r_draw = rd_px * d / f_px;
	float fade = smoothstep(0.0, 0.03, age) * (1.0 - smoothstep(0.85, 1.0, age));
	v_cover = (r_px * r_px) / max(rd_px * rd_px, 1e-9) * fade;
	vec3 right = normalize(INV_VIEW_MATRIX[0].xyz);
	vec3 up = normalize(INV_VIEW_MATRIX[1].xyz);
	vec3 wpos = p + (right * VERTEX.x + up * VERTEX.y) * 2.0 * r_draw;
	POSITION = PROJECTION_MATRIX * VIEW_MATRIX * vec4(wpos, 1.0);
}

void fragment() {
	vec2 q = UV * 2.0 - 1.0;
	float disk = 1.0 - smoothstep(0.55, 1.0, length(q));
	if (disk <= 0.0) {
		discard;
	}
	vec3 cam = CAMERA_POSITION_WORLD;
	vec3 to_cam = cam - v_center;
	float D = length(to_cam);
	vec3 lv = v_center - uw_lamp_pos;
	float r = max(length(lv), 0.02);
	vec3 l = lv / r;
	float cos_psi = dot(l, to_cam / D);
	vec3 E_lamp = uw_lamp_intensity(l) / (r * r) * exp(-uw_c * r);
	vec3 Ed = uw_esurf * exp(-uw_kd * max(uw_surface_y - v_center.y, 0.0));
	float lit = 0.5 * (1.0 - cos_psi);
	vec3 L = albedo_p / PI * (E_lamp * lit + Ed) * exp(-uw_c * D);
	vec3 x = clamp(L * uw_exposure * v_cover * disk, 0.0, 1.0);
	if (debug_show) {
		x = vec3(1.0, 0.3, 0.1) * disk;
	}
	int bi = int(mod(FRAGCOORD.x, 4.0)) + 4 * int(mod(FRAGCOORD.y, 4.0));
	x = min(x + (UW_BAYER[bi] + 0.5) / 16.0 / 255.0 * step(1e-7, x.g), vec3(1.0));   // дизеринг только у видимых
	ALBEDO = mix(12.92 * x, 1.055 * pow(x, vec3(1.0 / 2.4)) - 0.055, step(vec3(0.0031308), x));
}
