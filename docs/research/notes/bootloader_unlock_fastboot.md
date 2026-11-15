# Lenovo Yoga Tab 11 (YT-J706F / YT-J706X): boot chain, unlock, fastboot, verified boot, partitions, community

Research date: 2026-11-15. Scope: can a Mac host load and flash custom kernels on the YT-J706F over USB-C, reliably and without key presses?

Access notes, so the writer can weigh the evidence:
- XDA (xdaforums.com) and 4PDA both returned HTTP 403 to the fetch tool. Archive mirrors were not used. Everything attributed to XDA below comes from search-engine summaries of the thread, not from reading it. Treat it as forum claims of moderate reliability.
- The strongest evidence is primary material read directly: GitHub device and kernel trees, the stock kernel and DTB binaries from one of those trees (inspected locally with `strings` and `dtc`), the mtkclient and kaeru source trees, and Lenovo PSREF.
- **Name collision warning:** "TB-J706F" is the **Lenovo Tab P11 Pro**, a Qualcomm SM7150 (Snapdragon 730G) tablet. Many hits for "J706F" (TWRP builds, the phhusson wiki entry, firmware repos) are for the P11 Pro and **do not apply** to the YT-J706F. Example: [thka2016/lenovo-j706f-firmware](https://github.com/thka2016/lenovo-j706f-firmware) contains an `sm7150` folder, and [HK4567/twrp_device_lenovo_TB-J706F](https://github.com/HK4567/twrp_device_lenovo_TB-J706F) is described as "Lenovo Tab P11 Pro, 小新Pad Pro 2020".

## Boot chain, firmware versions, kernel and boot image format

### Takeaway
The YT-J706F is a MediaTek MT6785-family tablet: MT8185-branded on Wi-Fi, MT8789 on LTE. Lenovo's GPL config enables the Microtrust TEE and MediaTek GenieZone. It launched on Android 11, was upgraded to Android 12, and the last known build is `YT-J706F_S240301_240918_ROW`. That build ships a Linux 4.14.186 kernel (built 18 Sep 2024) as a gzip-compressed Image, in a **boot image header v2** with the SoC DTB inside the boot image and the board DTB overlay in a separate `dtbo` partition.

### Cited Findings
- **SoC naming.** Lenovo PSREF (spec last modified 2023-05-26) lists the processor as MediaTek Helio G90T: "M8185" on the Wi-Fi model and MT8789 on the LTE model. It is octa-core (2× A76 @ 2.05 GHz + 6× A55 @ 2.0 GHz) with LPDDR4x 4/8 GB and **UFS 2.1** storage (64/128/256 GB), a microSD slot, and **one USB-C 2.0 port** (no DisplayPort mentioned). OS: "Android 11 or later". The upgrade promise is only the generic "typically at least one Android OS upgrade cycle" — [Lenovo PSREF Yoga Tab 11 spec](https://psref.lenovo.com/syspool/Sys/PDF/Lenovo_Tablets/Yoga_Tab_11/Yoga_Tab_11_Spec.html)
- **Lenovo's GPL kernel.** Lenovo's kernel source for the device, re-hosted on 2026-08-06 for a postmarketOS port, describes the tablet as "MT6785/MT8789". The stock kernel was built with Clang r383902 plus GCC 4.9.1 binutils, confirmed via `/proc/version` on a stock boot — [JeremyWildsmith/lenovo-yt-j706f-toolchain README (2026-08-06)](https://github.com/JeremyWildsmith/lenovo-yt-j706f-toolchain)
- **Kernel version.** The kernel tree's Makefile is 4.14.186. The tree has `arch/arm64/configs/yoga11_defconfig`, `yoga11_lte_defconfig` (the YT-J706X variant), and DTS overlays `yoga11.dts` and `yoga11_lte.dts` — [JeremyWildsmith/lenovo-yt-j706f-kernel (2026-08-06)](https://github.com/JeremyWildsmith/lenovo-yt-j706f-kernel)
- **What `yoga11_defconfig` sets** — [yoga11_defconfig](https://github.com/JeremyWildsmith/lenovo-yt-j706f-kernel/blob/main/arch/arm64/configs/yoga11_defconfig):
  - TEE and hypervisor: `CONFIG_MICROTRUST_TEE_SUPPORT=y`, `CONFIG_MTK_TEE_GP_SUPPORT=y`, `CONFIG_MTK_ENABLE_GENIEZONE=y`.
  - Platform and project: `CONFIG_MTK_PLATFORM="mt6785"`, `CONFIG_ARCH_MTK_PROJECT="tb8185p3_64"`, `CONFIG_MTK_AB_OTA_UPDATER=y`.
  - DTB: `CONFIG_BUILD_ARM64_APPENDED_DTB_IMAGE_NAMES="mediatek/mt6785"`.
  - Storage: `CONFIG_MTK_UFS_SUPPORT=y` plus eMMC drivers.
  - Coprocessors: SSPM and SCP tinysys enabled.
  - Panels: `CONFIG_CUSTOM_KERNEL_LCM="hx83102p_fhdp_dsi_vdo_boe nt36523w_fhdp_dsi_vdo_boe"`, 1200×2000, rotation 180.
  - USB gadget: `CONFIG_USB_CONFIGFS_RNDIS`, `ACM` and `MASS_STORAGE` are built in.
- **Overlay vs base DTB.** `yoga11.dts` starts with `/dts-v1/; /plugin/;`, so it is a DT overlay meant for the `dtbo` partition. The SoC base DTB is built as `mediatek/mt6785` — [yoga11.dts](https://github.com/JeremyWildsmith/lenovo-yt-j706f-kernel/blob/main/arch/arm64/boot/dts/mediatek/yoga11.dts)
- **Latest stock build.** A TWRP-generator device tree (2024-12-10) built from stock firmware records the fingerprint `Lenovo/YT-J706F/YT-J706F:12/SP1A.210812.016/YT-J706F_S240301_240918_ROW:user/release-keys`. That is Android 12, ROW build S240301, dated 2024-09-18 — [jeremywildsmith/android_device_lenovo_yoga11 omni_yoga11.mk](https://github.com/jeremywildsmith/android_device_lenovo_yoga11/blob/master/omni_yoga11.mk)
- **Stock kernel binary, inspected locally.** `prebuilt/kernel` from that tree is gzip-compressed (10.1 MB, 28.6 MB uncompressed). Its banner is `Linux version 4.14.186-g59da9ac88f6c (nobody@android-build) (Android (6443078 based on r383902) clang version 11.0.1 ...) #1 SMP PREEMPT Wed Sep 18 18:30:11 CST 2024` — [prebuilt/kernel](https://github.com/jeremywildsmith/android_device_lenovo_yoga11/tree/master/prebuilt)
- **Stock DTB, inspected locally.**
  - `prebuilt/dtb.img` starts with magic `d7b7ab1e` (Android DT-table format) and holds one FDT of 139,089 bytes: `model = "MT6785"`, `compatible = "mediatek,MT6785"`.
  - Its chosen bootargs: `console=tty0 console=ttyS0,921600n1 root=/dev/ram vmalloc=400M ... firmware_class.path=/vendor/firmware ... loop.max_part=7`.
  - It has nodes `ufshci@11270000` (`mediatek,ufshci`) and `mmc@11230000`.
  - TEE nodes: both `trustonic,mobicore` and `microtrust,utos` (the common MTK base DTB carries both), plus GenieZone and Trusty nodes (`mediatek,trusty-gz`, `mediatek,trusty-mtee-v1`, a "nebula" TEE id).
  - Source: [prebuilt/dtb.img](https://github.com/jeremywildsmith/android_device_lenovo_yoga11/tree/master/prebuilt)
- **Boot image parameters**, from the stock boot.img as recorded by the generator — [BoardConfig.mk](https://github.com/jeremywildsmith/android_device_lenovo_yoga11/blob/master/BoardConfig.mk):
  - Header and layout: `BOARD_BOOTIMG_HEADER_VERSION := 2`, `BOARD_KERNEL_PAGESIZE := 2048`, `BOARD_KERNEL_BASE := 0x40078000`, `BOARD_RAMDISK_OFFSET := 0x07c08000`, `BOARD_KERNEL_TAGS_OFFSET := 0x0bc08000`.
  - Command line: `BOARD_KERNEL_CMDLINE := bootopt=64S3,32N2,64N2 buildvariant=user`.
  - DTB passed with `--dtb`.
  - Recovery: `BOARD_USES_RECOVERY_AS_BOOT := true`.
  - Platform: `TARGET_BOARD_PLATFORM := mt6785`.
- **Recovery init scripts.** The stock recovery ramdisk ships both `init.recovery.mt6785.rc` and `init.recovery.mt8185.rc` — [recovery/root](https://github.com/jeremywildsmith/android_device_lenovo_yoga11/tree/master/recovery/root)
- **Support end date (third-party).** A third-party summary of Lenovo's update timeline lists the YT-J706F as Android 11 at launch with an Android 12 upgrade. It gives security maintenance end dates of 2024-04-30 for YT-J706F and 2024-05-30 for YT-J706X, and lists no Android 13 — [mynexttablet.com (third-party summary, date not shown)](https://mynexttablet.com/?p=14434). This partly conflicts with the 2024-09-18 build date above.
- **Stock firmware listings.** A firmware mirror lists `Lenovo_Yoga_Tab_11_YT-J706F_MT6785_S240301_240918_ROW.zip` among YT-J706F SP Flash Tool packages — [firmwarefile.com (fetch blocked, search summary only)](https://firmwarefile.com/lenovo-yoga-tab-11-yt-j706f)

### Inferences
- **Boot chain**, assembled from the partition names below and the configs above:
  1. BROM (mask ROM, hwcode 0x813 per mtkclient)
  2. preloader, in the UFS boot LUN
  3. TF-A/ATF plus the TEE (Microtrust) from `tee1`/`tee2`
  4. GenieZone hypervisor from `gz1`/`gz2`
  5. LK from `lk`/`lk2`
  6. Linux 4.14 from `boot`

  The exact layering of ATF, GenieZone and TEE comes from MTK convention, not a Yoga-specific document.
- **TEE.** Answer: **Microtrust**, not Trustonic Kinibi. Only `CONFIG_MICROTRUST_TEE_SUPPORT` is set; the Trustonic node in the DTB is boilerplate from the shared MT6785 base DTB. Whether Microtrust's TEE here is the product the community calls "isee/Beanpod" was not verified.
- **No `vendor_boot`.** With header v2 on Android 11/12 there is none; a `vendor_boot` partition needs header v3+. The ramdisk is the full recovery-as-boot ramdisk.
- **Where the DTB lives.** The SoC DTB sits in the boot image's v2 DTB section, wrapped in a DT table. Board specifics (panel, touch, etc.) are applied by LK from `dtbo` as overlays.
- **Consequence for Linux.** A custom kernel needs either:
  - a boot.img that carries a DTB LK accepts, while LK still merges `dtbo`; or
  - a full board DTB, with `dtbo` neutralised.

  This is the same overlay problem pmOS ports of other MTK devices handle.
- **Debug console over USB.** UART is `ttyS0`/`ttyMT3` at 921600 baud on 0x11002000. With only USB-C 2.0 and no serial, early boot debugging must rely on:
  - pstore/ramoops;
  - the on-screen framebuffer console (the pmOS port enabled `CONFIG_VT`/`FRAMEBUFFER_CONSOLE` for exactly this);
  - USB gadget networking once the kernel is up.

### Gaps
- Was there an Android 13 build, or any build after S240301_240918? None was found. Settle with `adb shell getprop ro.build.display.id; getprop ro.build.version.release; getprop ro.build.version.security_patch` and an LMSA "Rescue" check.
- Which TEE is actually loaded at runtime? Settle with `adb shell ls /dev | grep -i -E "teei|isee|tee|mobicore"` and `adb shell getprop | grep -i -E "tee|microtrust|trustonic"`.
- Is LK 32-bit ARMv7? This matters for kaeru. Dump `lk` (`fastboot fetch` isn't available, so use mtkclient `python mtk.py r lk lk.img`) and inspect it.
- Does the LTE YT-J706X differ in boot chain? Only the `yoga11_lte` defconfig and DTS were seen; no YT-J706X firmware fingerprint was found.

## Bootloader unlock on YT-J706F

### Takeaway
Official-path unlock appears to be standard Android: enable "OEM unlocking" in Developer options, reboot to the LK fastboot, run `fastboot flashing unlock`. It wipes data. It is reported by XDA users who then rooted with Magisk, but no primary log (getvar output, unlock screen photo) was found, and no source documents behaviour across OTAs or PRC-versus-ROW differences. A second, OEM-independent path exists: MT6785 is a "confirmed" mtkclient target, so `mtk.py da seccfg unlock` can flip the seccfg lock state over BROM USB.

### Cited Findings
- **XDA root guide procedure.** The "[Root Guide] YT-J706F Lenovo Yoga Tab 11" thread, as summarized by the search engine:
  1. Get stock boot.img from Lenovo Rescue and Smart Assistant (LMSA).
  2. Unlock the bootloader. Some posts run `fastboot flashing unlock`; unlocking erases all data.
  3. Enter fastboot by holding **Vol− + Power** "until the fastboot mode text appears".
  4. Flash the Magisk-patched boot.
  5. Flash vbmeta with `--disable-verity --disable-verification`.
  - Magisk v24.3 is recommended; a bootloop after Magisk was fixed by flashing vbmeta or reflashing the stock boot.
  - Some users' older fastboot binaries rejected the `--disable-*` flags as an "unknown option".
  - Thread date not retrieved; its ID 4463519 suggests mid-2022, so Android 11/12-era firmware.
  - Source: [XDA thread 4463519 (search summary; fetch blocked)](https://xdaforums.com/t/root-guide-yt-j706f-lenovo-yoga-tab-11.4463519/)
- **Third-party guide (low quality).** A 2021 guide says the YT-J706F/J706X ship locked, the unlock wipes data, and lists `fastboot devices`, `fastboot flash unlock <file>.img`, `fastboot oem unlock-go`. That is the Lenovo ZUI/PRC unlock-file template and is not corroborated for this model — [GetDroidTips (2021)](https://www.getdroidtips.com/lenovo-yoga-tab-11-unlock-bootloader-guide/)
- **Same-SoC sibling (TB-J616F), forum claim.** On the Tab P11 Plus (TB-J616F, also Helio G90T), one XDA user reports that `fastboot flashing unlock` failed with "unknown status code" despite reflashing firmware. The device reached **fastbootd** from recovery. A reply says a recent security OTA blocked using an older firmware package — [XDA post 88345909 (search summary)](https://forum.xda-developers.com/t/can-the-p11-plus-be-rooted.4452917/post-88345909)
- **mtkclient support for MT6785.**
  - `brom_config.py` has `0x813: Chipconfig(var1=0xA, # confirmed ... damode=DAmodes.XFLASH, dacode=0x6785, name="MT6785", description="Helio G90", loader="mt6785_payload.bin")`, and `mt6785_payload.bin` ships in the payload folder.
  - MT6785 is **not** in the README's list of V6 chips whose bootrom is patched.
  - Repo state: last commit 2026-10-26.
  - Source: [bkerler/mtkclient brom_config.py](https://github.com/bkerler/mtkclient/blob/main/mtkclient/config/brom_config.py)
- **mtkclient unlock flow** for "stock mtk with android >=9": `python mtk.py da seccfg unlock`, then `python mtk.py e userdata,metadata,md_udc,cache`, then `python mtk.py da vbmeta 3` (disable verity and verification). Relock with `da seccfg lock`. After unlocking, "the device should boot and show a yellow warning about unlocked bootloader and then the device should boot within 5 seconds" (generic MTK statement) — [mtkclient README-USAGE.md](https://github.com/bkerler/mtkclient/blob/main/README-USAGE.md)
- **BROM entry.** BROM mode is entered by powering off and holding Vol+ + Power or Vol− + Power while connecting USB. `python mtk.py crash` crashes a running DA or preloader into BROM. macOS, including Apple Silicon, has install instructions — [mtkclient README.md](https://github.com/bkerler/mtkclient/blob/main/README.md); [README-INSTALL.md](https://github.com/bkerler/mtkclient/blob/main/README-INSTALL.md)
- **Unlock and Widevine.** One XDA thread warns that unlocking wipes the device and drops Widevine to L3. The thread is a generic "Bootloader Unlock? Root? Custom ROM?" question, and which Lenovo model it covers is not confirmed — [XDA thread 4230987 (search summary)](https://xdaforums.com/t/bootloader-unlock-root-custom-rom.4230987/)

### Inferences
- **Proof that unlock works on stock firmware.** The postmarketOS port (next sections) shows a custom 4.14 kernel booting on a YT-J706F in 2026 on the S240301-era firmware. A custom kernel cannot boot unless the bootloader is unlocked (or seccfg is unlocked via mtkclient), so unlock is achievable on current firmware.
- **The unlock confirmation needs a person.** MTK LK normally asks for a volume-key confirmation on `fastboot flashing unlock`, so this one-time step needs a human. The mtkclient seccfg route avoids the on-screen prompt but needs BROM entry, which means keys plus cable unless `crash` from preloader works.
- **Keyless BROM is plausible but unproven.** MTK preloaders usually enumerate on USB (VID 0e8d) for a moment at every boot. mtkclient can catch that window and `crash` into BROM, which would give a host-only recovery path. Whether Lenovo's preloader exposes that window on this device is unverified.

### Gaps
- No `fastboot getvar all` output for YT-J706F was found anywhere. Settle with `fastboot getvar all 2>&1 | tee getvar.txt`. Look for `unlocked`, `secure`, `slot-count`, `current-slot`, `max-download-size`, `version-bootloader`, `is-userspace`, and the `partition-size:*` lines.
- Unlock ability and behaviour:
  - Is the `get_unlock_ability` gate honoured? Run `fastboot flashing get_unlock_ability`.
  - Does `fastboot flashing unlock` or `fastboot oem unlock` work? Test both and record the on-screen prompt.
  - Does unlock survive an OTA? Check `adb shell getprop ro.boot.flash.locked` and `getprop ro.boot.verifiedbootstate` before and after an OTA.
  - Is the toggle allowed? Check `getprop sys.oem_unlock_allowed` and `getprop ro.oem_unlock_supported`.
- Did any OTA disable unlocking? The only hint is a TB-J616F report, a sibling device.
- Is there a PRC variant of the YT-J706F with the ZUI unlock-file process? Not found.
- Does the YT-J706F have SLA/DAA enabled, and does mtkclient's MT6785 exploit work on its production lot? Settle with `python mtk.py gettargetconfig` in BROM (prints SBC/SLA/DAA), then `python mtk.py printgpt`.

## Fastboot capabilities of the device's LK

### Takeaway
No YT-J706F-specific fastboot command list or `getvar` dump was found. MediaTek's reference LK registers `boot` (RAM boot) as allowed on secure devices but **forbidden while locked**, so `fastboot boot <img>` should work once unlocked unless Lenovo removed it. This is the single most important item to test on day one. Android 11-launch dynamic partitions mean userspace fastbootd must exist for logical partitions, while `boot`/`dtbo`/`vbmeta`/`lk` are flashed from LK.

### Cited Findings
- **MTK reference LK command table.**
  - Signature: `fastboot_register(prefix, handle, allowed_when_security_on, forbidden_when_lock_on)`.
  - Registrations include:
    - `fastboot_register("boot", cmd_boot, TRUE, TRUE)`
    - `fastboot_register("flash:", cmd_flash_mmc, TRUE, TRUE)`
    - `fastboot_register("erase:", ..., TRUE, TRUE)`
    - `fastboot_register("getvar:", cmd_getvar, TRUE, FALSE)`
    - `fastboot_register("reboot", ...)`
    - `fastboot_register("reboot-bootloader", ...)`
    - `fastboot_register("continue", cmd_continue, FALSE, FALSE)`
    - `fastboot_register("oem append-cmdline", ..., FALSE, FALSE)`
    - `oem unlock`, `oem lock`, `oem lks`, `oem p2u`, `oem reboot-recovery`, `oem off-mode-charge`
  - This is an older MTK LK (Gemini PDA, MT6797), not the YT-J706F's LK — [dguidipc/gemini-lk app/mt_boot/fastboot.c](https://github.com/dguidipc/gemini-lk/blob/master/lk/app/mt_boot/fastboot.c)
- **Entry from power-off.** Hold Vol− + Power — [XDA thread 4463519 (search summary)](https://xdaforums.com/t/root-guide-yt-j706f-lenovo-yoga-tab-11.4463519/). The generic Lenovo-tablet route from Android is `adb reboot bootloader` — [XDA post 88345909 (search summary)](https://forum.xda-developers.com/t/can-the-p11-plus-be-rooted.4452917/post-88345909)
- **Kernel-side reboot hooks.** The stock defconfig enables `CONFIG_ONEKEY_REBOOT_NORMAL_MODE=y` and `CONFIG_ONEKEY_REBOOT_OTHER_MODE=y`. These are MTK long-press reboot hooks — [yoga11_defconfig](https://github.com/JeremyWildsmith/lenovo-yt-j706f-kernel/blob/main/arch/arm64/configs/yoga11_defconfig)
- **mtkclient payload boot.** mtkclient can boot a device into a chosen mode through a payload (`python mtk.py payload --metamode FASTBOOT`) — [mtkclient README-USAGE.md](https://github.com/bkerler/mtkclient/blob/main/README-USAGE.md)
- **kaeru LK patcher.** kaeru ("ARMv7 payload that provides arbitrary code execution on MediaTek bootloaders (LK)", repo active 2026-11-12) patches an LK image to:
  - add custom fastboot commands;
  - remap key combinations / boot modes;
  - remove the unlocked-bootloader warning.

  Offsets are per-device and per-LK-version. The only Lenovo board in the tree is the Tab M10 HD 2nd Gen (`board-amar_row_lte.c`); there is no YT-J706F port — [R0rt1z2/kaeru](https://github.com/R0rt1z2/kaeru)

### Inferences
- **Inner dev loop over `fastboot boot`.** If `fastboot boot` survives in Lenovo's LK, a Mac can RAM-boot test kernels with nothing flashed, a cleaner inner loop than the Tab S2's heimdall flashing.
  - Path in: `adb reboot bootloader` from a running Linux or Android, or a `reboot bootloader` syscall from Linux.
  - After the test: `fastboot reboot` returns to the installed system.
  - Requires: the kernel's reboot handler must write the MTK boot-mode magic so LK enters fastboot. The stock 4.14 MTK kernel supports `reboot bootloader`.
- **Patch LK if `boot` was removed.** If Lenovo stripped `fastboot boot`, kaeru (patched `lk`) is the established way to add it back or add `oem` commands. It is risky: a bad `lk` needs BROM recovery via mtkclient or SP Flash Tool.
- **Recovery mode on A/B.** `fastboot reboot recovery` on an A/B recovery-as-boot device boots the same `boot` slot with a recovery flag. There is no separate RECOVERY partition, unlike the Tab S2.

### Gaps
- Is `fastboot boot` supported, and with what size limit? Test while unlocked: `fastboot boot test.img`, starting with the stock boot.img repacked unchanged. Check `fastboot getvar max-download-size`.
- What OEM commands exist? Run `fastboot oem help` (MTK LK may not implement it), `fastboot oem lks`, `fastboot oem p2u`, `fastboot oem off-mode-charge 0`, `fastboot oem append-cmdline "x=1"`. Each answers "unknown command" or not.
- Is there a userspace fastbootd? Run `fastboot reboot fastboot` then `fastboot getvar is-userspace`.
- Do the mode reboots work? Run `fastboot reboot`, `fastboot reboot recovery`, `fastboot reboot bootloader`, and `adb reboot bootloader` from Android.
- Can partitions be read back? Run `fastboot fetch boot_a boot_a.img`; MTK LK likely lacks it.
- What is the exact key combination from power-off for fastboot, recovery and BROM on this model? Only Vol− + Power for fastboot is reported, and only in a search summary.

## Verified boot (AVB 2.0)

### Takeaway
The device uses AVB 2.0 with chained `vbmeta`, `vbmeta_system` and `vbmeta_vendor`. Community roots flash vbmeta with `--disable-verity --disable-verification` (flags=3) after unlock. That, together with a 2026 postmarketOS kernel booting, shows that unlocked LK does not reject a non-Lenovo-signed boot image once vbmeta verification is disabled. Size limit: the boot partition is reported as 32 MiB.

### Cited Findings
- **AVB in the generated tree.** `BOARD_AVB_ENABLE := true` and `BOARD_AVB_MAKE_VBMETA_IMAGE_ARGS += --flags 3`, which is a TWRP-generator default and not a stock value. The fstab lists `/vbmeta`, plus `/vbmeta_system` and `/vbmeta_vendor` (both `slotselect`) — [BoardConfig.mk](https://github.com/jeremywildsmith/android_device_lenovo_yoga11/blob/master/BoardConfig.mk); [recovery.fstab](https://github.com/jeremywildsmith/android_device_lenovo_yoga11/blob/master/recovery.fstab)
- **Community vbmeta step.** XDA root guide: flash the patched boot, then `vbmeta` with `--disable-verity --disable-verification`. Boot loops after Magisk were fixed by flashing vbmeta — [XDA thread 4463519 (search summary)](https://xdaforums.com/t/root-guide-yt-j706f-lenovo-yoga-tab-11.4463519/)
- **mtkclient equivalent.** `python mtk.py da vbmeta 3` disables verity and verification. After an unlock on Android 11, "if you are getting a dm-verity error ... just press the power button", which is a key press on the verity error screen — [mtkclient README-USAGE.md](https://github.com/bkerler/mtkclient/blob/main/README-USAGE.md)
- **Boot partition size.** `BOARD_BOOTIMAGE_PARTITION_SIZE := 33554432` (32 MiB). The stock gzip kernel is 10.1 MB and the DTB 139 KB — [BoardConfig.mk](https://github.com/jeremywildsmith/android_device_lenovo_yoga11/blob/master/BoardConfig.mk); [prebuilt](https://github.com/jeremywildsmith/android_device_lenovo_yoga11/tree/master/prebuilt)
- **Stock kernel verity settings.** The defconfig enables `CONFIG_BLK_DEV_DM` and `CONFIG_DM_VERITY_FEC` — [yoga11_defconfig](https://github.com/JeremyWildsmith/lenovo-yt-j706f-kernel/blob/main/arch/arm64/configs/yoga11_defconfig)
- **Postmarketos port shows custom kernels boot.** The port's commits fix a "post-splash bootloop" (LCM driver name mismatch), disable SSPM "to avoid a boot hang on postmarketOS", and enable an on-screen VT console. That is iterative custom-kernel booting on the real device — [JeremyWildsmith/lenovo-yt-j706f-kernel commits (2026-08-06)](https://github.com/JeremyWildsmith/lenovo-yt-j706f-kernel/commits/main)

### Inferences
- **Orange state.** With an unlocked LK, MTK devices show an "orange state" warning screen and continue after a delay (typically ~5 s), with no key press needed. The mtkclient README describes the same "boot within 5 seconds" behaviour generically. Unattended boot loops therefore stay possible, with a ~5 s penalty per boot. kaeru can remove the screen.
- **Size ceiling.** 32 MiB for kernel + ramdisk + DTB is enough for a 4.14 Image.gz plus a small initramfs. A large Arch initramfs (Plymouth, firmware) may need trimming; on the Tab S2 the BOOT partition was the constraint too.
- **Header v2 kernel limit.** Header v2 has no separate kernel size limit beyond the partition. The download buffer (`max-download-size`) limits `fastboot boot`.

### Gaps
- Does LK still verify `boot` when vbmeta flags=3 but the device is locked? Expected no boot, not tested.
- Does the unlocked LK need vbmeta flags at all to boot an unsigned boot.img (orange state usually allows it)? Test `fastboot boot unsigned.img` with stock vbmeta.
- Check the boot-state properties:
  - `adb shell getprop ro.boot.verifiedbootstate` (expect green, then orange);
  - `getprop ro.boot.vbmeta.device_state`;
  - `getprop ro.boot.veritymode`.
- Check the orange-state screen and its delay: photograph the screen and time it.
- Anti-rollback: does LK enforce a rollback index from vbmeta, and could flashing an older stock build brick? Inspect with `avbtool info_image --image vbmeta.img` on the stock image (Rollback Index field).
- Run `avbtool info_image` on the stock `vbmeta`, `vbmeta_system` and `vbmeta_vendor` to see which partitions are chained or hashed. Only the S240301 LMSA package was identified as a source.

## Partition table

### Takeaway
The YT-J706F uses **A/B with dynamic partitions** (a `super` holding system, vendor and product per slot) on UFS 2.1, with **no recovery partition**: recovery is in `boot`. It also has MTK legacy dual-copy firmware partitions (`lk`/`lk2`, `tee1`/`tee2`, `gz1`/`gz2`, etc.) and a `dtbo` partition. No spare partition was identified as obviously free for a second (rescue) Linux. On the Tab S2 the rescue lived in RECOVERY; here the other A/B slot (`boot_b`) is the natural candidate.

### Cited Findings
- **A/B and dynamic partitions.**
  - `AB_OTA_UPDATER := true`, with OTA partitions system, product, vendor, vbmeta_system, vbmeta_vendor and boot.
  - `BOARD_USES_RECOVERY_AS_BOOT := true`.
  - `BOARD_SUPER_PARTITION_SIZE := 9126805504` (marked "TODO: Fix hardcoded value"); the group `lenovo_dynamic_partitions` holds system, vendor and product, size 9122611200.
  - `BOARD_BOOTIMAGE_PARTITION_SIZE := 33554432`.
  - Source: [BoardConfig.mk](https://github.com/jeremywildsmith/android_device_lenovo_yoga11/blob/master/BoardConfig.mk)
- **A/B in packages and kernel.** `device.mk` includes `bootctrl.mt6785` and `update_engine` — [device.mk](https://github.com/jeremywildsmith/android_device_lenovo_yoga11/blob/master/device.mk). The kernel has `CONFIG_MTK_AB_OTA_UPDATER=y` — [yoga11_defconfig](https://github.com/JeremyWildsmith/lenovo-yt-j706f-kernel/blob/main/arch/arm64/configs/yoga11_defconfig)
- **Partition names in the generated fstab** — [recovery.fstab](https://github.com/jeremywildsmith/android_device_lenovo_yoga11/blob/master/recovery.fstab):
  - Logical, slot-selected: `system`, `vendor`, `product`.
  - Slot-selected: `boot`, `vbmeta_system`, `vbmeta_vendor`.
  - `md_udc` (metadata), `userdata`.
  - MTK firmware: `protect1`, `protect2`, `nvdata`, `nvcfg`, `persist`, `frp`, `nvram`, `proinfo`, `lk`, `lk2`, `para`, `misc`, `logo`, `expdb`, `seccfg`, `tee1`, `tee2`, `scp1`, `scp2`, `sspm_1`, `sspm_2`, `md1img`, `md1dsp`, `cam_vpu1`, `cam_vpu2`, `cam_vpu3`, `gz1`, `gz2`, `spmfw`, `boot_para`, `dtbo`, `otp`, `vbmeta`, `lenovocust`.
- **Storage.** Storage is UFS 2.1 — [Lenovo PSREF](https://psref.lenovo.com/syspool/Sys/PDF/Lenovo_Tablets/Yoga_Tab_11/Yoga_Tab_11_Spec.html). The stock DTB has the `ufshci@11270000` node (inspected locally from [prebuilt/dtb.img](https://github.com/jeremywildsmith/android_device_lenovo_yoga11/tree/master/prebuilt)).
- **Reading the preloader.** On MTK UFS/eMMC devices, mtkclient reads the preloader from the boot area: `mtk.py r preloader preloader.bin --parttype boot1` — [mtkclient README-USAGE.md](https://github.com/bkerler/mtkclient/blob/main/README-USAGE.md)
- **Scatter packages.** SP Flash Tool (scatter) packages for MT6785 YT-J706F builds are listed by third-party mirrors, e.g. `..._S240301_240918_ROW.zip` — [firmwarefile.com (search summary)](https://firmwarefile.com/lenovo-yoga-tab-11-yt-j706f)

### Inferences
- **Generator output is unverified.** The fstab and BoardConfig come from SebaUbuntu's automatic generator, and the super size is explicitly flagged as hardcoded. The partition list mixes non-slotted legacy names (`lk`/`lk2`, `dtbo`, `vbmeta`) with slotted `boot`. That is unusual for a full A/B MTK layout, where `lk_a`/`lk_b`, `dtbo_a`/`dtbo_b`, `vbmeta_a`/`vbmeta_b` are common. **Treat slot naming as unverified until `ls /dev/block/by-name` is seen.**
- **Rescue-slot candidates.** If `boot_a`/`boot_b` both exist, the slot that is not booted can hold a rescue Linux, selected with `fastboot --set-active=b` or `fastboot boot`. That requires LK not to fall back automatically after failed boots (A/B retry counters in `misc`/`para`), which needs testing. Repurposing `vendor_b`/`system_b` space inside `super` (or shrinking it) is the other route for a rootfs.
- **Rootfs placement.** `userdata` (most of the UFS) or a microSD card are the obvious rootfs locations, as on the Tab S2.

### Gaps
- What is the real partition list, with sizes and slots? Run `adb shell ls -l /dev/block/by-name/`, then `adb shell cat /proc/partitions`, then `fastboot getvar all | grep partition-size`. Or use mtkclient: `python mtk.py printgpt`.
- What are the UFS LUN layout and where is the preloader? Run `adb shell ls -l /dev/block/sd*`.
- Does slot selection work? Run `fastboot getvar current-slot`, then `fastboot --set-active=b`, then `fastboot getvar slot-retry-count:b`.
- Does the LMSA package contain a scatter file and the DA? Download it with LMSA (Rescue) and list it.

## Community status (XDA, 4PDA, GitHub, postmarketOS)

### Takeaway
The YT-J706F modding scene is thin: one XDA Magisk root guide, no published TWRP/OrangeFox build, no LineageOS, no documented GSI success, and no phhusson-wiki entry. The most relevant recent work is a **postmarketOS downstream port by JeremyWildsmith (August 2026)**, which proves custom 4.14 kernels boot on the device. MT6785 also has an active **mainline** effort (pmOS "mt6785-mainline", package `linux-postmarketos-mediatek-mt6785` in testing), currently booting on Xiaomi phones only.

### Cited Findings
- **XDA.**
  - The YT-J706F root guide uses LMSA boot.img, a Magisk patch and vbmeta-disable — [XDA thread 4463519](https://xdaforums.com/t/root-guide-yt-j706f-lenovo-yoga-tab-11.4463519/).
  - In a "Download custom rom for lenovo yoga tab 11" thread, moderators found no LineageOS build — [XDA thread 4690704 (search summary)](https://xdaforums.com/t/download-custom-rom-for-lenovo-yoga-tab-11.4690704/).
  - A thread on a YT-J706F that kept restarting after root got the advice to reflash stock firmware — [XDA thread 4622529 (search summary)](https://xdaforums.com/t/lenovo-yoga-tab-11-yt-j706f-wont-let-me-turn-it-off-keeps-restarting-itself.4622529/).
- **4PDA.** The device discussion thread exists (topic 1039284); content was not readable (403) — [4PDA Lenovo Yoga Tab 11](https://4pda.to/forum/index.php?showtopic=1039284)
- **TWRP.** Only an auto-generated TWRP device tree exists (codename `yoga11`, generated 2024-12-10); no build or test report was found. A second repo titled "Device tree for Lenovo Yoga Tab 11 (YT-J706F, WiFi Version)" is **empty** (2025-09-10) — [jeremywildsmith/android_device_lenovo_yoga11](https://github.com/jeremywildsmith/android_device_lenovo_yoga11); [yungvender/android_device_Lenovo_YT-J706F](https://github.com/yungvender/android_device_Lenovo_YT-J706F)
- **postmarketOS port (2026-08-06).** Kernel commits describe:
  - disabling a wrongly enabled `CONFIG_TARGET_PROJECT_P522` (broken eMMC DT nodes);
  - fixing the LCM name `hx83102p_fhdp_dsi_vdo_boe_p522 → hx83102p_fhdp_dsi_vdo_boe`, "the actual root cause of the post-splash bootloop";
  - enabling `CONFIG_VT`/`FRAMEBUFFER_CONSOLE`;
  - disabling SSPM "to avoid a boot hang on postmarketOS, where its firmware/init handshake is never satisfied".

  The toolchain repo says it is fetched "via postmarketOS's pmaports". An earlier 2024-12 kernel import by the same author also exists — [lenovo-yt-j706f-kernel](https://github.com/JeremyWildsmith/lenovo-yt-j706f-kernel/commits/main); [lenovo-yt-j706f-toolchain](https://github.com/JeremyWildsmith/lenovo-yt-j706f-toolchain); [android_linux_lenovo_yoga11 (2024-12)](https://github.com/JeremyWildsmith/android_linux_lenovo_yoga11)
- **postmarketOS wiki.** It has no YT-J706F page (searches for "J706" and "yoga tab 11" return 0 hits). The MT6785 SoC page (edited 2026-03-24) says mainline = yes, community page `gitlab.postmarketos.org/mt6785-mainline`, kernel package `linux-postmarketos-mediatek-mt6785` (testing). Devices: Xiaomi Redmi Note 10S / POCO M5s (rosemary, downstream) and Xiaomi Redmi Note 8 Pro (begonia, testing) — [postmarketOS wiki: MediaTek Helio G90T/G95 (MT6785)](https://wiki.postmarketos.org/wiki/MediaTek_Helio_G90T/G95_(MT6785))
- **GSI.** phhusson's treble_experimentations wiki (last commit 2025-01-27) has no Yoga Tab 11 entry. Its Lenovo list has "Lenovo Tab P11 Pro TB-J706 A/B", which is the Qualcomm tablet — [phhusson treble wiki: Lenovo, Motorola and NEC](https://github.com/phhusson/treble_experimentations/wiki/Lenovo,-Motorola-and-NEC)
- **Stock firmware sources.** Firmware comes from Lenovo Rescue and Smart Assistant (LMSA), per the XDA guide, and third-party SP Flash Tool mirrors (firmwarefile.com, addrom.com) — [XDA thread 4463519](https://xdaforums.com/t/root-guide-yt-j706f-lenovo-yoga-tab-11.4463519/); [firmwarefile.com](https://firmwarefile.com/lenovo-yoga-tab-11-yt-j706f); [addrom.com](https://addrom.com/stock-rom-firmware-for-lenovo-yoga-tab-11-yt-j706/)

### Inferences
- **The postmarketOS port is the closest prior art.** It is a downstream 4.14 Linux userspace on this exact tablet, and its author's fixes (LCM name, SSPM, VT console) are directly reusable knowledge. How it booted (flash vs `fastboot boot`) and its pmaports `deviceinfo` were not found. It may live on a fork or merge request on postmarketOS GitLab: the API redirected to another host and was not followed.
- **Bricks look recoverable.** BROM is unpatched on MT6785 (mtkclient "confirmed"), so a bad `boot`, `lk` or `vbmeta` should be recoverable from the Mac with mtkclient (BROM, keys + cable), or SP Flash Tool on Windows with an LMSA/scatter package. No YT-J706F-specific hard-brick report was found.

### Gaps
- No XDA/4PDA thread could be read in full: dates, firmware versions per report, and brick stories are missing. A human-browser pass over XDA 4463519 and 4PDA 1039284 would fill this.
- Where are the pmOS port's `deviceinfo`, flash method and status? Contact the author or search pmOS GitLab.
- Has anyone booted a GSI on YT-J706F, and with which firmware? Nothing was found.

## What can only be settled with the tablet in hand (command checklist)

### Takeaway
The feasibility verdict hinges on five tablet-side facts:
1. Does `fastboot boot` work when unlocked?
2. The exact `getvar all` output (slots, partition sizes, download size).
3. Does a host-triggered reboot into fastboot work from Linux/Android without keys?
4. The orange-state delay and whether it ever needs a key press.
5. Does mtkclient reach BROM on this production unit, ideally via `crash` without keys?

### Cited Findings
- mtkclient's MT6785 config ("confirmed"), the `crash`/`printgpt`/`seccfg`/`vbmeta 3` commands, and macOS support — [mtkclient](https://github.com/bkerler/mtkclient)
- MTK LK `boot` is registered as forbidden-when-locked in the reference LK — [gemini-lk fastboot.c](https://github.com/dguidipc/gemini-lk/blob/master/lk/app/mt_boot/fastboot.c)

### Inferences
- **Steps 1–5 decide the dev loop.** If they all pass, the Mac-only, keyless dev loop is: Linux running → `reboot bootloader` → `fastboot boot` (test) or `fastboot flash boot_b` (install) → `fastboot reboot`. BROM via mtkclient is the brick safety net. It is roughly equivalent to the Tab S2's Download mode + heimdall, plus RAM boot.

### Gaps
Run in order, on stock firmware first:

**From Android:**
1. **Identity.** `adb shell getprop ro.product.model; getprop ro.build.fingerprint; getprop ro.build.version.security_patch`
2. **Boot state.** `adb shell getprop | grep -E "ro.boot.(slot_suffix|verifiedbootstate|flash.locked|vbmeta|dynamic_partitions|hardware|veritymode)"` (avoid dumping `/proc/cmdline` or `ro.serialno`: they hold the serial number)
3. **Partitions.** `adb shell ls -l /dev/block/by-name/` and `adb shell cat /proc/partitions`
4. **Unlock toggle.** `adb shell getprop sys.oem_unlock_allowed`
5. **Reboot to fastboot.** `adb reboot bootloader` (keyless entry to fastboot?)

**In fastboot (LK):**

6. **Variables.** `fastboot getvar all 2>&1 | tee getvar.txt`, then redact `serialno` before sharing.
7. **Unlock ability.** `fastboot flashing get_unlock_ability`
8. **Unlock.** `fastboot flashing unlock` (expect a volume-key confirmation and a wipe), or failing that `fastboot oem unlock`.

**After unlock:**

9. **RAM boot.**
   - Run `fastboot boot stock_boot.img`.
   - Then repack with a modified cmdline (`mkbootimg --header_version 2 --pagesize 2048 --base 0x40078000 --ramdisk_offset 0x07c08000 --tags_offset 0x0bc08000 --dtb dtb.img ...`) and `fastboot boot` it.
10. **vbmeta.** `fastboot --disable-verity --disable-verification flash vbmeta vbmeta.img`, then time the orange-state screen.
11. **Mode reboots.** `fastboot reboot fastboot` + `fastboot getvar is-userspace`, then `fastboot reboot recovery`, then `fastboot reboot bootloader`.
12. **Slots.** `fastboot getvar current-slot`, `fastboot --set-active=b`, and confirm fallback behaviour after a deliberately broken `boot_b`.
13. **OEM commands.** `fastboot oem append-cmdline "foo=1"`, `fastboot oem off-mode-charge 0`, `fastboot oem p2u` — record which ones exist.

**BROM:**

14. **Entry and config.** Power off, then hold Vol+ (or Vol−) + Power while plugging USB with `python mtk.py printgpt` waiting. Then run `python mtk.py gettargetconfig` (SBC/SLA/DAA) and back up with `python mtk.py rl backup/` (full partition backup before anything else).
15. **Keyless BROM.** Reboot normally while running `python mtk.py crash` to see whether preloader-to-BROM works without keys.

**From Linux on the device:**

16. **Reboot syscall.** Confirm `reboot bootloader` from the custom kernel lands in LK fastboot. This needs the MTK boot-mode magic in the kernel's reboot handler.
