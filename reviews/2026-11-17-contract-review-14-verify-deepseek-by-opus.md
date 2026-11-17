# Verification of DeepSeek's fourteenth contract review, by Opus

**Date:** 17 November 2026. **Verified:** [`2026-11-17-contract-review-14-deepseek.md`](2026-11-17-contract-review-14-deepseek.md) (2 high findings, 4 low, 4 doubts, a list of what it found sound). **Against:** `architecture/kernel-interface.md` and `decisions/README.md` at commit `a0e5848`, the diff `a1dca23..a0e5848`, and the reference model at `acecf8f` (read-only clone `/private/tmp/dodos-pr3-p22`). All line numbers are those of `kernel-interface.md` at `a0e5848` unless another file is named.

**How it was read, stated honestly.** The contract at `a0e5848` is 702 KB. I read in full: the rules and objects (lines 1-72), the call reference up to IPC (72-200), the whole of *Memory and devices* (237-407, frames, records, tables, TLB, IOMMU), the whole of *Memory and devices between nodes* and *The gate over page tables* (818-1095), *The fence* and *Reclaim* with the barrier (1304-1360), *Numbers* (1494-1524), *Debugging a component* (1664-1673), the fault table rows I cite (448-459), and the bounds paragraph of *A node of several cores* (654-700, the parts on *H*, *W* and `CORE_ANSWER_NS`). The rest I searched by keyword. Every quotation below was copied from the file or the source named; nothing is quoted from memory.

**Sources opened.** Intel SDM 325462-093 (title page "Order Number: 325462-093US"), VT-d D51397-019 ("Revision 5.20", "Order Number: D51397-019"), both downloaded from Intel's servers through the links the contract gives, and Arm DDI 0487 M.d ("Document version M.d", "30/Sep/2026 M.d"), the PDF that Arm's documentation service lists. Not opened: Arm IHI 0069, the RISC-V AIA, the IOAPIC 82093AA datasheet, the TI PC16550D datasheet, PSCI DEN0022F.b.

---

## 1. The six findings

### Finding 1 (high): a `Release` frees the use entry, so the count reads 0 — **confirmed in part**

**The text.** Line 917, *Release by the holder*: "When *Y* removes the root remote capability of a grant (by any removal other than one done for a `Revoke`, above), it sends *X* a `Release` that names the grant and its serial, and frees its use entry once the message is in the ring". Line 914: the holder's gate "frees a use entry, or writes it for another grant, only once its count is 0, a cleared leaf counting until its invalidation is complete (G6)". Line 1079, G6: "and frees a use entry only at a count of 0, so the granting node frees a grant only on that count (D-141)". The D-131 amendment row of `decisions/README.md` says the same: "frees a use entry only at a count of 0".

**When the two collide.** A root remote capability can be removed with its use entry's count above 0 in one case only. Line 252: on an *unmapping* record "a removal that reaches it returns `again`, until the invalidation completes and empties it", and line 915 adds that "the root is not removed while a record under it is unmapping"; so normally the root goes only once every count is down. The exception is line 396: "every record whose invalidation the unit did not confirm is emptied with its counts kept: the map counts, leaf counts and use-entry counts of its leaves are never lowered ... and a frame another node granted stays pinned, until the machine restarts". After that, nothing under the root is unmapping, the root can be removed, and the count is still above 0.

**Walk of the review's scenario.**
1. *Y* maps *X*'s frame into an iospace whose device sits behind unit *U*; the use entry counts the leaf (914, G6).
2. *Y* removes the root (its own `cap_delete`). The removal undoes the record (257), asks *U* to invalidate (349), *U* fails (393), the record is emptied with its counts kept (396). The next step removes the root.
3. Line 917 says: send `Release`, then free the use entry. Lines 914 and G6 say: do not free it while the count is above 0. The text gives both orders.
4. If line 917 is followed: *X* consumes the `Release`, reads the use entry "as a revocation reads it", which is "counted only if that entry names *X*, this grant, its serial and *X*'s generation, and as 0 otherwise" (915). The entry is gone, so 0; *X* frees the grant and, "if it has no descendant in *X*'s list", removes the anchor (917). *X* then deletes its frame capability, nothing below it stops the removal, the frame is destroyed and the memory goes back to the untyped (119), from which `memory_give` (881: "`busy` if the untyped capability has a descendant, then `busy` if a piece of it lives") is no longer refused. The chunk is given or retyped while *U* may still hold *Y*'s translation to it. One step more than the review wrote (*X* must delete its frame capability, which it is free to do once the grant is gone), same outcome.
5. If G6 is followed: *Y* keeps the use entry; *X* reads a count above 0, "leaves the entry as it is and traces the message (code 11)" (917). Nothing is freed. This is safe, and it is what line 396 promises.

**What the reference model does.** It follows line 917 literally. `remote_destroyed` (`model/src/grants.rs`) removes the use entry as soon as the `Release` is written (`self.table.uses[me].remove(&remote.use_entry)`), whatever its `leaves`. `freeze_unmapping` (`model/src/memory.rs`) returns early for a remote record, so the use entry keeps its count, and the next root removal frees it. So the model has the hole of step 4. No scenario covers it: `grep` finds no test that fails a unit under a remote frame (the failed-unit scenarios are in `pass17.rs`, `pass22.rs` and `mistral.rs`, none with a grant). The model's invariant 58 (`model/src/check/table.rs`, "58: leaves of a use entry") compares a use entry's count with the leaves in the tables plus the *unmapping* records only, so a frozen remote record would fail it the moment it is frozen: the model has never reached this state.

**Verdict.** The contradiction between line 917 and lines 914/1079 is real, and the model implements the unsafe side. **Refuted:** the review's "second defect", that the code-11 branch of line 917 "is unreachable in every case" and "can never be written". Under G6 the gate frees a use entry only at a count of 0, so a holder whose kernel sends a `Release` while its gate still counts leaves reaches that branch; the model tests exactly this (`a_release_of_the_holder_while_its_tables_translate_the_frame_frees_nothing`, `model/src/scenarios/pass22.rs`, which forges the `Release` and asserts the grant stays and one refusal is traced).

**The same defect in two more sentences**, which the review did not list:
- Line 915: "A removal on *Y* done for a `Revoke` frees *Y*'s use entry when it removes the root". Unconditional. With a failed unit during the revocation (the `Revoke` row of the table at 988 expects it: "beyond it the unit has failed, and the record is emptied with its counts kept"), the next step removes the root and frees the entry; *X* then reads "0 otherwise" from the `RevokeStep` and frees the grant. The model does this: `revoke_received` calls `remove_root` with `self.revoking` set, and `remote_destroyed` then removes the use entry unconditionally before the `RevokeStep` is written.
- Line 917: "A `Revoke` that reaches a use entry whose flag *release pending* is set finds the root already removed: *Y* answers `RevokeStep` reporting it removed, drops the pending release and frees the use entry." Also unconditional.

**Severity: high.** It needs a failed unit, but the result is memory a device may still write into, handed to another node, against line 396 and G (2) (line 1064).

### Finding 2 (high): a `Revoke` after the root went with a count above 0 — **confirmed in part**

**Walk.** Same start as finding 1, but the root is removed by a removal done for a `Revoke`.
- If line 915's "frees *Y*'s use entry when it removes the root" is followed (the model does): the free comes in *Y*'s event before the answer is written, and the ring's order (968: "the sender writes its entries, then the producer index with release order") makes the free visible before the answer. *X* reads 0 and frees the grant: finding 1's unsafe outcome, not a hang.
- The review's sub-case, *X* reading between the answer and the free, needs *Y* to free after it has published its answer. Nothing in the text orders it so, and no natural reading does. I do not count that branch.
- If G6 is followed: *Y* keeps the entry. *X* reads a count above 0, and line 915 says "otherwise leaves it *revoking* and is traced (code 11) (D-141); any other answer, and that one, makes the removal step return `again`, and its next call sends `Revoke` again". The next `Revoke` passes the check of 966 (the use entry still names *X* with that generation and serial). *Y* must then run "one removal step of at most 32 units on its root remote capability of the grant" (915, and the table at 937), and that root no longer exists. The only rule for a `Revoke` that finds the root removed is the *release pending* one, which does not apply. So *Y*'s action is unspecified. If *Y* answers "removed" without freeing, *X* loops for ever: each call sends a `Revoke`, gets "removed" with a count above 0, writes a code-11 trace and returns `again`. If *Y* frees (as the model's `revoke_received` does whenever `!self.objects.contains_key(&entry.root)`), we are back to finding 1.

**Verdict.** There is a real defect: no reading of the text gives a safe end state for a revocation whose holder's root went with a count kept by a failed unit. Under one reading the grant is freed unsafely, under the other the removal on *X* sends a message and writes a trace on every call, for ever. The review's own mechanism (the check refuses the second `Revoke`, no answer comes, "the thread waits in *waiting for another node*" for ever) rests on the unsupported ordering above. Note that line 916 already accepts a removal that returns `again` until the machine restarts, for a pinned grant ("For an unfenced grantee that is not before the machine restarts"); what is wrong here is the message and the trace on every call, and the missing rule on *Y*. One root cause with finding 1; one correction (C1 below). **Severity: medium as a liveness defect on its own; it is fixed with finding 1.**

### Neighbouring cases of findings 1 and 2

I walked each against the text, with C1 and C2 below in mind.

- **The unit fails before the map.** `iospace_map` has no "unit failed" state check (348 lists `again` for a full table as its last check). It writes the mapping, asks the unit, and the unit answers *failed* at once (394: "answers *failed* to every request it holds for the unit and to every later one"); the call returns `busy`, "the mapping kept and counted" (348). So a holder can create a frozen count on a granted frame after the unit has failed. This is availability only (1093: a faulty grantee "can keep the grant from being freed, which costs availability"), and it ends in the same state as the cases below.
- **The unit fails after the map** (a live mapping, the unit fails later). Removing the root undoes the record and asks the unit, which answers *failed*; the record is emptied with its counts kept. Same as findings 1 and 2.
- **The unit fails during the unmap.** This is the case the review walked.
- **The holder dies.** *Y* had a device behind *U*: its attach word stays *attached* (397: "the attach word of a device whose attach or detach the unit did not confirm stays *attached*"; a detach on a failed unit is `busy`, 390). So R1 for *Y* stays undone on *U* (1326) and *Y*'s barrier never holds (398). *X*'s R3 pins the grant "until generation *g* of *X* is over" (1333, roles swapped), and that never happens. Safe. *X*'s removal returns `again` with no message (916). Consistent with 396.
- **The granter dies.** Unsafe. This is a new finding, N1 below: *Y*'s R2 finishes, *Y* acknowledges, *X*'s barrier holds, and *X*'s memory is reused while *U* may still translate to it.
- **A seal.** *Y* sealing: "a sealing node completes its requests before it seals" (988); with *U* failed those requests are answered *failed* and the records frozen; nothing new. *X* sealed: its `Revoke`s wait in its ring until the resume (979); nothing new.
- **A `Release` crossing a `Revoke`.** Line 917 justifies the crossing with "(*Y* freed its use entry before it read the `Revoke`, so the check refuses it and no answer will come)". When the count is kept, *Y* did not free the entry (under G6), so the check passes and an answer does come; but *X* has already freed the credit ("a `Revoke` of it still in flight stops counting as in flight"). That answer then names a credit not in use, and the check of 966 refuses and traces it. This is harmless, but the reason given in the sentence is false in this case. C1 keeps the credit when the count is above 0.

### Finding 3 (low): the depth proof's 128 + 64 and 191 — **refuted**

The review assumes that the ordinary part of the walk starts deeper than where the restricted part ended ("If the restricted walk ends at depth *d*, the ordinary walk has at most 64 − *d* steps"). That holds for a derivation, but not for the other move of the walk, "from the root of a space to a capability the space holds" (123). The depth rule constrains only what line 122 lists: "The root capability of another capability space can be placed in a capability space only if its depth is greater than the depth of the root capability of that space. An `untyped` or `memory_control` capability (a root or a copy) can be placed there only if its depth is not smaller". Every other kind can be placed at any depth: line 120 says "`cap_move` moves a capability to an empty slot. Its place in the tree, its rights and its badge do not change." So a space whose root is at depth 64 can hold an ordinary capability of depth 1, and the ordinary part can restart from depth 1.

Construction of 191: the start-up space root *S*1 (depth 1) holds the start-up untyped *U*1 (depth 1); retyping *U*1 makes a cspace root *C*2 (depth 2), which holds a child untyped *U*2 of *U*1 (depth 2, "not smaller" than 2); and so on up to *U*63 and *C*64. That is 1 + 1 + 2 × 62 + 1 = 127 restricted capabilities. *C*64 holds a kept frame's root of depth 1, moved there by `cap_move`, and a chain of 63 copies derived from it reaches depth 64: 64 ordinary capabilities. 127 + 64 = 191. The 128th restricted capability (an untyped at depth 64, held by *C*64) derives nothing, so it cannot be followed by the ordinary part. That is why the bound of 128 + 64 = 192 is never reached and "shorter than 192 (the longest one that can be built has 191)" is right. The review's "at most 130" is wrong. No correction is needed. A clause saying why the ordinary part can restart at depth 1 would help a reader (C10, editorial).

### Finding 4 (low): the range of `FENCE_NS` starts at 12 ms — **confirmed in part**

The row at 1505 reads: "| `FENCE_NS` | 30 ms | 12 ms to 1 s. Time for two rounds of the NMI grace, INIT and the two SIPIs after the delays of the SDM's example (11.2 ms each, as due events, D-141), and the stub; ... then 20 ms, less than two rounds (D-141) |". The row's own reason rejects any value below 22.4 ms while the delays are those of the SDM's example, and the range still accepts 12 ms (`abi/` `FENCE_RANGE_NS = (12_000_000, 1_000_000_000)`, line 1793). The inconsistency is real. **The consequence the review states is wrong.** A fence runs only on a node that is already accused, so a short `FENCE_NS` does not "fence a healthy node". What it does is leave an accused node *unfenced* (1252: "Not every stop was confirmed within `FENCE_NS`") when one round was not enough, and an unfenced node's memory and the frames granted to it are "never reused until the machine restarts" (1252), with its unit roles taken over after `FENCE_NS` + `SETTLE_NS` (1318). This costs availability, not safety. There is one defensible reading of 12 ms: the delays are "an example, not a stated requirement" (1311) and are to be measured, so a machine whose cores need shorter delays may want a shorter fence. But the delays are not a value of the image, so the range should follow from them. **Low.**

### Finding 5 (low): "11.2 ms" does not add up — **refuted**

Line 1311: "one round takes about 11.2 ms (`NMI_GRACE_NS`, 10 ms and 200 µs)". The parenthesis names three components, and the review counted two. `NMI_GRACE_NS` is 1 ms (1504: "| `NMI_GRACE_NS` | 1 ms | Time for a crash record |"). 1 + 10 + 0.2 = 11.2 ms, as written. The two delays match SDM Table 11-1 (§11.4.4.1), which I opened: "; 10-millisecond delay loop." after the INIT and "; 200-microsecond delay loop" between the two SIPIs.

### Finding 6 (low): the first map's bound ignores a sealed granter — **confirmed**

Line 914: "a first map of a frame just received waits until its sender has consumed the answer, at most the latency of a kernel ring (one period of the recovery reserve under full load)". A sealed node "sends and consumes nothing: messages to it wait in its rings until it resumes or is accused (with evidence seal, after `SEAL_NS`" (979). `SEAL_NS` is 1 s by default and its range goes up to 60 s (1509). While *X* is sealed, the remote capability stays valid (911: valid with the granter "in a state starting, live, sealing or sealed"), so `aspace_map` and `iospace_map` return `again`, possibly for up to `SEAL_NS`. Once *X* is accused, the capability is invalid and the map returns `gone` (911). The stated bound is false; nothing is unsafe. **Low.**

---

## 2. The four doubts

### Doubt 1: the watchpoint at the kernel's level, on each architecture

**What the contract says.** Line 1667: "The kernel never reads or writes a thread's memory through a user address: it reaches a message page through its own mapping of the frame ([Bindings](#bindings)), and touches no other user memory. On x86-64 the debug address registers compare linear addresses, which lie in the user range, so no access of the kernel matches; on ARM64 the user mask of a watchpoint's control gives it the privilege of EL0 only, and the kernel issues no unprivileged load or store (`LDTR`, `STTR` and their kin) ... RISC-V gives user threads no trigger. So a watchpoint exception taken at the kernel's own level stays a bug of the kernel". Line 459 lists class 0x35 among "every class taken at the kernel's own level ... is a bug of the kernel, which accuses itself".

**ARM64: the contract is right, and so is the earlier report; they do not conflict.** Arm DDI 0487 M.d, D2.9.4 ("Execution conditions for which a watchpoint generates Watchpoint exceptions"), opened: "The PAC control relates to the privilege of the memory access and the Exception level at which the access was made: • Unprivileged memory accesses generated by unprivileged memory access instructions are treated as unprivileged EL0 accesses." Its Example D2-4: "if the PE executes an unprivileged memory access instruction at EL1, any resulting Explicit Memory Effect that is unprivileged triggers a watchpoint only if both: • PAC is programmed to a value that generates watchpoints on EL0 accesses." Table D2-13 gives the row HMC 0, SSCE 0, SSC 00, PAC 10, which generates exceptions at EL0 only. So the earlier report's fact is true: `LDTR` and `STTR` executed at EL1 match an EL0 watchpoint. It is exactly the case line 1667 excludes, by saying the kernel issues no such instruction. A plain access by the kernel at EL1, or at EL2 under VHE, does not match a watchpoint whose PAC is 0b10 with HMC 0. A second guard exists that the contract does not cite. D2.3.1: "When executing at ELD: ... All other debug exceptions are disabled if either of the following is true: — The Local (kernel) Debug Enable bit, MDSCR_EL1.KDE, is 0. — The Debug exception mask bit, PSTATE.D, is 1." So a watchpoint exception is taken at the kernel's own level only if the kernel set KDE. The citation "D2.9" of line 1667 is right, and the quotation is found as quoted, in D2.9.4.

**One gap on ARM64:** the "user mask ... (in `abi/`)" does not exist at the model's head. `abi/src/aarch64.rs` at `acecf8f` holds the exception classes (`EC_WATCHPOINT_SAME = 0x35` and the rest) but no breakpoint or watchpoint control mask; the only control-word check in `abi/` is `x86_64::dr7_valid`. The claim on ARM64 is only as good as a mask nobody has written yet (N6, C6).

**x86-64: the reason given is true, the conclusion is false.** It is true that no kernel access matches: the kernel touches no user linear address. But a user data breakpoint can still raise a #DB at CPL0 with no kernel access at all. Intel SDM 325462-093, §7.8.3 "Masking Exceptions and Interrupts When Switching Stacks", opened: "Any data breakpoint on the MOV to SS instruction or POP to SS instruction is inhibited until the instruction boundary following the next instruction." A thread that sets a data breakpoint on a word, loads SS from that word, and makes its next instruction the system-call instruction (or `INT n`, `INT3`) has the #DB delivered after that instruction, at CPL0, on the first instruction of the kernel's entry. (The SDM's FRED section, §8.3.3, says FRED event delivery "drops any debug traps that were pending at the time the original event occurred", "any pending data or I/O breakpoints ... are no longer pending after INT n, INT3, INTO, SYSCALL, or SYSENTER is delivered using FRED event delivery", which confirms that the legacy delivery keeps them pending.) This is the case behind CVE-2018-8897. Read as written, line 1667 makes such a #DB "a bug of the kernel", so any thread with `write` on another thread of its own process can make its node accuse itself. A second hazard: at the first instruction of a `SYSCALL` entry the stack pointer is still the thread's, so a #DB delivered there through an IDT gate without its own stack writes its frame onto a stack the thread chose. The contract says nothing on the #DB vector's stack (no "IST" anywhere in `kernel-interface.md` or `kernel.md` at `a0e5848`). New finding N2, medium.

**RISC-V: right.** The fault table at 455 says "the trigger registers of Sdtrig are reached from machine mode only ... so no user thread has one". With no user trigger, the case cannot arise. (I did not open the Sdtrig specification; the claim rests on the contract's own rule that the kernel exposes none.)

### Doubt 2: `CORE_ANSWER_NS` against 2 × *W* + *D* — **settled, no defect**

*H* is measured per image (688: "*H* and *D* are measured for the image"), and the check is against "the largest *N* the kernel image supports (entry `Node`)" (688). An image whose measured *H* makes 2 × *N* × *H* + *D* exceed 100 ms is refused at start-up, so it must declare a smaller *N*. The figure of 1 ms for *H* comes from the eighth review, not from the contract. This is a trade-off the contract states, not an inconsistency.

### Doubt 3: two opposite reasons for 10 ms — **refuted**

Line 393: "**The bound** is `IOMMU_WAIT_NS` (10 ms, provisional; 1 ms before D-141, below a stall of system management mode, which would have marked a healthy unit failed for the life of the machine)". The clause "below a stall of system management mode" describes the old value of 1 ms, as the reason it was raised. Both 10 ms values are chosen to be *above* a firmware stall. Nothing is reversed.

### Doubt 4: which check makes "a chunk under a live grant is never given" — **settled, no defect**

Line 117: "`untyped_retype` makes the new capability a child of the untyped capability", and the anchor is "a new child of the frame capability in *X*'s derivation list" (912). So the anchor is a descendant of the block's capability, and `memory_give` is "`busy` if the untyped capability has a descendant, then `busy` if a piece of it lives" (881). The second test alone suffices: the frame object lives as long as its root capability (119), and that root cannot go before its descendant, the anchor (118, 128). A sentence at G6 naming these two checks would help a reader (C11, editorial).

---

## 3. My own attack on the same paragraphs

### N1 (high): the granter dies after a holder's unit failed — its memory is reused under a stale translation

**Walk.**
1. *X* grants a frame to *Y*; *Y* maps it into an iospace whose device sits behind unit *U*.
2. *Y* unmaps it (or removes the capability), *U* fails, the record is emptied with its counts kept (396). *Y*'s use entry counts the leaf for ever. *U*'s IOTLB may still hold the translation for *Y*'s device, which is still attached (397) and so still has a context entry.
3. *X* is accused (any reason) and fenced.
4. *Y*'s R2 (1332): "It removes every translation it holds to memory of *X*: its remote frame capabilities of *X*'s grants, with their mappings ... a record left *unmapping* is completed by its request, and R2 is done when no such record remains." No record is *unmapping*, the record was emptied at step 2, so R2 is done. R3 and R4 follow, then R5 (1335): "It clears `maps_of` bit *X* and writes `acked[X]` = *g*".
5. *X*'s barrier (1343-1353) needs `acked[X]` from every live node, which it now has, and "no context entry of any IOMMU unit names *X*'s generation". *Y*'s device is *Y*'s, not *X*'s, so this condition holds. R1 on a failed unit holds only "the nodes whose devices sat behind it, and of no other" (1326); that holds *Y*'s barrier, not *X*'s.
6. R6 clears *X*'s tables, *X* becomes dead, and "**After dead**, every ownership word, device entry, identifier word (its attach word 0) and line word owned by *X* is free for any live node" (the paragraph after the barrier's table, 1353). Another node takes the chunk and uses it; *Y*'s device can still write into it through *U*'s cached entry.

**Which promise breaks.** Line 396 says "a frame another node granted stays pinned, until the machine restarts". G (2) (1064) and the barrier's purpose, "so that *X*'s devices can write into no memory reused after its death", apply here to *Y*'s device. Line 919 even states the opposite of what safety needs: "So no use entry outlives the generation it names." The pin of line 396 lives in *Y*'s use entry, and nothing on the path of *X*'s death reads it.

**In the model:** `reclaim_step` and `audited` (`model/src/nodes.rs`) finish R2 when "no remote capability of the node remains", and `remote_destroyed` frees the use entry of a generation that is over without looking at `leaves`. So the model has the hole too.

### N2 (medium): x86-64, a #DB at CPL0 caused by the thread alone

See doubt 1. The contract's rule makes a thread-caused #DB at CPL0 a kernel bug, and is silent on the stack the #DB vector runs on.

### N3 (low): the reason in the crossing sentence of 917 is false when the count is kept

See the neighbouring cases above. It is folded into C1.

### N4 (low): VT-d memory per unit is 1 MB + 4 KB, not "1 MB in all"

Line 341: "a root table of 4 KB and up to 256 context tables of 4 KB, 1 MB in all". 4 KB + 256 × 4 KB = 1,028 KB. The two sizes match VT-d §3.4.2, which I opened ("The root-table is 4-KByte in size and contains 256 root-entries", "Each context-table contains 256 entries"). The total is 4 KB short. Kept memory is sized from this sentence at start-up.

### N5 (low, editorial): VT-d §6.1 is listed as read and cited by no sentence

Line 2303 lists "VT-d §3.4.2, §3.4.4, §3.16 and §6.1" among the sections pass 22 "read ... it added". No sentence of the contract cites §6.1 ("Caching Mode" in D51397-019). Either a citation was dropped or the list is wrong.

### N6 (low): the ARM64 debug control mask is not in `abi/`

See doubt 1. The contract should name the fields, and `abi/` should check them.

### Checked and found sound

- The order of the count and the grant entry (914) on ARM64: Arm DDI 0487 B2.3.7 "Ordering relations", Barrier-ordered-before, contains "E1 is an Explicit Memory Write Effect with Release semantics. — E1 appears in program order before E2. — E2 is an Explicit Memory Read Effect with Acquire semantics." This is what a store-release then load-acquire pairing needs. Quoted correctly.
- The G14 audit (1087) with a frozen count: the unmap cleared the leaf from the tables, so the walk finds no leaf to judge. No false stop.
- R3 (1333) for a holder that dies with a frozen count: *Y*'s barrier never holds (398), so *X*'s pinned grant stays. Safe.
- R6 (1339) never runs for a node with a device behind a failed unit, so it never clears a frozen use entry of that node.

---

## 4. The hardware sentences of the diff, against the sources

| Sentence (line) | Source opened | Result |
|---|---|---|
| ID 255 is the broadcast in physical destination mode (814) | SDM §13.6.2.1 | Found as quoted: "either a single destination (local APIC IDs 00H through FEH) or a broadcast to all APICs (the APIC ID is FFH) may be specified in physical destination mode." |
| Directed EOI: bit 12 of the spurious-interrupt vector register, the IOAPIC's EOI register (797) | SDM §13.8.5 | Matches: "Software can inhibit the broadcast of EOI message by setting bit 12 of the Spurious Interrupt Vector Register"; directed EOIs are done "by writing to the I/O APIC's EOI register"; support is reported "in bit 24 in the Local APIC Version Register". That a given IOAPIC has an EOI register is the IOAPIC datasheet's, not opened. |
| `MFENCE; LFENCE` before the x2APIC ICR write (1083) | SDM §13.12.3 "MSR Access in x2APIC Mode" | Found as quoted: "WRMSR to an APIC register may complete before all preceding stores are globally visible; software can prevent this by inserting a serializing instruction or the sequence MFENCE;LFENCE before the WRMSR." |
| DR7: condition `10` with `CR4.DE` is I/O; length `10`; length on an execution breakpoint (1667) | SDM §20.2.4 | Found: "When the DE flag is set ... 10 — Break on I/O reads or writes."; "10 — Undefined (or 8 byte length, see note below)."; "If the corresponding RWn field in register DR7 is 00 (instruction execution), then the LENn field should also be 00. The effect of using other lengths is undefined." |
| `LFENCE` around `RDTSC` (496) | SDM, RDTSC | Found: "The RDTSC instruction is not a serializing instruction." and "subsequent instructions may begin execution before the read operation is performed". |
| 10 ms after INIT, 200 µs between SIPIs (1311) | SDM §11.4.4.1, Table 11-1 | Found ("; 10-millisecond delay loop.", "; 200-microsecond delay loop"). |
| VT-d table sizes (341) | VT-d §3.4.2 | Sizes right; the total is 1 MB + 4 KB (N4). |
| RMRR identity mapping (402) | VT-d §3.16 | Found as quoted. |
| No abort-DMA mode with active RMRR devices (402) | VT-d §3.4.4 | Found as quoted. |
| One domain, one set of tables (402) | VT-d §6.2.2.1 | Matches: "if multiple context-entries are programmed with the same Domain-id (DID), such entries must be programmed with the same values for the Second-Stage Page Translation Pointer (SSPTPTR) and Address Width (AW) fields". |
| Release/acquire order of the count (914) | DDI 0487 B2.3.7 | Found (section 3 above). |
| Unprivileged accesses count as EL0 for watchpoints (1667) | DDI 0487 D2.9 (D2.9.4) | Found as quoted (doubt 1). |
| `TTBR1_EL2` needs FEAT_VHE (1315) | DDI 0487 D8.13 "Virtualization Host Extensions" | Found: "All statements in this chapter require implementation of FEAT_VHE." (rule RSJSDF). |
| `CNTVCT_EL0` reads out of order (496) | DDI 0487 D12.2.2 "The virtual counter" | Found: "Reads of CNTVCT_EL0 can occur speculatively and out of order relative to other instructions executed on the same PE." |
| SME trap codes (448) | DDI 0487 D24.2 (D24.2.44, `ESR_EL1`) | Found, e.g. "0b011 SME instruction trapped because PSTATE.ZA is 0." |
| `ALLINT` masks "with or without Superpriority" (1315) | DDI 0487 C5.2.1 | Found: "an IRQ or FIQ interrupt that is targeted to ELx, with or without Superpriority, is masked." |
| Classes 0x21, 0x25, 0x27, 0x31, 0x33, 0x35 (459) | DDI 0487 D24.2.44, `ESR_EL1.EC` | Matches: 0b100001 instruction abort and 0b100101 data abort without a change of level, 0b100111 "Memory Operation Exception", 0b110001, 0b110011, 0b110101 breakpoint, software step and watchpoint "taken without a change in Exception level". |

**Not opened:** Arm IHI 0069 (the `DSB ISHST` before `ICC_SGI1R_EL1` of G10, and the ARM64 half of the level-line rule at 797); the RISC-V AIA (`fence w,o` before an IMSIC or ACLINT store, G10); the IOAPIC 82093AA datasheet; the TI PC16550D datasheet (the 16-byte queue at 1654); the RISC-V Sdtrig specification; PSCI DEN0022F.b. The contract marks the first four "to verify" itself.

---

## 5. The corrections

Each gives the sentence and its place, what it contradicts, its cost and when, its new state, and the model's work.

### C1 (high): a use entry is freed only at a count of 0, and a root removed with a count kept pins the grant

Closes findings 1 and 2 and N3.

- **Line 917, holder side.** Replace "and frees its use entry once the message is in the ring;" with "and frees its use entry once the message is in the ring if its count is 0 (G6); a use entry whose count a failed unit kept ([IOMMU](#iommu)) stays, with its root address 0 (slot 0 is never used), until the holder's generation ends;". In the next sentence, replace "no message is sent and the entry is freed" with "no message is sent and the entry is freed if its count is 0".
- **Line 915, holder side.** Replace "A removal on *Y* done for a `Revoke` frees *Y*'s use entry when it removes the root" with "A removal on *Y* done for a `Revoke` frees *Y*'s use entry when it removes the root if its count is 0, and otherwise keeps it with its root address 0, as after a release".
- **Line 917, the root already removed.** Replace "A `Revoke` that reaches a use entry whose flag *release pending* is set finds the root already removed: *Y* answers `RevokeStep` reporting it removed, drops the pending release and frees the use entry." with "A `Revoke` that reaches a use entry whose root is removed (its flag *release pending* set, or its root address 0) answers `RevokeStep` reporting it removed, drops a pending release, and frees the use entry if its count is 0."
- **Line 915, granter side.** Replace "and otherwise leaves it *revoking* and is traced (code 11) (D-141); any other answer, and that one, makes the removal step return `again`" with "and otherwise marks it *pinned* and is traced (code 11) (D-141); any other answer makes the removal step return `again`".
- **Line 917, the crossing.** After "the count read in the same way", add: "at a count above 0 the entry becomes *pinned* instead, and the credit of a `Revoke` in flight stays in use until its answer, which comes, since *Y* kept its use entry". Keep the release of a live entry as it is ("leaves the entry as it is and traces the message"): a later revocation then costs one round trip and ends *pinned*.
- **Line 916.** Replace "(its grantee is fenced or unfenced, [Reclaim](#reclaim), R3)" with "(its grantee is fenced or unfenced, [Reclaim](#reclaim), R3, or reported its root removed while its use entry still counted a leaf, which only a failed unit leaves)".
- **Table at 937-939.** Rows 1, 2 and 3: "freed at the `RevokeStep` that reports the root removed, or at a `Release`" and "Root removed: frees the grant entry" and "Frees the grant entry" each gain "when the holder's use entry counts no leaf; otherwise pinned (row 1, 2) or left as it is (row 3)".
- **Line 919.** "So no use entry outlives the generation it names" gains "except one whose count a failed unit kept, which stays until the machine restarts (and holds the granter's barrier: R2)".
- **What it contradicts once changed:** nothing else. G6 (1079), line 914, line 396, the D-131 amendment in `decisions/README.md` and the "Bounded since D-141" clause of `security.md` all become true as written.
- **Cost:** none on a memory access or on the common path. The count is already read at every release and `RevokeStep` (914). At a failure only: one more compare-and-swap writing *pinned*, and a use entry kept until restart.
- **New state:** none. *Pinned* exists (909), and a root address of 0 needs no bit.
- **Model:**
  - `remote_destroyed`: keep the use entry when `leaves > 0`, with its root cleared. `UseEntry.root` must become optional or carry a flag.
  - `revoke_received`: on the root-absent or *release pending* path, remove the entry only at `leaves == 0`.
  - `revoke_answered`: the `Some(_)` arm sets `GrantState::Pinned` besides tracing.
  - `release_received`: on a *revoking* entry with a count above 0, set *pinned* and keep the credit.
  - `freeze_unmapping`: record a frozen tally for remote records instead of returning early.
  - Invariant 58 (`check/table.rs`): count that tally.
  - New scenarios: a remote frame in an iospace whose unit fails (a) during the holder's own removal, (b) during a revocation, (c) with a `Release` crossing a `Revoke`, (d) before the map (`iospace_map` answered *failed*).

### C2 (high): R2 is not done while a use entry naming the dead granter still counts a leaf

Closes N1.

- **Line 1332, R2.** Replace "and R2 is done when no such record remains" with "and R2 is done when no such record remains and no use entry of *Y* that names *X*'s generation counts a leaf: a count a failed unit kept ([IOMMU](#iommu)) leaves R2 undone, so *Y* never writes `acked[X]` and *X* stays fenced, its memory frozen, until the machine restarts".
- **Line 1326, last sentence of R1.** "So a failed unit holds the barrier of the nodes whose devices sat behind it, and of no other" becomes "... and of the nodes whose frames a leaf under it still counts in such a node's use entry (R2), and of no other".
- **Line 398** gains the same clause for a granting node. Line 919 changes as in C1.
- **What it contradicts once changed:** nothing else. "What the survivors never wait for" (1328) still holds, since *Y* waits for nothing; it just does not acknowledge.
- **Cost:** at a death only. One read of each use entry naming *X*, at most `GRANTS`, in steps of the reserve. At a failure, a frozen node slot until restart, the same price line 398 already pays.
- **New state:** none.
- **Model:** `reclaim_step` and `audited` (`model/src/nodes.rs`) also require that no use entry with `granter == node`, that generation and `leaves > 0` exists; `remote_destroyed` must not free such an entry for a generation that is over (C1). Scenario: a failed unit under a granted frame, then the granter killed. Assert that its barrier never holds and that its chunks stay taken.

### C3 (medium): x86-64, a thread's breakpoint hit at CPL0

Closes N2.

- **Line 1667.** Replace "So a watchpoint exception taken at the kernel's own level stays a bug of the kernel" with: "On ARM64 and RISC-V a watchpoint exception taken at the kernel's own level therefore stays a bug of the kernel. On x86-64 it can be the thread's: a data breakpoint hit by a `MOV` or `POP` to SS is held until the boundary after the next instruction (Intel SDM §7.8.3), so a thread that follows it with the system-call instruction or an `INT n` has the #DB delivered at CPL0, on the kernel's first instruction. The kernel takes a #DB at CPL0 whose DR6 bits name only the thread's breakpoints as a fault of the thread (kind 9), delivered when its call ends, and the #DB vector runs on a stack of its own (an IST entry), since at the first instruction of the system-call entry the stack pointer is still the thread's."
- **Line 459** is ARM64 only and stays.
- **What it contradicts once changed:** nothing. The fault table row at 455 already maps a #DB raised by the thread's registers to kind 9.
- **Cost:** none at run time (one IDT field, one test in the #DB handler, paid at a #DB).
- **New state:** a small #DB stack per core, kept with the kernel's stacks (rule 3 already lists "its stacks").
- **Model:** nothing to change (it models no x86 entry). The kernel's trial must test the `MOV SS` + system call sequence.

### C4 (low): the first map's bound

Closes finding 6. At line 914, after "(one period of the recovery reserve under full load)", add "while the granting node is live; while it is sealed, until it resumes (at most `SEAL_NS`), and once it is accused the map returns `gone` ([What crosses between nodes](#what-crosses-between-nodes), "What ends with a generation")". No cost, no state, nothing in the model.

### C5 (low): the range of `FENCE_NS`

Closes finding 4. Row 1505: either raise the lower bound to two rounds plus the stub, 23 ms with the SDM's delays, with `FENCE_RANGE_NS` in `abi/` to match; or tie it to the delays: "at least two rounds of `NMI_GRACE_NS` and the delays the kernel uses, which the machine start-up checks". The second is better once the delays are measured. Cost: a start-up check. Model: the `abi/` constant and the test of the range.

### C6 (low): name the ARM64 debug control mask

Closes N6. At line 1667, after "gives it the privilege of EL0 only", add "(`DBGWCR<n>_EL1` and `DBGBCR<n>_EL1` with HMC 0, SSC 0b00 and PAC or PMC 0b10, no linking and no context matching, Arm DDI 0487, D2.9.4, Table D2-13; and the kernel keeps `MDSCR_EL1.KDE` 0 outside the debugger stub, so a debug exception other than a breakpoint instruction is never taken at its own level, D2.3.1)". `abi/`: add the mask and its check beside `dr7_valid`. No run-time cost.

### C7 (low): VT-d total

Closes N4. Line 341: "1 MB in all" becomes "1 MB and 4 KB in all". Check that the start-up layout in `abi/` reserves it.

### C8 (low, editorial): VT-d §6.1

Closes N5. Line 2303: drop §6.1 from the list, or restore the sentence that cited it.

### C9: none for findings 3 and 5 and doubts 2 and 3, which are refuted or settled

### C10 (editorial, optional): the depth proof

At line 123, after "at most 64 more", add "(the depth rule constrains only roots of spaces, `untyped` and `memory_control`, so a space may hold an ordinary capability of any depth, and the ordinary part may start again from depth 1)".

### C11 (editorial, optional): the check behind "never given"

At G6 (1079), after "A chunk under a live grant is never given", add "(the anchor is a descendant of the block's capability, so `memory_give` and `memory_split` are `busy` on it)".

---

## The corrections to make, by severity

1. **High, C1:** free a use entry only at a count of 0 in the three sentences that free it unconditionally (917 release, 915 removal for a `Revoke`, 917 *release pending*), and turn a "root removed" with a count above 0 into *pinned* instead of *revoking* + `again`. Amend 916, the table rows 937-939 and 919. Model: `remote_destroyed`, `revoke_received`, `revoke_answered`, `release_received`, `freeze_unmapping`, invariant 58, four scenarios. (Findings 1 and 2, confirmed in part.)
2. **High, C2:** R2 (1332) is not done while a use entry naming the dead granter counts a leaf. Amend R1's last sentence (1326), 398 and 919. Model: `reclaim_step` and `audited`, one scenario. (New, N1.)
3. **Medium, C3:** x86-64, a #DB at CPL0 caused by a `MOV`/`POP SS` breakpoint is the thread's fault, and the #DB vector gets its own stack (1667; SDM §7.8.3). (New, N2; the x86-64 half of doubt 1.)
4. **Low, C4:** qualify the first map's bound for a sealed or accused granter (914). (Finding 6, confirmed.)
5. **Low, C5:** make the range of `FENCE_NS` follow from two rounds (1505, `abi/`). (Finding 4, confirmed in part; its stated consequence is wrong.)
6. **Low, C6:** name the ARM64 watchpoint and breakpoint mask fields and KDE (1667), and add the mask to `abi/`. (New, N6; the ARM64 half of doubt 1 is otherwise right.)
7. **Low, C7:** VT-d per-unit memory is 1 MB + 4 KB (341). (New, N4.)
8. **Low, C8:** VT-d §6.1 listed as read, cited nowhere (2303). (New, N5.)
9. **Editorial, C10 and C11:** say why the ordinary part of the depth walk can restart at depth 1 (123), and name the check behind "never given" (1079).
10. **No change:** finding 3 (refuted: 191 is attainable), finding 5 (refuted: `NMI_GRACE_NS` is the missing 1 ms), the "second defect" of finding 1 (refuted: the code-11 branch is reached by a faulty holder), doubt 3 (refuted), doubts 2 and 4 (settled, no defect).
