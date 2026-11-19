# The gate call: entry, exit and events (version 2, draft, not normative)

Written 19 November 2026 by Claude Fable 5.2, as a design draft for the two owners. **Nothing here is a rule of the contract.** It replaces version 1 (the proposal in the re-judgement of the x86-64 gate review) and answers the attack on it. Head of the repository when written: `44ae630`.

It specifies, for x86-64 mechanism 2 (a translation root used only by the gate), for ARM64 and for RISC-V, what a gate call does from its first instruction to its last, and what happens to every event that can arrive at every instruction. It does not specify x86-64 mechanism 1; part B.2 says what that mechanism cannot do, for the owners' decision on D-120.

**Inputs, in order:** the review of the x86-64 gate's events (document 1); its re-judgement with the proposal called version 1 (document 2); the attack on version 1 with the manuals open (document 3); `architecture/kernel.md` (the mechanisms); `architecture/kernel-interface.md` (G1 to G16, Gate words); D-120, D-149 to D-152.

**Marks.**
- **[R]**: read by me in the primary source during this pass; the quotation is the manual's own text.
- **[3]**: read by document 3 with the manual open and not re-read by me; to be re-read before it enters a decision.
- **UNVERIFIED**: not found or not read; the cell says what must be read.
- **(choice)**: my design choice, with the alternative I rejected and its cost.
- **(estimate)**: my figure, measured nowhere.
- **OPEN**: a row I could not make sound; the options are in part D.

**Primary sources (title pages checked):** Intel SDM, order 325462-093US, September 2026 ("SDM"); Arm DDI 0487 M.d, 30 September 2026 ("Arm ARM"); Arm DEN 0054C, SDEI ("SDEI"); RISC-V privileged architecture, version 20240411 ("RISC-V priv").

**What changed from version 1, in six lines.**
1. An event whose interrupted address lies in gate text never reaches the kernel's handler. The stub marks it and returns by its own `IRETQ`. The kernel's handler runs only for events that interrupted code outside gate text. Version 1 ran the kernel's handler and then rewound, which let kernel code run between a stub's computation and its use.
2. A deferred event is delivered at the call's exit by a plain jump to a kernel routine, never by `INT 2`. No shadow-stack token is busy while it runs.
3. "Open" is read from CR3 (the reserved PCID), not from a flag page.
4. `load_root` and port access are windowed calls. The short entries that remain have a restart range that ends before the acting instruction.
5. The machine-check stub classifies in gate text and clears MCIP itself. No kernel code ever runs with MCIP set.
6. The pending word is a per-core word the kernel can read and clear. The gate never takes a trusted decision from it.

---

## A. The threat and the promise

1. **Held against a faulty kernel on every core of its node.** The kernel may call the gate with any register values, any flags, any stack pointer, from any of its cores at once, and may write any page it maps writable at any time.
2. **Held against an adversarial kernel on x86-64 with supervisor shadow stacks and IBT**, as far as part C shows (every break of version 1 has a closing row or is listed as not closed). **On ARM64 and RISC-V it is held against a faulty kernel only**: an exception return is an unchecked jump there (finding N4, part B.3).
3. **Held against the node's devices**: no page the sequence relies on can be the target of an iospace leaf or a user leaf (the memory tables below).
4. **The promise:** no kernel instruction runs while the gate's root is loaded; every store the gate makes is one the rules G1 to G16 allow; a call completes once or not at all; no event is lost unless the node's own kernel clears its own pending word.
5. **The cost of the promise is availability of the faulty node only**: a kernel can make its own gate calls restart for ever, and can get its own node declared fatal.

**The residue no sequence of this kind closes** (the two lists at the end of documents 2 and 3, merged):

| # | Item | From | Should the contract name it as outside the promise? |
|---|---|---|---|
| 1 | Transient execution: nothing here bounds what one node reads of another by speculation, in the gate's text included | 2, 3 | Yes. "Not covered" today names integrity gaps only |
| 2 | SMM and firmware (EL3, machine mode), which see every state, an open window included | 2, 3 | Already named ("firmware (SMM, EL3, machine mode)") |
| 3 | The processor's behaviour where the manual is silent, and errata: the shutdown response, a latched NMI, a platform's response to one core in shutdown | 2, 3 | Yes, as a class, with the trials of part D |
| 4 | A machine without control-flow protection: without CET on x86-64, BTI on ARM64, Zicfilp on RISC-V | 2, 3 | Already flagged in the start-up page; extend the sentence to ARM64 and RISC-V |
| 5 | The gate's own code and the scanner: larger than a leaf function; a decoding bug of the x86 scan | 2, 3 | Already named ("a bug in the gate") |
| 6 | IBT across an asynchronous event under IDT delivery | 2 | No longer residue on x86-64: closed by rule V3 (part C, N1). Keep it only for a machine without CET |
| 7 | Broadcast machine checks and banks shared across nodes: an error in a shared bank that no node can be charged with stops the machine | 3 | Yes. Part B.5 gives the rule; the stop is part of the promise's limit |
| 8 | Platform effects outside the IOMMU and the gate: PCIe fatal errors, device resets, thermal or power events, shared buses of the `platform` role | 3 | Yes, one sentence |
| 9 | Availability across nodes through shared hardware: cache and memory-bandwidth pressure, bus locks, rowhammer | 3 | Yes. Rowhammer is an integrity threat the gate does not hold; say so plainly |
| 10 | Out-of-band engines with physical memory access (management engine, BMC, external debug) | 3 | Yes, beside firmware |
| 11 | Gadgets inside gate text: a bounds bug or an indirect branch in the gate | 3 | Covered by item 5; no separate sentence |
| 12 | An exception return used as a jump on ARM64 and RISC-V (N4, mine) | new | Yes, until decision 2 of part D is taken |
| 13 | A core without machine-check delivery enabled (parked after INIT) at a broadcast machine check | new | Yes if trial T9 confirms it |

---

## B. The specification

### B.0 Cell codes

Each event cell holds one code.

| Code | Meaning |
|---|---|
| **no** (reason) | Cannot occur. If it occurs all the same, the stub treats it as **F** |
| **R** | Restart from the entry. The stub marks the event pending, rewrites the return address to the entry's first instruction and returns by its own `IRETQ`. No kernel instruction runs |
| **D** | Deferred. The stub marks the event pending and returns by its own `IRETQ` to the interrupted instruction. Delivered at the call's exit |
| **F** | Fatal to the node (B.1.9) |
| **FW** | Firmware's. It runs and returns to the interrupted instruction, or never returns; no kernel code runs |
| **K** | The kernel's handler runs and returns to the same instruction. Allowed only at rows where nothing trusted has been computed |
| **MC** | By the machine-check rule (B.5): the stub stops the machine, or declares the node fatal, or clears MCIP and then acts as the NMI cell of the same row |

INIT is **F** in every row of every x86-64 table: it is sent only by a fence (G10), the call is abandoned, and G12 (2) with G13 cover a call left half done. SMI is **FW** in every row. Both columns are kept in the tables because a model checker needs them.

### B.1 x86-64, mechanism 2

#### B.1.1 Rules

- **V1. No kernel instruction runs between a call's opening instruction and its closing instruction.** An event there is deferred in a stub, is fatal, or is firmware's. Nothing is saved for a kernel handler to resume. (Choice. Rejected: "save, run the kernel's handler, restore", which is kernel.md's first sentence on the subject. Its cost is a kernel that runs in the middle of a call while the gate lock is held, and may call the gate again.)
- **V2. All 256 IDT vectors are interrupt gates whose target is a gate stub.** "Accessing a handler procedure through a trap gate does not affect the IF flag" (SDM vol. 3A §7.12.1.3 [R]), so no vector is a trap gate. Every descriptor has DPL 0, except vector 3 (DPL 3), so that a user `INT3` stays a breakpoint (choice; the alternative, DPL 0 with the kernel decoding a `#GP`, costs a decoder).
- **V3. An event whose interrupted address lies in gate text is never given to the kernel.** The interrupted address is the one the processor pushed on the stub's shadow stack. The stub handles it by one of **R**, **D** or **F** and ends with its own `IRETQ`. The two exceptions are maskable interrupts at the first two instructions of an entry (cell **K**), where nothing trusted exists yet.
- **V4. Open means "CR3 holds the reserved tag".** A stub reads CR3 and compares bits 11:0 with `GATE_PCID`. CR3 is written only in gate text (G11). (Choice. Rejected: version 1's flag page with two mappings at one address. It needs no register, but its answer is a TLB lookup, so a stale entry would give the wrong answer; and it costs two pages. Linux's paranoid entry reads CR3 for the same question: secondary evidence, from memory.)
- **V5. The interrupted address is read from the shadow stack, never from the frame.** On a delivery from CPL 0 the processor "pushes the CS, LIP (CS.base + EIP), and SSP of the interrupted procedure" on the handler's shadow stack (§7.12.1.1 [R]). Shadow-stack pages take no ordinary store, and `WRSSQ` exists only in gate text (G11).
- **V6. Whether the event came from CPL 3 is read from SSP.** B.1.7 gives the test per kind of vector.
- **V7. A stub spills nothing trusted.** Every value a stub decides with (CR3, SSP, the interrupted address, a rewind target, a comparison) lives in a register from its computation to its use. A stub stores to its stack only the interrupted context's registers, whose corruption harms the interrupted context alone. No stub makes a `CALL`.
- **V8. Restart ranges end before the acting instruction.** A range is restarted only if every instruction in it can run twice. No instruction at or after the opening `MOV CR3` is in a restart range of the entry. A completed call is never run again.
- **V9. Nothing that differs between the gate's root and the kernel's roots is global.** B.1.3.
- **V10. The gate returns with IF = 0, DF = 0, and the arithmetic flags undefined.** The caller's IF is not saved and not restored: a healthy kernel calls the gate with IF = 0, and the entry's `CLI` is for the kernel that does not. (Choice. Rejected: saving the caller's flags, which needs a `PUSHFQ` on a stack the caller chose. seL4 runs its whole kernel with interrupts off: secondary evidence, from memory.)
- **V11. The gate reads its arguments from registers only.** It never dereferences the caller's RSP or a pointer the caller passed. A batch is described by registers (a frame, a first page, a count, rights), as the contract's calls already are.

#### B.1.2 Memory

"Twin" means two physical pages at one linear address: one under the kernel's roots, one under the gate's root.

| Page | Linear address | Under the kernel's roots and every aspace root | Under this core's gate root | Global | Class in the contract's terms |
|---|---|---|---|---|---|
| Gate text: entries, stubs, the system-call rows, the park loop | Same on all cores | Read, execute | Read, execute, same page | May be | *global read-only* (kept image). In pages apart from kernel text |
| Read-only gate tables: `ROOTS` (per core: the gate root's value with `GATE_PCID` and bit 63), `PL0_SSP_OF` (per core), the text-range table | Same | Read | Read, same page | May be | *global read-only*; written at node start-up |
| IDT, GDT, TSS, the interrupt SSP table | Per core | Read | Read, same page | May be | kept, written once at start-up (kernel.md) |
| Gate root of core *c* and its private tables | Not mapped as data in any kernel view | Not mapped | The gate's window on table pages | No | *kernel table* (kept, fixed) |
| Gate stack of core *c* | `GATE_STACK`, same on all cores | Not present | Read, write | No | *gate* (kept memory of the gate) |
| IST1 to IST4 stacks of core *c* (NMI, #DB, #MC, #DF), **kernel side** | Per core: IST pointers of core *c*'s TSS | Read, write | — | No | kept memory, "the kernel's own stacks" (start-up memory rule 1) |
| The same four stacks, **gate side** | The same four addresses | — | Read, write; other cores' IST addresses not present | No | *gate* |
| Shadow stacks of IST1 to IST4 of core *c*, each with its token | Per core | Shadow-stack page (R/W 0, dirty 1) | The same page, same typing | May be | *gate* ("the kernel's shadow stacks", G2) |
| The kernel's shadow stack of core *c* (`IA32_PL0_SSP`), with its token | Per core | Shadow-stack page | The same | May be | *gate* |
| Pending word of core *c*, and its deferred-DR6 word | `KPEND + 8c`, in one page per node | Read, write | Read, write, same page | No | kept memory of the node, kernel-writable |
| The node beacon (`panic`) | As today | Read, write | Read, write, same page | No | as today |
| Kernel text, kernel data, the kernel's stacks | As today | As today | **Not present** | **No** | as today |
| Table pages, the living part, the gate part, unit registers | The gate's own addresses | Read only, or not present (unit registers: G9) | Read, write | No | as today |

- **No iospace leaf and no user leaf can target any of these pages.** G3 (2) lets a leaf target an owned chunk, the floor, a grant, the global read-only set or a device entry; kept memory is none of them, and a *gate* page is refused by G3 (3). This is document 3's answer to N2 and needs no new stored class. G2's list of what the class *gate* covers should name the gate stack and the gate-side interrupt stacks, and say that the kernel-side interrupt stacks are kept memory (a wording change for the contract, not a new rule).
- **Token placement.** Each address in the interrupt SSP table and `IA32_PL0_SSP` satisfies `(address AND 1FH) = 18H`, holds a token equal to the address with bit 0 clear, and is the highest slot of its stack, below a guard page. The processor requires it: "Token and CS:LIP:oldSSP pushed on shadow stack must be contained in a naturally aligned 32-byte region ... IF (NewSSP & ~0x1F) != ((NewSSP – 24) & ~0x1F) #GP(0)" (SDM vol. 2A, `INT n`, pseudo-code of the 64-bit gate [R]).
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
- **Maskable interrupts cannot arrive after P1.** IF is cleared at P1. A stub returns into an entry only at P0 (cell R), and the kernel's own `IRETQ` can return into gate text only at P0 or P1 (the two K cells), because its return address is compared with the shadow stack (§7.12.1.1 [R]) and no other gate address was ever pushed for a kernel handler. So every path to P2 passed P1 with no later change of IF.
- **`STI` then a jump or call to P0.** The interrupt is held for one instruction ("Nonmaskable interrupts and system-management interrupts may also be inhibited on the instruction boundary following such an execution of STI", §7.8.1, note [R]) and arrives at P0: K.
- **`MOV SS` or `POP SS` then a call.** "Any single-step trap that would be delivered following the MOV to SS instruction ... is suppressed", and a data breakpoint "is inhibited until the instruction boundary following the next instruction" (§7.8.3 [R]). Both land at P0: R.
- **A single step cannot arrive at or after W0.** No prologue instruction changes TF. With TF = 1 at P0 a trap is taken before P1, and the stub clears TF in the frame before it restarts the entry. A stub's `IRETQ` into an entry lands at P0 only. So a path that executes P7 had TF = 0 from P0 on. (If another core of the node writes TF = 1 back into the frame on the kernel-side stack, the entry restarts again: the node loses its own time.)
- **Between P7 and W0 the stack pointer is still the caller's.** Only vectors with an IST index can arrive there (NMI, #MC; #DB and #DF cannot occur), and they push on gate-side stacks. A vector without an IST index would push a frame at an address the caller chose, under the gate's root; no such vector can arrive, because IF = 0 and W0 has no memory operand and no fault. This row must be checked by the model before any other.
- **A wild jump into P2 to P7** takes a `#CP` at the target (no `ENDBR64`): a fault in gate text, F (B.1.7). With an event taken first (N1), the stub sees an address in the restart range and restarts at P0, which recomputes every register.

#### B.1.5 The body

- **Stack:** the gate stack. **Shadow stack:** the caller's (the gate's own `CALL`s push on it); it takes no ordinary store from any core. A caller that leaves too little room on it takes a fault in the window, which is F for its node. (Choice. Rejected: a gate shadow stack per core, which needs a restore token and `RSTORSSP` at every entry.)
- **First step:** the view-epoch check of B.1.3; then the address of this core's pending word is computed; then, for an entry that writes, the gate lock.
- **A write of the living part** is `LOCK CMPXCHG` on the gate root's writable mapping of the word: an ordinary instruction under mechanism 2.
- **A write of a device register** is one plain store of a whole value (D-126) to the unit's page, which only the gate root of the role's holder maps (G9).
- **Clearing a table page** may use `REP STOS`: DF is 0 since P2.
- **What the kernel controls, and how each is made harmless** (version 1's table, corrected):

| State | Treatment |
|---|---|
| RSP | Never dereferenced. Saved as a value at P6, restored at E0 |
| IF | `CLI` at P1; V10 at exit |
| DF | `CLD` at P2 |
| TF | Cleared in the frame by the #DB stub, which restarts the entry (B.1.4); no `PUSHFQ` anywhere |
| AC | Not cleared: it matters only for user pages, which the gate's root does not map. Version 1's `CLAC` is removed (it is `#UD` without SMAP) |
| NT, RF, VM | "the processor also clears the VM, RF, and NT flags" at delivery (§7.12.1.3 [R]); a stub's `IRETQ` with NT set faults in gate text: F |
| Arithmetic flags | Undefined at entry and after every `MOV` to CR3 ("The OF, SF, ZF, AF, PF, and CF flags are undefined", SDM vol. 2B [R]); the gate tests nothing across one |
| General registers | Arguments are checked as values (V11); RAX, RCX, R11 are overwritten by the prologue |
| Segment registers, FS and GS bases, `SWAPGS` state | Not used: no segment prefix in gate text (the scan checks). The core is found by `RDPID` |
| CR2, CR8 | Never read; CR8 matters only with IF = 1 |
| x87, SSE and AVX state | Gate text is built without them |
| DR0 to DR3, DR7 | Written by the gate only. Production: user range only. Development: also kernel addresses outside gate text, gate memory, the living part, table pages, **the interrupt stacks on both sides, every shadow stack, the read-only gate tables and the pending page** |
| DR6 | "Updates to this register only occur when an exception is generated" (§20.2.3 [R]); the #DB stub copies it to the deferred-DR6 word and loads the reset value |
| SSP and tokens | Confined by guard pages; `RSTORSSP`, `SAVEPREVSSP`, `SETSSBSY`, `CLRSSBSY`, `WRSS*`, `WRUSS*` in gate text only (kernel.md's list should name the first two) |
| `IA32_S_CET`, `IA32_PL0_SSP`, the SSP table, `IA32_TSC_AUX`, `IA32_LSTAR`, `IA32_FMASK`, `IA32_DEBUGCTL`, the counters, Processor Trace, PKRS | `WRMSR` only, so the gate's; set at start-up |
| IBT tracker | Entries start with `ENDBR64`; a wild entry is F or R (B.1.4) |

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
| E2 | `JNZ deferred_events` | Direct jump to the kernel's routine, or falls through | no | D, back to E1 | MC | MC | D, back to E1 | no | no | FW | F |
| E3 | `RET` | Back in the caller, IF = 0 | no | D, back to E1 | MC | MC | D, back to E1 | no | F (the caller's stack or shadow stack is wrong) | FW | F |

- **Restart rows and rows that are not.** Restart to the entry: P0 to P7 only. Re-test: an event at E2 or E3 returns to E1, which only reads. No row from W0 to E0 is ever re-entered: an event there returns to the interrupted instruction. This is what "a completed call is never re-run" means here.
- **At E0 the stack pointer is the gate stack's address under the kernel's root, where it is not present.** An NMI or a machine check there uses an IST stack; nothing is pushed at RSP, and no kernel code runs (V3). This is the case document 3's break 1A found.
- **A single step at E0 to E3** is possible only if another core wrote TF into a frame on a kernel-side stack; the stub clears it and marks the event.
- **`load_root` closes directly to the new root.** X1 loads the root and tag the body checked and recorded, so a switch of address space costs two CR3 writes, not three.

**The delivery, and who pushes what on which shadow stack.**

| Step | Who | Regular stack | Shadow stack | NMI blocking |
|---|---|---|---|---|
| NMI taken at a row marked D or R | Processor | Frame of 5 words on IST1 (gate side if open, kernel side if not) | Marks IST1's token busy; pushes CS, LIP, SSP on IST1's shadow stack | Established |
| The stub | Gate text | Pushes and pops the context's scratch registers; for R, rewrites the frame's RIP | For R, one `WRSSQ` of the slot at SSP + 8; no `CALL`, so nothing else | Held |
| The stub's `IRETQ` | Processor | Pops the frame | Compares CS and LIP, pops three words, frees the token ("IF tempSSP != SSP THEN ... clear the busy bit", SDM vol. 2A, `IRET` pseudo-code [R]) | "NMI delivery is unblocked once execution of IRET commences" (§7.7.2 [R]) |
| E2 taken | Gate text | Nothing | Nothing: a direct `JMP` | Not blocked |
| `deferred_events` (kernel code) | Kernel | Its own frames on the caller's stack | Its own `CALL`s on the caller's shadow stack; its `RET` meets the return address the caller's `CALL` pushed | Not blocked |
| A hardware NMI during the routine | Processor | IST1, whose token is free | Token busy again, three words | Established; the interrupted address is outside gate text, so the kernel's handler runs and ends by `IRETQ` |

- **No software `INT 2`.** The routine takes the bits (`XCHG` with 0 on its pending word) and calls the kernel's NMI work as a function. Document 3's break 6A came from replaying through vector 2, which marks the token busy without blocking NMIs.
- **What the kernel's NMI work must be** (a requirement on the kernel, to enter the contract when this does): it may be entered from the routine and, nested, from a hardware NMI on the same core, so it reads words (the fence mark, the start request) and writes records in a way that is safe to repeat; it counts nothing. On x86-64 that is already its content (kernel.md, rule (2)).
- **The kernel also checks its pending word at the end of every kernel event and before it idles.** An event marked outside a gate call (a machine check of class "continue", B.5) is delivered there.
- **Bound on the delay.** An NMI taken anywhere from P0 to E3 is delivered no later than the jump at E2 of that call, which is the contract's *H*.

#### B.1.7 The vector table and the stubs

**How a stub classifies.** It pushes three scratch registers, reads CR3, reads SSP (`RDSSPQ`), and when a shadow frame exists reads the interrupted address at SSP + 8. It compares that address with the ranges of the read-only text-range table. From the first of these reads to the last use is the stub's **critical range**; its first instruction is the stub's **redo label**.

**Did the event come from CPL 3?**
- Vectors with an IST index: `(SSP AND 1FH) = 18H` means CPL 3 (the processor switched to the IST shadow stack and pushed nothing); `0` means CPL 0 (three words pushed). The token placement of B.1.2 makes the two cases disjoint [3].
- Vectors without an IST index: SSP equals this core's entry of `PL0_SSP_OF` (found by `RDPID`) means CPL 3. From CPL 0 the processor pushed three words below the interrupted SSP, which is never the token's address since the token is the highest slot.

| Interrupted address | Open | Not open |
|---|---|---|
| Outside gate text, from CPL 3 | F (cannot be) | The kernel's handler |
| Outside gate text, from CPL 0 | F (cannot be) | The kernel's handler; for #MC of class "continue", marked and returned instead (B.5) |
| P0 to P7 of an entry; the restart range of a short entry | — | **R** for NMI, #MC, #DB. Maskable at P0 or P1: **K**. Any other vector: F |
| W0 to X3 (the body) | **D** for NMI and #MC. Every other vector: F | F (a wild entry) |
| E0, E1; the last row of a short entry; the system-call rows; the park loop; a stub outside its critical range | — | **D** for NMI, #MC, #DB. Every other vector: F |
| E2, E3 | — | **D**, returning to E1 |
| A stub's critical range | D (the frame is private) | **D**, returning to that stub's redo label |

| Vector | Stack | Rule |
|---|---|---|
| 2, NMI | IST1 | The table above |
| 1, #DB | IST2 | The table above; in gate text it also clears TF in the frame, copies DR6 to the deferred-DR6 word and loads DR6 with FFFF0FF0H. Open: F |
| 18, #MC | IST3 | B.5 first, in gate text; then the table above. MCIP is cleared before any `IRETQ` or jump |
| 8, #DF | IST4 | **Always F.** It never jumps to the kernel (document 3, break 2A) |
| 3, #BP | current | DPL 3. Not open and outside gate text: the kernel's. Otherwise F |
| Other exceptions (0, 4 to 7, 9 to 17, 19 to 31) | current | Not open and outside gate text: the kernel's. Otherwise F. Open: the frame is on the gate stack |
| 32 to 255 | current | Not open and outside gate text, or at P0 or P1: the kernel's. Otherwise F |

- **Why a nested event restarts a stub's critical range.** With IF = 0 only an NMI or a machine check can interrupt a stub. By V3 neither runs kernel code, so the interrupted stub's registers are intact when it resumes; the return to the redo label is for the frame on a kernel-side stack, whose RSP and RFLAGS another core may have changed, so the stub recomputes from CR3 and SSP. Every action of a critical range can be repeated: the `WRSSQ` writes the same address, the `LOCK OR` sets the same bit, the DR6 copy finds the reset value.
- **The rewrite and the return.** For R the stub writes the entry's first address into the slot at SSP + 8 by `WRSSQ` and into the frame's RIP, then executes `IRETQ`, which "Compares the values on shadow stack at address SSP+8 (the LIP) and SSP+16 (the CS) to the CS and (CS.base + EIP) popped from the stack" (§7.12.1.1, as kernel.md quotes it). Document 3 read the `IRET` pseudo-code and found the pair accepted [3]; Xen fixes up a shadow-stack return slot the same way in its exception-table path (secondary evidence, from memory, to check). Trial T2.
- **OPEN-1. A machine check inside the NMI stub.** The #MC stub ends by `IRETQ`, which unblocks NMIs while the NMI stub is not finished. A second NMI then finds IST1's token busy and its delivery faults (`#GP(0)`, `INT n` pseudo-code [R]), in gate text: F. It needs a machine check of class "continue" and two NMIs within the length of one stub. Options in part D.
- **Software interrupts from the kernel.** `INT n`, `INT1`, `INT3` and `INTO` at CPL 0 leave an IST token busy if the kernel never returns. With vector 8 always F this harms the kernel's own node only. The scan should forbid them outside gate text all the same (a kernel has no use for them); see part D, contract changes.

#### B.1.8 The system-call entry

`SYSCALL` enters at CPL 0 with the user's RSP, and with shadow stacks on it executes "SSP := 0" and sets the tracker to `WAIT_FOR_ENDBRANCH`; it "masks RFLAGS using the IA32_FMASK MSR" (SDM vol. 2B, `SYSCALL` [R]). `SETSSBSY` is the gate's alone (kernel.md), so `IA32_LSTAR`'s target is in gate text:

| Row | Instruction | Holds after it | Mask | NMI | #MC | #DB | Fault |
|---|---|---|---|---|---|---|---|
| L0 | `ENDBR64` | CPL 0, SSP = 0, RSP the user's | no (`IA32_FMASK` clears IF) | D | MC | D (a data breakpoint held by `MOV SS`) | no |
| L1 | `SETSSBSY` | SSP = this core's kernel shadow stack, token busy | no | D | MC | D | F (`#CP(SETSSBSY)` when the token is not free [3]) |
| L2 | `JMP kernel_syscall` | In kernel text | no | D | MC | D | no |

- **`IA32_FMASK`** is written by the gate at start-up and clears IF, TF, DF, AC and NT.
- **No row is a restart row.** An event returns to the same instruction, so `SETSSBSY` runs once. Document 3's break 8A came from treating these rows either as a body (fatal) or as a restart range (`SETSSBSY` twice).
- **An NMI at L0 or L1** finds SSP = 0. The processor switches to IST1's shadow stack and pushes the old SSP, 0; the stub's `IRETQ` restores it [3]. The frame lies on the kernel-side stack; a core of the node that writes IF or TF into it harms its own node (the next event at CPL 0 with the user's RSP is the classic `SYSCALL` hazard, contained in the node's own translations).
- **Return to user mode is by `IRETQ` from kernel text (choice).** An `IRETQ` to CPL 3 frees the token at the current SSP ("safe to free the token", `IRET` pseudo-code [R]), and the event-driven kernel has unwound its shadow stack to the token by then. Rejected for now: a `CLRSSBSY; SYSRETQ` trampoline in gate text, which is faster and adds a second set of rows with SSP = 0. Trial T10 measures the difference.
- **Events from user mode on an IST vector** leave the kernel on the IST shadow stack with its token busy and nothing pushed. The kernel may change RSP to its own stack; it returns to user mode by `IRETQ` with SSP back at that token, which frees it. The IST shadow stacks are therefore as deep as the kernel's own (a page each).

#### B.1.9 Fatal to the node, and vector 8

"F" is one path in gate text:

1. If MCIP is set, run the machine-check rule first (it may stop the machine); clear MCIP.
2. Load this core's gate root, so that everything after is on pages no other core can write.
3. Write `panic` in the node beacon. The gate lock is left as it is (Gate words, the gate lock, column Death).
4. Build a frame from immediates on the gate-side stack, write the park loop's address into the shadow-stack slot, and execute `IRETQ` into the park loop. This frees the IST token and unblocks NMIs.
5. The park loop is in gate text, under the gate's root, with IF = 0. Every event there is D or MC and returns into the loop. INIT from the fence ends it.

- **OPEN-2. The shadow-stack state of the park loop, and a frame another core rewrites.** Step 4 needs a shadow frame to exist (it does not when the event came from CPL 3) and needs an SSP for the loop on which a later delivery without an IST index can push. And when F is reached while not open, steps 1 to 2 run with the frame on a kernel-side stack: an adversarial node of several cores can make `#DF` deliveries repeat until one faults with IST4's token busy, which is a triple fault: "the logical processor enters shutdown mode" (SDM vol. 2B, `PUSH`, on a stack fault met again during the delivery of a double fault [R]). Options in part D.

#### B.1.10 Short entries

Each entry is either windowed or has a restart range that excludes the acting instruction and everything after it.

| Entry | Form | Rows | Restart range | Why it is sound |
|---|---|---|---|---|
| End of interrupt (x2APIC) | Short | `ENDBR64`; `CLI`; `MOV ECX,80BH`; `XOR EAX,EAX`; `XOR EDX,EDX`; `WRMSR`; `RET` | From `ENDBR64` up to, not including, the execution of `WRMSR` | Every register the `WRMSR` uses is loaded from an immediate in the range; an event at `RET` is D with no rewind, so the write happens once |
| Timer deadline | Short | `ENDBR64`; `CLI`; `MOV RAX,RDI`; `MOV RDX,RDI`; `SHR RDX,32`; `MOV ECX,6E0H`; `WRMSR`; `RET` | As above | RDI is not written, so the range can run twice; any deadline is the caller's to choose |
| Interrupt to another core, ordinary vector | Short | `ENDBR64`; `CLI`; the vector check on immediates; `MFENCE`; `LFENCE`; `MOV ECX,830H`; the operand moves; `WRMSR`; `RET` | As above | G10 lets an ordinary vector go to any core, so no word is checked |
| INIT, SIPI, NMI to another core | Windowed | — | — | They follow writes of the fence record or the start request |
| Port access | **Windowed, under the gate lock** | — | — | The ownership word of a port entry can be given away by another core of the node between the check and the `OUT` (document 3, break 7C); `memory_give` takes the same lock |
| `load_root` | **Windowed** | — | — | It writes the loaded root and tag, the tag's set and the idle word, in the gate part (document 3, break 7A) |
| EOI register of an IOAPIC; a device register | Windowed | — | — | The page is mapped only under a gate root (G9) |

- **An event in a restart range is R**, also for an NMI that happens to land on a wild branch to the `WRMSR`: the restart reloads ECX.
- **The cost of a windowed port access** is two CR3 writes; the contract already accepts "under a microsecond" per access.

### B.2 x86-64 mechanism 1: what it cannot do

D-120 names page tables typed as shadow-stack pages as the first mechanism to prototype. These are facts for the owners; the decision is in part D.

| # | Fact | Source | Consequence |
|---|---|---|---|
| 1 | `WRSSD` and `WRSSQ` raise `#UD` "If the LOCK prefix is used" | SDM vol. 2D, `WRSSD/WRSSQ`, 64-bit mode exceptions [R] | No compare-and-swap exists on a page typed as a shadow stack: an ordinary `LOCK CMPXCHG` faults there, since CR4.CET requires CR0.WP (§2.5, quoted in kernel.md). The contract requires that "Every write of the living part is a compare-and-swap". Mechanism 1 cannot write the living part, on a node of one core either, because other nodes write it at the same time |
| 2 | `WRSSD` stores 4 bytes and `WRSSQ` 8 | the same entry [3] | The page class byte cannot be written alone |
| 3 | "Data may be read (implicitly or explicitly) from any supervisor-mode address" | SDM vol. 3A §5.6 [3] | A unit's registers typed this way are readable by the kernel, against G9's "in no kernel's view". Whether a shadow-stack store to uncached device memory works at all is undocumented [3] |
| 4 | The processor pushes an interrupt frame by ordinary stores ("The old SS, RSP, RFLAGS, CS, and RIP are pushed onto the new stack", §7.14.5 [R]) and compares only CS and the return address at `IRET` (§7.12.1.1) | [R] | The frame lies on a page the kernel maps writable; another core of the node can change RFLAGS and RSP before the stub returns |
| 5 | G3 lets an iospace leaf target any *data* page | the contract | A device of the node can write the stub stacks unless they are kept memory (document 3: placing them in kept memory closes this one) |

**What mechanism 1 can still do:** write page-table entries on a node of one core, with a second mechanism beside it for the living part, for device registers and for the events. That is two mechanisms in one gate.

### B.3 ARM64

**Finding N4 (mine; to be checked by another model before it enters a decision).** On ARM64 an exception return jumps to `ELR_ELx` with the state of `SPSR_ELx`, both of which the kernel writes. With BTI, "PSTATE.BTYPE is copied to SPSR_ELx.BTYPE and then PSTATE.BTYPE is set to 0" at an exception (Arm ARM D1.4.2 [R]), so a kernel that writes `SPSR_ELx.BTYPE` = 0 and executes `ERET` reaches any instruction with no landing-pad check. `ERET` cannot be forbidden outside the gate as it stands. So on ARM64 the entry sequence is protected against a wild entry by BTI for a faulty kernel, and not for an adversarial one. The same holds on RISC-V for `SRET` with `sepc`. FEAT_GCS adds `PSTATE.EXLOCK` (seen in the `AArch64_TakeException` pseudo-code [R]); whether it closes this is UNVERIFIED (read Arm ARM D11, the exception lock). Decision 2 of part D.

#### B.3.1 Mechanism 1 (a `TTBR1` context of the gate): memory and tags

- **The ASID.** "If the value is 0, then the TTBR0_ELx.ASID is used. If the value is 1, then the TTBR1_ELx.ASID is used" (Arm ARM D8.16.3.1, RSCBSR [R]). Version 1 switched `TTBR1_EL1` with `TCR_EL1.A1` = 0, so the ASID did not change and the gate's writable entries stayed usable after the exit (document 3, break 11A). **Version 2 sets `TCR_ELx.A1` = 1 for the life of the node** (choice): the ASID of an aspace is written into `TTBR1` at each switch of address space, with the kernel's tables; the gate's `TTBR1` value carries the gate's tables and `GATE_ASID`. Linux uses `A1` = 1 for the same reason (secondary evidence, from memory). Rejected: switching `TTBR0` too (two more register writes per call); a `TLBI` at every close (a broadcast or a local flush per call).
- **`GATE_ASID`** is the highest ASID of the width read at start-up, bound to no root: the tag table of G7 loses one tag on ARM64 too.
- **Nothing that differs is global.** "If the value is 1, the translation is non-global and the TLB entry applies to only the current ASID value" (D8.16.3.1, RQGKGF [R]): every block and page descriptor that differs between the gate's tables and the kernel's has nG = 1, the kernel's text and data included.
- **With FEAT_ASID2** ("OPTIONAL from Armv9.4 ... mandatory from Armv9.5", chapter A2 [R]) the design is unchanged; `TCR2_ELx.A2` may stay 0.
- **A change of the gate's own view** uses the view epoch of B.1.3 and a local `TLBI ASIDE1` for `GATE_ASID`.

| Page | Address | Under the kernel's `TTBR1` | Under this core's gate `TTBR1` | nG | Class |
|---|---|---|---|---|---|
| Gate text, the SDEI entry, the read-only `ROOTS` table | Same on all cores | Read, execute | The same page | 0 or 1 | *global read-only* |
| **The vector page** (`VBAR_ELx`) | Same | The kernel's own vectors | A gate page whose every vector is the fatal path | 1 | kernel image; *gate* |
| Gate stack | `GATE_STACK`, same on all cores | Not present | Read, write | 1 | *gate* |
| Pending word of the core | Per core, one page per node | Read, write | The same page | 1 | kept, kernel-writable |
| Kernel text, data and stacks | As today | As today | Not present | 1 | as today |
| Tables, living part, gate part, GIC and SMMU registers | Gate's addresses | Read only or not present | Read, write | 1 | as today |

- **The vector page is a twin (choice).** Under the kernel's context the vectors are the kernel's own, with no gate stub and no cost. Under the gate's context every vector is fatal, so it needs no scratch register and no test. Rejected: one stub that reads `TTBR1` (kernel.md's "Each loads the kernel's `TTBR1_EL1` ... as its first act"), which needs a register before it can test, and so a reserved system register or a push; document 3's break 11B is that push.

#### B.3.2 Mechanism 1: the entry and exit

Columns: **Sync** synchronous exception of this instruction; **IRQ/FIQ**; **SErr** SError; **SDEI** event 0. At EL2 with VHE the same instructions name the EL2 registers (`TTBR1_EL2`, `VBAR_EL2`, `SP_EL2`): accesses "redirect" under `E2H` = 1 [3]. `TPIDR_EL1` does not redirect [3]; the sequence does not use it.

| Row | Instruction | Holds after it | Sync | IRQ/FIQ | SErr | SDEI |
|---|---|---|---|---|---|---|
| A0 | `bti c` (a `NOP` without BTI) | Nothing trusted | no | K | K | K′ |
| A1 | `mrs x9, daif` | x9 = caller's masks | no | K | K | K′ |
| A2 | `msr daifset, #0xf` | D, A, I, F masked | no | pended | pended | K′ |
| A3 | `msr allint, #1`, **only where FEAT_NMI is implemented** (a `NOP` otherwise) | Superpriority masked | no | pended | pended | K′ |
| A4 | `msr spsel, #1` | SP is `SP_ELx` | no | pended | pended | K′ |
| A5 | `mrs x10, mpidr_el1` | x10 = this core's affinity | no | pended | pended | K′ |
| A6 | `ubfx x10, x10, #s, #w` (constants of the machine, set at start-up) | x10 = core index | no | pended | pended | K′ |
| A7 | `adrp x12, ROOTS` | | no | pended | pended | K′ |
| A8 | `ldr x11, [x12, x10, lsl #3]` | x11 = this core's gate `TTBR1` value | no (present by construction) | pended | pended | K′ |
| A9 | `mrs x13, ttbr1_el1` | x13 = caller's tables and ASID (trusted) | no | pended | pended | K′ |
| A10 | `msr ttbr1_el1, x11` | Written; in effect only after A11 | no | pended | pended | by `TTBR1`'s value |
| A11 | `isb` | **Open** | no | pended | pended | D or fence |
| A12 | `mov x14, sp` | x14 = caller's SP (a value) | no | pended | pended | D or fence |
| A13 | `adrp x15, GATE_STACK_TOP` | | no | pended | pended | D or fence |
| A14 | `mov sp, x15` | SP on the gate stack | no | pended | pended | D or fence |
| A15 | `stp x13, x14, [sp, #-32]!` | Saved privately | F | pended | pended | D or fence |
| A16 | `stp x9, x30, [sp, #16]` | Saved privately | F | pended | pended | D or fence |
| — | body | G12 (2) after every store | F | pended | pended | D or fence |
| Z0 | `ldp x9, x30, [sp, #16]` | | F | pended | pended | D or fence |
| Z1 | `ldp x13, x14, [sp]` | | F | pended | pended | D or fence |
| Z2 | `mov sp, x14` | Caller's SP, **before** the close | no | pended | pended | D or fence |
| Z3 | `msr ttbr1_el1, x13` | Written | no | pended | pended | by `TTBR1`'s value |
| Z4 | `isb` | **Closed** | no | pended | pended | K′ |
| Z5 | `msr daif, x9` | Caller's masks; pended interrupts are taken here, by the kernel's vectors | no | K | K | K′ |
| Z6 | `ret` | | K (the caller's) | K | K | K′ |

- **K′ (SDEI while not open).** Firmware enters the registered entry, which is in gate text, with "X2 is set to the interrupted PC" and "PSTATE is modified as follows: DAIF = 0b1111, EL = ELC, nRW = 0, SP = 1" (SDEI §5.2.1 [R]). The entry reads `TTBR1`; when it is not the gate's, it branches to the kernel's SDEI handler. On completion firmware restores the interrupted state: "The dispatcher must save and later restore the client Execution state that may be modified/corrupted by the handler" (§5.2.1.2 [R]), and "The handler must preserve all registers except for X0…X17" (§5.2.1 [R]). So a prologue resumed after an SDEI event has its x0 to x17 and its PSTATE from firmware. The prologue keeps every trusted value in x9 to x15, and so needs no restart. The completion calls are firmware calls, made by the gate (the allow-list); `SDEI_EVENT_COMPLETE_AND_RESUME` is accepted only with the park routine's address.
- **D or fence (SDEI while open).** The entry has x0 to x17 free and does not touch SP. It reads the core word: with the fence mark, it closes the window and enters the fence handler, which never resumes; without it (a development stop), it marks the pending word and completes the event.
- **SP is moved after the open and restored before the close.** Document 3's break 11C had the kernel's SDEI handler running on a stack pointer that was not mapped.
- **`msr spsel, #1` at A4.** An exception sets "PSTATE.SP = '1'" (`AArch64_TakeException` [R]); without A4 a caller with `SPSel` = 0 would leave `SP_ELx` its own while A14 wrote `SP_EL0` (break 11B).
- **`msr allint`.** "accesses to ALLINT are UNDEFINED" without FEAT_NMI (C5.2.1 [R]), which is "OPTIONAL from Armv8.7" (chapter A2 [R]). The row is patched at start-up from `ID_AA64PFR1_EL1` (break 11D).
- **A10 to A11.** Between the write and the `isb` the translation in use is either one. The two instructions lie in gate text, mapped the same in both. That a read of `TTBR1` there returns the written value is UNVERIFIED (read Arm ARM, "Synchronization requirements for AArch64 System registers"); the SDEI entry's test depends on it.
- **A synchronous exception while open** enters the gate-side vector page: fatal, with no register to save.
- **SError** is masked by A2 and pended; where the platform routes it to EL3 it is firmware's.
- **The deferred development stop** is delivered by the kernel when it checks its pending word (at the end of each kernel event), not by a jump at the exit: the count is a counter the stub raises and the kernel compares with its own, so no update is lost and the exit needs no atomic clear.

#### B.3.3 Mechanisms 1′, 2 and 3

**OPEN-3.** Version 2 gives no tables for them. What differs, and what must be read first:

| Mechanism | Opening instruction | What breaks the mechanism-1 design | To read |
|---|---|---|---|
| 1′, widening `TCR_EL1.T1SZ` | `msr tcr_el1` | No ASID changes. Whether a TLB entry made while the range was wide can be used after it is narrowed | Arm ARM D8, the rules on changing `TCR_ELx` fields and on TLB entries outside the configured range: UNVERIFIED |
| 2, permission overlays | `msr por_el1` | The translation does not change, so the vector page cannot be a twin; the stub must test `POR_EL1` and needs a scratch register | Arm ARM D8, how an overlay permission is cached: UNVERIFIED |
| 3, GCS pages written by `GCSSTR` | none | `GCSSTR` is a store; no compare-and-swap is defined on a GCS page, as on x86-64 (B.2, fact 1) | Arm ARM D11.10, Guarded Control Stack data accesses: UNVERIFIED |

No core with mechanism 2 or 3 was found (kernel.md), so the order of work is: mechanism 1 under QEMU, then 1′ as a measured variant.

### B.4 RISC-V, mechanism 1 (a `satp` root of the gate)

- **The ASID and the TLB.** "The number of ASID bits is UNSPECIFIED and may be zero" and "writing satp does not imply any ordering constraints between page-table updates and subsequent address translations, nor does it imply any invalidation of address-translation caches" (RISC-V priv §10.1.11 [R]). So: with ASIDLEN > 0, `GATE_ASID` is the highest ASID, bound to no root (G7 loses one tag); with ASIDLEN = 0, an `sfence.vma x0, x0` follows the opening and the closing `csrw satp` ("If the implementation does not provide ASIDs, or software chooses to always use ASID 0, then after every satp write, software should execute SFENCE.VMA with rs1=x0", §10.2.1 [R]).
- **Nothing that differs is global.** "The G bit designates a global mapping. Global mappings are those that exist in all address spaces" (§10.3.1 [R]).
- **Finding the hart.** Supervisor mode has no trusted hart number. `stvec` is written by the gate only, with one value per hart; the page after it is a read-only per-hart page that holds the hart's gate `satp` value and its gate stack top (choice, from version 1). The `stvec` page is a twin as on ARM64: the kernel's trap entry under the kernel's root, a fatal stub under the gate's.

| Row | Instruction | Holds after it | Sync | S-interrupt | M-trap |
|---|---|---|---|---|---|
| R0 | landing pad (where Zicfilp exists) | Nothing trusted | no | K | FW |
| R1 | `li t5, SIE+SUM+MXR` | | no | K | FW |
| R2 | `csrrc t0, sstatus, t5` | SIE, SUM, MXR clear; t0 = caller's `sstatus` | no | no (SIE = 0) | FW |
| R3 | `csrr t1, stvec` | t1 = this hart's trap page | no | no | FW |
| R4 | `ld t2, GSATP(t1)` | t2 = this hart's gate `satp` | no (present by construction) | no | FW |
| R5 | `csrr t3, satp` | t3 = caller's root and ASID (trusted) | no | no | FW |
| R6 | `csrw satp, t2` | **Open** | no | no | FW |
| R7 | `sfence.vma x0, x0`, only when ASIDLEN = 0 | No entry of the kernel's view remains | no | no | FW |
| R8 | `mv t4, sp` | t4 = caller's sp (a value) | no | no | FW |
| R9 | `ld sp, GSTACK(t1)` | sp on the gate stack | F | no | FW |
| R10 | `sd` of t0, t3, t4, ra on the gate stack (four rows) | Saved privately | F | no | FW |
| — | body | | F | no | FW |
| S0 | `ld` of t0, t3, t4, ra (four rows) | | F | no | FW |
| S1 | `mv sp, t4` | Caller's sp, before the close | no | no | FW |
| S2 | `csrw satp, t3` | **Closed** | no | no | FW |
| S3 | `sfence.vma x0, x0`, only when ASIDLEN = 0 | No entry of the gate's view remains | no | no | FW |
| S4 | `andi t0, t0, SIE` | | no | no | FW |
| S5 | `csrs sstatus, t0` | Caller's SIE; a pending interrupt is taken here | no | K | FW |
| S6 | `ret` | | K | K | FW |

- **Trap entry saves nothing in memory**: "When a trap is taken into supervisor mode, SPIE is set to SIE, and SIE is set to 0" (§10.1.1 [R]); `sepc`, `scause` and `stval` are registers.
- **That no supervisor interrupt is taken in supervisor mode with SIE = 0** is the privileged specification's rule on global interrupt enables: UNVERIFIED wording (read §3.1.6.1 and §10.1.1).
- **sp is moved after the open and back before the close**, as on ARM64 (document 3).
- **Machine-mode traps** run firmware and return by `mret` or never (`fence_hart`); this holds only if firmware never redirects a trap into supervisor code while the gate's root is loaded, which is firmware's promise.
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

The #MC stub is gate text and decides before any other code runs. It scans this core's banks (`IA32_MCG_CAP[7:0]`) and takes the first row that applies.

| # | Condition | Verdict | Whose error |
|---|---|---|---|
| 1 | MCIP = 0 | F | This node's: only code at CPL 0 can raise vector 18 (DPL 0) |
| 2 | `MCG_SER_P` = 0 and some bank has VAL and UC | **Stop the machine** | Nobody's to recover: the manual calls it fatal |
| 3 | Some bank has VAL, UC, EN and PCC | **Stop the machine** (choice, below) | A processor whose state may be corrupt |
| 4 | Some bank has VAL, UC, EN, S, AR and OVER | **Stop the machine** | The manual's rule |
| 5 | SRAR (VAL, UC, EN, S, AR, no PCC, no OVER) and this core is affected (`LMCE_S`, or EIPV, or RIPV = 0), interrupted in gate text or in the window | F if `ADDRV` and the address lies in memory this node owns (a taken chunk, its floor, its gate part); otherwise **stop the machine** (the data was shared: the living part, the kept image, gate text) | This node's, or the machine's |
| 6 | The same, interrupted in the node's kernel (CPL 0, outside gate text) | F (choice: Linux panics on such an error in kernel context unless a fix-up exists, from memory) | This node's |
| 7 | The same, interrupted at CPL 3 | Clear MCIP; the kernel's handler, which faults the thread (hardware error, code 7) and does not resume it | This node's thread |
| 8 | RIPV = 0 and no bank explains it | As rows 5 to 7 by the interrupted context, with no address: F in gate text or kernel, the kernel's handler at CPL 3 | This node's |
| 9 | SRAO (S, no AR) or an uncorrected error with EN = 0, and none of the above | **Continue**: clear MCIP, mark the pending word, return (R, D, or to the interrupted instruction) | The node that owns the address; each kernel reads the banks (`RDMSR` is allowed) and judges by the address |
| 10 | Nothing valid and uncorrected in this core's banks, RIPV = 1 | **Continue**, as row 9 | Another core's (deferred) |

- **Row 3 is a choice.** The alternative charges the node of the core whose private bank reports PCC and lets the machine run. Its cost is trusting a processor that reports its own state corrupt to have respected CR3 and the gate; "hardware that computes wrongly" is already outside the contract's promise.
- **No verdict of F or "stop" rests on a shared bank alone** except rows 2 to 4, which every core that sees the bank reaches together. Rows 5 to 8 need this core to be the affected one, which the manual gives per logical processor. This is the answer to document 3's break 10B: a healthy node is never declared fatal for an error another node's core consumed.
- **MCIP is cleared in gate text on every path that does not stop the machine**, before any `IRETQ` or jump (break 10C). The kernel never runs with MCIP set.
- **Clearing the banks.** The kernel that the error belongs to asks its gate (`mc_collect`, a windowed call): the gate copies and clears the banks this core owns by the CMCI protocol.
- **Start-up** sets `LMCE_EN` where firmware allows, sets CR4.MCE on every core before any node runs, and claims bank ownership.
- **On the reference desktop** `MCG_SER_P` is probably 0 (a client part; UNVERIFIED on the machine, trial T5), so row 2 makes every uncorrected machine check a stop of the machine with a stop record. That is what a monolithic system does on the same processor.
- **OPEN-4. No synchronisation across nodes.** Each core decides alone. Three gaps follow, with options in part D: a kernel that never calls `mc_collect` leaves VAL set, so a later SRAR finds OVER and row 4 stops the machine; the owner may clear a shared bank while another core still reads it; and the manual's "unexpected condition" (no core finds any error) is not detected.
- **OPEN-5. Row 7 runs the kernel on IST3 with the token busy.** A second machine check before that kernel returns to user mode faults at delivery, which is F.
- **A core with CR4.MCE clear.** "If the machine-check mechanism is not enabled (the MCE flag in control register CR4 is clear), a machine-check exception causes the processor to enter the shutdown state" (SDM vol. 3A §7.15, interrupt 18 [R]). A core in the park stub after INIT runs with paging off; whether CR4 is cleared by INIT (Table 11-1) is UNVERIFIED, and what a core in wait-for-SIPI does at a broadcast machine check is UNVERIFIED. If both go the wrong way, a fenced core turns the next broadcast machine check into a shutdown of that core. Trial T9; residue 13.

#### B.5.3 What the kernel's handler outside the gate must do

None is specified today. From the rule above:

1. It is entered only from row 7 (a thread to fault) or through the pending word (rows 9 and 10).
2. It reads the banks, decides by `IA32_MCi_ADDR` whether the address is its node's, writes the hardware error record (code 7), and for memory it owns stops using the page.
3. It calls `mc_collect`. It never writes an MSR, and never returns to the faulted thread in row 7.
4. It tolerates being entered twice for one error (two cores of the node saw the same bank).

#### B.5.4 ARM64 and RISC-V

| Architecture | In a gate call | Stops the machine |
|---|---|---|
| ARM64 | SError is masked and pended (taken by the kernel's vector after Z5); a synchronous external abort in the window is fatal to the node | Errors firmware at EL3 handles (RAS routed to EL3): firmware's |
| RISC-V | An access fault in the window is fatal to the node. The privileged specification defines no machine-check architecture; a hardware-error NMI is machine mode's (Smrnmi, chapter 8, not read in detail: UNVERIFIED) | Firmware's |

### B.6 Costs

**Documented by others, as cited in kernel.md and not re-opened by me:** a CR3 write "about 200 cycles" (Ren et al., SOSP 2019); SKEE's round trip 284 cycles on an Exynos 7420; Hilps 210 to 424 cycles. **Everything else below is my estimate. Nothing is measured on the project's machines.**

| | x86-64 mechanism 2 | ARM64 mechanism 1 | RISC-V mechanism 1 |
|---|---|---|---|
| Windowed call, fixed part | Two CR3 writes (about 400 by the documented figure) plus `RDPID` and about 20 instructions: 420 to 550 cycles (estimate) | Two `TTBR1` writes with `isb`: near SKEE's 284 (estimate from the documented figure) | Two `satp` writes; no figure found. With ASIDLEN = 0, two full flushes more |
| Per entry written | One store, or one `LOCK CMPXCHG` for a living-part word (about 20 cycles, estimate) | The same | The same |
| Switch of address space | Two CR3 writes instead of one: **+1 CR3 write**, about +200 to +250 (estimate). Version 1's short entry was wrong; closing to the old root first would have cost three | Two `TTBR1` writes and the `TTBR0` write: +2 register writes with `isb` | Two `satp` writes instead of one |
| Per interrupt taken | The stub: a CR3 read, `RDSSPQ`, range compares: 10 to 30 cycles (estimate; the cost of a CR3 read is trial T1). End of interrupt and timer deadline: a short entry, +5 to 10 over the bare `WRMSR` | Nothing at the vectors (the twin page); the acknowledgement is a gate call already (D-151) | Nothing at `stvec` |
| Port access | A windowed call: about 450 to 600 (estimate) | — | — |
| Memory per core | Four interrupt stacks on two sides (32 KB at a page each), four shadow stacks and the kernel's (20 KB), the gate stack (16 KB), a root and three private tables (16 KB): **about 84 KB** (estimate) | Gate stack (16 KB), root and private tables (16 KB): about 32 KB | The same, plus the per-hart trap page pair (8 KB) |
| Kernel mappings not global | Kernel TLB entries are per tag: more misses in the kernel after a switch of address space. Not estimated; trial T3 | The same | The same |

---

## C. Break → where version 2 closes it

Every break and every Job 1 item of document 3, one row each.

| # | Item of document 3 | Closed by | Status |
|---|---|---|---|
| N1 | IBT state lost across an IDT event | V3 with the table of B.1.7: an event that lands on a wild branch target in gate text is restarted (prologue), fatal (body) or harmless (rows with nothing trusted). The kernel's `IRETQ` can reach only P0 and P1 | Closed for x86-64 mechanism 2, timed and asynchronous; to be re-checked by another model |
| N2 | Stub stacks open to DMA | B.1.2: kept memory or class *gate*; G3 (2) and (3) | Closed |
| N3 | `WRSS` to MMIO and to the living part | B.2 (mechanism 1 is not specified); B.1.5 (plain `LOCK CMPXCHG` and plain stores under mechanism 2). Document 3's correction (`seal_parked`, not `parked`) is taken | Closed by not using mechanism 1; decision 1 |
| J2-a | X1/X2 rewind holds | Not needed any more: the pending test moved after the close (E1) | — |
| 1A | X3/X4 marked K: a completed call re-run, kernel handler with the gate's stack pointer; IF never restored | V8; rows E0 to E3 (D, re-test only); V10 states IF = 0 on return | Closed |
| 1B | Mechanism 1 pending word | Mechanism 1 is not specified | Not applicable |
| J2-b | Livelock on restart ranges | Not bounded, by design: it costs the faulty node its own time. A healthy kernel calls with IF = 0 (V10), so a device storm cannot hold P0 | Not closed for the faulty node (accepted); closed for a healthy one |
| J2-c | `WRSSQ` of SSP + 8 then `IRETQ`; token alignment | B.1.2 (token placement, with the pseudo-code quoted); trial T2 | Closed on paper |
| 2A | `#DF` handed to the kernel; a triple fault | B.1.7: vector 8 always F; B.1.9 | Closed for `INT 8`. A racing node of several cores: OPEN-2 |
| R4 | "From CPL 0" by SSP on several cores | B.1.7, the two tests | Closed |
| J2-d | `RDPID`, `ROOTS`, per-core IST addresses | B.1.2: IST addresses per core, the gate root maps its own core's only | Closed |
| 4A | The gate's PCID in G7's table; `INVPCID` at a change of the gate root | B.1.3: the tag reserved; the view epoch | Closed |
| 4B | The global-bit rule incomplete | V9 and B.1.2, column Global | Closed |
| J2-e | W0 and W1 hold | Kept (B.1.4), with the reason written as a row to model first | — |
| 6A | NMI replay by `INT 2` | B.1.6, the delivery table: a jump, a function, no token busy | Closed |
| J2-f | Tail `JMP` under CET holds | Kept (E2) | — |
| 7A | `load_root` as a short entry | B.1.10: windowed; closes to the new root | Closed |
| 7B | `RET` inside a restart range | V8; B.1.10: the range ends before the acting instruction | Closed |
| 7C | Port access races `memory_give` | B.1.10: windowed under the gate lock | Closed |
| 8 | Vectors 3 and 4 with DPL 0 | V2: vector 3 has DPL 3 | Closed |
| 8A | `IA32_LSTAR` and `SETSSBSY` | B.1.8: three rows in gate text, none restarted; `SYSCALL` and `SYSRET` to be forbidden outside gate text | Closed |
| 9A | A stub that spills a trusted value on a stack another core writes | V7; and V3 removes the kernel from between a stub's read and its use | Closed |
| 10A | `MCG_SER_P`, EN, OVER | B.5.2, rows 2, 4, 9 | Closed |
| 10B | Shared banks park healthy nodes; no rendezvous | B.5.2: F needs this core to be the affected one. The rendezvous: OPEN-4 | Partly closed |
| 10C | A kernel that leaves MCIP set | B.5.2: MCIP cleared in gate text on every path | Closed |
| 11A | `TTBR1` has no ASID of its own | B.3.1: `A1` = 1, `GATE_ASID`, nG | Closed |
| 11B | `PSTATE.SP` = 0; a push in the vector stub | Row A4; the twin vector page, which pushes nothing | Closed |
| 11C | SP moved outside the window; SDEI on an unmapped stack | Rows A12 to A14 and Z2 | Closed |
| 11D | `MSR ALLINT` undefined before FEAT_NMI | Row A3, patched | Closed |
| VHE | `TPIDR_EL1` not redirected; `SP_EL2`; the `_EL12` names | B.3.2 does not use `TPIDR`; A4 covers `SP_EL2`; the `_EL12` encodings go on the scan's list | Closed, with one contract change |
| BTI | A wild jump onto the `MSR` without BTI | Not closed, and N4 shows that BTI alone does not close it against an adversarial kernel | **Not closed**: decision 2 |
| 12A | `satp` without a flush; no ASID reserved; ASIDLEN 0; the G bit | B.4, first two bullets; rows R7 and S3 | Closed |
| 12-b | sp moved before the `satp` write | Rows R8, R9 and S1 | Closed |
| J3-1 | Mechanism 1 not viable even on one core | B.2, as facts for the owners | Presented: decision 1 |
| J3-2 | The cost of `load_root` and of a port access | B.6: +1 CR3 write per switch, stated | Stated, not removed |
| J3-3 | Five residue items added | Part A, rows 7 to 11 | Listed |

**Breaks of version 2 that I found while writing it and could not close:** OPEN-1 (a machine check inside the NMI stub), OPEN-2 (the park loop and a raced `#DF` frame), OPEN-4 (no synchronisation of broadcast machine checks), OPEN-5 (a second machine check during row 7), N4 (exception return as a jump on ARM64 and RISC-V).

---

## D. Open rows, trials and decisions

### D.1 Open rows

1. **OPEN-1, a machine check inside the NMI stub.** (a) Accept it: it needs a "continue" machine check and two NMIs within some tens of nanoseconds; the node is lost, nothing else. (b) Have the `#GP` stub recognise "delivery of an NMI failed inside the NMI stub", mark the NMI and return to the stub's redo label; this needs the state of NMI blocking after a failed delivery, which the SDM does not give (UNVERIFIED). (c) FRED, whose return instruction controls the unblocking; absent on the reference processor. I would take (a) and state it.
2. **OPEN-2, the park loop.** (a) The loop's SSP is the top of the core's kernel shadow stack, whose token is left as it is, and the loop makes no `CALL`; a core that reaches F from CPL 3 first executes three `CALL`s to make room for the frame it writes. (b) Reach the park loop by a jump, with the IST token left busy, and accept that a later event of that vector faults at delivery into the same path. (c) For the raced `#DF` frame: nothing closes it under shared kernel roots; a kernel root per core would, at the cost D-128's shared aspace roots avoid. I would take (a), leave the race as residue 3, and run trial T6.
3. **OPEN-3, ARM64 mechanisms 1′, 2 and 3**: tables not written; three readings named in B.3.3.
4. **OPEN-4, broadcast machine checks.** (a) No rendezvous, as written; the entry stub of a core that joins a node logs and clears stale banks; accept the three gaps. (b) A rendezvous word in the living part, which requires the #MC stub to load the gate's root from any context, and so to reach its own frame through the gate's window on the kernel-side stack. (c) Require LMCE and make every broadcast machine check a stop of the machine. On the reference desktop (a) and (c) probably coincide (row 2).
5. **OPEN-5, a second machine check during row 7.** (a) Accept: the node is lost. (b) Move the kernel off IST3 inside gate text (`CLRSSBSY` on IST3's token, `SETSSBSY` on the kernel's) before it runs.
6. **N4.** See decision 2.

### D.2 Trials on the reference machine (measurements and experiments)

1. **T1.** A CR3 write with PCID and bit 63, and a CR3 read, in cycles, on both kinds of core.
2. **T2.** A stub rewrites the slot at SSP + 8 by `WRSSQ` and the frame's RIP, then `IRETQ`: no `#CP`, the token free afterwards.
3. **T3.** Kernel text and data without the global bit: TLB misses in the kernel after a switch of address space, against the same with the bit.
4. **T4.** `RDPID` on both kinds of core; its cost.
5. **T5.** `IA32_MCG_CAP`: `MCG_SER_P`, `MCG_LMCE_P`, the bank count; `IA32_FEATURE_CONTROL` bits 0 and 20 as firmware leaves them; which banks two cores share (the CMCI protocol).
6. **T6.** One core driven into shutdown by a triple fault while the others run: what the platform does.
7. **T7.** An NMI injected at every row of B.1.4, B.1.6, B.1.8 and B.1.10 (single-stepped under a hypervisor first, then on the machine), with the events of the tables checked.
8. **T8.** N1: TF set, an indirect jump to P7, and the result (expected: restart at P0, no `#CP` lost).
9. **T9.** A core in wait-for-SIPI, and a core in the park stub, at an injected machine check (`MCG_STATUS` and the bank written by a test `WRMSR`, or an error-injection facility if the platform has one).
10. **T10.** Return to user mode by `IRETQ` against a `CLRSSBSY; SYSRETQ` trampoline, in cycles.
11. **T11.** An NMI arriving while NMIs are blocked: is one held and delivered at the `IRETQ`? (The SDM gives this only for SMM: "Only one NMI request will be latched during the SMI handler", §34.8 [R].)
12. **T12.** The ARM64 and RISC-V tables under QEMU, with an SDEI event and an interrupt injected at every row; the read of `TTBR1` between A10 and A11.

### D.3 Decisions for the owners

1. **The order of x86-64 mechanisms in D-120.** The facts are B.2. The options: (a) mechanism 2 becomes the mechanism, and mechanism 1 leaves the plan; (b) mechanism 1 is still prototyped, for page-table entries on a node of one core, with mechanism 2 beside it for everything else; (c) the order stays and the compare-and-swap rule of the living part changes. My recommendation is (a): (b) is two mechanisms and two proofs for the cost of one CR3 pair on calls that are not on any hot path except the switch of address space, and (c) reopens the whole of Gate words.
2. **What is promised on ARM64 and RISC-V.** (a) "Held against a faulty kernel, not an adversarial one", written into the contract beside the flag for a machine without control-flow protection; (b) exception returns move into gate text behind a check of the return address, which costs a gate entry on every return to user mode and a restart range for SDEI; (c) wait for FEAT_GCS's exception lock on ARM64. My recommendation is (a) now, and (b) designed only if an ARM64 product is decided.
3. **The machine-check policy** (B.5.2): that every uncorrected error stops the machine on a processor without `MCG_SER_P`; that PCC stops the machine; that an action-required error in kernel context is fatal to the node. Each has a costlier alternative written beside it.
4. **Which residue items the contract names** (part A, last column).

### D.4 Changes to the contract this draft implies, if it is taken

These are details of the kind the assistant settles and the owners review; they are listed so that none is taken by accident.

- G7: one tag reserved for the gate on each architecture (x86-64: 4,095 usable PCIDs).
- G2: the class *gate* names the gate stack and the gate-side interrupt stacks; the kernel-side interrupt stacks are kept memory.
- G11, x86-64: forbid outside gate text `SYSCALL`, `SYSRET`, `SYSENTER`, `SYSEXIT`, `INT n`, `INT1`, `INT3`, `INTO`, and name `RSTORSSP`, `SAVEPREVSSP` and `INCSSP` (the last may stay allowed: it only pops). ARM64: the `_EL12` encodings; `MSR SPSel` stays allowed. Check that no translation that differs between the views is global.
- kernel.md, rule (1) to (6) of "An event taken inside a gate call": replaced by V1 to V11; the sentence "saves the interrupted registers in a gate area, and restores them from there" removed on the three architectures; the ARM64 and RISC-V paragraphs lose "Each loads the kernel's `TTBR1_EL1` ... as its first act".
- The development image's allow-range for debug registers (B.1.5).
- A requirement on the kernel's NMI work (B.1.6) and on its machine-check handler (B.5.3); the kernel checks its pending word at the end of each event.
- `NMI_GRACE_NS` > *H* stays, with *H* now covering P0 to E3.

---

## E. What a model checker should check

**State, per core.**
- `step`: outside; a row of an entry (P0 to P7, W0 to W2, body, X0 to X3, E0 to E3); a row of a short entry; L0 to L2; a stub with its position (before the redo label, in the critical range, after it); the park loop; a kernel handler.
- `flags`: IF, TF, DF, NT.
- `root`: kernel (with a tag) or gate. `rsp`: caller's, gate stack, IST1 to IST4 (with the side the address maps to under `root`).
- `ssp`: which shadow stack, its depth, the words on it (CS, LIP, old SSP).
- `tokens`: busy or free for IST1 to IST4 and the kernel's. `nmi_blocked`. `mcip`.
- `tracker`: idle or waiting for `ENDBR64`.
- `pending`: the bits of the core's word; `completed`: how many times the call's body has run to its end.
- Registers that carry trust: RAX, RCX, R11, RDX, each "as computed" or "adversary's".
- Per node: the gate lock, the view epoch.

**The adversary's moves.**
1. Any event of the tables at any row boundary: maskable interrupt, NMI, #MC (local or broadcast, any bank contents), #DB (TF or breakpoint), a fault of the instruction, SMI, INIT.
2. Any register, flag and stack pointer at entry; an entry by a jump to any address of gate text.
3. A second core of the node writing any kernel-writable page at any time: the kernel-side interrupt stacks (so the RFLAGS, RSP and SS of any frame not on a gate-side stack), the pending words, the beacon.
4. A second core of the node calling any gate entry at any time.
5. A device writing any page the node may map for DMA (the classes of G3 (2)).
6. Any kernel handler: when control is given to the kernel, it may change every register and flag and return, by `IRETQ`, to any address the shadow stack holds, or never return.

**The properties.**
1. No kernel instruction executes while `root` is the gate's, nor between P7 and X3 of a call.
2. Every store made with `root` = gate is made by gate text; a frame the processor pushes with `root` = gate lands on a gate-side stack or the gate stack (this is the P7-to-W0 row).
3. At P7, RAX is "as computed"; at X3, RCX is; at every `WRMSR` of a short entry, ECX, EAX and EDX are.
4. `completed` goes from 0 to 1 at most once per call, or the node is fatal.
5. Every NMI taken between P0 and E3 sets its bit, and the bit is set at some later E1 of that call unless a core of the node cleared the word.
6. `nmi_blocked` is never cleared while a stub is between its first instruction and its `IRETQ`. **Known violation to report, not to hide: OPEN-1.**
7. No token is busy when control reaches kernel code outside a handler entered through that token.
8. `mcip` is clear whenever a kernel instruction executes.
9. No delivery faults with IST4's token busy (a triple fault), except under move 3 on a frame of vector 8 (OPEN-2); the checker should report the shortest such trace.
10. On ARM64 and RISC-V: properties 1, 2 and 4 with the rows of B.3.2 and B.4; SP is the gate stack's only while the window is open.

**Order of work:** the x86-64 entry and exit with moves 1, 2 and 6 on one core; then move 3; then the short entries and L0 to L2; then the machine-check rule as a table of bank contents; then ARM64 and RISC-V.

---

## Sources

- Intel SDM 325462-093US. Read by me this pass: vol. 2A `INT n` and `IRET` pseudo-code (shadow stacks); vol. 2B `MOV` to control registers, `SYSCALL`, `PUSH` (the shutdown note); vol. 2D `WRSSD/WRSSQ` (exceptions); vol. 3A §5.10.1, §5.10.2.3, §5.10.2.4, §5.10.4.1, §7.7.2, §7.8.1 (note), §7.8.3, §7.12.1.1, §7.12.1.3, §7.14.5, §7.15 (interrupt 18); vol. 3B §18.3.1.1, §18.3.1.2, §18.3.1.4, §18.3.1.5, §18.3.2.2, §18.5.2.1, §18.6.2, §18.6.3, §18.10.3.2, §18.10.4, §18.11.4.1, §20.2.3; vol. 3C §34.8. Not read by me, taken from document 3: vol. 1 §18.3.3.2 (the tracker), vol. 3A §5.6, §7.9 Table 7-2, Table 11-1, `RDPID`, `SETSSBSY`.
- Arm DDI 0487 M.d. Read by me: chapter A2 (feature lines), D8.16.3.1 (rules RSCBSR, RPYWKY, RXPSGZ, RQGKGF), the `AArch64_TakeException` pseudo-code (J1.2), D1.4.2 (BTYPE at exception entry), C5.2.1 (`ALLINT`). Taken from document 3: D24.2 (VHE redirection, `TPIDR_EL1`).
- Arm DEN 0054C, §5.2.1, §5.2.1.1, §5.2.1.2: read by me.
- RISC-V privileged 20240411, §10.1.1, §10.1.11, §10.2.1, §10.3.1: read by me. §10.1.2: from document 3.
- Secondary evidence (Linux's paranoid entry and its `A1` = 1, seL4's interrupts-off kernel, Xen's shadow-stack fix-up, Linux's handling of machine checks in kernel context): from memory, none opened this pass.
