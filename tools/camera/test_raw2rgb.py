#!/usr/bin/env python3
"""Offline unit tests for tools/camera/raw2rgb.py (stdlib only)."""

import contextlib
import io
import os
import statistics
import struct
import sys
import tempfile
import unittest
import zlib

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import raw2rgb  # noqa: E402


BAYER_PATTERN = {
    'bggr': (('B', 'G'), ('G', 'R')),
    'gbrg': (('G', 'B'), ('R', 'G')),
    'grbg': (('G', 'R'), ('B', 'G')),
    'rggb': (('R', 'G'), ('G', 'B')),
}

SAMPLES = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'samples')
BARS_SAMPLE = os.path.join(SAMPLES, 'ov8856-bars-640x480-le10.raw')
SCENE_SAMPLE = os.path.join(SAMPLES, 'ov8856-scene-640x480-le10.raw')


def pack_le10(rows: list[list[int]], stride: int | None = None) -> bytes:
    """Pack a 2D array of 10-bit pixels into the le10 layout.

    One continuous little-endian 10-bit bit stream per line: pixel k occupies
    bits 10k..10k+9 of the line read as a little-endian integer (what CAMSV
    writes with FMT_SEL=0x102 / PAK=1 and the line sized for 10 bits).
    """
    height = len(rows)
    width = len(rows[0])
    bpl = (width * 10 + 7) // 8
    if stride is None:
        stride = bpl
    if stride < bpl:
        raise ValueError(f'stride {stride} < bpl {bpl}')
    out = bytearray()
    for y in range(height):
        line = bytearray(stride)
        for x in range(0, width, 4):
            rem = min(4, width - x)
            v = 0
            for k in range(rem):
                v |= (rows[y][x + k] & 0x3FF) << (10 * k)
            line[(x // 4) * 5 : (x // 4) * 5 + (rem * 10 + 7) // 8] = v.to_bytes(
                (rem * 10 + 7) // 8, 'little'
            )
        out.extend(line)
    return bytes(out)


def pack_raw10(rows: list[list[int]], stride: int | None = None) -> bytes:
    """Pack a 2D array of 10-bit pixels into MIPI RAW10 bytes (4 px / 5 bytes)."""
    height = len(rows)
    width = len(rows[0])
    bpl = (width * 10 + 7) // 8
    if stride is None:
        stride = bpl
    if stride < bpl:
        raise ValueError(f'stride {stride} < bpl {bpl}')
    out = bytearray()
    for y in range(height):
        row = rows[y]
        line = bytearray()
        for x in range(0, width, 4):
            rem = min(4, width - x)
            chunk = [row[x + k] for k in range(rem)]
            for k in range(rem):
                line.append((chunk[k] >> 2) & 0xFF)
            b4 = 0
            for k in range(rem):
                b4 |= (chunk[k] & 0x03) << (2 * k)
            line.append(b4)
        if len(line) < stride:
            line.extend(b'\xA5' * (stride - len(line)))
        out.extend(line)
    return bytes(out)


def pack_p12(rows: list[list[int]], stride: int | None = None) -> bytes:
    """Pack 10-bit pixels into the MT6785 p12 container layout.

    Two pixels per 3 bytes: two little-endian 12-bit fields, each holding the
    10-bit sample shifted left by two (the old begonia FMT_SEL=0x101 / PAK=2
    output). bpl = width * 12 / 8.
    """
    height = len(rows)
    width = len(rows[0])
    bpl = (width * 12 + 7) // 8
    if stride is None:
        stride = bpl
    if stride < bpl:
        raise ValueError(f'stride {stride} < bpl {bpl}')
    out = bytearray()
    for y in range(height):
        row = rows[y]
        line = bytearray()
        for x in range(0, width & ~1, 2):
            v0 = (row[x] << 2) & 0xFFF
            v1 = (row[x + 1] << 2) & 0xFFF
            line.append(v0 & 0xFF)
            line.append(((v0 >> 8) & 0x0F) | ((v1 & 0x0F) << 4))
            line.append((v1 >> 4) & 0xFF)
        if width & 1:
            v0 = (row[width - 1] << 2) & 0xFFF
            line.append(v0 & 0xFF)
            line.append((v0 >> 8) & 0x0F)
            line.append(0)
        if len(line) < stride:
            line.extend(b'\xA5' * (stride - len(line)))
        out.extend(line)
    return bytes(out)


def parse_and_verify_png(png_bytes: bytes) -> tuple[int, int, list[list[tuple[int, int, int]]]]:
    """Verify PNG signature, chunk CRCs, IHDR, IEND, and return RGB rows."""
    if not png_bytes.startswith(b'\x89PNG\r\n\x1a\n'):
        raise AssertionError('invalid PNG signature')

    pos = 8
    ihdr = None
    idat_parts = []
    saw_iend = False
    while pos < len(png_bytes):
        length = struct.unpack('>I', png_bytes[pos : pos + 4])[0]
        tag = png_bytes[pos + 4 : pos + 8]
        payload = png_bytes[pos + 8 : pos + 8 + length]
        crc_actual = struct.unpack('>I', png_bytes[pos + 8 + length : pos + 12 + length])[0]
        crc_expect = zlib.crc32(tag + payload) & 0xFFFFFFFF
        if crc_actual != crc_expect:
            raise AssertionError(f'CRC mismatch on chunk {tag!r}: {crc_actual:#x} != {crc_expect:#x}')
        pos += 12 + length

        if tag == b'IHDR':
            ihdr = struct.unpack('>IIBBBBB', payload)
        elif tag == b'IDAT':
            idat_parts.append(payload)
        elif tag == b'IEND':
            if length != 0:
                raise AssertionError('non-empty IEND chunk')
            saw_iend = True
            break

    if pos != len(png_bytes):
        raise AssertionError('trailing bytes after IEND')
    if not saw_iend or ihdr is None:
        raise AssertionError('missing IHDR or IEND')

    width, height, bit_depth, color_type, comp, filt, interlace = ihdr
    if (bit_depth, color_type, comp, filt, interlace) != (8, 2, 0, 0, 0):
        raise AssertionError(f'unexpected IHDR format: {ihdr}')

    raw = zlib.decompress(b''.join(idat_parts))
    row_len = 1 + width * 3
    if len(raw) != height * row_len:
        raise AssertionError(f'IDAT length {len(raw)} != expected {height * row_len}')

    rgb_rows = []
    for y in range(height):
        start = y * row_len
        if raw[start] != 0:
            raise AssertionError(f'unexpected PNG filter byte {raw[start]} at row {y}')
        row = []
        for x in range(width):
            p = start + 1 + x * 3
            row.append((raw[p], raw[p + 1], raw[p + 2]))
        rgb_rows.append(row)
    return width, height, rgb_rows


def make_patch_frame(width: int, height: int, order: str, black_level: int = 64) -> list[list[int]]:
    """Build a synthetic 4-quadrant colour frame (White, Red / Green, Blue) in 10-bit Bayer."""
    pat = BAYER_PATTERN[order]
    hi = 960
    lo = black_level
    quad_rgb = {
        (0, 0): {'R': hi, 'G': hi, 'B': hi},  # top-left: bright white/grey
        (0, 1): {'R': hi, 'G': lo, 'B': lo},  # top-right: red
        (1, 0): {'R': lo, 'G': hi, 'B': lo},  # bottom-left: green
        (1, 1): {'R': lo, 'G': lo, 'B': hi},  # bottom-right: blue
    }
    rows = []
    for y in range(height):
        qy = 0 if y < height // 2 else 1
        row = []
        for x in range(width):
            qx = 0 if x < width // 2 else 1
            ch = pat[y & 1][x & 1]
            row.append(quad_rgb[(qy, qx)][ch])
        rows.append(row)
    return rows


def run_raw2rgb(argv: list[str]) -> tuple[int, str]:
    buf = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
        rc = raw2rgb.main(argv)
    return rc, buf.getvalue()


class TestLe10(unittest.TestCase):
    """Synthetic le10 frames: quadrant colours, LSBs, stride, odd width."""

    def test_all_bayer_orders_half_and_full(self):
        width, height = 32, 24
        with tempfile.TemporaryDirectory() as tmp:
            for order in ('bggr', 'gbrg', 'grbg', 'rggb'):
                raw_path = os.path.join(tmp, f'test_{order}.raw')
                frames = make_patch_frame(width, height, order, black_level=64)
                with open(raw_path, 'wb') as f:
                    f.write(pack_le10(frames))

                half_png = os.path.join(tmp, f'half_{order}.png')
                rc, _ = run_raw2rgb([raw_path, str(width), str(height), half_png, '--bayer', order])
                self.assertEqual(rc, 0)
                with open(half_png, 'rb') as f:
                    pw, ph, rgb = parse_and_verify_png(f.read())
                self.assertEqual((pw, ph), (width // 2, height // 2))

                w_px = rgb[2][2]
                r_px = rgb[2][pw - 3]
                g_px = rgb[ph - 3][2]
                b_px = rgb[ph - 3][pw - 3]

                self.assertGreater(w_px[0], 220)
                self.assertLess(abs(w_px[0] - w_px[1]), 3)
                self.assertLess(abs(w_px[1] - w_px[2]), 3)

                self.assertGreater(r_px[0], 220)
                self.assertEqual(r_px[1], 0)
                self.assertEqual(r_px[2], 0)

                self.assertEqual(g_px[0], 0)
                self.assertGreater(g_px[1], 220)
                self.assertEqual(g_px[2], 0)

                self.assertEqual(b_px[0], 0)
                self.assertEqual(b_px[1], 0)
                self.assertGreater(b_px[2], 220)

                full_png = os.path.join(tmp, f'full_{order}.png')
                rc, _ = run_raw2rgb([
                    raw_path, str(width), str(height), full_png, '--bayer', order, '--full',
                ])
                self.assertEqual(rc, 0)
                with open(full_png, 'rb') as f:
                    fw, fh, frgb = parse_and_verify_png(f.read())
                self.assertEqual((fw, fh), (width, height))

                self.assertGreater(frgb[4][4][0], 220)
                self.assertGreater(frgb[4][fw - 5][0], 220)
                self.assertEqual(frgb[4][fw - 5][1], 0)
                self.assertEqual(frgb[4][fw - 5][2], 0)
                self.assertGreater(frgb[fh - 5][4][1], 220)
                self.assertEqual(frgb[fh - 5][4][0], 0)
                self.assertEqual(frgb[fh - 5][4][2], 0)
                self.assertGreater(frgb[fh - 5][fw - 5][2], 220)
                self.assertEqual(frgb[fh - 5][fw - 5][0], 0)
                self.assertEqual(frgb[fh - 5][fw - 5][1], 0)

    def test_black_level_and_10bit_lsb_precision(self):
        # Pixels differ ONLY in the 2 LSBs (256 vs 259): the le10 bit stream
        # must preserve them (a top-8-only decoder would flatten the pair).
        width, height = 8, 8
        rows = [[256 if x < 4 else 259 for x in range(width)] for _ in range(height)]
        with tempfile.TemporaryDirectory() as tmp:
            raw_path = os.path.join(tmp, 'lsb.raw')
            out_png = os.path.join(tmp, 'lsb.png')
            with open(raw_path, 'wb') as f:
                f.write(pack_le10(rows))
            rc, _ = run_raw2rgb([
                raw_path, str(width), str(height), out_png,
                '--black-level', '256', '--wb', 'none', '--gamma', '1.0',
            ])
            self.assertEqual(rc, 0)
            with open(out_png, 'rb') as f:
                pw, ph, rgb = parse_and_verify_png(f.read())
            self.assertEqual((pw, ph), (4, 4))
            self.assertEqual(rgb[1][0], (0, 0, 0))
            self.assertGreater(rgb[1][2][0], 0)
            self.assertGreater(rgb[1][2][1], 0)
            self.assertGreater(rgb[1][2][2], 0)

    def test_stride_and_non_multiple_of_4_width(self):
        # 10-px-wide frame exercises the generic (any width) le10 decoder.
        width, height = 10, 8
        bpl = (width * 10 + 7) // 8
        stride = bpl + 7
        frames = make_patch_frame(width, height, 'bggr', black_level=64)
        with tempfile.TemporaryDirectory() as tmp:
            raw_path = os.path.join(tmp, 'stride.raw')
            out_png = os.path.join(tmp, 'stride.png')
            with open(raw_path, 'wb') as f:
                f.write(pack_le10(frames, stride=stride))
            # --layout pinned: this synthetic frame is near-constant, and
            # content-based auto-detection cannot separate layouts on flat
            # frames by design (the margin comes from image structure).
            rc, _ = run_raw2rgb([
                raw_path, str(width), str(height), str(stride), out_png,
                '--layout', 'le10',
            ])
            self.assertEqual(rc, 0)
            with open(out_png, 'rb') as f:
                pw, ph, rgb = parse_and_verify_png(f.read())
            self.assertEqual((pw, ph), (5, 4))
            self.assertGreater(rgb[0][4][0], 200)
            self.assertEqual(rgb[0][4][2], 0)

    def test_grey_world_white_balance(self):
        # Neutral scene where Green is 2x brighter than R and B: gains ~2 on
        # R/B bring the output back to grey.
        width, height = 16, 16
        pat = BAYER_PATTERN['bggr']
        vals = {'R': 64 + 200, 'G': 64 + 400, 'B': 64 + 200}
        rows = [[vals[pat[y & 1][x & 1]] for x in range(width)] for y in range(height)]
        with tempfile.TemporaryDirectory() as tmp:
            raw_path = os.path.join(tmp, 'wb.raw')
            out_png = os.path.join(tmp, 'wb.png')
            with open(raw_path, 'wb') as f:
                f.write(pack_le10(rows))
            rc, _ = run_raw2rgb([raw_path, str(width), str(height), out_png, '--bayer', 'bggr'])
            self.assertEqual(rc, 0)
            with open(out_png, 'rb') as f:
                _, _, rgb = parse_and_verify_png(f.read())
            px = rgb[2][2]
            self.assertLess(abs(px[0] - px[1]), 2)
            self.assertLess(abs(px[1] - px[2]), 2)

    def test_wb_gains_clipped_on_dark_frame(self):
        # A near-black noisy frame: after BLC the channel means are a few DN
        # of noise; the gains must stay unit-ish (clipped) instead of
        # amplifying the noise into a coloured tint.
        width, height = 16, 16
        pat = BAYER_PATTERN['bggr']
        rows = []
        for y in range(height):
            row = []
            for x in range(width):
                ch = pat[y & 1][x & 1]
                row.append(64 + {'R': 1, 'G': 6, 'B': 2}[ch])
            rows.append(row)
        gains = raw2rgb.compute_wb_gains(1.0, 6.0, 2.0, 'grey')
        for g in gains:
            self.assertGreaterEqual(g, raw2rgb.WB_GAIN_MIN)
            self.assertLessEqual(g, raw2rgb.WB_GAIN_MAX)
        # and the extreme: one channel at exactly zero mean
        gains = raw2rgb.compute_wb_gains(0.0, 6.0, 2.0, 'grey')
        self.assertEqual(gains[0], 1.0)

    def test_auto_mode_reports_all_orders_and_writes_outputs(self):
        width, height = 16, 16
        pat = BAYER_PATTERN['bggr']
        rows = []
        for y in range(height):
            row = []
            for x in range(width):
                ch = pat[y & 1][x & 1]
                if ch == 'G':
                    row.append(64 + 300)
                elif ch == 'R':
                    row.append(64 + 500)
                else:
                    row.append(64 + 100)
            rows.append(row)
        with tempfile.TemporaryDirectory() as tmp:
            raw_path = os.path.join(tmp, 'auto.raw')
            out_png = os.path.join(tmp, 'auto.png')
            with open(raw_path, 'wb') as f:
                f.write(pack_le10(rows))
            rc, stdout = run_raw2rgb([raw_path, str(width), str(height), out_png, '--auto'])
            self.assertEqual(rc, 0)
            for order in ('bggr', 'gbrg', 'grbg', 'rggb'):
                self.assertIn(f'{order}:', stdout)
                variant = os.path.join(tmp, f'auto_{order}.png')
                self.assertTrue(os.path.exists(variant))
                with open(variant, 'rb') as f:
                    pw, ph, _ = parse_and_verify_png(f.read())
                    self.assertEqual((pw, ph), (width // 2, height // 2))
            self.assertTrue(os.path.exists(out_png))


class TestLayoutDetection(unittest.TestCase):
    """Auto-detection between le10, p12 and raw10 from size and content."""

    def _gradient_rows(self, width, height, seed=3, black=64):
        import random
        rnd = random.Random(seed)
        rows = []
        for y in range(height):
            row = []
            for x in range(width):
                base = black + (x * 400) // width + (y * 300) // height
                row.append(max(0, min(1023, base + rnd.randrange(6))))
            rows.append(row)
        return rows

    def test_detect_le10_vs_raw10_by_content(self):
        # Both layouts share w*10/8 bytes per line; the content test must
        # separate them on a smooth gradient.
        width, height = 64, 16
        rows = self._gradient_rows(width, height)
        with tempfile.TemporaryDirectory() as tmp:
            for packer, expect in ((pack_le10, 'le10'), (pack_raw10, 'raw10')):
                raw_path = os.path.join(tmp, f'{expect}.raw')
                with open(raw_path, 'wb') as f:
                    f.write(packer(rows))
                with open(raw_path, 'rb') as f:
                    data = f.read()
                layout, note = raw2rgb.detect_layout(data, width, height)
                self.assertEqual(layout, expect, f'{packer.__name__}: {note}')

    def test_detect_p12_by_size(self):
        # A full p12 frame is larger than any 10-bit frame of the same
        # geometry; the file size alone decides.
        width, height = 64, 16
        rows = self._gradient_rows(width, height)
        raw = pack_p12(rows)
        layout, _ = raw2rgb.detect_layout(raw, width, height)
        self.assertEqual(layout, 'p12')

    def test_detect_tie_keeps_le10(self):
        # An all-black frame decodes flat in every layout: the tie-break
        # keeps le10 (this board's default).
        width, height = 64, 16
        rows = [[64] * width for _ in range(height)]
        raw = pack_le10(rows)
        layout, note = raw2rgb.detect_layout(raw, width, height)
        self.assertEqual(layout, 'le10')

    def test_cli_autodetects_and_prints_layout(self):
        width, height = 64, 16
        rows = self._gradient_rows(width, height)
        with tempfile.TemporaryDirectory() as tmp:
            raw_path = os.path.join(tmp, 'le10.raw')
            out_png = os.path.join(tmp, 'out.png')
            with open(raw_path, 'wb') as f:
                f.write(pack_le10(rows))
            rc, stdout = run_raw2rgb([raw_path, str(width), str(height), out_png])
            self.assertEqual(rc, 0)
            self.assertIn('layout=le10', stdout)

    def test_deprecated_pack_flag_maps(self):
        width, height = 32, 24
        frames = make_patch_frame(width, height, 'bggr', black_level=64)
        with tempfile.TemporaryDirectory() as tmp:
            raw_path = os.path.join(tmp, 'p12.raw')
            out_png = os.path.join(tmp, 'p12.png')
            with open(raw_path, 'wb') as f:
                f.write(pack_p12(frames))
            rc, stdout = run_raw2rgb([raw_path, str(width), str(height), out_png, '--pack', '12'])
            self.assertEqual(rc, 0)
            self.assertIn('layout=p12', stdout)


class TestP12(unittest.TestCase):
    """The p12 reference layout still decodes (old begonia captures)."""

    def test_p12_quadrant_frame_half(self):
        width, height = 32, 24
        with tempfile.TemporaryDirectory() as tmp:
            for order in ('bggr', 'rggb'):
                raw_path = os.path.join(tmp, f'test12_{order}.raw')
                frames = make_patch_frame(width, height, order, black_level=64)
                with open(raw_path, 'wb') as f:
                    f.write(pack_p12(frames))
                half_png = os.path.join(tmp, f'half12_{order}.png')
                rc, _ = run_raw2rgb([
                    raw_path, str(width), str(height), half_png,
                    '--layout', 'p12', '--bayer', order,
                ])
                self.assertEqual(rc, 0)
                with open(half_png, 'rb') as f:
                    pw, ph, rgb = parse_and_verify_png(f.read())
                self.assertEqual((pw, ph), (width // 2, height // 2))
                w_px = rgb[2][2]
                r_px = rgb[2][pw - 3]
                g_px = rgb[ph - 3][2]
                b_px = rgb[ph - 3][pw - 3]
                self.assertGreater(w_px[0], 220)
                self.assertLess(abs(w_px[0] - w_px[1]), 3)
                self.assertLess(abs(w_px[1] - w_px[2]), 3)
                self.assertGreater(r_px[0], 220)
                self.assertEqual(r_px[1], 0)
                self.assertEqual(r_px[2], 0)
                self.assertGreater(g_px[1], 220)
                self.assertEqual(g_px[0], 0)
                self.assertEqual(g_px[2], 0)
                self.assertGreater(b_px[2], 220)
                self.assertEqual(b_px[0], 0)
                self.assertEqual(b_px[1], 0)

    def test_p12_stride_and_odd_width(self):
        width, height = 10, 8
        bpl = (width * 12 + 7) // 8
        stride = bpl + 5
        frames = make_patch_frame(width, height, 'bggr', black_level=64)
        with tempfile.TemporaryDirectory() as tmp:
            raw_path = os.path.join(tmp, 'stride12.raw')
            out_png = os.path.join(tmp, 'stride12.png')
            with open(raw_path, 'wb') as f:
                f.write(pack_p12(frames, stride=stride))
            rc, _ = run_raw2rgb([
                raw_path, str(width), str(height), str(stride), out_png, '--layout', 'p12',
            ])
            self.assertEqual(rc, 0)
            with open(out_png, 'rb') as f:
                pw, ph, rgb = parse_and_verify_png(f.read())
            self.assertEqual((pw, ph), (5, 4))
            self.assertGreater(rgb[0][4][0], 200)
            self.assertEqual(rgb[0][4][2], 0)


class TestSamples(unittest.TestCase):
    """Decode the two real captures from the tablet (le10 layout)."""

    def test_bars_sample_uniform_vertical_bars(self):
        """The colour-bars capture renders as vertical bands.

        The live pixels form a quincunx (the G phase of the CFA is dead, an
        OV8856 test-pattern + CAMSV capture quirk; see T9-RAWTOOLS.md), so
        the bars render as magenta / red / blue / black pairs, but each band
        is uniform across the whole frame.
        """
        if not os.path.exists(BARS_SAMPLE):
            self.skipTest('sample capture not present')
        with tempfile.TemporaryDirectory() as tmp:
            out_png = os.path.join(tmp, 'bars.png')
            rc, _ = run_raw2rgb([
                BARS_SAMPLE, '640', '480', out_png, '--bayer', 'bggr', '--wb', 'none',
            ])
            self.assertEqual(rc, 0)
            with open(out_png, 'rb') as f:
                pw, ph, rgb = parse_and_verify_png(f.read())
            self.assertEqual((pw, ph), (320, 240))

            # 4 output bands of 80 pixels (sensor bars are 160 px wide);
            # each band must be uniform in every colour plane.
            for band in range(4):
                x0, x1 = band * 80 + 6, (band + 1) * 80 - 6
                for plane in range(3):
                    vals = [rgb[y][x][plane] for y in range(0, ph, 4) for x in range(x0, x1, 3)]
                    mean = statistics.mean(vals)
                    var = statistics.pvariance(vals)
                    self.assertLess(
                        var, 4.0,
                        f'band {band} plane {plane} variance {var:.2f} (mean {mean:.1f})',
                    )

            # band colours: magenta, red, blue, black (quincunx of the
            # sensor's 8-bar pattern; the stated colours of this capture).
            mid = ph // 2
            b0 = rgb[mid][10]
            b1 = rgb[mid][90]
            b2 = rgb[mid][170]
            b3 = rgb[mid][250]
            self.assertGreater(b0[0], 200, 'band 0 red')
            self.assertGreater(b0[2], 200, 'band 0 blue')
            self.assertGreater(b1[0], 200, 'band 1 red')
            self.assertLess(b1[2], 60, 'band 1 blue off')
            self.assertLess(b2[0], 60, 'band 2 red off')
            self.assertGreater(b2[2], 200, 'band 2 blue')
            for plane in range(3):
                self.assertLess(b3[plane], 20, 'band 3 black')

    def test_scene_sample_plausible_statistics(self):
        """The real-scene capture decodes with plausible image statistics.

        Checks (from the decode path, 10-bit): median well below the 99.5th
        percentile (the scene is mostly desk/keyboard with a bright screen),
        no all-zero colour plane, and a visible top/bottom brightness split.
        """
        if not os.path.exists(SCENE_SAMPLE):
            self.skipTest('sample capture not present')
        with open(SCENE_SAMPLE, 'rb') as f:
            data = f.read()
        self.assertEqual(len(data), 800 * 480)
        phases, hw, hh = raw2rgb.unpack_le10_phases(data, 640, 480, 800)
        tbl = raw2rgb._phase_to_raw_tbl('le10')
        for i, plane in enumerate(phases):
            vals = sorted(tbl[v] for v in plane)
            n = len(vals)
            self.assertGreater(n, 0, f'phase {i} empty')
            med = statistics.median(vals)
            p995 = vals[min(n - 1, int(0.995 * n))]
            self.assertLess(
                med, p995 * 0.5,
                f'phase {i}: median {med} not well below p99.5 {p995}',
            )
            self.assertGreater(vals[-1], 0, f'phase {i} all zero')
            # a real exposure: values span well beyond black level + noise
            self.assertGreater(vals[-1], 512, f'phase {i} never rises above mid-scale')

        with tempfile.TemporaryDirectory() as tmp:
            out_png = os.path.join(tmp, 'scene.png')
            rc, _ = run_raw2rgb([SCENE_SAMPLE, '640', '480', out_png])
            self.assertEqual(rc, 0)
            with open(out_png, 'rb') as f:
                pw, ph, rgb = parse_and_verify_png(f.read())
            self.assertEqual((pw, ph), (320, 240))
            # bright screen above a dark keyboard: the top third is
            # measurably brighter than the bottom third
            top = [rgb[y][x][1] for y in range(0, ph // 3) for x in range(0, pw, 4)]
            bot = [rgb[y][x][1] for y in range(2 * ph // 3, ph) for x in range(0, pw, 4)]
            self.assertGreater(statistics.mean(top), statistics.mean(bot) * 1.5)
            # no colour plane collapsed to zero
            for plane in range(3):
                vals = [rgb[y][x][plane] for y in range(0, ph, 4) for x in range(0, pw, 4)]
                self.assertGreater(max(vals), 100, f'plane {plane} all dark')
                self.assertGreater(statistics.mean(vals), 5, f'plane {plane} mean ~ 0')


if __name__ == '__main__':
    unittest.main()
