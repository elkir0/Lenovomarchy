#!/usr/bin/env python3
# yt11-wifi-cycle [low_ms] [high_ms]: unbind the MMC1 host, drop the MT7663
# enable line (GPIO99) for low_ms, raise it, wait high_ms, rebind the host,
# then report GPIO149 (the chip's interrupt line) and any SDIO card.
import mmap, os, struct, subprocess, sys, time
low = float(sys.argv[1]) / 1000 if len(sys.argv) > 1 else 0.2
high = float(sys.argv[2]) / 1000 if len(sys.argv) > 2 else 0.15
fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
g = mmap.mmap(fd, 0x1000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=0x10005000)
rd = lambda o: struct.unpack_from("<I", g, o)[0]
wr = lambda o, v: struct.pack_into("<I", g, o, v)
pin = lambda n: (rd(0x200 + 0x10 * (n // 32)) >> (n % 32)) & 1   # DIN
BIT = 1 << (99 % 32)
drv = "/sys/bus/platform/drivers/mtk-msdc/"
try:
    open(drv + "unbind", "w").write("11240000.mmc")
except OSError:
    pass
wr(0x138, BIT); time.sleep(low)
print("GPIO99 low: GPIO149=%d" % pin(149))
wr(0x134, BIT)
for i in range(int(high / 0.01)):
    time.sleep(0.01)
print("GPIO99 high %d ms: GPIO149=%d GPIO10=%d" % (high * 1000, pin(149), pin(10)))
subprocess.run("dmesg -C", shell=True)
open(drv + "bind", "w").write("11240000.mmc")
time.sleep(2)
out = subprocess.run("dmesg | grep -iE 'mmc1|sdio' | grep -v 'Kernel command line' | tail -3; ls /sys/bus/sdio/devices/",
                     shell=True, capture_output=True, text=True).stdout
print(out.strip() or "no SDIO card")
