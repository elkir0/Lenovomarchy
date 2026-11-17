# libcamera for the Yoga Tab 11 (MT6785 `mtk-mt6785-seninf` + software ISP)

This directory rebuilds the Arch Linux ARM `libcamera` package (0.7.2-4,
`extra/libcamera`) with one change: a patch that adds this tablet's media
device driver name to the `simple` pipeline handler's supported-device
table, with the software ISP enabled. Full background, links and the
kernel-side checklist live in
`docs/research/camera/T13-LIBCAMERA.md` (task T13).

## What the patch does

`libcamera-0.7.2-simple-mt6785.patch` adds one line to
`src/libcamera/pipeline/simple/simple.cpp` at tag `v0.7.2`:

```cpp
{ "mtk-mt6785-seninf", {}, true },
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

## Building on the tablet

Copy this directory to the tablet (it has no other repo dependencies)
and run, as a normal user with `base-devel` and `sudo`:

```sh
pacman -S --needed base-devel
cd libcamera-yt11
makepkg -s              # ~30-60 min on the MT6785
sudo pacman -U libcamera-0.7.2-4.yt11.1-aarch64.pkg.tar.xz \
                libcamera-ipa-0.7.2-4.yt11.1-aarch64.pkg.tar.xz \
                libcamera-tools-0.7.2-4.yt11.1-aarch64.pkg.tar.xz
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
      - driver: mtk-mt6785-seninf
        software_isp: true
```

## Testing

Prerequisites: the T8 kernel modules loaded (`mtk-seninf`,
`mtk-camsv`, `ov8856`) and `media-ctl -p` showing the four entities
with three enabled links (`docs/research/camera/T8-V4L2.md` §7).

1. List cameras (expect one camera):

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
   suffix `camera-sensor@36` under `i2c@11009000` is the stable part. With
   no `orientation` property in DT yet, the line reads
   `1: 'ov8856' (.../camera-sensor@36)` instead, plus a "Recommended V4L2
   control not supported" warning at startup.) With
   `LIBCAMERA_LOG_LEVELS=SimplePipeline:0 cam -l` expect a
   `Matched on device: /dev/media0` debug line — that is the patch
   working.

2. Capture five frames to files:

   ```sh
   cam -c 1 --capture=5 --file=frame-#.ppm
   ```

   Expected: five PPM files (`frame-0-...ppm`), 640x480 RGB. **Image
   content caveat (T13 §2):** until the CAMSV driver is switched to a
   standard byte layout, both the software ISP's debayered stream and
   the raw stream decode the le10 bitstream as if it were MIPI-packed,
   so the pictures come out garbled (the first sample of each 4-pixel
   group is right, the rest wrong). The point of this test is that the
   pipeline configures, requests flow and files appear — the imaging fix
   is kernel-side (checklist item 1 in T13 §5). The OV8856 colour bars
   (`v4l2-ctl -d /dev/v4l-subdev0 --set-ctrl test_pattern=1`) make the
   residual structure easy to see.

3. Graphical viewer (if Qt deps installed):

   ```sh
   qcam
   ```

   Select the camera in the drop-down, Start. Expect a live, possibly
   garbled (same layout caveat) 640x480 preview.

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
   portal). Same garbled-image caveat as above until the kernel layout
   fix.

## Regenerating the patch

```sh
curl -o simple.cpp 'https://gitlab.freedesktop.org/camera/libcamera/-/raw/v0.7.2/src/libcamera/pipeline/simple/simple.cpp'
# add the mtk-mt6785-seninf line after the mtk-seninf entry
diff -u simple.cpp simple.cpp.edited > libcamera-0.7.2-simple-mt6785.patch
# fix the ---/+++ headers to a/... and b/... paths
```
