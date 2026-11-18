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
- `ov-cap.py --frames N` returns a frame, but always the first one of the
  stream (see the FBC section below).

## FBC and interrupts (2026-11-17)

Measured with the V4L2 driver streaming the OV8856 at 640x480 (about 120
frames per second) and `/dev/mem` pokes at CAMSV0:

- `INT_EN` (+0x518) bit 31 switches `INT_STATUS` (+0x51c) from
  read-to-clear to write-1-to-clear. Writing 0xffffffff there, as the
  experiments did, leaves the level interrupt asserted for a handler that
  only reads the status (about 570 000 interrupts per second). The vendor
  value 0x001304b1 (bit 31 clear) gives one VS (bit 0), one SOF (bit 7)
  and one PASS1_DON (bit 10) per frame.
- `FBC_IMGO_CTL1` (+0x110) with FBC_EN (bit 15) and the low field at 1
  writes exactly one frame, then drops every frame: `FBC_IMGO_CTL2`
  (+0x114) reads 0xNN000001 with [31:24], the drop count, rising at the
  frame rate. Turning FBC off and on, resetting the IMGO DMA, or writing
  bits 8, 16 or 22 does not release it. So `ov-cap.py --frames N` only
  ever stored its first frame.
- The low field of CTL1 is a compare value, not the "RCNT_INC" strobe the
  begonia notes took it for: CTL2[6:0] counts the frames written (it
  wraps through 0) and the DMA stops, dropping frames, exactly when that
  count equals the compare value, or always when the compare value is 0.
  Written once, 2 gives two frames and 0x3f gives 63. Nothing was found
  that decrements the count. The V4L2 driver keeps the compare value 8
  ahead of the count at every PASS1_DON, which makes the DMA free-running.
- `IMGO_BASE_ADDR` (+0x20) written during vertical blanking applies to
  the next frame: each frame lands in its own buffer (zero copy).

## Both cameras through V4L2 (2026-11-17)

Driver `drivers/media/platform/mediatek/mt6785-cam/` (kernel `yt11`
31acd55e6 and the next commit), `tools/camera/v4l2-capture.sh`:

- OV8856 (cam0, CSI port 1, 2 lanes): 20 of 20 distinct frames at
  640x480, 6 of 6 at 1632x1224, 4 of 4 at 3264x2448 (TG sees one extra
  line in each mode), all checked by content. The full-size mode needs a
  larger CMA pool than the 32 MB default (160 MB used).
- S5K4H7 (cam1, 4 lanes, 700 MHz): nothing on CSI port 0 (PACKET_CNT 0);
  on **CSI port 2** (SENINF4) it delivers 5 of 5 frames at 640x480 and 8
  of 8 at 1632x1224 (GRBG). Its picture in the dark room is black with
  one faint spot: not yet judged in light. Its exposure control tops at
  626 lines and its analogue gain at 512.
- One sensor at a time: the seninf has one enabled sink link, switched
  with `media-ctl -l` (the script's `-c ov8856|s5k4h7`).
- Open: frames are a little-endian 10-bit bit stream exposed as `S*10P`
  (libcamera's software ISP cannot read it), the autofocus VCM at 0x0c is
  not driven, LARB MMU is bypassed, no picture has been taken in light.

## Standard 16-bit layout and autofocus actuator (2026-11-17)

- Packer sweep at 640x480 with the driver's `fmt_sel` / `pak` /
  `bytes_per_px_x8` parameters (OV8856 colour bars): `FMT_SEL` 0x102 with
  `PAK` 5 (PAK 1 plus bit 2) and two bytes per pixel writes each sample
  in a little-endian 16-bit word, value in the low 10 bits
  (`ff 03 00 00 ff 03 ...` on a bar line): the standard unpacked V4L2
  Bayer layout. `PAK` 0, 1, 2, 3 with a 2-byte line, bit 24 of FMT_SEL,
  and FMT_SEL 0x100, 0x101, 0x103 delivered no complete frame; `PAK` 1
  with a 10-bit line is the bit-stream layout above.
- A 1632x1224 real scene captured that way (bytes per line 3264, 6 of 6
  frames) decodes correctly with `raw2rgb.py --layout u16`.
- Autofocus: with the `dw9714` driver bound at 0x0c on i2c2 and its
  subdev held open (which powers `vcamaf`, GPIO197) the actuator ACKs.
  Register reads return 0x00 except 0x60 at registers 0x02 and 0x05.
  Sweeping `focus_absolute` 0..1023 during capture changed nothing
  measurable in image sharpness (9.4 to 9.5 on a noise-dominated dark
  scene at gain 2047): whether the dw9714 protocol moves this lens is
  not established. To redo in light, listening for the lens.

## Unpacked layout as the driver default (2026-11-17)

Kernel `yt11` c293f1f3c: the CAMSV node advertises only the unpacked
10-bit Bayer formats (`BG10`, `GB10`, `BA10`, `RG10`), FMT_SEL 0x102 /
PAK 5, bytes per line = 2 x width. Measured with
`tools/camera/v4l2-capture.sh`, all frames delivered, none missed or torn:

| Sensor | Mode | Frames | Bytes per frame |
|---|---|---|---|
| OV8856 | 640x480 (colour bars) | 20 of 20 | 614400 |
| OV8856 | 1632x1224 (colour bars, then real scene) | 6 of 6, twice | 3995136 |
| OV8856 | 3264x2448 (colour bars) | 4 of 4 | 15980544 |
| S5K4H7 | 640x480 | 5 of 5 | 614400 |
| S5K4H7 | 1632x1224 | 8 of 8 | 3995136 |

Selecting the other sensor is one `media-ctl -l` call (the seninf drops
the previous link itself). The `orientation` / `rotation` properties in
the board DT (rear 90, front 270) are guesses, not measured.

## libcamera (2026-11-17)

`image/camera/libcamera-yt11/` built on the tablet (libcamera 0.7.2,
simple pipeline, software ISP on the GPU through Panfrost, about 5
minutes on the eight cores) and installed:

- The media device's driver name must fit 15 characters: the default
  (the platform driver's name) was cut to `mtk-mt6785-seni` and matched
  nothing. The kernel now sets `mt6785-cam` (yt11, commit after
  c293f1f3c) and the libcamera patch lists that name.
- `cam -l` lists `Internal front camera` (S5K4H7) and `Internal back
  camera` (OV8856).
- `cam -c N --capture=8 --file=x.ppm` delivers 3260x2448 RGB frames from
  both, about 30 frames per second with a few skipped sequence numbers.
  The rear frame shows the room (dark and out of focus), upright as
  saved; the front frame is nearly uniform in the dark.
- libcamera warns that neither sensor driver implements the selection
  (crop) targets and that it has no tuning file or sensor helper for
  them: exposure and colour are uncalibrated defaults.

## Lit-room tests and autofocus (2026-11-17, morning)

- Both cameras show the room once exposure and gain are raised by hand
  (`v4l2-capture.sh -e/-g`; OV8856 at 1200 to 2400 lines, S5K4H7 at its
  maximum 626 lines and gain 512, in a dim room). Through libcamera the
  same scene stays dark: without a sensor helper the software ISP does
  not raise the exposure.
- The autofocus actuator at 0x0c is a **DW9718S-compatible** part, not a
  DW9714. With a close subject (about 40 cm) and the sharpness measure of
  the earlier sweep: the DW9714 protocol leaves it at 9.3 over the whole
  range again; writing the DW9718S registers by hand (0x00 = 0, 0x01 =
  0x39, position in 0x02/0x03) gives 9.5 at 0, 11.6 at 260, 18.9 at 340,
  14.1 at 380, 7.7 at 768 and above. The registers read back.
- With the board DT node switched to `dongwoon,dw9718s` (mainline
  `dw9719` driver, `vdd-supply` = vcamaf) the `focus_absolute` control
  gives the same curve (18.6 at 340). A full-size photo at that position
  is sharp: screen text is readable. The driver logs `Error writing reg
  0x0000: -6` at each power-up (first write after the rail comes up) and
  works regardless.
- With the tablet standing in landscape the rear picture is upright as
  stored. The front picture's orientation is not judged yet.

## libcamera auto-exposure (2026-11-17)

- Two additions make the software ISP's exposure loop work. The sensor
  drivers report their crop rectangles (`get_selection`: OV8856 active
  area 3264x2448 at (16,16) in a 3296x2480 array, S5K4H7 3264x2448 at
  (8,8), native size assumed 3280x2464), and
  `libcamera-0.7.2-yt11-sensors.patch` gives libcamera a gain model
  (OV8856 code/128, S5K4H7 code/32), a black level (64 at 10 bits) and
  static properties for both sensors (package 0.7.2-4.2, built on the
  tablet).
- The crop, sensor helper, static properties and sensor delays warnings
  are gone. What remains: no tuning file (`ov8856.yaml`, `s5k4h7.yaml`),
  libcamera falls back to `uncalibrated.yaml`.
- In the lit room the loop raises the exposure, then the gain, by at most
  6 % per step: from the driver defaults it needs about 110 steps (some
  15 s at 30 fps, 450 frames captured). Both cameras end at the maximum
  exposure (2524 lines) and gain (16x); the mean of the RGB output goes
  from about 30 to about 150 of 255. The result is on the bright side:
  windows are blown out and colours are washed.
- The sensor delays ({2, 2, 2, 2}) are copied from neighbouring entries,
  not measured.
- Camera numbers in `cam -l` are not stable: the back camera was 2 before
  this rebuild and 1 after. Select a camera by its id string.
- Mounting, checked with the tablet standing in landscape on its
  kickstand (owner's confirmation): the rear sensor's picture is upright
  as stored, the front sensor's is upside down. The DT now says
  `rotation = <0>` (rear) and `<180>` (front). libcamera reports these
  values and sets both flips on the S5K4H7 by itself: both pictures come
  out upright.
- libcamera does not drive the focus actuator: the rear picture of a
  close subject is blurred unless `focus_absolute` is set by hand.

## Auto-exposure tuning (2026-11-17)

- Package 0.7.2-4.3: `libcamera-0.7.2-yt11-agc.patch` makes the soft
  IPA's exposure loop tunable and `ov8856.yaml` / `s5k4h7.yaml` are
  installed as tuning files (no more fallback warning).
- With gain 0.35, step cap 0.35 and dead band 0.1 the loop settles in 6
  to 13 corrections, 1 to 2 s, where the stock values needed about 110
  (15 s). Statistics still come every fourth frame.
- Target 2.0 left the picture washed (front camera output mean about
  135 of 255, gain 11.7x, 2416 lines). Target 1.6, the value kept, gives
  about 100 of 255 at 1559 lines and the same gain, with the windows
  less blown out. The rear camera, pointed at a white page, gives 136.
- Colours stayed dull and slightly green without a colour matrix; see
  "Colours" below.
- The 4.3 packages on the tablet were built with target 2.0; the
  installed tuning files were then replaced by the 1.6 ones by hand
  (4.4 is built with 1.6).

## Focus through libcamera (2026-11-17)

- Package 0.7.2-4.4 adds `libcamera-0.7.2-yt11-lens.patch` and
  `libcamera-0.7.2-yt11-af.patch`. The rear camera lists `LensPosition`
  (0.0 far to 1.0 near, linear over 0..1023), `AfMode` and `AfTrigger`;
  the front camera lists none and captures as before at 30 fps.
- Manual: `LensPosition` 0.0, 0.33 and 1.0 from a `cam --script` file
  move the actuator to 0, 337 and 1023.
- Autofocus (`AfMode: 1` + `AfTrigger: 0`), subject at about 40 cm: with
  the stock steps it ends at 330 in 18 s; with `coarseStep` 60,
  `fineStep` 10, `settleFrames` 1 (kept in `ov8856.yaml`) it takes about
  8.5 s, `AfState` going from scanning to focused.
- With the raw sharpness sum, in a dim room (gain 16x, exposure at
  maximum) 3 runs in 10 ended elsewhere (300, 370, about 100): the sum
  follows brightness and only varies by about 10 % across the sweep. The
  figure is now divided by the green sum; after that 8 runs in 8 ended
  at 320.
- Not tested: `AfModeContinuous`, a far subject, low light. The lens
  subdev stays open, so the actuator supply stays on, as long as a
  libcamera process holds the camera manager.
- Faults found on the unit and fixed in the patches: the IPA moved the
  lens during `configure()`, before the proxy was running (fatal
  assertion); two `std::min`/`std::max` calls mixed signed and unsigned;
  sharpness was not normalised by brightness.

## Camera app (omacam) and continuous autofocus (2026-11-17)

- Omarchy Mobile's camera app, `omacam` 0.3.3-1, is installed on the
  tablet from `pkgs.omamobile.org/stable/aarch64` (sha256 matches the
  repository index, signature good against the release key in upstream's
  git tree), with `gst-plugins-good`, `gst-plugins-ugly`,
  `gst-plugin-pipewire` and `pipewire-libcamera` from Arch Linux ARM. It
  links against the tablet's own libcamera 0.7.2 build. Not in the image
  build yet.
- It opens on the rear camera, upright, with the 1x/2x/5x zoom buttons,
  Night/Photo/Video/Pro modes and the front-camera switch drawn. Only the
  viewfinder was checked: no photo, video or front-camera switch was
  tried (the shutter makes a sound).
- libcamera 0.7.2-4.5, three changes found with the app:
  - the app asks for `AfModeContinuous` in the controls given to
    `Camera::start()`, which the simple pipeline dropped: they now go to
    the IPA with the first request;
  - continuous mode starts with a sweep (it only reacted to a sharpness
    drop after a first sweep, so it never started);
  - a sweep waits until exposure and gain have been unchanged for three
    statistics: started on the first frames, it took the dark, noisy
    frames for the sharpest and stayed at 0.
- With these the lens goes 0, 240 ... 960, then 260 ... 340 and settles
  at 320 about 18 s after the app starts (sweep 12 s after a 6 s wait),
  and the viewfinder is sharp. `cam` with `AfMode: 2`: 3 runs in 3 end
  at 320.
- Reading the lens while libcamera holds it:
  `v4l2-ctl -d /dev/v4l-subdev2 --get-ctrl focus_absolute`. omacam sets
  `LIBCAMERA_LOG_FILE=syslog`: libcamera's log is in the journal.

## Colours (2026-11-18)

- Colour matrices: the stock camera tuning
  (`/vendor/lib64/ov8856_mipi_raw_tuning.so`, `s5k4h7_mipi_raw_tuning.so`
  and the `txd` / `yxsub` variants) holds four MediaTek "dynamic CCM"
  entries as packed 13-bit fields in units of 1/512, followed by the
  white balance gains of their light sources (R, G, B over 512: 1342/647,
  978/915, 1114/1021, 681/1207, i.e. D65, TL84, CWF, A). The four
  libraries hold the same matrices and gains: the stock tuning does not
  distinguish the two sensors here. `ov8856.yaml` and `s5k4h7.yaml` carry
  the D65, TL84 and A matrices at 6500, 4000 and 2850 K (the CWF entry's
  first row sums to 485 instead of 512 and is left out).
- White balance: the soft IPA's grey-world sums counted clipped pixels,
  which read the same in every channel and pull both gains towards 1. On
  the front camera facing a room with a blown-out window that gave gains
  of 1.47 / 1.36 and cyan whites (a white fan blade at 65, 86, 77), which
  the matrix then amplified. `libcamera-0.7.2-yt11-awb.patch` (package
  0.7.2-4.6) adds sums that leave out pixels with a channel at 240 of 255
  or more and uses them unless nearly everything is clipped: gains 1.72 /
  1.60 in the same scene, picture mean 86, 86, 85, white wall white, wood
  brown, skin natural.
- Cost: none measurable. The omacam viewfinder uses about 1.3 cores with
  or without the matrix (it is applied in the GPU debayer shader).
- Left: lens shading. The corners are darker and greener than the centre
  on both cameras; the soft ISP has no shading correction. Grey-world
  white balance still follows a scene's dominant colour. Nothing was
  measured against a colour chart.
