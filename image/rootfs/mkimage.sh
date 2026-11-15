#!/usr/bin/env bash
# Runs inside the helper container (Linux arm64, e2fsprogs >= 1.43) to populate
# an ext4 image from a rootfs tar stream on stdin without requiring loop mounts.
#
# Environment variables:
#   OUT_IMG     — output file path inside the container
#   SIZE_MIB    — filesystem size in MiB (default: 8192 = 8 GiB)
#   LABEL       — ext4 volume label (default: omarchy-root)

set -euo pipefail

OUT_IMG="${OUT_IMG:-/out/rootfs-omarchy-aarch64.img}"
SIZE_MIB="${SIZE_MIB:-8192}"
LABEL="${LABEL:-omarchy-root}"

STAGE="$(mktemp -d /tmp/rootfs-stage.XXXXXX)"
trap 'rm -rf "$STAGE"' EXIT

echo "==> [mkimage] Extracting container rootfs tar stream into $STAGE"
bsdtar --numeric-owner -xpf - -C "$STAGE"

# Clean container runtime artifacts injected by Docker onto the root layer
rm -f "$STAGE/.dockerenv" "$STAGE/.dockerinit"
rm -rf "$STAGE/dev" "$STAGE/proc" "$STAGE/sys" "$STAGE/run" "$STAGE/tmp"
mkdir -p "$STAGE/dev" "$STAGE/proc" "$STAGE/sys" "$STAGE/run" "$STAGE/tmp" "$STAGE/mnt"
chmod 1777 "$STAGE/tmp"
chmod 0755 "$STAGE/dev" "$STAGE/proc" "$STAGE/sys" "$STAGE/run" "$STAGE/mnt"

# Copy /etc/lenovomarchy-packages.txt out to /out/packages.txt
if [[ -f "$STAGE/etc/lenovomarchy-packages.txt" ]]; then
    cp -f "$STAGE/etc/lenovomarchy-packages.txt" "$(dirname "$OUT_IMG")/packages.txt"
fi

# Restore fresh hostname, /etc/hosts, and DNS resolver config (Docker bind-mounts
# these files read-only during container build)
echo "lenovomarchy" > "$STAGE/etc/hostname"
cat > "$STAGE/etc/hosts" <<'EOF'
127.0.0.1   localhost
::1         localhost
127.0.1.1   lenovomarchy.localdomain lenovomarchy
EOF
rm -f "$STAGE/etc/resolv.conf"
cat > "$STAGE/etc/resolv.conf" <<'EOF'
# Managed by NetworkManager on device; fallback public resolvers:
nameserver 1.1.1.1
nameserver 9.9.9.9
EOF

# Ensure sudo binary & sudoers permissions survived tar round-trip
if [[ -f "$STAGE/usr/bin/sudo" ]]; then
    chown root:root "$STAGE/usr/bin/sudo"
    chmod 4755 "$STAGE/usr/bin/sudo"
fi
if [[ -f "$STAGE/etc/sudoers.d/10-wheel" ]]; then
    chown root:root "$STAGE/etc/sudoers.d/10-wheel"
    chmod 0440 "$STAGE/etc/sudoers.d/10-wheel"
fi

echo "==> [mkimage] Staging tree size: $(du -sh "$STAGE" | awk '{print $1}')"
echo "==> [mkimage] Creating ${SIZE_MIB} MiB ext4 image at $OUT_IMG (label=$LABEL)"

rm -f "$OUT_IMG"
mkdir -p "$(dirname "$OUT_IMG")"

mke2fs \
    -t ext4 \
    -F \
    -L "$LABEL" \
    -b 4096 \
    -I 256 \
    -m 1 \
    -O ^metadata_csum_seed,^orphan_file \
    -E lazy_itable_init=0,lazy_journal_init=0 \
    -d "$STAGE" \
    "$OUT_IMG" \
    "${SIZE_MIB}M"

echo "==> [mkimage] Running e2fsck -fy on $OUT_IMG"
e2fsck -fy "$OUT_IMG" || {
    rc=$?
    if [[ $rc -ge 4 ]]; then
        echo "ERROR: e2fsck failed with exit code $rc" >&2
        exit "$rc"
    fi
}

echo "==> [mkimage] Filesystem summary:"
dumpe2fs -h "$OUT_IMG" 2>/dev/null | grep -E '^(Filesystem volume name|Filesystem UUID|Filesystem features|Block count|Free blocks|Block size|Inode count|Free inodes):' || true
echo "==> [mkimage] Done: $OUT_IMG ($(stat -c '%s' "$OUT_IMG") bytes)"
