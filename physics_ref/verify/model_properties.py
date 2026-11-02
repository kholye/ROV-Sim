"""Свойства аппарата из 3D-модели этапа 3: объём и ЦВ, баланс масс (масса, ЦМ, инерция),
присоединённые массы по полосам, силуэты для поперечного сопротивления.

Входы: blender/rov_report.json (объём и центр каждой детали после фасок), силуэты
docs/model/side_ortho_1mm.png, top_nofins_1mm.png, front_ortho.png (1 px = 1 мм), rov_params.json.
Выход: docs/verification/model_properties.json, model_properties.png и блок параметров
docs/verification/model_properties_params.json, который переносится в rov_params.json.

Принятые решения (docs/physics-sources.md, разд. «Модель аппарата»):
  - масса берётся из условия нейтральности при 70 мл воды в цистернах: m = rho (V - V_n),
    V из модели; «около 10 кг» из работ не согласуется с геометрией по фото;
  - баланс масс: известные и оценённые детали + остаток (рама, провода, герметик); остаток
    стоит на оси так, чтобы аппарат был уравновешен по дифференту при нейтральных цистернах;
  - присоединённые массы: полосовая теория по каждой трубе, гильзе и насадке (Ca = 1), плоскости
    вместе с корпусом как прямоугольная пластина (DNV-RP-H103, табл. A-2), продольная по Лэмбу.
"""
import json
import sys

import numpy as np
from PIL import Image

from common import OUT, ROOT, plt, save_results
from rov import params, dynamics as dyn

p = params.load()
rho = p["rho"]
rep = json.loads((ROOT / "blender" / "rov_report.json").read_text(encoding="utf-8"))
parts = rep["parts"]
res = {}


def c(name):
    return np.array(parts[name]["centroid_ned_m"])


# ---------- 1. Объём, ЦВ, масса ----------
V = rep["displaced_volume_l"] * 1e-3
cb = np.array(rep["cb_model_ned_m"])
Vn = p["neutral_tank_volume"]
m_dry = rho * (V - Vn)
drop_names = [n for n in parts if n.startswith("ballast_drop")]
V_drop = sum(parts[n]["volume_l"] for n in drop_names) * 1e-3
m_drop = p["ballast_drop_mass"]
# центр сбрасываемого узла по массе: дробь 0,93 кг, якорь 0,07 кг (сталь 190 × 25 × 2 мм)
r_drop = (0.93 * c("ballast_drop_shot") + 0.07 * c("ballast_drop_bar")) / 1.0
res["hydrostatics"] = {"V_model_m3": V, "cb_model_m": cb.tolist(), "mass_dry_kg": m_dry,
                       "V_drop_m3": V_drop, "r_drop_m": r_drop.tolist()}

# ---------- 2. Баланс масс ----------
# (имя, масса кг, положение, форма для собственной инерции, обоснование)
# форма: ("point",) | ("shell", r, L) тонкостенная труба вдоль x | ("rod", r, L) сплошной цилиндр вдоль x
PVC, STEEL, AL, PLA_EFF = 1400.0, 7850.0, 2700.0, 0.6 * 1240.0
t_tube = 0.0032
budget = [
    ("главная труба ПВХ 110 × 3,2", PVC * np.pi * 0.11 * t_tube * 0.555, c("hull_main_tube"),
     ("shell", 0.0534, 0.555), "SN4 110 × 3,2 мм; ПВХ 1400 кг/м³ (при стенке 2,7 мм на 0,13 кг меньше)"),
    ("кормовой фланец (печать)", PLA_EFF * np.pi * (0.07 ** 2 - 0.055 ** 2) * 0.025, c("hull_stern_flange"),
     ("point",), "кольцо Ø140/110 × 25 мм, PLA 1240 кг/м³ при заполнении 60 %"),
    ("кормовая крышка (текстолит Ø92 × 5)", 1850 * np.pi * 0.046 ** 2 * 0.005, c("stern_endplate"), ("point",),
     "стеклотекстолит 1850 кг/м³"),
    ("болты фланца 8 × M6", 8 * 0.008, np.array([-0.328, 0, 0]), ("point",), "M6 × 30 со шайбой ≈ 8 г"),
    ("гермовводы 8 шт.", 8 * 0.015, np.array([-0.30, 0, 0.01]), ("point",),
     "6 на корме, 1 на энергоотсеке, 1 у камеры; ≈ 15 г"),
    ("стяжной хомут фланца", STEEL * 0.03 * 0.0015 * np.pi * 0.116, c("hull_stern_collar"), ("point",),
     "лента 30 × 1,5 мм"),
    ("носовой колпак (печать)", 0.25, c("hull_nose_cap"), ("point",),
     "стакан со стенкой ≈ 5 мм; сплошной был бы 0,7 кг: диапазон 0,2-0,7 кг"),
    ("хомуты главной трубы 5 шт.", 5 * 0.09, np.array([-0.0016, 0, 0]), ("point",),
     "лента 14 × 1,5 мм ≈ 61 г + 2 болта + прокладка; центр = среднее x хомутов"),
    ("хомуты нижней трубы 2 шт.", 2 * 0.035, np.array([0.1045, 0, 0.085]), ("point",), "лента 14 × 1 мм"),
    ("движитель левый", 0.25, c("thruster_L_duct"), ("point",),
     "паспорта нет; движители 12-16 В, 130-150 Вт с насадкой весят 200-300 г"),
    ("движитель правый", 0.25, c("thruster_R_duct"), ("point",), "то же"),
    ("кронштейны движителей", 2 * 0.02, np.array([-0.25, 0, 0.03]), ("point",), "стальная полоса"),
    ("кабели движителей", 2 * 0.03, np.array([-0.32, 0, 0]), ("point",), "≈ 0,3 м × 100 г/м"),
    ("нижняя труба ПВХ 40 × 2", PVC * np.pi * 0.04 * 0.002 * 0.41, c("lower_tube"), ("shell", 0.019, 0.41),
     "ПВХ 40 × 2 мм"),
    ("фланец и заглушка нижней трубы", 0.04, np.array([-0.03, 0, 0.085]), ("point",), "печать"),
    ("батарея 4S1P 18650 + BMS", 0.25, c("lower_tube"), ("rod", 0.018, 0.28),
     "4 × 47 г + плата и провода; ёмкость 43,2 Вт·ч (rov_params battery_energy)"),
    ("груз неотделяемый, корма", 0.5, c("ballast_rear"), ("point",),
     "автор: всего 2 кг, сбрасывается 1 кг; остальные 1 кг поровну на 2 гильзы"),
    ("груз неотделяемый, нос", 0.5, c("ballast_front"), ("point",), "то же"),
    ("груз сбрасываемый с якорем", m_drop, r_drop, ("point",), "автор: 1 кг"),
    ("электромагнит", 0.15, c("magnet"), ("point",), "держатель Ø35 × 25 мм, сталь"),
    ("носовая пластина Al", AL * 0.19 * 0.06 * 0.002, c("nose_plate"), ("point",), "190 × 60 × 2 мм"),
    ("камера в боксе", 0.15, c("camera"), ("point",), "экшн-камера ≈ 60 г + бокс ≈ 90 г"),
    ("крепление камеры", 0.02, c("camera_mount"), ("point",), "пластик"),
    ("лампа", 0.08, c("lamp"), ("point",), "бокс, плата, 9 светодиодов, заливка"),
    ("плоскости 2 шт.", 2 * 0.012 * 0.003 * PVC, np.array([0.19, 0, 0]), ("point",), "лист ПВХ 3 мм, 0,012 м² каждая"),
    ("цистерны без воды 2 шт.", 0.4, np.array([0.0, 0, 0]), ("point",),
     "шприц-поршень + мотор с редуктором + винт ≈ 0,2 кг; стоят при x = ±0,25 симметрично"),
    ("электроника", 0.4, np.array([0.0, 0, 0]), ("point",), "ATmega2560, драйверы, БИНС, датчик давления, платы"),
]
# цистерны — две точки, учтём отдельно для инерции
tank_x = p["tank_x"]
m_known = sum(b[1] for b in budget)
m_rest = m_dry - m_known
if m_rest < 0:
    raise SystemExit(f"сумма деталей {m_known:.2f} кг больше массы {m_dry:.2f} кг")

# масса воды при нейтральной настройке и положение остатка для равновесия по дифференту
mw = rho * Vn / 2
m_tot = m_dry + 2 * mw
mx_known = sum(b[1] * b[2][0] for b in budget)
x_rest = (cb[0] * m_tot - mx_known - mw * (tank_x[0] + tank_x[1])) / m_rest
if not -0.30 < x_rest < 0.25:
    raise SystemExit(f"остаток массы пришлось бы поставить вне корпуса: x = {x_rest:.3f}")
budget.append(("остаток: рама, провода, герметик, крепёж", m_rest, np.array([x_rest, 0, 0]),
               ("rod", 0.04, 0.30), "масса m − сумма деталей; x подобран для равновесия по дифференту"))

M = sum(b[1] for b in budget)
rg = sum(b[1] * b[2] for b in budget) / M


def own_inertia(m, shape):
    if shape[0] == "shell":
        r, L = shape[1], shape[2]
        return np.diag([m * r * r, m * (r * r / 2 + L * L / 12), m * (r * r / 2 + L * L / 12)])
    if shape[0] == "rod":
        r, L = shape[1], shape[2]
        return np.diag([m * r * r / 2, m * (3 * r * r + L * L) / 12, m * (3 * r * r + L * L) / 12])
    return np.zeros((3, 3))


I = np.zeros((3, 3))
for name, m, r, shape, _ in budget:
    if name.startswith("цистерны"):        # две точки при x = ±0,25
        for tx in tank_x:
            d = np.array([tx, 0, 0]) - rg
            I += m / 2 * (d @ d * np.eye(3) - np.outer(d, d))
        continue
    d = r - rg
    I += own_inertia(m, shape) + m * (d @ d * np.eye(3) - np.outer(d, d))
res["mass_budget"] = {
    "items": [{"name": b[0], "mass_kg": round(b[1], 4), "pos_m": [round(v, 4) for v in b[2]], "note": b[4]}
              for b in budget],
    "mass_known_kg": m_known, "mass_rest_kg": m_rest, "x_rest_m": x_rest,
    "cg_dry_m": rg.tolist(), "inertia_cg_kgm2": I.tolist(),
    "BG_m": float(rg[2] - cb[2]),
    "products_rel": {"Ixz/Iyy": float(I[0, 2] / I[1, 1]), "Ixy/Iyy": float(I[0, 1] / I[1, 1])},
}

# ---------- 3. Присоединённые массы ----------
A = np.pi / 4
strips = []


def strip(name, x0, x1, y, z, D=None, s22=None, s33=None, s44=0.0):
    if D is not None:
        s22 = s33 = A * D * D             # Ca = 1: присоединённая масса круга = rho * pi D² / 4
    strips.append({"name": name, "x0": x0, "x1": x1, "y": y, "z": z,
                   "s22": round(s22, 7), "s33": round(s33, 7), "s44": s44})


strip("кормовой фланец Ø140", -0.325, -0.300, 0, 0, D=0.14)
strip("главная труба Ø110", -0.300, 0.255, 0, 0, D=0.11)
strip("носовой колпак Ø120", 0.255, 0.275, 0, 0, D=0.12)
strip("носовой колпак Ø140", 0.275, 0.325, 0, 0, D=0.14)
strip("фланец нижней трубы Ø60", -0.250, -0.230, 0, 0.085, D=0.06)
strip("нижняя труба Ø40", -0.230, 0.180, 0, 0.085, D=0.04)
strip("заглушка нижней трубы Ø52", 0.180, 0.205, 0, 0.085, D=0.052)
strip("груз корма Ø35", -0.205, -0.075, 0, 0.1225, D=0.035)
strip("груз сбрасываемый Ø35", -0.021, 0.109, 0, 0.150, D=0.035)
strip("груз нос Ø35", 0.210, 0.300, 0, 0.0905, D=0.035)
tz = p["thruster_pos"][2]
for s in (-1, 1):
    strip("насадка " + ("левая" if s < 0 else "правая") + " Ø62 (вода внутри увлекается)",
          -0.2875, -0.2125, s * p["thruster_pos"][1], tz, D=0.062)
# плоскости с корпусом в плане: пластина a × b, a = средняя хорда 0,171, b = размах 0,25 м
a_c, b_s = 0.1715, 0.25
ratio = b_s / a_c
tab = np.array([[1.0, 0.579], [1.25, 0.642], [1.5, 0.704], [2.0, 0.757], [2.5, 0.801], [3.0, 0.830]])
Ca = float(np.interp(ratio, tab[:, 0], tab[:, 1]))
m33_plate = Ca * rho * A * a_c * a_c * b_s
m33_hull_here = rho * A * 0.11 ** 2 * a_c
dm33 = m33_plate - m33_hull_here
# крен плоскостей: пластина полуразмаха s вращается вокруг оси, 2D: pi rho s^4 / 8 на метр,
# с тем же 3D-коэффициентом, что и в подъёме (3D / 2D полоса по хорде)
k3d = m33_plate / (rho * np.pi * (b_s / 2) ** 2 * a_c)
a44 = np.pi * rho * (b_s / 2) ** 4 / 8 * a_c * k3d
strip("плоскости (добавка к корпусу)", 0.19 - a_c / 2, 0.19 + a_c / 2, 0, 0,
      s22=0.0, s33=dm33 / (rho * a_c), s44=a44 / (rho * a_c))
k1, _, _ = dyn.lamb_k(0.65, 0.11)
m11 = k1 * rho * V
pp = dict(p, added_mass_strips=strips, added_mass_surge=m11)
MA = dyn.added_mass_matrix(pp)
res["added_mass"] = {"plate": {"a": a_c, "b": b_s, "Ca": Ca, "m33_plate": m33_plate, "m33_hull_same_chord": m33_hull_here,
                               "dm33_fins": dm33, "k3d": k3d, "a44_fins": a44},
                     "surge_lamb_k1": k1, "m11": m11, "MA": MA.tolist()}

# ---------- 4. Силуэты для поперечного сопротивления ----------
CELL = 0.04


def silhouette(fname, to_ned, mirror_cols=False):
    """Пиксели силуэта в метрах (по центрам пикселей). mirror_cols: объединить с зеркальным по y
    (аппарат симметричен по замыслу; несимметричны только кнопки бокса камеры)."""
    a = np.asarray(Image.open(OUT.parent / "model" / fname).getchannel("A")) > 128
    if mirror_cols:
        a = a | a[:, ::-1]
    rows, cols = np.nonzero(a)
    rows, cols = rows + 0.5, cols + 0.5
    u, w = to_ned(rows, cols)                         # (x, вторая координата) в метрах
    area = len(rows) * 1e-6
    return u, w, area


def cells(u, w):
    iu = np.floor(u / CELL).astype(int)
    iw = np.floor(w / CELL).astype(int)
    out = []
    for key in sorted(set(zip(iu, iw))):
        m = (iu == key[0]) & (iw == key[1])
        out.append([round(float(u[m].mean()), 4), round(float(w[m].mean()), 4), round(m.sum() * 1e-6, 7)])
    return out


xs, zs, A_side = silhouette("side_ortho_1mm.png", lambda r, c_: ((c_ - 500) / 1000, (r - 250) / 1000))
xt, yt, A_top = silhouette("top_nofins_1mm.png", lambda r, c_: ((500 - r) / 1000, (c_ - 250) / 1000), True)
yf, zf, A_front = silhouette("front_ortho.png", lambda r, c_: (-(c_ - 250) / 1000, (r - 250) / 1000), True)
side_cells = cells(xs, zs)
top_cells = cells(xt, yt)
res["drag"] = {"A_side_m2": A_side, "A_top_nofins_m2": A_top, "A_front_m2": A_front,
               "front_center_yz_m": [float(yf.mean()), float(zf.mean())],
               "side_centroid_xz_m": [float(xs.mean()), float(zs.mean())],
               "top_centroid_xy_m": [float(xt.mean()), float(yt.mean())],
               "n_side_cells": len(side_cells), "n_top_cells": len(top_cells),
               "old_model": {"A_cross_m2": 0.0916, "A_front_m2": float(np.pi * 0.07 ** 2)}}

# ---------- 5. Сравнение со старыми числами ----------
res["compare"] = {"mass_dry_kg": [p["mass_dry"], m_dry], "cg_dry_m": [p["cg_dry"], rg.tolist()],
                  "cb_m": [p["cb"], cb.tolist()], "inertia_diag": [p["inertia_dry_cg"], np.diag(I).tolist()]}
save_results("model_properties", res)

# ---------- 6. Блок параметров для rov_params.json ----------
block = {
    "mass_dry": round(m_dry, 3), "cg_dry": [round(v, 4) for v in rg], "cb": [round(v, 4) for v in cb],
    "inertia_dry_cg": [round(v, 4) for v in np.diag(I)],
    "ballast_drop_volume": round(V_drop, 7), "ballast_drop_pos": [round(v, 4) for v in r_drop],
    "added_mass_surge": round(m11, 4), "added_mass_strips": strips,
    "drag_area_front": round(A_front, 5), "drag_front_center": [round(float(yf.mean()), 4), round(float(zf.mean()), 4)],
    "drag_cells_side": side_cells,
    # сверху только правая половина (y > 0): вторую код зеркалит попарно, симметрия точная
    "drag_cells_top": [cl for cl in top_cells if cl[1] > 0],
}
(OUT / "model_properties_params.json").write_text(json.dumps(block, ensure_ascii=False), encoding="utf-8")

print(json.dumps({"hydro": res["hydrostatics"], "rest": [m_known, m_rest, x_rest], "cg": rg.tolist(),
                  "BG": res["mass_budget"]["BG_m"], "I": np.diag(I).tolist(), "prod": res["mass_budget"]["products_rel"],
                  "MA_diag": np.diag(MA).tolist(), "A35": MA[2, 4], "A15": MA[1, 5], "A24": MA[1, 3],
                  "plate": res["added_mass"]["plate"], "drag": {k: v for k, v in res["drag"].items() if k != "old_model"}},
                 ensure_ascii=False, indent=1))

# ---------- 7. Рисунок ----------
fig, ax = plt.subplots(1, 2, figsize=(10, 3.6))
sc = np.array(side_cells)
ax[0].scatter(sc[:, 0], sc[:, 1], s=sc[:, 2] / sc[:, 2].max() * 60, c="tab:blue", alpha=0.5, label="клетки силуэта сбоку")
ax[0].plot(*rg[[0, 2]], "ko", label=f"ЦМ ({rg[0]*1e3:.0f}; {rg[2]*1e3:.0f}) мм")
ax[0].plot(*cb[[0, 2]], "o", mfc="none", mec="r", ms=9, label=f"ЦВ ({cb[0]*1e3:.0f}; {cb[2]*1e3:.0f}) мм")
tp = p["thruster_pos"]
ax[0].plot(tp[0], tp[2], "g^", label="движитель")
ax[0].invert_yaxis()
ax[0].set(aspect="equal", xlabel="x, м (вперёд)", ylabel="z, м (вниз)", title="Вид сбоку: силуэт, ЦМ, ЦВ")
ax[0].legend(fontsize=7, loc="upper center", bbox_to_anchor=(0.5, -0.42), ncol=2)
names = [b[0] for b in budget]
mass = [b[1] for b in budget]
order = np.argsort(mass)[::-1][:12]
ax[1].barh([names[i][:34] for i in order][::-1], [mass[i] for i in order][::-1], color="tab:gray")
ax[1].set(xlabel="масса, кг", title=f"Баланс масс: {m_dry:.2f} кг (12 крупнейших)")
ax[1].tick_params(axis="y", labelsize=7)
fig.tight_layout()
fig.savefig(OUT / "model_properties.png")

# ---------- 8. Запись в rov_params.json (python model_properties.py --write) ----------
# Меняются только значения перечисленных ключей; единицы, статусы и источники остаются.
# x центра масс пишется точно из равновесия по дифференту (12 знаков), иначе покой не идеален.
if "--write" in sys.argv:
    from collections import OrderedDict
    path = params.PARAMS_PATH
    raw = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=OrderedDict)
    vals = dict(block, cb=[round(v, 5) for v in cb])
    vals["drag_front_center"] = [0.0, vals["drag_front_center"][1]]
    vals["drag_cells_top"] = [[c_[0], c_[1], c_[2]] for c_ in vals["drag_cells_top"]]
    m_w = round(m_dry, 3)
    vals["mass_dry"] = m_w
    vals["cg_dry"] = [round(vals["cb"][0] * (m_w + rho * Vn) / m_w, 12), 0.0, vals["cg_dry"][2]]
    for k, v in vals.items():
        raw[k]["value"] = v
    lines = ["{"]
    items = list(raw.items())
    for i, (k, v) in enumerate(items):
        sep = "," if i < len(items) - 1 else ""
        lines.append(f"  {json.dumps(k, ensure_ascii=False)}: {json.dumps(v, ensure_ascii=False)}{sep}")
    lines.append("}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("записано в", path)
