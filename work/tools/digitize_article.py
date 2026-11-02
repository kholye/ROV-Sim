"""Оцифровка рис. 10-13 статьи Игнатьевой и Кузьменко (2024): по 9 кривых K(x) в цветах MATLAB.

  python digitize_article.py <папка с картинками pdf_images.py> <папка вывода>

Картинки (объекты PDF): 71 = рис. 10, 73 = рис. 11, 85 = рис. 12, 87 = рис. 13.
Оси привязаны по засечкам, найденным по тёмным пикселям осей (см. CAL). Значения снимаются только в узлах
опыта (шаг 100 мм): медиана строк пикселей цвета кривой в окне ±2 пикселя. Секторы 1 и 8, 2 и 10 одного цвета
(8 и 10 пунктиром): верхний отрезок = 8 / 10, нижний = 1 / 2. Кривые одного цвета разводятся слежением
(ближайший отрезок к предыдущему узлу, скачок не больше 0,1); где кривая перекрыта, значение не ставится (пусто). Выход: CSV и картинка с наложением для проверки глазом.
Точность: 1 пиксель ≈ 0,0015-0,0024 по K (JPEG статьи низкого разрешения).
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

src, out = Path(sys.argv[1]), Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)

# фигура: файл, (px x0, px x1, x0, x1), (px y0, px y1, y0, y1), шаг узлов, легенда (x0, y0, x1, y1)
CAL = {
    "fig10": ("obj00071.jpg", (82.5, 577.5, 100, 800), (431.5, 35.5, 0.0, 0.6), 100, (100, 40, 178, 232)),
    "fig11": ("obj00073.jpg", (90.5, 635.5, 100, 800), (462.5, 38.5, 0.0, 0.5), 100, (100, 40, 195, 250)),
    "fig12": ("obj00085.jpg", (79.5, 554.5, 800, 2800), (453.5, 37.5, 0.1, 0.7), 100, (462, 10, 552, 205)),
    "fig13": ("obj00087.jpg", (82.5, 578.5, 800, 2800), (466.0, 38.5, 0.1, 0.7), 100, (480, 10, 580, 212)),
}
COLORS = {1: (0, 114, 189), 2: (217, 83, 25), 3: (237, 177, 32), 4: (126, 47, 142), 5: (119, 172, 48),
          6: (77, 190, 238), 7: (162, 20, 47)}
SHARED = {1: 8, 2: 10}          # цвет -> пунктирный сектор того же цвета (выше)
JUMP = 0.1                      # наибольший скачок кривой между соседними узлами


def runs(ys):
    """Отрезки подряд идущих строк (разрыв > 3 пикселей)."""
    if len(ys) == 0:
        return []
    ys = np.sort(ys)
    cut = np.where(np.diff(ys) > 3)[0]
    return [seg for seg in np.split(ys, cut + 1)]


for name, (fn, (xp0, xp1, xv0, xv1), (yp0, yp1, yv0, yv1), step, leg) in CAL.items():
    img = Image.open(src / fn).convert("RGB")
    a = np.asarray(img).astype(float)
    H, W = a.shape[:2]
    # каждый пиксель относится к ближайшему цвету палитры (цвета кривых + белый, серый сетки, чёрный)
    pal = np.array([(255, 255, 255), (235, 235, 235), (128, 128, 128), (0, 0, 0)] + list(COLORS.values()), float)
    dist = np.linalg.norm(a[:, :, None, :] - pal[None, None], axis=3)
    k = np.argmin(dist, 2)
    CLS = np.where((k >= 4) & (dist.min(2) < 60), k - 3, 0)      # 1..7 = номер цвета, 0 = фон
    lx0, ly0, lx1, ly1 = leg
    xs = np.arange(xv0, xv1 + 1, step)
    if name in ("fig12", "fig13"):
        xs = np.arange(800, 2701, 100)         # опыт: 800-2700 мм
    data = {s: [] for s in (1, 2, 3, 4, 5, 6, 7, 8, 10)}
    pts = []
    for x in xs:
        px = xp0 + (x - xv0) / (xv1 - xv0) * (xp1 - xp0)
        c0 = int(round(px)) - 2 if x > xv0 else int(round(px)) + 1
        c1 = int(round(px)) + 3 if x > xv0 else int(round(px)) + 5
        for col, rgb in COLORS.items():
            ys = np.where((CLS[:, c0:c1] == col).any(1))[0]
            ys = ys[(ys < yp0 - 1) & (ys > yp1 - 2)]
            ys = ys[~((ys >= ly0) & (ys <= ly1) & (px >= lx0) & (px <= lx1))]
            rs = runs(ys)
            vals = [yv0 + (np.median(r) - yp0) / (yp1 - yp0) * (yv1 - yv0) for r in rs]
            tracks = [col] if col not in SHARED else [SHARED[col], col]      # пунктир выше
            if col in SHARED and len(vals) == 1:   # один отрезок: отдать ближайшей из двух кривых
                last = [[v for v in data[t] if np.isfinite(v)] for t in tracks]
                dd = [abs(vals[0] - l[-1]) if l else 9 for l in last]
                keep = tracks[int(np.argmin(dd))]
                for t in tracks:
                    data[t].append(vals[0] if t == keep and min(dd) < JUMP else np.nan)
                continue
            for t in tracks:
                prev = [v for v in data[t] if np.isfinite(v)]
                if not vals:
                    data[t].append(np.nan)
                    continue
                if prev:                     # слежение: ближайший к предыдущему узлу отрезок
                    j = int(np.argmin([abs(v - prev[-1]) for v in vals]))
                    ok = abs(vals[j] - prev[-1]) < JUMP
                else:                        # первый узел: верхний отрезок пунктиру, нижний сплошной
                    j = int(np.argmax(vals)) if t in SHARED.values() else int(np.argmin(vals))
                    ok = True
                data[t].append(vals[j] if ok else np.nan)
                if ok and col in SHARED and len(vals) > 1:
                    vals.pop(j)
        for s in data:
            v = data[s][-1]
            if np.isfinite(v):
                pts.append((px, yp0 + (v - yv0) / (yv1 - yv0) * (yp1 - yp0), s))
    cols = (1, 2, 3, 4, 5, 6, 7, 8, 10)
    lines = ["x_mm," + ",".join(f"K{s}" for s in cols)]
    for i, x in enumerate(xs):
        lines.append(f"{x}," + ",".join("" if not np.isfinite(data[s][i]) else f"{data[s][i]:.4f}" for s in cols))
    (out / f"article_{name}.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    big = img.resize((W * 2, H * 2), Image.NEAREST)
    dr = ImageDraw.Draw(big)
    for px, py, s in pts:
        dr.ellipse([2 * px - 4, 2 * py - 4, 2 * px + 4, 2 * py + 4], outline=(0, 0, 0))
        dr.text((2 * px + 5, 2 * py - 6), str(s), fill=(0, 0, 0))
    big.save(out / f"article_{name}_check.png")
    n_ok = sum(np.isfinite(v) for s in cols for v in data[s])
    print(name, f"{n_ok} из {len(xs) * 9} значений")
