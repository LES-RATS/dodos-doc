# Verification of the review `v3-deepseek.md` (the contract alone, consistency)

Verifier: Claude Opus 5.5, 17 November 2026, working alone.

**What I read.** The brief names `main` at `6e7d8c0`. `main` now stands at
`1d83b8d`, which adds only review files: `git diff --quiet 6e7d8c0 1d83b8d --
architecture decisions` reports no change. Every line number below is therefore
valid for both commits. In `architecture/kernel-interface.md` I read every
passage the findings touch, with its surroundings: lines 84-200, 265-352,
425-482, 543, 595-612, 683-688, 940-1050, 1206, 1262-1283, 1400-1510, 1679,
1715-1800, 1890-1912, 2010-2106 and 2283-2300. For each finding I also searched
the whole file for any sentence that might already settle it (the search terms
are given under each finding). I did not read the remaining lines one by one. I
read decisions D-100 to D-120 in full and searched D-121 to D-140 for the
subjects of the findings. I searched `architecture/kernel.md` for those subjects
and found nothing bearing on them. Where the contract hands a value to `abi/`, I
opened `dodos-kernel` on branch `model` at `6312868` and the reference model in
the same checkout. I changed nothing in any repository.

**Outside facts.** None of the twelve findings rests on a processor,
controller or firmware fact; the author says so too. Finding 6 uses the
14 physical cores of the reference desktop, but that number is the contract's
own (line 1030, D-116 point 4), so I did not open an Intel page for it. No
specification was opened for this report.

**Severity scale used.** *Major*: two careful builders would build different
kernels. *Minor*: a gap or an error that a builder can resolve from other text
or from `abi/`, but should not have to. *Editorial*: wording, notation, or a
figure nothing is sized from.

---

## Finding 1: the "image untyped" in the derivation tree

**Quotes.** All five are exact, apart from bold the author added: line 117
("as descendants of the image untyped"), line 2019, line 2022, line 2024 and
line 2053.

**Replay.**

1. Line 117: "the frames of the start-up state are the exception, as
   descendants of the image untyped".
2. Line 2019: the kept image "is given once, as kept frames (rule 5), and never
   as an untyped". The same line names "an image untyped of one node" only as
   the rejected alternative. Line 2248 lists it the same way, in the table of
   alternatives.
3. Line 2053: "Every start-up capability except the frames made from the
   start-up untyped is the root of its object, at depth 1 … The frames made from
   the start-up untyped … are its children at depth 2 … the copy in slot 11 is a
   child of slot 10, at depth 3."
4. So line 117 names an object that does not exist. It is a remnant of the
   rejected alternative. It is also too broad: the kept frames (slots 13 and 14,
   the frames of the modules, the crash areas, the feedback frames) are
   start-up frames, and line 2053 makes them roots at depth 1.
5. Line 117 also misses one case that line 2053 gives. The start-up copy in
   slot 11 is neither a root nor a frame made from the untyped, so the opening
   clause ("except the capabilities given at start-up, each of which is the
   root capability of its object") still covers it wrongly.

Line 2053 is precise, and line 117 points to it, so a careful builder follows
2053. The author's step 4 ("`cap_revoke` on the start-up untyped then misses
them") assumes a builder who takes 117 over the section it cites. It is
possible, not likely.

**Verdict: real. Severity: minor** (the author says contradiction; I agree, but
the detailed section is right).

**Correction.** Line 117, replace "the frames of the start-up state are the
exception, as descendants of the image untyped (D-110, see [Start-up
state](#start-up-state))" with:

> the frames made from the node's start-up untyped are the exception, as its
> children, and so is the copy in slot 11, a child of slot 10 (D-110, see
> [Start-up state](#start-up-state))

Cost: text only, no state, nothing at run time.

---

## Finding 2: 64 threads and the 96 of the timer bound

**Quotes.** Line 129 and line 603 are exact.

**Replay.** A step of a removal, read as the text defines it:

1. Line 128: per call, "at most 32 units of work are done (a capability
   removed, a thread woken, or one of the undoings …)". A thread woken because
   an object is destroyed is a unit. Line 132 ("Destroying an object wakes every
   thread that waits on it") wakes them one unit each.
2. Line 129: the wake made by the step that *marks a reply object dying* "is not
   counted in the 32 of a step". A walk passes through at most one reply object,
   and a call makes at most 32 walks, so there are at most 32 such uncounted
   wakes.
3. A call therefore wakes at most 32 (counted, among the units) + 32
   (uncounted) = 64 threads. That is the 64 of line 129, and its reading is the
   one the earlier reviews confirmed:
   `reviews/2026-11-14-model-review-3-mistral.md` finding 5 ("32 counted
   removals/wakes **plus** up to 32 uncounted reply wakes") and
   `reviews/2026-11-14-model-review-5-mistral.md` finding 10.
4. The author's main reading (32 × 1 × 1 = 32) leaves out the counted wakes, so
   line 129 is right and its proposed change to "32" would be wrong.
5. Line 603 counts "one for each of its 32 units and for each of the 64 threads
   its reply objects can wake". Reply objects wake at most 32 threads uncounted,
   not 64. Any other wake, a reply object's destruction included, is one of the
   32 units. So 96 counts the 32 counted wakes twice. The tight figure is
   32 + 32 = 64. The author's "other reading" saw this.
6. 96 is still an upper bound, so nothing is unsafe. Nothing is sized from it:
   searching the file for "96" finds only unrelated sizes (lines 1604, 1788,
   1791, 2093).

**Verdict: line 129 refuted; line 603 real (a loose bound with a wrong label).
Severity: editorial.**

**Correction.** Line 603, replace "which puts at most 96 (one for each of its 32
units and for each of the 64 threads its reply objects can wake)" with:

> which puts at most 64 (one for each of its 32 units, a counted wake among
> them, and one for each of the at most 32 threads its reply objects wake
> uncounted)

Optional, for line 129: "so it wakes at most 64 threads: 32 counted among its
units, 32 not". Cost: text only.

---

## Finding 3: the walk "shorter than 192 … the longest one that can be built has 191"

**Quote.** Line 123 is exact.

**Replay.** The rules: a walk moves from a capability to one derived from it
(depth + 1), or from the root of a space to a capability the space holds. A
space holds another space's root only if that root is deeper, and an untyped
only if it is not shallower (line 122). "The next move from an `untyped` is a
derivation" (line 123). The tree is at most 64 deep (line 121). *S* is a space
root and *U* an untyped.

1. On restricted capabilities, the only move that keeps the depth equal is
   *S*(d) → *U*(d). Every other move goes deeper: *U*(d) → *S*(d+1) by retype,
   *U*(d) → *U*(d+1) by derivation, *S*(d) → *S*(d′) with d′ > d.
2. So each depth holds at most two restricted capabilities, in the order *S*
   then *U*: at most 2 × 64 = 128 (*S*1, *U*1, …, *S*64, *U*64). That is the
   first sentence.
3. A walk that hits 128 ends on *U*64. From an untyped the only move is a
   derivation, to depth 65, which line 121 forbids. So a 128-long restricted
   segment has no ordinary segment after it.
4. To hand over to ordinary capabilities, the restricted segment must end on a
   space root that holds an ordinary capability (a space root can hold an
   ordinary capability of any depth, since line 122 limits only space roots and
   untypeds), or on an untyped whose child is an ordinary root. In both cases
   the last depth level holds one restricted capability, not two: at most 127
   (*S*1, *U*1, …, *U*63, *S*64).
5. The ordinary segment only goes deeper by one per move, at most from depth 1
   to 64: 64 capabilities. *S*64 can hold a depth-1 start-up root (for example
   the start-up `thread`), whose copies run down to depth 64.
6. The maximum is max(128, 127 + 64) = **191**. That is what the text says, and
   the walk is indeed shorter than 192.

The author's "nothing forbids reaching both at once" is answered by the
sentence "the next move from an `untyped` is a derivation", read with the depth
limit. No legal tree has a 192-capability walk, so a counter sized at 191
refuses nothing legal. D-103 says "at most 192", which is a looser and
consistent bound.

**Verdict: refuted. Severity: none.** Optional clarity: after "has 191", add
"(a restricted part of 128 ends on an untyped at depth 64, from which no
derivation is possible, so one followed by ordinary capabilities has at most
127)". Text only.

---

## Finding 4: one letter, two quantities

**Quotes.** All are exact: line 90, line 683, line 688 (with ellipsis),
line 1502 and line 2300 (with ellipsis). The other collisions it cites are
real: *L* at line 2024 ("with *L* bytes left") against *L* levels at line 91;
*D* domains at line 1030 against *D* delivery at lines 688 and 2300; *N*
objects at line 603 against *N* cores at line 656. The search also finds *D*
and *E* used as node names at lines 1265 and 1268 ("driver *D*", "driver *E*").

**Replay.** Every use of the event length gives its definition inline:
"*E* = *N* × *H*" appears in lines 683, 688, 1502, 1510 and 2300 themselves. A
reader of line 1502 reads "`CORE_ANSWER_NS` + *E*, *E* = *N* × *H* the longest
kernel event", so the author's step 2 (comparing a time against 512 entries)
does not follow from the text. The collision is real as notation and harms
nothing as a rule. The worst case is *L* at line 2024, a length in a formula
next to *L* levels, which is a value of the machine published in the same
start-up page.

**Verdict: real. Severity: editorial.**

**Correction.** Smallest useful set:
- Lines 683, 688, 1502, 1510 and 2300: "*E* = *N* × *H*" becomes
  "*W* = *N* × *H*", "2 × *E* + *D*" becomes "2 × *W* + *D*", and
  "`CORE_ANSWER_NS` + *E*" becomes "`CORE_ANSWER_NS` + *W*". The letter *W* is
  not used anywhere in the file.
- Line 2024: "with *L* bytes left, the block is 2^min(trailing zeros of *a*,
  floor(log2 *L*))" becomes "with *Q* bytes left, the block is 2^min(trailing
  zeros of *a*, floor(log2 *Q*))". *Q* is not used either.
- *D* and *N* are defined in the sentence that uses them; leave them.

Cost: text only.

---

## Finding 5: "about 5 for 192 handles"

**Quotes.** Lines 1476, 968 and 960 are exact. One misreading: the author says
"each item is three words plus the entry's key", but line 960 makes the key one
of the three words ("three words per item: its key, then …"). This does not
change the count.

**Replay.** Line 960 caps a `Report` at 28 items (85 words, 11 entries), and
D-133 restates it ("a `Report` of 28 items takes the 11 entries"). By line
1476's own formula, ⌈192 / 28⌉ + 1 = 7 + 1 = 8. In fact a `Report` carries "the
key of the next item, or *end*", so the seventh `Report` ends the list and 7
asks suffice; the +1 covers a node with no item. The estimate came in with D-131
(commit `4070b95`), before D-133 fixed the item layout, and it was not
recomputed. Neither proposed harm follows. The cursor holds a node and a key,
not a count (line 1476). The answer reserve is sized by "one `Report` at most is
owed" (line 975), not by the number of asks.

**Verdict: real. Severity: editorial.**

**Correction.** Line 1476, replace "(about 5 for 192 handles: an estimate, not
measured)" with:

> (at most 8 for 192 handles, at 28 items to a `Report`)

Cost: text only.

---

## Finding 6: the size of the beacons

**Quote.** Line 1283 is exact.

**Recomputation.** At *n* = 128, one node beacon is 4,096 + 8 × 128 + 128 / 8 +
16 × 128 = 4,096 + 1,024 + 16 + 2,048 = 7,184 bytes, which rounds up to 8,192.
For 128 slots that is 1,048,576 bytes. Line 1030 gives the reference desktop 14
physical cores, so the core beacons are 14 × 4,096 = 57,344 bytes. The total is
1,105,920 bytes, about 1.1 MB. Counting the 20 hardware threads as cores instead
gives 1,130,496 bytes, still about 1.1 MB. The formula has not changed since it
was written (commit `61f7452`, D-128 and D-129), so 1.5 MB was never the value
of this formula. Nothing in the file reuses the 1.5 MB.

**Verdict: real. Severity: editorial.**

**Correction.** Line 1283, replace "about 1.5 MB for 128 slots on the reference
machine" with:

> about 1.1 MB for 128 slots on the reference machine (two pages per node
> beacon, 14 core beacons)

Cost: text only.

---

## Finding 7: `StartDebug` of 56 bytes, fields of 52

**Quotes.** Lines 2100, 1679 and 2086 are exact. The `StartNode` quote is exact
but sits at line 2087, not 2090.

**Replay.** 4 + 4 + 8 + 8 + 8 + 4 + 4 + 6 × 2 = 52 bytes, as the author
computed. The contract does not say what the remaining 4 bytes are, or where
the pairs start (byte 52 or byte 56). The number of pairs follows from the
entry's length in its `StartEntry` record (line 2072: "`StartEntry` records
(kind, reserved, offset, length)"), so the overrun scenario does not follow:
neither side reads past the entry. The real question is only where the list
starts. `abi/` settles it. In `dodos-kernel/abi/src/start.rs:434-455` (branch
`model`, `6312868`), the comment reads "The fields the contract lists take 52
bytes; the record is 56, so a reserved word ends it", and the struct ends with
`reserved_tail: u32`. The pairs therefore start at byte 56. Line 2283 makes
`abi/` "the reference for values", so the value is settled, but the contract's
own field list disagrees with it by one word.

**Verdict: real (the contract text); the value is settled in `abi/`. Severity:
minor.**

**Correction.** Line 2100, replace "hardware watchpoints of a user thread,
reserved (u16 each); then the ports refused to this node, as pairs of first and
last port (u16 each)" with:

> hardware watchpoints of a user thread, reserved (u16 each); reserved (u32);
> then, from byte 56 to the end of the entry, the ports refused to this node, as
> pairs of first and last port (u16 each)

Cost: text only. `abi/` already matches.

---

## Finding 8: `untyped_retype` and `cspace_grow` when the object does not fit

**Quotes.** Lines 159, 146, 293, 170 and 1900 are exact.

**Replay.** I searched the file for "does not fit", "past the end", "end of the
untyped", "exhausted" and "no_memory". Only `aspace_map` (line 293), the
`iospace` paragraph (line 344, "with the same rules as for an aspace") and
`thread_set_features` (line 725) state a `no_memory`. The rules of
`untyped_retype` (lines 162-178) and the row of `cspace_grow` (line 160) say how
the watermark is aligned and how memory is cleared, but never what happens when
the aligned object would end past the end of the untyped. The author's example
is correct: an 8 KB untyped with its watermark at 4 KB, asked for an 8 KB child
untyped, aligns the start to 8 KB and the end to 16 KB, past the end. No
sentence decides the result.

The reference model does decide it. `dodos-kernel/model/src/caps.rs:416-440`
returns `NoMemory` "if it does not fit". For `untyped_retype` (lines 274-303)
this comes after the depth checks, after `no_slot`, and after the `again` of a
watermark ready to return, and before any clearing. For `cspace_grow`
(lines 352-360) it comes after `no_slot`. So the behaviour is intended, but it
lives in the model and not in the contract, which the model is supposed to
follow.

One claim of the author is wrong: `no_memory` is also reachable through
`thread_set_features` (line 725), not only through the mapping calls. This does
not change the verdict.

**Verdict: real. Severity: minor** (two builders could pick `no_memory` or
`invalid`; the model and the meaning of `no_memory` at line 1900 both point the
same way).

**Correction.**
- At the end of the first bullet of "Rules of `untyped_retype`" (line 164), add:

  > If the new object, at the watermark aligned as above, would end beyond the
  > end of the untyped, the call returns `no_memory` with nothing changed; this
  > state check comes after `no_slot` and after the `again` of a watermark ready
  > to return, and before any clearing.

- In the row of `cspace_grow` (line 160), replace "`no_slot` when the maximum is
  reached" with:

  > `no_slot` when the maximum is reached; then `no_memory` if the segment,
  > aligned on its size, would end beyond the end of the untyped

Cost: one comparison already made by every creation; no new state; nothing per
memory access.

---

## Finding 9: `iospace_map` that asks the unit, with no state check for it

**Quotes.** Lines 348, 1028, 1737 and 1754 are exact.

**Replay.**

1. Line 1028: when a unit reports caching mode 1 or needs write-buffer
   flushing, bit 0 of the flags of the entry `Memory` is set (line 2091 agrees)
   "and every `iospace_map` also asks the unit's role holder to invalidate".
2. Asking the holder is a unit request, whose general rules are at line 1043.
   That line lists what a unit request completes: "the thread that waits for it
   in *waiting for a unit* (a call: `iospace_unmap`, `iospace_attach` and its
   detach, `irq_claim` of a line, a write of remapping entries) or what a step
   completes". `iospace_map` is in neither list.
3. Line 1043 does give one general rule: "A call that finds no free entry
   returns `again` with nothing changed". That covers a full table for any call.
4. Still unsettled: whether `iospace_map` waits for the confirmation; what it
   returns when the unit is found *failed* (and whether the mapping stays);
   whether the mapping is written before or after the request; and where the
   `again` falls among the state checks it inherits from `aspace_map`. The row
   at line 348 says nothing about any of this, and line 1754 lists no unit
   request for `IoSpaceMap`. Line 1770 lists the calls that gained `again` for
   a full unit request table as "`iospace_unmap`, `iospace_attach` and
   `irq_claim`", again without `iospace_map`.
5. The reference model does not implement this path. Searching
   `dodos-kernel/model/src` and `abi/src` for "caching" or for a flag of
   `Memory` finds nothing.

**Verdict: real. Severity: minor**, with a narrow reach. It applies only on
machines that set the flag (units with caching mode 1, or write-buffer
flushing, which in practice means emulated IOMMUs). On such a machine, though,
the call's result is not defined.

**Correction.** Append to the row of `iospace_map` (line 348):

> When bit 0 of the flags of the entry `Memory` is set and the iospace serves
> devices, the call writes the mapping, then asks the holder of the unit's role
> for an invalidation of translations (operation 3, the iospace's domain number)
> by a unit request and waits in *waiting for a unit*. Its last state check,
> after those of `aspace_map`, is `again` with nothing changed if the unit
> request table is full. At the answer, done ends the call with success;
> *failed* ends it with `busy`, the mapping kept, as for a claim
> ([Devices and shared hardware](#devices-and-shared-hardware)).

In the list of line 1043, after "`irq_claim` of a line", add "`iospace_map`
when it asks". Add `iospace_map` to the list of line 1770. The precedent for
"`busy` with the effect kept" is `irq_claim` (line 1041: "then the call ends,
`busy` if any unit was found failed. The irq … stay as the claim wrote them").

Cost: one unit request and one wait per `iospace_map`, only on machines that
set the flag; nothing on a machine whose units report caching mode 0; nothing
per memory access. No new state: it uses one entry of the existing unit request
table and the thread's existing wait. Not checked here: whether write-buffer
flushing needs a different command than operation 3. That is a VT-d fact,
outside this finding, and I did not open it.

---

## Finding 10: `node_watch` calls its `node` argument "the core"

**Quotes.** Lines 1400, 1445 and 1206 are exact.

**Replay.** The row (line 1400) takes "node, index, notify" and requires "`read`
on the node, which must name the caller's node". The order (line 1445) says "the
core (slot, kind, `read`, then that it names the caller's node, `invalid`)". The
checks listed are those of the node capability, and no capability kind `core`
exists. It is a slip of one word. A builder will follow the row, so the two
sentences do not lead to two kernels.

**Verdict: real. Severity: editorial.**

**Correction.** Line 1445: "Order: the core (slot," becomes "Order: the node
(slot,". Text only.

---

## Finding 11: a fault delivered and then dropped leaves no record

**Quotes.** Lines 429, 469 and 482 are exact.

**Replay.**

1. The fault is delivered as a `call` (line 429).
2. The endpoint or the reply object is destroyed, or `thread_cancel` is called
   with wait number 0.
3. Line 469: the thread is left suspended, "with its registers as at the fault,
   and drops the fault".
4. Line 482: "A fault is recorded when it is not delivered", and the fault was
   delivered.
5. So `thread_read_regs` returns a record of 0.

This is not an unsettled case. "Drops the fault" is the rule that refuses the
record, and lines 469 and 482 agree: a delivered fault never becomes a record.
The author's "no rule assigns it a record or refuses one" is answered by the
word "drops". For every fault that executes the instruction again (word 0 is
the faulting instruction, line 437), resuming the thread raises the fault again,
and with no handler it is then recorded (line 430). That is why line 469 says
"The thread is not left running: it would only fault again". The only
information lost is for traps (kinds 5 and 9), whose word 0 is the next
instruction, so a breakpoint hit seen by a handler that then died is not seen
again. Searching the decisions and reviews for "drops the fault" found no
earlier debate of this.

**Verdict: refuted (the text settles the case). Severity: none.** A design
remark for the owners, not a defect: line 429 already keeps the words of a
delivered fault in the thread object, so keeping them as the record at a drop
would cost nothing and need no new state. It would tell a supervisor why a
thread is suspended after its handler died. If the owners want it, line 469
becomes "… and keeps the fault as its record, as if it had not been delivered".

---

## Finding 12: bit 4 of the state word of `sched_read` has no constant in the list

**Quotes.** Lines 543, 1726 and 2283 are exact. Line 1726 sits in "Values to add
to `abi/`" (line 1715), which says of itself that it lists "the values the D-110
groups need". Bit 4 comes from instruction counting (D-118), which is later than
D-110.

**Replay.** The prose of line 543 gives the bit number ("bit 4 counted"). `abi/`
defines it: `SCHED_STATE_COUNTED: u64 = 1 << 4` at
`dodos-kernel/abi/src/lib.rs:848`, tested at `abi/src/tests.rs:550`. So nobody
guesses a number: the contract states it and the reference for values has it.
Only the list at line 1726 is incomplete. It also leaves out the class field
(`SCHED_STATE_HW_CLASS_SHIFT = 8`, `abi/src/lib.rs:850`).

**Verdict: real (the list is incomplete). Severity: editorial.**

**Correction.** Line 1726, after "`SCHED_STATE_LENT = 1 << 3`" add ",
`SCHED_STATE_COUNTED = 1 << 4`". Text only.

---

## On the author's list of what it found sound

I did not re-derive that list; that was not the task. It touches findings 2 and
3 in one place: the author computed "2^20 / 32 = 32,768 calls" correctly, which
uses the same unit counting that makes line 129's 64 right.

---

## Summary table

| # | Finding | Verdict | Severity | Correction in one line |
|---|---|---|---|---|
| 1 | "image untyped" in the derivation tree | real | minor | Line 117: "the frames made from the node's start-up untyped are the exception, as its children, and so is the copy in slot 11, a child of slot 10" |
| 2 | 64 wakes and the 96 timers of a removal step | 129 refuted; 603 real | editorial | Line 603: "at most 64 (one for each of its 32 units, a counted wake among them, and one for each of the at most 32 threads its reply objects wake uncounted)" |
| 3 | Walk bound 191 against 128 + 64 | refuted | none | None needed: a 128-long restricted part ends on an untyped at depth 64, so one followed by ordinary capabilities has at most 127; optional clarifying sentence |
| 4 | *E*, *L*, *D*, *N* used twice | real | editorial | Rename the event length to *W* at lines 683, 688, 1502, 1510 and 2300, and the length at line 2024 to *Q* |
| 5 | "about 5 for 192 handles" | real | editorial | Line 1476: "(at most 8 for 192 handles, at 28 items to a `Report`)" |
| 6 | Beacons "about 1.5 MB" | real | editorial | Line 1283: "about 1.1 MB for 128 slots … (two pages per node beacon, 14 core beacons)" |
| 7 | `StartDebug` 56 against 52 bytes | real in the contract; settled in `abi/` | minor | Line 2100: add "reserved (u32)" and "from byte 56 to the end of the entry" before the port pairs |
| 8 | `untyped_retype` and `cspace_grow` when the object does not fit | real (model decides, contract silent) | minor | Add the `no_memory` sentence to the rules of `untyped_retype` and to the row of `cspace_grow`, ordered as in the model |
| 9 | `iospace_map` with a unit request has no state check | real | minor (machines with caching mode 1 or write-buffer flushing only) | Row 348: write, then a unit request (operation 3) and a wait; `again` last if the table is full; `busy` with the mapping kept if the unit failed; add to lines 1043 and 1770 |
| 10 | `node_watch` "the core" | real | editorial | Line 1445: "the core" becomes "the node" |
| 11 | Delivered then dropped fault has no record | refuted ("drops the fault" settles it) | none | None; optional owner choice to keep the words as the record, at no cost |
| 12 | `SCHED_STATE_COUNTED` missing from the list | real (list incomplete; prose and `abi/` agree) | editorial | Line 1726: add "`SCHED_STATE_COUNTED = 1 << 4`" |
