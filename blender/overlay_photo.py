"""Наложение вида сбоку на фото reference/ (этап 3, проверка «визуальное наложение»).

Запуск: python blender/overlay_photo.py  (после blender/render_views.py)
Фото 12-41-14 снято почти точно сбоку с правого борта. Масштаб и сдвиг подобраны по двум
точкам: задний торец кормового фланца и передний торец носового колпака (габарит 650 мм)
и ось главной трубы. Перспектива фото не исправляется, поэтому ближние к камере детали
(движитель) на фото крупнее, а дальние мельче на несколько процентов.
"""
from PIL import Image, ImageChops, ImageFilter

ROOT = "D:/Документы/ROV-Sim"
PHOTO = ROOT + "/reference/photo_2026-10-24_12-41-14.jpg"
RENDER = ROOT + "/docs/model/side_ortho_1mm.png"     # 1 px = 1 мм, начало тела в центре кадра
OUT = ROOT + "/docs/model/overlay_side.png"

# Точки на фото (пиксели исходного снимка 2560×1920), промер вручную
STERN_X, BOW_X, AXIS_Y = 275, 2150, 793                 # торцы габарита 650 мм, ось трубы

photo = Image.open(PHOTO).convert("RGBA")
ren = Image.open(RENDER).convert("RGBA")
k = (BOW_X - STERN_X) / 650.0                           # пикселей фото на мм
ren = ren.resize((round(ren.width * k), round(ren.height * k)), Image.LANCZOS)
ox = round((STERN_X + BOW_X) / 2 - ren.width / 2)
oy = round(AXIS_Y - ren.height / 2)

layer = Image.new("RGBA", photo.size, (0, 0, 0, 0))
layer.paste(ren, (ox, oy), ren)
alpha = layer.getchannel("A")
fill = Image.new("RGBA", photo.size, (0, 160, 255, 0))
fill.putalpha(alpha.point(lambda a: 70 if a > 128 else 0))
edge = ImageChops.subtract(alpha.point(lambda a: 255 if a > 128 else 0),
                           alpha.point(lambda a: 255 if a > 128 else 0).filter(ImageFilter.MinFilter(5)))
outline = Image.new("RGBA", photo.size, (255, 0, 60, 0))
outline.putalpha(edge)
res = Image.alpha_composite(Image.alpha_composite(photo, fill), outline)
res = res.crop((150, 480, 2450, 1400)).convert("RGB")
res.save(OUT)
print("k =", round(k, 3), "px/мм; сохранено", OUT)
