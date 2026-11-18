# Display: DSI pixel-pull fault under mediatek-drm

Facts measured on the unit (YT-J706F, S240301 firmware, mainline 7.1
`yt11` branch) on 2026-11-15. They outrank anything in `docs/research/`.

## Resolved (2026-11-15): two causes, two kernel commits

The panel shows a correct picture under mediatek-drm and Hyprland since
kernel tree `yt11` commits `e5d7b2535` and `43b97efa8`.

1. **Long packets leave the DSI in a 1.5 pull mode.** After a long packet
   (DCS long write, data type 0x39) has gone through the DSI command
   queue, the MT6785 DSI pulls 1.5 input pixels for every pixel it sends
   in video mode. Executing any short packet afterwards brings the ratio
   back to 1.0; rewriting `DSI_CMDQ*` or `DSI_CMDQ_SIZE` does not. LK's
   last command is a short one (a DCS read), Linux's panel init and DCS
   backlight end with long writes. Reproduced in LK's working state with
   `tools/display/dsidcs.py 00043902,211083b9` (ratio 1.5), undone with
   `dsidcs.py 00000500` (DCS NOP, ratio 1.0). Fix: `drm/mediatek: dsi:
   Send a short packet before video mode on MT6785` (a DCS NOP before
   every switch to video mode when the last command was long).
2. **The frame rate fell to ~53-56 Hz.** With the vendor porches, mtk_dsi
   derives 973 Mbps per lane and warns `HFP + HBP less than d-phy, FPS
   will under 60Hz`: lines take 8.38 us (8.93 us with the non-continuous
   clock) instead of 7.84 us. Below 60 Hz the panel repeats the picture
   vertically (the top bar appeared three times). LK runs at 1044 Mbps.
   Fix: `drm/panel: himax-hx83102: J706F: Run at the vendor DSI rate`
   (mode clock 174 MHz, HFP widened to 128 so the mode stays at 60 Hz;
   measured line 7.91 us, PLL 1044 MHz) and a continuous clock.

3. **A band repeated at the panel's first rows (2026-11-18).** With HFP
   128 the mode was 60.0 Hz on paper, but the DSI host adds about 0.07 us
   of LP transition per line: 7.91 us measured, 59.4 Hz. The owner saw,
   in landscape, the leftmost ~3 mm of the screen (the panel's first rows,
   over its whole width) repeat the picture found ~4 mm further in; a
   screenshot was clean. A test mode with HFP 114 (7.83 us per line,
   60.07 Hz, no underrun) removed the band. Fix: `drm/panel:
   himax-hx83102: J706F: Shorten HFP to reach 60 Hz`. The panel wants at
   least 60 Hz: measure with `yt11-dsirate` after any timing change.

How it was found: `tools/display/dsiwatch.py` logs the ratio with
dmesg-comparable timestamps while mediatek-drm is loaded as a module
(`kernel/configs/dev/drm-module.config`) on top of LK's running display
(cmdline `clk_ignore_unused pd_ignore_unused regulator_ignore_unused
modprobe.blacklist=mediatek_drm`); every power-on step replayed by hand
in LK's state kept 1.0 until a long DCS write was sent.

The sections below are the investigation record.

## Symptom

With mediatek-drm driving the panel, the screen shows a grey, repeated
and sheared picture, even for a raw fbdev test pattern. With LK's own
display left running (`initcall_blacklist=mtk_drm_init`, simpledrm on
LK's framebuffer) the picture is correct.

## Root signature (objective, no camera needed)

`tools/display/dsirate.py` (installed on the tablet as
`/usr/local/sbin/yt11-dsirate`) times the DSI0 input counters
(`DSI_INPUT_DEBUG` 0x1d4: input line and pixel) against the DSI output
line period (`DSI_STATE_DBG7` 0x164: VACT phase).

| State | Input line | Output line | Ratio | `DSI_INTSTA` |
|---|---|---|---|---|
| LK display | 7.85 µs | 7.85 µs | 1.000 | 0x80000790 |
| mediatek-drm | 5.54 µs | 8.31 µs | 1.500 | 0x80001790 (bit 12 BUFFER_UNDERRUN) |

Under mediatek-drm the DSI pulls 1.5 input pixels for every pixel it
sends: a 1200×2000 input frame is used up after 1333 output lines
(11.08 ms of a 16.62 ms VACT), then the DSI underruns for the rest of
the frame. Each panel line therefore carries 1.5 source lines with
scrambled colour, which is the grey, repeated, sheared picture.

The 1.5 factor is a pure pixel ratio. It holds:

- for every `DSI_PSCTRL` pixel format (RGB565, RGB666 packed and loose,
  RGB888, RGB101010): the DSI pulls 1.5 × (payload bytes / bpp);
- for 1, 2, 3 and 4 data lanes;
- for any HFP length and any MIPI PLL rate (973.5 and 1044 Mbps): the
  input pace follows the output line, it is the DSI that pulls;
- for 1, 2 or 3 RGB packets per line (`RGB_PKT_CNT`): the ratio scales
  with the packet count, 1.5 per packet;
- whatever feeds the DSI: the normal path through the PQ engines, RDMA0
  routed straight to DSI0, RDMA0 in memory mode (no OVL), RDMA1 in memory
  mode. With `DSI_SIZE_CON` set to 1800 wide the input counter stops at
  line 1334: the source does send 1200×2000 pixels.

## Ruled out (the ratio stays 1.5 in the DRM state, 1.0 in the LK state)

- Every readable register: full 4 KiB pages of DSI0, MIPI TX, mmsys,
  mutex, OVL0, OVL_2L0, RDMA0, COLOR0, CCORR0, AAL0, GAMMA0, DITHER0,
  POSTMASK0 and the other 0x1400xxxx pages, compared LK vs DRM. The DSI,
  mmsys and mutex pages end up identical once LK's values are written
  in the DRM state; the rest differs only in status, layer and SMI/IOMMU
  settings, and the RDMA-straight-to-DSI and RDMA-memory-mode tests
  rule those out.
- LK's DSI values written live in the DRM state, with a DSI engine reset
  (`DSI_COM_CTRL` bit 0), a D-PHY reset (bit 2), or a full stop/reset/
  reprogram/restart; LK's MIPI PLL setting; LK's routing, OVL datapath,
  RDMA FIFO/ultra settings and PQ relay modes.
- Every single bit of `DSI_PSCTRL[31:15]`, `DSI_COM_CTRL`, `DSI_TXRX_CTRL`
  (bits 6-31), `DSI_SIZE_CON` upper bits, `DSI_VM_CMD_CON`, `DSI_LFR_CON`,
  `DSI_INPUT_SETTING`, and mmsys `MISC` 0x0f0, 0x0f4, 0x0f8, toggled one at
  a time in the DRM state.
- Clocks: booting the DRM image with `clk_ignore_unused` (nothing gated),
  or ungating mm_26m, mm_disp_rsz and mm_smi_larb1 live.
- Power domains: booting the DRM image with `pd_ignore_unused`.
- The mmsys hard reset of DSI0 at probe (`resets` dropped from the DT).
- In the LK state, none of these brings the 1.5 ratio: Linux's DSI
  values, Linux's MIPI PLL, gating and ungating the DSI clocks, a DSI
  engine reset and reprogram, DCS commands sent through the DSI queue
  (display-on, `set_pixel_format 0x77`), extra `DSI_COM_CTRL` bits.

So the 1.5 mode is state that is not visible in any register and that
survives DSI soft resets, but that mediatek-drm's bring-up creates and
LK's does not.

## Side facts

- `DSI_PSCTRL[31:26]` resets to 0x0b (reads 0x2c000000 after an mmsys
  hard reset); LK keeps it, mediatek-drm writes the whole register and
  clears it. It has no effect on the ratio.
- mmsys `SW0_RST_B` bit 25 (DT reset ID `MT6785_MMSYS_DISP_DSI0_RST`)
  also resets RDMA0 (its size registers return to 720×1280), and pulsing
  bits 13 and 14 (`MT6785_MMSYS_DISP_OVL0_RST`, `_OVL0_2L_RST`) resets the
  DSI and RDMA0 as well. After such a pulse the pipeline does not restart
  by hand. Without the OVL resets at bind, LK's leftover OVL state
  (constant-colour layer, `SRC_CON` bit 4) stalls the pipeline, so the
  resets stay.
- The vendor MDP reset table (`cmdq/v3/mt6785/cmdq_mdp.c`) gives SW0 bits
  0 SMI common, 1-2 larb0/1, 3-4 CAM_MDP, 5-11 MDP engines, 19 COLOR0.
- With a non-continuous clock, mtk_dsi sets `DSI_HSTX_CKL_WC` to the
  pixel word count; LK uses the automatic mode (bit 16, result 0x1fa in
  0x068), which costs ~0.55 us less per line.
- The DSI line period under mediatek-drm is 8.31 µs (56.6 Hz) instead of
  7.85 µs (60 Hz): with the non-continuous clock the clock-lane LP
  transitions are not budgeted by the driver.
- MIPI TX impedance codes (`RTCODE`) are programmed by LK and left at 0
  by Linux (no nvmem cell): signal quality item, unrelated to the ratio.

## Tools

`tools/display/` (debug only, run on the tablet as root, never on
production data):

- `regdump.py`, `regload.py`: dump the display blocks / write values back.
- `pagedump.py name=base[:size] ...`: dump whole register pages.
- `dsirate.py [off=val ...]`: poke DSI0 registers, then print the input
  vs output line pace, the ratio and whether BUFFER_UNDERRUN recurs.
- `dsiframe.py`: DSI vertical phases against input line milestones.
- `dsimon.py`: time when each `DSI_INTSTA` bit reappears after a clear.
- `dsiwatch.py <s> [frames]`: the ratio every few frames, with
  CLOCK_MONOTONIC timestamps comparable with dmesg.
- `dsireinit.py [regsfile]`: stop, reset, reprogram and restart DSI0.
- `dsidcs.py <cmd> ...`: send raw DSI command-queue commands (comma-
  separated words for a long packet).
