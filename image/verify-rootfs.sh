#!/usr/bin/env bash
# Offline verification of out/rootfs/rootfs-omarchy-aarch64.img.
# Loop-mounts the ext4 image read-only inside an arm64 Linux container and
# verifies packages, user, firmware, kernel modules, systemd units, SSH keys,
# fstab, Hyprland monitor config, and absence of private keys or /proc/cmdline leaks.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

IMG="${1:-$ROOT_DIR/out/rootfs/rootfs-omarchy-aarch64.img}"
if [[ ! -f "$IMG" ]]; then
    echo "ERROR: image not found: $IMG" >&2
    exit 1
fi

KREL_FILE="$ROOT_DIR/input/kernel.release"
AUTH_KEYS_FILE="$ROOT_DIR/input/authorized_keys"
for req in "$KREL_FILE" "$AUTH_KEYS_FILE"; do
    if [[ ! -f "$req" ]]; then
        echo "ERROR: required input file missing: $req" >&2
        exit 1
    fi
done

IMG_DIR="$(cd "$(dirname "$IMG")" && pwd)"
IMG_BASE="$(basename "$IMG")"

# Pick an available arm64 Linux container image with pacman, mount, and e2fsck
VERIFY_CONTAINER="lenovomarchy:dev-aarch64"
if ! docker image inspect "$VERIFY_CONTAINER" >/dev/null 2>&1; then
    VERIFY_CONTAINER="lenovomarchy-rootfs:aarch64"
fi

docker run --rm --privileged --platform linux/arm64 \
    -v "$IMG_DIR/$IMG_BASE:/image/rootfs.img:ro" \
    -v "$KREL_FILE:/input/kernel.release:ro" \
    -v "$AUTH_KEYS_FILE:/input/authorized_keys:ro" \
    "$VERIFY_CONTAINER" \
    bash -ec '
        set -euo pipefail
        FAIL=0
        pass() { printf "  [PASS] %s\n" "$*"; }
        fail() { printf "  [FAIL] %s\n" "$*" >&2; FAIL=$((FAIL + 1)); }

        mkdir -p /mnt
        mount -o loop,ro /image/rootfs.img /mnt
        trap "umount /mnt 2>/dev/null || true" EXIT

        # 1. pacman -Q of hyprland, mesa, linux-firmware-mediatek, openssh (and Omarchy packages)
        for pkg in hyprland mesa linux-firmware-mediatek openssh omarchy omarchy-settings omamobile-omarchy omamobile-shell squeekboard sddm; do
            if out="$(pacman --root /mnt -Q "$pkg" 2>/dev/null)"; then
                pass "pacman -Q $pkg -> $out"
            else
                fail "pacman -Q $pkg failed (package not installed)"
            fi
        done

        # 2. Omarchy user (alarm) and Hyprland session / monitor config
        if awk -F: "\$1 == \"alarm\" && \$3 == 1000 && \$6 == \"/home/alarm\" { found=1 } END { exit !found }" /mnt/etc/passwd; then
            pass "Omarchy user alarm (UID 1000, /home/alarm) present in /etc/passwd"
        else
            fail "Omarchy user alarm missing or misconfigured in /etc/passwd"
        fi
        if grep -qE "^wheel:.*\\balarm\\b" /mnt/etc/group; then
            pass "Omarchy user alarm is in wheel group"
        else
            fail "Omarchy user alarm is not in wheel group"
        fi
        if [[ -f /mnt/etc/sddm.conf.d/autologin.conf ]] && \
           grep -q "^User=alarm$" /mnt/etc/sddm.conf.d/autologin.conf && \
           grep -q "^Session=omarchy$" /mnt/etc/sddm.conf.d/autologin.conf && \
           [[ -f /mnt/usr/share/wayland-sessions/omarchy.desktop ]]; then
            pass "Autologin into Hyprland (omarchy.desktop) configured for alarm"
        else
            fail "Autologin configuration missing or invalid"
        fi
        if [[ -f /mnt/home/alarm/.config/hypr/monitors.lua ]] && \
           grep -q "omarchy_monitor_scale = 1.5" /mnt/home/alarm/.config/hypr/monitors.lua && \
           grep -q "transform = 2" /mnt/home/alarm/.config/hypr/monitors.lua; then
            pass "Hyprland monitor config sets scale = 1.5 and transform = 2"
        else
            fail "Hyprland monitor config missing scale = 1.5 or transform = 2"
        fi

        # 3. mediatek/mt7663* firmware present
        shopt -s nullglob
        mt7663_files=(/mnt/usr/lib/firmware/mediatek/mt7663*)
        shopt -u nullglob
        if [[ ${#mt7663_files[@]} -ge 2 ]]; then
            pass "mediatek/mt7663* firmware present (${#mt7663_files[@]} files)"
        else
            fail "mediatek/mt7663* firmware missing in /usr/lib/firmware/mediatek/"
        fi

        # 4. /usr/lib/modules/$(cat input/kernel.release)/modules.dep present
        KREL="$(tr -d "[:space:]" < /input/kernel.release)"
        MOD_DEP="/mnt/usr/lib/modules/$KREL/modules.dep"
        if [[ -s "$MOD_DEP" ]]; then
            pass "/usr/lib/modules/$KREL/modules.dep present ($(wc -l < "$MOD_DEP") lines)"
        else
            fail "/usr/lib/modules/$KREL/modules.dep missing or empty"
        fi

        # 5. USB gadget service, sshd, serial-getty@ttyGS0, and resize unit enabled
        for svc_link in \
            /mnt/etc/systemd/system/multi-user.target.wants/usb-gadget.service \
            /mnt/etc/systemd/system/multi-user.target.wants/sshd.service \
            /mnt/etc/systemd/system/multi-user.target.wants/lenovomarchy-resize-rootfs.service \
            /mnt/etc/systemd/system/getty.target.wants/serial-getty@ttyGS0.service; do
            if [[ -L "$svc_link" ]]; then
                pass "service enabled: ${svc_link#/mnt}"
            else
                fail "service not enabled: ${svc_link#/mnt}"
            fi
        done

        # Verify USB gadget parameters match the brief
        GADGET_SCRIPT="/mnt/usr/local/sbin/usb-gadget-setup"
        if [[ -x "$GADGET_SCRIPT" ]] && \
           grep -q "0x1d6b" "$GADGET_SCRIPT" && \
           grep -q "0x0104" "$GADGET_SCRIPT" && \
           grep -q "Lenovomarchy" "$GADGET_SCRIPT" && \
           grep -q "YT-J706F Linux" "$GADGET_SCRIPT" && \
           grep -q "lenovomarchy" "$GADGET_SCRIPT" && \
           grep -q "02:59:54:31:31:01" "$GADGET_SCRIPT" && \
           grep -q "02:59:54:31:31:02" "$GADGET_SCRIPT" && \
           grep -q "192.168.77.1/24" "$GADGET_SCRIPT" && \
           grep -q "192.168.77.2" /mnt/etc/usb-gadget/dnsmasq.conf; then
            pass "usb-gadget-setup and dnsmasq.conf match YT-J706F USB gadget specification"
        else
            fail "usb-gadget-setup or dnsmasq.conf missing required USB gadget parameters"
        fi

        # 6. authorized_keys installed with correct modes & key-only root sshd config
        for pair in "root:/mnt/root/.ssh:0:0" "alarm:/mnt/home/alarm/.ssh:1000:1000"; do
            IFS=: read -r who ssh_dir uid gid <<< "$pair"
            ak="$ssh_dir/authorized_keys"
            if [[ -d "$ssh_dir" && -f "$ak" ]] && \
               [[ "$(stat -c "%a" "$ssh_dir")" == "700" ]] && \
               [[ "$(stat -c "%a" "$ak")" == "600" ]] && \
               [[ "$(stat -c "%u:%g" "$ak")" == "$uid:$gid" ]] && \
               cmp -s "$ak" /input/authorized_keys; then
                pass "authorized_keys for $who installed with 0700/0600 modes and matching key"
            else
                fail "authorized_keys for $who missing, wrong modes/owner, or key mismatch"
            fi
        done
        if grep -rq "^PermitRootLogin prohibit-password$" /mnt/etc/ssh/sshd_config /mnt/etc/ssh/sshd_config.d/ 2>/dev/null && \
           grep -rq "^PasswordAuthentication no$" /mnt/etc/ssh/sshd_config /mnt/etc/ssh/sshd_config.d/ 2>/dev/null; then
            pass "sshd configured for key-only login (PermitRootLogin prohibit-password, PasswordAuthentication no)"
        else
            fail "sshd not configured for key-only root login"
        fi

        # 7. fstab entry (PARTLABEL=userdata on / as ext4)
        if awk "\$1 == \"PARTLABEL=userdata\" && \$2 == \"/\" && \$3 == \"ext4\" { found=1 } END { exit !found }" /mnt/etc/fstab; then
            pass "/etc/fstab mounts PARTLABEL=userdata on / (ext4)"
        else
            fail "/etc/fstab missing PARTLABEL=userdata / ext4 entry"
        fi

        # 8. No file in the image contains "PRIVATE KEY"
        priv_hits="$(grep -rnI --exclude-dir=proc --exclude-dir=sys "PRIVATE KEY" /mnt 2>/dev/null || true)"
        if [[ -z "$priv_hits" ]]; then
            pass "no file in the image contains PRIVATE KEY"
        else
            fail "files containing PRIVATE KEY found in image: $priv_hits"
        fi

        # 9. Nothing in custom scripts/configs logs or prints /proc/cmdline
        cmdline_hits="$(grep -rnI "/proc/cmdline" /mnt/usr/local /mnt/etc/systemd 2>/dev/null | grep -v "^#" | grep -v ":#" || true)"
        if [[ -z "$cmdline_hits" ]]; then
            pass "nothing in /usr/local or /etc/systemd reads or prints /proc/cmdline"
        else
            fail "found /proc/cmdline reference in custom scripts/units: $cmdline_hits"
        fi

        if [[ "$FAIL" -gt 0 ]]; then
            echo "FAILED ($FAIL check(s) failed)" >&2
            exit 1
        fi
        echo "PASS"
    '
