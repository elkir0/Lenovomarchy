#!/usr/bin/env bash
# Offline test suite for tools/image-set-key.sh.
# Requires Docker (alpine:3.22) and ssh-keygen. No tablet needed.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TOOL="$REPO/tools/image-set-key.sh"

FAILURES=0
pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1"; FAILURES=$((FAILURES + 1)); }

TMPDIR_TEST="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_TEST"' EXIT

IMG="$TMPDIR_TEST/rootfs.img"
KEY1="$TMPDIR_TEST/id_test1"
KEY2="$TMPDIR_TEST/id_test2"

ssh-keygen -t ed25519 -N "" -f "$KEY1" -C "test1@lenovomarchy" >/dev/null
ssh-keygen -t ed25519 -N "" -f "$KEY2" -C "test2@lenovomarchy" >/dev/null

# Build a 16 MiB raw ext4 image containing /root and /home/alarm (1000:1000).
docker run --rm -v "$TMPDIR_TEST:/out" alpine:3.22 sh -ec '
    apk add -q e2fsprogs >/dev/null
    mkdir -p /tmp/fs/root /tmp/fs/home/alarm
    chown 1000:1000 /tmp/fs/home/alarm
    truncate -s 16M /out/rootfs.img
    mke2fs -q -t ext4 -d /tmp/fs /out/rootfs.img
'

# Test 1: install one key
out1="$("$TOOL" "$IMG" "${KEY1}.pub" 2>&1)" && rc=0 || rc=$?
if [[ "$rc" -eq 0 && "$out1" == *"keys installed: 1"* ]]; then
    pass "install single key"
else
    fail "install single key (rc=$rc, out=$out1)"
fi

# Verify contents, modes, and owners via debugfs inside alpine:3.22
verify_out="$(docker run --rm -v "$TMPDIR_TEST:/img" alpine:3.22 sh -ec '
    apk add -q e2fsprogs e2fsprogs-extra >/dev/null
    for p in /root/.ssh /root/.ssh/authorized_keys /home/alarm/.ssh /home/alarm/.ssh/authorized_keys; do
        echo "=== $p ==="
        debugfs -R "stat $p" /img/rootfs.img 2>/dev/null
    done
    echo "=== CAT_ROOT ==="
    debugfs -R "cat /root/.ssh/authorized_keys" /img/rootfs.img 2>/dev/null
    echo "=== CAT_ALARM ==="
    debugfs -R "cat /home/alarm/.ssh/authorized_keys" /img/rootfs.img 2>/dev/null
')"

check_stat() {
    local label="$1" path="$2" expect_type="$3" expect_mode="$4" expect_uid="$5" expect_gid="$6"
    local section
    section="$(printf '%s\n' "$verify_out" | awk -v p="=== $path ===" '$0==p{f=1;next} /^=== /{f=0} f')"
    if printf '%s\n' "$section" | grep -q "Type: *$expect_type" &&
       printf '%s\n' "$section" | grep -q "Mode: *$expect_mode" &&
       printf '%s\n' "$section" | grep -q "User: *$expect_uid .*Group: *$expect_gid "; then
        pass "$label"
    else
        fail "$label (got: $section)"
    fi
}

check_stat "root .ssh dir mode/owner" "/root/.ssh" "directory" "0700" "0" "0"
check_stat "root authorized_keys mode/owner" "/root/.ssh/authorized_keys" "regular" "0600" "0" "0"
check_stat "alarm .ssh dir mode/owner" "/home/alarm/.ssh" "directory" "0700" "1000" "1000"
check_stat "alarm authorized_keys mode/owner" "/home/alarm/.ssh/authorized_keys" "regular" "0600" "1000" "1000"

expected_key1="$(cat "${KEY1}.pub")"
root_cat="$(printf '%s\n' "$verify_out" | awk '$0=="=== CAT_ROOT ==="{f=1;next} /^=== /{f=0} f')"
alarm_cat="$(printf '%s\n' "$verify_out" | awk '$0=="=== CAT_ALARM ==="{f=1;next} /^=== /{f=0} f')"
if [[ "$root_cat" == "$expected_key1" && "$alarm_cat" == "$expected_key1" ]]; then
    pass "single key readback matches"
else
    fail "single key readback mismatch"
fi

# Test 2: replace existing authorized_keys with two keys
out2="$("$TOOL" "$IMG" "${KEY1}.pub" "${KEY2}.pub" 2>&1)" && rc=0 || rc=$?
if [[ "$rc" -eq 0 && "$out2" == *"keys installed: 2"* ]]; then
    pass "replace with two keys"
else
    fail "replace with two keys (rc=$rc, out=$out2)"
fi

verify2="$(docker run --rm -v "$TMPDIR_TEST:/img" alpine:3.22 sh -ec '
    apk add -q e2fsprogs e2fsprogs-extra >/dev/null
    debugfs -R "cat /home/alarm/.ssh/authorized_keys" /img/rootfs.img 2>/dev/null
')"
expected_both="$(cat "${KEY1}.pub" "${KEY2}.pub")"
if [[ "$verify2" == "$expected_both" ]]; then
    pass "two-key replacement content matches"
else
    fail "two-key replacement content mismatch"
fi

# Test 3: refusals
if out="$("$TOOL" "$IMG" "$KEY1" 2>&1)"; then
    fail "refuse private key (unexpectedly exited 0)"
else
    pass "refuse private key"
fi

EMPTY_KEY="$TMPDIR_TEST/empty.pub"
: > "$EMPTY_KEY"
if out="$("$TOOL" "$IMG" "$EMPTY_KEY" 2>&1)"; then
    fail "refuse empty key file (unexpectedly exited 0)"
else
    pass "refuse empty key file"
fi

BAD_KEY="$TMPDIR_TEST/bad.pub"
printf '# comment line\nnot-a-valid-key-type AAAAB3Nza\n' > "$BAD_KEY"
if out="$("$TOOL" "$IMG" "$BAD_KEY" 2>&1)"; then
    fail "refuse invalid key prefix (unexpectedly exited 0)"
else
    pass "refuse invalid key prefix"
fi

NOT_EXT4="$TMPDIR_TEST/not_ext4.simg"
printf '\x3a\xff\x26\xed' > "$NOT_EXT4"
dd if=/dev/zero bs=1024 count=2 >> "$NOT_EXT4" 2>/dev/null
if out="$("$TOOL" "$NOT_EXT4" "${KEY1}.pub" 2>&1)"; then
    fail "refuse non-ext4 image (unexpectedly exited 0)"
elif [[ "$out" == *".simg"* && "$out" == *".xz"* ]]; then
    pass "refuse non-ext4 image with conversion message"
else
    fail "refuse non-ext4 image missing expected hint (out=$out)"
fi

if [[ "$FAILURES" -ne 0 ]]; then
    echo "$FAILURES test(s) failed"
    exit 1
fi
echo "all image-set-key tests passed"
