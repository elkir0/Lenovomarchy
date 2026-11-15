-- Override default Hyprland looknfeel settings for the Lenovo Yoga Tab 11 (YT-J706F).
-- Disables blur and drop shadows to save memory bandwidth and GPU power on
-- Mali-G76 (Panfrost) while driving the 1200x2000 panel at 60 Hz.

hl.config({
  general = {
    gaps_in = 4,
    gaps_out = 6,
  },
  decoration = {
    blur = {
      enabled = false,
    },
    shadow = {
      enabled = false,
    },
  },
})
