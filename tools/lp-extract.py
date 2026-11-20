#!/usr/bin/env python3
"""Minimal Android logical-partition (super) metadata reader.

Supports both raw and Android sparse super images: lists partitions with their
sizes and extent counts, or copies one partition out (linear extents only).
"""

from __future__ import annotations

import bisect
import os
import struct
import sys

SPARSE_MAGIC = 0xED26FF3A
CHUNK_RAW = 0xCAC1
CHUNK_FILL = 0xCAC2
CHUNK_DONT_CARE = 0xCAC3
CHUNK_CRC32 = 0xCAC4

LP_GEOMETRY_OFFSET = 4096
LP_GEOMETRY_MAGIC = 0x616C4467
LP_METADATA_OFFSET = 4096 * 3
LP_METADATA_MAGIC = 0x414C5030
SECTOR_SIZE = 512

NOT_SUPER_MSG = "not an Android super image (raw or sparse)"


class SparseReader:
    """Seekable, read-only view of an Android sparse image's unsparsed bytes."""

    def __init__(self, fh) -> None:
        self._fh = fh
        fh.seek(0)
        hdr = fh.read(28)
        if len(hdr) < 28:
            raise ValueError("truncated sparse header")
        (
            magic,
            _major,
            _minor,
            file_hdr_sz,
            chunk_hdr_sz,
            blk_sz,
            _total_blks,
            total_chunks,
            _checksum,
        ) = struct.unpack("<IHHHHIIII", hdr)
        if magic != SPARSE_MAGIC:
            raise ValueError("bad sparse magic")
        if file_hdr_sz < 28 or chunk_hdr_sz < 12 or blk_sz == 0:
            raise ValueError("invalid sparse header dimensions")

        chunks = []
        file_off = file_hdr_sz
        out_off = 0
        for _ in range(total_chunks):
            fh.seek(file_off)
            chdr = fh.read(12)
            if len(chdr) < 12:
                raise ValueError("truncated sparse chunk header")
            ctype, _reserved, chunk_sz, total_sz = struct.unpack("<HHII", chdr)
            if total_sz < chunk_hdr_sz:
                raise ValueError("invalid sparse chunk size")
            payload_off = file_off + chunk_hdr_sz
            payload_sz = total_sz - chunk_hdr_sz
            out_len = chunk_sz * blk_sz

            if ctype == CHUNK_RAW:
                if payload_sz < out_len:
                    raise ValueError("truncated RAW chunk")
                if out_len > 0:
                    chunks.append((out_off, out_off + out_len, CHUNK_RAW, payload_off))
            elif ctype == CHUNK_FILL:
                if payload_sz < 4:
                    raise ValueError("truncated FILL chunk")
                fh.seek(payload_off)
                pat = fh.read(4)
                if len(pat) < 4:
                    raise ValueError("short read in FILL chunk")
                if out_len > 0:
                    chunks.append((out_off, out_off + out_len, CHUNK_FILL, pat))
            elif ctype == CHUNK_DONT_CARE:
                if out_len > 0:
                    chunks.append((out_off, out_off + out_len, CHUNK_DONT_CARE, None))
            elif ctype == CHUNK_CRC32:
                if payload_sz < 4:
                    raise ValueError("truncated CRC32 chunk")
            else:
                raise ValueError("unknown sparse chunk type: 0x%x" % ctype)

            out_off += out_len
            file_off += total_sz

        self._chunks = chunks
        self._starts = [c[0] for c in chunks]
        self._size = out_off
        self._pos = 0

    def seek(self, offset: int, whence: int = os.SEEK_SET) -> int:
        if whence == os.SEEK_SET:
            target = offset
        elif whence == os.SEEK_CUR:
            target = self._pos + offset
        elif whence == os.SEEK_END:
            target = self._size + offset
        else:
            raise ValueError("invalid whence: %r" % whence)
        if target < 0:
            raise ValueError("negative seek position: %d" % target)
        self._pos = target
        return self._pos

    def read(self, n: int = -1) -> bytes:
        if n < 0:
            n = max(0, self._size - self._pos)
        if n == 0 or self._pos >= self._size:
            return b""

        left = min(n, self._size - self._pos)
        parts = []
        idx = bisect.bisect_right(self._starts, self._pos) - 1
        while left > 0 and idx < len(self._chunks):
            start, end, ctype, info = self._chunks[idx]
            take = min(left, end - self._pos)
            if ctype == CHUNK_RAW:
                self._fh.seek(info + (self._pos - start))
                data = self._fh.read(take)
                if not data:
                    break
                take = len(data)
            elif ctype == CHUNK_FILL:
                rot = (self._pos - start) % 4
                pat = info[rot:] + info[:rot]
                data = (pat * ((take + 3) // 4))[:take]
            else:
                data = b"\x00" * take
            parts.append(data)
            self._pos += take
            left -= take
            if self._pos == end:
                idx += 1
        return b"".join(parts)


def open_super_reader(fh):
    """Return a SparseReader for sparse images or the raw file handle."""
    fh.seek(0)
    magic_bytes = fh.read(4)
    fh.seek(0)
    if len(magic_bytes) == 4 and struct.unpack("<I", magic_bytes)[0] == SPARSE_MAGIC:
        return SparseReader(fh)
    return fh


def read_partitions(reader):
    """Parse super geometry and partition/extent tables from reader."""
    reader.seek(LP_GEOMETRY_OFFSET)
    geo = reader.read(52)
    if len(geo) < 52:
        raise ValueError(NOT_SUPER_MSG)
    magic, _struct_size = struct.unpack_from("<II", geo, 0)
    if magic != LP_GEOMETRY_MAGIC:
        raise ValueError(NOT_SUPER_MSG)

    reader.seek(LP_METADATA_OFFSET)
    hdr = reader.read(256)
    if len(hdr) < 256:
        raise ValueError(NOT_SUPER_MSG)
    m, _major, _minor, hsize = struct.unpack_from("<IHHI", hdr, 0)
    if m != LP_METADATA_MAGIC:
        raise ValueError(NOT_SUPER_MSG)

    # Header: magic, major, minor, header_size, header_checksum[32],
    # tables_size, tables_checksum[32], then 4 table descriptors (offset, num, entry_size).
    off = 4 + 2 + 2 + 4 + 32 + 4 + 32
    descs = [struct.unpack_from("<III", hdr, off + 12 * i) for i in range(4)]
    tables_base = LP_METADATA_OFFSET + hsize
    tables_len = sum(d[1] * d[2] for d in descs) + max(d[0] for d in descs)
    reader.seek(tables_base)
    tables = reader.read(tables_len)
    (poff, pn, psz), (eoff, en, esz) = descs[0], descs[1]
    if len(tables) < max(poff + pn * psz, eoff + en * esz):
        raise ValueError(NOT_SUPER_MSG)

    exts = [struct.unpack_from("<QIQI", tables, eoff + i * esz) for i in range(en)]
    parts = []
    for i in range(pn):
        e = tables[poff + i * psz : poff + (i + 1) * psz]
        name = e[:36].split(b"\0")[0].decode()
        _attrs, first, num, _group = struct.unpack_from("<IIII", e, 36)
        size = sum(exts[j][0] for j in range(first, first + num)) * SECTOR_SIZE
        parts.append((name, size, exts[first : first + num]))
    return parts


def extract_partition(reader, ext_list, out_path: str) -> None:
    """Copy linear extents of a partition to out_path."""
    with open(out_path, "wb") as out_fh:
        for nsec, ttype, tdata, _tsrc in ext_list:
            if ttype != 0:
                raise ValueError("non-linear extent")
            reader.seek(tdata * SECTOR_SIZE)
            left = nsec * SECTOR_SIZE
            while left:
                chunk = reader.read(min(left, 1 << 24))
                if not chunk:
                    raise ValueError("unexpected end of super image")
                out_fh.write(chunk)
                left -= len(chunk)


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) not in (1, 3):
        print("usage: lp-extract.py <super.img> [<name> <out.img>]", file=sys.stderr)
        return 1

    img = args[0]
    want = args[1] if len(args) == 3 else None
    out_path = args[2] if len(args) == 3 else None

    try:
        with open(img, "rb") as fh:
            reader = open_super_reader(fh)
            parts = read_partitions(reader)
            if want is None:
                for name, size, ext_list in parts:
                    print("%-24s %10d MiB extents %d" % (name, size >> 20, len(ext_list)))
                return 0

            for name, size, ext_list in parts:
                if name == want:
                    extract_partition(reader, ext_list, out_path)
                    print("wrote", name, size)
                    return 0
            print("partition not found: %s" % want, file=sys.stderr)
            return 1
    except (OSError, ValueError, struct.error) as exc:
        msg = str(exc) if str(exc) == NOT_SUPER_MSG else "%s (%s)" % (NOT_SUPER_MSG, exc)
        print(msg, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
