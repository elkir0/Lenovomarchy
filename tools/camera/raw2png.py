#!/usr/bin/env python3
"""Convert a MT6785 CAMSV IMGO raw frame dump to 8-bit grayscale PNG (stdlib only).

Two byte layouts are supported (--pack {10,12}):

- pack 10 (MIPI RAW10, ``CAMSV_PAK = 2``): 4 pixels occupy 5 bytes; the first
  4 bytes hold the upper 8 bits of pixels 0..3 and the 5th byte holds their
  LSBs. Line length = width * 10 / 8 bytes.
- pack 12 (what MT6785 CAMSV actually emits with ``CAMSV_PAK = 2`` +
  ``CAMSV_FMT_SEL = 0x101``): 2 pixels per 3 bytes as two little-endian
  12-bit fields, each holding the 10-bit sample shifted left by two
  (0xffc = 1023 << 2). Line length = width * 12 / 8 bytes.

This tool keeps only the top 8 bits of each pixel (fast Bayer-grid check);
use raw2rgb.py for colour decoding.

Usage:
  raw2png.py <frame.bin> <width> <height> [--pack {10,12}] [stride] <out.png>
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


def detect_pack(width: int, height: int, file_size: int, stride: int) -> int | None:
    """Guess the packing from the file size (see raw2rgb.detect_pack)."""
    candidates = []
    for pack in (10, 12):
        bpl = (width * pack + 7) // 8
        if file_size >= (height - 1) * stride + bpl:
            candidates.append(pack)
    return candidates[0] if len(candidates) == 1 else None


def detect_pack12_content(data: bytes, stride: int, lines: int = 4) -> bool:
    """Content test for the 12-bit packed layout (see raw2rgb.detect_pack12_content)."""
    vals: set[int] = set()
    checked = 0
    for y in range(min(lines, max(1, len(data) // stride))):
        line = data[y * stride : (y + 1) * stride]
        vals.update(line[1::3])
        checked += len(line) // 3
    return checked >= 96 and len(vals) <= 4


def unpack10_top8(line: bytes, width: int) -> bytes:
    """Upper 8 bits of each pixel from a MIPI RAW10 line (4 px / 5 bytes)."""
    px = bytearray()
    for i in range(0, len(line) - 4, 5):
        px.extend(line[i : i + 4])
    if len(px) < width:
        px.extend(b'\x00' * (width - len(px)))
    return bytes(px[:width])


def unpack12_top8(line: bytes, width: int) -> bytes:
    """Upper 8 bits of each pixel from a 12-bit packed line (2 px / 3 bytes).

    The 10-bit sample occupies bits [11:2] of each little-endian 12-bit field,
    so its top 8 bits are bits [11:4]: byte0 for even pixels, byte2 for odd
    pixels (after the nibble split).
    """
    px = bytearray()
    n = min(width, len(line) * 2 // 3)
    for k in range(n):
        base = (k // 2) * 3
        if k % 2 == 0:
            # top 8 bits = (b1 & 0xF) << 4 | b0 >> 4
            px.append(((line[base + 1] & 0x0F) << 4) | (line[base] >> 4))
        else:
            # field = (b1 >> 4) | (b2 << 4); top 8 bits = field >> 4 = b2
            px.append(line[base + 2])
    if len(px) < width:
        px.extend(b'\x00' * (width - len(px)))
    return bytes(px[:width])


def main() -> int:
    args = sys.argv[1:]
    pack = 10
    if '--pack' in args:
        i = args.index('--pack')
        if i + 1 >= len(args) or args[i + 1] not in ('10', '12'):
            print('error: --pack expects 10 or 12', file=sys.stderr)
            return 2
        pack = int(args[i + 1])
        del args[i : i + 2]
    if len(args) not in (4, 5):
        print(
            'usage: raw2png.py <frame.bin> <width> <height> [--pack {10,12}] [stride] <out.png>',
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

    bpl = (width * pack + 7) // 8
    if stride is None:
        stride = bpl
    if width <= 0 or height <= 0 or stride < bpl:
        print(
            f'error: invalid geometry width={width} height={height} stride={stride} (min {bpl} for pack={pack})',
            file=sys.stderr,
        )
        return 2

    with open(src, 'rb') as f:
        data = f.read()

    if pack == 10 and '--pack' not in sys.argv:
        det = detect_pack(width, height, len(data), stride)
        if det == 12:
            print(
                f'note: {src} is {len(data)} bytes, too small for a {width}x{height} '
                f'pack=10 frame; treating as pack=12',
                file=sys.stderr,
            )
            pack = 12
            bpl = (width * pack + 7) // 8
        else:
            # same-size ambiguity as raw2rgb.py: a truncated pack=12 capture has
            # exactly the pack=10 frame size; the middle bytes of each 3-byte
            # pair take few distinct values in the 12-bit layout.
            if detect_pack12_content(data, stride):
                print(
                    f'note: {src} has the 12-bit packed byte signature; treating as pack=12',
                    file=sys.stderr,
                )
                pack = 12
                bpl = (width * pack + 7) // 8

    needed = (height - 1) * stride + bpl
    if len(data) < needed:
        print(
            f'warning: {src} is {len(data)} bytes (< expected {needed}), padding missing pixels with 0',
            file=sys.stderr,
        )

    unpack = unpack10_top8 if pack == 10 else unpack12_top8
    rows = []
    for y in range(height):
        start = y * stride
        line = data[start : start + stride]
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

    print(f'ok {dst} {width}x{height} stride={stride} pack={pack}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
