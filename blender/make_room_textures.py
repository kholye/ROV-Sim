"""Свои текстуры стендов, плакатов и надписей зала (без снимков скана): рисуются здесь, Pillow.

    python blender/make_room_textures.py
Пишет blender/room_tex/own_*.png. Содержание — по смыслу того, что висит в лаборатории (стенды «элементы
радиоаппаратуры», план эвакуации, плакат об антенне, доска с записями, знак «курить запрещено»), рисунок свой.
Шрифты PT Sans (OFL, godot/assets/fonts).
"""
import math
import os
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = "D:/Документы/ROV-Sim"
OUT = ROOT + "/blender/room_tex"
FONT = ROOT + "/godot/assets/fonts/PTSans-Regular.ttf"
FONTB = ROOT + "/godot/assets/fonts/PTSans-Bold.ttf"
os.makedirs(OUT, exist_ok=True)
PX = 1000                                             # пикселей на метр


def F(sz, bold=False):
    return ImageFont.truetype(FONTB if bold else FONT, sz)


def aged(im, seed, amount=10):
    """Лёгкая неровность бумаги/краски: шум яркости и пятна."""
    r = random.Random(seed)
    W, H = im.size
    n = Image.effect_noise((W, H), amount).convert("L")
    im = Image.composite(im, Image.new("RGB", (W, H), (0, 0, 0)), n.point(lambda v: 255 - max(0, 128 - v) // 6))
    d = ImageDraw.Draw(im, "RGBA")
    for _ in range(3):
        x, y, s = r.uniform(0, W), r.uniform(0, H), r.uniform(0.05, 0.15) * min(W, H)
        d.ellipse((x - s, y - s, x + s, y + s), fill=(120, 100, 60, 4))
    return im


# ---------- стенды «элементы» (белое поле, чёрная полоса заголовка, ряды элементов с подписями)
def resistor(d, x, y, s):
    d.line((x - s, y, x + s, y), fill=(150, 150, 150), width=max(1, s // 12))
    d.rounded_rectangle((x - s * 0.5, y - s * 0.17, x + s * 0.5, y + s * 0.17), s // 8, fill=(196, 160, 110), outline=(80, 60, 40))
    for k, c in enumerate([(150, 40, 30), (30, 30, 30), (200, 120, 30), (190, 160, 40)]):
        xx = x - s * 0.33 + k * s * 0.2
        d.rectangle((xx, y - s * 0.17, xx + s * 0.06, y + s * 0.17), fill=c)


def capacitor(d, x, y, s):
    d.line((x, y + s * 0.4, x, y + s), fill=(150, 150, 150), width=max(1, s // 14))
    d.ellipse((x - s * 0.35, y - s * 0.35, x + s * 0.35, y + s * 0.45), fill=(45, 70, 120), outline=(20, 30, 50))
    d.rectangle((x - s * 0.35, y - s * 0.6, x + s * 0.35, y + s * 0.05), fill=(45, 70, 120))
    d.ellipse((x - s * 0.35, y - s * 0.75, x + s * 0.35, y - s * 0.45), fill=(170, 175, 180), outline=(60, 60, 60))


def tube(d, x, y, s):
    d.rounded_rectangle((x - s * 0.25, y - s * 0.8, x + s * 0.25, y + s * 0.5), s // 4, fill=(200, 205, 205), outline=(110, 110, 110))
    d.rectangle((x - s * 0.18, y - s * 0.45, x + s * 0.18, y + s * 0.2), fill=(90, 90, 95))
    d.rectangle((x - s * 0.28, y + s * 0.5, x + s * 0.28, y + s * 0.75), fill=(40, 40, 40))


def coil(d, x, y, s):
    d.ellipse((x - s * 0.5, y - s * 0.5, x + s * 0.5, y + s * 0.5), fill=(150, 90, 40), outline=(70, 40, 20))
    d.ellipse((x - s * 0.18, y - s * 0.18, x + s * 0.18, y + s * 0.18), fill=(235, 235, 230))
    for k in range(18):
        a = 2 * math.pi * k / 18
        d.line((x + math.cos(a) * s * 0.2, y + math.sin(a) * s * 0.2, x + math.cos(a) * s * 0.5, y + math.sin(a) * s * 0.5), fill=(110, 60, 25))


def transistor(d, x, y, s):
    d.ellipse((x - s * 0.3, y - s * 0.3, x + s * 0.3, y + s * 0.3), fill=(175, 178, 182), outline=(80, 80, 80))
    for k in (-1, 0, 1):
        d.line((x + k * s * 0.12, y + s * 0.3, x + k * s * 0.12, y + s * 0.8), fill=(150, 150, 150), width=max(1, s // 16))


def connector(d, x, y, s):
    d.rectangle((x - s * 0.5, y - s * 0.2, x + s * 0.5, y + s * 0.2), fill=(50, 50, 50))
    for k in range(8):
        d.rectangle((x - s * 0.45 + k * s * 0.12, y - s * 0.1, x - s * 0.4 + k * s * 0.12, y + s * 0.1), fill=(190, 160, 60))


DRAW = [resistor, capacitor, tube, coil, transistor, connector]
TITLES = ["РЕЗИСТОРЫ И КОНДЕНСАТОРЫ", "ЭЛЕКТРОВАКУУМНЫЕ ПРИБОРЫ", "ЭЛЕМЕНТЫ РАДИОАППАРАТУРЫ", "МОТОЧНЫЕ ИЗДЕЛИЯ И РАЗЪЁМЫ"]
CAPS = ["МЛТ-0,5", "КМ-5", "К50-6", "6Н2П", "ДМ-0,1", "КТ315", "МГТФ", "РП10", "ПЭВ-10", "КСО", "П213", "ГУ-50"]


def element_board(name, w, h, seed):
    r = random.Random(seed)
    W, H = int(w * PX), int(h * PX)
    im = Image.new("RGB", (W, H), (236, 234, 226))
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, W - 1, H - 1), outline=(70, 60, 50), width=int(0.012 * PX))
    d.rectangle((int(0.06 * W), int(0.04 * H), int(0.94 * W), int(0.11 * H)), fill=(35, 35, 40))
    d.text((W / 2, 0.075 * H), TITLES[seed % len(TITLES)], fill=(235, 235, 230), font=F(int(0.035 * H), True), anchor="mm")
    rows, cols = 3, 6
    for i in range(rows):
        d.text((0.05 * W, (0.2 + i * 0.27) * H), ["ПОСТОЯННЫЕ", "ПЕРЕМЕННЫЕ", "СПЕЦИАЛЬНЫЕ"][i], fill=(60, 60, 60), font=F(int(0.026 * H), True))
        for j in range(cols):
            x, y = (0.1 + j * 0.15) * W, (0.32 + i * 0.27) * H
            s = int(r.uniform(0.08, 0.105) * H)
            r.choice(DRAW)(d, x, y, s)
            d.text((x, y + 1.05 * s), r.choice(CAPS), fill=(40, 40, 40), font=F(int(0.02 * H)), anchor="mm")
    aged(im, seed).save(f"{OUT}/own_{name}.png")


# ---------- план эвакуации
def evac_plan(name, w, h):
    W, H = int(w * PX), int(h * PX)
    im = Image.new("RGB", (W, H), (80, 84, 88))
    d = ImageDraw.Draw(im)
    m = int(0.08 * W)
    d.rectangle((m, m, W - m, H - m), fill=(244, 240, 214))
    d.text((W / 2, m + 0.06 * H), "ПЛАН ЭВАКУАЦИИ ПРИ ПОЖАРЕ", fill=(30, 110, 50), font=F(int(0.05 * H), True), anchor="mm")
    x0, y0, x1, y1 = m + 0.06 * W, m + 0.16 * H, W - m - 0.3 * W, H - m - 0.08 * H
    d.rectangle((x0, y0, x1, y1), outline=(30, 30, 30), width=4)
    r = random.Random(3)
    for _ in range(9):
        if r.random() < 0.5:
            x = r.uniform(x0, x1)
            d.line((x, y0, x, r.uniform(y0, y1)), fill=(30, 30, 30), width=3)
        else:
            y = r.uniform(y0, y1)
            d.line((x0, y, r.uniform(x0, x1), y), fill=(30, 30, 30), width=3)
    for k in range(5):
        xa, ya = r.uniform(x0 + 20, x1 - 60), r.uniform(y0 + 20, y1 - 20)
        d.line((xa, ya, xa + 50, ya), fill=(30, 140, 60), width=6)
        d.polygon([(xa + 50, ya - 10), (xa + 66, ya), (xa + 50, ya + 10)], fill=(30, 140, 60))
    for k in range(4):
        ex, ey = r.uniform(x0, x1), r.uniform(y0, y1)
        d.ellipse((ex - 7, ey - 7, ex + 7, ey + 7), fill=(200, 30, 30))
    lx = W - m - 0.27 * W
    for k, (c, t) in enumerate([((30, 140, 60), "путь эвакуации"), ((200, 30, 30), "огнетушитель"), ((30, 30, 30), "стены")]):
        y = y0 + k * 0.09 * H
        d.rectangle((lx, y, lx + 0.04 * W, y + 0.03 * H), fill=c)
        d.text((lx + 0.06 * W, y), t, fill=(30, 30, 30), font=F(int(0.03 * H)))
    aged(im, 11).save(f"{OUT}/own_{name}.png")


# ---------- плакат «Конструкция антенны»
def antenna_poster(name, w, h):
    W, H = int(w * PX), int(h * PX)
    im = Image.new("RGB", (W, H), (238, 236, 228))
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, W - 1, H - 1), outline=(60, 50, 40), width=10)
    d.text((W / 2, 0.08 * H), "КОНСТРУКЦИЯ АНТЕННЫ ГИДРОЛОКАТОРА", fill=(25, 25, 25), font=F(int(0.055 * H), True), anchor="mm")
    cx, cy = 0.28 * W, 0.55 * H
    d.rectangle((cx - 0.06 * W, cy - 0.25 * H, cx + 0.06 * W, cy + 0.25 * H), fill=(60, 60, 60), outline=(20, 20, 20), width=3)
    for k in range(6):
        y = cy - 0.22 * H + k * 0.088 * H
        d.rectangle((cx - 0.05 * W, y, cx + 0.05 * W, y + 0.05 * H), fill=(190, 150, 70), outline=(40, 30, 20))
    d.rectangle((cx - 0.02 * W, cy + 0.25 * H, cx + 0.02 * W, cy + 0.38 * H), fill=(40, 40, 40))
    x0 = 0.5 * W
    d.rectangle((x0, 0.18 * H, 0.95 * W, 0.92 * H), outline=(30, 30, 30), width=3)
    for k in range(12):                                # чертёж: разрез с выносками
        y = 0.24 * H + k * 0.055 * H
        d.line((x0 + 0.03 * W, y, 0.92 * W - (k % 3) * 0.05 * W, y), fill=(60, 60, 60), width=2)
    d.ellipse((0.62 * W, 0.4 * H, 0.82 * W, 0.7 * H), outline=(30, 30, 30), width=3)
    d.line((0.62 * W, 0.55 * H, 0.82 * W, 0.55 * H), fill=(30, 30, 30), width=2)
    for k in range(5):
        d.text((x0 + 0.03 * W, 0.78 * H + k * 0.025 * H), f"{k + 1}. " + ["корпус", "пьезоэлемент", "демпфер", "кабельный ввод", "обтекатель"][k],
               fill=(30, 30, 30), font=F(int(0.022 * H)))
    aged(im, 21).save(f"{OUT}/own_{name}.png")


# ---------- доска с записями маркером
def whiteboard(name, w, h):
    W, H = int(w * PX), int(h * PX)
    im = Image.new("RGB", (W, H), (240, 242, 240))
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, W - 1, H - 1), outline=(170, 172, 175), width=14)
    r = random.Random(5)
    lines = ["3300  ср 17.20", "I пр  II пр  III пр", "7,2   21,0   6,3", "0,5   3,4   17,9", "15,5 - 15,5", "защита"]
    for k, t in enumerate(lines):
        layer = Image.new("RGBA", (W, int(0.14 * H)), (0, 0, 0, 0))
        ImageDraw.Draw(layer).text((0.08 * W + r.uniform(-8, 8), 0), t, fill=(35, 45, 120, 230), font=F(int(0.085 * H)))
        layer = layer.rotate(r.uniform(-2.5, 2.5), resample=Image.BICUBIC)
        im.paste(layer, (0, int((0.08 + k * 0.15) * H)), layer)
    im.filter(ImageFilter.GaussianBlur(0.6)).save(f"{OUT}/own_{name}.png")


# ---------- знак «Курить запрещено», табличка
def no_smoking(name):
    W = H = 300
    im = Image.new("RGB", (W, H), (245, 245, 240))
    d = ImageDraw.Draw(im)
    d.rectangle((70, 140, 230, 165), fill=(30, 30, 30))
    d.rectangle((200, 140, 230, 165), fill=(230, 120, 40))
    d.ellipse((20, 20, 280, 280), outline=(210, 30, 30), width=30)
    d.line((60, 60, 240, 240), fill=(210, 30, 30), width=30)
    im.save(f"{OUT}/own_{name}.png")


def cardboard(name, seed):
    W, H = 512, 512
    r = random.Random(seed)
    im = Image.new("RGB", (W, H), (178, 140, 92))
    d = ImageDraw.Draw(im)
    for _ in range(300):
        y = r.uniform(0, H)
        d.line((0, y, W, y + r.uniform(-3, 3)), fill=(170 + r.randint(-6, 6), 132 + r.randint(-6, 6), 86), width=1)
    d.rectangle((0, H * 0.45, W, H * 0.55), fill=(196, 170, 120))
    d.text((W * 0.1, H * 0.15), "НЕ КАНТОВАТЬ", fill=(60, 40, 25), font=F(40, True))
    aged(im, seed, 14).save(f"{OUT}/own_{name}.png")


for k, (nm, w, h) in enumerate([("Board_E1", 0.97, 0.63), ("Board_E2", 0.97, 0.63), ("Board_S1", 1.00, 0.70), ("Board_S2", 1.00, 0.75)]):
    element_board(nm, w, h, k)
evac_plan("Board_S3", 0.92, 0.55)
antenna_poster("Board_S4", 0.70, 0.57)
whiteboard("Board_WB", 0.35, 0.50)
no_smoking("sign_nosmoke")
cardboard("cardboard", 7)
print("TEX готово", flush=True)
