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
	ALBEDO = uw_camera(uw_radiance(CAMERA_POSITION_WORLD, P, N, a, emission), FRAGCOORD.xy);
}
