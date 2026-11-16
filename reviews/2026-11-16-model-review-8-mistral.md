# Model review 8 — Mistral — the tests and proofs of the executable model of the DodOS kernel

Subject: the tests and proofs of the executable model in `dodos-kernel`, branch `model`, head
`633f6f3` (pull request 3), whose commits after `8c2adef` rewrote the model for kernel nodes of
several cores. Contract read: [kernel-interface.md](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md)
(2252 lines; decisions run to D-133). Also read: `AGENTS.md` and `model/README.md` of the repo,
the skill `dodos-rust`, `model/src/property.rs` does not exist — the property tests are at
[model/tests/property.rs](/Users/btw/Documents/repos/dodos-kernel/model/tests/property.rs) (the task
said `model/src/property.rs`; the actual path is `model/tests/property.rs`, cited below as
`property.rs`).

Method: all experiments ran in a copy of the repository at `/tmp/model-review/dodos-kernel`
(a `cp -a` of the repo at `633f6f3`); nothing was ever written inside
`/Users/btw/Documents/repos/dodos-kernel`. Tests ran with
`nix develop -c cargo test -p dodos-model` (nix at `/nix/var/nix/profiles/default/bin`), a full run
about 49 s after the build. Baseline at `633f6f3` is green: 319 lib tests plus the integration
suites (boot 33, calls 347, cores 13, debug 20, faults 25, gate_attack 10, gate_classes 6,
gate_words 4, generations 5, irq 16, memory 37, property 15, sched 45, tasks 20,
verify7_deepseek 12). Each mutation was applied to the copy, the suite was run, and the copy was
reverted with `git checkout -- model abi` (only my own scratch edits were ever there). Mutation
definitions, per-mutation logs and results are kept in `/tmp/model-review/` (`mutations.py`,
`mutation-results.jsonl`, `mut-mXX.log`, `tally*.log`, `property-*.rs/.diff`).

Angle: would these tests catch a wrong model? The author says each of the 122 new scenarios in
`model/src/scenarios/` failed once under one of 82 mutations. I do not take that claim: I wrote 40
mutations of my own. 24 were killed by the suite; 16 passed the whole suite green. A mutation that
survives is a finding below, with the test that would kill it.

## Findings

### 1. The mutation campaign (40 mutations, 16 survivors)

Each survivor is one small change that makes the model wrong against one quoted sentence of the
contract, applied alone, with the whole suite still green.

**F1 — the fence can mark a core word before raising its park request, and no test can see it.**
Severity: breaks a guarantee.
Mutation: in `fence_unit` ([nodes.rs:857](/Users/btw/Documents/repos/dodos-kernel/model/src/nodes.rs:857))
the word is marked before the park request is raised (the two writes swapped inside the one event).
Contract: "the driver raises *p*'s park request, then marks *p*'s word, then stops *p* by the means
of its architecture" ([kernel-interface.md:1261](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:1261)).
Why no test fails: both writes happen inside one event, and `System::check` (whose invariants
include "fence: a word marked before its park request was raised") and the scenario
`kernel_shape_the_fence_raises_the_park_request_before_it_marks_the_word_request_before_mark`
([reviews.rs:464](/Users/btw/Documents/repos/dodos-kernel/model/src/scenarios/reviews.rs:464)) only
see post-event state, where request > before holds either way.
Smallest correction: make the park request and the mark two separate events (or assert the order
inside the model between the two writes); then the existing invariant can fail and the existing
`request_before_mark` test kills the mutation.

**F2 — the fence does not cancel start requests aimed at the fenced node.**
Severity: breaks a guarantee.
Mutation: the cancellation loop in `fence_unit` removed
([nodes.rs:878-884](/Users/btw/Documents/repos/dodos-kernel/model/src/nodes.rs:878)).
Contract: "and it cancels every start request aimed at *X*"
([kernel-interface.md:1261](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:1261)).
Why no test fails: the entry stub that later consumes the start request also refuses a word that is
not marked/live, so a stale start request is masked in every reachable scenario.
Smallest correction: a scenario that starts a node, fences it while a start request to it is in
flight, and asserts the start request is gone (or refused at once) — e.g. extend
`kernel_shape_the_fence_stops_the_joining_cores_of_a_starting_node`
([reviews.rs:531](/Users/btw/Documents/repos/dodos-kernel/model/src/scenarios/reviews.rs:531)) with a
live start request and an assertion on `start_requests`.

**F3 — R6 frees a core word without `SETTLE_NS` since the last stop sent to it.**
Severity: breaks a guarantee.
Mutation: the guard `self.now < last + SETTLE_NS` removed from `clear_step`
([nodes.rs:1334](/Users/btw/Documents/repos/dodos-kernel/model/src/nodes.rs:1334)).
Contract: a core word becomes free only when "the core is confirmed stopped, and `SETTLE_NS` have
passed since the last stop sent to it" ([kernel-interface.md:1172](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:1172)).
Why no test fails: `kernel_shape_r6_frees_a_core_word_only_settle_ns_after_the_last_stop_sent_to_it`
([reviews.rs:486](/Users/btw/Documents/repos/dodos-kernel/model/src/scenarios/reviews.rs:486)) asserts
`freed >= last_stop + SETTLE_NS`, but in every scenario that runs, the free still happens at or after
that instant anyway (`SETTLE_NS` = 1 ms, [machine.rs:258](/Users/btw/Documents/repos/dodos-kernel/abi/src/machine.rs:258);
fence retries run at 1 ms granularity, the recovery reserve at 10 ms,
[ring.rs:34](/Users/btw/Documents/repos/dodos-kernel/abi/src/ring.rs) and
[machine.rs:301](/Users/btw/Documents/repos/dodos-kernel/abi/src/machine.rs:301)), so the assertion
passes under the mutation too.
Smallest correction: a hand-written scenario that answers the park at once and fires `clear_step`
before `SETTLE_NS` has elapsed, asserting the word is still not `Free` (the mirror image of the
existing r6 test, with the clock moved to `last_stop + SETTLE_NS / 2`).

**F4 — the reclaim barrier ignores IOMMU context entries naming the dead generation.**
Severity: breaks a guarantee.
Mutation: in `barrier_holds` ([nodes.rs:1172](/Users/btw/Documents/repos/dodos-kernel/model/src/nodes.rs:1172))
the clause that no unit context entry names the node's generation was dropped.
Contract: the barrier holds only when "no context entry of any IOMMU unit names *X*'s generation"
([kernel-interface.md:1308](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:1308)).
Why no test fails: no seeded or hand-written scenario leaves a unit context entry naming the dead
generation at the moment the barrier is judged (measured: see F16-F19 — the explorers never combine
a device behind a unit with the death of its owner at barrier time).
Smallest correction: a scenario that attaches a device of *X* through a unit held by another node,
lets the holder write the context entry, kills *X*, and asserts `barrier_holds(X)` is false while
the entry still names *X*'s generation (the contract's own example at
[kernel-interface.md:371](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:371)).

**F5 — stale evidence off by one nanosecond.**
Severity: breaks a guarantee (at the boundary).
Mutation: in `evidence` ([nodes.rs:602](/Users/btw/Documents/repos/dodos-kernel/model/src/nodes.rs:602))
the stale test became `now > at + stale_ns` instead of `>=`.
Contract: "now − *t* ≥ `STALE_NS`, and now − `STALE_NS` > `idle_until`"
([kernel-interface.md:1247](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:1247)).
Why no test fails: no test sets `now` exactly to `at + STALE_NS`; `hydrogen_11_*` uses
50 × `STALE_NS` ([reviews.rs:208](/Users/btw/Documents/repos/dodos-kernel/model/src/scenarios/reviews.rs:208)).
Smallest correction: the hydrogen_11 scenario with `now = at + STALE_NS` exactly, asserting
`Evidence::Stale`.

**F6 — a remote frame capability does not check the granting node's generation.**
Severity: unsettled case (a required clause no test reaches).
Mutation: in `valid` ([grants.rs:79](/Users/btw/Documents/repos/dodos-kernel/model/src/grants.rs:79))
the `member.generation() == u.generation` conjunct was removed.
Contract: the check requires that "the granting node's member word names the generation recorded in
the use entry in a state starting, live, sealing or sealed"
([kernel-interface.md:877](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:877)).
Why no test fails: R0 and the resume cleanup remove the use entry whenever the generation ends, so
in every reachable state the clause is redundant.
Smallest correction: a direct unit test of `valid()` over a table with a surviving use entry and a
member word of another generation, or a scenario that injects the state with `inject_raw` (as
`crossing.rs:573` does for ring headers).

**F7 — a failed unit request lowers the record's counts like a done one.**
Severity: breaks a guarantee.
Mutation: in `unit_complete` ([units.rs:402](/Users/btw/Documents/repos/dodos-kernel/model/src/units.rs:402))
a `UnitResult::Failed` also calls `finish_unmapping` instead of `freeze_unmapping`.
Contract: "*failed* empties the record with its counts kept"
([kernel-interface.md:1001](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:1001)) —
the memory stays pinned.
Why no test fails: the G4 check passes because the count and the held leaves drop together, and no
test asserts that a failed unit leaves the counts unchanged. Related: the checker's escape for this
case is a stub, see F23.
Smallest correction: a scenario with a failed unit request on a record that has counts (a mapping
held), then an assertion that the use entry's leaves/count are unchanged and the frame is not
returned to the untyped.

**F8 — step 4 of a hand-over writes `handing` even when the target is dead.**
Severity: breaks a guarantee.
Mutation: in `hand_step` ([roles.rs:254](/Users/btw/Documents/repos/dodos-kernel/model/src/roles.rs:254))
step 4 writes the handing word without judging the target's liveness.
Contract: "the gate refuses if *Y* is no longer live; *X* then maps the unit again, serves it again
and stays the holder, and the call returns `busy`"
([kernel-interface.md:1421](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:1421));
the death table: "At step 4 the gate refuses: *X* maps again and stays the holder"
([kernel-interface.md:1427](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:1427)).
Why no test fails: the take-over of a handing word judged on its target repairs the word, so
ONE-HOLDER holds at every observable step.
Smallest correction: a scenario that fires events one at a time around step 4 with the target killed
in between (the interleaving `hydrogen_n3_*` approximates), asserting the role word never reads
`Handing` while its target is dead.

**F9 — a whole-tag invalidation does not clear the core's bit in the aspace's set of cores.**
Severity: breaks a guarantee (the set only ever over-reports; over-asking is safe, but the contract
sentence is violated).
Mutation: in `invalidate_on` ([cores.rs:348](/Users/btw/Documents/repos/dodos-kernel/model/src/cores.rs:348))
the `Flush::Tag` arm does not remove the core from the aspace's cores set.
Contract: "The header of an aspace holds the set of the node's cores that have loaded its tag since
it was last invalidated on them"
([kernel-interface.md:325](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:325)).
Why no test fails: no invariant requires the set to shrink; the asked/acked words carry the
invalidation.
Smallest correction: after a tag invalidation acknowledged by every core, assert the aspace's cores
set is empty (extend `cores::an_idle_core_is_not_asked_and_owes_the_invalidation_at_its_wake`
([cores.rs:304](/Users/btw/Documents/repos/dodos-kernel/model/src/scenarios/cores.rs:304)) with a
state assertion on the header's set).

**F10 — `all_cores` misses the top core of the node.**
Severity: breaks a guarantee.
Mutation: `(1 << n) - 1` became `(1 << n) - 2` in `all_cores`
([cores.rs:182](/Users/btw/Documents/repos/dodos-kernel/model/src/cores.rs:182)).
Contract: "the unmapping of a run from the kernel's own space asks every other core of the node,
idle ones included" ([kernel-interface.md:328](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:328)).
Why no test fails: the give/unmap scenarios run on core 0, and the mask differs from the correct one
only in the top bit, which is invisible when the requester is core 0 (the `a_give_*` test asserting
`asked == 0b10` for two cores coincides with the wrong mask).
Smallest correction: a give or unmap issued from a non-top core of a node of at least 3 cores with
the top core holding a stale kernel run, asserting `asked == all & !me` including the top bit.

**F11 — one request credit fewer per peer.**
Severity: wrong fact (an unchecked numeric bound).
Mutation: `Peer::free` returns credits in `0..REQUESTS_PER_PEER - 1` for requests
([rings.rs:213](/Users/btw/Documents/repos/dodos-kernel/model/src/rings.rs:213)).
Contract: "`REQUESTS_PER_PEER` (16) **request credits**"
([kernel-interface.md:940](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:940);
constant at [ring.rs:19](/Users/btw/Documents/repos/dodos-kernel/abi/src/ring.rs:19)).
Why no test fails: nothing checks the number of free request credits; the explorers never hold 16
requests in flight to one peer at once.
Smallest correction: assert `Peer::free(false)` can return index 15, or a scenario with 16
concurrent `Revoke`s to one peer (the credits explorer serves 114 sends, all consumed — never 16
requests at once).

**F12 — 33 pending releases/signals per event instead of 32.**
Severity: wrong fact (an unchecked numeric bound).
Mutation: `sent >= PENDING_STEP` became `sent > PENDING_STEP` in `send_pending`
([rings.rs:630](/Users/btw/Documents/repos/dodos-kernel/model/src/rings.rs:630)).
Contract: "pending signals are sent when room comes, in the order of the use table, at most 32 per
event" ([kernel-interface.md:946](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:946);
`PENDING_STEP = 32` at [ring.rs:29](/Users/btw/Documents/repos/dodos-kernel/abi/src/ring.rs:29)).
Smallest correction: a use table with 33 release-pending entries and one event, asserting at most 32
messages written in it.

**F13 — 9 open observations per node instead of 8.**
Severity: wrong fact (an unchecked numeric bound).
Mutation: `observe_needed` allows one more open observation
([nodes.rs:703](/Users/btw/Documents/repos/dodos-kernel/model/src/nodes.rs:703)).
Contract: "at most 8 open per node" ([kernel-interface.md:1255](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:1255);
`OBSERVATIONS_MAX = 8` at [machine.rs:242](/Users/btw/Documents/repos/dodos-kernel/abi/src/machine.rs:242)).
Smallest correction: observe 9 distinct peers in one sweep and assert the ninth is not opened.

**F14 — 17 user-ring entries served per interrupt instead of 16.**
Severity: wrong fact (an unchecked numeric bound).
Mutation: `serve_user_rings` consumes `RING_USER_STEP + 1`
([rings.rs:537](/Users/btw/Documents/repos/dodos-kernel/model/src/rings.rs:537)).
Contract: "at most 16 entries per ring per interrupt"
([kernel-interface.md:939](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:939);
`RING_USER_STEP = 16` at [ring.rs:27](/Users/btw/Documents/repos/dodos-kernel/abi/src/ring.rs:27)).
Smallest correction: fill a user ring with 17+ entries, fire one interrupt, assert the consumed
index advanced by at most 16.

**F15 — the invariant checker itself is never fed a bad state.**
Severity: unsettled case.
Mutations: `check_tlb` ([check/node.rs:82](/Users/btw/Documents/repos/dodos-kernel/model/src/check/node.rs:82))
weakened to allow a stale translation without a request or an owes bit; `check_rings` weakened so a
credit in use needs nothing in flight
([check/machine.rs:225](/Users/btw/Documents/repos/dodos-kernel/model/src/check/machine.rs:225)).
Neither fails any test.
Contract: the TLB guarantee "no thread on any core of the node … can use a translation that the call
removed or reduced", and the credit rule "a credit in use always has its request or its answer in
flight" (both invariants the model itself states in `System::check`).
Why no test fails: `System::check` is only run on states the model itself produced; no test injects
a bad state into the table and asserts `check()` returns `Err`.
Smallest correction: two tests that write a stale translation into a core's TLB (resp. mark a credit
in use with nothing in flight) directly into the table and assert `System::check()` is `Err` — this
also pins the strength of every other invariant.

The 24 mutations the suite did kill (each a single small change; full list with logs in
`/tmp/model-review/mutation-results.jsonl`):

| id | site | mutation | killed by |
|---|---|---|---|
| m01 | `model/src/rings.rs` | refused(): the receiver-generation check removed | crossing::a_message_to_an_earlier_generation_of_the_receiver_is_refused |
| m02 | `model/src/rings.rs` | refused(): the sender generation no longer compared with the member word | crossing::a_message_whose_sender_generation_is_not_current_is_refused |
| m03 | `model/src/rings.rs` | refused(): an answer's credit no longer checked to be in use with its serial and kind | crossing::an_answer_that_names_no_credit_in_use_is_refused_and_changes_nothing |
| m04 | `model/src/rings.rs` | ring_room(): no reserve of answers kept free for a kernel request | crossing::the_kernel_ring_keeps_its_reserve_of_answers_free_of_requests |
| m05 | `model/src/rings.rs` | write_message(): no ring interrupt when the ring goes from empty to not empty | 18 tests, first: crossing::a_frame_delivered_to_a_full_range_is_dropped_with_the_flag_caps_dropped |
| m06 | `model/src/rings.rs` | consume(): resync moves the consumer to producer minus entries+1 (off by one) | crossing::a_producer_index_too_far_ahead_is_read_as_a_failure_of_the_sender_and_resynchronised |
| m09 | `model/src/cores.rs` | start_request(): an idle core asked for a space's invalidation is not given the owes bit | cores::an_idle_core_is_not_asked_and_owes_the_invalidation_at_its_wake |
| m10 | `model/src/cores.rs` | answer_pending(): the acknowledging core never sets its bit in the acked set | 4 tests, first: cores::a_give_invalidates_the_kernels_own_space_on_every_core_idle_ones_included |
| m12 | `model/src/cores.rs` | load_root(): a core that loads a tag is not added to the space's set of cores | 6 tests, first: cores::a_protect_that_reduces_rights_waits_for_the_other_cores |
| m13 | `model/src/cores.rs` | mark_leaving(): the leave interrupt is never sent to the core that runs the thread | 6 tests, first: cores::a_removal_step_that_reaches_a_thread_running_on_another_core_returns_again |
| m14 | `model/src/cores.rs` | wake_core(): a core that owes an invalidation does not invalidate its tags at its wake | cores::an_idle_core_is_not_asked_and_owes_the_invalidation_at_its_wake |
| m18 | `model/src/nodes.rs` | r0(): the credits in use toward the accused node are not freed | 4 tests, first: crossing::r0_ends_with_gone_the_wait_for_an_answer_of_a_node_accused_first |
| m19 | `model/src/nodes.rs` | r0(): the waits for an answer of the accused node are not ended with gone | 5 tests, first: crossing::r0_ends_with_gone_the_wait_for_an_answer_of_a_node_accused_first |
| m22 | `model/src/nodes.rs` | node_stop(): the last live node may be killed or sealed | membership::node_stop_is_judged_and_never_leaves_no_live_node |
| m24 | `model/src/grants.rs` | release_received(): on a revoking entry the Revoke in flight is not ended | 2 tests, first: crossing::a_release_that_crosses_a_revoke_ends_the_revocation |
| m25 | `model/src/grants.rs` | remote_destroyed(): a removal done for a Revoke still sends a Release | reviews::hydrogen_n2_a_removal_done_for_a_revoke_sends_no_release |
| m26 | `model/src/grants.rs` | node_send(): no 2 send credits reserved for manage | crossing::node_send_is_busy_beyond_the_sends_in_flight_to_a_peer_two_kept_for_manage |
| m27 | `model/src/grants.rs` | send_answered(): the grant entry is never marked answered | 14 tests, first: crossing::a_mapped_remote_frame_whose_grant_is_revoking_keeps_its_slot_until_a_removal_reaches_it |
| m28 | `model/src/units.rs` | unit_requested(): the request's epoch is not judged against the role word | units::a_holder_answers_elsewhere_to_a_request_of_another_epoch_and_serves_one_of_its_epoch |
| m29 | `model/src/units.rs` | confirmed(): a broken unit confirms every submission | 2 tests, first: units::a_claim_whose_second_remapping_unit_has_failed_ends_busy_and_the_first_keeps_its_invalidation |
| m31 | `model/src/roles.rs` | take_over_due(): a handing word is judged on its holder, not its target | units::a_handing_word_whose_target_dies_is_taken_over_by_the_targets_successor |
| m32 | `model/src/roles.rs` | rebuild_step(): the entries of a sealed node are cleared when no report claims them | units::the_rebuild_keeps_without_a_report_the_entries_of_a_sealed_node |
| m36 | `model/src/locks.rs` | end_locks() L2: the gate lock is never added to the event's locks | cores::under_l2_a_call_takes_its_locks_in_the_order_of_their_kind_the_gate_lock_last |
| m37 | `model/src/nodes.rs` | accuse_with_evidence(): an accusation needs no other live or sealing node | 5 tests, first: explore::deaths_seals_resumes_and_fresh_starts_of_nodes_of_several_cores |

So the suite does catch many single-rule wrong models (the one-check refusals, the reserve, the ring
interrupt, the resync off-by-one, the owes/acked bits, R0, the last-live-node rule, the answer
marking, the epoch checks, the gate lock order), but 16 of my 40 wrong models pass green, and the
author's "each scenario failed once under one of 82 mutations" does not imply the converse: a wrong
model can pass all 122 scenarios plus the property tests.

### 2. What the seeded explorations reach (24 seeds each, `DODOS_SEED`)

Method: an instrumented copy (a `crate::tally()` eprintln at each fire/act/hang/write site of
`system.rs`, `rings.rs`, `grants.rs`, `nodes.rs`, `table.rs`) ran
`cargo test -p dodos-model --lib scenarios::explore -- --nocapture`; the instrumentation was reverted
afterwards and the copy is clean at `633f6f3`. Counts below are exact, from
`/tmp/model-review/tally-counts.txt`.

The six `explore::*` tests ([explore.rs:150,228,300,377,438,530](/Users/btw/Documents/repos/dodos-kernel/model/src/scenarios/explore.rs))
ran 132 seed-runs (24 seeds each, 12 for the credits explorer) and produced 139,351 tallied events:

| tallied | count |
|---|---|
| events Timer / Action / Ipi / CpuOff / StubHalt | 133,533 / 1,169 / 735 / 20 / **0** |
| hardware actions Ring / Stop / Park / Start / Interrupt / StopMachine | 690 / 235 / 88 / 81 / 75 / **0** |
| messages applied, by kind | 1:8, 2:8, 3:13, 4:26, 5:26, 7:129, 8:129, 10:169, 11:170, 12:3 (681 total) |
| kind 6 (`Handed`) applied / refused | **0 applied / 69 refused** |
| kind 9 (`Ping`) sent or applied | **0** |
| member-word states reached | all 8 (e.g. Dead→Starting 32, Starting→Live 75, Live→Sealing 75, Sealing→Sealed 70, Sealed→Starting 44, Live→Fencing 136, Fencing→Fenced 161, Fenced→Dead 161, Sealed→Fencing 22) |
| evidence in accusations | Kill 143, Seal 16, Stale 4; Retire and Stuck never (except self-accusation, not tallied) |
| rare: revoke crosses release / release on a revoking entry | **1 / 1** (one seed of one explorer, each) |
| rare: core parked (of which with rings waiting / wait for another node / credit in use) | 274 (13 / 1 / 1) |
| rare: core parked with a core request in flight / a record unmapping | **0 / 0** |
| rare: core hung with anything in flight | 9 hung, **0 with anything in flight** |
| full ring reached (any measure: full ring, full credit, exactly full, at reserve limit) | **0** |

**F16 — the seeds never reach a full ring or the answer reserve.**
Severity: unsettled case (coverage).
Across 132 seed-runs no ring ever filled (0 on every measure), so the rules for a full ring —
"no kernel ever waits on a full ring" and the reserve of answers
([kernel-interface.md:941-943](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:941))
— are exercised only by the single hand-written test
`crossing::the_kernel_ring_keeps_its_reserve_of_answers_free_of_requests` (which did kill m04) and
`kernel_shape_kernel_messages_are_not_blocked_by_a_full_user_ring`
([reviews.rs:551](/Users/btw/Documents/repos/dodos-kernel/model/src/scenarios/reviews.rs:551)).
Smallest correction: an explorer whose senders outpace a receiver that never reads (the credits
explorer comes close: 114 sends, all consumed) until `produced - consumed == entries`.

**F17 — a `Release` crossing a `Revoke` is reached exactly once in 132 seed-runs.**
Severity: unsettled case (coverage is one seed deep).
The crossing happened once (`rare:revoke_crosses_release` = 1, in one of the 24 seeds of
`explore::crossing_a_release_and_a_revoke_of_one_grant_in_every_order`). The real guard for this
case is the hand-written `crossing::a_release_that_crosses_a_revoke_ends_the_revocation`
([crossing.rs:371](/Users/btw/Documents/repos/dodos-kernel/model/src/scenarios/crossing.rs:371)),
which killed m24.
Smallest correction: none needed for correctness, but the explorer's seed count does not make the
crossing reliable; keep the hand-written test and add a second seed that forces both messages in
flight before either is read.

**F18 — a core stopping between two steps of a crossing is never reached by the seeds.**
Severity: unsettled case (coverage).
9 cores were hung and 274 parked during fences/seals, but none with a core invalidation request in
flight (0) or a record unmapping (0); the parked-with-something cases were 13 rings waiting, 1 wait
for another node, 1 credit in use. The death-at-each-step cases of the contract's tables
([kernel-interface.md:1225-1227](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md))
for a core stopping mid-request are therefore covered only by the hand-written scenarios in
`cores.rs`, not by exploration.
Smallest correction: an explorer variant that hangs or parks one core of a multi-core node while a
give/protect/unmap request to that core is between its steps, asserting the `again` and the owes bit.

**F19 — `Handed` is never applied, `Ping` is never sent, `StubHalt` never fires.**
Severity: unsettled case (coverage).
All 69 `Handed` messages were refused (kind 6 refused 69 times; the role still reaches `Held` via
the take-over path, `role:Handing->Held` 69), `Ping` was never sent (kind 9 = 0), and the `StubHalt`
event never fired (0). The refusal paths are covered by hand-written tests (m01-m03 kills), but the
successful `Handed` delivery at step 5 and the ping sweep have no seeded coverage.
Smallest correction: an explorer that completes a planned hand-over (target alive, no death), and
one that lets the sweep send a `Ping` to a silent peer.

### 3. The coverage floors of the property tests

The task said `model/src/property.rs`; the file is
[model/tests/property.rs](/Users/btw/Documents/repos/dodos-kernel/model/tests/property.rs). The only
commit after `8c2adef` touching it is `2553463` ("Abi and model: nodes of several cores, rings, unit
requests"). `SEEDS` = 24 and `STEPS` = 5000 are unchanged ([property.rs:19-20](/Users/btw/Documents/repos/dodos-kernel/model/tests/property.rs)).
Old values are from `8c2adef` (saved at `/tmp/model-review/property-old.rs`), new from `633f6f3`,
measured today by running the property suite and reading the `Reached` dump
(`/tmp/model-review/property-run.log`; all 15 property tests pass; the measured counts match the
"Measured" comments in the file, so the run is deterministic).

| floor | old (`8c2adef`) | new (`633f6f3`) | measured today |
|---|---|---|---|
| `dying` per kind, MADE order [untyped, cspace, aspace, frame, thread, sched, endpoint, reply, notify] — [property.rs:2475](/Users/btw/Documents/repos/dodos-kernel/model/tests/property.rs:2475) | [140, 5900, 15, 2500, 7, 6, 440, 8, 19] (old :2453) | [13, 4700, 19, 4700, 70, 6, 6, 460, 236] | [27, 9438, 39, 9509, 141, 13, 13, 920, 472] |
| `dying_copies` — :2476 | 160 (old :2454) | 16 | 32 |
| `cancelled` [queued caller, caller waiting for reply, receiver, waiter] — :2543 | [15, 5, 23, 9] (old :2520) | [15, 1, 12, 6] | [31, 3, 25, 13] |
| all other floors | unchanged between `8c2adef` and `633f6f3` (diff of the two files) | same | e.g. outside 47,633 ≥ 29,000; waits [38,742→…] all above floors; ends [15,2,1,7] measured above; sent_refused 24 ≥ 1; states and counts all above floors |

**F20 — the lowered floors now guard only against total disappearance, and every floor of 1 guards
only against zero.**
Severity: unsettled case (the floors no longer guard a bound).
Lowered: untyped 140→13, cspace 5900→4700, endpoint 440→6, `dying_copies` 160→16, `cancelled[1]` 5→1
(raised: aspace 15→19, frame 2500→4700, thread 7→70, reply 8→460, notify 19→236; sched unchanged 6).
The new comment at [property.rs:2467-2473](/Users/btw/Documents/repos/dodos-kernel/model/tests/property.rs)
admits why: "the larger counts of untyped and endpoint before it came each from one seed in which
one object stayed dying for hundreds of steps" — the old floors were guarding a one-seed artefact that
pass 15's generator change removed, so they were re-based to about half of the new measured counts
(untyped 13 of 27, endpoint 6 of 13, `dying_copies` 16 of 32, `cancelled[1]` 1 of 3). Such a floor
fails only if the behaviour disappears entirely, not if it thins out. Unchanged floors equal to 1 —
`ends[2] = 1` ([property.rs:2514](/Users/btw/Documents/repos/dodos-kernel/model/tests/property.rs:2514)),
`sent_refused = 1` (:2532), `cancelled_at_once = [3,3,1,1]` (:2547) — guard only against zero
occurrences. No floor is literally vacuous today (every measured count is above its floor), but none
of the lowered ones, and none of the 1s, would catch a partial regression.
Smallest correction: re-base each lowered floor to a fixed fraction (e.g. half) of a multi-seed
measured count, and raise the 1s to the measured minima, or state in the file that they are
smoke floors.

### 4. The narrowed Kani proofs in `abi/`

Both narrowings are in commit `6c14961` ("Abi: the Kani proofs of core words and ring indices made to
end"). I did not run Kani (not available here); this is a source-level reading of `8c2adef`/`2553463`
vs `633f6f3`.

**F21 — `core_words_read_back` now proves only 4-bit slots and generations.**
Severity: unsettled case (proof domain narrowed).
At `2553463` the proof took `(slot, generation): (u16, u8)`; at `633f6f3` it takes `(u8, u8)` masked
`slot & 0xF`, `generation & 0xF`
([machine.rs:1575](/Users/btw/Documents/repos/dodos-kernel/abi/src/machine.rs:1575), proof at :1573;
commit message: "The proof of the core words took a slot of 16 bits and a generation of 8 … It now
takes 4 bits of each"). The `CoreWord` layout stores the node slot in bits 16-31 with
`CORE_NO_SLOT = 0xFFFF` ([machine.rs:819-827](/Users/btw/Documents/repos/dodos-kernel/abi/src/machine.rs))
and the generation in bits 32-63, with `NODES_MAX = 1024`
([machine.rs:106](/Users/btw/Documents/repos/dodos-kernel/abi/src/machine.rs:106)).
What it no longer proves: read-back, field equality and flipped-check-bit refusal only for slots
0..15 and generations 0..15. Joining/owned words with any slot ≥ 16 (any node number 16..1023 on a
large machine) or any generation ≥ 16 (any later generation, and all wrap-around behaviour of the
32-bit field) are unproven. `free()` round-trip for any owner is still proven, because the field
asserts are skipped for `Free`.
Smallest correction: keep the 4-bit proof for CI and add a second proof over the full `(u16, u32)`
domain with the check recomputed symbolically, or state in the file which part of the domain is
unproven.

**F22 — `ring_indices_never_overflow_the_ring` now assumes a sane ring for the `ring_fits`
consequences.**
Severity: unsettled case.
At `2553463` the assertions under `if ring_fits(produced, consumed, entries, length, reserve)` were
unconditional; at `633f6f3` they are guarded by
`let sane = produced.wrapping_sub(consumed) <= entries;`
([ring.rs:298](/Users/btw/Documents/repos/dodos-kernel/abi/src/ring.rs), proof at :287; commit
message: "from a ring already beyond its entries (a faulty producer) a message of no entry fits
and the property does not hold").
What it no longer proves: that "a message that fits leaves the producer at most the ring's entries
ahead of the consumer, and keeps the reserve free" when the producer is already more than `entries`
ahead of the consumer — where the property is false. The receiver-side resync assertions
(`produced - ring_resync(...) <= entries` unconditionally, and `start == consumed` when sane)
remain proven for all inputs.
Can the kernel rely on the assumption for a ring written by another, possibly faulty, node? No — and
it does not need to. The producer index of ring X→Y is written only by X, "its writes are plain
stores, not gate calls, since the receiver checks every message"
([kernel-interface.md:936](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:936)) —
which is exactly why a faulty X can write an insane producer into its own ring. But the receiver of
that ring never calls `ring_fits` on it: in the model the sender checks room in its own ring
(`ring_room`, [rings.rs:261](/Users/btw/Documents/repos/dodos-kernel/model/src/rings.rs:261)), while
the receiver's path is `ring_resync` plus the readable-header rule, both still proven unconditionally,
plus the one check on every message
([kernel-interface.md:934](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:934))
(the scenario tests `an_unreadable_header_is_consumed_as_one_entry` and
`a_producer_index_too_far_ahead_…` exercise exactly this and killed m06). So: the narrowed assumption
is one a correct kernel holds for its own ring and may rely on there; for a ring written by a faulty
node the proven safety net is the resync path, not this proof — the proof's remaining content is a
statement about the sender's own bookkeeping.

**F23 — the checker's failed-unit escape is a stub.**
Severity: unsettled case.
`leaves_frozen` in [check/machine.rs:323](/Users/btw/Documents/repos/dodos-kernel/model/src/check/machine.rs:323)
is hardcoded `false`, with the doc "Whether a use entry's leaves are kept by a failed unit (never
lowered, IOMMU)". So the G6 check at [check/machine.rs:145](/Users/btw/Documents/repos/dodos-kernel/model/src/check/machine.rs:145)
never models the failed-unit frozen leaves of [kernel-interface.md:1001](/Users/btw/Documents/repos/Docs/architecture/kernel-interface.md:1001);
it is stricter than the contract, which is safe but means the failed-keeps-counts rule is checked
nowhere (see F7, whose mutation survived).
Smallest correction: implement `leaves_frozen` from the unit-request table (a failed request on the
record), or state in the doc that G6 as checked assumes no failed unit left frozen leaves.

### 5. The reviews.rs table

Ten rows of the mapping table
([reviews.rs:9-47](/Users/btw/Documents/repos/dodos-kernel/model/src/scenarios/reviews.rs)) were opened
and the named test read; all ten really exercise the finding (details in "Checked and found correct"
below). One wording nuance, not a finding: the row "Hydrogen 7, Opus N3" names both
`units::a_handing_word_whose_target_dies_…` (the target dies; the take-over is judged on it) and
`hydrogen_n3_*` ([reviews.rs:258](/Users/btw/Documents/repos/dodos-kernel/model/src/scenarios/reviews.rs:258)),
which actually covers the complementary death — the handing node dies after step 4 and the target
completes step 5 alone. Both variants exist, so the row is satisfied, but the two tests are not the
same case.

## Checked and found correct

- Baseline at `633f6f3` green, all suites (numbers above); `same_seed_gives_the_same_state`
  ([property.rs](/Users/btw/Documents/repos/dodos-kernel/model/tests/property.rs)) passes and the
  measured floors match the in-file "Measured" comments, so the property run is deterministic.
- 24 of my 40 mutations killed, each by a named test (table in section 1) — in particular the
  one-check refusals (receiver generation, sender generation, answer credit), the answer reserve,
  the empty→not-empty ring interrupt, the resync off-by-one, the idle-core owes bit and its wake
  invalidation, the acked bit, the leave IPI, R0's credit free and `gone` ends, the last-live-node
  rule, the release-crossing-revoke rule, the no-release-for-revoke rule, the 2 sends kept for
  manage, the grant `answered` mark, the unit epoch check, the broken-unit refusal, the take-over
  judged on the target, the sealed-node rebuild entries, the L2 gate lock last, and the
  accusation-needs-another-live-node rule.
- The seeded explorations reach all 8 member states, all hardware actions except StopMachine, 10 of
  12 message kinds, and Kill/Seal/Stale evidence (numbers in section 2).
- reviews.rs rows verified (table row → test → what the test really does):
  1. Hydrogen 2 → `crossing::a_resume_keeps_its_consumer_indices_and_consumes_the_answers_that_waited`
     ([crossing.rs:686](/Users/btw/Documents/repos/dodos-kernel/model/src/scenarios/crossing.rs)) — seals the waiter's node while the answer waits in the peer's ring, resumes, asserts the
     consumer index was kept and the wait ended with the answer (`Err(WouldWait)`), not `gone`;
     `hydrogen_2_*` ([reviews.rs:142](/Users/btw/Documents/repos/dodos-kernel/model/src/scenarios/reviews.rs:142)) asserts the same after a seal+resume. Correct.
  2. Hydrogen 3 → `crossing::a_release_that_crosses_a_revoke_ends_the_revocation`
     ([crossing.rs:371](/Users/btw/Documents/repos/dodos-kernel/model/src/scenarios/crossing.rs:371)) — `CapRevoke` waits while the holder deletes its capability; asserts the grant entry is
     gone, the uses empty, the waiter woken. Correct (and it killed m24).
  3. Hydrogen 6 → `crossing::an_unreadable_header_is_consumed_as_one_entry`
     ([crossing.rs:573](/Users/btw/Documents/repos/dodos-kernel/model/src/scenarios/crossing.rs:573)) and
     `a_producer_index_too_far_ahead_…` (:596) — inject a raw unreadable header (kind 200), assert
     consumed == produced and the ring still delivers; inject a producer 10×entries ahead, assert
     resync to produced and a bounded number of refusals. Correct.
  4. Hydrogen 7 / Opus N3 → `units::a_handing_word_whose_target_dies_is_taken_over_by_the_targets_successor`
     ([units.rs:464](/Users/btw/Documents/repos/dodos-kernel/model/src/scenarios/units.rs:464)) — hangs the target, hands the role, kills the target, asserts `Held` by a node ≠ target;
     `hydrogen_n3_*` covers the hander dying after step 4. Correct (see the nuance above).
  5. Opus N2 → `hydrogen_n2_a_removal_done_for_a_revoke_sends_no_release`
     ([reviews.rs:233](/Users/btw/Documents/repos/dodos-kernel/model/src/scenarios/reviews.rs:233)) — revoke to completion, asserts grant entries empty, refused count 0 (no `Release`
     naming a freed grant), uses empty. Correct (killed m25).
  6. Opus N5 → `hydrogen_n5_a_revoke_step_that_needs_a_units_invalidation_completes_its_record_by_a_unit_request`
     ([reviews.rs:284](/Users/btw/Documents/repos/dodos-kernel/model/src/scenarios/reviews.rs:284)) — maps a remote frame into an iospace on a device, revokes, fires event by event,
     asserts the record was left `Unmapping` and then completed by a unit request. Correct.
  7. DeepSeek 1 → `cores::an_idle_core_is_not_asked_and_owes_the_invalidation_at_its_wake`
     ([cores.rs:304](/Users/btw/Documents/repos/dodos-kernel/model/src/scenarios/cores.rs:304)) — suspends the thread on core 1, unmaps: completes at once with the owes bit set and the
     translation still cached; at resume, both bits cleared and the tag invalidated. Correct (killed
     m09 and m14).
  8. DeepSeek 3 → `deepseek_3_a_record_unmapping_is_busy_for_unmap_and_protect`
     ([reviews.rs:360](/Users/btw/Documents/repos/dodos-kernel/model/src/scenarios/reviews.rs:360)) — unmap from core 0 waits on core 1's loaded space; the other thread on core 1 gets
     `Busy` for both `ASpaceUnmap` and `ASpaceProtect` on the unmapping record. Correct.
  9. DeepSeek 15 → `deepseek_15_node_send_is_busy_when_the_grant_table_has_fewer_free_entries_than_frames`
     ([reviews.rs:439](/Users/btw/Documents/repos/dodos-kernel/model/src/scenarios/reviews.rs:439)) — fills all grant entries, `NodeSend` of one frame returns `Busy`. Correct.
  10. Round 2 Hydrogen 3 → `kernel_shape_a_resume_runs_r0_for_a_generation_that_ended_while_the_node_was_sealed`
      ([reviews.rs:561](/Users/btw/Documents/repos/dodos-kernel/model/src/scenarios/reviews.rs:561)) — grants to node 1, seals it, kills the granter while it is sealed, resumes, asserts the
      remote frame was dropped with no release and the uses are empty. Correct.
  Also read: Round 2 DeepSeek 6 → `kernel_shape_r6_…` ([reviews.rs:486](/Users/btw/Documents/repos/dodos-kernel/model/src/scenarios/reviews.rs:486)) asserts
  `freed >= last_stop + SETTLE_NS` directly from the sent log — a real R6 test (but see F3: it does not
  kill an early free in the scenarios that run). Round 2 DeepSeek 4 / Test 4 →
  `kernel_shape_the_fence_…_request_before_mark` ([reviews.rs:464](/Users/btw/Documents/repos/dodos-kernel/model/src/scenarios/reviews.rs:464)) asserts `park_request > before` for
  every marked core — post-event only, which is why F1 survives.
- The rows that admit no test (wording findings, removed mechanisms, DeepSeek 5 CnP "not modelled",
  Round 2 Hydrogen 6 "checked by ONE-HOLDER") say so in the table itself; consistent, not findings.

## Not checked

- Kani itself: not installed in this environment; section 4 is a source reading of the proofs at
  `2553463` and `633f6f3`, not a run. Whether the 4-bit proof actually ends in CI is unverified.
- The author's own 82 mutations and the claim that each of the 122 scenarios failed once under one of
  them: not reproduced (my 40 are independent); overlap with mine unknown.
- The property tests were run with the default page geometry only (`cargo test -p dodos-model --test
  property`); the `verify` path runs more geometries and was not run.
- The 122 scenarios were exercised only through the suite as a whole (per-mutation failing-test
  lists); I did not map each scenario to the contract sentence it guards beyond the reviews.rs rows.
- Timing constants (`SETTLE_NS` = 1 ms, `FENCE_NS` = 20 ms, `STALE_NS` = 100 ms, etc. in
  [abi/src/machine.rs:242-301](/Users/btw/Documents/repos/dodos-kernel/abi/src/machine.rs)) were read
  from source, not measured on hardware.
- Contract sentences outside the ones quoted above, and decisions after D-133, were not re-read for
  this report.
- The explorers were instrumented by adding eprintln tallies to a copy; the counts in section 2 are
  from that instrumented run (reverted afterwards), not from an unmodified binary.
