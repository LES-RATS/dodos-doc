# Security and Contract Review of `kernel-interface.md`

Target reviewed: `/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md` (lines 1-2307).
All findings are grouped by the attacker role used to reach them. Every quoted rule is verbatim from that file with its line number.

---

## Findings

### Attacker 1: User process with a few capabilities

#### Finding 1 — Moving a lent scheduling context via `sched_configure` lets one context run on two cores at once
- **Severity:** breaks a guarantee
- **Lines:**
  - Line 183: "`thread_cancel` | thread, wait number | `manage`. ... A wait that is ended: the thread is taken out of its queue (of an endpoint, of a notify) and its call returns `cancelled`; a reply object it was attached to, or that was armed with it, becomes idle, so a later answer is dropped as for any reply object that is not armed."
  - Line 511: "A thread is **runnable** when it is not suspended, does not wait, and is not marked *leaving its core* ([A node of several cores](#a-node-of-several-cores)); the event that clears the mark makes its context eligible on the core where the context is now placed (D-131: the eighth review found a context moved by `sched_configure` chosen on its new core while its old core still ran it)."
  - Line 512: "The **holder** of a context is the one thread that may run on it (rule below). A context is **eligible** when it is configured, not dying, and its holder is runnable."
  - Line 522: "core | The core of its node where it is placed: it is admitted in that core's sum and queued there ([A node of several cores](#a-node-of-several-cores))"
  - Line 539: "`sched_configure` | sched, node, core number, budget, period, class | | ... A core other than the one where the context is placed moves it there (D-129, [A node of several cores](#a-node-of-several-cores))"
  - Line 565: "A context is in at most one of them."
  - Line 609: "**A lend is made when a call is delivered** to a receiver that has no own context (a **passive** receiver), if the caller's context exists and is not dying."
  - Line 611: "**The holder.** The holder of a context is: its home, if the home is runnable; otherwise the receiver of the top lend, if the chain is not empty; otherwise none."
  - Line 612: "**An answer does not release a lend, nor does the end of the caller's wait by `thread_cancel` (design choice).**"
  - Line 664: "An event on core *a* that makes a context placed on core *b* eligible (a signal, a delivery, an answer, a timer, an interrupt arrival) puts it into *b*'s queues; if it should take *b* (*b* is idle, or the context's deadline is earlier than that of the context *b* runs), *a* sends *b* the kernel's reschedule interrupt through the gate (G10)."
  - Line 692: "So a call that must stop such a thread (suspend it, destroy it, revoke its task, move its context to another core) marks it **leaving its core** and sends *b* the kernel's leave interrupt; at that interrupt *b* saves the thread's registers into the thread object, stops running it and clears the mark, which makes its context eligible again if its holder is runnable ([What runs next](#what-runs-next)). ... `sched_configure` that moves a context waits for nothing, and its holder runs on the new core once the mark is clear. ... `thread_cancel` never waits for another core: it ends a wait, and a thread that waits runs on no core"
- **Scenario (2+ cores in one node):**
  1. Client thread `T` (home of scheduling context `S`, placed on core `a`) executes `call` to a passive server `P` (`call` at line 202, lend at line 609). `T` waits for the reply; `P` becomes holder of `S` (line 611) and runs on `S` on core `a` (line 662).
  2. Another thread of the process on core `b` calls `sched_configure(S, node, c, ...)` to move `S` to core `c` (lines 539, 692). The kernel marks `P` (the thread running on core `a`) as *leaving its core*, queues the leave interrupt to `a`, and updates `S`'s placement to core `c` (lines 522, 692).
  3. Before core `a` handles the leave interrupt (while `a` is still running `P` in user mode on `S`), core `b` calls `thread_cancel(T, 0)` (line 183) — or another server thread answers `T` via `send` on `P`'s reply object (line 205) or destroys the reply object (`cap_delete`, line 132). By line 692, `thread_cancel` never waits for another core because `T` is waiting and not running on `a`.
  4. `T` stops waiting and was never marked *leaving its core* (only `P` was). Therefore `T` is now *runnable* (line 511).
  5. By line 611, `T` (home of `S`) immediately replaces `P` as the holder of `S`, even though `S` still has `P` running on core `a` and `P` is still marked *leaving its core*.
  6. Because `T` is runnable, `S` is eligible (line 512) and placed on core `c` (lines 522, 539, 664). Core `b` sends a reschedule interrupt to `c` (line 664), and core `c` schedules and runs `T` on `S` while core `a` is still running `P` on `S`.
  7. Both core `a` (at its next event entry/exit, lines 577, 580, 582) and core `c` read and mutate `S`'s `remaining`, `consumed`, and sorted-queue links (`S` can be inserted into both `a`'s and `c`'s queues, violating line 565).
- **Smallest correction:** Record *leaving its core* (or a *leaving* core index) on the scheduling context itself as well as on the thread running on the old core, and keep the context ineligible (not runnable/choosable on the new core) in lines 511-512 and 692 until the old core clears that mark at its leave interrupt.

#### Finding 2 — `aspace_map` and `iospace_map` exceed the 64 KB single-call clearing bound on ARM64 with 16 KB pages
- **Severity:** contradiction / cannot be built as written
- **Lines:**
  - Line 98: "A count of bytes that bounds the work of one step (the clearing step of 64 KB, a segment of a `cspace`) stays in bytes and does not change with *P*."
  - Line 99: "So a 64 KB page (ARM64's largest granule, 8,192 entries per table) is refused: on such a processor the kernel takes its 16 KB or 4 KB granule, by the rule of D-121."
  - Line 103: "A run of at most *E* pages crosses at most 2 tables at each level below the root, so a mapping call takes at most 2 × (*L* − 1) tables."
  - Line 167: "If the clean mark is below that end, the call clears from the clean mark at most 64 KB (provisional), stopping at the end of the new object if it comes first, and moves the clean mark to where it stopped; if the end is still not reached, it returns `again` and makes nothing."
  - Line 168: "**The padding is cleared with the object (design choice).** The memory between the watermark and the aligned start of the new object is below the end, so it is cleared too."
  - Line 170: "The tables of an address space and the segments of a capability space are taken by `aspace_map`, `iospace_map` and `cspace_grow` by the same rule. Those calls take at most 2 × (*L* − 1) tables (6 tables, 24 KB, on the reference machine) or one segment (8 KB), a constant of the machine, so they clear within the call and never return `again`."
  - Line 266: "A table is one page, taken at the watermark (aligned on a page) and cleared by the rule of the clean mark."
  - Line 2195: "So ARM64 with 16 KB pages uses 47 bits on three levels: at stage 1 a 48-bit space needs a fourth level whose root holds 2 entries"
- **Scenario:**
  1. On ARM64 using the 16 KB page granule (explicitly supported by lines 99 and 2195), *P* = 16 KB and *L* = 3.
  2. A user process creates one small object, such as a 64-byte `endpoint` (lines 671, 1915), in a dirty `untyped`. This advances both the watermark and the clean mark to byte offset 64 (lines 164, 167, 168).
  3. The process then calls `aspace_map` across a boundary requiring the worst-case `2 × (L − 1) = 4` missing page-table pages (line 103).
  4. By line 266, each table is aligned on a page (16 KB). Clearing the alignment padding from byte 64 to byte 16,384 (16,320 bytes, line 168) plus the 4 tables (4 × 16 KB = 65,536 bytes) requires clearing 81,856 bytes (`80 KB − 64 B`) before the last table is ready.
  5. By lines 98 and 167, one call clears at most 64 KB, so clearing cannot finish in one call. That directly contradicts line 170 ("so they clear within the call and never return `again`"), and `aspace_map` (lines 274-295) defines no `again` return for table clearing (only for `> E` chunks in G3).
- **Smallest correction:** Either size the clearing step as `max(64 KB, P × (2 × L − 1))` (with `80 KB` for 16 KB pages at *L* = 3), or explicitly allow `aspace_map` and `iospace_map` to advance the clean mark and return `again` when clearing tables on *P* > 4 KB.

---

### Attacker 2 & 4: Driver process with a device, and device doing DMA or raising interrupts

#### Finding 3 — Remote-node level-line interrupts cause an infinite interrupt storm and lack wait/`again`/`busy` rules in `irq_bind` and `irq_ack`
- **Severity:** breaks a guarantee / contradiction
- **Lines:**
  - Line 196: "Three more waits hold no queue of an object (D-131): ... **waiting for a unit**, for the confirmation of a unit request ([Devices and shared hardware](#devices-and-shared-hardware)), which ends at the confirmation, with `busy` when the unit is found failed"
  - Line 775: "`irq_bind` | irq, notify | ... Otherwise the irq is armed and a level source is unmasked. Unbinding makes the irq idle, masks a level source and keeps pending."
  - Line 776: "`irq_ack` | irq | ... Otherwise the irq is armed and a level source is unmasked"
  - Line 780: "1. If the source is a level source, it is masked at the controller."
  - Line 781: "2. The interrupt controller is acknowledged (end of interrupt)."
  - Line 787: "**The work of the interrupt path is constant (design choice).** One table lookup, at most one controller write to mask, one end of interrupt, at most one thread woken, one mix into the entropy pool. There is no loop and no queue."
  - Line 789: "**An interrupt is signalled once until it is acknowledged.** This is what bounds an interrupt storm."
  - Line 791: "Each irq bound to it is unbound, as by `irq_bind` with notify 0 (idle, level source masked, pending kept)."
  - Line 797: "A line can be claimed through the `irq_control` of any node, on one of its cores. ... Where the local APIC suppresses the broadcast of the end of interrupt and the IOAPIC has an EOI register, a level line is acknowledged from the claiming core by one write of the vector into that register; otherwise the masking and unmasking of a level line are requests to the role holder, slower and still correct."
  - Line 971: "**Latency:** under full load a message of the kernel ring waits at most one period of the recovery reserve (10 ms) before it is served, an answer included, so a unit request takes two such periods"
  - Line 1043: "The table is served oldest first: an entry is sent when the role word reads held by a live node and a request credit toward that node is free, with the epoch the word then holds. A call that finds no free entry returns `again` with nothing changed"
  - Line 1082: "The registers of a unit are mapped only in the gate view of the node its role word reads held by, or names as target of a handing ([Roles](#roles))."
  - Line 1770: "`Again`, with nothing changed, is a new result of `untyped_retype`, `memory_give` and `memory_split` for the barrier of a watermark, in the rows above (D-138), and of `iospace_unmap`, `iospace_attach` and `irq_claim` when the unit request table is full"
- **Scenario A (Interrupt storm across nodes):**
  1. A driver on node `D` claims a level-triggered line on one of `D`'s cores while another node `H` holds the controller's unit role (an IOAPIC without EOI-broadcast suppression or EOI register, an ARM64 GIC distributor SPI, or a RISC-V APLIC domain line; lines 797, 1453).
  2. The device asserts the level line, raising the vector on `D`'s core.
  3. At step 1 of arrival (line 780), `D` must mask the level source at the controller. `D` does not map the controller's registers (line 1082), so by line 797 `D` must send a `UnitRequest` (operation 5 masked) to `H`.
  4. Sending and completing that request is asynchronous (up to 20 ms+ per line 971, or queued if credits/table are busy per line 1043), and `D` cannot wait inside an interrupt handler (line 787, rule 5 at line 2146).
  5. If `D` performs step 2 (end of interrupt at `D`'s local interrupt controller, line 781) before `H` masks the controller RTE, the still-asserted level line re-triggers the interrupt on `D` immediately, creating an unbounded interrupt storm (breaking lines 787 and 789) until `D`'s core misses heartbeats and healthy node `D` is fenced (`stale`). If instead `D` omits step 2 (`781`), it violates line 781 and leaves the local controller's in-service state set, blocking equal- and lower-priority vectors (including kernel timers/IPIs if configured at lower priority).
- **Scenario B (Missing wait, `again`, and `busy` rules on `irq_bind`, `irq_ack`, and `notify` destruction):**
  1. By line 797, `irq_bind` (binding an idle level source or unbinding an armed level source, line 775) and `irq_ack` (on a fired level source, line 776) must send a `UnitRequest` to `H`.
  2. Unlike `iospace_unmap`, `iospace_attach`, and `irq_claim`, neither `irq_bind` nor `irq_ack` (lines 775, 776, 196, 1043, 1770) places the caller into *waiting for a unit*, returns `again` when `UNIT_REQUESTS` is full, or defines `busy` / rollback when the controller unit is failed or unavailable, nor does `notify` destruction (line 791) define returning `again` to start a unit request to mask an armed level line.
- **Smallest correction:** Forbid claiming a level-triggered line on any node other than the controller's role holder unless the hardware provides a per-node/per-line EOI register bypass (and specify how GIC distributor / APLIC handle that), or handle level lines exclusively on the controller's role holder; if remote level lines remain allowed with an EOI register, add *waiting for a unit*, `again` on full `UNIT_REQUESTS`, and `busy` on unit failure to `irq_bind`, `irq_ack`, and `notify` unbinding.

#### Finding 4 — Cross-node IOAPIC EOI register writes contradict G9 (`1082`) and suffer cross-node vector collisions
- **Severity:** contradiction / breaks a guarantee
- **Lines:**
  - Line 768: "Each physical core has one table, which belongs to the node its core word names; it has one entry for each vector that can be claimed... On x86-64 those are vectors 48 to 239"
  - Line 774: "`irq_claim` | irq_control, source, core number, vector, destination"
  - Line 797: "Where the local APIC suppresses the broadcast of the end of interrupt and the IOAPIC has an EOI register, a level line is acknowledged from the claiming core by one write of the vector into that register"
  - Line 799: "Vectors 48 to 239 can be claimed."
  - Line 1055: "**What needs no role,** so keeps running whoever holds or loses the roles: ... the acknowledgement of a level line through the IOAPIC's EOI register, where the hardware has one ([Interrupts](#interrupts))."
  - Line 1082: "The registers of a unit are mapped only in the gate view of the node its role word reads held by, or names as target of a handing ([Roles](#roles))."
- **Scenario:**
  1. Lines 797 and 1055 state that a node `D` that does not hold an IOAPIC's unit role directly writes the vector into the IOAPIC's EOI register (`What needs no role`), yet line 1082 forbids `D`'s gate from mapping the unit's registers at all (and on x86-64 the IOAPIC EOI register at offset `0x40` lies in the same 4 KB MMIO page as `IOREGSEL` `0x00` and `IOWIN` `0x10`). That directly contradicts line 1082 and breaks single-writer register isolation.
  2. Even if `D`'s gate were given write access solely to the EOI register, `irq_claim` allocates vectors `48..239` independently per physical core (lines 768, 774, 799). Node `A` claims level GSI 16 on core 0 at vector 50; node `B` (or a driver/faulty kernel on `B`) claims level GSI 17 on core 1 on the same IOAPIC also at vector 50.
  3. Because the IOAPIC EOI register takes only an 8-bit vector number and clears Remote IRR on every RTE carrying that vector, when `A` writes vector 50 to the EOI register, it prematurely clears Remote IRR on `B`'s active GSI 17, causing `B` to receive a duplicate interrupt while `B`'s driver has not yet cleared the device source (breaking line 789).
- **Smallest correction:** Either require level-line GSIs of one IOAPIC to be claimed only on the node holding that IOAPIC's unit role (so the holder writes EOI and coordinates unique vectors/RTEs), or require the platform/kernel to ensure distinct vectors across all level RTEs sharing an IOAPIC and explicitly state the gate exception for the EOI register (if only the gate writes it, though mapping the shared MMIO page still weakens single-writer isolation against a bug outside the gate).

#### Finding 5 — `iospace_map` with Caching Mode 1 or write-buffer flushing lacks wait, `again`, `busy`, and 0-device rules
- **Severity:** unsettled case / contradiction
- **Lines:**
  - Line 196: "**waiting for a unit**, for the confirmation of a unit request ([Devices and shared hardware](#devices-and-shared-hardware)), which ends at the confirmation, with `busy` when the unit is found failed"
  - Line 344: "An iospace serves devices of one unit at a time, at most 16 of them."
  - Line 348: "`iospace_map` | iospace, frame, untyped, device address, first page, page count, rights | | As `aspace_map`, with these differences. `write` on the iospace. The frame's page size must be one that every unit supports (`unsupported`, the first plain check). The range must lie inside the iospace's address width. The rights word is a non-empty subset of `read` and `write` (`invalid` otherwise, `exec` included), and a subset of the frame capability's rights (`denied`). Device memory is accepted"
  - Line 1028: "`iospace_map` writes only the owner's own tables and sends nothing, because a unit that reports caching mode 0 needs no invalidation when a translation is added; if a unit reports caching mode 1 or needs write-buffer flushing, bit 0 of the flags of the entry `Memory` is set, and every `iospace_map` also asks the unit's role holder to invalidate."
  - Line 1043: "what it completes, which is either the thread that waits for it in *waiting for a unit* (a call: `iospace_unmap`, `iospace_attach` and its detach, `irq_claim` of a line, a write of remapping entries) ... A call that finds no free entry returns `again` with nothing changed"
  - Line 1770: "`Again`, with nothing changed, is a new result of `untyped_retype`, `memory_give` and `memory_split` for the barrier of a watermark, in the rows above (D-138), and of `iospace_unmap`, `iospace_attach` and `irq_claim` when the unit request table is full"
- **Scenario:**
  1. On a machine where `Memory` flag bit 0 is set (CM=1 or write-buffer flushing, line 2091), a driver creates a new `iospace` (0 devices attached, so it does not yet belong to any IOMMU unit, line 344) and calls `iospace_map`, or calls `iospace_map` on an `iospace` whose unit has failed or whose node's `UNIT_REQUESTS` table is full.
  2. Line 1028 says "every `iospace_map` also asks the unit's role holder to invalidate", but lines 348, 1043, and 1770 omit `iospace_map` from: (a) the list of calls that enter *waiting for a unit*, (b) returning `again` when `UNIT_REQUESTS` is full, (c) returning `busy` when the unit has failed, (d) how an `iospace` with 0 attached devices selects a unit (there is no unit to invalidate if no device is attached yet, and `iospace_attach` subsequently invalidates when attaching), and (e) whether a multi-step `partial` `iospace_map` (`> E` chunks, G3) asks the holder after each step or only after the last step.
- **Smallest correction:** Specify in line 348, 1028, 1043, and 1770 that when `Memory` flag bit 0 is set and the `iospace` serves at least one device (for 0 devices, no request is needed because `iospace_attach` invalidates on attach), `iospace_map` checks unit failure (`busy`) and `UNIT_REQUESTS` (`again`), enters *waiting for a unit* on each step (or on completion of the final step) to send operation 3, and leaves the newly written entries intact (or refuses on `busy`) as for any failed unit.

---

### Attacker 3: Whole faulty kernel of one node

#### Finding 6 — A faulty live node can trap unit rebuild in an infinite `Report` loop, freezing unit requests and dead-node reclaim forever
- **Severity:** breaks a guarantee
- **Lines:**
  - Line 940: "a request for a unit the holder is rebuilding is kept until the rebuild ends."
  - Line 943: "`ReportAsk` | kernel | new holder of a unit role → each node that is starting, live or sealing | Answers at once with one `Report` ([Roles](#roles))"
  - Line 960: "`Report` | The key of the next item, or *end* (all ones); then three words per item"
  - Line 966: "an answer (`RevokeStep`, `UnitAnswer`, `Report`, `SendAnswer`) names a credit of this node toward the sender that is in use, with that serial and the kind of request it answers"
  - Line 968: "A ring *X* → *Y* is mapped writable only in *X*'s kernel and read-only in *Y*'s (the guarantee of [The gate over page tables](#the-gate-over-page-tables)); its writes are plain stores, not gate calls, since the receiver checks every message."
  - Line 1475: "and acknowledges the reclaim of the old holder."
  - Line 1476: "It sends that node a `ReportAsk` naming the unit, the epoch and the key; the asked node answers at once with one `Report`: its items on the unit in a fixed order ... from that key, as many as fit in one message, and the key of the next item or *end*. The holder asks again from the next key until *end*, then moves to the next node in index order ... A rebuild asks each node at most ⌈items / items per message⌉ + 1 times"
  - Line 1485: "For each such node *Z* that is not dead, it does not write `acked[Z]` = *Z*'s generation until that R1 is done"
- **Scenario:**
  1. Faulty node `Z` keeps beating its core beacons and draining its kernel and user rings (so neither `stale` nor `stuck` evidence ever holds against `Z`, lines 1292-1293).
  2. Unit role holder `H` dies, and healthy successor `S` begins rebuilding unit `u` (line 1475).
  3. `S` sends `ReportAsk(u, epoch, key = 0)` to `Z` (line 1476).
  4. `Z` writes a `Report` into its kernel ring `Z -> S` using plain stores (line 968), matching `S`'s active credit and serial (passing line 966), with 0 items and `next key = 0` (or any `next key <= asked key`, or alternating `0` and `1`).
  5. Line 966 imposes no monotonicity check on `Report` keys (`next key > asked key`, or item keys strictly increasing from `asked key`), nor any cap on asks per node.
  6. By line 1476 ("The holder asks again from the next key until *end*"), `S` sends `ReportAsk(u, epoch, 0)` again forever.
  7. `S`'s rebuild never finishes (violating line 1476's bound), every `UnitRequest` to `u` across all healthy nodes stalls forever (line 940), and `S` never writes `acked[H]` (line 1485), freezing `H`'s memory and cores until machine restart.
- **Smallest correction:** Require `S` (in line 966 or 1476) to verify that every returned item key is strictly increasing and at least the asked key, and that `next key` (when not *end*) is strictly greater than the last item's key and the asked key (with at least 1 item when `next key != end`), stopping with `end` (skipping/ignoring malformed reports from `Z`, and tracing code 11) if `Z` violates key progress or exceeds the maximum possible items for that node on the unit.

#### Finding 7 — IOMMU `Report` validation omits device identifier-word ownership, letting a faulty kernel steal a healthy node's context entry or create a cross-node Domain-ID collision
- **Severity:** breaks a guarantee
- **Lines:**
  - Line 1030: "and two context entries under one number with two roots would let translations cached for one node's device serve another's: \"if multiple context-entries are programmed with the same Domain-id (DID), such entries must be programmed with the same values for the Second-Stage Page Translation Pointer (SSPTPTR)\", since \"hardware implementations tag the various translation caches with DID\" (VT-d, §6.2.2.1)."
  - Line 1035: "1 attach | device identifier (0-15), domain number (16-31) | physical address of the iospace's root table | G9: the attach word moves from *pinned* to *attached* with that root (or reads *attached* with it), the root being of class 48 + *n*, *n* ≥ 1, held by the requester; the identifier word names the requester with its generation; the domain number is in the requester's range on the unit"
  - Line 1061: "**The guarantee (G).** At every instant, for every node *X*, every translation that the hardware can use on *X*'s cores (the physical cores whose core word names *X*'s generation) leads only to:"
  - Line 1063: "1. memory *X* owns: chunks whose ownership word reads *taken* (*X*, *X*'s generation), and *X*'s floor"
  - Line 1068: "\"Translation\" covers the CPU page tables and TLBs under every tag, the IOMMU tables *X* writes, and any other walker *X* could configure."
  - Line 1082: "**G9. IOMMU tables.** ... The gate of a unit's role holder writes a context entry only for a device whose attach word it has just moved from *pinned* (root) to *attached* (root), or reads *attached* (root), with the root the request names, that root being of class 48 + *n* with *n* ≥ 1 in memory held by the node that owns the device (a chunk taken by it with its generation, or its floor)"
  - Line 1475: "keeps the context entries that match, rewrites those that differ, writing a context entry only for a device whose attach word reads *attached* with the root the report names (D-137; ...), keeps without a report the entries whose root table lies in memory the ownership table gives to a sealed node or in its floor (a sealed node cannot report until it resumes), and clears every other entry no report claims ... clears a reported entry whose domain number lies outside its reporter's range"
  - Line 1476: "The holder asks again from the next key until *end*, then moves to the next node in index order ... A node that is sealed when its turn comes is not asked"
- **Scenario:**
  1. Healthy node `A` owns `dev_A` (identifier word taken by `A`, attach word `*attached* (root_A)`), attached to `iospace` root `root_A` with domain ID `DID_A` (in `A`'s range). Faulty live node `Z` owns `dev_Z` attached to `root_Z` with domain ID `DID_Z` (in `Z`'s range). `A` is either currently `sealed`, or has `A < Z` in node index order (so `S` processes `A`'s report before `Z`'s, line 1476).
  2. The IOMMU role holder dies, and healthy successor `S` runs the rebuild (lines 1475-1476).
  3. When `S` asks `Z`, `Z` includes `(dev_A, root_A, DID_Z)` in its `Report` (written with plain stores, line 968).
  4. `S` checks the conditions stated in lines 1475 and 1082: `dev_A`'s attach word reads `*attached*` with `root_A`, `root_A` has class `48 + n` (`n >= 1`) in memory held by the device's owner (`A`!), and `DID_Z` lies inside the reporter `Z`'s domain range. Neither line 1475 nor G9 (line 1082) checks that `dev_A`'s **identifier word names the reporter `Z`**!
  5. `S` therefore accepts `Z`'s report item and rewrites `dev_A`'s context entry with `(root_A, DID_Z)` (or if `A` was sealed, `S` first kept `(root_A, DID_A)` and then overwrote it with `(root_A, DID_Z)` when `Z` reported).
  6. Now `dev_A` (pointing to `A`'s `root_A`) and `dev_Z` (pointing to `Z`'s `root_Z`) are both programmed on the same IOMMU with the same domain ID `DID_Z`, directly violating VT-d §6.2.2.1 (line 1030) and allowing `dev_A` and `dev_Z` to use stale/cross-node IOTLB translations across `A` and `Z`'s memory (breaking G at line 1061). (If `Z` also reports a valid `(dev_A, root_A, DID_Z)` vs `A` later, `Z` can still poison whenever `A` is sealed or `A < Z`, and `S` only accepts one context entry per device.)
- **Smallest correction:** In both line 1082 (G9) and line 1475 (rebuild), require that a reported IOMMU device item is accepted only if the device's **identifier word names the reporting node with its current generation** (and, during rebuild, refuse duplicate reports for the same device or tie `A < Z` safely since each identifier word has a single owner).

#### Finding 8 — A faulty kernel can overflow the reverse kernel ring `Y -> X` and exhaust `Y`'s answer room
- **Severity:** breaks a guarantee / contradiction
- **Lines:**
  - Line 962: "`Send` | Three: the message header, the task identifier and the marks of the stamp; then one word per grant, its index (0-11), its serial (12-41) and its rights (42-49); then the message words | 71 (10 entries)"
  - Line 966: "The receiving kernel checks, in one function and before anything changes: ... a `ReportAsk` names the role's current epoch and comes from the node the role word names as holder; a `UnitRequest` passes whatever its epoch, which the holder judges ([Roles](#roles)); an answer (`RevokeStep`, `UnitAnswer`, `Report`, `SendAnswer`) names a credit of this node toward the sender that is in use, with that serial and the kind of request it answers; a `Send`'s stamp carries 0 (a sender attached to no task, [Tasks and marks](#tasks-and-marks)) or a task identifier of the sender's node with a counter that is not 0"
  - Line 968: "A ring is a header and entries of 64 bytes: `RING_KERNEL_ENTRIES` (64) for a kernel ring and `RING_USER_ENTRIES` (64) for a user ring... A ring *X* → *Y* is mapped writable only in *X*'s kernel and read-only in *Y*'s (the guarantee of [The gate over page tables](#the-gate-over-page-tables)); its writes are plain stores, not gate calls, since the receiver checks every message."
  - Line 971: "at most 16 entries per ring per interrupt, as the due events of a timer interrupt; if entries remain, the core sends itself the interrupt again, so the next 16 are served before anything else runs."
  - Line 975: "**Answers** (`RevokeStep`, `UnitAnswer`, `Report`, `SendAnswer`) always have room: the kernel ring *Y* → *X* keeps `REQUESTS_PER_PEER` + `SENDS_PER_PEER` + 10 entries (34) for the answers to *X*: one entry for each credit *X* can have in use toward *Y*, and 10 more because a `Report` takes up to 11 entries; a new holder has at most one `ReportAsk` in flight to each node, whatever the number of units it rebuilds, so one `Report` at most is owed to it."
  - Line 1517: "`RING_KERNEL_ENTRIES`, `RING_USER_ENTRIES` | 64 each, of 64 bytes"
  - Line 1521: "Reserve of answers | 34 entries | Of each kernel ring: `REQUESTS_PER_PEER` + `SENDS_PER_PEER` + 10"
- **Scenario:**
  1. Faulty node `X` writes directly to its own outgoing rings `X -> Y` using plain stores (line 968), ignoring its own local `SENDS_PER_PEER` (8) and `REQUESTS_PER_PEER` (16) / "at most one `ReportAsk` in flight" sender limits (lines 972, 975, 1476).
  2. **Via `Send`:** `X` writes 64 one-entry `Send` messages (kind 11 with 0 grants and <= 3 message words fits in 1 entry) into the 64-entry user ring `X -> Y` (and repeats as `Y` drains 16 entries at a time, line 971). Because line 966 does not check that `X` has fewer than `SENDS_PER_PEER` (8) sends in flight or that a `Send`'s credit index is `< SENDS_PER_PEER` and unused, `Y` accepts all 64 `Send`s and queues 64 `SendAnswer` entries into the 64-entry kernel ring `Y -> X`. Any other message in `Y -> X` (such as a `Revoke`, `UnitRequest`, or `Release`) leaves fewer than 64 entries free, so `SendAnswer`s overflow `Y -> X` (`64` entries, line 1517) while `X` simply stops advancing its consumer index on `Y -> X`.
  3. **Via `ReportAsk`:** If `X` holds a unit role `u`, `X` is the holder named in `u`'s role word, so 6 consecutive 1-entry `ReportAsk`s written by `X` into kernel ring `X -> Y` all pass line 966 ("comes from the node the role word names as holder", with no check for at most one `ReportAsk` in flight). If `Y` has 28+ items on `u`, `Y` owes 6 × 11 = 66 entries of `Report` into the 64-entry ring `Y -> X`.
  4. Line 975 gives no overflow fallback because it asserts "Answers always have room", so `Y` either overwrites unread entries in `Y -> X` or panics on an unchecked ring write.
- **Smallest correction:** Track and enforce `X`'s in-flight credits on `Y`'s receive check (line 966): require `credit < SENDS_PER_PEER` for `Send` (refusing or dropping duplicates with `Release`/`SendAnswer` semantics—or even simpler, have `Y` verify no already-active/unanswered credit or enforce a strict credit bound, and refuse a `ReportAsk` if a `ReportAsk` for `X` is already active or cap total answers, or specify that `X` exceeding its credit limit violates the protocol and causes `Y` to refuse/drop excess requests with trace code 11 instead of answering into a full reserve).

#### Finding 9 — `UnitRequest` omits incoming `credit` bounds and duplicate-credit checks on the holder's `unit service table`
- **Severity:** cannot be built as written / breaks a guarantee
- **Lines:**
  - Line 966: "a `UnitRequest` passes whatever its epoch, which the holder judges ([Roles](#roles)); an answer (`RevokeStep`, `UnitAnswer`, `Report`, `SendAnswer`) names a credit of this node toward the sender that is in use, with that serial and the kind of request it answers"
  - Line 972: "Each node keeps in its node block, for each peer, `REQUESTS_PER_PEER` (16) **request credits** and `SENDS_PER_PEER` (8) **send credits**."
  - Line 1045: "The holder keeps each request it serves in its **unit service table**, one entry per request credit of each peer (`REQUESTS_PER_PEER` × (*n* − 1) entries, indexed by the peer and the credit, so none is searched)"
  - Line 1518: "`REQUESTS_PER_PEER` | 16 | Kernel requests in flight from one node to another"
  - Line 1520: "The holder's unit service table has `REQUESTS_PER_PEER` × (*n* − 1) entries"
  - Line 1793: "the ring entry header (kind, length in entries, sender slot, sender generation, receiver generation, and since D-131 the credit, 5 bits, with its serial, 27 bits)"
- **Scenario:**
  1. The ring entry header allocates 5 bits for `credit` (values `0..31`, line 1793), whereas `REQUESTS_PER_PEER` is 16 (`0..15`, lines 972, 1518), and the holder's `unit service table` is sized `REQUESTS_PER_PEER × (n - 1)` and indexed directly by `(peer, credit)` with no search (lines 1045, 1520).
  2. Line 966 checks `credit` only on incoming *answers*, not on incoming `UnitRequest` (or `Revoke` / `ReportAsk` / `Send`).
  3. Faulty node `X` sends a `UnitRequest` with `credit = 20` (or `31`), which passes line 966 and either indexes out-of-bounds past the end of `H`'s `unit service table` (or into peer `X + 1`'s slice if `16 * peer_idx + credit` is computed unchecked).
  4. Even with `credit = 0`, `X` can send a second `UnitRequest` with `credit = 0` while `H` already holds an in-flight `UnitRequest` for `(X, 0)` waiting up to `IOMMU_WAIT_NS` (line 1045), overwriting the active entry in `H`'s `unit service table` and leaking/corrupting its completion.
- **Smallest correction:** Add to line 966 (the single receive check) that for `Revoke`, `UnitRequest`, and `ReportAsk`, `credit < REQUESTS_PER_PEER` (and for `Send`, `credit < SENDS_PER_PEER`), and for `UnitRequest`, refuse (trace code 11 and consume without writing the table) any request whose `(sender, credit)` entry in the `unit service table` is already in use.

#### Finding 10 — A faulty unit role holder can permanently starve `UnitRequest`s across all nodes by answering `*elsewhere*` under its current epoch
- **Severity:** breaks a guarantee / contradiction
- **Lines:**
  - Line 940: "`UnitRequest` | kernel | any node → holder of a unit role | Judged by the holder ([Roles](#roles)): served if the role word reads held by the holder's node with the request's epoch and the holder has not begun to hand the role over, answered *elsewhere* otherwise"
  - Line 941: "`UnitAnswer` | kernel | holder → requester | ... *elsewhere* sends it again, at once if the role word reads held by another node, or once it reads held if it reads handing"
  - Line 1044: "*elsewhere* makes the entry queued again, sent at once if the role word now reads held by a live node with another epoch, and otherwise once it does, which the requester reads again at each step of its recovery reserve while it has queued entries."
  - Line 1465: "A requester answered *elsewhere* reads the role word again: if it reads held, it sends the request to the holder it names with that epoch; if it reads handing, it keeps the request queued and sends it once the word reads held."
- **Scenario:**
  1. First, there is a direct contradiction between line 1044 (resend *elsewhere* at once only if the role word reads held by a live node with *another epoch*) and line 1465 (if the role word reads held, resend to the holder it names with *that* epoch—so if the role word is still held by the same node with the same epoch, line 1465 resends immediately while line 1044 waits forever for the epoch to change).
  2. Second, faulty live node `Z` holds unit role `u` at epoch `e`, keeps its core beacons beating and drains its rings normally (never triggering `stale` or `stuck`).
  3. Whenever any healthy node `R` sends a `UnitRequest` for `u` carrying `(Z, e)`, `Z` writes `UnitAnswer(*elsewhere*)` into `Z -> R` using plain stores (line 968).
  4. Under line 1044, `R`'s request stays queued forever waiting for `e` to change; under line 1465, `R` loops resending the `UnitRequest` to `Z` forever. Either way, `Z` permanently starves `iospace_attach`, `iospace_unmap`, `irq_claim`, iospace teardown, and R2 on `u` across every node without failing any gate check or giving any evidence (`stale`, `stuck`, `self`, `seal`) to accuse `Z`.
- **Smallest correction:** Resolve line 1044 vs 1465 to match line 1044's rule for *same* `(holder, epoch)` (do not tight-loop resend to the same `(holder, epoch)`), and either require the requester to treat `*elsewhere*` from the current `(holder, epoch)` when the role word is not handing as a protocol fault of the holder (or accept that a faulty unit role holder can deny service on its unit, explicitly documenting it alongside line 966's statement that a faulty kernel can damage availability—and resolving the contradiction between 1044 and 1465).

#### Finding 11 — `Report` wire encoding has no item count and no sentinel, making the number of items ambiguous
- **Severity:** cannot be built as written
- **Lines:**
  - Line 949: "A message is its 16-byte header (below) and these 64-bit words; bit ranges are of the word named. It takes ⌈(16 + 8 × words) / 64⌉ entries."
  - Line 960: "8 | `Report` | The key of the next item, or *end* (all ones); then three words per item: its key, then for a device its root table and its domain number, for a remapping handle two words 0, for a line the two operands of its operation 5 claimed ... At most 28 items | 85 (11 entries)"
  - Line 1793: "and the ring entry header (kind, length in entries, sender slot, sender generation, receiver generation, and since D-131 the credit, 5 bits, with its serial, 27 bits) as a `repr(C)` type of 16 bytes at the start of a message's first entry."
- **Scenario:**
  1. The ring message header carries `length in entries` (multiples of 64 bytes = 8 words), not an exact word count or item count (lines 949, 1793).
  2. A `Report` has 2 header words + 1 `next key` word + `3 × k` item words = `3 + 3k` words total, rounded up to a multiple of 8 words (`entries × 8`).
  3. Because 3 and 8 are coprime (`⌊8/3⌋ >= 2`), multiple distinct item counts *k* occupy the same number of entries. For example, a 2-entry `Report` (16 words total = 14 payload words) holds `k = 2` (7 payload words), `k = 3` (10 payload words), OR `k = 4` (13 payload words).
  4. There is no sentinel word at the end of the items, and a remapping-handle item for handle `0` legitimately consists of `(key = 0, word1 = 0, word2 = 0)` (or handle key `0` with item type bits = 0) which is indistinguishable from zero-padding in the unused words of the last 64-byte entry.
- **Smallest correction:** Add an explicit `item count` field (5 bits fits 0..28, or 8 bits in the `next key` / first payload word, or carry exact `words` in the 16-byte header or first `Report` word) so the receiver knows *k* unambiguously.

#### Finding 12 — GIC ITS `Report` encoding, key order, and rebuild checks are unspecified
- **Severity:** cannot be built as written / unsettled case
- **Lines:**
  - Line 944: "`Report` | kernel | asked node → new holder | The asked node's items on the unit, in a fixed order, from the key the ask named, as many as fit in one message, and the key of the next item or *end* (an iospace serving a device of the unit: device, root table, domain number; a remapping handle it claimed; a line it claimed)"
  - Line 960: "`Report` | The key of the next item, or *end* (all ones); then three words per item: its key, then for a device its root table and its domain number, for a remapping handle two words 0, for a line the two operands of its operation 5 claimed ... (or the architecture's route: on ARM64 the SPI's identifier, trigger and enable in the first and the affinity of `GICD_IROUTER` in the second; on RISC-V the source, its mode and enable in the first and the target hart, priority or identity in the second...)"
  - Line 1082: "**An ITS mapping** (ARM64: the entry of a device in the ITS's device table and the translation of its events to an LPI and a collection) is written only for a device whose identifier word names the requester with its generation, with its interrupt translation table, which the ITS reads and writes, in memory the requester holds (G3 (2)), and toward a collection whose core's word names the requester with its generation"
  - Line 1475: "for a GIC ITS, it drains the command queue, issues again the mappings the live nodes report, then invalidates and synchronises"
  - Line 1476: "its items on the unit in a fixed order (its devices attached through the unit, from its own list, by identifier; then the remapping handles it claimed, by handle; then the lines it claimed, by global system interrupt)"
- **Scenario:**
  1. Line 1475 mandates that a node taking over a GIC ITS role after death rebuilds the ITS by issuing again "the mappings the live nodes report".
  2. Line 1082 establishes G9 security checks for an ITS mapping: device identifier word, ITT physical address and size, LPI, event ID, and collection/target core word.
  3. Yet lines 944, 960, and 1476 define `Report` items, 3-word payload encodings, and key orderings only for IOMMU devices, x86-64 remapping handles, and interrupt lines (IOAPIC, GICD SPI, APLIC), omitting GIC ITS mappings completely—and 2 payload words after a 64-bit key cannot even carry device ID, ITT base, event ID, LPI, and collection ID unless split across item types or packed explicitly.
- **Smallest correction:** Specify the `Report` item format, key space, fixed ordering, and G9 rebuild validation for GIC ITS device-table entries (device ID, ITT physical address/size) and event-to-LPI/collection mappings (device ID + event ID, LPI, target core/collection) in lines 944, 960, 1475, and 1476.

---

### Attacker 5: Someone at the debugger or the console

#### Finding 13 — Console take-over cursors cannot be rebuilt without reading the dead holder's memory
- **Severity:** contradiction / cannot be built as written
- **Lines:**
  - Line 1451: "Every role obeys three rules: one holder, recorded in the role word, changed only by compare-and-swap through the gate; nothing that cannot be rebuilt from the kept memory, the hardware and the reports of the nodes that are starting, live or sealing (a new holder never reads the dead holder's memory as truth: D-107)"
  - Line 1475: "maps the unit and **rebuilds** it without reading anything of the old holder's: ... for the console, it takes over the cursors."
  - Line 1523: "**What each node keeps** for this group, in its node block or its beacons, all fixed at start: its member word's last value seen, its four watch slots, the per-core part of each of its cores ..., its recovery reserve, its 8 observations, its `acked` array and `maps_of` bitmap, its request and send credits toward each peer, its unit request table and its unit service table, the cursor of each rebuild it runs, its write gate and gate lock (D-131), its node lock, its kernel epoch and its barrier epoch (D-138), its quiet word and the entry word of each of its cores, reserved (D-135, D-138), and in a development image the stopped time (D-137)."
  - Line 1632: "the kernel never enables its interrupts, never reads it (except the debugger stub of a development image, below) and polls its transmit status."
  - Line 1633: "**One node drives it:** the holder of the unit role `console` ([Roles](#roles)). Every other node's messages reach it through the rings and the beacons, which the holder reads."
  - Line 1647: "10 | IOMMU faults were recorded | unit index, number since the previous message 10 for this unit"
  - Line 1649: "12 | Hardware errors were corrected | node, number since the previous message 12 for this node"
  - Line 1651: "14 | Kernel entries were suppressed | node, code, number"
- **Scenario:**
  1. The console role holder `H` prints messages 1–14 from node beacons and core trace rings (lines 1633, 1636-1653), maintaining cursors of which trace-ring sequence numbers, member/role state transitions, and suppressed/fault counts ("since the previous message 10/12/14") have already been printed.
  2. `H` dies (or is killed via `node_stop`) and successor `S` takes over the `console` unit role (line 1475).
  3. Line 1475 requires `S` to "take over the cursors" "without reading anything of the old holder's", and line 1451 forbids reading the dead holder's memory.
  4. However, no console cursors exist anywhere in the machine table (lines 826-827), in the beacons (lines 1281-1282), in `What each node keeps` (line 1523), in debug headers (line 1548), in `Report` messages (lines 944, 960, 1476), or in the output-only UART hardware (line 1632). Thus `S` has no kept source from which to take over the cursors.
- **Smallest correction:** Either place a small fixed console-cursor record in kept memory (written by the current console role holder through its gate or single-writer slot, as a kept page per console), or replace "takes over the cursors" in line 1475 with an explicit reset rule (start cursors from the current debug-ring next sequences and current member/role words at take-over, accepting loss/duplication of unprinted lines from the dead holder's window).

#### Finding 14 — Debugger stub stop mechanism conflicts with RISC-V `fence_hart` and leaves unstopped or concurrently entering cores unsafe
- **Severity:** contradiction / cannot be built as written
- **Lines:**
  - Line 900: "Every write through a node's gate first reads that node's member word, and refuses unless the node is starting, live or sealing with its current generation ([Cores](#cores)); the kernel then parks itself."
  - Line 1083: "INIT, SIPI and NMI go only to a core whose core word names a node whose fence the caller drives and carries the fence mark, or, for the wake of a start (NMI, `CPU_ON`, `sbi_hart_start`), to a core whose word names, as *joining* or *owned* and without the fence mark, a node whose member word reads starting with the word's generation ...; in a development image only, the debugger stub also stops every core ([Two builds, and the debugger stub](#two-builds-and-the-debugger-stub))."
  - Line 1312: "An NMI that interrupts the entry stub before the entry stub has installed the node kernel's handler only returns, and the entry stub then reads its core word, which a fence marked before its NMI"
  - Line 1315: "clears every private event and masks the PE at the end of each PSCI `CPU_ON` ... and masks the PE again after a power-down suspend ... and acknowledges and loses an event that reaches a masked PE"
  - Line 1316: "So the stop of another hart needs **the DodOS stop extension** `fence_hart`, an SBI extension the project provides for firmware it can replace: the machine mode of *p* stops it whatever the supervisor mode masks, a forced stop, **confirmed** by the extension's answer to the park request, which the extension gives only once the hart executes nothing in supervisor mode or below and leaves it in the state STOPPED, so that `sbi_hart_start` can start it again ... Without the extension, the cooperative path only: an interrupt to *p*, whose handler, if it runs, calls `sbi_hart_stop`"
  - Line 1660: "The stub is entered when the link receives the byte 0x03, at a kernel breakpoint or watchpoint, or at a failure of any node if the development option *stub on failure* is set. The core that enters it sends the architecture's strongest signal (as the fence does) to every other core that runs a node, after it has raised the stop in the release word of kept memory, so that a handler that finds no fence mark on its core's word knows the signal is the stub's (D-134); each saves its registers in its core's slot kept for the stub and waits on that release word; a core that does not stop within 10 ms is shown to gdb as running. ... **While the release word is raised, the clocks of membership stop (D-135, D-137):** no gate records an observation and no node makes an accusation, of another node or of itself; a wait, a due event or a step of a fence that finds the release word raised suspends, and resumes once it is lowered. ... Beside the release word, a development image keeps one word, the **stopped time**: the total of the times spent stopped in the stub, which the stub adds to, by the length of the stop it ends, before it lowers the release word."
- **Scenario:**
  1. **RISC-V contradiction:** Line 1660 sends "the architecture's strongest signal (as the fence does)" to every other running core expecting each core to run a handler that sees no fence mark, saves registers, waits on `release word`, and resumes when `release word` is lowered. Under line 1316, however, the RISC-V fence signal (`fence_hart`, or the cooperative handler calling `sbi_hart_stop`) permanently forces the hart into SBI `STOPPED` state without running a resumable kernel handler—so on RISC-V every other hart is killed rather than paused by the debugger stub.
  2. **Gate refusal on `stub on failure` and unstopped-core races:** If a node fails and enters the stub via `stub on failure`, or enters on a core while its node's member word is no longer live/sealing, line 900 makes the gate refuse writes; yet G10 (line 1083) requires stopping signals to go through the gate. Meanwhile, any core that misses the signal (e.g., an x86-64 core in the entry stub before installing the kernel's NMI handler at line 1312, or an ARM64 core whose PE is masked before `SDEI_PE_UNMASK` at line 1315) is merely "shown to gdb as running" (line 1660) and continues executing kernel calls outside `wait`/`due event`/`step of a fence`—mutating shared tables or spinning on node locks held by stub-stopped cores—while `release word` and `stopped time` also have no lock/protocol preventing two cores from entering the stub simultaneously (e.g., `0x03` arriving on one core as another hits a kernel breakpoint) and double-counting `stopped time`.
- **Smallest correction:** Specify a non-destructive debug stop IPI/trap for RISC-V (e.g., an SBI/M-mode debug interrupt that enters the stub handler when `release word` is raised rather than stopping the hart), give the development-only stub entry a dedicated gate/lock entry that serializes `release word`/`stopped time` and works on a failing node, and require cores leaving the entry stub or idle unmasking to check `release word` before executing kernel work.

---

## What was checked and found sound

I tested all five attacker roles against the remaining mechanisms in `kernel-interface.md` and could not break the following promises as written:

- **Capability derivation tree and revocation bounds (lines 115-137, 150-161):** Checked whether a user process could construct a cycle in the derivation tree, keep a capability after its parent or `cspace` was revoked, or make `cap_delete`/`cap_revoke` loop unconditionally. The depth limit (64), strict depth ordering for spaces (`>` ) and untypeds (`>=`), bounded 32-unit / 128-slot removal steps, and the immediate `gone` marking on dying `cspace`s and objects hold up; the one explicit exception (a thread deriving `>= 33` capabilities per removal step) is already documented at line 131.
- **Process isolation, address spaces, and dirty memory clearing on 4 KB pages (lines 162-173, 250-335, 1074-1088):** Checked whether a user process could reach unzeroed memory, bypass W^X, map table/gate/kept pages writable, alias memory types, or retain a stale TLB/unhooked page-table page across `aspace_unmap` or `memory_give`. On 4 KB pages, the clean-mark padding rule, per-page `PageClass`, single-writer `GateWord` counts held until completion of cross-core invalidations (and `CnP = 0` + `TLBI` + `DSB ISH` on ARM64), external storage of unhooked table addresses before joining the free list, and the epoch-based barrier before watermark return all close the attacks I tried.
- **Tasks, provenance marks, and `task_revoke` (lines 1096-1180):** Checked whether a user thread could shed marks by detaching/reattaching, racing `task_attach` against concurrent IPC delivery, or continuing calls after `task_revoke`. Under the single node lock (`1114`), marks are monotonic and `task_revoke` stops all running threads of the task across cores before detaching them (`1142`). Known covert/notify channels are already honestly excluded (`1138`).
- **Faulty kernel isolation for owned memory and cross-node frame grants (lines 822-930, 966-991, 1061-1094, 1321-1356):** Tried aggressively to let a faulty kernel `Z` steal memory chunks, forge ownership/line/identifier/core words, reuse a grant serial across generations, fake a stale/stuck accusation against a healthy node, or bypass the reclaim barrier (`R0-R6`). Gate checks (`G1-G13`), `14-bit` check fields, per-node generation tagging, `AttachWord` transitions (`355-377`), `RetiredWord` vector retirement (`793`), and the `FENCE_NS` + `SETTLE_NS` + `maps_of` reclaim barrier (`1306-1353`) held against every attack on another node's owned memory or cores (noting that line 1093 explicitly excludes a grantee's faulty `Release`/`RevokeStep`/`SendAnswer` freeing a frame granted *to* that faulty kernel).
- **Device DMA fault bursts, ATS exclusion, and `irq` retirement on failed IOMMU units (lines 393-403, 785, 793, 1574-1575):** Tried to flood a kernel or reuse a stale interrupt-remapping handle after an IOMMU unit fails. The 16-fault-per-interrupt cap with 1 ms timer masking (`1575`), kernel trace-ring rate limit (`1574`), and `retired word` keeping failed handles unused until reboot (`793`) hold.
- **Crash record handover and production console isolation (lines 1531-1658):** Checked whether a user process or crashed kernel could overwrite the previous boot's crash area, erase kernel trace rings by flooding `debug_write`, or leak kernel addresses/secrets through a production console. The separate kernel/user rings (`1552`), read-only previous crash area (`1622`), and numbered decimal-only production console messages (`1634`) hold.

## What was not checked

- **External hardware specifications and referenced repository files:** By instruction, I did not read `kernel.md`, `abi/`, `decisions/`, `research/`, `reviews/`, or any external architecture manuals (Intel SDM, VT-d, Arm DDI 0487, Arm IHI 0069, PSCI, TF-A SDEI, RISC-V AIA/SBI) to cross-check register bit offsets, CSR names, or instruction semantics independently of what `kernel-interface.md` quotes.
- **Exact numeric sizing and empirical latency assumptions:** I did not verify whether provisional constants (`STALE_NS`, `CORE_ANSWER_NS`, `FENCE_NS`, `SETTLE_NS`, `IOMMU_WAIT_NS`, recovery reserve 1/64, `GRANTS = 4096`) suffice on real hardware, nor check boot-image/ACPI parsing edge cases outside the contract text.
