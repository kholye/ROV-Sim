"""Достаёт картинки из PDF без сторонних библиотек: JPEG (DCTDecode) как есть,
FlateDecode RGB/Gray 8 бит -> PNG. Только чтение исходного PDF."""
import re
import struct
import sys
import zlib
from pathlib import Path

src, out = Path(sys.argv[1]), Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
data = src.read_bytes()

# объекты: "N 0 obj ... endobj"
objs = {}
for m in re.finditer(rb"(\d+)\s+0\s+obj(.*?)endobj", data, re.S):
    objs[int(m.group(1))] = m.group(2)

# порядок страниц: /Type /Page объекты и их /XObject ссылки
def png(w, h, ch, raw):
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    ct = 2 if ch == 3 else 0
    rows = b"".join(b"\x00" + raw[i * w * ch:(i + 1) * w * ch] for i in range(h))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, ct, 0, 0, 0)) + \
        chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")

n = 0
info = []
for num, body in objs.items():
    if b"/Subtype/Image" not in body.replace(b" ", b"") and b"/Subtype /Image" not in body:
        continue
    sm = re.search(rb"stream\r?\n(.*)endstream", body, re.S)
    if not sm:
        continue
    stream = sm.group(1).rstrip(b"\r\n")
    head = body[:sm.start()]
    w = int(re.search(rb"/Width\s+(\d+)", head).group(1))
    h = int(re.search(rb"/Height\s+(\d+)", head).group(1))
    if w < 150 or h < 100:
        continue
    if b"DCTDecode" in head:
        (out / f"obj{num:05d}.jpg").write_bytes(stream)
        info.append((num, w, h, "jpg"))
    elif b"FlateDecode" in head:
        try:
            raw = zlib.decompress(stream)
        except Exception:
            continue
        cs = b"DeviceRGB" in head
        ch = 3 if cs else 1
        bpc = re.search(rb"/BitsPerComponent\s+(\d+)", head)
        if bpc and bpc.group(1) != b"8":
            continue
        if b"DecodeParms" in head:
            continue  # предсказатели PNG не разбираем
        if len(raw) < w * h * ch:
            continue
        (out / f"obj{num:05d}.png").write_bytes(png(w, h, ch, raw[:w * h * ch]))
        info.append((num, w, h, "png"))
    n += 1
for i in sorted(info):
    print(*i)
print("всего", len(info))
