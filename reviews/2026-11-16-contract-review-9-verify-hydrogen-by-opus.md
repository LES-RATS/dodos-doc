# Verification of contract review 9 (Hydrogen), by Opus

Target: [2026-11-16-contract-review-9-gemini-hydrogen.md](2026-11-16-contract-review-9-gemini-hydrogen.md), which reviews `architecture/kernel-interface.md` at Docs commit `fd13764` (pass 16, D-133). The reference model is `dodos-kernel`, branch `model`, head `633f6f3`. Line numbers are those of `kernel-interface.md` at `fd13764`; "the gaps file" is `research/drafts/model-15-contract-gaps.md`. Decisions are counted to D-133.

**Method.** For each finding I checked every quote at its line, replayed each scenario against the text, and read the model code that builds the rule (`model/src/system.rs`, `nodes.rs`, `table.rs`, `units.rs`, `irq.rs`, `memory.rs`, `locks.rs`, `cores.rs`, `lib.rs`, `caps.rs`; `abi/src/machine.rs`, `lib.rs`). I read these parts of the contract in full: lines 80-147, 239-260, 335-380, 560-669, 725-783, 871-1012, 1014-1052, 1137-1480, 1854-1905, 1928-1956. I read the other lines the review cites one by one. I did not read the rest line by line (debugging, unlike cores, registers, the start-up page entries, the open points), so a contradiction between those parts and my corrections is possible.

**Quotes.** Every quote in the review matches its line. The one slip: the reply-object quote in finding 6 is given as ":203 & :209" and is only at line 203. No quote is invented.

## Verdicts in brief

| # | Review's claim | Verdict | Introduced by pass 16? |
|---|---|---|---|
| 1 | The `started` word and the 1 ms retry | **Confirmed with another correction.** The layout, the generation, the writer on ARM64 and RISC-V, and what a late NMI does to a live kernel are all unsettled. Case A (a latched NMI restarts the entry stub) is wrong. The dying starter is already settled. I found one more hole, older than pass 16: an NMI that lands in the entry stub gives a false confirmation | Yes, apart from the false confirmation, which came in with D-131 |
| 2 | The fence record is indexed by position, and positions shift as R6 frees words | **Confirmed.** The scenario replays exactly. Two sub-claims are wrong: the write rules are stated, and an instant of 0 is settled | Yes (gap 6) |
| 3 | An unmapping record is not exempt, and `gone` blocks the holder | **Partly right.** Both are ambiguities of wording, not breaks; the model reads them the safe way. The review's correction exempts more than it needs to | Yes (gap 15) |
| 4 | The unit sequence has no cursor, leaks at a failure, and does not settle a destroyed waiter | **Confirmed with another correction.** The cursor (the PCI segment) is missing from the entry. On a failure nothing leaks, but what stays is not said, and stopping at the failed unit is the wrong rule. The destroyed waiter is unsettled | The cursor and the destroyed waiter: yes. What a `busy` claim leaves: before |
| 5 | The operands of `UnitRequest` are missing for attach and the redirection entry | **Confirmed with another correction.** Behind it is an older gap: nothing says who gives domain numbers on a unit that several nodes share | The layout: yes. The domain numbers: before |
| 6 | The L2 order by kind is inverted by several calls | **Confirmed in substance; some sub-claims are wrong.** The sentence "no call needs a lock of an earlier kind after a later one" is false, even on the IPC common path. The model cannot see it because it sorts the locks it collected | Yes (gap 5) |
| 7 | One window of 64 cores against the one-node fallback | **Confirmed**, an edge case. The side note (state features) is right too, and older | The window: yes. The features: before |
| 8 | The own-core watch cannot use `observations[8]`, and idle siblings do not watch | **Partly right.** The watch needs no gate observation. The real gap is that "what it last saw" has no field in the layout, and that the fallback when every other core is idle is not stated | Yes (gap 16) |

---

## Finding 1: the start request, `started`, and the retry every millisecond

### What the text says

- Line 1183: "The stub writes the start request it takes into `started` of its core beacon (0 when it parks), and the node that starts a core sends the wake again every `START_RETRY_NS` (1 ms) ... until `started` equals its request or the node is no longer starting", and further on: "a wake repeated to a core that has left the stub would be taken by its node's kernel as a fence signal".
- Line 1267: the stub's NMI handler "writes the park request it reads into `parked`, reads the start request, and returns by `IRET`; if the start request names a node the stub writes it into `started` and goes to the entry stub, otherwise it halts again".
- Line 1264 says what the kernel's NMI handler does when it "sees its member word in fencing", and nothing else.
- Line 1183 again: the entry stub "arms the fence's signal first (ARM64: ...), then reads its core word"; what arming means on x86-64 is not said.
- Line 1736: "The park request and the start request: one `u64` each". No layout is given anywhere in the contract.

### Sub-claims

**1A, an NMI latched behind NMI blocking restarts the entry stub. Wrong.** The handler of line 1267 returns by `IRET` to the instruction it interrupted. Leaving for the entry stub is a decision of the stub's loop after the halt, not of the handler. An NMI held while the handler runs is taken right after its `IRET` (SDM §7.7.2, the sentence quoted at line 1264). It runs the handler once more: `parked` is written again with the same request, the start request is read again, and the handler returns to the loop. That is idempotent. The retry period (1 ms) is also three orders of magnitude longer than the handler, so a retry almost never arrives inside it.

**1B, a late wake reaches the live kernel. Confirmed, and it was introduced by pass 16.** Replay: the starter *C* reads `started` ≠ its request; the stub takes the request, writes `started` and leaves; *C*'s next wake goes through its gate. G10 (line 1040) allows it, because the core word still reads *joining* (owned is written later). So the NMI reaches the core after it has left the stub. Before pass 16 only one NMI was sent, so this could not happen. The rationale at line 1183 says the node's kernel "would" take such a wake as a fence signal. If it did (parked its core on any NMI), a healthy starting or live node would lose a core and accuse itself through gap 16 or `CORE_ANSWER_NS`. The text gives the kernel's handler no rule to tell a late start wake from a fence. The model avoids the question without saying so: `System::wake` (system.rs:621-627) ignores a start wake to a core in `Entering` or `Running`, while `System::stop` (system.rs:553-561) parks on the fence's NMI. In hardware both are the same NMI, so the kernel must decide from shared state. The mark is the right test: G10 lets the driver send an NMI only to a marked word, and the driver raises the park request before it marks (line 1177).

**Another correction, a false confirmation older than pass 16.** The stub's handler writes `parked` wherever it runs. Suppose the entry stub has read its core word (not yet marked) and has not yet installed the node kernel's NMI handler. The driver then raises the park request, marks the word, and sends the NMI. The stub's handler writes `parked` = the new request and returns by `IRET` into the entry stub, which enters the node. The driver reads `parked` equal to its request and confirms (line 1268). R6 then frees the core while it runs *N* with *N*'s page tables. That breaks the central rule at line 1141. Line 1183 closes this only if "arms the fence's signal first" means, on x86-64, installing the kernel's NMI handler before the word is read. The text says that for ARM64 alone. This came in with D-131 (the stub's handler writes `parked`, N4 of the eighth review), not with pass 16.

**2, two starters across a restart. Confirmed for the text; the model is right.** The stop condition "the node is no longer starting" ignores the generation. Replay: *C1* starts *N*(*g*); *N* fails, is fenced (`FENCE_NS`), reclaimed and dead, and *C2* starts *N*(*g* + 2) on the same core, all inside *C1*'s `START_NS` (1 s). *N* reads starting again, so *C1* goes on waking *p*. With a generation in the request, `started` never equals *C1*'s request, and *C1* wakes every millisecond until `START_NS`, which feeds 1B. G10's "a node the caller is starting" is a condition the gate cannot check: it does not know who started the node. The model stops on the generation (`start_step`, nodes.rs:1581-1588: `member.generation() == start.generation`).

**2, the starter dies while retrying. Wrong as a defect.** Line 1375 settles it: "As at step 1 for the cores not yet started": *N* does not beat within `START_NS` and is accused with stale. The cost is the delay the table accepts.

**3, the layout collides with slot 0. Confirmed as unsettled.** The contract gives no layout, and "names a node" with a raw slot index would read slot 0 as none. The model already settles it: bit 63 set, the node slot in bits 32-47, the generation in bits 0-31, and 0 means none (`Table::start_request` and `started_node`, table.rs:366-375, over `NodeGen` in abi/src/lib.rs:1075). Bit 63 also keeps the word non-zero after the generation wraps (line 1232: generations wrap).

**4, ARM64 and RISC-V. Confirmed.** Line 1236 says `started` is written by "the park stub", which ARM64 and RISC-V do not have. So read literally, the starter retries `CPU_ON` or `sbi_hart_start` until the node is live, never seeing a confirmation. The repeats themselves are harmless. A `CPU_ON` to a core already on returns ALREADY_ON or ON_PENDING (PSCI, both added to CPU_ON before PSCI 1.0: I found this in the revision history of DEN0022 as the search results quote it; section 5.6 was not read in full). `sbi_hart_start` on a started hart returns `SBI_ERR_ALREADY_AVAILABLE` (SBI HSM, docs.riscv.org, read 16 November 2026). What breaks is the ARM64 confirmation "no `CPU_ON` was sent to it since" (line 1179): a retry that passes the gate after the fence raised the park request blocks the confirmation until the request is raised again. The model writes `started` in `wake` on every architecture (system.rs:647-650) and retries on every architecture. So the model's reading is "the stub that takes the request", which on ARM64 and RISC-V is the entry stub.

### Correction (exact text)

1. Line 1183, replace "The stub writes the start request it takes into `started` of its core beacon (0 when it parks), and the node that starts a core sends the wake again every `START_RETRY_NS` (1 ms), in its recovery reserve, until `started` equals its request or the node is no longer starting" with:

   > A start request and `started` are 64-bit words: bit 63 set, the node slot in bits 32-47, the generation in bits 0-31, the other bits 0; 0 means none. The stub that takes the request writes it into `started` of its core beacon, 0 when it parks: on x86-64 the park stub, before it leaves for the entry stub; on ARM64 and RISC-V the entry stub, as its first write. The node that starts a core writes the request once and sends the wake again every `START_RETRY_NS` (1 ms), in its recovery reserve, until `started` equals its request or the node no longer reads starting with the request's generation.

2. Line 1183, replace "and a wake repeated to a core that has left the stub would be taken by its node's kernel as a fence signal" with:

   > and the wakes repeated meanwhile would each interrupt a core that already runs the node. The node kernel's NMI handler parks its core only if the core's word carries the fence mark or the node no longer reads starting, live or sealing with its generation; otherwise it returns by `IRET` and changes nothing, so a wake that reaches a core after it left the stub costs one interrupt.

3. Line 1183, after "which arms the fence's signal first (ARM64: ...": insert "x86-64: it installs the node kernel's NMI handler;".

4. Line 1267, replace "the stub's NMI handler writes the park request it reads into `parked`, reads the start request, and returns by `IRET`" with:

   > the stub's NMI handler, if it interrupted the stub's loop (from the stub's write of `parked` to its halt), writes the park request it reads into `parked` and reads the start request; it then returns by `IRET`. An NMI that interrupts the entry stub before the entry stub has installed the node kernel's handler only returns, and the entry stub then reads its core word, which a fence marked before its NMI.

5. G10 (line 1040), replace "or to a core whose word names, as *joining* or *owned*, a node the caller is starting or resuming by `node_start`" with:

   > or, for the wake of a start (NMI, `CPU_ON`, `sbi_hart_start`), to a core whose word names, as *joining* or *owned* and without the fence mark, a node whose member word reads starting with the word's generation; the gate writes a start request only under the same condition, naming that node and generation.

6. Line 1236, replace "the start request the park stub took when it left for the entry stub" with "the start request the stub took (x86-64 the park stub, ARM64 and RISC-V the entry stub)".

7. Line 1736: "The park request and the start request: one `u64` each per physical core in the living part, the start request in the layout of [Node slots and core words]; `parked` and `started` (`u64` each) in the core beacon."

**The review's corrections judged.** Its layout (slot in bits 0-15, a valid bit 16, the generation in bits 32-63) works, but it differs from the model's for no gain. Its correction 2 ("write `started` under an atomic compare-and-clear before IRET ... do not re-enter the entry stub if `started == req`") answers case A, which is not a defect. Its correction 3 ("restrict the retries to x86-64") also works. I keep the retry on all three architectures because the model does it, the repeats are harmless there, and the writer becomes the entry stub. Its idea that the kernel's handler "checks `member == fencing`" is too narrow: an unfenced node is still driven (line 1223), so the handler must park there too. The mark covers every case of the fence.

**Cost against the owners' rule.** The retry costs only during a start, which is a rare event. Checking the mark in the NMI handler costs one read, and only when an NMI arrives. Nothing is paid on the common path.

**What changes in the model.** The layout, the writer and the generation test are already as above. Two things to add: (a) a test that a start wake reaching a core in `Entering` or `Running` changes nothing (today `System::wake` returns there without a test that pins the rule); (b) in `System::stop`, park a `Running` core only if its word is marked. That is true by construction now, but it should be asserted so that a future start path cannot reuse the stop. The false confirmation of the entry stub cannot show in the model as it stands: `Hardware::Entering` gets INIT rather than the stub's handler (system.rs:566-572). Modelling the entry stub's window (read of the word, then the handler installed) would let the explorer find it.

---

## Finding 2: the fence record indexed by position

**The text.** Line 1261: "words 4 to 67, for each position of *X*'s cores (0 to 63), the instant of the last stop sent to that core". Line 92: positions are "0 to *N* − 1 in the order of core numbers". Line 1294: R6 frees a word "once its core is confirmed stopped and `SETTLE_NS` have passed since the last stop sent to it, as *X*'s fence record gives it".

**Do positions shift? Yes, for any node that reads them from shared state.** A node's positions are fixed for its life (line 629). But the node that runs R6 is another node. The only shared record of which cores *X* had is the core words that still name (*X*, *g*), and R6 frees those one by one. The review's replay holds step for step. Cores 2 and 5 are positions 0 and 1. The last stops are at 100 µs and 15,000 µs. At 15,200 µs core 2 is freed. Core 5 is now the only word naming *X*, so it reads as position 0 and gets the instant 100 µs. It is freed 800 µs before `SETTLE_NS` (1 ms) has passed since its own last stop at 15,000 µs. The variant `r6_inflight` that line 1294 names is open again. The abi (`FenceRecord`, abi/src/machine.rs:270-285) keeps the positions. The model avoids the bug only because it keys `last_stop` by core number (`BTreeMap<usize, u64>`, table.rs:166-168), and its comment says so.

**The fix: index by something that does not move.** Gap 7 puts every core of a node in one window of 64 core numbers (line 1364). So *core number* mod 64 is unique within a node and never changes. No new field is needed: the reader knows the number of the core whose word it frees.

**The other sub-claims.** "Nothing states the gate's checks on the record": wrong. Line 1261 says "The first fence action of a generation writes the record anew ...; a driver that takes over keeps it; each stop sent writes its core's word, and the confirmation writes word 2 once". So word 1 is written once per generation, and a faulty driver cannot push the take-over away by writing it again. One point is left implicit and is worth a word: the instants are the gate's clock, not the caller's. "An instant of 0 is unsettled": wrong. "An instant of 0 means none", and no stop sent means no stop in flight. In any case every core whose word names *X* is sent a stop (line 1261: "for each physical core ... stops *p*"), so the case does not arise. The model reads 0 as passing (nodes.rs:1326-1335).

**Correction (exact text).** Line 1261, replace "words 4 to 67, for each position of *X*'s cores (0 to 63), the instant of the last stop sent to that core" with:

> words 4 to 67, for each core of *X*, at index 4 + (its core number mod 64), the instant of the last stop sent to that core (a node's cores lie in one window of 64 core numbers, `node_start`, so the index never changes while R6 frees other words; a position would). The instants are read from the gate's clock.

**What changes in the model.** The doc comment of `abi::FenceRecord` changes from "for each position of the node's cores" to the index by core number mod 64, and the model's conversion to the abi layout uses `core % 64`. Add a test in `scenarios/reviews.rs`: two cores, the first freed first, the second freed no earlier than its own last stop + `SETTLE_NS`. That is the review's replay. It passes in the model today, so it guards the abi layout and a future model that indexes by position.

---

## Finding 3: invalid remote capabilities with a mapping

**The text.** Line 877: "... the slot becomes dead, unless its record holds a mapping: then the slot stays until a removal reaches it (the step of a `Revoke`, R2, or a removal by its holder) ...".

**Sub-claim 1, an unmapping record is not exempt. Partly right.** Line 250 defines unmapping as "a mapping that is **unmapping**". So "holds a mapping" most likely includes it, and the model reads it so (`bury_stale`, lib.rs:1417-1420: `Record::Mapping(_) | Record::Unmapping(_)`). The words still allow the other reading, under which the scenario of the review (a completion aimed at a dead slot) would follow. A remote frame can hold no message page binding (line 879: `thread_configure` refuses a remote frame). So "the record is not empty" says it exactly.

**Sub-claim 2, `gone` stops the holder's own removal. Partly right.** The text does not say whether `cap_delete` is "a use". Line 107 makes `cap_delete` the exception for a dead slot, and line 127 says `cap_delete` "acts on the slot, not on the object". The model treats `cap_delete` as not a use: it does not go through `full` (caps.rs:228-255). Nothing leaks under the strict reading either, because the grant is revoking or its generation is over, so a `Revoke` step or R2 reaches the slot. The contradiction is with the words "a removal by its holder", which `cap_delete` should cover.

**The review's correction** also exempts `cap_revoke`, `aspace_unmap` and `iospace_unmap`. None is needed. `cap_delete` undoes the mapping with its invalidations (line 255), and an unmap by the holder of a capability that is about to be removed adds a second path with nothing to gain.

**Correction (exact text).** Line 877, replace "A use of an invalid remote capability is `gone`, judged with the slot, and the slot becomes dead, unless its record holds a mapping: then the slot stays until a removal reaches it (the step of a `Revoke`, R2, or a removal by its holder)" with:

> A use of an invalid remote capability other than `cap_delete` is `gone`, judged with the slot, and the slot becomes dead, unless its record is not empty (a mapping, or a mapping left unmapping): then the slot stays until a removal reaches it (`cap_delete` by its holder, the step of a `Revoke`, R2, or the removal of an ancestor or of its space)

**What changes in the model.** Nothing; it already reads it this way. A test that `cap_delete` on an invalid remote capability with a mapping undoes the mapping with its invalidations would pin the reading.

---

## Finding 4: the claim that asks each remapping unit in turn

**The text.** Line 998 (gap 12); line 1000, whose list of the fields of an entry is: role, operation, epoch, state, credit, what it completes; line 134 (a destroyed waiter).

**Where the cursor lives. Confirmed missing.** To send the next request, the event that consumes a done needs the PCI segment of the source and the unit it just asked. The entry has the role, which gives the unit, but not the segment. The segment is an argument of the call, kept in the waiting thread's registers, and those are gone once the thread is destroyed. The model added the field (`UnitEntry::segment`, units.rs:57-60) and finds the next unit from it (`next_unit`, units.rs:182-201: the next role, in the order of units, among those serving the segment). The cursor is therefore the entry's role together with the segment. A unit the requester holds itself is served "with no message" (line 1000), and its done is consumed in the same way, so the review's question about local units is answered by that sentence.

**What a failure at the second unit leaves. Nothing leaks, but it is not said, and the rule is wrong.** The model writes the irq entry, the remapping entry and the root capability before the first request (irq.rs:93-136). At *failed* it ends the call `busy` and undoes nothing (`unit_complete`, units.rs:407-432). That was already so with one unit before pass 16. What is new in gap 12 is the sentence "no later unit is asked". The later units are not failed, but their interrupt entry caches keep whatever they held for that handle, so the irq that stays claimed may never deliver through them. Going on to the later units costs nothing: a failed unit stays failed until the machine restarts (line 1409), and asking a working unit is harmless. Undoing the claim at the failure would be worse, because the new root capability may already have been moved by another thread of the node. I keep the irq and say so.

**Who cleans it.** The caller. The irq is an ordinary root capability in its destination, which `cap_delete` removes (line 759: the remapping entry is cleared).

**A destroyed waiter. Unsettled; the model goes on.** Line 134 applies the answer's effect "on grants, records, counts and credits". The next unit of a claim is none of these. The model goes on through every unit (the waiter becomes `Thread(None)`, and `next_unit` does not look at it). That is right, because the irq outlives the thread.

**Correction (exact text).**

1. Line 1000, after "the credit it uses while sent,": insert "for the claim of an MSI the PCI segment of its source,".
2. Line 998, replace "(the entry is used again for the next unit, in the event that consumes the done of the one before). A unit found failed ends the call `busy`, and no later unit is asked; the units already asked keep their invalidation, which is harmless (an invalidation done twice changes nothing)." with:

   > (the entry is used again for the next unit, after the entry's own, in the order of the units that serve the segment the entry records, in the event that consumes the done or the *failed* of the one before). A unit found failed is passed over and the later units are still asked; after the last one the call ends `busy` if any unit was found failed. The irq, its remapping entry and its root capability stay as the claim wrote them before its first request; a caller that does not want them removes the irq. If the waiting thread is destroyed, the later units are still asked (the irq outlives the thread, [The derivation tree](#the-derivation-tree), a thread).

**What changes in the model.** `unit_complete` calls `next_unit` on *failed* too, and the entry keeps one bit "a unit failed" so that the end returns `busy`. Add tests: a failed second unit with a working third unit still asks the third; and a destroyed waiter.

---

## Finding 5: the operands of `UnitRequest`

**The text.** Line 923: "Three: the role (0-15), the epoch (16-44) and the operation (48-55 ...); then two operands, whose meaning the operation fixes (attach and detach: the device identifier; a redirection entry: the global system interrupt, and 1 if claimed or 0 if masked; an invalidation: 0 and 0)". The three words are one word of header and two operands.

**Attach. Confirmed.** G9 (line 1039): the holder's gate writes a context entry "only if the root it names is a top-level iospace table owned by the node that owns the device". So the request must name the root table, and it does not. The domain number is the older gap behind it. Line 362 says the domain number is "given at its first device and freed with its last" without saying by whom. The requester judges "the unit has no free domain number (`busy`)" before it sends (line 360), so the requester must know which numbers are free. Yet the domain numbers of one unit are shared by every node that attaches through it, and the holder "rebuilds the map of domain numbers" (line 1430). Nothing stops two nodes from using one number with two roots on one unit. Translations cached under one domain number would then serve another node's device: DMA into memory that node does not own. The model does not show it: it counts domains per node (memory.rs:819-824) and models no numbers (`UnitOp::Attach { device }`, rings.rs:27).

**My settlement of the domain numbers** (Claude settles contract details): split each unit's domain numbers among the node slots, as the remapping handles are split among the cores (line 996). Node slot *s* owns the numbers 1 + *s* × *d* to (*s* + 1) × *d*, with *d* = ⌊(*D* − 1) / *n*⌋ and *D* the unit's count of domain numbers; 0 stays the kernel's own domain (line 341). Then the requester judges "no free domain number" alone, as written, and the holder's gate checks one range. The alternative, numbers given by the holder and returned in the `UnitAnswer`'s value, needs a fourth result ("no number free") and an undo of the attach at the answer. *D* comes from the unit's capability register (on VT-d, `CAP_REG.ND`: from memory, not checked against the VT-d specification today). A machine whose *d* would be 0 for some unit is refused at start-up. That limits *n* on units with few domain numbers, a cost to state.

**The redirection entry. Confirmed.** A line in remappable format needs the handle, the trigger and the polarity (lines 772-773, 779), and the vector for the EOI of a level line (line 763). Without remapping it needs the APIC ID and the vector. Two words hold all of it.

**The full layout, in the three words.** Word 0 stays as it is (role 0-15, epoch 16-44, operation 48-55). Then:

| Op | Operand 1 | Operand 2 | What the holder's gate checks |
|---|---|---|---|
| 1 attach | device identifier (0-15), domain number (16-31) | physical address of the iospace's root table | G9 as written; the identifier word names the requester; the domain number is in the requester's range |
| 2 detach | device identifier (0-15), domain number (16-31) | 0 | the context entry names that domain; the identifier word names the requester |
| 3 invalidation of translations | domain number (0-15) | 0 | the domain number is in the requester's range (a domain-selective invalidation in place of the global one) |
| 4 invalidation of the interrupt entry cache | handle (0-15) | 0 | the handle lies in the range of a core whose word names the requester (index-selective, mask 0) |
| 5 redirection entry | GSI (0-31), 1 claimed or 0 masked (32), trigger (33), polarity (34) | remapped: handle (0-15) and vector (16-23); not remapped: vector (16-23) and APIC ID (32-63); masked: 0 | the handle, or the APIC ID, names a core whose word names the requester |

The interrupt entry cache descriptor of VT-d has a granularity bit (global or index-selective), a 16-bit index and a 5-bit index mask. I found this in QEMU's `intel_iommu_internal.h`, as the search returned it, citing VT-d §6.5.2.7; I did not read the specification itself today. The format of the IOAPIC entry in remappable form is from memory.

**Entry counts and reserve.** Still three words: ⌈(16 + 24) / 64⌉ = 1 entry. `RING_MESSAGE_ENTRIES_MAX` (11) and the reserve of answers (34) do not change.

**The review's correction judged.** Its attach (the identifier and the domain in operand 1, the root in operand 2) matches mine. It leaves open who gives the domain number, which is the half that matters for safety. Its operation 5 omits the vector under remapping.

**What changes in the model.** `UnitOp::Attach` carries the domain number and the root; `Detach` the domain; `Invalidate` the domain; `InterruptCache` the handle; `Redirection` the trigger, the polarity, and the handle or the APIC ID with the vector. Add the per-node ranges of domain numbers at boot, refusing a layout with *d* = 0. Add the holder's range checks in `submit_for` (units.rs), with one test per check refusing a number or handle of another node.

---

## Finding 6: the order of L2 and its bound

**The text.** Line 648: the order "the sequence words of `cspace` segments ...; task; thread; endpoint; reply; notify; timer; `sched`; aspace; iospace; the lock words of cores ...; the gate lock", and: "no call needs a lock of an earlier kind after a later one".

**Why the model did not see it.** `locks.rs` collects every lock an event touched and checks them "taken in the order of `LockId` before the event changes anything" (locks.rs:14-18). That assumes a call knows its whole set of locks before it reads any object. A kernel finds most locks by reading an object that it must already hold locked. A check over a set that has been sorted cannot fail on the order.

**Each call the review names:**

1. **Destroying an aspace (line 318). Inverts.** The aspace's list of records is read under the aspace's lock, and the records are slots (segment locks, earlier). The bound threads are thread locks, also earlier. Destroying an iospace (line 364) is the same. Confirmed.
2. **Destroying a `sched` (line 527). Inverts.** The chain of lends runs through reply objects (reply, earlier than `sched`), and each receiver loses its context (thread, earlier). Confirmed.
3. **`send` on a reply object and `reply_recv` (lines 202-203). Inverts.** The caller is found from the reply object (thread, earlier than reply), and the capabilities go into its receive segments (earliest). **`call` (line 200) inverts too**, on the common path: the receiver is found in the endpoint's queue (thread, earlier than endpoint). Confirmed. These two show that **no total order by kind can hold**. A delivery goes from the endpoint to the thread, while `thread_cancel` or `thread_suspend` of a waiting thread goes from the thread to the endpoint it waits on. An answer goes from the reply to the caller's thread, while `call` goes from the receiver's thread to the reply it arms.
4. **An interrupt arrival (line 744). Partly right.** The core lock is held for the entry (line 646). The notify's word is updated by one atomic OR with no lock (line 643), so the arrival can release its core lock before it takes the notify's lock to wake a waiter. With that order the arrival is in order up to the notify. The wake then finds the waiting thread under the notify's lock (thread, earlier), which inverts, as `signal` does. Destroying a notify (line 757) inverts toward its bound endpoint. Its walk over the irq entries takes core locks, which come later and are counted in *k* ("plus one per core"), so the review's "outside *k*" is wrong.
5. **`task_revoke` (line 1101). The order holds; the review is wrong there.** Task, then thread, then the endpoint, notify or reply the thread waits on: each is later. Only *k* is in question (below). **`cap_move`, `cap_derive` and the lists (lines 254, 1903): inverts.** The neighbours in the derivation list and in a space's list of records are found from the slot moved or derived from, and they lie in any segment, earlier ones included. Confirmed.

**The bound *k*. Partly right.** "The number of objects and slots its rules name" does not say whether the links a removal step undoes count. The model counts them: `locks::bound` gives 4 × (32 + 64) + 8 for a removal step, 4 × 32 + 8 for `task_revoke`, 16 for IPC and 12 for the rest (locks.rs:158-169). The contract should say the same.

**The rule that holds.** No order by kind serves every call, so the exceptions need a rule.

> **The order of L2 and its bound (gap 5).** A core *waits* for a lock only in the order by kind: the sequence words of `cspace` segments, by space then segment (the state of an `untyped` with them, under the lock of its root's segment); task; thread; endpoint; reply; notify; timer; `sched`; aspace; iospace; the lock words of cores, by position; the gate lock; two locks of one kind in the order of their objects' addresses. A lock that a call finds by reading an object it holds locked (the thread at the head of a queue, the caller armed in a reply object, a slot next to another in the derivation list or in a space's list of records, a reply object or a thread of a chain of lends, the endpoint bound to a notify, the records and threads of a dying aspace or iospace), and that comes before a lock the call holds, is taken by a *try*, which never waits. If a try fails, the event releases every lock it holds, having changed nothing, and runs the call again from its look-up, now taking the lock it found in its place in the order, and then checks that it still finds that object where it found it; if not, it goes on with what it now finds, by the same rule. A removal step and a step of `task_revoke` instead return `again` with nothing changed. An arrival releases its core's lock before it takes a notify's lock. A call's *k* is the most locks it holds at once, the locks it found included: for a step of a removal 4 × (32 + 64) + 8, for a step of `task_revoke` 4 × 32 + 8, for `call`, `reply_recv`, `send` and `node_send` 16, for every other call 12 (`locks::bound` of the model).

**Why no call can deadlock under it.** A deadlock needs a cycle of cores, each waiting for a lock that the next one holds. Under the rule a core waits only for a lock that comes after every lock it holds in the order: a try never waits, and a failed try releases everything. Take any core in such a cycle. It holds lock *a* and waits for *b*, with *a* < *b*. The core holding *b* waits for some *c* > *b*, and so on around the cycle. The order would then have to increase strictly all the way round and come back to *a*, which is impossible in a total order. So no cycle exists. The queue locks of line 650 serve each waiter after at most *N* − 1 holders. The gate lock stays last and is taken with no other lock after it.

**What I do not prove.** I have no per-call bound on the number of runs again. Each run again needs another core to have changed, between the release and the new look-up, the link through which the call found the lock. My argument that this happens at most *N* − 1 times per found lock under queue locks is an argument, not a proof. Until the model checks it, the bound of line 653 holds for L1 and not for L2. That is one more reason to choose the variant after the measures, as line 639 says. Two cheaper refinements are open to the owners. (a) Guard a waiting thread's wait and queue links by the lock of the object it waits on, so that a delivery or an answer needs no lock of the thread it finds. (b) Put the segment locks last among the objects, since a look-up is lock-free in both variants (line 643). Together these would put the IPC common paths in order and leave the tries to destruction, revocation and list surgery, which is the owners' rule: the cost at the rare event. I have not traced every call under (a) and (b), so I do not write them as contract text.

**What changes in the model.** `locks.rs` must record the locks in the order an event finds them, not sort them. A lock reached through an object already locked is marked *found*. The check then fails on a wait out of order, on a found lock earlier than a held one that was not taken by a try, and on more than `bound` locks held at once. The exploration then needs interleavings of two cores on one endpoint (a delivery against `thread_cancel`) and on neighbouring slots (`cap_derive` against `cap_move`), to exercise the runs again.

---

## Finding 7: one window of 64 cores against the one-node fallback

**Confirmed, as an edge case.** Line 1950: "the machine then runs one node, on every usable core if the image supports that many". Line 1364: a node's cores lie in one window. Core numbers are dense positions in the full core list (line 2024), so the usable cores span two windows only when the list has more than 64 entries and some are unusable. An example: 65 cores, one of them unusable, 64 usable. Then "every usable core" cannot be named by one window and one mask. The side note is right too and older than pass 16: line 1950 omits the condition of line 1947 (one node holds cores of the same state features and vector lengths). The review's correction, "the largest subset in one window containing the booted core", adds a search the start-up does not need. All or the booted core is enough.

**Correction (exact text).** Line 1950, replace "on every usable core if the image supports that many and on the core firmware booted otherwise" with:

> on every usable core if they lie in one window of 64 core numbers, have the same state features and vector lengths, and are no more than the image supports, and on the core firmware booted otherwise

**What changes in the model.** The default layout of a machine with a core of class 0 applies the same test. I did not check `boot.rs` for it.

---

## Finding 8: the own-core watch

**Sub-claim 1, `observations[8]` cannot hold 63 siblings. Wrong reading, but it points at a real gap.** The watch ends in self-accusation (evidence self, line 662), which the gate checks through `panic`, not through an observation. "By the rule of stale evidence" names the conditions (an unchanged heartbeat for `STALE_NS`, now − `STALE_NS` > `idle_until`), not the gate's record. The real gap is "what it last saw": the per-core part (line 631) has no field for it. The model keeps one pair (heartbeat, instant) per other core in the watching core's part (`watched`, cores.rs:615-620), up to 63 pairs of 16 bytes (1,008 bytes per core part). I did not check that this fits the node block's layout.

**Sub-claim 2, idle siblings never watch. Right as an unsettled latency.** A core runs the heartbeat event only while it runs a thread (line 573). When core 0 hangs while running and every other core is idle with nothing armed, nobody inside the node watches. The sweep of the other nodes finds the silent core by stale evidence (line 1254), within about `SWEEP_NS` + `STALE_NS`. Waking idle cores every `STALE_NS` would pay on every idle period, against the owners' rule. On a machine of one node no other node sweeps, and nothing finds the silent core until a sibling wakes. Then there is no other node to recover anyway, and a silent core that holds a lock is found by `CORE_ANSWER_NS` as soon as a sibling needs that lock.

**Correction (exact text).**

1. Line 631, after "its save slot for the debugger stub": insert "; the heartbeat and the instant it last saw of each other core of the node (gap 16)".
2. Line 662, replace "(each core of the node compares, at each of its timer events, the heartbeats of the node's other cores with what it last saw, by the rule of stale evidence, gap 16)" with:

   > (each core of the node compares, at each of its timer events, the heartbeat of each other core of the node with the heartbeat and instant it last saw of it, kept in its own part: an unchanged heartbeat for `STALE_NS` while now − `STALE_NS` > that core's `idle_until` is a silence, which needs no observation of the gate, since the node accuses itself; when every other core is idle with nothing armed, no core of the node watches, and the silent core is found by the sweep of the other nodes, gap 16)

**What changes in the model.** Nothing in behaviour. The `watched` field becomes part of the per-core layout the model mirrors.

---

## All corrections, in order of severity

1. **Finding 1, the NMI rules (breaks a guarantee).** The node kernel's NMI handler parks only on a marked word or a node that can no longer write. The stub's NMI handler writes `parked` only from its own loop. The entry stub installs the kernel's handler before it reads its core word (x86-64's arming). This closes a false confirmation older than pass 16 and makes the late wakes of pass 16 harmless.
2. **Finding 2, the fence record indexed by core number mod 64 (breaks a guarantee: `r6_inflight`).**
3. **Finding 1, the start request (breaks a guarantee and blocks building).** Its layout (bit 63, slot in 32-47, generation in 0-31). The stop condition on the generation. The writer of `started` on ARM64 and RISC-V. G10's check of the mark and of the starting generation.
4. **Finding 5, the domain numbers split per node slot, and the operands of the five operations (blocks building; a shared domain number would break the isolation of DMA).** Still one entry; reserve unchanged.
5. **Finding 6, the rule of L2 (the order as written deadlocks).** Waits only in the order by kind; found locks by try; a failed try releases everything and runs again (`again` for removal and `task_revoke` steps); *k* as `locks::bound`. Deadlock-free as shown. The bound of the runs again is to be checked in the model.
6. **Finding 4, the unit sequence (blocks building).** The segment in the entry; failed units passed over, `busy` at the end; the irq stays; a destroyed waiter's claim goes on.
7. **Finding 3, `cap_delete` and "not empty" in line 877 (ambiguity).**
8. **Finding 7, the one-node fallback in one window and with like cores (contradiction, edge case).**
9. **Finding 8, the field "last seen" and the idle fallback (unsettled case).**

## What I checked and found correct in the review

- All quotes are verbatim at their lines.
- The arithmetic of finding 2's replay (800 µs early), and the replay itself.
- Finding 3's reading of lines 107 and 127, and that the gap was introduced by the gap-15 text.
- Finding 5's reading of G9 (line 1039) and of line 779.
- Finding 6's sub-claims 1, 2 and 3, and the cspace-list part of 5.
- Finding 7's replay and its side note.

## What I did not check

- The review's own list of things it found correct (gaps 1, 2, 4, 9, 10, 11, 13 and 14, the message arithmetic, and its SDM citations). The message arithmetic I recomputed only for `UnitRequest`.
- The VT-d specification itself (the domain-number register, §6.5.2.7) and the IOAPIC's remappable format: from memory or from secondary sources, as stated above.
- PSCI DEN0022 §5.6, which I did not read in full: ALREADY_ON and ON_PENDING are taken from the search results quoting its revision history.
- The arbitration of a line claimed by two nodes on one IOAPIC (finding 5, operation 5).
- The invalidation sequence after an irq's removal on a machine with several units.
- Whether 1,008 bytes per core part fit the node block.
- The contract outside the sections listed at the top.

Sources read on 16 November 2026: [SBI HSM](https://docs.riscv.org/reference/sbi/ext-hsm.html); [QEMU `intel_iommu_internal.h`, the IEC descriptor](https://git.cs.tu-dortmund.de/SYS-OSS/FRET-qemu/src/commit/2c02468c9b1750aaa5fbeee49cdb55f101608c6a/hw/i386/intel_iommu_internal.h) (secondary); the PSCI revision history as quoted by the [Arm documentation service](https://documentation-service.arm.com/static/60feb9bf3d73a34b640e1b67) result.
