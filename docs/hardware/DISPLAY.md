# Display: DSI pixel-pull fault under mediatek-drm

Facts measured on the unit (YT-J706F, S240301 firmware, mainline 7.1
`yt11` branch) on 2026-11-15. They outrank anything in `docs/research/`.

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
  also resets RDMA0 (its size registers return to 720×1280). After it,
  in the LK state, the pipeline does not restart by hand.
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
- `dsireinit.py [regsfile]`: stop, reset, reprogram and restart DSI0.
- `dsidcs.py <cmdq word> ...`: send raw DSI command-queue words.
