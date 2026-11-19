# Hardware video decoding on MT6785: feasibility from the code

Scope: what the source trees say about the MT6785 (Helio G90T) video
decoder, and what mainline `mtk-vcodec` would need to drive it on the
YT-J706F. Nothing here was measured on the unit; every statement cites a
file in `src/`, or is marked **unverified**. Estimates of effort are
labelled as estimates.

Trees used:

- `src/lenovo-gpl-4.14`: the vendor 4.14 GPL release. It is a sparse,
  blobless partial clone at commit `975d4381`. The DTS, defconfig and
  clock files are checked out. `drivers/misc/mediatek/{videocodec,jpeg,
  scp,vpu,vdec_fmt}` were read from the local git object store. The
  `drivers/media/platform/{Kconfig,mtk-vcodec,mtk-vcu}` blobs are not in
  the local store: they were read from the tree's public origin at the
  same commit, so they are cited by path and function name, without line
  numbers.
- `src/mt6785-mainline`: Linux 7.1, branch `yt11`.
- `kernel/configs/pmos-mt6785.config`: the project's kernel config.

Correction to the starting assumption: in mainline 7.1, the MT8183
decoder is **stateless**, not stateful. `mtk_vdec_8183_pdata` sets
`.uses_stateless_api = true` and `MTK_VDEC_PURE_SINGLE_CORE`
(`drivers/media/platform/mediatek/vcodec/decoder/mtk_vcodec_dec_stateless.c:917-932`).
It still goes through SCP firmware for every frame
(`vdec/vdec_h264_req_if.c:282-285, 398`: `SCP_IPI_VDEC_H264`,
`vpu_dec_init`, `vpu_dec_start`). Only MT8173 uses the stateful path
(`mtk_vdec_8173_pdata`, `mtk_vcodec_dec_stateful.c:609-621`).

---

## 1. Vendor decode architecture on MT6785

### 1.1 Which driver the tablet's kernel builds

| Item | Evidence |
|---|---|
| V4L2 codec driver with the VCU backend | `arch/arm64/configs/yoga11_defconfig:295` `CONFIG_VIDEO_MEDIATEK_VCU_WO_FUSE=y`, `:296` `CONFIG_VB2_MEDIATEK_DMA_CONTIG=y`, `:297` `CONFIG_VIDEO_MEDIATEK_VCODEC=y` |
| `VIDEO_MEDIATEK_VCODEC` selects `VIDEO_MEDIATEK_VCU`; `VCU_WO_FUSE` removes the default FUSE transport for IPIs to the daemon | `drivers/media/platform/Kconfig` (entries `VIDEO_MEDIATEK_VCODEC`, `VIDEO_MEDIATEK_VCU_WO_FUSE`) |
| Codec glue = VCU backend only (`vdec_common_if`, `vdec_log_if`, `vdec_vcu_if`; the VPU backend's `vdec_h264_if` etc. only under `CONFIG_VIDEO_MEDIATEK_VPU`, which is not set) | `drivers/media/platform/mtk-vcodec/Makefile` |
| SoC files | `drivers/media/platform/mtk-vcodec/mt6785/{mtk_vcodec_dec_pm,mtk_vcodec_enc_pm,mtk_vcodec_intr,vcodec_bw,vcodec_dvfs}.c` (in `git ls-tree`). The Makefile selects them with `$(MTK_PLATFORM)`, which it sets only for MT6893/6833/6877/6781. `drivers/misc/mediatek/Makefile:16` exports `MTK_PLATFORM`. How that value reaches `drivers/media` is **unverified**. |
| `drivers/misc/mediatek/video` is the **display** driver, not a codec | `drivers/misc/mediatek/Makefile:144` `obj-$(CONFIG_MTK_FB) += video/`; content is `video/mt6785/dispsys/ddp_*.c` |
| The older `/dev/Vcodec` kernel driver is not used on MT6785 | `drivers/misc/mediatek/Makefile:149` (needs `CONFIG_MTK_VIDEOCODEC_DRIVER`, `default n` in `videocodec/Kconfig`, absent from `yoga11_defconfig`). `videocodec/` has only mt6739/6765/6771/6885 subdirectories. |
| `vdec_fmt` (VDEC formatter, "miniMDP") is not used | `drivers/misc/mediatek/Makefile:133` needs `CONFIG_MTK_VDEC_FMT`, absent from `yoga11_defconfig`; no `mediatek-vdec-fmt` node in `mt6785.dts` |
| `CONFIG_MTK_VPU_SUPPORT=y` is the APU image DSP, not a video VPU | `yoga11_defconfig:221`; `drivers/misc/mediatek/vpu/Kconfig` ("image processing", `select MTK_APUSYS_VPU`) |

The tablet's DTB is `mediatek/mt6785` appended to the image
(`yoga11_defconfig:42-43`). `yoga11.dts` is an overlay (`yoga11.dts:13-14`)
and has no vdec, venc or vcu node (grep). So all nodes below come from
`arch/arm64/boot/dts/mediatek/mt6785.dts`.

### 1.2 DT nodes (vendor `mt6785.dts`)

| Node (line) | compatible | reg | IRQ | Notes |
|---|---|---|---|---|
| `vcu@16000000` (3441) | `mediatek-vcu` | `0x16000000+0x40000` "VDEC_BASE", `0x17020000+0x10000` "VENC_BASE", `0x19002000+0x1000` "VENC_LT" | none | `mboxes` GCE threads 16 and 17 (3452-3453); 16 `gce-event-names` (3455-3470) mapped to `CMDQ_EVENT_VDEC_EVENT_0..11` and the four VENC events (3472-3487); `iommus` port `HW_VDEC_MC_EXT` under `#ifdef CONFIG_MTK_IOMMU_V2` (3448-3450) |
| `vdec_gcon@16000000` (3490) | `mediatek,vdec_gcon`, `syscon` | `0x16000000` "VDEC_SYS", `0x16020000+0x400` "VDEC_VLD", `0x16021000` "VDEC_MC", `0x16023000` "VDEC_MV", `0x16025000` "VDEC_MISC" (3492-3496) | GIC_SPI 329 level-low (3501) | the decoder device the vendor driver probes; `mediatek,vcu = <&vcu>`; clocks `MT_SCP_SYS_DIS/VDE/VEN`, `MT_CG_SMI_COMMON`, `GALS_COMM0/1`, `MT_CG_VDEC`, `MT_CG_VENC` (3504-3521) |
| `vdec@16020000` (3530) | `mediatek,vdec` | `0x16020000+0x1000` | SPI 329 | |
| sub-block nodes (3536-3604) | `vld`, `vld_top`, `mc`, `avc_vld`, `avc_mv`, `vdec_pp`, `vdtop`, `vp6`, `vld2`, `avs_vld`, `vp8_vld`, `hevc_vld`, `vp9_vld`, `vdec_core0_vad` | `0x16020000`, `0x16020800`, `0x16021000`, `0x16022000`, `0x16023000`, `0x16024000`, `0x16025000`, `0x16026000`, `0x16026800`, `0x16027000`, `0x16027800`, `0x16028000`, `0x16028400`, `0x1602c000` | none | name-only nodes; no driver matches them (none of these compatibles appear in the vendor codec drivers read for this study) |
| `smi_larb2@16010000` (3606) | `mediatek,smi_larb2` | `0x16010000` | SPI 330 (3609) | clocks `SCP_SYS_VDE`, `VDEC_VDEC` |
| `venc_gcon@17000000` (3615) | `mediatek,venc_gcon`, `syscon` | `0x17000000`, `0x17020000` | SPI 270 (3623) | same clock list as vdec_gcon |
| `smi_larb3@17010000` (3647) | `mediatek,smi_larb3` | `0x17010000` | SPI 269 (3650) | clocks `SCP_SYS_VEN`, `VENC_GCON_VENC`, `VENC_GCON_JPGENC` |
| `venc@17020000` (3657) | `mediatek,venc` | `0x17020000+0x2000` | SPI 270 (3660) | |
| `venc_jpg@17030000` (3663) | `mediatek,venc_jpg` | `0x17030000+0x10000` | SPI 271 (3666) | JPEG encoder, clock `VENC_GCON_JPGENC` |
| `scp@10500000` (771) | `mediatek,scp` | SRAM `0x10500000+0xc0000` + three config windows | SPI 201 (778) | |
| `iommu0: m4u@10220000` (833) | `mediatek,iommu_v0` | `0x10220000` | SPI 187 | larbs 0-6 (837-839); under `#ifdef CONFIG_MTK_IOMMU_V2` (832) |
| `mmdvfs_pmqos` (3248) | — | — | — | VDEC clock steps 624/416/312 MHz, VENC 630/450/364 MHz (3274-3279); muxes `TOP_MUX_VENC`, `TOP_MUX_VDEC` (3292-3293) |

IOMMU ports (vendor `pseudo_m4u-larb*` nodes):

- larb2 = VDEC, 12 ports (904-920, comment "larb2-VDEC-12"): `MC`, `UFO`,
  `PP`, `PRED_RD`, `PRED_WR`, `PPWRAP`, `TILE`, `VLD`, `VLD2`, `AVC_MV`,
  `UFO_ENC`, `RG_CTRL_DMA`.
- larb3 = VENC + JPEG, 19 ports (922-945): VENC ports, `JPGENC_*`, and
  `JPGDEC_WDMA` and `JPGDEC_BSDMA`.

Inconsistencies in the vendor DT. None of them matters to the vendor
driver, but they must not be copied into mainline:

- `vdec_gcon` points `mediatek,larb` at `smi_larb1` (3500), and
  `venc_gcon` at `smi_larb4` (3622). VDEC actually sits on larb2 and
  VENC on larb3 (comments at 919 and 944). The vendor PM code ignores
  the phandle for power and hard-codes `SMI_LARB2`
  (`mt6785/mtk_vcodec_dec_pm.c`, `mtk_vcodec_dec_clock_on`).
- `venc_gcon` lists the VDEC IOMMU port `HW_VDEC_MC_EXT` (3620).
- The `vcu` "VENC_LT" window `0x19002000` (3447) falls inside the APU
  block on this SoC (mainline `apu_conn: clock-controller@19000000`,
  `mt6785.dtsi:2006`). It is probably stale (**unverified**).
- The legacy `mediatek,gce` node lists `vdec_base`, `vdec1_base` and
  similar entries (1656-1677) with addresses that do not match the
  decoder (`0x17010000` is larb3). They are GCE subsys table entries from
  an older chip, not the decoder's location.

### 1.3 Where the codec algorithm runs: the userspace VCU daemon

The kernel never programs decode registers. A userspace daemon does, and
the kernel only brokers. Evidence:

1. **The kernel never parses the bitstream.** For a decode,
   `vdec_decode` puts only buffer DMA addresses, dma-buf fds, size,
   length and flags into the shared `vsi` structure, then calls
   `vcu_dec_start(vcu, data, 3, bs, fb)`. It reads back
   `vdec_changed_info` and `error_map`
   (`drivers/media/platform/mtk-vcodec/vdec/vdec_common_if.c`, `vdec_decode`).
   There is no SPS, PPS or slice-header handling. The driver is
   **stateful**: it uses `V4L2_EVENT_SOURCE_CHANGE`, `V4L2_DEC_CMD_STOP`
   and no request API (`mtk_vcodec_dec.c`, `mtk_vdec_queue_res_chg_event`,
   `vidioc_decoder_cmd`).
2. **The daemon tells the kernel when to wait and lock.** The handler for
   daemon-to-kernel messages, `vcu_dec_ipi_handler`, accepts
   `VCU_IPIMSG_DEC_WAITISR` (the kernel waits for the decode-done IRQ for
   the daemon), `LOCK_CORE`/`UNLOCK_CORE`, `LOCK_LAT`/`UNLOCK_LAT`, and
   `GET_FRAME_BUFFER`/`PUT_FRAME_BUFFER`
   (`drivers/media/platform/mtk-vcodec/vdec_vcu_if.c`). Kernel-to-daemon
   messages are `AP_IPIMSG_DEC_INIT/START/END/DEINIT/RESET/QUERY_CAP/SET_PARAM`
   (same file).
3. **The daemon gets the registers.** In
   `drivers/media/platform/mtk-vcu/mtk_vcu.c`:
   - The probe function `mtk_vcu_probe` keeps the `reg` windows of the
     `vcu` node: the whole 256 KiB VDEC window, VENC, and VENC_LT.
   - `mtk_vcu_mmap` maps them uncached into the calling process, after
     `vcu_check_reg_base`.
   - The `VCU_GCE_SET_CMD_FLUSH` ioctl (`vcu_gce_cmd_flush` /
     `vcu_set_gce_cmd`) turns a userspace list of `CMD_WRITE`,
     `CMD_READ`, `CMD_POLL_REG`, `CMD_WAIT_EVENT`, `CMD_MEM_MV` and
     `CMD_POLL_ADDR` into a GCE (CMDQ) packet. It checks addresses
     against the same windows and submits the packet with
     `cmdq_pkt_flush_threaded`.
4. **The daemon is named.** `mtk_vcu.c` defines `VCU_PATH "/dev/vpud"`
   and identifies the daemon with `strcmp(current->comm, "vpud")`; it also
   knows `vdec_srv` and `venc_srv`. IPIs go through `vcu_ipi_send`, which
   wakes the daemon blocked in `VCU_GET_OBJECT`. On a timeout the kernel
   sends SIGTERM, then SIGKILL, to the daemon (same file).
5. **There is no firmware.** `vcu_load_firmware` only checks the device
   pointer and returns 0; `request_firmware` is never called
   (`mtk_vcu.c`).
6. **The SCP plays no part in video.** The MT6785 SCP IPI table lists
   WDT, logger, VOW, audio, sensor, CHRE, DVFS and similar IDs, but no
   VDEC or VENC ID (`drivers/misc/mediatek/scp/mt6785/scp_ipi.h:34-67`).
7. **The kernel touches very few registers.** The vendor MT6785 PM and
   IRQ code only:
   - reads the VDEC_SYS active bit and acks the decode-done IRQ at
     MISC+0xA4 (`mt6785/mtk_vcodec_intr.c`, `mtk_vcodec_dec_irq_handler`);
   - performs a "hw break" at clock-off (MISC+0x100/0x104, VLD+0x108
     soft reset);
   - reads debug registers (`mt6785/mtk_vcodec_dec_pm.c`,
     `mtk_vdec_hw_break` and dump helpers).

   Clock-on is `smi_bus_prepare_enable(SMI_LARB2)` plus
   `clk_prepare_enable(MT_CG_VDEC)`, with no register write (same file).

Conclusion for question 1: on MT6785 the codec algorithm runs in the
proprietary userspace daemon `vpud` and the libraries it loads. The
daemon drives the hardware either directly through mmap'd registers or
through GCE command lists. Neither the kernel nor the SCP does it. The
library names are not in any GPL file (**unverified**).

---

## 2. Decoder IP generation and codecs

### 2.1 Same family as MT8173/MT8183: a single-core VDEC with a MISC IRQ block

The interrupt and "active" protocol, the only part the kernel sees, is
identical to mainline:

| Constant | vendor `mt6785/mtk_vcodec_intr.h` | mainline |
|---|---|---|
| HW active bit in VDEC_SYS+0 | `MTK_VDEC_HW_ACTIVE 0x10` | `VDEC_HW_ACTIVE_MASK BIT(4)` (`decoder/mtk_vcodec_dec_hw.h:16`) |
| IRQ config register | `MTK_VDEC_IRQ_CFG_REG 0xA4` | `VDEC_IRQ_CFG_REG 0xa4` (`mtk_vcodec_dec_hw.h:19`) |
| IRQ cfg / clr bits | `0x11` / `0x10` | `0x11` / `0x10` (`mtk_vcodec_dec_hw.h:17-18`) |
| decode-done status | `0x10000` | `MTK_VDEC_IRQ_STATUS_DEC_SUCCESS 0x10000` (`decoder/mtk_vcodec_dec.h:25`) |
| VENC IRQ status / ack | `0x05C` / `0x060` | `0x05C` / `0x060` (`encoder/mtk_vcodec_enc.h:23-24`) |

The multimedia address map matches MT8183 block for block:

| Block | MT6785 vendor | MT8183 mainline |
|---|---|---|
| vdecsys | `0x16000000` (`mt6785.dts:3492`) | `0x16000000` (`mt8183.dtsi:2183`) |
| VDEC larb | `0x16010000` (3606) | `0x16010000` (`mt8183.dtsi:2219`) |
| decoder | `0x16020000`... `0x16028400` (3530-3599) | `0x16020000`... `0x16028400`, 11 ranges (`mt8183.dtsi:2190-2201`) |
| vencsys, VENC larb, venc, jpgenc | `0x17000000`, `0x17010000`, `0x17020000`, `0x17030000` (3615-3663) | same addresses (`mt8183.dtsi:2228-2270`) |
| SCP | `0x10500000` (771) | `0x10500000` (`mt8183.dtsi:1036`) |

### 2.2 But newer than MT8183, and not the MT8192 LAT/CORE split

The evidence below points to a revision between the two
(**unverified** as an exact IP version).

- **Not the MT8192 LAT/CORE split.**
  - MT6785 has one VDEC power domain (`mt6785-pm-domains.h:218-230`)
    and one VDEC larb (larb2).
  - MT8192 has a `mediatek,mtk-vcodec-lat` subdevice and a
    `mediatek,mtk-vcodec-core` subdevice with separate IRQs and power
    domains `VDEC` and `VDEC2`, two larbs (`L4_*`, `L5_*`) and a
    `vdecsys_soc` clock controller (`mt8192.dtsi:1699-1769`,
    `mt8192-larb-port.h:56-76`).
  - The vendor MT6785 PM code handles only `MTK_VDEC_CORE` and rejects
    any other `hw_id` (`mt6785/mtk_vcodec_dec_pm.c`).
- **Newer than MT8183.** The MT6785 VDEC larb has 12 ports, including
  `UFO`, `TILE`, `VLD2`, `UFO_ENC` and `RG_CTRL_DMA`
  (`mediatek,mt6785-memory-port.h:36-47`). MT8183 has 7
  (`mt8183-larb-port.h:33-39`). The MT6785 set is the MT8192 core larb
  set plus `UFO_ENC` (`mt8192-larb-port.h:56-66, 76`). This points to
  UFO frame compression and a newer decoder revision.
- MT6785 shares other IP with MT6779: in mainline, smi-common and GCE
  use `mt6779` fallbacks (`mt6785.dtsi:1096, 1917-1918`). Mainline has no
  vcodec support for MT6779 either.

### 2.3 Codecs

- **Bitstream decoders in the DT names:** `avc_vld` (H.264), `hevc_vld`
  (H.265), `vp9_vld`, `vp8_vld`, `vp6`, `avs_vld` (AVS), and
  `vld`/`vld2` (generic VLD, probably the MPEG-1/2/4, H.263 and VC-1
  path, **unverified**) (`mt6785.dts:3536-3599`). No AV1 block is named.
- **Formats the vendor kernel will pass through:** H.264, H.265, HEIF,
  MPEG-1/2/4, H.263, VP8, VP9, WMV1/2/3, WVC1, WMVA, RV30, RV40 and AV1
  all go to `get_dec_common_if()` (`vdec_drv_if.c`, `vdec_if_init`).
  This switch is shared by every SoC.
- **The real list comes from `vpud` at runtime.** The table
  `mtk_video_formats[]` starts zeroed. `get_supported_format()` fills it
  through `GET_PARAM_CAPABILITY_SUPPORTED_FORMATS` (`mtk_vcodec_dec.c`).
  The capture (decoded) pixel formats also come from `vpud`. The MT6785
  codec list and output format are therefore **unverified** from the
  code. They are probably MediaTek block or compressed formats, like
  `MT21C` and `MM21` in mainline.
- **Encoder:** one `venc@17020000`. The codec list also comes from
  `vpud` (`venc_common_if`). It is **unverified**.

---

## 3. What mainline `mtk-vcodec` would need for MT6785

### 3.1 Already in `src/mt6785-mainline`

| Piece | Where |
|---|---|
| VDEC / VENC power domains with bus protection | `drivers/pmdomain/mediatek/mt6785-pm-domains.h:218-243`; DT `mt6785.dtsi:1017-1033`; IDs 12 and 13 in `include/dt-bindings/power/mediatek,mt6785-power.h:18-19` |
| vdecsys / vencsys gate clocks | `drivers/clk/mediatek/clk-mt6785-vdec.c` (`vdec_main`, `vdec_larb1`, same registers as vendor `clk-mt6785.c:2851-2909`), `clk-mt6785-venc.c` (`venc_larb`, `venc_main`, `venc_jpgenc`, `venc_gals`, same bits as vendor `clk-mt6785.c:2937-2955`); DT `mt6785.dtsi:1974-1994` |
| `top_vdec` / `top_venc` muxes | `drivers/clk/mediatek/clk-mt6785-top.c:540-541` |
| SMI larb2 (VDEC) and larb3 (VENC) nodes | `mt6785.dtsi:1980-2004`; larb data `drivers/memory/mtk-smi.c:286-297, 517-521, 574` |
| IOMMU with the VDEC/VENC ports | `mt6785.dtsi:1086-1093` (larbs 0, 1, 2, 3, 5, 6); `drivers/iommu/mtk_iommu.c:1593-1604, 1919`; ports `include/dt-bindings/memory/mediatek,mt6785-memory-port.h:36-67` |
| GCE mailbox and VDEC/VENC event IDs | `mt6785.dtsi:1095-1102`; `drivers/mailbox/mtk-cmdq-mailbox.c:851` (mt6779 data); `include/dt-bindings/gce/mediatek,mt6785-gce.h:164-168, 191-206` |
| Kernel config for the bus side | `CONFIG_MTK_IOMMU=y`, `CONFIG_MTK_SMI=y`, `CONFIG_MTK_CMDQ=y`, `CONFIG_MTK_CMDQ_MBOX=y` (`kernel/configs/pmos-mt6785.config:6228, 6386, 6292, 6200`) |

So power, clocks, SMI, IOMMU and GCE, everything *around* the decoder,
is present.

### 3.2 Missing

1. **A decoder and encoder DT node and compatible.**
   - `mtk_vcodec_dec_get_chip_name` only knows mt8173, 8183, 8192, 8195,
     8186 and 8188; any other chip fails probe with `-EINVAL`
     (`decoder/mtk_vcodec_dec_drv.c:334-373`). The match table
     (`:540-561`) and the binding enum
     (`Documentation/devicetree/bindings/media/mediatek,vcodec-decoder.yaml`)
     would need an `mt6785` entry.
   - The kernel-side register needs are small: VDEC_SYS through the
     `mediatek,vdecsys` syscon (`mt6785.dtsi:1974`), and the MISC block
     with the IRQ register at +0xA4 (`mtk_vcodec_dec_drv.c:42-81`).
   - On MT8183 "misc" is `0x16020000` (`mt8183.dtsi:2191`), and the
     vendor MT6785 node maps `0x16020000` as its second range
     (`mt6785.dts:3493`, commented "VDEC_VLD"). That this is the same
     MISC block is likely but **unverified**.
   - IRQ: GIC_SPI 329, level low (`mt6785.dts:3501`).
2. **A firmware backend. This is the real gap.**
   - Mainline knows two transports: `enum mtk_vcodec_fw_type { VPU, SCP }`
     (`common/mtk_vcodec_fw.h:14-17`), chosen by a `mediatek,vpu` or
     `mediatek,scp` phandle; anything else returns `-ENODEV`
     (`decoder/mtk_vcodec_dec_drv.c:376-385`).
   - `VPU` is the MT8173 video processor only (`vpu/mtk_vpu.c:952`
     `mediatek,mt8173-vpu`).
   - `SCP` needs the remoteproc driver, which has no MT6785 entry
     (`drivers/remoteproc/mtk_scp.c:1584-1590`). It loads
     `mediatek/<soc>/scp.img` (`mtk_scp.c:1120-1156`), and that image
     must implement the vcodec IPIs (`SCP_IPI_VDEC_H264`... in
     `include/linux/remoteproc/mtk_scp.h:31-45`). MediaTek never shipped
     such an image for MT6785: the vendor SCP has no video IPI
     (section 1.3, item 6).
   - `CONFIG_MTK_SCP` is not set (`pmos-mt6785.config:6236`).
     `VIDEO_MEDIATEK_VCODEC` depends on `VIDEO_MEDIATEK_VPU || MTK_SCP`
     (`vcodec/Kconfig:14`).
   - The SCP itself is loaded by LK with vendor firmware (board DT
     comment, `mt6785-lenovo-yt-j706f.dts:52-56, 71-74`).
3. **A VCU transport, for a route through the vendor daemon.** It would
   be a third `mtk_vcodec_fw_ops` implementation
   (`common/mtk_vcodec_fw_priv.h:19-30`: `load_firmware`, `ipi_register`,
   `ipi_send`, `map_dm_addr`, `get_vdec_capa`) on top of a port of
   `mtk-vcu`. The IPI payloads would also have to follow the vendor
   protocol (`vdec_vcu_if.c` message set), not the mainline one, so in
   practice the vendor `vdec_common_if`/`venc_common_if` glue would have
   to come along. Vendor-only kernel APIs to replace:
   - `mtk_vcu.c` calls `cmdq_register_device`, `cmdq_mbox_create`,
     `cmdq_dev_get_event`, `cmdq_pkt_flush_threaded`,
     `cmdq_pkt_poll_timeout`, `cmdq_pkt_read_addr` and the
     `cmdq_sec_*` functions.
   - Mainline has the packet builders `cmdq_pkt_write`, `cmdq_pkt_read_s`,
     `cmdq_pkt_poll(_addr)`, `cmdq_pkt_mem_move` and `cmdq_pkt_wfe`
     (`drivers/soc/mediatek/mtk-cmdq-helper.c:218-484`), but not the
     threaded flush or event-by-name lookup.
   - `smi_bus_prepare_enable` (`mt6785/mtk_vcodec_dec_pm.c`) and the
     vendor IOMMU fault callbacks have no mainline equivalent. Mainline
     uses larb runtime-PM and power domains instead.
   - `mtk_vcodec_mem.c` (the `VCU_MVA_ALLOCATION`/`VCU_PA_ALLOCATION`
     backing) would move to the DMA API on the mainline IOMMU.
   - The userspace ABI (`uapi/linux/mtk_vcu_controls.h`, ioctl numbers
     and struct layouts) must match the `vpud` binary exactly.
4. **Not needed but not present:** VDEC DVFS. The vendor runs VDEC at up
   to 624 MHz (`mt6785.dts:3277`). The mainline driver does no DVFS, and
   the boot rate of `top_vdec` is **unverified**.

---

## 4. Verdict

**Not feasible without proprietary userspace.** On MT6785 the decode
"brain" is the vendor `vpud` daemon and its libraries (section 1.3). No
GPL file contains the register programming, there is no SCP or VPU video
firmware for this SoC, and mainline's two transports therefore have
nothing to talk to. Everything else in the path is already in the
7.1 tree (section 3.1).

With the vendor blobs, it becomes *feasible with a named amount of
work*. The route:

1. Port `mtk-vcu` (`mtk_vcu.c` is about 75 KB, `mtk_vcodec_mem.c` about
   13 KB) to 7.1.
2. Add a VCU backend plus the vendor common decode/encode glue to
   mainline `mtk-vcodec`.
3. Add the MT6785 DT nodes.
4. Run the vendor `vpud` in an Android chroot, as `src/begonia-ftp` does
   for `mnld` and the modem daemons (`src/begonia-ftp/README.md`, GPS
   and modem rows).

Estimate (a judgement, not a measurement): 4 to 8 weeks of kernel work,
assuming `vpud` starts in the chroot. The blobs could not ship in a
public image.

A blob-free driver would need the VDEC register interface
reverse-engineered from `vpud`. That is months of work at best, and out
of proportion to the gain.

### Three biggest blockers

1. **Register programming lives only in the proprietary `vpud`
   libraries.** The kernel only acks IRQs and does a reset at clock-off
   (`mt6785/mtk_vcodec_intr.c`, `mt6785/mtk_vcodec_dec_pm.c`). The
   daemon gets the full VDEC window by mmap or GCE (`mtk_vcu.c`
   `mtk_vcu_mmap`, `vcu_gce_cmd_flush`).
2. **No firmware transport fits.**
   - Mainline `mtk-vcodec` speaks only VPU (MT8173) or SCP (MT8183+).
   - The MT6785 SCP runs sensor, audio and VOW firmware with no video
     IPI (`scp/mt6785/scp_ipi.h:34-67`).
   - There is no `mt6785` SCP remoteproc data (`mtk_scp.c:1584-1590`).
   - MT8183's `scp.img` targets a different decoder revision (7 larb
     ports against 12, section 2.2). It would also replace the vendor
     SCP firmware that LK loads. Running it is **unverified** and
     unlikely.
3. **The blob route means reproducing a 4.14 vendor ABI on 7.1:**
   - `/dev/vcu` ioctls and their structs (`mtk_vcu.c`
     `mtk_vcu_unlocked_ioctl`);
   - the vendor CMDQ and SMI APIs (section 3.2, item 3);
   - possibly ION, since the vendor kernel has `CONFIG_ION=y`
     (`yoga11_defconfig:397`), while the project kernel has no
     dma-buf heaps (`pmos-mt6785.config:5855`). Whether `vpud` opens
     `/dev/ion` is **unverified**.
   - Decoded frames would likely be in MediaTek block formats needing a
     conversion step (section 2.3, **unverified**).

### Cheapest experiment

This one needs no kernel work, about 30 minutes on the stock Android
slot. It needs root there, and whether that is available is
**unverified**. While a video plays:

1. `pidof vpud` and `ls -l /dev/vcu*`: the daemon and node named in
   `mtk_vcu.c` exist.
2. `grep -i vcu /proc/$(pidof vpud)/maps`: shows the register windows
   mapped through `mtk_vcu_mmap`.
3. `strace -f -e trace=ioctl,openat -p $(pidof vpud)`: shows a stream of
   `VCU_GCE_SET_CMD_FLUSH` and `VCU_SET_OBJECT`/`VCU_GET_OBJECT` ioctls
   per frame, plus every other device node the daemon opens (for example
   `/dev/ion`), which sizes blocker 3.
4. `cat /vendor/etc/media_codecs*.xml`: gives the actual hardware codec
   list for section 2.3. This step does not need root.

If `vpud` maps the VDEC window and issues GCE flushes per frame, the
verdict is confirmed: the algorithm is in userspace and no SCP/VPU
firmware route exists. If decoding happens with no such activity, the
verdict is refuted and the SCP should be re-examined.

The next step, for the blob route only, is to start the vendor `vpud`
under `strace` in a Linux-side Android chroot. Its failing `open`s and
`ioctl`s give the exact kernel interface to port.

---

## 5. Software fallback today

Today the tablet decodes on the CPU, with no hardware help:

- 6 Cortex-A55 cores (`mt6785.dtsi:368-484`, OPP 500 MHz to 2.0 GHz,
  table at `:124-224`) and 2 Cortex-A76 cores (`:500-528`, OPP 774 MHz
  to 2.05 GHz, table at `:225-330`).

Kernel pieces that help, or could help, without any codec firmware:

| Piece | State | Value for video |
|---|---|---|
| cpufreq + EAS capacity data | `CONFIG_ARM_MEDIATEK_CPUFREQ=y`, `CPUFREQ_DT=y` (`pmos-mt6785.config:649-653`); `capacity-dmips-mhz` 284 on A55 against 1024 on A76 (`mt6785.dtsi:376, 508`) | Lets the scheduler put the heavy decode threads on the two A76 cores. The main lever for software decode. |
| Mali-G76 GPU (panfrost) | `mediatek,mt6785-mali` in `drivers/gpu/drm/panfrost/panfrost_drv.c:1097, 1182`; node `mt6785.dtsi:1528-1543`; enabled on the board (`mt6785-lenovo-yt-j706f.dts:260-262`); `CONFIG_DRM_PANFROST=m` (`pmos-mt6785.config:4509`) | YUV-to-RGB conversion and scaling in shaders (for example a GL video output), taking that load off the CPU. Decoding stays on the CPU. |
| Display OVL/RDMA YUV input | `DRM_FORMAT_UYVY`/`YUYV` in `drivers/gpu/drm/mediatek/mtk_disp_ovl.c:115-116, 139-140` and `mtk_disp_rdma.c:67-68` | Packed YUV 4:2:2 can be scanned out with hardware colour conversion on a plane. There is no NV12/I420 in those lists, and whether OVL can scale is **unverified**, so the value is limited. |
| JPEG **encoder** (`mtk-jpgenc`) | Hardware present: `venc_jpg@17030000`, SPI 271 (`mt6785.dts:3663-3671`). The vendor register layout (`drivers/misc/mediatek/jpeg/v2/jpeg_drv_reg.h:55-92`, `RSTB 0x100` ... `ULTRA_THRES 0x318`) matches mainline `jpeg/mtk_jpeg_enc_hw.h:48-70`. Mainline needs a DT node with `mediatek,mtk-jpgenc` (`jpeg/mtk_jpeg_core.c:1937`; binding enum `mediatek-jpeg-encoder.yaml:18-23`), clock `CLK_VENC_JPGENC`, the `VENC` power domain and the `M4U_PORT_JPGENC_*` ports. `CONFIG_VIDEO_MEDIATEK_JPEG` is not set (`pmos-mt6785.config:3966`). | Small task, no firmware. Helps camera stills and MJPEG encoding, not playback. |
| JPEG **decoder** | The vendor builds no JPEG decoder for MT6785: `JPEG_DEC_DRIVER` is set only for MT6757, MT6799 and MT8173, while the MT6785 block sets only SMI/QoS flags (`jpeg/v2/Makefile`, the `CONFIG_MACH_MT6785` block). There is no `jpgdec` DT node, although larb3 has `JPGDEC_*` ports (`mt6785.dts:936-937`). | Hardware presence **unverified**. Not usable. |
| MDP (scaling, CSC, rotation) | Vendor MDP nodes at `0x1400xxxx` (`mt6785.dts:3169-3356`). Mainline `mtk-mdp` is MT8173-only and VPU-based (`mdp/mtk_mdp_core.c:33-49`). `mtk-mdp3` needs SCP firmware (`mdp3/mtk-mdp3-vpu.c:129-141` `scp_ipi_register(SCP_IPI_MDP_*)`; `mdp3/mdp_cfg_data.c:170`). There are no MDP nodes in `mt6785.dtsi`. | Not usable: the same firmware gap as the decoder. |
| dma-buf heaps | `# CONFIG_DMABUF_HEAPS is not set` (`pmos-mt6785.config:5855`) | Not needed for CPU decode. Only relevant to a future zero-copy hardware path. |

In short, for playback today the useful kernel pieces are cpufreq and
scheduling on the A76 pair, and panfrost for conversion and scaling. The
only codec hardware that mainline can drive without firmware is the
JPEG encoder.
