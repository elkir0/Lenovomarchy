# Official USB repair paths for the Lenovo Yoga Tab 11 (YT-J706F, MT6785 / Helio G90T)

Research date: 2026-11-15. Scope: Lenovo's own tools (Software Fix / Rescue and Smart Assistant, "LMSA" or "RSA"), Lenovo firmware packages used with MediaTek's SP Flash Tool, and standard fastboot. Exploit and bypass techniques are only noted as existing, never described.

Reliability legend used below:
- **[Official]**: Lenovo's own page.
- **[Confirmed]**: something I checked directly (file listings, HTTP headers, source code).
- **[Owner report]**: a forum post. Gives the date and firmware where known.
- **[Third-party]**: a firmware or "how-to" aggregator. Low reliability, often generic text.
- **[Other model]**: applies to a different Lenovo tablet, not proven for the YT-J706F.

Naming trap, important for every search: **TB-J706F is not this tablet.** TB-J706F is the Lenovo Tab P11 Pro / Xiaoxin Pad Pro, a Qualcomm device, with firmware such as `TB-J706F_S620108_211124_ROW` ([XDA thread titles "Lenovo/Xiaoxin p11 pro TB-J706F", "TB-J706F TWRP for Android 11"](https://xdaforums.com/t/lenovo-xiaoxin-p11-pro-tb-j706f-zui-version-and-other-doubts.4545743/)). The Yoga Tab 11 is **YT-J706F** (Wi-Fi) and **YT-J706X** (LTE). Never flash a TB-J706F package on a YT-J706F.

## 1. Does Lenovo Software Fix (Rescue and Smart Assistant, LMSA) support the YT-J706F? Which firmware does it download? Does it run on macOS? Does it need a Lenovo account?

### Takeaway
Yes. Owners have used LMSA's "Tablet Rescue" on the YT-J706F since at least 2022 to download and flash the full stock ROW firmware. The tool is **Windows 10/11 64-bit only**: Lenovo publishes no macOS build. It needs a **Lenovo ID** login, and it picks the firmware from the tablet's serial number.

### Cited Findings
- **[Official]** The Lenovo download page "Software Fix (Rescue and Smart Assistant)" (document DS101291) lists only **Windows 10 (64-bit) and Windows 11 (64-bit)**. Current build released **27 Jul 2026**, 136.66 MB, plus a user guide. The page describes it as an official PC tool that can flash "all Lenovo android phone, MOTO phone, Lenovo tablet" software, with functions "Update Rom, Device Rescue". The page lists no macOS or Linux build. Page last modified 27 Jul 2026, first published 11 May 2017. — [Lenovo Support DS101291](https://support.lenovo.com/us/en/downloads/ds101291-rescue-and-smart-assistant-lmsa)
- **[Owner report, 2022-07-01, YT-J706F, firmware S000049_211204_ROW]** The XDA "[Root Guide] YT-J706F" says: install Rescue and Smart Assistant, **sign in with or register a Lenovo ID**, go to Rescue > Tablet Rescue, **enter the serial number**, check that it finds the tablet, then Start Rescue. The download was about 2.6 GB and was saved to `C:\ProgramData\RSA\Download\RomFiles\YT_J706F_S000049_211204_ROW`, including `boot.img` and `vbmeta.img`. — [XDA, rayoz12, 2022-07-01](https://xdaforums.com/t/root-guide-yt-j706f-lenovo-yoga-tab-11.4463519/)
- **[Owner report, 2024-01-04]** A reply in the same thread says the guide still worked, with Magisk 26.4. — [XDA, same thread](https://xdaforums.com/t/root-guide-yt-j706f-lenovo-yoga-tab-11.4463519/)
- **[Owner report, 2024-09-12, model not stated]** In the same thread, a user reports that "software fix is stuck loading" for hours. No answer was posted. — [XDA, same thread](https://xdaforums.com/t/root-guide-yt-j706f-lenovo-yoga-tab-11.4463519/)
- **[Owner report, 2025-02-21, Other model: Tab M11 TB330FU, MediaTek]** One user says Rescue "always downloads the correct firmware": enter the serial number, and the tablet does not need to be connected. The files land under `C:/ProgramData/LMSA/...` and can then be flashed with SP Flash Tool. Another user in the same thread counters that Lenovo's tools had been "upgraded" so they no longer offered that download. — [XDA TB330FU thread](https://xdaforums.com/t/lenovo-tab-m11-tb330fu-boot-loop-have-brom-access-with-mtkclient-and-flash_tool-and-fastboot-access.4719833/)
- **[Owner report, 2023-04-13, Other model: Tab M10 FHD Plus TB-X606F, MediaTek]** LMSA Rescue failed to detect the tablet until the owner installed MediaTek USB VCOM drivers ("MTK_USB_All_v1.0.8") on Windows 10. Then, **holding Volume Up while connecting the USB cable**, LMSA "immediately started flashing" and the tablet recovered. The owner also credits a video that Lenovo's RSA team made for them. — [XDA TB-X606F thread](https://xdaforums.com/t/solved-help-lenovo-tb-x606f-has-twrp-but-need-stock-rom-because-lmsa-rescue-fails.4574945/)
- **[Confirmed]** Firmware names: the ROW builds known for YT-J706F use the pattern `YT-J706F_S<build>_<yymmdd>_ROW`, the same format as LMSA's download folder in the 2022 guide. See section 2 for the full list. — [lolinet mirror listing](https://mirrors-obs-1.lolinet.com/firmware/lenowow/2021/Yoga_Tab_11/YT-J706F/)

### Inferences
- LMSA has always served the build Lenovo currently offers for the serial number. In July 2022 that was S000049_211204 (Android 11). As of late 2026 it is most likely the last build, `S240301_240918_ROW` (Android 12), since no later build appears on any mirror. I found no evidence that LMSA lets the user pick an older version.
- From a Mac, LMSA needs a real Windows x64 PC. Running it in a VM is possible in principle, but I found no report either way for this tablet. MediaTek flashing re-enumerates USB devices (preloader/BROM ports) during the process, and that is a common failure point for USB passthrough. This is unverified inference.
- The Lenovo ID requirement is documented by owners (2022), not on Lenovo's download page.

### Gaps
- Which LMSA build (2026) still lists the YT-J706F, and whether "Tablet Rescue" still downloads its firmware without the tablet connected. The tablet's end of support was given as April 2024 (section 2), and the 2025 claim that Lenovo restricted downloads is unresolved.
- The exact on-screen instruction LMSA shows for the YT-J706F (which key to hold while plugging in) was not found in any source.
- Whether LMSA checks the tablet's current version and refuses older packages (anti-rollback logic in the tool) is undocumented.

## 2. Official firmware packages: where to get them, which versions exist, and whether SP Flash Tool can flash them as distributed (or needs authorization)

### Takeaway
Lenovo's official distribution channel is LMSA. Mirrors of those packages exist. The **lolinet mirror** hosts ten YT-J706F ROW builds, from S000046 (Oct 2021) to **S240301 (18 Sep 2024)**, each 2.7–3.3 GB. Third-party sites say they are SP Flash Tool packages with `MT6785_Android_scatter.txt`. Android 11 builds use the `S000xxx` series and Android 12 builds the `S240xxx` series. **I found no Android 13 build.** Whether stock SP Flash Tool can flash them without Lenovo authorization is **not established** for this model. A GSM-service index labels several YT-J706F packages "Flashing By LST Tool [Need Auth From Server]", which hints that Lenovo's service tooling uses server-side authorization. Other Lenovo MediaTek tablets have been reflashed with SP Flash Tool v5 using the auth file shipped in the firmware.

### Cited Findings
- **[Confirmed, via HTTP HEAD on 2026-11-15]** lolinet (an unofficial mirror of Lenovo firmware) moved the 2021 models, including "Yoga_Tab_11 (Lenwow Yoga Tab 11) YT-J706F YT-J706X", to its "obsoleted" server. Its policy is to keep firmware 5 years from release. — [lolinet 2021 README](https://mirrors.lolinet.com/firmware/lenowow/2021/README.html). YT-J706F files (size; server Last-Modified date):
  - `YT-J706F_S000046_211015_ROW.zip`: 2,733,319,054 B; 2021-11-19
  - `YT-J706F_S000049_211204_ROW.zip`: 2,762,560,871 B; 2022-01-04
  - `YT-J706F_S240113_220811_ROW.zip`: 3,277,003,597 B; 2022-09-01
  - `YT-J706F_S240133_230206_ROW.zip`: 3,222,390,831 B; 2023-04-23
  - `YT-J706F_S240141_230506_ROW.zip`: 3,271,364,047 B; 2023-07-07
  - `YT-J706F_S240184_231114_ROW.zip`: 3,309,808,682 B; 2023-12-15
  - `YT-J706F_S240235_240105_ROW.zip`: 3,103,741,459 B; 2024-01-31
  - `YT-J706F_S240290_240410_ROW.zip`: 3,104,051,207 B; 2024-05-04
  - `YT-J706F_S240299_240703_ROW.zip`: 3,169,016,087 B; 2024-08-08
  - `YT-J706F_S240301_240918_ROW.zip`: 3,169,030,752 B; 2024-11-12
  - The YT-J706X folder has a parallel series, `S000052_211020` to `S240301_240918`. — [lolinet YT-J706F](https://mirrors-obs-1.lolinet.com/firmware/lenowow/2021/Yoga_Tab_11/YT-J706F/), [lolinet YT-J706X](https://mirrors-obs-1.lolinet.com/firmware/lenowow/2021/Yoga_Tab_11/YT-J706X/)
- **[Third-party, GSM service index, uploads 2021-06-07 to 2025-03-04]** HalabTech lists about 37 YT-J706F packages. Besides the ROW builds above, it lists:
  - intermediate builds: `S240122_221021`, `S240127_221213`, `S240151_230705`, `S240157_230829`;
  - early builds: `S000019_210408_ROW_UserDebug`, `S000037_210527`, `S000042_210721_ROW_SVC`, `S000056_220628`;
  - "_SVC" (service) variants and "MPR0/MPS0" factory-named packages;
  - a Korean carrier variant `S000032_220907_LGU` (LG U+), a `..._ImageLoader` package and a "Chip Level Repair" package;
  - several entries named "**Flashing By LST Tool [Need Auth From Server]**" or "[Need Auth By Server]" (for S240290, S240299, S240301 and LGU), next to plain `.zip` entries for the same builds.

  — [HalabTech YT-J706F folder](https://support.halabtech.com/index.php?a=downloads&b=folder&id=127291)
- **[Third-party]** NeedROM labels the builds `S240113_220811` through `S240301_240918` as **Android 12** ("user 12" build tag) and says flashing uses a flash tool with `MT6785_Android_scatter.txt`, in "Download Only" or "Firmware upgrade" mode. The same page wrongly states the chip as "MT8185" while naming an MT6785 scatter file. Last modified 2024-11-16. — [NeedROM YT-J706F 12](https://www.needrom.com/download/lenovo-yoga-tab-11-yt-j706f-12/). A sibling NeedROM page lists `S000056_220628_ROW` as Android 11, as summarized by a search engine; I did not fetch that page myself. — [NeedROM YT-J706F](https://www.needrom.com/download/lenovo-yoga-tab-11-yt-j706f/)
- **[Third-party]** Firmwarefile.com lists YT-J706F stock packages of about 3 GB, "flashed with SP Flash Tool for Windows or Linux". Seen only as a search snippet: the page returned 403 to direct fetch. — [firmwarefile.com YT-J706F](https://firmwarefile.com/lenovo-yoga-tab-11-yt-j706f)
- **[Third-party, secondary]** The Yoga Tab 11 launched on Android 11 with Android 12 as its planned upgrade. Security-maintenance end is listed as **2024-04-30 for YT-J706F** (2024-05-30 for YT-J706X), with the Android 12 date marked as an estimate. — [MyNextTablet, Lenovo Android 14 timeline](https://mynexttablet.com/lenovo-android-14-update/)
- **[Third-party, Other models]** For some Lenovo MediaTek tablets, the authentication file is shipped inside the stock firmware as `auth_sv5.auth`, and auth files are tied to the signed preloader. One Lenovo/Xiaoxin model needed a differently named `auth_sv5_onyx.auth`. — [DroidWin, DA/scatter/auth files](https://droidwin.com/download-agent-scatter-authentication-files-in-sp-flash-tool/) (undated); [XDA TB3-730X auth_sv5.auth](https://xdaforums.com/t/lenovo-tb3-730x-auth_sv5-auth-file.3559048/)
- **[Owner report, 2025-02-21, Other model: Tab M11 TB330FU]** The owner flashed Lenovo firmware with **SP_Flash_Tool_V5.2404_Win**, including a downgrade from May 2024 to October 2023 firmware on an unlocked, rooted unit. Recovering from a later bootloop also involved mtkclient. That is an exploit-based tool: noted, not detailed. A 2025-04-06 reply says the same steps restored a **Tab K10 TB-X6C6F** and "may work for any MediaTek-powered Lenovo tablet". — [XDA TB330FU thread](https://xdaforums.com/t/lenovo-tab-m11-tb330fu-boot-loop-have-brom-access-with-mtkclient-and-flash_tool-and-fastboot-access.4719833/)
- **[Third-party, 2025, Other models]** A GitHub project for newer Lenovo MediaTek tablets expects the Software Fix package to contain `flash.xml` and a `da.auth`. That is the newer V6/flash.xml format, not the scatter format. — [LPMBox on GitHub](https://github.com/dwas-KR/LPMBox)
- **[Third-party, general]** Secure-boot MediaTek devices fail in SP Flash Tool with authentication errors (S_AUTH_FAIL, STATUS_SEC_AUTH_FILE_NEEDED) unless given the device's auth file or matching Download Agent. Hovatek keeps a thread of Lenovo DA files. — [Hovatek SP Flash Tool error codes](https://www.hovatek.com/forum/thread-439.html); [Hovatek Lenovo DA post](https://www.hovatek.com/forum/post-209238.html). An XDA article covers SP Flash Tool auth **bypass**: noted only, not detailed. — [XDA news](https://www.xda-developers.com/bypass-mediatek-sp-flash-tool-authentication-requirement)

### Inferences
- Owners can get official YT-J706F images through LMSA (Windows, Lenovo ID) or the lolinet mirror. Both channels carry the same `..._ROW.zip` naming, and that naming matches LMSA's own folder.
- The latest build, `S240301_240918` (Sep 2024), is Android 12. The S000→S240 jump in Aug 2022 lines up with the Android 12 upgrade, and no Android 13 build appears anywhere.
- "Need Auth From Server" on the service-tool variants suggests that **Lenovo's own service flashing (LST) asks a Lenovo server for authorization**, the usual Lenovo/Motorola MediaTek arrangement. Whether the plain ROW zip includes a usable `auth_sv5.auth` and Download Agent, so that SP Flash Tool can flash it unaided, is unproven for this tablet. It depends on whether SLA/DAA is enabled on the YT-J706F's SoC, which nothing I found states.
- SP Flash Tool officially exists for Windows and Linux, not macOS. A Mac-only owner has no fully native official MediaTek-level flash path. Only fastboot works natively on macOS (Google's platform-tools for macOS: [Android SDK Platform-Tools](https://developer.android.com/tools/releases/platform-tools)).

### Gaps
- Contents of the YT-J706F ROW zip: scatter partition list, whether `auth_sv5.auth` and a `DA` / `MTK_AllInOne_DA` are present, preloader name. I did not download the 3 GB packages. An `unzip -l` on one package, which needs no tablet, settles this.
- The SP Flash Tool version known to work with this model (v5.x vs v6) and Linux behaviour: no YT-J706F-specific report found.
- Whether YT-J706F enforces SLA/DAA: no source.
- Whether a PRC (China) build of YT-J706F exists: none found on lolinet or HalabTech. The only non-ROW variant seen is the Korean "LGU" build.
- No official Lenovo page lists the YT-J706F firmware versions. The version list above comes from mirrors.

## 3. Documented key combinations and modes (recovery, fastboot, flash mode for LMSA / SP Flash Tool)

### Takeaway
Fastboot is confirmed by owners: **hold Volume Down + Power** until "fastboot mode" text appears, or `adb reboot bootloader`. Standard `fastboot flashing unlock` works after enabling "OEM unlocking". The recovery key combo is not confirmed by any first-hand source; aggregators say **Power + Volume Up**. The MediaTek download state that LMSA and SP Flash Tool expect is documented only on other Lenovo MediaTek tablets: **tablet powered off, hold Volume Up (some reports say Volume Down) while plugging in USB**.

### Cited Findings
- **[Owner report, 2022-07-01, YT-J706F, S000049]**
  - Fastboot: "Press Vol - and Power key" or `adb reboot bootloader`. To get back after a bad boot image: "hold Vol - (Vol Down) + Power button forever until the fastboot mode text appears".
  - Bootloader unlock: Developer options > **OEM unlocking**, then `fastboot flashing unlock`, which wipes the device.
  - Recovery after a bad root: flash the stock `boot.img` and `vbmeta.img` from the LMSA folder via fastboot.
  - On Windows, the fastboot driver had to be picked manually ("Android ADB composite").

  — [XDA root guide](https://xdaforums.com/t/root-guide-yt-j706f-lenovo-yoga-tab-11.4463519/)
- **[Owner report, 2022-09-01 / 09-09]** One user saw nothing happen after `fastboot flashing unlock`. The author replied that the screen prints a message when the unlock starts and ends. — [same thread](https://xdaforums.com/t/root-guide-yt-j706f-lenovo-yoga-tab-11.4463519/)
- **[Official user guide, via search snippet]** Hold Power about 8 s to turn off; about 10 s to force a restart. — [Yoga Tab 11 user manual (Croma-hosted PDF)](https://media.croma.com/image/upload/v1723282309/Croma%20Assets/Computers%20Peripherals/Tablets%20and%20iPads/User%20Manual/245015_User%20Manual.pdf)
- **[Official support reply, 2023-01-02]** A Lenovo specialist told a YT-J706F owner stuck in fastboot to "press the power button for about 30seconds then power it on normally". — [Lenovo Community](https://forums.lenovo.com/t5/Android-Yoga-Series-Tablets/Yoga-Tab-11-YT-J706F-stuck-in-fastboot-mode-after-reflashing-stock-firmware-with-Smart-Assistant/m-p/5193403)
- **[Third-party, 2026]** A general guide says Power + Volume Up opens recovery and groups the Yoga Tab 11 with older models for this combo. It also recommends charging at least 30 min before troubleshooting. — [fixmytablet.net, stuck on logo](https://fixmytablet.net/lenovo-tablet-stuck-on-lenovo-logo/). A YouTube video "How to Enter Recovery Mode on a LENOVO Yoga Tab 11" exists but was not viewed. — [YouTube](https://www.youtube.com/watch?v=dSmCxwF2mgY)
- **[Owner report, Other model: TB-X606F, 2023-04-13]** LMSA Rescue for a MediaTek tablet: **Volume Up held while connecting USB** started flashing, once MTK VCOM drivers were installed. — [XDA TB-X606F](https://xdaforums.com/t/solved-help-lenovo-tb-x606f-has-twrp-but-need-stock-rom-because-lmsa-rescue-fails.4574945/)
- **[Owner reports, Other models]** Other users of Lenovo MediaTek tablets report that holding **Volume Down** while plugging in, or no key at all, worked with SP Flash Tool. — [UBports forum, Tab M10 Plus X606 port](https://forums.ubports.com/topic/6437/porting-lenovo-smart-tab-m10-plus-x606/33?lang=en-GB)
- **[Owner report, Other model: Tab P11 Plus]** On that model, Power + Volume Up goes to a fastboot/META menu, and recovery needs a three-button press. — [Lenovo Community, Tab P11 Plus](https://forums.lenovo.com/t5/Lenovo-Android-based-Tablets-and-Phablets/Tab-P11-Plus-can-t-reset-device/m-p/5250877)

### Inferences
- The YT-J706F's mapping is unusual for Lenovo, where Volume Up + Power often means fastboot. Here **Volume Down + Power = fastboot**, so **Volume Up + Power is probably recovery**. Treat it as plausible, not confirmed.
- MediaTek preloader download mode (what LMSA and SP Flash Tool use) is entered from power-off by connecting USB, with or without a volume key held. Which key the YT-J706F needs must be tested.

### Gaps
- No first-hand YT-J706F source for the recovery combo, or for the key LMSA asks for in Rescue.
- No source on whether the YT-J706F exposes fastbootd (userspace fastboot) in addition to bootloader fastboot.

## 4. Owner reports: tablets that stopped booting and how official tools did or did not fix them

### Takeaway
I found very few YT-J706F-specific brick reports. The documented ones are a **failed LMSA reflash that ended in a dm-verity warning plus fastboot loop**, left unresolved with "contact service" (Jan 2023, firmware not stated), and LMSA hanging while "loading" (Sep 2024). Successful LMSA rescues are documented on sibling Lenovo MediaTek tablets (TB-X606F, 2023). The documented route out of a root-induced bootloop on YT-J706F is fastboot with the stock `boot.img` and `vbmeta.img`.

### Cited Findings
- **[Owner report, YT-J706F, 2023-01-02 → 2023-01-16, firmware not stated]** The owner had a "dm-verity corrupted" message and reflashed with Rescue/Smart Assistant. The tablet then showed the dm-verity splash and dropped to fastboot on power press. Lenovo support suggested a 30 s power press, then "The system could be corrupted already. You may contact our team for service". No resolution was posted, and the community is now read-only. — [Lenovo Community thread](https://forums.lenovo.com/t5/Android-Yoga-Series-Tablets/Yoga-Tab-11-YT-J706F-stuck-in-fastboot-mode-after-reflashing-stock-firmware-with-Smart-Assistant/m-p/5193403)
- **[Owner report, YT-J706F thread, 2024-09-12]** "software fix is stuck loading" for 3 hours; no follow-up. — [XDA root guide thread](https://xdaforums.com/t/root-guide-yt-j706f-lenovo-yoga-tab-11.4463519/)
- **[Owner report, YT-J706F, 2022-07-01]** The documented fix for a bootloop after flashing a Magisk-patched boot: flash stock `boot.img` + `vbmeta.img` (from the LMSA download) in fastboot. Magisk also requires `vbmeta.img` flashed with `--disable-verity --disable-verification`. — [XDA root guide](https://xdaforums.com/t/root-guide-yt-j706f-lenovo-yoga-tab-11.4463519/)
- **[Owner report, Other model: TB-X606F, 2023-04-12/13]** After a LineageOS GSI bootloop, LMSA Rescue failed at first. After installing MTK USB drivers and holding Volume Up while plugging in, the full LMSA flash succeeded: "tablet is reborn". — [XDA TB-X606F](https://xdaforums.com/t/solved-help-lenovo-tb-x606f-has-twrp-but-need-stock-rom-because-lmsa-rescue-fails.4574945/)
- **[Owner report, Other model: TB330FU, 2025-02-21]** An "Orange State" bootloop with no recovery menu took about 6 hours of work combining SP Flash Tool v5.2404 and the exploit-based mtkclient before the 241220 firmware booted. That is outside official scope. A 2025-09-11 reply: a user who "flash[ed] the wrong file" could afterwards only reach the tablet through mtkclient. — [XDA TB330FU](https://xdaforums.com/t/lenovo-tab-m11-tb330fu-boot-loop-have-brom-access-with-mtkclient-and-flash_tool-and-fastboot-access.4719833/)
- **[Other model, 2022–2023 reference]** An XDA thread on a dead Lenovo TB-X606F describes opening the tablet and disconnecting the battery before flashing with Lenovo's tool while holding Volume Up: a hardware-level last resort. — [XDA TB-X606F dead](https://xdaforums.com/t/lenovo-tb-x606f-dead-howto-unbrick.4698146/)

### Inferences
- The Jan 2023 case shows that an LMSA reflash does not always clear a dm-verity/fastboot loop. The thread does not say whether the bootloader was unlocked or vbmeta modified, so the cause is unknown.
- Reports where a pure LMSA flash fixed a Yoga Tab 11 are absent in what I could reach (XDA, Lenovo Community). The evidence for "LMSA rescues MediaTek Lenovo tablets" comes from sibling models.

### Gaps
- Reddit was not reachable by my tools, and 4PDA's Yoga Tab 11 thread did not surface. Both likely hold more YT-J706F reports.
- No YT-J706F report of a "hard brick" (no fastboot, only a preloader/BROM USB device) recovered or not recovered by LMSA or SP Flash Tool.

## 5. Documented risks: anti-rollback, wrong-region firmware, partitions never to erase, battery

### Takeaway
I found **no YT-J706F-specific documentation** on anti-rollback, region cross-flashing or battery thresholds. The documented risks are generic MediaTek and Lenovo ones:
- SP Flash Tool "Format All + Download", or wrong firmware, can wipe NVRAM/NVDATA (radio calibration, MAC/IMEI). These are unique per unit and are not in the stock ROM.
- Auth files are tied to the signed preloader.
- Unlocking the bootloader on this tablet drops Widevine to L3 (owner claim).
- Wrong-model packages (TB-J706F vs YT-J706F, J706F vs J706X) are an easy mistake.

### Cited Findings
- **[Owner report, YT-J706F, 2022-07-01]** "You will also lose any L3 Widevine DRM Certification, aka no more HD netflix". This is read as a downgrade to L3. Replies on 2022-11-26 and 2024-03-25 asking whether re-flashing stock restores it went unanswered. — [XDA root guide](https://xdaforums.com/t/root-guide-yt-j706f-lenovo-yoga-tab-11.4463519/)
- **[Owner report]** Unlocking with `fastboot flashing unlock` wipes all data. — [XDA root guide](https://xdaforums.com/t/root-guide-yt-j706f-lenovo-yoga-tab-11.4463519/)
- **[Third-party, MediaTek general]** Using the wrong firmware or a format option in SP Flash Tool can damage NVRAM/NVDATA and remove radio configuration (IMEI, Wi-Fi/BT calibration). Advice: back up NVRAM/NVDATA first and avoid "Format All". Restoring needs a backup (`nvram.bin`, `nvdata.img`) from the same unit or model. — [Hovatek thread 49301](https://www.hovatek.com/forum/thread-49301.html); [Hovatek, fix IMEI with nvram.bin & nvdata.img](https://www.hovatek.com/forum/thread-23412-post-140384.html); [TechProlonged, invalid IMEI and WiFi Err 0x10 on MediaTek](https://techprolonged.com/2015/12/how-to-fix-invalid-imei-and-wifi-err-0x10-on-mediatek-devices-without-root/)
- **[Third-party, Other models]** "Auth files are specific to the preloader they're signed with". A cross-region move on a Lenovo/Xiaoxin tablet needed a different auth file. — [DroidWin](https://droidwin.com/download-agent-scatter-authentication-files-in-sp-flash-tool/); [XDA TB132FU firmware discussion](https://xdaforums.com/t/tb132fu-mediatek-kompanio-1300t-discussion-firmware-rom-for-xiaoxin-pad-pro-2022.4515367/)
- **[Owner report, Other model: TB330FU, 2025-02-21]** A downgrade of about 7 months, from 2024 to 2023 firmware, worked with SP Flash Tool on an unlocked Tab M11. This shows at least one Lenovo MediaTek tablet that did not hard-block that downgrade. — [XDA TB330FU](https://xdaforums.com/t/lenovo-tab-m11-tb330fu-boot-loop-have-brom-access-with-mtkclient-and-flash_tool-and-fastboot-access.4719833/)
- **[Secondary, Other model: Moto G Pure]** A reply notes that disabling verification in fastboot does not bypass anti-rollback. — [r/androidroot via redlib](https://redlib.hackliberty.org/r/androidroot/comments/1lbm6pk/is_it_possible_to_downgrade_moto_g_pure)
- **[Third-party, 2026]** Charge-only USB cables are the most common reason LMSA fails to detect a tablet. Charge for 30 min before recovery attempts. — [fixmytablet.net](https://fixmytablet.net/lenovo-tablet-wont-turn-on/) (low-reliability source)
- **[Confirmed]** The ROW builds for YT-J706F and YT-J706X are separate package series with the same version numbers. Mirror folders are per model. — [lolinet Yoga_Tab_11](https://mirrors-obs-1.lolinet.com/firmware/lenowow/2021/Yoga_Tab_11/)

### Inferences
- On MT6785, the partitions to treat as never erase / never overwrite with another unit's copy are the typical MediaTek ones: `nvram`, `nvdata`, `nvcfg`, `protect1/2`, `persist`, `proinfo` (serial, factory data), `seccfg` (lock state), and any `efuse`/`otp` regions. This comes from general MediaTek layouts. The exact YT-J706F partition list must be read from the scatter file. Not sourced for this model.
- Anti-rollback: Android 12 builds normally carry AVB rollback indexes, and MediaTek preloaders can carry their own anti-rollback version. Going from an S240xxx (Android 12) build back to S000xxx (Android 11) is the move most likely to be refused or to brick. Flashing the **same or newer** build as the one installed is the safe default. Unverified for YT-J706F.
- Region: the YT-J706F appears to ship as a single ROW image, plus the Korean LGU carrier variant, so a ROW/PRC mix-up seems less likely than a **model** mix-up (YT vs TB, F vs X).

### Gaps
- No YT-J706F-specific statement on anti-rollback (AVB rollback index values, MediaTek preloader ARB).
- No documented battery threshold for LMSA or SP Flash Tool on this model.
- The partition list (scatter) for YT-J706F was not inspected.
- Whether relocking the bootloader on stock firmware restores Widevine L1: unanswered on XDA.

## 6. Do owners report mtkclient working on this tablet for partition backup?

### Takeaway
**No YT-J706F owner report found.** mtkclient lists the SoC: MT6785 is hwcode 0x813, "Helio G90", in its chip table, marked "confirmed". The only MT6785 issue in the current repository concerns a Xiaomi Redmi 13, where SLA signature handling was fixed in March 2026. Whether it works on the YT-J706F, and on which firmware, is unknown.

### Cited Findings
- **[Confirmed, source code checked 2026-11-15]** `mtkclient/config/brom_config.py` has `0x813: Chipconfig(var1=0xA, # confirmed ... damode=DAmodes.XFLASH, name="MT6785", description="Helio G90")`. — [bkerler/mtkclient brom_config.py](https://github.com/bkerler/mtkclient/blob/main/mtkclient/config/brom_config.py)
- **[Confirmed]** The current `bkerler/mtkclient` repository was created 2026-01-18 and last pushed 2026-10-26. Issue searches for "J706" and "MT6785 lenovo" returned nothing. An MT6785 issue (#127, 2026-03-15, Xiaomi Redmi 13 "moon", HyperOS/Android 16) reported a wrong SLA signature and was marked fixed 2026-03-18. — [mtkclient issue #127](https://github.com/bkerler/mtkclient/issues/127)
- **[Owner report, Other model: TB330FU / TB-X6C6F, 2025]** mtkclient V2.0.1 was used alongside SP Flash Tool on Lenovo MediaTek tablets in bootloop recovery. The method involves security bypass: noted only. — [XDA TB330FU](https://xdaforums.com/t/lenovo-tab-m11-tb330fu-boot-loop-have-brom-access-with-mtkclient-and-flash_tool-and-fastboot-access.4719833/)
- mtkclient describes itself as a MediaTek flash read/write tool. Its documentation covers BROM exploitation (not detailed here). — [bkerler/mtkclient](https://github.com/bkerler/mtkclient)

### Inferences
- Since the SoC is in mtkclient's table, a read-only backup of `nvram`/`nvdata`/`proinfo`/`persist` is plausible. On a device with SLA/DAA it goes through the security bypass path, which is out of scope here. Treat it as untested on YT-J706F.

### Gaps
- No owner report for YT-J706F or YT-J706X with mtkclient: no success, failure or firmware version. 4PDA and Reddit were not searchable with my tools.
- Older mtkclient issues from before the 2026 repository recreation were not searched.

## 7. What can only be settled with the tablet in hand

### Takeaway
The main unknowns are hardware and firmware state questions: installed build, unlock status, the key that enters MediaTek download mode, whether SP Flash Tool needs an auth file on this unit, and whether LMSA still serves its firmware. Most can be answered without writing anything to the tablet.

### Cited Findings
- The installed build (S000xxx Android 11 vs S240xxx Android 12) determines which packages are safe "same or newer" targets. Build naming comes from mirrors. — [lolinet YT-J706F](https://mirrors-obs-1.lolinet.com/firmware/lenowow/2021/Yoga_Tab_11/YT-J706F/)
- LMSA's serial-number lookup has to be run with the actual unit's serial number. — [XDA root guide](https://xdaforums.com/t/root-guide-yt-j706f-lenovo-yoga-tab-11.4463519/)

### Inferences
Checks that need the tablet itself, in rough order of safety:
1. Settings > About: exact build (`YT-J706F_S2403xx…`), Android version, security patch. Check that the label/model is **YT-J706F**, not YT-J706X or TB-J706F.
2. Whether "OEM unlocking" is present and can be toggled, and what the fastboot screen shows (`fastboot getvar all`: lock state, any anti-rollback or slot info) under Vol Down + Power.
3. Which key combo reaches recovery (Vol Up + Power expected), and whether recovery offers "Apply update from ADB" or fastbootd.
4. Which USB device appears on the Mac when the powered-off tablet is plugged in with Vol Up, Vol Down or no key held: MediaTek preloader vs BROM, vendor ID 0x0e8d. Do this with no flashing tool attached.
5. On a Windows PC: whether LMSA Rescue recognises the unit, which build it offers, and what key prompt it shows. Whether SP Flash Tool, given the ROW package, connects without an auth error. A read-back of nvram/nvdata/proinfo as a backup would be the first operation, before any write.
6. Battery health and charge level before any flash. No documented threshold was found.

### Gaps
- Whether a Windows VM on the owner's Mac can pass the MediaTek USB device through reliably enough for LMSA or SP Flash Tool. I found no report for this tablet, so it has to be tested, or a real Windows PC kept as the fallback.
