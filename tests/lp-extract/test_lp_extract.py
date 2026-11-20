#!/usr/bin/env python3
"""Offline unit and CLI tests for tools/lp-extract.py."""

import importlib.util
import os
import random
import struct
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
TOOL_PATH = os.path.join(REPO_ROOT, "tools", "lp-extract.py")

SPEC = importlib.util.spec_from_file_location("lp_extract", TOOL_PATH)
lp_extract = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(lp_extract)

BLK_SZ = 4096
SECTOR_SZ = 512


def build_synthetic_raw_super():
    """Build a synthetic raw super image with two partitions (one with two extents)."""
    rng = random.Random(42)

    # Construct payloads aligned to 4096-byte blocks so sparse encoding
    # exercises RAW, FILL, and DONT_CARE chunks inside and between partitions.
    v_ext0 = rng.randbytes(BLK_SZ) + (b"\xCA\xFE\xBA\xBE" * (BLK_SZ // 4))
    v_ext1 = (
        (b"\x00" * BLK_SZ)
        + (b"\x12\x34\x56\x78" * (BLK_SZ // 4))
        + rng.randbytes(254 * BLK_SZ)
    )
    vendor_payload = v_ext0 + v_ext1

    sys_payload = (
        (b"\xAA\x55\xAA\x55" * (BLK_SZ // 4))
        + (b"\x00" * BLK_SZ)
        + rng.randbytes(BLK_SZ)
    )

    # Sector offsets (all 4096-byte aligned = multiples of 8 sectors).
    v_ext0_sec = 64        # byte offset 32768 (block 8)
    v_ext1_sec = 128       # byte offset 65536 (block 16)
    sys_ext0_sec = 2200    # byte offset 1126400 (block 275)

    total_size = (sys_ext0_sec * SECTOR_SZ) + len(sys_payload) + (2 * BLK_SZ)
    buf = bytearray(total_size)

    # Geometry at offset 4096: magic(0x616C4467), struct_size(52), checksum[32],
    # max_meta(65536), slots(2), block_size(4096).
    struct.pack_into("<II", buf, 4096, 0x616C4467, 52)
    struct.pack_into("<III", buf, 4096 + 40, 65536, 2, BLK_SZ)

    # Partition table: 2 entries * 52 bytes
    part_entries = bytearray()
    for name, first, num in (
        (b"vendor_a", 0, 2),
        (b"system_a", 2, 1),
    ):
        entry = bytearray(52)
        entry[: len(name)] = name
        struct.pack_into("<IIII", entry, 36, 0, first, num, 0)
        part_entries += entry

    # Extent table: 3 entries * 24 bytes
    ext_entries = b"".join(
        [
            struct.pack("<QIQI", len(v_ext0) // SECTOR_SZ, 0, v_ext0_sec, 0),
            struct.pack("<QIQI", len(v_ext1) // SECTOR_SZ, 0, v_ext1_sec, 0),
            struct.pack("<QIQI", len(sys_payload) // SECTOR_SZ, 0, sys_ext0_sec, 0),
        ]
    )

    tables = bytes(part_entries) + ext_entries
    hsize = 256
    meta_off = 4096 * 3
    struct.pack_into("<IHHI", buf, meta_off, 0x414C5030, 10, 0, hsize)
    struct.pack_into("<I", buf, meta_off + 44, len(tables))

    desc_off = meta_off + 4 + 2 + 2 + 4 + 32 + 4 + 32
    # Descriptors: partitions, extents, groups (empty), block_devices (empty)
    struct.pack_into("<III", buf, desc_off, 0, 2, 52)
    struct.pack_into("<III", buf, desc_off + 12, len(part_entries), 3, 24)
    struct.pack_into("<III", buf, desc_off + 24, len(tables), 0, 48)
    struct.pack_into("<III", buf, desc_off + 36, len(tables), 0, 64)

    buf[meta_off + hsize : meta_off + hsize + len(tables)] = tables
    buf[v_ext0_sec * SECTOR_SZ : v_ext0_sec * SECTOR_SZ + len(v_ext0)] = v_ext0
    buf[v_ext1_sec * SECTOR_SZ : v_ext1_sec * SECTOR_SZ + len(v_ext1)] = v_ext1
    buf[sys_ext0_sec * SECTOR_SZ : sys_ext0_sec * SECTOR_SZ + len(sys_payload)] = sys_payload

    return bytes(buf), {"vendor_a": vendor_payload, "system_a": sys_payload}


def encode_sparse(raw: bytes, blk_sz: int = BLK_SZ, file_hdr_sz: int = 28, chunk_hdr_sz: int = 12, include_crc: bool = True) -> bytes:
    """Encode a block-aligned raw image into Android sparse format with RAW, FILL, and DONT_CARE chunks."""
    assert len(raw) % blk_sz == 0
    total_blks = len(raw) // blk_sz

    chunks = []
    i = 0
    while i < total_blks:
        blk = raw[i * blk_sz : (i + 1) * blk_sz]
        if blk == b"\x00" * blk_sz:
            j = i + 1
            while j < total_blks and raw[j * blk_sz : (j + 1) * blk_sz] == b"\x00" * blk_sz:
                j += 1
            chunks.append((0xCAC3, j - i, b""))
            i = j
        elif blk == blk[:4] * (blk_sz // 4):
            pat = blk[:4]
            j = i + 1
            while j < total_blks and raw[j * blk_sz : (j + 1) * blk_sz] == pat * (blk_sz // 4):
                j += 1
            chunks.append((0xCAC2, j - i, pat))
            i = j
        else:
            raw_parts = [blk]
            j = i + 1
            while j < total_blks:
                nxt = raw[j * blk_sz : (j + 1) * blk_sz]
                if nxt == b"\x00" * blk_sz or nxt == nxt[:4] * (blk_sz // 4):
                    break
                raw_parts.append(nxt)
                j += 1
            chunks.append((0xCAC1, j - i, b"".join(raw_parts)))
            i = j

    if include_crc:
        chunks.append((0xCAC4, 0, struct.pack("<I", 0x12345678)))

    out = bytearray()
    out += struct.pack(
        "<IHHHHIIII",
        0xED26FF3A,
        1,
        0,
        file_hdr_sz,
        chunk_hdr_sz,
        blk_sz,
        total_blks,
        len(chunks),
        0,
    )
    out += b"\xEE" * (file_hdr_sz - 28)

    for ctype, chunk_sz, payload in chunks:
        total_sz = chunk_hdr_sz + len(payload)
        out += struct.pack("<HHII", ctype, 0, chunk_sz, total_sz)
        out += b"\xDD" * (chunk_hdr_sz - 12)
        out += payload

    return bytes(out)


class TestLpExtract(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.raw_bytes, self.payloads = build_synthetic_raw_super()
        self.sparse_bytes = encode_sparse(self.raw_bytes)
        self.raw_path = os.path.join(self.tmpdir.name, "super_raw.img")
        self.sparse_path = os.path.join(self.tmpdir.name, "super_sparse.img")
        with open(self.raw_path, "wb") as f:
            f.write(self.raw_bytes)
        with open(self.sparse_path, "wb") as f:
            f.write(self.sparse_bytes)

    def tearDown(self):
        self.tmpdir.cleanup()

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, TOOL_PATH, *args],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_list_identical(self):
        res_raw = self.run_cli(self.raw_path)
        res_sparse = self.run_cli(self.sparse_path)
        self.assertEqual(res_raw.returncode, 0, res_raw.stderr)
        self.assertEqual(res_sparse.returncode, 0, res_sparse.stderr)
        self.assertEqual(res_raw.stdout, res_sparse.stdout)
        self.assertIn("vendor_a", res_raw.stdout)
        self.assertIn("extents 2", res_raw.stdout)
        self.assertIn("system_a", res_raw.stdout)
        self.assertIn("extents 1", res_raw.stdout)

    def test_extract_identical_and_matches_payload(self):
        for name, expected in self.payloads.items():
            out_raw = os.path.join(self.tmpdir.name, f"{name}_raw.img")
            out_sparse = os.path.join(self.tmpdir.name, f"{name}_sparse.img")

            res_raw = self.run_cli(self.raw_path, name, out_raw)
            res_sparse = self.run_cli(self.sparse_path, name, out_sparse)
            self.assertEqual(res_raw.returncode, 0, res_raw.stderr)
            self.assertEqual(res_sparse.returncode, 0, res_sparse.stderr)
            self.assertEqual(res_raw.stdout, res_sparse.stdout)
            self.assertEqual(res_raw.stdout.strip(), f"wrote {name} {len(expected)}")

            with open(out_raw, "rb") as f:
                data_raw = f.read()
            with open(out_sparse, "rb") as f:
                data_sparse = f.read()

            self.assertEqual(data_raw, expected)
            self.assertEqual(data_sparse, expected)
            self.assertEqual(data_raw, data_sparse)

    def test_sparse_reader_unaligned_and_custom_hdr_sizes(self):
        custom_sparse = encode_sparse(
            self.raw_bytes, file_hdr_sz=36, chunk_hdr_sz=16, include_crc=True
        )
        custom_path = os.path.join(self.tmpdir.name, "custom_sparse.img")
        with open(custom_path, "wb") as f:
            f.write(custom_sparse)

        with open(custom_path, "rb") as fh:
            reader = lp_extract.open_super_reader(fh)
            # Read across FILL + DONT_CARE + RAW boundary at an unaligned offset
            off = 64 * SECTOR_SZ + BLK_SZ + 13
            length = BLK_SZ * 3 + 77
            reader.seek(off)
            got = reader.read(length)
            self.assertEqual(got, self.raw_bytes[off : off + length])

            # SEEK_CUR and SEEK_END
            pos = reader.seek(-100, os.SEEK_CUR)
            self.assertEqual(pos, off + length - 100)
            self.assertEqual(reader.read(100), self.raw_bytes[pos : pos + 100])

            end_pos = reader.seek(-64, os.SEEK_END)
            self.assertEqual(reader.read(64), self.raw_bytes[end_pos:])
            self.assertEqual(reader.read(10), b"")

    def test_garbage_exits_with_error(self):
        for label, blob in (
            ("empty", b""),
            ("short", b"not a super image"),
            ("zeros_16k", b"\x00" * 16384),
            ("bad_sparse", struct.pack("<IHHHHIIII", 0xED26FF3A, 1, 0, 28, 12, 4096, 1, 1, 0)),
        ):
            bad_path = os.path.join(self.tmpdir.name, f"{label}.img")
            with open(bad_path, "wb") as f:
                f.write(blob)
            res = self.run_cli(bad_path)
            self.assertNotEqual(res.returncode, 0, label)
            self.assertIn("not an Android super image (raw or sparse)", res.stderr, label)


if __name__ == "__main__":
    unittest.main()
