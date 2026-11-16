#!/usr/bin/env python3
# yt11-dsiwatch <seconds> [interval_frames]: every few frames, print the
# CLOCK_MONOTONIC time (comparable with dmesg) and the DSI0 pull ratio
# (output line period / input line period) measured within one VACT.
import mmap, os, struct, sys, time
fd = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)
d = mmap.mmap(fd, 0x1000, mmap.MAP_SHARED, mmap.PROT_READ, offset=0x14014000)
rd = lambda o: struct.unpack_from("<I", d, o)[0]
dur = float(sys.argv[1]) if len(sys.argv) > 1 else 30
every = int(sys.argv[2]) if len(sys.argv) > 2 else 6
def spin(cond, tmo):
    t0 = time.monotonic()
    while cond():
        if time.monotonic() - t0 > tmo: return False
    return True
end = time.monotonic() + dur; n = 0; last = None
while time.monotonic() < end:
    vact = lambda: rd(0x164) & 0x2000
    if not (spin(lambda: vact(), 0.05) and spin(lambda: not vact(), 0.05)):
        msg = "stalled"
    else:
        t0 = time.monotonic(); l0 = (rd(0x1d4) >> 16) & 0x1fff
        spin(lambda: time.monotonic() - t0 < 0.004, 0.01)
        t1 = time.monotonic(); l1 = (rd(0x1d4) >> 16) & 0x1fff
        spin(lambda: vact(), 0.05); t2 = time.monotonic()
        vlines = rd(0x2c) & 0xfff or 1
        out = (t2 - t0) / vlines; dl = l1 - l0
        msg = "ratio %.3f" % (out / ((t1 - t0) / dl)) if dl > 0 else "no input"
    n += 1
    if msg != last or n % every == 0:
        print("[%11.6f] %s" % (time.monotonic(), msg), flush=True); last = msg
