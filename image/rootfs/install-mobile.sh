#!/usr/bin/env bash
# Stage 6: Install the mobile / tablet touch layer on top of Omarchy:
#   - squeekboard on-screen keyboard
#   - omamobile-omarchy patches over /usr/share/omarchy
#   - omamobile-shell Quickshell plugins + omamobile-setup-user --adopt for alarm
#   - tablet.lua appended to hyprland.lua, verified with Hyprland --verify-config
#   - theme wallpapers downscaled to <= 2000 px

set -euo pipefail

export OMARCHY_ALLOW_DIRECT_PACMAN=1

BUILD_DIR="/tmp/build"
MOBILE_FILE="$BUILD_DIR/packages.mobile"
USER_NAME="alarm"
HOME_DIR="/home/$USER_NAME"
GRAPH_WANTS="$HOME_DIR/.config/systemd/user/graphical-session.target.wants"

echo "==> [install-mobile] Installing packages from packages.mobile"
mapfile -t MOBILE_PKGS < <(grep -vE '^\s*(#|$)' "$MOBILE_FILE" | awk '{print $1}')
# The prebuilt omamobile-shell archive from the sister project declares
# depend = omatel-agent>=0.2.1 (for the SM-T715 modem); YT-J706F is Wi-Fi-only
# and disables callWatch/cellWatch in shell.json, so satisfy that virtual
# dependency with --assume-installed while resolving all real ALARM dependencies.
pacman -S --noconfirm --needed --assume-installed omatel-agent=0.2.1 "${MOBILE_PKGS[@]}"

for bin in squeekboard omamobile-omarchy-patches omamobile-setup-user; do
    command -v "$bin" >/dev/null 2>&1 || {
        echo "ERROR: '$bin' not on PATH after packages.mobile install" >&2
        exit 1
    }
done

echo "==> [install-mobile] Applying and verifying omamobile-omarchy patch series"
omamobile-omarchy-patches apply
omamobile-omarchy-patches verify
/usr/lib/omamobile-omarchy/lock-pam
test -f /etc/pam.d/omarchy-lock-password

echo "==> [install-mobile] Installing Wi-Fi tablet shell.json and home.json profiles"
cp -f "$BUILD_DIR/tablet-shell.json" /usr/share/omamobile/shell/profile/shell.json
cp -f "$BUILD_DIR/tablet-home.json" /usr/share/omamobile/shell/profile/home.json

echo "==> [install-mobile] Running omamobile-setup-user --adopt for $USER_NAME"
su - "$USER_NAME" -c 'omamobile-setup-user --adopt'
cp -f /usr/share/omamobile/shell/profile/shell.json "$HOME_DIR/.config/omarchy/shell.json"
mkdir -p "$HOME_DIR/.config/omamobile"
cp -f /usr/share/omamobile/shell/profile/home.json "$HOME_DIR/.config/omamobile/home.json"
cp -f /usr/share/omamobile/shell/profile/home.json "$HOME_DIR/.config/omarchy/home.json"

# Configure squeekboard dconf settings and terminal keyboard layouts with Esc
su - "$USER_NAME" -c '
    if command -v dbus-run-session >/dev/null 2>&1 && command -v gsettings >/dev/null 2>&1; then
        dbus-run-session -- bash -c "
            gsettings set org.gnome.desktop.a11y.applications screen-keyboard-enabled true
            gsettings set org.gnome.desktop.input-sources sources \"[(\x27xkb\x27, \x27us\x27), (\x27xkb\x27, \x27fr\x27)]\"
        " || true
    fi
    mkdir -p ~/.local/share/squeekboard/keyboards/terminal
    for l in us fr; do
        ln -sfn "/usr/share/lenovomarchy/squeekboard/keyboards/terminal/$l.yaml" \
            "$HOME/.local/share/squeekboard/keyboards/terminal/$l.yaml"
    done
'
rm -f "$HOME_DIR/.config/omarchy/plugins/omamobile.fingerprint" \
      "$HOME_DIR/.config/omarchy/plugins/omamobile.update" \
      "$HOME_DIR/.config/omarchy/plugins/omamobile.access" \
      "$HOME_DIR/.config/omarchy/plugins/omamobile.voice" \
      "$HOME_DIR/.config/omarchy/plugins/omamobile.call"
sed -i '/hypr\/phone\.lua/d' "$HOME_DIR/.config/hypr/looknfeel.lua"
if [[ -f "$HOME_DIR/.config/chromium-flags.conf" ]]; then
    sed -i 's/^"--user-agent=.*/"--user-agent=Mozilla\/5.0 (Linux; Android 14; YT-J706F) AppleWebKit\/537.36 (KHTML, like Gecko) Chrome\/146.0.0.0 Safari\/537.36"/' \
        "$HOME_DIR/.config/chromium-flags.conf"
    sed -i '/^--force-device-scale-factor=/d' "$HOME_DIR/.config/chromium-flags.conf"
fi
cat >> "$HOME_DIR/.config/chromium-flags.conf" <<'EOF'
--touch-events=enabled
--enable-features=TouchpadOverscrollHistoryNavigation
--enable-gpu-rasterization
--enable-zero-copy
--ignore-gpu-blocklist
--num-raster-threads=2
EOF
rm -f "$HOME_DIR/.local/state/omarchy/toggles/screensaver-off" \
      "$HOME_DIR/.local/state/omarchy/toggles/lock-after-screensaver"
mkdir -p "$HOME_DIR/.local/state/omarchy/toggles"
touch "$HOME_DIR/.local/state/omarchy/toggles/stay-awake"
# omamobile turns suspend off (phones); suspend-to-idle works on this tablet,
# so keep the system menu's Suspend entry.
rm -f "$HOME_DIR/.local/state/omarchy/toggles/suspend-off"

# Mask omamobile-setup-user.service so it does not re-run without --adopt at
# first login and overwrite monitors.lua with phone scale=3.
mkdir -p "$HOME_DIR/.config/systemd/user"
ln -sf /dev/null "$HOME_DIR/.config/systemd/user/omamobile-setup-user.service"

test -f "$HOME_DIR/.config/omarchy/shell.json"
test -L "$HOME_DIR/.config/omarchy/plugins/omamobile.bar"
test -f "$HOME_DIR/.local/state/omarchy/toggles/stay-awake"

echo "==> [install-mobile] Appending tablet.lua to hyprland.lua"
for cfg in "$HOME_DIR/.config/hypr/hyprland.lua" /etc/skel/.config/hypr/hyprland.lua; do
    if ! grep -q "Lenovo Yoga Tab 11 (YT-J706F) tablet layer" "$cfg"; then
        printf '\n' >> "$cfg"
        cat "$BUILD_DIR/tablet.lua" >> "$cfg"
    fi
done

# Ensure monitors.lua still has scale = 1.5 and transform = 2
cp -f /etc/skel/.config/hypr/monitors.lua "$HOME_DIR/.config/hypr/monitors.lua"

echo "==> [install-mobile] Downscaling theme backgrounds for the 1200x2000 panel"
bash "$BUILD_DIR/wallpapers.sh"
cp -a /usr/share/omarchy/themes/tokyo-night/backgrounds/. \
    "$HOME_DIR/.config/omarchy/current/theme/backgrounds/"

echo "==> [install-mobile] Enabling lenovomarchy-squeekboard.service for $USER_NAME"
mkdir -p "$GRAPH_WANTS"
ln -sf /etc/systemd/user/lenovomarchy-squeekboard.service \
    "$GRAPH_WANTS/lenovomarchy-squeekboard.service"

chown -R "$USER_NAME:$USER_NAME" "$HOME_DIR"

echo "==> [install-mobile] Verifying $HOME_DIR/.config/hypr/hyprland.lua with Hyprland --verify-config"
VERIFY_RUN="$(mktemp -d)"
chmod 0700 "$VERIFY_RUN"
chown "$USER_NAME:$USER_NAME" "$VERIFY_RUN"
runuser -u "$USER_NAME" -- env -i \
    PATH="/usr/share/omarchy/bin:/usr/local/bin:/usr/bin" \
    HOME="$HOME_DIR" \
    XDG_CONFIG_HOME="$HOME_DIR/.config" \
    XDG_RUNTIME_DIR="$VERIFY_RUN" \
    OMARCHY_PATH="/usr/share/omarchy" \
    LANG="C.UTF-8" \
    Hyprland --verify-config --config "$HOME_DIR/.config/hypr/hyprland.lua"
rm -rf "$VERIFY_RUN"

echo "==> [install-mobile] Done"
