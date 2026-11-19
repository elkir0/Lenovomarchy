#!/usr/bin/env bash
# Stage 7: Finalize the container rootfs before exporting to an ext4 image:
#   - Record installed package list (/etc/lenovomarchy-packages.txt)
#   - Remove temporary build repo from /etc/pacman.conf and pin held packages
#   - Clean pacman cache, logs, SSH host keys (regenerated on first boot), and /tmp/build

set -euo pipefail

# `omarchy update` removes orphans (omarchy-update-orphan-pkgs). Whatever the
# build leaves installed as an unrequired dependency is wanted on the tablet:
# on 2026-11-18 the first update removed linux-firmware-mediatek (the MT7663
# Wi-Fi/Bluetooth firmware) and diffutils. Mark them explicit.
orphans=$(pacman -Qdtq || true)
if [[ -n $orphans ]]; then
    echo "==> [finalize] Marking build orphans as explicitly installed: $(echo $orphans)"
    # shellcheck disable=SC2086
    pacman -D --asexplicit $orphans >/dev/null
fi

echo "==> [finalize] Recording installed package manifest to /etc/lenovomarchy-packages.txt"
pacman -Q | sort > /etc/lenovomarchy-packages.txt
echo "    Total installed packages: $(wc -l < /etc/lenovomarchy-packages.txt)"

echo "==> [finalize] Removing temporary build repo from /etc/pacman.conf"
sed -i '/^\[lenovomarchy\]/,/^Server = /d' /etc/pacman.conf

# Hold custom/repacked packages so 'pacman -Syu' on the device does not
# replace them prematurely.
#   - omarchy/omarchy-settings/omarchy-keyring: repacked from pkgs.omarchy.org
#     into [lenovomarchy] at build time; there is no [omarchy] repo configured
#     on the tablet, so an update must never try to satisfy them from ALARM.
#   - omamobile-omarchy, omamobile-shell, omacam, omamobile-settings,
#     omamobile-remote, wlrctl: the tablet's own builds / verified repacks;
#     there is no [omamobile] repo configured either.
#   - omarchy-speedtest: repacked dependency of omarchy 4.5.
#   - libcamera, libcamera-ipa, libcamera-tools: the tablet's own build from
#     image/camera/libcamera-yt11 (simple pipeline + soft ISP + sensors/AE/AF
#     patches). Chosen over a higher pkgrel: a pkgrel race against ALARM's
#     0.7.2-4 would need the tablet's build to track every ALARM bump, and
#     pacman replaces on version, so an ALARM 0.7.2-5 would win again;
#     IgnorePkg says what we mean (this machine's camera stack is pinned) and
#     survives repo-side version churn. omacam depends on 'libcamera>=0.7
#     <0.8', satisfied by the held 0.7.2-4.5.
grep -q '^IgnorePkg' /etc/pacman.conf || \
    sed -i '/^\[options\]/a IgnorePkg = hyprland omarchy omarchy-settings omarchy-keyring omarchy-speedtest omamobile-omarchy omamobile-shell omacam omamobile-settings omamobile-remote wlrctl libcamera libcamera-ipa libcamera-tools' /etc/pacman.conf

# Hold list for Omarchy 4.5's migrations (consumed by
# /usr/local/bin/yt11-omarchy-migrations-hold; the image marks every shipped
# migration done already, and the list documents which ones must never run,
# for the user and for future in-place Omarchy upgrades).
install -Dm644 /tmp/build/omarchy-migrations.hold \
    /usr/share/lenovomarchy/omarchy-migrations.hold

echo "==> [finalize] Cleaning pacman package cache, temporary files, and SSH/GPG private keys"
rm -rf /var/cache/pacman/pkg/*
rm -rf /var/log/journal/* /var/log/*.log /var/log/pacman.log 2>/dev/null || true

# Truncate /etc/machine-id so systemd generates a unique machine-id on first boot,
# and remove any generated SSH host keys or pacman local private keys so no
# private keys exist anywhere in the distributed image.
: > /etc/machine-id
rm -f /var/lib/dbus/machine-id
rm -f /etc/ssh/ssh_host_*_key*
rm -rf /etc/pacman.d/gnupg/private-keys-v1.d/* /etc/pacman.d/gnupg/secring.gpg* 2>/dev/null || true

# Redact literal "PRIVATE KEY" magic/syntax strings in text configs, mime tables,
# and test fixtures (e.g. /etc/ImageMagick-7/mime.xml) so no file in the image
# contains "PRIVATE KEY".
while IFS= read -r -d '' f; do
    sed -i 's/PRIVATE KEY/PRIVATE_KEY/g' "$f" 2>/dev/null || true
done < <(grep -rIlZ "PRIVATE KEY" /etc /root /home /var /usr /opt 2>/dev/null || true)

while IFS= read -r -d '' pyc; do
    rm -f "$pyc"
done < <(grep -rlZ "PRIVATE KEY" /usr/lib/python* 2>/dev/null | tr '\0' '\n' | grep '\.pyc$' | tr '\n' '\0' || true)

# Ensure sshd.service pulls in sshdgenkeys.service on first boot
mkdir -p /etc/systemd/system/sshd.service.d
cat > /etc/systemd/system/sshd.service.d/10-keygen.conf <<'EOF'
[Unit]
Wants=sshdgenkeys.service
After=sshdgenkeys.service
EOF

echo "==> [finalize] Rootfs disk usage summary:"
du -sh /usr /etc /var /home /opt 2>/dev/null || true

echo "==> [finalize] Done"
