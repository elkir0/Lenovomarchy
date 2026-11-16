#!/usr/bin/env python3
# yt11-dsirate [off=val ...]: optionally poke DSI0 registers (hex), then report
# input vs output line pace and whether the underrun bit recurs.
import mmap, os, struct, sys, time
fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
d = mmap.mmap(fd, 0x1000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=0x14014000)
rd = lambda o: struct.unpack_from("<I", d, o)[0]
wr = lambda o, v: struct.pack_into("<I", d, o, v)
for a in sys.argv[1:]:
    o, v = (int(x, 16) for x in a.split("="))
    print("dsi0 %03x %08x -> %08x" % (o, rd(o), v)); wr(o, v)
time.sleep(0.1)
def wait_line(n, tmo=0.1):
    t0 = time.perf_counter()
    while ((rd(0x1d4) >> 16) & 0x1fff) != n:
        if time.perf_counter() - t0 > tmo: return None
    return time.perf_counter()
t1 = wait_line(500); t2 = wait_line(800)
def spin(cond, tmo=0.1):
    t0 = time.perf_counter()
    while cond():
        if time.perf_counter() - t0 > tmo: return False
    return True
ok = spin(lambda: rd(0x164) & 0x2000) and spin(lambda: not rd(0x164) & 0x2000)
a = time.perf_counter()
ok = ok and spin(lambda: rd(0x164) & 0x2000)
b = time.perf_counter()
if not ok:
    print("DSI not cycling: START %08x MODE %08x DBG7 %08x INTSTA %08x" % (rd(0), rd(0x14), rd(0x164), rd(0xc)), flush=True); sys.exit(1)
wr(0xc, 0); time.sleep(0.05)
inp = (t2 - t1) / 300 * 1e6 if t1 and t2 else float("nan")
out = (b - a) / (rd(0x2c) & 0xfff) * 1e6
print("input %.3f us/line, DSI %.3f us/line, ratio %.3f, INTSTA %08x%s" % (
    inp, out, out / inp, rd(0xc), "  UNDERRUN" if rd(0xc) & 0x1000 else "  no underrun"))
