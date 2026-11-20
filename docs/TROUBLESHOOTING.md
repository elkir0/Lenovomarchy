# Troubleshooting

Common problems on the Lenovo Yoga Tab 11 (`YT-J706F`) and their documented
causes and fixes.

## Tablet does not reach fastboot

- **Cause:** `adb` is unavailable (Android is replaced or does not boot),
  the USB cable is charge-only, or hardware keys were not held properly.
  Note that `fastboot boot` (RAM boot) does not work on this tablet: Lenovo's
  LK crashes (`lk_crash`) and the watchdog reboots.
- **Fix:** Use a USB-C data cable and run the preloader handshake tool
  before rebooting or powering on the tablet:

```bash
python3 tools/mtk-preloader/preloader_fastboot.py --once
```

  It catches the 2-3 s preloader CDC-ACM window (`/dev/cu.usbmodem*` on
  macOS, `/dev/ttyACM*` on Linux), reads `READY`, and sends `FASTBOOT` so LK
  enters fastboot without hardware keys
  ([mtk-preloader/README.md](../tools/mtk-preloader/README.md)).
  `tools/flash-slot.sh` and `tools/flash-rootfs.sh` run it automatically
  when `adb` does not see the tablet. You can also hold **Volume Down +
  Power** until "fastboot mode" text appears.

## Tablet falls back to the other slot

- **Cause:** LK configures `slot-retry-count` to `1` per slot. If a Linux
  boot resets via the watchdog (30 s timeout in initramfs, 31 s hardware
  maximum) or never reaches `multi-user.target` so
  `yt11-boot-successful.service` can run `yt11-bootctl mark-successful`, LK
  decrements the retry counter and boots the other slot (`_b`) on the next
  reboot. Also, flashing `boot.img` without the empty `dtbo.img` causes LK
  to apply Lenovo's stock Android DTBO overlay onto the mainline DTB.
- **Fix:** Always flash both `boot.img` and `dtbo.img` (e.g.
  `tools/flash-slot.sh a boot.img dtbo.img`). Use
  [`tools/linux-test.sh`](../tools/linux-test.sh) to flash slot `a` and
  record whether the tablet reaches `LINUX_UP` or `FELL_BACK` (collecting
  `bootreason.txt` and `/sys/fs/pstore/*` if it fell back to Android):

```bash
tools/linux-test.sh boot.img dtbo.img
```

## No touch after install

- **Cause:** The Himax HX83102P touch controller is zero-flash and requires
  Lenovo's non-redistributable firmware
  (`/usr/lib/firmware/himax/hx83102p.bin`), which is omitted from the
  release and repository.
- **Fix:** Extract and install the touch firmware from your stock
  `super.img` (or raw `super` dump) over USB SSH, then reboot:

```bash
tools/touch-firmware.sh /path/to/super.img --install
```

```bash
tools/ytssh systemctl reboot
```

## No speaker protection or no microphones

- **Cause:** Both audio paths require non-redistributable Lenovo firmware
  from `super.img`:
  - **Speakers (4x CS35L41):** without
    `/usr/lib/firmware/cirrus/cs35l41-dsp1-spk-prot-yt-j706f.wmfw` and
    `...-spk1..4.bin`, `yt11-audio-defaults` falls back to the unprotected
    ASP path at analog gain 10 instead of the protection DSP at gain 17.
  - **Microphones (AS33970):** the voice processor has no internal flash;
    without `/usr/lib/firmware/tahiti/partition_boot2flash.img`, the
    `snd-soc-as33970` driver cannot load it and microphones stay silent.
  - **Startup delay:** with firmware installed, `snd-soc-as33970` loads the
    image over a 50 kHz I2C bus (`i2c9`), so microphones become ready **about
    31 s after power-on** (streams opened earlier are silent until second
    31). PipeWire captures in Raw mode with a fixed +15 dB gain; the chip's
    voice-processing mode is untested.
- **Fix:** Install both firmware sets from `super.img` and reboot, then wait
  at least 31 s after power-on before recording:

```bash
tools/amp-firmware.sh /path/to/super.img --install
```

```bash
tools/mic-firmware.sh /path/to/super.img --install
```

```bash
tools/ytssh systemctl reboot
```

## `ssh` refused or connection fails

- **Cause:** OpenSSH (`sshd_config.d/10-lenovomarchy.conf`) and initramfs
  `dropbear` disable password logins (`PasswordAuthentication no`,
  `PermitRootLogin prohibit-password`) and accept public-key logins only. If
  the image was flashed without `tools/install.sh --key` or
  `tools/image-set-key.sh` (or `input/authorized_keys` when building from
  source), no key is authorized. Connection also fails if a charge-only USB
  cable is used, or if the tablet froze.
- **Fix:** Install your public key into the root image with
  `tools/image-set-key.sh <rootfs.img> <key.pub>` (or re-run
  `tools/install.sh --key <key.pub>`) and connect via `tools/ytssh`:

```bash
tools/ytssh 'uname -a'
```

  If you need local shell access over USB without Ethernet, the tablet also
  exposes a CDC-ACM serial console (`ttyGS0`):

```bash
screen /dev/cu.usbmodem* 115200
```

## Tablet froze

- **Cause:** Taking any CPU core offline, enabling a PSCI CPU idle state, or
  using `deep` suspend freezes the tablet (no watchdog reset; see
  [BOARD.md](hardware/BOARD.md)). Note also that `s2idle` suspend is
  intentionally refused while the USB-C cable is plugged into a host (`mtu3`
  is active in gadget mode).
- **Fix:** Force a restart by holding the **Power** button for about 10 s
  (or up to 30 s if stuck in fastboot, per Lenovo's user guide and support
  notes). Keep `mem_sleep_default=s2idle` (`tools/mkboot.sh` and
  `/etc/systemd/sleep.conf.d/10-yt11-s2idle.conf`), never offline CPUs, and
  unplug the USB-C cable before suspending.

## Screen too dark

- **Cause:** `yt11-autobrightness` runs inside the Hyprland session and
  sets brightness from the LTR-578 light sensor along a `log10(lux)` curve
  (20 % at 0 lux, 22 % around 0.3 lux, 30 % at 3 lux, 45 % at 30 lux,
  70 % at 300 lux, 95 % at 3000 lux, 100 % from 10000 lux; tested only in
  dim/dark rooms). On older kernels before 2026-11-18, exponential backlight
  mapping on the KTZ8864A also made 28 % brightness emit ~1 % LED current.
- **Fix:** Adjust the brightness slider in Quick Settings or run
  `omarchy brightness display` (which saves a -50 to +50 offset in
  `~/.local/state/yt11/autobrightness-offset`), or turn auto-brightness off:

```bash
yt11-autobrightness off
```

  (in a terminal on the tablet, as `alarm`: the setting belongs to the
  user session).

  Run `yt11-autobrightness status` (inside the user session or checking the
  state) to see the current lux reading and target. Update to the latest
  release kernel if all brightness levels look very dim.

## `omarchy update` fails or wants to replace tablet packages

- **Cause:** The tablet runs Arch Linux ARM (`aarch64`) without upstream
  `[omarchy]` or `[omamobile]` pacman repositories, uses a patched
  `libcamera` for MT6785, uses `squeekboard` instead of `fcitx5`, and does
  not install `mise`. Migrations that call `mise` or install `[omarchy]`
  packages fail if not held.
- **Fix:** Run `omarchy update` on the tablet rather than overriding
  `IgnorePkg` in `/etc/pacman.conf`. The image keeps `hyprland`, `omarchy*`,
  `omamobile-*`, `omacam`, `wlrctl`, and `libcamera*` held via `IgnorePkg`,
  marks build orphans (`linux-firmware-mediatek`, `diffutils`) explicit, and
  holds incompatible migrations listed in
  `/usr/share/lenovomarchy/omarchy-migrations.hold`. If a new Omarchy
  release adds migrations to hold, run `yt11-omarchy-migrations-hold` as
  `alarm`, and run `omarchy-migrate` from `/home/alarm` (not `/root`). See
  [ROADMAP.md](../ROADMAP.md) and
  [M3-MIGRATIONS.md](research/omamobile/M3-MIGRATIONS.md).

## Reading the previous boot's log (`pstore`)

LK preserves the `pstore` RAM region (`mblock-14-pstore`, `0x4d010000` +
`0xe0000`) across reboots (`CONFIG_PSTORE_RAM`, `CONFIG_PSTORE_CONSOLE` at
log level 3 or lower, `CONFIG_PSTORE_PMSG`). Note that a hard CPU freeze
(such as `deep` suspend or CPU hotplug) may leave nothing in `pstore`.

- **From running Linux:** the initramfs copies `/sys/fs/pstore/*` into
  `/run/pstore-prev/` before `switch_root` moves `/run`. Read it and the
  previous systemd journal over SSH:

```bash
tools/ytssh 'ls -l /run/pstore-prev /sys/fs/pstore && cat /run/pstore-prev/* 2>/dev/null'
```

```bash
tools/ytssh 'journalctl -b -1 --no-pager | tail -n 100'
```

- **From the bring-up initramfs shell:** run the `prev-crash` alias (reads
  `/run/pstore-prev/*`) or `crashlog` (reads `/sys/fs/pstore/dmesg-*`).
- **From Android fallback:** `tools/linux-test.sh` runs `adb root`,
  decompresses any `.enc.z` pstore files, redacts identifiers, and saves
  them under `private/runs/<timestamp>/pstore/`.

Never share raw `pstore` dumps or `/proc/cmdline` in public: filter logs
through `redact` from [`tools/yt.sh`](../tools/yt.sh) first to strip serial
numbers and the kernel command line.

## Where to report issues

Open an issue at <https://github.com/elkir0/Lenovomarchy/issues> with your
tablet model (`YT-J706F`), release or kernel/image version, and redacted
logs (`dmesg`, `journalctl`, or `pstore` filtered with `redact`).
