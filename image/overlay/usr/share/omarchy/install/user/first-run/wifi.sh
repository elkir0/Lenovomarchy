#!/usr/bin/env bash
# First-run Wi-Fi prompt via NetworkManager (iwd is not used on this tablet).
if ! ping -c1 -W1 1.1.1.1 >/dev/null 2>&1; then
  notify-send "Connect to Wi-Fi" "Tap the Wi-Fi icon in Quick Settings to get online." -u critical
fi
