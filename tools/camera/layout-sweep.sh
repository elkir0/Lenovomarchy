#!/bin/sh
# Sweep CAMSV packer layouts (FMT_SEL x PAK x bytes-per-pixel) to find one
# libcamera's software ISP can read.
#
# WHY: with the measured FMT_SEL (0x514) = 0x102 / PAK (0x54c) = 1 the DMA
# writes each line as a continuous little-endian 10-bit bit stream ("le10",
# docs/hardware/CAMERA.md "Frame layout and first photo"), which no V4L2
# fourcc describes and libcamera cannot decode.  The goal is a layout with
# one 16-bit little-endian container per pixel and the 10-bit sample in the
# low bits — exactly V4L2_PIX_FMT_SBGGR10, what libcamera's debayer reads
# (docs/research/camera/T13-LIBCAMERA.md section 2).  The mt6785-camsv
# module exposes three parameters read at STREAMON:
#
#   /sys/module/mt6785_camsv/parameters/fmt_sel        FMT_SEL register value
#   /sys/module/mt6785_camsv/parameters/pak            PAK register value
#   /sys/module/mt6785_camsv/parameters/bytes_per_px_x8  bytes/px * 8 for BPL
#
# For each candidate this script writes the parameters, captures 3
# test-pattern frames at 640x480 through v4l2-capture.sh, saves them as
# /tmp/sweep-<fmt>-<pak>-<bpp>.raw and prints the first 24 bytes of line
# 100 and line 101 in hex (plus a u16 LE word decode) and the camsv status
# counters, so the resulting layout can be read off the output:
#
#   - u16 low-10 target: words look like 0x02a3, 0x0310 (value < 0x400);
#   - u16 MSB-justified: words look like 0xa8c0, 0xc400 (low 6 bits ~ 0);
#   - le10 (current): the u16 decode looks like garbage on both lines;
#   - p12: byte pattern 0x..ffc shifted;
#   - nothing written / drop counters rising: that combination stalls.
#
# Candidates come from the ISP 3.0 reference driver (MT8365,
# src/begonia-ftp/camera/ref/isp30/) and what CAMERA.md measured on this
# tablet: there TG1_FMT sits in FMT_SEL[2:0] with bit 8 always set,
# IMGO_BUS_SIZE_16 is FMT_SEL BIT(24), PAK modes are 0..3 with BIT(2) =
# PAK_DBL_MODE_2_PIXELS; measured 0x102/PAK=1 = le10 and 0x101/PAK=2 =
# 12-bit containers.
#
# Usage: layout-sweep.sh [-d /dev/media0] [-c ov8856|s5k4h7] [-n FRAMES]
#                        [-w WIDTH] [-h HEIGHT] [-l LINE] [candidate ...]
#   candidate   FMT_SEL:PAK:BPPX8 triple(s), e.g. 0x102:1:10; default: all
# Run as root on the tablet with the mt6785-camsv module loaded.

set -eu

MEDIA=/dev/media0
CAM=ov8856
FRAMES=3
WIDTH=640
HEIGHT=480
LINE=100
MODDIR=/sys/module/mt6785_camsv/parameters

# fmt_sel:pak:bytes_per_px_x8 — comment = why the candidate is here.
CANDIDATES='
# controls: the two layouts measured on this tablet (CAMERA.md).
0x102:1:10		le10 bitstream (current driver default; must reproduce)
0x101:2:12		p12 containers, truncated at a 10-bit stride (reference)
# FMT_SEL BIT(24) = IMGO_BUS_SIZE_16 in ISP 3.0, on top of the measured
# RAW10 config: the main hope for a 2-byte container.
0x1000102:1:16		BIT(24) + measured PAK 1, stride sized for u16
0x1000102:2:16		BIT(24) + PAK 2 (ISP 3.0 RAW10 mode value, begonia value)
0x1000102:0:16		BIT(24) + PAK 0 (ISP 3.0 RAW14 field value; nearest idle)
# PAK 0 without BIT(24): does the packer just pass the bus width through?
0x102:0:10		PAK 0, 10-bit stride
0x102:0:16		PAK 0, 2-byte stride
# PAK BIT(2) = PAK_DBL_MODE_2_PIXELS (ISP 3.0), paired two ways.
0x102:5:10		PAK 1|DBL, 10-bit stride
0x102:5:16		PAK 1|DBL, 2-byte stride
# remaining PAK field values and the remaining TG1_FMT low values.
0x102:3:10		PAK 3 (ISP 3.0 RAW8 mode value)
0x100:1:10		TG1_FMT field 0 (ISP 3.0 RAW8) + measured PAK 1
0x101:1:10		cross of the two measured single values
'

usage() {
	sed -n '2,/^# Run as root/p' "$0" | sed 's/^# \{0,1\}//'
	exit 2
}

while getopts d:c:n:w:h:l: opt; do
	case "$opt" in
	d) MEDIA=$OPTARG ;;
	c) CAM=$OPTARG ;;
	n) FRAMES=$OPTARG ;;
	w) WIDTH=$OPTARG ;;
	h) HEIGHT=$OPTARG ;;
	l) LINE=$OPTARG ;;
	*) usage ;;
	esac
done
shift $((OPTIND - 1))

HERE=$(dirname "$0")

# Optional candidate filter from the command line.
if [ "$#" -gt 0 ]; then
	CANDIDATES=$(printf '%s\n' "$@")
fi

for f in "$MODDIR/fmt_sel" "$MODDIR/pak" "$MODDIR/bytes_per_px_x8"; do
	if [ ! -w "$f" ]; then
		echo "error: $f not writable (is mt6785-camsv loaded?)" >&2
		exit 1
	fi
done

# Save the current values to restore at the end.
SAVED_FMT=$(cat "$MODDIR/fmt_sel")
SAVED_PAK=$(cat "$MODDIR/pak")
SAVED_BPP=$(cat "$MODDIR/bytes_per_px_x8")
restore() {
	echo "$SAVED_FMT" >"$MODDIR/fmt_sel"
	echo "$SAVED_PAK" >"$MODDIR/pak"
	echo "$SAVED_BPP" >"$MODDIR/bytes_per_px_x8"
}
trap restore EXIT INT TERM

hex24() {
	# First 24 bytes of line $LINE of $1, with $2 bytes per line.
	od -An -tx1 -N 24 -j $((LINE * $2)) "$1" | sed 's/^ *//'
}

u16decode() {
	# Decode the same 24 bytes as 12 LE u16 words (the sweep question:
	# value < 0x400 = sample in the low bits, i.e. the target layout).
	if command -v python3 >/dev/null 2>&1; then
		python3 - "$1" "$((LINE * $2))" <<'EOF'
import sys
path, off = sys.argv[1], int(sys.argv[2])
with open(path, 'rb') as f:
    f.seek(off)
    b = f.read(24)
words = [int.from_bytes(b[i:i+2], 'little') for i in range(0, len(b), 2)]
print(' '.join(f'{w:04x}' for w in words))
EOF
	else
		echo '(python3 not available)'
	fi
}

printf '%-14s %-4s %-4s  FILE\n' FMT_SEL PAK BPP
echo "------------------------------------------------------------------"

printf '%s\n' "$CANDIDATES" | while IFS= read -r line; do
	case "$line" in
	''|'#'*) continue ;;
	esac
	# Split fmt:pak:bppx8 (a tab or spaces may follow the triple).
	triple=${line%%[	 ]*}
	FMT=${triple%%:*}
	rest=${triple#*:}
	PAKV=${rest%%:*}
	BPPX8=${rest#*:}
	case "$FMT" in ''|*:*) continue ;; esac
	case "$PAKV" in ''|*:*) continue ;; esac
	case "$BPPX8" in ''|*:*) continue ;; esac

	# Effective bytes per pixel for the file geometry (0/10 -> 10 bits).
	case "$BPPX8" in
	0|10) EFFBPP=10 ;;
	*) EFFBPP=$BPPX8 ;;
	esac
	BPL=$((WIDTH * EFFBPP / 8))
	OUT=/tmp/sweep-$(printf '%s' "$FMT" | sed 's/^0x//')-${PAKV}-${EFFBPP}.raw

	echo 0 >"$MODDIR/bytes_per_px_x8"	# park BPL while switching
	echo "$FMT" >"$MODDIR/fmt_sel"
	echo "$PAKV" >"$MODDIR/pak"
	echo "$BPPX8" >"$MODDIR/bytes_per_px_x8"

	echo "=================================================================="
	printf '%-14s %-4s %-4s  %s (bpl %d)\n' "$FMT" "$PAKV" "$EFFBPP" "$OUT" "$BPL"
	if ! "$HERE/v4l2-capture.sh" -d "$MEDIA" -c "$CAM" -n "$FRAMES" -s "${WIDTH}x${HEIGHT}" \
		-t -o "$OUT" -p /dev/null 2>&1 | grep -E '^(==|error|warning)'; then
		echo "warning: capture for $FMT/$PAKV/$BPPX8 failed" >&2
	fi
	if [ -f "$OUT" ]; then
		SZ=$(wc -c <"$OUT" | tr -d ' ')
		echo "  file $SZ bytes (3 frames would be $((BPL * HEIGHT * FRAMES)))"
		echo "  line $LINE hex: $(hex24 "$OUT" "$BPL")"
		echo "  line $LINE u16: $(u16decode "$OUT" "$BPL")"
		NEXT=$((LINE + 1))
		LINE=$NEXT echo "  line $NEXT hex: $(LINE=$NEXT hex24 "$OUT" "$BPL")"
		LINE=$NEXT echo "  line $NEXT u16: $(LINE=$NEXT u16decode "$OUT" "$BPL")"
	else
		echo "  no output file (capture never started?)"
	fi
	if [ -r /sys/kernel/debug/mt6785-camsv-status ]; then
		echo "  -- camsv status:"
		sed 's/^/  /' /sys/kernel/debug/mt6785-camsv-status
	fi
done

echo "=================================================================="
echo "restored fmt_sel=$SAVED_FMT pak=$SAVED_PAK bytes_per_px_x8=$SAVED_BPP"
echo "decode a candidate with:"
echo "  python3 tools/camera/raw2rgb.py --layout u16 --stride \$BPL \\"
echo "     --bayer bggr <file> $WIDTH $HEIGHT -o /tmp/sweep.png"
