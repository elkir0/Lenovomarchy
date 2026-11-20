#!/usr/bin/env bash
# One-command installer for Omarchy Linux on the Lenovo YT-J706F from release files.
#
# Usage:
#   tools/install.sh --key <key.pub> [--firmware <super.img>] [--slot a|b]
#                    [--yes] [--dry-run] <rootfs.img|rootfs.img.xz|rootfs.img.zst> <boot.img> <dtbo.img>

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
    cat >&2 <<'EOF'
usage: tools/install.sh --key <key.pub> [--firmware <super.img>] [--slot a|b]
                        [--yes] [--dry-run] <rootfs.img|rootfs.img.xz|rootfs.img.zst> <boot.img> <dtbo.img>
EOF
}

KEY=""
FIRMWARE=""
SLOT="a"
YES=0
DRY_RUN=0
POSITIONAL=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --key)
            [[ $# -ge 2 ]] || { echo "error: --key requires an argument" >&2; usage; exit 1; }
            KEY="$2"
            shift 2
            ;;
        --firmware)
            [[ $# -ge 2 ]] || { echo "error: --firmware requires an argument" >&2; usage; exit 1; }
            FIRMWARE="$2"
            shift 2
            ;;
        --slot)
            [[ $# -ge 2 ]] || { echo "error: --slot requires an argument" >&2; usage; exit 1; }
            SLOT="$2"
            shift 2
            ;;
        --yes)
            YES=1
            shift
            ;;
        --dry-run)
            DRY_RUN=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        --)
            shift
            while [[ $# -gt 0 ]]; do
                POSITIONAL+=("$1")
                shift
            done
            ;;
        -*)
            echo "error: unknown option: $1" >&2
            usage
            exit 1
            ;;
        *)
            POSITIONAL+=("$1")
            shift
            ;;
    esac
done

if [[ ${#POSITIONAL[@]} -ne 3 ]]; then
    echo "error: expected 3 positional arguments (<rootfs> <boot.img> <dtbo.img>), got ${#POSITIONAL[@]}" >&2
    usage
    exit 1
fi

ROOTFS="${POSITIONAL[0]}"
BOOT="${POSITIONAL[1]}"
DTBO="${POSITIONAL[2]}"

if [[ "$SLOT" != "a" && "$SLOT" != "b" ]]; then
    echo "error: --slot must be a or b (got '$SLOT')" >&2
    exit 1
fi

if [[ -z "$KEY" ]]; then
    echo "error: --key <key.pub> is required: the image accepts SSH by key only, and the firmware step needs it" >&2
    usage
    exit 1
fi

case "$ROOTFS" in
    *.img|*.img.xz|*.img.zst) ;;
    *)
        echo "error: rootfs must end in .img, .img.xz, or .img.zst (got '$ROOTFS')" >&2
        exit 1
        ;;
esac

run_cmd() {
    if [[ "$DRY_RUN" = 1 ]]; then
        printf 'DRY:'
        printf ' %s' "$@"
        printf '\n'
    else
        "$@"
    fi
}

wait_for_linux() {
    local start="$SECONDS"
    while (( SECONDS - start < 300 )); do
        if "$REPO/tools/ytssh" true 2>/dev/null; then
            return 0
        fi
        sleep 5
    done
    cat >&2 <<'EOF'
error: timed out after 300 s waiting for Linux on the USB network (192.168.77.1)
Recovery hints (see docs/TROUBLESHOOTING.md):
  - Check the USB cable and verify the CDC-ECM Ethernet interface came up on the host.
  - On first boot the rootfs resize can take a little time; wait briefly or reboot the tablet.
  - If the slot failed to boot, reboot to fall back to the other slot or catch the preloader with fastboot.
EOF
    return 3
}

# Step 1: Check the host
echo "==> Checking host tools"
missing=()
for cmd in fastboot python3 ssh; do
    command -v "$cmd" >/dev/null 2>&1 || missing+=("$cmd")
done
if ! command -v docker >/dev/null 2>&1; then
    missing+=("docker")
elif ! docker info >/dev/null 2>&1; then
    missing+=("docker (daemon not reachable via 'docker info')")
fi
case "$ROOTFS" in
    *.xz)
        command -v xz >/dev/null 2>&1 || missing+=("xz")
        ;;
    *.zst)
        command -v zstd >/dev/null 2>&1 || missing+=("zstd")
        ;;
esac
if [[ ${#missing[@]} -gt 0 ]]; then
    echo "error: missing required host tools:" >&2
    for item in "${missing[@]}"; do
        echo "  - $item" >&2
    done
    exit 1
fi

# Step 2: Check inputs
echo "==> Checking input files (slot: $SLOT)"
for f in "$KEY" "$ROOTFS" "$BOOT" "$DTBO"; do
    if [[ ! -f "$f" ]]; then
        echo "error: input file not found: $f" >&2
        exit 1
    fi
done
if [[ -n "$FIRMWARE" && ! -f "$FIRMWARE" ]]; then
    echo "error: firmware super image not found: $FIRMWARE" >&2
    exit 1
fi

# Step 3: Confirmation
echo "==> Confirming flash target"
if [[ "$DRY_RUN" = 1 ]]; then
    echo "dry-run: skipping ERASE confirmation"
elif [[ "$YES" != 1 ]]; then
    echo "WARNING: This will erase everything on the tablet's 'userdata' partition (Android's data or a previous Linux install)."
    printf 'Type ERASE to continue: '
    IFS= read -r reply || true
    if [[ "$reply" != "ERASE" ]]; then
        echo "aborted" >&2
        exit 1
    fi
fi

# Step 4: Decompress .xz/.zst next to itself if needed
echo "==> Preparing rootfs image"
case "$ROOTFS" in
    *.xz)
        IMG="${ROOTFS%.xz}"
        if [[ ! -f "$IMG" || "$ROOTFS" -nt "$IMG" ]]; then
            run_cmd xz -dkf "$ROOTFS"
        else
            echo "using up-to-date $IMG"
        fi
        ;;
    *.zst)
        IMG="${ROOTFS%.zst}"
        if [[ ! -f "$IMG" || "$ROOTFS" -nt "$IMG" ]]; then
            run_cmd zstd -dkf "$ROOTFS"
        else
            echo "using up-to-date $IMG"
        fi
        ;;
    *)
        IMG="$ROOTFS"
        ;;
esac

# Step 5: Install SSH key into rootfs image
echo "==> Installing SSH key into rootfs image"
run_cmd "$REPO/tools/image-set-key.sh" "$IMG" "$KEY"

# Step 6: Flash rootfs and boot slot
echo "==> Flashing rootfs and slot $SLOT"
run_cmd "$REPO/tools/flash-rootfs.sh" "$IMG"
run_cmd "$REPO/tools/flash-slot.sh" "$SLOT" "$BOOT" "$DTBO"

# Step 7: Wait for Linux on the USB network
echo "==> Waiting for Linux on the USB network"
if [[ "$DRY_RUN" = 1 ]]; then
    echo "dry-run: skipping wait for tools/ytssh true"
else
    wait_for_linux
fi

# Step 8: Install firmware from super.img or remind how to run later
if [[ -n "$FIRMWARE" ]]; then
    echo "==> Extracting and installing device firmware"
    run_cmd "$REPO/tools/touch-firmware.sh" "$FIRMWARE" --install
    run_cmd "$REPO/tools/amp-firmware.sh" "$FIRMWARE" --install
    run_cmd "$REPO/tools/mic-firmware.sh" "$FIRMWARE" --install
    run_cmd "$REPO/tools/ytssh" systemctl reboot || true
    if [[ "$DRY_RUN" = 1 ]]; then
        echo "dry-run: skipping post-reboot wait for tools/ytssh true"
    else
        # Let the old system go down first, or the poll answers at once.
        sleep 20
        wait_for_linux
    fi
else
    echo "==> Device firmware skipped (no --firmware)"
    cat <<'EOF'
Note: touch, speaker protection, and microphones need firmware from your stock super.img.
Run these later once the tablet is booted and connected over USB:
  tools/touch-firmware.sh <super.img> --install
  tools/amp-firmware.sh <super.img> --install
  tools/mic-firmware.sh <super.img> --install
  tools/ytssh systemctl reboot
EOF
fi

# Step 9: Closing notes
echo "==> Install complete"
cat <<'EOF'
Next steps on the tablet:
  - User account: alarm / password: alarm (change it with: omamobile-set-pin)
  - Connect to Wi-Fi from quick settings
  - Open a root shell over USB anytime with: tools/ytssh
  - Set your time zone with: timedatectl set-timezone <Region/City>
EOF
