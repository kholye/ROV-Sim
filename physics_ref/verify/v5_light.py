"""V5: подводный свет против кадров мишени и выводов статьи Игнатьевой и Кузьменко (2024).

Шаги:
 1. Кадр в воде линеен по альбедо: в каждом канале  I_lin = S·ρ + V  (сигнал и вуаль; Akkaynak & Treibitz 2018).
    S и V находятся по 10 секторам МНК (ρ из эталона на воздухе), отношение V/S не зависит от экспозиции,
    усиления и мощности лампы: это и сравнивается с моделью. Камера считается sRGB (оценка).
 2. ПОДГОНКА: рассеяние взвеси b_p550 по V/S зелёного канала двух кадров СДВС5 2,7 м (т. 4 Холопова, 50 и 100 %).
 3. ПРЕДСКАЗАНИЯ (без подгонки): V/S красного и синего каналов; контраст секторов на 2,7 м (т. 4) при
    автоэкспозиции, настроенной на средний уровень того же кадра; кривые статьи (а)-(г); ΔE на 1 / 2 / 2,7 м.
Запуск: python v5_light.py [--write]  (--write записывает b_p550 в light_params.json)
"""
import json
import sys

import numpy as np
from PIL import Image
from scipy.optimize import brentq

from common import OUT, ROOT, plt, save_results, verdict
from rov import light

p = light.load()
fr = json.loads((OUT / "v5_frames.json").read_text(encoding="utf-8"))
NAMES = fr["sector_names"]
SHOWN = [0, 1, 2, 3, 4, 5, 6, 7, 9]              # без чёрного фона (9-й)
res = {}

# ---------- 1. альбедо и линейная модель кадра ----------
et = light.srgb_decode(np.array(fr["color"]["etalon"]) / 255)
ALB = et / et[9] * p["albedo_white"]               # (10, 3), белый = albedo_white во всех каналах
res["albedo"] = ALB.tolist()


def linfit(vals):
    """vals: (10, 3) 0..255 -> S, V, V/S, R² по каналам."""
    y = light.srgb_decode(np.asarray(vals, float) / 255)
    out = {"S": [], "V": [], "VS": [], "R2": []}
    for c in range(3):
        A = np.vstack([ALB[:, c], np.ones(10)]).T
        (s, v), *_ = np.linalg.lstsq(A, y[:, c], rcond=None)
        r2 = 1 - np.sum((y[:, c] - A @ [s, v]) ** 2) / np.sum((y[:, c] - y[:, c].mean()) ** 2)
        for k, x in zip(out, (s, v, v / s, r2)):
            out[k].append(float(x))
    return out


frames = {"СДВС5 50 %, 2,7 м (т. 4)": fr["chart"]["LED 50%"]["median_rgb"],
          "СДВС5 100 %, 2,7 м (т. 4)": fr["chart"]["LED 100%"]["median_rgb"]}
order = fr["led_compare_order"]
lab = {"sdvsLED_50.png": "СДВС5 50 %, 2,7 м (т. 12)", "sdvsLED_100.png": "СДВС5 100 %, 2,7 м (т. 12)",
       "myLED_50.png": "лампа аппарата 50 %, 2,7 м (т. 12)", "myLED_100.png": "лампа аппарата 100 %, 2,7 м (т. 12)"}
for f in order:
    frames[lab[f]] = fr["led_compare"][f]["median_rgb"]
for k, n in [("clear_1m_original", "лампа аппарата, 1 м (ΔE)"), ("clear_2m_original", "СДВС5, 2 м (ΔE)"),
             ("clear_2700mm_original", "СДВС5, 2,7 м (ΔE)"), ("murky_1m_original", "мутная, 1 м (ΔE)")]:
    frames[n] = fr["color"][k]
meas = {k: linfit(v) for k, v in frames.items()}
res["measured_linear"] = meas
print("1. Кадр = S·ρ + V по каналам R, G, B:")
for k, m in meas.items():
    print(f"  {k:38s} V/S = {np.round(m['VS'], 3)}  R² = {np.round(m['R2'], 3)}")

# ---------- геометрия опытов ----------
HFOV = np.radians(p["pvk_hfov_water_deg"])
F_PX = 960 / np.tan(HFOV / 2)                      # фокус ПВК в пикселях кадра 1920×1080
PLATE_PX = (1140, 855)                             # центр планшета на кадрах т. 4 (углы plate_corners.mat)
OFF = np.array([(PLATE_PX[0] - 960) / F_PX, (PLATE_PX[1] - 540) / F_PX, 1.0])
OFF /= np.linalg.norm(OFF)
CAM = np.zeros(3)                                  # камера: x вправо, y вниз, z вдоль оси


A_EXTRA = np.zeros(3)     # доп. поглощение воды бассейна (R, G, B), подгоняется ниже; G = 0 по определению


def setup(kind, d, base, power, bp, ray=OFF):
    """kind 'sdvs5': лампа сбоку на base (оценка: направление не известно), ось параллельна камере;
    'own': лампа аппарата по модели (58 мм позади, 95,5 мм ниже объектива)."""
    w = light.Water(p, b_p550=bp, a_extra=A_EXTRA)
    if kind in ("sdvs5", "own_rig"):    # own_rig: лампа аппарата на раме вместо СДВС5 (т. 12, оценка)
        name = "sdvs5" if kind == "sdvs5" else "own"
        lamp = light.Lamp((base, 0, 0), (0, 0, 1), light.lamp_intensity_I0(p, name, power), p[name + "_rgb"])
    else:
        dx, _, dz = p["own_pos_cam"]                   # NED тела: x вперёд, z вниз -> камера: z вперёд, y вниз
        lamp = light.Lamp((0, dz, dx), (0, 0, 1), light.lamp_intensity_I0(p, "own", power), p["own_rgb"])
    return w, lamp


def plate_radiance(kind, d, base, power, bp, albedo=ALB, ray=OFF):
    """Яркость (10, 3) секторов планшета на дальности d (планшет перпендикулярен лучу)."""
    w, lamp = setup(kind, d, base, power, bp)
    N = len(albedo)
    dirs = np.repeat(ray[None], N, 0)
    return light.radiance(CAM, dirs, np.full(N, d), -dirs, albedo, lamp, w, n=1500)


def model_vs(kind, d, base, bp):
    L1 = plate_radiance(kind, d, base, 0.5, bp, albedo=np.ones((1, 3)))
    L0 = plate_radiance(kind, d, base, 0.5, bp, albedo=np.zeros((1, 3)))
    return (L0 / (L1 - L0))[0]


# ---------- 2. подгонка: b_p550 по зелёному, доп. поглощение a_x по красному и синему ----------
VS_T4 = np.mean([meas["СДВС5 50 %, 2,7 м (т. 4)"]["VS"], meas["СДВС5 100 %, 2,7 м (т. 4)"]["VS"]], axis=0)
bp_fit = 0.3
for _ in range(6):                     # попеременно: b по G, затем a_x по R и B (сходится за 3-4 прохода)
    bp_fit = brentq(lambda b: model_vs("sdvs5", 2.7, 0.5, b)[1] - VS_T4[1], 0.02, 1.5, xtol=1e-5)
    for c in (0, 2):
        def f(a, c=c):
            A_EXTRA[c] = a
            return model_vs("sdvs5", 2.7, 0.5, bp_fit)[c] - VS_T4[c]
        A_EXTRA[c] = brentq(f, -0.05, 1.0, xtol=1e-5)
res["bp550_fit"] = bp_fit
res["a_extra_fit"] = A_EXTRA.tolist()
print(f"\n2. Подогнано по кадрам т. 4 (2,7 м, V/S = {np.round(VS_T4, 3)}): b_p550 = {bp_fit:.3f} 1/м, "
      f"доп. поглощение R, G, B = {np.round(A_EXTRA, 3)} 1/м")
wfit = light.Water(p, b_p550=bp_fit, a_extra=A_EXTRA)
print(f"   c = a + b по каналам R, G, B: {np.round(wfit.c, 3)} 1/м; видимость 4,6/c_G ≈ {4.6 / wfit.c[1]:.1f} м")

# ---------- 3. предсказание V/S ----------
pred = {}
for k, kind, d, base in [("СДВС5 50 %, 2,7 м (т. 4)", "sdvs5", 2.7, 0.5), ("СДВС5 100 %, 2,7 м (т. 4)", "sdvs5", 2.7, 0.5),
                         ("СДВС5 50 %, 2,7 м (т. 12)", "sdvs5", 2.7, 0.5), ("лампа аппарата 50 %, 2,7 м (т. 12)", "own_rig", 2.7, 0.5),
                         ("лампа аппарата, 1 м (ΔE)", "own", 1.0, 0), ("СДВС5, 2 м (ΔE)", "sdvs5", 2.0, 0.5),
                         ("СДВС5, 2,7 м (ΔE)", "sdvs5", 2.7, 0.5)]:
    pred[k] = model_vs(kind, d, base, bp_fit).tolist()
res["predicted_vs"] = pred
print("\n3. V/S: измерено против модели (R, G, B). Две первые строки подогнаны (среднее), остальные предсказания")
for k, v in pred.items():
    m = meas[k]["VS"]
    print(f"  {k:38s} изм. {np.round(m, 3)}  модель {np.round(v, 3)}  отношение {np.round(np.array(m) / v, 2)}")

bp_each = {}
for k, kind, d, base in [("СДВС5 50 %, 2,7 м (т. 12)", "sdvs5", 2.7, 0.5), ("лампа аппарата 50 %, 2,7 м (т. 12)", "own_rig", 2.7, 0.5),
                         ("лампа аппарата, 1 м (ΔE)", "own", 1.0, 0), ("СДВС5, 2 м (ΔE)", "sdvs5", 2.0, 0.5),
                         ("СДВС5, 2,7 м (ΔE)", "sdvs5", 2.7, 0.5), ("мутная, 1 м (ΔE)", "own", 1.0, 0)]:
    bp_each[k] = brentq(lambda b: model_vs(kind, d, base, b)[1] - meas[k]["VS"][1], 0.005, 6.0, xtol=1e-4)
res["bp550_per_frame"] = bp_each
res["turbid_bp550_fit"] = bp_each["мутная, 1 м (ΔE)"]
print("  b_p550, при котором модель повторяет V/S зелёного каждого кадра (разброс воды между съёмками):")
for k, v in bp_each.items():
    print(f"    {k:38s} {v:.2f} 1/м")

# ---------- автоэкспозиция и контраст ----------
RHO_BOTTOM = 0.15        # альбедо дна для автоэкспозиции (оценка: бетон с илом; по кадру не измерить, см. отчёт)
res["rho_bottom"] = RHO_BOTTOM


def white_level(name):
    """Линейный уровень белого сектора кадра (G): по нему калибруется экспозиция модели."""
    return float(light.srgb_decode(np.array(frames[name][9][1]) / 255))


# сетка лучей кадра ПВК 16:9, дно перпендикулярно оси камеры на дальности d
gx, gy = np.meshgrid(np.linspace(-1, 1, 24) * np.tan(HFOV / 2), np.linspace(-1, 1, 14) * np.tan(HFOV / 2) * 9 / 16)
RAYS = np.stack([gx.ravel(), gy.ravel(), np.ones(gx.size)], 1)
DIST_FACTOR = np.linalg.norm(RAYS, axis=1)
RAYS /= DIST_FACTOR[:, None]


PLATE_SIZE = 0.40         # планшет с белой рамкой, м (оценка по кадрам: секторы ≈0,33 м на 2,7 м)
PLATE_ALB = 0.7 * ALB.mean(0) + 0.3 * p["albedo_white"]   # секторы + рамка ≈30 % площади (оценка)


def frame_mean(kind, d, base, power, bp):
    """Средний уровень кадра для автоэкспозиции: дно + планшет (его доля кадра растёт при малой дальности)."""
    w, lamp = setup(kind, d, base, power, bp)
    L = light.radiance(CAM, RAYS, d * DIST_FACTOR, -np.repeat([[0, 0, 1.0]], len(RAYS), 0),
                       np.full((len(RAYS), 3), RHO_BOTTOM), lamp, w, n=400)
    Lp = plate_radiance(kind, d, base, power, bp, albedo=PLATE_ALB[None])
    fw = min(PLATE_SIZE / (2 * d * np.tan(HFOV / 2)), 1.0)
    f = fw * min(fw * 16 / 9, 1.0)
    return float((1 - f) * np.mean(light.gray601(L)) + f * light.gray601(Lp)[0])


def contrast(kind, d, base, power, bp, ae=True, k_fixed=None, white=None):
    """K_j = |B_j − B_9|/255 по серому Rec.601 от 8-битного sRGB, как у Холопова и в статье.
    Экспозиция: white — по белому сектору кадра; ae — автоэкспозиция (средний уровень кадра = T_AE); иначе k_fixed."""
    L = plate_radiance(kind, d, base, power, bp)
    if white is not None:
        k = white / L[9, 1]
    elif ae:
        k = T_AE / frame_mean(kind, d, base, power, bp)
    else:
        k = k_fixed
    v8 = np.round(255 * light.srgb_encode(k * L))
    g = np.round(light.gray601(v8))
    return np.abs(g - g[8]) / 255, v8, k


# ---------- 3б. контраст на 2,7 м против т. 4 ----------
# цель автоэкспозиции: при 2,7 м, 50 % белый сектор как на кадре т. 4 (экспозиция калибруется один раз)
_L = plate_radiance("sdvs5", 2.7, 0.5, 0.5, bp_fit)
T_AE = white_level("СДВС5 50 %, 2,7 м (т. 4)") / _L[9, 1] * frame_mean("sdvs5", 2.7, 0.5, 0.5, bp_fit)
res["ae_target"] = float(T_AE)
print(f"\nАвтоэкспозиция: цель {T_AE:.3f} (средний линейный уровень кадра при альбедо дна {RHO_BOTTOM})")
print("\n3б. Контраст секторов, 2,7 м, СДВС5, база 0,5 м, экспозиция по белому сектору кадра (предсказание 8 секторов):")
t4 = {}
for pw, key in [(0.5, "LED 50%"), (1.0, "LED 100%")]:
    K, _, _ = contrast("sdvs5", 2.7, 0.5, pw, bp_fit, white=white_level(f"СДВС5 {int(pw * 100)} %, 2,7 м (т. 4)"))
    Km = np.array(fr["chart"][key]["table4"])
    Ks = K[SHOWN]
    rel = Ks / Km - 1
    t4[key] = {"model": Ks.tolist(), "table4": Km.tolist(), "rel_err": rel.tolist(),
               "mean_model": float(Ks.mean()), "mean_table": float(Km.mean())}
    print(f"  {key}: модель {np.round(Ks, 3)}\n          т. 4   {Km}\n   средний {Ks.mean():.3f} против {Km.mean():.3f}"
          f" ({100 * (Ks.mean() / Km.mean() - 1):+.0f} %), по секторам {np.round(100 * rel).astype(int)} %")
res["table4_compare"] = t4

# ---------- 4. кривые статьи ----------
D = np.round(np.arange(0.8, 2.71, 0.1), 2)
BASES = np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8])
curves = {"d": D.tolist(), "bases": BASES.tolist()}
for pw in (0.5, 1.0):
    curves[f"K_vs_d_{int(pw * 100)}"] = [contrast("sdvs5", d, 0.5, pw, bp_fit)[0].tolist() for d in D]
    curves[f"K_vs_d_fixed_{int(pw * 100)}"] = None
curves["K_vs_base_27"] = [contrast("sdvs5", 2.7, b, 0.5, bp_fit)[0].tolist() for b in BASES]
curves["K_vs_base_20"] = [contrast("sdvs5", 2.0, b, 0.5, bp_fit)[0].tolist() for b in BASES]
curves["K_vs_base_20_100"] = [contrast("sdvs5", 2.0, b, 1.0, bp_fit)[0].tolist() for b in BASES]
# фиксированная экспозиция (настроена на 50 %): что было бы без автоматики камеры
k50 = {d: contrast("sdvs5", d, 0.5, 0.5, bp_fit)[2] for d in D}
curves["K_vs_d_fixed_100"] = [contrast("sdvs5", d, 0.5, 1.0, bp_fit, ae=False, k_fixed=k50[d])[0].tolist() for d in D]
res["curves"] = curves

Kd = np.array(curves["K_vs_d_50"])          # (len D, 10)
Kd100 = np.array(curves["K_vs_d_100"])
Kfix = np.array(curves["K_vs_d_fixed_100"])
checks = {}
# (а) убывание с дальностью, минимальный порядка 0,15
# допуск: K — разность двух 8-битных значений, каждое округлено, то есть ±2/255
mono = all(np.all(np.diff(Kd[:, j]) <= 2 / 255 + 1e-9) for j in SHOWN)
# уточнённый критерий (после сверки с рис. 12: у статьи секторы 2, 6, 8 растут на 0,8-1,0 м):
# K(2,7) < K(0,8) у каждого сектора и монотонный спад от 1,0 м
i10 = int(np.argmin(np.abs(D - 1.0)))
mono_10 = all(np.all(np.diff(Kd[i10:, j]) <= 2 / 255 + 1e-9) for j in SHOWN)
drop = all(Kd[-1, j] < Kd[0, j] for j in SHOWN)
rise = {NAMES[j]: float(Kd[:i10 + 1, j].max() - Kd[0, j]) for j in SHOWN if Kd[:i10 + 1, j].max() - Kd[0, j] > 2 / 255}
kmin = float(Kd[-1, SHOWN].min())
checks["a"] = {"monotonic_strict": bool(mono), "monotonic_from_1m": bool(mono_10), "K27_below_K08": bool(drop),
               "rise_08_10": rise, "K_min_27": kmin, "ok": bool(mono_10 and drop and 0.07 <= kmin <= 0.3)}
# (б) зелёный спадает положе красного, розового, фиолетового (отношение K(2,7)/K(0,8))
ratio = Kd[-1] / np.maximum(Kd[0], 1e-9)
checks["b"] = {"ratio_27_08": {NAMES[j]: float(ratio[j]) for j in SHOWN},
               "ok": bool(all(ratio[4] > ratio[j] for j in (1, 6, 7)))}
# (в) 50 % -> 100 %: контраст не растёт (с автоэкспозицией); без неё рост
dK = Kd100[:, SHOWN].mean(1) - Kd[:, SHOWN].mean(1)
checks["c"] = {"mean_dK_ae": dK.tolist(), "mean_dK_fixed_exposure": (Kfix[:, SHOWN].mean(1) - Kd[:, SHOWN].mean(1)).tolist(),
               "ok": bool(np.all(dK <= 0.03))}
# (г) база 0,1 -> 0,5 м сильно повышает контраст, дальше рост замедляется
Kb = np.array(curves["K_vs_base_20"])[:, SHOWN].mean(1)     # 2,0 м, как рис. 10 статьи
g1, g2 = Kb[4] - Kb[0], Kb[7] - Kb[4]
# первая формализация (абсолютный прирост 0,1→0,5 больше вдвое прироста 0,5→0,8) и относительная (во сколько раз)
r1, r2 = Kb[4] / Kb[0], Kb[7] / Kb[4]
checks["d"] = {"K_mean_by_base_27": Kb.tolist(), "gain_01_05": float(g1), "gain_05_08": float(g2),
               "ratio_05_01": float(r1), "ratio_08_05": float(r2),
               "ok_absolute": bool(g1 > 2 * g2), "ok": bool(r1 >= 2 and r1 > 2 * r2)}
res["article_checks"] = checks
print("\n4. Выводы статьи (качественно):")
print(f"  (а) спад с дальностью: строго монотонно {mono} (подъём на 0,8-1,0 м: {rise}); от 1,0 м {mono_10}; "
      f"K(2,7) < K(0,8) у всех {drop}; минимум на 2,7 м {kmin:.3f}: {verdict(checks['a']['ok'])}")
print(f"  (б) K(2,7)/K(0,8): зелёный {ratio[4]:.2f}, красный {ratio[1]:.2f}, розовый {ratio[6]:.2f}, "
      f"фиолетовый {ratio[7]:.2f}: {verdict(checks['b']['ok'])}")
print(f"  (в) 50→100 %, средний ΔK с автоэкспозицией {dK.min():+.3f}..{dK.max():+.3f}; при постоянной экспозиции "
      f"{np.min(checks['c']['mean_dK_fixed_exposure']):+.3f}..{np.max(checks['c']['mean_dK_fixed_exposure']):+.3f}: "
      f"{verdict(checks['c']['ok'])}")
print(f"  (г) средний K на 2,0 м по базам {BASES.tolist()}: {np.round(Kb, 3).tolist()}; прирост 0,1→0,5 {g1:.3f}, "
      f"0,5→0,8 {g2:.3f} (абсолютный критерий: {verdict(checks['d']['ok_absolute'])}); "
      f"в разах ×{r1:.1f} и ×{r2:.2f}: {verdict(checks['d']['ok'])}")


# ---------- 4б. числа статьи: рис. 12-13 (оцифровано), рис. 10-11 (вручную) ----------
def load_csv(name):
    rows = [l for l in (OUT / name).read_text(encoding="utf-8").splitlines() if l and not l.startswith("#")]
    return np.array([[float(v) if v else np.nan for v in r.split(",")] for r in rows[1:]])


ART = {50: load_csv("article_fig12.csv"), 100: load_csv("article_fig13.csv")}   # x_mm, K1..K8, K10
ART_B = load_csv("article_fig10_11_manual.csv")                                  # power, base, K...
art = {}
print("\n4б. Против кривых статьи (база 0,5 м; узлы 0,8 / 1,5 / 2,0 / 2,7 м; средний K секторов и по секторам):")
for pw, Km in ((50, Kd), (100, Kd100)):
    A = ART[pw]
    rel_all = []
    rows = []
    for x in (800, 1500, 2000, 2700):
        i_a = int(np.where(A[:, 0] == x)[0][0])
        i_m = int(np.argmin(np.abs(D - x / 1000)))
        a_row = A[i_a, 1:]
        m_row = Km[i_m, SHOWN]
        ok = np.isfinite(a_row)
        rel = m_row[ok] / a_row[ok] - 1
        rel_all += rel.tolist()
        rows.append({"x_mm": x, "article_mean": float(np.nanmean(a_row)), "model_mean": float(m_row[ok].mean()),
                     "n": int(ok.sum()), "rel_err": rel.tolist()})
        print(f"  {pw} %, {x / 1000:.1f} м: статья {np.nanmean(a_row):.3f}, модель {m_row[ok].mean():.3f} "
              f"({100 * (m_row[ok].mean() / np.nanmean(a_row[ok]) - 1):+.0f} %), по секторам "
              f"{np.round(100 * rel).astype(int).tolist()} %")
    # спад: K(2,7)/K(0,8) по средним
    sl_a = rows[-1]["article_mean"] / rows[0]["article_mean"]
    sl_m = rows[-1]["model_mean"] / rows[0]["model_mean"]
    within = float(np.mean(np.abs(rel_all) <= 0.25))
    art[pw] = {"nodes": rows, "share_within_25pct": within, "decay_article": sl_a, "decay_model": sl_m}
    print(f"     доля значений в пределах ±25 %: {100 * within:.0f} %; спад K(2,7)/K(0,8): статья {sl_a:.2f}, модель {sl_m:.2f}")
for pw, key in ((50, "K_vs_base_20"), (100, "K_vs_base_20_100")):
    B = ART_B[ART_B[:, 0] == pw]
    Mb = np.array(curves[key])[:, SHOWN].mean(1)
    a_m = B[:, 2:].mean(1)
    m_m = Mb[[0, 4, 7]]
    art[f"base_{pw}"] = {"article_mean_100_500_800": a_m.tolist(), "model_mean_100_500_800": m_m.tolist()}
    print(f"  база, {pw} %, 2,0 м: статья K(0,1/0,5/0,8) = {np.round(a_m, 3).tolist()} (×{a_m[1] / a_m[0]:.1f}, "
          f"×{a_m[2] / a_m[1]:.2f}); модель {np.round(m_m, 3).tolist()} (×{m_m[1] / m_m[0]:.1f}, ×{m_m[2] / m_m[1]:.2f})")
res["article_compare"] = art
ok_num = all(art[pw]["share_within_25pct"] >= 0.5 for pw in (50, 100))
res["article_numeric_ok"] = bool(ok_num)
print(f"  Числа статьи (не меньше половины значений в ±25 %): {verdict(ok_num)}")

# ---------- 5. ΔE (CIEDE2000) против эталона ----------
def srgb_to_lab(v8):
    c = light.srgb_decode(np.asarray(v8, float) / 255)
    M = np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750], [0.0193339, 0.1191920, 0.9503041]])
    xyz = c @ M.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > (6 / 29) ** 3, np.cbrt(xyz), xyz / (3 * (6 / 29) ** 2) + 4 / 29)
    return np.stack([116 * f[:, 1] - 16, 500 * (f[:, 0] - f[:, 1]), 200 * (f[:, 1] - f[:, 2])], 1)


def de2000(l1, l2):
    """CIEDE2000 (Sharma et al. 2005), построчно."""
    L1, a1, b1 = l1.T
    L2, a2, b2 = l2.T
    C1, C2 = np.hypot(a1, b1), np.hypot(a2, b2)
    Cb = (C1 + C2) / 2
    G = 0.5 * (1 - np.sqrt(Cb ** 7 / (Cb ** 7 + 25 ** 7)))
    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p, C2p = np.hypot(a1p, b1), np.hypot(a2p, b2)
    h1 = np.degrees(np.arctan2(b1, a1p)) % 360
    h2 = np.degrees(np.arctan2(b2, a2p)) % 360
    dL, dC = L2 - L1, C2p - C1p
    dh = h2 - h1
    dh = np.where(dh > 180, dh - 360, np.where(dh < -180, dh + 360, dh))
    dh = np.where(C1p * C2p == 0, 0, dh)
    dH = 2 * np.sqrt(C1p * C2p) * np.sin(np.radians(dh / 2))
    Lb, Cbp = (L1 + L2) / 2, (C1p + C2p) / 2
    hs = h1 + h2
    hb = np.where(C1p * C2p == 0, hs, np.where(np.abs(h1 - h2) <= 180, hs / 2,
                                                np.where(hs < 360, (hs + 360) / 2, (hs - 360) / 2)))
    T = (1 - 0.17 * np.cos(np.radians(hb - 30)) + 0.24 * np.cos(np.radians(2 * hb))
         + 0.32 * np.cos(np.radians(3 * hb + 6)) - 0.20 * np.cos(np.radians(4 * hb - 63)))
    dth = 30 * np.exp(-((hb - 275) / 25) ** 2)
    Rc = 2 * np.sqrt(Cbp ** 7 / (Cbp ** 7 + 25 ** 7))
    Sl = 1 + 0.015 * (Lb - 50) ** 2 / np.sqrt(20 + (Lb - 50) ** 2)
    Sc, Sh = 1 + 0.045 * Cbp, 1 + 0.015 * Cbp * T
    Rt = -np.sin(np.radians(2 * dth)) * Rc
    return np.sqrt((dL / Sl) ** 2 + (dC / Sc) ** 2 + (dH / Sh) ** 2 + Rt * (dC / Sc) * (dH / Sh))


# проверка реализации: пары Sharma et al. 2005, табл. 1 (первые три)
sh = de2000(np.array([[50, 2.6772, -79.7751], [50, 3.1571, -77.2803], [50, 2.8361, -74.0200]]),
            np.array([[50, 0, -82.7485], [50, 0, -82.7485], [50, 0, -82.7485]]))
ok_de = bool(np.allclose(sh, [2.0425, 2.8615, 3.4412], atol=1e-3))
print(f"\n5. CIEDE2000: проверка по Sharma 2005 {np.round(sh, 4)}: {verdict(ok_de)}")
lab_et = srgb_to_lab(fr["color"]["etalon"])
dE = {}
for name, kind, d, base, measured, fk in [("1 м, лампа аппарата", "own", 1.0, 0, 9.44, "лампа аппарата, 1 м (ΔE)"),
                                          ("2 м, СДВС5", "sdvs5", 2.0, 0.5, 27.04, "СДВС5, 2 м (ΔE)"),
                                          ("2,7 м, СДВС5", "sdvs5", 2.7, 0.5, 31.57, "СДВС5, 2,7 м (ΔE)")]:
    _, v8, _ = contrast(kind, d, base, 0.5, bp_fit, white=white_level(fk))
    e = de2000(lab_et, srgb_to_lab(v8))
    m = float(np.mean(e[[0, 1, 2, 3, 4, 5, 6, 7, 9]]))
    dE[name] = {"model": m, "kholopov": measured}
    print(f"  {name}: ΔE модель {m:.1f}, Холопов {measured}")
vals = [v["model"] for v in dE.values()]
ok_de_trend = bool(vals[0] < vals[1] < vals[2])
print(f"  ΔE растёт с дальностью: {verdict(ok_de_trend)} (баланс белого камер не известен: только качественно)")
res["deltaE"] = dE
res["deltaE_impl_ok"] = ok_de
res["deltaE_trend_ok"] = ok_de_trend

save_results("v5_light", res)

# ---------- графики ----------
fig, ax = plt.subplots(1, 3, figsize=(14, 4.2))
cols = {0: "#8b5a2b", 1: "#d62728", 2: "#ff7f0e", 3: "#bcbd22", 4: "#2ca02c", 5: "#1f77b4", 6: "#e377c2",
        7: "#9467bd", 9: "#7f7f7f"}
for j in SHOWN:
    ax[0].plot(D, Kd[:, j], color=cols[j], label=NAMES[j])
    ax[0].plot([2.7], [fr["chart"]["LED 50%"]["K"][j]], "o", color=cols[j], mfc="none")
    ax[0].plot(ART[50][:, 0] / 1000, ART[50][:, 1 + SHOWN.index(j)], ".", ms=3, color=cols[j])
ax[0].set(title="(а, б) K против дальности, СДВС5 50 %, база 0,5 м\nлинии: модель; точки: статья, рис. 12; о: т. 4 Холопова",
          xlabel="дальность, м", ylabel="K")
ax[0].legend(fontsize=6, ncol=2)
ax[1].plot(D, Kd[:, SHOWN].mean(1), label="50 %, автоэкспозиция")
ax[1].plot(D, Kd100[:, SHOWN].mean(1), "--", label="100 %, автоэкспозиция")
ax[1].plot(D, Kfix[:, SHOWN].mean(1), ":", label="100 %, экспозиция как у 50 %")
ax[1].plot([2.7, 2.7], [t4["LED 50%"]["mean_table"], t4["LED 100%"]["mean_table"]], "ko", mfc="none", label="т. 4 (50 / 100 %)")
ax[1].plot(ART[50][:, 0] / 1000, np.nanmean(ART[50][:, 1:], 1), "k.", ms=4, label="статья, рис. 12 (50 %)")
ax[1].plot(ART[100][:, 0] / 1000, np.nanmean(ART[100][:, 1:], 1), "kx", ms=4, label="статья, рис. 13 (100 %)")
ax[1].set(title="(в) мощность лампы, средний K секторов", xlabel="дальность, м", ylabel="средний K")
ax[1].legend(fontsize=7)
ax[2].plot(BASES, Kb, "o-", label="модель 2,0 м")
ax[2].plot(BASES, np.array(curves["K_vs_base_27"])[:, SHOWN].mean(1), "s-", label="модель 2,7 м")
ax[2].plot(ART_B[ART_B[:, 0] == 50][:, 1] / 1000, ART_B[ART_B[:, 0] == 50][:, 2:].mean(1), "k^--",
           label="статья, рис. 10 (2,0 м)")
ax[2].set(title="(г) база «лампа-камера», СДВС5 50 %", xlabel="база, м", ylabel="средний K")
ax[2].legend(fontsize=7)
fig.tight_layout()
fig.savefig(OUT / "v5_light.png")

if "--write" in sys.argv:
    path = light.PARAMS_PATH
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["pool_bp550"]["value"] = round(bp_fit, 4)
    raw["pool_a_extra_rgb"]["value"] = [round(float(x), 4) for x in A_EXTRA]
    raw["turbid_bp550"]["value"] = round(bp_each["мутная, 1 м (ΔE)"], 3)
    text = "{\n" + ",\n".join(f'  {json.dumps(k, ensure_ascii=False)}: {json.dumps(v, ensure_ascii=False)}'
                              for k, v in raw.items()) + "\n}\n"
    path.write_text(text, encoding="utf-8")
    print("b_p550 записано в", path)
