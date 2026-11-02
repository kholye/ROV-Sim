"""S1: у каждой физической модели есть источник, формула, проверка и статус.

Проверяет два места:
1. docs/physics-sources.md: в каждом нумерованном разделе есть поля
   «Источник», «Формула», «Проверка», «Статус» (жирным, как в остальных разделах).
2. godot/physics/rov_params.json и light_params.json: у каждого числа есть
   value, source и status из списка статусов проекта.
"""
import json
import re

from common import ROOT, save_results, verdict

FIELDS = ["Источник", "Формула", "Проверка", "Статус"]
STATUSES = ["проверено", "подогнано", "оценка", "не проверить"]

text = (ROOT / "docs" / "physics-sources.md").read_text(encoding="utf-8")
sections = re.split(r"^## ", text, flags=re.M)[1:]
md = {}
for sec in sections:
    title = sec.splitlines()[0].strip()
    if not re.match(r"\d", title):
        continue  # «Чего не хватает» и т. п.
    md[title] = [f for f in FIELDS if re.search(r"\*\*" + f, sec)]

params = {}
for name in ["rov_params.json", "light_params.json"]:
    data = json.loads((ROOT / "godot" / "physics" / name).read_text(encoding="utf-8"))
    for key, item in data.items():
        if key.startswith("_"):
            continue
        problems = []
        if not isinstance(item, dict) or "value" not in item:
            problems.append("нет value")
        else:
            if not str(item.get("source", "")).strip():
                problems.append("нет source")
            status = str(item.get("status", ""))
            # Статус может быть составным («оценка; поток проверено»): нужен хотя бы один известный.
            if not any(s in status for s in STATUSES):
                problems.append(f"статус «{status}»")
        params[f"{name}:{key}"] = problems

md_bad = {t: [f for f in FIELDS if f not in have] for t, have in md.items() if len(have) < len(FIELDS)}
par_bad = {k: v for k, v in params.items() if v}
status_count = {}
for name in ["rov_params.json", "light_params.json"]:
    data = json.loads((ROOT / "godot" / "physics" / name).read_text(encoding="utf-8"))
    for key, item in data.items():
        if key.startswith("_") or not isinstance(item, dict):
            continue
        # Составной статус считаем по самому слабому: «не проверить» < «оценка» < «подогнано» < «проверено».
        for s in reversed(STATUSES):
            if s in str(item.get("status", "")):
                status_count[s] = status_count.get(s, 0) + 1
                break

ok = not md_bad and not par_bad
print(f"Разделов моделей в physics-sources.md: {len(md)}, без полного набора полей: {len(md_bad)}")
for t, miss in md_bad.items():
    print(f"  {t}: нет {', '.join(miss)}")
print(f"Чисел в rov_params.json + light_params.json: {len(params)}, с проблемами: {len(par_bad)}")
for k, v in par_bad.items():
    print(f"  {k}: {', '.join(v)}")
print("Статусы чисел (по самому слабому):", status_count)
print("S1:", verdict(ok))
save_results("s1", {"sections": len(md), "sections_missing": md_bad, "numbers": len(params),
                    "numbers_bad": par_bad, "status_count": status_count, "pass": ok})
