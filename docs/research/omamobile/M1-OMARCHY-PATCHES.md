# M1: omamobile-omarchy 0.1.48 on the YT-J706F tablet

Date: 2026-11-17 · Package: `image/pkg/omamobile-omarchy` · Status: built
(`omamobile-omarchy-0.1.48-1-any.pkg.tar.xz`, 75 580 bytes, in the local
`[lenovomarchy]` repo at `cache/repo/aarch64/`), not yet installed on the
unit.

Upstream lives at `https://github.com/derekross/omarchy-mobile` (the old
`omarchy-mobile/omarchy-mobile` org is gone — the 0.1.32 recipe's "upstream
no longer exists" header was wrong). This port pins upstream commit
`c4623572be1c141d602cf99a83ae0bf9e3eea09c` (omamobile-omarchy 0.1.48,
2026-11-16) as a GitHub tarball with its sha256 in the PKGBUILD. The old
recipe's prebuilt `input/prebuilt/omamobile-omarchy-0.1.32-1.2-any.pkg.tar.zst`
retires (supervisor to-do below).

Upstream 0.1.48's layout: an `install` script staging into DESTDIR, two
series families (`patches/` for Omarchy 4.5, `legacy-4.0.6/` for 4.0.6 — the
installed Omarchy version picks), `bin/omamobile-update` (the phone's update
wrapper) with `lib/update-bin/` stand-ins, `lib/modules-cleanup` + a systemd
timer (kernel module tree pruning), a zram drop-in, a tmpfiles rule for
`/run`, `lib/lock-pam`, the pacman hook, and `test/all`.

## What the mechanism is (kept whole)

* **`bin/omamobile-omarchy-patches`** (Python, taken from upstream
  unmodified): every run rebuilds Omarchy's pristine files (from the disk if
  they match the package's mtree, else from its kept pristine copies, the
  pacman cache, or by reversing the previously applied series), applies the
  selected family in a scratch tree with `--fuzz=0`, verifies by reversing,
  and only then swaps files in. A patch whose reverse applies is already in
  Omarchy (an upstream backport) and is skipped and reported. Any failure
  leaves Omarchy's files exactly as shipped. The installed version selects
  the family: `4.0.6*` → `legacy-4.0.6`, `4.5.0*` → `patches`, anything
  else refuses ("no qualified mobile patch series").
* **The pacman hook** (`95-omamobile-omarchy-patches.hook`, PostTransaction
  on `omarchy`, `omarchy-dev`, `omamobile-omarchy`) re-applies the series
  after every transaction that replaces Omarchy's files — so the package
  works on the tablet today (4.0.6) and after the 4.5 upgrade without
  intervention.
* **`lib/lock-pam`** writes `/etc/pam.d/omarchy-lock-password` when missing
  (Omarchy's installer is the only thing that writes it; an image-built
  tablet had none and the lock refused). Run from `post_install`/`post_upgrade`.
* **`tmpfiles/omamobile-run.conf`** (`z /run 0755 root root - -`): Omarchy
  4.5 refuses to work under a `/run` anyone can write (its sudo migration
  1788163635 stops `omarchy update`); applied by pacman's tmpfiles hook in
  the same transaction that installs this package, before any 4.5 migration
  runs. Kept: cheap, and the tablet's boot image mounts `/run` 0755 already —
  this makes it true at every boot regardless.
* **zram**: upstream ships `zram/91-omamobile.conf` capping Omarchy's
  `zram-size = ram` at `ram / 2` (a Pixel with 7.4 GB hung under load with a
  whole-RAM zram). The tablet (4 GB LPDDR4X) already ships its own
  `/etc/systemd/zram-generator.conf` with `zram-size = ram / 2`, zstd,
  priority 100, fs-type swap, and `/etc` outranks `/usr/lib` drop-ins — so
  the drop-in is **not installed**; it would be a no-op. What upstream's
  behaviour amounts to on this tablet: 2 GB of compressed (zstd, ~3:1) RAM
  swap at priority 100, i.e. exactly what the image already configures.
* **`linux-modules-cleanup` drop-in** (upstream's
  `systemd/linux-modules-cleanup.service.d/10-omamobile.conf`): Arch's
  kernel-modules-hook moves every `/usr/lib/modules/<release>` that isn't
  running and that no package owns into `.old` at each boot; upstream holds
  it off with a `ConditionPathExists=!/usr/share/omamobile/omarchy/version`
  drop-in and prunes with its own timer instead. On the tablet the whole
  question is void: `kernel-modules-hook` is in `packages.omarchy-skip` (the
  kernel is not a package), so Arch's unit is **not installed at all** —
  nothing to hold off. The drop-in is not installed either (it would stage a
  condition for a unit that does not exist).

## The update path (the big divergence from upstream)

Upstream's patch 0012 hands `omarchy update` to `omamobile-update`, which
runs Omarchy's own `omarchy-update -y` with a stand-in directory first on
`PATH` (no Snapper snapshot, no AUR builds, no gum reboot prompt, boot
migrations held) and gates on `[omamobile]` being the first repository in
`/etc/pacman.conf`. The tablet has **no `[omamobile]` repository**: its
pacman.conf has `[lenovomarchy]` (a local file repo, baked at build time,
removed from pacman.conf by `finalize.sh` in the final image), Arch Linux
ARM's `[core]`/`[extra]`/`[alarm]` via the mirrorlist, and `[omarchy]`
(added when Omarchy was installed from the repacked packages). The wrapper's
repository-order and mirrorlist checks would refuse every update; its
battery/channel/boot-package policy is phone policy.

So the tablet **keeps Omarchy's own `omarchy update`** (patch 0012 is
dropped) and makes it safe with the two carried-forward tablet patches:

The tablet's `/etc/pacman.conf` as shipped: `[core]`, `[extra]`, `[alarm]`
(Arch Linux ARM via `/etc/pacman.d/mirrorlist`) and nothing else —
`[lenovomarchy]` is a build-time file repo removed by `finalize.sh`, and
`[omarchy]` was never added (Omarchy's packages reached the image through
`[lenovomarchy]`). `omamobile-omarchy`, `omamobile-shell` and the repacked
`omarchy`* packages are therefore **foreign** (`pacman -Qem`) once
installed, which is also why 9001 keeps `yay` out of the update path.

* **9000-tablet-pacman-keeps-alarm** (was `pacman-keeps-alarm.patch`, the
  0.1.32 recipe's 0016-adjacent guard): `omarchy-channel-set` and
  `omarchy-refresh-pacman` refuse when `/etc/pacman.conf` carries `[alarm]`.
  In 4.5 both render the platform's pacman templates (aarch64 variants now —
  not x86_64 as in 4.0.6, but still without the tablet's repositories and
  with Omarchy's own mirrorlist) and copy them over `/etc/pacman.conf` and
  `/etc/pacman.d/mirrorlist`.
* **9001-tablet-update-without-kernel-package** (was
  `update-without-kernel-package.patch`): 4.5's `omarchy-update-restart`
  decides "kernel updated" from a pacman-owned `modules.builtin` matching
  `uname -r` — always false here (the image unpacks the modules, no package
  owns them), so it would offer a reboot on every update. The probe is
  dropped; a reboot is asked for only via Omarchy's own
  `~/.local/state/omarchy/reboot-required` marker (and Hyprland's
  `(deleted)` exe check, kept). `omarchy-update-aur-pkgs` runs `yay` when
  any foreign package is installed; the tablet has no `yay`, so it now only
  runs `yay` when `yay` exists (the `[lenovomarchy]` packages are foreign
  and must never be rebuilt from the AUR).

What runs in Omarchy's own flow on the tablet, checked against 4.5's
`omarchy-update`: transcript → update lock → 10 GiB free-space check →
`omarchy-update-confirm` (gum, installed as an omarchy dep) → cache prune
(`paccache`, pacman-contrib) → `omarchy-snapshot` (Snapper absent → exit 127,
which Omarchy takes for "deliberately absent") → stay-awake inhibitor →
`omarchy-update-dev`/keyrings (omarchy-keyring installed; ALARM's keyring
checked by 4.5's `omarchy-update-keyring` on aarch64) →
`omarchy-update-system-pkgs` (`pacman -Syu --overwrite /usr/share/omarchy/*`
through the pacman guard) → migrations (see risks) → restarts/services →
mise (absent, tolerated) → AUR (9001) → `omarchy-update-boot` (4.5's
lifecycle dispatch: plain aarch64 registers no boot package, so it is a
documented no-op that only warns on machines that predate a boot package) →
restart (9001). `omamobile-omarchy`'s hook re-applies the 4.5 series at the
end of the transaction.

`omamobile-update` (the wrapper), `lib/update-bin/*` and everything that
would install them are **not in the package**; `install` stages neither.

## The keep/drop table

Both families get the same treatment (the 4.5 series and `legacy-4.0.6` must
stay applicable to their Omarchy at all times, because the hook picks by
installed version). 29 − 7 + 2 = 24 patches per family.

### 4.5 family (`patches/`)

| Patch | Decision | Why |
| --- | --- | --- |
| 0001 first-run keybindings skip | **keep** | Touch-only tablet has no keyboard-first workflow; same rationale as the phone |
| 0003 lock number pad | **keep** | Touch-only lock needs its own digits; the tablet locks with a PIN |
| 0005 image-picker swipe + hold for style | **keep** | Pure touch UI; no right button or shortcuts on the tablet |
| 0006 screensaver OSK off + cursor restore | **keep** | squeekboard pops up for the screensaver's terminal here too (the image runs squeekboard as the OSK) |
| 0007 idle lock on return to screensaver | **keep** | Touch-session behaviour, no hardware keys involved |
| 0008 brightness bl_power follows DPMS | **keep** | The tablet's panel is run from the bootloader's framebuffer; DPMS alone doesn't reach it (same class of panel as the phone's) |
| 0009 lock "wake" IPC | **keep** | Used by 0013/0023; nothing phone-specific in the mechanism |
| 0010 polkit prompt over OSK | **keep** | Root prompt with an on-screen keyboard; happens on the tablet (e.g. `pacman` via GUI helpers) |
| 0011 PIN or password input | **keep** | Direct follow-on of 0003/0010 for touch devices |
| 0012 hand `omarchy update` to `omamobile-update` | **DROP** | No `[omamobile]` repo on the tablet; the wrapper's repository/channel/battery/boot-package policy is phone policy and would refuse every update. The tablet keeps Omarchy's own update, made safe by 9000/9001. Also drops the second hunk (the `--reboot-only` PATH override), unneeded without the wrapper |
| 0013 idle wake through the lock | **keep** | Fixes a lit-screen-behind-lock drain; pure gain on a battery tablet |
| 0014 lock "Emergency call" button | **DROP** | **Modem-only.** No modem, no `omamobile.call` plugin (M2 drops it too): the button would appear (it shows whenever the keypad toggle is on) and do nothing. This is the emergency-call patch the brief names |
| 0015 notifications inline reply | **keep** | Generic freedesktop action; useful for any messaging app on the tablet |
| 0016 channel-switch/pacman-refresh refusal | **DROP** | Its guard keys on `-x /usr/bin/omamobile-update`, which this package no longer installs — it would never trigger. Its purpose survives as tablet patch 9000 with an `[alarm]` test instead |
| 0017 swipe to dismiss + touch close button | **keep** | Core touch notification UX |
| 0018 menu back button + swipe right | **keep** | Core touch menu navigation |
| 0019 forget one notification by IPC | **keep** | Used by 0023's glance; generic service call |
| 0020 notification touch phrasing | **DROP** | Rewords "click"/"Super+…" hints only when `/usr/bin/omamobile-update` exists — never true here, so the patch would be inert. (Reported: the tablet therefore keeps Omarchy's stock phrasing; a touch-worded variant would need a different platform test — follow-up if wanted) |
| 0021 display off before suspend | **DROP** | It blanks the panel via `bl_power` around suspend, tied to the phone's power-key/sleepd wake path (`omamobile-keys`, `omamobile-sleepd` — not shipped; M2 drops them too). The tablet suspends via the system menu with s2idle and its panel-off path is 0008's DPMS follow; forcing a pre-suspend blank without the phone's wake plumbing risks a dark screen on wake. Revisit with BOARD.md measurements if suspend drain shows up |
| 0022 fingerprint probe + PAM preserve | **DROP** | **No fingerprint reader.** The probe half is dead code here; the PAM-preserve half guards `/etc/pam.d/omarchy-lock-password` against Omarchy's own `omarchy-apply-lock` — on the tablet that file is written by our `lock-pam` from Omarchy's own stanza, so Omarchy rewriting it is harmless (it writes the same stanza) |
| 0023 lock glance view | **keep, rebased** | The glance (clock, notifications, weather, media) is the touch lock's home screen; the tablet has it today. Rebased: without 0014 its LockGlance insert anchors above the keypad hint instead of above the emergency button (two tail hunks rewritten, noted in the patch header) |
| 0024 app icons keep largest size | **keep** | Generic fix, visible on the tablet's launcher |
| 0025 no launch toast for shell surfaces | **keep** | Generic; the tablet's shell opens surfaces (quick settings) the same way |
| 0026 lock battery status | **keep** | A tablet shows its battery on the lock screen; reads kernel power supplies (max170xx-class gauge here) |
| 0027 lock media controls | **keep** | MPRIS transport on the glance/PIN view; nothing phone-specific |
| 0028 stacked logo for narrow terminals | **keep** | The 11" panel in portrait is narrow at Omarchy's terminal font; generic |
| 0029 double-tap to wake | **DROP** | Needs `omamobile-doubletap` (proximity-aware, from omamobile-shell) which M2 does not ship; without it a dark touch would wake nothing — a regression. Without 0029, 0023's own `wakeTouch` lights the screen on any touch, which is what a tablet without a proximity sensor wants |
| 0030 about logo above modules | **keep** | Same narrow-terminal rationale as 0028 |
| 0031 first-run skip missing units | **keep** | The image deliberately omits Omarchy units (OWE); without this first-run loops. Written against 4.5 only |
| **9000 tablet pacman-keeps-alarm** | **added** | The 0.1.32 `pacman-keeps-alarm.patch` rebased onto 4.5's channel-set/refresh-pacman (see above) |
| **9001 tablet update-without-kernel-package** | **added** | The 0.1.32 `update-without-kernel-package.patch` rebased onto 4.5's split restart step + the yay guard (see above) |

### `legacy-4.0.6` family

Identical decisions for the same numbers (0001, 0003, 0005–0011, 0013,
0015, 0017–0019, 0023–0028, 0030 kept; 0012, 0014, 0016, 0020, 0021, 0022,
0029 dropped; 9000/9001 added, written against the 4.0.6 scripts), plus:
* `bridge-4.0.4-menu-first-frame.patch` **kept** — 4.0.6's menu first-frame
  bridge, still needed while the tablet runs 4.0.6.
* 4.0.6 has no 0031 (it is a 4.5-only fix).
* The 4.0.6 `9001` drops the whole vmlinuz probe (4.0.6's restart step is a
  single script with a gum prompt) instead of 4.5's `modules.builtin` probe.

The 0.1.32 recipe's font-size tweak (`sed s/font-size: 16pt;/font-size:
13pt;/` on old 0003): **the hunk no longer exists.** No `16pt` string
remains anywhere in upstream 0.1.48's series (checked `patches/`,
`legacy-4.0.6/` and the published 0.1.47 package); 4.5's lock pad sizes
from `root.key` (`font.pixelSize: Math.round(root.key * 0.38)`), and menu
fonts come from Omarchy's `Style.font` scale. Nothing to carry forward.

## Neutralising the packaged-kernel machinery (brief item 4)

Neither `lib/modules-cleanup` nor its timer is installed, and neither is the
`linux-modules-cleanup` drop-in. The package ships **no file** whose name
matches `*modules-cleanup*` and **no systemd unit, timer or wants link at
all** (`bsdtar -tf` of the built package shows zero; `test/all` asserts it).
On the tablet, `/usr/lib/modules/<release>` is unpacked by the image build
and owned by no package — Arch's `linux-modules-cleanup.service` would move
it to `.old` at every boot if `kernel-modules-hook` were installed, and
upstream's own timer would prune it as "not pacman-owned and not the two
newest". Not installing either is the only safe option; the tablet's module
tree must survive every boot and every package transaction.

## The 4.0.6 → 4.5.0-3 upgrade on the tablet, step by step

The tablet today runs omarchy 4.0.6-1 with omamobile-omarchy 0.1.32-1.2
(the prebuilt), and `IgnorePkg = hyprland omarchy omarchy-settings
omarchy-keyring omamobile-omarchy omamobile-shell` in `/etc/pacman.conf`
pins everything that matters. Expected sequence:

1. **On the Mac** (supervisor): repin Omarchy 4.5 in
   `image/tools/repack.pins` (`omarchy-4.5.0-3`,
   `omarchy-settings-4.5.0-3`, sha256 from the brief; `omarchy-keyring`
   and friends unchanged), rebuild the local repo, and build the new
   packages (`build-pkg omamobile-omarchy`, `build-pkg omamobile-shell`).
2. **Push the packages to the tablet** (adb to `/root/` or the local repo
   dir) and install 0.1.48 **while still on 4.0.6**:
   `pacman -U omamobile-omarchy-0.1.48-1-any.pkg.tar.xz omamobile-shell-….pkg.tar.xz`.
   The hook fires (`Target = omamobile-omarchy`), selects `legacy-4.0.6`
   (24 patches), applies and verifies; `omamobile-omarchy-patches status`
   should list them all applied. The old 0.1.32's state
   (`/var/lib/omamobile/omarchy-patches/state.json`) is read by the same
   tool lineage for pristine recovery; a series that drops patches restores
   those files to Omarchy's own (the tool handles it — verified by the
   synthetic "dropped patches" test).
3. **Check the series** on the unit: `omamobile-omarchy-patches status` and
   `verify`. The 0.1.32-era phone-drops (SIM PIN etc.) are gone from both
   sides; the tablet's own 9000/9001 apply on 4.0.6's scripts.
4. **Lift the Omarchy pins** for the upgrade only:
   `sed -i 's/^IgnorePkg = .*/IgnorePkg = omamobile-omarchy omamobile-shell/' /etc/pacman.conf`
   (keep the two omamobile packages pinned: they are `[lenovomarchy]`
   builds, and an unpinned `omarchy update` must not try to replace them —
   there is no `[omamobile]` repo to satisfy them).
5. **Stage the 4.5 packages where pacman can see them**: the tablet has no
   `[omarchy]` repository, so either re-add `[lenovomarchy]` pointing at a
   repo dir pushed to the unit
   (`[lenovomarchy]` + `Server = file:///root/repo`), or `pacman -U` the
   two files (`omarchy-4.5.0-3-…`, `omarchy-settings-4.5.0-3-…`) directly.
   Then run `omarchy update` (Omarchy's own flow; 9000/9001 are in force)
   or plain `pacman -Syu` with the Omarchy pins lifted — both end in the
   same transaction. During it the hook re-runs and — this is the delicate
   moment — pacman has just replaced `/usr/share/omarchy` with 4.5's files;
   the tool reads 4.5's local db entry (mtime/mtree), selects the `patches`
   family and applies it. If it fails, Omarchy's 4.5 files stay in place
   (unpatched, PIN pad missing) and the log says why; re-run
   `omamobile-omarchy-patches apply` after fixing.
6. **Migrations**: 4.5 ships ~200 migrations; the tablet's image build
   pre-marked all shipped-at-build-time ones done
   (`omarchy-user-setup.sh`), so only 4.5's new ones run. Reviewed for this
   port: `1791403252` (move `[omarchy]` first in pacman.conf — the tablet
   has no `[omarchy]` section, so the awk leaves the file alone; safe
   no-op),
   `1788163635` (sudo passwordless cleanup; the tablet's sudoers is
   image-built, fine), the fcitx5 trio (`1785167800`, `1791367434`,
   `1792020559` — they enable/theme a user unit for fcitx5, which the
   tablet does not install; `systemctl --user enable` on a missing unit is
   a no-op with a warning), `1787589206`/`1788112314` (SigLevel and rc
   mirrorlist cleanups — the tablet's pacman.conf has neither the
   `SigLevel = Optional TrustAll` override nor rc mirrors, so they no-op or
   safely reorder). One installs packages the tablet skipped on purpose
   (1791367434: fcitx5 dictionaries — see risks), and 1785167800 writes a
   wants-link for `omarchy-fcitx5.service` (the unit file is not installed
   here; a dangling wants link makes the target log a load failure at
   login — remove `~/.config/systemd/user/graphical-session.target.wants/
   omarchy-fcitx5.service` after the upgrade, or before it).
7. **After the update**: `omamobile-omarchy-patches status` should now say
   the `patches` family (24 applied). `omamobile-setup-user` from the new
   shell package should be run once by hand if upgrading in place (M2's
   note). Put the pins back:
   `sed -i 's/^IgnorePkg = .*/IgnorePkg = hyprland omarchy omarchy-settings omarchy-keyring omamobile-omarchy omamobile-shell/' /etc/pacman.conf`
   (decide whether `hyprland` stays pinned: 4.5 was checked against
   ALARM's Hyprland 0.57; Omarchy's repo also ships Hyprland builds).
8. **Reboot** when `reboot-required` says so (4.5's Hyprland/(deleted) or
   marker rules only, thanks to 9001) and re-check on the unit: lock PIN
   pad + glance, notification swipe/close, menu back, brightness keys,
   `omamobile-omarchy-patches verify`.

A full reflash of the image (the other path) bakes 4.5.0-3 + this package
directly and needs none of steps 4–7; the in-place path exists because the
owner may prefer not to reflash.

## Risks

* **The in-place 4.5 transaction is the one delicate moment** (step 5): the
  hook runs with 4.5's files freshly in place. Rehearsed offline against
  the real `omarchy-4.5.0-3-aarch64.pkg.tar.zst` (the `real4.5` test in
  `check()`: the version-selected series applies to the signed package, 24
  applied, 0 upstream, verify passes, apply is idempotent), so the series
  itself is proven; the residual risk is the tool's pristine-file recovery
  paths on a live system (package cache absent after `finalize.sh` cleaned
  it — the mtree on disk and the kept pristine copies cover it).
* **Migration 1791367434** runs `omarchy-pkg-add fcitx5-mozc fcitx5-hangul
  fcitx5-chinese-addons fcitx5-chewing` — input-method packages the tablet
  skipped on purpose (`packages.omarchy-skip` drops fcitx5). They are in
  ALARM repos, so they would install (a few dozen MB) but change no
  running component. **Migration 1785167800** then writes a wants-link for
  `omarchy-fcitx5.service`, which does not exist here → delete
  `~/.config/systemd/user/graphical-session.target.wants/omarchy-fcitx5.service`
  after the upgrade (or pre-create the removal). If both are unwanted, the
  phone's hold mechanism is the model (a stand-in `omarchy-migrate` on PATH
  during updates); flagged to the supervisor as a possible follow-up.
* **`omarchy-update-confirm` uses gum interactively**; over ssh with no TTY
  it fails and the update stops before touching anything — safe, just
  run it from a terminal on the tablet or with `-y` semantics via
  `omarchy update -y`.
* **`omarchy-update-boot` on plain aarch64** is a documented no-op that
  prints a warning ("predates its platform's boot package"); it never fails
  the update (exit 0 path verified in the script).
* **The glance without 0014** anchors above the keypad hint; if upstream
  re-adds an emergency button in a later series the rebase note in 0023's
  header says what to restore.
* **`omamobile-shell` 0.2.133 (M2)** deliberately ships no `omamobile.update`
  plugin and expects update-by-reflash; that stays consistent with this
  package (no wrapper) — the tablet's update UI is the terminal, or a
  reflash. If the owner later wants the update sheet, both packages grow
  together.
* **zram unchanged** (image's own config, half RAM); nothing in this
  package touches it.

## Supervisor to-do (files I did not touch)

1. `image/tools/repack.pins` + `repack.list`: move the Omarchy pins to 4.5 —
   `omarchy  omarchy-4.5.0-3-aarch64.pkg.tar.zst
   d367067c1e35d6e99f7cd921e0a55ec6e46cb0d2bc681b1a4b39254c8c0416e7` and
   `omarchy-settings  omarchy-settings-4.5.0-3-aarch64.pkg.tar.zst
   2a81decbaeb873a354f2b9728cd0dfc8b633af101eed98e3945e2b6bf55c8c58`
   (both sha256 verified against the downloads; the .sig files are fetched
   by `repack-omarchy` itself). `omarchy-keyring`'s pin is unchanged (its
   file still matches `cce48c07…`). New 4.5 dependency to add to
   `repack.list`/`repack.pins` — `omarchy-speedtest
   omarchy-speedtest-0.2.1-1-aarch64.pkg.tar.zst
   0fe8413b0da314035fd68aee697b6d4b7e50cde5f2413920351be63719aafb7c`.
   Note it **contains an aarch64 ELF** (`usr/lib/omarchy/speedtest`), so
   the `verify-noarch` mode refuses it: add an `elf-ok`-style mode (or copy
   it after the GPG check) in `repack-omarchy` — both existing modes assume
   script-only payloads. `omarchy-security-functions` (also new in 4.5's
   depends) needs **no** package: `omarchy-settings-4.5.0-3` provides it.
2. `image/build-rootfs.sh`: drop `omamobile-omarchy-0.1.32-1.2` from the
   required-inputs list and the `input/prebuilt/` copy/`cp -f` lines (the
   local repo now gets it from `image/tools/build-pkg omamobile-omarchy`;
   the M2 note already says the same for the shell's prebuilt). If the
   repo-population `if` still names `omamobile-omarchy-0.1.32-1.2`,
   `omamobile-shell-0.2.94-5` and `omarchy-4.0.6-1`, update those filenames
   to the new ones (`omamobile-omarchy-0.1.48-1-any.pkg.tar.xz`, the M2
   shell archive, `omarchy-4.5.0-3`).
3. `image/rootfs/install-mobile.sh`: nothing must change for this package
   (it still runs `omamobile-omarchy-patches apply`, `verify` and
   `lock-pam`, all still present), but the M2 items (the
   `--assume-installed omatel-agent` drop) land together.
4. `image/rootfs/omarchy-user-setup.sh` and `install-packages.sh`: for a
   4.5-based image, `install-packages.sh`'s dependency walk picks up
   4.5's new depends (`omarchy-speedtest`; `omarchy-security-functions`
   resolves to the repacked settings) automatically — but check
   `packages.omarchy-skip` against 4.5's base list again when repinning
   (4.5's `omarchy-base.packages` has 162 entries; the skip list was written
   against 4.0.6's).
5. Nothing else: this package brings no new runtime package dependencies
   beyond what the image has (`bash python patch libarchive util-linux`).

## What `check()` runs, and what it cannot

`check()` runs upstream's `test/all`, adapted to the tablet tree: script
parsing, the staged layout and hook, the no-modules-cleanup/no-wrapper/no-zram
assertions, the keep/drop inventory, the full synthetic suite for
`omamobile-omarchy-patches` (apply/verify/restore/upstream-skip/dropped/
hand-edited-refusal/package-cache recovery), the real-package rehearsal
when `OMARCHY_PKG` is set (it is not set in the build container — that part
self-skips; the supervisor's dry-run acceptance below covers it), lock-pam,
the `/run` tmpfiles rule, and `source-family` selection. Not run, and why:
`test/update.sh` and `test/migration-mobile-holds.py` (they exercise
`omamobile-update` and its `update-bin` stand-ins, none of which this
package installs), `test/modules-cleanup.sh` and `test/zram.sh` (no
modules-cleanup, no zram drop-in), `test/sleep-lock.sh` and
`test/sleep-lock-family.py` (they rehearse patch 0021, dropped), the OWL
inline-reply container test (a docker image this repo does not build; the
patch's QML is still parsed by the synthetic suite), and `node`-based
notification-store tests when node is absent (self-skip).
