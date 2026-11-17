#!/usr/bin/env python3
"""Convert CAMSV MIPI-packed RAW10 frame dump to 8-bit grayscale PNG (stdlib only).

In MIPI/CAMSV RAW10 packing, 4 pixels occupy 5 bytes: the first 4 bytes hold
the upper 8 bits of pixels 0..3 and the 5th byte holds their LSBs. This script
extracts the upper 8 bits per pixel and writes an 8-bit grayscale PNG.

Usage:
  raw2png.py <frame.bin> <width> <height> [stride] <out.png>
"""

import struct
import sys
import zlib


def png_chunk(tag: bytes, payload: bytes) -> bytes:
    return (
        struct.pack('>I', len(payload))
        + tag
        + payload
        + struct.pack('>I', zlib.crc32(tag + payload) & 0xFFFFFFFF)
    )


def main() -> int:
    if len(sys.argv) not in (5, 6):
        print(
            'usage: raw2png.py <frame.bin> <width> <height> [stride] <out.png>',
            file=sys.stderr,
        )
        return 2

    src = sys.argv[1]
    width = int(sys.argv[2], 0)
    height = int(sys.argv[3], 0)
    bpl = width * 10 // 8
    stride = int(sys.argv[4], 0) if len(sys.argv) == 6 else bpl
    dst = sys.argv[-1]

    if width <= 0 or height <= 0 or stride < bpl:
        print(
            f'error: invalid geometry width={width} height={height} stride={stride} (min {bpl})',
            file=sys.stderr,
        )
        return 2

    with open(src, 'rb') as f:
        data = f.read()

    needed = (height - 1) * stride + bpl
    if len(data) < needed:
        print(
            f'warning: {src} is {len(data)} bytes (< expected {needed}), padding missing pixels with 0',
            file=sys.stderr,
        )

    rows = []
    for y in range(height):
        start = y * stride
        line = data[start : start + bpl]
        px = bytearray()
        for i in range(0, len(line) - 4, 5):
            px.extend(line[i : i + 4])
        if len(px) < width:
            px.extend(b'\x00' * (width - len(px)))
        rows.append(b'\x00' + bytes(px[:width]))

    ihdr = struct.pack('>IIBBBBB', width, height, 8, 0, 0, 0, 0)
    png = (
        b'\x89PNG\r\n\x1a\n'
        + png_chunk(b'IHDR', ihdr)
        + png_chunk(b'IDAT', zlib.compress(b''.join(rows), 9))
        + png_chunk(b'IEND', b'')
    )

    with open(dst, 'wb') as f:
        f.write(png)

    print(f'ok {dst} {width}x{height} stride={stride}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
