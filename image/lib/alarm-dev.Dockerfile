ARG BASE_IMAGE=lenovomarchy:base-aarch64
FROM ${BASE_IMAGE}

# Disable seccomp sandbox inside Docker Desktop / container builds
RUN sed -i 's/^#*\(DisableSandbox\).*/\1/' /etc/pacman.conf && \
    grep -q '^DisableSandbox' /etc/pacman.conf || \
    sed -i '/^\[options\]/a DisableSandbox' /etc/pacman.conf

# Remove kernel & firmware packages from the base rootfs before -Syu so we don't
# waste bandwidth upgrading ~500 MB of kernel/firmware inside the builder container.
RUN pacman-key --init && \
    pacman-key --populate archlinuxarm && \
    pacman -Rdd --noconfirm linux-aarch64 linux-firmware linux-firmware-whence \
        $(pacman -Qq | grep '^linux-firmware-' || true) 2>/dev/null || true && \
    pacman -Syu --noconfirm --needed \
        base-devel git sudo zstd xz jq python meson ninja cmake pkgconf

# Non-root builder user required by makepkg
RUN useradd -m -G wheel -s /bin/bash builder && \
    echo 'builder ALL=(ALL) NOPASSWD: ALL' > /etc/sudoers.d/builder && \
    chmod 0440 /etc/sudoers.d/builder && \
    sed -i 's/^PKGEXT=.*/PKGEXT=".pkg.tar.xz"/' /etc/makepkg.conf && \
    sed -i 's/^#*\s*MAKEFLAGS=.*/MAKEFLAGS="-j$(nproc)"/' /etc/makepkg.conf
