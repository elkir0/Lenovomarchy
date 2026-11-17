#!/bin/sh
# Capture raw frames from the MT6785 camera pipeline through the V4L2
# media controller (mt6785-seninf + mt6785-camsv modules):
#
#   ov8856 -> mtk-mt6785-seninf -> mtk-mt6785-camsv -> /dev/videoN
#
# Sets the pipeline formats with media-ctl, streams N frames with
# v4l2-ctl into one file and converts the first frame to PNG with
# raw2png.py (same directory).
#
# Tools: Arch Linux ARM packages  v4l-utils  (media-ctl, v4l2-ctl),
# python (for raw2png.py).
#
# Usage: v4l2-capture.sh [-d /dev/media0] [-n frames] [-o out.raw]
#                        [-p out.png] [-w width] [-h height]
# Run as root (or with write access to the media and video nodes).

set -eu

MEDIA=/dev/media0
FRAMES=10
WIDTH=640
HEIGHT=480
OUT=/tmp/mt6785-frame.raw
PNG=/tmp/mt6785-frame.png
# Default Bayer order matches the ov8856 24 MHz 640x480 mode (SBGGR10).
FMT=SBGGR10P
MBUS=SBGGR10_1X10

usage() {
	sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'
	exit 2
}

while getopts d:n:o:p:w:h: opt; do
	case "$opt" in
	d) MEDIA=$OPTARG ;;
	n) FRAMES=$OPTARG ;;
	o) OUT=$OPTARG ;;
	p) PNG=$OPTARG ;;
	w) WIDTH=$OPTARG ;;
	h) HEIGHT=$OPTARG ;;
	*) usage ;;
	esac
done
shift $((OPTIND - 1))

for tool in media-ctl v4l2-ctl; do
	if ! command -v "$tool" >/dev/null 2>&1; then
		echo "error: $tool not found (Arch package: v4l-utils)" >&2
		exit 1
	fi
done

HERE=$(dirname "$0")

echo "== media graph ($MEDIA)"
media-ctl -d "$MEDIA" -p

# Entity and pad names as the mt6785-cam drivers register them.
VIDEO=$(media-ctl -d "$MEDIA" -e "mtk-mt6785-camsv")
if [ -z "$VIDEO" ]; then
	# Fall back to the first capture node of the media device.
	VIDEO=$(media-ctl -d "$MEDIA" -p | awk '
		/entity [0-9]+:/ { ent = $0 }
		- entity .* Video Capture$/{ print prev; exit }
		{ prev = ent }')
	VIDEO=${VIDEO##*/}
fi
if [ -z "$VIDEO" ]; then
	echo "error: no video capture entity in $MEDIA" >&2
	exit 1
fi
VIDEO=/dev/$VIDEO
echo "== capture node: $VIDEO"

# Format the whole pipeline: sensor -> seninf -> camsv subdev -> video.
media-ctl -d "$MEDIA" -V "\"ov8856 2-0036\":0 [fmt:$MBUS/${WIDTH}x${HEIGHT}]"
media-ctl -d "$MEDIA" -V '"mtk-mt6785-seninf":0 [fmt:'"$MBUS/${WIDTH}x${HEIGHT}"']'
media-ctl -d "$MEDIA" -V '"mtk-mt6785-seninf":3 [fmt:'"$MBUS/${WIDTH}x${HEIGHT}"']'
media-ctl -d "$MEDIA" -V '"mtk-mt6785-camsv":0 [fmt:'"$MBUS/${WIDTH}x${HEIGHT}"']'

v4l2-ctl -d "$VIDEO" --set-fmt-video=width="$WIDTH",height="$HEIGHT",pixelformat=$FMT
v4l2-ctl -d "$VIDEO" -V

echo "== streaming $FRAMES frames"
v4l2-ctl -d "$VIDEO" --stream-mmap=4 --stream-count="$FRAMES" \
	--stream-to="$OUT" --verbose

echo "== saved $OUT ($(wc -c <"$OUT") bytes)"
v4l2-ctl -d "$VIDEO" --log-status || true

if [ -x "$(command -v python3)" ] && [ -f "$HERE/raw2png.py" ]; then
	BPL=$((WIDTH * 10 / 8))
	echo "== converting first frame to $PNG (stride $BPL)"
	dd if="$OUT" of=/tmp/frame1.raw bs="$((BPL * HEIGHT))" count=1 2>/dev/null
	python3 "$HERE/raw2png.py" /tmp/frame1.raw "$WIDTH" "$HEIGHT" "$BPL" "$PNG"
else
	echo "note: python3/raw2png.py not found; skip PNG conversion" >&2
fi
