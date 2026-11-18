#!/bin/bash
# Offline tests for image/overlay/usr/local/sbin/yt11-charge-guard against a
# fake /sys/class/power_supply. Run from anywhere: bash tests/charge-guard/run-tests.sh
set -u

here=$(cd "$(dirname "$0")" && pwd)
guard=$here/../../image/overlay/usr/local/sbin/yt11-charge-guard
work=$(mktemp -d)
trap 'kill "$pid" 2>/dev/null; rm -rf "$work"' EXIT
pid=

fail=0
pass=0
check() {	# <description> <expected> <actual>
	if [ "$2" = "$3" ]; then
		pass=$((pass + 1))
	else
		fail=$((fail + 1))
		echo "FAIL: $1: expected '$2', got '$3'"
	fi
}

sys=$work/ps
bat=$sys/bq27541-0
chg=$sys/mt6360-chg.3.auto
tcpm=$sys/tcpm-source-psy-mt6360-tcpc.6.auto
reset_sys() {
	rm -rf "$sys"
	mkdir -p "$bat" "$chg" "$tcpm"
	echo Battery > "$bat/type"
	echo 335 > "$bat/temp"
	echo USB > "$chg/type"
	echo 500000 > "$chg/constant_charge_current"
	echo 5000000 > "$chg/constant_charge_current_max"
	echo USB > "$tcpm/type"
}
cur() { cat "$chg/constant_charge_current"; }
run() { YT11_POWER_SUPPLY_DIR=$sys "$guard" "$@" 2>/dev/null; }
temp() { echo "$1" > "$bat/temp"; }

# --once: one band per temperature, from a fresh start.
reset_sys
for case in "335 2000000" "449 2000000" "450 100000" "600 100000" \
	"100 2000000" "99 500000" "0 500000" "-1 100000" "-150 100000"; do
	set -- $case
	temp "$1"; echo 500000 > "$chg/constant_charge_current"
	run --once
	check "--once at $1 tenths" "$2" "$(cur)"
done

# Unreadable or absurd temperatures: 500 mA.
for bad in "" "abc" "65380" "-" "12-3" "-500"; do
	temp "$bad"; echo 2000000 > "$chg/constant_charge_current"
	run --once
	check "--once with temp '$bad'" 500000 "$(cur)"
done
rm -f "$bat/temp"
echo 2000000 > "$chg/constant_charge_current"
run --once
check "no temp file" 500000 "$(cur)"

# Never above the charger's own maximum.
reset_sys
echo 1500000 > "$chg/constant_charge_current_max"
run --once
check "capped by constant_charge_current_max" 1500000 "$(cur)"

# No writable charger: exit 0, nothing written.
reset_sys
chmod a-w "$chg/constant_charge_current"
run --once; rc=$?
check "no writable charger: exit code" 0 "$rc"
check "no writable charger: untouched" 500000 "$(cur)"
chmod u+w "$chg/constant_charge_current"

# --sleep: at most 1 A, 500 mA from 40 C, never above what is set.
reset_sys
echo 2000000 > "$chg/constant_charge_current"; temp 335; run --sleep
check "--sleep at 33.5 C from 2 A" 1000000 "$(cur)"
echo 2000000 > "$chg/constant_charge_current"; temp 400; run --sleep
check "--sleep at 40 C from 2 A" 500000 "$(cur)"
echo 100000 > "$chg/constant_charge_current"; temp 460; run --sleep
check "--sleep keeps a cut" 100000 "$(cur)"
echo 2000000 > "$chg/constant_charge_current"; temp x; run --sleep
check "--sleep without temperature" 500000 "$(cur)"

# --safe
echo 2000000 > "$chg/constant_charge_current"; run --safe
check "--safe" 500000 "$(cur)"

# Service: hysteresis, reapply after a reset, 500 mA on SIGTERM.
reset_sys
temp 335
YT11_POWER_SUPPLY_DIR=$sys YT11_CHARGE_GUARD_INTERVAL=0.1 "$guard" 2> "$work/log" &
pid=$!
step() { temp "$1"; sleep 0.4; check "$2" "$3" "$(cur)"; }
step 335 "service starts at 33.5 C" 2000000
step 455 "service: 45.5 C cuts" 100000
step 430 "service: 43 C stays cut (hysteresis)" 100000
step 420 "service: 42 C back to 2 A" 2000000
step 95 "service: 9.5 C cold" 500000
step 120 "service: 12 C stays cold (hysteresis)" 500000
step 130 "service: 13 C back to 2 A" 2000000
step -5 "service: -0.5 C cut" 100000
step 20 "service: 2 C stays cut" 100000
step 30 "service: 3 C cold" 500000
echo 500000 > "$chg/constant_charge_current"
step 200 "service: reapplies after a reset" 2000000
kill -TERM "$pid"; wait "$pid"; rc=$?; pid=
check "service: exit code on SIGTERM" 0 "$rc"
check "service: 500 mA after SIGTERM" 500000 "$(cur)"
check "service: logged the hot cut" 1 "$(grep -c '45.5 C, hot: charge current 100 mA' "$work/log")"
sleep 0.2
check "service: no stray sleep left" 0 "$(ps -axo command | grep -c "^sleep 0.1$")"

echo "charge-guard tests: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
