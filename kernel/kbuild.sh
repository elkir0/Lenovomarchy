#!/usr/bin/env bash
# Build the arm64 mainline Linux 7.1 kernel for the Lenovo Yoga Tab 11
# (MediaTek MT6785) in Docker, natively on Apple silicon with LLVM.
#
# The kernel tree (src/mt6785-mainline, Dinolek/mt6785-mainline branch
# 7.1) is bind-mounted READ-ONLY into the container at /src and built
# out-of-tree (O=/build) inside the Docker named volume
# lenovomarchy-kbuild-out, so the tree never receives build files and
# incremental rebuilds are fast.
#
# Configuration: on a fresh volume the .config is seeded from
# kernel/configs/pmos-mt6785.config (postmarketOS config for this tree
# at Linux 6.16.4); every run then merges the project fragment
# kernel/configs/yoga11.config with scripts/kconfig/merge_config.sh -m
# and refreshes defaults with make olddefconfig.
#
# Usage:
#   kernel/kbuild.sh [--clean] [--rebuild-image] [-j N]
#
#   --clean          remove the build volume first and rebuild from
#                    scratch
#   --rebuild-image  rebuild the lenovomarchy-kbuild Docker image even
#                    if it already exists
#   -j N             parallel jobs (default: host CPU count)
#   -h, --help       print this header
#
# Environment overrides:
#   YT11_KERNEL_DIR  kernel tree (default: src/mt6785-mainline)
#   KBUILD_VOLUME    build volume name (default: lenovomarchy-kbuild-out)
#   KBUILD_OUT_DIR   output directory (default: out/kernel)
#   KBUILD_EXTRA_FRAGMENT  extra config fragment merged after yoga11.config
#   KBUILD_BUILD_TIMESTAMP, KBUILD_BUILD_VERSION, KBUILD_BUILD_USER and
#   KBUILD_BUILD_HOST reach make when set: a kernel to publish carries a
#   fixed build date and version, not the time it was built.
#
# Output in out/kernel/: Image.gz, dtbs/mediatek/mt6785-*.dtb,
# modules.tar.xz, config (final .config) and kernel.release.
#
# Boot partition budget: 32 MiB total shared by kernel + initramfs +
# DTB; the script fails if Image.gz exceeds 24 MiB.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
SOURCE_DIR="${YT11_KERNEL_DIR:-${REPO_ROOT}/src/mt6785-mainline}"
CONFIGS_DIR="${REPO_ROOT}/kernel/configs"
BASE_CONFIG_NAME="pmos-mt6785.config"
FRAGMENT_NAME="yoga11.config"
IMAGE_TAG="lenovomarchy-kbuild"
VOLUME="${KBUILD_VOLUME:-lenovomarchy-kbuild-out}"
OUT_DIR="${KBUILD_OUT_DIR:-${REPO_ROOT}/out/kernel}"
# docker -v needs an absolute host path.
[[ "$OUT_DIR" = /* ]] || OUT_DIR="$PWD/$OUT_DIR"
# Optional extra fragment merged after yoga11.config (a worker's test
# options, e.g. KUnit), as an absolute path; the build volume should be
# that worker's own (KBUILD_VOLUME).
EXTRA_FRAG="${KBUILD_EXTRA_FRAGMENT:-}"
if [[ -n "$EXTRA_FRAG" ]]; then
    [[ -f "$EXTRA_FRAG" ]] || { echo "error: KBUILD_EXTRA_FRAGMENT not found: $EXTRA_FRAG" >&2; exit 2; }
    EXTRA_FRAG="$(cd "$(dirname "$EXTRA_FRAG")" && pwd -P)/$(basename "$EXTRA_FRAG")"
fi
EXTRA_MOUNT=()
[[ -n "$EXTRA_FRAG" ]] && EXTRA_MOUNT=(-v "$(dirname "$EXTRA_FRAG"):/extra:ro")
IMAGE_MAX_BYTES=$((24 * 1024 * 1024))

# Host-portable CPU count: GNU/Linux nproc, macOS sysctl, POSIX getconf.
if command -v nproc >/dev/null 2>&1; then
    JOBS="$(nproc)"
elif command -v sysctl >/dev/null 2>&1; then
    JOBS="$(sysctl -n hw.ncpu)"
else
    JOBS="$(getconf _NPROCESSORS_ONLN)"
fi

CLEAN=0
REBUILD_IMAGE=0
print_header() {
    awk 'NR == 1 { next } /^#/ { sub(/^#[ ]?/, ""); print; next } { exit }' "$0"
}
while [[ $# -gt 0 ]]; do
    case "$1" in
        --clean) CLEAN=1; shift ;;
        --rebuild-image) REBUILD_IMAGE=1; shift ;;
        -j)
            [[ $# -ge 2 ]] || { echo "error: -j needs a value" >&2; exit 2; }
            JOBS="$2"; shift 2 ;;
        -j*) JOBS="${1#-j}"; shift ;;
        -h|--help)
            print_header; exit 0 ;;
        *)
            echo "error: unknown option: $1" >&2; print_header >&2; exit 2 ;;
    esac
done

# --- sanity checks -----------------------------------------------------------
[[ -d "$SOURCE_DIR" ]] || { echo "error: kernel tree not found: $SOURCE_DIR (set YT11_KERNEL_DIR)" >&2; exit 2; }
SOURCE_DIR="$(cd "$SOURCE_DIR" && pwd -P)"
[[ -f "$SOURCE_DIR/Makefile" ]] || { echo "error: $SOURCE_DIR has no Makefile" >&2; exit 2; }
[[ -f "$CONFIGS_DIR/$BASE_CONFIG_NAME" ]] || { echo "error: $CONFIGS_DIR/$BASE_CONFIG_NAME not found" >&2; exit 2; }
[[ -f "$CONFIGS_DIR/$FRAGMENT_NAME" ]] || { echo "error: $CONFIGS_DIR/$FRAGMENT_NAME not found" >&2; exit 2; }
command -v docker >/dev/null 2>&1 || { echo "error: docker not found in PATH" >&2; exit 2; }

# --- docker image ------------------------------------------------------------
if [[ $REBUILD_IMAGE -eq 1 ]] || ! docker image inspect "$IMAGE_TAG" >/dev/null 2>&1; then
    echo ">>> Building Docker image $IMAGE_TAG"
    docker build --platform linux/arm64 \
        -f "$REPO_ROOT/kernel/docker/kbuild.Dockerfile" \
        -t "$IMAGE_TAG" "$REPO_ROOT/kernel/docker"
fi

# --- build volume ------------------------------------------------------------
if [[ $CLEAN -eq 1 ]]; then
    echo ">>> --clean: removing build volume $VOLUME"
    docker volume rm -f "$VOLUME" >/dev/null
fi
docker volume create "$VOLUME" >/dev/null
mkdir -p "$OUT_DIR"

# --- make wrapper ------------------------------------------------------------
# The kernel tree is mounted read-only; everything make writes goes to
# /build in the named volume.  KBUILD_BUILD_* reach make when set.
run_make() {
    local v kv=()
    for v in KBUILD_BUILD_TIMESTAMP KBUILD_BUILD_VERSION KBUILD_BUILD_USER KBUILD_BUILD_HOST; do
        [[ -n "${!v:-}" ]] && kv+=("$v=${!v}")
    done
    docker run --rm \
        --platform linux/arm64 \
        -v "$SOURCE_DIR:/src:ro" \
        -v "$VOLUME:/build" \
        -w /src \
        "$IMAGE_TAG" \
        make LLVM=1 ARCH=arm64 O=/build ${kv[@]+"${kv[@]}"} "$@"
}

# --- configuration -----------------------------------------------------------
# Fresh volume: seed .config from the postmarketOS base config.  Every
# run: merge the yoga11 fragment on top, then let olddefconfig carry the
# result to this kernel's symbols.  merge_config.sh creates its temp
# files in the CWD, so it runs with -w /build, not -w /src.
echo ">>> Configuring ($BASE_CONFIG_NAME + $FRAGMENT_NAME, olddefconfig)"
docker run --rm \
    --platform linux/arm64 \
    -v "$SOURCE_DIR:/src:ro" \
    -v "$CONFIGS_DIR:/frags:ro" \
    ${EXTRA_MOUNT[@]+"${EXTRA_MOUNT[@]}"} \
    -v "$VOLUME:/build" \
    -w /build \
    "$IMAGE_TAG" \
    bash -ec '
        if [ ! -f /build/.config ]; then
            echo ">>> fresh build volume: seeding .config from '"$BASE_CONFIG_NAME"'"
            cp "/frags/'"$BASE_CONFIG_NAME"'" /build/.config
        fi
        /src/scripts/kconfig/merge_config.sh -m -O /build /build/.config "/frags/'"$FRAGMENT_NAME"'" '"${EXTRA_FRAG:+/extra/$(basename "$EXTRA_FRAG")}"'
    '
run_make olddefconfig

# --- build -------------------------------------------------------------------
echo ">>> Building Image.gz + DTBs + modules (-j$JOBS)"
run_make -j"$JOBS" Image.gz dtbs modules

# --- modules -----------------------------------------------------------------
# The volume persists between builds: drop module trees left by earlier
# kernel releases, or modules.tar.xz carries several lib/modules/<release>.
echo ">>> Installing modules"
docker run --rm --platform linux/arm64 -v "$VOLUME:/build" \
    "$IMAGE_TAG" bash -ec "rm -rf /build/mod-install"
run_make -j"$JOBS" INSTALL_MOD_PATH=/build/mod-install INSTALL_MOD_STRIP=1 modules_install
echo ">>> Packaging modules.tar.xz"
docker run --rm --platform linux/arm64 -v "$VOLUME:/build" \
    "$IMAGE_TAG" bash -ec "tar -C /build/mod-install -cJf /build/modules.tar.xz ."

# --- artifacts ---------------------------------------------------------------
echo ">>> Copying artifacts to $OUT_DIR"
mkdir -p "$OUT_DIR/dtbs/mediatek"
docker run --rm --platform linux/arm64 \
    -v "$VOLUME:/build" -v "$OUT_DIR:/out" \
    "$IMAGE_TAG" \
    bash -ec '
        set -e
        cp -f /build/arch/arm64/boot/Image.gz /out/
        cp -f /build/arch/arm64/boot/dts/mediatek/mt6785-*.dtb /out/dtbs/mediatek/
        cp -f /build/.config /out/config
        cp -f /build/include/config/kernel.release /out/kernel.release
        cp -f /build/modules.tar.xz /out/
    '

# --- size check (runs on the host; macOS/BSD stat has -f) --------------------
image_bytes=$(stat -f %z "$OUT_DIR/Image.gz" 2>/dev/null || stat -c %s "$OUT_DIR/Image.gz")
echo ">>> Image.gz: $image_bytes bytes of the $IMAGE_MAX_BYTES-byte budget"
if (( image_bytes > IMAGE_MAX_BYTES )); then
    echo "ERROR: Image.gz is $image_bytes bytes > 24 MiB budget ($IMAGE_MAX_BYTES);" >&2
    echo "the 32 MiB boot partition must also hold the initramfs and the DTB" >&2
    exit 1
fi

echo ">>> Done: $(cat "$OUT_DIR/kernel.release")"
exit 0
