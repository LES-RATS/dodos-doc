# Model review 7 (Mistral) — ARM64 and RISC-V hardware and firmware facts

Review of the corrected contract after the sixth review. My angle only: every sentence of the diff
`5d93e8f..3bc7597 -- architecture` that states what a processor, an interrupt controller, an IOMMU or
a firmware does, checked against the primary source. No model run.

## What I read and ran

- `git -C /Users/btw/Documents/repos/Docs diff 5d93e8f..3bc7597 -- architecture` in full (488 lines; scratch copy at `/tmp/review7-mistral/diff.txt`).
- [/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md](kernel-interface.md) in full (1894 lines): values of the machine :79-98, faults and register calls :359-435, cores :616-683, interrupts :683-745, gate G-rules :868-907, the fence :1086-1088, roles :1196-1200, entropy :1419, values to add to abi :1436-1457, start-up page :1707-1729, open points :1872-1894.
- [/Users/btw/Documents/repos/Docs/architecture/kernel.md](kernel.md) in full (212 lines): x86-64 list :147, ARM64 list :161, RISC-V list :170-172.
- abi at commit `2afc901` of `/Users/btw/Documents/repos/dodos-kernel` (branch `model`), extracted to `/tmp/review7-mistral/`: `x86_64.rs` (REGS_WORDS = 26, IRQ_VECTOR_FIRST = 48 / LAST = 239), `aarch64.rs` (FEATURES only: SVE/SME/SME2_ZT0), `riscv64.rs` (FEATURES only: V), `machine.rs` (FENCE_CLASS_*), `features.rs`, `lib.rs` (`Geometry::valid` :459-477: `entries == 1 << (page_shift[0] - 3)` and `entries <= TABLE_ENTRIES_MAX = 4096`), `tests.rs` (`object_kinds_and_page_sizes_have_their_numbers` :115 pins ObjectKind numbers Vcpu=16 … Role=20), `abi/tests/review6.rs` (64 KB / E==P/8 tests).
- [/Users/btw/Documents/repos/Docs/reviews/2026-11-16-model-review-6-mistral.md](reviews/2026-11-16-model-review-6-mistral.md) (F1-F10; F3's "tselect/tdata1 S-mode writable" claim at :46, F10's "MADT GICC has no efficiency class" at :106-110).
- Commit messages: `7f1f9d0b` ("Contract: ARM64, RISC-V and later architectures after the sixth review (Mistral F1-F10)") and the D-124 entry in decisions/README.md :134.
- Web checks of the primary sources, each cited below with URL and section: Arm DEN0054 (SDEI), DEN0022 (PSCI), TF-A SDEI docs, Arm ARM DDI 0487 material via its register descriptions and the Linux `esr.h` mirror, GIC IHI 0069 pages, RISC-V privileged spec (v20260120) machine/supervisor chapters, debug spec v1.0 (Sdtrig), SBI HSM v3.0 and probe extension, AIA v1.0 (IMSIC, AdvAPLIC), UEFI ACPI 6.5 §5.2.12.14 plus Linux `actbl3.h` and a Xen patch for the MADT GICC, QEMU lore for FEAT_NMI/ALLINT.

## Verdict

The corrected contract's ARM64 and RISC-V hardware and firmware facts are almost all confirmed at the
primary sources: the fence classes are honestly named for what their mechanisms guarantee, the class of
each core is knowable at start from a standard interface (the SDEI registration result on ARM64, the SBI
probe of the DodOS `fence_hart` extension on RISC-V), and pass 13 was right on all three points where it
rejected the sixth review (Sdtrig trigger CSRs are machine-mode-only; the MADT GICC does carry a
processor power efficiency class, with a table-length caveat; the object-kind numbers are pinned by an abi
test). Two real defects remain: the class of a core hosting a resident Trusted OS is not knowable at
start from PSCI/SDEI alone, so the published class can disagree with the class the contract assigns and
the one-node rule keys on that published class; and the sentence "without a successful SDEI registration
the kernel has no signal its peer cannot mask" is not a fact on FEAT_NMI cores, where an NMI is masked
only by PSTATE.ALLINT. The three ARM64 open points (interrupt message words, claimable range, fault-kind
mapping) are settled below with paste-ready rules from IHI 0069 and the ESR_ELx encoding.

## Findings

### F1 — The class of a core hosting a resident Trusted OS is not knowable at start from the standard interfaces (wrong as written)

- Where: [kernel-interface.md:1086](kernel-interface.md) ("A core that hosts a resident Trusted OS refuses `CPU_OFF`") and [:1088](kernel-interface.md) (class 0 list: "the ARM64 core of a resident Trusted OS"; "the machine start-up finds it for each core from what the core and the firmware offer"; the one-node rule keyed on the class).
- How known: read. PSCI DEN0022 (https://documentation-service.arm.com, DEN0022, `CPU_OFF`/`AFFINITY_INFO`): `CPU_OFF` powers down the *calling* PE only and may return `DENIED` at call time — there is no pre-query that tells the kernel a stop will be refused. On such a core the SDEI registration *succeeds* (the client is still the highest non-secure EL), so start-up would publish class 1 while the contract lists the core under class 0.
- What a kernel author would do wrong: rely on "start-up finds the class from what the core and the firmware offer" and publish class 1; the machine then runs several nodes on a core whose stop is confirmed only by the dying kernel's own code, while the contract's one-node rule (D-116) was supposed to prevent exactly that.
- The fence itself still works (SDEI event 0 is non-maskable and the handler parks and writes `parked`), so this is a published-class defect, not a stopped-core defect.
- Smallest correction: the signed image's loader (or DodOS's own firmware) reports "resident Trusted OS" at start-up, or the text says the class of such a core is refined at the first fence attempt (own-code confirmation ⇒ treat as class 0 from then on).

### F2 — "Without a successful SDEI registration the kernel has no signal its peer cannot mask" is not a fact on FEAT_NMI cores (wrong as a statement of hardware; the class-0 choice stays sound)

- Where: [kernel-interface.md:1086](kernel-interface.md), last sentence.
- How known: read. FEAT_NMI (Armv8.8, `ID_AA64PFR1_EL1.NMI`): an interrupt configured as an NMI (GICD/GICR `INMIR`) is not masked by `PSTATE.I`, only by `PSTATE.ALLINT` (QEMU series, lore.kernel.org.kernel 20240407081733.3231820-1-ruanjinjie@huawei.com). So on such a core a signal exists that the peer cannot mask *with PSTATE.I*; "cannot mask at all" holds only because a hung kernel could hold ALLINT — which is exactly why class 0 remains the right default. Whether ALLINT also masks SDEI event 0 itself: not verified (DEN0054 predates FEAT_NMI).
- What a kernel author would do wrong: either assert the false absolute ("no such signal exists on any core"), or the opposite — rely on an NMI without an ALLINT discipline and lose the fence to a kernel that hangs with ALLINT set.
- Smallest correction: qualify the sentence ("without SDEI, the only remaining unmaskable-by-PSTATE.I signal would be a FEAT_NMI NMI, maskable by ALLINT, so the class is 0 unless the image declares the ALLINT discipline and the firmware configures an NMI to this core"), and optionally detect FEAT_NMI + GIC NMI support at start (`ID_AA64PFR1_EL1.NMI`, `GICD_TYPER`/INMIR support).

### F3 — On ARM64 all interrupt routing is MMIO, which the binary scan cannot see; the contract says this for RISC-V's ACLINT/APLIC but not for the GIC (clarity gap with a real consequence)

- Where: [kernel.md:161](kernel.md) (ARM64 forbidden list) vs [kernel-interface.md:1200](kernel-interface.md) (the ACLINT/APLIC sentence); the kept-ranges rule and G9/G10 at :868-907.
- How known: read + reasoning. On ARM64 every interrupt-controller configuration — `GICD_IROUTER<n>` (affinity routing of an SPI to one PE, IRM=0), `GICD_ICFGR`, the GICR, the ITS command queue — is device memory. The scan (G11) inspects instructions only; routing is protected solely by mapping: the unit register ranges are kept memory and mapped only in the gate view / the role holder's view (GIC distributor and GIC ITS have unit roles, :1200, :1729).
- What a kernel author would do wrong: conclude from the ARM64 forbidden list that the scan covers interrupt routing, and skip the mapping check.
- Smallest correction: one sentence in the ARM64 section of kernel.md: "the GIC distributor, redistributors and ITS are device memory; the scan cannot see stores to them; they are protected by mapping only (kept ranges, gate view of the role holder)".
- Checked and fine: `ICC_PMR_EL1`, `ICC_SRE_EL1`, `ICC_IGRPEN0/1_EL1` are correctly *not* forbidden — `ICC_IGRPEN1_EL1` is needed on the hot path to receive interrupts at all; PMR/SRE are per-PE self-affecting and cannot mask SDEI event 0 (non-maskable, DEN0054/TF-A). Nothing that changes translation, debug state or vector length is missing from the ARM64 list; nothing listed is needed on the ordinary hot path (the generic timer `CNTP_*` is EL0-writable per-core and not listed — correct).

### F4 — Suspected: `ssp` in the RISC-V forbidden list conflicts with the RISC-V cost paragraph if user shadow stacks are ever enabled

- Where: [kernel.md:172](kernel.md) (writes to `ssp` forbidden outside the gate) vs the RISC-V cost paragraph (only inter-hart interrupts are gate calls).
- How known: suspected (read, not run). With Zicfiss enabled for user threads, `ssp` is per-thread state restored on every context switch — a hot path — and the x86-64 list has the same shape (shadow-stack management instructions forbidden, :147). As committed this is consistent only because `riscv64.rs` FEATURES lists only `V` (no Zicfiss): in v1 `ssp` is written only at start-up.
- Smallest correction: one clause — "in v1 user shadow stacks stay disabled, so `ssp` is written only at start-up" — or, when Zicfiss is enabled, move `ssp` save/restore behind the gate and fix the cost paragraph.

### F5 — The three places where pass 13 rejected the sixth review: pass 13 was right on all three

1. **Sdtrig trigger CSRs need no entry in the forbidden list — pass 13 right, sixth review (F3) wrong.** `tselect`/`tdata1`-`tdata3` are CSRs 0x7A0-0x7A3, machine-mode read-write only: the privileged spec's CSR address map reserves 0x7A0-0x7BF for the debug system ("0x7A0-0x7AF accessible to machine mode, 0x7B0-0x7BF only in debug mode" — docs.riscv.org/reference/isa/v20260120/priv/machine.html; docs.riscv.org/reference/debug/v1.0/Sdtrig.html). An S-mode access raises an illegal-instruction exception, so supervisor code cannot arm a trigger. Confirmed. The contract's "where a delegation of triggers to supervisor mode exists, the kernel leaves it disabled" is defensive phrasing — no such delegation exists in the ratified debug spec v1.0 (not verified as to future extensions; harmless).
2. **The MADT GICC entry does carry a processor power efficiency class — pass 13 right, sixth review (F10) wrong.** UEFI ACPI 6.5 §5.2.12.14 (MADT GICC) defines the 1-byte "Processor Power Efficiency Class"; Linux `include/acpi/actbl3.h` has `efficiency_class` in `acpi_madt_generic_interrupt` with `ACPI_MADT_GICC_MIN_LENGTH = offsetof(..., efficiency_class)` (the lore patch the commit cites, 20220425123819.137735-2-pierre.gondois@arm.com; Xen patch ratatoskr.run/xen-devel/2026/01/15396593/t). Caveat to add: the field exists only when GICC Length ≥ 82 (ACPI 6.3+); older tables (76/80 bytes) lack it and the byte reads 0 — [kernel-interface.md:1713](kernel-interface.md)'s "0 where the architecture has none" covers it only if "none" includes "table too short". Exact minimum ACPI revision: not pinned line-by-line (6.3 per Linux/Xen). Confirmed with that caveat. (The sixth review's PPTT remark was also true — PPTT carries efficiency data too — but it does not contradict this.)
3. **The kind numbers were already pinned — pass 13 right.** Read of `abi/src/tests.rs:115` at `2afc901`: `object_kinds_and_page_sizes_have_their_numbers` asserts every `ObjectKind` number equals its index (Vcpu=16 … Role=20). Repo fact, confirmed.

## The ARM64 open points, settled (paste-ready)

For [kernel-interface.md:1891](kernel-interface.md). Sources: GIC IHI 0069 (INTID ranges, GITS_TRANSLATER, ITS translation, GICD_IROUTER; support.arm.com IHI 0069 pages) and Arm ARM DDI 0487 ESR_ELx encoding (Linux mirror arch/arm64/include/asm/esr.h).

**(a) The two message words of `irq_claim` ([kernel-interface.md:698](kernel-interface.md), entry `Interrupts` :1724):**

- LPI (message interrupt): result = (address, data) = (physical address of the owning ITS's `GITS_TRANSLATER` register, the EventID granted). A peripheral generates an LPI by writing the EventID to `GITS_TRANSLATER`; the ITS translates (DeviceID, EventID) → (INTID, target PE) through its device and collection tables and writes the LPI to the redistributor (IHI 0069, GITS_TRANSLATER and ITS chapter).
- SPI (line): result = (0, 0); the INTID is programmed by the GIC distributor role holder — `GICD_IROUTER<n>` with IRM=0 routes the SPI to the one claiming PE's MPIDR affinity — exactly as the IOAPIC role holder programs a GSI on x86-64.
- SGIs (INTIDs 0-15), PPIs (16-31) and extended PPIs (1056-1079) are per-PE and never claimable.

**(b) The claimable range (entry `Interrupts`, first/last per class):**

- Lines: SPIs, INTIDs 32..1019, plus extended SPIs from 1024 up to the implemented INTID space when the distributor reports them (IHI 0069; GICD_TYPER).
- Messages: LPIs, INTIDs 8192..2^(GICD_TYPER.IDBits+1)−1 (LPI support requires at least 14 INTID bits; IDBits is implementation-defined, 14-24, when LPIs are supported).
- The entry publishes first/last of each class; a vector outside the published range is `invalid`, judged as at [:698](kernel-interface.md).

**(c) The mapping of fault kinds (ESR_EL2; ESR_EL1 has the same layout).** EC = ESR_ELx[31:26], DFSC = ISS[5:0], WnR = ISS bit 6:

| ESR_ELx | DFSC / note | fault kind | words |
|---|---|---|---|
| EC 0x00 (UNDEFINED), 0x07/0x08 (FP/SIMD disabled), 0x19 (SVE), 0x1D (SME) | — | 2 undefined instruction | word 2 = EC; word 4 = 1 + feature bit for 0x07/0x08/0x19/0x1D, else 0 |
| EC 0x15 (SVC AArch64) | — | 6 bad call | word 2 = 0x15 |
| EC 0x20/0x21 (instruction abort), 0x24/0x25 (data abort) | DFSC 0x04-0x07 (translation fault L0-L3) | 1 page fault | word 3: EXEC for IABT, WnR ? WRITE : READ for DABT, PRESENT clear; word 4 = FAR_ELx; word 0 = ELR_ELx |
| same | DFSC 0x08-0x0B (access flag), 0x0C-0x0F (permission) | 4 protection | ACCESS_PRESENT set; word 4 = FAR_ELx; word 0 = ELR_ELx |
| same | DFSC 0x21 (alignment) and every other DFSC (address size 0x00-0x03, SEA, …) | 4 protection | per the fixed rule (a fault that is not a translation fault); word 4 = FAR_ELx |
| EC 0x34/0x35 (watchpoint) | armed by the thread's DBGBCR/DBGWCR via `thread_write_regs` | 9 hardware breakpoint | word 3 = bits of the thread's debug registers that hit (ARM64 has no DR6; the kernel computes the match); word 4 = FAR_ELx (the watched address) |
| EC 0x38/0x3C (BRK), 0x3A/0x3B (software step) | — | 5 debug | word 0 = ELR_ELx |
| EC 0x22 (PC alignment), 0x26 (SP alignment) | — | 4 protection | — |
| EC 0x01 (WFx), 0x18 (trapped system register), 0x03-0x06, 0x0C-0x11, 0x14, 0x16/0x17 from the wrong level | — | not a thread fault (kernel bug: the scan forbids these outside the gate) | — |

**RISC-V, same open point** (scause exception code, stval = faulting address, mepc = PC; privileged spec, supervisor/machine chapters, docs.riscv.org/reference/isa/v20260120/priv/):

| scause | fault kind | words |
|---|---|---|
| 12/13/15 (instruction/load/store page fault) | 1 page fault | word 3: EXEC/READ/WRITE, PRESENT clear; word 4 = stval; word 0 = mepc |
| 1/4/5 (access fault, e.g. PMP) | 4 protection | word 4 = stval |
| 0/4/6 (misaligned) | 4 protection | per the fixed rule |
| 2 (illegal instruction) | 2 | word 4 = 1 + feature bit if the trap names a disabled extension, else 0 |
| 3 (EBREAK) | 5 debug | word 0 = mepc |
| 8/9 (ECALL from U/S) | 6 bad call | the call must come from the code page |
| watchpoints | none reachable from S-mode | Sdtrig triggers are machine-mode only (F5 above), so kind 9 is never raised on RISC-V |

RISC-V claimable range / message words: already fixed at [:698](kernel-interface.md) — (address of the target hart's IMSIC S-level interrupt file, interrupt identity as data) — confirmed against AIA IMSIC §2.1.2 (the MSI address selects the interrupt file = target hart + privilege level, the MSI data carries the identity, maximum identity 2047; docs.riscv.org/reference/aia/v1.0/IMSIC.html). Publish first = 1, last = 2047 (or the implemented maximum) in entry `Interrupts`; identity 0 reserved — not line-verified. The APLIC of each domain has one shared MMIO control region (§3.1.5, AdvAPLIC) — confirmed, matching [:1200](kernel-interface.md).

## Checked and found right (each hardware fact against its primary source)

1. **SDEI client EL and the EL1-under-a-hypervisor case** — CONFIRMED. DEN0054 + TF-A SDEI docs (https://trustedfirmware-a.readthedocs.io/en/latest/components/sdei.html, "Determining client EL"): the physical client must run at the highest implemented non-secure EL (EL2 if implemented, else EL1); the dispatcher only allows SDEI calls from EL2 if EL2 is implemented; a hypervisor at EL2 must run a virtual SDEI dispatcher for EL1 guests. So at EL1 under a hypervisor the registration fails and class 0 is knowable at start. SDEI event 0 is delivered "even when executing with exceptions masked" (DEN0054; TF-A). Whether PSTATE.ALLINT masks it: NOT VERIFIED. `SDEI_EVENT_SIGNAL` signals event 0 — CONFIRMED.
2. **FEAT_NMI** — CONFIRMED as lore/implementation evidence: Armv8.8 `ID_AA64PFR1_EL1.NMI`; NMI not masked by PSTATE.I, masked by PSTATE.ALLINT (QEMU series lore 20240407081733.3231820-1-ruanjinjie@huawei.com).
3. **PSCI `CPU_OFF` stops the calling PE only; may return DENIED at call time; `AFFINITY_INFO` returns ON/OFF/ON_PENDING** — CONFIRMED (DEN0022, https://documentation-service.arm.com, CPU_OFF / AFFINITY_INFO sections). "No standard call lets one core stop another" on ARM64 — CONFIRMED (PSCI has no remote-stop function; SDEI_EVENT_SIGNAL is the only cross-PE signal and needs registration).
4. **RISC-V: S-mode cannot mask an M-mode interrupt** — CONFIRMED. Privileged spec machine chapter: "Interrupts for higher-privilege modes, y>x, are always globally enabled regardless of the setting of the global yIE bit" (docs.riscv.org/reference/isa/v20260120/priv/machine.html).
5. **SBI HSM: `sbi_hart_stop` stops the calling hart only; STOPPED = "not executing in supervisor-mode or any lower privilege mode"; the SBI probe extension can detect the DodOS `fence_hart` EID at start** — CONFIRMED (docs.riscv.org/reference/sbi/v3.0/ext-hsm.html; probe extension). So the RISC-V class is knowable at start, and the one-node rule is implementable.
6. **Class-2 "forced" honesty on RISC-V** — CONFIRMED, conditional exactly as the contract states (the extension is DodOS's own, for firmware it can replace): the M-mode trap preempts whatever S-mode masks (item 4); RISC-V traps are precise, so at most the in-flight instruction completes, after which the hart is in M-mode and parks — no further old-kernel instruction, store, or interrupt. The precise-trap section line: NOT VERIFIED in this pass. RNMI (Smrnmi) reaching even M-mode: NOT VERIFIED (DodOS's firmware must not enable it — worth one clause).
7. **Class-1 ARM64 "signalled" honesty** — CONFIRMED: after `CPU_OFF` + `AFFINITY_INFO` = OFF the PE is powered off (cannot execute, write, or raise interrupts); before confirmation the stop is the dying kernel's own handler — the class name says exactly that. The resident-Trusted-OS core's `parked` confirmation is own-code only, which is why listing it under class 0 is honest — but see F1 for the knowability gap.
8. **Sdtrig CSRs machine-mode only** — CONFIRMED (see F5.1): privileged spec CSR map + docs.riscv.org/reference/debug/v1.0/Sdtrig.html; S-mode access → illegal instruction.
9. **MADT GICC efficiency class** — CONFIRMED with the Length ≥ 82 caveat (see F5.2).
10. **Kind numbers pinned** — CONFIRMED by read (see F5.3).
11. **GIC INTID ranges and routing** — CONFIRMED (IHI 0069): SGI 0-15, PPI 16-31, SPI 32-1019, extended PPI 1056-1079, LPI from 8192 (≥14 INTID bits required, `GICD_TYPER.IDBits` implementation-defined 14-24 with LPIs); `GITS_TRANSLATER` write carries the EventID; the ITS maps (DeviceID, EventID) → (INTID, target PE); `GICD_IROUTER` with IRM=0 routes an SPI to one PE.
12. **ESR_ELx EC/DFSC values** used in the table above — CONFIRMED via the Linux mirror of DDI 0487 (arch/arm64/include/asm/esr.h).
13. **Execute-only on RISC-V, no write-only** — CONFIRMED. PTE R/W/X table, privileged spec supervisor chapter (docs.riscv.org/reference/isa/v20260120/priv/supervisor.html): R=0,W=0,X=1 = execute-only page; R=0,W=1,X=0 = reserved for future use.
14. **One page size per level, no Svnapot/contiguous hint, 64 KB refused** — CONFIRMED as implementable. ARM64 granules 4/16/64 KB are implementation-defined and selected by TCR_EL1.TG0/TG1 (00=4 KB, 01=16 KB, 11=64 KB), so the kernel takes 16 KB or 4 KB on a 64 KB-capable core; a 64 KB table page is 8192 entries > E max 4096, so the refusal at [kernel-interface.md:94](kernel-interface.md) is right, and `Geometry::valid` (`lib.rs:459-477` at 2afc901) plus `abi/tests/review6.rs` now enforce it (read). Contiguous hint = descriptor bit 52 (DDI 0487; Linux PMD_SECT_CONTIG). Svnapot NAPOT PTEs may appear at any level (priv spec Svnapot §) — declining them is a valid choice since the kernel builds all its own tables.
15. **Tag table sized from the tag width** ([kernel-interface.md:891](kernel-interface.md), G7) — CONFIRMED: x86-64 PCID 12 bits; ARM64 ASID 8 or 16 bits (TCR_EL1.AS / FEAT_ASID16); RISC-V satp ASID: ASIDMAX = 16 for Sv39/Sv48/Sv57 (9 for Sv32) (priv spec supervisor chapter).
16. **Little-endian required** ([kernel-interface.md:1707](kernel-interface.md)) — CONFIRMED for ARM64: data-access endianness is selectable via SCTLR_EL1.EE (instruction fetch is always LE in AArch64), so the rule is a real requirement. RISC-V big-endian: NOT VERIFIED at the source in this pass (RVA23 mandates little-endian; the unprivileged spec's current statement not pinned line-by-line).
17. **Entropy** ([kernel-interface.md:1419](kernel-interface.md)) — CONFIRMED. RNDR/RNDRRS are UNDEFINED without FEAT_RNG (`ID_AA64ISAR0_EL1.RNDR`; df.lth.se RNDRRS page). The Zkr `seed` CSR is readable from S-/HS-mode only when machine mode has set `mseccfg.SSEED`, otherwise the read is an illegal instruction (privileged spec machine chapter, mseccfg; docs.riscv.org/reference/isa/v20260120/priv/machine.html; scalar-crypto page; OpenSBI change lists.infradead.org/pipermail/opensbi/2023-October/005780.html).
18. **AIA: IMSIC and APLIC** — CONFIRMED (docs.riscv.org/reference/aia/v1.0/): one interrupt file per privilege level per hart; maximum interrupt identity 2047; the MSI address selects the interrupt file (target hart + privilege level) and the data carries the identity (§2.1.2 MSI encoding) — matches [kernel-interface.md:698](kernel-interface.md); each APLIC interrupt domain has one shared memory-mapped control region (§3.1.5) — matches :1200 ("its registers are shared by every hart of the domain").
19. **`ICC_SGI1R_EL1` writable at EL1** (when `ICC_SRE_EL1.SRE`=1) — CONFIRMED (df.lth.se getz page) — this is why the scan forbids every `ICC_SGI*` write and the gate makes them (G10).
20. **`REGS_WORDS = 26`** — right, and only for x86-64: [kernel-interface.md:1450](kernel-interface.md) scopes it to module `x86_64`, `x86_64.rs` at 2afc901 says 26, matching the register-calls section's 26 words; `aarch64.rs`/`riscv64.rs` define FEATURES only, so 26 is not claimed for ARM64/RISC-V. The ARM64/RISC-V blocks remain an open point (already noted); natural sizes: ARM64 ≈ 34 words (x0-x30, SP, PC, PSTATE), RISC-V ≈ 32 (x1-x31 + pc), both ≤ 58.
21. **The one-node rule's knowability** — CONFIRMED on each architecture from a standard interface: ARM64 via the `SDEI_EVENT_REGISTER` status at start, RISC-V via the SBI probe of the `fence_hart` EID, x86-64 via the bootstrap flag and VMX state — with the single exception of F1 (resident Trusted OS).

## What I did not have time to check

- Whether PSTATE.ALLINT (FEAT_NMI) masks SDEI event 0 — DEN0054 predates FEAT_NMI; TF-A says only "exceptions masked" (DAIF).
- RISC-V big-endian at the unprivileged specification (RVA23's little-endian mandate noted, not line-pinned).
- The precise-trap section line of the privileged spec (the masking rule is confirmed; the instruction-boundary claim is standard but not pinned), and Smrnmi/RNMI interaction with M-mode traps.
- The exact minimum ACPI revision that adds the GICC efficiency class (6.3 per Linux/Xen, not pinned to a uefi.org line), and whether IMSIC identity 0 is reserved.
- SMMUv3 (IHI 0070) and ACPI IORT details beyond what the contract already cites; the diff's x86-64-only claims (outside my angle).
- The remaining "Open points" entries other than the ARM64 interrupt/fault one (:1879-1894).
