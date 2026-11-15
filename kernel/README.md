# Kernel build (Docker)

Reproducible build of the arm64 mainline Linux 7.1 kernel for the
Lenovo Yoga Tab 11 (MediaTek MT6785), natively on Apple-silicon Docker
with LLVM. One command, from the repo root:

```sh
bash kernel/kbuild.sh            # add -j N to cap parallel jobs
```

Requires only Docker Desktop (linux/arm64). The kernel tree
`src/mt6785-mainline` is mounted **read-only** into the container and
built out-of-tree (`O=/build`) inside the Docker volume
`lenovomarchy-kbuild-out`; a second run is incremental.

## Configuration

A fresh volume seeds `.config` from `kernel/configs/pmos-mt6785.config`
(postmarketOS, Linux 6.16.4); every run then merges
`kernel/configs/yoga11.config` (`scripts/kconfig/merge_config.sh -m`)
and refreshes defaults (`make olddefconfig`).

## Output (`out/kernel/`)

| File | Content |
|------|---------|
| `Image.gz` | compressed arm64 kernel image |
| `dtbs/mediatek/mt6785-*.dtb` | MT6785 device trees (begonia CSOT/Tianma) |
| `modules.tar.xz` | `lib/modules/<release>/`, stripped |
| `config` | final `.config` |
| `kernel.release` | release string (e.g. `7.1.0-g…`) |

`kernel/check-config.sh out/kernel/config kernel/configs/yoga11.config`
verifies every fragment option made it into the final config.

## Options and environment

| Option / variable | Meaning |
|-------------------|---------|
| `--clean` | remove the build volume first (full rebuild) |
| `--rebuild-image` | rebuild the `lenovomarchy-kbuild` image |
| `-j N` | parallel jobs (default: host CPU count) |
| `YT11_KERNEL_DIR` | kernel tree (default `src/mt6785-mainline`) |
| `KBUILD_VOLUME` | build volume name (default `lenovomarchy-kbuild-out`) |
| `KBUILD_OUT_DIR` | output dir (default `out/kernel`) |
| `KBUILD_BUILD_*` | `TIMESTAMP`/`VERSION`/`USER`/`HOST` passed to make |

The build fails if `Image.gz` exceeds 24 MiB: the 32 MiB boot
partition must also hold the initramfs and the DTB. Boot image
packing and flashing are handled separately (`tools/`, out of scope).
