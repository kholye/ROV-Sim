"""V5, шаг 1: измерение кадров мишени (данные Холопова), без модели света.

Повторяет обработку Холопова (data/Kholopov-progs) на Python:
  - контраст (для 2.1/Chart/main_chart.m, sravnenieLED/main_chart.m): углы планшета из plate_corners.mat,
    проективное выпрямление 400×500, серое по Rec.601 (как rgb2gray), медиана окна сектора,
    K_j = |B_j − B_9| / 255, БЕЗ histeq (как в программе Холопова);
  - цвет (для 2.2/color): уже выпрямленные кадры results/rectified/*_original.png (400×1000, 2×5),
    срез 20 % от краёв сектора, среднее.
Проверка самой обработки: контраст LED 50 % / 100 % должен совпасть с таблицей 4 ВКР Холопова
(там MATLAB, здесь Python; допуск 0,01). Результат: docs/verification/v5_frames.json.
"""
import numpy as np
import scipy.io as sio
from PIL import Image

from common import ROOT, save_results, verdict

KP = ROOT / "data" / "Kholopov-progs"
CHART = KP / "для 2.1" / "Chart"
LED = KP / "для 3.1.2.2" / "sravnenieLED"
RECT = KP / "для 2.2" / "color" / "results" / "rectified"

# окна секторов main_chart.m: центры (x, y) и размер (0,25 × 0,07) в долях планшета
CX = [0.36, 0.76] * 5
CY = [0.13, 0.13, 0.304, 0.304, 0.484, 0.484, 0.66, 0.66, 0.86, 0.86]
SW, SH = 0.25, 0.07
NAMES = ["brown", "red", "orange", "yellow", "green", "blue", "pink", "purple", "black", "white"]

# таблица 4 ВКР Холопова (без histeq), секторы C1..C8, C10
TABLE4 = {"LED 50%": [0.169, 0.196, 0.318, 0.471, 0.220, 0.157, 0.278, 0.208, 0.455],
          "LED 100%": [0.180, 0.216, 0.337, 0.498, 0.235, 0.169, 0.302, 0.227, 0.482]}


def homography(src, dst):
    """H: src -> dst (4 пары точек)."""
    A = []
    for (x, y), (u, v) in zip(src, dst):
        A.append([x, y, 1, 0, 0, 0, -u * x, -u * y, -u])
        A.append([0, 0, 0, x, y, 1, -v * x, -v * y, -v])
    _, _, vt = np.linalg.svd(np.array(A, float))
    return vt[-1].reshape(3, 3) / vt[-1, -1]


def rectify(img, corners, W=400, H=500):
    """Как fitgeotrans + imwarp (билинейно): углы по часовой с левого верхнего."""
    tgt = [(1, 1), (W, 1), (W, H), (1, H)]          # 1-based, как в MATLAB
    Hm = homography(tgt, [(x, y) for x, y in corners])   # выход -> вход
    yy, xx = np.mgrid[1:H + 1, 1:W + 1].astype(float)
    p = Hm @ np.stack([xx.ravel(), yy.ravel(), np.ones(xx.size)])
    u, v = p[0] / p[2] - 1, p[1] / p[2] - 1          # в 0-based пиксели
    a = np.asarray(img, float)
    u0, v0 = np.floor(u).astype(int), np.floor(v).astype(int)
    fu, fv = (u - u0)[:, None], (v - v0)[:, None]
    u0 = np.clip(u0, 0, a.shape[1] - 2)
    v0 = np.clip(v0, 0, a.shape[0] - 2)
    out = (a[v0, u0] * (1 - fu) * (1 - fv) + a[v0, u0 + 1] * fu * (1 - fv)
           + a[v0 + 1, u0] * (1 - fu) * fv + a[v0 + 1, u0 + 1] * fu * fv)
    return np.round(out).reshape(H, W, -1)


def gray601(rgb):
    return np.round(0.298936 * rgb[..., 0] + 0.587043 * rgb[..., 1] + 0.114021 * rgb[..., 2])


def chart_sectors(rect):
    """Окна sector_cut.m (MATLAB ceil, 1-based) -> медианы серого и каналов по 10 секторам."""
    H, W = rect.shape[:2]
    g = gray601(rect)
    med_g, med_rgb = [], []
    for cx, cy in zip(CX, CY):
        y0, y1 = int(np.ceil((cy - SH / 2) * H)), int(np.ceil((cy + SH / 2) * H))
        x0, x1 = int(np.ceil((cx - SW / 2) * W)), int(np.ceil((cx + SW / 2) * W))
        med_g.append(float(np.median(g[y0 - 1:y1, x0 - 1:x1])))
        med_rgb.append([float(np.median(rect[y0 - 1:y1, x0 - 1:x1, c])) for c in range(3)])
    return med_g, med_rgb


def color_sectors(rect, margin=0.2):
    """Сетка 2 × 5 (как main_delta_e.m), срез margin от краёв, среднее RGB 0..255."""
    H, W = rect.shape[:2]
    out = []
    for r in range(5):
        for c in range(2):
            x0, x1 = c * W / 2, (c + 1) * W / 2
            y0, y1 = r * H / 5, (r + 1) * H / 5
            dx, dy = margin * (x1 - x0), margin * (y1 - y0)
            sub = rect[int(y0 + dy):int(y1 - dy), int(x0 + dx):int(x1 - dx), :3]
            out.append(sub.reshape(-1, 3).mean(0).tolist())
    return out


def contrast(med_g):
    return [abs(b - med_g[8]) / 255 for b in med_g]


def load_rgb(path):
    return np.asarray(Image.open(path).convert("RGB"))


res = {"chart": {}, "led_compare": {}, "color": {}}

# --- контраст, 2700 мм, СДВС5 (для 2.1) ---
corners = sio.loadmat(CHART / "plate_corners.mat")["corners"]
for k, (f, name) in enumerate([("clear_led_50.png", "LED 50%"), ("clear_led_100.png", "LED 100%")]):
    img = load_rgb(CHART / f)
    rect = rectify(img, corners[k, 0])
    g, rgb = chart_sectors(rect)
    K = contrast(g)
    Ks = K[:8] + K[9:]
    err = float(np.max(np.abs(np.array(Ks) - TABLE4[name])))
    res["chart"][name] = {"file": f, "median_gray": g, "median_rgb": rgb, "K": K,
                          "table4": TABLE4[name], "max_abs_err_vs_table4": err}
    print(f"{name}: K = {np.round(Ks, 3).tolist()}\n   т.4 {TABLE4[name]}  макс. расхождение {err:.4f}")
ok_pipeline = all(v["max_abs_err_vs_table4"] <= 0.01 for v in res["chart"].values())
print("Обработка = таблица 4 Холопова (допуск 0,01):", verdict(ok_pipeline))
res["pipeline_ok"] = ok_pipeline

# --- контраст, 2700 мм: лампа аппарата против СДВС5 (для 3.1.2.2, т. 12) ---
c2 = sio.loadmat(LED / "plate_corners.mat")["corners"]
files = sorted(p.name for p in LED.glob("*.png"))
# порядок углов как в main_chart.m этой папки
order = ["sdvsLED_50.png", "sdvsLED_100.png", "myLED_50.png", "myLED_100.png"]
src = (LED / "main_chart.m").read_text(encoding="cp1251", errors="replace")
order = sorted(order, key=lambda n: src.find(n))
for k, f in enumerate(order):
    img = load_rgb(LED / f)
    g, rgb = chart_sectors(rectify(img, c2[k, 0]))
    K = contrast(g)
    Kmean = float(np.mean(K[:8] + K[9:]))
    res["led_compare"][f] = {"median_gray": g, "median_rgb": rgb, "K": K, "K_mean": Kmean}
    print(f"{f}: средний K = {Kmean:.3f}")
res["led_compare_order"] = order

# --- цвет (для 2.2): эталон на воздухе и кадры в воде ---
for name in ["etalon", "clear_1m_original", "clear_2m_original", "clear_2700mm_original", "murky_1m_original"]:
    rect = load_rgb(RECT / f"{name}.png").astype(float)
    res["color"][name] = color_sectors(rect)
res["sector_names"] = NAMES
save_results("v5_frames", res)
