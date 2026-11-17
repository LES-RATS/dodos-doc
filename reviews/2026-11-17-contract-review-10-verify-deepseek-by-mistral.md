# Verification of contract review 10 (DeepSeek) by Mistral

Verifier: Mistral. Date: 17 November 2026. Under review:
`/Users/btw/Documents/repos/Docs/reviews/2026-11-17-contract-review-10-deepseek.md`
(DeepSeek, 17 November 2026, ten findings), which reviews
`/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md`
(branch `main`, current working tree). I read that contract whole, together with
`/Users/btw/Documents/repos/Docs/architecture/kernel.md` and decisions D-128 to D-134 of
`/Users/btw/Documents/repos/Docs/decisions/README.md`.

Method. Every quote the review cites was opened at its file and line in the current tree;
the review's line numbers match this tree, and every quote I re-checked below is verbatim at
the line cited (all references `kernel-interface.md:LINE` are to that file). Each scenario was
replayed step by step against the full contract, looking for a sentence elsewhere that already
prevents it. External facts were checked today, 17 November 2026, by web search; anything I
could not open at the source is marked "from memory". Nothing was changed in any repository
and nothing was committed; this file is the only output. I worked alone and started no
subagents.

The review itself states that it opened no external source today and marks its own facts
"from memory"; where my checks today differ from or add to its external-facts section, I say
so in the external-facts section below.

---

## 1. `signal` cannot return `again` "with nothing changed" — CONFIRMED (high)

**Quotes, all verified verbatim.** `kernel-interface.md:650`: "If the try fails, the call
releases every lock it holds, having changed nothing, … the call returns `again` and has
changed nothing." `kernel-interface.md:653`: "`signal`, `notify_bind` and an arrival or a
timer that signals a bound notify, the bound endpoint" and "**Each of these calls may
therefore return `again` with nothing changed under L2** …". `kernel-interface.md:226`, the
`signal` row: "Sets in the word the bits of the capability's badge, or bit 0 if it has no
badge. If a thread waits, the first one is woken with the whole word and the word is
cleared". `kernel-interface.md:643`, the lock-free column shared by both variants:
"**signalling a notify**: one atomic OR on the notify's word, the lock taken only to wake a
waiter". `kernel-interface.md:648`, the order by kind: "the sequence words of `cspace`
segments …; task; thread; endpoint; reply; notify; timer; `sched`; aspace; iospace; the lock
words of cores …; the gate lock" — the endpoint (kind 4) comes before the notify (kind 6).

**Replay.** Node of two cores, variant L2. Thread T1 on core 0 calls `signal` on notify N,
which `notify_bind` bound to endpoint E. `signal` changes N — by the atomic OR of line 643
(the lock-free path) or under N's lock — and then needs E's lock, which it finds by reading N
while holding N: E comes earlier in the order (648), so it tries. Thread T2 on core 1 is
inside `recv` on E, so the try fails. Line 650 then requires T1 to release everything and
return `again` "having changed nothing", but the bits are already in N's word and an OR has
no inverse; worse, a third thread that called `wait` on N in that window consumes the bits
with no trace (226: the first waiter is woken with the whole word and the word is cleared).
So as written the call either returns `again` having changed N's word, or it must not set the
bits until after the try succeeds — and then it reads the binding through N before holding E,
which is exactly the out-of-order read the try rule exists for, and the second-round check of
650 ("checks that the object it read still leads to the same lock … the same binding") would
be meaningless. The same holds for `notify_bind`, which writes the binding into N before
trying the bound endpoint. Note the event path does not have this hole: line 652 makes an
arrival or a firing timer set the bits under its core's lock and then, on a failed try of the
notify or of the bound endpoint, release and take the locks in order (endpoint then notify),
and events "cannot return `again`" — so the contradiction is only on the call path under L2,
exactly as the review says.

**Verdict: confirmed.**

**Correction: right, and it must cover `notify_bind`'s binding write as well as `signal`'s
bits.** Exact text, at line 650, replacing "the call returns `again` and has changed nothing":

> the call returns `again` and has changed nothing, except the word of its notify, which
> cannot be undone: the bits a `signal` has already set in it by the atomic OR, or the binding
> a `notify_bind` has already written. Such a call returns `again` with its bits pending in
> the notify's word and no waiter woken, exactly as an arrival that found no waiter (line 652);
> line 653's "with nothing changed" carries the same exception for `signal` and `notify_bind`.

**Cost.** None on any path: the exception is paid only when a try fails (a lock race), never
on a memory access; the waiter semantics are unchanged, because bits left pending behave as
after an arrival that found no waiter.

---

## 2. `START_RETRY_NS` (1 ms) cannot be honoured inside a reserve of period 10 ms — CONFIRMED (high)

**Quotes, all verified verbatim.** `kernel-interface.md:1204`: "The node that starts a core
writes the request once and sends the wake again every `START_RETRY_NS` (1 ms), in its
recovery reserve, until `started` equals its request or the node no longer reads starting with
the request's generation". `kernel-interface.md:1335`: the reserve has "bandwidth 1/64 of a
core (2^26 …), period 10 ms, admitted from start-up in the sum of the node's first core
(position 0)", "When there is no such work, its time is slack and goes to others".
`kernel-interface.md:1487`: "| Recovery reserve | 1/64 of a core, period 10 ms | 156 µs of each
10 ms, on the node's first core |". `kernel-interface.md:573`: the hardware timer is set to
the earliest of the running context's budget end, "the first replenishment instant of the
four throttled queues, the first firing instant of the timer queue", and the heartbeat;
"**An idle core with nothing armed sets no timer.**" `kernel-interface.md:1288`: "An NMI that
comes between the stub's read of the start request and its halt is lost, so the node that
starts the core sends the NMI again every `START_RETRY_NS`". `kernel-interface.md:1484`:
`START_RETRY_NS` = 1 ms; `kernel-interface.md:1483`: `START_NS` = 1 s.

**Replay.** I searched the whole file for what arms a due event: the only armings are line 329
(a due event at `CORE_ANSWER_NS` for an invalidation request) and line 1629 (the console role
holder's pacing, "a due event every 1 ms"). Nothing arms a due event at `START_RETRY_NS`. The
reserve's replenishment is one per period, 10 ms; line 573 arms the timer from the first
replenishment instant of the throttled queues, so while the reserve has work the first core's
timer is armed at the reserve's replenishment — 10 ms away, not 1 ms. (So the review's phrasing
"nothing gives a due event at 1 ms" is exact; the refinement is that during an outstanding start
the timer is armed at all, because the wake is reserve work — the defect is the period, not a
missing timer. On a first core with nothing armed, no timer is set at all, per 573.) The
effective retry period is therefore the reserve's period, 10 ms: `START_NS` (1 s) covers about
100 retries, not 1,000, and the lost-wake window of line 1288 is covered ten times slower than
the value published in `abi/` (1484). If 1 ms were kept, 10 retries per 10 ms period would have
to fit in the reserve's 156 µs, i.e. at most about 15.6 µs per step, inside the 32-unit step
bound of 1335 — feasible, but only if a due event actually fires each millisecond, which
nothing arms.

**Verdict: confirmed.**

**Correction: either option closes it; the due-event option keeps the published value and is
precedented.** Line 1629 already shows the mechanism (a due event of the timer queue every
1 ms). Exact text, at line 1204, after "sends the wake again every `START_RETRY_NS` (1 ms), in
its recovery reserve":

> and arms a due event of its first core's timer queue at each `START_RETRY_NS` while the
> request is outstanding (as the console's pacing does, line 1629), so the retry really runs
> at 1 ms; the reserve's steps then number at most 10 per period within its 156 µs

(or, alternatively, change line 1484 to "`START_RETRY_NS` | 10 ms | the recovery reserve's
period; the wake is sent again at each replenishment of the reserve until …", which needs no
new mechanism). The same sentence belongs at line 1387 (`node_start` mode 0).

**Cost.** Paid only at a start (a rare event), never on a memory access: one due event per
retry on the node's first core. This satisfies the owners' principle.

---

## 3. Two sentences on when the watermark returns — CONFIRMED IN PART (medium)

**Quotes, all verified verbatim.** `kernel-interface.md:162`: "When the last one is destroyed
the watermark returns to the start: this is the only moment the memory becomes usable again
(as in seL4)." `kernel-interface.md:166`: "when the watermark returns to the start, so does
the clean mark." `kernel-interface.md:654` (D-134): "The watermark of an untyped moves back to
its start only once every other core of the node has ended the kernel event it was in when the
last object of the untyped was destroyed (its heartbeat has moved, or it is idle); until then
`untyped_retype` on it returns `again`."

**Replay.** Under L2 with N > 1, the return of the watermark is a later event on other cores
(their heartbeats moving), not the immediate consequence of the last destruction, so 162's
second sentence and 654 cannot both be true; 162 also calls the return "the only moment the
memory becomes usable again", which 654 denies (the memory becomes usable at the later moment).
Line 166 is keyed to "when the watermark returns", so it is not itself contradicted — it follows
whenever the return happens, and under 654 the clean mark must move only then; if the mark
moved early (with 162's reading), a frame made next could read the words of a lock another core
is about to take, which is what 654 exists to prevent.

**Who returns it (the review's second question): as written, only `untyped_retype` reads the
condition (654), so the first `untyped_retype` that finds every other core done performs the
return, reading the heartbeat or idle word of each of the N − 1 other cores. That is a cost on
the object-creation path the rule does not name, and a node whose memory service is idle never
returns the watermark at all (harmless, since nobody can use the memory meanwhile, but the rule
should say who does it).**

**Verdict: confirmed in part** — the contradiction between 162 and 654 is real under L2; 166 is
consistent with 654, not with 162's immediacy.

**Correction: the review's rewrite is right; add a state word so the N − 1 heartbeat reads are
paid only when a return is actually pending, not on every `untyped_retype`.** Exact text,
replacing the second sentence of line 162:

> When the last one is destroyed the watermark is *ready to return* (a word of the untyped's
> slot, set at that destruction); it returns to the start — and with it the clean mark
> (line 166) — at the first `untyped_retype` that finds every other core of the node has ended
> the kernel event it was in at that destruction, its heartbeat moved or idle (D-134, line 654);
> until then the memory is not usable again and `untyped_retype` on the untyped returns `again`.

**Cost.** One flag write at the last destruction of an untyped and one flag read per
`untyped_retype`; the N − 1 heartbeat reads only on the first `untyped_retype` after a full
destruction. All of it is paid at a destruction (a rare event), never on a memory access.

---

## 4. Who frees a core's invalidation request — CONFIRMED (medium)

**Quotes, all verified verbatim.** `kernel-interface.md:327`: "The core whose acknowledgement
makes the acknowledged set equal to the asked set completes the request in the same event: …
and frees the request." `kernel-interface.md:631`: "Each is written only by its core, except:
the interrupt table …; the pending set and the owes bit of the idle word, which a requesting
core sets; and the acknowledged set of a request, in which each asked core sets its own bit."
631 also lists, in the per-core part: "its invalidation request and its pending set".

**Replay.** Core 0 starts a request (the request lives in core 0's part of the node block);
core 3's acknowledgement completes it, so by 327 core 3 "empties the record and takes it out
of its space's list … and frees the request" — a write into core 0's part, which 631's three
exceptions do not allow. Either the completion violates 631 (the one-writer-per-core rule that
makes the lock-free protocol work), or core 3 has no way to tell core 0 the request is over, in
which case core 0's due event at `CORE_ANSWER_NS` (329: "if the request is not complete then, the
node accuses itself") fires and a healthy node fences itself.

**Verdict: confirmed.**

**Correction: right, and it must say how the owner knows the request is free, or the owner can
start a new request while the completer frees the old one.** Exact text, extending the
exceptions at line 631:

> … and the acknowledged set of a request, in which each asked core sets its own bit; and the
> request of another core, which the core whose acknowledgement completes it (line 327)
> empties and frees — the request carries a state word, *in use* written by its starting core
> and *done* written by the completing core by compare-and-swap, so a new request is started
> only after the old one reads *done*.

**Cost.** One CAS per completion, paid at a TLB shootdown completion — a rare event, never on
a memory access.

---

## 5. `again` is now a lock race, and three sentences still describe it as something else — CONFIRMED (medium)

**Quotes, all verified verbatim.** `kernel-interface.md:1865`: "| `again` | A bounded step
was done; repeat the call |", under the preamble at 1859: "Every caller handles `gone` and
`again`." `kernel-interface.md:653`: "**Rule 2 already asks every caller to handle `again`.**"
— against `kernel-interface.md:12`: "2. **Any call can fail with `gone`.**", which says nothing
of `again`; `again` enters the contract through rule 4 (line 14: "Every call is bounded. …
returns `again`; the caller repeats the call") and through 1859. `kernel-interface.md:1743`
(the changes list for `abi/`, 1719–1768): "**Errors.** None new." — the list carries `Again`
for `ASpaceUnmap`/`ASpaceProtect` (8, 9), `ThreadSuspend` (22), `TaskRevoke` (38) and
`MemoryGive` (49), but not for the fourteen calls that 653 gives a new `again` to (`call`,
`send`, `signal`, `notify_bind`, `cap_derive`, `cap_move`, `untyped_retype`, `irq_claim`,
`memory_take`, `ioports_issue`, `iospace_map`, `thread_configure`, `task_attach`,
`sched_configure`), whose rows say "unchanged".

**Replay.** Under L2, a call that fails a try returns `again` with nothing changed (650), so
1865's "a bounded step was done" is false for those calls — nothing was done. 653's citation
of rule 2 is wrong (rule 2 says only `gone`; rule 4 and 1859 carry `again`). The `abi/` list's
"Errors. None new." is inaccurate: `Again` is a new result for fourteen calls under L2 (D-134).

**Verdict: confirmed.**

**Correction: all four edits are right; the `again` definition must also absorb finding 1's
exception, or 1865 contradicts 650 again.** Exact texts:

- At 653, replace "Rule 2 already asks every caller to handle `again`." with: "Rule 4 and the
  Errors table (line 1859) already tell every caller to repeat a call that returned `again`."
- At 1865, replace the row with: "| `again` | The call did nothing — except the word of its
  notify, for `signal` and `notify_bind` (line 650) — or a bounded step was done; repeat the
  call |"
- In the `abi/` changes list (1719–1768), add `Again` to the rows of `Call` (10), `Send` (13),
  `Signal`, `NotifyBind`, `CapDerive` (0), `CapMove` (1), `UntypedRetype`, `IrqClaim` (46),
  `MemoryTake`, `IoportsIssue`, `IoSpaceMap` (32), `ThreadConfigure` (18), `TaskAttach`,
  `SchedConfigure` (24), each with "under variant L2 only, with nothing changed (D-134)"; and
  replace "**Errors.** None new." (1743) with: "**Errors.** `Again` added to the fourteen calls
  of [A node of several cores](#a-node-of-several-cores) under variant L2 (D-134); none other."

**Cost.** Documentation only; no run-time cost.

---

## Finding 5 and the open point at line 2270: can another party make a call return `again` for ever?

**Answer: yes for the number of repetitions — another party can make a given call return
`again` an unbounded number of times; no single invocation can be made to run for ever, because
each invocation is bounded (two rounds, line 650) and returns.** The bound that exists is
per-call; the bound that is missing is a fairness rule across calls, and line 656 concedes
exactly that ("What it does not prove: that a call repeated after `again` ends").

**Scenario.** Node of N ≥ 2 cores, variant L2. Victim thread V on core 0 calls `call` on
endpoint E; the receiver thread found at the head of E's queue has its receive range in `cspace`
segment S. Attacker thread A on core 1 shares the capability space (same task, or a derived
space with `write` on S) and loops `cap_move` into and out of slots of S; each of its calls takes
S's segment lock (kind 0, first in the order of 648). V's `call` holds E's lock, reads the head
thread, and tries S — S comes earlier than the endpoint, so it is tried, never waited for
(650). Whenever A holds S at that instant, the try fails and V's call returns `again` with
nothing changed. V's library retries.

**Why the repetitions are unbounded.** Each `again` needs A's hold or change to overlap V's try
window inside V's own two-round call, and that window includes waits of up to
2 × k × (N − 1) × h (656), so a continuously running A on another core can hit it every time.
A's scheduling budget bounds how much of each period A may run, but not the number of periods:
A can spend its whole budget, every period, holding S. No rule in the contract forces A to
yield, and none bounds the number of times V is told `again`. So V's IPC can starve indefinitely
— a liveness failure — while every individual call stays bounded and returns. The same
construction works on `cap_derive`'s "segment of a neighbour in the derivation list" and on the
receive-range segments of 653, as the review says. The contract's budgets bound each party per
period, not the number of repetitions.

**Correction: a fairness rule is needed; the review's first option is the right shape, and it
must be phrased so it does not break the no-deadlock proof** (taking the contested lock first is
safe only if the caller holds nothing while waiting for it, which keeps the invariant of 656:
a core waits only for a lock after every lock it holds — here, after none). Exact text, at line
656, after "What it does not prove":

> A caller that has been told `again` twice for the same call may, on its next attempt, release
> every lock it holds and take the lock that failed its try first, waiting for it as for any
> lock taken in order with nothing held, and then take the locks it needs in the order; the
> check of the second round is unchanged. (One word per thread: the count of `again` for the
> current call.)

**Cost.** One word per thread and one counter increment per `again` — paid only at a lock race,
never on an uncontended call. The review's alternative ("a kernel loop that repeats a call is
forbidden; only user space retries") does not add a bound either, since the retrying caller is
always user space; I would not write it.

---

## 6. A debugger stop at gdb kills the node it stops — CONFIRMED (medium)

**Quotes, all verified verbatim.** `kernel-interface.md:1636`: the entering core "sends the
architecture's strongest signal … to every other core that runs a node, after it has raised
the stop in the release word of kept memory … each saves its registers in its core's slot kept
for the stub and **waits on that release word**; a core that does not stop within 10 ms is
shown to gdb as running. Before the release, the stub clears every open observation of every
node beacon, so that no node accuses another for the time stopped." `kernel-interface.md:666`:
"**a lock wait, or a request not complete, longer than `CORE_ANSWER_NS`** (10 ms …) is a failure
of the node". `kernel-interface.md:672`: "the node accuses itself (evidence self), and the
whole node is fenced and reclaimed". `kernel-interface.md:1243`: fencing → unfenced when
"`FENCE_NS` has passed since the first action of the fence without every confirmation";
`kernel-interface.md:1228`: an unfenced node's "own memory and the frames granted to it are
never reused until the machine restarts".

**Replay.** Development image, node of four cores, developer stops at gdb for more than
`CORE_ANSWER_NS` = 10 ms. Core 1 is in its stub waiting on the release word, possibly in the
middle of a kernel event, so it neither releases a lock it holds nor acknowledges a request.
Core 2's wait for that lock passes 10 ms; by 666 and 672 the node accuses itself and is fenced
and reclaimed. The stub's countermeasure at 1636 covers only the other direction — clearing the
observations stops *another* node from accusing this one — not the self-accusation path of 672,
not a fence already in flight going unfenced at `FENCE_NS` (1243), and not the core that does not
stop within 10 ms (1636), which keeps running and can itself become the silent core.

**Verdict: confirmed.**

**Correction: right; the release word exists only in development images, so the suspension
costs nothing in production.** Exact text, appended to the debugger paragraph at 1636:

> While the release word is raised, `CORE_ANSWER_NS`, `FENCE_NS` and `SEAL_NS` are not measured
> and no node accuses itself: a wait or a fence step that finds the release word raised
> suspends and resumes when it is cleared (development images only, which is where the release
> word exists).

**Cost.** One read of the release word at each due event and accusation check, only in
development images — never in production, never on a memory access.

---

## 7. A node can take another node's interrupt line through an IOAPIC role it does not hold — CONFIRMED (high)

**Quotes, all verified verbatim.** `kernel-interface.md:1017`, operation 5: "claimed: the
handle, or the APIC ID, names a core whose word names the requester; **masked: the line is not
claimed by another node**". `kernel-interface.md:750`, `irq_claim`: "State: `busy` if the vector
is already claimed on that core, then `busy` if the source is a line whose input is already
claimed (on any vector), then `no_slot`." `kernel-interface.md:744`: "An `irq` is one entry of
a core's **interrupt table**. Each physical core has one table, which belongs to the node its
core word names"; "When a node's generation ends, R6 leaves the tables of its cores with no entry
claimed before the cores are free". `kernel-interface.md:1043`, the global read-only set of G:
"the kernel image …, the kept image …, the fixed and living parts of the machine table (read
only), the beacons and debug areas of other nodes and cores (read only), and the rings whose
receiver is *X* (read only)" — another node's interrupt table is not in it, and rule 3 (line
13) lists "the interrupt table of each physical core" as fixed kernel memory of its own.
`kernel-interface.md:773`: "A line can be claimed through the `irq_control` of any node, on one
of its cores. The inputs of an IOAPIC … have one writer, the holder of the IOAPIC's role …: the
claiming node asks it to program the redirection entry, and waits (a unit request …)".
`kernel-interface.md:352`: the identifier word exists because "without a word that ties it to an
owner any node holding the `iommu` capability could point another node's device at its own
tables". `kernel-interface.md:804`: the writer rules of the living part, and that a dead
generation's words are cleared by step R6.

**Replay.** Device D behind the IOAPIC, line GSI *g*, driver on node B; B claimed *g* through
B's `irq_control` on one of B's cores — recorded only in B's core's interrupt table (744). Node
A holds neither the IOAPIC's role nor any of B's objects. A calls `irq_claim` for its own core
with the same GSI *g* (773 explicitly permits a line through any node's `irq_control`): 750's
second check reads A's table, finds nothing, and the claim succeeds. A then sends operation 5
in the claimed form with a handle of A's own core; 1017's check "the handle … names a core whose
word names the requester" is true, and nothing checks that the line belongs to A — the masked
half, "the line is not claimed by another node", is unverifiable by the holder, because the
claim lives in B's node memory, which A's kernel cannot read (1043, rule 3). The IOAPIC's
redirection entry for *g* now points at A's core and handle (773: the holder programs it on the
claiming node's request), so B's device's interrupts arrive at A; B's `irq` stays claimed with
its line masked (791) and B's driver starves. This is the line-side twin of the attack that
line 352's design choice describes for device identifiers.

**Verdict: confirmed.** This is the most severe finding: a containment hole between nodes,
exactly the class the ownership words were introduced to close.

**Correction: the review's owner word is the right mechanism but incomplete — it must follow the
rules of taking and be cleared for dead generations like every other living-part word**
(rules of taking at 352 and 875; writer rules and R6 at 804; interrupt tables cleared by R6 at
744), or a dead node's line words leak and the line can never be claimed again. Exact text,
added in the Interrupts section after the first sentences of line 744:

> A claimable line has an owner word, like a device identifier (line 352): one word per GSI of
> each IOAPIC known to the kernel, in the living part of the machine table, in the format of the
> ownership words, fixed at machine start-up (rule 3). `irq_claim` of a line takes the line's
> word for the caller's node by the rules of taking (free and this node's, unclaimed, of a dead
> node, or taken by a generation that is over) — `busy` if it is taken by another live node —
> and the destruction of the `irq` writes it free, unclaimed; step R6 clears the words of a
> generation that is over, as it clears the interrupt tables of its cores (line 744) and the
> other words of the living part (line 804).

and at line 750, replacing the state checks:

> State: `busy` if the vector is already claimed on that core, then `busy` if the source is a
> line whose word is taken (on any vector of the machine), then `no_slot`.

and at line 1017, operation 5:

> claimed: the handle, or the APIC ID, names a core whose word names the requester, and the
> line's word names the requester; masked: the line's word is free or names the requester;

**Cost.** One word per GSI (32 per IOAPIC on x86-64 — a fixed table added to rule 3's list), one
CAS at claim and one write at destruction or R6: paid at a claim or a death, never on a memory
access. The checks at 750 and 1017 become reads of the global read-only set instead of
node-local tables.

---

## 8. "A unit found failed is passed over" vs "the IOAPIC never points at a stale remapping entry" — CONFIRMED (low-medium)

**Quote, verified verbatim, both sentences on line 1019:** "**A unit found failed is passed
over and the later units are still asked**; after the last one, the claim of a line sends its
redirection entry (operation 5) to the holder of the IOAPIC's role in the same entry, **so the
IOAPIC never points at a remapping entry that a unit's cache may still hold stale**; then the
call ends, `busy` if any unit was found failed." Also `kernel-interface.md:370`: a failed unit's
"devices stay as the unit has it … their identifier words stay *taken* … every later request on
the unit are `busy`".

**Replay.** Two IOMMU units serve one PCI segment; unit 1 is failed. A claim writes remapping
entry *h*, asks unit 2, gets done, passes unit 1 over — so unit 1's interrupt-entry cache may
still hold a stale entry for *h* — and then has the IOAPIC point the line at *h*. Unit 1 can then
deliver the line's interrupts from the stale entry. The "so" clause is false exactly when a
unit was passed over, which is also when the call ends `busy` — the only signal. Line 1019's
own "Why go on past a failed unit" confirms the contract deliberately goes on (stopping would
leave the later units' caches stale instead).

**Verdict: confirmed.**

**Correction: the weakened "so" clause is exactly what the mechanism gives.** Exact text, at
line 1019, replacing "so the IOAPIC never points at a remapping entry that a unit's cache may
still hold stale":

> so the IOAPIC never points at a remapping entry whose interrupt-entry cache the units that
> answered have not invalidated; a unit found failed may still hold a stale entry for the
> handle, one more cost of its failure, and the call says so with `busy`

**Cost.** None; documentation of what the mechanism gives.

---

## 9. Whether the `Ping` rule can ever fire — the review is RIGHT; the open point at 2269 is REFUTED (medium-high)

**Quotes, all verified verbatim.** `kernel-interface.md:2269`: "**The sweep's `Ping` is never
sent** … the first core of every node that is starting, live or sealing keeps a timer armed,
its recovery reserve's period and the sweep itself every `SWEEP_NS`, so no successor is ever
idle with nothing armed …". `kernel-interface.md:573`: "**An idle core with nothing armed sets
no timer.**" `kernel-interface.md:1257`: `idle_until` is "the instant of its next armed timer
when it goes idle (**the largest value if none**)". `kernel-interface.md:1268`, stale
evidence: "now − `STALE_NS` > `idle_until`" (written so it cannot wrap when `idle_until` is the
largest value). `kernel-interface.md:1335`: "When there is no such work, its time is slack and
goes to others". `kernel-interface.md:1275`: "a successor that is idle with no armed timer is
sent an interrupt and a ping message, which becomes stuck evidence if it is not consumed."

**Replay, and the answer to the brief's question.** The only arming rules in the contract are
line 573 (running context's budget end, first replenishment of the four throttled queues, first
firing of the timer queue, heartbeat `STALE_NS`/2 while running a thread) and two due-event
armings, at 329 (`CORE_ANSWER_NS`) and 1629 (console pacing, 1 ms). A grep of `SWEEP_NS` finds it
only at 672, 1275, 1479, 2249 and 2269: **no line arms a timer at `SWEEP_NS` or at the reserve's
period.** A context arms a timer only while it runs or while it is throttled in a queue; the
reserve with no work "is slack and goes to others" (1335), sits in no queue, and arms nothing.
So an idle node whose first core holds nothing else armed sets no timer (573), writes
`idle_until` = the largest value (1257), the stale test is false for ever (1268), and the core
"takes the deepest state" (623: "With no armed instant, it takes the deepest state"); line 1274
says "cores sleep without heartbeats every millisecond". Line 672 itself presupposes the state
is reachable: "when every other core of the node is idle with nothing armed, no core of the node
watches, and the silent core is found by the sweep of the other nodes". Therefore "a successor
that is idle with no armed timer" (1275) **is** reachable, the sweep's interrupt and `Ping`
**can** be sent, and 2269's claim that the `Ping` is never sent has no arming sentence behind it
and contradicts 573. (The review cited 573, 1257, 1268, 1335; I add 623, 672, 1274 and the
`SWEEP_NS` grep.)

**Verdict: the review's finding 9 is confirmed — the contract's claim at 2269 is refuted by
573/623/1335, not merely unproved.** The review's list of sentences that die if the arming is
added is correct: 921 (the `Ping` row), 938 (the words row "| 9 | `Ping` | None | 0 |"), 942 ("no
message but the sweep's `Ping`"), 954 ("a `Ping` as the sweep's observation (one per pair)"),
962 (the ten-kinds list including `Ping`), the last clause of 1275, and `NodeMessage::Ping = 9`
at 1761, which becomes a reserved number.

**Correction: the either/or is right, and the contract currently asserts both designs at once.**
If the owners want the `Ping` to be dead, add the arming sentence; exact text, at 1275 or 1335:

> The first core of every node that is starting, live or sealing arms a due event of its timer
> queue at every period of its recovery reserve and at every `SWEEP_NS`, so a node of the
> contract is never idle with nothing armed; with that arming the sweep's `Ping` is never sent
> (the interrupt alone wakes the successor) and the sentences named at line 2269 — the `Ping`
> row (921), the words row (938), the failure-machinery sentence (942), the credit sentence
> (954), the ten-kinds list (962), the last clause of the sweep (1275) and
> `NodeMessage::Ping = 9` (1761) — are removed.

If the owners prefer deep idle, delete the claim at 2269 and keep 1275's "idle with no armed
timer" clause as written. Note the tension the owners must decide: arming costs an idle node a
wake every 10 ms, which is what 672 rejects ("waking idle cores to watch would be paid on every
idle period") and what 2269 names as the price; the arming option also gives finding 2's due
event on a starting node. Per the owners' principle the price is paid on every idle period, not
on a memory access — it is a power cost, and it is theirs to choose; the contract must not
assert both.

---

## 10. `memory_take` "never returns `again`" — CONFIRMED (low)

**Quotes, all verified verbatim.** `kernel-interface.md:864`: "`memory_take` and
`memory_split` never return `again`; `memory_give` returns `again` only, with nothing changed,
when the request of the caller's core is in use." `kernel-interface.md:653`: among the calls
that try "the segment of a neighbour in the derivation list": "… `untyped_retype`,
`irq_claim`, **`memory_take`**, `ioports_issue` …", and "Each of these calls may therefore
return `again` with nothing changed under L2". `kernel-interface.md:852`, `memory_take`'s own
checks, does not list `again`.

**Replay.** Under L2 a `memory_take` that tries the segment of a derivation-list neighbour
fails its try and returns `again` with nothing changed — which 864 forbids in absolute terms.
A caller that trusts 864 (a memory service filling a pool in one pass) treats the `again` as
success and loses the block. `memory_give` has the same hole: 864 says it returns `again` only
when the request of the caller's core is in use, but under L2 a give that walks the derivation
list of the run can also fail a try and return `again` with nothing changed.

**Verdict: confirmed.**

**Correction: right, extended to `memory_give`.** Exact text, replacing the sentence at 864:

> `memory_take` and `memory_split` never return `again` under L1, and under L2 only with
> nothing changed, when a try of a segment of the derivation list fails; `memory_give` returns
> `again`, with nothing changed, when the request of the caller's core is in use or, under L2,
> when a try of a segment of the derivation list fails.

**Cost.** None; documentation.

---

## What the review missed in L2 locking and its no-deadlock proof, the NMI rules and the start, domain numbers and the unit operations

I re-walked all three groups myself, to the same standard (every lock each event takes, tries
apart from waits, against the order of 648, the try rule of 650, the wait-fields rule of 651,
the event paths of 652, the three lock-less state kinds of 646, and the cycle argument of 656).
The review's section 11 is correct on all three, and I found no logical miss in them:

- **L2 locking and the no-deadlock proof holds.** In every path I checked — delivery (endpoint,
  then the head thread and the receive-range segments by try, the receiver's core queues by
  wait), `cap_derive`/`cap_move` (neighbour segments by try), aspace destruction (record slots
  and bound threads by try), `task_attach` (neighbour threads by try), `sched_configure` (holder
  thread by try), a notify's bound endpoint (by try), a timer through its core's queue (by try),
  the arrival path (core's lock, then notify and endpoint by try, or released and retaken in
  order), the thread-waits-on-an-object rule of 651 — a lock found through a held object is
  either later in the order and waited for, or earlier and tried, so "a core waits only for a
  lock that comes after every lock it holds" survives, and a wait cycle would have to increase
  strictly in a total order and come back: impossible. The gate lock last (646), queue locks
  serving at most N − 1 holders, and the two-round bound 2 × k × (N − 1) × h all stand. What the
  review did not state: 656 already concedes the repetition question (my finding-5 answer above),
  so the proof's scope is honestly bounded; and the proof's real blind spot is not deadlock but
  the "nothing changed" claim on the lock-free OR path (finding 1).
- **The NMI rules and the start hold, with finding 2 as the one defect in the group.** I
  re-walked G10 (1061: INIT/SIPI/NMI only to a marked word, or a start to a joining/owned word
  of a starting node with the right generation), the `started`/`parked` writes (1204, 1288), the
  fence's mark-before-stop, and the lost NMI window of 1288. The review is right that the only
  residue is the bootstrap core (open point 2248). My addition: while a start is outstanding the
  reserve does have work, so its replenishment does arm the first core's timer — at 10 ms; the
  published 1 ms needs the due event of the finding-2 correction, and the pattern already exists
  at 1629 (the console's pacing arms a due event every 1 ms), which the review did not cite.
- **Domain numbers and unit operations hold.** I re-checked the arithmetic: with D domains and
  n node slots, d = ⌊(D − 2)/n⌋ and slot s owns 1 + s·d … (s + 1)·d, so the last slot's top
  number is n·d ≤ D − 2 and numbers 0 and D − 1 stay reserved; the operand field is 16 bits and
  D ≤ 65,536 (ND = 6 gives 2^(4 + 2×6) = 65,536), so every number fits; 341 cores × 192 entries
  = 65,472 < 65,536 fits the 16-bit remapping handle; the operand table's 16 + 24 bits fit one
  64-bit ring entry; the remappable MSI address the contract builds (bit 4 set, handle bits
  14:0 in bits 19:5, bit 15 in bit 2, data 0) agrees with the RTE remappable form quoted at 1017
  (index in bits 63:49, index bit 15 in bit 11, bit 48 set); the answer reserve 16 + 8 + 10 = 34
  = `RING_ANSWER_RESERVE`. All hold. What the review did not flag in this group: for finding 7,
  R6 already clears a dead generation's interrupt tables (744) and living-part words (804), and
  the line-word correction must reuse those rules (my exact text above does).

What the review missed overall, beyond those sections, is documentary, not logical: the
contract cites **two editions of the PSCI document** (DEN 0022D.b at 1204 and DEN 0022E at
1200) while its own one-edition rule (line 78: "the Intel SDM citations follow one edition") is
stated for the SDM only — and both cited PSCI editions, the VT-d revision 4.1 and Arm DDI 0487
K.a are superseded today (see below). Also, for finding 9, line 672 independently presupposes
that "idle with nothing armed" is reachable, which refutes 2269 without needing the scheduling
argument — the review cited 573 but not 672.

---

## External facts, checked today, 17 November 2026

The review opened none of these and marked most "from memory"; I checked today by web search.
Where I could not open the source itself, I say "from memory".

- **Intel SDM, order 325462, version 093.** intel.com's SDM page states today: "The downloadable
  PDFs of all IA-32 Architectures Software Developer's Manual volumes are at version 093", and
  the Vol. 3A 093 PDF is published (cdrdv2-public.intel.com/929359/253668-093-sdm-vol-3a.pdf).
  So 325462-093 is the current edition today, as the contract cites it. The "September 2026"
  date of 093: not separately confirmed today — from memory and search snippets only. §7.7.2
  "NMI Blocking": the 093 Vol. 3A table of contents contains "NMI Blocking" and the exception
  reference sits in chapter 7 (Event 9 at page 7-37), which is consistent with §7.7.2 in the 093
  numbering; the full clause was not re-read today — from memory, corroborated by a public
  issue tracker that cites "Intel SDM 325462-093" for NMI-blocking semantics. §34.5.1/§34.14.2
  (INIT in SMM) and §2.5 (CR0.WP): from memory, not checked today.
- **PSCI, Arm DEN 0022.** DEN0022D.b and DEN0022E both exist as cited. CPU_ON is §5.6, with
  §5.6.2 corroborated by a 2026 patch citing "Section 5.6.2 'Caller responsibilities'"; AFFINITY_INFO
  is §5.7 — the contract's section numbers are right, and the ALREADY_ON / ON_PENDING return
  values are confirmed (E's revision history: "Added ON_PENDING return value of CPU_ON"; 2026
  patches quote both). AFFINITY_INFO's OFF also meaning "has not been booted yet": from memory,
  not re-read today. **The review's defect is confirmed and is worse than it states: the latest
  edition today is DEN0022F.b (PSCI v1.3, 2024)** — two independent 2026 sources quote it — so
  the contract cites two editions of one document, both superseded, against the spirit of its own
  one-edition rule (line 78).
- **Intel VT-d.** Revision 4.1, order D51397-016, exists exactly as cited
  (cdrdv2-public.intel.com/774206). But newer editions exist today: D51397-017 (Rev 5.0),
  D51397-018, and D51397-019, which is Rev 5.20 and is quoted as the current spec in a December
  2026 audit. The cited section numbers still exist in the newer numbering (§4.2.3, §6.5.2.6,
  §5.1.5.1 "I/OxAPIC RTE Programming" at 5-8, the §11.4.x registers) per the search snippets. The
  quoted rules — same Domain-id must have the same SSPTPTR and domain-id 0 must not be used with
  CM=1 (§6.2.2.1); ND bits 2:0 with D = 2^(4 + 2×ND), up to 65,536 at ND = 6 (§11.4.2); the
  interrupt-entry-cache invalidation descriptor (§6.5.2.7); the I/OxAPIC remappable RTE fields
  (index bits 63:49, index bit 15 in bit 11, bit 48 set, §5.1.5.1) — are right from memory and
  corroborated by the driver code the contract itself links (Zephyr's `intc_intel_vtd.h`, QEMU's
  `intel_iommu.h`) and by Linux/QEMU invalidation code in today's results; I could not open the
  spec PDFs to re-read each clause today, so the bit positions are from memory.
- **Linux v6.12 `adl_cstates`.** Confirmed at the v6.12 tag of torvalds/linux
  `drivers/idle/intel_idle.c`: C6 exit_latency 220 µs (target_residency 600), C8 280, and C10
  ("MWAIT 0x60") exit_latency 680 µs (target_residency 2000). The contract's C6/C10 exit
  latencies of 220/680 µs are right for v6.12.
- **Arm DDI 0487 (Armv8-A Arm ARM).** K.a exists as cited (May 2024), but L.a (January 2025) and
  L.b exist, and a 2026-dated known-issues document is current — so K.a is at least two editions
  behind today. The cited clauses (16 KB granule stage-1 lookup starting at level 0 indexed by
  bit 47; CnP; break-before-make): from memory, not re-checked today.
- **RISC-V SBI HSM.** The contract's link resolves to the ratified SBI v3.0
  (docs.riscv.org/reference/sbi/v3.0/ext-hsm.html); `sbi_hart_start` returns
  `SBI_ERR_ALREADY_AVAILABLE` for an already-started hart — confirmed by the spec text in today's
  results.
- **GICv3 (Arm IHI 0069):** not re-checked today; from memory.

---

## Corrections to apply, in order of severity, each as exact text

1. **Finding 7 (high) — a line gets an owner word.** In the Interrupts section, after the first
   sentences of `kernel-interface.md:744`, add: "A claimable line has an owner word, like a
   device identifier (line 352): one word per GSI of each IOAPIC known to the kernel, in the
   living part of the machine table, in the format of the ownership words, fixed at machine
   start-up (rule 3). `irq_claim` of a line takes the line's word for the caller's node by the
   rules of taking (free and this node's, unclaimed, of a dead node, or taken by a generation
   that is over) — `busy` if it is taken by another live node — and the destruction of the `irq`
   writes it free, unclaimed; step R6 clears the words of a generation that is over, as it
   clears the interrupt tables of its cores (line 744) and the other words of the living part
   (line 804)." At 750, replace the state checks with: "State: `busy` if the vector is already
   claimed on that core, then `busy` if the source is a line whose word is taken (on any vector
   of the machine), then `no_slot`." At 1017, operation 5: "claimed: the handle, or the APIC ID,
   names a core whose word names the requester, and the line's word names the requester; masked:
   the line's word is free or names the requester; …"
2. **Finding 1 (high) — the `again` of a `signal`/`notify_bind` exception.** At
   `kernel-interface.md:650`, replace "the call returns `again` and has changed nothing" with:
   "the call returns `again` and has changed nothing, except the word of its notify, which
   cannot be undone: the bits a `signal` has already set in it by the atomic OR, or the binding
   a `notify_bind` has already written. Such a call returns `again` with its bits pending in the
   notify's word and no waiter woken, exactly as an arrival that found no waiter (line 652);
   line 653's 'with nothing changed' carries the same exception for `signal` and `notify_bind`."
3. **Finding 2 (high) — the wake retry really runs at `START_RETRY_NS`.** At
   `kernel-interface.md:1204` (and 1387), after "sends the wake again every `START_RETRY_NS`
   (1 ms), in its recovery reserve", add: "and arms a due event of its first core's timer queue
   at each `START_RETRY_NS` while the request is outstanding (as the console's pacing does, line
   1629), so the retry really runs at 1 ms; the reserve's steps then number at most 10 per period
   within its 156 µs". (Alternative: at 1484 set `START_RETRY_NS` to 10 ms, the reserve's period.)
4. **Finding 9 (medium-high) — resolve 2269 against 573/1275; one of the two designs must go.**
   Either delete the claim at `kernel-interface.md:2269` ("The sweep's `Ping` is never sent …")
   and keep 1275's "a successor that is idle with no armed timer is sent an interrupt and a ping
   message" as written; or add at 1275/1335: "The first core of every node that is starting, live
   or sealing arms a due event of its timer queue at every period of its recovery reserve and at
   every `SWEEP_NS`, so a node of the contract is never idle with nothing armed; with that arming
   the sweep's `Ping` is never sent (the interrupt alone wakes the successor) and the sentences
   named at line 2269 — the `Ping` row (921), the words row (938), the failure-machinery sentence
   (942), the credit sentence (954), the ten-kinds list (962), the last clause of the sweep
   (1275) and `NodeMessage::Ping = 9` (1761) — are removed."
5. **Finding 5 (medium) — four text fixes plus a fairness rule.** At 653, replace "Rule 2 already
   asks every caller to handle `again`." with "Rule 4 and the Errors table (line 1859) already
   tell every caller to repeat a call that returned `again`." At 1865, replace the `again` row
   with: "| `again` | The call did nothing — except the word of its notify, for `signal` and
   `notify_bind` (line 650) — or a bounded step was done; repeat the call |". In the `abi/`
   changes list (1719–1768), add `Again` to the rows of `Call`, `Send`, `Signal`, `NotifyBind`,
   `CapDerive`, `CapMove`, `UntypedRetype`, `IrqClaim`, `MemoryTake`, `IoportsIssue`,
   `IoSpaceMap`, `ThreadConfigure`, `TaskAttach` and `SchedConfigure`, each with "under variant
   L2 only, with nothing changed (D-134)", and replace "**Errors.** None new." (1743) with
   "**Errors.** `Again` added to the fourteen calls of [A node of several cores](#a-node-of-several-cores)
   under variant L2 (D-134); none other." At 656, after "What it does not prove", add: "A caller
   that has been told `again` twice for the same call may, on its next attempt, release every
   lock it holds and take the lock that failed its try first, waiting for it as for any lock
   taken in order with nothing held, and then take the locks it needs in the order; the check of
   the second round is unchanged. (One word per thread: the count of `again` for the current
   call.)"
6. **Finding 6 (medium) — suspend the membership clocks during a debugger stop.** Append to the
   debugger paragraph at `kernel-interface.md:1636`: "While the release word is raised,
   `CORE_ANSWER_NS`, `FENCE_NS` and `SEAL_NS` are not measured and no node accuses itself: a wait
   or a fence step that finds the release word raised suspends and resumes when it is cleared
   (development images only, which is where the release word exists)."
7. **Finding 3 (medium) — one sentence on the watermark, plus a flag.** Replace the second
   sentence of `kernel-interface.md:162` with: "When the last one is destroyed the watermark is
   *ready to return* (a word of the untyped's slot, set at that destruction); it returns to the
   start — and with it the clean mark (line 166) — at the first `untyped_retype` that finds every
   other core of the node has ended the kernel event it was in at that destruction, its heartbeat
   moved or idle (D-134, line 654); until then the memory is not usable again and `untyped_retype`
   on the untyped returns `again`."
8. **Finding 4 (medium) — the fourth per-core exception.** Extend the exceptions at
   `kernel-interface.md:631` with: "and the request of another core, which the core whose
   acknowledgement completes it (line 327) empties and frees — the request carries a state word,
   *in use* written by its starting core and *done* written by the completing core by
   compare-and-swap, so a new request is started only after the old one reads *done*."
9. **Finding 8 (low-medium) — weaken the "so" clause.** At `kernel-interface.md:1019`, replace
   "so the IOAPIC never points at a remapping entry that a unit's cache may still hold stale" with
   "so the IOAPIC never points at a remapping entry whose interrupt-entry cache the units that
   answered have not invalidated; a unit found failed may still hold a stale entry for the
   handle, one more cost of its failure, and the call says so with `busy`".
10. **Finding 10 (low) — the `again` of the memory calls under L2.** Replace the sentence at
    `kernel-interface.md:864` with: "`memory_take` and `memory_split` never return `again` under
    L1, and under L2 only with nothing changed, when a try of a segment of the derivation list
    fails; `memory_give` returns `again`, with nothing changed, when the request of the caller's
    core is in use or, under L2, when a try of a segment of the derivation list fails."
11. **Citations (low) — one edition per specification, the current one.** Extend the
    one-edition rule of `kernel-interface.md:78` from the Intel SDM to every cited
    specification, and update: PSCI to a single current edition (today DEN0022F.b, v1.3) at 1200
    and 1204, re-checking the section numbers in it; VT-d to the current edition (today Rev 5.20,
    order D51397-019) at 1008, 1017 and 2268, re-reading §6.2.2.1, §11.4.2, §6.5.2.7 and §5.1.5.1
    in it; Arm DDI 0487 to the current edition (today at least L.b) at 2163 and the TLBI
    citations; the Intel SDM stays at 325462-093, which is the current edition today.

Nothing else in the review was found wrong: its section 11 (the no-deadlock walk, the
thread-waits-on-an-object rule, the NMI/start walk, the domain-number split, the operand-table
arithmetic, the wait states and bounds, and the `security.md:108` check) holds under my own
re-walk, and its "what I did not check" list is honest.
