# Review of pull request 3, lot D (deepseek)

Repository `/private/tmp/dodos-pr3-final`, branch `model`, head `6312868`
("Model: the thirteenth contract review and the twelfth model review (pass
21, D-140)"). The pull request is `origin/main..HEAD`; everything in it is
new. I read `AGENTS.md`, `model/README.md`, the skills `dodos-rust` and
`rust-1-100`, and every line of my lot:

`model/src/check.rs`, `model/src/scenarios/checker.rs`,
`model/src/check/cores.rs`, `model/src/check/debug.rs`,
`model/src/scenarios/explore.rs`, `model/src/check/machine.rs`,
`model/src/check/memory.rs`, `model/src/scenarios/mod.rs`,
`model/src/check/node.rs`, `model/src/check/sched.rs`,
`model/src/check/table.rs`, `model/src/check/tasks.rs`,
`model/src/check/tests.rs`,

and as much of `model/src/lib.rs`, `cores.rs`, `memory.rs`, `sched.rs`,
`table.rs`, `units.rs`, `system.rs`, `grants.rs` and `abi/src/*.rs` as I
needed to judge what each check reads.

The work copy is `/private/tmp/dodos-pr3-v2-D-deepseek` (the shared clone is
untouched). The tests of this report are one new file,
`model/src/scenarios/probe_d.rs`, plus one line `mod probe_d;` in
`model/src/scenarios/mod.rs`. The command, in the work copy:

    nix develop -c cargo test -p dodos-model --lib probe_d -- --nocapture

and its output is quoted under each finding. Baseline:
`nix develop -c cargo test -p dodos-model --lib` passes 523 tests before my
file is added (78.62 s), so no finding below is a test that was already
failing.

The whole check is `Model::check` (`model/src/check.rs:287`) and
`System::check` (`model/src/check/machine.rs:23`), run after every event by
the harness (`N::call`, `S::call`, `S::run_by` in `scenarios/mod.rs`).

---

## D1 — a core runs a thread that holds no context: nothing reports it

**Severity: likely exploitable.** **Attacker: a hostile kernel (the kernel
of the node itself; a user program that makes it schedule).**

`model/src/check/sched.rs:161-170`, `check_choice`:

```rust
            let pending = core.ipis.contains(&crate::Ipi::Reschedule);
            ensure(core.running == chosen || pending, "46: running context")?;
            if let Some(thread) = core.thread {
                ensure(running.insert(thread), "46: a thread on two cores")?;
                let marked = self.threads.get(&thread).is_none_or(|t| t.leaving);
                let aspace = self.threads.get(&thread).and_then(|t| t.aspace);
                ensure(
                    pending || marked || aspace.is_some_and(|a| !self.marked(a)),
                    "46: address space of the running thread",
                )?;
            }
```

`core.running` is the context the core runs and `core.thread` the thread
(`cores.rs:116-119`: "the thread it runs on it (the holder at the choice)").
The first `ensure` checks the context against the queues; the second checks
the thread's address space. **No invariant says the thread is the holder of
the context.** The rule 46 of the file's own doc ("the running context of
each core is its choice ... the thread it runs ... has an address space that
is not dying") is therefore two independent checks, and a state where they
speak of different threads passes.

What the attacker gains: with `core.thread` naming any healthy thread, the
"address space of the running thread is not dying" rule no longer applies to
the thread that really runs (the holder), and `Model::load_root`
(`cores.rs:540-546`) derives the loaded root from `core.thread`, so the core
runs the holder's context on the *other* thread's address space — which is
D2 from the other side. The context's budget is charged to one context while
another thread executes, so the admitted sum of rule 42 no longer bounds
what runs.

Steps:

1. Boot a node of two cores (`N::on(&one_node(Arch::X86_64, 2))`); the first
   thread runs on core 0, and `cores[0].running` is its context.
2. Make a second thread, configured, with no context of its own.
3. Set `cores[0].thread` to that second thread.
4. `Model::check()` returns `Ok(())`.

Proof: `deepseek_d1_a_core_runs_a_thread_that_holds_no_context`
(`model/src/scenarios/probe_d.rs`), which asserts the premise
(`scheds[&running.0].home == Some(k.t)`) and then `assert_eq!(k.m.check(),
Ok(()))`. Output:

    test scenarios::probe_d::deepseek_d1_a_core_runs_a_thread_that_holds_no_context ... ok

A check that would close it: in `check_choice`, `core.thread` must equal
`core.running.and_then(|(context, _)| self.holder(context))` (with the
caveat of a context whose holder is gone, which rule 41 already handles).

## D2 — a core loads an address space that is not the running thread's

**Severity: likely exploitable.** **Attacker: a hostile kernel; the effect
is a user thread executing on another party's translations.**

`cores.rs:540-546`, the rule the model implements (G7):

```rust
    /// The root a core loads for the thread it runs (G7), through the gate:
    /// its address space, which enters the space's set of cores that loaded
    /// its tag; and what the core caches of it. An idle core runs on the
    /// kernel's root.
    pub(crate) fn load_root(&mut self) {
        let at = *self.at;
        let space = self.cores[at]
            .thread
            .and_then(|t| self.threads[&t].aspace)
            .filter(|&a| !self.dying(a));
        self.cores[at].loaded = space;
```

`Model::cores[..].loaded` is read by exactly one invariant,
`model/src/check/node.rs:113`:

```rust
                    let usable = core.loaded == Some(space) && !core.silent;
```

and by no other check (I grepped `loaded` over `check.rs` and `check/`: that
one line). So nothing says the loaded root is the running thread's address
space, although the TLB rule of this very file ("a translation a core may
still hold that its space no longer holds ... is allowed only while a
request asks that core for it") takes `usable` from it: the check treats a
space as usable by a core on the strength of `loaded` alone.

What the attacker gains: a thread of address space A runs while B is loaded,
so every cached translation the check reads as "usable" is B's, and the
thread's stores and loads go through the frames of another party. The rule
that should forbid it (`load_root`, G7) has no invariant behind it.

Steps:

1. Boot a node of two cores; the first thread runs on core 0 with
   `cores[0].loaded = Some(<start-up aspace>)`.
2. Take a second address space of the node (`untyped_retype` kind `ASpace`).
3. Set `cores[0].loaded = Some(<that space>)`.
4. `Model::check()` returns `Ok(())`.

Proof: `deepseek_d2_a_core_loads_another_threads_space`, which asserts
`assert_ne!(k.m.cores[0].loaded, Some(other))` before the edit and
`assert_eq!(k.m.check(), Ok(()))` after. Output:

    test scenarios::probe_d::deepseek_d2_a_core_loads_another_threads_space ... ok

A check that would close it: `load_root`'s own expression as an invariant —
"the root a core has loaded is the address space of the thread it runs, or
none when that thread has none or its space is dying".

## D3 — the domain numbers of an iospace are covered by no invariant

**Severity: hardening.** **Attacker: a device, or a node that allocates
iospaces (a domain number kept, or shared, between two iospaces of one
unit makes the unit's translations one party's for two).**

`model/src/check/memory.rs:159-164`, the only place in the check that
mentions domains:

```rust
            let domains: BTreeSet<_> = unit.attached.values().collect();
            let limit = self.machine.iommus.get(unit.unit).map_or(0, |u| u.domains);
            ensure(
                domains.len() as u32 <= limit,
                "39: domain numbers of a unit",
            )?;
```

`unit.attached` is the machine table's device → iospace map; the set is of
*iospaces*, so the check counts how many iospaces a unit serves, and never
looks at `Model::domains` (`lib.rs:1048`: "the domain number of each iospace
that serves devices, on its unit, taken from this node slot's range at its
first device and freed with its last"). Nothing checks:

- that a domain number is kept only while the iospace serves a device
  (`memory.rs:892` inserts it at an attach, `memory.rs:1116-1128`
  `detach_local` removes it with the last device);
- that a domain number lies in the node's range (`memory.rs:1102-1111`,
  `domain_range`);
- that two iospaces of one unit do not share one (`free_domain` picks a
  number no *other* iospace of that unit uses, and nothing verifies the
  result).

Steps:

1. Boot a node of two cores.
2. Take an `IoSpace` object; it serves no device (`iospaces[&space]` is
   empty).
3. Insert a domain number for it that is outside the node's range — on a
   machine of one node whose unit has 256 domain numbers, the range is
   1..=254, so `m.domains.insert(space, 255)`, and the test asserts
   `!k.m.domain_range(0, k.m.node).contains(&255)`.
4. `Model::check()` returns `Ok(())`.

Proof: `deepseek_d3_a_domain_number_with_no_device_is_unchecked`. Output:

    test scenarios::probe_d::deepseek_d3_a_domain_number_with_no_device_is_unchecked ... ok

This is a hole the model cannot itself reach today (I tried the paths that
could leak one — an attach that fails after `self.domains.insert` — and the
unit request table is refused before the insert, `memory.rs:876-878`, so the
model is right and the check is blind). It matters because `iospace_attach`
also writes the domain into the *unit's* context entry
(`units.rs:459`), so a wrong number here is a wrong number in hardware.

## D4 — the check of the scheduling panics on a lend whose receiver is dead

**Severity: hardening.** **Attacker: a hostile kernel; the effect is that
the whole check of the model dies instead of reporting invariant 44.**

`model/src/check/sched.rs:40` and `:47-50`:

```rust
        let runs = |thread: &ObjId| Self::runnable_thread(&self.threads[thread]);
...
            let top = sched.chain.last().and_then(|reply| self.lends.get(reply));
            let holder = home.or(top.map(|&(_, receiver)| receiver));
            let dying = self.marked(id);
            let eligible = sched.configured && !dying && holder.is_some_and(|h| runs(&h));
```

`runs` indexes `self.threads[thread]`, which panics for a thread that is not
live. `holder` comes from `self.lends` (the receiver of the top lend) when
the home does not run, and the rule that a lend "names ... a live receiver"
is invariant 44, checked *later* in the same function
(`check/sched.rs:110-120`). So the state that 44 exists to reject kills the
check before 44 can report it.

Steps:

1. Boot a node of two cores, whose first thread runs.
2. Take a `Reply` object; push its id into the first thread's context
   `chain`; insert `m.lends[reply] = (context, ObjId(9999))` — a receiver
   that is not a thread of the model.
3. Suspend the first thread so its context has no runnable home.
4. `Model::check()` panics.

Proof: `deepseek_d4_the_check_panics_on_a_lend_of_a_thread_that_is_not_live`
catches the panic and asserts its message. Output:

    thread 'scenarios::probe_d::deepseek_d4_the_check_panics_on_a_lend_of_a_thread_that_is_not_live' panicked at model/src/check/sched.rs:40:72:
    no entry found for key
    test scenarios::probe_d::deepseek_d4_the_check_panics_on_a_lend_of_a_thread_that_is_not_live ... ok

The same test asserts first that the same state with a runnable home returns
`Err("44: lend")` — `assert_eq!(k.m.check(), Err("44: lend"))` — because the
lend's receiver is then never read (`holder` takes the home). That is what
the check should say of the state after the suspend too, and it is the
report the check panics out of.

## D5 — the check of the debug area panics on a ring whose next sequence is 0

**Severity: hardening.** **Attacker: a hostile kernel (it owns its debug
area, `areas` is in the machine table), or a boot image with any values.**

`model/src/check/debug.rs:17-24`, `ring_holds`:

```rust
fn ring_holds(ring: &[TraceEntry], next: u64, entries: u64) -> bool {
    let placed = ring.iter().enumerate().all(|(index, entry)| {
        entry.seq == 0
            || (entry.seq < next
                && entry.seq + entries >= next
                && (entry.seq - 1) % entries == index as u64)
    });
    let last = next == 1 || ring[((next - 2) % entries) as usize].seq == next - 1;
    next >= 1 && placed && last
}
```

For `next == 0`, `next == 1` is false, so `(next - 2)` is evaluated: 0 − 2 on
a `u64`. The function is documented to judge invariant 88 and the guard
`next >= 1` is only conjoined *after* the arithmetic.

Steps:

1. Boot a node of two cores.
2. Set the first core's debug area's kernel ring next sequence to 0:
   `Arc::make_mut(&mut m.table.crash).areas[0].next_kernel = 0`.
3. `Model::check()` panics instead of reporting 88.

Proof: `deepseek_d5_the_check_panics_on_a_ring_whose_next_sequence_is_zero`.
Output:

    thread 'scenarios::probe_d::deepseek_d5_the_check_panics_on_a_ring_whose_next_sequence_is_zero' panicked at model/src/check/debug.rs:23:35:
    attempt to subtract with overflow
    test scenarios::probe_d::deepseek_d5_the_check_panics_on_a_ring_whose_next_sequence_is_zero ... ok

In a release build there is no overflow panic: `(0u64 - 2) % entries` wraps to
an index inside the ring, `ring[..].seq == next - 1` is false, and the
function returns false as the `next >= 1` of the last line intends — so the
panic is the debug build's, which is the build `verify` and the tests run
(`cargo test`, unoptimized). The guard belongs before the subtraction:
`next >= 1 && (next == 1 || ring[((next - 2) % entries) as usize].seq == next - 1)`.

## D6 — the checker's test of G6 cannot fail for G6

**Severity: hardening.** **Attacker: none; the cost is a test that would stay
green with the G6 check wrong or deleted, in the file that exists to make
exactly that impossible.**

`model/src/scenarios/checker.rs:539-545`, the test
`a_grant_freed_while_its_holder_translates_to_it_is_reported`:

```rust
    let report = m.sys.check().expect_err("spoiled");
    assert!(
        report.ends_with("G6: a grant freed while its holder translates to it")
            || report.contains("58"),
        "{report}"
    );
    let _ = Member::new;
```

The file's header says: "for each invariant of a node of several cores and
of the whole machine ... a valid state spoiled in one place, and the check's
report. A check that cannot fail is caught here." The second arm of this
disjunction is the one that always fires: the spoiled use entry counts a leaf
under no grant of its own, so node 1's own check reports
`58: leaves of a use entry` (`model/src/check/table.rs:433`) before
`System::check` reaches `check_grants`, and the assertion is satisfied by
that. A reader is told that G6 is guarded by this test; it is not.

Steps:

1. Build the state the test builds: `S::two()`, then a use entry in
   `table.uses[1]` with `leaves: 1` and the granter's grant absent.
2. Ask for the report.
3. The report is `node 1: 58: leaves of a use entry`, not G6.

Proof: `deepseek_d6_the_g6_test_reports_a_use_entry`, which asserts that
exact string. Output:

    test scenarios::probe_d::deepseek_d6_the_g6_test_reports_a_use_entry ... ok

I did not find this hole unguarded elsewhere: `scenarios/pass18.rs:564`,
`a_grant_freed_while_an_unfenced_holder_translates_to_it_is_reported_by_g6`,
reaches G6 the intended way (an unfenced node whose own check no longer runs
still holds a translation under a grant) and asserts the message exactly. So
the cost is a misleading test and a hole in the file's own promise, not an
unproven check. The repair is D7 below, or the message asserted alone on
pass18's route, and the two tests then differ in what they spoil.

## D7 — (proof, not a defect) a shorter state that reaches G6

`model/src/check/machine.rs:166-177`, `check_grants`:

```rust
                let entry = table.grants[used.granter as usize].get(&used.grant);
                let held = entry.is_some_and(|e| e.serial == used.serial && e.grantee == slot);
                ensure(held, "G6: a grant freed while its holder translates to it")?;
```

I wrote the state D6's test was meant to build, on one node that *does* run
and whose own check passes: the only leaf `check_table` counts into a use
entry without requiring a grant beside it is the branch for a record
*unmapping* of a remote object (`model/src/check/table.rs:277-285`), which
counts `m.count` leaves and asks nothing about the grant. A record stays
*unmapping* until its invalidation completes (D-131), so this is a state of
the model.

Steps:

1. `S::two()`; `pass17::granted_to_1` (node 0 grants node 1 a frame).
2. In the machine table: clear `grants[0]`, and set `uses[1][0].leaves = 1`.
3. In node 1: give the capability of the granted frame the record
   `Unmapping { space: <its aspace>, count: 1, rights: READ, .. }`, and list
   that capability in the space's `records`.
4. `node(1).check()` is `Ok(())` — node 1's own invariants agree — and
   `System::check()` is `Err("G6: a grant freed while its holder translates
   to it")`.

Proof: `deepseek_d7_g6_is_reported_of_a_record_unmapping_under_no_grant`,
which asserts both. Output:

    test scenarios::probe_d::deepseek_d7_g6_is_reported_of_a_record_unmapping_under_no_grant ... ok

## D8 — a thread waits on an entry of the unit request table that is not there

**Severity: hardening.** **Attacker: a user program whose call is answered
by a unit, and a hostile node or device that answers, or does not answer, a
unit request.**

No invariant reads `Model::unit_requests` or `Model::unit_service` (I
grepped both names over `model/src/check.rs` and `model/src/check/`: one hit,
`machine.rs:417` `self.unit_service.contains_key(&(from, credit))`, used by
CREDIT only). The waits that bound a call to a unit are excluded from
invariant 14 (`check.rs:706-708`):

```rust
        let in_queue = |thread: &&Thread| {
            !matches!(thread.wait, Wait::None | Wait::Reply(_)) && !thread.bounded()
        };
```

with `Thread::bounded` (`lib.rs:747-755`) covering `Wait::Node`, `Wait::Unit`,
`Wait::Cores` and `Wait::Hand`. Every other invariant about a wait (16, 30,
31) is about its outcome, not about what it waits on. Nothing checks:

- that a thread with `Wait::Unit(i)` has `unit_requests[i] == Some(entry)`
  with `waiter == Thread(Some(thread))`;
- that such an entry's `role` is one this node holds, its `epoch` the one
  the role word names, and its `op` one the rules of the unit allow;
- that a thread with `Wait::Hand(...)` waits for a hand-over that is in
  flight (compare invariant 44's lend and the Cores wait at
  `check/node.rs:232-239`, which *are* covered).

Steps:

1. Boot a node of two cores; the unit request table is empty.
2. Make a second thread, configured, and set its wait to `Wait::Unit(0)`.
3. `Model::check()` returns `Ok(())`.

Proof: `deepseek_d8_a_wait_on_no_unit_request_is_accepted`, which asserts the
table is empty and then `Ok(())`. Output:

    test scenarios::probe_d::deepseek_d8_a_wait_on_no_unit_request_is_accepted ... ok

The cost is a wait with nothing in flight — a call of unbounded duration
(AGENTS.md: "Every system call has a bounded duration") that the check does
not bound; the explorations test it only at the end of a run
(`explore.rs:waits_bounded`).

## D9 — a dead statement in the check of the tasks

**Severity: hardening.** **Attacker: none; the cost is that the file ends
with a check that checks nothing.**

`model/src/check/tasks.rs:55`:

```rust
        ensure(true, "50: running thread of a revoked task")
```

The loop above it does the work; the trailing `ensure(true, ...)` is the
identity. It is the shape a check takes just after somebody deletes the last
clause of it, in a file whose whole purpose is that no `ensure` is vacuous,
so it should be removed (or the clause it was meant to carry written).

---

## Functions I examined and found sound

`check.rs`: `ensure`, `Census::census`, `Model::depths` (a parent is older
than its child, invariant 1, so one pass over the `BTreeMap` is enough),
`Model::marked`, `Model::written_block`, `Model::check` (every check of the
lot is in its list), `check_identifiers` (88, with the root's class count of
invariant 59), `check_lines` (96 and R0), `check_tree` (1, 2, 3, 4, 6, 8, 20,
25, 26, 93; the `ioports` range and the `exec` of a root), `check_removal`
(21, 24: I checked that the in-degrees are counted once per edge, so the
`*count -= 1` cannot underflow and the Kahn pass cannot loop), `check_slots`
(5, 7, 23, 27, 28), `check_objects` (9, 10, 11, 25), `check_waits` (12 to 17,
22, 29, 30, 31, 40; the `endpoint.queue[0]` inside `all` is never evaluated
on an empty queue), `check_memory` (18, 19, 34, 65), `check_bindings` (32,
33).

`check/cores.rs`: `check_cores` (74, 76, 77; the `event.counts` entry and
`event.resets` make 77 judge the event and not the state, as documented).

`check/debug.rs`: `check_area` (88 to 91; `ring_holds` except for D5, and
`check_area`'s own indices are bounded by `cores` and `areas`), `check_records`
(92, 93, 95, including the platform role's ports and the `dr7` mask).

`check/machine.rs`: `System::check` (the order: the R-1 park rule, then each
running node's check, then the machine's; `D-136`'s replacement slot),
`check_cores` (P2, P3, the free word, the fence marks), `check_counts` (G4,
including the floor and the owner whose kernel is gone), `check_grants` (G6,
LEAK, and the failed unit that keeps its leaves), `check_rings` (the ring
bound with `wrapping_sub`, CREDIT, RESERVE), `in_ring`, `released`, `served`,
`check_units` (ONE-HOLDER), `check_fence_order` (the trace, which the state
cannot show), `check_reserve`, `running_node`, `has_generation`,
`Model::peers_of`, `Model::peers_sending`, `Model::serves`.

`check/memory.rs`: `check_spaces` (35, 36, 37, 38; the u128 arithmetic of the
end of a record, the overlap pass over the sorted translations, the level
count of an iospace), `check_devices` (39, except D3 which is about
`Model::domains` and not about this function).

`check/node.rs`: `check_node`, `check_window` (gap 7), `check_crossing`
(SERVED, RECEIVER, SENDER), `check_tlb` (TLB and G5, apart from D2's input),
`check_requests` (the state word, the barrier, `asked`/`acked`, the
`CORE_ANSWER_NS` bound, the pending set, the N = 1 rule), `check_marks`,
`check_locks` (N = 1, no spin, the node lock then the gate lock, the exit),
`check_epoch`, `check_credits`.

`check/sched.rs`: `check_sched` (41, 42, 43, 44, 45; `sums[sched.core]` is
reached only after the core is bounded), `check_choice` (46, apart from D1),
`check_timers` (47), `check_events` (60 to 64; `is_sorted` on the positions
of the change list, and the "no thread raised two faults" pass).

`check/table.rs`: `read`, `judge_write` (52: a take only of a word the rules
give the writer — its own free or older one, a free unclaimed one, a reserve
it holds, or that of a node whose member word reads dead or a generation
over — and a release only of a word it holds, with an identifier word freed
only to owner `0xffff`; I found no write it accepts and the rules refuse), `leaves_by_target` (the leaves of a remote record and of a kept
range), `check_table` (53 to 59: two blocks on a chunk or an entry, a block
on a word not taken, the start-up untyped and the floor, free words, the
kernel's runs and the wait of a request, the map counts, the use entries, the
page classes, the gate words, the bound on the tables one change unhooks).

`check/tasks.rs`: `check_tasks` (48, 49, 50), `check_irqs` (51).

`scenarios/mod.rs`: `machine`, `one_node`, `untyped_slot`, `slots_of`,
`retype_from`, `N::on`/`call`/`ok`/`no`/`interrupts`/`thread_on`/
`place_first`, `thread_calls`, `place_first`, `S::on`/`two`/`call`/`call_by`/
`ok`/`no`/`thread_on`/`retype`/`settle`/`run`/`run_by`/`shuffle`/`state`/
`woken`/`restarted` (every one of them runs the whole check after the step it
makes).

`scenarios/checker.rs`: every test except D6 (they spoil one thing, and the
message they assert is the one the check reports; I re-derived the order of
the checks for the ones whose spoiling touches two subsystems —
`a_map_count_that_is_not_the_leaves_of_its_chunk_is_reported`,
`a_credit_in_use_with_nothing_in_flight_is_reported`,
`a_translation_under_no_grant_is_reported`).

`scenarios/explore.rs`: `seeds`, `say`, `kill`, `seal`, `fresh`, `resume`,
`try_call` (it judges the node's state and its core before it calls),
`churn`, `quiet`, `waits_bounded`, `refresh`, `crossed`, `reached`,
`applied_handed`, `map_again`, and the seven explorations (their assertions
are on the whole check after every event and on liveness at the end; the
`once()` gate makes them return early under `DODOS_PAGE`, which the module
doc states).

`check/tests.rs`: the harness (`state`, `cap`, `object`, `At`, `orphan`,
`without_root`, `places`, `spoiled`, `spoiled_with_block`, `with_block`,
`with_device`, `with_irqs`, `with_frame`, `own_context`, `chain_down_to`,
`dying_space`, `inner_space`, `child_untyped`, `with_caller`,
`with_outcome`) and the 208 `#[test]` functions; I read them for
messages that the order of the checks would make unreachable, and found none
(the one that could, `record_that_names_a_space_that_does_not_exist`, is
asserted with a formatted message so a mismatch would print).

## What I did not examine

- `abi/` beyond the words the checks read (`Ownership`, `AttachWord`,
  `PageClass`, `CoreWord`, `Member`, `RoleWord`, `GateWord`, `Rights`,
  `Geometry`, the trace and fault constants): its encodings, its tests and
  its Kani proofs are not in this lot.
- The parts of `model/src` my checks only touch at their edges: the insides
  of `grants.rs`, `rings.rs`, `units.rs`, `nodes.rs`, `roles.rs`, `irq.rs`,
  `debug.rs`, `boot.rs`, `faults.rs`, `locks.rs`, and the calls of `caps.rs`,
  `memory.rs`, `sched.rs`, `ipc.rs` — I read what a check reads and no more.
- The invariant numbers that no file of the lot carries: 66 to 73, 75, 78 to
  87 and 94. They may be the machine's named rules (P2, P3, G4, G6, LEAK,
  CREDIT, RESERVE, ONE-HOLDER) or may be uncovered; I could not tell from the
  repository, which does not hold `architecture/kernel-interface.md`.
- The page geometries of 16 KB and 32 KB (`verify` runs the page-dependent
  tests on three geometries; I ran the 4 KB default only), the
  `DODOS_SEED`/`DODOS_COUNTS` modes of `explore.rs`, Kani, Miri and the
  address sanitizer.
- I did not run the property test or the explorations with more seeds than
  the crate's own (24 × 5000 steps and the seven explorations) to hunt for a
  state the check reports; my findings come from reading the checks and from
  the eight tests above, not from a fuzz.
