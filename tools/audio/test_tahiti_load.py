#!/usr/bin/env python3
"""Offline unit tests for tahiti_load.py against a simulated AS33970 device."""

from __future__ import annotations

import os
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tahiti_load as tl  # noqa: E402


def naive_fletcher_reference(buf: bytes) -> int:
    """Independent naive implementation of the spec's Fletcher-32 algorithm."""
    words = [
        buf[j] | (buf[j + 1] << 8)
        for j in range(0, len(buf), 2)
    ]
    s1 = 0xFFFF
    s2 = 0xFFFF
    n = len(words)
    i = 0
    while n:
        k = min(n, 359)
        n -= k
        for _ in range(k):
            s1 = (s1 + words[i]) & 0xFFFFFFFF
            s2 = (s2 + s1) & 0xFFFFFFFF
            i += 1
        s1 = (s1 & 0xFFFF) + (s1 >> 16)
        s2 = (s2 & 0xFFFF) + (s2 >> 16)
    lo = (s1 & 0xFFFF) + (s1 >> 16)
    hi = (s2 & 0xFFFF) + (s2 >> 16)
    return ((hi << 16) | lo) & 0xFFFFFFFF


class SimulatedTahiti:
    """Device-side AS33970 simulator implementing the Stage 1 and Stage 2 protocol."""

    def __init__(self, initial_idle_polls: int = 0) -> None:
        self.buf = bytearray(0x2000)
        self.phase = "unreset"
        self.initial_idle_polls = initial_idle_polls
        self._idle_left = 0
        self.stage1_started = False
        self.expected_bl_idx = 0
        self.bl_received = bytearray()
        self.expected_seq = 0
        self.stage2_status = 0
        self.recorded_blocks: list[tuple[int, bytes]] = []
        self.aborted = False
        self.forced_stage2_error: int | None = None
        self.write_count = 0
        self.read_count = 0

    def reset(self) -> None:
        self.buf[:] = b"\x00" * len(self.buf)
        self.phase = "stage1"
        self.stage1_started = False
        self._idle_left = self.initial_idle_polls
        self.expected_bl_idx = 0
        self.bl_received = bytearray()
        self.expected_seq = 0
        self.stage2_status = 0
        self.recorded_blocks = []
        self.aborted = False
        struct.pack_into("<I", self.buf, 0, 0x43)  # 'C'

    def write(self, sub: int, data: bytes) -> None:
        self.write_count += 1
        assert sub % 4 == 0, f"Unaligned write sub-address 0x{sub:x}"
        assert len(data) % 4 == 0, f"Unaligned write size {len(data)}"
        assert len(data) <= 120, f"Burst write exceeded 120 bytes: {len(data)}"
        assert sub + len(data) <= len(self.buf), "Write out of simulator buffer"

        self.buf[sub : sub + len(data)] = data
        if sub != 0:
            return

        word0 = struct.unpack_from("<I", self.buf, 0)[0]

        if self.phase == "stage1":
            if not self.stage1_started and word0 == 0:
                self.stage1_started = True
                if self._idle_left > 0:
                    struct.pack_into("<I", self.buf, 0, 0x00)
                else:
                    struct.pack_into("<I", self.buf, 0, 0x53)  # 'S'
                return

            if word0 == 0x52:  # 'R' chunk trigger
                hdr = struct.unpack_from("<4I", self.buf, 0)
                _, idx, _, nwords = hdr
                chunk_len = nwords * 4
                chunk = bytes(self.buf[0x10 : 0x10 + chunk_len])
                words = struct.unpack(f"<{nwords}I", chunk)
                total = (sum(words) + sum(hdr)) & 0xFFFFFFFF
                if total == 0xFFFFFFFF and idx == self.expected_bl_idx:
                    self.bl_received.extend(chunk)
                    self.expected_bl_idx += 1
                    struct.pack_into("<I", self.buf, 0, 0x53)  # 'S'
                else:
                    struct.pack_into("<I", self.buf, 0, 0x54)  # 'T'
                return

            if word0 == 0x44:  # 'D' end of stage 1
                self.phase = "stage2"
                struct.pack_into("<I", self.buf, 0, 0x80)
                return

            if word0 == 0x41:  # 'A' abort after too many retries
                self.aborted = True
                self.phase = "aborted"
                struct.pack_into("<I", self.buf, 0, 0x46)  # 'F'
                return

            raise AssertionError(f"Unexpected stage1 trigger word0=0x{word0:08x}")

        if self.phase == "stage2":
            cmd = self.buf[0] & 0x3F
            seq = self.buf[1]
            msglen = struct.unpack_from("<H", self.buf, 2)[0]
            recv_hash = struct.unpack_from("<I", self.buf, 4)[0]

            assert seq == (self.expected_seq & 0xFF), (
                f"Expected seq {self.expected_seq & 0xFF}, got {seq}"
            )
            msg_for_hash = bytearray(self.buf[0:msglen])
            msg_for_hash[4:8] = b"\x00\x00\x00\x00"
            expected_hash = naive_fletcher_reference(bytes(msg_for_hash))
            assert recv_hash == expected_hash, (
                f"Fletcher mismatch: got 0x{recv_hash:08x}, expected 0x{expected_hash:08x}"
            )
            self.expected_seq += 1

            if self.forced_stage2_error is not None:
                code6 = self.forced_stage2_error & 0x3F
                self.buf[0] = 0x80 | 0x40 | code6
                self.buf[1:12] = b"\x00" * 11
                return

            if cmd == 0x00:  # ping
                self.buf[0:28] = b"\x00" * 28
            elif cmd == 0x01:  # read_status
                self.buf[0:12] = b"\x00" * 12
                struct.pack_into("<I", self.buf, 8, self.stage2_status)
            elif cmd == 0x02:  # write_status
                self.stage2_status = struct.unpack_from("<I", self.buf, 8)[0]
                self.buf[0:12] = b"\x00" * 12
            elif cmd == 0x08:  # write_verify
                blk_idx, blk_len = struct.unpack_from("<HH", self.buf, 8)
                blk_data = bytes(self.buf[msglen : msglen + blk_len])
                self.recorded_blocks.append((blk_idx, blk_data))
                self.buf[0:12] = b"\x00" * 12
            elif cmd == 0x0E:  # reboot
                self.buf[0:12] = b"\x00" * 12
                self.phase = "reboot_pending"
            else:
                raise AssertionError(f"Unknown stage2 command 0x{cmd:02x}")

            self.buf[0] = 0x80  # bit 7 set, bit 6 clear
            return

        raise AssertionError(f"Write in unexpected phase {self.phase!r}")

    def read(self, sub: int, n: int) -> bytes:
        self.read_count += 1
        assert sub % 4 == 0, f"Unaligned read sub-address 0x{sub:x}"
        assert n % 4 == 0, f"Unaligned read size {n}"
        assert n <= 16, f"Burst read exceeded 16 bytes: {n}"

        if self.phase == "stage1" and self.stage1_started and sub == 0 and self._idle_left > 0:
            self._idle_left -= 1
            if self._idle_left == 0:
                struct.pack_into("<I", self.buf, 0, 0x53)

        out = bytes(self.buf[sub : sub + n])
        if self.phase == "reboot_pending" and sub == 0 and n == 12:
            self.phase = "rebooted"
            struct.pack_into("<I", self.buf, 4, 0x8BADD00D)
        return out


class CorruptingTransport:
    """Wrapper that corrupts one byte in flight on matching stage-1 chunk writes."""

    def __init__(self, inner: SimulatedTahiti, corrupt_times: int, target_chunk_idx: int = 1) -> None:
        self.inner = inner
        self.remaining_corruptions = corrupt_times
        self.target_chunk_idx = target_chunk_idx

    def write(self, sub: int, data: bytes) -> None:
        if sub == 0 and len(data) == 4 and struct.unpack("<I", data)[0] == 0x52:
            # A chunk trigger is being issued; check if hdr[1] matches target chunk.
            hdr_idx = struct.unpack_from("<I", self.inner.buf, 4)[0]
            if hdr_idx == self.target_chunk_idx and self.remaining_corruptions > 0:
                self.remaining_corruptions -= 1
                self.inner.buf[0x10] ^= 0x01
        self.inner.write(sub, data)

    def read(self, sub: int, n: int) -> bytes:
        return self.inner.read(sub, n)


def build_synthetic_image(
    *,
    magic: int = tl.EFLC_MAGIC,
    version: tuple[int, int, int, int] = (1, 2, 3, 4),
    bl_size: int = 6144,
    short_last_block_bytes: int = 102,
) -> tuple[bytes, bytes, list[bytes]]:
    """Build a synthetic EFLC image with a 6 KiB BL and 3 system blocks."""
    bl_offset = 0x1000
    sys_off_4k = 3  # 0x3000: leaves room for header + 6 KiB BL
    sys_offset = sys_off_4k << 12

    bl_data = bytes(((i * 73 + 19) & 0xFF) for i in range(bl_size))

    # Block 0: contains the second header (+0x26 = sys_blocks = 3) and payload.
    blk0 = bytearray(((i * 31 + 5) & 0xFF) for i in range(4096))
    struct.pack_into("<H", blk0, 0x26, 3)

    # Block 1: all 0xff (must be sent in full as 4096 bytes).
    blk1 = bytearray(b"\xFF" * 4096)

    # Block 2: only short_last_block_bytes present in file; loader pads with 0xff
    # to 4096 bytes and then trims trailing 0xffffffff words.
    blk2_partial = bytes(((i * 17 + 3) & 0xFF) for i in range(short_last_block_bytes))

    total_len = sys_offset + 2 * 4096 + len(blk2_partial)
    img = bytearray(b"\x00" * total_len)
    struct.pack_into("<I", img, 0x00, magic)
    struct.pack_into("<II", img, 0x08, bl_offset, bl_size)
    struct.pack_into("<H", img, 0x26, sys_off_4k)
    struct.pack_into("<4I", img, 0x38, *version)

    img[bl_offset : bl_offset + bl_size] = bl_data
    img[sys_offset : sys_offset + 4096] = blk0
    img[sys_offset + 4096 : sys_offset + 8192] = blk1
    img[sys_offset + 8192 : sys_offset + 8192 + len(blk2_partial)] = blk2_partial

    blk2_padded = blk2_partial + b"\xFF" * (4096 - len(blk2_partial))
    return bytes(img), bl_data, [bytes(blk0), bytes(blk1), blk2_padded]


class FakeClock:
    """Deterministic clock so tests run instantaneously without sleeping 1 s."""

    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, dt: float) -> None:
        self.now += dt


class TestTahitiLoad(unittest.TestCase):
    def test_fletcher_known_vector_and_reference(self) -> None:
        # Hand-computed: words [0x0001, 0x0002]
        # s1 = 0xffff + 1 + 2 = 0x10002 -> fold = 3
        # s2 = 0xffff + 0x10000 + 0x10002 = 0x30001 -> fold = 4
        vec = b"\x01\x00\x02\x00"
        self.assertEqual(tl.fletcher(vec), 0x00040003)
        self.assertEqual(tl.fletcher(vec), naive_fletcher_reference(vec))

        # All-zero 4 bytes: s1 = 0xffff, s2 = 0xffff + 2*0xffff -> fold = 0xffff
        zeros = b"\x00\x00\x00\x00"
        self.assertEqual(tl.fletcher(zeros), 0xFFFFFFFF)
        self.assertEqual(tl.fletcher(zeros), naive_fletcher_reference(zeros))

        # Long vector (> 359 * 2 bytes) exercising the outer reduction loop
        long_vec = bytes((i * 37) & 0xFF for i in range(1500))
        self.assertEqual(tl.fletcher(long_vec), naive_fletcher_reference(long_vec))

    def test_full_load_with_synthetic_image(self) -> None:
        raw, bl_data, raw_blocks = build_synthetic_image()
        image = tl.parse_image(raw)
        self.assertEqual(image.bl_size, 6144)
        self.assertEqual(image.sys_blocks, 3)
        self.assertEqual(image.version, (1, 2, 3, 4))

        sim = SimulatedTahiti(initial_idle_polls=3)
        clock = FakeClock()
        logs: list[str] = []
        loader = tl.TahitiLoader(
            i2c=sim,
            reset_fn=sim.reset,
            sleep_fn=clock.sleep,
            monotonic_fn=clock.monotonic,
            log_fn=logs.append,
        )

        ready = loader.load(image)
        self.assertEqual(ready, 0x8BADD00D)
        self.assertEqual(sim.phase, "rebooted")
        self.assertEqual(bytes(sim.bl_received), bl_data)

        # Block 0: all 4096 bytes (ends with non-0xffffffff word)
        # Block 1: all 0xff -> spec keeps all 4096 bytes
        # Block 2: 102 bytes + 2 bytes of 0xff padding in last word -> 104 bytes trimmed
        expected_blk0 = raw_blocks[0]
        expected_blk1 = b"\xFF" * 4096
        expected_blk2 = raw_blocks[2][:104]
        self.assertEqual(len(expected_blk0), 4096)
        self.assertEqual(len(expected_blk1), 4096)
        self.assertEqual(len(expected_blk2), 104)
        self.assertEqual(
            sim.recorded_blocks,
            [(0, expected_blk0), (1, expected_blk1), (2, expected_blk2)],
        )

    def test_stage1_retransmission_once_and_abort_on_four(self) -> None:
        raw, bl_data, _ = build_synthetic_image()
        image = tl.parse_image(raw)

        # Single corruption on chunk 1 -> one 'T' -> retransmit succeeds.
        sim = SimulatedTahiti()
        transport = CorruptingTransport(sim, corrupt_times=1, target_chunk_idx=1)
        clock = FakeClock()
        loader = tl.TahitiLoader(
            i2c=transport,
            reset_fn=sim.reset,
            sleep_fn=clock.sleep,
            monotonic_fn=clock.monotonic,
            log_fn=lambda _: None,
        )
        self.assertEqual(loader.load(image), 0x8BADD00D)
        self.assertEqual(bytes(sim.bl_received), bl_data)

        # Four consecutive corruptions -> 4th 'T' writes 0x41 and fails.
        sim_fail = SimulatedTahiti()
        transport_fail = CorruptingTransport(sim_fail, corrupt_times=4, target_chunk_idx=1)
        loader_fail = tl.TahitiLoader(
            i2c=transport_fail,
            reset_fn=sim_fail.reset,
            sleep_fn=clock.sleep,
            monotonic_fn=clock.monotonic,
            log_fn=lambda _: None,
        )
        with self.assertRaises(tl.TahitiError):
            loader_fail.load(image)
        self.assertTrue(sim_fail.aborted)

    def test_wrong_magic_rejected(self) -> None:
        raw, _, _ = build_synthetic_image(magic=0xDEADBEEF)
        with self.assertRaises(tl.TahitiError) as ctx:
            tl.parse_image(raw)
        self.assertIn("magic", str(ctx.exception).lower())

        with tempfile.NamedTemporaryFile(suffix=".bin") as tmp:
            tmp.write(raw)
            tmp.flush()
            rc = tl.main(["--dry-run", tmp.name])
            self.assertNotEqual(rc, 0)

    def test_stage2_signed_6bit_error_code(self) -> None:
        raw, _, _ = build_synthetic_image()
        image = tl.parse_image(raw)
        sim = SimulatedTahiti()
        sim.forced_stage2_error = -5  # 0x3b in low 6 bits
        clock = FakeClock()
        loader = tl.TahitiLoader(
            i2c=sim,
            reset_fn=sim.reset,
            sleep_fn=clock.sleep,
            monotonic_fn=clock.monotonic,
            log_fn=lambda _: None,
        )
        with self.assertRaises(tl.TahitiError) as ctx:
            loader.load(image)
        self.assertEqual(ctx.exception.code, -5)


if __name__ == "__main__":
    unittest.main()
