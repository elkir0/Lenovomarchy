# Lenovomarchy Root Filesystem Build (`aarch64`)

Docker-based pipeline that builds `out/rootfs/rootfs-omarchy-aarch64.img`, a raw
ext4 root filesystem image running Arch Linux ARM (`aarch64`), Hyprland, and
Omarchy 4.5 with its Quickshell tablet shell for the Lenovo Yoga Tab 11
(`YT-J706F`, MediaTek Helio G90T / MT6785).

## What the Build Does

1. **Base Arch Linux ARM (`aarch64`)**: Downloads `ArchLinuxARM-aarch64-latest.tar.gz`
   and `.md5` into `cache/`, verifies its MD5 digest, and imports it into Docker
   (`lenovomarchy:base-aarch64`).
2. **Omarchy Supply-Chain Verification (`tools/repack-omarchy`)**: Downloads pinned
   packages from `https://pkgs.omarchy.org/stable/aarch64/`, verifies every file's
   SHA-256 digest against `tools/repack.pins` and detached GPG signature against
   `omarchy-keyring` (`tools/omarchy-trusted.fpr`), confirms `omarchy` and
   `omarchy-settings` contain no ELF binaries (`omarchy-speedtest`, which ships
   an aarch64 ELF, gets the `verify-elf` mode instead), and indexes a local
   `[lenovomarchy]` pacman repository.
3. **Omarchy Mobile Supply-Chain Verification (`tools/repack-omamobile`)**: the
   same treatment for `https://pkgs.omamobile.org/stable/aarch64/`: pins in
   `tools/repack.omamobile.pins` cross-checked against the signed repository
   index `omamobile.db`, detached signatures verified against the keyring
   package the repo publishes (whose keys must match
   `tools/omamobile-trusted.fpr`; signatures are made by the release key's
   signing subkey, which the fingerprint list includes). Brings in `omacam`
   (camera app), `omamobile-settings`, `omamobile-remote` and `wlrctl`.
4. **Tablet Touch Layer (`pkg/`, `camera/`)**: `omamobile-omarchy` (idempotent
   patch series over `/usr/share/omarchy`) and `omamobile-shell` (Quickshell
   touch status bar, quick settings, app drawer, task switcher, home screen,
   OSK hide button, and back gesture) are **built from their PKGBUILDs** by
   `image/tools/build-pkg` whenever the archive of the PKGBUILD's current
   version is missing from the local repo (the old `input/prebuilt/` archives
   are gone from the flow). `image/camera/libcamera-yt11` builds the tablet's
   own libcamera (simple pipeline + soft ISP + sensor/AE/AF patches) the same
   way — `build-pkg --src` accepts any PKGBUILD directory — and the image
   installs it in place of Arch Linux ARM's, held with `IgnorePkg`.
5. **Rootfs Assembly (`rootfs/Dockerfile`)**:
   - Removes the stock `linux-aarch64` kernel package and installs Omarchy
     4.5.0-3, `hyprland`, `mesa` (Panfrost for Mali-G76),
     `linux-firmware-mediatek` (`mediatek/mt7663*`), `chromium`, `sddm`,
     `networkmanager`, `openssh`, `dnsmasq`, `squeekboard`, the camera app
     and its GStreamer/PipeWire plumbing, and system utilities. `mako` is
     deliberately absent (Omarchy 4.5's shell is the notification server).
   - Installs kernel modules from `input/modules.tar.xz` into
     `/usr/lib/modules/$(cat input/kernel.release)` and runs `depmod`.
   - Applies `image/overlay/` (`PARTLABEL=userdata` `/etc/fstab`, first-boot
     `lenovomarchy-resize-rootfs.service`, configfs `usb-gadget.service` with
     `ecm.usb0` at `192.168.77.1/24` + `dnsmasq` DHCP serving `192.168.77.2` +
     `acm.GS0`, `serial-getty@ttyGS0.service`, `sshd.service` with key-only login
     from `input/authorized_keys`, and Hyprland monitor config with `scale = 1.5`
     and `transform = 2` for the 180°-rotated 1200x2000 panel).
   - Marks every shipped Omarchy migration done for `alarm` and installs the
     hold list (`omarchy-migrations.hold` →
     `/usr/share/lenovomarchy/omarchy-migrations.hold`, consumed by
     `/usr/local/bin/yt11-omarchy-migrations-hold` after in-place Omarchy
     upgrades).
   - Verifies `/home/alarm/.config/hypr/hyprland.lua` via `Hyprland --verify-config`,
     runs `smoke-check.sh`, strips caches and SSH host keys, sets the
     `IgnorePkg` hold list, and packs the filesystem into an 8 GiB ext4 image
     via `mke2fs -d`.

`input/` (git-ignored, symlinked to the worktree's input directory) holds only
`modules.tar.xz`, `kernel.release` and `authorized_keys`; there is no
`input/prebuilt/` requirement anymore.

## Differences from the Samsung Tab S2 (`armv7h`) Build

- **Native `aarch64`**: Uses official Arch Linux ARM `aarch64` packages directly
  on Apple Silicon Docker (`linux/arm64`) without 32-bit cross-repacks.
- **Dropped `pkg/` rebuilds (11 packages)**:
  - `hyprgraphics`: shipped natively in ALARM `aarch64` `[extra]`.
  - `t715-chromium`: ALARM `aarch64` ships native `chromium` in `[extra]`.
  - `t715-modem`, `omatel-agent`, `omaphone`, `omamessages`: SM-T715 Exynos
    Shannon LTE modem and telephony stack (YT-J706F is Wi-Fi-only).
  - `t715-gps`: SM-T715 Android `gpsd` wrapper.
  - `t715-claude-code`, `pi-coding-agent`: 32-bit Node.js workarounds unnecessary
    on `aarch64`.
- **Camera stack (new)**: `libcamera`/`libcamera-ipa`/`libcamera-tools` are the
  tablet's own build from `image/camera/libcamera-yt11` (ALARM's libcamera has
  none of the MT6785 simple-pipeline, sensor-helper, AE-tuning, lens and
  autofocus patches); `omacam` and its GStreamer/PipeWire dependencies come on
  top. Everything is `IgnorePkg`-held so a plain `pacman -Syu` cannot replace
  the tablet's libcamera with ALARM's.
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

# Rebuild a single package into the local [lenovomarchy] repo
bash image/tools/build-pkg omamobile-shell
bash image/tools/build-pkg --src image/camera/libcamera-yt11 libcamera
```

## Fresh install

For installing from prebuilt release files instead of building from source,
see [docs/INSTALL.md](../docs/INSTALL.md).

Tested on 2026-11-18 on the unit (wiped `userdata`, first boot to the
Omarchy session in about 30 s, root grown to the partition's 110 GiB, slot
marked successful, no failed unit):

```bash
bash kernel/kbuild.sh
cp out/kernel/modules.tar.xz out/kernel/kernel.release input/
bash image/build-rootfs.sh
tools/flash-rootfs.sh out/rootfs/rootfs-omarchy-aarch64.img
tools/flash-slot.sh a <boot.img> <dtbo.img>      # tools/mkboot.sh output
# once the tablet answers on the USB network (192.168.77.1):
tools/touch-firmware.sh <super.img> --install    # no touch without it
tools/amp-firmware.sh <super.img> --install      # speakers' protection DSP
tools/mic-firmware.sh <super.img> --install      # no microphones without it
tools/ytssh systemctl reboot
```

The three firmware sets are Lenovo's and are not redistributable: they come
from the unit's own stock `super` image, so the first boot has no touch,
and the speakers play without their protection DSP, until they are
installed over USB. Wi-Fi is then set up on the tablet. The bring-up probes
(`yt11-dsirate` and the like) are not part of the image.

First settings on the tablet: the account is `alarm`, password `alarm`
(`omamobile-set-pin` changes it and chooses a PIN or a password); the lock
screen comes after 5 minutes idle and asks for it on the full keyboard. The
time zone is UTC (`timedatectl set-timezone <zone>`).

A full build downloads the pinned Omarchy/Omarchy Mobile packages (cached in
`cache/`), compiles `omamobile-omarchy`, `omamobile-shell` and the libcamera
split package inside arm64 Docker containers (libcamera is the slow one), then
assembles the rootfs image. Every step is skipped when its outputs are already
current, so re-running after a `image/pkg/` change rebuilds only what moved.
