#!/usr/bin/env bash
# Flash a Linux test image to slot A of the YT-J706F, wait for the boot
# outcome, and collect logs into a timestamped run directory.
#
# Usage:
#   tools/linux-test.sh [--timeout SECONDS] [--no-flash] <boot.img> <dtbo.img>
#
# Outcomes / exit codes:
#   0  LINUX_UP   Linux answered SSH at 192.168.77.1
#   3  FELL_BACK  Bootloader fell back to Android on slot _b (pstore saved)
#   4  TIMEOUT    Neither outcome observed before --timeout (default 420 s)
#   1  Error      Invalid arguments, missing image, or flash failure

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TIMEOUT=420
NO_FLASH=0
POLL_INTERVAL="${YT11_POLL_INTERVAL:-2}"
SSH_TARGET="${YT11_SSH_TARGET:-root@192.168.77.1}"
SSH_OPTS=(
    -n
    -o BatchMode=yes
    -o StrictHostKeyChecking=no
    -o UserKnownHostsFile=/dev/null
    -o ConnectTimeout=3
    -o ServerAliveInterval=5
    -o ServerAliveCountMax=3
)

usage() {
    sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'
}

die() {
    echo "linux-test.sh: $*" >&2
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --timeout)
            [[ $# -ge 2 ]] || die "--timeout requires a value"
            TIMEOUT="$2"
            shift 2
            ;;
        --timeout=*)
            TIMEOUT="${1#*=}"
            shift
            ;;
        --no-flash)
            NO_FLASH=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        --)
            shift
            break
            ;;
        -*)
            die "unknown option: $1"
            ;;
        *)
            break
            ;;
    esac
done

[[ $# -eq 2 ]] || { usage >&2; exit 1; }
BOOT="$1"
DTBO="$2"

[[ "$TIMEOUT" =~ ^[0-9]+$ ]] || die "--timeout must be a non-negative integer: $TIMEOUT"
[[ "$POLL_INTERVAL" =~ ^[0-9]+$ ]] && (( POLL_INTERVAL > 0 )) || die "invalid poll interval: $POLL_INTERVAL"
[[ -f "$BOOT" ]] || die "missing boot image: $BOOT"
[[ -f "$DTBO" ]] || die "missing dtbo image: $DTBO"

for cmd in ssh adb python3; do
    command -v "$cmd" >/dev/null 2>&1 || die "required command not found on PATH: $cmd"
done

abs_file() {
    local dir base
    dir=$(cd "$(dirname "$1")" && pwd -P)
    base=$(basename "$1")
    printf '%s/%s\n' "$dir" "$base"
}

BOOT=$(abs_file "$BOOT")
DTBO=$(abs_file "$DTBO")

RUNS_BASE="${YT11_RUNS_DIR:-$REPO/private/runs}"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
RUN_DIR="$RUNS_BASE/$STAMP"
if [[ -e "$RUN_DIR" ]]; then
    suffix=1
    while [[ -e "${RUN_DIR}-${suffix}" ]]; do
        suffix=$((suffix + 1))
    done
    RUN_DIR="${RUN_DIR}-${suffix}"
fi
mkdir -p "$RUN_DIR"
RUN_DIR=$(cd "$RUN_DIR" && pwd -P)
RUN_LOG="$RUN_DIR/run.log"
: > "$RUN_LOG"

# Load yt / ytadb / redact without failing if the tablet is not yet in adb.
YT_T=""
# shellcheck source=tools/yt.sh
. "$REPO/tools/yt.sh" 2>/dev/null || true

refresh_yt() {
    YT_T=""
    # shellcheck source=tools/yt.sh
    . "$REPO/tools/yt.sh" 2>/dev/null || true
}

# Filter sensitive lines (including Kernel command line) and ignore grep's
# exit code 1 when zero lines survive under pipefail.
safe_redact() {
    LC_ALL=C tr -d '\0\r' | LC_ALL=C redact || true
}

log() {
    printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | safe_redact | tee -a "$RUN_LOG"
}

sha256_file() {
    if command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$1" | awk '{print $1}'
    else
        sha256sum "$1" | awk '{print $1}'
    fi
}

BOOT_SHA=$(sha256_file "$BOOT")
DTBO_SHA=$(sha256_file "$DTBO")
log "run directory: $RUN_DIR"
log "boot image: $BOOT (sha256: $BOOT_SHA)"
log "dtbo image: $DTBO (sha256: $DTBO_SHA)"

if [[ "$NO_FLASH" -eq 0 ]]; then
    FLASH_CMD="${YT11_FLASH_CMD:-$REPO/tools/flash-slot.sh}"
    log "flashing slot a via $FLASH_CMD"
    set +e
    flash_out=$("$FLASH_CMD" a "$BOOT" "$DTBO" 2>&1)
    flash_rc=$?
    set -e
    if [[ -n "$flash_out" ]]; then
        printf '%s\n' "$flash_out" | safe_redact | tee -a "$RUN_LOG"
    fi
    if [[ "$flash_rc" -ne 0 ]]; then
        log "error: flash failed with exit code $flash_rc"
        exit 1
    fi
else
    log "skipping flash (--no-flash)"
fi

START_TS=$(date +%s)
DEADLINE=$((START_TS + TIMEOUT))
VERDICT=""

log "polling for outcome (timeout ${TIMEOUT}s, interval ${POLL_INTERVAL}s)"
while true; do
    if ssh "${SSH_OPTS[@]}" "$SSH_TARGET" true >/dev/null 2>&1; then
        VERDICT="LINUX_UP"
        break
    fi

    refresh_yt
    if [[ -n "${YT_T:-}" ]]; then
        slot=$(yt getprop ro.boot.slot_suffix 2>/dev/null | tr -d '\r\n ') || slot=""
        if [[ "$slot" = "_b" ]]; then
            VERDICT="FELL_BACK"
            break
        fi
    fi

    now=$(date +%s)
    if (( now >= DEADLINE )); then
        VERDICT="TIMEOUT"
        break
    fi
    sleep "$POLL_INTERVAL"
done

ELAPSED=$(( $(date +%s) - START_TS ))
log "outcome: $VERDICT after ${ELAPSED}s"

collect_ssh_file() {
    local remote_cmd="$1"
    local out_file="$2"
    ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "$remote_cmd" 2>/dev/null | safe_redact > "$out_file" || true
}

decompress_zlib_stream() {
    python3 -c '
import sys, zlib
data = sys.stdin.buffer.read()
if not data:
    sys.exit(0)
try:
    out = zlib.decompress(data)
except zlib.error:
    decomp = zlib.decompressobj()
    out = decomp.decompress(data) + decomp.flush()
sys.stdout.buffer.write(out)
'
}

if [[ "$VERDICT" = "LINUX_UP" ]]; then
    log "collecting Linux diagnostics over SSH"
    collect_ssh_file "dmesg" "$RUN_DIR/dmesg.log"
    collect_ssh_file "uname -a" "$RUN_DIR/uname.txt"
    collect_ssh_file "cat /proc/device-tree/model" "$RUN_DIR/model.txt"
    collect_ssh_file "ls /sys/class/udc /sys/bus/i2c/devices" "$RUN_DIR/devices.txt"
    if ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "test -e /sys/kernel/debug/devices_deferred" >/dev/null 2>&1; then
        collect_ssh_file "cat /sys/kernel/debug/devices_deferred" "$RUN_DIR/devices_deferred.txt"
    fi
    collect_ssh_file "lsmod" "$RUN_DIR/lsmod.txt"
    collect_ssh_file "ip addr" "$RUN_DIR/ip-addr.txt"
elif [[ "$VERDICT" = "FELL_BACK" ]]; then
    log "collecting pstore logs from Android fallback"
    set +e
    root_out=$(ytadb root 2>&1)
    set -e
    if [[ -n "$root_out" ]]; then
        printf '%s\n' "$root_out" | safe_redact | tee -a "$RUN_LOG"
    fi

    boot_wait_deadline=$(( $(date +%s) + 120 ))
    while true; do
        refresh_yt
        if [[ -n "${YT_T:-}" ]]; then
            uid=$(yt id -u 2>/dev/null | tr -d '\r\n ') || uid=""
            booted=$(yt getprop sys.boot_completed 2>/dev/null | tr -d '\r\n ') || booted=""
            if [[ "$uid" = "0" && "$booted" = "1" ]]; then
                break
            fi
        fi
        if (( $(date +%s) >= boot_wait_deadline )); then
            log "warning: timed out waiting for root adbd and boot completion"
            break
        fi
        sleep 1
    done

    bootreason=$(yt getprop ro.boot.bootreason 2>/dev/null | safe_redact) || bootreason=""
    printf '%s\n' "$bootreason" > "$RUN_DIR/bootreason.txt"
    log "bootreason: ${bootreason:-<empty>}"

    mkdir -p "$RUN_DIR/pstore"
    pstore_list=$(yt 'ls -1 /sys/fs/pstore 2>/dev/null' | tr -d '\r' || true)
    if [[ -n "$pstore_list" ]]; then
        while IFS= read -r entry; do
            [[ -n "$entry" ]] || continue
            name="${entry##*/}"
            [[ "$name" = "." || "$name" = ".." ]] && continue
            if [[ "$name" == *.enc.z ]]; then
                out_name="${name%.enc.z}"
                [[ -e "$RUN_DIR/pstore/$out_name" ]] && out_name="${name}.txt"
                set +e
                ytadb exec-out "cat '/sys/fs/pstore/$name'" 2>/dev/null \
                    | decompress_zlib_stream 2>/dev/null \
                    | safe_redact > "$RUN_DIR/pstore/$out_name"
                set -e
            else
                out_name="$name"
                set +e
                ytadb exec-out "cat '/sys/fs/pstore/$name'" 2>/dev/null \
                    | safe_redact > "$RUN_DIR/pstore/$out_name"
                set -e
            fi
            line_count=$(wc -l < "$RUN_DIR/pstore/$out_name" | tr -d ' ')
            log "saved pstore/$out_name (${line_count} lines)"
        done <<< "$pstore_list"
    else
        log "no files found in /sys/fs/pstore"
    fi
fi

# Collect console & error lines for summary.
console_files=()
scan_files=()
if [[ "$VERDICT" = "LINUX_UP" && -f "$RUN_DIR/dmesg.log" ]]; then
    console_files=("$RUN_DIR/dmesg.log")
    scan_files=("$RUN_DIR/dmesg.log")
elif [[ "$VERDICT" = "FELL_BACK" && -d "$RUN_DIR/pstore" ]]; then
    for f in "$RUN_DIR/pstore"/console-ramoops*; do
        [[ -f "$f" ]] && console_files+=("$f")
    done
    if [[ ${#console_files[@]} -eq 0 ]]; then
        for f in "$RUN_DIR/pstore"/dmesg-ramoops*; do
            [[ -f "$f" ]] && console_files+=("$f")
        done
    fi
    for f in "$RUN_DIR/pstore"/*; do
        [[ -f "$f" ]] && scan_files+=("$f")
    done
fi

{
    echo "=== Summary ==="
    echo "Verdict:  $VERDICT"
    echo "Elapsed:  ${ELAPSED}s"
    echo "Run dir:  $RUN_DIR"
    if [[ ${#console_files[@]} -gt 0 ]]; then
        echo "--- Last 30 lines of Linux console ---"
        cat "${console_files[@]}" | safe_redact | tail -n 30
    else
        echo "--- Last 30 lines of Linux console ---"
        echo "(none)"
    fi
    echo "--- Matched panic/error lines ---"
    if [[ ${#scan_files[@]} -gt 0 ]]; then
        matched=$(LC_ALL=C grep -hE 'Kernel panic|Oops|BUG:|Unable to handle|-110|failed with error' "${scan_files[@]}" 2>/dev/null | safe_redact || true)
        if [[ -n "$matched" ]]; then
            printf '%s\n' "$matched"
        else
            echo "(none)"
        fi
    else
        echo "(none)"
    fi
} | tee -a "$RUN_LOG"

case "$VERDICT" in
    LINUX_UP)  exit 0 ;;
    FELL_BACK) exit 3 ;;
    TIMEOUT)   exit 4 ;;
    *)         exit 1 ;;
esac
