# MT6785 mainline ports: what really works for Wi-Fi, Bluetooth, audio and battery (verified 2026-11-15)

Method: I cloned `F-to-pay/PostmarketOS-begonia` (full history, 5 commits) into a scratch directory and read the code, patches and notes as data. I did not build or run anything. I queried the GitHub API for Dinolek's tree and uniLoader, the Nura GitLab API (`gitlab.nura.eco`, the renamed `gitlab.postmarketos.org`, which now answers with a 308 redirect) for the `mt6785-mainline` group, `nura/pmaports` and a personal fork, and the Nura wiki API for raw wikitext and revision history. All dates are 2026 unless a year is given. Tags: **[Confirmed]** = seen in code, commits, package files or wiki source. **[Claim]** = someone's statement (README, notes, commit message) that I could not check on hardware.

## 1. Settling the conflict between (A) and (B)

### Takeaway
(A) and (B) do not contradict each other: they describe different things. (A) is the official, packaged state, and it is accurate: the Nura package is still 6.16.4 with no Wi-Fi, BT, audio or battery driver. (B) is a one-device, unofficial patch set written by Claude (Opus 5.5 and Sonnet 5.5) and published on 2026-11-14. It contains real, substantial driver code for Wi-Fi, BT, audio and the fuel gauge [Confirmed], but the evidence that these features work is the owner's own notes [Claim]: no raw logs, screenshots, video or independent testers. A second, earlier and independent Wi-Fi port (June) also exists and claims scanning works, which makes Wi-Fi on MT6785 + mainline plausible. It is not proven to production quality.

### Cited Findings
- [Confirmed] The begonia wiki infobox still reads `status_wifi = N <!-- Technically possible -->`, `status_battery = N`, `status_audio = N`, `status_bluetooth = N`, `pmoskernel = 6.16.4`. The last edits were on 2026-10-13 (a user's undone edit) and 2026-09-27 (the bot rename postmarketOS → Nura). Nobody behind (B) has edited the page — [wiki raw](https://wiki.nura.eco/index.php?title=Xiaomi_Redmi_Note_8_Pro_(xiaomi-begonia)&action=raw), [history](https://wiki.nura.eco/index.php?title=Xiaomi_Redmi_Note_8_Pro_(xiaomi-begonia)&action=history)
- [Confirmed] The official kernel package `linux-postmarketos-mediatek-mt6785` in `nura/pmaports` is `pkgver=6.16.4`, `pkgrel=1`, built from tag `6.16.4-r0` of `mt6785-mainline/linux`, maintainer Dinolek. Its last change was "build with LLVM" on 2026-08-05. Nothing in it touches Wi-Fi, audio or the gauge — [APKBUILD](https://gitlab.nura.eco/nura/pmaports/-/blob/main/device/testing/linux-postmarketos-mediatek-mt6785/APKBUILD), [path history](https://gitlab.nura.eco/nura/pmaports/-/commits/main/device/testing/linux-postmarketos-mediatek-mt6785)
- [Confirmed] (B) was created on 2026-11-14 at 00:04 UTC and last pushed the same day at 13:47 UTC. The repo description reads "firmware for begonia. Writed by Claude Sonnet 5.5 and Claude Opus 5.5. Tested on real device. Have too many bugs as well". It has 0 stars, 0 forks and 0 issues — [GitHub repo](https://github.com/F-to-pay/PostmarketOS-begonia)
- [Claim] The README's status table: Wi-Fi "works: wlan0/wlan1, scan, WPA2-Enterprise, traffic". Bluetooth "works: BR/EDR + LE, A2DP sink". Audio "works: headphones, 2 microphones, noise suppression, speaker (with protection), jack detection, earpiece (quiet)". Battery "works (r3 verified on hardware)". GPS "does not work: the chip sends NMEA, 0 satellites". Modem "does not work: MD boots up to RF init, then asserts in `el1d_rf_error_check`" — [README](https://github.com/F-to-pay/PostmarketOS-begonia/blob/master/README.md)
- [Claim] The README's authorship note: the code, patches, scripts and notes were "written by an AI — Claude (Anthropic, model Claude Opus 5.5) working through Claude Code, with shell access to the phone and the build machine". The human owner did the hardware testing. It warns that the patches "work on this one unit, but nobody has read them line by line yet" — [README](https://github.com/F-to-pay/PostmarketOS-begonia/blob/master/README.md)
- [Confirmed] An independent, earlier Wi-Fi port exists: branch `begonia-conn-wifi` of `minorum/linux` on Nura GitLab, a fork of `mt6785-mainline/linux`. It has 51 commits from 2026-06-16 to 2026-06-19 by Michal Andrzejczak. Its commit messages claim, on hardware, "Boots clean, wlan0 scans real APs" and "WIFI function ON, wlan0 scans 2.4+5GHz" (2026-06-19) [Claim] — [branch commits](https://gitlab.nura.eco/minorum/linux/-/commits/begonia-conn-wifi), [compare 6.16...begonia-conn-wifi](https://gitlab.nura.eco/minorum/linux/-/compare/6.16...begonia-conn-wifi)
- [Confirmed] (B) never mentions the minorum work (no match for `minorum`, `begonia-conn-wifi` or the author's name anywhere in the repo), so the two efforts are independent — [repo](https://github.com/F-to-pay/PostmarketOS-begonia)
- On 2026-11-15, web searches for "PostmarketOS-begonia" and for "begonia mt6785 mainline wifi gen4m" found no announcement or forum post about (B) or the minorum branch. The first search returned only the begonia wiki page and the package page; the second returned nothing about MT6785 — [wiki page returned by the search](https://wiki.postmarketos.org/wiki/Xiaomi_Redmi_Note_8_Pro_(xiaomi-begonia)), [package page returned by the search](https://pkgs.postmarketos.org/package/v25.12/postmarketos/aarch64/device-xiaomi-begonia)

### Inferences
- The study's statement "(A) Wi-Fi/BT/audio/battery NOT working" stays true for anything you can install from Nura today. "(B) works" should be read as "an AI-written patch set that its owner reports working on one Redmi Note 8 Pro, published 1 day ago, unreviewed".
- Two separate efforts, with different architectures, both report that the CONSYS boots and `wlan0` scans on mainline 6.16. That raises confidence that MT6785 Wi-Fi is technically achievable on mainline. It is no longer a "no driver exists" situation: driver code exists, out of tree, in staging-quality form.
- For the YT-J706F study, Wi-Fi moves from "blocking unknown" to "port and validate existing out-of-tree code, risk medium-high". The main risks are code quality, board-specific CONSYS parameters, power management and suspend.

### Gaps
- No independent reproduction of (B) or of the minorum branch exists. I could not run either; the notes quote dmesg lines, but the repo ships no raw logs (they were excluded as "25 MB" and private).
- Whether the (B) author will maintain the repo, upstream it or send the "report-to-maintainer" drafts is unknown. The drafts are marked "DRAFT, not sent".

## 2. What F-to-pay/PostmarketOS-begonia contains, its base, its author, its maintenance

### Takeaway
It is a source-and-notes dump, not a GitHub fork: 469 files, a 22-patch kernel series on tag `6.16.4-r0` of `mt6785-mainline/linux` (= Dinolek's `6.16` branch head `203a993f`), a pmaports overlay, a userspace package `begonia-port`, and per-area notes and debug tools. It is a single, previously unknown author's 4-to-5-day project (2026-11-10 → 2026-11-14), with no sign yet of ongoing maintenance.

### Cited Findings
- [Confirmed] `"fork": false`, license GPL-2.0, default branch `master`, size about 3.5 MB. Five commits, all dated 2026-11-14 (+0100): "first push" at 01:07, then four at 14:44: "wifi: Retransmit lost STP frames and sleep on the BTIF RX interrupt", "audio: Event driven jack automation in begonia-port, IMU rate udev rule", "kernel-build: Add a plasma-nm overlay with the Wi-Fi switch fix", "kernel-build: Kernel 6.16.4-r10 (patches 0019-0022, RFCOMM/BNEP)" — [commits](https://github.com/F-to-pay/PostmarketOS-begonia/commits/master), [commit 2421c22](https://github.com/F-to-pay/PostmarketOS-begonia/commit/2421c22742b82676dae090329cd9c2a30985b5a8)
- [Confirmed] The base: the README says "State as of 2026-11-13. Target system: `linux-postmarketos-mediatek-mt6785` 6.16.4 (tag `6.16.4-r0` of mt6785-mainline)", and lists the upstream tree `mt6785-linux-6.16 ← gitlab.postmarketos.org/mt6785-mainline/linux (203a993f)`. Tag `6.16.4-r0` on Nura GitLab points to commit `203a993f86cd` (2025-09-04), which is also the head of Dinolek's GitHub `6.16` branch — [README](https://github.com/F-to-pay/PostmarketOS-begonia/blob/master/README.md), [Nura linux tags](https://gitlab.nura.eco/mt6785-mainline/linux/-/tags), [Dinolek branches](https://github.com/Dinolek/mt6785-mainline/branches)
- [Confirmed] The kernel series in `kernel-build/kernel/patches/` (patch dates in parentheses):
  - battery and touch: 0001 MT6359 fuel gauge (11-12), 0002 mt6360_charger (11-12), 0003-0004 DTS for touch power and the battery (11-12)
  - CONSYS DT: 0005 DTS for CONSYS, Wi-Fi and reserved memory (11-12)
  - audio and touch DT: 0006/0008/0009 DTS for the audio front end (AFE), the TFA9874 amplifier and ACCDET jack detection; 0007 novatek-nvt-ts touch probe fix (11-12)
  - IR: 0010 DTS for the IR transmitter (11-12)
  - audio drivers (11-13): 0011-0013 ASoC common/mt6359/accdet fixes, 0014 TFA9874 driver, 0015 MT6785 AFE and machine driver
  - Wi-Fi/BT drivers (11-13): 0016 staging CONSYS bring-up driver, 0017 staging gen4m
  - panel: 0018 nt36672a reset sequence (11-13)
  - late fixes (11-14): 0019 STP retransmit, 0020 DTS BTIF interrupt, 0021 BTIF RX interrupt, 0022 bmi160 IIO — [patches](https://github.com/F-to-pay/PostmarketOS-begonia/tree/master/kernel-build/kernel/patches)
- [Confirmed] Packaging: an overlay of `linux-postmarketos-mediatek-mt6785` (APKBUILD and config) and a new package `begonia-port`. It ships the systemd units `begonia-wifi`, `begonia-audio`, `idle-shutdown` and `begonia-jack`, modprobe.d, udev rules, a PulseAudio profile-set and a `-firmware` subpackage. That subpackage is filled from your own backup (`FWDIR`), not shipped. There is also a `plasma-nm` overlay patch — [begonia-port APKBUILD](https://github.com/F-to-pay/PostmarketOS-begonia/blob/master/kernel-build/pmaports/device/testing/begonia-port/APKBUILD), [kernel-build README](https://github.com/F-to-pay/PostmarketOS-begonia/blob/master/kernel-build/README.md)
- [Confirmed] Patch authorship is a placeholder, `From: Begonia <begonia@localhost>` and `Signed-off-by: Begonia <begonia@localhost>`. Patch 0021 adds `Co-Authored-By: Claude Sonnet 5.5`. Most new C files are mode `100755` — [patch 0016](https://github.com/F-to-pay/PostmarketOS-begonia/blob/master/kernel-build/kernel/patches/0016-staging-Add-the-MT6785-CONNSYS-bring-up-driver.patch), [patch 0021](https://github.com/F-to-pay/PostmarketOS-begonia/blob/master/kernel-build/kernel/patches/0021-staging-mt6785-consys-Sleep-on-the-BTIF-RX-interrupt.patch)
- [Confirmed] The account `F-to-pay` (display name "Any%", bio "Just peanuts") was created 2022-11-10 and has 0 followers and 6 public repos. The others are a game ("Deviant", 2026-11-07), "skole", "VibecodingAndLearning" and "C". None is earlier kernel or mobile-Linux work — [user](https://github.com/F-to-pay), [repos](https://github.com/F-to-pay?tab=repositories)
- [Claim] Build host was Windows + WSL. The source of truth is a local `begonia-fixes` branch (not published). The README's "What is NOT in this folder" says the repo excludes all proprietary firmware, partition backups, `.ko` files, logs and voice recordings — [README](https://github.com/F-to-pay/PostmarketOS-begonia/blob/master/README.md), [kernel-build/README](https://github.com/F-to-pay/PostmarketOS-begonia/blob/master/kernel-build/README.md)
- [Claim] Timeline from the notes: Wi-Fi Result #1 (CONSYS chip id read) on 2026-11-10; Wi-Fi up and traffic on 2026-11-11; Bluetooth on 2026-11-11; audio from 2026-11-11 to 2026-11-13; battery on 2026-11-12; the STP-loss fix on 2026-11-14 — [docs/NOTES-chronological.md](https://github.com/F-to-pay/PostmarketOS-begonia/blob/master/docs/NOTES-chronological.md)

### Inferences
- It is effectively a fork of Dinolek's 6.16 tree, distributed as patches plus a pmaports overlay. Rebasing it onto Dinolek's 7.1 branch is untested.
- Maintenance is unknown and the bus factor is one person with an AI agent. Treat it as a donor codebase and a bring-up recipe, not as a dependency.

### Gaps
- The published history is a snapshot, so the real development history (the WSL `begonia-fixes` branch, intermediate snapshots) is not public.

## 3. Wi-Fi and Bluetooth in (B): driver, firmware, helpers, stability, size, portability

### Takeaway
(B) replaces MediaTek's userspace launcher and most of the WMT stack with a 2.7 kLOC staging driver, `drivers/staging/mt6785-consys/consys-bringup.c`. That driver powers CONSYS, downloads the ROM patches over BTIF (the patch body through the AP_DMA TX vFIFO), runs STP and WMT, exports a ~17-function WMT shim, and registers Bluetooth as an `hci_dev` over STP. On top it carries the vendor gen4m driver, ported from 4.14 to 6.16 in staging: 342 files, +456 kLOC, CONNAC profile, AXI host interface. The firmware is the vendor `soc1_0` set copied from an Android vendor image. The owner reports scan, WPA2-Enterprise association, DHCP and ping, and BT BR/EDR, LE scan, pairing and A2DP. Suspend, throughput, MCU-crash recovery and long-term stability are not demonstrated.

### Cited Findings
**Driver architecture**
- [Confirmed] Patch 0016 description: "Power up the MT6785 connectivity subsystem without the vendor WMT stack: genpd + CONN regulators, the MT6359 DCXO buffer, firmware patches over BTIF (PIO and AP_DMA vFIFOs), STP full mode, the WMT handshake and RF calibration. Bluetooth is exposed as hci0 on top of STP… The WMT entry points the gen4m WLAN driver expects (mtk_wcn_wmt_*, EMI base/size) are exported from here." Defaults are `stage=8 calib=3 bt_hci=1`. Diffstat: 7 files, +2,856 (consys-bringup.c 2,575 lines, h4_recv.h 153, wmt_exp.h 110). After patches 0019 and 0021 the file is 2,728 lines — [patch 0016](https://github.com/F-to-pay/PostmarketOS-begonia/blob/master/kernel-build/kernel/patches/0016-staging-Add-the-MT6785-CONNSYS-bring-up-driver.patch), [wifi/consys-bringup.c](https://github.com/F-to-pay/PostmarketOS-begonia/blob/master/wifi/consys-bringup.c)
- [Confirmed] Patch 0017 imports `connectivity/wlan/core/gen4m` from MiCode `MTK_kernel_modules` at commit `cc4a1521` ("Kernel: Xiaomi kernel_modules changes for Redmi Note 8 Pro Android R", 2021-07-23), processed by `port.py` (261 lines): "cfg80211/netdev API updates for 6.16, a WMT shim … backed by mt6785-consys, AXI HIF only". Diffstat: 342 files, +456,281 lines. It includes unused chip directories (mt6632, mt7663, mt7668, mt7915, mt7961, soc3_0) and their multi-thousand-line register headers. The commit message says "Vendor code, staging quality: warnings are not errors here." — [patch 0017](https://github.com/F-to-pay/PostmarketOS-begonia/blob/master/kernel-build/kernel/patches/0017-staging-Add-the-gen4m-WLAN-driver-ported-to-Linux-6..patch), [port.py](https://github.com/F-to-pay/PostmarketOS-begonia/blob/master/wifi/gen4m-port/port.py), [MiCode commit](https://github.com/MiCode/MTK_kernel_modules/commit/cc4a152193b03cde6ecfcffcc317151aaa2b0cdd)
- [Claim] gen4m build profile: `MTK_COMBO_CHIP=CONNAC WLAN_CHIP_ID=6785 WIFI_IP_SET=2 MTK_ANDROID_EMI=y`. The host interface is AXI on a `mediatek,wifi` node (`reg 0x18000000/0x100000`, IRQ SPI 322 level-low, 3 MiB `shared-dma-pool`). The profile is CONNAC "even though the MCU register reports 0x6632". Porting from 4.14 to 6.16 went "710 → 0 compile errors" — [Wi-Fi report](https://github.com/F-to-pay/PostmarketOS-begonia/blob/master/wifi/report-to-maintainer-wifi.md)
- [Claim] MT6785 uses the old WMT scheme, not conninfra: "no SMC/SIP calls into ATF at all. Everything is plain register writes + regulators" — [Wi-Fi report](https://github.com/F-to-pay/PostmarketOS-begonia/blob/master/wifi/report-to-maintainer-wifi.md)

**Bring-up recipe**

These steps all come from the owner's report [Claim] — [Wi-Fi report](https://github.com/F-to-pay/PostmarketOS-begonia/blob/master/wifi/report-to-maintainer-wifi.md), [wifi/NOTES.md](https://github.com/F-to-pay/PostmarketOS-begonia/blob/master/wifi/NOTES.md):
- Power: genpd `MT6785_POWER_DOMAIN_CONN`, clock `CLK_INFRA_CCIF4_AP`, regulators `vcn18`, `vcn33_1_wifi` and `vcn33_2_wifi`.
- XO_WCN clock buffer: pwrap `DCXO_ENABLE` +0x190 bit 1, and MT6359 `DCXO_CW00` 0x788 (`EXTBUF2_MODE` = 0, `EXTBUF2_EN_M` = 1).
- Chip id: `0x180b1000+0x10 == 0x10020600`.
- EMI remap: written in INFRACFG_AO (0x10001000) at +0x380 and +0x388. The trap is that the vendor's `topckgen_base` is really INFRACFG_AO.
- RAM images are written into EMI, then the MCU reset is released. Alive marker: `0x18002600 == 0x1d1e`.
- BTIF at 0x1100c000, STP framing, WMT commands.
- The decisive trap: `patch_mcu` has to go through the PDA protocol over the **AP_DMA BTIF TX** vFIFO (0x11000b80), because PIO "silently loses bytes". `BTIF_DMA_EN` bit 1 = TX, bit 0 = RX.
- PDA target address `0x0001c000`.
- The STP RX buffer must be at least ~460 bytes (the RF-calibration event is a 454-byte frame).

**Firmware and user-space helpers**
- [Confirmed] Files required by `begonia-port`: `WIFI_RAM_CODE_soc1_0_2a_1.bin`, `soc1_0_patch_mcu_2a_1_hdr.bin`, `soc1_0_ram_bt_2a_1_hdr.bin`, `soc1_0_ram_mcu_2a_1_hdr.bin` and `soc1_0_ram_wifi_2a_1_hdr.bin`, plus `wifi.cfg` and `txpowerctrl.cfg`. The firmware directory is `/usr/lib/firmware/begonia-connsys` — [begonia-port APKBUILD](https://github.com/F-to-pay/PostmarketOS-begonia/blob/master/kernel-build/pmaports/device/testing/begonia-port/APKBUILD), [begonia-modprobe.conf](https://github.com/F-to-pay/PostmarketOS-begonia/blob/master/kernel-build/pmaports/device/testing/begonia-port/begonia-modprobe.conf)
- [Claim] The firmware was taken "from the vendor partition of a custom Android ROM (Project Infinity-X 3.12)". The author does not think it is redistributable. The firmware manifest is `t-neptune-mp-soc1_0e1-2015-KRUG_SOC1_0_E1_ASIC-20200924182102`, HW/SW id `0x8a00`. `mtsoc1_0_patch_e1_hdr.bin` is missing and harmless — [Wi-Fi report](https://github.com/F-to-pay/PostmarketOS-begonia/blob/master/wifi/report-to-maintainer-wifi.md), [wifi/NOTES.md Result #7](https://github.com/F-to-pay/PostmarketOS-begonia/blob/master/wifi/NOTES.md)
- [Confirmed] There is no `wmt_loader` or `wmt_launcher` equivalent in userspace. `begonia-wifi.sh` (run by `begonia-wifi.service`) does `modprobe consys_bringup bdaddr=<00:00:46:+md5(machine-id)>` then `modprobe wlan_6785_axi`, with a reboot-loop guard (`/var/lib/begonia/{starting,disabled}`). `consys_bringup` is blacklisted from DT autoload. The script comment still says "wlan_6785_axi must not be unloaded (oops) - restart only with a reboot" — [begonia-wifi.sh](https://github.com/F-to-pay/PostmarketOS-begonia/blob/master/kernel-build/pmaports/device/testing/begonia-port/begonia-wifi.sh)
- [Confirmed] The DT node uses compatible `xiaomi,begonia-consys-bringup` with regs `0x18002000` and `0x180b1000`, interrupts SPI 138 (btif) and 154 (rxdma), and a 4 MiB `no-map` EMI carve-out. Other blocks are mapped by hard-coded physical address: RGU 0x10007000, pwrap 0x1000d000, pinmux 0x10005000, BTIF 0x1100c000, AP_DMA 0x11000b80/0x11000c00, HIF_ON 0x18007000 — [consys-begonia.dtsi](https://github.com/F-to-pay/PostmarketOS-begonia/blob/master/wifi/consys-begonia.dtsi), [consys-bringup.c](https://github.com/F-to-pay/PostmarketOS-begonia/blob/master/wifi/consys-bringup.c)

**Reported Wi-Fi results [Claim]**
- `FW_START EVT success!!`, `Ready bit asserted`, `wlan0` and `wlan1` registered. NetworkManager scans 2.4 and 5 GHz, including DFS channel 120. It associates to WPA2-Enterprise (PEAP) on 5 GHz channel 120 and gets DHCP. Ping to the gateway: 0 % loss, 3.5-98 ms. Ping to the internet: 0 % loss, 14-400 ms ("latency/jitter is high … not investigated"). "No throughput measurement yet". Not tested: "throughput/stability over time, power management, suspend, error recovery (chip reset), regulatory behaviour, WPA3/SAE, AP mode" — [Wi-Fi report](https://github.com/F-to-pay/PostmarketOS-begonia/blob/master/wifi/report-to-maintainer-wifi.md)
- `glLoadNvram fail` gives a random MAC on each load. `rmmod wlan_6785_axi` used to oops; fixed on 2026-11-11 (Result #21) by calling `hifAxiRemove()` first in `exitWlan()`. The CONSYS module itself can only be replaced by rebooting — [wifi/NOTES.md](https://github.com/F-to-pay/PostmarketOS-begonia/blob/master/wifi/NOTES.md)
- On 2026-11-14 the notes (in Russian) describe BT and Wi-Fi breaking when toggled: `Opcode 0x0c13 failed: -110`, `STP tx window stuck`, `[WMT] NO WMT EVENT`. The cause was lost STP frames. Fix: host retransmit with a 180 ms timeout and the `7f 7f 7f 7f` resync pattern (patch 0019). Stress test: 17 Wi-Fi off/on cycles in parallel with BT alias changes, plus 3 `rfkill block/unblock all` cycles, gave "0 errors". The root cause of the frame loss is "not established" — [wifi/NOTES.md, last section](https://github.com/F-to-pay/PostmarketOS-begonia/blob/master/wifi/NOTES.md), [patch 0019](https://github.com/F-to-pay/PostmarketOS-begonia/blob/master/kernel-build/kernel/patches/0019-staging-mt6785-consys-Retransmit-unacknowledged-STP-.patch)

**Bluetooth [Claim unless noted]**
- `FUNC_CTRL(BT on)`, then H4 packets inside STP frames of type 0 over the same BTIF link, registered as a plain `hci_dev` (`HCI_UART`). The controller reports HCI 11 (BT 5.2), manufacturer 0x0046 (MediaTek). Three firmware quirks need host workarounds:
  - the driver answers opcode `0x0c77` locally;
  - it ORs `0x0f` into the LE event mask, because the firmware reports zeros in supported-commands octets 26-27;
  - it reprograms the BD_ADDR (vendor command `0xFC1A`) on every open.
- Reported results: inquiry (RSSI -27 dBm at ~0.5 m), an incoming ACL/L2CAP/AVDTP connection, an LE scan that saw 43 devices, SSP pairing and AVRCP, and a Sony WH-CH720N A2DP sink in PulseAudio. Not tested: HFP microphone, LE connections, throughput, sleep/wake.
- [Confirmed] RX was polled every 1-2 ms until patch 0021 (2026-11-14) switched to the BTIF interrupt.
- Sources: [bluetooth/NOTES.md](https://github.com/F-to-pay/PostmarketOS-begonia/blob/master/bluetooth/NOTES.md), [Wi-Fi report, BT section](https://github.com/F-to-pay/PostmarketOS-begonia/blob/master/wifi/report-to-maintainer-wifi.md), [patch 0021](https://github.com/F-to-pay/PostmarketOS-begonia/blob/master/kernel-build/kernel/patches/0021-staging-mt6785-consys-Sleep-on-the-BTIF-RX-interrupt.patch)

**Suspend [Claim]**
- System suspend fails on this kernel, independently of CONSYS. The errors are `mtu3 11201000.usb: PM: failed to suspend async: error -16` and `mediatek-drm: vblank wait timed out on crtc 0`. Once the panel power-off timed out and kwin dropped `/dev/dri/card0`. The owner's workaround is to disable auto-suspend (screen blank only). So "survives suspend" is untestable today — [docs/NOTES-system.md](https://github.com/F-to-pay/PostmarketOS-begonia/blob/master/docs/NOTES-system.md)

**The independent June effort (minorum/linux `begonia-conn-wifi`)**
- [Confirmed] Different architecture: a faithful forward-port of the vendor WMT stack (`wmt_drv`), the vendor BTIF driver and gen4m. 429 files changed, 418 of them new: 402 under `drivers/misc/mediatek/connectivity`, 14 under `drivers/misc/mediatek/btif`, plus DT and mt76/mt7615 touches. Line counts were not available from the API (diffs collapsed). The launcher's work is replayed in-kernel (`srh_rom_patch`, `srh_patch`, the `SET_STP_MODE` equivalent), and a `/dev/wmtWifi` trigger is reconstructed. An earlier "reimpl" mt76 WMAC path and a conninfra re-implementation were tried and then removed ("remove superseded reimpl conn drivers", 2026-06-18) — [compare](https://gitlab.nura.eco/minorum/linux/-/compare/6.16...begonia-conn-wifi), [commits](https://gitlab.nura.eco/minorum/linux/-/commits/begonia-conn-wifi)
- [Claim] Its commit messages report, on hardware: the conn-MCU reaches idle `0x1d1e` once the CONSYS EMI carve-out is pinned at `0xab000000` ("At 0xbc000000 the conn-MCU cannot fetch its firmware", 2026-06-16); chip id `0x6785` read; and finally "wlan0 scans 2.4+5GHz" (2026-06-19). No association, traffic or Bluetooth result is claimed — [commits](https://gitlab.nura.eco/minorum/linux/-/commits/begonia-conn-wifi)
- Conflict: (B)'s report places the CONSYS EMI carve-out at `0xbc000000` (dynamic allocation) and the Wi-Fi pool at `0xab000000`, and reports success. The minorum branch reports that `0xbc000000` fails and pins CONSYS EMI to `0xab000000`. Both claim working Wi-Fi bring-up, so the requirement is unresolved — [(B) Wi-Fi report](https://github.com/F-to-pay/PostmarketOS-begonia/blob/master/wifi/report-to-maintainer-wifi.md), [(B) wifi/NOTES.md Result #7](https://github.com/F-to-pay/PostmarketOS-begonia/blob/master/wifi/NOTES.md); contradicted by [minorum commit "pin CONNSYS EMI carveout to fixed 0xab000000"](https://gitlab.nura.eco/minorum/linux/-/commits/begonia-conn-wifi)
- [Confirmed] An Arch-based Kupfer Linux port for begonia (`criollojoel10/begonia-kupfer-linux`, 2026-09-26 → 2026-10-20) builds its kernel from `minorum/linux` at commit `3a1ea769` (the `begonia-conn-wifi` head). It says the stack compiles (`wmt_drv`, `wlan_gen4m`, `mtk-vendor-btif`), but its own status table lists "Flasheo y verificación en device: pendiente" (flashing and on-device check pending) and "Bluetooth interno ❌ falta el driver HCI" (HCI driver missing) — [Kupfer port README](https://github.com/criollojoel10/begonia-kupfer-linux), [linux PKGBUILD](https://github.com/criollojoel10/begonia-kupfer-linux/blob/main/overlay/linux/mt6785/PKGBUILD)

### Inferences
- **How much code:** the CONSYS + BT part a tablet port would actually own is about 3 kLOC (consys-bringup.c, h4_recv.h, the shim header and the DT). gen4m is a ~456 kLOC vendor blob in staging. Trimming the unused chips (mt7915, mt7961, soc3_0, mt66xx) would shrink it a lot, but it stays a large unreviewable vendor driver.
- **Portability to another MT6785 device: plausible.**
  - Most of `consys-bringup.c` is SoC-level: the hard-coded addresses are MT6785 SoC addresses, the CONSYS IP and its `soc1_0` firmware family are SoC properties, and the PMIC rails are the MT6359 LDOs that the YT-J706F also has (MT6359P).
  - Board-specific items to re-derive from the tablet's stock DT and vendor partition: the clock-buffer config (`clkbuf-config`, i.e. whether XO_WCN buf2 is SW-controlled), the CONN pinmux and drive values, the EMI carve-out placement (see the conflict above), `wifi.cfg`/`txpowerctrl.cfg` (antennas and power tables), the BT radio and NVRAM settings, and the tablet's own `soc1_0_*` files. The `2a_1` suffix comes from `WIFI_IP_SET=2` and flavor 'a' in mt6785 `plat_priv.c`, so the same names are likely but unverified.
  - The DT compatible string and module parameters are begonia-named and would need a tablet node.
  - If the tablet's Wi-Fi is the 2x2 SKU, the gen4m path configuration has not been exercised by either port.
- **Stability:** good enough for interactive use on one phone, per the owner. The STP layer was still losing frames as of 2026-11-14 (now masked by retransmit), MCU-assert recovery is absent, and power save is not investigated. Expect weeks, not days, to bring this to daily-driver quality on a tablet, and suspend is blocked by unrelated display and USB problems in the base tree.

### Gaps
- No raw dmesg, `iw` or `iperf` output, screenshots or video in either effort.
- Exact firmware file names on the YT-J706F: not checked. They need `adb shell ls /vendor/firmware`; see `hardware_inventory.md`.
- Whether the minorum vendor-WMT approach or (B)'s shim approach is more robust: no comparative data.

## 4. Audio and battery in (B): which drivers

### Takeaway
Audio is a new `sound/soc/mediatek/mt6785` ASoC platform driver (12.8 kLOC). It is built on the mainline mtk-afe framework, derived from the mainline mt8192 AFE with MT6785 register tables from the vendor tree, plus fixes to the mainline MT6359 codec and ACCDET and a minimal TFA9874 amplifier driver. Battery is a new mainline-style `mt6359_fgadc` power-supply driver plus an `mt6360_charger` patch. Both report working on the phone [Claim], with clock-gate workarounds and missing features. The fuel gauge is the most directly reusable piece for the YT-J706F (same MT6359P + MT6360). The begonia speaker path (TFA9874) is not reusable, because the tablet uses CS35L41 amplifiers.

### Cited Findings
**Audio driver code [Confirmed]**
- Patch 0015 "ASoC: mediatek: Add MT6785 AFE and MT6359 machine driver": "Port the MT6785 audio front end from the vendor 4.14 kernel to the mainline mtk-afe framework". It is 17 files, +12,755 lines:
  - core files: `mt6785-afe-pcm.c` 2,568, `mt6785-dai-i2s.c` 2,104, `mt6785-dai-adda.c` 1,398, `mt6785-reg.h` 3,133;
  - machine driver: `mt6785-mt6359.c` 668;
  - also the clock, GPIO, PCM and TDM DAI files.
- The IRQ handler includes interrupt-storm recovery. The machine driver binds the AFE to MT6359 (headphones, earpiece, AIN0/AIN2 microphones, ACCDET) and TFA9874 on I2S3.
- Sources: [patch 0015](https://github.com/F-to-pay/PostmarketOS-begonia/blob/master/kernel-build/kernel/patches/0015-ASoC-mediatek-Add-MT6785-AFE-and-MT6359-machine-driv.patch), [patches 0011-0014](https://github.com/F-to-pay/PostmarketOS-begonia/tree/master/kernel-build/kernel/patches)
- Patch 0014 is a minimal TFA9874 driver (`sound/soc/codecs/tfa9874.c`, 815 lines) with no DSP. It loads registers from a decoded vendor container, has a fault poller for OCP/OTP/UVP, and caps hardware gain at -18 dB. Patches 0011-0013 cover a separate AP interrupt in mtk common, the mt6359 inverted gains and mic types, and the accdet cell name — [patch 0014](https://github.com/F-to-pay/PostmarketOS-begonia/blob/master/kernel-build/kernel/patches/0014-ASoC-codecs-Add-a-minimal-NXP-TFA9874-amplifier-driv.patch)

**Audio approach and traps [Claim]**
- "the AFE register layout of MT6785 is the same generation as mainline mt8192 (2441 of 2450 register defines are identical)". So the driver is mt8192 AFE + `common/` + mainline `mt6359.c`, with `top_apll{1,2}_d4` → `_d8`.
- DT: `afe` node with compatible `mediatek,mt6785-audio`, SPI 184, 33 clocks; `sound` node with compatible `mediatek,mt6785_mt6359`.
- Traps:
  - reading the ASRC block while gated by `AUDIO_TOP_CON1` bits 12-14 hard-hangs the SoC;
  - `AUDIO_TOP_CON0` bit 2 (`aud_afe`) stays set despite CCF enable, so the driver force-clears it after `regcache_sync`. Root cause not found;
  - the MT6359 headset, lineout and handset volume scales are inverted in the mainline-derived driver (control value 0 = +8 dB). "Worth a look at the upstream driver";
  - the microphones need mic type DCC.
- Sources: [audio report](https://github.com/F-to-pay/PostmarketOS-begonia/blob/master/audio/report-to-maintainer-audio.md), [audio/NOTES.md](https://github.com/F-to-pay/PostmarketOS-begonia/blob/master/audio/NOTES.md)

**Audio results [Claim]**
- Headphones and main microphone through PulseAudio at 48 kHz (2026-11-12).
- TFA9874 speaker "works, switchable from PulseAudio" (2026-11-12 18:27), with a high-pass filter and amplifier protection.
- ACCDET jack detection (2026-11-12 22:00), dual-mic noise suppression ("verified on synthetic signals"), earpiece "works, quiet" (2026-11-13).
- Known issues: AFE IRQ storm (fixed), `ASoC error (-16)`, a ~100 ms click at capture start, leftover debug module parameters (`stage`, `ungate0/1`, `keep_intbus`). An unsafe-loudness incident happened while the gain scale was inverted.
- Sources: [audio/NOTES.md](https://github.com/F-to-pay/PostmarketOS-begonia/blob/master/audio/NOTES.md), [audio report](https://github.com/F-to-pay/PostmarketOS-begonia/blob/master/audio/report-to-maintainer-audio.md)

**Battery and charging**
- [Confirmed] Patch 0001 adds a new `drivers/power/supply/mt6359_fgadc.c` (543 lines), an MFD cell `mt6359-fgadc` in `mt6397-core.c`, Kconfig and a DT binding. It is +626 lines over 6 files. Patch 0002 makes `mt6360_charger` follow the USB source current and battery limits through a power-supply notifier — [patch 0001](https://github.com/F-to-pay/PostmarketOS-begonia/blob/master/kernel-build/kernel/patches/0001-power-supply-Add-MediaTek-MT6359-PMIC-fuel-gauge-dri.patch), [patch 0002](https://github.com/F-to-pay/PostmarketOS-begonia/blob/master/kernel-build/kernel/patches/0002-power-supply-mt6360_charger-Follow-the-USB-source-cu.patch)
- [Confirmed] Quality defect: in patch 0001 the `mediatek,mt6397.yaml` hunk adds the line `:  /schemas/power/supply/mediatek,mt6359-fgadc.yaml#`. The `$ref` key is missing, apparently lost to shell expansion, so the binding is malformed — [patch 0001](https://github.com/F-to-pay/PostmarketOS-begonia/blob/master/kernel-build/kernel/patches/0001-power-supply-Add-MediaTek-MT6359-PMIC-fuel-gauge-dri.patch)
- [Claim] Gauge method: FGADC latched reads (`FGADC_CON1` 0x0d0a, current `0x0d8a`, coulomb counter `0x0d16/0x0d18`), current LSB 610.352 µA and charge LSB 0.085 µAh for a 5 mΩ shunt. The capacity starts from an OCV table (vendor 25 °C profile resampled into `simple-battery`) and is then driven by coulomb counting.
- [Claim] Measured: FGADC current within ~3 % of the MT6360 IBAT ADC; coulomb counter 3969 vs 3946 µAh over 42 s. The input current limit rises from 500 mA to 2 A with a 5 V/2 A PD source.
- [Claim] Not done: temperature compensation, keeping the state of charge across reboots, Qmax learning, end-of-charge handling, and the "cable plugged at boot" case (the notifier misses it).
- [Claim] A `power-supplies = <&tcpc>` DT link deadlocks the probe.
- Sources: [battery report](https://github.com/F-to-pay/PostmarketOS-begonia/blob/master/battery/report-to-maintainer-battery.md), [battery/NOTES.md](https://github.com/F-to-pay/PostmarketOS-begonia/blob/master/battery/NOTES.md)
- [Confirmed] For comparison, Dinolek's own battery approach is the `battery-downstream` branch (last commit 2025-08-28): downstream `mtk_battery` made to compile. It is not in the 6.16 or 7.1 branches, nor in the package — [Nura linux branches](https://gitlab.nura.eco/mt6785-mainline/linux/-/branches), [Dinolek branches](https://github.com/Dinolek/mt6785-mainline/branches)

### Inferences
- **For the YT-J706F:**
  - **AFE:** probably reusable as is at the SoC level (same MT6785 AFE).
  - **Machine driver:** has to be rewritten. The tablet has CS35L41 amplifiers (mainline driver, but needing Cirrus firmware and tuning files) and an AS33970 voice DSP, and no 3.5 mm jack, so ACCDET and the TFA9874 driver do not apply (see `hardware_inventory.md`).
  - **Fuel gauge:** applies directly (MT6359P). The tablet's stock DTB reports `R_FG_VALUE = 5` (5 mΩ, the same shunt the driver assumes) — [hardware_inventory.md](hardware_inventory.md). It needs a tablet OCV table from Lenovo's battery profile.
  - **Charger:** applies (MT6360). The tablet's optional RT9465 slave charger has no mainline driver.
- The audio clock workarounds and the malformed binding show what "unreviewed" means here. Budget time for review and cleanup before relying on the code.

### Gaps
- No recordings, measurements or logs of the audio claims are published (recordings excluded as private).
- Whether the CS35L41 + MT6785 AFE + TDM routing works: untested anywhere.

## 5. Other sources: Dinolek branches, Nura packaging, newer work, uniLoader

### Takeaway
Nothing official has moved since June. Dinolek's tree has three branches, the newest commit dated 2026-06-17 (7.1). The Nura group has only `linux` and `firmware`, and the firmware repo holds only touchscreen firmware. pmaports still ships 6.16.4, and the 7.1 update is an open Draft MR untouched since 2026-07-17. uniLoader is a tiny second-stage bootloader that embeds kernel, DTB and initramfs and chain-loads them from the stock bootloader. Begonia needed it only during early bring-up (2025-08), when the stock LK ignored the mainline DTB. The packaged port now boots a normal boot.img v2 with the mainline DTB, because the DT carries "nodes required by lk".

### Cited Findings
**Dinolek's tree and Nura packaging [Confirmed]**
- GitHub `Dinolek/mt6785-mainline` (default `7.1`, `pushed_at` 2026-06-17):
  - `6.16` = `203a993f`, 2025-09-04;
  - `7.1` = `811c3c80`, 2026-06-17;
  - `battery-downstream` = `fad73078`, 2025-08-28 ("Enable pmic fuel gauge and battery manager").
- In the 7.1 compare against v7.1, only one commit subject matches audio, Wi-Fi, connectivity, battery or suspend keywords, and it is the CCI interconnect binding (2025-07-09). There is no AFE, CONSYS or gauge work.
- Sources: [branches](https://github.com/Dinolek/mt6785-mainline/branches), [compare v7.1...7.1](https://github.com/Dinolek/mt6785-mainline/compare/8cd9520d35a6c38db6567e97dd93b1f11f185dc6...7.1)
- Nura GitLab group `mt6785-mainline` has two projects:
  - `linux`: same three branches; tags `6.16.4-r0` (2025-09-04) and `7.1-r0` (2026-06-17); last activity 2026-06-22.
  - `firmware`: branch `begonia` at `ea59e1c` (2026-06-17) containing only `novatek/nt36672a_begonia_{csot,tianma}.bin.zst`; tags `begonia-20250810-r0` and `begonia-20260617-r0`.
  - Sources: [group linux](https://gitlab.nura.eco/mt6785-mainline/linux), [group firmware](https://gitlab.nura.eco/mt6785-mainline/firmware)
- The Kupfer README states the firmware repo contains `WMT_SOC.cfg` and the `soc1_0_*` blobs [Claim], but the `begonia` branch head I listed only has the two touchscreen files [Confirmed] — [Kupfer README](https://github.com/criollojoel10/begonia-kupfer-linux), [firmware tree](https://gitlab.nura.eco/mt6785-mainline/firmware/-/tree/begonia)
- `nura/pmaports` MRs:
  - !6975 "xiaomi-begonia: Mainline port" by Dinolek, merged 2025-09-05;
  - !8852 "Draft: Update mt6785 kernel to 7.1, add support for Tianma variant to Redmi Note 8 Pro" by Dinolek, opened 2026-06-17, last updated 2026-07-17, still open;
  - !8987 "device-xiaomi-begonia: add vbmeta partition for AVB", opened 2026-07-09;
  - !9851 "firmware-xiaomi-begonia: install to /usr/lib", merged 2026-11-04.
  - No MR adds Wi-Fi, audio or the gauge — [MR 8852](https://gitlab.nura.eco/nura/pmaports/-/merge_requests/8852), [MR 6975](https://gitlab.nura.eco/nura/pmaports/-/merge_requests/6975), [MR 9851](https://gitlab.nura.eco/nura/pmaports/-/merge_requests/9851)
- Another MT6785 device on the same tree: Realme 6 (`Hari-Pi/realme6-pmos-port`, "Mainline 6.16.4 based on the `mt6785-mainline` fork") boots to USB SSH, with the panel driver not yet ported (pushed 2026-10-02) — [repo](https://github.com/Hari-Pi/realme6-pmos-port)

**uniLoader**
- [Confirmed] Definition from the Nura wiki: uniLoader "is a secondary bootloader that is capable of loading Linux for Android and iOS based devices. Such bootloader embeds ramdisk, upstream kernel and DTB into its own binary image … and finally, after relocating upstream kernel, it jumps to the latter". Porting needs a board file (a simplefb framebuffer description) and a defconfig (`CONFIG_TEXT_BASE`, `CONFIG_PAYLOAD_ENTRY`, `CONFIG_RAMDISK_ENTRY`, optional position-independent mode) — [wiki: UniLoader](https://wiki.nura.eco/wiki/UniLoader)
- [Confirmed] Repo `ivoszbg/uniLoader`: 157 stars, pushed 2026-11-12.
  - MT6785 / begonia support came from PR #41 "board: introduce support for Xiaomi Redmi Note 8 Pro" (opened 2025-08-08, merged 2025-10-04).
  - `configs/begonia_defconfig` (`CONFIG_MT6785=y`, `CONFIG_XIAOMI_BEGONIA=y`, `CONFIG_TEXT_BASE=0x40080000`) was added on 2026-07-10.
  - The Lenovo boards present are `p1ma40` and `tb373fu`; there is no YT-J706F board.
  - Sources: [repo](https://github.com/ivoszbg/uniLoader), [PR 41](https://github.com/ivoszbg/uniLoader/pull/41), [begonia_defconfig](https://github.com/ivoszbg/uniLoader/blob/HEAD/configs/begonia_defconfig), [board/lenovo](https://github.com/ivoszbg/uniLoader/tree/HEAD/board/lenovo)
- [Confirmed] Why begonia needed it (wiki revision of 2025-08-22, user Cristianc): early mainline boot needed a fixed `earlycon` driver, a minimal custom DTBO and a cmdline patch, "However … mainline devicetree is ignored by stock bootloader and not loaded at all. In order to make this problem solved, a second stage bootloader is required", and uniLoader "bypassed" the stock-bootloader limitations so "mainline DTB is loaded and fully working". The uniLoader text was moved to its own page that same day. The early-bringup section disappeared in Dinolek's edits of 2025-09-05 (page size 15,819 → 13,044 bytes) — [old revision 82242](https://wiki.nura.eco/index.php?oldid=82242), [history](https://wiki.nura.eco/index.php?title=Xiaomi_Redmi_Note_8_Pro_(xiaomi-begonia)&action=history)
- [Confirmed] Dinolek commit `7e25c308ec5b` (2025-07-18), "Add nodes required by lk", adds `chosen { bootargs = ""; }`, an empty `reserved-memory` and `scp { compatible = "mediatek,scp"; }`, each commented "needed by Little Kernel". The packaged `deviceinfo` builds a standard image (`--header_version 2 --dtb /boot/dtbs/mediatek/mt6785-xiaomi-begonia.dtb --recovery_dtbo /boot/empty.dtbo`, fastboot, `flash_kernel_on_update`). There is no uniLoader in the install path — [commit](https://github.com/Dinolek/mt6785-mainline/commit/7e25c308ec5bc477feba548194b17ff5bf10c881), [deviceinfo](https://gitlab.nura.eco/nura/pmaports/-/blob/main/device/testing/device-xiaomi-begonia/deviceinfo), [wiki install section](https://wiki.nura.eco/wiki/Xiaomi_Redmi_Note_8_Pro_(xiaomi-begonia))
- [Claim] Kupfer's begonia notes say the kernel cmdline must contain `bootopt=64S3,32N2,64N2` — [Kupfer README](https://github.com/criollojoel10/begonia-kupfer-linux)
- [Confirmed] (B) also relies on this LK path: its notes warn that `apk upgrade` → `mkinitfs`/`boot-deploy` rebuilds boot.img from `/boot/dtbs/.../mt6785-xiaomi-begonia.dtb` and reflashes `boot`. This is consistent with LK accepting the DTB carried in boot.img — [wifi/NOTES.md "PITFALL (2026-11-11)"](https://github.com/F-to-pay/PostmarketOS-begonia/blob/master/wifi/NOTES.md)

### Inferences
- **Why the ports "need" uniLoader:**
  - historically, because MediaTek LK on begonia did not load the mainline DTB (it expects certain nodes it patches: `chosen`, `reserved-memory`, `scp`);
  - today begonia avoids it by adding those nodes;
  - uniLoader stays the fallback when a vendor LK rejects or ignores the DTB or patches it destructively.
- For the YT-J706F, the first boot experiment should try the "LK-compatible DTB in boot.img v2" path (Dinolek's three nodes, an empty `recovery_dtbo`, `bootopt=` in the cmdline). Keep a uniLoader board port (simplefb at the tablet's framebuffer address) as plan B. Lenovo's LK behaviour is unverified.
- No newer upstream-track Wi-Fi or audio work exists. All Wi-Fi/BT/audio/gauge code for MT6785 lives in two personal, unreviewed trees (the minorum June branch for Wi-Fi only, and (B) from November for everything).

### Gaps
- Matrix rooms (Nura/postmarketOS mainline and MediaTek channels) were not searchable from here. An announcement or discussion of either Wi-Fi effort may exist there.
- Whether Dinolek intends to merge either Wi-Fi effort: no public statement found.
- Whether Lenovo's YT-J706F LK accepts a mainline DTB with the same three nodes: unknown.
