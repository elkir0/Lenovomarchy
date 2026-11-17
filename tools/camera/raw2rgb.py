#!/usr/bin/env python3
"""Convert a MT6785 CAMSV IMGO raw frame dump to an 8-bit RGB PNG (stdlib only).

Three byte layouts are supported (--layout {le10,p12,raw10}):

- le10 (default; measured on YT-J706F with CAMSV FMT_SEL = 0x102 / PAK = 1
  and the line sized for 10 bits, see docs/hardware/CAMERA.md): each line is
  one continuous little-endian 10-bit bit stream; pixel k occupies bits
  10k..10k+9 of the line read as a little-endian integer. Bytes per line =
  width * 10 / 8. This is NOT the MIPI RAW10 byte layout: the two share only
  their size.
- p12 (old begonia values, FMT_SEL = 0x101 / PAK = 2, kept for reference):
  two pixels per three bytes as two little-endian 12-bit fields, each holding
  the 10-bit sample shifted left by two (0xffc = 1023 << 2). Bytes per line =
  width * 12 / 8. Truncation: with a line sized for 10 bits instead, the DMA
  writes only 2/3 of the pixels per line (533 of 640; see
  docs/research/camera/T9-RAWTOOLS.md).
- raw10 (MIPI CSI-2 RAW10): 4 pixels in 5 bytes; bytes 0..3 hold the upper
  8 bits of pixels 0..3 and byte 4 holds their 2-bit LSBs (pixel 0 in [1:0],
  pixel 3 in [7:6]). Bytes per line = width * 10 / 8.
- u16 (layout-sweep candidate): one little-endian 16-bit container per
  pixel, 10-bit sample in the LOW bits (word & 0x3ff). Bytes per line =
  width * 2. This is what a CAMSV FMT_SEL/PAK combination is hoped to
  produce (libcamera's software ISP reads exactly this as SBGGR10); see
  tools/camera/layout-sweep.sh and docs/research/camera/T13-LIBCAMERA.md.
- u16h: same container, 10-bit sample in the HIGH bits (word >> 6, i.e.
  MSB-justified). The option for the case the hardware left-justifies.

The layout is auto-detected from the file size and the decoded content when
--layout is not given (ties and flat frames keep le10). After unpacking, the
tool subtracts the black level, applies grey-world white balance (gains
clipped to a sane range so noise in dark frames cannot tint the image) and
gamma, and demosaics (2x2 half-resolution by default, or optional
full-resolution bilinear with --full).

Default Bayer order is 'bggr', matching the OV8856 datasheet native CFA order
and mainline ov8856.c default flip/mirror (0x3820/0x3821 with 0x3813=0x02).
"""

import argparse
from operator import add
import os
import struct
import sys
import zlib

# Layout names in tie-break preference order (le10 is this board's default).
LAYOUTS = ('le10', 'p12', 'raw10', 'u16', 'u16h')

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

_NIB0_LUT = bytes(b & 0x0F for b in range(256))
_NIB1_LUT = bytes(b >> 4 for b in range(256))

_LUT_AND3 = bytes(b & 0x03 for b in range(256))
_LUT_SHR2_3 = bytes((b >> 2) & 0x03 for b in range(256))
_LUT_SHR4_3 = bytes((b >> 4) & 0x03 for b in range(256))
_LUT_SHR6_3 = bytes((b >> 6) & 0x03 for b in range(256))

# 16-bit little-endian word LUTs for the le10 fast splitter. A 5-byte group
# (b0..b4, little-endian) holds pixels p0..p3 at bit offsets 0/10/20/30, so:
#   p0 = b0 | ((b1 & 3) << 8)
#   p1 = (b1 >> 2) | ((b2 & 0xF) << 6)
#   p2 = (b2 >> 4) | ((b3 & 0x3F) << 4)
#   p3 = (b3 >> 6) | (b4 << 2)
# The phase planes store enc = (p >> 2) | ((p & 3) << 8) as native 16-bit
# words; their low bytes need bits from two adjacent group bytes:
#   enc0 lo (from b0|b1<<8) = (b0 >> 2) | ((b1 & 3) << 6)
#   enc1 lo (from b1|b2<<8) = (b1 >> 4) | ((b2 & 0xF) << 4)
#   enc2 lo (from b2|b3<<8) = (b2 >> 6) | ((b3 & 0x3F) << 2)
#   enc3 lo = b4 ; the high bytes are 2-bit slices of single bytes.
_LUT_W01_P0LO = bytes(
    (((c & 0xFF) >> 2) | (((c >> 8) & 0x03) << 6)) & 0xFF for c in range(65536)
)
_LUT_W12_P1LO = bytes(
    (((c & 0xFF) >> 4) | (((c >> 8) & 0x0F) << 4)) & 0xFF for c in range(65536)
)
_LUT_W23_P2LO = bytes(
    (((c & 0xFF) >> 6) | (((c >> 8) & 0x3F) << 2)) & 0xFF for c in range(65536)
)


def bpl_for(width: int, layout: str) -> int:
    """Bytes per line for a given pixel width and byte layout."""
    if layout == 'le10' or layout == 'raw10':
        return (width * 10 + 7) // 8
    if layout == 'p12':
        return (width * 12 + 7) // 8
    if layout in ('u16', 'u16h'):
        return width * 2
    raise ValueError(f'unsupported layout {layout!r} (expected one of {LAYOUTS})')


def _enc_to_10bit(enc: int) -> int:
    if sys.byteorder == 'little':
        return ((enc & 0xFF) << 2) | (enc >> 8)
    return ((enc >> 8) << 2) | (enc & 0xFF)


_ENC_TO_RAW10 = tuple(_enc_to_10bit(i) for i in range(1024))
_ENC_TO_RAW12 = tuple(i >> 2 for i in range(4096))
# u16 container, 16-bit code space: sample in the low 10 bits (u16) or the
# high 10 bits, i.e. >> 6 (u16h; the remaining bits are zero/undefined).
_ENC_TO_RAW_U16 = tuple(i & 0x3FF for i in range(65536))
_ENC_TO_RAW_U16H = tuple(i >> 6 for i in range(65536))

# enc-space -> 10-bit sample table per layout (le10 and raw10 share the same
# (msb8 | lsb2 << 8) encoding; p12 stores the raw 12-bit field, sample << 2;
# u16/u16h store the container word itself).
_ENC_TO_RAW_TABLE = {
    'le10': _ENC_TO_RAW10,
    'raw10': _ENC_TO_RAW10,
    'p12': _ENC_TO_RAW12,
    'u16': _ENC_TO_RAW_U16,
    'u16h': _ENC_TO_RAW_U16H,
}


def _phase_to_raw_tbl(layout: str) -> tuple[int, ...]:
    try:
        return _ENC_TO_RAW_TABLE[layout]
    except KeyError:
        raise ValueError(f'unsupported layout {layout!r}') from None


# ---------------------------------------------------------------------------
# Generic (any width) per-line decoders. Each returns `width` enc values; a
# le10/raw10 enc word is (p >> 2) | ((p & 3) << 8), a p12 enc word is the
# 12-bit field itself (p << 2). Missing pixels decode as 0.

def _le10_line_enc(line: bytes, width: int) -> list[int]:
    """Continuous little-endian 10-bit bit stream (pixel k at bits 10k..10k+9)."""
    v = int.from_bytes(line, 'little')
    enc = []
    for x in range(width):
        p = (v >> (10 * x)) & 0x3FF
        enc.append((p >> 2) | ((p & 0x03) << 8))
    return enc


def _raw10_line_enc(line: bytes, width: int) -> list[int]:
    """MIPI RAW10: 4 pixels per 5 bytes (4 MSB bytes + 1 packed LSB byte)."""
    enc = []
    px = 0
    n_full = min(width // 4, len(line) // 5)
    for g in range(n_full):
        base = 5 * g
        b4 = line[base + 4]
        for k in range(4):
            val = (line[base + k] << 2) | ((b4 >> (2 * k)) & 0x03)
            enc.append(((val & 0x03) << 8) | (val >> 2))
            px += 1
    rem = width - px
    if rem > 0:
        base = n_full * 5
        b4 = line[base + 4] if len(line) > base + 4 else 0
        for k in range(rem):
            msb = line[base + k] if len(line) > base + k else 0
            val = (msb << 2) | ((b4 >> (2 * k)) & 0x03)
            enc.append(((val & 0x03) << 8) | (val >> 2))
    return enc


def _p12_line_enc(line: bytes, width: int) -> list[int]:
    """12-bit containers: 2 pixels per 3 bytes, LE 12-bit fields, sample << 2."""
    enc = []
    for base in range(0, (len(line) // 3) * 3, 3):
        if len(enc) >= width:
            break
        enc.append((line[base] | ((line[base + 1] & 0x0F) << 8)) & 0xFFF)
        if len(enc) >= width:
            break
        enc.append(((line[base + 1] >> 4) | (line[base + 2] << 4)) & 0xFFF)
    while len(enc) < width:
        enc.append(0)
    return enc


def _u16_line_enc(line: bytes, width: int) -> list[int]:
    """16-bit LE containers, 10-bit sample in the low bits (enc = container)."""
    return [int.from_bytes(line[2 * x:2 * x + 2], 'little')
            for x in range(min(width, len(line) // 2))] + [0] * max(0, width - len(line) // 2)


def _u16h_line_enc(line: bytes, width: int) -> list[int]:
    """16-bit LE containers, 10-bit sample in the high bits (enc = container)."""
    return _u16_line_enc(line, width)


GENERIC_LINE_DECODERS = {
    'le10': _le10_line_enc,
    'raw10': _raw10_line_enc,
    'p12': _p12_line_enc,
    'u16': _u16_line_enc,
    'u16h': _u16h_line_enc,
}


# ---------------------------------------------------------------------------
# Fast (multiple-of-group width) splitters into the two Bayer phases of a
# concatenated run of same-parity rows.

def _split_le10_rows_fast(rows: bytes) -> tuple[memoryview, memoryview]:
    """Split concatenated le10 rows into (even-x, odd-x) enc word planes.

    Assumes len(rows) is a multiple of 5 (width % 4 == 0). Returns native
    16-bit arrays where each word is enc = (p >> 2) | ((p & 3) << 8).
    """
    n = len(rows) // 5
    b0 = rows[0::5]
    b1 = rows[1::5]
    b2 = rows[2::5]
    b3 = rows[3::5]
    b4 = rows[4::5]
    ib01 = bytearray(2 * n)
    ib01[0::2] = b0
    ib01[1::2] = b1
    p0_lo = bytes(map(_LUT_W01_P0LO.__getitem__, memoryview(ib01).cast('H')))
    ib12 = bytearray(2 * n)
    ib12[0::2] = b1
    ib12[1::2] = b2
    p1_lo = bytes(map(_LUT_W12_P1LO.__getitem__, memoryview(ib12).cast('H')))
    ib23 = bytearray(2 * n)
    ib23[0::2] = b2
    ib23[1::2] = b3
    p2_lo = bytes(map(_LUT_W23_P2LO.__getitem__, memoryview(ib23).cast('H')))
    even = bytearray(4 * n)  # words (enc p0, enc p2)
    even[0::4] = p0_lo
    even[1::4] = b0.translate(_LUT_AND3)
    even[2::4] = p2_lo
    even[3::4] = b2.translate(_LUT_SHR4_3)
    odd = bytearray(4 * n)  # words (enc p1, enc p3)
    odd[0::4] = p1_lo
    odd[1::4] = b1.translate(_LUT_SHR2_3)
    odd[2::4] = b4
    odd[3::4] = b3.translate(_LUT_SHR6_3)
    return memoryview(even).cast('H'), memoryview(odd).cast('H')


def _split_row_bytes_fast(row_bytes: bytes) -> tuple[memoryview, memoryview]:
    """Split concatenated MIPI RAW10 rows into (even-x, odd-x) enc planes."""
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


def _split_row12_bytes_fast(row12: bytes) -> tuple[memoryview, memoryview]:
    """Split concatenated p12 rows into (even-x, odd-x) enc planes.

    Layout: 2 pixels per 3 bytes, two little-endian 12-bit fields each
    holding the 10-bit sample << 2. Bytes n3[0]=P0[7:0], n3[1]&0xf=P0[11:8],
    n3[1]>>4=P1[3:0], n3[2]=P1[11:4]. The 16-bit LE word of each pair
    directly equals the 12-bit field value (v12 = raw10 << 2), so the phases
    are returned in the _ENC_TO_RAW12 index space (raw = enc >> 2).
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


# ---------------------------------------------------------------------------
# Phase-plane unpacking per layout.

def _pad_short_input(data: bytes, width: int, height: int, stride: int, layout: str) -> bytes:
    bpl = bpl_for(width, layout)
    needed = (height - 1) * stride + bpl
    if len(data) < needed:
        print(
            f'warning: input is {len(data)} bytes (< expected {needed} for '
            f'layout={layout} {width}x{height} stride={stride}), padding with 0',
            file=sys.stderr,
        )
        data = data + b'\x00' * (needed - len(data))
    return data


def _unpack_generic_phases(data: bytes, width: int, height: int, stride: int, layout: str):
    """Any-width fallback: decode every line with the generic per-line decoder."""
    bpl = bpl_for(width, layout)
    decode = GENERIC_LINE_DECODERS[layout]
    hw = width // 2
    hh = height // 2
    used_h = hh * 2
    p00: list[int] = []
    p01: list[int] = []
    p10: list[int] = []
    p11: list[int] = []
    for r in range(hh):
        y0 = 2 * r
        y1 = y0 + 1
        e0 = decode(data[y0 * stride : y0 * stride + bpl], width)
        e1 = decode(data[y1 * stride : y1 * stride + bpl], width)
        p00.extend(e0[0::2])
        p01.extend(e0[1::2])
        p10.extend(e1[0::2])
        p11.extend(e1[1::2])
    return (p00, p01, p10, p11), hw, hh


def unpack_le10_phases(
    data: bytes, width: int, height: int, stride: int
) -> tuple[tuple[memoryview | list[int], ...], int, int]:
    """Unpack the le10 layout into the four 2x2 Bayer phase planes.

    Each element is an encoded 10-bit integer mapped via _ENC_TO_RAW10.
    Returns ((p00, p01, p10, p11), hw, hh) with hw = width // 2, hh = height // 2.
    """
    data = _pad_short_input(data, width, height, stride, 'le10')
    bpl = bpl_for(width, 'le10')
    hw = width // 2
    hh = height // 2
    used_h = hh * 2
    if (width & 3) == 0:
        even_rows = b''.join(data[y * stride : y * stride + bpl] for y in range(0, used_h, 2))
        odd_rows = b''.join(data[y * stride : y * stride + bpl] for y in range(1, used_h, 2))
        p00, p01 = _split_le10_rows_fast(even_rows)
        p10, p11 = _split_le10_rows_fast(odd_rows)
        return (p00, p01, p10, p11), hw, hh
    return _unpack_generic_phases(data, width, height, stride, 'le10')


def unpack_raw10_phases(
    data: bytes, width: int, height: int, stride: int
) -> tuple[tuple[memoryview | list[int], ...], int, int]:
    """Unpack MIPI RAW10 into the four 2x2 Bayer phase planes (p00, p01, p10, p11)."""
    data = _pad_short_input(data, width, height, stride, 'raw10')
    bpl = bpl_for(width, 'raw10')
    hw = width // 2
    hh = height // 2
    used_h = hh * 2
    if (width & 3) == 0:
        even_rows = b''.join(data[y * stride : y * stride + bpl] for y in range(0, used_h, 2))
        odd_rows = b''.join(data[y * stride : y * stride + bpl] for y in range(1, used_h, 2))
        p00, p01 = _split_row_bytes_fast(even_rows)
        p10, p11 = _split_row_bytes_fast(odd_rows)
        return (p00, p01, p10, p11), hw, hh
    return _unpack_generic_phases(data, width, height, stride, 'raw10')


def unpack_p12_phases(
    data: bytes, width: int, height: int, stride: int
) -> tuple[tuple[memoryview | list[int], ...], int, int]:
    """Unpack the p12 (12-bit container) layout into the four Bayer phase planes.

    Same return convention as unpack_le10_phases. Each element is a 12-bit
    field value mapped via _ENC_TO_RAW12; the 10-bit sample is the top 10 bits
    (hardware stores sample << 2). When the stride is too short for the full
    width, only the first stride // 3 * 2 pixels of each line hold data.
    """
    data = _pad_short_input(data, width, height, stride, 'p12')
    bpl12 = bpl_for(width, 'p12')
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

    decode = _p12_line_enc
    p00_l: list[int] = []
    p01_l: list[int] = []
    p10_l: list[int] = []
    p11_l: list[int] = []
    for r in range(hh):
        y0 = 2 * r
        y1 = y0 + 1
        e0 = decode(data[y0 * stride : y0 * stride + line_bpl], width)
        e1 = decode(data[y1 * stride : y1 * stride + line_bpl], width)
        p00_l.extend(e0[0::2])
        p01_l.extend(e0[1::2])
        p10_l.extend(e1[0::2])
        p11_l.extend(e1[1::2])
    return (p00_l, p01_l, p10_l, p11_l), hw, hh


def unpack_u16_phases(
    data: bytes, width: int, height: int, stride: int
) -> tuple[tuple[memoryview | list[int], ...], int, int]:
    """Unpack the u16/u16h layout (16-bit LE container per pixel) into the
    four 2x2 Bayer phase planes.

    The container word is the enc value itself; _ENC_TO_RAW_U16/_U16H map it
    to the 10-bit sample.  Line reordering is the same as the le10 fast path.
    """
    layout = 'u16'  # the byte geometry is identical for u16h
    data = _pad_short_input(data, width, height, stride, layout)
    bpl = bpl_for(width, layout)
    hw = width // 2
    hh = height // 2
    used_h = hh * 2
    even_rows = b''.join(data[y * stride : y * stride + bpl] for y in range(0, used_h, 2))
    odd_rows = b''.join(data[y * stride : y * stride + bpl] for y in range(1, used_h, 2))
    even = memoryview(even_rows).cast('H')
    odd = memoryview(odd_rows).cast('H')
    return (even[0::2], even[1::2], odd[0::2], odd[1::2]), hw, hh


PHASE_UNPACKERS = {
    'le10': unpack_le10_phases,
    'raw10': unpack_raw10_phases,
    'p12': unpack_p12_phases,
    'u16': unpack_u16_phases,
    'u16h': unpack_u16_phases,
}


def unpack_phases(data: bytes, width: int, height: int, stride: int, layout: str):
    try:
        fn = PHASE_UNPACKERS[layout]
    except KeyError:
        raise ValueError(f'unsupported layout {layout!r}') from None
    return fn(data, width, height, stride)


# ---------------------------------------------------------------------------
# Layout auto-detection.

def _content_score(data: bytes, width: int, stride: int | None, layout: str, max_pairs: int = 10) -> float:
    """Content plausibility score for one layout (lower = more plausible).

    Decodes the first rows into the four Bayer phase planes and sums the mean
    absolute difference of the diagonal green pairs (minimum of the two
    pairings, so the score is Bayer-order agnostic) and the mean horizontal
    gradient inside each phase plane. A wrong layout shuffles pixel bits and
    both measures explode to sample-range levels; the correct layout keeps
    them at image-noise level.
    """
    bpl = bpl_for(width, layout)
    s = stride if stride is not None else bpl
    decode = GENERIC_LINE_DECODERS[layout]
    tbl = _ENC_TO_RAW_TABLE[layout]
    planes: tuple[list[int], ...] = ([], [], [], [])
    pairs = 0
    for y in range(0, 2 * max_pairs, 2):
        base = y * s
        if base + 2 * s > len(data):
            break
        for dy in (0, 1):
            line = data[base + dy * s : base + dy * s + min(s, bpl)]
            vals = [tbl[e] for e in decode(line, width)]
            row_plane = planes[((y + dy) & 1) << 1]
            col_plane_odd = planes[(((y + dy) & 1) << 1) | 1]
            row_plane.extend(vals[0::2])
            col_plane_odd.extend(vals[1::2])
        pairs += 1
    if pairs == 0:
        return float('inf')

    def _mad(a: list[int], b: list[int]) -> float:
        n = min(len(a), len(b))
        if n == 0:
            return 0.0
        return sum(abs(a[i] - b[i]) for i in range(n)) / n

    gmad = min(_mad(planes[1], planes[2]), _mad(planes[0], planes[3]))
    tot = 0
    cnt = 0
    for pl in planes:
        for i in range(len(pl) - 1):
            tot += abs(pl[i + 1] - pl[i])
            cnt += 1
    return gmad + tot / max(1, cnt)


def detect_layout(data: bytes, width: int, height: int, stride: int | None = None) -> tuple[str, str]:
    """Pick the byte layout from the file size, then from the decoded content.

    Returns (layout, human note). Ties (e.g. an all-black frame, where every
    layout decodes flat) keep le10, the layout measured on this board.
    """
    candidates = []
    for layout in LAYOUTS:
        bpl = bpl_for(width, layout)
        s = stride if stride is not None else bpl
        if len(data) >= (height - 1) * s + bpl:
            candidates.append(layout)
    if not candidates:
        return LAYOUTS[0], (
            f'input of {len(data)} bytes fits no complete {width}x{height} '
            f'frame in any layout; defaulting to {LAYOUTS[0]}'
        )
    if len(candidates) == 1:
        return candidates[0], f'file size fits only the {candidates[0]} layout'
    scores = {c: _content_score(data, width, stride, c) for c in candidates}
    best = min(candidates, key=lambda c: (scores[c], LAYOUTS.index(c)))
    detail = ', '.join(f'{c}={scores[c]:.1f}' for c in candidates)
    return best, f'layout auto-detected as {best} (content scores: {detail})'


# ---------------------------------------------------------------------------
# Statistics, white balance, demosaic.

def compute_phase_stats(
    phases: tuple[memoryview | list[int], ...], black_level: int, layout: str = 'le10'
) -> list[dict[str, float]]:
    enc_tbl = _phase_to_raw_tbl(layout)
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


# Grey-world gains are clipped to this range so that noise in dark frames
# (blc means of a few DN) cannot produce extreme tints; real illuminant
# correction on this sensor stays well inside it.
WB_GAIN_MIN = 0.2
WB_GAIN_MAX = 5.0


def compute_wb_gains(
    mean_r: float, mean_g: float, mean_b: float, mode: str
) -> tuple[float, float, float]:
    if mode == 'none':
        return 1.0, 1.0, 1.0
    if mean_g <= 1.0:
        # Essentially black after black-level correction: unit gains, so
        # noise around the pedestal cannot tint the frame.
        return 1.0, 1.0, 1.0
    gr = min(WB_GAIN_MAX, max(WB_GAIN_MIN, mean_g / mean_r)) if mean_r > 0.0 else 1.0
    gb = min(WB_GAIN_MAX, max(WB_GAIN_MIN, mean_g / mean_b)) if mean_b > 0.0 else 1.0
    return gr, 1.0, gb


def analyze_bayer_orders(
    phases: tuple[memoryview | list[int], ...], black_level: int, wb_mode: str,
    layout: str = 'le10'
) -> list[dict]:
    pstats = compute_phase_stats(phases, black_level, layout)
    blc_tbl = tuple(max(0, v - black_level) for v in _phase_to_raw_tbl(layout))
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
    layout: str = 'le10',
) -> tuple[int, int, bytes]:
    ri, g1i, g2i, bi = BAYER_LAYOUTS[order]
    scale = 1.0 / max(1, 1023 - black_level)
    blc_tbl = tuple(max(0, v - black_level) for v in _phase_to_raw_tbl(layout))

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
    layout: str = 'le10',
) -> tuple[int, int, bytes]:
    w = hw * 2
    h = hh * 2
    if hw == 0 or hh == 0:
        raise ValueError(f'image too small for Bayer demosaic: {w}x{h}')

    ri, g1i, g2i, bi = BAYER_LAYOUTS[order]
    scale = 1.0 / max(1, 1023 - black_level)
    blc_tbl = tuple(max(0, v - black_level) for v in _phase_to_raw_tbl(layout))

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


# ---------------------------------------------------------------------------
# PNG output.

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


def _auto_output_path(base_out: str, order: str) -> str:
    stem, ext = os.path.splitext(base_out)
    if not ext:
        ext = '.png'
    return f'{stem}_{order}{ext}'


# ---------------------------------------------------------------------------
# CLI.

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description='Convert a CAMSV IMGO raw frame dump to an RGB PNG (stdlib only).'
    )
    ap.add_argument('src', help='Input raw frame dump file')
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
        '--layout',
        choices=LAYOUTS,
        default=None,
        help='Byte layout: le10 = continuous little-endian 10-bit bit stream '
             'per line (default and what this board emits with FMT_SEL=0x102/'
             'PAK=1), p12 = old begonia 12-bit containers (FMT_SEL=0x101/PAK=2, '
             'reference), raw10 = MIPI RAW10, u16/u16h = 16-bit LE container '
             'per pixel with the 10-bit sample in the low (u16) or high (u16h) '
             'bits (layout-sweep candidates, bytes/line = width * 2). When not '
             'given, the layout is auto-detected from the file size and content '
             '(ties keep le10).',
    )
    ap.add_argument(
        '--pack',
        type=int,
        choices=(10, 12),
        default=None,
        help=argparse.SUPPRESS,  # deprecated: 10 -> raw10, 12 -> p12
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
        help='White balance mode (default grey = grey-world with clipped gains)',
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

    if args.layout is not None and args.pack is not None:
        ap.error('cannot combine --layout with the deprecated --pack')

    if args.width <= 1 or args.height <= 1:
        ap.error(f'invalid geometry width={args.width} height={args.height}')
    min_bpl = bpl_for(args.width, 'le10')
    if stride is not None and stride < min_bpl:
        ap.error(f'invalid stride {stride} (minimum {min_bpl} bytes for a {args.width}-pixel le10 line)')
    if out_path is None and not args.auto:
        ap.error('output PNG path required unless --auto is used')

    args.stride = stride
    args.out = out_path
    return args


def resolve_layout(args: argparse.Namespace, data: bytes) -> str:
    """Return the layout to decode with, from --layout/--pack or detection."""
    if args.pack is not None:
        layout = 'raw10' if args.pack == 10 else 'p12'
        print(
            f'note: --pack {args.pack} is deprecated; treating as --layout {layout}',
            file=sys.stderr,
        )
        return layout
    if args.layout is not None:
        return args.layout
    layout, note = detect_layout(data, args.width, args.height, args.stride)
    print(f'note: {note}', file=sys.stderr)
    return layout


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    with open(args.src, 'rb') as f:
        data = f.read()

    layout = resolve_layout(args, data)
    bpl = bpl_for(args.width, layout)
    stride = args.stride if args.stride is not None else bpl
    if stride < bpl:
        if layout == 'p12':
            usable = (stride // 3) * 2
            print(
                f'warning: stride {stride} < {bpl} bytes needed for a p12 '
                f'{args.width}-pixel line; only the first {usable} pixels of '
                f'each line hold sensor data, the rest decode as 0',
                file=sys.stderr,
            )
        else:
            usable = args.width * stride // bpl
            print(
                f'warning: stride {stride} < {bpl} bytes per layout={layout} '
                f'line; each line holds only {usable} of {args.width} pixels',
                file=sys.stderr,
            )

    phases, hw, hh = unpack_phases(data, args.width, args.height, stride, layout)
    analysis = analyze_bayer_orders(phases, args.black_level, args.wb, layout)
    if args.full:
        demosaic_fn = lambda *a: demosaic_bilinear(*a, layout=layout)  # noqa: E731
    else:
        demosaic_fn = lambda *a: demosaic_half(*a, layout=layout)  # noqa: E731

    if args.auto:
        print(f'Bayer order analysis ({args.width}x{args.height}, layout={layout}, blc={args.black_level}, wb={args.wb}):')
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
        f'gamma={args.gamma} layout={layout}'
    )
    return 0


if __name__ == '__main__':
    sys.exit(main())
