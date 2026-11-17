# T19 — libcamera simple pipeline: lens control and contrast autofocus

Task: make the simple pipeline handler and the soft IPA drive the rear
camera's focus actuator — manual `LensPosition` first (patch A), then a
contrast autofocus algorithm on top (patch B). All `file:line` references
point at **tag v0.7.2** with the two existing yt11 patches applied (they
touch none of the same files).

## 1. Hardware and pre-existing facts

- Rear sensor `ov8856 2-0036` has `lens-focus` in its DT node, pointing at
  a voice-coil actuator driven by the mainline `dw9719` driver: a V4L2
  subdev `dw9719 2-000c` with `V4L2_CID_FOCUS_ABSOLUTE`, range 0..1023,
  step 1 (docs/hardware/CAMERA.md "Standard 16-bit layout and autofocus
  actuator" identifies the part as a DW9718S).
- The actuator's supply is only on while the subdev node is held open —
  libcamera's `CameraLens` opens it in `CameraLens::init()`
  (`src/libcamera/camera_lens.cpp:56-77`) and keeps it open for the
  lifetime of the `CameraSensor`, which is what we want.
- A subject at ~40 cm is sharpest near driver position 340; far subjects
  near the low end. So the useful range is 0 (far) → 1023 (near).
- Front sensor `s5k4h7` has no actuator: both patches are written so that
  `sensor_->focusLens()` returning null changes nothing at all.

libcamera already has all the plumbing for lenses — none of it was
connected in the simple pipeline:

- `CameraSensorLegacy::discoverAncillaryDevices()`
  (`src/libcamera/sensor/camera_sensor_legacy.cpp:653-673`) creates and
  opens the `CameraLens` for any `MEDIA_ENT_F_LENS` ancillary entity. Our
  tablet is served by `CameraSensorLegacy` (the `mt6785-cam` media graph
  has no routing-capable subdevs upstream), so the lens is already found
  and opened today — it is simply never used.
- `CameraLens::setFocusPosition()`
  (`src/libcamera/camera_lens.cpp:87-96`) wraps
  `V4L2_CID_FOCUS_ABSOLUTE` in a `ControlList` and pushes it to the
  subdev.
- The ipu3 pipeline is the model for lens control flow
  (`src/libcamera/pipeline/ipu3/ipu3.cpp:1203-1217`): the IPA computes a
  lens position, emits it through a `setLensControls` event, the pipeline
  handler calls `focusLens->setFocusPosition()`.
- The rpi controller's `Af` (`src/ipa/rpi/controller/rpi/af.cpp`) is the
  model for the algorithm: coarse sweep → fine sweep around the peak,
  with settle frames between moves. The ipu3 `Af`
  (`src/ipa/ipu3/algorithms/af.cpp`) is the model for a hill-climbing
  scan at IPA scale — this patch follows its shape (coarse step 30, fine
  step, ignore/settle counters, best-focus tracking, early stop on the
  first significant decline).
- v0.7.2 has **no** lens support in the simple pipeline or the soft IPA
  (verified: `grep -rn "focusLens\|LensPosition" src/libcamera/pipeline/simple/
  src/ipa/simple/` is empty), and neither does master at the time of
  writing (the renamed `src/ipa/softisp/` has no Af algorithm). Nothing to
  build on; this is new wiring, not a backport.

## 2. Part A — `libcamera-0.7.2-yt11-lens.patch` (manual focus)

Files changed:

| File | Change |
|---|---|
| `include/libcamera/ipa/soft.mojom` | `init()` gains a `lensControls` ControlInfoMap argument; new `setLensControls(ControlList)` event. Mirrors ipu3.mojom:14/41. |
| `src/libcamera/software_isp/software_isp.cpp`, `.h` | `SoftwareIsp` ctor takes the lens controls map and passes it to `ipa_->init()`; the new `setLensControls` event is re-emitted as a `Signal` for the pipeline handler. |
| `src/libcamera/pipeline/simple/simple.cpp` | `SimpleCameraData` keeps the `CameraLens *` from `sensor_->focusLens()`; passes `lens_->controls()` (or an empty map when there is no lens) to the `SoftwareIsp`; connects and applies `setLensControls`. |
| `src/ipa/simple/soft_simple.cpp`, `ipa_context.h` | The IPA stores the lens controls map, records the driver range in `context_.configuration.lens`, declares `controls::LensPosition`, applies manual `LensPosition` requests, and reports the position back in metadata. |

Design decisions:

- **Lens discovery/open**: nothing new — `CameraSensorLegacy` already
  opened it. Keeping the subdev open keeps the actuator powered; that is
  required by the driver and already the behaviour for the whole camera
  lifetime.
- **`LensPosition` scale**: the control is specified in dioptres
  (`src/libcamera/control_ids_core.yaml:1025`). We have no calibration
  mapping driver units to dioptres for this module, so the patch maps the
  driver range **linearly to [0.0, 1.0]**: 0.0 = driver minimum (far),
  1.0 = driver maximum (near). On this tablet, position 340 (≈40 cm) is
  `LensPosition ≈ 340/1023 ≈ 0.33`. The mapping is documented in the
  patch and in the IPA log at configure time. This keeps applications
  portable across actuators with different ranges and avoids inventing a
  fake dioptre calibration; a real map can replace it later without
  changing the control.
- **When the position is applied**: `queueRequest()` (per request, from
  the request's `LensPosition` control), because the simple pipeline
  forwards request controls to the IPA there
  (`simple.cpp:1765`). The lens is not part of `DelayedControls` — the
  actuator has no frame-synchronised semantics — so the position is
  applied immediately via `setLensControls` → `CameraLens::
  setFocusPosition()`.
- **No-lens path**: `lens_ == nullptr` → empty `ControlInfoMap` is passed
  down; the IPA finds no `V4L2_CID_FOCUS_ABSOLUTE` in it, sets
  `lens.present = false`, declares no control, and every lens path
  returns early. The front camera is bit-for-bit unchanged.
- **Start position**: `configure()` moves the lens to the driver's
  default position (0 for dw9719 = far), so streaming always starts from
  a known state and the "supply only while open" behaviour can't leave
  the lens parked at a random near position from a previous session.

## 3. Part B — `libcamera-0.7.2-yt11-af.patch` (contrast autofocus)

Files changed:

| File | Change |
|---|---|
| `include/libcamera/internal/software_isp/swisp_stats.h` | New `uint64_t sharpness` field in `SwIspStats`. |
| `src/libcamera/software_isp/swstats_cpu.cpp` | The line statistics macros accumulate the sum of absolute horizontal differences of the green samples; `startFrame()`/`finishFrame()` reset/aggregate it like the histogram. |
| `src/ipa/simple/algorithms/af.{h,cpp}` | New `Af` algorithm. |
| `src/ipa/simple/algorithms/meson.build`, `data/uncalibrated.yaml` | Build/enable it. |
| `src/ipa/simple/soft_simple.cpp`, `ipa_context.h` | Lens bookkeeping shared with A (afAuto flag, position application after algorithms run). |

### 3.1 Sharpness figure

`SWSTATS_ACCUMULATE_LINE_STATS` already computes `g = (g + g2) / 2`
(the average of the two green samples of the 2×2 Bayer block) for every
sampled block. The patch adds, per sampled block, `|g − prevG|` where
`prevG` is the previous block's green value **on the same line**
(`firstG` skips the first block of each line so it never compares
against a stale value from the previous line):

- Same sampling grid as the existing statistics: every other 2×2 block
  in x (`x += 4`) and lines 0-1 of every 4 (`ySkipMask_ = 0x02`). At
  3264×2448 that is ~1000 blocks per sampled line × ~612 sampled lines ≈
  6×10⁵ additions of already-loaded values — no extra memory traffic,
  one compare + one subtract + one add per block on data that is hot in
  cache because debayering interleaves with stats. This is the same
  order as the existing histogram increment.
- Overflow: worst case all |Δg| = 1023 over 6×10⁵ samples ≈ 6×10⁸ per
  thread, and per-thread accumulators are summed into `uint64_t
  sharpness` — no wraparound (12-bit sensors: 4095 × 6×10⁵ ≈ 2.4×10⁹,
  still < 2³², and the accumulator is 64-bit anyway).
- Green horizontal difference is the classic cheap CDAF figure: green
  has twice the samples of R or B, and horizontal differences survive
  the row-subsampling. Absolute difference (not squared) keeps it
  linear-ish and cheap.

### 3.2 Af algorithm

State machine (`ScanState`): `Idle → Coarse → Fine → Idle`.

- **Manual (default)**: `AfModeManual`. The algorithm declares the
  control and reports `AfStateIdle`; `LensPosition` from part A is the
  only way the lens moves.
- **Auto**: `AfModeAuto` + `AfTrigger` (`AfTriggerStart`) starts a scan:
  a coarse sweep from the far end (driver min) in steps of
  `coarseStep` (30, ~34 points over 0..1023); the first position whose
  sharpness drops more than 10% below the running peak ends the sweep
  (hill climbing, like ipu3's `afScan()` at
  `src/ipa/ipu3/algorithms/af.cpp:277-319`); then a fine sweep over
  ±`coarseStep` around the peak in steps of `fineStep` (5); then the
  lens settles on the best fine position and `AfState` becomes
  `Focused` (or `Failed` if nothing was ever measured).
  `AfTriggerCancel` returns to `Idle` without moving the lens.
- **Continuous** (implemented — it ended up simple and safe):
  `AfModeContinuous` starts a scan immediately on mode entry and, once
  focused, retriggers when the sharpness stays below
  `retriggerRatio` (0.7) of the focused sharpness for
  `retriggerFrames` (3) consecutive statistics events. That catches
  subject/scene changes; the ratio and the frame count are tuning
  keys, and `retriggerFrames` prevents a single noisy frame from
  launching a full sweep.
- **Settle handling**: statistics run once every 4 frames
  (`SwStatsCpu::kStatPerNumFrames`,
  `include/libcamera/internal/software_isp/swstats_cpu.h:47`) and the
  actuator needs a couple of frames to move, so after every lens step
  the algorithm ignores `settleFrames` (2) statistics events ≈ 8 frames
  before measuring. A full scan is ~34 coarse + ~12 fine points × (1
  measure + 2 settle) events / 7.5 Hz ≈ **20 s worst case at 30 fps**;
  the early-stop on decline typically cuts the coarse sweep to well
  under half of that. This is the price of the statistics cadence and
  the voice-coil settle time; it is a still-image AF, not a video AF.
- **Interaction with AGC**: the sharpness sum scales with exposure
  (more light → bigger differences), so a scan can be misled if AGC is
  converging at the same time. In practice the T18 tuning converges in
  1-2 s and a scan takes ~10-20 s, so AGC is stable for almost all
  measured points. The `retriggerRatio` in continuous mode is likewise
  exposure-sensitive; if the tablet shows spurious retriggers in
  changing light, raise it or raise `retriggerFrames`. A
  sharpness/exposure normalisation is deliberately left out (it would
  need the frame's gain in the stats path and is not needed to prove
  the mechanism).
- **Mode/position interaction**: `LensPosition` is ignored whenever an
  automatic mode owns the lens (the IPA checks `AfMode` in the same
  request first, then the sticky `afAuto` state), matching the control
  documentation ("ignored unless AfMode is AfModeManual",
  `control_ids_core.yaml:1034`). `AfState` is reported in metadata
  every frame (settable-control declaration deliberately omitted, as
  rpi does — it is `direction: out`).

Tuning keys (`Af:` section of the sensor YAML, defaults in
parentheses): `coarseStep` (30), `fineStep` (5), `settleFrames` (2),
`retriggerRatio` (0.7), `retriggerFrames` (3).

### 3.3 mojom interface change — implementers/callers updated

`include/libcamera/ipa/soft.mojom` changes in part A:
`init()` signature gains `libcamera.ControlInfoMap lensControls`; new
event `setLensControls(libcamera.ControlList)`. The generated
`soft_ipa_interface.h`, `soft_ipa_proxy.cpp` and
`soft_ipa_proxy_worker.cpp` are build-time generated from the mojom, so
only hand-written implementers/callers needed updating — all of them
were:

| Role | File | What changed |
|---|---|---|
| IPA implementer | `src/ipa/simple/soft_simple.cpp` (`IPASoftSimple::init`, new `setLensControls` emit) | signature + emission |
| Proxy caller | `src/libcamera/software_isp/software_isp.cpp` (`SoftwareIsp` ctor / `ipa_->init`) | passes lens controls, connects event |
| Event consumer | `src/libcamera/pipeline/simple/simple.cpp` (`SimpleCameraData::setLensControls`) | applies to the actuator |

No other user of the interface exists in the tree (verified:
`grep -rln IPASoftInterface src/ include/` lists only the mojom and
`soft_simple.cpp`). Part B does not touch the mojom.

## 4. Limits

- The dioptre mapping is linear/normalised, not calibrated: `LensPosition
  0.33` means "33% of the actuator travel", not exactly 2.5 dioptres.
- The AF knows nothing about subject distance or PDAF (there is none);
  it is pure contrast AF over the whole statistics window (no
  `AfWindows` support — the soft ISP statistics have no ROI grid).
- Scan speed is bounded by `kStatPerNumFrames = 4` and the actuator
  settle time (see above); expect tens of seconds worst case, and tune
  `coarseStep` up (e.g. 40-50) if it is too slow for the 0..1023 range.
- Sharpness is exposure-sensitive (no normalisation); see §3.2.
- `AfRange`, `AfSpeed`, `AfMetering`, `AfWindows`, `AfPause` are not
  declared (not implemented). Setting them returns the standard
  "control not supported" error, which `cam` prints per script line —
  expected.
- The lens moves on `configure()` to the driver default; if an
  application wants a specific start position it should send
  `LensPosition` in the first request.

## 5. Test plan on the tablet

Build and install with the two new patches appended to the PKGBUILD
(see the worker report for the exact lines). Prerequisites as in the
README: kernel with `dw9719` module loaded, rear camera link enabled
(`cam -l` shows the OV8856).

Debug log categories: `IPASoftAf` (the algorithm),
`IPASoft` (lens moves), `SimplePipeline` (lens discovery). Enable with
e.g. `LIBCAMERA_LOG_LEVELS='*:WARN,IPASoftAf:DEBUG,IPASoft:DEBUG'`.

### 5.1 Lens is discovered (part A)

```sh
LIBCAMERA_LOG_LEVELS='*:WARN,SimplePipeline:DEBUG' cam -l
```

Expect a line `Using focus lens 'dw9719'` (the entity name; the model
comes from the subdev) and, after start, in the IPA:
`Lens focus control 0-1023`.

Check `LensPosition` is listed in the camera controls:

```sh
cam -c 1 --metadata --capture=1 --file=/dev/null 2>&1 | grep -i lens
```

(`--capture=1` prints the request metadata; expect a `LensPosition = 0`
line.)

### 5.2 Manual focus far/near (part A)

Write `/tmp/focus.yml`:

```yaml
properties:
  - loop: 2
frames:
  - 0:
      LensPosition: 0.0
  - 1:
      LensPosition: 0.33
```

Wait — the loop property repeats every `loop` frames and controls are
only applied on the frames listed, so a 2-entry loop applies "far" on
even frames and "near" on odd frames; use it with `--capture=N` to see
alternating metadata. For a settled check prefer two separate runs:

`/tmp/focus-far.yml` (apply once, capture 30):

```yaml
frames:
  - 0:
      LensPosition: 0.0
```

`/tmp/focus-near.yml` (≈40 cm subject):

```yaml
frames:
  - 0:
      LensPosition: 0.33
```

Run each with the camera pointed at a detailed subject at the matching
distance and check the output frames:

```sh
cam -c 1 --script /tmp/focus-far.yml  --capture=30 --file=far-#.ppm
cam -c 1 --script /tmp/focus-near.yml --capture=30 --file=near-#.ppm
LIBCAMERA_LOG_LEVELS='*:WARN,IPASoft:DEBUG' cam -c 1 \
    --script /tmp/focus-near.yml --capture=30 --file=/dev/null
```

Expected: `Lens position set to 337` (0.33 × 1023 ≈ 337) in the log on
frame 0; the near run's PPMs of the ~40 cm subject are visibly sharper
than the far run's, and vice versa for a distant subject. Confirm the
metadata with `--metadata` (`LensPosition = 0.33`).

Known quirk to expect: `cam` applies script controls per frame; on
frames without an entry no control is sent, so the lens stays where the
last command put it — that is the behaviour we want here.

### 5.3 Contrast autofocus (part B)

`/tmp/af.yml`:

```yaml
frames:
  - 0:
      AfMode: 1
      AfTrigger: 0
```

(`AfMode: 1` = `AfModeAuto`, `AfTrigger: 0` = `AfTriggerStart`; enum
values are in `control_ids_core.yaml:795`/`954`.)

```sh
LIBCAMERA_LOG_LEVELS='*:WARN,IPASoftAf:DEBUG,IPASoft:DEBUG' cam -c 1 \
    --script /tmp/af.yml --metadata --capture=300 --file=/dev/null
```

Expected log sequence: `Coarse scan started`, then a series of
`frame N focus P sharpness S` lines stepping P by 30 from 0, then
`Fine scan 310-370`, fine steps of 5, then `AF done, focus <best>
sharpness <peak>`. In `--metadata` output the `AfState` line goes
`1` (Scanning) then `2` (Focused) — or `3` (Failed) if the scene was
flat (lens cap on: expect Failed, not a hang).

With the ~40 cm subject, the final `focus` should land in the 300-380
band (the sharpness peak near 340). Repeat with a window or the room
across the street: the peak should move toward the low end.

### 5.4 Continuous AF (optional check)

`/tmp/caf.yml`:

```yaml
frames:
  - 0:
      AfMode: 2
```

```sh
LIBCAMERA_LOG_LEVELS='*:WARN,IPASoftAf:DEBUG' cam -c 1 \
    --script /tmp/caf.yml --metadata --capture=900 --file=/dev/null
```

Expect an immediate scan, then `Continuous retrigger` lines only when
you move the subject or point at a very different scene; a static scene
must not retrigger more than once after settling.

### 5.5 Front camera regression (both parts)

Switch the link and repeat 5.1-5.2:

```sh
media-ctl -l '"s5k4h7 4-002d":0 -> "mtk-mt6785-seninf":2 [1]'
cam -l
LIBCAMERA_LOG_LEVELS='*:WARN,IPASoft:DEBUG' cam -c 1 --capture=30 --file=/dev/null
```

Expected: no `Using focus lens` line, no `Lens focus control` line, no
`LensPosition` in `--metadata`, no `IPASoftAf` activity, captures
unchanged from before the patches.

### 5.6 Part-A-only regression

If part B misbehaves on hardware, ship only
`libcamera-0.7.2-yt11-lens.patch` (it applies independently). Then
5.1/5.2 must still work, and `AfMode`/`AfTrigger` are simply absent
from the camera controls (`cam --script` prints "Unsupported control"
for them, which is correct).

## 6. Regenerating the patches

The patches were generated from a git clone of v0.7.2 with the two
existing patches applied first, as two commits:

```sh
git clone --depth 1 --branch v0.7.2 https://gitlab.freedesktop.org/camera/libcamera.git
cd libcamera
git am ../libcamera-0.7.2-simple-mt6785.patch ../libcamera-0.7.2-yt11-sensors.patch
# ... edit, commit part A, then part B ...
git format-patch -1 <A> --stdout > ../libcamera-0.7.2-yt11-lens.patch
git format-patch -1 <B> --stdout > ../libcamera-0.7.2-yt11-af.patch
```

Both were verified to apply with `patch -Np1` (no fuzz, no rejects) on a
pristine v0.7.2 after the two existing patches, and part A alone was
verified the same way. The Mac cannot build libcamera (Linux-only
headers); the build happens on the tablet per the PKGBUILD.

## Supervisor addendum: results on the tablet (2026-11-17)

Changes made to the worker's patches after building and testing on the
unit; measurements are in `docs/hardware/CAMERA.md`, "Focus through
libcamera".

- `configure()` no longer moves the lens: emitting `setLensControls`
  before `start()` hits a fatal assertion in the threaded IPA proxy. The
  default position is applied with the first statistics instead.
- `std::max`/`std::min` in the fine-sweep bounds cast `coarseStep_` to
  `int32_t` (did not compile).
- The sharpness used by `Af` is divided by the green sum, so a
  brightness change during a sweep is not read as a focus change.
- `ov8856.yaml` enables `Af` with `coarseStep` 60, `fineStep` 10,
  `settleFrames` 1.
- Section 3.1's statement that sharpness is not normalised, and the
  start-position paragraph in section 2, describe the worker's version.

