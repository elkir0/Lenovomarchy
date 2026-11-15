#!/usr/bin/env bash
# Smoke-test the initramfs under QEMU (TCG) inside an alpine:3.22
# arm64 container: boots out/initramfs/initramfs.cpio.gz with the
# Alpine linux-virt kernel (console=ttyAMA0 yt11.nowdt=1) and passes
# when "yt11-init: ready" reaches the serial console within 180 s.
# It also verifies that no line starting with "yt11-init:" leaks the
# kernel command line (it contains the device serial number; only the
# kernel itself prints that line).
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ROOT_DIR=$(cd "$SCRIPT_DIR/.." && pwd)
ARCHIVE="$ROOT_DIR/out/initramfs/initramfs.cpio.gz"
export YT11_TIMEOUT=180

if [ ! -f "$ARCHIVE" ]; then
    printf 'test-qemu.sh: %s not found; run build.sh first\n' "$ARCHIVE" >&2
    exit 1
fi

docker run --rm --platform linux/arm64 \
    -e YT11_TIMEOUT \
    -v "$ARCHIVE:/initramfs.cpio.gz:ro" \
    alpine:3.22 sh -euc '
        apk add -q --no-cache qemu-system-aarch64 linux-virt >/dev/null
        mkdir -p /tmp/q && cd /tmp/q

        qemu-system-aarch64 \
            -M virt -cpu cortex-a57 -m 512 \
            -display none -monitor none -serial stdio -no-reboot \
            -kernel /boot/vmlinuz-virt \
            -initrd /initramfs.cpio.gz \
            -append "console=ttyAMA0 yt11.nowdt=1" \
            >console.log 2>&1 &
        QPID=$!

        deadline=$(( $(date +%s) + YT11_TIMEOUT ))
        found=0
        while [ "$(date +%s)" -lt "$deadline" ]; do
            if grep -q "yt11-init: ready" console.log 2>/dev/null; then
                found=1
                break
            fi
            kill -0 "$QPID" 2>/dev/null || break
            sleep 2
        done
        kill "$QPID" 2>/dev/null || true
        sleep 1
        kill -9 "$QPID" 2>/dev/null || true
        wait "$QPID" 2>/dev/null || true

        if [ "$found" != 1 ]; then
            echo "FAIL: no \"yt11-init: ready\" on the serial console; last lines:"
            tail -n 40 console.log
            exit 1
        fi
        if grep "^yt11-init:" console.log | grep -q "Kernel command line"; then
            echo "FAIL: init leaked the kernel command line:"
            grep "^yt11-init:" console.log | grep "Kernel command line"
            exit 1
        fi
        echo "--- init log lines ---"
        grep "yt11-init:" console.log | sed "s/^/  /" | tail -n 20
        echo "PASS"
    '
