#!/usr/bin/env python3
# Clear DSI0 INTSTA and timestamp when each status bit reappears.
import mmap, os, struct, time
fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
d = mmap.mmap(fd, 0x1000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=0x14014000)
rd = lambda o: struct.unpack_from("<I", d, o)[0]
names = {4: "FRAME_DONE", 7: "TE_TIMEOUT", 8: "VBP_STR", 9: "VACT_STR", 10: "VFP_STR", 12: "UNDERRUN", 13: "BTA_TO", 14: "INP_UNFINISH"}
for run in range(3):
    struct.pack_into("<I", d, 0xc, 0)
    t0 = time.perf_counter(); seen = {}; prev = rd(0xc)
    while time.perf_counter() - t0 < 0.06:
        v = rd(0xc); now = (time.perf_counter() - t0) * 1000
        for b, n in names.items():
            if v & (1 << b) and n not in seen:
                seen[n] = round(now, 2)
                if b == 12:
                    seen["dbg7_at_underrun"] = "%08x" % rd(0x164)
                    seen["inp_dbg_at_underrun"] = "%08x" % rd(0x1d4)
    print("run", run, "after-clear=%08x" % prev, seen)
print("STALL_DBG1..4: %08x %08x %08x %08x" % tuple(rd(o) for o in (0x1c0, 0x1c4, 0x1c8, 0x1cc)))
print("DBG7 now %08x  SHADOW_DEBUG %08x  SHADOW_STA %08x" % (rd(0x164), rd(0x190), rd(0x194)))
