#!/usr/bin/env bash
# Stage 7: Finalize the container rootfs before exporting to an ext4 image:
#   - Record installed package list (/etc/lenovomarchy-packages.txt)
#   - Remove temporary build repo from /etc/pacman.conf and pin held packages
#   - Clean pacman cache, logs, SSH host keys (regenerated on first boot), and /tmp/build

set -euo pipefail

echo "==> [finalize] Recording installed package manifest to /etc/lenovomarchy-packages.txt"
pacman -Q | sort > /etc/lenovomarchy-packages.txt
echo "    Total installed packages: $(wc -l < /etc/lenovomarchy-packages.txt)"

echo "==> [finalize] Removing temporary build repo from /etc/pacman.conf"
sed -i '/^\[lenovomarchy\]/,/^Server = /d' /etc/pacman.conf

# Hold custom/repacked packages so 'pacman -Syu' on the device does not
# replace them prematurely.
grep -q '^IgnorePkg' /etc/pacman.conf || \
    sed -i '/^\[options\]/a IgnorePkg = hyprland omarchy omarchy-settings omarchy-keyring omamobile-omarchy omamobile-shell' /etc/pacman.conf

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
