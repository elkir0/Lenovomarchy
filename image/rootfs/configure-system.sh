#!/usr/bin/env bash
# Stage 3: System-level configuration for the Lenovo Yoga Tab 11 (YT-J706F):
#   - Overlay files (/etc, /usr)
#   - Kernel modules from input/modules.tar.xz + depmod for input/kernel.release
#   - Locale, timezone, hostname
#   - User 'alarm' (UID 1000) and root SSH authorized_keys from input/authorized_keys
#   - Systemd service enablement (usb-gadget, lenovomarchy-resize-rootfs, sshd,
#     serial-getty@ttyGS0, sddm, NetworkManager, bluetooth)

set -euo pipefail

BUILD_DIR="/tmp/build"
OVERLAY_DIR="$BUILD_DIR/overlay"

echo "==> [configure-system] Installing rootfs overlay files"
cp -a "$OVERLAY_DIR/." /

chown root:root /etc/sudoers.d/10-wheel
chmod 0440 /etc/sudoers.d/10-wheel
chmod 0755 /usr/local/sbin/usb-gadget-setup
chmod 0755 /usr/local/sbin/lenovomarchy-resize-rootfs
chmod 0755 /usr/share/omarchy/install/user/first-run/wifi.sh

# --- Kernel modules (input/modules.tar.xz + input/kernel.release) ------------
KREL="$(tr -d '[:space:]' < "$BUILD_DIR/kernel.release")"
if [[ -z "$KREL" ]]; then
    echo "ERROR: empty kernel.release" >&2
    exit 1
fi
echo "==> [configure-system] Installing kernel modules for $KREL into /usr/lib/modules/$KREL"
MOD_TMP="$(mktemp -d)"
bsdtar --no-same-owner --no-same-permissions -xf "$BUILD_DIR/modules.tar.xz" -C "$MOD_TMP"
if [[ ! -d "$MOD_TMP/lib/modules/$KREL" ]]; then
    echo "ERROR: $BUILD_DIR/modules.tar.xz does not contain lib/modules/$KREL" >&2
    exit 1
fi
mkdir -p /usr/lib/modules
rm -rf "/usr/lib/modules/$KREL"
cp -a "$MOD_TMP/lib/modules/$KREL" "/usr/lib/modules/$KREL"
rm -rf "$MOD_TMP"
# Remove dangling host build/source symlinks from the kernel tree
rm -f "/usr/lib/modules/$KREL/build" "/usr/lib/modules/$KREL/source"
depmod -a "$KREL"
if [[ ! -s "/usr/lib/modules/$KREL/modules.dep" ]]; then
    echo "ERROR: depmod did not produce a non-empty /usr/lib/modules/$KREL/modules.dep" >&2
    exit 1
fi

# --- Locale & timezone -------------------------------------------------------
# shellcheck source=/dev/null
source /usr/share/lenovomarchy/locale.env
echo "==> [configure-system] Generating locales (en_US.UTF-8 + $LENOVOMARCHY_LOCALE)"
sed -i 's/^#\s*\(en_US\.UTF-8 UTF-8\)/\1/' /etc/locale.gen
grep -q '^en_US\.UTF-8 UTF-8' /etc/locale.gen || echo 'en_US.UTF-8 UTF-8' >> /etc/locale.gen
locale-gen
echo "LANG=${LENOVOMARCHY_LOCALE}" > /etc/locale.conf
echo "KEYMAP=${LENOVOMARCHY_XKB_LAYOUT}" > /etc/vconsole.conf

ln -sf "/usr/share/zoneinfo/${LENOVOMARCHY_TIMEZONE}" /etc/localtime

if [[ -f /etc/conf.d/wireless-regdom ]]; then
    sed -i 's/^WIRELESS_REGDOM=.*/#WIRELESS_REGDOM=/' /etc/conf.d/wireless-regdom
    if grep -q "^#*\s*WIRELESS_REGDOM=\"${LENOVOMARCHY_WIFI_REGDOM}\"" /etc/conf.d/wireless-regdom; then
        sed -i "s/^#*\s*\(WIRELESS_REGDOM=\"${LENOVOMARCHY_WIFI_REGDOM}\"\)/\1/" /etc/conf.d/wireless-regdom
    else
        echo "WIRELESS_REGDOM=\"${LENOVOMARCHY_WIFI_REGDOM}\"" >> /etc/conf.d/wireless-regdom
    fi
fi

# --- Hostname & /etc/hosts ---------------------------------------------------
# Note: /etc/hostname, /etc/hosts, and /etc/resolv.conf are bind-mounted
# read-only by Docker BuildKit during `RUN`; mkimage.sh writes them into the
# exported rootfs staging tree before mke2fs.

# --- Users & SSH keys --------------------------------------------------------
echo "==> [configure-system] Configuring 'alarm' user and SSH authorized_keys"
for grp in wheel video audio input render storage network power lp uucp; do
    getent group "$grp" >/dev/null || groupadd -r "$grp"
done

if ! id -u alarm >/dev/null 2>&1; then
    useradd -m -u 1000 -G wheel,video,audio,input,render,storage,network,power,lp,uucp -s /bin/bash alarm
else
    usermod -aG wheel,video,audio,input,render,storage,network,power,lp,uucp -s /bin/bash alarm
fi

echo "alarm:alarm" | chpasswd
# Root login is by SSH public key only (PermitRootLogin prohibit-password); lock root password.
passwd -l root >/dev/null 2>&1 || true

if [[ ! -s "$BUILD_DIR/authorized_keys" ]]; then
    echo "ERROR: $BUILD_DIR/authorized_keys is missing or empty" >&2
    exit 1
fi

install -d -m 0700 -o root -g root /root/.ssh
install -m 0600 -o root -g root "$BUILD_DIR/authorized_keys" /root/.ssh/authorized_keys

install -d -m 0700 -o alarm -g alarm /home/alarm/.ssh
install -m 0600 -o alarm -g alarm "$BUILD_DIR/authorized_keys" /home/alarm/.ssh/authorized_keys

# --- Systemd services --------------------------------------------------------
echo "==> [configure-system] Enabling systemd services"
systemctl enable \
    sddm.service \
    NetworkManager.service \
    sshd.service \
    bluetooth.service \
    usb-gadget.service \
    lenovomarchy-resize-rootfs.service \
    yt11-wifi-after-bt.service \
    serial-getty@ttyGS0.service

# Mask wait-online so boot never hangs offline, and iwd, which conflicts
# with NetworkManager. wpa_supplicant stays: NetworkManager starts it over
# D-Bus for Wi-Fi.
systemctl mask \
    systemd-networkd-wait-online.service \
    NetworkManager-wait-online.service \
    iwd.service

mkdir -p /var/lib/sddm
chown -R sddm:sddm /var/lib/sddm

echo "==> [configure-system] Done"
