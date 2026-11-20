#!/usr/bin/env bash
# Offline test suite for tools/install.sh.
# Exercises argument validation and --dry-run command ordering without a tablet.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TOOL="$REPO/tools/install.sh"

FAILURES=0
pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1"; FAILURES=$((FAILURES + 1)); }

TMPDIR_TEST="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_TEST"' EXIT

KEY="$TMPDIR_TEST/test.pub"
BOOT="$TMPDIR_TEST/boot.img"
DTBO="$TMPDIR_TEST/dtbo.img"
SUPER="$TMPDIR_TEST/super.img"
ROOTFS_IMG="$TMPDIR_TEST/rootfs.img"
ROOTFS_XZ="$TMPDIR_TEST/rootfs.img.xz"
ROOTFS_ZST="$TMPDIR_TEST/rootfs.img.zst"

printf 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITestKeyDummy test@host\n' > "$KEY"
printf 'boot' > "$BOOT"
printf 'dtbo' > "$DTBO"
printf 'super' > "$SUPER"
printf 'raw-rootfs' > "$ROOTFS_IMG"
xz -c "$ROOTFS_IMG" > "$ROOTFS_XZ"
zstd -q -c "$ROOTFS_IMG" > "$ROOTFS_ZST"

# Argument error tests
if out="$("$TOOL" "$ROOTFS_IMG" "$BOOT" "$DTBO" 2>&1)"; then
    fail "missing --key should fail"
elif [[ "$out" == *"--key"* ]]; then
    pass "missing --key rejected with explanation"
else
    fail "missing --key output unexpected: $out"
fi

if out="$("$TOOL" --key "$KEY" --slot c "$ROOTFS_IMG" "$BOOT" "$DTBO" 2>&1)"; then
    fail "invalid --slot should fail"
else
    pass "invalid --slot rejected"
fi

if out="$("$TOOL" --key "$KEY" "$ROOTFS_IMG" "$BOOT" 2>&1)"; then
    fail "missing positional arg should fail"
else
    pass "missing positional arg rejected"
fi

if out="$("$TOOL" --key "$KEY" --dry-run "$TMPDIR_TEST/missing.img" "$BOOT" "$DTBO" 2>&1)"; then
    fail "missing input file should fail"
else
    pass "missing input file rejected"
fi

BAD_EXT="$TMPDIR_TEST/rootfs.simg"
printf 'simg' > "$BAD_EXT"
if out="$("$TOOL" --key "$KEY" "$BAD_EXT" "$BOOT" "$DTBO" 2>&1)"; then
    fail "invalid rootfs extension should fail"
else
    pass "invalid rootfs extension rejected"
fi

# Test dry-run 1: raw .img without --firmware (default slot a)
dry1="$("$TOOL" --key "$KEY" --dry-run "$ROOTFS_IMG" "$BOOT" "$DTBO" 2>&1)" && rc=0 || rc=$?
if [[ "$rc" -ne 0 ]]; then
    fail "dry-run raw .img exited $rc: $dry1"
else
    dry_lines="$(printf '%s\n' "$dry1" | grep '^DRY: ' || true)"
    expected_lines="$(cat <<EOF
DRY: $REPO/tools/image-set-key.sh $ROOTFS_IMG $KEY
DRY: $REPO/tools/flash-rootfs.sh $ROOTFS_IMG
DRY: $REPO/tools/flash-slot.sh a $BOOT $DTBO
EOF
)"
    if [[ "$dry_lines" == "$expected_lines" ]] &&
       [[ "$dry1" == *"omamobile-set-pin"* ]] &&
       [[ "$dry1" == *"timedatectl set-timezone"* ]]; then
        pass "dry-run raw .img order and notes"
    else
        fail "dry-run raw .img mismatch: got '$dry_lines'"
    fi
fi

# Test dry-run 2: .img.xz (older uncompressed .img removed first) with --firmware and --slot b
rm -f "$ROOTFS_IMG"
dry2="$("$TOOL" --key "$KEY" --firmware "$SUPER" --slot b --dry-run "$ROOTFS_XZ" "$BOOT" "$DTBO" 2>&1)" && rc=0 || rc=$?
if [[ "$rc" -ne 0 ]]; then
    fail "dry-run .img.xz + --firmware exited $rc: $dry2"
else
    dry_lines="$(printf '%s\n' "$dry2" | grep '^DRY: ' || true)"
    expected_lines="$(cat <<EOF
DRY: xz -dkf $ROOTFS_XZ
DRY: $REPO/tools/image-set-key.sh $ROOTFS_IMG $KEY
DRY: $REPO/tools/flash-rootfs.sh $ROOTFS_IMG
DRY: $REPO/tools/flash-slot.sh b $BOOT $DTBO
DRY: $REPO/tools/touch-firmware.sh $SUPER --install
DRY: $REPO/tools/amp-firmware.sh $SUPER --install
DRY: $REPO/tools/mic-firmware.sh $SUPER --install
DRY: $REPO/tools/ytssh systemctl reboot
EOF
)"
    if [[ "$dry_lines" == "$expected_lines" ]]; then
        pass "dry-run .img.xz + --firmware order"
    else
        fail "dry-run .img.xz + --firmware mismatch:
expected:
$expected_lines
got:
$dry_lines"
    fi
fi

# Test dry-run 3: .img.zst when uncompressed .img does not exist
dry3="$("$TOOL" --key "$KEY" --dry-run "$ROOTFS_ZST" "$BOOT" "$DTBO" 2>&1)" && rc=0 || rc=$?
if [[ "$rc" -ne 0 ]]; then
    fail "dry-run .img.zst exited $rc: $dry3"
else
    dry_lines="$(printf '%s\n' "$dry3" | grep '^DRY: ' || true)"
    expected_lines="$(cat <<EOF
DRY: zstd -dkf $ROOTFS_ZST
DRY: $REPO/tools/image-set-key.sh $ROOTFS_IMG $KEY
DRY: $REPO/tools/flash-rootfs.sh $ROOTFS_IMG
DRY: $REPO/tools/flash-slot.sh a $BOOT $DTBO
EOF
)"
    if [[ "$dry_lines" == "$expected_lines" ]]; then
        pass "dry-run .img.zst order"
    else
        fail "dry-run .img.zst mismatch: got '$dry_lines'"
    fi
fi

# Test dry-run 4: skip decompression if .img already exists and is newer than .img.xz
sleep 1
printf 'newer-raw-rootfs' > "$ROOTFS_IMG"
dry4="$("$TOOL" --key "$KEY" --dry-run "$ROOTFS_XZ" "$BOOT" "$DTBO" 2>&1)" && rc=0 || rc=$?
if [[ "$rc" -ne 0 ]]; then
    fail "dry-run newer .img exited $rc: $dry4"
else
    dry_lines="$(printf '%s\n' "$dry4" | grep '^DRY: ' || true)"
    if printf '%s\n' "$dry_lines" | grep -q 'xz -dkf'; then
        fail "dry-run should skip xz when .img is newer"
    else
        pass "dry-run skips xz when .img is newer"
    fi
fi

if [[ "$FAILURES" -ne 0 ]]; then
    echo "$FAILURES test(s) failed"
    exit 1
fi
echo "all install tests passed"
