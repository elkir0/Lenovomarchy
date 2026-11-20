# Lenovomarchy

Omarchy (Arch Linux ARM + Hyprland + Quickshell) on the Lenovo Yoga Tab 11,
model **YT-J706F** (MediaTek MT6785 / Helio G90T), replacing Android, on a
mainline-lineage kernel. Developed by AI agents on a Mac, with the tablet on
USB only (no serial console). Sister project of
[omarchy-tab-s2](https://github.com/elkir0/omarchy-tab-s2) (Samsung Galaxy
Tab S2).

Beware: **TB-J706F** is a different tablet (Tab P11 Pro, Qualcomm). Nothing
made for it applies here.

## What works

Condensed from [ROADMAP.md](ROADMAP.md) (see that file for full details):

| Block | State | Notes |
|---|---|---|
| Boot (`boot_a`, root on `userdata`) | works | Keyless fastboot via preloader; `fastboot boot` unusable |
| Display and backlight | works | 1200x2000 at 60.07 Hz; KTZ8864A linear mapping |
| Touch (Himax HX83102P) | works | Needs non-redistributable firmware from stock `super` |
| GPU (Mali-G76, Panfrost) | works | Mesa Panfrost |
| Wi-Fi and Bluetooth (MT7663 SDIO) | works | 2.4 GHz Wi-Fi and BT scan tested; 5 GHz and pairing untested |
| Speakers (4x CS35L41) | works | Stereo with protection DSP (needs firmware from stock `super`) |
| Microphones (AS33970) | partial | Ready ~31 s after power-on (needs firmware from `super`); voice mode untested |
| Cameras (OV8856, S5K4H7) | partial | `omacam` + libcamera; AF ~18 s at start; no lens shading correction |
| Sensors, battery, charging, USB-C | works | Auto-rotation, 2 A charge guard, gadget network; light sensor untested in daylight |
| Vibrator | partial | Driver switches the LDO on; buzz not yet felt by a person |
| Pen, microSD | untested | Present in DT/driver, not exercised on the unit |
| Suspend (`s2idle`) | partial | Wi-Fi back on resume; ~135 mA asleep (~48 h standby) |
| Deep sleep, CPU idle, CPU hotplug | missing | Taking a core offline or `deep` suspend freezes the tablet |
| Hardware video decode/encode | missing | No open driver/firmware; video stays decoded on CPU |
| Proximity, keyboard accessory | missing | Not ported |

## Install

Download `boot.img`, `dtbo.img`, and `rootfs-omarchy-aarch64.img.xz` from the
[latest release](https://github.com/elkir0/Lenovomarchy/releases/latest),
then follow [docs/INSTALL.md](docs/INSTALL.md) to unlock the bootloader, run
`tools/install.sh`, and extract the three non-redistributable Lenovo firmware
sets from your own `super` image.

## Build from source

See [docs/BUILD.md](docs/BUILD.md) for the full source build and flashing
sequence. On macOS, the kernel tree must reside on a case-sensitive APFS
volume (`src/`), attached after each reboot with:

```bash
diskutil image attach --mountPoint src .src.sparsebundle
```

Day-to-day kernel and image commands:

- Kernel: `kernel/kbuild.sh`, then `tools/push-modules.sh`, `tools/mkboot.sh`
  and `tools/flash-slot.sh` (sequence in [tools/README.md](tools/README.md)).
- Shell on the tablet: `tools/ytssh '<command>'` (root over the USB network).
- Image: `image/build-rootfs.sh` ([image/README.md](image/README.md)).

## Documentation

- [docs/INSTALL.md](docs/INSTALL.md) — install from a release on a YT-J706F
- [docs/BUILD.md](docs/BUILD.md) — build kernel, initramfs, and rootfs from source
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) — recovery, firmware, and known hazards
- [ROADMAP.md](ROADMAP.md) — hardware/software status and milestones
- [CLAUDE.md](CLAUDE.md) — rules for agents (partitions never written, identifier redaction, `private/`)
- [docs/hardware/](docs/hardware/) — facts read from the unit: board wiring, display, cameras, inventory
- [docs/design/](docs/design/) — driver designs (touch and pen)
- [docs/research/](docs/research/) — feasibility study (French), camera bring-up notes, Omarchy / Omarchy Mobile upgrade notes
- [kernel/README.md](kernel/README.md), [initramfs/README.md](initramfs/README.md), [image/README.md](image/README.md), [tools/README.md](tools/README.md), [tools/mtk-preloader/README.md](tools/mtk-preloader/README.md) — component references

## Repository layout

| Path | What |
|---|---|
| `ROADMAP.md` | status of every component, milestones |
| `docs/hardware/` | facts read from the unit: board wiring, display, cameras, inventory |
| `docs/design/` | driver designs (touch and pen) |
| `docs/research/` | feasibility study (French), camera bring-up notes, Omarchy / Omarchy Mobile upgrade notes |
| `kernel/` | kernel build in Docker, config fragment (`configs/yoga11.config`) |
| `image/` | root file system image build: Omarchy, tablet packages, overlay, smoke check ([image/README.md](image/README.md)) |
| `initramfs/` | bring-up initramfs: USB network, boot-slot control, switch to the root on `userdata` |
| `tools/` | host tools: flashing, boot images, module push, SSH, bring-up probes ([tools/README.md](tools/README.md)) |
| `tests/` | offline tests (boot-control tool, `tools/linux-test.sh`) |
| `src/` | git-ignored: case-sensitive APFS volume (`.src.sparsebundle`) holding the kernel trees |
| `private/` | git-ignored: stock firmware, unit inventory, backups; never published, never given to fleet workers |
| `out/`, `cache/` | git-ignored: build outputs and download cache |

## Kernel base

- [Dinolek/mt6785-mainline](https://github.com/Dinolek/mt6785-mainline),
  branch `7.1` (Redmi Note 8 Pro "begonia"), cloned in `src/mt6785-mainline`;
  this project's work is on the branch `yt11`, published in
  [elkir0/mt6785-mainline](https://github.com/elkir0/mt6785-mainline/tree/yt11).
- Donor patches from
  [F-to-pay/PostmarketOS-begonia](https://github.com/F-to-pay/PostmarketOS-begonia)
  (audio AFE, MT6360 charger), cloned in `src/begonia-ftp`.
- `kernel/configs/pmos-mt6785.config`: postmarketOS/Nura's 6.16.4 config for
  that tree, the starting point; `kernel/configs/yoga11.config` is merged on
  top.

## How it was made

Developed by AI agents on a Mac with the tablet connected over USB only (no
serial console). Agent rules for target isolation, identifier redaction,
forbidden partitions, and `private/` handling live in
[CLAUDE.md](CLAUDE.md).

## Licence

This repository's own files are licensed under the MIT License; see
[LICENSE](LICENSE). Patches keep the licence of what they modify, the Linux
kernel tree is GPL-2.0 in its own repository, and Lenovo's proprietary
firmware is not included.
