#!/usr/bin/env bash
# Stage 1: Configure pacman, initialize keyrings, and register the local
# [lenovomarchy] repository inside the Arch Linux ARM aarch64 container.

set -euo pipefail

echo "==> [setup-pacman] Configuring /etc/pacman.conf"

if [[ -d /tmp/build/pacman-cache ]]; then
    mkdir -p /var/cache/pacman/pkg
    cp -rn /tmp/build/pacman-cache/*.pkg.tar.* /var/cache/pacman/pkg/ 2>/dev/null || true
    rm -rf /tmp/build/pacman-cache
fi

sed -i 's/^#*\(DisableSandbox\).*/\1/' /etc/pacman.conf
grep -q '^DisableSandbox' /etc/pacman.conf || \
    sed -i '/^\[options\]/a DisableSandbox' /etc/pacman.conf

sed -i 's/^#*\(ParallelDownloads\).*/ParallelDownloads = 5/' /etc/pacman.conf
grep -q '^ParallelDownloads' /etc/pacman.conf || \
    sed -i '/^\[options\]/a ParallelDownloads = 5' /etc/pacman.conf

if [[ ! -f /tmp/build/repo/lenovomarchy.db.tar.gz ]]; then
    echo "ERROR: local repo index /tmp/build/repo/lenovomarchy.db.tar.gz not found" >&2
    exit 1
fi

if ! grep -q '^\[lenovomarchy\]' /etc/pacman.conf; then
    cat >> /etc/pacman.conf <<'EOF'

[lenovomarchy]
SigLevel = Optional TrustAll
Server = file:///tmp/build/repo
EOF
fi

echo "==> [setup-pacman] Initializing pacman keyring"
pacman-key --init
pacman-key --populate archlinuxarm

# Remove the stock ALARM kernel package and unrelated desktop/server GPU/NIC
# firmware packages before -Syu. We keep linux-firmware-whence and
# linux-firmware-mediatek (installed in install-packages.sh for MT7663).
echo "==> [setup-pacman] Removing stock linux-aarch64 kernel and unused vendor firmware"
if pacman -Qq linux-aarch64 >/dev/null 2>&1; then
    pacman -Rdd --noconfirm linux-aarch64
fi
rm -rf /boot/Image* /boot/initramfs* /boot/dtbs /etc/mkinitcpio.d/linux-aarch64.preset

mapfile -t UNUSED_FW < <(
    pacman -Qq \
        linux-firmware \
        linux-firmware-amdgpu \
        linux-firmware-atheros \
        linux-firmware-broadcom \
        linux-firmware-cirrus \
        linux-firmware-intel \
        linux-firmware-liquidio \
        linux-firmware-marvell \
        linux-firmware-mellanox \
        linux-firmware-nfp \
        linux-firmware-nvidia \
        linux-firmware-other \
        linux-firmware-qcom \
        linux-firmware-qlogic \
        linux-firmware-radeon \
        linux-firmware-realtek \
        2>/dev/null || true
)
if [[ ${#UNUSED_FW[@]} -gt 0 ]]; then
    pacman -Rdd --noconfirm "${UNUSED_FW[@]}"
fi

echo "==> [setup-pacman] Refreshing package databases and upgrading base system"
pacman -Syu --noconfirm

echo "==> [setup-pacman] Installing and populating omarchy-keyring"
pacman -S --noconfirm --needed lenovomarchy/omarchy-keyring
pacman-key --populate omarchy || true
if [[ -f /usr/share/pacman/keyrings/omarchy.gpg ]]; then
    fpr="$(gpg --with-colons --show-keys /usr/share/pacman/keyrings/omarchy.gpg | awk -F: '/^fpr:/{print $10; exit}')"
    if [[ -n "$fpr" ]]; then
        pacman-key --lsign-key "$fpr" || true
    fi
fi

echo "==> [setup-pacman] Done"
