"""Offline tests for image/overlay/usr/local/bin/yt11-autobrightness.

Run: python3 -m unittest discover -s tests/autobrightness -v
No hardware: a fake backlight directory, a fake clock for the controller,
and a fake monitor-sensor script for the end-to-end runs.
"""

import contextlib
import importlib.machinery
import importlib.util
import io
import math
import os
import shlex
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(REPO, "image", "overlay", "usr", "local", "bin",
                      "yt11-autobrightness")


def load_script():
    # No .py suffix: load it by hand, and keep __pycache__ out of the overlay.
    loader = importlib.machinery.SourceFileLoader("yt11_autobrightness", SCRIPT)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    saved = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = saved
    return module


ab = load_script()

MAX = 4095


def write_file(path, text):
    with open(path, "w") as f:
        f.write(text)


def read_int(path):
    with open(path) as f:
        return int(f.read().strip())


def raw(pct):
    return ab.pct_to_raw(pct, MAX)


class TempDirTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        self.addCleanup(self._tmp.cleanup)

    def make_backlight(self, brightness=2048, bl_power=0):
        path = os.path.join(self.tmp, "backlight")
        os.makedirs(path, exist_ok=True)
        write_file(os.path.join(path, "max_brightness"), f"{MAX}\n")
        write_file(os.path.join(path, "brightness"), f"{brightness}\n")
        write_file(os.path.join(path, "bl_power"), f"{bl_power}\n")
        return path


class CurveTest(unittest.TestCase):
    def test_curve_points(self):
        for lux, pct in ab.CURVE:
            self.assertAlmostEqual(ab.curve_pct(lux), pct, places=9, msg=lux)

    def test_points_table(self):
        self.assertEqual(ab.CURVE, ((0.0, 20.0), (3.0, 30.0), (30.0, 45.0),
                                    (300.0, 70.0), (3000.0, 95.0),
                                    (10000.0, 100.0)))

    def test_interpolated_on_log_lux(self):
        # Halfway between 3 and 30 lux on the log10(1 + lux) axis.
        mid = 10 ** ((math.log10(4) + math.log10(31)) / 2) - 1
        self.assertAlmostEqual(
            ab.curve_pct(mid), (ab.curve_pct(3) + ab.curve_pct(30)) / 2,
            places=9)
        self.assertLess(ab.curve_pct(1000), ab.curve_pct(3000))
        self.assertGreater(ab.curve_pct(1000), ab.curve_pct(300))

    def test_monotonic(self):
        values = [ab.curve_pct(10 ** (e / 10)) for e in range(-30, 51)]
        self.assertEqual(values, sorted(values))

    def test_ends(self):
        self.assertEqual(ab.curve_pct(-5), ab.CURVE[0][1])
        self.assertEqual(ab.curve_pct(10000), ab.CURVE[-1][1])
        self.assertEqual(ab.curve_pct(1e6), ab.CURVE[-1][1])

    def test_target_clamped(self):
        self.assertEqual(ab.target_pct(0, -50), 3.0)
        self.assertEqual(ab.target_pct(3000, 50), 100.0)
        self.assertAlmostEqual(ab.target_pct(300, -10), ab.curve_pct(300) - 10)
        for lux in (0, 1, 50, 1e5):
            for offset in (-50, 0, 50):
                self.assertGreaterEqual(ab.target_pct(lux, offset), 3.0)
                self.assertLessEqual(ab.target_pct(lux, offset), 100.0)

    def test_raw_never_zero(self):
        self.assertEqual(ab.pct_to_raw(0, MAX), 1)
        self.assertEqual(ab.pct_to_raw(-3, MAX), 1)
        self.assertEqual(ab.pct_to_raw(100, MAX), MAX)
        self.assertEqual(ab.pct_to_raw(65, MAX), 2662)  # 2661.75 rounded
        self.assertEqual(ab.pct_to_raw(50, MAX), 2048)  # 2047.5 rounded up


class SmoothingTest(unittest.TestCase):
    def test_first_reading_taken_as_is(self):
        self.assertEqual(ab.smooth_step(None, 42.0, 0.25), 42.0)

    def test_no_time_no_change(self):
        self.assertEqual(ab.smooth_step(10.0, 100.0, 0.0), 10.0)

    def test_rise_time_constant_1s(self):
        self.assertAlmostEqual(ab.smooth_step(0.0, 100.0, 1.0),
                               100 * (1 - math.exp(-1)))

    def test_fall_time_constant_3s(self):
        self.assertAlmostEqual(ab.smooth_step(100.0, 0.0, 3.0),
                               100 * math.exp(-1))

    def test_brightens_faster_than_it_dims(self):
        up = ab.smooth_step(10.0, 110.0, 0.5) - 10.0
        down = 110.0 - ab.smooth_step(110.0, 10.0, 0.5)
        self.assertGreater(up, 2 * down)

    def test_step_independent(self):
        # Ten 0.1 s steps equal one 1 s step for a constant input.
        s = 0.0
        for _ in range(10):
            s = ab.smooth_step(s, 100.0, 0.1)
        self.assertAlmostEqual(s, ab.smooth_step(0.0, 100.0, 1.0))


class HysteresisAndRampTest(unittest.TestCase):
    def test_needs_move(self):
        self.assertFalse(ab.needs_move(50.0, 50.0))
        self.assertFalse(ab.needs_move(50.0, 46.01))
        self.assertTrue(ab.needs_move(50.0, 46.0))
        self.assertTrue(ab.needs_move(50.0, 54.0))
        self.assertFalse(ab.needs_move(50.0, 53.99))

    def test_ramp(self):
        self.assertEqual(ab.ramp_value(100, 200, 0.0), 100)
        self.assertEqual(ab.ramp_value(100, 200, 0.25), 150)
        self.assertEqual(ab.ramp_value(100, 200, 0.5), 200)
        self.assertEqual(ab.ramp_value(100, 200, 9.0), 200)
        self.assertEqual(ab.ramp_value(200, 100, 0.25), 150)
        self.assertEqual(ab.ramp_value(100, 200, -1.0), 100)


class OverrideFunctionsTest(unittest.TestCase):
    def test_manual_change(self):
        self.assertFalse(ab.is_manual_change(2000, 2000, MAX))
        self.assertFalse(ab.is_manual_change(2040, 2000, MAX))  # 40 <= 40.95
        self.assertTrue(ab.is_manual_change(2041, 2000, MAX))
        self.assertTrue(ab.is_manual_change(1959, 2000, MAX))
        self.assertFalse(ab.is_manual_change(2041, None, MAX))
        self.assertFalse(ab.is_manual_change(None, 2000, MAX))

    def test_offset(self):
        self.assertEqual(ab.override_offset(30.0, 20.0), 10.0)
        self.assertEqual(ab.override_offset(10.0, 20.0), -10.0)
        self.assertEqual(ab.override_offset(100.0, 5.0), 50.0)
        self.assertEqual(ab.override_offset(3.0, 90.0), -50.0)


class ParseTest(unittest.TestCase):
    def test_initial_line(self):
        self.assertEqual(ab.parse_line(
            "=== Has ambient light sensor (value: 2.400000, unit: lux)"),
            ("lux", 2.4))
        self.assertEqual(ab.parse_line(
            "=== Has ambient light sensor (value: 0.000000, unit: lux)\n"),
            ("lux", 0.0))

    def test_change_line(self):
        self.assertEqual(ab.parse_line("    Light changed: 0.300000 (lux)"),
                         ("lux", 0.3))
        self.assertEqual(ab.parse_line(b"    Light changed: 12.500000 (lux)\n"),
                         ("lux", 12.5))
        self.assertEqual(ab.parse_line("    Light changed: 7 (vendor)"),
                         ("lux", 7.0))
        self.assertEqual(ab.parse_line("Light changed: 1e3"), ("lux", 1000.0))

    def test_decimal_comma(self):
        self.assertEqual(ab.parse_line(
            "=== Has ambient light sensor (value: 0,300000, unit: lux)"),
            ("lux", 0.3))
        self.assertEqual(ab.parse_line("    Light changed: 1234,500000 (lux)"),
                         ("lux", 1234.5))
        self.assertEqual(ab.parse_line(
            "=== Has ambient light sensor (value: 3, unit: lux)"), ("lux", 3.0))

    def test_sensor_state_lines(self):
        self.assertEqual(ab.parse_line("=== No ambient light sensor"),
                         ("missing", None))
        self.assertEqual(ab.parse_line("--- Light sensor disappeared"),
                         ("gone", None))
        self.assertEqual(ab.parse_line(
            "--- iio-sensor-proxy vanished, waiting for it to appear"),
            ("gone", None))

    def test_junk(self):
        junk = [
            "", "\n", "x" * 10000,
            "    Waiting for iio-sensor-proxy to appear",
            "+++ iio-sensor-proxy appeared",
            "+++ Light sensor appeared",
            "    Accelerometer orientation changed: normal",
            "=== Has accelerometer (orientation: normal, tilt: vertical)",
            "    Light changed: abc (lux)",
            "    Light changed:  (lux)",
            "    Light changed: -1.000000 (lux)",
            "    Light changed: 1e999 (lux)",
            "    Light changed: 12abc (lux)",
            "=== Has ambient light sensor (value: nan, unit: lux)",
            "=== Has ambient light sensor (value: inf, unit: lux)",
            "=== Has ambient light sensor (value: , unit: lux)",
            b"\xff\xfe\x00garbage\x80",
            None, 42,
        ]
        for line in junk:
            self.assertIsNone(ab.parse_line(line), msg=repr(line)[:60])


class StateFilesTest(TempDirTest):
    def env(self):
        return {"XDG_STATE_HOME": os.path.join(self.tmp, "state"),
                "XDG_RUNTIME_DIR": os.path.join(self.tmp, "nonexistent-run")}

    def run_main(self, *args):
        out = io.StringIO()
        with mock.patch.dict(os.environ, self.env()), \
                contextlib.redirect_stdout(out):
            code = ab.main(list(args))
        return code, out.getvalue()

    def test_dirs(self):
        env = self.env()
        self.assertEqual(ab.state_dir(env),
                         os.path.join(self.tmp, "state", "yt11"))
        self.assertEqual(ab.runtime_dir(env), ab.state_dir(env))
        env["XDG_RUNTIME_DIR"] = self.tmp
        self.assertEqual(ab.runtime_dir(env), os.path.join(self.tmp, "yt11"))
        home = ab.state_dir({})
        self.assertTrue(home.endswith(os.path.join(".local", "state", "yt11")))

    def test_on_off_toggle_status(self):
        off_file = os.path.join(self.tmp, "state", "yt11", "autobrightness-off")
        self.assertEqual(self.run_main("status"), (0, "on\n"))
        self.assertEqual(self.run_main("off"), (0, "off\n"))
        self.assertTrue(os.path.exists(off_file))
        self.assertEqual(self.run_main("status"), (0, "off\n"))
        self.assertEqual(self.run_main("off"), (0, "off\n"))
        self.assertEqual(self.run_main("toggle"), (0, "on\n"))
        self.assertFalse(os.path.exists(off_file))
        self.assertEqual(self.run_main("toggle"), (0, "off\n"))
        self.assertEqual(self.run_main("on"), (0, "on\n"))
        self.assertEqual(self.run_main("on"), (0, "on\n"))
        self.assertFalse(os.path.exists(off_file))

    def test_bad_usage(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(ab.main(["bogus"]), 2)
            self.assertEqual(ab.main(["on", "extra"]), 2)
        self.assertIn("usage", err.getvalue())

    def test_offset_file(self):
        sdir = os.path.join(self.tmp, "state", "yt11")
        self.assertEqual(ab.load_offset(sdir), 0.0)
        ab.save_offset(sdir, 12.34)
        with open(os.path.join(sdir, "autobrightness-offset")) as f:
            self.assertEqual(f.read(), "12.3\n")
        self.assertAlmostEqual(ab.load_offset(sdir), 12.3)
        for text, value in (("junk", 0.0), ("", 0.0), ("nan", 0.0),
                            ("-80", -50.0), ("75.5\n", 50.0), ("-7", -7.0)):
            write_file(os.path.join(sdir, "autobrightness-offset"), text)
            self.assertEqual(ab.load_offset(sdir), value, msg=text)

    def test_status_text(self):
        self.assertEqual(ab.format_status(True, None), "on")
        self.assertEqual(ab.format_status(False, None), "off")
        self.assertEqual(
            ab.format_status(True, {"lux": 2.4, "target": 13.84, "offset": 5.0}),
            "on\nlux 2.4\ntarget 14%\noffset +5")
        self.assertEqual(
            ab.format_status(False, {"lux": 300.0, "target": 65.0, "offset": 0}),
            "off\nlux 300\ntarget 65%\noffset +0")
        self.assertEqual(ab.format_status(True, {"lux": None, "target": None}),
                         "on\nlux -\ntarget -")

    def test_read_status_needs_live_pid(self):
        rdir = os.path.join(self.tmp, "run")
        os.makedirs(rdir)
        self.assertIsNone(ab.read_status(rdir))
        ab.write_status(rdir, {"pid": os.getpid(), "lux": 1.0})
        self.assertEqual(ab.read_status(rdir)["lux"], 1.0)
        dead = subprocess.Popen([sys.executable, "-c", "pass"])
        dead.wait()
        ab.write_status(rdir, {"pid": dead.pid, "lux": 1.0})
        self.assertIsNone(ab.read_status(rdir))
        write_file(os.path.join(rdir, "autobrightness-status"), "{broken")
        self.assertIsNone(ab.read_status(rdir))

    def test_find_backlight_dir(self):
        sysdir = os.path.join(self.tmp, "sys")
        missing_cmd = os.path.join(self.tmp, "no-omarchy-hw-display")
        self.assertIsNone(ab.find_backlight_dir({}, sysdir, missing_cmd))
        os.makedirs(os.path.join(sysdir, "b-second"))
        os.makedirs(os.path.join(sysdir, "a-first"))
        self.assertEqual(ab.find_backlight_dir({}, sysdir, missing_cmd),
                         os.path.join(sysdir, "a-first"))
        hw = os.path.join(self.tmp, "hw-display")
        write_file(hw, "#!/bin/sh\necho b-second\n")
        os.chmod(hw, 0o755)
        self.assertEqual(ab.find_backlight_dir({}, sysdir, hw),
                         os.path.join(sysdir, "b-second"))
        self.assertEqual(
            ab.find_backlight_dir({"YT11_BACKLIGHT_DIR": self.tmp}, sysdir, hw),
            self.tmp)
        self.assertIsNone(ab.find_backlight_dir(
            {"YT11_BACKLIGHT_DIR": os.path.join(self.tmp, "nope")}, sysdir, hw))


class ControllerTest(TempDirTest):
    """The controller against a fake backlight directory and a fake clock."""

    def setUp(self):
        super().setUp()
        self.sdir = os.path.join(self.tmp, "state", "yt11")
        os.makedirs(self.sdir)

    def make(self, brightness=2048, bl_power=0):
        self.path = self.make_backlight(brightness, bl_power)
        self.bl = ab.Backlight(self.path)
        self.writes = []
        write = self.bl.write

        def recording_write(value):
            self.writes.append((self.now, value))
            return write(value)

        self.bl.write = recording_write
        self.now = 0.0
        self.ctl = ab.Controller(self.bl, self.sdir, self.now)
        return self.ctl

    def advance(self, until):
        while self.now < until:
            self.now += self.ctl.tick(self.now)

    def lux(self, value):
        self.ctl.feed(("lux", value))

    def brightness(self):
        return read_int(os.path.join(self.path, "brightness"))

    def set_file(self, name, value):
        write_file(os.path.join(self.path, name), f"{value}\n")

    def test_ramps_to_curve(self):
        target = raw(ab.curve_pct(300.0))
        self.make(brightness=2048)
        self.lux(300.0)
        self.advance(1.0)
        self.assertEqual(self.brightness(), target)
        values = [v for _, v in self.writes]
        self.assertGreaterEqual(len(values), 5)  # small steps
        self.assertEqual(values, sorted(values))
        self.assertEqual(values[-1], target)
        self.assertTrue(all(v >= 1 for v in values))
        span = self.writes[-1][0] - self.writes[0][0]
        self.assertGreater(span, 0.3)
        self.assertLess(span, 0.6)
        self.assertFalse(os.path.exists(
            os.path.join(self.sdir, "autobrightness-offset")))

    def test_dark_room_never_zero(self):
        self.make(brightness=2048)
        self.lux(0.0)
        self.advance(2.0)
        self.assertEqual(self.brightness(), raw(ab.curve_pct(0.0)))
        self.assertTrue(all(v >= 1 for _, v in self.writes))

    def test_hysteresis(self):
        base = ab.curve_pct(300.0) - 3
        self.make(brightness=raw(base))  # 3 points away from target at 300 lux
        self.lux(300.0)
        self.advance(3.0)
        self.assertEqual(self.writes, [])
        self.lux(320.0)  # still under 4 points
        self.advance(8.0)
        self.assertEqual(self.writes, [])
        self.lux(500.0)  # moves, then stays within 4 points
        self.advance(16.0)
        self.assertTrue(self.writes)
        pct = ab.raw_to_pct(self.brightness(), MAX)
        self.assertGreater(pct, base + 4.0)
        self.assertLess(abs(pct - ab.target_pct(500.0)), 4.0)

    def test_asymmetric_in_controller(self):
        self.make(brightness=raw(ab.curve_pct(300.0)))
        self.lux(300.0)
        self.ctl.tick(0.0)
        self.assertEqual(self.ctl.smoothed, 300.0)
        self.lux(3.0)  # falls: 3 s time constant
        self.ctl.tick(1.0)
        self.assertAlmostEqual(self.ctl.smoothed, 3 + 297 * math.exp(-1 / 3))
        start = self.ctl.smoothed
        self.lux(3000.0)  # rises: 1 s time constant
        self.ctl.tick(2.0)
        self.assertAlmostEqual(self.ctl.smoothed,
                               3000 - (3000 - start) * math.exp(-1))

    def test_manual_override(self):
        base = ab.curve_pct(300.0)
        self.make(brightness=2048)
        self.lux(300.0)
        self.advance(1.0)
        self.assertEqual(self.brightness(), raw(base))
        self.writes.clear()
        # The user drags the slider: +5, +10, then +15 points.
        for pct in (base + 5, base + 10, base + 15):
            self.set_file("brightness", raw(pct))
            drag_end = self.now
            self.advance(self.now + 1.0)
        offset_file = os.path.join(self.sdir, "autobrightness-offset")
        with open(offset_file) as f:
            self.assertAlmostEqual(float(f.read()), 15.0, places=1)
        self.assertAlmostEqual(self.ctl.offset, 15.0, places=1)
        # Light rises during the hold: nothing written for 5 s.
        self.lux(3000.0)
        self.advance(drag_end + 4.9)
        self.assertEqual(self.writes, [])
        self.assertEqual(self.brightness(), raw(base + 15))
        # Then curve + offset (95 + 15, clamped to 100).
        self.advance(drag_end + 7.0)
        self.assertEqual(self.brightness(), MAX)

    def test_offset_applies_both_ways(self):
        low = ab.curve_pct(300.0) - 30
        self.make(brightness=2048)
        self.lux(300.0)
        self.advance(1.0)
        self.set_file("brightness", raw(low))  # 30 points under the curve
        self.advance(7.0)
        self.assertAlmostEqual(self.ctl.offset, -30.0, places=1)
        self.assertEqual(self.brightness(), raw(low))
        self.lux(3.0)  # curve 30 - 30: clamped to 3 %
        self.advance(40.0)
        self.assertAlmostEqual(self.ctl.target, 3.0)
        pct = ab.raw_to_pct(self.brightness(), MAX)
        self.assertGreaterEqual(pct, 3.0 - 0.05)
        self.assertLess(pct, 3.0 + 4.0)  # within the hysteresis

    def test_off_then_on_keeps_offset(self):
        self.make(brightness=2048)
        self.lux(300.0)
        self.advance(1.0)
        self.set_file("brightness", raw(ab.curve_pct(300.0) + 10))  # offset +10
        self.advance(7.0)
        ab.set_enabled(self.sdir, False)
        self.advance(8.0)
        self.writes.clear()
        self.set_file("brightness", raw(30))  # moved while off: not an override
        self.advance(15.0)
        self.assertEqual(self.writes, [])
        self.assertEqual(self.brightness(), raw(30))
        self.assertAlmostEqual(self.ctl.offset, 10.0, places=1)
        self.assertIsNotNone(self.ctl.target)  # still tracked while off
        ab.set_enabled(self.sdir, True)
        on_at = self.now
        self.advance(on_at + 1.0)  # takes effect within a second
        self.assertTrue(self.writes)
        self.assertLess(self.writes[0][0] - on_at, 1.0)
        self.assertEqual(self.brightness(), raw(ab.curve_pct(self.ctl.smoothed) + 10))
        self.assertAlmostEqual(ab.load_offset(self.sdir), 10.0, places=1)
        # A new helper (next session) starts with the same offset.
        self.assertAlmostEqual(ab.Controller(self.bl, self.sdir, 0).offset, 10.0,
                               places=1)

    def test_starts_off(self):
        ab.set_enabled(self.sdir, False)
        self.make(brightness=2048)
        self.lux(300.0)
        self.advance(5.0)
        self.assertEqual(self.writes, [])
        self.assertEqual(self.brightness(), 2048)

    def test_bl_power_guard(self):
        self.make(brightness=2048, bl_power=4)
        self.lux(300.0)
        self.advance(1.0)
        self.lux(0.0)  # the sensor reads 0 with the screen off: ignored
        self.set_file("brightness", 1000)  # changed while off: not an override
        self.advance(5.0)
        self.assertEqual(self.writes, [])
        self.assertEqual(self.brightness(), 1000)
        self.set_file("bl_power", 0)
        self.advance(7.0)
        self.assertEqual(self.brightness(), raw(ab.curve_pct(300.0)))
        self.assertEqual(self.ctl.offset, 0.0)
        self.assertFalse(os.path.exists(
            os.path.join(self.sdir, "autobrightness-offset")))

    def test_guard_mid_ramp(self):
        self.make(brightness=raw(10))
        self.lux(3000.0)
        self.advance(0.2)
        self.set_file("bl_power", 4)
        count = len(self.writes)
        self.advance(3.0)
        self.assertEqual(len(self.writes), count)

    def test_brightness_zero_guard(self):
        self.make(brightness=0)
        self.lux(300.0)
        self.advance(5.0)
        self.assertEqual(self.writes, [])
        self.assertEqual(self.brightness(), 0)
        self.set_file("brightness", 2048)
        self.advance(6.0)
        self.assertEqual(self.brightness(), raw(ab.curve_pct(300.0)))
        self.assertEqual(self.ctl.offset, 0.0)

    def test_sensor_gone(self):
        self.make(brightness=2048)
        self.ctl.feed(("gone", None))
        self.lux(300.0)  # back
        self.advance(1.0)
        self.assertEqual(self.brightness(), raw(ab.curve_pct(300.0)))
        self.ctl.feed(("gone", None))
        self.writes.clear()
        self.ctl.lux = 3000.0
        self.advance(5.0)
        self.assertEqual(self.writes, [])

    def test_no_reading_no_write(self):
        self.make(brightness=2048)
        self.advance(5.0)
        self.assertEqual(self.writes, [])


FAKE_MONITOR = textwrap.dedent(r'''
    import os, sys, time

    def out(line):
        print(line, flush=True)

    count_file = os.environ["FAKE_COUNT"]
    try:
        with open(count_file) as f:
            n = int(f.read())
    except (OSError, ValueError):
        n = 0
    with open(count_file, "w") as f:
        f.write(str(n + 1))
    with open(os.environ["FAKE_PID"], "w") as f:
        f.write(str(os.getpid()))
    if sys.argv[1:] != ["--light"] or os.environ.get("LC_ALL") != "C":
        out("=== No ambient light sensor")
        sys.exit(3)
    if os.environ.get("FAKE_MODE") == "hang":
        out("=== Has ambient light sensor (value: 30.000000, unit: lux)")
        time.sleep(60)
        sys.exit(0)
    if n == 0:
        out("    Waiting for iio-sensor-proxy to appear")
        out("+++ iio-sensor-proxy appeared")
        out("=== Has ambient light sensor (value: 300.000000, unit: lux)")
        out("garbage \x01\x02 line")
        out("    Light changed: abc (lux)")
        time.sleep(2.0)
        out("    Light changed: 3000.000000 (lux)")
        time.sleep(2.5)
        sys.stdout.write("    Light chan")  # cut short by the exit
        sys.stdout.flush()
        sys.exit(1)
    out("=== No ambient light sensor")
    time.sleep(30)
''')


class DaemonTest(TempDirTest):
    """End-to-end runs of the script with a fake monitor-sensor."""

    def setUp(self):
        super().setUp()
        self.backlight = self.make_backlight(brightness=2048)
        self.state = os.path.join(self.tmp, "state")
        self.run_dir = os.path.join(self.tmp, "run")
        os.makedirs(self.run_dir)
        fake = os.path.join(self.tmp, "fake-monitor-sensor.py")
        write_file(fake, FAKE_MONITOR)
        self.pid_file = os.path.join(self.tmp, "fake.pid")
        self.count_file = os.path.join(self.tmp, "fake.count")
        self.env = dict(os.environ)
        self.env.update({
            "XDG_STATE_HOME": self.state,
            "XDG_RUNTIME_DIR": self.run_dir,
            "YT11_BACKLIGHT_DIR": self.backlight,
            "YT11_MONITOR_SENSOR": shlex.join([sys.executable, fake]),
            "FAKE_COUNT": self.count_file,
            "FAKE_PID": self.pid_file,
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        self.env.pop("LC_ALL", None)
        self.rdir = os.path.join(self.run_dir, "yt11")

    def start(self, **extra):
        env = dict(self.env, **extra)
        return subprocess.Popen([sys.executable, SCRIPT], env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True)

    def run_script(self, *args, **extra):
        env = dict(self.env, **extra)
        return subprocess.run([sys.executable, SCRIPT, *args], env=env,
                              capture_output=True, text=True, timeout=10)

    def wait_status(self, lux, timeout=5.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            data = ab.read_status(self.rdir)
            if data and data.get("lux") == lux:
                return data
            time.sleep(0.05)
        self.fail(f"no status with lux {lux}")

    def assert_fake_gone(self):
        with open(self.pid_file) as f:
            pid = int(f.read())
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            time.sleep(0.05)
        self.fail("fake monitor-sensor still running")

    def test_end_to_end(self):
        curve300 = ab.curve_pct(300.0)
        curve3000 = ab.curve_pct(3000.0)
        started = time.monotonic()
        proc = self.start()
        try:
            data = self.wait_status(300.0)
            self.assertEqual(data["target"], curve300)
            result = self.run_script("status")
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout.splitlines()[:3],
                             ["on", "lux 300", f"target {curve300:.0f}%"])
            out, err = proc.communicate(timeout=15)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
        elapsed = time.monotonic() - started
        self.assertEqual(proc.returncode, 0, err)
        self.assertLess(elapsed, 15)
        self.assertIn("monitor-sensor exited (1)", err)
        self.assertIn("no ambient light sensor", err)
        with open(self.count_file) as f:
            self.assertEqual(f.read(), "2")  # restarted once
        final = read_int(os.path.join(self.backlight, "brightness"))
        pct = ab.raw_to_pct(final, MAX)
        # 3000 lux: curve ~95 %, hysteresis 4
        self.assertGreaterEqual(pct, curve3000 - 5.0)
        self.assertLessEqual(pct, curve3000 + 0.5)
        self.assertFalse(os.path.exists(  # its own writes are not overrides
            os.path.join(self.state, "yt11", "autobrightness-offset")))
        self.assertFalse(os.path.exists(os.path.join(self.rdir,
                                                     "autobrightness-status")))
        self.assert_fake_gone()
        self.assertEqual(self.run_script("status").stdout, "on\n")

    def test_sigterm_kills_child(self):
        proc = self.start(FAKE_MODE="hang")
        try:
            self.wait_status(30.0)
            time.sleep(1.0)  # let the ramp finish
            proc.send_signal(signal.SIGTERM)
            out, err = proc.communicate(timeout=5)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
        self.assertEqual(proc.returncode, 0, err)
        self.assert_fake_gone()
        self.assertFalse(os.path.exists(os.path.join(self.rdir,
                                                     "autobrightness-status")))
        self.assertEqual(read_int(os.path.join(self.backlight, "brightness")),
                         raw(ab.curve_pct(30.0)))

    def test_off_while_running(self):
        target30 = ab.curve_pct(30.0)
        self.assertEqual(self.run_script("off").stdout, "off\n")
        proc = self.start(FAKE_MODE="hang")
        try:
            self.wait_status(30.0)
            time.sleep(1.0)
            self.assertEqual(read_int(os.path.join(self.backlight, "brightness")),
                             2048)
            result = self.run_script("status")
            self.assertEqual(result.stdout.splitlines()[:3],
                             ["off", "lux 30", f"target {target30:.0f}%"])
            self.assertEqual(self.run_script("on").stdout, "on\n")
            time.sleep(1.5)
            self.assertEqual(read_int(os.path.join(self.backlight, "brightness")),
                             raw(target30))
            proc.send_signal(signal.SIGTERM)
            proc.communicate(timeout=5)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
        self.assertEqual(proc.returncode, 0)

    def test_missing_backlight(self):
        result = self.run_script(YT11_BACKLIGHT_DIR=os.path.join(self.tmp, "no"))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(len(result.stderr.splitlines()), 1, result.stderr)
        self.assertIn("no backlight", result.stderr)

    def test_missing_monitor_sensor(self):
        result = self.run_script(
            YT11_MONITOR_SENSOR=os.path.join(self.tmp, "no-monitor-sensor"))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(len(result.stderr.splitlines()), 1, result.stderr)
        self.assertIn("cannot run", result.stderr)

    def test_missing_sensor(self):
        write_file(self.count_file, "1")  # the fake's second run: no sensor
        result = self.run_script()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr.strip(),
                         "yt11-autobrightness: no ambient light sensor, exiting")
        self.assert_fake_gone()
        self.assertEqual(read_int(os.path.join(self.backlight, "brightness")),
                         2048)

    def test_second_instance(self):
        os.makedirs(self.rdir)
        fd = ab.take_lock(self.rdir)
        self.assertIsInstance(fd, int)
        self.assertGreaterEqual(fd, 0)
        try:
            result = self.run_script()
        finally:
            os.close(fd)
        self.assertEqual(result.returncode, 0)
        self.assertIn("already running", result.stderr)
        self.assertFalse(os.path.exists(self.count_file))


if __name__ == "__main__":
    unittest.main()
