"""Скачивает текстуры CC0 с Poly Haven (api.polyhaven.com) в godot/assets/textures/<имя>/.

  python get_polyhaven.py <разрешение 1k|2k> <имя> [<имя> ...]

Берутся карты цвета (diff), рельефа (nor_gl), шероховатости (rough) и затенения (ao), если есть, в JPG.
Лицензия Poly Haven: CC0 (указание авторства не требуется, указываем в docs/CREDITS.md из вежливости).
"""
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "godot" / "assets" / "textures"
MAPS = {"Diffuse": "diff", "nor_gl": "nor_gl", "Rough": "rough", "AO": "ao"}
UA = {"User-Agent": "ROV-Sim texture fetch (portfolio project)"}


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return r.read()


res = sys.argv[1]
for name in sys.argv[2:]:
    files = json.loads(get(f"https://api.polyhaven.com/files/{name}"))
    d = OUT / name
    d.mkdir(parents=True, exist_ok=True)
    got = []
    for key, short in MAPS.items():
        if key not in files or res not in files[key]:
            continue
        entry = files[key][res].get("jpg") or files[key][res].get("png")
        ext = "jpg" if "jpg" in files[key][res] else "png"
        p = d / f"{name}_{short}_{res}.{ext}"
        if not p.exists():
            p.write_bytes(get(entry["url"]))
        got.append(p.name)
    print(name, got)
