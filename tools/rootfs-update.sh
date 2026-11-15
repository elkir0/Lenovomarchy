#!/usr/bin/env bash
# Update a built Omarchy root image in place for the current kernel:
# replace /usr/lib/modules with <modules.tar.xz> (depmod in a chroot),
# install yt11-bootctl and the unit that marks the A/B slot successful
# once the system is up. Optionally write a sparse copy for fastboot.
#
# Usage: tools/rootfs-update.sh <rootfs.img> <modules.tar.xz> [<sparse out.simg>]

set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMG="${1:?usage: $0 <rootfs.img> <modules.tar.xz> [<out.simg>]}"
MODS="${2:?modules.tar.xz}"
SIMG="${3:-}"
abs() { (cd "$(dirname "$1")" && echo "$(pwd -P)/$(basename "$1")"); }
IMG=$(abs "$IMG"); MODS=$(abs "$MODS")

docker run --rm --privileged --platform linux/arm64 \
    -v "$IMG:/img/rootfs.img" -v "$MODS:/in/modules.tar.xz:ro" \
    -v "$REPO/initramfs/files/usr/sbin/yt11-bootctl:/in/yt11-bootctl:ro" \
    alpine:3.22 sh -ec '
        apk add -q xz >/dev/null
        mkdir -p /mnt/r
        mount -o loop /img/rootfs.img /mnt/r
        trap "umount /mnt/r" EXIT
        rm -rf /mnt/r/usr/lib/modules/*
        tar -C /mnt/r/usr -xJf /in/modules.tar.xz ./lib/modules
        rel=$(ls /mnt/r/usr/lib/modules)
        rm -f /mnt/r/usr/lib/modules/$rel/build
        chroot /mnt/r depmod "$rel"
        install -Dm755 /in/yt11-bootctl /mnt/r/usr/local/sbin/yt11-bootctl
        cat > /mnt/r/etc/systemd/system/yt11-boot-successful.service <<EOF
[Unit]
Description=Mark this A/B boot slot successful
After=multi-user.target
ConditionPathExists=/usr/local/sbin/yt11-bootctl

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/yt11-bootctl mark-successful

[Install]
WantedBy=multi-user.target
EOF
        ln -sf ../yt11-boot-successful.service \
            /mnt/r/etc/systemd/system/multi-user.target.wants/yt11-boot-successful.service
        echo "modules: $rel ($(find /mnt/r/usr/lib/modules/$rel -name "*.ko*" | wc -l) files)"
    '
if [[ -n "$SIMG" ]]; then
    mkdir -p "$(dirname "$SIMG")"; SIMG=$(abs "$SIMG")
    docker run --rm --platform linux/arm64 -v "$IMG:/img/rootfs.img:ro" \
        -v "$(dirname "$SIMG"):/out" lenovomarchy-kbuild sh -ec '
            command -v img2simg >/dev/null || { apt-get update -qq >/dev/null; apt-get install -y -qq android-sdk-libsparse-utils >/dev/null; }
            img2simg /img/rootfs.img "/out/'"$(basename "$SIMG")"'"'
    ls -l "$SIMG" | awk '{print "sparse image:", $5, "bytes"}'
fi
