"""Записать авторов в поле asset.copyright моделей .glb (стандарт glTF 2.0), не трогая геометрию.

Те же строки передают скрипты Blender при экспорте (export_copyright), так что после пересборки
модели поле совпадёт. Запуск из корня проекта: python work/tools/stamp_glb.py
"""
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OWN = "ROV-Sim, Kholopov E. G. (Холопов Е. Г.), 2026, CC BY 4.0"
STAMPS = {
    "godot/assets/rov/rov.glb": OWN + "; ROV Petrovich: SMTU, Dept. of Marine Information Systems and Technologies",
    "godot/assets/pool/pool.glb": OWN,
    "godot/assets/lab/lab_pool.glb": OWN,
    "godot/assets/wreck/wreck_site.glb": OWN + "; wreck scan: Malpas Metal Boat Wreck by artfletch, CC BY 4.0",
}


def stamp(path: Path, text: str) -> None:
    data = path.read_bytes()
    magic, ver, _ = struct.unpack_from("<III", data, 0)
    assert magic == 0x46546C67 and ver == 2, path
    jlen, jtype = struct.unpack_from("<II", data, 12)
    assert jtype == 0x4E4F534A, path
    doc = json.loads(data[20:20 + jlen].decode("utf-8"))
    doc.setdefault("asset", {})["copyright"] = text
    js = json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    js += b" " * ((4 - len(js) % 4) % 4)
    rest = data[20 + jlen:]
    out = struct.pack("<III", magic, ver, 12 + 8 + len(js) + len(rest)) + struct.pack("<II", len(js), jtype) + js + rest
    path.write_bytes(out)


if __name__ == "__main__":
    for rel, text in STAMPS.items():
        stamp(ROOT / rel, text)
        print("ok", rel)
    sys.exit(0)
