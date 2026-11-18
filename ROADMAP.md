# Roadmap

Where the YT-J706F port stands and what is left before it is a fully working
Omarchy tablet. Updated 2026-11-18. Facts come from `docs/hardware/` (read on
the unit); this file only summarises them and orders the work.

Legend: **works** (tested on the unit), **partial** (works with a known gap),
**untested** (in place, never exercised), **missing** (does not work yet),
**n/a** (not on this model).

## Hardware status

| Block | State | Notes |
|---|---|---|
| Boot (LK, `boot_a`, root on `userdata`) | works | Keyless fastboot through the preloader; `fastboot boot` unusable (`docs/hardware/INVENTORY.md`) |
| Display (Himax HX83102P, DSI) | works | `docs/hardware/DISPLAY.md` |
| Backlight (LM36274-class) | works | Off before suspend through `bl_power` |
| Touch (Himax, zero-flash) | works | `docs/design/TOUCH.md`; firmware extracted from the unit |
| Pen (Precision Pen 2, through the touch chip) | untested | No pen at hand so far |
| GPU (Mali-G76, Panfrost) | works | |
| Wi-Fi (MT7663 SDIO) | works | 2.4 GHz measured; 5 GHz not measured |
| Bluetooth (MT7663 SDIO) | works | Scan works; loaded before Wi-Fi (shared ROM patch) |
| Speakers (4x CS35L41) | works | Stereo through the protection DSP; no factory calibration |
| Microphones (AS33970 voice processor) | missing | Firmware upload acknowledged, firmware never starts (`BOARD.md`, Audio wiring) |
| Battery gauge (bq27541) | works | |
| Charging (MT6360) | works | 2 A with a temperature guard (`yt11-charge-guard`, cut from 45 °C); not tested from a wall charger yet |
| USB-C (MT6360 TCPC, mtu3) | works | Gadget network to the Mac, role switch |
| microSD (MSDC, SDR104) | untested | Node matches the stock DT; needs a card in the slot |
| Vibrator (ERM on MT6359 VIBR) | partial | Since 2026-11-18: the LDO switches with a rumble effect; buzz not yet felt by a person |
| Buttons (power, volume) | works | |
| Accelerometer + gyroscope (BMI220) | works | Auto-rotation in all four positions |
| Light sensor (LTR-578) | partial | Reads lux, drives auto-brightness (`yt11-autobrightness`); only tested in a dim room |
| Proximity | missing | LTR-578 proximity part and the device at i2c1 0x29 not supported |
| Rear camera (OV8856) | partial | libcamera + omacam, autofocus, stock colour matrices; no lens shading correction, AF ~18 s to settle at app start |
| Front camera (S5K4H7) | partial | libcamera + omacam, stock colour matrices; no lens shading correction |
| Thermal (LVTS) | works | Throttling at 85 °C |
| Suspend (s2idle) | partial | Works, Wi-Fi back on resume; ~135 mA asleep (about 48 h) |
| Suspend (deep), CPU idle states | missing | Need MediaTek's SPM/MCDI firmware handling |
| Hardware video decode/encode | missing | No `mtk-vcodec` support for MT6785 |
| Keyboard accessory (pogo) | missing | Not ported |
| Headphone jack, cover sensor, modem, GNSS | n/a | Not fitted on the Wi-Fi model |

## Software status

| Piece | State | Notes |
|---|---|---|
| Omarchy 4.5.0-3 + Omarchy Mobile 0.1.48 / shell 0.2.133 | works | `docs/research/omamobile/STATUS-20261117.md` |
| Image build (`image/build-rootfs.sh`) | works | Builds what the tablet runs; a fresh flash of it not yet tested |
| Firewall (ufw) | works | IPv6 rules load since 2026-11-18 |
| Lock-screen keypad, shell gestures | untested | Need a person at the screen |
| `omarchy update` on the tablet | untested | Migrations to hold are listed in `image/rootfs/omarchy-migrations.hold` |
| Camera app (omacam) | partial | Viewfinder and AF checked; photo, video and camera switch not checked |

## Milestones

### R1: quick wins (in progress)

- [x] ufw IPv6 rules: netfilter matches in the kernel config.
- [x] Vibrator in the device tree.
- [x] Auto-brightness helper from the light sensor (`yt11-autobrightness`).
- [ ] Auto-brightness in daylight.
- [x] Charge current 2 A with a battery temperature guard (`yt11-charge-guard`).
- [ ] Charging from a wall charger (USB PD) and over a full charge.
- [ ] With the owner: feel the vibrator, insert a microSD card, try the pen,
      unlock with the keypad, the shell gestures, photo/video in omacam.
- [ ] Run `omarchy update` once on the tablet and keep the hold list current.
- [ ] Flash the image `image/build-rootfs.sh` produces on a wiped `userdata`
      and go through first boot.

### R2: camera quality

- [x] Colour matrices for both sensors (from the stock tuning) and a white
      balance that ignores clipped pixels.
- [x] Lens shading correction in the soft ISP (libcamera 0.7.2-4.7, `Lsc`
      tuning block) and a fit tool (`tools/camera/lsc-fit.py`).
- [ ] Lens shading coefficients: needs a flat-field frame per camera (blank
      white diffuser on the lens, even light). Two tries by hand on
      2026-11-18 were not flat enough; until then the corners stay dark.
- Faster autofocus at app start (first sweep), then photo/video checks.

### R3: microphones

- Get the AS33970's firmware to start (second-stage loader mailbox, see
  `BOARD.md`), then a capture link on I2S2 and a PipeWire source.

### R4: power

- Find the extra ~50 mA the speaker DSP firmware costs in system sleep (the
  sleep hook unloads it meanwhile).
- Understand SPM/MCDI enough for CPU idle states and `deep` sleep: the main
  lever on the ~135 mA standby floor.

### R5: video

- Port `mtk-vcodec` (decoder first) to MT6785 and expose it through V4L2
  stateless/stateful decoding for GStreamer and browsers.

### R6: remaining hardware

- Proximity (LTR-578 part, unknown device at i2c1 0x29).
- Keyboard accessory (I2C-HID MCU at 0x60/0x61, hall interrupt GPIO196).
- 5 GHz Wi-Fi measurement; which backlight chip vendor is fitted.

## Out of scope

Android coexistence (the tablet runs Linux only), publishing (nothing is
pushed without the owner), and the partitions `CLAUDE.md` forbids.
