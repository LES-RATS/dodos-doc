# The write gate over the node's own page tables (D-117, point 2)

Written 15 November 2026 for the two owners. It answers two questions: (A) how to improve point 2 on x86-64, and (B) the same guarantee on ARM64 and RISC-V. Nothing under `/Users/btw/Documents/repos` was edited.

Inputs:
- the drafts `ownership-alternatives.md`, `fencing-without-cooperation.md` and `nodes-memory-devices.md`;
- `kernel-interface.md` (TLB, address spaces, IOMMU) and `debug-ioports-gaps.md` (I/O ports);
- D-115, D-116 and D-117.

**Marks used in this report.**
- **verified (source)**: read today in the primary source, or in a raw dump of hardware registers. Sources are in part 12.
- **verified in fencing-without-cooperation.md**: checked by that report and not re-read today.
- **(arithmetic)**: computed by me from verified inputs.
- **(inference)**: my conclusion; no single source states it.
- **not verified**: exactly that.

Local extracts used:
- the Intel SDM vol. 3, order 325384-093;
- the Arm ARM DDI 0487 M.d (30 September 2026);
- the RISC-V privileged specification (machine.adoc, supervisor.adoc);
- the PDFs of the Nested Kernel, SKEE, Hilps, CETIS, Keystone and the SPTM study.

The extracts are in the scratchpad folders `x86/`, `arm/`, `rv/`, `papers/` and `dl/`.

---

## 0. Verdict

### 0.1 Flaws in the decided design, stated first

**F1. On the reference CPU, toggling CR0.WP and Intel CET exclude each other.**
- The SDM says of CR0.WP: "This flag must be set before software can set CR4.CET, and it cannot be cleared as long as CR4.CET = 1" (verified, SDM 325384-093, §2.5).
- So a Nested Kernel gate, which clears WP on every entry, cannot run on a core that has shadow stacks or indirect-branch tracking turned on.
- Those are exactly the control-flow protections that stop a corrupted kernel from jumping into the middle of the gate.
- The i5-14600K has both (CPUID dump, part 3.1). D-117 as written ("in the style of the Nested Kernel") therefore forces a choice: write protection or control-flow protection, not both.
- **Part 3 gives a mechanism that keeps both, and is cheaper.**

**F2. The rule "refuse any translation to a frame in a chunk the node does not own" is too strict in one place and too weak in four.**

Too strict:
- Every node must map some memory it does not own:
  - the kernel image, which is part of node 0's floor;
  - the read-only machine table;
  - the rings between kernels;
  - frames shared between nodes ("every remote mapping is recorded on both sides", `kernel-interface.md`);
  - the per-node copies of a multi-core process's address space.
- Taken literally, the rule forbids all of these. The rule needs explicit classes: the global read-only set, and **grants** written by the owner's gate.

Too weak:
1. **Map counts.** A chunk can be given away while a page-table entry still maps it. The obvious case is a user mapping left behind after the kernel's direct mapping was removed. The gate must keep a **map count per chunk** and refuse `memory_give` while it is not zero.
2. **Typed page-table pages.** A page-table page must never be reachable through a writable mapping. Otherwise the kernel maps its own tables writable and the gate protects nothing. The gate must know which frames are page-table pages, and at which level.
3. **TLB and PCID/ASID.** A stale TLB entry is a translation too. After a give, a translation that survives in a TLB, or under a recycled PCID/ASID, reaches another node's memory. So invalidation, and the allocation of PCIDs/ASIDs, belong to the gate.
4. **Side doors.** Several paths reach memory without going through the CPU page tables. The binary scan does not close them all, because some are reached by instructions the kernel legitimately executes:
   - IOMMU tables (iospace tables and context entries);
   - the x2APIC ICR (INIT/SIPI to another core);
   - port I/O. Every node holds an `ioports` object covering ports 0–65,535, and the kernel itself runs IN/OUT for it, so PCI configuration through 0xCF8/0xCFC and reset through 0xCF9 are open;
   - firmware calls (SMC, HVC, ECALL, UEFI runtime services);
   - VMX/SVM, where an EPT is just another page table;
   - instructions that discard dirty cache lines: INVD, DC ISW, CBO.INVAL;
   - microcode loading, and MTRR/PAT changes;
   - on RISC-V, hgatp.

D-117 lists "device writes to memory (the IOMMU's part)" as not covered. The part a kernel writes, its iospace tables, can be covered at no cost on any hot path. **I recommend covering it** (part 2, rule G9).

**F3. Opening a window is the weak point of the whole Nested Kernel family.**
- CR0.WP, PKS, a separate root, TTBR1 or satp switching: each opens a window.
- NMIs, machine checks, SDEI events and debug traps arrive while the window is open.
- The interrupted register state is saved in memory that ordinary kernel code can write. A buggy handler can therefore change what the gate writes after the gate has checked it.
- PerspicuOS handles this with trap gates and a protected stack, but did not implement its IDT protection (verified, Nested Kernel §3.10).
- Any design with a window needs the rule of part 3.4. **The recommended x86 design has no window at all.**

### 0.2 Recommended mechanism, one line per architecture

- **x86-64 (reference PC).** Map every gate-owned page as a *supervisor shadow-stack page* (R/W = 0, Dirty = 1). This covers page tables, gate words and the save area. Ordinary stores then fault, and only `WRSSQ` writes them, which the scan confines to the gate. CET-IBT and supervisor shadow stacks stay on.
  - Origin: the idea is from CETIS (CCS 2022), which suggests it for kernel page tables. Nobody has built it in a kernel (verified, CETIS §8). **It must be prototyped first.**
  - Gains: no window; nothing to close on NMI, #MC or SMI; compatible with F1.
  - Cost: 9.3 cycles per WRSS against 0.8 for a MOV, on Tiger Lake (verified, CETIS).
  - Fallbacks, ranked:
    1. PKS, if the reference CPU really has it (conflicting evidence, part 3.1);
    2. a gate-only CR3 root with PCID (two CR3 writes, about 200 cycles each);
    3. CR0.WP, only on CPUs without CET.
- **ARM64.**
  - Baseline on every Armv8.0+ core: a gate-only translation context reached by switching TTBR1_EL1 (SKEE) or TCR_EL1.T1SZ (Hilps), with an ASID and interrupts masked. A round trip measured 284 cycles (SKEE, Exynos 7420) and 424 cycles on a big core (Hilps, Juno).
  - Where they exist: POE (POR_EL1, Armv8.8, no shipping core found), or the shadow-stack idea with GCS pages written by `GCSSTR` (Armv9.3 GCS, which needs S1PIE; no shipping core found).
  - The scan is sound because A64 instructions are fixed-length and aligned (verified, Hilps).
- **RISC-V.**
  - Baseline: a gate-only satp with its own ASID. The exit instruction goes on the last word of a gate-only page, the SKEE trick, so ordinary kernel code can never execute it.
  - Where Zicfiss exists (ratified, no silicon found): shadow-stack pages written by `SSAMOSWAP`, the no-window variant.
  - PMP/Smepmp can stay only a static bound (firmware memory, or a fixed page-table pool). Every PMP change requires a full `SFENCE.VMA` (verified, privileged spec).
  - An M-mode gate reached by ECALL is possible; no cycle figure exists for it.
  - The scan must decode at every 2-byte offset, because of the C extension.

### 0.3 Cost: the principle of D-117 holds

- **Nothing is paid on an ordinary memory access or a TLB miss.** The tables are walked natively, in one stage.
- The gate is paid on:
  - a mapping change, which DodOS batches up to 512 entries;
  - an address-space switch (CR3/TTBR0/satp loads go through the gate);
  - a few privileged writes: on x86 the x2APIC EOI, the TSC deadline and IPIs, as calls into the gate with no window.
- Per-entry costs measured on other parts: x86 WRSS about 9 cycles. A window round trip is 210–473 cycles on the parts measured (CR0.WP 473, SKEE 284, Hilps 210–424). A hypercall is 497–961 cycles (verified in fencing-without-cooperation.md).
- **No figure exists for the reference CPU.** Part 9 lists the measurements.

### 0.4 What the guarantee still does not cover

- hardware that computes wrongly;
- devices that ignore the IOMMU, or PCIe ATS-translated requests;
- firmware (SMM, EL3, M-mode, UEFI runtime);
- DRAM disturbance (bit flips in page tables; well known, not verified here);
- a bug in the gate (hence the proof and the audit);
- data-only misuse of the gate's legal interface, which by construction can damage only the node's own memory and what it has granted.

Part 7 gives the details.

---

## 1. The guarantee, stated precisely

**G (bounded node).** At every instant, for every node X, every translation that the hardware can use on X's cores leads only to:
1. memory X owns (chunks whose word reads taken(X, g_X), and X's floor); or
2. memory granted to X by its owner and not yet revoked; or
3. the global read-only set (the kernel image, read and execute only; the machine table, read only); or
4. device memory whose entry X owns.

Here "translation" covers:
- CPU page tables and TLBs, under every PCID/ASID;
- the IOMMU tables X writes;
- any other walker X can configure (EPT, hgatp, stage 2).

Write permission exists only in classes 1 and 2, and only on frames that are not page-table frames or gate frames.

The gate makes G a consequence of three facts. Each must hold on every architecture:
- **(a) single writer:** only the gate writes the structures that define translations;
- **(b) checked writes:** every value the gate writes keeps G;
- **(c) no bypass:** no other instruction can redefine translation or reach memory around it. This is the scan and the configuration lock.

The proof (part 8) is about (b) plus the hardware model; the scan checker is about (c).

Why G is what we want: a kernel bug in X can then corrupt X's memory, X's devices and what X was granted, and nothing else. D-107 and D-115 already accept this unit of failure.

---

## 2. What the gate must check, on every architecture (contract rules)

These rules are written so they could go into `kernel.md` / `kernel-interface.md` as they stand. The mechanism (part 3 onwards) differs per architecture; the rules do not.

**G1. The gate is the only writer.**
- The gate is the only code that writes:
  - page-table entries, of the kernel's own space and of every aspace;
  - iospace tables;
  - the gate words (G4);
  - the ownership, member and role words (D-115);
  - the grant table (G6).
- It is also the only code that loads a translation root (CR3, TTBR0/1, satp) and that changes translation-control state (part 3.5, 4.4, 5.4).

**G2. Frame classes.** Every frame is in exactly one class:
- *data*;
- *page table of level k*;
- *iospace table*;
- *gate* (gate words, the save area, kernel shadow stacks);
- *global read-only* (the image, the machine table);
- *device*.

Classes are recorded per chunk in the gate word. Inside a page-table chunk, the level of each 4 KB page is recorded in a gate-owned descriptor of 512 bytes per chunk. Page-table pages are drawn only from chunks of the page-table class.
- Alternative considered: a type per 4 KB frame for all memory, as the Nested Kernel's physical page descriptors and SPTM's frame table do (verified, Nested Kernel §3.4; SPTM study §5).
- That costs memory in proportion to RAM for every node, and makes retyping a 4 KB operation. Chunk-level classes keep every check O(1) at 2 MB, the unit DodOS already uses.

**G3. Checks on writing an entry.** For each entry, the gate:
1. Computes the chunk c of the target frame (`pa >> 21`).
2. Reads the ownership word of c. It must be taken(me, my generation); or the frame lies in my floor; or a live grant to me covers it; or it is in the global read-only set; or it is a device entry I own. A *free* chunk is never mappable: it holds no block.
3. Reads the gate word of c, then:
   - a table entry (not a leaf) must point to a page of class "page table of level k−1" (or "iospace table");
   - a leaf may point to data, device or global read-only frames only;
   - a leaf may never point to page-table or gate frames, except the gate's own mapping of them.
4. Checks permissions:
   - no leaf is both writable and executable at kernel level;
   - a kernel-executable leaf points only to the kernel text;
   - global read-only frames are never writable;
   - device frames are never executable and carry a device memory type;
   - user leaves are never kernel-executable (SMEP on x86, PrivExecute removed on ARM, the U bit on RISC-V, all verified, parts 3–5);
   - a non-present entry is written as all zeros;
   - the A and D bits of a leaf are preset;
   - physical-address bits above the platform's limit are zero (on x86 this includes the TME-MK key-ID bits, inference).
5. Adjusts map counts: decrement for the old target, increment for the new.

Every step is O(1): one ownership word, one gate word, one descriptor byte. A 1 GB leaf is the exception: it costs 512 checks (bounded, the same bound as `memory_take`).

**G4. One gate word per chunk.**
- A second table beside the ownership table holds, per chunk: the class (3 bits) and the map count (32 bits).
- It is written only by the owner's gate, and read-only everywhere. This is D-115's single-writer rule applied once more.
- Space: 8 bytes per chunk, 256 KB for 64 GB (arithmetic).
- A count that would overflow makes the mapping call return `busy`.

**G5. Give, destroy and retype preconditions.** `memory_give`, the destruction of a block, and a change of class all require:
- map count 0;
- for page-table chunks, no hooked table page;
- **a local invalidation since the count reached zero.** On x86 that is INVPCID of all contexts, globals included. On ARM it is TLBI VMALLE1 (or IS). On RISC-V it is SFENCE.VMA x0, x0.
- On a node with several cores, every core of the node must have passed a gate flush epoch (G12).

The gate performs the invalidation itself: give is a rare event.

**G6. Grants.**
- X's gate writes a grant: frame range, grantee Y, Y's generation, rights. It goes into a grant table that X owns and that everyone reads.
- Y's gate maps a frame of X only under a live grant. It counts its uses in its own grant-use table, which it alone writes.
- X revokes in two steps:
  1. X marks the grant *revoking*, and Y's gate then refuses new mappings under it;
  2. X's gate clears the grant only when Y's use count reads 0, or when Y's generation is dead and reclaimed.
- A chunk under a live grant cannot be given.

This is "every remote mapping recorded on both sides", turned into a mechanism. Rings between kernels and per-node copies of a multi-core address space are grants. On one core no grant ever exists, but the table format must exist now (part 11).

**G7. Roots and tags.**
- A root may be loaded only if it is a page of class "page table, top level" owned by this node.
- The gate allocates PCIDs/ASIDs. It invalidates a tag before reusing it.

**G8. W^X for the kernel, and no code generation.**
- The kernel text is read and execute only, and nothing else in kernel space is executable.
- The kernel never generates code. Wasm is compiled to user pages, which the kernel can never execute (G3).

**G9. IOMMU tables.**
- iospace tables obey G2–G5 exactly as CPU tables do: they are of class "iospace table", written only by the gate, and their leaves are checked by G3.
- The hardware node's gate writes a context entry only if:
  - the root it names is a top-level iospace table owned by the node that owns the device;
  - device-TLB (ATS) is off unless the image declares the device trusted.
- Remapping entries in posted format, which make the IOMMU write a descriptor address, are written only if that address passes G3.

The IOMMU's own registers are mapped only in the hardware node's gate view.

**G10. Interrupts, ports and firmware.** These go through the gate:
- inter-processor interrupts, including INIT/SIPI/NMI, which only go to a core whose member word says the caller is fencing it (D-116, D-117 point 1);
- port I/O, with configuration (0xCF8–0xCFF) and reset ports (0xCF9, 0x92) reserved to the hardware node (inference from the x86 platform; ports from memory, see `debug-ioports-gaps.md`);
- firmware calls (SMC, HVC, ECALL, UEFI runtime), on an allow-list that refuses calls naming a core or memory the caller does not own.

**G11. Build-time scan.**
- The kernel binary is scanned at every byte offset (x86), every 2-byte offset (RISC-V with C) or every 4-byte word (ARM64).
- The scan finds the forbidden instructions (lists in parts 3.5, 4.4, 5.4) and refuses any instance outside the gate and the start-up code that runs before protection is on.
- With control-flow protection on, it also checks that:
  - every direct branch from outside the gate targets a gate entry or a point outside the gate;
  - no landing-pad pattern (ENDBR64, BTI, LPAD) appears anywhere except at intended entries.

**G12. Several cores per node (if the trial adopts it).**
- Gate state is shared by the node's cores and protected by one gate lock with a bounded hold time.
- Each core keeps a flush epoch that only its gate increments.
- G5's "every core flushed" check is O(cores), and is paid only at give and retype.

**G13. Reload.**
- A reloaded node resets the gate words of the chunks whose ownership word names it, and empties its grant-use table.
- Grants it had made die with its generation, and grantees drop them in their reclaim answer.

**G14. Audit.**
- The recovery audit of D-115 also checks, for each chunk the auditing node holds, that the map count equals the number of entries that point into it. It walks its own tables, bounded by its own memory.
- A mismatch is a containment violation: full stop with a trace.

---

## 3. x86-64 (reference: Core i5-14600KF, Raptor Lake refresh, 6P + 8E)

### 3.1 What the CPU has

The source is the InstLatx64 CPUID dump of an i5-14600K, which has the same die as the KF. All 20 logical processors report identical leaf 7 values, and leaf 1 ECX bit 31 = 0, so the dump was taken with no hypervisor present (verified, raw dump).

| Feature | Bit | Value | Meaning |
|---|---|---|---|
| CET shadow stack (CET_SS) | leaf 7.0 ECX[7] | 1 | Present (verified, dump; bit meaning from Linux `cpufeatures.h`) |
| CET indirect-branch tracking (IBT) | leaf 7.0 EDX[20] | 1 | Present (verified, dump; Linux `cpufeatures.h`) |
| PKS | leaf 7.0 ECX[31] | 1 | CPUID says present (verified, dump; bit meaning from the Linux PKS patch, QEMU and Xen). **But** an Intel support technician wrote in May 2023: "we can confirm that the Intel® 13th-generation processors do not support PKS feature". That user's value (0x184027a4) lacked bit 31 and also bit 23, which suggests a filtered view, perhaps under Windows virtualisation (inference). **Conflicting: must be tested on the machine** |
| PCID | leaf 1 ECX[17] | 1 | Present (verified, dump: 0x7FFAFBFF) |
| FRED | leaf 7.1 EAX[17] | 0 | Absent, so the old IDT/IST event model applies (verified, dump: 0x00400810) |
| LASS | leaf 7.1 EAX[6] | 0 | Absent |
| PCONFIG, TME | leaf 7.0 EDX[18], ECX[13] | 1 | Present: key IDs in physical-address bits must be refused by G3 (inference) |
| XSAVE supervisor state CET_S | leaf 0Dh.0Ch | listed | Present (verified, dump) |

### 3.2 The four ways for the gate to write, compared

| Mechanism | How | Window | Compatible with CET | Cost per gate call | Status |
|---|---|---|---|---|---|
| **A. Shadow-stack-typed tables + WRSSQ (recommended)** | Gate pages are mapped R/W = 0, D = 1: a supervisor shadow-stack address. "Shadow-stack accesses are allowed only to shadow-stack addresses"; an ordinary write is refused because R/W = 0 and WP = 1 (verified, SDM §5.6.1). WRSS is enabled by IA32_S_CET (verified, CETIS §6). Reads stay ordinary (verified, CETIS) | **None** | Requires it | WRSSQ 9.3 cycles against 0.8 for MOV, measured in user mode on an i7-1165G7, Tiger Lake (verified, CETIS Fig. 3). Plus a function call and the checks. Raptor Lake: **no figure found** | Proposed for kernel page tables in CETIS §8; **no kernel implements it** (verified, CETIS: "CETIS will be extended to kernel space when the patch is available") |
| B. PKS | Gate pages carry key k; IA32_PKRS.WD_k = 1 by default; the gate writes PKRS | Yes (key k only) | Yes | WRMSR to IA32_PKRS is "not serializing" (verified, SDM §5.6.2 and §11.3 footnote). **No cycle figure found** | Hardware support on this CPU conflicting (3.1); Linux PKS never merged (verified in ownership-alternatives.md) |
| C. Gate root with PCID | The gate's CR3 maps gate pages writable; kernel roots map them read-only | Yes | Yes | Two MOV CR3 writes. "Writing to CR3 is expensive, costing around 200 cycles" (verified, Ren et al. SOSP 2019); "on the order of a hundred cycles" (verified, Linux PTI doc). MOV to CR3 is serializing (verified, SDM). Round trip about 200–400 cycles (arithmetic) | Works on any x86-64 with PCID |
| D. CR0.WP toggle (Nested Kernel) | Clear WP, write, set WP | Yes (**every** read-only page, including the text and the ownership table) | **No**: WP cannot be cleared while CR4.CET = 1 (verified, SDM §2.5) | NK call 0.139 µs on a Core i7-3770 at 3.4 GHz, about 473 cycles (verified, NK Table 3; arithmetic). MOV to CR0 is serializing (verified, SDM) | Built (PerspicuOS, FreeBSD 9) |

**Why A first.**
- It is the only mechanism with no window. Part 3.4's rule is then needed only for the fallbacks.
- It keeps CET, so the scan argument becomes sound against wild jumps (3.3).
- Its per-write cost is a store that is about ten times slower than a MOV, with no serialisation at all.
- Apple's PPL is the production precedent for "page tables read-only to the kernel, writable by a gate at the same level". PPL used a fast permission register; its successor SPTM moved to a lateral level (verified, Apple Platform Security; SPTM study §2.3).
- A is the x86 analogue with an architectural feature.

**Risks of A, to settle in the prototype:**
1. **Writes to shadow-stack pages through the shadow-stack pointer (SSP).**
   - CALL pushes at SSP. SSP changes through:
     - IA32_PL0_SSP and the interrupt SSP table (MSRs, which the scan forbids);
     - the token-checked instructions SETSSBSY and RSTORSSG;
     - INCSSP.
   - Rule A1: these instructions, and WRSS/WRUSS, appear only in the gate. The kernel's own shadow stacks are separated from gate pages by non-shadow-stack guard pages, as CETIS does (verified, CETIS §8).
   - Interrupt delivery verifies a supervisor token at the new SSP and refuses a busy one (verified, SDM §7.12.1). A present page-table entry has bit 0 = 1, so it can never pass as a free token. Non-present entries are written as 0 (G3), which can never equal the token's own address (inference).
2. **Page walks.**
   - The hardware walker reads and updates tables through physical addresses (SDM chapter 5, not re-read for this point: not verified), so typing the linear mapping should not matter.
   - To test on the machine: a table page mapped as a shadow-stack page must still serve walks, and A/D updates must still work.
3. **Hybrid CPU.** P-cores and E-cores must behave the same; the CPUID values are identical (verified).
4. **Errata.** Xen notes a "supervisor shadow stack fracturing" problem on some hardware when virtualised (verified, xen-devel). That does not apply to bare metal; to check the specification update of Raptor Lake (not verified).
5. **Production use of supervisor shadow stacks** exists in Xen 4.14 and later, for the hypervisor itself (verified, XSA-451). Linux does not use them; it uses kernel IBT.

### 3.3 Control flow: why CET makes the scan sound, and what remains without it

Without control-flow protection, a corrupted kernel can jump to any byte:
- into the gate after its checks;
- into the middle of an instruction, to find an unintended `0F 22` (MOV to CR) or `0F 30` (WRMSR).

PerspicuOS scanned the outer kernel at unaligned offsets and found 40 unintended instances (2 writes to CR0, 38 WRMSR). It removed them by changing alignment, inserting NOPs, rewriting arithmetic and splitting constants (verified, NK §5.2). It also relied on unmapping its CR3- and IDTR-loading code while the outer kernel ran, and did not finish that part (verified, NK §3.7, §3.10).

With **IBT**:
- an indirect JMP or CALL must land on ENDBR64;
- the gate's only ENDBR64 are its entries;
- a byte pattern F3 0F 1E FA inside an immediate would be an unintended landing pad. Linux builds the ENDBR constant at run time to avoid exactly this (`gen_endbr`, verified, Linux `ibt.h`), and its objtool seals unused ENDBRs (verified, same source).

With the **supervisor shadow stack**:
- a RET must match the shadow stack;
- IRET to CPL 0 checks it too (SDM vol. 1 ch. 18, not re-read: not verified).

So with both on, the reachable instruction stream is:
- the aligned decoding from legitimate targets;
- plus any byte pattern that decodes as ENDBR64.

The scan (G11) then needs three checks:
1. no forbidden instruction in the aligned decoding outside the gate;
2. no unintended ENDBR64 pattern anywhere;
3. every direct branch outside the gate targets a gate entry or a point outside the gate.

The every-byte scan of PerspicuOS stays as defence in depth: it costs nothing at run time.

**Cost of CET:**
- Shadow stacks: 2.02 % on SPEC CPU 2017 C/C++ in user space (verified, CETIS Fig. 2; i7-1165G7).
- IBT: no kernel figure found.
- To measure: the DodOS null system call and IPC with S_CET off and on.

### 3.4 NMI, machine check, SMI and debug traps while a window is open (fallbacks B, C, D only)

| Event | Can it arrive in the gate? | What happens without a rule | Closing rule |
|---|---|---|---|
| Maskable interrupt | No: the gate runs with IF = 0 | — | CLI at entry; a second CLI after opening, as PerspicuOS does (verified, NK Fig. 2) |
| NMI | Yes | Handler runs with the window open | Rule W below |
| #MC (machine check) | Yes | Same | Rule W; a fatal #MC kills the node, and the window dies with it |
| #DB (debug), #PF inside the gate | Yes if DR7 or a bug | Same | Rule W; MOV to DR outside the gate is forbidden by the scan; a fault inside the gate is fatal |
| SMI | Yes | SMM firmware runs. The SMM register-initialisation table: CR0 "PE, EM, TS, and PG flags set to 0; others unmodified", CR4 "Cleared to zero" (verified, SDM Table 34-4). RSM reloads the saved state (verified, SDM §34.3.2). RSM refuses a saved state with "CR4.CET would be set to 1 and CR0.WP to 0" (verified, SDM §34.3.2) | None needed beyond trusting firmware, which every design does. No kernel code runs in between |
| INIT from the fence | Yes | The core resets | Intended (D-117 point 1) |

**Rule W (window events).**
1. Every IDT entry points to a gate stub. The IDT is written once at start-up and mapped read-only. IDTR is loaded only at start-up.
2. If the interrupted RIP lies inside the window, the stub:
   - closes the window before any non-gate instruction runs (sets WP, writes PKRS closed, or reloads the kernel root);
   - saves the interrupted general registers and RIP into a gate-owned per-core area;
   - runs the outer handler;
   - on return, restores the gate's registers from that area, not from the frame the handler could have written;
   - reopens and resumes.
3. A return into the window that does not come from that save halts the node.

PerspicuOS states the first half (invariants 11 and 12: WP set on every trap before outer handlers; IDT write-protected), and invariant 13 (gate stack write-protected) (verified, NK §3.2). Hilps adds the check "if TCR does not have the outer value at the vector, halt" (verified, Hilps, section on the inner-domain call). The register-save half is my addition: the outer handler can otherwise rewrite the saved registers (inference).

With mechanism A there is no window. The only residue: an event interrupting the gate between its check and its WRSS could alter registers through the saved frame.
- Rule A2: the gate is a leaf function. It holds the checked values in registers and keeps no stack.
- When an NMI, #MC or #DB interrupts the gate, the stub saves the interrupted registers to a gate-owned area with WRSSQ and restores them from there. It does this only in that rare case, about 16 WRSS, roughly 150 cycles (arithmetic).
- After each write, the gate re-reads the entry and re-checks it. If the check fails, the node halts (fail-stop). This costs one load per entry.

### 3.5 Structures behind the gate, and instructions the scan forbids (x86)

Structures behind the gate or immutable after start-up:

| Structure | Why it matters to G | Rule |
|---|---|---|
| Page tables, all levels, every aspace | Define translation | G1–G5 |
| CR3 | Chooses the root | Gate entry `load_root`: checks G7, then MOV CR3 (the cost every kernel pays anyway, plus a few checks) |
| PCIDs | Stale translations | Allocated by the gate; INVPCID before reuse |
| CR0 (WP, PG), CR4 (SMEP, SMAP, PCIDE, CET, PKS, PKE, VMXE, LA57) | Lift protection, run user pages, enable VMX | Written only at start-up. Mechanism A needs no CR write afterwards. CR4.VMXE stays 0 unless the image declares the optional monitor (D-117 point 3) |
| EFER (NXE, LME, SVME), IA32_S_CET, IA32_PL0_SSP, IA32_INTERRUPT_SSP_TABLE_ADDR, PKRS, LSTAR/STAR/SFMASK/CSTAR, SYSENTER_EIP, APIC_BASE, MTRRs, PAT, microcode-update trigger, IA32_FEATURE_CONTROL | Disable NX, move entry points, retype memory, load microcode | WRMSR only in the gate, against an allow-list. Start-up-only MSRs are refused after start-up |
| x2APIC ICR | INIT/SIPI/NMI to another core | Gate entry `send_ipi`: fixed vectors to any core of the machine; INIT, SIPI and NMI only under G10 |
| x2APIC EOI, TSC_DEADLINE | Not dangerous, but written by WRMSR | Gate entries `eoi()` and `set_deadline()`. Both MSRs are non-serializing (verified, SDM footnote), so the cost is a call plus the WRMSR |
| IDT, GDT, TSS, interrupt SSP table, IST stacks' tokens | Event delivery | Written at start-up, then read-only. DodOS has one kernel stack per core and no TSS I/O bitmap (`debug-ioports-gaps.md`), so nothing needs to change them at run time (inference) |
| IOMMU (VT-d) registers, root and context tables, interrupt remapping table | DMA | G9: hardware node's gate only |
| Port I/O | PCI configuration, reset, SMI port | G10. The DodOS kernel executes IN/OUT for `ioport_in`/`ioport_out` (`debug-ioports-gaps.md`), so those paths become gate entries. IN/OUT at CPL 0 are never checked against IOPL or the I/O bitmap (verified: pseudocode checks the bitmap only "IF ((PE = 1) and ((CPL > IOPL) or (VM = 1)))") |
| UEFI runtime services | Firmware code at CPL 0 with the caller's tables | Called only from the gate, on a dedicated root that maps only the runtime regions and the arguments (inference) |

Instructions forbidden outside the gate and start-up (G11):
- MOV to CR0/CR3/CR4 (0F 22); MOV to DR (0F 23);
- WRMSR (0F 30); XRSTORS (it restores supervisor CET state, verified dump: CET_S is XSAVE-managed);
- LGDT, LIDT, LLDT, LTR;
- INVD, which loses data: "Data cached internally and not written back to main memory will be lost" (verified);
- the whole VMX and SVM sets (VMXON … VMRUN);
- IN, OUT, INS, OUTS;
- WRSS, WRUSS, RSTORSSG, SAVEPREVSSP, SETSSBSY, CLRSSBSY, INCSSP;
- ENCLS, PCONFIG;
- any unintended ENDBR64.

WBINVD, INVLPG, INVPCID and RDMSR are harmless to G and allowed.

### 3.6 One core per node, and several

- CR0, CR3, CR4, PKRS, IA32_S_CET and SSP are per logical processor (SDM; PKRS "per logical processor" not re-read: not verified). A window opened on one core opens nothing on another (inference).
- **One core per node (decided).** The gate needs no lock. The ownership word of a chunk X owns can change only through X itself (single writer), so check-then-write has no race across nodes. Only a shootdown inside the node is ever needed, and on one core that is a local invalidation.
- **Several cores per node (candidate).**
  - Gate state is shared, so a gate lock is needed (G12).
  - A window on core A leaves core B's view read-only.
  - PerspicuOS's multiprocessor concern applies: a stack in outer memory could be rewritten from another core while the gate runs (verified, NK invariant 13). Rule A2 (no stack) and Rule W (gate-owned save area) cover it.
  - G5 requires every core of the node to have flushed: an IPI round, plus the epoch check.

### 3.7 Batching and large pages

- PerspicuOS was 2.5–3× slower on mmap and fork without batching, and preliminary batching cut that by more than 60 % (verified, NK §5.4).
- The kpkeys series on arm64 batches page-table permission switches in lazy-MMU sections, so a section switches twice whatever the mapping size (verified, kpkeys v6 cover letter).
- DodOS rule: a gate call takes a vector of up to 512 operations (one table page). Each operation is read once into registers, then checked and written.
- `memory_take` of a 1 GB run is one call with 512 entries of 2 MB.
- 2 MB leaves cost one ownership word and one gate word each; a 1 GB leaf costs 512 (G3).
- With mechanism A, a batch of 512 entries is about 512 × (9.3 + checks) cycles of stores. The checks are two loads per entry, most of them in L1 (inference). That is a few thousand to ten thousand cycles, next to clearing 1 GB, which takes milliseconds (inference).

---

## 4. ARM64

### 4.1 The problem

ARM has no CR0.WP. An EL1 write to a read-only mapping always faults; that part is fine. But the kernel can rewrite TTBR0/1_EL1, TCR_EL1 or SCTLR_EL1 with one MSR. The gate therefore needs either:
- a second translation context only it can enter; or
- a register that overlays permissions.

The scan of MSR instructions is sound on A64, because "instruction opcodes have a fixed length and are aligned on AArch64, Hilps can exhaustively identify privileged instructions" (verified, Hilps, section on control of system registers).

### 4.2 Mechanisms

| Mechanism | How | Window | Cost (cycles, round trip) | Architecture | Shipping cores |
|---|---|---|---|---|---|
| **Switch TTBR1_EL1 to a gate context (SKEE)** | Entry: `MSR TTBR1_EL1, XZR` (a constant: the gate tables sit at physical 0), then the TLB is invalidated, or an ASID is used. Exit: the instruction that restores the kernel's TTBR1 is the last one of a page mapped only in the gate context, so it never exists in the kernel's view (verified, SKEE, switch-gate section) | Yes | 813 with TLB invalidation; 284 with ASID; Exynos 7420 (Galaxy S6) (verified, SKEE Table II). The ASID variant "is not complete without adopting a sandboxing mechanism" (verified, SKEE) | Armv8.0 | All |
| **Widen TCR_EL1.T1SZ to reveal the gate region (Hilps)** | The gate region lies beyond the kernel's VA range. Entry widens T1SZ (27 → 25); exit narrows it back. The gate region is non-global with its own ASID. Code after each TCR write checks the value. The vector checks TCR and halts if interrupted inside (verified, Hilps, design section) | Yes | 424 (big, ASID), 832 (big, TLB invalidation), 210 / 249 (little); Juno board (verified, Hilps Table II). LMbench close to native | Armv8.0 | All |
| POE overlay (FEAT_S1POE) | Page-table pages carry a POIndex; POR_EL1 denies write except inside the gate. Overlays "are not permitted to be cached in a TLB" (verified, Arm ARM D8), so a switch is an MSR plus an ISB | Yes | **No figure**: "No arm64 hardware currently implements POE"; a mock gives about 2 % system time on kernbench (verified, kpkeys v6, February 2026) | OPTIONAL from Armv8.8 (verified, Arm ARM A2) | **None found.** Apple M1, M3, M4: absent (verified, ID-register table). M5: not verified |
| PIE (FEAT_S1PIE) | Indirect permissions through PIR_EL1 | Yes | Base permissions "are permitted to be cached in a TLB" (verified, Arm ARM D8), so a switch needs TLB maintenance: not a cheap gate | OPTIONAL from Armv8.8 | Apple M1/M3/M4 absent (verified) |
| **GCS-typed page tables + GCSSTR** (analogue of x86 A) | Map gate pages as privileged GCS pages with PrivWrite = 0. Only Guarded Control Stack stores (GCSSTR, enabled by GCSCR_EL1) write them. GCS encodings exist only under PIE: "FEAT_S1PIE is required to be implemented if FEAT_GCS is implemented" (verified, Arm ARM D11.5) | **None** | **No figure** | GCS OPTIONAL from Armv9.3 (verified) | **None found**; Apple M1/M3/M4 absent (verified) |
| Apple PPL (production precedent) | Page tables and PPL code mapped r-- to the kernel; the PPL trampoline flips the proprietary APRR register to make the tables rw- (verified, SPTM study §2.3.2) | Yes | No figure found | Apple A11+ | Apple only, undocumented |
| Apple SPTM (production precedent) | Lateral guarded level GL2, entered by GENTER. SPRR gives page tables r-- at EL2 (the kernel) and rw- at GL2 (verified, SPTM study §2.3.3–2.3.4). SPTM is "sole authority regarding memory retyping" (verified, ibid.); Apple says it "help[s] protect page tables for both user and kernel processes" (verified, Apple Platform Security) | n/a | No figure found | A15+/M2+ | Apple only; not usable by DodOS (D-024: no reverse engineering) |
| FEAT_THE (Translation Hardening) | Protected descriptors may be changed only by RCW instructions within RCWMASK_EL1. But plain stores remain possible unless stage 2 marks the tables AssuredOnly (verified, Arm ARM D8.2.7) | — | — | OPTIONAL from Armv8.8 | Not found. **Useful only to the optional monitor layer** |

### 4.3 Recommended ARM64 design

1. **Baseline on every core:** a SKEE/Hilps-style gate context with its own ASID. My preference is TTBR1 switching with the SKEE exit-page trick, because it needs no VA-size juggling. Both are measured.
2. **POE when present**, chosen at boot from ID_AA64MMFR3_EL1. It is cheaper (no TLB maintenance) and opens only the page-table index.
3. **GCS typing when present.** It removes the window, as x86 A does. It is the long-term target; there is no hardware today.
4. **Control flow.**
   - BTI (OPTIONAL from Armv8.4, mandatory from 8.5) and PAC (mandatory from Armv8.3) where present (verified, Arm ARM).
   - Apple M3/M4 have both; M1 has PAC only (verified, ID-register table).
   - Without them, ARM falls back to "jumps are improbable for bugs", as on x86 without CET.
5. **Window rule** (as 3.4):
   - The vector stubs are gate code, and VBAR_EL1 is written only at start-up.
   - SError, synchronous exceptions, FEAT_NMI interrupts and SDEI events can arrive inside the window. D-117 point 1 plans SDEI or NMI priority for the stop, and that stop may arrive inside the window.
   - The stub closes the window (restores the kernel's TTBR1/TCR, or POR_EL1) before any outer code runs, then saves state in the gate area.
   - SDEI entry points are registered only through the gate's SMC path (G10).
6. **Break-before-make.** The gate follows Arm's break-before-make rules when it changes block sizes (not re-verified here; standard in the Arm ARM).

### 4.4 Structures and instructions (ARM64)

Forbidden outside the gate (every 4-byte word scanned):

- **MSR to translation and control registers:** TTBR0_EL1, TTBR1_EL1, TCR_EL1, TCR2_EL1, SCTLR_EL1, MAIR_EL1, VBAR_EL1, POR_EL1, PIR_EL1, PIRE0_EL1, GCSCR_EL1, GCSPR_EL1. If the kernel runs at EL2 with VHE (Apple machines under m1n1), add their _EL2 forms and the _EL12 aliases.
- **SMC and HVC:** PSCI CPU_ON names another core and an entry address; FF-A can move memory to the secure world (G10).
- **DC ISW:** invalidate by set/way without clean. It may drop dirty lines a coherent cache holds for another node (inference).
- **Implementation-defined system registers:** the SYS/MSR encodings outside the architected space.
- **Hypervisor state:** the EL2 translation registers and VTTBR, unless the optional monitor is declared.

Allowed: TLBI, AT, DC CIVAC, and ICC_SGI1R_EL1 (IPIs). An SGI cannot reset a core; storms are a denial of service only (inference).

Hardware helps by itself:
- WXN: privileged-writable is execute-never;
- "if UnprivWrite is present, then PrivExecute is removed" (verified, Arm ARM D8);
- PAN; HPDS (mandatory from 8.1).

### 4.5 Several cores (ARM64)

TCR, TTBRs and POR_EL1 are per core: "as TCR containing the TxSZ field exists per processor core, Hilps can enforce the intra-level isolation to each core separately" (verified, Hilps). Broadcast TLBI (IS) gives G5 across a node's cores without IPIs. It also invalidates other nodes' entries, which costs performance but is harmless (inference).

---

## 5. RISC-V

### 5.1 The problem

- An S-mode store to a page without W raises a store page fault: "Attempting to execute a store … whose effective address lies within a page without write permissions raises a store page-fault exception" (verified, priv. spec, supervisor.adoc).
- There is no override bit, so read-only tables bind S-mode.
- But satp is an S-mode CSR, so any S-mode code can load any root.
- "Irrespective of SUM, the supervisor may not execute code on pages with U=1" (verified): user Wasm code is never executable by the kernel.
- sstatus.SUM and MXR affect only the node's own user pages, so they do not touch G (inference).

### 5.2 Mechanisms

| Mechanism | How | Window | Cost | Status |
|---|---|---|---|---|
| **Gate-only satp with its own ASID** | Kernel roots map gate pages read-only; the gate root maps them writable. "writing satp does not imply any ordering constraints … nor does it imply any invalidation", so distinct, never-reused ASIDs avoid SFENCE (verified, supervisor.adoc) | Yes | **No figure found** for a satp write. To measure: a csrw satp round trip on a P550 or K3 board | Ratified, everywhere with Sv39 |
| SKEE exit trick, RISC-V form (proposed) | `csrw satp, <kernel>` is the last instruction of a page mapped only in the gate root. The next fetch, in the shared page after it, runs under the kernel root. Entry loads a constant gate root | — | — | Inference, built on SKEE's verified ARMv8 version. Entry has the same weakness as SKEE's ASID variant: a jump to `csrw satp` with a forged register. It is closed only by Zicfilp, or by a check after the write |
| **Zicfiss shadow-stack pages + SSAMOSWAP** (no window) | "A non-shadow-stack store causes a fault if done to a page mapped as a shadow stack"; SSAMOSWAP stores to an address in a shadow-stack page, enabled for S-mode by menvcfg.SSE (verified, unprivileged CFI chapter) | **None** | **No figure** | Zicfilp/Zicfiss ratified (v1.0, verified); **no shipping silicon found**; research core CVA6-CFI (verified, arXiv 2602.04991); emulated in QEMU (verified, QEMU `cpu.c`) |
| PMP/Smepmp as the write bound | M-mode sets a PMP region over the page-table pool read-only for S. "PMP checks are also applied to page-table accesses for virtual-address translation, for which the effective privilege mode is S" (verified, machine.adoc). 0, 16 or 64 entries, "PMP CSRs are only accessible to M-mode" (verified) | Gate in M-mode | ECALL round trip: **no figure found**. Keystone's M-mode context switch, which includes PMP changes, takes 1.8 K–2.6 K cycles (verified, Keystone §7). A PMP change needs "SFENCE.VMA … with rs1=x0 and rs2=x0" (verified, machine.adoc): a full TLB flush | Ratified. Workable only with a **fixed** page-table pool per node; ownership cannot follow 2 MB chunks with 16 entries. Hardware A/D updates are checked by PMP, so they fault on a read-only pool: A and D must be preset (G3) |
| SPMP (Sspmp) | S-mode PMP "in systems that implement S-mode but do not use paged virtual memory" (verified, SPMP spec) | — | — | Ratified (v1.0, August 2026); **not applicable** to a paged kernel |
| Smmpt / supervisor domains | M-mode per-hart memory-protection table, one domain per node: hardware ownership per page, on every access | — | Unknown | Not ratified (v0.9.0, verified in fencing-without-cooperation.md). The best future answer; keep `StartOwnership.layout` as the hook |

### 5.3 Recommended RISC-V design

1. **Baseline:** a gate-only satp with a dedicated ASID, the SKEE exit-page trick, interrupts masked (sstatus.SIE = 0), and Rule W at stvec. stvec is written only at start-up, and the stub checks satp.
2. **Zicfiss typing when present.** It removes the window. Zicfilp landing pads must be 4-byte aligned "to keep accidental byte patterns from forming a valid landing pad" (verified), which makes a compressed-code kernel scannable for LPAD.
3. **PMP stays static:** firmware and, optionally, a fixed pool. **No M-mode gate by default.** It would make DodOS depend on its own OpenSBI extension at every mapping change, with an unmeasured cost and a full TLB flush for each PMP change.
4. **Firmware.**
   - ECALL to M-mode goes only through the gate's allow-list. HSM hart_start names another hart and an address. RFENCE and IPI name hart masks. PMU snapshot and steal-time take physical addresses (G10).
   - The firmware sets menvcfg.CBIE so that S-mode CBO.INVAL flushes or traps instead of discarding. senvcfg semantics verified; menvcfg by analogy, not verified.

### 5.4 Instructions (RISC-V)

Forbidden outside the gate (every 2-byte offset scanned, because the C extension allows 32-bit instructions at any halfword):
- CSR writes (all six forms, including rd = x0) to satp, stvec, ssp, the H-extension CSRs (hgatp is a second page table) and senvcfg;
- ECALL;
- SSAMOSWAP, SSPUSH and C.SSPUSH (if the kernel uses Zicfiss for page tables);
- CBO.INVAL;
- HFENCE and the hypervisor load/store instructions.

SFENCE.VMA and SINVAL.VMA are allowed.

---

## 6. Cost table

Unless "estimate" is written, figures are measured, with the part named.

| | x86-64 | ARM64 | RISC-V |
|---|---|---|---|
| Ordinary access, TLB miss | 0 (one-stage walk) | 0 | 0 |
| **Recommended write mechanism, per entry** | WRSSQ 9.3 cycles (MOV 0.8), i7-1165G7 Tiger Lake (CETIS). Raptor Lake: no figure | TTBR1 switch, round trip per call: 284 (ASID) / 813 (TLBI), Exynos 7420 (SKEE). T1SZ switch: 424 / 832 big, 210 / 249 little, Juno (Hilps) | satp switch: no figure found |
| No-window variant | = recommended | GCSSTR: no figure, no hardware | SSAMOSWAP: no figure, no silicon |
| Key-overlay variant | WRMSR PKRS: no figure; architecturally non-serializing (SDM) | POR_EL1 + ISB: no figure; mock about 2 % system time on kernbench (kpkeys) | — |
| Second-root variant | MOV CR3 about 200 cycles (Ren et al.), "order of a hundred" (Linux PTI). Round trip about 200–400 (estimate) | = recommended | = recommended |
| CR0.WP variant | NK call 0.139 µs ≈ 473 cycles, i7-3770 (NK Table 3; arithmetic). Excluded with CET | n/a | n/a |
| M-mode gate | n/a | n/a | Null ECALL: no figure. Keystone SM context switch 1.8–2.6 K cycles (FU540, Rocket). PMP change → full SFENCE.VMA |
| For comparison: hypercall | 497–961 (seven Intel parts); VMCALL 0.513 µs (NK) | 376–6,500 | 739 (FireSim) (verified in fencing-without-cooperation.md) |
| Batch of 512 × 2 MB (`memory_take` of 1 GB) | About 5–15 K cycles (estimate, from WRSS and two L1 loads per entry) | One switch + 512 stores + checks (estimate) | Same (estimate) |
| Address-space switch | MOV CR3 + gate checks (about +10–30 cycles over plain, estimate) | MSR TTBR0 + checks (estimate) | csrw satp + checks (estimate) |
| Control flow | SHSTK 2.02 % SPEC 2017 user (CETIS); kernel IBT: no figure | BTI/PAC: no figure found | Zicfilp/Zicfiss: no silicon |

---

## 7. What the guarantee does not cover, and attacks that survive

1. **Hardware that computes wrongly.** A mercurial core can write anything its tables allow, including the gate's own pages through a corrupted WRSS. The audit (G14) detects damage to the shared words afterwards. The optional monitor of D-117 point 3 is the answer when it matters.
2. **DMA outside the IOMMU's control:**
   - devices that bypass the IOMMU;
   - ATS-translated requests from a device whose device-TLB was enabled (G9 forbids enabling it unless the image declares the device trusted);
   - peer-to-peer traffic that never reaches the IOMMU (platform-dependent; not verified).
3. **Firmware:** SMM, EL3, M-mode, UEFI runtime and microcode. Trusted by every design.
4. **DRAM disturbance** (bit flips in page tables): not covered. ECC and the check field narrow it. Well known; not verified here.
5. **A bug in the gate.** Hence the proof (part 8) and the audit (G14).
6. **Data-only attacks through the legal interface.** A corrupted kernel can still, legally:
   - map, unmap or give its own memory;
   - grant its own memory to the wrong node;
   - send IPI storms;
   - write garbage into rings it owns (receivers validate).

   All of this damages only X, what X granted, or availability. The gate does not judge "this block has no live descendant", which stays with the derivation-tree code (as in `ownership-alternatives.md`).
7. **Time-of-check races.**
   - None across nodes on one core: only X writes X's words.
   - Grants are revoked by the two-step protocol of G6.
   - Within a multi-core node, the gate lock covers it.
   - Interrupts: Rule W, or Rule A2.
8. **Interrupt windows.** None with mechanism A, x86 GCS or Zicfiss. Rule W for the others. Its weakest point is an NMI-class event that corrupts the saved state twice consistently, which is improbable for bugs (inference).
9. **Jumps into the gate without control-flow protection.** Machines without CET, BTI or Zicfilp (Apple M1, Raspberry Pi-class Armv8.2 cores) rest on improbability for bugs, plus SKEE-style exit pages and checks after control-register writes. The Pi-class claim is from memory, not verified.
10. **Speculative reads.** Refusing cross-node mappings except grants (G3) also denies speculative reads of other nodes' memory through the kernel's map (inference). Cache side channels remain.

---

## 8. Proof: what is realistic, and the exact property

**The property P_gate (per node X, per gate call), for the specification to state:**
1. **Pre-state invariant I.** The invariant is:
   - every entry reachable from every registered root of X, and from every iospace root of X, satisfies G3's classes and permissions;
   - every frame of class page-table or gate is mapped by no writable or user entry;
   - for every chunk, the map count equals the number of leaves that target it;
   - every registered root is a top-level table page of X;
   - every loaded tag is not stale.
2. **Preservation.** If I holds before a gate call, and the ownership words of chunks X owns change only through this call, then I holds after it, whatever the arguments.
3. **Refinement.** The abstract mapping (virtual address → frame, rights) changes exactly as the call's specification says.
4. **Give safety.** After give(c), no translation to c exists in X's tables or in its TLB model.
5. **Hardware model.** Translation is the walk defined by the tables plus a TLB that may hold any translation since the last invalidation. That is the cached-translation model; Syeda and Klein's JAR 2020 paper on reasoning under cached address translation is one such model (title from search; not read).

Outside the proof, checked separately:
- the scan (a small checker, itself testable);
- the start-up configuration (registers locked);
- the stub rule.

**What exists:**

| Work | Scope | Size | Gaps |
|---|---|---|---|
| Asterinas / CertiK (CortenMM) | Page management including page tables; cursor functional correctness; refinement of the tree to a flat map "maintaining invariants after each update" (partial, ongoing) | About 6 K lines of specification, 2 K of proof, 2 K executable (verified, Asterinas blog, February 2025); KVerus later generated 1,387 proof lines (verified, arXiv 2605.03822) | Concurrency open; no hardware or TLB model mentioned; found a race that "might have allowed a page table node to be freed prematurely" (verified) |
| verified-nrkernel (Verus) | Single-threaded page-table code proved against a model of the hardware MMU | 288 verified items (verified, repository mirror) | Single-threaded |
| Verus case studies (SOSP 2024) | Includes an OS page table | 6.1 K implementation, 31 K proof across all case studies (verified, search summary of the paper) | — |
| Atmosphere (SOSP 2025) | Verified kernel in Verus | 6 K lines, 20.1 K proof (verified in fencing-without-cooperation.md) | No termination |
| SeKVM | Stage-2 page-table isolation on a multiprocessor | 3.8 K lines, about two person-years (verified in fencing-without-cooperation.md) | C/assembly link not machine-checked |

**Realistic for DodOS (inference).**
- The gate is the page-table writer plus G4–G7. That is about 1.5–3 K executable lines of Rust, in the range of Asterinas' page-table module.
- Expect a 3–4× specification-plus-proof overhead in Verus (Asterinas: 8 K for 2 K).
- On one core, sequential reasoning suffices.
- The multi-core gate (G12) adds a lock and flush epochs. VerusSync-style reasoning is unfinished even in Asterinas.
- The assembly stubs (the window or A2 save, CR/MSR writes) are proved by hand or tested exhaustively, as SeKVM did.

---

## 9. What to measure or prototype first, and where

D-024: the only hardware is the reference desktop and the Dell laptop (both Intel). ARM64 and RISC-V are QEMU only.

| # | Question | How | Machine | Decides |
|---|---|---|---|---|
| 1 | Does the 14600KF really have PKS, CET_SS and IBT on bare metal, on P- and E-cores? | Read CPUID 7.0 on every core from a UEFI test kernel. Set CR4.PKS (bit 24) and check there is no #GP. Write IA32_PKRS (0x6E1) and check a write to a key-k page faults. Set CR4.CET with S_CET.SH_STK_EN, WRSS_EN, ENDBR_EN | Reference desktop | Whether PKS is a fallback at all. Settles the CPUID versus Intel-support conflict |
| 2 | **Shadow-stack-typed page tables work** | Map a table page R/W = 0, D = 1. Check: an ordinary store faults; WRSSQ writes; the walker still uses the page; A/D updates still happen; IST delivery with tokens still works; an NMI inside the gate goes through the A2 save | Reference desktop, then the Dell | Mechanism A or fallback C |
| 3 | Gate call costs | rdtsc/lfence loops on P and E cores: WRSSQ alone; a batch of 512 entries; MOV CR3 with PCID no-flush; MOV CR0 toggling with CET off; WRMSR PKRS if #1 says yes; null gate call | Reference desktop | The cost table for the reference machine |
| 4 | CET overhead on the kernel | DodOS null system call, IPC on one node, address-space switch: S_CET off, IBT only, IBT + SS | Reference desktop | Whether CET is on by default |
| 5 | Scanner false positives | Run the every-byte scanner on the one-core kernel. Count unintended forbidden instructions and ENDBR patterns; fix by layout, as NK did (40 instances) | Build machine | Feasibility of G11 |
| 6 | Functional ARM64 gate | TTBR1 switch with ASID and SKEE exit page; GCS-typed tables (QEMU emulates GCS and S1PIE, not POE: verified, QEMU `emulation.rst`) | QEMU | Whether ARM64 code is ready when hardware is bought |
| 7 | ARM64 cycles | The same microbenchmarks | **Needs a board**: any Armv8.2+ for TTBR/T1SZ; none exists yet for POE or GCS | Owners: buy a board or not |
| 8 | Functional RISC-V gate | Gate satp with ASID and exit page; Zicfiss-typed tables with SSAMOSWAP (QEMU emulates Zicfiss/Zicfilp/Smepmp: verified, QEMU `cpu.c`) | QEMU | — |
| 9 | RISC-V cycles | csrw satp round trip; null ECALL | An RVA23-class board (P550, K3) | Whether the satp gate is cheap enough |
| 10 | Fault injection | Mutate the gate's callers: wrong frame, wrong level, give with a live mapping, stale PCID. Random stray stores. Count cross-node translations that survive | QEMU + reference model | That G3–G7 catch what the check field and D-115 miss |
| 11 | Audit cost (G14) | Walk all tables of a node holding 64 GB | QEMU, then desktop | Fits the recovery budget |

---

## 10. Points for the two owners to decide

**O1. The x86 write mechanism.**
- *Recommendation:* the contract states rules G1–G14 and stays mechanism-neutral. The x86 implementation uses A (shadow-stack-typed tables + WRSSQ) when CET_SS is present, chosen at boot. C (gate root with PCID) is the fallback.
- *Alternatives:* B, PKS, if test #1 confirms it. D, CR0.WP, only on CPUs without CET. D as the default would give up CET (F1).

**O2. CET on the reference machine.**
- *Recommendation:* IBT and supervisor shadow stacks are on by default where present. A machine without them runs in a mode flagged "gate without control-flow protection" in the start-up page.
- *Alternative:* CET optional, off by default. Simpler, but the gate is then protected only by improbability against wild jumps.

**O3. Shared frames between nodes.**
- *Recommendation:* grants written by the owner's gate (G6). This is required by remote mappings and by multi-core address spaces.
- *Alternative:* forbid every cross-node mapping except the global read-only set. That drops remote mappings and makes multi-core processes impossible. Not recommended.

**O4. IOMMU tables, ports and IPIs behind the gate.**
- *Recommendation:* yes (G9, G10). Amend D-117's "not covered: device writes" to "not covered: devices that bypass the IOMMU, and ATS-trusted devices".
- *Alternative:* leave the IOMMU side to the hardware node's correctness, as D-117 now says. A buggy node could then point its own device at another node's memory through its iospace.

**O5. Ports: ownership or a fixed deny-list.**
- *Recommendation:* the gate refuses the configuration and reset ports to every node but the hardware node, and allows all others as today.
- *Alternative:* per-node port ranges in the device table. This reverses `debug-ioports-gaps.md`'s "no exclusive ranges" choice.

**O6. Firmware calls.**
- *Recommendation:* gate-only, on an allow-list, with UEFI runtime called on a dedicated root.
- *Alternative:* trust the kernel's firmware calls. This is a cross-node hole (PSCI CPU_ON, SBI hart_start, FF-A).

**O7. ARM64 baseline.**
- *Recommendation:* TTBR1 switch with ASID (SKEE form) on every core; POE or GCS typing when present. Buy one Armv8.2+ board to measure, since the project owns no ARM64 machine.
- *Alternative:* T1SZ switch (Hilps); or wait for POE or GCS hardware.

**O8. RISC-V baseline.**
- *Recommendation:* gate-only satp with ASID; Zicfiss typing when silicon exists; no M-mode gate.
- *Alternative:* an M-mode gate with a fixed per-node page-table pool under PMP. It is stronger against S-mode code, but every PMP change costs a full TLB flush, and it adds a firmware dependency.

**O9. Proof scope.**
- *Recommendation:* P_gate (part 8) in Verus for the one-core gate; a tested scanner; stubs reviewed by hand.
- *Alternative:* Kani bounded proofs only. Cheaper, but they do not prove preservation for all inputs.

**O10. Several cores per node (if adopted).**
- *Recommendation:* one gate lock per node, and per-core flush epochs (G12).
- *Alternative:* per-core gates with lock-free updates to gate words. Harder to prove.

---

## 11. What the one-core kernel must contain now (no deferral)

Kernel:
1. A `gate` module that is the only writer of tables, words and grants. Its API takes typed handles (block, run, table page, root), never raw physical addresses (D-115's rule).
2. Frame classes per chunk (G2), and page-table pages drawn only from page-table chunks.
3. The gate word table (G4) beside the ownership table, with map counts kept on every entry write.
4. G3 checks, including W^X, preset A/D, zero non-present entries and the physical-address-bit limit.
5. G5 preconditions on give, destroy and retype, with the gate doing the invalidation.
6. A root registry and PCID/ASID allocation in the gate (G7).
7. iospace tables under the gate (G9). The hardware node's context-entry writes go through its gate.
8. Gate entries for:
   - IPIs, with INIT/SIPI/NMI tied to the member word;
   - EOI and timer deadline (x86);
   - port I/O, with the deny-list;
   - firmware calls.
9. IDT, GDT, TSS and the interrupt SSP table (x86), VBAR (ARM) and stvec (RISC-V) written at start-up only, then immutable.
10. The x86 mechanism chosen at boot (A, otherwise C), with the A2 save or Rule W in the stubs.
11. The build-time scanner (G11) in CI: every byte offset (x86), every halfword (RISC-V), every word (ARM64); direct-branch targets; landing-pad patterns.
12. The audit extended to map counts (G14), and gate-word reset on reload (G13).

ABI and contract (`abi/`, `kernel-interface.md`):
- **Gate words:** their format in the machine table, read-only, in the frame of slot 13 beside the ownership words.
- **Grant table:** its format, plus a grant-use table per node. Both stay empty on one core, but their slots and layout are fixed now.
- **Layout field:** keep `StartOwnership.layout` (proposed by `ownership-alternatives.md`) as the hook for hardware tables (Smmpt) and for the monitor layer.
- **Start-up page:** flags for which mechanism is active, and whether control-flow protection is on.

---

## 12. Sources (retrieved 15 November 2026)

Intel and x86:
- Intel SDM vol. 3, 325384-093 (local extract): §2.5 CR0.WP and CR4.CET; §5.6.1–5.6.2 access rights, shadow-stack addresses, PKRS; §11.3 serializing instructions and its footnote on non-serializing MSRs; §34 SMM (Table 34-4, RSM checks). Index: https://www.intel.com/content/www/us/en/developer/articles/technical/intel-sdm.html
- CPUID dumps, InstLatx64:
  - i5-14600K https://raw.githubusercontent.com/InstLatx64/InstLatx64/master/GenuineIntel/GenuineIntel00B0671_RaptorLake_12_CPUID.txt
  - i9-13900K https://raw.githubusercontent.com/InstLatx64/InstLatx64/master/GenuineIntel/GenuineIntel00B0671_RaptorLake_01_CPUID.txt
  - other Raptor Lake and Alder Lake files in https://github.com/InstLatx64/InstLatx64/tree/master/GenuineIntel
- Intel community, PKS on 13th gen: https://community.intel.com/t5/Mobile-and-Desktop-Processors/PKS-Supervisor-Protection-Key-support-on-13th-intel/m-p/1476054
- Linux `cpufeatures.h`: https://raw.githubusercontent.com/torvalds/linux/master/arch/x86/include/asm/cpufeatures.h
- PKS:
  - CPU bit patch https://lkml.iu.edu/hypermail/linux/kernel/2201.3/08845.html
  - PKRS non-serializing https://lkml.rescloud.iu.edu/hypermail/linux/kernel/2201.3/10619.html
- Linux kernel IBT, `gen_endbr`: https://codebrowser.dev/linux/linux/arch/x86/include/asm/ibt.h.html
- Xen CET-SS, XSA-451: https://xenbits.xen.org/xsa/advisory-451.html
- IN pseudocode: https://www.felixcloutier.com/x86/in ; INVD: https://www.felixcloutier.com/x86/invd
- Ren et al., "An Analysis of Performance Evolution of Linux's Core Operations", SOSP 2019: https://www.seltzer.com/margo/teaching/CS508-generic/papers-a1/ren19.pdf
- Linux PTI documentation: https://docs.kernel.org/arch/x86/pti.html
- Intel VT-rp/HLAT (for the optional monitor): https://tandasat.github.io/blog/2023/07/05/intel-vt-rp-part-1.html

Papers on privilege separation inside the kernel:
- Dautenhahn et al., "Nested Kernel", ASPLOS 2015 (read in full): http://nathandautenhahn.com/downloads/publications/asplos200-dautenhahn.pdf
- Xie et al., "CETIS: Retrofitting Intel CET for Generic and Efficient Intra-process Memory Isolation", CCS 2022 (read in full): https://www.cs.wm.edu/~smherwig/readings/papers/22-ccs-cetis.pdf (DOI 10.1145/3548606.3559344)
- Azab et al., "SKEE", NDSS 2016 (read in full): https://www.ndss-symposium.org/wp-content/uploads/2017/09/skee-lightweight-secure-kernel-level-execution-environment-for-arm.pdf
- Cho et al., "Dynamic Virtual Address Range Adjustment for Intra-Level Privilege Separation on ARM" (Hilps), NDSS 2017 (read in full): https://www.ndss-symposium.org/wp-content/uploads/2017/09/ndss2017_05B-5_Cho_paper.pdf
- Proskurin et al., "xMP", S&P 2020. VMFUNC/altp2m; hypervisor-based, so relevant only to the optional layer (abstract and README): https://par.nsf.gov/servlets/purl/10149850 ; https://github.com/virtsec/xmp
- Steffin and Classen, "Modern iOS Security Features – A Deep Dive into SPTM, TXM, and Exclaves", arXiv 2510.09272 (background sections read): https://arxiv.org/pdf/2510.09272v1
- Apple Platform Security, PPL and SPTM: https://support.apple.com/guide/security/sec8b776536b/web
- Lee et al., "Keystone" (read in part): https://arxiv.org/pdf/1907.10119

Arm:
- Arm ARM DDI 0487 M.d (local extract): A2 feature versions (S1POE, S1PIE, THE, GCS, BTI, PAuth, HPDS, PAN, NMI); D8.2.7 Translation Hardening; D8 overlay and indirect permissions, TLB caching rules, UnprivWrite and PrivExecute; D11.5 GCS. https://developer.arm.com/documentation/ddi0487/latest
- Apple M1/M3/M4 feature table from ID registers: https://github.com/lelegard/arm-cpusysregs/blob/main/docs/apple-m1-features.md
- kpkeys page-table hardening:
  - v6 https://lkml.iu.edu/2602.3/07865.html
  - v7 batching https://lists.infradead.org/pipermail/linux-arm-kernel/2026-May/1126542.html
- QEMU Arm features emulated: https://gitlab.com/qemu-project/qemu/-/raw/master/docs/system/arm/emulation.rst

RISC-V:
- Privileged specification (local extract, machine.adoc, supervisor.adoc): https://github.com/riscv/riscv-isa-manual
- CFI chapter (Zicfilp, Zicfiss): https://docs.riscv.org/reference/isa/v20260120/unpriv/unpriv-cfi.html
- CVA6-CFI: https://arxiv.org/abs/2602.04991
- SPMP (Sspmp) specification: https://docs.riscv.org/reference/isa/extensions/sspmp/_attachments/riscv-spmp.pdf
- QEMU RISC-V extensions: https://gitlab.com/qemu-project/qemu/-/raw/master/target/riscv/cpu.c

Verification:
- Asterinas and CertiK, Verus: https://asterinas.github.io/2025/02/13/towards-practical-formal-verification-for-a-general-purpose-os-in-rust.html
- KVerus: https://arxiv.org/html/2605.03822v1
- verified-nrkernel: https://github.com/utaal/verified-nrkernel (seen through a mirror)
- Verus, SOSP 2024: https://dl.acm.org/doi/10.1145/3694715.3695952
- Syeda and Klein (title only): https://trustworthy.systems/publications/full_text/Syeda_Klein_20.pdf

Earlier DodOS reports (figures marked "verified in"): `research/drafts/fencing-without-cooperation.md`, `research/drafts/ownership-alternatives.md`.

**Not verified, used in the text:**
- the IRET shadow-stack check (SDM vol. 1);
- that page walks use physical addresses, so the linear type of a table page does not matter;
- PKRS being per logical processor;
- the x86 configuration and reset port numbers;
- menvcfg.CBIE (by analogy with senvcfg);
- Arm break-before-make details;
- Raspberry Pi-class cores lacking PAC and BTI;
- DRAM disturbance;
- peer-to-peer DMA paths;
- AMD's support for supervisor shadow stacks and PKS (AMD is not discussed in detail here).
