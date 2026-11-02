shader_type spatial;
// Текстурированная поверхность под водой: та же модель света (underwater.gdshaderinc), что и
// underwater_surface.gdshader, плюс карта рельефа (нормали, касательное пространство, OpenGL) и
// смесь двух наборов текстур по цвету вершин (дно: RGB — тон крупных пятен, A — доля песка).
// Свет по-прежнему считает uw_radiance; рельеф меняет только нормаль N.
render_mode unshaded, cull_back;

#include "res://shaders/underwater.gdshaderinc"

uniform sampler2D albedo_tex : source_color, hint_default_white, filter_linear_mipmap, repeat_enable;
uniform sampler2D normal_tex : hint_normal, filter_linear_mipmap, repeat_enable;
uniform sampler2D albedo_tex2 : source_color, hint_default_white, filter_linear_mipmap, repeat_enable;
uniform sampler2D normal_tex2 : hint_normal, filter_linear_mipmap, repeat_enable;
uniform bool has_normal = false;
uniform bool use_mix = false;          // вторая текстура по альфе цвета вершин
uniform bool use_tone = false;         // умножать альбедо на RGB цвета вершин (×1,15, см. build_wreck_site.py)
uniform vec2 uv_scale = vec2(1.0);
uniform vec3 albedo_gain = vec3(1.0);  // перевод фото-текстуры в альбедо (оценка, для каждого набора)
uniform float normal_strength = 1.0;
uniform vec3 emission = vec3(0.0);
// Обрастание корпуса (только судно у места крушения, game/wreck.gd): бурый налёт (гидроидный «дёрн», ил)
// на всех гранях, кроме нижних, и светлые «ковры» мелких актиний на стенках — пятна по шуму в мировых
// координатах поверх фото-текстуры скана. Крупные организмы — отдельными экземплярами. Оценка.
uniform float fouling = 0.0;
uniform vec3 turf_albedo = vec3(0.10, 0.085, 0.05);
uniform vec3 carpet_albedo = vec3(0.50, 0.47, 0.40);

float hash3(vec3 p) {
	p = fract(p * 0.3183099 + 0.1);
	p *= 17.0;
	return fract(p.x * p.y * p.z * (p.x + p.y + p.z));
}

float vnoise(vec3 x) {
	vec3 i = floor(x);
	vec3 f = fract(x);
	f = f * f * (3.0 - 2.0 * f);
	return mix(mix(mix(hash3(i), hash3(i + vec3(1, 0, 0)), f.x), mix(hash3(i + vec3(0, 1, 0)), hash3(i + vec3(1, 1, 0)), f.x), f.y),
			mix(mix(hash3(i + vec3(0, 0, 1)), hash3(i + vec3(1, 0, 1)), f.x), mix(hash3(i + vec3(0, 1, 1)), hash3(i + vec3(1, 1, 1)), f.x), f.y), f.z);
}

vec3 nmap(sampler2D t, vec2 uv) {
	vec3 n = texture(t, uv).rgb * 2.0 - 1.0;
	n.xy *= normal_strength;
	return normalize(n);
}

void fragment() {
	vec2 uv = UV * uv_scale;
	vec3 a = texture(albedo_tex, uv).rgb;
	vec3 nt = has_normal ? nmap(normal_tex, uv) : vec3(0.0, 0.0, 1.0);
	if (use_mix) {
		float k = smoothstep(0.15, 0.85, COLOR.a);
		a = mix(a, texture(albedo_tex2, uv).rgb, k);
		if (has_normal) {
			nt = normalize(mix(nt, nmap(normal_tex2, uv), k));
		}
	}
	if (use_tone) {
		a *= COLOR.rgb * 1.15;
	}
	a *= albedo_gain;
	vec3 Nv = normalize(TANGENT * nt.x + BINORMAL * nt.y + NORMAL * nt.z);
	vec3 P = (INV_VIEW_MATRIX * vec4(VERTEX, 1.0)).xyz;
	vec3 N = normalize((INV_VIEW_MATRIX * vec4(Nv, 0.0)).xyz);
	if (fouling > 0.0) {
		float n1 = vnoise(P * 3.2);
		float n2 = vnoise(P * 9.0);
		float turf = fouling * 0.6 * smoothstep(-0.7, 0.2, N.y);
		a = mix(a, turf_albedo * (0.6 + 0.8 * n2), turf);
		float carpet = fouling * 0.85 * smoothstep(0.5, 0.75, n1 * 0.7 + n2 * 0.3) * (1.0 - smoothstep(0.6, 0.9, abs(N.y)));
		float polyp = smoothstep(0.3, 0.8, vnoise(P * 33.0));
		a = mix(a, carpet_albedo * (0.5 + 0.7 * polyp), carpet);
	}
	ALBEDO = uw_camera(uw_radiance(CAMERA_POSITION_WORLD, P, N, a, emission), FRAGCOORD.xy);
}
