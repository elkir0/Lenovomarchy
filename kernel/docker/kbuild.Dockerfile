# Reproducible native build environment for the arm64 mainline Linux 7.1
# kernel of the Lenovo Yoga Tab 11 (MediaTek MT6785), tree
# src/mt6785-mainline.  debian:trixie runs natively on Apple-silicon
# Docker (linux/arm64), and clang/LLVM builds the arm64 kernel natively
# (make LLVM=1 ARCH=arm64), so no cross toolchain is needed.
#
# The kernel tree is never written to by the image build itself: it is
# bind-mounted read-only at /src at run time and the out-of-tree build
# directory lives in the Docker named volume lenovomarchy-kbuild-out
# mounted at /build (see kernel/kbuild.sh).
#
# Build (from the repo root):
#   docker build --platform linux/arm64 \
#                -f kernel/docker/kbuild.Dockerfile \
#                -t lenovomarchy-kbuild kernel/docker
#
# Packages:
#   clang lld llvm                                      -> native LLVM build
#   make bc bison flex                                  -> kernel build system
#   libssl-dev libelf-dev                               -> host tools
#       (extract-cert, sign-file, resolve_btfids)
#   cpio kmod                                           -> initramfs, depmod
#   xz-utils lz4 gzip                                   -> kernel/modules
#       compression (Image.gz, modules.tar.xz)
#   python3 device-tree-compiler                        -> DT tooling
#   git rsync ca-certificates                           -> setlocalversion,
#       artifact handling, https apt
#   Plus, required by the postmarketOS base config (not by the build
#   system itself):
#   zstd        -> MODULE_COMPRESS_ZSTD=y runs the zstd binary during
#                  modules_install
#   openssl     -> MODULE_SIG_ALL=y auto-generates certs/signing_key.pem
#                  with the openssl CLI
#   dwarves     -> DEBUG_INFO_BTF=y needs pahole
#   zlib1g-dev  -> resolve_btfids links tools/lib/bpf, which includes
#                  zlib.h
#
# git safe.directory '*': the read-only bind mount of src/ is owned by
# the host user, not root; without this, git refuses to describe the
# tree and scripts/setlocalversion cannot append the -g<hash> suffix
# (LOCALVERSION_AUTO=y).

FROM --platform=linux/arm64 debian:trixie

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        clang \
        lld \
        llvm \
        make \
        bc \
        bison \
        flex \
        libssl-dev \
        libelf-dev \
        cpio \
        kmod \
        xz-utils \
        lz4 \
        gzip \
        python3 \
        device-tree-compiler \
        git \
        rsync \
        ca-certificates \
        zstd \
        openssl \
        dwarves \
        zlib1g-dev \
    && rm -rf /var/lib/apt/lists/* \
    && git config --global --add safe.directory '*'

# Upstream quality checks for new drivers: dt_binding_check needs
# dtschema (pip, in a venv) and yamllint; checkpatch.pl needs perl and,
# for its spelling and type checks, python3-ply and python3-git. mkbootimg
# (mkbootimg, unpack_bootimg) packs the tablet's boot and dtbo images.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3-venv python3-pip yamllint perl python3-ply python3-git \
        swig libyaml-dev gcc python3-dev mkbootimg \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/dtschema \
    && /opt/dtschema/bin/pip install --no-cache-dir dtschema
ENV PATH="/opt/dtschema/bin:${PATH}"
