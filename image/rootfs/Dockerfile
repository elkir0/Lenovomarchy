# syntax=docker/dockerfile:1
# Builds the complete Arch Linux ARM (aarch64) + Omarchy rootfs for the
# Lenovo Yoga Tab 11 (YT-J706F, MediaTek MT6785).

ARG BASE_IMAGE=lenovomarchy:base-aarch64
FROM ${BASE_IMAGE}

ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

COPY repo/                  /tmp/build/repo/
COPY packages.omarchy-skip  /tmp/build/packages.omarchy-skip
COPY packages.extra         /tmp/build/packages.extra
COPY setup-pacman.sh        /tmp/build/setup-pacman.sh
COPY install-packages.sh    /tmp/build/install-packages.sh

RUN --mount=type=cache,target=/var/cache/pacman/pkg,id=lenovomarchy-pacman-aarch64 \
    chmod +x /tmp/build/*.sh && \
    /tmp/build/setup-pacman.sh && \
    /tmp/build/install-packages.sh

COPY overlay/               /tmp/build/overlay/
COPY modules.tar.xz         /tmp/build/modules.tar.xz
COPY kernel.release         /tmp/build/kernel.release
COPY authorized_keys        /tmp/build/authorized_keys
COPY looknfeel.lua          /tmp/build/looknfeel.lua
COPY configure-system.sh    /tmp/build/configure-system.sh
COPY omarchy-system-setup.sh /tmp/build/omarchy-system-setup.sh
COPY omarchy-user-setup.sh  /tmp/build/omarchy-user-setup.sh

RUN chmod +x /tmp/build/*.sh && \
    /tmp/build/configure-system.sh && \
    /tmp/build/omarchy-system-setup.sh && \
    /tmp/build/omarchy-user-setup.sh

COPY packages.mobile        /tmp/build/packages.mobile
COPY tablet.lua             /tmp/build/tablet.lua
COPY tablet-shell.json      /tmp/build/tablet-shell.json
COPY tablet-home.json       /tmp/build/tablet-home.json
COPY wallpapers.sh          /tmp/build/wallpapers.sh
COPY install-mobile.sh      /tmp/build/install-mobile.sh
COPY smoke-check.sh         /tmp/build/smoke-check.sh
COPY finalize.sh            /tmp/build/finalize.sh

RUN --mount=type=cache,target=/var/cache/pacman/pkg,id=lenovomarchy-pacman-aarch64 \
    chmod +x /tmp/build/*.sh && \
    /tmp/build/install-mobile.sh && \
    /tmp/build/finalize.sh && \
    /tmp/build/smoke-check.sh && \
    rm -rf /tmp/* /var/tmp/*

CMD ["/bin/bash"]
