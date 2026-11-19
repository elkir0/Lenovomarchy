#!/usr/bin/env python3
"""faketouch: inject touches on the tablet through a uinput touchscreen.

Runs ON the tablet as root (copy it there, e.g. to /tmp). It lets an agent
exercise the touch interface with nobody at the screen: taps, long presses
and swipes, to be checked with a screenshot (grim).

Coordinates are fractions of the virtual touchscreen, 0..1 on both axes.
The compositor maps the device to the whole output; how it is rotated
depends on the output transform, so calibrate once with a tap and a
screenshot.

Usage:
  faketouch.py [--hold S] ACTION [ACTION...]
Actions (run in order on one device, created once):
  tap:X,Y            press 60 ms
  long:X,Y[,MS]      press MS ms (default 800)
  swipe:X1,Y1,X2,Y2[,MS]   drag in MS ms (default 300)
  sleep:MS
--hold S keeps the device alive S seconds before the first action (the
compositor needs a moment to pick a new device up; default 1.0).
--transform N gives the coordinates in SCREEN fractions for a Hyprland
output transform N (0 upright portrait, 1 = 90 degrees: the tablet on its
stand in landscape); the default 0 is the panel's own frame.
"""

import fcntl
import os
import struct
import sys
import time

RANGE = 4095

EV_SYN, EV_KEY, EV_ABS = 0, 1, 3
SYN_REPORT = 0
BTN_TOUCH = 0x14A
ABS_X, ABS_Y = 0x00, 0x01
ABS_MT_SLOT, ABS_MT_POSITION_X, ABS_MT_POSITION_Y = 0x2F, 0x35, 0x36
ABS_MT_TRACKING_ID = 0x39
INPUT_PROP_DIRECT = 1

UI_SET_EVBIT = 0x40045564
UI_SET_KEYBIT = 0x40045565
UI_SET_ABSBIT = 0x40045567
UI_SET_PROPBIT = 0x4004556E
UI_DEV_SETUP = 0x405C5503
UI_ABS_SETUP = 0x401C5504
UI_DEV_CREATE = 0x5501
UI_DEV_DESTROY = 0x5502


class Touch:
    def __init__(self):
        self.fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
        for ev in (EV_SYN, EV_KEY, EV_ABS):
            fcntl.ioctl(self.fd, UI_SET_EVBIT, ev)
        fcntl.ioctl(self.fd, UI_SET_KEYBIT, BTN_TOUCH)
        fcntl.ioctl(self.fd, UI_SET_PROPBIT, INPUT_PROP_DIRECT)
        for code, top in ((ABS_X, RANGE), (ABS_Y, RANGE), (ABS_MT_SLOT, 0),
                          (ABS_MT_POSITION_X, RANGE),
                          (ABS_MT_POSITION_Y, RANGE),
                          (ABS_MT_TRACKING_ID, 65535)):
            fcntl.ioctl(self.fd, UI_SET_ABSBIT, code)
            # struct uinput_abs_setup: u16 code, pad, struct input_absinfo
            # (value, minimum, maximum, fuzz, flat, resolution)
            fcntl.ioctl(self.fd, UI_ABS_SETUP,
                        struct.pack("HHiiiiii", code, 0, 0, 0, top, 0, 0, 0))
        # struct uinput_setup: input_id (bus, vendor, product, version),
        # name[80], ff_effects_max
        fcntl.ioctl(self.fd, UI_DEV_SETUP,
                    struct.pack("HHHH80sI", 0x06, 0x1234, 0x5678, 1,
                                b"yt11-faketouch", 0))
        fcntl.ioctl(self.fd, UI_DEV_CREATE)
        self.tracking = 0

    def close(self):
        fcntl.ioctl(self.fd, UI_DEV_DESTROY)
        os.close(self.fd)

    def emit(self, etype, code, value):
        os.write(self.fd, struct.pack("llHHi", 0, 0, etype, code, value))

    def sync(self):
        self.emit(EV_SYN, SYN_REPORT, 0)

    transform = 0

    def move(self, x, y):
        if self.transform == 1:
            x, y = 1.0 - y, x
        elif self.transform == 2:
            x, y = 1.0 - x, 1.0 - y
        elif self.transform == 3:
            x, y = y, 1.0 - x
        px = int(max(0.0, min(1.0, x)) * RANGE)
        py = int(max(0.0, min(1.0, y)) * RANGE)
        self.emit(EV_ABS, ABS_MT_POSITION_X, px)
        self.emit(EV_ABS, ABS_MT_POSITION_Y, py)
        self.emit(EV_ABS, ABS_X, px)
        self.emit(EV_ABS, ABS_Y, py)

    def down(self, x, y):
        self.tracking += 1
        self.emit(EV_ABS, ABS_MT_SLOT, 0)
        self.emit(EV_ABS, ABS_MT_TRACKING_ID, self.tracking)
        self.move(x, y)
        self.emit(EV_KEY, BTN_TOUCH, 1)
        self.sync()

    def up(self):
        self.emit(EV_ABS, ABS_MT_TRACKING_ID, -1)
        self.emit(EV_KEY, BTN_TOUCH, 0)
        self.sync()

    def press(self, x, y, ms):
        self.down(x, y)
        time.sleep(ms / 1000.0)
        self.up()

    def swipe(self, x1, y1, x2, y2, ms):
        steps = max(2, int(ms / 10))
        self.down(x1, y1)
        for i in range(1, steps + 1):
            time.sleep(ms / 1000.0 / steps)
            f = i / steps
            self.move(x1 + (x2 - x1) * f, y1 + (y2 - y1) * f)
            self.sync()
        time.sleep(0.03)
        self.up()


def main(argv):
    hold = 1.0
    while len(argv) >= 2 and argv[0] in ("--hold", "--transform"):
        if argv[0] == "--hold":
            hold = float(argv[1])
        else:
            Touch.transform = int(argv[1])
        argv = argv[2:]
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0 if argv else 2
    touch = Touch()
    try:
        time.sleep(hold)
        for action in argv:
            name, _, rest = action.partition(":")
            vals = [float(v) for v in rest.split(",")] if rest else []
            if name == "tap":
                touch.press(vals[0], vals[1], 60)
            elif name == "long":
                touch.press(vals[0], vals[1], vals[2] if len(vals) > 2 else 800)
            elif name == "swipe":
                touch.swipe(vals[0], vals[1], vals[2], vals[3],
                            vals[4] if len(vals) > 4 else 300)
            elif name == "sleep":
                time.sleep(vals[0] / 1000.0)
            else:
                print(f"unknown action {action!r}", file=sys.stderr)
                return 2
            time.sleep(0.15)
    finally:
        time.sleep(0.2)
        touch.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
