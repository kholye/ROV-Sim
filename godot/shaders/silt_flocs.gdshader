shader_type particles;
// Хлопья ила (версия 1.2): частицы-метки той же массы, что облако клубов (physics/silt_plume.gd,
// docs/physics-sources.md, разд. 29). Рождаются в пятне размыва под струёй движителя с частотой ∝ размыву
// (game/silt_flocs.gd), в толще струи над дном, или перерождаются внутри клубов облака по их массе; движутся по тому же полю скоростей: течение с профилем у дна
// (Soulsby 1997), струи движителей (Albertson 1950), оседание w_s, турбулентное блуждание с K = κ u* z (u* от
// течения и от струй у дна под хлопком); ложатся на дно (исчезают). Все числа — из rov_params.json через мост.
// Система координат — Godot (Y вверх): перевод сделан в мосте (NedGodot).
render_mode disable_velocity, keep_data;

uniform vec4 em0 = vec4(0.0);      // пятно размыва струи 0: центр (xyz), частиц в секунду (w)
uniform vec4 es0 = vec4(0.05, 0.05, -100.0, 0.0);   // σ по горизонтали, толщина струи σ, высота дна Y, —
uniform vec4 em1 = vec4(0.0);
uniform vec4 es1 = vec4(0.05, 0.05, -100.0, 0.0);
uniform vec4 jo0 = vec4(0.0);      // струя 0: срез (xyz), U0 (w, 0 — нет струи)
uniform vec4 jd0 = vec4(0.0, 0.0, 1.0, 0.054);   // направление (xyz), диаметр D (w)
uniform vec4 jo1 = vec4(0.0);
uniform vec4 jd1 = vec4(0.0, 0.0, 1.0, 0.054);
uniform vec3 cur = vec3(0.0);      // течение, средняя по глубине скорость (с порывами), м/с
uniform float site_h = 0.0;        // глубина места для профиля течения, м (0 — без профиля)
uniform float ws = 0.0005;         // оседание, м/с
uniform float cd_bed = 0.005;
uniform float cd_cur = 0.0025;
uniform float jet_spread = 0.081;
uniform float jet_core = 6.2;
uniform float pool_rate = 1000.0;  // сколько частиц пула перезапускается в секунду (amount / lifetime)
uniform vec4 box = vec4(-1e4, 1e4, -1e4, 1e4);   // стенки бассейна: x мин, x макс, z мин, z макс
uniform float per_kg = 1.0e6;      // хлопьев на кг ила (light_params.json, silt_flocs_per_kg)
// клубы облака (те же глобальные параметры, что у дымки): центр (Godot), масса; σh, σv, высота дна
global uniform vec4 uw_sp0;
global uniform vec4 uw_ss0;
global uniform vec4 uw_sp1;
global uniform vec4 uw_ss1;
global uniform vec4 uw_sp2;
global uniform vec4 uw_ss2;
global uniform vec4 uw_sp3;
global uniform vec4 uw_ss3;
global uniform vec4 uw_sp4;
global uniform vec4 uw_ss4;
global uniform vec4 uw_sp5;
global uniform vec4 uw_ss5;
global uniform vec4 uw_sp6;
global uniform vec4 uw_ss6;
global uniform vec4 uw_sp7;
global uniform vec4 uw_ss7;
global uniform int uw_nsilt;
uniform float r_min = 0.00015;     // радиусы хлопьев, м (n(r) ∝ r^−2)
uniform float r_max = 0.002;

uint hash_u(uint x) {
	x ^= x >> 16u;
	x *= 0x7feb352du;
	x ^= x >> 15u;
	x *= 0x846ca68bu;
	x ^= x >> 16u;
	return x;
}

float rnd(inout uint s) {
	s = hash_u(s);
	return float(s & 0x00ffffffu) / 16777216.0;
}

float gauss(inout uint s) {
	float u1 = max(rnd(s), 1e-7);
	float u2 = rnd(s);
	return sqrt(-2.0 * log(u1)) * cos(6.2831853 * u2);
}

// Скорость, наведённая струёй (круглая струя Albertson: ядро 6,2 D, σ = 0,081 x, не уже D/4).
vec3 jet_v(vec3 X, vec4 o, vec4 d) {
	if (o.w <= 0.0) {
		return vec3(0.0);
	}
	vec3 rel = X - o.xyz;
	float xa = dot(rel, d.xyz);
	if (xa <= 0.0) {
		return vec3(0.0);
	}
	float r2 = dot(rel, rel) - xa * xa;
	float core = jet_core * d.w;
	float Um = xa <= core ? o.w : o.w * core / xa;
	float sig = max(jet_spread * xa, d.w * 0.25);
	return d.xyz * Um * exp(-r2 / (2.0 * sig * sig));
}

float bed_profile(float z, float h) {
	if (z <= 0.0 || h <= 0.0) {
		return h <= 0.0 ? 1.0 : 0.0;
	}
	return z < 0.5 * h ? pow(z / (0.32 * h), 1.0 / 7.0) : 1.07;
}

vec4 puff_sp(int k) {
	return k == 0 ? uw_sp0 : k == 1 ? uw_sp1 : k == 2 ? uw_sp2 : k == 3 ? uw_sp3 : k == 4 ? uw_sp4 : k == 5 ? uw_sp5
			: k == 6 ? uw_sp6 : uw_sp7;
}

vec4 puff_ss(int k) {
	return k == 0 ? uw_ss0 : k == 1 ? uw_ss1 : k == 2 ? uw_ss2 : k == 3 ? uw_ss3 : k == 4 ? uw_ss4 : k == 5 ? uw_ss5
			: k == 6 ? uw_ss6 : uw_ss7;
}

// Рождение (и перерождение отслужившей частицы пула): с частотой размыва — в пятне под струёй (в толще струи
// над дном); с частотой m_k·per_kg / LIFETIME — внутри клуба k облака (гаусс клуба с отражением от дна), так что
// хлопьев в облаке держится столько, сколько весит ил × per_kg (пока пул не исчерпан).
void start() {
	uint s = hash_u(INDEX * 747796405u + RANDOM_SEED);
	float puff_rate = 0.0;
	for (int k = 0; k < 8; k++) {
		if (k < uw_nsilt) {
			puff_rate += puff_sp(k).w * per_kg / LIFETIME;
		}
	}
	float total = em0.w + em1.w + puff_rate;
	TRANSFORM = mat4(1.0);
	VELOCITY = vec3(0.0);
	if (total <= 0.0 || rnd(s) > total / pool_rate) {
		ACTIVE = false;
		CUSTOM = vec4(-1e4, 1.0, 0.0, 0.0);
	} else {
		float pick = rnd(s) * total;
		vec3 p;
		float bed;
		if (pick < em0.w + em1.w) {
			bool first = pick < em0.w;
			vec4 em = first ? em0 : em1;
			vec4 es = first ? es0 : es1;
			p = em.xyz + vec3(gauss(s) * es.x, 0.0, gauss(s) * es.x);
			p.y = es.z + abs(gauss(s)) * es.y;
			bed = es.z;
		} else {
			float acc = em0.w + em1.w;
			int kk = 0;
			for (int k = 0; k < 8; k++) {
				if (k < uw_nsilt) {
					acc += puff_sp(k).w * per_kg / LIFETIME;
					if (pick <= acc && kk == 0 && acc > 0.0) {
						kk = k + 1;
					}
				}
			}
			int k = max(kk - 1, 0);
			vec4 sp = puff_sp(k);
			vec4 ss = puff_ss(k);
			p = sp.xyz + vec3(gauss(s) * ss.x, gauss(s) * ss.y, gauss(s) * ss.x);
			bed = ss.z;
			p.y = bed + abs(p.y - bed);    // отражение от дна (как у клуба)
		}
		TRANSFORM[3].xyz = p;
		float r = 1.0 / (1.0 / r_min - rnd(s) * (1.0 / r_min - 1.0 / r_max));
		CUSTOM = vec4(bed, 0.0, r, rnd(s));    // дно, возраст (доля), радиус, случайное
	}
}

void process() {
	CUSTOM.y += DELTA / LIFETIME;
	vec3 p = TRANSFORM[3].xyz;
	float bed = CUSTOM.x;
	float hgt = max(p.y - bed, 0.0);
	vec3 v = cur * bed_profile(hgt, site_h) + jet_v(p, jo0, jd0) + jet_v(p, jo1, jd1);
	vec3 pb = vec3(p.x, bed, p.z);
	vec3 vb = jet_v(pb, jo0, jd0) + jet_v(pb, jo1, jd1);
	float us = sqrt(cd_cur * dot(cur, cur) + cd_bed * dot(vb, vb));
	float K = 0.4 * us * max(hgt, 0.05);
	v.y -= ws;
	uint s = hash_u(INDEX * 2654435761u + floatBitsToUint(TIME));
	vec3 walk = vec3(gauss(s), gauss(s), gauss(s)) * sqrt(2.0 * K * DELTA);
	p += v * DELTA + walk;
	p.x = clamp(p.x, box.x, box.y);
	p.z = clamp(p.z, box.z, box.w);
	VELOCITY = v;
	TRANSFORM[3].xyz = p;
	if (p.y < bed) {
		ACTIVE = false;     // лёг на дно
	}
}
