#!/usr/bin/env bash
# Build the Lenovomarchy bring-up initramfs in an alpine:3.22 arm64
# Docker container: out/initramfs/initramfs.cpio.gz (newc, gzip -9,
# root-owned entries) plus out/initramfs/contents.txt.
#
# Environment:
#   YT11_SSH_PUBKEY  path to a .pub file installed as
#                    /root/.ssh/authorized_keys (mode 600), or the word
#                    "none": no key, so /init leaves SSH off in the
#                    initramfs (images meant to be published)
# Optional:
#   YT11_AUTOTEST    path to a script installed as /autotest.sh (755)

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ROOT_DIR=$(cd "$SCRIPT_DIR/.." && pwd)
OUT_DIR="$ROOT_DIR/out/initramfs"

die() {
    printf 'build.sh: error: %s\n' "$*" >&2
    exit 1
}

abspath() {
    case $1 in
        /*) printf '%s\n' "$1" ;;
        *) printf '%s/%s\n' "$PWD" "$1" ;;
    esac
}

[ -n "${YT11_SSH_PUBKEY:-}" ] || die "YT11_SSH_PUBKEY is required (path to a .pub file, or none)"
PUBKEY_MOUNT=()
if [ "$YT11_SSH_PUBKEY" != none ]; then
    PUBKEY=$(abspath "$YT11_SSH_PUBKEY")
    [ -f "$PUBKEY" ] || die "public key file not found: $PUBKEY"
    # Never let a private key slip into the image.
    if grep -q 'PRIVATE KEY' "$PUBKEY"; then
        die "refusing $PUBKEY: file contains a PRIVATE KEY"
    fi
    [ -s "$PUBKEY" ] || die "public key file is empty: $PUBKEY"
    PUBKEY_MOUNT=(-v "$PUBKEY:/src-pubkey:ro")
fi

AUTOTEST_MOUNT=()
if [ -n "${YT11_AUTOTEST:-}" ]; then
    AUTOTEST=$(abspath "$YT11_AUTOTEST")
    [ -f "$AUTOTEST" ] || die "YT11_AUTOTEST file not found: $AUTOTEST"
    AUTOTEST_MOUNT=(-v "$AUTOTEST:/src-autotest:ro")
fi

[ -x "$SCRIPT_DIR/init" ] || chmod +x "$SCRIPT_DIR/init" || true
mkdir -p "$OUT_DIR"

# Everything heavy happens inside the container; the host only mounts
# files in and the output directory out.
docker run --rm --platform linux/arm64 \
    -v "$SCRIPT_DIR/init:/src-init:ro" \
    -v "$SCRIPT_DIR/files:/src-files:ro" \
    ${PUBKEY_MOUNT[@]+"${PUBKEY_MOUNT[@]}"} \
    ${AUTOTEST_MOUNT[@]+"${AUTOTEST_MOUNT[@]}"} \
    -v "$OUT_DIR:/out" \
    alpine:3.22 sh -euc '
        # Stage inside the container FS: the macOS bind mount under /out
        # rejects mknod, while /tmp allows it (default CAP_MKNOD).
        S=/tmp/stage
        rm -rf "$S"
        mkdir -p "$S"

        apk add --root "$S" --initdb --no-cache \
            --repositories-file /etc/apk/repositories \
            --keys-dir /etc/apk/keys \
            busybox dropbear dnsmasq >/dev/null

        # Drop apk bookkeeping; the runtime never needs it.
        rm -rf "$S/lib/apk/db" "$S/etc/apk" "$S/var"

        install -m 0755 /src-init "$S/init"
        cp -a /src-files/. "$S/"

        mkdir -p "$S/root/.ssh"
        if [ -e /src-pubkey ]; then
            install -m 0600 /src-pubkey "$S/root/.ssh/authorized_keys"
        fi
        chmod 0700 "$S/root/.ssh"

        if [ -e /src-autotest ]; then
            install -m 0755 /src-autotest "$S/autotest.sh"
        fi

        # Static early-dev nodes so PID 1 has a console before devtmpfs
        # is mounted; devtmpfs hides them once mounted.  Some packages
        # already ship them, hence rm -f.
        mkdir -p "$S/dev"
        rm -f "$S/dev/console" "$S/dev/null"
        mknod -m 0600 "$S/dev/console" c 5 1
        mknod -m 0666 "$S/dev/null" c 1 3

        # Sanity checks on the pieces the init script depends on.
        for f in init bin/busybox sbin/init sbin/getty sbin/switch_root \
                 sbin/watchdog usr/sbin/dropbear usr/sbin/dnsmasq \
                 etc/inittab \
                 etc/dnsmasq-usb0.conf etc/passwd; do
            [ -e "$S/$f" ] || { echo "build.sh: missing in stage: $f" >&2; exit 1; }
        done
        [ ! -e /src-pubkey ] || [ -s "$S/root/.ssh/authorized_keys" ] || {
            echo "build.sh: authorized_keys missing in stage" >&2; exit 1; }
        [ ! -e /src-autotest ] || [ -x "$S/autotest.sh" ] || {
            echo "build.sh: autotest.sh not executable in stage" >&2; exit 1; }

        cd "$S"
        find . | LC_ALL=C sort | tee /out/contents.txt \
            | cpio -o -H newc -R 0:0 2>/dev/null | gzip -9 > /out/initramfs.cpio.gz
        rm -rf "$S"
    '

SIZE=$(wc -c <"$OUT_DIR/initramfs.cpio.gz" | tr -d ' ')
printf 'initramfs: %s bytes (%s)\n' "$SIZE" "$OUT_DIR/initramfs.cpio.gz"
