-- Lenovo Yoga Tab 11 (YT-J706F) tablet layer (image/rootfs/tablet.lua)
-- Appended to ~/.config/hypr/hyprland.lua so it loads after Omarchy's defaults,
-- the user's config files, and the toggles.

-- Unbind laptop lid switch rules (the tablet has only its internal DSI panel).
hl.unbind("switch:on:Lid Switch")
hl.unbind("switch:off:Lid Switch")

-- On-screen keyboard (squeekboard): pop up without layer animation and remain
-- usable above the session lock screen.
hl.layer_rule({ match = { namespace = "^osk$" }, no_anim = true, animation = "none" })
hl.layer_rule({ match = { namespace = "^osk$" }, above_lock = 2 })
hl.layer_rule({ match = { namespace = "^omamobile-osk-hide$" }, above_lock = 2, no_anim = true })

-- Lock on start if the user has configured a PIN/password via omamobile-set-pin.
o.launch_on_start("bash -c 'omarchy-toggle-enabled lock-on-start || exit 0; "
    .. "for _ in $(seq 100); do omarchy-shell lock status >/dev/null 2>&1 && break; sleep 0.2; done; "
    .. "omarchy-system-lock'")

-- Auto-rotation: follow the accelerometer (iio-sensor-proxy) with the output
-- and the touch/pen layer.
o.launch_on_start("yt11-autorotate")

-- Fit floating windows to the portrait/landscape tablet screen (800x1333 logical at scale 1.5).
o.window({ tag = "floating-window" }, { size = { "(monitor_w*0.92)", "(monitor_h*0.65)" } })
o.window("org.omarchy.about", { size = { "(monitor_w*0.92)", "(monitor_h*0.50)" } })
-- Lenovo Yoga Tab 11 tablet end
