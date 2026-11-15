# Lenovomarchy: rules for agents

- Talk to the owner in French; write repository docs, code comments and
  commits in English.
- **Target the tablet only.** Other adb devices may be attached to the Mac
  (the owner's phone). Source `tools/yt.sh` and use `yt` / `ytadb`, or
  `adb -t <transport id>`; check `fastboot devices | wc -l` is 1 before any
  fastboot command.
- **Never print identifiers**: no `adb devices` (use `adb get-state` or the
  awk in `tools/yt.sh`), no `cat /proc/cmdline` (extract one key with
  `grep -o`), no `getprop ro.serialno`, `fastboot getvar all` through
  `grep -vi serial`, every `dmesg` without "Kernel command line". Pipe
  device output through `redact`.
- **Partitions**: this project only ever writes `boot_a`, `boot_b`,
  `vbmeta*`, `dtbo_*`, `misc` and `userdata`. Never `preloader*`, `lk_*`,
  `tee_*`, `gz_*`, `scp_*`, `sspm_*`, `spmfw_*`, `seccfg`, `super`,
  `nvram`, `nvdata`, `nvcfg`, `proinfo`, `protect*`, `persist`, `otp`,
  `lenovo*`. No "Format All" flash.
- Since 2026-11-15 the owner gives agents full autonomy on the tablet:
  flash the allowed partitions, reboot, wipe and iterate without asking
  (Android's content does not matter). Pushing or publishing anything still
  needs the owner.
- Recovery without keys: `tools/mtk-preloader/preloader_fastboot.py --once`
  answers the preloader at the next boot and lands in fastboot. `fastboot
  boot` does not work (LK crashes): test images are flashed to `boot_*`.
- `private/` holds unit data and vendor firmware: never copy it into git or
  into a fleet worker's brief; workers must not read it.
- Facts read from the unit go to `docs/hardware/`; they outrank
  `docs/research/`.
