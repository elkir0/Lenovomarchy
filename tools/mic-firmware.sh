#!/usr/bin/env bash
# Extract the AS33970 voice processor's firmware image (Synaptics "Tahiti",
# second-stage loader plus system image) from the unit's own stock `super`
# image and, with --install, copy it to the running tablet under the name the
# kernel's as33970 driver asks for. The chip has no flash: the driver loads
# this file at every start, and the microphones stay silent without it.
# The file is not redistributable: it stays under private/ and on the unit.
#
# Usage: tools/mic-firmware.sh <super.img> [--install]
#        tools/mic-firmware.sh --install     (file already in private/)
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$REPO/private/extracted/tahiti"
FILE=partition_boot2flash.img

if [[ "${1:-}" != "--install" ]]; then
    SUPER="${1:?usage: $0 <super.img> [--install] | --install}"
    shift
    mkdir -p "$OUT"
    python3 -I "$REPO/tools/lp-extract.py" "$SUPER" vendor_a "$OUT/vendor_a.img"
    docker run --rm -v "$OUT:/x" alpine:3.22 sh -ec "
        apk add -q e2fsprogs e2fsprogs-extra >/dev/null
        debugfs -R \"dump /etc/tahiti_dsp/$FILE /x/$FILE\" /x/vendor_a.img"
    rm -f "$OUT/vendor_a.img"
    ls -l "$OUT/$FILE" | awk '{print $NF ":", $5, "bytes"}'
fi

if [[ "${1:-}" == "--install" ]]; then
    ssh_tab() {
        ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
            -o LogLevel=ERROR "root@${YT11_HOST:-192.168.77.1}" "$@"
    }
    dst=/usr/lib/firmware/tahiti
    ssh_tab "install -d $dst"
    ssh_tab "cat > $dst/$FILE" < "$OUT/$FILE"
    ssh_tab "ls -l $dst/$FILE" | awk '{print "installed", $NF}'
fi
