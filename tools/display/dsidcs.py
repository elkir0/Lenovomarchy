#!/usr/bin/env python3
# yt11-dsidcs <hexword>...: drop DSI0 to command mode, send raw CMDQ words
# (e.g. 773a1500 = DCS short write 0x3a 0x77), return to video mode.
import mmap, os, struct, sys, time
fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
d = mmap.mmap(fd, 0x1000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=0x14014000)
rd = lambda o: struct.unpack_from("<I", d, o)[0]
wr = lambda o, v: struct.pack_into("<I", d, o, v)
mode = rd(0x14) or 1
wr(0x0, 0); wr(0x14, 0); time.sleep(0.03)
for w in sys.argv[1:]:
    wr(0xc, 0)
    wr(0x200, int(w, 16)); wr(0x60, 1)
    wr(0x0, 0); wr(0x0, 1)
    t0 = time.perf_counter()
    while not rd(0xc) & 2 and time.perf_counter() - t0 < 0.05: pass
    print("sent %s: INTSTA %08x" % (w, rd(0xc)), flush=True)
    wr(0x0, 0)
wr(0x14, mode); wr(0x0, 0); wr(0x0, 1)
