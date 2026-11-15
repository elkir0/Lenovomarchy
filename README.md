# Lenovomarchy

Omarchy (Arch Linux ARM + Hyprland + Quickshell) on the Lenovo Yoga Tab 11,
model **YT-J706F** (MediaTek MT6785 / Helio G90T), replacing Android, on a
mainline-lineage kernel. Developed by AI agents on a Mac, with the tablet on
USB only (no serial console). Sister project of
[omarchy-tab-s2](https://github.com/elkir0/omarchy-tab-s2) (Samsung Galaxy Tab S2).

Beware: **TB-J706F** is a different tablet (Tab P11 Pro, Qualcomm). Nothing
made for it applies here.

## Status

Phase 0 (no writes to the tablet): stock unit inventoried, firmware package
analysed, build environment in progress. See
[docs/hardware/INVENTORY.md](docs/hardware/INVENTORY.md) for what the unit
really contains, and [docs/research/](docs/research/) for the feasibility
study (in French) and its source notes.

## Layout

| Path | What |
|---|---|
| `docs/research/` | feasibility study (2026-11-15) and its seven research notes |
| `docs/hardware/` | facts read from the unit and the stock firmware |
| `kernel/` | kernel configs, build scripts, patch series |
| `tools/` | host tools (adb helpers, preloader handshake) |
| `src/` | git-ignored: case-sensitive APFS volume (`.src.sparsebundle`) holding the kernel trees |
| `private/` | git-ignored: stock firmware, unit inventory, backups; never published, never given to fleet workers |

Mount the source volume after a reboot of the Mac:

```bash
diskutil image attach --mountPoint src .src.sparsebundle
```

## Kernel base

- [Dinolek/mt6785-mainline](https://github.com/Dinolek/mt6785-mainline),
  branch `7.1` (Redmi Note 8 Pro "begonia"), cloned in `src/mt6785-mainline`.
- Donor patches from
  [F-to-pay/PostmarketOS-begonia](https://github.com/F-to-pay/PostmarketOS-begonia)
  (audio AFE, MT6360 charger), cloned in `src/begonia-ftp`; unreviewed,
  results self-reported.
- `kernel/configs/pmos-mt6785.config`: postmarketOS/Nura's 6.16.4 config for
  that tree, the starting point.
