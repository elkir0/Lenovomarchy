# Host tools (`tools/`)

Utilities for targeting, flashing, backing up, and test-booting the Lenovo Yoga Tab 11 (`YT-J706F`) over USB from macOS.

## Scripts

- [`yt.sh`](yt.sh): source before running `adb` commands to target the tablet by transport id (`yt`, `ytadb`) and strip identifiers (`redact`).
- [`mkboot.sh`](mkboot.sh): pack `Image.gz`, a mainline `.dtb`, and an initramfs into `boot.img` (Android header v2) plus an empty `dtbo.img`.
- [`mkdtbo.py`](mkdtbo.py): build an Android DT table image (`dtbo.img`) from one or more `.dtbo` overlay blobs.
- [`flash-slot.sh`](flash-slot.sh): flash `boot_<slot>` and optional `dtbo_<slot>`, set the active slot, and reboot (enters fastboot via `adb` or `mtk-preloader`).
- [`linux-test.sh`](linux-test.sh): flash Linux to slot A, poll for `LINUX_UP` (SSH at `192.168.77.1`), `FELL_BACK` (Android slot `_b` + pstore), or `TIMEOUT`, and save redacted logs.
- [`backup-partitions.sh`](backup-partitions.sh): stream and SHA-256 verify all partitions (except `userdata`), UFS boot LUs, and GPT headers over root `adb` into `private/`.
- [`mtk-preloader/preloader_fastboot.py`](mtk-preloader/preloader_fastboot.py): catch the MediaTek preloader CDC-ACM boot window and send `FASTBOOT` (or `METAMETA`) without hardware keys.
- [`mtk-preloader/test_preloader_fastboot.py`](mtk-preloader/test_preloader_fastboot.py): pty-based unit tests for `preloader_fastboot.py`.

## One-command Linux boot test

```bash
tools/linux-test.sh [--timeout SECONDS] [--no-flash] <boot.img> <dtbo.img>
```

- Creates `${YT11_RUNS_DIR:-private/runs}/<UTC timestamp>/run.log` and records image SHA-256 digests.
- Exit codes: `0` `LINUX_UP` (saves `dmesg.log`, `uname.txt`, `model.txt`, `devices.txt`, `devices_deferred.txt` if present, `lsmod.txt`, `ip-addr.txt`), `3` `FELL_BACK` (runs `adb root`, waits for `sys.boot_completed=1`, saves `bootreason.txt` and decompressed/redacted `/sys/fs/pstore/*`), `4` `TIMEOUT` (default `420` s), `1` error.
- All outputs are filtered through `redact` (no serial numbers or `Kernel command line` lines written to disk).
- Offline test suite: `bash tests/linux-test/run-tests.sh`.
