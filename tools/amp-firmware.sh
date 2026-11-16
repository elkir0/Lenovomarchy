#!/usr/bin/env bash
# Extract the CS35L41 speaker-protection DSP firmware (Cirrus "CSPL"
# protection firmware and Lenovo's tuning for each amplifier) from the unit's
# own stock `super` image and, with --install, copy it to the running tablet
# under the names mainline's wm_adsp looks for: the board DT gives the amps
# cirrus,subsystem-id = "yt-j706f" and the prefixes SPK1-SPK4 (amp 0x40 is
# SPK1 and takes prot1.bin, as in the stock DT). Lenovo's files are not
# redistributable: they stay under private/ and on the unit.
#
# Usage: tools/amp-firmware.sh <super.img> [--install]
#        tools/amp-firmware.sh --install     (files already in private/)
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$REPO/private/extracted/cs35l41"
FILES="cs35l41-dsp1-spk-prot.wmfw cs35l41-dsp1-spk-prot1.bin cs35l41-dsp1-spk-prot2.bin
       cs35l41-dsp1-spk-prot3.bin cs35l41-dsp1-spk-prot4.bin"

if [[ "${1:-}" != "--install" ]]; then
    SUPER="${1:?usage: $0 <super.img> [--install] | --install}"
    shift
    mkdir -p "$OUT"
    python3 -I "$REPO/tools/lp-extract.py" "$SUPER" vendor_a "$OUT/vendor_a.img"
    docker run --rm -v "$OUT:/x" alpine:3.22 sh -ec "
        apk add -q e2fsprogs e2fsprogs-extra >/dev/null
        for f in $(echo $FILES); do debugfs -R \"dump /firmware/\$f /x/\$f\" /x/vendor_a.img; done"
    rm -f "$OUT/vendor_a.img"
    for f in $FILES; do ls -l "$OUT/$f" | awk '{print $NF ":", $5, "bytes"}'; done
fi

if [[ "${1:-}" == "--install" ]]; then
    ssh_tab() {
        ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
            -o LogLevel=ERROR "root@${YT11_HOST:-192.168.77.1}" "$@"
    }
    dst=/usr/lib/firmware/cirrus
    ssh_tab "install -d $dst"
    ssh_tab "cat > $dst/cs35l41-dsp1-spk-prot-yt-j706f.wmfw" < "$OUT/cs35l41-dsp1-spk-prot.wmfw"
    for n in 1 2 3 4; do
        ssh_tab "cat > $dst/cs35l41-dsp1-spk-prot-yt-j706f-spk$n.bin" \
            < "$OUT/cs35l41-dsp1-spk-prot$n.bin"
    done
    ssh_tab "ls -l $dst/cs35l41-dsp1-spk-prot-yt-j706f*" | awk '{print "installed", $NF}'
fi
