# Contract review 8 — Mistral (hardware and firmware claims) — PARTIAL, paused 16 November 2026

**This review is partial.** The owner paused it on 16 November 2026; it will be resumed. The
contract has changed since this review began: pass 14C is Docs commit `b29c06c`, and Docs HEAD is
now `deabf10` ("Decisions: D-132…"). This review read the working tree at Docs HEAD `deabf10`;
`Docs/architecture/kernel-interface.md` is unchanged since commit `a0a6947`, which is an
ancestor of both `b29c06c` and `deabf10`, so every line number cited below is valid at `b29c06c`
and at HEAD. `Docs/decisions/README.md` was likewise read at HEAD (D-125 at line 135, D-126 at
line 136). Pass 14C (`b29c06c`) touched plan and draft files, not the contract; D-132
(`deabf10`) was not read.

Angle: every hardware and firmware claim of the pass, checked at the primary source (document,
version, section, quoted sentence). A claim that could not be opened is marked "not verified",
never guessed. Sources fetched on 16 November 2026; scratch copies under `/tmp` (e.g.
`/tmp/sdm086.txt`, `/tmp/armka.txt`, `/tmp/apm3.txt`, `/tmp/psci_E.txt`, `/tmp/Registers.json`,
`/tmp/xed/`, `/tmp/riscvdb/`).

## Claims checked

| # | Contract line | Claim | Primary source (version, section) | Quoted sentence | Verdict |
|---|---|---|---|---|---|
| 1 | 1246 | NMI blocks further NMIs until IRET | Intel SDM 325384-086 (Dec 2024), Vol 3A — in 086 the section is §7.7.1 (older editions §6.7.1, which the cited xem.github.io mirror has) | "While an NMI interrupt handler is executing, the processor blocks delivery of subsequent NMIs until the next execution of the IRET instruction." | verified (quote exact; section number differs by edition — finding F1) |
| 2 | 1247 | INIT on the BSP runs boot-strap code, on an AP wait-for-SIPI | SDM 086 §10.4.2 | "…subsequent INITs … examine its BSP flag (in the IA32_APIC_BASE MSR) … execute the BIOS boot-strap code (if it is the BSP) or enter a wait-for-SIPI state (if it is an AP)" | verified |
| 3 | 1247 | INIT blocked in VMX root, causes VM exits in non-root | SDM 086 §25.8 | "The INIT signal is blocked whenever a logical processor is in VMX root operation. It is not blocked in VMX non-root operation. Instead, INITs cause VM exits" | verified |
| 4 | 1247 | INIT inhibited on entering SMM | SDM 086 §33.5.1 | "…INIT operations are inhibited when the processor enters SMM" | verified |
| 5 | 1247 | INIT blocked after RSM iff VMX root | SDM 086 §33.14.2 | "INIT signals are blocked after RSM if and only if the logical processor will be in VMX root operation." | verified |
| 6 | 1247 | SDM silent on INIT arriving during SMM (held vs lost) | SDM 086 ch. 33 (full text searched) | no statement found | verified (silence confirmed) |
| 7 | 1248 | INIT-SIPI-SIPI delays 10 ms / 200 µs, an example | SDM 086 §10.4.4 "MP Initialization Example", Table 10-1 | 10-millisecond delay after INIT; 200-microsecond between SIPIs; section titled "Example" | verified; FENCE_NS 20 ms > 10.2 ms example, consistent |
| 8 | 1248 | HLT wakes on NMI/INIT | SDM 086 (HLT) | "An enabled interrupt (including NMI and SMI), a debug exception, the BINIT# signal, the INIT# signal, or the RESET# signal will resume execution" | verified |
| 9 | 1248 | machine checks broadcast; disabled MCE → shutdown | SDM 086 ch. 17 | "…an MCA signal is broadcast to all logical processors in the system" (06H_0EH and onward) | verified |
| 10 | 325 | PCID is a 12-bit tag, CR4.PCIDE bit 17 | SDM 086 | "A PCID is a 12-bit identifier… PCIDE flag (bit 17) of CR4" | verified |
| 11 | 327 | INVLPG/INVPCID act on the executing logical processor only | SDM 086 + felixcloutier mirrors of SDM Vol 2 | per-logical-processor wording; INVPCID may invalidate other PCIDs / whole TLB | verified |
| 12 | 668 | CPUID leaf 0x1A reports native model ID and core type; leaf 1 bit 15 = Hybrid | SDM Vol 2 Table 3-8 (via felixcloutier mirror; Vol 2 not downloaded) | "Bit 15: Hybrid… If CPUID.0.MAXLEAF ≥ 1AH and CPUID.1A.EAX ≠ 0, then the Native Model ID Enumeration Leaf 1AH exists"; "EAX Enumerates the native model ID and core type" | verified |
| 13 | kernel.md:134 | XSETBV writes XCR0 (AMX tile state enable) | SDM 086 | "XCR0.TILECFG (bit 17): If 1, and if XCR0.TILEDATA is also 1, Intel AMX instructions can be executed" | verified |
| 14 | 664-676 | Alder Lake is a P-core/E-core hybrid | SDM 086 §21 | "The 12th generation Intel® Core™ processor supports Alder Lake performance hybrid architecture… a unique combination of Performance and Efficient-cores (P-core and E-core)" | verified; whether a given ADL SKU's E-cores lack AMX/AVX-512 is product-level, corroborated only by secondary sources (see Not checked) |
| 15 | 1247 | Linux commit e1c467e69040 (BSP woken by NMI) | github torvalds/linux | "x86, hotplug: Wake up CPU0 via NMI instead of INIT, SIPI, SIPI … Instead of waiting for STARTUP after INITs, BSP will execute the BIOS boot-strap code" | verified (commit exists) |
| 16 | 330 | Linux v6.12 adl_cstates: C6 exit 220 µs, C10 680 µs | torvalds/linux v6.12 drivers/idle/intel_idle.c, `adl_cstates[]` | `.name = "C6" … .exit_latency = 220` ; `.name = "C10" … .exit_latency = 680` | verified exact |
| 17 | 1893 | long mode cannot run with paging off | SDM 086 | "The processor enters into IA-32e mode from protected mode by enabling paging and setting the LME bit" | verified |
| 18 | 327, kernel.md:134 | INVLPGB broadcasts to all processors; rAX[5] nested | AMD APM vol 3, 24594 rev 3.39 (Oct 2026), System Instruction Reference p. 397 (kib.kiev.ua mirror) | "Invalidations are done both in the local TLB and broadcast to all processors to perform the same invalidations"; "If rAX[5] is set, all nested translations that could be used for guest translation … are flushed" | verified exact |
| 19 | 327 | TLBSYNC guarantees all processors done | APM vol 3 r3.39 p. 398 | "For software to guarantee that all processors have seen and done the TLB invalidations, a TLBSYNC must be executed on the initiating processor." | verified exact |
| 20 | 327 | TLBSYNC drains retired memory ops and writes | APM vol 3 r3.39 p. 499 | "A TLBSYNC also ensures that memory instructions using the translations invalidated by those prior INVLPGB instructions have retired and writes using the translations have drained from the write combining buffers." | verified exact |
| 21 | 326 | TLBI ASIDE1IS broadcast applies to all PEs in the Inner Shareable domain | Arm's register description for TLBI ASIDE1IS (current issue; mirror df.lth.se/~getz/ARM/SysReg/AArch64-tlbi-aside1is.html) | "The invalidation applies to all PEs in the same Inner Shareable shareability domain as the PE that executes this System instruction." | verified exact |
| 22 | 326 | a TLBI effect is complete once a DSB follows it; DSB ISH completes it | Arm DDI 0487 **K.a** (31 May 2024; kib.kiev.ua mirror PDF), B2.3.1 "Basic definitions", subsection "TLBI effects, Completed TLBI effects and Invalidation Scopes" | "A TLBI effect E1 is a Completed TLBI effect if E1 appears in program order before a DSB.FULL effect."; and "A DSB FULL effect is generated by a DSB instruction with neither a LD nor ST qualifier" (so DSB ISH qualifies) | verified exact in K.a |
| 23 | 332 | an entry generating a listed fault is never cached in a TLB | DDI 0487 K.a, D8.16 "TLB maintenance", rule IWZCBG | "TLB invalidation is not required because an entry that generates one of the listed faults is never cached in a TLB." (listed: Translation, Address size, Access flag faults; Permission fault excluded) | verified exact in K.a |
| 24 | 332 | break-before-make list and sequence | DDI 0487 K.a, D8.16.1 "Using break-before-make when updating translation table entries", rules RWHZWS and RDDMVT | list: "A change to the memory type, Shareability or Cacheability"; OA change with write permission or differing contents; block-size changes both directions; "A global entry is created that might overlap with non-global entries"; sequence: invalid entry, DSB, broadcast TLBI, DSB, new entry, DSB | verified exact in K.a; matches the contract's list and "sequence of D8.16.1" |
| 25 | 326 | CnP resets UNKNOWN on warm reset; CnP=1 with differing tables → CONSTRAINED UNPREDICTABLE | Arm's register description for TTBR0_EL1 (current issue; df.lth.se mirror) | "The reset behavior of this field is: On a Warm reset, this field resets to an architecturally UNKNOWN value."; "…the results of translations are CONSTRAINED UNPREDICTABLE" | verified exact |
| 26 | 1249 | ALLINT masks superpriority (FEAT_NMI) interrupts | Arm's register description for ALLINT (current issue; df.lth.se mirror) | "This register is present only when FEAT_NMI is implemented"; ALLINT=1 with SCTLR_ELx.NMI=1: "an IRQ or FIQ interrupt that is targeted to ELx, with or without Superpriority, is masked" | verified for IRQ/FIQ incl. superpriority; the NMI case itself is not quoted on the page (see Not checked) |
| 27 | 1249 | PSCI MIGRATE_INFO_TYPE / MIGRATE_INFO_UP_CPU semantics; CPU_OFF DENIED on resident core | Arm DEN0022E (PSCI 1.3), §5.1.7, §5.1.8, §5.9.1 | 0x84000006; "Attempts to call CPU_OFF on the core where the Trusted OS is resident, will fail with DENIED"; 2 = "Trusted OS is either not present or does not require migration"; NOT_SUPPORTED treated as 2; 0x84000007/0xC4000007 returns the MPIDR | verified exact; contract's "returns 2 for a Trusted OS on every core" is looser than the spec — finding F2 |
| 28 | 1249 | AFFINITY_INFO state affected by in-flight CPU_ON/CPU_OFF; OFF after CPU_OFF | DEN0022E §5.7.2, §6.6 | "…the state returned by the AFFINITY_INFO call is affected by calls to CPU_ON and CPU_OFF, both of which could be in flight at the same time."; OFF = "called CPU_OFF… or the core has not been booted yet" | verified exact |
| 29 | 1249 | SDEI event IDs; TF-A v2.12.0 behaviour | TF-A tag v2.12.0: include/smc-arch… sdei.h; services/std_svc/sdei/sdei_intr_mgmt.c:351, sdei_main.c:1111/1114, sdei_intr.c:676; docs/components/sdei.rst:398; readthedocs v2.12.0 SDEI component docs | SDEI_EVENT_COMPLETE_AND_RESUME 0xC4000026; SDEI_PE_MASK 0xC400002B; SDEI_EVENT_SIGNAL 0xC400002F; "This PE is masked. We EOI the interrupt, as it can't be delegated"; SUBSCRIBE_TO_EVENT(psci_cpu_on_finish, sdei_cpu_on_init) / (psci_suspend_pwrdown_finish, sdei_cpu_wakeup_init); "Make it look as if a synchronous exception were taken at the…"; "If the client fails to complete the event handling, it might result in UNPREDICTABLE behavior in the client and potentially end up in unusable PE"; SDEI client executes at the highest implemented Non-secure EL (EL2 if implemented) | verified exact |
| 30 | 1249 | Linux parks inside the uncompleted SDEI event because of EL3 wedge | torvalds/linux master (16 Nov 2026) arch/arm64/kernel/smp.c:891 | "a CPU_OFF from that not-yet-completed context wedges EL3 on some firmware" | verified exact |
| 31 | 2131 | ARM64 16 KB pages: 47 bits on three levels; 48-bit space needs a level-0 root of 2 entries; 48 = 14 + 3×11 + 1; 2048 entries below | Arm ARM VMSA chapter (manual mirror codingbelief/…-for-armv8-a, D4.2.5; in K.a the same content is the D8 initial-lookup-level tables) | "When using the 16KB translation granule, a maximum of 1 bit of IA is resolved by a level 0 lookup."; "IA[13:0] = OA[13:0]"; 48-bit figure D4-10 | verified (arithmetic and rules match; K.a's own table not separately located in the extracted text) |
| 32 | 675 | on ARM64 ZCR_ELx.LEN can lower the SVE vector length | Arm SVE supplement DDI 0584A | "The ZCR_ELx.LEN field constrains the SVE vector length to be no greater than (LEN+1)×128 bits" | verified |
| 33 | 2131 | stage 2 may use concatenated root tables | Arm ARM VMSA (as #31) | "up to 16 translation tables can be concatenated at the initial lookup level" | verified (the contract's "not used" is a design choice on a verified fact) |
| 34 | 1893 | ARM64 boot protocol: MMU off | torvalds/linux v6.12 Documentation/arch/arm64/booting.rst:176 | "The MMU must be off." | verified exact |
| 35 | 1250 | sbi_hart_stop stops the calling hart only; sbi_hart_get_status; STOPPED state | RISC-V SBI v3.0, HSM extension (docs.riscv.org/reference/sbi/ext-hsm.html) | "Request the SBI implementation to stop executing the calling hart in supervisor-mode and return its ownership to the SBI implementation."; STOPPED: "The hart is not executing in supervisor-mode or any lower privilege mode."; hart start: satp 0, MMU off | verified exact |
| 36 | 327 | SBI remote fence with hart mask and ASID | SBI v3.0 RFENCE extension (ext-rfence.html) | `sbi_remote_sfence_vma_asid(hart_mask, hart_mask_base, start_addr, size, asid)` | verified |
| 37 | 327, gate-page-tables draft | writing satp implies no ordering and no invalidation; SFENCE.VMA is local; other harts need a shootdown; ASID/global rules | RISC-V Privileged Architecture, main branch 2026-11-14, src/priv/supervisor.adoc | "Note that writing satp does not imply any ordering constraints between page-table updates and subsequent address translations, nor does it imply any invalidation of address-translation caches."; "SFENCE.VMA orders only the local hart's implicit references…"; "…other harts must be notified separately… This is, of course, the RISC-V analog to a TLB shootdown."; rs2 selects the ASID, global mappings excepted | verified exact |
| 38 | 1250 | EEI defines per-trap preciseness | RISC-V Unprivileged ISA, main 2026-11-14, Vol I §1.6 "Exceptions, Traps, and Interrupts" (src/unpriv/intro.adoc) | "The EEI defines for each trap whether it is handled precisely, though the recommendation is to maintain preciseness where possible." | verified exact |
| 39 | 675 | RISC-V VLEN is a per-hart design-time constant; vlenb read-only; no migration of active vector state between harts of different VLEN | RISC-V Unprivileged ISA, main 2026-11-14, src/unpriv/vector-common.adoc | "Each hart supporting a vector extension defines two parameters" (VLEN, ELEN); "Each vector register has a fixed VLEN bits of state."; vlenb "read-only CSR … design-time constant"; "thread contexts with active vector state cannot be migrated during execution between harts that have any difference in VLEN or ELEN parameters." | verified exact |
| 40 | 2134, 1893 | without Svpbmt the memory type is the PMA's; RISC-V boot: satp 0 | RISC-V Privileged spec svpbmt.adoc; linux v6.12 Documentation/arch/riscv/boot.rst:34 | Svpbmt adds "page-based memory types that override the PMA(s)"; "``$satp = 0``: the MMU, if present, must be disabled." | verified |
| 41 | 2121 | AIA stopei/IMSIC indirect registers exist in the AIA spec but are absent from riscv-unified-db; db is BSD-3-Clause-Clear | riscv/riscv-aia main src/IMSIC.adoc (stopei documented); riscv/riscv-unified-db main @ 2026-11-16 (blobless clone; full file tree listing: no stopei/mtopei/mireg/sireg/AIA; root has LICENSE-BSD-3-Clause-Clear.txt) | — | verified |
| 42 | 1878 | UEFI memory-type mapping of the hand-over block | UEFI Specification 2.10 §7.2 (uefi.org/specs/UEFI/2.10/07_Services_Boot_Services.html via wayback 2026-06-01) | "Following the ExitBootServices() call, the image implicitly owns all unused memory in the map. This includes memory types EfiLoaderCode, EfiLoaderData, EfiBootServicesCode, EfiBootServicesData, and EfiConventionalMemory."; Table 7.6 (after ExitBootServices): runtime code/data, ACPI reclaim, NVS "to be preserved"; EfiReservedMemoryType "Not usable"; EfiMemoryMappedIO "not used by the OS"; EfiUnusableMemory "contains errors and is not to be used" | verified; contract's usable/firmware/unusable mapping matches |
| 43 | 1878 | device-tree /memory and /reserved-memory | Devicetree Specification, master, source/chapter3-devicenodes.rst | "/reserved-memory Node … Reserved memory is specified as a node under the /reserved-memory node"; memory node section ("Memory nodes could be defined as follows…") | verified |
| 44 | 1879 | UBIOS memory types Free/Data/Code/Shared/Reserved/Disabled/Device | UBIOS T/GCC 3007-2025 spec PDF (gccorg.com article 69/426 linked mirror; /tmp/ubios.pdf), Table 16 "Memory Type 定义表" | "Free 0 …; Data 1 …; Code 2 …; Shared 3 …; Reserved 4 …; Disabled 5 …; Device 6 …" | verified exact; contract's UBIOS mapping matches |
| 45 | 1874 | Limine enters ARM64 with a 4 KB granule (and MMU on) | Limine-Bootloader/limine-protocol master, PROTOCOL.md, AArch64 "At entry" | "The used translation granule size for both TTBR0_EL1 and TTBR1_EL1 is 4KiB."; "the MMU (SCTLR_EL1.M) is enabled" | verified exact |
| 46 | 2121 | AARCHMRS: release 2026-09, BSD-licensed, pinned mirror | kernel.googlesource.com/pub/scm/linux/kernel/git/maz/AARCHMRS commit 1346b16d "AARCHMRS_OPENSOURCE_A_profile_FAT-2026-09" (2026-10-15, "Retrieved from https://developer.arm.com/-/cdn-downloads/…/AARCHMRS_BSD/AARCHMRS_OPENSOURCE_A_profile_FAT-2026-09.tar…"); Registers.json metadata; docs/notice.html; README.md | metadata: ref "2026-09_rel", architecture "vFATAp2-A", schema 2.9.6, "This document is Non-confidential and licensed under the BSD 3-clause license"; README: "This package contains a subset of the information provided in the packages with Arm proprietary licenses…" | verified; the counts "598 writable register encodings, 13 MSR immediate targets" were confirmed by the earlier verification's script over this exact Registers.json (Docs/reviews/2026-11-16-verify-architecture-boundary-by-mistral.md rows 46/48) and were not re-derived here |
| 47 | 2121, kernel.md:134 | XED: Apache-2.0; 69 RING0 classes; msr-imm data | intelxed/xed @ 0bcb623 (= main HEAD, "External Release v2026.08.23"): LICENSE; datafiles/**/*.txt recounted by script; datafiles/msr-imm/ | Apache License 2.0; 69 ICLASS blocks marked RING0, one-for-one with the draft's list (incl. WRMSRNS WRMSRLIST LMSW CLTS XSETBV INVLPGB TLBSYNC ERETS ERETU LKGS LOADIWKEY HRESET SETSSBSY CLRSSBSY PVALIDATE RMPADJUST RMPUPDATE PSMASH SEAM* TDCALL); msr-imm-isa.xed.txt defines RDMSR/WRMSRNS with an MSR_IMM operand | verified |
| 48 | 698 | MADT GICC efficiency class is the byte at offset 76, entry length 80 since ACPI 6.0 | Linux v6.12 include/acpi/actbl2.h, `struct acpi_madt_generic_interrupt` (comment: "GICC (ACPI 5.0 + ACPI 6.0 + ACPI 6.3 + ACPI 6.5 changes)") — packed offsets computed from the struct: header(2) + reserved(2) + … + arm_mpidr(8) end at 76, efficiency_class u8 at 76, length 80 | — | verified (offset computed, not from memory; ACPI spec PDF itself not opened) |
| 49 | 1439 | FENCE_NS 20 ms covers the SDM example (10.2 ms); CORE_ANSWER_NS 10 ms and SEAL_NS 1 s not contradicted by any hardware document | SDM 086 §10.4.4 (example only; the SDM states no required delays); contract itself marks CORE_ANSWER_NS/SEAL_NS "to measure" | — | verified consistent; no required figure exists to check against |
| 50 | 330 | deep-idle exit times used to justify not waiting for idle cores | linux v6.12 intel_idle.c adl_cstates | C6 exit_latency 220 µs, C10 680 µs | verified exact (row 16) |

## Findings so far

| # | Severity | Lines | Finding | Smallest paste-ready fix |
|---|---|---|---|---|
| F1 | wording | kernel-interface.md:1246 | The NMI-blocking quote is cited as "Intel SDM Vol. 3A, §6.7.1 'Handling Multiple NMIs'"; in the pinned edition 325384-086 (Dec 2024) the section is §7.7.1 — §6.7.1 is the number in older editions (the xem.github.io mirror the contract links). The quote is verbatim in both. | Write "§7.7.1 in 325384-086 (Dec 2024; §6.7.1 in earlier editions)". |
| F2 | wording | kernel-interface.md:1249 | "it returns 2 for a Trusted OS on every core" — DEN0022E §5.1.7/§5.9.1 says 2 means the Trusted OS is "either not present or does not require migration" (MP capable or not present). | Write "returns 2 when the Trusted OS is MP-capable or not present". |

No claim checked so far was contradicted by its primary source. All ARM K.a citations of
lines 326/332 (B2.3 "Completed TLBI effects", D8.16 "never cached in a TLB", D8.16.1
break-before-make) were re-checked against the DDI 0487 K.a PDF itself and are correct as
cited — an earlier note that "B2.3 Completed TLBI effects" could not be found was wrong; it is
a subsection of B2.3.1 in K.a.

## Not checked yet

For whoever resumes — claims of this angle not yet reached or only partially verified:

- Pass 14C (`b29c06c`) and D-132 (`deabf10`): whether any draft/plan sentence quoted by the
  contract changed; `Docs/decisions/README.md` beyond D-125/D-126 (D-127 to D-132 unread here).
- x86-64: the exact SDM sentences that INVLPG/INVPCID "may invalidate entries for other
  addresses / other PCIDs / the entire TLB" (seen on the felixcloutier mirror; not re-grepped in
  `/tmp/sdm086.txt`); SDM Vol 2 not downloaded (leaf 0x1A checked via mirror only).
- ARM64: existence of `TLBI VALE1IS` (last-level form) and the "EL2&0 forms" wording of
  `TLBI VAE1IS` in K.a (not located in `/tmp/armka.txt`); whether ALLINT masks an NMI
  specifically (the ALLINT page quotes IRQ/FIQ "with or without Superpriority"); the SDEI spec
  DEN0054 itself (TF-A docs were read instead); FEAT_NMI in the ARM ARM K.a text.
- RISC-V: nothing to verify for the project's own proposed `fence_hart` extension (its
  guarantee is a requirement on firmware the project writes); the unified-db listing was
  checked by file tree (no stopei/mtopei/mireg/sireg/AIA), not by content search of the db.
- Hybrid: Intel ark page for i5-14600KF (6P+8E) not opened; per-core AMX/AVX-512 absence on
  ADL E-cores corroborated only by secondary sources (Intel community, Tom's Hardware), not by
  an Intel primary document.
- AARCHMRS: the 598/13 counts not re-derived in this review (relied on the earlier
  verification's script over Registers.json @ 1346b16; the file, license and release metadata
  were re-opened here).
- D-126 (language split): the Zig 0.17.1 toolchain claims (`std.debug.simple_panic` not
  freestanding, volatile struct-literal RMW per field, FullPanic 3.6 KB) are not
  hardware/firmware claims and were not checked.
- UEFI: differences of spec 2.11 vs 2.10 not checked; "second signed program" and "lacks five
  duties" are internal design claims, not hardware claims.
- Deep-sleep: the contract's only hardware figures are C6 220 µs / C10 680 µs (verified, row
  16); no other exit-time figure is given in the text.
- If the contract moves again, re-anchor every line number before resuming.
