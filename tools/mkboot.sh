#!/usr/bin/env bash
# Pack a Linux boot image and an empty dtbo image for the YT-J706F.
#
# Usage: tools/mkboot.sh [--cmdline "extra args"] <Image.gz> <board.dtb> <initramfs.cpio.gz> <out dir>
#
# Writes <out dir>/boot.img (Android boot image header v2, the stock
# layout: kernel at 0x40080000, ramdisk at 0x47c80000, tags and DTB at
# 0x4bc80000, page 2048, os 12.0.0 / 2024-10) and <out dir>/dtbo.img (one
# empty overlay, so LK does not apply Lenovo's board overlay to the
# mainline DTB). LK keeps "bootopt=..." first and appends its own
# androidboot.* arguments, the serial number among them: never print the
# resulting /proc/cmdline.

set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# mem_sleep_default=s2idle: the "deep" suspend never wakes up on mainline
# (docs/hardware/BOARD.md, Suspend).
EXTRA="console=tty0 loglevel=7 panic=5 oops=panic mem_sleep_default=s2idle"
if [[ "${1:-}" = "--cmdline" ]]; then EXTRA="$EXTRA $2"; shift 2; fi
[[ $# -eq 4 ]] || { sed -n '2,4p' "$0"; exit 2; }
KERNEL="$1" DTB="$2" RAMDISK="$3" OUT="$4"
mkdir -p "$OUT"
for f in "$KERNEL" "$DTB" "$RAMDISK"; do [[ -f "$f" ]] || { echo "missing: $f" >&2; exit 2; }; done
abs() { (cd "$(dirname "$1")" && echo "$(pwd -P)/$(basename "$1")"); }
KERNEL=$(abs "$KERNEL") DTB=$(abs "$DTB") RAMDISK=$(abs "$RAMDISK") OUT=$(cd "$OUT" && pwd -P)

STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
printf '/dts-v1/;\n/plugin/;\n/ {\n};\n' > "$STAGE/empty.dts"
dtc -@ -q -I dts -O dtb -o "$STAGE/empty.dtbo" "$STAGE/empty.dts"
python3 -I "$REPO/tools/mkdtbo.py" -o "$OUT/dtbo.img" "$STAGE/empty.dtbo"

docker run --rm --platform linux/arm64 \
    -v "$KERNEL:/in/kernel:ro" -v "$DTB:/in/dtb:ro" -v "$RAMDISK:/in/ramdisk:ro" \
    -v "$OUT:/out" lenovomarchy-kbuild \
    mkbootimg --header_version 2 --os_version 12.0.0 --os_patch_level 2024-10 \
        --kernel /in/kernel --ramdisk /in/ramdisk --dtb /in/dtb \
        --pagesize 2048 --base 0 --kernel_offset 0x40080000 \
        --ramdisk_offset 0x47c80000 --second_offset 0 \
        --tags_offset 0x4bc80000 --dtb_offset 0x4bc80000 \
        --board "" --cmdline "bootopt=64S3,32N2,64N2 $EXTRA" \
        -o /out/boot.img
size=$(stat -f %z "$OUT/boot.img" 2>/dev/null || stat -c %s "$OUT/boot.img")
echo "$OUT/boot.img: $size bytes (boot_a/b hold 33554432)"
(( size <= 33554432 )) || { echo "boot image too large" >&2; exit 1; }
