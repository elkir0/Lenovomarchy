# YT-J706F cameras: facts from the stock device tree

Read on 2026-11-16 from the stock firmware `YT-J706F_S240301_240918_ROW`
(decompiled `dtb`/`dtbo`) and the unit's inventory. Nothing here has been
tried on mainline yet. The SoC is the MT6785, the same as the Xiaomi
begonia whose camera bring-up notes are in `src/begonia-ftp/camera/`.

## Sensors and buses

The stock DT describes three camera slots (vendor bus numbering, both
buses at 400 kHz, `mediatek,use-open-drain`):

| Slot (vendor name) | Bus | Sensor client | Autofocus | EEPROM |
|---|---|---|---|---|
| `camera_main` | i2c2 | 0x1a | 0x0c | 0x50 |
| `camera_sub` | i2c4 | 0x2d | none | 0x52 |
| `camera_main_two` | i2c4 | 0x10 | 0x0c | 0x50 |

As on other MediaTek boards these client addresses are placeholders: the
vendor sensor driver sets the real address itself. The stock software
names one sensor driver, `ov8856_mipi_raw` (OmniVision OV8856, 8 MP; the
mainline driver is `ov8856`). Which slot holds it, and what the other
sensor is, is not known yet: the feasibility study guessed S5K4H7 or
OV8856. The stock bus-addr inventory lists camera clients on buses 2 and
4 and one at 7-0043.

## Power, reset and clock pins

From the `kd_camera_hw1` pin states (`camN` = sensor index 0 or 1):

| Signal | cam0 | cam1 |
|---|---|---|
| Reset | GPIO119 (GPIO mode, high = run) | GPIO124 |
| Analog supply switch `vcama` | GPIO195 | GPIO195 (shared) |
| Digital supply switch `vcamd` | GPIO50 | GPIO50 (shared) |
| Autofocus supply switch `vcamaf` | GPIO197 | none |
| Master clock | GPIO117, pin function 1 (`CMMCLK`) | GPIO120, function 1 |
| I/O supply `vcamio` | MT6359 `vcamio` LDO | MT6359 `vcamio` LDO |

There is no power-down pin and no MIPI switch in the stock pin states.
`vcamio_sub`, `vcamio_main2`, `vcamaf` and `vcamaf_main2` all point to the
MT6359 `vcamio` regulator. The master clock pin states exist at 2, 4, 6
and 8 mA drive.

## SoC side

The stock DT has the same camera blocks as other MT6785 boards:
`mipi_rx_ana_csi0a`..`csi2b` from 0x11c80000 (named per 0x1000, see the
begonia notes for the real layout), `kd_camera_hw1`, SENINF, CAMSV and
the ISP. Which CSI-2 port each sensor uses is decided by the closed
camera HAL and is not in the device tree.

## Sensors identified on the unit (2026-11-16, mainline)

With the `yt11-cam-probe` module (kernel `yt11`, `stage=1`, all five CAMTG
clocks at 24 MHz) and the multi-channel I2C support
(`mediatek,ch-offset = <0x100>` on both camera buses), read-only probes
with `tools/camera/cam-id.py`:

| Slot | Mainline bus | Answering addresses | Sensor |
|---|---|---|---|
| 0 (`cam0`: reset GPIO119, MCLK GPIO117) | `i2c2` (0x11009000, `/dev/i2c-2`) | 0x36 and 0x21 (chip ID 0x885a at 0x300b on both), 0x0c (autofocus VCM) | OmniVision OV8856 |
| 1 (`cam1`: reset GPIO124, MCLK GPIO120) | `i2c4` (0x11011000, `/dev/i2c-4`) | 0x2d (ID 0x487b at 0x0000) | Samsung S5K4H7 |

Each sensor answers only when its own slot is powered; the other bus stays
silent. Neither EEPROM address (0x50, 0x52) answered the scan. Without a
master clock neither sensor answers. Enabling one CAMTG clock at a time:
cam0's MCLK (GPIO117, `CMMCLK1`) is `CLK_TOP_CAMTG2` and cam1's (GPIO120,
`CMMCLK2`) is `CLK_TOP_CAMTG3`. Which physical camera (rear or front) is
which slot and which CSI-2 port each sensor uses are still open.

## First frames (2026-11-16, mainline, experiment modules)

With the `mt6785-seninf-tm` / `mt6785-camsv-tm` modules and
`tools/camera/` (see `docs/research/camera/T2-SENINF-CAMSV.md`):

- The SENINF test model runs (MUX0 size 0x10001f00, pixel count advancing)
  and `cap-tm.sh` gets a full 640x480 RAW10 test-pattern frame (384000
  bytes) from CAMSV0 into memory, larb6/larb7 MMU bypassed.
- OV8856 (cam0) streaming 640x480 on 2 lanes, sweeping the CSI ports with
  `ov-cap.py`: only **CSI port 1** (SENINF2, MIPI RX ANA 0x4000/0x5000)
  sees packets (PKT_CNT 0x01e1xxxx, MUX2 size 0x01e00280, DPHY lane state
  0x110); ports 0 and 2 stay at zero. CAMSV0 then writes the full frame:
  the sensor's colour bars come out as expected, and a capture without
  the test pattern gives a dark noisy frame (dark room, not yet checked
  in light). CAMSV0 INT_STATUS reads 0x0018048f and TG_FRMSIZE 640x481.
- The S5K4H7 (cam1) path is not tried yet.

## Frame layout and first photo (2026-11-16)

- With `FMT_SEL` (CAMSV +0x514) = 0x101 and `PAK` (+0x54c) = 2, the values
  taken from begonia, IMGO writes 12-bit fields (two pixels in three
  bytes, the 10-bit sample shifted left by two): an 800-byte line then
  holds only 533 of the 640 pixels.
- With `FMT_SEL` = 0x102 and `PAK` = 1 and the line still sized for 10
  bits (800 bytes for 640 pixels, 384000 bytes per frame), the frame is
  complete: 10-bit samples packed as one continuous little-endian bit
  stream per line (pixel k in bits 10k..10k+9). This is not the MIPI
  RAW10 byte layout. Sized for 12 bits (960 bytes per line) the DMA stops
  at half the buffer.
- Decoded as BGGR, the OV8856 colour bars come out as clean vertical bars
  (magenta, red, blue, black at 640x480) and a capture with exposure 1200
  lines and analogue gain 2047 shows the room: the first photo from this
  tablet on mainline (rear-facing camera = cam0, out of focus: the VCM
  is not driven). Samples: `tools/camera/samples/*-le10.raw`.
- `ov-cap.py --frames N` works since it re-arms FBC for each frame.
