# M2: omamobile-shell 0.2.133 on the YT-J706F tablet

Date: 2026-11-17 · Package: `image/pkg/omamobile-shell` · Status: 0.2.133-1 installed on the unit (home screen and quick settings verified); 0.2.133-2 = the follow-up below

## Follow-up (pkgrel 2): phone leftovers found on the unit

The first 0.2.133-1 install showed three kinds of phone leftovers. All are
fixed in patch `0004-tablet-phone-leftovers.patch` (pkgrel 2); `check()`'s
`setup-user.sh` run covers each with a new cleanup pass.

**1. `omamobile-setup-user` seeded phone plugins and menu rows.** Every
phone-only step in the script, and what the tablet build does with it now:

| Step (marker) | What the phone does | Tablet (0004) |
| --- | --- | --- |
| `omamobile-fingerprint-plugin`, `omamobile-menu-fingerprint` | adds `omamobile.fingerprint` + a Setup > Fingerprint row | gated on `is_unshipped`; never added; the row's `when: test -x …omamobile-fp-chroot` also fails, but it is no longer seeded at all |
| `omamobile-voice-plugin`, `omamobile-menu-voice` | adds `omamobile.voice` + Setup > Voice | gated |
| `omamobile-mobilenetwork-plugin`, `omamobile-menu-mobilenetwork` | adds `omamobile.mobilenetwork` + Setup > Mobile network | gated (the tablet's `shell.json` had the entry from -1; see cleanup below) |
| `omamobile-update-plugin`, `omamobile-menu-update` | adds `omamobile.update`, rebinds Update > Omarchy, hides fwupd/Plymouth rows | gated; the two hides move to the standing `menu_hide` list (no fwupd, no Plymouth here either) so they no longer depend on the unshipped sheet |
| `omamobile-access-plugin` | adds `omamobile.access` (portal permission sheet) | gated |
| `omamobile-call-plugin` | adds `omamobile.call` | gated |
| `omamobile-suspend-off` | creates the `suspend-off` toggle (phone kernel can't suspend) | inverted: removes a stale toggle — this tablet's s2idle is verified (docs/hardware/BOARD.md) and the menu keeps Suspend |
| `omamobile-auto-sleep-on` | creates `omamobile-sleep` where the device flag says so | flag never exists here; the else branch now also clears a stale `omamobile-sleep` toggle (omamobile-sleepd is not shipped) |
| voxtype setup blocks | Voxtype config/model/daemon (`command -v voxtype` gated) | left as-is: already a no-op without voxtype, nothing to gate |
| omatel-agent enable | `[[ -f $units/omatel-agent.service ]]` gated | left as-is: no unit file here, no-op |
| `omamobile-lock-after-screensaver`, `omamobile-screensaver` branding | toggles/files for the screensaver flow | left as-is: inert with idle 0/0 and no screensaver; correct the day one is enabled |

**Cleanup pass (runs at every login):** `remove_unshipped` takes the six
unshipped plugin ids out of `~/.config/omarchy/shell.json` (a plugin entry
whose folder is gone makes the host log a load failure), deletes stale
links under `~/.config/omarchy/plugins/`, and `remove_phone_menu_rows`
strips the four phone menu rows from `omarchy-menu.jsonc`. Everything the
tablet ships — plugins, their settings, `disabledPlugins`, the user's own
menu rows — stays, and the pass is idempotent (a second login changes
nothing). `test/setup-user.sh` builds a phone-era `shell.json` (all six
phone plugins among the tablet's own, `disabledPlugins`, a 6-column
launcher), stale links to three unshipped plugins plus one shipped, and
the four phone menu rows plus the tablet's PIN row; one run must remove
exactly the phone side and keep the rest.

**2. `WARN scene: … omamobile.voice/VoiceLinkClient.qml: No such file`.**
The launcher's voice link was a `Loader` with a fixed source into the
unshipped plugin's folder. It now reads the plugin's `manifest.json`
first (a `FileView` on a missing path fails quietly) and loads the client
only when it parses; `voiceCall` falls through to the IPC call as its
fallback, so a hold on the pill degrades to one console line instead of a
scene warning at every start.

**3. `Process failed to start … omamobile-gnss status --json` and
`omamobile-fp-enroll list`.** The sheet's open-refresh scheduler refreshed
every tile backend it knows, including tiles this build dropped from the
catalog, so each sheet open spawned probes for binaries that will never
exist here. The scheduler and each dropped tile's `refresh()` now ask
`TilesModel.known()` first (the catalog is the tablet's, patch 0001), so
location (`omamobile-gnss`), fingerprint (`omamobile-fp-enroll`), torch
(`brightnessctl --device=white:torch`), rotation-lock (the
`omamobile-autorotate` service check) and NFC (`rfkill`) probes never
start. `toggleTile` was already safe: it checks the backend's
`available`, which stays false. The bar's `omamobile-cell-watch` /
`omamobile-call-watch` were already gated by patch 0003's `cellWatch` /
`callWatch` settings (false in the profile).

**4. External commands spawned by shipped code, reviewed one by one:**

| Command | Spawned by | Status |
| --- | --- | --- |
| `omarchy-shell`, `qs`, `omarchy-menu(-clipboard/-emoji)`, `omarchy-capture-screenshot`, `omarchy-notification-send`, `omarchy-theme-(color\|switcher)`, `omarchy-done`, `omarchy-toggle(-idle\|-nightlight)`, `omarchy-hw-display`, `omarchy-bluetooth-power`, `omarchy-launch-floating-terminal-with-presentation`, `omamobile-launch`, `omamobile-osk-watch`, `omamobile-bt-agent`, `omamobile-keyboard-languages`, `omamobile-home` | various | provided by `omarchy` (depends) or shipped in `/usr/bin` (this package) |
| `omamobile-widget`, `omamobile-screenrecord`, `omamobile-set-pin`, `omamobile-screenshot-open/-edit` | shell surfaces | shipped |
| `nmcli`, `iw`, `rfkill` (airplane/Wi-Fi), `busctl`, `systemctl`, `jq`, `wtype`, `hyprctl`, `wf-recorder`, `inotifywait`, `gsettings` | panels, tiles, back gesture, launch, widget watch | in depends (networkmanager, iw, util-linux, jq, wtype, hyprland via omarchy, wf-recorder, inotify-tools) or Omarchy's own |
| `brightnessctl` | brightness slider + torch probe | **moved to depends** (pkgrel 2): the slider is core UI and works here; the torch probe is gated off by the catalog |
| `omamobile-gnss`, `omamobile-fp-enroll` | location/fingerprint tiles | probes removed (issue 3); no shipped code spawns them anymore |
| `omamobile-cell-watch`, `omamobile-call-watch` | bar | gated by `cellWatch`/`callWatch` (false); never spawn |
| `omaphone --in-call` | the bar's call chip | unreachable: the chip shows only while `callWatch` runs, which it never does here |
| `voxtype` | dictation tile probe | tile not in the default layout; the probe itself (`tile-state.sh` `have voxtype`) is a `command -v` check, no spawn |
| `omamobile-voice` | dictation tile action, keyboard Mic key | tile/keys absent (tile droppable via "Add tiles" only); the spawn happens only on a tap of a tile nobody shows |
| `wl-copy`, `notify-send` | OWL widget host (behind `features.json`, off) / screenrecord fallback toast | optional by design; `libnotify` in depends covers `omamobile-notification-send` first |
| `fbcli` | the pill's hold haptic | `command -v`-guarded inside `sh -c` (optdepends feedbackd) |
| `khal`, `playerctl`, `powerprofilesctl`, `hyprsunset` | calendar/media/battery-saver/night-light tiles | optdepends, tiles dim with a reason when absent |
| `gum`, `omarchy-agent-prompt`, `xdg-terminal-exec`, `foot`, `tensaku-edit`, `loupe` | set-pin chooser, agent prompt chain, screenshot fallback | optdepends with reasons; all degrade |
| `timeout`, `bash`, `sh`, `mkdir`, `cp`, `rm` | widget command host, GeoLocation | coreutils/bash (base); always present |
| `omacam` | only via `omamobile-keys` (not shipped) | no shipped code spawns it; optdepends note fixed to say so |

## What changed

`image/pkg/omamobile-shell` moves from the frozen 0.2.94 recipe (upstream
commit 87b8395, "kept for reference only" since the old
`omarchy-mobile/omarchy-mobile` org 404'd) to a real build of upstream
**0.2.133** from `https://github.com/derekross/omarchy-mobile`, pinned at
commit `c4623572be1c141d602cf99a83ae0bf9e3eea09c` with its GitHub tarball
sha256 (`892334c9…ae7bf`) checked by makepkg. The package is built from
source again by `image/tools/build-pkg omamobile-shell`; the
`input/prebuilt/omamobile-shell-0.2.94-5-any.pkg.tar.zst` archive and its
`--assume-installed omatel-agent` workaround in `install-mobile.sh` both
retire (supervisor to-do below).

Upstream 0.2.133 targets Omarchy 4.5.0-3. This image repacks **Omarchy
4.0.6**, so the shell runs against 4.0 — which upstream still supports in
the same release: the dnd read tries 4.5's `isDnd` then 4.0's `dndState`,
the bar reads both notification stores (`history/` files and
`history.json`), `omamobile-reboot` tries both system-command names, and
`omamobile-setup-user` guards the 4.5-only dictation-default step behind
files that exist. Risk to re-test on the unit: the notification shade and
unread count on 4.0.6 (`#482`, `#694` are 4.5-driven but dual-path).

## Design

* **Build = upstream `install` minus what cannot work here, plus three
  patches.** The PKGBUILD still stages files itself (the same explicit loop
  the 0.2.94 recipe used) rather than driving upstream's `./install` into
  `$pkgdir` and deleting: the omitted set is large (6 of 14 plugins, 16 of
  28 bins, hypr/, squeekboard/, portal/, hooks/, two env files, three
  desktop entries, five user units) and a deletion list that big is harder
  to review than an explicit keep-list, and would silently re-ship anything
  upstream adds. The keep-lists (`_plugins`, `_bins`) are the reviewable
  contract, and `check()` asserts the profile names nothing outside them.
* **Two profiles** (`tablet-shell.json`, `tablet-home.json`) are copied over
  `profile/` in `prepare()`, as before. `tablet-home.json` is unchanged
  content (0.2.133's `HomeModel` limits are columns 3-6, rows 4-8; 6x8
  fits), now verified in `check()` through `HomeModel.normalize` so a
  future upstream clamp can't silently move items. `tablet-shell.json`
  regenerates from 0.2.133's `profile/shell.json`: same bar keys plus the
  patch-0003 `cellWatch`/`callWatch` (both false), `idle` kept at
  `{screensaver: 0, lock: 0}` (the tablet has no lock password by default
  and `install-mobile.sh` deletes the screensaver-off toggles), the
  launcher pinned at 6 columns, and `disabledPlugins` extended with
  `omarchy.idle` and `omarchy.remote-session` (both are 0.2.13x upstream
  additions that would otherwise load; `omarchy.idle` reads idle 0 as "act
  immediately" and `omamobile-setup-user` now disables the remote-session
  service for its probes).
* **`omamobile-setup-user` ships upstream-unmodified except one hunk in
  patch 0003** (the idle block it seeds for a user without one is the
  tablet's `{0, 0}`, not the phone's `{0, 60}`). Every other step it takes
  is guarded by `command -v` or file existence, so on this image it degrades:
  no `omatel-agent.service` (never enabled), no voxtype (block skipped), no
  fingerprint menu entry (`when: test -x /usr/lib/omamobile-fp/...` fails,
  so Omarchy's own entry stays), no auto-sleep flag file. The image keeps
  running it once with `--adopt` and then masking the unit, as today.
* **No `omamobile-omarchy` dependency.** Upstream 0.2.133 wants
  `omamobile-omarchy>=0.1.11` for the shade's swipe-to-forget IPC
  (`notifications forget`) and the lock's number pad. This image ships its
  own 0.1.32-era `omamobile-omarchy` built from the same upstream tree
  (patch 0019 there provides `forget`), so the requirement is satisfied in
  substance; declaring the package name would just couple the two recipes
  until M1 lands. Revisit when the sister package moves.
* **`hypr/phone.lua` is not shipped.** It maximizes every window, drops
  Omarchy's gaps, rebinds power/volume keys to `omamobile-keys`, wires
  squeekboard's action-row XF86 keysyms, and layers fingerprint/call
  surfaces above the lock — a phone's ruleset. The image's
  `image/rootfs/tablet.lua` already holds the tablet's (float sizing,
  `osk` layer rules, autorotate). `post_upgrade` therefore reloads no
  Hyprland (upstream reloads because its phone.lua binds change between
  releases; `test/install-hook.sh` in patch 0003 checks nothing runs).

## Per-patch decisions

| Patch (0.2.94 set) | Decision | Where / why |
| --- | --- | --- |
| 0001 tablet quick-settings tiles | **Rebased** onto 0.2.133 | Same catalog surgery (drop mobile-data, hotspot, torch, rotation-lock, location, nfc, fingerprint), same tablet default layout; `test/tiles-model.js` now asserts the tablet catalog (available-list expectations rewritten: spare tiles are `stay-awake, mic, screen-record, dictation`) |
| 0002 Wi-Fi WPA2 without SAE | **Rebased** onto 0.2.133 | Same `iw phy` probe + `nmcliWpa2ConnectArgv` fallback; WifiModel/WifiPanel moved (the nmcli fallback argv is unchanged upstream) and the SAE check now hooks the panel's `open()` the same way; tests ported to `test/wifi-model.js` |
| 0003 tablet quiet pollers | **Rebased, extended** | Watchers half unchanged in intent: `cellWatch`/`callWatch` bar settings gate the two Processes (upstream still starts them unconditionally at 0.2.133). Dnd half rewritten: upstream's read is now `isDnd`-then-`dndState` over IPC, so the toggles instead watch Omarchy 4.0's `notifications.json` **and** 4.5's `notifications/quiet.json` (both files, whichever exists), still with no poll. Also adapts `test/setup-user.sh` (idle block, disabledPlugins list) and `test/install-hook.sh` (no reload), and seeds the tablet idle block in `omamobile-setup-user` |
| 0004 tablet phone leftovers (new, pkgrel 2) | **Added** | Setup-user gates + cleanup, the conditional voice link, catalog-gated tile probes — see the follow-up section |
| Sister 0004 tablet modem | **Dropped — no modem** | The YT-J706F is Wi-Fi-only; upstream's mobile-data tile is driven by `omamobile-sit`, which is not built here. The tile stays out of the catalog (patch 0001) |
| Sister 0005 tablet rotation | **Dropped — not needed** | Its Rotation-lock tile targets `omamobile-autorotate` (omamobile-sensors); this image auto-rotates with its own `yt11-autorotate` from `tablet.lua`, and a manual Rotate tile is unnecessary when rotation is sensor-driven and working. Re-adding a hand-rotate tile is a follow-up if the owner wants it |
| Sister 0006 tablet mobile settings | **Dropped — no modem** | Opens the SM-T715's "Réseau mobile" (`t715-mobile-settings`); nothing to open here |
| Sister 0007 tablet tiles that work | **Dropped — modem/hotspot/speaker specific** | Airplane-mode-plus-modem, Hotspot-with-password and the call-card Speaker toggle all need the SS333 modem or a call card; the Wi-Fi/Bluetooth rfkill airplane tile upstream provides is complete on this tablet |
| Sister 0008 tablet set-pin | **Dropped — upstream wording is fine** | Only renamed "phone" to "tablet" in prompts and flipped sudo policy; the sudo policy lives in this image's overlay already, and the prompt text is upstream's to carry. Re-add locally if the owner wants "tablet" in the PIN dialog |
| Sister 0009 tablet back gesture | **Dropped — upstream fixed it** | Upstream 0.2.116 (`f0c9b7a`) sends Escape **by key code** (`code:9`) precisely because the by-name dispatch failed the same way ("key not found", Hyprland 0.57), and prefers `wtype -k Escape`, which reaches the app; `depends` gains `wtype`. The `t715-keys` fallback is no longer needed |
| Sister 0010 tablet location tile | **Dropped — no GNSS** | The tile drives `omamobile-gnss`; the tablet has no driven GNSS |
| Sister 0011 tablet modem tile | **Dropped — no modem** | `t715-modem-power` switches the SS333's CP; nothing to switch |
| Sister 0012 tablet sdcard tile | **Dropped — no user-visible slot** | The YT-J706F has no microSD slot (its only removable storage is USB); a tile over `t715-sdcard` would always read "no card" |

## Per-omission decisions (upstream `install` output not shipped)

| Piece | Why omitted |
| --- | --- |
| plugins `omamobile.call`, `omamobile.mobilenetwork` | No modem, no omatel; the call card dials through omaphone |
| plugin `omamobile.fingerprint` + `bin/omamobile-fp-enroll` | No fingerprint sensor (the manifest targets the under-display Pixel sensor) |
| plugin `omamobile.update` + `applications/omamobile-update.desktop` | Needs `omamobile-update` from `omamobile-omarchy` ≥ the 4.5 wrapper; this image updates by reflash (IgnorePkg pins omamobile-shell itself) |
| plugin `omamobile.access`, `bin/omamobile-portal-access`, `portal/*`, its unit, `xdg-desktop-portal-gnome-omamobile.conf` | The permission sheet is a portal backend choice; this image keeps Omarchy's stock portals (and would need xdg-desktop-portal-gnome for the file chooser half, which the image does not install) |
| plugin `omamobile.voice`, `bin/omamobile-voice`, `-voice-preview` | Voxtype daemon + speech model not shipped; the Dictation tile degrades to "Not installed" and is not in the default layout |
| `bin/omamobile-call-watch`, `-cell-watch` | Modem watchers; the bar starts them only behind `cellWatch`/`callWatch` (false) per patch 0003 |
| `bin/omamobile-nfc-open` + system unit | No NFC controller driven |
| `bin/omamobile-keys` | Pixel power/volume semantics (short-press lock, chords, camera shutter through omacam, Android power key behind `OMAMOBILE_POWER_KEY_ANDROID`). The tablet keeps logind's power key and Omarchy's own volume handling |
| `bin/omamobile-sleepd`, `-doubletap`, their units | Phone sleep/wake daemons: sleepd encodes the phone's suspend policy (and is wired to omamobile-keys' power path), doubletap needs omamobile-keys and turns Hyprland's wake-on-touch off — the tablet wants touch-to-wake. The tablet suspends via the system menu (s2idle verified, docs/hardware/BOARD.md) |
| `bin/omamobile-onboarding` | First-run SIM/fingerprint/identity prompts; the image provisions the user itself |
| `bin/omamobile-open-intent`, `applications/omamobile-open-intent.desktop` | Android intent links |
| `bin/omamobile-weather` + service/timer | Lock-glance weather whose GeoClue path expects `omamobile-gnss`'s socket/agent; not shipped. (The home screen's weather widget is separate: it fetches by itself and is kept.) |
| `bin/omamobile-mobile-network` | omamobile-sit client |
| `bin/omamobile-reboot` | Only the update sheet's and mobile-network page's Restart buttons call it; both are not shipped |
| `bin/omamobile-osk-guard` + unit | Safety net for the phone's screensaver-keyboard dance (omamobile-omarchy patch 0006 paths); this image runs Omarchy stock with the screensaver off and `squeekboard` started by its own unit |
| `hypr/phone.lua` | See design above (tablet.lua replaces it) |
| `squeekboard/keyboards/*`, `squeekboard/generate`, `bin/omamobile-keyboard-theme`, `hooks/theme-set-keyboard` | The image ships its own terminal layouts (with Esc) under `/usr/share/lenovomarchy` and links them per user; upstream's layouts replace squeekboard's own per-language layouts to add the phone's action row (Mic/Paste/Emoji/Hide + globe), which only makes sense with phone.lua's binds. The keyboard plugin's show/hide/language-sheet IPC works with squeekboard's own layouts; `omamobile-keyboard-languages` is shipped (it talks to gsettings + the keyboards dir, and squeekboard's popover stays available) |
| `environment.d/20-omamobile-osk.conf` | The image's `/etc/environment.d/20-lenovomarchy-osk.conf` already sets `GTK_IM_MODULE=wayland`, `QT_IM_MODULE=wayland`; fcitx5 is skipped in this image so there is nothing to override; the portal-env vars belong to the portal choice we don't change |
| `systemd/user/omarchy-fcitx5-omamobile.conf` | fcitx5 not installed |
| `applications/omamobile-agent.desktop` | Opens Omarchy's agent picker; the tablet's drawer gets it from Omarchy itself when an agent is installed (judged phone-side branding; re-add if wanted) |
| depends `omamobile-apps` | Pulls the dialer (omaphone), Messages (omamessages + omatel-agent), gnome-maps + geoclue, neard, omacam, loupe, omamobile-settings — mostly unusable or unwanted here; loupe is already an image package |

Kept from upstream unchanged: `omamobile-setup-user` (patched once), `-launch`,
`-home`, `-osk-watch`, `-bt-agent`, `-screenrecord`, `-widget`,
`-keyboard-languages`, `-set-pin`, `-screenshot-open`/`-edit` +
`environment.d/30-omamobile-screenshot.conf`, the polkit admin-self rule,
`branding/`, `widgets/` guides + template + examples, the seven plugins'
QML/JS, `omamobile-setup-user.service` (+ its vendor wants link).

## depends / optdepends on the tablet

`depends`: `omarchy>=4.0.6` (host shell, all `omarchy-*` helpers), bash,
python, python-dbus, python-gobject (osk-watch, bt-agent,
keyboard-languages, widget, launch), squeekboard (the OSK + sm.puri.OSK0),
quickshell (the `qs` IPC binary the toggles and shade call by name),
qt6-declarative, bluez + bluez-utils (BT panel, rfkill), networkmanager +
iw (Wi-Fi panel + the SAE probe), util-linux (busctl), jq (BackModel,
launch), inotify-tools (user-widget watch), wtype (back-gesture Escape),
wf-recorder (screen record), libnotify (screenrecord toast fallback).

`optdepends` with the reason in the PKGBUILD: loupe (installed by the
image), khal, playerctl, power-profiles-daemon, hyprsunset, omacam,
omamobile-settings, omamobile-owl-widgets, gum, foot, xdg-terminal-exec.
Home-screen widgets degrade to a message without their helper; no plugin
fails to load.

The shell does **not** break without `omamobile-owl-widgets`: the OWL
built-ins are behind `~/.config/omamobile/features.json` `{"owlWidgets":
true}`, off by default, and the built-in QML widgets (clock, weather,
battery, media, agenda, note, toggles, command) don't touch it.

## What the user sees change, 0.2.94-5 → 0.2.133-1

From upstream's `packages/omamobile-shell` log (87b8395..c462357), keeping
what reaches this tablet (its plugins and bins only):

* Home/drawer/launcher: fluid open/close gestures following the finger
  (0.2.56), wide-cell icons sized properly (0.2.72), widgets paused when
  not visible (0.2.44-0.2.52 line), a widget crash guard with one retry
  (0.2.66), the home strip reserving its height under the keyboard and over
  the drawer (0.2.113).
* Quick settings: stable notification viewport while sliding (0.2.109),
  staggered backend refreshes at open (0.2.110), media card with album art
  in the shade (0.2.74), Omarchy 4.5 notification-store support (0.2.125,
  0.2.127 — dual-path with 4.0).
* Back gesture: Escape sent by key code and through wtype (0.2.116), the
  armed tick (0.2.111), one-level-back panels (0.2.117: Wi-Fi/Bluetooth
  panels go back to the sheet, "Show with…" to its menu).
* Switcher: the user's card survives a window close (0.2.105).
* Bar: the battery's reported state (0.2.104), unread count over both
  notification stores (0.2.125).
* Setup: `omamobile-setup-user --adopt` (0.2.67) — already used by the
  image, now genuinely upstream; single-tap folders in Files and the
  no-wait file-chooser fix are phone-portal features not shipped here.
* Transparency on Hyprland 0.57 fixed (0.2.79) — relevant when the image
  moves to 0.57.
* The removed prebuilt archive also means the package stops pretending to
  be 0.2.94-5 with a modem dependency.

Not seen here (phone-side): voice/dictation stack, fingerprint, modem/SIM,
NFC, sleep/double-tap/power-key work, update sheet, onboarding, lock glance
weather, keyboard layouts/action row/theming.

## Risks

* **Omarchy 4.0.6 vs upstream's 4.5 target.** The shell's 4.0 code paths
  are still present, but they get less upstream testing now. The shade's
  notification reading (`history/` files) and the dnd IPC read are the ones
  to watch on the unit.
* **Back gesture via wtype.** New hard dependency, new mechanism (a virtual
  keyboard per keypress). If Escape misbehaves on the tablet's Hyprland
  0.5x, BackModel keeps the `send_key_state` dispatch fallback.
* **`omamobile-setup-user` at 0.2.133 writes more Omarchy menu extensions**
  (hide rows, PIN row, mobile-network/voice rows gated by file tests). On
  4.0.6 the extension file ids that don't exist are inert, but the menu
  extension file gains entries; the image's `--adopt` + mask flow means
  they land once, at image build.
* **`disabledPlugins` additions** (`omarchy.idle`, `omarchy.remote-session`)
  exist at Omarchy 4.0.6? `omarchy.idle` does (it's the idle service
  plugin); `omarchy.remote-session` was added later — listing an unknown id
  is harmless (the host ignores names it doesn't know; upstream's own setup
  adds it unconditionally on 4.0 phones too).
* **tile-scripts test on macOS**: `tile-state.sh` needs `timeout`; the
  check runs in the build container only, not on the Mac host.
* The upstream tarball is fetched by sha-named URL; a future upstream force
  push cannot change it, but `version` inside is asserted in `prepare()`.

## Supervisor to-do (files I did not touch)

1. `image/build-rootfs.sh`: drop `omamobile-shell-0.2.94-5` from the
   required-inputs list and the `input/prebuilt/` copies (keep
   `omamobile-omarchy-0.1.32-1.2` until M1 lands); the local repo now gets
   the shell from `image/tools/build-pkg omamobile-shell`.
2. `image/rootfs/install-mobile.sh`: drop the
   `--assume-installed omatel-agent=0.2.1` workaround (the new package has
   no omatel dependency); keep `omamobile-setup-user --adopt` and the
   mask. Its `rm -f … omamobile.call` plugin cleanup can stay (it removes
   stale links from the 0.2.94-era prebuilt, which shipped the call plugin
   linked into `~/.config/omarchy/plugins`; with 0.2.133 the link targets
   don't exist and Quickshell would log a load failure for each — actually
   `omamobile-setup-user` re-links only what exists, but stale links from
   the old image persist, so keep the `rm -f` block until the unit is
   reflashed clean).
3. `image/rootfs/install-mobile.sh` and `omarchy-user-setup.sh`: nothing
   else required — `omamobile-setup-user --adopt` marks the profile-gated
   steps done, so monitors.lua scale 1.5 and the cursor stay as the image
   set them. (If the 0.2.94 prebuilt had been run on the unit before: the
   once-only markers under `~/.local/state/omarchy/done/` persist across
   the upgrade; the new steps run at the first post-upgrade login, and the
   unit masks that service after `--adopt` at image build — on an in-place
   upgrade of a running tablet, run `omamobile-setup-user` once by hand.)
4. `image/rootfs/packages.extra` / `packages.mobile`: no change needed;
   `dnsmasq` is already there, `wf-recorder` and `loupe` too. `wtype`,
   `inotify-tools`, `jq`, `libnotify`, `iw` are new runtime deps — they
   come in automatically as package dependencies; nothing to add by hand.
5. `image/rootfs/smoke-check.sh`: it greps the package list only; fine as
   is.
