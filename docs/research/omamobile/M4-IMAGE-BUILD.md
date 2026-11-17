# M4: the image build produces what the tablet now runs

Date: 2026-11-17 · Scope: `image/` only · Status: build verified
(`smoke-check.sh` prints ALL CHECKS PASSED; the ext4 image is written).

The recipe moves from Omarchy 4.0.6 + prebuilt `omamobile-*` archives +
`--assume-installed omatel-agent` to what the tablet ran after the 2026-11-17
manual upgrade: Omarchy 4.5.0-3, `omamobile-omarchy` 0.1.48-1 and
`omamobile-shell` 0.2.133-3 built from `image/pkg/`, the camera app, the
migration hold list, and no mako.

## What changed

### Pins and verification (`image/tools/`)

- `repack.pins` / `repack.list`: `omarchy` and `omarchy-settings` repinned to
  4.5.0-3 (sha256 d367067c…, 2a81decb…); `omarchy-speedtest` 0.2.1-1 added
  (0fe8413b…) — it is a new hard dependency of omarchy 4.5. It ships an
  aarch64 ELF (`usr/lib/omarchy/speedtest`), so `repack-omarchy` gained a
  `verify-elf` mode: after the SHA-256 + GPG checks it requires arch=aarch64
  and every ELF in the archive to be 64-bit ARM. `verify-noarch` is unchanged
  (omarchy and omarchy-settings stay script-only). One stale digit in the
  cached `ufw-docker` pin was corrected (the download's real digest).
- New `repack-omamobile` + `repack.omamobile.pins` / `repack.omamobile.list` /
  `omamobile-trusted.fpr`: a second pinned source for
  `https://pkgs.omamobile.org/stable/aarch64/`, in the spirit of the Omarchy
  one: exact filename + SHA-256 pin, detached signature verified in the
  container. The trust bootstrap: the `omamobile-keyring` package is itself
  pinned by SHA-256, its signature is checked against the ORIGINAL package key
  (6C84FE3D…49FE), every key in the keyring must be listed in
  `omamobile-trusted.fpr`, and — because the release key is certify-only and
  signatures are made by its ed25519 SUBKEY — the fingerprint list carries the
  subkey (DDBA4581…1504) alongside both primaries. The pinned SHA-256 of every
  package is also cross-checked against the signed repository index
  `omamobile.db` (whose own signature is verified), so a pin cannot drift from
  what the repo actually serves. Packages: `omacam` 0.3.3-1 (e65a90f7…, from
  the brief, matches the index), `omamobile-settings` 0.1.2-1,
  `omamobile-remote` 0.1.2-1, `wlrctl` 0.2.2-1 (digests taken from
  `omamobile.db` and verified). Modes: `copy-any` (remote) and `copy-elf`
  (aarch64 archives; the GPG + index checks are the trust boundary).

### Built-in-the-image packages

- `image/tools/build-pkg` grew `--src <dir>`: any PKGBUILD directory, not just
  `image/pkg/<name>`. `image/build-rootfs.sh` uses it for
  `image/camera/libcamera-yt11`.
- `image/build-rootfs.sh` no longer requires `input/prebuilt/*`. It derives
  the wanted versions from `repack.pins` (upstream) and the PKGBUILDs'
  `pkgver`/`pkgrel` (built), runs each repack/build tool only when the
  matching archive is missing, and re-indexes the repo once. Stale archives of
  older versions are handled by `alarm_repo_index`'s newest-per-name cleanup.
- `libcamera` 0.7.2-4.5 (the tablet's build: MT6785 simple pipeline, soft
  ISP, sensor helpers, AE tuning, lens + autofocus) is built in the container
  (~25 min on arm64 Docker) and installed in place of ALARM's 0.7.2-4. Two
  build-dependency fixes were needed because ALARM's aarch64 repos differ
  from Arch's: `python-pyyaml` → `python-yaml`, `sdl2` → `sdl2-compat`
  (which provides sdl2), and `libunwind` added to `makedepends` (meson
  requires it; on the tablet it had come in with the base image).

### Rootfs scripts

- `install-mobile.sh`: the `--assume-installed omatel-agent=0.2.1` workaround
  is gone (the 0.1.48 package has no omatel dependency). The
  `rm -f ~/.config/omarchy/plugins/omamobile.{fingerprint,update,access,voice,call}`
  cleanup stays (M2 asks to keep it until a clean reflash; this build IS the
  clean reflash, but the links would only ever come from the 0.2.94-era
  prebuilt, which no longer exists in the flow — kept as belt-and-braces,
  it is a no-op here). The package-overwrite of the shell profiles is gone
  (see "Profile files" below). New: the Docker-overlay EXDEV workaround
  (below), `omacam` in the PATH check, and a pre-removal of the dangling
  `omarchy-fcitx5.service` wants link that migration 1785167800 would seed.
- `packages.extra`: `mako` removed — Omarchy 4.5's shell is the notification
  server and mako steals `org.freedesktop.Notifications` by D-Bus activation
  at boot (found on the tablet after the upgrade).
- `omarchy-user-setup.sh`: no more `~/.config/mako` + `mako.ini` link (no
  mako; the 4.5 themes ship no mako.ini). The fallback
  `~/.local/state/omarchy/version` now says 4.5.0 (it is only used when
  `/usr/share/omarchy` is not a git checkout; `omarchy-version` itself reads
  pacman).
- `finalize.sh`: `IgnorePkg` now holds `omarchy-speedtest`, the repacked
  Omarchy Mobile binaries (`omacam omamobile-settings omamobile-remote
  wlrctl`) and — the important one — `libcamera libcamera-ipa
  libcamera-tools`. Decision: **IgnorePkg over a higher pkgrel**, because
  pacman replaces on version and ALARM's next `libcamera 0.7.2-5` (or 0.7.3)
  would win again over our 4.5; a pkgrel race means re-building the tablet's
  libcamera on every ALARM bump, while IgnorePkg states the actual policy
  ("this machine's camera stack is pinned") and survives repo-side churn.
  omacam's `libcamera>=0.7 <0.8` dependency stays satisfied by the held
  0.7.2-4.5. `finalize.sh` also installs `omarchy-migrations.hold` as
  `/usr/share/lenovomarchy/omarchy-migrations.hold`.
- `smoke-check.sh` additions: `omarchy-migrate --pending` empty as `alarm`;
  `omamobile-omarchy-patches verify` passes; installed versions of omarchy /
  omarchy-settings / omamobile-omarchy / omamobile-shell / omacam match the
  pins / PKGBUILDs; `mako` not installed; `omacam` present and
  `ldd /usr/bin/omacam` resolves; the hold list is installed.
- `packages.mobile`: adds `omacam`, `gst-plugins-good`, `gst-plugins-ugly`,
  `gst-plugin-pipewire`, `pipewire-libcamera`, `omamobile-settings`,
  `omamobile-remote`, `wlrctl`.

### The EXDEV workaround (in-build, not a skipped check)

`omamobile-omarchy-patches`'s swap step does
`os.rename(state/pristine, work/pristine.old)`. During the image build the
pacman hook has already applied the series when `install-packages.sh` (an
earlier `RUN`) installs omarchy, so `pristine/` sits in a lower overlay
layer; the explicit `apply` in `install-mobile.sh` (a later `RUN`) then hits
`EXDEV: Invalid cross-device link` on the directory rename (reproduced
against `lenovomarchy-rootfs:aarch64`). Fix, as the brief prescribes: the
same RUN copies `/var/lib/omamobile` and `/usr/share/omarchy` in place
(`cp -a` + `rm -rf` + `mv`, exactly what `out/rehearsal/step.sh` does) before
running `apply` — after which both trees are upper-layer and every rename
works. `apply` still runs for real and `verify` still checks it.

### Profile files

The brief asked to check whether the image still needs to copy
`tablet-shell.json` / `tablet-home.json` over the package's profiles. The
*package* overwrite is gone: the `omamobile-shell` PKGBUILD already installs
exactly those two files as
`usr/share/omamobile/shell/profile/{shell,home}.json` (verified
byte-identical against `image/pkg/omamobile-shell/tablet-*.json`), so
`build-rootfs.sh` no longer stages `tablet-*.json` into the Docker context
and the Dockerfile no longer COPYies them. The *user's* copies, however,
still need seeding: with `--adopt`, `omamobile-setup-user` marks its
`omamobile-shell-profile` step done **without running it**, so
`install-mobile.sh` now seeds `~/.config/omarchy/shell.json` and
`~/.config/omamobile/home.json` straight from the package's profiles after
the adopt run (the old script did the same, just from the separately-staged
copies). The generated home-screen default (Home.qml builds a layout of
installed apps when `home.json` is missing) is thereby replaced by the
hand-authored 6x8 grid, matching what the tablet runs today.

### Repository order (libcamera shadowing)

The local `[lenovomarchy]` section is now inserted **before** `[core]` in
`/etc/pacman.conf` (`setup-pacman.sh`) instead of appended. Reason: this
pacman (7.1.0 / libalpm 16) resolves a package name offered by several
repositories by *repository order*, not by highest version — with the local
repo appended, Arch Linux ARM's `libcamera 0.7.2-4` shadowed the tablet's
`0.7.2-4.5` (reproduced with `pacman -S --print` in a dev container; with
the local repo first, `0.7.2-4.5` wins). `finalize.sh` still removes the
section at the end, as before.

### An errexit bug in our own patch (found by the fresh build)

Patch `0004-tablet-phone-leftovers.patch` (the M2 tablet port, not upstream)
ended `remove_unshipped()` with `((removed)) && echo …`. On a fresh user
there are no stale plugin links, so `removed=0`, the arithmetic command
returns status 1, the function returns 1, and `set -e` aborted
`omamobile-setup-user --adopt` (rc 1 after "adopted omamobile-shell-profile").
On the upgraded tablet it never fired because stale links existed
(`removed>0`). Fixed to an `if ((removed)); then …; fi` + explicit
`return 0`, hunk headers adjusted, pkgrel bumped to 0.2.133-3. Lesson: a
`--adopt` run on a *clean* user is the path that exercises the zero
branches.

## What Omarchy 4.5 newly pulls (and what the image skips)

Diff of 4.5's `omarchy-base.packages` + `omarchy-aarch64.packages` against
4.0.6's base list, after `packages.omarchy-skip`; sizes are ALARM
`Installed Size` where the package exists there:

**Skipped, [omarchy]-repo/AUR only (unavailable in ALARM, ~0 bytes pulled):**
`monologue`, `hype`, `signed`, `owe` (+`owe-lockfeed`), `gliff`,
`disktree-bin`, `omacalc`, `omacut`, `omawrite`, `aether`,
`omarchy-power-profiles-daemon`, `omarchy-hyprland-titlebars`,
`superwhisper-bin`, `cliamp`, `herdr`, `ttfx`, `mise-bin`,
`hyprland-preview-share-picker`. Omarchy Mobile holds the matching
migrations on phones for the same reason.

**Skipped on tablet grounds (would install from ALARM if not skipped):**

| Package | Size | Reason |
|---|---|---|
| `base-devel` | ~250 MiB with deps | compiler toolchain; nobody builds on the tablet (M3 1790702362) |
| `qt6-base`, `qt6-multimedia`, `qt6-svg`, `qt6-wayland` | ~100 MiB together | full Qt6 module set; nothing needs more than qt6-declarative, which still arrives as an omamobile-shell / omamobile-settings dependency |
| `fcitx5-chewing`, `-chinese-addons`, `-hangul`, `-mozc`, `-table-extra` | ~1 GiB | CJK keyboard input engines; squeekboard is the IME, no hardware keyboard (M3 1791367434) |
| `kernel-modules-hook` | small | already skipped: the tablet's modules are not a package |
| `ufw-docker` | 25 KiB | already skipped: docker is not installed |

**Newly pulled from ALARM (installed by this build), main entries:**
`ffmpeg` 43.3 MiB, `evince` 13.0 MiB (papers stays too), `nautilus` 14.2 MiB,
`mpv` 7.7 MiB, `libvips` 6.5 MiB, `tree-sitter-cli` 8.3 MiB, `usage` 10.0 MiB,
`lazygit` 21.2 MiB, `starship` 10.3 MiB, `noto-fonts` 106.8 MiB,
`gnome-disk-utility` 6.7 MiB, `gnome-themes-extra` 4.2 MiB, `ddcutil` 3.3 MiB
(no DDC port here; harmless), `bolt` 0.6 MiB (Thunderbolt daemon, no
Thunderbolt; harmless), `fzf` 5.8 MiB, `ripgrep` 4.2 MiB, `bat` 4.7 MiB,
`yt-dlp` 32.7 MiB (Chromium extension backend), `rtkit` (aarch64 list),
`zram-generator` (already an image package), `vi`→`ex-vi-compat` 1.2 KiB,
`xorg-xsetroot` 69 KiB, plus small CLI utilities (`fd eza zoxide tldr tmux
socat inxi man-db plocate qrencode zbar udiskie mpv-mpris ffmpegthumbnailer
gvfs-{mtp,nfs,smb} nss-mdns bluez-tools …`). The pre-existing set
(`chromium hyprland sddm gum git …`) was already installed.

4.5 also drops from its base list: `clang`, `llvm`, `ruby`, `tobi-try`
(still pinned here as a repacked any-package), `dua-cli`, `kdenlive`,
`lazydocker`, `obs-studio`, `power-profiles-daemon`, `tensaku`, `xournalpp`.

### `Hyprland --verify-config` against Omarchy 4.5 (supervisor)

The build's config check crashed on the 4.5 configuration, and the same
command crashes the same way on the tablet, so it is not a container
artefact. Two causes, both in `default/hypr/startup-cursor.lua`'s
`config.reloaded` handler, which only ever ran inside a session before:

- `hl.env("OMARCHY_STARTUP_CURSOR_SESSION", os.getenv("HYPRLAND_INSTANCE_SIGNATURE"))`
  is a Lua error when the variable is unset. The check now sets it.
- `hl.timer(...)` called from that handler makes Hyprland 0.57.2 segfault in
  `--verify-config` mode (bisected on the tablet: a config holding only that
  handler with an empty timer exits 139; the same handler with
  `hl.get_monitors`, `hl.config` or `hl.env` exits 0).

`install-mobile.sh` therefore verifies a two-line wrapper that replaces
`hl.timer` with a no-op and then loads the user's `hyprland.lua`. The check
keeps its value: with the wrapper the real config exits 0, and a config with
an unknown function or an unknown config section appended exits 1 (both
tried on the tablet).

## Result

`image/build-rootfs.sh` runs to the end: smoke check `ALL CHECKS PASSED`
(39 checks, the eleven new ones included), 779 packages, 8 GiB ext4 image in
`out/rootfs/`. The image was not flashed: the tablet was upgraded in place
(STATUS-20261117) and only received `omamobile-shell` 0.2.133-3 for parity.
A fresh flash of this image is the remaining test.

## Open points

- The image build now compiles libcamera in Docker on every version bump of
  `image/camera/libcamera-yt11` (~25 min arm64). Cached in `cache/repo/`
  between builds.
- `ddcutil` and `bolt` come in via 4.5's base list and are useless on this
  tablet; left installed (removal would need another skip entry — trivial if
  the owner wants the MiBs back).
- `omamobile-owl-widgets` remains not installed (OWL built-ins are behind
  `features.json`, off; the built-in QML widgets work without it).
- The ufw IPv6 failure noted in STATUS-20261117 (kernel lacks
  `NETFILTER_XT_MATCH_LIMIT` & co) is untouched by this change; it predates
  the upgrade.
