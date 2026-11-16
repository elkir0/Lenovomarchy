#!/usr/bin/env python3
# yt11-dsireinit [regsfile]: stop DSI0, reset its engine, rewrite its config
# registers with their current values (or those of regsfile), restart video mode.
import mmap, os, struct, sys, time
fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
d = mmap.mmap(fd, 0x1000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=0x14014000)
rd = lambda o: struct.unpack_from("<I", d, o)[0]
wr = lambda o, v: struct.pack_into("<I", d, o, v)
cfg = [0x8,0x18,0x1c,0x20,0x24,0x28,0x2c,0x38,0x50,0x54,0x58,0x5c,0x60,0x64,0x104,0x108,0x10c,0x110,0x114,0x118,0x11c,0x130,0x190,0x1d0]
val = {o: rd(o) for o in cfg + [0x14]}
if len(sys.argv) > 1:
    for l in open(sys.argv[1]):
        b, o, v = l.split()
        if b == "dsi0" and int(o, 16) in val: val[int(o, 16)] = int(v, 16)
wr(0x0, 0); wr(0x14, 0); time.sleep(0.03)
wr(0x10, rd(0x10) | 1); wr(0x10, rd(0x10) & ~1)
for o in cfg: wr(o, val[o])
wr(0x14, val[0x14]); wr(0x0, 0); wr(0x0, 1)
print("dsi0 reinit: PSCTRL %08x MODE %08x TXRX %08x" % (rd(0x1c), rd(0x14), rd(0x18)))
