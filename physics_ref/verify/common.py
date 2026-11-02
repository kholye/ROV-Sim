import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "physics_ref"))

sys.stdout.reconfigure(encoding="utf-8")
OUT = ROOT / "docs" / "verification"
OUT.mkdir(parents=True, exist_ok=True)

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

plt.rcParams.update({"figure.dpi": 110, "axes.grid": True, "grid.alpha": 0.3, "font.size": 9})


def save_results(name, data):
    (OUT / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def verdict(ok):
    return "ПРОЙДЕНО" if ok else "НЕ ПРОЙДЕНО"
