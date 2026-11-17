# Mainline Gap Analysis for YT-J706F Camera Bring-up (MT6785 / Kernel 7.1)

## Corrections (2026-11-17)

Two register readings in the CAMSV table below (section on CAMSV
registers) were corrected by measurements on the unit; see
`docs/hardware/CAMERA.md` ("Frame layout and first photo", "FBC and
interrupts") and `docs/research/camera/T8-V4L2.md` sections 0g-0i:

- `FBC_IMGO_CTL1` `|= 1` is **not** an "RCNT_INC" release: the low 6-bit
  field is a compare value against the written-frame count
  (`CTL2[6:0]`), and `CTL2[31:24]` is a drop counter, not a frame
  counter.  Writing `0x8001` yields exactly one frame per stream; the
  DMA runs free while the compare value stays ahead of the count.
- `FMT_SEL = 0x101` / `PAK = 2` does not give MIPI RAW10 on this board:
  it writes 12-bit containers and truncates lines.  The complete-frame
  configuration is `FMT_SEL = 0x102` / `PAK = 1` with the line sized for
  10 bits (continuous little-endian 10-bit bit stream per line).

Scope: Gap analysis against `src/mt6785-mainline` (Linux 7.1, branch `yt11`), `kernel/configs/{pmos-mt6785,yoga11}.config`, `docs/hardware/{CAMERA,BOARD}.md`, `src/begonia-ftp/`, and `src/lenovo-gpl-4.14/`. Every "present" item cites `file:line`; missing items specify the exact register, bit, parent clock, or DT/driver change needed.

---

## 1. Clocks

### 1.1 `camsys` and `imgsys` clock providers

| Item | Status | Location in `src/mt6785-mainline` | Details |
|---|---|---|---|
| `camsys` driver | **Present** | `drivers/clk/mediatek/clk-mt6785-cam.c:12-54` | `compatible = "mediatek,mt6785-camsys"`. Set/clr/sta regs at `0x4`/`0x8`/`0x0`. Gates (all parented to `"top_cam"`): `CLK_CAM_LARB6` (bit 0), `CLK_CAM_LARB7` (bit 2), `CLK_CAM_GALS` (bit 4), `CLK_CAM_MAIN` (bit 6), `CLK_CAM_TG` (bit 7), `CLK_CAM_SENINF` (bit 8), `CLK_CAM_SV0` (bit 9), `CLK_CAM_SV1` (bit 10), `CLK_CAM_CCU` (bit 12), `CLK_CAM_FAKE_ENG` (bit 13). |
| `camsys` bindings & DT | **Present** | `include/dt-bindings/clock/mediatek,mt6785-clk.h:91-102`; `arch/arm64/boot/dts/mediatek/mt6785.dtsi:2030-2034` | `camsys: clock-controller@1a000000`, `#clock-cells = <1>`. Enabled by `CONFIG_COMMON_CLK_MT6785_CAM=y` (`kernel/configs/pmos-mt6785.config:6061`). |
| `imgsys` driver | **Present** | `drivers/clk/mediatek/clk-mt6785-img.c:12-54` | `compatible = "mediatek,mt6785-imgsys"`. Gates (parent `"top_img"`): `CLK_IMG_LARB5` (bit 0), `CLK_IMG_LARB4` (bit 1), `CLK_IMG_DIP` (bit 2), `CLK_IMG_FDVT` (bit 3), `CLK_IMG_DPE` (bit 4), `CLK_IMG_RSC` (bit 5), `CLK_IMG_MFB` (bit 6), `CLK_IMG_WPE_A` (bit 7), `CLK_IMG_WPE_B` (bit 8), `CLK_IMG_OWE` (bit 9). |
| `imgsys` bindings & DT | **Present** | `include/dt-bindings/clock/mediatek,mt6785-clk.h:104-115`; `arch/arm64/boot/dts/mediatek/mt6785.dtsi:1957-1961` | `imgsys: clock-controller@15020000`, `#clock-cells = <1>`. Enabled by `CONFIG_COMMON_CLK_MT6785_IMG=y` (`kernel/configs/pmos-mt6785.config:6062`). |
| `camsv2..5` gates (`CAMSV3..6`) | **Absent** (vendor also omits) | `drivers/clk/mediatek/clk-mt6785-cam.c:29-30`; cf. `src/lenovo-gpl-4.14/include/dt-bindings/clock/mt6785-clk.h:209-210` | Only `CLK_CAM_SV0` and `CLK_CAM_SV1` exist (vendor `mt6785.dts:4107-4139` declares `camsv1..6`, and `clk-mt6785-pg.c:5142` mentions `camsys_camsv2`, but `mt6785-clk.h` only has SV0/SV1). `CAMSV0` (`0x1a050000`) is sufficient for capture. |

### 1.2 `CAMTG1..5` muxes and parents (24 MHz MCLK)

* **Present** in `drivers/clk/mediatek/clk-mt6785-top.c:222-231` (`camtg_parents`) and `:491-494, 548` (`top_mux_clks`); bindings in `include/dt-bindings/clock/mediatek,mt6785-clk.h:319-324, 366-369, 404`; provider `topckgen: clock-controller@10000000` in `arch/arm64/boot/dts/mediatek/mt6785.dtsi:881-885`:
  * `CLK_TOP_CAMTG1` (76): `TOP_MUX_GATE(4, ..., 0, 3, 7, 16)`
  * `CLK_TOP_CAMTG2` (77): `TOP_MUX_GATE(4, ..., 8, 3, 15, 17)`
  * `CLK_TOP_CAMTG3` (78): `TOP_MUX_GATE(4, ..., 16, 3, 23, 18)`
  * `CLK_TOP_CAMTG4` (79): `TOP_MUX_GATE(4, ..., 24, 3, 31, 19)`
  * `CLK_TOP_CAMTG5` (114): `TOP_MUX_GATE(13, ..., 24, 3, 31, 56)`
* **`camtg_parents[]`** (`clk-mt6785-top.c:222-231`):
  0. `clk26m` — 26 MHz (`mt6785.dtsi:801-806`)
  1. **`univpll_192m_d8`** (`CLK_TOP_UNIVPLL_192M_D8` = 32) — **24 MHz** (`univ2pll` at 2496 MHz -> `/13` = `univpll_192m` at 192 MHz at `clk-mt6785-top.c:83` -> `/8` = 24 MHz at `clk-mt6785-top.c:86`)
  2. `univpll_d3_d8` — 52 MHz
  3. `univpll_192m_d4` — 48 MHz
  4. `univpll_d3_d16` — 26 MHz
  5. `clk13m` — 13 MHz (`mt6785.dtsi:792-799`)
  6. `univpll_192m_d16` — 12 MHz
  7. `univpll_192m_d32` — 6 MHz
* **Gap (DT + sensor clock rate):**
  1. `mt6785-lenovo-yt-j706f.dts` has no real V4L2 sensor nodes yet (a concurrent M0 staging `camera-probe` node at `:103-126` temporarily holds `CAMTG1..5` and `CLK_TOP_UNIVPLL_192M_D8`; real sensor nodes will need `assigned-clocks` / `assigned-clock-parents` selecting `CLK_TOP_UNIVPLL_192M_D8`, since YT-J706F uses `CMMCLK1` on GPIO117 and `CMMCLK2` on GPIO120 and the exact `CMMCLKn -> CAMTGm` pairing is unverified).
  2. `camtg_parents` cannot produce 19.2 MHz (only 26/24/52/48/13/12/6 MHz), whereas mainline `drivers/media/i2c/ov8856.c:23, 2292` expects `19200000` Hz.

### 1.3 SENINF clocks

* **Present:**
  * Topckgen muxes (`drivers/clk/mediatek/clk-mt6785-top.c:343-348, 522-524`; `include/dt-bindings/clock/mediatek,mt6785-clk.h:387-389`):
    * `CLK_TOP_SENINF0` (97), `CLK_TOP_SENINF1` (98), `CLK_TOP_SENINF2` (99) — `TOP_MUX_GATE(9, ..., 8/16/24, 2, 15/23/31, 38/39/40)` with `seninf_parents`: `clk26m` (26 MHz), `univpll_d7` (~178.3 MHz), `univpll_d3_d2` (208 MHz), `univpll_d2_d2` (312 MHz).
  * `CLK_TOP_CAMTM` (111, `clk-mt6785-top.c:446-451, 542`) and `CLK_TOP_SCAM` (91, `clk-mt6785-top.c:311-314, 514`).
  * Camsys gates (`drivers/clk/mediatek/clk-mt6785-cam.c:25-28`; `include/dt-bindings/clock/mediatek,mt6785-clk.h:94-97`): `CLK_CAM_GALS`, `CLK_CAM_MAIN`, `CLK_CAM_TG`, `CLK_CAM_SENINF` (plus `CLK_CAM_SV0`, `CLK_CAM_SV1` at `:29-30`).
* **Gap:** No `seninf` DT node exists in `mt6785.dtsi` to claim these clocks.

### 1.4 APMIXEDSYS MIPI 26 MHz gates (`0x1000C020`)

* **Present in `src/mt6785-mainline` (unlike older 6.16 begonia notes):**
  * `drivers/clk/mediatek/clk-mt6785-apmixed.c:13-39`: `apmixed_cg_regs` uses offset `0x20` (`sta_ofs = clr_ofs = set_ofs = 0x20`) with `mtk_clk_gate_ops_no_setclr_inv` (bit = 1 enables the clock), matching `0x1000C020`:
    * `CLK_APMIXED_MIPIC0` (15, `"apmixed_mipic0"`, parent `"clk26m"`, bit **6**) — `clk-mt6785-apmixed.c:30`, `include/dt-bindings/clock/mediatek,mt6785-clk.h:25`
    * `CLK_APMIXED_MIPIC1` (19, `"apmixed_mipic1"`, parent `"clk26m"`, bit **11**) — `clk-mt6785-apmixed.c:34`, `include/dt-bindings/clock/mediatek,mt6785-clk.h:29`
    * (DSI gates `CLK_APMIXED_MIPID0` bit 16 and `CLK_APMIXED_MIPID1` bit 17 are at `:37-38`.)
  * DT provider `apmixedsys: clock-controller@1000c000` is at `arch/arm64/boot/dts/mediatek/mt6785.dtsi:1045-1049`.
* **Gap (DT wiring only):** No DT consumer references `CLK_APMIXED_MIPIC0` or `CLK_APMIXED_MIPIC1`, so CCF leaves bits 6 and 11 cleared (0). Without them, `mipi_rx_ana` calibration (`ANA+0x48`) stays 0 and D-PHY receives zero packets (`src/begonia-ftp/camera/NOTES.md:296-300`). The future SENINF/CSIRX DT node must include:
  ```dts
  clocks = /* ... camsys + top_seninf0..2 ... */
           <&apmixedsys CLK_APMIXED_MIPIC0>,
           <&apmixedsys CLK_APMIXED_MIPIC1>;
  ```

---

## 2. Power Domains (`CAM`, `ISP`, dependencies, `scpsys`)

| Item | Status | Location in `src/mt6785-mainline` | Details |
|---|---|---|---|
| Power domain IDs | **Present** | `include/dt-bindings/power/mediatek,mt6785-power.h:7, 9, 17` | `MT6785_POWER_DOMAIN_CAM` = `1`, `MT6785_POWER_DOMAIN_ISP` = `3`, `MT6785_POWER_DOMAIN_MM` = `11`. |
| `scpsys` DT nodes | **Present** | `arch/arm64/boot/dts/mediatek/mt6785.dtsi:920-928, 988-1015` | `power-domain@MT6785_POWER_DOMAIN_CAM` (`:999-1006`, clock `CLK_TOP_CAM`, `mediatek,infracfg`, `mediatek,smi = <&smi_common>`) and `power-domain@MT6785_POWER_DOMAIN_ISP` (`:1008-1015`, clock `CLK_TOP_IMG`, `mediatek,infracfg`, `mediatek,smi = <&smi_common>`) are nested under `power-domain@MT6785_POWER_DOMAIN_MM` (`:988-997`). |
| `scpsys` driver & domain tables | **Present** | `drivers/pmdomain/mediatek/mtk-pm-domains.c:619-680, 1153-1154`; `drivers/pmdomain/mediatek/mt6785-pm-domains.h:74-88, 101-114, 190-217` | Handled by `compatible = "mediatek,mt6785-power-controller"` (`CONFIG_MTK_SCPSYS=y`, `CONFIG_MTK_SCPSYS_PM_DOMAINS=y`, `kernel/configs/pmos-mt6785.config:6342-6343`). `mt6785-lenovo-yt-j706f.dts:806-808` deletes only `power-domain@4` (`MD`); `MM`, `CAM`, and `ISP` remain enabled. |
| Bus protection (`CAM`, `ISP`, `MM`) | **Present** | `drivers/pmdomain/mediatek/mt6785-pm-domains.h:74-88, 101-114` | `CAM`: `sta_mask = BIT(25)`, `ctl_offs = 0x324`, SRAM pdn `GENMASK(9,8)`/ack `GENMASK(13,12)`, `bp_cfg`: `INFRA_TOPAXI_MM` (`BIT(4)\|BIT(5)\|BIT(9)\|BIT(13)`, then `BIT(11)`), `INFRA_TOPAXI` (`BIT(28)`), `SMI_COMMON_CLAMP_EN` (`GENMASK(7,6)`). `ISP`: `sta_mask = BIT(5)`, `ctl_offs = 0x308`, SRAM pdn `BIT(8)`/ack `BIT(12)`, `bp_cfg`: `INFRA_TOPAXI_MM` (`BIT(3)\|BIT(8)`, then `BIT(10)`), `SMI_COMMON_CLAMP_EN` (`BIT(4)`). |
| LARB / GALS dependency | **Partial** | `arch/arm64/boot/dts/mediatek/mt6785.dtsi:1963-1972, 2036-2045` | `larb5` (`ISP`, `CLK_MM_GALS_IMG2MM`) and `larb6` (`CAM`, `CLK_MM_GALS_CAM2MM`) are wired to their domains and `&smi_common`. **`larb7`** (`0x1a002000`, `CLK_CAM_LARB7`, `MT6785_POWER_DOMAIN_CAM`) and **`larb4`** (`CLK_IMG_LARB4`) are missing from `mt6785.dtsi`. |

Note: Begonia's test modules attached both `CAM` and `CONN` in DT (`src/begonia-ftp/camera/gen-camera-dtsi.py:183, 203`), but only resumed `CAM` (`seninf-tm.c:70-77`, `camsv-tm.c:58-64`), confirming `MT6785_POWER_DOMAIN_CAM` (with its parent `MM`) is sufficient.

---

## 3. IOMMU and SMI

| Item | Status | Location in `src/mt6785-mainline` | Details |
|---|---|---|---|
| M4U / IOMMU node & driver | **Present** | `arch/arm64/boot/dts/mediatek/mt6785.dtsi:1086-1093`; `drivers/iommu/mtk_iommu.c:1593-1604, 1919` | `iommu: iommu@10220000` (`compatible = "mediatek,mt6785-iommu-mm"`, `#iommu-cells = <1>`). `mt6785_data_mm` enables `OUT_ORDER_WR_EN \| HAS_SUB_COMM_2BITS \| WR_THROT_EN \| MTK_IOMMU_TYPE_MM \| PGTABLE_PA_35_EN`, 1 bank. Enabled by `CONFIG_MTK_IOMMU=y` (`pmos-mt6785.config:6228`). |
| `smi_common` | **Present** (via `mt6779` fallback) | `arch/arm64/boot/dts/mediatek/mt6785.dtsi:1916-1924`; `drivers/memory/mtk-smi.c:789-795, 870` | `compatible = "mediatek,mt6785-smi-common", "mediatek,mt6779-smi-common"`. Uses `mtk_smi_common_mt6779` (`has_gals = true`, `bus_sel = F_MMU1_LARB(1\|2\|4\|5\|6\|7)`). Enabled by `CONFIG_MTK_SMI=y` (`pmos-mt6785.config:6386`). |
| `larb5` (ISP) & `larb6` (CAM) | **Present** | `arch/arm64/boot/dts/mediatek/mt6785.dtsi:1963-1972, 2036-2045`; `drivers/memory/mtk-smi.c:294-298, 517-521, 574` | `larb5@15021000` (26-port OSTD table), `larb6@1a001000` (31-port OSTD table). Both are in `iommu`'s `mediatek,larbs` (`mt6785.dtsi:1090-1091`). |
| `larb7` (CAMSV / CAM) | **Missing from DT & `mtk_iommu`** | Driver partial: `drivers/memory/mtk-smi.c:299` (`ostd[7]`), `drivers/clk/mediatek/clk-mt6785-cam.c:24` (`CLK_CAM_LARB7`); cf. `src/lenovo-gpl-4.14/arch/arm64/boot/dts/mediatek/mt6785.dts:4074-4081` | `mtk-smi.c:299` already has the 5-port OSTD table `[7] = {0x1f, 0x14, 0x1f, 0x1f, 0x14}`, and `clk-mt6785-cam.c:24` has `CLK_CAM_LARB7`, **but**: (1) `larb7: larb@1a002000` is missing from `mt6785.dtsi`, (2) `&larb7` is missing from `iommu`'s `mediatek,larbs` (`mt6785.dtsi:1090-1091`), and (3) `mt6785_data_mm.larbid_remap` in `drivers/iommu/mtk_iommu.c:1597-1598` is `{{0}, {1}, {2}, {3}, {5}, {MTK_INVALID_LARBID}, {MTK_INVALID_LARBID}, {6}}` (no larb 7 entry). |
| Port IDs for `IMGO` / `CAMSV` | **`IMGO` present; `CAMSV`/`larb7` missing** | `include/dt-bindings/memory/mediatek,mt6785-memory-port.h:69-126` | Line 96 defines `M4U_PORT_CAM_IMGO` = `MTK_M4U_ID(6, 0)` (larb 6, ports 0..30 defined; larb 5 `M4U_PORT_IMG_IMGI`..`FDVT_WRB` at `:69-94`). **No `larb7` / `CAMSV` port IDs** exist (vendor `src/lenovo-gpl-4.14/drivers/misc/mediatek/include/mt-plat/mt6785/include/mach/mt_iommu_port.h:245-319` and `mt_iommu_plat.h:40` also mark `iommu_null_larb7` and omit larb 7). |

**Why begonia needed a LARB bypass (`src/begonia-ftp/camera/camsv/larb-bypass.py`):**
Hardware reset leaves `MMU_EN` (bit 0 of `SMI_LARB_NONSEC_CON` at `0x380 + 4 * port`) = `1` on all ports of `larb6` (`0..30`) and `larb7` (`0..4`). In `drivers/memory/mtk-smi.c:277-282`, `mtk_smi_larb_config_port_gen2_general()` only sets `F_MMU_EN` for ports listed in `larb->mmu` and **never clears** `F_MMU_EN` for ports that have no IOMMU consumer attached. Thus, without an `iommus = <&iommu ...>` binding on the CAMSV node, CAMSV DMA treats physical CMA addresses as untranslated IOVAs and fails with `IMGO_ERR` (`NOTES.md:248-250`). Which exact port (larb 6 port 0 `M4U_PORT_CAM_IMGO` vs one of larb 7 ports 0..4) CAMSV0 uses must be verified by enabling `MMU_EN` port-by-port (`NOTES.md:266-267`).

DT snippet needed if `larb7` is added to `mt6785.dtsi`:
```dts
/* Under &iommu (mt6785.dtsi:1090-1091): append <&larb7> */
mediatek,larbs = <&larb0>, <&larb1>, <&larb2>,
		 <&larb3>, <&larb5>, <&larb6>, <&larb7>;

/* Under &soc (after larb6 at mt6785.dtsi:2045): */
larb7: larb@1a002000 {
	compatible = "mediatek,mt6785-smi-larb";
	reg = <0 0x1a002000 0 0x1000>;
	mediatek,smi = <&smi_common>;
	mediatek,larb-id = <7>;
	clocks = <&camsys CLK_CAM_LARB7>, <&camsys CLK_CAM_LARB7>;
	clock-names = "apb", "smi";
	power-domains = <&spm MT6785_POWER_DOMAIN_CAM>;
};
```
(Plus adding `MTK_M4U_ID(7, 0..4)` macros to `include/dt-bindings/memory/mediatek,mt6785-memory-port.h` and checking `larbid_remap` in `mtk_iommu.c:1597` if CAMSV DMA masters are on larb 7.)

---

## 4. Pinctrl & I2C Buses

### 4.1 Pin functions in `src/mt6785-mainline`

All pin definitions exist in `include/dt-bindings/pinctrl/mediatek,mt6785-pinfunc.h` and `drivers/pinctrl/mediatek/pinctrl-mtk-mt6785.h`:

| YT-J706F Signal (`docs/hardware/CAMERA.md:31-36`) | GPIO | Required Pinfunc Macro(s) | `mediatek,mt6785-pinfunc.h` | `pinctrl-mtk-mt6785.h` |
|---|---|---|---|---|
| `cam0` MCLK | GPIO117 | `PINMUX_GPIO117__FUNC_CMMCLK1` (func 1) / `FUNC_GPIO117` (func 0) | `:738-739` | `:1210-1216` |
| `cam1` MCLK | GPIO120 | `PINMUX_GPIO120__FUNC_CMMCLK2` (func 1) / `FUNC_GPIO120` (func 0) | `:753-754` | `:1237-1244` |
| `cam0` Reset | GPIO119 | `PINMUX_GPIO119__FUNC_GPIO119` (func 0) | `:748` | `:1228-1234` |
| `cam1` Reset | GPIO124 | `PINMUX_GPIO124__FUNC_GPIO124` (func 0) | `:781` | `:1281-1290` |
| `vcama` switch (shared) | GPIO195 | `PINMUX_GPIO195__FUNC_GPIO195` (func 0) | `:1157` | `:1941-1950` |
| `vcamd` switch (shared) | GPIO50 | `PINMUX_GPIO50__FUNC_GPIO50` (func 0) | `:405` | `:609-617` |
| `cam0` `vcamaf` switch | GPIO197 | `PINMUX_GPIO197__FUNC_GPIO197` (func 0) | `:1174` | `:1966-1975` |
| I2C2 (`SCL2` / `SDA2`) | GPIO112 / GPIO113 | `PINMUX_GPIO112__FUNC_SCL2`, `PINMUX_GPIO113__FUNC_SDA2` (func 1) | `:718, 721` | `:1169-1181` |
| I2C4 (`SCL4` / `SDA4`) | GPIO110 / GPIO111 | `PINMUX_GPIO110__FUNC_SCL4`, `PINMUX_GPIO111__FUNC_SDA4` (func 1) | `:712, 715` | `:1155-1166` |
| MIPI CSI-2 data/clock | — | **Not GPIO-muxed** (dedicated analog PHY pads at `0x11c80000`). Note: `MIPI0..5_SCLK/SDATA` (`pinfunc.h:566-572, 651-685`) are RF RFFE pins, not CSI-2. | — | — |

**Drive-strength pitfall:** `drivers/pinctrl/mediatek/pinctrl-mt6785.c:972` uses `mtk_pinconf_drive_set_rev1` (`drivers/pinctrl/mediatek/pinctrl-mtk-common-v2.c:1087-1102`) with `DRV_GRP4` (`min=2, max=16, step=2` mA at `:45`). Setting vendor raw `drive-strength = <1>` returns `-ENOTSUPP` (`-524`) and rolls back the `CMMCLK` mux (`src/begonia-ftp/camera/NOTES.md:95-97`). Mainline DT must specify `drive-strength = <4>;` (or `<2>`/`<6>`/`<8>` mA).

### 4.2 I2C2 / I2C4 address matching, board DT status, and multi-channel driver gap

| Vendor Node (`src/lenovo-gpl-4.14/.../mt6785.dts`) | Base Reg | Mainline Label (`mt6785.dtsi`) | Used in YT-J706F Board DT? |
|---|---|---|---|
| `i2c2: i2c2@11009000` (`:2189-2192`) | `0x11009000` (DMA `0x11000180`, size `0x180`) | `i2c2: i2c@11009000` (`mt6785.dtsi:1176-1187`, `status = "disabled"`) | **Added by concurrent M0 commit** in `mt6785-lenovo-yt-j706f.dts:229-234` (`i2c2_pins` at `:635-641`, `400 kHz`); absent in baseline `yt11` and `-audio.dtsi`. |
| `i2c4: i2c4@11011000` (`:2231-2234`) | `0x11011000` (DMA `0x11000380`, size `0x180`) | `i2c4: i2c@11011000` (`mt6785.dtsi:1253-1264`, `status = "disabled"`) | **Added by concurrent M0 commit** in `mt6785-lenovo-yt-j706f.dts:254-259` (`i2c4_pins` at `:651-657`, `400 kHz`); absent in baseline `yt11` and `-audio.dtsi`. |

**Critical gap in `drivers/i2c/busses/i2c-mt65xx.c`:**
Vendor `mt6785.dts:2207-2208, 2249-2250` configures `ch_offset_default = <0x100>` (and `ch_offset_ccu = <0x200>`) on `i2c2` and `i2c4`. Mainline `i2c-mt65xx.c` has **no multi-channel support** (`mt6785` uses `mt8186_compat` at `mt6785.dtsi:1177, 1254`; `i2c-mt65xx.c:486-536`). On MT6785 camera I2C buses, channel 0 (`base + 0x0`) gets 0 interrupts and times out (`src/begonia-ftp/camera/NOTES.md:111-121, 144-147`; `src/begonia-ftp/camera/i2c-mch/mch-port.py`):
* Shadow config registers (`SOFTRESET`, `IO_CONFIG`, `DCM_EN`, `TIMING`, `LTIMING`, `HS`) must be written to channel 0 (`base`), and transaction registers to `base + 0x100`.
* Short transfers (`<= 8` bytes) must use FIFO PIO (not AP-DMA), write `MCU_INTR` (`0x40`) = `1`, set `FIFO_ADDR_CLR |= 0x4` (`MCH`), and **omit** `I2C_ACKERR` / `I2C_HS_NACKERR` from channel `INTR_MASK` (otherwise NACK jams `START = 0x3` until reboot).

DT pinctrl status in `mt6785-lenovo-yt-j706f.dts`: `i2c2_pins` (`:635-641`), `i2c4_pins` (`:651-657`), `cam_gpio_pins` (`:667-676`), and `cam0_mclk_off`/`cam0_mclk_on`/`cam1_mclk_off`/`cam1_mclk_on` (`:678-697+`, with `drive-strength = <4>`) were added for M0 probing; real V4L2 sensor nodes will also need `reset-gpios` and `regulator-fixed` nodes once `i2c-mt65xx.c` supports multi-channel (`ch_offset`).

---

## 5. Regulators

* **`vcamio` in mainline:** **Present** in `arch/arm64/boot/dts/mediatek/mt6359.dtsi:145-149` (included by `mt6785-lenovo-yt-j706f.dts:20`):
  * DT label: `mt6359_vcamio_ldo_reg: ldo_vcamio` (`regulator-name = "vcamio"`, `1700000`–`1900000` uV)
  * Driver: `drivers/regulator/mt6359-regulator.c:578, 815` (`"ldo_vcamio"`, `CONFIG_REGULATOR_MT6359=y` at `pmos-mt6785.config:3728`).
  * Referenced in `mt6785-lenovo-yt-j706f.dts:105` by the M0 staging `camera-probe` node, **not** yet bound to any V4L2 sensor node (`dovdd-supply = <&mt6359_vcamio_ldo_reg>;`).
* **Other PMIC LDOs (`vcama1/2`, `vcamd`, `vcn...`) in case GPIO switches gate a PMIC rail:**
  * MT6359 has **no `vcama1`, `vcama2`, or `vcamd` LDOs** (`mt6359.dtsi:102-301`, `mt6359-regulator.c:570-905`).
  * Existing MT6359 LDOs in `mt6359.dtsi` (available as `vin-supply` if gated by GPIO195/50/197):
    * `mt6359_vio18_ldo_reg` (`ldo_vio18`, 1.8 V, `always-on` in `yt-j706f.dts:541-545`)
    * `mt6359_vio28_ldo_reg` (`ldo_vio28`, 2.8–3.3 V, `always-on`, `mt6359.dtsi:218-223`)
    * `mt6359_vfe28_ldo_reg` (`ldo_vfe28`, 2.8 V, `:156-161`)
    * `mt6359_vbif28_ldo_reg` (`ldo_vbif28`, 2.8 V, `:212-217`)
    * `mt6359_va12_ldo_reg` (`ldo_va12`, 1.2–1.3 V, `always-on`, `:244-249`)
    * `mt6359_va09_ldo_reg` (`ldo_va09`, 0.8–1.2 V, `:250-254`, UFS)
    * `mt6359_vcn18_ldo_reg` (`ldo_vcn18`, 1.8 V, `always-on` in `yt-j706f.dts:537-539`)
    * `mt6359_vcn13_ldo_reg` (`ldo_vcn13`, 0.9–1.3 V, `mt6359.dtsi:162-166`)
    * `mt6359_vcn33_1_bt_ldo_reg` / `ldo_vcn33_1_wifi` / `ldo_vcn33_2_bt` / `ldo_vcn33_2_wifi` (2.8–3.5 V, `:167-176, 234-243`)
    * `mt6359_vemc_ldo_reg` / `ldo_vemc_1` (`:224-233`), `mt6359_vrf12_ldo_reg` / `ldo_vrf18` (`:118-122, 255-259`)
  * Existing MT6360 LDOs in `mt6785-lenovo-yt-j706f.dts:369-422`: `mt6360_vfp_ldo_reg` (`ldo1`), `mt6360_vtp_ldo_reg` (`ldo2`, `always-on`), `mt6360_vmc_ldo_reg` (`ldo3`, `always-on`), `mt6360_vmch_ldo_reg` (`ldo5`, `always-on`), `ldo6` (`vmddr`, `always-on`), `ldo7` (`vdram2`, `always-on`).
* **Missing in `mt6785-lenovo-yt-j706f.dts`:** `regulator-fixed` nodes for GPIO195 (`vcama`, 2.8 V `avdd`), GPIO50 (`vcamd`, 1.2 V `dvdd`), and GPIO197 (`vcamaf`; note `docs/hardware/CAMERA.md:36, 41` reports stock DT points `vcamaf` at `vcamio` while also declaring a GPIO197 switch).

---

## 6. Existing Media Drivers and Kernel Configuration

### 6.1 Drivers in `src/mt6785-mainline`

| Component | Driver File | Kconfig Symbol | Usable As-Is? |
|---|---|---|---|
| **OV8856** sensor | `drivers/media/i2c/ov8856.c` | `CONFIG_VIDEO_OV8856` (`drivers/media/i2c/Kconfig:675`, `Makefile:119`) | **Needs 24 MHz fix.** Binds and probes chip ID (`0x885a`) in DT mode, but `ov8856.c:23, 2292-2294` hardcodes `OV8856_XVCLK_19_2` (`19200000`) and logs `"external clock rate 24000000 is unsupported"`; PLL tables (`:165-209`) assume 19.2 MHz so link/pixel rates scale by `1.25x` at 24 MHz. |
| Second sensor (TBD: guessed S5K4H7?) | No `s5k4h7` driver in `drivers/media/i2c/` | — | **Missing** if not OV8856 (must identify over I2C2/I2C4 first). |
| **VCM** autofocus (`0x0c` in stock DT) | `drivers/media/i2c/ad5820.c`, `ak7375.c`, `dw9714.c`, `dw9719.c`, `dw9768.c`, `dw9807-vcm.c` | `CONFIG_VIDEO_AD5820` (`:881`), `CONFIG_VIDEO_AK7375` (`:888`), `CONFIG_VIDEO_DW9714` (`:896`), `CONFIG_VIDEO_DW9719` (`:905`), `CONFIG_VIDEO_DW9768` (`:913`), `CONFIG_VIDEO_DW9807_VCM` (`:921`) | Yes (once exact VCM chip at `0x0c` is identified; `dw9714`/`ak7375` are typical at `0x0c`). |
| **MT6360 flash LED** | `drivers/leds/flash/leds-mt6360.c` (`compatible = "mediatek,mt6360-led"` at `:878`) | `CONFIG_LEDS_MT6360` (`drivers/leds/flash/Kconfig:52`, `Makefile:3`) | Driver is usable as-is, **but** `mt6785-lenovo-yt-j706f.dts:321-460` has no `led-controller` child under `pmic@34` (cf. `mt6785-xiaomi-begonia-common.dtsi:283-315`) and tablet flash wiring is unverified. |
| **MT6785 SENINF / CAMSV / ISP** | **None** (`drivers/media/platform/mediatek/` has only `jpeg`, `mdp`, `mdp3`, `vcodec`, `vpu`) | — | **Missing** — must be written/ported (ISP7 `phy_2_0` + ISP3.0 CAMSV skeleton). |

### 6.2 `kernel/configs/pmos-mt6785.config` + `kernel/configs/yoga11.config`

`yoga11.config:1-103` sets **no** `CONFIG_MEDIA_*`, `CONFIG_VIDEO_*`, `CONFIG_V4L2_*`, or `CONFIG_VIDEOBUF2_*` options (it only adds `CONFIG_YT11_CAM_PROBE=m` at `:103` from concurrent M0 work). `pmos-mt6785.config` status:

* **Enabled:**
  * Core & Media Controller: `CONFIG_MEDIA_SUPPORT=m` (`:3809`), `CONFIG_MEDIA_SUPPORT_FILTER=y` (`:3810`), `CONFIG_MEDIA_CAMERA_SUPPORT=y` (`:3816`), `CONFIG_MEDIA_PLATFORM_SUPPORT=y` (`:3821`), `CONFIG_MEDIA_PLATFORM_DRIVERS=y` (`:3918`), `CONFIG_VIDEO_DEV=m` (`:3825`), `CONFIG_MEDIA_CONTROLLER=y` (`:3826`), `CONFIG_VIDEO_V4L2_I2C=y` (`:3832`), `CONFIG_VIDEO_V4L2_SUBDEV_API=y` (`:3833`), `CONFIG_V4L2_FWNODE=m` (`:3837`), `CONFIG_V4L2_ASYNC=m` (`:3838`), `CONFIG_MEDIA_ATTACH=y` (`:4047`).
  * Videobuf2: `CONFIG_VIDEOBUF2_CORE=m` (`:4036`), `CONFIG_VIDEOBUF2_V4L2=m` (`:4037`), `CONFIG_VIDEOBUF2_MEMOPS=m` (`:4038`), `CONFIG_VIDEOBUF2_VMALLOC=m` (`:4039`).
  * Flash LED: `CONFIG_LEDS_CLASS_FLASH=m` (`:5553`), `CONFIG_LEDS_MT6360=m` (`:5614`).
* **Disabled / Missing (must enable in `yoga11.config`):**
  * `CONFIG_VIDEO_OV8856` (`pmos-mt6785.config:4114`, `# is not set`) -> set `=m`
  * All VCM drivers (`:4141-4146`, `# is not set`) -> enable matched VCM `=m`
  * `CONFIG_VIDEOBUF2_DMA_CONTIG` (not in `pmos-mt6785.config`) -> needed (`=m`/`=y`) for CAMSV IMGO DMA
  * `CONFIG_V4L2_FLASH_LED_CLASS` (`:3836`, `# is not set`) -> enable `=m` if MT6360 flash V4L2 subdev is desired

---

## 7. Register-Level Reference Summary from Begonia (`src/begonia-ftp/camera/NOTES.md`)

| Subsystem / Base | Offset / Mapping | Fields, Values, and Behavior | `NOTES.md` Section |
|---|---|---|---|
| **APMIXEDSYS** (`0x1000C000`) | `+0x020` (`AP_PLL_CON8`-like) | Inverted gate (`1` = on): bit 6 = `apmixed_mipic0_26m`, bit 11 = `apmixed_mipic1_26m` (bits 16/17 = `mipid0/1`). Boot default `0x20`; write `\|= 0x840` (`0x860`). Required for MIPI RX ANA calibration. | `2026-11-13 ~21:00–22:00` ("What was wrong" #1) |
| **MIPI RX ANA** (`0x11C80000`) | Port *k* = `0, 1, 2` at stride `0x4000`: `CSIkA` `+0x0000`, `CSIkB` `+0x1000`, `DPHYk` `+0x2000`, `CPHYk` `+0x3000` (CSI2 = `0x8000`/`0x9000`/`0xa000`/`0xb000`) | Vendor DT `0x11c84000` naming is wrong. `ANA+0x00`: bit 0 `CPHY_EN`, bits 2/3 LPF/CORE power-on (`0`->`8`->`4`), CKMODE L0/L1/L2 = bits 5/8/11, CKSEL = bits 6/9/12 (`A.L2` clock). `ANA+0x04..+0x3c`: `phyA_init` (`+0x18/+0x1c/+0x20` per lane). `ANA+0x48`: cal/LPRX status (`& 0x29 == 0x29`). `ANA+0x80[15:8]` / `+0x84`: debug mux. | `2026-11-13 ~14:00`; `2026-11-13 ~21:00–22:00` ("MIPI RX map") |
| **MIPI RX DPHY / CPHY** | `DPHYk` (`+0x2000`), `CPHYk` (`+0x3000`) | `DPHY+0x00`: PHY enable/lanes. `DPHY+0x04`: lane mux + bit 31 `CK_DATA_MUX_EN`. `DPHY+0x20..+0x2c`: per-lane settle. `DPHY+0x30`/`+0x34`: clk/data lane FSM (`0x01` idle, `0x10` HS). `DPHY+0xe0[7:0]`/`+0x280`/`+0x288`: debug. `CPHY+0x18 \|= 0x10` (`setSeninfCsiMipi`). | `2026-11-13 ~21:00–22:00` ("What was wrong" #4, "MIPI RX map") |
| **CSI Port -> SENINF Table** | HAL `getCSIInfo` `{port, seninf}` | `(0, 0)`, `(1, 2)`, `(2, 4)`, `(3, 0)`, `(4, 1)`, `(5, 2)`, `(6, 3)`. CSI2 goes to **SENINF4** (`ctrl 0x4200`, `csi2 0x4a00`), not SENINF2. | `2026-11-13 ~21:00–22:00` ("What was wrong" #2) |
| **SENINF TOP & `TOP_MUX_CTRL`** (`0x1A040000`) | `TOP` `+0x000`: `+0x00` `TOP_CTRL`, `+0x08` (`0x32100000`, keep), `+0x10` `TOP_MUX_CTRL_0`, `+0x14` `TOP_MUX_CTRL_1`, `+0x68` `TOP_PHY_CTRL_CSI2` | `TOP_MUX_CTRL_0` (`+0x10`): nibble/byte per mux: `mux0[3:0]`, `mux1[11:8]`, `mux2[19:16]`, `mux3[27:24]`; `+0x14`: `mux4/5`. Default `0x03020100` / `0x504` (`mux i <- seninf i`). For CSI2->SENINF4->MUX2: `+0x10 = 0x03040100`. `+0x68`: clear bit 1, set bit 0 (D-PHY). | `2026-11-13 19:50`; `2026-11-13 ~21:00–22:00` ("What was wrong" #3) |
| **SENINF Sub-blocks** (`0x1A040000`) | `CTRL(i)` `+0x200+0x1000*i` (i=0..4); `TG(i)` `+0x600+0x1000*i`; `CSI2(i)` `+0xa00+0x1000*i` (i=0..5); `MUX(i)` `+0xd00+0x1000*i` (i=0..5); `CAM_MUX` `+0x400` | Layout = ISP7 `phy_2_0` except `TG` is at `+0x600` (not `+0xf00`). `CTRL`: `+0x00` `SENINF_CTRL`, `+0x10` `CSI2_CTRL`, `+0x20` `TESTMDL_CTRL`. `TG`: `+0x08` `TM_CTL` (`0x00300161`), `+0x0c` `TM_SIZE`, `+0x10` `TM_CLK`, `+0x18` `TM_DUM`. `CSI2`: `+0x00` `CSI2_EN` (lane mask `0x3`), `+0x04` `OPT`, `+0x08` `HDR_MODE_0`, `+0x10` `RESYNC_MERGE_CTRL` (`\|=0x100`), `+0xc0` `IRQ_EN` (`\|=0x80000000`), `+0xc8` `IRQ_STATUS`, `+0xd0..+0xdc` (`LINE_FRAME`, `PKT_STATUS`, `SHORT`, `PKT_CNT`), `+0xe0` `DBG_CTRL` (`0xffffffff`). `MUX`: `+0x00` `CTRL_0`, `+0x04` `CTRL_1` (`0x001f0001` TM / `0x8` MIPI), `+0x08` polarity, `+0x18` `IRQ`, `+0x20` `IMG_SIZE`, `+0x30` `SIZE`, `+0xa4` `PIX_CNT`, `+0xa8` `FRAME_SIZE_MON_CTRL`, `+0xb0`/`+0xb8` H/V valid. `CAM_MUX`: `+0x10` `EN` (`0x1f`), `+0x18` `CHK_EN`, `+0xa8` `IRQ`, `+0x108`/`+0x128` `CAM_MUX0/2_CHK_RES`; `CAMSV0 = cam_mux 2` (`convertTgEnum2CamMux = tg - 14`). | `2026-11-13 ~14:00`; `2026-11-13 19:50`; `2026-11-13 ~20:10`; `2026-11-13 ~21:00–22:00` |
| **CAMSV** (`0x1A050000 + 0x1000*i`, `camsv1..6`, IRQ SPI 279..282) | DMA `+0x20..0x48`; FBC `+0x110..0x114`; TG `+0x220..0x2a4`; TOP `+0x510..0x54c` | **DMA (ISP5 layout):** `+0x20` `BASE_ADDR`, `+0x28` `OFST_ADDR`, `+0x30` `XSIZE` (`BPL-1`), `+0x34` `YSIZE` (`L-1`), `+0x38` `STRIDE` (**omit bit 24** or DMA packs 2 lines into 1 -> half-frame!), `+0x3c` `CON`, `+0x40`/`+0x44` `CON2/CON3` (`0x20002`), `+0x48` ultra. **FBC:** `+0x110` `FBC_IMGO_CTL1` (`0x8000` `FBC_EN`, `\|=1` `RCNT_INC`; bits 16/22 break DMA), `+0x114` `CTL2` (`[31:24]` frame cnt). **TG:** `+0x230` `SEN_MODE` (`0x10001`: bit 0 `CMOS_EN`, bits 1/13 pixmode, bit 16 always 1, bits 17..18 subsample), `+0x234` `VF_CON` (`1`), `+0x238` `GRAB_PXL`, `+0x23c` `GRAB_LIN`, `+0x268` `TG_FRMSIZE`, `+0x26c` `TG_INTER_ST`, `+0x2a0` `TIME_STAMP`, `+0x2a4` subsample. **TOP:** `+0x400=1` (DMA/FBC en), `+0x510` `MODULE_EN` (bit 0 TG, 2 `PAK_EN`, 3 `PAK_SEL`, 4 IMGO, 30 DB -> `0x40000015`), `+0x514` `FMT_SEL` (`0x101` RAW10), `+0x518` `INT_EN`, `+0x51c` `INT_STATUS` (clear-on-read; bit 4 `TG_ERR`, 10 `PASS1_DON`, 16 `IMGO_ERR`, 19), `+0x520` `SW_CTL` (reset `4->0->1`, wait `==3`, `0`), `+0x530` `CLK_EN` (`0x8005`: TG/PAK/DMA), `+0x53c` `0x20150120`, `+0x54c` `PAK` (`2` RAW10). | `2026-11-13 ~14:15`; `2026-11-13 ~20:00`..`~21:10` |
| **SMI LARB bypass** | `larb6` (`0x1A001000`, 0..30), `larb7` (`0x1A002000`, 0..4) | `SMI_LARB_NONSEC_CON` (`+0x380 + 4*port`): clear bit 0 (`MMU_EN`) if running without IOMMU. | `2026-11-13 ~20:15–20:40` |

---

## 8. Ordered Checklist of Kernel Changes Before a Real V4L2 Driver Can Exist

1. **Patch `drivers/i2c/busses/i2c-mt65xx.c` for MT6785 multi-channel I2C (`mediatek,ch-offset`):**
   * Route shadow config registers (`SOFTRESET`, `IO_CONFIG`, `DCM_EN`, `TIMING`, `LTIMING`, `HS`) to channel 0 (`base`) and transaction registers to `base + ch_off` (`0x100`).
   * Use FIFO PIO for short (`<= 8` byte) transfers, set `MCU_INTR(0x40)=1` and `FIFO_ADDR_CLR |= 0x4`, and keep `ACKERR`/`HS_NACKERR` masked in the channel `INTR_MASK` so NACKs during probing do not hang the bus.
2. **Enable camera I2C, MCLK, pinctrl, and regulators in `arch/arm64/boot/dts/mediatek/mt6785-lenovo-yt-j706f.dts`:**
   * Add `regulator-fixed` nodes for GPIO195 (`vcama`), GPIO50 (`vcamd`), and GPIO197 (`vcamaf`), and wire `<&mt6359_vcamio_ldo_reg>` (`dovdd`).
   * Add `&pio` pinctrl groups for `i2c2` (GPIO112/113), `i2c4` (GPIO110/111), `CMMCLK1`/`CMMCLK2` (GPIO117/120 with `drive-strength = <4>` mA), and control GPIOs (119, 124, 195, 50, 197).
   * Enable `&i2c2` and `&i2c4` (`400 kHz`, `mediatek,ch-offset = <0x100>`) and assign `CLK_TOP_CAMTG1..5` parent to `CLK_TOP_UNIVPLL_192M_D8` (`24 MHz`).
3. **Update/add sensor and VCM drivers + `kernel/configs/yoga11.config`:**
   * Enable `CONFIG_VIDEO_OV8856=m` and `CONFIG_VIDEOBUF2_DMA_CONTIG=m` (plus the matched VCM Kconfig symbol once `0x0c` is identified, and `CONFIG_V4L2_FLASH_LED_CLASS=m` if MT6360 flash is wired).
   * Patch `drivers/media/i2c/ov8856.c` to support 24 MHz `xvclk` (24 MHz PLL / link-frequency entries alongside 19.2 MHz).
   * After hardware I2C probe identifies the second sensor on YT-J706F, add a V4L2 subdev driver if it lacks mainline support (e.g. `s5k4h7`).
4. **Complete SMI LARB7 & IOMMU support (`mt6785.dtsi`, `mediatek,mt6785-memory-port.h`, `mtk_iommu.c`):**
   * Confirm on hardware which LARB/port CAMSV0 DMA uses (`larb6` port 0 `M4U_PORT_CAM_IMGO` vs `larb7` ports 0..4).
   * Add `larb7: larb@1a002000` (`MT6785_POWER_DOMAIN_CAM`, `CLK_CAM_LARB7`) to `mt6785.dtsi` and `&larb7` to `&iommu`'s `mediatek,larbs` (and update `mtk_iommu.c:1597` `larbid_remap` + `mediatek,mt6785-memory-port.h` if CAMSV translates through `larb7`, or clear `MMU_EN` on unmapped ports in `mtk-smi.c` if `larb7` is physical-only).
5. **Add SENINF and CAMSV SoC DT nodes to `arch/arm64/boot/dts/mediatek/mt6785.dtsi`:**
   * `seninf@1a040000` (with `mipi_rx_ana` `0x11c80000` `0xc000`, `MT6785_POWER_DOMAIN_CAM`, `CLK_CAM_{MAIN,GALS,TG,SENINF}`, `CLK_TOP_SENINF0..2`, **`CLK_APMIXED_MIPIC0` & `CLK_APMIXED_MIPIC1`**, and media graph `ports` linking sensor endpoints to CAMSV).
   * `camsv0..N@1a050000` (`GIC_SPI 279..`, `MT6785_POWER_DOMAIN_CAM`, `CLK_CAM_SV0`/`SV1`, `iommus = <&iommu ...>`, `mediatek,larb`).
6. **Implement the V4L2 SENINF + CAMSV media platform driver (`drivers/media/platform/mediatek/`):**
   * Build the `v4l2_device` + `media_device` + `v4l2_async_notifier` + `seninf` subdev (ISP7 `phy_2_0` subset + begonia HAL diffs) + `camsv` `vb2_dma_contig` capture video node (ISP3.0 skeleton adapted to the MT6785 CAMSV register layout).
