#!/usr/bin/env bash
# Back up every partition of the YT-J706F except userdata, over adb as root
# (adbd must already run as root, e.g. on the stock boot-debug image).
#
# Usage: tools/backup-partitions.sh <output dir>
#
# Each partition is read on the tablet with dd and streamed to the Mac with
# `adb exec-out`; its SHA-256 is computed on the tablet first and checked
# against the copy. The UFS boot LUs (sda, sdb: the preloader) and the main
# LU's primary and backup GPT are saved as well. The output holds
# unit-specific data (calibration, serial numbers): keep it in private/.

set -euo pipefail
OUT="${1:?usage: $0 <output dir>}"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=tools/yt.sh
. "$REPO/tools/yt.sh"
[ -n "$YT_T" ] || exit 1
[ "$(yt id -u | tr -d '\r')" = 0 ] || { echo "adbd is not root" >&2; exit 1; }
mkdir -p "$OUT"
LOG="$OUT/backup.log"
: > "$OUT/SHA256SUMS"

save() { # <name> <device path> [<dd args>]
    local name="$1" dev="$2" args="${3:-bs=4194304}" want got
    want=$(yt "dd if=$dev $args 2>/dev/null | sha256sum" | awk '{print $1}')
    ytadb exec-out "dd if=$dev $args 2>/dev/null" > "$OUT/$name.img"
    got=$(shasum -a 256 "$OUT/$name.img" | awk '{print $1}')
    if [ "$want" = "$got" ]; then
        echo "$got  $name.img" >> "$OUT/SHA256SUMS"
        echo "ok   $name $(stat -f %z "$OUT/$name.img") bytes" | tee -a "$LOG"
    else
        echo "FAIL $name: device $want, copy $got" | tee -a "$LOG"
        return 1
    fi
}

parts=$(yt 'ls /dev/block/by-name/' | tr -d '\r' | grep -vxE 'userdata|sda|sdb|sdc|preloader_raw_a|preloader_raw_b')
for p in $parts; do
    save "$p" "/dev/block/by-name/$p"
done
save ufs-lu-sda /dev/block/sda
save ufs-lu-sdb /dev/block/sdb
# Main LU: primary GPT (first 8 blocks of 4 KiB) and backup GPT (last 8).
# /sys/block/*/size counts 512-byte sectors whatever the block size.
blocks=$(( $(yt 'cat /sys/block/sdc/size' | tr -d '\r') / 8 ))
save sdc-gpt-primary /dev/block/sdc "bs=4096 count=8"
save sdc-gpt-backup /dev/block/sdc "bs=4096 skip=$((blocks - 8)) count=8"
echo "done: $(wc -l < "$OUT/SHA256SUMS") images" | tee -a "$LOG"
