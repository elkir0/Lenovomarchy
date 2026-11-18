#!/usr/bin/env python3
"""Fit lens shading correction coefficients from flat-field raw frames (stdlib only).

Usage:
  lsc-fit.py <frame> <width> <height> --bayer RGGB|BGGR|GRBG|GBRG
             [--layout le10|p12|raw10|u16|u16h] [--stride N] [--black-level 64]
             [--centre auto|X,Y] [--grid 32] [frame2 ...]
  lsc-fit.py <frame> <width> <height> --bayer ... --check <tuning.yaml>

Input: one or more raw frames of a uniformly lit white surface (several
frames are averaged). Runs on the Mac or on the tablet.

Model (the libcamera Lsc block this tool writes):

  - Lsc:
      centre: [ cx, cy ]       # optical centre as a fraction of width, height
      red:   [ k1, k2, k3 ]    # gain(r) = 1 + k1*r^2 + k2*r^4 + k3*r^6
      green: [ k1, k2, k3 ]
      blue:  [ k1, k2, k3 ]

r is the distance from the centre divided by half the frame diagonal (square
pixels); the consumer multiplies black-subtracted linear raw data by the gain,
clamped to [1, 4].

Steps:

1. Unpack every frame with raw2rgb.py (same directory; layout detected when
   --layout is omitted) and split the four Bayer phase planes.
2. Reduce each plane to a grid of cell means: --grid cells across the width
   and round(grid * height / width) down the frame (32 x 24 for 4:3). The
   black level is subtracted and the two green planes are averaged. A cell
   holding any sample >= 1000 (of 1023, in any frame) is ignored for that
   channel, as is a cell whose level is at or below black; frames are
   averaged cell by cell. Cell positions are the exact mean pixel-centre
   positions of each channel's samples.
3. Optical centre (--centre auto, the default): coarse-to-fine grid search
   over candidate centres (0.20..0.80 of width and height in steps of 0.05,
   then refined around the best candidate in steps of 0.01, 0.002 and
   0.0004) that minimises the relative residual of a least-squares fit of
   the green cells to the correction model with a free intercept. A
   radially symmetric falloff is fitted exactly only about its own centre;
   an offset adds an odd term the even polynomial cannot absorb, so the
   residual minimum is the optical centre. The search needs a measurable
   falloff (a few percent); on a nearly flat field the centre hardly
   matters. --centre X,Y gives the centre as fractions instead.
4. Fit, per channel: the target gain of a cell is centre_value / cell_value,
   where centre_value is the mean of the valid cells within r < 0.1. The
   weighted linear least-squares fit (normal equations, pure Python)
   minimises the relative error of the corrected field, sum((cell * gain /
   centre - 1)^2), with a free intercept a0; the coefficients are divided
   by a0, so gain(0) = 1 exactly for every channel: the correction keeps the
   colour ratio at the centre (white balance owns it) and the r < 0.1
   averaging does not bias k. The centre and the k values are rounded to 4
   decimal places before the residuals are computed.

Output (stdout): comment lines (cells ignored, centre, centre level per
channel, RMS and maximum relative residual, corner gain at r = 1) followed by
the YAML block, ready to paste into a tuning file. Exit code 1 with a message
on stderr when the frame is unusable: fewer than half the cells of a channel
valid, a centre level (black-subtracted) under 100 of 1023, or an RMS fit
residual above 5 % (a maximum residual above 5 % only adds a warning line, so
a few dusty cells do not block the fit).

--check <yaml> applies the coefficients of an Lsc block (found in a full
tuning file or alone) to the frame's grid, with the consumer's [1, 4] clamp,
and prints the centre-to-corner falloff per channel before and after the
correction, plus the spread of the corrected cells.
"""

import argparse
from array import array
from operator import add
import math
import os
import re
import sys

sys.dont_write_bytecode = True  # keep tools/camera free of __pycache__
sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import raw2rgb  # noqa: E402

CLIP_LEVEL = 1000          # a sample at or above this (10-bit) is clipped
MIN_CENTRE_LEVEL = 100.0   # black-subtracted centre level, of 1023
MAX_RMS_RESIDUAL = 0.05
CENTRE_RADIUS = 0.1        # cells within this r give the centre value
GAIN_MIN = 1.0             # consumer clamp
GAIN_MAX = 4.0
CHANNELS = ('red', 'green', 'blue')
SHORT = {'red': 'R', 'green': 'G', 'blue': 'B'}

# Centre search: coarse grid, then refinement steps around the best point.
SEARCH_LO = 0.20
SEARCH_HI = 0.80
SEARCH_STEP = 0.05
REFINE_STEPS = (0.01, 0.002, 0.0004)
REFINE_SPAN = 3            # candidates per side at each refinement step


class Unusable(Exception):
    """The frame cannot give a trustworthy fit (exit code 1)."""


# ---------------------------------------------------------------------------
# Linear algebra and the model.

def solve(m: list[list[float]], b: list[float]) -> list[float] | None:
    """Solve m x = b by Gaussian elimination with partial pivoting."""
    n = len(b)
    a = [list(row) + [bv] for row, bv in zip(m, b)]
    scale = max(abs(v) for row in m for v in row) or 1.0
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(a[r][col]))
        if abs(a[piv][col]) <= 1e-14 * scale:
            return None
        a[col], a[piv] = a[piv], a[col]
        p = a[col]
        for r in range(col + 1, n):
            f = a[r][col] / p[col]
            if f:
                row = a[r]
                for c in range(col, n + 1):
                    row[c] -= f * p[c]
    x = [0.0] * n
    for r in range(n - 1, -1, -1):
        x[r] = (a[r][n] - sum(a[r][c] * x[c] for c in range(r + 1, n))) / a[r][r]
    return x


def fit_inverse_poly(r2s: list[float], vs: list[float]) -> tuple[list[float] | None, float]:
    """Least squares for sum((v_i * m(r_i) - 1)^2), m = a0 + a1 r^2 + a2 r^4 + a3 r^6.

    v_i * m(r_i) is the corrected level of cell i relative to the reference
    level, so the residuals are relative errors of the flattened field.
    Returns (a, sum of squared residuals), or (None, inf) when singular.
    """
    m00 = m01 = m02 = m03 = m11 = m12 = m13 = m22 = m23 = m33 = 0.0
    b0 = b1 = b2 = b3 = 0.0
    for r2, v in zip(r2s, vs):
        f1 = v * r2
        f2 = f1 * r2
        f3 = f2 * r2
        m00 += v * v
        m01 += v * f1
        m02 += v * f2
        m03 += v * f3
        m11 += f1 * f1
        m12 += f1 * f2
        m13 += f1 * f3
        m22 += f2 * f2
        m23 += f2 * f3
        m33 += f3 * f3
        b0 += v
        b1 += f1
        b2 += f2
        b3 += f3
    a = solve(
        [[m00, m01, m02, m03], [m01, m11, m12, m13], [m02, m12, m22, m23], [m03, m13, m23, m33]],
        [b0, b1, b2, b3],
    )
    if a is None:
        return None, math.inf
    ssr = len(vs) - (a[0] * b0 + a[1] * b1 + a[2] * b2 + a[3] * b3)
    return a, max(0.0, ssr)


def gain_at(k: list[float], r2: float) -> float:
    return 1.0 + r2 * (k[0] + r2 * (k[1] + r2 * k[2]))


def radii2(xs: list[float], ys: list[float], centre: tuple[float, float],
           width: int, height: int) -> list[float]:
    """Squared r of each point (pixel coordinates), r = distance / half diagonal."""
    px = centre[0] * width
    py = centre[1] * height
    inv = 4.0 / (width * width + height * height)
    return [((x - px) * (x - px) + (y - py) * (y - py)) * inv for x, y in zip(xs, ys)]


def farthest_corner_r(centre: tuple[float, float], width: int, height: int) -> float:
    inv = 2.0 / math.hypot(width, height)
    return max(
        math.hypot((u - centre[0]) * width, (v - centre[1]) * height) * inv
        for u in (0.0, 1.0) for v in (0.0, 1.0)
    )


# ---------------------------------------------------------------------------
# Frames to a grid of cell means.

def resolve_layout(path: str, width: int, height: int, stride: int | None) -> str:
    """raw2rgb's detection, plus a u16 / u16h tie-break on the unused bits."""
    with open(path, 'rb') as f:
        data = f.read()
    layout, note = raw2rgb.detect_layout(data, width, height, stride)
    if layout in ('u16', 'u16h'):
        # Same byte geometry: a u16 frame leaves the top 6 bits of every word
        # zero, a u16h frame the bottom 6 bits.
        bpl = raw2rgb.bpl_for(width, 'u16')
        s = stride if stride is not None else bpl
        words = []
        for y in range(0, height, max(1, height // 64)):
            if y * s + bpl <= len(data):
                words.extend(memoryview(data[y * s:y * s + bpl]).cast('H'))
        if words and max(words) < 1024:
            layout = 'u16'
        elif words and not any(w & 0x3F for w in words):
            layout = 'u16h'
        note += f'; {layout} from the unused container bits'
    print(f'note: {note}', file=sys.stderr)
    return layout


def read_planes(path: str, width: int, height: int, stride: int, layout: str):
    """Return the four Bayer phase planes (p00, p01, p10, p11) as 10-bit arrays."""
    with open(path, 'rb') as f:
        data = f.read()
    bpl = raw2rgb.bpl_for(width, layout)
    need = (height - 1) * stride + bpl
    if len(data) < need:
        raise Unusable(
            f'{path} is {len(data)} bytes; a {width}x{height} {layout} frame '
            f'with a {stride}-byte stride needs {need}'
        )
    phases, _, _ = raw2rgb.unpack_phases(data, width, height, stride, layout)
    tbl = raw2rgb._phase_to_raw_tbl(layout)
    return [array('H', map(tbl.__getitem__, p)) for p in phases]


def cell_bounds(n_px: int, n_cells: int) -> list[int]:
    return [i * n_px // n_cells for i in range(n_cells + 1)]


def plane_cells(plane: array, hw: int, xb: list[int], yb: list[int]) -> tuple[list[int], list[bool]]:
    """Per-cell sample sums and clipped flags of one phase plane."""
    gx = len(xb) - 1
    sums = [0] * (gx * (len(yb) - 1))
    clipped = [False] * len(sums)
    spans = list(zip(xb[:-1], xb[1:]))
    for j in range(len(yb) - 1):
        base = j * gx
        for y in range(yb[j], yb[j + 1]):
            row = plane[y * hw:(y + 1) * hw]
            hot = max(row) >= CLIP_LEVEL
            for i, (x0, x1) in enumerate(spans):
                seg = row[x0:x1]
                sums[base + i] += sum(seg)
                if hot and max(seg) >= CLIP_LEVEL:
                    clipped[base + i] = True
    return sums, clipped


class Grid:
    """Cell means per channel (black-subtracted, None when ignored)."""

    def __init__(self, width: int, height: int, gx: int, gy: int):
        self.width = width
        self.height = height
        self.gx = gx
        self.gy = gy
        self.ncell = gx * gy
        self.xs: dict[str, list[float]] = {}
        self.ys: dict[str, list[float]] = {}
        self.vals: dict[str, list[float | None]] = {}
        self.clipped: dict[str, int] = {}
        self.dark: dict[str, int] = {}

    def valid(self, ch: str) -> tuple[list[float], list[float], list[float]]:
        pts = [(x, y, v) for x, y, v in zip(self.xs[ch], self.ys[ch], self.vals[ch]) if v is not None]
        return [p[0] for p in pts], [p[1] for p in pts], [p[2] for p in pts]

    def corner_indices(self) -> tuple[int, ...]:
        gx, gy = self.gx, self.gy
        return (0, gx - 1, (gy - 1) * gx, gy * gx - 1)


def measure(paths: list[str], width: int, height: int, stride: int, layout: str,
            order: str, black: int, grid: int) -> Grid:
    hw = width // 2
    hh = height // 2
    gx = grid
    gy = max(2, round(grid * height / width))
    if gx < 4 or gx > hw or gy > hh:
        raise ValueError(f'--grid {grid} gives {gx}x{gy} cells, which does not fit a {width}x{height} frame')
    xb = cell_bounds(hw, gx)
    yb = cell_bounds(hh, gy)
    ncell = gx * gy
    sums = [[0] * ncell for _ in range(4)]
    clip = [[False] * ncell for _ in range(4)]
    for path in paths:
        planes = read_planes(path, width, height, stride, layout)
        for p in range(4):
            s, c = plane_cells(planes[p], hw, xb, yb)
            sums[p] = list(map(add, sums[p], s))
            clip[p] = [a or b for a, b in zip(clip[p], c)]
    counts = [(xb[i + 1] - xb[i]) * (yb[j + 1] - yb[j]) * len(paths)
              for j in range(gy) for i in range(gx)]

    def means(p: int) -> list[float]:
        return [s / n - black for s, n in zip(sums[p], counts)]

    ri, g1i, g2i, bi = raw2rgb.BAYER_LAYOUTS[order]
    chans = {
        'red': (means(ri), clip[ri], (ri,)),
        'green': ([0.5 * (a + b) for a, b in zip(means(g1i), means(g2i))],
                  [a or b for a, b in zip(clip[g1i], clip[g2i])], (g1i, g2i)),
        'blue': (means(bi), clip[bi], (bi,)),
    }
    g = Grid(width, height, gx, gy)
    for ch, (vals, clipped, phases) in chans.items():
        # Plane pixel j sits at full-resolution column 2j + dx (centre
        # 2j + dx + 0.5); the mean over a cell's columns x0..x1-1 is
        # x0 + x1 + dx - 0.5, with dx averaged over the two green phases.
        dx = sum(p & 1 for p in phases) / len(phases)
        dy = sum(p >> 1 for p in phases) / len(phases)
        g.xs[ch] = [xb[i] + xb[i + 1] + dx - 0.5 for j in range(gy) for i in range(gx)]
        g.ys[ch] = [yb[j] + yb[j + 1] + dy - 0.5 for j in range(gy) for i in range(gx)]
        g.vals[ch] = [None if (c or v <= 1.0) else v for v, c in zip(vals, clipped)]
        g.clipped[ch] = sum(clipped)
        g.dark[ch] = sum(1 for v, c in zip(vals, clipped) if not c and v <= 1.0)
    return g


def check_valid_cells(g: Grid) -> None:
    for ch in CHANNELS:
        n = sum(1 for v in g.vals[ch] if v is not None)
        if 2 * n < g.ncell:
            raise Unusable(
                f'only {n} of {g.ncell} {ch} cells are valid ({g.clipped[ch]} with '
                f'clipped samples >= {CLIP_LEVEL}, {g.dark[ch]} at black level): '
                f'adjust the exposure so the brightest area stays below {CLIP_LEVEL}'
            )


def centre_level(r2s: list[float], vals: list[float], ch: str) -> float:
    centre_vals = [v for r2, v in zip(r2s, vals) if r2 < CENTRE_RADIUS * CENTRE_RADIUS]
    if not centre_vals:
        raise Unusable(
            f'no valid {ch} cell within r < {CENTRE_RADIUS} of the centre '
            f'(clipped there, or --grid too coarse)'
        )
    level = sum(centre_vals) / len(centre_vals)
    if level < MIN_CENTRE_LEVEL:
        raise Unusable(
            f'{ch} centre level {level:.1f} (black-subtracted) is under '
            f'{MIN_CENTRE_LEVEL:.0f} of 1023: expose longer or light the surface brighter'
        )
    return level


# ---------------------------------------------------------------------------
# Centre estimation and fit.

def estimate_centre(g: Grid) -> tuple[float, float]:
    """Centre minimising the green-plane fit residual (coarse-to-fine search)."""
    xs, ys, vs = g.valid('green')
    mean = sum(vs) / len(vs)
    vs = [v / mean for v in vs]
    cache: dict[tuple[float, float], float] = {}

    def cost(c: tuple[float, float]) -> float:
        key = (round(c[0], 6), round(c[1], 6))
        if key not in cache:
            cache[key] = fit_inverse_poly(radii2(xs, ys, key, g.width, g.height), vs)[1]
        return cache[key]

    n = int(round((SEARCH_HI - SEARCH_LO) / SEARCH_STEP))
    cands = [(SEARCH_LO + i * SEARCH_STEP, SEARCH_LO + j * SEARCH_STEP)
             for i in range(n + 1) for j in range(n + 1)]
    best = min(cands, key=cost)
    for step in REFINE_STEPS:
        cands = [(min(0.95, max(0.05, best[0] + i * step)), min(0.95, max(0.05, best[1] + j * step)))
                 for i in range(-REFINE_SPAN, REFINE_SPAN + 1)
                 for j in range(-REFINE_SPAN, REFINE_SPAN + 1)]
        best = min(cands, key=cost)
    return best


def fit_channel(g: Grid, ch: str, centre: tuple[float, float]) -> dict:
    xs, ys, vs = g.valid(ch)
    r2s = radii2(xs, ys, centre, g.width, g.height)
    level = centre_level(r2s, vs, ch)
    vrel = [v / level for v in vs]
    a, _ = fit_inverse_poly(r2s, vrel)
    if a is None or a[0] <= 0.0:
        raise Unusable(f'the {ch} fit is singular: too few valid cells away from the centre')
    k = [round(a[i] / a[0], 4) + 0.0 for i in (1, 2, 3)]
    res = [v * a[0] * gain_at(k, r2) - 1.0 for v, r2 in zip(vrel, r2s)]
    return {
        'k': k,
        'level': level,
        'rms': math.sqrt(sum(e * e for e in res) / len(res)),
        'max': max(abs(e) for e in res),
    }


# ---------------------------------------------------------------------------
# The Lsc YAML block.

def fmt_list(vals) -> str:
    return '[ ' + ', '.join(f'{v:.4f}' for v in vals) + ' ]'


def format_block(centre: tuple[float, float], ks: dict[str, list[float]]) -> list[str]:
    return [
        '  - Lsc:',
        f'      centre: {fmt_list(centre)}',
        f'      red:   {fmt_list(ks["red"])}',
        f'      green: {fmt_list(ks["green"])}',
        f'      blue:  {fmt_list(ks["blue"])}',
    ]


_KEY_RE = re.compile(r'^\s*(centre|center|red|green|blue)\s*:\s*\[([^\]]*)\]\s*$')
_LSC_RE = re.compile(r'^(\s*(?:-\s+)?)Lsc\s*:\s*$')


def parse_lsc_yaml(text: str) -> dict:
    """Parse an Lsc block: {'centre': (x, y), 'red': [k1, k2, k3], ...}.

    Reads the lines under an 'Lsc:' key (a full tuning file works) or, when
    there is none, the whole text. Only the flow-list form written by this
    tool is understood.
    """
    lines = [ln.split('#', 1)[0].rstrip() for ln in text.splitlines()]
    body = lines
    for i, ln in enumerate(lines):
        m = _LSC_RE.match(ln)
        if m:
            key_col = len(m.group(1))
            body = []
            for nxt in lines[i + 1:]:
                if not nxt.strip():
                    continue
                if len(nxt) - len(nxt.lstrip(' ')) <= key_col:
                    break
                body.append(nxt)
            break
    out: dict = {}
    for ln in body:
        m = _KEY_RE.match(ln)
        if not m:
            continue
        key = 'centre' if m.group(1) == 'center' else m.group(1)
        try:
            vals = [float(v) for v in m.group(2).split(',') if v.strip()]
        except ValueError:
            raise ValueError(f'bad number in the Lsc {key} list: {m.group(2).strip()}') from None
        out[key] = vals
    for key, n in (('centre', 2), ('red', 3), ('green', 3), ('blue', 3)):
        if key not in out:
            raise ValueError(f'the Lsc block has no {key}: [ ... ] list')
        if len(out[key]) != n:
            raise ValueError(f'the Lsc {key} list has {len(out[key])} values, expected {n}')
    out['centre'] = (out['centre'][0], out['centre'][1])
    return out


# ---------------------------------------------------------------------------
# Modes.

def header_lines(g: Grid, args: argparse.Namespace, nframes: int, layout: str, mode: str) -> list[str]:
    ign = ' '.join(f'{SHORT[ch]} {g.clipped[ch]}' for ch in CHANNELS)
    lines = [
        f'# lsc-fit.py{mode}: {g.width}x{g.height} {args.bayer.upper()} layout {layout}, '
        f'{nframes} frame(s), grid {g.gx}x{g.gy}, black level {args.black_level}',
        f'# ignored cells (clipped samples >= {CLIP_LEVEL}): {ign} of {g.ncell}',
    ]
    if any(g.dark.values()):
        dark = ' '.join(f'{SHORT[ch]} {g.dark[ch]}' for ch in CHANNELS)
        lines.append(f'# ignored cells (at or below black level): {dark}')
    return lines


def run_fit(g: Grid, args: argparse.Namespace, nframes: int, layout: str) -> int:
    check_valid_cells(g)
    if args.centre == 'auto':
        centre = estimate_centre(g)
        how = 'auto, green-plane residual search'
    else:
        centre = args.centre
        how = 'given'
    centre = (round(centre[0], 4) + 0.0, round(centre[1], 4) + 0.0)
    fits = {ch: fit_channel(g, ch, centre) for ch in CHANNELS}

    def per(fmt, key):
        return ' '.join(f'{SHORT[ch]} {fmt(fits[ch][key])}' for ch in CHANNELS)

    bad = [ch for ch in CHANNELS if fits[ch]['rms'] > MAX_RMS_RESIDUAL]
    if bad:
        raise Unusable(
            f'RMS fit residual above {MAX_RMS_RESIDUAL * 100:.0f} % '
            f'({per(lambda v: f"{v * 100:.2f} %", "rms")}): the frame is not an evenly '
            f'lit flat field (uneven lighting, texture or a non-radial falloff)'
        )
    lines = header_lines(g, args, nframes, layout, '')
    lines += [
        f'# centre: {centre[0]:.4f}, {centre[1]:.4f} ({how})',
        f'# centre level (black-subtracted, of 1023): {per(lambda v: f"{v:.1f}", "level")}',
        f'# fit residual RMS: {per(lambda v: f"{v * 100:.2f} %", "rms")}',
        f'# fit residual max: {per(lambda v: f"{v * 100:.2f} %", "max")}',
        '# corner gain (r = 1): ' + ' '.join(
            f'{SHORT[ch]} {gain_at(fits[ch]["k"], 1.0):.4f}' for ch in CHANNELS),
    ]
    rmax = farthest_corner_r(centre, g.width, g.height)
    far = {ch: gain_at(fits[ch]['k'], rmax * rmax) for ch in CHANNELS}
    if rmax > 1.0005:
        lines.append(f'# farthest frame corner (r = {rmax:.4f}) gain: '
                     + ' '.join(f'{SHORT[ch]} {far[ch]:.4f}' for ch in CHANNELS))
    if args.centre == 'auto' and max(abs(centre[0] - 0.5), abs(centre[1] - 0.5)) > 0.25:
        lines.append('# warning: the centre estimate is far from the frame centre; check the lighting')
    for ch in CHANNELS:
        if far[ch] > GAIN_MAX:
            lines.append(f'# warning: {ch} gain reaches {far[ch]:.2f} at the farthest corner; '
                         f'the consumer clamps it to {GAIN_MAX:.0f}')
    if any(fits[ch]['max'] > MAX_RMS_RESIDUAL for ch in CHANNELS):
        lines.append(f'# warning: a cell deviates by more than {MAX_RMS_RESIDUAL * 100:.0f} % '
                     f'from the fit (dust, a reflection or uneven lighting?)')
    lines += format_block(centre, {ch: fits[ch]['k'] for ch in CHANNELS})
    print('\n'.join(lines))
    return 0


def run_check(g: Grid, args: argparse.Namespace, nframes: int, layout: str) -> int:
    with open(args.check, encoding='utf-8') as f:
        lsc = parse_lsc_yaml(f.read())
    check_valid_cells(g)
    centre = lsc['centre']
    lines = header_lines(g, args, nframes, layout, ' --check')
    lines.append(f'# {args.check}: centre {centre[0]:.4f}, {centre[1]:.4f}; '
                 f'gains clamped to [{GAIN_MIN:.0f}, {GAIN_MAX:.0f}]')
    lines.append('# falloff = 1 - corner level / centre level (mean of the valid corner cells, '
                 f'cells within r < {CENTRE_RADIUS}), before -> after correction')
    corners = g.corner_indices()
    for ch in CHANNELS:
        k = lsc[ch]
        r2all = radii2(g.xs[ch], g.ys[ch], centre, g.width, g.height)
        before = g.vals[ch]
        after = [None if v is None else v * min(GAIN_MAX, max(GAIN_MIN, gain_at(k, r2)))
                 for v, r2 in zip(before, r2all)]
        valid_r2 = [r2 for r2, v in zip(r2all, before) if v is not None]
        c_before = centre_level(valid_r2, [v for v in before if v is not None], ch)
        c_after = centre_level(valid_r2, [v for v in after if v is not None], ch)
        corner_b = [before[i] for i in corners if before[i] is not None]
        corner_a = [after[i] for i in corners if after[i] is not None]
        rel = [v / c_after for v in after if v is not None]
        rms = math.sqrt(sum((x - 1.0) ** 2 for x in rel) / len(rel))
        spread = (f'corrected cells {min(rel) * 100:.2f} % .. {max(rel) * 100:.2f} % '
                  f'of centre, RMS {rms * 100:.2f} %')
        if not corner_a:
            lines.append(f'{ch + ":":<7}falloff n/a (no valid corner cell); {spread}')
            continue
        ratio_b = sum(corner_b) / len(corner_b) / c_before
        ratio_a = sum(corner_a) / len(corner_a) / c_after
        lines.append(
            f'{ch + ":":<7}falloff {(1 - ratio_b) * 100:.2f} % -> {(1 - ratio_a) * 100:.2f} % '
            f'(corner/centre {ratio_b:.4f} -> {ratio_a:.4f}); {spread}'
        )
    print('\n'.join(lines))
    return 0


# ---------------------------------------------------------------------------
# CLI.

def _centre_arg(text: str):
    if text == 'auto':
        return text
    try:
        x, y = (float(v) for v in text.split(','))
    except ValueError:
        raise argparse.ArgumentTypeError(f'expected auto or X,Y fractions, got {text!r}') from None
    if not (0.0 < x < 1.0 and 0.0 < y < 1.0):
        raise argparse.ArgumentTypeError(f'centre fractions must lie in (0, 1), got {text!r}')
    return (x, y)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description='Fit lens shading coefficients (libcamera Lsc block) from flat-field '
                    'raw frames of a uniformly lit white surface (stdlib only).',
        epilog='See the module docstring for the model, the centre search and the checks.',
    )
    ap.add_argument('frame', help='raw frame of the flat field')
    ap.add_argument('width', type=lambda x: int(x, 0), help='frame width in pixels')
    ap.add_argument('height', type=lambda x: int(x, 0), help='frame height in lines')
    ap.add_argument('more', nargs='*', metavar='frame2',
                    help='more raw frames of the same scene, averaged with the first')
    ap.add_argument('--bayer', required=True, type=str.lower,
                    choices=sorted(raw2rgb.BAYER_LAYOUTS), metavar='RGGB|BGGR|GRBG|GBRG',
                    help='Bayer CFA order of the frame')
    ap.add_argument('--layout', choices=raw2rgb.LAYOUTS, default=None,
                    help='byte layout (as raw2rgb.py); detected from the first frame when omitted')
    ap.add_argument('--stride', type=lambda x: int(x, 0), default=None,
                    help='line stride in bytes (default: the packed line size of the layout)')
    ap.add_argument('--black-level', type=int, default=64,
                    help='black level in 10-bit units (default 64)')
    ap.add_argument('--centre', type=_centre_arg, default='auto',
                    help='optical centre: auto (default, green-plane residual search) or X,Y '
                         'as fractions of width and height')
    ap.add_argument('--grid', type=int, default=32,
                    help='cells across the width (default 32; rows follow the aspect ratio)')
    ap.add_argument('--check', metavar='YAML', default=None,
                    help='apply the Lsc block of this file to the frame and print the '
                         'remaining centre-to-corner falloff instead of fitting')
    args = ap.parse_intermixed_args(argv)
    if args.width < 16 or args.height < 16:
        ap.error(f'invalid geometry {args.width}x{args.height}')
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    paths = [args.frame] + list(args.more)
    try:
        layout = args.layout or resolve_layout(args.frame, args.width, args.height, args.stride)
        bpl = raw2rgb.bpl_for(args.width, layout)
        stride = args.stride if args.stride is not None else bpl
        if stride < bpl:
            raise ValueError(f'stride {stride} is shorter than a {args.width}-pixel {layout} line ({bpl} bytes)')
        g = measure(paths, args.width, args.height, stride, layout, args.bayer,
                    args.black_level, args.grid)
        if args.check:
            return run_check(g, args, len(paths), layout)
        return run_fit(g, args, len(paths), layout)
    except Unusable as e:
        print(f'lsc-fit: unusable frame: {e}', file=sys.stderr)
        return 1
    except (OSError, ValueError) as e:
        print(f'lsc-fit: error: {e}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
