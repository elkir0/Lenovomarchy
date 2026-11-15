#!/usr/bin/env bash
# Offline test suite for initramfs/files/usr/sbin/yt11-bootctl.
# Runs yt11-bootctl under busybox sh inside alpine:3.22 and verifies the
# bootloader_control bytes and CRC32 independently with host python3.

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)
TOOL="$REPO_ROOT/initramfs/files/usr/sbin/yt11-bootctl"
STOCK_HEX="$SCRIPT_DIR/bootctrl-stock.hex"

[ -x "$TOOL" ] || { printf 'FAIL: tool not executable: %s\n' "$TOOL" >&2; exit 1; }
[ -f "$STOCK_HEX" ] || { printf 'FAIL: missing stock hex: %s\n' "$STOCK_HEX" >&2; exit 1; }

TMP_DIR=$(mktemp -d "${TMPDIR:-/tmp}/yt11-bootctl-test.XXXXXX")
trap 'rm -rf "$TMP_DIR"' EXIT

pass_count=0
fail_count=0

pass() {
    pass_count=$((pass_count + 1))
    printf 'PASS: %s\n' "$1"
}

fail() {
    fail_count=$((fail_count + 1))
    printf 'FAIL: %s\n' "$1" >&2
}

assert_contains() {
    local haystack=$1 needle=$2 label=$3
    if printf '%s\n' "$haystack" | grep -Fq "$needle"; then
        pass "$label"
    else
        fail "$label (expected '$needle' in output)"
        printf '--- output ---\n%s\n--------------\n' "$haystack" >&2
    fi
}

assert_rc() {
    local actual=$1 expected=$2 label=$3
    if [ "$actual" -eq "$expected" ]; then
        pass "$label"
    else
        fail "$label (expected rc=$expected, got rc=$actual)"
    fi
}

run_in_alpine() {
    docker run --rm \
        -v "$TOOL:/usr/sbin/yt11-bootctl:ro" \
        -v "$TMP_DIR:/work" \
        alpine:3.22 \
        busybox sh /usr/sbin/yt11-bootctl "$@"
}

# Build a 4096-byte fake misc image with non-zero sentinel bytes outside 2048-2079
# and the stock 32-byte bootloader_control block at offset 2048.
MISC="$TMP_DIR/misc.bin"
ORIG="$TMP_DIR/misc.orig.bin"
python3 - "$STOCK_HEX" "$MISC" "$ORIG" <<'PY'
import sys

stock = bytes.fromhex(open(sys.argv[1], "r", encoding="ascii").read().strip())
assert len(stock) == 32, len(stock)

prefix = bytes((i * 37 + 11) & 0xFF for i in range(2048))
suffix = bytes((i * 53 + 29) & 0xFF for i in range(4096 - 2080))
img = prefix + stock + suffix
assert len(img) == 4096

for path in (sys.argv[2], sys.argv[3]):
    with open(path, "wb") as f:
        f.write(img)
PY

# 1. status on stock block
set +e
out=$(run_in_alpine --misc /work/misc.bin status 2>&1)
rc=$?
set -e
assert_rc "$rc" 0 "stock status exit code 0"
assert_contains "$out" "magic: 0x42414342 (ok)" "stock magic ok"
assert_contains "$out" "version: 1" "stock version 1"
assert_contains "$out" "nb_slot: 2" "stock nb_slot 2"
assert_contains "$out" "slot a: priority=14 tries=1 successful=1" "stock slot a decoded"
assert_contains "$out" "slot b: priority=15 tries=1 successful=1" "stock slot b decoded"
assert_contains "$out" "crc32: 0xf92515db (ok)" "stock crc32 ok"

# 2. set-active a -> status + host zlib.crc32 verification
set +e
out=$(run_in_alpine --misc /work/misc.bin set-active a 2>&1)
rc=$?
set -e
assert_rc "$rc" 0 "set-active a exit code 0"

set +e
out=$(run_in_alpine --misc /work/misc.bin status 2>&1)
rc=$?
set -e
assert_rc "$rc" 0 "status after set-active a exit code 0"
assert_contains "$out" "slot a: priority=15 tries=7 successful=0" "set-active a slot a 15/7/0"
assert_contains "$out" "slot b: priority=14 tries=1 successful=1" "set-active a lowered slot b to 14/1/1"
assert_contains "$out" "(ok)" "status after set-active a crc ok"

if python3 - "$MISC" "$ORIG" <<'PY'
import struct, sys, zlib

cur = open(sys.argv[1], "rb").read()
orig = open(sys.argv[2], "rb").read()
assert len(cur) == 4096
assert cur[:2048] == orig[:2048], "bytes before 2048 changed"
assert cur[2080:] == orig[2080:], "bytes after 2079 changed"
blk = cur[2048:2080]
assert blk[12] == 0x7F, f"expected slot a 0x7f, got {blk[12]:#x}"
assert blk[14] == 0x9E, f"expected slot b 0x9e, got {blk[14]:#x}"
stored = struct.unpack("<I", blk[28:32])[0]
calc = zlib.crc32(blk[:28]) & 0xFFFFFFFF
assert stored == calc, f"CRC mismatch: stored={stored:#010x} calc={calc:#010x}"
PY
then
    pass "host python3 zlib.crc32 and sentinel bytes after set-active a"
else
    fail "host python3 verification after set-active a"
fi

# 3. mark-successful a -> sets bit 7, preserves tries=7, valid CRC
set +e
out=$(run_in_alpine --misc /work/misc.bin mark-successful a 2>&1)
rc=$?
set -e
assert_rc "$rc" 0 "mark-successful a exit code 0"

set +e
out=$(run_in_alpine --misc /work/misc.bin status 2>&1)
rc=$?
set -e
assert_rc "$rc" 0 "status after mark-successful a exit code 0"
assert_contains "$out" "slot a: priority=15 tries=7 successful=1" "mark-successful a slot a 15/7/1"
assert_contains "$out" "slot b: priority=14 tries=1 successful=1" "mark-successful a kept slot b 14/1/1"

if python3 - "$MISC" "$ORIG" <<'PY'
import struct, sys, zlib

cur = open(sys.argv[1], "rb").read()
orig = open(sys.argv[2], "rb").read()
assert cur[:2048] == orig[:2048], "bytes before 2048 changed"
assert cur[2080:] == orig[2080:], "bytes after 2079 changed"
blk = cur[2048:2080]
assert blk[12] == 0xFF, f"expected slot a 0xff, got {blk[12]:#x}"
assert blk[14] == 0x9E, f"expected slot b 0x9e, got {blk[14]:#x}"
stored = struct.unpack("<I", blk[28:32])[0]
calc = zlib.crc32(blk[:28]) & 0xFFFFFFFF
assert stored == calc, f"CRC mismatch: stored={stored:#010x} calc={calc:#010x}"
PY
then
    pass "host python3 zlib.crc32 and outside bytes unchanged after mark-successful a"
else
    fail "host python3 verification after mark-successful a"
fi

# 4. Corrupted magic is refused on write and status exits 2
BAD_MAGIC="$TMP_DIR/misc-badmagic.bin"
BAD_MAGIC_ORIG="$TMP_DIR/misc-badmagic.orig.bin"
python3 - "$ORIG" "$BAD_MAGIC" "$BAD_MAGIC_ORIG" <<'PY'
import sys

data = bytearray(open(sys.argv[1], "rb").read())
data[2052] ^= 0x01
for path in (sys.argv[2], sys.argv[3]):
    with open(path, "wb") as f:
        f.write(data)
PY

set +e
out=$(run_in_alpine --misc /work/misc-badmagic.bin status 2>&1)
rc=$?
set -e
assert_rc "$rc" 2 "bad magic status exit code 2"
assert_contains "$out" "BAD" "bad magic status prints BAD"

set +e
out=$(run_in_alpine --misc /work/misc-badmagic.bin set-active a 2>&1)
rc=$?
set -e
assert_rc "$rc" 2 "bad magic set-active refused with exit code 2"

set +e
out=$(run_in_alpine --misc /work/misc-badmagic.bin mark-successful a 2>&1)
rc=$?
set -e
assert_rc "$rc" 2 "bad magic mark-successful refused with exit code 2"

if cmp -s "$BAD_MAGIC" "$BAD_MAGIC_ORIG"; then
    pass "bad magic image left unmodified"
else
    fail "bad magic image was modified"
fi

# 5. CRC mismatch prints mismatch and exits 2
BAD_CRC="$TMP_DIR/misc-badcrc.bin"
BAD_CRC_ORIG="$TMP_DIR/misc-badcrc.orig.bin"
python3 - "$ORIG" "$BAD_CRC" "$BAD_CRC_ORIG" <<'PY'
import sys

data = bytearray(open(sys.argv[1], "rb").read())
data[2076] ^= 0xFF
for path in (sys.argv[2], sys.argv[3]):
    with open(path, "wb") as f:
        f.write(data)
PY

set +e
out=$(run_in_alpine --misc /work/misc-badcrc.bin status 2>&1)
rc=$?
set -e
assert_rc "$rc" 2 "bad crc status exit code 2"
assert_contains "$out" "MISMATCH" "bad crc status prints MISMATCH"

set +e
out=$(run_in_alpine --misc /work/misc-badcrc.bin set-active a 2>&1)
rc=$?
set -e
assert_rc "$rc" 2 "bad crc set-active refused with exit code 2"

if cmp -s "$BAD_CRC" "$BAD_CRC_ORIG"; then
    pass "bad crc image left unmodified"
else
    fail "bad crc image was modified"
fi

# 6. Usage error exits 1; write failure exits 3
set +e
out=$(run_in_alpine --misc /work/misc.bin set-active c 2>&1)
rc=$?
set -e
assert_rc "$rc" 1 "invalid slot exits 1"

RO_MISC="$TMP_DIR/misc-ro.bin"
cp "$ORIG" "$RO_MISC"
set +e
out=$(docker run --rm \
    -v "$TOOL:/usr/sbin/yt11-bootctl:ro" \
    -v "$RO_MISC:/work/misc-ro.bin:ro" \
    alpine:3.22 \
    busybox sh /usr/sbin/yt11-bootctl --misc /work/misc-ro.bin set-active a 2>&1)
rc=$?
set -e
assert_rc "$rc" 3 "read-only misc write failure exits 3"

printf '\nSummary: %d passed, %d failed\n' "$pass_count" "$fail_count"
[ "$fail_count" -eq 0 ]
