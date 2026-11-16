#!/usr/bin/env bash
# Extract the Himax HX83102P touch firmware from the unit's own stock
# `super` image and, with --install, copy it to the running tablet as
# /usr/lib/firmware/himax/hx83102p.bin. The firmware is Lenovo's and is
# not redistributable: it stays under private/ and on the unit.
#
# Usage: tools/touch-firmware.sh <super.img> [--install]
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SUPER="${1:?usage: $0 <super.img> [--install]}"
OUT="$REPO/private/extracted"
mkdir -p "$OUT"
python3 -I "$REPO/tools/lp-extract.py" "$SUPER" vendor_a "$OUT/vendor_a.img"
docker run --rm -v "$OUT:/x" alpine:3.22 sh -ec '
    apk add -q e2fsprogs >/dev/null
    debugfs -R "dump /firmware/Himax_firmware.bin /x/Himax_firmware.bin" /x/vendor_a.img'
rm -f "$OUT/vendor_a.img"
ls -l "$OUT/Himax_firmware.bin" | awk '{print "firmware:", $5, "bytes"}'
if [[ "${2:-}" == "--install" ]]; then
    ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        -o LogLevel=ERROR root@192.168.77.1 \
        'install -d /usr/lib/firmware/himax && cat > /usr/lib/firmware/himax/hx83102p.bin' \
        < "$OUT/Himax_firmware.bin"
    echo "installed /usr/lib/firmware/himax/hx83102p.bin"
fi
