# Build from source

This guide builds the kernel, initramfs, boot image, and Omarchy root
filesystem from source, then flashes them to the YT-J706F.

## Prerequisites

- **macOS** (Apple Silicon native `linux/arm64` Docker) or **Linux**.
- **Docker** running.
- Host tools: `git`, `python3`, `dtc` (device-tree-compiler), `adb`,
  `fastboot`, `ssh` with an Ed25519 key pair.
- **macOS case-sensitive volume:** the Linux kernel source tree requires a
  case-sensitive filesystem, so `src/` cannot live directly on macOS's
  default case-insensitive APFS. Mount a case-sensitive APFS volume at `src/`
  before cloning the kernel tree: create a sparse bundle once, then attach
  it (again after each reboot of the Mac):

```bash
hdiutil create -size 40g -type SPARSEBUNDLE -fs "Case-sensitive APFS" -volname src .src.sparsebundle
```

```bash
mkdir -p src && diskutil image attach --mountPoint src .src.sparsebundle
```

## Step 1: Clone the repositories

Clone this repository and check out the `yt11` kernel branch into
`src/mt6785-mainline`:

```bash
git clone https://github.com/elkir0/Lenovomarchy.git && cd Lenovomarchy
```

```bash
git clone -b yt11 https://github.com/elkir0/mt6785-mainline.git src/mt6785-mainline
```

## Step 2: Build the kernel

Build `out/kernel/Image.gz`, the MT6785 device trees, and
`out/kernel/modules.tar.xz` inside Docker (`lenovomarchy-kbuild`), see
[kernel/README.md](../kernel/README.md) for options:

```bash
bash kernel/kbuild.sh
```

Optionally verify that every option in `kernel/configs/yoga11.config` reached
the final `.config`:

```bash
bash kernel/check-config.sh out/kernel/config kernel/configs/yoga11.config
```

## Step 3: Build the initramfs

Build `out/initramfs/initramfs.cpio.gz` with your SSH public key installed
(or `YT11_SSH_PUBKEY=none` for an image without initramfs SSH); see
[initramfs/README.md](../initramfs/README.md):

```bash
YT11_SSH_PUBKEY=~/.ssh/id_ed25519.pub bash initramfs/build.sh
```

Optionally run the QEMU smoke test:

```bash
bash initramfs/test-qemu.sh
```

## Step 4: Pack the boot image

Pack `out/boot/boot.img` and an empty `out/boot/dtbo.img` using
[`tools/mkboot.sh`](../tools/mkboot.sh); `--cmdline` must be the first
argument. Passing `yt11.root=PARTLABEL=userdata` tells the initramfs
`/init` script to resolve the GPT partition named `userdata` via sysfs
([initramfs/README.md](../initramfs/README.md)):

```bash
tools/mkboot.sh --cmdline "yt11.root=PARTLABEL=userdata" \
    out/kernel/Image.gz \
    out/kernel/dtbs/mediatek/mt6785-lenovo-yt-j706f.dtb \
    out/initramfs/initramfs.cpio.gz \
    out/boot
```

## Step 5: Build the root filesystem image

Stage the three required inputs into `input/` (`modules.tar.xz`,
`kernel.release`, and `authorized_keys`):

```bash
mkdir -p input && cp out/kernel/modules.tar.xz out/kernel/kernel.release input/ && cp ~/.ssh/id_ed25519.pub input/authorized_keys
```

For an image meant to be published, put a single comment line in
`input/authorized_keys` instead of a key: the image then accepts no SSH
login until `tools/image-set-key.sh` installs one (that is how the release
image is made).

Build `out/rootfs/rootfs-omarchy-aarch64.img` (this builds `omamobile-omarchy`,
`omamobile-shell`, and `libcamera-yt11` in arm64 Docker containers and
assembles the 8 GiB ext4 image; see [image/README.md](../image/README.md)):

```bash
bash image/build-rootfs.sh
```

Optionally run the read-only verification check inside Docker:

```bash
bash image/verify-rootfs.sh out/rootfs/rootfs-omarchy-aarch64.img
```

## Step 6: Flash and install firmware

Make sure the bootloader is unlocked first (see
[docs/INSTALL.md](INSTALL.md)). Flash the root image to `userdata` (the
tablet stays in fastboot afterwards):

```bash
tools/flash-rootfs.sh out/rootfs/rootfs-omarchy-aarch64.img
```

Flash `boot.img` and `dtbo.img` to slot `a`, set slot `a` active, and
reboot:

```bash
tools/flash-slot.sh a out/boot/boot.img out/boot/dtbo.img
```

Once Linux answers on the USB network (`192.168.77.1`), extract and install
the three non-redistributable Lenovo firmware sets from your stock
`super.img` and reboot:

```bash
tools/touch-firmware.sh /path/to/super.img --install
```

```bash
tools/amp-firmware.sh /path/to/super.img --install
```

```bash
tools/mic-firmware.sh /path/to/super.img --install
```

```bash
tools/ytssh systemctl reboot
```

## Day-to-day kernel rebuilds

When iterating on the kernel with Omarchy already installed on `userdata`,
push the new modules over SSH, repack `boot.img`, and flash slot `a` (or use
`tools/linux-test.sh out/boot/boot.img out/boot/dtbo.img` to capture boot
outcome logs automatically); see [tools/README.md](../tools/README.md):

```bash
bash kernel/kbuild.sh
```

```bash
tools/push-modules.sh
```

```bash
tools/mkboot.sh --cmdline "yt11.root=PARTLABEL=userdata" \
    out/kernel/Image.gz \
    out/kernel/dtbs/mediatek/mt6785-lenovo-yt-j706f.dtb \
    out/initramfs/initramfs.cpio.gz \
    out/boot
```

```bash
tools/flash-slot.sh a out/boot/boot.img out/boot/dtbo.img
```

To update an already-built `rootfs.img` on the host with new kernel modules
and the A/B slot-success service without rebuilding the whole image, run:

```bash
tools/rootfs-update.sh out/rootfs/rootfs-omarchy-aarch64.img out/kernel/modules.tar.xz
```
