#!/usr/bin/env python3
# yt11-pagedump name=base[:size] ... : dump 32-bit words of whole register pages.
import mmap, os, struct, sys
fd = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)
for a in sys.argv[1:]:
    name, spec = a.split("=")
    base, _, size = spec.partition(":")
    base = int(base, 16); size = int(size, 16) if size else 0x1000
    m = mmap.mmap(fd, size, mmap.MAP_SHARED, mmap.PROT_READ, offset=base)
    for o in range(0, size, 4):
        print("%s %03x %08x" % (name, o, struct.unpack_from("<I", m, o)[0]))
