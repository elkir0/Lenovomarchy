# YT-J706F board wiring, from the stock device tree

Source: the SoC DTB (`dtb.img`) and the board overlay (`dtbo.img`) of the
stock firmware `YT-J706F_S240301_240918_ROW`, decompiled with `dtc`
(2026-11-15), cross-checked with the running unit (`INVENTORY.md`). GPIO
numbers are MT6785 pin numbers (`&pio N`); a pinmux value `0xPPFF` decodes as
pin `0xPP`, function `0xFF`. Vendor bindings differ from mainline: only the
wiring facts below carry over.

## Buses and devices

| Bus (mainline label) | Address | Part | Wiring |
|---|---|---|---|
| `i2c3` | 0x55 | TI bq27541 fuel gauge | `ti,bq27541`, no GPIO |
| `i2c5` | 0x34 (+0x1a, 0x4e, 0x64) | MT6360 PMU / PMIC / TCPC / LDO | as on begonia (`mediatek,mt6360`, IRQ via pinctrl) |
| `i2c5` | 0x11 | KTZ8864A backlight + LCD bias | Kinetic clone of TI LM36274 (begonia uses `ti,lm36274` at 0x11 on `i2c0`) |
| `i2c6` | 0x40, 0x41, 0x42, 0x43 | 4x CS35L41 speaker amps | shared reset GPIO24; IRQs GPIO14 (0x40), GPIO13 (0x41), GPIO4 (0x42), GPIO3 (0x43), pull-up |
| `i2c7` | 0x36 | SGM37604A backlight (second source) | |
| `i2c7` | 0x3e | OCP2138 LCD bias (second source) | |
| `i2c7` | 0x12 | Awinic AW9610x SAR sensor | ignore (RF exposure) |
| `i2c9` | 0x41 | Synaptics AS33970 voice DSP | reset GPIO122, enable GPIO49, IRQ GPIO12 |
| `spi0` | cs 0 | Himax HX83102 touch + pen (`himax,hxcommon`) | 9.6 MHz; IRQ GPIO1, reset GPIO2; SPI pins GPIO17-20 function 1 (CS GPIO19) |
| `mmc0` @ 0x11230000 | — | microSD | 4-bit, 200 MHz, SDR104; card detect GPIO8 active low; `vmmc` = "vmch", `vqmmc` = "vfp" (MT6360 LDOs in vendor naming); CMD/DAT GPIO167-169, 172, 177 f1, CLK GPIO176 f1, GPIO47 f0 (level shifter) |
| `mmc1` @ 0x11240000 | — | MT7663 Wi-Fi/BT (SDIO) | 4-bit, 200 MHz, SDR104, non-removable, `cap-sdio-irq`, keep-power-in-suspend; SDIO IRQ on DAT1 = GPIO139; CMD/DAT GPIO135-139 f1, CLK GPIO134 f1; chip enable GPIO99 (pwrseq, low = off); `vmmc` = "vmch", `vqmmc` = "vmc" |

**Opposite of begonia:** on the Redmi Note 8 Pro, `mmc1` (0x11240000) is the
microSD slot. Here it is the SDIO Wi-Fi, and the microSD is on `mmc0`.

## Panel (Himax HX83102P, BOE 1200x2000)

- DSI0, video mode, 4 lanes (vendor LCM `hx83102p_fhdp_dsi_vdo_boe`).
- Reset GPIO44, tearing effect GPIO43 (function 1).
- LCD bias: ENP GPIO23, ENN GPIO202 (outputs).
- Backlight: KTZ8864A (I2C5 0x11) or SGM37604A (I2C7 0x36), both drivers
  bind on the stock kernel.
- Mounted rotated 180 degrees (vendor config).

## Keys

- Power: MT6359 PMIC power key (vendor `kpd-sw-pwrkey` 116).
- Volume up: MT6359 PMIC "home"/reset key (vendor `kpd-sw-rstkey` 115).
- Volume down: SoC keypad controller at 0x10010000, matrix entry 0 =
  `KEY_VOLUMEDOWN` (vendor `kpd-hw-init-map` starts with 0x72). Mainline has
  `mediatek,mt6779-keypad` for this block; the 7.1 tree's `mt6785.dtsi` has
  no keypad node yet.

## Wi-Fi/BT (MT7663)

- Vendor control node `mediatek,mt7663_wifi_ctrl`, interrupt GPIO149
  (`interrupts = <0x95 ...>`; out-of-band wake, probably).
- Stock `wifi_pwrseq` (`mmc-pwrseq-simple`) is disabled; GPIO99 is the
  enable line in pinctrl state `pins_wifi_enable`.
- Firmware on the unit: `WIFI_RAM_CODE_MT7663.bin`, `mt7663_patch_e2_hdr.bin`,
  `EEPROM_MT7663.bin`, `TxPwrLimit_MT76x3.dat`, `BT_FW.cfg`.

## Audio

- I2S/TDM pins: I2S0 GPIO70, I2S1 GPIO31, 32, 34, I2S2 GPIO33, I2S3 GPIO67,
  68, 71 (all function 1 when on). PMIC audio interface GPIO143-146,
  189-194 (function 1).
- Amps: see `i2c6` above; the unit carries protection and calibration
  firmware `cs35l41-dsp1-spk-prot.wmfw`, `cs35l41-dsp1-spk-cali.wmfw` and
  per-amp `.bin` tunings (`prot1`..`prot4`, `cali1`..`cali4`).
- No headphone jack; the `ACCDET` input exists anyway.

## USB

- USB-C through the MT6360 TCPC (`i2c5` 0x4e); a redriver control GPIO30 and
  a "U3 switch" GPIO32 exist in the overlay (probably unused on this USB 2.0
  board; GPIO32 is also I2S1).

## Sensors

Accelerometer, gyroscope, light and proximity are served by the SCP sensor
hub and appear nowhere in the DT; see `INVENTORY.md`.

## Regulators to map

The vendor names "vmch", "vmc", "vfp" belong to the MT6360 LDOs (MT6359 has
no LDO by those names). Begonia labels MT6360 `ldo3` = `vmc` and `ldo5` =
`vmch`; "vfp" is still to be identified among `ldo1`, `ldo2`, `ldo6`,
`ldo7`.
