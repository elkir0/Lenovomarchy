#!/usr/bin/env bash
# Stage 6: Install the mobile / tablet touch layer on top of Omarchy:
#   - squeekboard on-screen keyboard
#   - omamobile-omarchy patches over /usr/share/omarchy
#   - omamobile-shell Quickshell plugins + omamobile-setup-user --adopt for alarm
#   - Omarchy Mobile extras (omacam camera app, settings, remote test tools)
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
pacman -S --noconfirm --needed "${MOBILE_PKGS[@]}"

for bin in squeekboard omamobile-omarchy-patches omamobile-setup-user omacam; do
    command -v "$bin" >/dev/null 2>&1 || {
        echo "ERROR: '$bin' not on PATH after packages.mobile install" >&2
        exit 1
    }
done

# The 0.1.48 package has no omatel-agent dependency, so the old
# --assume-installed omatel-agent workaround is gone.

echo "==> [install-mobile] Applying and verifying omamobile-omarchy patch series"
# Docker's overlayfs makes os.rename() of a directory created in an earlier
# RUN layer fail with EXDEV (the pacman hook already applied the series when
# install-packages.sh installed omarchy, leaving
# /var/lib/omamobile/omarchy-patches/pristine in a lower layer). Copy the
# state tree in place first — same trick as out/rehearsal/step.sh — so the
# tool's directory swaps stay inside this layer. Verification still runs.
for d in /var/lib/omamobile /usr/share/omarchy; do
    if [[ -d "$d" ]]; then
        cp -a "$d" "$d.omamobile-copy"
        rm -rf "$d"
        mv "$d.omamobile-copy" "$d"
    fi
done
omamobile-omarchy-patches apply
omamobile-omarchy-patches verify
/usr/lib/omamobile-omarchy/lock-pam
test -f /etc/pam.d/omarchy-lock-password

echo "==> [install-mobile] Running omamobile-setup-user --adopt for $USER_NAME"
# The omamobile-shell package ships the tablet profiles itself
# (/usr/share/omamobile/shell/profile/shell.json is tablet-shell.json and
# profile/home.json is tablet-home.json from its PKGBUILD). With --adopt the
# profile-seeding step is marked done WITHOUT running, so the image seeds the
# user's copies itself, exactly from the package's profiles:
su - "$USER_NAME" -c 'omamobile-setup-user --adopt'
cp -f /usr/share/omamobile/shell/profile/shell.json "$HOME_DIR/.config/omarchy/shell.json"
mkdir -p "$HOME_DIR/.config/omamobile"
cp -f /usr/share/omamobile/shell/profile/home.json "$HOME_DIR/.config/omamobile/home.json"
chown "$USER_NAME:$USER_NAME" "$HOME_DIR/.config/omarchy/shell.json" \
    "$HOME_DIR/.config/omamobile/home.json"

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
# The account password the image ships ("alarm") has letters: record the
# credential as a password so the lock screen and the polkit prompt open the
# full keyboard (a PIN gets the number pad, on which it cannot be typed).
# `omamobile-set-pin` changes both the secret and this choice.
mkdir -p "$HOME_DIR/.config/omamobile"
echo password > "$HOME_DIR/.config/omamobile/credential"
touch "$HOME_DIR/.local/state/omarchy/toggles/credential-password"
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

# A migration that seeds a wants link for omarchy-fcitx5.service (a unit the
# image does not install; fcitx5 is skipped for squeekboard) would leave a
# dangling link the user manager complains about at login: pre-remove it.
rm -f "$HOME_DIR/.config/systemd/user/graphical-session.target.wants/omarchy-fcitx5.service"

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
# Omarchy 4.5's startup-cursor.lua needs two things outside a real session:
# HYPRLAND_INSTANCE_SIGNATURE (nil is a Lua error) and no hl.timer() call,
# which makes Hyprland 0.57.2 segfault in --verify-config mode (no event
# loop). The wrapper stubs the timer, then loads the user's config.
cat > "$VERIFY_RUN/verify.lua" <<EOF
hl.timer = function() end
dofile("$HOME_DIR/.config/hypr/hyprland.lua")
EOF
chown -R "$USER_NAME:$USER_NAME" "$VERIFY_RUN"
runuser -u "$USER_NAME" -- env -i \
    PATH="/usr/share/omarchy/bin:/usr/local/bin:/usr/bin" \
    HOME="$HOME_DIR" \
    XDG_CONFIG_HOME="$HOME_DIR/.config" \
    XDG_RUNTIME_DIR="$VERIFY_RUN" \
    OMARCHY_PATH="/usr/share/omarchy" \
    LANG="C.UTF-8" \
    HYPRLAND_INSTANCE_SIGNATURE="verify" \
    Hyprland --verify-config --config "$VERIFY_RUN/verify.lua"
rm -rf "$VERIFY_RUN"

echo "==> [install-mobile] Done"
