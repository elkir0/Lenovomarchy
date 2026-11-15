#!/usr/bin/env bash
# Stage 5: Initialize the 'alarm' user's Omarchy configuration (/home/alarm/.config)
# and adapt Hyprland monitor/looknfeel settings for the Lenovo Yoga Tab 11:
#   - 1200x2000 panel mounted rotated 180 degrees (transform = 2), default scale 1.5
#   - Mali-G76 (Mesa Panfrost): blur and drop shadows disabled in looknfeel.lua

set -euo pipefail

USER_NAME="alarm"
HOME_DIR="/home/$USER_NAME"
OMARCHY_PATH="/usr/share/omarchy"
# shellcheck source=/dev/null
source /usr/share/lenovomarchy/locale.env

echo "==> [omarchy-user-setup] Populating $HOME_DIR/.config from /etc/skel"
mkdir -p "$HOME_DIR/.config" "$HOME_DIR/.local/share" "$HOME_DIR/.local/state" "$HOME_DIR/.local/bin"
if [[ -d /etc/skel/.config ]]; then
    cp -rn /etc/skel/.config/* "$HOME_DIR/.config/" || true
fi
if [[ -f /etc/skel/.bashrc ]]; then
    cp -f /etc/skel/.bashrc "$HOME_DIR/.bashrc"
fi
if [[ -f /etc/skel/.bash_profile ]]; then
    cp -f /etc/skel/.bash_profile "$HOME_DIR/.bash_profile"
fi

# Ensure monitors.lua from our overlay is installed in both /etc/skel and ~/.config/hypr
cp -f /etc/skel/.config/hypr/monitors.lua "$HOME_DIR/.config/hypr/monitors.lua"

# Stage default Tokyo Night theme
echo "==> [omarchy-user-setup] Setting default theme -> tokyo-night"
mkdir -p "$HOME_DIR/.config/omarchy/current" "$HOME_DIR/.config/omarchy/themes"
echo "tokyo-night" > "$HOME_DIR/.config/omarchy/current/theme.name"
if [[ -d "$OMARCHY_PATH/themes/tokyo-night" ]]; then
    cp -a "$OMARCHY_PATH/themes/tokyo-night" "$HOME_DIR/.config/omarchy/current/theme"
    shopt -s nullglob
    bg_files=("$HOME_DIR/.config/omarchy/current/theme/backgrounds/"*)
    shopt -u nullglob
    if [[ ${#bg_files[@]} -gt 0 ]]; then
        ln -sf "${bg_files[0]}" "$HOME_DIR/.config/omarchy/current/background"
    fi
fi

if [[ -d "$HOME_DIR/.config/omarchy/current/theme" ]]; then
    mkdir -p "$HOME_DIR/.config/btop/themes" "$HOME_DIR/.config/mako" "$HOME_DIR/.config/eza"
    [[ -f "$HOME_DIR/.config/omarchy/current/theme/btop.theme" ]] && \
        ln -sf "$HOME_DIR/.config/omarchy/current/theme/btop.theme" "$HOME_DIR/.config/btop/themes/current.theme"
    [[ -f "$HOME_DIR/.config/omarchy/current/theme/mako.ini" ]] && \
        ln -sf "$HOME_DIR/.config/omarchy/current/theme/mako.ini" "$HOME_DIR/.config/mako/config"
    [[ -f "$HOME_DIR/.config/omarchy/current/theme/eza.yml" ]] && \
        ln -sf "$HOME_DIR/.config/omarchy/current/theme/eza.yml" "$HOME_DIR/.config/eza/theme.yml"
fi

echo "==> [omarchy-user-setup] Applying Hyprland tablet overrides (scale 1.5, transform 2, no blur/shadow)"
sed -i "s/kb_layout = \"[^\"]*\"/kb_layout = \"${LENOVOMARCHY_XKB_LAYOUT}\"/" \
    "$HOME_DIR/.config/hypr/input.lua" /etc/skel/.config/hypr/input.lua

cp /tmp/build/looknfeel.lua "$HOME_DIR/.config/hypr/looknfeel.lua"
cp /tmp/build/looknfeel.lua /etc/skel/.config/hypr/looknfeel.lua

echo "==> [omarchy-user-setup] Enabling user systemd units"
USER_WANTS="$HOME_DIR/.config/systemd/user/default.target.wants"
GRAPH_WANTS="$HOME_DIR/.config/systemd/user/graphical-session.target.wants"
SOCK_WANTS="$HOME_DIR/.config/systemd/user/sockets.target.wants"
mkdir -p "$USER_WANTS" "$GRAPH_WANTS" "$SOCK_WANTS"

for unit in pipewire.socket pipewire-pulse.socket; do
    if [[ -f "/usr/lib/systemd/user/$unit" ]]; then
        ln -sf "/usr/lib/systemd/user/$unit" "$SOCK_WANTS/$unit"
    fi
done
if [[ -f /usr/lib/systemd/user/wireplumber.service ]]; then
    ln -sf /usr/lib/systemd/user/wireplumber.service "$USER_WANTS/wireplumber.service"
fi

for unit in omarchy-shell.service omarchy-battery-monitor.timer hyprpolkitagent.service; do
    if [[ -f "/etc/systemd/user/$unit" ]]; then
        ln -sf "/etc/systemd/user/$unit" "$GRAPH_WANTS/$unit"
    elif [[ -f "/usr/lib/systemd/user/$unit" ]]; then
        ln -sf "/usr/lib/systemd/user/$unit" "$GRAPH_WANTS/$unit"
    fi
done

mkdir -p "$HOME_DIR/.local/state/omarchy"
if [[ -d "$OMARCHY_PATH/.git" ]]; then
    git -C "$OMARCHY_PATH" describe --tags --abbrev=0 > "$HOME_DIR/.local/state/omarchy/version" 2>/dev/null || \
        echo "4.0.6" > "$HOME_DIR/.local/state/omarchy/version"
else
    echo "4.0.6" > "$HOME_DIR/.local/state/omarchy/version"
fi

echo "==> [omarchy-user-setup] Setting ownership of $HOME_DIR to $USER_NAME:$USER_NAME"
chown -R "$USER_NAME:$USER_NAME" "$HOME_DIR"

echo "==> [omarchy-user-setup] Done"
