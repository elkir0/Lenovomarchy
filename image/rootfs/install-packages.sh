#!/usr/bin/env bash
# Stage 2: Install Omarchy, its base package list (/usr/share/omarchy/install/omarchy-base.packages)
# minus packages.omarchy-skip, and Lenovo Yoga Tab 11 system/hardware packages (packages.extra).

set -euo pipefail

export OMARCHY_ALLOW_DIRECT_PACMAN=1

BUILD_DIR="/tmp/build"
SKIP_FILE="$BUILD_DIR/packages.omarchy-skip"
EXTRA_FILE="$BUILD_DIR/packages.extra"
BASE_LIST="/usr/share/omarchy/install/omarchy-base.packages"

read_list() {
    tr -d '\r' < "$1" | grep -vE '^\s*(#|$)' | awk '{print $1}'
}

available() {
    pacman -Sp --print-format %n "$1" >/dev/null 2>&1
}

echo "==> [install-packages] Extracting dependency list from lenovomarchy/omarchy"
OMARCHY_PKG="$(ls "$BUILD_DIR"/repo/omarchy-[0-9]*-aarch64.pkg.tar.* | head -n1)"
if [[ -z "$OMARCHY_PKG" ]]; then
    echo "ERROR: omarchy package not found in $BUILD_DIR/repo" >&2
    exit 1
fi

mapfile -t OMARCHY_DEPS < <(
    bsdtar -xOf "$OMARCHY_PKG" .PKGINFO \
        | awk -F' = ' '$1 == "depend" {print $2}' \
        | sed 's/[<>=].*//'
)
echo "    omarchy declares ${#OMARCHY_DEPS[@]} direct dependencies"

declare -A SKIP=()
while read -r pkg; do
    SKIP["$pkg"]=1
done < <(read_list "$SKIP_FILE")

INSTALL_DEPS=()
for dep in "${OMARCHY_DEPS[@]}"; do
    if [[ -z "${SKIP[$dep]:-}" ]]; then
        INSTALL_DEPS+=("$dep")
    fi
done

# Pre-select non-interactive providers for virtual dependencies
echo "==> [install-packages] Installing provider packages (pipewire-jack, wireplumber, noto-fonts-emoji, Polkit agent)"
pacman -S --noconfirm --needed \
    pipewire-jack \
    wireplumber \
    noto-fonts-emoji \
    lenovomarchy/ttf-jetbrains-mono-nerd-basic \
    hyprpolkitagent

echo "==> [install-packages] Installing direct omarchy dependencies"
pacman -S --noconfirm --needed "${INSTALL_DEPS[@]}"

echo "==> [install-packages] Installing packages from [lenovomarchy] repo"
pacman -S --noconfirm --needed \
    lenovomarchy/omarchy-keyring \
    lenovomarchy/omarchy-themes-intros \
    lenovomarchy/omarchy-nvim \
    lenovomarchy/ttf-ia-writer \
    lenovomarchy/ttf-jetbrains-mono-nerd-basic \
    lenovomarchy/yaru-icon-theme

echo "==> [install-packages] Installing omarchy + omarchy-settings"
pacman -Sdd --noconfirm --needed \
    lenovomarchy/omarchy \
    lenovomarchy/omarchy-settings

echo "==> [install-packages] Resolving /usr/share/omarchy/install/omarchy-base.packages for aarch64"
WANT_BASE=()
SKIPPED_BASE=()
UNAVAIL_BASE=()
if [[ -f "$BASE_LIST" ]]; then
    while read -r pkg; do
        if [[ -n "${SKIP[$pkg]:-}" ]]; then
            SKIPPED_BASE+=("$pkg")
        elif available "$pkg"; then
            WANT_BASE+=("$pkg")
        else
            UNAVAIL_BASE+=("$pkg")
        fi
    done < <(read_list "$BASE_LIST")
fi
echo "    omarchy-base.packages: ${#WANT_BASE[@]} installable, ${#SKIPPED_BASE[@]} skipped, ${#UNAVAIL_BASE[@]} unavailable (${UNAVAIL_BASE[*]})"

echo "==> [install-packages] Installing omarchy-base.packages + Lenovo Yoga Tab 11 extra packages (packages.extra)"
mapfile -t EXTRA_PKGS < <(read_list "$EXTRA_FILE")
pacman -S --noconfirm --needed "${WANT_BASE[@]}" "${EXTRA_PKGS[@]}"

echo "==> [install-packages] Verifying critical binaries and libraries"
for bin in Hyprland qs sddm foot nvim btop fastfetch magick plymouth NetworkManager sshd dnsmasq resize2fs depmod; do
    if ! command -v "$bin" >/dev/null 2>&1; then
        echo "ERROR: required binary '$bin' not found on PATH after package install" >&2
        exit 1
    fi
done

for pkg in hyprland mesa linux-firmware-mediatek openssh; do
    pacman -Q "$pkg"
done

echo "==> [install-packages] Checking for missing shared libraries on Hyprland and Quickshell"
for bin in /usr/bin/Hyprland /usr/bin/qs; do
    if ldd "$bin" | grep -q 'not found'; then
        echo "ERROR: $bin has unresolved shared libraries:" >&2
        ldd "$bin" | grep 'not found' >&2
        exit 1
    fi
done

echo "==> [install-packages] Done"
