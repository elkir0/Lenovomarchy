#!/usr/bin/env bash
# Offline test suite for tools/linux-test.sh using stub adb, fastboot, and ssh.
# Prints three PASS lines and exits 0 on success.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STUBS="$REPO/tests/linux-test/stubs"
SCRIPT="$REPO/tools/linux-test.sh"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

BOOT="$TMP/boot.img"
DTBO="$TMP/dtbo.img"
printf 'fake-boot-image-content\n' > "$BOOT"
printf 'fake-dtbo-image-content\n' > "$DTBO"

BOOT_SHA=$(shasum -a 256 "$BOOT" | awk '{print $1}')
DTBO_SHA=$(shasum -a 256 "$DTBO" | awk '{print $1}')

fail() {
    echo "FAIL: $*" >&2
    exit 1
}

assert_file() {
    [[ -f "$1" ]] || fail "expected file missing: $1"
}

assert_contains() {
    local file="$1" pattern="$2"
    LC_ALL=C grep -qE -- "$pattern" "$file" || fail "expected '$pattern' in $file"
}

assert_not_in_tree() {
    local dir="$1" pattern="$2"
    if LC_ALL=C grep -rnE -- "$pattern" "$dir" >/dev/null 2>&1; then
        fail "forbidden pattern '$pattern' found in $dir"
    fi
}

single_run_dir() {
    local base="$1" count=0 found=""
    for d in "$base"/*; do
        [[ -d "$d" ]] || continue
        count=$((count + 1))
        found="$d"
    done
    [[ "$count" -eq 1 ]] || fail "expected 1 run dir in $base, got $count"
    printf '%s\n' "$found"
}

# --- Scenario 1: LINUX_UP (full flash-slot.sh flow with stubs) ---
run_linux_up() {
    local base="$TMP/runs-up" state="$TMP/state-up" out="$TMP/out-up.txt" rc
    mkdir -p "$base" "$state"
    printf 'adb' > "$state/mode"
    printf '42' > "$state/tid"
    printf '0' > "$state/is_root"

    set +e
    PATH="$STUBS:$PATH" \
    YT11_RUNS_DIR="$base" \
    YT11_POLL_INTERVAL=1 \
    STUB_STATE_DIR="$state" \
    STUB_ADB_ON_BOOT=0 \
    STUB_SSH_REACHABLE=1 \
    STUB_SSH_READY_AFTER=2 \
    STUB_DEVICES_DEFERRED="11270000.mmc" \
        bash "$SCRIPT" --timeout 10 "$BOOT" "$DTBO" > "$out" 2>&1
    rc=$?
    set -e

    [[ "$rc" -eq 0 ]] || { cat "$out" >&2; fail "LINUX_UP exited $rc, expected 0"; }
    local rdir
    rdir=$(single_run_dir "$base")

    assert_file "$rdir/run.log"
    assert_file "$rdir/dmesg.log"
    assert_file "$rdir/uname.txt"
    assert_file "$rdir/model.txt"
    assert_file "$rdir/devices.txt"
    assert_file "$rdir/devices_deferred.txt"
    assert_file "$rdir/lsmod.txt"
    assert_file "$rdir/ip-addr.txt"

    assert_contains "$out" "Verdict:[[:space:]]+LINUX_UP"
    assert_contains "$rdir/run.log" "$BOOT_SHA"
    assert_contains "$rdir/run.log" "$DTBO_SHA"
    assert_contains "$rdir/dmesg.log" "gadget configured"
    assert_contains "$rdir/uname.txt" "6\.16\.4-mt6785"
    assert_contains "$rdir/model.txt" "Lenovo Yoga Tab 11"
    assert_contains "$rdir/devices.txt" "11201000\.usb"
    assert_contains "$rdir/devices_deferred.txt" "11270000\.mmc"
    assert_contains "$rdir/lsmod.txt" "usb_f_ecm"
    assert_contains "$rdir/ip-addr.txt" "<MAC>"

    assert_contains "$state/fastboot.calls" "flash boot_a"
    assert_contains "$state/fastboot.calls" "flash dtbo_a"
    assert_contains "$state/fastboot.calls" "--set-active=a"
    assert_contains "$state/fastboot.calls" "^reboot$"

    assert_not_in_tree "$rdir" "Kernel command line|FAKE_LINUX_SERIAL_999|YTJ706F_FAKE_SERIAL|PHONE_FAKE_SERIAL|02:aa:bb:cc:dd:ee"
    if LC_ALL=C grep -qE "Kernel command line|FAKE_LINUX_SERIAL_999|YTJ706F_FAKE_SERIAL|PHONE_FAKE_SERIAL" "$out"; then
        fail "forbidden identifier leaked to stdout in LINUX_UP"
    fi

    echo "PASS: LINUX_UP (exit 0, diagnostics collected, identifiers redacted)"
}

# --- Scenario 2: FELL_BACK (pstore + .enc.z decompression + Kernel command line redaction) ---
run_fell_back() {
    local base="$TMP/runs-fb" state="$TMP/state-fb" pstore="$TMP/pstore-fb" out="$TMP/out-fb.txt" rc
    mkdir -p "$base" "$state" "$pstore"
    printf 'booted' > "$state/mode"
    printf '42' > "$state/tid"
    printf '0' > "$state/is_root"

    cat > "$pstore/console-ramoops-0" <<'EOF'
[    0.000000] Booting Linux on physical CPU 0x0000000000
[    0.000000] Kernel command line: bootopt=64S3,32N2,64N2 androidboot.serialno=SECRET_SERIAL_999
[    1.100000] mmc0: initializing host
[    2.250000] Kernel panic - not syncing: VFS: Unable to mount root fs
EOF

    python3 -c '
import sys, zlib
payload = (
    b"[    0.000000] dmesg ramoops start\n"
    b"[    0.000000] Kernel command line: bootopt=64S3 androidboot.serialno=SECRET_SERIAL_999\n"
    b"[    1.500000] i2c-mt65xx 11007000.i2c: transfer failed with error -110\n"
)
open(sys.argv[1], "wb").write(zlib.compress(payload))
' "$pstore/dmesg-ramoops-0.enc.z"

    set +e
    PATH="$STUBS:$PATH" \
    YT11_RUNS_DIR="$base" \
    YT11_POLL_INTERVAL=1 \
    STUB_STATE_DIR="$state" \
    STUB_ADB_ON_BOOT=1 \
    STUB_SLOT_SUFFIX="_b" \
    STUB_BOOT_COMPLETED=1 \
    STUB_BOOTREASON="kernel_panic" \
    STUB_PSTORE_DIR="$pstore" \
    STUB_SSH_REACHABLE=0 \
        bash "$SCRIPT" --no-flash --timeout 10 "$BOOT" "$DTBO" > "$out" 2>&1
    rc=$?
    set -e

    [[ "$rc" -eq 3 ]] || { cat "$out" >&2; fail "FELL_BACK exited $rc, expected 3"; }
    local rdir
    rdir=$(single_run_dir "$base")

    assert_file "$rdir/run.log"
    assert_file "$rdir/bootreason.txt"
    assert_file "$rdir/pstore/console-ramoops-0"
    assert_file "$rdir/pstore/dmesg-ramoops-0"

    assert_contains "$out" "Verdict:[[:space:]]+FELL_BACK"
    assert_contains "$out" "Kernel panic - not syncing"
    assert_contains "$out" "failed with error -110"
    assert_contains "$rdir/bootreason.txt" "kernel_panic"
    assert_contains "$rdir/pstore/console-ramoops-0" "Booting Linux"
    assert_contains "$rdir/pstore/dmesg-ramoops-0" "transfer failed with error -110"
    assert_contains "$state/adb.calls" "^root$"

    assert_not_in_tree "$rdir" "Kernel command line|SECRET_SERIAL_999|YTJ706F_FAKE_SERIAL|PHONE_FAKE_SERIAL"
    if LC_ALL=C grep -qE "Kernel command line|SECRET_SERIAL_999|YTJ706F_FAKE_SERIAL|PHONE_FAKE_SERIAL" "$out"; then
        fail "forbidden identifier leaked to stdout in FELL_BACK"
    fi

    echo "PASS: FELL_BACK (exit 3, pstore + .enc.z saved, Kernel command line redacted)"
}

# --- Scenario 3: TIMEOUT ---
run_timeout() {
    local base="$TMP/runs-to" state="$TMP/state-to" out="$TMP/out-to.txt" rc
    mkdir -p "$base" "$state"
    printf 'absent' > "$state/mode"

    set +e
    PATH="$STUBS:$PATH" \
    YT11_RUNS_DIR="$base" \
    YT11_POLL_INTERVAL=1 \
    STUB_STATE_DIR="$state" \
    STUB_ADB_TABLET_PRESENT=0 \
    STUB_SSH_REACHABLE=0 \
        bash "$SCRIPT" --no-flash --timeout 2 "$BOOT" "$DTBO" > "$out" 2>&1
    rc=$?
    set -e

    [[ "$rc" -eq 4 ]] || { cat "$out" >&2; fail "TIMEOUT exited $rc, expected 4"; }
    local rdir
    rdir=$(single_run_dir "$base")

    assert_file "$rdir/run.log"
    assert_contains "$out" "Verdict:[[:space:]]+TIMEOUT"
    assert_contains "$rdir/run.log" "TIMEOUT"

    echo "PASS: TIMEOUT (exit 4, run.log recorded)"
}

run_linux_up
run_fell_back
run_timeout
