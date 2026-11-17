#!/usr/bin/env python3
"""Convert a MT6785 CAMSV IMGO raw frame dump to an 8-bit RGB PNG (stdlib only).

Two byte layouts are supported (--pack {10,12}):

- pack 10 (MIPI RAW10, ``CAMSV_PAK = 2``): 4 pixels in 5 bytes; bytes 0..3
  hold the upper 8 bits of pixels 0..3 and byte 4 holds their 2-bit LSBs
  (pixel 0 in [1:0], pixel 3 in [7:6]). Bytes per line = width * 10 // 8.
- pack 12 (what the hardware actually emits with ``CAMSV_PAK = 2`` +
  ``CAMSV_FMT_SEL = 0x101`` on MT6785): 2 pixels in 3 bytes as two
  little-endian 12-bit fields, each holding the 10-bit sample shifted left by
  2 (measured on YT-J706F: white bars read 0xffc = 1023 << 2). Bytes per line
  = width * 12 // 8. With a DMA line sized for RAW10 only 4/5 of the pixels
  fit; see docs/research/camera/T9-RAWTOOLS.md.

Both layouts are auto-detected from the file size when the geometry is
ambiguous. After unpacking, the tool subtracts the black level, applies
grey-world white balance and gamma, and demosaics (2x2 half-resolution by
default, or optional full-resolution bilinear).

Default Bayer order is 'bggr', matching the OV8856 datasheet native CFA order
and mainline ov8856.c default flip/mirror (0x3820/0x3821 with 0x3813=0x02).
"""

import argparse
from operator import add
import os
import struct
import sys
import zlib

# (r_phase, g1_phase, g2_phase, b_phase) indices into (p00, p01, p10, p11)
# where p00=(2r,2c), p01=(2r,2c+1), p10=(2r+1,2c), p11=(2r+1,2c+1).
BAYER_LAYOUTS = {
    'bggr': (3, 1, 2, 0),
    'gbrg': (2, 0, 3, 1),
    'grbg': (1, 0, 3, 2),
    'rggb': (0, 1, 2, 3),
}

# Tie-break preference when diagonal green symmetry is equal (OV8856 modes).
BAYER_PRIORITY = ('bggr', 'grbg', 'gbrg', 'rggb')

_LSB_LUT0 = bytes(b & 0x03 for b in range(256))
_LSB_LUT1 = bytes((b >> 2) & 0x03 for b in range(256))
_LSB_LUT2 = bytes((b >> 4) & 0x03 for b in range(256))
_LSB_LUT3 = bytes((b >> 6) & 0x03 for b in range(256))

# bytes-per-line helper for both supported layouts
def bpl_for(width: int, pack: int) -> int:
    """Bytes per line for a given pixel width and packing (10 or 12 bits/pixel)."""
    if pack == 10:
        return (width * 10 + 7) // 8
    if pack == 12:
        return (width * 12 + 7) // 8
    raise ValueError(f'unsupported packing {pack!r} (expected 10 or 12)')


def detect_pack(width: int, height: int, file_size: int, stride: int) -> int | None:
    """Guess the packing from the file size.

    Returns 10, 12, or None when the size is consistent with both layouts.
    Only called with the stride the caller resolved (default stride equals
    bpl for each candidate packing). Note that a truncated 12-bit capture
    whose stride was sized for RAW10 has exactly the RAW10 frame size, which
    the size alone cannot tell apart from a genuine RAW10 frame.
    """
    candidates = []
    for pack in (10, 12):
        bpl = bpl_for(width, pack)
        if file_size >= (height - 1) * stride + bpl:
            candidates.append(pack)
    if len(candidates) == 1:
        return candidates[0]
    return None


def detect_pack12_content(data: bytes, stride: int, lines: int = 4) -> bool:
    """Content test for the 12-bit packed layout.

    In that layout the 10-bit sample occupies bits [11:2] of each 12-bit
    field, so the middle byte of every 3-byte pixel pair takes only 16 values
    (one per low-nibble, high nibble fixed by the neighbouring samples); for
    a saturated pattern it collapses to very few. In a genuine RAW10 line
    that byte is the packed 2-bit LSBs of pixels 1 and 3 and spreads over all
    256 values for any natural image. Measure the number of distinct middle
    bytes on a handful of lines: <= 4 distinct values over >= 400 samples is
    the 12-bit layout.
    """
    vals: set[int] = set()
    checked = 0
    for y in range(min(lines, max(1, len(data) // stride))):
        line = data[y * stride : (y + 1) * stride]
        vals.update(line[1::3])
        checked += len(line) // 3
    # A natural 8-bit-spread byte would need far more distinct values; the
    # 12-bit layout bounds it by the 4-bit x 4-bit nibble pair, and real
    # frames use only a handful. 16 covers saturated and mid-level frames.
    return checked >= 24 and len(vals) <= 16


def _enc_to_10bit(enc: int) -> int:
    if sys.byteorder == 'little':
        return ((enc & 0xFF) << 2) | (enc >> 8)
    return ((enc >> 8) << 2) | (enc & 0xFF)


_ENC_TO_RAW10 = tuple(_enc_to_10bit(i) for i in range(1024))


def png_chunk(tag: bytes, payload: bytes) -> bytes:
    return (
        struct.pack('>I', len(payload))
        + tag
        + payload
        + struct.pack('>I', zlib.crc32(tag + payload) & 0xFFFFFFFF)
    )


def write_rgb_png(path: str, width: int, height: int, scanlines: bytes, compress_level: int = 6) -> None:
    ihdr = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)
    png = (
        b'\x89PNG\r\n\x1a\n'
        + png_chunk(b'IHDR', ihdr)
        + png_chunk(b'IDAT', zlib.compress(scanlines, compress_level))
        + png_chunk(b'IEND', b'')
    )
    with open(path, 'wb') as f:
        f.write(png)


def _unpack_line_generic(line: bytes, width: int) -> tuple[list[int], list[int]]:
    even = []
    odd = []
    n_full = min(width // 4, len(line) // 5)
    px = 0
    for g in range(n_full):
        base = g * 5
        b4 = line[base + 4]
        for k in range(4):
            val = (line[base + k] << 2) | ((b4 >> (2 * k)) & 0x03)
            enc = ((val & 0x03) << 8) | (val >> 2) if sys.byteorder == 'little' else ((val >> 2) << 8) | (val & 0x03)
            if (px & 1) == 0:
                even.append(enc)
            else:
                odd.append(enc)
            px += 1
    rem = width - px
    if rem > 0:
        base = n_full * 5
        b4_idx = base + 4 if len(line) >= base + 5 else base + rem
        b4 = line[b4_idx] if b4_idx < len(line) else 0
        for k in range(rem):
            msb = line[base + k] if base + k < len(line) else 0
            val = (msb << 2) | ((b4 >> (2 * k)) & 0x03)
            enc = ((val & 0x03) << 8) | (val >> 2) if sys.byteorder == 'little' else ((val >> 2) << 8) | (val & 0x03)
            if (px & 1) == 0:
                even.append(enc)
            else:
                odd.append(enc)
            px += 1
    while px < width:
        if (px & 1) == 0:
            even.append(0)
        else:
            odd.append(0)
        px += 1
    hw = width // 2
    return even[:hw], odd[:hw]


def _split_row_bytes_fast(row_bytes: bytes) -> tuple[memoryview, memoryview]:
    b0 = row_bytes[0::5]
    b1 = row_bytes[1::5]
    b2 = row_bytes[2::5]
    b3 = row_bytes[3::5]
    b4 = row_bytes[4::5]
    n = len(b0) * 4
    even_x = bytearray(n)
    even_x[0::4] = b0
    even_x[1::4] = b4.translate(_LSB_LUT0)
    even_x[2::4] = b2
    even_x[3::4] = b4.translate(_LSB_LUT2)
    odd_x = bytearray(n)
    odd_x[0::4] = b1
    odd_x[1::4] = b4.translate(_LSB_LUT1)
    odd_x[2::4] = b3
    odd_x[3::4] = b4.translate(_LSB_LUT3)
    return memoryview(even_x).cast('H'), memoryview(odd_x).cast('H')


_NIB0_LUT = bytes(b & 0x0F for b in range(256))
_NIB1_LUT = bytes(b >> 4 for b in range(256))


def _split_row12_bytes_fast(row12: bytes) -> tuple[memoryview, memoryview]:
    """Split concatenated 12-bit packed lines (even or odd sensor rows) into
    the two Bayer phases of those rows.

    Layout: 2 pixels per 3 bytes, two little-endian 12-bit fields each
    holding the 10-bit sample << 2. Bytes n3[0]=P0[7:0], n3[1]&0xf=P0[11:8],
    n3[1]>>4=P1[3:0], n3[2]=P1[11:4].
    The 16-bit LE word of each pair directly equals the 12-bit field value
    (v12 = raw10 << 2): the phases are returned in the _ENC_TO_RAW12 index
    space (raw = enc >> 2), matching the generic path, so both layouts share
    the LUT machinery.
    """
    n = len(row12) // 3
    b0 = row12[0 : n * 3 : 3]
    b1 = row12[1 : n * 3 : 3]
    b2 = row12[2 : n * 3 : 3]
    hi = b1.translate(_NIB0_LUT)
    lo = b1.translate(_NIB1_LUT)
    hi2 = b2.translate(_NIB1_LUT)  # b2 >> 4: top nibble of P1's high byte
    even_x = bytearray(n * 2)
    even_x[0::2] = b0
    even_x[1::2] = hi
    odd_x = bytearray(n * 2)
    odd_x[0::2] = lo
    odd_x[1::2] = hi2
    return memoryview(even_x).cast('H'), memoryview(odd_x).cast('H')


def _unpack_line12_generic(line: bytes, width: int, line_bpl: int) -> tuple[list[int], list[int]]:
    """Unpack one 12-bit packed sensor line of `line_bpl` packed bytes.

    When the DMA stride was too short for the full width, fewer than `width`
    pixels are available; the missing ones decode as 0.
    """
    even: list[int] = []
    odd: list[int] = []
    px = 0
    for base in range(0, (line_bpl // 3) * 3, 3):
        if px >= width:
            break
        even.append((line[base] | ((line[base + 1] & 0x0F) << 8)) & 0xFFF)
        px += 1
        if px >= width:
            break
        odd.append(((line[base + 1] >> 4) | (line[base + 2] << 4)) & 0xFFF)
        px += 1
    while px < width:
        if (px & 1) == 0:
            even.append(0)
        else:
            odd.append(0)
        px += 1
    hw = width // 2
    return even[:hw], odd[:hw]


def _pad_short_input(data: bytes, width: int, height: int, stride: int, pack: int) -> bytes:
    bpl = bpl_for(width, pack)
    needed = (height - 1) * stride + bpl
    if len(data) < needed:
        print(
            f'warning: input is {len(data)} bytes (< expected {needed} for '
            f'pack={pack} {width}x{height} stride={stride}), padding with 0',
            file=sys.stderr,
        )
        data = data + b'\x00' * (needed - len(data))
    return data


def unpack_raw12_phases(
    data: bytes, width: int, height: int, stride: int
) -> tuple[tuple[memoryview | list[int], ...], int, int]:
    """Unpack the 12-bit packed layout into the four 2x2 Bayer phase planes.

    Same return convention as unpack_raw10_phases. Each element is an encoded
    12-bit-field integer mapped via _ENC_TO_RAW12; the 10-bit sample is the
    top 10 bits (hardware stores sample << 2).
    """
    data = _pad_short_input(data, width, height, stride, 12)
    bpl12 = bpl_for(width, 12)
    line_bpl = min(stride, bpl12)
    hw = width // 2
    hh = height // 2
    used_h = hh * 2

    if line_bpl == bpl12 and (width & 1) == 0:
        even_raw = b''.join(data[y * stride : y * stride + bpl12] for y in range(0, used_h, 2))
        odd_raw = b''.join(data[y * stride : y * stride + bpl12] for y in range(1, used_h, 2))
        p00, p01 = _split_row12_bytes_fast(even_raw)
        p10, p11 = _split_row12_bytes_fast(odd_raw)
        return (p00, p01, p10, p11), hw, hh

    p00_l: list[int] = []
    p01_l: list[int] = []
    p10_l: list[int] = []
    p11_l: list[int] = []
    for r in range(hh):
        y0 = 2 * r
        y1 = y0 + 1
        e0, o0 = _unpack_line12_generic(data[y0 * stride : y0 * stride + stride], width, line_bpl)
        e1, o1 = _unpack_line12_generic(data[y1 * stride : y1 * stride + stride], width, line_bpl)
        p00_l.extend(e0)
        p01_l.extend(o0)
        p10_l.extend(e1)
        p11_l.extend(o1)
    return (p00_l, p01_l, p10_l, p11_l), hw, hh


_ENC_TO_RAW12 = tuple(i >> 2 for i in range(4096))


def unpack_raw10_phases(
    data: bytes, width: int, height: int, stride: int
) -> tuple[tuple[memoryview | list[int], ...], int, int]:
    """Unpack RAW10 into the four 2x2 Bayer phase planes (p00, p01, p10, p11).

    Each element is an encoded 10-bit integer mapped via _ENC_TO_RAW10.
    Returns ((p00, p01, p10, p11), hw, hh) where hw = width // 2, hh = height // 2.
    """
    bpl = (width * 10 + 7) // 8
    needed = (height - 1) * stride + bpl
    if len(data) < needed:
        print(
            f'warning: input is {len(data)} bytes (< expected {needed}), padding with 0',
            file=sys.stderr,
        )
        data = data + b'\x00' * (needed - len(data))
    # note: keep the padding above for the pack=10 layout; pack=12 uses
    # _pad_short_input() inside unpack_raw12_phases()

    hw = width // 2
    hh = height // 2
    used_h = hh * 2

    if (width & 3) == 0 and bpl == width * 10 // 8:
        even_raw = b''.join(data[y * stride : y * stride + bpl] for y in range(0, used_h, 2))
        odd_raw = b''.join(data[y * stride : y * stride + bpl] for y in range(1, used_h, 2))
        p00, p01 = _split_row_bytes_fast(even_raw)
        p10, p11 = _split_row_bytes_fast(odd_raw)
        return (p00, p01, p10, p11), hw, hh

    p00_l: list[int] = []
    p01_l: list[int] = []
    p10_l: list[int] = []
    p11_l: list[int] = []
    for r in range(hh):
        y0 = 2 * r
        y1 = y0 + 1
        e0, o0 = _unpack_line_generic(data[y0 * stride : y0 * stride + bpl], width)
        e1, o1 = _unpack_line_generic(data[y1 * stride : y1 * stride + bpl], width)
        p00_l.extend(e0)
        p01_l.extend(o0)
        p10_l.extend(e1)
        p11_l.extend(o1)
    return (p00_l, p01_l, p10_l, p11_l), hw, hh


def _phase_to_raw_tbl(pack: int) -> tuple[int, ...]:
    return _ENC_TO_RAW10 if pack == 10 else _ENC_TO_RAW12


def compute_phase_stats(
    phases: tuple[memoryview | list[int], ...], black_level: int, pack: int = 10
) -> list[dict[str, float]]:
    enc_tbl = _phase_to_raw_tbl(pack)
    blc_tbl = tuple(max(0, v - black_level) for v in enc_tbl)
    stats = []
    for plane in phases:
        n = len(plane)
        if n == 0:
            stats.append({'raw_mean': 0.0, 'blc_mean': 0.0, 'min': 0, 'max': 0})
            continue
        raw_sum = sum(map(enc_tbl.__getitem__, plane))
        blc_sum = sum(map(blc_tbl.__getitem__, plane))
        raw_min = min(map(enc_tbl.__getitem__, plane))
        raw_max = max(map(enc_tbl.__getitem__, plane))
        stats.append({
            'raw_mean': raw_sum / n,
            'blc_mean': blc_sum / n,
            'min': raw_min,
            'max': raw_max,
        })
    return stats


def _diagonal_diff(a: memoryview | list[int], b: memoryview | list[int], blc_tbl: tuple[int, ...]) -> float:
    n = len(a)
    if n == 0:
        return 0.0
    # Sample up to 65536 elements for fast green-pair correlation in --auto
    step = max(1, n // 65536)
    sa = a[::step]
    sb = b[::step]
    total = sum(abs(x - y) for x, y in zip(map(blc_tbl.__getitem__, sa), map(blc_tbl.__getitem__, sb)))
    return total / len(sa)


def compute_wb_gains(
    mean_r: float, mean_g: float, mean_b: float, mode: str
) -> tuple[float, float, float]:
    if mode == 'none':
        return 1.0, 1.0, 1.0
    if mean_g <= 0.0:
        return 1.0, 1.0, 1.0
    gr = min(16.0, max(0.1, mean_g / mean_r)) if mean_r > 0.0 else 1.0
    gb = min(16.0, max(0.1, mean_g / mean_b)) if mean_b > 0.0 else 1.0
    return gr, 1.0, gb


def analyze_bayer_orders(
    phases: tuple[memoryview | list[int], ...], black_level: int, wb_mode: str,
    pack: int = 10
) -> list[dict]:
    pstats = compute_phase_stats(phases, black_level, pack)
    blc_tbl = tuple(max(0, v - black_level) for v in _phase_to_raw_tbl(pack))
    # Green pairs are always either (p01, p10) or (p00, p11)
    diff_01_10 = _diagonal_diff(phases[1], phases[2], blc_tbl)
    diff_00_11 = _diagonal_diff(phases[0], phases[3], blc_tbl)

    results = []
    for order in BAYER_PRIORITY:
        ri, g1i, g2i, bi = BAYER_LAYOUTS[order]
        rs, g1s, g2s, bs = pstats[ri], pstats[g1i], pstats[g2i], pstats[bi]
        g_mean = 0.5 * (g1s['blc_mean'] + g2s['blc_mean'])
        gains = compute_wb_gains(rs['blc_mean'], g_mean, bs['blc_mean'], wb_mode)
        g_pair_diff = diff_01_10 if (g1i, g2i) == (1, 2) else diff_00_11
        g_mean_diff = abs(g1s['blc_mean'] - g2s['blc_mean'])
        results.append({
            'order': order,
            'r': rs,
            'g1': g1s,
            'g2': g2s,
            'b': bs,
            'g_mean': g_mean,
            'g_mean_diff': g_mean_diff,
            'g_pair_diff': g_pair_diff,
            'gains': gains,
        })

    results.sort(key=lambda d: (round(d['g_pair_diff'], 4), round(d['g_mean_diff'], 4), BAYER_PRIORITY.index(d['order'])))
    return results


def _build_lut(gain: float, scale: float, gamma: float, max_val: int, divisor: int = 1) -> bytes:
    inv_gamma = (1.0 / gamma) if gamma > 0.0 else 1.0
    out = bytearray(max_val + 1)
    factor = gain * scale / divisor
    for s in range(max_val + 1):
        v = s * factor
        if v <= 0.0:
            out[s] = 0
        elif v >= 1.0:
            out[s] = 255
        else:
            out[s] = min(255, int(round((v ** inv_gamma) * 255.0)))
    return bytes(out)


def demosaic_half(
    phases: tuple[memoryview | list[int], ...],
    hw: int,
    hh: int,
    order: str,
    black_level: int,
    gains: tuple[float, float, float],
    gamma: float,
    pack: int = 10,
) -> tuple[int, int, bytes]:
    ri, g1i, g2i, bi = BAYER_LAYOUTS[order]
    scale = 1.0 / max(1, 1023 - black_level)
    blc_tbl = tuple(max(0, v - black_level) for v in _phase_to_raw_tbl(pack))

    lut_r_sum1 = _build_lut(gains[0], scale, gamma, 1023, 1)
    lut_b_sum1 = _build_lut(gains[2], scale, gamma, 1023, 1)
    lut_r_enc = bytes(lut_r_sum1[blc_tbl[i]] for i in range(len(blc_tbl)))
    lut_b_enc = bytes(lut_b_sum1[blc_tbl[i]] for i in range(len(blc_tbl)))
    lut_g_sum2 = _build_lut(gains[1], scale, gamma, 2046, 2)

    r_bytes = bytes(map(lut_r_enc.__getitem__, phases[ri]))
    b_bytes = bytes(map(lut_b_enc.__getitem__, phases[bi]))
    g_bytes = bytes(
        map(
            lut_g_sum2.__getitem__,
            map(
                add,
                map(blc_tbl.__getitem__, phases[g1i]),
                map(blc_tbl.__getitem__, phases[g2i]),
            ),
        )
    )

    rgb = bytearray(hw * hh * 3)
    rgb[0::3] = r_bytes
    rgb[1::3] = g_bytes
    rgb[2::3] = b_bytes
    mv = memoryview(rgb)
    row_stride = hw * 3
    scanlines = b''.join(
        b'\x00' + mv[r * row_stride : (r + 1) * row_stride].tobytes()
        for r in range(hh)
    )
    return hw, hh, scanlines


def _h_prev_sum(grid: list[int], hw: int, hh: int) -> list[int]:
    s = list(map(add, [grid[0]] + grid[:-1], grid))
    for r in range(1, hh):
        idx = r * hw
        s[idx] = grid[idx] * 2
    return s


def _h_next_sum(grid: list[int], hw: int, hh: int) -> list[int]:
    s = list(map(add, grid, grid[1:] + [grid[-1]]))
    for r in range(hh - 1):
        idx = r * hw + hw - 1
        s[idx] = grid[idx] * 2
    return s


def _v_prev_sum(grid: list[int], hw: int) -> list[int]:
    return list(map(add, grid[:hw] + grid[:-hw], grid))


def _v_next_sum(grid: list[int], hw: int) -> list[int]:
    return list(map(add, grid, grid[hw:] + grid[-hw:]))


def _interp_grid_by_phase(
    grid: list[int],
    src_phase: int,
    dst_phase: int,
    hw: int,
    hh: int,
    lut1: bytes,
    lut2: bytes,
    lut4: bytes,
) -> bytes:
    if src_phase == dst_phase:
        return bytes(map(lut1.__getitem__, grid))
    src_y, src_x = (src_phase >> 1) & 1, src_phase & 1
    dst_y, dst_x = (dst_phase >> 1) & 1, dst_phase & 1
    same_y = src_y == dst_y
    same_x = src_x == dst_x

    if same_y and not same_x:
        # Horizontal neighbors: src_x=1 is left/right of dst_x=0 -> prev; src_x=0 -> next
        s = _h_prev_sum(grid, hw, hh) if dst_x == 0 else _h_next_sum(grid, hw, hh)
        return bytes(map(lut2.__getitem__, s))
    if same_x and not same_y:
        s = _v_prev_sum(grid, hw) if dst_y == 0 else _v_next_sum(grid, hw)
        return bytes(map(lut2.__getitem__, s))

    # Diagonal neighbors
    hs = _h_prev_sum(grid, hw, hh) if dst_x == 0 else _h_next_sum(grid, hw, hh)
    ds = _v_prev_sum(hs, hw) if dst_y == 0 else _v_next_sum(hs, hw)
    return bytes(map(lut4.__getitem__, ds))


def _interp_green_at_rb(
    g1: list[int],
    g1_phase: int,
    g2: list[int],
    g2_phase: int,
    dst_phase: int,
    hw: int,
    hh: int,
    lut4: bytes,
) -> bytes:
    dst_y, dst_x = (dst_phase >> 1) & 1, dst_phase & 1
    g1_y, _ = (g1_phase >> 1) & 1, g1_phase & 1
    # Pick whichever G shares row with dst for horizontal sum, other for vertical sum
    if g1_y == dst_y:
        gh, gv = g1, g2
    else:
        gh, gv = g2, g1
    hs = _h_prev_sum(gh, hw, hh) if dst_x == 0 else _h_next_sum(gh, hw, hh)
    vs = _v_prev_sum(gv, hw) if dst_y == 0 else _v_next_sum(gv, hw)
    return bytes(map(lut4.__getitem__, map(add, hs, vs)))


def demosaic_bilinear(
    phases: tuple[memoryview | list[int], ...],
    hw: int,
    hh: int,
    order: str,
    black_level: int,
    gains: tuple[float, float, float],
    gamma: float,
    pack: int = 10,
) -> tuple[int, int, bytes]:
    w = hw * 2
    h = hh * 2
    if hw == 0 or hh == 0:
        raise ValueError(f'image too small for Bayer demosaic: {w}x{h}')

    ri, g1i, g2i, bi = BAYER_LAYOUTS[order]
    scale = 1.0 / max(1, 1023 - black_level)
    blc_tbl = tuple(max(0, v - black_level) for v in _phase_to_raw_tbl(pack))

    r_grid = list(map(blc_tbl.__getitem__, phases[ri]))
    g1_grid = list(map(blc_tbl.__getitem__, phases[g1i]))
    g2_grid = list(map(blc_tbl.__getitem__, phases[g2i]))
    b_grid = list(map(blc_tbl.__getitem__, phases[bi]))

    luts_r = (
        _build_lut(gains[0], scale, gamma, 1023, 1),
        _build_lut(gains[0], scale, gamma, 2046, 2),
        _build_lut(gains[0], scale, gamma, 4092, 4),
    )
    lut_g1 = _build_lut(gains[1], scale, gamma, 1023, 1)
    lut_g4 = _build_lut(gains[1], scale, gamma, 4092, 4)
    luts_b = (
        _build_lut(gains[2], scale, gamma, 1023, 1),
        _build_lut(gains[2], scale, gamma, 2046, 2),
        _build_lut(gains[2], scale, gamma, 4092, 4),
    )

    even_rows = bytearray(hh * w * 3)
    odd_rows = bytearray(hh * w * 3)

    for phase, target_buf, x_off in ((0, even_rows, 0), (1, even_rows, 3), (2, odd_rows, 0), (3, odd_rows, 3)):
        r_ch = _interp_grid_by_phase(r_grid, ri, phase, hw, hh, *luts_r)
        b_ch = _interp_grid_by_phase(b_grid, bi, phase, hw, hh, *luts_b)
        if phase == g1i:
            g_ch = bytes(map(lut_g1.__getitem__, g1_grid))
        elif phase == g2i:
            g_ch = bytes(map(lut_g1.__getitem__, g2_grid))
        else:
            g_ch = _interp_green_at_rb(g1_grid, g1i, g2_grid, g2i, phase, hw, hh, lut_g4)
        target_buf[x_off + 0 :: 6] = r_ch
        target_buf[x_off + 1 :: 6] = g_ch
        target_buf[x_off + 2 :: 6] = b_ch

    mv_e = memoryview(even_rows)
    mv_o = memoryview(odd_rows)
    row_stride = w * 3
    lines = []
    for r in range(hh):
        s = r * row_stride
        lines.append(b'\x00' + mv_e[s : s + row_stride].tobytes())
        lines.append(b'\x00' + mv_o[s : s + row_stride].tobytes())
    return w, h, b''.join(lines)


def _auto_output_path(base_out: str, order: str) -> str:
    stem, ext = os.path.splitext(base_out)
    if not ext:
        ext = '.png'
    return f'{stem}_{order}{ext}'


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description='Convert CAMSV MIPI-packed RAW10 frame dump to RGB PNG (stdlib only).'
    )
    ap.add_argument('src', help='Input RAW10 dump file')
    ap.add_argument('width', type=lambda x: int(x, 0), help='Frame width in pixels')
    ap.add_argument('height', type=lambda x: int(x, 0), help='Frame height in lines')
    ap.add_argument(
        'rest',
        nargs='*',
        help='Optional [stride] <out.png> (compatible with raw2png.py)',
    )
    ap.add_argument('-o', '--out', dest='out_flag', help='Output PNG path')
    ap.add_argument('--stride', type=lambda x: int(x, 0), default=None, help='Line stride in bytes')
    ap.add_argument(
        '--pack',
        type=int,
        choices=(10, 12),
        default=None,
        help='Byte packing: 10 = MIPI RAW10 (4 px in 5 bytes), 12 = 12-bit LE '
             'fields, 2 px in 3 bytes, sample << 2 (what MT6785 CAMSV emits '
             'with PAK=2/FMT_SEL=0x101; default: auto-detect from file size, '
             'else 10)',
    )
    ap.add_argument(
        '--bayer',
        choices=tuple(BAYER_LAYOUTS.keys()),
        default='bggr',
        help='Bayer CFA order (default bggr, OV8856 datasheet/ov8856.c default)',
    )
    ap.add_argument(
        '--auto',
        action='store_true',
        help='Try all four Bayer orders, print channel statistics, and write all four if out is given',
    )
    ap.add_argument(
        '--black-level',
        type=int,
        default=64,
        help='Black level in 10-bit units (default 64 for OV8856)',
    )
    ap.add_argument(
        '--wb',
        choices=('grey', 'none'),
        default='grey',
        help='White balance mode (default grey = grey-world)',
    )
    ap.add_argument(
        '--gamma',
        type=float,
        default=2.2,
        help='Output gamma exponent (default 2.2; 1.0 = linear)',
    )
    ap.add_argument(
        '--full',
        action='store_true',
        help='Use full-resolution bilinear demosaic instead of 2x2 half-resolution binning',
    )
    ap.add_argument(
        '--compress',
        type=int,
        default=6,
        choices=range(0, 10),
        help='zlib compression level 0..9 (default 6)',
    )
    args = ap.parse_args(argv)

    bpl10 = (args.width * 10 + 7) // 8
    bpl12 = (args.width * 12 + 7) // 8
    out_path = args.out_flag
    stride = args.stride

    if len(args.rest) == 2:
        if stride is not None or out_path is not None:
            ap.error('cannot combine positional [stride] <out.png> with --stride/--out')
        stride = int(args.rest[0], 0)
        out_path = args.rest[1]
    elif len(args.rest) == 1:
        if out_path is None:
            out_path = args.rest[0]
        elif stride is None:
            stride = int(args.rest[0], 0)
        else:
            ap.error('unexpected extra positional argument')
    elif len(args.rest) > 2:
        ap.error('too many positional arguments (expected [stride] <out.png>)')

    pack = args.pack
    if pack is None:
        pack = 10
    # Explicit pack wins; otherwise try to infer from the file size (a file
    # that fits pack=12 but not pack=10 decides it; a file that fits neither
    # full frame is kept as pack=10 and decoded with zero padding).
    if args.pack is None:
        try:
            with open(args.src, 'rb') as f:
                f.seek(0, 2)
                size = f.tell()
        except OSError:
            size = -1
        det = detect_pack(args.width, args.height, size, stride if stride is not None else 0)
        if det is not None:
            pack = det
    bpl = bpl10 if pack == 10 else bpl12
    if stride is None:
        stride = bpl
    if args.width <= 1 or args.height <= 1 or stride < bpl10:
        ap.error(f'invalid geometry width={args.width} height={args.height} stride={stride} (min {bpl10} for pack=10)')
    if stride < bpl:
        print(
            f'warning: stride {stride} < {bpl} bytes per pack={pack} line; '
            f'each line holds only {args.width * stride // bpl} of {args.width} pixels',
            file=sys.stderr,
        )
    if out_path is None and not args.auto:
        ap.error('output PNG path required unless --auto is used')

    args.pack = pack
    args.stride = stride
    args.out = out_path
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    with open(args.src, 'rb') as f:
        data = f.read()

    # Auto-detect the packing when the caller did not pin it. The file size
    # cannot separate a genuine RAW10 frame from a 12-bit-container capture
    # whose stride was sized for RAW10 (both are stride*height bytes), so
    # decode both layouts and keep the one whose Bayer structure is saner:
    # the green phase pair of the correct layout has the smallest mean
    # absolute difference (diagonal symmetry of the CFA). This is decided
    # purely from the data, so it works for test patterns and real scenes
    # alike; ties (e.g. an all-black frame) keep pack=10.
    explicit_pack = '--pack' in (argv if argv is not None else sys.argv[1:])
    if args.pack == 10 and not explicit_pack and len(data) > 0:
        ph10, hw10, hh10 = unpack_raw10_phases(data, args.width, args.height, args.stride)
        ph12, hw12, hh12 = unpack_raw12_phases(data, args.width, args.height, args.stride)
        mad10 = min(item['g_pair_diff'] for item in analyze_bayer_orders(ph10, args.black_level, args.wb, 10))
        mad12 = min(item['g_pair_diff'] for item in analyze_bayer_orders(ph12, args.black_level, args.wb, 12))
        if mad12 < mad10 * 0.5:
            print(
                f'note: {args.src} decodes with better Bayer green symmetry '
                f'as pack=12 (diag_mad {mad12:.1f} vs {mad10:.1f} as pack=10); '
                f'treating as pack=12',
                file=sys.stderr,
            )
            args.pack = 12

    if args.pack == 12:
        bpl12 = bpl_for(args.width, 12)
        if args.stride < bpl12:
            # A 12-bit capture with a RAW10-sized stride cannot hold a full
            # line; only floor(stride * 2 / 3) pixels per line are usable.
            usable = (args.stride // 3) * 2
            print(
                f'warning: stride {args.stride} < {bpl12} bytes needed for a '
                f'pack=12 {args.width}-pixel line; only the first {usable} '
                f'pixels of each line hold sensor data, the rest decode as 0',
                file=sys.stderr,
            )
        phases, hw, hh = unpack_raw12_phases(data, args.width, args.height, args.stride)
    else:
        phases, hw, hh = unpack_raw10_phases(data, args.width, args.height, args.stride)
    analysis = analyze_bayer_orders(phases, args.black_level, args.wb, args.pack)
    if args.full:
        demosaic_fn = lambda *a: demosaic_bilinear(*a, pack=args.pack)  # noqa: E731
    else:
        demosaic_fn = lambda *a: demosaic_half(*a, pack=args.pack)  # noqa: E731

    if args.auto:
        print(f'Bayer order analysis ({args.width}x{args.height}, blc={args.black_level}, wb={args.wb}):')
        for item in analysis:
            gr, gg, gb = item['gains']
            print(
                f"  {item['order']}: R={item['r']['blc_mean']:.2f} "
                f"G1={item['g1']['blc_mean']:.2f} G2={item['g2']['blc_mean']:.2f} "
                f"B={item['b']['blc_mean']:.2f} |G1-G2|={item['g_mean_diff']:.2f} "
                f"diag_mad={item['g_pair_diff']:.2f} gains=({gr:.3f},{gg:.3f},{gb:.3f})"
            )
        best = analysis[0]
        print(f"best green-channel symmetry: {best['order']}")
        if args.out:
            for item in analysis:
                order = item['order']
                dst = _auto_output_path(args.out, order)
                ow, oh, scanlines = demosaic_fn(
                    phases, hw, hh, order, args.black_level, item['gains'], args.gamma
                )
                write_rgb_png(dst, ow, oh, scanlines, args.compress)
                print(f'ok {dst} {ow}x{oh} bayer={order}')
            ow, oh, scanlines = demosaic_fn(
                phases, hw, hh, best['order'], args.black_level, best['gains'], args.gamma
            )
            write_rgb_png(args.out, ow, oh, scanlines, args.compress)
            print(f"ok {args.out} {ow}x{oh} bayer={best['order']} (selected)")
        return 0

    chosen = next(item for item in analysis if item['order'] == args.bayer)
    ow, oh, scanlines = demosaic_fn(
        phases, hw, hh, args.bayer, args.black_level, chosen['gains'], args.gamma
    )
    write_rgb_png(args.out, ow, oh, scanlines, args.compress)
    gr, gg, gb = chosen['gains']
    print(
        f'ok {args.out} {ow}x{oh} bayer={args.bayer} '
        f'blc={args.black_level} wb=({gr:.3f},{gg:.3f},{gb:.3f}) '
        f'gamma={args.gamma} pack={args.pack}'
    )
    return 0


if __name__ == '__main__':
    sys.exit(main())
