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
| `i2c3` | 0x55 | TI bq27541 fuel gauge | `ti,bq27541`, no GPIO; bus at 100 kHz (see below) |
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
- Volume down: SoC keypad controller at 0x10010000 (GIC SPI 75), matrix
  entry 0 = `KEY_VOLUMEDOWN` (vendor `kpd-hw-init-map` starts with 0x72),
  single-key mode, row 0 / column 0 on KPROW0 (GPIO58) and KPCOL0 (GPIO59),
  function 1, already muxed by LK. Kernel `yt11` adds the keypad node
  (`mediatek,mt6779-keypad`). Tested 2026-11-16 with the owner pressing: Vol+
  reports `KEY_VOLUMEUP` on `mtk-pmic-keys`, Vol- reports `KEY_VOLUMEDOWN` on
  `mt6779-keypad`, nothing crosses over.
- No cover sensor: the stock DT has no hall node and stock Android exposed
  no lid input. The DWS name `GPIO_HALL_1_PIN` on GPIO118 comes from the
  reference design. The keyboard/touchpad accessory nodes (I2C-HID MCU at
  0x60/0x61, `mcu_hall_int_gpio` GPIO196) belong to an optional keyboard
  accessory; not ported, not tested.

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
- No headphone jack (confirmed by the owner, 2026-11-16), although the stock
  DT enables `ACCDET` with headset thresholds (reference design). Mainline
  keeps the accdet node disabled and the sound card has no jack; the
  PipeWire profile has a single speaker port.

## Fuel gauge (bq27541, 2026-11-16)

- The stock i2c3 node sets no `clock-frequency`, so the vendor I2C driver
  runs it at its default 100 kHz. At 400 kHz the first data byte of each
  read is right but the second often comes back as 0xff: capacity 65380 %,
  6278 degrees C, cycle count 65353, health "Overheat", a current of exactly
  -256 mA (0xff00). At 100 kHz, 200 raw reads and 60 s of sysfs samples
  are clean.
- Measured on the unit: 4.33 V, 31.7 degrees C, full charge 6638 mAh of
  7500 mAh design (UPower: 88.5 % capacity), 73 cycles.
- On battery (USB unplugged, desktop idle, followed over Wi-Fi): about
  -400 mA at 4.29 V, the charge counter falling 7 mAh per minute to match,
  UPower 1.76 W and 16 h to empty.
- The gauge keeps its full-charge flag set for a while after unplugging,
  and mainline `bq27xxx` let that flag win over the current sign: the
  battery reported "Full" while discharging, and the desktop bar kept its
  charging icon. Kernel `yt11` 85098c2c8 reports discharging whenever the
  current is negative; tested: plugged in at 100 % -> Full, unplugged ->
  Discharging at once, and the owner saw the icon change.

## SoC thermal (LVTS, 2026-11-16)

- The stock kernel uses the LVTS controller at 0x1100b000 (GIC SPI 100),
  not the older AUXADC sensors: four controllers at offsets 0x0-0x300
  holding eight sensors, big CPU x2, little CPU x3, GPU x2, VPU x1.
  Calibration comes from the efuse at 0x11c10000: golden temperature in
  the low byte of 0x1b0, a 24-bit `count_r` per sensor at 0x1c8, 0x1cc and
  0x93c-0x950 (`count_rc` is unused, the vendor runs auto RCK). Conversion:
  -204.65 * raw / 16384 + golden / 2 + 204.65 degrees C. Vendor critical
  temperature: 117 degrees C (`tzcpu_initcfg.h`).
- Kernel `yt11` bcba65572..f9a602693 completes the tree's partial MT6785
  LVTS data and adds the efuse, the LVTS node and one zone per sensor:
  passive trip 85 degrees C (big CPU, little CPU and GPU throttle on their
  own sensors), critical trip 117 degrees C.
- Measured on the unit: 42-45 degrees C at idle on every sensor. An
  all-core load takes the big cores to 84-87 degrees C within 15 s; the
  throttle then holds them at 82-93 degrees C at 1.53-1.86 GHz instead of
  2.05 GHz. With `emul_temp` at 92 degrees C the caps are 1.796 GHz (big),
  1.733 GHz (little) and 884 MHz (GPU), released once the real
  temperature returns.

## USB

- USB-C through the MT6360 TCPC (`i2c5` 0x4e); a redriver control GPIO30 and
  a "U3 switch" GPIO32 exist in the overlay (probably unused on this USB 2.0
  board; GPIO32 is also I2S1).

## Sensors

Accelerometer, gyroscope, light and proximity are served by the SCP sensor
hub and appear nowhere in the DT; see `INVENTORY.md`. Found on the unit
(2026-11-16), all reachable from the AP without the SCP:

- The SCP firmware (`scp.img`) auto-detects an accel/gyro among
  `lsm6dsm`, `icm4n607` and `bmi2xy` (on SPI: "acc spi_num") and a
  light/proximity sensor among `ltr578`, `tmd2755`, `tmf8801`.
- Light/proximity: GPIO61/62 (`GPIO_SENSOR0_I2C`) are SCP_SCL0/SDA0 but
  also the AP's SCL1/SDA1, already muxed so by the boot loader. On i2c1:
  Lite-On LTR-578ALS at 0x53 (part ID 0xb1 at register 0x06) and an
  unidentified device at 0x29. No mainline driver for the LTR-578 yet.
- Accelerometer + gyroscope: Bosch BMI220 (chip id 0x26) on GPIO63-66,
  which are SCP_SPI2 and also the AP's SPI2 (MI, CSB, MO, CLK; found by
  bit-banging the pins). Kernel `yt11` adds the BMI220 to the `bmi270`
  driver and the board's spi2 node. Like the BMI260/270 it needs an
  8 KiB initialization blob at probe, `bmi220-init-data.fw`: Bosch does not
  publish it, and the only copy is inside the SCP firmware (signature
  `c8 2e 00 2e`, 8192 bytes, ending with `80 2e 00 c1`). It never goes into
  the repository: `yt11-sensor-firmware.service` extracts it on the unit
  from its own `scp_a` partition (else `scp_b`, read only) while
  `/usr/lib/firmware/bmi220-init-data.fw` is missing, then reloads the
  driver. Tested by deleting the file and rebooting: same blob back, IMU
  and auto-rotation up in the same boot.
- Axes (measured with the owner): the chip's +x points to the top of the
  upright portrait image, +y to the image's left edge. The udev rule
  `61-yt11-sensors.rules` gives iio-sensor-proxy the mount matrix
  `0, 1, 0; -1, 0, 0; 0, 0, 1`.
- Auto-rotation: `yt11-autorotate`, started by Hyprland (`tablet.lua`),
  follows `monitor-sensor` and sets the output transform (upright = 2, the
  panel is mounted upside down) and the touch/pen transform (upright = 0),
  both one step per quarter turn. Tested with the owner in all four
  positions, image and touch right. It must run inside the graphical
  session: polkit refuses the sensor claim to a process started over SSH.

## MT6360 (i2c5 0x34): same wiring as the reference design (begonia)

From the stock SoC DTB (`mt6360_pmu_dts`, `mt6360_ldo_dts`,
`type_c_port0`): PMU interrupt GPIO16, Type-C/PD interrupt GPIO7, LDO
names `ldo1` = vfp, `ldo2` = vtp, `ldo3` = vmc, `ldo5` = vmch. The begonia
DTS's MT6360 node (same pins, same LDO names) applies as is. `vtp` (ldo2) is
the panel/touch logic supply the vendor LCM driver calls "vddi 1.8V".

## Backlight and LCD bias: one LM36274-class chip at i2c5 0x11

The vendor panel driver (`hx83102p_fhdp_dsi_vdo_boe.c`) only programs the
chip at i2c5 0x11 (`ktz8864a_*`): it reads a vendor ID from register 0x01
(`& 0x03`, 0x2 = KTZ8864A) and then writes LM36274 registers (0x09 bias
enable, 0x0d/0x0e VPOS/VNEG = 5.8 V, 0x02 OVP 29 V + exponential + PWM,
0x08 backlight enable, 0x04/0x05 current), plus three extra registers
(0xf0, 0xb1, 0x10) for the other vendor. Sequence: vddi (vtp) on, 3 ms,
`GPIO_LCD_BL_EN` high, configure, bias enable, ENP high, 3 ms, ENN high,
3 ms; then reset 1-0-1 (2/18/8 ms) and the DCS init. Mainline: TI LMU
`ti,lm36274` (backlight + lm363x regulators). LK logged
"KTZ8864A_read_byte: i2c_read failed" once, so the vendor of this unit's
chip is still to be read from Linux (register 0x01). The SGM37604A
(i2c7 0x36) and OCP2138 (i2c7 0x3e) drivers bind on the stock kernel but are
not used by this panel's driver.

## GPIO table of the vendor project (`tb8185p3_64.dws`)

The DWS file of the GPL tree (`drivers/misc/mediatek/dws/mt6785/tb8185p3_64.dws`,
decoded list in `private/inventory/dws-gpio-names.txt`) is the platform
project's pin map, not always this board's: where it disagrees with the
board overlay, the overlay wins. Useful entries: GPIO1/2 touch EINT/reset,
GPIO7 Type-C IRQ, GPIO8 SD card detect, GPIO16 MT6360 IRQ, GPIO17-20 SPI0
(touch), GPIO28/29 I2C5, GPIO42 `GPIO_PWM_BL_PIN`, GPIO43 DSI TE, GPIO44
LCM reset, GPIO45/46 I2C6, GPIO55/56 I2C3, GPIO59/60 keypad columns
`KCOL0`/`KCOL1` (begonia's volume buttons are gpio-keys on 59/60),
GPIO67/68/70/71 smart-amp I2S (LRCK, DOUT, DIN, BCK), GPIO69 smart-amp
EINT, **GPIO73 `GPIO_LCD_BL_EN`**, GPIO118 hall sensor, GPIO134-139 MSDC1
(SDIO), GPIO153 smart-amp reset, GPIO189-194 PMIC audio interface,
GPIO198/199 I2C7, GPIO202 LCD bias ENN. Disagreements to settle on the
unit: LCD bias ENP is GPIO23 in the overlay, GPIO72 in the DWS; amp reset
is GPIO24 in the overlay, GPIO153 in the DWS.

## MT7663 on SDIO: working (2026-11-15)

**The module's supply is switched by GPIO158.** The stock kernel drives
it high; Linux left it an input, so the chip was unpowered and never
answered on SDIO (CMD52/CMD5 timeouts, its interrupt line GPIO149 read 0).
Found by listing the pins that stock Android drives as high outputs
(`private/inventory/wifi-oracle/on.txt`) and raising them one by one:
with GPIO158 high, GPIO149 goes high and the card enumerates at SDR104.
The board DT now has a fixed regulator on GPIO158 as the slot's `vmmc`
and an `mmc-pwrseq-simple` for the PMU enable GPIO99 (active low),
kernel tree `yt11` commit `86667a9cb`.

- Both SDIO functions enumerate: function 1 Wi-Fi (`mt7663s`, firmware
  `mediatek/mt7663pr2h.bin` + `mt7663_n9_v3.bin` from linux-firmware, N9
  3.1.1), function 2 Bluetooth (`btmtksdio`).
- Both functions download the same ROM patch. Racing, Wi-Fi fails with
  "Failed to get patch semaphore"; Wi-Fi first makes Bluetooth setup fail
  (WMT command 0xfc7a times out). Bluetooth first, then Wi-Fi, works:
  the image blacklists `mt7663s` and `yt11-wifi-after-bt.service` loads it
  once the Bluetooth controller is set up (15 s fallback).
- Measured: 2.4 GHz link at -30 dBm, 270-300 Mbit/s (MCS15, 40 MHz,
  short GI), 8.7 MB/s (70 Mbit/s) on a 50 MB download; Bluetooth scan
  finds nearby devices.
- The efuse holds no MAC address: NetworkManager uses a stable per-network
  address (`wifi.cloned-mac-address=stable`).
- The image used to mask `wpa_supplicant.service`, which NetworkManager
  needs for Wi-Fi; only iwd stays masked.

Ruled out on the way (all equal to stock): supplies (vcn18, vio18, MT6360
vmc 1.8 V, vmch 3.5 V; also vemc, vbif28, va09, vrf18, which turned out
unneeded), MSDC1 pin mux (`GPIO_MISC` bit 9), pad TDSEL/RDSEL, host
registers at CMD time (identical to the stock driver's dump), MT6359
DCXO buffers, the RTC 32 kHz output (`RTC_CON` F32KOB clear).

## Audio wiring (stock DT, 2026-11-15)

- Speakers: four CS35L41 (Rev B2) on i2c6 (400 kHz, GPIO45/46) at
  0x40-0x43, one shared reset GPIO24 (active low), interrupts GPIO14, 13,
  4, 3 (level low), boost 4500 mA / 1000 nH / 15 uF, `asp-sdout-hiz` 3,
  GPIO2 output source 4.
- Their audio bus is the SoC's **I2S1 output** (GPIO31 BCK, GPIO32 LRCK,
  GPIO34 DO, function 1), with feedback on the **I2S2 input** (GPIO33,
  function 1): the stock sound node says `mtk_spk_i2s_out = <1>` and
  `mtk_spk_i2s_in = <2>`. The `GPIO_SMARTPA_*` names the DWS table gives
  GPIO67-71 (I2S3/I2S0) come from the MediaTek reference design and are
  wrong for this board (same as its name for GPIO24). On I2S3 the SoC pads
  toggle but the amps never see a clock: their PLL does not lock and the
  power-up times out (`Enable(1) failed: -110`).
- The stock machine driver runs one I2S link to all four at 48 kHz with a
  3.072 MHz bit clock as the amps' PLL reference, SPK1/SPK2 left,
  SPK3/SPK4 right, name prefixes SPK1-SPK4. Mainline does the same with
  `mediatek,speaker-i2s = "I2S1"` (kernel `yt11`): measured PLL lock and
  PUP_DONE on all four amps, muted, digital silence only.
- First audible test (2026-11-16, owner listening): clear speech from the
  speakers, left and right on the right sides (landscape, camera on top),
  through PipeWire at 50 % with the amps at 0 dB digital and 10.5 dB
  analog. Two faults came first. They were found by playing constant
  S32_LE patterns with the amps muted while sampling LRCK (GPIO32) and DO
  (GPIO34) together:
  - The mt6785 AFE driver declared a 32-bit memif mode (as mt8192 does).
    With `HD_MODE` 2 the MT6785 DL1 memif reads 16-bit samples, so every
    32-bit sample left as two half-words over two frames: crackle, no
    voice. S32_LE now uses the 24-bit mode, MSB aligned (`AFE_DL1_CON0`
    `HD_MODE` 1, `HALIGN` 1).
  - The speaker link forced S32_LE on the amps, which take 16 or 24-bit
    words: mainline wrote a 32-bit word length into `SP_RX_WL` (0x4840),
    and once the data was right the amps played silence. The link now runs
    S24_LE (32-bit slots on the wire, 24-bit words). A 24-bit or 32-bit
    `SP_FORMAT` RX width both play correctly.
  - Android keeps I2S1 and I2S2 in low-jitter mode (`I2S1_HD_Mux` and
    `I2S2_HD_Mux` stay `Low_Jitter` even in its "HD_OFF" paths);
    `yt11-audio-defaults` does the same. Whether the amps need it was not
    tested.
- At boot the AFE logs `-EBUSY` on register 0x52c
  (`I2S1_TINYCONN_CH1_MUX DAPM update failed`) while it is runtime
  suspended. Playback is not affected; not investigated yet.
- Amp DSP firmware (Cirrus "prince" protection): `cs35l41-dsp1-spk-prot.wmfw`
  with per-amp tunings `cs35l41-dsp1-spk-prot1..4.bin`, plus calibration
  variants, in the vendor partition's `/firmware` (not redistributable).
  Mainline runs the amps without it (DSP bypass, no speaker protection).
- Microphones: Synaptics AS33970 ("Tahiti") voice processor at 0x41 on
  i2c9 (GPIO151 SDA9 / GPIO152 SCL9, function 1; "I2C_APPM" in the GPIO
  table), enable GPIO49, reset GPIO122 (active low), interrupt GPIO12. The
  vendor machine driver makes it the codec of the I2S2 capture link
  (`as33970-aif`); I2S2 only has its DI pin (GPIO33) and shares I2S1's bit
  and frame clocks, and the yoga11 defconfig (`CONFIG_TARGET_PROJECT_P530`)
  gives that link no MCLK.
- The AS33970 has no firmware of its own: after reset its ROM boot loader
  answers `0x43` ('C') at sub-address 0 and waits. Android's
  `/vendor/bin/tahiti_i2c_load` pushes `/vendor/etc/tahiti_dsp/partition_boot2flash.img`
  (firmware 4.15.13.0: an 8 KiB second-stage loader at 0x100, then 158
  blocks of 4 KiB at 0x10000) at every boot. `tools/audio/tahiti_load.py`
  reimplements that protocol (16-bit big-endian sub-addresses, 32-bit
  little-endian words). Measured on the unit (2026-11-16): the ROM accepts
  the second-stage loader (`S`, `S`, then `O` after `D`), but that loader
  (`iflash_boot2`) never posts its ready word `0x80` and does not answer
  messages, with or without I2S1 clocks running and with vbif28, va09 and
  vemc forced on. Something it needs at start-up (a clock, a supply or a
  pin the stock kernel sets) is still missing. The microphones do not work
  yet.
- Second-stage findings (2026-11-16, from the image and the unit): the
  8 KiB loader is a Cortex-M image in two segments, each behind a 0x18-byte
  header (load address, length): 0xff0 bytes at 0x30019000 (vector table,
  reset handler) and 0x710 bytes at 0x30019ff0. Its init points the I2C
  slave window (registers at 0x42001400) at a RAM mailbox at 0x3001a69c and
  writes 0x80 there; its loop waits for bit 7 of word 0 to clear, checks
  the sequence byte and the hash in word 1, dispatches commands 8 (write a
  4 KiB block) to 16 (14 sets the state that leaves the loop and jumps to
  the firmware's vector table), others answer trivially, then sets bit 7.
- On mainline the host sees that mailbox 4 bytes higher than the vendor
  loader assumes: with every message moved to sub-address +4, ping and
  status messages and all 158 block writes are acknowledged (4.7 s), but
  the device only ever updates the done bit (reply words 1 and 2 keep what
  the host wrote) and command 14 does not leave the loop: the firmware never
  starts. The offset and the frozen reply words point at a different window
  set-up than the stock kernel's, or at the ROM answering instead of the
  loader; untangling it needs more disassembly of the loader's I2C path.

## Suspend (s2idle, 2026-11-16)

- `mem_sleep` offers `s2idle` and `deep`, and the kernel defaulted to
  `deep`. A `deep` cycle (`rtcwake -m mem`) never came back: no RTC wake,
  no power-key wake, a forced restart was needed, nothing in pstore (the
  vendor kernel loads SPM firmware that mainline does not have). The
  project now defaults to s2idle twice over: `mem_sleep_default=s2idle`
  in `tools/mkboot.sh` and `MemorySleepMode=s2idle` in
  `/etc/systemd/sleep.conf.d/10-yt11-s2idle.conf`.
- Wi-Fi (MT7663 SDIO): without WoWLAN, suspend disconnects and cfg80211
  restores the regulatory domain while the chip is already asleep;
  `mt7615_regd_notifier` then waited 20 s for each firmware reply (40 s
  to enter suspend). Kernel `yt11` 6d52a72ac skips those firmware updates
  while suspended (`pm.suspended`, as mt7921 does; `mt7615_start()`
  reprograms them on resume) and ea3b186dc unparks the tx status worker on
  resume (its double park gave the `kthread_park` WARN). An s2idle cycle
  with a 20 s alarm now takes 21 s, twice in a row, Wi-Fi back each time.
- USB: `mtu3` refuses suspend (`-EBUSY`) while `mtu->connected`, i.e. while
  a host uses the gadget. That is intended, but the PHY never reported the
  cable being pulled, so the flag stayed set forever and suspend never
  worked. Kernel `yt11` de556a1dd wires the MT6360 TCPC connector to the
  mtu3 role switch (otg, peripheral by default for the USB network at
  boot, xHCI enabled for the host role) and a5610bec2 makes a "none" role
  stop the device and a new attach start it. Unplugged, the UDC goes to
  "not attached"; plugged back into a host, it enumerates again.
- Omarchy's mobile setup turns the menu's Suspend entry off
  (`suspend-off` toggle); `install-mobile.sh` removes that toggle. The
  power key opens Omarchy's system menu (logind ignores it), and the PMIC
  power key is a wakeup source.
- Tested with the owner (2026-11-16): cable out, power -> Suspend, 138 s in
  s2idle (`suspend_stats` success 1), power key wakes it, lock screen,
  session and touch fine, Wi-Fi reconnected. With the cable in a computer
  the suspend is still refused, by design.
