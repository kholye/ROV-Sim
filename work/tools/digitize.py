"""Оцифровка синей кривой MATLAB-графика (рисунки Дунаева, извлечённые pdf_images.py).

Ось привязывается по двум линиям сетки, найденным вручную по картинке:
  python digitize.py fig.png out.csv x_px1,x_px2 x_val1,x_val2 y_px1,y_px2 y_val1,y_val2
Так получены docs/verification/dunaev_fig48_digitized.csv и dunaev_fig49_digitized.csv:
  рис. 48: x 144,434 -> 20,100 с;  y 79,324 -> 0,5;3,0 м
  рис. 49: x 99,485 -> 40,220 с;   y 79,324 -> 1,8;2,8 м
Точность около 1 пикселя: 0,5 с по времени и 4 мм по глубине.
"""
import sys

import matplotlib.image as mi
import numpy as np

fn, out = sys.argv[1], sys.argv[2]
xp, xv, yp, yv = ([float(v) for v in a.split(",")] for a in sys.argv[3:7])
img = mi.imread(fn)[:, :, :3]
r, g, b = img[..., 0], img[..., 1], img[..., 2]
blue = (b > 0.6) & (r < 0.35) & (g < 0.35)
ax = np.polyfit(xp, xv, 1)
ay = np.polyfit(yp, yv, 1)
res = []
for c in range(img.shape[1]):
    rows = np.where(blue[:, c])[0]
    if len(rows):
        res.append((np.polyval(ax, c), np.polyval(ay, rows.mean())))
np.savetxt(out, np.array(res), delimiter=",", header="t,depth", comments="", fmt="%.4f")
print(len(res), "точек")
