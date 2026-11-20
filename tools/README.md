# Host tools (`tools/`)

Utilities for targeting, flashing, backing up, and test-booting the Lenovo Yoga Tab 11 (`YT-J706F`) over USB from macOS, plus bring-up probes that run on the tablet itself.

## Scripts

- [`yt.sh`](yt.sh): source before running `adb` commands to target the tablet by transport id (`yt`, `ytadb`) and strip identifiers (`redact`).
- [`ytssh`](ytssh): on the Mac, `ssh` as root to the tablet's Linux over the USB network (`192.168.77.1`); its arguments are the remote command. Batch mode, no host-key check, a 5 s connect timeout and keepalives so a call fails fast when the tablet dies, and `-n` so it never reads the calling script's stdin.
- [`push-modules.sh`](push-modules.sh): on the Mac, stream a kernel build's `modules.tar.xz` (default `out/kernel/modules.tar.xz`) over SSH into the running Omarchy root: replaces `/usr/lib/modules/<release>`, removes its `build` link and runs `depmod` (`YT11_HOST` overrides the address).
- [`mk-extras-cpio.sh`](mk-extras-cpio.sh): on the Mac (Docker image `lenovomarchy-kbuild`), build a second initramfs archive holding the named modules with their dependencies, decompressed (busybox cannot load `.ko.zst`), plus a firmware tree, to append to the main initramfs: `mk-extras-cpio.sh <modules.tar.xz> <firmware dir> <out.cpio.gz> <module>...`.
- [`mkboot.sh`](mkboot.sh): pack `Image.gz`, a mainline `.dtb`, and an initramfs into `boot.img` (Android header v2) plus an empty `dtbo.img`; `--cmdline "<args>"` (first argument) appends kernel arguments to the built-in ones.
- [`mkdtbo.py`](mkdtbo.py): build an Android DT table image (`dtbo.img`) from one or more `.dtbo` overlay blobs.
- [`flash-slot.sh`](flash-slot.sh): flash `boot_<slot>` and optional `dtbo_<slot>`, set the active slot, and reboot (enters fastboot via `adb` or `mtk-preloader`, after asking a running Linux to reboot through `ytssh`).
- [`linux-test.sh`](linux-test.sh): flash Linux to slot A, poll for `LINUX_UP` (SSH at `192.168.77.1`), `FELL_BACK` (Android slot `_b` + pstore), or `TIMEOUT`, and save redacted logs.
- [`flash-rootfs.sh`](flash-rootfs.sh): convert the root image `image/build-rootfs.sh` produced to a sparse image (via `img2simg` on PATH, `lenovomarchy-kbuild`, or `debian:bookworm-slim`) and write it to `userdata` (everything on the tablet's Linux side is lost); the tablet stays in fastboot for `flash-slot.sh`: `flash-rootfs.sh <rootfs.img>`. Full sequence in [`image/README.md`](../image/README.md), "Fresh install".
- [`image-set-key.sh`](image-set-key.sh): on the Mac (`alpine:3.22` + `debugfs`), install SSH public key(s) into a raw ext4 rootfs image for `root` and `alarm`, verify readback and run `e2fsck -fn`: `image-set-key.sh <rootfs.img> <key.pub> [<key.pub>...]`.
- [`install.sh`](install.sh): one-command installer from release files (`--key <key.pub> [--firmware <super.img>] [--slot a|b] [--yes] [--dry-run] <rootfs> <boot.img> <dtbo.img>`): decompresses the rootfs, injects the SSH key, flashes `userdata` and the boot slot, waits for USB SSH, and optionally installs stock firmware.
- [`rootfs-update.sh`](rootfs-update.sh): on the Mac (privileged `alpine:3.22` arm64 container), update a built Omarchy root image in place for the current kernel: replace `/usr/lib/modules` from a `modules.tar.xz` and run `depmod` in a chroot, install `yt11-bootctl` and enable `yt11-boot-successful.service`, which marks the A/B slot successful once `multi-user.target` is reached. An optional third argument also writes a sparse copy (`img2simg`) for fastboot: `rootfs-update.sh <rootfs.img> <modules.tar.xz> [<out.simg>]`.
- [`backup-partitions.sh`](backup-partitions.sh): stream and SHA-256 verify all partitions (except `userdata`), UFS boot LUs, and GPT headers over root `adb` into `private/`.
- [`mtk-preloader/preloader_fastboot.py`](mtk-preloader/preloader_fastboot.py): catch the MediaTek preloader CDC-ACM boot window and send `FASTBOOT` (or `METAMETA`) without hardware keys; protocol notes in [`mtk-preloader/README.md`](mtk-preloader/README.md).
- [`mtk-preloader/test_preloader_fastboot.py`](mtk-preloader/test_preloader_fastboot.py): pty-based unit tests for `preloader_fastboot.py`.
- [`lp-extract.py`](lp-extract.py): on the Mac, minimal reader for raw or Android sparse logical-partition (`super`) metadata: `lp-extract.py <super.img>` lists the partitions with their size and extent count, `lp-extract.py <super.img> <name> <out.img>` copies one partition out (linear extents only). Used by `amp-firmware.sh`, `mic-firmware.sh`, and `touch-firmware.sh`.
- [`amp-firmware.sh`](amp-firmware.sh): extract the CS35L41 speaker-protection DSP firmware and per-amp tunings from the unit's stock `super` image into `private/`, and with `--install` copy them to the tablet under the names mainline loads (`YT11_HOST` overrides the address).
- [`mic-firmware.sh`](mic-firmware.sh): extract the AS33970 voice processor's firmware image from the unit's stock `super` image into `private/`, and with `--install` copy it to the tablet as `/usr/lib/firmware/tahiti/partition_boot2flash.img`, the file the `snd-soc-as33970` driver loads at every start (no microphones without it).
- [`touch-firmware.sh`](touch-firmware.sh): extract the Himax touch firmware from the stock `super` image, optionally install it.
- [`wifi-cycle.py`](wifi-cycle.py): on the tablet as root (`/dev/mem`), power-cycle the MT7663 Wi-Fi chip: unbind the MMC1 host (`11240000.mmc`), hold the chip's enable line GPIO99 low for `low_ms` (default 200), raise it, wait `high_ms` (default 150), clear the kernel log and rebind the host, then print GPIO149 (the chip's interrupt line), GPIO10 (its role is not stated in the source), the last `mmc1`/`sdio` kernel messages and any SDIO device: `wifi-cycle.py [low_ms] [high_ms]`.
- [`audio/audprobe.py`](audio/audprobe.py): on the tablet, play digital silence on the muted speaker path and dump the AFE I2S registers, pad levels and CS35L41 power/PLL status.
- [`audio/tahiti_load.py`](audio/tahiti_load.py): on the tablet, load the AS33970 voice processor's firmware over i2c-dev (`--bus` is the i2c9 adapter's number). The kernel driver does this itself now; the tool stays for experiments. Offline tests in [`audio/test_tahiti_load.py`](audio/test_tahiti_load.py).

### Camera bring-up (`tools/camera/`)

Unless noted, these run on the tablet as root. They target the rear OV8856 (cam0) through the bring-up modules `mt6785-camsv-tm` and `yt11-cam-probe` (register-level, debugfs) or the V4L2 drivers `mt6785-seninf` and `mt6785-camsv`. Findings are in [`docs/hardware/CAMERA.md`](../docs/hardware/CAMERA.md).

- [`camera/cam-id.py`](camera/cam-id.py): read-only scan of `/dev/i2c-N` (0x08-0x77) that lists the addresses that ACK (flagging likely VCM and EEPROM addresses), then reads the chip-ID registers at known sensor addresses to recognise OV8856, S5K4H7, S5KGW1, S5K3T1/T2, GC5035, GC2375 or OV02A10: `cam-id.py <bus>`. Power a camera slot first through `/sys/kernel/debug/yt11-cam/power`.
- [`camera/larb-bypass.py`](camera/larb-bypass.py): clear `MMU_EN` on the camera SMI local arbiter ports (LARB6, LARB7) through `/dev/mem`, so CAMSV DMA without IOMMU bindings writes to a physical CMA address; `--status` only prints the bits. Needs `CONFIG_DEVMEM` without `IO_STRICT_DEVMEM` and the camera power and LARB clocks on.
- [`camera/cap-tm.sh`](camera/cap-tm.sh): with `mt6785-camsv-tm` loaded, program the SENINF test-pattern generator and CAMSV0 IMGO DMA through `/sys/kernel/debug/camsv-tm` (after `larb-bypass.py`), capture one frame, and save it raw (`-o`, default `/tmp/tm-frame.raw`) and as a grayscale PNG through `raw2png.py` (`-p`, or `-n` for none). `-w`/`-l` set the size (default 640x480), `-k le10|p12` the DMA byte layout; environment variables override some register values.
- [`camera/ov-cap.py`](camera/ov-cap.py): register-level OV8856 MIPI CSI-2 capture through SENINF and CAMSV0 without the V4L2 drivers: powers the sensor (`--power-mode auto|probe|sysfs|none`), loads its register tables over `/dev/i2c-N`, configures the CSI port, lanes and DPHY settle, and saves a raw frame (`--out`, default `/tmp/ov.raw`; optional `--png` through `raw2png.py`). Key options: `--csi-port`, `--seninf`, `--mux`, `--lanes`, `--i2c-bus`/`--i2c-addr` (default `/dev/i2c-2`, `0x36`), `--testpat`, `--exposure`, `--again`, `--frames`, `--layout le10|p12`, `--w`/`--l`.
- [`camera/ov-expo.py`](camera/ov-expo.py): read (no options) or write OV8856 exposure, analogue and digital gain, VTS, test pattern and flip/mirror over `/dev/i2c-N` (default bus 2, address `0x36`). `--auto FILE.raw` measures a MIPI RAW10-packed frame's mean level above black and suggests exposure and gains, `--apply` writes them; with all four `--cur-*` values given, `--auto` needs no I2C access and runs offline.
- [`camera/vcm-probe.py`](camera/vcm-probe.py): identify the rear camera's autofocus actuator at `0x0c` on I2C bus 2 (the part is unknown) by trying the identification reads of the dw9714, dw9719, dw9768, dw9807 and ak7375 driver families: `vcm-probe.py [bus] [-a addr]`. `--proto <family> --pos N` prints the focus-position write in that protocol, `--write` sends it (moves the lens). The vcamaf rail (GPIO197) must be on.
- [`camera/v4l2-capture.sh`](camera/v4l2-capture.sh): capture through the V4L2 media controller: enable the link of the chosen sensor (`-c ov8856|s5k4h7`), set the sensor mode (`-s WxH`, default 640x480) and matching pad and video formats with `media-ctl`/`v4l2-ctl`, stream `-n` frames (default 10) into `-o` (default `/tmp/mt6785-frame.raw`), and convert the last frame to a PNG (`-p`) with `raw2rgb.py --layout u16`. `-e`/`-g` set exposure and analogue gain, `-t` the sensor test pattern, `-d` the media device. Needs `v4l-utils`.
- [`camera/layout-sweep.sh`](camera/layout-sweep.sh): CAMSV packer experiments: for each `FMT_SEL:PAK:BPPX8` candidate (built-in list, or arguments such as `0x102:1:10`), write the `mt6785_camsv` module parameters, capture test-pattern frames with `v4l2-capture.sh`, save `/tmp/sweep-<fmt>-<pak>-<bpp>.raw` and print bytes of two lines, a 16-bit word decode and the CAMSV counters; the parameters are restored on exit. Options `-d`, `-c`, `-n`, `-w`, `-h` (height), `-l` (line to print).
- [`camera/raw2png.py`](camera/raw2png.py): Mac or tablet (standard library only): convert a CAMSV raw frame to an 8-bit grayscale PNG keeping the top 8 bits of each pixel, for a quick look at the Bayer grid: `raw2png.py <frame> <width> <height> [--layout le10|p12|raw10] [stride] <out.png>` (layout detected from size and content when omitted).
- [`camera/raw2rgb.py`](camera/raw2rgb.py): Mac or tablet (standard library only): convert a raw frame to an 8-bit RGB PNG: unpack (`--layout le10|p12|raw10|u16|u16h`, detected when omitted), subtract the black level (`--black-level`, default 64), white-balance (`--wb grey|none`), apply gamma (`--gamma`, default 2.2) and demosaic (2x2 half resolution, or bilinear full resolution with `--full`). `--bayer` sets the CFA order (default `bggr`), `--auto` tries all four. Takes the same positional arguments as `raw2png.py`, or `-o`/`--stride`.
- [`camera/test_raw2rgb.py`](camera/test_raw2rgb.py): offline `unittest` suite for `raw2rgb.py`, run on the Mac with `python3 tools/camera/test_raw2rgb.py`: synthetic frames for every layout and Bayer order, layout detection, and two recorded OV8856 640x480 le10 frames in `camera/samples/` (colour bars and a scene).
- [`camera/lsc-fit.py`](camera/lsc-fit.py): Mac or tablet (standard library only): fit lens shading correction coefficients from raw frames of a uniformly lit white surface (several frames are averaged) and print the libcamera `Lsc` block (`centre`, then `red`/`green`/`blue` `[ k1, k2, k3 ]` for gain(r) = 1 + k1 r² + k2 r⁴ + k3 r⁶) with the fit residuals, corner gains and centre levels as comments: `lsc-fit.py <frame> <width> <height> --bayer RGGB|BGGR|GRBG|GBRG [--layout ...] [--black-level 64] [--centre auto|X,Y] [--grid 32] [frame2 ...]`. Unpacks with `raw2rgb.py`, reduces each channel to a grid of cell means (cells with samples >= 1000 ignored), estimates the optical centre from the green plane by a residual-minimising search, and keeps a gain of 1 at the centre of every channel. Exits 1 when the frame is unusable (under half the cells valid, a centre level under 100, or an RMS residual above 5 %). `--check <yaml>` applies an `Lsc` block (alone or in a tuning file) to the frame and prints the remaining centre-to-corner falloff.
- [`camera/test_lsc_fit.py`](camera/test_lsc_fit.py): offline `unittest` suite for `lsc-fit.py`, run on the Mac with `python3 tools/camera/test_lsc_fit.py`: synthetic flat fields with known coefficients and an off-centre optical centre in all four Bayer orders and the `u16` and `le10` layouts, clipped cells, unusable frames, multi-frame averaging and `--check`.

### Display bring-up (`tools/display/`)

Debug tools from the DSI bring-up, described in [`docs/hardware/DISPLAY.md`](../docs/hardware/DISPLAY.md). They run on the tablet as root and read or write MT6785 display registers directly through `/dev/mem` (DSI0 at `0x14014000`); several headers name them `yt11-<name>`.

- [`display/regdump.py`](display/regdump.py): print `block offset value` lines for the display-path blocks (MIPI TX, MMSYS, OVL, RDMA, colour, CCORR, AAL, gamma, dither, DSI0, mutex, postmask), so two states (LK's and mediatek-drm's) can be diffed. Read-only, no arguments.
- [`display/regload.py`](display/regload.py): write values from a `regdump.py` file back into the hardware and print old and new values: `regload.py <dump> <block>[:off,off,...] ...` (every offset of the block when none is listed).
- [`display/pagedump.py`](display/pagedump.py): dump the 32-bit words of whole register pages in the same format: `pagedump.py name=base[:size] ...` (size defaults to `0x1000`). Read-only.
- [`display/dsirate.py`](display/dsirate.py): optionally write DSI0 registers (`dsirate.py [off=val ...]`, hex), then print the input and DSI output line periods, their ratio, and whether the underrun bit recurs.
- [`display/dsiframe.py`](display/dsiframe.py): for about 50 ms, log DSI0 vertical phase changes (VSA, VBP, VACT, VFP) against input line milestones. Read-only, no arguments.
- [`display/dsimon.py`](display/dsimon.py): clear DSI0 `INTSTA` three times and record when each status bit (frame done, TE timeout, VBP/VACT/VFP start, underrun, BTA timeout, input unfinished) reappears within 60 ms, then print the stall and shadow debug registers.
- [`display/dsiwatch.py`](display/dsiwatch.py): `dsiwatch.py [seconds] [interval_frames]` (defaults 30 and 6): print the DSI0 pull ratio (output line period over input line period, measured within one VACT) with CLOCK_MONOTONIC timestamps comparable with dmesg, whenever it changes and every few frames. Read-only.
- [`display/dsireinit.py`](display/dsireinit.py): `dsireinit.py [regsfile]`: stop DSI0, reset its engine, rewrite its configuration registers with their current values (or the `dsi0` lines of a `regdump.py` file), and restart video mode.
- [`display/dsidcs.py`](display/dsidcs.py): `dsidcs.py <cmd> ...`: switch DSI0 to command mode, send each command (comma-separated hex command-queue words, e.g. `773a1500` for the DCS short write `0x3a 0x77`), print the interrupt status and read-back registers, and return to video mode.

## Day-to-day kernel cycle

With Omarchy running on the tablet and answering on the USB network:

```bash
kernel/kbuild.sh
tools/push-modules.sh
tools/mkboot.sh --cmdline "yt11.root=<root device>" out/kernel/Image.gz \
    out/kernel/dtbs/mediatek/mt6785-lenovo-yt-j706f.dtb <ramdisk> <outdir>
tools/flash-slot.sh a <outdir>/boot.img <outdir>/dtbo.img
```

1. [`kernel/kbuild.sh`](../kernel/kbuild.sh) builds the kernel in Docker and writes `out/kernel/Image.gz`, `out/kernel/dtbs/mediatek/*.dtb` and `out/kernel/modules.tar.xz`.
2. `tools/push-modules.sh` installs `out/kernel/modules.tar.xz` (its default argument) into the running root over SSH, so the new kernel finds its modules at the next boot.
3. `tools/mkboot.sh` writes `<outdir>/boot.img` and `<outdir>/dtbo.img`. `--cmdline` must be the first argument; its value is appended to the built-in `console=tty0 loglevel=7 panic=5 oops=panic mem_sleep_default=s2idle`. The initramfs `/init` reads `yt11.root=` and switches to that root device ([`initramfs/README.md`](../initramfs/README.md)). `<ramdisk>` is `out/initramfs/initramfs.cpio.gz` from `initramfs/build.sh`, optionally concatenated with an archive from `mk-extras-cpio.sh`.
4. `tools/flash-slot.sh` reaches fastboot, writes `boot_a` and `dtbo_a`, sets slot `a` active and reboots; the `dtbo.img` argument is optional. To wait for the boot result and keep its logs, run `tools/linux-test.sh <boot.img> <dtbo.img>` instead (below).

## One-command Linux boot test

```bash
tools/linux-test.sh [--timeout SECONDS] [--no-flash] <boot.img> <dtbo.img>
```

- Creates `${YT11_RUNS_DIR:-private/runs}/<UTC timestamp>/run.log` and records image SHA-256 digests.
- Exit codes: `0` `LINUX_UP` (saves `dmesg.log`, `uname.txt`, `model.txt`, `devices.txt`, `devices_deferred.txt` if present, `lsmod.txt`, `ip-addr.txt`), `3` `FELL_BACK` (runs `adb root`, waits for `sys.boot_completed=1`, saves `bootreason.txt` and decompressed/redacted `/sys/fs/pstore/*`), `4` `TIMEOUT` (default `420` s), `1` error.
- All outputs are filtered through `redact` (no serial numbers or `Kernel command line` lines written to disk).
- Offline test suite: `bash tests/linux-test/run-tests.sh`.

## Checking the interface with nobody at the screen

- `tools/ytshot <out.png> [scale]`: screenshot of the tablet's screen (grim in
  the Hyprland session), copied to the Mac.
- `tools/faketouch.py`: runs on the tablet as root (copy it to `/tmp`) and
  injects taps, long presses and swipes through a uinput touchscreen;
  `--transform 1` takes screen coordinates when the tablet stands in
  landscape. Used on 2026-11-18 to go through the lock screen (swipe up,
  password on the on-screen keyboard), the recent-apps gesture and an app
  launch.
