shader_type spatial;
// Поверхность воды лабораторного бассейна снизу. Внутри окна Снелла (угол от вертикали < 48,6°) прозрачна —
// там виден зал (hall_refract.gdshader, частичное отражение ≈ 2-6 % не рисуется). За окном — полное внутреннее
// отражение: поверхность как зеркало; отражается толща воды бассейна — её яркость берётся как яркость пелены
// (uw_linf) в точке отражения (стены и дно в отражении не рисуются — упрощение). Над водой — не рисуется.
render_mode unshaded, cull_disabled;

#include "res://shaders/underwater.gdshaderinc"

const float N_W = 1.333;

void fragment() {
	vec3 cam = CAMERA_POSITION_WORLD;
	vec3 P = (INV_VIEW_MATRIX * vec4(VERTEX, 1.0)).xyz;
	vec3 dir = normalize(P - cam);
	if (cam.y >= uw_surface_y || dir.y > sqrt(1.0 - 1.0 / (N_W * N_W))) {
		discard;
	}
	ALBEDO = uw_camera(uw_radiance(cam, P, vec3(0.0, -1.0, 0.0), vec3(0.0), uw_linf(P)), FRAGCOORD.xy);
}
