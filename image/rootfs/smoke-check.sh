#!/usr/bin/env bash
# Build-time smoke check run inside the container at the end of Dockerfile.

set -euo pipefail

FAIL=0
pass() { printf '  [PASS] %s\n' "$*"; }
fail() { printf '  [FAIL] %s\n' "$*" >&2; FAIL=$((FAIL + 1)); }

echo "==> [smoke-check] Running build-time verification on rootfs"

# 1. Architecture check (64-bit ARM EABI5)
file_out="$(file -b /usr/bin/Hyprland)"
if [[ "$file_out" == *"ELF 64-bit LSB"* && "$file_out" == *"ARM aarch64"* ]]; then
    pass "/usr/bin/Hyprland is 64-bit ARM aarch64 ($file_out)"
else
    fail "/usr/bin/Hyprland unexpected format: $file_out"
fi

# 2. Required packages
for pkg in hyprland mesa linux-firmware-mediatek openssh omarchy omarchy-settings omamobile-omarchy omamobile-shell squeekboard sddm networkmanager dnsmasq; do
    if pacman -Q "$pkg" >/dev/null 2>&1; then
        pass "package installed: $(pacman -Q "$pkg")"
    else
        fail "package missing: $pkg"
    fi
done

# 3. MediaTek MT7663 firmware
shopt -s nullglob
mt7663_fw=(/usr/lib/firmware/mediatek/mt7663*)
shopt -u nullglob
if [[ ${#mt7663_fw[@]} -ge 2 ]]; then
    pass "mediatek/mt7663* firmware present (${#mt7663_fw[@]} files)"
else
    fail "mediatek/mt7663* firmware missing in /usr/lib/firmware/mediatek/"
fi

# 4. Kernel modules & modules.dep
shopt -s nullglob
mod_deps=(/usr/lib/modules/*/modules.dep)
shopt -u nullglob
if [[ ${#mod_deps[@]} -ge 1 && -s "${mod_deps[0]}" ]]; then
    pass "kernel modules.dep present: ${mod_deps[0]}"
else
    fail "kernel modules.dep missing under /usr/lib/modules/*/"
fi

# 5. Systemd services enabled
for link in \
    /etc/systemd/system/display-manager.service \
    /etc/systemd/system/multi-user.target.wants/usb-gadget.service \
    /etc/systemd/system/multi-user.target.wants/lenovomarchy-resize-rootfs.service \
    /etc/systemd/system/multi-user.target.wants/yt11-sensor-firmware.service \
    /etc/systemd/system/multi-user.target.wants/yt11-charge-guard.service \
    /etc/systemd/system/multi-user.target.wants/yt11-boot-successful.service \
    /etc/systemd/system/multi-user.target.wants/sshd.service \
    /etc/systemd/system/multi-user.target.wants/NetworkManager.service \
    /etc/systemd/system/getty.target.wants/serial-getty@ttyGS0.service; do
    if [[ -L "$link" ]]; then
        pass "service symlink enabled: $link -> $(readlink "$link")"
    else
        fail "service symlink missing: $link"
    fi
done

if [[ -x /usr/local/sbin/yt11-bootctl ]]; then
    pass "A/B slot tool present: /usr/local/sbin/yt11-bootctl"
else
    fail "A/B slot tool missing: /usr/local/sbin/yt11-bootctl"
fi

# 6. SSH authorized_keys and modes
for d in /root/.ssh /home/alarm/.ssh; do
    f="$d/authorized_keys"
    if [[ -d "$d" && "$(stat -c '%a' "$d")" == "700" && -s "$f" && "$(stat -c '%a' "$f")" == "600" ]]; then
        pass "authorized_keys present with 0700/0600 modes: $f"
    else
        fail "authorized_keys missing or bad modes: $f"
    fi
done

# 7. /etc/fstab entry for PARTLABEL=userdata
if awk '$1 == "PARTLABEL=userdata" && $2 == "/" && $3 == "ext4" { found=1 } END { exit !found }' /etc/fstab; then
    pass "/etc/fstab mounts PARTLABEL=userdata on / (ext4)"
else
    fail "/etc/fstab missing PARTLABEL=userdata / ext4 entry"
fi

# 8. Hyprland monitor config (transform = 2, scale = 1.5)
if grep -q 'omarchy_monitor_scale = 1.5' /home/alarm/.config/hypr/monitors.lua && \
   grep -q 'transform = 2' /home/alarm/.config/hypr/monitors.lua; then
    pass "/home/alarm/.config/hypr/monitors.lua sets scale = 1.5 and transform = 2"
else
    fail "/home/alarm/.config/hypr/monitors.lua missing scale = 1.5 or transform = 2"
fi

# 9. No PRIVATE KEY in /etc, /root, /home, /var, /usr, /opt
if grep -rnI "PRIVATE KEY" /etc /root /home /var /usr /opt 2>/dev/null; then
    fail "found PRIVATE KEY in rootfs"
else
    pass "no PRIVATE KEY in /etc, /root, /home, /var, /usr, /opt"
fi

# 10. Omarchy 4.5 migration state: nothing pending for alarm (every shipped
#     migration is marked done by omarchy-user-setup.sh at build time).
pending="$(su - alarm -c 'cd /home/alarm && omarchy-migrate --pending' 2>/dev/null || true)"
if [[ -z "$pending" ]]; then
    pass "omarchy-migrate --pending is empty for alarm"
else
    fail "omarchy-migrate --pending lists: $(echo "$pending" | tr '\n' ' ')"
fi

# 11. The omamobile-omarchy patch series is applied and verifies.
if omamobile-omarchy-patches verify >/dev/null 2>&1; then
    pass "omamobile-omarchy-patches verify"
else
    fail "omamobile-omarchy-patches verify failed"
fi

# 12. Installed versions match the pins / PKGBUILDs.
expect_version() {  # <pkg> <expected pkgver-pkgrel>
    local got
    got="$(pacman -Q "$1" 2>/dev/null | awk '{print $2}')"
    if [[ "$got" == "$2" ]]; then
        pass "$1 $got (matches pin/PKGBUILD)"
    else
        fail "$1 version $got, expected $2"
    fi
}
expect_version omarchy            "4.5.0-3"
expect_version omarchy-settings   "4.5.0-3"
expect_version omamobile-omarchy  "0.1.48-2"
expect_version omamobile-shell    "0.2.133-3"
expect_version libcamera         "0.7.2-4.7"
expect_version omacam             "0.3.3-1"

# 13. mako must not be installed (Omarchy 4.5's shell is the notification
#     server; mako steals the D-Bus name at boot).
if pacman -Q mako >/dev/null 2>&1; then
    fail "mako is installed (would steal org.freedesktop.Notifications)"
else
    pass "mako not installed"
fi

# 14. omacam present with resolved shared libraries.
if [[ -x /usr/bin/omacam ]] && ! ldd /usr/bin/omacam 2>/dev/null | grep -q 'not found'; then
    pass "/usr/bin/omacam present and ldd resolves"
else
    fail "/usr/bin/omacam missing or has unresolved libraries"
fi

# 15. The migration hold list is installed (for in-place Omarchy upgrades).
if [[ -f /usr/share/lenovomarchy/omarchy-migrations.hold ]]; then
    pass "hold list at /usr/share/lenovomarchy/omarchy-migrations.hold ($(grep -cve '^\s*\(#\|$\)' /usr/share/lenovomarchy/omarchy-migrations.hold) entries)"
else
    fail "hold list missing at /usr/share/lenovomarchy/omarchy-migrations.hold"
fi

if [[ "$FAIL" -gt 0 ]]; then
    echo "==> [smoke-check] FAILED with $FAIL error(s)" >&2
    exit 1
fi
echo "==> [smoke-check] ALL CHECKS PASSED"
