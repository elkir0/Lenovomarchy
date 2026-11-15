# mtk-preloader: preloader → fastboot handshake

`preloader_fastboot.py` (Python 3.12+, standard library only) catches the
short USB window at tablet boot during which the MediaTek preloader
enumerates as a CDC-ACM serial device, and sends it a boot-mode token.

## Protocol

At every boot with a USB cable attached, the preloader appears for about
2-3 seconds as `/dev/cu.usbmodem*` on macOS (`/dev/ttyACM*` on Linux),
sends the ASCII string `READY`, and waits for an 8-byte token:

- host sends `FASTBOOT` → the preloader enters the fastboot bootloader
  and acknowledges with the token reversed: `TOOBTSAF`;
- host sends `METAMETA` → meta mode (same reversed-token ack).

The tool reads until `READY`, sends the token once, then reads until the
reversed token. Each event is logged on stdout with an ISO-8601 local
timestamp with milliseconds (`port ... appeared`, `READY after N ms`,
`sent FASTBOOT`, `ack TOOBTSAF after N ms`, or the failure line).

## Usage

```sh
# Handle the next boot, then exit (default mode: --once)
python3 tools/mtk-preloader/preloader_fastboot.py --once

# Handle every boot (each new appearance), until Ctrl-C
python3 tools/mtk-preloader/preloader_fastboot.py --watch

# Explicit port node: skip discovery (Linux, or an existing node)
python3 tools/mtk-preloader/preloader_fastboot.py --port /dev/ttyACM0
```

Other options: `--wait SECONDS` port appearance, default 120;
`--ready-timeout` (2 s), `--ack-timeout` (1 s); `--glob PATTERN`
(default `/dev/cu.usbmodem*`); `--token`.

## Exit codes

0 ack received (or Ctrl-C in `--watch`) · 1 usage error (e.g. a token
outside the two allowed) · 2 no `READY` within the timeout · 3 token
sent but no reversed ack · 4 no new port appeared within `--wait`.

## Safety rules

- **Never writes before `READY`**: the token is sent only after `READY`
  has actually been read; other serial devices attached to the Mac are
  never written to.
- **Ignores pre-existing ports**: nodes that already existed when the
  tool started are never handled; discovery only reacts to new nodes.
- **Only two tokens**: `FASTBOOT` and `METAMETA`; anything else is
  refused by the argument parser (exit 1), so the tool cannot trigger
  another boot mode.

## Tests

`python3 -m unittest discover -s tools/mtk-preloader -v` — the tests
simulate the preloader on the master side of a pty (`os.openpty()`).
