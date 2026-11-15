# Several architectures: where the kernel's boundary runs

**Research draft, 15 November 2026. Not integrated: not the contract.** Written by an agent at the owners' request. It turns the five directions the owners accepted (one page-table code from a description, a common entry path, registers from the machine-readable specifications, the hand-over to the kernel, synthesised translation code) and two questions (the reference model as the kernel's core; what stays per architecture) into proposals precise enough to be written into [kernel-interface.md](../../architecture/kernel-interface.md). Two additions from the owner are answered in part 5: a DodOS UEFI stub as the leading option for the hand-over, and a kernel independent of the firmware standard.

Every fact about hardware, a specification, a licence or another project's code is cited at its source: a URL, or a file and line in a clone whose commit is listed in [part 11](#11-sources-and-what-was-measured). What could not be checked is marked **not verified**. Line counts are physical lines (`wc -l`), comments and blank lines included, unless a part says otherwise.

## Contents

1. [Summary](#1-summary)
2. [Direction 1: one page-table code from a description of the format](#2-direction-1-one-page-table-code-from-a-description-of-the-format)
3. [Direction 2: a common entry path](#3-direction-2-a-common-entry-path)
4. [Direction 3: registers and the binary check from the specifications](#4-direction-3-registers-and-the-binary-check-from-the-specifications)
5. [Direction 4: the hand-over, a DodOS stub, and a kernel that knows no firmware standard](#5-direction-4-the-hand-over-a-dodos-stub-and-a-kernel-that-knows-no-firmware-standard)
6. [Direction 5: Velosiraptor](#6-direction-5-velosiraptor)
7. [Question 1: the reference model as the kernel's core](#7-question-1-the-reference-model-as-the-kernels-core)
8. [Question 2: what stays per architecture, and how much](#8-question-2-what-stays-per-architecture-and-how-much)
9. [What the contract must say](#9-what-the-contract-must-say)
10. [Not verified](#10-not-verified)
11. [Sources and what was measured](#11-sources-and-what-was-measured)

## 1. Summary

| Item | Recommendation | Why, in one sentence |
|---|---|---|
| 1. Page tables from a description | **Adopt**, as a format description compiled into one generic walker per format (Linux `generic_pt` and Redox `rmm` do this), with the invalidation, the root load and break-before-make kept as code | Seven formats (three CPU, four IOMMU) share one walker and the gate's checks (G3) are written once; the description costs nothing at run time when it is a compile-time constant |
| 2. Common entry path | **Adopt**, with a smaller promise than "one entry": a per-architecture stub that saves the registers into the thread's save area and calls one common Rust function per kind of event | Linux itself kept 514 to 1,576 lines of entry assembly per architecture after its generic entry; seL4's trap files are 147 to 756 lines |
| 3. Registers from the specifications | **Adopt for ARM64 and RISC-V**, generate both the accessors and the scan lists, with the rule "every encoding is classified once, an unclassified one fails the build"; **on x86-64 use Intel XED's instruction data**, since no vendor publishes registers in machine-readable form | The 2026-09 Arm package lists 598 writable AArch64 register encodings and 13 `MSR` immediate targets; XED marks 69 instruction classes ring 0, several of which the hand-written x86-64 list of kernel.md does not name |
| 4. Hand-over | **DodOS's own UEFI stub in Rust, one source for three architectures, producing a neutral hand-over that names no firmware standard**; other first stages (U-Boot or device-tree boot, a UBIOS loader, Limine for bring-up, a phone's boot chain) produce the same hand-over. Limine is not adopted as the product loader nor its protocol as the entry contract | Limine lacks five of the loader's duties, is a second signed program with about 38,000 lines in its common sources, enters ARM64 with a 4 KB granule, and its protocol carries UEFI-shaped features; a stub keeps the single signed image of security.md |
| 5. Velosiraptor | **Leave**, as kernel code and as a test oracle; keep its idea | It has no specification for ARM64, RISC-V or any IOMMU, synthesises map, protect and unmap but no invalidation, knows nothing of ownership, classes or map counts, and its tool repository's main branch was last changed on 11 July 2024 |
| Model as the core | **No: the model stays a model.** The kernel's core is written `no_std` and heap-free from the contract, behind a machine boundary of about 30 operations, and the model's tests drive both through the same call interface | The model keeps every object in `BTreeMap`s (34 map fields in `Model` alone), translations as a map from address to record, and the derivation tree as `Vec` children, while the contract fixes 64-byte slots with links inside them; reusing its logic would mean rewriting its data, which is writing the kernel |
| Per-architecture size | **Estimate: x86-64 about 7,000 lines, ARM64 about 7,500, RISC-V about 5,000**, against 19,700, 16,400 and 6,000 in seL4's 64-bit, non-virtualisation parts | The description, the common entry and the generated registers remove most of what seL4 writes per architecture; the IOMMU and the interrupt controllers stay, and they are the largest parts |

The language of the kernel matters here. D-004 decided "kernel in Zig and Rust", and the contract's [Language split](../../architecture/kernel-interface.md#language-split) (an estimate, not a decision) puts "page-table primitives and TLB", "entry and exit", "context switch" and "the IPC fast path" in Zig. Directions 1 and 2 and question 1 move the generic page-table walker and the gate's checks to Rust, next to the model's checks of the same rules and their Kani proofs, and leave Zig the stubs, the boot path and the fast path. D-004 is untouched; the estimate of the split changes. This is an open point of part 9.

## 2. Direction 1: one page-table code from a description of the format

### 2.1 What Linux `generic_pt` is, and what its authors learnt

`generic_pt` entered Linux in 6.19: `drivers/iommu/generic_pt` is absent from the v6.18 tree and present in v6.19 (both checked out from `github.com/torvalds/linux`, tags `v6.18` and `v6.19`). At v7.3 it is 6,772 lines, of which 1,369 are the IOMMU algorithms (`iommu_pt.h`), 1,511 the tests (`kunit_*.h`), and 1,330 the four formats (`fmt/amdv1.h` 413, `fmt/riscv.h` 322, `fmt/vtdss.h` 285, `fmt/x86_64.h` 280).

What it is, from its own documentation:

- **A format is code, not data.** Each format supplies a dozen inline functions under common names (`pt_load_entry_raw`, `pt_install_leaf_entry`, `pt_install_table`, `pt_entry_oa`, `pt_table_pa`, `pt_can_have_leaf`, `pt_num_items_lg2`, `pt_attr_from_entry`...) and a few constants (`PT_GRANULE_LG2SZ`, `PT_TABLEMEM_LG2SZ`, `PT_ITEM_WORD_SIZE`, `PT_MAX_TOP_LEVEL`, `PT_MAX_VA_ADDRESS_LG2`): `fmt/x86_64.h:45-160`. "The required inline functions need to be implemented in the format header" (`Documentation/driver-api/generic_pt.rst`, "Writing a Format").
- **One format per compilation unit, no function pointers below map and unmap.** "Generic PT is structured as a multi-compilation system ... This design avoids function pointers around the low level API ... the per-format code can be directly inlined" (`generic_pt.rst:14-24`). So the description costs nothing at run time.
- **The table geometry is the same at every level except the top** (`pt_fmt_defaults.h:18-20`), with optional features for what breaks this: contiguous entries, a runtime-selected top level, "runtime variable table level size (ARM's concatenated tables)", sign-extended addresses (`include/linux/generic_pt/common.h:35-45`).
- **Invalidation is not in the format.** The algorithms gather what changed (ranges, levels of leaves and tables, freed tables) and the driver issues the hardware's invalidation; "every HW has its own approach on how to describe what has changed" (`generic_pt.rst:114-140`, `iommu_pt.h:43-106`).
- **One format serves several walkers.** `fmt/x86_64.h` is "used by x86 CPUs, AMD and VT-d IOMMU HW" (`fmt/x86_64.h:17`), in its four and five level variants (line 5).
- **Scope.** At v7.3 its users are the Intel, AMD and RISC-V IOMMU drivers (`drivers/iommu/intel/iommu.c:1164`, `amd/iommu.c:2169`, `riscv/iommu.c:839`). The CPU page tables of Linux do not use it, and the Arm SMMUv3 driver still uses `io-pgtable-arm` (`arm-smmu-v3.c:2912-2921`): there is no Arm format in `generic_pt/fmt`.

Redox reached the same design for the CPU tables in Rust. Its `rmm` crate has one mapper and a trait `Arch` of associated constants (`PAGE_SHIFT`, `PAGE_ENTRY_SHIFT`, `PAGE_LEVELS`, `ENTRY_FLAG_PRESENT`, `ENTRY_FLAG_READONLY`, `ENTRY_FLAG_NO_EXEC`, `ENTRY_FLAG_DEVICE_MEMORY`...) and four functions (`invalidate`, `invalidate_all`, `table`, `set_table`): `rmm/src/arch/mod.rs:22-108`. Its instances are 118 lines for x86-64, 155 for ARM64 and 116 to 124 for each of Sv39, Sv48 and Sv57 (part 8). Two lessons are in its own comments: a constant `KERNEL_SEPARATE_TABLE` says whether the kernel half has its own root (true on ARM64: `rmm/src/arch/aarch64.rs:8`), and "TODO: rather than global constants, use an associated type that wraps the format of page table entries" (`mod.rs:40`), because flags alone could not express every format.

**What this says for DodOS.** The approach works and is cheap when the description is a compile-time constant of each instantiation; plain bit constants are not enough, so the description holds small functions where a format needs them; invalidation stays code.

### 2.2 What the reference model's `Geometry` is today

`Geometry` (`abi/src/lib.rs:388-470`) holds the log2 of each page size, *E*, *L* and the user range end. The model's page-table code (`model/src/memory.rs:13-46`) uses it to count which tables a set of translations needs; the translations themselves are a `BTreeMap<u64, Translation>` per space (`model/src/lib.rs:605`). **No entry is ever encoded**: the model has no bits, no permission encoding, no memory type in an entry and no invalidation (`model/src/lib.rs:15-17`: "the hardware (translations are a map ...) ... not modelled"). The tests run it on three geometries, x86-64, 16 KB with three levels, 32 KB with three levels (`model/src/boot.rs:193-222`). So `Geometry` proves that the model's counting has no hidden 4 KB constant; it is the shape half of a format description, not the format.

### 2.3 What the description must hold

The table below is what one format's description must say, for each format DodOS needs. Facts are from the cited headers; "Linux" files are at v7.3.

| Field | x86-64 (4 and 5 levels) | ARM64 stage 1, 4 KB and 16 KB | RISC-V Sv39, Sv48, Sv57 | VT-d second stage | AMD IOMMU v1 | SMMUv3 stage 2 | RISC-V IOMMU |
|---|---|---|---|---|---|---|---|
| Entry size, entries per table | 8 bytes, 512 | 8 bytes; 512 (4 KB), 2,048 (16 KB) | 8 bytes, 512 | 8 bytes, 512 | 8 bytes, 512 | 8 bytes, as stage 1 | 8 bytes, 512 |
| Levels | 4 or 5 (`fmt/x86_64.h:5`, PML5 with 5) | 4 KB: 4 for 48 bits; 16 KB: 3 for 47 bits, 4 for 48 bits (`arch/arm64/Kconfig:363-372`) | 3, 4, 5 | 3 to 5 by address width (`fmt/vtdss.h:5-20`) | up to 6 (`fmt/amdv1.h`) | as stage 1, with concatenated root tables allowed (`generic_pt/common.h:38`) | Sv39, Sv48, Sv57, and Sv39x4 to Sv57x4 for the second stage (**not verified** at the RISC-V IOMMU specification; Linux uses the Sv formats through `fmt/riscv.h`) |
| Levels that may hold a leaf | 4 KB, 2 MB, 1 GB (`pt_can_have_leaf`: level ≤ 2, `fmt/x86_64.h:98-101`) | 4 KB: 4 KB, 2 MB, 1 GB; 16 KB: 16 KB, 32 MB; Linux uses no level-1 block with 16 KB (`pud_sect_supported` returns true only for 4 KB, `arch/arm64/include/asm/pgtable.h:1622-1625`) | every level ("supports leafs in every level", `fmt/riscv.h:17-19`) | 4 KB, 2 MB, 1 GB (PS bit 7, `fmt/vtdss.h:52-55`) | any power of two through the "next level 7" size encoding (`fmt/amdv1.h:56`, `90-123`) | as stage 1 | every level |
| Valid, table, leaf | P bit 0; PS bit 7 marks a large leaf (`fmt/x86_64.h:60-73`) | bit 0 valid; bit 1: table or page (1) against block (0) (`pgtable-hwdef.h:164-166`, `io-pgtable-arm.c:67-72`) | V bit 0; a leaf has R, W or X set (Linux `pgtable-bits.h:11-15`; the leaf rule **not verified** at the privileged specification) | R or W set (`fmt/vtdss.h:45-50`) | PR bit 0, next level field 9-11 (`fmt/amdv1.h:54-56`) | as stage 1 | as Sv |
| Output address field | bits 12-51 (`fmt/x86_64.h:66`) | bits 12-47 with 48-bit output; other bits with 52-bit LPA (`pgtable-hwdef.h:179-187`) | PPN bits 10-53 (**not verified** at the privileged specification; Linux) | bits 12-51 (`fmt/vtdss.h:51`) | bits 12-51 (**not verified**) | as stage 1 | as Sv |
| Permissions | RW bit 1, U bit 2, XD bit 63 (`fmt/x86_64.h:60-67`); write-only and execute-only impossible | AP[1] bit 6 user, AP[2] bit 7 read-only, PXN bit 53, UXN bit 54; table entries carry PXNTable, UXNTable (`pgtable-hwdef.h:129-131`, `167-176`) | R, W, X, U bits 1-4; W without R is reserved (**not verified** at the specification) | R bit 0, W bit 1 | IR bit 61, IW bit 62 (`fmt/amdv1.h:59-60`) | S2AP bits 6-7 (`io-pgtable-arm.c:100-102`), XN 53-54 | as Sv |
| Memory type | PWT, PCD, PAT bits index the PAT register | AttrIndx bits 2-4 index `MAIR_EL1` (`pgtable-hwdef.h:195-196`) | PBMT bits 61-62 with Svpbmt (0 the physical attributes, 1 non-cacheable, 2 I/O: `pgtable-64.h:116-125`); without Svpbmt, none | SNP bit 11 (`fmt/vtdss.h:50`) | FC bit 60 (`fmt/amdv1.h:58`) | MemAttr bits 2-5 (`io-pgtable-arm.c:114-117`) | as Sv |
| Accessed and dirty | A bit 5, D bit 6, set by hardware | AF bit 10; hardware update of it is optional (Linux `cpufeature.h:905`), and an access with AF clear faults without it (**not verified** at the Arm ARM); dirty is "writable" with DBM bit 51 | A bit 6, D bit 7; under Svade a clear A, or a clear D on a write, causes a page fault (unified database `ext/Svade.yaml:11-14`); Svadu lets hardware set them | A bit 8, D bit 9 (`fmt/vtdss.h:48-49`) | D bit 6 (`fmt/amdv1.h:55`) | AF bit 10 | as Sv |
| Global, tags | G bit 8; PCID 12 bits | nG bit 11; ASID 8 or 16 bits | G bit 5; ASID from `satp` | domain number | domain number | VMID | process and guest identifiers |
| Kernel half | entries of the one root (shared, as the contract's reserved slot) | its own root, `TTBR1_EL1` (Redox `KERNEL_SEPARATE_TABLE = true`) | entries of the one root | none | none | none | none |
| Live changes without break-before-make | any | only PXN, read-only, write, nG and software bits, and Normal against Normal-Tagged; never the output address; never nG to global (`arch/arm64/mm/mmu.c:119-152`) | any | any | any | as stage 1 (**not verified**) | any |
| Invalidation after a map | none required | none for an entry that was invalid (**not verified** at the Arm ARM) | `SFENCE.VMA` unless Svvptc (`arch/riscv/include/asm/pgtable.h:570-576`) | only with caching mode 1 (contract, Devices and shared hardware) | **not verified** | **not verified** | **not verified** |
| Invalidation after unmap or reduced rights | `INVLPG` or `INVPCID`, by tag | `DSB ISHST; TLBI VAE1IS; DSB ISH; ISB` (as in Redox `rmm/src/arch/aarch64.rs:44-55`) | `SFENCE.VMA` by address and ASID | queued invalidation, wait descriptor | command buffer, completion wait | command queue, `CMD_SYNC` | command queue, fence |

Three consequences for the contract:

- **Choose the levels so that every level, the root included, has *E* entries.** The contract's bound of 2 × (*L* − 1) tables per call and its `Geometry` assume it. With 16 KB pages and 48 bits, the root has 2 entries (48 = 14 + 11 × 3 + 1); with 47 bits it has 2,048 on three levels. So ARM64 with 16 KB uses 47 bits, which is the model's `SIXTEEN_KB` geometry (`model/src/boot.rs:197-206`), and an `iospace` uses the widths whose root is full (39, 48 or 57 bits with 4 KB tables). Rule in part 9.
- **The kernel half is a field of the description.** On ARM64 the contract's reserved slot (code page and clock page, shared tables) is the last entry of the user root (`TTBR0_EL1`), and the kernel's own space is the other root. Nothing else changes.
- **RISC-V without Svpbmt cannot carry a memory type in an entry.** The contract fixes the memory type of a device frame as uncached or write-combining, chosen by the creator. Without Svpbmt the type is the platform's attribute of the physical address, and write-combining cannot be asked for. Open point with alternatives in part 9.

Two choices of the contract simplify the description and stay: one page size per level, no contiguous hints (so AMD v1's size encoding, Svnapot and ARM's contiguous bit are unused), and never splitting a large page (so the only break-before-make case left on ARM64 is one the kernel never makes: replacing a valid leaf by a leaf to another address; unmap and map are separate steps).

### 2.4 What does not fit a description and stays as code

- **Invalidation sequences** (the last two rows), per CPU architecture and per IOMMU, with their waits. The description says which change needs which kind (none, one address under one tag, the whole tag, the walk caches when a table is freed); the code issues it.
- **Loading a root with its tag** (`CR3` with PCID, `TTBR0_EL1` with ASID, `satp` with ASID and mode), which G1 and G7 give to the gate.
- **The gate's write mechanism**: `WRSSQ` on x86-64 if the shadow-stack typing of page tables works (kernel.md), a switch of translation context on ARM64 and RISC-V. The walker calls one "write entry" operation; the mechanism is behind it.
- **Start-up of translation**: turning paging on, `MAIR_EL1`, `TCR_EL1`, the PAT register.
- **Concatenated stage-2 roots of the SMMU**, if a width needs them; the rule of full roots avoids them.

### 2.5 Cost

No cost on a memory access or a TLB miss: the hardware walks the tables. On a mapping call, the generic walker compiled for one format is the same code a hand-written walker would be, if the description is a constant of the instantiation (Linux's multi-compilation, Rust generics over a format type, or Zig `comptime`). A description read at run time from a table would add a load per field per entry: refused. One kernel image holds two or three instantiations (the CPU format and the IOMMU formats of the machine), which costs code size, not time; the size is **not measured**.

### 2.6 What the contract must say, and what stays open

Rule, in [Values of the machine](../../architecture/kernel-interface.md#values-of-the-machine) or [Architectures](../../architecture/kernel-interface.md#architectures): "Each table format the kernel writes (the CPU's and each IOMMU's) is a **format description**, a compile-time value of the architecture layer, and one generic walker serves every format. The description holds: the entries per table, the levels, the levels that may hold a leaf, the encodings of present, table and leaf, the output address field, the encodings of `read`, `write`, `exec` and user access, the memory types and their encodings, the accessed and dirty bits to preset, the global bit, whether the kernel half has its own root, the changes allowed on a live entry, and the invalidation each change needs. The invalidation, the loading of a root and the gate's write are code of the architecture layer. Every level of a table, the root included, has *E* entries: the kernel chooses the levels of the CPU and the widths of the iospaces so that it holds."

Open points: (1) the language of the walker and the gate (Rust, recommended, beside the model's checks and Kani; or Zig with `comptime`); (2) RISC-V without Svpbmt (part 9).

## 3. Direction 2: a common entry path

### 3.1 What Linux and seL4 show

Linux's generic entry is C that runs after the architecture's assembly: `kernel/entry/common.c` (205 lines), `syscall-common.c` (30), `syscall_user_dispatch.c` (198), `virt.c` (46), with `include/linux/entry-common.h` (348) and `irq-entry-common.h` (632). It does the bookkeeping on entry and the work loop before the return to user mode (`common.c:42-205`). x86, RISC-V and LoongArch select `GENERIC_ENTRY` (`arch/x86/Kconfig:175`, `arch/riscv/Kconfig:115`, `arch/loongarch/Kconfig:98`); ARM64 selects only `GENERIC_IRQ_ENTRY` (`arch/arm64/Kconfig:134`). The assembly stays: `arch/x86/entry/entry_64.S` is 1,576 lines (plus 152 for FRED), `arch/arm64/kernel/entry.S` 1,094, `arch/riscv/kernel/entry.S` 514.

seL4's trap files are smaller, because its kernel has one stack per core and saves user registers into the thread's block: `src/arch/x86/64/traps.S` 756 lines, `src/arch/arm/64/traps.S` 263, `src/arch/riscv/traps.S` 147. On ARM64 the per-core pointer is in `TPIDR_EL1`, or `TPIDR_EL2` when the kernel runs at EL2 (`traps.S:18-34`); on RISC-V in `sscratch` (`traps.S:27-33`); on x86-64 the hardware pushes the interrupt frame where the TSS points, and `swapgs` gives the per-core block (`traps.S:14-60`).

### 3.2 What stays in assembly on each architecture, and why

DodOS has no kernel stack per thread (rule 5) and a code page that is the only legal origin of a call (rule 6). The stub's work is therefore the same in kind on every architecture: find the per-core block without a free register, save the user registers into the current thread's save area, switch to the core's kernel stack, call one common function with the kind of event, and on return restore and leave.

| Architecture | What must be assembly | Why it cannot be Rust |
|---|---|---|
| x86-64 | The `syscall` entry (the instruction does not switch stack: `swapgs`, then load the core's stack before any push); one stub per IDT vector that pushes a uniform frame (some exceptions push an error code, others not); the NMI and machine-check stubs with their own IST stacks, and the gate's window rule of kernel.md (an event inside the gate closes the window first); the return by `sysret` or `iretq` with the checks on the restored state; CET shadow-stack switching on entry and exit | No register is free at entry, the stack is the user's until switched, and the frame layout is the hardware's |
| ARM64 | The vector table (16 entries of 128 bytes each: seL4 `traps.S:36-40`, `75-95`; its 2 KB alignment is the architecture's rule, **not verified** here); saving x0 to x30, `SP_EL0`, `ELR` and `SPSR` into the save area; `ERET`. At EL2 with VHE the same code, the `_EL1` names redirected to the EL2 registers (Limine PROTOCOL.md "EL2 entry" states this redirection) | The vector layout and the register save are fixed by the hardware |
| RISC-V | The `stvec` handler: swap `sscratch` with a register to reach the core's block, save the 31 registers and `sepc`, `sstatus`, `scause`, `stval`; `sret` | The same |

Everything after the call is common Rust: decode the event (call, fault, interrupt, other core), check that a call came from the code page (one comparison of the saved instruction pointer with the code page's range), dispatch, choose what runs next, and return the thread to restore. The register calls and the fault message read the save area through one per-architecture table of offsets (`REGS_WORDS` 26 in `abi/`), so they are common too.

### 3.3 Cost

The common function is a direct call from the stub: one call and one return per event, no indirect branch, no table lookup beyond the event kind. The fast path of IPC stays where the contract puts it (Zig in the language split estimate, checked against the slow path); a common entry does not add a step to it if the stub branches to the fast path before the common call, as seL4 does (`include/arch/*/fastpath`). **Not measured.**

### 3.4 What the contract must say, and what stays open

Rule, in [Architectures](../../architecture/kernel-interface.md#architectures): "The entry of each architecture is a stub that finds the core's block, saves the user registers into the current thread's save area in the layout of `abi/`, switches to the core's stack and calls the common kernel with the kind of event; the return restores from the save area. Nothing else is architecture code on the path of an event, except the fast path of IPC and the gate's window rule."

Open point: whether the stub is Zig or assembly files (the language split puts "entry and exit" in Zig; the content is the same).

## 4. Direction 3: registers and the binary check from the specifications

### 4.1 Arm: AARCHMRS

**What the open package is.** Arm publishes the Architecture Machine Readable Specification in two forms: a proprietary one and one under the BSD licence. The open one was read from a mirror kept on kernel.org by a Linux maintainer, `kernel.googlesource.com/pub/scm/linux/kernel/git/maz/AARCHMRS`, whose last commit is titled `AARCHMRS_OPENSOURCE_A_profile_FAT-2026-09`. Its README says: "This package contains a subset of the information provided in the packages with Arm proprietary licenses. Content that is not currently in a machine-readable format, as well as all descriptive content, is omitted" (README.md, "Introduction"). It holds `Features.json` (1.3 MB), `Instructions.json` (117 MB, A64, A32, T32), `Registers.json` (97 MB, "the AArch32, AArch64, and MemoryMapped System Registers and System instructions"), and the JSON schema. The metadata of `Registers.json` says "This document is Non-confidential and licensed under the BSD 3-clause license", architecture `vFATAp2-A`, reference `2026-09_rel`, schema 2.9.6. The licence text in `docs/notice.html` is the three-clause BSD licence, "Copyright 2010-2026 Arm Limited or its affiliates". Whether this mirror is byte for byte Arm's download was **not verified**: Arm's download page was not reached; the mirror's contents carry Arm's licence and metadata.

**What it contains, counted** (a script over `Registers.json`, part 11):

- 1,830 records: 966 AArch64 registers and register arrays (891 and 75), 338 AArch32, 518 external (memory-mapped), 8 register blocks.
- Every AArch64 record has its name, the feature condition under which it exists (an expression tree such as `IsFeatureImplemented(FEAT_AA64)`), its fields with bit ranges, and its accessors: the instruction that reaches it (`MRS`, `MSR`, `TLBI`, `DC`, `AT`, `GIC`...) with the encoding (`op0`, `op1`, `CRn`, `CRm`, `op2`), and the access rule as an expression tree (which exception level may access it, which trap applies, when it is undefined).
- 598 distinct encodings are written by `MSR` or `MSRR` (register arrays such as `DBGBCR<n>_EL1` counted once), by name suffix: 185 `_EL1`, 163 `_EL2`, 63 `_EL12`, 61 `_EL3`, 60 `_EL0`, 6 `_EL02`, 60 without suffix.
- 13 `MSR` immediate targets: `ALLINT`, `DAIFClr`, `DAIFSet`, `DIT`, `PAN`, `PM`, `SPSel`, `SSBS`, `SVCRSM`, `SVCRSMZA`, `SVCRZA`, `TCO`, `UAO`. Three of them (`SVCRSM`, `SVCRSMZA`, `SVCRZA`, the `SMSTART` and `SMSTOP` forms) change the streaming vector state of SME, which D-118 ties to the vector length; kernel.md's ARM64 list names `ZCR_EL1` and `SMCR_EL1` but not these immediates.
- System instructions: 166 `TLBI`, 120 `TLBIP`, 54 `PLBI`, 40 `DC`, 25 `GIC`, 17 `AT`, 3 `IC`, and others.
- The memory-mapped part includes the GIC: 47 `GICD`, 54 `GICR`, 22 `GITS`, 16 `GICC` records, and the generic timer frames. It has no SMMU record.

**What it leaves out.** Every `purpose` and `title` field is empty (0 of 966 AArch64 records have one), and no record has a `groups` value: the meaning of a register is not in the package. Implementation-defined registers are by definition absent.

### 4.2 RISC-V: the unified database

`riscv-software-src/riscv-unified-db` (commit `d583fec`, 13 November 2026) keeps one YAML file per CSR. The CSR files carry `SPDX-License-Identifier: BSD-3-Clause-Clear` (for example `spec/std/isa/csr/satp.yaml:1-2`), and `REUSE.toml` gives the same licence for the tool code. Each file has the address, `priv_mode`, `writable`, the fields with locations for RV32 and RV64, the defining extension, and the write behaviour in its own language (`sw_write`, `satp.yaml:43-60`). Counted: 417 CSR records under `spec/std/isa/csr` with an address; 343 marked `writable: true`; by mode, 259 M, 77 U, 58 S, 19 VS, 4 D.

Coverage of what DodOS needs: `satp`, `stvec`, `senvcfg`, `ssp`, `stimecmp` (Sstc), `siselect` and `sireg` (Smcsrind), `sstateen0`, `hgatp`, `hedeleg`, `vstart`, `vl`, `vtype`, `scontext` are present. **`stopei` of the AIA (Ssaia) is absent**, although `spec/std/isa/ext/Ssaia.yaml` exists; and the registers of the IMSIC reached through `siselect`/`sireg` (`eidelivery`, `eithreshold`, `eip`, `eie`) were not found as CSR records. The database is a project of RISC-V International's software organisation, not the ratified specification itself; where it and the ratified text disagree the text wins (whether any disagreement exists was **not verified**).

### 4.3 x86-64: nothing equivalent from Intel or AMD, and what exists instead

No machine-readable register database from Intel or AMD was found: neither vendor's documentation pages nor a search turned one up. An absence cannot be proved; this is **not verified** beyond that search. What exists:

| Source | What | Licence | State |
|---|---|---|---|
| Linux `arch/x86/include/asm/msr-index.h` | 714 `#define MSR_` lines, 1,322 lines | GPL-2.0 (SPDX line 1) | maintained (v7.3) |
| Xen `xen/arch/x86/include/asm/msr-index.h` | 412 `#define MSR_` lines, 727 lines | the file has no SPDX line; Xen is GPL-2.0 (**not verified** in the file) | maintained (commit `97bf370`, 12 November 2026) |
| `x86` crate (`gz/rust-x86`), `src/msr.rs` | 1,066 `pub const`, 3,199 lines | MIT (`Cargo.toml:32`) | version 0.52.0; last commit 24 November 2023 |
| **Intel XED** (`intelxed/xed`) | the instruction encoder and decoder, with machine-readable data files per instruction set extension, each instruction carrying attributes, among them `RING0` | Apache-2.0 | commit `0bcb623`, 24 August 2026 |

The x86-64 binary check is about instructions more than registers: `WRMSR` takes the register's index in `ECX` at run time, so the scan cannot know which MSR it writes, and kernel.md already forbids `WRMSR` outside the gate. **XED is the machine-readable source for that list.** Its data files mark 69 instruction classes `RING0`: `CLAC CLRSSBSY CLTS ENCLS ENQCMDS ERETS ERETU HLT HRESET INVD INVEPT INVLPG INVLPGA INVLPGB INVPCID INVVPID LGDT LIDT LKGS LLDT LMSW LOADIWKEY LTR MONITOR MOV_CR MOV_DR MWAIT PBNDKB PCONFIG PSMASH PVALIDATE RDMSR RDMSRLIST RMPADJUST RMPUPDATE SEAMCALL SEAMOPS SEAMRET SETSSBSY STAC SWAPGS SYSEXIT SYSRET SYSRET64 SYSRET_AMD TDCALL TLBSYNC VMCALL VMCLEAR VMLAUNCH VMPTRLD VMPTRST VMREAD VMRESUME VMWRITE VMXOFF VMXON WBINVD WBNOINVD WRMSR WRMSRLIST WRMSRNS WRUSSD WRUSSQ XRSTORS XRSTORS64 XSAVES XSAVES64 XSETBV`. Against kernel.md's x86-64 list, these are not named there: **`WRMSRNS` and `WRMSRLIST`** (other ways to write an MSR); the MSR forms with an immediate index (XED's `datafiles/msr-imm`); **`LMSW` and `CLTS`** (writes to CR0 by other opcodes than `MOV CR0`); **`XSETBV`** (writes XCR0, which sets the vector state features: the x86-64 counterpart of `ZCR_EL1` under D-118); **`INVLPGB` and `TLBSYNC`** (AMD's broadcast invalidation, which acts on other cores' TLBs); **`ERETS`, `ERETU`, `LKGS`** (FRED, deferred, but the scan must still refuse them); `LOADIWKEY`, the SEAM and TDX calls, the SEV-SNP instructions (`PVALIDATE`, `RMPADJUST`, `RMPUPDATE`, `PSMASH`), `HRESET`, `SETSSBSY` and `CLRSSBSY`. Whether each is harmful is the classification's work; that the hand list does not name them is the finding the sixth review predicted.

### 4.4 The rule: every encoding classified once

Generate two things from the specification of each architecture, and hand-write one:

1. **The register accessors** (ARM64 from `Registers.json`, RISC-V from the database, x86-64 by hand for the few registers the kernel uses: CR0, CR3, CR4, XCR0 and about thirty MSRs), with typed fields.
2. **The scan lists** of G11, from the encodings.
3. **By hand: a classification file**, one line per encoding of the specification (ARM64: each writable register encoding, each `MSR` immediate, each system instruction; RISC-V: each writable CSR at S or HS level; x86-64: each XED instruction class marked `RING0` and each class that writes a system register), with one of these classes:

| Class | Meaning | Scan |
|---|---|---|
| `gate` | changes translation, interrupt routing, debug state, vector length or reaches firmware | allowed only in the gate and the start-up code |
| `kernel` | used by the kernel, harmless to other nodes | allowed |
| `unreachable` | traps or is undefined at the kernel's level (an `_EL3` register, an M-mode CSR) | refused anyway; listed so that a later change of level is noticed |
| `unused` | not used by the kernel | refused |

The build reads the specification of the pinned release and the classification, and **fails when an encoding of the specification has no line**, and when an encoding the scan finds in the binary is neither in the specification nor in the classification. Encodings outside the specification (ARM64's implementation-defined space, unallocated encodings) are refused by default, as kernel.md already says. So a new release of the specification fails the build until each new encoding is classified, which is a review of a few lines, not a hunt. Pinning: the release of each specification is a build input with its hash.

**What the specifications cannot tell, said plainly.** They give the encodings, the fields, the feature conditions and, for Arm, the access rule. They do not say whether writing a register changes translation, routes an interrupt, arms a watchpoint or changes the vector length: that is the classification, by people, from the descriptive text of the manuals, which the open Arm package omits. They do not list implementation-defined registers. They do not cover stores to memory-mapped regions (the RISC-V ACLINT and IMSIC, which kernel.md already maps only in the gate's view). Arm's access rules could be evaluated to mark automatically what is writable at EL1, or at EL2 with VHE; this was **not done** here.

### 4.5 Barrelfish's description tools

Velosiraptor's authors come from Barrelfish (`BarrelfishOS/barrelfish`, MIT, last commit 20 March 2020). Barrelfish described hardware with three tools: **Mackerel**, a language for device registers from which C accessors are generated (92 `.dev` files in `devices/`, hand-written from the manuals, such as `devices/xapic.dev`, "Numbers in comments refer to the Intel Software Development Manual"); **Sockeye**, a language for the address decoding of a system on chip (`socs/*.soc`); **Hake**, the build system. Mackerel and Sockeye together are about 10,500 lines of Haskell (`tools/mackerel`, `tools/sockeye`).

Not worth taking. Mackerel moves the hand work into another language; the vendor data of 4.1 and 4.2 replace it for system registers, and the GIC is in Arm's data. The memory-mapped units DodOS drives on x86-64 (local APIC, IOAPIC, VT-d) have no vendor data and few registers; typed Rust structures written from the manuals cost less than a tool in Haskell that nobody maintains. Sockeye answers a question DodOS leaves to user space (the platform service reads the firmware tables; the kernel reads only the MADT and the DMAR, D-112). The idea worth keeping is Mackerel's: one description, accessors generated, no register offset written twice.

### 4.6 What the contract must say, and what stays open

Rule, in G11 and kernel.md: "The scan lists and the system register accessors are generated from the pinned release of each architecture's machine-readable specification (ARM64: Arm's AARCHMRS; RISC-V: the unified database, checked against the ratified text; x86-64: Intel XED's instruction data). Every encoding of the specification is classified once, as `gate`, `kernel`, `unreachable` or `unused`; the build fails on an unclassified encoding, and on an encoding in the binary that is neither in the specification nor classified."

Open points: (1) RISC-V CSRs missing from the database (`stopei`, the IMSIC's indirect registers): add them to the classification by hand from the AIA text, or contribute them upstream; (2) whether a vendor's own data for x86-64 appears (none found).

## 5. Direction 4: the hand-over, a DodOS stub, and a kernel that knows no firmware standard

The question became wider in two steps. The owner first asked whether the loader could simply be a UEFI stub (the contract's loader already is one: "the part of the single signed EFI image that runs before the kernel", Start-up state). The owner then asked that the kernel not depend on UEFI at all. This part answers in that order: the neutral hand-over (5.1, 5.2), the sentences of the contract that change (5.3), each first stage (5.4), the crash record without a variable store (5.5), Limine judged against the stub (5.6), and the facts on who governs the firmware standards (5.7).

### 5.1 The principle

All the UEFI knowledge lives in the first stage. The kernel receives one **hand-over block** whose words name no firmware standard. The DodOS UEFI stub is the first first stage; a U-Boot or device-tree boot, a UBIOS loader, Limine for bring-up and a phone's boot chain are others, each a small program that produces the same block. This costs nothing at run time: the block is read once per machine start.

### 5.2 The neutral hand-over

The block is a header and typed entries, little-endian, like the start-up page. One register at entry holds its physical address (x86-64 `rdi`, ARM64 `x0`, RISC-V `a0`, as Linux's ARM64 and RISC-V entries take the device tree in `x0` and `a1`: `Documentation/arch/arm64/booting.rst`, `Documentation/arch/riscv/boot.rst`).

| Entry | Content | Replaces in the contract |
|---|---|---|
| Memory ranges | base, length, DodOS type: `usable` (ordinary memory the kernel may take), `kept-by-stage` (the image, modules, crash areas, already placed), `firmware` (reserved, runtime firmware, ACPI tables and NVS: never ordinary, may be device memory), `unusable` (faulty, never mapped), `device` (MMIO the stage knows) | "the UEFI memory map after `ExitBootServices`"; "the UEFI types loader code and data, boot services code and data, and conventional memory"; "the UEFI type unusable memory"; entry `UefiMemoryMap` |
| Firmware tables | a list of (kind, physical address, length): kind 1 ACPI root pointer, 2 device tree blob, 3 UBIOS root table, 4 SMBIOS entry point, others reserved | "the ACPI root pointer ... or the physical address of the device tree"; entry `AcpiRoot` |
| Crash areas | bases and lengths of the current and previous area, the previous sequence, and a flag "the stage can keep these addresses across a reset" | "addresses recorded in one non-volatile UEFI variable"; "a machine without a UEFI variable store" |
| Entropy seed | 64 bytes, and the stage's statement of its source (hardware, firmware service, none) | unchanged in substance |
| Times | the counter frequency, then pairs (stage event, counter value): stage entry, end of firmware services, kernel entry | "the counter at entry to the loader, at `ExitBootServices`" |
| Framebuffer, modules, boot image records, first service | as today | unchanged |
| Origin | the kind of first stage (UEFI stub, device tree, UBIOS, Limine, other) and its version, for the crash record and the boot gates only; the kernel's behaviour never depends on it | new |

**Machine state at entry, per architecture.** x86-64: 64-bit mode with an identity map of the block, the kernel image and the modules (long mode cannot run with paging off), interrupts masked. ARM64: MMU off, at EL2 if the stage runs at EL2, else EL1 (D-124 point 7 wants EL2 with VHE where it exists; the kernel sets VHE itself), as Linux's ARM64 boot protocol requires ("The MMU must be off", `booting.rst:179`). RISC-V: S-mode, `satp` = 0, as Linux's ("`$satp = 0`: the MMU, if present, must be disabled", `riscv/boot.rst:34`). An MMU-off entry on ARM64 and RISC-V lets the kernel choose its granule (D-121) without a trampoline.

### 5.3 The sentences of the contract that change

Every place where the contract names UEFI, `ExitBootServices` or the signed EFI image, from `grep` on [kernel-interface.md](../../architecture/kernel-interface.md) at commit `3bc7597`:

| Line | Today | Proposed |
|---|---|---|
| 894 (G10) | "the kernel never calls the UEFI runtime services" | "the kernel never calls firmware runtime services" (unchanged in effect) |
| 1253 | "The loader keeps two crash areas, A and B" | "The first stage keeps two crash areas" |
| 1335, 1717 | "the loader's seed" | "the first stage's seed" |
| 1338 | "The loader and the kernel are one signed image, so this is part of the contract" | "Every first stage keeps the crash areas by the rule below, so this is part of the contract" |
| 1340 | "The loader keeps the two crash areas at addresses recorded in one non-volatile UEFI variable" | "The first stage keeps the two crash areas at the same physical addresses from one boot to the next, by a means of its own (5.5)" |
| 1342 | "The loader hands over the bases and lengths of both" | "The first stage hands over" |
| 1346 | "or the UEFI variable store at failure time" | "or a firmware variable store at failure time" |
| 1347 | "or a machine without a UEFI variable store" | "or a first stage that cannot keep the addresses" |
| 1419, 1637 | "the loader hands no seed" | "the first stage hands no seed" |
| 1615 | "What the loader hands over. The loader is the part of the single signed EFI image that runs before the kernel" | "What the first stage hands over. The first stage is the program that runs before the kernel and builds the hand-over block; on a UEFI machine it is the DodOS stub, part of the single signed image" |
| 1617 | "the UEFI memory map after `ExitBootServices`" | "the memory ranges, with DodOS's types" |
| 1618 | the ACPI root pointer or the device tree | "the firmware tables, each with its kind" |
| 1621 | "the boot time stamps" | unchanged |
| 1624, 1629, 1657 | "the loader has already filled in", "The loader lays out the modules", "the loader has zeroed" | "the first stage" |
| 1638 | "the one the signed image carries" | "the one the boot image carries, checked by the first stage's verification" (secure boot stays a property of the first stage: 5.6) |
| 1655 | "the RAM that is usable after `ExitBootServices`: the UEFI types loader code and data, boot services code and data, and conventional memory" | "the ranges of type `usable`" |
| 1658 | "no byte of the UEFI type unusable memory ... the runtime services of UEFI" | "no byte of a range of type `unusable` ... the ranges of type `firmware`" |
| 1714 | entry 3 `AcpiRoot` | entry `FirmwareTables`: (kind, address, length) records |
| 1715 | entry 4 `UefiMemoryMap` "the descriptors as UEFI gave them" | entry `MemoryRanges`, DodOS's records; the stage's raw map, if the platform service wants it, as a module |
| 1718 | entry 7 `BootTimes` "at `ExitBootServices`" | the counter frequency and (event, counter) pairs |

`abi/` changes with the last three rows (`StartEntry` kinds 3, 4, 7, and `START_MAGIC` version); that change is the owners' to approve. Outside the contract, [security.md](../../architecture/security.md#secure-boot) ("A single signed EFI image") stays true for UEFI machines and needs one sentence for the others (5.6), and D-046 (A/B through UEFI boot variables) stays as decided for UEFI machines; on another first stage the A/B choice is that stage's own mechanism, a rule to add, not a reopening.

### 5.4 Each first stage

**(a) A Rust UEFI stub: how much is common.** Linux's stub was measured as the best evidence of the split (`drivers/firmware/efi/libstub`, 8,497 lines at v7.3). Its Makefile builds a common library for every architecture (`lib-y`: helpers, GOP, secure boot, TPM, file, memory, random, allocation, PCI, printing: 3,310 lines, plus the header `efistub.h`, 1,263), a "generic stub" for the architectures that boot from a device tree (`EFI_GENERIC_STUB`: 711 lines; `fdt.c`, 379; selected by ARM64 and RISC-V: `arch/arm64/Kconfig:2562-2565`, `arch/riscv/Kconfig:1281-1284`), and per architecture: ARM64 202 lines (`arm64.c`, `arm64-stub.c`) plus a PE/COFF header of 181 (`arch/arm64/kernel/efi-header.S`); RISC-V 156 plus a header of 124 (`arch/riscv/kernel/efi-header.S`); x86 1,183 (`x86-stub.c`, `x86-stub.h`, `x86-5lvl.c`) plus `arch/x86/boot/header.S` (619). So 94 % of what an ARM64 Linux image's stub uses is shared, 95 % for RISC-V, and 72 % for x86, whose share is large because of Linux's legacy `boot_params` protocol and its five-level trampoline, which a DodOS stub does not have. A DodOS stub does less than Linux's (no command line, no initrd, no KASLR, no compressed image): it loads nothing (the image is one signed file), reads the memory map, the configuration tables (ACPI, device tree, SMBIOS), the RNG protocol, the GOP framebuffer, the crash-area variable, calls `ExitBootServices`, builds the block and jumps. **Estimate**, not measured: 1,500 to 2,500 common lines, 100 to 300 per architecture (the entry state of 5.2 and the PE header where needed).

**(b) Rust UEFI targets.** rustc has `x86_64-unknown-uefi`, `aarch64-unknown-uefi` and `i686-unknown-uefi` (`compiler/rustc_target/src/spec/targets/`, and `src/doc/rustc/src/platform-support/unknown-uefi.md:10-12`, at rust commit `5f4effd`, 13 November 2026). **There is no `riscv64` UEFI target.** What a RISC-V stub needs instead is what Linux and Limine do: build an ELF for `riscv64gc-unknown-none-elf`, put a hand-made PE/COFF header at the start of the image (Linux: `arch/riscv/kernel/efi-header.S:11-20`, machine `IMAGE_FILE_MACHINE_RISCV64`, "Adapted from arch/arm64/kernel/efi-header.S"), and turn the ELF into a raw binary (Limine: `objcopy -O binary` to `BOOTRISCV64.EFI`, `common/common.mk:401-403`; its PE header is in its `picoefi` submodule, not checked out here, **not verified**). About 120 lines of assembly and a linker script; the stub's Rust is the same.

**(c) U-Boot's UEFI (EBBR).** EBBR requires `SetVariable` before `ExitBootServices` and makes it optional after (`source/chapter2-uefi.rst:525-565`, the table of runtime services: `SetVariable` "Required" before, "Optional" after). It says so because "the firmware cannot access storage after `ExitBootServices()`" on many platforms (`chapter2-uefi.rst:625-656`). The contract's loader writes its variable before `ExitBootServices`, and only when it must place an area again (contract line 1340), so **EBBR does not stop it**. Whether the write persists depends on U-Boot's configuration: non-volatile variables go to the file `/ubootefi.var` on the EFI system partition, to SPI flash, or through OP-TEE (`lib/efi_loader/Kconfig:121-162`, U-Boot commit `6487c50`), unless the board chose `EFI_VARIABLE_NO_STORE`, "non-volatile variables cannot be persisted" (`Kconfig:164-170`). Fallback when the variable does not persist: the stub reads it back after writing; if it did not stick, it writes the two addresses to a file of its own on the EFI system partition (boot services include file writes), and if that fails too it sets "cannot keep" in the hand-over and the record of the current boot is the only one (contract line 1347, already the rule).

**(d) No UEFI.** On many ARM64 and RISC-V boards and on phones, the previous stage loads a kernel image and a device tree and jumps (Linux's ARM64 and RISC-V boot protocols, cited in 5.2). A DodOS first stage there is a small program, entered by that protocol, that reads the device tree's `/memory` and `/reserved-memory` nodes, its `/chosen` node, and builds the block. Linux's own stub shows the conversion in the other direction: it places the UEFI memory map into the device tree as `linux,uefi-mmap-start`, `linux,uefi-mmap-size` and related properties, and a seed as `kaslr-seed` (`drivers/firmware/efi/libstub/fdt.c:99-129`), so that one kernel entry serves both paths. That is the same idea as the neutral hand-over, with the device tree as the carrier. A Limine first stage is the same kind of program: a Limine-protocol executable that converts Limine's responses into the block. A UBIOS first stage converts UBIOS's memory map and table references (5.7).

**This is where a neutral entry protocol pays**: one entry for the kernel, several small converters outside it. The Limine protocol is not that protocol, because it carries UEFI-shaped features (the EFI memory map, the EFI system table) and a higher-half direct map, and because the kernel must not depend on a loader project's revision for its own entry.

### 5.5 Keeping the crash record without a variable store

What every first stage must be able to do, for the previous area to survive a complete stop:

1. place two ranges at the **same physical addresses** at every boot, and never let the firmware or the stage clear them;
2. know those addresses at the next boot without the kernel's help;
3. survive a warm reset of the machine with memory kept (already an open point of the contract, "whether memory survives the warm reset").

The means per first stage: on UEFI, the variable, then the file fallback of 5.4 (c); on a device-tree boot, a `reserved-memory` node at a fixed address in the board's device tree, which is how Linux's ramoops keeps its panic log across a reset ("Use Device Tree bindings, as described in `Documentation/devicetree/bindings/reserved-memory/ramoops.yaml`", `Documentation/admin-guide/ramoops.rst:62-74`); on UBIOS, a range of its memory map that the stage marks reserved at a fixed address (whether UBIOS keeps a range across a reset is **not verified**); on a phone, the same `reserved-memory` node, if the boot chain lets the image carry its device tree. A stage that can do none of these sets "cannot keep", and the rule of line 1347 applies.

### 5.6 Limine, judged against the DodOS stub

Limine protocol at commit `877c2d4` (14 November 2026), base revision 6; Limine at commit `033b597`, BSD two-clause licence (`COPYING`).

| Point of the contract | Limine | DodOS stub |
|---|---|---|
| Crash areas at addresses kept in a firmware variable (lines 1338-1343) | no feature | yes (5.4 c, 5.5) |
| Entropy seed (D-057) | yes: Entropy feature, best effort, "no guarantee of hardware-grade entropy" (PROTOCOL.md:2146-2190) | yes: `EFI_RNG_PROTOCOL` where present, statement of source |
| Boot times | Bootloader Performance feature in microseconds from "an arbitrary point in the past" (`:1939-1980`) and the TSC frequency feature (`:2016`) | counter values at each event |
| First service's segments loaded, tail zeroed | no: modules are files loaded as they are (`:1593-1670`) | yes |
| Modules aligned on large pages | no: "always at least 4KiB aligned" (`:2219`) | yes |
| Memory map | its own types, and the EFI memory map as a feature (`:1414`, `:1809-1847`) | DodOS types |
| Entry state, ARM64 | EL2 with VHE when the loader is at EL2 and VHE exists, else EL1, never EL2 without VHE (`:321-334`, `:588-593`): matches D-124 point 7; MMU on with a 4 KB granule (`:611`) | MMU off, EL2 or EL1 |
| Entry state, address space | executable in the higher half at or above `0xffffffff80000000`, plus a direct map of memory (`:338-415`) | identity map (x86-64) or MMU off |
| Other cores | MP feature: the loader starts the other cores and parks them in its own memory until a write to `goto_address` (`:1133-1230`) | the kernel starts every core itself (machine start-up step 4, `core_start`, G10) |
| Secure boot (security.md: one signed image) | Limine is its own EFI program, signed separately; under Secure Boot, if a BLAKE2b hash of its configuration is enrolled into the Limine binary, the configuration is checked on every boot and every file path must carry a BLAKE2b hash or Limine stops (USAGE.md:28-56, CONFIG.md:448-456); without an enrolled hash, Limine "treats Secure Boot as inactive" | the stub, the kernel and the boot image are one PE file signed once |
| Code in the boot chain | `common/` alone is 37,937 lines (C, headers and assembly: filesystems, BIOS paths, other protocols, menu, image decoding) | estimate 2,000 to 3,000 lines |

On each of the four frictions of the brief:

- **Loader duties Limine lacks**: five of the six (crash areas, segments loaded, large-page alignment, DodOS memory types, counter-based times). The entropy feature exists. A DodOS converter after Limine can do the layout work (copy segments, realign modules) at the cost of a second copy of the image, but not the crash areas.
- **Secure boot**: Limine's chain (signed Limine binary → enrolled configuration hash → BLAKE2b of each file) is a sound chain of hashes, but it is two artefacts, not the single signed image of security.md, and its trusted base adds Limine's code. The kernel's check of the kept image's SHA-256 would compare with a hash carried by the kernel binary, which Limine's BLAKE2b covers; workable, weaker in simplicity.
- **ARM64 granule.** Limine enters with 4 KB tables on both roots. To take 16 KB (D-121), the kernel must build its 16 KB tables, run from an identity-mapped page, turn the MMU off, set `TCR_EL1.TG0`, `TG1` and the roots, invalidate, and turn it back on: the technique Linux uses to turn its MMU off for kexec (`arch/arm64/kernel/cpu-reset.S`, not opened here, **not verified**). Its cost is once per core start, microseconds (**not measured**); its risk is code that runs with the MMU off in the middle of start-up. Whether the Arm ARM allows changing the granule with the MMU on was **not verified**. With an MMU-off entry (the stub) the question does not arise.
- **Starting the other cores**: the MP feature is of no use and should not be requested. The kernel starts and restarts cores itself, with INIT and SIPI, PSCI `CPU_ON` or SBI `hart_start`, from its own park stub, and the fence relies on the kernel knowing what each core runs. Without the request Limine starts no other core (`:1161-1163`).

Comparison of the three options of the brief, with the neutral hand-over:

| Option | For | Against | Verdict |
|---|---|---|---|
| Limine as the loader | exists, five architectures, maintained | five missing duties, two signed artefacts, 4 KB granule on ARM64, the kernel's entry follows a third party's revisions | no |
| Limine's protocol as the entry contract, DodOS's loader for the product, Limine for bring-up | one entry for two loaders | the protocol's UEFI-shaped features and direct map enter the kernel's contract; the product loader must emulate a protocol designed for another purpose | no |
| Own hand-over (today's contract) | fits every duty | names UEFI in the kernel's contract | becomes the next row |
| **Own neutral hand-over; the DodOS UEFI stub as first first stage; converters for device-tree boot, UBIOS and Limine** | one signed image on UEFI machines; no firmware word in the kernel; Limine usable for bring-up behind a small converter | the converters are DodOS's to write (each a few hundred lines, **estimate**) | **recommended** |

### 5.7 Who governs the firmware standards

- **The UEFI Forum's board.** The board page of uefi.org (read from the Internet Archive's copy of 1 January 2026, `web.archive.org/web/20260101224308/https://uefi.org/board`, because uefi.org refused automated access) lists twelve members: Intel (president), Arm (vice-president), Lenovo (treasurer), Phoenix Technologies (secretary), AMD, American Megatrends, Apple, Dell, Hewlett Packard Enterprise, HP Inc., Insyde Software and Microsoft. Microsoft holds one seat of twelve. The current page and the full promoter list were **not verified** at uefi.org itself.
- **Microsoft's real hold is the keys, not the specification.** Microsoft's support article KB 5062710 (`support.microsoft.com/help/5062710`) says that "since Windows introduced Secure Boot support, all Windows-based devices have carried the same set of Microsoft certificates in the KEK and DB"; the Platform Key is "typically owned by the hardware manufacturer"; "any entity with a KEK can update the DB and DBX". The certificates are: Microsoft Corporation KEK CA 2011 (replaced by KEK 2K CA 2023), Microsoft Windows Production PCA 2011 (replaced by Windows UEFI CA 2023), and Microsoft UEFI CA 2011, which "signs third-party boot loaders and EFI applications" and is split into Microsoft UEFI CA 2023 and Microsoft Option ROM UEFI CA 2023. The 2011 certificates "begin expiring in June 2026". So on a machine that ships with Microsoft's keys only, a non-Windows loader boots under Secure Boot only if Microsoft's third-party CA signed it, or if the owner enrols other keys; security.md already plans the second (the user enrols the project's key or their own) and the first "later". Neither depends on the UEFI specification's text.
- **UBIOS.** The standard is public: the Global Computing Consortium's page `www.gccorg.com/article/69/426.html` links a 64-page PDF, "GCC-3007-2025 统一基本输入输出系统（UBIOS）基础架构规范" (UBIOS base architecture specification), dated 17 October 2025, downloaded and read for this draft. Its drafters are the China Electronics Standardization Institute, Huawei and eleven others (as listed by IT之家 at `view.inews.qq.com/a/20251021A07EJQ00`). What the text itself says: it is "loosely coupled to the chip architecture and can be applied to different processor architectures, including ARM, RISC-V and others" (section 5, note b; x86 and LoongArch are not named); data is little-endian and addresses are system physical addresses; it defines its own memory map, records of 24 bytes (base aligned on 4 KB, size, type, reliability, hot-plug) with types Free, Data, Code, Shared, Reserved, Disabled, Device (tables 15 and 16); other tables are referenced from an `other_tables` object, whose only listed member is `dtb_address`, the physical address of a device tree blob (table 34). **The text never mentions ACPI** (a search of the extracted text finds no occurrence), nor UEFI except in comparisons. No machine shipping with UBIOS in 2026 was found (**not verified**: press articles describe the standard, not products). For DodOS, a UBIOS first stage would convert its memory map and pass the device tree: the neutral hand-over of 5.2 takes it without change.
- **RISC-V BRS.** Version 1.0, ratified 29 August 2025 (`docs.riscv.org/reference/brs/v1.0/`), defines two recipes (`recipes.html`). **BRS-I** ("Interoperable", for servers, desktops, laptops): UEFI 2.10 or later, ACPI 6.6 or later, device tree optional, SBI 2.0 or later, SMBIOS 3.7.0 or later. **BRS-B** ("Bespoke", for mobile, real-time and embedded devices): UEFI through EBBR 2.1.0 or later, ACPI or device tree ("never both at the same time"), SBI 2.0 or later. BRS-I's UEFI chapter (`uefi.html`) requires that "the non-volatile UEFI variables MUST persist across calls to the `ResetSystem()` runtime service call" (URT_040) and, with Secure Boot, at least 128 KiB of variable storage (USEC_020). So both RISC-V recipes require a UEFI interface; on standard RISC-V machines the DodOS stub is the normal path, and the neutral hand-over is insurance for boards outside BRS and for other standards.

### 5.8 What the contract must say, and what stays open

Rules, in [Start-up state](../../architecture/kernel-interface.md#start-up-state):

- "The kernel receives a **hand-over block** from a first stage. The block names no firmware standard: memory ranges with DodOS's types, kept ranges, the crash areas, the seed, the counter frequency and stage events, the framebuffer, the modules and the boot image records, and the firmware tables as (kind, address, length) records. The first stage on a UEFI machine is the DodOS stub, part of the single signed image; on other machines another first stage builds the same block. The kernel's behaviour never depends on which first stage built it."
- "Entry state: x86-64 in 64-bit mode with an identity map of the block, the image and the modules; ARM64 with the MMU off, at EL2 if the first stage ran at EL2; RISC-V in S-mode with `satp` 0. The block's address is in the first argument register."
- "A first stage keeps the two crash areas at the same physical addresses from boot to boot by a means of its own, and says in the block whether it can."

Open points, with alternatives: (1) the stub's language, Rust (recommended, one source with the UEFI targets of rustc and a hand-made header on RISC-V) or Zig (D-004 allows both); (2) the A/B choice on first stages without UEFI variables (U-Boot's boot count and environment, or a DodOS file on the boot partition); (3) whether the raw firmware memory map is also handed to the platform service, as a module (recommended) or not at all.

## 6. Direction 5: Velosiraptor

**What it is.** "Velosiraptor: Code Synthesis for Memory Translation", Reto Achermann, Em Chu, Ryan Mehri, Ilias Karimalis, Margo Seltzer, ASPLOS '25 (DOI 10.1145/3676641.3711998), posted on arXiv as 2608.07966 on 8 August 2026 (arxiv.org/abs/2608.07966). The paper is under CC BY 4.0 (its first page). The artifact is `github.com/ubc-systopia/velosiraptor-asplos25-artifact` (commit `74933d4`, 31 January 2025), which pins the tool `github.com/ubc-systopia/velosiraptor` at commit `0596b97` of branch `dev/hwgenrefactor2` (30 January 2025). The tool's `main` branch was last changed on 11 July 2024 (`150d1a8`). Licence: MIT (`LICENSE`; the paper's artifact appendix: "Code licenses?: MIT").

- **Input**: a specification in its own language (`*.vrs`) of a translation unit: its state (registers and in-memory descriptors as bit fields), its interface (the loads, stores and instructions the OS can use), and its behaviour (`translate`, `matchflags`, validity), built from "segments" composed into tables (`examples/x86_64_pagetable.vrs`, 477 lines, from Intel SDM volume 3, section 4.5).
- **Output**: C or Rust (`lib/velosicodegen/src/c`, `rust`) for three operations, `map`, `protect` and `unmap` (`lib/velosisynth/src/vmops/map.rs`, `protect.rs`, `unmap.rs`; "addmap, setperms, and delmap" in the paper's Table 1), and a simulated hardware module for Arm Fast Models (`velosihwgen`).
- **No invalidation.** The TLB is left out: "we exclude segmentation and the TLB for simplicity" (paper, 2.3.3); the only related action in the synthesiser is a write-buffer flush, `GlobalBarrier` (`lib/velosisynth/src/programs/mod.rs:582-642`).
- **Hardware evaluated**: specifications of a simple page table, x86-32 and x86-64 page tables, the Arm MPU, the Xeon Phi SMPT, four segment models, x86 segmentation and the MIPS R4700 TLB (Table 1); **no ARM64 MMU, no RISC-V, no IOMMU**. Generated x86-64 code was run in Barrelfish under QEMU, and its map, protect and unmap took 13, 12 and 11 ns at the median against 13, 13 and 12 ns for code taken from Linux 6.8 (Table 3).
- **What it proves, and how**: each candidate program is checked by the Z3 SMT solver against the specification's model, "for all possible initial states and arguments, the candidate program satisfies the goal condition for the end state" (paper, 5.3). That is a check of the synthesised sequence against the specification, done by the solver. The specification is trusted, the code generator that prints C or Rust is not verified, and there is no proof about concurrency, invalidation or several cores.

**Could its output serve the gate?** No. G1 to G14 are about who may write which entry: ownership words (G3 (2)), page classes (G2, G3 (3)), map counts (G4), grants (G6), roots and tags (G7), IOMMU context entries (G9), the bound of *E* chunks per call (G3). Velosiraptor knows a translation unit, not memory ownership, and produces no invalidation, which the contract's guarantee needs ("When a call returns ... no thread on any core can use a translation that the call removed or reduced"). Its operations are also not the contract's (the contract maps whole frames from records, never splits, and bounds each call).

**Could it be a test oracle for direction 1?** Only for x86-64, whose specification exists. For ARM64, RISC-V and the IOMMUs, someone would write the specifications first, in a language with one maintained branch and no release since January 2025. The same cross-check is cheaper inside the project: the format description of direction 1 is tested against hand-written tables of known entries from the manuals, and against the model's G3 checks in property tests.

**Recommendation: leave.** Keep the idea of one description from which code and checks are derived, which direction 1 and direction 3 already take. Revisit if the project adds ARM64 and IOMMU specifications and invalidation.

Contract: nothing to add.

## 7. Question 1: the reference model as the kernel's core

### 7.1 Measures

Over `model/src` (17,307 lines, 26 files, branch `model` at `2afc901`), with a script that strips line comments and counts occurrences per file (part 11):

| Measure | Count | Where |
|---|---|---|
| `std::` paths | 86 | every file but six; `check/tests.rs` 18, `boot.rs` 9, `lib.rs` 9, `debug.rs` 8, `system.rs` 8 |
| `Vec` or `vec!` | 291 | `boot.rs` 65, `lib.rs` 42, `remote.rs` 35, `table.rs` 33, `recovery.rs` 17, `system.rs` 16 |
| `BTreeMap` or `HashMap` | 62 | `lib.rs` 34: every object store of `Model` (`caps`, `objects`, `untypeds`, `frames`, `cspaces`, `aspaces`, `threads`, `endpoints`, `notifies`...) |
| `BTreeSet` or `HashSet` | 35 | `memory.rs`, `check/*`, `system.rs` |
| `VecDeque` | 4 | `lib.rs` |
| `Box` | 2 | `moves.rs`, `remote.rs` |
| `Arc` or `Rc` | 52 | the machine table's large parts, shared copy-on-write between nodes (`table.rs:143-175`) |
| `String`, `format!` | 2 | `system.rs` |
| `.collect`, `.to_vec()`, `.clone()` | 131 | everywhere |
| `loop` | 3 | `caps.rs`, `recovery.rs`, `system.rs` |
| `while` | 20 | `system.rs` 4, `sched.rs` 3, `check/tests.rs` 6 |
| `for` | 204 | everywhere; most iterate over a collection |
| Direct self-recursion | none found | the syntactic scan flagged seven functions; each calls a method of the same name on another type (checked by hand); mutual recursion was not searched exhaustively |

What the counts mean, file by file: allocation is in the state itself, not in a few helpers. `Model` keeps each kind of object in a `BTreeMap` keyed by identifier (`lib.rs:917-1032`); an address space keeps its translations as a `BTreeMap<u64, Translation>` and its records as a `Vec<CapId>` (`lib.rs:598-616`); a capability's children are a `Vec<CapId>` (`lib.rs:513`); messages carry `Vec<u64>` (`lib.rs:83-89`). The loops are over these collections, so their bounds are the collections' sizes.

### 7.2 Where the line between logic and machine runs today

The model's header says what it leaves out: "the contents of memory (the start-up page is sized, not written); the hardware (translations are a map; the invalidations of the TLB and of the IOMMU are done before a call returns; masking, the end of interrupt and the entropy pool are not seen); the kernel's own time" (`model/src/lib.rs:15-21`). Its inputs are events: `apply` (a call), `advance` (time), `fault`, `interrupt` (`lib.rs:5-13`). Its outputs to the machine are values: `HwAction` (`Nmi`, `Init`, `Sipi`, `Signal`, `Start`, `ParkSelf`: `recovery.rs:29-54`), `UnitOp` (`Attach`, `Detach`, `Invalidate`: `roles.rs:22-29`), and `Packet`s between nodes (`remote.rs`). `System` holds several `Model`s and delivers their packets (`system.rs:38-47`).

So the model has no machine boundary inside: it has a boundary at its edge (events in, actions out), and above it the logic works on Rust collections, not on the contract's layouts. The contract fixes layouts the model does not have: a 64-byte slot that holds a frame's record and the links of its space's list ([The capability slot](../../architecture/kernel-interface.md#the-capability-slot)), a derivation list linked through slots, a table of *E* entries per page, an interrupt table of 192 entries of 64 bytes, a grant table of fixed entries.

### 7.3 Verdict

**The model must stay a model.** To run its logic in a kernel without a heap, every `BTreeMap` would become a fixed table or a list linked through slots, every `Vec` of children a linked list, every `Vec<u64>` message a slice of the message page, and every translation map the real tables; the functions that walk them would change with them. That is not a port of the logic behind a narrow trait: it is the kernel, written again from the same contract, which is what the project's order already says ("specification, model, oracle, implementation", `dodos-kernel/AGENTS.md`). seL4's prototype in Haskell was rewritten in C for the same reason; the narrow trait does not avoid it, because the hard part is the data, not the hardware.

What the idea does buy, kept: **the model's tests can hold for every architecture**, not by sharing code but by sharing the call interface.

### 7.4 The proposal: a core behind a machine boundary, driven by the model's tests

1. The kernel's core (capabilities, objects, scheduling, IPC slow path, memory calls, the gate's checks, the inter-node protocol, recovery) is written `no_std`, with fixed tables and lists linked through objects, from the contract.
2. It talks to the machine only through a boundary of about thirty operations (below), which each architecture implements and which a **simulated machine** implements for tests, on the host.
3. The model's test suite (19,642 lines in `model/tests`, which drive the model through `apply`, `advance`, `fault`, `interrupt`, `check`: 279, 36, 19, 2 and 91 call sites) is run against the core on the simulated machine, call by call, and their results compared: the oracle harness the project already plans, run on the host at every build.
4. The same suite runs against the real kernel on each architecture under QEMU, through the code page, for what the simulated machine cannot show (the stubs, the real tables, the invalidations).

The boundary, with its contract (each operation is bounded and never allocates):

| Group | Operation | Contract |
|---|---|---|
| Tables | `write_entry(table, index, value)` | the gate's write of one entry (G1); the value was checked by the common G3 code; re-read after write where the mechanism needs it |
| | `read_entry(table, index)` | plain load |
| | `invalidate_page(tag, address)`, `invalidate_tag(tag)`, `invalidate_all()` | done on this core when it returns |
| | `load_root(table, tag)` | G7 checked by the common code |
| | `table_page_class(page, class)` | where the mechanism types the page (shadow-stack typing on x86-64) |
| IOMMU | `iommu_write_context(unit, device, root, domain)`, `iommu_clear_context(unit, device)`, `iommu_invalidate(unit, domain, range)`, `iommu_wait(unit, deadline)` | the role holder's operations; `iommu_wait` returns timed out after the bound |
| | `iommu_write_remap(index, entry)`, `iommu_invalidate_remap(unit, index)` | interrupt remapping |
| Interrupts | `irq_mask(source)`, `irq_unmask(source)`, `irq_eoi(vector)` | constant work |
| | `irq_route(source, core, vector)` | programs an IOAPIC entry, an APLIC target, an ITS mapping |
| | `send_ipi(core, kind)` with kind ordinary, fence signal, start | G10 checked by the common code |
| Cores | `core_start(core, entry)`, `core_park_self()`, `core_stop_confirmed(core)` | INIT/SIPI, PSCI, SBI; the fence steps of the contract |
| Time | `clock_now()`, `timer_set(deadline)`, `counter_frequency()` | monotonic |
| Registers | `save_user_state(thread)`, `restore_user_state(thread)`, `save_vector_state(thread, mask)`, `restore_vector_state(thread, mask)` | the save area layout of `abi/` |
| Memory | `clear(range)`, `copy(from, to, length)` | bounded by the caller's step (64 KB) |
| Entropy | `hardware_random()` | none if absent |
| Debug | `console_write(bytes)`, `breakpoint_set(thread, slot, spec)` | only if the image declares a console |

The simulated machine keeps the tables in arrays, records the invalidations, and checks after every operation what the model's invariants check (no stale translation after a call returns, G14's map counts).

**Cost.** On real hardware the boundary is static dispatch, monomorphised per architecture: an inlined call, no indirect branch on any path. Run on the host it costs nothing to the kernel.

### 7.5 What the contract must say, and what stays open

Rule, in [Architectures](../../architecture/kernel-interface.md#architectures): "The kernel's architecture-independent part reaches the machine only through the machine boundary listed in kernel.md; a simulated machine implements the same boundary on the host, and the reference model's tests are run against the kernel on it at every build, and on each architecture under QEMU."

Open point: the list of operations, to be fixed when the one-core kernel is written; the language of the core (Rust) and of the boundary's implementations (Zig or Rust per D-004).

## 8. Question 2: what stays per architecture, and how much

### 8.1 seL4

seL4 at commit `c98d70a` (9 November 2026), every file under `src` and `include`: 88,367 lines; 19,418 outside `arch`, `plat` and `drivers`; `arch/x86` 24,990, `arch/arm` 27,021, `arch/riscv` 6,446; `plat` 7,230 (of which device trees); `drivers` 3,262. The owners' figures (84,600; 19,600; 24,600; 28,100; 6,200) are close; the difference is the commit and which files are counted.

Split by part (C, headers, assembly and bit-field files of `src/arch/<a>` and `include/arch/<a>`, with `plat/pc99` for x86 and `drivers/{smmu,timer,irq}` for Arm, classified by file path with the regular expressions of the script in part 11; the classification is coarse, a file goes to its first matching part):

| Part | x86 | Arm | RISC-V |
|---|---|---|---|
| 32-bit modes (not needed by DodOS) | 4,338 | 12,721 | 319 |
| Virtualisation objects (not needed) | 3,172 | 1,705 | 0 |
| Page tables and TLB | 3,452 | 2,344 | 1,307 |
| IOMMU | 1,139 | 2,099 | 0 |
| Interrupt controllers and timers | 1,496 | 3,702 | 297 |
| Entry, traps, fast path | 2,321 | 1,104 | 712 |
| Boot and cores | 3,025 | 1,057 | 861 |
| Context, FPU, registers | 762 | 733 | 530 |
| Debug, CapDL, benchmarks | 1,796 | 2,007 | 296 |
| Objects, machine, other | 5,689 | 3,395 | 1,969 |
| **Total** | 27,190 | 30,867 | 6,291 |
| **Without 32-bit and virtualisation** | **19,680** | **16,441** | **5,972** |

The Arm interrupt row includes drivers for several boards' controllers besides the GIC (`include/drivers/irq`); the Arm IOMMU row is seL4's SMMU support, which is the older SMMU architecture (`src/drivers/smmu`), not SMMUv3 (**not verified** in detail).

### 8.2 Redox, the Rust kernel with real hardware support

Redox's kernel (`gitlab.redox-os.org/redox-os/kernel`, commit `8f0e965`, 14 November 2026, MIT) runs on x86-64, ARM64 and RISC-V; 43,230 lines of Rust in `src`. Architecture code (`src/arch/*`, `src/asm`, the per-architecture ACPI files, `rmm/src/arch`), classified the same way:

| Part | x86-64 | ARM64 | RISC-V |
|---|---|---|---|
| 32-bit x86 (not needed) | 729 | 0 | 0 |
| Board-specific (Raspberry Pi controllers, System76 EC) | 89 | 543 | 0 |
| Page tables (the `rmm` instance and glue) | 165 | 162 | 370 |
| Interrupt controllers, timers, IPIs | 1,848 | 1,192 | 687 |
| Entry, traps, system calls | 1,950 | 868 | 604 |
| Boot and cores | 1,191 | 2,461 | 209 |
| Debug | 139 | 171 | 102 |
| Other | 727 | 263 | 204 |
| **Total** | 6,838 | 5,660 | 2,176 |
| Context switch (`src/context/arch`) | 447 | 387 | 219 |

Redox has no IOMMU in its kernel and drives the interrupt controllers simply, so it is a floor, not a model.

### 8.3 Estimate for DodOS

Reasoned per part, from the two kernels and the directions above; an estimate within a factor of about 1.5, not a measure.

| Part | x86-64 | ARM64 | RISC-V | Reasoning |
|---|---|---|---|---|
| Entry stubs, context switch, vector state | 900 | 700 | 500 | 3.2; seL4 traps 756 / 263 / 147 plus the save of vector state (XSAVE, SVE and SME, V) and the shadow stacks |
| Page tables: description, invalidation, root, start-up of translation | 300 | 450 | 300 | 2.3, 2.4; Redox `rmm` instances 118 / 155 / 116-124; ARM64 adds two granules, the second root, the BBM rule |
| IOMMU (tables through the generic walker; units, queues, faults, interrupt remapping) | 1,600 | 2,000 | 1,300 | seL4 VT-d 1,139 without interrupt remapping; SMMUv3 command and event queues, stream tables; RISC-V IOMMU queues, similar in kind (no seL4 code to compare: **not measured**) |
| Interrupt controllers and timer | 1,200 | 1,500 | 1,000 | x2APIC, IOAPIC, TSC deadline (seL4 1,496, Redox 1,848); GICv3 and ITS (seL4 GICv3 1,054 lines in `gic_v3.c` and `gic_v3.h`) and the generic timer; IMSIC, APLIC, Sstc (Redox's PLIC 687) |
| Starting, parking and fencing cores | 600 | 600 | 350 | INIT/SIPI, park stub, NMI handler; PSCI and SDEI; SBI HSM and the DodOS stop extension |
| The gate's mechanism | 400 | 400 | 300 | kernel.md: shadow-stack typing or a gate root on x86-64; a gate context on ARM64 and RISC-V; window entry stubs |
| Firmware tables the kernel reads | 600 | 800 | 700 | MADT and DMAR; MADT and GICC or the device tree; RHCT or the device tree (Redox's ACPI and DT code) |
| Register accessors | 300 | 0 hand-written | 0 hand-written | 4.4: generated on ARM64 and RISC-V; the classification file is data |
| Debug (breakpoints, console, stub link) | 500 | 500 | 300 | seL4 x86 breakpoints 678; Arm debug 549 |
| Other (cache maintenance, features, errata) | 600 | 550 | 250 | |
| **Total** | **≈ 7,000** | **≈ 7,500** | **≈ 5,000** | against seL4 19,680 / 16,441 / 5,972 without 32-bit and virtualisation |

The saving is largest where seL4 writes per architecture what DodOS writes once: page tables (seL4 3,452 / 2,344 / 1,307 against 300 / 450 / 300), objects and capability decoding per architecture (seL4 exposes per-architecture objects; the contract does not), and boot. It is small where the hardware differs: the IOMMU and the interrupt controllers stay the largest per-architecture parts, together about 40 % of each estimate. RISC-V gains least, because seL4's RISC-V port is already small and has no IOMMU.

Contract: nothing to add beyond parts 2 to 7; the estimate belongs in the [Language split](../../architecture/kernel-interface.md#language-split), to be replaced by a count after the one-core kernel.

## 9. What the contract must say

| Where | Rule |
|---|---|
| Values of the machine, Architectures | Each table format the kernel writes is a compile-time format description (fields of 2.6); one generic walker serves every format; invalidation, root load and the gate's write are architecture code. Every level, the root included, has *E* entries: the kernel chooses the CPU's levels and the iospaces' widths so that it holds (ARM64 with 16 KB pages: 47 bits, three levels) |
| Architectures | The entry of each architecture is a stub that saves into the thread's save area and calls the common kernel (3.4) |
| G11, kernel.md | Scan lists and register accessors generated from the pinned machine-readable specification of each architecture (AARCHMRS; the RISC-V unified database checked against the ratified text; Intel XED); every encoding classified once; the build fails on an unclassified one (4.6) |
| kernel.md, x86-64 list | Add to the forbidden instructions, pending classification: `WRMSRNS`, `WRMSRLIST`, the immediate MSR forms, `LMSW`, `CLTS`, `XSETBV`, `INVLPGB`, `TLBSYNC`, `ERETS`, `ERETU`, `LKGS`, `LOADIWKEY`, the SEAM and TDX calls, the SEV-SNP instructions, `HRESET`, `SETSSBSY`, `CLRSSBSY` |
| kernel.md, ARM64 list | Add the `MSR` immediates that change the streaming vector state (`SVCRSM`, `SVCRSMZA`, `SVCRZA`: `SMSTART`, `SMSTOP`) to the vector-length rule of D-118 |
| Start-up state | The neutral hand-over block, the entry state per architecture, the crash areas kept by the first stage (5.8); the sentences of 5.3 |
| Architectures | The machine boundary; the model's tests run against the kernel on a simulated machine and on each architecture (7.5) |

Open points, each with its alternatives:

1. **Language of the walker and the gate's checks.** A: Rust, beside the model's G3 checks and their Kani proofs (recommended). B: Zig with `comptime` descriptions, as the language split estimate places page-table primitives. Either keeps D-004.
2. **RISC-V without Svpbmt.** The page table cannot carry a memory type. A: refuse write-combining frames on such a machine (`unsupported` in `untyped_retype`) and accept uncached only where the physical attributes say so (recommended: the contract's rule "the memory type belongs to the frame" stays true). B: accept the type and document that the platform decides (breaks the rule). C: require Svpbmt to start (excludes older RISC-V machines).
3. **Missing RISC-V CSRs in the database** (`stopei`, the IMSIC's indirect registers): A: classify them by hand from the AIA text (recommended now). B: contribute them upstream and wait.
4. **The stub's language.** A: Rust (recommended). B: Zig.
5. **A/B on first stages without UEFI variables.** A: the first stage's own mechanism (U-Boot's boot count and environment). B: a DodOS file on the boot partition, read by every first stage.
6. **The raw firmware memory map.** A: handed to the platform service as a module (recommended). B: not handed at all.
7. **The machine boundary's list**, fixed with the one-core kernel.

## 10. Not verified

- Whether the AARCHMRS mirror on kernel.org is identical to Arm's own download (Arm's page was not reached).
- Arm ARM rules on: invalidation after an invalid-to-valid change; changing `TCR_EL1.TG0`/`TG1` with the MMU on; level-1 blocks with a 16 KB granule (Linux uses none: `pud_sect_supported`). The kexec MMU-off technique in `arch/arm64/kernel/cpu-reset.S` was cited, not opened.
- The RISC-V PPN field bits, the leaf rule (R, W or X set), W without R being reserved, and the RISC-V IOMMU's second-stage formats at the specifications (taken from Linux).
- At the Arm ARM: that an access with AF clear faults when hardware update is off; the 2 KB alignment of the vector table.
- AMD IOMMU v1's output-address field and its invalidation after a map; SMMUv3 stage 2's live-change rules and its invalidation after a map.
- Xen's licence of `msr-index.h` in the file itself.
- That Intel and AMD publish no machine-readable register data (a search found none; an absence cannot be proved).
- Whether the RISC-V unified database disagrees with the ratified text anywhere.
- Limine's RISC-V PE header (in its `picoefi` submodule, not checked out).
- The current uefi.org board page and promoter list (read from the archive of 1 January 2026).
- Any machine shipping with UBIOS in 2026; whether UBIOS keeps a memory range across a reset.
- seL4's SMMU support's architecture version.
- Every cost and every DodOS line count in parts 2.5, 3.3, 5.4 and 8.3: estimates, not measures.

## 11. Sources and what was measured

Clones, each in its own directory under `/tmp/dodos-arch`, at these commits; nothing was built or run from them except the counting scripts and one JSON parse.

| Source | Commit or version |
|---|---|
| Linux, `github.com/torvalds/linux` | tag `v7.3` (`Makefile`: VERSION 7, PATCHLEVEL 3), tags `v6.18` and `v6.19` for the date of `generic_pt` |
| seL4, `github.com/seL4/seL4` | `c98d70a`, 9 November 2026 |
| Limine protocol, `github.com/limine-bootloader/limine-protocol` | `877c2d4`, 14 November 2026 |
| Limine, `github.com/limine-bootloader/limine` | `033b597`, 14 November 2026 |
| Velosiraptor artifact, `github.com/ubc-systopia/velosiraptor-asplos25-artifact` | `74933d4`, 31 January 2025; tool `github.com/ubc-systopia/velosiraptor` at `0596b97` (pinned) and `main` at `150d1a8` |
| Velosiraptor paper | `arxiv.org/abs/2608.07966`, PDF read in full text |
| AARCHMRS (open), `kernel.googlesource.com/pub/scm/linux/kernel/git/maz/AARCHMRS` | `1346b16`, "AARCHMRS_OPENSOURCE_A_profile_FAT-2026-09" |
| RISC-V unified database, `github.com/riscv-software-src/riscv-unified-db` | `d583fec`, 13 November 2026 |
| Intel XED, `github.com/intelxed/xed` | `0bcb623`, 24 August 2026 |
| `x86` crate, `github.com/gz/rust-x86` | `ae3306a`, 24 November 2023 |
| Xen, `github.com/xen-project/xen` | `97bf370`, 12 November 2026 |
| Barrelfish, `github.com/BarrelfishOS/barrelfish` | `06a9f54`, 20 March 2020 |
| Redox kernel, `gitlab.redox-os.org/redox-os/kernel` | `8f0e965`, 14 November 2026 |
| rustc, `github.com/rust-lang/rust` | `5f4effd`, 13 November 2026 |
| U-Boot, `github.com/u-boot/u-boot` | `6487c50`, 13 November 2026 |
| EBBR, `github.com/ARM-software/ebbr` | `524a0f2`, 8 October 2026 |
| RISC-V BRS 1.0 | `docs.riscv.org/reference/brs/v1.0/` (`recipes.html`, `uefi.html`) |
| UBIOS, T/GCC 3007-2025 | `www.gccorg.com/article/69/426.html` and the PDF it links on `obsgcc.obs.cn-south-1.myhuaweicloud.com` |
| UEFI Forum board | `web.archive.org/web/20260101224308/https://uefi.org/board` |
| Microsoft Secure Boot certificates | `support.microsoft.com/help/5062710` (KB 5062710) |
| DodOS | Docs at `3bc7597`; dodos-kernel branch `model` at `2afc901` |

Measures made for this draft:

- **The model** (part 7.1): a Python script over `model/src` that strips `//` comments and counts, per file, the patterns `std::`, `Vec`/`vec!`, `Box`, `BTreeMap`/`HashMap`, `BTreeSet`/`HashSet`, `VecDeque`, `String`/`format!`, `Arc`/`Rc`, `.collect`/`.to_vec()`/`.clone()`, `loop`, `while`, `for`, and functions whose body calls their own name; the seven hits of the last were checked by hand. Test call sites counted with `grep` over `model/tests`.
- **seL4 and Redox** (part 8): `wc -l` over the listed directories, and a Python script that assigns each file to a part by regular expressions on its path (the rules are in the tables' captions); the scripts are kept with the draft's working files, not in this repository.
- **Linux**: `wc -l` of `generic_pt`, `kernel/entry`, the entry assembly, `libstub` and the PE headers; the `libstub` split from its `Makefile` and the architectures' `Kconfig`.
- **AARCHMRS**: a Python parse of `Registers.json`: records by type and state, accessors by instruction, distinct writable encodings, `MSR` immediate targets, memory-mapped prefixes, empty `purpose`, `title` and `groups`.
- **RISC-V database**: a Python scan of `spec/std/isa/csr/**/*.yaml` for `kind: csr`, `address`, `writable: true`, `priv_mode`; `grep` for the CSRs named in 4.2.
- **XED**: a Python scan of `datafiles/**/*.txt` for instruction blocks whose `ATTRIBUTES` contain `RING0`.
- **Limine**: `wc -l` of `common/` (C, headers, assembly).
