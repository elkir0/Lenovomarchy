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

# Verify required read-only inputs exist
for req in \
    "$ROOT_DIR/input/modules.tar.xz" \
    "$ROOT_DIR/input/kernel.release" \
    "$ROOT_DIR/input/authorized_keys" \
    "$ROOT_DIR/input/prebuilt/omamobile-omarchy-0.1.32-1.2-any.pkg.tar.zst" \
    "$ROOT_DIR/input/prebuilt/omamobile-shell-0.2.94-5-any.pkg.tar.zst"; do
    [[ -f "$req" ]] || die "required input file not found: $req"
done

# 1. Ensure official Arch Linux ARM aarch64 tarball is downloaded, MD5-verified,
#    and imported into Docker (lenovomarchy:base-aarch64 & lenovomarchy:dev-aarch64).
alarm_ensure_base "$ARCH"
alarm_ensure_dev "$ARCH"

# 2. Populate local [lenovomarchy] repository with SHA-256 + GPG-verified Omarchy
#    packages and the prebuilt arch=any omamobile packages from input/prebuilt/.
if [[ ! -f "$REPO_DIR/$ARCH/lenovomarchy.db.tar.gz" ]] || \
   [[ ! -f "$REPO_DIR/$ARCH/omamobile-omarchy-0.1.32-1.2-any.pkg.tar.zst" ]] || \
   [[ ! -f "$REPO_DIR/$ARCH/omamobile-shell-0.2.94-5-any.pkg.tar.zst" ]] || \
   [[ ! -f "$REPO_DIR/$ARCH/omarchy-4.0.6-1-aarch64.pkg.tar.zst" ]]; then
    "$SCRIPT_DIR/tools/repack-omarchy"
    log "Copying prebuilt omamobile-omarchy and omamobile-shell archives from input/prebuilt/ -> $REPO_DIR/$ARCH"
    cp -f "$ROOT_DIR/input/prebuilt/omamobile-omarchy-0.1.32-1.2-any.pkg.tar.zst" "$REPO_DIR/$ARCH/"
    cp -f "$ROOT_DIR/input/prebuilt/omamobile-shell-0.2.94-5-any.pkg.tar.zst" "$REPO_DIR/$ARCH/"
    alarm_repo_index "$ARCH"
else
    log "Local [lenovomarchy] repository at $REPO_DIR/$ARCH is already populated and indexed"
fi

# 3. Stage Docker build context under cache/rootfs-context
CTX_DIR="$CACHE_DIR/rootfs-context"
rm -rf "$CTX_DIR"
mkdir -p "$CTX_DIR/repo" "$CTX_DIR/overlay"

cp -a "$SCRIPT_DIR/rootfs/." "$CTX_DIR/"
cp -a "$SCRIPT_DIR/overlay/." "$CTX_DIR/overlay/"
cp -a "$REPO_DIR/$ARCH/." "$CTX_DIR/repo/"
cp -f "$SCRIPT_DIR/pkg/omamobile-shell/tablet-shell.json" "$CTX_DIR/tablet-shell.json"
cp -f "$SCRIPT_DIR/pkg/omamobile-shell/tablet-home.json" "$CTX_DIR/tablet-home.json"
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
