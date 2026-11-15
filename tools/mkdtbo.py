#!/usr/bin/env python3
"""Pack device-tree overlay blobs into an Android DT table (dtbo image).

Usage: mkdtbo.py -o dtbo.img overlay.dtbo [overlay2.dtbo ...]

LK applies the entries of the slot's dtbo partition on top of the boot
image's DTB. The mainline DTB must not receive Lenovo's vendor overlay, so
the Linux slot gets a table holding one empty overlay instead.
"""

import argparse
import struct

MAGIC = 0xD7B7AB1E
HEADER_SIZE = 32
ENTRY_SIZE = 32
PAGE_SIZE = 2048


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-o", "--output", required=True)
    parser.add_argument("blobs", nargs="+")
    args = parser.parse_args()

    blobs = [open(path, "rb").read() for path in args.blobs]
    offset = HEADER_SIZE + ENTRY_SIZE * len(blobs)
    entries, payload = b"", b""
    for blob in blobs:
        if blob[:4] != bytes.fromhex("d00dfeed"):
            raise SystemExit("not a flattened device tree: %r" % blob[:4])
        # dt_size, dt_offset, id, rev, custom[4]
        entries += struct.pack(">8I", len(blob), offset + len(payload),
                               0, 0, 0, 0, 0, 0)
        payload += blob
    total = offset + len(payload)
    header = struct.pack(">8I", MAGIC, total, HEADER_SIZE, ENTRY_SIZE,
                         len(blobs), HEADER_SIZE, PAGE_SIZE, 0)
    with open(args.output, "wb") as out:
        out.write(header + entries + payload)
    print("%s: %d entr%s, %d bytes" % (args.output, len(blobs),
                                       "y" if len(blobs) == 1 else "ies", total))


if __name__ == "__main__":
    main()
