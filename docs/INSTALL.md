# Install on your own YT-J706F

This guide installs Omarchy 4.5 (Arch Linux ARM, Hyprland, and the Quickshell
tablet shell) on a Lenovo Yoga Tab 11 (**YT-J706F**), replacing Android.

## What you get and what does not work

The tablet boots Linux 7.1 (`yt11` branch) from `boot_a` with its root
filesystem on `userdata`.

- **Works:** display (1200x2000 at 60.07 Hz), touch, Mali-G76 GPU (Panfrost),
  Wi-Fi (2.4 GHz measured; 5 GHz not measured), Bluetooth scan, four speakers
  with protection DSP, battery gauge, USB-C gadget networking and host role
  switching, 2 A charging with temperature guard, power and volume buttons,
  auto-rotation (BMI220), auto-brightness (LTR-578, tested in dim light), and
  `s2idle` sleep (~135 mA standby, about 48 h).
- **Partial:** microphones (firmware loads in ~31 s, stereo capture with
  fixed +15 dB gain; voice-processing mode untested), rear OV8856 and front
  S5K4H7 cameras (`omacam` and libcamera; autofocus takes ~18 s at app start,
  no lens shading correction so corners are darker), vibrator (driver drives
  the LDO, buzz not yet felt by a person).
- **Untested:** Precision Pen 2, microSD slot, USB PD wall charging, pairing
  Bluetooth devices.
- **Does not work:** `deep` suspend, CPU idle states, and CPU hotplug (taking
  a core offline freezes the tablet), hardware video decoding and encoding
  (stays on CPU), proximity sensor, and the pogo-pin keyboard accessory.

See [ROADMAP.md](../ROADMAP.md) for the full component-by-component status.

## Check the model

This project targets only the Wi-Fi model **YT-J706F** (MediaTek MT6785 /
Helio G90T). Check the exact model string in Android under **Settings >
About**.

- **TB-J706F** is a different tablet (Tab P11 Pro / Xiaoxin Pad Pro,
  Qualcomm). Nothing made for it applies here.
- **YT-J706X** is the LTE variant with a separate stock firmware series and
  is untested here.
- The Wi-Fi YT-J706F has no headphone jack, cover sensor, cellular modem, or
  GNSS hardware.

## What you need

- A host computer running **macOS** or **Linux**.
- A **USB-C data cable** (not a charge-only cable).
- Android platform-tools (`adb` and `fastboot`).
- `python3` (Python 3.12 or newer for
  [`preloader_fastboot.py`](../tools/mtk-preloader/preloader_fastboot.py)).
- **Docker** running on the host.
- `xz` and `git`.
- `ssh` with an Ed25519 key pair.
- Your tablet's stock `super` image (the sparse `super.img` from Lenovo's
  stock firmware package for the YT-J706F, or a raw dump of your tablet's
  `super` partition) to extract the non-redistributable firmware sets.

## Warnings

- **Everything on Android is erased.** Unlocking the bootloader wipes all
  user data, and the installer overwrites `userdata` with the Linux root
  filesystem.
- **Partitions written:** the project only ever writes `boot_a`, `boot_b`,
  `vbmeta*`, `dtbo_*`, `misc`, and `userdata` (`tools/install.sh` writes
  `userdata`, `boot_<slot>`, and `dtbo_<slot>`). It never writes
  `preloader*`, `lk_*`, `tee_*`, `gz_*`, `scp_*`, `sspm_*`, `spmfw_*`,
  `seccfg`, `super`, `nvram`, `nvdata`, `nvcfg`, `proinfo`, `protect*`,
  `persist`, `otp`, or `lenovo*`. Never run a "Format All" flash in any
  MediaTek tool.
- **No tested way back to Android.** Returning to stock Android requires
  Lenovo's official rescue tool (Windows 10/11 64-bit only, needs a Lenovo ID
  and serial number) or MediaTek SP Flash Tool. This project has not tested
  restoring Android; see
  [official_recovery_paths.md](research/notes/official_recovery_paths.md).
  Unlocking the bootloader also drops Widevine DRM to L3.
- **Lenovo firmware is not included.** The prebuilt release contains no SSH
  keys and none of Lenovo's proprietary firmware for the touch controller,
  speaker protection DSP, or microphone voice processor. Until you install
  those three sets from your own `super` image, there is no touch input, the
  speakers play without their protection DSP, and the microphones do not
  work.
- **CPU hotplug and deep sleep hazard:** never take a CPU core offline,
  enable PSCI CPU idle states, or switch sleep mode to `deep`; doing so
  freezes the tablet until a forced restart with the power button.

## Step 1: Prepare Android

1. In Android on the tablet, enable **Developer options**.
2. Open Developer options and turn on **OEM unlocking** and **USB debugging**.
3. Connect the tablet to your computer with the USB-C data cable and accept
   the USB debugging prompt on the tablet.

Verify that `adb` sees the tablet:

```bash
adb get-state
```

If other Android devices are connected to the same computer, source
[`tools/yt.sh`](../tools/yt.sh) and use `ytadb` instead of bare `adb`, and
verify `fastboot devices | wc -l` is `1` before running any fastboot command.

## Step 2: Unlock the bootloader

Reboot the tablet into the LK fastboot bootloader:

```bash
adb reboot bootloader
```

Fastboot appears in about 8 s. (You can also hold **Volume Down + Power**
until the "fastboot mode" text appears.)

Confirm that unlocking is allowed (the command must return a non-zero value;
with OEM unlocking enabled it returns `16777216`):

```bash
fastboot flashing get_unlock_ability
```

Unlock the bootloader (this wipes Android's user data without touching
`nvram`, `nvdata`, or `proinfo`):

```bash
fastboot flashing unlock
```

The screen prints `Start unlock flow`. Press **Volume Up** on the tablet to
confirm. Fastboot prints `OKAY` after about 16 s (`fastboot getvar unlocked`
now reports `yes`).

On subsequent boots, the orange-state warning clears by itself after a few
seconds with no key press.

## Step 3: Get the stock firmware package

The three non-redistributable Lenovo firmware sets live inside the `vendor_a`
partition inside the stock `super` image:

- **Touch controller:** Himax `Himax_firmware.bin` (installed as
  `/usr/lib/firmware/himax/hx83102p.bin`).
- **Speaker protection DSP:** Cirrus Logic `cs35l41-dsp1-spk-prot.wmfw` and
  `cs35l41-dsp1-spk-prot1..4.bin`.
- **Microphone voice processor:** Synaptics AS33970
  `partition_boot2flash.img`.

You can obtain `super.img` from Lenovo's official Windows rescue tool
(Software Fix / Rescue and Smart Assistant, which saves the downloaded ROW
firmware under `C:\ProgramData\RSA\Download\RomFiles\...` or
`C:\ProgramData\LMSA\...`), or from the ROW firmware mirrors noted in
[official_recovery_paths.md](research/notes/official_recovery_paths.md).
[`tools/lp-extract.py`](../tools/lp-extract.py) reads both the sparse
`super.img` from Lenovo's firmware package and a raw `super` partition dump.

If you want to back up your unit's stock partitions (except `userdata`)
before overwriting `boot_a`, flash the stock package's `boot-debug.img`
temporarily to get root `adb` as described in
[INVENTORY.md](hardware/INVENTORY.md) and run:

```bash
tools/backup-partitions.sh private/backup
```

## Step 4: Download the release files and clone the repository

Clone this repository and enter it:

```bash
git clone https://github.com/elkir0/Lenovomarchy.git && cd Lenovomarchy
```

Download the three release files from the
[latest release](https://github.com/elkir0/Lenovomarchy/releases/latest) into
the working directory:

- `boot.img`
- `dtbo.img`
- `rootfs-omarchy-aarch64.img.xz`

Create an Ed25519 SSH key pair if you do not already have one:

```bash
ssh-keygen -t ed25519
```

## Step 5: Run `tools/install.sh`

With the tablet connected over USB (in Android with `adb`, in fastboot, or
ready to reboot so the preloader can be caught), run:

```bash
tools/install.sh --key ~/.ssh/id_ed25519.pub --firmware /path/to/super.img \
    rootfs-omarchy-aarch64.img.xz boot.img dtbo.img
```

Omit `--firmware /path/to/super.img` if you want to extract and install the
firmware sets later. Optional flags: `--slot a|b` (defaults to `a`), `--yes`
(skips the confirmation prompt), and `--dry-run`.

Each phase of `tools/install.sh` performs the following:

1. Checks that the required host tools and Docker are available.
2. Prompts you to type `ERASE` to confirm wiping `userdata`.
3. Decompresses `rootfs-omarchy-aarch64.img.xz` (also accepts raw `.img` or
   `.img.zst`) and installs your SSH public key for `root` and `alarm`.
4. Flashes `userdata`, then flashes `boot_<slot>` and `dtbo_<slot>`, sets the
   slot active, and reboots.
5. Waits for Linux to come up on the USB network (`192.168.77.1`). First boot
   reaches the Omarchy session about 30 s after power-on and grows the root
   filesystem to fill `userdata`.
6. When `--firmware` is given, extracts the three firmware sets from
   `super.img`, installs them over SSH, and reboots the tablet. On the next
   boot, the microphone DSP firmware finishes loading about 31 s after
   power-on.

## Step 6: First settings

1. **Log in / unlock:** the user account is `alarm` with default password
   `alarm`. Change it on the tablet with `omamobile-set-pin` (choose either
   a PIN or a password). The screen locks after 5 minutes idle and blanks
   10 s later; tap the screen to wake it.
2. **Wi-Fi:** tap the Wi-Fi icon in Quick Settings to connect to a network.
3. **Time zone:** the system defaults to `UTC`. Set your time zone from a
   terminal on the tablet or over SSH:

```bash
tools/ytssh 'timedatectl set-timezone <Region/City>'
```

4. **SSH over USB:** when connected to the host over USB-C, the tablet runs
   CDC-ECM at `192.168.77.1` and assigns `192.168.77.2` to the host by DHCP.
   `tools/ytssh '<command>'` connects as `root` using your SSH key
   (login by password is disabled).

## Installing the firmware later

If you ran `tools/install.sh` without `--firmware`, connect the running
tablet over USB and run the three firmware installers followed by a reboot:

```bash
tools/touch-firmware.sh /path/to/super.img --install
```

```bash
tools/amp-firmware.sh /path/to/super.img --install
```

```bash
tools/mic-firmware.sh /path/to/super.img --install
```

```bash
tools/ytssh systemctl reboot
```

## Updating

- **Packages and Omarchy:** run `omarchy update` on the tablet. Custom
  tablet packages (`hyprland`, `omarchy`, `omarchy-settings`,
  `omarchy-keyring`, `omarchy-speedtest`, `omamobile-*`, `omacam`, `wlrctl`,
  and the custom `libcamera*` packages) are pinned in `/etc/pacman.conf`
  via `IgnorePkg`, and incompatible Omarchy migrations are listed in
  `/usr/share/lenovomarchy/omarchy-migrations.hold` (held by
  `yt11-omarchy-migrations-hold`).
- **Kernel updates:** a new kernel requires both the new `boot.img` (flashed
  via `tools/flash-slot.sh`) and its matching kernel modules (installed via
  `tools/push-modules.sh`). See [tools/README.md](../tools/README.md):

```bash
tools/push-modules.sh out/kernel/modules.tar.xz
```

```bash
tools/flash-slot.sh a boot.img dtbo.img
```

## Doing each step by hand

To run the installation steps manually with the release files instead of
`tools/install.sh`:

1. Decompress the root filesystem image:

```bash
xz -d rootfs-omarchy-aarch64.img.xz
```

2. Install your SSH public key for `root` and `alarm` inside the raw ext4
   image:

```bash
tools/image-set-key.sh rootfs-omarchy-aarch64.img ~/.ssh/id_ed25519.pub
```

3. Convert the root image to sparse format and flash it to `userdata` (the
   tablet stays in fastboot afterwards):

```bash
tools/flash-rootfs.sh rootfs-omarchy-aarch64.img
```

4. Flash `boot.img` and `dtbo.img` to slot `a`, set slot `a` active, and
   reboot:

```bash
tools/flash-slot.sh a boot.img dtbo.img
```

5. Once Linux answers on the USB network (`192.168.77.1`), extract and
   install the three firmware sets from `super.img` and reboot:

```bash
tools/touch-firmware.sh /path/to/super.img --install
```

```bash
tools/amp-firmware.sh /path/to/super.img --install
```

```bash
tools/mic-firmware.sh /path/to/super.img --install
```

```bash
tools/ytssh systemctl reboot
```
