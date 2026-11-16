#!/usr/bin/env python3
# Minimal Android logical-partition (super) metadata reader: list partitions
# and their extents, or copy one partition out (linear extents only).
import struct, sys
img, want, out = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else None), (sys.argv[3] if len(sys.argv) > 3 else None)
f = open(img, "rb")
f.seek(4096); geo = f.read(52)
magic, struct_size = struct.unpack_from("<II", geo, 0)
assert magic == 0x616C4467, hex(magic)
max_meta, slots, block_size = struct.unpack_from("<III", geo, 40)
f.seek(4096 * 3); hdr = f.read(256)
m, major, minor, hsize = struct.unpack_from("<IHHI", hdr, 0)
assert m == 0x414C5030, hex(m)
# header: magic,major,minor,header_size,header_checksum[32],tables_size,tables_checksum[32], then 4 table descriptors (offset,num,entry_size)
off = 4 + 2 + 2 + 4 + 32 + 4 + 32
descs = [struct.unpack_from("<III", hdr, off + 12 * i) for i in range(4)]
tables_base = 4096 * 3 + hsize
f.seek(tables_base); tables = f.read(sum(d[1] * d[2] for d in descs) + max(d[0] for d in descs))
(poff, pn, psz), (eoff, en, esz) = descs[0], descs[1]
exts = [struct.unpack_from("<QIQI", tables, eoff + i * esz) for i in range(en)]
for i in range(pn):
    e = tables[poff + i * psz: poff + (i + 1) * psz]
    name = e[:36].split(b"\0")[0].decode()
    attrs, first, num, group = struct.unpack_from("<IIII", e, 36)
    size = sum(exts[j][0] for j in range(first, first + num)) * 512
    if want is None:
        print("%-24s %10d MiB extents %d" % (name, size >> 20, num))
    elif name == want:
        with open(out, "wb") as o:
            for j in range(first, first + num):
                nsec, ttype, tdata, tsrc = exts[j]
                assert ttype == 0, "non-linear extent"
                f.seek(tdata * 512); left = nsec * 512
                while left:
                    chunk = f.read(min(left, 1 << 24)); o.write(chunk); left -= len(chunk)
        print("wrote", name, size)
