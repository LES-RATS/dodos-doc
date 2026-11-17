# Review of lot E (scenarios), Opus

Repository `/private/tmp/dodos-pr3-final`, branch `model`, head `6312868`.
Runs were made in a copy, `/private/tmp/dodos-pr3-E-opus`.
Severities: **stop** (stops the merge), **fix** (should be fixed), **question**.

## Summary

- **Stops the merge (2).** E23: the rule that a request is judged late on
  the clock without the debugger's stopped time (`sched.rs:659`) has no
  test. Changing it to the hardware clock leaves the whole model suite
  green, and the pass 20 test named after it ends on an assertion that
  holds by construction. E29: `hydrogen_n3_*` never reaches its scenario
  (the handing node is never killed, measured), and the reviews table
  cites it as the cover for Opus N3.
- **Should be fixed.**
  - E5, E6: tests whose end assertions accept almost any outcome.
  - E12, E32, E33, E34: tests that do not assert part of their name; two
    of these were measured.
  - E15: the shared `judged` helper compares only two fields of
    `UnitState`.
  - E28: the reviews table names three tests removed with L2.
  - E11, E20, E30: dead `let _ =` lines kept to silence warnings.
  - E24, E25: duplicated set-up, and set-up calls whose result is never
    asserted.
  - E1, E2: false or overstated comments and names.
- **Questions.** The rest. E7 is the most concrete: the second core that
  the comment's argument relies on never caches the translation
  (measured).
- **Checked and sound.** Two tests looked as if they could not fail. A
  mutation or a changed set-up made each fail: membership.rs:358 and
  pass19.rs:484.

## model/src/scenarios/cores.rs

**E1 (fix) cores.rs:3-4, false module comment.**
`//! two locking variants over one layout.` The file tests one variant only:
its own section heading at line 480 says `// Locking: one node lock (D-138).`,
`model/README.md` ("What it does not model") and `locks.rs:12-16` say the
lock per object (variant L2) left the contract and the model with D-138.
The module comment still announces two variants.

**E2 (fix) cores.rs:496-510, the test checks one event, not every event.**
`fn every_event_holds_the_node_lock_from_entry_to_exit_and_the_gate_lock_inside()`
reads `k.m.locks.steps` once, after the last call. `locks.rs:107-113`
(`begin_locks`) clears the trace at the start of each event ("The steps of
the current or last event", `locks.rs:85`), so the assertions judge only the
`ASpaceMap` event. The name promises every event. (The per-event check in
`check/node.rs:272` runs after every call through `N::call`, so the
property is covered there, but this test adds nothing beyond one sample and
its name overstates it.) The same holds for
`a_node_of_one_core_takes_no_lock_and_pays_no_cost_of_several_cores`
(line 483): only the trace of the final `ASpaceUnmap` is read.

**E3 (question) cores.rs:535-541, assertions weaker than the cases they name.**
`k.m.locks.steps = vec![Step::Spin(crate::locks::WaitKind::Unit)]; assert!(k.m.check().is_err());`
and `one.m.locks.steps = vec![Step::Pay(Cost::Interrupt)]; assert!(one.m.check().is_err());`
accept any error, where the three cases above them assert the exact
message. I checked `check/node.rs:272-302`: today each state can only fail
on the intended rule, so the test is right now, but it would keep passing
if the intended rule were deleted and another check happened to refuse the
state. Also, no case covers the gate lock held past the exit or an
`Unlock(Node)` without a lock: `check_locks` (check/node.rs:289-301) checks
neither (it never looks at `Unlock(Gate)`, and `Unlock(Node)` with `node ==
false` passes). If the contract forbids those, the check and this test both
miss them.

**E4 (question) cores.rs:453-478, a lower bound looser than the name.**
`a_core_that_runs_one_thread_with_no_other_event_beats_every_half_stale_ns`
runs `3 * STALE_NS` and asserts `heartbeat >= before + 5`. The heartbeat is
the count of the core's events (`sched.rs:309`). A beat every `STALE_NS / 2`
gives 6 beats in that time; the assertion also accepts a beat every
`0.6 * STALE_NS`. The real guard is the `Live` assertion (a beat slower than
`STALE_NS` would accuse the node), so this is a question of why 5 and not 6.

## model/src/scenarios/crossing.rs

**E5 (fix) crossing.rs:633-655, the test cannot fail on what its comment says.**
```
let refused = refused_count(&m, 1) - before;
assert!(refused <= 1 + dodos_abi::RING_KERNEL_ENTRIES, "{refused}");
```
The comment says "The consumer index moved to the producer minus the
ring's entries in one step, traced once; the entries left were read one by
one." `rings.rs:488-531` (`consume`) does exactly that: one refusal for the
resynchronisation, then one per entry left, so the count is exactly
`1 + RING_KERNEL_ENTRIES`. The assertion is only an upper bound: a consumer
that jumped straight to the producer index (0 refusals, nothing read) passes
it, and so does one that never traced the resynchronisation. The name says
"read as a failure of the sender"; nothing about the sender is asserted.
The assertion should be `==`.

**E6 (fix) crossing.rs:326-358, 370-383, 385-413, end assertions that accept almost anything.**
- line 354: `matches!(woken, Some(Ok(Output::Done)) | Some(Err(Error::Again)))`:
  the revoking thread may end with success or `again`; which one the
  contract gives is not decided by the test.
- line 382: `assert!(m.woken(0).is_some());` accepts any outcome, an error
  included, for "a release that crosses a revoke ends the revocation".
- line 412: `assert!(m.sys.node(0).grant_entries().is_empty() || m.woken(0).is_some());`
  is true as soon as the revoking thread was woken with anything.

**E7 (question) crossing.rs:385-413, the invariant the comment relies on may not be exercised.**
The comment at 406-409 says the slot keeping its mapping is "checked by the
TLB invariant: a slot made dead at once would drop the mapping without the
other core's invalidation". `check_tlb` (check/node.rs:81-118) only judges
translations present in a core's `tlb`, and a core fills its `tlb` only at
the end of one of its own events (`sched.rs:278-282`, `cores.rs:540-575`).
Between `map_got` (an event of node 1's first core) and the `ASpaceUnmap`
that returns `gone`, no event runs on node 1's second core (no `settle`,
no `run`), so that core may hold no translation of `AT` and the invariant
would then pass even if the slot were made dead at once.
I measured it: in the copy I printed, right after the `gone` assertion,
whether each core of node 1 holds `AT` in its `tlb`
(`nix develop -c cargo test -p dodos-model --lib a_mapped_remote_frame_whose_grant -- --nocapture`):
`PROBE core 0 caches AT: true`, `PROBE core 1 caches AT: false`. So the
second core, the one the comment's argument is about, never holds the
translation at that point; only the calling core does. The test is set up
with two cores for nothing, and the comment's reason is false as written.
Whether the invariant would still catch a dead slot through core 0 alone I
did not test.

**E8 (question) crossing.rs:528-563, the name covers a case not tested.**
`a_release_or_a_signal_that_names_a_grant_entry_of_another_grantee_or_serial_is_refused`
only sends messages from node 1, the real grantee, with `serial + 1`. The
"another grantee" half is not tested (on two nodes there is no other
grantee; three nodes would be needed).

**E9 (question) crossing.rs:508-526.** The name says "is refused and
changes nothing"; only the refusal counter is asserted. Nothing checks the
credits of node 0 (`peers[1].sends()`) or its grant entries after the
injected answer.

## model/src/scenarios/membership.rs

No finding that stops the merge. What I checked beyond reading:

- `a_fresh_start_on_cores_of_different_state_features_is_busy` (line 358)
  has no positive control, so I checked that the `busy` really comes from
  the features: in the copy, with `machine.cores[2].kind = 1;` commented
  out, the test fails with `left: Ok(Done)`, `right: Err(Busy)` at
  membership.rs:369 (`nix develop -c cargo test -p dodos-model --lib a_fresh_start_on_cores_of_different_state_features_is_busy`).
  The test is sound.
- The time sums of the VMX test (lines 447-451: `FENCE_NS + MS` then
  `2 * MS`, against `FENCE_NS + SETTLE_NS`, `SETTLE_NS` = 1 ms in
  `abi/src/machine.rs:366`) hold.

**E10 (question) membership.rs:690-699.**
`a_sealing_node_returns_to_live_if_no_other_node_is_live` asserts only
`Live` at the end. It never observes node 1 in state `Sealing`, so it does
not show that the seal began and was abandoned, rather than that the seal
request was dropped before it took effect (for example because node 0, its
requester, was killed in the same instant). A `assert_eq!(m.state(1),
MemberState::Sealing)` after line 694 would pin the first half.

## model/src/scenarios/mistral.rs

**E11 (fix) mistral.rs:432 and 12, dead code that keeps an import alive.**
`let _ = Hardware::Running;` is the last line of
`f14_one_interrupt_serves_at_most_sixteen_entries_of_a_user_ring` and has
nothing to do with the test; `Hardware` (imported at line 12,
`use crate::system::Hardware;`) is used nowhere else in the file. The line
exists only so the import is not reported unused. Both should go.

**E12 (fix) mistral.rs:199-244, the test does not assert half of its name, and its comment names the wrong holder.**
`f7_an_unmap_whose_unit_failed_empties_the_record_and_keeps_the_map_count`
asserts `woken == Err(Busy)` and the map count, never the record. The
comment at 237-238 says "its record is emptied". Also the comment at
205-206 says the device is "behind the unit node 0 holds". I measured
both in the copy with `eprintln!` probes
(`nix develop -c cargo test -p dodos-model --lib f7_an_unmap -- --nocapture`):
`PROBE attach Ok(Waits) holder of role 0: 1` and, at the end,
`PROBE record after Empty`. So the holder of unit 0 on the reference
machine is node 1 (as `membership.rs:5-6` says), the request crosses to
node 1, and the record is in fact emptied today but no assertion holds it:
a mutation that kept the record would pass this test. The attach result
is also not asserted (`if m.call(0, attach) == WAITS { ... }`): an attach
refused outright would let the test go on.

**E13 (question) mistral.rs:24-25, comment against the set-up.**
"Node 1 starts again on cores 1 and 2, and is accused before either core
took its request: the fence's first round cancels both." Only core 2 is
hung (`m.sys.hang(2, false)`), and only `start_requests[2]` is asserted.
Core 1 is free to take its request in the loop at 28-36, so "before either
core" and "cancels both" are not what the test sets up or checks.

**E14 (question) mistral.rs:386-388.** `m.sys.node_mut(1).send_pending()`
changes node 1's state directly and no `check()` follows, unlike every other
step of the file. Probably harmless, but it is the one place in the lot
where a state change is not followed by the whole check that the module
comment of `scenarios/mod.rs` promises ("every step is followed by the
whole check").

## model/src/scenarios/pass17.rs

**E15 (fix) pass17.rs:534-557, `judged` checks less than its comment says.**
```
/// The holder judges `op` from `requester`; returns whether its gate
/// refused it, and checks that a refusal changed nothing on the unit.
...
        assert_eq!(
            after.map(|u| (u.entries, u.lines)),
            unit.map(|u| (u.entries, u.lines))
        );
```
`UnitState` (`table.rs:145-161`) also holds `domains`, `remap`, `queue`,
`mapped`, `masked` and `next` (the serial of the next submission). A
refused request that still wrote the domain number of an attach, a
remapping entry, or submitted a command to the unit (`queue`/`next`) passes
this helper. This matters for the tests that use it: in
`the_holder_refuses_an_attach_under_a_domain_number_of_another_node`
(line 593) two refused attaches are followed by an accepted one, and the
final `domains[&0x10] == own` would hide a refused attach that had written
`domains`. The section comment at 519-522 also promises that a refused
request "is answered done"; no caller checks the answer. Comparing the
whole `UnitState` (it derives `PartialEq`, `table.rs:144`) would close
it with a shorter line than the current one. Also no `m.sys.check()`
follows the direct `model.unit_requested(...)` call.

**E16 (question) pass17.rs:246-249, a wrapper with no purpose.**
`pub(super) fn granted_to_1(m: &mut S) { granted(m); }` only renames the
private `granted` for `pass18.rs:560` and `checker.rs:574`. Making
`granted` itself `pub(super)` removes a function.

**E17 (question) pass17.rs:513.** `let handle = 50 - 48;` hard-codes the
first claimable vector (48) and the handle layout of core 0 (`core * 192 +
vector - 48`, as `handle(core)` at lines 669 and 693 spell it with `+ 3` and
`+ 2`). Three spellings of one layout in one file, and `pass18.rs:353` and
`pass18.rs:418` add a fourth and fifth (`requester * 192`, `b * 192`, the
number written out instead of `IRQ_TABLE_ENTRIES`). A named helper would
keep them in step.

The arithmetic of the RESERVE test (lines 351-389) checks out against
`abi/src/ring.rs`: `RING_KERNEL_ENTRIES` 64, `RING_ANSWER_RESERVE` = 16 + 8
+ 10 = 34, so 30 entries of room; owed = 11 (Report) + 15 (Revoke) + 8
(Send) = 34; after the 11-entry report 23 and 23; one more entry, 22 for 23.

## model/src/scenarios/pass18.rs

No finding that stops the merge. The tests that use `judged` (lines 291-373,
422) inherit E15.

**E18 (question) pass18.rs:209-248, clumsy set-up and a one-line wrapper.**
`claim_on` fixes `vector: 48`, so the first claim rewrites it through
`if let Syscall::IrqClaim { vector, .. } = &mut call { *vector = 49; }`;
a `vector` parameter would be one argument. `fn role_holder(m: &S, role:
usize) -> u16 { m.sys.role(role).holder() }` wraps one expression used once.

**E19 (question) pass18.rs:120-134.**
`a_stale_wake_of_a_halted_park_stub_writes_the_current_park_request` edits
the table and fires `late_wake` with no `m.sys.check()` after either step,
unlike its neighbours (`settle` runs the check in the tests above it).

## model/src/scenarios/pass19.rs

What I checked beyond reading: the test
`a_node_sealed_before_a_long_stop_in_the_stub_is_not_accused_with_seal_at_the_release`
(line 484) looked as if its 10 ms window after the release might hold no
sweep, so that it could not fail. I mutated `Model::evidence`
(`nodes.rs:631`) in the copy to use `self.now` instead of
`self.membership_now()` for a sealed node; the test fails at
pass19.rs:495 with `left: Dead`, `right: Sealed`. The test is sound.

**E20 (fix) pass19.rs:565 and 577, dead code.**
`let (mut m, holder, a, _) = holder_requester_third();` then
`let _ = holder;`. `holder` is never used; the second line only silences
the warning. Bind `_` in the pattern and drop the line. Same file, line
573-576: `let claimed = m.call(a, claim); if claimed == WAITS { m.settle(); }`
does not assert the claim succeeded; a refused claim would surface only as
the `expect("the irq")` panic two lines later, with a misleading message.

**E21 (question) pass19.rs:563-604, a state no event can make, with no check.**
The test writes an entry straight into `node.unit_requests` (with
`epoch: 0`, `order: 0`, `Waiter::Thread(None)`) through `node_mut` and calls
`irq_removal` on it, with no `check()` before or after. Whether that entry
is one the model can actually reach (a redirection request queued for a
line whose claim already completed) is not shown; if the whole check would
refuse that state, the test exercises a branch only an impossible state
takes. I did not run the check on it.

**E22 (question) pass19.rs:639 and 714, a parameter shadowed by a different quantity.**
`fn acknowledged_after_grants(rounds: u32, blocks: u32)` uses `blocks` as
the number of runs to take, then `let blocks = m.sys.node(0).untypeds ...
.count();` rebinds it to the count of run untypeds and returns that. The
callers assert the returned value equals what they passed, so it works,
but a reader of the return tuple sees the same name for the request and
the measurement.

## model/src/scenarios/pass20.rs

**E23 (stops the merge) pass20.rs:646-671, the rule the test is named after has no test, and its last assertion cannot fail.**
`a_request_across_a_stop_is_judged_on_the_clock_less_the_stopped_time`
ends with
```
    let stop = 2 * answer;
    let now = k.m.now + stop;
    k.m.table.stopped_time += stop;
    k.m.set_now(now);
    assert_eq!(k.m.check(), Ok(()));
    assert!(k.m.membership_now() < request.started + answer);
```
`membership_now()` is `now - stopped_time` (`nodes.rs:608-610`). The test
raises both by the same `stop`, so `membership_now()` is unchanged and
equals `request.started` (asserted at line 661); the last assertion reads
`started < started + answer`, true by construction. The `check()` before it
evaluates the same formula (`check/node.rs:209`), so it holds for the same
reason. No event runs, so the code that actually judges a late request,
the due event in `sched.rs:650-663`
(`r.started + self.table.core_answer_ns <= self.membership_now()`), is never
reached.
I checked that nothing else covers it: in the copy I changed that line of
`sched.rs:659` to compare with the hardware clock,
`.is_some_and(|r| r.started + self.table.core_answer_ns <= self.now)`
(the stop is no longer left out, so after a debugger stop a node accuses
itself `CoreSilent` for a request that is not late), and ran
`nix develop -c cargo test -p dodos-model`: every test binary passes
(lib 523 passed, `calls` 347, `property` 15, all others ok, 0 failed).
So the rule of D-139 "the waits on the clock less the stopped time" for a
request (`model/README.md`, the paragraph on `pass20.rs`) has no test that
fails without it. `pass21.rs:375`
(`deepseek12_7_the_due_event_of_a_request_falls_at_...`) only checks where
the due event is armed (`request_due`), not how it judges. A test needs a
request in flight, a `stub_stop` longer than `CORE_ANSWER_NS`, and an
event on the requesting core after the release, asserting the node is
still live.

**E24 (fix) duplicated set-up across the lot.**
The rule "a check that several operations share is written once"
(`.claude/skills/dodos-rust/SKILL.md`) is broken in the test helpers:
- the search for a free unclaimed chunk
  (`(0..1u64 << (k.m.machine.phys_bits - shift)).find(|&c| k.m.ownership(c) == ...free(Unclaimed).raw())`)
  is written five times: `cores.rs:359`, `mistral.rs:305`, `pass20.rs:103`,
  `pass20.rs:273`, `pass20.rs:321` (and `pass19.rs:647` a sixth way, over
  `canonical().owners`);
- the detach built from an attach (`match call { Syscall::IoSpaceAttach {
  iommu, device, .. } => ... iospace: SlotAddr::NONE ..., other => other }`)
  is inlined at `pass19.rs:134`, `pass20.rs:459`, `pass20.rs:489`,
  `pass20.rs:680`, `pass20.rs:718`, while `pass21.rs:12` has it as
  `detach_of`. Its `other => other` arm silently turns a wrong input into
  the same call, so a typo would make a "detach" an attach;
- `kill`, `seal`, `resume`, `fresh` are `pub(super)` in `pass17.rs:41-77`,
  and written again in `reviews.rs:70-106`, `units.rs:47-53`,
  `crossing.rs:779-796` (`seal_of`, `resume_of`) and `membership.rs:19-48`
  (`stop`, `start_on`, `resume`);
- `submissions` is written twice, identical: `pass17.rs:414` and
  `units.rs:266`; `granted` three times with small differences:
  `crossing.rs:73`, `pass17.rs:251`, `reviews.rs:132`.

**E25 (fix) claims and attaches whose result is never asserted.**
The pattern `if m.call(n, claim) == WAITS { m.run(...); }` with no
assertion on the result appears at `pass20.rs:538`, `pass20.rs:563`,
`pass20.rs:602`, `pass21.rs:110`, `pass21.rs:191`, `pass21.rs:254`,
`pass21.rs:513`, `pass21.rs:556`, `pass19.rs:574`, `mistral.rs:217`,
`reviews.rs:306`. If the set-up claim or attach failed (immediately or at
its answer), these tests go on from a state they did not intend, and fail
later with an unrelated message or, worse, pass. `units.rs:62-73`
(`attached`) shows the right form: assert `DONE` in both branches.
`pass18.rs:379` (`claim_line`) returns the outcome and its callers assert it.

## model/src/scenarios/pass21.rs

**E26 (question) pass21.rs:522-541, conditional assertions.**
`deepseek12_m33_the_reclaim_of_a_second_death_of_one_slot_starts_afresh`
asserts inside `if let Some(reclaim) = m.sys.node(observer).reclaims.get(&2)`
for observers 0 and 1. If neither held a record at that instant the test
would assert only `Dead`. I measured it in the copy:
`PROBE m33 observer 0 has record: false`, `PROBE m33 observer 1 has record: true`
(`nix develop -c cargo test -p dodos-model --lib deepseek12_m33 -- --nocapture`),
so today one assertion runs. `model/README.md` leans on this test to show
mutation m33 equivalent; an `expect` on node 1's record would make sure it
keeps asserting something.

**E27 (question) pass21.rs:113, 257.** `(u64::from(n) * 192) as u16` and
`(u64::from(a) * 192) as u16`: the same hard-coded 192 as E17.

Other tests of this file that call model functions directly through
`node_mut` (lines 227, 405, 424, 439, 568, 580, 590) run no `check()`
afterwards; same remark as E14.

## model/src/scenarios/reviews.rs

**E28 (fix) reviews.rs:31, 36, 57, the table points to tests that do not exist.**
The module comment says "Where another module already holds the scenario,
the table says which test". I checked every name in the table against the
files (script: each backticked `module::name` grepped as `fn name` in
`model/src/scenarios/module.rs`). Three rows name tests that are not in
the repository:
- line 31: `| DeepSeek 4: an interrupt entry and an untyped under L2 | deepseek_4_* here |`:
  there is no `deepseek_4_*` in reviews.rs (only `deepseek_3_*` at 368 and
  `deepseek_15_*` at 401);
- line 36: `cores::under_l2_a_call_takes_its_locks_in_the_order_of_their_kind_the_gate_lock_last`:
  no such test (`grep -rn under_l2 model/src` finds only this table);
- line 57: `pass17::under_l2_a_call_records_its_locks_*` (no such test) and
  `cores::the_check_refuses_a_lock_order_the_contract_forbids` (the test is
  `the_check_refuses_a_lock_the_contract_forbids`, cores.rs:513).
These are the L2 tests removed by D-138 (README, "What it does not model").
The rows should say the finding left with L2, as `pass20.rs:735-736` does
for Mistral's findings 1 to 3. Minor: line 43's glob
`kernel_shape_*_class_*` does not match the test it means,
`kernel_shape_a_unit_role_is_not_handed_to_a_node_with_a_core_of_a_lesser_class`
(which ends in `_class`).

**E29 (stops the merge) reviews.rs:265-289, the test never reaches the case it is named after.**
`hydrogen_n3_the_node_that_hands_dies_after_step_4_and_the_target_completes_step_5_alone`:
```
    for _ in 0..200 {
        if m.sys.role(0).state() == RoleState::Handing { break; }
        m.run(100_000);
    }
    if m.sys.role(0).state() == RoleState::Handing {
        m.ok(0, kill(1));
    }
```
The kill happens only if the loop observed `Handing`. I printed it in the
copy (`nix develop -c cargo test -p dodos-model --lib hydrogen_n3 -- --nocapture`):
`PROBE n3 handing reached: false`. So node 1 is never killed: the test runs
a plain hand-over from node 1 to node 2 and checks it ended held by 2. The
scenario of Opus N3 (the handing node dies after step 4) is not exercised,
and the table row at line 19 cites this test for it. The result of the
`RoleHand` call is also discarded (`let _ = m.call(...)`). The units.rs
test the same row cites (`a_handing_word_whose_target_dies_...`) covers
the target's death, not the hander's.

**E30 (fix) reviews.rs:541 and 66, dead code that keeps an import alive.**
`let _ = CrashReason::Fenced;` closes
`kernel_shape_a_resume_runs_r0_for_a_generation_that_ended_while_the_node_was_sealed`;
`CrashReason` (imported at line 66) is used nowhere else in the file. Same
as E11.

**E31 (question) reviews.rs:149-170.**
`hydrogen_2_...` resumes only `if m.state(1) == MemberState::Sealed`; the
comment accepts that the answer may have been consumed before the seal. If
it was, the test does not exercise "gets it at the resume" at all, which is
its name. `crossing.rs:724` covers the resume case deterministically, so
this test may be redundant.

## model/src/scenarios/units.rs

**E32 (fix) units.rs:509-526, the timing in the name is not asserted.**
`a_unit_role_is_taken_over_settle_ns_after_the_stop_is_confirmed` records
`first`, the instant the holder changes, and then only asserts
`first.is_some()` and the successor. It never compares `first` with the
confirmed stop (`fences[1].confirmed`) plus `SETTLE_NS`, which is what the
name says. A take-over at the confirmation, or before it, passes.

**E33 (fix) units.rs:447-477, the step the name describes is not observed.**
`a_unit_role_is_handed_in_steps_handing_then_held_by_the_target_two_epochs_later`
accepts `assert!(handing || m.sys.role(IOMMU_ROLE).holder() == 2);`. I
printed both in the copy
(`nix develop -c cargo test -p dodos-model --lib a_unit_role_is_handed_in_steps -- --nocapture`):
`PROBE hand outcome: Ok(Waits)`, `PROBE handing seen: false`. The word is
never seen `Handing`, sampling every 100 µs; the test passes on the epoch
count alone (`epoch + 2`). The `Handing` state is observed in
`a_handing_word_whose_target_dies_...` (line 498) because the target hangs
there; this test's name promises the steps and checks only the end.

**E34 (fix) units.rs:540-554, half the name is untested.**
`the_rebuild_of_a_unit_keeps_the_entries_of_live_nodes_and_clears_those_of_no_report`
asserts that node 0's entry is kept and that node 2 has no rebuild left. No
entry without a report is set up, so "clears those of no report" is not
tested here. (`pass19.rs:175` covers a related case, an entry whose attach
word is 0.)

**E35 (question) units.rs:218-242.** The comment says "A later request is
answered failed at once", but the test accepts a `WAITS` followed by `busy`
30 ms later as well; "at once" is not checked. Similarly at line 185 the
second `unit_requested` (right epoch) is not checked to be answered `done`,
only that the entry was written.

**E36 (question) unbounded retry loops.** `pass20.rs:370`
(`while k.call(k.t, Syscall::CapDelete(s(390))) == Err(Error::Again) {}`),
`crossing.rs:244` and `pass17.rs:450` loop on `again` with no bound, where
the other files bound the same loop to 8 tries (e.g. `cores.rs:223`,
`pass20.rs:304`). A regression that made the removal return `again`
forever would hang the test run instead of failing it.

## Files read whole

All eleven files of the lot, every line, in the order given:
`model/src/scenarios/cores.rs`, `crossing.rs`, `membership.rs`,
`mistral.rs`, `pass17.rs`, `pass18.rs`, `pass19.rs`, `pass20.rs`,
`pass21.rs`, `reviews.rs`, `units.rs`.

Also read whole: `AGENTS.md`, `model/README.md`,
`.claude/skills/dodos-rust/SKILL.md`, `model/src/scenarios/mod.rs`,
`model/src/locks.rs`. Read in part, as far as needed: the start of
`.claude/skills/rust-1-100/SKILL.md`; `check/node.rs` (`check_tlb`,
`check_locks`, `check_epoch`, the request check at 149-212); `rings.rs`
(`consume`, 478-536); `system.rs` (`share`, `inject_raw`, `stub_stop`,
`break_unit`); `cores.rs` (`load_root`, `cache_here`, `request_free`);
`sched.rs` (`runnable_thread`, the end of a switch 270-290, `due`
650-663); `nodes.rs` (`membership_now`, `evidence` 608-640); `grants.rs`
(`valid`); `table.rs` (`UnitState`); `boot.rs` (`Refusal`); constants in
`abi/src/ring.rs`, `abi/src/machine.rs`, `abi/src/lib.rs`.

Not read: the rest of the model and `abi/`, `checker.rs`, `explore.rs`,
`check/tests.rs`, and the documentation repository (not available, as
the brief intends). I did not run `./verify` in full; I ran
`cargo test -p dodos-model --lib scenarios` on the unchanged copy (312
passed) and the mutation and probe runs quoted above. Every probe and
mutation was reverted in the copy with `git checkout` after its run; the
shared clone was not changed.
