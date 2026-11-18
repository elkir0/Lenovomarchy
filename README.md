# Lenovomarchy

Omarchy (Arch Linux ARM + Hyprland + Quickshell) on the Lenovo Yoga Tab 11,
model **YT-J706F** (MediaTek MT6785 / Helio G90T), replacing Android, on a
mainline-lineage kernel. Developed by AI agents on a Mac, with the tablet on
USB only (no serial console). Sister project of
[omarchy-tab-s2](https://github.com/elkir0/omarchy-tab-s2) (Samsung Galaxy Tab S2).

Beware: **TB-J706F** is a different tablet (Tab P11 Pro, Qualcomm). Nothing
made for it applies here.

## Status

The tablet runs Linux only: kernel 7.1 branch `yt11` from `boot_a`, root
file system on `userdata`, Omarchy 4.5 with the Omarchy Mobile touch shell.
Display, touch, GPU, Wi-Fi, Bluetooth, speakers, microphones, battery, USB,
sensors and auto-rotation, both cameras (with the omacam app) and s2idle
sleep work. Deep sleep and hardware video decoding do not yet.

[ROADMAP.md](ROADMAP.md) has the component-by-component status and the
milestones. Facts read from the unit are in [docs/hardware/](docs/hardware/).

## Layout

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

Mount the source volume after a reboot of the Mac:

```sh
diskutil image attach --mountPoint src .src.sparsebundle
```

## Working on the tablet

- Kernel: `kernel/kbuild.sh`, then `tools/push-modules.sh`, `tools/mkboot.sh`
  and `tools/flash-slot.sh` (sequence in [tools/README.md](tools/README.md)).
- Shell on the tablet: `tools/ytssh '<command>'` (root over the USB network).
- Image: `image/build-rootfs.sh` ([image/README.md](image/README.md)).
- Rules for agents (partitions never written, identifiers never printed,
  `private/`): [CLAUDE.md](CLAUDE.md).

## Kernel base

- [Dinolek/mt6785-mainline](https://github.com/Dinolek/mt6785-mainline),
  branch `7.1` (Redmi Note 8 Pro "begonia"), cloned in `src/mt6785-mainline`;
  this project's work is on its local branch `yt11`.
- Donor patches from
  [F-to-pay/PostmarketOS-begonia](https://github.com/F-to-pay/PostmarketOS-begonia)
  (audio AFE, MT6360 charger), cloned in `src/begonia-ftp`.
- `kernel/configs/pmos-mt6785.config`: postmarketOS/Nura's 6.16.4 config for
  that tree, the starting point; `kernel/configs/yoga11.config` is merged on
  top.
