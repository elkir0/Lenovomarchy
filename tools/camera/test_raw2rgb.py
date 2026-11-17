#!/usr/bin/env python3
"""Offline unit tests for tools/camera/raw2rgb.py (stdlib only)."""

import contextlib
import io
import os
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


def pack_raw10(rows: list[list[int]], stride: int | None = None) -> bytes:
    """Pack a 2D array of 10-bit pixels (0..1023) into MIPI/CAMSV RAW10 bytes."""
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
    with contextlib.redirect_stdout(buf):
        rc = raw2rgb.main(argv)
    return rc, buf.getvalue()


class TestRaw2Rgb(unittest.TestCase):
    def test_all_bayer_orders_half_and_full(self):
        width, height = 32, 24
        with tempfile.TemporaryDirectory() as tmp:
            for order in ('bggr', 'gbrg', 'grbg', 'rggb'):
                raw_path = os.path.join(tmp, f'test_{order}.raw')
                frames = make_patch_frame(width, height, order, black_level=64)
                with open(raw_path, 'wb') as f:
                    f.write(pack_raw10(frames))

                # Half-resolution (2x2 binning -> 16x12)
                half_png = os.path.join(tmp, f'half_{order}.png')
                rc, _ = run_raw2rgb([raw_path, str(width), str(height), half_png, '--bayer', order])
                self.assertEqual(rc, 0)
                with open(half_png, 'rb') as f:
                    pw, ph, rgb = parse_and_verify_png(f.read())
                self.assertEqual((pw, ph), (width // 2, height // 2))

                # Check interior of each quadrant
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

                # Full-resolution bilinear (32x24)
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
        # Pixels differ ONLY in the 2 LSBs (256 vs 259 -> MSB=64, LSB=0 vs 3)
        width, height = 8, 8
        rows = []
        for y in range(height):
            row = []
            for x in range(width):
                row.append(256 if x < 4 else 259)
            rows.append(row)

        with tempfile.TemporaryDirectory() as tmp:
            raw_path = os.path.join(tmp, 'lsb.raw')
            out_png = os.path.join(tmp, 'lsb.png')
            with open(raw_path, 'wb') as f:
                f.write(pack_raw10(rows))

            rc, _ = run_raw2rgb([
                raw_path, str(width), str(height), out_png,
                '--black-level', '256', '--wb', 'none', '--gamma', '1.0',
            ])
            self.assertEqual(rc, 0)
            with open(out_png, 'rb') as f:
                pw, ph, rgb = parse_and_verify_png(f.read())
            self.assertEqual((pw, ph), (4, 4))
            # Left half (256 - 256 = 0) -> 0; right half (259 - 256 = 3) -> > 0
            self.assertEqual(rgb[1][0], (0, 0, 0))
            self.assertGreater(rgb[1][2][0], 0)
            self.assertGreater(rgb[1][2][1], 0)
            self.assertGreater(rgb[1][2][2], 0)

    def test_stride_and_non_multiple_of_4_width(self):
        width, height = 10, 8
        bpl = (width * 10 + 7) // 8
        stride = bpl + 7
        frames = make_patch_frame(width, height, 'bggr', black_level=64)
        with tempfile.TemporaryDirectory() as tmp:
            raw_path = os.path.join(tmp, 'stride.raw')
            out_png = os.path.join(tmp, 'stride.png')
            with open(raw_path, 'wb') as f:
                f.write(pack_raw10(frames, stride=stride))
            # Positional [stride] <out.png> compatible with raw2png.py
            rc, _ = run_raw2rgb([raw_path, str(width), str(height), str(stride), out_png])
            self.assertEqual(rc, 0)
            with open(out_png, 'rb') as f:
                pw, ph, rgb = parse_and_verify_png(f.read())
            self.assertEqual((pw, ph), (5, 4))
            # Top-right is Red
            self.assertGreater(rgb[0][4][0], 200)
            self.assertEqual(rgb[0][4][2], 0)

    def test_grey_world_white_balance(self):
        # Create a neutral scene where Green is 2x brighter than R and B (typical sensor)
        width, height = 16, 16
        pat = BAYER_PATTERN['bggr']
        vals = {'R': 64 + 200, 'G': 64 + 400, 'B': 64 + 200}
        rows = [[vals[pat[y & 1][x & 1]] for x in range(width)] for y in range(height)]
        with tempfile.TemporaryDirectory() as tmp:
            raw_path = os.path.join(tmp, 'wb.raw')
            out_png = os.path.join(tmp, 'wb.png')
            with open(raw_path, 'wb') as f:
                f.write(pack_raw10(rows))
            rc, _ = run_raw2rgb([raw_path, str(width), str(height), out_png, '--bayer', 'bggr'])
            self.assertEqual(rc, 0)
            with open(out_png, 'rb') as f:
                _, _, rgb = parse_and_verify_png(f.read())
            px = rgb[2][2]
            self.assertLess(abs(px[0] - px[1]), 2)
            self.assertLess(abs(px[1] - px[2]), 2)

    def test_auto_mode_reports_all_orders_and_writes_outputs(self):
        width, height = 16, 16
        rows = []
        pat = BAYER_PATTERN['bggr']
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
                f.write(pack_raw10(rows))

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


if __name__ == '__main__':
    unittest.main()
