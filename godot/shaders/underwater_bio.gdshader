shader_type spatial;
// Водоросли и сидячая живность у судна (материалы BIO_* из blender/build_wreck_site.py, сетки и экземпляры): та же модель
// подводного света (underwater.gdshaderinc), двусторонние листы, альбедо × цвет вершин (×1,15). Цвет вершин
// приходит в UV2.xy и UV.y (красный, зелёный, синий), вес колыхания — в UV.x: в пачках экземпляров рендер
// Compatibility подменяет COLOR данными экземпляра (INSTANCE_CUSTOM).
// Колыхание: волновое движение воды у дна — смещение вдоль sway_dir с периодом period, фаза бежит по
// дну (волна длиной wave_len), плюс поперечная составляющая и трепет листа; вес — UV.x (0 у основания).
// Оценка, художественная форма: течение и волны на аппарат в этой сцене не действуют.
render_mode unshaded, cull_disabled;

#include "res://shaders/underwater.gdshaderinc"

uniform vec3 albedo = vec3(0.1);
uniform float sway = 0.0;                    // амплитуда на конце, м
uniform float period = 6.0;                  // период качания, с (волны у дна 4-8 с, оценка)
uniform float wave_len = 9.0;                // длина волны вдоль дна, м
uniform vec3 sway_dir = vec3(0.97, 0.0, -0.24); // направление качания (Godot, горизонтально) = течение у дна в build_wreck_site.py
uniform bool instanced = false;              // экземпляры MultiMesh (game/wreck_life.gd): тон экземпляра в INSTANCE_CUSTOM.rgb

varying vec3 v_tone;
varying vec3 v_col;

void vertex() {
	v_tone = instanced ? INSTANCE_CUSTOM.rgb : vec3(1.0);
	v_col = vec3(UV2.x, UV2.y, UV.y);
	float w = UV.x;                              // вес колыхания (blender/build_wreck_site.py, Batch)
	if (sway > 0.0 && w > 0.0) {
		// смещение считается в мировых осях (MODEL_MATRIX включает преобразование экземпляра) и переводится
		// обратно в оси сетки: world_vertex_coords с пачками экземпляров в Compatibility не работает
		vec3 wp = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
		float ph = 6.2832 * (TIME / period - dot(wp.xz, sway_dir.xz) / wave_len);
		vec3 across = vec3(-sway_dir.z, 0.0, sway_dir.x);
		vec3 off = sway * w * (sway_dir * (0.25 + sin(ph)) + across * 0.35 * sin(1.7 * ph + wp.y * 3.0));
		off.y -= 0.5 * dot(off, off) / max(sway, 0.01) * w;     // конец опускается при отклонении (длина почти та же)
		// трепет: короткая волна бежит по листу к концу (период ≈ 1,3 с), заметна у длинных листьев
		off += sway * 0.18 * w * w * vec3(0.0, 1.0, 0.0) * sin(6.2832 * (TIME / 1.3 - w * 2.0) + wp.x * 5.0);
		VERTEX += (inverse(MODEL_MATRIX) * vec4(off, 0.0)).xyz;
	}
}

void fragment() {
	vec3 P = (INV_VIEW_MATRIX * vec4(VERTEX, 1.0)).xyz;
	vec3 n = FRONT_FACING ? NORMAL : -NORMAL;
	vec3 N = normalize((INV_VIEW_MATRIX * vec4(n, 0.0)).xyz);
	vec3 a = albedo * v_col * 1.15 * v_tone;
	ALBEDO = uw_camera(uw_radiance(CAMERA_POSITION_WORLD, P, N, a, vec3(0.0)), FRAGCOORD.xy);
}
