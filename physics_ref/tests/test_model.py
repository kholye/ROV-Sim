"""Модульные тесты эталона. Запуск из physics_ref: .venv/Scripts/python -m unittest discover -s tests"""
import unittest

import numpy as np

from rov import params, dynamics as dyn, sensors, control
from rov.environment import Battery, Current
from rov.sim import HeaveBatch, run_depth_hold


class TestKinematics(unittest.TestCase):
    def test_rotation_orthonormal(self):
        R = dyn.rot_nb(0.3, -0.4, 2.0)
        np.testing.assert_allclose(R @ R.T, np.eye(3), atol=1e-12)
        self.assertAlmostEqual(np.linalg.det(R), 1.0, places=12)

    def test_yaw_only(self):
        R = dyn.rot_nb(0.0, 0.0, np.pi / 2)
        # нос на восток: x тела -> +y NED
        np.testing.assert_allclose(R @ [1, 0, 0], [0, 1, 0], atol=1e-12)


class TestCoriolis(unittest.TestCase):
    def test_no_work(self):
        p = params.load()
        veh = dyn.Vehicle(p)
        rng = np.random.default_rng(3)
        _, _, MRB = veh.mass_props(60e-6, 10e-6, False)
        for M in (MRB, veh.MA):
            for _ in range(20):
                nu = rng.standard_normal(6)
                self.assertAlmostEqual(nu @ dyn.coriolis(M, nu) @ nu, 0.0, places=12)


class TestFins(unittest.TestCase):
    def test_fins_only_dissipate(self):
        p = params.load()
        veh = dyn.Vehicle(p)
        rng = np.random.default_rng(7)
        for _ in range(50):
            nu = rng.standard_normal(6)
            self.assertLessEqual(nu @ veh.fin_forces(nu), 1e-12)

    def test_no_fin_force_at_rest(self):
        veh = dyn.Vehicle(params.load())
        np.testing.assert_allclose(veh.fin_forces(np.zeros(6)), 0.0)


class TestForces(unittest.TestCase):
    def setUp(self):
        self.p = params.load()
        self.veh = dyn.Vehicle(self.p)

    def test_neutral(self):
        x = dyn.initial_state(1.0)
        xd, _ = self.veh.deriv(x, (0, 0), (0, 0))
        # cg_dry[0] записан с точностью 1e-12 м (равновесие по дифференту), отсюда остаток ~1e-10
        np.testing.assert_allclose(xd, 0.0, atol=1e-6)

    def test_nose_tank_pitches_nose_down(self):
        x = dyn.initial_state(1.0, V1=70e-6, V2=0.0)
        _, nud = self.veh.deriv(x, (0, 0), (0, 0))
        self.assertLess(nud[4], 0.0)   # q' < 0: тета убывает, нос вниз

    def test_right_stick_turns_right(self):
        L, R = control.joystick_to_motors(32767, 0)
        _, nud = self.veh.deriv(dyn.initial_state(1.0), (L / 100, R / 100), (0, 0))
        self.assertGreater(nud[5], 0.0)  # r' > 0: курс растёт, поворот вправо

    def test_submerged_fraction(self):
        r = self.veh.r
        self.assertEqual(dyn.submerged_fraction(-r - 0.01, r), 0.0)
        self.assertEqual(dyn.submerged_fraction(r + 0.01, r), 1.0)
        self.assertAlmostEqual(dyn.submerged_fraction(0.0, r), 0.5, places=12)


class TestControl(unittest.TestCase):
    def test_mixing(self):
        self.assertEqual(control.joystick_to_motors(0, 32767), (100, 100))
        self.assertEqual(control.joystick_to_motors(32767, 0), (100, -100))
        self.assertEqual(control.joystick_to_motors(14999, -14999), (0, 0))
        self.assertEqual(control.joystick_to_motors(32767, 32767), (100, 0))

    def test_quantize(self):
        self.assertEqual(control.quantize_gain(0.25), 0.3)
        self.assertEqual(control.quantize_gain(12.0), 9.9)
        self.assertEqual(control.quantize_gain(-1.0), 0.0)


class TestHeave(unittest.TestCase):
    def test_heave_matches_full_model(self):
        # сведение точное, если вертикаль не связана с дифферентом: симметричный корпус без плоскостей
        tube = {"name": "труба", "x0": -0.325, "x1": 0.325, "y": 0.0, "z": 0.0, "s22": 0.0095, "s33": 0.0095, "s44": 0.0}
        base = params.load()
        p = params.load(fins=[], added_mass_strips=[tube], drag_cells_top=[[0.0, 0.0, 0.0928]],
                        cg_dry=[0.0, 0.0, base["cg_dry"][2]], cb=[0.0, 0.0, base["cb"][2]])
        full = run_depth_hold(p, 1.0, 1.0, 0.1, 2.0, 60.0)
        _, rec = HeaveBatch(p).run([1.0], [0.1], [2.0], 1.0, 60.0, record=True)
        dz = np.abs(full[:-1, 1] - rec[:, 0]).max()
        self.assertLess(dz, 1e-6)

    def test_heave_with_fins_close(self):
        # с настоящей геометрией (плоскости впереди, несимметричный силуэт) вертикаль связана
        # с дифферентом: только приближение
        p = params.load()
        full = run_depth_hold(p, 1.0, 1.0, 0.1, 2.0, 60.0)
        _, rec = HeaveBatch(p).run([1.0], [0.1], [2.0], 1.0, 60.0, record=True)
        dz = np.abs(full[:-1, 1] - rec[:, 0]).max()
        self.assertLess(dz, 0.02)


class TestSensors(unittest.TestCase):
    def test_allan_white_noise(self):
        rng = np.random.default_rng(5)
        fs, N = 100.0, 0.0057
        y = sensors.imu_noise(360000, fs, N, 0.0, 1e-12, 100.0, rng)
        ad = sensors.allan_deviation(y, fs, [1.0])[0]
        self.assertLess(abs(ad / N - 1), 0.05)

    def test_pressure_roundtrip(self):
        p = params.load()
        self.assertAlmostEqual(sensors.depth_from_pressure(sensors.pressure_at(2.345, p), p), 2.345, places=12)


class TestBattery(unittest.TestCase):
    def test_energy_drains(self):
        p = params.load()
        b = Battery(p)
        E = [b.E]
        for _ in range(1000):
            b.step(1.0, (0.5, -0.3), (1, 0), 1.0)
            E.append(b.E)
        self.assertTrue(np.all(np.diff(E) <= 0))
        self.assertAlmostEqual(b.E0 - b.E, b.used, places=6)


class TestCurrent(unittest.TestCase):
    def test_vehicle_drifts_with_current(self):
        p = params.load()
        veh = dyn.Vehicle(p)
        vc = Current(0.2, np.pi / 4).velocity()
        x = dyn.initial_state(1.0)
        # квадратичное сопротивление: относительная скорость убывает как 1/t, поэтому 600 с
        for _ in range(12000):
            x, _ = dyn.rk4_step(veh, x, 0.05, (0, 0), (0, 0), vc)
        vel_n = dyn.rot_nb(*x[3:6]) @ x[6:9]
        np.testing.assert_allclose(vel_n, vc, atol=0.01 * 0.2)

    def test_bed_profile(self):
        from rov.environment import bed_profile
        h = 8.0
        z = np.linspace(0.0, h, 200001)
        u = np.array([bed_profile(zi, h) for zi in z])
        # среднее по глубине = 1 (определение V0 как средней скорости), профиль растёт ко дну до 0
        self.assertAlmostEqual(np.trapezoid(u, z) / h, 1.0, delta=0.005)
        self.assertEqual(bed_profile(0.0, h), 0.0)
        self.assertTrue(np.all(np.diff(u[: len(u) // 2]) >= 0))
        c = Current(0.1, 0.3)
        np.testing.assert_allclose(c.velocity_at(1.0, h), c.velocity() * (1.0 / (0.32 * h)) ** (1 / 7))


class TestThrusterRamp(unittest.TestCase):
    def test_ramp_100_in_3s_both_ways(self):
        p = params.load()
        r = control.ThrusterRamp(p)
        for _ in range(150):                              # 1,5 с шагом 10 мс
            s = r.step(0.01, [1.0, -1.0])
        np.testing.assert_allclose(s, [0.5, -0.5], atol=1e-12)
        for _ in range(150):
            s = r.step(0.01, [1.0, -1.0])
        np.testing.assert_allclose(s, [1.0, -1.0], atol=1e-12)
        for _ in range(100):                              # назад: через ноль, 100 % -> -100 % за 6 с
            s = r.step(0.01, [-1.0, 1.0])
        np.testing.assert_allclose(s, [1.0 - 100 * 0.01 / 3.0, -1.0 + 100 * 0.01 / 3.0], atol=1e-12)

    def test_no_overshoot_small_step(self):
        r = control.ThrusterRamp(params.load())
        s = r.step(0.01, [0.001, 0.0])
        np.testing.assert_allclose(s, [0.001, 0.0], atol=1e-15)


if __name__ == "__main__":
    unittest.main()
