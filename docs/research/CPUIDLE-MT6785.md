# CPU idle states and deep sleep on MT6785: what mainline needs

Research date: 2026-11-18. Code study only; nothing was run on the unit.

Scope: the vendor 4.14 kernel in `src/lenovo-gpl-4.14` (commit `975d4381`)
and the mainline-lineage 7.1 kernel in `src/mt6785-mainline` (branch
`yt11`). Facts measured on the unit live in `docs/hardware/BOARD.md` and
outrank this file.

How the vendor files were read. `src/lenovo-gpl-4.14` is a sparse,
blob-less partial clone. Most vendor files cited here are not in its working
tree, but their blobs are in the local object store. They were read with
`GIT_NO_LAZY_FETCH=1 git -C src/lenovo-gpl-4.14 show HEAD:<path>`; the
variable stops git from fetching anything. Line numbers refer to those
blobs. Four blobs are not in the local store:
`drivers/cpuidle/cpuidle-mtk_acao.c`, `drivers/firmware/psci.c`,
`drivers/clocksource/mtk_systimer.c` and `arch/arm64/Kconfig.platforms`.
They were read from the upstream GitHub repository at the same commit.
Claims that rest on them are tagged **(remote)**, and their line numbers are
approximate.

"Unverified" marks anything the two trees cannot show, mostly the behaviour
of the secure firmware (ATF), whose source is in neither tree.

## Summary

1. The vendor DT declares seven PSCI idle states: `standby` 0x1,
   `mcdi-cpu` 0x10001, `mcdi-cluster` 0x1010001, and four SPM-backed
   cluster-level states `idledram`, `idlesyspll`, `idlebus26m` and
   `suspend` (0x1010002-0x1010005). The vendor uses this table only to map
   indices to `power_state` values. The latencies the kernel acts on come
   from MediaTek's MCDI tables, not from the DT.
2. Every vendor low-power path ends in PSCI `CPU_SUSPEND` (0xC4000001) with
   one of these values, through `mtk_enter_idle_state(mode)` →
   `arm_cpuidle_suspend(mode)`. The vendor never calls `standby` (0x1) and
   never calls `SYSTEM_SUSPEND`.
3. Before its first `CPU_SUSPEND`, the vendor kernel clears the MCDI SYSRAM.
   It asks ATF to start ("kick") the SPM firmware, sets up the CPC through
   MCDI SMCs and sends the SSPM a CPU mask. It also waits 10 s after boot and
   then writes "AP ready" into the SSPM mailbox. None of this exists in
   mainline.
4. The kernel loads no firmware for any of this. The SPM PCM firmware and
   the SSPM firmware are already in place when Linux starts. The kernel only
   queries the SPM firmware's status, kicks it, and talks to the SSPM over a
   mailbox and IPIs. MCUPM is not used on MT6785.
5. The four SPM states need an SMC that sets up the SPM before
   `CPU_SUSPEND`. They also need the CIRQ and, for `suspend`, an IPI to the
   SSPM. A DT change alone cannot give them.
6. `mcdi-cpu` and `mcdi-cluster` are the only candidates for a DT-only
   approach. mt8183, mt8186 and mt8365 use the very same encodings in
   mainline. But BOARD.md records that the stock encodings hung the unit.
   Even `standby` on one CPU froze it. The missing kernel-side handshake in
   point 3 is the main suspect (unverified).
7. Two DT fragments are given in section 4 (core-off, then core-off plus
   cluster-off). Both compile with dtc 1.8.1. They are worth flashing only
   after the read-only probes and the init replay that section 4 lists.
8. Vendor "deep" suspend is an SPM sequence. It sends `SPM_SUSPEND_ARGS`
   (0xC2000220) with PCM flags and an IPI `SPM_SUSPEND` to the SSPM, arms
   the CIRQ, then issues `CPU_SUSPEND(0x01010005)` from the last CPU.
9. Mainline offers `deep` because ATF answers `PSCI_FEATURES(SYSTEM_SUSPEND)`
   as supported. The vendor never uses that call, and on the unit it never
   comes back (BOARD.md).
10. The timer side is already in place in mainline. The MT6785 SYST
    (`mediatek,mt6765-timer`) is the same block and has the same flags as
    the vendor's broadcast timer. Because the arch timer is not
    `always-on`, the tick core will use the SYST as the broadcast device.

---

## 1. Idle states the vendor kernel defines

### 1.1 The DT table

`src/lenovo-gpl-4.14/arch/arm64/boot/dts/mediatek/mt6785.dts`,
`idle-states` node at lines 166-228 (`entry-method = "arm,psci"`). All eight
CPUs list the same seven states, in the same order (`cpu-idle-states` at
lines 55-56, 65-66 and so on up to 125-126):

| # | Node | `arm,psci-suspend-param` | entry / exit / min-residency (us) | `status` |
|---|---|---|---|---|
| 1 | `standby` | `0x00000001` | 600 / 600 / 1200 | (none) |
| 2 | `mcdi-cpu` | `0x00010001` | 600 / 600 / 1200 | (none) |
| 3 | `mcdi-cluster` | `0x01010001` | 600 / 600 / 1200 | (none) |
| 4 | `idledram` | `0x01010002` | 800 / 1000 / 2000 | `okay` |
| 5 | `idlesyspll` | `0x01010003` | 800 / 1000 / 2000 | `okay` |
| 6 | `idlebus26m` | `0x01010004` | 800 / 1000 / 2000 | `okay` |
| 7 | `suspend` | `0x01010005` | 800 / 1000 / 2000 | `okay` |

Decoding in the PSCI "original" format (`include/uapi/linux/psci.h:75-82`
in mainline): bits [15:0] are the StateID, bit 16 is the type (1 =
power-down) and bits [25:24] are the affinity level. So `standby` is a
level-0 standby with StateID 1, and `mcdi-cpu` is a level-0 (core)
power-down with StateID 1. The other five are level-1 power-downs with
StateIDs 1 to 5. The StateID distinguishes the four SPM scenarios at the
same level.

The vendor board overlay `yoga11.dts` (a `/plugin/`, line 14) does not touch
`cpus` or `idle-states`.

`psci` is `arm,psci-1.0`, method `smc` (`mt6785.dts:262-265`).

### 1.2 How the vendor maps these states to code

- `mtk_cpuidle.h` (`drivers/misc/mediatek/base/power/include/cpuidle_v3/mtk_cpuidle.h:17-29`)
  numbers the modes as follows: `MTK_STANDBY_MODE=1`,
  `MTK_MCDI_CPU_MODE=2`, `MTK_MCDI_CLUSTER_MODE=3`, `MTK_IDLEDRAM_MODE=4`,
  `MTK_IDLESYSPLL_MODE=5`, `MTK_IDLEBUS26M_MODE=6` and `MTK_SUSPEND_MODE=7`.
  These are exactly the 1-based positions of the states in `cpu-idle-states`.
- `mtk_enter_idle_state(mode)` (`drivers/misc/mediatek/base/power/cpuidle_v3/mtk_cpuidle.c:316-357`)
  wraps `cpu_pm_enter()` and calls `arm_cpuidle_suspend(mode)` at line 341.
- In 4.14, `psci_cpu_suspend_enter(index)` uses `state[index - 1]`. That is
  the value that `psci_dt_cpu_init_idle()` read from the index-th
  `cpu-idle-states` phandle. It saves context through `cpu_suspend()` when
  the type bit says the state loses context (`drivers/firmware/psci.c`,
  about lines 283-336 and 438-455, **(remote)**).
- The per-CPU PSCI table is filled by `arm_cpuidle_init(cpu)` in
  `mtk_acao_cpuidle_init()` (`drivers/cpuidle/cpuidle-mtk_acao.c`,
  `device_initcall`, **(remote)**). That function first registers the MTK
  drivers through `mtk_cpuidle_register_driver()`. Its call to
  `dt_init_idle_driver()` is inside `#if 0`. So the DT latencies are never
  loaded into a cpuidle driver; only the `arm,psci-suspend-param` values are
  used.
- Build check. `drivers/misc/mediatek/base/power/Makefile` builds `spm/`
  (line 28), `mcdi/` (line 117) and `cpuidle_v3/` (line 163) for
  `CONFIG_MACH_MT6785`.
- `MTK_STANDBY_MODE` is declared and nowhere used in the examined code
  (cpuidle_v3, mcdi, spm, sspm). The vendor kernel never issues
  `CPU_SUSPEND(0x00000001)`.

### 1.3 The cpuidle driver the vendor actually registers

`drivers/misc/mediatek/base/power/mcdi/mt6785/mtk_mcdi_state.c` registers
two drivers. Set 0 covers CPUs 0-5 (mask 0x3F) and set 1 covers CPUs 6-7
(mask 0xC0), lines 40-47 and 266-292. Each driver has two states
(lines 54-96):

| Driver | state 0 | state 1 |
|---|---|---|
| `mtk_acao_cpuidle_set_0` (A55) | `rgidle` "wfi", exit 1, residency 1 | `mcdi`, exit 150, residency 1600, `CPUIDLE_FLAG_TIMER_STOP` |
| `mtk_acao_cpuidle_set_1` (A76) | `rgidle` "wfi", exit 1, residency 1 | `mcdi`, exit 150, residency 1400, `CPUIDLE_FLAG_TIMER_STOP` |

- `rgidle` runs `wfi_enter()` → `__go_to_wfi()`, a plain `wfi` in the
  kernel with no SMC (`mcdi/mcdi_v1/mtk_mcdi_main.c:553-567, 649-668`).
- `mcdi` runs `mcdi_enter()` (`mtk_mcdi_main.c:670-779`). There, the MCDI
  governor picks the real state.

The governor uses a private table of six states (`mtk_mcdi_state.c:102-200`).
All values are exit latency / target residency in microseconds:

| MCDI state | set 0 (A55) | set 1 (A76) | entered via |
|---|---|---|---|
| `wfi` | 1 / 1 | 1 / 1 | `__go_to_wfi()` |
| `cpu_off` | 150 / 1600 | 150 / 1400 | `mtk_enter_idle_state(MTK_MCDI_CPU_MODE)`, `mtk_mcdi_main.c:717` |
| `cluster_off` | 300 / 12500 | 300 / 12500 | `mtk_enter_idle_state(MTK_MCDI_CLUSTER_MODE)`, `mtk_mcdi_main.c:734` |
| `IdleDram` | 1300 / 1900 | 1300 / 2300 | SPM idle model (section 2.3) |
| `IdleSyspll` | 1300 / 1900 | 1300 / 2300 | SPM idle model |
| `IdleBus26m` | 4800 / 1 | 4800 / 1 | SPM idle model |

The governor (`mcdi/mtk_mcdi_governor.c:592-700`) follows these rules:

- It returns WFI while MCDI is disabled, during the first 10 s of uptime
  (`BOOT_TIME_LIMIT`, line 37, check at 605-622) and while the CPU is
  invalid.
- Otherwise it picks `cluster_off` if the latency QoS allows it and
  `cluster_off_check()` passes, else `cpu_off`.
- The last CPU in MCUSYS may try an SPM idle model through
  `any_core_deepidle_sodi_check()` (lines 496-570), when `any_core` is set.
  `mcdi_governor_init()` sets `any_core` through
  `set_mcdi_s_state(MCDI_STATE_SODI3)` (lines 814-848, 903).

### 1.4 The SPM idle models and the suspend state

- The "dram/syspll/bus26m" models are compiled off by default
  (`spm/mt6785/mtk_idle_module_plat.h:30-32`). DT `status = "okay"` on the
  `idledram`, `idlesyspll` and `idlebus26m` nodes turns them on
  (`spm/mt6785/mtk_idle_module_plat.c:20-50`, and for example
  `spm/mt6785/models/mtk_idle_bus26m.c:172-178`).
- `status = "okay"` on the `suspend` node makes the vendor suspend ops valid
  for `mem` (`spm/common/mtk_sleep.c:400-421`, `mtk_lp_dts.h:22-47`).

### 1.5 Topology

MCDI treats MT6785 as one cluster of eight CPUs:

- `NF_CPU 8` and `NF_CLUSTER 1` (`mcdi/mt6785/mtk_mcdi_plat.h:17-18`).
- `cluster_idx_get()` returns 0 for every CPU (`mtk_mcdi_plat.c:82-85`).
- The "all CPUs in cluster" mask is 0xFF (`mtk_mcdi_plat.c:38-48`).

So `mcdi-cluster` (level 1) means the whole DynamIQ cluster (DSU), not the
A55 or the A76 group. The vendor `cpu-map` (`mt6785.dts:130-164`) splits
CPUs 0-5 and 6-7 into two "clusters", but that split only matters to the
scheduler. Mainline already uses a single `cluster0` of eight cores
(`src/mt6785-mainline/arch/arm64/boot/dts/mediatek/mt6785.dtsi:330-364`).
How ATF maps affinity level 1 is unverified.

---

## 2. How each state is entered, and what must be set up first

### 2.1 Entry paths

| State | Kernel path | Firmware call |
|---|---|---|
| `rgidle` / `wfi` | `__go_to_wfi()` | none |
| `cpu_off` | `mcdi_enter()` → `mtk_enter_idle_state(2)` → `arm_cpuidle_suspend(2)` | PSCI `CPU_SUSPEND` (SMC64 0xC4000001) with `power_state` 0x00010001 |
| `cluster_off` | `mcdi_enter()` → `mtk_enter_idle_state(3)` | `CPU_SUSPEND` 0x01010001 |
| `IdleDram` / `IdleSyspll` / `IdleBus26m` | `mtk_idle_pre_process_by_chip()` → `mtk_idle_trigger_wfi()` → `mtk_enter_idle_state(4/5/6)` (`spm/mt6785/mtk_spm_idle.c:154-203, 238-271`) | SMC `SPM_LP_ARGS` (section 2.2), then `CPU_SUSPEND` 0x01010002 / 0x01010003 / 0x01010004 |
| `suspend` | `slp_suspend_ops_enter()` → `spm_go_to_sleep_ex()` → `spm_trigger_wfi_for_sleep()` → `mtk_enter_idle_state(7)` (`spm/mt6785/mtk_spm_suspend.c:137-159`) | SMCs in section 5, then `CPU_SUSPEND` 0x01010005 |

All the SPM flag sets the vendor uses leave `SPM_FLAG_DISABLE_CPU_PDN` clear,
so `is_cpu_pdn()` is true (`spm/mt6785/sleep_def.h:22, 162`). The alternative
branch, with `SPM_LEGACY_SLEEP` and no PSCI (`mtk_spm_suspend.c:144-150`,
`mtk_spm_idle.c:187-194`), is therefore never taken on MT6785.

`PSCI_0_2_FN64_CPU_SUSPEND` is 0x84000000 + 0x40000000 + 1
(`include/uapi/linux/psci.h:26-31, 44` in mainline).

### 2.2 SMC catalogue (MediaTek SiP)

On arm64, `MTK_SIP_SMC_AARCH_BIT` is 0x40000000, so `0x82000xxx` becomes
`0xC2000xxx` (`drivers/misc/mediatek/include/mt-plat/mtk_secure_api.h:27-31`).
The call is `mt_secure_call(id, a0, a1, a2, a3)` (same file, lines 305-310).

| ID | Name (`mtk_secure_api.h` line) | Arguments as used for MT6785 | Where |
|---|---|---|---|
| 0xC2000214 | `MTK_SIP_POWER_FLOW_DEBUG` (65) | (0, 2, footprint PA) with RAM console; (0, 1, buffer) for profiling | `cpuidle_v3/mtk_cpuidle.c:64, 225-226` |
| 0xC2000220 | `MTK_SIP_KERNEL_SPM_SUSPEND_ARGS` (72) | (pcm_flags, pcm_flags1, timer_val, resource_usage) | `spm/mt6785/mtk_spm_suspend.c:188-189` |
| 0xC2000221 | `MTK_SIP_KERNEL_SPM_FIRMWARE_STATUS` (74) | () → -1 not init, 0 not loaded, 1 loaded, 2 loaded and kicked | `spm/mt6785/mtk_spm_utils.c:36-44` |
| 0xC2000222 | `MTK_SIP_KERNEL_SPM_IRQ0_HANDLER` (76) | (ISR status) to clear the SPM IRQ | `spm/mt6785/mtk_spm_irq.c:225` |
| 0xC200022A | `MTK_SIP_KERNEL_SPM_ARGS` (99) | a0 = `SPM_ARGS_*` (`spm/mt6785/mtk_spm_internal.h:126-144`): 0 `SPMFW_IDX_KICK` (idx, DRAM freq); 8 `PCM_WDT` (1, 30) / (0, 0) | `spm/mt6785/mtk_spm.c:415-418`; `mtk_spm_suspend.c:375, 471` |
| 0xC200022B | `MTK_SIP_KERNEL_SPM_GET_PWR_CTRL_ARGS` (103) | (17 `SPM_PWR_CTRL_SUSPEND`, 12 `PW_WAKE_SRC`, 0) → wake-source mask | `mtk_spm_suspend.c:361-362`; enums in `mtk_spm_internal.h:157-183`, `pwr_ctrl.h:269-282` |
| 0xC200022E | `MTK_SIP_KERNEL_SPM_LP_ARGS` (115) | (0xDAF10000 + idle type: 0 bus26m, 1 syspll, 2 dram; pcm_flags; pcm_flags1; resource_usage) | `spm/mt6785/mtk_spm_idle.c:211-224`; magic at `mtk_spm_internal.h:99` |
| 0xC2000231 | `MTK_SIP_KERNEL_MCDI_ARGS` (129) | a0 = event (`mcdi/include/mcdi_v1/mtk_mcdi.h:17-27`): 3 `LAST_CORE_CLR` (mask 1<<9 or 1<<8); 4 `GIC_DPG_SET` (CPU isolation mask); 5 `CPC_CONFIG` with a1 = 0 PROF, 1 AUTO_OFF, 2 AUTO_OFF_THRES (13 MHz ticks), 3 CNT_CLR | `mcdi/mtk_mcdi_governor_lib.c:37-41`; `mcdi/mcdi_v1/mtk_mcdi_util.c:159-162, 197-200`; `mcdi/mcdi_v1/mtk_mcdi_cpc.c:110-134` |
| 0xC2000226 | `MTK_SIP_KERNEL_SPM_VCOREFS_ARGS` (84) | VCORE DVFS, not idle | `spm/common/mtk_vcore_dvfs.c:23-57` |

`SPM_LEGACY_SLEEP` (0xC2000225), `SPM_AP_MDSRC_REQ` (0xC2000223, modem) and
`MCUPM_FW_LOAD_STATUS` (0xC2000234) exist, but MT6785 idle does not use
them.

### 2.3 Firmware: what the kernel loads (nothing) and what it talks to

- **SPM PCM firmware.** The kernel does not load it. `request_firmware` does
  not appear in `spm/`, `mcdi/`, `cpuidle_v3/`, `sspm/` or `mcupm/`. The
  kernel asks ATF for its state (`FIRMWARE_STATUS`, above) and, at
  `late_initcall`, asks ATF to kick it. The call is
  `SMC_CALL(ARGS, SPM_ARGS_SPMFW_IDX_KICK, spm_get_spmfw_idx(), dram_steps_freq(0))`
  (`mtk_spm.c:415-418`, enabled by `MTK_FEATURE_EANABLE_KICK_SPMFW 1` at
  `mtk_spm_internal.h:40`). The index is 0 (`spm/mt6785/mtk_spm_dram.c:49-55`).
  The DRAM frequency comes from the DRAMC driver, which `MACH_MT6785`
  selects (`arch/arm64/Kconfig.platforms`, **(remote)**). SPM idle requires
  status 2 (`spm/common/mtk_idle_select.c:130-138`) and suspend requires
  status ≥ 1 (`spm/common/mtk_sleep.c:223-227`). The unit has an `spmfw`
  partition (`docs/research/notes/bootloader_unlock_fastboot.md:209`). Which
  boot stage loads it, and whether mainline boots with status 1, is
  unverified.
- **SSPM.** The kernel does not load SSPM firmware either: the v1 driver's
  probe only maps `cfgreg`, the IPI IRQ and the reserved memory
  (`drivers/misc/mediatek/sspm/v1/sspm_helper.c:177-237`). The `sspm_1` and
  `sspm_2` partitions exist (same notes file, line 209). MT6785 uses
  `CONFIG_MTK_TINYSYS_SSPM_SUPPORT=y` with `CONFIG_MTK_TINYSYS_SSPM_VERSION="v1"`
  (`arch/arm64/configs/yoga11_defconfig:213-214`). The kernel uses the SSPM
  in two ways:
  - **MCDI mailbox.** Mailbox 3 (`MCDI_MBOX 3`; slots in
    `mcdi/mt6785/mtk_mcdi_reg.h:97-127`), written with `sspm_mbox_write()`
    at `mbox_base + 4 × slot` (`sspm/v1/sspm_mbox.c:71-81`,
    `sspm_define.h:22`). The vendor DT puts `mbox3_base` at 0x10480000
    (`mt6785.dts`, `sspm@10400000`, lines 1985-2040). So slot 7
    (`AVAIL_CPU_MASK`) is 0x1048001C, slot 9 (`ACTION_STAT`, written by the
    SSPM) is 0x10480024 and slot 17 (`AP_READY`) is 0x10480044.
  - **Suspend IPI.** `IPI_ID_SPM_SUSPEND = 7` (`sspm/v1/sspm_ipi_pin.h:25-26`),
    sent synchronously with `SPM_SUSPEND` / `SPM_RESUME` around system
    suspend (`spm/mt6785/mtk_sspm.c:86-110`,
    `spm/mt6785/mtk_spm_suspend_process.c:123-182`).
- **MCUPM.** Not used on MT6785. `MCDI_MCUPM_INTF` is commented out and
  `MCDI_SSPM_INTF` is selected (`mcdi/mt6785/mtk_mcdi_plat.h:34-36`).
  `drivers/misc/mediatek/mcupm/` is only built with
  `CONFIG_MTK_TINYSYS_MCUPM_SUPPORT` (`drivers/misc/mediatek/Makefile:56`),
  and that option is absent from `yoga11_defconfig`.
- **MCDI "firmware".** On MT6785, MCDI runs in "CPC mode" (`MCDI_CPC_MODE`,
  `mtk_mcdi_plat.h:32`). The CPU Power Controller sits in MCUSYS at
  0x0C53A000 (`mtk_mcdi_reg.h:56-90`; DT node `mediatek,mt6785-mcdi`,
  `mt6785.dts:1204-1209`, reg 1). In CPC mode `mcdi_task_pause()` returns
  immediately and no SSPM handshake happens (`mcdi/mtk_mcdi_api.c:28-31`).
  The 2 KiB at 0x0011B000 (DT reg 0, `MCDI_SYSRAM_SIZE 0x800`,
  `mtk_mcdi_reg.h:19`) is a profiling and latency area that firmware writes
  (`mtk_mcdi_reg.h:23-37`). The kernel only clears it.

### 2.4 Kernel-side setup before the first CPU_SUSPEND (vendor order)

1. `subsys_initcall mcdi_sysram_init()` (`mtk_mcdi_main.c:864-879`):
   - It maps the SYSRAM and the CPC and reads `mediatek,enabled`
     (`mtk_mcdi_plat.c:101-137`).
   - It clears 0x0011B008-0x0011B7FF with `memset_io`.
   - If the CPC cannot be mapped, it calls `disable_cpuidle()` (line 136).
2. `device_initcall mtk_acao_cpuidle_init()` **(remote)** registers the two
   MTK drivers and fills the per-CPU PSCI table from the DT (section 1.2).
   From then on, idle is WFI only, because MCDI is not yet enabled.
3. `late_initcall mtk_sleep_init()` (`spm/common/mtk_sleep_init.c:29-40`)
   does three things:
   - `slp_module_init()` installs `slp_suspend_ops` (`mtk_sleep.c:437`).
   - `mtk_spm_init()` (`mtk_spm.c:425-431`) runs `mtk_cpuidle_init()`. That
     sets `mtk_cpuidle_initialized`; without it `mtk_enter_idle_state()`
     returns `-EOPNOTSUPP`, see `mtk_cpuidle.c:320-321, 359-375`.
   - It then registers the SPM IRQ (SPI 213, `mtk_spm_irq.c:253-289`) and
     the edge-IRQ list, and **kicks the SPM firmware** (SMC 0xC200022A,
     a0 = 0).
   `spm/` links before `mcdi/` (`base/power/Makefile:28` against line 117),
   so this runs before step 4.
4. `late_initcall mcdi_init()` (`mtk_mcdi_main.c:882-908`):
   - `mcdi_cpc_init()` (`mtk_mcdi_cpc.c:510-531`) sends SMC 0xC2000231
     (5, 2, 104000), the CPC auto-off threshold of 8 ms × 13 ticks/us, then
     SMC 0xC2000231 (5, 1, 0), auto-off disabled.
   - `mcdi_governor_init()` (`mtk_mcdi_governor.c:873-913`) writes the
     online CPU mask to SSPM slot 7 (`mcdi_avail_cpu_cluster_update()`,
     lines 745-796), enables MCDI from the DT (`mcdi_status_init()`) and
     sets the deepest state to SODI3, which turns on `cluster_off` and
     `any_core`.
   - `mcdi_cpu_iso_mask(0)` sends SMC 0xC2000231 (4, 0), the GIC DPG
     isolation mask (`mtk_mcdi_api.c:20-26`, `mtk_mcdi_util.c:186-201`).
   - CPU hotplug callbacks re-send the mask on every CPU up or down
     (`mtk_mcdi_main.c:831-858`).
5. After 10 s of uptime, the first `mcdi_governor_select()` writes 1 to
   SSPM slot 17, `AP_READY` (`mtk_mcdi_governor.c:605-622`;
   `mtk_mcdi_governor_lib.c:128-131`). Only then can `cpu_off` or
   `cluster_off` be chosen.
6. At run time, on every exit from `mcdi_enter()`, including WFI, the
   kernel writes `1 << cpu` to `CPC_CPU_ON_SW_HINT_CLR` at 0x0C53A8AC
   (`mtk_mcdi_governor.c:708` → `mtk_mcdi_cpc.c:360-364`).
7. The last-core protocol for SPM idle is a non-secure write of
   `CPC_LAST_CORE_REQ` at 0x0C53A818, then a poll of the response at
   0x0C53A824 (`mtk_mcdi_governor_lib.c:60-100`). It is released by SMC
   (5... event 3). Cluster-off needs no such request:
   `cpc_cpusys_off_hw_prot()` is 1, meaning hardware protection
   (`mtk_mcdi_plat.h:57`, `mtk_mcdi_governor_lib.c:102-125`).

---

## 3. What can work from mainline with a DT change only

### 3.1 What was already tried (BOARD.md, 2026-11-16)

- **Stock encodings.** `mcdi-cpu` 0x10001 and `mcdi-cluster` 0x1010001 with
  `local-timer-stop` hung the kernel about 1.9 s after boot, at the first
  idle.
- **One state at a time.** With the states disabled by default and enabled
  one by one, `standby` (0x1) on CPU7 alone froze the whole system, without
  a watchdog reset.
- **Firmware mode.** PSCI is v1.1 in platform-coordinated mode, with no OSI
  (`docs/hardware/BOARD.md:541-552`).

The project then added a WFI-only driver with an s2idle state
(`src/mt6785-mainline/drivers/cpuidle/cpuidle-wfi-s2idle.c:31-77`;
`kernel/configs/yoga11.config:101-103`; BOARD.md:553-562).

### 3.2 Per-state verdict

| State | What the vendor does before using it | DT only? |
|---|---|---|
| `standby` 0x1 | Never uses it (section 1.2) | No. Untested by the vendor, and it froze the unit (BOARD.md:546-548) |
| `mcdi-cpu` 0x10001 | Steps 1-5 of section 2.4; first use ≥ 10 s after boot | Plausible only if ATF needs none of steps 1-5. The 2026-11-16 hang says it needs at least one (unverified which) |
| `mcdi-cluster` 0x1010001 | Same, plus CPC hardware coordination of the last core | Same as `mcdi-cpu`, with more risk (no CPU left to report a hang) |
| `idledram`, `idlesyspll`, `idlebus26m` 0x1010002-4 | SPM firmware status 2; SMC `SPM_LP_ARGS` with per-model PCM flags; GIC mask and CIRQ clone; clock and PLL condition checks (`spm/mt6785/mtk_idle_cond_check.c`); last-core request | No: needs a driver |
| `suspend` 0x1010005 | Section 5 | No: needs a driver |

The PCM flags for the SPM idle models (`mtk_spm_idle.c:53-105`, bits from
`sleep_def.h:22-78`, SSPM support built in) are:

| Model | `pcm_flags` | `pcm_flags1` |
|---|---|---|
| bus26m | 0x211A | 0x00C00380 |
| syspll | 0x411A | 0x00C00380 |
| dram | 0x011A | 0x00C00380 |

### 3.3 Why the DT-only attempt probably hung (hypotheses, all unverified)

ATF's source is not in the trees, so these are ranked guesses:

- **H1: missing handshake.** ATF's `CPU_SUSPEND` handler depends on state
  that the vendor kernel sets up: SPM firmware kicked, CPC configured by
  `MCDI_ARGS`, SSPM told `AVAIL_CPU_MASK` and `AP_READY`. Without it, ATF
  spins in EL3. If that loop holds a lock that other CPUs' SMCs need, the
  whole system freezes at once, as observed even for `standby` on one CPU.
  The vendor's 10 s delay and `AP_READY` write (section 2.4, step 5) point
  this way.
- **H2: no standby handler.** ATF has no real standby path for StateID 1 at
  level 0, since the vendor never uses one. It might route it through the
  same MCDI path as H1.
- **H3: no wake.** The core enters and is never woken: nothing re-powers it.
  The other CPUs then block on the first synchronous IPI they send to it.
  This should show RCU stall messages if the console lives long enough.
  BOARD.md does not record any.

### 3.4 Format check: original or extended StateID

Mainline treats bit 16 as "loses context" only if ATF reports the original
format. If the extended format is reported, bit 30 is the type bit
(`src/mt6785-mainline/drivers/firmware/psci/psci.c:83-110`;
`include/uapi/linux/psci.h:85-89`). The vendor encodings only make sense in
the original format. `/sys/kernel/debug/psci` prints "Original/Extended
StateID format" (`psci.c:424-432`). BOARD.md records "v1.1, no OSI" but not
the format: read it before any retry.

### 3.5 Comparison with mainline MediaTek SoCs

From `src/mt6785-mainline/arch/arm64/boot/dts/mediatek/`:

| SoC (file:lines) | States (name: `arm,psci-suspend-param`, exit / residency in us) | `local-timer-stop` |
|---|---|---|
| mt8183 (`mt8183.dtsi:511-537`) | `cpu-sleep` 0x00010001 (200 / 800); `cluster-sleep-0` 0x01010001 (400 / 1000); `cluster-sleep-1` 0x01010001 (400 / 1300) | yes |
| mt8186 (`mt8186.dtsi:566-602`) | `cpu-retention-l/b` 0x00010001 (100 / 1600 and 1400); `cpu-off-l/b` 0x01010001 (250 / 2100 and 1900) | yes |
| mt8365 (`mt8365.dtsi:222-249`) | `cpu-mcdi` 0x00010001 (200 / 1000); `cluster-mcdi` 0x01010001 (250 / 1200); `cluster-dpidle` 0x01010004 (800 / 3300) | yes |
| mt8192 (`mt8192.dtsi:271-303`) | `cpu-retention-l/b` 0x00010001; `cpu-off-l/b` 0x01010002 | yes |
| mt8195 (`mt8195.dtsi:243-279`) | `cpu-retention-l/b` 0x00010001; `cpu-off-l/b` 0x01010002 | yes |
| mt8188 (`mt8188.dtsi:252-288`) | `cpu-off-l/b` 0x00010000; `cluster-off-l/b` 0x01010010 | yes |
| mt8173 (`mt8173.dtsi:211-221`) | `cpu-sleep-0` 0x0010000 (680 / 1088) | yes |
| mt2712e (`mt2712e.dtsi:123-141`) | `cpu-sleep-0` 0x0010000; `cluster-sleep-0` 0x1010000 | yes |
| mt8516 (`mt8516.dtsi:102-118`) | `cpu-sleep-0-0` 0x0010000 (600 / 600 / 1200); `cluster-sleep-0` 0x2010000 (800 / 1000 / 2000) | n/a |
| mt6779, mt6795, mt6797 | no `idle-states` | n/a |

Observations:

- mt8183, mt8186 and mt8365 use exactly the MT6785 encodings for core-off
  and cluster-off. mt8365 even uses StateID 4 at cluster level for its
  SPM deep-idle state, like `idlebus26m`.
- mt8516's latencies are the vendor MT6785 DT values word for word.
- Several SoCs name 0x00010001 "retention" although bit 16 marks it as a
  power-down.
- Every mainline user is a Chromebook or IoT board. None of the MediaTek
  phone SoCs in mainline (mt6779, mt6795, mt6797) has idle states. The
  assumption that on those boards the boot firmware (coreboot or U-Boot plus
  TF-A) loads and starts SPM, SSPM and MCDI by itself, leaving the kernel
  only PSCI, is not shown by these trees and is unverified. On MT6785
  Android, part of that work is in the vendor kernel (section 2.4).
- No mainline driver speaks MCDI, SPM low power or SSPM: a grep of
  `drivers/soc/mediatek`, `drivers/firmware`, `drivers/cpuidle`,
  `drivers/mailbox` and `drivers/remoteproc` for `mcdi`, `sspm` and
  `MTK_SIP_KERNEL_SPM` finds nothing.

---

## 4. Candidate DT fragments

### 4.1 Before flashing anything

**Read-only probes.** No DT change; mostly sysfs/debugfs reads plus a
CPU-hotplug test (step 4) and a probe module (steps 3 and 5):

1. `/sys/kernel/debug/psci`. Expect "Original StateID format" and "OSI is
   not supported". If it says Extended, the vendor encodings are wrong for
   Linux: stop.
2. `/proc/timer_list`. The broadcast device should be `mtk-clkevt`
   (section 6.2).
3. SMC 0xC2000221 from a throwaway module, like
   `kernel/experiments/dcxo-poke`. 1 means loaded but not kicked; 2 means
   kicked. The SMC only reports a state; that it changes nothing is
   unverified.
4. CPU7 hotplug off and back on. This is PSCI `CPU_OFF` and `CPU_ON` on the
   same CPC power-down hardware as `mcdi-cpu`. If it fails, idle power-down
   cannot work either.
5. Reads of `CPC_SPMC_PWR_STATUS` at 0x0C53A840 and of SSPM mailbox 3,
   slot 9 (`ACTION_STAT`) at 0x10480024: is the SSPM's MCDI side alive
   (states 0-3 in `mtk_mcdi_reg.h:123-127`)? Reaching these from the
   normal world is how the vendor does it; that mainline can too is
   unverified.

**Replay the vendor init in a module** (proposal, not a vendor fact; values
from section 2.4). Load it more than 10 s after boot, before any idle state
is enabled:

1. SMC 0xC200022A (0, 0, DRAM freq). The DRAM frequency value is
   unverified; the vendor's fallback without DRAMC is 4266
   (`mtk_spm.c:37-44`).
2. SMC 0xC2000231 (5, 2, 104000).
3. SMC 0xC2000231 (5, 1, 0).
4. SMC 0xC2000231 (4, 0).
5. Write 0xFF to 0x1048001C and 1 to 0x10480044.

Kicking the SPM firmware starts code whose effect on a mainline system
(VCORE, DVFSRC) is unknown. Do it with the unit on USB power and the
fastboot recovery ready.

**Keep the states off by default** and enable them per CPU in
`/sys/devices/system/cpu/cpuN/cpuidle/stateM/disable`, as the 2026-11-16
experiment did. The DT has no property for that; it takes a small patch
setting `CPUIDLE_FLAG_OFF` (`include/linux/cpuidle.h:85`).
`cpuidle-psci` needs states on every present CPU, or its probe fails for
all of them (`drivers/cpuidle/cpuidle-psci.c:399-401, 437-440`). So the
fragments give the states to all eight CPUs.

**Side effect: s2idle timekeeping.** With valid DT states, `cpuidle-psci`
registers instead of the WFI s2idle driver, which only binds when no other
driver exists (`cpuidle-wfi-s2idle.c:62-64`). In platform-coordinated mode
`cpuidle-psci` sets `enter_s2idle` only in the OSI hierarchy
(`cpuidle-psci.c:253-271`). So s2idle would again stop freezing
timekeeping (BOARD.md:528-540), unless `cpuidle-psci` is patched to give
its deepest flat state an `enter_s2idle`.

The kernel config is already in place: `CONFIG_CPU_IDLE`,
`CONFIG_DT_IDLE_STATES`, `CONFIG_ARM_PSCI_CPUIDLE`, and the tick broadcast
(`kernel/configs/pmos-mt6785.config:73-75, 610-622`).

### 4.2 Fragment A: core power-down only (try first)

To append to `arch/arm64/boot/dts/mediatek/mt6785-lenovo-yt-j706f.dts` (it
could later move into `mt6785.dtsi`).

`standby` is left out on purpose: the vendor never uses it, and it froze the
unit. The latencies are the vendor DT values for `mcdi-cpu`. The residencies
are the ones the vendor governor actually uses (`mtk_mcdi_state.c:114-120`,
`162-168`). Names follow mt8186/mt8192.

```dts
/*
 * Fragment A: per-core power-down only (vendor "mcdi-cpu",
 * MCDI_STATE_CPU_OFF). Append to mt6785-lenovo-yt-j706f.dts.
 */
&{/cpus} {
	idle-states {
		entry-method = "psci";

		cpu_off_l: cpu-off-l {
			compatible = "arm,idle-state";
			idle-state-name = "mcdi-cpu";
			arm,psci-suspend-param = <0x00010001>;
			local-timer-stop;
			entry-latency-us = <600>;
			exit-latency-us = <600>;
			min-residency-us = <1600>;
		};

		cpu_off_b: cpu-off-b {
			compatible = "arm,idle-state";
			idle-state-name = "mcdi-cpu";
			arm,psci-suspend-param = <0x00010001>;
			local-timer-stop;
			entry-latency-us = <600>;
			exit-latency-us = <600>;
			min-residency-us = <1400>;
		};
	};
};

&cpu0 {
	cpu-idle-states = <&cpu_off_l>;
};

&cpu1 {
	cpu-idle-states = <&cpu_off_l>;
};

&cpu2 {
	cpu-idle-states = <&cpu_off_l>;
};

&cpu3 {
	cpu-idle-states = <&cpu_off_l>;
};

&cpu4 {
	cpu-idle-states = <&cpu_off_l>;
};

&cpu5 {
	cpu-idle-states = <&cpu_off_l>;
};

&cpu6 {
	cpu-idle-states = <&cpu_off_b>;
};

&cpu7 {
	cpu-idle-states = <&cpu_off_b>;
};
```

Expected failure modes for A, in order of likelihood given section 3:

1. **Hang at entry.** The first `CPU_SUSPEND` never returns and other CPUs
   stop at their next SMC. The console stops, with no watchdog reset: the
   2026-11-16 symptom, which supports H1. Next step: the init replay of
   section 4.1, or a narrower subset of it.
2. **No wake.** The core powers down and stays off. Other CPUs report RCU
   stalls naming that CPU about 21 s later, then block on a synchronous IPI
   to it. Enabling the state on CPU7 only and watching
   `cpuidle/state1/usage` tells this apart from point 1.
3. **Refused.** ATF answers DENIED or INVALID_PARAMETERS. `rejected`
   increases in sysfs, `usage` does not, and the system stays healthy:
   harmless, but no gain.
4. **Late timers.** Timers fire late (for example, `sleep 1` overshoots)
   if the broadcast through SYST does not work. Check `/proc/timer_list`
   (section 6).
5. **Crash after the first wake.** Random oops if ATF reports the extended
   StateID format: Linux would not save context. Probe 1 of section 4.1
   rules this out.

### 4.3 Fragment B: core power-down plus cluster power-down

This replaces fragment A. Cluster means the whole DSU, all eight cores
(section 1.5). Platform-coordinated mode lets every CPU vote for
cluster-off; firmware demotes to core-off while other cores are awake, as
on mt8183. The cluster latencies are the vendor DT values; the residency is
the MCDI `cluster_off` 12500 us (`mtk_mcdi_state.c:121-127`).

```dts
/*
 * Fragment B: core power-down plus cluster (DSU, all 8 cores) power-down
 * (vendor "mcdi-cpu" + "mcdi-cluster"). Replaces fragment A.
 */
&{/cpus} {
	idle-states {
		entry-method = "psci";

		cpu_off_l: cpu-off-l {
			compatible = "arm,idle-state";
			idle-state-name = "mcdi-cpu";
			arm,psci-suspend-param = <0x00010001>;
			local-timer-stop;
			entry-latency-us = <600>;
			exit-latency-us = <600>;
			min-residency-us = <1600>;
		};

		cpu_off_b: cpu-off-b {
			compatible = "arm,idle-state";
			idle-state-name = "mcdi-cpu";
			arm,psci-suspend-param = <0x00010001>;
			local-timer-stop;
			entry-latency-us = <600>;
			exit-latency-us = <600>;
			min-residency-us = <1400>;
		};

		cluster_off: cluster-off {
			compatible = "arm,idle-state";
			idle-state-name = "mcdi-cluster";
			arm,psci-suspend-param = <0x01010001>;
			local-timer-stop;
			entry-latency-us = <600>;
			exit-latency-us = <600>;
			min-residency-us = <12500>;
		};
	};
};

&cpu0 {
	cpu-idle-states = <&cpu_off_l &cluster_off>;
};

&cpu1 {
	cpu-idle-states = <&cpu_off_l &cluster_off>;
};

&cpu2 {
	cpu-idle-states = <&cpu_off_l &cluster_off>;
};

&cpu3 {
	cpu-idle-states = <&cpu_off_l &cluster_off>;
};

&cpu4 {
	cpu-idle-states = <&cpu_off_l &cluster_off>;
};

&cpu5 {
	cpu-idle-states = <&cpu_off_l &cluster_off>;
};

&cpu6 {
	cpu-idle-states = <&cpu_off_b &cluster_off>;
};

&cpu7 {
	cpu-idle-states = <&cpu_off_b &cluster_off>;
};
```

Failure modes for B, beyond those of A:

1. **The cluster never comes back.** As soon as all eight CPUs are idle
   together (an idle desktop within seconds), nothing re-powers MCUSYS. That
   is a total freeze with no CPU left to print a stall. If only a touch or a
   key press revives the unit, the CPC wake path works but the timer wake
   does not: the SYST interrupt (SPI 224) reaches nobody.
2. **Lost interrupts.** Edge interrupts are lost if cluster-off also gates
   the GIC. The vendor arms the CIRQ only in the SPM paths
   (`mtk_spm_irq.c:158-185`, called from `mtk_spm_idle.c:262` and
   `mtk_spm_suspend.c:388`), not for MCDI cluster-off. That suggests the GIC
   stays powered in cluster-off (inference, unverified).
3. **Wasted cluster-off.** Without the vendor governor's cross-CPU residency
   check and hrtimer (`mtk_mcdi_governor.c:228-289, 420-460`), `menu`
   picks cluster-off from one CPU's view. Firmware demotes or aborts, which
   costs latency but should be harmless.

Validation: each fragment was appended to a skeleton DTS with the same
`/cpus` node and the same `cpu0`..`cpu7` labels and node addresses as
`mt6785.dtsi:326-541`. Both compile with dtc 1.8.1, with no warnings. The
`&{/cpus}` path reference works because the mainline `cpus` node has no
label.

---

## 5. System suspend ("deep")

### 5.1 What the vendor does

`mem` is handled by MediaTek's own `platform_suspend_ops`, installed at
`late_initcall`: `slp_suspend_ops` (`spm/common/mtk_sleep.c:282-289, 437`).
The generic suspend code takes the secondary CPUs offline before calling
`->enter` (mainline `kernel/power/suspend.c:453, 468`). So the following
runs on the boot CPU:

1. **Checks** (`mtk_sleep.c:177-264`). Infra PDN without CPU PDN is
   refused, as is an SSPM IPI that holds the SPM lock. The SPM firmware
   status must be ≥ 1 (SMC 0xC2000221). `mcdi_task_pause(true)` is a no-op
   in CPC mode.
2. **Flags** (`spm_go_to_sleep_ex()`, `spm/mt6785/mtk_spm_suspend.c:333-488`):
   - The wake-source mask comes from ATF: SMC 0xC200022B (17, 12, 0).
   - `pcm_flags` is `DISABLE_VCORE_DVS | DISABLE_VCORE_DFS` = 0x18. Without
     SSPM support, `DISABLE_SSPM_SRAM_SLEEP` would be added, giving 0x20018.
   - `pcm_flags1` is `ENABLE_BIG_BUCK_OFF | ENABLE_BIG_BUCK_ON |
     FORCE_CPU_BUCK_OFF | DISABLE_VS1_VOTER | DISABLE_VS2_VOTER` =
     0x00C00380 (lines 92-106; bits in `sleep_def.h`).
   - The wake timer is in 32 kHz ticks (`timer_val`, lines 369-372 and
     186).
3. **SPM watchdog.** The PCM watchdog is armed for 30 s: SMC 0xC200022A
   (8, 1, 30) (line 375).
4. **Interrupts** (`mtk_spm_irq_backup()`, `mtk_spm_irq.c:158-172`). All
   GIC interrupts are masked except the SPM IRQ and the edge-wake list. That
   list holds keypad and modem WDT (`mtk_spm_irq_edge.h:28-31`). The CIRQ
   at 0x10204000 (277 lines, SPI offset 64, `mt6785.dts:1282-1289`) then
   clones the GIC and is enabled. `MACH_MT6785` selects `MTK_SYS_CIRQ` and
   `MTK_GIC_V3_EXT` (`arch/arm64/Kconfig.platforms`, **(remote)**).
5. **SSPM.** An IPI `SPM_SUSPEND` goes to the SSPM (IPI 7, synchronous,
   polling) (`mtk_spm_suspend_process.c:123-160`).
6. **ATF setup.** SMC 0xC2000220 (pcm_flags, pcm_flags1, timer_val,
   resource_usage) (`mtk_spm_suspend.c:161-190`).
7. **UART.** The UART is asked to sleep (line 418).
8. **Entry.** `mtk_enter_idle_state(MTK_SUSPEND_MODE)` →
   `CPU_SUSPEND(0x01010005)` (line 143).
9. **Resume.** The kernel reads the wake status from SPM registers, sends
   an IPI `SPM_RESUME` to the SSPM, flushes and disables the CIRQ,
   restores the GIC masks and disarms the PCM watchdog with SMC 0xC200022A
   (8, 0, 0) (lines 437-471).

Firmware involved: the SPM PCM firmware, ATF (the SMC handlers and PSCI) and
the SSPM firmware (the IPI). The kernel loads none of them (section 2.3).

### 5.2 PSCI SYSTEM_SUSPEND

**Vendor.** The 4.14 `psci_init_system_suspend()` installs
`psci_suspend_ops` when `PSCI_FEATURES(SYSTEM_SUSPEND)` is not
NOT_SUPPORTED (`drivers/firmware/psci.c`, about lines 478-500,
**(remote)**). MediaTek's `late_initcall` then replaces them with
`slp_suspend_ops`. No reference to `SYSTEM_SUSPEND` or `psci_` exists in
the vendor power code examined. The vendor kernel never calls it.

**Mainline.** `mem_sleep` offers `deep` on the unit (BOARD.md:497-503).
On this arm64 configuration, the only caller of `suspend_set_ops()` is
`psci_init_system_suspend()` (`drivers/firmware/psci/psci.c:582-593`; the
other callers in the tree are ACPI, PowerMac, Loongson, Broadcom and TI
code). So ATF does answer `PSCI_FEATURES(SYSTEM_SUSPEND)` as supported.
Calling it (0xC400000E, `include/uapi/linux/psci.h:66`) never came back on
the unit, and nothing was left in pstore (BOARD.md:497-503).

What ATF does in `SYSTEM_SUSPEND` is unverified. A plausible reading is that
it reaches the same SPM path as `CPU_SUSPEND(0x01010005)`, without the PCM
flags, timer, SSPM IPI and CIRQ that the vendor sets up first.

### 5.3 What a mainline "deep" would need

In order of dependency, all inferred from section 5.1:

1. SPM firmware kicked (status 2).
2. The `SPM_SUSPEND_ARGS` SMC with the flags above, plus the PCM watchdog
   SMCs.
3. An SSPM mailbox and IPI driver able to send IPI 7 `SPM_SUSPEND` /
   `SPM_RESUME`. Mainline has none.
4. CIRQ support. Mainline's `irq-mtk-cirq.c` knows mt2701, mt8135, mt8173
   and mt8192 (`drivers/irqchip/irq-mtk-cirq.c:292-298`), and no arm64
   mainline DT uses it. Which register layout the MT6785 CIRQ has (v1 or
   v2) is unverified.
5. A `platform_suspend_ops` that ends in `CPU_SUSPEND(0x01010005)`, as the
   vendor's does. Alternatively, `SYSTEM_SUSPEND` could be retried once
   steps 1-4 are in place.
6. Wake-reason readout from the SPM registers at 0x10006000 (mainline maps
   that block as the `scpsys` syscon, `mt6785.dtsi:920-924`).

Step 3 is the largest piece; `docs/hardware/BOARD.md:563-573` already
identifies the SPM as the blocker for the ~132 mA floor.

---

## 6. The timer during deep idle states

### 6.1 Vendor

- **Broadcast is required.** The MCDI state is flagged
  `CPUIDLE_FLAG_TIMER_STOP` (`mtk_mcdi_state.c:68, 90`), so the tick core
  hands the CPU's timer to the broadcast device. The arch timer node has no
  `always-on` (`mt6785.dts:761-768`, `clock-frequency` 13 MHz).
- **Broadcast device.** It is the SoC system timer `mediatek,sys_timer` at
  0x10017000 (SPI 224, `TOP_CLK13M`, `mt6785.dts:753-759`). Its driver is
  `drivers/clocksource/mtk_systimer.c` **(remote)**:
  - clockevent `mtk-clkevt`, rating 300;
  - `CLOCK_EVT_FEAT_ONESHOT | CLOCK_EVT_FEAT_DYNIRQ`, `cpumask =
    cpu_possible_mask`;
  - compare registers at base + 0x40;
  - registered with `CLOCKSOURCE_OF_DECLARE`, with comments calling it the
    "SoC timer for tick-broadcasting (oneshot)".
  `MACH_MT6785` selects `MTK_TIMER_SYSTIMER` and not `MTK_TIMER_APXGPT`
  (**(remote)**).
- **MCDI hrtimer.** For cluster-off, the MCDI governor also arms its own
  hrtimer to re-check residency (`mtk_mcdi_governor.c:214-289`).
- **Suspend.** The SPM's own 32 kHz PCM timer (`timer_val`; 32768 ticks/s
  and a 30 s PCM watchdog, `mtk_spm_internal.h:65-72`) wakes the system.
  The kernel logs the 13 MHz system counter ("world clock",
  0x10017008/0x1001700C, `mtk_spm_internal.h:62-63`;
  `mtk_spm_suspend_process.c:72-83`). For the 26 MHz-off states
  (`idlebus26m`, `suspend`), the SYST is clocked from 13 MHz, which derives
  from 26 MHz. That it stops there, leaving the SPM PCM timer as the only
  timed wake, is inferred and unverified.

### 6.2 Mainline

- **SYST node.** `systimer: timer@10017000` is `"mediatek,mt6785-timer",
  "mediatek,mt6765-timer"`, SPI 224, clocked by `clk13m`
  (`mt6785.dtsi:1073-1078`). `clk13m` is 26 MHz / 2 (`mt6785.dtsi:792-799`).
- **Driver.** `mtk_syst_init()` registers the same block (`SYST_BASE`
  0x40) as `mtk-clkevt`: rating 300, `ONESHOT | DYNIRQ`, `cpumask =
  cpu_possible_mask`, no `C3STOP` (`drivers/clocksource/timer-mediatek.c:50-57,
  270-303, 341`). That is the vendor's broadcast timer under its mainline
  compatible.
- **Arch timer.** It gets `CLOCK_EVT_FEAT_C3STOP` because the mainline node
  (`mt6785.dtsi:832-839`) has no `always-on`
  (`drivers/clocksource/arm_arch_timer.c:682-683, 1156`).
- **Tick core.** A non-per-CPU, non-`C3STOP`, one-shot device qualifies as
  the broadcast device (`kernel/time/tick-broadcast.c:88-100`).
  `CONFIG_GENERIC_CLOCKEVENTS_BROADCAST`, `CONFIG_TIMER_OF` and
  `CONFIG_MTK_TIMER` are set (`kernel/configs/pmos-mt6785.config:75, 6178,
  6187`).
- **Result.** Fragments A and B (`local-timer-stop`) need no timer work.
  Confirm on the unit with `/proc/timer_list` (broadcast device
  `mtk-clkevt`) before the first test. For SPM states and `deep`, the SPM
  PCM timer and wake sources (section 5) would take over the timed wake.

---

## What could not be determined

- ATF's MT6785 `CPU_SUSPEND`, `SYSTEM_SUSPEND` and MediaTek SiP handlers:
  why `standby` froze the unit, and which of the vendor's init steps ATF
  depends on (H1-H3).
- Whether mainline boots with the SPM firmware loaded (status 1) or already
  kicked (2), and which boot stage loads the `spmfw` and `sspm_*` images.
- Whether ATF reports the original or extended StateID format (readable in
  `/sys/kernel/debug/psci`; not recorded in BOARD.md).
- Whether the SSPM's MCDI side is alive under mainline, and whether the
  normal world can reach the SSPM mailbox and the CPC registers.
- The DRAM frequency argument of the SPM kick (`dram_steps_freq(0)` from the
  vendor DRAMC driver, not in the local blobs).
- Whether MCDI cluster-off gates the GIC, and how SYST behaves in the
  26 MHz-off states.
- The MT6785 CIRQ register layout against mainline's v1/v2 variants.
- Three vendor files (`cpuidle-mtk_acao.c`, 4.14 `psci.c`, `mtk_systimer.c`)
  and `Kconfig.platforms` were read remotely. Line numbers for them are
  approximate, and the 4.14 arm64 `cpuidle.c` glue
  (`arm_cpuidle_init`/`arm_cpuidle_suspend`) was not read; its role is
  inferred from the PSCI code.
