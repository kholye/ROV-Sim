"""Загрузка параметров аппарата из общего JSON (его же читает Godot)."""
import json
from pathlib import Path

PARAMS_PATH = Path(__file__).resolve().parents[2] / "godot" / "physics" / "rov_params.json"


def load(path=PARAMS_PATH, **overrides):
    """Словарь {имя: значение}. overrides заменяют значения (для проверок чувствительности)."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    p = {k: v["value"] for k, v in raw.items() if not k.startswith("_")}
    for k, v in overrides.items():
        if k not in p:
            raise KeyError(k)
        p[k] = v
    return p
