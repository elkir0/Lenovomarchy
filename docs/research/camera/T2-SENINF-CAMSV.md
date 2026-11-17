# T2: SENINF Test Model and CAMSV0 Frame Capture (`mt6785-seninf-tm`, `mt6785-camsv-tm`)

## Corrections (2026-11-17)

Later measurements on the unit supersede three readings this document
carries from the begonia notes; see `docs/hardware/CAMERA.md`
("Frame layout and first photo", "FBC and interrupts") and
`docs/research/camera/T8-V4L2.md` (sections 0g-0i) for what was actually
measured:

- The FBC `FBC_IMGO_CTL1` low bit is **not** an "RCNT_INC" release
  strobe (section 4 register table, section 5 failure modes): it is a
  compare value against the count of frames written (`CTL2[6:0]`).  With
  1 the DMA writes exactly one frame per stream and drops the rest;
  keeping the compare value ahead of the count makes the DMA
  free-running.  No release mechanism exists or is needed.
- `FMT_SEL = 0x101 / PAK = 2` does **not** produce MIPI RAW10 on this
  board: it writes 12-bit containers (2 px / 3 bytes, sample << 2) and
  truncates lines to 2/3 of the pixels at a 10-bit stride.  The
  complete-frame layout is `FMT_SEL = 0x102 / PAK = 1` with the line
  sized for 10 bits: a continuous little-endian 10-bit bit stream per
  line ("le10"), which shares only its size with MIPI RAW10.
- Consequently "RAW10 frame" below means "10-bit frame", not the MIPI
  RAW10 byte layout; decode captures with
  `tools/camera/raw2rgb.py --layout le10`.

Port of the MT6785 M2 bring-up experiments from Xiaomi `begonia`
(`src/begonia-ftp/camera/`) to the Lenovo Yoga Tab 11 (`YT-J706F`) on Linux 7.1.
Covers two stages:
1. **SENINF test pattern -> CAMSV0 -> CMA memory -> PNG** (purely SoC-internal, no sensor needed).
2. **Real OV8856 over MIPI CSI-2 -> SENINF -> CAMSV0 -> CMA memory -> PNG** (CSI port, SENINF index, lane count, and I2C bus/address parameterized).

---

## 1. Kernel Infrastructure Checked in `src/mt6785-mainline`

All required SoC clock gates, power domains, and LARB6 exist in Linux 7.1 already; no clock driver or binding edits were needed:

| Resource | Status in `src/mt6785-mainline` | Reference |
|---|---|---|
| `MT6785_POWER_DOMAIN_CAM`, `MT6785_POWER_DOMAIN_ISP` | Present in `mt6785.dtsi` under `&spm` (`MT6785_POWER_DOMAIN_MD` deleted in board DT; CAM/ISP intact) | `mt6785.dtsi` L999-1015, `mt6785-lenovo-yt-j706f.dts` L808-810 |
| CAMSYS clocks (`CLK_CAM_LARB6/7`, `GALS`, `MAIN`, `TG`, `SENINF`, `SV0`, `SV1`) | Present in `clk-mt6785-cam.c` | `clk-mt6785-cam.c` L22-33, `mediatek,mt6785-clk.h` L92-99 |
| `CLK_TOP_SENINF0..2` | Present in `clk-mt6785-top.c` (`CLK_CFG_9`) | `clk-mt6785-top.c` L522-524, `mediatek,mt6785-clk.h` L387-389 |
| APMIXED 26 MHz MIPI-CSI gates (`CLK_APMIXED_MIPIC0`, `CLK_APMIXED_MIPIC1`) | **Already present** in `clk-mt6785-apmixed.c` at `0x1000C000 + 0x20` bits `6` and `11` using `mtk_clk_gate_ops_no_setclr_inv` (1 = on, parent `clk26m`) | `clk-mt6785-apmixed.c` L13-34, `clk-gate.c` L143-203, `mediatek,mt6785-clk.h` L25, L29 |
| `larb6` (`0x1a001000`) | Present and enabled in `mt6785.dtsi` (label `&larb6`); `mtk-smi.c` has 31 ports for LARB6, 5 for LARB7 | `mt6785.dtsi` L2036-2045, `mtk-smi.c` L296-299 |
| `larb7` (`0x1a002000`) | Not in `mt6785.dtsi`; bypassed in userspace via `tools/camera/larb-bypass.py` (`CONFIG_DEVMEM=y`, `CONFIG_IO_STRICT_DEVMEM` not set) | `out/kernel/config` L2965, L8526-8527 |

Because `CLK_APMIXED_MIPIC0` and `CLK_APMIXED_MIPIC1` are already registered by `clk-mt6785-apmixed.c`, `camsv_tm` requests them directly via DT (`"mipic0"`, `"mipic1"`) so `echo 1 > /sys/kernel/debug/camsv-tm/power` enables bits 6 and 11 of `0x1000C020` through CCF. `ov-cap.py` also verifies `0x1000C020` via `/dev/mem` and sets `0x840` if cleared.

Both DT nodes (`seninf-tm@1a040000` and `camsv-tm@1a050000` in `mt6785-lenovo-yt-j706f.dts` L907-953) declare two power domains (`"cam"`, `"isp"`) so Linux's platform-bus `genpd_dev_pm_attach()` does not power on `MT6785_POWER_DOMAIN_CAM` at probe time; each driver attaches `"cam"` explicitly via `dev_pm_domain_attach_by_name(dev, "cam")` on `power=1`.

---

## 2. Exact Run Procedure on the Tablet

Copy `tools/camera/` (`cap-tm.sh`, `larb-bypass.py`, `raw2png.py`, `ov-cap.py`) to the tablet, boot the `yt11` kernel + DTB with `CONFIG_MT6785_SENINF_TM=m` and `CONFIG_MT6785_CAMSV_TM=m` installed under `/lib/modules`.

### Step A: Optional SENINF-only test-model sanity check (`mt6785-seninf-tm`)

Verifies `MT6785_POWER_DOMAIN_CAM`, `CLK_TOP_SENINF0..2`, and `SENINF0 -> MUX0 -> CAM_MUX0` without touching CAMSV or DMA:

```sh
sudo modprobe mt6785-seninf-tm
echo 1 | sudo tee /sys/kernel/debug/seninf-tm/power
echo 1 | sudo tee /sys/kernel/debug/seninf-tm/start
cat /sys/kernel/debug/seninf-tm/dump
```

Expected output from `dump`:
- `SENINF_TOP_CTRL` readable (non-`0xffffffff`), `top-seninf0` at `312000000` Hz in `dmesg`.
- `MUX0 #0` vs `#1`: `size 0x10001f00` (4096 x 7936), `pix_cnt` advancing between `#0` and `#1`, `mon H 7935`.
- `CAM_MUX`: `mux0 chk_res 0x10007c00`.

Power down and unload before running CAMSV if desired (`echo 0 | sudo tee /sys/kernel/debug/seninf-tm/power && sudo rmmod mt6785-seninf-tm`), or leave loaded (`mt6785-camsv-tm` uses `devm_ioremap` without `request_mem_region` so they do not conflict on `0x1a040000`).

### Step B: Full test-pattern capture (`SENINF TM -> CAMSV0 -> RAW10 -> PNG`)

Do **not** `rmmod`/`insmod` `mt6785-camsv-tm` repeatedly on the same boot if a capture fails (see failure mode #3 below — reboot if TG locks up).

```sh
sudo modprobe mt6785-camsv-tm
sudo sh tools/camera/cap-tm.sh
```

By default, `cap-tm.sh` captures a `640x480` RAW10 frame (pre-filled with `0xa5` sentinel), saves `/tmp/tm-frame.raw` (`384000` bytes), and converts it via `raw2png.py` to `/tmp/tm-frame.png`.

Custom geometry / output paths:
```sh
sudo sh tools/camera/cap-tm.sh -w 640 -l 480 -o /tmp/tm-640x480.raw -p /tmp/tm-640x480.png
# Re-render PNG manually at any time:
python3 tools/camera/raw2png.py /tmp/tm-640x480.raw 640 480 800 /tmp/tm-640x480.png
```

Expected output:
- `larb6 ... MMU_EN: 000...` and `larb7 ... MMU_EN: 00000` (all zeros).
- `CAMSV0` `TG_FRMSIZE` (`0x268`): `0x028001e0` (`640 x 480`).
- `CAMSV0` `INT_STATUS` (`0x51c`): `0x0009048f` / `0x0009049f` (includes `PASS1_DON` bit 10; `VS`/`TG_ST`/`EXPDON`/`SOF`).
- `saved /tmp/tm-frame.raw: 384000 bytes, non-0xa5 count=384000, last+1=384000`.
- `/tmp/tm-frame.png`: horizontal gradient hatching across all 480 lines (pattern `0x16`).

### Step C: Real OV8856 capture over MIPI CSI-2 (`ov-cap.py`)

Preconditions: `yt11-cam-probe` (M0), `mt6785-camsv-tm` (M2), and multi-channel `i2c-mt65xx` (`mediatek,ch-offset = <0x100>` on `i2c2` already in board DT) loaded. From `docs/hardware/CAMERA.md` L62, YT-J706F's OV8856 (`cam0`) sits on `i2c2` (`/dev/i2c-2`) and answers at `0x36` and `0x21`. Because the board's MIPI CSI port (`0`, `1`, or `2`) and lane count (`2` or `4`) are unknown, sweep `--csi-port`:

```sh
sudo modprobe yt11-cam-probe
sudo modprobe mt6785-camsv-tm
for port in 0 1 2; do
  sudo python3 tools/camera/ov-cap.py \
    --csi-port "$port" --lanes 2 --i2c-bus 2 --i2c-addr 0x36 \
    --testpat --out "/tmp/ov-csi${port}.raw" --png "/tmp/ov-csi${port}.png"
done
```

Look for the port where:
1. `ANA +0x48 & 0x29 == 0x29` (calibration + LPRX ready).
2. `CSI2 PKT_CNT` (`+0xdc`) and `LINE_FRAME` (`+0xd0`) are non-zero (e.g. `0x01e101e1`), and `DPHY +0x30` leaves idle (`0x01`) for HS (`0x10`).
3. `MUX2 SIZE` (`0x2d30`) and `CAM_MUX2 CHK_RES` (`0x528`) show `0x01e00280` (`480 x 640`).
4. `CAMSV0 TG_FRMSIZE` (`0x268`) shows `0x028001e0`/`0x028001e1` and `frame:` reports `384000` bytes written.

If HAL's default `{0->0, 1->2, 2->4}` SENINF assignment does not match, override `--seninf 0..4`. If CAMSV DMA hangs in `IMGO_ERR` when streaming starts after CAMSV enable, retry after a reboot with `--stream-first`.

---

## 3. Register Map and Value Provenance

Every register offset and value below comes from `src/begonia-ftp/camera/NOTES.md`, `seninf/seninf-tm.c`, `camsv/camsv-tm.c`, `camsv/cap1.sh`, `camsv/larb-bypass.py`, `ov8856-mipi/ov-cap.py`, and `ref/isp7-v1/src/`.

### 3.1 SoC Base Windows and Clocks

| Block / Register | Base / Offset | Value | Source |
|---|---|---|---|
| `SENINF` window | `0x1a040000` (`0x6000`) | `seninfN` ctrl `+0x200+0x1000*N`, TG `+0x600+0x1000*N`, CSI2 `+0xa00+0x1000*N`, MUX `+0xd00+0x1000*N`, CAM_MUX `+0x400` | `NOTES.md` L179-181, `seninf-tm.c` L8-15, L32-37 |
| `CAMSV0` window | `0x1a050000` (`0x1000`) | `camsvN` at `0x1a050000 + 0x1000*N` | `NOTES.md` L190, `gen-camera-dtsi.py` L200 |
| `CAMSYS` window | `0x1a000000` (`0x1000`) | Clock controller (`clk-mt6785-cam.c`) | `mt6785.dtsi` L2030-2034, `gen-camera-dtsi.py` L201 |
| `MIPI_RX_ANA` | `0x11c80000` (`0xc000`) | Port `p` (`0..2`) at `+0x4000*p`: ANA-A `+0x0000`, ANA-B `+0x1000`, DPHY `+0x2000`, CPHY `+0x3000` | `NOTES.md` L181, L310-311, `gen-camera-dtsi.py` L202 |
| `APMIXEDSYS` gate | `0x1000c000 + 0x20` | Bits `6` (`apmixed_mipic0`) and `11` (`apmixed_mipic1`) = `1` (`0x840`) | `NOTES.md` L296-300, `ov-cap.py` L114-117, `clk-mt6785-apmixed.c` L30, L34 |
| `LARB6` / `LARB7` | `0x1a001000` (31 ports) / `0x1a002000` (5 ports) | `SMI_LARB_NONSEC_CON` (`0x380 + 4*i`) &= `~1` (`MMU_EN = 0`) | `NOTES.md` L248-249, `larb-bypass.py` L6-10 |

### 3.2 SENINF Test Model (`mt6785-seninf-tm.c` and `cap-tm.sh`)

| Block + Offset | Register | Value | Source |
|---|---|---|---|
| `SENINF_CAMMUX + 0x10` | `SENINF_CAM_MUX_EN` | `\|= 0x1f` (enable cam_mux 0..4) | `seninf-tm.c` L105, `cap1.sh` L13, `mtk_cam-seninf-cammux.h` L49 |
| `SENINF_CAMMUX + 0x18` | `SENINF_CAM_MUX_CHK_EN` | `\|= 0x1` (enable mux0 size check) | `seninf-tm.c` L106 |
| `SENINF_MUX(n) + 0x04` | `SENINF_MUX_CTRL_1` | `0x001f0001` (source=testmdl, 1-pixel mode) | `seninf-tm.c` L17, L107, `cap1.sh` L16 |
| `SENINF_MUX(n) + 0x00` | `SENINF_MUX_CTRL_0` | `0x1` (mux enable) | `seninf-tm.c` L108, `cap1.sh` L17 |
| `SENINF_MUX(n) + 0xa8` | `FRAME_SIZE_MON_CTRL` | `0x1` (enable H/V valid counters) | `seninf-tm.c` L109 |
| `SENINF_CTRL(n) + 0x20` | `SENINF_TESTMDL_CTRL` | `0x1` (route test model to SENINF) | `seninf-tm.c` L110, `cap1.sh` L18 |
| `SENINF_CTRL(n) + 0x00` | `SENINF_CTRL` | `0x1` (SENINF enable) | `seninf-tm.c` L111, `cap1.sh` L19 |
| `SENINF_TG(n) + 0x0c` | `TM_SIZE` | `0x10001f00` (`4096x7936` in `seninf-tm`) / `(L<<16)\|W` (`0x01e00280` in `cap-tm.sh`) | `seninf-tm.c` L39, L112, `cap1.sh` L20 |
| `SENINF_TG(n) + 0x10` | `TM_CLK` | `7` | `seninf-tm.c` L43, L113, `cap1.sh` L21 |
| `SENINF_TG(n) + 0x18` | `TM_DUM` | `0x00640064` (dummy blanking in `cap1.sh`) | `cap1.sh` L22, `NOTES.md` L253 |
| `SENINF_TG(n) + 0x08` | `TM_CTL` | `0x00300161` (enable + pattern `0x16` gradient hatching) | `seninf-tm.c` L41, L114, `cap1.sh` L23, `NOTES.md` L274, L283 |

### 3.3 CAMSV0 Capture (`cap-tm.sh` and `ov-cap.py`)

| Offset | Register | Value | Source |
|---|---|---|---|
| `0x230`, `0x234`, `0x510`, `0x110` | Pre-reset stop | `0`, `0`, `0x40000000` (DB bit30), `0` | `cap1.sh` L26, `ov-cap.py` L193 |
| `0x520` | `CAMSV_SW_CTL` | `4 -> 0 -> 1` (wait `== 3`), then `0` | `NOTES.md` L217, `cap1.sh` L27 |
| `0x238` | `CAMSV_TG_SEN_GRAB_PXL` | `(W << 16)` (`0x02800000` for 640 px) | `NOTES.md` L221, L240, `cap1.sh` L29 |
| `0x23c` | `CAMSV_TG_SEN_GRAB_LIN` | `(L << 16)` (`0x01e00000` for 480 lines) | `NOTES.md` L221, L240, `cap1.sh` L30 |
| `0x020` | `IMGO_BASE_ADDR` | CMA physical address (`buf` phys) | `NOTES.md` L222, `cap1.sh` L31 |
| `0x030` | `IMGO_XSIZE` | `BPL - 1` (`W*10/8 - 1` = `799` = `0x31f`) | `NOTES.md` L284, `cap1.sh` L32 |
| `0x034` | `IMGO_YSIZE` | `L - 1` (`479` = `0x1df`) | `NOTES.md` L284, `cap1.sh` L33 |
| `0x038` | `IMGO_STRIDE` | `BPL` (`800` = `0x320`, **no bit 24 flag**) | `NOTES.md` L282-284, `cap1.sh` L34 |
| `0x040`, `0x044` | `IMGO_CON2`, `IMGO_CON3` | `0x00020002` | `NOTES.md` L223, L284, `cap1.sh` L35 |
| `0x514` | `CAMSV_FMT_SEL` | `0x101` (`TG1_FMT = 1` = RAW10) | `NOTES.md` L232, L285, `cap1.sh` L36 |
| `0x54c` | `CAMSV_PAK` | `0x2` (RAW10 packing) | `NOTES.md` L233, L285, `cap1.sh` L37 |
| `0x110` | `FBC_IMGO_CTL1` | `0x8000` (`FBC_EN`, no bits 16/22), then `0x8001` (`RCNT_INC`) | `NOTES.md` L272-273, L285, `cap1.sh` L38, L47 |
| `0x530` | `CAMSV_CLK_EN` | `0x8005` (TG bit0 \| PAK bit2 \| DMA bit15) | `NOTES.md` L233, L285, `cap1.sh` L40 |
| `0x510` | `CAMSV_MODULE_EN` | `0x40000015` (DB bit30 \| IMGO bit4 \| PAK_EN bit2 \| TG bit0) | `NOTES.md` L232, L285, `cap1.sh` L41 |
| `0x518` | `CAMSV_INT_EN` | `0xffffffff` | `NOTES.md` L285, `cap1.sh` L42 |
| `0x400` | DMAO enable (`libimageio_plat_drv`) | `0x1` | `NOTES.md` L219, L285, `cap1.sh` L42 |
| `0x234` | `CAMSV_TG_VF_CON` | `0x1` (`VFDATA_EN`) | `NOTES.md` L221, L285, `cap1.sh` L43 |
| `0x230` | `CAMSV_TG_SEN_MODE` | `0x10001` (bit16 \| `CMOS_EN` bit0, 1-pixel mode) | `NOTES.md` L220, L239-241, L285, `cap1.sh` L44 |

### 3.4 Real Sensor MIPI RX PHY / CSI2 / Routing (`ov-cap.py`)

| Block + Offset | Value / Formula | Source |
|---|---|---|
| `ANA_A/B +0x4,+0x8,+0xc,+0x18..+0x20,+0x28,+0x30,+0x34,+0x3c` | `phyA_init`: biasing, termination, clock/data pad config | `ov-cap.py` L120-139, `NOTES.md` L168 |
| `DPHY +0x20..+0x2c` | `dphy_init`: settle `[15:8]` (`15` default), `[23:16]=0x20`, bit 29 | `ov-cap.py` L140-143 |
| `CPHY +0x18` | `\|= 0x10` (`setSeninfCsiMipi` between `dphy_init` and `csi2_setting`) | `NOTES.md` L305, `ov-cap.py` L145 |
| `SENINF_CSI2(seninf)` `+0x10,+0x8,+0x4,+0xc0,+0x0,+0xe0` | `RESYNC\|=0x100`, `HDR_MODE=0`, `CPHY_SEL=0`, `IRQ_EN\|=0x80000000`, `CSI2_EN=(1<<lanes)-1`, `DBG_CTRL=0xffffffff` | `NOTES.md` L184, L314-315, `ov-cap.py` L148-154, `mtk_cam-seninf-hw_phy_2_0.c` L1431-1446 |
| `SENINF_TOP + 0x60 + 4*csi_port` | `SENINF_TOP_PHY_CTRL_CSIp`: clear bit 1 (`CPHY_EN`), set bit 0 (`DPHY_EN`) | `ov-cap.py` L155, `mtk_cam-seninf-top-ctrl.h` L59-81 |
| `ANA_A/B +0x0` | `phyA_setting` (4D1C clock on A.L2) + `phyA_power_on` (`+0x18..+0x20`, bits `2,3` LPF/CORE, wait `+0x48 & 0x29 == 0x29`) | `NOTES.md` L312-313, `ov-cap.py` L157-177 |
| `DPHY +0x0`, `+0x4` | `dphy_setting`: lane mux, `0x1\|0x100..0x800`, `+0x4 \|= 0x80000000` (`CK_DATA_MUX_EN`) | `NOTES.md` L306, `ov-cap.py` L163-166, `mtk_cam-seninf-hw_phy_2_0.c` L1798-1813 |
| `SENINF_CTRL(seninf) +0x10, +0x0` | `\|= 1` (`CSI2_EN`, `SENINF_EN`) | `ov-cap.py` L179-180, `mtk_cam-seninf-hw_phy_2_0.c` L1468-1471 |
| `SENINF_TOP + 0x10/0x14` | `TOP_MUX_CTRL`: nibble at `8*(mux%4)` = `seninf` (e.g. mux2 `bits[19:16]`) | `NOTES.md` L303-304, `ov-cap.py` L181 |
| `SENINF_MUX(mux) +0x4,+0x8,+0x0,+0xa8` | Source `0x8` (MIPI), polarities `0`, toggle reset `0x6`, enable `1`, monitor `1` | `ov-cap.py` L182-187 |
| OV8856 I2C `0x3018` | `0x12` (1 lane), `0x32` (2 lanes), `0x72` (4 lanes) | `ov8856.c` L218, L602; `init.regs` L10 |

---

## 4. SoC-Generic vs Board-Specific

| Aspect | Classification | Details |
|---|---|---|
| SENINF, MIPI RX ANA/CDPHY, CAMSV0, CAMSYS, APMIXED, LARB6/7 register layouts & physical bases | **SoC-generic (MT6785)** | Identical across begonia and YT-J706F (`0x1a040000`, `0x1a050000`, `0x1a000000`, `0x11c80000`, `0x1000c000`, `0x1a001000`, `0x1a002000`). |
| Test-pattern capture (`mt6785-seninf-tm`, `mt6785-camsv-tm`, `cap-tm.sh`, `larb-bypass.py`, `raw2png.py`) | **SoC-generic (MT6785)** | Does not touch any sensor, I2C bus, GPIO, or external regulator. |
| HAL `getCSIInfo` mapping (`port -> seninf`: `0->0`, `1->2`, `2->4`) & `CAMSV0 = cam_mux 2` | **SoC-generic (MT6785)** | Hardcoded in MT6785 SENINF/CAM_MUX hardware and MediaTek HAL. |
| Sensor power, reset, MCLK pins (`yt11-cam-probe`) | **Board-specific (YT-J706F)** | `cam0` = reset GPIO119, MCLK GPIO117, shared `vcama` GPIO195 / `vcamd` GPIO50, `vcamaf` GPIO197 (`CAMERA.md` L31-36). No MIPI switch GPIO on YT-J706F (`CAMERA.md` L40). |
| Camera I2C bus & OV8856 address | **Board-specific (YT-J706F)** | OV8856 (`cam0`) is on `i2c2` (`/dev/i2c-2`, `0x11009000`) at `0x36` / `0x21` (`CAMERA.md` L62), vs begonia `i2c7` (`0x1101a000`) at `0x10` (`NOTES.md` L107). |
| Sensor CSI port & lane wiring | **Board-specific (YT-J706F, unknown)** | Determined by board PCB + vendor closed HAL; passed via `ov-cap.py --csi-port`, `--seninf`, `--lanes`, `--i2c-bus`, `--i2c-addr`. |
| Second camera sensor (`cam1`) | **Board-specific (YT-J706F)** | Samsung S5K4H7 at `0x2d` on `i2c4` (`/dev/i2c-4`, `CAMERA.md` L63), vs begonia S5K3T1/GC2375. `ov-cap.py` targets OV8856 only. |

---

## 5. Known Failure Modes from `begonia` and How to Recognise Them

1. **IOMMU translation still active (`IMGO_ERR`, buffer stays zero or `0xa5`):**
   - *Symptom:* `CAMSV0 INT_STATUS` (`0x51c`) has bit 16 (`IMGO_ERR`, e.g. `0x0001008f` or `0x0009048f`), `TG_FRMSIZE` (`0x268`) is valid (`0x028001e0`), and **no** IOMMU fault appears in `dmesg`, yet the DMA buffer is untouched.
   - *Cause:* `larb6` (`mtk-smi`) or `larb7` has `MMU_EN=1` (`SMI_LARB_NONSEC_CON` bit 0), so CAMSV treats the CMA physical address as an unmapped IOVA (`NOTES.md` L248-250).
   - *Fix:* Run `larb-bypass.py` after `camsv-tm/power=1` and verify all printed bits are `0`.

2. **Half-height frames (lines `240..479` untouched):**
   - *Symptom:* Only `50%` of expected bytes are written (`192000` of `384000` bytes for `640x480` RAW10), even though `TG_FRMSIZE` shows the full `640x480`.
   - *Cause:* Bit 24 (`0x01000000`) set in `IMGO_STRIDE` (`0x038`), causing DMA to pack two lines into one (`NOTES.md` L282-283).
   - *Fix:* Write `IMGO_STRIDE = BPL` (`800` = `0x320`) with no upper flag bits.

3. **TG stuck at `0` lines after `rmmod`/`insmod` (`TG_FRMSIZE = 0x02800000`):**
   - *Symptom:* `CAMSV0 INT_STATUS` shows `0x00030097` (`TG_ERR` bit 4 + bits 16/17), `TG_FRMSIZE` reads `0x02800000` (width OK, 0 lines), `TG_INTER_ST` (`0x26c`) reads `0x105` instead of `0x...207` (`NOTES.md` L251-252, L260).
   - *Cause:* Unloading and reloading `camsv-tm` in the same boot left CAMSV/SENINF state wedged.
   - *Fix:* Do not `rmmod`/`insmod` `mt6785-camsv-tm` during a test session; reboot cleanly and run once.

4. **FBC bits `16`/`22` stall DMA (`FBC_IMGO_CTL1 = 0x418000` / `0x18000`):**
   - *Symptom:* `INT_STATUS` reports `TG_ERR` (e.g. `0x0001009f`), `FBC_CTL2` stays `0`, nothing is written (`NOTES.md` L234, L273).
   - *Fix:* Use `FBC_IMGO_CTL1 = 0x8000` (`FBC_EN` only), then `0x8001` (`RCNT_INC`) after a short delay to latch one clean frame.

5. **APMIXED 26 MHz MIPI-CSI clocks off (real sensor only):**
   - *Symptom:* `ANA +0x48` reads `0` instead of `& 0x29 == 0x29`, `DPHY +0x30` only toggles LP states (never `0x10` HS), and `CSI2` packet/IRQ counters remain `0` (`NOTES.md` L296-299).
   - *Cause:* `0x1000C020` bits 6 (`apmixed_mipic0`) and 11 (`apmixed_mipic1`) are off (`0x20` at boot).
   - *Fix:* `mt6785-camsv-tm` enables `CLK_APMIXED_MIPIC0`/`1` via CCF on `power=1`, and `ov-cap.py` verifies `0x1000C020 & 0x840 == 0x840`.

6. **Real-sensor CAMSV DMA stall when armed before stream-on (`NOTES.md` L322-325):**
   - *Symptom:* `CSI2`, `MUX2`, `CAM_MUX2`, and `CAMSV0 TG_FRMSIZE` all show `640x480` (or `640x481`), but `INT_STATUS` is `0x0009048f`, `FBC_CTL2` is `0xf4000001`, and the buffer remains `0xa5`.
   - *Fix:* Reboot and test `ov-cap.py --stream-first` (starts OV8856 streaming before resetting and arming `CAMSV0`), and check whether `OV8856` emits 481 lines vs `480` in `TG_SEN_GRAB_LIN`.

---

## 6. Open Questions

1. **YT-J706F CSI-2 port, SENINF index, and lane count for OV8856 (`cam0`) and S5K4H7 (`cam1`):** Not listed in the stock DT (`CAMERA.md` L50-51, L66-68); must be determined on the tablet by sweeping `ov-cap.py --csi-port 0|1|2`.
2. **Real-sensor DMA write after `APMIXED` fix:** On `begonia`, `SENINF` and `CAMSV TG` saw `640x481` from OV8856, but `CAMSV0` IMGO DMA still stalled with `0x0009048f` when CAMSV was configured prior to stream-on (`NOTES.md` L322-325). Confirming `--stream-first` vs `GRAB_LIN` (`480` vs `481`) remains to be tested on hardware.
3. **Proper camera IOMMU instead of `larb-bypass.py`:** `larb6` ports in `mt6785.dtsi` and missing `larb7` (`0x1a002000`) DT node need IOMMU port mapping once raw capture works, before building a V4L2/videobuf2 driver.
4. **S5K4H7 (`cam1`) register tables and 24 MHz PLL settings:** `ov-cap.py` covers `OV8856` (`cam0`) only; `cam1` (`S5K4H7` on `i2c4` `0x2d`) will need its own register table when ready.
5. **Remaining `TG_ERR` (bit 4) / `IMGO_ERR` (bit 16) / bit 19 flags in `INT_STATUS` (`0x0009049f`)** even during successful full-frame test-pattern captures (`NOTES.md` L286).
