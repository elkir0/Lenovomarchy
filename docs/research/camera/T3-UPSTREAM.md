# Task T3: Upstream Research — MediaTek Camera Receivers, libcamera SoftISP, and Sensors for MT6785 (YT-J706F)

## Corrections (2026-11-17)

Two register readings below were corrected by measurements on this
tablet (see `docs/hardware/CAMERA.md` "FBC and interrupts" and
`docs/research/camera/T8-V4L2.md` sections 0g-0i):

- The MT6785 FBC `FBC_IMGO_CTL1` low bit (`0x1`) is **not** "RCNT_INC"
  and the suggested porting recipe "write `0x8000` then `0x8001` per
  queued buffer" (section 2 register-mapping table, section on
  `mtk_camsv_fbc_*`) is wrong for this silicon: the low 6-bit field is a
  compare value against the written-frame count (`CTL2[6:0]`); with 1
  the DMA stops after one frame and drops the rest.  A free-running DMA
  needs the compare value kept ahead of the count, not a strobe.
- The frame data this pipeline captures is **not** MIPI RAW10: with the
  measured `FMT_SEL = 0x102 / PAK = 1` each line is a continuous
  little-endian 10-bit bit stream ("le10"), same size, different bit
  order.  Mentions of "RAW10" below should be read as "10-bit raw".

This document surveys the upstream Linux kernel and `libcamera` status for bringing up the cameras on the Lenovo Yoga Tab 11 (`YT-J706F`, MediaTek MT6785) on mainline Linux 7.1, cross-referenced against the MT6785 hardware findings on Xiaomi Redmi Note 8 Pro (`begonia`) in [NOTES.md](../../../src/begonia-ftp/camera/NOTES.md) and the tablet's stock DT inventory in [CAMERA.md](../../../docs/hardware/CAMERA.md) and [BOARD.md](../../../docs/hardware/BOARD.md).

---

## 1. MediaTek Camera Receivers Upstream as of Today

In mainline Linux 7.1 ([drivers/media/platform/mediatek/](../../../src/mt6785-mainline/drivers/media/platform/mediatek/Makefile) / [git.kernel.org `drivers/media/platform/mediatek`](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/tree/drivers/media/platform/mediatek)), only `jpeg`, `mdp`, `mdp3`, `vcodec`, and `vpu` are merged. **No MediaTek CSI-2 sensor interface (`seninf`), raw DMA receiver (`camsv`), or ISP (`camsys` / Pass 1 / `cam-raw`) driver is merged in mainline or `linux-next` as of today.** However, the MIPI CSI-2 v0.5 D-PHY/CD-PHY driver for MT8365 *is* merged in mainline under `drivers/phy/mediatek/`, and two major V4L2/Media-Controller series on the mailing lists (`ISP 3.0` for MT8365 and `ISP 7.x` for MT8188) provide all the building blocks needed for MT6785.

| Series / SoC Family | Latest Upstream Posting | Merge Status | Mainline PHY / Clocks Merged? | Maintained Out-of-Tree Branch |
|---|---|---|---|---|
| **(a) MT8365 "ISP 3.0"** (`seninf` + `camsv`) | `[PATCH v8 0/5] Add Mediatek ISP3.0` (Julien Stephan, BayLibre, 2025-01-22) ([lore v8 cover](https://lore.kernel.org/all/20250122-add-mtk-isp-3-0-support-v8-0-a3d3731eef45@baylibre.com/)) | **On list only** (not in mainline 7.1; DT bindings and `mt8365.dtsi` carry `Reviewed-by:` tags) | **Yes**: `phy-mtk-mipi-csi-0-5.c` ([git.kernel.org](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/tree/drivers/phy/mediatek/phy-mtk-mipi-csi-0-5.c)) and `clk-mt8365-cam.c` ([git.kernel.org](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/tree/drivers/clk/mediatek/clk-mt8365-cam.c)) | [MediaTek AIoT BSP Linux (`gitlab.com/mediatek/aiot/rity/bsp-linux`)](https://gitlab.com/mediatek/aiot/rity/bsp-linux) (`mtk-v5.15-dev` / `mtk-v6.6-dev`) and [BayLibre RITA Linux (`gitlab.baylibre.com/baylibre/mediatek/rita/linux`)](https://gitlab.baylibre.com/baylibre/mediatek/rita/linux) |
| **(b) MT8188 "ISP 7.x"** (`mtk-cam` + `seninf` `phy_2_0`) | `[PATCH v1 00/10] Add MediaTek ISP7 camera system driver` (Shu-hsiang Yang, MediaTek, 2024-10-09) ([lore v1 cover](https://lore.kernel.org/all/20241009111551.27052-1-Shu-hsiang.Yang@mediatek.com/)) | **On list only** (v1 received structural review feedback from AngeloGioacchino Del Regno and CK Hu) | **Clocks only**: `clk-mt8188-cam.c` ([git.kernel.org](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/tree/drivers/clk/mediatek/clk-mt8188-cam.c)); PHY is embedded inside `mtk_csi_phy_2_0` | [MediaTek AIoT BSP Linux (`gitlab.com/mediatek/aiot/rity/bsp-linux`)](https://gitlab.com/mediatek/aiot/rity/bsp-linux) and [ChromiumOS `chromeos-5.15` (`chromium.googlesource.com`)](https://chromium.googlesource.com/chromiumos/third_party/kernel/+/refs/heads/chromeos-5.15/drivers/media/platform/mtk-isp/) |
| **(c) MT8183 / MT8192 / MT8195** (`camsys` / `seninf` / P1 / DIP) | MT8183 P1 RFC v4 (Jungo Lin, 2019-08-07) ([lore RFC v4](https://lore.kernel.org/all/20190807124803.29884-1-jungo.lin@mediatek.com/)); MT8183 DIP RFC v0 (Frederic Chen, 2019-02) ([LWN](https://lwn.net/Articles/780388/)) | **On list only** (abandoned upstream; only `mdp3` was eventually merged from that effort) | **Clocks & IOMMU only**: `clk-mt8183-cam.c`, `clk-mt8192-cam.c`, `clk-mt8195-cam.c` | [ChromiumOS `chromeos-5.10` / `chromeos-5.15` `drivers/media/platform/mtk-isp/`](https://chromium.googlesource.com/chromiumos/third_party/kernel/+/refs/heads/chromeos-5.10/drivers/media/platform/mtk-isp/) |

### 1(a). MT8365 "ISP 3.0" SENINF + CAMSV Series (BayLibre / MediaTek)

- **History and Latest Version:** Originally posted as an RFC by Louis Kuo (MediaTek) in July 2020 ([`20200708104023.3225-1-louis.kuo@mediatek.com`](https://lore.kernel.org/all/20200708104023.3225-1-louis.kuo@mediatek.com/)), then taken over by Phi-bang Nguyen, Florian Sylvestre, and Julien Stephan at BayLibre (with review contributions from Paul Elder and Laurent Pinchart). The latest upstream revision verified on the mailing list is **v8** posted on **January 22, 2025** (rebased on `v6.13-rc1`, change-id `20240704-add-mtk-isp-3-0-support-a08a978cac36`; local copy archived in [ref/isp30/](../../../src/begonia-ftp/camera/ref/isp30/idx.html)):
  - Cover letter `[PATCH v8 0/5] Add Mediatek ISP3.0`: [`lore.kernel.org`](https://lore.kernel.org/all/20250122-add-mtk-isp-3-0-support-v8-0-a3d3731eef45@baylibre.com/) ([LKML mirror](https://lkml.iu.edu/hypermail/linux/kernel/2501.2/06543.html); v7 is at [`lore.kernel.org`](https://lore.kernel.org/all/20241121-add-mtk-isp-3-0-support-v7-0-b04dc9610619@baylibre.com/), v6 at [`lore.kernel.org`](https://lore.kernel.org/all/20240729-add-mtk-isp-3-0-support-v6-0-c374c9e0c672@baylibre.com/)).
  - Patch 1/5 (`dt-bindings: media: add mediatek ISP3.0 sensor interface`): [`lore.kernel.org`](https://lore.kernel.org/all/20250122-add-mtk-isp-3-0-support-v8-1-a3d3731eef45@baylibre.com/) — adds `Documentation/devicetree/bindings/media/mediatek,mt8365-seninf.yaml`.
  - Patch 2/5 (`dt-bindings: media: add mediatek ISP3.0 camsv`): [`lore.kernel.org`](https://lore.kernel.org/all/20250122-add-mtk-isp-3-0-support-v8-2-a3d3731eef45@baylibre.com/) — adds `Documentation/devicetree/bindings/media/mediatek,mt8365-camsv.yaml`.
  - Patch 3/5 (`media: platform: mediatek: isp: add mediatek ISP3.0 sensor interface`): [`lore.kernel.org`](https://lore.kernel.org/all/20250122-add-mtk-isp-3-0-support-v8-3-a3d3731eef45@baylibre.com/) ([local copy](../../../src/begonia-ftp/camera/ref/isp30/06547.html)).
  - Patch 4/5 (`media: platform: mediatek: isp: add mediatek ISP3.0 camsv`): [`lore.kernel.org`](https://lore.kernel.org/all/20250122-add-mtk-isp-3-0-support-v8-4-a3d3731eef45@baylibre.com/) ([local copy](../../../src/begonia-ftp/camera/ref/isp30/06546.html)).
  - Patch 5/5 (`arm64: dts: mediatek: mt8365: Add support for camera`): [`lore.kernel.org`](https://lore.kernel.org/all/20250122-add-mtk-isp-3-0-support-v8-5-a3d3731eef45@baylibre.com/) ([local copy](../../../src/begonia-ftp/camera/ref/isp30/06545.html)).
- **Files and Size:** Placed in `drivers/media/platform/mediatek/isp/` (totaling 3,834 lines across 15 files, of which the C/H driver files are 3,276 lines; extracted in [ref/isp30/src/](../../../src/begonia-ftp/camera/ref/isp30/src/)):
  - [mtk_seninf.c](../../../src/begonia-ftp/camera/ref/isp30/src/mtk_seninf.c) (1,454 lines) and [mtk_seninf_reg.h](../../../src/begonia-ftp/camera/ref/isp30/src/mtk_seninf_reg.h) (114 lines).
  - [mtk_camsv.h](../../../src/begonia-ftp/camera/ref/isp30/src/mtk_camsv.h) (152 lines), [mtk_camsv_hw.c](../../../src/begonia-ftp/camera/ref/isp30/src/mtk_camsv_hw.c) (440 lines), [mtk_camsv_hw.h](../../../src/begonia-ftp/camera/ref/isp30/src/mtk_camsv_hw.h) (19 lines), [mtk_camsv_reg.h](../../../src/begonia-ftp/camera/ref/isp30/src/mtk_camsv_reg.h) (90 lines), [mtk_camsv_video.c](../../../src/begonia-ftp/camera/ref/isp30/src/mtk_camsv_video.c) (1,017 lines).
- **Register Layout (ISP 3.0):**
  - **CSI-2 Analog PHY (`phy-mtk-mipi-csi-0-5.c`):** Separate generic PHY driver in [drivers/phy/mediatek/phy-mtk-mipi-csi-0-5.c](../../../src/mt6785-mainline/drivers/phy/mediatek/phy-mtk-mipi-csi-0-5.c) (merged in Linux v6.7, [`git.kernel.org`](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/tree/drivers/phy/mediatek/phy-mtk-mipi-csi-0-5.c)), mapped at `0x11c10000` (`csi0`, window `0x2000`, `CSIXB_OFFSET = 0x1000`) and `0x11c12000` (`csi1`). Only configures analog registers (`MIPI_RX_ANA00..ANAA8`); digital D-PHY timing sits inside SENINF.
  - **SENINF (`0x15040000`, window `0x6000`, stride `0x1000` per SENINF port):**
    - `SENINF_TOP_CTRL` at `+0x0000`, `SENINF_TOP_MUX_CTRL` at `+0x0008`, `SENINF_TOP_CAM_MUX_CTRL` at `+0x0010`, `SENINF_TOP_PHY_SENINF_CTL_CSI0/1` at `+0x001c/+0x0020`. Note: there is **no** separate `SENINF_CAM_MUX` block at `+0x0400`; cam-mux selection is a single register at `TOP + 0x0010`.
    - Per-instance blocks (`+0x1000 * i`): `SENINF_CTRL` at `+0x0200`, `SENINF_TG1` at `+0x0600` (`PH_CNT 0x600`, `SEN_CK 0x604`, `TM_CTL 0x608`, `TM_SIZE 0x60c`, `TM_CLK 0x610`), `MIPI_RX_CON24_CSI0` at `+0x0824`, `SENINF_CSI2` at `+0x0a00` (older ISP 3.0 CSI2 register map: `CSI2_CTL 0xa00`, `LNRD_TIMING 0xa08`, `DPCM 0xa0c`, `HS_TRAIL 0xa40`, `RESYNC_MERGE_CTL 0xa74`, `MODE 0xae8`, `DPHY_SYNC 0xb20`), `SENINF_MUX` at `+0x0d00` (single-word `MUX_CTRL 0xd00` with `MUX_EN` in `BIT(31)`, `INTEN 0xd04`, `CTRL_EXT 0xd3c`).
  - **CAMSV (`0x15050000` for `camsv1`, `0x15050800` for `camsv2`):** Uses **three separate `reg` tuples** in DT ([mt8365.dtsi](../../../src/begonia-ftp/camera/ref/isp30/src/mt8365.dtsi#L72-L97)):
    1. `regs` (TOP, `0x15050000`, size `0x40`): `MODULE_EN +0x00`, `FMT_SEL +0x04`, `INT_EN +0x08`, `INT_STATUS +0x0c`, `SW_CTL +0x10`, `IMGO_FBC +0x1c`, `CLK_EN +0x20`, `PAK +0x3c`.
    2. `regs_img0` (IMGO DMA, `0x15050208`, size `0x20`): `BASE_ADDR +0x00`, `XSIZE +0x08`, `YSIZE +0x0c`, `STRIDE +0x10`, `CON +0x14`, `CON2 +0x18`.
    3. `regs_tg` (TG, `0x15050400`, size `0x100`): `SEN_MODE +0x10`, `VF_CON +0x14`, `SEN_GRAB_PXL +0x18`, `SEN_GRAB_LIN +0x1c`, `PATH_CFG +0x20`.

### 1(b). MediaTek "ISP 7.x" `mtk-cam` / `seninf` Series (`mtk_csi_phy_2_0`)

- **History and Latest Version:** Posted by Shu-hsiang Yang (`Shu-hsiang.Yang@mediatek.com`) on **October 9, 2024** as `[PATCH v1 00/10] Add MediaTek ISP7 camera system driver` targeting MT8188 (ISP 7.1):
  - Cover letter (`[PATCH v1 00/10]`): [`lore.kernel.org`](https://lore.kernel.org/all/20241009111551.27052-1-Shu-hsiang.Yang@mediatek.com/) ([Patchew](https://patchew.org/linux/20241009111551.27052-1-Shu-hsiang.Yang@mediatek.com/)).
  - Patch 02/10 (`[PATCH v1 02/10] media: platform: mediatek: add seninf controller`): [`lore.kernel.org`](https://lore.kernel.org/all/20241009111551.27052-3-Shu-hsiang.Yang@mediatek.com/) ([IU LKML mirror](https://lkml.iu.edu/hypermail/linux/kernel/2410.1/02440.html); local copy in [ref/isp7-v1/p02.html](../../../src/begonia-ftp/camera/ref/isp7-v1/p02.html)).
  - Patch 04/10 (`[PATCH v1 04/10] media: platform: mediatek: add isp_7x cam-raw unit`): [`lore.kernel.org`](https://lore.kernel.org/all/20241009111551.27052-5-Shu-hsiang.Yang@mediatek.com/) ([IU LKML mirror](https://lkml.iu.edu/hypermail/linux/kernel/2410.1/02439.html)).
  - No v2 of this 10-patch series could be verified on `lore.kernel.org` after the October 2024 review comments from AngeloGioacchino Del Regno ([`lore.kernel.org`](https://lore.kernel.org/all/d5c0b95f-51d2-4d38-9214-2750a8b35a0b@collabora.com/)) and CK Hu requesting that register bitfield macros (`SENINF_BITS` / `SENINF_READ_BITS`) be replaced with standard `<linux/bitfield.h>` `FIELD_PREP`/`FIELD_GET` and that the monolithic driver be split cleanly.
- **Files and Size:** Placed in `drivers/media/platform/mediatek/isp/isp_7x/camsys/` (patch 02/10 alone is 5,017 lines across 11 files in `mtk_csi_phy_2_0/`, extracted in [ref/isp7-v1/src/](../../../src/begonia-ftp/camera/ref/isp7-v1/src/), plus core `mtk_cam-seninf-drv.c`, `mtk_cam-seninf-route.c`, and `cam-raw` / `camsv` units in the remaining patches):
  - [mtk_cam-seninf-hw_phy_2_0.c](../../../src/begonia-ftp/camera/ref/isp7-v1/src/mtk_cam-seninf-hw_phy_2_0.c) (2,879 lines).
  - 10 bitfield register headers: [mtk_cam-seninf-top-ctrl.h](../../../src/begonia-ftp/camera/ref/isp7-v1/src/mtk_cam-seninf-top-ctrl.h) (99 lines), [mtk_cam-seninf-cammux.h](../../../src/begonia-ftp/camera/ref/isp7-v1/src/mtk_cam-seninf-cammux.h) (911 lines), [mtk_cam-seninf-seninf1.h](../../../src/begonia-ftp/camera/ref/isp7-v1/src/mtk_cam-seninf-seninf1.h) (47 lines), [mtk_cam-seninf-seninf1-csi2.h](../../../src/begonia-ftp/camera/ref/isp7-v1/src/mtk_cam-seninf-seninf1-csi2.h) (415 lines), [mtk_cam-seninf-seninf1-mux.h](../../../src/begonia-ftp/camera/ref/isp7-v1/src/mtk_cam-seninf-seninf1-mux.h) (147 lines), [mtk_cam-seninf-tg1.h](../../../src/begonia-ftp/camera/ref/isp7-v1/src/mtk_cam-seninf-tg1.h) (49 lines), [mtk_cam-seninf-mipi-rx-ana-cdphy-csi0a.h](../../../src/begonia-ftp/camera/ref/isp7-v1/src/mtk_cam-seninf-mipi-rx-ana-cdphy-csi0a.h) (257 lines), [mtk_cam-seninf-csi0-dphy.h](../../../src/begonia-ftp/camera/ref/isp7-v1/src/mtk_cam-seninf-csi0-dphy.h) (139 lines), [mtk_cam-seninf-csi0-cphy.h](../../../src/begonia-ftp/camera/ref/isp7-v1/src/mtk_cam-seninf-csi0-cphy.h) (69 lines).
- **Register Layout (`mtk_csi_phy_2_0`):**
  - **MIPI RX (`ana_base`, stride `0x4000` per CSI port `0..3`):** `CSI_PORT_kA = +0x0000`, `CSI_PORT_kB = +0x1000`, `DPHY_TOP_k = +0x2000`, `CPHY_TOP_k = +0x3000` ([mtk_cam-seninf-hw_phy_2_0.c](../../../src/begonia-ftp/camera/ref/isp7-v1/src/mtk_cam-seninf-hw_phy_2_0.c#L85-L137)).
  - **SENINF (`if_base`, stride `0x1000` per instance):**
    - `reg_if_top = if_base + 0x0000` (`SENINF_TOP_CTRL 0x00`, `SENINF_TOP_MUX_CTRL_0 0x10`, `SENINF_TOP_MUX_CTRL_1 0x14`, `SENINF_TOP_PHY_CTRL_CSI0..3 0x60..0x6c`).
    - `reg_if_cam_mux = if_base + 0x0400` (`SENINF_CAM_MUX_CTRL_0..2 0x00..0x08`, `SENINF_CAM_MUX_EN 0x10`, `SENINF_CAM_MUX_CHK_EN 0x18`, `SENINF_CAM_MUX_IRQ_EN 0xa0`, `SENINF_CAM_MUX_IRQ_STATUS 0xa8`, `SENINF_CAM_MUX0_CHK_RES 0x108` + `0x10 * k`).
    - Per-instance (`+0x1000 * i`): `reg_if_ctrl[i] = +0x0200` (`SENINF_CTRL 0x00`, `SENINF_CSI2_CTRL 0x10`, `SENINF_TESTMDL_CTRL 0x20`), `reg_if_csi2[i] = +0x0a00` (`CSI2_EN 0x00`, `CSI2_OPT 0x04`, `CSI2_HDR_MODE_0 0x08`, `CSI2_RESYNC_MERGE_CTRL 0x10`, `S0_DI_CTRL 0x20`, `CH0_CTRL 0x40`, `IRQ_EN 0xc0`, `IRQ_STATUS 0xc8`, `LINE_FRAME_NUM 0xd0`, `PACKET_STATUS 0xd4`, `GENERIC_SHORT_PACKET_STATUS 0xd8`, `PACKET_CNT_STATUS 0xdc`, `DBG_CTRL 0xe0`), `reg_if_mux[i] = +0x0d00` (`MUX_CTRL_0 0x00`, `MUX_CTRL_1 0x04`, `MUX_OPT 0x08`, `MUX_IRQ_EN 0x10`, `MUX_IRQ_STATUS 0x18`, `MUX_IMG_SIZE 0x20`, `MUX_SIZE 0x30`, `MUX_PIX_CNT 0xa4`, `FRAME_SIZE_MON_CTRL 0xa8`), `reg_if_tg[i] = +0x0f00` (`TM_CTL 0x08`, `TM_SIZE 0x0c`, `TM_CLK 0x10`, `TM_DUM 0x18`).

### 1(c). MT8183 / MT8192 / MT8195 `camsys` or `seninf`

- **Clock and SMI/IOMMU Drivers (Merged in Mainline):**
  - MT8183 (ISP 5.0, same ISP generation as MT6785's ISP 6s/5.0 hybrid): [`drivers/clk/mediatek/clk-mt8183-cam.c`](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/tree/drivers/clk/mediatek/clk-mt8183-cam.c) is merged and has the **exact same 10 gate bit positions** (`LARB6` bit 0, `DFVAD` bit 1, `LARB3/7` bit 2, `GALS` bit 4, `CAM` bit 6, `CAMTG` bit 7, `SENINF` bit 8, `CAMSV0` bit 9, `CAMSV1` bit 10, `CCU` bit 12, `FAKE_ENG` bit 13) as [clk-mt6785-cam.c](../../../src/mt6785-mainline/drivers/clk/mediatek/clk-mt6785-cam.c#L22-L33).
  - MT8192 (ISP 6s / 7.0 transition): [`drivers/clk/mediatek/clk-mt8192-cam.c`](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/tree/drivers/clk/mediatek/clk-mt8192-cam.c) (`camsys`, `cam_rawa`, `cam_rawb`, `cam_rawc`) is merged.
  - MT8195 (ISP 7.0): [`drivers/clk/mediatek/clk-mt8195-cam.c`](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/tree/drivers/clk/mediatek/clk-mt8195-cam.c) is merged.
- **Camera / ISP Receiver Drivers (On-List RFCs & Out-of-Tree Only):**
  - For **MT8183**, MediaTek posted two RFC series in 2019: Jungo Lin's `[RFC,v4,0/4] media: platform: mtk-isp: Add Mediatek ISP Pass 1 driver` ([`lore.kernel.org`](https://lore.kernel.org/all/20190807124803.29884-1-jungo.lin@mediatek.com/), [LWN](https://lwn.net/Articles/795694/)) and Frederic Chen's `[RFC PATCH V0 0/7] media: platform: Add support for Digital Image Processing (DIP)` ([LWN](https://lwn.net/Articles/780388/)). Those RFCs required a companion SCP co-processor firmware binary to program ISP registers (`mtk_cam-scp`) and did **not** include a standalone `seninf` or `camsv` driver; they were never merged into mainline.
  - Maintained out-of-tree branches for MT8183 (`isp_50` + `seninf`) and MT8195/MT8188 (`isp_70`/`isp_71`) live in the ChromiumOS kernel repository under [`drivers/media/platform/mtk-isp/` (`chromeos-5.10`)](https://chromium.googlesource.com/chromiumos/third_party/kernel/+/refs/heads/chromeos-5.10/drivers/media/platform/mtk-isp/) and [`chromeos-5.15`](https://chromium.googlesource.com/chromiumos/third_party/kernel/+/refs/heads/chromeos-5.15/drivers/media/platform/mtk-isp/), as well as the MediaTek Genio BSP tree ([`gitlab.com/mediatek/aiot/rity/bsp-linux`](https://gitlab.com/mediatek/aiot/rity/bsp-linux)).
  - No upstream `seninf` or `camsv` patch series specifically targeting MT8192 could be verified on `lore.kernel.org`.

---

## 2. Comparing Upstream Drivers with Begonia's `NOTES.md` & Best Base for MT6785

Cross-checking the hardware reverse-engineering in [NOTES.md](../../../src/begonia-ftp/camera/NOTES.md#L178-L326) (and working test code in [seninf-tm.c](../../../src/begonia-ftp/camera/seninf/seninf-tm.c), [camsv-tm.c](../../../src/begonia-ftp/camera/camsv/camsv-tm.c), and [ov-cap.py](../../../src/begonia-ftp/camera/ov8856-mipi/ov-cap.py)) against the two upstream series reveals that **MT6785 is an architectural bridge**: its **SENINF + MIPI RX PHY** is already the newer **ISP7 `mtk_csi_phy_2_0`** IP block, while its **CAMSV** is the **ISP 5.0 / ISP 3.0** IP block with a single unified `0x1000` register window per instance and a dedicated 2-register FBC block.

### 2.1 Detailed Register & Functional Comparison

#### A. SENINF & MIPI CSI-2 PHY (`0x1a040000` & `0x11c80000`)

| Feature / Block | MT8365 ISP 3.0 ([mtk_seninf_reg.h](../../../src/begonia-ftp/camera/ref/isp30/src/mtk_seninf_reg.h)) | MT8188 ISP 7.x `phy_2_0` ([hw_phy_2_0.c](../../../src/begonia-ftp/camera/ref/isp7-v1/src/mtk_cam-seninf-hw_phy_2_0.c)) | MT6785 Hardware ([NOTES.md](../../../src/begonia-ftp/camera/NOTES.md#L178-L188), [ov-cap.py](../../../src/begonia-ftp/camera/ov8856-mipi/ov-cap.py)) |
|---|---|---|---|
| **MIPI RX Base & Stride** | `0x11c10000`, `0x2000`/port (`phy-mtk-mipi-csi-0-5.c`); no DPHY/CPHY top in ANA | `ana_base`, `0x4000`/port: `ANA_A +0x0`, `ANA_B +0x1000`, `DPHY +0x2000`, `CPHY +0x3000` | **Matches ISP7 `phy_2_0` 100%**: `0x11c80000`, `0x4000`/port (`CSI0..2`: `ANA_A +0x0`, `ANA_B +0x1000`, `DPHY +0x2000`, `CPHY +0x3000`) |
| **PHY Init & Power-on** | Only EQ tune + clock lane select + byteck invert; no `ANA +0x48` calibration check | `csirx_phyA_init`, `dphy_init`, `phyA_setting`, `dphy_setting`, `phyA_power_on` (polls `ANA +0x48 & 0x29`) | **Matches ISP7 `phy_2_0`**, plus two HAL writes found in `NOTES.md`: `CPHY_TOP + 0x18 \|= 0x10` (`setSeninfCsiMipi`) and `DPHY + 0x04 \|= BIT(31)` (`CK_DATA_MUX_EN`) |
| **APMIXED 26 MHz Ref Clocks** | Not used in `phy-mtk-mipi-csi-0-5.c` | Handled by SoC clock tree | **Mandatory on MT6785**: `APMIXEDSYS + 0x20` bit 6 (`CLK_APMIXED_MIPIC0`) and bit 11 (`CLK_APMIXED_MIPIC1`). Already defined in [clk-mt6785-apmixed.c](../../../src/mt6785-mainline/drivers/clk/mediatek/clk-mt6785-apmixed.c#L30-L34)! |
| **SENINF TOP (`+0x0000`)** | `TOP_MUX_CTRL +0x08`, `TOP_CAM_MUX_CTRL +0x10`, `PHY_SENINF_CTL_CSI0 +0x1c` | `TOP_CTRL +0x00`, `TOP_MUX_CTRL_0/1 +0x10/+0x14`, `TOP_PHY_CTRL_CSI0..3 +0x60..+0x6c` | **Matches ISP7 `phy_2_0`** (`TOP_MUX_CTRL_0/1` at `+0x10/+0x14`, `TOP_PHY_CTRL_CSI2` at `+0x68`) |
| **SENINF_CTRL (`+0x0200`)** | `SENINF_CTRL +0x200`, `SENINF_CTRL_EXT +0x204` (`CSI2_IP_EN BIT(6)`) | `SENINF_CTRL +0x00` (`EN BIT(0)`), `SENINF_CSI2_CTRL +0x10`, `TESTMDL_CTRL +0x20` | **Matches ISP7 `phy_2_0`** (`+0x00 = 1`, `+0x10 = 1`, `+0x20 = 1`) |
| **SENINF_CAM_MUX (`+0x0400`)** | **Absent** (uses `TOP + 0x10` only) | Present at `+0x0400` (`CTRL_0..2 +0x0..+0x8`, `EN +0x10`, `CHK_EN +0x18`, `CHK_RES +0x108`) | **Matches ISP7 `phy_2_0`** (`CAMSV0` = `cam_mux 2`, `CHK_RES` at `0x400 + 0x128`) |
| **SENINF_TG (`+0x0600` vs `+0x0f00`)** | At `+0x0600` (`PH_CNT 0x600`, `TM_CTL 0x608`, `TM_SIZE 0x60c`, `TM_CLK 0x610`) | At `+0x0f00` (`PH_CNT +0x0`, `TM_CTL +0x8`, `TM_SIZE +0xc`, `TM_CLK +0x10`, `TM_DUM +0x18`) | **At `+0x0600 + 0x1000*i`** (offset matches ISP 3.0, register fields match ISP7 `mtk_cam-seninf-tg1.h`) |
| **SENINF_CSI2 (`+0x0a00`)** | Completely different (`CTL +0x0`, `LNRD_TIMING +0x8`, `RESYNC_MERGE_CTL +0x74`, `MODE +0xe8`) | `CSI2_EN +0x00`, `OPT +0x04`, `HDR_MODE_0 +0x08`, `RESYNC_MERGE_CTRL +0x10`, `IRQ_EN +0xc0`, `IRQ_STATUS +0xc8`, `PACKET_CNT +0xdc`, `DBG_CTRL +0xe0` | **Matches ISP7 `phy_2_0` bit-for-bit** |
| **SENINF_MUX (`+0x0d00`)** | Single `MUX_CTRL +0x00` (`MUX_EN BIT(31)`), `CTRL_EXT +0x3c` | `MUX_CTRL_0 +0x00` (`EN BIT(0)`), `MUX_CTRL_1 +0x04` (`SRC_SEL`, `PIX_MODE`), `MUX_OPT +0x08`, `MUX_SIZE +0x30`, `MON_CTRL +0xa8` | **Matches ISP7 `phy_2_0` bit-for-bit** |
| **CSI Port -> SENINF Mapping** | `CSI0 -> SENINF1`, `CSI1 -> SENINF2` | `0/0A->0`, `0B->1`, `1/1A->2`, `1B->3`, `2/2A->4`, `2B->5` ([hw_phy_2_0.c](../../../src/begonia-ftp/camera/ref/isp7-v1/src/mtk_cam-seninf-hw_phy_2_0.c#L169-L209)) | **Matches ISP7 `phy_2_0`**: `CSI0->SENINF0`, `CSI1->SENINF2`, `CSI2->SENINF4` (`0x4a00`), `CSI0B->SENINF1`, `CSI1B->SENINF3` ([NOTES.md](../../../src/begonia-ftp/camera/NOTES.md#L301-L302)) |

#### B. CAMSV (`0x1a050000 + 0x1000 * i`, `i = 0..5`)

| Sub-block / Register | MT8365 ISP 3.0 ([mtk_camsv_reg.h](../../../src/begonia-ftp/camera/ref/isp30/src/mtk_camsv_reg.h)) | MT6785 Hardware ([NOTES.md](../../../src/begonia-ftp/camera/NOTES.md#L189-L288), [ov-cap.py](../../../src/begonia-ftp/camera/ov8856-mipi/ov-cap.py#L190-L209)) | What Must Change |
|---|---|---|---|
| **DT `reg` mapping** | 3 separate `reg` tuples (`top @ +0x000`, `img0 @ +0x208`, `tg @ +0x400`) | Single `0x1000` window per instance (`0x1a050000 + 0x1000 * i`, GIC SPI 279..284) | Map 1 `IORESOURCE_MEM` (`0x1000`) and derive sub-block offsets, or set `regs = base + 0x510`, `regs_img0 = base + 0x20`, `regs_tg = base + 0x220` |
| **TOP block** | Base `+0x000`: `MODULE_EN +0x00`, `FMT_SEL +0x04`, `INT_EN +0x08`, `INT_STATUS +0x0c`, `SW_CTL +0x10`, `CLK_EN +0x20`, `PAK +0x3c` | Shifted to **`+0x510`**: `MODULE_EN 0x510`, `FMT_SEL 0x514`, `INT_EN 0x518`, `INT_STATUS 0x51c`, `SW_CTL 0x520`, `CLK_EN 0x530`, `PAK 0x54c` (plus `0x400 |= 1` DMA enable) | Add `+0x510` offset to TOP registers; add `writel(1, base + 0x400)` in `mtk_camsv_setup()` |
| **TG block** | Base `+0x400`: `SEN_MODE +0x10`, `VF_CON +0x14`, `GRAB_PXL +0x18`, `GRAB_LIN +0x1c`, `PATH_CFG +0x20` | Shifted to **`+0x220`**: `SEN_MODE 0x230` (`0x10001`: bit 16 + `CMOS_EN`), `VF_CON 0x234`, `GRAB_PXL 0x238`, `GRAB_LIN 0x23c`, `FRMSIZE_ST 0x268`, `INTER_ST 0x26c` | Shift TG base to `+0x220`; set `SEN_MODE = BIT(16) \| CMOS_EN` (`0x10001`, 1-pixel mode without `DBL_DATA_BUS_EN` when `MUX` is in 1-pixel mode) and `PAK = 2` (RAW10, no `PAK_DBL_MODE_2_PIXELS`) |
| **IMGO DMA block** | Base `+0x208`: `BASE_ADDR +0x00`, `XSIZE +0x08`, `YSIZE +0x0c`, `STRIDE +0x10` (with `BUS_SIZE_EN \| BUS_SIZE_32`), `CON +0x14`, `CON2 +0x18` | Shifted to **`+0x020`** (ISP5 layout): `BASE_ADDR 0x20`, `OFST_ADDR 0x28`, `XSIZE 0x30` (`BPL - 1`), `YSIZE 0x34` (`H - 1`), `STRIDE 0x38` (**plain `BPL`, NO bit 24**), `CON 0x3c` (`0x80000080`), `CON2 0x40` (`0x20002`), `CON3 0x44` (`0x20002`) | Shift IMGO offsets (`0x20`, `0x30`, `0x34`, `0x38`, `0x3c`, `0x40`, `0x44`); **critical**: do NOT set bit 24 on `STRIDE` (setting bit 24 packs 2 lines into 1 and writes only half the frame, [NOTES.md](../../../src/begonia-ftp/camera/NOTES.md#L281-L285)) |
| **FBC (Frame Buffer Control)** | Single register `CAMSV_IMGO_FBC` at `top + 0x1c` (`RCNT_INC BIT(11)`, `FBC_EN BIT(14)`, `FB_NUM GENMASK(19,16)`) | Dedicated block at **`0x110` / `0x114`**: `FBC_IMGO_CTL1 0x110` (`FBC_EN = BIT(15) = 0x8000`, `RCNT_INC = BIT(0) = 0x1`), `FBC_IMGO_CTL2 0x114` (`FBC_CNT` in `[31:24]`) | Replace `mtk_camsv_fbc_init()` / `mtk_camsv_fbc_inc()` to write `0x8000` to `0x110` for enable and `0x8001` (`BIT(15) \| BIT(0)`) per queued buffer |

### 2.2 Which Upstream Driver Is the Best Base for MT6785?

**Recommendation: Use the MT8365 ISP 3.0 series ([ref/isp30/src/](../../../src/begonia-ftp/camera/ref/isp30/src/)) as the V4L2 / Media-Controller / `vb2` skeleton for both `mtk_seninf` and `mtk_camsv`, and transplant the hardware register programming functions from ISP7 `mtk_csi_phy_2_0` ([mtk_cam-seninf-hw_phy_2_0.c](../../../src/begonia-ftp/camera/ref/isp7-v1/src/mtk_cam-seninf-hw_phy_2_0.c) / [ov-cap.py](../../../src/begonia-ftp/camera/ov8856-mipi/ov-cap.py)) into `mtk_seninf.c`.**

Why this hybrid beats starting from ISP7's full `camsys` driver:
1. **ISP 3.0 has the exact V4L2 media graph topology we want:** `sensor -> mtk-seninf (subdev) -> mtk-camsv (subdev + /dev/videoN)` with zero dependency on the ISP Pass 1 (`cam-raw`), SCP co-processor firmware, request API, or media controller routing ioctls. Its `vb2_queue`, `v4l2_async_notifier`, `media_pipeline`, and runtime PM code in [mtk_camsv_video.c](../../../src/begonia-ftp/camera/ref/isp30/src/mtk_camsv_video.c) and [mtk_seninf.c](../../../src/begonia-ftp/camera/ref/isp30/src/mtk_seninf.c) were already reviewed through 8 iterations by Laurent Pinchart and CK Hu ([lore v8](https://lore.kernel.org/all/20250122-add-mtk-isp-3-0-support-v8-0-a3d3731eef45@baylibre.com/)).
2. **ISP7 `camsys` is a massive ~25,000-line multi-pipe ISP framework:** Its `seninf` driver (`mtk_cam-seninf-drv.c` + `mtk_cam-seninf-route.c`) is tightly coupled to `mtk-cam` (`cam-raw`,PDAF/HDR virtual channels, C-PHY, custom vendor V4L2 controls in `kd_imgsensor_define_v4l2.h`). Conversely, the actual MT6785 D-PHY + SENINF hardware sequence needed for 2-lane / 4-lane D-PHY is only ~120 lines of register writes (already proven in [ov-cap.py](../../../src/begonia-ftp/camera/ov8856-mipi/ov-cap.py#L118-L189)).

### 2.3 What Has to Change and Size Estimate

| Component | Base Source | Required Changes for MT6785 | Estimated Final Size (LoC) |
|---|---|---|---|
| **1. `mtk_camsv` driver** (`mtk_camsv.h`, `mtk_camsv_reg.h`, `mtk_camsv_hw.c`, `mtk_camsv_video.c`) | MT8365 ISP 3.0 ([ref/isp30/src/](../../../src/begonia-ftp/camera/ref/isp30/src/), 1,718 LoC) | • Map single `0x1000` resource (`0x1a050000 + 0x1000*i`).<br>• Update register offsets in `mtk_camsv_reg.h` (`TOP +0x510`, `TG +0x220`, `IMGO +0x20`, `FBC 0x110/0x114`).<br>• Update `mtk_camsv_fbc_init()` / `mtk_camsv_fbc_inc()` for `FBC_IMGO_CTL1` (`0x8000` / `0x8001`).<br>• Update `mtk_cam_format_info[]` (`imgo_stride = 0`, 1-pixel mode `PAK_MODE_RAW_10 = 2`, `SEN_MODE = 0x10001`, `0x400 = 1`).<br>• Clocks: `cam_main`, `cam_gals`, `cam_tg`, `cam_seninf`, `cam_sv0`/`sv1`, `cam_larb6`, `cam_larb7`. | **~1,550 LoC** (~150 lines modified from ISP 3.0) |
| **2. `mtk_seninf` driver** (`mtk_seninf.c`, `mtk_seninf_reg.h`) | V4L2 subdev/async/pad skeleton from ISP 3.0 ([mtk_seninf.c](../../../src/begonia-ftp/camera/ref/isp30/src/mtk_seninf.c), 1,568 LoC) + PHY/CSI2/MUX sequence from ISP7 `phy_2_0` ([hw_phy_2_0.c](../../../src/begonia-ftp/camera/ref/isp7-v1/src/mtk_cam-seninf-hw_phy_2_0.c)) | • Replace `mtk_seninf_Start()` / PHY calls with direct mapping of `mipi_rx_ana` (`0x11c80000`, `0x10000`) + `seninf` (`0x1a040000`, `0x6000`).<br>• Enable `CLK_APMIXED_MIPIC0` / `CLK_APMIXED_MIPIC1` via `clk_bulk` alongside `CLK_CAM_*` and `CLK_TOP_SENINF0..2`.<br>• Program `phyA_init`, `dphy_init` (settle delay), `CPHY_TOP+0x18\|=0x10`, `csi2_setting`, `phyA_setting` (4D1C clock lane select), `dphy_setting` (`CK_DATA_MUX_EN`), `phyA_power_on` (poll `ANA+0x48 & 0x29`), `TOP_MUX_CTRL`, `MUX` (`0x2d00`), and `CAM_MUX` (`0x400`).<br>• Optional module param `test_pattern=1` using `SENINF_TG` (`+0x600`) for sensorless testing. | **~1,100 LoC** (~450 lines of hw init replaced) |
| **3. Multi-channel I2C (`i2c-mt65xx`)** | Mainline `drivers/i2c/busses/i2c-mt65xx.c` + [i2c-mch/](../../../src/begonia-ftp/camera/NOTES.md#L111-L122) | • Support `mediatek,ch-offset = <0x100>` on camera buses (`i2c2`, `i2c4`, `i2c7`), PIO for `<= 8` bytes, and `mch_ackmask = 0` so NACKs do not lock the channel ([NOTES.md](../../../src/begonia-ftp/camera/NOTES.md#L144-L149)). | **~120 LoC** patch to `i2c-mt65xx.c` |
| **4. IOMMU / LARB7 & DT** | [mt6785.dtsi](../../../src/mt6785-mainline/arch/arm64/boot/dts/mediatek/mt6785.dtsi) + [mtk_iommu.c](../../../src/mt6785-mainline/drivers/iommu/mtk_iommu.c#L1593-L1604) | • Add `larb7@1a002000` (5 ports, `CLK_CAM_LARB7`) or bypass `SMI_LARB_NONSEC_CON` (`0x380 + 4*port`) for CMA initially; add `seninf`, `camsv0`, and sensor/regulator/MCLK DT nodes in `mt6785-lenovo-yt-j706f.dts`. | **~200 LoC** (DT + IOMMU/LARB table) |
| **Total** | | | **~2,970 LoC total** (~800 LoC of new/modified code on top of ISP 3.0) |

---

## 3. `libcamera`: `simple` Pipeline Handler and Software ISP Requirements & Limits

### 3.1 What `SimplePipelineHandler` and `SoftwareIsp` Need from the Kernel Side

In `libcamera`, the `simple` pipeline handler ([`src/libcamera/pipeline/simple/simple.cpp`](https://git.libcamera.org/libcamera/libcamera.git/tree/src/libcamera/pipeline/simple/simple.cpp)) and the Software ISP ([`src/libcamera/software_isp/software_isp.cpp`](https://git.libcamera.org/libcamera/libcamera.git/tree/src/libcamera/software_isp/software_isp.cpp)) require the following kernel contract:

1. **Driver Registration in `supportedDevices[]`:**
   `SimplePipelineHandler::match()` only binds to media controller device names explicitly listed in `supportedDevices[]` in [`simple.cpp`](https://git.libcamera.org/libcamera/libcamera.git/tree/src/libcamera/pipeline/simple/simple.cpp). Note that upstream `simple.cpp` already has `{ "mtk-seninf", { { "mtk-mdp", 3 } }, false }` (from BayLibre's MT8365 YUV sensor work, where `swIspEnabled` is `false`!). To use `SoftISP` with a raw Bayer sensor on MT6785, that entry in `simple.cpp` must have `swIspEnabled = true` (`{ "mtk-seninf", {}, true }`), or the media device driver name must match an entry with `swIspEnabled = true`.
2. **Media Graph Shape:**
   - A linear directed acyclic graph starting at a sensor entity with `function = MEDIA_ENT_F_CAM_SENSOR` (1 source pad), passing through 0 or more subdevs (`MEDIA_ENT_F_VID_IF_BRIDGE` / `MEDIA_ENT_F_PROC_VIDEO_PIXEL_FORMATTER`), and ending at a V4L2 video capture node (`MEDIA_ENT_F_IO_V4L`).
   - In the MT8365 ISP 3.0 driver ([mtk_seninf.c](../../../src/begonia-ftp/camera/ref/isp30/src/mtk_seninf.c) + [mtk_camsv_video.c](../../../src/begonia-ftp/camera/ref/isp30/src/mtk_camsv_video.c)), `mtk-seninf` registers the `media_device` and `v4l2_device`, and the graph is:
     `sensor (pad 0) -> (sink pad 0..3) mtk-seninf (source pad 4) -> (sink pad 0) mtk-camsv subdev (source pad 1) -> (sink pad 0) mtk-camsv video node (/dev/video0)`.
   - Every intermediate subdev must implement `V4L2_SUBDEV_FL_HAS_DEVNODE` so `SimplePipelineHandler` can open `/dev/v4l-subdev*` and call `VIDIOC_SUBDEV_ENUM_MBUS_CODE`, `VIDIOC_SUBDEV_G_FMT`, and `VIDIOC_SUBDEV_S_FMT` across every link in the pipeline.
   - Note: `mtk_camsv_video.c` uses the multiplanar API (`V4L2_CAP_VIDEO_CAPTURE_MPLANE`), which `libcamera`'s `V4L2VideoDevice` supports transparently alongside single-planar capture nodes.
3. **Formats (Media Bus Codes & V4L2 Pixel Formats):**
   - The sensor subdev and `seninf`/`camsv` subdevs must negotiate matching `MEDIA_BUS_FMT_S*8_1X8`, `MEDIA_BUS_FMT_S*10_1X10`, or `MEDIA_BUS_FMT_S*12_1X12` codes (`SBGGR`, `SGBRG`, `SGRBG`, `SRGGB`).
   - The `/dev/videoN` capture node must expose the corresponding V4L2 pixel format (`V4L2_PIX_FMT_S*8`, unpacked 16-bit `V4L2_PIX_FMT_S*10` / `V4L2_PIX_FMT_S*12`, or MIPI CSI-2 packed `V4L2_PIX_FMT_S*10P` / `V4L2_PIX_FMT_S*12P`).
   - **Important detail for MT6785 CAMSV:** When `CAMSV_PAK` is enabled in RAW10 mode (`CAMSV_PAK_PAK_MODE_RAW_10 = 2`, 10 bits per pixel, `BPL = width * 10 / 8`), the hardware writes **packed 10-bit data** (4 pixels in 5 bytes) into memory, whereas MT8365 ISP 3.0's [mtk_camsv_video.c](../../../src/begonia-ftp/camera/ref/isp30/src/mtk_camsv_video.c#L88-L130) advertises `V4L2_PIX_FMT_SBGGR10` / `SGRBG10` (which in V4L2 means 16-bit unpacked, 2 bytes/pixel) while calculating `bpl = ALIGN(DIV_ROUND_UP(width * 10, 8), 2)`! For `libcamera` `DebayerCpu` (which distinguishes 16-bit unpacked `SBGGR10` from 10-bit packed `SBGGR10P`), either:
     - Advertise `V4L2_PIX_FMT_S*10P` (if the byte packing matches MIPI CSI-2 RAW10: 4 MSBs-8bit bytes followed by 1 byte of 4x2 LSBs), **or**
     - Disable `PAK` (`CAMSV_MODULE_EN_PAK_EN = 0` or 16-bit unpacked mode) so each 10-bit pixel occupies 2 bytes (`V4L2_PIX_FMT_SGRBG10`), **or**
     - Verify the exact 4-pixel/5-byte packing order of MT6785 `CAMSV_PAK` (in [raw2png.py](../../../src/begonia-ftp/camera/camsv/raw2png.py), MT6785's packer stores four 10-bit values packed as a 40-bit little-endian bitstream across 5 bytes, which differs from standard MIPI CSI-2 `SBGGR10P` byte layout!). Running CAMSV in **unpacked 16-bit mode** (or RAW8) avoids any custom bitstream unpacking in `libcamera`.
4. **Mandatory V4L2 Controls and Selection Targets (`CameraSensorLegacy` / `CameraSensorRaw` & `IPASoftSimple`):**
   - Checked in [`src/libcamera/sensor/camera_sensor_raw.cpp`](https://git.libcamera.org/libcamera/libcamera.git/tree/src/libcamera/sensor/camera_sensor_raw.cpp) and [`src/ipa/simple/soft_simple.cpp`](https://git.libcamera.org/libcamera/libcamera.git/tree/src/ipa/simple/soft_simple.cpp):
     - **Required by `IPASoftSimple::init()`:** `V4L2_CID_EXPOSURE` and `V4L2_CID_ANALOGUE_GAIN` (if either is missing on the sensor subdev, `IPASoftSimple` refuses to initialize AGC).
     - **Required/ Strongly Expected by `CameraSensor`:** `V4L2_CID_PIXEL_RATE`, `V4L2_CID_HBLANK`, `V4L2_CID_VBLANK`, `V4L2_CID_LINK_FREQ`.
     - **Recommended DT properties (exposed via `v4l2_ctrl_new_fwnode_properties`):** `V4L2_CID_CAMERA_ORIENTATION` (`orientation` in DT) and `V4L2_CID_CAMERA_SENSOR_ROTATION` (`rotation` in DT).
   - **Kernel Buffer Allocation (`DmaBufAllocator`):** `SoftwareIsp` allocates output RGB/NV12 buffers using `/dev/dma_heap/system` (`CONFIG_DMABUF_HEAPS` + `CONFIG_DMABUF_HEAPS_SYSTEM`) or `/dev/udmabuf` (`CONFIG_UDMABUF`) ([`dma_buf_allocator.cpp`](https://git.libcamera.org/libcamera/libcamera.git/tree/src/libcamera/dma_buf_allocator.cpp)). At least one of `CONFIG_DMABUF_HEAPS_SYSTEM=y` or `CONFIG_UDMABUF=y` must be enabled in [yoga11.config](../../../kernel/configs/yoga11.config).

### 3.2 Current Limits of `libcamera` Software ISP & Performance on MT6785

- **Supported Input Bayer Formats ([`debayer_cpu.cpp`](https://git.libcamera.org/libcamera/libcamera.git/tree/src/libcamera/software_isp/debayer_cpu.cpp)):**
  - 8-bit raw Bayer: `SBGGR8`, `SGBRG8`, `SGRBG8`, `SRGGB8`.
  - 10-bit unpacked (16-bit LE storage): `SBGGR10`, `SGBRG10`, `SGRBG10`, `SRGGB10`.
  - 10-bit MIPI CSI-2 packed: `SBGGR10P`, `SGBRG10P`, `SGRBG10P`, `SRGGB10P`.
  - 12-bit unpacked (16-bit LE storage): `SBGGR12`, `SGBRG12`, `SGRBG12`, `SRGGB12`.
  - *Not supported:* Mediatek-proprietary 40-bit contiguous bitstream packing (unless unpacked to 16-bit in CAMSV or a 20-line unpacker loop is added to `debayer_cpu.cpp`).
- **Supported Output Formats:** `RGB888`, `BGR888`, `XRGB8888`, `ARGB8888`, `XBGR8888`, `ABGR8888` (used cleanly by PipeWire, `qcam`, Firefox/Chromium WebRTC, and Snapshot/Megapixels).
- **3A / Image Quality Limits ([`src/ipa/simple/algorithms/`](https://git.libcamera.org/libcamera/libcamera.git/tree/src/ipa/simple/algorithms)):**
  - Implements Black Level Correction (`blc.cpp`), Auto White Balance (`awb.cpp`, grey-world), Auto Gain/Exposure (`agc.cpp`), Gamma/LUT (`lut.cpp`), and Color Correction Matrix (`ccm.cpp`, recent libcamera >= 0.4).
  - Does **not** yet implement Lens Shading Correction (vignetting), Defect Pixel Correction, temporal/spatial denoising, or VCM autofocus in `IPASoftSimple` by default (though `ov8856` has on-sensor BLC, OTP defect pixel correction, and OTP lens shading correction enabled in its mode register tables! See [ov8856.c](../../../src/mt6785-mainline/drivers/media/i2c/ov8856.c#L1332-L1380), registers `0x5000 = 0x77` LENC + OTP + BLC enable).
- **Performance on MT6785 (2x Cortex-A76 @ 2.05 GHz + 6x Cortex-A55 @ 2.0 GHz, Mali-G76 MC4):**
  - `DebayerCpu` uses 1D lookup tables and processes each frame on a dedicated worker thread. On Cortex-A53/A55 cores (~1.8 GHz, e.g., Qualcomm SDM845 / Snapdragon 7c / Allwinner A64 benchmarks reported by Hans de Goede and Bryan O'Donoghue on the `libcamera` list, [Linaro SoftISP benchmarks](https://libcamera.org/blog/2025-12-18-software-isp-gpu)), single-threaded `DebayerCpu` takes:
    - **1632x1224 / 1640x1232 (2 MP 2x2 binned preview):** ~8–12 ms/frame on a single Cortex-A76 core (~25–35% of one big core at 30 fps) — **easily achieves smooth 30 fps** on CPU alone.
    - **3264x2448 / 3280x2464 (8 MP full sensor):** ~32–45 ms/frame on a single Cortex-A76 core (~22–30 fps at ~100% of one A76 core, or 30 fps with `DebayerEGL` on the Mali-G76 MC4 via Mesa Panfrost).
  - **GPU ISP (`DebayerEGL`, [`debayer_egl.cpp`](https://git.libcamera.org/libcamera/libcamera.git/tree/src/libcamera/software_isp/debayer_egl.cpp)):** Merged in `libcamera` v0.7.0 ([Phoronix v0.7.0](https://www.phoronix.com/news/libcamera-0.7-Released), [libcamera blog](https://libcamera.org/blog/2025-12-18-software-isp-gpu)). It uses OpenGL ES 2.0 fragment shaders + GBM/DMA-BUF, supported by Mesa's `panfrost` driver on MT6785's Bifrost Mali-G76 MC4, cutting CPU usage by >50% at full 8 MP resolution.

### 3.3 Platforms Working This Way Today (`simple` + Raw CSI Receiver + SoftISP)

All of the following platforms use a raw CSI-2 DMA receiver (with the hardware ISP bypassed or unimplemented) wired into `SimplePipelineHandler` + `SoftwareIsp` ([`simple.cpp`](https://git.libcamera.org/libcamera/libcamera.git/tree/src/libcamera/pipeline/simple/simple.cpp)):
1. **Qualcomm Snapdragon (`qcom-camss`):** [`drivers/media/platform/qcom/camss`](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/tree/drivers/media/platform/qcom/camss) uses the VFE's **RDI (Raw Dump Interface)** path (the exact Qualcomm equivalent of MediaTek's `CAMSV`) on SDM845 (OnePlus 6, POCO F1), SM7150/SC7180 (Xiaomi Mi A3, Acer Spin 513), SM8250, and X1E80100 laptops, feeding raw Bayer frames into `libcamera` SoftISP.
2. **Allwinner (`sun6i-csi`):** [`drivers/media/platform/sunxi/sun6i-csi`](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/tree/drivers/media/platform/sunxi/sun6i-csi) on PinePhone / PineTab (Allwinner A64) captures raw Bayer directly to DRAM for `SimplePipelineHandler`.
3. **Rockchip (`rockchip-cif` / `rkcif`):** [`drivers/media/platform/rockchip/rkcif`](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/tree/drivers/media/platform/rockchip/rkcif) on PX30 / RK3568 / RK3588 captures raw MIPI CSI-2 frames to memory without the RkISP1 block.
4. **Intel IPU6 (`intel-ipu6` / `ipu-bridge`):** [`drivers/media/pci/intel/ipu6`](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/tree/drivers/media/pci/intel/ipu6) (merged in Linux 6.10) exposes only the **ISYS (Input System)** raw CSI-2 DMA receiver in mainline (equivalent to `SENINF + CAMSV`, bypassing the proprietary PSYS ISP) and relies on `SimplePipelineHandler` + `SoftwareIsp` with `ov8856`, `ov2740`, and `hi556` on Tiger Lake / Alder Lake / Raptor Lake laptops/tablets.
5. **TI J721E (`j721e-csi2rx`):** [`drivers/media/platform/ti/j721e-csi2rx`](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/tree/drivers/media/platform/ti/j721e-csi2rx) — Cadence CSI-2 bridge + TI SHIM DMA raw receiver enabled with `swIspEnabled = true` in `simple.cpp`.

---

## 4. Camera Sensors: Mainline `ov8856` and Candidate Second Sensors

From [CAMERA.md](../../../docs/hardware/CAMERA.md), the Lenovo Yoga Tab 11 (`YT-J706F`) stock firmware names `ov8856_mipi_raw` (8 MP OmniVision OV8856), and has two physical cameras (`cam0` on `i2c2` or `i2c4`, `cam1` on `i2c4`; one rear 8 MP with autofocus on `GPIO197`, one front 8 MP fixed-focus). Below is the complete technical reference for `ov8856` and the candidate 8 MP / auxiliary sensors.

### 4.1 Mainline `ov8856` (`drivers/media/i2c/ov8856.c`)

- **Source & DT Binding:**
  - Driver: [drivers/media/i2c/ov8856.c](../../../src/mt6785-mainline/drivers/media/i2c/ov8856.c) ([`git.kernel.org`](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/tree/drivers/media/i2c/ov8856.c), 2,496 lines).
  - Binding: [Documentation/devicetree/bindings/media/i2c/ovti,ov8856.yaml](../../../src/mt6785-mainline/Documentation/devicetree/bindings/media/i2c/ovti,ov8856.yaml) ([`git.kernel.org`](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/tree/Documentation/devicetree/bindings/media/i2c/ovti,ov8856.yaml)).
- **Chip ID & I2C Address:**
  - 7-bit I2C address: **`0x10`** (8-bit write ID `0x20` in MediaTek vendor tables, or `0x36` if SID pin is pulled high).
  - Chip ID register: **`0x300a`..`0x300c`** (24-bit read in mainline [ov8856.c#L27-L28](../../../src/mt6785-mainline/drivers/media/i2c/ov8856.c#L27-L28)) = **`0x00885a`**.
- **Required DT Properties ([ovti,ov8856.yaml#L92-L100](../../../src/mt6785-mainline/Documentation/devicetree/bindings/media/i2c/ovti,ov8856.yaml#L92-L100)):**
  - `compatible = "ovti,ov8856"`; `reg = <0x10>`
  - `clocks = <&topckgen CLK_TOP_CAMTG...>` and `clock-names = "xvclk"`
  - `dovdd-supply` (1.8 V I/O, `mt6359_vcamio_ldo`), `avdd-supply` (2.8 V analog, `GPIO195`), `dvdd-supply` (1.2 V digital, `GPIO50`)
  - `reset-gpios = <&pio 119 GPIO_ACTIVE_LOW>` (for `cam0`) or `<&pio 124 GPIO_ACTIVE_LOW>` (for `cam1`). Note: `gpiod_set_value_cansleep(reset_gpio, 1)` asserts reset (drives pin LOW when `GPIO_ACTIVE_LOW` is specified in DT) and `0` deasserts reset (drives pin HIGH = run), matching [CAMERA.md](../../../docs/hardware/CAMERA.md#L33)!
  - Endpoint: `data-lanes = <1 2>` or `<1 2 3 4>`, and `link-frequencies = /bits/ 64 <...>`.
- **Supported Lanes, Link Frequencies, and Modes ([ov8856.c#L1460-L1590](../../../src/mt6785-mainline/drivers/media/i2c/ov8856.c#L1460-L1590)):**
  - **Critical DT Endpoint Rule ([ov8856.c#L2345-L2358](../../../src/mt6785-mainline/drivers/media/i2c/ov8856.c#L2345-L2358)):** `ov8856_get_hwcfg()` loops over **both** entries in `priv_lane->link_freq_menu_items[]` and returns `-EINVAL` (`"no link frequency %lld supported"`) unless **both** link frequencies for the chosen lane count are listed in the DT `link-frequencies` property!
  - **2-lane configuration (`data-lanes = <1 2>`, `lane_cfg_2`):**
    - Required `link-frequencies = /bits/ 64 <720000000 360000000>;`
    - Mode 0: `3280x2464` @ 30 fps (`hts = 1928`, `vts_def = 2488`, link freq `720 MHz` = 1440 Mbps/lane, default `MEDIA_BUS_FMT_SGRBG10_1X10`).
    - Mode 1: `1640x1232` @ 30 fps (`hts = 3168`, `vts_def = 1514`, link freq `360 MHz` = 720 Mbps/lane, default `MEDIA_BUS_FMT_SGRBG10_1X10`).
  - **4-lane configuration (`data-lanes = <1 2 3 4>`, `lane_cfg_4`):**
    - Required `link-frequencies = /bits/ 64 <360000000 180000000>;`
    - Mode 0: `3280x2464` @ 30 fps (link freq `360 MHz`, `SGRBG10_1X10`).
    - Mode 1: `1640x1232` @ 30 fps (link freq `180 MHz`, `SGRBG10_1X10`).
    - Mode 2: `3264x2448` @ 30 fps (link freq `360 MHz`, `SBGGR10_1X10`).
    - Mode 3: `1632x1224` @ 30 fps (link freq `180 MHz`, `SBGGR10_1X10`).
  - Supported media bus codes: `MEDIA_BUS_FMT_SBGGR10_1X10` and `MEDIA_BUS_FMT_SGRBG10_1X10` (switches horizontal window start `0x3813` between `0x02` and `0x01`).
  - Exposed V4L2 controls ([ov8856.c#L1888-L1970](../../../src/mt6785-mainline/drivers/media/i2c/ov8856.c#L1888-L1970)): `LINK_FREQ`, `PIXEL_RATE`, `VBLANK`, `HBLANK`, `ANALOGUE_GAIN` (`128..2047`), `DIGITAL_GAIN` (`0..4095`), `EXPOSURE`, `TEST_PATTERN`, `HFLIP`, `VFLIP`, plus `ORIENTATION` / `ROTATION` — **100% compliant with `libcamera` `SimplePipelineHandler` and `IPASoftSimple`**.
- **Known Quirks:**
  1. **19.2 MHz vs 24 MHz `xvclk` Rate ([ov8856.c#L23](../../../src/mt6785-mainline/drivers/media/i2c/ov8856.c#L23), [#L2291-L2294](../../../src/mt6785-mainline/drivers/media/i2c/ov8856.c#L2291-L2294)):**
     - Mainline `ov8856.c` only has PLL tables for `OV8856_XVCLK_19_2` (19.2 MHz). On MT6785, `camtg_parents` in [clk-mt6785-top.c#L222-L231](../../../src/mt6785-mainline/drivers/clk/mediatek/clk-mt6785-top.c#L222-L231) can only generate **24 MHz** (`univpll_192m_d8`) or **26 MHz** (`clk26m`), not 19.2 MHz.
     - At probe time, `ov8856_get_hwcfg()` logs a warning (`dev_warn(dev, "external clock rate 24000000 is unsupported")`) and **still succeeds** (confirmed on begonia in [NOTES.md#L139-L140](../../../src/begonia-ftp/camera/NOTES.md#L139-L140)).
     - However, during streaming, if 24 MHz is fed into the 19.2 MHz PLL multipliers (`0x0302 = 0x4b` (75), `0x030d = 0x4b` (75)), all internal clocks (`SCLK` and MIPI bit rate) run **1.25x faster** (`24 / 19.2 = 1.25`: the 360 MHz link freq runs at 450 MHz, and the 720 MHz link freq runs at 900 MHz, exceeding the sensor's 1440 Mbps/lane specification!).
     - **Fix for 24 MHz:** In `mipi_data_rate_lane_2` / `mipi_data_rate_lane_4` (or in a `xvclk_rate == 24000000` branch in [ov8856.c](../../../src/mt6785-mainline/drivers/media/i2c/ov8856.c#L165-L208), matching [ov8856ofilm_vendor.c#L782-L787](../../../src/begonia-ftp/camera/ref/ov8856ofilm_vendor.c#L782-L787)), scale the PLL multipliers by `4/5` (`19.2 / 24`): for 720 Mbps/lane (`360 MHz` link freq), set `0x0302 = 0x3c` (60 instead of 75, `24 MHz * 60 / 2 = 720 Mbps`) and `0x030b = 0x00, 0x030d = 0x1e` (or `0x030b = 0x02, 0x030d = 0x3c`, giving `SCLK = 144 MHz`).
  2. **ACPI D0 Probe Waiver (`full_power = acpi_dev_state_d0(ov8856->dev)`):**
     On DT platforms, `acpi_dev_state_d0()` returns `true`, so `ov8856_probe()` powers on the sensor, reads the chip ID `0x00885a` over I2C, and powers it back off via runtime PM ([ov8856.c#L2398-L2411](../../../src/mt6785-mainline/drivers/media/i2c/ov8856.c#L2398-L2411)). Note that `ov8856_identify_module()` does **not** check the OTP module revision (`0x700f`) unless running on a pre-existing ACPI power state where OTP was loaded; in `ov8856_probe()` it only checks `0x300a..0x300c == 0x00885a`.

### 4.2 Candidate Second Sensors: Upstream Status and Patch/Source Links

| Sensor | Resolution / Interface | Typical 7-bit I2C Addr | Chip ID Reg -> Value | Upstream Status (Mainline 7.1) | Mainline / On-List / Out-of-Tree Source Links |
|---|---|---|---|---|---|
| **Hynix Hi-846** (`hynix,hi846`) | 8 MP (3264x2448), 2/4-lane MIPI RAW10 (`SGBRG10`) | `0x20` (or `0x21`) | `0x0f16` (H) = `0x08`, `0x0f17` (L) = `0x46` (`0x0846`) | **Merged in mainline** (since Linux 5.16) | • Driver: [drivers/media/i2c/hi846.c](../../../src/mt6785-mainline/drivers/media/i2c/hi846.c) ([`git.kernel.org`](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/tree/drivers/media/i2c/hi846.c))<br>• Binding: [hynix,hi846.yaml](../../../src/mt6785-mainline/Documentation/devicetree/bindings/media/i2c/hynix,hi846.yaml) ([`git.kernel.org`](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/tree/Documentation/devicetree/bindings/media/i2c/hynix,hi846.yaml)) |
| **Samsung S5K4H7 / S5K4H7YX** (`samsung,s5k4h7`) | 8 MP (3264x2448), 2/4-lane MIPI RAW10 (`SGRBG10`/`SBGGR10`) | `0x10` (write `0x20`) or `0x2d` (write `0x5a`) | `0x0000` (16-bit) = `0x487b` | **Not in mainline and never posted to `lore.kernel.org`** | • Out-of-tree V4L2 subdev driver in Rockchip BSP: [`github.com/rockchip-linux/kernel` `drivers/media/i2c/s5k4h7.c`](https://github.com/rockchip-linux/kernel/blob/develop-4.19/drivers/media/i2c/s5k4h7.c)<br>• Mainline Samsung ISOCELL template: [`drivers/media/i2c/s5kjn1.c`](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/tree/drivers/media/i2c/s5kjn1.c) |
| **GalaxyCore GC5035** (`galaxycore,gc5035`) | 5 MP (2592x1944), 2-lane MIPI RAW10 (`SRGGB10`) | `0x37` (write `0x6e`) or `0x3f` (write `0x7e`) | `0xf0` = `0x50`, `0xf1` = `0x35` (`0x5035`) | **On list (`linux-media` v4) & in ChromeOS kernel** (not merged in mainline) | • On-list v4 series (Tomasz Figa, 2020-09-25): [`lore.kernel.org` cover](https://lore.kernel.org/linux-media/20200925134625.2768789-1-tfiga@chromium.org/) / [Patch 3/4 `gc5035.c` (IU LKML)](https://lkml.iu.edu/hypermail/linux/kernel/2009.3/02641.html)<br>• Maintained ChromeOS driver: [`chromium.googlesource.com` `drivers/media/i2c/gc5035.c`](https://chromium.googlesource.com/chromiumos/third_party/kernel/+/refs/heads/chromeos-5.10/drivers/media/i2c/gc5035.c) |
| **GalaxyCore GC8034** (`galaxycore,gc8034`) | 8 MP (3264x2448), 2/4-lane MIPI RAW10 (`SRGGB10`) | `0x37` (write `0x6e`) | `0xf0` = `0x80`, `0xf1` = `0x44` (`0x8044`) | **Not in mainline and never posted to `lore.kernel.org`** | • Out-of-tree V4L2 subdev driver in Rockchip 5.10/6.1 BSP: [`github.com/rockchip-linux/kernel` `drivers/media/i2c/gc8034.c`](https://github.com/rockchip-linux/kernel/blob/develop-5.10/drivers/media/i2c/gc8034.c)<br>• Mainline GalaxyCore 8 MP CCI template: [`drivers/media/i2c/gc08a3.c`](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/tree/drivers/media/i2c/gc08a3.c) |
| **GalaxyCore GC02M1** (`galaxycore,gc02m1`) | 2 MP (1600x1200), 1-lane MIPI RAW10 | `0x37` (write `0x6e`) or `0x10` (write `0x20`) | `0xf0` = `0x02`, `0xf1` = `0xd0` (`0x02d0`) | **Not in mainline and never posted to `lore.kernel.org`** | • Out-of-tree V4L2 subdev driver in Rockchip 5.10 BSP: [`github.com/rockchip-linux/kernel` `drivers/media/i2c/gc02m1.c`](https://github.com/rockchip-linux/kernel/blob/develop-5.10/drivers/media/i2c/gc02m1.c)<br>• Mainline GalaxyCore CCI template: [`drivers/media/i2c/gc05a2.c`](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/tree/drivers/media/i2c/gc05a2.c) |

**Additional notes on `hi846.c` if fitted:**
- Mainline [hi846.c](../../../src/mt6785-mainline/drivers/media/i2c/hi846.c#L1060-L1138) supports 2 or 4 lanes, `link-frequencies = /bits/ 64 <80000000 200000000>`, and three modes (`640x480@120`, `1280x720@90`, `1632x1224@30`; 3264x2448 is not yet in `supported_modes[]`). It logs a non-fatal `dev_warn` if `mclk` is not 25 MHz ([hi846.c#L2062-L2065](../../../src/mt6785-mainline/drivers/media/i2c/hi846.c#L2062-L2065)).
- Also note from [CAMERA.md](../../../docs/hardware/CAMERA.md#L18-L25) that the stock firmware *only* names `ov8856_mipi_raw`: it is very common on Lenovo tablets (and confirmed on `google-krane` SKU variants) for **both** front and rear cameras—or the primary camera—to be `OV8856` (or `OV8856` + `S5K4H7`). Only an I2C ID probe on `i2c2` and `i2c4` with `cam0` and `cam1` powered will definitively identify both slots.

---

## 5. Other Mainline Ports of MT6785 / MT6768 / MT6765-Class Devices and Camera Status

A thorough search across `lore.kernel.org`, GitLab mainlining groups, and the postmarketOS device wiki shows:

1. **MT6785 (Helio G90T / G95):**
   - Active mainline ports exist in [`gitlab.com/mt6785-mainline/linux`](https://gitlab.com/mt6785-mainline/linux) (maintained by Dinolek et al.) for the **Xiaomi Redmi Note 8 Pro (`xiaomi-begonia`)** ([postmarketOS wiki](https://wiki.postmarketos.org/wiki/Xiaomi_Redmi_Note_8_Pro_(xiaomi-begonia))) and **Xiaomi Redmi Note 10S (`xiaomi-rosemary`)** ([postmarketOS wiki](https://wiki.postmarketos.org/wiki/Xiaomi_Redmi_Note_10S_(xiaomi-rosemary))).
   - **Camera status:** Prior to the November 2026 bring-up work on `begonia` in [src/begonia-ftp/camera/NOTES.md](../../../src/begonia-ftp/camera/NOTES.md), **no MT6785 device had working cameras on mainline**. The `begonia` effort is the first on MT6785 to identify sensors over the multi-channel I2C controller (`i2c-mt65xx-mch`), bind mainline `ov8856`, capture a full 640x480 RAW10 frame from the SENINF test pattern generator through `CAMSV0` DMA to RAM, and stream real MIPI CSI-2 packets from `OV8856` through `CSI2 -> SENINF4 -> MUX2 -> CAM_MUX2 -> CAMSV0 TG` after enabling `CLK_APMIXED_MIPIC0`/`MIPIC1`.
2. **MT6768 (Helio P65 / G80 / G85) and MT6765 (Helio P35 / G35):**
   - Community mainline trees exist at [`gitlab.com/mt6768-mainline/linux`](https://gitlab.com/mt6768-mainline/linux) and [`gitlab.com/mt6765-mainline/linux`](https://gitlab.com/mt6765-mainline/linux) (covering devices such as Xiaomi Redmi 9 `xiaomi-lancelot`, Redmi 9A `xiaomi-dandelion`, and Samsung Galaxy A12 `samsung-a12`).
   - **Camera status:** **No MT6768 or MT6765 mainline port has working cameras.** All postmarketOS wiki pages for MT6765/MT6768 devices list Camera as Broken/Non-functional because no mainline `seninf`/`camsv` driver existed.
3. **Adjacent MediaTek SoCs That *Did* Get Mainline/Close-to-Mainline Camera Working, and How:**
   - **MT8365 (Genio 350 EVK):** BayLibre got both raw Bayer (`OV5640` / `IMX214`) and YUV (`AP1302` external ISP) cameras streaming into V4L2 and `libcamera`'s `simple` pipeline handler using the **exact `mtk_seninf` + `mtk_camsv` raw-bypass architecture** ([lore ISP 3.0 v8](https://lore.kernel.org/all/20250122-add-mtk-isp-3-0-support-v8-0-a3d3731eef45@baylibre.com/), [`libcamera` `mtk-seninf` commit](https://git.libcamera.org/libcamera/libcamera.git/tree/src/libcamera/pipeline/simple/simple.cpp)).
   - **MT8183 (`google-kukui` / `google-krane` Lenovo IdeaPad Duet):** Uses `OV8856` (rear) + `OV2685` (front) or `GC5035` (`google-kodama`) ([`mt8183-kukui-krane.dtsi` on `git.kernel.org`](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/tree/arch/arm64/boot/dts/mediatek/mt8183-kukui-krane.dtsi), [postmarketOS `google-krane` wiki](https://wiki.postmarketos.org/wiki/Lenovo_IdeaPad_Duet_Chromebook_(google-krane))). On ChromeOS 5.10/5.15 it uses the out-of-tree `mtk-isp` (`isp_50` P1 + DIP + SCP firmware + proprietary CrOS 3A HAL), which has **not** worked on pure mainline because P1/DIP were never upstreamed — further confirming that for mainline Linux + `libcamera`, **SENINF + CAMSV + SoftISP** is the only viable, firmware-free route.

---

## 6. Recommended Route for the Lenovo Yoga Tab 11 (`YT-J706F`)

### Milestone Plan

#### Milestone M0 — Multi-Channel I2C, Sensor Power/Clocks, and Chip ID Discovery (`cam0` & `cam1`)
- **Goal:** Power up `cam0` and `cam1` on `YT-J706F` and identify the exact sensors, I2C buses (`i2c2` @ `0x11009000`, `i2c4` @ `0x11011000`), 7-bit addresses, and VCM/EEPROM addresses.
- **Concrete Steps:**
  1. Port the multi-channel I2C support (`ch_offset = 0x100`, PIO for `<= 8` bytes, `mch_ackmask = 0` NACK fix from [NOTES.md#L111-L149](../../../src/begonia-ftp/camera/NOTES.md#L111-L149)) to `i2c2` (`0x11009000`) and `i2c4` (`0x11011000`). Note from [mt6785.dtsi#L1176-L1187](../../../src/mt6785-mainline/arch/arm64/boot/dts/mediatek/mt6785.dtsi#L1176-L1187) that `i2c2` and `i2c4` have `0x1000` register windows in `mt6785.dtsi` ( verify if `0x200` is needed for channel `+0x100`).
  2. Configure `YT-J706F` camera power and clocks per [CAMERA.md](../../../docs/hardware/CAMERA.md#L27-L44):
     - `vcamio`: MT6359 `vcamio` LDO (1.8 V).
     - `vcama`: `GPIO195` (shared analog switch), `vcamd`: `GPIO50` (shared digital switch), `vcamaf`: `GPIO197`.
     - Reset: `GPIO119` (`cam0`, high = run), `GPIO124` (`cam1`, high = run).
     - MCLK: `GPIO117` function 1 (`CMMCLK`, drive-strength `4` mA) for `cam0`, `GPIO120` function 1 (`CMMCLK`, `4` mA) for `cam1`, with `CLK_TOP_CAMTG1..5` parented to `univpll_192m_d8` (24 MHz).
  3. Scan `i2c2` and `i2c4` while `cam0` and `cam1` are powered to confirm which slot holds `OV8856` (`0x10`, reg `0x300a..0x300c = 0x00885a`) and what the second sensor is (another `OV8856` at `0x10`/`0x36`, `S5K4H7` at `0x10`/`0x2d` reg `0x0000 = 0x487b`, `Hi-846` at `0x20` reg `0x0f16 = 0x0846`, or `GC8034`/`GC5035` at `0x37` reg `0xf0/0xf1`).

#### Milestone M1 — SENINF Test Pattern -> CAMSV0 -> Memory (Sensorless DMA Verification)
- **Goal:** Verify the SoC-side capture pipeline (`SENINF -> MUX -> CAM_MUX -> CAMSV0 -> IMGO DMA -> RAM`) on `YT-J706F` before involving MIPI CSI-2 or sensors.
- **Concrete Steps:**
  1. Bring up `seninf` (`0x1a040000`) + `camsv0` (`0x1a050000`) with `MT6785_POWER_DOMAIN_CAM`, `CLK_CAM_MAIN/GALS/TG/SENINF/SV0/LARB6/LARB7`, and `CLK_TOP_SENINF0..2`.
  2. Configure either `larb6`/`larb7` IOMMU bypass (`SMI_LARB_NONSEC_CON` bit 0 cleared on `0x1a001000` and `0x1a002000` with CMA, as in [larb-bypass.py](../../../src/begonia-ftp/camera/camsv/larb-bypass.py)) or add `larb7` to `mt6785.dtsi` and `mtk_iommu.c`.
  3. Run the 640x480 SENINF test pattern (`SENINF_TG +0x600`) into `CAMSV0` (`STRIDE = BPL` without bit 24, `FBC_IMGO_CTL1 = 0x8000` then `|= 1`) and verify a full 384,000-byte frame.

#### Milestone M2 — Real Sensor (`OV8856`) MIPI CSI-2 Frame Capture
- **Goal:** Capture real frames from `OV8856` over MIPI CSI-2 into memory.
- **Concrete Steps:**
  1. Enable `CLK_APMIXED_MIPIC0` and `CLK_APMIXED_MIPIC1` ([clk-mt6785-apmixed.c#L30-L34](../../../src/mt6785-mainline/drivers/clk/mediatek/clk-mt6785-apmixed.c#L30-L34)) so the MIPI CSI 26 MHz reference clocks are active and `ANA + 0x48` calibrates (`& 0x29 == 0x29`).
  2. Determine which CSI port (`CSI0` -> `SENINF0`, `CSI1` -> `SENINF2`, or `CSI2` -> `SENINF4`) receives HS transitions (`DPHY + 0x30 / +0x34`) and packet counts (`CSI2 + 0xdc`) when `cam0` / `cam1` streams.
  3. Resolve the last bug seen at the end of `begonia`'s log ([NOTES.md#L321-L325](../../../src/begonia-ftp/camera/NOTES.md#L321-L325)): when `OV8856` streamed 640x480, `CAMSV TG_FRMSIZE` read `0x028001e1` (640x481) while `CAMSV` was configured before sensor stream-on, causing `IMGO_ERR`. Fix by starting/resetting `CAMSV` (`SW_CTL 4 -> 0 -> 1 -> 0`) and pulsing `FBC_IMGO_CTL1 |= 1` *after* SENINF MUX sees valid frames, or matching `GRAB_LIN` to `<=` active lines.
  4. Patch `ov8856.c` PLL multipliers (`0x0302`, `0x030d`) for the 24 MHz `xvclk` (`univpll_192m_d8`) so 1640x1232 and 3280x2464 run at nominal link frequencies (360 MHz / 720 MHz) instead of 1.25x overclocked.

#### Milestone M3 — Proper V4L2 Media-Controller Driver (`mtk-seninf` + `mtk-camsv`)
- **Goal:** Clean kernel modules exposing `/dev/media0`, `/dev/v4l-subdev*`, and `/dev/video0` (and `/dev/video1` via `camsv1` for the second camera).
- **Concrete Steps:**
  1. Adapt the BayLibre ISP 3.0 `mtk_seninf.c` + `mtk_camsv_*.c` drivers ([ref/isp30/src/](../../../src/begonia-ftp/camera/ref/isp30/src/)) with the MT6785 `phy_2_0` SENINF sequences and shifted CAMSV register map (`+0x510` top, `+0x220` TG, `+0x20` IMGO, `0x110` FBC) as detailed in Section 2.
  2. Output standard 16-bit unpacked Bayer (`V4L2_PIX_FMT_SGRBG10` / `SBGGR10`, or standard `SGRBG10P`) so standard V4L2 tools (`v4l2-ctl`, `media-ctl`) and `libcamera` can consume buffers directly without custom bitstream unpacking.

#### Milestone M4 — `libcamera` Software ISP + Desktop Integration (PipeWire / WirePlumber)
- **Goal:** Working camera preview and capture in user-space applications via `libcamera` (`cam`, `qcam`, PipeWire).
- **Concrete Steps:**
  1. Ensure `CONFIG_DMABUF_HEAPS_SYSTEM=y` or `CONFIG_UDMABUF=y` is enabled in `kernel/configs/yoga11.config`.
  2. In `libcamera` `src/libcamera/pipeline/simple/simple.cpp`, set `swIspEnabled = true` for `mtk-seninf` (`{ "mtk-seninf", {}, true }`).
  3. Test with `cam -l` and `cam -c 1 --capture=10`, then verify PipeWire camera nodes (`wpctl status`) and add the second sensor (`cam1`) and VCM (`dw9714` / `dw9768` at `0x0c` once identified).

### Key Risks and Mitigations

1. **Unknown CSI-2 Port / Lane Mapping on `YT-J706F`:**
   - *Risk:* Stock DT does not state which CSI port (`CSI0`, `CSI1`, `CSI2`) or how many lanes (2 vs 4) each sensor uses ([CAMERA.md#L47-L51](../../../docs/hardware/CAMERA.md#L47-L51)).
   - *Mitigation:* Enable all three CSI ports (`CSI0 -> SENINF0`, `CSI1 -> SENINF2`, `CSI2 -> SENINF4`) while the sensor streams in 2-lane mode and read `DPHY + 0x30` (clock/data lane HS FSM) and `CSI2 + 0xdc` (`PACKET_CNT`) across all three ports; the active port and active data lanes (`DPHY + 0x34`) identify themselves immediately.
2. **CAMSV `IMGO_ERR` on Live MIPI Stream ([NOTES.md#L321-L325](../../../src/begonia-ftp/camera/NOTES.md#L321-L325)):**
   - *Risk:* On `begonia`, `CAMSV` DMA worked with the SENINF test pattern but raised `IMGO_ERR` (`bit 16 + bit 19`) when `OV8856` streamed 640x481 lines into a 640x480 window configured prior to stream-on.
   - *Mitigation:* Perform `CAMSV` `SW_CTL` reset and `FBC` `RCNT_INC` *after* `SENINF_MUX` is streaming, and ensure `SEN_GRAB_PXL` / `SEN_GRAB_LIN` do not exceed the sensor's active frame size or use the mainline `ov8856` 1640x1232 mode (`vts = 1514`, exact 1232 active lines).
3. **Second Sensor Lacks a Mainline Driver (e.g., `S5K4H7` or `GC8034`):**
   - *Risk:* If the second camera is `S5K4H7` (`0x487b`) or `GC8034` (`0x8044`), mainline 7.1 has no built-in driver.
   - *Mitigation:* The Rockchip BSP `drivers/media/i2c/s5k4h7.c` ([GitHub](https://github.com/rockchip-linux/kernel/blob/develop-4.19/drivers/media/i2c/s5k4h7.c)) and `gc8034.c` ([GitHub](https://github.com/rockchip-linux/kernel/blob/develop-5.10/drivers/media/i2c/gc8034.c)) are already standalone V4L2 subdev drivers with complete mode/register tables for 24 MHz `xvclk` and can be adapted to Linux 7.1 in ~1 day after `OV8856` is streaming.
4. **IOMMU vs CMA (`larb6` / `larb7`):**
   - *Risk:* `larb7` (`0x1a002000`) is not wired into `mt6785.dtsi` or `mt6785_data_mm.larbid_remap` in `mtk_iommu.c` ([mtk_iommu.c#L1597](../../../src/mt6785-mainline/drivers/iommu/mtk_iommu.c#L1597)).
   - *Mitigation:* For initial bring-up and `vb2-dma-contig` CMA buffers, clearing bit 0 (`MMU_EN`) in `SMI_LARB_NONSEC_CON` (`0x380 + 4*port`) on `larb6` and `larb7` is already proven to work on MT6785 ([NOTES.md#L248-L250](../../../src/begonia-ftp/camera/NOTES.md#L248-L250)); proper IOMMU mapping can be enabled later by testing `MMU_EN` port-by-port on `larb6`/`larb7`.
