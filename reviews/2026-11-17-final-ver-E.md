# Verification of the two reviews of lot E

The two reports judge the same eleven files of `model/src/scenarios/` at head
`6312868`: `v1-E-mistral.md` (2 findings) and `v1-E-opus.md` (36, E1 to E36).
I worked in a fresh copy, `/private/tmp/dodos-pr3-ver-E`, made with
`cp -R /private/tmp/dodos-pr3-final` after removing the copy an interrupted
run had left. Every mutation and probe below was run there and reverted with
`git checkout -- .`; the working tree is clean at the end, and nothing was
committed.

Baseline, before any experiment:

    cd /private/tmp/dodos-pr3-ver-E && nix develop -c ./verify
    → all green: fmt, clippy with warnings denied, 523 lib tests, `calls` 347,
      `property` 15, every other binary, and the two page geometries (16k and
      32k); total 3m35s.

The contract I judged against is `Docs/architecture/kernel-interface.md` at
`main`, with D-128 to D-140 of `Docs/decisions/README.md`.

Two findings are the same finding: **Mistral 1 and Opus E28** (the table in
`reviews.rs` names tests that do not exist) are judged once, as E28.

Verdict words are the five the brief gives; the severities are the two
reviewers' (**stop**, **fix**, **question**), with **none** for a finding I
refuted outright.

## Both reviews: the table of `reviews.rs` (Mistral 1 = Opus E28)

**Real, fix.** `model/src/scenarios/reviews.rs:31`, `36`, `57`. The four
backticked names `deepseek_4_*`,
`cores::under_l2_a_call_takes_its_locks_in_the_order_of_their_kind_the_gate_lock_last`,
`pass17::under_l2_a_call_records_its_locks_*` and
`cores::the_check_refuses_a_lock_order_the_contract_forbids` occur nowhere
but in those three rows:

    grep -rn "under_l2\|the_check_refuses_a_lock_order\|deepseek_4" model abi model/tests
    → only reviews.rs:31, reviews.rs:36, reviews.rs:57
    grep -n "fn deepseek" model/src/scenarios/reviews.rs
    → only `deepseek_3_…` (368) and `deepseek_15_…` (401)

I checked the four names of the rows by grep, as both reviewers did, and they
agree. The tests left with variant L2: `model/README.md:149-151` says
"The lock per object (variant L2): it left the contract of version 1 by
D-138, and its model left with it: the order by kind, the tries and their two
rounds, … the bound *k* (`locks::bound`), their tests and the L2 values of
the machine's configuration", and D-138 in the decision log settles the same.
The table's own preamble (lines 7-9) says such findings "have no test: the
table says so", and `pass20.rs:737-738` does it correctly ("1, 2 and 3 left
with L2"). These three rows break that convention. The only test that does
exist for the last row is `cores::the_check_refuses_a_lock_the_contract_forbids`
(`cores.rs:513`), whose name differs from the one the table gives.

Correction: in the three rows, replace the names with "left with L2" as
`pass20.rs` does. Opus's minor point also holds: line 43's glob
`kernel_shape_*_class_*` matches no test — the only one is
`kernel_shape_a_unit_role_is_not_handed_to_a_node_with_a_core_of_a_lesser_class`
(`reviews.rs:473`), which ends in `_class`; write `kernel_shape_*_class`.

## Mistral's own second finding

**M2 (units.rs:366-368) — real, fix.** The comment says "Node 1 hangs without
its handler on a class-2 core: it is fenced by INIT", and the code passes
`m.sys.hang(1, true)`. `System::hung`'s flag is documented as "whether its
kernel can still run the handler of the fence's signal"
(`system.rs:24-26`), and `System::stop` parks a x86-64 core in
`Hung { nmi: true }` by the fence's NMI (its handler runs, `system.rs:606-620`)
and a core in `Hung { nmi: false }` "by INIT" (`system.rs:634-641`). So the
comment describes `hang(1, false)`. I flipped the flag to `false` and ran the
test: `cargo test -p dodos-model --lib a_plain_role_of_a_fenced_holder` →
`ok. 1 passed`. Both arms park the core, so nothing but the reading is wrong.
Correction: either pass `false`, or write "hangs with its handler on a class-2
core: the fence's NMI parks it". No test fails without the change; this is one
of the findings I could only read, and the reason is that there is nothing to
execute — the finding is a false comment, and I ran the flag both ways to show
the test cannot tell them apart.

## Opus, `cores.rs`

**E1 (cores.rs:3-4) — real, fix.** The module comment announces "the two
locking variants over one layout", while the file's own section heading at
`cores.rs:480` reads "// Locking: one node lock (D-138)." and `README.md:149`
says L2's model left. Correction: "one node lock over one layout (D-138)".
Reading only: a comment.

**E2 (cores.rs:496-510 and 483-494) — real, fix.** The test promises "every
event" and reads one trace. `locks.rs:107-113` (`begin_locks`) does
`self.locks.steps.clear()` at the start of every event, and `end_locks`
(`locks.rs:117-139`) wraps the steps of that event. I printed the trace at the
assertion:

    cargo test -p dodos-model --lib every_event_holds_the_node_lock -- --nocapture
    PROBE E2 steps at the assertion: [Pay(Lock), Lock(Node), Lock(Gate), Unlock(Gate), Unlock(Node)]

Five steps: exactly the last event (`ASpaceUnmap`), not the retype and the
`ASpaceMap` before it. So the assertions judge one event and the name
overstates them. The same holds for
`a_node_of_one_core_takes_no_lock_and_pays_no_cost_of_several_cores`
(`cores.rs:483`), where the "takes no lock" half is vacuous by construction
(`end_locks` returns at once when `width() == 1`, so no `Lock`/`Unlock` step
is ever written); only its `Pay` half can fail. And the first and last
assertions of the two-core test are satisfied for any event that is not a
lock-free `signal`, because `end_locks` itself (`locks.rs:127-139`) wraps every
event's steps in `Lock(Node)` … `Unlock(Node)`; the test therefore cannot
notice an event that never took the lock in its own code. Correction: either
run the assertions inside the loop of the events (a small helper that checks
the trace at the end of each call, as `check/node.rs:272` does for the whole
check) or rename to "the last event"; what the name claims is covered by the
per-event check, not by this test.

**E3 (cores.rs:535-541) — real, fix.** Two halves, both measured. (a) The two
last cases use `assert!(k.m.check().is_err())` where the three above them
assert the exact message, so they would keep passing if the intended rule were
deleted and another check refused the state. (b) `check_locks`
(`check/node.rs:270-303`) never looks at `Step::Unlock(LockId::Gate)`, and
`Step::Unlock(LockId::Node)` with `node == false` simply sets `node = false`.
I fed the check three states it accepts:

    cargo test -p dodos-model --lib probe_e3 -- --nocapture
    PROBE E3 gate unlocked without a lock: Ok(())
    PROBE E3 node lock unlocked twice: Ok(())
    PROBE E3 gate lock held past its call: Ok(())

So the gap is wider than Opus wrote: a gate lock taken and never released also
passes. Correction: in `check_locks`, track the gate lock as a counter
(`Lock(Gate)` sets, `Unlock(Gate)` clears) and refuse an unmatched unlock in
either direction, and refuse a gate lock still held at the exit; in the test,
compare with `Err("…")` for all five cases. A test that fails without the
change: the same test, with the three states above asserted as errors.

**E4 (cores.rs:453-478) — real, fix.** The name says the core "beats every
half `STALE_NS`" and the assertion is `heartbeat >= before + 5` for
`run_by(3 * STALE_NS)`. A beat every `STALE_NS / 2` gives 6; the assertion
also accepts a beat every `0.6 * STALE_NS`. I measured the real number:

    cargo test -p dodos-model --lib probe_e4 -- --nocapture
    PROBE E4 beats in 3 * STALE_NS: 7 (STALE_NS = 100000000)

Correction: `assert!(… >= before + 6)`, which holds today and fails if the
beating interval regresses. The rule is the contract's ("a heartbeat event at
most `STALE_NS` / 2 ahead while a core runs", D-131), so a lower bound that
permits 5 is a weak guard, not a matter of taste.

## Opus, `crossing.rs`

**E5 (crossing.rs:633-655) — real, fix.** `rings.rs:488-531` (`consume`)
moves the consumer index to the producer minus the ring's entries once
(one refusal, one trace) and then reads the entries left one by one. The test
asserts `refused <= 1 + RING_KERNEL_ENTRIES`; measured, it is exactly that:

    cargo test -p dodos-model --lib a_producer_index_too_far_ahead -- --nocapture
    PROBE E5 refused: 65          (= 1 + RING_KERNEL_ENTRIES)

I then removed the refusal and the trace of the resynchronisation
(`rings.rs:493-497`) and ran the whole suite: 21 test binaries, all `ok`, no
failure. So nothing anywhere holds "the resynchronisation is traced once as a
failure of the sender", and the upper bound cannot notice its absence.
Correction: `assert_eq!(refused, 1 + dodos_abi::RING_KERNEL_ENTRIES, "{refused}")`;
that assertion fails on the mutation above.

**E6 (crossing.rs:354, 382, 412) — real, fix.** Read: line 353-356 accepts
`Some(Ok(Output::Done)) | Some(Err(Error::Again))` for the thread that
revoked; line 382 `assert!(m.woken(0).is_some())` accepts any outcome,
an error included; line 412 `assert!(m.sys.node(0).grant_entries().is_empty()
|| m.woken(0).is_some())` is satisfied by any wake. The middle one is the
worst: "a release that crosses a revoke ends the revocation" is guarded by an
assertion true of a failed call. Correction: assert the outcome the contract
gives where it gives one, and on line 412 assert both halves
(`grant_entries().is_empty()`, with the wake checked separately). Nothing to
run here: the finding is the shape of three assertions, and I confirmed each by
opening the lines.

**E7 (crossing.rs:385-413) — real, fix (comment).** The comment says a slot
made dead at once "would drop the mapping without the other core's
invalidation", checked by the TLB invariant. I printed which cores of node 1
hold `AT` right after the `gone` assertion:

    cargo test -p dodos-model --lib a_mapped_remote_frame_whose_grant -- --nocapture
    PROBE E7 cores of node 1 caching AT: [(1, true), (2, false)]

Core 2, the core the comment's argument is about, holds nothing: it takes no
event between `map_got` and the unmap, and a core fills its `tlb` only at the
end of its own event (`sched.rs:278-282`, `cores.rs:529-578`). So the sentence
is false as written and the two-core set-up buys nothing. What I did not test,
and say so: whether the invariant still catches a dead slot through core 1,
which does hold the translation. Correction: either give core 2 an event
(`m.run(MS)`) after `map_got` so it caches the translation, or write the
comment about the calling core and drop the second core.

**E8 (crossing.rs:528-563) — real, question.** The name promises "another
grantee or serial"; the messages are all injected from node 1, the real
grantee, and only `serial + 1` is varied. The grantee half needs a third node.
Read only, nothing to execute.

**E9 (crossing.rs:508-526) — real, question.** The name says "is refused and
changes nothing"; only `refused_count` is asserted. Node 0's credits and
grant entries are never read after the injected answer. Correction: assert
them, as `crossing.rs` does elsewhere.

## Opus, `membership.rs`

**E10 (membership.rs:690-699) — real, question.** The test asserts only
`Live` at the end; node 1 is never observed in `Sealing`, so it does not show
that the seal began and was abandoned. Reading; the O(1) fix Opus gives is
right: `assert_eq!(m.state(1), MemberState::Sealing)` before the last `run`.

## Opus, `mistral.rs`

**E11 (mistral.rs:432 with 12) — real, fix.** Measured by grep: `Hardware`
appears exactly twice in the file, the import at line 12 and
`let _ = Hardware::Running;` as the last line of `f14_…`. Correction: delete
both.

**E12 (mistral.rs:199-244) — real in part, refuted in part; question.** Three
claims. (a) The record half is not asserted by the test — true; (b) "a
mutation that kept the record would pass this test" — **refuted**: I skipped
`live(&mut self.caps, cap).record = Record::Empty;` in `Memory::freeze_unmapping`
(`memory.rs:283`) and ran the test:

    cargo test -p dodos-model --lib f7_an_unmap
    panicked at model/src/scenarios/mistral.rs:241:
    left: Err("node 0: 36: list of the records of a space")  right: Ok(())

— which is exactly what Mistral reported from the same mutation. The property
is guarded by the whole check at every step of `m.run`, so the finding loses
its "would pass" half; what remains is that the test's own assertion does not
hold it. (c) The comment at 205-206 says the device is "behind the unit node 0
holds": measured, the holder is node 1 —

    PROBE E12 holder of the IOMMU role: 1
    PROBE E12 attach outcome: Ok(Waits)
    PROBE E12 record after the failed unmap: [Mapping(…), Mapping(…), Binding(…)]

— so the request crosses, and the record is emptied (no `Unmapping` left in the
list I printed). Severity question because the property is guarded; correction:
say "node 1" in the comment, `assert_eq!(m.call(0, attach), WAITS)` instead of
`if m.call(0, attach) == WAITS`, and add an `assert` that the unmapped
capability's record reads `Empty` so the name is held by the test and not only
by invariant 36.

**E13 (mistral.rs:24-36) — real, question.** Only core 2 is hung
(`m.sys.hang(2, false)`) and only `start_requests[2]` is asserted; the comment
says "before either core took its request: the fence's first round cancels
both". Core 1 is free to take its request in the loop at 28-36. Reading;
correction: hang both cores or narrow the comment to core 2.

**E14 (mistral.rs:386-388) — real, question.** `m.sys.node_mut(1).send_pending()`
changes node 1's state with no `check()` after it, against
`scenarios/mod.rs:5` ("every step is followed by the whole check"). Correction:
`m.sys.node_mut(1).send_pending(); m.sys.check()` — a whole-check call after a
direct model call; I did not run whether the check would accept it.

## Opus, `pass17.rs`

**E15 (pass17.rs:534-557) — real, fix.** `judged` compares only
`(u.entries, u.lines)` of `UnitState`, which also holds `domains`, `remap`,
`queue`, `mapped`, `masked` and `next` (`table.rs:144-162`). I made a refused
attach write the domain it named (`units.rs:530-534`) and ran the whole suite:
all binaries `ok`. Nothing anywhere holds the contract sentence that a refused
request "is not written to the unit" (`kernel-interface.md:1040`) for the
fields the helper ignores, and the direct `model.unit_requested` call in
`judged` is not followed by `m.sys.check()`. Correction: compare the whole
`UnitState` — it derives `PartialEq` (`table.rs:144`) — so that
`assert_eq!(after, unit)` replaces the tuple, and add `m.sys.check().unwrap()`
after the call. The test that fails without the change: `judged` itself, on
the mutation above (`the_holder_refuses_an_attach_under_a_domain_number_of_another_node`
would then assert the domain it refused).

**E16 (pass17.rs:246-249) — real, question.** `granted_to_1` only renames the
private `granted`. Correction: make `granted` `pub(super)` and delete the
wrapper.

**E17 (pass17.rs:513, 669, 693, with pass18.rs:353, 418) — real, question.**
`let handle = 50 - 48;`, `core * IRQ_TABLE_ENTRIES as u16 + 3`,
`core * IRQ_TABLE_ENTRIES as u16 + 2`, and in `pass18` the number written out
(`requester * 192`, `b * 192`): one layout spelled five ways. Correction: one
`pub(super) fn handle(core: u16, vector: u16) -> u16` in `pass17.rs` used
everywhere.

## Opus, `pass18.rs`

**E18 (pass18.rs:209-248) — real, question.** `claim_on` fixes `vector: 48`
and the first claim rewrites it through `if let Syscall::IrqClaim { vector, .. }`;
`role_holder` wraps `m.sys.role(role).holder()`, used twice. Correction: a
`vector` argument on `claim_on`, and drop `role_holder`.

**E19 (pass18.rs:120-134) — real, question.** `m.sys.edit_table(…)` and
`m.sys.late_wake(1)` with no `m.sys.check()` after either, unlike the
neighbouring tests that run the check through `settle`. Same correction as E14.

## Opus, `pass19.rs`

**E20 (pass19.rs:565, 577) — real, fix.** `let (mut m, holder, a, _) = …;` then
`let _ = holder;` — dead. And `if claimed == WAITS { m.settle(); }` asserts
nothing about the claim, so a refused claim surfaces as the
`expect("the irq")` panic two lines later. Correction: bind `_` in the pattern
and assert the claim's outcome (`assert!(claimed == WAITS || claimed == DONE)`
with the woken result checked), as `units::attached` does.

**E21 (pass19.rs:563-604) — real in part (the missing check), refuted in part;
question.** Opus's worry was that the whole check might refuse the hand-written
`UnitEntry`, making the test exercise an impossible state. It does not:

    cargo test -p dodos-model --lib the_removal_of_a_lines_irq_waits -- --nocapture
    PROBE E21 whole check on the hand-written entry: Ok(())
    PROBE E21 whole check after the removal: Ok(())

So the state is one the check accepts. What remains is real: no `check()` runs
and nothing shows the entry is reachable. Correction: call `node.check()` (or
`m.sys.check()`) before and after the removal — it passes today, so the test
gains a guard at no cost — and note in the comment which path queues such an
entry.

**E22 (pass19.rs:639, 714) — real, question.** `acknowledged_after_grants(rounds, blocks)`
rebinds `blocks` to the count of run untypeds and returns it. Correction: name
the measurement `runs` (or `blocks_taken`).

## Opus, `pass20.rs`

**E23 (pass20.rs:646-671) — real, stop.** This is the most serious finding of
either report and I reproduce it exactly. `membership_now()` is
`now - stopped_time` (`nodes.rs:608-610`); the test raises `now` and
`stopped_time` by the same `stop`, so `membership_now()` does not move, equals
`request.started` (asserted at line 661) and the final
`assert!(k.m.membership_now() < request.started + answer)` reads
`started < started + answer`. No event runs, so `sched.rs:650-663` — the code
that judges a late request — is never reached. I then changed that line to the
hardware clock:

    sched.rs:659: r.started + self.table.core_answer_ns <= self.now

and ran `cargo test --workspace`: every binary `ok` (523 lib tests, 347 in
`calls`, all others). The rule has no test. The contract is explicit that the
clock less the stopped time is the one to use: the instant of a request's
start is among the stored instants "both sides of every comparison are read
from the same clock (D-139)"
(`kernel-interface.md`, "The stopped time", line 1660), and the reason it
gives names it — "the earlier rule … left every other stored instant, a seal, a
fence record, a request's start, counting the stop" — while
"a lock wait or a request not complete, longer than `CORE_ANSWER_NS` … is a
failure of the node" (line 688) is the rule being modelled.

Correction: a test that has a request in flight, a `stub_stop` longer than
`CORE_ANSWER_NS`, and an event on the requesting core after the release,
asserting the node is still live and not accused; plus, in the same test, a
second case where the stop is short and the request does become late by the
membership clock, asserting the accusation. That test fails on the mutation
above and on the opposite one. `pass21.rs:375` (`deepseek12_7`) only checks
where the due event is armed (`sched.rs:606-611`), not how it judges, so it
does not cover it.

**E24 (duplicated set-up across the lot) — real, fix.** Measured by grep:
`kill`/`seal`/`resume` are written again in `reviews.rs:70,78,86`,
`units.rs:47`, `membership.rs:19-48` and `explore.rs:47-74` beside
`pass17.rs:41-77`; the free-chunk search as
`k.m.ownership(c) == Ownership::free(Owner::Unclaimed).raw()` appears at
`cores.rs:361`, `mistral.rs:307`, `pass20.rs:105`, `275` and `323` (a sixth
spelling over `canonical().owners` at `pass19.rs:655`); the detach built from
an attach is inlined at `pass19.rs:135`, `pass20.rs:460`, `490`, `681`, `719`
and exists as `detach_of` at `pass21.rs:12`; `submissions` twice
(`pass17.rs:414`, `units.rs:266`); `granted` three times (`crossing.rs:73`,
`pass17.rs:251`, `reviews.rs:132`). This is the rule "a check that several
operations share is written once" of `dodos-rust`. Correction: delete the
per-file copies in favour of the `pass17` ones (the reverse of the usual
direction would also do, but `pass17` already holds them `pub(super)`), and put
`detach_of` beside them. The `other => other` arm of the inlined matches is
worth removing for the reason Opus gives: it turns a typo into a call that
still compiles.

**E25 (claims and attaches whose result is never asserted) — real, fix.**
`grep -n "if m.call(.*) == WAITS {"` finds the pattern at `pass20.rs:538, 563,
602` and `pass21.rs:110, 191, 254, 513, 556`, and Opus's other three sites
(`pass19.rs:574`, `mistral.rs:217`, `reviews.rs:306`) are there too. The right
form is in `units.rs:65-72`, which asserts `DONE` in both branches. Correction:
the same two-branch assertion everywhere, or a `pub(super) fn claimed(m, node)`
helper next to the other shared helpers of E24.

## Opus, `pass21.rs`

**E26 (pass21.rs:522-541) — real, question.** Both assertions sit inside
`if let Some(reclaim) = m.sys.node(observer).reclaims.get(&2)`. Measured:

    cargo test -p dodos-model --lib deepseek12_m33 -- --nocapture
    PROBE E26 observer 0 has a reclaim record: false
    PROBE E26 observer 1 has a reclaim record: true

One assertion runs today, as Opus measured; if the reclaim of node 1 moved the
test would assert only `Dead`, and `README.md` leans on this test for mutation
m33. Correction: `m.sys.node(1).reclaims.get(&2).expect("the record")` instead
of the `if let`, keeping node 0 optional.

**E27 (pass21.rs:113, 257) — real, question.** `(u64::from(n) * 192) as u16`
and `(u64::from(a) * 192) as u16` write `IRQ_TABLE_ENTRIES` out; same
correction as E17.

## Opus, `reviews.rs`

**E29 (reviews.rs:265-289) — real, stop.** `hydrogen_n3_the_node_that_hands_dies_after_step_4_and_the_target_completes_step_5_alone`
kills node 1 only if the loop saw `RoleState::Handing`. I printed every state
the loop observed:

    cargo test -p dodos-model --lib hydrogen_n3 -- --nocapture
    PROBE n3 states seen: [Held, Held, Held, Held]
    PROBE n3 handing at end: false

So the word is never `Handing`, the kill never happens, and the test runs a
plain hand-over from node 1 to node 2 that ends held by 2. The scenario the
contract has a row for — "4. handing (*X* → *Y*) written; `Handed` in flight |
*Y* completes step 5 from the word, even if the `Handed` is refused"
(`kernel-interface.md`, "What a death does at each step of a planned
hand-over") with *X* the node that dies — is not exercised by this test, and
the table row at `reviews.rs:19` cites it as the cover for Opus N3. The
`units.rs` test the same row cites covers the target's death, not the
hander's. The `RoleHand` result is also discarded (`let _ = m.call(…)`).

Correction: make the hand persist — the way `units.rs:484-500` does, by
hanging the target (`m.sys.hang(2, true)`) so step 5 cannot complete — assert
`Handing`, then kill node 1, then assert the target completed step 5 and the
word reads held by 2 with one holder at every step. Without the change the
test passes with node 1 alive throughout; with it, a model that let the death
of the hander lose the word fails.

**E30 (reviews.rs:541 with 66) — real, fix.** Measured by grep: `CrashReason`
appears twice, the import at line 66 and `let _ = CrashReason::Fenced;` closing
`kernel_shape_a_resume_runs_r0_…`. Correction: delete both.

**E31 (reviews.rs:149-170) — refuted, none.** Opus feared the answer might be
consumed before the seal, leaving the resume untested. It is not:

    cargo test -p dodos-model --lib hydrogen_2_a_thread_that_waits -- --nocapture
    PROBE E31 state of node 1 after the seal: Sealed

so the resume does run and the name is exercised today. What survives is
Opus's own remark that the test would silently degrade if the timing changed,
and that `crossing.rs:724` covers the same case deterministically; I would fold
that into a comment, not a finding.

## Opus, `units.rs`

**E32 (units.rs:509-526) — real, fix.** `first`, the instant the holder
changes, is only checked to be `Some`. Measured:

    cargo test -p dodos-model --lib a_unit_role_is_taken_over -- --nocapture
    PROBE E32 first: Some(1100000) fence confirmed: Some(Some(100000)) settle: 1000000

`100_000 + 1_000_000 = 1_100_000`: the model is right, the test does not say
so. And nothing else does: I removed `+ SETTLE_NS` from
`Roles::take_over_due` (`roles.rs:343-345`) and ran the whole suite —
`cargo test --workspace`, 21 binaries, all `ok`. The delay is the contract's
("`SETTLE_NS` … the time after the last stop sent to a core before R6 frees its
word", `kernel-interface.md:1506`, and the take-over row "after `SETTLE_NS`"),
so this is a contract rule with no test at all. Correction:
`assert_eq!(first, Some(confirmed + SETTLE_NS))` with `confirmed` read from
`table.fences[1].confirmed`, which fails on the mutation above.

**E33 (units.rs:447-477) — real, fix.** `assert!(handing || m.sys.role(IOMMU_ROLE).holder() == 2)`
lets the end state stand in for the steps in the name. Measured:

    cargo test -p dodos-model --lib a_unit_role_is_handed_in_steps -- --nocapture
    PROBE E33 handing seen: false
    PROBE E33 outcome: Ok(Waits)

The word is never seen `Handing` while sampling every 100 µs. Correction: hang
node 2 (as `units.rs:487` does) so that `Handing` persists, assert it, resume
it, and then assert the two epochs; with node 2 live the separate assertion
`assert!(handing || …)` should go.

**E34 (units.rs:540-554) — real, fix.** The test sets up no entry without a
report, so "clears those of no report" is untested here. Stronger than Opus
could see by reading: I removed the clearing from `Roles::rebuild_step`
(`roles.rs:505-510`, the `if !claimed && !sealed.contains(&node)` block) and
ran the whole suite — all 21 binaries `ok`. So no test anywhere holds the
clearing half of the rebuild. Correction: a test with three nodes in which the
taker rebuilds and one node holds an entry it does not report (and itself stays
live), asserting the entry is gone while a sealed node's entry beside it stays;
it fails on the mutation above.

**E35 (units.rs:218-242, 185) — real, question.** The comment says "A later
request is answered failed at once", and the test accepts a `WAITS` followed
by `busy` 30 ms later, which is not "at once"; line 185 checks only that the
entry was written, not that it was answered `done`. Correction: assert the
immediate answer at the second attach and the `done` answer where the count is
read.

**E36 (pass20.rs:370, crossing.rs:244, pass17.rs:450) — real, question.** Two
`while … == Err(Error::Again) {}` and one `while outcome == Err(Error::Again)`
loop are unbounded, where the same retry is bounded elsewhere
(`cores.rs:223`, `for _ in 0..8`). A regression that answered `again` for ever
would hang the test run instead of failing it. Correction: bound each to the
same 8 tries and `expect` the outcome.

## What both reviewers missed

Three of the rules the lot's tests name are held by nothing at all, and I found
them by removing the code rather than by reading the assertions: the
resynchronisation of a ring's consumer index, which is traced once as a failure
of the sender (`rings.rs:493-497`, E5), the `SETTLE_NS` a unit role's take-over
waits after a confirmed stop (`roles.rs:343-345`, E32), and the clearing of a
rebuild's entries of nodes that send no report (`roles.rs:505-510`, E34) — each
removal leaves all 21 test binaries green. The reviewers stopped at the test
that was supposed to hold them; the question worth asking of this lot is not
whether each test asserts its name but which rule has only a name. And the
reason E23 hides so well is a property of the checker that neither report
traced: `check/node.rs:205-212` accepts any state in which the node has accused
itself (`panicked ||`), so a model that accuses itself too early is refused by
nothing, and the two directions of the `CORE_ANSWER_NS` invariant are not
symmetric. Both missed, too, that `check_locks` accepts a gate lock taken and
never released — Opus saw the unmatched unlock and not the leak — so the test
named after "the gate lock inside" is weaker than either report concluded.

## The table

| Finding | Verdict | Severity | Correction, one line |
|---|---|---|---|
| M2 units.rs:366-368, comment against `hang(1, true)` | real | fix | say "with its handler" (the NMI parks it), or pass `false` |
| E1 cores.rs:3-4, "two locking variants" | real | fix | "one node lock over one layout (D-138)" |
| E2 cores.rs:496, the trace is one event | real | fix | check the trace at the end of every call, or rename to "the last event" |
| E3 cores.rs:535, any-error assertions; `check_locks` gaps | real | fix | counter for the gate lock and refuse unmatched unlocks; exact messages in the test |
| E4 cores.rs:453, `>= before + 5` | real | fix | `>= before + 6` (measured: 7 beats) |
| E5 crossing.rs:633, `refused <= 1 + ENTRIES` | real | fix | `assert_eq!(refused, 1 + RING_KERNEL_ENTRIES)` |
| E6 crossing.rs:354, 382, 412, assertions true of anything | real | fix | assert the answer the contract gives, and both halves of line 412 |
| E7 crossing.rs:406, the other core caches nothing | real | fix | give core 2 an event after `map_got`, or rewrite the comment |
| E8 crossing.rs:528, "another grantee" untested | real | question | a third node, or narrow the name |
| E9 crossing.rs:508, "changes nothing" unasserted | real | question | assert node 0's credits and grant entries |
| E10 membership.rs:690, `Sealing` never observed | real | question | assert `Sealing` before the last `run` |
| E11 mistral.rs:432, `let _ = Hardware::Running` | real | fix | delete the line and the import |
| E12 mistral.rs:199-244 | real (comment, unasserted attach) / refuted ("a mutation keeping the record would pass") | question | say node 1 holds the unit, assert the attach and the emptied record |
| E13 mistral.rs:24, "cancels both" | real | question | hang both cores, or narrow the comment to core 2 |
| E14 mistral.rs:386, no check after `send_pending` | real | question | `m.sys.check()` after the direct call |
| E15 pass17.rs:534, `judged` compares two fields | real | fix | compare the whole `UnitState`, add `m.sys.check()` |
| E16 pass17.rs:246, wrapper `granted_to_1` | real | question | make `granted` `pub(super)`, delete the wrapper |
| E17 pass17.rs:513 with pass18.rs:353, 418, 192 spelled out | real | question | one `handle(core, vector)` helper |
| E18 pass18.rs:209, `claim_on` rewrites the vector; `role_holder` | real | question | a `vector` argument; drop the one-line wrapper |
| E19 pass18.rs:120, no check after two direct writes | real | question | `m.sys.check()` after each |
| E20 pass19.rs:565, 577, dead `holder`, unasserted claim | real | fix | `_` in the pattern, assert the claim's outcome |
| E21 pass19.rs:563, hand-written entry, no check | real (no check) / refuted (that the check refuses it: it returns `Ok`) | question | `check()` before and after; say which path queues the entry |
| E22 pass19.rs:639, `blocks` shadowed | real | question | name the measurement `runs` |
| E23 pass20.rs:646, the stopped-time rule has no test | real | stop | a request in flight across a long `stub_stop`, an event after it, assert not accused |
| E24 duplicated set-up (kill/seal/resume, the free chunk, the detach, `submissions`, `granted`) | real | fix | one `pub(super)` copy of each in `pass17.rs` |
| E25 claims and attaches whose result is dropped (11 sites) | real | fix | assert `DONE` in both branches, as `units::attached` does |
| E26 pass21.rs:522, conditional assertions | real | question | `expect` node 1's reclaim record |
| E27 pass21.rs:113, 257, `* 192` | real | question | `IRQ_TABLE_ENTRIES`, as in E17 |
| E28 = Mistral 1, reviews.rs:31, 36, 57 (and the glob at 43) | real | fix | "left with L2" in the three rows; `kernel_shape_*_class` |
| E29 reviews.rs:265, `Handing` never reached, node 1 never killed | real | stop | hang the target so the word stays handing, assert it, then kill the hander |
| E30 reviews.rs:541, `let _ = CrashReason::Fenced` | real | fix | delete the line and the import |
| E31 reviews.rs:149, resume may not run | refuted (measured: node 1 is `Sealed`) | none | a comment that `crossing.rs:724` holds the deterministic case |
| E32 units.rs:509, the take-over delay unasserted | real | fix | `assert_eq!(first, Some(confirmed + SETTLE_NS))` |
| E33 units.rs:447, `Handing` never observed | real | fix | hang the target, assert `Handing`, then resume it |
| E34 units.rs:540, "clears those of no report" untested | real | fix | a live node with an unreported entry beside a sealed one; assert it is cleared |
| E35 units.rs:218, 185, "at once" and the `done` answer | real | question | assert the immediate answer and the `done` |
| E36 pass20.rs:370, crossing.rs:244, pass17.rs:450, unbounded `again` | real | question | bound each to 8 tries and `expect` |
