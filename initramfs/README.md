# Bring-up initramfs (Lenovomarchy)

Minimal Linux userland that makes the MT6785 tablet reachable and
debuggable over its only link to the Mac: a USB cable. Builds in
Docker (`alpine:3.22`, linux/arm64) into a root-owned newc archive
under 8 MiB and runs as PID 1.

## What `/init` does

1. Mounts `proc`, `sysfs`, `devtmpfs`, `configfs`, `pstore` (failure
   tolerated), devpts, and tmpfs on `/run` and `/tmp`.
2. Parses the `yt11.*` keys below from `/proc/cmdline`. The command
   line holds the device serial number, so it is never printed or
   logged — every log line goes to `/dev/kmsg` as `<3>yt11-init: ...`
   (pstore keeps console output only at log level 3 or lower).
3. Starts `watchdog -t 5 -T 30 /dev/watchdog` in the background
   (unless `yt11.nowdt=1`): the MT6785 watchdog maxes out at 31 s.
4. Copies any pstore records from the previous boot to
   `/run/pstore-prev/` and logs their names and sizes.
5. Brings up a USB gadget through configfs (`usb_gadget/g1`): vendor
   `1d6b:0104` (Linux gadget), CDC-ECM (`ecm.usb0`, fixed MACs) plus
   CDC-ACM (`acm.GS0`), strings "Lenovomarchy / YT-J706F Linux /
   lenovomarchy" (a constant, never the device serial). Waits up to
   15 s for a UDC and binds it; without configfs or a UDC (QEMU) it
   logs that and continues.
6. Configures `usb0` 192.168.77.1/24 and serves DHCP for exactly one
   address (192.168.77.2) — the Mac gets it natively over CDC-ECM.
   Alpine's busybox has no `udhcpd` applet, so dnsmasq runs in
   DHCP-only mode (no router, no DNS; lease file in `/run`).
7. Runs `dropbear` on port 22, password logins disabled: host key
   generated per boot into `/run/dropbear/`, root's key installed
   from `YT11_SSH_PUBKEY` at build time.
8. Respawns a root shell on the USB serial port
   (`getty -n -l /bin/sh 115200 ttyGS0`) and on `tty1` (fbcon) via
   busybox init and the generated `/etc/inittab`.
9. `yt11.autotest=1`: after setup, runs `/autotest.sh` (when present
   in the image), forwards its output line by line to `/dev/kmsg` at
   `<3>`, then syncs and reboots with sysrq-b.
10. `yt11.root=<device>`: waits up to 10 s for the device, mounts it
    on `/newroot` (`yt11.rootfstype`, default ext4; `yt11.rootflags`),
    moves `/dev /proc /sys /run` into it and
    `exec switch_root /newroot /sbin/init`; on any failure it logs
    and stays in the initramfs.

`ready (usb=<bound|none>, ssh=<up|down>)` marks the setup done.

## Kernel command line keys

| Key | Effect |
|-----|--------|
| `yt11.nowdt=1` | do not start the watchdog daemon |
| `yt11.autotest=1` | run `/autotest.sh` then reboot (sysrq-b) |
| `yt11.root=<dev>` | switch_root to this device after setup |
| `yt11.rootfstype=<fs>` | its file system type (default `ext4`) |
| `yt11.rootflags=<opts>` | extra mount options for it |

## Build and test

```sh
YT11_SSH_PUBKEY=~/.ssh/id_ed25519.pub bash initramfs/build.sh
# optional: YT11_AUTOTEST=./my-test.sh (installed as /autotest.sh)
bash initramfs/test-qemu.sh               # prints PASS
```

Only host dependency: Docker. Layout: `init` (PID 1 script),
`build.sh` (refuses a pubkey containing a private key; prints the
archive size), `test-qemu.sh` (QEMU smoke test), `files/` (`/etc`
overlay: inittab, dnsmasq DHCP config, passwd, shell profile).

## Mac-side access

```sh
ssh root@192.168.77.1                      # CDC-ECM, key from build
screen /dev/cu.usbmodem* 115200            # CDC-ACM serial shell
```

macOS speaks CDC-ECM natively (no RNDIS); the tablet hands the Mac
192.168.77.2 by DHCP once the gadget binds. Past crash logs live in
`/run/pstore-prev/` (`prev-crash` alias in the shell).
