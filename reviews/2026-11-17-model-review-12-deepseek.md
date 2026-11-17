# Model review 12: the model of pass 20 against the contract, and its tests

Reviewer: DeepSeek. Copy of the model: `/private/tmp/dodos-kernel-review12`,
branch `model`, head `a96ac5b`. Contract read:
`/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md` at `6eb2f4b`,
decisions D-128 to D-139. I never read or edited
`/Users/btw/Documents/repos/dodos-kernel` after the clone.

Baseline before any mutation, on the untouched copy:

    nix develop -c ./verify    -> exit 0, 47 "test result: ok" lines, 2:02 wall

Every mutation below was applied to that same copy with a script that asserts the
replaced text occurs exactly once, then `cargo fmt --all`, then
`nix develop -c ./verify`, then `git checkout -- .`. Nothing was committed.

**Headline.** The removal of L2 is clean: nothing of it is reachable or dead in
`model/src/` or `abi/src/`, no object size or layout in `abi/` moved, and one
test that also held an L1 rule was deleted with it and has no replacement
(finding 3, whose check cannot fail either). Of the 33 mutations I wrote in the
code pass 20 added or changed, 15 leave the suite green (finding 4 and the table
of item 7). The barrier is the weakest new construction: three of its rules
survive mutation (m02, m08, m27).

---

## Findings

### 1. A line the rebuild writes masked still delivers interrupts. Severity: medium.

Contract, D-139 (3) (`decisions/README.md`, D-139): "A `Report` of a line
carries its mask state, and a new holder writes the entry masked unless the line
is unmasked." The `Report` item carries it: `kernel-interface.md:960`, "three
words per item: its key, then for a device ...".

The model writes it and nothing reads it. `model/src/table.rs:151-156` adds
`masked: BTreeSet<u32>`, "The lines whose entry a rebuild wrote masked", written
at `model/src/roles.rs:541-544` (a rebuilt line) and `model/src/units.rs:445`,
`449` (an operation 5 claim, which unmasks). A grep of `model/src/` for `masked`
gives those four writes and no read: no check, no arrival path, no check-in of a
redirection entry consults it. So a level line whose irq is idle, written masked
by a rebuild, still delivers: `Model::interrupt_on` (`model/src/irq.rs:289`)
finds the irq in `self.irqs` and fires it, whatever `unit.masked` says.

The state that shows it: the pass 20 test's own
(`a_report_carries_a_lines_mask_and_the_new_holder_writes_an_idle_line_masked`,
`model/src/scenarios/pass20.rs:520`) leaves `unit.masked` containing 5 and
the line's redirection entry written; an arrival on GSI 5 then still reaches the
notify of the irq, while the contract's entry is masked at the controller
(`kernel-interface.md:793`: "its source is masked at the controller"). No test
asserts the arrival after a rebuild.

Smallest correction: consult the set where a line's arrival is judged — refuse
the arrival for a `gsi` in `self.table.units[role].masked` (or record the mask
bit in `unit.lines` itself) — and add one test: a rebuild writes GSI 5 masked,
an arrival on GSI 5 delivers nothing, an operation 5 claim unmasks it and the
next arrival delivers.

### 2. D-138's re-read of the slot under the lock has no code and no test. Severity: medium.

Contract, `kernel-interface.md:668`: "**Once it holds the lock, the call reads
again the sequence word of each segment its lookup read without it, and if one
has changed it looks the slot up again under the lock (D-138):** so no call acts
on a capability that an event of another core removed between its read and its
lock. (Under L2 the second round of the rule of tries made that check; with L2
gone, no sentence made it.)"

Nothing in `model/src/` implements or records it. The only trace of the sentence
is a comment, `model/src/caps.rs:474-477` ("the lock-free paths reach object
memory before the node lock"), and `abi/src/lib.rs:126-131`, which keeps
`CSPACE_DIRECTORY_BYTES = 16` for the sequence word. There is no sequence word,
no second read and no lookup under the lock in the model — `Model` has no
`lookup` step at all — and the model's own `model/README.md` says so ("Real
concurrency ... the lock-free slot read, its check under the lock ... are not
interleaved with other events"). The consequence is that this half of D-138 is
neither modelled nor checked, so no mutation of it can fail and no test covers
it. It is the one rule of D-138 that pass 20 was asked to add (D-138, "Settled
by the assistant for L1 alone: (1)").

Smallest correction: record the rule as the model records the locks — one
`Step::Lookup(segment)` before the node lock and one `Step::Relookup(segment)`
after it, with a check that every lookup that read a segment without the lock is
followed by a re-read of the same segment in the same event; a test on a node of
two cores that removes a capability from another core's event and reads the two
steps.

### 3. Three `ensure!`s of `check_locks` cannot fire, and the L1 test that guarded them was deleted. Severity: medium.

Contract, `kernel-interface.md:690`: "A kernel event (a call, an interrupt
arrival, a due event of a timer queue, the delivery of a fault, a step of the
recovery reserve) takes it once it has done its lock-free part, below, and holds
it until its exit"; and "The gate lock (G12) is taken inside it, for each gate
call, and is never contended."

`model/src/check/node.rs:272-309` (`check_locks`) ensures "the node lock taken
twice in one event", "the gate lock taken outside the node lock" and "the node
lock held past the exit of an event". None can fail: the trace those checks read
is built by `Model::end_locks` (`model/src/locks.rs:120-146`), which writes
exactly one `Lock(Node)` first, then `Lock(Gate)`/`Unlock(Gate)` inside it, then
`Unlock(Node)` last. The only `Step::Lock(Gate)` that could arrive from elsewhere
would be pushed by a `touch`, and no `touch` remains in `model/src/` (grep: no
`fn touch`, no `Step::Lock(LockId::Gate)` outside `end_locks`).

The test that could have caught a change here was deleted in this pass:
`under_l1_every_event_holds_the_node_lock_from_entry_to_exit_and_the_gate_lock_inside`
and its two checker tests `under_l1_the_gate_lock_outside_the_node_lock_is_reported`
and `under_l1_the_node_lock_held_past_the_exit_is_reported`
(`git diff 04503d5..a96ac5b -- model/src/scenarios/cores.rs
model/src/scenarios/checker.rs`). That is the one test that also held an L1 rule
that left with L2 (item 1). What remains asserts the node lock for one kind of
event only: `a_signal_takes_the_node_lock_only_when_it_wakes_a_waiter`
(`model/src/scenarios/pass20.rs:290-310`) asserts `Step::Lock(LockId::Node)` for
a waking `signal` and its absence for a lock-free one, so a model that took the
node lock for `signal` alone would still pass. I checked this: mutation m27,
which makes `start_barrier` overwrite a request in use, survives (green), and no
mutation of `end_locks` is available to the suite at all.

Smallest correction: restore one test that asserts the whole trace of a plain
call is `[Pay(Lock), Lock(Node), .., Unlock(Node)]` (the deleted
`under_l1_every_event_holds...`, ported to `checker.rs` against `end_locks`), and
feed `check_locks` a hand-made bad trace for the three ensures, as the deleted
`under_l1_the_gate_lock_outside_the_node_lock_is_reported` did.

### 4. Fifteen mutations of mine survive the whole suite. Severity: medium overall; each row of item 7 says what it breaks.

The list is the "GREEN" column of the table of item 7. Each is argued where it
belongs: m16 → finding 1 (a mask nothing reads); m09 → finding 5; m27 → finding 6;
m23 → finding 7; m30, m10, m12, m14, m15 and m20 → finding 8 (cells of the attach
table no test reaches); m25 → the boundary case of finding 9's sentence
(`CORE_ANSWER_NS` exactly 2 × *E* + *D* accepted); m02 → finding 10; m08 →
finding 11; m29 → the wait of an MSI's removal for its answer, which nothing
distinguishes from its absence; m33 → item 5.

### 5. A detach of a device on a failed unit is not `busy`. Severity: low; the code differs from the contract's order.

Contract, `kernel-interface.md:361` (rules of `iospace_attach`, iospace 0): "With
iospace 0, the state is judged in this order (D-139: the detach had no state
check): the unit has failed (`busy`, as for an attach); the attach word is
*pinned* (an attach is in flight: `busy`); the device is attached to another
node's iospace (`denied`); the device is in no header of an iospace of the
caller's node (success without effect); its entry is marked *detaching* (a detach
is in flight: `busy`)."

The model checks it at `model/src/memory.rs:797-799` (`if self.unit_failed(role)
{ return Err(Error::Busy); }`) — and mutation m09, which deletes that check,
leaves the suite green, so no test detaches on a failed unit. Deleting the check
does not just change an error code: the call falls through to `detach()`
(`model/src/memory.rs:913`), which on a failed unit calls `detach_local` and
succeeds, so the device leaves the header and the call answers `done` where the
contract answers `busy`. The smallest correction: a test that fails the unit
(broken unit, `IOMMU_WAIT_NS` past) and detaches, asserting `busy` and the
header unchanged.

### 6. A barrier started while the core's request is in use overwrites that request. Severity: medium.

Contract, `kernel-interface.md:676`: "while the request of its core is in use it
returns `again` with nothing changed, as any call that needs it does."

`model/src/cores.rs:407-409` guards it (`if self.width() == 1 ||
self.cores[at].request_state == RequestState::InUse { return; }`). Mutation m27
deletes the second half and leaves the suite green: on a node of two cores with
the core's request in use (an unmapping in flight), a retype that needs the
barrier replaces `cores[at].request` with the barrier request — the record's
`Completes::Record(cap)` is lost, so `finish_unmapping` never runs and the leaves
of that record are never lowered. No test makes a second barrier request while
another request of the same core is in flight; `a_barrier_in_flight_that_covers_the_epoch_is_not_started_again`
(`model/src/scenarios/pass20.rs:96`) covers the *covered* case, not the *in use*
one. Smallest correction: one test — start a barrier on core 0 (so the request is
in use), make a second untyped ready, retype it, and assert `again` with
`cores[0].request` still the first barrier and `m.check()` `Ok`.

### 7. The due event of a request still adds the stopped time, and no test compares the two clocks there. Severity: low.

Contract, `kernel-interface.md:1660` ("The stopped time (D-137)"): "every instant
that membership and the waits of a node compare is read from the monotonic clock
less the stopped time: ... the instant an invalidation request started, the start
of a wait for the node lock or for a unit (`IOMMU_WAIT_NS` from a submission)".

`sched.rs:618-623` computes the due event of a request as
`r.started + core_answer_ns + stopped_time`, which is the reverse conversion and
deliberate (its comment at `nodes.rs:1757-1761` says the due events of membership
are on the monotonic clock). Mutation m23 drops `+ stopped_time` and the suite
stays green, so nothing tests that the due event of a request falls on the
monotonic instant of `started + CORE_ANSWER_NS` plus the stops already counted.
The pass 20 test `a_request_across_a_stop_is_judged_on_the_clock_less_the_stopped_time`
(`pass20.rs:659`) asserts `membership_now() < started + answer`, which is the
other side of the comparison.

Smallest correction: in that test, after the stop, assert
`k.m.hardware_due_of_the_request() == request.started + answer + stopped_time`
(or drive `Model::watch_own_cores` at that instant and assert the node does not
accuse itself before it, and does after).

### 8. Eight cells of the attach table are reached by no test, and one cell's code differs from the table. Severity: low; see item 3 for the cell-by-cell table.

The cells with no test are: attach asked / *pinned* (m30 green), attach
answered *failed* / *pinned*'s identifier word (m14 green), detach asked / 0 and
detach asked / *pinned* when the pinned attach is another node's (m09 green shows
that no test detaches a device of a failed unit; no test asks a detach of a pinned
word either),
detach asked / *detached*, detach answered done / 0 and / *pinned*, detach
answered *failed* / 0 and / *pinned*, and rebuild / *attached*'s root (m20
green). One cell is reached only by a hand-made answer: detach answered done /
*attached* (the holder refused), which `pass19.rs:124-128` builds by calling
`detach_answered(role, DEVICE, Done)` on an attached word and asserts the word is
unchanged. Mutation m11 (`refused` always false) is caught — but by the assertion
three calls later, `pass19.rs:139`, because removing the device from the header
makes the following detach answer `done` instead of `waits`; the cell's own rule,
"the device stays in the header", has no assertion.

The cell where the code and the table differ: row "detach asked" / *pinned*. The
table (`kernel-interface.md:370`) says "`busy`: an attach is in flight; a step
returns `again`". The model (`model/src/memory.rs:802`) says
`if pinned && self.holds_identifier(key) { return Err(Error::Busy); }` and then
falls through to `let Some(from) = attached else { ... }`
(`memory.rs:805-810`), which for a device pinned by *another* node's attach
answers `denied`, not `busy`. The contract's own order for iospace 0 puts
*pinned* before *denied* (`kernel-interface.md:361`). Smallest correction: drop
the `&& self.holds_identifier(key)` so a pinned word is `busy` for every caller.

### 9. The start-up judges `CORE_ANSWER_NS` against the cores the machine has, not the largest *N* the image supports. Severity: low; older than pass 20.

Contract, `kernel-interface.md:688`: "The machine start-up refuses a
`CORE_ANSWER_NS` not above the longest healthy wait it judges, for the largest
*N* the kernel image supports (entry `Node`), from the values measured for that
image (D-131, D-137, D-138): 2 × *E* + *D*,".

`model/src/boot.rs:746`: `let largest =
u64::from(self.cores_supported.min(self.cores.len() as u32));`. The state that
shows it: `Machine { cores_supported: 64, cores: two physical cores,
hold_ns: 10_000, delivery_ns: 5_000, core_answer_ms: 1 }`. The contract's bound
is 2 × 64 × 10 µs + 5 µs = 1.285 ms, above `CORE_ANSWER_NS` = 1 ms, so the start
must be refused; the model computes 2 × 2 × 10 µs + 5 µs = 45 µs and accepts it
(`answer > held` holds). I did not run this machine through `Model::boot`; the
arithmetic is from the two constants and the code. The line predates pass 20
(`git show 04503d5:model/src/boot.rs:757` has the same `min`), but it is part of
the sentence this pass changed. Smallest correction: `let largest =
u64::from(self.cores_supported);`.

### 10. A stale barrier can lower the barrier epoch. Severity: low; the sequence costs a spurious barrier, not safety.

Contract, `kernel-interface.md:677`: "The core whose acknowledgement completes
the request writes the epoch the request carries into the barrier epoch, under
the node lock, if it is larger."

`model/src/cores.rs:472` writes `.max(epoch)`. Mutation m02 writes `epoch`
unconditionally and the suite stays green. The state that differs: core 0 starts
a barrier carrying epoch 3 (`cores.rs:421` takes `self.kernel_epoch`), a second
destruction raises the kernel epoch to 5 and core 1 starts a barrier carrying 5;
core 1's request completes first (`barrier_epoch = 5`), then core 0's completes
and the mutation writes 3. `return_watermark` (`caps.rs:512`) then finds a
watermark ready at 5 above `barrier_epoch` 3, starts another barrier and returns
`again` where the contract has it return. No test drives two barriers from two
cores, so `barrier_epoch` is only ever raised once per test.
Smallest correction: a test on a node of three cores that completes the two
barriers in that order and asserts `barrier_epoch` stays 5 and the retype
returns `done` at the first call.

### 11. `unmap_block` ignores the barrier's `again`, and no test sees the difference. Severity: low.

Contract, `kernel-interface.md:676`: "A `memory_give` or `memory_split` of a
block whose watermark is ready to return, and a removal step that would destroy
such a block, return the watermark by the same rule first".

`model/src/blocks.rs:253-257` does `if self.return_watermark(object).is_err() {
return Some(false); }`. Mutation m08 replaces it with
`let _ = self.return_watermark(object);` and the suite stays green, including
`the_destruction_of_a_block_whose_watermark_is_ready_to_return_waits_for_the_barrier`
(`pass20.rs:635`), which asserts a `Completes::Barrier` request — and still sees
one, because `return_watermark` is still called and still starts the barrier.
What the mutation changes is that the step goes on to `take_block`
(`blocks.rs:264`) and to `start_request`, which returns `InUse` (`cores.rs:317`)
because the barrier holds the request, so the step ends `again` for the wrong
reason and the block's place is already taken. The test cannot tell the two
apart: it asserts that the untyped still exists, which holds because the words
are written later. Smallest correction: assert `k.m.untypeds[&block].block ==
Some(Block::Run)` after the first `again`, which is false under the mutation.

---

## Item 1: what left with L2, and what left with it that was not L2

**The diff of the tests.** `git diff 04503d5..a96ac5b -- model/src/scenarios/`
removes 31 functions, of which 26 are L2 by name and subject: the rule of tries
and its two rounds (`under_l2_a_failed_try_takes_a_second_round...`,
`under_l2_a_link_changed_by_the_holder...`, `under_l2_an_arrival_whose_try_fails...`,
`under_l2_a_recv_whose_try_fails...`), the escalation and the quiet word
(`under_l2_a_third_again_of_tries_escalates...`,
`an_arrival_on_a_core_that_waits_for_the_quiet_word...`,
`with_the_ordering_operations_no_interleaving_lets_a_core_enter_while_an_escalation_runs_alone`),
the object locks and their order (`under_l2_a_call_takes_its_locks_in_the_order_of_their_kind...`,
`under_l2_a_delivery_wakes_the_receiver_under_the_endpoint_lock...`,
`under_l2_thread_cancel_locks_the_waiting_thread...`,
`under_l2_notify_bind_takes_the_endpoint_then_the_notify...`,
`under_l2_notify_bind_with_endpoint_0...`, `a_second_core_never_takes_a_lock_another_core_holds`,
`deepseek_4_an_untyped_is_guarded_by_its_segments_lock...`), the bound *k*
(`the_bound_k_of_each_call_is_the_contracts`), the count of `again`
(`a_result_other_than_the_again_of_tries_sets_the_count_to_0`, helper
`again_of_tries`), the checker of the orders
(`the_check_refuses_the_orders_that_the_rounds_of_l2_forbid`,
`the_check_refuses_a_lock_order_the_contract_forbids`,
`under_l2_the_gate_lock_before_another_is_reported`,
`under_l2_more_than_k_locks_is_reported`, `under_l2_a_lock_without_its_instruction_is_reported`,
`under_l1_a_lock_of_an_object_is_reported`), the L2 entry word
(`under_l2_a_watermark_returns_only_once_every_other_core_left_the_event_it_was_in`),
the L2 start-up check (`the_start_up_refuses_a_core_answer_ns_below_the_healthy_wait_of_l2...`),
the L2 bound of a call (`the_bound_of_an_escalated_call_is_closed...`) and the
L2 delivery of marks (`a_delivery_ors_its_marks_into_the_receivers_own_word...`).

Replaced, correctly, by pass 20: the watermark test by the four barrier tests;
the two bounds tests by `a_request_is_bounded_by_two_events_and_a_delivery` and
`the_start_up_refuses_a_core_answer_ns_that_leaves_out_the_event_of_the_interrupt`;
the marks test by `a_delivery_writes_its_marks_into_the_receivers_task_alone`; the
epoch test by `a_raise_of_the_kernel_epoch_other_than_at_a_last_destruction_is_reported`.

**The two that held an L1 rule.** `under_l1_every_event_holds_the_node_lock_from_entry_to_exit_and_the_gate_lock_inside`
(left without a replacement: finding 3), and `under_l1_the_gate_lock_outside_the_node_lock_is_reported`
and `under_l1_the_node_lock_held_past_the_exit_is_reported` (checker tests for
L1 rules that still exist; they left with the pool because the pool became
unfailable). Both are findings 3.

**Anything of L2 still in the code.** A grep of `model/src/` and `abi/src/` (not
the tests) for `locked(`, `Locking`, `again_tries`, `entry_orders`, `quiet`,
`contended`, `fn hold`, `touch_`, `LockId::Notify|Endpoint|Task|Own` returns
nothing live: `locks.rs` keeps `LockId::{Node, Gate}` only, `Cost` keeps the
seven costs of L1 (`Interrupt`, `Broadcast`, `IdleWord`, `Request`, `LoadedSet`,
`Lock` and, dropped, nothing else), `Step` keeps `Lock`, `Unlock`, `Epoch`,
`Ready`, `Wait`, `Spin`, `Pay`. `Model::hold` and the scripted second core are
gone from `scenarios/cores.rs` (`node2(locking)` too). Two names could mislead a
reader and are not L2: `self.quiet` at `nodes.rs:1519` is a local word of the
hand-over check ("handed and quiet"), and `Cost::IdleWord` is L1's idle mark and
owes bit (`cores.rs:337`). The `again` that remains in the model is the `again`
of rule 4 (a bounded step), not the `again` of tries.

**The reserved words and `abi/`.** The author's claim, `model/README.md` ("`abi/`
had no value of L2 to keep: the words the contract reserves for it (lock words,
the quiet word, the entry words) are not in `abi/` yet"), is true and nothing in
`abi/` moved: the whole `abi/` diff of pass 20 is two doc comments
(`abi/src/lib.rs:126-131`, `abi/src/machine.rs:56-60`). I compared every size of
the contract's table (`kernel-interface.md:1909-1924`) with `abi/src/lib.rs`:
slot 64 = `SLOT_BYTES`, endpoint/notify/reply/timer 64 = `ENDPOINT_BYTES`,
`NOTIFY_BYTES`, `REPLY_BYTES`, `TIMER_BYTES`, `sched` 256 = `SCHED_BYTES`, task
256 = `TASK_BYTES`, thread 1,024 = `THREAD_FIXED_BYTES`, irq entry 64 =
`IRQ_BYTES`, directory entry 16 = `CSPACE_DIRECTORY_BYTES`. The contract's lock
words fit inside those sizes ("within the sizes of [Object sizes]
(kernel-interface.md:695)"), so no size had to move and none did. `abi/` has no
word for the kernel epoch, the barrier epoch or the two thread bits, which the
contract puts in the node block and the thread's reserved words — that is a gap
of the same kind as the one the README states, and it is not a divergence,
because the contract says "The kernel of version 1 writes none of them, and each
reads 0."

---

## Item 2: the five new constructions

**(a) The barrier of an untyped's watermark.** Contract: `kernel-interface.md:676`
("the request of its core ... with nothing to invalidate and the kernel epoch of
the moment, which asks every other core of the node, idle ones included") and
`:677` (the answering, the acknowledgement, the completion "if it is larger").
Code: `caps.rs:508-528` (`return_watermark`), `cores.rs:405-425`
(`start_barrier`), `cores.rs:432-455` (`answer_pending`), `cores.rs:472` (the
completion). The model matches on: every other core asked, idle ones included
(`cores.rs:410`, `all_cores() & !(1 << at)`, no idle-word short cut, unlike the
invalidation path at `cores.rs:333-343`); `Flush::Nothing` with
`invalidation_on` returning at once (`cores.rs:369-371`); the epoch carried being
the kernel epoch of the moment; the return only once `barrier_epoch >= epoch`;
`again` with nothing changed otherwise; the give, the split and the destruction
of a block returning it first (`blocks.rs:211`, `296`, `254`); one core returning
at once (`caps.rs:479`, `release` never sets `ready` when `width() == 1`).

**Where they differ:** the "if it is larger" of the completion (finding 10); the
"request of its core is in use" guard, which the model has but no test reaches
(finding 6); and the clean mark: mutation m06, which returns the watermark
without the clean mark, is caught, so that part is held — by an assertion on the
watermark through a second retype rather than by a direct one, but held.

**(b) The slot read checked again under the lock.** Contract: `kernel-interface.md:668`.
Code: none. Finding 2. The model has no state where the two differ, because it
has no representation of the rule at all: the smallest correction is a trace
step and a check, not a fix.

**(c) Marks as plain words.** Contract: `kernel-interface.md:1114` ("Marks are
read and written under the node lock (D-138) ... a delivery writes the stamp into
the effective marks of the receiver (its task's word, or its own word if it has
none) ... and a detach writes the task's marks into the thread's own word in the
same event"). Code: `tasks.rs:15-30` (`deliver_marks`: the task's word if
attached, otherwise the thread's), `tasks.rs:96` (`marks = marks`, a plain write
at a detach), `tasks.rs:83` (`|=` at an attach). This is right, and it is held:
mutation m04 (the epoch raised at every destruction) is caught by
`a_thread_detached_by_the_destruction_of_its_task_keeps_its_marks`, and my own
q4/q5 mutations, which drop the detach's write and the delivery's OR, are both
caught (item 8). The invariant the contract states — "The effective marks of a
thread never lose a bit while the thread lives" — holds because a thread's own
word never holds a bit its task's word lacks (an attach ORs the effective marks
into the task, and every write while attached goes to the task). No state
differs; I found none.

**(d) A request bounded by 2 × E + D and the start-up checks.** Contract:
`kernel-interface.md:687` ("a wait for a request lasts at most 2 × *E* + *D*")
and `:688` (the three refusals). Code: `locks.rs:156-168` (`event_with_waits` =
*N* × *H*, `healthy_wait` = 2 × *E* + *D*), `boot.rs:744-761` (`answer > held`,
`stale > answer + event`, `stuck > RECOVERY_PERIOD_NS + answer + event`).
`RECOVERY_PERIOD_NS` is "the reserve's period" (10 ms, `abi/src/machine.rs:421`).
The comparisons are strict, which is the contract's "not above" refused. The
three refusals are held: m24 and m26 (weakening the STUCK/STALE terms) are caught
by `model/tests/boot.rs:597`. Two differences: the *N* the check uses (finding 9)
and `answer >= held` being accepted (m25, green) — the boundary case
`CORE_ANSWER_NS` exactly equal to 2 × *E* + *D*, which the contract refuses and
the model accepts; no test builds a measurement where the two are equal.

**(e) `memory_give`, `memory_split` and the destruction of a block.** Covered
above: the give and the split return the watermark first and the suite holds it
(m07 caught); the destruction step's guard is written but nothing distinguishes
it from its absence (finding 11).

---

## Item 3: the attach word, cell by cell

Contract: `kernel-interface.md:363` (the caption) and the table at `:365-376`,
rows in the order attach asked (367), attach answered done (368), attach answered
failed (369), detach asked (370), detach answered done (371), detach answered
failed (372), iospace destroyed (373), node dead (374), holder dead (375),
rebuild (376). Code: `memory.rs:773-895` (`iospace_attach`), `memory.rs:904-926`
(`detach`), `memory.rs:953-1002` (`attach_answered`), `memory.rs:1013-1053`
(`detach_answered`), `units.rs:578-610` (the answer judged by the word),
`caps.rs:988-1002` (the destruction step), `nodes.rs:1388-1405` (R6),
`roles.rs:553-580` (the kept request), `roles.rs:596-620` (the report).

| Row / state | Contract cell | Model | Reached by a test |
|---|---|---|---|
| asked / 0 | pinned, *n*+1, identifier taken, op 1 | `memory.rs:873-884` | yes (`attach_in_flight`) |
| asked / pinned | `busy` | `memory.rs:848` | **no** (m30 green) |
| asked / attached | success if this root and not *detaching*, else `busy` | `memory.rs:844-850` | yes (`one_request_at_a_time...`) |
| asked / detached | `busy` | `memory.rs:848` | **no** |
| done / 0 | none in flight | `memory.rs:977-999` changes nothing | no (unreachable) |
| done / pinned | as *failed* on pinned | `memory.rs:1002-1028` | **no** |
| done / attached | device enters the header, success | `memory.rs:977-990` | yes (`an_attach_enters_the_header_only_at_its_answer_done`) |
| done / detached | none in flight | falls to `pinned`, nothing | no (unreachable) |
| failed / 0 | none in flight | nothing | no (unreachable) |
| failed / pinned | → 0, *n*−1, identifier free, `busy` | `memory.rs:1002-1030` | yes (`an_attach_answered_failed_on_a_pinned_word...`); the identifier word is **not tested** (m14 green) |
| failed / attached | stays attached, out of the header, `busy` | `memory.rs:996-1002` | yes (`an_attach_the_holder_served...`) |
| failed / detached | none in flight | nothing | no (unreachable) |
| detach asked / 0 | success, nothing changed | `memory.rs:805-810` | partly (`a_detach_answered_failed...` removes a device) |
| detach asked / pinned | `busy` (a step: `again`) | **`denied` for another node's device** (`memory.rs:802`, `805-810`) — finding 8 | **no** (m09 green) |
| detach asked / attached | mark *detaching*, op 2; a second is `busy` | `memory.rs:811-825` | yes (`a_second_detach_while_one_is_in_flight_is_busy`) |
| detach asked / detached | `busy` (a step: `again`) | same as attached, via the header's `detaching` — right while the answer is unconsumed | **no** |
| done / 0, / pinned | none in flight | `detach_answered` would call `detach_local` (a faulty holder only) | no (unreachable) |
| done / attached | mark cleared, device stays, `busy` | `memory.rs:1046-1052` | **no** (m11's true arm unreached) |
| done / detached | → 0, *n*−1, identifier free, leaves, success | `memory.rs:1036-1045` | yes (`one_request_at_a_time...`) |
| failed / attached | stays attached, leaves the header, `busy`, class kept, destruction goes on | `memory.rs:1049-1052` | yes (`a_detach_answered_failed_...`) |
| failed / detached | as done | same arm | no |
| destroyed / 0 | nothing | `caps.rs:993` (no header entry) | yes |
| destroyed / pinned | `again` until the answer | `caps.rs:997-999` | yes (`a_detach_while_an_attach_is_in_flight...`) |
| destroyed / attached | the step asks the detach | `caps.rs:999-1010` | yes (same test) |
| destroyed / detached | `again` until the answer | `detach()` `Again` while detaching | **no** |
| dead / all | R1 then R6: word 0, identifier free | `nodes.rs:1388-1405` | yes (`pass19::r6_clears_the_attach_word_of_a_device_of_a_dead_generation`) |
| holder dead / pinned | the request is sent again with its epoch | `roles.rs:570-580` (kept requests) | yes (pass 19's rebuild tests) |
| rebuild / 0 | no entry; one no report claims is cleared | `roles.rs:596-620` | partly |
| rebuild / pinned | no entry, no report names it, served after | `roles.rs:553-560` (attached only) | yes |
| rebuild / attached | entry from the report if the header holds it | `roles.rs:565` — the root is not checked (m20 green) | the **root** untested |
| rebuild / detached | no entry, served after, answered done | not modelled for a word *detached* | **no** |

Two further remarks. The *detaching* mark is `iommus[iommu].detaching` — one set
of devices per iommu object, which is the unit's, not the iospace header's; the
contract puts the mark in "the device's entry in the iospace header"
(`kernel-interface.md:363`). Nothing in the model can differ, because the mark is
only ever consulted for one device of one unit. And row 376 / *detached* ("the
kept detach is served once the rebuild ends and answered done") has no code: a
unit request table entry of kind `Detach` kept across a rebuild is re-submitted
by `roles.rs:570-580` like any other, so the cell is arguably covered by that
path, but no test builds a detach kept across a rebuild.

---

## Item 4: the smaller items

**Unhooked tables listed in the request, and the link cleared before reuse.**
Contract, D-139 (2) (`decisions/README.md`): "The tables a change unhooks are
listed in the request (at most 2 × (*L* − 1)), not chained through their first
word; the free list's link is cleared before a table is hooked again; a change
that unhooks tables of an iospace is one record." Code: `check/table.rs:466-478`
(the bound, `2 * (self.levels(id) - 1)` per `by`, ensured as "59: more tables
unhooked by one change than its request lists"), `memory.rs:159-205`
(`rehook_by`, the per-record `unhooked` list), `caps.rs:988` (one record).
The bound is held (m21's sibling test
`more_tables_unhooked_by_one_change_than_its_request_lists_are_reported`).
"The free list's link is cleared before a table is hooked again" is a rule about
table words; the model's free list is a vector of addresses with no link word, so
it cannot be modelled or mutated. Nothing untested follows from it beyond that.

**The `Report` of a line with its mask state.** Finding 1: written, never read.

**A handle and a vector retired while a unit is failed.** D-139 (4). Code:
`irq.rs:74-82` (the claim refuses a retired handle), `units.rs:585-591` (a failed
`InterruptCache` retires it), `irq.rs:390` (`handle_of`). Both halves are
held: m17 and m18 are caught by
`a_vector_whose_invalidation_a_failed_unit_did_not_confirm_is_not_claimed_again`.
"its remapping entry" is not held separately: the entry is removed before the
request is sent (`irq.rs:433-453`), so no state shows a stale entry, and nothing
tests that the entry is *not* reused — q3 (removing the `remap.remove`) is caught
by the same test's `!remapped(&m)`, so the entry's removal is held.

**`idle_until` on the clock it is compared on.** D-139 (5); `kernel-interface.md:1660`.
Held: `sched.rs:299-306` writes it less the stopped time, and m22 is caught by
`idle_until_is_written_on_the_clock_less_the_stopped_time`. The comparison side is
held by `check/cores.rs`'s stale rule and by the pass 20 test.

**The stopped time on the fence record and the waits.** `nodes.rs:891-893`
(`let now = self.membership_now();` for the fence record), `nodes.rs:1420`,
`cores.rs:345`, `units.rs:377`, `roles.rs:145`, `roles.rs:580`, `sched.rs:651`.
All the comparisons named in the sentence now read `membership_now()`. The
converse direction — a due event on the monotonic clock — is deliberate and is
the one place the suite does not compare the two clocks: finding 7.

**The removal of an MSI's `irq` as a request.** Contract, `kernel-interface.md:793`
("When its root capability is removed, it is unbound from its notify, its source
is masked at the controller ..."). Code: `irq.rs:404-478` (`msi_removal`: one
`InterruptCache` per unit of the segment, the next step after the answer). Held
in part: `the_removal_of_an_msi_with_remapping_is_a_request_that_clears_its_entry`
fails for the right reason when the entry is not cleared (q3) and when the step
does not wait is green (m29, so the wait for the answer is not tested — a
"step returns `again`" rule of the removal with no test that distinguishes it).

**The invalidation of a line's remapping entry at its removal — what it leaves
untested.** The model masks a line and sends no `InterruptCache` for it
(`irq.rs:348-360`: a line's `entry.source.is_line()` branch never calls
`msi_removal`). So the following have no test and cannot have one until the rule
is modelled: (i) that removing a line's irq on a machine with interrupt
remapping clears its remapping entry before the capability goes, so that a stale
entry cannot deliver an interrupt for a removed line — the very property the
`InterruptCache` request exists for; (ii) that the removal step of a line irq
costs one more unit of the 32 when a unit of the segment is another node's, and
returns `again` until the answer (so a step bound that a line can overrun is
untested too); (iii) that a line's vector whose invalidation a failed unit did
not confirm is retired, which the model checks only through the handle of an MSI
(the handle is per vector, so a line's vector is covered by the same word only if
the rule is reached, and it is not); (iv) that the mask of a line and the
invalidation of its entry are ordered — the model writes `masked` and never sends
the invalidation, so no mutation of their order can fail.

---

## Item 5: the two mutations the author reports as surviving

**m18** (pass 19's `nodes.rs:1688`, "`instants.push(start.since + START_NS);`
removed"). It is no longer the same code: `start_over` (`nodes.rs:1719-1725`) now
carries `!current || confirmed || self.membership_now() >= start.since + START_NS`
and the instant to arm is in `reserve_due` (`nodes.rs:1766`). I replayed the
mutation on the clause that replaced it — dropping the `START_NS` term of
`start_over`, mutation m32 — and it is **caught**:
`scenarios::pass19::a_start_whose_core_never_takes_its_wake_ends_at_start_ns`
(`model/src/scenarios/pass19.rs:394`). So the author's list is out of date for
m18: pass 19 added the test that kills it. The state it would leave (a start
never over, the wake sent every `START_RETRY_NS` for ever on a machine with no
other node to accuse the starter) is now excluded by that test.

**m25** (pass 19's `nodes.rs:1060-1063`, "the `|| self.reclaims.get(&node)
.is_some_and(|r| r.generation != g)` clause removed"; today `nodes.rs:1096-1100`).
I replayed it as mutation m33 and it is still **green** over the whole suite
(`nix develop -c ./verify`, exit 0, 47 `test result: ok`). The state that differs
is reachable and observable, and I did not build it — the argument is from the
code, and I say so:

- `reclaims` is a `BTreeMap<u16, Reclaim>` keyed by *node slot*; the record's
  `generation` is read in exactly one place, `nodes.rs:1098`, the clause under
  test (grep of `model/src/`: `reclaims.get(&node).is_some_and(|r| r.generation
  != g)` and `reclaims[&node].r3`, `.audit`, `.r5`, `.acked` elsewhere — none of
  which looks at `generation`).
- `reclaim_step` (`nodes.rs:1089-1101`) removes the record only when the member
  state is not `Dead` or the record is of an older generation; the record is
  created by `reclaims.entry(node).or_default()` with `generation: g` when the
  reclaim starts. So a node that dies at generation *g*, is started again and
  dies at *g* + 2 keeps the first record with its `r3`, `audit`, `r5` and `acked`
  already set, and the reclaim of the second generation reads them as done: R3
  never pins the grants made to *g* + 2 (`nodes.rs:1136`), R4 never audits
  its blocks (`nodes.rs:1142-1160`), and `audited` (`nodes.rs:1201`) answers
  `true` from the old block list.
- The observable difference is therefore a state, not a side effect:
  `m.sys.node(k).reclaims[&peer].r3 == true` before R3 of the second generation
  has run, and a grant entry `{grantee: peer, generation: g + 2}` still reading
  *granted* while `member(peer)` reads `Fenced`. On the model without the
  mutation the record is dropped when the member reads `Dead` at *g* + 2 and R3
  runs afresh.
- Why the suite misses it: no test drives two successive deaths of one node slot.
  The smallest correction is one scenario in `scenarios/crossing.rs`: a node that
  dies, is started again, takes a grant from a live node, and dies again; then
  assert the grant is pinned and `reclaims[&peer].r3` was false before the step.

---

## Item 6: the siblings of the run-block fault

The fault that was fixed: a removal step on x86-64 in a node of several cores
takes the block (`blocks.rs:266`, `take_block`) before its words are written at
the completion of the request, and the completion `write_freed`s a block the
`untypeds` map no longer has, so checks 11 and 54 read the untyped as an untyped
of the start-up. The fix is `written_block` (`check.rs:157-173`) plus the two
call sites (`check.rs:612-617`, `check/table.rs:339-341`) and the removal of
`self.touch_untyped(object)` from `take_block`.

- **RISC-V.** The same operation reaches the same code: `start_request`
  (`cores.rs:291-345`) has no architecture arm except ARM64's broadcast, so on
  RISC-V a removal step on a node of several cores starts a request and returns
  `again` exactly as on x86-64, and the same `written_block` covers it. No test
  runs it: `the_removal_of_a_run_block_on_two_cores_writes_its_words_at_the_completion`
  (`pass20.rs:395`) builds its node with `Arch::X86_64`. A model that reintroduced
  the fault on RISC-V alone would be caught only by the shared check, which is
  the fix — so the test does not prove the RISC-V path, and its name says "on two
  cores", not "on x86-64". Low severity; the correction is to run the same test
  on `Arch::Riscv64`.
- **ARM64.** The fault cannot arise: `others_hold` (`cores.rs:272-281`) returns
  `false` for ARM64 whatever the space, so the invalidation is complete in the
  call (`cores.rs:303-314`, the broadcast), `start_request` answers `Complete`,
  `write_freed` runs in the call and the block is never forgotten. So an ARM64
  test of the same operation proves nothing about the fix, and the pass 20 test
  is rightly x86-64 only. What is untested is the *other* half of the ARM64 rule:
  a `Flush::Kernel` on ARM64 with several cores always takes the broadcast path,
  including the barrier's own "asks every other core" — which the model gives
  through `start_barrier`, a request, and which is tested
  (`the_barrier_uses_the_request_on_arm64_too`). Consistent.
- **The other calls that unmap from the kernel's own space.**
  `memory_give` (`blocks.rs:196-243`) does the same: `take_block(...,
  Freed::Given(node), false)` then `start_request(Flush::Kernel, Completes::Run)`
  and the words at the completion. It is covered — by
  `a_give_of_a_block_whose_watermark_is_ready_to_return_waits_for_the_barrier`
  (`pass20.rs:110`), which drives the give through `Waits` and then `interrupts()`,
  and by the whole check after every step. `memory_split` does not unmap a run (it
  is a device entry). The destruction of a block from `task_revoke`, a `Revoke`
  step and the destruction of an iospace all go through `unmap_block`
  (`blocks.rs:247-290`), the same path as the fixed test. One sibling I did not
  find a test for: the destruction of a run block reached from a `Revoke` step of
  another node on RISC-V; nothing distinguishes it from the removal step, so it
  is the same coverage as the RISC-V gap above.

---

## Item 7: 33 mutations of mine, in the code pass 20 added or changed

Each: the file and line in the copy, the replacement, the sentence it contradicts
(contract lines of `kernel-interface.md` unless a decision is named), and the
result of `nix develop -c ./verify` after `cargo fmt --all` on the whole suite.
"green" = exit 0 and 47 `test result: ok`; "caught" names the first failure.

| id | file:line | mutation | sentence | result |
|---|---|---|---|---|
| m01 | cores.rs:421 | `Completes::Barrier(self.kernel_epoch)` → `Barrier(0)` | 676, "the kernel epoch of the moment" | caught, `pass20::a_give_of_a_block...` (4 tests) |
| m02 | cores.rs:472 | `.max(epoch)` → `= epoch` | 677, "if it is larger" | **green** (finding 10) |
| m03 | caps.rs:512 | `epoch > self.barrier_epoch` → `>=` | 676, "finds ... at least that value" | caught, `pass20:132` |
| m04 | caps.rs:480 | `if watched && live == 1` → `if watched` | 675, "When the last object of an untyped is destroyed" | caught, `cores:222` |
| m05 | caps.rs:479 | `let watched = self.width() > 1` → `true` | 676, "On a node of one core the watermark returns at once" | caught, `pass20:81` |
| m06 | caps.rs:525 | the clean mark not returned | 676, "and the clean mark with it" | caught, `pass20:56` |
| m07 | blocks.rs:211 | the give's `return_watermark(object)?` removed | 676, "A memory_give ... return the watermark by the same rule first" | caught, `pass20:127` |
| m08 | blocks.rs:255 | the destruction's `is_err() { return }` → `let _ =` | 676, "a removal step that would destroy such a block" | **green** (finding 11) |
| m09 | memory.rs:797 | the detach's failed-unit `busy` removed | 361, "With iospace 0 ... the unit has failed (busy)" | **green** (finding 5) |
| m10 | memory.rs:908 | `detach`'s *detaching* guard removed | 794, "a device whose entry is already detaching is not asked again" | **green** |
| m11 | memory.rs:1046 | `refused` → `false` | 371 / *attached*, "the device stays in the header" | caught, `pass19:139` |
| m12 | memory.rs:1036 | `detached` without the root test | 794, "only if the word reads detached with the root the entry names" | **green** |
| m13 | memory.rs:977 | `Done && attached` → `attached` | 369 / *attached*, "the device stays out of the header" | caught, `pass20:444` |
| m14 | memory.rs:992 | the identifier word not written free | 369 / *pinned*, "the identifier word free, unclaimed" | **green** |
| m15 | memory.rs:986 | `pinned` without the root test | 363, judged "by the word as it reads then" with the root | **green** |
| m16 | roles.rs:615 | `unmasked` without `!irq.removing` | D-139 (3), the mask state of a report | **green** (finding 1) |
| m17 | irq.rs:79 | a retired handle claimed again | D-139 (4) | caught, `pass20:585` |
| m18 | units.rs:591 | `retired.insert` removed | D-139 (4) | caught, `pass20:577` |
| m19 | memory.rs:818 | the *detaching* mark not set at the ask | 361, "Then its entry is marked detaching" | caught, `pass20:465`, `686` |
| m20 | roles.rs:565 | a rebuilt attach without the root test | 376 / *attached* | **green** |
| m21 | roles.rs:543 | a rebuilt masked line takes no mask | D-139 (3), "a new holder writes the entry masked" | caught, `pass20:543` |
| m22 | sched.rs:304 | `idle_until` on the monotonic clock | 1660, "a core's idle_until ... on this clock" | caught, `pass20:640` |
| m23 | sched.rs:623 | the request's due event without the stopped time | 1660, "the instant an invalidation request started" | **green** (finding 7) |
| m24 | boot.rs:756 | the STUCK term → `stuck > 0` | 688, "STUCK_NS not above the reserve's period + CORE_ANSWER_NS + E" | caught, `boot:597` |
| m25 | boot.rs:763 | `answer > held` → `>=` | 688, "refuses a CORE_ANSWER_NS not above 2 × E + D" | **green** |
| m26 | boot.rs:756 | the reserve's period dropped from STUCK | 688 | caught, `boot:597` |
| m27 | cores.rs:407 | the "request in use" guard removed | 676, "while the request of its core is in use" | **green** (finding 6) |
| m28 | cores.rs:448 | a request completes at the first acknowledgement | 677, "the acknowledgement completes the request" | caught, `pass20:49` |
| m29 | irq.rs:412 | the MSI removal proceeds while the invalidation is in flight | 793, the step after the answer | **green** |
| m30 | memory.rs:848 | a second attach on a *pinned* word allowed | 367 / *pinned*, `busy`: an attach is in flight | **green** |
| m31 | caps.rs:997 | the destruction does not wait for an attach in flight | 373 / *pinned*, "again until the attach's answer" | caught, `pass20:497` |
| m32 | nodes.rs:1724 | `start_over` without the `START_NS` term (review 10's m18) | 1411, "at most START_NS" | caught, `pass19:394` |
| m33 | nodes.rs:1098 | the reclaim's generation clause (review 10's m25) | 1357 and D-131, the reclaim of a generation that is over | **green** (item 5) |

15 green of 33: m02, m08, m09, m10, m12, m14, m15, m16, m20, m23, m25, m27, m29,
m30, m33.

Four further mutations of mine did not compile and were replaced rather than
counted (a `result` left unused in `attach_answered`/`detach_answered`, a `root`
left unused in `rebuilt_attach`, a `()` against `bool` in the rebuilt line's
mask); the table above has one mutation per id that compiled and ran.

---

## Item 8: fifteen of the 31 tests of `model/src/scenarios/pass20.rs`

The file has 31 `#[test]`s (`grep -c '#\[test\]' model/src/scenarios/pass20.rs`).
For each test below I broke the rule its name states, by a mutation of the code
of that rule (never of the test), and ran the test alone
(`cargo test -p dodos-model --lib scenarios::pass20::<name>`), except where the
whole-suite run of item 7 already contains it.

| test | mutation | result |
|---|---|---|
| `a_watermark_ready_to_return_returns_only_after_a_barrier_asks_every_other_core` | m28 (a request completes at the first acknowledgement) | fails at `pass20.rs:49`, `assert!(k.m.barrier_epoch < epoch)` — its subject |
| `on_a_node_of_one_core_the_watermark_returns_at_once` | m05 (`watched` always true) | fails at `pass20.rs:81`, `assert_eq!(k.m.untypeds[&untyped].ready, None)` |
| `the_barrier_uses_the_request_on_arm64_too` | m01 (the barrier carries 0) | fails in the same run as the barrier, one of the four tests m01 breaks (`pass20.rs:56` is the watermark test's line, not this one) |
| `a_give_of_a_block_whose_watermark_is_ready_to_return_waits_for_the_barrier` | m07 (the give does not return the watermark) | fails at `pass20.rs:127`, `assert_eq!(k.call(k.t, give.clone()), Err(Error::Again))` |
| `a_thread_detached_by_the_destruction_of_its_task_keeps_its_marks` | q4 (`tasks.rs:96`, the detach's write removed) | fails at `pass20.rs:369`, `assert_eq!(k.m.threads[&thread].marks & untrusted, untrusted)` |
| `a_delivery_writes_its_marks_into_the_receivers_task_alone` | q5 (`tasks.rs:26`, the delivery's OR removed) | fails at `pass20.rs:198`, `assert_eq!(k.m.tasks[&task].marks & untrusted, untrusted)` |
| `an_attach_enters_the_header_only_at_its_answer_done` | q1 (`memory.rs:979`, the header push removed) | fails at `pass20.rs:396`, `assert_eq!(m.sys.node(0).census().devices, 1)` |
| `an_attach_the_holder_served_and_the_unit_did_not_confirm_stays_attached_out_of_the_header` | m13 | fails at `pass20.rs:444`, `assert_eq!(m.sys.node(0).census().devices, 0)` |
| `a_second_detach_while_one_is_in_flight_is_busy` | m19 (the *detaching* mark not set) | fails at `pass20.rs:686`, `assert_eq!(m.call_by(0, other, detach), Err(Error::Busy))` |
| `a_detach_while_an_attach_is_in_flight_is_busy_and_the_destruction_waits_for_it` | m31 (the destruction does not wait) | fails at `pass20.rs:497`, `assert_eq!(m.call_by(0, other, CapDelete(IOSPACE)), Err(Error::Again))` |
| `a_report_carries_a_lines_mask_and_the_new_holder_writes_an_idle_line_masked` | m21 (the rebuild writes no mask) | fails at `pass20.rs:543`, `assert!(unit.masked.contains(&5))` |
| `a_vector_whose_invalidation_a_failed_unit_did_not_confirm_is_not_claimed_again` | m17 (a retired handle claimed again) | fails at `pass20.rs:585`, `assert_eq!(m.call(0, again), Err(Error::Busy))` |
| `the_start_up_refuses_a_core_answer_ns_that_leaves_out_the_event_of_the_interrupt` | q2 (`locks.rs:166`, `mul(1)` for `mul(2)`) | fails at `pass20.rs:259`, `assert_eq!(Model::boot(&machine).err(), Some(Refusal::Floors))` |
| `the_removal_of_an_msi_with_remapping_is_a_request_that_clears_its_entry` | q3 (`irq.rs:441`, the `remap.remove` removed) | fails at `pass20.rs:605`, `assert!(!remapped(&m))` |
| `idle_until_is_written_on_the_clock_less_the_stopped_time` | m22 | fails at `pass20.rs:640`, `assert_eq!(idle_until, k.m.hardware(1).unwrap() - 7 * MS)` |

That is 15 tests of the 31, each failing at an assertion that names the same
subject as the test's name. Two remarks on the ones I did not take:
`a_barrier_epoch_beyond_the_kernel_epoch_is_reported` and
`a_raise_of_the_kernel_epoch_other_than_at_a_last_destruction_is_reported` are
checker tests and are exercised by the pass 20 checks themselves;
`the_removal_of_a_run_block_on_two_cores_writes_its_words_at_the_completion` is
the regression test of the fixed fault and is exercised by the whole suite on
every mutation of `written_block`'s call sites that the check reaches.

---

## What I checked and found correct

- `abi/` did not move in pass 20 (two doc comments only), every object size
  matches the contract's table, and no reserved word needed a size.
- Nothing of L2 is reachable or dead in `model/src/` or `abi/src/`: no
  `locked(`, no `Locking`, no tries, no `again` count, no quiet word, no entry
  word, no bound *k*, no `Model::hold`, no scripted second core.
- The barrier in its main shape: every other core asked, idle ones included, no
  idle-word short cut, `Flush::Nothing`, the epoch of the moment, the return only
  after a complete barrier, `again` unchanged otherwise, one core at once, and
  the give, the split and the block's destruction ordering it first (m01, m03,
  m04, m05, m06, m07 caught).
- Marks as plain words: the delivery into the effective marks alone, the detach's
  plain write, the attach's OR (m04, q4, q5 caught).
- The start-up checks of `CORE_ANSWER_NS`, `STALE_NS` and `STUCK_NS` against
  2 × *E* + *D*, `answer + *E*` and the reserve's period + `answer + *E*`
  (m24, m26 caught), and `*E*` = *N* × *H*, *D* as the delivery.
- The attach word's ten events in their main cells: the entry only at the answer
  done, the device out of the header on a failed attempt, the mark *detaching*
  and one request per device, the failed detach keeping the word and taking the
  device out of the header, the destruction waiting for an attach in flight, the
  rebuild writing no entry for *pinned*, the identifier refused at a retired
  handle (m13, m17, m18, m19, m21, m31, q1, q3 caught).
- The tables unhooked listed per change within 2 × (*L* − 1), and one record per
  change.
- `idle_until` on the clock of membership, and the fence record, the waits and
  the request's start on the same clock.
- The removal of an MSI's `irq` as a unit request, with its remapping entry
  cleared before the request.
- `model/src/scenarios/pass20.rs`: 15 of its 31 tests fail for the reason their
  name says, at an assertion of that subject.

## What I did not check or could not run

- The full `verify` under `DODOS_SEED` explorations with several seeds; I ran the
  suite as `./verify` runs it, once per mutation, and the explorations once each.
- Finding 9's machine (the `min` in `boot.rs:746`): I did not boot that machine
  through `Model::boot`; the arithmetic is from the constants.
- Item 5's m33: I did not build the two successive deaths of one node; the state
  and the reason the suite misses it are argued from the code, as marked.
- RISC-V and ARM64 paths for the run-block removal (item 6) beyond reading
  `others_hold` and `start_request`; no test on those architectures.
- The `Report`'s and the ring's word-level layouts against `abi/` (the mask bit is
  bit 32 of the first word of a line item, `rings.rs:65-67`); I checked the
  model, not the `abi/` bit assignment of that item.
- `abi/src/tests.rs` and `abi/tests/review6.rs`: no test of the reserved words'
  being written as 0, because `abi/` has no such word.
