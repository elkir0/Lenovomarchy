#!/usr/bin/env python3
"""Catch the MediaTek preloader's USB window and pick a boot mode.

On this MT6785 tablet, at every boot with a USB cable attached, the
preloader enumerates as a USB CDC-ACM serial device (macOS:
/dev/cu.usbmodem*) for two to three seconds.  During that window it
sends the ASCII string ``READY`` and waits for an 8-byte boot-mode
token.  Sending ``FASTBOOT`` makes it continue into the fastboot
bootloader; it acknowledges with the token reversed (``TOOBTSAF``).

This tool watches for the serial node to appear, opens it, waits until
it has actually read ``READY`` (it never writes before that), sends the
token once, then waits for the reversed token.  Example::

    # one shot: handle the next boot and exit
    preloader_fastboot.py --once

    # every boot, until interrupted (Ctrl-C exits 0)
    preloader_fastboot.py --watch

    # explicit port (Linux name, or a node that already exists)
    preloader_fastboot.py --port /dev/ttyACM0

Exit codes: 0 acknowledged / interrupted, 2 no READY, 3 no ack,
4 no port appeared, 1 usage error.

Only the two tokens the project allows, FASTBOOT and METAMETA, are
accepted; the tool never triggers any other boot mode.
"""

from __future__ import annotations

import argparse
import glob
import os
import sys
import termios
import time
import tty

DEFAULT_GLOB = "/dev/cu.usbmodem*"
TOKENS = ("FASTBOOT", "METAMETA")

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_NO_READY = 2
EXIT_NO_ACK = 3
EXIT_NO_PORT = 4

POLL_INTERVAL = 0.02          # port discovery poll: 20 ms
OPEN_RETRY_TOTAL = 0.3        # keep retrying open() for 300 ms
READ_CHUNK = 256
DEBUG_REPR_LIMIT = 64         # bytes shown from a timed-out read


def now_iso() -> str:
    """Local time, ISO-8601 with milliseconds."""
    now = time.time()
    base, ms = time.localtime(now), int(now * 1000) % 1000
    return time.strftime("%Y-%m-%dT%H:%M:%S", base) + ".%03d" % ms


def log(message: str) -> None:
    print("%s %s" % (now_iso(), message))
    sys.stdout.flush()


def debug_repr(data: bytes) -> str:
    """repr() of the received bytes, truncated to 64 bytes."""
    if len(data) > DEBUG_REPR_LIMIT:
        return repr(data[:DEBUG_REPR_LIMIT]) + "... (%d bytes)" % len(data)
    return repr(data)


def find_ports(pattern: str) -> set[str]:
    return set(glob.glob(pattern))


def open_port(path: str):
    """Open a serial node and configure it: raw, 115200 8N1, no flow control.

    The node can exist before the kernel is done creating it, so keep
    retrying for up to 300 ms.  Returns the fd, or None.
    """
    deadline = time.monotonic() + OPEN_RETRY_TOTAL
    while True:
        try:
            fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
            try:
                tty.setraw(fd)
                attrs = termios.tcgetattr(fd)
                attrs[0] &= ~(
                    termios.IGNBRK | termios.BRKINT | termios.PARMRK
                    | termios.ISTRIP | termios.INLCR | termios.IGNCR
                    | termios.ICRNL | termios.IXON | termios.IXANY
                )
                attrs[1] &= ~termios.OPOST
                attrs[2] &= ~(
                    termios.CSIZE | termios.PARENB | termios.CSTOPB
                    | termios.CRTSCTS
                )
                attrs[2] |= termios.CS8 | termios.CREAD | termios.CLOCAL
                attrs[4] = termios.B115200
                attrs[5] = termios.B115200
                cc = list(attrs[6])
                cc[termios.VMIN] = 1
                cc[termios.VTIME] = 0
                attrs[6] = cc
                termios.tcsetattr(fd, termios.TCSANOW, attrs)
            except termios.error:
                os.close(fd)
                raise
            return fd
        except OSError:
            if time.monotonic() >= deadline:
                return None
            time.sleep(0.02)


def write_all(fd, data: bytes) -> None:
    """Write all of data, tolerating a non-blocking fd."""
    while data:
        try:
            written = os.write(fd, data)
        except BlockingIOError:
            time.sleep(0.002)
            continue
        data = data[written:]


def read_until(fd, needle: bytes, timeout: float):
    """Read from fd until needle is seen in the accumulated bytes.

    Returns (True, elapsed_ms) on match, (False, elapsed_ms, all_bytes)
    on timeout.  Also returns on EOF (other side closed) with match
    status.
    """
    start = time.monotonic()
    buf = b""
    deadline = start + timeout
    while True:
        try:
            data = os.read(fd, READ_CHUNK)
        except BlockingIOError:
            data = None          # nothing to read yet (O_NONBLOCK)
        except OSError:
            # The peer closed the port (EOF on a pty).
            return needle in buf, (time.monotonic() - start) * 1000.0, buf
        if data:
            buf += data
            if needle in buf:
                return True, (time.monotonic() - start) * 1000.0, buf
        elif data == b"":
            # EOF: the peer closed the port.
            return needle in buf, (time.monotonic() - start) * 1000.0, buf
        if time.monotonic() >= deadline:
            return needle in buf, (time.monotonic() - start) * 1000.0, buf
        time.sleep(0.002)


def handshake(fd, path: str, token: str, ready_timeout: float,
              ack_timeout: float) -> int:
    """Full exchange on an open port.  Writes only after READY is read.

    Returns EXIT_OK, EXIT_NO_READY or EXIT_NO_ACK.
    """
    expected_ack = token[::-1].encode("ascii")
    ok, ms, buf = read_until(fd, b"READY", ready_timeout)
    if not ok:
        log("no READY on %s after %.0f ms: received %s"
            % (path, ms, debug_repr(buf)))
        return EXIT_NO_READY
    log("READY after %.0f ms" % ms)
    write_all(fd, token.encode("ascii"))
    log("sent %s" % token)
    ok, ms, buf = read_until(fd, expected_ack, ack_timeout)
    if not ok:
        log("no ack on %s after %.0f ms: received %s"
            % (path, ms, debug_repr(buf)))
        return EXIT_NO_ACK
    log("ack %s after %.0f ms" % (token[::-1], ms))
    return EXIT_OK


def close_quietly(fd) -> None:
    try:
        os.close(fd)
    except OSError:
        pass


def run_once(port: str, args) -> int:
    """Handle one known port: open it and run the handshake."""
    fd = open_port(port)
    if fd is None:
        log("cannot open %s" % port)
        return EXIT_NO_READY
    try:
        return handshake(fd, port, args.token, args.ready_timeout,
                         args.ack_timeout)
    finally:
        close_quietly(fd)


def run_watch(args) -> int:
    """--watch: snapshot existing ports, then handle each new one forever."""
    existing = find_ports(args.glob)
    if existing:
        log("ignoring %d port(s) that already exist" % len(existing))
    while True:
        current = find_ports(args.glob)
        # macOS names the node after the USB location, so the preloader's
        # port comes back under the same name at every boot: forget a port
        # once it has vanished, or the next boot would be ignored.
        existing &= current
        new = current - existing
        if new:
            port = sorted(new)[0]
            existing.add(port)
            log("port %s appeared" % port)
            try:
                run_once(port, args)
            except Exception as exc:      # keep watching on any error
                log("handshake with %s failed: %s" % (port, exc))
        else:
            time.sleep(POLL_INTERVAL)


class ToolArgumentParser(argparse.ArgumentParser):
    """Exit with 1 (usage error) instead of argparse's default 2, which
    the tool already uses for "no READY"."""

    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(EXIT_USAGE, "%s: error: %s\n" % (self.prog, message))


def main(argv=None) -> int:
    parser = ToolArgumentParser(
        description="Catch the MediaTek preloader's USB window and send "
                    "a boot-mode token (FASTBOOT or METAMETA).")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true", default=True,
                      help="handle the first new port, then exit (default)")
    mode.add_argument("--watch", action="store_true",
                      help="handle every new port (each boot), never exit "
                           "on a failed handshake")
    parser.add_argument("--port", metavar="PATH",
                        help="skip discovery and use this serial node "
                             "(e.g. /dev/ttyACM0 on Linux)")
    parser.add_argument("--glob", metavar="PATTERN", default=DEFAULT_GLOB,
                        help="port discovery pattern (default: %(default)s)")
    parser.add_argument("--token", default="FASTBOOT",
                        choices=list(TOKENS),
                        help="boot-mode token to send (default: %(default)s)")
    parser.add_argument("--wait", type=float, default=120.0, metavar="SECONDS",
                        help="max time to wait for a port to appear "
                             "(default: %(default)s)")
    parser.add_argument("--ready-timeout", type=float, default=2.0,
                            metavar="SECONDS",
                            help="max wait for READY (default: %(default)s)")
    parser.add_argument("--ack-timeout", type=float, default=1.0,
                        metavar="SECONDS",
                        help="max wait for the ack (default: %(default)s)")
    args = parser.parse_args(argv)

    if args.port:
        log("port %s appeared" % args.port)
        try:
            return run_once(args.port, args)
        except Exception as exc:
            log("handshake with %s failed: %s" % (args.port, exc))
            return EXIT_NO_READY
    if args.watch:
        try:
            return run_watch(args)
        except KeyboardInterrupt:
            return EXIT_OK
    return wait_for_first_port(args)


def wait_for_first_port(args) -> int:
    """Default --once without --port: wait for one new port, handle it, exit."""
    existing = find_ports(args.glob)
    if existing:
        log("ignoring %d port(s) that already exist" % len(existing))
    deadline = time.monotonic() + args.wait
    while time.monotonic() < deadline:
        new = find_ports(args.glob) - existing
        if new:
            port = sorted(new)[0]
            log("port %s appeared" % port)
            try:
                return run_once(port, args)
            except Exception as exc:
                log("handshake with %s failed: %s" % (port, exc))
                return EXIT_NO_READY
        time.sleep(POLL_INTERVAL)
    log("no port appeared within %.0f s" % args.wait)
    return EXIT_NO_PORT


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(EXIT_OK)
