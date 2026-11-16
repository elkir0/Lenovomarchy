#!/usr/bin/env python3
# Over ~50 ms: DSI vertical phase changes (DBG7 bits 12-15) and input line milestones.
import mmap, os, struct, time
fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
d = mmap.mmap(fd, 0x1000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=0x14014000)
rd = lambda o: struct.unpack_from("<I", d, o)[0]
ph = {0x1000: "VFP", 0x2000: "VACT", 0x4000: "VBP", 0x8000: "VSA", 0: "idle"}
t0 = time.perf_counter(); lastph = None; lastmile = -1; ev = []
while time.perf_counter() - t0 < 0.05:
    t = (time.perf_counter() - t0) * 1000
    p = rd(0x164) & 0xf000; inl = (rd(0x1d4) >> 16) & 0x1fff
    if p != lastph:
        ev.append("%6.2f DSI %s (in_line=%d)" % (t, ph.get(p, hex(p)), inl)); lastph = p
    m = inl // 250
    if m != lastmile:
        ev.append("%6.2f   input line %d" % (t, inl)); lastmile = m
print("\n".join(ev))
