# T1: Sensor Power-Up and I2C Identification Probe (`yt11-cam-probe`)

M0 bring-up module and user-space I2C ID scanner for the Lenovo Yoga Tab 11
(`YT-J706F`, MediaTek MT6785). Mirrors the M0 workflow proven on Xiaomi
`begonia` (`src/begonia-ftp/camera/NOTES.md`) without adding sensor V4L2
nodes yet.

## Hardware Mapping and Source Provenance

### Camera I2C Buses

From `docs/hardware/CAMERA.md` (lines 10-18), the stock device tree uses
vendor buses `i2c2` and `i2c4` at 400 kHz:

| Vendor bus | Mainline DT label | Register base (`mt6785.dtsi`) | SCL / SDA pins | Pinfunc macros (`mediatek,mt6785-pinfunc.h`) |
|---|---|---|---|---|
| `i2c2` | `&i2c2` | `0x11009000` (`mt6785.dtsi` L1176) | GPIO112 / GPIO113 | `PINMUX_GPIO112__FUNC_SCL2` (L718), `PINMUX_GPIO113__FUNC_SDA2` (L721) |
| `i2c4` | `&i2c4` | `0x11011000` (`mt6785.dtsi` L1253) | GPIO110 / GPIO111 | `PINMUX_GPIO110__FUNC_SCL4` (L712), `PINMUX_GPIO111__FUNC_SDA4` (L715) |

Both `&i2c2` and `&i2c4` were checked against
`src/mt6785-mainline/arch/arm64/boot/dts/mediatek/mt6785-lenovo-yt-j706f.dts`
and `mt6785-lenovo-yt-j706f-audio.dtsi` and had no prior users.

### Power Rails, Switches, and Resets

From `docs/hardware/CAMERA.md` (lines 31-43) and `mt6359.dtsi` (lines 145-149):

| Signal | `cam0` | `cam1` | DT property (`camera-probe`) |
|---|---|---|---|
| `vcamio` (I/O, 1.8 V) | MT6359 `ldo_vcamio` | MT6359 `ldo_vcamio` | `vcamio-supply = <&mt6359_vcamio_ldo_reg>` |
| `vcama` (analog switch) | GPIO195 (shared) | GPIO195 (shared) | `vcama-gpios = <&pio 195 GPIO_ACTIVE_HIGH>` |
| `vcamd` (digital switch) | GPIO50 (shared) | GPIO50 (shared) | `vcamd-gpios = <&pio 50 GPIO_ACTIVE_HIGH>` |
| `vcamaf` (AF switch) | GPIO197 | none | `vcamaf-gpios = <&pio 197 GPIO_ACTIVE_HIGH>` |
| Reset (high = run) | GPIO119 | GPIO124 | `cam0-reset-gpios`, `cam1-reset-gpios` |

There is no power-down (`PDN`) pin and no MIPI switch in the stock pin states.

### Master Clocks (`CMMCLK1` / `CMMCLK2` vs `CLK_TOP_CAMTG1..5`)

- `docs/hardware/CAMERA.md` (L37): `cam0` uses GPIO117 pin function 1
  (`CMMCLK`) and `cam1` uses GPIO120 pin function 1.
- `src/mt6785-mainline/drivers/pinctrl/mediatek/pinctrl-mtk-mt6785.h`
  (L1202-1255, L1953-1964) and `mediatek,mt6785-pinfunc.h` (L735-760, L1166):
  - GPIO116 func 1 = `CMMCLK0`
  - GPIO117 func 1 = `CMMCLK1` (`cam0_mclk_on`, `drive-strength = <4>`)
  - GPIO120 func 1 = `CMMCLK2` (`cam1_mclk_on`, `drive-strength = <4>`)
  - GPIO121 func 1 = `CMMCLK3`
  - GPIO196 func 1 = `CMMCLK4`
- `src/mt6785-mainline/drivers/clk/mediatek/clk-mt6785-top.c` (L222-231,
  L491-494, L548) and `mediatek,mt6785-clk.h` (L366-369, L404):
  - `topckgen` exposes five 1-indexed mux gates `CLK_TOP_CAMTG1`..`CLK_TOP_CAMTG4`
    (`CLK_CFG_4`) and `CLK_TOP_CAMTG5` (`CLK_CFG_13`), each selectable to
    `CLK_TOP_UNIVPLL_192M_D8` (24 MHz, `clk-mt6785-top.c` L86).
- `src/begonia-ftp/camera/NOTES.md` (L75, L137) and `cam-probe.c` (L42-43):
  - Because `CMMCLK0..4` is 0-indexed and `CLK_TOP_CAMTG1..5` is 1-indexed,
    whether `CMMCLK1`/`CMMCLK2` are fed by `CAMTG2`/`CAMTG3` or
    `CAMTG1`/`CAMTG2` was not established on `begonia` (`"which CAMTG goes to
    CMMCLK4 — not found out"`).
  - Therefore `yt11-cam-probe` exposes the `camtg` module parameter
    (`0` = enable all five `CLK_TOP_CAMTG1..5` at 24 MHz; `1..5` = enable
    only `CLK_TOP_CAMTG<n>`), while pinctrl only muxes the active slot's
    `CMMCLK` pin and keeps the other slot's MCLK pin as a low GPIO output.
  - Per `begonia` `NOTES.md` (L95-96), mainline `pinctrl-mt6785` rejects
    `drive-strength = <1>` with `-ENOTSUPP` (`-524`), so both `mclk_on` states
    use `drive-strength = <4>` (4 mA).

## How to Use on the Tablet

1. Load the module (built as `CONFIG_YT11_CAM_PROBE=m`):

   ```sh
   sudo modprobe yt11-cam-probe
   # Optional:
   #   stage=0        skip CAMTG clocks and CMMCLK pinmux (rails/resets only)
   #   camtg=2        enable only CLK_TOP_CAMTG2 (or camtg=2,3 for cam0,cam1)
   ```

2. Check the driver state:

   ```sh
   cat /sys/kernel/debug/yt11-cam/status
   ```

3. Find the Linux `/dev/i2c-N` bus numbers for `i2c@11009000` (`i2c2`) and
   `i2c@11011000` (`i2c4`), since mainline bus numbering can differ from
   vendor Android:

   ```sh
   for d in /sys/class/i2c-dev/i2c-*; do
     echo "$d -> $(readlink -f "$d/device/of_node")"
   done
   ```

4. Power **one** slot at a time, scan both camera buses with `cam-id.py`, and
   power the slot off before testing the next:

   ```sh
   echo '0 on' | sudo tee /sys/kernel/debug/yt11-cam/power
   sudo python3 tools/camera/cam-id.py <N_i2c2>
   sudo python3 tools/camera/cam-id.py <N_i2c4>
   echo '0 off' | sudo tee /sys/kernel/debug/yt11-cam/power

   echo '1 on' | sudo tee /sys/kernel/debug/yt11-cam/power
   sudo python3 tools/camera/cam-id.py <N_i2c2>
   sudo python3 tools/camera/cam-id.py <N_i2c4>
   echo '1 off' | sudo tee /sys/kernel/debug/yt11-cam/power
   ```

5. To narrow down which `CLK_TOP_CAMTGn` feeds `CMMCLK1` (`cam0`) and
   `CMMCLK2` (`cam1`) once a sensor answers with `camtg=0`:

   ```sh
   echo 2 | sudo tee /sys/module/yt11_cam_probe/parameters/camtg
   echo '0 on' | sudo tee /sys/kernel/debug/yt11-cam/power
   sudo python3 tools/camera/cam-id.py <N_bus>
   echo '0 off' | sudo tee /sys/kernel/debug/yt11-cam/power
   ```

## Power Sequence

`yt11-cam-probe` uses a conservative, generic sequence (only one slot may be
active at a time, returning `-EBUSY` otherwise):

- **Power on (`<slot> on`)**: both resets low and inactive slot MCLK off ->
  `vcamio` 1.8 V -> `vcama` (GPIO195) high -> `vcamd` (GPIO50) high ->
  `vcamaf` (GPIO197) high for `slot 0` only -> if `stage >= 1`: enable
  `CLK_TOP_CAMTG*` (parented to `univpll_192m_d8`, 24 MHz) and mux active
  slot `CMMCLKn` -> 5 ms settle -> active slot reset high -> 10 ms settle.
- **Power off (`<slot> off` or module `remove`)**: reverse order (reset low ->
  MCLK pin back to GPIO low and CAMTG clocks off -> `vcamaf` low -> `vcamd`
  low -> `vcama` low -> `vcamio` disabled).

## Open Questions

1. **Multi-channel I2C controllers (`i2c-mt65xx`)**: On `begonia` (same MT6785
   SoC), vendor `i2c2`, `i2c4`, and `i2c7` were multi-channel controllers
   (`ch_offset_default = <0x100>`), and mainline `i2c-mt65xx` timed out with 0
   interrupts on channel 0 (`src/begonia-ftp/camera/NOTES.md` L111-121,
   L144-147). This DT keeps the mainline `i2c2`/`i2c4` compatibles untouched; if
   `cam-id.py` hits `ETIMEDOUT` on the tablet, `i2c-mt65xx` will need the
   channel `+0x100` / PIO / NACK-mask fix ported from `begonia/i2c-mch`.
2. **Exact `CMMCLK1`/`CMMCLK2` to `CLK_TOP_CAMTG1..5` mapping**: Not determinable
   from mainline clock/pinctrl tables or `begonia` notes alone; verify on the
   tablet using the `camtg` parameter.
3. **Three vendor camera slots vs two `kd_camera_hw1` pin groups**:
   `docs/hardware/CAMERA.md` lists `camera_main` (`i2c2`), `camera_sub`
   (`i2c4`), and `camera_main_two` (`i2c4`), plus an inventory reference to
   `7-0043`, whereas `kd_camera_hw1` only defines `cam0` (GPIO119/117/197) and
   `cam1` (GPIO124/120) with shared `vcama`/`vcamd`. Hardware probing will show
   which physical sensors sit on `i2c2` vs `i2c4` and which reset/MCLK pair
   wakes each one.
4. **Sensor-specific reset polarity or power ordering**: The probe assumes
   active-high run on `GPIO119`/`GPIO124` (`CAMERA.md` L33: `high = run`). If a
   fitted sensor needs an inverted reset pulse (like `begonia` class E
   `OV02A10`/`GC2375`) or a specific rail order, it may fail to ACK until
   adjusted.
