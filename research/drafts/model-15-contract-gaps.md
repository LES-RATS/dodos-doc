# Contract gaps found by the model of pass 15

**Settled by pass 16 (D-133, Docs commit that adds this line): every gap below is written into `architecture/kernel-interface.md` at its place, marked "gap *n*". Gaps 7 and 12 were settled otherwise than the model's reading; the layout of gap 3 corrects the summary below (a `Send` of 64 words with 4 grants takes 10 entries, a `Report` of 28 items 11).**

The executable model of `dodos-kernel` (branch `model`) was rewritten for the new shape of nodes (D-128, D-129, D-131) against `architecture/kernel-interface.md` as it stood at commit `a0a6947`. Where the contract is silent, ambiguous or contradicts itself, the model implements one reading and marks it in its code with a comment that starts `CONTRACT-GAP` and the number below. Each entry gives the sentence with its line, the case it does not settle, the readings, the one implemented and why, and the text proposed. Nothing here is decided: these are proposals for the owners.

Line numbers are those of `kernel-interface.md` at `a0a6947`.

## 1. A member word with fence class 3

**The sentence.** Line 1715: "`Member`: bits 7-8 the node's fence class". Line 1251 lists the classes 0, 1 and 2.

**The case.** Two bits hold four values; no class 3 exists. The contract does not say whether a word with 3 in these bits fails the word's check (as a state 8 to 15 does) or is read as some class.

**Readings.** (a) The word fails its check, like any value no rule writes. (b) Class 3 is read as "above forced" and accepted.

**Implemented.** (a): `Member::from_raw` refuses it (`abi/src/machine.rs`).

**Why.** Every other field of the member word refuses the values no rule writes; a class no core has would let a forged word claim more than the best class.

**Proposed text.** After "bits 7-8 the node's fence class": "(0, 1 or 2; a word with 3 fails its check, as a state 8 to 15 does)".

## 2. The header of a debug area: 56 bytes listed, 64 stated

**The sentence.** Line 1481: "The **header** of a debug area (64 bytes): magic (u32), version (u16, 2), core number (u16), generation ... (u32), node slot ... (u32), next sequence of the kernel ring (u64), next sequence of the user ring (u64), number of kernel entries suppressed ... (u64), then 16 reserved bytes, 0."

**The case.** The fields listed take 4 + 2 + 2 + 4 + 4 + 8 + 8 + 8 = 40 bytes, with the 16 reserved bytes 56, not 64.

**Readings.** (a) The header is 64 bytes, and 24 reserved bytes end it. (b) The header is 56 bytes and the area's first entry starts at 56. (c) A field is missing from the list.

**Implemented.** (a): `DebugAreaHeader` keeps 64 bytes with 24 reserved bytes (`abi/src/debug.rs`), and its size is a stability test.

**Why.** 64 is stated twice (the header and the alignment of the area's blocks); the count of reserved bytes is the only number that disagrees with it.

**Proposed text.** "... number of kernel entries suppressed by the rate limit since machine start (u64), then 24 reserved bytes, 0."

## 3. The words of each message after its header, and the numbers of the unit operations

**The sentence.** Line 916: "A message takes 1 to 11 consecutive entries (a `Send` of 64 words with 4 grants takes the most)." Line 977 lists the operations of a unit request (attach, detach, the invalidation after an unmap, the invalidation of the interrupt entry cache, a line's redirection entry) without numbers. The table of line 897 names what each kind carries, never its layout.

**The case.** The room a message takes in its ring, the reserve of answers and the order of a `Report`'s items all depend on the words of each kind, which the contract does not fix; nor does it number the unit operations that a `UnitRequest` carries.

**Readings.** One layout per kind is needed; any that fits the counts the contract gives (11 entries for the largest `Send`, 34 entries of reserve, one `Report` per ask) is a reading.

**Implemented.** The layout written in the documentation of `NodeMessage` in `abi/src/ring.rs`: `Revoke` one word (grant 0-11, serial 12-41, use index 42-53); `RevokeStep` one word; `Release` and `Signal` one word (grant, serial); `UnitRequest` three words (role and epoch, operation and its argument, the requester's generation); `UnitAnswer` two words; `Handed` one word; `ReportAsk` two words (role and epoch, key); `Report` one word (the next key, or `REPORT_END`) and three per item, at most 28 items; `Ping` none; `SendAnswer` one word and one per frame; `Send` three words (header, stamp) plus one per grant and the message words. `UnitOperation`: attach 1, detach 2, invalidate 3, interrupt cache 4, redirection 5.

**Why.** With these words the largest `Send` (64 words, 4 grants) takes 11 entries of 64 bytes with its 16-byte header, as the contract says, and one `Report` fits the 10 entries the reserve adds for it.

**Proposed text.** A table in [What crosses between nodes] after the twelve kinds: "The words after the header, by kind: ..." with the layout above, and in [Devices and shared hardware]: "The operations are numbered: attach 1, detach 2, invalidation of translations 3, of the interrupt entry cache 4, a line's redirection entry 5."

## 4. A thread marked *leaving its core* that makes a call before its core takes the leave interrupt

**The sentence.** Line 654: "a call that must stop such a thread ... marks it **leaving its core** and sends *b* the kernel's leave interrupt; at that interrupt *b* saves the thread's registers ... While the mark is set, no core runs the thread: a marked thread is not runnable."

**The case.** Between the mark (an event of core *a*) and the leave interrupt taken by *b*, the thread still executes on *b* and may enter the kernel by a call. The contract says the thread is not runnable, but not what happens to a call it makes in that window: is it carried out, refused, or never entered?

**Readings.** (a) A core takes its pending interrupts at every kernel entry before the call, so the marked thread's call is never carried out: *b* leaves the thread first. (b) The call is carried out, and the thread leaves at its end.

**Implemented.** (a): a marked thread is not among the threads that can make a call (`Model::runnable`), and a core's pending interrupts are taken before any call of the thread it runs.

**Why.** (b) lets a suspended or revoked thread act after `thread_suspend` returned success to another core, which is what D-131 forbids ("a `thread_suspend` that succeeds has a thread that executes nothing").

**Proposed text.** After "a marked thread is not runnable": "A core takes its pending interrupts at each entry into its kernel before it carries out a call, so a marked thread that enters the kernel leaves its core there and its call is carried out only once it runs again."

## 5. The order by kind of the locks of variant L2, and the bound *k* of each call

**The sentence.** Line 642: "a call takes its locks in one order fixed by kind, the gate lock last, at most *k* per call (*k* fixed by the call's rules, the gate lock counted)".

**The case.** The order among the kinds and the value of *k* for each call are not given.

**Readings.** Any total order of the kinds with the gate lock last; any *k* per call that bounds what its rules touch.

**Implemented.** The order of `LockId` in `model/src/locks.rs`: the segment of a `cspace` (and so an untyped's root slot), task, thread, endpoint, reply, notify, timer, `sched`, aspace, iospace, the lock word of a core, the gate. The bound of each call is `locks::bound`: the objects and slots its rules name, plus the cores whose queues or interrupt tables it may change, plus the gate lock. The check fails on an order out of it, on more than *k* locks, and on a lock that is not paid for.

**Why.** Capability lookup first (slots), then the objects a call names in the order the rules check them, then the per-core state the call's effect changes, then the gate: no call in the model needs a lock of an earlier kind after a later one.

**Proposed text.** Under the table of the variants: "The order by kind is: the sequence words of `cspace` segments, by space then segment; task; thread; endpoint; reply; notify; timer; `sched`; aspace; iospace; the lock words of cores, by position; the gate lock. A call's *k* is the number of objects and slots its rules name, plus one per core whose queues or interrupt table it may change, plus one for the gate lock."

## 6. Where the instants of a fence are kept

**The sentence.** Line 1392: "the holder is fenced or dead, and `SETTLE_NS` has passed since the stop was confirmed; or the holder is unfenced and `FENCE_NS` + `SETTLE_NS` have passed since the first fence action". Line 1273 (R6): "once its core is confirmed stopped and `SETTLE_NS` have passed since the last stop sent to it".

**The case.** Every live node must judge these instants (a successor that takes over, any node that runs R6), but only the driver knows when it acted. The contract does not say where the first fence action, the confirmation and the last stop sent to each core are recorded.

**Readings.** (a) In the living part, beside the member word, written by the driver's gate. (b) Each node measures from when it saw the state change (its own clock of observation).

**Implemented.** (a): a fence record per node slot in the living part, with the instant of the first fence action, of the confirmation, and of the last stop sent to each core (`FenceRecord` in `model/src/table.rs`).

**Why.** (b) lets two nodes compute different instants, and a node that sees the change late takes over or clears too early by its own reckoning only if it saw it early; a record written by the gate gives every node the same instant, which the gate can check when it allows a take-over or an R6 write.

**Proposed text.** In [The fence]: "The driver's gate records in the living part, for each node slot, the instant of the first fence action, the instant the fence was confirmed, and for each core the instant of the last stop sent to it; the delays of [Roles] and of R6 are measured from these instants."

## 7. The cores set of a context, when a node's cores lie in several windows

**The sentence.** Line 506: "A context made by `untyped_retype` ... has ... the cores set of every core of the node that holds it". The cores set is given and changed as a window and a mask (64 core numbers), as `node_start` names cores.

**The case.** A node whose cores lie in two windows (cores 60 to 67) has no cores set of "every core of the node" in one window and one mask.

**Readings.** (a) The set is the window of the node's first core, with the node's cores in it. (b) The set has as many windows as the node's cores span. (c) A node's cores must lie in one window.

**Implemented.** (a) (`Model::cores_set`).

**Why.** It keeps the layout of a `sched` as it is; (c) would be a rule of `node_start` the contract does not state, and (b) changes the layout.

**Proposed text.** Either in `node_start`: "the cores named lie in one window (`invalid` otherwise)", or at line 506: "the cores set of the node's cores in the window of its first core".

## 8. How the park stub confirms a start, and the retry of a lost wake

**The sentence.** Line 1162: "Each physical core has a start request in the living part ... written through the gate by the node that starts it; then x86-64 sends an NMI, which wakes the halted stub". The brief of this pass adds the correction to come: "the starter sends the wake again every millisecond until the stub confirms".

**The case.** An NMI that reaches the stub between its read of the start request and its halt starts nothing (the lost wake-up of 16 November). The retry needs a confirmation the starter can read, which the contract does not name.

**Readings.** (a) The stub writes the start request it took into a word of the core beacon (`started`), and the starter repeats the wake every millisecond until that word equals its request. (b) The starter repeats until the core word reads *owned*.

**Implemented.** (a): the core beacon has `started`, written by the stub when it takes a start request and cleared when the core parks; the starter repeats the wake every `START_RETRY_NS` (1 ms) in its recovery reserve until it reads its request there, or the node is no longer starting (`model/src/nodes.rs`, `model/src/system.rs`).

**Why.** (b) confirms too late: the core passes the entry stub and builds state before it writes *owned*, and repeated NMIs to a core that already left the stub are taken by the node's kernel as fence signals. A word written by the stub itself confirms at the right step.

**Proposed text.** In the paragraph of line 1162: "The stub writes the start request it takes into `started` of its core beacon (0 when it parks). The node that starts a core sends the wake again every millisecond, in its recovery reserve, until `started` equals its request or the node is no longer starting."

## 9. Where `node_send` judges the right `grant`

**The sentence.** Line 950: "the capability list ... (`grant` on the node when the list is not empty)", placed after the header and the message. Line 144, [Order of checks]: the capability the call acts on is judged first, with its rights.

**The case.** The call's own text names `grant` after the list, the general order judges every right of the capability the call acts on with it, first.

**Readings.** (a) `send` and `grant` on the node with its three checks, first. (b) `send` first, `grant` after the list.

**Implemented.** (a) (`grants::node_send`).

**Why.** The general order is the rule every call follows, and a right of the capability acted on is part of its check; the rights of `send` already work so for a message with capabilities.

**Proposed text.** "The node (slot, kind, `send`, and `grant` when the message lists frames; `invalid` if it names the caller's own node ...)" and the clause after the list removed.

## 10. The generation of the granting node that keeps a remote capability valid

**The sentence.** Line 873: "It is **valid** when the grant entry is live with that serial and the granting node's member word is live with the generation recorded in the use entry."

**The case.** A granting node that is starting, sealing or sealed has the same generation and its grants are not dead (line 1208: a sealed node keeps its memory; its grants are freed only when its generation is over). Read literally, every remote capability of a sealing or sealed node is invalid, and a use of one makes its slot dead, which loses the holder's mapping of memory that is still granted.

**Readings.** (a) "live" is literal: a seal of the granter kills the holder's remote capabilities. (b) Valid while the granter's generation is current: starting, live, sealing or sealed with the recorded generation.

**Implemented.** (b) (`grants::valid`).

**Why.** A replacement (seal, then resume) must not break the grants of the node replaced; the generation, not the state, says whether a grant can still exist.

**Proposed text.** "... and the granting node's member word names the generation recorded in the use entry in a state starting, live, sealing or sealed."

## 11. Where `iospace_attach` judges a failed unit

**The sentence.** Line 365 ([IOMMU]) and line 980: a unit whose role word has the failed bit refuses new requests, and a call that waits for it ends `busy`. The state checks of `iospace_attach` are listed without it.

**The case.** The order of the state errors of `iospace_attach` does not place the failed unit.

**Readings.** First among the state checks; last; between the device's owner and the domain numbers.

**Implemented.** First (`memory.rs`).

**Why.** A failed unit makes every other state check moot, and judging it first changes nothing on the unit.

**Proposed text.** In `iospace_attach`: "State, in order: `busy` if the unit has failed; ..."

## 12. The invalidation of the interrupt entry cache when several units remap

**The sentence.** Line 977: "the invalidation of the interrupt entry cache after a remapping entry is written" goes to "the holder of a unit's role". Line 978: a call that sends a unit request waits for it in *waiting for a unit*.

**The case.** A machine with several IOMMU units has one remapping table per unit, or one shared table cached by each unit; the claim of an MSI must invalidate the cache of every unit that can deliver it, but the call has one wait and one entry of the unit request table.

**Readings.** (a) One request to the holder of the unit of the device (unknown at claim time). (b) One request per unit, the call waiting for all. (c) One request to the first unit, assuming one remapping unit per machine.

**Implemented.** (c): the claim's request goes to the role of the first IOMMU unit (`irq.rs`).

**Why.** The reference machines have one remapping unit; (b) needs several waits per call, which the layout of the thread does not hold.

**Proposed text.** "On a machine with several remapping units, the claim sends one request per unit that serves the source's segment, and waits for the last" — or, if one remapping unit is assumed: "The machine has one interrupt remapping unit per segment, and the claim asks the holder of its role."

## 13. `role_hand` of a unit role to a phantom node

**The sentence.** Line 1426: `role_hand` is `busy` "if the target is not live". Line 1397: "a unit role held by a phantom node would leave every request to it unanswered".

**The case.** A phantom node's member word reads live, so `role_hand` of a unit role to it passes the checks, and its hand-over never completes (no kernel to take step 5).

**Readings.** (a) `busy`, as for a target that is not live. (b) Allowed, and the role stays handing for ever.

**Implemented.** (a) (`roles::role_hand`).

**Why.** The contract already treats a phantom as not live for `node_stop` (line 1397) for the same reason.

**Proposed text.** In `role_hand`: "`busy` if the target is not live, or is a phantom node ([Roles])".

## 14. A thread that left its core for its removal and is chosen again

**The sentence.** Line 654: "a removal step that reaches the thread returns `again`"; "at that interrupt *b* ... stops running it and clears the mark, which makes its context eligible again if its holder is runnable".

**The case.** A thread being destroyed is not suspended by the step that marks it. Once *b* clears the mark the thread is runnable, and *b* may choose it again before the next removal step, which marks it again: the removal can return `again` for ever.

**Readings.** (a) The step that marks a thread for its removal also sets its suspended flag. (b) The removal step marks the root capability dying, and a thread whose object is dying is not chosen. (c) Nothing: the caller repeats until it wins the race.

**Implemented.** (a) (`caps.rs`, the removal's undo of a thread).

**Why.** The thread never runs again anyway (it is being destroyed); (a) costs one write, uses the flag every core already reads, and makes the removal end in at most two steps after the leave.

**Proposed text.** After "a removal step that reaches the thread returns `again`": "and sets the thread's suspended flag, so that its core does not choose it again once it has left".

## 15. The slot of an invalid remote capability that holds a mapping

**The sentence.** Line 873: "A use of an invalid remote capability is `gone`, judged with the slot, and the slot becomes dead."

**The case.** A remote frame capability whose record holds a mapping, used after its grant became revoking: making its slot dead removes the capability and its mapping at once, in the call, without the invalidation of the node's other cores ([TLB]) or of the units that serve its iospaces, which only a removal step starts.

**Readings.** (a) The slot becomes dead at once and the mapping is dropped without invalidation. (b) A capability whose record holds a mapping keeps its slot (the use is still `gone`) until a removal reaches it: the step of the `Revoke`, R2, or a removal by its holder.

**Implemented.** (b) (`Model::bury_stale`).

**Why.** (a) breaks the rule "when a call returns success, no thread on any core of the node can use a translation that the call removed"; the seeded exploration of the crossing found it at once on a holder of two cores.

**Proposed text.** "... is `gone`, judged with the slot, and the slot becomes dead, unless its record holds a mapping: then the slot stays until a removal reaches it, which undoes the mapping with its invalidations."

## 16. Who watches the heartbeats of a node's own cores

**The sentence.** Line 658: "If one core of a node ... does not acknowledge a request of its node within `CORE_ANSWER_NS` of the request's start (the core that started it sees this at the due event it armed, [TLB]), or its heartbeat goes stale while it is not idle, the node accuses itself (evidence self)".

**The case.** For the request the contract names who sees the failure and when; for the heartbeat it does not. A core of the node that stops answering while running, with no request in flight, is seen by nobody inside the node; and if it is the core at position 0, the node's recovery reserve stops with it, so the node no longer sweeps or reclaims.

**Readings.** (a) Every core of the node, at its own timer events, compares the heartbeats of the node's other cores with what it last saw, by the rule of stale evidence. (b) Only other nodes see it, by stale evidence.

**Implemented.** (a): `Model::watch_own_cores`, at every due event of every core of a node of several cores, from when the node is ready.

**Why.** (b) leaves a node whose reserve core is silent unable to recover anyone until another node happens to sweep it; (a) costs a read of *N* − 1 beacon words at each timer event, only on a node of several cores.

**Proposed text.** After "its heartbeat goes stale while it is not idle": "(each core of the node compares, at each of its timer events, the heartbeats of the node's other cores with what it last saw, by the rule of stale evidence)".
