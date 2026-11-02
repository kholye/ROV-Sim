shader_type canvas_item;
// Помехи видеоканала у предела кабеля (game/tether.gd): «снег», полосы срыва строчной развёртки и
// бегущая тёмная полоса, сила amount 0..1. Оформление, не физика.

uniform float amount = 0.0;

float hash(vec2 p) {
	return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453);
}

void fragment() {
	vec2 uv = SCREEN_UV;
	float t = floor(TIME * 24.0);
	float line = floor(uv.y * 240.0);
	float tear = step(1.0 - 0.35 * amount, hash(vec2(line * 0.13, t)));          // строки с срывом
	float snow = hash(floor(uv * vec2(427.0, 240.0)) + vec2(t * 7.1, t * 3.7));
	float roll = smoothstep(0.0, 0.08, abs(fract(uv.y - TIME * 0.21) - 0.5));       // бегущая полоса
	float k = amount * amount;                                                        // мягко в начале, сплошь у предела
	float a = clamp(k * (0.6 * snow + 0.7 * tear) + k * amount * 0.5 * (1.0 - roll), 0.0, 1.0);
	COLOR = vec4(vec3(snow * 0.8 + 0.1), a);
}
