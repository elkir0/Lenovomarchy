# libcamera for the Yoga Tab 11 (MT6785 `mt6785-cam` + software ISP)

This directory rebuilds the Arch Linux ARM `libcamera` package (0.7.2-4,
`extra/libcamera`) with one change: a patch that adds this tablet's media
device driver name to the `simple` pipeline handler's supported-device
table, with the software ISP enabled. Full background, links and the
kernel-side checklist live in
`docs/research/camera/T13-LIBCAMERA.md` (task T13).

## Status

The kernel side is ready: since the 2026-11-17 layout change the CAMSV
driver's default (and only advertised) output is the **standard unpacked
10-bit Bayer layout** (`V4L2_PIX_FMT_S*10`, FMT_SEL 0x102 / PAK 5, two
bytes per pixel, sample in the low bits of a little-endian 16-bit word) —
exactly what libcamera's software ISP debayer reads natively
(docs/hardware/CAMERA.md "Standard 16-bit layout and autofocus actuator",
T13 §2 recommendation (a1), now implemented). No garbled-image caveat
anymore: once this package is installed, `cam`/`qcam`/PipeWire should
show real pictures.

## What the patch does

`libcamera-0.7.2-simple-mt6785.patch` adds one line to
`src/libcamera/pipeline/simple/simple.cpp` at tag `v0.7.2`:

```cpp
{ "mt6785-cam", {}, true },
```

That is the media device driver name our kernel reports (the SENINF
platform driver's `.driver.name`, used verbatim by `MEDIA_IOC_DEVICE_INFO`
when `media_device.driver_name` is unset — see T13 §1), with
`swIspEnabled = true` so the debayer/AEC pipeline runs on the CPU. The
entry must be sorted after `mtk-seninf` (the MT8365 name) and before
`mxc-isi`; the file's upstream URL is
https://gitlab.freedesktop.org/camera/libcamera/-/blob/v0.7.2/src/libcamera/pipeline/simple/simple.cpp.

The patch was generated from the real v0.7.2 `simple.cpp` fetched from
that URL and verified to apply with `patch -p1 --dry-run` against a
pristine copy of the upstream file.

### Sensor helpers and static properties (`libcamera-0.7.2-yt11-sensors.patch`)

`libcamera-0.7.2-yt11-sensors.patch` adds support for the tablet's two
10-bit sensors (`ov8856` rear, `s5k4h7` front) at tag `v0.7.2` so the
software ISP's auto-exposure/gain loop and `CameraSensorLegacy` stop
falling back to unscaled raw V4L2 gain codes and missing-property
defaults:

- `src/ipa/libipa/camera_sensor_helper.cpp`: adds
  `CameraSensorHelperOv8856` (`blackLevel_ = 4096` for 64 at 10 bits,
  `AnalogueGainLinear{ 1, 0, 0, 128 }` matching `OV8856_ANAL_GAIN_MIN`
  = 128 / 1x) and `CameraSensorHelperS5k4h7` (`blackLevel_ = 4096`,
  `AnalogueGainLinear{ 1, 0, 0, 32 }` matching `S5K4H7_AGAIN_MIN` = 32
  / 1x).
- `src/libcamera/sensor/camera_sensor_properties.cpp`: adds `ov8856` and
  `s5k4h7` static property entries with `unitCellSize = { 1120, 1120 }`
  nm, `testPatternModes` matching the kernel drivers'
  `V4L2_CID_TEST_PATTERN` menus, and `sensorDelays` (`{ 2, 2, 2, 2 }`).

### Auto-exposure tuning (`libcamera-0.7.2-yt11-agc.patch`, `ov8856.yaml`, `s5k4h7.yaml`)

The patch lets the soft IPA's tuning file set four `Agc` parameters
(`proportionalGain`, `maxStep`, `optimalExposure`, `deadband`); without
them the behaviour is the stock one. The two tuning files, installed in
`/usr/share/libcamera/ipa/simple/`, make the loop settle in 1 to 2 s
instead of about 15 s and aim lower (`optimalExposure: 1.6`), which
keeps the highlights. They hold no colour matrix: colours stay dull
until the sensors are characterized. Analysis in
`docs/research/camera/T18-LIBCAMERA-AGC.md`.

### Focus (`libcamera-0.7.2-yt11-lens.patch`, `libcamera-0.7.2-yt11-af.patch`)

The first patch makes the simple pipeline hand the sensor's focus lens
(the rear camera's DW9718S, through `CameraSensor::focusLens()`) to the
soft IPA, which exposes `LensPosition`: 0.0 is the far end of the
actuator's range and 1.0 the near end, linearly (no dioptre calibration
exists). The second adds a sharpness figure to the software ISP
statistics and an `Af` algorithm: `AfModeAuto` with `AfTrigger` runs a
coarse then a fine sweep and reports `AfState`; `AfModeContinuous`
starts a new sweep when sharpness stays low. `Af:` in the tuning file
takes `coarseStep`, `fineStep`, `settleFrames`, `retriggerRatio` and
`retriggerFrames`. A camera without a lens (the front one) gets none of
these controls. Design and limits:
`docs/research/camera/T19-LIBCAMERA-LENS.md`.

### Lens shading (`libcamera-0.7.2-yt11-lsc.patch`)

Both cameras show lens shading: the corners are darker and greener than
the centre. The patch adds an `Lsc` algorithm to the soft IPA. Each colour
channel of the raw values is multiplied, after black level subtraction
and before the white balance gains, the colour matrix and gamma, by a
radial gain:

```yaml
  - Lsc:
      centre: [ 0.5, 0.5 ]          # optical centre as a fraction of width, height (optional, default 0.5, 0.5)
      red:   [ k1, k2, k3 ]         # gain(r) = 1 + k1*r^2 + k2*r^4 + k3*r^6
      green: [ k1, k2, k3 ]
      blue:  [ k1, k2, k3 ]
```

`r` is the distance from the centre divided by half the frame diagonal,
with square pixels (r = 1 in a corner when the centre is 0.5, 0.5); the
centre fraction counts from the first column and row of the buffer. Each
gain is clamped to [1, 4]. A missing colour entry leaves that channel
uncorrected; without an `Lsc` entry the feature is off and the shaders do
not contain it. Only the GPU debayer applies the correction (the CPU
debayer logs a warning and ignores it), and the statistics, hence the
exposure and white balance loops, still see the uncorrected image. The
frame is the full debayered image at the sensor mode's aspect ratio:
when the requested output has another aspect ratio, the GPU debayer
crops it at the right or bottom and the correction stays on the optics,
so fit the coefficients on a capture with the native aspect ratio.

## Building on the tablet

Copy this directory to the tablet (it has no other repo dependencies)
and run, as a normal user with `base-devel` and `sudo`:

```sh
pacman -S --needed base-devel
cd libcamera-yt11
makepkg -s              # ~30-60 min on the MT6785
sudo pacman -U libcamera-0.7.2-4.7-aarch64.pkg.tar.xz \
                libcamera-ipa-0.7.2-4.7-aarch64.pkg.tar.xz \
                libcamera-tools-0.7.2-4.7-aarch64.pkg.tar.xz
```

Notes:

- `makepkg -s` installs the missing build dependencies with sudo
  (meson, qt6-base, sdl2, libyuv, ...). The list is much shorter than
  the stock package's because the GStreamer plugin, the Python
  bindings, the docs and `lc-compliance` are disabled in `build()`.
- The build only compiles the `simple` pipeline handler and the
  `simple` (soft) IPA: `-D pipelines=simple -D ipas=simple`.
- If `cam` is missing at runtime, check that `libcamera-tools` was
  installed.
- To keep the distro package instead, remove ours with
  `sudo pacman -R libcamera libcamera-ipa libcamera-tools` and reinstall
  the repo versions.

## Enabling the software ISP without rebuilding

libcamera ≥ 0.6 reads `/etc/libcamera/configuration.yaml` (and
`$XDG_CONFIG_HOME/libcamera/configuration.yaml`); the `software_isp`
flag of a driver entry can be overridden there. This is **not**
sufficient for this tablet (the driver name must be in the table
first), but it is how the flag can be toggled later without a rebuild
(T13 §2.3):

```yaml
pipelines:
  simple:
    supported_devices:
      - driver: mt6785-cam
        software_isp: true
```

## Testing

Prerequisites: the kernel built from the 2026-11-17 tree (unpacked
10-bit layout, `orientation`/`rotation` in the sensor DT nodes) with
its modules loaded (`mt6785-seninf`, `mt6785-camsv`, `ov8856`,
`s5k4h7`, `dw9714`), and `media-ctl -p` showing the graph with the
OV8856 link enabled (`docs/research/camera/T8-V4L2.md` §7). Sanity
check first with the V4L2 tools:

```sh
sh tools/camera/v4l2-capture.sh -n 3 -t -p /tmp/bars.png
v4l2-ctl -d /dev/video0 --list-formats   # expect BG10/GB10/BA10/RG10
```

1. List cameras (expect one camera, the rear OV8856):

   ```sh
   cam -l
   ```

   Expected output shape:

   ```
   Available cameras:
   1: Internal back camera (/soc/i2c@11009000/camera-sensor@36)
   ```

   (The camera id is the sensor's DT node path — `sysfs::firmwareNodePath`
   on a devicetree platform — so the exact string depends on the DTS; the
   suffix `camera-sensor@36` under `i2c@11009000` is the stable part.)
   With `LIBCAMERA_LOG_LEVELS=SimplePipeline:0 cam -l` expect a
   `Matched on device: /dev/media0` debug line — that is the patch
   working. Note the simple pipeline only enumerates the camera whose
   link is enabled; to check the front camera, switch it first
   (`media-ctl -l '"s5k4h7 4-002d":0 -> "mtk-mt6785-seninf":2 [1]'`
   — one call now switches the selection — then `cam -l` again).

2. Capture five frames to files:

   ```sh
   cam -c 1 --capture=5 --file=frame-#.ppm
   ```

   Expected: five PPM files (`frame-0-...ppm`), 640x480 RGB, real
   pictures (the software ISP debayer reads the unpacked 10-bit
   samples directly). The OV8856 colour bars
   (`v4l2-ctl -d /dev/v4l-subdev0 --set-ctrl test_pattern=1`) make
   the check unambiguous; if the bars look vertically smeared or
   rotated, revisit the DT `rotation` value.

3. Graphical viewer (if Qt deps installed):

   ```sh
   qcam
   ```

   Select the camera in the drop-down, Start. Expect a live 640x480
   preview.

4. Through PipeWire (after installing `pipewire-libcamera`, in the
   repos):

   ```sh
   systemctl --user restart pipewire wireplumber
   wpctl status
   ```

   Expect a `VideoCapture` section listing a source named like
   `libcamera_input.<camera id>` (WirePlumber's libcamera monitor runs
   by default in the `hardware.video-capture` profile). Then in a
   browser on Hyprland, the camera appears in `getUserMedia` device
   lists (Firefox/Chromium enumerate PipeWire camera nodes through the
   portal).

## Regenerating the patch

```sh
curl -o simple.cpp 'https://gitlab.freedesktop.org/camera/libcamera/-/raw/v0.7.2/src/libcamera/pipeline/simple/simple.cpp'
# add the mt6785-cam line after the mtk-seninf entry
diff -u simple.cpp simple.cpp.edited > libcamera-0.7.2-simple-mt6785.patch
# fix the ---/+++ headers to a/... and b/... paths
```
