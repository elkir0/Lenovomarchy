#!/usr/bin/env python3
"""Read/write OV8856 exposure, gain, test pattern, and flip/mirror via /dev/i2c-N.

Uses standard Linux I2C_RDWR ioctls (stdlib ctypes + fcntl, matching cam-id.py).
Register map matches src/mt6785-mainline/drivers/media/i2c/ov8856.c and the
OmniVision OV8856 datasheet.

Also provides --auto FILE.raw to measure a captured MIPI/CAMSV RAW10 frame's
mean signal level above black level and suggest (or --apply) updated exposure
and gains.
"""

import argparse
import ctypes
import fcntl
import glob
import os
import sys

I2C_RDWR = 0x0707
I2C_M_RD = 0x0001

REG_CHIP_ID_H = 0x300A
REG_CHIP_ID_M = 0x300B
REG_CHIP_ID_L = 0x300C

REG_EXPOSURE = 0x3500       # 20-bit [19:0] across 0x3500..0x3502, 4 LSBs fractional
REG_AEC_MANUAL = 0x3503     # 0x08 = manual AEC/AGC (real gain format)
REG_ANALOG_GAIN = 0x3508    # 16-bit BE (0x3508..0x3509), 128 = 1.0x, max 2047
REG_DIGITAL_GAIN = 0x350A   # 16-bit BE (0x350A..0x350B), 1024 = 1.0x, max 4095

REG_FLIP_OPT_1 = 0x376B     # vflip bits 1, 2
REG_HTS = 0x380C            # 16-bit BE
REG_VTS = 0x380E            # 16-bit BE
REG_ISP_Y_OFF = 0x3812      # 16-bit BE (0x3812..0x3813)
REG_FORMAT1 = 0x3820        # vflip bits 1, 2, 6 (0x46)
REG_FORMAT2 = 0x3821        # hflip bits 1, 2, 6 (0x46, cleared on hflip=1)

REG_ISP_CTRL0 = 0x5000      # bit 5 = LENC
REG_ISP_CTRL1 = 0x5001      # bit 2 = vflip opt2, bit 3 = AWB/BLC
REG_MIRROR_OPT_1 = 0x5004   # bit 2 = hflip opt (cleared on hflip=1)
REG_FLIP_OPT_3 = 0x502E     # bits 0, 1 (cleared on vflip=1)
REG_TEST_PATTERN = 0x5E00   # bit 7 = enable, bits [3:2] = bar mode 0..3

EXPOSURE_MIN = 6
EXPOSURE_MAX_MARGIN = 6
ANAL_GAIN_MIN = 128
ANAL_GAIN_MAX = 2047
DGTL_GAIN_DEFAULT = 1024
DGTL_GAIN_MAX = 4095

_LSB_LUT0 = bytes(b & 0x03 for b in range(256))
_LSB_LUT1 = bytes((b >> 2) & 0x03 for b in range(256))
_LSB_LUT2 = bytes((b >> 4) & 0x03 for b in range(256))
_LSB_LUT3 = bytes((b >> 6) & 0x03 for b in range(256))


class I2CMsg(ctypes.Structure):
    _fields_ = [
        ('addr', ctypes.c_uint16),
        ('flags', ctypes.c_uint16),
        ('len', ctypes.c_uint16),
        ('buf', ctypes.c_void_p),
    ]


class I2CRdwrData(ctypes.Structure):
    _fields_ = [
        ('msgs', ctypes.POINTER(I2CMsg)),
        ('nmsgs', ctypes.c_uint32),
    ]


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


def parse_gain(value: str, unit: int, lo: int, hi: int, name: str) -> int:
    s = value.strip().lower()
    if s.endswith('x'):
        try:
            mult = float(s[:-1])
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f'invalid {name} multiplier: {value!r}') from exc
        raw = int(round(mult * unit))
    else:
        try:
            raw = int(s, 0)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f'invalid {name} value: {value!r}') from exc
    if raw < lo or raw > hi:
        raise argparse.ArgumentTypeError(f'{name} {raw} out of range [{lo}, {hi}]')
    return raw


def i2c_read(fd: int, addr: int, reg: int, nbytes: int = 1) -> int:
    wb = ctypes.create_string_buffer(bytes([reg >> 8, reg & 0xFF]), 2)
    rb = ctypes.create_string_buffer(nbytes)
    msgs = (I2CMsg * 2)(
        I2CMsg(addr, 0, 2, ctypes.addressof(wb)),
        I2CMsg(addr, I2C_M_RD, nbytes, ctypes.addressof(rb)),
    )
    fcntl.ioctl(fd, I2C_RDWR, I2CRdwrData(msgs, 2))
    return int.from_bytes(rb.raw, 'big')


def i2c_write(fd: int, addr: int, reg: int, val: int, nbytes: int = 1) -> None:
    payload = bytes([reg >> 8, reg & 0xFF]) + val.to_bytes(nbytes, 'big')
    wb = ctypes.create_string_buffer(payload, len(payload))
    msg = (I2CMsg * 1)(I2CMsg(addr, 0, len(payload), ctypes.addressof(wb)))
    fcntl.ioctl(fd, I2C_RDWR, I2CRdwrData(msg, 1))


def i2c_rmw(fd: int, addr: int, reg: int, clr: int, st: int) -> int:
    cur = i2c_read(fd, addr, reg, 1)
    nxt = (cur & ~clr) | st
    i2c_write(fd, addr, reg, nxt, 1)
    return nxt


def read_state(fd: int, addr: int) -> dict:
    chip_id = i2c_read(fd, addr, REG_CHIP_ID_H, 3)
    exp20 = i2c_read(fd, addr, REG_EXPOSURE, 3) & 0xFFFFF
    aec_manual = i2c_read(fd, addr, REG_AEC_MANUAL, 1)
    again = i2c_read(fd, addr, REG_ANALOG_GAIN, 2)
    dgain = i2c_read(fd, addr, REG_DIGITAL_GAIN, 2)
    hts = i2c_read(fd, addr, REG_HTS, 2)
    vts = i2c_read(fd, addr, REG_VTS, 2)
    y_off = i2c_read(fd, addr, REG_ISP_Y_OFF, 2)
    fmt1 = i2c_read(fd, addr, REG_FORMAT1, 1)
    fmt2 = i2c_read(fd, addr, REG_FORMAT2, 1)
    r5000 = i2c_read(fd, addr, REG_ISP_CTRL0, 1)
    r5001 = i2c_read(fd, addr, REG_ISP_CTRL1, 1)
    r5004 = i2c_read(fd, addr, REG_MIRROR_OPT_1, 1)
    r502e = i2c_read(fd, addr, REG_FLIP_OPT_3, 1)
    r376b = i2c_read(fd, addr, REG_FLIP_OPT_1, 1)
    testpat = i2c_read(fd, addr, REG_TEST_PATTERN, 1)
    return {
        'chip_id': chip_id,
        'exp_raw20': exp20,
        'exposure': exp20 >> 4,
        'aec_manual': aec_manual,
        'again': again,
        'dgain': dgain,
        'hts': hts,
        'vts': vts,
        'y_off': y_off,
        'fmt1': fmt1,
        'fmt2': fmt2,
        'r5000': r5000,
        'r5001': r5001,
        'r5004': r5004,
        'r502e': r502e,
        'r376b': r376b,
        'hflip': 0 if (fmt2 & 0x46) == 0x46 else 1,
        'vflip': 1 if (fmt1 & 0x46) == 0x46 else 0,
        'testpat': testpat,
    }


def print_state(st: dict, prefix: str = '') -> None:
    tp = st['testpat']
    if tp & 0x80:
        tp_desc = f'on (mode {((tp >> 2) & 0x03) + 1}, 0x{tp:02x})'
    else:
        tp_desc = f'off (0x{tp:02x})'
    print(f"{prefix}chip_id : 0x{st['chip_id']:06x} (expect 0x00885a)")
    print(
        f"{prefix}exposure: {st['exposure']} lines "
        f"(0x3500..0x3502 = 0x{st['exp_raw20']:05x}, 0x3503 = 0x{st['aec_manual']:02x})"
    )
    print(
        f"{prefix}again   : {st['again']} (0x{st['again']:04x}, {st['again'] / 128.0:.2f}x) "
        f"[0x3508..0x3509]"
    )
    print(
        f"{prefix}dgain   : {st['dgain']} (0x{st['dgain']:04x}, {st['dgain'] / 1024.0:.2f}x) "
        f"[0x350A..0x350B]"
    )
    print(
        f"{prefix}timing  : HTS={st['hts']} (0x{st['hts']:04x}) "
        f"VTS={st['vts']} (0x{st['vts']:04x}) y_off=0x{st['y_off']:04x}"
    )
    print(
        f"{prefix}orient  : hflip={st['hflip']} (0x3821=0x{st['fmt2']:02x}, 0x5004=0x{st['r5004']:02x}) "
        f"vflip={st['vflip']} (0x3820=0x{st['fmt1']:02x}, 0x376b=0x{st['r376b']:02x}, "
        f"0x5001=0x{st['r5001']:02x}, 0x502e=0x{st['r502e']:02x})"
    )
    print(f"{prefix}testpat : {tp_desc} (0x5000=0x{st['r5000']:02x}, 0x5001=0x{st['r5001']:02x})")


def set_exposure(fd: int, addr: int, lines: int, vts: int | None = None) -> int:
    if vts is not None and vts > EXPOSURE_MAX_MARGIN + EXPOSURE_MIN:
        max_exp = vts - EXPOSURE_MAX_MARGIN
        if lines > max_exp:
            print(f'warning: clamping exposure {lines} to VTS-6 = {max_exp}', file=sys.stderr)
            lines = max_exp
    lines = max(EXPOSURE_MIN, min(0xFFFF, lines))
    i2c_write(fd, addr, REG_EXPOSURE, (lines << 4) & 0xFFFFF, 3)
    return lines


def set_again(fd: int, addr: int, raw: int) -> None:
    raw = max(ANAL_GAIN_MIN, min(ANAL_GAIN_MAX, raw))
    i2c_write(fd, addr, REG_ANALOG_GAIN, raw, 2)


def set_dgain(fd: int, addr: int, raw: int) -> None:
    raw = max(0, min(DGTL_GAIN_MAX, raw))
    i2c_write(fd, addr, REG_DIGITAL_GAIN, raw, 2)


def set_test_pattern(fd: int, addr: int, mode: int) -> None:
    if mode == 0:
        i2c_rmw(fd, addr, REG_ISP_CTRL0, 0x00, 0x20)
        i2c_rmw(fd, addr, REG_ISP_CTRL1, 0x00, 0x08)
        i2c_write(fd, addr, REG_TEST_PATTERN, 0x00, 1)
    else:
        val = (((mode - 1) & 0x03) << 2) | 0x80
        i2c_rmw(fd, addr, REG_ISP_CTRL0, 0x20, 0x00)
        i2c_rmw(fd, addr, REG_ISP_CTRL1, 0x08, 0x00)
        i2c_write(fd, addr, REG_TEST_PATTERN, val, 1)


def set_hflip(fd: int, addr: int, enable: int) -> None:
    # Matches ov8856_set_ctrl_hflip() in mainline ov8856.c
    if enable:
        i2c_rmw(fd, addr, REG_MIRROR_OPT_1, 0x04, 0x00)
        i2c_rmw(fd, addr, REG_FORMAT2, 0x46, 0x00)
    else:
        i2c_rmw(fd, addr, REG_MIRROR_OPT_1, 0x00, 0x04)
        i2c_rmw(fd, addr, REG_FORMAT2, 0x00, 0x46)


def set_vflip(fd: int, addr: int, enable: int) -> None:
    # Matches ov8856_set_ctrl_vflip() in mainline ov8856.c
    if enable:
        i2c_rmw(fd, addr, REG_FLIP_OPT_1, 0x00, 0x06)
        i2c_rmw(fd, addr, REG_FLIP_OPT_2, 0x00, 0x04)
        i2c_rmw(fd, addr, REG_FLIP_OPT_3, 0x03, 0x00)
        i2c_rmw(fd, addr, REG_FORMAT1, 0x46, 0x00)
    else:
        i2c_rmw(fd, addr, REG_FLIP_OPT_1, 0x06, 0x00)
        i2c_rmw(fd, addr, REG_FLIP_OPT_2, 0x04, 0x00)
        i2c_rmw(fd, addr, REG_FLIP_OPT_3, 0x00, 0x03)
        i2c_rmw(fd, addr, REG_FORMAT1, 0x00, 0x46)


def measure_raw10_frame(
    path: str, width: int, height: int, stride: int | None, black_level: int
) -> dict:
    bpl = (width * 10 + 7) // 8
    if stride is None:
        stride = bpl
    with open(path, 'rb') as f:
        data = f.read()

    needed = (height - 1) * stride + bpl
    if len(data) < needed:
        print(
            f'warning: {path} is {len(data)} bytes (< expected {needed}), padding with 0',
            file=sys.stderr,
        )
        data = data + b'\x00' * (needed - len(data))

    if stride == bpl and (width & 3) == 0:
        frame = data[: bpl * height]
    else:
        frame = b''.join(data[y * stride : y * stride + bpl] for y in range(height))

    if (width & 3) == 0:
        b0 = frame[0::5]
        b1 = frame[1::5]
        b2 = frame[2::5]
        b3 = frame[3::5]
        b4 = frame[4::5]
        l0 = b4.translate(_LSB_LUT0)
        l1 = b4.translate(_LSB_LUT1)
        l2 = b4.translate(_LSB_LUT2)
        l3 = b4.translate(_LSB_LUT3)
        npix = len(b0) * 4

        buf = bytearray(npix * 2)
        buf[0::8] = b0
        buf[1::8] = l0
        buf[2::8] = b1
        buf[3::8] = l1
        buf[4::8] = b2
        buf[5::8] = l2
        buf[6::8] = b3
        buf[7::8] = l3
        mv = memoryview(buf).cast('H')

        if sys.byteorder == 'little':
            raw_tbl = tuple(((i & 0xFF) << 2) | (i >> 8) for i in range(1024))
        else:
            raw_tbl = tuple(((i >> 8) << 2) | (i & 0xFF) for i in range(1024))
        blc_tbl = tuple(max(0, v - black_level) for v in raw_tbl)

        raw_mean = (
            (sum(b0) + sum(b1) + sum(b2) + sum(b3)) * 4
            + sum(l0) + sum(l1) + sum(l2) + sum(l3)
        ) / npix
        blc_mean = sum(map(blc_tbl.__getitem__, mv)) / npix
        raw_min = min(map(raw_tbl.__getitem__, mv))
        raw_max = max(map(raw_tbl.__getitem__, mv))
        clipped = sum(1 for v in map(raw_tbl.__getitem__, mv) if v >= 1020)
    else:
        vals = []
        for y in range(height):
            line = data[y * stride : y * stride + bpl]
            px = 0
            for g in range(len(line) // 5):
                base = g * 5
                b4 = line[base + 4]
                for k in range(4):
                    if px >= width:
                        break
                    vals.append((line[base + k] << 2) | ((b4 >> (2 * k)) & 0x03))
                    px += 1
        npix = len(vals)
        raw_mean = sum(vals) / npix
        blc_mean = sum(max(0, v - black_level) for v in vals) / npix
        raw_min = min(vals)
        raw_max = max(vals)
        clipped = sum(1 for v in vals if v >= 1020)

    return {
        'pixels': npix,
        'raw_mean': raw_mean,
        'blc_mean': blc_mean,
        'raw_min': raw_min,
        'raw_max': raw_max,
        'clipped_pct': 100.0 * clipped / npix if npix else 0.0,
    }


def suggest_exposure(
    blc_mean: float,
    target: float,
    cur_exp: int,
    cur_again: int,
    cur_dgain: int,
    vts: int,
) -> tuple[int, int, int, float]:
    max_exp = max(EXPOSURE_MIN, vts - EXPOSURE_MAX_MARGIN)
    effective_mean = max(1.0, blc_mean)
    mult = target / effective_mean
    total_cur = max(1.0, float(cur_exp)) * (cur_again / 128.0) * (cur_dgain / 1024.0)
    total_new = total_cur * mult

    # Priority: exposure up to max_exp -> analogue gain -> digital gain
    new_exp = max(EXPOSURE_MIN, min(max_exp, int(round(total_new))))
    rem_after_exp = total_new / new_exp
    new_again = max(ANAL_GAIN_MIN, min(ANAL_GAIN_MAX, int(round(rem_after_exp * 128.0))))
    if new_again == ANAL_GAIN_MAX and total_new > new_exp * (new_again / 128.0):
        rem_after_again = total_new / (new_exp * (new_again / 128.0))
        new_dgain = max(DGTL_GAIN_DEFAULT, min(DGTL_GAIN_MAX, int(round(rem_after_again * 1024.0))))
    else:
        new_dgain = DGTL_GAIN_DEFAULT
    return new_exp, new_again, new_dgain, mult


def _parse_testpat(val: str) -> int:
    s = val.strip().lower()
    if s in ('off', '0'):
        return 0
    if s in ('bars', '1'):
        return 1
    if s in ('2', '3', '4'):
        return int(s)
    raise argparse.ArgumentTypeError(f'invalid test pattern {val!r} (expected off/0, 1/bars, 2, 3, 4)')


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description='Read/write OV8856 exposure, gains, test pattern, and flip/mirror over /dev/i2c-N.'
    )
    ap.add_argument(
        '--i2c-bus', '--bus', '-b',
        type=parse_bus,
        default='/dev/i2c-2',
        help='I2C bus number, /dev/i2c-N, or OF node suffix (default /dev/i2c-2)',
    )
    ap.add_argument(
        '--i2c-addr', '--addr', '-a',
        type=lambda x: int(x, 0),
        default=0x36,
        help='OV8856 7-bit I2C address (default 0x36)',
    )
    ap.add_argument('--exposure', type=lambda x: int(x, 0), help='Exposure in lines (writes 0x3500..0x3502 as lines<<4)')
    ap.add_argument('--again', help='Analogue gain: raw 128..2047 (128=1x) or Nx (e.g. 4x)')
    ap.add_argument('--dgain', help='Digital gain: raw 0..4095 (1024=1x) or Nx (e.g. 2x)')
    ap.add_argument('--vts', type=lambda x: int(x, 0), help='Vertical total size 0x380E..0x380F (lines)')
    ap.add_argument('--testpat', type=_parse_testpat, help='Test pattern: off/0, 1/bars, 2, 3, 4')
    ap.add_argument('--hflip', type=int, choices=(0, 1), help='Horizontal mirror (0 or 1)')
    ap.add_argument('--vflip', type=int, choices=(0, 1), help='Vertical flip (0 or 1)')

    ap.add_argument('--auto', metavar='FILE.raw', help='Analyze RAW10 file and suggest exposure/gain')
    ap.add_argument('--apply', action='store_true', help='Apply --auto suggested exposure/gain over I2C')
    ap.add_argument('--w', type=int, default=640, help='Frame width for --auto (default 640)')
    ap.add_argument('--l', type=int, default=480, help='Frame height for --auto (default 480)')
    ap.add_argument('--stride', type=lambda x: int(x, 0), default=None, help='Line stride for --auto')
    ap.add_argument('--black-level', type=int, default=64, help='10-bit black level for --auto (default 64)')
    ap.add_argument('--target', type=float, default=192.0, help='Target 10-bit mean above black level for --auto (default 192)')
    ap.add_argument('--cur-exposure', type=int, default=None, help='Override current exposure (lines) for offline --auto')
    ap.add_argument('--cur-again', default=None, help='Override current again for offline --auto')
    ap.add_argument('--cur-dgain', default=None, help='Override current dgain for offline --auto')
    ap.add_argument('--cur-vts', type=int, default=None, help='Override current VTS for offline --auto')
    args = ap.parse_args(argv)

    again_val = parse_gain(args.again, 128, ANAL_GAIN_MIN, ANAL_GAIN_MAX, 'again') if args.again is not None else None
    dgain_val = parse_gain(args.dgain, 1024, 0, DGTL_GAIN_MAX, 'dgain') if args.dgain is not None else None

    if args.auto:
        stats = measure_raw10_frame(args.auto, args.w, args.l, args.stride, args.black_level)
        print(
            f"frame {args.auto} ({args.w}x{args.l}, blc={args.black_level}): "
            f"raw_mean={stats['raw_mean']:.2f} blc_mean={stats['blc_mean']:.2f} "
            f"min={stats['raw_min']} max={stats['raw_max']} clipped={stats['clipped_pct']:.2f}%"
        )

        st = None
        if args.apply or (
            args.cur_exposure is None or args.cur_again is None or args.cur_dgain is None or args.cur_vts is None
        ):
            try:
                fd = os.open(args.i2c_bus, os.O_RDWR)
                try:
                    st = read_state(fd, args.i2c_addr)
                finally:
                    os.close(fd)
            except OSError as exc:
                if args.apply:
                    print(f'error: cannot open {args.i2c_bus}: {exc.strerror}', file=sys.stderr)
                    return 1

        cur_exp = args.cur_exposure if args.cur_exposure is not None else (st['exposure'] if st else 604)
        cur_again = (
            parse_gain(args.cur_again, 128, ANAL_GAIN_MIN, ANAL_GAIN_MAX, 'cur-again')
            if args.cur_again is not None
            else (st['again'] if st else 384)
        )
        cur_dgain = (
            parse_gain(args.cur_dgain, 1024, 0, DGTL_GAIN_MAX, 'cur-dgain')
            if args.cur_dgain is not None
            else (st['dgain'] if st else DGTL_GAIN_DEFAULT)
        )
        cur_vts = args.cur_vts if args.cur_vts is not None else (st['vts'] if st else 620)

        new_exp, new_again, new_dgain, mult = suggest_exposure(
            stats['blc_mean'], args.target, cur_exp, cur_again, cur_dgain, cur_vts
        )
        print(
            f'current : exposure={cur_exp} again={cur_again} ({cur_again / 128.0:.2f}x) '
            f'dgain={cur_dgain} ({cur_dgain / 1024.0:.2f}x) vts={cur_vts}'
        )
        print(
            f'suggest : target={args.target:.1f} mult={mult:.2f}x -> '
            f'--exposure {new_exp} --again {new_again} ({new_again / 128.0:.2f}x) '
            f'--dgain {new_dgain} ({new_dgain / 1024.0:.2f}x)'
        )
        if not args.apply:
            return 0

        fd = os.open(args.i2c_bus, os.O_RDWR)
        try:
            set_exposure(fd, args.i2c_addr, new_exp, cur_vts)
            set_again(fd, args.i2c_addr, new_again)
            set_dgain(fd, args.i2c_addr, new_dgain)
            print('applied suggested settings; readback:')
            print_state(read_state(fd, args.i2c_addr), prefix='  ')
        finally:
            os.close(fd)
        return 0

    try:
        fd = os.open(args.i2c_bus, os.O_RDWR)
    except OSError as exc:
        print(f'error: cannot open {args.i2c_bus}: {exc.strerror}', file=sys.stderr)
        return 1

    try:
        wrote = False
        if args.vts is not None:
            i2c_write(fd, args.i2c_addr, REG_VTS, args.vts & 0x7FFF, 2)
            wrote = True
        if args.exposure is not None:
            cur_vts = i2c_read(fd, args.i2c_addr, REG_VTS, 2)
            set_exposure(fd, args.i2c_addr, args.exposure, cur_vts)
            wrote = True
        if again_val is not None:
            set_again(fd, args.i2c_addr, again_val)
            wrote = True
        if dgain_val is not None:
            set_dgain(fd, args.i2c_addr, dgain_val)
            wrote = True
        if args.testpat is not None:
            set_test_pattern(fd, args.i2c_addr, args.testpat)
            wrote = True
        if args.hflip is not None:
            set_hflip(fd, args.i2c_addr, args.hflip)
            wrote = True
        if args.vflip is not None:
            set_vflip(fd, args.i2c_addr, args.vflip)
            wrote = True

        st = read_state(fd, args.i2c_addr)
        if wrote:
            print(f'updated {args.i2c_bus}@0x{args.i2c_addr:02x}:')
        else:
            print(f'status {args.i2c_bus}@0x{args.i2c_addr:02x}:')
        print_state(st, prefix='  ')
    finally:
        os.close(fd)

    return 0


if __name__ == '__main__':
    sys.exit(main())
