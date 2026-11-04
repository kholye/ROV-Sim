shader_type canvas_item;
// Последний проход кадра камеры аппарата: перевод прямолинейного кадра Godot в проекцию объектива DiCam 300
// (render/dicam_lens.gd, docs/physics-sources.md, разд. 21) и усиление в линейном свете (окошко «со стороны»).
// from_screen: уже нарисованный кадр (весь экран) или своя текстура (окошко).

uniform sampler2D screen_tex : hint_screen_texture, filter_nearest;
uniform bool from_screen = true;
uniform float gain = 1.0;                    // усиление в линейном свете (своя экспозиция окошка)
// кадр Godot прямолинейный с половиной угла в воде lens_half_water; на экране — равноудалённая проекция с половиной
// угла на воздухе lens_half_air, плоское окно бокса — закон Снелла sin θ_воздух = n·sin θ_вода. Вне поля — чёрное.
uniform bool lens = false;
uniform float lens_half_air = 1.2217;
uniform float lens_half_water = 0.7825;
uniform float lens_n = 1.333;
uniform float lens_aspect = 1.7778;          // ширина / высота экрана

// Точка экрана (проекция объектива) -> точка прямолинейного кадра Godot; z = 0 — вне поля объектива.
vec3 lens_map(vec2 uv) {
	vec2 p = (uv - 0.5) * 2.0 * vec2(1.0, 1.0 / lens_aspect);   // на полуширину
	float r = length(p);
	if (r < 1e-6) {
		return vec3(uv, 1.0);
	}
	float th_a = r * lens_half_air;
	if (th_a >= 1.5707963) {
		return vec3(uv, 0.0);
	}
	float th_w = asin(sin(th_a) / lens_n);
	vec2 q = p / r * tan(th_w) / tan(lens_half_water);
	vec2 uv2 = 0.5 + 0.5 * q * vec2(1.0, lens_aspect);
	float inside = step(0.0, uv2.x) * step(uv2.x, 1.0) * step(0.0, uv2.y) * step(uv2.y, 1.0);
	return vec3(uv2, inside);
}

void fragment() {
	vec2 uv = from_screen ? SCREEN_UV : UV;
	float keep = 1.0;
	if (lens && from_screen) {
		vec3 m = lens_map(uv);
		uv = m.xy;
		keep = m.z;
	}
	vec3 c = (from_screen ? texture(screen_tex, uv).rgb : texture(TEXTURE, uv).rgb) * keep;
	COLOR = vec4(pow(min(pow(c, vec3(2.2)) * gain, vec3(1.0)), vec3(1.0 / 2.2)), 1.0);
}
