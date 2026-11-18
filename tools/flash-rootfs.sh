#!/usr/bin/env bash
# Write a root filesystem image (image/build-rootfs.sh) to `userdata` on the
# YT-J706F. Everything on the tablet's Linux side is lost. The tablet stays
# in fastboot afterwards: finish with tools/flash-slot.sh, which writes the
# matching boot image and reboots.
#
# Usage: tools/flash-rootfs.sh <rootfs.img>
#
# The raw ext4 image is converted to a sparse one first (img2simg in the
# lenovomarchy-kbuild Docker image), next to it as <rootfs>.simg. Fastboot is
# reached the way tools/flash-slot.sh does. Only `userdata` is written.

set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMG="${1:?usage: $0 <rootfs.img>}"
IMG="$(cd "$(dirname "$IMG")" && pwd)/$(basename "$IMG")"
SIMG="${IMG%.img}.simg"

if [[ ! -f "$SIMG" || "$IMG" -nt "$SIMG" ]]; then
    docker run --rm --platform linux/arm64 -v "$IMG:/img/rootfs.img:ro" \
        -v "$(dirname "$SIMG"):/out" lenovomarchy-kbuild sh -ec '
            command -v img2simg >/dev/null || { apt-get update -qq >/dev/null; apt-get install -y -qq android-sdk-libsparse-utils >/dev/null; }
            img2simg /img/rootfs.img "/out/'"$(basename "$SIMG")"'"'
fi
ls -l "$SIMG" | awk '{print "sparse image:", $5, "bytes"}'

fb_count() { fastboot devices 2>/dev/null | wc -l | tr -d ' '; }

if [[ "$(fb_count)" != 1 ]]; then
    # shellcheck source=tools/yt.sh
    . "$REPO/tools/yt.sh" 2>/dev/null || true
    if [[ -n "${YT_T:-}" ]]; then
        ytadb reboot bootloader
    else
        echo "tablet not in adb: waiting for the preloader at its next boot"
        python3 "$REPO/tools/mtk-preloader/preloader_fastboot.py" --once --wait 300 &
        pf=$!
        sleep 1
        if "$REPO/tools/ytssh" true 2>/dev/null; then
            echo "Linux answers on the USB network: rebooting it"
            "$REPO/tools/ytssh" 'sync; (sleep 1; reboot -f) >/dev/null 2>&1 &' || true
        fi
        wait "$pf" || true
    fi
    for _ in $(seq 1 60); do [[ "$(fb_count)" = 1 ]] && break; sleep 1; done
fi
[[ "$(fb_count)" = 1 ]] || { echo "expected exactly one fastboot device" >&2; exit 1; }

fastboot flash userdata "$SIMG" 2>&1 | grep -vi serial
echo "userdata written; now run tools/flash-slot.sh <a|b> <boot.img> [<dtbo.img>]"
