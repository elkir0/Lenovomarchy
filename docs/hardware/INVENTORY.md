# YT-J706F hardware inventory, read from a real unit

Read on 2026-11-15 from the project's own tablet over adb (stock, locked,
no root) and from fastboot, then cross-checked against the stock firmware
package `YT-J706F_S240301_240918_ROW` (the build the unit runs). Raw
outputs stay in `private/inventory/` (not in git). This page supersedes the
feasibility study (`docs/research/`) wherever they disagree.

## Unit

| Item | Value |
|---|---|
| Model / product | Lenovo YT-J706F, product `YT-J706F_EEA` |
| Firmware | `YT-J706F_S240301_240918_ROW`, Android 12 (SP1A.210812.016), patch level 2024-10-05 |
| Platform props | `ro.board.platform=mt6785`, `ro.hardware=mt8185` |
| RAM | 4 GB (MemTotal 3.9 GB) |
| CPU | cpu0-5 up to 2.0 GHz, cpu6-7 up to 2.05 GHz (17 OPPs each) |
| Battery | 7500 mAh design, Li-ion |

## Corrections to the feasibility study

1. **Wi-Fi and Bluetooth are a discrete MediaTek MT7663 on SDIO, not the
   SoC's CONSYS block.** `mmc1` (`11240000.msdc`) carries SDIO function 1
   (`wlan`) and function 2 (`btmtk_sdio`); the vendor modules are
   `wlan_drv_gen4_mt7663.ko` and `btmtksdio.ko`; firmware files
   `WIFI_RAM_CODE_MT7663.bin`, `mt7663_patch_e2_hdr.bin`,
   `EEPROM_MT7663.bin`, `TxPwrLimit_MT76x3.dat`. Mainline has drivers for
   this chip on SDIO: `mt76` (`mt7663s`) and `btmtksdio`. The DT overlay has
   `mediatek,mt7663_wifi_ctrl` and `mediatek,mt8185-sdio`. The CONSYS
   patches of the begonia series (0016, 0017, 0019, 0021) do not apply here.
2. **The fuel gauge is a TI bq27541** (I2C 3-0055, bound to
   `bq27xxx-battery`; power supplies `ac battery bq27541 charger usb`).
   Mainline `bq27xxx_battery_i2c` covers it. The MT6359 gauge patch (0001)
   is not needed.
3. **This unit is the Himax variant**: touch `himax_tp` on SPI `spi0.0`,
   input devices `himax-touchscreen` (1200x2000) and `himax-pen`. The panel
   is therefore the BOE HX83102P (`hx,hx83102p` in the overlay). The
   Novatek NT36523W variant also exists in the same firmware.
4. **The pen goes through the Himax touch chip**: `himax-pen` reports
   `BTN_TOOL_RUBBER`, `BTN_STYLUS`, `BTN_STYLUS2`, `ABS_PRESSURE` 0-4095,
   `ABS_TILT_X/Y` -60..60. No Bluetooth needed for pen input.
5. **Motion and light sensors are not in the device tree at all.**
   Accelerometer, gyroscope, light and proximity are "MTK" sensors served by
   the SCP sensor hub; neither the DT nor the overlay describes them. The
   unbound I2C clients (`9-006b`, `9-0060`, `7-0020`, `7-0028`, `3-0008`,
   `0-0061`, `6-0073`, `2-0060`) are generic platform placeholders
   (`vproc_buck`, `nfc`, `i2c_lcd_bias`, alternative SAR chips,
   `hid-over-i2c` keyboard/mouse), not sensors.
6. **Boot image**: header v2, page 2048, kernel at 0x40080000, ramdisk at
   0x47c80000, cmdline `bootopt=64S3,32N2,64N2 buildvariant=user`; the DTB
   is inside `boot.img`. `vendor_boot_a/b` partitions exist (64 MiB) but the
   firmware package ships no image for them.

## I2C and SPI devices bound by the stock kernel

| Bus-addr | Driver | Part |
|---|---|---|
| 3-0055 | `bq27xxx-battery` | TI bq27541 fuel gauge |
| 5-0011 | `ktz8864a` | backlight |
| 5-001a, 5-0034, 5-004e, 5-0064 | `mt6360_pmic`, `mt6360_pmu`, `usb_type_c`, `mt6360_ldo` | MT6360 |
| 6-0040..6-0043 | `cs35l41` | 4x Cirrus Logic CS35L41 |
| 7-0012 | `aw9610x_sar` | Awinic SAR sensor |
| 7-0036 | `sgm37604a` | backlight (second source, also bound) |
| 7-003e | `ocp2138` | LCD bias |
| 9-0041 | `as33970` | Synaptics AS33970 voice DSP |
| 2-*, 4-*, 7-0043 | camera drivers | rear/front cameras, AF, EEPROM |
| spi0.0 | `himax_tp` | Himax HX83102 touch + pen |
| mmc1:0001:1/2 | `wlan`, `btmtk_sdio` | MT7663 Wi-Fi/BT |

Both backlight drivers bind; which chip is fitted needs `dmesg` (root) or a
register read from Linux.

## Input devices

`aw9610x_sar`, `mtk-tpd`, `himax-touchscreen`, `ACCDET`, `himax-pen`,
`mtk-kpd`.

## Partitions and fastboot

A/B (`current-slot: b`, `slot-retry-count` 1 on each slot), `super` 6 GiB
(dynamic), `userdata` ~111 GiB, `boot_a/b` 32 MiB, `vendor_boot_a/b` 64 MiB,
`dtbo_a/b` 8 MiB, `vbmeta*_a/b`, `expdb` 20 MiB, `misc` 512 KiB. Unit data
never to overwrite: `nvram`, `nvdata`, `nvcfg`, `proinfo`, `protect1/2`,
`persist`, `seccfg`, `otp`, `lenovoraw`, `lenovocust`. Never written by this
project: `preloader*`, `lk_*`, `tee_*`, `gz_*`, `scp_*`, `sspm_*`,
`spmfw_*`, `super`.

`fastboot getvar all` (LK, not fastbootd): product `yoga11`,
`version-bootloader yoga11-4ac899a7-20221010101625-20240918`,
`secure: yes`, `unlocked: no`, `max-download-size` 128 MiB,
`off-mode-charge: 1`, `fastboot-hotkey: 1`, `recovery-hotkey: 1`.
`fastboot flashing get_unlock_ability` = 0 while "OEM unlocking" is off
(`sys.oem_unlock_allowed=0`). `fastboot oem help`: unknown command.

`adb reboot bootloader` reaches fastboot in 8 s; `fastboot reboot` gives
`bootreason PMIC_cold_reboot` and Android is up 119 s later.

## Preloader USB window (keyless fastboot): works

Tested 2026-11-15 with `tools/mtk-preloader/preloader_fastboot.py --once`
while the tablet rebooted from Android (`adb reboot`, locked bootloader):
the preloader's CDC-ACM node `/dev/cu.usbmodem101` appeared 9 s after the
reboot command, `READY` was already waiting when the port opened, the tool
sent `FASTBOOT`, the preloader answered `TOOBTSAF` 20 ms later, and LK's
fastboot was on USB 3 s after that. Lenovo did not disable the handshake:
the Mac can force fastboot at any boot without keys, including after a
watchdog reset.

## Bootloader unlock: done (2026-11-15)

- "OEM unlocking" on in Android, then `fastboot flashing get_unlock_ability`
  answered `16777216` (0x01000000, non-zero = allowed).
- `fastboot flashing unlock`: LK printed "Start unlock flow", the owner
  confirmed with Volume Up, `OKAY` after 16 s; `getvar unlocked` = yes.
  User data was wiped; `nvram`/`nvdata`/`proinfo` are not touched by the
  unlock.
- Next boot: the orange-state warning passes **by itself** after a few
  seconds (no key press), Android's setup wizard was on USB 138 s after
  `fastboot reboot` (first boot after the wipe).

## `fastboot boot` (RAM boot): not usable

Tested 2026-11-15 on the unlocked unit with three images built from the
package's `boot-debug.img` (unchanged; cmdline marker; kernel banner changed
to `4.14.186-yt11ramboot01`): LK accepts the download (`OKAY`), drops USB at
"Booting", and the tablet comes back on the stock kernel from flash
(`/proc/version` unchanged) with `ro.boot.bootreason=lk_crash`. Lenovo's LK
crashes on RAM boot, then its watchdog reboots normally. Test kernels must
be flashed to a `boot_*` slot instead; an LK crash recovers by itself.

## Root through the stock debug boot image

Flashing the package's own `boot-debug.img` (same build) to the active slot
gives `ro.force.debuggable=1` and `adb root` on the unlocked unit (SELinux
stays enforcing); the stock `boot.img` goes back afterwards. Facts read as
root on 2026-11-15:

- **Bootloader framebuffer** (`/chosen/atag,videolfb-*` and `fb0`): base
  `0x7e605000`, 1200x2000 visible, **stride 4864 bytes** (1216 px), 32 bpp,
  three buffers (virtual 1216x6048), 60.00 fps, LCM
  `hx83102p_fhdp_dsi_vdo_boe_drv`, `islcmfound` 1. LK reserves
  `0x7cf50000` + `0x20b0000` for it (`mblock-16-framebuffer`).
- **pstore**: LK adds reserved-memory nodes `mblock-*` at boot, among them
  `mblock-14-pstore` = `0x4d010000` + `0xe0000` (`mediatek,pstore`) and
  `mblock-13-aee_debug_kinfo` = `0x4d000000` + `0x10000`; Android shows
  `console-ramoops` (248 KB) and `pmsg-ramoops-0`.
- **Touch IC**: the vendor driver reads chip ID `83 10 2E` and logs
  `[Vendor]himax [IC]hx83102e`: the touch side identifies as HX83102E,
  the panel driver is `hx83102p`.
- **Backlight**: brightness goes through DSI commands
  (`[DISP][BL]_set_backlight_by_cmdq`) and the display PWM
  (`disp_pwm_backlight_status ... pwm id: (0)`). No I2C errors from
  `5-0011` (KTZ8864A), `7-0036` (SGM37604A) or `7-003e` (OCP2138); the only
  I2C ACK errors come from the absent SAR alternatives `7-0020` and
  `7-0028`. Which backlight chip is fitted stays open.
- Full `dmesg` (without the command line) in `private/inventory/`.

## Still unknown

- Which backlight chip is fitted (both I2C drivers bind silently).
- Wi-Fi 1x1 or 2x2.
- The simple-framebuffer pixel order (a8r8g8b8 or a8b8g8r8): test at the
  first Linux boot.
