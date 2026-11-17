#!/usr/bin/env python3
"""Convert a MT6785 CAMSV IMGO raw frame dump to 8-bit grayscale PNG (stdlib only).

Three byte layouts are supported (--layout {le10,p12,raw10}; the old --pack
{10,12} spelling is still accepted, 10 -> raw10 and 12 -> p12):

- le10 (default; measured on YT-J706F with CAMSV FMT_SEL = 0x102 / PAK = 1,
  see docs/hardware/CAMERA.md): each line is one continuous little-endian
  10-bit bit stream; pixel k occupies bits 10k..10k+9 of the line read as a
  little-endian integer. Line length = width * 10 / 8 bytes.
- p12 (old begonia values, FMT_SEL = 0x101 / PAK = 2, kept for reference):
  2 pixels per 3 bytes as two little-endian 12-bit fields, each holding the
  10-bit sample shifted left by two (0xffc = 1023 << 2). Line length =
  width * 12 / 8 bytes; with a shorter stride only 2/3 of the pixels fit.
- raw10 (MIPI CSI-2 RAW10): 4 pixels occupy 5 bytes; the first 4 bytes hold
  the upper 8 bits of pixels 0..3 and the 5th byte holds their LSBs. Line
  length = width * 10 / 8 bytes.

The layout is auto-detected from the file size and, when the size is
ambiguous between le10 and raw10, from the decoded content (both share
width * 10 / 8 bytes per line).

This tool keeps only the top 8 bits of each pixel (fast Bayer-grid check);
use raw2rgb.py for colour decoding.

Usage:
  raw2png.py <frame.bin> <width> <height> [--layout {le10,p12,raw10}] [stride] <out.png>
"""

import sys


def png_chunk(tag: bytes, payload: bytes) -> bytes:
    import struct
    import zlib
    return (
        struct.pack('>I', len(payload))
        + tag
        + payload
        + struct.pack('>I', zlib.crc32(tag + payload) & 0xFFFFFFFF)
    )


LAYOUTS = ('le10', 'p12', 'raw10')


def bpl_for(width: int, layout: str) -> int:
    if layout in ('le10', 'raw10'):
        return (width * 10 + 7) // 8
    if layout == 'p12':
        return (width * 12 + 7) // 8
    raise ValueError(f'unsupported layout {layout!r}')


def unpack_le10_top8(line: bytes, width: int) -> bytes:
    """Top 8 bits of each pixel from an le10 line (continuous LE 10-bit stream)."""
    out = bytearray(width)
    px = 0
    for base in range(0, (len(line) // 5) * 5, 5):
        if px >= width:
            break
        b0, b1, b2, b3, b4 = line[base], line[base + 1], line[base + 2], line[base + 3], line[base + 4]
        # pixel = b0 | (b1 & 3) << 8 -> top8 = (b0 >> 2) | ((b1 & 3) << 6)
        out[px] = (b0 >> 2) | ((b1 & 0x03) << 6)
        px += 1
        if px >= width:
            break
        # pixel = (b1 >> 2) | (b2 & 0xF) << 6 -> top8 = (b1 >> 4) | (b2 & 0xF) << 4
        out[px] = (b1 >> 4) | ((b2 & 0x0F) << 4)
        px += 1
        if px >= width:
            break
        # pixel = (b2 >> 4) | (b3 & 0x3F) << 4 -> top8 = (b2 >> 6) | (b3 & 0x3F) << 2
        out[px] = (b2 >> 6) | ((b3 & 0x3F) << 2)
        px += 1
        if px >= width:
            break
        # pixel = (b3 >> 6) | b4 << 2 -> top8 = b4
        out[px] = b4
        px += 1
    if px < width:
        # tail group (width % 4 != 0): decode the leftover bits slowly
        v = int.from_bytes(line, 'little')
        while px < width:
            p = (v >> (10 * px)) & 0x3FF
            out[px] = p >> 2
            px += 1
    return bytes(out)


def unpack_p12_top8(line: bytes, width: int) -> bytes:
    """Top 8 bits of each pixel from a p12 line (2 px / 3 bytes, sample << 2)."""
    out = bytearray(width)
    px = 0
    for base in range(0, len(line) - 2, 3):
        if px >= width:
            break
        # 12-bit field = sample << 2 -> top8 of sample = field >> 4
        out[px] = (((line[base + 1] & 0x0F) << 4) | (line[base] >> 4)) & 0xFF
        px += 1
        if px >= width:
            break
        out[px] = line[base + 2]
        px += 1
    return bytes(out)


def unpack_raw10_top8(line: bytes, width: int) -> bytes:
    """Top 8 bits of each pixel from a MIPI RAW10 line (4 px / 5 bytes)."""
    out = bytearray(width)
    px = 0
    for base in range(0, len(line) - 4, 5):
        if px >= width:
            break
        out[px] = line[base]
        out[px + 1] = line[base + 1]
        out[px + 2] = line[base + 2]
        out[px + 3] = line[base + 3]
        px += 4
    if px < width:
        for k in range(px, width):
            # same group, k = px % 4: msb byte + lsb bits from byte 4
            base = (px // 4) * 5
            if base + k % 4 < len(line):
                out[k] = line[base + k % 4]
            else:
                out[k] = 0
    return bytes(out)


def detect_layout(width: int, height: int, file_size: int, stride: int) -> str | None:
    """Guess the layout from the file size (both 10-bit layouts share a size).

    Returns 'p12' only when the file fits a full p12 frame and nothing else;
    ambiguous cases return None (the caller then decides with a content test
    between le10 and raw10).
    """
    fits = []
    for layout in LAYOUTS:
        bpl = bpl_for(width, layout)
        if file_size >= (height - 1) * stride + bpl:
            fits.append(layout)
    if fits == ['p12']:
        return 'p12'
    return None


def looks_p12(data: bytes, stride: int, lines: int = 4) -> bool:
    """Content test for the p12 layout on a 10-bit-sized stride.

    In the p12 layout the 10-bit sample occupies bits [11:2] of each 12-bit
    field, so the middle byte of every 3-byte pixel pair takes few distinct
    values (bounded by the two neighbouring nibbles); in a genuine le10 or
    raw10 line that byte spreads over all 256 values for natural content.
    """
    vals: set[int] = set()
    checked = 0
    for y in range(min(lines, max(1, len(data) // stride))):
        line = data[y * stride : (y + 1) * stride]
        vals.update(line[1::3])
        checked += len(line) // 3
    return checked >= 24 and len(vals) <= 16


def _score_le10_vs_raw10(data: bytes, width: int, stride: int, lines: int = 8) -> tuple[float, float]:
    """Mean horizontal gradient of the decoded top-8 image for both layouts.

    Decoding an le10 file as raw10 (or the reverse) shuffles bits between
    neighbouring pixels and makes the horizontal gradient explode, so the
    smaller score wins.
    """
    tot_le = tot_rq = cnt = 0
    for y in range(min(lines, max(1, len(data) // stride))):
        line = data[y * stride : (y + 1) * stride]
        px = unpack_le10_top8(line, width)
        rq = unpack_raw10_top8(line, width)
        for i in range(width - 1):
            tot_le += abs(px[i + 1] - px[i])
            tot_rq += abs(rq[i + 1] - rq[i])
            cnt += 1
    return tot_le / max(1, cnt), tot_rq / max(1, cnt)


def main() -> int:
    args = sys.argv[1:]
    layout = None
    if '--layout' in args:
        i = args.index('--layout')
        if i + 1 >= len(args) or args[i + 1] not in LAYOUTS:
            print(f'error: --layout expects one of {LAYOUTS}', file=sys.stderr)
            return 2
        layout = args[i + 1]
        del args[i : i + 2]
    pack = None
    if '--pack' in args:
        i = args.index('--pack')
        if i + 1 >= len(args) or args[i + 1] not in ('10', '12'):
            print('error: --pack expects 10 or 12 (deprecated; use --layout)', file=sys.stderr)
            return 2
        pack = int(args[i + 1])
        del args[i : i + 2]
    if layout is not None and pack is not None:
        print('error: cannot combine --layout with the deprecated --pack', file=sys.stderr)
        return 2

    if len(args) not in (4, 5):
        print(
            'usage: raw2png.py <frame.bin> <width> <height> '
            '[--layout {le10,p12,raw10}] [stride] <out.png>',
            file=sys.stderr,
        )
        return 2

    src = args[0]
    width = int(args[1], 0)
    height = int(args[2], 0)
    if len(args) == 5:
        stride = int(args[3], 0)
        dst = args[4]
    else:
        stride = None
        dst = args[3]

    explicit = layout is not None or pack is not None
    if pack is not None:
        layout = 'raw10' if pack == 10 else 'p12'
        print(f'note: --pack {pack} is deprecated; treating as --layout {layout}', file=sys.stderr)
    if layout is None:
        layout = 'le10'

    bpl = bpl_for(width, layout)
    if stride is None:
        stride = bpl
    if width <= 0 or height <= 0 or (explicit and stride < bpl):
        print(
            f'error: invalid geometry width={width} height={height} stride={stride} '
            f'(min {bpl} for layout={layout})',
            file=sys.stderr,
        )
        return 2
    if not explicit and stride < bpl_for(width, 'le10'):
        print(
            f'error: invalid stride {stride} (minimum {bpl_for(width, "le10")} for a '
            f'{width}-pixel le10 line)',
            file=sys.stderr,
        )
        return 2

    with open(src, 'rb') as f:
        data = f.read()

    if not explicit:
        det = detect_layout(width, height, len(data), stride)
        if det == 'p12':
            print(f'note: {src} is {len(data)} bytes, only a full p12 frame fits; treating as p12', file=sys.stderr)
            layout = 'p12'
            bpl = bpl_for(width, layout)
        elif layout == 'le10' and len(data) >= bpl:
            # le10 and raw10 share the same line size; pick by content
            s_le, s_rq = _score_le10_vs_raw10(data, width, stride)
            if s_rq * 2 < s_le:
                print(
                    f'note: {src} decodes smoother as raw10 (h-grad {s_rq:.1f} vs '
                    f'{s_le:.1f} as le10); treating as raw10',
                    file=sys.stderr,
                )
                layout = 'raw10'
                bpl = bpl_for(width, layout)

    needed = (height - 1) * stride + bpl
    if len(data) < needed:
        print(
            f'warning: {src} is {len(data)} bytes (< expected {needed}), padding missing pixels with 0',
            file=sys.stderr,
        )

    unpack = {
        'le10': unpack_le10_top8,
        'p12': unpack_p12_top8,
        'raw10': unpack_raw10_top8,
    }[layout]
    rows = []
    for y in range(height):
        start = y * stride
        line = data[start : start + max(stride, bpl)]
        rows.append(b'\x00' + unpack(line, width))

    import struct
    import zlib

    ihdr = struct.pack('>IIBBBBB', width, height, 8, 0, 0, 0, 0)
    png = (
        b'\x89PNG\r\n\x1a\n'
        + png_chunk(b'IHDR', ihdr)
        + png_chunk(b'IDAT', zlib.compress(b''.join(rows), 9))
        + png_chunk(b'IEND', b'')
    )

    with open(dst, 'wb') as f:
        f.write(png)

    print(f'ok {dst} {width}x{height} stride={stride} layout={layout}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
