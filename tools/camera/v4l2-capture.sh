#!/bin/sh
# Capture raw frames from the MT6785 camera pipeline through the V4L2
# media controller (mt6785-seninf + mt6785-camsv modules):
#
#   sensor -> mtk-mt6785-seninf (selector) -> mtk-mt6785-camsv -> /dev/videoN
#
# Selects the sensor (-c): the seninf is an input selector, every bound
# sensor has a link to the sink pad of its CSI port and exactly one of
# those links is enabled (the driver switches the selection itself when
# another one is enabled), so the script just enables the chosen link.
# It then sets the sensor mode (-s), reads back the media bus code the
# sensor actually uses (media-ctl --get-v4l2), sets the same code and
# size on the seninf sink and camsv sink pads, the matching unpacked
# 10-bit fourcc on the video node (bytesperline = width * 2), streams N
# frames and converts the last one to a PNG with raw2rgb.py
# --layout u16 --bayer <order>.
#
# FOURCC/BAYER MAP (bus code -> video fourcc -> raw2rgb --bayer):
#   SBGGR10_1X10 -> BG10 -> bggr
#   SGBRG10_1X10 -> GB10 -> gbrg
#   SGRBG10_1X10 -> BA10 -> grbg
#   SRGGB10_1X10 -> RG10 -> rggb
#
# BYTE LAYOUT: the driver writes each 10-bit sample in a little-endian
# 16-bit word, value in the low bits (CAMSV FMT_SEL 0x102 / PAK 5), i.e.
# the standard V4L2 unpacked 10-bit Bayer layout; decode with
# raw2rgb.py --layout u16 (the same thing libcamera's software ISP
# reads).  If the driver's fmt_sel/pak/bytes_per_px_x8 module parameters
# are overridden, the layout changes and the decode must follow (e.g.
# --layout le10 for PAK 1 with a 10-bit line).
#
# Tools: Arch Linux ARM packages  v4l-utils  (media-ctl, v4l2-ctl),
# python (for raw2rgb.py).
#
# Usage: v4l2-capture.sh [-d /dev/media0] [-n frames] [-o out.raw]
#                        [-p out.png] [-s WxH] [-e EXPOSURE] [-g GAIN]
#                        [-t] [-c ov8856|s5k4h7]
#   -c SENSOR   camera: ov8856 (default; cam0, rear, CSI port 1) or
#               s5k4h7 (cam1, assumed front, CSI port 2)
#   -n FRAMES   frames to stream (default 10)
#   -s WxH      sensor mode (default 640x480; ov8856 24 MHz modes:
#               640x480, 1632x1224, 3264x2448; s5k4h7: 640x480,
#               1632x1224, 3264x1836, 3264x2448)
#   -e LINES    sensor exposure in lines (range: v4l2-ctl -l on the
#               sensor subdev; ov8856 640x480: max 614)
#   -g GAIN     sensor analogue gain (ov8856: 128..2047)
#   -t          sensor test pattern (colour bars); without -t it is off
#   -o FILE     raw output (default /tmp/mt6785-frame.raw)
#   -p FILE     PNG of the last frame (default /tmp/mt6785-frame.png)
#   -d DEV      media device (default /dev/media0)
# Run as root (or with write access to the media and video nodes).

set -eu

MEDIA=/dev/media0
FRAMES=10
SIZE=640x480
OUT=/tmp/mt6785-frame.raw
PNG=/tmp/mt6785-frame.png
EXPOSURE=
GAIN=
TESTPAT=0
CAM=ov8856

usage() {
	sed -n '2,/^# Run as root/p' "$0" | sed 's/^# \{0,1\}//'
	exit 2
}

while getopts d:n:o:p:s:e:g:tc: opt; do
	case "$opt" in
	d) MEDIA=$OPTARG ;;
	n) FRAMES=$OPTARG ;;
	o) OUT=$OPTARG ;;
	p) PNG=$OPTARG ;;
	s) SIZE=$OPTARG ;;
	e) EXPOSURE=$OPTARG ;;
	g) GAIN=$OPTARG ;;
	t) TESTPAT=1 ;;
	c) CAM=$OPTARG ;;
	*) usage ;;
	esac
done
shift $((OPTIND - 1))

case "$SIZE" in
[0-9]*x[0-9]*) ;;
*) echo "error: -s wants WxH (e.g. 640x480)" >&2; exit 1 ;;
esac
WIDTH=${SIZE%x*}
HEIGHT=${SIZE#*x}

case "$CAM" in
ov8856 | s5k4h7) ;;
*) echo "error: -c wants ov8856 or s5k4h7" >&2; exit 1 ;;
esac

for tool in media-ctl v4l2-ctl; do
	if ! command -v "$tool" >/dev/null 2>&1; then
		echo "error: $tool not found (Arch package: v4l-utils)" >&2
		exit 1
	fi
done

HERE=$(dirname "$0")
TAB=$(printf '\t')

# Entity names as the drivers register them: the subdev is
# "mtk-mt6785-camsv" and the video node entity is
# "mtk-mt6785-camsv video" (distinct on purpose).
SENINF="mtk-mt6785-seninf"
CAMSV="mtk-mt6785-camsv"
VIDEONENT="mtk-mt6785-camsv video"

echo "== media graph ($MEDIA)"
media-ctl -d "$MEDIA" -p

# Device node of the entity named exactly $1 (empty if none).
devnode() {
	media-ctl -d "$MEDIA" -p | awk -v want="$1" '
		/^- entity / {
			line = $0
			sub(/^- entity [0-9]+: /, "", line)
			sub(/ \(.*$/, "", line)
			inent = (line == want)
			next
		}
		inent && /device node name/ { print $NF; exit }'
}

VIDEO=$(devnode "$VIDEONENT")
if [ -z "$VIDEO" ]; then
	echo "error: entity \"$VIDEONENT\" not found in $MEDIA" >&2
	exit 1
fi
echo "== capture node: $VIDEO"

# Every sensor link of the seninf, enabled or not, one per line:
#   <seninf sink pad> TAB <sensor entity> TAB <sensor pad> TAB <1 if enabled>
# media-ctl -p prints them under the seninf's "padN:" headings as
#   <- "ov8856 2-0036":0 [ENABLED]     (a disabled link shows [])
# The heading, not the :N after the name, is the seninf sink pad.
LINKS=$(media-ctl -d "$MEDIA" -p | awk -v sd="$SENINF" '
	/^- entity / {
		line = $0
		sub(/^- entity [0-9]+: /, "", line)
		sub(/ \(.*$/, "", line)
		insd = (line == sd)
		next
	}
	insd && /^[[:space:]]*pad[0-9]+:/ {
		p = $0
		sub(/^[[:space:]]*pad/, "", p); sub(/:.*/, "", p)
		curpad = p
		next
	}
	insd && /<- "/ {
		s = $0
		sub(/^.*<- "/, "", s)
		name = s; sub(/".*$/, "", name)
		rest = s; sub(/^[^"]*":/, "", rest)
		srcpad = rest; sub(/[^0-9].*$/, "", srcpad)
		en = index(rest, "ENABLED") > 0 ? 1 : 0
		printf "%s\t%s\t%s\t%d\n", curpad, name, srcpad, en
	}')

SEL=
SENPAD=
SELSRC=
while IFS=$TAB read -r spad sname ssrc sen; do
	[ -n "$spad" ] || continue
	case "$sname" in
	"$CAM"*) SEL=$sname; SENPAD=$spad; SELSRC=$ssrc ;;
	esac
done <<EOF
$LINKS
EOF
if [ -z "$SEL" ]; then
	echo "error: no \"$CAM\" sensor linked to $SENINF (is it bound? see dmesg)" >&2
	exit 1
fi
SENSORDEV=$(devnode "$SEL")
if [ -z "$SENSORDEV" ]; then
	echo "error: sensor \"$SEL\" has no subdev node" >&2
	exit 1
fi
echo "== sensor: $SEL ($SENSORDEV), pad $SELSRC -> $SENINF pad $SENPAD"

# Link selection: enabling the chosen sensor's link switches the seninf
# selection by itself (the driver disables the previously enabled link
# when not streaming); the explicit disable loop is kept for older
# drivers that refuse a second enabled link with EBUSY.
echo "== selecting $CAM"
while IFS=$TAB read -r spad sname ssrc sen; do
	[ -n "$spad" ] || continue
	if [ "$sen" = 1 ] && [ "$spad" != "$SENPAD" ]; then
		echo "   disabling \"$sname\":$ssrc -> \"$SENINF\":$spad"
		media-ctl -d "$MEDIA" -l "\"$sname\":$ssrc -> \"$SENINF\":$spad [0]"
	fi
done <<EOF
$LINKS
EOF
media-ctl -d "$MEDIA" -l "\"$SEL\":$SELSRC -> \"$SENINF\":$SENPAD [1]"

# Sensor mode: keep the sensor's own bus code in the request (the code
# depends on the sensor and its flips), ask for the geometry, then read
# back what it actually took.  media-ctl also propagates the result to
# the seninf sink pad over the enabled link.
cur_fmt() {
	media-ctl -d "$MEDIA" --get-v4l2 "\"$1\":$2"
}
CODE=$(cur_fmt "$SEL" "$SELSRC" | sed -n 's/.*fmt:\([A-Z0-9_]*\)\/.*/\1/p')
echo "== sensor format request ${WIDTH}x${HEIGHT} (code ${CODE:-?})"
media-ctl -d "$MEDIA" -V "\"$SEL\":$SELSRC [fmt:${CODE:-SBGGR10_1X10}/${WIDTH}x${HEIGHT}]"
GOT=$(cur_fmt "$SEL" "$SELSRC")
echo "$GOT"
CODE=$(echo "$GOT" | sed -n 's/.*fmt:\([A-Z0-9_]*\)\/.*/\1/p')
GOTSIZE=$(echo "$GOT" | sed -n 's/.*fmt:[A-Z0-9_]*\/\([0-9]*x[0-9]*\).*/\1/p')
if [ -z "$CODE" ]; then
	echo "error: could not read the sensor's bus code" >&2
	exit 1
fi
if [ "$GOTSIZE" != "${WIDTH}x${HEIGHT}" ]; then
	echo "error: sensor refused ${WIDTH}x${HEIGHT} (took $GOTSIZE); pick one of its modes (-s)" >&2
	exit 1
fi
echo "== sensor bus code: $CODE"

# Bus code -> unpacked 10-bit fourcc on the video node, -> Bayer order
# for raw2rgb.py.
case "$CODE" in
SBGGR10_1X10) FOURCC=BG10; BAYER=bggr ;;
SGBRG10_1X10) FOURCC=GB10; BAYER=gbrg ;;
SGRBG10_1X10) FOURCC=BA10; BAYER=grbg ;;
SRGGB10_1X10) FOURCC=RG10; BAYER=rggb ;;
*)
	echo "error: unexpected bus code $CODE (need a 10-bit Bayer code)" >&2
	exit 1
	;;
esac

# Sensor controls after the mode: a mode change resets vblank and with
# it the exposure range.  The test pattern sticks across streams, so it
# is switched off explicitly without -t.
if [ "$TESTPAT" = 1 ]; then
	v4l2-ctl -d "$SENSORDEV" --set-ctrl test_pattern=1
else
	v4l2-ctl -d "$SENSORDEV" --set-ctrl test_pattern=0 || true
fi
if [ -n "$EXPOSURE" ]; then
	v4l2-ctl -d "$SENSORDEV" --set-ctrl "exposure=$EXPOSURE"
fi
if [ -n "$GAIN" ]; then
	v4l2-ctl -d "$SENSORDEV" --set-ctrl "analogue_gain=$GAIN"
fi

# Pads down the pipeline: the seninf sink of the selected port (its
# source mirrors it), the camsv sink (validated against the seninf
# source at STREAMON), then the video node, whose S_FMT also sets the
# camsv pads from the fourcc.
media-ctl -d "$MEDIA" -V "\"$SENINF\":$SENPAD [fmt:$CODE/${WIDTH}x${HEIGHT}]"
media-ctl -d "$MEDIA" -V "\"$CAMSV\":0 [fmt:$CODE/${WIDTH}x${HEIGHT}]"
echo "== seninf source / camsv sink:"
cur_fmt "$SENINF" 3
cur_fmt "$CAMSV" 0

# Video node: v4l2-ctl wants the fourcc characters.
v4l2-ctl -d "$VIDEO" --set-fmt-video=width="$WIDTH",height="$HEIGHT",pixelformat=$FOURCC
v4l2-ctl -d "$VIDEO" -V

echo "== streaming $FRAMES frames"
# A stalled stream would block v4l2-ctl forever: bound it (generous: a
# second per frame plus 10 s) so the status dumps below still run.  If
# it is cut short, its last partial 4 KiB stdio block is lost, so the
# file can end mid-frame (only whole frames are decoded below).
LIMIT=$((FRAMES + 10))
if command -v timeout >/dev/null 2>&1; then
	TIMEOUT="timeout $LIMIT"
else
	TIMEOUT=
fi
if ! $TIMEOUT v4l2-ctl -d "$VIDEO" --stream-mmap=4 --stream-count="$FRAMES" \
	--stream-to="$OUT" --verbose; then
	echo "warning: v4l2-ctl failed or was stopped after ${LIMIT}s (stalled stream?)" >&2
fi
[ -f "$OUT" ] || : >"$OUT"

BPL=$((WIDTH * 2))
FRAME_BYTES=$((BPL * HEIGHT))
TOTAL_BYTES=$((FRAME_BYTES * FRAMES))
ACTUAL_BYTES=$(wc -c <"$OUT" | tr -d ' ')
NFRAMES=$((ACTUAL_BYTES / FRAME_BYTES))
echo "== saved $OUT ($ACTUAL_BYTES of $TOTAL_BYTES expected bytes, $NFRAMES frames of $FRAME_BYTES)"

if [ "$ACTUAL_BYTES" != "$TOTAL_BYTES" ]; then
	echo "warning: byte count mismatch (dropped or short frames?)" >&2
fi

# Debugfs status of both halves, for the log.
for f in /sys/kernel/debug/mt6785-seninf-status /sys/kernel/debug/mt6785-camsv-status; do
	if [ -r "$f" ]; then
		echo "== $f"
		cat "$f"
	fi
done

if [ "$NFRAMES" -lt 1 ]; then
	echo "error: no complete frame in $OUT" >&2
	exit 1
fi

if command -v python3 >/dev/null 2>&1 && [ -f "$HERE/raw2rgb.py" ]; then
	# Decode the last complete frame: v4l2-ctl appends frames in order.
	LAST=/tmp/mt6785-frame-last.raw
	echo "== converting frame $NFRAMES to $PNG (stride $BPL, u16, $BAYER)"
	dd if="$OUT" of="$LAST" bs="$FRAME_BYTES" skip=$((NFRAMES - 1)) \
		count=1 2>/dev/null
	python3 "$HERE/raw2rgb.py" --layout u16 --stride "$BPL" \
		--bayer "$BAYER" "$LAST" "$WIDTH" "$HEIGHT" -o "$PNG"
else
	echo "note: python3/raw2rgb.py not found; skip PNG conversion" >&2
fi
