#!/usr/bin/env python3
"""Write register values from a regdump file back into the live hardware
(debug only): regload.py <dump> <block>[:off,off,...] ...

Only offsets listed (or every offset of the block when none is given) are
written, through /dev/mem.
"""
import mmap, os, struct, sys

BASES = {"mipi_tx": 0x11e50000, "mmsys": 0x14000000, "ovl0": 0x14008000,
         "ovl_2l0": 0x14009000, "rdma0": 0x1400b000, "color0": 0x1400e000,
         "ccorr0": 0x1400f000, "aal0": 0x14010000, "gamma0": 0x14011000,
         "dither0": 0x14012000, "dsi0": 0x14014000, "mutex": 0x14016000,
         "postmask0": 0x14021000}
dump = {}
for line in open(sys.argv[1]):
    b, off, val = line.split()
    dump.setdefault(b, {})[int(off, 16)] = int(val, 16)
fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
for spec in sys.argv[2:]:
    blk, _, offs = spec.partition(":")
    offsets = [int(o, 16) for o in offs.split(",")] if offs else sorted(dump[blk])
    m = mmap.mmap(fd, 0x1000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=BASES[blk])
    for off in offsets:
        old = struct.unpack_from("<I", m, off)[0]
        struct.pack_into("<I", m, off, dump[blk][off])
        print("%s %03x %08x -> %08x" % (blk, off, old, dump[blk][off]))
    m.close()
