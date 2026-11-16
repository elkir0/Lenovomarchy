#!/usr/bin/env python3
"""Dump the MT6785 display engine registers through /dev/mem (debug only).

Prints "block offset value" lines for the blocks of the display path, so two
states (LK's configuration vs mediatek-drm's) can be diffed.
"""
import mmap, os, struct, sys

BLOCKS = [
    ("mipi_tx", 0x11e50000, 0x1000),
    ("mmsys", 0x14000000, 0x1000),
    ("ovl0", 0x14008000, 0x400),
    ("ovl_2l0", 0x14009000, 0x400),
    ("rdma0", 0x1400b000, 0x200),
    ("color0", 0x1400e000, 0x1000),
    ("ccorr0", 0x1400f000, 0x100),
    ("aal0", 0x14010000, 0x400),
    ("gamma0", 0x14011000, 0x100),
    ("dither0", 0x14012000, 0x100),
    ("dsi0", 0x14014000, 0x400),
    ("mutex", 0x14016000, 0x200),
    ("postmask0", 0x14021000, 0x100),
]
fd = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)
for name, base, size in BLOCKS:
    try:
        m = mmap.mmap(fd, size, mmap.MAP_SHARED, mmap.PROT_READ, offset=base)
    except OSError as e:
        print(name, "error", e); continue
    for off in range(0, size, 4):
        v = struct.unpack_from("<I", m, off)[0]
        print("%s %03x %08x" % (name, off, v))
    m.close()
