# Model review 6 (Mistral) — does the contract hold on ARM64 and RISC-V, and does it leave room for architectures that do not exist yet?

Date: 2026-11-16. Reviewer angle (per the common brief): portability of the contract off the x86-64 reference machine, and headroom for future architectures. Review only; nothing in the repo was changed.

## What I read and ran

Read in full:

- [Docs/architecture/kernel-interface.md](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md) (1880 lines, the whole contract).
- [Docs/architecture/kernel.md](/Users/btw/Documents/repos/Docs/architecture/kernel.md) (208 lines; per-architecture write-gate mechanisms and forbidden-instruction lists at lines 147, 160, 170).
- The `abi` crate of [dodos-kernel](/Users/btw/Documents/repos/dodos-kernel): `abi/src/lib.rs` (1129 lines), `machine.rs` (1267), `start.rs` (362), `features.rs` (202), `x86_64.rs` (136), `aarch64.rs`, `riscv64.rs`.
- Decisions D-112 to D-123 via `Docs/decisions/README.md` (D-121 in particular: the page size is a value of the machine — 4 KB on x86-64 and RISC-V, 16 KB on ARM64 where supported, 4 KB otherwise). The research drafts `gate-page-tables.md` and `fencing-without-cooperation.md` were skimmed by grep only (the fencing draft states: "No remote stop anywhere in the standard firmware interfaces").
- The model: `model/src/boot.rs:184` (`SIXTEEN_KB = Geometry { page_shift: [14,25,36,0], ... }` — the model is exercised with 4 KB and 16 KB pages only) and `model/src/caps.rs:133` (aspace size = `ASPACE_PAGES * page`).

Ran (in a scratch copy at `/tmp/review6-mistral/dodos-kernel`; the repo itself untouched): one new test file `abi/tests/review6.rs`, `cargo test -p dodos-abi --test review6` — 2 tests passed, proving that `Geometry::valid()` in `abi/src/lib.rs` never ties `entries` to `page_shift[0]`: it accepts a 64 KB page (shift 16) with `entries: 4096`, although a 64 KB table page holds 8192 entries, which exceeds `TABLE_ENTRIES_MAX = 4096`; and it accepts `entries: 2` on a 4 KB page. I did not run the model's own test suite (not needed for this angle).

Hardware facts below were checked against primary sources on the web; each carries its URL. Facts I could not check are listed at the end as "not verified". Earlier reviews in this directory were not read, per the brief.

## Verdict

The contract's core — capabilities, objects, IPC, scheduling, memory ownership, and the multi-node part — is written in machine-neutral terms and holds on ARM64 and RISC-V; the D-121 page-size work is genuine but incomplete (the 64 KB granule refusal exists only as prose in the abi crate, and Svnapot is never addressed). The architecture-specific soft spots are the fence (ARM64 SDEI is not available to an EL1 kernel on EL3 firmware and RISC-V has no remote stop in standard firmware, yet both are classed as "signalled") and G10, which the per-architecture scan lists cannot enforce as written on ARM64 and RISC-V. The gate rules G1–G14 themselves are meetable on both architectures through a gate translation context, at a per-call cost the contract's cost paragraph counts only for x86-64.

## Findings

### F1 — ARM64 fence class 1 assumes SDEI, which an EL1 kernel cannot use on EL3 firmware; without FEAT_NMI there is no unmaskable signal at all

- **Where:** [kernel-interface.md:1077–1079](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md) — ARM64 fence via SDEI with PSTATE.I masked; fence classes at :1079 put every ARM64 core in class 1, "a signal its kernel cannot mask"; the same section admits "Not covered: ARM64 machines without SDEI where the handler cannot run".
- **What is wrong:** SDEI (Arm DEN0054, <https://developer.arm.com/docs/den0054/a/>) requires the client to execute at the highest implemented Non-secure exception level; on firmware with an EL3 dispatcher the client must be EL2, so a kernel at EL1 cannot register SDEI. SDEI events do preempt even masked PSTATE — but only if registered. Separately, without FEAT_NMI, PSTATE.ALLINT still masks priority-0 interrupts (<https://support.arm.com/documentation/111107/0000/ALLINT...>), so there is no interrupt the kernel cannot mask; PSCI CPU_OFF acts on the calling PE only (DEN0022, <https://documentation-service.arm.com/static/6703a8b8d7e4b739d817e10d>), which is a self-stop, not a remote one. So on the common ARM64 server shape (EL3/TF-A firmware, no FEAT_NMI) an ARM64 core is in practice fence class 0, cooperative only — exactly the case the contract says it does not cover but still classes as 1.
- **How I know:** read of the contract + web check of DEN0054, the ARM support article on ALLINT/FEAT_NMI, and DEN0022 (URLs above).
- **What a kernel author would do wrong:** build a node placement or a unit role that relies on a forced stop of an ARM64 peer, discover at run time that the "signal" never arrives (no SDEI registration, priority-0 interrupt masked by ALLINT), and either deadlock the fence protocol or silently fall back to cooperation while believing the core is fenced.
- **Smallest correction:** derive the fence class from what the firmware actually offers (SDEI registered at the kernel's EL, else FEAT_NMI with ALLINT discipline, else class 0); on class-0 machines state that roles and placement must not depend on a forced stop, and require the external monitor where they do.

### F2 — RISC-V fence class 1 is overstated: no remote stop exists in standard firmware; `fence_hart` is a DodOS-specific extension nothing ships

- **Where:** [kernel-interface.md:1078–1079](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md) — RISC-V fence via `fence_hart` / SBI `hart_stop`; class 1 = "signalled".
- **What is wrong:** in S-mode, `sstatus.SIE` masks all S-mode interrupts (RISC-V privileged spec, <https://docs.riscv.org/reference/isa/v20260120/priv/interrupts.html>); there is no NMI in the base ISA. SBI HSM v3.0 (<https://docs.riscv.org/reference/sbi/v3.0/ext-hsm.html>) defines `sbi_hart_stop` for the *calling* hart (invoked with S-mode interrupts disabled) and `hart_start` to start a STOPPED hart; like PSCI, no standard call stops a *remote* hart. The fencing research draft says the same: "No remote stop anywhere in the standard firmware interfaces." `fence_hart` is therefore a custom firmware extension the contract assumes; a hart on stock SBI firmware is cooperative-only (class 0), not "signalled".
- **How I know:** read of the contract + web check of the SBI HSM chapter and the privileged spec interrupt chapter (URLs above) + the fencing draft (grep).
- **What a kernel author would do wrong:** treat every RISC-V machine as remotely fenceable, then find that stopping a parked peer needs either the custom `fence_hart` extension in firmware or the external monitor — i.e. the "unfenced residue" rules of the contract become the common case, not the exception.
- **Smallest correction:** say that RISC-V harts without the `fence_hart` firmware extension are fence class 0, and that machines which want unit roles on RISC-V must ship that extension (or the monitor); keep `sbi_hart_stop` for the self-fence path only.

### F3 — G10 is not enforceable by the scan lists as written on ARM64 and RISC-V; the per-arch IPI path costs a gate call the contract never counts for RISC-V

- **Where:** G10 at [kernel-interface.md:886](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md); forbidden-instruction lists at [kernel.md:147 (x86-64), :160 (ARM64), :170 (RISC-V)](/Users/btw/Documents/repos/Docs/architecture/kernel.md); cost paragraph at [kernel-interface.md:894](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md) ("on x86-64 the end of interrupt, the timer deadline and interrupts to other cores").
- **What is wrong, in four parts:**
  1. The ARM64 list does not forbid `ICC_SGI1R_EL1`, the register that sends an SGI. A priority-0 fence signal is then indistinguishable from an allowed ordinary SGI by instruction alone, so the scan cannot enforce "the fence signal goes only to fenced cores" (the scan works on x86-64 because NMI/INIT/SIPI are distinct mechanisms, not because of the list).
  2. Both non-x86 lists omit the debug/trigger registers: ARM64 `DBGBCR_EL1`/`DBGWCR_EL1` are EL1-writable (<https://support.arm.com/documentation/102120/0101>), RISC-V `tselect`/`tdata1` are S-mode writable. A parked node could arm a cross-node watchpoint and snoop another node's accesses.
  3. Neither list forbids `ZCR_EL1` / `SMCR_EL1` (SVE/SME vector-length registers, per-core and EL1-writable — <https://support.arm.com/documentation/ddi0601/latest/"), so decision D-118's "one vector length per kind" is not protected on the core itself.
  4. On RISC-V an inter-hart IPI is a store to the ACLINT MSWI register, a per-hart register in a shared MMIO region (<https://github.com/riscvarchive/riscv-aclint/blob/main/riscv-aclint.adoc>); the only way G10 can stop it is the gate-view mapping of the controller registers — so every IPI pays a gate call. The cost paragraph at :894 lists that cost only for x86-64.
- **How I know:** read of kernel.md lists and the contract + web check of the debug-register and ZCR pages and the ACLINT spec (URLs above). The GIC SGI routing fact (GICD_IROUTER routes one SPI to one PE; LPIs are message-based via the ITS — IHI0069) was checked at the spec level; the LPI trigger-mode detail is not verified (see end).
- **What a kernel author would do wrong:** rely on the scan to keep the fence signal, debug watchpoints and vector length out of parked nodes on ARM64/RISC-V, and budget IPIs as cheap when on RISC-V each one is a gate call.
- **Smallest correction:** extend the ARM64 list with `ICC_SGI1R_EL1` (or a priority-0-only form) and both lists with the debug/trigger and vector-length registers; state that on RISC-V controller MMIO is mapped only in the gate view of the core, and add "interrupts to other cores" to the cost paragraph for ARM64 and RISC-V, not just x86-64.

### F4 — page sizes: the 64 KB granule refusal is prose-only in the abi crate (run-proven), Svnapot is unaddressed, and the slot parentheticals are 4 KB-specific

- **Where:** refusal of E > 4096 at [kernel-interface.md:94](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md); `Geometry::valid()` in [abi/src/lib.rs](/Users/btw/Documents/repos/dodos-kernel/abi/src/lib.rs); model geometry at [model/src/boot.rs:184](/Users/btw/Documents/repos/dodos-kernel/model/src/boot.rs); slot layout parentheticals "low 13 bits are 0" / "low 12 bits are 0" at [kernel-interface.md:1584](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md).
- **What is wrong, in three parts:**
  1. On a 64 KB granule (a legal ARM64 configuration — granules 4/16/64 KB, so 64 KB tables hold 8192 entries; <https://support.arm.com/documentation/ddi0601/latest/>), a table page has 8192 entries > E max 4096, so the kernel must refuse to start per :94 — but `Geometry::valid()` never checks `entries == page / 8`. My run in the /tmp copy proves it: `Geometry { page_shift: [16, ...], entries: 4096 }` passes `valid()` (a 64 KB table page actually has 8192 entries > `TABLE_ENTRIES_MAX`), and `entries: 2` on a 4 KB page also passes. The model is only ever tested with 4 KB and 16 KB (`boot.rs:184`), so nothing catches this.
  2. RVA23 mandates Svnapot (<https://github.com/riscv/riscv-profiles/blob/main/src/rva23-profile.adoc>, <https://docs.riscv.org/reference/rva23/>), whose NAPOT entries can appear at *any* level including a leaf (<https://docs.riscv.org/reference/isa/v20260120/priv/supervisor.html> §11.1.7). The contract's large pages are defined as "sizes one entry of a higher table maps", and the level/free-list rules assume one level per size; the contract never says the kernel declines Svnapot.
  3. "low 12/13 bits are 0" at :1584 is true only for a 4 KB page; the real invariant is that the field width (not the page size) is what makes the fields fit.
- **How I know:** run (the abi test above) + read + web check of the ARM granule sizes and the RISC-V Svnapot/RVA23 chapters (URLs above).
- **What a kernel author would do wrong:** accept a 64 KB machine into `Geometry::valid`, then either run with an entry count the hardware contradicts or discover the refusal only at first table allocation; on RISC-V RVA23, map NAPOT entries the level model does not anticipate.
- **Smallest correction:** add `entries == 1 << (page_shift[0] - 3)` to `Geometry::valid()` with a test, and add a 64 KB geometry to the model expecting the refusal; state explicitly "the kernel does not use Svnapot"; reword the :1584 parentheticals to "the field widths leave the low bits zero".

### F5 — "processors of version 1 cannot express write-only or execute-only" is false on RISC-V

- **Where:** [kernel-interface.md:292](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md).
- **What is wrong:** RISC-V PTE R/W/X bits are independent and only the combination R=0, W=1 is reserved (<https://docs.riscv.org/reference/isa/v20260120/priv/supervisor.html> §11.1.1, table of PTE bit combinations), so execute-only *is* expressible on RISC-V. The rule itself (W^X) is a fine design choice; the hardware justification is wrong, and it matters for future readers who may want execute-only user pages on RISC-V.
- **How I know:** read + web check of the privileged spec's PTE table (URL above).
- **What a kernel author would do wrong:** believe execute-only mappings are impossible and avoid a useful permission, or copy the sentence into architecture documentation.
- **Smallest correction:** reword to "the contract does not use write-only or execute-only mappings (execute-only is expressible on RISC-V and unused)".

### F6 — "RISC-V interrupt controllers have registers with a natural single writer" is not a hardware property

- **Where:** [kernel-interface.md:1190](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md) (roles).
- **What is wrong:** ACLINT MSWI/MTIMECMP are per-hart registers inside shared MMIO regions that any hart can write (<https://github.com/riscvarchive/riscv-aclint/blob/main/riscv-aclint.adoc>); PLIC/APLIC context registers are per-context but the global registers are shared. The only hardware single-writer mechanism is PMP, which is region-granular, per-hart, and programmed by M-mode firmware — a firmware setup, not a property of the controller. On ARM64 the equivalent claim is saved by GICD_IROUTER routing each SPI to one PE (IHI0069), which RISC-V lacks.
- **How I know:** read + web check of the ACLINT spec (URL above); PLIC/AIA register sharing per the AIA introduction (<https://docs.riscv.org/reference/aia/v1.0/intro.html>) and the IOMMU spec for the analogous command-queue model (<https://github.com/riscv-non-isa/riscv-iommu/blob/main/src/iommu_registers.adoc>).
- **What a kernel author would do wrong:** map a RISC-V interrupt controller's registers into a unit role holder believing the hardware serializes writers, and let a parked node reprogram another hart's timer or IPI register.
- **Smallest correction:** treat RISC-V controller registers like any unit register — mapped only in the gate view of the role holder, per core — or require PMP protection of the controller MMIO and say so explicitly.

### F7 — entropy: on RISC-V the `seed` CSR exists only if M-mode sets `mseccfg.SSEED`, yet entropy_read is "never unsupported" and the generator is "seeded from the processor's source"

- **Where:** [kernel-interface.md:1408](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md).
- **What is wrong:** RVA23 mandates Zkr (<https://github.com/riscv/riscv-profiles/blob/main/src/rva23-profile.adoc>), but the `seed` CSR is readable from S-mode only when M-mode has set `mseccfg.SSEED = 1` (<https://docs.riscv.org/reference/isa/v20240411/unpriv/scalar-crypto.html>, Zkr chapter). On firmware that leaves SSEED clear there is no processor entropy source, so "seeded from the processor's source" and "never unsupported" cannot both hold as written.
- **How I know:** read + web check of the Zkr/seed CSR documentation and RVA23 (URLs above).
- **What a kernel author would do wrong:** build the entropy path on the assumption that a `seed` read always works, and fail at run time on firmware with SSEED clear.
- **Smallest correction:** keep "entropy_read never fails", but say the generator is seeded from the processor's source *where the architecture and firmware provide one* (x86 RDRAND/RDSEED, ARM RNDR, RISC-V `seed` only with SSEED set), else from the platform service.

### F8 — the interrupt result words, claimable range and fault kinds are x86-64-shaped with no per-architecture definition

- **Where:** irq table "vectors 48 to 239, 192 entries, 12 KB" at [kernel-interface.md:688](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md); `irq_claim` result "MSI address, MSI data … 0 and 0 for a line" at :694; fault kinds table with an x86-64 column only at :392–404.
- **What is wrong:** on GICv3 the claimable set is INTIDs, not "vectors 48–239": the INTID space is implementation-defined (minimum 10 bits, 14 with LPIs; SPIs start at 32, base 32–1019) (IHI0069), and delivery to a PE is by GICD_IROUTER/LPIs via the ITS (`GITS_TRANSLATER` + EventID), so "MSI address, MSI data" has no meaning — the device writes an EventID, not an MSI. On RISC-V with AIA the MSI is an IMSIC MSI address plus an interrupt file (<https://docs.riscv.org/reference/aia/v1.0/intro.html>); with a PLIC there is no MSI at all. The fault table has no kind for RISC-V misaligned-access causes (4/6) or access-fault causes (1/5/7); ARM64 alignment faults (EC 0x22/0x26) must be folded into an existing kind without the contract saying which.
- **How I know:** read + web check of IHI0069 (via the ARM GIC architecture summary), the AIA intro, and the RISC-V exception-cause table in the privileged spec (URLs above). GICv3 LPI trigger mode: not verified.
- **What a kernel author would do wrong:** size the irq table from "192 entries" on ARM64 (wrong: INTID width is implementation-defined), or parse the claim result as MSI address/data on ARM64/RISC-V AIA and get garbage.
- **Smallest correction:** define per architecture in the Architectures section: the claimable range (GICv3 INTIDs; RISC-V hart/context × interrupt number), the result words for `irq_claim` (ITS EventID+deviceID; IMSIC address+file; PLIC: 0 and 0), and the mapping of RISC-V causes 1/4/5/6/7 and ARM64 alignment faults to a fault kind (kind 4, or a new kind).

### F9 — G1–G14 are meetable on ARM64 and RISC-V only through a gate translation context, at costs the contract counts only for x86-64; tag-table sizing is ASID-width-dependent

- **Where:** G1–G14 at [kernel-interface.md:877–890](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md); cost at :894; G7 tags at :883; gate-page-tables draft (TTBR1 switch ≈ 284 cycles round trip on Exynos 7420, SKEE; no figure for `satp`).
- **What is right and what is missing:** the mechanism ports — a second translation context (TTBR1_EL1 window on ARM64, `satp` switch on RISC-V) gives the gate its own view, G1's "only writer" holds, G3's preset A/D bits are exactly what keeps the RISC-V hardware walker (Svadu, mandated in RVA23) from writing PTEs outside the gate, and the G11 scan is sound on A64 (4-byte fixed) and RISC-V (2-byte with the C extension). What is missing: the per-gate-call, per-address-space-switch and (on RISC-V) per-inter-core-IPI cost is stated only for x86-64 at :894; and G7's tag table must be sized from the ASID width (8 or 16 bits with FEAT_ASID16 — width without the feature: not verified), which the contract never mentions.
- **How I know:** read of the contract and drafts + web check of RVA23's Svadu mandate and the SKEE figure as quoted in the draft.
- **What a kernel author would do wrong:** assume the gate is free outside mapping changes on ARM64/RISC-V, or size the tag table for 4096 tags and overflow it on a 256-ASID machine.
- **Smallest correction:** publish the per-architecture gate cost (including RISC-V IPIs through the gate) and size the tag table from the architecture's ASID width.

### F10 — start-up and loader leftovers pin x86-64/ACPI and contain two internal contradictions

- **Where:** "the ACPI root pointer" in the loader's inputs at [kernel-interface.md:1607](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md); "power-efficiency class of the core's MADT GICC entry on ARM64" in `core_start` at :648; "All integers are little-endian" in the start-up page at :1694; "REGS_WORDS = 20" in the values-to-add list at :1439 vs "26 words" in the register block at :422.
- **What is wrong:** RISC-V machines boot from a device tree, not ACPI, so "the ACPI root pointer" is undefined there (the Architectures section mentions DT only for ISA strings). The MADT GICC carrying a power-efficiency class is suspected wrong — the efficiency class lives in PPTT, and the GICC entry does not carry one (not verified; ARM's MADT documentation would settle it); if so, `core_start` asks the kernel for a field the table does not have. "All integers are little-endian" pins LE without saying the kernel refuses big-endian machines (both ARM and RISC-V permit BE). And REGS_WORDS is 26 in the register-block section (20 GPRs + DR0–3 + DR7 + UINTR; [x86_64.rs](/Users/btw/Documents/repos/dodos-kernel/abi/src/x86_64.rs) agrees) but 20 in the values list.
- **How I know:** read of the contract and the abi crate; the MADT point is marked not verified.
- **What a kernel author would do wrong:** implement the loader against ACPI on RISC-V, read a nonexistent MADT field, or size the register block at 20 words and truncate DR6/UINTR.
- **Smallest correction:** list the platform-table input per architecture (ACPI RSDP on x86-64/ARM64 with ACPI, DTB on RISC-V and ARM64-DT); source the efficiency class from PPTT via the platform service (or set the field to 0 on ARM64); state "little-endian only; big-endian machines are refused at start-up"; make :1439 say 26.

### F11 — the aspace's "header (8 KB on the reference machine)" contradicts the abi crate's two-page aspace

- **Where:** [kernel-interface.md:256](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md) ("two pages: its root table (one page) and a header (8 KB on the reference machine)"); `ASPACE_BYTES = ASPACE_PAGES * PAGE` in [abi/src/machine.rs](/Users/btw/Documents/repos/dodos-kernel/abi/src/machine.rs) and `model/src/caps.rs:133` — two pages of 4 KB = 8 KB total, so the header is one 4 KB page, not 8 KB. With a 16 KB page the aspace is 32 KB and the header 16 KB.
- **How I know:** read of the contract, the abi crate and the model.
- **What a kernel author would do wrong:** allocate an 8 KB header inside an 8 KB aspace and overwrite the root table, or vice versa when reading the contract.
- **Smallest correction:** say "a header of one page", or make the header two pages and set `ASPACE_PAGES = 3` consistently in abi and model.

## What I checked and found right

- **D-121's page-size-as-machine-value is real, not decorative.** `StartMemory` publishes `page_shift`/`E`/`L`/`user_end` (kernel-interface.md:1713); `x86_64.rs` derives all fixed addresses from `PAGE`; module frames and floors are geometry-relative in `machine.rs`; the clearing step, the cspace segment and the debug area are byte-based; the model runs with 4 KB and 16 KB geometries (`model/src/boot.rs:184`). The reserved-slot trick (user range ends on a chunk boundary) is enforced by `Geometry::valid` and works on Sv39/Sv48/Sv57 and on 4/16/64 KB ARM64 granules.
- **The clock rule is portable.** ARM64's generic timer CNTPCT is fixed-frequency and power-management-invariant (<https://support.arm.com/documentation/102379>); RISC-V's ACLINT has one MTIME per device with per-hart MTIMECMP in shared MMIO (<https://github.com/riscvarchive/riscv-aclint/blob/main/riscv-aclint.adoc>); the contract's refuse-to-start rule covers machines that lack an invariant clock. (Whether the privileged spec mandates a single mtime: not verified.)
- **I/O ports are correctly arch-conditional** — `ioport_in/out`, `ioports_issue` return `unsupported` on the other architectures (kernel-interface.md:66, :133), slot 7 is empty elsewhere (:1387), and PCI config space is correctly treated as MMIO (ECAM) on ARM64/RISC-V. A core with no I/O ports is fully covered.
- **The register block and fault words are parameterized to the architecture layer** (:419–422); the absence of single-step on RISC-V is acknowledged; the user-interrupt hook (bit 31 + one word) is arch-neutral.
- **The feature-mask / fault-kind / vector-length mechanism is generic and future-proof**: `features.rs` carries per-architecture masks; the contract's claim that RISC-V VLEN is read-only and that ARM64 ZCR_EL1 is per-core and EL1-programmable (<https://support.arm.com/documentation/ddi0601/latest/>) checks out — a new vector extension slots into the same mechanism.
- **Hypervisor-extension room exists**: the RISC-V forbidden list includes the hypervisor CSRs (`hgatp` etc.) and the ARM64 list includes EL2 forms (kernel.md:160,170); RVA23S64 mandates the H extension (<https://docs.riscv.org/reference/rva23/>).
- **The IOMMU model maps onto real hardware**: SMMUv3 with IORT on ARM64, and on RISC-V the IOMMU spec's DDTP/DDT, device contexts, MSI page tables and command queue (<https://github.com/riscv-non-isa/riscv-iommu/blob/main/src/iommu_registers.adoc>); ATS/PRI disabled by configuration on all three architectures, as the contract requires (G9).
- **64-bit physical/virtual addresses fit the slot words** (word 1 = u64 physical, 52-bit record address at 4 KB pages); wider-than-64-bit is excluded by the contract's stated "64-bit only" decision, so no rule silently assumes 48-bit addresses except the prose noted in F4/F10.
- **CHERI headroom is partial, as it should be**: the software capability model is arch-neutral, but a 128-bit CHERI capability (<https://docs.alexrp.com/riscv/riscv_cheri_v0_9_0.pdf>) does not fit word 1 of the 64-byte slot — the slot layout is not CHERI-ready, and the contract does not claim it is; a future CHERI port would need a wider slot, which the versioned slot format leaves room for.
- **Confidential-computing modes (RME/realms) are out of scope but not contradicted**: the G rules' not-covered list names firmware (SMM/EL3/M-mode), and the physical ownership model is realm-agnostic; I did not verify the realm details (below).

## What I did not check (not verified)

- Whether the RISC-V privileged spec mandates a single `mtime` per device (I relied on the ACLINT spec's register layout).
- GICv3 LPI trigger mode (edge vs level) in IHI0069.
- Whether the ACPI MADT GICC structure carries a power-efficiency class (F10) — suspected absent; PPTT carries it.
- Whether `ICC_PMR` masks priority 0 without FEAT_NMI (the GICv3 PMR rule) — relevant to F1's fallback.
- The ASID width without FEAT_ASID16 (256 tags assumed in F9).
- Linux commit e1c467e69040 (INIT delivered to the BSP) cited by the contract — not re-verified by me.
- MTE/TBI tagged-pointer interaction with the contract's "canonical address" check — the arch layer's business, not checked.
- RME/realm-world and CHERI details — literature only (URLs above), no implementation read.
- The gate-page-tables and fencing research drafts were skimmed by grep, not read end to end; the model's own test suite was not run (one new abi test was run instead, in /tmp).
- Earlier reviews in this directory were not read, per the brief.
