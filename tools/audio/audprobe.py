#!/usr/bin/env python3
"""yt11-audprobe [seconds]: silent speaker-path probe (debug only).

Mutes the four CS35L41 amps, plays digital silence on the speaker (I2S1)
back end and snapshots the AFE I2S registers, the I2S1/I2S2 pin modes and
pad levels, and the amps' power and clock status while the stream runs.
Never plays anything but zeros. Needs i2c-tools and /dev/mem.
"""
import mmap, os, re, subprocess, sys, time

CARD = "0"
AFE = 0x11210000
AFE_REGS = [("AUDIO_TOP_CON0", 0x0), ("AUDIO_TOP_CON1", 0x4), ("AFE_DAC_CON0", 0x10),
            ("AFE_I2S_CON", 0x18), ("AFE_I2S_CON1", 0x34), ("AFE_I2S_CON2", 0x38),
            ("AFE_I2S_CON3", 0x40), ("AFE_I2S_CON4", 0x9f8), ("AFE_APLL1_TUNER_CFG", 0x3f0)]
AMP_REGS = [("PWR_CTRL1", 0x2014), ("PWR_CTRL2", 0x2018), ("PLL_CLK_CTRL", 0x2c04),
            ("GLOBAL_CLK_CTRL", 0x2c0c), ("SP_ENABLES", 0x4800), ("SP_RATE_CTRL", 0x4804),
            ("SP_FORMAT", 0x4808), ("SP_RX_SLOT", 0x4820), ("DAC_PCM1_SRC", 0x4c00),
            ("AMP_DIG_VOL", 0x6000), ("IRQ1_ST1", 0x10010), ("IRQ1_ST2", 0x10014),
            ("IRQ1_ST3", 0x10018), ("IRQ1_ST4", 0x1001c), ("RAW_ST1", 0x10090),
            ("RAW_ST2", 0x10094), ("RAW_ST3", 0x10098), ("RAW_ST4", 0x1009c)]
AMPS = [0x40, 0x41, 0x42, 0x43]
ROUTES = ["I2S1_CH1 DL1_CH1", "I2S1_CH2 DL1_CH2", "Speaker Switch"]


def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout


def cset(name, val):
    subprocess.run(["amixer", "-c", CARD, "-q", "cset", "name=" + name, str(val)], check=True)


def amp_read(addr, reg):
    b = [(reg >> s) & 0xff for s in (24, 16, 8, 0)]
    out = sh("i2ctransfer -f -y 0 w4@0x%02x %s r4" % (addr, " ".join(str(x) for x in b)))
    vals = out.split()
    if len(vals) != 4:
        return None
    return int("".join(v[2:] for v in vals), 16)


def amps_dump(tag):
    print("== amps (%s)" % tag)
    for name, reg in AMP_REGS:
        vals = []
        for a in AMPS:
            v = amp_read(a, reg)
            vals.append("--------" if v is None else "%08x" % v)
        print("  %-16s %06x  %s" % (name, reg, " ".join(vals)))


def afe_dump():
    fd = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)
    m = mmap.mmap(fd, 0x1000, mmap.MAP_SHARED, mmap.PROT_READ, offset=AFE)
    print("== afe")
    for name, off in AFE_REGS:
        print("  %-20s %03x  %08x" % (name, off, int.from_bytes(m[off:off + 4], "little")))
    m.close()
    os.close(fd)


def pins_dump():
    print("== pins")
    txt = open("/sys/kernel/debug/pinctrl/10005000.pinctrl-pinctrl_paris/pins").read()
    for line in txt.splitlines():
        if re.match(r"pin (24|31|32|33|34) ", line):
            print("  " + line.strip())


def pin_sample(n=20000):
    """Sample the I2S1/I2S2 pads (GPIO31..34) through the GPIO input registers."""
    fd = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)
    m = mmap.mmap(fd, 0x1000, mmap.MAP_SHARED, mmap.PROT_READ, offset=0x10005000)
    ones = {31: 0, 32: 0, 33: 0, 34: 0}
    for _ in range(n):
        v = int.from_bytes(m[0x200:0x204], "little") | (int.from_bytes(m[0x210:0x214], "little") << 32)
        for pin in ones:
            ones[pin] += (v >> pin) & 1
    m.close()
    os.close(fd)
    print("== pad samples (ones / %d): %s" % (n, " ".join("GPIO%d=%d" % kv for kv in ones.items())))


def main():
    secs = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    subprocess.run("modprobe i2c-dev", shell=True)
    for n in range(1, 5):
        cset("SPK%d Digital PCM Volume" % n, 0)
        cset("SPK%d Analog PCM Volume" % n, 0)
    amps_dump("idle")
    for r in ROUTES:
        cset(r, "on")
    subprocess.run("dmesg -C", shell=True)
    play = subprocess.Popen(["aplay", "-q", "-D", "hw:%s,0" % CARD, "-t", "raw", "-f", "S32_LE",
                             "-r", "48000", "-c", "2", "-d", str(secs), "/dev/zero"])
    time.sleep(1.5)
    try:
        afe_dump()
        pins_dump()
        pin_sample()
        amps_dump("streaming")
    finally:
        play.wait()
        for r in ROUTES:
            cset(r, "off")
    amps_dump("after")
    print("== dmesg")
    print(sh("dmesg | grep -v 'Kernel command line' | tail -25"))


main()
