"""Unit tests for preloader_fastboot, simulating the device on a pty.

The "device" side of each test is the master side of os.openpty(); the
tool under test opens the slave side through --port.  No real serial
hardware is involved.

subprocess use: the tool is launched by absolute path (a trusted path
built from __file__), with this directory prepended to PYTHONPATH so the
test module can import the module under test.
"""

from __future__ import annotations

import os
import selectors
import subprocess
import sys
import tempfile
import termios
import time
import unittest

import preloader_fastboot as pf

TOOL = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    "preloader_fastboot.py")

# Enough for the tool's open() retries and 2 s READY timeout.
TIMEOUT = 10.0


class Pty:
    """A fake preloader: master side of a pty kept open for the tool."""

    def __init__(self):
        self.master, slave = os.openpty()
        self.slave_path = os.ttyname(slave)
        self.slave_fd = slave  # kept open; the tool opens its own fd

    def close(self):
        for fd in (self.master, getattr(self, "slave_fd", -1)):
            try:
                os.close(fd)
            except OSError:
                pass


def spawn_tool(argv, env=None):
    """Start the tool; returns (proc, pty).  Cleanup is the test's job."""
    return subprocess.Popen(
        [sys.executable, TOOL] + argv,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, env=env)


def run_tool(argv, env=None):
    return subprocess.run(
        [sys.executable, TOOL] + argv,
        capture_output=True, text=True, timeout=TIMEOUT, env=env)


def finish(proc):
    """Wait for the tool to exit, capture its output, kill on timeout."""
    try:
        out, err = proc.communicate(timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, err = proc.communicate()
        raise AssertionError("tool did not exit in time:\n%s" % out)
    return proc.returncode, out, err


def wait_readable(fd, timeout=TIMEOUT):
    """Block until fd has data; return True, or False on timeout."""
    sel = selectors.DefaultSelector()
    sel.register(fd, selectors.EVENT_READ)
    try:
        return bool(sel.select(timeout))
    finally:
        sel.close()


class HandshakeTests(unittest.TestCase):
    def setUp(self):
        self.pty = Pty()
        self.addCleanup(self.pty.close)
        self.procs = []
        self.addCleanup(self.cleanup_procs)

    def cleanup_procs(self):
        for proc in self.procs:
            if proc.poll() is None:
                proc.kill()

    def tool_args(self, extra=()):
        return ["--port", self.pty.slave_path] + list(extra)

    def start(self, extra=()):
        proc = spawn_tool(self.tool_args(extra))
        self.procs.append(proc)
        # Do not write READY before the tool has put the port in raw
        # mode, or the pty echoes it back at us.
        self.wait_raw()
        return proc

    def wait_raw(self, timeout=5.0):
        """Block until the tool has configured the slave side (no ECHO)."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            attrs = termios.tcgetattr(self.pty.slave_fd)
            if not attrs[3] & termios.ECHO:
                return
            time.sleep(0.005)
        raise AssertionError("tool never configured the port")

    def read_all_available(self, timeout=2.0):
        """Drain the master side once data is readable."""
        self.assertTrue(wait_readable(self.pty.master, timeout),
                        "tool wrote nothing")
        out = b""
        while True:
            part = os.read(self.pty.master, 1024)
            out += part
            if len(part) < 1024:
                return out

    def test_ready_then_ack_exits_0(self):
        proc = self.start()
        os.write(self.pty.master, b"READY")

        # The tool writes the token only after our READY.
        self.assertEqual(self.read_all_available(), b"FASTBOOT")
        os.write(self.pty.master, b"TOOBTSAF")

        code, out, err = finish(proc)
        self.assertEqual(code, 0, err)
        self.assertIn("sent FASTBOOT", out)
        self.assertIn("ack TOOBTSAF", out)

    def test_no_ready_exits_2_and_writes_nothing(self):
        proc = self.start(["--ready-timeout", "0.5"])

        code, out, err = finish(proc)
        self.assertEqual(code, 2, err)
        self.assertIn("no READY", out)
        # Nothing must ever be written before READY: no data for 1 s.
        self.assertFalse(wait_readable(self.pty.master, 1.0),
                         "tool wrote before reading READY")

    def test_ready_but_no_ack_exits_3(self):
        proc = self.start(["--ack-timeout", "0.5"])
        os.write(self.pty.master, b"READY")
        self.assertEqual(self.read_all_available(), b"FASTBOOT")
        # Device stays silent: no reversed token.

        code, out, err = finish(proc)
        self.assertEqual(code, 3, err)
        self.assertIn("no ack", out)

    def test_ready_split_across_writes_is_recognised(self):
        proc = self.start(["--ready-timeout", "3"])
        os.write(self.pty.master, b"RE")
        time.sleep(0.1)
        os.write(self.pty.master, b"AD")
        time.sleep(0.1)
        os.write(self.pty.master, b"Y")

        self.assertEqual(self.read_all_available(), b"FASTBOOT")
        os.write(self.pty.master, b"TOOBTSAF")

        code, out, err = finish(proc)
        self.assertEqual(code, 0, err)
        self.assertIn("READY after", out)

    def test_wrong_ack_exits_3(self):
        proc = self.start(["--ack-timeout", "0.5"])
        os.write(self.pty.master, b"READY")
        self.assertEqual(self.read_all_available(), b"FASTBOOT")
        os.write(self.pty.master, b"WRONGACK")

        code, out, err = finish(proc)
        self.assertEqual(code, 3, err)


class CliTests(unittest.TestCase):
    def test_refuses_other_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, PYTHONPATH=tmp)
            # --port /dev/null: refused at argument parsing, before any I/O.
            result = run_tool(["--token", "RECOVERY", "--port", "/dev/null"],
                              env=env)
        # Refused at argument parsing, before any I/O; usage error is 1,
        # not 2 (which means "no READY").
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("--token", result.stderr)
        self.assertNotIn("sent", result.stdout)

    def test_no_port_appeared_exits_4(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, PYTHONPATH=tmp)
            result = run_tool(
                ["--wait", "0.3", "--glob", os.path.join(tmp, "nomatch*")],
                env=env)
        self.assertEqual(result.returncode, 4, result.stderr)
        self.assertIn("no port appeared", result.stdout)


class UnitTests(unittest.TestCase):
    def test_token_choices(self):
        self.assertEqual(pf.TOKENS, ("FASTBOOT", "METAMETA"))

    def test_debug_repr_truncates(self):
        self.assertEqual(pf.debug_repr(b"ab"), repr(b"ab"))
        self.assertEqual(pf.debug_repr(b"x" * 80),
                         repr(b"x" * 64) + "... (80 bytes)")

    def test_debug_repr_limit(self):
        self.assertLessEqual(len(pf.debug_repr(b"y" * 300)), 100)

    def test_now_iso_format(self):
        stamp = pf.now_iso()
        date, clock = stamp.split("T")
        self.assertEqual(len(date), 10)
        self.assertEqual(len(clock), 12)
        self.assertEqual(clock[8], ".")


if __name__ == "__main__":
    unittest.main()
