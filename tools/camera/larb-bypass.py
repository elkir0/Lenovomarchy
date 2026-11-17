#!/usr/bin/env python3
"""Clear MMU_EN (bit 0 of SMI_LARB_NONSEC_CON) on MT6785 LARB6 and LARB7 ports.

Without camera IOMMU port bindings, CAMSV IMGO DMA writes to a contiguous CMA
physical address; clearing MMU_EN stops the SMI local arbiters from treating
the physical address as an IOVA. Requires CONFIG_DEVMEM=y (no IO_STRICT_DEVMEM)
and active CAM power/LARB clocks (e.g. via /sys/kernel/debug/camsv-tm/power=1).

Usage:
  sudo python3 larb-bypass.py [--status]
"""

import argparse
import mmap
import os
import struct
import sys

LARBS = (
    ('larb6', 0x1A001000, 31),
    ('larb7', 0x1A002000, 5),
)
SMI_LARB_NONSEC_CON_BASE = 0x380


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Disable MMU_EN on MT6785 camera LARB6/LARB7 ports via /dev/mem.'
    )
    parser.add_argument(
        '--status',
        action='store_true',
        help='Read and print MMU_EN bits without modifying registers.',
    )
    args = parser.parse_args()

    flags = os.O_RDONLY if args.status else (os.O_RDWR | os.O_SYNC)
    prot = mmap.PROT_READ if args.status else (mmap.PROT_READ | mmap.PROT_WRITE)

    try:
        fd = os.open('/dev/mem', flags)
    except OSError as exc:
        print(f'error: cannot open /dev/mem: {exc.strerror}', file=sys.stderr)
        return 1

    try:
        for name, base, nports in LARBS:
            m = mmap.mmap(fd, 0x1000, mmap.MAP_SHARED, prot, offset=base)
            try:
                if not args.status:
                    for i in range(nports):
                        off = SMI_LARB_NONSEC_CON_BASE + 4 * i
                        val = struct.unpack_from('<I', m, off)[0]
                        struct.pack_into('<I', m, off, val & ~1)
                bits = ''.join(
                    str(struct.unpack_from('<I', m, SMI_LARB_NONSEC_CON_BASE + 4 * i)[0] & 1)
                    for i in range(nports)
                )
                print(f'{name} (0x{base:08x}, {nports} ports) MMU_EN: {bits}')
            finally:
                m.close()
    finally:
        os.close(fd)

    return 0


if __name__ == '__main__':
    sys.exit(main())
