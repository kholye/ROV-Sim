"""V4: датчики.

(а) генератор шума гироскопа воспроизводит таблицу 5 Дунаева (N при tau = 1 с) и форму его кривой Аллана
(б) уход курса неподвижного аппарата за 20 минут против 0,15° (Дунаев 4.2, допуск вдвое: 0,075-0,3°)
    1. только гироскоп: сравнение с моделированием Дунаева (т. 8: курс 2,85° за 1200 с), без подгонки
    2. гироскоп + магнитометр: постоянная фильтра модуля tau_f не известна и ПОДГОНЯЕТСЯ по 0,15°
    Для сравнения: вариант «числа т. 5 в рад/с, как в шапке таблицы».
"""
import numpy as np

from common import OUT, plt, save_results
from rov import params, sensors

p = params.load()
fs = p["imu_rate"]
DEG = np.pi / 180
res = {}

# ---------- (а) Аллан ----------
rng = np.random.default_rng(11)
n = int(3 * 3600 * fs)
taus = np.logspace(-2, 3.3, 40)
fig, ax = plt.subplots(1, 3, figsize=(14, 4.2))
res["allan"] = {}
for i, axis in enumerate("xyz"):
    N, K, B = p["gyro_N"][i], p["gyro_K"][i], p["gyro_B"][i]
    y = sensors.imu_noise(n, fs, N, K, B, p["gyro_bias_tau"], rng)
    ad = sensors.allan_deviation(y, fs, taus)
    a1 = sensors.allan_deviation(y, fs, [1.0])[0]
    res["allan"][f"W{axis}"] = {"N_table_deg": N / DEG, "allan_at_1s_deg": a1 / DEG, "N_rel_error": a1 / N - 1,
                                "B_table_deg": B / DEG, "allan_min_deg": float(np.nanmin(ad)) / DEG,
                                "tau_at_min_s": float(taus[np.nanargmin(ad)])}
    ax[0].loglog(taus, ad / DEG, label=f"W{axis} модель")
    ax[0].loglog(1.0, N / DEG, "o", color=ax[0].lines[-1].get_color())
    ax[0].loglog(taus[np.nanargmin(ad)], B / DEG, "s", mfc="none", color=ax[0].lines[-1].get_color())
ax[0].set(title="(а) девиация Аллана модели гироскопа\n(о: N т. 5 при τ = 1 с; □: B т. 5 у минимума)", xlabel="τ, с",
          ylabel="σ(τ), °/с")
ax[0].legend(fontsize=7)

# ---------- (б) уход курса ----------
T = 1200.0
n = int(T * fs)
runs = 20
rng = np.random.default_rng(21)
Nz, Kz, Bz = p["gyro_N"][2], p["gyro_K"][2], p["gyro_B"][2]
base = np.array([sensors.imu_noise(n, fs, Nz, Kz, Bz, p["gyro_bias_tau"], rng) for _ in range(runs)])
mag_noise = p["mag_heading_sigma_deg"] * DEG * rng.standard_normal((runs, n))


def drift_deg(gz, tau_f):
    """Максимальный |psi(t) - psi(0)| за 20 минут, по прогонам. Истинный курс = 0."""
    psi = np.zeros(runs)
    k = 1.0 / (fs * tau_f) if np.isfinite(tau_f) else 0.0
    mx = np.zeros(runs)
    dt = 1.0 / fs
    psi0 = None
    for i in range(n):
        psi = psi + gz[:, i] * dt
        if k > 0:
            e = mag_noise[:, i] - psi
            psi = psi + k * np.arctan2(np.sin(e), np.cos(e))
        if psi0 is None:
            psi0 = psi.copy()
        mx = np.maximum(mx, np.abs(psi - psi0))
    return mx / DEG


tau_list = [1.0, 2.0, 3.0, 5.0, 7.0, 10.0, 15.0, 20.0, 30.0, 100.0, 300.0, 1000.0, np.inf]
res["heading"] = {"measured_deg": 0.15, "tolerance_deg": [0.075, 0.3], "dunaev_sim_gyro_only_deg": 2.85,
                  "runs": runs, "cases": []}
curves = {}
for label, scale in (("т. 5 в °/с, как на рис. 24-25", 1.0), ("т. 5 в рад/с, как в шапке", 1 / DEG)):
    gz = base * scale
    q = np.array([np.percentile(drift_deg(gz, tf), [5, 50, 95]) for tf in tau_list])
    curves[label] = q
    for tf, row in zip(tau_list, q):
        res["heading"]["cases"].append({"units": label, "tau_f_s": "только гироскоп" if not np.isfinite(tf) else tf,
                                        "drift_p5_deg": row[0], "drift_median_deg": row[1], "drift_p95_deg": row[2],
                                        "in_tolerance": bool(0.075 <= row[1] <= 0.3)})
    xs = np.arange(len(tau_list))
    ax[1].errorbar(xs, q[:, 1], yerr=[q[:, 1] - q[:, 0], q[:, 2] - q[:, 1]], fmt="o-", capsize=3, label=label)

q = curves["т. 5 в °/с, как на рис. 24-25"]
finite = np.isfinite(tau_list)
i_best = int(np.argmin(np.where(finite, np.abs(np.log(q[:, 1] / 0.15)), np.inf)))
res["heading"]["gyro_only_median_deg"] = float(q[-1, 1])
res["heading"]["calibrated_tau_f_s"] = tau_list[i_best]
res["heading"]["calibrated_median_deg"] = float(q[i_best, 1])
res["heading"]["tau_f_in_tolerance_s"] = [tf for tf, row in zip(tau_list, q) if np.isfinite(tf) and 0.075 <= row[1] <= 0.3]
res["heading"]["ahrs_tau_param"] = p["ahrs_tau"]
ax[1].axhspan(0.075, 0.3, color="g", alpha=0.15, label="0,15° ± вдвое (бассейн)")
ax[1].axhline(2.85, color="r", ls=":", lw=1, label="модель Дунаева, т. 8 (только гироскоп)")
ax[1].set_yscale("log")
ax[1].set_xticks(np.arange(len(tau_list)), [f"{x:g}" for x in tau_list[:-1]] + ["гиро"], fontsize=7)
ax[1].set(title="(б) уход курса за 20 мин (медиана, 5-95 %)", xlabel="постоянная фильтра модуля τ_f, с", ylabel="max |Δψ|, °")
ax[1].legend(fontsize=6.5)

gz = base[:1]
t = np.arange(n) / fs
ax[2].plot(t / 60, np.cumsum(gz[0]) / fs / DEG, label="только гироскоп")
psi_a = sensors.ahrs_heading(np.zeros(n), gz[0], fs, p["ahrs_tau"], p["mag_heading_sigma_deg"] * DEG, np.random.default_rng(3))
ax[2].plot(t / 60, psi_a / DEG, lw=0.6, label=f"с магнитометром, τ_f = {p['ahrs_tau']:g} с (в модели)")
ax[2].set(title="(б) одна реализация", xlabel="t, мин", ylabel="ψ − ψ_ист, °")
ax[2].legend(fontsize=7)
fig.tight_layout()
fig.savefig(OUT / "v4_sensors.png")
save_results("v4", res)
print(res["allan"])
print({k: v for k, v in res["heading"].items() if k != "cases"})
for c in res["heading"]["cases"]:
    print(c["units"], c["tau_f_s"], round(c["drift_median_deg"], 3))
