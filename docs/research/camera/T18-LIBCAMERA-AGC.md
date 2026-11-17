# T18 — libcamera simple-IPA auto-exposure: analysis, patch and tuning

Task: understand why the software ISP's AGC converges slowly and overexposes
on the tablet's OV8856 / S5K4H7, fix it with a small patch plus per-sensor
tuning files, and give a test plan. All `file:line` references below point at
**tag v0.7.2** of libcamera (with the two existing yt11 patches applied; they
touch neither `agc.cpp` nor the statistics code).

## 1. How the v0.7.2 simple IPA computes exposure

### 1.1 exposureMSV: which histogram, black level, bins

The statistics are produced by `SwStatsCpu` from the raw Bayer data, before
any ISP processing:

- `src/libcamera/software_isp/swstats_cpu.cpp:170-172` — luminance weights
  `kRedYMul = 77`, `kGreenYMul = 150`, `kBlueYMul = 29` (Rec.601, ×256).
- `swstats_cpu.cpp:187-190` (`SWSTATS_ACCUMULATE_LINE_STATS`) — for each
  sampled 2×2 block the Y value is computed **from the raw samples, black
  level NOT subtracted**, then scaled to 8 bits: for our unpacked 10-bit
  format (`statsBGGR10Line0`, `swstats_cpu.cpp:222-246`, `div = 4`) the
  10-bit sample is used directly and Y is divided by 4·256... concretely
  `yVal * 64 / (256*256*4)`, i.e. the histogram index is the 10-bit sample
  shifted to its 8-bit equivalent. Sampling is subsampled: every other 2×2
  block in x (`x += 4` over 16-bit samples) and lines 3-4 of every 4 are
  skipped (`ySkipMask_ = 0x02`, `swstats_cpu.cpp:457`).
- `include/libcamera/internal/software_isp/swisp_stats.h:37-45` — the
  histogram has **64 bins** (`kYHistogramSize = 64`) of `uint32_t`.

The MSV itself is computed in `Agc::process()`,
`src/ipa/simple/algorithms/agc.cpp:162-191`:

- `agc.cpp:163-164` — the black level **is** subtracted here, but only as a
  bin offset: `blackLevelHistIdx = blc.level / (256/64) = blc.level / 4`.
  With the sensor helpers' 16-bit `blackLevel_ = 4096`, `soft_simple.cpp:242-243`
  (`/ 256`) sets the 8-bit `blc.level = 16`, so bins 0-3 (samples 0-15,
  i.e. raw 0-63 at 10 bits) are dropped and the remaining 60 bins are used.
  If `BlackLevel::process()` re-estimates the level (`blc.cpp:59-117`), the
  offset moves frame to frame.
- `agc.cpp:166-169` — those 60 bins are re-binned into **5 equal bins**
  (`kExposureBinsCount = 5`, `agc.cpp:27`); `yHistValsPerBinMod`
  (`agc.cpp:168-169`) spreads the remainder so all 60 histogram bins map to
  exactly one of the 5 exposure bins (`agc.cpp:180-183`).
- `agc.cpp:185-191` — `exposureMSV = Σ(bin_i · (i+1)) / Σ(bin_i)`, the
  "Mean Sample Value" of the ACRA 2007 paper cited at `agc.cpp:160`. Range
  1.0 (all pixels in the darkest bin) to 5.0 (all saturated). Saturated
  pixels pile into the top bin, so a blown frame still reads ~5 while the
  visible mean is capped.

### 1.2 The target and the per-step factor

- Target: `kExposureOptimal = 5 / 2.0 = 2.5` (`agc.cpp:33`), i.e. the middle
  bin of a linear-light histogram.
- Deadband: `kExposureSatisfactory = 0.2` (`agc.cpp:40`) — no correction
  when `|2.5 − MSV| ≤ 0.2`.
- v0.7.2 already uses a proportional controller, not a fixed 10% bang-bang:
  `agc.cpp:83-85`, `factor = 1 + clamp(0.04 × error, ±0.15)` with
  `kExpProportionalGain = 0.04` (`agc.cpp:56`) and `kExpMaxStep = 0.15`
  (`agc.cpp:62`). The measured log line `error 1.5 factor 1.06` matches
  exactly: `1 + 0.04 × 1.5 = 1.06`.
- Exposure is raised before gain, and lowered gain-first (`agc.cpp:87-111`),
  with the ±1-line / `againMinStep = (max−min)/100` (`soft_simple.cpp:231-234`)
  minimum steps and the final clamps to the sensor limits
  (`agc.cpp:113-116`).

Why it is slow on this tablet: the error is bounded by the sensor itself.
Going from the dark side, once pixels saturate they all land in the top MSV
bin, so the MSV asymptotes near 2.1-2.25 (measured) — the error never
exceeds ~1.5, so the factor is pinned at ~1.06 per correction. Combined
with the correction cadence below, the ~7.4-stop trip (520 lines ×1x →
2524 lines ×16x) needs ~110 corrections ≈ 15 s. Decreasing is bounded the
same way: a fully dark frame reads MSV ≥ 1.0 (the darkest bin has weight
1), so the error from below saturates at ~1.5 → factor ≈ 0.94.

### 1.3 Why a step happens only every ~4 frames

`SwStatsCpu::kStatPerNumFrames = 4`
(`include/libcamera/internal/software_isp/swstats_cpu.h:47`):
`startFrame()`/`processFrame()`/`finishFrame()`
(`swstats_cpu.cpp:384-423`, `605-617`) only accumulate and publish the
histogram when `frame % 4 == 0`; every other frame gets `valid = false`
(`swstats_cpu.cpp:407,421`), and `Agc::process()` returns early on invalid
stats (`agc.cpp:148-156`). So at 30 fps the loop runs at ~7.5 Hz — this is
by design (statistics cost), independent of the AGC gains, and the patch
does not touch it.

### 1.4 What in the output path can wash the picture

Processing order in the debayer is black level → gains → gamma
(`src/libcamera/software_isp/debayer_cpu.cpp:1007`), with the LUTs built in
`updateLookupTables()` (`debayer_cpu.cpp:981-1060`):

- **Gamma**: the IPA sends `params->gamma = 1/2.2`
  (`kDefaultGamma = 2.2`, `src/ipa/simple/algorithms/adjust.h:20`;
  `adjust.cpp:109`), applied as `value = 255 · normalized^(1/2.2)`
  (`debayer_cpu.cpp:994`) on top of the *S-curve contrast* expansion
  (`debayer_cpu.cpp:986-993`, `contrastExp = 1.0` by default = no-op).
  Brightening for gamma happens **after** the AGC has already targeted the
  middle of the *linear* range: MSV 2.5 with a roughly linear distribution
  maps to a mean linear value ≈ 0.5 → after gamma ≈ 0.5^(1/2.2) ≈ 0.73 ≈
  186/255, and the top bin (samples ≥ 4/5 of range) is fully saturated —
  the measured "~150/255 mean, windows blown out" picture. The AGC target
  and the gamma curve are simply not consistent with each other; v0.7.2 has
  no knob to reconcile them.
- **Black level**: with our 10-bit sensors the effective 8-bit black level
  is 16 (`blc.cpp:35` for the tuning file, `soft_simple.cpp:242-243` for
  the helper); `blackIndex = 16` of 256 (`debayer_cpu.cpp:1013`) and the
  LUT divides by `256 − 16` (`debayer_cpu.cpp:1015`), a mild ~7% stretch.
  This part is consistent; it is not the cause of the wash.
- **AWB gains** (`awb.cpp:80-85`, up to 4× per channel) multiply inside the
  same LUT (`debayer_cpu.cpp:1014,1049`); at 16x analogue gain the AWB
  gains act on noisy data and amplify the wash.
- **CCM**: absent — `uncalibrated.yaml` ships the `Ccm` algorithm commented
  out, and `context.ccmEnabled` stays false (`ipa_context.h:92`), so
  `combinedMatrix` stays identity. Colours are therefore "raw-Bayer +
  AWB gains" only: no saturation boost, no cross-channel correction. That
  is the correct choice without measurements, but it does contribute to
  the low-contrast look compared with a tuned pipeline.

### 1.5 What a tuning YAML can configure in v0.7.2, and what is hard-coded

Tunable per sensor (the file is `<sensor model>.yaml`, resolved by
`software_isp.cpp:151` → `IPAProxy::configurationFile()` in
`src/libcamera/ipa_proxy.cpp:174-200`, which is what prints the
"Configuration file 'ov8856.yaml' not found ... falling back to
'uncalibrated.yaml'" warning):

| Key | Parsed at | Meaning |
|---|---|---|
| `version` | `soft_simple.cpp:126` | informational |
| `algorithms` list | `soft_simple.cpp:129-134` | which algorithms run and their order; `enabled: false` disables one (`libipa/module.h:71-78`) |
| `BlackLevel.blackLevel` | `blc.cpp:29-36` | 16-bit-scale black level (`>> 8` to 8 bits); overrides the sensor helper and freezes auto-estimation (`blc.cpp:75-76`) |
| `Ccm.ccms` | `ccm.cpp:30-42` | per-colour-temperature 3×3 matrices (interpolated, `ccm.cpp:44-59`) |
| (runtime) `controls::Gamma/Contrast/Saturation` | `adjust.cpp:27-71` | per-request, not from the tuning file |

Hard-coded in v0.7.2 (the patch makes the first four tunable):

- AGC: bins count 5 (`agc.cpp:27`), target 2.5 (`agc.cpp:33`), deadband 0.2
  (`agc.cpp:40`), proportional gain 0.04 (`agc.cpp:56`), max step 0.15
  (`agc.cpp:62`).
- Statistics: 64-bin histogram (`swisp_stats.h:37`), once every 4 frames
  (`swstats_cpu.h:47`), Y weights (`swstats_cpu.cpp:170-172`).
- Debayer: default gamma 2.2 (`adjust.h:20`), contrast S-curve with
  `contrastExp = 1.0` (`adjust.cpp:111`), no saturation default.

## 2. What the patch changes and why

`image/camera/libcamera-yt11/libcamera-0.7.2-yt11-agc.patch` touches only
`src/ipa/simple/algorithms/agc.{cpp,h}`:

1. `Agc::init()` now reads four keys from the tuning file, with defaults
   equal to the compiled-in v0.7.2 constants — an `uncalibrated.yaml`
   without an `Agc` section behaves exactly as before:
   - `proportionalGain` (default 0.04),
   - `maxStep` (default 0.15),
   - `optimalExposure` (default 2.5),
   - `deadband` (default 0.2).
2. The constants stay in the file as the documented defaults
   (`kDefaultProportionalGain`, `kDefaultMaxStep`), and `updateExposure()`
   uses the members instead.

Rationale for the tablet values (in the YAML files, not the code):

- **Convergence, no oscillation.** The plant (sensor + MSV metric) is
  roughly logarithmic: measured anchors give MSV ≈ 1.0 at 520 lines ×1x and
  MSV ≈ 2.15 at the rails (2524 ×16), i.e. ~0.18 MSV per stop. Each
  correction moves log₂(E) by P·err/ln2 and the error shrinks by the
  factor (1 − s·P/ln2); the error converges monotonically (no crossing, no
  oscillation) as long as s·P/ln2 ≤ 1, i.e. P ≤ ~3.8 here — the shipped
  0.35 is an order of magnitude below that bound. It gives a first step of
  ≤ ×1.35 (+0.43 stop) that then decays geometrically: the loop reaches
  the deadband in ~25 corrections (~3.5 s at 30 fps) instead of ~110
  (~15 s), about 4× faster, and the last few steps are
  single-digit-percent so it settles without visible pumping. The cap (not
  the gain) is what bounds the transient after a hard scene change.
- **Final brightness.** The owner's hand-measured good frame was 2400 lines
  ×8x ≈ MSV 1.95 on this plant. Target 2.0 with the stock 0.2 deadband
  would rest anywhere in [1.8, 2.2]; `deadband: 0.1` narrows it to
  [1.9, 2.1], centred on that measurement and below the old railed
  endpoint: with the same exposure ceiling the loop now stops near
  2524 × ~6x instead of the maximum 2524 × 16x (simulation on the measured
  anchors), so the ~1.4 stops of spare gain and the extra noise that came
  with it are gone.
  The gamma inconsistency of §1.4 is thereby sidestepped: the linear
  target is lowered until the post-gamma output looks right, which is the
  only lever v0.7.2 offers without touching the debayer.

What the patch deliberately does **not** do: no change to the statistics
cadence (frame % 4), the MSV metric, the debayer/gamma path, or the
exposure/gain ordering — those are riskier and upstream is reworking this
area anyway (master renamed the IPA to `softisp` and routes AGC through the
shared `AgcMeanLuminance`; backporting that is out of scope).

### 2.1 Tuning files

`ov8856.yaml` and `s5k4h7.yaml` (installed to
`/usr/share/libcamera/ipa/simple/`) contain:

- `BlackLevel.blackLevel: 4096` — the same 16-bit-scale value the new
  sensor helpers provide (64 at 10 bits << 6). Writing it explicitly pins
  the level and prevents `BlackLevel::process()`'s 2%-quantile estimator
  (`blc.cpp:89-117`) from wandering on dark scenes.
- `Agc:` with `proportionalGain: 0.35`, `maxStep: 0.35`, `deadband: 0.1`,
  `optimalExposure: 2.0`.
- `Awb` and `Adjust` left at defaults; **no `Ccm`**. A colour matrix
  without measurements would shift all colours arbitrarily; calibrating one
  needs a ColorChecker capture per illuminant (typically 3) under fixed
  AGC/AWB, solving the 3×3 in linear space, and verifying saturation —
  none of which can be done without the tablet. Until then the identity
  matrix (CCM disabled) is the honest choice.

## 3. Test plan on the tablet

Build and install the package (see the PKGBUILD lines in the worker
report), then for each camera (the rear OV8856 first; for the front S5K4H7
switch the SENINF link first as in the README:
`media-ctl -l '"s5k4h7 4-002d":0 -> "mtk-mt6785-seninf":2 [1]'`):

1. **Tuning file is found.**

   ```sh
   LIBCAMERA_LOG_LEVELS='*:INFO' cam -l
   ```

   Expect `Using tuning file /usr/share/libcamera/ipa/simple/ov8856.yaml`
   (or `s5k4h7.yaml`) instead of the old
   `Configuration file 'ov8856.yaml' not found ... falling back to
   '.../uncalibrated.yaml'` warning.

2. **Convergence speed.** In the same daylight room as the previous
   measurements:

   ```sh
   LIBCAMERA_LOG_LEVELS="*:WARN,IPASoftExposure:DEBUG" cam -c 1 --capture=300 --file=/dev/null
   ```

   Compare the `agc.cpp` lines `exposureMSV ... error ... factor ... exp
   ... again` (they print once per 4 frames):
   - before the patch: `factor` pinned at ~1.06 for ~110 lines (~15 s)
     before settling at `exp 2524 again 16`;
   - after: `factor` starts at ~1.3 and decays; the loop should cross into
     `|error| ≤ 0.1` within ~20 lines (~3 s), ending with `again` around
     4-8 and `exposureMSV` between 1.9 and 2.1 instead of 2.1-2.25.
   - Watch for oscillation: once inside the deadband there should be no
     further `factor` lines (any line means it left the deadband again); a
     couple of crossings after a hard scene change is fine, sustained
     alternation `exp up / exp down` is not.

3. **Final brightness.** Capture frames and check them off-tablet:

   ```sh
   cam -c 1 --capture=5 --file=frame-#.ppm
   ```

   The room that measured ~150/255 mean with blown windows should now sit
   around ~110-130/255 mean with window detail retained. If it is still
   hot, lower `optimalExposure` in 0.1 steps (1.9, 1.8...); if dark and
   noisy, raise it. The `exp/again` pair at rest tells you which lever
   moved: `again ≥ 12` at rest means the target is still too high for that
   light.

4. **Scene-change transient.** Cover the lens, then uncover:

   ```sh
   LIBCAMERA_LOG_LEVELS="*:WARN,IPASoftExposure:DEBUG" cam -c 1 --capture=600 --file=/dev/null
   ```

   Recovery in both directions should take ≲ 30 correction lines (~4 s) per
   ~4 stops, with `factor` never exceeding `1 + maxStep` (1.35). Check the
   black-level estimator stayed quiet (`IPASoftBL` category, `Auto-set
   black level` lines should not appear since the YAML pins it).

5. **Low light.** Dim the room and repeat 3: when the loop rails
   (`exp 2524` with `again` climbing), the picture is expected noisy —
   that is the sensor at 16x, not an AGC regression; the log should show
   `error` stuck above the deadband with `factor` at the cap.

6. **Front camera.** Repeat 1-3 with the S5K4H7; same expectations, the
   file is `s5k4h7.yaml`.

Regression check: temporarily renaming the YAML files (or
`LIBCAMERA_...`-less run with the files moved away) must restore the
previous behaviour exactly — the patch defaults equal the old constants.
