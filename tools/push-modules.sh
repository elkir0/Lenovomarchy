#!/usr/bin/env bash
# Install a kernel build's modules into the running Omarchy root over SSH.
# Usage: tools/push-modules.sh [<modules.tar.xz>]   (default out/kernel/modules.tar.xz)
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODS="${1:-$REPO/out/kernel/modules.tar.xz}"
rel=$(tar -tJf "$MODS" | awk -F/ '$2=="lib" && $3=="modules" && $4!="" {print $4; exit}')
ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    -o LogLevel=ERROR root@192.168.77.1 \
    "rm -rf /usr/lib/modules/$rel && tar -xJ -C /usr ./lib/modules && rm -f /usr/lib/modules/$rel/build && depmod $rel && echo installed $rel" < "$MODS"
