-- yt11 mic gain: fixed software gain on the built-in microphones
-- (Lenovo YT-J706F).
--
-- In its raw mode the AS33970 voice processor delivers speech at arm's
-- length around -36 dBFS rms (peaks near -18 dBFS), too quiet to listen to.
-- Neither the chip driver nor the AFE has a capture volume, so the gain is
-- applied on the PipeWire node's master volume. That volume sits under the
-- source's own (route) volume: the slider still reads 100 % and keeps its
-- full range below.

local NODE = "alsa_input.platform-sound.analog-input"
local GAIN = 5.623 -- linear, +15 dB; leaves about 3 dB before speech clips

om = ObjectManager {
  Interest {
    type = "node",
    Constraint { "node.name", "=", NODE },
  }
}

om:connect("object-added", function (_, node)
  node:set_param("Props", Pod.Object {
    "Spa:Pod:Object:Param:Props", "Props",
    volume = GAIN,
  })
end)

om:activate()
