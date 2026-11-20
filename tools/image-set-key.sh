#!/usr/bin/env bash
# Install one or more SSH public keys into a raw ext4 rootfs image as
# /root/.ssh/authorized_keys (0:0) and /home/alarm/.ssh/authorized_keys
# (1000:1000) using debugfs in an alpine:3.22 Docker container.
#
# Usage: tools/image-set-key.sh <rootfs.img> <key.pub> [<key.pub>...]

set -euo pipefail

if [[ $# -lt 2 ]]; then
    echo "usage: $0 <rootfs.img> <key.pub> [<key.pub>...]" >&2
    exit 1
fi

IMG="$1"
shift

if [[ ! -f "$IMG" ]]; then
    echo "error: image not found: $IMG" >&2
    exit 1
fi

IMG="$(cd "$(dirname "$IMG")" && pwd)/$(basename "$IMG")"
IMG_DIR="$(dirname "$IMG")"
IMG_BASE="$(basename "$IMG")"

# Check ext4 superblock magic 0xEF53 (little-endian bytes 53 ef) at offset 1080.
magic="$(od -An -tx1 -j 1080 -N 2 "$IMG" 2>/dev/null | tr -d ' \n\r' || true)"
if [[ "$magic" != "53ef" ]]; then
    echo "error: $IMG is not a raw ext4 image (superblock magic at 1080 is '${magic:-missing}', expected 0xEF53); a .simg/.xz/.zst image must be converted or decompressed first" >&2
    exit 1
fi

TMPDIR_WORK="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_WORK"' EXIT
KEYS_OUT="$TMPDIR_WORK/authorized_keys"
: > "$KEYS_OUT"

key_count=0
for keyfile in "$@"; do
    if [[ ! -f "$keyfile" ]]; then
        echo "error: key file not found: $keyfile" >&2
        exit 1
    fi
    if [[ ! -s "$keyfile" ]]; then
        echo "error: key file is empty: $keyfile" >&2
        exit 1
    fi
    if grep -qF "PRIVATE KEY" "$keyfile"; then
        echo "error: refusing private key file: $keyfile" >&2
        exit 1
    fi

    file_keys=0
    while IFS= read -r line || [[ -n "$line" ]]; do
        line="${line%$'\r'}"
        stripped="${line#"${line%%[![:space:]]*}"}"
        [[ -z "$stripped" || "$stripped" == \#* ]] && continue
        case "$stripped" in
            ssh-*|ecdsa-*|sk-*)
                file_keys=$((file_keys + 1))
                key_count=$((key_count + 1))
                ;;
            *)
                echo "error: invalid SSH public key line in $keyfile (must start with ssh-, ecdsa-, or sk-)" >&2
                exit 1
                ;;
        esac
    done < "$keyfile"

    if [[ "$file_keys" -eq 0 ]]; then
        echo "error: no SSH public keys found in $keyfile" >&2
        exit 1
    fi

    cat "$keyfile" >> "$KEYS_OUT"
    if [[ -n "$(tail -c 1 "$KEYS_OUT" | tr -d '\n')" ]]; then
        printf '\n' >> "$KEYS_OUT"
    fi
done

docker run --rm -v "$IMG_DIR:/img" -v "$TMPDIR_WORK:/work" alpine:3.22 sh -ec '
    apk add -q e2fsprogs e2fsprogs-extra >/dev/null
    img_path="/img/'"$IMG_BASE"'"
    has_path() {
        debugfs -R "stat $1" "$img_path" 2>&1 | grep -q "^Inode:"
    }
    : > /work/debugfs.cmds
    for pair in "/root:0:0" "/home/alarm:1000:1000"; do
        base="${pair%%:*}"
        rest="${pair#*:}"
        uid="${rest%%:*}"
        gid="${rest#*:}"
        if ! has_path "$base/.ssh"; then
            printf "mkdir %s/.ssh\n" "$base" >> /work/debugfs.cmds
        fi
        if has_path "$base/.ssh/authorized_keys"; then
            printf "rm %s/.ssh/authorized_keys\n" "$base" >> /work/debugfs.cmds
        fi
        cat >> /work/debugfs.cmds <<CMDS
write /work/authorized_keys $base/.ssh/authorized_keys
sif $base/.ssh mode 040700
sif $base/.ssh uid $uid
sif $base/.ssh gid $gid
sif $base/.ssh/authorized_keys mode 0100600
sif $base/.ssh/authorized_keys uid $uid
sif $base/.ssh/authorized_keys gid $gid
CMDS
    done
    debugfs -w -f /work/debugfs.cmds "$img_path" >/dev/null
    debugfs -R "cat /root/.ssh/authorized_keys" "$img_path" > /work/read_root
    debugfs -R "cat /home/alarm/.ssh/authorized_keys" "$img_path" > /work/read_alarm
    cmp -s /work/authorized_keys /work/read_root || { echo "error: /root/.ssh/authorized_keys readback mismatch" >&2; exit 1; }
    cmp -s /work/authorized_keys /work/read_alarm || { echo "error: /home/alarm/.ssh/authorized_keys readback mismatch" >&2; exit 1; }
    e2fsck -fn "$img_path"
'

echo "keys installed: $key_count"
