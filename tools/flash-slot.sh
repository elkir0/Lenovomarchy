#!/usr/bin/env bash
# Flash a Linux boot image (and its dtbo) to one slot of the YT-J706F and
# boot it once.
#
# Usage: tools/flash-slot.sh <a|b> <boot.img> [<dtbo.img>]
#
# Reaches fastboot from Android (adb, tablet targeted by transport id) or,
# when adb does not see the tablet, by answering the preloader's handshake
# at the next boot (tools/mtk-preloader). Only boot_<slot> and dtbo_<slot>
# are written. With slot-retry-count 1, a Linux boot that never marks its
# slot successful falls back to the other slot at the next reboot.

set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SLOT="${1:?usage: $0 <a|b> <boot.img> [<dtbo.img>]}"
BOOT="${2:?boot image}"
DTBO="${3:-}"
[[ "$SLOT" = a || "$SLOT" = b ]] || { echo "slot must be a or b" >&2; exit 2; }

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
        # Linux on the tablet: ask it to reboot so the preloader shows up.
        if "$REPO/tools/ytssh" true 2>/dev/null; then
            echo "Linux answers on the USB network: rebooting it"
            "$REPO/tools/ytssh" 'sync; (sleep 1; reboot -f) >/dev/null 2>&1 &' || true
        fi
        wait "$pf" || true
    fi
    for _ in $(seq 1 60); do [[ "$(fb_count)" = 1 ]] && break; sleep 1; done
fi
[[ "$(fb_count)" = 1 ]] || { echo "expected exactly one fastboot device" >&2; exit 1; }

fastboot flash "boot_$SLOT" "$BOOT" 2>&1 | grep -vi serial
[[ -n "$DTBO" ]] && fastboot flash "dtbo_$SLOT" "$DTBO" 2>&1 | grep -vi serial
fastboot --set-active="$SLOT" 2>&1 | grep -vi serial
fastboot reboot 2>&1 | grep -vi serial
echo "flashed boot_$SLOT${DTBO:+ and dtbo_$SLOT}, slot $SLOT active, rebooting"
