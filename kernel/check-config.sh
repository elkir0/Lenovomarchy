#!/bin/sh
# Compare every CONFIG_* assignment of a config fragment against a
# final kernel .config.  Prints each fragment option whose value
# differs in the final config, exits 1 if any, 0 otherwise.
#
# Usage: kernel/check-config.sh <final .config> <fragment>
#
# Only CONFIG assignments are compared, line by line: the fragment is
# expected to carry the exact lines that should appear in the final
# config (comments and blank lines are ignored).

set -eu

usage() {
    echo "Usage: $0 <final .config> <fragment>" >&2
    exit 2
}

[ $# -eq 2 ] || usage
FINAL=$1
FRAGMENT=$2

[ -r "$FINAL" ] || { echo "error: cannot read $FINAL" >&2; exit 2; }
[ -r "$FRAGMENT" ] || { echo "error: cannot read $FRAGMENT" >&2; exit 2; }

# Key = symbol name, value = desired line (CONFIG_FOO=y or
# "# CONFIG_FOO is not set").
want=$(mktemp) || exit 2
got=$(mktemp) || exit 2
trap 'rm -f "$want" "$got"' EXIT INT TERM

# Normalise both files to "SYMBOL<TAB>value" so a fragment line and a
# final config line compare equal regardless of surrounding comments.
normalise() {
    grep -E '^(CONFIG_[A-Za-z0-9_]+=|# CONFIG_[A-Za-z0-9_]+ is not set)' "$1" \
    | awk -F= '/^#/ { sub(/^# /, ""); sub(/ is not set$/, ""); print $1 "\tn"; next }
        { print $1 "\t" $2 }'
}

normalise "$FRAGMENT" > "$want"
normalise "$FINAL" > "$got"

status=0
while IFS="$(printf '\t')" read -r sym val; do
    final_val=$(awk -F'\t' -v s="$sym" '$1 == s { print $2; exit }' "$got")
    if [ "$final_val" != "$val" ]; then
        echo "MISMATCH $sym: fragment wants $val, final config has ${final_val:-<absent>}"
        status=1
    fi
done < "$want"

if [ "$status" -eq 0 ]; then
    echo "OK: every fragment option matches the final config"
fi
exit "$status"
