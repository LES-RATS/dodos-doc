# The gate call: entry, exit and events (version 4, draft, not normative)

Written 19 November 2026 by Gemini 4 Neon (high), building on version 3 by Claude Fable 5.2, as a design draft for the two owners. **Nothing here is a rule of the contract.** It replaces version 3 (commit `6be6a94`) and answers the attack on version 3 (document 6, findings V3-1 to V3-8) and the re-judgement of that attack (document 7, which decides where the two differ, adds ARGON-1 to ARGON-3, and proposes the uniform evacuate-and-free IST discipline). Head of the repository when written: `019947c`. The contract, kernel.md and D-120 are not touched.

It specifies, for x86-64 mechanism 2 (a translation root used only by the gate), for ARM64 and for RISC-V, what a gate call does from its first instruction to its last, and what happens to every event that can arrive at every instruction. It does not specify x86-64 mechanism 1; part B.2 says what that mechanism cannot do, for the owners' decision on D-120.

**Inputs, in order:** the review of the x86-64 gate's events (document 1); its re-judgement with the proposal called version 1 (document 2); the attack on version 1 (document 3); version 2 of this draft; the attack on version 2 (document 4, findings F1 to F15); the re-judgement of that attack (document 5, M1 to M6); version 3 (`6be6a94`); the attack on version 3 (document 6, findings V3-1 to V3-8); the re-judgement of that attack (document 7, ARGON-1 to ARGON-3); `architecture/kernel.md`; `architecture/kernel-interface.md` (G1 to G16, Gate words, lines 800 to 815, 1672, 1675, 2084); D-120, D-142, D-143, D-149 to D-153.

**Marks.**
- **[R]**: read by me in the primary source, in this pass or an earlier pass; the quotation is the manual's own text.
- **[J]**: read by document 5 or 7 with the manual open and not re-read by me.
- **[3]**, **[4]**: read by document 3 or 4 with the manual open and not re-read by me.
- **from memory**: no source opened.
- **UNVERIFIED**: not found or not read; the cell says what must be read.
- **(choice)**: a design choice, with the alternative rejected and its cost.
- **(estimate)**: my figure, measured nowhere.
- **OPEN**: a row I could not make sound; the options are in part D.

**Primary sources (title pages checked):** Intel SDM, order 325462-093US, September 2026 ("SDM"); Arm DDI 0487 M.d, 30 September 2026 ("Arm ARM"); Arm DEN 0054C, SDEI ("SDEI"); RISC-V privileged architecture, version 20240411 ("RISC-V priv").

---

## Changes from version 3

Each finding of documents 6 and 7, and each open row of version 3, with the place that answers it. (Version 2 → version 3 changes, F1 to F15, M1 to M6, OPEN-1, OPEN-3 and OPEN-5, remain in force except where superseded below: specifically, row G1 is replaced by the evacuate-and-free IST discipline.)

| Finding | What it was | Answered in | Status |
|---|---|---|---|
| V3-1 (a)–(d) | Row G1 failed four ways: second NMI at N0..N3 skipped saves into open window; second NMI overwrote IST1 frame before `#GP(0)`; `#GP` had no IST so its push at `F` faulted; `#GP` returned on the same `RFRAME_OF` | **Row G1 eliminated.** Uniform evacuate-and-free IST discipline (B.1.2, B.1.7, B.5.2): a `"continue"` `#MC` inside the NMI stub restores `SSP` via `WRSSQ`+`RSTORSSP`+`INCSSPQ 1` (or `CLRSSBSY` at `NMI_H2`), frees `IST3`, clears `MCIP`, and `JMP`s directly to `NMI_N4` (after copying `RAX/RCX/RDX` if in `NMI_N0..N3`) without `IRETQ`. NMI blocking is never lifted inside the NMI stub | Closed; trial T15 updated |
| V3-2 (a) | `#MC` cleared `MCIP` while `IST3` token was still busy; a second `#MC` in S0..S17 faulted `#GP(0)` | B.5.2 (`MC_SW0..MC_SW8` and `M0..M9`): `IST3` token is freed (`WRSSQ` or `CLRSSBSY`) and `SSP` switched off `IST3` (onto `MC_RSHSTK`, `MC_RSHSTK+24`, `SSP_nmi` or `PL0_SSP`) **before** `WRMSR 0x17A` clears `MCIP`. A second `#MC` in Range 2 preserves `IST_SAVE_MC` and `MC_RSHSTK` | Closed; trial T17 |
| V3-2 (b) | `#MC` checked `CR3 == GATE_PCID` (N9) before running B.5.2, so an SRAR/PCC/MCIP=0 `#MC` while open skipped the verdict | B.5.2: bank scan, verdict, sticky Row-7 latch, bank log/clear, `IST3` release and `MCIP` clear run **before** dispatching open vs closed return | Closed |
| V3-2 (c) | `#MC` copied context off `IST3` only for returns outside gate text; a second `#MC` after Step 5 clobbered `IST3` for open-window and closed-gate returns | B.1.2, B.5.2: `IST_SAVE_MC` (on shadow-stack-typed `RFRAME_OF`) captures the frame, saved registers and shadow-stack words for **all** `"continue"` returns before `MCIP` is cleared | Closed |
| V3-3 (a) | NMI between Step 4 bank clear and Step 5 restarted at N4 with `VAL = 0`, downgrading Row 7 (CPL-3 SRAR) to Row 10 ("continue") | B.5.2: `row7_sticky` latched in `IST_SAVE_MC` (via `WRSSQ`) **before** Step 4 clears any owned bank; cleared at `M1` after Step 4 | Closed |
| V3-3 (b) | NMI between Step 4 log-index `WRSSQ` and bank-clear `WRMSR` wrote a duplicate log record against line 852's claim | B.5.2, B.5.3 item 4: false "written once" claim removed; index advances before `WRMSR` so no record is ever lost, and B.5.3 item 4 explicitly tolerates a duplicate from a nested NMI restart | Closed |
| V3-3 (c) | A later `"continue"` `#MC` clobbered `MCBLOCK_OF` before `kernel_mc_user` finished reading it | B.1.2, B.5.2: Row 7 writes a dedicated `MCUSER_BLOCK_OF`; `"continue"` `#MC` writes only `IST_SAVE_MC` on `RFRAME_OF` and never touches `MCUSER_BLOCK_OF` | Closed |
| V3-4 | `#DB` at `N0` of an IDT stub was F, so user `MOV SS` + data watchpoint + `INT3`/`UD2`/`#PF`/`#DE`/`#GP` panicked a healthy node | V12 item 4, B.1.7: `#DB` at `N0` (`ENDBR64`) of any IDT stub with `CR3` not open and `DR6.{BS,BD,BT} == 0` is **D** (record/reset `DR6`, `RFLAGS = 2`; at `NMI_N0` no-`IRETQ` jump to `NMI_N4`). `N1..S17` and `BS/BD/BT != 0` stay **F** (F2 remains closed) | Closed; trial T18 |
| V3-5 | Misbehaving kernel could leave `IST1`, `IST2` or `PL0_SSP` busy via `JMP L0`/`Y0`/`U0` from CPL-3 IST handlers | B.1.7, B.1.8, B.1.9, B.5.2: every CPL-3 IST handler (`NMI`, `#DB`, `#MC` Row 7) evacuates to its user block, frees `ISTk` (`CLRSSBSY`), acquires `PL0_SSP` (`SETSSBSY`), then jumps to kernel text. `U0` checks `SSP == PL0_SSP_OF`; `Y0` splits into Range 1 (`SSP == PL0_SSP_OF`, `CLRSSBSY`, `JC T0`) and Range 2 (reloads block, re-checks canonical RIP, `SYSRETQ`) so NMI after `Y13` never causes a false `JC T0` panic | Closed |
| V3-6 (a), (b) | `DR7.GD` and `R/Wn = 10` (I/O breakpoints) not forbidden; dev-image `DR0..DR3` exclusion missed gate private view, unit tables, clock page, `parked` and crash area | B.1.5 (`[R]` SDM vol. 3B §20.2.4), D.4 item 9: `DR7.GD = 0` and `R/Wn != 10` required in all builds; full gate private view (and table-page clearing through it) plus unit tables, clock page, `parked` and crash area excluded | Closed |
| V3-7 (a)–(g) | (a) `IA32_STAR`/GDT layout omitted; (b) `Y7` hardcoded 4-level `47` and `SYSRET` `#GP(0)` from memory; (c) `F` at offset 0 of `RFRAME_OF` let `#GP(0)` push into preceding page; (d) `N9` missed `T0..T26`; (e) `I15`/`M9` omitted from V12 item 5; (f) B.1.7 allowed `K` only at `P0/P1`; (g) Property 5 missed sibling corrupting saved `RDX` at `E0..E3` | (a) B.1.5, D.4 item 4 (`[R]` SDM vol. 2B `SYSCALL`/`SYSRET`); (b) B.1.9 `Y18` (`47`, or `56` if `CR4.LA57 = 1`, `[R]`); (c) B.1.2 (`F` at offset 64 of `RFRAME_OF`, `[R]` Table 7-5); (d) B.1.7 `N9`; (e) V12 item 5, B.1.7; (f) B.1.7; (g) Part E Property 5 | Closed |
| V3-8 (a)–(d) | ARM64: (a) missing `GCSCR_ELx.PCRSEL`, `SCR_EL3.GCSEn`, `HCRX_EL2.GCSEn`; (b) `Y4′` omitted beside `Q7`; (c) `POR_OPEN` must not set `PrivExecute` (`RQXXPC`); (d) `HCR_EL2`/`HCRX_EL2` omitted from D.4 item 10 | (a) B.3 (`[R]` Arm ARM D11.2.1 `RBYVYL`/`RWFTRC`); (b) B.3.3; (c) B.3.3 (`[R]` Arm ARM `RQXXPC`); (d) D.4 item 10 | Closed |
| ARGON-1 / OPEN-2 | `T9..T25` left `IST1..IST4` busy when entered with multiple frames; later NMI/`#DF` at `park` triple-faulted | B.1.10 (`T6..T15`): unconditionally clears `IST1..IST4` tokens via four `WRSSQ` instructions and switches `SSP := PARK_RSHSTK` via `WRSSQ`+`RSTORSSP`+`INCSSPQ 1` before clearing `MCIP` and before `T26: IRETQ`. `CALL T9` loop removed; all four IST tokens guaranteed free at `park` | **OPEN-2 Closed**; trial T19 |
| ARGON-2 | `L1` (line 382) and `T15` (line 562) contradicted each other on `SSP = 0` | B.1.8, B.1.10 (`[R]` SDM vol. 2A `INT n`, vol. 3A Table 7-5, vol. 2B `RSTORSSP`): non-IST faults at `SSP = 0` fault during IDT delivery (`0xFFFF_FFFF_FFFF_FFFC` → `#PF` → `#DF` on `IST4`); direct jumps to `T0` with `SSP = 0` (from `Y13a`/Range 2) are handled directly by `T14: RSTORSSP` without dereferencing old `SSP` | Closed |
| ARGON-3 | `T7` jumped into B.5.2 without specifying register/`RSP` handling | B.1.10 (`T16`): self-contained helper `mc_check_stop_or_clear_mcip` checks B.5.2 Rows 2–5 for `"stop the machine"`, else clears `MCIP` (`WRMSR 0x17A`) and jumps to `T17` | Closed |
| OPEN-6 | `POP`/`IRETQ` reading from a shadow-stack-typed page was `[4]` / open | B.1.2, B.1.9, D.1: verbatim `[R]` from SDM vol. 3A §5.6.1 confirms ordinary supervisor data reads (implicit and explicit) from shadow-stack pages are permitted; trial T13 stays as hardware confirmation only | **OPEN-6 Closed** |
| OPEN-8 | ARM64 `POR_EL1` read-write encoding and `isb` requirement were unverified | B.3.3, D.1: verbatim `[R]` from Arm ARM Table D8-74, D24.2.150 (`0b0101` = Read+Write) and D24.1.2.2 (`isb` mandatory at `Q8` and `Y5′`) | **OPEN-8 Closed** |
| OPEN-4 | Broadcast machine checks: shared-bank clearing race, no-error detection, second `#MC` while `MCIP = 1` | B.5.2, D.1 item 1 | Still **OPEN** |
| OPEN-7 | VT-d compatibility-format control name and PCI bridge bus-renumbering primary citations | B.1.9, B.1.12, D.1 item 2 | Still **OPEN** |

---

## A. The threat and the promise

1. **Held against a faulty kernel on every core of its node**, on the three architectures. The kernel may call the gate with any register values, any flags, any stack pointer, from any of its cores at once, and may write any page it maps writable at any time.
2. **Held against an adversarial kernel on x86-64 only, and only with every precondition below.** On ARM64 and RISC-V no shipping core lets it be held (the table below).
3. **Held against the node's devices**: no page the sequence relies on can be the target of an iospace leaf or a user leaf (B.1.2), and no device can signal an exception vector, an NMI or an INIT to another node's core (B.1.12).
4. **The promise:** no kernel instruction runs while the gate's root is loaded; every store the gate makes is one the rules G1 to G16 allow; every privileged instruction of gate text runs with operands computed in the same run (V12); a call completes once or not at all; no event is lost unless the node's own kernel clears its own pending word.
5. **The cost of the promise is availability of the faulty node only**: a kernel can make its own gate calls restart for ever, and can get its own node declared fatal.

**Preconditions of the adversarial promise on x86-64.** Each is a start-up check; a machine that fails one runs flagged, as a machine without control-flow protection does today.

| # | Precondition | Why | Where |
|---|---|---|---|
| 1 | Supervisor shadow stacks and IBT on, with the field values of B.1.5 | A wild entry is caught only then; `NO_TRACK_EN` = 1 removes the check | B.1.5 |
| 2 | Variant (a) or (c) of B.1.9 taken | Otherwise any kernel reaches every I/O port through IOPL | B.1.9 |
| 3 | Interrupt remapping on, with compatibility-format messages blocked | Otherwise a device the node drives sends vector 18, an NMI or an INIT to any core | B.1.12 |
| 4 | Every vector that hardware can signal is composed by the gate (ICR, LVT, IOAPIC and remapping entries) | Row 1 of B.5.2 and "INIT is the fence" rest on it | B.1.11, B.5.2 |

**What holds on each architecture.**

| Architecture, hardware features | What holds today | What would close it |
|---|---|---|
| x86-64, shadow stacks and IBT, the four preconditions | Adversarial kernel, as far as part C shows and the model of part E confirms | — |
| x86-64, shadow stacks and IBT, a precondition missing | Faulty kernel only | The precondition |
| x86-64 without CET | Faulty kernel, by improbability | CET |
| ARM64, any shipping core, **with or without BTI** | **Faulty kernel only**, by improbability. BTI does not change it: "Any other instruction \| Any \| Any register \| 0b00" (Arm ARM, Table D8-85 [R]), so a `RET` reaches any instruction of gate text with BTYPE = 0, and an `ERET` takes `SPSR_ELx.BTYPE`, which the kernel writes | FEAT_GCS with BTI (no shipping core), or a gate one exception level above the kernel (B.7) |
| ARM64 with FEAT_GCS and BTI | Adversarial kernel possible, not shown: B.3.2 is not re-walked with it | The re-walk, under the conditions of B.3 |
| RISC-V, any core | **Faulty kernel only**. `sret` jumps to `sepc`, which the kernel writes; a plain return is unchecked. That Zicfilp does not track a return, and Zicfiss checks only where code executes its check: from memory (neither extension is in the edition read) | A gate in a mode above the kernel (B.7), or a scan-enforced discipline on every return |

**The residue no sequence of this kind closes.**

| # | Item | Should the contract name it as outside the promise? |
|---|---|---|
| 1 | Transient execution: nothing here bounds what one node reads of another by speculation, in the gate's text included | Yes |
| 2 | SMM and firmware (EL3, machine mode), which see every state, an open window included | Already named |
| 3 | The processor's behaviour where the manual is silent, and errata: the platform's response to one core in shutdown, a core in wait-for-SIPI at a machine check | Yes, as a class, with the trials of part D |
| 4 | A machine without control-flow protection | Already flagged; the sentence should say that on ARM64 and RISC-V the flag changes nothing |
| 5 | The gate's own code and the scanner | Already named |
| 6 | Broadcast machine checks and banks shared across nodes (OPEN-4) | Yes |
| 7 | Platform effects outside the IOMMU and the gate: PCIe fatal errors, device resets, thermal or power events, shared buses of the `platform` role | Yes, one sentence |
| 8 | Availability across nodes through shared hardware: cache and memory-bandwidth pressure, bus locks; and rowhammer, which is an integrity threat the gate does not hold | Yes |
| 9 | Out-of-band engines with physical memory access (management engine, BMC, external debug) | Yes, beside firmware |
| 10 | A return and an exception return used as a jump on ARM64 and RISC-V (N4, F7) | Yes: it is the table above |
| 11 | A core with CR4.MCE clear (between INIT and the park stub) at a broadcast machine check | Yes if trial T9 confirms it. One unknown is left: INIT does clear CR4 (B.5.2) |
| 12 | A machine without interrupt remapping (M3) | Yes, as a flagged machine |
| 13 | Port I/O through IOPL, if variant (b) of B.1.9 is taken | Yes, and B.1.9 says what that sentence gives away |

---

## B. The specification

### B.0 Cell codes

| Code | Meaning |
|---|---|
| **no** (reason) | Cannot occur. If it occurs all the same, the stub treats it as **F** |
| **R** | Restart. The stub marks the event pending and returns to the first instruction of the restart range the interrupted address lies in (an entry's first row, a stub's redo label, `MC_SW0`, `MC_R2_0`, `M0`, `M5`, `Y14`, `T0`). No kernel instruction runs |
| **D** | Deferred. The stub marks the event pending and returns to the interrupted instruction. Allowed only on the rows V12 lists as harmless, and anywhere while the window is open (except `T0..T26`, `MC_SW0..MC_SW8`, `MC_R2_0..MC_S17`, which are **R**) |
| **F** | Fatal to the node (B.1.10) |
| **FW** | Firmware's. It runs and returns to the interrupted instruction, or never returns; no kernel code runs |
| **K** | The kernel's handler runs and returns to the same instruction. Allowed only at rows where nothing trusted has been computed |
| **MC** | By the machine-check rule (B.5): the stub stops the machine, or declares the node fatal, or clears MCIP and then acts as the NMI cell of the same row (returning without `IRETQ` if interrupting the NMI stub) |

INIT is **F** in every row of every x86-64 table: it is sent only by a fence (G10, and precondition 3), the call is abandoned, and G12 (2) with G13 cover a call left half done. SMI is **FW** in every row.

### B.1 x86-64, mechanism 2

#### B.1.1 Rules

- **V1. No kernel instruction runs between a call's opening instruction and its closing instruction.** An event there is deferred in a stub, is fatal, or is firmware's. (Choice. Rejected: "save, run the kernel's handler, restore"; its cost is a kernel that runs in the middle of a call while the gate lock is held.)
- **V2. All 256 IDT vectors are interrupt gates whose target is a gate stub.** "Accessing a handler procedure through a trap gate does not affect the IF flag" (SDM vol. 3A §7.12.1.3 [R]). Every descriptor has DPL 0, except vector 3 (DPL 3), so that a user `INT3` stays a breakpoint (choice).
- **V3. An event whose interrupted address lies in gate text is never given to the kernel.** The stub handles it by **R**, **D** or **F**. The one exception is maskable interrupts at the first two instructions (`ENDBR64`, `CLI`) of an entry (cell **K**).
- **V4. Open means "CR3 holds the reserved tag".** A stub reads CR3 and compares bits 11:0 with `GATE_PCID`. (Choice. Rejected: version 1's flag page, whose answer is a TLB lookup.)
- **V5. The interrupted address is read from the shadow stack, never from the frame** ("pushes the CS, LIP (CS.base + EIP), and SSP of the interrupted procedure", §7.12.1.1 [R]).
- **V6. Whether the event came from CPL 3 is read from SSP by exact token equality** (B.1.7).
- **V7. A stub spills nothing trusted.** A stub stores to its stack only the interrupted context's registers, in fixed slots (V12, item 3). Their corruption harms the interrupted context alone, **which is why no interrupted context inside gate text is resumed with the registers it had (V12)**. Per-core stub scratch that must survive across a nested event (`IST_SAVE_MC`, `MC_RSHSTK`, `PARK_RSHSTK`) lives on the shadow-stack-typed `RFRAME_OF` page, written by `WRSSQ` only. No stub makes a `CALL` (and neither does the fatal path).
- **V8. A completed call is never run again.** No instruction at or after the opening `MOV CR3` is in a restart range of the entry.
- **V9. Nothing that differs between the gate's root and the kernel's roots is global** (B.1.3).
- **V10. The gate returns with IF = 0, DF = 0, and the arithmetic flags undefined.** A healthy kernel calls with IF = 0. (Choice; seL4 runs its whole kernel with interrupts off: from memory.)
- **V11. A windowed call reads its arguments from registers only.** The return entries of B.1.9 read a per-core block instead; they open no window and decide nothing trusted from it.
- **V12. While the window is closed, no instruction of gate text is resumed with registers it did not load in the same run.** (Document 5's rule, taken whole.)
  1. Gate text that can run closed is made of **restart ranges** and of **listed harmless rows**. An NMI or a machine check in a restart range returns to the range's first instruction. After that first instruction the range loads every register that a privileged instruction of the range uses (`MOV CR3`, `WRMSR`, `WRSSQ`, `RSTORSSP`, `INCSSPQ`, the RSP of an `IRETQ`, `CLRSSBSY`, `OUT`) or that a trusted comparison uses.
  2. Each stub, from its redo label to its last instruction inclusive (except its harmless CPL-3 handoff rows `H2..H3`), is one restart range. The `#MC` stub is split into restart ranges around its irreversible transitions: Range 1a (`MC_N4` through Step 4), Range 1b (`MC_SW0..MC_SW8`, freeing `IST3`, switching `SSP` and clearing `MCIP`), Range 2 (`MC_R2_0..MC_S17` and the direct no-`IRETQ` NMI return jumps `MC_JNMI_*`), and for Row 7, Range 1b-a (`M0..M3`) and Range 1b-b (`M5..M8`) separated by harmless row `M4` (`SETSSBSY`) and followed by harmless row `M9` (`JMP kernel_mc_user`) (B.5.2). `ret_user_fast` is two ranges: `Y0..Y13a` and `Y14..Y21` (B.1.9). The fatal path `T0..T26` (including `mc_check_stop_or_clear_mcip`) is one restart range. `ret_user` (`U0..U24`) and `ret_kernel` are one range each.
  3. So that a range can run twice, a stub saves the interrupted context's registers by `MOV` into fixed slots, not by `PUSH`: above the processor's frame for a vector with an IST index (the IST pointer leaves three slots free above it), below the stack pointer otherwise.
  4. **A `#DB` whose interrupted address is in gate text is R in P0 to P7 and in the restart range of a short entry or of a return entry, D at L0 to L2, at E0 to E3, and at `N0` (`ENDBR64`) of any IDT stub when `CR3` is not open and `DR6.{BS,BD,BT} == 0` (a deferred `MOV SS`/`POP SS` data watchpoint), and F everywhere else.** (Inside `N1..S17` of a stub, or with `BS = 1`, it cannot arise honestly: delivery clears `TF`, `MOV SS` suppresses `TF`, `DR7.GD = 0`, and no breakpoint covers gate text. At `L0` or `N0` of an IDT stub a user thread's `MOV SS` + data watchpoint + `SYSCALL`/`INT3`/`UD2`/`#PF`/`#DE`/`#GP` can deliver a trap-class `#DB` with `BS = BD = BT = 0`. At `E0..E3` it can arise under variant (b) if a sibling wrote `TF` into a frame.)
  5. The harmless rows, each with its reason: `E0` (`MOV RSP, R11`, a caller's value); `E1` (a read); `E2` and `E3` (they return to `E1`); `I14`, `I15` (`MOV EAX, REFUSED`), `I16` and the `RET` of any short entry; `L0` and `L2` (no operand); `L1`, `NMI_H2`, `DB_H2` and `M4` (`SETSSBSY`, whose only operand is `IA32_PL0_SSP`); `NMI_H3`, `DB_H3` and `M9` (direct `JMP` to `kernel_nmi`/`kernel_db`/`kernel_mc_user`, no operand); the rows of a stub before its redo label (`N0..N3`, which store the context's own registers without altering `RAX/RCX/RDX`); the park loop.
- **V13. Every transition to CPL 3 loads RFLAGS from a value the gate masked in a register, and no `IRETQ` pops a frame that a store outside gate text can reach.** This is variant (a) of B.1.9. Under variant (b) the rule is absent and port I/O through IOPL is outside the promise.

#### B.1.2 Memory

"Twin" means two physical pages at one linear address: one under the kernel's roots, one under the gate's root.

| Page | Linear address | Under the kernel's roots and every aspace root | Under this core's gate root | Global | Class in the contract's terms |
|---|---|---|---|---|---|
| Gate text: entries, stubs, the system-call rows, the park loop | Same on all cores | Read, execute | Read, execute, same page | May be | *global read-only* (kept image). In pages apart from kernel text |
| Read-only gate tables, one entry per core unless said: `ROOTS` (the gate root's value with `GATE_PCID` and bit 63), `PL0_SSP_OF`, `IST1_SSP_OF` to `IST4_SSP_OF` (each IST's shadow-stack token address), `ISTTOP_OF` (for each IST vector, the stack pointer its stub starts with), `RFRAME_OF`, `RBLOCK_OF`, `NMIUSER_BLOCK_OF`, `DBUSER_BLOCK_OF`, `MCUSER_BLOCK_OF`, `APICID_OF`, and the text-range table (one for the node) | Same | Read | Read, same page | May be | *global read-only*; written at node start-up |
| IDT, GDT, TSS, the interrupt SSP table | Per core | Read | Read, same page | May be | kept, written once at start-up (kernel.md) |
| Gate root of core *c* and its private tables | Not mapped as data in any kernel view | Not mapped | The gate's window on table pages | No | *kernel table* (kept, fixed) |
| Gate stack of core *c* | `GATE_STACK`, same on all cores | Not present | Read, write | No | *gate* (kept memory of the gate) |
| IST1 to IST4 stacks of core *c* (NMI, #DB, #MC, #DF), **kernel side** | Per core: IST pointers of core *c*'s TSS | Read, write | — | No | kept memory, "the kernel's own stacks" (start-up memory rule 1) |
| The same four stacks, **gate side** | The same four addresses | — | Read, write; other cores' IST addresses not present | No | *gate* |
| Shadow stacks of IST1 to IST4 of core *c*, each with its token | Per core | Shadow-stack page (R/W 0, dirty 1) | The same page, same typing | May be | *gate* ("the kernel's shadow stacks", G2) |
| The kernel's shadow stack of core *c* (`IA32_PL0_SSP`), with its token | Per core | Shadow-stack page | The same | May be | *gate* |
| Pending word of core *c*, and its deferred-DR6 word | `KPEND + 16c`, in one page per node | Read, write | Read, write, same page | No | kept memory of the node, kernel-writable |
| **Return-frame and IST-scratch page** of core *c* (`RFRAME_OF`, 4 KB): `F` (at offset `0x40`), `IST_SAVE_MC` (`0x180`), `MC_RSHSTK` (`0x280`), `PARK_RSHSTK` (`0x2C0`) (layout below) | Per core (`RFRAME_OF`) | Shadow-stack page (R/W 0, dirty 1): readable, written by `WRSSQ` / `RSTORSSP` only | The same page, same typing | May be | *gate* |
| **Return block** of core *c* (`RBLOCK_OF`, 7 words: RAX, RCX, RDX, R11, RIP, RFLAGS, RSP) and the **three CPL-3 IST user-context blocks** (`NMIUSER_BLOCK_OF`, `DBUSER_BLOCK_OF`, `MCUSER_BLOCK_OF`, 6 words each: RAX, RCX, RDX, RIP, RFLAGS, RSP) | Per core, in one page per node | Read, write | Not needed | No | kept memory of the node, kernel-writable |
| **Machine-check log** of core *c*: a ring of records and its write index | Per core, in pages of the node | Shadow-stack page: readable, written by `WRSSQ` only | The same | May be | *gate* |
| The node beacon (`panic`) | As today | Read, write | Read, write, same page | No | as today |
| Kernel text, kernel data, the kernel's stacks | As today | As today | **Not present** | **No** | as today |
| Table pages, the living part, the gate part, unit registers | The gate's own addresses | Read only, or not present (unit registers: G9) | Read, write | No | as today |

- **Per-core `RFRAME_OF` page layout** (base `F_BASE`, 4 KB aligned, shadow-stack page under both kernel roots and gate root, written by `WRSSQ` and `RSTORSSP` only — zero extra pages beyond version 3, and tamper-proof by sibling cores under every root):
  - `F_BASE + 0x000..0x03F` (64 B): read-only guard zone below `F` inside `RFRAME_OF`. **V3-7 (c):** because `F = F_BASE + 0x040`, a `#GP(0)` at `U24` or `S17` (`RSP = F + 8`, e.g. non-canonical user RIP) attempts to push its 6-word frame at `F + 8 - 48 = F_BASE + 0x018..F_BASE + 0x047`, strictly inside `RFRAME_OF` (never crossing into the preceding page). That ordinary store hits `R/W = 0` with `CR0.WP = 1` → `#PF`; by SDM vol. 3A Table 7-5 [R] (Contributory + Page Fault → Handle Exceptions Serially; Page Fault + Page Fault → Generate a Double Fault), the processor delivers `#PF` on the same `RSP = F + 8`, faults a second time on `RFRAME_OF`, and delivers `#DF` on `IST4` → `T0`.
  - `F_BASE + 0x040..0x06F` (`F`, 48 B = 6 words): `IRETQ` return frame (`[F+0]` saved RAX; `[F+8]` RIP; `[F+16]` CS; `[F+24]` RFLAGS; `[F+32]` RSP; `[F+40]` SS).
  - `F_BASE + 0x180..0x1FF` (`IST_SAVE_MC`, 128 B): per-core `#MC` capture block (written by `WRSSQ` only): `rip`, `rflags`, `rsp`, `rax`, `rcx`, `rdx`, `old_ssp`, `old_lip`, `target_ssp`, `return_mode` (open-continue / closed-gate / kernel-continue / cpl3-continue / jmp-nmi-n4 / jmp-nmi-h2 / jmp-nmi-h3), and `row7_sticky` (initialized to 0 at start-up; latched to 1 before Step 4 clears any owned bank on Row 7; cleared to 0 at `M1`).
  - `F_BASE + 0x278..0x29F` (`MC_RSHSTK` at `F_BASE + 0x280`, 32-byte aligned): `[MC_RSHSTK - 8]` restore-SSP token scratch slot; `[MC_RSHSTK + 0..23]` 3-word shadow frame (`old_ssp`, `return_lip`, `KERNEL_CS`) for CPL-0 `"continue"` `#MC` `IRETQ`; `[MC_RSHSTK + 24]` valid supervisor shadow-stack dummy slot (`MC_RSHSTK + 24`, free) used both as the `SSP + 24` target of CPL-0 `IRETQ` and as `SSP` for CPL-3 `"continue"` `IRETQ` (B.5.2).
  - `F_BASE + 0x2B8..0x2DF` (`PARK_RSHSTK` at `F_BASE + 0x2C0`, 32-byte aligned): `[PARK_RSHSTK - 8]` restore-SSP token scratch slot; `[PARK_RSHSTK + 0..23]` 3-word shadow frame (`PL0_SSP`, `park`, `KERNEL_CS`) for `T26: IRETQ` (B.1.10); `[PARK_RSHSTK + 24]` dummy supervisor shadow-stack slot.
- **No iospace leaf and no user leaf can target any of these pages.** G3 (2) lets a leaf target an owned chunk, the floor, a grant, the global read-only set or a device entry; kept memory is none of them, and a *gate* page is refused by G3 (3). This is document 3's answer to N2 and needs no new stored class. G2's list of what the class *gate* covers should name the gate stack, the gate-side interrupt stacks, the return-frame/scratch pages and the machine-check log, and say that the kernel-side interrupt stacks are kept memory (a wording change for the contract, not a new rule).
- **Token placement.** Each address in the interrupt SSP table and `IA32_PL0_SSP` satisfies `(address AND 1FH) = 18H`, holds a token equal to the address with bit 0 clear, and is the highest slot of its stack, below a guard page. The processor requires it: "Token and CS:LIP:oldSSP pushed on shadow stack must be contained in a naturally aligned 32-byte region ... IF (NewSSP & ~0x1F) != ((NewSSP – 24) & ~0x1F) #GP(0)" (SDM vol. 2A, `INT n`, pseudo-code of the 64-bit gate [R]). Each IST shadow-stack page has at least 64 bytes of valid supervisor shadow-stack space below the token, so `[ISTk_TOKEN - 32]` (for CPL 0, `SSP = ISTk_TOKEN - 24`) and `[ISTk_TOKEN - 8]` (for CPL 3, `SSP = ISTk_TOKEN`) are always free supervisor shadow-stack slots for `RSTORSSP`.
- **The slots above an IST frame.** Each IST pointer of the TSS lies three slots below the top of its stack, on both sides, so that a stub's three saved registers lie above the processor's frame (V12, item 3).
- **Pages typed as shadow stacks and written by `WRSSQ` (OPEN-6 closed [R]).** `RFRAME_OF` and the machine-check log must be written by gate text under both kernel roots and the gate root, with no `CR3` switch; an ordinary store cannot reach them from any core (`CR0.WP = 1`, `R/W = 0`), and `WRSSQ`/`RSTORSSP` exist only in gate text. They take no compare-and-swap and hold no device register, so the three facts of B.2 do not bear on them. That `IRETQ` and `POP` read their operands from such a page is explicitly authorized by SDM vol. 3A §5.6.1 ("Access Rights", pp. 5-33–5-34 [R]):
  > "Shadow-stack accesses are allowed only to shadow-stack addresses. A linear address is a shadow-stack address if the following are true of the translation of the linear address: (1) the R/W flag (bit 1) is 0 and the dirty flag (bit 6) is 1 in the paging-structure entry that maps the page containing the linear address; and (2) the R/W flag is 1 in every other paging-structure entry controlling the translation of the linear address."
  > "For supervisor-mode accesses: — Data may be read (implicitly or explicitly) from any supervisor-mode address with a protection key for which read access is permitted."
  `POP` and `IRETQ` are implicit supervisor-mode data reads, so OPEN-6 is closed by the manual; trial T13 remains as a hardware confirmation check.
- **The last page of the address space is never a shadow-stack page**, and nothing is mapped there, so that any non-IST delivery with `SSP = 0` always faults at `0xFFFF_FFFF_FFFF_FFFC` (`#PF` → `#DF` on `IST4`, B.1.8 and B.1.10).
- **Why per-core gate roots (choice).** With one root per core, `GATE_STACK` is one immediate in shared text. The alternative, one gate root per node with per-core addresses for everything, saves a top-level table per core and costs a table lookup before the stack can be used. All gate roots of a node share every subtree except the private one.
- **Why the pending word is kernel-writable (choice).** A stub that interrupts a prologue runs under the kernel's root and can write no gate page; and the kernel must take the bits without a gate call. The gate never decides anything trusted from the word: at exit it only chooses between `RET` and a jump to a kernel routine. Rejected: version 1's gate-only word, which cannot record an event taken before the opening instruction. Cost of the choice: "no event is lost" holds only for a kernel that does not clear its own word.

#### B.1.3 Tag reservation and the TLB

- **The tag table of G7 loses one tag.** `GATE_PCID` = 4095 is bound to no root by `bind`, so the x86-64 table holds tags 0 to 4094. Document 3's break 4A needs a user root under the gate's tag; this removes it. This is a change to the contract's "min(2^(tag width), 4,096) entries".
- **Why a tag separates the two views.** "When using entries in the TLBs and paging-structure caches to translate a linear address, a logical processor uses only those entries associated with the current PCID (see Section 5.10.2.4 for an exception)" (SDM vol. 3A §5.10.1 [R]). The exception: "A logical processor may use a global TLB entry to translate a linear address, even if the TLB entry is associated with a PCID different from the current PCID" (§5.10.2.4 [R]). Hence V9.
- **Open:** `MOV CR3` with the gate root, `GATE_PCID` and bit 63 set. "If CR4.PCIDE = 1 and bit 63 of the instruction's source operand is 1, the instruction is not required to invalidate any TLB entries or entries in paging-structure caches" (§5.10.4.1 [R]). Nothing needs flushing: an entry under `GATE_PCID` on this core was made under this core's gate root.
- **Close:** `MOV CR3` with the saved root and tag and bit 63 set. "The instruction does not modify bit 63 of CR3, which is reserved and always 0" (SDM vol. 2B, `MOV` to control registers [R]), so the value read at entry has bit 63 clear and the exit sets it.
- **When the gate root's own mappings change** (unit registers at a role hand-over or take-over): the node keeps a view epoch in its gate part; each core compares it with its own copy at the first step of the body and, if they differ, executes `INVPCID` type 1 for `GATE_PCID`: "the logical processor invalidates all mappings—except global translations—associated with the PCID specified" (§5.10.4.1 [R]). A mapping only added needs nothing: "there can be a TLB entry for a page number only if the P flag is 1" (§5.10.2.3 [R]).
- **An invalidation the call owes on this core** for the caller's tag is made inside the window by `INVPCID` type 0 or 1 naming that tag, or by closing with bit 63 clear: "the instruction invalidates all TLB entries associated with the PCID specified in bits 11:0 of the instruction's source operand except those for global pages" (§5.10.4.1 [R]).
- **Without PCID** (`CR4.PCIDE` = 0) every CR3 write flushes the non-global entries, which is correct and slower, and V4 compares CR3's address bits with `ROOTS`. The reference processor has PCID (kernel.md).
- **Not relied on:** "MOV to CR3 may invalidate TLB entries for global pages" (§5.10.4.1 [R]).

#### B.1.4 The entry sequence

Registers at `P0`: the call's arguments in RDI, RSI, RDX, R8, R9, R10; RAX, RCX and R11 are the gate's (the caller loses them). Stack: the caller's `CALL` pushed the return address on its stack and on its shadow stack.

Columns: **Mask** maskable interrupt; **#MC-L** machine check with `LMCE_S` = 1; **#MC-B** broadcast machine check; **#DB-TF** single step; **#DB-BP** breakpoint; **Fault** a fault of this instruction.

| Row | Instruction | Holds after it | Mask | NMI | #MC-L | #MC-B | #DB-TF | #DB-BP | Fault | SMI | INIT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| P0 | `ENDBR64` | Nothing trusted | K | R | MC | MC | R | R | no (no operand) | FW | F |
| P1 | `CLI` | IF = 0 | K | R | MC | MC | R | no (text and stack excluded, B.1.5) | no (CPL 0) | FW | F |
| P2 | `CLD` | DF = 0 | no (IF = 0) | R | MC | MC | R | no | no | FW | F |
| P3 | `RDPID RAX` | RAX = this core's number | no | R | MC | MC | R | no | no (`#UD` only if absent: start-up check) | FW | F |
| P4 | `MOV RAX,[ROOTS+RAX*8]` | RAX = this core's gate root, tag, bit 63 | no | R | MC | MC | R | no (`ROOTS` excluded) | no (table present by construction); else F | FW | F |
| P5 | `MOV RCX,CR3` | RCX = caller's root and tag (trusted: only the gate writes CR3) | no | R | MC | MC | R | no | no | FW | F |
| P6 | `MOV R11,RSP` | R11 = caller's RSP (a value, never dereferenced) | no | R | MC | MC | R | no | no | FW | F |
| P7 | `MOV CR3,RAX` | **Open.** Kernel text not mapped | no | R (before it executes) | MC | MC | R | no | no (value built at start-up); else F | FW | F |
| W0 | `MOV RSP,GATE_STACK_TOP` | RSP on this core's gate stack | no | D | MC | MC | no (below) | no | no (no memory operand) | FW | F |
| W1 | `PUSH RCX` | Caller's root saved privately | no | D | MC | MC | no | no | no (page present by construction); else F | FW | F |
| W2 | `PUSH R11` | Caller's RSP saved privately | no | D | MC | MC | no | no | as W1 | FW | F |

- **`RDPID`** reads `IA32_TSC_AUX`, which only `WRMSR` writes [3]; the gate writes it once per core at start-up.
- **Maskable interrupts cannot arrive after P1.** IF is cleared at P1. A stub returns into an entry only at P0 (cell R), and a return by the kernel (through `ret_kernel` under variant (a) of B.1.9, by its own `IRETQ` under variant (b)) can reach gate text only at P0 or P1 (the two K cells), because the return address is compared with the shadow stack (§7.12.1.1 [R]) and no other gate address was ever pushed for a kernel handler. Document 5 walked this last sentence and found it sound, given an SSP that is always aligned, which is why `INCSSP` leaves kernel text (D.4). So every path to P2 passed P1 with no later change of IF.
- **`STI` then a jump or call to P0.** The interrupt is held for one instruction ("Nonmaskable interrupts and system-management interrupts may also be inhibited on the instruction boundary following such an execution of STI", §7.8.1, note [R]) and arrives at P0: K.
- **`MOV SS` or `POP SS` then a call.** "Any single-step trap that would be delivered following the MOV to SS instruction ... is suppressed", and a data breakpoint "is inhibited until the instruction boundary following the next instruction" (§7.8.3 [R]). Both land at P0: R.
- **A single step cannot arrive at or after W0.** No prologue instruction changes TF. With TF = 1 at P0 a trap is taken before P1, and the stub clears TF in the frame before it restarts the entry. A stub's `IRETQ` into an entry lands at P0 only. So a path that executes P7 had TF = 0 from P0 on. (Under variant (a) the stub returns with RFLAGS = 2, a constant, so TF is clear whatever the frame holds. Under variant (b) another core of the node can write TF = 1 back into the frame, and the entry restarts again: the node loses its own time.)
- **Between P7 and W0 the stack pointer is still the caller's.** Only vectors with an IST index can arrive there (NMI, #MC; #DB and #DF cannot occur), and they push on gate-side stacks. A vector without an IST index would push a frame at an address the caller chose, under the gate's root; no such vector can arrive, because IF = 0 and W0 has no memory operand and no fault. This row must be checked by the model before any other.
- **A wild jump into P2 to P7** takes a `#CP` at the target (no `ENDBR64`): a fault in gate text, F (B.1.7). With an event taken first, the tracker is lost ("Higher priority faults/traps/events that occur at the end of an indirect CALL/JMP are delivered ahead of any #CP(ENDBRANCH) fault", SDM vol. 1 §18.3 [R]): the stub sees an address in the restart range and restarts at P0, which recomputes every register. The same holds for every restart range of gate text (V12); it needs `NO_TRACK_EN` = 0 (B.1.5).

#### B.1.5 The body

- **Stack:** the gate stack. **Shadow stack:** the caller's (the gate's own `CALL`s push on it); it takes no ordinary store from any core. A caller that leaves too little room on it takes a fault in the window, which is F for its node. (Choice. Rejected: a gate shadow stack per core, which needs a restore token and `RSTORSSP` at every entry.)
- **First step:** the view-epoch check of B.1.3; then the address of this core's pending word is computed; then, for an entry that writes, the gate lock.
- **A write of the living part** is `LOCK CMPXCHG` on the gate root's writable mapping of the word: an ordinary instruction under mechanism 2.
- **A write of a device register** is one plain store of a whole value (D-126) to the unit's page, which only the gate root of the role's holder maps (G9).
- **Clearing a table page** uses the gate's private linear view (outside the kernel's data range, excluded from `DR0..DR3`) and may use `REP STOS`: DF is 0 since P2.
- **What the kernel controls, and how each is made harmless** (version 1's table, corrected):

| State | Treatment |
|---|---|
| RSP | Never dereferenced. Saved as a value at P6, restored at E0 |
| IF | `CLI` at P1; V10 at exit |
| DF | `CLD` at P2 |
| TF | A `#DB` in an entry restarts it (B.1.4). Variant (a): the stub's composed frame carries RFLAGS = 2. Variant (b): the stub clears TF in the frame. No `PUSHFQ` anywhere |
| AC | Not cleared: it matters only for user pages, which the gate's root does not map. Version 1's `CLAC` is removed (it is `#UD` without SMAP) |
| NT, RF, VM | "the processor also clears the VM, RF, and NT flags" at delivery (§7.12.1.3 [R]); a stub's `IRETQ` with NT set faults in gate text: F |
| Arithmetic flags | Undefined at entry and after every `MOV` to CR3 ("The OF, SF, ZF, AF, PF, and CF flags are undefined", SDM vol. 2B [R]); the gate tests nothing across one |
| General registers | Arguments are checked as values (V11); RAX, RCX, R11 are overwritten by the prologue |
| Segment registers, FS and GS bases, `SWAPGS` state | Not used: no segment prefix in gate text (the scan checks). The core is found by `RDPID` |
| CR2, CR8 | Never read; CR8 matters only with IF = 1 |
| x87, SSE and AVX state | Gate text is built without them |
| DR0 to DR3, DR7 | Written by the gate only. **In both production and development builds**, the gate refuses **`DR7.GD = 1`** (bit 13: "enables the debug-register protection condition", raising `#DB` prior to any `MOV` accessing `DR0..DR7`, SDM vol. 3B §20.2.4 [R]) and refuses **`R/Wn = 10`** ("Break on I/O reads or writes" when `CR4.DE = 1`, undefined when `0`, §20.2.4 [R]). Production: `DR0..DR3` user range only. Development: also kernel addresses outside gate text, **the entire linear address range of the gate's private view** (which covers table pages, newly allocated table pages cleared through that view, the living part, the gate part, unit registers and unit tables), the gate stack, **the interrupt stacks on both sides, every shadow stack, the read-only gate tables, the pending/deferred-DR6 page, the return and CPL-3 IST user blocks, `RFRAME_OF`, the machine-check log, the node beacon (`panic`), the clock page, `parked` and the crash area** (V3-6: a watchpoint on any address the gate reads or writes while open raises `#DB` in the window, which is F) |
| DR6 | "Updates to this register only occur when an exception is generated ... To avoid confusion in identifying debug exceptions, debug handlers should load DR6 with its reset value (FFFF0FF0H) before returning to the interrupted task. In 64-bit mode, the upper 32 bits of DR6 are reserved and must be written with zeros" (SDM vol. 3B §20.2.3 [R]); the #DB stub copies `DR6` to the deferred-DR6 word and loads `0x0000_0000_FFFF_0FF0` |
| SSP and tokens | Confined by guard pages; `RSTORSSP`, `SAVEPREVSSP`, `SETSSBSY`, `CLRSSBSY`, `WRSS*`, `WRUSS*`, **`INCSSPD` and `INCSSPQ`** in gate text only. `INCSSPQ` "SSP := SSP + Range * 8" after loads at the first and last slot only, so with SSP at the token it leaves SSP on the guard page's first byte and the next delivery overwrites the token; `INCSSPD` leaves SSP 4 bytes off (SDM vol. 2A, `INCSSPD/INCSSPQ` pseudo-code [R]). The event-driven kernel unwinds by `RET` and has no use for either; without them SSP is always aligned and moves only by `CALL`, `RET` and deliveries |
| `IA32_S_CET`, `IA32_U_CET` | `WRMSR` only, so the gate's; the values of the table below |
| `IA32_PL0_SSP`, the SSP table, `IA32_TSC_AUX`, **`IA32_STAR`**, `IA32_LSTAR`, `IA32_FMASK`, `IA32_SYSENTER_CS`, `IA32_DEBUGCTL`, the counters, Processor Trace, PKRS | `WRMSR` only, so the gate's; set at start-up. `IA32_STAR` fixes the GDT selector layout required by `SYSCALL` (`CS.Selector := IA32_STAR[47:32] AND FFFCH`, `SS.Selector := IA32_STAR[47:32] + 8`, SDM vol. 2B `SYSCALL` [R]) and 64-bit `SYSRET` (`CS.Selector := (IA32_STAR[63:48]+16) OR 3`, `SS.Selector := (IA32_STAR[63:48]+8) OR 3`, SDM vol. 2B `SYSRET` [R]): the GDT therefore places `KERNEL_CS` at selector `K`, `KERNEL_SS` at `K + 8`, `USER_SS` at `U + 8` (RPL 3) and `USER_CS` at `U + 16` (RPL 3), with `IA32_STAR[47:32] = K` and `IA32_STAR[63:48] = U` (V3-7a). `IA32_SYSENTER_CS` = 0, so a user `SYSENTER` faults ("#GP(0) If IA32_SYSENTER_CS[15:2] = 0", SDM vol. 2B, `SYSENTER` [R]) |
| IBT tracker | Entries start with `ENDBR64`; a wild entry is F or R (B.1.4) |

**Every field of `IA32_S_CET` and `IA32_U_CET`** (SDM vol. 4, Table 2-2, MSR 6A0H, and 6A2H "similar format" [R]).

| Bit | Field | The manual | `IA32_S_CET` | `IA32_U_CET` |
|---|---|---|---|---|
| 0 | `SH_STK_EN` | "enable shadow stacks" | **1** | 0 |
| 1 | `WR_SHSTK_EN` | "enables the WRSSD/WRSSQ instructions" | **1** (the stubs' rewrites, the return frame page, the log) | 0 |
| 2 | `ENDBR_EN` | "enables indirect branch tracking" | **1** | 0 |
| 3 | `LEG_IW_EN` | "Enable legacy compatibility treatment for indirect branch tracking" | **0** | 0 |
| 4 | `NO_TRACK_EN` | "enables use of no-track prefix for indirect branch tracking" | **0** | 0 |
| 5 | `SUPPRESS_DIS` | "disables suppression of CET indirect branch tracking on legacy compatibility" | 0 (no meaning with bit 3 clear) | 0 |
| 9:6 | reserved | "must be zero" | 0 | 0 |
| 10 | `SUPPRESS` | "indirect branch tracking is suppressed" | **0** | 0 |
| 11 | `TRACKER` | "IDLE (0), WAIT_FOR_ENDBRANCH(1)" | 0 when written | 0 |
| 63:12 | `EB_LEG_BITMAP_BASE` | "a legacy code page bitmap used for legacy compatibility" | 0 | 0 |

- **Why bit 4 must be 0.** "When enabled by setting the NO_TRACK_EN control in the IA32_U_CET/IA32_S_CET MSR, near indirect CALL and JMP instructions when prefixed with 3EH do not modify the CET indirect branch tracker. ... When this control is 0, near indirect CALL and JMP instructions are always tracked irrespective of the presence of the 3EH prefix" (SDM vol. 1 §18.3.1 [R]). With the bit set, `3EH JMP R15` to P7 loads the kernel's RAX into CR3 with no `#CP`. The kernel and the gate are therefore built without no-track jump tables.
- **`IA32_U_CET` is 0 in version 1**: user threads run without CET, and the register is the gate's to write all the same. A later decision that gives user threads shadow stacks states its values then; nothing in this draft depends on them.

#### B.1.6 The exit sequence and the delivery of a deferred event

The return value is in RAX (and RDI for a second word); the exit rows do not touch them. RDX holds the address of this core's pending word, computed in the body.

| Row | Instruction | Holds after it | Mask | NMI | #MC-L | #MC-B | #DB-TF | #DB-BP | Fault | SMI | INIT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| X0 | `MOV R11,[RSP]` | R11 = caller's RSP, from the gate stack | no | D | MC | MC | no | no | no | FW | F |
| X1 | `MOV RCX,[RSP+8]` | RCX = caller's root and tag (for `load_root`: the new root and tag, checked by G7) | no | D | MC | MC | no | no | no | FW | F |
| X2 | `BTS RCX,63` | No-flush bit set (omitted when the call owes a flush of that tag, B.1.3) | no | D | MC | MC | no | no | no | FW | F |
| X3 | `MOV CR3,RCX` | **Closed.** The window existed from P7 to here | no | D (before it executes) | MC | MC | no | no | no (value read from CR3 at P5, or checked by G7); else F | FW | F |
| E0 | `MOV RSP,R11` | Caller's stack | no | D | MC | MC | D | no | no | FW | F |
| E1 | `CMP QWORD PTR [RDX],0` | ZF = no event pending | no | D | MC | MC | D | no | no (page present by construction); else F | FW | F |
| E2 | `JNZ deferred_events` | Direct jump to the kernel's routine (an address of the kernel entry table, D.4), or falls through | no | D, back to E1 | MC | MC | D, back to E1 | no | no | FW | F |
| E3 | `RET` | Back in the caller, IF = 0 | no | D, back to E1 | MC | MC | D, back to E1 | no | F (the caller's stack or shadow stack is wrong) | FW | F |

- **Restart rows and rows that are not.** Restart to the entry: P0 to P7 only. Re-test: an event at E2 or E3 returns to E1, which only reads. No row from W0 to E0 is ever re-entered: an event there returns to the interrupted instruction. This is what "a completed call is never re-run" means here.
- **At E0 the stack pointer is the gate stack's address under the kernel's root, where it is not present.** An NMI or a machine check there uses an IST stack; nothing is pushed at RSP, and no kernel code runs (V3). This is the case document 3's break 1A found.
- **A single step at E0 to E3** is possible only under variant (b), if another core wrote TF into a frame on a kernel-side stack; the stub clears it and marks the event. V12, item 4, lists these rows as the only ones of the exit where a `#DB` is not fatal.
- **`load_root` closes directly to the new root.** X1 loads the root and tag the body checked and recorded, so a switch of address space costs two CR3 writes, not three.

**The delivery, and who pushes what on which shadow stack.**

| Step | Who | Regular stack | Shadow stack | NMI blocking |
|---|---|---|---|---|
| NMI taken at a row marked D or R | Processor | Frame of 5 words on IST1 (gate side if open, kernel side if not) | Marks IST1's token busy; pushes CS, LIP, SSP on IST1's shadow stack | Established |
| The stub | Gate text | Saves the context's three registers in its slots; composes its return (B.1.9, rows S0 to S17) | For R, one `WRSSQ` of the slot at SSP + 8; no `CALL`, so nothing else | Held |
| The stub's `IRETQ` | Processor | Pops the composed frame from the return frame page (variant (a)), or the processor's frame (variant (b)) | Compares CS and LIP, pops three words, frees the token ("IF tempSSP != SSP THEN ... clear the busy bit", SDM vol. 2A, `IRET` pseudo-code [R]) | "NMI delivery is unblocked once execution of IRET commences" (§7.7.2 [R]) |
| E2 taken | Gate text | Nothing | Nothing: a direct `JMP` | Not blocked |
| `deferred_events` (kernel code) | Kernel | Its own frames on the caller's stack | Its own `CALL`s on the caller's shadow stack; its `RET` meets the return address the caller's `CALL` pushed | Not blocked |
| A hardware NMI during the routine | Processor | IST1, whose token is free | Token busy again, three words | Established; the interrupted address is outside gate text, so the kernel's handler runs and ends through `ret_kernel` (variant (a)) or by its own `IRETQ` (variant (b)) |

- **No software `INT 2`.** The routine takes the bits (`XCHG` with 0 on its pending word) and calls the kernel's NMI work as a function. Document 3's break 6A came from replaying through vector 2, which marks the token busy without blocking NMIs.
- **What the kernel's NMI work must be** (a requirement on the kernel, to enter the contract when this does): it may be entered from the routine and, nested, from a hardware NMI on the same core, so it reads words (the fence mark, the start request) and writes records in a way that is safe to repeat; it counts nothing. On x86-64 that is already its content (kernel.md, rule (2)).
- **The kernel also checks its pending word at the end of every kernel event and before it idles.** An event marked outside a gate call (a machine check of class "continue", B.5) is delivered there.
- **Bound on the delay.** An NMI taken anywhere from P0 to E3 is delivered no later than the jump at E2 of that call, which is the contract's *H*.

#### B.1.7 The stubs, the evacuate-and-free IST discipline, and the vector table

**Uniform IST discipline (closes V3-1, V3-2, V3-5; eliminates version 3's Row G1).**
1. **No `IRETQ` while returning into an unfinished NMI stub.** Hardware blocks NMIs on NMI delivery until an `IRET` executes ("NMI delivery is unblocked once execution of IRET commences", SDM vol. 3A §7.7.2 [R]). Any nested `"continue"` `#MC` (or deferred `#DB` at `NMI_N0`) that interrupts the NMI stub frees its own IST shadow-stack token (`WRSSQ`), restores `SSP` directly onto `IST1` via `RSTORSSP` + `INCSSPQ 1` (or clears `SSP := 0` via `CLRSSBSY` at `NMI_H2`), clears `MCIP` (for `#MC`), and executes a direct **`JMP`** back to `NMI_N4` (or `NMI_H2`/`NMI_H3`) **without executing `IRETQ`**. NMI blocking is never lifted while `IST1` is active; a second NMI can never fault on a busy `IST1` token; version 3's Row `G1` is deleted.
2. **Exact CET primitive to restore `SSP := TARGET_SSP` without `IRETQ`** (verified in SDM vol. 2B `RSTORSSP`, pp. 4-598–4-599 [R], and vol. 2A `INCSSPD/INCSSPQ`, p. 3-459 [R]). Given an 8-byte aligned supervisor shadow-stack address `TARGET_SSP` in `RCX` whose preceding slot `[TARGET_SSP - 8]` is a free supervisor shadow-stack slot:
   - `LEA RDX, [RCX - 8]`; `OR RCX, 1`; `WRSSQ [RDX], RCX` — writes the 64-bit restore-SSP token (`(token & 3) == 1`, `((token & ~1) - 8) & ~7 == RDX`) at `[TARGET_SSP - 8]`.
   - `RSTORSSP [RDX]` — atomically verifies the token, overwrites `[RDX]` with `old_SSP | 3` without dereferencing `old_SSP` (so it succeeds even when `old_SSP == 0`), and sets `SSP := RDX` (`TARGET_SSP - 8`) and `CF := 0`.
   - `MOV ECX, 1`; `INCSSPQ RCX` — loads 8 bytes from `SSP` (`[TARGET_SSP - 8]`) and advances `SSP := SSP + 8 = TARGET_SSP`.
   - Every target of this primitive (`IST1_TOKEN`, `IST1_TOKEN - 24`, `IA32_PL0_SSP`, `MC_RSHSTK`, `MC_RSHSTK + 24`, `PARK_RSHSTK`) is 8-byte aligned and has a dedicated free supervisor shadow-stack slot at `[TARGET_SSP - 8]` (B.1.2). The sequence is 100% idempotent when restarted from its `WRSSQ`, regardless of the value `SSP` held at interruption.
3. **Every CPL-3 IST event evacuates to its user block and switches onto `IA32_PL0_SSP` before entering kernel text (V3-5).** Kernel handlers entered from CPL 3 (`kernel_nmi`, `kernel_db`, `kernel_mc_user`) never run on an IST shadow stack; every IST token is free whenever kernel code entered from CPL 3 or user code runs.

**The NMI stub, as rows.** The `#DB` stub has the same shape with the `DR6` check/copy/reset rows and `IST2` / `DBUSER_BLOCK_OF` / `kernel_db`; the `#MC` stub is specified in full in B.5.2. RAX, RCX and RDX are the stub's three registers.

| Row | Instruction | Holds after it | Part |
|---|---|---|---|
| N0 | `ENDBR64` | Tracker idle | Before the redo label: harmless rows |
| N1 | `MOV [RSP+40],RAX` | The context's RAX in the first slot above the frame | Before |
| N2 | `MOV [RSP+48],RCX` | The context's RCX | Before |
| N3 | `MOV [RSP+56],RDX` | The context's RDX | Before |
| N4 | `RDPID RAX` | RAX = this core's number | **Redo label.** The restart range begins |
| N5 | `MOV RSP,[ISTTOP_NMI+RAX*8]` | RSP = this stub's own stack pointer, from a read-only table: the frame at RSP, the slots above it | Range |
| N6 | `MOV RCX,CR3` | | Range |
| N7 | `AND ECX,0FFFH` | The tag in use | Range |
| N8 | `CMP ECX,GATE_PCID` | Open or not (V4) | Range |
| N9 | `JE` to the open path | Open: runs `RDSSPQ RDX`, checks `SSP == IST1_TOKEN - 24` (else F); reads interrupted address `RCX = [RDX+8]`; checks `RCX` against the text-range table: **`T0..T26` → R to `T0` (V3-7d); `MC_N4..Step 4` (Range 1a) → R to `MC_N4`; `MC_SW0..MC_SW8` → R to `MC_SW0`; `MC_R2_0..MC_S17` → R to `MC_R2_0`; `W0..X3`, `MC_N0..MC_N3`, `park` → D; anything else → F**. Marks `NMI_BIT` (N18); for R rewrites `[RDX+8]` (`WRSSQ`) and returns via `S0..S17` (or for D restores its three registers from the slots and returns by `IRETQ` on the private gate-side frame) | Range |
| N10 | `RDSSPQ RDX` | RDX = SSP | Range |
| N11 | `MOV RCX,[IST1_SSP_OF+RAX*8]` | RCX = this core's `IST1` shadow-stack token address (`IST1_TOKEN`) | Range |
| N12 | `CMP RDX,RCX` | Exact equality test for CPL 3 (V6) | Range |
| N13 | `JE` to CPL-3 handoff (`NMI_H_COPY`) | From CPL 3: copies 6 words (`RAX, RCX, RDX, RIP, RFLAGS, RSP`) from `[RSP+0..56]` to `NMIUSER_BLOCK_OF[core]`, then executes `NMI_H0..NMI_H3` below | Range |
| N14 | `SUB RCX,24`; `CMP RDX,RCX`; `JNE T0` | Exact equality test for CPL 0 (`SSP == IST1_TOKEN - 24`); any other `SSP` (e.g. wild indirect jump to `N0`) → **F** | Range |
| N15 | `MOV RCX,[RDX+8]` | RCX = the interrupted address, from the shadow stack (V5) | Range |
| N16 | Compares of RCX with the bounds of the text-range table (registers and the read-only table only) | The class of the table below | Range |
| N17 | Branch by class | Outside gate text: restore the three registers from the slots, `JMP kernel_nmi` (CPL-0 kernel handler; returns via `ret_kernel`). Fatal: `JMP T0`. Restart: RCX := the first address of the range. Deferred: RCX unchanged | Range |
| N18 | `LOCK OR QWORD PTR [KPEND+RAX*16],NMI_BIT` | The event is marked. Repeating it changes nothing | Range |
| N19 | `WRSSQ [RDX+8],RCX` | The return address on the shadow stack is the one in RCX (for D it rewrites the same value) | Range |
| S0 to S17 | The return rows of B.1.9 | The stub's last instruction is the `IRETQ` at S17 | Range |

**CPL-3 IST handoff rows (`NMI_H0..NMI_H3`; identical `DB_H0..DB_H3` for `#DB` using `IST2` and `kernel_db`; V3-5).** Reached from `N13` after copying the 6 user-context words into `NMIUSER_BLOCK_OF[core]` (or `DBUSER_BLOCK_OF[core]`, plus `DR6` copy/reset for `#DB`). `NMI_H_COPY..NMI_H1` lie inside the stub's restart range (`N4`); `NMI_H2` and `NMI_H3` are listed harmless `D` rows (V12 item 5):

| Row | Instruction | Holds after it | Part |
|---|---|---|---|
| NMI_H0 | `MOV RDX,[IST1_SSP_OF+RAX*8]` | RDX = `IST1_TOKEN` | Range (`N4`) |
| NMI_H1 | `CLRSSBSY [RDX]` | `IST1` token free; `SSP = 0` (`CLRSSBSY` pseudo-code [R]). NMI blocking still held | Range (`N4`) until it executes |
| NMI_H2 | `SETSSBSY` | `SSP = IA32_PL0_SSP`, token busy (it was free since the event came from CPL 3). No register operand | Harmless **D** row |
| NMI_H3 | `JMP kernel_nmi` | In kernel text on `IA32_PL0_SSP`, every IST token free, NMI blocking held until `ret_user`. Kernel loads its stack pointer and reads `NMIUSER_BLOCK_OF[core]`. No register operand | Harmless **D** row |

- **Why N5.** A nested event returns to N4 with whatever RSP its own return carried. The stub's stack pointer is a constant of the core and the vector, so the stub reloads it. Everything the stub reads through RSP afterwards (the frame's RSP and RFLAGS words, the three slots) is the interrupted context's, untrusted by class.
- **Every instruction with a trusted operand lies between N4 and S17 (or `NMI_H0..NMI_H1`)**, and a nested event there returns to N4 (for `#MC` interrupting NMI: by direct `JMP NMI_N4` without `IRETQ`). A `#DB` in `N1..S17` or `NMI_H0..NMI_H3` is **F** (V12, item 4): this closes document 4's F2 and document 5's M2.
- **Fixed-point property of N19.** Every target `N19` writes (`P0`, `I0`, `U0`, `Y0`, `Y14`, `E1`, `T0`, `DB_N4`, `MC_N4`, `MC_SW0`, `MC_R2_0`, `M0`, `M5`, and every `D` row) classifies back to itself under N16–N17. So a `#MC` arriving after `N19` and jumping back to `NMI_N4` recomputes the exact same target.
- **The stubs of vectors without an IST index** have no N5: their stack pointer is the interrupted context's. After their redo label they store nothing through RSP, never execute `IRETQ`, and end only by a jump to the kernel's handler (if not open and outside gate text, or maskable at `ENDBR64`/`CLI` of an entry) or `JMP T0`.

**Did the event come from CPL 3?**
- Vectors with an IST index (`NMI`, `#DB`, `#MC`): exact equality `SSP == ISTk_SSP_OF[core]` means CPL 3 (the processor switched to `ISTk`'s shadow stack and pushed nothing, saving user SSP to `IA32_PL3_SSP` if enabled: SDM vol. 2A, `INT n`, `INTER-PRIVILEGE-LEVEL-INTERRUPT` [R]); exact equality `SSP == ISTk_SSP_OF[core] - 24` means CPL 0 (three words pushed: `INTRA-PRIVILEGE-LEVEL-INTERRUPT` [R]); any other `SSP` value is **F** (`JMP T0`).
- Vectors without an IST index: `SSP == PL0_SSP_OF[core]` means CPL 3. From CPL 0 the processor pushed three words below the interrupted SSP, which is never the token's address. With `INCSSPD`/`INCSSPQ` out of kernel text (D.4), SSP is always aligned and exact.

**What a stub does, by the interrupted address.**

| Interrupted address | Open | Not open |
|---|---|---|
| Outside gate text, from CPL 3 | F (cannot be) | The kernel's handler (IST vectors evacuate via `H0..H3` / `M0..M9`; `"continue"` `#MC` returns via `MC_R2`, B.5.2) |
| Outside gate text, from CPL 0 | F (cannot be) | The kernel's handler; for `#MC` of class "continue", marked and returned by the stub (B.5.2) |
| First two instructions (`ENDBR64`, `CLI`) of **any** entry (`P0/P1`, `I0/I1`, `U0/U1`, `Y0/Y1`, EOI, timer) (V3-7f) | — | **R** for NMI, `#MC`, `#DB`. Maskable interrupts (vectors 32–255): **K**. Any other vector: F |
| Remainder of `P2..P7`, short entry restart ranges (`I2..I13`, EOI, timer), `U2..U24`, `Y2..Y13a`, `Y14..Y21` | — | **R** to that range's first instruction for NMI, `#MC`, `#DB`. Any other vector: F |
| `W0..X3` (the body) | **D** for NMI and `#MC`. Every other vector: F | F (a wild entry) |
| `E0`, `E1`; `L0..L2`; `I14..I16` (including `I15: MOV EAX, REFUSED`, V3-7e) and `RET` of a short entry; `NMI_H2..H3`, `DB_H2..H3`, `M4`, `M9` | — | **D** for NMI and `#MC` (`#MC` at `NMI_H2`/`NMI_H3` returns by direct `JMP` without `IRETQ`). **D** for `#DB` at `E0`, `E1`, `L0..L2` only; **F** for `#DB` at `I14..I16`, `H2..H3`, `M4`, `M9`. Every other vector: F |
| `E2`, `E3` | — | **D**, returning to `E1` (NMI, `#MC`, `#DB`) |
| `N0` (`ENDBR64`) of any IDT stub (V3-4) | **D** for NMI and `#MC` (`#MC` at `NMI_N0` copies `RAX/RCX/RDX` to `[IST1_TOP+40..56]` and `JMP`s to `NMI_N4` without `IRETQ`). **`#DB`: F** | **D** for NMI and `#MC` (`#MC` at `NMI_N0` copies `RAX/RCX/RDX` and `JMP NMI_N4`). **`#DB` with `DR6.{BS,BD,BT} == 0`: D** (copies/resets `DR6`, `RFLAGS = 2`; at `NMI_N0` copies `RAX/RCX/RDX`, frees `IST2`, restores `SSP := SSP_nmi`, `JMP NMI_N4` without `IRETQ`). **`#DB` with `BS/BD/BT != 0`: F** |
| `N1..N3` of any IDT stub | **D** for NMI and `#MC` (`#MC` at `NMI_N1..N3` copies `RAX/RCX/RDX` to `[IST1_TOP+40..56]` and `JMP NMI_N4` without `IRETQ`). **`#DB`: F** | **D** for NMI and `#MC` (`#MC` at `NMI_N1..N3` copies `RAX/RCX/RDX` and `JMP NMI_N4`). **`#DB`: F** |
| A stub from its redo label (`N4`) to `S17` or `H0..H1`; `#MC` Range 1a (`MC_N4..Step 4`), Range 1b (`MC_SW0..MC_SW8`), Range 2 (`MC_R2_0..MC_S17`, `MC_JNMI_*`), `M0..M3`, `M5..M8` | **R** to that range's first instruction for NMI and `#MC` (`#MC` in NMI stub `JMP`s to `NMI_N4` without `IRETQ`; second `#MC` in Range 2 preserves `IST_SAVE_MC` and jumps to `MC_SW0`). **`#DB`: F** | **R** to that range's first instruction for NMI and `#MC` (`#MC` in NMI stub `JMP`s to `NMI_N4` without `IRETQ`; second `#MC` in Range 2 preserves `IST_SAVE_MC` and jumps to `MC_SW0`). **`#DB`: F**. **`#GP`: F** (Row G1 is gone) |
| The fatal path, `T0..T26` (including `mc_check_stop_or_clear_mcip`) | **R** to `T0` for NMI and `#MC` (V3-7d). **`#DB`: F** | **R** to `T0` for NMI and `#MC`. **`#DB`: F** |
| The park loop (`park`, `park + 1`) | **D** for NMI and `#MC`. Every other vector: F | F (the loop runs only under the gate's root) |

| Vector | Stack | Rule |
|---|---|---|
| 2, NMI | IST1 | The table above |
| 1, `#DB` | IST2 | The table above. Where it is not F it copies `DR6` to the deferred-DR6 word and loads `DR6` with `0x0000_0000_FFFF_0FF0` (SDM vol. 3B §20.2.3 [R]); both can be repeated. At `N0` of any IDT stub when not open: checks `(DR6 & 0xE000) == 0` (`BS = BD = BT = 0`, else F); if `N0` is `NMI_N0`, evacuates without `IRETQ` (table below) |
| 18, `#MC` | IST3 | B.5.2 first, in gate text (before any open-vs-closed dispatch); then the table above. Frees `IST3` and switches `SSP` off `IST3` before `WRMSR 0x17A` clears `MCIP` |
| 8, `#DF` | IST4 | **Always F**, by `JMP T0` |
| 13, `#GP` | current | Not open and outside gate text: the kernel's. Otherwise **F** (Row G1 is eliminated) |
| 3, `#BP` | current | DPL 3. Not open and outside gate text: the kernel's. Otherwise F |
| Other exceptions (0, 4 to 7, 9 to 12, 14 to 17, 19 to 31) | current | Not open and outside gate text: the kernel's. Otherwise F |
| 32 to 255 | current | Not open and outside gate text, or at the first two instructions (`ENDBR64`, `CLI`) of any entry: the kernel's. Otherwise F |

**Complete 4 × 4 IST nesting matrix (outer running vector vs. arriving inner IST vector).**

| Outer running \ Inner arriving | **NMI (`IST1`)** | **`#DB` (`IST2`)** | **`#MC` (`IST3`)** | **`#DF` (`IST4`)** |
|---|---|---|---|---|
| **NMI stub (`NMI_N0..S17`, `NMI_H0..H3`)** | **Blocked by hardware** (§7.7.2 [R]). Never lifted inside the stub because neither `#MC` nor `#DB` at `NMI_N0` executes `IRETQ` here | At `NMI_N0`, not open, `DR6.{BS,BD,BT} == 0`: copy/reset `DR6`, copy `RAX/RCX/RDX` to `[IST1_TOP+40..56]`, `WRSSQ [IST2_TOKEN], IST2_TOKEN`, restore `SSP := SSP_nmi` (`RSTORSSP`+`INCSSPQ 1`), mark `DB_BIT`, **`JMP NMI_N4` (no `IRETQ`)**. Elsewhere or `BS/BD/BT != 0` or open: **F** (`JMP T0`) | Stop/F → stop/`T0`. `"Continue"` (**no `IRETQ`**): at `NMI_N0..N3` copy `IST_SAVE_MC.{rax,rcx,rdx}` to `[IST1_TOP+40..56]`, `MC_SW` restores `SSP := SSP_nmi`, frees `IST3`, clears `MCIP`, `JMP NMI_N4`; at `NMI_N4..S17` or `NMI_H0..H1` same without copying registers; at `NMI_H2` (`SSP=0`) `CLRSSBSY [IST3_TOKEN]`, clear `MCIP`, `JMP NMI_H2`; at `NMI_H3` (`SSP=PL0_SSP`) `MC_SW` restores `SSP := PL0_SSP`, `JMP NMI_H3` | Always **F** (`JMP T0`) |
| **`#DB` stub (`DB_N0..S17`, `DB_H0..H3`)** | At `DB_N0..N3`, `DB_H2..H3`: **D** (via `S0..S17`). At `DB_N4..S17`, `DB_H0..H1`: **R** to `DB_N4` | Cannot arise honestly (`TF=0`, `DR7.GD=0`, gate/IST/shadow-stack pages excluded). If forced: `IST2` busy → `#GP(0)` in gate text → **F** (`JMP T0`) | Stop/F → stop/`T0`. `"Continue"` via `MC_SW0..MC_SW8` → `MC_R2_0..MC_S17` (`MC_RSHSTK`): at `DB_N0..N3`, `DB_H2..H3` **D**; at `DB_N4..S17`, `DB_H0..H1` **R** to `DB_N4` | Always **F** (`JMP T0`) |
| **`#MC` stub (`MC_N0..N3`, Range 1a, `MC_SW`, Range 2, `M0..M9`)** | At `MC_N0..N3`, `M4`, `M9`: **D**. Range 1a (`MC_N4..Step 4`): **R** to `MC_N4` (`row7_sticky` preserved). Range 1b (`MC_SW0..MC_SW8`): **R** to `MC_SW0`. Range 2 (`MC_R2_0..MC_S17`): **R** to `MC_R2_0`. `M0..M3`: **R** to `M0`. `M5..M8`: **R** to `M5` | At `MC_N0`, not open, `DR6.{BS,BD,BT} == 0`: **D** (copy/reset `DR6`, `RFLAGS = 2`). Everywhere else in `#MC` stub: **F** (`JMP T0`, closes F2/M2) | Before `MC_SW8`/`M8` (`WRMSR 0x17A`): `MCIP = 1` → hardware shutdown (OPEN-4 item 3). After `MC_SW8` (in Range 2 `MC_R2_0..MC_S17` or `MC_JNMI_*`): `IST3` is already free; `MC2` sees `LIP ∈ Range 2`, preserves `IST_SAVE_MC` and `MC_RSHSTK`, scans/logs/clears banks, marks `MC_BIT`, jumps to `MC_SW0` (or `CLRSSBSY`+`WRMSR`+`JMP NMI_H2`) and restarts Range 2. After `M8` (at `M9`): `IST3` free, `row7_sticky = 0`, `MC2` returns **D** to `M9` without touching `MCUSER_BLOCK_OF` | Always **F** (`JMP T0`) |
| **Fatal path (`T0..T26`, `mc_check_stop_or_clear_mcip`) and `park`** | At `T0..T26`: **R** to `T0`. At `park`: **D** (`IST1` guaranteed free by `T6`) | At `T0..T26` or `park`: **F** (`JMP T0`) | Before `T16` clears `MCIP` (if entered with `MCIP = 1`): shutdown (OPEN-4 item 3). After `T16` (`IST3` already freed at `T8`): stop → stop; `"continue"` at `T0..T26` → **R** to `T0`, at `park` → **D** (`IST3` guaranteed free) | Cannot arise in `T0..T26` or `park` (all pages gate-side present; `IST4` freed at `T9`) |

- **Why `#DB` at `N0` of an IDT stub (V3-4) does not reopen F2.** By SDM vol. 3A §7.8.3 [R], `"Any data breakpoint on the MOV to SS instruction or POP to SS instruction is inhibited until the instruction boundary following the next instruction ... Any single-step trap that would be delivered following the MOV to SS instruction or POP to SS instruction (because EFLAGS.TF is 1) is suppressed. The suppression and inhibition ends after delivery of an exception or the execution of the next instruction."` A user thread executing `MOV SS`/`POP SS` (with a data watchpoint) followed by `INT3`, `UD2`, `#PF`, `#DE` or `#GP` therefore delivers a trap-class `#DB` with `DR6.B0..B3` set and `DR6.BS = BD = BT = 0` immediately at `N0` (`ENDBR64`) of that exception's gate stub. Treating `N0` (`ENDBR64`, zero operands, no privileged action) as **D** when `CR3` is not open and `DR6.{BS,BD,BT} == 0`, returning with `RFLAGS = 2` (`TF = 0`), stops an unprivileged user watchpoint from panicking a healthy node while keeping every instruction `N1..S17` and every single-step (`DR6.BS = 1`) **F**.
- **Software interrupts from the kernel** (`INT n`, `INT1`, `INT3`, `INTO`) leave an IST token busy if the kernel never returns. With vector 8 always F this harms the kernel's own node only; the scan forbids them outside gate text all the same (D.4).

#### B.1.8 The system-call entry

`SYSCALL` enters at CPL 0 with the user's RSP, and with shadow stacks on it executes "SSP := 0" and sets the tracker to `WAIT_FOR_ENDBRANCH`; it "masks RFLAGS using the IA32_FMASK MSR" (SDM vol. 2B, `SYSCALL` [R]). `SETSSBSY` is the gate's alone, so `IA32_LSTAR`'s target is in gate text:

| Row | Instruction | Holds after it | Mask | NMI | #MC | #DB | Fault |
|---|---|---|---|---|---|---|---|
| L0 | `ENDBR64` | CPL 0, SSP = 0, RSP the user's | no (`IA32_FMASK` clears IF) | D | MC | D (a data breakpoint held by `MOV SS`) | no |
| L1 | `SETSSBSY` | SSP = this core's kernel shadow stack, token busy | no | D | MC | D | **F, reached through `#DF`**: `#CP(SETSSBSY)` when the token is not free ("IF shadow_stack_lock_cmpxchg8B(...) != expected_token_value THEN #CP(SETSSBSY)" [R]). The delivery of `#CP` first writes a frame at the user's RSP, in the node's own translations, then faults on the shadow stack |
| L2 | `JMP kernel_syscall` | In kernel text (an address of the kernel entry table, D.4) | no | D | MC | D | no |

- **`IA32_FMASK`** is written by the gate at start-up and clears IF, TF, DF, AC and NT.
- **No row is a restart row**, and each is a harmless row of V12: none has an operand the kernel can supply. `SETSSBSY` runs once.
- **The fault at L1, in order (ARGON-2).** The frame is pushed first ("Push(far pointer to old stack); ... Push(far pointer to return instruction)", `INT n` pseudo-code [R]), at the user's RSP, with CPL 0: the node's own memory at an address its own thread chose. Then, with `SSP = 0`, the processor executes "Shadow_stack_store 4 bytes of 0 to (NewSSP − 4)" (`INT n`, `INTRA-PRIVILEGE-LEVEL-INTERRUPT` [R]), at `0xFFFF_FFFF_FFFF_FFFC`. That address is canonical; the store raises `#PF` because the last page of the address space is never mapped (B.1.2). By SDM vol. 3A Table 7-5 [R], benign (`#CP`) + `#PF` delivers `#PF` serially; delivering `#PF` (also non-IST, `NewSSP = SSP = 0`) executes the same store at `0xFFFF_FFFF_FFFF_FFFC` → second `#PF` → `#PF + #PF = #DF` on `IST4` (`SSP = IST4_TOKEN - 24 != 0`) → `T0` (**F**). A healthy node never takes this fault: its `IA32_PL0_SSP` token is free at every `SYSCALL`, and any kernel jumping to `L0` from CPL 0 always finds `IA32_PL0_SSP` busy (because CPL-3 IST handlers switch onto `IA32_PL0_SSP` before entering kernel text, V3-5).
- **An NMI at L0 or L1** finds `SSP = 0`. The processor switches to `IST1`'s shadow stack and pushes `oldSSP = 0`; `IRETQ` (`RETURN-TO-SAME-PRIVILEGE-LEVEL`, SDM vol. 2A p. 3-495 [R]) checks `(tempSSP & 3) == 0` and canonical (both pass for `0`) and restores `SSP := 0`.
- **Return to user mode** is B.1.9.
- **Events from user mode on an IST vector (V3-5)** never leave the kernel on an IST shadow stack: `NMI` (`NMI_H0..H3`), `#DB` (`DB_H0..H3`) and `#MC` Row 7 (`M0..M9`) all evacuate the 6 user-context words to their per-core user block, free `ISTk` (`CLRSSBSY`), and acquire `IA32_PL0_SSP` (`SETSSBSY`) before jumping to kernel text. Consequently every CPL-3 entry (non-IST interrupt/exception, `SYSCALL`, `NMI`, `#DB`, `#MC` Row 7) enters kernel text with `SSP == PL0_SSP_OF[core]` and every IST token free; the IST shadow stacks need only single-frame depth (64 bytes below the token), and `U0`/`Y0` enforce `SSP == PL0_SSP_OF[core]` on return to CPL 3.
- **`IA32_CSTAR`** names the same row L0, or the GDT holds no compatibility-mode code segment (the case today; from memory that `SYSCALL` from compatibility mode uses it).

#### B.1.9 Returns: every `IRETQ` and every transition to CPL 3 (F1 and M1)

**What the processor does.**
- `IRET` loads IOPL from the frame when it executes at CPL 0: "IF CPL = 0 THEN EFLAGS(IOPL) := tempEFLAGS" (SDM vol. 2A, `IRET` pseudo-code [R]).
- On a return to CPL 3 it compares nothing with the shadow stack: "IF CS(RPL) != 3 THEN tempSsCS = shadow_stack_load 8 bytes from SSP+16; tempSsLIP = shadow_stack_load 8 bytes from SSP+8" (the same pseudo-code [R]). The comparison of CS and of the return address exists only for a return that stays in supervisor mode.
- With CPL ≤ IOPL every port is open: "If in protected mode and the CPL is less than or equal to the current IOPL, the processor allows all I/O operations to proceed. If the CPL is greater than the IOPL or if the processor is operating in virtual-8086 mode, the processor checks the I/O permission bit map" (SDM vol. 1 §20.5.2 [R]).
- IOPL can be set at CPL 0 without a frame: `POPF` there may change it ("All non-reserved flags except RF, VIP, VIF, and VM can be modified", `POPF` pseudo-code [R]); `SYSRET` keeps it ("RFLAGS := (R11 & 3C7FD7H) | 2" [R]; the mask holds bits 12 and 13); a far `RET` and `SYSEXIT` reach CPL 3 without touching RFLAGS [J].
- So a kernel that executes any of `IRET`, far `RET`, `SYSRET` or `SYSEXIT` gives its user code IOPL 3; user code is not scanned (G8); and G10's rule that port I/O is the gate's fails. And a core of the node that rewrites the CS, SS and RFLAGS words of a frame on a kernel-side stack turns a stub's own `IRETQ` into the same thing (M1).

**The closure, in two variants, for the owners to choose.**

| Path | Variant (a): the gate composes the frame (V13) | Variant (b): IOPL named outside the promise |
|---|---|---|
| Kernel text | Holds no `IRET` of any size, no far `RET` (opcodes CA, CB), no `SYSRET`, no `SYSEXIT`. `POPF` stays | Holds `IRETQ`, as in version 2. No `SYSRET`, no `SYSEXIT`, no far `RET` (they bring nothing the `IRETQ` does not) |
| Return to user mode after an event | The entry `ret_user`, rows U0 to U24 (with SSP check U2a) | The kernel's own `IRETQ` |
| Return to user mode after a system call | `ret_user`, or the entry `ret_user_fast`, rows Y0 to Y21 | The kernel's own `IRETQ` |
| Return to interrupted kernel code | The entry `ret_kernel`: rows U0 to U24 with `KERNEL_CS` and `KERNEL_SS` at U7 and U15, and without U2a, U10 and U11 | The kernel's own `IRETQ` |
| A stub's own return, window closed | Rows S0 to S17, on `F = F_BASE + 0x40` inside `RFRAME_OF` | `IRETQ` on the processor's frame, on a kernel-side stack |
| A stub's own return, window open | `IRETQ` on the processor's frame, which is on a gate-side stack (or `MC_R2` on `F` for `#MC`); the body's flags are kept | The same |
| Port I/O | The gate's alone, as G10 says | Open to every kernel through its user code |

**Variant (a), the rows.** Before it jumps to an entry, the kernel writes the seven words of its core's return block (B.1.2): at offsets 0 to 24 the context's RAX, RCX, RDX and R11; at 32 RIP; at 40 RFLAGS; at 48 RSP. Every other register already holds the context's value. The return frame sits at `F = F_BASE + 0x40` inside `RFRAME_OF` (leaving a 64-byte read-only guard zone `[F_BASE .. F_BASE + 0x3F]` below `F`, V3-7c): the context's RAX at `F`, then RIP, CS, RFLAGS, RSP, SS at `F + 8` to `F + 40`.

| Row | Instruction | Holds after it |
|---|---|---|
| U0 | `ENDBR64` | Nothing trusted |
| U1 | `CLI` | IF = 0 |
| U2 | `RDPID RAX` | This core's number |
| U2a | `RDSSPQ RCX`; `CMP RCX,[PL0_SSP_OF+RAX*8]`; `JNE T0` | **V3-5:** confirms `SSP` is at the top of this core's kernel shadow stack (`PL0_SSP_OF`), never on an IST shadow stack or with unpopped frames; any mismatch is **F** |
| U3 | `MOV RDX,[RBLOCK_OF+RAX*8]` | RDX = this core's return block (kernel-writable: its words are the kernel's choice) |
| U4 | `MOV RAX,[RFRAME_OF+RAX*8]`; `ADD RAX,40H` | RAX = `F = F_BASE + 0x40` inside this core's `RFRAME_OF` page (V3-7c) |
| U5 | `MOV RCX,[RDX+32]` | The RIP the kernel chose |
| U6 | `WRSSQ [RAX+8],RCX` | Frame: RIP |
| U7 | `MOV ECX,USER_CS` | An immediate |
| U8 | `WRSSQ [RAX+16],RCX` | Frame: CS. The return is to CPL 3 whatever the block holds |
| U9 | `MOV RCX,[RDX+40]` | The RFLAGS the kernel chose |
| U10 | `AND RCX,RFLAGS_USER_MASK` | IOPL, NT, RF, VM, VIF and VIP cleared: **masked in a register** (the constant of `abi/`, 0x0024_0DD5 as document 5 reads it, holds none of those bits) |
| U11 | `OR RCX,RFLAGS_FIXED` | IF = 1, bit 1 |
| U12 | `WRSSQ [RAX+24],RCX` | Frame: RFLAGS |
| U13 | `MOV RCX,[RDX+48]` | The RSP the kernel chose |
| U14 | `WRSSQ [RAX+32],RCX` | Frame: RSP |
| U15 | `MOV ECX,USER_SS` | An immediate |
| U16 | `WRSSQ [RAX+40],RCX` | Frame: SS |
| U17 | `MOV RCX,[RDX]` | The context's RAX |
| U18 | `WRSSQ [RAX],RCX` | Below the frame |
| U19 | `MOV R11,[RDX+24]` | The context's R11 |
| U20 | `MOV RCX,[RDX+8]` | The context's RCX |
| U21 | `MOV RDX,[RDX+16]` | The context's RDX |
| U22 | `MOV RSP,RAX` | RSP = `F` |
| U23 | `POP RAX` | The context's RAX; RSP = `F + 8` (ordinary supervisor data read from shadow-stack page, SDM vol. 3A §5.6.1 [R]) |
| U24 | `IRETQ` | At CPL 3 with IOPL 0; the `PL0_SSP` token at SSP is freed |

- **The whole of U0 to U24 is one restart range.** Its inputs are the core's number and the return block, neither of which it writes, so it can run twice. An NMI, a machine check or a `#DB` there is R to U0.
- **A fault of U24** (a RIP that is not canonical, a frame the kernel chose badly) raises `#GP(0)` with `RSP = F + 8 = F_BASE + 0x48`. The processor pushes the 6-word `#GP(0)` frame at `F_BASE + 0x18..0x47`, strictly inside the read-only `RFRAME_OF` page → `#PF` → serial `#PF` → `#DF` on `IST4` → `T0` (SDM vol. 3A Table 7-5 [R], V3-7c): **F**, for the node whose kernel chose it.
- **`ret_kernel`** differs by its two immediates (`KERNEL_CS`, `KERNEL_SS`) and by omitting `U2a`, `U10` and `U11`. Its `IRETQ` stays in supervisor mode, so the processor compares CS and RIP with the shadow stack (`RETURN-TO-SAME-PRIVILEGE-LEVEL` [R]): the kernel returns where it was interrupted and nowhere else, and the IST token (for CPL-0 NMI or `#DB`) is freed.
- **The stub's own return, rows S0 to S17.** At S0, RAX is the core's number, RCX the return address (N17), and RSP the stub's own (N5).

| Row | Instruction | Holds after it |
|---|---|---|
| S0 | `MOV RDX,[RFRAME_OF+RAX*8]`; `ADD RDX,40H` | RDX = `F = F_BASE + 0x40` (V3-7c) |
| S1 | `WRSSQ [RDX+8],RCX` | Frame: RIP, the address N19 wrote on the shadow stack |
| S2 | `MOV ECX,KERNEL_CS` | |
| S3 | `WRSSQ [RDX+16],RCX` | Frame: CS, an immediate: **the return cannot be to CPL 3** |
| S4 | `MOV ECX,2` | |
| S5 | `WRSSQ [RDX+24],RCX` | Frame: RFLAGS = 2. IF, TF, DF, NT and IOPL are 0 whatever the processor's frame holds |
| S6 | `MOV RCX,[RSP+24]` | The RSP word of the processor's frame (the interrupted context's; untrusted by class) |
| S7 | `WRSSQ [RDX+32],RCX` | Frame: RSP |
| S8 | `MOV ECX,KERNEL_SS` | |
| S9 | `WRSSQ [RDX+40],RCX` | Frame: SS |
| S10 | `MOV RCX,[RSP+40]` | The context's RAX, from the first slot |
| S11 | `WRSSQ [RDX],RCX` | Below the frame |
| S12 | `MOV RCX,[RSP+48]` | The context's RCX |
| S13 | `MOV RAX,RDX` | RAX = `F` |
| S14 | `MOV RDX,[RSP+56]` | The context's RDX |
| S15 | `MOV RSP,RAX` | RSP = `F` |
| S16 | `POP RAX` | |
| S17 | `IRETQ` | In gate text, at the address of S1, with RFLAGS = 2. The processor compares CS and the address with the shadow stack, and frees the token |

- **RFLAGS = 2 is right for every return into gate text while closed**: a restart range recomputes its flags; E2 and E3 return to E1, which sets them; the L rows, `H2..H3`, `M4`, `M9` and a `RET` use none.
- **The `#MC` stub's return (`MC_R2_0..MC_S17`, B.5.2)** uses the same frame composition at `F`, reading its words from `IST_SAVE_MC` on `RFRAME_OF` instead of `IST3`: keeping the saved RFLAGS for open-window or kernel `"continue"` returns, or using `USER_CS`, `USER_SS` and the mask of U10–U11 for CPL-3 `"continue"` returns.
- **One `RFRAME_OF` page per core is enough.** A stub nested in a stub, or in a return entry, overwrites `F` (`F_BASE + 0x40`) and returns to the first instruction of the range it interrupted, which writes every word of `F` again; `#MC`'s `IST_SAVE_MC`, `MC_RSHSTK` and `PARK_RSHSTK` occupy disjoint offsets on the same page (B.1.2).
- **`ret_user_fast`, rows Y0 to Y21** (optional; it has no `WRSSQ`). `SYSRETQ` loads RFLAGS from R11 and RIP from RCX, both registers. Split into two restart ranges (`Y0..Y13a` and `Y14..Y21`) so that `Y13a: JC T0` (V3-5) cannot fire falsely on a healthy node if an NMI arrives after `Y13: CLRSSBSY` has freed `PL0_SSP`:

| Row | Instruction | Holds after it | Part |
|---|---|---|---|
| Y0 | `ENDBR64` | | **Range 1 begins** |
| Y1 | `CLI` | | Range 1 |
| Y2 | `RDPID RAX` | | Range 1 |
| Y3 | `MOV RDX,[PL0_SSP_OF+RAX*8]` | RDX = the address of this core's kernel shadow-stack token | Range 1 |
| Y3a | `RDSSPQ RCX`; `CMP RCX,RDX`; `JNE T0` | **V3-5:** confirms `SSP == PL0_SSP_OF[core]` (never on an IST stack, never `0`, never unpopped frames); else **F** | Range 1 |
| Y13 | `CLRSSBSY [RDX]` | The kernel token free; `SSP = 0` ("RFLAGS.CF = (invalid_token == 1) ? 1 : 0 ... SSP := 0", `CLRSSBSY` pseudo-code [R]) | Range 1 |
| Y13a | `JC T0` | **V3-5:** if the `PL0_SSP` token was not busy → **F** (`T0` handles `SSP = 0` directly via `T14: RSTORSSP`) | Range 1 ends |
| Y14 | `RDPID RAX` | Reloads core number; `PL0_SSP` is already free and `SSP = 0` | **Range 2 begins** |
| Y15 | `MOV RAX,[RBLOCK_OF+RAX*8]` | RAX = the return block | Range 2 |
| Y16 | `MOV RCX,[RAX+32]` | The RIP the kernel chose | Range 2 |
| Y17 | `MOV R11,RCX` | | Range 2 |
| Y18 | `SAR R11,47` (**`56`** if `CR4.LA57 = 1`, V3-7b) | 0 for a canonical address in the user half | Range 2 |
| Y19 | `JNZ T0` | A RIP outside the canonical user half is **F** (`SYSRET` checks `IF (RCX is not canonical) THEN #GP(0);` before `CPL := 3`, SDM vol. 2B `SYSRET` pp. 4-709–4-710 [R], so non-canonical `RCX` would fault at CPL 0 with user `RSP`; `T0` handles `SSP = 0` directly via `T14: RSTORSSP`) | Range 2 |
| Y20 | `MOV R11,[RAX+40]`; `AND R11,RFLAGS_USER_MASK`; `OR R11,RFLAGS_FIXED`; `MOV RSP,[RAX+48]`; `MOV RDX,[RAX+16]`; `MOV RAX,[RAX]` | RFLAGS masked in a register (IOPL = 0); user RSP, RDX, RAX loaded | Range 2 |
| Y21 | `SYSRETQ` | At CPL 3 with IOPL 0 (`CS.Selector := (IA32_STAR[63:48]+16) OR 3`, `SS.Selector := (IA32_STAR[63:48]+8) OR 3` [R]). RCX and R11 are lost to the user, as at every system call | Range 2 ends |

- **Why two ranges for `ret_user_fast`.** If `Y13a: JC T0` sat inside a single restart range `Y0..Y21`, an NMI arriving between `Y13` and `Y21` would restart at `Y0`, re-run `Y13: CLRSSBSY [RDX]` against the already-free token (`CF := 1`), and panic a healthy node at `Y13a`! Splitting at `Y14` makes Range 1 (`Y0..Y13a`) restart at `Y0` (before `CLRSSBSY` executes) and Range 2 (`Y14..Y21`) restart at `Y14` (where `PL0_SSP` is already free and `SSP = 0`; only IST vectors can arrive, and they return to `Y14` with `SSP = 0`).

**What another core of the node can and cannot do.**

| | Variant (a) | Variant (b) |
|---|---|---|
| Change a word that an `IRETQ` or a `SYSRET` consumes | **No.** The frame is on `RFRAME_OF` (written by `WRSSQ`) or on a gate-side stack; `SYSRET` reads registers | **Yes**, every word of every frame on a kernel-side stack or a kernel stack |
| Reach CPL 3 with IOPL 3 | **No** | **Yes**: its own `IRETQ`, or a rewritten frame under a stub's `IRETQ` (M1) |
| Change the return block | Yes. Its words are the kernel's own choice of user RIP, RSP, registers and flags before the mask | — |
| Change the saved registers and the RSP and RFLAGS words of a frame the processor pushed on a kernel-side stack | Yes. They are read only as the interrupted context's values, and never for a context inside gate text (V12) | Yes, the same, and CS and SS too |
| Make a core return into gate text with IF or TF set | No (RFLAGS = 2) | Yes; the entry restarts or the `#DB` is fatal by V12, at the node's own cost |
| Reach the ports G10 reserves (0xCF8, 0xCFC, the reset port, another node's port entries) | **No** | **Yes** |

**The cost of variant (a), counted from the rows.**

| Event | Rows added | Of which | Estimate |
|---|---|---|---|
| Return to user mode after an interrupt or a fault | U0 to U23 (plus U2a), 28 instructions before `IRETQ` | 6 `WRSSQ`, 1 `RDPID`, 1 `RDSSPQ`, 10 loads, 1 `CLI`, 1 `POP`; plus the kernel's 7 stores into the return block | 6 × 9.3 cycles for the `WRSSQ` (the figure kernel.md cites for a Tiger Lake core, not re-opened) + about 35 for the rest: **85 to 105 cycles per event** (estimate) |
| Return to user mode after a system call | Y0 to Y20 (labels Y4 to Y12 unused after the split), 21 instructions before `SYSRETQ` | 1 `CLRSSBSY`, 2 `RDPID`, 1 `RDSSPQ`, 8 loads | About 35 to 55 cycles (estimate; no figure found for `CLRSSBSY`); `SYSRETQ` itself is cheaper than the `IRETQ` it replaces (from memory) |
| Return to interrupted kernel code | 22 rows | 6 `WRSSQ` | As the first row; rare in a kernel that runs with IF = 0 (an idle wake, an NMI) |
| An event inside closed gate text | S0 to S16, 17 rows | 6 `WRSSQ` | About 70 cycles (estimate), at a rare event |
| Memory | One 4 KB page per core (`RFRAME_OF`, shared by `F`, `IST_SAVE_MC`, `MC_RSHSTK` and `PARK_RSHSTK`), 56 bytes per core in `RBLOCK_OF`, 144 bytes per core in the three CPL-3 IST user blocks | | |

**Is there a closure paid only at a rare event?** I looked for anything that makes IOPL = 3 at CPL 3 harmless.
- **The I/O permission bitmap does not**: it is consulted only "If the CPL is greater than the IOPL" (§20.5.2 [R], quoted above); "protected mode in which, if the CPL is less than or equal to the IOPL, I/O access is allowed without checking the I/O permission bit map" (SDM vol. 3B, in the chapter on virtual-8086 mode [R]).
- **No bit of CR4 does**: I found none among its fields that bears on port I/O at CPL 3 (CR4.DE makes an I/O breakpoint possible, which reports the access after it happened). From a reading of the field list, not from a sentence that says so.
- **VMX does, and only VMX.** "Unconditional I/O exiting: This control determines whether executions of I/O instructions (IN, INS/INSB/INSW/INSD, OUT, ..." cause exits, and "Use I/O bitmaps ... whether I/O bitmaps are used to restrict executions of I/O instructions" (SDM vol. 3C, the primary processor-based controls [R]). **Variant (c):** on a machine whose image declares the hardening monitor of D-117, the monitor sets one of the two controls and the whole of variant (a) is unnecessary: nothing is paid per event. Without the monitor it does not exist.
- **Detection afterwards is not a closure**: the port write has happened.
- **Rejected as too clever:** returning to user mode by `SYSRET` at every event, with a user-side trampoline that restores RCX, R11 and the flags from a page of the thread. It needs no frame in memory, and costs a user ABI.
- **So, without the monitor, the answer is no**: the processor reads IOPL from memory at every `IRETQ`, and under shared kernel roots that memory is shared. Document 5 reached the same conclusion.

**What variant (b) gives away, stated exactly.** Any kernel, healthy-looking or not, can then drive every I/O port: the reset port (the machine restarts with no stop record), the ACPI and SMI command ports, another node's port entries, and the PCI configuration mechanism at 0xCF8 and 0xCFC. The last one is not an availability matter only: through configuration space a node can re-number the buses behind a bridge, and so give a device it drives the requester identifier of another node's device, whose IOMMU context then lets it write that node's memory (from memory of the PCI bridge registers and of how a unit keys its context entries; not read in a primary source: OPEN-7). If that holds, variant (b) is not "port I/O outside the promise"; it is "the adversarial promise is withdrawn on x86-64, and the faulty one stays". The owners should read it so.

#### B.1.10 Fatal to the node, and the park loop (closes ARGON-1, ARGON-2, ARGON-3, OPEN-2)

"F" is one path in gate text, reached by `JMP T0`. It reads nothing the processor pushed, makes no `CALL`, works for any entry `SSP` (including `SSP = 0` or arbitrarily deep IST stacks), and unconditionally frees all four IST shadow-stack tokens before clearing `MCIP` and before entering `park`.

| Row | Instruction | Holds after it |
|---|---|---|
| T0 | `RDPID RAX` | This core's number. **The restart range begins** |
| T1 | `MOV RCX,[ROOTS+RAX*8]` | This core's gate root |
| T2 | `MOV CR3,RCX` | The gate's root is loaded (again, if it was) |
| T3 | `MOV RSP,GATE_STACK_TOP` | An immediate: RSP on the gate stack, whatever it was |
| T4 | `MOV QWORD PTR [PANIC],PANIC_MARK` | `panic` written in the node beacon, at an address every gate root of the node maps. The gate lock is left as it is |
| T5 | `RDPID RAX` | This core's number |
| T6 | `MOV RDX,[IST1_SSP_OF+RAX*8]`; `WRSSQ [RDX],RDX` | **ARGON-1 / OPEN-2:** `IST1` shadow-stack token cleared unconditionally (`WRSSQ` does not touch `SSP` and never faults on an already-free token, SDM vol. 2D `WRSSD/WRSSQ` [R]) |
| T7 | `MOV RDX,[IST2_SSP_OF+RAX*8]`; `WRSSQ [RDX],RDX` | `IST2` shadow-stack token cleared unconditionally |
| T8 | `MOV RDX,[IST3_SSP_OF+RAX*8]`; `WRSSQ [RDX],RDX` | `IST3` shadow-stack token cleared unconditionally (already free before `T16` clears `MCIP`) |
| T9 | `MOV RDX,[IST4_SSP_OF+RAX*8]`; `WRSSQ [RDX],RDX` | `IST4` shadow-stack token cleared unconditionally |
| T10 | `MOV RDX,[RFRAME_OF+RAX*8]` | RDX = `F_BASE` |
| T11 | `LEA RDX,[RDX+2C0H]` | RDX = `PARK_RSHSTK` (32-byte aligned inside `RFRAME_OF`) |
| T12 | `LEA RCX,[RDX+1]` | RCX = `PARK_RSHSTK \| 1` (64-bit restore-SSP token) |
| T13 | `WRSSQ [RDX-8],RCX` | Restore-SSP token written at `[PARK_RSHSTK - 8]` |
| T14 | `RSTORSSP [RDX-8]` | `SSP := PARK_RSHSTK - 8` (succeeds for any prior `SSP`, including `SSP = 0`, without dereferencing old `SSP`, SDM vol. 2B `RSTORSSP` [R]; closes ARGON-2) |
| T15 | `MOV ECX,1`; `INCSSPQ RCX` | `SSP := PARK_RSHSTK` (SDM vol. 2A `INCSSPQ` [R]) |
| T16 | `MOV ECX,17AH`; `RDMSR`; `TEST EAX,4`; `JNZ mc_check_stop_or_clear_mcip` | **ARGON-3:** self-contained helper `mc_check_stop_or_clear_mcip` (part of the `T0..T26` restart range) scans only B.5.2 Rows 2–5 for `"stop the machine"` (jumping to the gate's stop entry if so), otherwise loads `ECX = 17AH, EAX = 0, EDX = 0`, executes `WRMSR` to clear `MCIP`, and jumps to `T17`. Never touches `RSP` and never re-enters `#MC` stub `N4..N17` |
| T17 | `RDPID RAX`; `MOV RDX,[RFRAME_OF+RAX*8]`; `LEA RDX,[RDX+2C0H]` | RDX = `PARK_RSHSTK` |
| T18 | `MOV RCX,[PL0_SSP_OF+RAX*8]`; `WRSSQ [RDX],RCX` | Shadow frame: `tempSSP = PL0_SSP` (the SSP the park loop will run on) |
| T19 | `LEA RCX,[park]`; `WRSSQ [RDX+8],RCX` | Shadow frame: `tempSsLIP = park` |
| T20 | `MOV ECX,KERNEL_CS`; `WRSSQ [RDX+16],RCX` | Shadow frame: `tempSsCS = KERNEL_CS` |
| T21 | `PUSH KERNEL_SS` | Frame on the gate stack, from immediates (`RSP` is `GATE_STACK_TOP` from `T3`) |
| T22 | `PUSH GATE_STACK_TOP` | |
| T23 | `PUSH 2` | RFLAGS: IF = 0 |
| T24 | `PUSH KERNEL_CS` | |
| T25 | `PUSH park` | |
| T26 | `IRETQ` | Pops `[PL0_SSP, park, KERNEL_CS]` from `PARK_RSHSTK`, sets `SSP += 24` (`PARK_RSHSTK + 24`, harmless `cmpxchg8b` on valid supervisor shadow-stack page `RFRAME_OF`), sets `SSP := PL0_SSP`, unblocks NMIs, enters `park` with **all four `IST1..IST4` tokens guaranteed free** and `MCIP = 0` |
| park | `HLT` | Under the gate's root, IF = 0, on the gate stack, all four IST tokens free |
| park + 1 | `JMP park` | |

- **`T0..T26` (including `mc_check_stop_or_clear_mcip`) is one restart range** (V12): an NMI or a `"continue"` `#MC` anywhere in `T0..T26` returns to `T0`, which reloads core number, gate root, `GATE_STACK_TOP`, re-clears `IST1..IST4` tokens, re-establishes `SSP := PARK_RSHSTK`, re-populates the shadow frame, and parks cleanly. Every row is idempotent: `T6..T9` write the same free-token values; `T13..T15` rewrite `[PARK_RSHSTK - 8]` and restore `SSP := PARK_RSHSTK` cleanly regardless of what `SSP` was at interruption.
- **Immediates.** Gate text, the gate stack and the kernel entry table lie in the top 2 GB of the address space, so that `GATE_STACK_TOP`, `park` and the absolute addresses of the read-only tables are 32-bit immediates and displacements.
- **How `ARGON-2` (`SSP = 0`) is resolved cleanly.** Any non-IST fault when `SSP = 0` (e.g. `#CP(SETSSBSY)` at `L1`, `NMI_H2`, `DB_H2`, `M4`) already faults during IDT delivery at `0xFFFF_FFFF_FFFF_FFFC` (`#PF` → serial `#PF` → `#DF` on `IST4` with `SSP = IST4_TOKEN - 24 != 0`, B.1.8); and if a direct gate jump reaches `T0` with `SSP = 0` (from `Y13a: JC T0` or `Y19: JNZ T0`), `T14: RSTORSSP` does not dereference old `SSP` and transitions cleanly onto `PARK_RSHSTK` with zero fault.
- **Closure of `OPEN-2` (`ARGON-1`).** Version 3 left `OPEN-2` open because `T9..T25` could leave an IST token busy whenever `T0` was entered with multiple frames on an IST shadow stack, risking a triple fault on a later NMI/`#DF` at `park`. In version 4: (1) `T6..T9` unconditionally clear `IST1..IST4` via `WRSSQ` before `T16` clears `MCIP` and before `T26: IRETQ` enters `park`; (2) `T0..T26` accesses only gate-side pages present by construction (`RFRAME_OF`, `IST1..IST4` shadow stacks, `GATE_STACK`, `PANIC`), so no fault can arise during `T0..T26`; (3) at `park`, all four `IST1..IST4` tokens are free, so any subsequent NMI or `"continue"` `#MC` is **D** cleanly on gate-side `IST1`/`IST3`, and `INIT` from the fence ends the loop. Property 9 of part E confirms this mechanically; trial T19 exercises `T0..T26` with pre-busied IST tokens and `SSP = 0`.

#### B.1.11 Short entries

Each entry is either windowed or has a restart range that ends before the acting instruction executes (V8, V12).

| Entry | Form | Restart range | Why it is sound |
|---|---|---|---|
| End of interrupt (x2APIC) | Short: `ENDBR64`; `CLI`; `MOV ECX,80BH`; `XOR EAX,EAX`; `XOR EDX,EDX`; `WRMSR`; `RET` | From `ENDBR64` up to, not including, the execution of `WRMSR` | Every register the `WRMSR` uses is loaded from an immediate in the range; an event at `RET` is D, so the write happens once |
| Timer deadline | Short: `ENDBR64`; `CLI`; `MOV RAX,RDI`; `MOV RDX,RDI`; `SHR RDX,32`; `MOV ECX,6E0H`; `WRMSR`; `RET` | As above | RDI is not written; any deadline is the caller's to choose. Start-up checks that the timer is in TSC-deadline mode |
| Interrupt to another core, ordinary vector | Short: rows I0 to I16 below | I0 up to, not including, the execution of I13 | Below |
| INIT, SIPI, NMI to another core | Windowed | — | They follow writes of the fence record or the start request |
| Port access | Windowed, under the gate lock | — | The ownership word of a port entry can be given away by another core between the check and the `OUT`; `memory_give` takes the same lock |
| `load_root` | Windowed | — | It writes the loaded root and tag, the tag's set and the idle word |
| EOI register of an IOAPIC; a device register | Windowed | — | The page is mapped only under a gate root (G9) |
| `ret_user`, `ret_user_fast`, `ret_kernel` (variant (a)) | Short: B.1.9 | The whole entry (`ret_user_fast`: two ranges, `Y0..Y13a` and `Y14..Y21`) | B.1.9 |
| `mc_collect` | Windowed | — | It reads the machine-check log; it clears nothing (B.5.2) |

**The interrupt to another core, as rows** (F4). Arguments: the vector in DIL, the target's core number in RSI.

| Row | Instruction | Holds after it |
|---|---|---|
| I0 | `ENDBR64` | |
| I1 | `CLI` | |
| I2 | `MOVZX EAX,DIL` | **EAX is the vector alone.** Bits 31:8 are 0: delivery mode 000 (fixed), destination mode 0 (physical), trigger mode 0 (edge), shorthand 00 (none) (SDM vol. 3A §13.12.9, Figure 13-28 [R]). The caller supplies no other bit of the ICR |
| I3 | `CMP EAX,IKV_FIRST` | |
| I4 | `JB I15` | Refused below the inter-kernel vectors |
| I5 | `CMP EAX,IKV_LAST` | |
| I6 | `JA I15` | Refused above them. `IKV_FIRST` and `IKV_LAST` are constants of `abi/` inside 240 to 255, so outside 0 to 31 and outside the claimable 48 to 239 |
| I7 | `CMP RSI,NCORES` | |
| I8 | `JAE I15` | Refused: not a core of the machine |
| I9 | `MOV EDX,[APICID_OF+RSI*4]` | EDX = the target's x2APIC identifier, from a read-only table. Never FFFF_FFFFH: "A destination ID value of FFFF_FFFFH is used for broadcast of interrupts in both logical destination and physical destination modes" (§13.12.9 [R]) |
| I10 | `MFENCE` | |
| I11 | `LFENCE` | G10's order |
| I12 | `MOV ECX,830H` | |
| I13 | `WRMSR` | The interrupt is sent |
| I14 | `RET` | |
| I15 | `MOV EAX,REFUSED` | |
| I16 | `RET` | |

- **Why the vector is bounded.** "The Intel 64 and IA-32 architectures reserve vectors 16 through 31 ... However, the local APIC does not treat vectors in this range as illegal" (SDM vol. 3A §13.5.2 [R]). A fixed interrupt with vector 18 would enter another node's #MC stub with MCIP clear, and row 1 of B.5.2 would declare that healthy node fatal.
- **Why the target is a core number and not an identifier (choice).** The gate never writes an identifier it did not read from its own table, so the broadcast value and an identifier of no core cannot be sent. The alternative, the caller's identifier checked against FFFF_FFFFH, leaves identifiers of no core, for which document 4 quotes "Interrupts to invalid destinations may be dropped or may go to logical processor(s) with APIC IDs that do not match the destination" [4].
- **A wild branch to I13** with an event taken first restarts at I0, which reloads EAX, EDX and ECX; without an event it is `#CP`, F.

#### B.1.12 What rests on interrupt remapping (M3)

**The fact.** A node that owns a device writes that device's MSI-X entries itself ("The per-vector mask bit of MSI-X sits in the device's table, in the driver's memory", the contract, Interrupts). The data word of a message holds a vector and a delivery mode: "Vector — This 8-bit field contains the interrupt vector associated with the message. Values range from 010H to 0FEH", and the delivery modes "000 - Fixed", "010 - SMI", "100 - NMI", "101 - INIT", "111 - ExtINT" (SDM vol. 3A §13.11.2 and Figure 13-25 [R]). So **without interrupt remapping a device driven by one node can send vector 18, or an NMI, an SMI or an INIT, to any core of the machine.** With remapping in the remappable format the device names only a handle ("a device cannot forge another interrupt", the contract), provided the unit blocks messages in the compatibility format (from memory of the VT-d specification, which is not among the files read: OPEN-7).

**The rows that assume no device can do that.**

| Row or sentence | What it assumes | What happens otherwise |
|---|---|---|
| B.0: "INIT is F ... sent only by a fence" | No device sends INIT | Any node resets any core of another node |
| B.5.2, row 1: MCIP = 0 is charged to the core's own node | No device and no other node sends vector 18 | A healthy node is declared fatal from outside |
| Every NMI cell, the bound "*H*" of B.1.6, and `NMI_GRACE_NS` | NMIs come from a fence round or a start wake, at most one per round | A device floods a core with NMIs: its gate calls restart for ever, a healthy node's |
| The stubs of vectors 16 to 31 | These vectors are raised by the processor only | A device raises `#CP` or `#AC` at another node's core: with the address in gate text, F for a healthy node |
| SMI is FW in every row | The rate of SMIs is the platform's | A device adds its own |

**The precondition** (part A, row 3): interrupt remapping on, compatibility-format messages blocked, and every remapping entry composed by the gate with fixed delivery and a vector in 48 to 239 (G9, D-150, already the rule). The contract's flag `Interrupts` bit 0 says whether remapping is on; a machine without it runs with the faulty-kernel promise only. The IOAPIC redirection entries and the LVT entries are written by the gate alone (unit registers; `WRMSR`), and the ICR by row I13. On ARM64 and RISC-V the corresponding writes (ITS mappings, `GICD_IROUTER`, APLIC targets) are the gate's already (G9).

### B.2 x86-64 mechanism 1: what it cannot do

D-120 names page tables typed as shadow-stack pages as the first mechanism to prototype. These are facts for the owners; the decision is in part D.

| # | Fact | Source | Consequence |
|---|---|---|---|
| 1 | `WRSSD` and `WRSSQ` raise `#UD` "If the LOCK prefix is used" | SDM vol. 2D, `WRSSD/WRSSQ`, 64-bit mode exceptions [R] | No compare-and-swap exists on a page typed as a shadow stack: an ordinary `LOCK CMPXCHG` faults there, since CR4.CET requires CR0.WP (§2.5, quoted in kernel.md). The contract requires that "Every write of the living part is a compare-and-swap". Mechanism 1 cannot write the living part, on a node of one core either, because other nodes write it at the same time |
| 2 | `WRSSD` stores 4 bytes and `WRSSQ` 8 | the same entry [3] | The page class byte cannot be written alone |
| 3 | "Data may be read (implicitly or explicitly) from any supervisor-mode address" | SDM vol. 3A §5.6.1 [R] | A unit's registers typed this way are readable by the kernel, against G9's "in no kernel's view". Whether a shadow-stack store to uncached device memory works at all is undocumented [3] |
| 4 | The processor pushes an interrupt frame by ordinary stores ("The old SS, RSP, RFLAGS, CS, and RIP are pushed onto the new stack", §7.14.5 [R]) and compares only CS and the return address at `IRET` (§7.12.1.1) | [R] | The frame lies on a page the kernel maps writable; another core of the node can change RFLAGS and RSP before the stub returns |
| 5 | G3 lets an iospace leaf target any *data* page | the contract | A device of the node can write the stub stacks unless they are kept memory (document 3: placing them in kept memory closes this one) |

**What mechanism 1 can still do:** write page-table entries on a node of one core, with a second mechanism beside it for the living part, for device registers and for the events. That is two mechanisms in one gate.

**One piece of it stays in variant (a) of B.1.9**: the return frame page (`RFRAME_OF`) and the machine-check log are pages typed as shadow stacks and written by `WRSSQ`. Facts 1 to 3 do not bear on them (no compare-and-swap, whole words only, nothing to hide from the kernel), and fact 4 is what they answer. Decision 1 should be read with that in view.

### B.3 ARM64

**Finding N4, corrected by F7.** Version 2 named `ERET` as the unchecked jump. The larger fact is that a plain `RET` is one too. Table D8-85 of the Arm ARM, "Values taken by PSTATE.BTYPE on execution of an instruction" [R], gives a non-zero BTYPE to the `BR` and `BLR` forms only, and ends:

> "ERET, ERETAA, ERETAB, and DRPS | Any | Any register | SPSR_ELx.BTYPE"
> "Any other instruction | Any | Any register | 0b00"

- So `ADR X30, A11; RET` lands on the opening instruction of B.3.2 with BTYPE = 0 and no Branch Target exception, with or without BTI, and with x11 the kernel's own value. An `ERET` does the same with `SPSR_ELx.BTYPE` = 0.
- **BTI never protected the entry against an adversarial kernel**, and not against a corrupted return address of a faulty one either. What protects it today is improbability.
- **Version 2's decision 2 (b)** (exception returns moved into gate text behind a check) does not close this, since `RET` remains. It is withdrawn as an option of its own.
- **FEAT_GCS would close both.** "When enabled, PSTATE.EXLOCK prevents MSR instructions from modifying the state of the ELR_ELx and SPSR_ELx, by causing such instructions to generate an EXLOCK Exception. When enabled, execution of an exception return instruction which targets the current Exception level will check PSTATE.EXLOCK and will set PSTATE.IL to cause an Illegal exception return" (Arm ARM D11, ICCMMC [R]); and a `RET` is compared with the Guarded Control Stack [J]. **Full enablement conditions (V3-8a):** in addition to `GCSCR_ELx` having `EXLOCKEN` and `RVCHKEN` set and `PUSHMEn` and `STREn` clear [J], Arm ARM D11.2.1 [R] requires **`GCSCR_ELx.PCRSEL = 1`** (`RBYVYL`: `"The Guarded Control Stack at ELx is PCR Selected if GCSCR_ELx.PCRSEL is 1, where x is 1 or greater."`), **`SCR_EL3.GCSEn = 1`** (when EL3 is implemented), and at EL0/EL1 when EL2 is implemented and enabled without `{E2H, TGE} == {1, 1}`, **`SCR_EL3.HXEn = 1` and `HCRX_EL2.GCSEn = 1`** (`RWFTRC`: `"The Guarded Control Stack at ELx is enabled if all of the following are true: • The Guarded Control Stack at ELx is PCR Selected. • If EL3 is implemented, SCR_EL3.GCSEn is 1. • If ELx is EL0 or EL1, then one of the following is true: — EL2 is not implemented or is disabled in the current Security state. — HCR_EL2.{E2H, TGE} is {1, 1}. — SCR_EL3.HXEn is 1 or EL3 is not implemented, and HCRX_EL2.GCSEn is 1."`). FEAT_GCS is "OPTIONAL from Armv9.3" [R] and no shipping core has it (kernel.md). B.3.2 is not re-walked with it.
- The same holds on RISC-V for `sret` with `sepc` and for a return (part A).

#### B.3.1 Mechanism 1 (a `TTBR1` context of the gate): memory and tags

- **The ASID.** "If the value is 0, then the TTBR0_ELx.ASID is used. If the value is 1, then the TTBR1_ELx.ASID is used" (Arm ARM D8.16.3.1, RSCBSR [R]). **`TCR_ELx.A1` = 1 for the life of the node** (choice): the ASID of an aspace is written into `TTBR1` at each switch of address space, with the kernel's tables; the gate's `TTBR1` value carries the gate's tables and `GATE_ASID`. Linux uses `A1` = 1 (from memory). Rejected: switching `TTBR0` too; a `TLBI` at every close.
- **`GATE_ASID`** is the highest ASID of the width read at start-up, bound to no root: the tag table of G7 loses one tag on ARM64 too.
- **Nothing that differs is global.** "If the value is 1, the translation is non-global and the TLB entry applies to only the current ASID value" (D8.16.3.1, RQGKGF [R]).
- **With FEAT_ASID2** ("OPTIONAL from Armv9.4 ... mandatory from Armv9.5", chapter A2 [R]) the design is unchanged.
- **A change of the gate's own view** uses the view epoch of B.1.3 and a local `TLBI ASIDE1` for `GATE_ASID`.
- **`SCTLR_ELx.EIS` = 1 and `EOS` = 1** where FEAT_ExS exists, so that an exception entry and an exception return synchronise a pending write of `TTBR1` ("Exception Entry is a context synchronization event", the description of `EIS` [R]; that both bits matter for the SDEI entry and its completion: [4]).

| Page | Address | Under the kernel's `TTBR1` | Under this core's gate `TTBR1` | nG | Class |
|---|---|---|---|---|---|
| Gate text, the SDEI entry, the read-only `ROOTS` table | Same on all cores | Read, execute | The same page | 0 or 1 | *global read-only* |
| **The vector page** (`VBAR_ELx`) | Same | The kernel's own vectors | A gate page whose every vector is the fatal path | 1 | kernel image; *gate* |
| Gate stack | `GATE_STACK`, same on all cores | Not present | Read, write | 1 | *gate* |
| Pending word of the core | Per core, one page per node | Read, write | The same page | 1 | kept, kernel-writable |
| Kernel text, data and stacks | As today | As today | Not present | 1 | as today |
| Tables, living part, gate part, GIC and SMMU registers | Gate's addresses | Read only or not present | Read, write | 1 | as today |

- **The vector page is a twin (choice).** Under the kernel's context the vectors are the kernel's own. Under the gate's context every vector is fatal, so it needs no scratch register and no test. Rejected: one stub that reads `TTBR1`, which needs a register before it can test.

#### B.3.2 Mechanism 1: the entry and exit

- **A-V10.** A healthy kernel calls with `SPSel` = 1. The gate returns with `SPSel` = 1, and with DAIF and `ALLINT` as they were at entry.
- **The SDEI entry tests the interrupted PC first** (F10). Firmware enters the registered entry, which is in gate text, with "X2 is set to the interrupted PC" and "PSTATE is modified as follows: DAIF = 0b1111, EL = ELC, nRW = 0, SP = 1" (SDEI §5.2.1 [R]). The entry compares X2 with the bounds of gate text. **Outside gate text:** the kernel's handler. **Inside gate text, open or not (cell D′):** with the fence mark on the core word, it closes the window if it is open and enters the fence handler, which never resumes; without it (a development stop), it raises the core's pending counter and completes the event, and firmware resumes the interrupted row: "The dispatcher must save and later restore the client Execution state that may be modified/corrupted by the handler" (§5.2.1.2 [R]). No kernel code runs for an event inside gate text; version 2's cell K′ is gone.

Columns: **Sync** synchronous exception of this instruction; **IRQ/FIQ**; **SErr** SError; **SDEI** event 0. At EL2 with VHE the same instructions name the EL2 registers [3]; `TPIDR_EL1` does not redirect [3] and is not used.

| Row | Instruction | Holds after it | Sync | IRQ/FIQ | SErr | SDEI |
|---|---|---|---|---|---|---|
| A0 | `bti c` (a `NOP` without BTI) | Nothing trusted | no | K | K | D′ |
| A1 | `mrs x9, daif` | x9 = caller's masks | no | K | K | D′ |
| A2 | `mrs x16, allint` (patched to `mov x16, xzr` where `SCTLR_ELx.NMI` is 0) | x16 = caller's `ALLINT` | no | K | K | D′ |
| A3 | `msr daifset, #0xf` | D, A, I, F masked | no | pended | pended | D′ |
| A4 | `msr allint, #1` (patched to `NOP` where `SCTLR_ELx.NMI` is 0) | Every IRQ and FIQ masked, with or without superpriority | no | pended | pended | D′ |
| A5 | `msr spsel, #1` | SP is `SP_ELx` | no | pended | pended | D′ |
| A6 | `mrs x10, mpidr_el1` | x10 = this core's affinity | no | pended | pended | D′ |
| A7 | `ubfx x10, x10, #s, #w` | x10 = core index | no | pended | pended | D′ |
| A8 | `adrp x12, ROOTS` | | no | pended | pended | D′ |
| A9 | `ldr x11, [x12, x10, lsl #3]` | x11 = this core's gate `TTBR1` value | no (present by construction); else the kernel's vector, the node's own fault | pended | pended | D′ |
| A10 | `mrs x13, ttbr1_el1` | x13 = caller's tables and ASID (trusted) | no | pended | pended | D′ |
| A11 | `msr ttbr1_el1, x11` | Written; in effect only after A12 | no | pended | pended | D′ |
| A12 | `isb` | **Open** | no | pended | pended | D′ |
| A13 | `mov x14, sp` | x14 = caller's SP (a value) | no | pended | pended | D′ |
| A14 | `adrp x15, GATE_STACK_TOP` | | no | pended | pended | D′ |
| A15 | `mov sp, x15` | SP on the gate stack | no | pended | pended | D′ |
| A16 | `stp x13, x14, [sp, #-48]!` | Saved privately | F | pended | pended | D′ |
| A17 | `stp x9, x30, [sp, #16]` | Saved privately | F | pended | pended | D′ |
| A18 | `str x16, [sp, #32]` | Saved privately | F | pended | pended | D′ |
| — | body | G12 (2) after every store | F | pended | pended | D′ |
| Z0 | `ldr x16, [sp, #32]` | | F | pended | pended | D′ |
| Z1 | `ldp x9, x30, [sp, #16]` | | F | pended | pended | D′ |
| Z2 | `ldp x13, x14, [sp]` | For `load_root`: the body rewrote this slot, so x13 is the kernel's tables with the new ASID | F | pended | pended | D′ |
| Z3 | `mov sp, x14` | Caller's SP, **before** the close | no | pended | pended | D′ |
| Z4 | `msr ttbr1_el1, x13` | Written | no | pended | pended | D′ |
| Z5 | `isb` | **Closed** | no | pended | pended | D′ |
| Z6 | `msr allint, x16` (patched to `NOP` where `SCTLR_ELx.NMI` is 0) | Caller's `ALLINT` | no | pended | pended | D′ |
| Z7 | `msr daif, x9` | Caller's masks; pended interrupts are taken here, by the kernel's vectors | no | K | K | D′ |
| Z8 | `ret` | | K (the caller's) | K | K | D′ |

- **`ALLINT` (F8).** With `ALLINT` = 1, "If SCTLR_ELx.NMI is 1 and execution is at ELx, an IRQ or FIQ interrupt that is targeted to ELx, with or without Superpriority, is masked" (Arm ARM C5.2.1 [R]). Version 2 set it and never restored it, so a core with FEAT_NMI in use stopped taking interrupts after its first gate call. Rows A2, A4 and Z6 are patched by `SCTLR_ELx.NMI`, which the gate writes, not by the feature's presence; without FEAT_NMI "direct accesses to ALLINT are UNDEFINED" (C5.2.1 [R]), so the three rows are then `mov x16, xzr`, `NOP`, `NOP`.
- **`MPIDR` (F9).** The affinity fields are separate bytes, with "Aff3, bits [39:32]" apart from "Aff2, bits [23:16]", "Aff1, bits [15:8]" and "Aff0, bits [7:0]" (D24.2 [R]). The constants *s* and *w* of A7 are chosen at start-up so that the extracted field differs for every core of the machine; **the start-up checks it**, sizes `ROOTS` to 2^*w* entries, and refuses a machine for which no field of at most 16 bits does it (one that needs Aff3 among them). Document 4 proposes a per-core `VBAR_ELx` as on RISC-V in place of the extract; it would remove the check and is not taken here.
- **`msr spsel, #1` at A5.** An exception sets "PSTATE.SP = '1'" (`AArch64_TakeException` [R]); without A5 a caller with `SPSel` = 0 would leave `SP_ELx` its own while A15 wrote `SP_EL0`. A-V10 states what the caller gets back.
- **A11 to A12, and Z4 to Z5.** Between the write and the `isb` the translation in use is either one; the instructions lie in gate text, mapped the same in both. The SDEI entry's reads of `TTBR1` there return the written value: "All direct writes to a register occur in program order with respect to all direct reads to the same register using the same encoding" (D24.1.2.2 [R]). Version 2 had this as UNVERIFIED.
- **IRQ and FIQ at A0 to A2** reach the kernel's vectors with the PC in gate text (cell K): nothing trusted exists yet, as at P0 and P1 on x86-64.
- **A synchronous exception while open** enters the gate-side vector page: fatal, with no register to save.
- **SError** is masked by A3 and pended; where the platform routes it to EL3 it is firmware's.
- **SP is moved after the open and restored before the close** (A13 to A15, Z3).
- **The deferred development stop** is a counter the SDEI entry raises and the kernel compares with its own at the end of each kernel event.

#### B.3.3 Mechanisms 1′, 2 and 3 (version 2's OPEN-3)

| Mechanism | Verdict | The text |
|---|---|---|
| 1′, widening `TCR_EL1.T1SZ` | **Usable only with a local TLB invalidation at each close** | "Any of the bits in TCR_EL1, other than the EPDx bits when they have the value 1, and the A1 bit are permitted to be cached in a TLB" (D24.2, `TCR_EL1` [R]); "When a System register field is modified and that field is permitted to be cached in a TLB, software is required to invalidate all TLB entries that might be affected by the field" (D8, RVNRFW [R]). After the range is narrowed nothing guarantees a fault on the gate's addresses |
| 2, permission overlays | **Viable**; the table below | "Stage 1 Overlay permissions are not permitted to be cached in a TLB. POIndex is permitted to be cached in a TLB" (D8.4, ISKPNZ [R]); "The POE field is not permitted to be cached in a TLB" (IKPGBV [R]). No shipping core (kernel.md) |
| 3, GCS pages written by `GCSSTR` | **Unusable alone**, as x86-64's mechanism 1 | "Management of EL1 Guarded Control Stack pages is possible from EL1 by using the GCSSTR or GCSPUSHM instructions" (D11, SGRGDT [R]): stores, and no compare-and-swap. For a memory type other than Normal write-back memory, "it is CONSTRAINED UNPREDICTABLE whether: A Data Abort for unsupported access ... is generated ... The access proceeds using the specified memory type" (D11.10, RFFJDX [R]); document 4 reads this as an abort, the text says either. So neither the living part nor a device register can be written this way |

**The cost of 1′, counted.** Each close adds one local invalidation of the gate's range (a `TLBI` and its barrier), and each call then starts with none of the gate's translations cached, so it pays a table walk for every page it touches: the gate stack, the gate part, each table page and each living-part page of the call. That is one `TLBI` and some four to ten walks per call (estimate), to set against the 210 to 424 cycles Hilps reports (as kernel.md cites; whether that figure includes an invalidation I did not read). Mechanism 1 pays none of it. Document 5 notes that `A1` is the one field of the quotation that is not cached; a design that flips `A1` in the same write is mechanism 1 by another route.

**Mechanism 2, as rows (V3-8c and OPEN-8 closed [R]).** `TCR2_ELx.POE` = 1. Every page the gate writes keeps its place in the kernel's own tables with a base permission of read and write, and carries one of two overlay indexes: *G*, for pages the kernel may read (tables, the living part, the gate part), and *H*, for pages it may not (the gate stacks, unit registers). `POR_ELx` holds, for privileged access, "POR_EL1[(POIndex*4 + 3): POIndex*4]" (Table D8-72 [R]). Closed: field *G* = `0b0001` ("PrivRead", Table D8-74 [R]), and field *H* = `0b0000`. Open (`POR_OPEN`): **both fields *G* and *H* = `0b0101`** (`PrivRead | PrivWrite`, **never** `PrivExecute`). Table D8-74 [R] defines `0b0101` as `"PrivRead / UnprivRead"` and `"PrivWrite / UnprivWrite"`, and D24.2.150 (`POR_EL1` [R]) confirms `"0b0101 | Write, Read."` **Why `PrivExecute` must never be set in `POR_OPEN` (V3-8c):** Arm ARM `RQXXPC` [R] states `"If S1PrivOverlay is enabled and the stage 1 Overlay permission PrivExecute is present, then the stage 1 Overlay permission PrivWrite is removed."` The two values `POR_CLOSED` and `POR_OPEN` are constants, the same on every core.

| Row | Instruction | Holds after it | Sync | IRQ/FIQ | SErr | SDEI |
|---|---|---|---|---|---|---|
| Q0 | `bti c` | Nothing trusted | no | K | K | D′ |
| Q1 | `mrs x9, daif` | | no | K | K | D′ |
| Q2 | `mrs x16, allint` (patched) | | no | K | K | D′ |
| Q3 | `msr daifset, #0xf` | Masked | no | pended | pended | D′ |
| Q4 | `msr allint, #1` (patched) | | no | pended | pended | D′ |
| Q5 | `msr spsel, #1` | | no | pended | pended | D′ |
| Q6 | `mov x11, #POR_OPEN` (two rows if the constant needs a `movk`) | An immediate | no | pended | pended | D′ |
| Q7 | `msr por_el1, x11` | Written | no | pended | pended | D′ |
| Q8 | `isb` | **Open**: this core may write the pages of *G* and *H* | no | pended | pended | D′ |
| Q9 | `mrs x10, mpidr_el1` | | F | pended | pended | D′ |
| Q10 | `ubfx x10, x10, #s, #w` | Core index | F | pended | pended | D′ |
| Q11 | `adrp x12, GSTACKS` | | F | pended | pended | D′ |
| Q12 | `ldr x15, [x12, x10, lsl #3]` | This core's gate stack (a per-core address: the translation is the same on every core) | F | pended | pended | D′ |
| Q13 | `mov x14, sp` | | F | pended | pended | D′ |
| Q14 | `mov sp, x15` | | F | pended | pended | D′ |
| Q15 | `stp x14, x30, [sp, #-32]!` | | F | pended | pended | D′ |
| Q16 | `stp x9, x16, [sp, #16]` | | F | pended | pended | D′ |
| — | body | | F | pended | pended | D′ |
| Y0′ | `ldp x9, x16, [sp, #16]` | | F | pended | pended | D′ |
| Y1′ | `ldp x14, x30, [sp]` | | F | pended | pended | D′ |
| Y2′ | `mov sp, x14` | | F | pended | pended | D′ |
| Y3′ | `mov x11, #POR_CLOSED` | An immediate | F | pended | pended | D′ |
| Y4′ | `msr por_el1, x11` | | F | pended | pended | D′ |
| Y5′ | `isb` | **Closed** | no | pended | pended | D′ |
| Y6′ | `msr allint, x16` (patched) | | no | pended | pended | D′ |
| Y7′ | `msr daif, x9` | | no | K | K | D′ |
| Y8′ | `ret` | | K | K | K | D′ |

- **What differs from mechanism 1.**
  1. *No tag is reserved, no root is per core, nothing must be non-global, and no TLB rule exists*: the overlay is read at each access.
  2. *The opening value is an immediate*, so no table is read before the open.
  3. *Kernel text stays mapped and executable while the window is open.* Rule V1 then rests on control flow alone: the masks of Q3 and Q4, and the vector stub below. This is weaker than mechanism 1, where the kernel's text is not present.
  4. *The vector page cannot be a twin.* Every vector of `VBAR_ELx` is a gate stub that needs one scratch register before it can test: `msr <scratch>, x0`; `mrs x0, por_el1`; a compare with `POR_CLOSED`; if it differs, the fatal path (which closes first); otherwise `mrs x0, <scratch>` and a branch to the kernel's vector. The scratch register is `TPIDR_EL1` at EL2 with VHE, where the kernel does not use it, and `TPIDRRO_EL0` at EL1, which the kernel then rewrites at each return to EL0 (Linux's trampoline for its split tables uses it so: from memory). Cost: three system-register accesses and a compare at every exception the kernel takes.
  5. **`isb` at `Q8` and `Y5′` is mandatory (OPEN-8 closed [R]).** Arm ARM D24.1.2.2 ("Synchronization requirements for AArch64 System registers" [R]) states: `"Unless otherwise stated in its System register definition, a direct write to a System register requires synchronization before software can rely on the effects of that write to affect instructions appearing in program order after the write. This does not apply to Special-purpose registers."` and `"Explicit synchronization occurs as a result of a Context Synchronization event, which is one of the following events: • Execution of an ISB instruction."` D24.2.150 (`POR_EL1` [R]) grants no exemption, so `Q8` and `Y5′` are required.
- **Against an adversarial kernel (V3-8b)** mechanism 2 is weaker still than mechanism 1: a `RET` onto **`Q7` or `Y4′`** with its own `x11` opens the window persistently with the kernel's text mapped (at `Y4′`, `isb`, `msr allint`, `msr daif`, and `ret` immediately return to the caller with `POR_OPEN` active). Against a faulty one it is the simplest of the three.

### B.4 RISC-V, mechanism 1 (a `satp` root of the gate)

- **The ASID and the TLB.** "The number of ASID bits is UNSPECIFIED and may be zero" and "writing satp does not imply any ordering constraints between page-table updates and subsequent address translations, nor does it imply any invalidation of address-translation caches" (RISC-V priv §10.1.11 [R]). So: with ASIDLEN > 0, `GATE_ASID` is the highest ASID, bound to no root (G7 loses one tag); with ASIDLEN = 0, an `sfence.vma x0, x0` follows the opening and the closing `csrw satp` ("If the implementation does not provide ASIDs, or software chooses to always use ASID 0, then after every satp write, software should execute SFENCE.VMA with rs1=x0", §10.2.1 [R]).
- **Nothing that differs is global.** "The G bit designates a global mapping. Global mappings are those that exist in all address spaces" (§10.3.1 [R]).
- **Finding the hart.** Supervisor mode has no trusted hart number. `stvec` is written by the gate only, with one value per hart, **in direct mode** ("1 Vectored Asynchronous interrupts set pc to BASE+4×cause", §10.1.2, Table 21 [R]: in vectored mode the value read at R3 would have its low bit set); the page after it is a read-only per-hart page that holds the hart's gate `satp` value and its gate stack top (choice, from version 1). The `stvec` page is a twin as on ARM64: the kernel's trap entry under the kernel's root, a fatal stub under the gate's.

| Row | Instruction | Holds after it | Sync | S-interrupt | M-trap |
|---|---|---|---|---|---|
| R0 | landing pad (where Zicfilp exists) | Nothing trusted | no | K | FW |
| R1 | `li t5, SIE+SUM+MXR` | | no | K | FW |
| R2 | `csrrc t0, sstatus, t5` | SIE, SUM, MXR clear; t0 = caller's `sstatus` | no | no (SIE = 0) | FW |
| R3 | `csrr t1, stvec` | t1 = this hart's trap page | no | no | FW |
| R4 | `ld t2, GSATP(t1)` | t2 = this hart's gate `satp` | no (present by construction); else F | no | FW |
| R5 | `csrr t3, satp` | t3 = caller's root and ASID (trusted) | no | no | FW |
| R6 | `csrw satp, t2` | **Open** | no | no | FW |
| R7 | `sfence.vma x0, x0`, only when ASIDLEN = 0 | No entry of the kernel's view remains | no | no | FW |
| R8 | `mv t4, sp` | t4 = caller's sp (a value) | no | no | FW |
| R9 | `ld sp, GSTACK(t1)` | sp on the gate stack | no (the same page as R4); else F | no | FW |
| R10 | `sd` of t0, t3, t4, ra on the gate stack (four rows) | Saved privately | F | no | FW |
| — | body | | F | no | FW |
| S0 | `ld` of t0, t3, t4, ra (four rows) | For `load_root`: the body rewrote the slot of t3, so S2 closes to the new root | F | no | FW |
| S1 | `mv sp, t4` | Caller's sp, before the close | no | no | FW |
| S2 | `csrw satp, t3` | **Closed** | no | no | FW |
| S3 | `sfence.vma x0, x0`, only when ASIDLEN = 0 | No entry of the gate's view remains | no | no | FW |
| S4 | `andi t0, t0, SIE` | | no | no | FW |
| S5 | `csrs sstatus, t0` | Caller's SIE; a pending interrupt is taken here | no | K | FW |
| S6 | `ret` | | K | K | FW |

- **Trap entry saves nothing in memory**: "When a trap is taken into supervisor mode, SPIE is set to SIE, and SIE is set to 0" (§10.1.1 [R]); `sepc`, `scause` and `stval` are registers.
- **No supervisor interrupt is taken in supervisor mode with SIE = 0**: "The SIE bit enables or disables all interrupts in supervisor mode. When SIE is clear, interrupts are not taken while in supervisor mode" (§10.1.1 [R]).
- **R-V10.** The gate returns with SUM = 0 and MXR = 0 (R2 clears them and nothing restores them), and with SIE as it was at entry (S4, S5).
- **sp is moved after the open and back before the close**, as on ARM64 (document 3).
- **Machine-mode traps** run firmware and return by `mret` or never (`fence_hart`); a resumable NMI of Smrnmi stays in machine mode and returns by `mnret` (chapter 8 [4]); this holds only if firmware never redirects a trap into supervisor code while the gate's root is loaded, which is firmware's promise.
- **`sscratch` and `tp`** stay the kernel's and are never read by the gate.
- **Mechanism 2** (Zicfiss pages written by `SSAMOSWAP`): the instruction is a swap, not a compare-and-swap; whether a compare-and-swap can be built on such a page is UNVERIFIED (the Zicfiss specification is not in the edition I read). Same question as B.2, fact 1.

### B.5 Machine checks

#### B.5.1 x86-64: what the manual fixes

- **A second machine check before MCIP is cleared stops the processor.** "The occurrence of a second Machine-Check Event while MCIP is set will cause the processor to enter a shutdown state" (SDM vol. 3B §18.3.1.2 [R]); "Before returning from the machine-check exception handler, software must clear the MCIP flag" (§18.11.4.1 [R]). Clearing it is a `WRMSR`, so it is the gate's.
- **Broadcast.** "an MCA signal is broadcast to all logical processors in the system" from family 6 model 0EH on, and "the MCE handler may be required to synchronize with the other processors that received a machine check error and serialize access to the machine check registers" (§18.11.4.1 [R]); except with LMCE, when "hardware can choose to report the error to only a single logical processor". LMCE needs firmware: "System software must ensure that both IA32_FEATURE_CONTROL.Lock (bit 0) and IA32_FEATURE_CONTROL.LMCE_ENABLED (bit 20) are set before attempting to set IA32_MCG_EXT_CTL.LMCE_EN" (§18.3.1.5 [R]).
- **Without `MCG_SER_P` nothing is recoverable.** "When IA32_MCG_CAP [24] is zero, there are no recoverable errors supported and all machine-check are fatal exceptions", and then "any uncorrected error condition (VAL =1 and UC=1) including the one with the EN flag cleared are fatal" (§18.11.4.1 [R]). Bits 56:55 of a bank's status are S and AR only "If IA32_MCG_CAP[24] is 1" (§18.3.2.2 [R]).
- **PCC.** "If the PCC flag is set for enabled uncorrected errors (UC=1 and EN=1), recovery is not possible" (§18.11.4.1 [R]).
- **SRAR, SRAO, UCNA** are the rows of Table 18-7 (§18.6.3 [R]). For an SRAR with OVER set, "the MCE handler must signal the operating system to reset the system" (§18.11.4.1 [R]).
- **Who is affected.** Table 18-21 (§18.10.3.2 [R]): the affected logical processor has RIPV 1 and EIPV 1 (continuable) or RIPV 0; the others have RIPV 1 and EIPV 0. `LMCE_S` "Indicates (when set) that ... the current machine-check event was delivered to only this logical processor" (§18.3.1.2 [R]).
- **A software vector 18.** "If it is not set, this machine check was generated by either an INT 18 instruction or some piece of hardware signaling an interrupt with vector 18" (§18.11.4.1 [R]).
- **Shared banks** are found by the CMCI ownership protocol: each thread examines `IA32_MCi_CTL2[30]` "to determine if another thread has already claimed ownership of that bank" (§18.5.2.1 [R]).

#### B.5.2 x86-64: the rule

The `#MC` stub is gate text and decides **before any other code runs and before any open-vs-closed dispatch (V3-2b)**. It scans this core's banks (`IA32_MCG_CAP[7:0]`) and takes the first row that applies.

| # | Condition | Verdict | Whose error |
|---|---|---|---|
| 1 | MCIP = 0 | F | This node's, **because the gate composes every vector that hardware can signal** (the ICR at row I13, the LVT entries, the IOAPIC entries, the remapping entries) and vector 18 is not among them; so only an `INT 18` at CPL 0 remains. This holds under preconditions 3 and 4 of part A only (B.1.12). Version 2's reason, "only code at CPL 0 can raise vector 18", ignored the manual's own "or some piece of hardware signaling an interrupt with vector 18" |
| 2 | `MCG_SER_P` = 0 and some bank has VAL and UC | **Stop the machine** | Nobody's to recover: the manual calls it fatal |
| 3 | Some bank has VAL, UC, EN and PCC | **Stop the machine** (choice, below) | A processor whose state may be corrupt |
| 4 | Some bank has VAL, UC, EN, S, AR and OVER | **Stop the machine** | The manual's rule |
| 5 | SRAR (VAL, UC, EN, S, AR, no PCC, no OVER) and this core is affected (`LMCE_S`, or EIPV, or RIPV = 0), interrupted in gate text or in the window | F if `ADDRV` and the address lies in memory this node owns (a taken chunk, its floor, its gate part); otherwise **stop the machine** (the data was shared: the living part, the kept image, gate text) | This node's, or the machine's |
| 6 | The same, interrupted in the node's kernel (CPL 0, outside gate text) | F (choice: Linux panics on such an error in kernel context unless a fix-up exists, from memory) | This node's |
| 7 | The same, interrupted at CPL 3 | The kernel's handler, entered by rows `M0..M9`, which faults the thread (hardware error, code 7) and does not resume it | This node's thread |
| 8 | RIPV = 0 and no bank explains it | As rows 5 to 7 by the interrupted context, with no address | This node's |
| 9 | SRAO (S, no AR) or an uncorrected error with EN = 0, and none of the above | **Continue**: log, clear, mark the pending word, free `IST3`, switch `SSP`, clear MCIP, return | The node that owns the address; each kernel reads the log and judges by the address |
| 10 | Nothing valid and uncorrected in this core's banks, RIPV = 1 | **Continue**, as row 9 | Another core's (deferred) |

**The `#MC` stub, in order (closes V3-1, V3-2a/b/c, V3-3a/b/c, V3-5).** It begins with the four harmless pre-redo rows `MC_N0..MC_N3` (`ENDBR64`; save `RAX, RCX, RDX` at `[RSP+40..56]`), followed by three restart ranges (`Range 1a`, `Range 1b` = `MC_SW0..MC_SW8`, and `Range 2` = `MC_R2_0..MC_S17` / `MC_JNMI_*`) for `"continue"`, or `M0..M9` for Row 7:

| Step / Range | What | Restart range |
|---|---|---|
| `MC_N0..MC_N3` | `ENDBR64`; save `RAX, RCX, RDX` at `[RSP+40..56]` | Before redo label: harmless rows (V12 item 5) |
| **Range 1a — Capture & Guard** (`MC_N4`) | `RDPID RAX`; `MOV RSP,[ISTTOP_MC+RAX*8]`; `RDSSPQ RDX`; `MOV RCX,[IST3_SSP_OF+RAX*8]`. Exact `SSP` check: `SSP == IST3_TOKEN` (CPL 3) or `SSP == IST3_TOKEN - 24` (CPL 0); any other `SSP` → `JMP T0` (**F**). **Range-2 guard FIRST:** if CPL 0 and `LIP = [RDX+8]` lies in Range 2 (`MC_R2_0..MC_S17` or `MC_JNMI_*`), set local `is_mc2 = 1` and **skip capture** so `IST_SAVE_MC` and `MC_RSHSTK` retain `MC1`'s context. Otherwise (`is_mc2 = 0`), capture `rip`, `rflags`, `rsp`, `rax`, `rcx`, `rdx` (and for CPL 0: `old_ssp = [RDX]`, `old_lip = [RDX+8]`) into **`IST_SAVE_MC`** on `RFRAME_OF` via `WRSSQ` for **all** contexts (open window, closed gate text, kernel, CPL 3 — closes **V3-2c**), leaving `row7_sticky` untouched | **Range 1a** (`MC_N4`) |
| **Range 1a — Step 1** | **Verdict FIRST, before open/closed dispatch (closes V3-2b):** if `is_mc2 == 0` and `IST_SAVE_MC.row7_sticky == 1` → **Row 7** (closes **V3-3a**). Otherwise read `CR3 & 0xFFF == GATE_PCID` (open flag), `IA32_MCG_STATUS`, and each bank's status (`IA32_MCG_CAP[7:0]`), classifying Rows 1–10 using the captured CPL, open flag and `old_lip` | Range 1a |
| **Range 1a — Step 2** | `"Stop the machine"`: gate stop entry. **F**: `JMP T0` (where `T6..T16` frees `IST1..IST4`, switches `SSP` to `PARK_RSHSTK` and clears `MCIP`). Neither clears a bank | Range 1a |
| **Range 1a — Step 3** | **Row 7:** (1) `WRSSQ [F_BASE + IST_SAVE_MC_ROW7], 1` (**latch `row7_sticky = 1` before Step 4 clears any owned bank**, closes **V3-3a**); (2) copy the 6 user-context words into dedicated **`MCUSER_BLOCK_OF[core]`** (`C0..C13` below, never touched by `"continue"`, closes **V3-3c**). **`"Continue"` (`is_mc2 == 0`):** classify `old_lip` (B.1.7) and write `return_mode` and `target_ssp` into `IST_SAVE_MC` via `WRSSQ`: (a) **NMI stub** (`NMI_N0..N3`: copy `IST_SAVE_MC.{rax,rcx,rdx}` to `[IST1_TOP+40..56]`, `mode = JMP_NMI_N4`, `target_ssp = old_ssp`; `NMI_N4..S17` / `NMI_H_COPY..H1`: `mode = JMP_NMI_N4`, `target_ssp = old_ssp`; `NMI_H2`: `mode = JMP_NMI_H2`; `NMI_H3`: `mode = JMP_NMI_H3`, `target_ssp = PL0_SSP_OF[core]`); (b) **CPL 0 outside NMI stub** (`OPEN_CONT`, `CLOSED_GATE`, `KERNEL_CONT`): populate `MC_RSHSTK[0..23]` = `{old_ssp, return_lip, KERNEL_CS}` and `[MC_RSHSTK+24] = MC_RSHSTK+24`, set `target_ssp = MC_RSHSTK`; (c) **CPL 3** (`CPL3_CONT`): write `[MC_RSHSTK+24] = MC_RSHSTK+24`, set `target_ssp = MC_RSHSTK+24` (note below). **`"Continue"` (`is_mc2 == 1`):** leave `IST_SAVE_MC` and `MC_RSHSTK` unchanged | Range 1a |
| **Range 1a — Step 4** | For `"continue"` and Row 7: for each bank this core owns (CMCI protocol) that has `VAL = 1`, four `WRSSQ` write its bank number, status, address and misc words into the core's machine-check log, one `WRSSQ` advances the log write index, and one `WRMSR` (with all three operands loaded in Range 1a) clears the bank's status. For `"continue"` (both `MC1` and `MC2`): `LOCK OR QWORD PTR [KPEND+RAX*16], MC_BIT`. Branch: Row 7 → `M0`; `"continue"` → `MC_SW0` | Range 1a ends |
| **Range 1b — Free `IST3`, Switch `SSP`, Clear `MCIP`** (`MC_SW0..MC_SW8`) | Frees `IST3` token and switches `SSP` onto `target_ssp` (or `0` for `JMP_NMI_H2`) **before** `WRMSR 0x17A` clears `MCIP` (table below; closes **V3-2a**). Idempotent if an NMI restarts at `MC_SW0` | **Range 1b** (`MC_SW0`) |
| **Range 2 — Return / Direct NMI Resume** (`MC_R2_0..MC_S17`, `MC_JNMI_*`) | Dispatches by `IST_SAVE_MC.return_mode`: NMI-interrupted modes execute a direct **`JMP NMI_N4` / `JMP NMI_H2` / `JMP NMI_H3`** with zero `IRETQ` (closes **V3-1**); all other `"continue"` modes compose the 6-word frame at `F = F_BASE + 0x40` from `IST_SAVE_MC` (keeping `rflags` for open/kernel, `2` for closed gate, or masked user flags + `USER_CS`/`USER_SS` for CPL 3), restore `RCX, RDX`, `MOV RSP, F`, `POP RAX`, `MC_S17: IRETQ` | **Range 2** (`MC_R2_0`) |

**Rows `MC_SW0..MC_SW8` (Range 1b: free `IST3`, switch `SSP`, clear `MCIP` — closes V3-2a).**

| Row | Instruction | Holds after it |
|---|---|---|
| MC_SW0 | `RDPID RAX` | Core number. **Range 1b begins** |
| MC_SW1 | `MOV RDX,[RFRAME_OF+RAX*8]` | RDX = `F_BASE` |
| MC_SW2 | `MOV RCX,[IST3_SSP_OF+RAX*8]` | RCX = `IST3_TOKEN` |
| MC_SW3 | `CMP QWORD PTR [RDX+IST_SAVE_MC_MODE],JMP_NMI_H2`; `JNE MC_SW4`; `CLRSSBSY [RCX]`; `JMP MC_SW8` | For `#MC` at `NMI_H2` (`SSP = 0`): `IST3` token free and `SSP := 0` (`CLRSSBSY` sets `SSP := 0` without faulting even if restarted after the token is already free, SDM vol. 2A p. 3-150 [R]) |
| MC_SW4 | `WRSSQ [RCX],RCX` | **`IST3` shadow-stack token freed BEFORE `MCIP` is cleared** (idempotent, does not touch `SSP`, SDM vol. 2D `WRSSD/WRSSQ` [R]) |
| MC_SW5 | `MOV RCX,[RDX+IST_SAVE_MC_TSSP]`; `LEA RDX,[RCX-8]`; `OR RCX,1`; `WRSSQ [RDX],RCX` | Restore-SSP token (`TARGET_SSP \| 1`) written at `[TARGET_SSP - 8]` |
| MC_SW6 | `RSTORSSP [RDX]` | `SSP := TARGET_SSP - 8` (SDM vol. 2B `RSTORSSP` [R]) |
| MC_SW7 | `MOV ECX,1`; `INCSSPQ RCX` | `SSP := TARGET_SSP` (`MC_RSHSTK`, `MC_RSHSTK + 24`, `SSP_nmi` or `PL0_SSP`, SDM vol. 2A `INCSSPQ` [R]) |
| MC_SW8 | `MOV ECX,17AH`; `XOR EAX,EAX`; `XOR EDX,EDX`; `WRMSR` | **`MCIP` cleared.** `IST3` is already free and `SSP` is already `TARGET_SSP`. Falls into `MC_R2_0` (Range 2) |

- **Why `CPL3_CONT` uses `target_ssp = MC_RSHSTK + 24` and NOT `SSP = 0`.** In SDM vol. 2A `IRET` (`RETURN-TO-OUTER-PRIVILEGE-LEVEL`, p. 3-494 [R]), when `ShadowStackEnabled(0) == 1` the processor unconditionally executes `tempOldSSP = SSP; shadow_stack_lock_cmpxchg8b(tempOldSSP, ...)` before switching to CPL 3. Setting `SSP := 0` before `MC_S17: IRETQ` to CPL 3 would dereference linear address `0` and raise `#PF` → `#DF` → `T0` on a healthy node. Pointing `SSP` at `[MC_RSHSTK + 24]` (a valid supervisor shadow-stack slot on `RFRAME_OF` holding `MC_RSHSTK + 24`, busy bit clear) makes that `cmpxchg8b` harmless while `IST3` is already free.
- **Why `MC_SW0..MC_SW8` is its own restart range (Range 1b).** If an NMI interrupts between `MC_SW6` (`RSTORSSP`) and `MC_SW7` (`INCSSPQ 1`), `SSP` is `TARGET_SSP - 8`, not `IST3_TOKEN - 24`. Restarting at `MC_N4` would fail the exact `SSP == IST3` check and panic a healthy node. Because Range 1b restarts at `MC_SW0`, reloads `F_BASE` and `IST3_TOKEN` from read-only tables, and re-runs `WRSSQ` + `RSTORSSP` + `INCSSPQ 1` + `WRMSR 0x17A` idempotently (working for any prior `SSP`), an NMI anywhere in `MC_SW0..MC_SW8` is harmless. (When `return_mode == JMP_NMI_*`, hardware NMI blocking is still active, so no NMI can arrive there at all.)
- **Why a second `#MC` (`MC2`) in Range 2 (`MC_R2_0..MC_S17` or `MC_JNMI_*`) loses nothing.** While `MCIP` is set a second machine check is a shutdown by hardware ("The machine-check architecture does not support recursion", §18.11.4.1 [R], OPEN-4 item 3). Once `MC_SW8` clears `MCIP`, `IST3` is already free (freed at `MC_SW3`/`MC_SW4`). A second `#MC` (`MC2`) arriving anywhere in Range 2 is delivered cleanly on `IST3` with hardware-pushed `LIP ∈ Range 2`, sets `is_mc2 = 1`, leaves `IST_SAVE_MC` and `MC_RSHSTK` untouched, scans/logs/clears banks, marks `MC_BIT`, and enters `MC_SW0` to free `IST3`, restore `MC1`'s `target_ssp`, clear `MCIP`, and restart `MC_R2_0`. No software active-flag clear race exists at `MC_S17` because hardware atomically retires `LIP` out of Range 2 when `MC_S17` or `MC_JNMI_*` executes.
- **Re-running Range 1a on a nested NMI (closes V3-3a, V3-3b).** An NMI inside Range 1a restarts at `MC_N4`. The captured words in `IST_SAVE_MC` are identical because `MCIP = 1` prevents any second `#MC` from overwriting `IST3`. If Step 3 already latched `row7_sticky = 1` and Step 4 already cleared the SRAR bank, Step 1 sees `row7_sticky == 1` and preserves Row 7 instead of downgrading to Row 10 (V3-3a). If an NMI interrupts Step 4 between advancing the log index (`WRSSQ`) and clearing the bank (`WRMSR`), the restarted run logs that bank a second time before clearing it: no error record is ever silently lost, and B.5.3 item 4 explicitly requires the kernel handler to tolerate a duplicate record (V3-3b; version 3's "a record is written once" claim is removed).

**Rows `C0..C13`: Row 7 user-context copy into dedicated `MCUSER_BLOCK_OF`** (closes **V3-3c**; written only on Row 7, never touched by `"continue"` `#MC`).

| Row | Instruction | Holds after it |
|---|---|---|
| C0 | `RDPID RAX` | |
| C1 | `MOV RDX,[MCUSER_BLOCK_OF+RAX*8]` | RDX = this core's Row-7 user block (kernel-writable; untrusted by class) |
| C2, C3 | `MOV RCX,[RSP]`; `MOV [RDX+32],RCX` | User RIP |
| C4, C5 | `MOV RCX,[RSP+16]`; `MOV [RDX+40],RCX` | User RFLAGS |
| C6, C7 | `MOV RCX,[RSP+24]`; `MOV [RDX+48],RCX` | User RSP |
| C8, C9 | `MOV RCX,[RSP+40]`; `MOV [RDX],RCX` | User RAX |
| C10, C11 | `MOV RCX,[RSP+48]`; `MOV [RDX+8],RCX` | User RCX |
| C12, C13 | `MOV RCX,[RSP+56]`; `MOV [RDX+16],RCX` | User RDX |

**Rows `M0..M9`: Row 7 handoff — free `IST3`, acquire `IA32_PL0_SSP`, clear `MCIP`, jump to `kernel_mc_user`** (closes V3-2a, V3-3a, V3-5).

| Row | Instruction | Holds after it | NMI | `#MC` | `#DB` |
|---|---|---|---|---|---|
| M0 | `RDPID RAX` | Core number. **Range 1b-a begins** | R to M0 | MCIP = 1 (shutdown) | F |
| M1 | `MOV RDX,[RFRAME_OF+RAX*8]`; `XOR ECX,ECX`; `WRSSQ [RDX+IST_SAVE_MC_ROW7],RCX` | `row7_sticky := 0` (Step 4 already logged and cleared all banks) | R to M0 | MCIP = 1 | F |
| M2 | `MOV RDX,[IST3_SSP_OF+RAX*8]` | RDX = `IST3_TOKEN` | R to M0 | MCIP = 1 | F |
| M3 | `CLRSSBSY [RDX]` | `IST3` token free; `SSP = 0` (`CLRSSBSY` pseudo-code [R]; idempotent on restart) | R to M0 (before it executes); else D to M4 | MCIP = 1 | F |
| M4 | `SETSSBSY` | `SSP = IA32_PL0_SSP`, token busy (it was free since Row 7 came from CPL 3). Harmless **D** row, no register operand | **D** | MCIP = 1 | F |
| M5 | `MOV ECX,17AH` | **Range 1b-b begins** | R to M5 | MCIP = 1 | F |
| M6 | `XOR EAX,EAX` | | R to M5 | MCIP = 1 | F |
| M7 | `XOR EDX,EDX` | | R to M5 | MCIP = 1 | F |
| M8 | `WRMSR` | **`MCIP` cleared**, with `IST3` already free and `SSP == IA32_PL0_SSP` | R to M5 (before it executes); else D to M9 | MCIP = 1 (before); after: delivered on free `IST3` | F |
| M9 | `JMP kernel_mc_user` | In kernel text on `IA32_PL0_SSP`, every IST token free, `MCIP = 0`. Harmless **D** row, no register operand. Kernel loads its stack pointer and reads `MCUSER_BLOCK_OF[core]` | **D** | Delivered on free `IST3`; `"continue"` returns **D** to `M9` without touching `MCUSER_BLOCK_OF` | F |

- **A `#DB` anywhere in `M0..M9` is fatal** (V12, item 4): a single step onto `M3` with the kernel's `RDX` would free an arbitrary token.
- **`M0..M3` (Range 1b-a) and `M5..M8` (Range 1b-b)** are separate restart ranges around harmless row `M4` (`SETSSBSY`) so `SETSSBSY` runs once and `WRMSR 0x17A` always executes with operands loaded in the same run.

**The other bullets of the rule.**
- **Row 3 is a choice.** The alternative charges the node of the core whose private bank reports PCC. Its cost is trusting a processor that reports its own state corrupt to have respected CR3 and the gate.
- **No verdict of F or "stop" rests on a shared bank alone** except rows 2 to 4, which every core that sees the bank reaches together. Rows 5 to 8 need this core to be the affected one. A healthy node is never declared fatal for an error another node's core consumed.
- **MCIP is cleared in gate text on every path that does not stop the machine** (`MC_SW8`, `M8`, and `T16` on the fatal path), always **after** `IST3`'s token is freed. The kernel never runs with `MCIP` set.
- **The stub logs and clears; the kernel does not (F6).** Version 2 left the clearing to a kernel call, so a kernel that never called it left VAL set, and a later SRAR found OVER, which row 4 turns into a stop of the machine. `mc_collect` now only reads the log, and clears nothing.
- **Start-up** sets `LMCE_EN` where firmware allows, sets CR4.MCE on every core before any node runs, and claims bank ownership.
- **On the reference desktop** `MCG_SER_P` is probably 0 (UNVERIFIED on the machine, trial T5), so row 2 makes every uncorrected machine check a stop of the machine with a stop record.
- **OPEN-4, what remains.**
  1. *Shared banks under a broadcast machine check.* The owner's stub clears a shared bank while another core's stub may still be reading it; that core then sees VAL = 0 and takes row 10. It loses the address of an error; I found no way from there to wrong data being used (document 5 found none either), but the manual asks for the serialisation ("serialize access to the machine check registers when analyzing, logging, and clearing", §18.11.4.1 [R]) and this rule does not give it.
  2. *The case no core finds any error* (the manual's "unexpected condition") is not detected, since no core knows what the others found.
  3. *A second machine check before `MC_SW8`/`M8`/`T16` clears `MCIP`* is a shutdown of that core.
  Options in part D.
- **A core with CR4.MCE clear.** "If the machine-check mechanism is not enabled (the MCE flag in control register CR4 is clear), a machine-check exception causes the processor to enter the shutdown state" (SDM vol. 3A §7.15, interrupt 18 [R]). **INIT clears CR4**: the row "CR2, CR3, CR4" of Table 12-1, "Processor States Following Power-up, Reset, or INIT", reads 00000000H in its three columns (§12.1.1 [R]; version 2 cited Table 11-1 and marked this UNVERIFIED, both wrong). The contract already has the park stub set machine checks enabled (the fence, step 4), and the park stub runs only after a SIPI. Between the INIT and the SIPI the core is in wait-for-SIPI with CR4.MCE clear; what it does at a broadcast machine check the SDM does not say [J]. One unknown, trial T9, residue 11.

#### B.5.3 What the kernel's handler outside the gate must do

None is specified today. From the rule above:

1. It is entered only by row `M9` (a thread to fault, on `IA32_PL0_SSP` with every IST token free and user words in `MCUSER_BLOCK_OF[core]`) or through the pending word (rows 9 and 10).
2. It reads the machine-check log, decides by the address word whether the address is its node's, writes the hardware error record (code 7), and for memory it owns stops using the page.
3. It never writes an MSR, and never returns to the faulted thread of row 7.
4. It tolerates duplicate log records: both a record another core of its node also sees (a shared bank logged by its owner) and a record written twice if a nested NMI restarted Range 1a of `#MC` Step 4 between advancing the log index and clearing the bank (V3-3b).

#### B.5.4 ARM64 and RISC-V

| Architecture | In a gate call | Stops the machine |
|---|---|---|
| ARM64 | SError is masked and pended (taken by the kernel's vector after Z7); a synchronous external abort in the window is fatal to the node | Errors firmware at EL3 handles: firmware's |
| RISC-V | An access fault in the window is fatal to the node. The privileged specification defines no machine-check architecture; a hardware-error NMI is machine mode's (Smrnmi [4]) | Firmware's |

### B.6 Costs

**Documented by others, as cited in kernel.md and not re-opened by me:** a CR3 write "about 200 cycles" (Ren et al., SOSP 2019); `WRSSQ` 9.3 cycles on a Tiger Lake core (CETIS, CCS 2022); SKEE's round trip 284 cycles; Hilps 210 to 424 cycles. **Everything else below is my estimate. Nothing is measured on the project's machines.**

| | x86-64 mechanism 2 | ARM64 mechanism 1 | RISC-V mechanism 1 |
|---|---|---|---|
| Windowed call, fixed part | Two CR3 writes (about 400 by the documented figure) plus `RDPID` and about 20 instructions: 420 to 550 cycles (estimate) | Two `TTBR1` writes with `isb`: near SKEE's 284 (estimate) | Two `satp` writes; no figure found. With ASIDLEN = 0, two full flushes more |
| Per entry written | One store, or one `LOCK CMPXCHG` for a living-part word (about 20 cycles, estimate) | The same | The same |
| Switch of address space | Two CR3 writes instead of one: +1 CR3 write, about +200 to +250 (estimate) | Two `TTBR1` writes and the `TTBR0` write | Two `satp` writes instead of one |
| **Return to user mode, variant (a)** | After an event: 85 to 105 cycles more (B.1.9). After a system call: 35 to 55 more, less what `SYSRETQ` saves over `IRETQ` | Nothing (the question does not arise: no frame in memory) | Nothing |
| Per interrupt taken | The stub: a CR3 read, `RDSSPQ`, range compares: 10 to 30 cycles (estimate). End of interrupt and timer deadline: +5 to 10 over the bare `WRMSR` | Nothing at the vectors (the twin page); the acknowledgement is a gate call already (D-151) | Nothing at `stvec` |
| An event inside closed gate text | One stub with rows S0 to S17: about 100 cycles (estimate), and the interrupted range runs again | An SDEI event: firmware's cost | — |
| Port access | A windowed call: about 450 to 600 (estimate) | — | — |
| A machine check of class "continue" | Per owned bank with VAL: 5 `WRSSQ`, 4 `RDMSR`, 1 `WRMSR`; plus `IST_SAVE_MC` capture and `MC_SW` (`WRSSQ`+`RSTORSSP`+`INCSSPQ`) | — | — |
| Memory per core | Four interrupt stacks on two sides (32 KB), four shadow stacks and the kernel's (20 KB), the gate stack (16 KB), a root and three private tables (16 KB), the `RFRAME_OF` page (4 KB, shared by `F`, `IST_SAVE_MC`, `MC_RSHSTK` and `PARK_RSHSTK`), a log page (4 KB): **about 92 KB** (estimate), plus 200 bytes for `RBLOCK_OF` and the three CPL-3 IST user blocks | Gate stack and tables: about 32 KB | The same, plus the trap page pair (8 KB) |
| Kernel mappings not global | More kernel TLB misses after a switch of address space. Not estimated; trial T3 | The same | The same |

**ARM64, the other mechanisms.** 1′: mechanism 1's two register writes become two `TCR` writes, plus one local `TLBI` per close and four to ten table walks per call (B.3.3). 2: two `POR` writes with `isb` per call, no TLB cost, and three system-register accesses at every exception the kernel takes; no figure exists on hardware.

### B.7 A gate one exception level above the kernel: an assessment, not a design

Document 5 suggests studying a gate that runs one level above the kernel and is entered by a trap: EL2 with the kernel at EL1 on ARM64 (`HVC`); HS-mode with the kernel in VS-mode, or machine mode, on RISC-V (`ecall`).

**What it would give.**
- The entry becomes atomic by hardware. Every sequence in this draft has an opening instruction that takes its operand from a register, in text the kernel can jump into; that is why a peer-level gate needs control-flow integrity, and why ARM64 and RISC-V are "faulty kernel only" today. A trap has no such instruction. This would move ARM64 to the adversarial promise on every core with EL2, without FEAT_GCS.
- No second stage of translation is needed for it: the gate's pages are simply absent from the kernel's own tables, as today, and the kernel's writes of its translation registers trap ("Traps writes to the virtual memory control registers to EL2", `HCR_EL2.TVM` [R]; on RISC-V "The hstatus fields VTSR, VTW, and VTVM are defined analogously to the mstatus fields TSR, TW, and TVM, but affect execution only in VS-mode" [R]). So the principle "nothing on an ordinary access or a TLB miss" would stand.
- B.3 would shrink: no reserved ASID, no twin vector page, no per-core gate tables, no rows A0 to Z8.

**What it would cost per gate call.** One exception entry to the higher level and one return, in place of two writes of a translation register with their barriers. I have no figure from a source for either on the same core; from memory they are of the same order (some hundreds of cycles). It must be measured before it is argued.

**What it conflicts with.**
- **The contract, the fence on ARM64 (line 1675):** "The kernel runs at the highest non-secure exception level the machine offers ... because SDEI requires its client to execute at that level." The gate would become the SDEI client, and the fence's handler, the park routine and the registration of event 0 would move into it. That is a rewrite of that paragraph and of the firmware allow-list's wording, not of the fence's logic.
- **The hardening monitor of D-117** would sit at the same level. The two would have to be one design.
- **Cores without EL2**, and RISC-V harts without the hypervisor extension, keep mechanism 1: two mechanisms on one architecture. On RISC-V the machine-mode variant puts the gate in firmware, which the project does not own.
- **x86-64 has no counterpart worth the cost**: VMX root operation is the hardening monitor itself, and x86-64 already reaches the adversarial promise at the kernel's own level.

**Whether it deserves a separate study.** Yes, for ARM64, before any software discipline for returns is considered: it is the only route found to the adversarial promise on shipping ARM64 cores, and it may be simpler than B.3. It is not designed here, and nothing in this draft depends on it. The alternative document 4 proposes (a mask before every return and indirect branch, enforced by the scan, with an `ERET` trampoline that needs the X2 test of B.3.2) works on every core and is a toolchain project paid at every function return.

---

## C. Break → where version 4 closes it

Every break and every Job 1 item of document 3, re-checked against the rows of version 4. The findings of documents 6 and 7 (V3-1 to V3-8, ARGON-1 to ARGON-3) are mapped in "Changes from version 3", and the six critical version 4 nesting-safe scenarios are walked explicitly below the table.

| # | Item of document 3 | Closed by, in version 4 | Status |
|---|---|---|---|
| N1 | IBT state lost across an IDT event | **Re-walked.** A branch to an instruction of gate text with an event taken first lands, by the table of B.1.7: in an entry's prologue, a short entry or a return entry (`U0..U24`, `Y0..Y13a`, `Y14..Y21`) → R, every operand reloaded; in a stub from its redo label, in the `#MC` stub's ranges (`Range 1a`, `MC_SW0..MC_SW8`, `MC_R2_0..MC_S17`, `M0..M3`, `M5..M8`), in `T0..T26` → R to that range's first row; on a harmless row (`E0..E3`, `L0..L2`, `I14..I16`, `NMI_H2..H3`, `DB_H2..H3`, `M4`, `M9`, `N0..N3`, the park loop) → D, and V12 item 5 gives the reason no operand there is the kernel's; in the body, closed → F. A `#DB` is F outside the rows V12 item 4 lists (`N0` of an IDT stub requires `DR6.{BS,BD,BT} == 0` and not open, closing V3-4 without reopening F2). Without an event: `#CP`, F. With a `3EH` prefix: `NO_TRACK_EN` = 0 (B.1.5). The kernel's own returns reach only the first two instructions of an entry or addresses outside gate text | Closed for x86-64 mechanism 2 under precondition 1. For the model to confirm (property 3) |
| N2 | Stub stacks open to DMA | B.1.2: kept memory or class *gate* | Closed |
| N3 | `WRSS` to MMIO and to the living part | B.2 (mechanism 1 is not specified); B.1.5 | Closed by not using mechanism 1; decision 1 |
| 1A | A completed call re-run; IF never restored | V8; rows E0 to E3; V10 | Closed |
| 1B | Mechanism 1 pending word | Mechanism 1 is not specified | Not applicable |
| J2-b | Livelock on restart ranges | Not bounded, by design: the faulty node loses its own time. None is entered by a healthy kernel's event at a rate the node does not choose, given precondition 3 | Not closed for the faulty node (accepted) |
| J2-c | `WRSSQ` of SSP + 8 then `IRETQ`; token alignment | B.1.2 (token placement); row N19; trial T2 | Closed on paper |
| 2A | `#DF` handed to the kernel; a triple fault | Vector 8 is `JMP T0`; `T0..T26` reads nothing the processor pushed, makes no `CALL`, unconditionally clears `IST1..IST4` tokens via `WRSSQ` (`T6..T9`), switches `SSP := PARK_RSHSTK` via `RSTORSSP`+`INCSSPQ 1` (`T14..T15`, handling `SSP = 0`, ARGON-2), and clears `MCIP` (`T16`, ARGON-3) before entering `park` with all four IST tokens free (ARGON-1) | **Closed (OPEN-2 closed)**; trial T19, property 9 |
| R4 | "From CPL 0" by SSP | B.1.7, exact token equality (`SSP == ISTk_TOKEN` for CPL 3, `ISTk_TOKEN - 24` for CPL 0, else F); CPL-3 IST handoffs onto `IA32_PL0_SSP` (V3-5); `INCSSPD`/`INCSSPQ` out of kernel text | Closed |
| J2-d | `RDPID`, `ROOTS`, per-core IST addresses | B.1.2 | Closed |
| 4A | The gate's PCID in G7's table | B.1.3 | Closed |
| 4B | The global-bit rule | V9 and B.1.2 | Closed |
| 6A | NMI replay by `INT 2` | B.1.6: a jump, a function, no token busy | Closed |
| 7A | `load_root` as a short entry | B.1.11: windowed; closes to the new root (also on ARM64 and RISC-V: rows Z2 and S0) | Closed |
| 7B | `RET` inside a restart range | V8; B.1.11 | Closed |
| 7C | Port access races `memory_give` | B.1.11: windowed under the gate lock | Closed. Under variant (b) of B.1.9 the ports are open by another road |
| 8 | Vectors 3 and 4 with DPL 0 | V2 | Closed |
| 8A | `IA32_LSTAR` and `SETSSBSY` | **Re-walked.** `L0..L2` are harmless rows. Because CPL-3 IST handlers switch onto `IA32_PL0_SSP` before entering kernel text (V3-5), any kernel jump to `L0` finds `IA32_PL0_SSP` busy → `#CP(SETSSBSY)` → `#PF` at `0xFFFF_FFFF_FFFF_FFFC` → serial `#PF` → `#DF` on `IST4` → `T0` (ARGON-2). Return to user mode is `U0..U24` / `Y0..Y21` under variant (a) | Closed under variant (a) or (c). Under (b) the row holds and the IOPL of the return is outside the promise |
| 9A | A stub that spills a trusted value on a stack another core writes | **Re-walked.** A stub stores only the context's three registers (`N1..N3`) and reloads its own stack pointer at `N5`. Every trusted value is computed after the redo label; persistent `#MC` scratch (`IST_SAVE_MC`, `MC_RSHSTK`, `PARK_RSHSTK`) and return frame `F` (at `F_BASE + 0x40`, V3-7c) live on shadow-stack-typed `RFRAME_OF` written by `WRSSQ` only. `IST3` is freed before `MCIP` is cleared (`MC_SW0..MC_SW8`, `M0..M8`, V3-2a) | Closed under variant (a) (OPEN-6 closed [R]). Under (b) the frame's words stay writable, which is what (b) names |
| 10A | `MCG_SER_P`, EN, OVER | B.5.2, rows 2, 4, 9 (evaluated before open/closed dispatch, V3-2b) | Closed |
| 10B | Shared banks park healthy nodes; no rendezvous | B.5.2: F needs this core to be the affected one; row 1's reason corrected (F4); the stub logs and clears (F6); `row7_sticky` prevents downgrade on NMI (V3-3a); duplicate log record tolerated (V3-3b); `MCUSER_BLOCK_OF` isolated from `"continue"` (V3-3c) | Partly closed: OPEN-4, three items |
| 10C | A kernel that leaves MCIP set | B.5.2 (`MC_SW8`, `M8`) and B.1.10 (`T16`: `mc_check_stop_or_clear_mcip`) | Closed |
| 11A | `TTBR1` has no ASID of its own | B.3.1 | Closed |
| 11B | `PSTATE.SP` = 0; a push in the vector stub | Row A5; the twin vector page; A-V10 | Closed |
| 11C | SP moved outside the window | Rows A13 to A15 and Z3 | Closed |
| 11D | `MSR ALLINT` undefined before FEAT_NMI | Rows A2, A4 and Z6, patched by `SCTLR_ELx.NMI`; caller's value saved at A18 and restored at Z6 | Closed |
| VHE | `TPIDR_EL1`; `SP_EL2`; the `_EL12` names | B.3.2; D.4 | Closed, with one contract change |
| BTI | A wild jump onto the `MSR` without BTI | **Not closed, with BTI or without**: a `RET` or an `ERET` reaches `A11` (and `Q7` or `Y4′` under mechanism 2, V3-8b). FEAT_GCS full enablement stated in B.3 (V3-8a) | **Not closed**: the table of part A; decision 3 |
| 12A | `satp` without a flush; no ASID reserved; ASIDLEN 0; the G bit | B.4 | Closed |
| 12-b | sp moved before the `satp` write | B.4 | Closed |
| J3-1 | Mechanism 1 not viable even on one core | B.2 | Presented: decision 1 |
| J3-2 | The cost of `load_root` and of a port access | B.6 | Stated |
| J3-3 | Five residue items | Part A | Listed |

**Version 4 adversarial walk-throughs (nesting-safe IST discipline & snags caught while verifying against the manuals).**

1. **`#MC` inside the NMI stub (`NMI_N0..N3`, `NMI_N4..S17`, `NMI_H0..H3`; V3-1).**
   - `#MC` arrives on `IST3` while NMI blocking is active (`IST1` busy). Range 1a captures into `IST_SAVE_MC`, evaluates B.5.2 (stop/F → stop/`T0`), logs/clears owned banks, and sets `MC_BIT`.
   - *Snag caught (1):* If `#MC` interrupted `NMI_N0..N3`, `N1..N3` have not yet written the interrupted context's `RAX, RCX, RDX` into `[IST1_TOP+40..56]`; jumping straight to `NMI_N4` would lose them. Because `N0..N3` never modify `RAX, RCX, RDX`, Step 3 copies `IST_SAVE_MC.{rax,rcx,rdx}` into `[IST1_TOP+40..56]` before setting `return_mode = JMP_NMI_N4`, `target_ssp = old_ssp` (`IST1_TOKEN` or `IST1_TOKEN - 24`).
   - *Snag caught (2):* If `#MC` interrupted `NMI_H2` (`SETSSBSY`), `old_ssp == 0`, so `RSTORSSP` cannot restore `0`; `MC_SW3` executes `CLRSSBSY [IST3_TOKEN]` (which frees `IST3` and sets `SSP := 0` without faulting, SDM vol. 2A p. 3-150 [R]), clears `MCIP` at `MC_SW8`, and executes `JMP NMI_H2`.
   - On all other NMI-stub rows (`NMI_N0..S17`, `NMI_H0..H1`, `NMI_H3`), `MC_SW4..MC_SW8` frees `IST3` via `WRSSQ`, restores `SSP` (`SSP_nmi` or `PL0_SSP`) via `WRSSQ`+`RSTORSSP`+`INCSSPQ 1`, clears `MCIP`, and executes `JMP NMI_N4` / `JMP NMI_H3`. **Zero `IRETQ` executes**, NMI blocking is never lifted, `IST1` remains valid, and Row G1 is gone.
2. **Second `#MC` (`MC2`) immediately after `MCIP` clear (Range 2 `MC_R2_0..MC_S17` and `MC_JNMI_*`; V3-2a/c).**
   - `MC_SW3`/`MC_SW4` frees `IST3` **before** `MC_SW8` clears `MCIP`. When `MC2` arrives anywhere in Range 2, `IST3` is free and `MC2` pushes `LIP ∈ Range 2` onto `IST3`'s shadow stack.
   - *Snag caught (3):* Clearing a software `active` flag before `MC_S17` would leave a race window at `MC_S16..MC_S17`. Checking hardware-pushed `LIP = [IST3_SSP + 8] ∈ Range 2` before touching `IST_SAVE_MC` or `MC_RSHSTK` has zero race window: hardware atomically moves `LIP` out of Range 2 when `MC_S17` or `MC_JNMI_*` retires. `MC2` sets `is_mc2 = 1`, skips capture, scans/logs/clears banks, sets `MC_BIT`, jumps to `MC_SW0`, frees `IST3`, restores `MC1`'s `target_ssp`, clears `MCIP`, and restarts `MC_R2_0`.
   - *Snag caught (4):* For a CPL-3 `"continue"` `#MC`, setting `SSP := 0` before `MC_S17: IRETQ` would fault `#PF` → `#DF` → `T0`, because SDM vol. 2A `IRET` (`RETURN-TO-OUTER-PRIVILEGE-LEVEL`, p. 3-494 [R]) unconditionally executes `shadow_stack_lock_cmpxchg8b(SSP, ...)` whenever `ShadowStackEnabled(0) == 1`. Pointing `target_ssp` at `[MC_RSHSTK + 24]` on `RFRAME_OF` satisfies `cmpxchg8b` harmlessly while leaving `IST3` free.
3. **`NMI` inside `#MC` Step 4 and inside `MC_SW0..MC_SW8` (V3-3a/b).**
   - An NMI in Range 1a after Step 3 latched `row7_sticky = 1` and Step 4 cleared the SRAR bank restarts at `MC_N4`, where Step 1 sees `row7_sticky == 1` and preserves Row 7 instead of downgrading to Row 10 (V3-3a). An NMI between Step 4's log-index `WRSSQ` and bank-clear `WRMSR` may duplicate one record, never losing an error, which B.5.3 item 4 explicitly tolerates (V3-3b).
   - *Snag caught (5):* If an NMI arrived between `MC_SW6` (`RSTORSSP`) and `MC_SW7` (`INCSSPQ 1`), `SSP` would be `TARGET_SSP - 8` (not `IST3_TOKEN - 24`), so restarting at `MC_N4` would fail the exact `SSP == IST3` check and panic a healthy node. Isolating `MC_SW0..MC_SW8` as its own idempotent restart range (`Range 1b`), and splitting `M0..M9` into `Range 1b-a` (`M0..M3`), harmless row `M4` (`SETSSBSY`), `Range 1b-b` (`M5..M8`), and harmless row `M9`, eliminates this race completely.
4. **`#DB` at `N0` via `MOV SS`/`POP SS` + data watchpoint + `INT3`/`UD2`/`#PF`/`#DE`/`#GP` (V3-4).**
   - By SDM vol. 3A §7.8.3 [R], `MOV SS`/`POP SS` inhibits a data breakpoint until the next instruction boundary (including exception entry at `N0`) while suppressing `TF`. At `N0` (`ENDBR64`) of any IDT stub with `CR3` not open and `DR6.{BS,BD,BT} == 0`, the `#DB` stub copies/resets `DR6` (`0x0000_0000_FFFF_0FF0`), marks `DB_BIT`, and returns **D** with `RFLAGS = 2` (or at `NMI_N0`, copies `RAX/RCX/RDX` to `[IST1_TOP+40..56]`, frees `IST2`, restores `SSP := SSP_nmi`, and executes `JMP NMI_N4` without `IRETQ`). Every instruction `N1..S17` and any `DR6.{BS,BD,BT} != 0` remain **F**, keeping F2 completely closed.
5. **Misbehaving kernel `JMP U0`, `JMP Y0`, or `JMP L0` (V3-5).**
   - Every CPL-3 IST entry (`NMI_H0..H3`, `DB_H0..H3`, `M0..M9`) frees `ISTk` and acquires `IA32_PL0_SSP` before entering kernel text, so no IST token is ever busy in kernel code entered from CPL 3 and `IA32_PL0_SSP` is always busy whenever kernel code runs.
   - `JMP U0` on an IST shadow stack or with unpopped frames fails `U2a` (`SSP != PL0_SSP_OF[core]`) → `T0` (**F**). `JMP L0` finds `IA32_PL0_SSP` busy at `L1: SETSSBSY` → `#CP` → `#PF` at `0xFFFF_FFFF_FFFF_FFFC` → serial `#PF` → `#DF` on `IST4` → `T0` (**F**, ARGON-2).
   - *Snag caught (6):* Putting `Y13a: JC T0` inside a single restart range `Y0..Y21` would panic a healthy node if an NMI arrived after `Y13: CLRSSBSY` (restarting at `Y0` would re-run `CLRSSBSY` on the already-free token, setting `CF = 1` → `T0`). Splitting `ret_user_fast` into Range 1 (`Y0..Y13a`, checking `Y3a: SSP == PL0_SSP_OF` and `Y13a: JC T0`) and Range 2 (`Y14..Y21`, reloading `RBLOCK_OF` and `LA57`-aware canonical check `Y18..Y19` before `SYSRETQ`) closes V3-5 without false panics.
6. **`NMI` or `#MC` at `park` after `T0..T26` (ARGON-1, ARGON-2, ARGON-3, OPEN-2).**
   - Whatever `SSP` or combination of busy IST tokens existed on entry to `T0` (including `SSP = 0` from `Y13a`/`Y19` or nested IST frames), `T6..T9` unconditionally clear `IST1..IST4` tokens via four `WRSSQ` instructions, `T13..T15` switch `SSP := PARK_RSHSTK` via `WRSSQ`+`RSTORSSP`+`INCSSPQ 1` (never dereferencing old `SSP`), `T16` runs self-contained `mc_check_stop_or_clear_mcip` (clearing `MCIP` with `IST3` already free), and `T26: IRETQ` enters `park` under the gate's root with all four `IST1..IST4` tokens free. Any later NMI or `"continue"` `#MC` at `park` is **D** cleanly on gate-side `IST1`/`IST3`, and no delivery can ever triple-fault.

**Not closed in version 4.**
1. **ARM64 and RISC-V against an adversarial kernel** (N4, F7, the BTI row): no shipping core allows it.
2. **OPEN-4**: shared banks under a broadcast machine check; the case no core finds an error; a second machine check before `MC_SW8`/`M8`/`T16` clears `MCIP`.
3. **OPEN-7**: two primary readings still owed (VT-d compatibility-format control name and PCI bridge bus-renumbering registers).
4. **A machine without interrupt remapping** (M3): the faulty-kernel promise only.
5. **Under variant (b)**, everything B.1.9 lists; and **ARM64 mechanism 2**, if it is ever used, keeps the kernel's text mapped in the window.

(`OPEN-2`, `OPEN-6` and `OPEN-8` from version 3 are now **closed**.)

---

## D. Open rows, trials and decisions

### D.1 Open rows

Only **two** open rows remain in version 4:

1. **OPEN-4, broadcast machine checks.** (a) As written: no rendezvous; accept the three items of B.5.2. (b) A rendezvous word in the living part, which requires the `#MC` stub to open the window from any context and to reach its frame through the gate's view of the kernel-side stack. (c) Require LMCE and make every broadcast machine check a stop of the machine. On the reference desktop (a) and (c) probably coincide (row 2).
2. **OPEN-7, two readings still owed for B.1.9 and B.1.12**: the VT-d control that blocks compatibility-format messages, and the PCI bridge registers behind the sentence on variant (b). Both are from memory here (neither specification is among the four manuals on disk).

**Closed in version 4:**
- **OPEN-2 (closed):** `T6..T15` (B.1.10) unconditionally clears all four `IST1..IST4` tokens via `WRSSQ` and transitions `SSP` onto `PARK_RSHSTK` via `RSTORSSP`+`INCSSPQ 1` before clearing `MCIP` and entering `park`. Trial T19 and property 9 verify it.
- **OPEN-6 (closed [R]):** SDM vol. 3A §5.6.1 (pp. 5-33–5-34 [R]) explicitly permits implicit and explicit supervisor-mode data reads (`POP`, `IRETQ`) from shadow-stack-typed pages (B.1.2). Trial T13 remains as hardware confirmation only.
- **OPEN-8 (closed [R]):** Arm ARM Table D8-74 and D24.2.150 (`POR_EL1` [R]) confirm `0b0101` (`PrivRead | PrivWrite`, never `PrivExecute` per `RQXXPC` [R]), and D24.1.2.2 [R] confirms `isb` at `Q8` and `Y5′` is mandatory (B.3.3).

Version 2's OPEN-1 (now superseded by the evacuate-and-free IST discipline of B.1.7 and B.5.2), OPEN-3 (B.3.3) and OPEN-5 (B.5.2 `C0..C13` and `M0..M9`) remain closed.

### D.2 Trials on the reference machine (measurements and experiments)

1. **T1.** A CR3 write with PCID and bit 63, and a CR3 read, in cycles, on both kinds of core.
2. **T2.** A stub rewrites the slot at SSP + 8 by `WRSSQ`, then returns: no `#CP`, the token free afterwards. With a 64-bit return address, on IST1, IST2 and IST3 (document 4's fifth suspicion).
3. **T3.** Kernel text and data without the global bit: TLB misses in the kernel after a switch of address space.
4. **T4.** `RDPID` on both kinds of core; its cost.
5. **T5.** `IA32_MCG_CAP`: `MCG_SER_P`, `MCG_LMCE_P`, the bank count; `IA32_FEATURE_CONTROL` bits 0 and 20; which banks two cores share.
6. **T6.** One core driven into shutdown by a triple fault while the others run: what the platform does.
7. **T7.** An NMI injected at every row of B.1.4, B.1.6 to B.1.11 (single-stepped under a hypervisor first, then on the machine).
8. **T8.** N1: TF set, an indirect jump to P7, to N19, to T2, to `MC_SW6` (`RSTORSSP`), and to `MC_SW8`/`M8` (`WRMSR 0x17A`); expected: restart or F, never the instruction with the kernel's operand.
9. **T9.** A core in wait-for-SIPI at an injected machine check.
10. **T10.** `ret_user` against `ret_user_fast` against a bare `IRETQ`, in cycles (the estimates of B.1.9).
11. **T11.** An NMI arriving while NMIs are blocked: is one held and delivered at the `IRETQ`?
12. **T12.** The ARM64 and RISC-V tables under QEMU, with an SDEI event and an interrupt injected at every row; TF-A's SDEI dispatcher with the kernel at EL2 (document 4's fourth suspicion).
13. **T13.** Hardware confirmation of OPEN-6 (already confirmed in SDM vol. 3A §5.6.1 [R]): a page typed as a shadow stack, written by `WRSSQ`, then `MOV RSP` to it, `POP` and `IRETQ` to CPL 3 and to CPL 0.
14. **T14.** `CLRSSBSY`, `SETSSBSY`, `RSTORSSP` and `INCSSPQ 1` in cycles; rows `Y13` and `M0..M4` run twice.
15. **T15.** Evacuate-and-free `#MC` inside the NMI stub (replaces Row G1): inject `#MC` at `NMI_N0..N3`, `NMI_N4..S17`, and `NMI_H2` while NMI blocking is held; confirm `WRSSQ`+`RSTORSSP`+`INCSSPQ 1` (or `CLRSSBSY` at `NMI_H2`) + `WRMSR 0x17A` + `JMP NMI_N4`/`NMI_H2` leaves `IST3` free, `IST1` active, and NMI blocking uninterrupted until `NMI`'s own `S17: IRETQ`.
16. **T16.** Interrupt remapping on the reference machine: a message in the compatibility format, and one with the NMI delivery mode, sent by a test device: both dropped.
17. **T17.** Two machine checks injected a few instructions apart, before and after `MC_SW8` (`WRMSR 0x17A`), including `MC2` in Range 2 (`MC_R2_0..MC_S17`) for CPL-0 and CPL-3 `"continue"` (confirming `[MC_RSHSTK + 24]` satisfies `IRET RETURN-TO-OUTER-PRIVILEGE-LEVEL` without `#PF`).
18. **T18 (new, V3-4).** User thread executes `MOV SS` with an active data watchpoint followed by `INT3`, `UD2` and `#PF`, delivering `#DB` (`DR6.{BS,BD,BT} == 0`) at `N0` of the stub (and at `NMI_N0` with an NMI arriving on the same boundary): confirm healthy-node survival (**D**), while `DR6.BS = 1` or `#DB` at `N1..S17` triggers **F**.
19. **T19 (new, OPEN-2 / ARGON-1 / ARGON-2).** Enter `T0..T26` with (a) multiple pre-busied `IST1..IST4` tokens and deep IST shadow stacks, and (b) `SSP = 0` (from `Y13a`/`Y19`), then inject NMI and `"continue"` `#MC` at `park`: confirm all four IST tokens are free at `park`, no `#PF`/`#DF`/triple fault occurs, and `INIT` exits `park`.

### D.3 Decisions for the owners

1. **The order of x86-64 mechanisms in D-120** (unchanged from version 2). (a) Mechanism 2 becomes the mechanism; (b) mechanism 1 is still prototyped for page-table entries on a node of one core, with mechanism 2 beside it; (c) the order stays and the compare-and-swap rule changes. My recommendation is (a). One fact added by version 3 and retained in version 4: variant (a) of B.1.9 keeps two small pages typed as shadow stacks (`RFRAME_OF` and the machine-check log).
2. **How F1 is closed** (B.1.9). (a) The gate composes every frame: 85 to 105 cycles at each return to user mode after an event (estimate), one 4 KB `RFRAME_OF` page per core (also hosting `IST_SAVE_MC`, `MC_RSHSTK` and `PARK_RSHSTK`), with `POP`/`IRETQ` reads now confirmed by SDM vol. 3A §5.6.1 [R] (OPEN-6 closed). (b) Port I/O through IOPL is named outside the promise, which by B.1.9 probably withdraws the adversarial promise on x86-64. (c) Where the image declares the hardening monitor, the monitor's I/O exiting closes it at no per-event cost. My recommendation is (a), with (c) in its place on a machine that has the monitor. This is the only closure in this draft that is paid at every interrupt.
3. **What is promised on ARM64 and RISC-V.** The table of part A says what holds: a faulty kernel only, with or without BTI. To decide: whether the contract says so in those words (I recommend it), and whether the study of B.7 is commissioned (I recommend it for ARM64, before any software discipline). Version 2's option "exception returns behind a check" is withdrawn.
4. **Whether the adversarial promise on x86-64 requires interrupt remapping** (B.1.12), with a machine without it flagged. I recommend it: the contract already calls remapping the normal case.
5. **The machine-check policy** (B.5.2): every uncorrected error stops the machine without `MCG_SER_P`; PCC stops the machine; an action-required error in kernel context is fatal to the node; and, for OPEN-4, whether LMCE is required.
6. **Which residue items the contract names** (part A).

**Settled in version 4 by the assistant, for the owners to review:** elimination of Row G1 in favour of the uniform evacuate-and-free IST discipline (no `IRETQ` when returning into an unfinished NMI stub, `WRSSQ`+`RSTORSSP`+`INCSSPQ 1` shadow-stack switching); `MC_SW0..MC_SW8` and `M0..M9` freeing `IST3` before `WRMSR 0x17A` clears `MCIP`; `row7_sticky` and `MCUSER_BLOCK_OF` isolation; CPL-3 IST handoffs (`NMI_H0..H3`, `DB_H0..H3`, `M0..M9`) onto `IA32_PL0_SSP` plus `U2a` and two-range `Y0..Y21`; `#DB` at `N0` with `DR6.{BS,BD,BT} == 0` as **D**; `T0..T26` unconditionally clearing `IST1..IST4` and switching onto `PARK_RSHSTK` (closing OPEN-2); `OPEN-6` and `OPEN-8` closed from the primary manuals.

### D.4 Changes to the contract this draft implies, if it is taken

Nothing here is made by this draft. The list is complete as far as I can make it.

| # | Where | Change |
|---|---|---|
| 1 | G7 | One tag reserved for the gate on each architecture (x86-64: 4,095 usable PCIDs) |
| 2 | G2; start-up memory, rule 1 | The class *gate* names the gate stack, the gate-side interrupt stacks, the `RFRAME_OF` return-frame/IST-scratch pages (`F = F_BASE + 0x40`, `IST_SAVE_MC`, `MC_RSHSTK`, `PARK_RSHSTK`) and the machine-check log; the kernel-side interrupt stacks are kept memory; **new kept pages**: the pending and deferred-DR6 words, `RBLOCK_OF` and the three CPL-3 IST user blocks (`NMIUSER_BLOCK_OF`, `DBUSER_BLOCK_OF`, `MCUSER_BLOCK_OF`, kernel-writable), and the read-only gate tables (including `IST1_SSP_OF..IST4_SSP_OF`). The last page of the address space is never mapped |
| 3 | kernel.md, the forbidden list (G11), x86-64 | Add `SYSCALL`, `SYSRET`, `SYSENTER`, `SYSEXIT`, `INT n`, `INT1`, `INT3`, `INTO`, `RSTORSSP`, `SAVEPREVSSP`, `INCSSPD`, `INCSSPQ`; under variant (a) also `IRET` of every size and the far `RET` (CA, CB). `POPF` stays. No translation that differs between the views is global |
| 4 | Start-up configuration, x86-64 | The field values of `IA32_S_CET` and `IA32_U_CET` (B.1.5), `NO_TRACK_EN` = 0 among them; **`IA32_STAR`** and the required GDT selector layout (`KERNEL_CS = K`, `KERNEL_SS = K + 8`, `USER_SS = U + 8` RPL 3, `USER_CS = U + 16` RPL 3, V3-7a); `IA32_FMASK`; `IA32_SYSENTER_CS` = 0; `IA32_TSC_AUX`; `CR4.LA57` check selecting `47` vs `56` in `Y18` (V3-7b); `LMCE_EN`; `CR4.MCE` on every core; the timer in TSC-deadline mode; the kernel and the gate built without no-track jump tables |
| 5 | G1 and kernel.md, "Gate entries for privileged writes" | New entries: `mc_collect` (reads the log), and under variant (a) `ret_user`, `ret_user_fast`, `ret_kernel`; port access and `load_root` are windowed calls; the short entries are B.1.11's |
| 6 | G10 and `abi/` | A number for "ordinary vector": `IKV_FIRST` and `IKV_LAST` inside 240 to 255; the ICR composed by the gate (fixed, physical, edge, no shorthand); the target named by core number. For a line without remapping (operation 5), the vector in 48 to 239 |
| 7 | A new table at the head of the kernel image (M4) | The kernel entry table: the fixed addresses gate text jumps to. x86-64: `deferred_events`, `kernel_syscall`, `kernel_nmi`, **`kernel_db`**, `kernel_mc_user`, and one handler per vector 0 to 255 for events outside gate text. ARM64: the kernel's vector page, its SDEI handler, the fence handler. RISC-V: the kernel's trap entry. If every node runs one image linked with the gate, a sentence saying so replaces the table |
| 8 | kernel.md, "An event taken inside a gate call", rules (1) to (6) | Replaced by V1 to V13; the sentence "saves the interrupted registers in a gate area, and restores them from there" removed on the three architectures; the ARM64 and RISC-V paragraphs lose "Each loads the kernel's `TTBR1_EL1` ... as its first act" |
| 9 | Debugging (production and development images; V3-6) | **Both builds:** refuse `DR7.GD = 1` and `R/Wn = 10` (I/O breakpoints). **Development allow-range:** exclude the entire gate private linear view (table pages, table-page clearing view, living part, gate part, unit registers and unit tables), gate stack, interrupt stacks on both sides, all shadow stacks, read-only gate tables, pending/deferred-DR6 page, `RBLOCK_OF`, CPL-3 IST user blocks, `RFRAME_OF`, machine-check log, node beacon (`panic`), clock page, `parked` and crash area |
| 10 | ARM64 (kernel.md line 149; V3-8a, V3-8d) | `SCTLR_ELx.EIS` and `EOS` = 1; `TCR_ELx.A1` = 1; the return rule A-V10 (`SPSel`, DAIF, `ALLINT`); the start-up check of the `MPIDR` field; the SDEI entry's test of X2; the `_EL12` encodings on the scan's list; **`HCR_EL2` and `HCRX_EL2`** on the forbidden-register list (`kernel.md` line 149 already forbids `HCR_EL2` and must add `HCRX_EL2`, which controls `GCSEn` and FEAT_GCS at EL1); if FEAT_GCS is ever enabled, require `GCSCR_ELx.PCRSEL = 1`, `SCR_EL3.GCSEn = 1` and `HCRX_EL2.GCSEn = 1`; the twin vector page; `load_root` rewrites the saved `TTBR1` slot |
| 11 | RISC-V | `stvec` in direct mode, one value per hart; the return rule R-V10 (SUM, MXR); `load_root` rewrites the saved `satp` slot; the reserved ASID |
| 12 | The fence, x86-64, step 4 | The citation of INIT clearing CR4 (Table 12-1), and a sentence on the wait between INIT and the SIPI, during which CR4.MCE is clear |
| 13 | Interrupts, x86-64; the start-up page | The adversarial promise requires interrupt remapping with compatibility-format messages blocked; the flag `Interrupts` bit 0 gains that meaning |
| 14 | "What it costs and what it does not cover" | The promise per architecture (part A); the residue items the owners keep; on ARM64 and RISC-V, "BTI and Zicfilp do not change this" |
| 15 | I/O ports, "User code cannot execute `in` or `out`" | Under variant (a): IOPL 0 is enforced by the gate, not by the kernel. Under (b): the sentence that names port I/O outside the promise |
| 16 | Requirements on the kernel | Its NMI work may be entered twice (B.1.6); `kernel_nmi`, `kernel_db` and `kernel_mc_user` entered from CPL 3 run on `IA32_PL0_SSP` and read their per-core user blocks (`NMIUSER_BLOCK_OF`, `DBUSER_BLOCK_OF`, `MCUSER_BLOCK_OF`); its machine-check handler tolerates duplicate log records from shared banks and nested NMI restarts in Step 4 (B.5.3); it checks its pending word at the end of each event; it writes `RBLOCK_OF` before a return entry; a healthy kernel calls with IF = 0 (x86-64), `SPSel` = 1 (ARM64) |
| 17 | `NMI_GRACE_NS` | Greater than *H*, with *H* covering P0 to E3 |

---

## E. What a model checker should check

**State, per core.**
- `step`: outside; a row of an entry (`P0..P7`, `W0..W2`, body, `X0..X3`, `E0..E3`); a row of a short entry or of a return entry (`I0..I16`, `U0..U24` incl. `U2a`, `Y0..Y21`); `L0..L2`; a stub's row (`N0..N19`, `S0..S17`, `NMI_H0..H3`, `DB_H0..H3`, `MC_N0..N4`, `MC_SW0..MC_SW8`, `MC_R2_0..MC_S17`, `MC_JNMI_*`, `C0..C13`, `M0..M9`); `T0..T26` (incl. `mc_check_stop_or_clear_mcip`); the park loop; a kernel handler.
- `flags`: IF, TF, DF, NT, IOPL. `cpl`.
- `root`: kernel (with a tag) or gate. `rsp`: caller's, gate stack, `IST1..IST4` (with the side the address maps to under `root`), `F = F_BASE + 0x40` inside `RFRAME_OF`.
- `ssp`: `0`, `IA32_PL0_SSP`, `IST1..IST4`, `MC_RSHSTK`, `MC_RSHSTK + 24`, or `PARK_RSHSTK`; its depth and words.
- `tokens`: busy or free for `IST1..IST4` and `IA32_PL0_SSP`. `nmi_blocked`. `mcip`. `row7_sticky`.
- `tracker`: idle or waiting for `ENDBR64`.
- `pending`: the bits of the core's word; `completed`: how many times the call's body has run to its end.
- On `RFRAME_OF` (shadow-stack-typed, tamper-proof by sibling cores): `F`'s 6 words, `IST_SAVE_MC` (`rip`, `rflags`, `rsp`, `rax`, `rcx`, `rdx`, `old_ssp`, `old_lip`, `target_ssp`, `return_mode`, `row7_sticky`), `MC_RSHSTK`, `PARK_RSHSTK`. On kernel-writable pages: `RBLOCK_OF`'s 7 words and the 6 words each of `NMIUSER_BLOCK_OF`, `DBUSER_BLOCK_OF`, `MCUSER_BLOCK_OF`, each "as written by gate text in this run" or "adversary's".
- Registers that carry trust: RAX, RCX, RDX, R11, each "as computed in this run" or "adversary's".
- Per node: the gate lock, the view epoch.

**The adversary's moves.**
1. Any event of the tables at any row boundary: maskable interrupt, NMI, `#MC` (local or broadcast, any bank contents), `#DB` (TF or data/code breakpoint, including `MOV SS` deferred data breakpoint at `L0` or `N0`), a fault of the instruction, SMI, INIT.
2. Any register, flag and stack pointer at entry; an entry by a jump to any address of gate text, with or without TF.
3. A second core of the node writing any kernel-writable page at any time: **every word of any frame not on a gate-side stack or on `RFRAME_OF`** (CS and SS included: M1), the saved-register slots on a kernel-side stack, the pending words, `RBLOCK_OF`, `NMIUSER_BLOCK_OF`, `DBUSER_BLOCK_OF`, `MCUSER_BLOCK_OF`, the beacon.
4. A second core of the node calling any gate entry at any time.
5. A device writing any page the node may map for DMA; under precondition 3, no interrupt but through a remapping entry.
6. Any kernel handler: when control is given to the kernel, it may change every register and flag and return, through `ret_kernel`, `ret_user` or `ret_user_fast` (variant (a)) or by its own `IRETQ` (variant (b)), or jump to `L0`/`U0`/`Y0`, or never return.

**The properties.**
1. No kernel instruction executes while `root` is the gate's, nor between P7 and X3 of a call.
2. Every store made with `root` = gate is made by gate text; a frame the processor pushes with `root` = gate lands on a gate-side stack or the gate stack (the P7-to-W0 row).
3. **At every `MOV CR3`, `WRMSR`, `WRSSQ`, `RSTORSSP`, `INCSSPQ`, `CLRSSBSY`, `OUT` and `IRETQ` of gate text, every operand, the stack pointer of the `IRETQ` included, is "as computed in this run"** (V12).
4. `completed` goes from 0 to 1 at most once per call, or the node is fatal.
5. Every NMI taken between P0 and E3 sets its bit, and the bit is set at some later E1 of that call unless a core of the node cleared the word **or corrupted saved `RDX` on a kernel-side IST stack during an event at `E0..E3`** (V3-7g).
6. **NMI blocking is never cleared inside an unfinished NMI stub; no NMI ever faults on a busy `IST1` token** (restored from version 2: Row G1 is eliminated, V3-1).
7. **No IST token (`IST1..IST4`) is busy when control reaches kernel code entered from CPL 3 or user code; `U0` and `Y0` reject `SSP != PL0_SSP_OF[core]` as F** (V3-5).
8. `mcip` is clear whenever a kernel instruction executes, and `IST3`'s token is always free before `mcip` is cleared (V3-2a).
9. **All four `IST1..IST4` tokens are free whenever `park` is reached; no delivery faults with `IST4`'s token busy (no triple fault)** (OPEN-2 / ARGON-1 closed).
10. **Under variant (a): `cpl` = 3 implies IOPL = 0; and every `IRETQ` pops from `RFRAME_OF` or from a gate-side stack, with all words "as written by gate text in this run".**
11. On ARM64 and RISC-V: properties 1, 2 and 4 with the rows of B.3.2 and B.4; SP is the gate stack's only while the window is open; `ALLINT`, DAIF and `SPSel` at Z8 are as A-V10 says. The adversary's move 2 is not given to these models (the promise there excludes it).

**Order of work:** the x86-64 entry and exit with moves 1, 2 and 6 on one core; then the stubs (including the full 4 × 4 IST nesting matrix), `T0..T26` and the return entries (`U0..U24`, `Y0..Y21`); then move 3; then the short entries and `L0..L2`; then the machine-check rule as a table of bank contents; then ARM64 and RISC-V.

---

## Sources

- Intel SDM 325462-093US. Read by me in version 4 pass: vol. 2A `CLRSSBSY` (p. 3-150), `INCSSPD/INCSSPQ` (p. 3-459), `INT n` (`INTER-PRIVILEGE-LEVEL-INTERRUPT` and `INTRA-PRIVILEGE-LEVEL-INTERRUPT`, shadow-stack 32-byte alignment and `NewSSP - 4` zero store), `IRET` (`RETURN-TO-OUTER-PRIVILEGE-LEVEL` p. 3-494 `cmpxchg8b` on `SSP`, `RETURN-TO-SAME-PRIVILEGE-LEVEL` p. 3-495); vol. 2B `RSTORSSP` (pp. 4-598–4-599), `SAVEPREVSSP`, `RDSSPD/RDSSPQ`, `SETSSBSY`, `SYSCALL` (`IA32_STAR[47:32]`), `SYSRET` (pp. 4-709–4-710, `IA32_STAR[63:48]` and non-canonical `RCX` `#GP(0)` before `CPL := 3`); vol. 2D `WRSSD/WRSSQ`; vol. 3A §5.6.1 ("Access Rights", pp. 5-33–5-34, supervisor data reads from shadow-stack pages — closes OPEN-6), §7.7.2, §7.8.3 (`MOV SS`/`POP SS` data-breakpoint inhibition and `TF` suppression), Table 7-5 (double-fault combinations); vol. 3B §18.3.1.2, §20.2.3 (`DR6` reset `FFFF0FF0H`), §20.2.4 (`DR7.GD` bit 13 and `R/Wn = 10` I/O breakpoints). Read in earlier passes: vol. 1 §18.3, §18.3.1, §20.5.2; vol. 2B `MOV` to control registers, `POPF`, `PUSH`, `SYSENTER`; vol. 3A §5.10.1 to §5.10.4.1, §7.8.1, §7.12.1.1, §7.12.1.3, §7.14.5, §7.15, §12.1.1 with Table 12-1, §13.5.2, §13.11.2 with Figure 13-25, §13.12.9 with Figure 13-28; vol. 3B chapter 18, virtual-8086 I/O bitmap; vol. 3C primary processor-based I/O controls, §34.8; vol. 4 Table 2-2 MSRs 6A0H and 6A2H. Not read by me: the flags of the far `RET` and of `SYSEXIT` (from document 5), `RDPID` and Table 7-2 (from document 3).
- Arm DDI 0487 M.d. Read by me in version 4 pass: Table D8-74 (`0b0101` = Read+Write), `RQXXPC` (`PrivExecute` removes `PrivWrite`), D11.2.1 (`RBYVYL` `GCSCR_ELx.PCRSEL`, `RWFTRC` `SCR_EL3.GCSEn` and `HCRX_EL2.GCSEn`), D24.1.2.2 (System register synchronization and `ISB` — closes OPEN-8), D24.2.150 (`POR_EL1` `0b0101` and no synchronization exemption). Read in earlier passes: chapter A2, C5.2.1 (`ALLINT`), D1.4.2, D8 (`RVNRFW`, `ISKPNZ`, `IKPGBV`, Tables D8-72, D8-85), D8.16.3.1, D11 (`ICCMMC`, `SGRGDT`, `RFFJDX`), D24.2 (`TCR_EL1`, `MPIDR_EL1`, `HCR_EL2.TVM`, `EIS`), `AArch64_TakeException`. Not read by me: the GCS conditions RTNHNB and RJTRFY and the remaining fields of `GCSCR_ELx` (from document 5); D24.2 on VHE redirection (from document 3).
- Arm DEN 0054C, §5.2.1, §5.2.1.1, §5.2.1.2: read by me (earlier pass).
- RISC-V privileged 20240411: §10.1.1 (SIE), §10.1.2 with Table 21, §10.1.11, §10.2.1, §10.3.1, the sentence on `hstatus.VTVM`: read by me. Chapter 8 (Smrnmi): from document 4.
- The contract and docs, read by me: `architecture/kernel.md` (including line 149), `architecture/kernel-interface.md` (lines 800–815, 1672–1675, 2084), `decisions/README.md` (D-120, D-142, D-143, D-149 to D-153).
- From memory, none opened: the VT-d control for compatibility-format messages (OPEN-7); PCI bridge bus numbers (OPEN-7); Linux's use of `A1` = 1 and of `TPIDRRO_EL0` as a scratch register; seL4's interrupts-off kernel; Xen's shadow-stack fix-up; Linux's handling of a machine check in kernel context; the cost of a trap to EL2; the Zicfilp and Zicfiss rules; that `IA32_CSTAR` serves `SYSCALL` from compatibility mode.
