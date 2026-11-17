# Verification of Hydrogen's contract review 12 (pass 19)

I verify the eleven findings of [the review under test](2026-11-17-contract-review-12-gemini-hydrogen.md) against
[the contract](../architecture/kernel-interface.md) at branch `main`, head `05d4ed6` (17 November 2026, 2307 lines), and
against [the decisions](../decisions/README.md), D-128 to D-137. I opened every quote at the line the review names and
say whether it is exact. I replay every scenario as a sequence of single reads and writes, and for findings 1 and 2 I
write the sequence out step by step. I judge the correction, and where it is wrong or incomplete I write the right one as
exact text. For finding 8 I recount each number the review changes, lock by lock, from the rules. For finding 11 I say
what I could open today and what I could not. I close with what the review missed in the same passages, and with one list
of corrections in order of severity.

Nothing in any repository was changed for this verification, and no commit was made.

**A note on editions and documents.** I could not open the Intel SDM (order 325462-093), the VT-d specification (order
D51397-019, revision 5.20) or Arm DDI 0487 M.d from this environment; neither could I read the PSCI specification. Where
the review rests on those documents I say "not opened" and judge only what the contract says about them. Everywhere else
the evidence is the text of the contract at head `05d4ed6`, which I read in full.

---

## Finding 1 — CRITICAL: the ticket-lock deadlock in the quiet word

### The quotes, at their lines

All four quotations are from `kernel-interface.md:666` (three of them) and `kernel-interface.md:668` (one). All are
**exact**, character for character, including the parenthesis "(D-137: the earlier text said it cleared the word, which a
ticket lock with a waiter behind the holder cannot be)". Line 666 is one bullet, so the three quotations from it stand
side by side in the same paragraph, which is what makes the finding readable as a contradiction between one sentence and
another in the same bullet.

- The escalation, exact: "It releases every lock it holds, takes the node's **quiet word** (one word of the node block: a
  ticket lock, its next ticket and its serving ticket, a ticket taken by an atomic add so that the cores that wait for it
  are served in the order they came; held while the two differ), raises the node's kernel epoch by one by an atomic add,
  orders both before its next load (an atomic read-modify-write is such an operation on x86-64; `DMB ISH` after it on
  ARM64; `fence rw,rw` on RISC-V), waits until the entry word of every other core of the node reads 0 or at least the new
  epoch, runs the call alone, taking its locks in the order (no try can fail and no link can change, since no other core is
  in a kernel event), and releases the word by advancing its serving ticket, a release store".
- The entry, exact: "If another core holds the word, the core writes its entry word 0, waits until the word is released
  and enters again, and it takes no lock before." This sentence sits in the paragraph that begins "**Every core reads the
  quiet word when it enters the kernel** for a call or an event": it is a rule for an entry, and its own words say so
  ("enters again").
- The entry word, exact: "holds the kernel epoch the core read when it entered its current kernel event, and 0 outside one
  and while it waits for the quiet word: one ordered write to the core's own line at each entry, one release store of 0 at
  each exit".
- `668`, exact: "**The quiet word adds no cycle (D-135):** a core waits for it only at the entry of an event, before it
  takes any lock, its entry word 0; the holder takes it only once it has released every lock, waits only for the other
  cores' current events, none of which waits for it, and then takes its locks in the order with no other core in an
  event".

Two more sentences of line 666 matter to the replay and the review does not quote them, so I set them here: the fourth
quote from 666 that it does give, "and each escalation ahead of it in the queue, at most *N* − 1, runs alone in its
one-core bound", is exact and is the contract's own admission that up to *N* − 1 cores **wait for the word from inside
their events**.

### The replay, step by step

Cores *b* and *c* of one node, kernel epoch *e*, both entry words 0 (both outside the kernel), quiet word's next ticket
and serving ticket both 0. A delivery or a call has put *b* in an event and a call has put *c* in an event; each thread's
count of consecutive `again` from the rule of tries already stands at 2, so the next `again` of either call escalates.

1. *b* enters its event: writes `b.entry := e` (ordered, `XCHG` on x86-64). Reads the quiet word: next 0, serving 0, the
   two are equal, so the word is free, and *b* enters.
2. *c* enters its event: writes `c.entry := e`. Reads the quiet word: still free. *c* enters.
3. *b* runs its third call and reaches the point where it would return `again`; its count is 2, so it escalates. *c*
   does the same, concurrently.
4. *b* releases every lock it holds. *c* releases every lock it holds. Neither writes its entry word: the only rule that
   writes 0 outside an exit is the rule of the entry, and neither is at an entry.
5. *b* makes an atomic add on next: it receives ticket *t*, next becomes *t* + 1, and because serving is *t*, *b* is
   served and holds the word.
6. *c* makes an atomic add on next: it receives ticket *t* + 1, next becomes *t* + 2, serving is still *t*, so *c* waits
   for serving to reach *t* + 1. The text calls this "the cores that wait for it are served in the order they came"; *c*
   is now one of the at most *N* − 1 the bound of 666 counts.
7. *b* makes an atomic add on the node's kernel epoch: *e* becomes *e* + 1.
8. *b* reads `c.entry`. *c* wrote *e* at step 2 and has written nothing since, so *b* reads *e*. The condition is "0 or at
   least the new epoch": *e* is neither. *b* waits.
9. *c* reads serving: still *t*. *c* waits. No rule has told *c* to write 0, and no rule can: the sentence that writes 0
   speaks of the core entering the kernel, and *c* entered at step 2 and is inside its event. **The guarantee breaks here.**
10. *b* reads `c.entry` again: *e*. *b* spins. *c* reads serving: *t*. *c* spins.
11. The cycle is closed and neither core can leave it: only *b* can advance serving ("releases the word by advancing its
    serving ticket"), and it advances only after step 8 passes, which needs *c* to write 0 or to reach *e* + 1, which
    only *c*'s **exit** can do ("one release store of 0 at each exit"), and its exit needs the word.
12. Both waits outlast `CORE_ANSWER_NS`, which is "a failure of the node, as a lock wait is" (666). The node accuses
    itself, evidence self, reason 9 (line 698: "the node accuses itself (evidence self), and the whole node is fenced and
    reclaimed"). No user error, no device, no debugger: a healthy node kills itself.

The report's steps 1 to 5 and 7 are the same sequence and are right. Its step 6 — "*c* also raised `kernel_epoch`
immediately after taking its ticket" — is not a hypothetical: the text says the escalator "takes the node's quiet
word ..., raises the node's kernel epoch by one by an atomic add" before it waits, so an escalator raises the epoch while
it is queued. But that does **not** make the deadlock worse, as the report says: *b* computed its target as *e* + 1 at
step 7 and never reads the epoch again, so *c*'s raise to *e* + 2 changes nothing in the cycle. That raise is a second,
independent defect, which I set out below because it decides the shape of the right correction.

### The sentence that stops the guarantee

`668`: "a core waits for it only at the entry of an event, before it takes any lock, its entry word 0". The first clause
is false under D-137's own ticket lock — up to *N* − 1 escalators wait for it from inside their events, after taking and
releasing locks — and the second and third clauses are false with it: an escalator waits **inside** an event, with its
entry word still the epoch it read at its entry. The whole proof at 668 rests on that sentence ("the holder ... waits
only for the other cores' current events, none of which waits for it"), and the escalator waiting for the word is exactly
a current event that waits for the holder.

### Verdict: confirmed

The review's finding is right about the mechanism, right about the line, right about the class of failure, and its
correction 1 is the fix the contract needs. Two of its statements are weaker than the truth and one is wrong:

- Weaker: the review treats the entry-word definition ("and 0 outside one and while it waits for the quiet word") as a
  quotation that supports the contradiction. It is more than support: it is the contract asserting the state that no rule
  produces. That is the defect in its cleanest form — an invariant stated as a fact of the word's layout, whose write is
  named only for the entry and the exit.
- Weaker: the review says 668 "directly contradicts line 666's ticket queue". It does, and the contradiction is sharper
  than it says: 666's own bound sentence counts "each escalation ahead of it in the queue, at most *N* − 1", so the
  contract states the queued escalators in one sentence and denies that anything but an entry waits in the next.
- Wrong: correction 2's second half ("write its own `entry_word = new_epoch` with store-load ordering"). A holder's own
  entry word is read by no rule: the check is over "every other core of the node", and an entering core that finds the
  word held writes 0 and waits whatever the holder's word says. The store changes no result and adds a rule to every
  escalation for nothing.

### The correction, judged

**Does correction 1 close the hole?** Yes, and it is the whole of the first fix, provided the write is ordered and
placed as follows: after the escalator has released every lock, and before it reads the word, it writes its entry word 0
with the same operation the entry uses, because on x86-64 "the Intel-64 memory-ordering model allows a load to be
reordered with an earlier store to a different location" — the very sentence 666 uses to justify `XCHG` at the entry. A plain
store can be delayed past the escalator's own read of the word, so the holder may still read *e_old* while the escalator
already waits. With
that write in place, step 8 of the replay reads 0 and *b* runs alone; step 9's "no rule tells *c* to write 0" becomes a
rule.

**What correction 2 adds, and why it is unnecessary.** Correction 2 asks the holder to raise the epoch only once it is
served, and to write `entry_word = new_epoch` into its own word. Neither is needed, and the first rests on a reading of
the ticket lock that the text does not support. The word reads **held** exactly while some core holds it or queues for it,
because every taker adds one to next before its own ticket: a holder's ticket equals serving and next is one beyond it,
so next > serving. It reads **free** only when next equals serving, that is, when no core holds and none queues. So no
core can enter the kernel while a holder runs: an entering core that finds the word held writes 0 and waits (666). A
core that entered *before* the holder took the word wrote an epoch below the holder's target and the holder waits for its
exit; a core that enters *after* the holder releases reads an epoch at or above the target, and the next escalator's raise
is above that. Writing `new_epoch` into the holder's own word is read by no rule at all: the check is over "every other
core of the node", and a core that finds the word held never reads the holder's word to decide anything.

**One thing neither correction covers, which the fix brings into the open.** An escalator with entry word 0 is
indistinguishable, to the *other* rule that reads entry words, from a core that has ended its event. Line 666 says the
entry word "is what both rules read to know that every other core has ended the kernel event it was in (an escalation,
and the return of a watermark above)". A destroying core that raised its own epoch while the escalator was suspended sees
the escalator's 0 and concludes it has ended its event — which is true in the sense that matters for memory (it holds no
lock, it has changed nothing, it will not write until it holds the word) but false for the call it is in the middle of.
Its own premise, "runs the call alone, taking its locks in the order (no try can fail and no link can change, since no
other core is in a kernel event)", then does not hold: a watermark may have been returned, and a link the call read before
it escalated may now differ. So the escalator must, after it is served and before it takes its locks, read the epoch
once; if the epoch is not the one it read at its entry, it releases the word and returns `again` with nothing changed. One
read of a word "written only at an escalation and at the last destruction of an untyped", at an event that happens at most
once per three calls of a thread. Without this clause the fix trades a deadlock for a stale read.

**What the correction falsifies, and what it costs.** The entry's own rule keeps its 0 and needs no change. 668 must lose
its sentence, because an escalator waits in the middle of an event after taking and releasing locks. The paragraph of
666 on "the four orders" gains one case, the same shape as its case (3), where a core reads the word held and writes 0 —
an escalator that arrives after the holder is that case with the lock releasing earlier. The cost is one ordered store and
(at most) one read, per escalation only: under L1 no call escalates, so nothing is paid there; on the common path of L2
nothing is paid at all, and nothing is paid on a memory access. This is the owners' principle kept to the letter: the
guarantee is bought at a rare event, with two accesses, and the wait it buys is one the contract already charged to every
kernel entry.

### The right text

In `kernel-interface.md:666`, replace

> takes the node's **quiet word** (one word of the node block: a ticket lock, its next ticket and its serving ticket, a
> ticket taken by an atomic add so that the cores that wait for it are served in the order they came; held while the two
> differ), raises the node's kernel epoch by one by an atomic add, orders both before its next load

with

> writes its entry word 0 by the operation that orders a store before the next load (an `XCHG` on x86-64, the store then
> `DMB ISH` on ARM64, the store then `fence rw,rw` on RISC-V), after it has released every lock and before it reads the
> word below, so that a core that finds it waiting reads 0; takes the node's **quiet word** (one word of the node block: a
> ticket lock, its next ticket and its serving ticket, a ticket taken by an atomic add so that the cores that wait for it
> are served in the order they came; held while the two differ), raises the node's kernel epoch by one by an atomic add,
> orders that store and the ticket before its next load

In the same sentence, replace

> runs the call alone, taking its locks in the order (no try can fail and no link can change, since no other core is in a
> kernel event)

with

> reads the epoch once more and, if it differs from the one it read at its entry, releases the word by advancing its
> serving ticket and returns `again` with nothing changed (a watermark was returned while it waited); otherwise it runs the
> call alone, taking its locks in the order (no try can fail and no link can change, since no other core is in a kernel
> event)

In `kernel-interface.md:668`, replace

> **The quiet word adds no cycle (D-135):** a core waits for it only at the entry of an event, before it takes any lock,
> its entry word 0; the holder takes it only once it has released every lock, waits only for the other cores' current
> events, none of which waits for it, and then takes its locks in the order with no other core in an event

with

> **The quiet word adds no cycle (D-135, D-138):** a core waits for it in one of two places, both outside every lock: at
> the entry of an event, before it takes any lock, and at an escalation, after it has released every lock and changed
> nothing. In both places it writes its entry word 0 before it waits, so the holder, which waits for the other cores'
> current events, never waits for a core that waits for it: an entering core is not in an event, and an escalator holds no
> lock. The escalator is suspended inside its event, not out of it, and reads the epoch again once it is served, as an
> entering core's ordered write is what the other rule reads.

---

## Finding 2 — CRITICAL: the marks a thread loses when it changes task

### The quotes, at their lines

The review quotes lines 1114, 1116, 1120, 1131, 1133 and 1136. All six are **exact**. I opened each one and compared the
quoted words with the line:

- `1114` gives "**The effective marks of a thread never lose a bit while the thread lives.** Every rule below keeps this
  invariant." Exact.
- `1116` is one long paragraph; the review's quotation of it is exact and covers the two decisive clauses: "the task read
  after the own word is written" and "`task_attach` writes the thread's new task first, then ORs into the new task the
  thread's own word and the marks of the task it leaves". I add the clause that closes the paragraph, because the review's
  verdict turns on it: "So when a delivery races an attach on another core, either the attach reads the own word with the
  new bits, or the delivery reads the new task and ORs into it: no bit a delivery stamps is lost by the thread or by the
  task it ends in." Also in 1116, and not quoted: "The own word of an attached thread is read by no rule, so ORing into it
  changes no result."
- `1120` exact, including "Detaching sets the thread's own marks word to the marks of the task it leaves."
- `1131` exact ("marks = the effective marks of the sender | the added marks of the message (below)").
- `1133` exact ("The values are taken at delivery, not when the call was made: a caller marked while it waited in a queue
  sends its new marks").
- `1136` exact ("If at a delivery at least one capability is moved or derived (the transfer was not dropped), and the
  sender is not attached to a mark-aware task, the sender's effective marks become themselves | the receiver's effective
  marks as they were before this delivery").

One more sentence of 1120 matters and the review does not use it: "Otherwise, with *m* the effective marks of the thread,
the thread leaves its old task if it had one, joins the new one, and the new task's marks become marks \| *m*." That is the
effect as a single step, and the trace below is where the single step hides two.

### The replay, step by step

The words: `T.task` is the task a thread is attached to; `T.own` is its own marks word; a thread's effective marks are
`T.task.marks` if `T.task` is not 0 and `T.own` otherwise (1114); a delivery reads the effective marks "at delivery" (1133)
and ORs into "the thread's own word always, and into its task's word too if the thread is attached to one, the task read
after the own word is written" (1116).

**Race A, a thread re-attached from Task1 to Task2.** Before: `Task1.marks = M ≠ 0`, `T.own = 0`, `Task2.marks = 0`, so
*T*'s effective marks are *M*. Core A runs `task_attach(T, Task2)`; core B delivers a message whose sender is *T*.

1. A: READ `T.task` = Task1.
2. A: WRITE `T.task := Task2`. This is the order 1116 mandates ("writes the thread's new task first").
3. B: READ `T.task` = Task2; READ `Task2.marks` = 0. The delivery stamps the message with marks 0 (1131) instead of *M*
   (1133: "taken at delivery"). B ORs its bits into `T.own` and into `Task2.marks`.
4. A: READ `Task1.marks` = M; OR `Task2.marks := M`.
5. From step 4 *T*'s effective marks are *M* again. Between step 2 and step 4 every reader of *T*'s effective marks reads
   0, and the message at step 3 carried 0 out of a marked task: rule 8's channel, opened by the very rule meant to keep it
   shut. **The guarantee breaks at step 2.**

The review's step list for this race is the same and is right. Its sentence "Core B reads `T.task == Task2` and
`Task2.marks == 0`" is right; 1116's own argument does not cover it, because that argument is about "no bit a delivery
**stamps**", and *M* was not stamped by this delivery — it was in the old task's word.

**Race B, a thread detached, with a sibling receiving in the same task.** Before: `T.task = Task1`, `T.own = 0`,
`Task1.marks = M`; sibling `T2` is attached to Task1 too. Core A runs `task_attach(T, 0)`; core B delivers a marked
message to *T2*.

1. A: READ `T.task` = Task1; READ `Task1.marks` = M.
2. B: delivery to *T2*: READ `Task1.marks` = M; OR `Task1.marks := M | M'` (lock-free, as 1116 requires).
3. A: WRITE `T.own := M` (1120: "Detaching sets the thread's own marks word to the marks of the task it leaves"). The value
   is the one read at step 1.
4. A: WRITE `T.task := 0`.
5. *T*'s effective marks are now `T.own = M`, missing *M'*, which they held at step 1. **The guarantee breaks at step 4**,
   and step 3 is where the bit was already unrepresented.

The review's version of this race is the same, with the roles of *T* and *T2* swapped in its wording and the same result,
and its statement that reading `Task1.marks` *before* clearing `T.task` still fails is right. There is a third variant,
which it does not give and which shows that no order helps: a delivery that ORs into **T's own word** between A's read at
step 1 and A's store at step 3 has its bit overwritten by the store, even though 1116 calls the detach's write "an OR too"
— a store of a value read earlier is not an OR of the word as it is.

**Why no order of the two writes closes it.** The loss does not come from the order of A's writes but from the move: the
effective marks change from one word to another, and there is no instant at which both words hold every bit the thread
had. Any order leaves a window in which a delivery takes a bit into the word the thread is leaving (or into the word it is
entering, before the copy). The only ways out are to stop deliveries while the thread crosses, or to give deliveries a
lock on the marks word — which is what D-137 removed to keep deliveries free of locks.

### Verdict: confirmed

Both races are real, both follow from the text as written, and the invariant they break is stated in the contract's own
words at 1114. The finding's mechanism, its two scenarios and its conclusion are right. The finding is weaker than it
could be in one place: it says 1116 "only considers bits newly stamped into `thread.own_word` during a delivery concurrent
with `task_attach`". That is precise, and the precise statement is stronger: 1116's argument covers only the crossing of
one thread's own word with one delivery's stamp, and is silent about the bits already in the old task's word, about a
sibling's delivery into the old task, and about the loss that happens on the *detach* side, where the thread's own word is
overwritten.

### The correction, judged

The review offers a menu: "Option A", then "Specifically, if deliveries take the sender/receiver `task` lock ... OR if
`task_attach` transitions `T` via `task_attach` only when `T` is suspended and not waiting", then a "cleanest fix" that
makes deliveries take the task lock and reintroduce two locks per message, then a last alternative that writes the marks
across before the switch, waits out every other core's current kernel event, and re-reads.

- The menu is not a correction: three of its branches close the hole only by giving it up somewhere else, and it does not
  say which one it wants. A review that leaves the owners to choose has not finished the finding.
- "Take `old_task`'s and `new_task`'s locks in `task_attach`, and make deliveries take `task` lock when ORing
  `task.marks`" is exact in mechanism and wrong in cost: it puts a lock on **every** message, on a path that carries
  marks on every delivery, to fix a race that happens only when a thread changes task. Against the owners' principle — a
  guarantee is paid at a failure or a rare event, never on every memory access — this is the one branch that must not be
  taken, and it is the branch the review calls "the cleanest".
- The last alternative has the right shape and the right price ("costs 0 on deliveries and adds an `entry_word` wait only
  on `task_attach` when leaving a non-null task"), but it names a mechanism that does not exist for a call: waiting out
  "every other core's current kernel event" is what the quiet word does, and only an escalating call may take the quiet
  word (666). So the alternative needs one new rule, which is the correction below.

**Does it close the hole?** Only the last branch, and only with the rule written down: `task_attach` that moves a thread
takes the quiet word first, then moves the marks, then writes the thread's task word, then releases the word. While the
word is held no core is in an event and none can enter one, and a delivery is part of an event, so no delivery can read
the marks or OR into either word while the thread crosses. Both races disappear at their first step.

**What it falsifies, and what it costs.** It falsifies 1116's closing sentence (a bit *can* be lost, by the move and not
by the stamp) and its "The own word of an attached thread is read by no rule" stays true but stops being an argument. It
leaves 1131, 1133 and 1136 alone: deliveries still read plain words and still OR without a lock. It costs one wait for
the quiet word (at most *E* + (*N* − 1) × *B*1max, 666) plus the call, on `task_attach` only, and only when the thread
actually moves; nothing at a delivery, nothing on the common path, nothing under L1, where a node's events run one at a
time under its lock. A cheaper shape exists and is worse: making the effective marks the union of the task's word and the
thread's own word would keep every bit without any wait, but it changes 1114, 1131 and 1136 and it would let a delivery
outlive the sticky rule that makes marks survive a thread's death, so it is a design change for the owners, not a
correction.

### The right text

In `kernel-interface.md:1116`, replace

> and `task_attach` writes the thread's new task first, then ORs into the new task the thread's own word and the marks of
> the task it leaves, each of these an operation ordered with the next (an atomic OR, a read after a store ordered as the
> entry word is). So when a delivery races an attach on another core, either the attach reads the own word with the new
> bits, or the delivery reads the new task and ORs into it: no bit a delivery stamps is lost by the thread or by the task
> it ends in.

with

> and `task_attach` that moves a thread from one task to another, or to none, takes the node's quiet word first, as an
> escalating call does ([A node of several cores](#a-node-of-several-cores)): it writes its entry word 0, waits for the
> word, and only then reads the marks of the task the thread leaves, ORs them into the new task's word (for a detach, ORs
> them into the thread's own word, which already holds every bit of them), writes the thread's task word, and releases the
> word. While it holds the word no core is inside a kernel event and no core can enter one, and a delivery is part of an
> event and not a call of its own (664), so no delivery reads or writes either marks word
> while the thread crosses, and no bit the thread had is left behind in the word it leaves. Under L1 no quiet word exists
> and none is needed: the events of a node run one at a time under the node lock. An attach that changes nothing (the
> thread is already attached to that task, or already attached to none) takes no word, and the detach that the destruction
> of a task makes needs none either: it ORs nothing away, since the thread keeps the marks in its own word.

In `kernel-interface.md:1120`, replace

> Detaching sets the thread's own marks word to the marks of the task it leaves.

with

> Detaching ORs the marks of the task it leaves into the thread's own marks word, under the quiet word ([Tasks and
> marks](#tasks-and-marks)).

---

## Finding 3 — HIGH: the destruction of an iospace on a failed unit

### The quotes, at their lines

Every quotation is **exact**: 374 (the whole passage, with its ellipsis where the review cuts), 373 ("at the answer done,
the caller's gate writes the attach word 0 and the identifier word *free*, unclaimed, and lowers the root's count of
devices, and the device leaves the iospace's header"), 1046 ("*done* completes the entry ... *failed* empties the record
with its counts kept, or ends the waiting call with `busy`"), 380 (the table-pages clause) and 368 ("the device is
already attached to this iospace (success, nothing changes)"). The one sentence the review leans on that it does not quote
in full is 377, which is exact as I read it: the holder "answers *failed* to every request it holds for the unit and to
every later one".

The state machine the replay needs, at its lines: `359` ("*pinned* (root) or *detached* (root) → 0, by the gate of the
owner, which lowers *n* in the same gate call and writes the identifier word *free*, unclaimed; never from *attached*");
`357` ("*pinned* (root) → *attached* (root), by the gate of the unit's role holder, which serves an attach (operation 1)
only by this compare-and-swap"); `364` ("the unit has failed (`busy` ...)"); `367` ("the device is attached to another
iospace, or is being detached, its attach word not 0 (`busy` ...)"); `1038` ("once the invalidation is complete, the
holder's gate writes the attach word *detached* if it reads *attached*").

### The replay

1. A device is attached: `attach_word = attached(iso.root)`, the identifier word taken by the node, the root's count *n*
   = 1, the device in `iso`'s header (372).
2. The unit fails. The holder writes the *failed* bit in the role word and "answers *failed* to every request it holds for
   the unit and to every later one" (377).
3. `cap_delete` reaches the root capability of `iso`. The iospace becomes dying, and 374 says its destruction "first
   detaches each of its devices (most recently attached first)": the step starts a detach as a unit request and returns
   `again`.
4. The request reaches the failed holder: *failed* (377).
5. At the answer (1046), *failed* "ends the waiting call with `busy`". There is no waiting call — the requester is the
   removal step — and 1046 gives no other branch for it. Nothing writes the header.
6. Only the *done* answer removes the device: 373's "the device leaves the iospace's header" is inside its "at the answer
   done". The attach word stays *attached* and the count stays above 0, as 374's own last sentence says.
7. The next call of the removal finds the same device at the head of the same header (most recently attached first, and it
   never left) and starts the same request. Steps 3 to 7 repeat.
8. The call returns `again` for ever, one step per call. 374 cannot reach its second half ("then empties each record of its
   list") and cannot remove the root, because "the root and the tables turn back into *data* only once the root's count of
   devices is 0 (G2)". A `cap_delete` that never returns success is a removal that never ends, and rule 4 tells the caller
   to call again.

### Verdict: confirmed in part

- **The infinite `again` loop: confirmed.** The chain 374 → 377 → 1046 → 373 is exactly as the review states, and 1046's
  silence about the header on a *failed* answer is the hole. The review is also right that a `cap_delete` on the
  capability space or the untyped above such an iospace never finishes.
- **The "false `ok` on a failed `op 1`": refuted.** The review's step says a second `iospace_attach` "somehow ran before
  failure, or on a unit whose failure isn't checked before 368 if ever re-ordered". There is no such order: the failed
  unit is the **first** state check (364, "first, since it makes every other state check moot"), so every attach on a
  failed unit is `busy` before anything else; and a device left *pinned* by a failed attach is caught by 367, whose
  condition is "its attach word not 0" and whose answer is `busy`. So no second attach returns success. The review's own
  quotation of 367 contains the condition that refutes it.
- **The residue it is right about: confirmed.** 380's "since the attach word stays *attached*" is false for a device whose
  operation 1 answered *failed*: 357 moves *pinned* → *attached* only when the holder serves the attach, so a failed
  attach leaves the word *pinned*. The conclusion 380 draws (*n* > 0, the pages keep their class) still holds, but its
  stated reason does not, and a reader who trusts the reason will think a failed attach cannot leave a device counted.

### The correction, judged

**Does it close the hole? No.** Correction 1 — remove the device entry from the header at a *failed* answer without
lowering *n* or clearing the identifier word — is the right first half and it lets the step walk past its devices. It does
not let the step **end**: *n* stays above 0 by the correction's own design, and 374 says the root turns back into *data*
only from class 48 + 0. So the step reaches the root, cannot turn it into data, and returns `again` for ever one step
later. The loop the review found is not removed; it is moved. What the review missed is that 380 already says what must
happen instead: the pages "keep their class ... when the iospace is destroyed, so they are never reused before the machine
restarts". The two sentences cannot both hold for *n* > 0, and 380 is the one that says what the machine can afford, so
374 needs the exception in its own words.

**Correction 2 is aimed at a state the contract already refuses.** It asks that 367–368 "check `attach_word ==
*attached*(root)` rather than the header alone before returning success in `368`". 367 already checks the *word* ("its
attach word not 0"), not the header; what needs fixing is that 367's condition makes 368 unreachable (see Finding 4 and
what the review missed, below). Its other half — "specify that on *failed* `op 1`, `attach_word` stays *pinned*" — is
right, but the place to write it is 380's parenthesis, one word long.

**What it costs.** The header removal at a failed answer is one gate write, at an event that happens once per device of a
failed unit, for the rest of the boot. Nothing on the common path, nothing on a map or an attach of a healthy unit. The
exception at 374 costs nothing at all: it is a sentence about a state the machine reaches only after a unit has failed.
This matches 379's pattern, which the contract already applies to the counts of a failed unit's records: keep what cannot
be undone, and keep it out of reuse until the machine restarts.

### The right text

In `kernel-interface.md:374`, replace

> The root and the tables turn back into *data* only once the root's count of devices is 0 (G2); a detach answered *failed*
> leaves the attach word *attached* and the count above 0 (below).

with

> The root and the tables turn back into *data* only once the root's count of devices is 0 (G2), and a detach answered
> *failed* leaves the attach word as it was and the count above 0 (below). **A device of a unit that has failed is
> detached for the purpose of this step at a *failed* answer (D-138):** the answer removes the device entry from the
> iospace's header, and so from the node's list of its devices for that unit (below), counts as a unit of the step, leaves
> the attach word and the identifier word as they are and does not lower the count. Such an iospace's destruction then
> ends with the count above 0: the root capability is removed, and its pages and tables keep their class and are never
> reused before the machine restarts (below). The removal returns success, since nothing more can be done for a unit that
> stays failed until the machine restarts.

In `kernel-interface.md:380`, replace

> and its root *iospace root with n devices attached*, *n* > 0, since the attach word stays *attached*: D-137) when the
> iospace is destroyed, so they are never reused before the machine restarts;

with

> and its root *iospace root with n devices attached*, *n* > 0, since the attach word stays *attached*, or *pinned* if
> the device's attach was never served, D-137) when the iospace is destroyed, so they are never reused before the machine
> restarts;

---

## Finding 4 — HIGH: the answers of attach and detach racing on the attach word

### The quotes, at their lines

All **exact**: 367–368 (the two list items), 372–373 (the attach's gate call and the detach's answer), 359 (the transition
list of the attach word), 1037 (row 1), 1038 (row 2) and 1042 ("A request whose operands fail these checks is not written
to the unit: the holder traces it (code 11 ...) and answers it done, so the requester's entry ends"). I add two sentences
the review does not quote and its two races turn on: `363` ("With an iospace, the state is judged in this order") — which
shows that 364 to 371 are the checks of the **attach only**, so the iospace-0 detach path of 373 has no state check at
all; and `1038`'s "a detach is idempotent", which is what lets the holder serve a second detach of a device it has already
detached.

### Race 1, a second attach while the first is in flight: refuted

The review's steps are: 372 writes *pinned* and puts the device in the header, then waits; a second `iospace_attach` "367
passes (*\"attached to another iospace\"* is false because it is in `iso`'s header!)" and 368 returns success.

367's condition is not "the device is in the header": it is "its attach word not 0", and the review quotes those words. A
device whose operation 1 is in flight has `attach_word = pinned(iso.root)`, which is not 0, so 367 fires and the call is
`busy` — with the contract's own instruction, "detach it first, or wait for the detach's answer". The same applies while
a detach is in flight: 373 has the holder write the word *detached* before the answer, and *detached* is not 0 either, so
367 fires. There is no state in which a device is in flight and its word is 0.

Worse for the finding, the ordering makes 368 **unreachable**: 367's condition ("its attach word not 0") is true of every
device that 368 could catch ("already attached to this iospace"), because an attached device's word is
`attached(iso.root)`. So no `iospace_attach` ever returns success from 368; a repeat attach to the same iospace is
`busy`. That is a defect of its own — a dead sentence in a list of ordered checks, and a repeat call that cannot be
idempotent — but it is the opposite of the report's: it makes a premature `ok` impossible rather than likely.

### Race 2, two detaches and a stale answer: confirmed

1. Thread `T1` calls `iospace_attach(iommu, 0, dev)` for a device attached to `iso1`. The iospace-0 path has no state
   check (363's list is "with an iospace"; 373 states the effects directly), so **two** such calls can both run.
2. Each sends operation 2 to the holder. The holder serves both — "a detach is idempotent" (1038) — and answers *done*.
3. `T1`'s answer arrives first: the gate writes `attach_word = 0`, writes the identifier word *free*, lowers `iso1`'s
   count, and the device leaves `iso1`'s header (373).
4. `T3` calls `iospace_attach(iommu, iso2, dev)`. Every check passes: the word is 0, so 367 does not fire. 372 writes the
   identifier word taken by the node, `attach_word = pinned(iso2.root)`, raises `iso2`'s count, puts the device in
   `iso2`'s header, and sends operation 1 (`A1`).
5. The second detach's answer (`D2`) arrives. The holder, when it served it, read the word as *pinned*, not *attached*,
   so it wrote nothing and traced code 11 and answered *done* (1038, 1042). At the answer the requester's gate now
   performs 373's write — and 359's transition list allows "**pinned (root)** or *detached* (root) → 0, by the gate of the
   owner, which lowers *n* in the same gate call and writes the identifier word *free*, unclaimed". So the gate clears
   `iso2`'s pin to 0, writes the identifier word free, lowers `iso2`'s count to 0 and removes the device from `iso2`'s
   header.
6. Consequences, any one of which is a containment failure: `A1`'s pin is gone, so if `A1` has not yet been served it
   fails 1037's "moves from *pinned* to *attached*", is traced and answered *done* (1042), and `T3`'s call returns `ok`
   with no context entry and a device it believes attached; the identifier word is free while `A1` may still be in
   flight, so the next claim of that identifier can put **another device** on the same identifier; and `iso2`'s count is
   0 while a device's context entry may name `iso2`'s root, so `iso2`'s root reaches class 48 + 0 and can "turn back into
   *data*" (362, G2) under a device that still translates through it.

The review's sequence is this one, step for step, and it is right, including its aside that 359 "explicitly allows
`*pinned*(root) → 0`". This is the more serious of its two races and it is the one the review puts second.

### Verdict: confirmed in part

One race refuted, one confirmed and correctly analysed. The finding's headline — "`iospace_attach` / `iospace_detach` /
destruction race on `attach_word` and `iospace` header" — is right, and its diagnosis of the shared root cause is nearly
right: it says 372 "adds `dev` to `iso`'s header *before* waiting for `op 1`", but the header is not what fails; what is
missing is a **state check on the iospace-0 path** and a **condition on the answer's write**. A device can be in the
header of an iospace it no longer belongs to only because a stale answer wrote the word from under a newer owner.

### The correction, judged

- "Refuse (`busy`, or `again`) any new `iospace_attach` (`367`/`368`) or `iospace_detach` (`373`/`374`) on a device that
  already has an `op 1` or `op 2` request in flight": right for the iospace-0 path, where there is nothing today, and it
  costs one read of a word the call already reads elsewhere. For the attach, 367 already does it. As written it would
  also fix the dead 368, but only if it is phrased as the word's state and not the header's.
- "In `368`, return success only if the device is currently `*attached*` with no detach/attach in flight": right, and it
  repairs the dead sentence. It has to be written as an exception to 367 or the list stays contradictory.
- "Restrict `359` / `373`–`374` so that a detach `UnitAnswer(done)` transitions `attach_word` to `0` and lowers `n`
  **only** if `attach_word == *detached*(iso.root)`": this is the load-bearing half, and it is right. It must be a
  compare-and-swap on both words — the attach word still reading *detached* with the requester's root, and the identifier
  word still naming the requester with its generation — because a newer attach can move both.
- "Refuse `op 1` / `op 2` answers from an earlier transition by matching the `iospace` root / generation in the unit
  request completion": unnecessary once the answer's own write is conditional; the entry already carries the requester and
  its generation (1037, 1038), and an *idempotent* detach must still answer *done* so that its requester's entry ends.
  Refusing the answer would leave the entry in the table.

**Cost.** One compare where 373 now has a plain write, and one read where the iospace-0 path now has none: both at a
detach and an attach, which 362 already charges "two gate writes each, never on a map". Nothing on a memory access or on
a message.

### The right text

In `kernel-interface.md:373`, replace

> at the answer done, the caller's gate writes the attach word 0 and the identifier word *free*, unclaimed, and lowers the
> root's count of devices, and the device leaves the iospace's header

with

> at the answer done, in one gate call, the caller's gate writes the attach word 0 and the identifier word *free*,
> unclaimed, lowers the root's count of devices, and the device leaves the iospace's header **only if the attach word
> still reads *detached* with this call's root and the identifier word still names the caller's node with the generation it
> wrote at its attach**; otherwise the answer changes nothing, the node traces it (code 11) and the call ends `gone`, since
> a newer attach or detach of the device owns the words now

and, earlier in the same item, after "With iospace 0:", insert

> if the attach word is *pinned*, an attach or a detach of the device is in flight: `busy`, and it takes the answer of the
> request that is in flight.

In `kernel-interface.md:367`, replace

> - the device is attached to another iospace, or is being detached, its attach word not 0 (`busy`; detach it first, or
>   wait for the detach's answer: D-137);
> - the device is already attached to this iospace (success, nothing changes);

with

> - the device is attached to another iospace, or an attach or a detach of it is in flight, its attach word *pinned* or
>   *detached* (`busy`; detach it first, or wait for the answer of the request that is in flight: D-137);
> - the device is already attached to this iospace, its attach word *attached* with this iospace's root (success, nothing
>   changes);

---

## Finding 5 — HIGH: the chain link in the first word of an unhooked table

### The quotes, at their lines

All three are **exact**: 267 (the D-137 chain rule, quoted with its ellipsis where the review cuts), 1078's G3 (4) ("a
non-present entry is written as all zeros") and 1087's G12 (2) ("that the invariant of G3 holds after **every store**, not
only at the end of a call, because the walkers of the node's other cores read the tables while the gate writes them"). I
add three sentences the finding turns on, all exact: 1096, "if the invariant holds before (every entry **reachable from
every root of the node** satisfies G3; ...)"; 1089's G14, "every entry that is not a leaf must point to a table page of the
next level down. A failure is a violation of containment: the machine stops with a stop record"; and 267's own "An aspace
takes tables from its free list first (most recently freed first), then from its untyped."

### The replay

1. An unmap empties a table. The table is unhooked from its parent, and the kernel writes the chain's next link into its
   first word (267).
2. A core or a unit with a cached entry of the old parent still walks the table at its old place (267's own reason for the
   whole rule). It reads entry 0, which now holds a link. On x86-64, ARM64 and VT-d the link is the physical address of a
   table page, so it is page-aligned: bit 0 is 0 (and bit 1 is 0 on ARM64), so the entry reads **not present** and the
   walker treats entry 0 as an unmapped page. This is what the walker would have seen anyway after the unmap.
3. The invalidation completes and the table joins the free list. **No rule clears the first word** — not 267, not the
   invalidation completion, not the free list.
4. A later map takes the table from the free list and hooks it as a non-present entry of some level. The table now holds a
   stale link in entry 0.
5. G14's audit walks a hooked table: every entry that is not a leaf must point to "a table page of the next level down".
   Entry 0 holds a link to a sibling table of the same aspace, at whatever level that sibling was. The walk fails, and "A
   failure is a violation of containment: the machine stops with a stop record". This is deterministic, on every node that
   unhooked a table and reused it, at the next recovery audit.
6. Before the audit, G3 (4) is broken at the hook: a non-present entry is not all zeros, and the entry is now reachable
   from a root.

### Verdict: confirmed in part

- **"The hardware walker interprets entry 0 as a present entry pointing at physical address 0 or bogus flags": refuted.**
  The review hedges it ("if a physical page address or pointer metadata happens to have bit 0 set"), but the hedge cannot
  be satisfied: a link is the physical address of a table page, and a table page is page-aligned by G3 (3) ("an entry that
  is not a leaf must point to a table page of the next level down"), so bit 0 and bit 1 are 0 on every architecture the
  contract serves. No walker follows it, and x86-64 and ARM64 ignore the remaining bits of a not-present descriptor. The
  danger the finding is named for does not exist.
- **G3 (4) and G12 (2) "after every store": confirmed, with a qualification the review does not make.** G3's invariant is
  scoped: "every entry **reachable from every root** of the node satisfies G3" (1096). A table in the chain is not
  reachable from a root, so the link in its first word does not break the invariant while the table is unhooked, and
  G12 (2) is satisfied while it is unhooked. The violation begins at step 4, when the table is hooked again, and there it
  is real and permanent.
- **The real defect, which the review only half reaches: the missing clearing rule.** Its scenario has the link in an
  unhooked table; the danger is in a *hooked* one, and the contract never says the word is cleared when the table leaves
  the chain. The report's correction keeps every unhooked table "all zeros" — which is impossible while the chain lives in
  the table — but does not add the rule that matters for the table that comes back.

### The correction, judged

**Does it close the hole?** Its direction (keep the up-to-2 × (*L* − 1) addresses in the request entry or the entry of the
unit request table) does close it, and its count is right (303 bounds a call at "at most 2 × (*L* − 1) tables", six with
four levels). But it is the expensive way: it changes the size of the invalidation request and of the unit request table
entry, in the layout of a structure whose size the contract states elsewhere, to avoid one rule.

**The cheaper correction, which is the one I recommend.** Keep the chain in the first word — it is the only storage the
contract already has, and 267's argument for it (an empty table has no use for the word) is sound while the table is
unhooked — and add the missing rule: the completion that ends the invalidation clears the first word of each table it takes
out of the chain, in the same gate call that puts the table on the free list, before it goes there. Then a hooked table is
empty, G3 (4) and G14 hold, and G3 (4) gains one sentence: the first word of a table that is in a change's chain is a link
and an entry of no root, so the rule of the all-zero non-present entry begins for it when it joins the free list.

**What the correction falsifies, and what it costs.** Nothing else in 267 changes; the sequence of the free list and its
order are untouched; 303's bound is untouched. The cost is one gate store per table that a call unhooks, in the gate call
that ends the invalidation — at most 2 × (*L* − 1) stores, six with four levels, at an unmap that freed a whole path, and
nothing on a map, an access or a message. Paid at a rare event, as the owners' principle requires.

### The right text

In `kernel-interface.md:267`, replace

> until then the tables a change unhooked are linked through their own first word, which an empty table does not use, in a
> chain whose head the request (or the entry of the unit request table) holds.

with

> until then the tables a change unhooked are linked through their own first word, which is an entry of no root while the
> table is in the chain, in a chain whose head the request (or the entry of the unit request table) holds, and the
> completion that ends the invalidation clears that word in the same gate call that puts the table on the free list, before
> it goes there (D-138: without the clearing, a table hooked again later carried a stale link in its first entry, which G3
> (4) forbids and which G14's walk reads as an entry of the next level down).

In `kernel-interface.md:1078`, in G3 (4), replace

> a non-present entry is written as all zeros;

with

> a non-present entry is written as all zeros (the first word of a table that a change's chain links is a link, not an
> entry of any root, and the rule begins for it when it joins the free list, where that word is cleared: [Page tables](#page-tables));

---

## Finding 6 — HIGH: what a `Report` of a line says about the mask

### The quotes, at their lines

All **exact**: 772 ("A level source is masked at the controller while the `irq` is idle or fired, and unmasked while it is
armed"), 791 ("An interrupt is signalled once until it is acknowledged. This is what bounds an interrupt storm"), 795 (the
removal of an `irq` that is a request, "for a line, first the redirection entry masked (operation 5, or the architecture's
route disabled)"), 962 (row 8, `Report`: "for a line the two operands of its operation 5 claimed"), 1477 ("rewrites each
reported line's entry from the two words of its report (the operands of its operation 5 claimed, checked as at that
request)") and 1478 ("a node reports every line whose word it holds, the dying ones included (D-137)"). Its quotation of
1041 is exact too, including "1 claimed or 0 masked (32)" and "masked: 0".

Three sentences of the same passages that the review does not use decide the finding: 782, "If the source is a level
source, it is masked at the controller" — step 1 of "**An arrival**"; 784, "If the irq is armed, it becomes fired and the
notify is signalled ... Otherwise an edge source sets pending" — step 3; and 787, "An arrival on an irq whose notify is
dying is handled as on an idle irq: nothing is signalled, a level source stays masked (step 1 masked it)". Also 1477's
last sentence, "Then it serves requests, the ones it kept during the rebuild first".

### The replay

1. A node *O* dies while it holds an IOAPIC's role. Its successor *S* takes the word and rebuilds the unit (1477).
2. *S* pulls a `Report` from every live or sealing node. For each line *N* holds, *N* sends "the two operands of its
   operation 5 claimed" (962) — that is, the words of the claim, whose first word has bit 32 set (`1041`: "1 claimed or 0
   masked (32)").
3. *S* rewrites each reported line's redirection entry from those two words (1477). Bit 32 is 1, so the entry is
   **unmasked**, whatever the line's `irq` state is.
4. If that line's `irq` is idle (no notify), or fired (signalled and not acknowledged), 772 requires the entry to be
   masked and it is not. **The rule breaks here**, at step 3, and it breaks for every idle and fired level line of every
   live node, at every take-over.
5. The cost, and it is bounded: the device asserts, an interrupt arrives on the claimed vector, and step 1 masks the level
   source at the controller before anything else (782). Step 3 signals nothing, because the irq is not armed (784). So the
   line is masked again by its own first arrival, and the kernel has taken exactly one interrupt it did not want — for a
   fired line, one more interrupt after the one the driver already owes an answer to.

### Verdict: confirmed in part

- **The idle and fired cases: confirmed.** 962 and 1477 do send and write the claimed form, 772 does require the mask, and
  nothing in 1477 reads the `irq`'s state. This is a real inconsistency between two rules of the same document, and the
  review found it.
- **"An interrupt storm", and the breaking of 791: refuted.** Step 1 of any arrival masks a level source, and step 3
  signals only an armed irq. A line rewritten unmasked while idle or fired therefore costs exactly one interrupt and masks
  itself. 791's bound is not "the line is unmasked", it is "An interrupt is signalled once until it is acknowledged", and
  nothing was signalled at all. The review's "immediate interrupt storm on any asserted device line whose driver's budget
  was exhausted" does not follow: a fired irq signals nothing, so an exhausted budget cannot be flooded.
- **The dying line: refuted.** The review says a line whose `irq` is mid-removal "is also reported as claimed and unmasked
  again at the IOAPIC". 1478 closes this in the same breath: "nor do its lines, since the removal of an `irq` on a line is
  a request too, **kept in the same way**", and 1477's last sentence says the rebuild-then-serve order: "Then it serves
  requests, the ones it kept during the rebuild first". So the queued `operation 5 masked` of the removal runs immediately
  after the rebuild and leaves the line masked. And even in the window, 787 says an arrival on a dying irq's line is
  handled as on an idle irq and "a level source stays masked (step 1 masked it)". The dying line costs nothing.

### The correction, judged

**Does it close the hole? Yes, with one part of it removed and one part added.** The report's first bullet — set bit 32 to
1 only when the line's `irq` is armed (or the source is an edge source), and to 0 when it is idle or fired — is exactly
right, and it is the whole of the fix. Its second bullet — "Update `1477` so the IOAPIC rebuild writes the RTE masked
(`mask = 1`) whenever bit 32 of the reported entry is `0`" — is right in effect and redundant: 1477 already writes the
entry "from the two words of its report", so once 962's words carry the mask, the rebuild follows.

Its instruction to change `1041`, `1084` (G9) and "the architecture's route" as well is wrong: 1041 is the operation's own
operand layout and its checks, which the rebuild does not perform (it is not a request), and G9 is about the classes of
iospace tables. Changing them widens the diff and touches a rule that is right.

**What the correction must add, or it breaks a line's destination.** The reported words are the *claim's* two words, and
the second of them carries the destination (the remapped handle and vector, or the vector and the APIC ID). A reported
"masked" word like the operand form of a masked *request* is "0" (`1041`: "masked: 0"), and a rebuild writing 0 would
leave the redirection entry with no destination at all until the driver's next `irq_ack`. So the words reported must stay
the claim's two words — with the mask bit cleared — and not become the masked request's operands. The report's wording
("carrying its trigger/polarity/destination or masked form as appropriate") half says this; the text below says it
exactly.

**What it costs.** One read of the `irq`'s state when a `Report` is built, at a role take-over, and nothing else: no lock,
no write, nothing on an arrival, nothing on a memory access. The alternative the contract has today costs one spurious
interrupt per idle or fired line per take-over, which is a cost on a rare event too — but it is a cost in the wrong
direction: it violates a rule the same document states.

### The right text

In `kernel-interface.md:962`, replace

> for a line the two operands of its operation 5 claimed (or of the architecture's route

with

> for a line the two operands of its operation 5 claimed, with bit 32 of the first word cleared while the line's `irq` is
> idle, fired or dying, so that the rebuild writes the redirection entry masked as the state of the `irq` requires and the
> second word still names the destination (D-138; or of the architecture's route

In `kernel-interface.md:1477`, replace

> rewrites each reported line's entry from the two words of its report (the operands of its operation 5 claimed, checked as
> at that request)

with

> rewrites each reported line's entry from the two words of its report (the operands of its operation 5 claimed, checked as
> at that request, with the mask bit as the reporting node cleared it for an `irq` that is idle, fired or dying: [Interrupt
> routing](#interrupt-routing))

---

## Finding 7 — HIGH: the request bound misses the work of the invalidation event

### The quotes, at their lines

All **exact**: 691 ("so a wait for a request lasts at most *N* × *H* (L1), or *E* for the asked core's current event plus
*E* + (*N* − 1) × *B*1max for a wait for the quiet word at its next entry (L2: 2 × *E* + (*N* − 1) × *B*1max, D-137: the
earlier bound left the quiet word out), plus *D*, the delivery of one interrupt, every core answering in parallel"), 692
("under L2, 2 × *E* + (*N* − 1) × *B*1max + *D*, with *E* = *E*1 + 2 × *k*max × (*N* − 1) × *h*") and 1512 (the same
expression in the row of the table of Numbers). I add the definition the finding turns on, 666: "*E* the longest kernel
event of another core of the node, its waits for locks included (its one-core bound plus 2 × *k*max × (*N* − 1) × *h*)".

### The replay

Core *c1* starts a request of its core and sends the invalidation interrupt to the asked core *c2*; the wait ends when *c2*
acknowledges and the request completes.

1. *c2* is inside an event. It ends at most *E* after the request starts: **+ *E***.
2. The interrupt is delivered: **+ *D***.
3. At the entry of its invalidation event, *c2* reads the quiet word. If a core holds it, *c2* writes 0 and waits, for at
   most "a kernel entry may wait for the quiet word for at most *E* + (*N* − 1) × *B*1max" (666): **+ *E* + (*N* − 1) ×
   *B*1max**.
4. *c2* then **runs** the invalidation event: it invalidates on itself what the request asks (up to *E* translations, 691's
   own bound of a request's work), clears its bit, sets its position in the acknowledged set by an atomic OR; and the last
   acker does the completion — it takes the gate lock, lowers up to *E* map counts, frees the tables an unmap unhooked,
   wakes the waiting thread and sets the state *done*. That event is a kernel event of *c2*, so its length is at most *E*
   by the definition at 666: **+ *E***.
5. Total: **3 × *E* + (*N* − 1) × *B*1max + *D***, and the contract states **2 × *E* + (*N* − 1) × *B*1max + *D***.

The sentence that stops the guarantee is step 3's list itself: 691 enumerates three terms — the asked core's current event,
the quiet-word wait at its next entry, and the delivery — and the event that follows the wait is not among them. It cannot
be inside *D*, which is "the delivery of one interrupt", and it cannot be inside the first *E*, which is the event the core
was in *before* the interrupt. The 2 × *E* is the current event plus the quiet-word wait's first term, and the second *E*
of the quiet-word term is the *holder's* wait for the other cores' events, not the asked core's work.

### Verdict: confirmed

The finding is right on the arithmetic, right on the consequence, and its correction is right. The consequence is the one
that matters, and 692 states the failure itself: "Otherwise ordinary contention would make a healthy node accuse itself
(the eighth review found the threshold crossed at eleven cores with a hold of 1 ms, and at three with the threshold at the
low end of its range ...)". With 2 × *E* as the minimum it accepts, an image whose `CORE_ANSWER_NS` sits just above that
minimum is judged healthy at start-up and then exceeds it on every long request: evidence self, reason 9, a node fenced
and reclaimed with no fault in it.

Two things in the finding are weaker than the truth or beside the point:

- Its step 3 says the quiet-word chain is "up to *N* − 1 escalating cores (whose wait begins with at most one remaining
  *E* for running cores plus (*N* − 1) × *B*1max)". The contract's term is fixed and simpler: *E* + (*N* − 1) × *B*1max,
  the *E* being the wait for the events the other cores are in (666). The finding should quote the term, not re-derive it.
- Its alternative "`2 × E + (N − 1) × B1max + E_ipi + D`" adds a term for the interrupt delivery that *D* already is ("*D*,
  the delivery of one interrupt"). Two terms for one cost.

### The correction, judged

**Does it close the hole? Yes**, and it is the only change: the *E* of step 4 goes into all three places that carry the
expression — 691, 692 and 1512 (the row of `CORE_ANSWER_NS` in the table of Numbers). Missing any one of them leaves the
start-up check computing a threshold the bound contradicts, which is what the eleventh review's verification found of the
expression before it.

**What it falsifies.** Nothing else: the L1 expression (*N* × *H* + *D*) is untouched, *E*'s own definition is untouched,
and 689's "with L2, every call and every event may first wait for the quiet word, at most *E* + (*N* − 1) × *B*1max" still
holds as a statement about one entry. It does mean the numbers of a real image move: the smallest accepted
`CORE_ANSWER_NS` grows by one *E*, and *E* itself grows with *N* through *k*max and *h*, so a machine with many cores
needs a larger value, or a smaller *h*. That is the honest cost.

**What it costs.** A comparison at machine start-up, computed from measured values, once. Nothing in operation, nothing on
a memory access, nothing on a lock. The alternative reading — that *E* already contains a quiet-word wait because 666 says
the term is "a term of every bound" — would be more than the finding asks and would double the same correction
everywhere; a reviewer may prefer to make *E*'s definition in 666 say "and the quiet word of one entry, once", but that is
a second change with its own cost, and the finding does not need it.

### The right text

In `kernel-interface.md:691`, replace

> (L2: 2 × *E* + (*N* − 1) × *B*1max, D-137: the earlier bound left the quiet word out)

with

> (L2: 3 × *E* + (*N* − 1) × *B*1max, D-137 left the quiet word out; D-138: the earlier bound left out the invalidation
> event the asked core runs after the wait, whose length is at most *E*)

In `kernel-interface.md:692`, replace

> under L2, 2 × *E* + (*N* − 1) × *B*1max + *D*, with *E* = *E*1 + 2 × *k*max × (*N* − 1) × *h*

with

> under L2, 3 × *E* + (*N* − 1) × *B*1max + *D* (D-138), with *E* = *E*1 + 2 × *k*max × (*N* − 1) × *h*

In `kernel-interface.md:1512`, replace

> *N* × *H* + *D* under L1 and 2 × *E* + (*N* − 1) × *B*1max + *D* under L2, which the machine start-up checks

with

> *N* × *H* + *D* under L1 and 3 × *E* + (*N* − 1) × *B*1max + *D* under L2 (D-138), which the machine start-up checks

---

## Finding 8 — MEDIUM: the lock counts, recounted lock by lock

### The quotes, at their lines

All **exact**: 670 (the pieces of *k*), 676 (`recv` 40), 677 (`reply_recv` 67), 678 (`thread_configure` 21), 679 (a step
of a removal, 387), 680 (a step of `task_revoke`, 194), 681 ("`node_send` takes 10 ..."), 664 (the list of tries). I also
read the sentences the counts rest on: 658 (the order by kind), 660 (a try never waits), 656 (the `cspace`'s own fields
under the word of the first directory entry), 920 ("A notify keeps the list of the grant entries whose doorbell it is,
linked through those entries"), 604 ("A `call` to a passive receiver and its answer move no context between queues: the
context stays eligible and only its holder changes"), 363 and 1148 to 1151.

**The order the counts are taken in (658):** the sequence words of `cspace` segments, by space then segment; task; thread;
endpoint; reply; notify; timer; `sched`; aspace; iospace; the lock words of cores, by position; the gate. A core counts
"one lock per core whose queues or interrupt table the call may change" and one for the gate (670).

### The recount, one number at a time

**(1) `node_send`, 681: the review says 10 → 11. It is right.** The row's own pieces: "the frames' slots and their old
next in the derivation list for the anchors, 8" — four anchors, each with the frame capability's segment and the segment
of the parent's old next, 2 each, 8; "the caller's core", 1; "the gate, which guards the rings and the credits", 1. That
is 10, and the doorbell is missing. The doorbell is a notify named by the call (999: the argument `doorbell`), and 920
says the notify "keeps the list of the grant entries whose doorbell it is, linked through those entries", while 1005 has
the gate write "one grant entry per frame listed (the anchor, the rights, the target's current generation as grantee, the
doorbell)". Inserting an entry into that list writes the notify's head, which is a field of the notify and guarded by its
lock word (656). So one notify lock. Order: the 8 segments are `cspace` segments, first in the order (658); the notify
comes after reply and before timer; the core and the gate last. So 8 + 1 + 1 + 1 = **11**, taken in order, with no try.
Confirmed.

**(2) `recv`, 676: the review says 40 → 43. It is wrong; the number is 40.** Sum the row's own pieces: the endpoint and
the reply object, 2; "the two lends released, each its `sched`, the two reply objects next to it in its chain and the
thread it leaves without a context (8)", 2 × 4 = 8, so 10; "the bound notify", 1, so 11; "the 26 of the caller found",
26, so 37; "the caller's `sched`, lent, and the reply object on top of its chain", 2, so 39; "the thread's own core", 1,
so **40**. The row is complete and consistent with its pieces.
The review adds "up to 2 more core locks + 1 gate lock" because the lent and released `sched` objects "may have their
`sched` placed on **different** cores from the receiver's own core, requiring updates to those cores' scheduler queues and
reschedule IPIs sent through the **gate**". Nothing in the contract does that. A passive receiver runs on the core of the
context lent to it ("A `call` to a passive server runs it on the caller's core", 696), so the context whose `sched` is
released is on the receiving core, and 604 says in the contract's own words that a call to a passive receiver and its
answer "move no context between queues: the context stays eligible and only its holder changes". Releasing a lend changes
the holder, not eligibility: the home was runnable before and after. No queue is touched on another core, so no core lock
and no reschedule interrupt, and therefore no gate. The `sched` locks the review points at are already in the 8. **40
stands.**

**(3) `reply_recv`, 677: the review says 67 → 69. It is wrong, and the right number is 68, not 67.** The answer's 29 is
right (the reply object, the 26, the caller's core, the gate). The receive part is "`recv` less its reply object, which is
the same, and less the gate counted once: 38", and that parenthetical is the defect: `recv`'s 40 contains **no gate**, as
the recount above shows, so there is no gate to subtract once and the receive part is 39, not 38, and the call is 29 + 39
= **68**. So the review's 69 is one too high and the contract's 67 is one too low; the review found the region and missed
the arithmetic. Its stated reason (two more core locks for the answered and the receiving caller) does not hold either:
the answered caller's core and the gate are in the 29 already.

**(4) The segments of a dying space in a step of a removal, 679: the review says 2 → 3. It is right.** The row sums to
387: 32 units × 8 = 256; "the threads woken by the reply objects the walks pass, at most 64, each the lock of the object it
waits on and of its core, 128" = 128; "the segments of the 128 slots of a dying space it examines, 2"; "the gate, 1".
256 + 128 + 2 + 1 = 387. The step that sweeps a dying space reads and writes its sweep position, and 656 puts a `cspace`'s
own fields — "its dying mark, its sweep, the head of its list of bound threads" — under "the sequence word of the first
entry of its directory". That word guards the first segment of the space's directory, which is a `cspace` segment, not the
segments the 128 slots being examined lie in. So the step holds it as well: 2 → 3 segments, and 256 + 128 + 3 + 1 = **388**.
Confirmed.

**(5) `task_revoke`'s later steps, 194 → 226: the review is wrong; 194 stands.** The row: "the first unit ... the task, at
most 63 threads, their 63 cores and the gate, 128" = 1 + 63 + 63 + 1 = 128; "each later step, the task, 32 detached
threads of 6 each ... and the gate, 194" = 1 + 192 + 1 = 194. The per-thread 6 is "the thread, the object it waits on, its
reply object, its two neighbours in the task's list, its core", and 1149 to 1151 give two shapes of detached thread:
- a thread that **waits**: "it leaves its queue", so the endpoint it waits on (1), "a reply object attached to it or armed
  with it becomes idle" (1), its two neighbours in the task's list (2), the thread (1), its core (1) = **6**. It has no
  queued `sched`: a waiting thread is not runnable, so its context is not eligible, so it is in no queue.
- a thread that is **ready**: its suspended flag is set (1146: "When the scheduler would pick it, the kernel sets its
  suspended flag"), so its context leaves its core's queue: the thread (1), its `sched` (1), its two neighbours in the
  task's list (2), its core (1) = **5**. Its queue links are guarded by its core's lock, which is one of the five, as it is
  for every queue in this contract (676's "the thread's own core" is the same term).
A thread is in one shape or the other, never both, so 6 covers both. **194 stands**, and the review's 226 counts a lock the
6 already has room for.

**(6) `thread_configure`'s try list, 664: the review is right.** 664 lists for `thread_configure` "the segment or the
thread of a neighbour in a space's list of records or of bound threads". The call also reads, through the thread it holds,
the `cspace` the thread leaves (whose own fields sit behind the sequence word of its first directory entry, 656) and the
message page's slot, which sits in a `cspace` segment. `cspace` segments come before thread in the order (658), so both
are locks "a call finds by reading an object it already holds locked, and that comes earlier in the order" (660) — the
definition of a try. 678 already counts them ("the sequence word of the first directory entry of a `cspace`" and "the
segments of the old and of the new message page's slots"), so the *k* is right and only the list of tries is short. The
new message page's segment needs no try: it is an argument, known before the first lock, and it is taken in order before
the thread.

### Verdict: confirmed in part, three of six changes right

| the review's change | my recount | verdict |
|---|---|---|
| `node_send` 10 → 11 (`681`) | 11 (8 segments + the doorbell notify + the core + the gate) | right |
| `recv` 40 → 43 (`676`) | 40 (no queue moves, so no core and no gate) | wrong |
| `reply_recv` 67 → 69 (`677`) | **68** (29 + 39: `recv` holds no gate to subtract) | wrong, and it misses the real error of one |
| the dying space's segments 2 → 3 (`679`) | 388 (256 + 128 + 3 + 1) | right |
| `task_revoke` 194 → 226 (`680`) | 194 (6 covers a waiting thread, 5 a ready one) | wrong |
| `thread_configure`'s try list (`664`) | two locks must be tried | right |

### The correction, judged

Two of the three wrong changes are one error repeated: the review assumes that a released lend moves a context between
cores' queues. 604 says it does not, and 696 places a passive server on the caller's core. The third is a wrong
per-thread sum that would put a lock on a thread shape that has no such lock. Its one genuine miss in the same rows is
`reply_recv`'s 67, which should be 68.

**What the right changes cost.** One notify lock in `node_send`, on a call that is already the most expensive in the
contract and that is not on a memory access or a message path of one node; one `cspace` segment lock in a removal step that
sweeps; two tries in `thread_configure`'s list, which is a re-read of locks the call already takes. All are locks already
taken under other rules, so the bound grows by one or two and nothing new is *paid*; `recv`, `reply_recv` and
`task_revoke` keep their cost.

### The right text

In `kernel-interface.md:681`, replace

> `node_send` takes 10 (the frames' slots and their old next in the derivation list for the anchors, 8; the caller's core;
> the gate, which guards the rings and the credits)

with

> `node_send` takes 11 (the frames' slots and their old next in the derivation list for the anchors, 8; the doorbell's
> notify, whose list of doorbells the new entry joins; the caller's core; the gate, which guards the rings and the credits)

In `kernel-interface.md:677`, replace

> and the receive (`recv` less its reply object, which is the same, and less the gate counted once: 38)

with

> and the receive (`recv` less its reply object, which is the same: 39, `recv` holding no gate)

and change the row's 67 to 68. In `kernel-interface.md:679`, replace

> the segments of the 128 slots of a dying space it examines, 2; the gate, 1

with

> the segments of the 128 slots of a dying space it examines and the sequence word of its first directory entry, which
> guards its sweep and its dying mark: 3; the gate, 1

and change the row's 387 to 388. In `kernel-interface.md:664`, replace

> `aspace_map`, `iospace_map`, `aspace_unmap`, `iospace_unmap`, `thread_configure` and the removal of a frame capability
> with a record, the segment or the thread of a neighbour in a space's list of records or of bound threads;

with

> `aspace_map`, `iospace_map`, `aspace_unmap`, `iospace_unmap`, `thread_configure` and the removal of a frame capability
> with a record, the segment or the thread of a neighbour in a space's list of records or of bound threads, and, for
> `thread_configure`, the locks of the lists and the message page it leaves — the sequence word of the first directory
> entry of the old `cspace` and the segment of the old message page's slot — which it finds by reading the thread it holds;

---

## Finding 9 — MEDIUM: an `irq`'s removal frees the handle and the vector when the invalidation failed

### The quotes, at their lines

All **exact**: 795 ("At the end of the last request, done or *failed*, the line word is written *free*, unclaimed, the
remapping entry and the vector are free, and the next step removes the capability"), 1043 ("a unit found failed may still
hold a stale entry for the handle, one more cost of its failure") and 380 ("`iospace_attach` and every later request on
the unit are `busy`"). Its citation of the handle's formula to 1030 is imprecise — 1030 gives the *range*, "handles *core*
× 192 to *core* × 192 + 191 on x86-64, for each core whose word names the node" — and the formula itself is at 815:
"handle *h* = core number × 192 + (vector − 48)". I add the sentence the finding's harm rests on, 815: "The device can then
raise only that entry: a device cannot forge another interrupt."

### The replay

1. Node *X* claims `(core, vector)`; the claim writes the remapping entry at handle *h* = core × 192 + (vector − 48) with
   "the vector, the APIC ID of that core, edge or level, and source validation" (815).
2. *X* removes the `irq`. The removal is a request: the line is masked (operation 5), then the interrupt entry cache of
   every unit that serves the source's segment is invalidated (operation 4) (795).
3. Unit *U* has failed, or fails now. It answers *failed* to operation 4, and 1043 admits the consequence: "a unit found
   failed may still hold a stale entry for the handle".
4. "At the end of the last request, done or *failed*, ... the remapping entry and the vector are free" (795). So the vector
   can be claimed again (795's first sentence says so of the vector in the same breath), and *h*, being a function of
   (core, vector) alone, is the same handle for the next claim on that core and vector.
5. Another `irq` claims the same `(core, vector)` for a different source and writes its own remapping entry at *h*.
6. The failed unit's cache still holds the *old* entry for *h*: the old vector, the old core, and the old source's
   requester ID. A device still behind *U* that raises an interrupt with the old MSI address and data passes source
   validation against the stale entry and is delivered to `(core, vector)` — the vector of the new `irq`. The new `irq`'s
   owner receives an interrupt from a device it does not own, and 815's "a device cannot forge another interrupt" is
   false.
7. Nothing in the removal says otherwise: the freeing happens on *failed* as on *done*, in one sentence that names both.

### Verdict: confirmed

The chain is complete and every step is a sentence of the contract. The failure is at step 4, and the sharpest form of it
is the one the review gives: the same `(core, vector)` is re-claimable, so the stale cache entry points at a live vector
that has changed owner. The review's extra condition — "if a line's IOAPIC mask `op 5` itself also answered *failed*" — is
not needed: the forgery works with operation 5 done and operation 4 failed, because the mask is a different request to a
different holder. And its parenthesis about "another node reusing the line/vector ... or via another working unit" is beside
the point: the handle is a function of the core and the vector only (815), and the table "holds one entry per handle"
(815), so the re-claim is on the same core and the same vector by construction, and any unit that serves that core's
segment may be the one with the stale cache.

### The correction, judged

**Does it close the hole? Yes.** Keeping the vector claimed makes the handle unreachable without any new state: 776 says
`irq_claim` is "`busy` if the vector is already claimed on that core", and a kept vector is claimed. Keeping the line word
out of *free* keeps the line from being re-claimed and reported. Finishing the removal of the capability in the same step
keeps `cap_delete` terminating, which Finding 3 shows the contract needs an explicit rule for. This is exactly 379's
pattern, applied to a second resource: keep what a failed unit can still act on, until the machine restarts.

**One thing to add to it.** The step should record *why* the vector stays: a word the node keeps, or the state *failed* of
the request's entry, so that a later `node_status` or a rebuild can report it; and 380's list of what a failed unit keeps
should name the vector, since that list is what an owner reads to know what a failure costs. The review does not say where
the "retired" state lives.

**What it costs.** One vector and one handle per `irq` of a failed unit, for the rest of the boot — the same currency as
379 and 380, and nothing at all on a healthy path: the check is a state test at the end of a removal request, an event that
already exists. Never on a memory access, never on an arrival.

### The right text

In `kernel-interface.md:795`, replace

> At the end of the last request, done or *failed*, the line word is written *free*, unclaimed, the remapping entry and the
> vector are free, and the next step removes the capability.

with

> At the end of the last request the next step removes the capability, and if every request was answered *done* the line
> word is written *free*, unclaimed, and the remapping entry and the vector are free. **If any request was answered
> *failed*, the vector and its remapping entry are not freed and the line word is not written *free* (D-138):** the vector
> stays claimed on its core, so `irq_claim` is `busy` for it and the handle, which is the core's number and the vector, can
> be claimed by no other source; the capability is removed as usual, so the removal ends. A unit that has failed may hold
> the entry of that handle for ever (below, and [Devices and shared hardware](#devices-and-shared-hardware)), and freeing
> the handle would let another source take it while the unit still delivered the old source's interrupts to the vector.

In `kernel-interface.md:380`, after

> `iospace_attach` and every later request on the unit are `busy`

insert

> , the vectors whose removal a request of the unit answered *failed* stay claimed for the rest of the boot ([Interrupt
> routing](#interrupt-routing))

---

## Finding 10 — MEDIUM: `idle_until` and the stopped time of a development image

### The quotes, at their lines

All **exact**: 1283 ("`idle_until`, the instant of its next armed timer when it goes idle (the largest value if none), so a
core does not have to beat while idle, and 0 again at its first event after idle"), 1294 ("now − *t* ≥ `STALE_NS`, and now
− `STALE_NS` > `idle_until`") and 1662 (the paragraph on the stopped time, ending "so `STALE_NS`, `STUCK_NS`,
`CORE_ANSWER_NS`, `FENCE_NS`, `SEAL_NS`, `START_NS` and `IOMMU_WAIT_NS` all leave the stop out, and an instant stored before
the stop is still right after it").

### The replay

**Its case 1, the literal reading.** `idle_until` is stored as the timer's instant, which is a value of the monotonic clock
(479: "The kernel has one clock: a count of nanoseconds in 64 bits, monotonic, the same on every core"; and 1662: "The clock of user threads, their timers and the scheduling of contexts read the monotonic clock unchanged"). The comparison at 1294 is
`now − STALE_NS > idle_until` with `now` read, in a development image, as "the monotonic clock less the stopped time"
(1662). Then a cumulative stopped time of 10 s makes the left side 10 s smaller than the right side's clock, and a hung
idle core is found stale 10 s late. **The rule breaks at the comparison**, and the review's arithmetic is right.

**Its case 2, "even worse".** Here the review subtracts the stopped time twice. It stores `idle_until = 10.010` (the timer's
instant, with `stopped_time = 0` at that moment), then a 5 s stop, and then computes `idle_until − stopped_time = 5.010`
and compares `now − STALE_NS = 9.901 > 5.010`. But 1662's rule is that the *instant is read from* the clock less the
stopped time, on both sides: `idle_until` stored at `10.010` when the stopped time was 0 **is** its adjusted value, and
`now − STALE_NS` is 9.901, so `9.901 > 10.010` is false and no accusation follows. 1662 says so in words: "an instant
stored before the stop is still right after it". A value stored on the adjusted clock does not need the subtraction again.
So case 2 is refuted by the sentence it quotes.

Its premise that "on resume its deadline 10.010 s has already passed" is also weaker than it needs: on the resume the timer
fires at once, the core wakes, and 1283 has it write `idle_until` 0 "at its first event after idle", so the window it
describes closes by itself.

### Verdict: confirmed in part

- **Case 1: confirmed**, and it is a real gap between two lines: 1283 defines the word as a timer instant and 1662 adjusts
  the comparison, without saying that the stored value is on the adjusted clock. On the letter of the two lines the review
  is right.
- **Case 2: refuted**, for the reason above; it contradicts 1662's own closing clause.
- **Its correction: right in its one clean formula, wrong everywhere else, and visibly unsettled.** `idle_until = d −
  stopped_time_at_entry_to_idle` is the fix. Its option (a), "have the stub push `idle_until` forward by `delta_stopped`
  when resuming", is the double subtraction of case 2, written as a rule; its option (b), comparing on the raw monotonic
  clock with `current_stop_elapsed`, is the same mixed clock by another route; and its own text interrupts itself with
  "wait, no". A review that offers three mutually inconsistent repairs of one word leaves the owners nothing to apply.

### The correction, judged

**Does it close the hole? Yes, in the form I give below**, which is one clause in one line: a core writes `idle_until` as
an instant of the adjusted clock — the timer's instant less the stopped time in force when it goes idle. Then the
comparison at 1294 is between two instants of one clock; a stop while the core is idle adds to the stopped time and
leaves the adjusted `now` where it was, which is right, since the idle time the machine spent stopped is not time the
node counts; and a stop before the core goes idle is already inside both sides.

**What it falsifies.** Nothing: 1294's condition stands, 1662's list stands, and the sentence "an instant stored before the
stop is still right after it" becomes true of `idle_until` as it is of the gate's instants. It does require the same
reading for the other instants 1662 names — they are all stored from the adjusted clock, which 1662 says — so the fix
makes 1283 the only line that had to change.

**What it costs.** One subtraction when a core goes idle, at an event that happens once per idle period of a core, and
nothing anywhere else: no memory access, no lock, no arrival, and nothing at all in a production image, which has neither
the release word nor the stopped time.

### The right text

In `kernel-interface.md:1283`, replace

> `idle_until`, the instant of its next armed timer when it goes idle (the largest value if none), so a core does not have
> to beat while idle, and 0 again at its first event after idle

with

> `idle_until`, the instant of its next armed timer when it goes idle (the largest value if none), read on the clock of a
> development image's stopped time — the timer's instant less the stopped time in force when it goes idle (D-138) — so a
> core does not have to beat while idle, and 0 again at its first event after idle

---

## Finding 11 — LOW: editions, citations and one internal inconsistency

### What I could open, and what I could not

**Not opened:** the Intel SDM, order 325462-093 (September 2026); the Intel VT-d specification, revision 5.20, order
D51397-019 (April 2026); Arm DDI 0487 M.d; DEN0022F.b (PSCI 1.3). I have no access to any of them from this environment,
and I will not pass off a search result as the document. So every claim of the review that a section number, a figure or a
bit field "matches" one of those documents is **unverified by me**, and so is every claim in its section "External
citations verified against primary/indexed documentation": the Arm sections B2.3.1, C5.5.60, C5.5.11, D8.17.1, D8.17.7,
D8.17.8 and C5.2.1; the VT-d sections 5.1.5.1, 6.2.2.1, 6.5.2.8 with Figure 6-8, and 11.4.2; and the PSCI sections 5.1.7,
5.1.8 and 5.9. I note that its own list admits that `IWZCBG` "could not be verified through public web indexing", which
tells me the method was web indexing, and web indexing cannot settle what a printed section says.

### (a) The Intel SDM edition: confirmed as an internal inconsistency, its remedy unverified

The three quotations are **exact**: 80 ("**Editions cited (D-135).** Each specification is cited in one edition, the
current one on 17 November 2026, named here once; a citation elsewhere gives only the document and the section: the Intel
SDM, combined volumes, order 325462-093 (September 2026)"), 1312 ("Every citation of the Intel SDM in this contract is of
the edition named in [Call reference](#call-reference), read on 16 November 2026 (it renumbered the chapters of volume 3
cited before from order 325384-086)"), and 666 ("read in the older edition 253668-032, §8.2.3.4, not in the edition named
above").

The inconsistency is real and it is in the contract, whatever the SDM says: 666 states that one of its citations is of an
older edition, and 1312 states that every citation is of the edition named. One of the two sentences is false. 80 is
contradicted too, twice — "Each specification is cited in one edition" and "a citation elsewhere gives only the document
and the section" (666 gives the edition as well, deliberately).

What I cannot confirm is the review's remedy: it says the section is "Volume 3A, §11.2.3.4" of 325462-093. That number is
consistent with 1312's own statement that the new edition renumbered volume 3's chapters (8 becomes 11), and it is
plausible, but I did not open the document, so I cannot say the section is there and I cannot say the old §8.2.3.4 became
§11.2.3.4. A correction that rests on a citation nobody in this repository can open must be marked as needing that check,
not asserted. The cheaper repair, which needs no access to the document, is to keep 666's sentence and add the exception to
80 and 1312 — one older edition, one sentence, named once — and to make 1312 say "except one sentence of the section on
memory ordering, marked there".

### (b) The watermark's `again` under L1 and L2: confirmed, and the review's correction is right

The quotations are **exact**: 665 ("**The rule holds under both variants (D-137):** under L1 the events of a node run one at
a time under the node lock, but the two lock-free paths ... read and write object memory outside the lock, so the watermark
rule reads the entry words there too"), 1746 ("Under variant L2, `Again` while the watermark is ready to return and another
core of the node is still in the kernel event it was in at the last destruction (D-135); `Again` under variant L2 only,
with nothing changed (D-134, D-135)") and 1775 ("`Again` is a new result of fourteen calls under variant L2, with nothing
changed").

The inconsistency is real, and the mechanism at 665 shows it can happen: under L1 a core inside its event may be doing a
slot read before it takes the node lock, so a second core holding the node lock for `untyped_retype` can see a non-zero
entry word and must return `again` — under **both** variants. So 1746's "Under variant L2" and 1775's blanket "under variant
L2" are both wrong for this one `again`, and the review is right that both lines must change. Its parenthesis, "while L2
tries `Again` remains L2-only", is the distinction that keeps the fix from breaking 664 ("Each of these calls but `signal`
may therefore return `again` with nothing changed under L2"). This part of the finding is the best-argued part of the
review: it names the two lines, the mechanism and the limit of the fix.

### (c) The VT-d revision and order number: not a finding

The review says "order string `D51397-019` and date `April 2026` did not appear in indexed pages" and asks the owners to
"verify the VT-d PDF header". A document's order number that does not appear in a web index is not evidence that it is
wrong, and the review itself says the sections match version 5.2. **Not opened**, so I cannot settle it either, and I do
not treat it as a defect. One thing the review could have found instead, in the same line of 80, is an inconsistency that
needs no document: 80 says "Every section cited from these four was read again in these editions on 17 November 2026,
except those of the Intel SDM", while D-137's entry says of VT-d section 5.1.5.1 "revision 3.2 (D51397-012, read by the
assistant; **revision 5.20 not read**)". The contract's own decision record contradicts its own statement that every
cited section of VT-d was read in revision 5.20. That is the same class as (a) and it can be checked in this repository.

### Verdict: confirmed in part

(a) confirmed as an internal contradiction, with a remedy that cannot be verified here and should be marked as such;
(b) confirmed, and its correction is right; (c) not a defect, and the review's own evidence does not support it.

### The right text

In `kernel-interface.md:1312`, replace

> Every citation of the Intel SDM in this contract is of the edition named in [Call reference](#call-reference), read on 16
> November 2026 (it renumbered the chapters of volume 3 cited before from order 325384-086).

with

> Every citation of the Intel SDM in this contract is of the edition named in [Call reference](#call-reference), read on 16
> November 2026 (it renumbered the chapters of volume 3 cited before from order 325384-086), except one sentence of [A node
> of several cores](#a-node-of-several-cores), which quotes the section on memory ordering from the older edition
> 253668-032 and says so there.

In `kernel-interface.md:1746`, replace

> Under variant L2, `Again` while the watermark is ready to return and another core of the node is still in the kernel event
> it was in at the last destruction (D-135); `Again` under variant L2 only, with nothing changed (D-134, D-135)

with

> `Again` while the watermark is ready to return and another core of the node is still in the kernel event it was in at the
> last destruction, under both variants (D-135, D-137: under L1 a core reads a slot outside the node lock); `Again` of the
> rule of tries under variant L2 only, with nothing changed (D-134, D-135)

In `kernel-interface.md:1775`, replace

> `Again` is a new result of fourteen calls under variant L2, with nothing changed

with

> `Again` is a new result of fourteen calls under variant L2, with nothing changed, and of one call under both variants, the
> watermark of `untyped_retype` that is ready to return

---

## What the review missed in the same passages

Same standard: every item is a sequence that follows from sentences I can point at.

**1. `368` is unreachable, and `367`'s gloss says so (lines 367 and 368).** 367 is "the device is attached to another
iospace, or is being detached, its attach word not 0 (`busy` ...)". A device "already attached to this iospace" has
`attach_word = attached(root)`, which is not 0, so 367 fires first and 368 never runs. The checks are "judged in this
order" (363), so the order is what makes 368 dead. Two consequences: an `iospace_attach` repeated on an attached device
answers `busy` where the contract meant it to be idempotent, and a reader cannot tell whether 367's "or is being detached"
is meant to qualify the word or to name a second state. The repair is in the exact text of Finding 4.

**2. The stale link is a hooked table, not an unhooked one (line 267).** The review's danger is a hardware walker following
entry 0 of an unhooked table; the real danger is a table that comes back. Nothing clears the first word when the table
leaves the chain and joins the free list, and G14's audit (1089) reads a non-zero non-leaf entry of a hooked table as a
violation of containment and stops the machine. This is a deterministic machine stop, not a hypothesis, and the review's
own scenario does not reach it.

**3. The `8` of a removal unit has no room for the dying mark of a space the unit kills (lines 656, 670 and 679).** 670
counts "removing one, as a unit of a removal, takes 3 segments (its slot, its previous and its next) and, for a full
record, 2 more segments, the space, the gate and the lock of the caller's core for its invalidation request: 8". A unit
whose capability is the root of a `cspace` also writes that space's dying mark, and 656 puts a `cspace`'s dying mark under
"the sequence word of the first entry of its directory" — a segment that is not one of the unit's three. Since 679 says the
step "holds [the locks of its units] until the step ends", the mark's lock is held too: 9 per such unit, and a step of 32
such units is 288, not 256, so the step's bound is 288 + 128 + 3 + 1 = 420, not 388. Either the row must say the mark's
lock is taken and released before the unit's first try, or the number must grow.

**4. The iospace-0 path has no state checks at all (line 373).** 363's ordered list is introduced by "With an iospace",
and 373's `iospace 0` branch goes straight to the effects. So a detach on a *failed* unit is not `busy` first, unlike every
attach (364); a detach while an attach is in flight is not refused; and two detaches are not refused. This is the shared
cause of the review's Finding 3 loop and Finding 4's race 2, and the review names neither the missing check nor where it
belongs.

**5. `380`'s reason is wrong for a failed attach, and the review finds only half of it (line 380).** The review notices that
`attach_word` stays *pinned* rather than *attached*; it does not say that the same sentence is the only place the contract
justifies keeping the root's count above 0, so a reader who finds the reason false may conclude the count is 0 and free the
pages. The exact text of Finding 3 repairs both halves.

**6. `recv`'s list has no gate and `reply_recv` subtracts one (lines 676 and 677).** The review reads 676's missing gate as
the defect; the arithmetic of 677 is the other half of the same coin, and its `67` is one too small. Nobody can have both,
and the review's `69` is not the number either.

**7. The contract states that VT-d revision 5.20 was read, and its own decision record says it was not (lines 80 and
D-137).** 80: "Every section cited from these four was read again in these editions on 17 November 2026, except those of
the Intel SDM". D-137: "section 5.1.5.1 of revision 3.2 (D51397-012, read by the assistant; revision 5.20 not read)". One
of the two is false, and the finding spends its effort on an order number instead.

**8. Two lines disagree on whether an idle core is ever asked (lines 691 and 1512).** 691 bounds a request with "an idle
core is not asked: [TLB](#tlb-one-core-and-several)", while the row of `CORE_ANSWER_NS` at 1512 ends "an idle core is never
asked, except to invalidate the kernel's own space". One of the two is wrong, and the exception is the one that matters to
the bound: a core asked for the kernel's own space is asked while it is idle, and its answer begins with an entry into the
kernel, so the term *E* of 691 is not the term that bounds it — its event begins at once, and the request's cost is *D*
plus the wait for the quiet word plus one event, which the 2 × *E* (or, after Finding 7, 3 × *E*) of 691 covers. The
sentence should say which core is exempt and from what.

---

## Corrections to apply, in order of severity

**1. `kernel-interface.md:666`, the escalation: a deadlock between two escalators (Finding 1).** Replace "takes the
node's **quiet word** (…; held while the two differ), raises the node's kernel epoch by one by an atomic add, orders both
before its next load" with: "writes its entry word 0 by the operation that orders a store before the next load (`XCHG` on
x86-64, the store then `DMB ISH` on ARM64, the store then `fence rw,rw` on RISC-V), after it has released every lock and
before it reads the word, so that a core that finds it waiting reads 0; takes the node's **quiet word** (…; held while the
two differ), raises the node's kernel epoch by one by an atomic add, orders that store and the ticket before its next
load". In the same sentence, replace "runs the call alone, taking its locks in the order (no try can fail and no link can
change, since no other core is in a kernel event)" with: "reads the epoch once more and, if it differs from the one it read
at its entry, releases the word by advancing its serving ticket and returns `again` with nothing changed; otherwise it runs
the call alone, taking its locks in the order (no try can fail and no link can change, since no other core is in a kernel
event)". In `668`, replace the sentence "a core waits for it only at the entry of an event, before it takes any lock, its
entry word 0" with: "a core waits for it in one of two places, both outside every lock: at the entry of an event, before it
takes any lock, and at an escalation, after it has released every lock and changed nothing; in both places it writes its
entry word 0 before it waits".

**2. `kernel-interface.md:1116`, `task_attach` and marks: a thread loses bits when it changes task (Finding 2).** Replace
"and `task_attach` writes the thread's new task first, … no bit a delivery stamps is lost by the thread or by the task it
ends in." with: "and `task_attach` that moves a thread from one task to another, or to none, takes the node's quiet word
first, as an escalating call does: it writes its entry word 0, waits for the word, and only then reads the marks of the
task the thread leaves, ORs them into the new task's word (for a detach, ORs them into the thread's own word, which already
holds every bit of them), writes the thread's task word, and releases the word. While it holds the word no core is inside a
kernel event and no core can enter one, and a delivery is part of an event and not a call of its own, so no delivery reads
or writes either marks word while the thread crosses. Under L1 no quiet word exists and none is needed: the events of a node
run one at a time under the node lock. An attach that changes nothing takes no word." In `1120`, replace "Detaching sets
the thread's own marks word to the marks of the task it leaves." with "Detaching ORs the marks of the task it leaves into
the thread's own marks word, under the quiet word."

**3. `kernel-interface.md:373` and `367`: a stale detach answer writes the words of a newer attach (Finding 4).** In 373
replace "at the answer done, the caller's gate writes the attach word 0 and the identifier word *free*, unclaimed, and
lowers the root's count of devices, and the device leaves the iospace's header" with: "at the answer done, in one gate
call, the caller's gate writes the attach word 0 and the identifier word *free*, unclaimed, lowers the root's count of
devices, and the device leaves the iospace's header **only if the attach word still reads *detached* with this call's root
and the identifier word still names the caller's node with the generation it wrote at its attach**; otherwise the answer
changes nothing, the node traces it (code 11) and the call ends `gone`". Add after "With iospace 0:" in the same item:
"if the attach word is *pinned*, an attach or a detach of the device is in flight: `busy`, and it takes the answer of the
request that is in flight." In 367 and 368, replace the two items with: "- the device is attached to another iospace, or an
attach or a detach of it is in flight, its attach word *pinned* or *detached* (`busy`; detach it first, or wait for the
answer of the request that is in flight: D-137); - the device is already attached to this iospace, its attach word
*attached* with this iospace's root (success, nothing changes);". This also repairs the dead `368`.

**4. `kernel-interface.md:374` and `380`: the destruction of an iospace on a failed unit never ends (Finding 3).**
In 374, replace "The root and the tables turn back into *data* only once the root's count of devices is 0 (G2); a detach
answered *failed* leaves the attach word *attached* and the count above 0 (below)." with: "The root and the tables turn
back into *data* only once the root's count of devices is 0 (G2), and a detach answered *failed* leaves the attach word as
it was and the count above 0 (below). **A device of a unit that has failed is detached for the purpose of this step at a
*failed* answer (D-138):** the answer removes the device entry from the iospace's header, and so from the node's list of
its devices for that unit, counts as a unit of the step, leaves the attach word and the identifier word as they are and
does not lower the count. Such an iospace's destruction then ends with the count above 0: the root capability is removed,
and its pages and tables keep their class and are never reused before the machine restarts (below)." In 380, replace "since
the attach word stays *attached*: D-137" with "since the attach word stays *attached*, or *pinned* if the device's attach
was never served, D-137".

**5. `kernel-interface.md:691`, `692` and `1512`: the request bound misses the invalidation event (Finding 7).** Replace
"2 × *E*" with "3 × *E* + …" in exactly these places: in 691 "(L2: 2 × *E* + (*N* − 1) × *B*1max, D-137: the earlier bound
left the quiet word out)" becomes "(L2: 3 × *E* + (*N* − 1) × *B*1max; D-137 left the quiet word out, and D-138 the
invalidation event the asked core runs after the wait, whose length is at most *E*)"; in 692 "under L2, 2 × *E* + (*N* −
1) × *B*1max + *D*" becomes "under L2, 3 × *E* + (*N* − 1) × *B*1max + *D* (D-138)"; in 1512 "2 × *E* + (*N* − 1) ×
*B*1max + *D* under L2" becomes "3 × *E* + (*N* − 1) × *B*1max + *D* under L2 (D-138)".

**6. `kernel-interface.md:962` and `1477`: a `Report` unmasks a line whose `irq` is idle or fired (Finding 6).** In 962,
replace "for a line the two operands of its operation 5 claimed (or of the architecture's route" with "for a line the two
operands of its operation 5 claimed, with bit 32 of the first word cleared while the line's `irq` is idle, fired or dying,
so that the rebuild writes the redirection entry masked as the state of the `irq` requires and the second word still names
the destination (D-138; or of the architecture's route". In 1477, replace "the operands of its operation 5 claimed, checked
as at that request" with "the operands of its operation 5 claimed, checked as at that request, with the mask bit as the
reporting node cleared it for an `irq` that is idle, fired or dying".

**7. `kernel-interface.md:267` and G3 (4) at `1078`: a stale chain link returns in a hooked table (Finding 5).** In 267,
replace "until then the tables a change unhooked are linked through their own first word, which an empty table does not
use, in a chain whose head the request (or the entry of the unit request table) holds." with "until then the tables a
change unhooked are linked through their own first word, which is an entry of no root while the table is in the chain, in a
chain whose head the request (or the entry of the unit request table) holds, and the completion that ends the invalidation
clears that word in the same gate call that puts the table on the free list, before it goes there (D-138: without it, a
table hooked again carried a stale link in its first entry, which G3 (4) forbids and which G14's walk reads as an entry of
the next level down)." In 1078, in G3 (4), replace "a non-present entry is written as all zeros;" with "a non-present entry
is written as all zeros (the first word of a table that a change's chain links is a link, not an entry of any root, and the
rule begins for it when it joins the free list, where that word is cleared);".

**8. `kernel-interface.md:795` and `380`: a failed IEC invalidation frees the handle and the vector (Finding 9).** In 795,
replace "At the end of the last request, done or *failed*, the line word is written *free*, unclaimed, the remapping entry
and the vector are free, and the next step removes the capability." with "At the end of the last request the next step
removes the capability, and if every request was answered *done* the line word is written *free*, unclaimed, and the
remapping entry and the vector are free. **If any request was answered *failed*, the vector and its remapping entry are not
freed and the line word is not written *free* (D-138):** the vector stays claimed on its core, so `irq_claim` is `busy` for
it and the handle, which is the core's number and the vector, can be claimed by no other source; the capability is removed
as usual, so the removal ends." In 380, after "`iospace_attach` and every later request on the unit are `busy`", insert
", the vectors whose removal a request of the unit answered *failed* stay claimed for the rest of the boot".

**9. `kernel-interface.md:681`, `677`, `679` and `664`: the lock counts (Finding 8).** In 681, replace "`node_send` takes
10 (the frames' slots and their old next in the derivation list for the anchors, 8; the caller's core; the gate, which
guards the rings and the credits)" with "`node_send` takes 11 (the frames' slots and their old next in the derivation list
for the anchors, 8; the doorbell's notify, whose list of doorbells the new entry joins; the caller's core; the gate, which
guards the rings and the credits)". In 677, replace "and the receive (`recv` less its reply object, which is the same, and
less the gate counted once: 38)" with "and the receive (`recv` less its reply object, which is the same: 39, `recv` holding
no gate)", and the row's 67 with 68. In 679, replace "the segments of the 128 slots of a dying space it examines, 2; the
gate, 1" with "the segments of the 128 slots of a dying space it examines and the sequence word of its first directory
entry, which guards its sweep and its dying mark: 3; the gate, 1", and the row's 387 with 388. In 664, after "the segment
or the thread of a neighbour in a space's list of records or of bound threads;", insert ", and, for `thread_configure`, the
locks of the lists and the message page it leaves — the sequence word of the first directory entry of the old `cspace` and
the segment of the old message page's slot — which it finds by reading the thread it holds;". Do **not** change `recv` or
`task_revoke`: 40 and 194 stand.

**10. `kernel-interface.md:679`, the bound of a removal step when it kills a capability space (missed, item 3 above).**
Either say in 679 that the dying mark of a space the step kills is written and its lock released before the unit's first
try, or replace "32 units of at most 8 (…), 256" with "32 units of at most 9 (an 8-unit that also writes the dying mark of
a `cspace` whose root it removes, under the sequence word of that space's first directory entry), 288" and change the row's
number from 388 to 420.

**11. `kernel-interface.md:1283`: `idle_until` is written on the adjusted clock (Finding 10).** Replace "`idle_until`, the
instant of its next armed timer when it goes idle (the largest value if none), so a core does not have to beat while idle,
and 0 again at its first event after idle" with "`idle_until`, the instant of its next armed timer when it goes idle (the
largest value if none), read on the clock of a development image's stopped time — the timer's instant less the stopped time
in force when it goes idle (D-138) — so a core does not have to beat while idle, and 0 again at its first event after idle".

**12. `kernel-interface.md:1312`, `1746` and `1775`: editions and the watermark's `again` (Finding 11).** In 1312, after
"(it renumbered the chapters of volume 3 cited before from order 325384-086)", insert "except one sentence of [A node of
several cores](#a-node-of-several-cores), which quotes the section on memory ordering from the older edition 253668-032 and
says so there". In 1746, replace "Under variant L2, `Again` while the watermark is ready to return …; `Again` under variant
L2 only, with nothing changed (D-134, D-135)" with "`Again` while the watermark is ready to return and another core of the
node is still in the kernel event it was in at the last destruction, under both variants (D-135, D-137: under L1 a core
reads a slot outside the node lock); `Again` of the rule of tries under variant L2 only, with nothing changed (D-134,
D-135)". In 1775, replace "`Again` is a new result of fourteen calls under variant L2, with nothing changed" with "`Again`
is a new result of fourteen calls under variant L2, with nothing changed, and of one call under both variants, the watermark
of `untyped_retype` that is ready to return".

**13. `kernel-interface.md:80`: the VT-d revision that was read (missed, item 7 above).** Replace "Every section cited from
these four was read again in these editions on 17 November 2026, except those of the Intel SDM, whose edition did not
change." with "Every section cited from these four was read again in these editions on 17 November 2026, except those of the
Intel SDM, whose edition did not change, and the section of VT-d named below that was read in revision 3.2 (D-137)."

**14. `kernel-interface.md:666`, the SDM citation (Finding 11 (a)) — only after the document is opened.** Replace "read in
the older edition 253668-032, §8.2.3.4, not in the edition named above" with "§11.2.3.4" of order 325462-093, once someone
has opened that edition and found the section there; until then correction 12 above is the one to apply, since it needs no
document.

**15. `kernel-interface.md:691`: the idle core of a request (missed, item 8 above).** Replace "an idle core is not asked:
[TLB](#tlb-one-core-and-several)" with "an idle core is asked only to invalidate the kernel's own space, and its event
begins at once: [TLB](#tlb-one-core-and-several), and [Numbers](#numbers) at `CORE_ANSWER_NS`".
