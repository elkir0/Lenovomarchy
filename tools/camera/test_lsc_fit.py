#!/usr/bin/env python3
"""Offline unit tests for tools/camera/lsc-fit.py (stdlib only).

Synthetic flat fields with a known per-channel falloff gain(r) = 1 + k1 r^2
+ k2 r^4 + k3 r^6 about an off-centre optical centre, packed with the
helpers of test_raw2rgb.py, with mild deterministic noise.
"""

import contextlib
import importlib.machinery
import importlib.util
import io
import os
import random
import re
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True  # keep tools/camera free of __pycache__
HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
from test_raw2rgb import BAYER_PATTERN, pack_le10, pack_u16  # noqa: E402


def _load_lsc_fit():
    loader = importlib.machinery.SourceFileLoader('lsc_fit', os.path.join(HERE, 'lsc-fit.py'))
    spec = importlib.util.spec_from_loader('lsc_fit', loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


lsc = _load_lsc_fit()

W, H = 320, 240
BLACK = 64
COEFFS = {'R': (0.55, 0.25, 0.10), 'G': (0.45, 0.15, 0.05), 'B': (0.60, 0.20, 0.20)}
LEVELS = {'R': 380.0, 'G': 700.0, 'B': 330.0}  # black-subtracted, at the centre
NAMES = {'R': 'red', 'G': 'green', 'B': 'blue'}


def poly_gain(k, r2):
    return 1.0 + k[0] * r2 + k[1] * r2 ** 2 + k[2] * r2 ** 3


def flat_field(order, centre, seed=1, levels=LEVELS, modulate=None, noise=1.5,
               width=W, height=H):
    """10-bit Bayer rows of a flat field shaded by COEFFS about `centre`."""
    pat = BAYER_PATTERN[order]
    cx, cy = centre[0] * width, centre[1] * height
    inv = 4.0 / (width * width + height * height)
    rnd = random.Random(seed)
    rows = []
    for y in range(height):
        dy2 = (y + 0.5 - cy) ** 2
        row = []
        for x in range(width):
            ch = pat[y & 1][x & 1]
            r2 = ((x + 0.5 - cx) ** 2 + dy2) * inv
            s = levels[ch] / poly_gain(COEFFS[ch], r2)
            if modulate is not None:
                s *= modulate(x, y)
            v = int(round(BLACK + s + rnd.gauss(0.0, noise)))
            row.append(min(1023, max(0, v)))
        rows.append(row)
    return rows


def run_lsc(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = lsc.main(argv)
    return rc, out.getvalue(), err.getvalue()


class LscTestCase(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, name, data):
        path = os.path.join(self.tmp, name)
        with open(path, 'wb') as f:
            f.write(data)
        return path

    def assert_gains_close(self, fit, centre, tol=0.01, width=W, height=H):
        """Fitted gains within tol of the true ones over the whole frame."""
        inv = 4.0 / (width * width + height * height)
        worst = (0.0, None)
        for ch, name in NAMES.items():
            for j in range(21):
                for i in range(21):
                    x, y = i / 20 * width, j / 20 * height
                    rt = ((x - centre[0] * width) ** 2 + (y - centre[1] * height) ** 2) * inv
                    rf = ((x - fit['centre'][0] * width) ** 2
                          + (y - fit['centre'][1] * height) ** 2) * inv
                    err = abs(poly_gain(fit[name], rf) / poly_gain(COEFFS[ch], rt) - 1.0)
                    if err > worst[0]:
                        worst = (err, (name, i / 20, j / 20))
        self.assertLess(worst[0], tol, f'worst gain error {worst[0] * 100:.3f} % at {worst[1]}')

    def assert_centre_close(self, fit, centre, tol=0.02):
        self.assertLess(abs(fit['centre'][0] - centre[0]), tol, fit['centre'])
        self.assertLess(abs(fit['centre'][1] - centre[1]), tol, fit['centre'])


class TestFit(LscTestCase):
    """Recover known coefficients and an off-centre optical centre."""

    def test_u16_rggb_auto_centre(self):
        centre = (0.53, 0.47)
        path = self.write('u16.raw', pack_u16(flat_field('rggb', centre)))
        rc, out, err = run_lsc([path, str(W), str(H), '--bayer', 'RGGB', '--layout', 'u16'])
        self.assertEqual(rc, 0, err)
        fit = lsc.parse_lsc_yaml(out)
        self.assert_centre_close(fit, centre)
        self.assert_gains_close(fit, centre)
        self.assertIn('(auto, green-plane residual search)', out)

    def test_le10_bggr_detected_layout(self):
        centre = (0.46, 0.55)
        path = self.write('le10.raw', pack_le10(flat_field('bggr', centre, seed=2)))
        rc, out, err = run_lsc([path, str(W), str(H), '--bayer', 'BGGR'])
        self.assertEqual(rc, 0, err)
        self.assertIn('le10', err)  # the detection note
        self.assertIn('layout le10', out)
        fit = lsc.parse_lsc_yaml(out)
        self.assert_centre_close(fit, centre)
        self.assert_gains_close(fit, centre)

    def test_u16_detection_prefers_low_bits(self):
        # u16 and u16h share the byte geometry; the unused container bits
        # decide between them.
        centre = (0.5, 0.5)
        path = self.write('u16auto.raw', pack_u16(flat_field('rggb', centre, seed=6)))
        rc, out, err = run_lsc([path, str(W), str(H), '--bayer', 'rggb'])
        self.assertEqual(rc, 0, err)
        self.assertIn('layout u16,', out)

    def test_grbg_given_centre(self):
        centre = (0.53, 0.47)
        path = self.write('grbg.raw', pack_u16(flat_field('grbg', centre, seed=3)))
        rc, out, err = run_lsc([path, str(W), str(H), '--bayer', 'grbg', '--layout', 'u16',
                                '--centre', '0.53,0.47'])
        self.assertEqual(rc, 0, err)
        fit = lsc.parse_lsc_yaml(out)
        self.assertEqual(fit['centre'], (0.53, 0.47))
        self.assertIn('(given)', out)
        self.assert_gains_close(fit, centre)

    def test_gbrg_le10_coarse_grid(self):
        centre = (0.52, 0.53)
        path = self.write('gbrg.raw', pack_le10(flat_field('gbrg', centre, seed=4)))
        rc, out, err = run_lsc([path, str(W), str(H), '--bayer', 'GBRG', '--layout', 'le10',
                                '--grid', '16'])
        self.assertEqual(rc, 0, err)
        self.assertIn('grid 16x12', out)
        fit = lsc.parse_lsc_yaml(out)
        self.assert_centre_close(fit, centre)
        self.assert_gains_close(fit, centre)

    def test_output_block_format(self):
        path = self.write('fmt.raw', pack_u16(flat_field('rggb', (0.53, 0.47), seed=5)))
        rc, out, err = run_lsc([path, str(W), str(H), '--bayer', 'rggb', '--layout', 'u16'])
        self.assertEqual(rc, 0, err)
        lines = out.rstrip('\n').split('\n')
        block = lines[-5:]
        num = r'-?\d+\.\d{4}'
        self.assertEqual(block[0], '  - Lsc:')
        self.assertRegex(block[1], rf'^      centre: \[ {num}, {num} \]$')
        for line, key in zip(block[2:], ('red:   ', 'green: ', 'blue:  ')):
            self.assertRegex(line, rf'^      {key}\[ {num}, {num}, {num} \]$')
        for line in lines[:-5]:
            self.assertTrue(line.startswith('#'), line)
        for label in ('fit residual RMS:', 'fit residual max:', 'corner gain (r = 1):',
                      'centre level (black-subtracted, of 1023):'):
            self.assertIn(label, out)
        # the centre level comment reports the synthetic levels
        m = re.search(r'centre level \(black-subtracted, of 1023\): R ([\d.]+) G ([\d.]+) B ([\d.]+)', out)
        for got, want in zip(m.groups(), (LEVELS['R'], LEVELS['G'], LEVELS['B'])):
            self.assertLess(abs(float(got) / want - 1.0), 0.02)
        # the corner gain comment matches the coefficients it precedes
        fit = lsc.parse_lsc_yaml(out)
        m = re.search(r'corner gain \(r = 1\): R ([\d.]+) G ([\d.]+) B ([\d.]+)', out)
        for got, name in zip(m.groups(), ('red', 'green', 'blue')):
            self.assertAlmostEqual(float(got), 1.0 + sum(fit[name]), places=3)

    def test_clipped_cells_are_ignored(self):
        # 320x240 with --grid 32: cells of 5x5 samples per Bayer plane. The
        # saturated block covers plane x 20..39, y 15..29: 4 x 3 = 12 cells
        # in every channel. One R sample at exactly 1000 adds one R cell; a
        # G sample at 999 is still valid.
        centre = (0.53, 0.47)
        rows = flat_field('rggb', centre, seed=7)
        for y in range(30, 60):
            for x in range(40, 80):
                rows[y][x] = 1023
        rows[180][200] = 1000  # R (even row, even column in RGGB)
        rows[180][211] = 999   # G
        path = self.write('clip.raw', pack_u16(rows))
        rc, out, err = run_lsc([path, str(W), str(H), '--bayer', 'rggb', '--layout', 'u16'])
        self.assertEqual(rc, 0, err)
        self.assertIn('ignored cells (clipped samples >= 1000): R 13 G 12 B 12 of 768', out)
        fit = lsc.parse_lsc_yaml(out)
        self.assert_centre_close(fit, centre)
        self.assert_gains_close(fit, centre)


class TestUnusable(LscTestCase):
    """Frames that cannot give a trustworthy fit exit with code 1."""

    def test_dark_frame(self):
        levels = {'R': 50.0, 'G': 90.0, 'B': 45.0}
        path = self.write('dark.raw', pack_u16(flat_field('rggb', (0.5, 0.5), levels=levels)))
        rc, out, err = run_lsc([path, str(W), str(H), '--bayer', 'rggb', '--layout', 'u16'])
        self.assertEqual(rc, 1)
        self.assertEqual(out, '')
        self.assertIn('centre level', err)
        self.assertIn('under 100', err)

    def test_overexposed_frame(self):
        levels = {'R': 760.0, 'G': 1400.0, 'B': 660.0}
        path = self.write('hot.raw', pack_u16(flat_field('rggb', (0.5, 0.5), levels=levels)))
        rc, out, err = run_lsc([path, str(W), str(H), '--bayer', 'rggb', '--layout', 'u16'])
        self.assertEqual(rc, 1)
        self.assertEqual(out, '')
        self.assertRegex(err, r'only \d+ of 768 green cells are valid')

    def test_non_flat_frame(self):
        # Vertical bands of 100 % and 80 %: no radial falloff fits them.
        def bands(x, y):
            return 1.0 if (x // 40) % 2 == 0 else 0.8
        path = self.write('bands.raw', pack_u16(flat_field('rggb', (0.5, 0.5), modulate=bands)))
        rc, out, err = run_lsc([path, str(W), str(H), '--bayer', 'rggb', '--layout', 'u16'])
        self.assertEqual(rc, 1)
        self.assertEqual(out, '')
        self.assertIn('RMS fit residual above 5 %', err)

    def test_short_file(self):
        data = pack_u16(flat_field('rggb', (0.5, 0.5)))
        path = self.write('short.raw', data[: len(data) // 2])
        rc, out, err = run_lsc([path, str(W), str(H), '--bayer', 'rggb', '--layout', 'u16'])
        self.assertEqual(rc, 1)
        self.assertIn('bytes', err)


class TestMultiFrame(LscTestCase):
    """Several frames are averaged cell by cell before the fit."""

    def test_two_frames_average_out_bands(self):
        # Each frame carries +/-25 % bands in opposite phase: alone, neither
        # fits; their average is the clean flat field.
        def band(x):
            return 1.0 if (x // 40) % 2 == 0 else -1.0
        centre = (0.47, 0.53)
        a = self.write('a.raw', pack_u16(flat_field(
            'bggr', centre, seed=11, modulate=lambda x, y: 1.0 + 0.25 * band(x))))
        b = self.write('b.raw', pack_u16(flat_field(
            'bggr', centre, seed=12, modulate=lambda x, y: 1.0 - 0.25 * band(x))))
        base = [str(W), str(H), '--bayer', 'bggr', '--layout', 'u16']
        rc, _, err = run_lsc([a] + base)
        self.assertEqual(rc, 1)
        self.assertIn('residual', err)
        # extra frames may follow the options
        rc, out, err = run_lsc([a] + base + [b])
        self.assertEqual(rc, 0, err)
        self.assertIn('2 frame(s)', out)
        fit = lsc.parse_lsc_yaml(out)
        self.assert_centre_close(fit, centre)
        self.assert_gains_close(fit, centre)


class TestCheck(LscTestCase):
    """--check applies an Lsc block to the frame's grid."""

    FALLOFF = re.compile(r'^(red|green|blue):\s+falloff (-?[\d.]+) % -> (-?[\d.]+) %', re.M)

    def falloffs(self, out):
        return {m.group(1): (float(m.group(2)), float(m.group(3)))
                for m in self.FALLOFF.finditer(out)}

    def test_check_after_fit_in_tuning_file(self):
        centre = (0.53, 0.47)
        path = self.write('chk.raw', pack_u16(flat_field('rggb', centre, seed=21)))
        args = [path, str(W), str(H), '--bayer', 'rggb', '--layout', 'u16']
        rc, out, err = run_lsc(args)
        self.assertEqual(rc, 0, err)
        tuning = (
            '# SPDX-License-Identifier: CC0-1.0\n%YAML 1.1\n---\nversion: 1\nalgorithms:\n'
            '  - BlackLevel:\n  - Awb:\n      speed: 0.2\n'
            + out
            + '  - Adjust:\n      red: [ 9.0, 9.0, 9.0 ]  # not part of Lsc\n'
        )
        yaml_path = os.path.join(self.tmp, 'tuning.yaml')
        with open(yaml_path, 'w') as f:
            f.write(tuning)
        parsed = lsc.parse_lsc_yaml(tuning)
        self.assertEqual(parsed, lsc.parse_lsc_yaml(out))
        rc, cout, err = run_lsc(args + ['--check', yaml_path])
        self.assertEqual(rc, 0, err)
        fall = self.falloffs(cout)
        self.assertEqual(set(fall), {'red', 'green', 'blue'})
        for ch, (before, after) in fall.items():
            self.assertGreater(before, 20.0, ch)
            self.assertLess(abs(after), 1.0, ch)
        self.assertIn('RMS', cout)

    def test_check_identity_block(self):
        # Zero coefficients, given without the Lsc: line: nothing changes.
        path = self.write('id.raw', pack_u16(flat_field('rggb', (0.5, 0.5), seed=22)))
        yaml_path = os.path.join(self.tmp, 'id.yaml')
        with open(yaml_path, 'w') as f:
            f.write('center: [ 0.5, 0.5 ]\nred: [ 0, 0, 0 ]\n'
                    'green: [ 0.0, 0.0, 0.0 ]\nblue: [0,0,0]\n')
        rc, out, err = run_lsc([path, str(W), str(H), '--bayer', 'rggb', '--layout', 'u16',
                                '--check', yaml_path])
        self.assertEqual(rc, 0, err)
        fall = self.falloffs(out)
        self.assertEqual(len(fall), 3)
        for ch, (before, after) in fall.items():
            self.assertGreater(before, 20.0, ch)
            self.assertEqual(before, after, ch)

    def test_parser_errors(self):
        with self.assertRaisesRegex(ValueError, 'no blue'):
            lsc.parse_lsc_yaml('  - Lsc:\n      centre: [ 0.5, 0.5 ]\n'
                               '      red: [ 1, 2, 3 ]\n      green: [ 1, 2, 3 ]\n')
        with self.assertRaisesRegex(ValueError, 'expected 3'):
            lsc.parse_lsc_yaml('centre: [ 0.5, 0.5 ]\nred: [ 1, 2 ]\n'
                               'green: [ 1, 2, 3 ]\nblue: [ 1, 2, 3 ]\n')


if __name__ == '__main__':
    unittest.main()
