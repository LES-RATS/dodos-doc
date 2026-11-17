# Review V3 (Opus 5.5): kernel-interface.md, hardware and external facts

Document reviewed: `Docs/architecture/kernel-interface.md` (2,306 lines). I read all of it, from line 1 to line 2306, before writing the findings. As the brief asks, I opened no other file of the repository and did not look for the project on the web. The sources I checked are vendor documents and public code. Each one is named below with the place I read it.

Angle: can the text be built on real x86-64, ARM64 and RISC-V hardware, and are its outside facts true? I looked in particular at memory ordering between cores and at time limits.

Severity labels, as the brief defines them: **breaks a guarantee**, **cannot be built as written**, **contradiction**, **unsettled case**, **wrong external fact**.

Contract quotes are copied from the file. I removed only the Markdown emphasis marks (`**`, `*`).

Sources downloaded and read on 17 November 2026 (copies kept in my scratchpad):
- Intel SDM, combined volumes, order 325462-093 (title page: "Order Number: 325462-093US, September 2026"), from `https://cdrdv2.intel.com/v1/dl/getContent/671200`.
- Intel VT-d, revision 5.20, order D51397-019 ("April 2026, Revision 5.20"), from `https://cdrdv2.intel.com/v1/dl/getContent/671081`.
- Arm DDI 0487 M.d, `DDI0487M_d_a-profile_architecture_reference_manual.pdf`, from `https://documentation-service.arm.com/static/6abbec2a6db85c5e6614a4a1` (metadata: published 2026-09-29).
- Arm DEN0022F.b (PSCI), `https://documentation-service.arm.com/static/6703a8b8d7e4b739d817e10d`.
- Trusted Firmware-A at tag v2.12.0: `services/std_svc/sdei/{sdei_main.c,sdei_intr_mgmt.c,sdei_private.h}` and `docs/components/sdei.rst`, from `raw.githubusercontent.com/ARM-software/arm-trusted-firmware/v2.12.0/...`.
- Linux, from `raw.githubusercontent.com/torvalds/linux/...`:
  - at tag v6.12: `drivers/idle/intel_idle.c` and `arch/x86/mm/tlb.c`;
  - at master: `arch/arm64/kernel/smp.c`, `drivers/irqchip/irq-gic-v3.c`, `arch/x86/include/asm/processor.h`, `arch/x86/kernel/apic/x2apic_phys.c`, `arch/x86/include/asm/iommu.h`, `drivers/iommu/intel/dmar.c`, `arch/x86/include/asm/vdso/gettimeofday.h`, `arch/arm64/include/asm/arch_timer.h`, `arch/riscv/include/asm/mmio.h`;
  - commit `e1c467e69040` as a patch from github.com.
- RISC-V: `https://docs.riscv.org/reference/isa/v20260120/unpriv/a-st-ext.html` and `https://docs.riscv.org/reference/sbi/v3.0/ext-hsm.html`.

---

## Findings, most severe first

### 1. An interrupt can reach another core before the stores it announces are visible (breaks a guarantee)

**Lines:**
- l. 968: "A ring X → Y is mapped writable only in X's kernel and read-only in Y's (...); its writes are plain stores, not gate calls, since the receiver checks every message."
- l. 971: "(an interrupt of the kernel's own, sent through the gate to one core of the receiver when the ring goes from empty to not empty)".
- l. 1293, evidence stuck: "taken when the ring was not empty and after Y sent X an interrupt, and the consumer index still reads c with now − t ≥ STUCK_NS".
- l. 1083 (G10) and l. 1091 say how interrupts to other cores are sent: on ARM64 "ICC_SGI1R_EL1 and its aliases are written only by the gate"; on RISC-V "a store to the ACLINT's or the target IMSIC's registers".

No sentence of the contract orders the stores that come before an interrupt with the interrupt itself.

**The hardware facts:**
- x86-64 in x2APIC mode, SDM 325462-093 §13.12.3 "MSR Access in x2APIC Mode": "A WRMSR to an APIC register may complete before all preceding stores are globally visible; software can prevent this by inserting a serializing instruction or the sequence MFENCE;LFENCE before the WRMSR." Linux does exactly this with `weak_wrmsr_fence()` ("mfence; lfence"), whose comment in `arch/x86/include/asm/processor.h` says the barrier "is only required for the IA32_TSC_DEADLINE and X2APIC MSRs".
- ARM64 with GICv3: Linux `drivers/irqchip/irq-gic-v3.c`, `gic_ipi_send_mask`: "Ensure that stores to Normal memory are visible to the other CPUs before issuing the IPI." followed by `dsb(ishst)`. A DMB does not order a system-register write. I did not open the GIC specification (IHI 0069) for this sentence.
- RISC-V: an IMSIC or ACLINT register is an I/O region. Linux `arch/riscv/include/asm/mmio.h` puts `__io_bw()`, defined as `RISCV_FENCE(w, o)`, before every `writel`. Without that fence, earlier stores to ordinary memory are not ordered before the device store.

**Scenario (ARM64; x86-64 in x2APIC mode and RISC-V are the same):**
1. A thread of X calls `node_send` to Y. X's kernel writes the entries of the `Send` and the producer index of the user ring X → Y, both plain stores (l. 968).
2. The ring was empty, so the gate writes `ICC_SGI1R_EL1` to interrupt one core of Y. There is no DSB before it.
3. The SGI reaches Y's core before the producer index store is visible there. Y's event reads the old producer index, finds the ring empty and ends.
4. The ring now holds a message, and later messages do not take it "from empty to not empty", so no further interrupt is sent (l. 971). The kernel ring has the same flaw: the stuck evidence of l. 1293 counts on "after Y sent X an interrupt" for both rings.
5. The sending thread waits for its `SendAnswer`. `thread_cancel` does not end that wait (l. 1003).
6. X observes the ring and, after `STUCK_NS` (100 ms), the stuck evidence holds. X accuses Y and Y is fenced, though Y is healthy.

This breaks "A kernel that is wrong cannot accuse a healthy node" (l. 1287). Here neither kernel is wrong. Only the order is missing.

The same gap touches:
- the fence's NMI or SDEI signal sent after the fence mark is written. The handler can miss the mark and return (l. 1228); the fence only repeats, so this costs delay, not safety;
- the start request and its wake. Hidden by the retries every `START_RETRY_NS`.

Inside one node, the handler takes the node lock before its work (l. 687: "its wait for the lock and its work included"). The lock's acquire then orders the requester's stores, provided the handler reads its pending set after taking the lock. l. 677 ("it reads its pending set by a read with acquire order") does not say whether that read happens before or after the lock.

**Smallest correction (add to G10):** "Before the gate sends an interrupt to another core, it orders every earlier store before the interrupt: x86-64 in x2APIC mode `MFENCE; LFENCE` before the `WRMSR` to the ICR (SDM §13.12.3); ARM64 `DSB ISHST` before the write of `ICC_SGI1R_EL1`; RISC-V `fence w,o` before the store to the IMSIC or ACLINT register. A handler reads what the interrupt announces (a producer index, a pending set) with acquire order, after the interrupt is taken."

### 2. The ring indexes have no release and acquire order (breaks a guarantee)

**Lines:**
- l. 968: "its writes are plain stores", and "The producer index is in the ring's header, written by X only; the consumer index of each ring into Y is in Y's node beacon, written by Y only".
- l. 966: "A message that fails any of these changes nothing, is consumed, and is traced".
- l. 1003: the send's wait "ends at the answer, or with gone if the target is accused first (R0 (...)). thread_cancel does not end it."
- l. 972: credits.

Even when the interrupt is ordered (finding 1), the ring itself is two single-writer words over shared entries. On ARM64 (RVWMO is no stronger), plain stores can be observed out of order, and a load can be reordered after a later store.

**Scenario A (ARM64 or RISC-V):**
1. X writes a `Send` into entries k to k+9, then the producer index p+10.
2. Y observes the new producer index before the entries. Y reads entry k as it was 64 messages earlier.
3. Y's check sees an old header with a credit serial that is no longer in use. The message is consumed and traced (l. 966), and no `SendAnswer` is ever written.
4. The sender's thread waits for ever while Y lives (l. 1003), and the send credit stays in use (l. 972). After `SENDS_PER_PEER` such losses, every `node_send` to Y returns `busy`.

**Scenario B:**
1. Y copies a message, then advances its consumer index.
2. Y's loads of the entries can be satisfied after its store of the consumer index, so X sees the room freed and overwrites the entries.
3. Y copies a mix of two messages. The check may refuse it, with the loss of scenario A. Worse, it may accept a mix whose header is right and whose words are a later message's.

**Smallest correction (l. 968):** "X stores the producer index with release order after the entries; Y loads it with acquire order before it reads them; Y stores its consumer index with release order after its last read of the consumed entries; X loads it with acquire order before it reuses them (x86-64 plain moves; ARM64 `STLR`/`LDAR`; RISC-V `fence rw,w` before the store, `fence r,rw` after the load)." The formal model at l. 1813 lists "x86-TSO and the Armv8 memory model". RVWMO should be added.

### 3. The lock-free slot read has no read or write barriers, and `signal` acts on it without the lock (unsettled case; as written, it breaks containment inside the node)

**Lines:**
- l. 668: "The lookup of a call reads the sequence word of the slot's segment (...), the slot, then the sequence word again, and reads them once more if a writer was active (...). A writer of a slot holds the node lock and makes the sequence word of its segment odd while it writes, even again after."
- l. 669: "signal sets its bits by one atomic OR on the notify's word, then reads whether a thread waits (...), and returns without the lock if none does".

The text gives the ordering of the signal against a waiter and against a bind (l. 669), with barriers and sources. It gives none for the sequence lock itself. Under the Armv8 model (Arm DDI 0487 M.d, B2.3, "Barrier-ordered-before" lists the DMB, DMB LD, DMB ST and acquire/release cases, and plain loads are in none of them) and under RVWMO:
- the reader's two loads of the sequence word can be satisfied around its loads of the slot;
- the writer's store that makes the word odd can become visible after its stores of the slot.

**Scenario (ARM64):**
1. Core b holds the node lock. It deletes the notify capability in slot s, then moves a thread capability into s. Each write makes the segment's word odd, then even.
2. Core a runs `signal` on s without the lock. It reads the word as v twice, but its slot loads return word 0 of the old capability (kind `notify`, right `send`) and word 1 of the new one (the address of a thread object).
3. Core a ORs the badge into what it takes for the notify's word, which is a word of the thread object.
4. No thread waits, so a returns without the lock (l. 669). The re-check of the sequence words "once it holds the lock" (l. 668) never runs.

The D-138 barrier (l. 673-679) covers memory that is reused after a destruction, not a torn read of a live slot.

**Smallest correction (l. 668):** "The writer makes the word odd, then orders that store before the slot stores (ARM64 `DMB ISHST`, RISC-V `fence w,w`), and makes the word even with release order. The reader loads the word with acquire order, loads the slot, orders those loads before its second load of the word (ARM64 `DMB ISHLD`, RISC-V `fence r,r`), then loads the word again. On x86-64 only the compiler's order is needed." The small model at l. 1813 must run under RVWMO as well.

### 4. x86-64: a bit mask cannot refuse an I/O breakpoint, and an I/O breakpoint fires in the kernel (cannot be built as written; a holder of `write` on a thread can kill the node)

**Lines:**
- l. 477: "the breakpoint control word must have no bit outside its user mask (invalid, judged word by word in order)".
- l. 1666: "a control word with a bit outside the architecture's user mask (in abi/) is invalid, so a thread can never watch a kernel address or an I/O port".
- l. 1666: "The kernel saves and restores a thread's debug registers only when its control word enables one".

**The hardware facts:**
- SDM 325462-093 §20.2.4 "Debug Control Register (DR7)": with CR4.DE set, R/Wn "10 — Break on I/O reads or writes"; with DE clear, "10 — Undefined".
- §20.3.1.2: "Data memory and I/O breakpoints are reported when the processor attempts to access a memory or I/O address specified in a breakpoint-address register (DR0 through DR3) that has been set up to detect data or I/O accesses (R/W flag is set to 1, 2, or 3)." Nothing ties this to the privilege level.

A mask that allows write watchpoints (01) and read/write watchpoints (11) must allow both R/W bits, so it also allows 10. The address check does not help: a port number such as 0x3F8 lies in the user range.

**Scenario:**
1. A process suspends one of its own threads W and calls `thread_write_regs` with DR0 = 0x3F8, L0 set and R/W0 = 10. Every bit is inside the mask, and the address is in the user range.
2. It resumes W.
3. While W runs, a timer interrupt lets the console role holder write the UART at port 0x3F8 (l. 1653). Or W calls `ioport_in`, which the gate executes (l. 1687).
4. With CR4.DE = 1, the `out` or `in` raises #DB in kernel mode, inside the gate. With CR4.DE = 0 the behaviour is undefined.
5. A #DB in kernel mode is "an unexpected exception in kernel mode" (l. 1291). The node accuses itself, and every process of the node is lost.

**Smallest correction (l. 477 and l. 1666):** "The control word is judged field by field: an R/Wn or LENn field of 10 is invalid, and so is GD (bit 13). The kernel runs with CR4.DE set, so that 10 has a defined meaning and is refused."

### 5. The fence's repetitions and delays cannot keep their timing inside the recovery reserve (contradiction)

**Lines:**
- l. 1306: the driver "runs the fence in its recovery reserve (below), in steps".
- l. 1309: "Wait at most NMI_GRACE_NS" (1 ms, l. 1504).
- l. 1311: "10 ms after INIT and 200 µs between the two SIPIs".
- l. 1313: "The driver repeats steps 1 to 3 every millisecond for a core not yet confirmed, until it is or FENCE_NS has passed".
- l. 1359: the reserve has "bandwidth 1/64 of a core (...), period 10 ms".
- l. 1511: "156 µs of each 10 ms".
- l. 1505: `FENCE_NS` is 20 ms, "Time for the NMI grace, INIT, the two SIPIs after the delays of the SDM's example (10.2 ms), the stub and its repetitions".

The SDM delays are real: SDM §11.4.4.1, Table 11-1 "Broadcast INIT-SIPI-SIPI Sequence and Choice of Timeouts" has "10-millisecond delay loop" and "200-microsecond delay loop". A step that must wait ends, though, and a throttled reserve on a fully loaded node runs again only at its next replenishment, 10 ms later. The text gives slack only to time that "no context with budget wants" (l. 593).

**Scenario (x86-64, a core whose kernel cannot run its NMI handler, the case INIT exists for):**
1. NMI at t0.
2. INIT at the next activation, t0 + 10 ms.
3. First SIPI at about t0 + 20 ms.
4. `FENCE_NS` has then passed, so the node becomes unfenced. Its memory and the frames granted to it are frozen until the machine restarts (l. 1252).

"Every millisecond" also cannot coexist with a round that itself lasts more than 10 ms. D-135 fixed the same flaw for starts (l. 1228: sent from the reserve, the wakes "went out every 10 ms, not every 1 ms").

**Smallest correction (l. 1306 and l. 1313):** "The fence's waits (`NMI_GRACE_NS`, the INIT-to-SIPI delay, the SIPI gap) and its repetitions are due events of the driver's first core's timer queue, as the retries of a start are; a round is repeated when the previous one has ended without a confirmation." Then check `FENCE_NS` against two rounds.

### 6. Masking a level line needs the IOAPIC's role holder, yet "an arrival never involves the role holder" (contradiction; unsettled on machines without directed EOI)

**Lines:**
- l. 780-781, an arrival: "1. If the source is a level source, it is masked at the controller. 2. The interrupt controller is acknowledged (end of interrupt)."
- l. 797: "The inputs of an IOAPIC are programmed through an index and a data register, so they have one writer, the holder of the IOAPIC's role (...) Where the local APIC suppresses the broadcast of the end of interrupt and the IOAPIC has an EOI register, a level line is acknowledged from the claiming core by one write of the vector into that register; otherwise the masking and unmasking of a level line are requests to the role holder, slower and still correct."
- l. 816: "An arrival never involves the role holder."
- l. 787: "The work of the interrupt path is constant".

**Two problems:**
- In the "otherwise" case, step 1 of an arrival on a node that does not hold the IOAPIC role is a unit request, which contradicts l. 816 and l. 787.
- It is not "still correct". If the core sends the LAPIC end of interrupt (step 2) before the mask is done, the broadcast EOI clears the IOAPIC's Remote IRR. The line is still asserted, so it is delivered again at once. That gives a storm on the claiming core for as long as the request takes, up to "two such periods" of the reserve, 20 ms (l. 971). If instead it holds the EOI back, every vector of equal or lower priority on that core is blocked for the same time.

Even with directed EOI, the text never says that the "mask" of step 1 is the Remote IRR left set until `irq_ack` writes the IOAPIC's EOI register. An implementer who reads l. 780 literally masks the redirection entry, which only the holder may write.

**Smallest correction (l. 780 and l. 797):**
- "On x86-64 a level line of an IOAPIC whose role the node does not hold is claimable only where directed EOI is possible (flag bit 2 of `Interrupts`). Its arrival masks nothing: the LAPIC end of interrupt is sent with the broadcast suppressed, the line stays held by its Remote IRR, and `irq_ack` and a bind write the vector into the IOAPIC's EOI register."
- "Otherwise `irq_claim` of such a line is `unsupported` unless the node holds the IOAPIC's role."

### 7. Blocking every device at machine start-up cuts off firmware-owned DMA to RMRR regions (cannot be built as written on machines with RMRRs)

**Lines:**
- l. 2009: machine start-up "turns every IOMMU unit on in blocking mode".
- l. 341: "By default every device is blocked".
- l. 402: RMRR regions are mapped by "the driver's node (...) into the iospace of its device (...) before the device is attached".
- l. 1979 and l. 2081: the framebuffer is handed over and published (entry `Framebuffer`).

**The hardware facts:**
- VT-d 5.20 §3.16 "Handling Requests to Reserved System Memory": "For proper functioning of these legacy reserved memory usages, when system software enables DMA remapping, the second-stage translation structures for the respective devices are expected to be set up to provide identity mapping for the specified reserved memory regions". The same section names "DMA from unified memory access (UMA) graphics controllers to graphics reserved memory" and "DMA performed by a USB controller under BIOS SMM control for legacy keyboard emulation".
- §3.4.4 "Abort DMA Mode": "System software should not program remapping hardware in abort-dma mode if devices are active that require access to the reserved memory region as reported through RMRR".

**Scenario (an Intel machine with integrated graphics):**
1. The first stage hands over the GOP framebuffer.
2. At step 2 of machine start-up the unit blocks the graphics device. Its display engine scans the framebuffer out of stolen memory, an RMRR range, by DMA, and that DMA is now refused.
3. The framebuffer goes dark, and DMA faults are logged as code 2 until a graphics driver attaches.

The same happens to SMM's USB legacy keyboard. The reference desktop's i5-14600KF has no integrated graphics, which hides this there. Other machines with integrated graphics would be affected.

**Smallest correction:** either "the machine start-up reads the RMRR entries of the DMAR as well and attaches each listed device to the unit's kernel domain (number D − 1, l. 1030) with an identity map of its regions, read and write, until its first `iospace_attach`", or a sentence that says the framebuffer and SMM-owned USB stop at machine start-up. The first option conflicts with the reason given at l. 402 ("a region the kernel mapped by itself would be a translation no record names"). The kernel already makes such an exception for the stub-link device (l. 343), so it fits.

### 8. The counter read in `clock_now` and in `now` has no ordering (unsettled case; breaks the cross-core guarantee of l. 500 if implemented as written)

**Lines:**
- l. 496: "A reader reads the sequence word, the parameters, the counter, then the sequence word again, and starts over if the word was odd or has changed".
- l. 500: "A value read on one core, then sent by any means to another core, is never greater than a value read afterwards on that core."
- l. 497: the kernel's `now` uses "the same value".

**The hardware facts:**
- SDM 325462-093, instruction page "RDTSC—Read Time-Stamp Counter": "The RDTSC instruction is not a serializing instruction. It does not necessarily wait until all previous instructions have been executed before reading the counter." The same page then advises LFENCE before RDTSC. Linux's x86 vDSO uses `rdtsc_ordered()` (`arch/x86/include/asm/vdso/gettimeofday.h`).
- Arm DDI 0487 M.d, D12.2: "Reads of CNTVCT_EL0 can occur speculatively and out of order relative to other instructions executed on the same PE." Linux reads it as `isb; mrs cntvct_el0`, or `CNTVCTSS_EL0` with FEAT_ECV (`arch/arm64/include/asm/arch_timer.h`).

**Scenario:**
1. Core a reads the clock as T and stores it to a shared word.
2. Core b loads that word, then calls `clock_now`.
3. b's counter read executes before its load of the word (x86-64: RDTSC is not ordered after earlier loads; ARM64: speculative). b reads a value smaller than T.

A reader can also mix a counter read from before an update of `ns_base` (l. 499, at resume) with parameters from after it.

**Smallest correction (l. 496):** "The counter is read after the parameters and before the second read of the sequence word, in order: x86-64 `LFENCE; RDTSC` (or `RDTSCP`), ARM64 `ISB` then `MRS CNTVCT_EL0` (or `CNTVCTSS_EL0` where FEAT_ECV exists), RISC-V `fence` as the architecture layer states; the loads of the sequence word are acquire loads."

### 9. `IOMMU_WAIT_NS` = 1 ms declares a unit failed for ever, but no specification bounds an invalidation, and the order of the last check is unstated (unsettled case; timing)

**Lines:**
- l. 393: "The bound is IOMMU_WAIT_NS (1 ms, provisional) from the submission to the unit. A unit that has not confirmed by then has failed".
- l. 393: "it checks for the confirmation at each later step of its recovery reserve, or at the unit's completion interrupt".
- l. 1045: "answers done at the confirmation and failed at IOMMU_WAIT_NS".
- l. 396-398: what follows is frozen until the machine restarts.

**The facts:**
- VT-d 5.20 sets no completion time for IOTLB or interrupt-entry-cache invalidations. The only timeout it defines is for device-TLB invalidation, where "The invalidation completion time-out value is recommended to be sufficiently larger than the PCI Express read completion time-outs" (§4.3, "Handling of Device-TLB Invalidations").
- Linux `qi_submit_sync` (`drivers/iommu/intel/dmar.c`) spins on the wait descriptor with no time limit.
- For register-based operations Linux uses `DMAR_OPERATION_TIMEOUT ((cycles_t) tsc_khz*10*1000)`, that is 10 s (`arch/x86/include/asm/iommu.h`).

**Scenario:**
1. A healthy but slow unit, or a holder stalled in system management mode, misses 1 ms.
2. The holder's next look comes at a reserve step, up to 10 ms later under load.
3. If the holder judges the deadline before it reads the status, it writes *failed*.
4. Every device of the unit and the barrier of every node with a device behind it are then frozen until restart (l. 398).

**Smallest correction (l. 393):**
- "The holder judges failure only after a read of the completion status that still shows the request incomplete at or after the deadline."
- `IOMMU_WAIT_NS` becomes a value measured per machine, with a range like the other times of `BootMembership`, rather than a constant of 1 ms.

### 10. RISC-V is missing from the orders of the grant counter and from the formal models (unsettled case)

**Lines:**
- l. 914: "Each side writes its own word by compare-and-swap and then reads the other's (on ARM64 the compare-and-swap has release and the read acquire semantics), so at least one sees the other".
- l. 1813: "under x86-TSO and the Armv8 memory model".

The ARM64 sentence is right. Arm DDI 0487 M.d, B2.3, "Barrier-ordered-before": "E1 is an Explicit Memory Write Effect with Release semantics. E1 appears in program order before E2. E2 is an Explicit Memory Read Effect with Acquire semantics." On x86-64 a locked compare-and-swap is a full barrier (SDM §11.2.2, quoted correctly at l. 669).

RISC-V is not named. A compare-and-swap built from LR/SC with only `.rl`, or `amocas` without `.aqrl`, followed by a plain load gives no store-to-load order under RVWMO. Then neither side sees the other: Y maps under a grant that X has freed.

**Smallest correction (l. 914):** "(...; on RISC-V the compare-and-swap is `.aqrl`, or is followed by `fence rw,rw`)". Add RVWMO to the models of l. 1813.

### 11. ARM64 cores with EL2 but without FEAT_VHE (unsettled case)

**Lines:**
- l. 1315: "The kernel runs at the highest non-secure exception level the machine offers (EL2, with the virtualization host extensions, where EL2 exists; EL1 otherwise), because SDEI requires its client to execute at that level".
- l. 1992: "the kernel sets the virtualization host extensions itself".

TF-A v2.12.0 `sdei_private.h`, `sdei_client_el()`: "If EL2 is implemented (hence the enabled HCE bit), deem EL2; otherwise, deem EL1". `sdei.rst` says calls are allowed only from "EL2, if EL2 is implemented".

On an Armv8.0 core with EL2 and no VHE, the kernel cannot run user threads at EL0 under the EL2 regime, so it must run at EL1. SDEI then refuses its calls, so its cores are of class 0, and the machine runs one node (l. 1317).

The text never states this case.

**Smallest correction (l. 1315):** "A core with EL2 but without FEAT_VHE runs the kernel at EL1 and is of fence class 0 (TF-A accepts SDEI calls from EL2 only when EL2 is implemented)."

### 12. RISC-V machines without an S-mode way to send an interrupt (unsettled case)

**Lines:**
- l. 329: "RISC-V uses the kernel's own interrupt rather than the SBI remote fence".
- l. 1091: the interrupt is "a store to the ACLINT's or the target IMSIC's registers".
- l. 2208 lists "APLIC, IMSIC, Sstc".

A RISC-V machine with only a machine-mode CLINT has neither an S-mode ACLINT software-interrupt device nor an IMSIC. It can send an interrupt to another hart only through SBI. The text does not say whether the machine start-up refuses it or falls back to SBI.

**Smallest correction (l. 2001, the refusals):** add "or, on RISC-V, the harts have neither an IMSIC nor an ACLINT supervisor software-interrupt device".

### 13. VT-d table sizes reversed (wrong external fact)

**Line:** l. 341: "(root and context tables, 1 MB and 4 KB per unit on x86-64)".

VT-d 5.20 §3.4.2: "The root-table is 4-KByte in size and contains 256 root-entries", and "Each context-table contains 256 entries". A context table is therefore 4 KB per bus, so 256 buses need up to 1 MB. The order in the text gives the root 1 MB.

**Correction:** "(a 4 KB root table and up to 256 context tables of 4 KB, 1 MB, per unit on x86-64, in legacy mode)".

### 14. Console pacing outruns a 16550 at 115,200 baud (wrong external fact, minor)

**Line:** l. 1653: "a due event every 1 ms (...) at which it writes at most 16 bytes; that matches a 16550's transmit queue at 115,200 baud".

At 115,200 baud with 8N1 framing a byte takes 10 bits, so the line carries 11,520 bytes per second. 16 bytes take about 1.39 ms. At 16 bytes per millisecond the FIFO fills unless each write waits for the "transmitter holding register empty" status. The text says the kernel "polls its transmit status" (l. 1632), which prevents loss, but then the rate is not the one claimed.

**Correction:** "every 1.5 ms" or "at most 16 bytes, once the transmit FIFO reads empty".

---

## What I checked and found sound

Intel SDM 325462-093:
- The edition exists as named.
- §7.7.2 "NMI Blocking": the quoted sentence, l. 1309.
- §11.2.2: "Reads or writes cannot be reordered with I/O instructions, locked instructions, or serializing instructions", l. 669.
- §11.4.2: the BSP-flag sentence, l. 1310. The SDM has it as "each logical processor examines its BSP flag (in the IA32_APIC_BASE MSR)".
- §11.4.4.1, Table 11-1: 10 ms and 200 µs, l. 1311.
- §26.8: "The INIT signal is blocked whenever a logical processor is in VMX root operation".
- §34.5.1: INIT operations "are inhibited when the processor enters SMM".
- §34.14.2: "blocked after RSM if and only if the logical processor will be in VMX root operation".
- The section numbers the contract gives match this edition.

VT-d 5.20:
- The edition exists.
- §6.2.2.1: both quotes, the SSPTPTR/DID sentence and "Software must not use domain-id value of 0 (...) CM=1", l. 1030.
- §5.1.5.1: the remappable RTE layout (index bits 63:49 and bit 11, bit 48, bits 10:8 000b) and the vector-match sentence for EOI broadcast, l. 1039.
- The interrupt-entry-cache descriptor has the G, IIDX and IM fields, l. 1038. I did not re-read the bit positions.
- The ND encodings 000b to 110b, 4-bit to 16-bit domain-ids, l. 1030. The text wraps over lines in my extraction.

Arm DDI 0487 M.d:
- The edition exists, published 2026-09-29.
- D8.17.8 rule IYNJCP: the sentence "only guaranteed to be finished for a PE other than PEx after the execution of DSB by the PEx".
- The broadcast sentence "A TLB maintenance instruction executed by a PE causes a TLB maintenance operation to occur on each PE within the..." is present.
- B2.3.1: "A TLBI Effect E1 is a Completed TLBI Effect if E1 appears in program order before a DSB FULL Effect".
- D8.17, rule IWZCBG: "an entry that generates one of the listed faults is never cached in a TLB".
- C5.2.1 `ALLINT`: "with or without Superpriority, is masked".
- B2.3: the write of an atomic with acquire and release semantics is barrier-ordered-before every later access, as l. 669 says. The text is "E1 is an Explicit Memory Write Effect with Release semantics. E3 and E1 are generated by an atomic instruction. E3 is an Explicit Memory Read Effect with Acquire semantics. E1 appears in program order before E2".
- I matched the sentences, not every section number.

PSCI DEN0022F.b:
- ALREADY_ON and ON_PENDING (§5.6.2).
- "could be in flight at the same time" (§5.7.2).
- OFF for "the core has not been booted yet" (§6.6).
- "Multiprocessor (MP) capable or not present" and "Any core can be hot unplugged without first asking the Trusted OS" (§5.9.1).

TF-A v2.12.0:
- "This PE is masked. We EOI the interrupt, as it can't be delegated" (`sdei_intr_mgmt.c`).
- `sdei_cpu_on_init` clears the private events and masks the PE, subscribed to `psci_cpu_on_finish`.
- `sdei_cpu_wakeup_init` masks the PE, subscribed to `psci_suspend_pwrdown_finish`.
- `sdei.rst`: "fails to complete the event handling, it might result in UNPREDICTABLE behavior".
- Event 0 is raised as an EL3 SGI by `plat_ic_raise_el3_sgi`.

Linux:
- v6.12 `adl_cstates`: C6 `exit_latency = 220`, C10 `exit_latency = 680`.
- v6.12 `native_flush_tlb_multi` sends the IPI to lazy CPUs when `info->freed_tables` is set.
- Commit `e1c467e69040` is "x86, hotplug: Wake up CPU0 via NMI instead of INIT, SIPI, SIPI".
- Master `arch/arm64/kernel/smp.c` has `arm64_nmi_cpu_stop()`, whose comment contains "a CPU_OFF from that not-yet-completed context wedges EL3 on some firmware".

RISC-V:
- The A-extension sentence on `.aqrl` at the URL given at l. 669.
- SBI v3.0 HSM: STOPPED "is not executing in supervisor-mode or any lower privilege mode"; `SBI_ERR_ALREADY_AVAILABLE` "The given hartid is already started"; `sbi_hart_stop` stops "the calling hart".

Arithmetic and internal consistency:
- `RFLAGS_USER_MASK` 0x0024_0DD5 is exactly CF, PF, AF, ZF, SF, TF, DF, OF, AC and ID.
- The handle limit of 341 cores: 341 × 192 > 65,536 − 192.
- 65,536 identifier words of 8 bytes make 512 KB.
- The firing-instant rule of l. 634 gives the value with the most trailing zeros in [deadline, x].
- The ARM64 16 KB granule on three levels gives 47 bits (14 + 3 × 11).
- The ring sizes and the reserve of 34 answers.

Cross-core orders the text does state:
- The bind's `MFENCE` / `DMB ISH` / `fence rw,rw`, and the signal's ordered OR (l. 669): sound on all three architectures.
- The barrier's acknowledgement by `LDSETAL` / `amoor.d.aqrl` (l. 677): sound.
- The grant Dekker pair on x86-64 and ARM64 (l. 914): sound. RISC-V is finding 10.
- Inside one node, everything written and read under the node lock is ordered by the lock.

## What I did not check

Not opened:
- the GIC specification (IHI 0069): the `GICD_TYPER` fields, the extended PPI and SPI ranges, the non-secure view of `ICC_PMR_EL1`, and the DSB requirement of finding 1. For that requirement I relied on Linux's code and comment;
- ACPI, for the MADT GICC power-efficiency byte at offset 76;
- the RISC-V AIA, for the IMSIC's limit of 2,047 identities;
- the RISC-V privileged specification 1.13 and Zicfilp/Zicfiss, for the `scause` codes and the `stval` values;
- the Zephyr and QEMU links of l. 813;
- the seL4 clustered multikernel PDF;
- the `df.lth.se` register mirror;
- gdb's `x86-xstate.h`;
- the OpenSBI and isa-dev mails of l. 1698;
- the Linux 7.3 constants.

Not re-read:
- the ARM64 `ESR_ELx.EC` and fault-status values of the fault tables (l. 447-459);
- the remapped MSI address formula of l. 813 against VT-d §5.1.5.2. It agrees with what I recall of that format, from memory.

Not judged here:
- whether 10 ms (`CORE_ANSWER_NS`), 100 ms (`STALE_NS`) and 1 ms (`SETTLE_NS`) suffice on real firmware. The text marks them to measure, and I have no measurement;
- the posted-write assumption behind `SETTLE_NS` (l. 1487), which the text names as its one untested hardware assumption;
- logic that does not touch hardware (rights, derivation, scheduling), which is outside this angle.
