shader_type spatial;
// Поверхность под водой: освещение считается вручную по модели подводного света (unshaded),
// стандартный свет Godot не используется. Альбедо и яркость задаются в линейных единицах.
render_mode unshaded, cull_back;

#include "res://shaders/underwater.gdshaderinc"

uniform vec3 albedo = vec3(0.15);                 // линейное альбедо
uniform sampler2D albedo_tex : source_color, hint_default_white, filter_nearest_mipmap;
uniform vec2 uv_scale = vec2(1.0);
uniform vec3 emission = vec3(0.0);                // кд/м²

void fragment() {
	vec3 P = (INV_VIEW_MATRIX * vec4(VERTEX, 1.0)).xyz;
	vec3 N = normalize((INV_VIEW_MATRIX * vec4(NORMAL, 0.0)).xyz);
	vec3 a = albedo * texture(albedo_tex, UV * uv_scale).rgb;
	ALBEDO = uw_camera(uw_radiance(CAMERA_POSITION_WORLD, P, N, a, emission), FRAGCOORD.xy);
}
