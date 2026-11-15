#!/usr/bin/env bash
# Build a second initramfs archive with kernel modules (and their
# dependencies, decompressed: busybox cannot load .ko.zst) and firmware,
# to append to the main initramfs (the kernel unpacks concatenated cpio
# archives in order).
#
# Usage: tools/mk-extras-cpio.sh <modules.tar.xz> <firmware dir> <out.cpio.gz> <module>...
#   <firmware dir> holds lib/firmware/... (e.g. out/firmware-extra)
#
# Example:
#   tools/mk-extras-cpio.sh out/kernel/modules.tar.xz out/firmware-extra \
#       out/extras.cpio.gz mt7663s btmtksdio

set -euo pipefail
[[ $# -ge 4 ]] || { sed -n '2,13p' "$0"; exit 2; }
MODS="$1" FW="$2" OUT="$3"; shift 3
abs() { (cd "$(dirname "$1")" && echo "$(pwd -P)/$(basename "$1")"); }
MODS=$(abs "$MODS") FW=$(cd "$FW" && pwd -P)
mkdir -p "$(dirname "$OUT")"; OUT=$(abs "$OUT")

docker run --rm --platform linux/arm64 \
    -v "$MODS:/in/modules.tar.xz:ro" -v "$FW:/in/fw:ro" -v "$(dirname "$OUT"):/out" \
    -e WANT="$*" -e NAME="$(basename "$OUT")" lenovomarchy-kbuild bash -ec '
        mkdir -p /m /stage
        tar -C /m -xJf /in/modules.tar.xz
        rel=$(ls /m/lib/modules)
        for m in $WANT; do
            modprobe -d /m -S "$rel" --show-depends "$m" | awk "/^insmod/ {print \$2}"
        done | sort -u > /tmp/list
        while read -r f; do
            rel_path=${f#/m/}
            mkdir -p "/stage/$(dirname "${rel_path%.zst}")"
            zstd -q -d -c "$f" > "/stage/${rel_path%.zst}"
        done < /tmp/list
        cp /m/lib/modules/$rel/modules.order /m/lib/modules/$rel/modules.builtin* /stage/lib/modules/$rel/ 2>/dev/null || true
        depmod -b /stage "$rel"
        cp -a /in/fw/. /stage/
        cd /stage && find . | sort | cpio -o -H newc -R 0:0 2>/dev/null | gzip -9 > "/out/$NAME"
        echo "modules:"; sed "s#.*/##" /tmp/list
        echo "firmware:"; find lib/firmware -type f | sed "s#^#  #"
    '
ls -l "$OUT" | awk '{print "archive:", $5, "bytes"}'
