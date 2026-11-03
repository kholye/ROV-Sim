// Подводный свет: та же модель, что physics_ref/rov/light.py (docs/physics-sources.md, разд. 17-21).
// Для каждого канала: L = ρ/π·E·exp(−c·D) + ∫ b·β̃(ψ)·I(θ)/r²·exp(−c(r+t)) dt + L∞·(1 − exp(−c·D)).
// Система Godot (Y вверх); все величины приходят глобальными параметрами из render/underwater.gd.

global uniform vec3 uw_c;          // a + b, 1/м
global uniform vec3 uw_b;          // рассеяние, 1/м
global uniform vec3 uw_kd;         // ослабление света сверху K_d, 1/м
global uniform vec4 uw_ff;         // Фурнье-Форанд: nu, k = 4/(3(n−1)²), член 180°, mu_d
global uniform vec3 uw_lamp_pos;
global uniform vec3 uw_lamp_dir;
global uniform vec3 uw_lamp_i;     // I0·цвет, кд (0 = лампа выключена)
global uniform vec3 uw_esurf;      // освещённость под поверхностью, лк
global uniform float uw_surface_y; // высота поверхности воды
global uniform float uw_exposure;  // м²/кд
// Неподвижные источники сцены (подводные светильники бассейна): массивы материала (render/underwater.gd
// раздаёт их всем подводным материалам; глобальные параметры Godot массивов не поддерживают, а чтение
// из float-текстуры в каждом пикселе оказалось в 4 раза медленнее, замер 2026-11-02).
// uw_lp: положение, uw_li: I0·цвет (кд), uw_ld: ось и показатель m в I(θ) = I0·cos^m θ.
uniform vec4 uw_lp[16];
uniform vec4 uw_li[16];
uniform vec4 uw_ld[16];
global uniform int uw_nlights;
global uniform sampler2D uw_halo_lut : filter_linear;   // первообразная фазовой функции для ореола
global uniform float uw_caustics;  // амплитуда каустики у поверхности (0 = нет), спад с глубиной e^(−z/4 м)
global uniform float uw_time;
// облако ила (разд. 29, physics_ref/rov/light.py, silt_terms): до 8 клубов — параметры
// глобальными (массивы материала в каждом из сотен материалов обновлялись 20 раз в секунду — рывки кадров);
// uw_spN: центр (Godot), масса, кг; uw_ssN: σ по горизонтали, σ по вертикали, высота дна (Y), —
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
global uniform vec3 uw_silt_a;     // поглощение на массу ила по каналам, м²/кг
global uniform vec3 uw_silt_b;     // рассеяние на массу ила, м²/кг
global uniform vec3 uw_silt_k;     // a* + B·b*: ослабление в квазиоднократном приближении, м²/кг

const int UW_STEPS = 10;           // шагов интеграла обратного рассеяния (сгущены к камере; сходится уже с 8, v5_godot)
const int UW_MAX_LIGHTS = 16;

float uw_phase(float cos_psi) {
	float nu = uw_ff.x;
	float k = uw_ff.y;
	float s2 = max((1.0 - cos_psi) * 0.5, 1e-6);
	float d = k * s2;
	if (abs(1.0 - d) < 1e-3) {
		d = 1.0 - 1e-3;
	}
	float dn = pow(d, nu);
	float f = (nu * (1.0 - d) - (1.0 - dn) + (d * (1.0 - dn) - nu * (1.0 - d)) / s2)
			/ (4.0 * PI * (1.0 - d) * (1.0 - d) * dn);
	return f + uw_ff.z * (3.0 * cos_psi * cos_psi - 1.0);
}

vec3 uw_lamp_intensity(vec3 l) {
	return uw_lamp_i * max(dot(l, uw_lamp_dir), 0.0);
}

vec3 uw_backscatter(vec3 cam, vec3 dir, float D) {
	vec3 acc = vec3(0.0);
	if (dot(uw_lamp_i, vec3(1.0)) <= 0.0) {
		return acc;
	}
	for (int i = 0; i < UW_STEPS; i++) {
		float s = (float(i) + 0.5) / float(UW_STEPS);
		float t = D * s * s;
		float dt = D * 2.0 * s / float(UW_STEPS);
		vec3 X = cam + dir * t;
		vec3 v = X - uw_lamp_pos;
		float r = max(length(v), 0.02);
		vec3 l = v / r;
		float cos_psi = -dot(l, dir);
		acc += uw_b * uw_phase(cos_psi) * uw_lamp_intensity(l) / (r * r) * exp(-uw_c * (r + t)) * dt;
	}
	return acc;
}

// Каустика: фокусировка света сверху рябью поверхности. Узор: сумма трёх бегущих волн, заострённая
// степенью (среднее ≈ 1); контраст спадает с глубиной (размытие фокусов). Оценка, художественная форма
// на физической основе (рябь не моделируется).
float uw_caustic(vec3 P) {
	if (uw_caustics <= 0.0) {
		return 1.0;
	}
	vec2 q = P.xz * 1.7;
	float t = uw_time * 0.6;
	float w = sin(q.x + t) + sin(0.8 * q.y - 1.3 * t + 1.7) + sin(0.6 * q.x + 0.7 * q.y + 0.9 * t + 4.1);
	float c = pow(clamp(0.5 + w / 6.0, 0.0, 1.0), 4.0) * 6.6;     // среднее ≈ 1
	float depth = max(uw_surface_y - P.y, 0.0);
	return 1.0 + uw_caustics * exp(-depth / 4.0) * (c - 1.0);
}

vec3 uw_ambient_e(vec3 P, vec3 N) {
	vec3 Ed = uw_esurf * exp(-uw_kd * max(uw_surface_y - P.y, 0.0));
	float nu = N.y;
	return Ed * ((1.0 + nu) * 0.5 * uw_caustic(P) + 0.05 * (1.0 - nu) * 0.5);
}

// Неподвижный источник j: положение, сила I0·цвет, ось, показатель m.
vec3 uw_static_intensity(int j, vec3 l) {
	vec4 ax = uw_ld[j];
	float cd = max(dot(l, ax.xyz), 0.0);
	return uw_li[j].rgb * (ax.w == 2.0 ? cd * cd : pow(cd, ax.w));
}

vec3 uw_static_e(vec3 P, vec3 N) {
	vec3 e = vec3(0.0);
	for (int j = 0; j < UW_MAX_LIGHTS; j++) {
		if (j >= uw_nlights) {
			break;
		}
		vec3 lv = P - uw_lp[j].xyz;
		float r = max(length(lv), 0.05);
		if (r > 12.0) {          // дальше 12 м вклад < 0,2 % ближнего (обратный квадрат и ослабление)
			continue;
		}
		vec3 l = lv / r;
		float cos_i = (N == vec3(0.0)) ? 1.0 : max(-dot(l, N), 0.0);
		e += uw_static_intensity(j, l) * cos_i / (r * r) * exp(-uw_c * r);
	}
	return e;
}

// Ореол неподвижных источников (однократное рассеяние вдоль луча), без цикла по шагам.
// На луче r² = h² + (t − t0)², где h — расстояние источника от прямой луча, t0 — ближайшая точка.
// Замена φ = atan((t − t0)/h): dt/r² = dφ/h и ψ = φ + 90°, поэтому ∫ β̃(ψ)/r² dt = (F(φb) − F(φa))/h,
// F — первообразная β̃(φ + 90°), таблица uw_halo_lut (256 значений, считается в render/underwater.gd).
// Приближение: ослабление e^(−c(r+t)) и диаграмма источника берутся в ближайшей точке отрезка (оценка).
float uw_halo_F(float phi) {
	// узел i таблицы (φ_i = −π/2 + π·i/255) лежит в центре текселя (i + 0,5)/256; у краёв без выхода за таблицу:
	// иначе фильтрация смешивает первый узел с последним и ореол у самого светильника становится отрицательным
	float u = clamp(phi / PI + 0.5, 0.0, 1.0);
	return texture(uw_halo_lut, vec2((u * 255.0 + 0.5) / 256.0, 0.5)).r;
}

vec3 uw_static_halo(vec3 cam, vec3 dir, float D) {
	vec3 acc = vec3(0.0);
	for (int j = 0; j < UW_MAX_LIGHTS; j++) {
		if (j >= uw_nlights) {
			break;
		}
		vec3 Lp = uw_lp[j].xyz;
		float t0 = dot(Lp - cam, dir);
		float h = max(length(Lp - cam - dir * t0), 0.03);
		if (h > 4.0) {           // луч проходит дальше 4 м от источника: ореол пренебрежим
			continue;
		}
		float G = uw_halo_F(atan((D - t0) / h)) - uw_halo_F(atan(-t0 / h));
		float tc = clamp(t0, 0.0, D);
		vec3 v = cam + dir * tc - Lp;
		float rc = max(length(v), 0.03);
		acc += uw_b * uw_static_intensity(j, v / rc) * exp(-uw_c * (rc + tc)) * (G / h);
	}
	return acc;
}

vec3 uw_linf(vec3 cam) {
	vec3 Ed = uw_esurf * exp(-uw_kd * max(uw_surface_y - cam.y, 0.0));
	return uw_b * Ed / uw_ff.w / (4.0 * PI * uw_c);
}

// erf (Абрамовиц, Стиган 7.1.26, ошибка < 1,5e-7)
float uw_erf(float x) {
	float t = 1.0 / (1.0 + 0.3275911 * abs(x));
	float y = 1.0 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592)
			* t * exp(-x * x);
	return sign(x) * y;
}

// Один клуб: интеграл концентрации вдоль луча M (точно, с отражением от дна) и точка луча t*, ближайшая к центру;
// копит Σ M, насыщение рассеяния b*/(2k)·(1 − e^(−2kM)) и Σ M·t* (средняя по массе точка).
void uw_silt_one(vec4 sp, vec4 ss, vec3 cam, vec3 dir, float D, inout float mm, inout vec3 sat, inout float mt,
		inout float mt2) {
	vec3 C = sp.xyz;
	float sh = ss.x;
	float sv = ss.y;
	vec3 inv = vec3(1.0 / (sh * sh), 1.0 / (sv * sv), 1.0 / (sh * sh));
	float a2 = dot(dir * dir, inv);
	float a = sqrt(a2);
	float norm = sp.w / (15.749609945722419 * sh * sh * sv);
	float M = 0.0;
	float tstar = 0.0;
	for (int k = 0; k < 2; k++) {
		vec3 Ck = k == 0 ? C : vec3(C.x, 2.0 * ss.z - C.y, C.z);
		vec3 q0 = cam - Ck;
		float qw = dot(dir * q0, inv);
		float t0 = -qw / a2;
		if (k == 0) {
			tstar = clamp(t0, 0.0, D);
		}
		float d2 = max(dot(q0 * q0, inv) - qw * qw / a2, 0.0);
		if (d2 < 40.0) {
			M += norm * exp(-0.5 * d2) * 1.2533141373155003 / a
					* (uw_erf(a * (D - t0) * 0.7071067811865476) + uw_erf(a * t0 * 0.7071067811865476));
		}
	}
	if (M <= 0.0) {
		return;
	}
	mm += M;
	sat += uw_silt_b / (2.0 * uw_silt_k) * (1.0 - exp(-2.0 * uw_silt_k * M));
	mt += M * tstar;
	mt2 += M * (tstar * tstar + 1.0 / a2);
}

// Облако ила на луче (как silt_terms эталона): Tc — пропускание чёткого изображения e^(−(a* + b*)·M), Tk — яркости
// с учётом рассеяния вперёд e^(−k·M) (рисунок размыт), S — добавка яркости: освещённость (лампа, свет сверху)
// одна на луч — в средней по массе точке клубов.
void uw_silt(vec3 cam, vec3 dir, float D, out vec3 Tc, out vec3 Tk, out vec3 S) {
	float mm = 0.0;
	vec3 sat = vec3(0.0);
	float mt = 0.0;
	float mt2 = 0.0;
	if (uw_nsilt > 0) uw_silt_one(uw_sp0, uw_ss0, cam, dir, D, mm, sat, mt, mt2);
	if (uw_nsilt > 1) uw_silt_one(uw_sp1, uw_ss1, cam, dir, D, mm, sat, mt, mt2);
	if (uw_nsilt > 2) uw_silt_one(uw_sp2, uw_ss2, cam, dir, D, mm, sat, mt, mt2);
	if (uw_nsilt > 3) uw_silt_one(uw_sp3, uw_ss3, cam, dir, D, mm, sat, mt, mt2);
	if (uw_nsilt > 4) uw_silt_one(uw_sp4, uw_ss4, cam, dir, D, mm, sat, mt, mt2);
	if (uw_nsilt > 5) uw_silt_one(uw_sp5, uw_ss5, cam, dir, D, mm, sat, mt, mt2);
	if (uw_nsilt > 6) uw_silt_one(uw_sp6, uw_ss6, cam, dir, D, mm, sat, mt, mt2);
	if (uw_nsilt > 7) uw_silt_one(uw_sp7, uw_ss7, cam, dir, D, mm, sat, mt, mt2);
	Tc = exp(-mm * (uw_silt_a + uw_silt_b));
	Tk = exp(-mm * uw_silt_k);
	S = vec3(0.0);
	if (mm > 0.0) {
		float t = mt / mm;
		float s2 = max(mt2 / mm - t * t, 0.0);    // протяжённость облака вдоль луча: сглаживание у лампы
		vec3 P = cam + dir * t;
		vec3 lv = P - uw_lamp_pos;
		float r = max(length(lv), 0.02);
		vec3 l = lv / r;
		float re2 = r * r + s2;
		vec3 Ein = uw_phase(min(-dot(l, dir), r * inversesqrt(re2))) * uw_lamp_intensity(l) / re2 * exp(-uw_c * (r + t));
		Ein += uw_esurf * exp(-uw_kd * max(uw_surface_y - P.y, 0.0)) / (4.0 * PI * uw_ff.w) * exp(-uw_c * t);
		S = sat * Ein;
	}
}

const float UW_SILT_BLUR_ALBEDO = 0.15;   // рисунок за облаком размыт: в рассеянной вперёд части — среднее альбедо

// Яркость точки P (нормаль N) для камеры cam; emission — собственная яркость поверхности, кд/м².
vec3 uw_radiance(vec3 cam, vec3 P, vec3 N, vec3 albedo, vec3 emission) {
	vec3 V = P - cam;
	float D = max(length(V), 1e-4);
	vec3 dir = V / D;
	vec3 lv = P - uw_lamp_pos;
	float r = max(length(lv), 0.02);
	vec3 l = lv / r;
	float cos_i = max(-dot(l, N), 0.0);
	vec3 e_irr = uw_lamp_intensity(l) * cos_i / (r * r) * exp(-uw_c * r) + uw_ambient_e(P, N) + uw_static_e(P, N);
	vec3 T = exp(-uw_c * D);
	vec3 path = uw_backscatter(cam, dir, D) + uw_static_halo(cam, dir, D) + uw_linf(cam) * (1.0 - T);
	if (uw_nsilt > 0) {
		vec3 Tc;
		vec3 Tk;
		vec3 S;
		uw_silt(cam, dir, D, Tc, Tk, S);
		// размытая часть: освещённость гладкой поверхности, обращённой к камере (без рельефа и рисунка)
		vec3 e_blur = uw_lamp_intensity(l) * max(dot(l, dir), 0.0) / (r * r) * exp(-uw_c * r) + uw_ambient_e(P, vec3(0.0));
		return (albedo * Tc * e_irr + UW_SILT_BLUR_ALBEDO * (Tk - Tc) * e_blur) / PI * T + emission * Tk * T + path * Tk + S;
	}
	return albedo / PI * e_irr * T + emission * T + path;
}

// Камера: экспозиция, обрезка и кривая sRGB.
// Рендер Compatibility хранит 3D-кадр в 8-битном ЛИНЕЙНОМ буфере: вывод шейдера он понимает как sRGB,
// переводит в линейный, округляет до 1/255 и при показе снова кодирует в sRGB (установлено пробой
// значений, docs/verification-report.md, V5-порт). Тёмные тона из-за этого слипаются (sRGB < 13 -> 0).
// Поэтому до кодирования добавляется упорядоченный дизеринг Байера 4×4 на [0, 1) шага линейного буфера:
// среднее по блоку 4×4 точное, а зерно в тенях и так часть стиля (этап 5).
const float UW_BAYER[16] = float[16](0.0, 8.0, 2.0, 10.0, 12.0, 4.0, 14.0, 6.0,
		3.0, 11.0, 1.0, 9.0, 15.0, 7.0, 13.0, 5.0);

vec3 uw_camera(vec3 L, vec2 frag) {
	vec3 x = clamp(L * uw_exposure, 0.0, 1.0);
	int i = int(mod(frag.x, 4.0)) + 4 * int(mod(frag.y, 4.0));
	x = clamp(x + (UW_BAYER[i] + 0.5) / 16.0 / 255.0, 0.0, 1.0);   // буфер отбрасывает дробь: шум в [0, 1) шага
	return mix(12.92 * x, 1.055 * pow(x, vec3(1.0 / 2.4)) - 0.055, step(vec3(0.0031308), x));
}
