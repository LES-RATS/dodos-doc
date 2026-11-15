# Independent Verification of Model Review 7 (Mistral)

Verification of `/Users/btw/Documents/repos/Docs/reviews/2026-11-16-model-review-7-mistral.md` against primary specifications and upstream firmware/kernel sources, cross-checked against `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md`, `/Users/btw/Documents/repos/Docs/architecture/kernel.md`, and `/Users/btw/Documents/repos/dodos-kernel/abi/src/`.

## Summary

- **Total items audited:** 34 (12 items covering F1–F5 and the paste-ready rules, 16 standalone items from Mistral's 21-item "Checked and found right" list [the remaining 5 items, `#8`–`#12`, cross-reference F5.1–F5.3 and the ARM64 paste-ready rules and are scored there to avoid double-counting], and all 6 items Mistral listed under "What I did not have time to check"). All 21 items of the "Checked and found right" list were checked.
- **`confirmed`:** **24** (20 of Mistral's stated claims confirmed at primary sources + 4 items Mistral left unverified now verified at primary sources)
- **`wrong, with the right fact`:** **8** (`F1`, `F2`, `F5.2`/`#9`, `ARM64 (a)`/`#11`, `ARM64 (b)`/`#11`, `ARM64 (c)`/`#12`, `RISC-V scause`, and `Checked #6`)
- **`not verified`:** **2** (out-of-scope SMMUv3/IORT/x86-64 items and hardware-measurement open points)

---

## Verification Table

*(Permitted verdicts: `confirmed`, `wrong, with the right fact`, `not verified`.)*

| Item | Verdict | Source |
|---|---|---|
| **F1** — PSCI `CPU_OFF` on resident Trusted OS core: no pre-query exists (`:34-40`) | **wrong, with the right fact** — `MIGRATE_INFO_TYPE` (`0x84000006`) + `MIGRATE_INFO_UP_CPU` (`0x84000007`/`0xC4000007`) identify a uniprocessor Trusted OS's resident PE MPIDR beforehand (`CPU_OFF` returns `DENIED` on it). Only an MP Trusted OS (`2`), `NOT_SUPPORTED`, or platform `pwr_domain_off_early` (`DENIED` at call time) lacks a pre-query. | Arm PSCI DEN 0022E §§5.1.7, 5.1.8, 5.5, 5.9, Table 9; Linux `drivers/firmware/psci/psci.c:607-641`; TF-A `lib/psci/psci_main.c:328-350`, `lib/psci/psci_off.c:69-102` |
| **F2** — `FEAT_NMI`, `PSTATE.ALLINT`, and SDEI delayability (`:42-47`) | **wrong, with the right fact** — `FEAT_NMI` NMI vs `PSTATE.I`/`ALLINT` is right and NS `PSTATE.ALLINT` does not mask EL3 Group 0 interrupts, **but** interrupted NS software *can* block/delay SDEI event 0 via `SDEI_PE_MASK` (`0xC400002B`), causing `SDEI_EVENT_SIGNAL` to return `SDEI_EINVAL` and `handle_masked_trigger` to skip dispatch; DodOS relies on forbidding `SMC`, not hardware unmaskability. | Arm DDI 0487 `C5.2.1` (`ALLINT`), `D1.5.1`; Arm SDEI DEN 0054C §§5.1, 6.1.2; TF-A `docs/components/sdei.rst:187-189`, `services/std_svc/sdei/sdei_main.c:939-942`, `sdei_intr_mgmt.c:334-336,435-451`; `kernel.md:161` |
| **F3** — GIC routing is MMIO vs `ICC_*` system registers (`:49-55`) | **confirmed** (with `ICC_*` inventory: routing `ICC_SGI0R_EL1`, `ICC_SGI1R_EL1`, `ICC_ASGI1R_EL1` [all banned in `kernel.md:161`]; priority masking/enable `ICC_PMR_EL1` [NS view `0x80–0xFF` when `DS==0 && SCR_EL3.FIQ==1`], `ICC_BPR0/1_EL1`, `ICC_CTLR_EL1`, `ICC_IGRPEN1_EL1`; NS EL1/EL2 `ICC_IGRPEN0_EL1` is UNDEFINED when `DS==0 && SCR_EL3.FIQ==1`) | Arm GIC IHI 0069 §4.8.1 (`ICC_PMR_EL1`), `GICD_IROUTER<n>`, `GITS_*`, `ICC_*`; Linux `include/linux/irqchip/arm-gic-v3.h:35-43,364-382`; `kernel.md:161`; `kernel-interface.md:1200,1729` |
| **F4** — RISC-V `Zicfiss` and `ssp` CSR conflict (`:57-61`) | **confirmed** (`ssp` at `0x011`, URW, is per-thread state if U-mode `Zicfiss` is enabled via `senvcfg.SSE=1` / `menvcfg.SSE=1`; consistent in v1 only because `abi/src/riscv64.rs` enables only `V`) | RISC-V Unpriv ISA `unpriv-cfi.html` §33.1.2.2 (`ssp` `0x011`), Priv ISA `priv-cfi.html` §§15.1.2.1–2, `machine.html` §2.1.1.18 (`menvcfg.SSE`); `abi/src/riscv64.rs:5-11`; `kernel.md:172` |
| **F5.1** (also `#8`) — `Sdtrig` trigger CSRs M/Debug-mode only (`:65,122`) | **confirmed** (`tselect`, `tdata1–3`, `tinfo`, `tcontrol`, `mcontext` [`0x7A0–0x7A8`] are accessible only in M-mode and Debug mode; `scontext` [`0x5A8`]/`hcontext` [`0x6A8`] are context-ID CSRs only; Pass 13 right, Review 6 F3 wrong) | RISC-V Priv ISA `priv-csrs.html` (`0x7A0–0x7AF` M-mode, `0x7B0–0x7BF` D-mode); Debug Spec `Sdtrig.html` §5.2 (`Trigger Module Registers`) |
| **F5.2** (also `#9`) — MADT GICC `efficiency_class`, header, and ACPI rev/length (`:66,123`) | **wrong, with the right fact** — Pass 13 was right that the field exists (Review 6 F10 wrong), **but** Mistral cites the wrong Linux header (`include/acpi/actbl3.h` lacks GICC; it is `include/acpi/actbl2.h`) and the wrong revision/length caveat: `Processor Power Efficiency Class` was added in **ACPI 6.0** at offset 76 inside an **80-byte** GICC entry (not ACPI 6.3+ / Length ≥ 82). | UEFI ACPI 6.0 / 6.3 / 6.5 §5.2.12.14 (MADT GICC); Linux `include/acpi/actbl2.h:1438-1459`, `arch/arm64/include/asm/acpi.h:31-44` |
| **F5.3** (also `#10`) — `ObjectKind` numbers pinned by `abi` test (`:67,124`) | **confirmed** (`object_kinds_and_page_sizes_have_their_numbers` asserts `Vcpu=16` through `Role=20`) | `dodos-kernel/abi/src/tests.rs:115-143` |
| **Paste-ready ARM64 (a)** (also `#11` part) — `irq_claim` message words & PPIs (`:73-77,125`) | **wrong, with the right fact** — `GITS_TRANSLATER` + `(DeviceID, EventID)` for LPIs and `GICD_IROUTER<n>` (`IRM=0`) for SPIs are confirmed, **but** extended PPIs are **`1056–1119`** (64 interrupts), not `1056–1079`. | Arm GIC IHI 0069 §2.2, `GICR_TYPER.PPInum`, `GITS_TRANSLATER`; Linux `include/linux/irqchip/arm-gic-v3.h:42,97,136-146,380`, `drivers/irqchip/irq-gic-v3.c:1619-1623`; TF-A `drivers/arm/gic/v3/gicv3_main.c:454-465` |
| **Paste-ready ARM64 (b)** (also `#11` part) — ARM64 claimable INTID range (`:79-83,125`) | **wrong, with the right fact** — Extended SPIs in GICv3.1 are **`4096–5119`** (`4096 .. 4095 + 32*(GICD_TYPER.ESPI_range+1)` when `ESPI==1`), not `1024..` (`1024–1055`, `1120–4095`, `5120–8191` are reserved); standard SPI upper bound is `min(32*(GICD_TYPER.ITLinesNumber+1)-1, 1019)`; LPI upper bound is `min(2^(IDbits+1)-1, 8192 + 2^(num_LPIs+1) - 1)` when `GICD_TYPER.num_LPIs != 0` and `LPIS==1`. | Arm GIC IHI 0069 §2.2, `GICD_TYPER`; Linux `include/linux/irqchip/arm-gic-v3.h:47,83-91`, `drivers/irqchip/irq-gic-v3.c:1614-1618`, `irq-gic-v3-its.c:2196-2208`; TF-A `drivers/arm/gic/v3/gicv3_main.c:461` |
| **Paste-ready ARM64 (c)** (also `#12`) — `ESR_ELx` fault mapping table (`:85-97,126`) | **wrong, with the right fact** — Lists `EC 0x08` (`CP10_ID`, EL2 AArch32) as FP/SIMD disabled; omits `DFSC 0x2B` (L-1 translation fault under LPA2); omits `EC 0x30/0x31` (hardware breakpoints) from kind 9 and `FnV`/no-FAR rules; uses `EC 0x3A/0x3B` (`VECTOR32`/unallocated) instead of `0x32/0x33` for software step; sets `word 0 = ELR_ELx` for `BRK` `0x3C` instead of `ELR_ELx + 4`; classifies EL0-trappable `0x01`/`0x18`, user faults `0x0D` (`BTI`)/`0x0E` (`ILL`), `0x11` (`SVC32`), and unallocated `0x0F–0x10`/`0x14` as kernel bugs; omits `0x2C` (`FP_EXC64`), `0x1C` (`FPAC`), `0x27` (`MOPS`), `0x2D` (`GCS`). | Arm DDI 0487 `ESR_EL1`/`ESR_EL2`, `C5.2.5` (`ELR_EL1`), `D2.7` (`BRK`), `D2.11` (Software Step), `FAR_EL1`; Linux `arch/arm64/include/asm/esr.h:14-72,108-145`; `kernel-interface.md:388,406` |
| **Paste-ready RISC-V `scause`** — `scause` fault mapping & `Sdtrig` note (`:99-109`) | **wrong, with the right fact** — Writes **`mepc`** instead of **`sepc`** on S-mode traps; writes access faults as **`1/4/5`** instead of **`1/5/7`**; sets `word 0 = mepc` on `scause=3` `EBREAK` instead of `sepc + instr_len`; maps `scause=9` (`ECALL` from S-mode) to user `bad call` instead of kernel bug; gives wrong reason for kind 9 (M-mode can arm `action=0` triggers delegated via `medeleg[3]=1`, raising `scause=3`); omits `scause=18` (`Software check`, `stval=2/3`). | RISC-V Priv ISA `supervisor.html` §§11.1.1.7–9, Table 2 (`scause`); `machine.html` §2.1.1.8; Debug Spec `Sdtrig.html` §5.1.4; `kernel-interface.md:388` |
| **Paste-ready RISC-V AIA** — IMSIC words/range (`1..2047`) & shared APLIC MMIO (`:111`) | **confirmed** (MSI write to target hart's S-level IMSIC `seteipnum_le` + identity `1..2047` max; identity `0` never valid; one shared MMIO region per APLIC domain) | RISC-V AIA `IMSIC.html` §§2.1, 2.1.2, 2.1.5; `AdvPLIC.html` §3.1.5; `kernel-interface.md:698,1200` |
| **Checked #1** — SDEI client EL, EL1-under-EL2 rejection, `SDEI_EVENT_SIGNAL` event 0 (`:115`) | **confirmed** (as stated in #1; `PSTATE.ALLINT` and `SDEI_PE_MASK` resolved in `F2` & `NV1`) | Arm SDEI DEN 0054C; TF-A `docs/components/sdei.rst:193-200`, `services/std_svc/sdei/sdei_main.c:925-955` |
| **Checked #2** — `FEAT_NMI` (`ID_AA64PFR1_EL1.NMI`, `PSTATE.I` vs `PSTATE.ALLINT`) (`:116`) | **confirmed** (verified directly in Arm DDI 0487, replacing Mistral's non-primary QEMU lore citation) | Arm DDI 0487 `C5.2.1` (`ALLINT`), `D1.5.1` (`FEAT_NMI`) |
| **Checked #3** — PSCI `CPU_OFF` calling PE only / `AFFINITY_INFO` / no remote-stop PSCI call (`:117`) | **confirmed** (pre-query gap handled in `F1`) | Arm PSCI DEN 0022E §§5.1.3, 5.1.5, 5.5, 5.7 |
| **Checked #4** — RISC-V higher-privilege interrupts always globally enabled regardless of `yIE` (`:118`) | **confirmed** | RISC-V Priv ISA `machine.html` §2.1.1.6.1 |
| **Checked #5** — SBI HSM `sbi_hart_stop`, `STOPPED`, `sbi_probe_extension` (`:119`) | **confirmed** | RISC-V SBI v3.0 `ext-hsm.html`, `ext-base.html` |
| **Checked #6** — Class-2 "forced" honesty on RISC-V ("RISC-V traps are precise") (`:120`) | **wrong, with the right fact** — Claiming unqualified **"RISC-V traps are precise"** is overclaimed: the RISC-V Unprivileged ISA explicitly defines trap precision as **EEI-defined** (recommended, not required; fatal traps can be observed to be imprecise). | RISC-V Unpriv ISA `unpriv/intro.html` §1.6 (Table 1 & note 2) |
| **Checked #7** — Class-1 ARM64 "signalled" honesty & Trusted OS own-code `parked` (`:121`) | **confirmed** (pre-query knowability defect tracked in `F1`) | Arm PSCI DEN 0022E §§5.5, 5.7; `kernel-interface.md:1086,1088` |
| **Checked #13** — RISC-V execute-only (`R=0,W=0,X=1`) & reserved `R=0,W=1,X=0` (`:127`) | **confirmed** | RISC-V Priv ISA `supervisor.html` Table 6 (`Encoding of PTE R/W/X fields`) |
| **Checked #14** — One page size per level, no `Svnapot`/contiguous hint, 64 KB refused (`:128`) | **confirmed** (minor symbol note: Linux uses `PTE_CONT` at `pgtable-hwdef.h:174`, not `PMD_SECT_CONTIG`) | Arm DDI 0487 `TCR_EL1.TG0/TG1`; Linux `arch/arm64/include/asm/pgtable-hwdef.h:174`; RISC-V Priv ISA `supervisor.html` (`Svnapot`); `abi/src/lib.rs:459-478`; `abi/tests/review6.rs` |
| **Checked #15** — Tag widths (PCID 12b, ARM64 ASID 8/16b, RISC-V `ASIDMAX=16`/`9`) (`:129`) | **confirmed** | Arm DDI 0487 `TCR_EL1.AS`/`FEAT_ASID16`; RISC-V Priv ISA `supervisor.html` §11.1.1.11 (`satp`); `kernel-interface.md:891` |
| **Checked #16** — Little-endian requirement on ARM64 (`SCTLR_EL1.EE`) (`:130`) | **confirmed** (`SCTLR_EL1.EE` selects data-access endianness; AArch64 instruction fetch is always LE) | Arm DDI 0487 `SCTLR_EL1.EE`; `kernel-interface.md:1707` |
| **Checked #17** — Entropy (`RNDR`/`RNDRRS` & `Zkr` `seed` gated by `mseccfg.SSEED`) (`:131`) | **confirmed** | Arm DDI 0487 `D24.2.84` (`ID_AA64ISAR0_EL1.RNDR`); RISC-V Unpriv ISA `scalar-crypto.html` §31.1.2.9, Priv ISA `machine.html` §2.1.1.19 (`mseccfg`); OpenSBI `include/sbi/riscv_encoding.h:274,748-749`, `lib/sbi/sbi_hart.c:175` |
| **Checked #18** — AIA IMSIC & APLIC (`:132`) | **confirmed** | RISC-V AIA `IMSIC.html` §§2.1, 2.1.2, `AdvPLIC.html` §3.1.5 |
| **Checked #19** — `ICC_SGI1R_EL1` writable at EL1 when `ICC_SRE_EL1.SRE=1` (`:133`) | **confirmed** | Arm GIC IHI 0069 (`ICC_SGI1R_EL1`, `ICC_SRE_EL1`); `kernel.md:161` |
| **Checked #20** — `REGS_WORDS = 26` scoped to `x86_64` (`:134`) | **confirmed** (`x86_64.rs:61` sets `REGS_WORDS = 26`; `aarch64.rs` and `riscv64.rs` define `FEATURES` only) | `dodos-kernel/abi/src/x86_64.rs:61`, `aarch64.rs:1-14`, `riscv64.rs:1-12`; `kernel-interface.md:1450` |
| **Checked #21** — One-node rule knowability ("with the single exception of F1") (`:135`) | **confirmed** (qualified exactly on `F1`) | Arm SDEI DEN 0054C; RISC-V SBI v3.0 `ext-base.html`; `kernel-interface.md:1088` |
| **NV1** — `PSTATE.ALLINT` vs SDEI event 0 (Mistral not verified, `:139`) | **confirmed** (newly verified: NS `PSTATE.ALLINT` masks only interrupts targeted at `ELx`, not EL3 Group 0 interrupts; **however**, `SDEI_PE_MASK` blocks event 0 as noted in `F2`) | Arm DDI 0487 `C5.2.1`; Arm GIC IHI 0069 §4.8.1; Arm SDEI DEN 0054C §6.1.2; TF-A `docs/components/sdei.rst:187-189`, `sdei_main.c:940` |
| **NV2** — RISC-V big/bi-endianness rule (Mistral not verified, `:140`) | **confirmed** (newly verified: data memory endianness is configurable via `mstatus.{MBE,SBE,UBE}` on bi-endian harts; instruction parcels are always 16-bit LE) | RISC-V Unpriv ISA `unpriv/intro.html` §1.5; Priv ISA `machine.html` §2.1.1.6.5 |
| **NV3** — RISC-V precise-trap rule & `Smrnmi` interaction (Mistral not verified, `:141`) | **confirmed** (newly verified: trap precision is EEI-defined [`#6`]; `Smrnmi` `rnmi` signals preempt all interrupts/exceptions regardless of `mstatus.MIE` and cannot be disabled by software) | RISC-V Unpriv ISA `unpriv/intro.html` §1.6; Priv ISA `rnmi.html` §§7.1.1–7.1.2 |
| **NV4** — Minimum ACPI revision for GICC `efficiency_class` & IMSIC identity `0` (Mistral not verified, `:142`) | **confirmed** (newly verified: minimum ACPI revision is **6.0** §5.2.12.14 [offset 76, Length 80]; IMSIC identity `0` is **never valid**) | UEFI ACPI 6.0 §5.2.12.14; Linux `arch/arm64/include/asm/acpi.h:31-37`; RISC-V AIA `IMSIC.html` §2.1 |
| **NV5** — SMMUv3 (IHI 0070), ACPI IORT details, and x86-64-only claims (`:143`) | **not verified** (out of ARM64/RISC-V review scope; not audited) | — |
| **NV6** — Remaining open points at `kernel-interface.md:1879-1894` (`:144`) | **not verified** (out of scope / pending reference hardware measurements) | — |

---

## Wrong Items in Detail

### 1. F1 — PSCI pre-query for a resident Trusted OS (`2026-11-16-model-review-7-mistral.md:34-40`)
- **Mistral's claim (`:37`):** `CPU_OFF` powers down the calling PE only and may return `DENIED` at call time — *"there is no pre-query that tells the kernel a stop will be refused."*
- **Primary-source fact:** PSCI DEN 0022E provides optional **`MIGRATE_INFO_TYPE` (`0x84000006`)** (§§5.1.7, 5.9, Table 9) and **`MIGRATE_INFO_UP_CPU` (`0x84000007` / `0xC4000007`)** (§5.1.8). In TF-A (`lib/psci/psci_main.c:328-350`) and Linux (`drivers/firmware/psci/psci.c:607-641`), `MIGRATE_INFO_TYPE` reports:
  - `0` (`TOS_UP_MIGRATE`) or `1` (`TOS_UP_NO_MIGRATE`): uniprocessor Trusted OS, where `MIGRATE_INFO_UP_CPU` returns the MPIDR of the **resident PE** beforehand (on which `CPU_OFF` returns `DENIED`, per DEN 0022E Table 9).
  - `2` (`TOS_MP`) or `NOT_SUPPORTED` (`-1`): either a multiprocessor Trusted OS or `MIGRATE_INFO_TYPE` unimplemented. Moreover, a platform's `pwr_domain_off_early` (`tf-a/lib/psci/psci_off.c:69-74`) or `svc_off` (`psci_off.c:97-102`) can return `PSCI_E_DENIED` dynamically.
- **Impact:** Mistral's conclusion that start-up should treat the core carefully remains sound for MP Trusted OSes and platform refusals, **but** saying "there is no pre-query" overlooks `MIGRATE_INFO_TYPE`/`MIGRATE_INFO_UP_CPU`, which start-up *can* call first to classify a UP Trusted OS resident core as class 0 immediately.

### 2. F2 — `FEAT_NMI`, `PSTATE.ALLINT`, and SDEI delayability (`2026-11-16-model-review-7-mistral.md:42-47, 115, 139`)
- **Mistral's claim (`:45`, `:139`):** Notes `FEAT_NMI` NMI is masked only by `PSTATE.ALLINT` (citing a QEMU patch series rather than Arm DDI 0487), and leaves `"Whether ALLINT also masks SDEI event 0 itself: not verified"` while assuming SDEI event 0 is unconditionally unmaskable by interrupted software (`:39`, `:55`).
- **Primary-source fact (two points):**
  1. **Resolved `ALLINT` question:** Per Arm DDI 0487 `C5.2.1` (`ALLINT`), `PSTATE.ALLINT` masks interrupts **targeted at `ELx`** when executing at `ELx`. Because TF-A SDEI events are physical **EL3 Group 0 interrupts** (`tf-a/docs/components/sdei.rst:187-189`), Non-secure EL1/EL2 `PSTATE.ALLINT` does **not** mask delivery of SDEI event 0 to EL3. (Likewise, NS `ICC_PMR_EL1` is shifted to `0x80–0xFF` when `DS==0 && SCR_EL3.FIQ==1` per IHI 0069 §4.8.1 and cannot mask EL3 Group 0 interrupts, and NS EL1/EL2 `ICC_IGRPEN0_EL1` is `UNDEFINED`.)
  2. **Overlooked delayability mechanism (`SDEI_PE_MASK`):** Under Arm SDEI DEN 0054C (§§5.1, 6.1.2) and TF-A, interrupted Non-secure software *can* block SDEI delivery (including event 0) by calling **`SDEI_PE_MASK` (`0xC400002B`)**. In TF-A:
     - `sdei_signal` (`services/std_svc/sdei/sdei_main.c:940-942`) checks `sdei_is_target_pe_masked(target_pe)` and refuses with `SDEI_EINVAL`;
     - `sdei_intr_handler` (`services/std_svc/sdei/sdei_intr_mgmt.c:435-451, 334-336`) checks `state->pe_masked` and calls `handle_masked_trigger`, which for `SDEI_EVENT_0` immediately returns without dispatching to the NS client.
  - Thus ARM64 class-1 honesty depends on the static scan/gate banning `SMC` (`kernel.md:161`) and never unmasking/calling `SDEI_PE_MASK`, not solely on EL3 hardware unmaskability.

### 3. F5.2 (and Confirmed `#9`) — MADT GICC `efficiency_class` header & ACPI revision/length caveat (`2026-11-16-model-review-7-mistral.md:66, 123`)
- **Mistral's claim:** Cites Linux `include/acpi/actbl3.h` for `struct acpi_madt_generic_interrupt`, and states *"the field exists only when GICC Length ≥ 82 (ACPI 6.3+); older tables (76/80 bytes) lack it and the byte reads 0."*
- **Primary-source fact:** Both the header citation and the revision/length cutoff are wrong:
  1. `struct acpi_madt_generic_interrupt` is in Linux **`include/acpi/actbl2.h:1438-1459`** (`u8 efficiency_class` at line 1453); `actbl3.h` has no MADT GICC struct.
  2. `Processor Power Efficiency Class` (1 byte at offset **76**, followed by 3 reserved bytes) was added in **ACPI 6.0** (§5.2.12.14), expanding the MADT GICC structure from 76 bytes (ACPI 5.0/5.1) to **80 bytes** (`arch/arm64/include/asm/acpi.h:31-37`: `"added in ACPI 6.0"`, `ACPI_MADT_GICC_MIN_LENGTH = offsetof(struct acpi_madt_generic_interrupt, efficiency_class)` = 76). ACPI 6.3 merely assigned 2 of the already-present trailing reserved bytes to `spe_interrupt` (still **80 bytes**); Length **82** (`trbe_interrupt`) was added in **ACPI 6.5** (`actbl2.h:1454-1456`). Thus an **80-byte** (ACPI 6.0–6.4) GICC entry *does* carry `efficiency_class`; only a **76-byte** (ACPI 5.x) entry lacks it.

### 4. Paste-ready ARM64 (a) (and Confirmed `#11` part) — Extended PPI range (`2026-11-16-model-review-7-mistral.md:77, 125`)
- **Mistral's claim:** *"SGIs (INTIDs 0-15), PPIs (16-31) and extended PPIs (1056-1079) are per-PE and never claimable."* (Repeated in `#11`: *"extended PPI 1056-1079"*.)
- **Primary-source fact:** In GICv3.1 (Arm IHI 0069 §2.2 / `GICR_TYPER.PPInum`), extended PPIs span **64** INTIDs: **`1056–1119`** (either none when `PPInum==0`, `1056–1087` when `PPInum==1`, or `1056–1119` when `PPInum==2`), NOT `1056–1079`. Verified in Linux `include/linux/irqchip/arm-gic-v3.h:136-146` (`EPPI_BASE_INTID = 1056`, `GICR_TYPER_NR_PPIS`), `drivers/irqchip/irq-gic-v3.c:1620-1622` (accepts offsets `0..63`), and TF-A `drivers/arm/gic/v3/gicv3_main.c:455` (`/* SGIs: 0-15, PPIs: 16-31, EPPIs: 1056-1119 */`).

### 5. Paste-ready ARM64 (b) (and Confirmed `#11` part) — Claimable SPI/ESPI/LPI ranges (`2026-11-16-model-review-7-mistral.md:81-82, 125`)
- **Mistral's claim:**
  - *"Lines: SPIs, INTIDs 32..1019, plus extended SPIs from 1024 up to the implemented INTID space when the distributor reports them"*
  - *"Messages: LPIs, INTIDs 8192..2^(GICD_TYPER.IDBits+1)−1"*
- **Primary-source facts:**
  1. **Wrong extended SPI base:** Extended SPIs begin at **`4096`** and span **`4096–5119`**, bounded by `4096 .. 4095 + 32 * (GICD_TYPER.ESPI_range + 1)` when `GICD_TYPER.ESPI == 1` (Arm IHI 0069 §2.2 / `GICD_TYPER`; Linux `arm-gic-v3.h:47,85,90-91` `ESPI_BASE_INTID = 4096`, `irq-gic-v3.c:1615-1617`; TF-A `gicv3_main.c:461` `/* SPIs: 32-1019, ESPIs: 4096-5119 */`). INTIDs `1024–1055`, `1120–4095`, and `5120–8191` are **reserved**, NOT extended SPIs.
  2. **Standard SPI upper bound:** Not every machine implements up to `1019`; the implemented maximum is `min(32 * (GICD_TYPER.ITLinesNumber + 1) - 1, 1019)` (Linux `arm-gic-v3.h:89`).
  3. **LPI upper bound & field name:** Requires `GICD_TYPER.LPIS == 1`, the architectural field name is `IDbits` (`[23:19]`), and **`GICD_TYPER.num_LPIs` (`[15:11]`)** restricts LPIs to `8192 .. 8192 + 2^(num_LPIs + 1) - 1` whenever `num_LPIs != 0` (Arm IHI 0069 `GICD_TYPER`; Linux `arm-gic-v3.h:83,87-88`, `drivers/irqchip/irq-gic-v3-its.c:2198-2208`).

### 6. Paste-ready ARM64 (c) (and Confirmed `#12`) — `ESR_ELx` fault table (`2026-11-16-model-review-7-mistral.md:85-97, 126`)
Checked directly against Arm DDI 0487 and Linux `arch/arm64/include/asm/esr.h:14-162`:
1. **Row `:89` (`0x08`):** Lists `0x08 (FP/SIMD disabled)`. **`0x08` is `ESR_ELx_EC_CP10_ID`** (`esr.h:22`, trapped AArch32 CP10 ID register read, **EL2 only**). AArch64 FP/SIMD disabled is **`0x07`** (`ESR_ELx_EC_FP_ASIMD`) alone.
2. **Row `:91` (`DFSC`):** Lists only `DFSC 0x04-0x07 (translation fault L0-L3)`. Omits **`DFSC 0x2B`** (translation fault at **level -1** when `FEAT_LPA2` / 52-bit OA/VA on 4 KB/16 KB granule is enabled; `esr.h:143-145` `ESR_ELx_FSC_FAULT_L(-1) == 0x2C + (-1) == 0x2B`). (Similarly, `0x29` is address-size fault at level -1, `esr.h:135`.) Also note `word 3` of fault kind 1 requires `ACCESS_PRESENT` clear (`0`) and `bits 32..63 = ESR_ELx` (`kernel-interface.md:391`).
3. **Row `:94` (hardware breakpoints):** Maps only `EC 0x34/0x35 (watchpoint)` to kind 9 (`hardware breakpoint`), omitting hardware **instruction breakpoints `EC 0x30/0x31`** (`BREAKPT_LOW`/`BREAKPT_CUR`, `esr.h:59-60`), even though `kernel-interface.md:406` defines kind 9 for both breakpoints and watchpoints. Additionally: for `0x30/0x31`, `FAR_ELx` is `UNKNOWN` (hardware writes `FAR_ELx` only for `0x20/0x21/0x22/0x24/0x25/0x34/0x35`), and for `0x34/0x35` `FAR_ELx` is valid only if `ESR_ELx.FnV == 0` (`esr.h:109`).
4. **Row `:95` (`0x3A/0x3B` and `BRK` `word 0`):**
   - Lists `0x3A/0x3B (software step)`. **`0x3A` is `VECTOR32`** (EL2-only AArch32 vector catch, `esr.h:68`) and **`0x3B` is UNALLOCATED** (`esr.h:69`). Software step is **`EC 0x32/0x33`** (`SOFTSTP_LOW`/`SOFTSTP_CUR`, `esr.h:61-62`).
   - Sets `word 0 = ELR_ELx` for `0x38/0x3C (BRK)`. Per Arm DDI 0487 `D2.7` / `C5.2.5`, on `BRK #imm` (`EC 0x3C`) hardware writes the **address of the `BRK` instruction itself** into `ELR_ELx`, whereas `kernel-interface.md:388` requires `word 0` for a trap (`breakpoint, single step`) to be the **next** instruction (`ELR_ELx + 4`). (`SOFTSTP` `0x32/0x33` already puts the next instruction in `ELR_ELx`; `0x38` is AArch32 `BKPT32`.)
5. **Row `:97` ("kernel bug" catch-all & omissions):**
   - Wrongly treats **`EC 0x01` (`WFx`)** and **`EC 0x18` (`SYS64`)** from EL0 as always a kernel bug: user threads executing trapped `WFI`/`WFE` or trapped system-register instructions (e.g., disabled feature/ID/timer access from EL0) raise `0x01`/`0x18` from `EL0` and are user faults (kind 4/2), whereas current-EL `*_CUR` faults indicate a kernel bug.
   - The swept range **`0x0C-0x11`** wrongly includes **`0x0D` (`BTI` — Branch Target Identification fault, kind 4 protection)**, **`0x0E` (`ILL` — Illegal Execution state, fault)**, **unallocated `0x0F-0x10`**, and **`0x11` (`SVC32`)**; **`0x14` is also unallocated** (`esr.h:26-34`).
   - Omits **`EC 0x2C`** (`FP_EXC64`, trapped IEEE FP exception -> kind 3 arithmetic if enabled), **`EC 0x1C`** (`FPAC`, Pointer Authentication fault -> kind 4 protection), **`EC 0x27`** (`MOPS`, Memory Copy/Set exception -> kind 4), and **`EC 0x2D`** (`GCS`, Guarded Control Stack exception -> kind 4).

### 7. Paste-ready RISC-V `scause` fault table (`2026-11-16-model-review-7-mistral.md:99-109`)
Checked directly against RISC-V Privileged ISA `supervisor.html` §§11.1.1.7–9 & Table 2, `machine.html` §2.1.1.8, and `Sdtrig.html` §5.1.4:
1. **`mepc` instead of `sepc` (`:99, :103, :107`):** Traps taken to S-mode write **`sepc`**, NOT `mepc`.
2. **Access fault codes `1/4/5` (`:104`):** Table 2 defines **`1`** (Instruction access fault), **`5`** (Load access fault), and **`7`** (Store/AMO access fault). Code **`4`** is **Load address misaligned** (which Mistral also lists on line 105!).
3. **`scause = 3` (`EBREAK`) `word 0` (`:107`):** Hardware saves the address of the `EBREAK` / `C.EBREAK` instruction in `sepc`, whereas `kernel-interface.md:388` requires `word 0` of a breakpoint trap to be the **next** instruction (`sepc + 4` for 32-bit `EBREAK`, `sepc + 2` for compressed `C.EBREAK`).
4. **`scause = 8/9` (`ECALL` from U/S) (`:108`):** Only `scause = 8` (`ECALL` from U-mode) is a user thread `bad call` (kind 6). `scause = 9` (`ECALL` from S-mode) is a trap from supervisor mode itself (a kernel bug, never a user fault).
5. **`Sdtrig` / kind 9 explanation (`:109`):** Saying *"Sdtrig triggers are machine-mode only ... so kind 9 is never raised on RISC-V"* is factually flawed: under `Sdtrig.html` §5.1.4, M-mode *can* program a trigger with `action=0` for S/U-mode and delegate breakpoints (`medeleg[3] = 1`), delivering `scause = 3` to S-mode. The actual constraint is that S-mode cannot write trigger CSRs for per-thread `thread_write_regs` (and cannot distinguish an M-mode-armed trigger `scause=3` from `EBREAK` without firmware cooperation).
6. **Omitted causes:** **`scause = 18` (`Software check`)** encodes `stval = 2` (Zicfilp landing-pad fault) and `stval = 3` (Zicfiss shadow-stack fault) -> kind 4 protection (`supervisor.html` §11.1.1.9); **`scause = 19` (`Hardware error`)** is a fatal/node error, not a user fault.

### 8. Checked `#6` — "RISC-V traps are precise" (`2026-11-16-model-review-7-mistral.md:120`)
- **Mistral's claim (`:120`):** Asserts unqualified **"RISC-V traps are precise, so at most the in-flight instruction completes"**, leaving only the section line "NOT VERIFIED".
- **Primary-source fact:** RISC-V Unprivileged ISA `unpriv/intro.html` §1.6 (Table 1, footnote 2, and text below Table 1) states: *"The EEI defines for each trap whether it is handled precisely, though the recommendation is to maintain preciseness where possible... Fatal traps can be observed to be imprecise by software running inside the execution environment, if known-errorful instructions do not cause immediate termination."* Unqualified architectural trap precision is therefore **not guaranteed by the RISC-V ISA alone**; it depends on the platform hardware/SBI EEI.

---

## Corrected Paste-Ready Rules and Tables

*(Replacements for `2026-11-16-model-review-7-mistral.md:73-110`, verified against Arm GIC IHI 0069, Arm DDI 0487, Linux `esr.h` / `arm-gic-v3.h` / `irq-gic-v3*.c`, TF-A `gicv3_main.c`, and the RISC-V Privileged / Debug specs.)*

### (a) ARM64 `irq_claim` message words ([kernel-interface.md:698](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L698), entry `Interrupts` `:1724`)

- **LPI (message interrupt):** `result = (address, data) = (physical address of owning ITS's GITS_TRANSLATER register [offset 0x10040 in ITS register frame / 0x0040 in translation frame], EventID)`. Writing `EventID` to `GITS_TRANSLATER` causes the ITS to translate `(DeviceID, EventID) -> (INTID, target PE)` via its device and collection tables and forward the LPI to the target redistributor (Arm IHI 0069; Linux `arm-gic-v3.h:380`).
- **SPI / extended SPI (line):** `result = (0, 0)`. The GIC distributor role holder programs `GICD_IROUTER<n>` (or `GICD_IROUTER<n>E` for ESPIs) with `IRM = 0` to route the line to the claiming PE's MPIDR affinity (Arm IHI 0069; Linux `arm-gic-v3.h:42-43,97`).
- **Unclaimable per-PE interrupts:** SGIs (`0–15`), PPIs (`16–31`), and extended PPIs (`1056–1119`) are per-PE and never claimable.

### (b) ARM64 claimable INTID ranges (entry `Interrupts`)

- **Lines (SPIs):**
  - Standard SPIs: `32 .. min(32 * (GICD_TYPER.ITLinesNumber + 1) - 1, 1019)`.
  - Extended SPIs (when `GICD_TYPER.ESPI == 1`): `4096 .. min(4095 + 32 * (GICD_TYPER.ESPI_range + 1), 5119)` (Arm IHI 0069 `GICD_TYPER`; Linux `arm-gic-v3.h:47,85,89-91`; TF-A `gicv3_main.c:461`).
  - Ranges `1024–1055`, `1120–4095`, and `5120–8191` are reserved (never claimable).
- **Messages (LPIs, when `GICD_TYPER.LPIS == 1`):**
  - `8192 .. LPI_last`, where `LPI_last = (1 << (GICD_TYPER.IDbits + 1)) - 1` (`IDbits` in `[23:19]`, ≥ 13 so ≥ 14 bits when LPIs are supported, up to 24 bits), further bounded to `8192 + (1 << (GICD_TYPER.num_LPIs + 1)) - 1` when `GICD_TYPER.num_LPIs != 0` (`[15:11]`) (Arm IHI 0069 `GICD_TYPER`; Linux `arm-gic-v3.h:83,87-88`, `irq-gic-v3-its.c:2198-2208`).

### (c) ARM64 `ESR_ELx` fault-kind mapping (`EC = ESR_ELx[31:26]`, `DFSC/IFSC = ISS[5:0]`, `WnR = ISS[6]`, `FnV = ISS[10]`)

| ESR_ELx (`EC` & privilege) | `IFSC`/`DFSC` / condition | Fault kind | Words |
|---|---|---|---|
| `EC 0x00` (`UNKNOWN`), `0x07` (`FP_ASIMD`), `0x19` (`SVE`), `0x1D` (`SME`), or EL0 `0x01` (`WFx`) / EL0 `0x18` (`SYS64`) when unallowed instruction/trap | — | `2` undefined instruction | `word 2 = EC`; `word 4 = 1 + feature bit` for `0x07`/`0x19`/`0x1D` (or disabled feature via `0x18`), else `0` |
| `EC 0x2C` (`FP_EXC64`) | trapped IEEE FP exception (if enabled) | `3` arithmetic | `word 2 = 0x2C`; `word 3 = ISS` |
| `EC 0x15` (`SVC64`) | outside kernel syscall code page | `6` bad call | `word 2 = 0x15` |
| `EC 0x20` (`IABT_LOW`) / `0x24` (`DABT_LOW`) (or `*_CUR` from user if applicable; kernel `*_CUR` faults are kernel bugs) | `IFSC`/`DFSC 0x04–0x07` (translation L0–L3) or `0x2B` (translation L-1, `FEAT_LPA2`) | `1` page fault | `word 0 = ELR_ELx`; `word 2 = EC`; `word 3`: `EXEC` for `0x20`/`0x21`, `WnR ? WRITE : READ` for `0x24`/`0x25`, `PRESENT = 0`, `bits 32..63 = ESR_ELx`; `word 4 = FAR_ELx` |
| same (`0x20`/`0x24`) | `0x08–0x0B` (access flag), `0x0C–0x0F` (permission), `0x21` (alignment), `0x00–0x03`/`0x29` (address size), SEA, etc. | `4` protection | `word 0 = ELR_ELx`; `word 2 = EC`; `word 3 = ESR_ELx` (for non-translation fault, `PRESENT` not used unless classified as page fault); `word 4 = (FnV == 0) ? FAR_ELx : 0` |
| `EC 0x22` (`PC_ALIGN`), `0x26` (`SP_ALIGN`) | — | `4` protection | `word 0 = ELR_ELx`; `word 2 = EC`; `word 4 = FAR_ELx` for `0x22`, `0` for `0x26` |
| `EC 0x0D` (`BTI`), `0x0E` (`ILL`), `0x1C` (`FPAC`), `0x27` (`MOPS`), `0x2D` (`GCS`) from EL0 | — | `4` protection | `word 0 = ELR_ELx`; `word 2 = EC`; `word 3 = ISS` |
| `EC 0x30` (`BREAKPT_LOW`) / `0x34` (`WATCHPT_LOW`) | armed via thread's `DBGBCR`/`DBGWCR` (`thread_write_regs`) | `9` hardware breakpoint | `word 0 = ELR_ELx`; `word 2 = EC`; `word 3 = bitmask of thread's matching debug registers`; `word 4 = (EC == 0x34 && FnV == 0) ? FAR_ELx : 0` |
| `EC 0x32` (`SOFTSTP_LOW`), `0x3C` (`BRK64`) | — | `5` debug | `word 2 = EC`; `word 0 = ELR_ELx` for `0x32` (`SOFTSTP`, already points to next instr), **`ELR_ELx + 4`** for `0x3C` (`BRK64`, per `kernel-interface.md:388`) |
| Current-EL (`*_CUR`) unexpected traps (`0x21`/`0x25`/`0x31`/`0x33`/`0x35`), `0x01`/`0x18` from kernel outside gate, `0x2F` (`SERROR`), unallocated/AArch32-only ECs (`0x03–0x06`, `0x08`, `0x0C`, `0x11`, `0x16/0x17`, `0x38`, `0x3A`) | — | not a thread fault (kernel bug, AArch32 disallowed, or hardware error `0x2F`) | — |

### (d) RISC-V `scause` fault-kind mapping (traps to S-mode write `scause`, `stval`, **`sepc`**)

| `scause` (Interrupt bit = 0) | Fault kind | Words |
|---|---|---|
| `12`, `13`, `15` (instruction / load / store-AMO page fault) | `1` page fault | `word 0 = sepc`; `word 2 = scause`; `word 3`: `EXEC`/`READ`/`WRITE`, `PRESENT = 0`; `word 4 = stval` |
| `1`, `5`, `7` (instruction / load / store-AMO access fault, e.g. PMP/PMA) | `4` protection | `word 0 = sepc`; `word 2 = scause`; `word 4 = stval` |
| `0`, `4`, `6` (instruction / load / store-AMO address misaligned) | `4` protection | `word 0 = sepc`; `word 2 = scause`; `word 4 = stval` |
| `18` (software check: `Zicfilp` `stval=2`, `Zicfiss` `stval=3`) | `4` protection | `word 0 = sepc`; `word 2 = 18`; `word 3 = stval` |
| `2` (illegal instruction) | `2` undefined instruction | `word 0 = sepc`; `word 2 = 2`; `word 4 = 1 + feature bit` if disabled extension (e.g. `V`), else `0` |
| `3` (`EBREAK` / `C.EBREAK`) | `5` debug | `word 2 = 3`; `word 0 = next PC` (`sepc + 4` for 32-bit `EBREAK`, `sepc + 2` for `C.EBREAK`, per `kernel-interface.md:388`) |
| `8` (`ECALL` from U-mode) | `6` bad call | `word 0` per `kernel-interface.md:388`; `ECALL` outside the kernel-supplied code page (`scause = 9`, `ECALL` from S-mode, is a kernel bug, not a user fault) |
| `19` (hardware error) | not a thread fault (fatal / node hardware error) | — |
| Hardware breakpoints (`Sdtrig`) | none user-configurable via S-mode | Trigger CSRs (`0x7A0–0x7A8`) are M-mode/Debug-mode only, so `thread_write_regs` cannot configure per-thread triggers in S-mode without M-mode mediation (note: if M-mode arms an `action=0` trigger with `medeleg[3]=1`, it still raises `scause = 3`) |
