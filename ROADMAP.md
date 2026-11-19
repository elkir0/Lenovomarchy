# Roadmap

Where the YT-J706F port stands and what is left before it is a fully working
Omarchy tablet. Updated 2026-11-19, when work on the project stopped
(see "Where it stopped" at the end). Facts come from `docs/hardware/` (read on
the unit); this file only summarises them and orders the work.

Legend: **works** (tested on the unit), **partial** (works with a known gap),
**untested** (in place, never exercised), **missing** (does not work yet),
**n/a** (not on this model).

## Hardware status

| Block | State | Notes |
|---|---|---|
| Boot (LK, `boot_a`, root on `userdata`) | works | Keyless fastboot through the preloader; `fastboot boot` unusable (`docs/hardware/INVENTORY.md`) |
| Display (Himax HX83102P, DSI) | works | `docs/hardware/DISPLAY.md`; 60.07 Hz since 2026-11-18 (at 59.4 Hz a band repeated at the panel's first rows) |
| Backlight (KTZ8864A, LM36274-class) | works | Linear mapping and four LED strings since 2026-11-18 (it was about 1 % of the LED current at 28 %); off before suspend through `bl_power` |
| Touch (Himax, zero-flash) | works | `docs/design/TOUCH.md`; firmware extracted from the unit |
| Pen (Precision Pen 2, through the touch chip) | untested | No pen at hand so far |
| GPU (Mali-G76, Panfrost) | works | |
| Wi-Fi (MT7663 SDIO) | works | 2.4 GHz measured; 5 GHz not measured |
| Bluetooth (MT7663 SDIO) | works | Scan works; loaded before Wi-Fi (shared ROM patch); RFCOMM (hands-free, headset profiles) and BNEP in the kernel since 2026-11-18, no device paired yet |
| Speakers (4x CS35L41) | works | Stereo through the protection DSP; no factory calibration |
| Microphones (AS33970 voice processor) | partial | Since 2026-11-18: firmware loaded by `snd-soc-as33970` (ready 31 s after power-on), stereo capture through PipeWire with a fixed +15 dB (voice heard back by the owner); voice-processing mode untested (`BOARD.md`, Audio wiring) |
| Battery gauge (bq27541) | works | |
| Charging (MT6360) | works | 2 A with a temperature guard (`yt11-charge-guard`, cut from 45 °C); not tested from a wall charger yet |
| USB-C (MT6360 TCPC, mtu3) | works | Gadget network to the Mac, role switch |
| microSD (MSDC, SDR104) | untested | Node matches the stock DT; needs a card in the slot |
| Vibrator (ERM on MT6359 VIBR) | partial | Since 2026-11-18: the LDO switches with a rumble effect; buzz not yet felt by a person |
| Buttons (power, volume) | works | |
| Accelerometer + gyroscope (BMI220) | works | Auto-rotation in all four positions |
| Light sensor (LTR-578) | partial | Reads lux, drives auto-brightness (`yt11-autobrightness`); curve raised on 2026-11-18 (0.3 lux gives 22 %); only tested in a dim or dark room |
| Proximity | missing | LTR-578 proximity part and the device at i2c1 0x29 not supported |
| Rear camera (OV8856) | partial | libcamera + omacam, autofocus, stock colour matrices; no lens shading correction, AF ~18 s to settle at app start |
| Front camera (S5K4H7) | partial | libcamera + omacam, stock colour matrices; no lens shading correction |
| Thermal (LVTS) | works | Throttling at 85 °C |
| Suspend (s2idle) | partial | Works, Wi-Fi back on resume; ~135 mA asleep (about 48 h) |
| Suspend (deep), CPU idle states, CPU hotplug | missing | Anything that powers a core down freezes the unit with no watchdog reset (`BOARD.md`); needs the vendor's SPM/MCDI setup (`docs/research/CPUIDLE-MT6785.md`) |
| Hardware video decode/encode | missing | Not feasible without Android's proprietary `vpud` daemon: the codec's register programming lives there (`docs/research/VIDEO-DECODE-MT6785.md`) |
| Keyboard accessory (pogo) | missing | Not ported |
| Headphone jack, cover sensor, modem, GNSS | n/a | Not fitted on the Wi-Fi model |

## Software status

| Piece | State | Notes |
|---|---|---|
| Omarchy 4.5.0-3 + Omarchy Mobile 0.1.48 / shell 0.2.133 | works | `docs/research/omamobile/STATUS-20261117.md` |
| Image build (`image/build-rootfs.sh`) | works | Fresh flash on a wiped `userdata` tested on 2026-11-18 (`image/README.md`, Fresh install); the non-redistributable firmware is installed afterwards over USB |
| Firewall (ufw) | works | IPv6 rules load since 2026-11-18 |
| Lock screen, shell gestures | works | Checked on 2026-11-18 with injected touches (`tools/faketouch.py`) and screenshots: swipe up, password on the on-screen keyboard, recent apps, app launch; locks after 5 minutes idle and blanks 10 s later, a touch wakes it. Not yet done by hand |
| `omarchy update` on the tablet | works | Ran on 2026-11-18 after two fixes (keyring step, orphan cleanup that removed the Wi-Fi firmware package); migrations to hold are listed in `image/rootfs/omarchy-migrations.hold` |
| Camera app (omacam) | works | Viewfinder and AF checked; photo with each camera (3260x2448), camera switch and a video (1080p H.264 + Opus) taken through the app's buttons by injected touches on 2026-11-18; pictures not looked at |

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
- [x] Run `omarchy update` once on the tablet and keep the hold list current.
- [x] Flash the image `image/build-rootfs.sh` produces on a wiped `userdata`
      and go through first boot (2026-11-18; the build now ships the A/B
      slot service, `tools/flash-rootfs.sh` writes the image).

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

- [x] AS33970 firmware start: the I2C bus was too fast for the chip (50 kHz
      now).
- [x] Codec driver, capture link on I2S2, PipeWire source.
- [x] With the owner: record a voice and listen to it (faint, hence a fixed
      +15 dB on the PipeWire source).
- [ ] Which microphone is left and right.
- [ ] Voice mode (echo cancelling, noise reduction) for calls; the chip's
      power draw in system sleep; a faster firmware load (30 s today).

### R4: power

- Find the extra ~50 mA the speaker DSP firmware costs in system sleep (the
  sleep hook unloads it meanwhile).
- Understand SPM/MCDI enough for CPU idle states and `deep` sleep: the main
  lever on the ~135 mA standby floor. Studied on 2026-11-18
  (`docs/research/CPUIDLE-MT6785.md`): the vendor kernel kicks the SPM
  firmware and configures MCDI through SiP SMCs and an SSPM mailbox before
  its first `CPU_SUSPEND`; a module replaying that sequence is the next
  experiment, with someone at the tablet (a failed try needs a forced
  restart by hand).

### R5: video (closed)

- Studied on 2026-11-18 (`docs/research/VIDEO-DECODE-MT6785.md`): the
  decoder is of the MT8183 family and mainline has its clocks, power
  domains and IOMMU ports, but the vendor runs the codec from a proprietary
  user-space daemon (`vpud`) and no VPU or SCP firmware exists for this
  chip. Video stays decoded on the CPU.

### R6: remaining hardware

- Proximity (LTR-578 part, unknown device at i2c1 0x29).
- Keyboard accessory (I2C-HID MCU at 0x60/0x61, hall interrupt GPIO196).
- 5 GHz Wi-Fi measurement; which backlight chip vendor is fitted.

## Out of scope

Android coexistence (the tablet runs Linux only), publishing (nothing is
pushed without the owner), and the partitions `CLAUDE.md` forbids.

## Where it stopped (2026-11-19)

The last session ran unattended on the night of 2026-11-18. What it left:

- **On the tablet**: the image flashed on 2026-11-18 plus the night's fixes
  applied in place, and the kernel of `yt11` at `fec216c2b` in `boot_a`.
- **Checked without a person** (injected touches and screenshots): lock
  screen and unlock, recent-apps gesture, app launch, the camera app's
  photo, video and camera switch, `omarchy update`, auto-lock after 5
  minutes. Sound was only tested silent at night (stream opens, no error).
- **Not checked by a person**: touch by hand, a sound from the speakers
  and the microphones after the last kernel, the screen in daylight,
  vibrator, microSD, pen, keyboard accessory, wall charger.
- **Hazard**: never take a CPU offline, enable a PSCI idle state or use
  `deep` suspend (`BOARD.md`, CPU hotplug). The night session did the first
  one as a probe and the tablet stayed frozen until restarted by hand.
- **Image**: `image/build-rootfs.sh` builds with all of the above and passes its
  smoke check (2026-11-18, 22:54), but that image was **not flashed**: the
  tablet was frozen by then. The last image tested by a fresh flash is the
  one of the afternoon of 2026-11-18.
- **Open work, by value**: CPU idle states and deep sleep (R4), the
  microphones' voice mode and the reason the voice processor needs a slow
  I2C bus (R3), lens shading (R2), proximity and keyboard accessory (R6).
  Hardware video decode is closed (R5).
