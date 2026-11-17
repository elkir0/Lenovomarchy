#!/usr/bin/env python3
"""Scan an I2C bus and read camera sensor chip IDs (read-only).

Runs on the tablet against /dev/i2c-N using standard Linux I2C_RDWR ioctls
with no third-party Python dependencies. Power one camera slot via
/sys/kernel/debug/yt11-cam/power before running.
"""

import argparse
import ctypes
import errno
import fcntl
import os
import sys

I2C_RDWR = 0x0707
I2C_M_RD = 0x0001

SCAN_START = 0x08
SCAN_END = 0x77

# Known candidate 7-bit sensor addresses from YT-J706F DT and begonia NOTES.md
CANDIDATE_ADDRS = (0x10, 0x17, 0x1a, 0x20, 0x2d, 0x36, 0x37, 0x3c, 0x3d, 0x56, 0x5a)

# Auxiliary devices on camera buses (VCM actuators, calibration EEPROMs)
AUX_HINTS = {
    0x0c: 'VCM actuator',
    0x18: 'VCM actuator',
    **{a: 'calibration EEPROM' for a in range(0x50, 0x58)},
}

# (label, reg_width_bits, reg_addr, read_len, {id_value: sensor_name})
ID_PROBES = (
    ('OV8856 (0x300B/0x300C)', 16, 0x300B, 2, {
        0x885A: 'OV8856',
    }),
    ('Samsung 16-bit (0x0000/0x0001)', 16, 0x0000, 2, {
        0x487B: 'S5K4H7',
        0x0971: 'S5KGW1 ofilm',
        0x0972: 'S5KGW1 sunny',
        0x3142: 'S5K3T2 ofilm',
        0x3143: 'S5K3T2 sunny',
        0x3141: 'S5K3T1 ofilm',
        0x3140: 'S5K3T1 sunny',
    }),
    ('GalaxyCore 8-bit (0xF0/0xF1)', 8, 0xF0, 2, {
        0x5035: 'GC5035',
        0x5036: 'GC5035 sunny',
        0x2375: 'GC2375 alpha',
        0x2374: 'GC2375 beta',
        0x2376: 'GC2375 AF',
    }),
    ('OV02A10 (0x02/0x03)', 8, 0x02, 2, {
        0x2509: 'OV02A10 alpha',
        0x2508: 'OV02A10 beta',
        0x250A: 'OV02A10 AF',
    }),
)


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


def parse_bus(value: str) -> int:
    if value.startswith('/dev/i2c-'):
        value = value[len('/dev/i2c-'):]
    try:
        bus = int(value, 10)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f'invalid bus number: {value!r}') from exc
    if bus < 0:
        raise argparse.ArgumentTypeError(f'bus number must be >= 0: {bus}')
    return bus


def probe_read1(fd: int, addr: int):
    """Read 1 byte from addr. Returns (True, None) on ACK, or (False, errno)."""
    rbuf = ctypes.create_string_buffer(1)
    msg = (I2CMsg * 1)(I2CMsg(addr, I2C_M_RD, 1, ctypes.addressof(rbuf)))
    data = I2CRdwrData(msg, 1)
    try:
        fcntl.ioctl(fd, I2C_RDWR, data)
        return True, 0
    except OSError as exc:
        return False, exc.errno


def read_reg(fd: int, addr: int, reg: int, regw: int, nbytes: int):
    """Write register address and read nbytes via repeated-start I2C_RDWR."""
    wbytes = bytes([reg >> 8, reg & 0xFF] if regw == 16 else [reg & 0xFF])
    wbuf = ctypes.create_string_buffer(wbytes, len(wbytes))
    rbuf = ctypes.create_string_buffer(nbytes)
    msgs = (I2CMsg * 2)(
        I2CMsg(addr, 0, len(wbytes), ctypes.addressof(wbuf)),
        I2CMsg(addr, I2C_M_RD, nbytes, ctypes.addressof(rbuf)),
    )
    data = I2CRdwrData(msgs, 2)
    try:
        fcntl.ioctl(fd, I2C_RDWR, data)
    except OSError:
        return None
    return int.from_bytes(rbuf.raw, 'big')


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Scan /dev/i2c-N (0x08-0x77) and read camera sensor chip IDs.'
    )
    parser.add_argument(
        'bus',
        type=parse_bus,
        help='I2C bus number N (or /dev/i2c-N)',
    )
    args = parser.parse_args()

    dev_path = f'/dev/i2c-{args.bus}'
    try:
        fd = os.open(dev_path, os.O_RDWR)
    except OSError as exc:
        print(f'error: cannot open {dev_path}: {exc.strerror}', file=sys.stderr)
        return 1

    try:
        print(f'Scanning {dev_path} (0x{SCAN_START:02x}-0x{SCAN_END:02x}, read-only)...')
        acked = []
        timeouts = 0
        for addr in range(SCAN_START, SCAN_END + 1):
            ok, err = probe_read1(fd, addr)
            if ok:
                acked.append(addr)
                hint = AUX_HINTS.get(addr, '')
                suffix = f' ({hint})' if hint else ''
                print(f'  ACK 0x{addr:02x}{suffix}')
            elif err == errno.ETIMEDOUT:
                timeouts += 1

        if timeouts:
            print(f'  warning: {timeouts} address probe(s) timed out (ETIMEDOUT)')

        if not acked:
            print('  no ACKed addresses in scan')

        probe_addrs = list(CANDIDATE_ADDRS)
        for addr in acked:
            if addr not in AUX_HINTS and addr not in probe_addrs:
                probe_addrs.append(addr)

        print('Probing sensor chip IDs...')
        id_hits = 0
        for addr in sorted(probe_addrs):
            for label, regw, reg, nbytes, ids in ID_PROBES:
                val = read_reg(fd, addr, reg, regw, nbytes)
                if val is None:
                    continue
                id_hits += 1
                match = ids.get(val)
                status = f'= {match}' if match else '(unrecognized ID)'
                print(
                    f'  0x{addr:02x} {label:<30s} reg 0x{reg:0{regw // 4}x} -> '
                    f'0x{val:0{nbytes * 2}x} {status}'
                )

        if not acked and not id_hits:
            print('No devices answered (check that a slot is powered via debugfs).')
    finally:
        os.close(fd)

    return 0


if __name__ == '__main__':
    sys.exit(main())
