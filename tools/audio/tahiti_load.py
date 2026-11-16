#!/usr/bin/env python3
"""Firmware loader for the Synaptics AS33970 ("Tahiti") voice DSP over I2C.

This protocol implementation was derived from observing the vendor's loader
behaviour. No vendor code is included, and the firmware image itself is not
part of the repository.

Status (2026-11-16): stage 1 works on the YT-J706F (the ROM accepts the
second-stage loader), but the second-stage loader does not start on mainline
yet, so the wait for 0x80 times out. See docs/hardware/BOARD.md.
"""

from __future__ import annotations

import argparse
import ctypes
from dataclasses import dataclass
import fcntl
import mmap
import os
import struct
import sys
import time
from typing import Callable, Optional, Protocol, Tuple


I2C_RDWR = 0x0707
I2C_M_RD = 0x0001

EFLC_MAGIC = 0x434C4645  # "EFLC" as u32le
HEADER_MIN_SIZE = 0x48
SYS_HEADER_MIN_SIZE = 0x28
BLOCK_SIZE = 4096

BURST_WRITE_MAX = 120  # 0x78 bytes
BURST_READ_MAX = 16

MT6785_GPIO_BASE = 0x10005000
DEFAULT_BUS = 2
DEFAULT_ADDR = 0x41
DEFAULT_RESET_PIN = 122

READY_MAGIC = 0x8BADD00D


class TahitiError(RuntimeError):
    """Error raised during AS33970 image parsing or firmware download."""

    def __init__(self, message: str, code: Optional[int] = None) -> None:
        super().__init__(message)
        self.code = code


class I2CTransport(Protocol):
    """Minimal I2C register transport interface for injection in tests."""

    def write(self, sub: int, data: bytes) -> None:
        """Write data starting at a 16-bit big-endian sub-address."""

    def read(self, sub: int, n: int) -> bytes:
        """Read n bytes starting at a 16-bit big-endian sub-address."""


class _I2CMsg(ctypes.Structure):
    _fields_ = [
        ("addr", ctypes.c_uint16),
        ("flags", ctypes.c_uint16),
        ("len", ctypes.c_uint16),
        ("buf", ctypes.POINTER(ctypes.c_uint8)),
    ]


class _I2CRdwrIoctlData(ctypes.Structure):
    _fields_ = [
        ("msgs", ctypes.POINTER(_I2CMsg)),
        ("nmsgs", ctypes.c_uint32),
    ]


class I2CDevice:
    """Linux /dev/i2c-N transport using I2C_RDWR ioctls."""

    def __init__(self, bus: int, addr: int = DEFAULT_ADDR, verbose: bool = False) -> None:
        if not (0 <= addr <= 0x7F):
            raise ValueError(f"7-bit I2C address out of range: 0x{addr:x}")
        self.bus = bus
        self.addr = addr
        self.verbose = verbose
        self.path = f"/dev/i2c-{bus}"
        self._fd: Optional[int] = os.open(self.path, os.O_RDWR)

    def close(self) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    def __enter__(self) -> "I2CDevice":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def write(self, sub: int, data: bytes) -> None:
        if self._fd is None:
            raise TahitiError("I2C device is closed")
        payload = bytes([(sub >> 8) & 0xFF, sub & 0xFF]) + bytes(data)
        if self.verbose:
            preview = payload[2:18].hex()
            suffix = "..." if len(payload) - 2 > 16 else ""
            print(f"[i2c] W sub=0x{sub:04x} len={len(data)} data={preview}{suffix}")
        buf = (ctypes.c_uint8 * len(payload)).from_buffer_copy(payload)
        msg = _I2CMsg(addr=self.addr, flags=0, len=len(payload), buf=buf)
        msgs = (_I2CMsg * 1)(msg)
        ioctl_data = _I2CRdwrIoctlData(msgs=msgs, nmsgs=1)
        fcntl.ioctl(self._fd, I2C_RDWR, ioctl_data)

    def read(self, sub: int, n: int) -> bytes:
        if self._fd is None:
            raise TahitiError("I2C device is closed")
        if n <= 0:
            raise ValueError(f"Read length must be positive, got {n}")
        wpayload = bytes([(sub >> 8) & 0xFF, sub & 0xFF])
        wbuf = (ctypes.c_uint8 * 2).from_buffer_copy(wpayload)
        rbuf = (ctypes.c_uint8 * n)()
        msgs = (_I2CMsg * 2)(
            _I2CMsg(addr=self.addr, flags=0, len=2, buf=wbuf),
            _I2CMsg(addr=self.addr, flags=I2C_M_RD, len=n, buf=rbuf),
        )
        ioctl_data = _I2CRdwrIoctlData(msgs=msgs, nmsgs=2)
        fcntl.ioctl(self._fd, I2C_RDWR, ioctl_data)
        out = bytes(rbuf)
        if self.verbose:
            print(f"[i2c] R sub=0x{sub:04x} len={n} data={out.hex()}")
        return out


@dataclass(frozen=True)
class FirmwareImage:
    """Parsed EFLC firmware image containing stage-1 BL and stage-2 system blocks."""

    magic: int
    bl_offset: int
    bl_size: int
    bl_data: bytes
    sys_off_4k: int
    sys_offset: int
    sys_blocks: int
    sys_data: bytes
    version: Optional[Tuple[int, int, int, int]]


def parse_image(raw: bytes) -> FirmwareImage:
    """Parse and validate an EFLC firmware image buffer."""
    if len(raw) < HEADER_MIN_SIZE:
        raise TahitiError(
            f"Image too small for header: {len(raw)} bytes (need >= {HEADER_MIN_SIZE})"
        )

    magic = struct.unpack_from("<I", raw, 0x00)[0]
    if magic != EFLC_MAGIC:
        raise TahitiError(
            f"Unsupported image magic 0x{magic:08x} (expected 0x{EFLC_MAGIC:08x} 'EFLC')"
        )

    bl_offset, bl_size = struct.unpack_from("<II", raw, 0x08)
    sys_off_4k = struct.unpack_from("<H", raw, 0x26)[0]
    sys_offset = sys_off_4k << 12
    ver_words = struct.unpack_from("<4I", raw, 0x38)
    version: Optional[Tuple[int, int, int, int]] = (
        None if ver_words[0] == 0xFFFFFFFF else ver_words
    )

    if bl_size % 4 != 0:
        raise TahitiError(f"Boot loader size {bl_size} is not a multiple of 4")
    if bl_offset + bl_size > len(raw):
        raise TahitiError(
            f"Boot loader range [0x{bl_offset:x}, 0x{bl_offset + bl_size:x}) "
            f"exceeds image size 0x{len(raw):x}"
        )
    bl_data = raw[bl_offset : bl_offset + bl_size]

    if sys_offset + SYS_HEADER_MIN_SIZE > len(raw):
        raise TahitiError(
            f"System image offset 0x{sys_offset:x} exceeds image size 0x{len(raw):x}"
        )

    sys_blocks = struct.unpack_from("<H", raw, sys_offset + 0x26)[0]
    expected_sys_len = sys_blocks * BLOCK_SIZE
    sys_slice = raw[sys_offset : sys_offset + expected_sys_len]
    if len(sys_slice) < expected_sys_len:
        # Pad a short final read at EOF with 0xff to complete the last 4 KiB block.
        sys_data = sys_slice + (b"\xFF" * (expected_sys_len - len(sys_slice)))
    else:
        sys_data = sys_slice

    return FirmwareImage(
        magic=magic,
        bl_offset=bl_offset,
        bl_size=bl_size,
        bl_data=bl_data,
        sys_off_4k=sys_off_4k,
        sys_offset=sys_offset,
        sys_blocks=sys_blocks,
        sys_data=sys_data,
        version=version,
    )


def fletcher(buf: bytes) -> int:
    """Compute the AS33970 32-bit Fletcher checksum over 16-bit little-endian words."""
    if len(buf) % 2 != 0:
        raise ValueError(f"fletcher input length must be even, got {len(buf)}")
    s1 = 0xFFFF
    s2 = 0xFFFF
    n = len(buf) // 2
    i = 0
    while n:
        k = min(n, 359)
        n -= k
        for _ in range(k):
            word = int.from_bytes(buf[2 * i : 2 * i + 2], "little")
            s1 = (s1 + word) & 0xFFFFFFFF
            s2 = (s2 + s1) & 0xFFFFFFFF
            i += 1
        s1 = (s1 & 0xFFFF) + (s1 >> 16)
        s2 = (s2 & 0xFFFF) + (s2 >> 16)
    return (
        (((s2 & 0xFFFF) + (s2 >> 16)) << 16) | ((s1 & 0xFFFF) + (s1 >> 16))
    ) & 0xFFFFFFFF


def trim_block(block: bytes) -> bytes:
    """Trim trailing 0xffffffff 32-bit words, keeping all 4096 bytes if all 0xff."""
    if len(block) != BLOCK_SIZE:
        raise ValueError(f"Expected {BLOCK_SIZE}-byte block, got {len(block)}")
    end = len(block)
    while end >= 4 and block[end - 4 : end] == b"\xFF\xFF\xFF\xFF":
        end -= 4
    if end == 0:
        return block
    return block[:end]


def devmem_reset(pin: int, sleep_fn: Callable[[float], None] = time.sleep) -> None:
    """Toggle an active-low MediaTek MT6785 GPIO reset pin via /dev/mem."""
    if pin < 0:
        raise ValueError(f"GPIO pin must be non-negative, got {pin}")
    reg_off = 0x100 + (pin // 32) * 0x10
    bit = 1 << (pin % 32)
    map_size = max(0x1000, ((reg_off + 4 + 0xFFF) // 0x1000) * 0x1000)

    fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
    mm: Optional[mmap.mmap] = None
    reg: Optional[ctypes.c_uint32] = None
    try:
        mm = mmap.mmap(
            fd,
            map_size,
            mmap.MAP_SHARED,
            mmap.PROT_READ | mmap.PROT_WRITE,
            offset=MT6785_GPIO_BASE,
        )
        reg = ctypes.c_uint32.from_buffer(mm, reg_off)
        reg.value = reg.value & ~bit
        sleep_fn(0.020)
        reg.value = reg.value | bit
    finally:
        if reg is not None:
            del reg
        if mm is not None:
            mm.close()
        os.close(fd)


class TahitiLoader:
    """Host-side firmware loader state machine for the AS33970 DSP."""

    def __init__(
        self,
        i2c: I2CTransport,
        reset_fn: Callable[[], None],
        sleep_fn: Callable[[float], None] = time.sleep,
        monotonic_fn: Callable[[], float] = time.monotonic,
        log_fn: Callable[[str], None] = print,
    ) -> None:
        self.i2c = i2c
        self.reset_fn = reset_fn
        self.sleep_fn = sleep_fn
        self.monotonic_fn = monotonic_fn
        self.log_fn = log_fn

    def burst_write(self, sub: int, data: bytes) -> None:
        if sub % 4 != 0 or len(data) % 4 != 0:
            raise ValueError(
                f"burst_write requires 4-byte aligned sub (0x{sub:x}) and size ({len(data)})"
            )
        for offset in range(0, len(data), BURST_WRITE_MAX):
            self.i2c.write(sub + offset, data[offset : offset + BURST_WRITE_MAX])

    def burst_read(self, sub: int, n: int) -> bytes:
        if sub % 4 != 0 or n % 4 != 0:
            raise ValueError(
                f"burst_read requires 4-byte aligned sub (0x{sub:x}) and size ({n})"
            )
        out = bytearray()
        for offset in range(0, n, BURST_READ_MAX):
            chunk_len = min(BURST_READ_MAX, n - offset)
            out.extend(self.i2c.read(sub + offset, chunk_len))
        return bytes(out)

    def read_u32(self, sub: int) -> int:
        return struct.unpack("<I", self.i2c.read(sub, 4))[0]

    def write_u32(self, sub: int, val: int) -> None:
        self.i2c.write(sub, struct.pack("<I", val & 0xFFFFFFFF))

    def _send_stage1_chunk(self, idx: int, chunk: bytes) -> None:
        if len(chunk) % 4 != 0 or len(chunk) > BLOCK_SIZE:
            raise ValueError(f"Invalid stage-1 chunk size: {len(chunk)}")
        nwords = len(chunk) // 4
        words = struct.unpack(f"<{nwords}I", chunk)
        hdr = [0x52, idx, 0, nwords]
        s = (sum(words) + sum(hdr)) & 0xFFFFFFFF
        hdr[2] = (~s) & 0xFFFFFFFF

        self.burst_write(0x10, chunk)
        self.burst_write(0x04, struct.pack("<3I", hdr[1], hdr[2], hdr[3]))
        self.write_u32(0x00, hdr[0])  # Triggers the ROM loader

    def stage1(self, bl_data: bytes) -> None:
        """Reset the chip and stream the second-stage boot loader to the ROM."""
        self.log_fn("Stage 1: resetting chip and waiting for ROM prompt ('C')")
        self.reset_fn()

        # Right after reset the ROM does not acknowledge its address for a
        # while: treat I2C errors as "not ready yet" until the deadline.
        deadline = self.monotonic_fn() + 1.0
        st: Optional[int] = None
        while True:
            try:
                st = self.read_u32(0)
            except OSError:
                st = None
            if st == 0x43:
                break
            if self.monotonic_fn() >= deadline:
                last = "no answer" if st is None else f"0x{st:08x}"
                raise TahitiError(f"Timeout waiting for ROM 'C' after reset (last status: {last})")
            self.sleep_fn(0.001)

        self.write_u32(0, 0)

        chunks = [
            bl_data[off : off + BLOCK_SIZE] for off in range(0, len(bl_data), BLOCK_SIZE)
        ]
        self.log_fn(
            f"Stage 1: sending boot loader ({len(bl_data)} bytes in {len(chunks)} chunks)"
        )

        next_idx = 0
        last_idx: Optional[int] = None
        retries = 0
        idle_polls = 0
        stage1_deadline = self.monotonic_fn() + 10.0

        while True:
            if self.monotonic_fn() >= stage1_deadline:
                raise TahitiError("Stage 1 timeout (10 s)")

            st = self.read_u32(0)
            if st in (0x00, 0x43):
                idle_polls += 1
                if idle_polls > 200:
                    raise TahitiError(
                        f"Stage 1 stuck at status 0x{st:08x} for >200 polls"
                    )
                self.sleep_fn(0.001)
                continue

            idle_polls = 0

            if st in (0x53, 0x80):
                if next_idx >= len(chunks):
                    self.write_u32(0, 0x44)  # 'D'
                    break
                self._send_stage1_chunk(next_idx, chunks[next_idx])
                last_idx = next_idx
                next_idx += 1
                retries = 0
            elif st in (0x52, 0x44):
                self.sleep_fn(0.001)
            elif st == 0x54:
                if last_idx is None:
                    raise TahitiError("Stage 1 received 'T' before any chunk was sent")
                retries += 1
                if retries > 3:
                    self.write_u32(0, 0x41)  # 'A'
                    raise TahitiError(
                        f"Stage 1 chunk {last_idx} failed after 3 retransmissions"
                    )
                self._send_stage1_chunk(last_idx, chunks[last_idx])
            elif st == 0x4F:
                break
            elif st == 0x46:
                raise TahitiError("Stage 1 failed: device reported 'F' (0x46)")
            else:
                raise TahitiError(f"Stage 1 unexpected status word: 0x{st:08x}")

    def wait_for_loader(self) -> None:
        """Poll status word until the second-stage loader announces 0x80."""
        self.log_fn("Stage 1: waiting for second-stage loader (0x80)")
        deadline = self.monotonic_fn() + 2.0
        st: Optional[int] = None
        while self.monotonic_fn() < deadline:
            try:
                st = self.read_u32(0)
            except OSError:
                st = None
            if st == 0x80:
                return
            self.sleep_fn(0.001)
        last = "no answer" if st is None else f"0x{st:08x}"
        raise TahitiError(f"Timeout waiting for second-stage loader status 0x80 (last: {last})")

    def stage2(self, sys_blocks: int, sys_data: bytes) -> None:
        """Upload system blocks to the second-stage loader and reboot."""
        if len(sys_data) != sys_blocks * BLOCK_SIZE:
            raise ValueError(
                f"System data length {len(sys_data)} does not match {sys_blocks} blocks"
            )

        # Persistent message buffer: reboot intentionally retains m[8:12].
        m = bytearray(0x24)
        seq = 0

        def send(cmd: int, msglen: int, replylen: int, data: bytes = b"") -> bytes:
            nonlocal seq
            if msglen > len(m):
                raise ValueError(f"msglen {msglen} exceeds buffer length {len(m)}")
            m[0] = cmd & 0x3F
            m[1] = seq & 0xFF
            struct.pack_into("<H", m, 2, msglen)
            m[4:8] = b"\x00\x00\x00\x00"
            h = fletcher(bytes(m[:msglen]))
            struct.pack_into("<I", m, 4, h)

            if data:
                self.burst_write(msglen, data)
            self.burst_write(4, bytes(m[4:msglen]))
            self.i2c.write(0, bytes(m[0:4]))

            deadline = self.monotonic_fn() + 5.0
            while True:
                hdr = self.i2c.read(0, 4)
                if hdr[0] & 0x80:
                    break
                if self.monotonic_fn() >= deadline:
                    raise TahitiError(
                        f"Stage 2 timeout waiting for reply to cmd 0x{cmd:02x}"
                    )
                self.sleep_fn(0.001)

            seq += 1
            if hdr[0] & 0x40:
                raw_code = hdr[0] & 0x3F
                code = raw_code - 0x40 if (raw_code & 0x20) else raw_code
                if code == -1:
                    desc = "message error"
                elif code in (-2, -5):
                    desc = "unsupported flash"
                else:
                    desc = "image error"
                raise TahitiError(
                    f"Stage 2 cmd 0x{cmd:02x} error {code} ({desc})",
                    code=code,
                )

            return self.burst_read(0, replylen)

        self.log_fn("Stage 2: ping, write_status(0), read_status")
        send(0x00, 0x08, 0x1C)  # ping
        struct.pack_into("<I", m, 8, 0)
        send(0x02, 0x0C, 0x0C)  # write_status(0)
        send(0x01, 0x08, 0x0C)  # read_status

        self.log_fn(f"Stage 2: writing {sys_blocks} system blocks")
        for blk_idx in range(sys_blocks):
            raw_blk = sys_data[blk_idx * BLOCK_SIZE : (blk_idx + 1) * BLOCK_SIZE]
            trimmed = trim_block(raw_blk)
            struct.pack_into("<HH", m, 8, blk_idx, len(trimmed))
            send(0x08, 0x0C, 0x0C, trimmed)

        self.log_fn("Stage 2: rebooting DSP into firmware")
        reply = send(0x0E, 0x0C, 0x0C)
        status = struct.unpack_from("<I", reply, 8)[0]
        if status != 0:
            raise TahitiError(f"Stage 2 reboot failed with status 0x{status:08x}")

    def wait_ready(self) -> int:
        """Wait 1 s after reboot, then poll sub-address 4 for 0x8badd00d."""
        self.log_fn("Post-reboot: waiting 1 s then polling for firmware ready (0x8badd00d)")
        self.sleep_fn(1.0)
        deadline = self.monotonic_fn() + 5.0
        while True:
            val = self.read_u32(4)
            if val == READY_MAGIC:
                self.log_fn(f"Firmware ready: 0x{val:08x}")
                return val
            if self.monotonic_fn() >= deadline:
                raise TahitiError(
                    f"Firmware ready timeout after 5 s (sub-address 4 = 0x{val:08x})"
                )
            self.sleep_fn(0.050)

    def load(self, image: FirmwareImage) -> int:
        """Run the full stage-1, stage-2, and post-reboot verification sequence."""
        self.stage1(image.bl_data)
        self.wait_for_loader()
        self.stage2(image.sys_blocks, image.sys_data)
        return self.wait_ready()


def print_image_summary(image: FirmwareImage, path: str) -> None:
    """Print parsed EFLC header fields."""
    ver_str = (
        "ignored (0xffffffff)"
        if image.version is None
        else ".".join(str(v) for v in image.version)
    )
    print(f"Image:       {path}")
    print(f"Magic:       0x{image.magic:08x} (EFLC)")
    print(f"Boot loader: offset=0x{image.bl_offset:08x}, size={image.bl_size} bytes")
    print(
        f"System img:  offset=0x{image.sys_offset:08x} "
        f"(sys_off_4k=0x{image.sys_off_4k:04x}), blocks={image.sys_blocks} "
        f"({image.sys_blocks * BLOCK_SIZE} bytes)"
    )
    print(f"Version:     {ver_str}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Load firmware into a Synaptics AS33970 ('Tahiti') DSP over Linux i2c-dev."
    )
    parser.add_argument(
        "--bus",
        type=int,
        default=DEFAULT_BUS,
        help=f"I2C bus number for /dev/i2c-N (default: {DEFAULT_BUS})",
    )
    parser.add_argument(
        "--addr",
        type=lambda s: int(s, 0),
        default=DEFAULT_ADDR,
        help=f"7-bit I2C slave address (default: 0x{DEFAULT_ADDR:02x})",
    )
    reset_group = parser.add_mutually_exclusive_group()
    reset_group.add_argument(
        "--reset-devmem",
        type=int,
        default=None,
        metavar="PIN",
        help=(
            "Toggle active-low MT6785 GPIO PIN via /dev/mem before loading "
            f"(default: {DEFAULT_RESET_PIN})"
        ),
    )
    reset_group.add_argument(
        "--no-reset",
        action="store_true",
        help="Skip hardware reset (assume caller already reset the chip)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and print the image header, then exit without touching hardware",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print every I2C read/write transfer",
    )
    parser.add_argument("image", metavar="IMAGE", help="Path to the EFLC firmware image")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    try:
        with open(args.image, "rb") as fh:
            raw = fh.read()
        image = parse_image(raw)
    except (OSError, TahitiError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print_image_summary(image, args.image)
    if args.dry_run:
        return 0

    if args.no_reset:
        reset_fn: Callable[[], None] = lambda: None
    else:
        pin = DEFAULT_RESET_PIN if args.reset_devmem is None else args.reset_devmem
        reset_fn = lambda: devmem_reset(pin)

    try:
        with I2CDevice(args.bus, args.addr, verbose=args.verbose) as i2c:
            loader = TahitiLoader(i2c=i2c, reset_fn=reset_fn)
            loader.load(image)
    except (OSError, TahitiError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
