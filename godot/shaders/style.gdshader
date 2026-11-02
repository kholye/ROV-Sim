shader_type canvas_item;
// Стиль последним проходом (свет по физике, стиль сверху и отключаем): «чёткие» крупные пиксели, ограниченное число уровней
// на канал с упорядоченным дизерингом Байера 4×4, плёночное зерно, виньетка. Физика света до этого
// посчитана полностью (shaders/underwater.gdshaderinc); выключается клавишей Tab (научный вид).
// from_screen: стилизовать уже нарисованный кадр (весь экран) или свою текстуру (окошко).

uniform sampler2D screen_tex : hint_screen_texture, filter_nearest;
uniform bool from_screen = true;
uniform vec2 low_res = vec2(427.0, 240.0);   // сетка «пикселей» стиля
uniform float levels = 12.0;                 // уровней на канал
uniform float grain = 0.025;                 // СКО зерна (доля полной яркости)
uniform float vignette = 0.45;               // затемнение в углах: 1 − k·r²
uniform float gamma_k = 1.15;                // лёгкое «проваливание» теней
uniform bool stylize = true;                 // false: только усиление (окошко в научном виде)
uniform float gain = 1.0;                    // усиление в линейном свете (своя экспозиция окошка)

float bayer4(vec2 p) {
	int x = int(mod(p.x, 4.0));
	int y = int(mod(p.y, 4.0));
	int i = x + y * 4;
	int m[16] = int[16](0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5);
	return float(m[i]) / 16.0 - 0.5;
}

float hash(vec2 p) {
	return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453);
}

vec3 sample_at(vec2 uv, sampler2D own) {
	vec3 c = from_screen ? texture(screen_tex, uv).rgb : texture(own, uv).rgb;
	return pow(min(pow(c, vec3(2.2)) * gain, vec3(1.0)), vec3(1.0 / 2.2));
}

void fragment() {
	vec2 uv = from_screen ? SCREEN_UV : UV;
	if (!stylize) {
		COLOR = vec4(sample_at(uv, TEXTURE), 1.0);
	} else {
		vec2 px = floor(uv * low_res);
		vec3 c = sample_at((px + 0.5) / low_res, TEXTURE);
		// зерно меняется 24 раза в секунду, по крупным пикселям; приблизительно гауссово (сумма двух)
		float t = floor(TIME * 24.0);
		float n = (hash(px + t * 17.0) + hash(px * 1.7 + t * 31.0) - 1.0) * 1.73;
		c += grain * n;
		vec2 d = uv * 2.0 - 1.0;
		c *= clamp(1.0 - vignette * dot(d, d) * 0.5, 0.0, 1.0);
		c = pow(clamp(c, 0.0, 1.0), vec3(gamma_k));
		c = floor(c * (levels - 1.0) + 0.5 + bayer4(px)) / (levels - 1.0);
		COLOR = vec4(clamp(c, 0.0, 1.0), 1.0);
	}
}
