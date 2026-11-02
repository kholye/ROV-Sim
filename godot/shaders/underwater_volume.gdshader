shader_type spatial;
// «Бесконечная» вода: сфера вокруг камеры (изнутри) там, где луч не встречает предметов.
// Дальность берётся до сферы (50 м): пропускание exp(−c·50) пренебрежимо, остаются вуаль и
// обратное рассеяние света лампы.
// Прозрачный проход (ALPHA = 1): рисуется после непрозрачных предметов, поэтому дорогой расчёт идёт только
// в пикселях, где луч не встретил предмет (иначе сфера с центром у камеры рисовалась первой на весь экран).
render_mode unshaded, cull_front, depth_draw_never, blend_mix;

#include "res://shaders/underwater.gdshaderinc"

void fragment() {
	vec3 P = (INV_VIEW_MATRIX * vec4(VERTEX, 1.0)).xyz;
	ALBEDO = uw_camera(uw_radiance(CAMERA_POSITION_WORLD, P, vec3(0.0, 1.0, 0.0), vec3(0.0), vec3(0.0)), FRAGCOORD.xy);
	ALPHA = 1.0;
}
