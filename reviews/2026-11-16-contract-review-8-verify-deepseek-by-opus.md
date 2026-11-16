# Verification of review 8 (deepseek): inside a node of *N* cores

Judged: [2026-11-16-contract-review-8-deepseek.md](2026-11-16-contract-review-8-deepseek.md), 15 findings.
Contract read: [kernel-interface.md](../architecture/kernel-interface.md) at Docs commit `9e6e188` (after `git pull`, already up to date).
`git diff fa90461..9e6e188 -- architecture/kernel-interface.md` is empty, so the reviewer's line numbers are the current ones, and every line number below is one of them.
My explorer: `/tmp/verify8-opus/explore.py`, run with `timeout 60 python3 -B -I explore.py`. Its output is quoted where it is used.
The reviewer's script (`scratchpad/review8/deepseek/check.py`) is judged in the last section.

## Table of verdicts

| # | Verdict | Severity (mine) | Correction in one line |
|---|---|---|---|
| 1 | CONFIRMED IN PART | unspecified. Read literally, it blocks for ever; dropped, it is unsafe | G12's flush epoch cannot be met by anyone. Replace it with "no invalidation of the node in flight" (see new finding N2). The reviewer's reason ("an idle core holds no translation") is false |
| 2 | CONFIRMED IN PART | unspecified (two sentences contradict each other) | Add the mark to *runnable* (line 475). Line 647 already settles what must happen, so the two-cores scenario is not allowed by the text |
| 3 | CONFIRMED | unspecified. One reading breaks isolation | Lines 250 and 273/295 must name *unmapping* as full and `busy`, as lines 327 and 1589 already do |
| 4 | CONFIRMED IN PART | wrong result (lost interrupt) for `irq`. Wording for `untyped` | An `irq` entry is guarded by its core's lock word, which already exists, not by the gate lock. An untyped's state lives in a slot, so the slot's segment lock already guards it |
| 5 | CONFIRMED IN PART | breaks isolation (`CnP`). Wording (domain) | State `CnP` = 0. State the single Inner Shareable domain as an assumption: no register reports it, so start-up cannot check it |
| 6 | CONFIRMED IN PART | wrong result: the node accuses itself for a fault of a unit | The wait for an IOMMU unit must not be inside a hold. The audit part falls: recovery runs in steps of 32 units |
| 7 | NOT A FAULT | — | Lines 325 to 328 are under "Several cores of one node", and line 333 settles it: "A node of one core: nothing beyond the one-core rule" |
| 8 | CONFIRMED IN PART | wrong result (second suspend) | A second `thread_suspend` waits for the same mark. A concurrent resume is an ordinary race, not a fault |
| 9 | CONFIRMED IN PART | wrong result: the machine stops | The hole is real, but it is not L2's. The audit runs in steps on every node, *N* = 1 included, so the proposed fix does not close it (see N3) |
| 10 | CONFIRMED IN PART | unspecified (the bound) | The gate lock is last in L2's order and is counted in *k*. The reviewer's clause "a gate call never acts on an object whose lock its caller holds" would forbid `aspace_map` |
| 11 | CONFIRMED IN PART | wording | The contract's rules are right. The library paragraph (line 937) must say that the grant asks for `send` |
| 12 | CONFIRMED | wording | Line 935: "rule 7 in its old form" |
| 13 | CONFIRMED IN PART | wording | Items 1 and 2 hold. Item 3 falls: object interiors are not published |
| 14 | CONFIRMED | wording | Line 92 names the second numbering, by position in the node |
| 15 | CONFIRMED | wording | `busy` for a full grant table. Add `send` on a frame to the table of rights |

New findings (siblings): N1 breaks isolation (kernel-space unmapping at a give is invalidated on one core only). N2 unspecified: the flush epoch has no storage, and no core's epoch moves on ARM64. N3 wrong result (the audit in steps, on every node). N4 unspecified (an `iospace_unmap` waiting for its unit has no record state). N5 unspecified (L2: the iospace's lock word is not reserved; suspicion on the `iommu` list).

Count: CONFIRMED 4 (3, 12, 14, 15); CONFIRMED IN PART 10 (1, 2, 4, 5, 6, 8, 9, 10, 11, 13); NOT A FAULT 1 (7); IMPOSSIBLE SCENARIO 0; NOT VERIFIED 0.

---

## Detail

### 1. An idle core and the flush epoch: CONFIRMED IN PART

**What the reviewer gets right.** Line 979 says each core's flush epoch is incremented "only [by] its gate … at each full invalidation of its TLB and at each acknowledgement of an invalidation". Line 328 says an idle core "is sent no interrupt", so it acknowledges nothing. An idle core with no armed instant "takes the deepest state" (line 614), and its wake sources are listed at line 616. None of them is an invalidation. So under G12's rule ("every core of the node past the epoch recorded when the count reached zero"), a give can wait for as long as the core stays idle.

**What falls.**

- **No contradiction between lines 327 and 328.** "Every acknowledgement is in" means every acknowledgement that was asked for. Line 644 says so ("an idle core is not waited for"), and so does line 1355 ("an idle core is never waited").
- **"Refused for ever" is one reading, not the text.** The state checks of `memory_give` at line 836 refuse only on a map count ("`busy` if the gate refuses the give … a map count is not 0"). G5 adds "The gate does the invalidation itself" (line 972). So the text does not say that a give is refused for an epoch. It says nothing about what the gate does on several cores. It cannot wait: `memory_give` is not among the calls that wait (line 644), and the gate lock is "never [held] across a wait for another core" (line 979).
- **The fault is wider than idle cores.** My explorer (`epoch_check`) applies line 979 literally after one unmap, with core 0 the caller, core 1 active in the tag set, core 2 idle and core 3 never having loaded the tag:

  ```
  G12 epoch, owed work as written: [('x86-64', [0, 2, 3]), ('ARM64', [0, 1, 2, 3])]
  ```

  The list gives the cores still behind. The caller's own range invalidation is neither full nor an acknowledgement. A core outside the tag set acknowledges nothing (line 325 sends only to "every core of that set"). On ARM64 there is no acknowledgement at all ("No interrupt and no wait", line 326). With the reviewer's change (owed work counts), x86-64 still leaves cores 0 and 3 behind.
- **The reviewer's reason is false.** The reviewer writes that an idle core "holds *no* translation of any address space of the node". Loading another root does not remove entries tagged with other PCIDs. Intel SDM Vol. 3A §4.10.4 ([mirror, p. 4-43](https://xem.github.io/minix86/manual/intel-x86-and-64-manual-vol3/o_fe12b1e2a880e0ce-147.html)): "additional steps are required if the entry may be used for PCIDs other than the current one". What makes an idle core safe is the other half of line 328: it does what it owes "before it loads a root of the node again". So no entry under the node's tags can be used before that.

**Correction.** Needs a decision of the owners, because it changes G12. My recommendation is in N2: withdraw the flush epoch and replace it with "no invalidation of the node in flight".

### 2. A thread marked *leaving its core*: CONFIRMED IN PART

The definitions at lines 475 and 476 and the choice at line 533 do not know the mark. So the mechanism allows the new core to choose the moved context. Line 647, however, settles the outcome in plain words: "While the mark is set, no core runs the thread … `sched_configure` that moves a context waits for nothing, and its holder runs on the new core once the mark is clear." So the text does not allow two cores to run the thread. It contradicts itself, and an implementer who reads only the scheduler would get it wrong. That is "unspecified", not "breaks isolation". It also concerns one thread of one process, not a boundary between protection domains.

The reviewer's fix is sound and consistent with the rest of the text. When the mark clears, the context becomes eligible, and line 628 then sends the reschedule interrupt to its new core. That is exactly line 647's "runs on the new core once the mark is clear".

**Correction (ready to paste, line 475).** "A thread is **runnable** when it is not suspended, does not wait, and is not marked *leaving its core* ([A node of several cores](#a-node-of-several-cores)); the event that clears the mark makes its context eligible on the core where it is now placed."

### 3. The record *unmapping*: CONFIRMED

There is a direct contradiction for `aspace_unmap`. Line 327 and the `abi/` list at line 1589 say: "`Busy` on an unmapping record". The call table (line 273) and the effect's checks (line 295) refuse only "if the record names an `iospace` or a thread". For `aspace_map` the reviewer's bad reading is the weaker one: line 1782 defines kind 3 as "a mapping whose entries are cleared", so it is full under line 287. But line 250 lists only two kinds of full record, so the text should say it.

Under the bad reading the result is worse than the reviewer writes. A fresh leaf is left with no record. The frame is destroyed once "every record of it is empty" (line 327), and its memory goes back to the untyped while a user leaf still points into it. A later retype into a kernel object, which stays in class *data*, is then mapped by a user process. Two notes on the reviewer's trace: "no leaf in any table" in their script's printed end state is wrong (the leaf stays and the record goes), and the script drops the leaf at the acknowledgement.

**Correction (line 250, second sentence).** "A full record is a **mapping**, a **message page binding**, or a mapping that is **unmapping** (its entries cleared and its invalidation on other cores of the node in flight, [TLB](#tlb-one-core-and-several)); `aspace_map`, `aspace_unmap` and `aspace_protect` are `busy` on an unmapping record, and a removal that reaches it returns `again`."

**Correction (line 273 and the checks at the end of line 295).** "`busy` if the record names an `iospace` or a thread, or is unmapping".

### 4. L2 with no lock word for an `untyped` or an interrupt entry: CONFIRMED IN PART

- **`irq`: confirmed.** An arrival on core *b* changes `armed`, `fired` and `pending` (line 737). `irq_ack` (line 731) and `irq_bind` (line 730) do the same from any core, and line 622 says so ("except the interrupt table, which the node's kernel writes for any of its cores"). L2's list (line 635) names no lock for an entry, and an arrival is not "a call". My explorer (`irq_check`) interleaves one arrival with one `irq_ack` on a fired edge entry:

  ```
  F4 irq entry, L2, no lock: ['arr:read', 'ack:read', 'arr:write', 'ack:write'] (2 losing orders)
  F4 irq entry, locked: no trace (0 losing orders)
  ```

  The arrival sets `pending`, then the acknowledgement writes back `armed` with `pending` 0. The arrival is lost, and an edge source is never masked (line 725), so nothing records it again. The severity is wrong result, not breaks isolation.
- **The reviewer's fix is the wrong lock.** The gate lock guards the gate's writes (G1), and an `irq` entry is not gate state. Taking the node-wide gate lock on every arrival puts the interrupt path behind every mapping change of the node. The layout already has the right lock: line 622 gives each core "its lock word (variant L2 below)". The entries are in that core's table, and the arrival takes it on its own core.
- **`untyped`: the race falls, the wording stays.** The watermark and the clean mark are words 2 and 3 of the capability slot (line 1783). L2 already makes "the sequence word of each `cspace` segment … its writers' lock" (line 635). So two `untyped_retype`s on one untyped capability write the same slot and take the same segment lock. What remains is that line 635 lists "untyped" among objects with "a lock word in each object", and there is nowhere to put one (lines 637 and 1743 to 1757). A suspicion I did not settle, outside this angle: copies of an untyped exist ("a root or a copy", line 120; "it can hold a copy of it, and so grow itself", line 122). If copies in different segments share one watermark, the segment lock does not serialise them.

**Correction (after line 637).** "Two kinds of state have no lock word of their own in variant L2: the state of an `untyped` (its watermark and clean mark, words 2 and 3 of its capability's slot) is guarded by the lock of that slot's segment; an entry of a core's interrupt table is guarded by that core's lock word, which an arrival takes on its own core and `irq_claim`, `irq_bind`, `irq_ack` and the removal steps of an `irq` or a notify take from any core, counted in *k*." In line 635, delete "untyped" from the list in parentheses.

### 5. The ARM64 broadcast and `CnP`: CONFIRMED IN PART

- **`CnP`: confirmed.** The words `CnP` and `TTCNP` appear nowhere in `kernel-interface.md` or `kernel.md` (checked with grep). Only the draft `kernel-shape-opus.md:267` says "stays 0". Arm, `TTBR0_EL1.CnP` ([mirror](https://df.lth.se/~getz/ARM/SysReg/AArch64-ttbr0_el1.html)): with 1, PEs "for which the value of TTBR0_EL1.CnP is 1" and the same ASID must point to the same entries, "If … those TTBR0_EL1s do not point to the same translation table entries … the results of translations are CONSTRAINED UNPREDICTABLE". Also: "On a Warm reset, this field resets to an architecturally UNKNOWN value". So the kernel must write it. G7 (line 974) gives tags "from one table per node", so two nodes can give one ASID to different tables. `TTBR0_EL2` has the same field ([mirror](https://df.lth.se/~getz/ARM/SysReg/AArch64-ttbr0_el2.html)), and that matters because line 326 runs at EL2. With `CnP` = 0, line 326's "never safety" is right, since a broadcast only removes entries.
- **The domain: wording, and the proposed fix cannot be built.** Arm's text that the contract quotes is about one domain. All PEs under one operating system being in one Inner Shareable domain is an expectation of the architecture. I found it only in secondary sources that quote DDI 0487 B2.8.1 (search result: "The architecture assumes that all PEs that use the same operating system or hypervisor are in the same Inner Shareable shareability domain"), so it is not verified at the primary source. The same sources say that no register reports a PE's domain. So "the machine start-up records each core's domain as a value of the machine" cannot be built. Besides, the whole machine table (CAS on member words, ownership words) needs coherence between all the machine's cores, not just a node's. A machine split into two Inner Shareable domains breaks far more than the TLB, so the rule belongs among the machine's assumptions.

**Correction (append to line 326).** "The kernel writes `CnP` = 0 in every translation table base register it loads (`TTBR0_EL1` and `TTBR1_EL1`, or their EL2 forms), since two nodes may give one ASID to different tables and `CnP` = 1 would then make translation CONSTRAINED UNPREDICTABLE (Arm, `TTBR0_EL1.CnP`; its value after a warm reset is UNKNOWN). The contract assumes that every core of the machine is in one Inner Shareable domain, as the architecture expects of the cores under one system; no register reports a core's domain, so the machine start-up cannot check it."

### 6. *H* and what a hold may contain: CONFIRMED IN PART

- **Confirmed: a unit wait is inside an event.** Line 902: "The kernel ring is served in the receiver's recovery reserve … since a unit request may wait for its unit (at most `IOMMU_WAIT_NS`)". Line 910 says the same: "a `UnitRequest` (one unit operation and its wait, at most `IOMMU_WAIT_NS`)". Line 365: "The kernel waits for the confirmation". Line 644 takes only waits "for another core" out of a hold. Under L1 the node lock is "held for one kernel event, from entry to exit" (line 634). So *H* ≥ `IOMMU_WAIT_NS` = 1 ms (line 1566) on a node that holds a unit role or that unmaps on its own unit.

  The consequence: (*N* − 1) × 1 ms reaches the default `CORE_ANSWER_NS` of 10 ms at *N* = 11. With the floor of its allowed range, 1 ms (line 1355), it is reached at *N* = 2. The trigger is a unit that is slow to confirm. Line 365 calls that "a hardware fault of the unit, not of a node", yet the node then accuses itself through line 651. That contradiction is the real fault.
- **Falls: the audit as seconds in one event.** Line 1220 says the steps R2 to R5 are finished "in steps of its recovery reserve", and line 1249 says "in steps of at most 32 units". So the audit is not one event. (It has another fault, N3.)
- **Overstated: "routine contention".** A healthy unit confirms well under the timeout (not measured in the contract). The case that matters is a slow unit, which is exactly the case line 365 wants contained.
- **The second gap (a call that both locks and waits)** is wording. The two bounds simply add up.

**Correction (append to line 644).** "No lock is held across a wait for an IOMMU unit either: a call, a removal step or a step of the recovery reserve that must wait for a unit's confirmation ends its kernel event in the state *waiting for its unit* and is resumed at the confirmation or at `IOMMU_WAIT_NS`, so *H* and *h* contain no wait for hardware; a call that both locks and waits is bounded by the sum of the two bounds."

**Correction (line 1355).** Add: "An image accepts no node whose (*N* − 1) × *H* reaches its `CORE_ANSWER_NS`, with *H* as measured for the image."

### 7. *N* = 1 pays for the idle mark and the tag set: NOT A FAULT

Lines 325 to 328 are sub-items of the item "**Several cores of one node (D-128, D-129)**" (line 325). The idle mark and the core set are protocols of several cores, and line 620 leaves them out: "leaves out the protocols", with the list in parentheses giving examples, not a complete list. Line 333 settles it: "**Cost.** A node of one core: nothing beyond the one-core rule." At most, line 620 could add "and every protocol of [TLB](#tlb-one-core-and-several) for several cores". Even if the reviewer were right, the claimed severity ("unbounded kernel operation") would be wrong: a constant cost is bounded.

### 8. Resume or a second suspend during a suspend's wait: CONFIRMED IN PART

- **Second suspend: confirmed.** Line 180 says both calls "succeed when the thread is already in the state asked for", and that a suspend "returns only once that core has left it, so that a suspended thread executes nothing". A second `thread_suspend` on another core finds the flag set and returns at once while the thread still runs on *b*. My explorer (`suspend_check`) gives `['suspend#1 on core 1: flag, mark, wait', 'suspend#2 on core 2 returns ok', 'thread still executing on core b']`, and no trace once the second suspend waits for the mark.
- **A resume during the wait: not a fault.** Two holders of `manage` race. The outcome (running after both return) is that of the order suspend-then-resume, which is allowed on one core too. Making `thread_resume` `busy` is not needed.
- **Register calls: the outcome is unspecified, the rule is not.** Line 647 already forbids it: "no call reads or writes its registers". Lines 179 and 440 do not give the error.

**Correction (line 180, after "so that a suspended thread executes nothing").** "A `thread_suspend` that finds the thread already suspended but still marked *leaving its core* waits for the same mark; `thread_read_regs`, `thread_write_regs` and `thread_configure` are `busy` on a thread so marked."

I checked that `thread_write_regs` exists as a call name: grep finds it in the call table.

### 9. The audit under L2: CONFIRMED IN PART

The hole is real, but it is not specific to L2. Line 1220 says the audit is done "in steps of its recovery reserve". Between two steps, other contexts run on every node (line 1249: bandwidth 1/64, "its time is slack and goes to others"). A chunk's map count counts leaves anywhere in the node's tables, so one comparison cannot fit in one step of 32 units. So even with *N* = 1 and L1, a mapping between two steps makes a mismatch, and "the machine stops with a stop record" (line 981). See N3 for the trace and the correction. The reviewer's fix ("the gate lock for each step") does not close it, because the comparison spans steps.

### 10. The gate lock in the lock order: CONFIRMED IN PART

- **Confirmed: the bound does not count the gate lock.** Under L2, line 979 says the gate lock "is what orders gate calls from different cores", but line 642 counts only the *k* object locks.
- **Suspicion only: the deadlock.** No path in the text takes an object lock inside a gate call. G1 (line 968) lists what the gate writes: entries, gate words, classes, shared words and the grant and use tables, none of them an object lock. The examples in the report ("a gate call that wakes a thread …") are not in the text.
- **Part of the reviewer's fix is wrong.** "A gate call never acts on an object whose lock its caller holds" would forbid `aspace_map`, which holds the aspace's lock while the gate writes that aspace's tables.

**Correction (line 979, after "held for one gate call").** "With variant L2 the gate lock is the last lock of every order: a call takes it after the object locks of its order, takes no other lock while it holds it, and counts it among its *k* locks, with *h* at least the longest gate call."

### 11. `send` for `grant_signal`: CONFIRMED IN PART (wording)

The rules are consistent. Line 917 asks for `send`. The anchor's rights are "the rights the item asks" (line 867), and a capability's rights are independent of a mapping's rights, so the grant can carry `read` and `send` while the peer maps the ring read-only (line 937). Nothing is broken. The only gap is that the library paragraph that describes connections does not say to ask for `send`.

**Correction (line 937, after "with the grant of its request ring").** Insert ", asking `read` and `send` for it".

### 12. Rule 7 withdrawn and in force: CONFIRMED (wording)

Line 935 says "Rule 7 is withdrawn (D-128)", while line 17 is a live rule 7 that lines 200, 752 and 1702 cite. The reviewer's text is fine.

**Correction (line 935).** "Rule 7 in its old form is withdrawn (D-128); rule 7 of [Rules](#rules) stands in its place."

### 13. Lists of values: CONFIRMED IN PART

- **Item 1: confirmed.** Line 1922 has "the layout version (0)" and then "the layout version is 1 since D-129" in the same cell. Delete "(0)".
- **Item 2: confirmed.** `git show 8c2adef:abi/src/debug.rs` in `dodos-kernel` gives "/// The header of a debug area, then the node's crash record." (line 7), `NODE_CRASH_RECORD_BYTES` (line 9) and `struct NodeCrashRecord` (line 138). The `abi/` list at line 1615 does not rename them. The reviewer's sentence can be pasted as written.
- **Item 3 falls.** The contract publishes only the sizes of kernel objects (lines 1743 to 1757), never their internal offsets. User space never reads an endpoint's words, so a lock word's offset is not interface.

### 14. "The only numbering of cores": CONFIRMED (wording)

Line 92 says "It is the only numbering of cores in this contract". Line 622 numbers "the core's position *j* in the node (0 to *N* − 1, in the order of core numbers)". The reviewer's sentence can be pasted as written.

### 15. `no_memory` and `send` on a frame: CONFIRMED (wording)

Line 1729 says `no_memory` means "The supplied untyped memory is exhausted". The grant table is fixed (`GRANTS` per node slot, line 1757), and the call supplies no memory. `busy` (line 1731) fits a state that clears when grants are freed. The table of rights (line 1712) says `send` means "Call or send on an endpoint; signal a notification" and nothing about frames. The reviewer's two sentences can be pasted as written.

---

## New findings

### N1. A give or a destroyed block is unmapped from the kernel's own space on one core only: breaks isolation

Line 838 (effect of `memory_give`): "A run is unmapped from the kernel's own space, the local translations are invalidated, and each word becomes *free* (node)". Line 842 says the same for the destruction of a block. The kernel's own space is shared by the node's cores (line 624: "its address spaces, their tables"; G1 at line 968). Line 834 maps a run there "with large entries", and an idle core runs on "the kernel's own root" (line 328), so it uses those translations. The TLB rule for several cores (line 325) covers only "an unmap, a protect, the removal of a record, the first step of the destruction of an aspace", which are user spaces.

The scenario: core 0 gives a run to node *Y* and invalidates locally, and the words become *free*. *Y* takes the run and uses it. Core 1 of node *X* still holds a writable kernel translation of it. A fault in *X*'s kernel on core 1 then writes into *Y*'s memory without passing the gate. That is the containment G3 promises ("a *free* chunk is never mappable"). This is a sibling of finding 1: the same "local" invalidation, left over from the one-core text.

**Correction (line 838, replacing "the local translations are invalidated").** "the translations of the run in the kernel's own space are invalidated on every core of the node, idle ones included, before any word is written (ARM64: by broadcast inside the gate call; x86-64 and RISC-V: by the invalidation interrupt, the call waiting in *waiting for its node's cores*, and a removal step returning `again` until every core has acknowledged)". Line 842 gets the same clause, and line 644's list of the calls that wait gets `memory_give`.

### N2. The flush epoch of G12 has no storage, and on ARM64 no core's epoch ever moves: unspecified

G12 (line 979) compares each core against "the epoch recorded when the count reached zero". A chunk's gate word holds the map count in bits 0-31 and the class count in bits 32-44, and "the other bits are 0 (`GateWord` of `abi/`)" (line 971). No other per-chunk word exists (line 1757). So there is nowhere to record it, and the epoch would be a vector of *N* values. My explorer (finding 1) shows that, as written, the caller's epoch, the epoch of a core outside the tag set, and every epoch on ARM64 stay behind.

**Correction (needs a decision of the owners; my recommendation, replacing the flush-epoch sentence of G12).** "On a node of several cores, G5's 'a local invalidation since the count reached zero' becomes 'no invalidation of the node in flight': the gate counts, in the node block, the requests for invalidation whose acknowledgements are not all in, and refuses a give, the destruction of a block and a change of page class while that count is not 0 (`busy`, or `again` for a removal step). An idle core counts as done, since it does what it owes before it loads a root of the node again; on ARM64 the count stays 0, since the broadcast is completed inside the gate call."

This holds because the map count is lowered in the same gate call that writes the request, under the gate lock, so there is no window. It adds one word to the node block, a layout change that must be made now. G12's proof obligation (3) then speaks of this count rather than of epochs.

### N3. The audit of G14 and R4 runs in steps, and a mapping between steps stops the machine: wrong result, on every node

Lines 1220 and 1249 are quoted above. My explorer (`audit_check`, *N* = 1, one other thread mapping between steps):

```
G14 audit in steps, maps allowed: ['read count', 'aspace_map into T1', 'walk T1', 'walk T2', 'compare', 'mismatch: machine stops'] (1 losing places)
G14 audit in steps, maps refused: no trace (0 losing places)
```

The same hole exists for line 1224's ownership words: a block given away between two steps of its walk. This is avoidable if each step checks again that the block is live, which the text does not say.

**Correction (needs a decision; my recommendation, append to G14).** "While a node's audit runs, its gate refuses every change of a map count of the node (`again` for a mapping call or a removal step), so that the counts and the tables the audit compares do not move between its steps; R4 checks the ownership words of one block in one step, after checking that the block is still live." Other options: drop the per-chunk comparison from R4, or keep, for the length of the audit, a per-chunk tally that the gate corrects behind the walk's cursor. The tally costs 4 bytes per chunk of kept memory.

### N4. `iospace_unmap` waiting for its unit has no record state: unspecified

Line 347 says "a call made on another node waits for it", and line 948 includes "the invalidation after an unmap … including those done by removal steps". Kind 3 is defined only as "invalidation on other cores of the node … in flight" (line 1782). During that wait, another thread can call `iospace_unmap` or `iospace_map` on the same capability, or reach it by a removal. Even on *N* = 1, a second thread can run on the same core while the first waits. The text allows two outcomes: a second unmap that undoes the record again, or a `busy`. Emptying the record before the confirmation would let the frame be destroyed while a device may still use it, which line 365 forbids.

**Correction (line 347).** "During that wait the record is *unmapping* (kind 3, which also covers an invalidation of an IOMMU unit in flight): `iospace_map`, `iospace_unmap` on it are `busy`, and a removal that reaches it returns `again`." Line 1782's definition of kind 3 gets ", or of the unit's translation cache".

### N5. L2 for an `iospace` and the `iommu` list: unspecified (the second part is a suspicion)

Line 635 lists "iospace" among objects with a lock word. Line 637 ("the header page of an aspace") and line 1748 ("The header of an aspace holds, since D-129, … a lock word") reserve it only for an aspace. To fix this, add "and of an iospace" to both lines.

The suspicion, not verified, outside this angle: an `iommu` "keeps the list of the devices attached through it … linked through the device entries of the iospaces' headers" (line 364). An `iommu` is a machine object that "belong[s] to no node" (line 17). The list therefore links headers in the memory of the iospaces' nodes, and is written by the holder of the unit's role (line 948). Under L2 it has no lock, and between nodes it would be a word written into another node's object. This is for the reviewer of the boundary between nodes.

---

## The reviewer's script

`check.py` runs (`timeout 60 python3 -B -I check.py`) and prints what the report quotes. For each check, whether it can fail:

- **A.** Can fail: forbid `aspace_map` on `"unmapping"` and no trace is found. It encodes the disputed reading as a premise, and its ack move drops the leaf, so the printed "no leaf in any table" is wrong (see finding 3).
- **B.** Can fail if the choice move checks the mark. The mutation is not in the code. It encodes the reading that line 647 contradicts.
- **C.** Cannot fail. `c_moves` has no move out of `"unmapping"` at all (the branch is `pass`), so the "stuck" state is reached by construction, and the mutation named in the report does not exist in the code. It also models only the idle core, while the fault covers every core (finding 1, N2).
- **D.** Can fail. It models the resume race, which is not a fault (finding 8). It does not model the second suspend, which is.
- **E.** Arithmetic. It can fail with a smaller *H*. Its premise (*H* = 1 ms) is right only through lines 902 and 910, which the report does not cite.
