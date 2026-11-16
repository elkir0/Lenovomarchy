#!/usr/bin/env python3
# yt11-dsidcs <cmd> ...: drop DSI0 to command mode, send each command, return
# to video mode. A command is one or more comma-separated hex CMDQ words
# (e.g. 773a1500 = DCS short write 0x3a 0x77; 00043902,211083b9 = long
# write b9 83 10 21; 000a0604 = DCS read 0x0a with BTA).
import mmap, os, struct, sys, time
fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
d = mmap.mmap(fd, 0x1000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=0x14014000)
rd = lambda o: struct.unpack_from("<I", d, o)[0]
wr = lambda o, v: struct.pack_into("<I", d, o, v)
mode = rd(0x14) or 1
wr(0x0, 0); wr(0x14, 0); time.sleep(0.03)
for cmd in sys.argv[1:]:
    words = [int(w, 16) for w in cmd.split(",")]
    wr(0xc, 0)
    for i, w in enumerate(words): wr(0x200 + 4 * i, w)
    wr(0x60, len(words))
    wr(0x0, 0); wr(0x0, 1)
    t0 = time.perf_counter()
    while not rd(0xc) & 3 and time.perf_counter() - t0 < 0.05: pass
    print("sent %s: INTSTA %08x RX %08x %08x" % (cmd, rd(0xc), rd(0x74), rd(0x78)), flush=True)
    wr(0x0, 0)
wr(0x14, mode); wr(0x0, 0); wr(0x0, 1)
