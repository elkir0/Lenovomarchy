# T9: Userspace RAW Conversion and OV8856 Exposure/Gain Tools

Python 3 standard-library-only tools under `tools/camera/` for turning MT6785 CAMSV0 raw captures from the OmniVision OV8856 (`cam0`) into viewable RGB PNGs and tuning sensor exposure/gain over `/dev/i2c-N`. No third-party packages (`numpy`, `PIL`) are required.

## 0. The real IMGO byte layout (measured 2026-11-16)

The complete frame is captured with **`FMT_SEL` (0x514) = 0x102, `PAK`
(0x54c) = 1 and the line sized for 10 bits** (`bpl = w * 10 / 8`, 800 bytes
for 640 pixels, 384000 bytes per 640x480 frame). The data is **a continuous
little-endian 10-bit bit stream per line**: pixel k occupies bits 10k..10k+9
of the line read as a little-endian integer. This is *not* the MIPI RAW10
byte layout (the two only share their size). Samples captured that way:
`tools/camera/samples/ov8856-bars-640x480-le10.raw` (OV8856 test-pattern
colour bars) and `tools/camera/samples/ov8856-scene-640x480-le10.raw` (a real
scene, black level about 64, exposure 1200 lines, analogue gain 2047 — the
first photo from this tablet on mainline; see
`docs/hardware/CAMERA.md` "Frame layout and first photo").

| | `le10` (default, complete frame) | `p12` (old begonia values, reference) | `raw10` (MIPI, for reference) |
|---|---|---|---|
| grouping | continuous LE 10-bit bit stream | 2 px / 3 bytes | 4 px / 5 bytes |
| container | bits 10k..10k+9 of the line | LE 12-bit field, sample << 2 | 8-bit MSBs + packed 2-bit LSBs |
| bytes/line | `w * 10 / 8` (800 for 640) | `w * 12 / 8` (960 for 640) | `w * 10 / 8` (800 for 640) |
| CAMSV `PAK` (0x54c) | 1 | 2 | 2 |
| CAMSV `FMT_SEL` (0x514) | `0x102` (TG1_FMT=2) | `0x101` (TG1_FMT=1) | `0x101` |

The `p12` values (`FMT_SEL = 0x101`, `PAK = 2`, taken from begonia) make the
DMA write 12-bit containers (two pixels in three bytes, the 10-bit sample
shifted left by two, `0xffc` = 1023 << 2). **Truncation**: with the line
sized for 10 bits (800 bytes) only `533` of the `640` pixels per line fit
and the decoders produced garbage columns; sized for 12 bits (960 bytes) the
DMA stops at half the buffer. `p12` is therefore kept only for decoding old
captures; new captures use `le10`. The historical sample
`ov8856-bars-640x480-stride800.raw` (a truncated p12 capture with an
800-byte stride) has been removed.

Capture quirk seen in the bar samples (needs hardware to resolve): the live
pixels form a **quincunx** — even-row/even-x and odd-row/odd-x carry data,
the other two Bayer phases are black (0). The two live phases carry the bar
patterns of the OV8856 test-pattern mode 1 (8 bars: white, yellow, cyan,
green, magenta, red, blue, black): one phase follows the R components (on in
W Y, off in C G, on in M R, off in B K -> boundaries at x = 160/320/480
sensor pixels), the other the G components (on in W Y C G, off in M R B K ->
boundary at 320). With `--bayer bggr` the bars therefore render as four
uniform bands (magenta, red, blue, black); the scene sample decodes with all
four Bayer phases alive.

## 1. Tools Overview

| Tool | Purpose |
|---|---|
| `tools/camera/ov-cap.py` | Captures raw frames from OV8856 over MIPI CSI-2 -> SENINF -> CAMSV0. `--layout {le10,p12}` selects the IMGO byte layout (default `le10`, see above); `--exposure`, `--again`, `--frames N` as before. |
| `tools/camera/cap-tm.sh` | Same for the SENINF test model: `[-k LAYOUT]` with the same two layouts and defaults (`le10`). |
| `tools/camera/ov-expo.py` | Reads/writes OV8856 exposure, analogue/digital gain, timing (`VTS`), test pattern, and flip/mirror via `I2C_RDWR`, plus `--auto FILE.raw` exposure estimation (still RAW10-only stats). |
| `tools/camera/raw2rgb.py` | Unpacks CAMSV raw (`--layout {le10,p12,raw10}`, auto-detected from file size and decoded content when not pinned), subtracts black level, applies grey-world WB (gains clipped to [0.2, 5] so dark-frame noise cannot tint the image) and gamma, demosaics (2x2 half-res default or `--full` bilinear), and writes an 8-bit RGB PNG. |
| `tools/camera/raw2png.py` | Fast 8-bit grayscale converter for all three layouts (uses upper 8 bits only; useful for checking raw Bayer grid / test patterns). |
| `tools/camera/test_raw2rgb.py` | Offline `unittest` suite: synthetic le10 colour patches across all four Bayer orders, 10-bit LSB unpacking, stride padding, odd widths, `--auto`, layout auto-detection, p12 decoding, and decodes of both real sample files (uniform bars in the stated colours; plausible scene statistics). |

---

## 2. Usage on the Tablet

From `docs/hardware/CAMERA.md` (lines 60–86), YT-J706F's OV8856 (`cam0`) is on `/dev/i2c-2` at address `0x36` (also `0x21`) and streams over **CSI port 1** (`--csi-port 1`, SENINF2, 2 lanes).

### 2.1 Capturing a clean frame (`ov-cap.py`)

First frames immediately after stream-on can be dark or partially exposed. Use `--frames N` to keep streaming and save the Nth frame, and optionally override exposure/analogue gain before stream-on. `--layout le10` (default) configures the DMA for the complete-frame layout and prints the bytes-per-line used:

```sh
sudo modprobe yt11-cam-probe
sudo modprobe mt6785-camsv-tm

# Default 640x480 capture (le10, 800 B/line, 384000 B/frame), skipping the first 4 frames:
sudo python3 tools/camera/ov-cap.py \
  --csi-port 1 --lanes 2 --i2c-bus 2 --i2c-addr 0x36 \
  --frames 5 --out /tmp/ov.raw

# With explicit exposure (lines) and analogue gain (128 = 1.0x):
sudo python3 tools/camera/ov-cap.py \
  --csi-port 1 --lanes 2 --i2c-bus 2 --i2c-addr 0x36 \
  --exposure 600 --again 4x --frames 5 --out /tmp/ov.raw

# Old begonia values (12-bit containers, 960 B/line) for A/B on hardware:
sudo python3 tools/camera/ov-cap.py --layout p12 ... --out /tmp/ov12.raw
```

Multi-frame note: re-arming only `RCNT_INC` on a running FBC does not latch
another frame (the old `--frames N` ended with "0 bytes written"), so each
frame now re-arms the full `FBC_EN` -> `RCNT_INC` sequence, and only the last
frame is preceded by the `0xa5` fill marker.

### 2.2 Converting raw captures to RGB PNG (`raw2rgb.py`)

```sh
# Default: layout auto-detected (le10 unless content says otherwise), 2x2 half-resolution,
# Bayer bggr, BLC=64, grey-world WB (clipped gains), gamma=2.2
python3 tools/camera/raw2rgb.py /tmp/ov.raw 640 480 /tmp/ov-rgb.png

# Full-resolution bilinear demosaic (640x480)
python3 tools/camera/raw2rgb.py /tmp/ov.raw 640 480 /tmp/ov-full.png --full

# Pin the layout explicitly (--layout le10 / p12 / raw10; --pack 10|12 still works, deprecated)
python3 tools/camera/raw2rgb.py /tmp/ov.raw 640 480 --layout p12 /tmp/ov-rgb.png

# Decode the real samples:
python3 tools/camera/raw2rgb.py tools/camera/samples/ov8856-scene-640x480-le10.raw 640 480 -o /tmp/scene.png
python3 tools/camera/raw2rgb.py tools/camera/samples/ov8856-bars-640x480-le10.raw 640 480 -o /tmp/bars.png

# Inspect all 4 Bayer orders (prints R/G1/G2/B stats and writes /tmp/ov_<order>.png + /tmp/ov.png)
python3 tools/camera/raw2rgb.py /tmp/ov.raw 640 480 /tmp/ov.png --auto

# Stats-only check without writing PNGs
python3 tools/camera/raw2rgb.py /tmp/ov.raw 640 480 --auto

# Explicit stride (e.g. raw2png.py-compatible positional syntax)
python3 tools/camera/raw2rgb.py /tmp/ov.raw 640 480 800 /tmp/ov-rgb.png
```

Options:
- `--layout {le10,p12,raw10}`: byte layout (see section 0). When not given,
  the layout is auto-detected: the file size rules out what cannot fit, then
  the remaining candidates are decoded and scored on Bayer green-phase
  diagonal symmetry plus within-plane horizontal smoothness (a wrong layout
  shuffles bits between neighbouring pixels and both measures explode; ties
  keep `le10`). The chosen value is printed as `layout=NAME` in the `ok`
  line. `--pack {10,12}` is still accepted and maps to `raw10`/`p12`.
- `--bayer {bggr,gbrg,grbg,rggb}`: Bayer CFA order (default `bggr`).
- `--black-level N`: 10-bit black level subtracted before WB/demosaic (default `64`).
- `--wb {grey,none}`: grey-world white balance anchored to green (`grey`, default) or unit gains (`none`). Grey-world gains are clipped to [0.2, 5] and fall back to unit gains when the green mean after BLC is <= 1, so noise in dark frames cannot tint the image.
- `--gamma G`: output gamma exponent (default `2.2`; `1.0` for linear output).
- `--full`: full-resolution bilinear demosaic instead of 2x2 binning.

`raw2png.py` takes the same `--layout {le10,p12,raw10}` flag (and
auto-detects: size for `p12`, horizontal-gradient content test between
`le10` and `raw10`).

### 2.3 Tuning exposure, gain, flip/mirror, and test pattern (`ov-expo.py`)

```sh
# Read current OV8856 exposure, gains, timing, orientation, and test pattern
sudo python3 tools/camera/ov-expo.py --i2c-bus 2 --i2c-addr 0x36

# Measure a captured frame and suggest updated exposure/gain (read-only)
sudo python3 tools/camera/ov-expo.py --i2c-bus 2 --i2c-addr 0x36 --auto /tmp/ov.raw --w 640 --l 480

# Measure and immediately apply the suggested exposure/gain to the sensor
sudo python3 tools/camera/ov-expo.py --i2c-bus 2 --i2c-addr 0x36 --auto /tmp/ov.raw --w 640 --l 480 --apply

# Manual register writes
sudo python3 tools/camera/ov-expo.py --i2c-bus 2 --i2c-addr 0x36 --exposure 614 --again 8x --dgain 1x
sudo python3 tools/camera/ov-expo.py --i2c-bus 2 --i2c-addr 0x36 --hflip 1 --vflip 0
sudo python3 tools/camera/ov-expo.py --i2c-bus 2 --i2c-addr 0x36 --testpat bars
sudo python3 tools/camera/ov-expo.py --i2c-bus 2 --i2c-addr 0x36 --testpat off
```

`--auto FILE.raw` can also run offline (e.g. on a host PC without `/dev/i2c-N`) using `--cur-exposure`, `--cur-again`, `--cur-dgain`, and `--cur-vts` to calculate suggestions without opening I2C. Note: `measure_raw10_frame` still assumes the raw10 byte layout; for le10 or p12 captures its mean/clip statistics are approximate (still usable for exposure bracketing, since the sample values map linearly).

---

## 3. CAMSV Byte Layouts and ISP Pipeline

### 3.1 The three layouts (see section 0 for the measurement)

**le10 — continuous LE 10-bit bit stream** (default, `CAMSV_FMT_SEL =
0x102`, `CAMSV_PAK = 1`, line sized for 10 bits): each line read as one
little-endian integer, pixel k at bits `10k..10k+9`. Per 5-byte group
(`b0..b4`, little-endian) holding pixels `p0..p3`:

| Byte | Contribution |
|---|---|
| `+0` | `p0[7:0]` (low 8 bits of `p0`) |
| `+1` | `p0[9:8]` in bits `[1:0]`, `p1[7:2]` in bits `[7:2]` |
| `+2` | `p1[9:8]` in bits `[3:0]`, `p2[7:4]` in bits `[7:4]` |
| `+3` | `p2[9:8]` in bits `[5:4]`, `p3[7:6]` in bits `[7:6]` |
| `+4` | `p3[7:0]` (low 8 bits of `p3`) |

So `p0 = b0 \| ((b1 & 3) << 8)`, `p1 = (b1 >> 2) \| ((b2 & 0xF) << 6)`,
`p2 = (b2 >> 4) \| ((b3 & 0x3F) << 4)`, `p3 = (b3 >> 6) \| (b4 << 2)`.
Unlike MIPI RAW10 the samples are *not* MSB-aligned in whole bytes: every
byte boundary is crossed.

**raw10 — MIPI CSI-2 RAW10** (`CAMSV_PAK = 2`, `CAMSV_FMT_SEL = 0x101`):
four 10-bit pixels `(P0, P1, P2, P3)` packed into 5 bytes:

| Byte offset | Contents | Bits |
|---|---|---|
| `+0` | `P0[9:2]` | Upper 8 bits of pixel 0 |
| `+1` | `P1[9:2]` | Upper 8 bits of pixel 1 |
| `+2` | `P2[9:2]` | Upper 8 bits of pixel 2 |
| `+3` | `P3[9:2]` | Upper 8 bits of pixel 3 |
| `+4` | `(P3[1:0] << 6) \| (P2[1:0] << 4) \| (P1[1:0] << 2) \| P0[1:0]` | Packed 2-bit LSBs (pixel 0 in `[1:0]`, pixel 3 in `[7:6]`) |

**p12 — 12-bit containers** (what MT6785 CAMSV writes for a RAW10 sensor
stream with the old begonia `PAK = 2 / FMT_SEL = 0x101` values): two 10-bit
samples in 3 bytes, each in a little-endian 12-bit field holding the sample
shifted left by 2:

| Byte offset | Contents |
|---|---|
| `+0` | `P0[7:0]` (low 8 bits of `P0 << 2`) |
| `+1` | `P0[11:8]` in bits `[3:0]`, `P1[3:0]` in bits `[7:4]` |
| `+2` | `P1[11:4]` |

Line length in bytes: `bpl = width * 10 // 8` (`le10`, `raw10`) or
`width * 12 // 8` (`p12`). For `640x480`: `800`/`384000` or `960`/`460800`;
for a full `3264x2448`: `4080`/`9987840` or `4896`/`11983872`.

### 3.2 Pure-Stdlib Performance Approach

To process 8 MP frames quickly without `numpy` or `PIL`:
1. `raw2rgb.py` separates even and odd lines and concatenates each parity's rows into one buffer, then slices `rows[0::5]`..`rows[4::5]` in C. For `le10` the per-pixel 16-bit enc words are rebuilt with two 65536-entry 16-bit word LUTs (each maps an adjacent byte pair `(b_k, b_k+1)` to one output byte) plus 256-byte `bytes.translate()` tables for the 2-bit remainders, interleaved into 16-bit `memoryview(...).cast('H')` phase arrays (`p00, p01, p10, p11`). A 3264x2448 frame unpacks in about 0.15 s on the development Mac (2026-11).
2. Black-level subtraction, white-balance scaling, division (for 2x2 green average or bilinear sums), and gamma encoding (`v ** (1/gamma)`) are collapsed into precomputed 1024/2047/4093-entry LUTs applied with `bytes(map(lut.__getitem__, ...))`.
3. `demosaic_half` bins each 2x2 Bayer cell (`R`, `(G1+G2)/2`, `B`) directly into RGB scanlines; `demosaic_bilinear` computes horizontal/vertical/diagonal neighbor sums across the four sub-grids with replicated-edge boundaries and slice-assigns into even/odd RGB row buffers.

---

## 4. OV8856 Register Reference

Register definitions and bitfields below are cross-checked against the mainline driver `src/mt6785-mainline/drivers/media/i2c/ov8856.c` and the tables in `tools/camera/ov-cap.py`.

| Register(s) | Mainline Driver Symbol (`ov8856.c`) | Encoding / Behaviour |
|---|---|---|
| `0x300A`–`0x300C` | `OV8856_REG_CHIP_ID` (`0x300a`), `OV8856_CHIP_ID` (`0x00885a`) | 24-bit chip ID (`0x300B`/`0x300C` = `0x885A`). (`ov8856.c` L27–28, L1699) |
| `0x0100` | `OV8856_REG_MODE_SELECT` | `0x00` = `OV8856_MODE_STANDBY`, `0x01` = `OV8856_MODE_STREAMING`. (`ov8856.c` L30–32) |
| `0x3500`–`0x3502` | `OV8856_REG_EXPOSURE` (`0x3500`, 24-bit) | 20-bit exposure in `1/16`-line units (`ctrl->val << 4`); bits `[3:0]` of `0x3502` are fractional. Range `OV8856_EXPOSURE_MIN` (`6`) to `VTS - OV8856_EXPOSURE_MAX_MARGIN` (`VTS - 6`). (`ov8856.c` L55–58, L1850–1854) |
| `0x3503` | — (set to `0x08` in all mode tables) | Manual AEC/AGC and real-gain mode (`0x08` in `OV8856_INIT_REGS` and `ov8856.c` L224, L416). |
| `0x3508`–`0x3509` | `OV8856_REG_ANALOG_GAIN` (`0x3508`, 16-bit BE) | Real analogue gain: `128` (`0x0080`) = `1.0x`, `OV8856_ANAL_GAIN_MIN` = `128`, `OV8856_ANAL_GAIN_MAX` = `2047` (`~15.99x`). `OV8856_INIT_REGS` sets `0x0180` (`3.0x`). (`ov8856.c` L61–64, L1842–1843) |
| `0x350A`–`0x350B` | `OV8856_REG_DIGITAL_GAIN` (`0x350a`, 16-bit BE) | Digital gain: `OV8856_DGTL_GAIN_DEFAULT` = `1024` (`0x0400` = `1.0x`), range `0`..`4095` (`~4.0x`). (`ov8856.c` L67, L71–74, L1715–1719) |
| `0x380C`–`0x380D` | `OV8856_REG_HTS` (`0x380c`, 16-bit BE) | Horizontal total size in pixels (`0x078C` = `1932` in `OV8856_VGA_REGS`). (`ov8856.c` L52) |
| `0x380E`–`0x380F` | `OV8856_REG_VTS` (`0x380e`, 16-bit BE) | Vertical total size in lines (`0x026C` = `620` in `OV8856_VGA_REGS`; max `OV8856_VTS_MAX` = `0x7fff`). (`ov8856.c` L48–49) |
| `0x3813` | `bayer_offset_configs` (`mipi_data_mbus_*`) | ISP Y window offset; `0x02` selects `MEDIA_BUS_FMT_SBGGR10_1X10` (`bggr`), `0x01` shifts by 1 line for `MEDIA_BUS_FMT_SGRBG10_1X10` (`grbg`). (`ov8856.c` L1385–1415) |
| `0x3820`, `0x376B`, `0x5001`, `0x502E` | `OV8856_REG_FORMAT1`, `OV8856_REG_FLIP_OPT_1..3` | VFLIP control (`ov8856_set_ctrl_vflip`): `vflip=1` sets `0x3820` bits `1,2,6` (`0x46`), `0x376B` bits `1,2` (`0x06`), `0x5001` bit `2` (`0x04`), and clears `0x502E` bits `0,1` (`0x03`); `vflip=0` is the inverse. (`ov8856.c` L86, L94–100, L1764–1816) |
| `0x3821`, `0x5004` | `OV8856_REG_FORMAT2`, `OV8856_REG_MIRROR_OPT_1` | HFLIP control (`ov8856_set_ctrl_hflip`): `hflip=1` clears `0x3821` bits `1,2,6` (`0x46`) and `0x5004` bit `2` (`0x04`); `hflip=0` sets them. (`ov8856.c` L87, L97, L101–102, L1731–1762) |
| `0x5E00`, `0x5000`, `0x5001` | `OV8856_REG_TEST_PATTERN` (`0x5e00`) | `0x00` = disabled; `0x80 \| ((mode - 1) << 2)` enables bar modes 1..4 (`OV8856_TEST_PATTERN_ENABLE = BIT(7)`, `OV8856_TEST_PATTERN_BAR_SHIFT = 2`); mode 1 = "Standard Color Bar" = 8 bars white, yellow, cyan, green, magenta, red, blue, black (mainline menu `ov8856_test_pattern_menu`). `ov-cap.py --testpat` uses mode 1 (`0x5E00 = 0x80`) and `ov-expo.py` maps `--testpat bars` to the same mode. Both also clear `0x5000` bit `5` (LENC) and `0x5001` bit `3` during test pattern and restore them when disabled. (`ov8856.c` L77–79, L1398–1404, L1721–1729) |

### 4.1 Default Bayer Order and Black Level

- **Default Bayer order (`bggr`)**: In `OV8856_INIT_REGS` / `OV8856_VGA_REGS` in `tools/camera/ov-cap.py`, `0x3820 = 0x90` (`vflip=0`), `0x3821 = 0x67` (`hflip=0`), `0x3811 = 0x08`, `0x3813 = 0x02`. Both the OV8856 datasheet native CFA array (`B G / G R`) and `ov8856.c` (`OV8856_MEDIA_BUS_FMT_SBGGR10_1X10` for `0x3813=0x02`, L1385–1387, L1573, L1588) correspond to `bggr`. (Note: the quincunx capture quirk of section 0 means the sample's bars do not exercise the full CFA; the phase naming above refers to stream coordinates.)
- **Default black level (`64` at 10-bit)**: OV8856's on-sensor BLC (`0x4000`–`0x400F` in `ov8856.c` and `OV8856_INIT_REGS`, e.g. `0x4009 = 0x05`, `0x4003 = 0x40`) targets a pedestal of `64` DN in 10-bit output (`16` DN at 8-bit).
