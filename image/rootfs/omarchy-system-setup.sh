#!/usr/bin/env bash
# Stage 4: Apply Omarchy system-level branding, SDDM/Wayland session entry,
# Plymouth theme, and UFW rules inside the container rootfs.

set -euo pipefail

OMARCHY_PATH="/usr/share/omarchy"

echo "==> [omarchy-system-setup] Configuring /etc/os-release and /etc/issue"
if [[ -f "$OMARCHY_PATH/default/issue" ]]; then
    cp -f "$OMARCHY_PATH/default/issue" /etc/issue
fi

# Ensure neither /etc/issue nor any getty drop-in prints /proc/cmdline
mkdir -p /etc/systemd/system/getty@tty1.service.d
cat > /etc/systemd/system/getty@tty1.service.d/noclear.conf <<'EOF'
[Service]
TTYVTDisallocate=no
EOF

echo "==> [omarchy-system-setup] Creating /usr/share/wayland-sessions/omarchy.desktop"
mkdir -p /usr/share/wayland-sessions
cat > /usr/share/wayland-sessions/omarchy.desktop <<'EOF'
[Desktop Entry]
Name=Omarchy
Comment=Omarchy Hyprland Session
Exec=/usr/local/bin/omarchy-start-session
Type=Application
DesktopNames=Hyprland
EOF

cat > /usr/local/bin/omarchy-start-session <<'EOF'
#!/usr/bin/env bash
export PATH="/usr/share/omarchy/bin:$HOME/.local/bin:$PATH"
export OMARCHY_PATH="/usr/share/omarchy"
if command -v start-hyprland >/dev/null 2>&1; then
    exec start-hyprland
else
    exec Hyprland
fi
EOF
chmod 0755 /usr/local/bin/omarchy-start-session

echo "==> [omarchy-system-setup] Installing Omarchy Plymouth splash theme"
if [[ -d "$OMARCHY_PATH/default/plymouth" ]] && command -v plymouth-set-default-theme >/dev/null 2>&1; then
    mkdir -p /usr/share/plymouth/themes/omarchy
    cp -r "$OMARCHY_PATH/default/plymouth/"* /usr/share/plymouth/themes/omarchy/
    plymouth-set-default-theme omarchy || true
fi

echo "==> [omarchy-system-setup] Installing Omarchy GPG configuration to /etc/gnupg"
if [[ -d "$OMARCHY_PATH/default/gpg" ]]; then
    mkdir -p /etc/gnupg
    cp -r "$OMARCHY_PATH/default/gpg/"* /etc/gnupg/
    chmod 0700 /etc/gnupg
    chmod 0600 /etc/gnupg/* || true
fi

echo "==> [omarchy-system-setup] Enabling UFW firewall (SSH + DHCP on usb0 pre-allowed in /etc/ufw/user.rules)"
if [[ -f /etc/ufw/ufw.conf ]]; then
    sed -i 's/^ENABLED=.*/ENABLED=yes/' /etc/ufw/ufw.conf
    systemctl enable ufw.service || true
fi

echo "==> [omarchy-system-setup] Enabling bluetooth.service"
systemctl enable bluetooth.service || true

echo "==> [omarchy-system-setup] Done"
