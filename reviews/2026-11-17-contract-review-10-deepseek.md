# Contract review 10: what pass 17 wrote into the kernel contract

Reviewer: DeepSeek. Date: 17 November 2026. Under review: `architecture/kernel-interface.md` at
`d180986`, as pass 17 changed it (`540ee59`, `5f17991`), read against the whole contract, against
`architecture/kernel.md`, `architecture/security.md` and against decisions D-128 to D-134 of
`decisions/README.md`. Nothing was changed in any repository; this file is the only output.

References are `architecture/kernel-interface.md:LINE` at that commit unless another file is named.
Every quote is verbatim from the line cited.

---

## 1. `signal` cannot return `again` "with nothing changed" — severity high

**Quotes.**

- `kernel-interface.md:650`: "If the try fails, the call releases every lock it holds, having changed
  nothing, takes the locks it now knows it needs in the order … the call returns `again` and has
  changed nothing."
- `kernel-interface.md:653`: "`signal`, `notify_bind` and an arrival or a timer that signals a bound
  notify, the bound endpoint" and "**Each of these calls may therefore return `again` with nothing
  changed under L2** …: for `call`, `send`, `signal`, `notify_bind`, … it is new, and only under L2
  (D-134)."
- `kernel-interface.md:226`, the `signal` row: "Sets in the word the bits of the capability's badge,
  or bit 0 if it has no badge. If a thread waits, the first one is woken with the whole word and the
  word is cleared".

**Scenario.** A node of two cores, variant L2. Thread T1 on core 0 calls `signal` on notify N, which
`notify_bind` bound to endpoint E. The order of L2 puts the endpoint (kind 4) before the notify
(kind 6), and line 653 makes `signal` try the bound endpoint. T1 therefore changes N — by the atomic
OR of line 652 or under N's lock — and then needs E's lock, found by reading N while holding N: an
earlier lock, so it tries. Thread T2 on core 1 is inside `recv` on E, or a delivery is in progress on
E, so the try fails. Line 650 now requires T1 to release everything and return `again` "having
changed nothing", but the bits are already in N's word and an OR has no inverse; worse, if a third
thread had called `wait` on N in that window, the bits are gone with no trace. As written, the call
either returns `again` having changed the word, or it does not set the bits until after the try — and
then it is not taking its locks in the order at all.

**Smallest correction.** One clause in line 650, after "having changed nothing": "except the bits a
`signal` has set in its notify's word by an atomic OR, which cannot be undone: such a call returns
`again` with its bits already pending and no waiter woken, as after an arrival that found none."

---

## 2. `START_RETRY_NS` (1 ms) cannot be honoured inside a reserve of period 10 ms — severity high

**Quotes.**

- `kernel-interface.md:1204`: "The node that starts a core writes the request once and sends the wake
  again every `START_RETRY_NS` (1 ms), in its recovery reserve, until `started` equals its request or
  the node no longer reads starting with the request's generation".
- `kernel-interface.md:1335`: "It runs on an internal scheduling context of each node, the **recovery
  reserve**: bandwidth 1/64 of a core (2^26 in the units of [Admission](#scheduling-contexts)), period
  10 ms, admitted from start-up in the sum of the node's first core (position 0)".
- `kernel-interface.md:1487`: "| Recovery reserve | 1/64 of a core, period 10 ms | 156 µs of each 10
  ms, on the node's first core …".
- `kernel-interface.md:573`: "After the choice, the hardware timer is set to the earliest of: the
  instant the running context's budget ends … the first replenishment instant of the four throttled
  queues, the first firing instant of the timer queue … **An idle core with nothing armed sets no
  timer.**"

**Scenario.** Node A is starting and its first core is idle. A arms nothing but the reserve, whose
period is 10 ms: the reserve's context runs, spends its 156 µs, is throttled, and is selected again
only at its replenishment instant. Nothing in the contract gives a due event at 1 ms — not the reserve
(its replenishment is one per period), not a `timer` (which signals a `notify`, not the reserve), and
the core sets no timer when nothing is armed. So the retry of the wake happens at 10 ms, not 1 ms; and
the very mechanism that closes the lost wake-up between the stub's read of the start request and its
halt (line 1288: "An NMI that comes between the stub's read of the start request and its halt is
lost") runs ten times slower than the value the contract publishes in `abi/`. The cost is measurable:
`START_NS` (1 s) then covers 100 retries instead of 1,000, and a start that loses two or three wakes in
a row is accused with stale.

**Smallest correction.** Either set `START_RETRY_NS` to the reserve's period ("`START_RETRY_NS =
10_000_000`, the recovery reserve's period"), or keep 1 ms and add the due event it needs: "while a
start request is outstanding, the node arms a due event of its first core's timer queue every
`START_RETRY_NS`", which also gives that core an armed timer (see finding 9).

---

## 3. The memory of a destroyed object: two sentences on when the watermark returns — severity medium

**Quotes.**

- `kernel-interface.md:162`: "Memory is taken at a watermark that only moves up while an object made
  from the untyped lives. **When the last one is destroyed the watermark returns to the start:** this is
  the only moment the memory becomes usable again (as in seL4)."
- `kernel-interface.md:166`: "When the watermark moves past the clean mark, the clean mark moves with
  it; **when the watermark returns to the start, so does the clean mark.**"
- `kernel-interface.md:654` (new, D-134): "**The memory of a destroyed object is not reused while a core
  may still take its lock.** The watermark of an untyped moves back to its start only once every other
  core of the node has ended the kernel event it was in when the last object of the untyped was
  destroyed (its heartbeat has moved, or it is idle); until then `untyped_retype` on it returns
  `again`."

**Why it matters.** Line 162 states the return as the immediate consequence of the last destruction,
and calls it "the only moment the memory becomes usable again". Under L2 it is a later event on
another core, and the two sentences cannot both be true. The same applies to the clean mark at 166,
which is the mark that makes cleared memory observable to a new object: if the mark returns early, a
frame made next can read the words of a lock another core is about to take, which is exactly what 654
exists to prevent.

**Second half of the same rule that the text leaves open.** Nothing says *who* returns the watermark.
As written, the only reader of the condition is `untyped_retype`, so that call must read the heartbeat
(or the idle word) of every other core of the node on every creation — the most frequent call of a
memory service — and the return itself is then made inside a call that also checks its own arguments,
its slot and its untyped. That is buildable, but it is a cost on the object-creation path that the
rule does not name, and it puts the return in whichever thread happens to call `untyped_retype` first;
a node whose memory service is idle never returns the watermark at all.

**Smallest correction.** Rewrite the second sentence of 162: "When the last one is destroyed the
watermark is ready to return; it returns, and with it the clean mark (line 166), at the first
`untyped_retype` that finds that every other core of the node has ended the kernel event it was in
(D-134)."

---

## 4. Who frees a core's invalidation request — severity medium

**Quotes.**

- `kernel-interface.md:327`: "The core whose acknowledgement makes the acknowledged set equal to the
  asked set completes the request in the same event: through the gate it lowers the counts of the
  leaves the request cleared (G4, G6), empties the record and takes it out of its space's list …, makes
  the waiting thread runnable with its result, **and frees the request**."
- `kernel-interface.md:631`: "Each is written only by its core, except: the interrupt table, which the
  node's kernel writes for any of its cores, since a claim is a call; the pending set and the owes bit
  of the idle word, which a requesting core sets; and the acknowledged set of a request, in which each
  asked core sets its own bit."

**Scenario.** Core 0 of a node starts an invalidation request for a record of an `aspace`; core 3 is
the last to acknowledge, so core 3 is the "core whose acknowledgement makes the acknowledged set equal
to the asked set". Line 327 makes core 3 free the request, which lives in core 0's part of the node
block. Line 631 allows a core to write another core's part in three cases only — the interrupt table,
the pending set and the owes bit, and its own bit of the acknowledged set — and the request itself is
in none of them. So either the completion writes a word of another core's part (against 631, which is
the whole basis of the lock-free protocol: each core's part has one writer), or core 3 has no way to
tell core 0 that the request is over, and core 0's due event at `CORE_ANSWER_NS` reads an incomplete
request and accuses its own node (line 329: "if the request is not complete then, the node accuses
itself").

**Smallest correction.** Add the fourth exception to 631: "and the request of another core, which the
core whose acknowledgement completes it frees, and the completion it writes".

---

## 5. `again` is now a lock race, and three sentences still describe it as something else — severity medium

**Quotes.**

- `kernel-interface.md:1865`: "| `again` | A bounded step was done; repeat the call |" — against
  `kernel-interface.md:650`: "the call returns `again` and **has changed nothing**".
- `kernel-interface.md:653`: "**Rule 2 already asks every caller to handle `again`.**" — against
  `kernel-interface.md:12`: "2. **Any call can fail with `gone`.**", which says nothing of `again`;
  `again` enters the contract through rule 4 (line 14), for long operations.
- `kernel-interface.md:1719`–`1768`, the list "every value the shape of nodes and cores adds, changes
  or removes" and "**Errors.** None new.": the list carries `Again` for `ASpaceUnmap`, `ASpaceProtect`,
  `ThreadSuspend`, `TaskRevoke` and `MemoryGive`, and does **not** carry the fourteen calls that D-134
  gives a new `again` to (`call`, `send`, `signal`, `notify_bind`, `cap_derive`, `cap_move`,
  `untyped_retype`, `irq_claim`, `memory_take`, `ioports_issue`, `iospace_map`, `thread_configure`,
  `task_attach`, `sched_configure`).

**Scenario (the question the open point at line 2270 leaves open).** A thread of a process shares its
capability space with its peers, so a peer holds `write` on the segment that holds the receive range
of the endpoint a client calls. The peer loops `cap_move` into that segment; each of its calls takes
that segment's lock. The client's `call` (653: it tries "the segments of the receive range of the
thread found") fails its try whenever the peer holds the lock at that instant, returns `again` with
nothing done, and the client's library retries. This is a third party spending nothing but its own
budget to make another party's IPC return `again`, and no rule in the contract bounds the number of
repetitions: line 656 states "What it does not prove: that a call repeated after `again` ends". The
same construction works on `cap_derive`'s "segment of a neighbour in the derivation list". My answer to
the open point: a peer can make the *rate* of `again` as high as it likes and the number of
repetitions unbounded, but no interleaving in this text forces one call to return `again` for ever,
because each failure needs the other party's change or hold inside the call's own window. The bound is
therefore a fairness statement, not an interleaving, and the contract has none.

**Smallest correction.** Replace the citation in 653 with the truth — "Rule 4 already tells every
caller to repeat a call that returned `again`" — add the fourteen calls to the `abi/` list of changed
results at 1719, define `again` in 1865 as "the call did nothing and the caller must repeat it; a
bounded step may or may not have been done", and state the fairness rule the owners want: either "a
caller that is told `again` twice for the same call may keep the earlier lock it found, which the next
attempt takes first" (one word per thread, one more state in the layout) or "a kernel loop that
repeats a call is forbidden; only user space retries".

---

## 6. A debugger stop at gdb kills the node it stops — severity medium

**Quotes.**

- `kernel-interface.md:1636`: "The core that enters it sends the architecture's strongest signal (as
  the fence does) to every other core that runs a node, after it has raised the stop in the release
  word of kept memory … each saves its registers in its core's slot kept for the stub and **waits on
  that release word**; a core that does not stop within 10 ms is shown to gdb as running. Before the
  release, the stub clears every open observation of every node beacon, so that no node accuses
  another for the time stopped."
- `kernel-interface.md:666`: "**a lock wait, or a request not complete, longer than `CORE_ANSWER_NS`**
  (10 ms …) is a failure of the node (below)".
- `kernel-interface.md:672`: "the node accuses itself (evidence self), and the whole node is fenced and
  reclaimed".

**Scenario.** A development image runs a node of four cores. A developer stops the machine at gdb for
more than 10 ms (any human review of a variable takes longer). Core 2 waits for a lock held by core 1,
which is inside its stub waiting on the release word without IRET and without taking any further
event, so it neither releases the lock nor answers. Core 2's wait passes `CORE_ANSWER_NS`, and by 666
and 672 the node writes its own `panic` and accuses itself: the node is fenced and reclaimed, its
processes are gone, and the stop the developer is looking at is the corpse. The stub's countermeasure
covers the other direction — clearing the *observations* stops another node from accusing this one —
and evidence self and a fence already in flight are both outside it. A fence that was in progress when
the stop began also goes from fencing to unfenced at `FENCE_NS` (line 1243), and an unfenced node's
memory is never reused before the machine restarts (line 1228).

**Smallest correction.** One sentence in the debugger paragraph: "While the release word is raised,
`CORE_ANSWER_NS`, `FENCE_NS` and `SEAL_NS` are not measured and no node accuses itself: a wait that
finds the release word raised suspends, and resumes when it is cleared" — in a development image only,
which is where the release word exists.

---

## 7. A node can take another node's line and interrupt through an IOAPIC role it does not hold — severity high

**Quotes.**

- `kernel-interface.md:1017`, operation 5 of the operand table: "5 redirection entry | GSI (0-31), 1
  claimed or 0 masked (32), … | claimed: the handle, or the APIC ID, names a core whose word names the
  requester; **masked: the line is not claimed by another node**".
- `kernel-interface.md:750`, `irq_claim`: "State: `busy` if the vector is already claimed on that core,
  then `busy` if the source is a line whose input is already claimed (on any vector), then `no_slot`."
- `kernel-interface.md:744`: "An `irq` is one entry of a core's **interrupt table**. Each physical core has
  one table, which belongs to the node its core word names".
- `kernel-interface.md:1043`, the global read-only set of G: "the kernel image …, the kept image …, the
  fixed and living parts of the machine table (read only), the beacons and debug areas of other nodes
  and cores (read only), and the rings whose receiver is *X* (read only)". Rule 3 (line 13) lists "the
  interrupt table of each physical core" as an object of its own, apart from the machine table.

**Scenario.** Device D sits behind the IOAPIC and its line is GSI *g*; D's driver runs on node B, and B
claimed *g* through B's `irq_control` on one of B's cores (line 750: the claim is recorded in B's
interrupt table only). Node A holds neither the IOAPIC's role nor any of B's objects. A calls
`irq_claim` for its own core with the same GSI *g*: line 750's second state check reads *A's* table,
finds nothing, and A's claim succeeds. A then sends operation 5 with the claimed form and a handle of
A's own core; the holder checks "the handle … names a core whose word names the requester", which is
true, and nothing checks that the line belongs to A. The IOAPIC's redirection entry for *g* now points
at A's core and A's remapping handle, so B's device's interrupts arrive at A. B's `irq` stays fired
with its source masked and B's driver starves for lack of interrupts. The `masked` half of the same
check has the same hole and in the other direction: the holder is told to verify "the line is not
claimed by another node" and cannot, because the claim lives in B's node memory and A's kernel reads
neither the interrupt tables nor any other word of B. This is exactly the attack the contract uses to
justify the identifier words for devices (line 352: "without a word that ties it to an owner any node
holding the `iommu` capability could point another node's device at its own tables"), left open for
interrupt lines.

**Smallest correction.** Give a line the same kind of owner word a device identifier has: one word per
claimable GSI in the living part of the machine table, in the format of the ownership words, taken by
the `irq_claim` that claims a line and released when the `irq` is destroyed; then line 750's check and
the holder's checks for operations 5 read the word ("the line's word names the requester") instead of a
node-local table, and "on any vector" becomes "on any vector of the machine".

---

## 8. "a unit found failed is passed over" contradicts "the IOAPIC never points at a remapping entry that a unit's cache may still hold stale" — severity low-medium

**Quotes**, both in `kernel-interface.md:1019`:

- "**A unit found failed is passed over and the later units are still asked**; after the last one, the
  claim of a line sends its redirection entry (operation 5) to the holder of the IOAPIC's role in the
  same entry, **so the IOAPIC never points at a remapping entry that a unit's cache may still hold
  stale**".
- "then the call ends, `busy` if any unit was found failed."

**Scenario.** A machine with two IOMMU units serving one PCI segment. Unit 1 has already been found
failed (its `failed` bit is set, and by line 370 "every device of the unit stays as the unit has it: the
holder clears their context entries anyway (it cannot know that the unit applies it)"). Node A claims a
remapped line: it writes the remapping entry for handle *h*, asks unit 2 for the cache invalidation,
gets done, passes unit 1 over — so unit 1's interrupt-entry cache still holds whatever it held for *h* —
and then has the IOAPIC point the line at *h*. Unit 1 now delivers the line's interrupts from the stale
entry: the wrong vector, and a destination that the current claim never chose. The sentence that
promises the opposite is the sentence that justifies doing the redirection entry last.

**Smallest correction.** Weaken the "so" clause to what the mechanism gives: "so that the IOAPIC never
points at a remapping entry whose cache the units that answered have not invalidated; a unit found
failed may still hold a stale entry for the handle, which is one more cost of its failure, and the
claim says so with `busy`."

---

## 9. The `Ping` is not proved dead, and the sentence that would make it dead contradicts the idle rule — severity medium-high

**Quotes.**

- `kernel-interface.md:2269`: "**The sweep's `Ping` is never sent** …: "a successor that is idle with no
  armed timer is sent an interrupt and a ping message", but **the first core of every node that is
  starting, live or sealing keeps a timer armed, its recovery reserve's period and the sweep itself
  every `SWEEP_NS`**, so no successor is ever idle with nothing armed, and stale evidence already
  judges it by the instant of that timer."
- `kernel-interface.md:573`: "**An idle core with nothing armed sets no timer.**"
- `kernel-interface.md:1257`: "`idle_until`, the instant of its next armed timer when it goes idle (**the
  largest value if none**)".
- `kernel-interface.md:1268`, the stale evidence: "now − `STALE_NS` > `idle_until`".
- `kernel-interface.md:1335`: the reserve "is admitted from start-up in the sum of the node's first
  core" and, "When there is no such work, its time is slack and goes to others"; the work it lists is
  "the driver's fence, every node's steps R0 to R5, step R6, the rebuild of a unit role, and the kernel
  ring of messages from other nodes" — the sweep is not among them, and no line arms a due event at
  `SWEEP_NS`.

**Why the claim does not hold.** A scheduling context arms a timer only while it runs or while it is
throttled (line 573: the timer is set from the running context's budget end and from the four throttled
queues). A reserve with no work is neither: its internal thread is not runnable, so it sits in no queue
and has no replenishment instant to arm. So an idle node whose first core holds nothing else armed sets
no timer, writes `idle_until` = the largest value, and the stale test is false for ever — which is
precisely the state the sweep's ping was written for. The claim at 2269 is therefore not established,
and it is the opposite of 573.

**The sentences that are dead if the claim is made true.** If the owners add the arming sentence, then
these die and should go with it: the `Ping` row of the message table (`:921`, "Consumed; a ping left
unconsumed becomes stuck evidence"), the words row (`:938`, "| 9 | `Ping` | None | 0 |`), the failure
machinery sentence (`:942`, "no message but the sweep's `Ping`"), the credit sentence (`:954`, "a `Ping`
as the sweep's observation (one per pair)"), the ten-kinds list of "What a receiver keeps" (`:962`,
"`ReportAsk`, `Report`, `Ping`, `SendAnswer`, `Send` and `Signal`"), the last clause of the sweep
(`:1275`, "a successor that is idle with no armed timer is sent an interrupt and a ping message, which
becomes stuck evidence if it is not consumed"), and `NodeMessage::Ping = 9` (`:1761`) becomes a reserved
number.

**Smallest correction.** One sentence at the sweep (line 1275) or in the reserve (line 1335), and then
2269 becomes true and the sentences above can go: "The first core of every node that is starting, live
or sealing arms a due event of its recovery reserve at every period and the sweep at every `SWEEP_NS`,
so a node of the contract is never idle with nothing armed." The price is the one the open point
already names: an idle node can no longer sleep longer than 10 ms. If the owners prefer the price of the
ping, then 2269 is the sentence to delete, and the sweep's "idle with no armed timer" clause stays.

---

## 10. `memory_take` "never returns `again`" — severity low

**Quotes.**

- `kernel-interface.md:864`: "`memory_take` and `memory_split` never return `again`; `memory_give`
  returns `again` only, with nothing changed, when the request of the caller's core is in use."
- `kernel-interface.md:653`: "for `call`, `send`, `signal`, `notify_bind`, `cap_derive`, `cap_move`,
  `untyped_retype`, `irq_claim`, **`memory_take`**, `ioports_issue`, `iospace_map`, `thread_configure`,
  `task_attach` and `sched_configure` it is new, and only under L2 (D-134)."

**Scenario.** Under L2 a `memory_take` that tries the segment of a neighbour in the derivation list
(line 653) fails its try and returns `again` — which line 864 forbids in absolute terms, and which
`memory_take`'s own checks (line 852) do not list. A caller that trusts 864 (a memory service filling a
pool of blocks in one pass, say) treats an `again` as a success and loses the block.

**Smallest correction.** "`memory_take` and `memory_split` never return `again` **under L1, and under L2
only with nothing changed, when a try of the derivation list fails**".

---

## 11. Smaller matters I checked and would leave as they are, or flag without a finding

- **The no-deadlock argument itself holds.** I walked it for every call that line 653 lists as crossing
  the order and for the calls it does not list. A delivery holds the endpoint, then needs the thread at
  the head of its queue (kind 3 < 4), the receiver's receive-range segments (kind 0 < 4) and the
  receiver's core's queues (kind 10 > 4): the first two are tried, the last waited for. `cap_derive`
  and every derivation-list walk (kinds 0) try the neighbour's segment. An aspace's destruction (kind
  9) tries the segments of its records and the threads bound to it. `task_attach` (kind 3) tries the
  neighbours' thread locks. `sched_configure` tries the holder thread it finds through the context.
  A notify's bound endpoint is tried; a timer is tried through its core's queue (kind 8 < 10); an
  arrival's own core lock is released before it takes the notify (kind 6 < 10) and then the endpoint
  (kind 4). In every one of these a lock found through a held object is either later in the order and
  waited for, or earlier and tried, so "a core waits only for a lock that comes after every lock it
  holds" survives a successful try, and a cycle of waits would have to increase strictly in a total
  order. The gate lock last, with nothing taken after it and counted in *k*, and the bounds on a queue
  lock (*N* − 1 holders) then give the two-round bound `2 × k × (N − 1) × h`. I found no call whose
  locks break this, and the record of it in the reference model (the order each event takes, tries
  apart from waits) is the right check.
- **The thread-waits-on-an-object rule is sound and costs nothing on a common path.** Endpoint (4),
  reply (5) and notify (6) all lie after thread (3), so `thread_cancel`, `thread_suspend`, a
  destruction and `task_revoke` take the thread and then wait for the object in the order, and a
  delivery, an answer and a signal need no thread lock at all. The three queue-less waits (another
  node, a unit, the node's cores) are guarded by the thread's own lock, which is where line 194 puts
  them. It is the rule that makes the event paths of line 652 work: the endpoint's lock is what guards
  the receiver's wait fields, so "wakes the endpoint's first receiver if the binding still holds" needs
  no earlier lock.
- **The NMI rules and the start.** I walked a fence, a start, a late wake and a debugger stop against
  each other. The mark is written before any stop and the gate sends an NMI "only to a marked word or
  for a start" (G10, line 1061), so a late wake cannot be mistaken for a fence; a stub that takes a
  start request writes it into `started` and the entry stub then reads the core word and parks again
  unless the word is unmarked and names a starting or live node, so a fence that marks between the two
  still parks the core; the park stub writes `parked` from the request it reads, so a park confirmed
  from inside the entry stub is the request current at that moment and not an older one; and the park
  stub of a core that had parked itself writes `parked` again at the fence's NMI. I could not build a
  false confirmation that mattered: `started` can be set for a core that then parks, but only by a fence
  of the same node, and that node is dying. The one lossy window — an NMI between the stub's read of the
  start request and its halt — is covered for every core but the bootstrap core by the INIT and the two
  SIPIs of step 3, and for the bootstrap core the contract already records the residue as an open point
  ("The bootstrap core on x86-64", line 2248). Finding 2 is the part of this group that does not hold.
- **The domain numbers of a shared unit are consistent.** `d = ⌊(D − 2) / n⌋` makes the last slot's top
  number `n × d ≤ D − 2`, so number 0 and `D − 1` stay reserved; the operand field is 16 bits and
  `D ≤ 65,536`; the holder can check "the domain number is in the requester's range on the unit" from
  the fixed part of the machine table alone. I found no way for a node to use a number outside its
  range or to make two roots share one number through a request.
- **The operand table fits one ring entry and its bit ranges are consistent.** ⌈(16 + 24) / 64⌉ = 1 for
  three words; the handle is 16 bits and 341 cores × 192 entries = 65,472 < 65,536; the remappable
  MSI address the contract builds (bit 4 set, handle bits 14:0 in bits 19:5, bit 15 in bit 2, data 0)
  agrees with the redirection-entry form it quotes for operation 5 (index in bits 63:49, index bit 15
  in bit 11, bit 48 set).
- **"Traced and done" to a request whose operands fail.** I could not turn it into a gain for the
  sender: a refused request writes nothing to the unit, so the only false belief is about the
  requester's own request, and a correct requester never produces failing operands. The one case a
  correct requester can reach is an attach whose identifier word it has already taken: answered done, it
  believes a device is attached while the unit has no context entry, and `iospace_attach`'s later state
  check "the device is already attached to this iospace (success, nothing changes)" makes that
  permanent. It costs that node its own device and no other node anything, so I report it here rather
  than as a finding.
- **The two wait states and the bounds.** "No lock is held across a wait for another core or for a
  unit" (line 665) is consistent with the invalidation request being a state of the waiting thread and
  with the IOMMU confirmation being checked at later steps; the reserve of answers (`REQUESTS_PER_PEER
  + SENDS_PER_PEER + 10 = 34`), the two rings per ordered pair and the credit rules add up, and the
  `Report` of 28 items fits the 11-entry maximum.
- **`security.md:108`** was changed to match D-134 ("and accepts 0, the stamp of a sender attached to
  no task"). It states the cost the decision accepted; I found no sentence it makes false.

---

## External facts the pass says it read

I opened none of these sources today; where I say "from memory" I am reporting what I recall of the
document, not a check.

- **Arm DEN 0022, `CPU_ON` returns `ALREADY_ON` and `ON_PENDING`** (`kernel-interface.md:1204`, cited as
  "Arm DEN 0022D.b, section 5.6.2, read on 17 November 2026"). I confirmed by search today that
  DEN0022D.b exists and is the PSCI document (Arm, copyright through 2021). I could not open the
  document, so the section number is unverified; from memory, `CPU_ON` is §5.6.2 in DEN0022D and its
  return values include `ALREADY_ON` and `ON_PENDING`, with the meanings the contract gives. **The
  fact is right from memory; the section number is not checked.**
- **`AFFINITY_INFO` returning OFF for a core that has never been booted, and `ON_PENDING` counting as
  running** (`kernel-interface.md:1200`, cited as "Arm DEN 0022E, sections 6.6 and 5.7.2"). Right from
  memory. Note that the same subsection cites **two editions of one document** — DEN 0022E for
  `AFFINITY_INFO` and DEN 0022D.b for `CPU_ON` — which the contract's own rule for the Intel SDM ("the
  citations follow one edition", line 78) would not allow if applied to Arm.
- **Intel VT-d revision 4.1** (order D51397-016, March 2023), §6.2.2.1: the sentence quoted at line 1008
  ("if multiple context-entries are programmed with the same Domain-id (DID), such entries must be
  programmed with the same values for the Second-Stage Page Translation Pointer (SSPTPTR)") and "Software
  must not use domain-id value of 0 … on implementations reporting CM=1". Right from memory, including
  that the requirement is why the domain split is needed. Not opened today.
- **§11.4.2, the Capability Register's ND field (bits 2:0, 4-bit at 0 up to 16-bit at 6, 7 reserved) and
  `D = 2^(4 + 2 × ND)`.** Right from memory. Not opened today.
- **§6.5.2.7, the Interrupt Entry Cache Invalidate Descriptor, `IIDX` bits 47:32, `IM` bits 31:27, the
  granularity bit 4.** Right from memory, and consistent with the 16-bit handle the contract uses. Not
  opened today.
- **§5.1.5.1, "I/OxAPIC Programming"**, the remappable redirection entry with the interrupt index in bits
  63:49, index bit 15 in bit 11 and the format bit 48. Right from memory. Not opened today.
- **The Intel SDM, "order 325462-093, September 2026"**, and "§7.7.2, NMI Blocking". The combined-volumes
  order number 325462 is right from memory; the revision suffix and the date I could not check, and the
  section number for NMI blocking I could not check either.
- **Arm DDI 0487 K.a**, cited for the TLBI completion rule, `CnP`, "an entry that generates one of the
  listed faults is never cached in a TLB" and break-before-make. K.a is a revision I know exists; the
  clauses are not checked today.
- **The two other figures the pass relies on** — Linux v6.12 `adl_cstates` C6/C10 exit latencies of
  220 µs and 680 µs, and `native_flush_tlb_multi` in `arch/x86/mm/tlb.c` — are from memory plausible
  but unchecked.

No external fact in the pass looked wrong to me. The one defect I can state without the sources is the
two PSCI editions.

---

## What I did not check

- I did not run the reference model, the pass's explorer (`research/drafts/node-protocol-explorer.py`)
  or the trials; every "hold" and "fail" above is from reading the text.
- I read `kernel.md`, `security.md` and `decisions/README.md` (rows D-128 to D-134) for the sentences
  these changes could falsify, not as a whole. I did not read `memory.md`, `scheduling.md`,
  `drivers.md`, `platform.md`, `plan/verification.md` or the `contracts/` WIT files, so a contradiction
  between this contract and those files is outside this report.
- In `kernel-interface.md` I read the whole of Rules, Objects, System calls, the call groups through
  Interrupts, Memory and devices between nodes, The gate over page tables, Tasks and marks, Cores,
  Debugging, I/O ports, Entropy, Values to add to `abi/`, Changes for `abi/` and the model, Errors,
  Points for the two owners and Open points, and skimmed the Start-up state and the sections after it
  (synchronous or asynchronous, data plane, pager, power states, architectures, language split) only
  for statements the pass could have falsified. The start-up layout tables and the `abi/` records were
  not audited value by value.
- No measure of any lock hold, of `NMI_GRACE_NS`, of `FENCE_NS` or of a fence on real hardware was
  possible here; findings 2 and 6 depend on published values (10 ms, 1 ms, 20 ms) rather than on
  measured ones.
