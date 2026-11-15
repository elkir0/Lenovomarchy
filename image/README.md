# Lenovomarchy Root Filesystem Build (`aarch64`)

Docker-based pipeline that builds `out/rootfs/rootfs-omarchy-aarch64.img`, a raw
ext4 root filesystem image running Arch Linux ARM (`aarch64`), Hyprland, and
Omarchy with its Quickshell tablet shell for the Lenovo Yoga Tab 11 (`YT-J706F`,
MediaTek Helio G90T / MT6785).

## What the Build Does

1. **Base Arch Linux ARM (`aarch64`)**: Downloads `ArchLinuxARM-aarch64-latest.tar.gz`
   and `.md5` into `cache/`, verifies its MD5 digest, and imports it into Docker
   (`lenovomarchy:base-aarch64`).
2. **Omarchy Supply-Chain Verification (`tools/repack-omarchy`)**: Downloads pinned
   packages from `https://pkgs.omarchy.org/stable/aarch64/`, verifies every file's
   SHA-256 digest against `tools/repack.pins` and detached GPG signature against
   `omarchy-keyring` (`tools/omarchy-trusted.fpr`), confirms `omarchy` and
   `omarchy-settings` contain no ELF binaries, and indexes a local `[lenovomarchy]`
   pacman repository.
3. **Tablet Touch Layer (`input/prebuilt/`, `pkg/`)**: Publishes the prebuilt
   `arch=any` `omamobile-omarchy` (idempotent patch series over
   `/usr/share/omarchy`) and `omamobile-shell` (Quickshell touch status bar,
   quick settings, app drawer, task switcher, home screen, OSK hide button, and
   back gesture) archives from `input/prebuilt/` into `[lenovomarchy]` (their
   PKGBUILDs are kept under `image/pkg/` for reference as upstream is offline).
4. **Rootfs Assembly (`rootfs/Dockerfile`)**:
   - Removes the stock `linux-aarch64` kernel package and installs Omarchy,
     `hyprland`, `mesa` (Panfrost for Mali-G76), `linux-firmware-mediatek`
     (`mediatek/mt7663*`), `chromium`, `sddm`, `networkmanager`, `openssh`,
     `dnsmasq`, `squeekboard`, and system utilities.
   - Installs kernel modules from `input/modules.tar.xz` into
     `/usr/lib/modules/$(cat input/kernel.release)` and runs `depmod`.
   - Applies `image/overlay/` (`PARTLABEL=userdata` `/etc/fstab`, first-boot
     `lenovomarchy-resize-rootfs.service`, configfs `usb-gadget.service` with
     `ecm.usb0` at `192.168.77.1/24` + `dnsmasq` DHCP serving `192.168.77.2` +
     `acm.GS0`, `serial-getty@ttyGS0.service`, `sshd.service` with key-only login
     from `input/authorized_keys`, and Hyprland monitor config with `scale = 1.5`
     and `transform = 2` for the 180°-rotated 1200x2000 panel).
   - Verifies `/home/alarm/.config/hypr/hyprland.lua` via `Hyprland --verify-config`,
     runs `smoke-check.sh`, strips caches and SSH host keys, and packs the
     filesystem into an 8 GiB ext4 image via `mke2fs -d`.

## Differences from the Samsung Tab S2 (`armv7h`) Build

- **Native `aarch64`**: Uses official Arch Linux ARM `aarch64` packages directly
  on Apple Silicon Docker (`linux/arm64`) without 32-bit cross-repacks.
- **Dropped `pkg/` rebuilds (11 packages)**:
  - `hyprgraphics`: shipped natively in ALARM `aarch64` `[extra]`.
  - `t715-chromium`: ALARM `aarch64` ships native `chromium` in `[extra]`.
  - `t715-modem`, `omatel-agent`, `omaphone`, `omamessages`: SM-T715 Exynos
    Shannon LTE modem and telephony stack (YT-J706F is Wi-Fi-only).
  - `t715-camera`, `libcamera`, `omacam`: SM-T715 camera ISP stack (ALARM
    `aarch64` ships `libcamera`; camera is out of scope).
  - `t715-gps`: SM-T715 Android `gpsd` wrapper.
  - `t715-claude-code`, `pi-coding-agent`: 32-bit Node.js workarounds unnecessary
    on `aarch64`.
- **Hardware & storage adaptations**:
  - Dropped Exynos 5433 `drm_IOCTL_MODE_CREATE_DUMB` `LD_PRELOAD` shim, Samsung
    Wi-Fi/BT NVRAM extraction, and `t715-*` hardware daemons.
  - Added `linux-firmware-mediatek` (`mediatek/mt7663*`) and `input/modules.tar.xz`.
  - Mounted `PARTLABEL=userdata` on `/` (`ext4`) with `lenovomarchy-resize-rootfs.service`.
  - Configured Hyprland for the 1200x2000 panel mounted rotated 180° (`transform = 2`,
    `scale = 1.5`, touch `transform = 0`).

## Commands

```bash
# Build out/rootfs/rootfs-omarchy-aarch64.img and out/rootfs/packages.txt
bash image/build-rootfs.sh

# Verify the generated ext4 image read-only inside Docker (prints PASS)
bash image/verify-rootfs.sh out/rootfs/rootfs-omarchy-aarch64.img
```
