#!/usr/bin/env bash
# Build the Arch Linux ARM (aarch64) + Omarchy ext4 rootfs image for the
# Lenovo Yoga Tab 11 (YT-J706F, MediaTek MT6785).
#
# Outputs:
#   out/rootfs/rootfs-omarchy-aarch64.img
#   out/rootfs/packages.txt

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/alarm.sh
source "$SCRIPT_DIR/lib/alarm.sh"

ARCH="aarch64"
SIZE_MIB="${SIZE_MIB:-8192}"
OUT_ROOTFS_DIR="$OUT_DIR/rootfs"
OUT_IMG="$OUT_ROOTFS_DIR/rootfs-omarchy-aarch64.img"
OUT_PKGS="$OUT_ROOTFS_DIR/packages.txt"
ROOTFS_TAG="lenovomarchy-rootfs:$ARCH"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --size-mib) SIZE_MIB="$2"; shift 2 ;;
        --out)      OUT_IMG="$2"; shift 2 ;;
        -*)         die "unknown option: $1" ;;
        *)          die "unexpected argument: $1" ;;
    esac
done

# Versions the local [lenovomarchy] repository must hold. The pinned upstream
# versions come from image/tools/repack.pins; the built ones from the
# PKGBUILDs' pkgver/pkgrel. When any archive is missing, the right tool runs.
repo_pin_version() {  # <pkgname> -> <pkgver-pkgrel> from repack.pins
    awk -v p="$1" '$1 == p { print $2; exit }' "$SCRIPT_DIR/tools/repack.pins" \
        | sed -E 's/-aarch64\.pkg\.tar\.(zst|xz)$//; s/-any\.pkg\.tar\.(zst|xz)$//'
}
repo_pin_archfile() {  # <pkgname> -> filename from repack.pins
    awk -v p="$1" '$1 == p { print $2; exit }' "$SCRIPT_DIR/tools/repack.pins"
}
pkgbuild_version() {  # <dir> -> pkgver-pkgrel of the PKGBUILD in <dir>
    local pv pr
    pv="$(sed -nE 's/^pkgver=//p' "$1/PKGBUILD" | head -n1)"
    pr="$(sed -nE 's/^pkgrel=//p' "$1/PKGBUILD" | head -n1)"
    echo "${pv}-${pr}"
}

REPO_ARCH_DIR="$REPO_DIR/$ARCH"

OMARCHY_PIN_VER="$(repo_pin_version omarchy)"
OMARCHY_SETTINGS_PIN_VER="$(repo_pin_version omarchy-settings)"
OMARCHY_SPEEDTEST_PIN_VER="$(repo_pin_version omarchy-speedtest)"
OMAMOBILE_OMARCHY_VER="$(pkgbuild_version "$SCRIPT_DIR/pkg/omamobile-omarchy")"
OMAMOBILE_SHELL_VER="$(pkgbuild_version "$SCRIPT_DIR/pkg/omamobile-shell")"
for v in "$OMARCHY_PIN_VER" "$OMARCHY_SETTINGS_PIN_VER" "$OMARCHY_SPEEDTEST_PIN_VER" \
         "$OMAMOBILE_OMARCHY_VER" "$OMAMOBILE_SHELL_VER"; do
    [[ -n "$v" ]] || die "could not derive a wanted version (check repack.pins / PKGBUILDs)"
done

# Verify required read-only inputs exist
for req in \
    "$ROOT_DIR/input/modules.tar.xz" \
    "$ROOT_DIR/input/kernel.release" \
    "$ROOT_DIR/input/authorized_keys"; do
    [[ -f "$req" ]] || die "required input file not found: $req"
done

# 1. Ensure official Arch Linux ARM aarch64 tarball is downloaded, MD5-verified,
#    and imported into Docker (lenovomarchy:base-aarch64 & lenovomarchy:dev-aarch64).
alarm_ensure_base "$ARCH"
alarm_ensure_dev "$ARCH"

# 2. Populate local [lenovomarchy] repository:
#    a) SHA-256 + GPG-verified Omarchy packages (tools/repack-omarchy)
#    b) SHA-256 + GPG-verified Omarchy Mobile packages (tools/repack-omamobile)
#    c) omamobile-omarchy and omamobile-shell, built from image/pkg/ by
#       tools/build-pkg when the archive of the PKGBUILD's current version is
#       missing (the old input/prebuilt/ archives are gone from the flow)
#    Each step is skipped when everything it provides is already there.
want_repack_omarchy=0
for p in omarchy omarchy-settings omarchy-speedtest omarchy-keyring \
         omarchy-themes-intros omarchy-nvim ttf-ia-writer \
         ttf-jetbrains-mono-nerd-basic yaru-icon-theme tobi-try ufw-docker; do
    [[ -f "$REPO_ARCH_DIR/$(repo_pin_archfile "$p")" ]] || want_repack_omarchy=1
done
if [[ "$want_repack_omarchy" -eq 1 ]]; then
    "$SCRIPT_DIR/tools/repack-omarchy"
else
    log "Omarchy packages already pinned in $REPO_ARCH_DIR"
fi

want_repack_omamobile=0
while read -r pkg _mode _; do  # _mode: used by the repack container loop
    [[ -z "${pkg:-}" || "$pkg" =~ ^# ]] && continue
    fn="$(awk -v p="$pkg" '$1 == p { print $2; exit }' "$SCRIPT_DIR/tools/repack.omamobile.pins")"
    [[ -z "$fn" ]] && { want_repack_omamobile=1; continue; }
    [[ -f "$REPO_ARCH_DIR/$fn" ]] || want_repack_omamobile=1
done < "$SCRIPT_DIR/tools/repack.omamobile.list"
if [[ "$want_repack_omamobile" -eq 1 ]]; then
    "$SCRIPT_DIR/tools/repack-omamobile"
else
    log "Omarchy Mobile packages already pinned in $REPO_ARCH_DIR"
fi

for spec in "omamobile-omarchy:$OMAMOBILE_OMARCHY_VER:any" \
            "omamobile-shell:$OMAMOBILE_SHELL_VER:any"; do
    name="${spec%%:*}"; rest="${spec#*:}"; ver="${rest%%:*}"; parch="${rest##*:}"
    if ! ls "$REPO_ARCH_DIR/${name}-${ver}-${parch}.pkg.tar."* >/dev/null 2>&1; then
        log "Building $name $ver from image/pkg/$name (archive missing or stale)"
        "$SCRIPT_DIR/tools/build-pkg" "$name"
    else
        log "$name $ver already built in $REPO_ARCH_DIR"
    fi
done

# libcamera for this tablet's cameras (image/camera/libcamera-yt11, split
# package). Built the same way when the pkgver-pkgrel's archives are missing.
LIBCAMERA_YT11_VER="$(pkgbuild_version "$SCRIPT_DIR/camera/libcamera-yt11")"
[[ -n "$LIBCAMERA_YT11_VER" ]] || die "could not read libcamera-yt11 PKGBUILD version"
lc_missing=0
for sub in libcamera libcamera-ipa libcamera-tools; do
    ls "$REPO_ARCH_DIR/${sub}-${LIBCAMERA_YT11_VER}-aarch64.pkg.tar."* >/dev/null 2>&1 || lc_missing=1
done
if [[ "$lc_missing" -eq 1 ]]; then
    log "Building libcamera $LIBCAMERA_YT11_VER from image/camera/libcamera-yt11 (slow)"
    "$SCRIPT_DIR/tools/build-pkg" --nocheck --src "$SCRIPT_DIR/camera/libcamera-yt11" libcamera
else
    log "libcamera $LIBCAMERA_YT11_VER already built in $REPO_ARCH_DIR"
fi

alarm_repo_index "$ARCH"

# 3. Stage Docker build context under cache/rootfs-context
CTX_DIR="$CACHE_DIR/rootfs-context"
rm -rf "$CTX_DIR"
mkdir -p "$CTX_DIR/repo" "$CTX_DIR/overlay"

cp -a "$SCRIPT_DIR/rootfs/." "$CTX_DIR/"
cp -a "$SCRIPT_DIR/overlay/." "$CTX_DIR/overlay/"
cp -a "$REPO_ARCH_DIR/." "$CTX_DIR/repo/"
# The omamobile-shell package ships the tablet profiles itself
# (usr/share/omamobile/shell/profile/{shell,home}.json are tablet-shell.json /
# tablet-home.json from its PKGBUILD); install-mobile.sh seeds the user's
# copies from the package's profiles after omamobile-setup-user --adopt
# (which marks its own seeding step done without running it), so the image
# no longer stages its own tablet-*.json files into the context.
cp -f "$ROOT_DIR/input/modules.tar.xz" "$CTX_DIR/modules.tar.xz"
cp -f "$ROOT_DIR/input/kernel.release" "$CTX_DIR/kernel.release"
cp -f "$ROOT_DIR/input/authorized_keys" "$CTX_DIR/authorized_keys"

# 4. Build the container rootfs image (runs smoke-check.sh and finalize.sh)
BASE_IMG="$(alarm_base_image "$ARCH")"
DEV_IMG="$(alarm_dev_image "$ARCH")"
PLATFORM="$(alarm_platform "$ARCH")"

log "Building container rootfs image $ROOTFS_TAG ($PLATFORM)"
DOCKER_BUILDKIT=1 docker build \
    --platform "$PLATFORM" \
    --build-arg "BASE_IMAGE=$BASE_IMG" \
    -t "$ROOTFS_TAG" \
    -f "$CTX_DIR/Dockerfile" \
    "$CTX_DIR"

# 5. Export container filesystem and create the ext4 image via mke2fs -d
mkdir -p "$OUT_ROOTFS_DIR"
IMG_DIR="$(cd "$(dirname "$OUT_IMG")" && pwd)"
IMG_BASE="$(basename "$OUT_IMG")"

CID="$(docker create --platform "$PLATFORM" "$ROOTFS_TAG" /bin/true)"
cleanup() {
    docker rm -f "$CID" >/dev/null 2>&1 || true
}
trap cleanup EXIT

log "Exporting container filesystem and building ${SIZE_MIB} MiB ext4 image -> $OUT_IMG"
docker export "$CID" | docker run --rm -i \
    --platform "$PLATFORM" \
    -v "$IMG_DIR:/out" \
    -v "$SCRIPT_DIR/rootfs/mkimage.sh:/mkimage.sh:ro" \
    -e "OUT_IMG=/out/$IMG_BASE" \
    -e "SIZE_MIB=$SIZE_MIB" \
    "$DEV_IMG" \
    bash /mkimage.sh

[[ -f "$OUT_PKGS" ]] || die "packages.txt was not written to $OUT_PKGS"
IMG_BYTES="$(stat -f '%z' "$OUT_IMG" 2>/dev/null || stat -c '%s' "$OUT_IMG")"
IMG_HUMAN="$(du -h "$OUT_IMG" | awk '{print $1}')"
log "Package list written to $OUT_PKGS ($(wc -l < "$OUT_PKGS" | tr -d ' ') packages)"
printf '%s (%s bytes, %s on disk)\n' "$OUT_IMG" "$IMG_BYTES" "$IMG_HUMAN"
