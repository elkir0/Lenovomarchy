-- See https://wiki.hypr.land/Configuring/Basics/Monitors/
-- List current monitors and supported resolutions with: hyprctl monitors all
-- Lenovo Yoga Tab 11 (YT-J706F): 1200x2000 panel mounted rotated 180 degrees
-- (transform = 2), default scale 1.5 (800x1333 logical). Touch is mounted
-- upright (transform = 0).

local omarchy_gdk_scale = 2
local omarchy_monitor_scale = 1.5

hl.env("GDK_SCALE", tostring(omarchy_gdk_scale))
hl.monitor({ output = "DSI-1", mode = "preferred", position = "auto", scale = omarchy_monitor_scale, transform = 2 })
hl.config({ input = { touchdevice = { transform = 0 } } })
