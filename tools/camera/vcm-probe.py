#!/usr/bin/env python3
"""Probe and drive the unidentified cam0 autofocus VCM at i2c 0x0c.

The Lenovo Yoga Tab 11's rear camera module has a voice-coil actuator at
0x0c on i2c2 (answers only when the vcamaf rail, GPIO197, is on; the part
is not named by the stock software or the begonia notes — see
docs/hardware/CAMERA.md).  This tool reads whatever identification
registers the plausible mainline VCM driver families have, and can write
a raw focus position with each of their protocols so the right driver can
be picked and the lens driven from userspace.

Protocols (register maps from drivers/media/i2c/ of this tree):

- dw9714: NO registers and NO identification — the focus position is one
  2-byte big-endian I2C write, value = position << 4 (10-bit DAC in
  [15:4], slope bits in [3:2], period in [1:0]; the driver writes 0).
  Identification = "device ACKs its address and 2-byte writes" only.
  Wrong-chip risk: a register-less part with a different bit shift will
  move but on the wrong scale.
- dw9719 (also dw9718s/dw9761/dw9800k in that driver): INFO register 0x00
  reads 0xF1 (DW9719) or 0xF4 (DW9761); position = 16-bit BIG-endian
  write to register 0x03 (DW9719 family) — the driver uses CCI_REG16,
  which defaults to big-endian.  A part without registers answers the
  register-address write with the wrong byte, so the read fails or
  returns garbage.
- dw9768 (also giantec,gt9769): position in two registers, MSB 0x03 /
  LSB 0x04, written big-endian-first (i2c_smbus_write_word_swapped);
  register 0x02 bit 0 powers down, bit 1 selects AAC (ringing control)
  mode.  No ID register; 0x02..0x07 exist and read back.
- dw9807: like dw9768 (MSB 0x03 / LSB 0x04, byte writes) plus a busy bit
  in STATUS register 0x05 [2:0] the driver polls before writing.
- ak7375 (also ak7345): position = 16-bit write to register 0x00, value
  = position << 4 (ak7375, 12-bit DAC) or << 7 (ak7345, 9-bit); control
  register 0x02 (0 = active, 0x40 = standby).  No ID register.

Reads are always safe.  Writes (a focus position) need --write: they move
the lens, and writing a register address into a register-less chip
(dw9714-style) can set its DAC to an arbitrary current — start with small
positions and watch the current draw.

The sensor does NOT need to stream, but the rail does need to be on: run
with the camera pipeline probing (the vcamaf regulator is enabled by the
dw9714 DT node, the yt11-cam-probe module's debugfs power switch, or a
v4l2 open on the ov8856 subdev while it holds its supplies).
"""

import argparse
import ctypes
import errno
import fcntl
import os
import sys

I2C_RDWR = 0x0707
I2C_M_RD = 0x0001

DEFAULT_BUS = 2
DEFAULT_ADDR = 0x0C

# (name, human description)
PROTOS = ('dw9714', 'dw9719', 'dw9768', 'dw9807', 'ak7375')

# Identification reads per protocol: (label, reg, nbytes, {value: name}).
# dw9714 has nothing to read (register-less); probing it = an ACK scan.
ID_READS = {
    'dw9719': ('INFO register 0x00', 0x00, 1, {0xF1: 'DW9719', 0xF4: 'DW9761'}),
    'dw9768': ('RING/PD register 0x02', 0x02, 1, {0x00: 'active, direct mode', 0x02: 'active, AAC mode', 0x03: 'powered down (AAC)'}),
    'dw9807': ('CTL/STATUS registers 0x02/0x05', 0x05, 1, {0x00: 'idle'}),
    'ak7375': ('control register 0x02', 0x02, 1, {0x00: 'active', 0x40: 'standby'}),
}

# Extra sanity reads that exist only on register-mapped parts: reading a
# few registers back exercises the register-address write, which a
# register-less part cannot do correctly.
SANITY_READS = (
    ('dw9719', 'MODE register 0x06', 0x06, 1),
    ('dw9719', 'VCM_FREQ register 0x07', 0x07, 1),
    ('dw9768', 'AAC prescale register 0x06', 0x06, 1),
    ('dw9768', 'AAC time register 0x07', 0x07, 1),
    ('dw9807', 'mode register 0x06', 0x06, 1),
    ('dw9807', 'resonance register 0x07', 0x07, 1),
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
        raise argparse.ArgumentTypeError(f'bus number must be >= 0: {value!r}')
    return bus


def parse_addr(value: str) -> int:
    try:
        addr = int(value, 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f'invalid i2c address: {value!r}') from exc
    if not 0x08 <= addr <= 0x77:
        raise argparse.ArgumentTypeError(f'i2c address must be 0x08-0x77: {value!r}')
    return addr


def rdwr(fd: int, msgs) -> None:
    """Run an I2C_RDWR transaction; raises OSError on failure."""
    array = (I2CMsg * len(msgs))(*msgs)
    data = I2CRdwrData(array, len(msgs))
    fcntl.ioctl(fd, I2C_RDWR, data)


def ack(fd: int, addr: int) -> tuple[bool, int]:
    """Probe one address with a 1-byte read. Returns (acked, errno)."""
    rbuf = ctypes.create_string_buffer(1)
    msg = I2CMsg(addr, I2C_M_RD, 1, ctypes.addressof(rbuf))
    try:
        rdwr(fd, [msg])
        return True, 0
    except OSError as exc:
        return False, exc.errno


def write_bytes(fd: int, addr: int, payload: bytes) -> None:
    wbuf = ctypes.create_string_buffer(payload, len(payload))
    rdwr(fd, [I2CMsg(addr, 0, len(payload), ctypes.addressof(wbuf))])


def read_reg(fd: int, addr: int, reg: int, nbytes: int):
    """Register read (write reg address, repeated-start read). None on error."""
    wbuf = ctypes.create_string_buffer(bytes([reg & 0xFF]), 1)
    rbuf = ctypes.create_string_buffer(nbytes)
    try:
        rdwr(fd, [
            I2CMsg(addr, 0, 1, ctypes.addressof(wbuf)),
            I2CMsg(addr, I2C_M_RD, nbytes, ctypes.addressof(rbuf)),
        ])
    except OSError:
        return None
    return rbuf.raw


def set_position(fd: int, addr: int, proto: str, pos: int) -> None:
    """Write a raw focus position with the given protocol."""
    if not 0 <= pos <= 0x3FF:
        raise ValueError(f'position {pos} out of range 0..1023')

    if proto == 'dw9714':
        # One 2-byte big-endian write: DAC[15:4] | slope/period bits (0).
        write_bytes(fd, addr, bytes([(pos << 4) >> 8, (pos << 4) & 0xFF]))
    elif proto == 'dw9719':
        # Register 0x03, 16-bit big-endian (CCI_REG16 default).
        write_bytes(fd, addr, bytes([0x03, (pos >> 8) & 0x03, pos & 0xFF]))
    elif proto in ('dw9768', 'dw9807'):
        # MSB register 0x03 then LSB register 0x04, byte writes.
        write_bytes(fd, addr, bytes([0x03, (pos >> 8) & 0x03]))
        write_bytes(fd, addr, bytes([0x04, pos & 0xFF]))
    elif proto == 'ak7375':
        # Register 0x00, 16-bit big-endian, position << 4 (ak7375 12-bit DAC).
        val = pos << 4
        write_bytes(fd, addr, bytes([0x00, (val >> 8) & 0xFF, val & 0xFF]))
    else:
        raise ValueError(f'unknown protocol {proto!r}')


def identify(fd: int, addr: int) -> list[str]:
    """Read every identification register the candidate families have."""
    lines = []

    ok, err = ack(fd, addr)
    if ok:
        lines.append(f'ACK at 0x{addr:02x}: the actuator is present and powered')
    else:
        lines.append(
            f'no ACK at 0x{addr:02x} (errno {err}): the vcamaf rail is off, '
            f'or no actuator at this address')
        return lines

    lines.append(
        'dw9714: register-less, no ID to read (identification = this ACK '
        'plus a working 2-byte write)')

    for proto, (label, reg, nbytes, vals) in ID_READS.items():
        raw = read_reg(fd, addr, reg, nbytes)
        if raw is None:
            lines.append(f'{proto}: {label}: read FAILED '
                         f'(no register map -> probably not this family)')
            continue
        val = raw[0]
        note = vals.get(val, 'unknown value')
        lines.append(f'{proto}: {label}: 0x{val:02x} ({note})')

    for proto, label, reg, nbytes in SANITY_READS:
        raw = read_reg(fd, addr, reg, nbytes)
        if raw is None:
            lines.append(f'{proto}: {label}: read FAILED')
        else:
            lines.append(f'{proto}: {label}: 0x{raw[0]:02x}')

    return lines


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description='Identify and drive the unidentified cam0 VCM at i2c 0x0c.',
        epilog='Reads are safe; --pos moves the lens and needs --write. '
               'The vcamaf rail (GPIO197) must be on for the part to answer.',
    )
    ap.add_argument('bus', type=parse_bus, nargs='?', default=DEFAULT_BUS,
                    help=f'I2C bus number or /dev/i2c-N (default {DEFAULT_BUS}: the cam0 bus)')
    ap.add_argument('-a', '--address', type=parse_addr, default=DEFAULT_ADDR,
                    help=f'7-bit actuator address (default 0x{DEFAULT_ADDR:02x})')
    ap.add_argument('--proto', choices=PROTOS,
                    help='protocol to write with (see --pos)')
    ap.add_argument('--pos', type=lambda x: int(x, 0),
                    help='raw focus position to write, 0..1023 (moves the lens)')
    ap.add_argument('--write', action='store_true',
                    help='actually write the position (without it, the tool '
                         'only reads and prints what it would write)')
    args = ap.parse_args(argv)

    if args.pos is not None and args.proto is None:
        ap.error('--pos needs --proto')
    if args.proto is not None and args.pos is None:
        ap.error('--proto with no --pos does nothing (omit both to identify)')

    dev_path = f'/dev/i2c-{args.bus}'
    try:
        fd = os.open(dev_path, os.O_RDWR)
    except OSError as exc:
        print(f'error: cannot open {dev_path}: {exc.strerror}', file=sys.stderr)
        return 1

    try:
        for line in identify(fd, args.address):
            print(line)

        if args.pos is not None:
            payload = {
                'dw9714': f'2-byte BE write, value {args.pos} << 4 = 0x{(args.pos << 4) & 0xFFFF:04x}',
                'dw9719': f'reg 0x03, 16-bit BE, value 0x{args.pos:04x}',
                'dw9768': f'reg 0x03 = 0x{(args.pos >> 8) & 0x03}, reg 0x04 = 0x{args.pos & 0xFF}',
                'dw9807': f'reg 0x03 = 0x{(args.pos >> 8) & 0x03}, reg 0x04 = 0x{args.pos & 0xFF}',
                'ak7375': f'reg 0x00, 16-bit BE, value {args.pos} << 4 = 0x{(args.pos << 4) & 0xFFFF:04x}',
            }[args.proto]
            if args.write:
                set_position(fd, args.address, args.proto, args.pos)
                print(f'wrote position {args.pos} with {args.proto}: {payload}')
            else:
                print(f'dry run (add --write): {args.proto}: {payload}')
    finally:
        os.close(fd)

    return 0


if __name__ == '__main__':
    sys.exit(main())
