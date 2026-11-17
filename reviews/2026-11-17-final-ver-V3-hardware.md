# Verification of V3 Hardware & Memory-Ordering Review (`v3-opus.md`)

Verified on **17 November 2026** against:
- Contract: [`Docs/architecture/kernel-interface.md`](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md) (branch `main`, head `6e7d8c0`)
- Kernel architecture & other docs: [`Docs/architecture/kernel.md`](file:///Users/btw/Documents/repos/Docs/architecture/kernel.md), [`Docs/architecture/gpu.md`](file:///Users/btw/Documents/repos/Docs/architecture/gpu.md), [`Docs/architecture/platform.md`](file:///Users/btw/Documents/repos/Docs/architecture/platform.md)
- Decision log: [`Docs/decisions/README.md`](file:///Users/btw/Documents/repos/Docs/decisions/README.md) (D-001 to D-140)
- Kernel ABI: [`dodos-kernel/abi/src/x86_64.rs`](file:///Users/btw/Documents/repos/dodos-kernel/abi/src/x86_64.rs), [`aarch64.rs`](file:///Users/btw/Documents/repos/dodos-kernel/abi/src/aarch64.rs), [`riscv64.rs`](file:///Users/btw/Documents/repos/dodos-kernel/abi/src/riscv64.rs)

External specifications opened and verified on **17 November 2026**:
- Intel SDM combined volumes, Order `325462-093US` (September 2026): <https://cdrdv2.intel.com/v1/dl/getContent/671200>
- Intel VT-d Architecture Specification, Revision `5.20`, Order `D51397-019` (April 2026): <https://cdrdv2.intel.com/v1/dl/getContent/671081>
- Arm Architecture Reference Manual `DDI 0487 M.d` (29 September 2026): <https://documentation-service.arm.com/static/6abbec2a6db85c5e6614a4a1>
- Arm PSCI `DEN0022F.b` (1.3): <https://documentation-service.arm.com/static/6703a8b8d7e4b739d817e10d>
- Trusted Firmware-A `v2.12.0` (`sdei_private.h`, `sdei_intr_mgmt.c`, `docs/components/sdei.rst`)
- Linux sources (`torvalds/linux`): `processor.h`, `x2apic_phys.c`, `irq-gic-v3.c`, `riscv_mmio.h`, `gettimeofday.h`, `arch_timer.h`, `iommu.h`, `dmar.c`
- RISC-V specifications (`v20260120` unprivileged ISA & AIA / ACLINT / SBI):
  - <https://docs.riscv.org/reference/isa/v20260120/unpriv/a-st-ext.html>
  - <https://docs.riscv.org/reference/isa/v20260120/unpriv/rvwmo.html>
  - `riscv-aclint.adoc` (`riscvarchive/riscv-aclint`), `IPIs.adoc` (`riscv/riscv-aia`), `ext-ipi.adoc` (`riscv-non-isa/riscv-sbi-doc`; `docs.riscv.org/reference/sbi/v3.0/ext-ipi.html` returned HTTP 503)
- **Not opened**: Arm GICv3 `IHI 0069` (redirects to login-gated portal on `support.arm.com`); TI `PC16550D` datasheet (`ti.com` timed out).

---

## Finding 1 — Inter-core interrupt / doorbell store ordering

1. **Quote accuracy (`kernel-interface.md`):**
   - `l. 968`: Exact (`A ring *X* → *Y* is mapped writable only in *X*'s kernel and read-only in *Y*'s (the guarantee of ...); its writes are plain stores, not gate calls, since the receiver checks every message.`). Opus removed Markdown emphasis as stated in its header.
   - `l. 971`: Exact (`(an interrupt of the kernel's own, sent through the gate to one core of the receiver when the ring goes from empty to not empty)`).
   - `l. 1293`: Exact wording (`taken when the ring was not empty and after *Y* sent *X* an interrupt, and the consumer index still reads *c* with now − *t* ≥ \`STUCK_NS\``). Note the contract's `stuck` sentence uses `Y -> X` where `Y` sends to `X`, whereas `l. 968` and Opus's scenario use `X -> Y` where `X` sends to `Y`.
   - `l. 1083` (G10) and `l. 1091`: Exact (`ICC_SGI1R_EL1 and its aliases are written only by the gate`; `a store to the ACLINT's or the target IMSIC's registers`).
   - `l. 677` and `l. 687`: Exact (`it reads its pending set by a read with acquire order`; `its wait for the lock and its work included`).

2. **Replay against full context:**
   Neither [`kernel-interface.md`](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md) nor [`kernel.md`](file:///Users/btw/Documents/repos/Docs/architecture/kernel.md) (`send_ipi`, l. 183) nor [`decisions/README.md`](file:///Users/btw/Documents/repos/Docs/decisions/README.md) requires any barrier between ordinary stores and an inter-core interrupt (whether an x2APIC ICR `WRMSR`, ARM64 `ICC_SGI1R_EL1` write, or RISC-V IMSIC/ACLINT MMIO store).
   Race trace (shared-memory ring `X -> Y` becoming non-empty, assuming `l. 968` plain stores):
   1. Core *a* (node *X*) writes message entries `buf[p .. p+len]` to ring `X -> Y`.
   2. Core *a* writes `producer_index := p + len` (plain store in write buffer / store queue).
   3. Core *a*'s gate sends an interrupt to core *b* (node *Y*): on x86-64 via `WRMSR IA32_X2APIC_ICR`, on ARM64 via `MSR ICC_SGI1R_EL1`, or on RISC-V via MMIO store to *b*'s IMSIC/ACLINT. Because no barrier orders ordinary stores before the interrupt send, the IPI/SGI/MSI reaches the interconnect before the store to `producer_index` (or `buf`) is globally visible.
   4. Core *b* (node *Y*) takes the interrupt and reads `producer_index`, observing old value `p == consumer_index`.
   5. Core *b* concludes the ring is empty and exits the interrupt handler.
   6. Because the ring already holds `producer_index = p + len > consumer_index` once *a*'s store drains, future sends from *X* do not transition the ring "from empty to not empty" (`l. 971`), so no second interrupt is sent.
   7. Sending thread on *X* stays blocked in *waiting for another node* (unaffected by `thread_cancel`, `l. 1003`); after `STUCK_NS` (100 ms), `X` observes `stuck` (`l. 1293`) and accuses healthy `Y` (`l. 1287` violated).
   The same missing barrier affects:
   - the fence mark / park request written before an NMI or SDEI signal (`l. 1306`);
   - an intra-node invalidation/barrier interrupt if the target reads its `pending set` (`l. 677`) *before* acquiring the node lock (`l. 687`), though reading it *after* acquiring the node lock is ordered by the lock.

3. **External sources (verified 17 November 2026):**
   - Intel SDM `325462-093US` §13.12.3 "MSR Access in x2APIC Mode" (p. 3611, <https://cdrdv2.intel.com/v1/dl/getContent/671200>): `"A WRMSR to an APIC register may complete before all preceding stores are globally visible; software can prevent this by inserting a serializing instruction or the sequence MFENCE;LFENCE before the WRMSR."`
   - Linux `arch/x86/include/asm/processor.h` (`l. 792–797`): `"IA32_TSC_DEADLINE and X2APIC MSRs"` / `alternative("mfence; lfence", ...)` and `arch/x86/kernel/apic/x2apic_phys.c` (`l. 48–50`): `weak_wrmsr_fence(); __x2apic_send_IPI_dest(...)`.
   - Linux `drivers/irqchip/irq-gic-v3.c` (`l. 1386–1389`): `"Ensure that stores to Normal memory are visible to the other CPUs before issuing the IPI."` followed by `dsb(ishst)`.
   - Arm GICv3 `IHI 0069`: **Not opened** (login/portal redirect).
   - RISC-V AIA `IPIs.adoc` (`l. 83–85`, `riscv/riscv-aia`): `"Similarly, if hart A stores anything to memory that should be visible at hart B, a FENCE is likely needed before a subsequent store sending an MSI to B's IMSIC."` Also Linux `arch/riscv/include/asm/riscv_mmio.h` (`l. 136`): `#define __io_bw() RISCV_FENCE(w, o)`.

4. **Verdict and severity:**
   - **Verdict:** **real**.
   - **Severity:** **breaks a guarantee** (specifically [`l. 1287`](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1287): a healthy node *Y* can be accused and fenced because an ordered interrupt arrived before the store it announces).

5. **Smallest correction:**
   - **Where & text:** In [`kernel-interface.md`](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1083) (G10) and [`kernel.md`](file:///Users/btw/Documents/repos/Docs/architecture/kernel.md#L183) (`send_ipi`):
     `"Before the gate sends an interrupt to another core, it orders every preceding store before the interrupt: on x86-64 in x2APIC mode MFENCE; LFENCE before the WRMSR to the ICR (Intel SDM §13.12.3); on ARM64 DSB ISHST before writing ICC_SGI1R_EL1 (or its aliases); on RISC-V fence w,o before the store to the IMSIC or ACLINT register. After taking the interrupt, the receiving core reads the announced state (producer index, pending set, park request) with acquire order (for the intra-node pending set, under or after taking the node lock)."`
   - **Cost & when:** Paid only inside gate G10 when sending an inter-core interrupt (already a privileged gate operation); zero cost on normal memory accesses.
   - **New state:** None.

---

## Finding 2 — Ring producer and consumer index ordering

1. **Quote accuracy (`kernel-interface.md`):**
   - `l. 968`: Exact (`its writes are plain stores`; `The producer index is in the ring's header, written by X only; the consumer index of each ring into Y is in Y's node beacon, written by Y only`).
   - `l. 966`: Exact (`A message that fails any of these changes nothing, is consumed, and is traced`).
   - `l. 1003`: Exact (`ends at the answer, or with gone if the target is accused first (R0 (...)). thread_cancel does not end it.`).
   - `l. 972`: Accurate reference to send/request credits.

2. **Replay against full context:**
   `l. 968` explicitly declares ring writes to be `plain stores`, and no sentence in `kernel-interface.md` or `decisions/README.md` specifies release/acquire ordering on `producer_index` or `consumer_index`. Neither the user ring nor the kernel ring has a shared lock across nodes.
   - **Scenario A (producer index observed before message entries, ARM64 / RISC-V):**
     1. Core *a* (node *X*) writes entries `buf[k .. k+9]`.
     2. Core *a* writes `producer_index := p + 10` (plain store).
     3. Without a release barrier between steps 1 and 2, core *b* (node *Y*) reads `producer_index == p + 10` (plain load) before *a*'s writes to `buf[k .. k+9]` are ordered before it, or speculatively reads `buf[k .. k+9]` before loading `producer_index`.
     4. Core *b* reads stale bytes in `buf[k]` (from 64 entries earlier), fails the message check (`l. 966`), consumes and traces the message, and emits no `SendAnswer`.
     5. *X*'s caller waits forever until *Y* dies (`l. 1003`), leaking a send credit (`l. 972`); after `SENDS_PER_PEER` (8) losses, `node_send` to *Y* permanently returns `busy`.
   - **Scenario B (consumer index observed before receiver finishes reading entries, ARM64 / RISC-V):**
     1. Core *b* (node *Y*) loads message entries `buf[k .. k+len]`.
     2. Core *b* writes `consumer_index := c + len` (plain store).
     3. Without load-before-store ordering (`LDAR` / `DMB ISH` or `DMB ISHLD`+`STLR` / `fence r,w`), step 2 becomes visible to *X* before step 1 completes.
     4. Core *a* (node *X*) loads `consumer_index == c + len` and overwrites `buf[k .. k+len]` with a newer message.
     5. Core *b*'s reads in step 1 return a mix of old header and new payload, corrupting or silently dropping messages.

3. **External sources (verified 17 November 2026):**
   - Arm DDI `0487 M.d` §B2.3.7 `"Barrier-ordered-before"` (p. 278–280, <https://documentation-service.arm.com/static/6abbec2a6db85c5e6614a4a1>): plain loads and stores have no `Barrier-ordered-before` relation; ordering requires `E1 appears in program order before E2; E2 is an Explicit Memory Write Effect with Release semantics` (`STLR`), `E1 is an Explicit Memory Read Effect with Acquire semantics; E1 appears in program order before E2` (`LDAR`), or `DMB FULL` / `DMB LD` / `DMB ST`. Note: `DMB ISH` / `STLR` on consumer index ensures *reads* of ring entries precede the consumer-index store (`E1` read before `E2` `STLR` is `Barrier-ordered-before`; note `DMB ST` alone only orders writes, NOT reads before writes!).
   - RISC-V RVWMO §17.1.1.3 `"Preserved Program Order"` (<https://docs.riscv.org/reference/isa/v20260120/unpriv/rvwmo.html>): disjoint plain loads/stores are unordered; `"Explicit Synchronization"` requires `FENCE` (`fence rw,w` before index store, `fence r,rw` after index load) or `.aq`/`.rl` instructions (`Zalasr` is optional; base RV64GC uses `FENCE`).

4. **Verdict and severity:**
   - **Verdict:** **real**.
   - **Severity:** **breaks a guarantee** (silent loss/corruption of inter-node messages and permanent hang of `node_send`).

5. **Smallest correction:**
   - **Where & text:** At [`kernel-interface.md:968`](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L968):
     `"The sender writes the producer index with release order after writing the message entries, and loads the consumer index with acquire order before reusing slots; the receiver loads the producer index with acquire order before reading the entries, and writes the consumer index with release order after reading them (x86-64: compiler barriers around plain loads/stores; ARM64: STLR and LDAR; RISC-V: fence rw,w before the index store, fence r,rw after the index load)."`
     (Also add `RVWMO` at `l. 1813` per Finding 10.)
   - **Cost & when:** Paid once per ring message sent/consumed (not per memory access or payload word); zero extra CPU instructions on x86-64.
   - **New state:** None.

---

## Finding 3 — Seqlock and lock-free `signal` have no memory barriers

1. **Quote accuracy (`kernel-interface.md`):**
   - `l. 668`: Exact (`The lookup of a call reads the sequence word of the slot's segment (...), the slot, then the sequence word again, and reads them once more if a writer was active (...). A writer of a slot holds the node lock and makes the sequence word of its segment odd while it writes, even again after.`).
   - `l. 669`: Exact (`signal sets its bits by one atomic OR on the notify's word, then reads whether a thread waits (...), and returns without the lock if none does`).
   - `l. 673–679`: Accurate summary (`D-138` barrier guards memory reuse after destruction, not a torn slot read of a live slot).

2. **Replay against full context:**
   D-138 removed L2 and added a post-lock sequence re-check to `l. 668` for calls that take the node lock (`Once it holds the lock, the call reads again the sequence word...`). D-140 deliberately preserved lock-free execution for `signal` when no thread waits (`signal keeps no lock when nobody waits`), relying on the slot lookup returning a consistent `(kind, rights, object_pointer)` capability. However, `l. 668` never specifies barriers for the segment sequence lock itself.
   Race trace (ARM64 or RISC-V):
   1. Core *b* holds the node lock and replaces notify capability in slot *s* with a thread capability (or clears/rewrites it):
      - `W1`: writes `seq := 2k + 1` (odd)
      - `W2`: writes `slot[s].word0` (kind = `thread`), `slot[s].word1` (pointer to Thread object)
      - `W3`: writes `seq := 2k + 2` (even)
   2. Core *a* runs `signal(s)` lock-free:
      - `R1`: reads `seq` -> observes `2k` (even), OR `W2` becomes visible to *a* before `W1` (`W1` and `W2` are unordered plain writes to different addresses!) so `R1` reads `2k`, `R2` reads mixed words, and `W3` hasn't even occurred or already finished so `R3` reads `2k` (or `R1` and `R3` both read `2k` speculatively before `R2` reads `slot[s]`).
      - Concretely without reader load-load ordering: `R1` reads `seq = 2k`; `R3` (reordered before `R2`) reads `seq = 2k`; meanwhile *b* executes `W1, W2, W3`; then `R2a` reads `slot[s].word0` (old `notify`, `send` right) and `R2b` reads `slot[s].word1` (new Thread object pointer).
   3. Core *a* sees matching even `seq == 2k` and `kind == notify`, so it accepts the torn capability without retrying or taking the lock.
   4. Core *a* executes `LDSETAL` / `amoor.d.aqrl` with the badge into word 0 of what it thinks is a `notify`, corrupting word 0 of the live `thread` object (note: `signal` never takes the lock if waiter word reads 0, `l. 669`, so the post-lock recheck of `l. 668` never executes).

3. **External sources (verified 17 November 2026):**
   - Arm DDI `0487 M.d` §B2.3.7 `"Barrier-ordered-before"` (p. 278–279, <https://documentation-service.arm.com/static/6abbec2a6db85c5e6614a4a1>): plain loads and stores without `DMB ISHLD` / `DMB ISHST` / `LDAR` / `STLR` are not `Barrier-ordered-before`.
   - RISC-V RVWMO §17.1.1.3 `"Preserved Program Order"` (<https://docs.riscv.org/reference/isa/v20260120/unpriv/rvwmo.html>): disjoint loads/stores require explicit `FENCE` (`fence w,w` / `fence rw,w` on writer; `fence r,rw` / `fence r,r` on reader).

4. **Verdict and severity:**
   - **Verdict:** **real**.
   - **Severity:** **breaks a guarantee** (violates object integrity / containment inside the node on ARM64 and RISC-V; Opus wrote `"unsettled case; as written, it breaks containment inside the node"` — **breaks a guarantee** is the right label).

5. **Smallest correction:**
   - **Where & text:** At [`kernel-interface.md:668`](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L668):
     `"The writer makes the sequence word odd, orders that store before writing the slot (x86-64: compiler barrier; ARM64: DMB ISHST; RISC-V: fence w,w), writes the slot, then writes the even sequence word with release order (x86-64: compiler barrier; ARM64: STLR; RISC-V: fence rw,w before the store). The reader loads the sequence word with acquire order (x86-64: compiler barrier; ARM64: LDAR; RISC-V: load then fence r,rw), loads the slot, orders those loads before the second sequence read (x86-64: compiler barrier; ARM64: DMB ISHLD; RISC-V: fence r,r), then reads the sequence word again."`
   - **Cost & when:** Paid on lock-free capability slot lookup (every syscall) and slot modification (rare): **0 hardware barrier instructions on x86-64** (compiler barriers only); two lightweight read barriers (`LDAR`/`DMB ISHLD` or `fence r,rw`/`fence r,r`) on ARM64/RISC-V capability lookup, unavoidable for a lock-free seqlock that `signal` relies on.
   - **New state:** None.

---

## Finding 4 — x86-64 DR7 validation (`R/Wn = 10` I/O breakpoints, `LENn`, `CR4.DE`)

1. **Quote accuracy (`kernel-interface.md`):**
   - `l. 477`: Exact (`the breakpoint control word must have no bit outside its user mask (\`invalid\`, judged word by word in order)`).
   - `l. 1666`: Exact (`a control word with a bit outside the architecture's user mask (in \`abi/\`) is \`invalid\`, so a thread can never watch a kernel address or an I/O port`; `The kernel saves and restores a thread's debug registers only when its control word enables one`).
   - `l. 1291`, `l. 1653`, `l. 1687`: Accurate references.

2. **Replay against full context:**
   Checking [`dodos-kernel/abi/src/x86_64.rs`](file:///Users/btw/Documents/repos/dodos-kernel/abi/src/x86_64.rs#L92-L110) reveals an important partial fix in code that is **missing from `kernel-interface.md`**:
   - `abi/src/x86_64.rs:92` defines `DR7_USER_MASK = 0xFFFF_0055` (L0–L3 and R/W0–3 + LEN0–3), AND `abi/src/x86_64.rs:98-110` already defines `dr7_valid(word)` which explicitly checks `if word >> (16 + 4 * n) & 0b11 == DR7_CONDITION_IO { return false; }`!
   - However:
     1. `kernel-interface.md` (`l. 477` and `l. 1666`) still specifies ONLY a bit-mask check (`"no bit outside its user mask"`), contradicting `dr7_valid` and failing to prohibit `R/Wn = 10` in the contract text.
     2. Neither `kernel-interface.md` nor `abi/src/x86_64.rs` states the value of `CR4.DE` or handles invalid `LENn` combinations (e.g., `R/Wn = 00` with `LENn != 00`, which is architecturally undefined).
     3. **Correction caveat on Opus's own fix:** Opus proposes rejecting **both** `R/Wn == 10` **and** `LENn == 10` unconditionally (`"an R/Wn or LENn field of 10 is invalid"`). Per Intel SDM §20.2.4, `LENn = 10B` encodes **8-byte watchpoints** on Intel Core / Xeon / Atom (`x86-64`) data breakpoints (`R/Wn` = `01` or `11`), and is only undefined on older CPUs or when `R/Wn == 00`! Rejecting `LENn == 10` unconditionally is stricter than Intel64 requires (though safe if 8-byte watchpoints are intentionally omitted), whereas refusing `R/Wn == 00 && LENn != 00` is strictly required everywhere.
   Replay of the I/O breakpoint exploit against the literal contract text (`l. 477`, `l. 1666`):
   1. A holder of `write` on thread *W* calls `thread_write_regs` with `DR0 = 0x3F8`, `DR7` setting `L0 = 1, R/W0 = 0b10` (every bit inside `0xFFFF_0055`, address in user range).
   2. On resume, *W* triggers an `in`/`out` at `0x3F8` inside `ioport_in` (or a timer interrupt logs to the `0x3F8` console inside the kernel).
   3. With `CR4.DE = 1`, `#DB` fires in ring 0 -> unexpected exception in kernel mode (`l. 1291`) -> whole node panics.

3. **External sources (verified 17 November 2026):**
   - Intel SDM `325462-093US` §20.2.4 `"Debug Control Register (DR7)"` (p. 3825–3826, <https://cdrdv2.intel.com/v1/dl/getContent/671200>):
     - With `CR4.DE` set: `R/Wn`: `"10 — Break on I/O reads or writes."`; with `DE` clear: `"10 — Undefined."`
     - `LENn`: `"10 — Undefined (or 8 byte length, see note below)."`; `"If the corresponding RWn field in register DR7 is 00 (instruction execution), then the LENn field should also be 00. The effect of using other lengths is undefined."` Note: `"Encoding 10B is also supported in processors based on Intel Core microarchitecture or enhanced Intel Core microarchitecture... The encoding 10B is undefined for other processors."`
   - §20.3.1.2 `"Data Memory and I/O Breakpoint Exception Conditions"` (p. 3829): `"Data memory and I/O breakpoints are reported when the processor attempts to access a memory or I/O address specified in a breakpoint-address register (DR0 through DR3) that has been set up to detect data or I/O accesses (R/W flag is set to 1, 2, or 3)."` (No CPL filter.)

4. **Verdict and severity:**
   - **Verdict:** **real** (contract omits the `dr7_valid` field check already added in `abi/src/x86_64.rs`, leaves `CR4.DE` unstated, and leaves `R/Wn = 00 && LENn != 00` / `LENn = 10` unstated).
   - **Severity:** **cannot be built as written** (for the contract text as written; `abi/src/x86_64.rs` already refuses `R/Wn = 0b10`, making it a documentation-vs-code divergence plus an unsettled `CR4.DE` / `LENn` corner).

5. **Smallest correction:**
   - **Where & text:** At [`kernel-interface.md:477`](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L477) and [`kernel-interface.md:1666`](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1666) (and update `dr7_valid` in [`dodos-kernel/abi/src/x86_64.rs`](file:///Users/btw/Documents/repos/dodos-kernel/abi/src/x86_64.rs#L98)):
     `"The breakpoint control word must pass the architecture's control check (in abi/, x86-64 dr7_valid): no bit outside DR7_USER_MASK (which excludes GD bit 13), no R/Wn field equal to 10 (I/O breakpoints), for R/Wn = 00 only LENn = 00, and LENn = 10 only where the CPU supports 8-byte data watchpoints (or invalid otherwise); the kernel sets CR4.DE = 1 so encoding 10 is defined and refused (or keeps CR4.DE = 0 while refusing 10)."`
   - **Cost & when:** Checked once inside `thread_write_regs` validation; zero run-time or per-access cost.
   - **New state:** None.

## Finding 5 — Fence delays and repetitions inside the recovery reserve (`FENCE_NS = 20 ms`)

1. **Quote accuracy (`kernel-interface.md`):**
   - `l. 1306`: Exact (`runs the fence in its recovery reserve (below), in steps`).
   - `l. 1309`: Exact (`Wait at most NMI_GRACE_NS`). `l. 1504`: `NMI_GRACE_NS` | `1 ms`.
   - `l. 1311`: Exact (`10 ms after INIT and 200 µs between the two SIPIs`).
   - `l. 1313`: Exact (`The driver repeats steps 1 to 3 every millisecond for a core not yet confirmed, until it is or FENCE_NS has passed`).
   - `l. 1359`: Exact (`bandwidth 1/64 of a core (...), period 10 ms`). Also explicitly states: `its replenishment sets its core's hardware timer only while it has work, so a node with no work is woken by its sweep alone (D-135)`.
   - `l. 1511`: Exact (`156 µs of each 10 ms`).
   - `l. 1505`: Exact (`Time for the NMI grace, INIT, the two SIPIs after the delays of the SDM's example (10.2 ms), the stub and its repetitions`).
   - `l. 593` and `l. 1228`: Exact (`no context with budget wants`; `went out every 10 ms, not every 1 ms`).

2. **Replay against full context:**
   D-135 already caught this exact defect for `START_RETRY_NS` (`l. 1228`), moving start retries out of the 10 ms-period recovery reserve onto due events of the first core's timer queue. The fence (`l. 1306–1313`) was left on the recovery reserve (`period 10 ms`, `156 µs` bandwidth, woken on replenishment or sweep under full load when slack from `l. 593` is zero).
   Replay under full load on the driver's core 0 (target AP *p* has a hung kernel so NMI fails to stop it and INIT-SIPI-SIPI is needed):
   1. At `t0`: recovery reserve sends NMI (`step 1`) and enters `NMI_GRACE_NS` (1 ms).
   2. Under load, the reserve either blocks/yields its step or runs out of its 156 µs window; its next guaranteed wake is at `t0 + 10 ms` (next replenishment).
   3. At `t0 + 10 ms`: sends INIT (`step 2`), waits 10 ms (`l. 1311`).
   4. At `t0 + 20 ms`: sends first SIPI (`step 3`). At this point `20 ms = FENCE_NS` (`l. 1505`) has already elapsed before the second SIPI can even fire, marking the node **unfenced** (`l. 1252`) and permanently freezing its memory and granted frames until machine restart.
   5. Separately, `"repeats steps 1 to 3 every millisecond"` (`l. 1313`) is impossible both because the reserve period is 10 ms and because one pass of steps 1–3 itself requires `1 ms + 10 ms + 0.2 ms = 11.2 ms`. Even on due events, two rounds (`l. 1505`'s `"and its repetitions"`) take > `22.4 ms`, exceeding `FENCE_NS = 20 ms`.

3. **External sources (verified 17 November 2026):**
   - Intel SDM `325462-093US` §11.4.4.1, Table 11-1 `"Broadcast INIT-SIPI-SIPI Sequence and Choice of Timeouts"` (p. 3486, <https://cdrdv2.intel.com/v1/dl/getContent/671200>): `"; 10-millisecond delay loop."` after INIT IPI and `"; 200-microsecond delay loop"` after the first SIPI IPI.

4. **Verdict and severity:**
   - **Verdict:** **real**.
   - **Severity:** **contradiction** (and **cannot be built as written**: 1 ms repetition and 200 µs/1 ms waits violate the 10 ms recovery reserve cadence, and `FENCE_NS = 20 ms` cannot fit even one repetition of an 11.2 ms sequence).

5. **Smallest correction:**
   - **Where & text:** At [`kernel-interface.md:1306`](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1306), [`l. 1313`](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1313), and [`l. 1505`](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1505):
     `"The fence's timed waits (NMI_GRACE_NS, the 10 ms INIT-to-SIPI delay, the 200 µs SIPI gap) and its repetitions are due events of the driver's first core's timer queue, as the retries of a start are (l. 1228); a core whose round ends without confirmation begins a new round of steps 1 to 3 immediately after the previous round completes, until it is confirmed or FENCE_NS has passed."`
     And set `FENCE_NS` in `l. 1505` (which already permits `10 ms to 1 s`) to at least `30 ms` (e.g., `30 ms` or `50 ms`) so two full ~11.2 ms INIT-SIPI-SIPI rounds plus NMI grace and interrupt/stub margin complete within `FENCE_NS`.
   - **Cost & when:** Paid only when fencing a failed node (due event interrupt time on driver core 0).
   - **New state:** None (reuses existing fence record timestamps and core 0's timer queue).

---

## Finding 6 — Level-triggered IOAPIC masking & EOI across nodes

1. **Quote accuracy (`kernel-interface.md`):**
   - `l. 780–781`: Exact (`1. If the source is a level source, it is masked at the controller.` / `2. The interrupt controller is acknowledged (end of interrupt).`).
   - `l. 797`: Exact (`The inputs of an IOAPIC are programmed through an index and a data register, so they have one writer, the holder of the IOAPIC's role (...). Where the local APIC suppresses the broadcast of the end of interrupt and the IOAPIC has an EOI register, a level line is acknowledged from the claiming core by one write of the vector into that register; otherwise the masking and unmasking of a level line are requests to the role holder, slower and still correct.`).
   - `l. 816`: Exact (`An arrival never involves the role holder.`).
   - `l. 787`: Exact (`The work of the interrupt path is constant`).

2. **Replay against full context:**
   Neither D-139 (which added mask state to `Report` on IOAPIC role rebuild) nor D-140 resolved this conflict. Suppose node *C* claims an IOAPIC level line on a core of *C*, while node *H* != *C* holds the IOAPIC's unit role (`l. 1453`).
   - **On machines without Directed EOI (`"otherwise"` branch of `l. 797`):**
     1. *l. 797* requires masking a level line via a unit request to *H* (kernel ring -> *H*'s recovery reserve -> `UnitAnswer` back, taking up to two 10 ms reserve periods = 20 ms, `l. 971`).
     2. *l. 816* and *l. 787* forbid involving the role holder or unbounded/blocking work on an interrupt arrival; an interrupt handler cannot wait in *waiting for a unit* (`l. 687`).
     3. If the arrival handler sends LAPIC EOI (`step 2`, `l. 781`) immediately after queueing the mask request, the LAPIC broadcasts EOI to the IOAPIC, clearing the IOAPIC RTE's **Remote IRR** bit while the RTE is still unmasked and the device asserts the line -> the IOAPIC immediately re-delivers the interrupt in an interrupt storm for up to 20 ms (`2 × 10 ms` reserve period) until *H* masks the RTE.
     4. Conversely, if the handler withholds LAPIC EOI until *H* answers, the core's LAPIC ISR bit stays set, masking every equal-or-lower-priority vector on that core for up to 20 ms (and potentially blocking the unit-answer/kernel-ring wake itself if its vector priority is <= the IRQ's vector).
   - **On machines WITH Directed EOI:**
     `l. 780` states `"If the source is a level source, it is masked at the controller"`, which literally instructs masking the RTE (`IOREGSEL`/`IOWIN`, owned solely by *H*) rather than leaving the RTE unmasked and relying on LAPIC EOI-broadcast suppression keeping IOAPIC **Remote IRR** set until `irq_ack` writes the IOAPIC's 32-bit EOI register (`offset 0x40`). Note also that writing the IOAPIC EOI register directly from *C* requires *C*'s gate (not just *H*) to map/allow writes to that EOI register (not `IOREGSEL`/`IOWIN`).

3. **External sources (verified 17 November 2026):**
   - Intel SDM `325462-093US` §13.8.5 `"Signaling Interrupt Servicing Completion"` (p. 3602, <https://cdrdv2.intel.com/v1/dl/getContent/671200>):
     `"Software can inhibit the broadcast of EOI message by setting bit 12 of the Spurious Interrupt Vector Register (see Section 13.9). If this bit is set, a broadcast EOI is not generated on an EOI cycle even if the associated TMR bit indicates that the current interrupt was level-triggered."`
     `"System software desiring to perform directed EOIs for level-triggered interrupts should set bit 12 of the Spurious Interrupt Vector Register and follow each the EOI to the local xAPIC for a level triggered interrupt with a directed EOI to the I/O APIC generating the interrupt (this is done by writing to the I/O APIC’s EOI register)."`
   - Intel VT-d `5.20` §5.1.5.1 (p. 95) also explicitly distinguishes `"platforms using End-of-Interrupt (EOI) broadcasts"`.

4. **Verdict and severity:**
   - **Verdict:** **real**.
   - **Severity:** **contradiction** (and **breaks a guarantee** in the `"otherwise"` path: constant-time lockless arrival / no role holder on arrival cannot coexist with asynchronous IOAPIC masking without causing an interrupt storm or blocking core vectors).

5. **Smallest correction:**
   - **Where & text:** At [`kernel-interface.md:780`](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L780) and [`l. 797`](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L797):
     `"On x86-64, a level line of an IOAPIC whose role the caller's node does not hold is claimable only when Directed EOI is supported (LAPIC EOI-broadcast suppression and an IOAPIC EOI register, published in Interrupts flag bit 2); otherwise irq_claim of that line on a non-holder node returns unsupported. Under Directed EOI, step 1 of an arrival writes no IOAPIC redirection entry: step 2 sends the LAPIC EOI with broadcast suppressed, leaving the IOAPIC Remote IRR set (keeping the line masked), and irq_ack (or a bind delivering a pending interrupt) writes the vector through the claiming node's gate to the IOAPIC EOI register."`
     (Note: if the IOAPIC's `0x40` EOI register shares a 4 KB MMIO page with `IOREGSEL`/`IOWIN`, only the gate—never ordinary kernel code—maps that page writable, and the gate permits writes only to `IOREGSEL`/`IOWIN` for the role holder and to `EOI` (`0x40`) for the claiming node's claimed vector.)
   - **Cost & when:** Zero extra cost on arrivals (one LAPIC EOI write; no unit request); one gate write on `irq_ack`.
   - **New state:** None.

---

## Finding 7 — Enabling IOMMUs in blocking mode before first process destroys active RMRRs / GOP

1. **Quote accuracy (`kernel-interface.md`):**
   - `l. 2009`: Exact (`turns every IOMMU unit on in blocking mode`).
   - `l. 341`: Exact (`By default every device is blocked`).
   - `l. 402`: Exact (`the driver's node (...) into the iospace of its device (...) before the device is attached`).
   - `l. 1979` and `l. 2081`: Exact (`the framebuffer`; `Framebuffer` entry in start-up page).

2. **Replay against full context:**
   Look at [`Docs/architecture/gpu.md:39-42`](file:///Users/btw/Documents/repos/Docs/architecture/gpu.md#L39-L42) and [`Docs/architecture/platform.md:94`](file:///Users/btw/Documents/repos/Docs/architecture/platform.md#L94): DodOS explicitly uses the firmware framebuffer (UEFI GOP) for initial display output and as its fallback software-compositor target (`D-050`). Meanwhile `l. 2009` turns every IOMMU unit on in blocking mode during machine start-up before any driver starts, and `l. 402` delegates RMRRs entirely to user-space drivers later at `iospace_attach`.
   Replay on any Intel platform with active RMRR DMA (integrated UMA graphics GOP framebuffer in stolen memory, or BIOS SMM USB legacy keyboard emulation):
   1. First stage preserves UEFI GOP framebuffer and hands it over (`l. 1979`, `l. 2081`).
   2. Step 2 of machine start-up (`l. 2009`) enables VT-d translation with all devices blocked (`abort-dma` or all-not-present root/context entries).
   3. Active DMA from the display engine to its stolen-memory RMRR (or SMM USB controller DMA to its RMRR) hits the IOMMU, has no identity mapping, and is blocked with DMA remapping faults.
   4. The firmware framebuffer stops scanning out (or breaks fallback software compositor) and BIOS USB legacy emulation fails until (or if) a user-space driver ever attaches.

3. **External sources (verified 17 November 2026):**
   - Intel VT-d Revision `5.20`, Order `D51397-019`, §3.4.4 `"Abort DMA Mode"` (p. 35, <https://cdrdv2.intel.com/v1/dl/getContent/671081>):
     `"System software should not program remapping hardware in abort-dma mode if devices are active that require access to the reserved memory region as reported through RMRR (i.e., Bus Master Enable = 1 for such devices)."`
   - Intel VT-d Revision `5.20`, §3.16 `"Handling Requests to Reserved System Memory"` (p. 57, <https://cdrdv2.intel.com/v1/dl/getContent/671081>):
     `"Requests to these reserved regions may either occur as a result of operations performed by the system software driver (for example in the case of DMA from unified memory access (UMA) graphics controllers to graphics reserved memory), or may be initiated by non system software (for example in case of DMA performed by a USB controller under BIOS SMM control for legacy keyboard emulation). For proper functioning of these legacy reserved memory usages, when system software enables DMA remapping, the second-stage translation structures for the respective devices are expected to be set up to provide identity mapping for the specified reserved memory regions with read and write permissions."`

4. **Verdict and severity:**
   - **Verdict:** **real**.
   - **Severity:** **contradiction** (contradicts [`gpu.md:39-42`](file:///Users/btw/Documents/repos/Docs/architecture/gpu.md#L39-L42) / `l. 1979` GOP handover and violates VT-d §3.4.4 / §3.16; **cannot be built as written** on machines with active RMRR DMA).

5. **Smallest correction:**
   - **Where & text:** At [`kernel-interface.md:341`](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L341), [`l. 402`](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L402), and [`l. 2009`](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L2009):
     `"At machine start-up, before enabling each IOMMU unit, the kernel reads the DMAR RMRR entries as well as DRHD: every device named by an active RMRR is attached to the unit's kernel domain (number D − 1, l. 1030) with an identity mapping (read and write) of its RMRR ranges only (excluded from usable untyped memory as device memory), until the device's driver performs its first iospace_attach (after mapping those RMRRs into its iospace per l. 402); every other device is blocked."`
     (Wait: if USB legacy handoff is disabled at start-up/firmware stage, USB RMRRs need no lifetime identity map; iGPU/GOP RMRRs still need it until driver attach.)
   - **Cost & when:** Paid once at machine start-up (and released once at first driver attach); zero runtime or per-access cost.
   - **New state:** Identity page tables for active RMRR ranges kept at boot (bounded by firmware RMRR count, reclaimed/unused after first attach or left in boot tables).

---

## Finding 8 — Counter reads in `clock_now` and `now` lack ordering barriers

1. **Quote accuracy (`kernel-interface.md`):**
   - `l. 496`: Exact (`A reader reads the sequence word, the parameters, the counter, then the sequence word again, and starts over if the word was odd or has changed`).
   - `l. 500`: Exact (`A value read on one core, then sent by any means to another core, is never greater than a value read afterwards on that core.`).
   - `l. 497`: Exact (`the same value`).

2. **Replay against full context:**
   Neither `kernel-interface.md` nor `kernel.md` specifies serialization/instruction barriers around `RDTSC` (x86-64), `CNTVCT_EL0` (ARM64), or `rdtime` (RISC-V), nor seqlock read barriers around `seq1`, parameters, counter, and `seq2`.
   - **Cross-core monotonicity violation (`l. 500`):**
     1. Core *a* calls `clock_now`, observes `T`, and writes `msg := T` (with release/lock).
     2. Core *b* loads `msg` (`T`) and calls `clock_now` (`seq1`, parameters, `RDTSC`/`CNTVCT_EL0`, `seq2`).
     3. Without `LFENCE` before `RDTSC` (or `ISB` before `CNTVCT_EL0`, or `fence` before `rdtime`), core *b*'s counter read executes speculatively *before* core *b*'s load of `msg` (or acquire of the lock/channel), returning a timestamp `< T`.
   - **Torn seqlock across `ns_base` update at suspend/resume (`l. 499`):**
     1. On x86-64 (`"subsequent instructions may begin execution before the read operation is performed"`) or ARM64 (without `ISB` or data/address dependency after `MRS CNTVCT_EL0`), the second load `seq2` executes *before* `RDTSC`/`CNTVCT_EL0` completes.
     2. Meanwhile the kernel updates `ns_base` (and `seq` odd -> even) across resume.
     3. Reader pairs old `seq1` == new `seq2`? Even simpler: `seq1` and `seq2` both execute *before* the delayed `RDTSC`/`CNTVCT_EL0` reads the post-resume counter while using pre-resume `ns_base`/`counter_base`!

3. **External sources (verified 17 November 2026):**
   - Intel SDM `325462-093US`, `"RDTSC—Read Time-Stamp Counter"` (Vol. 2B, p. 1850, <https://cdrdv2.intel.com/v1/dl/getContent/671200>):
     `"The RDTSC instruction is not a serializing instruction. It does not necessarily wait until all previous instructions have been executed before reading the counter. Similarly, subsequent instructions may begin execution before the read operation is performed."`
     `"If software requires RDTSC to be executed only after all previous instructions have executed and all previous loads are globally visible, it can execute LFENCE immediately before RDTSC."`
   - Linux `arch/x86/include/asm/vdso/gettimeofday.h` (`l. 127`) uses `rdtsc_ordered()`.
   - Arm DDI `0487 M.d`, §D12.2.2 `"The virtual counter"` (p. 7940, <https://documentation-service.arm.com/static/6abbec2a6db85c5e6614a4a1>; parent section `D12.2`, as Opus cited):
     `"Reads of CNTVCT_EL0 can occur speculatively and out of order relative to other instructions executed on the same PE."`
     And Example D12-3 (p. 7940) / Example D12-2 (p. 7939) show `ISB` before `MRS Xn, CNTVCT_EL0` (or `CNTVCTSS_EL0` under `FEAT_ECV`) AND `ISB` (or XOR address dependency `EOR Xm, Xn, Xn; LDR Xa, [Xb, Xm]`) *after* `MRS` to order subsequent loads!
   - Linux `arch/arm64/include/asm/arch_timer.h` (`l. 81–83`): `"isb\n mrs %0, cntvct_el0"` / `SYS_CNTVCTSS_EL0` with `ARM64_HAS_ECV`.

4. **Verdict and severity:**
   - **Verdict:** **real**.
   - **Severity:** **breaks a guarantee** (violates `l. 500` cross-core monotonicity and allows torn reads against `ns_base` updates).

5. **Smallest correction:**
   - **Where & text:** At [`kernel-interface.md:496`](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L496):
     `"A reader loads the sequence word with acquire order (ARM64 LDAR, RISC-V load + fence r,rw, x86-64 compiler barrier), reads the parameters, reads the counter ordered after earlier loads and before the second sequence read (x86-64: LFENCE; RDTSC; LFENCE or RDTSCP; LFENCE; ARM64: ISB; MRS CNTVCT_EL0; ISB or CNTVCTSS_EL0 with ISB/dependency; RISC-V: fence r,rw before and after rdtime), orders parameter/counter reads before the second sequence load (ARM64 DMB ISHLD/ISB, RISC-V fence r,r), and restarts if the word was odd or has changed."`
   - **Cost & when:** Paid only when reading `clock_now` or kernel entry `now`; zero per-memory-access cost.
   - **New state:** None.

## Finding 9 — `IOMMU_WAIT_NS = 1 ms` and the order of the last completion check

1. **Quote accuracy (`kernel-interface.md`):**
   - `l. 393`: Exact (`The bound is IOMMU_WAIT_NS (1 ms, provisional) from the submission to the unit. A unit that has not confirmed by then has failed`; `it checks for the confirmation at each later step of its recovery reserve, or at the unit's completion interrupt`).
   - `l. 1045`: Exact (`answers done at the confirmation and failed at IOMMU_WAIT_NS`).
   - `l. 396–398`: Accurate summary (memory/grants pinned and devices/unit permanently unusable until restart).

2. **Replay against full context:**
   Neither D-131, D-139, nor D-140 specifies the read-before-deadline order or justifies 1 ms against the 10 ms recovery reserve period (`l. 1359`).
   Replay:
   1. At `t0`, unit holder *H* submits an IOTLB/IEC invalidation to the queued invalidation (QI) ring and sets deadline `t0 + IOMMU_WAIT_NS` (1 ms).
   2. The hardware completes the invalidation at `t0 + 0.8 ms` (or at `t0 + 1.2 ms` due to SMM stall or PCIe/chipset activity).
   3. Under load (`l. 1359`), *H*'s recovery reserve next runs at `t0 + 10 ms` (if no completion interrupt was armed or after an SMI delayed it).
   4. If *H* checks `now - t0 >= IOMMU_WAIT_NS` **before** reading the unit's QI completion status (`VTD_QI_DONE` / wait descriptor status), it declares the healthy, already-completed unit permanently *failed* (`bit 63` of role word, `l. 393–398`).
   5. Even with status checked first, `1 ms` is shorter than common BIOS SMM stalls and far below standard OS timeouts when a slow invalidation completes in 2–10 ms (which, given the 10 ms reserve cadence, isn't even polled until 10 ms under load).

3. **External sources (verified 17 November 2026):**
   - Intel VT-d Revision `5.20`, Order `D51397-019`, §4.3 `"Handling of Device-TLB Invalidations"` (p. 69, <https://cdrdv2.intel.com/v1/dl/getContent/671081>): sets a timeout recommendation only for ATS Device-TLB invalidations (`"The invalidation completion time-out value is recommended to be sufficiently larger than the PCI Express read completion time-outs"`), and specifies no latency upper bound for normal IOTLB or IEC invalidations (note ATS is disabled in `l. 402`).
   - Linux `drivers/iommu/intel/dmar.c` (`l. 1573`): `while (READ_ONCE(qi->desc_status[wait_index]) != QI_DONE)` — no 1 ms failure cutoff on QI wait descriptors.
   - Linux `arch/x86/include/asm/iommu.h` (`l. 26–27`): `/* 10 seconds */ #define DMAR_OPERATION_TIMEOUT ((cycles_t) tsc_khz*10*1000)`.

4. **Verdict and severity:**
   - **Verdict:** **real**.
   - **Severity:** **unsettled case** (and **breaks a guarantee** if deadline is checked before status: falsely marks a healthy IOMMU permanently failed and freezes memory/devices until reboot).

5. **Smallest correction:**
   - **Where & text:** At [`kernel-interface.md:393`](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L393) and [`l. 1045`](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1045):
     `"At each check, the holder reads the unit's completion status first, and judges the unit failed only if the status still reads incomplete at or after the deadline (IOMMU_WAIT_NS)."`
     And make `IOMMU_WAIT_NS` a machine-calibrated value (or raise the provisional default well above SMI/10 ms reserve intervals, e.g., `100 ms` provisional with per-machine range in `BootMembership`).
   - **Cost & when:** Reorders two checks inside the holder's recovery-reserve step; zero normal-path cost.
   - **New state:** None.

---

## Finding 10 — RISC-V omitted from grant-counter Dekker pair and formal memory models

1. **Quote accuracy (`kernel-interface.md`):**
   - `l. 914`: Exact (`Each side writes its own word by compare-and-swap and then reads the other's (on ARM64 the compare-and-swap has release and the read acquire semantics), so at least one sees the other.`).
   - `l. 1813`: Exact (`under x86-TSO and the Armv8 memory model`). See also [`kernel.md:35`](file:///Users/btw/Documents/repos/Docs/architecture/kernel.md#L35).

2. **Replay against full context:**
   Look at `l. 669`, where the contract explicitly specifies `x86-64`, `ARM64 (LDSETAL)`, **and** `RISC-V (amoor.d.aqrl)`. By contrast, `l. 914` names only x86-64 (implicitly via CAS) and ARM64 (explicitly: release CAS + acquire load), leaving RISC-V unspecified, and `l. 1813` (plus `kernel.md:35`) omits RVWMO from the formal memory models.
   Race trace (RISC-V under RVWMO, assuming an LR/SC CAS with `.rl` only or `amocas` without `.aqrl` followed by plain `ld`):
   1. Node *Y* (grantee) runs `aspace_map` under a grant:
      - `W_Y`: updates `use_entry.count` via `lr.d` / `sc.d.rl` (release only, no `aq` and no trailing `fence rw,rw`).
      - `R_Y`: reads `grant_entry` via plain `ld` (no `aq` on plain `ld` in RV64GC!).
   2. Node *X* (granter) runs `grant_revoke`:
      - `W_X`: writes `grant_entry := revoking` via `lr.d` / `sc.d.rl` (or `amocas.d.rl`).
      - `R_X`: reads `use_entry.count` via plain `ld`.
   3. Under RVWMO, neither `W_Y -> R_Y` nor `W_X -> R_X` is in Preserved Program Order (`PPO`): `R_Y` can execute before `W_Y` and observe `grant_entry == live`, while `R_X` executes before `W_X` and observes `use_entry.count == 0`.
   4. *X* frees the grant and reclaims/gives away the frame while *Y*'s gate maps the frame into *Y*'s page tables (`l. 914` invariant broken).

3. **External sources (verified 17 November 2026):**
   - Arm DDI `0487 M.d` §B2.3.7 `"Barrier-ordered-before"` (p. 279, <https://documentation-service.arm.com/static/6abbec2a6db85c5e6614a4a1>): `"E1 is an Explicit Memory Write Effect with Release semantics. E1 appears in program order before E2. E2 is an Explicit Memory Read Effect with Acquire semantics."` -> ARM64 release-CAS + acquire-load IS sound as written.
   - RISC-V RVWMO §17.1.1.3 `"Preserved Program Order"` (<https://docs.riscv.org/reference/isa/v20260120/unpriv/rvwmo.html>): store-before-load is ordered only by `"There is a FENCE instruction that orders a before b"` or `"a and b both have RCsc annotations"`. Plain `ld` has no RCsc annotation (`Zalasr` is separate/optional).
   - RISC-V `"A" Extension` §12.1 (<https://docs.riscv.org/reference/isa/v20260120/unpriv/a-st-ext.html>): `"The LR/SC sequence can be given release semantics by setting the rl bit on the SC instruction... Such a sequence does not act as a fence for ordering ordinary load and store instructions before and after the sequence."` Whereas `"Setting both the aq and the rl bit on an AMO makes the sequence sequentially consistent, meaning that it cannot be reordered with earlier or later memory operations from the same hart."` (Or `fence rw,rw` after the CAS before reading the other's word.)

4. **Verdict and severity:**
   - **Verdict:** **real**.
   - **Severity:** **unsettled case** (and **breaks a guarantee** on RISC-V if built without `fence rw,rw` / `.aqrl`).

5. **Smallest correction:**
   - **Where & text:** At [`kernel-interface.md:914`](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L914):
     `"Each side writes its own word by compare-and-swap and then reads the other's (on ARM64 the compare-and-swap has release and the read acquire semantics; on RISC-V the compare-and-swap uses fence rw,rw before reading the other's word, or amocas.aqrl), so at least one sees the other."`
     And at [`kernel-interface.md:1813`](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1813) and [`kernel.md:35`](file:///Users/btw/Documents/repos/Docs/architecture/kernel.md#L35): replace `"under x86-TSO and the Armv8 memory model"` with `"under x86-TSO, the Armv8 memory model and RVWMO"`.
   - **Cost & when:** Paid only on mapping/revoking a cross-node frame grant; zero cost on normal memory accesses.
   - **New state:** None.

---

## Finding 11 — ARM64 cores with EL2 but without `FEAT_VHE`

1. **Quote accuracy (`kernel-interface.md`):**
   - `l. 1315`: Exact (`The kernel runs at the highest non-secure exception level the machine offers (EL2, with the virtualization host extensions, where EL2 exists; EL1 otherwise), because SDEI requires its client to execute at that level`).
   - `l. 1992`: Exact (`at EL2 if the stage ran at EL2, otherwise EL1 (the kernel sets the virtualization host extensions itself, ...)`).
   - `l. 1317`: Accurate (`Without a successful SDEI registration ... the core is of class 0`; `the machine start-up runs one node`).

2. **Replay against full context:**
   `l. 1317` correctly discovers fence classes at start-up from hardware/firmware probing rather than assuming them, and sets class 0 if SDEI registration fails (`l. 1315`). However, `l. 1315` and `l. 1992` omit what happens on an Armv8.0 core that implements EL2 (`ID_AA64PFR0_EL1.EL2 != 0`) **without** `FEAT_VHE` (`ID_AA64MMFR1_EL1.VH == 0`).
   Replay at boot:
   1. First stage enters the kernel at EL2 (`l. 1992`).
   2. The kernel executes `"sets the virtualization host extensions itself"` (`HCR_EL2.{E2H, TGE} = {1, 1}`, programs `TTBR1_EL2` per `kernel.md:148`).
   3. Without `FEAT_VHE`, `HCR_EL2.E2H` is `RES0` and `TTBR1_EL2` does not exist (setting `TGE=1` alone routes EL0 exceptions to EL2 using only the EL2 single-range `TTBR0_EL2` translation regime, with no split kernel/user `TTBR1`/`TTBR0` and different `CNTVCT_EL0` behavior). The kernel as designed (`kernel.md:143–148`, SKEE / `TCR_EL1.T1SZ`) cannot run at EL2 without `FEAT_VHE`.
   4. If instead the kernel drops from EL2 to EL1 when `FEAT_VHE` is absent, TF-A's `sdei_client_el()` inspects `SCR_EL3.HCE` (set whenever EL2 is enabled for Non-secure state), sees `MODE_EL2`, and rejects SDEI calls made from EL1 — making the core fence class 0 (`l. 1317`: one node unless monitor/accept-unfenced). Neither the drop to EL1 nor this `FEAT_VHE` check is stated in `l. 1315` or `l. 1992`.

3. **External sources (verified 17 November 2026):**
   - Arm DDI `0487 M.d`, §D8.13 `"Virtualization Host Extensions"` (p. 7824, <https://documentation-service.arm.com/static/6abbec2a6db85c5e6614a4a1>): `"All statements in this chapter require implementation of FEAT_VHE."` And §D8.13.1: `TTBR1_EL2` and the EL2&0 host OS regime depend on `FEAT_VHE` and `HCR_EL2.E2H = 1`.
   - Trusted Firmware-A `v2.12.0`:
     - `services/std_svc/sdei/sdei_private.h` (`l. 164–171`): `sdei_client_el()` returns `((read_ctx_reg(el3_ctx, CTX_SCR_EL3) & SCR_HCE_BIT) != 0U) ? MODE_EL2 : MODE_EL1;`.
     - `docs/components/sdei.rst` (`l. 200–204`): `"EL2, if EL2 is implemented."` / `"Non-secure EL1, if EL2 is not implemented or disabled."`

4. **Verdict and severity:**
   - **Verdict:** **real**.
   - **Severity:** **unsettled case** (and **cannot be built as written** if an Armv8.0 non-VHE EL2 core attempts to enable VHE at EL2).

5. **Smallest correction:**
   - **Where & text:** At [`kernel-interface.md:1315`](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1315) and [`l. 1992`](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1992):
     `"If EL2 is implemented without FEAT_VHE (ID_AA64MMFR1_EL1.VH = 0), machine start-up drops the core from EL2 to EL1 before setting up its tables; on firmware that binds SDEI to EL2 whenever EL2 is implemented (TF-A), SDEI registration fails and the core is of fence class 0."`
   - **Cost & when:** One feature-register check and `ERET` to EL1 once per core at boot; zero runtime cost.
   - **New state:** None.

---

## Finding 12 — RISC-V ACLINT `MSWI` vs `SSWI` and machines without S-mode IPI hardware

1. **Quote accuracy (`kernel-interface.md`):**
   - `l. 329`: Exact (`RISC-V uses the kernel's own interrupt rather than the SBI remote fence`).
   - `l. 1091`: Exact (`a store to the ACLINT's or the target IMSIC's registers`).
   - `l. 2208`: Exact (`APLIC, IMSIC, Sstc`).
   - See also [`kernel-interface.md:1453`](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1453) and [`kernel.md:161, 163`](file:///Users/btw/Documents/repos/Docs/architecture/kernel.md#L161-L163).

2. **Replay against full context:**
   Checking [`kernel.md:161–163`](file:///Users/btw/Documents/repos/Docs/architecture/kernel.md#L161-L163) reveals **two** closely related defects:
   1. **ACLINT privilege-level ambiguity (`wrong external fact`):** Both `kernel-interface.md:1091` (`"a store to the ACLINT's or the target IMSIC's registers"`), `l. 1453` (`"the ACLINT's software-interrupt registers"`), and `kernel.md:161` refer generically to `"ACLINT"` without specifying **`SSWI`**. In the ACLINT specification, `MSWI` (including SiFive CLINT's IPI range `0x0000_0000–0x0000_3fff`) is a **Machine-mode** device, whereas only **`SSWI`** is a **Supervisor-mode** device. Mapping `MSWI` into the S-mode gate either faults on PMP or lets S-mode corrupt M-mode interrupts.
   2. **CLINT-only / non-SSWI platforms (`unsettled case` across `kernel-interface.md` vs `kernel.md`):** Many RISC-V systems provide only a machine-mode CLINT/MSWI and PLIC/APLIC without `SSWI` or `IMSIC`. [`kernel-interface.md`](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L2001) neither refuses such platforms at start-up nor states an SBI fallback for `send_ipi`, **even though [`kernel.md:163`](file:///Users/btw/Documents/repos/Docs/architecture/kernel.md#L163) already places `"the IPI extension"` (`sbi_send_ipi`) on the RISC-V firmware allow-list**! (Note `l. 329` rejects SBI *remote TLB fence* `RFENCE`, not necessarily `sbi_send_ipi` when no S-mode MMIO IPI exists.)

3. **External sources (verified 17 November 2026):**
   - RISC-V `riscv-aclint.adoc` (`riscvarchive/riscv-aclint`, `l. 90–133`):
     - `"Unfortunately, the SiFive CLINT has a unified register map for both IPI and timer functionalities and it does not provide supervisor-level IPI functionality."`
     - Table 1 `"ACLINT Devices"`: `MSWI` = `Machine | Inter-processor (or software) interrupts`; `SSWI` = `Supervisor | Inter-processor (or software) interrupts`.
     - Table 2 `"One SiFive CLINT device is equivalent to two ACLINT devices"`: `0x0000_0000 - 0x0000_3fff | MSWI | Machine-level inter-processor (or software) interrupts`.
   - RISC-V SBI `ext-ipi.adoc` (`riscv-non-isa/riscv-sbi-doc`, `l. 11–17`; note `https://docs.riscv.org/reference/sbi/v3.0/ext-ipi.html` returned HTTP 503 today): `sbi_send_ipi(unsigned long hart_mask, unsigned long hart_mask_base)` — `"Interprocessor interrupts manifest at the receiving harts as the supervisor software interrupts."`

4. **Verdict and severity:**
   - **Verdict:** **real**.
   - **Severity:** **unsettled case** (plus **wrong external fact** / ambiguity failing to name ACLINT `SSWI` vs `MSWI`, and unresolved discrepancy with `kernel.md:163` listing the SBI IPI extension).

5. **Smallest correction:**
   - **Where & text:** At [`kernel-interface.md:1091`](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1091), [`l. 1453`](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1453), and [`kernel.md:161`](file:///Users/btw/Documents/repos/Docs/architecture/kernel.md#L161): change `"ACLINT's software-interrupt registers"` to `"ACLINT's supervisor software-interrupt device (SSWI)"`. And either:
     - (a) at `l. 2001` (start-up refusals), add `"or, on RISC-V, the harts have neither an IMSIC nor an ACLINT SSWI"` (and remove `"the IPI extension"` from `kernel.md:163`); **or**
     - (b) at `l. 1091`, add `"or, where neither an IMSIC nor an SSWI exists, through SBI sbi_send_ipi (already on kernel.md's allow-list)"` (choosing `SSWI`/`IMSIC` at start-up when present so fast systems pay zero SBI overhead).
   - **Cost & when:** Choice (a): start-up check only; choice (b): zero overhead on `SSWI`/`IMSIC` hardware, `ECALL` only on legacy CLINT-only systems when sending an IPI.
   - **New state:** None.


---

## Finding 13 — VT-d root and context table sizes reversed

1. **Quote accuracy:**
   - [`kernel-interface.md:341`](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L341): `"(root and context tables, 1 MB and 4 KB per unit on x86-64)"` — **exact** (full sentence: `"The memory for the units' own tables (root and context tables, 1 MB and 4 KB per unit on x86-64) is kept by the kernel at start (see Start-up state), once, and never grows."`).

2. **Step-by-step replay:**
   - The parenthetical pairs `"root and context tables"` in order with `"1 MB and 4 KB per unit on x86-64"`, stating that the root table is 1 MB and the context table(s) total 4 KB.
   - In [`kernel-interface.md:2018`](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L2018), the exact allocation is left to `"the tables of the IOMMU units"` (`"Their size is the implementation's own"`), so an implementer using the real VT-d sizes still lands at `4 KB + 1 MB` for legacy mode, whereas an implementer copying the reversed comment literally or failing to specify legacy mode (vs. scalable mode, which needs 2 MB for lower+upper context tables plus PASID directories/tables) either mis-allocates or leaves the mode implicit.
   - No other document (`kernel.md`, `decisions/README.md`) explains or overrides this wording (`Docs/research/drafts/memory.md:130` repeats the same swapped order).

3. **External source (verified 17 November 2026):**
   - Intel VT-d Architecture Specification, rev. 5.20 (`D51397-019`, `https://cdrdv2.intel.com/v1/dl/getContent/671081`):
     - §3.4.2 `"Root Table"` (p. 33): `"The root-table is 4-KByte in size and contains 256 root-entries to cover the PCI bus number space (0-255)."`
     - §3.4.2 `"Context Table"` (p. 33): `"Each context-table contains 256 entries, with each entry corresponding to a specific device function on the bus identified by the referencing root-entry."` (Each legacy context-entry is 16 bytes -> `256 * 16 B = 4 KB` per bus; across 256 PCI buses `0..255`, context tables take up to `256 * 4 KB = 1 MB`.)
     - §3.4.3 `"Scalable-Mode Translation"` (p. 34): Scalable mode replaces each 4 KB legacy context table with a 4 KB *lower* and 4 KB *upper* context table (`2 MB` max across 256 buses) plus PASID-directory and PASID-table pages; the contract does not state scalable mode and allocates no dynamic PASID tables.

4. **Verdict and severity:**
   - **Verdict:** **real**.
   - **Severity:** **wrong external fact**.

5. **Smallest correction:**
   - **Where & text:** At [`kernel-interface.md:341`](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L341), replace `"(root and context tables, 1 MB and 4 KB per unit on x86-64)"` with `"(in legacy translation mode, a 4 KB root table and up to 256 context tables of 4 KB, 1 MB in all, per unit on x86-64)"`.
   - **Cost & when:** Zero runtime or memory cost (clarifies the actual 1 MB + 4 KB attribution and states legacy translation mode).
   - **New state:** None.

---

## Finding 14 — Console pacing outruns a 16550 UART at 115,200 baud

1. **Quote accuracy:**
   - [`kernel-interface.md:1653`](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1653): `"a due event every 1 ms (...) at which it writes at most 16 bytes; that matches a 16550's transmit queue at 115,200 baud"` — **exact** with ellipsis over `"(in its timer queue, counted among the 16 due events of an interrupt)"`.
   - [`kernel-interface.md:1632`](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1632): `"polls its transmit status"` — **exact**.

2. **Step-by-step replay:**
   - Step 1 (framing rate): With standard 8N1 UART framing (1 start bit + 8 data bits + 1 stop bit = 10 bits/byte), 115,200 baud carries `115,200 / 10 = 11,520 bytes/s` = `11.52 bytes/ms`. Sending 16 bytes takes `16 / 11.52 = 1.3889 ms` (~1.39 ms), not 1.0 ms.
   - Step 2 (`t = 0 ms`): Assume the console role holder starts with an empty 16-byte TX FIFO and enables/fills it on the first 1 ms due event: it writes 16 bytes.
   - Step 3 (`t = 1.0 ms`): After 1.0 ms, the UART has shifted out ~11 bytes and ~5 bytes still sit in the TX FIFO (so LSR `THRE` / FIFO-empty status is false, or the FIFO has room for at most 11 bytes depending on how `polls its transmit status` checks `THRE`).
   - Step 4: Because [`l. 1632`](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1632) says `"polls its transmit status"`, the kernel will not overwrite bytes in the FIFO, **but** the 1 ms pacing claim fails in practice:
     - If the event busy-waits until `THRE` is set before writing each byte or batch of 16 bytes, each 1 ms console due event burns ~389 µs (or more if checking `THRE` between bytes at ~86.8 µs/byte) of kernel event time charged as an interrupt on the console node's core 0 ([`l. 1653`](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1653)).
     - If it stops without waiting when `THRE == 0`, it cannot sustain 16 bytes per 1 ms (at most ~11 bytes/ms).
   - No other document (`kernel.md`, `decisions/README.md`) alters the 1 ms / 16-byte figure.

3. **External source (verified 17 November 2026):**
   - TI `PC16550D` Universal Asynchronous Receiver/Transmitter datasheet (`ti.com` timed out): **Not opened**. (Note: 115,200 baud / 10 bits per byte = `11,520 B/s` -> `1.389 ms` for 16 bytes is exact serial-framing arithmetic; the 16550A/D 16-byte TX FIFO depth and `LSR.THRE` polling behavior are standard PC16550 facts, and Opus accurately cited `l. 1632` `"polls its transmit status"`.)

4. **Verdict and severity:**
   - **Verdict:** **real**.
   - **Severity:** **wrong external fact**.

5. **Smallest correction:**
   - **Where & text:** At [`kernel-interface.md:1653`](file:///Users/btw/Documents/repos/Docs/architecture/kernel-interface.md#L1653), change `"a due event every 1 ms (in its timer queue, counted among the 16 due events of an interrupt) at which it writes at most 16 bytes; that matches a 16550's transmit queue at 115,200 baud"` to `"a due event every 1.5 ms (in its timer queue, counted among the 16 due events of an interrupt) at which it writes at most 16 bytes while transmit status reads empty without spinning (at 115,200 baud 8N1, 16 bytes drain in 1.39 ms)"`.
   - **Cost & when:** Reduces console due-event frequency by a third and eliminates busy-wait spinning during a due event; paid only when console messages wait.
   - **New state:** None.

---

## Cross-check of Opus's "What I checked and found sound" and "What I did not check"

Every item Opus marked sound and checked against the named 17 November 2026 editions was re-checked against our opened sources:
- **Intel SDM `325462-093`:** All quoted rules and section numbers match verbatim (§7.7.2 p. 3313, §11.2.2 p. 3469, §11.4.2 p. 3482, §11.4.4.1 Table 11-1 p. 3486, §26.8 p. 4027, §34.5.1 p. 4322, §34.14.2 p. 4345).
- **Intel VT-d `5.20`:** §6.2.2.1 (`SSPTPTR`/`DID`/`CM=1`), §5.1.5.1 (remappable RTE and vector-match EOI), and ND encodings `000b..110b` match verbatim.
- **Arm `DDI 0487 M.d`:** Rule `IYNJCP` (`D8.17.8` p. 7909), broadcast TLB maintenance (`D8.17.8`), `B2.3.1` (`DMB`/`DSB FULL`), Rule `IWZCBG` (`D8.17` p. 7848), `C5.2.1` (`ALLINT`), and `B2.3` atomic acquire-release ordering match verbatim. (Opus missed the `B2.3.7` / `D12.2.2` counter-read ordering covered in Finding 8, which it separately found!)
- **PSCI `DEN0022F.b` & TF-A `v2.12.0`:** All PSCI error/status quotes (§5.6.2, §5.7.2, §5.9.1, §6.6) and TF-A SDEI files (`sdei_intr_mgmt.c`, `sdei_cpu_on_init`, `sdei_cpu_wakeup_init`, `sdei.rst`, `plat_ic_raise_el3_sgi`) match verbatim.
- **Linux (`v6.12` / mainline):** `adl_cstates` (`C6 = 220`, `C10 = 680`), `native_flush_tlb_multi` lazy CPU IPI when `info->freed_tables` is set, commit `e1c467e69040`, and `arch/arm64/kernel/smp.c` `arm64_nmi_cpu_stop()` comment match verbatim.
- **RISC-V:** `a-st-ext.html` §12.1 `.aqrl` quote and SBI `ext-hsm` (`STOPPED`, `SBI_ERR_ALREADY_AVAILABLE`, `sbi_hart_stop`) match verbatim.
- **Unopened sources (17 Nov 2026):** Arm GIC `IHI 0069` and TI `PC16550D` remain **Not opened** (`developer.arm.com` PDF gated / `ti.com` timeout); `docs.riscv.org/reference/sbi/v3.0/ext-ipi.html` returned HTTP 503 so canonical upstream `ext-ipi.adoc` (`riscv-non-isa/riscv-sbi-doc`) was read instead.
- **Note on Opus's arithmetic list:** Opus listed `"The ring sizes and the reserve of 34 answers"` as sound, though Finding 5 shows `FENCE_NS = 20 ms` did not fit in `CORE_ANSWER_NS = 10 ms` per reserve tick, and Finding 4 over-stated `LENn = 10` as reserved on x86-64 when Intel SDM §20.2.4 defines it as 8-byte watchpoints. Otherwise, all 14 of Opus's findings are **real** issues in the specification.

---

## Summary Table

| Finding | Verdict | Severity | Correction in one line |
|---|---|---|---|
| 1. Inter-core IPI / doorbell store ordering | **real** | breaks a guarantee | Add a store barrier (`MFENCE; LFENCE` / `DSB ISHST` / `fence w,o`) before every inter-core IPI at `l. 1083` (`kernel.md:183`) and acquire-read in the handler. |
| 2. Ring producer and consumer index ordering | **real** | breaks a guarantee | Require release stores and acquire loads on ring producer and consumer indices at `l. 968`. |
| 3. Seqlock and lock-free `signal` lack barriers | **real** | breaks a guarantee | Add odd-store-before-slot (`DMB ISHST` / `fence w,w`), even-store release, and reader acquire / `DMB ISHLD` / `fence r,r` barriers at `l. 668`. |
| 4. x86-64 `DR7` validation (`R/Wn = 10`, `LENn`, `CR4.DE`) | **real** | cannot be built as written | Sync `l. 477`/`1666` with `abi/src/x86_64.rs` to refuse `R/Wn == 10` (I/O), clarify `R/Wn == 00 && LENn != 00` invalid and `CR4.DE = 1` (8-byte `LENn = 10` is valid on Intel 64). |
| 5. Fence delays inside recovery reserve (`FENCE_NS = 20 ms`) | **real** | contradiction | Move INIT-SIPI-SIPI / fallback delays onto non-blocking due events (`l. 1306, 1313`) like `START_RETRY_NS` and raise `FENCE_NS` to at least `30 ms` (`l. 1505`). |
| 6. IOAPIC level masking & EOI across nodes | **real** | contradiction | Allow non-holder level-line claims only when IOAPIC supports Directed EOI (`l. 780, 797`, letting Remote IRR mask until `irq_ack` writes EOI `0x40`), else `unsupported`. |
| 7. VT-d blocking mode cuts off active RMRR / GOP | **real** | contradiction | Identity-map active RMRR ranges into kernel domain `D - 1` at start-up (`l. 341, 402, 2009`) and keep until first `iospace_attach` (matching `gpu.md:39-42`). |
| 8. Counter reads in `clock_now` and `now` lack barriers | **real** | breaks a guarantee | Order counter reads on both sides (`LFENCE; RDTSC; LFENCE` / `ISB; MRS CNTVCT_EL0; ISB` / `fence r,rw`) around the seqlock sequence reads at `l. 496`. |
| 9. `IOMMU_WAIT_NS = 1 ms` & completion check order | **real** | unsettled case | Re-read QI completion status *before* checking the deadline (`l. 1045`) and calibrate/raise `IOMMU_WAIT_NS` above firmware/queue burst stalls (`l. 393`). |
| 10. RISC-V omitted from grant Dekker pair & models | **real** | unsettled case | Specify RISC-V `fence rw,rw` / `amocas.aqrl` in the Dekker pair (`l. 914`) and add `RVWMO` to memory models (`l. 1813`, `kernel.md:35`). |
| 11. ARM64 cores with EL2 but without `FEAT_VHE` | **real** | unsettled case | Drop from EL2 to EL1 at start-up when `ID_AA64MMFR1_EL1.VH == 0` (`l. 1992`), forcing class 0 (`l. 1315`) because TF-A rejects EL1 SDEI. |
| 12. RISC-V ACLINT `MSWI` vs `SSWI` & CLINT-only harts | **real** | unsettled case | Name ACLINT `SSWI` (not `MSWI`) at `l. 1091, 1453` (`kernel.md:161`) and either refuse missing `SSWI`/IMSIC (`l. 2001`) or allow fallback to `sbi_send_ipi` (`kernel.md:163`). |
| 13. VT-d root and context table sizes reversed | **real** | wrong external fact | Fix `l. 341` to specify legacy translation mode with a `4 KB` root table and up to `256` context tables of `4 KB` (`1 MB` total). |
| 14. Console pacing outruns 16550 at 115,200 baud | **real** | wrong external fact | Change console due-event pacing at `l. 1653` to `1.5 ms` and write at most 16 bytes only while transmit status reads empty without spinning. |
