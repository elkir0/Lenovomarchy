# Source this file (". tools/yt.sh") before talking to the tablet over adb.
#
# - Targets the Lenovo Yoga Tab 11 (YT-J706F) by adb transport id, so a
#   phone or another device attached to the same Mac is never touched.
# - Never prints serial numbers: use `adb get-state`, never `adb devices`.
# - `redact` filters every output that may carry an identifier: serial
#   numbers, the kernel command line (it holds the serial), MAC addresses.

YT_T=$(adb devices -l | awk '/model:Lenovo_YT_J706F/ {for (i = 1; i <= NF; i++) if ($i ~ /^transport_id:/) {split($i, a, ":"); print a[2]}}')
if [ -z "$YT_T" ]; then
    echo "yt.sh: the YT-J706F is not in adb" >&2
fi

# Run a shell command on the tablet only.
yt() { adb -t "$YT_T" shell "$@"; }
# Any other adb command (reboot bootloader, pull...) on the tablet only.
ytadb() { adb -t "$YT_T" "$@"; }

redact() {
    grep -viE 'serial|kernel command line|bootargs|me_id|soc_id|imei|meid|bdaddr|wifimac|mac_addr|macaddr|androidboot|cmdline|uuid|android_id|device_id|cpuid|efuse|hrid' \
        | sed -E 's/([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}/<MAC>/g'
}
