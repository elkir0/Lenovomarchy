# M3: Omarchy 4.5.0-3's 98 pending migrations triaged for the tablet

Date: 2026-11-17 · Scope: the 98 migrations `omarchy-migrate --pending`
lists for `alarm` after the upgrade to Omarchy 4.5.0-3 (see
`out/rehearsal/run2.log`). Every script was read from the 4.5.0-3 package
(`out/rehearsal/omarchy-4.5.0-3-aarch64.pkg.tar.zst`) together with the
helpers it calls (`omarchy-pkg-add`, `omarchy-mise-install`, `omarchy-hw-*`,
`omarchy-bar`, `omarchy-shell`, `omarchy-theme-*`, …). Package availability
was checked against the tablet's actual repositories (`[core] [extra]
[alarm] [aur]`, no `[omarchy]`) with `pacman -Si` in the rehearsal
container.

Deliverables: `image/rootfs/omarchy-migrations.hold` (the HOLD list; the
image build must install it as `/usr/share/lenovomarchy/omarchy-migrations.hold`)
and `image/overlay/usr/local/bin/yt11-omarchy-migrations-hold` (applies the
holds as the user; not wired into the build — the supervisor decides when).

## Verdicts

| Class | Count | Meaning |
|---|---|---|
| RUN | 33 | harmless or wanted; ran green in the container (or fails only there for lack of systemd/session/hardware) |
| NOOP | 40 | guards itself and does nothing on this tablet (guard named below) |
| HOLD | 25 | must not run here (marked done without running) |

RUN 33 + NOOP 40 = 73 migrations `omarchy-migrate` executes (the NOOPs run
and self-exit — that is what the container rehearsal's 73 "Running
migration" lines are); the 25 HOLDs are removed from its queue beforehand
by `yt11-omarchy-migrations-hold`. Of the 73, one (1791769486) fails in the
container only (no user bus) and completes on the booted tablet.

Notes on two class boundaries:

* mise is **not installed** on the tablet (no `mise`, no `~/.local/bin`
  wrappers, `omarchy-mise-install` writes a wrapper that calls a missing
  binary). Migrations that *write* such wrappers are HOLD (broken artifact);
  migrations that *run* `mise` are HOLD (they would fail the chain);
  migrations that only loop over `~/.local/bin` find nothing and are NOOP.
* fcitx5 is deliberately not installed (squeekboard is the tablet's input
  method; `packages.omarchy-skip` drops fcitx5). Anything configuring fcitx5
  is HOLD or NOOP, never RUN.

## Full table (98)

First line = the migration's own `echo`. Class reasons cite the script.

| Migration | First line | Class | Reason / evidence |
|---|---|---|---|
| 1786609204 | Native video dependencies are superseded by the OWE migration | RUN | body is the echo only; changes nothing |
| 1786719479 | Replace the Gemini coding agent with Antigravity | HOLD | `omarchy-mise-install antigravity-cli agy` writes a wrapper calling absent mise; unreviewed agent CLI. Loses: nothing the tablet had (gemini never installed) |
| 1786967403 | Install Kimi coding agent mise wrapper | HOLD | mise wrapper, no mise; also symlinks agent skills (harmless) but the wrapper is a broken command |
| 1787215824 | Install hey (hey-cli) via mise wrapper | HOLD | mise wrapper, no mise |
| 1787342993 | Install ori (OpenRouter's agent harness) via mise wrapper | HOLD | mise wrapper, no mise |
| 1787573629 | Regenerate mise wrappers that still print mise's own output to stdout | NOOP | loops `~/.local/bin/*`, finds nothing (dir absent); `[[ -d $bin_dir ]] || exit 0` |
| 1787666837 | Enable Dell XPS 13 sidecar speaker amplifiers | NOOP | guard `omarchy-hw-dell-xps13-sidecar-amps` (DMI match DX13260; no DMI on this DT tablet) |
| 1787679775 | Drop saved workspace layouts belonging to named workspaces | RUN | deletes `workspace-layouts/-*.lua` if any; none exist, `hyprctl reload` is `|| true` |
| 1788129995 | Replace Satty and Tensaku with Omasnap | HOLD | `omarchy-pkg-add omasnap` → target not found (pkgs.omarchy.org only; proven in container). Loses: Omasnap screenshot editor |
| 1788163635 | Remove legacy temporary passwordless sudo grants | RUN | helper `omarchy-sudo-passwordless __migration-complete` answers done (no `99-omarchy-nopasswd-*` grants exist; tablet's wheel-NOPASSWD file is `10-wheel`, untouched by it) |
| 1788256455 | Restore polkit brute-force protection … | NOOP | `[[ -f /etc/pam.d/polkit-1 ]]` false — file does not exist on the tablet |
| 1788261467 | Expose GNOME Keyring to sandboxed apps through the Secret portal | RUN | writes `~/.config/xdg-desktop-portal/hyprland-portals.conf` (Secret portal → gnome-keyring); no session restart needed in container (guarded by `systemctl --user is-active`) |
| 1788279117 | Replace the YT6801 vendor DKMS driver with the upstream kernel driver | NOOP | `lspci -Dn -d 1f0a:6801` finds nothing (empty list → zero pending devices → no-op); guard proven in container run |
| 1788281348 | Re-stage the active theme with packaged intro videos | RUN | no-op here (`~/.local/state/omarchy/current/theme.name` absent on 4.0.6 image; the state-move migration 1781043107 that creates it is already marked done on this install); exits 0 |
| 1788595060 | Register the Chromium extension native messaging hosts for Brave Origin | HOLD | writes Brave-Origin config dirs for a browser that is not and cannot be installed (AUR-only). No loss |
| 1788596255 | Add vi as a standard terminal editor | RUN | `omarchy-pkg-add vi` resolves to `ex-vi-compat` (provides `vi`) in [extra]; already installed → `--needed` skips |
| 1788862626 | Expose the Elgato Cam Link 4K as a 16:9 virtual camera | NOOP | guard `omarchy-hw-elgato-camlink-4k` reads `/sys/bus/usb/devices/*/product` |
| 1788941927 | Install basecamp (basecamp-cli) via mise wrapper | HOLD | mise wrapper, no mise |
| 1789294350 | Switch TCP congestion control to BBR with fq pacing | RUN | reads current sysctls (fails in container: read-only /proc/sys → falls to `omarchy-state set reboot-required`, exit 0). On the tablet: `sudo sysctl -p /etc/sysctl.d/99-omarchy-sysctl.conf` applies BBR now. Wanted |
| 1789310715 | Install cf (Cloudflare CLI) via mise wrapper | HOLD | mise wrapper, no mise |
| 1789764927 | Enable OWE desktop video backgrounds and lock feed | HOLD | `omarchy-pkg-add owe owe-lockfeed` → target not found (proven in container). Loses: video wallpapers |
| 1789928586 | Retain the installed ARM Limine recovery packages during orphan cleanup | NOOP | guard `[[ $(uname -m) == aarch64 && -f /etc/default/limine ]]` — no `/etc/default/limine` on the tablet |
| 1790042972 | Put Elsewhen, the world clock, on the bar | HOLD | `omarchy-bar put omarchy.elsewhen` targets the omarchy bar; the tablet runs the omamobile bar (`shell.json` `bar.id: omamobile.bar`). Upstream Omarchy Mobile holds it too ("the phone has its own status bar") |
| 1790364978 | Disable system sleep on GB10 machines, as DGX OS does | NOOP | guard `omarchy-hw-aarch64-gb10 || exit 0` |
| 1790457067 | Loosen the offline install's exact Node pin | NOOP | `~/.config/mise/config.toml` absent |
| 1790517230 | Boot the DGX Spark without a UKI | NOOP | guard `omarchy-hw-aarch64-gb10 && omarchy-hw-match "NVIDIA_DGX_Spark"` |
| 1790528634 | Move Elsewhen … into Omarchy as omarchy.elsewhen | RUN | renames in shell.json (no match: empty sections), drops absent plugin dir, `omarchy-pkg-drop elsewhen` no-ops (not installed) |
| 1790539857 | Install Monologue, the webcam recorder | HOLD | `monologue` target not found (container-proven; pkgs.omarchy.org only). Loses: Monologue (tablet has omacam) |
| 1790542069 | Install Hype, the Markdown presentation app | HOLD | `hype` target not found (container-proven). Loses: Hype |
| 1790702362 | Install the compiler and Qt pieces for building Omarchy-style apps | HOLD | `base-devel` + full Qt6 dev stack from ALARM — installs, but hundreds of MB for a feature (building Omarchy-style apps) nobody uses on the tablet. Held as policy, not availability |
| 1790702606 | Link the omarchy-app agent skill for building apps | RUN | symlinks `$OMARCHY_PATH/default/agents/skills/omarchy-app` into skill dirs; the skill ships in omarchy-settings (verified) |
| 1790863209 | Install Grok through mise's first-party package | HOLD | `omarchy-mise-install grok` writes a broken wrapper (no mise) |
| 1790917415 | Make the ASUS ProArt P14 (NVIDIA N1x) touchpad register touches | NOOP | guard `omarchy-hw-match "H7407BA"` (DMI) |
| 1790917571 | Route ASUS ProArt P14 … speakers, headphones and microphones | NOOP | guard `omarchy-hw-match "H7407BA"` |
| 1790917620 | List Omarchy's aarch64 repository ahead of ALARM's on the N1x | NOOP | guard `omarchy-hw-aarch64-n1x`; also would rewrite pacman.conf (why holding would also be fine) |
| 1790917773 | Boot N1x laptops quietly … | NOOP | guard `[[ -f /etc/limine-entry-tool.d/00-omarchy-n1x-console.conf ]]` |
| 1790950659 | Light the N1x panel for Plymouth's LUKS prompt | NOOP | guard `[[ -f …/00-omarchy-n1x-gpu.conf ]]` |
| 1790953795 | Give the ASUS ProArt P14 … the RAM its firmware reserves | NOOP | guard `omarchy-hw-match "H7407BA"` |
| 1790973240 | Give the ASUS ProArt P14 … speakers ASUS's amplifier tuning | NOOP | guard `omarchy-hw-match "H7407BA"` |
| 1790984400 | Give the Dell XPS 16 (NVIDIA N1x) the RAM … | NOOP | guard `omarchy-hw-match "DX16263"` |
| 1790984500 | Give the N1x swap on zram … | NOOP | guard `omarchy-hw-aarch64-n1x` |
| 1790984600 | Turn on USB4 and Thunderbolt on the N1x | NOOP | guard `omarchy-hw-aarch64-n1x` |
| 1790984700 | Leave the N1x GPU firmware room below its memory | NOOP | guard: drop-in file absent |
| 1791077437 | Move NVIDIA N1x laptops to linux-omarchy-n1x … | NOOP | guard `omarchy-hw-aarch64-n1x || exit 0` (first line of body) |
| 1791080527 | Enable desktop camera access on Snapdragon ThinkPad T14s Gen 6 | NOOP | guard `omarchy-hw-aarch64-qualcomm && omarchy-hw-match '^21N[12]'` |
| 1791112479 | Make agent account selection apply to scripts and subprocesses | HOLD | body is `mise reshim` → `mise: command not found` (container-proven failure); would abort the chain |
| 1791123731 | Add an example for opting applications in to transparency | RUN | appends a comment block to `~/.config/hypr/looknfeel.lua` (file exists) |
| 1791125650 | Install the fingerprint resume hook on existing fingerprint setups | NOOP | guard `[[ -f /etc/pam.d/omarchy-lock-fingerprint ]]` — not present (image uses the password lock stack; omamobile's lock-pam writes only `omarchy-lock-password`) |
| 1791134093 | Keep the ASUS ProArt P14's USB4 tunnel root ports awake | NOOP | guard `omarchy-hw-aarch64-n1x && omarchy-hw-match "H7407BA"` |
| 1791147791 | Answer ARP only for each interface's own address | RUN | applies `/etc/sysctl.d/90-omarchy-arp.conf` (shipped by omarchy-settings; exists) via `sudo sysctl -p`; container fails read-only → falls to reboot-required, exit 0; on tablet applies arp_ignore/arp_announce |
| 1791152480 | Drop the N1x rescue entry and pacman hook | NOOP | guard `[[ -f /etc/pacman.d/hooks/zz-omarchy-n1x-rescue.hook ]]` |
| 1791345484 | Replace the Disk Usage TUI with Disktree | HOLD | `disktree-bin` target not found (container-proven). Keeps dua-cli (RUN 1780739888's predecessor already installed it) |
| 1791367434 | Configure shared input-method defaults and free desktop shortcuts | HOLD | installs the fcitx5 CJK stack (mozc/hangul/chinese/chewing — available in ALARM but ~1 GB of input engines the tablet cannot use: no keyboard, squeekboard is the IME) and runs `omarchy-input-method configure --defaults`, which writes fcitx5 profile/hotkey config. Upstream Omarchy Mobile holds fcitx migrations on phones for the same reason |
| 1791376887 | Enable overlay scrollbars in Chromium-based browsers | RUN | appends `--enable-features=OverlayScrollbar` to existing `~/.config/chromium-flags.conf` |
| 1791382872 | Switch default mise tools to native lazy shims | HOLD | guard passes (`/etc/mise/conf.d/omarchy-tools.toml` ships with omarchy-settings) then runs `mise reshim --system` → command not found → chain aborts (container-proven) |
| 1791403310 | Install titlebars for floating workspaces | HOLD | `omarchy-hyprland-titlebars` target not found; upstream holds it as "pinned to a different Hyprland build" (the tablet runs ALARM hyprland 0.57.2, not Omarchy's) |
| 1791408113 | Make the ASUS ProArt P14 keyboard's top row send media keys | NOOP | guard `omarchy-hw-match "H7407BA"` |
| 1791470456 | Repair background selections after bundled images moved to WebP | RUN | current background link resolves (jpg still exists) → nothing to rewrite; exits 0 either way |
| 1791479273 | Preserve Voxtype as the default for existing dictation users | RUN | guard: `voxtype-bin` not installed, no defaults file written; no-op that self-guards |
| 1791542175 | Install Gliff, the Hyprland remote desktop over SSH | NOOP | guard `omarchy-hw-x86` (uname -m == x86_64); prints nothing, installs nothing |
| 1791554699 | Switch to Omarchy's power-profiles-daemon build with CPPC support | HOLD | `sudo pacman -S omarchy-power-profiles-daemon` → target not found (container-proven). The tablet's stock power-profiles-daemon 0.30 stays; MT6785's cpufreq is cpufreq-dt, not cppc_cpufreq, so Omarchy's CPPC build would gain nothing anyway |
| 1791640449 | Move the keyboard layout widget to the right side of the bar | RUN | `omarchy-bar move … || true`; no omarchy clock/keyboard widgets on the omamobile bar; harmless. (Doubtful-value list below) |
| 1791676907 | Let a lone Shift switch out of an input method and back | RUN | guard: `~/.config/fcitx5/config` exists (created by 4.0.6 squeekboard-era config? verified present) but the awk predicate requires an *empty* `[Hotkey/AltTriggerKeys]` section — not present → no write. No-op in practice; keyboard-only feature anyway |
| 1791696584 | Name web app windows in their launchers … | RUN | loops `~/.local/share/applications/*.desktop` for `Exec=omarchy-launch-webapp` entries; none on the tablet → no writes |
| 1791698594 | Save workspace layouts as modes … | RUN | rewrites `workspace-layouts/*.lua` files; none exist |
| 1791705142 | Keep windows opaque where animations are turned off | RUN | touches `toggles/hypr/no-animations.lua` only if present; it is not (only lock-keypad/suspend-off/stay-awake exist) |
| 1791708587 | Install Signed, the PDF signing app | HOLD | `signed` target not found (container-proven; pkgs.omarchy.org only). Loses: PDF signing app |
| 1791722809 | Let herdr's tab bar show the terminal's background | RUN | guard `~/.config/herdr/config.toml` — herdr not installed → no-op |
| 1791723398 | Let Neovim's current line and status line show the terminal background | RUN | `omarchy-nvim` 2026.9.21-5 installed (satisfies the version gate); copies transparency files into `~/.config/nvim` |
| 1791769486 | Remove approval for new USB and Thunderbolt devices | RUN | fails in the container only at `systemctl --user daemon-reload` (no user bus: `$DBUS_SESSION_BUS_ADDRESS and $XDG_RUNTIME_DIR not defined`). On the tablet the user manager exists; every substantive guard (`$tb_dir`, usbguard, drop-ins) is absent → it only reloads units and removes nothing. Wanted: it is the cleanup path for a retired Omarchy feature |
| 1791784278 | Have the N1x firmware reserve 4 GiB for the GPU … | NOOP | guard `omarchy-hw-aarch64-n1x || exit 0` |
| 1791867831 | Turn on CPPC autonomous frequency selection on the N1x | NOOP | guard `omarchy-hw-aarch64-n1x || exit 0` |
| 1791875754 | Name web app windows in launchers that run their own command | RUN | loops applications/*.desktop; no matching Exec lines → no writes |
| 1791898365 | Speed up the boot menu and keep it quiet until a key is pressed | NOOP | guard: `/etc/default/limine` unreadable → `limine_conf=/boot/limine.conf` absent → `sudo test -f` false → exit 0 (container-proven). No Limine on this tablet (Android LK boot image) |
| 1791968925 | Write the bar's tray where the bar drew it | RUN | jq predicate requires `bar.id` "" or "omarchy.bar"; tablet's is "omamobile.bar" → skip (deliberate: replacement bars keep their layout) |
| 1791969355 | Split the bar's center section at its anchor … | RUN | predicate requires `bar.centerAnchor`; absent → skip |
| 1792020559 | Theme the Fcitx candidate window with the current Omarchy theme | HOLD | `omarchy-theme-set-fcitx5 --activate` would write `~/.local/share/fcitx5/themes/omarchy` + classicui.conf for an input method the tablet does not run; stray config for nothing |
| 1792041364 | Install Gliff on aarch64 | HOLD | `gliff` target not found in ALARM (container-proven; Omarchy's repo builds it, ours doesn't have it). Loses: Gliff remote desktop |
| 1792202836 | Let mpv and Chromium decode video on the video chip of Snapdragon laptops | NOOP | guard `omarchy-hw-aarch64-qualcomm` inside `omarchy-install-video-decode`; MT6785 is plain aarch64 → exit 0 (container-proven: ran green doing nothing) |
| 1792259038 | Keep background selections across renumbered bundled backgrounds | RUN | renumbered-source matcher finds no match (background still exists as .jpg) → no writes |
| 1792343099 | Leave Node to Omarchy's mise declaration | HOLD | guard passes (`omarchy-mise-default-tools declares node` reads /etc/mise/conf.d) then `mise unuse` → command not found → chain aborts (container-proven) |
| 1792343225 | Leave mise's upgrade pruning setting to Omarchy's config | NOOP | guard `[[ -f $mise_config ]]` — `~/.config/mise/config.toml` absent |
| 1792345511 | Replace the T3 Code package with the T3 Code app | NOOP | guards: neither `t3code-nightly-bin` nor `t3code-bin` installed → exit 0 |
| 1792359308 | Let Chromium use the cameras of Snapdragon laptops through PipeWire | NOOP | guard `omarchy-hw-aarch64-qualcomm` (container-proven no-op). The tablet's camera path is our own libcamera/pipewire-libcamera work |
| 1792474908 | Repair the Copy URL shortcut for Brave Origin profiles | RUN | profile roots under `~/.config/BraveSoftware/Brave-Origin*` absent → `find_pending` empty, no backups → exit 0 |
| 1792504295 | Build the lazy shims for the newly declared default coding agents | HOLD | guard passes (`qwen` is declared in /etc/mise/conf.d/omarchy-tools.toml) then `mise reshim --system` → command not found → chain aborts (container-proven) |
| 1792507034 | Check network connectivity against ping.omacom.io | RUN | body: `systemctl is-active NetworkManager` fails in container → nothing; on the tablet NM is active → `sudo nmcli general reload conf` (harmless reload; the connectivity drop-in ships with omarchy-settings). Wanted |
| 1792634594 | Clear SoundWire routes … N1x UCM profiles | NOOP | guard `omarchy-hw-aarch64-n1x` |
| 1792648436 | Remove the files the 4.0 notification engine left behind | RUN | upstream Omarchy Mobile reviewed and released this one (`RELEASED` in its own test): deletes 4.0 notification state the 4.5 shell never reads; carries DND over if set |
| 1792965062 | Name the hibernation resume device by its filesystem UUID | NOOP | guards: `/etc/limine-entry-tool.d/resume.conf` absent and no pending marker → exit 0 (no hibernation on the tablet) |
| 1793069744 | Recheck FIDO2 authfile paths previously marked repaired | NOOP | sources 1787494718: `/etc/fido2` absent, `[[ ! -d $authdir || -x $authdir ]]` → exit 0 (container-proven: prints its echo then exits clean) |
| 1793315076 | Load Omarchy's shell setup on Apple Silicon | NOOP | guard `omarchy-hw-aarch64-apple` (device-tree `apple,*`) |
| 1793452544 | Install Intel hardware video decoding … | NOOP | guard `lspci | grep … [intel graphics` — no Intel GPU (container-proven no-op; MT6785 has no PCI at all) |
| 1793477875 | Move dictation to Alt + Space … | RUN | guard `omarchy-default-dictation` fails (no defaults file) → skips the bindings block; superwhisper absent → done. No-op in practice; flagged below as keyboard-only |
| 1793512402 | Install xorg-xsetroot for X11/XWayland root cursor restoration | RUN | `omarchy-pkg-add xorg-xsetroot` — available in [extra] (container-proven install); fixes XWayland root cursor |
| 1793531426 | Keep GB10 CPU cores out of deep idle states | NOOP | guard `omarchy-hw-aarch64-gb10 || exit 0` |
| 1793565796 | Open OpenCode 2 with the Omarchy theme | RUN | `~/.config/opencode/cli.json` absent and config dir absent → writes nothing (the `elif` requires the dir); no-op in practice |
| 1793667581 | Finish Superwhisper setup … | RUN | guard `omarchy-default-dictation` != superwhisper (fails, unset) → no-op in practice |

## Container rehearsal (out/rehearsal step extended: `/tmp` script `step-m3.sh`)

Sequence (in `lenovomarchy-rootfs:aarch64`, same EXDEV workaround as
`step.sh`): mobile packages → omarchy 4.5.0-3 → install hold list +
`yt11-omarchy-migrations-hold` → run twice as `alarm` → `omarchy-migrate`
as `alarm`, marking container-only failures done and restarting, until the
queue drains.

* `yt11-omarchy-migrations-hold` run 1: `held` × 25, `rc=0`; pending 98 → 73.
* run 2: every line `held … (already held)`, `rc=0`; pending stays 73 (idempotent).
* `omarchy-migrate` ran 73 migrations; **one** container-only stop:
  * `1791769486` — `systemctl --user daemon-reload` → "Failed to connect to
    user scope bus … `$DBUS_SESSION_BUS_ADDRESS` and `$XDG_RUNTIME_DIR` not
    defined". Evidence it passes on the tablet: every substantive branch is
    gated on files/units the tablet does not have (`/var/lib/omarchy/thunderbolt-authorization`,
    `usbguard` not installed, `/etc/limine-entry-tool.d/usb-authorization.conf`
    absent, `/etc/default/limine` absent); what remains is unit cleanup under
    a live user manager, which exists on the booted tablet. Marked done in the
    rehearsal only, with a comment; not added to the hold list.
* sysctl-based RUN migrations (1789294350 BBR, 1791147791 ARP) print
  `permission denied` in the container (read-only `/proc/sys`), take their
  `omarchy-state set reboot-required` fallback and exit 0 — on the tablet
  the `sudo sysctl -p` path applies the shipped files for real.
* Final `omarchy-migrate --pending | wc -l` as `alarm`: **0**. Every one of
  the 98 is held (25) or executed by omarchy-migrate (73 = 33 RUN with
  effect + 40 NOOP by their own guards), the one container-marked
  (1791769486) being inside the 73.

Log: kept at `out/rehearsal/m3-run.log` (copy of the container transcript).

## Packages the RUN migrations install from Arch Linux ARM

Verified installed in the container (`pacman -Qi`):

| Package | Version | Installed size | Why |
|---|---|---|---|
| udiskie | 2.7.0-2 | 941 KiB | 1781793381-family auto-mount of removable drives (RUN from the earlier batch; still present) |
| qrencode | 4.1.1-4 | 154 KiB | Wi-Fi QR sharing |
| zbar | 0.23.95-3 | 1.0 MiB | QR scanning |
| ddcutil | 3.0.2-1 | 3.3 MiB | external monitor brightness (no external DisplayPort monitor can attach; candidate for removal later) |
| libvips | 8.18.7-1 | 6.5 MiB | image picker thumbnails |
| mpv-mpris | 1.3-1 | 67 KiB | MPRIS for mpv |
| dua-cli | 3.0.3-1 | 4.5 MiB | disk usage TUI (kept because disktree-bin is HOLD) |
| qt6-imageformats | 6.12.0-1 | 438 KiB | WebP decoding in the shell |
| yt-dlp | 2025.12.08-2 | 32.7 MiB | Chromium yt-dlp extension backend |
| xorg-xsetroot | 1.1.4-1 | 69 KiB | XWayland root cursor |
| ex-vi-compat | 3-1 | 1.2 KiB | provides `vi` (already installed) |

Total ≈ 50 MiB. Nothing outside `[core]/[extra]/[alarm]` was installed by
the RUN set — every `[omarchy]`-only install is in the HOLD list.

## What the supervisor must check on the real tablet after migrating

1. `systemctl --user` units now enabled (none of these are in
   `graphical-session.target.wants` today — the image only enables
   `hyprpolkitagent` and `lenovomarchy-squeekboard`):
   `omarchy-migrate-notify.service`, `omarchy-crash-watch.service`,
   `omarchy-fcitx5.service` (this one will fail to start without fcitx5 —
   check `systemctl --user status omarchy-fcitx5`; if it spams, mask it),
   and `owed.service` must **not** appear (held).
2. `systemctl is-active systemd-oomd` (1785424256-family RUN) and
   `NetworkManager-wait-online.service` masked state.
3. Sysctls applied: `sysctl net.ipv4.tcp_congestion_control` = `bbr`,
   `net.core.default_qdisc` = `fq`, `net.ipv4.conf.all.arp_ignore` = `1`,
   `arp_announce` = `2`.
4. Config files written: `~/.config/xdg-desktop-portal/hyprland-portals.conf`
   (Secret portal → gnome-keyring — confirm gnome-keyring is installed or
   the browser password pinning still behaves), `~/.config/chromium-flags.conf`
   gained `--enable-features=OverlayScrollbar`, tmux/kitty/foot config
   edits from the RUN set, `~/.config/hypr/looknfeel.lua` transparency
   example block.
5. Packages above present with `pacman -Q`, sizes as listed; `du` the
   `/usr` growth (~50 MiB).
6. `omarchy-migrate --pending` as `alarm` → empty; login notice gone.
7. `/var/lib/omarchy/migrations/1788163635` marker exists (passwordless
   sudo cleanup ran machine-wide) and `sudo -n true` still works for alarm.
8. Shell still starts: `shell.json` untouched in its bar section
   (`bar.id: omamobile.bar` preserved by the jq predicates in 1791968925/
   1791969355) — verify the omamobile bar still renders.
9. Held-but-wanted review list (below) once upstream ships aarch64 builds
   or the owner wants them.

## Doubtful on a touch-only tablet (flagged for the owner)

* **1791640449** (keyboard layout widget move) — RUN, but it only makes
  sense with a physical keyboard; harmless here because the omamobile bar
  ignores the omarchy layout.
* **1793477875** (dictation keybindings) — RUN, no-op here (no dictation
  backend configured). If dictation is ever wanted on the tablet it needs a
  touch-friendly backend decision first (superwhisper is x86 + [omarchy]
  only).
* **1791676907** (lone Shift input-method toggle) — RUN, guarded into
  no-op; pure keyboard feature.
* **1792020559** (fcitx5 candidate theme) — HOLD; would write stray fcitx5
  config for an IME the tablet doesn't run.
* **1791367434** (fcitx5 CJK defaults) — HOLD; ~1 GB of keyboard input
  engines, useless without a hardware keyboard, and it would fight
  squeekboard's text-input path.
* **1789764927** (OWE video wallpapers) — HOLD for availability, but also
  unreviewed on mobile grounds upstream (owedvideo held there too).
* **ddcutil** (via RUN 1785608251-family) — installed for external-monitor
  brightness over DDC; the tablet has no DDC-capable port. Harmless; remove
  if disk matters.
