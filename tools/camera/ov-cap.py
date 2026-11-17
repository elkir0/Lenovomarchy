#!/usr/bin/env python3
"""Real-sensor OV8856 MIPI CSI-2 capture test via MT6785 SENINF + CAMSV0.

Ported from begonia's ov8856-mipi/ov-cap.py and parameterized for boards whose
CSI port, SENINF index, lane count, and I2C bus/address are not yet fixed.
Uses /sys/kernel/debug/camsv-tm/ for SENINF/ANA/CAMSV0 registers and DMA,
larb-bypass.py for physical CMA DMA without IOMMU, and /dev/i2c-N for OV8856.

Preconditions on YT-J706F:
  - mt6785-camsv-tm loaded (also enables CLK_APMIXED_MIPIC0/1 26 MHz gates)
  - yt11-cam-probe loaded (unless --power-mode sysfs/none)
  - i2c-mt65xx multi-channel support active on the camera I2C bus

Usage:
  sudo python3 ov-cap.py --csi-port 0 --lanes 2 --i2c-bus 2 --i2c-addr 0x36
"""

import argparse
import fcntl
import ctypes
import glob
import mmap
import os
import struct
import subprocess
import sys
import time

DBG = '/sys/kernel/debug/camsv-tm'
PROBE_POWER = '/sys/kernel/debug/yt11-cam/power'
HERE = os.path.dirname(os.path.realpath(__file__))

# HAL SeninfDrvImp::getCSIInfo() default mapping on MT6785: csi_port -> seninf
CSI_TO_SENINF = {0: 0, 1: 2, 2: 4}

# OV8856 0x3018 MIPI lane control (from mainline ov8856.c / begonia init.regs)
OV8856_LANE_REG = {1: 0x12, 2: 0x32, 4: 0x72}

# OV8856 initialization sequence (24 MHz XVCLK base from begonia ov8856-mipi/init.regs)
OV8856_INIT_REGS = (
    (0x0103, 0x01), (0x0100, 0x00), (0x0302, 0x3C), (0x0303, 0x01), (0x031E, 0x0C),
    (0x3000, 0x00), (0x300E, 0x00), (0x3010, 0x00), (0x3015, 0x84), (0x3018, 0x32),
    (0x3021, 0x23), (0x3033, 0x24), (0x3500, 0x00), (0x3501, 0x4C), (0x3502, 0xE0),
    (0x3503, 0x08), (0x3505, 0x83), (0x3508, 0x01), (0x3509, 0x80), (0x350C, 0x00),
    (0x350D, 0x80), (0x350E, 0x04), (0x350F, 0x00), (0x3510, 0x00), (0x3511, 0x02),
    (0x3512, 0x00), (0x3600, 0x72), (0x3601, 0x40), (0x3602, 0x30), (0x3610, 0xC5),
    (0x3611, 0x58), (0x3612, 0x5C), (0x3613, 0xCA), (0x3614, 0x60), (0x3628, 0xFF),
    (0x3629, 0xFF), (0x362A, 0xFF), (0x3633, 0x10), (0x3634, 0x10), (0x3635, 0x10),
    (0x3636, 0x10), (0x3663, 0x08), (0x3669, 0x34), (0x366E, 0x08), (0x3706, 0x86),
    (0x370B, 0x7E), (0x3714, 0x27), (0x3730, 0x12), (0x3733, 0x10), (0x3764, 0x00),
    (0x3765, 0x00), (0x3769, 0x62), (0x376A, 0x2A), (0x376B, 0x30), (0x3780, 0x00),
    (0x3781, 0x24), (0x3782, 0x00), (0x3783, 0x23), (0x3798, 0x2F), (0x37A1, 0x60),
    (0x37A8, 0x6A), (0x37AB, 0x3F), (0x37C2, 0x14), (0x37C3, 0xF1), (0x37C9, 0x80),
    (0x37CB, 0x16), (0x37CC, 0x16), (0x37CD, 0x16), (0x37CE, 0x16), (0x3800, 0x00),
    (0x3801, 0x00), (0x3802, 0x00), (0x3803, 0x0C), (0x3804, 0x0C), (0x3805, 0xDF),
    (0x3806, 0x09), (0x3807, 0xA3), (0x3808, 0x06), (0x3809, 0x60), (0x380A, 0x04),
    (0x380B, 0xC8), (0x380C, 0x07), (0x380D, 0x8C), (0x380E, 0x04), (0x380F, 0xDE),
    (0x3810, 0x00), (0x3811, 0x08), (0x3812, 0x00), (0x3813, 0x02), (0x3814, 0x03),
    (0x3815, 0x01), (0x3816, 0x00), (0x3817, 0x00), (0x3818, 0x00), (0x3819, 0x00),
    (0x3820, 0x90), (0x3821, 0x67), (0x382A, 0x03), (0x382B, 0x01), (0x3830, 0x06),
    (0x3836, 0x02), (0x3862, 0x04), (0x3863, 0x08), (0x3CC0, 0x33), (0x3D85, 0x17),
    (0x3D8C, 0x73), (0x3D8D, 0xDE), (0x4001, 0xE0), (0x4003, 0x40), (0x4008, 0x00),
    (0x4009, 0x05), (0x400A, 0x00), (0x400B, 0x84), (0x400F, 0x80), (0x4010, 0xF0),
    (0x4011, 0xFF), (0x4012, 0x02), (0x4013, 0x01), (0x4014, 0x01), (0x4015, 0x01),
    (0x4042, 0x00), (0x4043, 0x80), (0x4044, 0x00), (0x4045, 0x80), (0x4046, 0x00),
    (0x4047, 0x80), (0x4048, 0x00), (0x4049, 0x80), (0x4041, 0x03), (0x404C, 0x20),
    (0x404D, 0x00), (0x404E, 0x20), (0x4203, 0x80), (0x4307, 0x30), (0x4317, 0x00),
    (0x4503, 0x08), (0x4601, 0x80), (0x4800, 0x44), (0x4816, 0x53), (0x481B, 0x58),
    (0x481F, 0x27), (0x4837, 0x16), (0x483C, 0x0F), (0x484B, 0x05), (0x5000, 0x77),
    (0x5001, 0x0A), (0x5004, 0x04), (0x502E, 0x03), (0x5030, 0x41), (0x5795, 0x00),
    (0x5796, 0x10), (0x5797, 0x10), (0x5798, 0x73), (0x5799, 0x73), (0x579A, 0x00),
    (0x579B, 0x28), (0x579C, 0x00), (0x579D, 0x16), (0x579E, 0x06), (0x579F, 0x20),
    (0x57A0, 0x04), (0x57A1, 0xA0), (0x5780, 0x14), (0x5781, 0x0F), (0x5782, 0x44),
    (0x5783, 0x02), (0x5784, 0x01), (0x5785, 0x01), (0x5786, 0x00), (0x5787, 0x04),
    (0x5788, 0x02), (0x5789, 0x0F), (0x578A, 0xFD), (0x578B, 0xF5), (0x578C, 0xF5),
    (0x578D, 0x03), (0x578E, 0x08), (0x578F, 0x0C), (0x5790, 0x08), (0x5791, 0x04),
    (0x5792, 0x00), (0x5793, 0x52), (0x5794, 0xA3), (0x59F8, 0x3D), (0x5A08, 0x02),
    (0x5B00, 0x02), (0x5B01, 0x10), (0x5B02, 0x03), (0x5B03, 0xCF), (0x5B05, 0x6C),
    (0x5E00, 0x00),
)

# OV8856 640x480 binned mode sequence (from begonia ov8856-mipi/vga.regs)
OV8856_VGA_REGS = (
    (0x0100, 0x00), (0x0300, 0x00), (0x0302, 0x3C), (0x0303, 0x01), (0x030B, 0x00),
    (0x030C, 0x00), (0x030D, 0x1E), (0x3501, 0x25), (0x3502, 0xC0), (0x366E, 0x08),
    (0x3714, 0x29), (0x37C2, 0x34), (0x3800, 0x01), (0x3801, 0x50), (0x3802, 0x01),
    (0x3803, 0x10), (0x3804, 0x0B), (0x3805, 0x8F), (0x3806, 0x08), (0x3807, 0x9F),
    (0x3808, 0x02), (0x3809, 0x80), (0x380A, 0x01), (0x380B, 0xE0), (0x380C, 0x07),
    (0x380D, 0x8C), (0x380E, 0x02), (0x380F, 0x6C), (0x3810, 0x00), (0x3811, 0x08),
    (0x3812, 0x00), (0x3813, 0x02), (0x3814, 0x03), (0x3820, 0x90), (0x3821, 0x67),
    (0x382A, 0x07), (0x4009, 0x05), (0x4601, 0x40), (0x4837, 0x16), (0x5795, 0x00),
    (0x5796, 0x10), (0x5797, 0x10), (0x5798, 0x73), (0x5799, 0x73), (0x579B, 0x00),
    (0x579D, 0x00), (0x579E, 0x05), (0x579F, 0xA0), (0x57A0, 0x03), (0x57A1, 0x20),
    (0x0100, 0x01),
)


class I2CMsg(ctypes.Structure):
    _fields_ = [
        ('a', ctypes.c_uint16),
        ('f', ctypes.c_uint16),
        ('l', ctypes.c_uint16),
        ('b', ctypes.c_void_p),
    ]


class I2CRdwrData(ctypes.Structure):
    _fields_ = [
        ('m', ctypes.POINTER(I2CMsg)),
        ('n', ctypes.c_uint32),
    ]


def parse_again(value: str) -> int:
    s = value.strip().lower()
    if s.endswith('x'):
        try:
            raw = int(round(float(s[:-1]) * 128.0))
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f'invalid again multiplier: {value!r}') from exc
    else:
        try:
            raw = int(s, 0)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f'invalid again value: {value!r}') from exc
    if raw < 128 or raw > 2047:
        raise argparse.ArgumentTypeError(f'again {raw} out of range [128, 2047]')
    return raw


def parse_bus(value: str) -> str:
    if value.startswith('/dev/i2c-'):
        return value
    if value.isdigit():
        return f'/dev/i2c-{value}'
    matches = [
        p for p in glob.glob('/sys/class/i2c-dev/i2c-*')
        if os.path.realpath(p + '/device/of_node').endswith(value)
    ]
    if not matches:
        raise argparse.ArgumentTypeError(f'no i2c-dev matching {value!r}')
    return '/dev/' + matches[0].rsplit('/', 1)[1]


def w(blk: str, off: int, val: int) -> None:
    with open(DBG + '/w', 'w') as f:
        f.write(f'{blk} {off:x} {val & 0xffffffff:x}')


def r(blk: str, off: int) -> int:
    with open(DBG + '/r', 'w') as f:
        f.write(f'{blk} {off:x} 1')
    with open(DBG + '/r', 'r') as f:
        return int(f.read().split(':')[1], 16)


def rmw(blk: str, off: int, clr: int = 0, st: int = 0) -> None:
    w(blk, off, (r(blk, off) & ~clr) | st)


def field(blk: str, off: int, hi: int, lo: int, val: int) -> None:
    mask = ((1 << (hi - lo + 1)) - 1) << lo
    rmw(blk, off, mask, (val << lo) & mask)


def sw(fd: int, addr: int, reg: int, val: int) -> None:
    buf = ctypes.create_string_buffer(bytes([reg >> 8, reg & 0xFF, val]), 3)
    msg = (I2CMsg * 1)(I2CMsg(addr, 0, 3, ctypes.addressof(buf)))
    fcntl.ioctl(fd, 0x0707, I2CRdwrData(msg, 1))


def sr(fd: int, addr: int, reg: int) -> int:
    wb = ctypes.create_string_buffer(bytes([reg >> 8, reg & 0xFF]), 2)
    rb = ctypes.create_string_buffer(1)
    msgs = (I2CMsg * 2)(
        I2CMsg(addr, 0, 2, ctypes.addressof(wb)),
        I2CMsg(addr, 1, 1, ctypes.addressof(rb)),
    )
    fcntl.ioctl(fd, 0x0707, I2CRdwrData(msgs, 2))
    return rb.raw[0]


def load_reg_file(path: str):
    regs = []
    with open(path, 'r') as f:
        for line in f:
            parts = line.split()
            if not parts or parts[0].startswith('#'):
                continue
            if parts[0] == 'delay':
                regs.append(('delay', int(parts[1], 0)))
            else:
                regs.append((int(parts[0], 16), int(parts[1], 16)))
    return regs


def apply_table(fd: int, addr: int, regs, skip_stream_on: bool = False) -> int:
    n = 0
    for reg, val in regs:
        if reg == 'delay':
            time.sleep(val / 1000.0)
            continue
        if skip_stream_on and reg == 0x0100 and val == 1:
            continue
        sw(fd, addr, reg, val)
        n += 1
    return n


def power_sensor(mode: str, slot: int, addr: int) -> None:
    if mode == 'none':
        return
    if mode in ('auto', 'sysfs'):
        devs = glob.glob(f'/sys/bus/i2c/drivers/ov8856/*-{addr:04x}')
        if devs:
            with open(devs[0] + '/power/control', 'w') as f:
                f.write('on')
            time.sleep(0.05)
            status = open(devs[0] + '/power/runtime_status').read().strip()
            print(f'sensor power: sysfs {devs[0]} runtime={status}')
            return
        if mode == 'sysfs':
            raise RuntimeError(f'no bound ov8856 device at address 0x{addr:02x}')
    if mode in ('auto', 'probe'):
        if not os.path.exists(PROBE_POWER):
            raise RuntimeError(f'{PROBE_POWER} not found (load yt11-cam-probe or use --power-mode none)')
        with open(PROBE_POWER, 'w') as f:
            f.write(f'{slot} on\n')
        time.sleep(0.05)
        print(f'sensor power: yt11-cam-probe slot {slot} on')


def ensure_apmixed_mipic() -> None:
    try:
        fd = os.open('/dev/mem', os.O_RDWR | os.O_SYNC)
    except OSError as exc:
        print(f'APMIXED check skipped (/dev/mem: {exc.strerror})')
        return
    try:
        m = mmap.mmap(fd, 0x1000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=0x1000C000)
        try:
            cur = struct.unpack_from('<I', m, 0x20)[0]
            if (cur & 0x840) != 0x840:
                struct.pack_into('<I', m, 0x20, cur | 0x840)
                cur = struct.unpack_from('<I', m, 0x20)[0]
                print(f'APMIXED 0x1000c020 = 0x{cur:08x} (forced mipic0/1 26M bits 6,11 on)')
            else:
                print(f'APMIXED 0x1000c020 = 0x{cur:08x} (mipic0/1 26M already on via clk)')
        finally:
            m.close()
    finally:
        os.close(fd)


def setup_phy_seninf(csi_port: int, seninf: int, mux: int, lanes: int, settle: int) -> None:
    ana_a = csi_port * 0x4000
    ana_b = ana_a + 0x1000
    ana_pair = (ana_a, ana_b)
    dphy = csi_port * 0x4000 + 0x2000
    cphy = csi_port * 0x4000 + 0x3000

    # phyA_init
    for a in ana_pair:
        for hi, lo, val in ((2, 0, 4), (6, 4, 4), (10, 8, 4), (14, 12, 4), (19, 16, 8)):
            field('ana', a + 0x4, hi, lo, val)
        for off in (0x18, 0x1C, 0x20):
            for hi, lo, val in ((5, 4, 1), (21, 20, 1), (7, 6, 1), (23, 22, 1)):
                field('ana', a + off, hi, lo, val)
            rmw('ana', a + off, 0, (1 << 2) | (1 << 18))
            field('ana', a + off, 11, 8, 3)
            field('ana', a + off, 27, 24, 3)
        for hi, lo in ((4, 0), (12, 8), (20, 16), (28, 24)):
            field('ana', a + 0x8, hi, lo, 0x10)
        for hi, lo in ((4, 0), (12, 8)):
            field('ana', a + 0xC, hi, lo, 0x10)
        for off in (0x30, 0x3C):
            for hi, lo in ((4, 0), (12, 8), (20, 16)):
                field('ana', a + off, hi, lo, 8)
        rmw('ana', a + 0x28, 0, 1)
        rmw('ana', a + 0x34, 0, 1)
        for off in (0x30, 0x3C):
            field('ana', a + off, 28, 24, 1)

    # dphy_init
    for off in (0x20, 0x24, 0x28, 0x2C):
        field('ana', dphy + off, 23, 16, 0x20)
        field('ana', dphy + off, 15, 8, settle or 4)
        rmw('ana', dphy + off, 0, 1 << 29)

    # setSeninfCsiMipi: CPHY top +0x18 |= 0x10
    rmw('ana', cphy + 0x18, 0, 0x10)

    # seninf_csi2_setting (D-PHY, N lanes)
    csi2 = 0xA00 + 0x1000 * seninf
    csi_en = (1 << lanes) - 1
    rmw('seninf', csi2 + 0x10, 0, 0x100)
    rmw('seninf', csi2 + 0x8, 0x7FF, 0)
    rmw('seninf', csi2 + 0x4, 1, 0)
    rmw('seninf', csi2 + 0xC0, 0, 0x80000000)
    w('seninf', csi2 + 0x0, csi_en)
    w('seninf', csi2 + 0xE0, 0xFFFFFFFF)  # DBG_CTRL: enable packet counters

    # SENINF_TOP_PHY_CTRL_CSIp (0x60 + 4*port): D-PHY
    rmw('seninf', 0x60 + 4 * csi_port, 0x2, 0x1)

    # phyA_setting (4D1C clock on A.L2)
    for a in ana_pair:
        rmw('ana', a + 0x0, 1, 0)
    rmw('ana', ana_pair[0], 0x20 | 0x100, 0x800)
    rmw('ana', ana_pair[1], 0x20 | 0x100 | 0x800, 0)
    for a in ana_pair:
        rmw('ana', a, 0, 0x40 | 0x200 | 0x1000)

    # dphy_setting
    for hi, lo, val in ((18, 16, 0), (10, 8, 1), (2, 0, 2), (14, 12, 3), (22, 20, 4)):
        field('ana', dphy + 0x4, hi, lo, val)
    rmw('ana', dphy + 0x0, 0x2, 0x100 | 0x200 | 0x400 | 0x800 | 0x1)
    rmw('ana', dphy + 0x4, 0, 0x80000000)

    # phyA_power_on
    for a in ana_pair:
        for off in (0x18, 0x1C, 0x20):
            rmw('ana', a + off, 1 | 0x10000, 0)
        rmw('ana', a, 4 | 8, 0)
        time.sleep(0.0003)
        rmw('ana', a, 0, 8)
        time.sleep(0.0001)
        rmw('ana', a, 0, 4)
        time.sleep(0.0001)
        for off in (0x18, 0x1C, 0x20):
            rmw('ana', a + off, 0, 1 | 0x10000)
        time.sleep(0.002)
        print(f'ANA 0x{a:04x}: +0x48 = 0x{r("ana", a + 0x48):08x} (expect & 0x29 == 0x29)')

    # seninf_setting: CSI2_CTRL + SENINF_CTRL
    ctrl = 0x200 + 0x1000 * seninf
    rmw('seninf', ctrl + 0x10, 0, 1)
    rmw('seninf', ctrl + 0x0, 0, 1)

    # TOP_MUX_CTRL_0/1: route seninf -> mux (default mux2 -> cam_mux2 -> CAMSV0)
    top_mux_reg = 0x10 if mux < 4 else 0x14
    top_mux_shift = 8 * (mux % 4)
    rmw('seninf', top_mux_reg, 0xF << top_mux_shift, seninf << top_mux_shift)

    # muxN: MIPI source (8), 1-pixel mode, polarities 0
    mux_base = 0xD00 + 0x1000 * mux
    rmw('seninf', mux_base + 0x4, 0x30F, 0x8)
    rmw('seninf', mux_base + 0x8, 0x30000, 0)
    rmw('seninf', mux_base + 0x0, 0, 0x6)
    rmw('seninf', mux_base + 0x0, 0x6, 0)
    rmw('seninf', mux_base + 0x0, 0, 1)
    w('seninf', mux_base + 0xA8, 1)
    rmw('seninf', 0x410, 0, 0x1F)


def setup_camsv0(phys: int, w_px: int, l_ln: int, pack: int = 12) -> int:
    """Configure CAMSV0 TG + IMGO DMA for a w_px x l_ln RAW10 sensor stream.

    pack selects the IMGO byte layout:
      - 10: true MIPI RAW10 packing, bpl = w*10/8 (PAK=2, TG1_FMT=1). The
        MT6785 with these register values emits 12-bit containers instead
        (see below), so this mode is only for trying HW bit 3 (PAK_SEL) or
        other packer knobs; expect the same 12-bit layout unless they bite.
      - 12 (default): 12-bit containers, 2 px / 3 bytes, sample << 2,
        bpl = w*12/8. This matches what the hardware writes with
        FMT_SEL=0x101 / PAK=2 (measured 2026-11-16, T9-RAWTOOLS.md).
    """
    if pack not in (10, 12):
        raise ValueError(f'pack must be 10 or 12, got {pack}')
    bpl = w_px * pack // 8
    fmt_sel = 0x101 if pack == 10 else 0x102  # TG1_FMT: 1=RAW10, 2=RAW12
    pak = 2 if pack == 10 else 1              # PAK mode: 2=RAW10, 1=RAW12
    for off, val in ((0x230, 0), (0x234, 0), (0x510, 0x40000000), (0x110, 0)):
        w('camsv', off, val)
    for val in (4, 0, 1):
        w('camsv', 0x520, val)
    time.sleep(0.05)
    w('camsv', 0x520, 0)

    for off, val in (
        (0x238, w_px << 16),
        (0x23C, l_ln << 16),
        (0x20, phys),
        (0x30, bpl - 1),
        (0x34, l_ln - 1),
        (0x38, bpl),
        (0x40, 0x20002),
        (0x44, 0x20002),
        (0x514, fmt_sel),
        (0x54C, pak),
        (0x110, 0x8000),
        (0x530, 0x8005),
        (0x510, 0x40000015),
        (0x518, 0xFFFFFFFF),
        (0x400, 1),
        (0x234, 1),
        (0x230, 0x10001),
    ):
        w('camsv', off, val)
    return bpl


def arm_one_frame() -> None:
    """Re-arm FBC for one frame: FBC_EN then RCNT_INC (begonia cap1.sh)."""
    w('camsv', 0x110, 0x8000)
    w('camsv', 0x110, 0x8001)


def main() -> int:
    ap = argparse.ArgumentParser(
        description='Capture a raw frame from OV8856 over MIPI CSI-2 -> SENINF -> CAMSV0.'
    )
    ap.add_argument('--csi-port', type=int, choices=(0, 1, 2), default=0,
                    help='MT6785 MIPI RX CSI port index (0, 1, or 2; default 0)')
    ap.add_argument('--seninf', type=int, choices=range(5), default=None,
                    help='SENINF block index 0..4 (default from HAL map: 0->0, 1->2, 2->4)')
    ap.add_argument('--mux', type=int, choices=range(6), default=2,
                    help='SENINF MUX / CAM_MUX index (default 2 = CAMSV0)')
    ap.add_argument('--lanes', type=int, choices=(1, 2, 4), default=2,
                    help='MIPI data lane count (1, 2, or 4; default 2)')
    ap.add_argument('--i2c-bus', type=parse_bus, default='/dev/i2c-2',
                    help='I2C bus number, /dev/i2c-N, or OF node suffix (default /dev/i2c-2)')
    ap.add_argument('--i2c-addr', type=lambda x: int(x, 0), default=0x36,
                    help='OV8856 7-bit I2C address (default 0x36; YT-J706F also answers at 0x21)')
    ap.add_argument('--slot', type=int, choices=(0, 1), default=0,
                    help='yt11-cam-probe slot when --power-mode=probe/auto (default 0)')
    ap.add_argument('--power-mode', choices=('auto', 'probe', 'sysfs', 'none'), default='auto',
                    help='How to power the sensor before I2C config (default auto)')
    ap.add_argument('--testpat', action='store_true', help='Enable OV8856 internal color bars')
    ap.add_argument('--exposure', type=lambda x: int(x, 0), default=None,
                    help='OV8856 exposure in lines (0x3500..0x3502) applied before stream-on')
    ap.add_argument('--again', type=parse_again, default=None,
                    help='OV8856 analogue gain (128..2047 or Nx, 0x3508..0x3509) applied before stream-on')
    ap.add_argument('--frames', type=int, default=1,
                    help='Keep streaming for N frames and save the Nth frame (default 1)')
    ap.add_argument('--pack', type=int, choices=(10, 12), default=12,
                    help='IMGO byte packing: 10 = MIPI RAW10 (w*10/8 B/line), '
                         '12 = 12-bit containers w*12/8 B/line (what the HW '
                         'emits; default 12)')
    ap.add_argument('--settle', type=lambda x: int(x, 0), default=15,
                    help='DPHY HS-settle register value (default 15)')
    ap.add_argument('--w', type=int, default=640, help='Frame width in pixels (default 640)')
    ap.add_argument('--l', type=int, default=480, help='Frame height in lines (default 480)')
    ap.add_argument('--stream-first', action='store_true',
                    help='Start sensor streaming before resetting/arming CAMSV0')
    ap.add_argument('--init-regs', help='Optional path to override OV8856 init register table')
    ap.add_argument('--vga-regs', help='Optional path to override OV8856 mode register table')
    ap.add_argument('--out', default='/tmp/ov.raw', help='Output raw frame path (default /tmp/ov.raw)')
    ap.add_argument('--png', help='Optional PNG output path (converted via raw2png.py)')
    args = ap.parse_args()

    if args.frames < 1:
        ap.error('--frames must be >= 1')

    seninf = args.seninf if args.seninf is not None else CSI_TO_SENINF[args.csi_port]
    print(f'config: csi_port={args.csi_port} seninf={seninf} mux={args.mux} '
          f'lanes={args.lanes} i2c={args.i2c_bus}@0x{args.i2c_addr:02x} {args.w}x{args.l}')

    if not os.path.isdir(DBG):
        print(f'error: {DBG} not found (modprobe mt6785-camsv-tm)', file=sys.stderr)
        return 1

    # 1. Sensor power + register configuration
    power_sensor(args.power_mode, args.slot, args.i2c_addr)
    fd = os.open(args.i2c_bus, os.O_RDWR)
    try:
        chip_id = (sr(fd, args.i2c_addr, 0x300B) << 8) | sr(fd, args.i2c_addr, 0x300C)
        print(f'sensor ID: 0x{chip_id:04x}')
        init_tbl = load_reg_file(args.init_regs) if args.init_regs else OV8856_INIT_REGS
        vga_tbl = load_reg_file(args.vga_regs) if args.vga_regs else OV8856_VGA_REGS
        print(f'init: {apply_table(fd, args.i2c_addr, init_tbl)} writes')
        if args.lanes != 2:
            sw(fd, args.i2c_addr, 0x3018, OV8856_LANE_REG[args.lanes])
            print(f'ov8856 0x3018 = 0x{OV8856_LANE_REG[args.lanes]:02x} ({args.lanes} lanes)')
        print(f'vga : {apply_table(fd, args.i2c_addr, vga_tbl, skip_stream_on=True)} writes (stream off)')
        if args.testpat:
            for reg, val in ((0x5000, 0x57), (0x5001, 0x02), (0x5E00, 0x80)):
                sw(fd, args.i2c_addr, reg, val)
            print('sensor test pattern: color bars enabled')
        if args.exposure is not None:
            exp20 = (args.exposure << 4) & 0xFFFFF
            sw(fd, args.i2c_addr, 0x3500, (exp20 >> 16) & 0x0F)
            sw(fd, args.i2c_addr, 0x3501, (exp20 >> 8) & 0xFF)
            sw(fd, args.i2c_addr, 0x3502, exp20 & 0xFF)
            print(f'ov8856 exposure = {args.exposure} lines (0x{exp20:05x})')
        if args.again is not None:
            sw(fd, args.i2c_addr, 0x3508, (args.again >> 8) & 0xFF)
            sw(fd, args.i2c_addr, 0x3509, args.again & 0xFF)
            print(f'ov8856 again = {args.again} (0x{args.again:04x}, {args.again / 128.0:.2f}x)')

        # 2. CAM power domain, LARB bypass, CMA buffer
        with open(DBG + '/power', 'w') as f:
            f.write('1')
        subprocess.check_call([sys.executable, os.path.join(HERE, 'larb-bypass.py')])

        bpl = args.w * args.pack // 8
        need_buf = max(0x200000, bpl * args.l)
        cur_sz = int(open(DBG + '/buf').read().split()[3], 16)
        if cur_sz < need_buf:
            with open(DBG + '/buf', 'w') as f:
                f.write(f'0x{need_buf:x}')
        phys = int(open(DBG + '/buf').read().split()[1], 16)
        with open(DBG + '/fill', 'w') as f:
            f.write('0xa5')

        # 3. APMIXED + MIPI RX PHY + CSI2 + SENINF
        ensure_apmixed_mipic()
        setup_phy_seninf(args.csi_port, seninf, args.mux, args.lanes, args.settle)

        # 4. CAMSV0 + sensor streaming
        if args.stream_first:
            sw(fd, args.i2c_addr, 0x0100, 1)
            time.sleep(0.1)
            setup_camsv0(phys, args.w, args.l, args.pack)
        else:
            setup_camsv0(phys, args.w, args.l, args.pack)
            sw(fd, args.i2c_addr, 0x0100, 1)
    finally:
        os.close(fd)

    print(f'IMGO: pack={args.pack}, {bpl} bytes/line ({args.w} px), '
          f'frame = {bpl * args.l} bytes')
    time.sleep(0.3)
    # Multi-frame: the single-frame path arms FBC once (FBC_EN | RCNT_INC) and
    # reads the buffer afterwards. Re-writing RCNT_INC alone on a running FBC
    # does not latch another frame (the Nth-frame counter never advances), so
    # for N > 1 re-arm the full FBC sequence per frame; without hardware to
    # tell DMA-done from INT_STATUS, fall back to fixed frame waits.
    for frame_idx in range(args.frames):
        last = frame_idx == args.frames - 1
        if last:
            with open(DBG + '/fill', 'w') as f:
                f.write('0xa5')
        arm_one_frame()
        time.sleep(0.3 if last else 0.1)

    # 5. Status report + frame save
    csi2 = 0xA00 + 0x1000 * seninf
    dphy = args.csi_port * 0x4000 + 0x2000
    mux_base = 0xD00 + 0x1000 * args.mux
    chk_res_off = 0x400 + 0x108 + 0x10 * args.mux

    print('CSI2 IRQ %08x LINE_FRAME %08x PKT %08x SHORT %08x PKT_CNT %08x' % tuple(
        r('seninf', csi2 + o) for o in (0xC8, 0xD0, 0xD4, 0xD8, 0xDC)))
    print('DPHY [0x00]=%08x [0x04]=%08x [0x30]=%08x' % (
        r('ana', dphy), r('ana', dphy + 0x4), r('ana', dphy + 0x30)))
    print('MUX%d: SIZE %08x PIX_CNT %08x IRQ %08x MON H %d V %d' % (
        args.mux, r('seninf', mux_base + 0x30), r('seninf', mux_base + 0xA4),
        r('seninf', mux_base + 0x18), r('seninf', mux_base + 0xB0), r('seninf', mux_base + 0xB8)))
    print('CAM_MUX%d CHK_RES %08x' % (args.mux, r('seninf', chk_res_off)))
    print('CAMSV0: INT %08x TG_FRMSIZE %08x FBC_CTL2 %08x' % (
        r('camsv', 0x51C), r('camsv', 0x268), r('camsv', 0x114)))

    frame_bytes = bpl * args.l
    with open(DBG + '/frame', 'rb') as f:
        data = f.read(frame_bytes + 4096)
    idx = [i for i, b in enumerate(data) if b != 0xA5]
    print('frame: %d bytes written (last+1 %d, expected %d)' % (
        len(idx), (max(idx) + 1) if idx else 0, frame_bytes))
    with open(args.out, 'wb') as f:
        f.write(data[:frame_bytes])
    os.chmod(args.out, 0o644)
    print(f'saved {args.out}')

    if args.png:
        subprocess.check_call([
            sys.executable, os.path.join(HERE, 'raw2png.py'),
            args.out, str(args.w), str(args.l), '--pack', str(args.pack),
            str(bpl), args.png,
        ])
    return 0


if __name__ == '__main__':
    sys.exit(main())
