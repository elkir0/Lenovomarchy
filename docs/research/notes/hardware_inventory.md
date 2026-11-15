# Hardware inventory of the Lenovo Yoga Tab 11 (YT-J706F / YT-J706X), with the Linux driver for each part

Research date: 2026-11-15. Researcher notes for the Omarchy-port feasibility study.

**How the strongest evidence was obtained (read this first).** No public firmware dump, kernel source, FCC internal photos or teardown naming chips was found for this tablet. The best primary evidence is a TWRP device tree for the YT-J706F published on GitHub by jeremywildsmith ([repo](https://github.com/jeremywildsmith/android_device_lenovo_yoga11), created and last pushed 2024-12-10, 0 stars, generated with SebaUbuntu's twrpdtgen). It contains the **stock boot image's kernel and DTB** ([prebuilt/kernel](https://github.com/jeremywildsmith/android_device_lenovo_yoga11/blob/HEAD/prebuilt/kernel), [prebuilt/dtb.img](https://github.com/jeremywildsmith/android_device_lenovo_yoga11/blob/HEAD/prebuilt/dtb.img)). For these notes:
- the DTB (an Android DT table holding one 139 089-byte DTB) was decompiled with `dtc` (5 802 lines, `model = "MT6785"`);
- the kernel (gzip, 28.6 MB unpacked) was read with `strings` only, never executed. Its banner is `Linux version 4.14.186-g59da9ac88f6c ... clang version 11.0.1 ... #1 SMP PREEMPT Wed Sep 18 18:30:11 CST 2024`.

Three caveats apply to everything tagged **[stock DTB]** or **[stock kernel]** below:
1. The provenance is a third-party repo, not checked against a Lenovo firmware hash.
2. The DTB in the boot image is the **SoC-level** DTB. Board-level nodes (the real touch, panel, amplifier and sensor nodes) live in the separate `dtbo` partition, which is **not** in the repo. The DTB only has empty placeholders (`touch`, `smart_pa`, `tcpc_pd`).
3. The MediaTek 4.14 kernel builds in every driver the ODM enabled. A driver name in the kernel proves that the firmware supports the part, **not** that every unit carries it. Several parts clearly have second sources (two panel/touch variants, two camera sensors, three SAR sensors).

Mainline status was checked against `torvalds/linux` master through the GitHub API on 2026-11-15 ("mainline: yes" means that the driver file exists there).

## SoC, CPU, GPU, RAM and storage

### Takeaway
The YT-J706F is a MediaTek MT6785 (Helio G90T) platform: 2x Cortex-A76 at 2.05 GHz, 6x Cortex-A55 at 2.0 GHz, Mali-G76 MC4, 4 or 8 GB LPDDR4X, and 64/128/256 GB UFS 2.1. The MT6785 SoC is **not in mainline Linux**. A community "mt6785-mainline" tree (kernel 6.16) supports the SoC basics and is in active use as of November 2026.

### Cited Findings
- **Lenovo's SoC string:** the PSREF lists the processor as "MediaTek Helio G90T (M8185 for WiFi model; G90T MT8789 for LTE model only)", octa-core 2x A76 + 6x A55, A76@2.05GHz / A55@2.0GHz, with an ARM Mali-G76 MC4 GPU (page last modified 2023-05-26) — [Lenovo PSREF Yoga Tab 11](https://psref.lenovo.com/syspool/Sys/PDF/Lenovo_Tablets/Yoga_Tab_11/Yoga_Tab_11_Spec.html)
- **Firmware platform:** the YT-J706F build uses `TARGET_BOARD_PLATFORM := mt6785`, the boot-control HAL `bootctrl.mt6785` and the kernel cmdline `bootopt=64S3,32N2,64N2 buildvariant=user`. The boot image is header v2: base 0x40078000, page size 2048, ramdisk offset 0x07c08000, tags offset 0x0bc08000 — [BoardConfig.mk](https://github.com/jeremywildsmith/android_device_lenovo_yoga11/blob/HEAD/BoardConfig.mk), [device.mk](https://github.com/jeremywildsmith/android_device_lenovo_yoga11/blob/HEAD/device.mk)
- **Both platform names in the ramdisk:** the recovery ramdisk contains both `init.recovery.mt6785.rc` and `init.recovery.mt8185.rc` — [repo tree](https://github.com/jeremywildsmith/android_device_lenovo_yoga11/tree/HEAD/recovery/root)
- **[stock DTB] CPU and GPU nodes:**
  - `model = "MT6785"`, `compatible = "mediatek,MT6785"`.
  - cpu0-5 are `arm,cortex-a55` and cpu6-7 are `arm,cortex-a75` (the vendor DT labels the A76 cores "a75").
  - GPU: `mali@13040000` with `"mediatek,mali", "arm,mali-midgard", "arm,mali-bifrost"`, plus a separate `mediatek,mt6785-gpufreq` node — [dtb.img](https://github.com/jeremywildsmith/android_device_lenovo_yoga11/blob/HEAD/prebuilt/dtb.img)
- **Memory and storage:** 4 GB or 8 GB soldered LPDDR4x; 64/128/256 GB UFS 2.1 on the system board; microSD up to 1 TB exFAT. No storage vendor is stated — [Lenovo PSREF](https://psref.lenovo.com/syspool/Sys/PDF/Lenovo_Tablets/Yoga_Tab_11/Yoga_Tab_11_Spec.html)
- **Mainboard FRUs by memory configuration:** 5B28C18879 "YT-J706F MB_4+64G", 5B28C18880 "MB_4+128G" and 5B28C18881 "MB_8+256G"; plus a separate SUB board, 5P68C18883 — [IPC Computer 5B28C18879](https://www.ipc-computer.eu/laptop-spare-parts/mainboards/mainboard-5b28c18879-145210232), [IPC 5B28C18881](https://www.ipc-computer.eu/laptop-spare-parts/mainboards/mainboard-5b28c18881-145210234), [IPC SUB board](https://www.ipc-computer.eu/laptop-spare-parts/pcb-boards/pcb-5p68c18883-101798356)
- **[stock DTB] UFS:** controller `mediatek,ufshci` at 0x11270000 with `lanes-per-direction = <1>`, plus `mediatek,ufs_mphy` — [dtb.img](https://github.com/jeremywildsmith/android_device_lenovo_yoga11/blob/HEAD/prebuilt/dtb.img)
- **UFS boot layout:** the init script symlinks `/dev/block/sda`/`sdb` (UFS boot LUs) as `preloader_a`/`preloader_b` — [init.recovery.mt6785.rc](https://github.com/jeremywildsmith/android_device_lenovo_yoga11/blob/HEAD/recovery/root/init.recovery.mt6785.rc)
- **Partition layout:**
  - A/B slots for system, vendor, product (dynamic group `lenovo_dynamic_partitions`, ~9.1 GB), boot, vbmeta_system and vbmeta_vendor; recovery-as-boot.
  - MediaTek firmware partitions: lk/lk2, tee1/2, gz1/2, scp1/2, sspm_1/2, spmfw, md1img, md1dsp, cam_vpu1-3, dtbo, nvram, nvdata, protect1/2, lenovocust.
  - [recovery.fstab](https://github.com/jeremywildsmith/android_device_lenovo_yoga11/blob/HEAD/recovery.fstab)
- **[stock DTB] microSD:** `mmc@11230000`, `compatible = "mediatek,mt8183-mmc"`, status okay, 4-bit, 200 MHz max, SDR104, `no-mmc; no-sdio`, card detect on GPIO 8 — [dtb.img](https://github.com/jeremywildsmith/android_device_lenovo_yoga11/blob/HEAD/prebuilt/dtb.img)
- **Mainline has no MT6785 support:** `torvalds/linux` has no `arch/arm64/boot/dts/mediatek/mt6785*`, no `pinctrl-mt6785.c` and no `clk-mt6785*`, and no MT6785/MT8185/MT8789 DTS files — [torvalds/linux dts/mediatek](https://github.com/torvalds/linux/tree/master/arch/arm64/boot/dts/mediatek)
- **Community MT6785 tree (`external-mirrors/mt6785-mainline-linux`, default branch `6.16`):**
  - Files: `mt6785.dtsi`, `mt6785-xiaomi-begonia.dts`, `clk-mt6785-{apmixed,apu,aud,cam,img,infra,mcu,mfg,mm,top,vdec,venc}.c`, `pinctrl-mt6785.c`, `mt6785-pm-domains.h`, `mt6785-mmsys.h`.
  - The dtsi compatibles cover: UFS (`mediatek,mt6785-ufshci`/`-ufsphy`), MMC, xHCI/MTU3/T-PHY, I2C, SPI, PWRAP, SCPSYS, IOMMU, the display pipeline (OVL, RDMA, DSI, PWM, mutex) and `mediatek,mt6785-mali`.
  - Latest commits are by Dinolek, July-August 2025 ("Enable GPU", "Enable USB controller", "Enable sub PMIC", "Enable touchscreen", DSI/OVL fixes); the mirror was last pushed 2026-06-19.
  - [external-mirrors/mt6785-mainline-linux](https://github.com/external-mirrors/mt6785-mainline-linux)
- **Upstream of that mirror:** the begonia port names `gitlab.postmarketos.org/mt6785-mainline/linux` (tag `6.16.4-r0`) and the pmaports package `linux-postmarketos-mediatek-mt6785` — [PostmarketOS-begonia README](https://github.com/F-to-pay/PostmarketOS-begonia)
- **GPU in mainline:** Panfrost lists `GPU_MODEL(g76, 0x7001)`, but its MediaTek compatibles are only mt8183, mt8183b, mt8186, mt8188, mt8192 and mt8370 (no mt6785) — [panfrost_gpu.c](https://github.com/torvalds/linux/blob/master/drivers/gpu/drm/panfrost/panfrost_gpu.c), [panfrost_drv.c](https://github.com/torvalds/linux/blob/master/drivers/gpu/drm/panfrost/panfrost_drv.c)
- **Mainline host drivers that do exist:** `mtk-sd.c` (MMC/SD), `ufs-mediatek.c`, `mtu3_plat.c` (USB device/DRD) and `mtk-pmic-wrap.c` — [torvalds/linux](https://github.com/torvalds/linux)

### Inferences
- **The "M8185" vs "MT8789" labels** probably mark Lenovo's tablet SKUs of the same MT6785 die: a modem-less "MT8185" for Wi-Fi, an MT8789 with modem for LTE. The ramdisk ships both mt6785 and mt8185 init files, so `ro.hardware` on a Wi-Fi unit may read `mt8185`. The kernel and DTB still say MT6785, so the mainline target is the MT6785 dtsi.
- **Porting base:** the community mt6785-mainline tree (clk, pinctrl, pm-domains, display, GPU, UFS, USB, MMC) is the realistic base. A YT-J706F board DTS would be a sibling of `mt6785-xiaomi-begonia.dts`. Because UFS is in that tree, a root filesystem on internal storage is plausible from day one.
- **GPU:** Panfrost already knows the G76 core, so on the community tree GPU acceleration is mostly a DT/compatible matter (begonia already has an "Enable GPU" commit). Upstreaming would need an `mediatek,mt6785-mali` entry.
- **UFS lanes:** the vendor DT says `lanes-per-direction = <1>`, so UFS runs on one lane on this board. That is a performance detail, not a blocker.

### Gaps
- No Lenovo GPL kernel source for the YT-J706F was found. The Lenovo support pages mention an open-source link that could not be opened.
- **RAM die vendor and UFS vendor:** unknown. Check with `adb shell cat /sys/block/sda/device/vendor /sys/block/sda/device/model` and `adb shell cat /proc/meminfo`. For the DRAM vendor, `adb shell su -c 'dmesg | grep -iE "dram|emi|lpddr"'` (root) or the preloader log in `expdb`.
- **Platform string on a real unit:** run `adb shell getprop ro.board.platform; getprop ro.hardware; getprop ro.vendor.mediatek.platform; cat /proc/cpuinfo`, and `cat /sys/devices/system/cpu/cpu{0,6}/cpufreq/cpuinfo_max_freq` for the real clock ceilings (the DTB `clock-frequency` values of 1.701 GHz and 2.171 GHz are vendor placeholders).
- **Mainline vs community tree:** whether anyone has posted MT6785 support to lore.kernel.org could not be confirmed. Searches found no thread, and the postmarketOS wiki page for MT6785 was behind bot protection.

## Display, touchscreen, backlight and stylus

### Takeaway
The panel is an 11" 2000x1200 60 Hz IPS BOE panel driven by a TDDI chip. The stock kernel carries two variants: **Novatek NT36523W** (LCM driver `nt36523w_fhdp_dsi_vdo_boe`) and **Himax HX83102P** (`hx83102p_fhdp_dsi_vdo_boe`, touch reported as HX83102E). Both touch controllers are on **SPI**. The pen uses Lenovo's **WGP** active-pen protocol and is read through the Novatek touch IC (`novatek,wgp-stylus`).

For mainline: the NT36523W-on-BOE panel has a close relative (`lenovo,j606f-boe-nt36523w`, same size, resolution and lane count). There is no mainline SPI touch driver for either IC, and no mainline driver for the backlight chips (KTZ8864A, SGM37604A) or the OCP2138 bias chip.

### Cited Findings
- **Panel spec:** 11" 2K (2000x1200), IPS, 400 nits, 15:9, 1500:1, 70% NTSC, 213 PPI, 60 Hz, 10-point capacitive multi-touch. Pen: "Lenovo Precision Pen 2 ... 4096 pressure levels, tilt detection, WGP protocol", sold separately — [Lenovo PSREF](https://psref.lenovo.com/syspool/Sys/PDF/Lenovo_Tablets/Yoga_Tab_11/Yoga_Tab_11_Spec.html)
- **Display FRU:** "Lenovo 5D18C18878 YT-J706 TP LCM Assy" (5079AA000154), a touch-panel + LCD module — [IPC Computer](https://www.ipc-computer.eu/laptop-spare-parts/displayunits/displayunit-5d18c18878-101794109)
- **[stock kernel] Panel drivers:** two MediaTek legacy LCM drivers, `drivers/misc/mediatek/lcm/nt36523w_fhdp_dsi_vdo_boe/` and `drivers/misc/mediatek/lcm/hx83102p_fhdp_dsi_vdo_boe/`; both are DSI video mode on BOE glass. The DT compatibles `nt,nt36523w` and `hx,hx83102p` are present. LK hands over the panel choice through `atag,videolfb-lcmname` — [kernel](https://github.com/jeremywildsmith/android_device_lenovo_yoga11/blob/HEAD/prebuilt/kernel)
- **[stock kernel] Touch IC identity:** the touch driver logs "TP info: [Vendor]novatek [IC]nt36523w P530" and "TP info: [Vendor]P530 himax [IC]hx83102e"; the display code logs "It is P530 NVT IC, do tp resume" and "It is P530 himax IC, do tp suspend" — [kernel](https://github.com/jeremywildsmith/android_device_lenovo_yoga11/blob/HEAD/prebuilt/kernel)
- **[stock kernel] Novatek touch driver:**
  - SPI: `novatek,NVT-ts-spi`, `NVTSPI`.
  - DT properties: `novatek,irq-gpio`, `novatek,pen-support`, `novatek,wgp-stylus`, `novatek,spi-rd-fast-addr`, `novatek,swrst-n8-addr`, `novatek,mp-support-dt`.
  - Firmware: `novatek_ts_fw.bin`, `novatek_ts_mp.bin`.
  - [kernel](https://github.com/jeremywildsmith/android_device_lenovo_yoga11/blob/HEAD/prebuilt/kernel)
- **[stock kernel] Himax touch driver:**
  - SPI: "Himax_ts SPI Touchscreen Driver", `himax-spi`, `himax_common_probe_spi`.
  - Firmware: `Himax_firmware.bin`, `Himax_mpfw.bin`.
  - The same build also knows HX83102A/B/D/E.
  - [kernel](https://github.com/jeremywildsmith/android_device_lenovo_yoga11/blob/HEAD/prebuilt/kernel)
- **[stock kernel] Backlight and bias:** I2C drivers for **KTZ8864A** ("[KERNEL/LCM][KTZ8864A] Success to register ktz8864a i2c driver"), **SGM37604A** and **OCP2138**. GPIO names `GPIO_LCD_BIAS_ENP`/`GPIO_LCD_BIAS_ENN` and `LCM_RST` appear too — [kernel](https://github.com/jeremywildsmith/android_device_lenovo_yoga11/blob/HEAD/prebuilt/kernel)
- **[stock DTB] Display hardware:** `mediatek,dsi0`, `mediatek,dsi1`, `mediatek,dsi_split`, `mediatek,mipi_tx0`/`tx1`, `mediatek,disp_pwm0` and `mediatek,dpi0`/`dpi1`. There is no DisplayPort or HDMI transmitter node — [dtb.img](https://github.com/jeremywildsmith/android_device_lenovo_yoga11/blob/HEAD/prebuilt/dtb.img)
- **Mainline NT36523 panel driver:** `panel-novatek-nt36523.c` supports `lenovo,j606f-boe-nt36523w` (the Lenovo Tab P11 J606F on SM6115): 1200x2000 at 60 Hz, 4 DSI lanes, single DSI, 143x235 mm. It also covers `xiaomi,elish-boe-nt36523` and `xiaomi,elish-csot-nt36523` (dual DSI) — [panel-novatek-nt36523.c](https://github.com/torvalds/linux/blob/master/drivers/gpu/drm/panel/panel-novatek-nt36523.c); patch thread [lkml 2023-04](https://lkml.iu.edu/hypermail/linux/kernel/2304.1/04951.html)
- **Mainline HX83102 panel driver:** `panel-himax-hx83102.c` supports `boe,nv110wum-l60`, `csot,pna957qt1-1`, `ivo,t109nw41`, `kingdisplay,kd110n11-51ie`, `starry,2082109qfh040022-50e`, `starry,himax83102-j02`, `holitech,htf065h045` and `waveshare,12.3-dsi-touch-a`. None of them is the Lenovo HX83102P panel — [panel-himax-hx83102.c](https://github.com/torvalds/linux/blob/master/drivers/gpu/drm/panel/panel-himax-hx83102.c)
- **Mainline Novatek touch driver:** `novatek-nvt-ts.c` is I2C-only, for `novatek,nt11205-ts` and `novatek,nt36672a-ts` — [novatek-nvt-ts.c](https://github.com/torvalds/linux/blob/master/drivers/input/touchscreen/novatek-nvt-ts.c)
- **Novatek SPI RFC:** an RFC/RFT for an SPI NT36xxx driver (October 2024) covered nt36525/nt36672a/nt36675/nt36676f/nt36772, not NT36523. No merge was found — [lkml RFC 0/3](https://lkml.iu.edu/hypermail/linux/kernel/2410.1/11376.html)
- **Mainline Himax touch driver:** `himax_hx83112b.c` is I2C-only (`himax,hx83112b`, `himax,hx83100a`) — [himax_hx83112b.c](https://github.com/torvalds/linux/blob/master/drivers/input/touchscreen/himax_hx83112b.c)
- **Backlight drivers in mainline:** `ktz8866.c` exists (`kinetic,ktz8866`, with an `kinetic,enable-lcd-bias` option). No `ktz8864`, `sgm37604a` or OCP2138 driver exists — [ktz8866.c](https://github.com/torvalds/linux/blob/master/drivers/video/backlight/ktz8866.c)
- **Pen, from Lenovo:** Lenovo's Precision Pen 2 page gives "WGP: 86 ~ 400 [kHz] / 8 channels", a WGP tip output of "Nominal 20 [V]", and pressure "Up to 4096 levels, depends on touch IC's F/W setting" (seen in search results; the page returned 403 to the fetcher) — [Lenovo support ACC500265](https://support.lenovo.com/ca/en/accessories/acc500265-lenovo-precision-pen-2-overview-and-service-parts)
- **Pen, from retailers:** one retailer says the Precision Pen 2 (ZG38C03372) connects "via Bluetooth" and has 3 buttons — [Coolblue](https://www.coolblue.nl/en/product/876515/lenovo-precision-pen-2.html). A spare-parts site lists the Yoga Tab 11 spare pen as MPP 2.0 — [sparepartworld](https://www.sparepartworld.com/lenovo/tablet/yoga-tablet-serie/yoga-tab-11-zaa9/pen-78206194). These retailer claims conflict with each other and with PSREF ("WGP").

### Inferences
- **The two panel/touch pairs are second sources.** Each unit has *either* NT36523W (TDDI: display and touch in one chip) *or* HX83102P (display) with HX83102E-class touch. The board DT must be chosen per unit, as LK does today through the LCM name.
- **"P530"** is probably Longcheer's internal project code for this tablet. It is never tied to a Lenovo model name in any source found.
- **Novatek variant:** this is the most promising route. The mainline J606F panel is the same controller, glass maker (BOE), size class, resolution, refresh rate and lane count. The vendor init sequence must still be compared byte by byte with the `j606f_boe_init_sequence`. Touch would need a new SPI driver or the community SPI RFC, extended to NT36523 with WGP pen reports.
- **Himax variant:** this needs a new panel entry in `panel-himax-hx83102.c` and an SPI Himax touch driver. Both are absent from mainline.
- **Pen:** WGP is decoded by the touch IC firmware, so pen support on Linux depends on the touch driver exposing the pen reports (`novatek,wgp-stylus`). If the pen has Bluetooth at all, it is likely only for buttons or shortcuts; that is unconfirmed.
- **Backlight:** the vendor kernel has three bias/backlight drivers, so the backlight IC may differ between units as well. A 60 Hz single-DSI video-mode panel is the simplest case for the mainline MediaTek DSI driver once the community DSI work is in place.

### Gaps
- **Which variant a given unit has:**
  - `adb shell cat /proc/device-tree/chosen/atag,videolfb-lcmname` (may need root);
  - `adb shell getevent -lp` (input device names, and whether the touch device advertises BTN_TOOL_PEN/ABS_PRESSURE);
  - `adb shell su -c 'dmesg | grep -iE "TP info|lcm|ktz8864|sgm37604|ocp2138"'`.
- **Board DT (dtbo, not obtained):** `adb shell su -c 'dd if=/dev/block/by-name/dtbo_a of=/sdcard/dtbo.img'`, then `mkdtboimg.py dump` / `dtc -I dtb`; or extract `dtbo.img` from a stock ROM package. This settles the SPI bus numbers, GPIOs, the backlight IC, the amplifier and sensor nodes in one step.
- **Live device tree:** `adb shell su -c 'cat /sys/firmware/fdt' > live.dtb`.
- **Panel part number on the glass** (BOE model number): only a teardown or the module label settles it.
- **Pen Bluetooth:** check `adb shell dumpsys bluetooth_manager` with the pen paired, and `adb shell getevent -lt` while hovering the pen.

## Wi-Fi, Bluetooth, GNSS and LTE

### Takeaway
Wi-Fi, Bluetooth and GNSS are the MT6785's integrated CONSYS (MediaTek "connac"/gen4m generation, firmware family `soc1_0`, RF companion reportedly MT6631), not a discrete SDIO/PCIe chip. There is **no mainline driver**. An out-of-tree port of the vendor gen4m Wi-Fi driver and a CONSYS bring-up shim to kernel 6.16.4 works on another MT6785 device (Redmi Note 8 Pro) as of 2026-11-13: Wi-Fi and Bluetooth work, GPS and the LTE modem do not. LTE (YT-J706X only) is the MT6785's integrated modem.

### Cited Findings
- **Wi-Fi/Bluetooth/location per PSREF:**
  - Two configurations are listed: 802.11a/b/g/n/ac dual band 1x1 + BT 5.0, and 802.11a/b/g/n/ac dual band 2x2 + BT 5.0.
  - "WLAN models have no location service. WWAN models have GPS + GLONASS + A-GPS."
  - Wi-Fi Direct and Wi-Fi Display are supported.
  - [Lenovo PSREF](https://psref.lenovo.com/syspool/Sys/PDF/Lenovo_Tablets/Yoga_Tab_11/Yoga_Tab_11_Spec.html)
- **[stock DTB] CONSYS nodes:**
  - `consys@18002000` with `compatible = "mediatek,mt6785-consys"`.
  - `wifi@18000000` with `compatible = "mediatek,wifi"` (memory region reserved).
  - `mediatek,btif` and `mediatek,consys-reserve-memory`.
  - `wifi-pwrseq` (`mmc-pwrseq-simple`) is disabled, so there is no SDIO Wi-Fi.
  - [dtb.img](https://github.com/jeremywildsmith/android_device_lenovo_yoga11/blob/HEAD/prebuilt/dtb.img)
- **[stock kernel] Built-in connectivity code:** only WMT thermal glue (`wmt_tm`, `mtk_ts_wmt_766x`). The Wi-Fi and BT drivers themselves are not built in, which is consistent with MediaTek shipping them as vendor modules (`wmt_drv`, `wlan_drv_gen4m`) — [kernel](https://github.com/jeremywildsmith/android_device_lenovo_yoga11/blob/HEAD/prebuilt/kernel)
- **Firmware names on another MT6785 device (Redmi Note 8 Pro, not this tablet):** `WIFI_RAM_CODE_soc1_0_2a_1.bin`, `WMT_SOC.cfg`, `BT_FW.cfg`, `fm_cust.cfg` — [begonia proprietary-files.txt](https://github.com/begonia-dev/android_device_redmi_begonia/blob/HEAD/proprietary-files.txt)
- **Vendor properties on that device:** `persist.vendor.connsys.fm_chipid=mt6631` and `ro.vendor.wlan.gen=gen4m` — [begonia vendor.prop](https://github.com/begonia-dev/android_device_redmi_begonia/blob/HEAD/vendor.prop)
- **MT6631's role:** on the earlier MT6771T, the RF parts of the WLAN, Bluetooth, GPS and FM blocks are on the companion MT6631 — [FCC report for MT6771T device](https://fcc.report/FCC-ID/2APMJA100/5588286.pdf)
- **Out-of-tree Wi-Fi on mainline 6.16.4, as reported by the author (draft not sent upstream):**
  - The MT6785 CONSYS (`soc1_0`, HW/SW id 0x8a00) was brought up on mainline 6.16.4 with `WIFI_RAM_CODE_soc1_0_2a_1.bin` and `soc1_0_{patch_mcu,ram_mcu,ram_bt,ram_wifi}_2a_1_hdr.bin`.
  - The approach is a CONSYS power/firmware shim (BTIF + STP + WMT, patch download through the AP_DMA BTIF TX vFIFO) plus the vendor gen4m driver ported from 4.14 (~1 100 files, profile CONNAC, `WLAN_CHIP_ID=6785`, HIF AXI on `mediatek,wifi`).
  - Result: it scans 2.4/5 GHz and associates with WPA2-Enterprise. It is "not upstreamable as is" and the driver cannot be unloaded.
  - [report-to-maintainer-wifi.md](https://github.com/F-to-pay/PostmarketOS-begonia/blob/HEAD/wifi/report-to-maintainer-wifi.md)
- **Same port, overall status (2026-11-13):** Wi-Fi works (now in `drivers/staging/mt6785-consys` and `drivers/staging/mt6785-gen4m`). Bluetooth works over HCI on STP (BR/EDR, LE, A2DP sink). GPS "does not work: the chip sends NMEA, 0 satellites". The modem "does not work: MD boots up to RF init, then asserts" — [PostmarketOS-begonia README](https://github.com/F-to-pay/PostmarketOS-begonia)
- **Mainline has no driver for this Wi-Fi.** mt76 has `mt7921/sdio.c` and there is `btmtksdio.c`, but both target discrete SDIO/PCIe MediaTek chips, not the SoC-integrated CONSYS — [mt76 mt7921](https://github.com/torvalds/linux/tree/master/drivers/net/wireless/mediatek/mt76/mt7921), [btmtksdio.c](https://github.com/torvalds/linux/blob/master/drivers/bluetooth/btmtksdio.c)
- **LTE (YT-J706X):**
  - Bands: GSM B2/3/5/8; WCDMA B1/2/5(6/19)/8; FDD-LTE B1/2/3/4/5(19)/7/8/20/26/28; TDD-LTE B38/40/41; carrier aggregation including CA_3C and CA_7C.
  - The card slot is nano-SIM + microSD on the WWAN model.
  - [Lenovo PSREF](https://psref.lenovo.com/syspool/Sys/PDF/Lenovo_Tablets/Yoga_Tab_11/Yoga_Tab_11_Spec.html)
- **[stock DTB/kernel] Modem and SAR (shared by both models' image):**
  - Modem infrastructure nodes: `mediatek,dpmaif`, `mediatek,ap_ccif0-4`, `md1_sim1_hot_plug_eint`, `md1_sim2_hot_plug_eint`, `swtp-eint`, and the Longcheer `longcheer,ant_check` / `longcheer,ant_check_div`.
  - Capacitive SAR sensor drivers: Semtech **SX933x/SX9328**, **ABOV** (`abov,abov_sar`) and Awinic **AW9610x** (`awinic,aw9160x_sar`, `aw9610x,firmware_name`).
  - [dtb.img](https://github.com/jeremywildsmith/android_device_lenovo_yoga11/blob/HEAD/prebuilt/dtb.img), [kernel](https://github.com/jeremywildsmith/android_device_lenovo_yoga11/blob/HEAD/prebuilt/kernel)
- **SAR sensors in mainline:** `aw96103.c` (`awinic,aw96103`, `awinic,aw96105`), `sx9310.c` (`semtech,sx9310`/`sx9311`), `sx9324.c` and `sx9360.c`. No SX933x or ABOV driver exists — [aw96103.c](https://github.com/torvalds/linux/blob/master/drivers/iio/proximity/aw96103.c), [proximity dir](https://github.com/torvalds/linux/tree/master/drivers/iio/proximity)

### Inferences
- The Wi-Fi of the YT-J706F is almost certainly the same CONSYS IP as the Redmi Note 8 Pro's. The begonia port is therefore direct prior art. Its bring-up recipe (EMI remap, XO_WCN clock buffer, BTIF DMA patch download) should transfer, with board differences limited to regulators and antenna configuration.
- Expect a staging-quality out-of-tree driver, not mainline mt76, for the life of the port. Bluetooth comes from the same shim.
- **Wi-Fi model location:** PSREF says the Wi-Fi model has no location service, even though the CONSYS contains a GNSS block. The YT-J706F likely has no GNSS antenna or has GNSS disabled in firmware, so GNSS is not a goal there.
- **LTE (J706X only):** this requires the MediaTek CCCI/DPMAIF modem stack, which has no mainline driver for MT6785; the begonia attempt failed at RF init. Treat LTE as out of scope for a first port.
- **SAR sensors:** these are mainly relevant to the LTE model's RF exposure limits; the YT-J706F can ignore them.

### Gaps
- **1x1 vs 2x2 Wi-Fi:** which retail SKUs have which. Check with `adb shell dumpsys wifi | grep -iE "nss|MaxNumberTxSpatialStreams|antenna"`; FCC test reports for O57YTJ706F could also settle it. The FCC pages (device.report, fccid.io, fcc.report) returned HTTP 403, so the internal photos and chip list in the filing were not seen. The filing ID exists — [device.report O57YTJ706F](https://device.report/fccid/O57YTJ706F).
- **This tablet's exact firmware file names:** `adb shell ls -l /vendor/firmware | grep -iE "WIFI|soc1_0|BT|WMT|gps|fm"`, `adb shell getprop | grep -iE "connsys|wlan|wifi.gen"`, and `adb shell lsmod` or `ls /vendor/lib/modules`.
- **GNSS on the Wi-Fi model:** `adb shell dumpsys location | grep -i gnss`.
- **Which SAR chip is fitted:** `adb shell cat /sys/bus/i2c/devices/*/name`.

## Audio: codec, amplifiers, microphones, jack

### Takeaway
The audio path is the MT6785 AFE plus the MT6359(P) PMIC codec (`mediatek,mt6785-mt6359-sound`). The four JBL speakers are driven by **Cirrus Logic CS35L41** smart amplifiers (I2C, firmware-tuned). Far-field voice uses a **Synaptics AudioSmart AS33970** DSP; PSREF's "Synopsys codec" is very likely this part, misspelled. There is no 3.5 mm jack. Mainline has CS35L41 and the MT6359 codec and ACCDET, but no MT6785 AFE platform driver (a community port exists) and no AS33970 driver.

### Cited Findings
- **PSREF audio block:** "Quad JBL speakers, Synopsys codec, 2 x 1W (top), 2 x 2W (bottom), 5cc audio chamber ... Dolby Atmos"; "Dual-microphone array, low-power DSP for far-field voice recognition" — [Lenovo PSREF](https://psref.lenovo.com/syspool/Sys/PDF/Lenovo_Tablets/Yoga_Tab_11/Yoga_Tab_11_Spec.html)
- **[stock DTB] Sound nodes:** `sound` has `compatible = "mediatek,mt6785-mt6359-sound"` with `mtk_spk_i2s_out = <1>` and `mtk_spk_i2s_in = <2>`. Also present: `mediatek,mt6785-sound` (AFE), `mediatek,mt6359-sound`, `mediatek,pmic-accdet`, `mediatek,snd_audio_dsp`, `mediatek,snd_scp_ultra`, `mediatek,mtk-btcvsd-snd`, `mediatek,smartpainfo`, and a placeholder `smart_pa` — [dtb.img](https://github.com/jeremywildsmith/android_device_lenovo_yoga11/blob/HEAD/prebuilt/dtb.img)
- **[stock kernel] CS35L41 amplifier:**
  - A full ASoC driver is built in (`snd_soc_cs35l41`, `cs35l41_probe`, `cs35l41_mi2s_snd_init`, `cs35l41_do_fast_switch`, `cs35l41_enter_hibernate`, `cs35l41_otp_unpack`) with DT properties `cirrus,cs35l41`, `cirrus,cs35l40`, `cirrus,boost-ind-nanohenry`, `cirrus,boost-cap-microfarad`, `cirrus,wmfw-file`, `cirrus,bin-file`, `cirrus,right-channel-amp`.
  - Firmware name patterns `%s-%s-%s.wmfw` / `%s-%s-%s.bin`; tuning files `fast_switch1.txt` … `fast_switch5.txt`.
  - `tfa98xx` appears only twice as a name and `mtk_spk_mediatek_mt6660` once.
  - [kernel](https://github.com/jeremywildsmith/android_device_lenovo_yoga11/blob/HEAD/prebuilt/kernel)
- **[stock kernel] AS33970 voice DSP:** `syna,as33970`, `snd_soc_as33970`, `as33970_i2c_probe`, `as33970_set_always_listening`, `as33970_set_aec`, `as33970_set_nr`, `as33970_rst_gpio`, `as33970_irq_gpio` — [kernel](https://github.com/jeremywildsmith/android_device_lenovo_yoga11/blob/HEAD/prebuilt/kernel)
- **No 3.5 mm jack:** reviews state the Yoga Tab 11 has no headphone jack — [Tom's Guide review](https://tomsguide.com/reviews/lenovo-yoga-tab-11-review), [Android Police review](https://www.androidpolice.com/lenovo-yoga-tab-11-review/), [91mobiles review](https://www.91mobiles.com/hub/lenovo-yoga-tab-11-review/)
- **Mainline status:**
  - Yes: `sound/soc/codecs/cs35l41.c` (I2C compatibles `cirrus,cs35l40` and `cirrus,cs35l41`), `sound/soc/codecs/mt6359.c`, `mt6359-accdet.c`.
  - No: `sound/soc/mediatek/` has platform drivers for mt2701, mt6797, mt7986, mt8173, mt8183, mt8186, mt8188, mt8189, mt8192, mt8195, mt8196 and mt8365, but **no mt6785**.
  - [cs35l41-i2c.c](https://github.com/torvalds/linux/blob/master/sound/soc/codecs/cs35l41-i2c.c), [mt6359.c](https://github.com/torvalds/linux/blob/master/sound/soc/codecs/mt6359.c), [sound/soc/mediatek](https://github.com/torvalds/linux/tree/master/sound/soc/mediatek)
- **Community MT6785 audio port:** the begonia port (2026-11-13) moved an MT6785 AFE port into `sound/soc/mediatek/mt6785`, with MT6359 codec/ACCDET changes and a TFA9874 amplifier driver, out of tree on 6.16.4. Headphones, two microphones, speaker and jack detection work on that phone — [PostmarketOS-begonia README](https://github.com/F-to-pay/PostmarketOS-begonia)

### Inferences
- **Speakers:** the begonia MT6785 AFE port plus mainline `cs35l41` (with Cirrus DSP firmware `.wmfw` and tuning `.bin` from `/vendor/firmware`) is a credible path. The CS35L41 uses Halo-core DSP firmware for speaker protection, so the vendor tuning files must be reused for safe speaker drive.
- **Microphones:** the AS33970 sits between the microphones and the SoC, or alongside them, for far-field use. Without a driver the microphones may still reach the MT6359 ADCs directly. The routing is unknown until the board DT is read.
- **Headset audio:** with no jack, the MT6359 ACCDET node is SoC-generic and probably unused. USB-C headset audio would depend on the MT6360 TCPC and analog switches, which is unverified.

### Gaps
- **Number of CS35L41 amplifiers** (two or four), their I2C addresses and the I2S/TDM wiring: settle with the dtbo, or with `adb shell cat /sys/bus/i2c/devices/*/name`, `adb shell ls /vendor/firmware | grep -iE "cs35|wmfw|as339|syna"`, `adb shell cat /proc/asound/cards` and `adb shell cat /proc/asound/pcm`.
- **Microphone routing** (MT6359 ADCs vs AS33970): read the dtbo and `adb shell su -c 'tinymix'`.
- **USB-C analog audio support:** test a passive USB-C to 3.5 mm adapter on stock Android.

## Power: PMICs, charger, fuel gauge, battery, USB-C

### Takeaway
The main PMIC is **MediaTek MT6359P** (regulators, codec, RTC, AUXADC, built-in gauge "GM3.0"). The sub-PMIC is **MediaTek MT6360** (switching charger, LDOs, flash/RGB LED, ADC and the **Type-C/PD TCPC**). The base DTB also has a placeholder for a **Richtek RT9465** slave charger, but the kernel has no driver for it. The battery is a 7 500 mAh minimum / 7 700 mAh typical Li-Po, charged with a 20 W (10 V/2 A) adapter. USB-C is **USB 2.0** per Lenovo, and there is no DisplayPort transmitter in the SoC DT. Mainline covers MT6359 regulators, codec and keys and the whole MT6360 (charger, regulators, LEDs, TCPC), but has no MT6359 fuel-gauge driver.

### Cited Findings
- **PSREF power and port data:**
  - Battery: integrated Li-Polymer, 7500 mAh (min) / 7700 mAh (typical).
  - Charging: "over 2 hr to fully charged" with a 10V/2A (20W) adapter.
  - Port: "1x USB-C 2.0 (data transfer and charging)". OTG and DisplayPort are not mentioned.
  - [Lenovo PSREF](https://psref.lenovo.com/syspool/Sys/PDF/Lenovo_Tablets/Yoga_Tab_11/Yoga_Tab_11_Spec.html)
- **Battery part:** an aftermarket listing names the YT-J706F/X battery **L20D2P31** (no capacity given, out of stock). An "L20D2P32 ... 29Wh" listed for ZA8X is a different code — [iServiceIndia L20D2P31](https://iserviceindia.in/product/battery-for-lenovo-yoga-tab-11-yt-j706f-yt-j706x), [sparepartworld L20D2P32](https://www.sparepartworld.com/laptop-spare-parts/batteries/battery-l20d2p32-128909202)
- **[stock DTB] MT6359 nodes:** `mediatek,mt6359-pmic`, `-regulator`, `-rtc`, `-auxadc`, `-misc`, `-sound`, `mediatek,mt6359_gauge`, the gauge config `mediatek,bat_gm30` (e.g. `R_FG_VALUE = 5`, `CAR_TUNE_VALUE = 100`), and `mediatek,mt6785-pwrap` — [dtb.img](https://github.com/jeremywildsmith/android_device_lenovo_yoga11/blob/HEAD/prebuilt/dtb.img)
- **[stock kernel] MT6359P identity:** strings `mt6359p`, `mt6359vproc`, `mt6359vgpu`, `mt6359vcore` — [kernel](https://github.com/jeremywildsmith/android_device_lenovo_yoga11/blob/HEAD/prebuilt/kernel)
- **[stock DTB] MT6360 node `mt6360_pmu_dts`:**
  - Child functions `mediatek,mt6360_pmu_adc`, `_chg` (`chg_name = "primary_chg"`), `_fled`, `_rgbled`, `_core`, plus `mt6360_pmic_dts`. The interrupt is on GPIO 16.
  - Charger values in the base DTB: `ichg` = 3 700 000 µA, `aicr` = 2 100 000 µA, `cv` = 4 430 000 µV, `ieoc` = 350 000 µA.
  - Also present: `mediatek,rt-pd-manager`, `mediatek,pd_adapter`, `mediatek,extcon-usb`, and a placeholder `rt9465_slave_chr` with `compatible = "richtek,rt9465"`.
  - [dtb.img](https://github.com/jeremywildsmith/android_device_lenovo_yoga11/blob/HEAD/prebuilt/dtb.img)
- **[stock kernel] Charging/Type-C stack:** `tcpc_mt6360`, `mt6360_tcpc_init`, `mt6360pd,intr_gpio`, the Richtek TCPC framework (`tcpci_core`) and PD/DP alt-mode properties (`signal,dp_v13`, `signal,dp_gen2`, `pin_assignment,mode_c`). There are no `rt946x` strings; `bq27xxx` strings are generic upstream code — [kernel](https://github.com/jeremywildsmith/android_device_lenovo_yoga11/blob/HEAD/prebuilt/kernel)
- **[stock DTB] USB:**
  - `usb3@11200000` (`mediatek,usb3`, regs `ssusb_base`, `ssusb_ippc`, `ssusb_sif2`), `mtu3_0` (`mediatek,mt6785-mtu3`, `dr_mode = "otg"`), `mediatek,mt67xx-xhci`, `mediatek,usb3_phy`, `usb-nop-xceiv`.
  - `phy_tuning` (`u2_vrt_ref = 7`, `u2_term_ref = 7`).
  - The recovery fstab mounts USB storage from `/devices/platform/usb3_xhci*`.
  - [dtb.img](https://github.com/jeremywildsmith/android_device_lenovo_yoga11/blob/HEAD/prebuilt/dtb.img), [recovery.fstab](https://github.com/jeremywildsmith/android_device_lenovo_yoga11/blob/HEAD/recovery.fstab)
- **Mainline status:**
  - Yes: `drivers/mfd/mt6360-core.c`, `power/supply/mt6360_charger.c`, `regulator/mt6360-regulator.c`, `leds/flash/leds-mt6360.c`, `usb/typec/tcpm/tcpci_mt6360.c` (`mediatek,mt6360-tcpc`), `regulator/mt6359-regulator.c` (with MT6359P tables), `iio/adc/mt6359-auxadc.c`, `rtc/rtc-mt6397.c`. The `mfd/mt6397-core.c` compatibles include `mediatek,mt6359`, `-accdet`, `-auxadc`, `-keys`.
  - No: an MT6359 fuel-gauge driver in `drivers/power/supply`, and `rt9465`. `rt9467-charger.c` exists but is a different part.
  - [torvalds/linux drivers/power/supply](https://github.com/torvalds/linux/tree/master/drivers/power/supply), [mt6359-regulator.c](https://github.com/torvalds/linux/blob/master/drivers/regulator/mt6359-regulator.c), [tcpci_mt6360.c](https://github.com/torvalds/linux/blob/master/drivers/usb/typec/tcpm/tcpci_mt6360.c)
- **Community fuel gauge and charger:** the begonia MT6785 port carries out-of-tree patches for the MT6359 fuel gauge (FGADC), the MT6360 charger and the battery DT, "works (r3 verified on hardware)" — [PostmarketOS-begonia README](https://github.com/F-to-pay/PostmarketOS-begonia)

### Inferences
- **The power stack is the best-supported area.** The MT6360 (charger, TCPC, regulators) and MT6359P regulators are mainline. Battery percentage needs the community MT6359 gauge patches, or a simple voltage-based fallback.
- **The RT9465 node** is a MediaTek reference placeholder. No RT946x driver is compiled, so a second charger is unlikely on this board. It could still be defined in the dtbo; verify.
- **No USB-C video out:** the SoC DT has DSI and DPI blocks but no DP or HDMI transmitter, and Lenovo states USB 2.0, so DisplayPort alt mode is very likely impossible. The DP alt-mode strings are generic Richtek TCPC framework code.
- **USB 3 controller vs USB 2.0 port:** the SSUSB controller supports xHCI host and OTG, but the board's USB 3 lanes are probably not routed.

### Gaps
- **USB 2 vs USB 3 on the port:** with a USB 3 drive on OTG, `adb shell cat /sys/bus/usb/devices/*/speed`.
- **Type-C and PD state:** `adb shell ls /sys/class/typec/` and `adb shell dumpsys usb`.
- **Battery data:** `adb shell dumpsys battery` and `adb shell cat /sys/class/power_supply/*/uevent`. The battery cell maker and profile ID need root `dmesg | grep -i battery_id`.
- **Second charger or the real charge limits** (dtbo overrides of the base-DTB values): read the dtbo.
- **Charging during the port:** whether the PSREF "20 W" relies on MT6360 PE+/PD at 9-10 V, which a Linux port must negotiate through TCPM. Test with `adb shell cat /sys/class/power_supply/*/voltage_now` while charging on stock.

## Sensors, cameras, vibration, buttons, kickstand, keyboard

### Takeaway
- **Motion and light sensors:** accelerometer, gyroscope and ALS, behind MediaTek's **SCP sensor hub** (`accelhub`, `gyrohub`, `alspshub`), so the physical chip names are in SCP firmware, not the kernel.
- **Front camera:** 8 MP fixed focus, with a ToF sensor (driver not built into the kernel).
- **Rear camera:** 8 MP autofocus.
- **Camera sensor drivers in the kernel:** Samsung **S5K4H7** (three variants) and OmniVision **OV8856**.
- **Vibration:** ERM motor.
- **Keyboard:** no pogo keyboard for this model. The kernel's pogo-keyboard code ("P11 KeyBoard Lenovo") reports "Not support pogo keyboard" when the DT lacks it.
- **Mainline:** OV8856 yes; S5K4H7 and the MT6785 camera ISP no.

### Cited Findings
- **PSREF sensors and cameras:**
  - Sensors: "Accelerometer, ambient light sensor (ALS), gyroscope, ToF sensor".
  - Vibration motor: Eccentric Rotating Mass (ERM).
  - Front camera: 8.0 MP, 1080p30, ToF sensor, 99° FoV, fixed focus, face unlock. Rear camera: 8.0 MP, 1080p30, 86° FoV, autofocus.
  - Buttons: power, volume. Kickstand: "free stop". Keyboard: not listed.
  - [Lenovo PSREF](https://psref.lenovo.com/syspool/Sys/PDF/Lenovo_Tablets/Yoga_Tab_11/Yoga_Tab_11_Spec.html)
- **Kickstand hang mode:** reviews describe an integrated kickstand that can also hang the tablet (single source for hanging) — [MyNextTablet review](https://mynexttablet.com/lenovo-yoga-tab-11-review/), [91mobiles review](https://www.91mobiles.com/hub/lenovo-yoga-tab-11-review/)
- **[stock kernel] Sensor hub:** `SCP_sensorHub`, `accelhub_ReadSensorData`, `gyrohub_ReadGyroData`, `alspshub`, `situation`. No ToF driver (VL53/TMF8 family) is built in; only a stray `tof_i2c` string — [kernel](https://github.com/jeremywildsmith/android_device_lenovo_yoga11/blob/HEAD/prebuilt/kernel)
- **[stock DTB] SCP:** `mediatek,scp` with `scp_i2c0-2`, `scp_spi0-2` and `scp_gpio` — [dtb.img](https://github.com/jeremywildsmith/android_device_lenovo_yoga11/blob/HEAD/prebuilt/dtb.img)
- **[stock kernel] Camera sensor drivers:**
  - Sensors: `s5k4h7_mipi_raw`, `s5k4h7txd_mipi_raw`, `s5k4h7yxsub_mipi_raw`, `ov8856_mipi_raw`.
  - Many generic MediaTek autofocus actuator drivers are built in (dw9718, gt9764, ak7371/7374, lc898212/214/217/229, fp5510e2, bu64748, dw9763, …). The fitted actuator is not identifiable.
  - [kernel](https://github.com/jeremywildsmith/android_device_lenovo_yoga11/blob/HEAD/prebuilt/kernel)
- **[stock DTB] Camera and flash hardware:** `mediatek,imgsensor` (`kd_camera_hw1`), `seninf1-6` CSI-2 receivers, `mipi_rx_ana_csi0a..2b`, `flashlights_mt6360` — [dtb.img](https://github.com/jeremywildsmith/android_device_lenovo_yoga11/blob/HEAD/prebuilt/dtb.img)
- **[stock kernel] Vibrator and keys:** `vibrator_drv` and the `vibr` PMIC LDO. Keys: `mediatek,kp` (`kp@10010000`) and MT6359 power key — [kernel](https://github.com/jeremywildsmith/android_device_lenovo_yoga11/blob/HEAD/prebuilt/kernel), [dtb.img](https://github.com/jeremywildsmith/android_device_lenovo_yoga11/blob/HEAD/prebuilt/dtb.img)
- **[stock kernel] Pogo keyboard code:**
  - Driver strings `lq_keyboard`, "%s %04hX:%04hX P11  KeyBoard Lenovo", "KEYBOARD_STATATUS=ENABLE", `mcu_hall_int_gpio`, and "kb_hall_status".
  - Log lines "Not support pogo keyboard and mouse", "Not support pogo keyboard and mouse hall int pin".
  - A Longcheer touch self-test string ("Longcheer MMI TP self-test").
  - [kernel](https://github.com/jeremywildsmith/android_device_lenovo_yoga11/blob/HEAD/prebuilt/kernel)
- **Keyboard accessories:** the accessory search found Bluetooth keyboards listed as compatible with the Yoga Tab 11 but no pogo-pin keyboard for it. The pogo folio keyboards found are for the IdeaTab 11 and Yoga Tab Plus — [Newegg BoxWave listing](https://www.newegg.com/p/3C6-03AW-00632), [Ballicom ZG38C07010](https://www.ballicom.co.uk/zg38c07010-lenovo-keyboard-pack.p1695206.html)
- **Mainline status:**
  - Yes: `drivers/media/i2c/ov8856.c`, `drivers/input/keyboard/mtk-pmic-keys.c` (`mediatek,mt6359-keys` in the mt6397 MFD).
  - No: `s5k4h7`. No MT6785 camsys/seninf/ISP driver exists; only `clk-mt6785-cam/img` clocks exist in the community tree.
  - [ov8856.c](https://github.com/torvalds/linux/blob/master/drivers/media/i2c/ov8856.c), [external-mirrors/mt6785-mainline-linux](https://github.com/external-mirrors/mt6785-mainline-linux)
- **Community ERM approach:** the begonia DTS uses `regulator-haptic` for its vibration motor and mainline drivers for its sensors (`bosch,bmi120`, `asahi-kasei,ak09918`, `sensortek,stk3310`) on the AP I2C buses, not through the SCP — [mt6785-xiaomi-begonia.dts](https://github.com/external-mirrors/mt6785-mainline-linux/blob/6.16/arch/arm64/boot/dts/mediatek/mt6785-xiaomi-begonia.dts)

### Inferences
- **"P11 KeyBoard Lenovo" and "Longcheer"** point to a Longcheer ODM kernel shared with other Lenovo MT6785 tablets; the Tab P11 Plus TB-J616 is a plausible sibling. The pogo, hall and keyboard code is probably inactive on the YT-J706F. The DTB compatible `longcheer,ant_check` also points to Longcheer as ODM.
- **Sensors:** the accelerometer, gyroscope and ALS chips are probably wired to SCP I2C pins on the vendor design. Mainline Linux has no SCP sensor-hub framework, so on Linux they work only if they are reachable from AP I2C, as on begonia, or if the SCP firmware protocol is reimplemented. Screen rotation (accelerometer) is a must-have for a tablet port; this is a significant risk.
- **Cameras:** treat them as out of scope. There is no mainline MT6785 ISP, and S5K4H7 has no driver. Of the two sensor families, OV8856 has a mainline driver.
- **Vibration:** the ERM motor on the MT6359 `vibr` LDO can be driven by mainline `regulator-haptic`.
- **Hall sensor and kickstand:** no hall sensor for a cover or the kickstand is evidenced. The kickstand appears purely mechanical.

### Gaps
- **Physical sensor chips and buses:** `adb shell dumpsys sensorservice | head -60` (vendor and name of the accelerometer, gyroscope, ALS and ToF); `adb shell cat /sys/bus/i2c/devices/*/name`; the dtbo SCP/I2C nodes.
- **Camera sensor per position:** `adb shell dumpsys media.camera | grep -iE "sensor|facing"`; `adb shell su -c 'cat /proc/driver/camera_info'` (MediaTek); `adb shell getprop | grep -i camera`.
- **ToF part number and driver:** `adb shell ls /vendor/lib/modules /vendor/firmware`; `dumpsys sensorservice`.
- **Volume key wiring** (keypad matrix or GPIO): `adb shell getevent -lp`.
- **Pogo pins:** physical inspection of the tablet edges, and whether any pogo or hall node exists in the dtbo.

## Differences between YT-J706F and YT-J706X, and regional variants

### Takeaway
The models differ in the modem (LTE on X), location (GNSS only on X), SIM slot and the SoC marketing name. Every unit also varies in second-source parts (panel/touch variant, camera sensor, possibly backlight IC), and SKUs vary in RAM/storage and possibly in 1x1 vs 2x2 Wi-Fi.

### Cited Findings
- **Per-model differences:**
  - SoC label: "M8185" for the Wi-Fi model, "G90T MT8789" for the LTE model.
  - SIM: card slot is microSD on the WLAN model, nano-SIM + microSD on the WWAN model.
  - Location: none on the WLAN model; GPS/GLONASS/A-GPS on WWAN.
  - ENERGY STAR 8.0: only the YT-J706F.
  - Thickness: 7.9-8.3 mm "varies by configuration".
  - [Lenovo PSREF](https://psref.lenovo.com/syspool/Sys/PDF/Lenovo_Tablets/Yoga_Tab_11/Yoga_Tab_11_Spec.html); ENERGY STAR note also in the [PSREF PDF](https://psrefstuff.lenovo.com/syspool/Sys/PDF/Lenovo_Tablets/Yoga_Tab_11/Yoga_Tab_11_Spec.PDF)
- **Lenovo support identities:** "Yoga Tab 11 (Lenovo YT-J706F, Lenovo YT-J706X)", with machine types ZA8W, ZA8X, ZAA8 and ZAA9 under the product — [Lenovo PC Support](https://pcsupport.lenovo.com/products/tablets/yoga-series/yoga-tab-11), [ZA8W](https://pcsupport.lenovo.com/products/tablets/yoga-series/yoga-tab-11/za8w), [ZAA9](https://pcsupport.lenovo.com/products/tablets/yoga-series/yoga-tab-11/zaa9)
- **PSREF configuration options:** 4 GB or 8 GB RAM; 64/128/256 GB UFS; Wi-Fi 1x1 or 2x2 — [Lenovo PSREF](https://psref.lenovo.com/syspool/Sys/PDF/Lenovo_Tablets/Yoga_Tab_11/Yoga_Tab_11_Spec.html)
- **Spec-sheet revisions differ:** a 2021 PSREF revision described "4 side stereo speakers, Synopsys codec, JBL authorized"; a 2024 revision describes "Quad JBL speakers ... 2 x1W (top), 2 x2W (bottom)" (from search-result excerpts) — [PSREF PDF](https://psrefstuff.lenovo.com/syspool/Sys/PDF/Lenovo_Tablets/Yoga_Tab_11/Yoga_Tab_11_Spec.PDF)
- **Mainboard FRUs:** 4+64, 4+128 and 8+256 boards have distinct FRUs (5B28C18879/80/81) — [IPC Computer](https://www.ipc-computer.eu/laptop-spare-parts/mainboards/mainboard-5b28c18879-145210232)
- **[stock kernel] Second-source parts in one build:** two panel/touch variants (NT36523W, HX83102P/E), two backlight drivers (KTZ8864A, SGM37604A), two camera sensor families (S5K4H7 and variants, OV8856) and three SAR sensors (SX933x, ABOV, AW9610x) — [kernel](https://github.com/jeremywildsmith/android_device_lenovo_yoga11/blob/HEAD/prebuilt/kernel)
- **FCC filing:** the YT-J706F's FCC ID is **O57YTJ706F**, described as a "Portable Tablet Computer" from Lenovo (Shanghai) (search-result excerpt; the page returned 403) — [device.report](https://device.report/fccid/O57YTJ706F)
- **Name clash:** "TB-J706F" (no Y) is the **Lenovo Tab P11 Pro**, on a Qualcomm sm6150 platform. It must not be confused with the YT-J706F — [Geekbench TB-J706F](https://browser.geekbench.com/v5/compute/2364377), [iServiceIndia P11 Pro battery](https://iserviceindia.in/product/battery-for-lenovo-tab-p11-pro-tb-j706f-tb-j706l)

### Inferences
- **For a Linux port, the YT-J706F is the simpler target:** no modem, no SIM, no GNSS, and the SAR sensors can be ignored.
- **One kernel, per-unit DT:** a single kernel can carry both panel/touch variants, but the DT must be selected per unit. The approaches are a bootloader-provided LCM name, DT overlays, or one DTB per variant.
- **Before buying:** the variant of a unit cannot be known from the box. A first-boot probe or the stock Android `getevent` check is needed.

### Gaps
- **Machine-type mapping** (ZA8W/ZA8X/ZAA8/ZAA9 to F/X and Wi-Fi 1x1/2x2): not established.
- **Factory share of each panel variant:** unknown.
- **Regional software differences** (PRC ROM, etc.): not researched.

## Consolidated component table (chip, bus, vendor driver, mainline status)

### Takeaway
The table below sums up the sections above. Mainline readiness is good for the PMICs, charger, Type-C, SD/UFS/USB and the CS35L41 amplifier. It is partial for the panel (NT36523W relative) and GPU (G76 known to Panfrost). It is missing for the SoC itself (community tree only), Wi-Fi/BT (out-of-tree port exists), audio AFE (community port), touch over SPI, the backlight ICs, the sensor hub, the cameras, the fuel gauge and the modem.

### Cited Findings
Sources for every row are the ones cited in the sections above. Abbreviations: "stock DTB/kernel" = [jeremywildsmith/android_device_lenovo_yoga11 prebuilt](https://github.com/jeremywildsmith/android_device_lenovo_yoga11/tree/HEAD/prebuilt); "mainline" = [torvalds/linux master](https://github.com/torvalds/linux), checked 2026-11-15; "community" = [mt6785-mainline mirror](https://github.com/external-mirrors/mt6785-mainline-linux) and [PostmarketOS-begonia](https://github.com/F-to-pay/PostmarketOS-begonia).

| Block | Exact part (evidence) | Bus | Vendor driver / DT compatible (stock) | Mainline driver for that part |
|---|---|---|---|---|
| SoC | MediaTek MT6785 "Helio G90T"; Lenovo label M8185 (Wi-Fi) / MT8789 (LTE) (PSREF; stock DTB `mediatek,MT6785`) | — | MediaTek 4.14 BSP | **No** (no mt6785 dtsi, clk or pinctrl). **Community**: dtsi, clk, pinctrl, pm-domains, mmsys on 6.16 |
| CPU | 2x A76 @2.05 GHz + 6x A55 @2.0 GHz (PSREF; stock DTB labels the big cores `cortex-a75`) | — | `mediatek,mt-cpufreq`, `mediatek,mt6785-dvfsp` | Generic arm64 yes; MT6785 cpufreq: community (OPP tables) |
| GPU | Mali-G76 MC4 (PSREF) | internal | `mediatek,mali` + `arm,mali-bifrost`, `mediatek,mt6785-gpufreq` | Panfrost knows G76 (0x7001); no `mt6785-mali` compatible upstream; **community** "Enable GPU" |
| RAM | 4/8 GB LPDDR4X (PSREF) | — | `mediatek,dramc`, `mediatek,emi` | n/a (set up by the bootloader) |
| Storage | UFS 2.1, 64/128/256 GB, vendor unknown (PSREF) | UFS, 1 lane (stock DTB) | `mediatek,ufshci`, `mediatek,ufs_mphy` | `ufs-mediatek.c` yes; MT6785 compatible: community |
| microSD | MSDC @0x11230000, SDR104 (stock DTB) | SD 4-bit | `mediatek,mt8183-mmc` | `mtk-sd.c` yes (mt8183 compatible) |
| Display panel | 11" 2000x1200 60 Hz BOE; variant A NT36523W TDDI, variant B HX83102P TDDI (stock kernel) | MIPI DSI video mode (4-lane likely) | LCM `nt36523w_fhdp_dsi_vdo_boe`, `hx83102p_fhdp_dsi_vdo_boe` | NT36523W: `panel-novatek-nt36523.c` has `lenovo,j606f-boe-nt36523w` (1200x2000, 4 lanes; **relative, not verified identical**). HX83102P: **no** entry in `panel-himax-hx83102.c` |
| DSI host / display pipeline | MT6785 DISP (OVL, RDMA, DSI0/1) | internal | `mediatek,dsi0`, `mtkfb` | Mainline mediatek-drm: no MT6785 data; **community** DSI/OVL support |
| Backlight / bias | KTZ8864A and/or SGM37604A backlight; OCP2138 LCD bias (stock kernel) | I2C | `ktz8864a`, `sgm37604a`, `ocp2138` i2c drivers | **No** (only `ktz8866` exists, a different part) |
| Touch | NT36523W (variant A) or HX83102E-class (variant B) (stock kernel) | **SPI** | `novatek,NVT-ts-spi` (fw `novatek_ts_fw.bin`); `himax-spi` (fw `Himax_firmware.bin`) | **No**: `novatek-nvt-ts` and `himax_hx83112b` are I2C-only for other ICs; SPI NT36xxx RFC (2024) not merged and without NT36523 |
| Stylus | Lenovo Precision Pen 2, WGP protocol (PSREF) | via touch IC (SPI) | `novatek,pen-support`, `novatek,wgp-stylus` | **No** (needs the touch driver) |
| Wi-Fi / BT / (GNSS, FM) | MT6785 CONSYS, CONNAC gen4m, fw family `soc1_0`; RF companion reportedly MT6631 (on begonia); 802.11ac 1x1 or 2x2, BT 5.0 (PSREF) | internal AXI + BTIF | `mediatek,mt6785-consys`, `mediatek,wifi`, vendor `wmt_drv`/`wlan_drv_gen4m` modules | **No**. **Community**: staging `mt6785-consys` + `mt6785-gen4m` on 6.16.4 (Wi-Fi and BT work on begonia; GPS no) |
| LTE modem (J706X only) | MT6785 integrated modem MD1 (PSREF bands) | internal CCIF/DPMAIF | `mediatek,dpmaif`, `ap_ccif*`, CCCI | **No** (begonia attempt fails at RF init) |
| SAR (mostly J706X) | Semtech SX933x/SX9328, ABOV, or Awinic AW9610x (stock kernel) | I2C | `sx933x`, `abov,abov_sar`, `awinic,aw9160x_sar` | AW96103/AW96105 yes (`aw96103.c`, if the fitted part is one of these); SX933x and ABOV no |
| PMIC | MediaTek MT6359P (stock kernel `mt6359p`) | PWRAP (SPI-like) | `mediatek,mt6359-pmic`, `-regulator`, `-rtc`, `-auxadc` | Yes: `mt6359-regulator.c` (MT6359P), `mt6397-core` (`mediatek,mt6359`), `mt6359-auxadc.c`, `rtc-mt6397.c` |
| Fuel gauge | MT6359 built-in coulomb counter, GM3.0 (stock DTB) | PWRAP | `mediatek,mt6359_gauge`, `mediatek,bat_gm30` | **No**. **Community**: begonia FGADC patches |
| Sub-PMIC / charger / Type-C | MediaTek MT6360 (charger, LDOs, flash LED, RGB LED, ADC, TCPC) (stock DTB) | I2C | `mediatek,mt6360_pmu_*`, `mt6360pd` TCPC, `rt-pd-manager` | Yes: `mt6360-core`, `mt6360_charger`, `mt6360-regulator`, `leds-mt6360` (flash), `tcpci_mt6360` |
| 2nd charger | RT9465 placeholder only (stock DTB); no driver in the kernel | I2C | `richtek,rt9465` | No (probably not fitted) |
| Battery | 7500/7700 mAh Li-Po, FRU likely L20D2P31 (PSREF; aftermarket) | — | — | n/a |
| USB | MT6785 SSUSB (MTU3 + xHCI), port is USB-C **2.0** (PSREF); no DP or HDMI block (stock DTB) | USB 2.0 | `mediatek,mt6785-mtu3`, `mediatek,mt67xx-xhci` | `mtu3`, `xhci-mtk`, T-PHY yes; MT6785 compatibles: community. DP alt mode: hardware absent |
| Audio AFE / codec | MT6785 AFE + MT6359 codec (stock DTB `mediatek,mt6785-mt6359-sound`) | internal + PWRAP | `mediatek,mt6785-sound`, `mediatek,mt6359-sound` | Codec yes (`mt6359.c`); AFE **no**. **Community**: begonia `sound/soc/mediatek/mt6785` |
| Speaker amps (4 speakers) | Cirrus Logic CS35L41, count unknown (stock kernel) | I2C control + I2S/TDM | `cirrus,cs35l41` (with `.wmfw`/`.bin` firmware) | **Yes**: `cs35l41.c` / `cs35l41-i2c.c` |
| Voice DSP / mics | Synaptics AudioSmart AS33970; dual mics (PSREF "low-power DSP for far-field") | I2C + I2S | `syna,as33970` | **No** |
| Headphone jack | None (reviews) | — | MT6359 ACCDET present but SoC-generic | n/a |
| Accel / gyro / ALS | Chips unknown, behind the SCP sensor hub (stock kernel `accelhub`, `gyrohub`, `alspshub`) | SCP I2C (probably) | SCP firmware + `SCP_sensorHub` | **No** SCP hub; individual chip drivers depend on which part is fitted |
| ToF (front) | Unknown (PSREF lists it) | I2C (probably) | not in kernel (vendor module or SCP?) | Unknown |
| Cameras | 8 MP rear AF + 8 MP front FF (PSREF); S5K4H7 (3 variants) or OV8856 (stock kernel) | MIPI CSI-2 + I2C | MediaTek imgsensor `s5k4h7*_mipi_raw`, `ov8856_mipi_raw` | OV8856 **yes** (`ov8856.c`); S5K4H7 no; MT6785 ISP/seninf **no** |
| Flash LED | MT6360 FLED (stock DTB); PSREF lists no flash | I2C | `mediatek,flashlights_mt6360` | `leds-mt6360.c` yes |
| Vibrator | ERM (PSREF), MT6359 `vibr` LDO (stock kernel `vibrator_drv`) | PMIC LDO | `vibrator_drv` | `regulator-haptic` (generic) yes |
| Keys | Power (MT6359 PWRKEY) and volume (`mediatek,kp`) (stock DTB/PSREF) | PMIC / keypad / GPIO | `mediatek,kp` | `mtk-pmic-keys` yes; MT6785 keypad: community `mediatek,mt6785-keypad` |
| Keyboard / pogo | None for this model; pogo code inactive (stock kernel "Not support pogo keyboard") | — | `lq_keyboard` | n/a (Bluetooth keyboards via BlueZ) |

### Inferences
- **Tier 1 (already done on the sibling device, "port + DT" work):** boot to a framebuffer or console over USB, UFS root, the PMIC rails, charging and Type-C, the GPU, the CS35L41 speakers after the AFE, and Wi-Fi/BT via the begonia staging drivers.
- **Tier 2 (new driver work):** SPI touch (NT36523W + WGP pen; or Himax), the backlight IC driver (KTZ8864A or SGM37604A; small I2C drivers), the AS33970 microphone path, and the fuel gauge (community patch).
- **Tier 3 (very hard or out of scope):** the SCP sensor hub (rotation), the cameras/ISP, the ToF sensor and the LTE modem.

### Gaps
- Every "unknown" row above is settled by the board dtbo plus the I2C/SPI device listing, as detailed in the next section.

## Unknowns that need the tablet in hand, with the command that settles each one

### Takeaway
Most open questions collapse into one action: **dump the `dtbo` partition (or extract `dtbo.img` from a stock ROM package) and decompile it**, then list the I2C/SPI devices and firmware files on stock Android. No source covering bootloader-unlock policy was found within this research's scope.

### Cited Findings
- **Partition names** that the commands below rely on (A/B `boot`, `dtbo`, `vbmeta`, `vendor` logical, `nvram`, `lenovocust`) — [recovery.fstab](https://github.com/jeremywildsmith/android_device_lenovo_yoga11/blob/HEAD/recovery.fstab)
- **Stock firmware packages** for the YT-J706F are hosted by a third-party site, with MT6785 in the file names (not verified; untrusted source) — [firmwarefile.com](https://firmwarefile.com/lenovo-yoga-tab-11-yt-j706f)

### Inferences
Exact commands, in order of value. `adb shell` works on a stock user build; `su -c` needs root.

1. **Board DT (settles the touch/panel, backlight, amplifier count, AS33970 wiring, sensors, ToF, SAR, GPIOs):**
   - `adb shell su -c 'dd if=/dev/block/by-name/dtbo_a of=/sdcard/dtbo_a.img'`, then `adb pull`, `mkdtboimg.py dump dtbo_a.img -b dt`, and `dtc -I dtb -O dts dt.0`.
   - Without root: unpack `dtbo.img` from the stock ROM package.
   - Also `adb shell su -c 'cat /sys/firmware/fdt' > live.dtb` (live merged tree).
2. **Fitted I2C/SPI parts:**
   - `adb shell 'for d in /sys/bus/i2c/devices/*; do echo $d $(cat $d/name 2>/dev/null); done'`
   - `adb shell 'for d in /sys/bus/spi/devices/*; do echo $d $(cat $d/modalias); done'`
   - `adb shell ls /sys/bus/i2c/drivers /sys/bus/spi/drivers`
3. **Panel and touch variant:**
   - `adb shell cat /proc/device-tree/chosen/atag,videolfb-lcmname`
   - `adb shell getevent -lp` (touch device name; BTN_TOOL_PEN / ABS_PRESSURE for the pen)
   - `adb shell su -c 'dmesg | grep -iE "TP info|lcm|ktz8864|sgm37604|ocp2138|cs35l41|as33970"'`
4. **Firmware and modules:**
   - `adb shell ls -l /vendor/firmware /vendor/etc/firmware 2>/dev/null` (WIFI_RAM_CODE_soc1_0_*, *_hdr.bin, cs35l41*.wmfw/.bin, novatek/himax fw, AS33970 fw)
   - `adb shell lsmod`, `adb shell ls /vendor/lib/modules`
   - `adb shell getprop | grep -iE "connsys|wlan|wifi|platform|hardware|lcm|tp"`
5. **SoC and memory:**
   - `adb shell getprop ro.board.platform; getprop ro.hardware; cat /proc/cpuinfo; cat /proc/meminfo`
   - `adb shell cat /sys/devices/system/cpu/cpu*/cpufreq/cpuinfo_max_freq`
   - `adb shell cat /sys/block/sda/device/{vendor,model,rev}` (UFS vendor)
6. **Sensors and cameras:**
   - `adb shell dumpsys sensorservice | head -80`
   - `adb shell dumpsys media.camera | grep -iE "sensor|facing|orientation"`
   - `adb shell su -c 'cat /proc/driver/camera_info'`
7. **Audio:** `adb shell cat /proc/asound/cards /proc/asound/pcm`; `adb shell su -c tinymix`.
8. **USB and power:**
   - `adb shell dumpsys usb`; `adb shell ls /sys/class/typec`
   - `adb shell cat /sys/bus/usb/devices/*/speed` (with a USB 3 device on OTG)
   - `adb shell dumpsys battery`; `adb shell cat /sys/class/power_supply/*/uevent`
9. **Wi-Fi spatial streams and GNSS:** `adb shell dumpsys wifi | grep -iE "nss|spatial|antenna"`; `adb shell dumpsys location | grep -i gnss`.
10. **Boot chain and unlockability (gates the whole port):**
    - `adb reboot bootloader`, then `fastboot getvar all` (unlocked state, slot, partition sizes).
    - `fastboot flashing get_unlock_ability`.
    - `adb shell getprop ro.boot.verifiedbootstate`.

### Gaps
- None of these commands has been run; every result above is pending hardware access.
- This research did not check whether Lenovo permits bootloader unlocking on the YT-J706F; that is out of this researcher's scope.
