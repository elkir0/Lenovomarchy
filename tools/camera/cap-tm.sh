#!/bin/sh
# Capture a full SENINF test-pattern frame through CAMSV0 IMGO DMA into memory
# (no IOMMU, using larb-bypass.py) and save the raw frame and grayscale PNG.
#
# Ported from begonia camsv/cap1.sh. Requires root and mt6785-camsv-tm loaded.
# Usage:
#   sudo sh cap-tm.sh [-w WIDTH] [-l HEIGHT] [-k LAYOUT] [-o OUT_RAW] [-p OUT_PNG] [-n]
#
# LAYOUT=le10 (default) configures the IMGO DMA the way the complete frame was
# measured on YT-J706F (FMT_SEL 0x102 / PAK 1, line sized for 10 bits:
# W*10/8 bytes; the DMA writes a continuous little-endian 10-bit bit stream
# per line). LAYOUT=p12 keeps the old begonia values (FMT_SEL 0x101 / PAK 2,
# W*12/8-byte lines holding 12-bit containers, truncated to 2/3 of the
# pixels on a 10-bit-sized line) for reference; see T9-RAWTOOLS.md.

set -eu

DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
D=/sys/kernel/debug/camsv-tm

W=${W:-640}
L=${L:-480}
LAYOUT=${LAYOUT:-le10}
OUT=${OUT:-/tmp/tm-frame.raw}
PNG=${PNG:-}
NO_PNG=0
FILL=${FILL:-0xa5}

usage() {
	cat <<EOF
usage: $0 [-w WIDTH] [-l HEIGHT] [-k LAYOUT] [-o OUT_RAW] [-p OUT_PNG] [-n] [-h]
  -w WIDTH    frame width in pixels (default: 640)
  -l HEIGHT   frame height in lines (default: 480)
  -k LAYOUT   byte layout: le10 or p12 (default: le10)
  -o OUT_RAW  output raw file (default: /tmp/tm-frame.raw)
  -p OUT_PNG  output grayscale PNG file (default: <OUT_RAW>.png)
  -n          do not generate a PNG
EOF
}

while getopts "w:l:k:o:p:nh" opt; do
	case "$opt" in
		w) W=$OPTARG ;;
		l) L=$OPTARG ;;
		k) LAYOUT=$OPTARG ;;
		o) OUT=$OPTARG ;;
		p) PNG=$OPTARG ;;
		n) NO_PNG=1 ;;
		h) usage; exit 0 ;;
		*) usage >&2; exit 2 ;;
	esac
done

case "$LAYOUT" in
	le10) BPL=$((W * 10 / 8)); FMT=102; PAK=1 ;;
	p12) BPL=$((W * 12 / 8)); FMT=101; PAK=2 ;;
	*) echo "error: LAYOUT must be le10 or p12 (got $LAYOUT)" >&2; exit 2 ;;
esac

if [ "$NO_PNG" -eq 0 ] && [ -z "$PNG" ]; then
	case "$OUT" in
		*.raw) PNG=${OUT%.raw}.png ;;
		*.bin) PNG=${OUT%.bin}.png ;;
		*) PNG=${OUT}.png ;;
	esac
fi

if [ ! -d "$D" ]; then
	modprobe mt6785-camsv-tm 2>/dev/null || true
fi
if [ ! -d "$D" ]; then
	echo "error: $D not found (is mt6785-camsv-tm loaded and DT node present?)" >&2
	exit 1
fi

w() { printf '%s %s %s\n' "$1" "$2" "$3" > "$D/w"; }
r() { printf '%s %s %s\n' "$1" "$2" "${3:-1}" > "$D/r"; cat "$D/r"; }

FRAME_BYTES=$((BPL * L))
MIN_BUF=$((0x200000))
if [ "$FRAME_BYTES" -gt "$MIN_BUF" ]; then
	BUF_SZ=$FRAME_BYTES
else
	BUF_SZ=$MIN_BUF
fi

echo 1 > "$D/power"
python3 "$DIR/larb-bypass.py"

CUR_SZ=$(awk '{print $4}' "$D/buf")
if [ "$CUR_SZ" = "0x0" ] || [ "$(printf '%d' "$CUR_SZ")" -lt "$BUF_SZ" ]; then
	printf '0x%x\n' "$BUF_SZ" > "$D/buf"
fi
[ -n "$FILL" ] && printf '%s\n' "$FILL" > "$D/fill"
PH=$(awk '{print $2}' "$D/buf")
echo "buffer $PH ($FRAME_BYTES bytes expected)"

# --- SENINF: cam_mux EN, test model on seninf0..4 (TG +0x600, mux +0xd00, ctrl +0x200)
w seninf 410 1f
for n in 0 1 2 3 4; do
	B=$((n * 0x1000))
	w seninf "$(printf '%x' $((B + 0xd04)))" 001f0001
	w seninf "$(printf '%x' $((B + 0xd00)))" 1
	w seninf "$(printf '%x' $((B + 0x220)))" 1
	w seninf "$(printf '%x' $((B + 0x200)))" 1
	w seninf "$(printf '%x' $((B + 0x60c)))" "$(printf '%08x' $(((L << 16) | W)))"
	w seninf "$(printf '%x' $((B + 0x610)))" "${TMCLK:-7}"
	w seninf "$(printf '%x' $((B + 0x618)))" "${TMDUM:-00640064}"
	w seninf "$(printf '%x' $((B + 0x608)))" "${TMCTL:-00300161}"
done

# --- CAMSV0: stop TG/DMA/FBC, then SW_CTL reset (4 -> 0 -> 1 -> wait 3 -> 0)
w camsv 230 0
w camsv 234 0
w camsv 510 40000000
w camsv 110 0
sleep 0.1
w camsv 520 4
w camsv 520 0
w camsv 520 1
sleep 0.05
r camsv 520
w camsv 520 0

# --- CAMSV0 TG window + IMGO DMA (FMT/PAK/BPL follow LAYOUT; env overrides stay)
w camsv 238 "$(printf '%08x' $((W << 16)))"
w camsv 23c "$(printf '%08x' $((L << 16)))"
w camsv 20 "${PH#0x}"
w camsv 30 "$(printf '%x' "${XS:-$((BPL - 1))}")"
w camsv 34 "$(printf '%x' "${YS:-$((L - 1))}")"
w camsv 38 "$(printf '%x' $((BPL | ${STF:-0})))"
w camsv 40 20002
w camsv 44 20002
w camsv 514 "$FMT"
w camsv 54c "$PAK"
w camsv 110 "${FBC:-8000}"

# --- Enable CAMSV0 clocks, modules, interrupts, VF, TG
w camsv 530 8005
w camsv 510 "${MEN:-40000015}"
w camsv 518 ffffffff
w camsv 400 1
w camsv 234 1
w camsv 230 "${SEN:-10001}"
sleep 0.3

# Refill marker before arming FBC (FBC_EN then RCNT_INC) so the next full
# frame is isolated; env FBC overrides the base value for experiments
[ -n "$FILL" ] && printf '%s\n' "$FILL" > "$D/fill"
w camsv 110 "$(printf '%x' "${FBC:-8000}")"
w camsv 110 "$(printf '%x' $((0x${FBC:-8000} | 1)))"
sleep 0.3

echo "== CAMSV0 after start"
r camsv 230 2
r camsv 268 2
r camsv 510 4
r camsv 51c
r camsv 110 2
echo "== SENINF mux0/mux2 size and cam_mux chk"
r seninf d30
r seninf 2d30
r seninf 400 3
sleep 0.3
r camsv 51c
r camsv 51c
head -n 8 "$D/bufdump"

python3 - "$D/frame" "$FRAME_BYTES" "$OUT" "${FILL:-}" <<'PY'
import sys

src, nbytes, dst, fill = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4]
with open(src, 'rb') as f:
    data = f.read(nbytes)
with open(dst, 'wb') as f:
    f.write(data)
if fill:
    fv = int(fill, 0) & 0xFF
    changed = [i for i, b in enumerate(data) if b != fv]
    span = (max(changed) + 1) if changed else 0
    print(f'saved {dst}: {len(data)} bytes, non-0x{fv:02x} count={len(changed)}, last+1={span}')
else:
    print(f'saved {dst}: {len(data)} bytes')
PY

if [ "$NO_PNG" -eq 0 ]; then
	python3 "$DIR/raw2png.py" "$OUT" "$W" "$L" --layout "$LAYOUT" "$BPL" "$PNG"
fi
