# Himax HX83102P touch and pen: clean mainline driver

Decision (owner, 2026-11-15): write a clean, upstreamable driver directly,
not a port of the vendor driver.

## The hardware

- TDDI: one Himax HX83102P drives the BOE 1200x2000 panel (DSI) and senses
  touch and pen (SPI0 cs0, 9.6 MHz; IRQ GPIO1 falling edge; reset GPIO2,
  shared with the display side). See `docs/hardware/BOARD.md`.
- **Zero flash**: the touch MCU has no firmware storage. The host uploads the
  firmware into its SRAM after every power-on, every resume and every MCU
  exception, then checks it with the chip's CRC engine.
- Firmware on the unit: `/vendor/firmware/Himax_firmware.bin` (stock
  S240301). Not redistributable: the install extracts it from the unit's own
  `super` partition and installs it as `/lib/firmware/himax/hx83102p.bin`.
- Pen: Lenovo Precision Pen 2 (WGP), reported by the touch MCU itself:
  pressure 0-4095, tilt X/Y -60..60, barrel buttons, eraser (stock input
  device `himax-pen`).

## Sources of truth

1. The vendor driver actually built into the stock kernel:
   `src/lenovo-gpl-4.14/drivers/input/touchscreen/mediatek/hxchipset/`
   (`HIMAX_DRIVER_VER "2.0.0.68_LC_00"`; build switches in `himax_common.h`:
   `HX_ZERO_FLASH`, `HX_PROTOCOL_B_3PA`, `HX_RESUME_SEND_CMD`,
   `HX_EXCP_RECOVERY`, `HX_RST_PIN_FUNC`, `HX_SMART_WAKEUP`). The relevant
   code: SPI framing in `himax_platform.c`; register access, ZF upload
   (`himax_mcu_firmware_update_0f`, `himax_zf_part_info`,
   `himax_mcu_write_sram_0f`, `himax_sram_write_crc_check`), sense on/off and
   exception handling in `himax_ic_incell_core.c`; HX83102-specific values in
   `himax_ic_HX83102.c`; event parsing (fingers, pen, exception patterns) in
   `himax_common.c`. `hxchipset_8789p1_8185p3/` is a sibling copy, for
   comparison only.
2. Template for structure and style: the 7.1 tree's Novatek TDDI driver,
   `drivers/input/touchscreen/novatek-nvt-ts-{core,spi,i2c}.c` and
   `novatek-nvt-ts.h` (core/transport split, `firmware-name`,
   `devm_drm_panel_add_follower`).
3. Existing mainline Himax touch drivers, for naming and binding style:
   `himax_hx83112b.c`, `himax_hx852x.c`,
   `Documentation/devicetree/bindings/input/touchscreen/himax,hx852es.yaml`.

## Design

- Files: `drivers/input/touchscreen/himax_hx83102.c` (core: chip ops, ZF
  upload, event parsing, input devices, panel follower, PM) and
  `himax_hx83102_spi.c` (SPI transport), `himax_hx83102.h`. Kconfig
  `TOUCHSCREEN_HIMAX_HX83102` (+ `_SPI`), tristate, depends on `SPI` and
  `DRM_PANEL` where the follower is used.
- DT binding `Documentation/devicetree/bindings/input/touchscreen/himax,hx83102p.yaml`:
  `compatible = "himax,hx83102p-ts"`, `reg`, `spi-max-frequency`,
  `interrupts`, `reset-gpios`, optional `firmware-name` (default
  `himax/hx83102p.bin`), optional `panel` (phandle), standard
  `touchscreen-*` properties (size, inverted-x/y, swapped-x-y) through
  `touchscreen.yaml`.
- Power sequencing follows the panel: when `panel` is set, the touch side
  starts in `panel_prepared` (reset release, firmware upload, sense on) and
  stops in `panel_unpreparing` (sense off, IRQ off); without `panel` (early
  bring-up on the bootloader's framebuffer), probe brings it up directly.
- Firmware upload: parse the partition table the way `himax_zf_part_info`
  does, write each part to SRAM over SPI in bounded chunks, verify each with
  the hardware CRC, retry a bounded number of times, then reload/sense-on.
  Keep the firmware in memory after the first `request_firmware` so resume
  does not hit the file system.
- Reporting: one input device for fingers (MT protocol B, up to 10 slots,
  `INPUT_MT_DIRECT | INPUT_MT_DROP_UNUSED`, `touchscreen_report_pos()`), a
  second input device for the pen (`BTN_TOOL_PEN`, `BTN_TOOL_RUBBER`,
  `BTN_TOUCH`, `BTN_STYLUS`, `BTN_STYLUS2`, `ABS_X/Y`, `ABS_PRESSURE`,
  `ABS_TILT_X/Y`, `INPUT_PROP_DIRECT`), same coordinate transform.
- Exceptions: recognise the vendor's exception/ESD event patterns and
  re-upload the firmware from a work item, rate-limited.
- Out of scope: gestures and smart wake-up, proc/debugfs debug nodes,
  inspection/MP tests, flash upgrade paths, guest info, palm/glove modes,
  the Novatek panel variant.

## Quality bar

`checkpatch.pl --strict` clean, `W=1` build clean with LLVM, binding passes
`dt_binding_check`, no vendor-style globals, every vendor magic number named
(`#define`) with a comment saying which vendor function it comes from. A
KUnit test covers the event parser (finger and pen packets, exception
patterns) with packets built from the vendor's parsing code.

## Verification on the unit (later phase)

Needs the tablet on a mainline kernel with SPI0 and the panel: `evtest`
over SSH while the owner touches and draws at agreed moments; firmware
upload time and CRC results in `dmesg`; suspend/resume and an induced
exception (sense off/on loop) must bring touch back.
