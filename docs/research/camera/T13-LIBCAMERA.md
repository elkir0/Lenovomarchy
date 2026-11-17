# T13: libcamera on top of the new MT6785 capture driver (research and packaging)

> Correction, 2026-11-17: the media device driver name is cut to 15
> characters, so `mtk-mt6785-seninf` below never matched. The kernel now
> sets `mt6785-cam` and the patch lists it; built and run on the tablet,
> see `docs/hardware/CAMERA.md` "libcamera".

State at the time of writing: the tablet has a working V4L2 media-controller
pipeline `ov8856 2-0036` -> `mtk-mt6785-seninf` -> `mtk-mt6785-camsv` ->
`mtk-mt6785-camsv video` (`/dev/video0`), and `v4l2-ctl` streams 640x480
10-bit Bayer frames (docs/research/camera/T8-V4L2.md, [T3-UPSTREAM.md §3](T3-UPSTREAM.md)).
**Update 2026-11-17 (T15): the layout quirk below is fixed in the kernel** —
the CAMSV driver now defaults to FMT_SEL 0x102 / PAK 5 / 2 bytes per pixel
and advertises only the unpacked `V4L2_PIX_FMT_S*10` fourccs, so §2's
recommendation (a1) is implemented and this document's earlier "le10 exposed
as S*10P" caveat is history (kept for the record). The original quirk, for
reference: with `FMT_SEL` 0x514 = 0x102, `PAK` 0x54c = 1 and the line sized
for 10 bits, each line was a continuous little-endian 10-bit bit stream
(pixel k in bits 10k..10k+9) — the same size as MIPI RAW10, but not its
byte layout — exposed (wrongly) as the V4L2 `S*10P` fourccs.

This document covers: how the `simple` pipeline handler decides it supports
a device (§1), what the software ISP's debayer accepts and what to do about
our packing (§2), what the sensor needs on the libcamera side (§3), how Arch
Linux ARM packages libcamera and how PipeWire picks the cameras up (§4), and
the kernel-side checklist for the driver's author (§5).

All libcamera source references are to tag **v0.7.2**, the version Arch
Linux ARM ships today (2026-11-17). The upstream repository is
[git.libcamera.org/libcamera/libcamera](https://git.libcamera.org/libcamera/libcamera.git);
raw files are served by the freedesktop mirror, e.g.
[simple.cpp at v0.7.2](https://gitlab.freedesktop.org/camera/libcamera/-/blob/v0.7.2/src/libcamera/pipeline/simple/simple.cpp).

## 1. How `SimplePipelineHandler` decides it supports a device

### 1.1 The match on the media device driver name

The `simple` pipeline handler does not probe hardware generically. Its
`match()` walks an explicit allow-list, `supportedDevices[]` in
`src/libcamera/pipeline/simple/simple.cpp` (v0.7.2, lines 258-268):

```cpp
static const SimplePipelineInfo supportedDevices[] = {
	{ "dcmipp", {}, false },
	{ "imx7-csi", { { "pxp", 1 } }, true },
	{ "intel-ipu6", {}, true },
	{ "intel-ipu7", {}, true },
	{ "j721e-csi2rx", {}, true },
	{ "mtk-seninf", { { "mtk-mdp", 3 } }, false },
	{ "mxc-isi", {}, false },
	{ "qcom-camss", {}, true },
	{ "sun6i-csi", {}, false },
};
```

([simple.cpp](https://gitlab.freedesktop.org/camera/libcamera/-/blob/v0.7.2/src/libcamera/pipeline/simple/simple.cpp),
`SimplePipelineHandler::match()` at line ~2029: for each entry it builds a
`DeviceMatch(inf.driver)` and calls `acquireMediaDevice()`.)

`DeviceMatch` compares the string against the **media device driver name**,
i.e. the `driver` field of `struct media_device_info` returned by
`MEDIA_IOC_DEVICE_INFO` — `DeviceMatch::match()` in
[src/libcamera/device_enumerator.cpp](https://gitlab.freedesktop.org/camera/libcamera/-/blob/v0.7.2/src/libcamera/device_enumerator.cpp)
line 104-107 (`if (driver_ != device->driver()) return false;`).

On the kernel side that field is filled by `media_device_get_info()`
(drivers/media/mc/mc-device.c:64-68): it uses
`media_device.driver_name` when set, otherwise **falls back to
`dev->driver->name`** — the platform driver's name. Our SENINF driver never
sets `driver_name` (checked: no assignment in
[src/mt6785-mainline/drivers/media/platform/mediatek/mt6785-cam/mt6785-seninf.c](../../../src/mt6785-mainline/drivers/media/platform/mediatek/mt6785-cam/mt6785-seninf.c)),
and its platform driver is `.name = "mtk-mt6785-seninf"` (line 1172), so
the media device driver name userspace sees is exactly
**`mtk-mt6785-seninf`** — the `model` string (`"mtk-mt6785-cam"`) is
irrelevant for matching.

That means the entry this driver needs is:

```cpp
{ "mtk-mt6785-seninf", {}, true },
```

- The empty converter list `{}`: we have no `mtk-mdp`-style m2m converter
  in the graph, and a converter would forbid the software ISP anyway.
- The `true` is `swIspEnabled` — see §1.2.

Note the existing `mtk-seninf` entry is for the BayLibre MT8365 driver
(that driver's platform `.name` is `"mtk-seninf"`, see
[mtk_seninf.c](../../../src/begonia-ftp/camera/ref/isp30/src/mtk_seninf.c)
line 1442) with `swIspEnabled = false` because MT8365 boards pair the
receiver with an AP1302 YUV ISP or the mdp converter; it does not match our
device and must not be modified (it would break MT8365 boards). The two
entries coexist fine since the names differ.

### 1.2 Whether the software ISP is used

`SimplePipelineInfo` has three fields: `driver`,
`converters` (a list of `(media driver name, number of streams)` pairs for
m2m converters), and `swIspEnabled`. In
`SimplePipelineHandler::matchDevice()` (simple.cpp v0.7.2, line ~1868):

- For each converter name it tries to acquire that media device; if found,
  `numStreams` comes from the converter entry. **A converter and the
  software ISP are mutually exclusive** (`ASSERT(!converter_)` when
  `swIspEnabled`).
- `if (info.swIspEnabled) ... numStreams = 2;` — with the software ISP the
  camera exposes **two streams**: the debayered processed stream (RGB888,
  XRGB8888, ...) plus a raw stream (the sensor's Bayer output).
- The `SoftwareIsp` object itself is created in
  `SimpleCameraData::init()` (line ~617) only when
  `!converter_ && pipe->swIspEnabled()`.

So for this tablet: no converter in the graph, entry with
`swIspEnabled = true`, software ISP in use, two streams per camera.

### 1.3 The runtime override (no rebuild needed to flip the flag)

Since v0.6, `matchDevice()` also reads
`pipelines.simple.supported_devices` from the global configuration file
(`/etc/libcamera/configuration.yaml` or
`$XDG_CONFIG_HOME/libcamera/configuration.yaml`;
[src/libcamera/global_configuration.cpp](https://gitlab.freedesktop.org/camera/libcamera/-/blob/v0.7.2/src/libcamera/global_configuration.cpp)
line 30-31) and lets a `software_isp: true/false` flag override
`swIspEnabled` for a listed driver:

```yaml
pipelines:
  simple:
    supported_devices:
      - driver: mtk-mt6785-seninf
        software_isp: true
```

This only works for a driver **already in the table**, so the patch in
`image/camera/libcamera-yt11/` is still required; but the config file is
the cheap way to toggle the flag while experimenting (both directions).

### 1.4 What else `matchDevice()` needs from the graph

After the name match, `matchDevice()` → `locateSensors()` → per-sensor BFS
(simple.cpp line ~476-530) walks source pads looking for an entity with
`function == MEDIA_ENT_F_IO_V4L`, and `SimpleCameraData::init()`:

1. opens every entity in the path — subdevs need
   `V4L2_SUBDEV_FL_HAS_DEVNODE` (our seninf/camsv set it),
2. runs `setupFormats()` with `VIDIOC_SUBDEV_S_FMT`/`G_FMT` along the whole
   chain — every subdev pad must support the format API (ours do; the
   drivers' coherent SBGGR10_1X10/640x480 defaults make this a no-op),
3. enumerates the video node's pixel formats filtered by the negotiated
   media bus code via `VIDIOC_ENUM_FMT` with `mbus_code` set (the video
   node must have `V4L2_CAP_IO_MC`, ours does — mt6785-camsv.c line 950)
   and frame sizes via `VIDIOC_ENUM_FRAMESIZES` (continuous 16x16 to
   4624x4032, which `V4L2VideoDevice::enumSizes()` maps to a SizeRange —
   present),
4. instantiates the sensor with `CameraSensorFactoryBase::create()` (§3).

The graph is exactly what T8 built: sensor -> seninf -> camsv subdev ->
video node, all links enabled. No changes needed here.

## 2. Formats: what the debayer accepts, and what was done about our le10 packing

**Resolved 2026-11-17 (T15):** the sweep found the register combination
(§2.2 a1 candidates: `FMT_SEL` 0x102 with `PAK` 5 — PAK 1 plus bit 2, the
ISP 3.0 `PAK_DBL_MODE_2_PIXELS` flag — and the line sized for two bytes per
pixel; docs/hardware/CAMERA.md "Standard 16-bit layout and autofocus
actuator"). The mt6785-camsv driver now writes those values by default and
advertises only `V4L2_PIX_FMT_SBGGR10`/`SGBRG10`/`SGRBG10`/`SRGGB10`
(bytesperline = width * 2, sizeimage = bpl * height, colorspace raw,
ENUM_FMT honouring the mbus_code filter, discrete frame sizes from the
active sensor's modes with a continuous-range fallback). The `fmt_sel`,
`pak` and `bytes_per_px_x8` module parameters remain for experiments and
log a warning at STREAMON whenever they override the default. §2.3 (patch
libcamera) is therefore not needed. The text below is the original
analysis.

### 2.1 Accepted input formats of the software ISP today (v0.7.2)

`DebayerCpu::getInputConfig()` in
[src/libcamera/software_isp/debayer_cpu.cpp](https://gitlab.freedesktop.org/camera/libcamera/-/blob/v0.7.2/src/libcamera/software_isp/debayer_cpu.cpp)
(line 431-476) accepts exactly:

| Family | Pixel formats | Storage |
|---|---|---|
| 8-bit unpacked | `SBGGR8`, `SGBRG8`, `SGRBG8`, `SRGGB8` | 1 byte/px |
| 10-bit unpacked | `SBGGR10`, `SGBRG10`, `SGRBG10`, `SRGGB10` | **2 bytes/px, 16-bit LE container** |
| 12-bit unpacked | `SBGGR12`, ... | 2 bytes/px |
| 10-bit MIPI CSI-2 packed | `SBGGR10P` (`S*10_CSI2P`), ... | 4 px / 5 bytes: four MSB bytes then one LSB byte |
| 12-bit MIPI CSI-2 packed | `SBGGR12P`, ... | 2 px / 3 bytes |

plus the same 8/10/12-unpacked and 10P/12P families in the GPU path
`DebayerEGL` (`debayer_egl.cpp` line 66-90, GLSL sampler does the
unpacking) and in `SwStatsCpu` (`swstats_cpu.cpp::configure()`, line
~477-530). `BayerFormat::Packing` distinguishes `None` / `CSI2` / `IPU3` /
`PISP1` / `PISP2` ([bayer_format.cpp](https://gitlab.freedesktop.org/camera/libcamera/-/blob/v0.7.2/src/libcamera/bayer_format.cpp));
the `IPU3`/`PISP` packings are handled by dedicated pixel formats, not by
the generic debayer.

**None of these is our le10 layout.** The packed-CSI2 10-bit family
(`debayer10P_*`, e.g. `debayer10P_BGBG_BGR888`) assumes the MIPI layout:
the macro walks `width * 5 / 4` bytes and every 5th byte carries the 2 LSBs
of the previous 4 samples. Feeding it our le10 lines produces subtly wrong
pixel values everywhere except the first sample of each 4-px group —
`raw2rgb.py --layout raw10` vs `--layout le10` on the same samples shows
the difference (T9-RAWTOOLS.md §0: same bytes/line, different bit order).

### 2.2 Option (a): change the kernel driver's packer to a supported layout

Two candidate targets:

**(a1) 16-bit unpacked (`V4L2_PIX_FMT_SBGGR10` etc., 2 bytes/px).** This is
what the debayer's `Packing::None` 10-bit path expects
(`DECLARE_SRC_POINTERS(uint16_t)`, value >> 2 into 8 bits —
`debayer10_BGBG_BGR888` divides by 4, i.e. it reads the 10-bit sample in
the low bits of each 16-bit LE halfword).

Hardware evidence this is reachable on MT6785 CAMSV:

- The MT8365 ISP 3.0 reference driver we modeled on **advertises the
  unpacked fourcc** in its format table:
  [mtk_camsv_video.c](../../../src/begonia-ftp/camera/ref/isp30/src/mtk_camsv_video.c)
  lists `V4L2_PIX_FMT_SBGGR10` (in V4L2 that fourcc *means* 16-bit
  unpacked storage, 2 bytes/px) for `MEDIA_BUS_FMT_SBGGR10_1X10`, and
  for every raw entry
  [mtk_camsv_hw.c](../../../src/begonia-ftp/camera/ref/isp30/src/mtk_camsv_hw.c)
  writes `CAMSV_IMGO_SV_STRIDE = fmtinfo->imgo_stride | bpl` where
  `imgo_stride = CAMSV_IMGO_SV_STRIDE_BUS_SIZE_EN |
  CAMSV_IMGO_SV_STRIDE_BUS_SIZE_32` — the **"bus size" field of the
  STRIDE register** (bits 16-19: `BUS_SIZE_16` = BIT(16) alone selects
  2-byte containers, `BUS_SIZE_32` = GENMASK(17,16) selects 4-byte,
  `BUS_SIZE_EN` = BIT(19) gates the field;
  [mtk_camsv_reg.h](../../../src/begonia-ftp/camera/ref/isp30/src/mtk_camsv_reg.h)
  line 50-53). The bus size controls the write-side container
  independently of the sample's bit depth.
  Caveat carried over from T3 §3.1 item 3: the same reference computes
  `bpl = ALIGN(DIV_ROUND_UP(width * bpp, 8), 2)` — a *packed* stride —
  while advertising the unpacked fourcc, which is internally
  inconsistent (a genuine `SBGGR10` frame needs `width * 2`). Whether
  MT8365 actually produces 2-byte containers with those settings or the
  table entry is simply wrong/unused was never verified on that board.
  The YUV entries in the same table pair
  `CAMSV_FMT_SEL_IMGO_BUS_SIZE_16` (BIT(24) of FMT_SEL) with
  `BUS_SIZE_16` in STRIDE — so ISP 3.0 silicon has **two** container
  knobs: a bus-size field in `FMT_SEL` and one in `IMGO_STRIDE`.
- On our MT6785 CAMSV the registers moved to `FMT_SEL` 0x514 and
  `PAK` 0x54c, and `IMGO_STRIDE` 0x38 with the documented hazard that
  bit 24 there packs two lines into one (NOT the bus size — T8 §2.2).
  The measured `FMT_SEL = 0x102` decodes as TG1_FMT=2, and bit 8 (0x100)
  is set in both 0x101 and 0x102; the ISP 3.0 header places
  `IMGO_BUS_SIZE_16` at BIT(24), far from the low byte we have swept.
  The le10 result (PAK=1, FMT_SEL=0x102) and the p12 result
  (PAK=2, FMT_SEL=0x101) show the low `TG1_FMT` field and `PAK` mode
  trade packing group sizes; the un-swept combinations are:
  - `FMT_SEL` bit 24 (`IMGO_BUS_SIZE_16`) on top of TG1_FMT RAW10 —
    plausibly "write each 10-bit sample in a 16-bit container";
  - `PAK` = 0 (mode RAW14 field value 0 is RAW14, but with PAK_EN
    cleared in MODULE_EN bit 2 the packer may be bypassed entirely —
    MODULE_EN 0x40000015 currently keeps PAK_EN set);
  - the STRIDE bus-size bits of ISP 3.0 may exist at MT6785's
    `IMGO_CON2/CON3` (0x40/0x44, both 0x20002 today) instead — the
    begonia NOTES.md flagged those as "FIFO/burst" unknowns
    (NOTES.md line 278).

  Each candidate needs a one-line experiment in `tools/camera/ov-cap.py`
  (a new `--layout u16` writing those register values and
  `bpl = width * 2`) and a capture to check. The acceptance test is
  trivial: `raw2rgb.py --layout raw16` (or a 10-line decoder: every LE
  u16 is a sample) decodes the bars cleanly at 1280 B/line.

**(a2) MIPI CSI-2 packed 10-bit (`V4L2_PIX_FMT_SBGGR10P`).** The PAK modes
we have measured (PAK=1 with FMT_SEL=0x102 gives le10; PAK=2 with
FMT_SEL=0x101 gives 12-bit containers) do not include the MIPI byte
layout, and nothing in the ISP 3.0 reference suggests the packer can
reorder bytes per-MIPI (it packs pixel streams, not CSI-2 payloads). So
(a2) looks unreachable in hardware.

### 2.3 Option (b): patch libcamera with a new unpacker

Add a `BayerFormat::Packing`-style case for le10 in `debayer_cpu.cpp`
(a `debayer10LE_*` sibling of `debayer10P_*` reading 4 samples from a
5-byte LE integer, ~30 lines), plus `swstats_cpu.cpp` equivalents, plus a
new `PixelFormat`/V4L2 fourcc mapping in `bayer_format.cpp` /
`formats.yaml` / the V4L2 pixel format table — and then either a new
kernel-side fourcc or keep lying with `S*10P` and special-casing the
driver name in libcamera. Upstreaming that to libcamera is a non-starter:
the layout is not a standard, and the project has spent years *removing*
per-driver format hacks; it would also need `DebayerEGL` GLSL and
`SwStatsCpu` variants to keep the GPU path working.

### 2.4 Recommendation

**Option (a1): make the kernel driver write 16-bit-unpacked Bayer
(`V4L2_PIX_FMT_S*10`), by finding the CAMSV mode that puts each sample in
a 2-byte container.**

Reasons:

1. **It is the only end state that upstream libcamera accepts without a
   custom format.** Both debayers (CPU and EGL) and the statistics code
   already implement `Packing::None` 10-bit; nothing new is needed in
   userspace, for us or for anyone else who ever mainlines an MT6785
   camera.
2. **The hardware plausibly can do it.** The ISP 3.0 sibling of this
   exact CAMSV IP has explicit "bus size" container programming in
   STRIDE/FMT_SEL, and the MT6785 register map has the same registers at
   shifted offsets. The 12-bit-container behaviour we measured (`p12`)
   already proves the write-side container width is programmable
   independently of the 10-bit sample size on this silicon. A short
   register sweep settles it either way.
3. **Cost is bounded and one-sided.** If no combination yields 2-byte
   containers, we have lost an afternoon of experiments and fall back to
   (b) — the le10 layout stays correct for `tools/camera/` either way.
   The reverse order (patch libcamera first, fix the kernel later) means
   maintaining an out-of-tree libcamera fork and re-doing the userspace
   work when the kernel is fixed anyway.
4. **Bandwidth is acceptable.** 640x480x2 B = 614 kB/frame at 120 fps
   mode ≈ 74 MB/s, and 1632x1224 at 30 fps ≈ 120 MB/s — well within the
   DMA and DRAM budget; le10's 25 % saving is not worth a custom format.

Interim step while (a1) is being tested: the `S*10P` exposure lets
`cam -l` and pipeline configuration work today; frames will be garbled
through the software ISP (it will decode them as MIPI-packed), which is
still useful to validate the control path, the IPA and PipeWire plumbing.

### 2.5 What the driver must NOT do

- Do not keep the current `S*10P`-means-le10 exposure once 16-bit works:
  report `V4L2_PIX_FMT_SBGGR10` (etc.) with `bytesperline = width * 2`
  and the matching `MEDIA_BUS_FMT_S*10_1X10` on the pads.
- The 12-bit-container `p12` mode (FMT_SEL=0x101/PAK=2) is NOT
  `V4L2_PIX_FMT_SBGGR12`: the samples are 10-bit shifted left by 2 with
  no way to express that shift in the fourcc. Do not expose it as a
  12-bit format.

## 3. What the sensor needs on the libcamera side

### 3.1 Sensor class selection and its requirements

`SimpleCameraData::init()` calls `CameraSensorFactoryBase::create()`
(simple.cpp line 564). At v0.7.2 two classes are registered:

- `CameraSensorRaw` (priority 0,
  [camera_sensor_raw.cpp](https://gitlab.freedesktop.org/camera/libcamera/-/blob/v0.7.2/src/libcamera/sensor/camera_sensor_raw.cpp),
  `REGISTER_CAMERA_SENSOR(CameraSensorRaw, 0)` line 1162): for the new
  streams-API sensor drivers. Its `match()` requires 1-2 pads flagged
  `MEDIA_PAD_FL_SINK | MEDIA_PAD_FL_INTERNAL` plus exactly one source
  pad (line 190-219), and `init()` then enumerates
  `VIDIOC_SUBDEV_G_ROUTING` routes. The mainline ov8856 driver has a
  single source pad and no routing
  ([ov8856.c](../../../src/mt6785-mainline/drivers/media/i2c/ov8856.c)
  line 3252: `ov8856->pad.flags = MEDIA_PAD_FL_SOURCE`, pad ops at
  3059-3067 with only set_fmt/get_fmt/enum), so `match()` returns 0
  ("not mine") and the factory falls through to the legacy class.
- `CameraSensorLegacy` (priority -100,
  [camera_sensor_legacy.cpp](https://gitlab.freedesktop.org/camera/libcamera/-/blob/v0.7.2/src/libcamera/sensor/camera_sensor_legacy.cpp),
  line 1048): the pre-streams-API path, which is what a classic
  single-pad sensor like our ov8856 gets. Its
  `validateSensorDriver()`:

  - **Mandatory (hard fail, `return -EINVAL`)**: `V4L2_CID_ANALOGUE_GAIN`,
    `V4L2_CID_EXPOSURE`, `V4L2_CID_HBLANK`, `V4L2_CID_PIXEL_RATE`,
    `V4L2_CID_VBLANK` (line 440-467). The mainline ov8856 driver
    registers all five (plus DIGITAL_GAIN, TEST_PATTERN, HFLIP, VFLIP,
    LINK_FREQ) — **compliant**.
  - **Recommended (warning + err, but init continues: the error from the
    selection targets is *not* propagated — see the code path at line
    425-436 where `err` only logs)**: `V4L2_CID_CAMERA_ORIENTATION`
    (from the DT `orientation` property, registered by the driver via
    `v4l2_ctrl_new_fwnode_properties` — ov8856.c line 2774 calls it, so
    adding `orientation = <0>` (or 1/2) to the DT node exposes it);
    optional: `V4L2_CID_CAMERA_SENSOR_ROTATION` (DT `rotation`).
    Missing orientation means libcamera logs
    "Recommended V4L2 control ... not supported" and the
    `Location` property falls back to a default.
  - **Selection targets** (`V4L2_SEL_TGT_CROP_BOUNDS/DEFAULT/CROP`):
    same treatment — warnings and defaults (`pixelArraySize_` defaults
    to the largest mode, `activeArea_` to the full array;
    `sensorInfo()` then defaults `analogCrop` to the active area). The
    ov8856 driver implements **no** selection ops, so these warnings
    will appear; harmless for the soft IPA (it uses the defaults), but
    worth fixing in the driver for correct `PixelArraySize` /
    `PixelArrayActiveAreas` properties. (The libcamera sensor
    requirements doc:
    [sensor_driver_requirements.rst](https://gitlab.freedesktop.org/camera/libcamera/-/blob/v0.7.2/Documentation/sensor_driver_requirements.rst).)

  So the ov8856 lands in `CameraSensorLegacy` and passes.

### 3.2 Camera sensor helper for ov8856 — not present, and mostly fine

The analogue-gain model and black level come from
`CameraSensorHelperFactoryBase::create(sensorModel)` in the IPA
([src/ipa/libipa/camera_sensor_helper.cpp](https://gitlab.freedesktop.org/camera/libcamera/-/blob/v0.7.2/src/ipa/libipa/camera_sensor_helper.cpp)):
40+ sensors registered via `REGISTER_CAMERA_SENSOR_HELPER`, and
**`ov8856` is not among them** (checked at v0.7.2: `ov01a10`, `ov08x40`,
`ov2685`, `ov2740`, `ov4689`, `ov5640`, ..., `ov8858`, `ov8865`,
`ov13858`, ...). The consequences in `IPASoftSimple`:

- `init()` only warns ("Failed to create camera sensor helper for
  ov8856") and continues (soft_simple.cpp line 102-106).
- AGC then treats the raw V4L2 control value as the gain directly
  (`frameContext.sensor.gain = again` without conversion, line 307) and
  uses `againMin/Max/Def` as-is. The ov8856 gain register (0x3508,
  16-bit, range 128-2047 per the driver constants OV8856_ANAL_GAIN_MIN/
  MAX) is a linear code where gain ≈ code/128, i.e. 1x-16x — so AGC
  still converges, just with a coarse gain grid (steps of 1/128 = 0.8 %).
- Black level is left to the soft IPA's `Blc` algorithm, which
  auto-guesses it from the histogram (and can be pinned via the tuning
  file — §3.4).

The neighbouring OmniVision helpers all use
`AnalogueGainLinear{ 1, 0, 0, 128 }` (ov8858, ov5670, ov5675, ov64a40,
...) with `blackLevel_` where known — an upstream-quality `ov8856` entry
would be ~8 lines:

```cpp
class CameraSensorHelperOv8856 : public CameraSensorHelper
{
public:
	CameraSensorHelperOv8856()
	{
		/* From datasheet: 0x40 at 10 bits. */
		blackLevel_ = 4096; /* 64 << 6: 16-bit scale, TO CONFIRM */
		gain_ = AnalogueGainLinear{ 1, 0, 0, 128 };
	}
};
REGISTER_CAMERA_SENSOR_HELPER("ov8856", CameraSensorHelperOv8856)
```

Worth upstreaming later; NOT required for first light. (The black-level
scaling must be verified against the OV8856 datasheet before submitting —
the helpers store it on a 16-bit scale and the scene measurements in
CAMERA.md put it near 64/1023 at 10 bits; the ov5675 entry uses 4096 for
its "0x40 at 10 bits".)

### 3.3 Static sensor properties — not present either

[CameraSensorProperties::get()](https://gitlab.freedesktop.org/camera/libcamera/-/blob/v0.7.2/src/libcamera/sensor/camera_sensor_properties.cpp)
holds unit cell size, test-pattern mode mapping and sensor delays;
`ov8856` is absent (its neighbours `ov8858` and `ov8865` are present).
Missing entries mean:

- `unitCellSize` is unknown → the `UnitCellSize` property is not set
  (only used by IPA modules that compute an optical grid; the soft IPA
  does not).
- `testPatternModes` mapping unknown → `initTestPatternModes()` returns
  early: the `TestPatternMode` control is simply not offered
  (camera_sensor_legacy.cpp line 507-528). The V4L2
  `test_pattern` control remains directly settable with `v4l2-ctl`,
  which is how the bars were captured so far — good enough.
- `sensorDelays` fall back to the unverified defaults (exposure 2,
  gain 1, vblank/hblank 2 — the legacy class's `defaultSensorDelays`,
  camera_sensor_legacy.cpp line 490-495), used by `DelayedControls` for
  the AGC loop (simple.cpp line 568-573). The OV8856's real exposure
  delay is ~2 frames, so the defaults are plausible.

Again: an `ov8856` properties entry is a nice-to-have for upstream, not a
blocker.

### 3.4 Tuning file for the software ISP

`SoftwareIsp` loads the IPA tuning file as
`<sensor model>.yaml` with fallback to `uncalibrated.yaml`
(software_isp.cpp line 149-151;
[src/ipa/simple/data/uncalibrated.yaml](https://gitlab.freedesktop.org/camera/libcamera/-/blob/v0.7.2/src/ipa/simple/data/uncalibrated.yaml)).
Search paths: `$LIBCAMERA_SYSCONF_DIR/ipa/simple/` then
`$LIBCAMERA_DATA_DIR/ipa/simple/` (`IPA_CONFIG_DIR`, built from
`libcamera_sysconfdir`/`libcamera_datadir`,
[src/ipa/meson.build](https://gitlab.freedesktop.org/camera/libcamera/-/blob/v0.7.2/src/ipa/meson.build)
line 8-13) — on Arch that is `/etc/libcamera/ipa/simple/` and
`/usr/share/libcamera/ipa/simple/`.

The fallback `uncalibrated.yaml` (ships with the package, installed by the
`libcamera-ipa` split package) enables BlackLevel, Awb (grey world),
Adjust and Agc, and leaves Ccm commented out. That is enough for first
light. A tuned `/usr/share/libcamera/ipa/simple/ov8856.yaml` can later add
the CCM matrices and a measured black level.

**One wrinkle worth knowing:** without a sensor helper the IPA's BlackLevel
algorithm starts from its default (16 at 8-bit scale) and then
**auto-guesses** the level from each frame's Y histogram
([blc.cpp](https://gitlab.freedesktop.org/camera/libcamera/-/blob/v0.7.2/src/ipa/simple/algorithms/blc.cpp):
`process()` walks the low bins until 2 % of pixels are covered). So black
level works out of the box; a tuned `ov8856.yaml` can pin it instead —
the algorithm's `init()` reads a `blackLevel` integer (16-bit scale,
shifted >> 8 internally) from its tuning node:

```yaml
algorithms:
  - BlackLevel:
      blackLevel: 4096   # 64 at 10 bits -> 16 at 8 bits -> 16 << 8
```

which stops the per-frame re-estimation.

### 3.5 Required controls on the subdev (summary)

| Control | ov8856 driver | Needed by |
|---|---|---|
| `V4L2_CID_EXPOSURE` | yes (lines, 4 LSB fractional << 4) | IPASoftSimple AGC — **mandatory**, init fails without it |
| `V4L2_CID_ANALOGUE_GAIN` | yes (128-2047) | IPASoftSimple AGC — **mandatory** |
| `V4L2_CID_PIXEL_RATE` | yes | CameraSensor — **mandatory**; line duration = minLineLength/pixelRate |
| `V4L2_CID_HBLANK` | yes (read-only per mode) | CameraSensor — **mandatory**; libcamera sets it to min at init (harmless: driver marks read-only, the class skips read-only ctrl sets, camera_sensor_legacy.cpp line 288-292) |
| `V4L2_CID_VBLANK` | yes | CameraSensor — **mandatory**; frame-rate control |
| `V4L2_CID_LINK_FREQ` | yes | read-only info used by pixel-rate validation |
| `V4L2_CID_TEST_PATTERN` | yes (5-entry menu) | optional; without properties entry libcamera does not expose it as TestPatternMode |
| `V4L2_CID_HFLIP`/`VFLIP` | yes | optional; flips → Bayer order handling (`V4L2_CTRL_FLAG_MODIFY_LAYOUT` flags must be set correctly if flips swap the pattern) |
| `V4L2_CID_CAMERA_ORIENTATION` | via DT `orientation` | recommended (warning if absent) |
| `V4L2_CID_CAMERA_SENSOR_ROTATION` | via DT `rotation` | optional |

**DT action for this board**: add `orientation` to the `ov8856` node in
`mt6785-lenovo-yt-j706f.dts` (cam0 is the rear camera:
`orientation = <1>`; V4L2 constants: 0 = front, 1 = back, 2 = external),
and once the physical mounting vs. sensor scan direction is known,
`rotation = <n>` (the Yoga Tab 11's rear sensor is landscape-mounted;
expect 90 or 270 — verify with the test-pattern bars' orientation).
The mainline driver already parses both through
`v4l2_fwnode_device_parse` + `v4l2_ctrl_new_fwnode_properties`
(ov8856.c line 2769-2777); only the DT properties are missing. Without
them, applications get `Location` defaults and no rotation compensation
(qcam/Hyprland will show the image rotated).

## 4. Arch Linux ARM packaging and the PipeWire path

### 4.1 What Arch ARM ships

- **libcamera 0.7.2-4** (`extra/libcamera`, aarch64; package page:
  [archlinuxarm.org/packages/aarch64/libcamera](https://archlinuxarm.org/packages/aarch64/libcamera),
  build date 2026-09-01). Split packages: `libcamera`, `libcamera-docs`,
  `libcamera-ipa`, `libcamera-tools`, `gst-plugin-libcamera`,
  `python-libcamera`.
  PKGBUILD: [github.com/archlinuxarm/PKGBUILDs, extra/libcamera](https://github.com/archlinuxarm/PKGBUILDs/tree/master/extra/libcamera).
- **Pipelines enabled**: the ALARM PKGBUILD passes only
  `-D v4l2=enabled -D tracing=disabled -D test=true -D
  rpi-awb-nn=disabled` (plus the libpisp make-dependency, an ALARM
  addition) — `pipelines` is left at its default `auto`. libcamera's
  root meson.build maps `auto` per-arch through the `pipelines_support`
  table (`'simple': ['any']`, `'uvcvideo': ['any']`, `'virtual':
  ['any']`, `'imx8-isi'/'mali-c55'/'rkisp1'/'rpi/*': ['arm','aarch64']`,
  `'ipu3': ['x86','x86_64']`), so aarch64 builds get **all ARM pipelines
  plus `simple`**. In other words: **the stock ALARM libcamera already
  contains the simple pipeline handler**; what it lacks is our driver in
  `supportedDevices[]` — hence the rebuild in
  `image/camera/libcamera-yt11/`.
- **libcamera-tools 0.7.2-4** provides `cam`, `qcam`, `lc-compliance`,
  `libcamera-bug-report`; **libcamera-ipa** the signed IPA modules and
  tuning data (`/usr/share/libcamera/ipa/`, incl. `simple/uncalibrated.yaml`).
- **pipewire 1:1.6.11-1** and **wireplumber 0.5.19-1** (package pages
  [pipewire](https://archlinuxarm.org/packages/aarch64/pipewire),
  [wireplumber](https://archlinuxarm.org/packages/aarch64/wireplumber)).
  The `pipewire-libcamera` subpackage (ALARM PKGBUILD line 457-468)
  carries the SPA plugin `/usr/lib/spa-0.2/libcamera/libspa-libcamera.so`
  (built whenever libcamera headers are present — the ALARM pipewire
  PKGBUILD lists `libcamera` in makedepends and does not disable it).

### 4.2 How PipeWire picks up libcamera cameras

- PipeWire's SPA `libcamera` plugin
  ([spa/plugins/libcamera/](https://gitlab.freedesktop.org/pipewire/pipewire/-/tree/1.6.11/spa/plugins/libcamera))
  hosts a `libcamera-manager` + per-camera `libcamera-device` +
  `libcamera-source` nodes; it enumerates cameras through the normal
  `CameraManager`, so it sees exactly what the pipeline handlers find.
- WirePlumber's Lua monitor
  ([src/scripts/monitors/libcamera/](https://gitlab.freedesktop.org/pipewire/wireplumber/-/tree/0.5.19/src/scripts/monitors/libcamera))
  drives the `api.libcamera.enum.manager`: `enumerate-device.lua` →
  `create-device.lua` → `create-node.lua`, producing a VideoCapture
  source node per camera (node name `libcamera_input.<camera id>`).
  The monitor is part of WirePlumber's default `hardware.video-capture`
  component group (wireplumber.conf line 882-886: the virtual component
  providing `hardware.video-capture` wants `[ monitor.v4l2,
  monitor.libcamera ]`), so with `pipewire-libcamera` installed there is
  **no configuration to write**: restart the user services and
  `wpctl status` shows the camera under VideoCapture.
- Browsers: Firefox and Chromium (Wayland/Hyprland) enumerate camera
  devices through the desktop portal / PipeWire camera nodes, so a
  `libcamera_input.*` source appears in `getUserMedia` once WirePlumber
  creates it. XDG portal access rules (`wireplumber.conf.d.examples/
  libcamera.conf`) only matter for renaming/disabling nodes.

### 4.3 The rebuild package (deliverable 2)

`image/camera/libcamera-yt11/` contains the PKGBUILD (based on the ALARM
one, trimmed to `libcamera`/`libcamera-ipa`/`libcamera-tools`, building
only the `simple` pipeline and `simple` IPA), the patch, and a README
with build/test instructions. See that directory.

## 5. Kernel-side checklist for the driver's author

What libcamera (v0.7.2, simple + soft IPA, per the above) needs from the
kernel side, in rough priority order. Statuses below reflect the tree
after T15 (2026-11-17).

1. **[Done 2026-11-17] CAMSV output in a standard layout — 16-bit
   unpacked `V4L2_PIX_FMT_S*10`** (§2). The sweep found FMT_SEL 0x102 /
   PAK 5 / 2 bytes per pixel; the driver now writes those by default and
   advertises only the unpacked fourccs with `bytesperline = width * 2`,
   `sizeimage = bpl * height`. The override parameters remain
   (experiments) and log when used.
2. **[Done] Media device driver name** stays `mtk-mt6785-seninf`
   (the patch matches it). If the platform driver is ever renamed, the
   libcamera entry must follow. Setting `media_device.driver_name`
   explicitly is still open (cosmetic; not needed while the platform
   driver name matches).
3. **[Done] Graph/API basics**: `V4L2_SUBDEV_FL_HAS_DEVNODE` on both
   subdevs (present), `V4L2_CAP_IO_MC` on the video node (present),
   working `ENUM_FMT` (now honouring the `mbus_code` filter — the latent
   gap below is closed), `ENUM_FRAMESIZES` (now discrete sizes from the
   active sensor through the seninf's new `enum_frame_size`, continuous
   range fallback when no sensor is reachable), `S_FMT/G_FMT` on
   all pads, `link_validate`, colorspace raw on the node and pads.
   `get_selection` on the sensors stays open (see item 6).
4. **[Done] Sensor controls** — all five mandatory ones present on both
   sensors (ov8856: §3.5; s5k4h7: PIXEL_RATE, HBLANK, VBLANK, EXPOSURE,
   ANALOGUE_GAIN all registered). `V4L2_CID_EXPOSURE`'s range updates
   with the mode on both drivers.
5. **[Done] DT `orientation` + `rotation`** on both sensor nodes
   (cam0 OV8856: back, rotation 90; cam1 S5K4H7: front — assumed,
   rotation 270), marked provisional in the DTS comments. The
   `Location`/`Rotation` properties should now be right; verify against
   the real images and adjust.
6. **[Open, non-blocking] Selection targets on the sensors**: implement
   `get_selection` (CROP_BOUNDS = full pixel array, CROP_DEFAULT =
   active area, CROP = current mode's window) to silence the libcamera
   warnings and give correct `PixelArraySize` /
   `PixelArrayActiveAreas` properties. In the ov8856 mainline driver
   this is a `pad_ops` addition alongside set_fmt/get_fmt
   (ov8856.c line 3059); the data comes from each mode's
   `width`/`height` (the driver has no explicit crop-offset fields, so
   CROP would default to the mode size anchored at 0,0 until the mode
   tables gain offsets).
7. **[Done] Multi-buffer / continuous-streaming readiness**: the
   zero-copy per-frame IMGO_BASE_ADDR flow delivers buffers in order
   with `sequence` and a monotonic timestamp; the FBC compare value is
   kept ahead of the written count (T8 §0i), so no stall. 20 distinct
   frames at 640x480 and full-size modes verified by content on the
   tablet (CAMERA.md "Both cameras through V4L2").
8. **[Later] Buffer allocation**: the video node currently uses
   `vb2_dma_contig` (contiguous CMA, MMAP). libcamera's simple handler
   first tries `importBuffers()` (DMABUF) and falls back to
   `allocateBuffers()` (MMAP) when import is refused — so MMAP-only
   works today (that is the `v4l2-ctl` path); adding
   `vb2_dma_contig`'s DMABUF import (`->prepare`/`->map_dmabuf`) later
   lets the software ISP write its debayered output directly into the
   capture buffers if desired. The software ISP's own output buffers
   come from `/dev/dma_heap/system`, `/dev/dma_heap/linux,cma` or
   `/dev/udmabuf` (it tries in that order,
   software_isp.cpp line 85-87 + dma_buf_allocator.cpp line 48-51); the
   base config has `CONFIG_UDMABUF=y` but `CONFIG_DMABUF_HEAPS`
   **disabled** (kernel/configs/pmos-mt6785.config line 5855), so
   udmabuf serves first light — fine, but enabling
   `CONFIG_DMABUF_HEAPS=y` + `CONFIG_DMABUF_HEAPS_SYSTEM=y` later
   matches what libcamera prefers.
9. **[Partly done] The second sensor (S5K4H7)**: bound and capturing
   through CAMSV0 (CSI port 2, verified on hardware), DT orientation
   added, the seninf's one-enabled-link rule now switches the selection
   automatically when its link is enabled (so libcamera's own
   `setupLinks()` can select it without a disable-first dance). Its
   `CameraSensorProperties`/helper entries do not exist upstream
   (same pattern as §3.2/§3.3) — open, non-blocking (AGC treats the
   raw control value as the gain).
10. **[Done] No non-standard layout under a standard fourcc**: the
    driver advertises only the unpacked fourccs it actually writes; the
    le10 layout is reachable only through the override parameters,
    which log a warning. The 12-bit-container `p12` mode is not
    advertised.

---

### Appendix: source files consulted

- libcamera v0.7.2 (freedesktop GitLab mirror, raw files):
  `src/libcamera/pipeline/simple/simple.cpp` (supportedDevices 258-268,
  match 2026-2053, matchDevice 1868-2025, init 594-676, tryPipeline
  681-758, validate 1150-1260, start buffers 1640-1660),
  `src/libcamera/software_isp/software_isp.cpp` (constructor 82-160,
  DmaBufAllocator flags 85-87, tuning file 149-151),
  `src/libcamera/software_isp/debayer_cpu.cpp` (getInputConfig 431-476,
  setDebayerFunctions 529-640, debayer10/10P bodies 218-360),
  `src/libcamera/software_isp/swstats_cpu.cpp` (configure 467-530),
  `src/libcamera/software_isp/debayer_egl.cpp` (formats 58-100),
  `src/libcamera/bayer_format.cpp` (packing map 99-140),
  `src/libcamera/sensor/camera_sensor.cpp` (factory 453-485),
  `src/libcamera/sensor/camera_sensor_legacy.cpp` (init 176-299,
  validateSensorDriver 325-470, model 556-560),
  `src/libcamera/sensor/camera_sensor_raw.cpp` (match 173-231, init
  233-475), `src/libcamera/sensor/camera_sensor_properties.cpp`
  (table, ov8858 entry 459-473),
  `src/ipa/libipa/camera_sensor_helper.cpp` (helper table, ov8858 at
  794-808), `src/ipa/simple/soft_simple.cpp` (init 96-215, AGC
  223-250), `src/ipa/simple/data/uncalibrated.yaml`,
  `src/libcamera/device_enumerator.cpp` (DeviceMatch 44-150),
  `src/libcamera/media_device.cpp` (populate 210-220),
  `src/libcamera/v4l2_videodevice.cpp` (formats 1127-1175),
  `src/libcamera/v4l2_subdevice.cpp` (model 1703-1733, getRouting
  1539-1545), `src/libcamera/global_configuration.cpp` (paths 30-31),
  `src/libcamera/ipa_proxy.cpp` (configurationFile 174-199, config
  dirs 84-98), `src/libcamera/dma_buf_allocator.cpp` (provider table
  48-51), `meson_options.txt`, `meson.build` (pipelines 213-253),
  `src/ipa/meson.build`, `src/apps/cam/main.cpp` (options 124-177),
  `src/apps/cam/camera_session.cpp`,
  `Documentation/sensor_driver_requirements.rst`.
- PipeWire 1.6.11: `spa/plugins/libcamera/meson.build`,
  `spa/plugins/libcamera/libcamera-manager.cpp`.
- WirePlumber 0.5.19: `src/config/wireplumber.conf` (components
  552-582, 882-886), `src/config/wireplumber.conf.d.examples/libcamera.conf`,
  `src/scripts/monitors/libcamera/*`, `src/config/meson.build`.
- Arch Linux ARM: package pages
  ([libcamera](https://archlinuxarm.org/packages/aarch64/libcamera),
  [pipewire](https://archlinuxarm.org/packages/aarch64/pipewire),
  [wireplumber](https://archlinuxarm.org/packages/aarch64/wireplumber),
  [libcamera-tools](https://archlinuxarm.org/packages/aarch64/libcamera-tools)),
  PKGBUILDs from the [archlinuxarm/PKGBUILDs](https://github.com/archlinuxarm/PKGBUILDs)
  GitHub mirror (`extra/libcamera`, `extra/pipewire`).
- Local: docs/hardware/CAMERA.md, docs/research/camera/T8-V4L2.md,
  docs/research/camera/T9-RAWTOOLS.md, docs/research/camera/T3-UPSTREAM.md,
  tools/camera/ov-cap.py, `src/mt6785-mainline/drivers/media/platform/mediatek/mt6785-cam/`
  (mt6785-seninf.c, mt6785-camsv.c),
  `src/mt6785-mainline/drivers/media/i2c/ov8856.c`,
  `src/begonia-ftp/camera/ref/isp30/src/` (mtk_camsv_video.c,
  mtk_camsv_hw.c, mtk_camsv_reg.h, mtk_seninf.c).

## 6. Remaining work on the tablet (2026-11-17, after T15)

The kernel side is aligned (unpacked 10-bit fourccs, discrete frame
sizes, mbus_code-filtered ENUM_FMT, DT orientation/rotation, sensor
link auto-switch). What is left is install and look:

1. Build and install the kernel + modules from the T15 tree
   (`kernel/kbuild.sh`, then Image.gz + DTB + `modules.tar.xz` to the
   tablet as usual) and reboot.
2. Sanity: `v4l2-ctl -d /dev/video0 --list-formats` must show only
   `BG10/GB10/BA10/RG10` ("10-bit Bayer unpacked, 2 bytes per
   sample"); `tools/camera/v4l2-capture.sh -n 3 -t` must still capture
   (now decoding with `--layout u16` by default).
3. Build and install this package (`image/camera/libcamera-yt11/`,
   README §"Building on the tablet").
4. `cam -l` — expect `1: Internal back camera
   (/soc/i2c@11009000/camera-sensor@36)` (or the equivalent DT path)
   and no "Recommended V4L2 control not supported" warning.
5. `cam -c 1 --capture=5 --file=frame-#.ppm` — real pictures at
   640x480; the OV8856 colour bars make the check unambiguous. Then
   `qcam` and the PipeWire path (README §"Testing" items 3-4).
6. Judgement calls only possible with images: the DT `rotation` values
   (provisional), the S5K4H7's assumed front position, and the
   autofocus actuator question (CAMERA.md "Standard 16-bit layout and
   autofocus actuator").
