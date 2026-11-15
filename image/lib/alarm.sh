#!/usr/bin/env bash
# Shared helpers for Arch Linux ARM (aarch64) Docker-based package and rootfs builds.
# Sourced by image/build-rootfs.sh, image/tools/repack-omarchy, and image/tools/build-pkg.

set -euo pipefail

IMAGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT_DIR="$(cd "$IMAGE_DIR/.." && pwd)"
OUT_DIR="${OUT_DIR:-$ROOT_DIR/out}"
CACHE_DIR="${CACHE_DIR:-$ROOT_DIR/cache}"
REPO_DIR="${REPO_DIR:-$CACHE_DIR/repo}"
REPO_NAME="${REPO_NAME:-lenovomarchy}"

ALARM_MIRROR="${ALARM_MIRROR:-http://os.archlinuxarm.org}"

log()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33mWARN:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

# Docker platform for a given ALARM architecture.
alarm_platform() {
    case "$1" in
        aarch64) echo "linux/arm64" ;;
        armv7h)  echo "linux/arm/v7" ;;
        *)       die "unsupported architecture: $1" ;;
    esac
}

# Rootfs tarball filename for a given ALARM architecture.
alarm_tarball() {
    case "$1" in
        aarch64) echo "ArchLinuxARM-aarch64-latest.tar.gz" ;;
        armv7h)  echo "ArchLinuxARM-armv7-latest.tar.gz" ;;
        *)       die "unsupported architecture: $1" ;;
    esac
}

alarm_base_image() { echo "lenovomarchy:base-$1"; }
alarm_dev_image()  { echo "lenovomarchy:dev-$1"; }

# Verify MD5 of a file against a .md5 sidecar (works on macOS and Linux).
verify_md5() {
    local file="$1" md5file="$2" expected actual
    expected="$(awk '{print $1}' "$md5file")"
    if command -v md5sum >/dev/null 2>&1; then
        actual="$(md5sum "$file" | awk '{print $1}')"
    elif command -v md5 >/dev/null 2>&1; then
        actual="$(md5 -q "$file")"
    else
        die "neither md5sum nor md5 found"
    fi
    [[ "$expected" == "$actual" ]] || die "MD5 mismatch for $file: expected $expected, got $actual"
}

# Ensure the raw ALARM rootfs tarball is cached, verified, and imported into Docker.
alarm_ensure_base() {
    local arch="$1"
    local img platform tarball url
    img="$(alarm_base_image "$arch")"
    platform="$(alarm_platform "$arch")"
    tarball="$(alarm_tarball "$arch")"
    url="$ALARM_MIRROR/os/$tarball"

    mkdir -p "$CACHE_DIR"
    if [[ ! -f "$CACHE_DIR/$tarball" ]]; then
        log "Downloading $tarball from $url"
        curl -fL --retry 3 -o "$CACHE_DIR/$tarball.part" "$url"
        curl -fL --retry 3 -o "$CACHE_DIR/$tarball.md5" "$url.md5"
        verify_md5 "$CACHE_DIR/$tarball.part" "$CACHE_DIR/$tarball.md5"
        mv "$CACHE_DIR/$tarball.part" "$CACHE_DIR/$tarball"
    else
        if [[ ! -f "$CACHE_DIR/$tarball.md5" ]]; then
            curl -fL --retry 3 -o "$CACHE_DIR/$tarball.md5" "$url.md5"
        fi
        log "Verifying cached $tarball against $tarball.md5"
        verify_md5 "$CACHE_DIR/$tarball" "$CACHE_DIR/$tarball.md5"
    fi

    if docker image inspect "$img" >/dev/null 2>&1; then
        return 0
    fi

    log "Importing $tarball -> $img ($platform)"
    docker import \
        --platform "$platform" \
        --change 'CMD ["/bin/bash"]' \
        --change 'ENV PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin' \
        "$CACHE_DIR/$tarball" "$img" >/dev/null
}

# Ensure the base-devel + builder-user image exists for $arch.
alarm_ensure_dev() {
    local arch="$1"
    local base dev platform
    base="$(alarm_base_image "$arch")"
    dev="$(alarm_dev_image "$arch")"
    platform="$(alarm_platform "$arch")"

    alarm_ensure_base "$arch"

    if docker image inspect "$dev" >/dev/null 2>&1; then
        return 0
    fi

    log "Building $dev ($platform) — initializing keyring and installing base-devel"
    docker build \
        --platform "$platform" \
        --build-arg "BASE_IMAGE=$base" \
        -t "$dev" \
        -f "$IMAGE_DIR/lib/alarm-dev.Dockerfile" \
        "$IMAGE_DIR/lib"
}

# Re-index the local pacman repository at $REPO_DIR/$arch cleanly from *.pkg.tar*.
alarm_repo_index() {
    local arch="$1"
    local repo_arch_dir="$REPO_DIR/$arch"
    mkdir -p "$repo_arch_dir"

    shopt -s nullglob
    local pkgs=("$repo_arch_dir"/*.pkg.tar.xz "$repo_arch_dir"/*.pkg.tar.zst)
    shopt -u nullglob
    if [[ ${#pkgs[@]} -eq 0 ]]; then
        warn "No packages in $repo_arch_dir to index"
        return 0
    fi

    alarm_ensure_dev "$arch"
    local dev platform
    dev="$(alarm_dev_image "$arch")"
    platform="$(alarm_platform "$arch")"

    log "Indexing repository [$REPO_NAME] in $repo_arch_dir (${#pkgs[@]} package file(s))"
    docker run --rm --platform "$platform" \
        -v "$repo_arch_dir:/repo" \
        "$dev" \
        bash -ec "
            shopt -s nullglob
            rm -f /repo/${REPO_NAME}.db* /repo/${REPO_NAME}.files*
            # Keep only the newest file per pkgname when multiple versions exist.
            declare -A newest
            for p in /repo/*.pkg.tar.xz /repo/*.pkg.tar.zst; do
                name=\$(bsdtar -xOf \"\$p\" .PKGINFO | awk -F' = ' '\$1==\"pkgname\"{print \$2; exit}')
                if [[ -n \"\${newest[\$name]:-}\" ]]; then
                    cmp=\$(vercmp \"\$p\" \"\${newest[\$name]}\")
                    if [[ \$cmp -gt 0 ]]; then
                        rm -f \"\${newest[\$name]}\"
                        newest[\$name]=\"\$p\"
                    else
                        rm -f \"\$p\"
                    fi
                else
                    newest[\$name]=\"\$p\"
                fi
            done
            repo-add -q /repo/${REPO_NAME}.db.tar.gz \"\${newest[@]}\"
        "
}
